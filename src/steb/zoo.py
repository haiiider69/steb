"""Bug zoo support: load, run and validate the reproducible bugs used for evaluation.

The zoo lives in ``eval/bug_zoo/``. Each bug is a folder ``<category>/<slug>/`` with three files:

    * ``buggy.py``: a small, realistic script that fails with a known exception;
    * ``fixed.py``: the same script with the reference fix applied, which runs cleanly;
    * ``meta.json``: the ground truth (category, expected exception, fix summary).

This module reads that format, rejects malformed bugs, and checks that every bug really behaves
as its metadata claims, so the evaluation ground truth stays honest. It is used by the scripts in
``eval/scripts/`` and by the test suite.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = (
    "import_errors",
    "type_errors",
    "value_errors",
    "key_index_errors",
    "attribute_errors",
    "file_path_errors",
    "encoding_errors",
    "removed_apis",
    "unpacking_errors",
    "timeouts_and_limits",
    "async_and_threads",
    "syntax_errors",
)

DEFAULT_TIMEOUT_SECONDS = 20.0

_REQUIRED_FIELDS = ("id", "category", "title", "exception", "message_contains", "fix_summary")
_NAME = re.compile(r"[a-z][a-z0-9_]*")
_TRACEBACK_START = "Traceback (most recent call last):"


class BugFormatError(ValueError):
    """Raised when a bug folder does not follow the zoo format."""


@dataclass(frozen=True, slots=True)
class Bug:
    """One bug of the zoo, with its ground truth.

    Attributes:
        id: The bug's identifier, ``<category>/<slug>``.
        category: One of ``CATEGORIES``.
        title: A short human description of the mistake.
        exception: The exception name exactly as Python prints it (qualified if not builtin).
        message_contains: A fragment that the exception message must contain.
        fix_summary: The reference fix, in words.
        directory: The folder holding ``buggy.py``, ``fixed.py`` and ``meta.json``.
    """

    id: str
    category: str
    title: str
    exception: str
    message_contains: str
    fix_summary: str
    directory: Path

    @property
    def slug(self) -> str:
        """The bug's folder name."""
        return self.directory.name

    @property
    def buggy_path(self) -> Path:
        """Path of the script that fails."""
        return self.directory / "buggy.py"

    @property
    def fixed_path(self) -> Path:
        """Path of the script with the reference fix."""
        return self.directory / "fixed.py"


@dataclass(frozen=True, slots=True)
class ScriptRun:
    """The outcome of running one script.

    Attributes:
        exit_code: The exit code, or ``None`` if the script timed out.
        output: Everything the script printed (stdout and stderr merged).
        timed_out: Whether the script was stopped for exceeding the time limit.
    """

    exit_code: int | None
    output: str
    timed_out: bool


def default_zoo_dir() -> Path:
    """Return the zoo folder of this repository (``eval/bug_zoo``)."""
    return Path(__file__).resolve().parents[2] / "eval" / "bug_zoo"


def iter_bug_dirs(zoo_dir: Path | None = None) -> list[Path]:
    """List every bug folder of the zoo, sorted.

    Hidden folders and folders starting with ``_`` are ignored, as are stray files.

    Args:
        zoo_dir: The zoo folder (defaults to ``eval/bug_zoo``).

    Returns:
        The ``<category>/<slug>`` folders, sorted by category then slug.
    """
    root = zoo_dir if zoo_dir is not None else default_zoo_dir()
    if not root.is_dir():
        return []
    directories = []
    for category_dir in sorted(root.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
            continue
        directories.extend(
            bug_dir
            for bug_dir in sorted(category_dir.iterdir())
            if bug_dir.is_dir() and not bug_dir.name.startswith((".", "_"))
        )
    return directories


def load_bug(directory: Path) -> Bug:
    """Read and validate one bug folder.

    Args:
        directory: A ``<category>/<slug>`` folder.

    Returns:
        The bug described by its ``meta.json``.

    Raises:
        BugFormatError: If a file is missing or the metadata is malformed or inconsistent.
    """
    category = directory.parent.name
    slug = directory.name
    for name in ("meta.json", "buggy.py", "fixed.py"):
        if not (directory / name).is_file():
            message = f"{category}/{slug}: {name} is missing"
            raise BugFormatError(message)

    try:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        message = f"{category}/{slug}: meta.json is not valid JSON ({exc})"
        raise BugFormatError(message) from exc
    if not isinstance(meta, dict):
        message = f"{category}/{slug}: meta.json must contain a JSON object"
        raise BugFormatError(message)

    unknown = sorted(set(meta) - set(_REQUIRED_FIELDS))
    if unknown:
        message = f"{category}/{slug}: unknown meta.json field(s): {', '.join(unknown)}"
        raise BugFormatError(message)
    for field in _REQUIRED_FIELDS:
        value = meta.get(field)
        if not isinstance(value, str) or not value.strip():
            message = f"{category}/{slug}: meta.json field '{field}' must be a non-empty string"
            raise BugFormatError(message)

    if category not in CATEGORIES:
        message = f"{category}/{slug}: '{category}' is not a known category"
        raise BugFormatError(message)
    if not _NAME.fullmatch(slug):
        message = f"{category}/{slug}: the folder name must be lowercase letters, digits, _"
        raise BugFormatError(message)
    if meta["category"] != category:
        message = f"{category}/{slug}: meta.json says category '{meta['category']}'"
        raise BugFormatError(message)
    if meta["id"] != f"{category}/{slug}":
        message = f"{category}/{slug}: meta.json says id '{meta['id']}'"
        raise BugFormatError(message)

    return Bug(
        id=meta["id"],
        category=category,
        title=meta["title"],
        exception=meta["exception"],
        message_contains=meta["message_contains"],
        fix_summary=meta["fix_summary"],
        directory=directory,
    )


def load_zoo(zoo_dir: Path | None = None) -> list[Bug]:
    """Load every bug of the zoo.

    Args:
        zoo_dir: The zoo folder (defaults to ``eval/bug_zoo``).

    Returns:
        All bugs, sorted by id.

    Raises:
        BugFormatError: If any bug is malformed.
    """
    return [load_bug(directory) for directory in iter_bug_dirs(zoo_dir)]


def run_script(path: Path, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> ScriptRun:
    """Run a Python script in a fresh temporary directory and capture its output.

    The script is started with the current interpreter and its absolute path, like a user would
    run it. Running in a temporary working directory keeps stray files out of the repository.

    Args:
        path: The script to run.
        timeout: Seconds after which the script is stopped.

    Returns:
        The exit code (``None`` on timeout), the merged output and whether it timed out.
    """
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory() as workdir:
        try:
            completed = subprocess.run(
                [sys.executable, str(path.resolve())],
                cwd=workdir,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout if isinstance(exc.stdout, bytes) else b""
            return ScriptRun(None, partial.decode("utf-8", errors="replace"), timed_out=True)
    output = completed.stdout.decode("utf-8", errors="replace")
    return ScriptRun(completed.returncode, output, timed_out=False)


def _find_exception_line(output: str, exception: str) -> str | None:
    """Find the last line of the output that reports the given exception."""
    for line in reversed(output.splitlines()):
        if line == exception or line.startswith(f"{exception}:"):
            return line
    return None


def _last_lines(output: str, count: int = 3) -> str:
    """Return the last few non-empty lines of an output, for error messages."""
    lines = [line for line in output.splitlines() if line.strip()]
    return " | ".join(lines[-count:])


def check_bug(bug: Bug, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    """Check that a bug behaves as its metadata claims.

    The rules: ``buggy.py`` must differ from ``fixed.py``; ``buggy.py`` must exit with an error
    and report the expected exception with the expected message fragment; ``fixed.py`` must exit
    cleanly and print no traceback.

    Args:
        bug: The bug to check.
        timeout: Seconds allowed for each script.

    Returns:
        A list of problems, empty when the bug is valid.
    """
    problems = []
    buggy_text = bug.buggy_path.read_text(encoding="utf-8")
    fixed_text = bug.fixed_path.read_text(encoding="utf-8")
    if buggy_text == fixed_text:
        problems.append("buggy.py and fixed.py are identical")

    buggy = run_script(bug.buggy_path, timeout=timeout)
    if buggy.timed_out:
        problems.append(f"buggy.py did not finish within {timeout:g} seconds")
    elif buggy.exit_code == 0:
        problems.append("buggy.py exited successfully but is supposed to fail")
    else:
        line = _find_exception_line(buggy.output, bug.exception)
        if line is None:
            problems.append(
                f"buggy.py did not report {bug.exception} (last lines: {_last_lines(buggy.output)})"
            )
        elif bug.message_contains not in line:
            problems.append(f"buggy.py message {line!r} does not contain {bug.message_contains!r}")

    fixed = run_script(bug.fixed_path, timeout=timeout)
    if fixed.timed_out:
        problems.append(f"fixed.py did not finish within {timeout:g} seconds")
    elif fixed.exit_code != 0:
        problems.append(
            f"fixed.py exited with code {fixed.exit_code} (last lines: {_last_lines(fixed.output)})"
        )
    elif _TRACEBACK_START in fixed.output:
        problems.append("fixed.py exited cleanly but printed a traceback")
    return problems
