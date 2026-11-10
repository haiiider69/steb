"""Command logic behind the ``steb`` command line.

Each function takes an open ``ErrorStore`` plus output streams and returns an exit code. They
contain everything the commands do and none of the argument parsing, so they can be tested
without Typer; ``cli.py`` only parses arguments and calls them.

Conventions: results go to ``out``; messages from steb itself go to ``err`` and start with
``steb:``, so they never get mixed into the wrapped command's own output.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from steb.capture.runner import CommandNotFoundError, run_and_capture
from steb.ingest.fingerprint import parse_error
from steb.store.database import ErrorNotFoundError, ErrorStore, Fix, RecordResult, StoredError

EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_COMMAND_NOT_FOUND = 127

_SUMMARY_WIDTH = 70
_RECENT_OCCURRENCES = 5
_UNKNOWN_TYPE = "Unknown"


def _when(timestamp: str) -> str:
    """Show a stored UTC timestamp in a short, readable form."""
    return timestamp[:16].replace("T", " ") + " UTC"


def _summary(error: StoredError) -> str:
    """Describe a bug in one line, such as ``KeyError: 'name'``."""
    parsed = parse_error(error.normalized_text)
    if parsed.exc_type == _UNKNOWN_TYPE:
        text = parsed.message
    elif parsed.message:
        text = f"{parsed.exc_type}: {parsed.message}"
    else:
        text = parsed.exc_type
    flat = " ".join(text.split())
    if len(flat) <= _SUMMARY_WIDTH:
        return flat
    return flat[: _SUMMARY_WIDTH - 3] + "..."


def _describe_fix(fix: Fix) -> str:
    """Describe a fix in one line, with its commit when there is one."""
    if fix.git_commit:
        return f"{fix.note} (commit {fix.git_commit})"
    return fix.note


def _report_recorded(store: ErrorStore, recorded: RecordResult, err: TextIO) -> None:
    """Tell the user what was recorded, and show the known fix if the bug is a repeat."""
    stored = store.get_error(recorded.error_id)
    label = _summary(stored) if stored else ""
    ident = recorded.error_id
    if recorded.is_new:
        print(f"steb: new error recorded as #{ident} ({label}).", file=err)
        print(f'steb: once you fix it, run: steb fix {ident} --note "what you did"', file=err)
        return
    print(
        f"steb: seen this error before! #{ident} ({label}), now {recorded.occurrence_count} times.",
        file=err,
    )
    fixes = store.fixes_for(ident)
    if fixes:
        print(f"steb: last fix: {_describe_fix(fixes[0])}", file=err)
    else:
        print(f'steb: no fix recorded yet. Add one with: steb fix {ident} --note "..."', file=err)


def run_command(
    command: Sequence[str],
    store: ErrorStore,
    *,
    out: TextIO,
    err: TextIO,
    cwd: Path | None = None,
) -> int:
    """Run a command, record its failure, and report whether the error is a repeat.

    Args:
        command: The program and its arguments.
        store: The error store.
        out: Where the command's output is shown live.
        err: Where steb's own messages go.
        cwd: The directory to run in (defaults to the current directory).

    Returns:
        The wrapped command's exit code, or a steb exit code if it could not be started.
    """
    try:
        result = run_and_capture(command, store, cwd=cwd, echo=out)
    except CommandNotFoundError as exc:
        print(f"steb: {exc}", file=err)
        return EXIT_COMMAND_NOT_FOUND
    except ValueError as exc:
        print(f"steb: {exc}", file=err)
        return EXIT_USAGE
    if result.recorded is not None:
        _report_recorded(store, result.recorded, err)
    return result.exit_code


def add_fix(
    store: ErrorStore,
    error_id: int,
    note: str,
    commit: str | None,
    *,
    out: TextIO,
    err: TextIO,
) -> int:
    """Record a fix for a bug.

    Args:
        store: The error store.
        error_id: The bug the fix belongs to (as shown by ``steb list``).
        note: What was done to fix it.
        commit: The commit containing the fix, if any.
        out: Where the confirmation goes.
        err: Where error messages go.

    Returns:
        0 on success, a non-zero exit code otherwise.
    """
    if not note.strip():
        print("steb: the note must not be empty", file=err)
        return EXIT_USAGE
    try:
        store.add_fix(error_id, note=note.strip(), git_commit=commit)
    except ErrorNotFoundError as exc:
        print(f"steb: {exc}", file=err)
        return EXIT_FAILURE
    print(f"Fix recorded for error #{error_id}.", file=out)
    return 0


def show_recent(store: ErrorStore, limit: int, *, out: TextIO) -> int:
    """Print the most recently seen bugs as a table.

    Args:
        store: The error store.
        limit: The maximum number of bugs to show.
        out: Where the table goes.

    Returns:
        Always 0.
    """
    errors = store.list_errors(limit)
    if not errors:
        print("No errors recorded yet. Try: steb run -- <command>", file=out)
        return 0
    print(f"{'ID':>5}  {'COUNT':>5}  {'FIXED':>5}  {'LAST SEEN':<20}  ERROR", file=out)
    for error in errors:
        fixed = "yes" if store.fixes_for(error.id) else "no"
        print(
            f"{error.id:>5}  {error.occurrence_count:>5}  {fixed:>5}  "
            f"{_when(error.last_seen):<20}  {_summary(error)}",
            file=out,
        )
    return 0


def show_error(store: ErrorStore, error_id: int, *, out: TextIO, err: TextIO) -> int:
    """Print everything known about one bug.

    Args:
        store: The error store.
        error_id: The bug to show.
        out: Where the details go.
        err: Where error messages go.

    Returns:
        0 on success, a non-zero exit code if the bug does not exist.
    """
    error = store.get_error(error_id)
    if error is None:
        print(f"steb: no error with id {error_id}", file=err)
        return EXIT_FAILURE

    print(f"Error #{error.id}  {_summary(error)}", file=out)
    print(f"Fingerprint:  {error.fingerprint}", file=out)
    print(
        f"Seen:         {error.occurrence_count} times "
        f"(first {_when(error.first_seen)}, last {_when(error.last_seen)})",
        file=out,
    )

    fixes = store.fixes_for(error.id)
    print("\nFixes (newest first):" if fixes else "\nNo fix recorded yet.", file=out)
    for fix in fixes:
        print(f"  - [{_when(fix.created_at)}] {_describe_fix(fix)}", file=out)

    occurrences = store.occurrences_for(error.id)[-_RECENT_OCCURRENCES:]
    print(f"\nLatest occurrences (up to {_RECENT_OCCURRENCES}):", file=out)
    for occurrence in occurrences:
        where = ""
        if occurrence.git_branch or occurrence.git_commit:
            where = f"  {occurrence.git_branch or '?'} @ {occurrence.git_commit or '?'}"
        command = f"  $ {occurrence.command}" if occurrence.command else ""
        print(f"  - {_when(occurrence.occurred_at)}{where}{command}", file=out)

    print("\nNormalized error text:", file=out)
    for line in error.normalized_text.splitlines():
        print(f"  {line}", file=out)
    return 0
