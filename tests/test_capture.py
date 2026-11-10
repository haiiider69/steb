
"""Tests for command capture and git context
The tests run real commands: a small Python snippet
launched with sys.executable,
so they behave the same on every machine.
The git tests build a throwaway
repository in a temporary folder and skip
themselves if git isn't installed."""


import io
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from steb.capture.git import git_context
from steb.capture.runner import (
    MAX_ERROR_CHARS,
    TAIL_LINES,
    CommandNotFoundError,
    extract_error_text,
    guess_language,
    run_and_capture,
)
from steb.store.database import ErrorStore


def python(code: str) -> list[str]:
    """Build a command that runs a snippet with the current Python."""
    return [sys.executable, "-c", code]


def init_repo(path: Path) -> None:
    """Create a git repository with one commit on a branch called main."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "initial commit",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def store() -> Iterator[ErrorStore]:
    with ErrorStore(":memory:") as opened:
        yield opened


def test_successful_command_is_not_recorded(store: ErrorStore) -> None:
    result = run_and_capture(python("print('hello')"), store)
    assert result.exit_code == 0
    assert "hello" in result.output
    assert result.recorded is None
    assert store.list_errors() == []


def test_failing_python_command_is_recorded(store: ErrorStore) -> None:
    result = run_and_capture(python("raise KeyError('name')"), store)
    assert result.exit_code == 1
    assert result.recorded is not None
    assert result.recorded.is_new
    stored = store.get_error(result.recorded.error_id)
    assert stored is not None
    assert stored.exc_type == "KeyError"
    occurrence = store.occurrences_for(result.recorded.error_id)[0]
    assert occurrence.language == "python"
    assert occurrence.command is not None
    assert "KeyError" in occurrence.command


def test_same_failure_twice_is_counted_twice(store: ErrorStore) -> None:
    first = run_and_capture(python("raise KeyError('name')"), store)
    second = run_and_capture(python("raise KeyError('name')"), store)
    assert first.recorded is not None
    assert second.recorded is not None
    assert second.recorded.error_id == first.recorded.error_id
    assert second.recorded.occurrence_count == 2


def test_output_is_echoed_live_and_both_streams_are_captured(store: ErrorStore) -> None:
    echo = io.StringIO()
    code = "import sys; print('to stdout'); print('to stderr', file=sys.stderr)"
    result = run_and_capture(python(code), store, echo=echo)
    for text in (result.output, echo.getvalue()):
        assert "to stdout" in text
        assert "to stderr" in text


def test_exit_code_is_passed_through_unchanged(store: ErrorStore) -> None:
    code = "import sys; print('boom', file=sys.stderr); sys.exit(3)"
    result = run_and_capture(python(code), store)
    assert result.exit_code == 3
    assert result.recorded is not None


def test_silent_failure_is_not_recorded(store: ErrorStore) -> None:
    result = run_and_capture(python("import sys; sys.exit(2)"), store)
    assert result.exit_code == 2
    assert result.recorded is None


def test_missing_program_raises_and_records_nothing(store: ErrorStore) -> None:
    with pytest.raises(CommandNotFoundError):
        run_and_capture(["definitely-not-a-real-program-xyz"], store)
    assert store.list_errors() == []


def test_empty_command_is_rejected(store: ErrorStore) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        run_and_capture([], store)


def test_secrets_in_the_output_are_not_stored(store: ErrorStore) -> None:
    result = run_and_capture(python("raise RuntimeError('DB_PASSWORD=hunter2')"), store)
    assert result.recorded is not None
    occurrence = store.occurrences_for(result.recorded.error_id)[0]
    assert "hunter2" not in occurrence.redacted_text


def test_non_ascii_output_survives(store: ErrorStore) -> None:
    result = run_and_capture(python("print('caf\\u00e9')"), store)
    assert "caf\u00e9" in result.output


def test_command_runs_in_the_given_directory(store: ErrorStore, tmp_path: Path) -> None:
    result = run_and_capture(python("import os; print(os.getcwd())"), store, cwd=tmp_path)
    assert Path(result.output.strip()).resolve() == tmp_path.resolve()


def test_extract_prefers_the_last_traceback() -> None:
    output = "\n".join(
        [
            "lots of noise",
            "Traceback (most recent call last):",
            "KeyError: 'old'",
            "more noise",
            "Traceback (most recent call last):",
            "ValueError: 'new'",
        ]
    )
    text = extract_error_text(output)
    assert text.startswith("Traceback")
    assert "ValueError: 'new'" in text
    assert "noise" not in text
    assert "old" not in text


def test_extract_reads_pytest_error_lines() -> None:
    output = "\n".join(
        [
            "tests/test_a.py::test_x FAILED",
            "    def test_x():",
            ">       d['name']",
            "E       KeyError: 'name'",
            "",
            "tests/test_a.py:3: KeyError",
            "===== 1 failed in 0.05s =====",
        ]
    )
    assert extract_error_text(output) == "KeyError: 'name'"


def test_extract_falls_back_to_the_last_lines() -> None:
    output = "\n".join(f"line {number}" for number in range(100))
    lines = extract_error_text(output).splitlines()
    assert len(lines) == TAIL_LINES
    assert lines[-1] == "line 99"


def test_extract_removes_terminal_colors() -> None:
    output = "\x1b[31mTraceback (most recent call last):\x1b[0m\nKeyError: 'x'"
    assert "\x1b" not in extract_error_text(output)


def test_extract_caps_the_size_and_handles_empty_output() -> None:
    assert len(extract_error_text("x" * (MAX_ERROR_CHARS + 500))) == MAX_ERROR_CHARS
    assert extract_error_text("") == ""


@pytest.mark.parametrize(
    ("command", "error_text", "expected"),
    [
        (["python", "app.py"], "", "python"),
        (["pytest", "-x"], "", "python"),
        (["uv", "run", "pytest"], "", "python"),
        (["npm", "test"], "", "javascript"),
        (["node", "app.js"], "", "javascript"),
        (["make"], "", None),
        (["make"], "Traceback (most recent call last):\nKeyError", "python"),
        ([], "", None),
    ],
)
def test_guess_language(command: list[str], error_text: str, expected: str | None) -> None:
    assert guess_language(command, error_text) == expected


def test_git_context_outside_a_repository(tmp_path: Path) -> None:
    context = git_context(tmp_path)
    assert context.branch is None
    assert context.commit is None


def test_git_context_reads_branch_and_commit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    context = git_context(tmp_path)
    assert context.branch == "main"
    assert context.commit is not None
    assert re.fullmatch(r"[0-9a-f]{7,}", context.commit)


def test_failure_records_the_git_context(store: ErrorStore, tmp_path: Path) -> None:
    init_repo(tmp_path)
    result = run_and_capture(python("raise KeyError('name')"), store, cwd=tmp_path)
    assert result.recorded is not None
    occurrence = store.occurrences_for(result.recorded.error_id)[0]
    assert occurrence.git_branch == "main"
    assert occurrence.git_commit is not None
