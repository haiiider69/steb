"""Tests for the SQLite error store."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from steb.store.database import (
    SCHEMA_VERSION,
    DatabaseVersionError,
    ErrorNotFoundError,
    ErrorStore,
)

WINDOWS_TRACEBACK = r"""Traceback (most recent call last):
  File "C:\Users\ASUS\Desktop\proj\app.py", line 12, in <module>
    main()
  File "C:\Users\ASUS\Desktop\proj\loader.py", line 21, in load
    return config["name"]
KeyError: 'name'
"""

LINUX_TRACEBACK = """Traceback (most recent call last):
  File "/home/alice/code/proj/app.py", line 99, in <module>
    main()
  File "/home/alice/code/proj/loader.py", line 44, in load
    return config["name"]
KeyError: 'name'
"""

OTHER_ERROR = "Traceback (most recent call last):\nValueError: bad input"


@pytest.fixture #gives each test a fresh in-memory database, so tests never affect each other
def store() -> Iterator[ErrorStore]:
    with ErrorStore(":memory:") as opened:
        yield opened #runs when the test ends and closes the connection.


def test_new_error_is_stored(store: ErrorStore) -> None:
    result = store.record_error(WINDOWS_TRACEBACK)
    assert result.is_new
    assert result.occurrence_count == 1
    assert len(result.fingerprint) == 16
    stored = store.get_error(result.error_id)
    assert stored is not None
    assert stored.exc_type == "KeyError"
    assert stored.fingerprint == result.fingerprint


def test_same_bug_from_two_machines_is_one_error(store: ErrorStore) -> None:
    first = store.record_error(WINDOWS_TRACEBACK)
    second = store.record_error(LINUX_TRACEBACK)
    assert second.error_id == first.error_id
    assert not second.is_new
    assert second.occurrence_count == 2
    assert len(store.occurrences_for(first.error_id)) == 2
    assert len(store.list_errors()) == 1


def test_different_bugs_get_different_ids(store: ErrorStore) -> None:
    first = store.record_error(WINDOWS_TRACEBACK)
    second = store.record_error(OTHER_ERROR)
    assert first.error_id != second.error_id
    assert first.fingerprint != second.fingerprint


def test_lookups(store: ErrorStore) -> None:
    result = store.record_error(WINDOWS_TRACEBACK)
    assert store.get_error(999) is None
    assert store.find_by_fingerprint("0000000000000000") is None
    found = store.find_by_fingerprint(result.fingerprint)
    assert found is not None
    assert found.id == result.error_id


def test_context_metadata_is_stored(store: ErrorStore) -> None:
    result = store.record_error(
        WINDOWS_TRACEBACK,
        command="pytest -x",
        git_branch="feature/login",
        git_commit="a1b2c3d",
        language="python",
    )
    occurrence = store.occurrences_for(result.error_id)[0]
    assert occurrence.command == "pytest -x"
    assert occurrence.git_branch == "feature/login"
    assert occurrence.git_commit == "a1b2c3d"
    assert occurrence.language == "python"


def test_secrets_are_removed_before_anything_is_stored(store: ErrorStore) -> None:
    text = "Traceback (most recent call last):\nRuntimeError: login failed DB_PASSWORD=hunter2"
    result = store.record_error(text, command="run.sh --token=abc123secret")
    fix_id = store.add_fix(result.error_id, note="rotated password=hunter2 in the vault")

    stored = store.get_error(result.error_id)
    occurrence = store.occurrences_for(result.error_id)[0]
    fix = store.fixes_for(result.error_id)[0]
    assert fix.id == fix_id

    everything = " ".join(
        [stored.normalized_text if stored else "", occurrence.redacted_text, fix.note]
        + [occurrence.command or ""]
    )
    assert "hunter2" not in everything
    assert "abc123secret" not in everything
    assert "[REDACTED:" in everything


def test_redacted_text_keeps_the_original_line_numbers(store: ErrorStore) -> None:
    result = store.record_error(WINDOWS_TRACEBACK)
    occurrence = store.occurrences_for(result.error_id)[0]
    assert "line 12" in occurrence.redacted_text
    assert "ASUS" not in occurrence.redacted_text


def test_first_and_last_seen(store: ErrorStore) -> None:
    early = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    late = datetime(2026, 11, 3, 18, 30, tzinfo=UTC)
    first = store.record_error(WINDOWS_TRACEBACK, occurred_at=early)
    store.record_error(LINUX_TRACEBACK, occurred_at=late)
    stored = store.get_error(first.error_id)
    assert stored is not None
    assert stored.first_seen == "2026-11-01T10:00:00+00:00"
    assert stored.last_seen == "2026-11-03T18:30:00+00:00"


def test_list_errors_is_newest_first_and_limited(store: ErrorStore) -> None:
    old = store.record_error(WINDOWS_TRACEBACK, occurred_at=datetime(2026, 1, 1, tzinfo=UTC))
    new = store.record_error(OTHER_ERROR, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    assert [item.id for item in store.list_errors()] == [new.error_id, old.error_id]
    assert [item.id for item in store.list_errors(limit=1)] == [new.error_id]


def test_fixes_are_listed_newest_first(store: ErrorStore) -> None:
    result = store.record_error(WINDOWS_TRACEBACK)
    store.add_fix(result.error_id, note="first attempt")
    store.add_fix(result.error_id, note="pin the dependency", git_commit="a1b2c3d")
    fixes = store.fixes_for(result.error_id)
    assert [fix.note for fix in fixes] == ["pin the dependency", "first attempt"]
    assert fixes[0].git_commit == "a1b2c3d"
    assert fixes[1].git_commit is None


def test_fix_for_unknown_error_is_rejected(store: ErrorStore) -> None:
    with pytest.raises(ErrorNotFoundError):
        store.add_fix(42, note="nothing to fix")


def test_blank_text_is_rejected(store: ErrorStore) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        store.record_error("   \n")


def test_data_survives_closing_and_reopening(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "folder" / "steb.db"
    with ErrorStore(path) as first:
        result = first.record_error(WINDOWS_TRACEBACK)
        first.add_fix(result.error_id, note="pin urllib3")
    with ErrorStore(path) as second:
        stored = second.find_by_fingerprint(result.fingerprint)
        assert stored is not None
        assert second.fixes_for(stored.id)[0].note == "pin urllib3"
        again = second.record_error(LINUX_TRACEBACK)
        assert again.occurrence_count == 2


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "steb.db"
    with ErrorStore(path):
        pass
    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    connection.close()


def test_database_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "steb.db"
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    connection.close()
    with pytest.raises(DatabaseVersionError):
        ErrorStore(path)
