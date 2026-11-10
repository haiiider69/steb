"""Tests for the command logic behind the steb CLI."""

import io
import sys
from collections.abc import Iterator

import pytest

from steb.commands import (
    EXIT_COMMAND_NOT_FOUND,
    EXIT_FAILURE,
    EXIT_USAGE,
    add_fix,
    run_command,
    show_error,
    show_recent,
)
from steb.store.database import ErrorStore

FAILING = [sys.executable, "-c", "raise KeyError('name')"]


@pytest.fixture
def store() -> Iterator[ErrorStore]:
    with ErrorStore(":memory:") as opened:
        yield opened


def run(store: ErrorStore, command: list[str]) -> tuple[int, str, str]:
    """Run a command through run_command and return its exit code, stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    code = run_command(command, store, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_successful_command_prints_its_output_and_records_nothing(store: ErrorStore) -> None:
    code, out, err = run(store, [sys.executable, "-c", "print('hello')"])
    assert code == 0
    assert "hello" in out
    assert err == ""
    assert store.list_errors() == []


def test_new_failure_is_reported_with_a_hint(store: ErrorStore) -> None:
    code, _, err = run(store, FAILING)
    assert code == 1
    assert "new error recorded as #1" in err
    assert "KeyError: 'name'" in err
    assert "steb fix 1 --note" in err


def test_repeat_failure_says_it_was_seen_before(store: ErrorStore) -> None:
    run(store, FAILING)
    _, _, err = run(store, FAILING)
    assert "seen this error before" in err
    assert "now 2 times" in err
    assert "no fix recorded yet" in err


def test_repeat_failure_shows_the_last_fix(store: ErrorStore) -> None:
    run(store, FAILING)
    add_fix(store, 1, "add a default value", "a1b2c3d", out=io.StringIO(), err=io.StringIO())
    _, _, err = run(store, FAILING)
    assert "last fix: add a default value (commit a1b2c3d)" in err


def test_exit_code_of_the_wrapped_command_is_returned(store: ErrorStore) -> None:
    code, _, _ = run(store, [sys.executable, "-c", "import sys; sys.exit(3)"])
    assert code == 3


def test_missing_program_gives_exit_code_127(store: ErrorStore) -> None:
    code, _, err = run(store, ["definitely-not-a-real-program-xyz"])
    assert code == EXIT_COMMAND_NOT_FOUND
    assert "command not found" in err


def test_empty_command_is_a_usage_error(store: ErrorStore) -> None:
    code, _, err = run(store, [])
    assert code == EXIT_USAGE
    assert "must not be empty" in err


def test_add_fix_confirms_and_stores_it(store: ErrorStore) -> None:
    run(store, FAILING)
    out, err = io.StringIO(), io.StringIO()
    code = add_fix(store, 1, "  pin urllib3  ", "a1b2c3d", out=out, err=err)
    assert code == 0
    assert "Fix recorded for error #1" in out.getvalue()
    fix = store.fixes_for(1)[0]
    assert fix.note == "pin urllib3"
    assert fix.git_commit == "a1b2c3d"


def test_add_fix_for_unknown_error_fails(store: ErrorStore) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = add_fix(store, 42, "nothing", None, out=out, err=err)
    assert code == EXIT_FAILURE
    assert "no error with id 42" in err.getvalue()


def test_add_fix_with_blank_note_is_a_usage_error(store: ErrorStore) -> None:
    run(store, FAILING)
    out, err = io.StringIO(), io.StringIO()
    assert add_fix(store, 1, "   ", None, out=out, err=err) == EXIT_USAGE
    assert store.fixes_for(1) == []


def test_list_when_empty_suggests_how_to_start(store: ErrorStore) -> None:
    out = io.StringIO()
    assert show_recent(store, 20, out=out) == 0
    assert "steb run" in out.getvalue()


def test_list_shows_count_fixed_flag_and_summary(store: ErrorStore) -> None:
    run(store, FAILING)
    run(store, FAILING)
    run(store, [sys.executable, "-c", "raise ValueError('bad input')"])
    add_fix(store, 1, "fixed", None, out=io.StringIO(), err=io.StringIO())
    out = io.StringIO()
    show_recent(store, 20, out=out)
    lines = out.getvalue().splitlines()
    assert lines[0].split() == ["ID", "COUNT", "FIXED", "LAST", "SEEN", "ERROR"]
    by_id = {line.split()[0]: line for line in lines[1:]}
    assert "KeyError: 'name'" in by_id["1"]
    assert by_id["1"].split()[1:3] == ["2", "yes"]
    assert "ValueError: bad input" in by_id["2"]
    assert by_id["2"].split()[1:3] == ["1", "no"]


def test_list_respects_the_limit(store: ErrorStore) -> None:
    run(store, FAILING)
    run(store, [sys.executable, "-c", "raise ValueError('bad input')"])
    out = io.StringIO()
    show_recent(store, 1, out=out)
    assert len(out.getvalue().splitlines()) == 2


def test_show_prints_everything_known_about_a_bug(store: ErrorStore) -> None:
    run(store, FAILING)
    add_fix(store, 1, "add a default value", "a1b2c3d", out=io.StringIO(), err=io.StringIO())
    out, err = io.StringIO(), io.StringIO()
    assert show_error(store, 1, out=out, err=err) == 0
    text = out.getvalue()
    assert "Error #1  KeyError: 'name'" in text
    assert "Fingerprint:" in text
    assert "Seen:         1 times" in text
    assert "add a default value (commit a1b2c3d)" in text
    assert "Latest occurrences" in text
    assert "Normalized error text:" in text
    assert "Traceback (most recent call last):" in text


def test_show_without_a_fix_says_so(store: ErrorStore) -> None:
    run(store, FAILING)
    out = io.StringIO()
    show_error(store, 1, out=out, err=io.StringIO())
    assert "No fix recorded yet." in out.getvalue()


def test_show_unknown_error_fails(store: ErrorStore) -> None:
    out, err = io.StringIO(), io.StringIO()
    assert show_error(store, 7, out=out, err=err) == EXIT_FAILURE
    assert "no error with id 7" in err.getvalue()
