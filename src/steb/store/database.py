"""SQLite store: the source of truth for captured errors and their fixes.

Three tables:

    * ``errors``: one row per distinct bug (one fingerprint), with an occurrence counter.
    * ``occurrences``: one row each time that bug was seen, with its context.
    * ``fixes``: the fixes recorded for a bug, optionally linked to a git commit.

Safety rule: ``ErrorStore`` takes *raw* text and runs ``redact()``, ``normalize()`` and
``fingerprint()`` itself. Nothing unredacted can reach the database, because there is no method
that accepts already-processed text from outside.

The schema version is kept in SQLite's ``user_version`` pragma, so future steb versions can
migrate old databases instead of breaking them.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from steb.ingest.fingerprint import fingerprint, parse_error
from steb.ingest.normalize import normalize
from steb.ingest.redact import redact

SCHEMA_VERSION = 1
_MEMORY = ":memory:"

_SCHEMA_V1 = """
BEGIN;
CREATE TABLE errors (
    id INTEGER PRIMARY KEY,
    fingerprint TEXT NOT NULL UNIQUE,
    exc_type TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE occurrences (
    id INTEGER PRIMARY KEY,
    error_id INTEGER NOT NULL REFERENCES errors(id) ON DELETE CASCADE,
    occurred_at TEXT NOT NULL,
    command TEXT,
    git_branch TEXT,
    git_commit TEXT,
    language TEXT,
    redacted_text TEXT NOT NULL
);
CREATE INDEX idx_occurrences_error ON occurrences(error_id);
CREATE TABLE fixes (
    id INTEGER PRIMARY KEY,
    error_id INTEGER NOT NULL REFERENCES errors(id) ON DELETE CASCADE,
    git_commit TEXT,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_fixes_error ON fixes(error_id);
PRAGMA user_version = 1;
COMMIT;
"""

# Insert a new bug, or count one more occurrence if its fingerprint already exists.
_UPSERT_ERROR = """
INSERT INTO errors (fingerprint, exc_type, normalized_text, first_seen, last_seen)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(fingerprint) DO UPDATE SET
    last_seen = excluded.last_seen,
    occurrence_count = occurrence_count + 1
"""


class ErrorNotFoundError(LookupError):
    """Raised when an operation refers to an error id that does not exist."""


class DatabaseVersionError(RuntimeError):
    """Raised when a database was created by a newer version of steb."""


@dataclass(frozen=True, slots=True)
class StoredError:
    """One distinct bug, as stored in the database.

    Attributes:
        id: The error id (what ``steb fix <id>`` refers to).
        fingerprint: The stable identifier of the bug.
        exc_type: The exception class name.
        normalized_text: The redacted and normalized error text.
        first_seen: UTC time of the first occurrence (ISO 8601).
        last_seen: UTC time of the latest occurrence (ISO 8601).
        occurrence_count: How many times this bug was recorded.
    """

    id: int
    fingerprint: str
    exc_type: str
    normalized_text: str
    first_seen: str
    last_seen: str
    occurrence_count: int


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One time a bug was seen.

    Attributes:
        id: The occurrence id.
        error_id: The bug this occurrence belongs to.
        occurred_at: UTC time (ISO 8601).
        command: The redacted command that failed, if known.
        git_branch: The git branch at that moment, if known.
        git_commit: The git commit at that moment, if known.
        language: The programming language, if known.
        redacted_text: The error text with secrets removed, but otherwise as it was printed.
    """

    id: int
    error_id: int
    occurred_at: str
    command: str | None
    git_branch: str | None
    git_commit: str | None
    language: str | None
    redacted_text: str


@dataclass(frozen=True, slots=True)
class Fix:
    """A recorded fix for a bug.

    Attributes:
        id: The fix id.
        error_id: The bug this fix belongs to.
        note: What was done, with secrets removed.
        git_commit: The commit containing the fix, if any.
        created_at: UTC time the fix was recorded (ISO 8601).
    """

    id: int
    error_id: int
    note: str
    git_commit: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class RecordResult:
    """What happened when an error was recorded.

    Attributes:
        error_id: The id of the bug (new or existing).
        fingerprint: The bug's fingerprint.
        is_new: True if this is the first time the bug was seen.
        occurrence_count: How many times the bug has now been recorded.
    """

    error_id: int
    fingerprint: str
    is_new: bool
    occurrence_count: int


def _timestamp(when: datetime | None) -> str:
    """Format a time as a UTC ISO 8601 string, using the current time by default."""
    moment = when if when is not None else datetime.now(UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _redact_optional(text: str | None) -> str | None:
    """Redact a text that may be missing."""
    return None if text is None else redact(text)


class ErrorStore:
    """The error database.

    Use it as a context manager so the connection is always closed::

        with ErrorStore(settings.db_path) as store:
            result = store.record_error(stderr_text)
    """

    def __init__(self, path: str | Path) -> None:
        """Open (and create if needed) the database at ``path``.

        Args:
            path: Database file, or ``":memory:"`` for a temporary database (used in tests).

        Raises:
            DatabaseVersionError: If the file was created by a newer version of steb.
        """
        if str(path) != _MEMORY:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        try:
            self._migrate()
        except Exception:
            self._conn.close()
            raise

    def _migrate(self) -> None:
        """Create the schema if the database is new; refuse databases from the future."""
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            message = (
                f"database schema version {version} is newer than supported "
                f"version {SCHEMA_VERSION}; upgrade steb"
            )
            raise DatabaseVersionError(message)
        if version < 1:
            self._conn.executescript(_SCHEMA_V1)
        # Future migrations go here, e.g. ``if version < 2: ...``.

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> Self:
        """Return the store itself for use in a ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection when the ``with`` block ends."""
        self.close()

    def record_error(
        self,
        raw_text: str,
        *,
        command: str | None = None,
        git_branch: str | None = None,
        git_commit: str | None = None,
        language: str | None = None,
        occurred_at: datetime | None = None,
    ) -> RecordResult:
        """Record one occurrence of an error.

        The text is redacted, normalized and fingerprinted here. If the fingerprint is already
        known, the existing bug's counter goes up; otherwise a new bug is created.

        Args:
            raw_text: The error text exactly as it was printed.
            command: The command that failed.
            git_branch: The current git branch.
            git_commit: The current git commit.
            language: The programming language.
            occurred_at: When it happened (defaults to now).

        Returns:
            The id and fingerprint of the bug and whether it is new.

        Raises:
            ValueError: If ``raw_text`` is empty.
        """
        if not raw_text.strip():
            message = "raw_text must not be empty"
            raise ValueError(message)

        redacted = redact(raw_text)
        normalized = normalize(redacted)
        key = fingerprint(normalized)
        exc_type = parse_error(normalized).exc_type
        when = _timestamp(occurred_at)

        with self._conn:
            #opens a transaction. If everything inside succeeds, it commits;
            #if anything fails, it rolls back.
            #So a bug and its occurrence are saved together or not at all
            self._conn.execute(_UPSERT_ERROR, (key, exc_type, normalized, when, when))
            row = self._conn.execute(
                "SELECT id, occurrence_count FROM errors WHERE fingerprint = ?", (key,)
            ).fetchone()
            self._conn.execute(
                "INSERT INTO occurrences (error_id, occurred_at, command, git_branch,"
                " git_commit, language, redacted_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    when,
                    _redact_optional(command),
                    git_branch,
                    git_commit,
                    language,
                    redacted,
                ),
            )
        return RecordResult(
            error_id=row["id"],
            fingerprint=key,
            is_new=row["occurrence_count"] == 1,
            occurrence_count=row["occurrence_count"],
        )

    def add_fix(self, error_id: int, *, note: str, git_commit: str | None = None) -> int:
        """Attach a fix to a bug.

        Args:
            error_id: The bug the fix belongs to.
            note: What was done to fix it (secrets are removed).
            git_commit: The commit containing the fix, if any.

        Returns:
            The id of the new fix.

        Raises:
            ErrorNotFoundError: If ``error_id`` does not exist.
        """
        if self.get_error(error_id) is None:
            message = f"no error with id {error_id}"
            raise ErrorNotFoundError(message)
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO fixes (error_id, git_commit, note, created_at) VALUES (?, ?, ?, ?)",
                (error_id, git_commit, redact(note), _timestamp(None)),
            )
        return int(cursor.lastrowid or 0)

    def get_error(self, error_id: int) -> StoredError | None:
        """Return the bug with this id, or ``None`` if it does not exist."""
        row = self._conn.execute("SELECT * FROM errors WHERE id = ?", (error_id,)).fetchone()
        return None if row is None else _error_from_row(row)

    def find_by_fingerprint(self, key: str) -> StoredError | None:
        """Return the bug with this fingerprint, or ``None`` if it was never seen."""
        row = self._conn.execute("SELECT * FROM errors WHERE fingerprint = ?", (key,)).fetchone()
        return None if row is None else _error_from_row(row)

    def list_errors(self, limit: int = 20) -> list[StoredError]:
        """Return the most recently seen bugs, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM errors ORDER BY last_seen DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_error_from_row(row) for row in rows]

    def occurrences_for(self, error_id: int) -> list[Occurrence]:
        """Return every recorded occurrence of a bug, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM occurrences WHERE error_id = ? ORDER BY id", (error_id,)
        ).fetchall()
        return [Occurrence(**dict(row)) for row in rows]

    def fixes_for(self, error_id: int) -> list[Fix]:
        """Return the fixes recorded for a bug, newest first."""
        rows = self._conn.execute(
            "SELECT id, error_id, note, git_commit, created_at FROM fixes"
            " WHERE error_id = ? ORDER BY id DESC",
            (error_id,),
        ).fetchall()
        return [Fix(**dict(row)) for row in rows]


def _error_from_row(row: sqlite3.Row) -> StoredError:
    """Convert a database row into a ``StoredError``."""
    return StoredError(**dict(row))
