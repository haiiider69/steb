"""Tests for the steb command line: argument parsing and wiring."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from steb.cli import app
from steb.config import get_settings

runner = CliRunner()

FAILING = [sys.executable, "-c", "raise KeyError('name')"]


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Each test gets its own empty database folder; the settings cache must be reset around it.
    monkeypatch.setenv("STEB_HOME", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_help_lists_the_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("run", "fix", "list", "show"):
        assert name in result.output


def test_no_arguments_shows_the_usage() -> None:
    result = runner.invoke(app, [])
    assert "Usage:" in result.output


def test_run_records_a_failure_and_list_shows_it() -> None:
    result = runner.invoke(app, ["run", "--", *FAILING])
    assert result.exit_code == 1
    assert "new error recorded as #1" in result.output
    listing = runner.invoke(app, ["list"])
    assert listing.exit_code == 0
    assert "KeyError: 'name'" in listing.output


def test_run_works_without_the_double_dash() -> None:
    result = runner.invoke(app, ["run", *FAILING])
    assert result.exit_code == 1
    assert "new error recorded" in result.output


def test_run_passes_the_exit_code_through() -> None:
    result = runner.invoke(app, ["run", "--", sys.executable, "-c", "import sys; sys.exit(3)"])
    assert result.exit_code == 3


def test_run_shows_the_output_of_a_successful_command() -> None:
    result = runner.invoke(app, ["run", "--", sys.executable, "-c", "print('hello')"])
    assert result.exit_code == 0
    assert "hello" in result.output


def test_run_without_a_command_is_a_usage_error() -> None:
    assert runner.invoke(app, ["run"]).exit_code == 2


def test_run_with_an_unknown_program_gives_127() -> None:
    result = runner.invoke(app, ["run", "--", "definitely-not-a-real-program-xyz"])
    assert result.exit_code == 127
    assert "command not found" in result.output


def test_the_whole_workflow_run_fix_run_show() -> None:
    runner.invoke(app, ["run", "--", *FAILING])
    again = runner.invoke(app, ["run", "--", *FAILING])
    assert "seen this error before" in again.output

    fixed = runner.invoke(app, ["fix", "1", "--note", "add a default", "--commit", "abc123"])
    assert fixed.exit_code == 0

    third = runner.invoke(app, ["run", "--", *FAILING])
    assert "last fix: add a default (commit abc123)" in third.output

    detail = runner.invoke(app, ["show", "1"])
    assert detail.exit_code == 0
    assert "Fixes (newest first):" in detail.output


def test_fix_requires_a_note() -> None:
    assert runner.invoke(app, ["fix", "1"]).exit_code == 2


def test_fix_for_an_unknown_error_fails() -> None:
    result = runner.invoke(app, ["fix", "99", "--note", "whatever"])
    assert result.exit_code == 1
    assert "no error with id 99" in result.output


def test_show_for_an_unknown_error_fails() -> None:
    assert runner.invoke(app, ["show", "99"]).exit_code == 1


def test_list_rejects_a_limit_below_one() -> None:
    assert runner.invoke(app, ["list", "--limit", "0"]).exit_code == 2


def test_list_on_an_empty_database() -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No errors recorded yet" in result.output
