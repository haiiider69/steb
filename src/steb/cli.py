"""Command-line interface (Typer) for steb.

This is the ``steb`` entry point. It only parses arguments, opens the error store at the
configured location, and calls the functions in ``steb.commands``, which hold the behaviour.

Commands: ``run`` (run a command and record its failure), ``fix`` (record how a bug was fixed),
``list`` (recent bugs) and ``show`` (one bug in detail). ``ask`` and ``ingest`` arrive in later
phases.
"""

import sys
from typing import Annotated

import typer

from steb.commands import add_fix, run_command, show_error, show_recent
from steb.config import get_settings
from steb.store.database import ErrorStore

app = typer.Typer(
    name="steb",
    help="steb (seen this error before): a personal memory of your errors and their fixes.",
    no_args_is_help=True,
    add_completion=False,
)

_ID_HELP = "Id of the error, as shown by 'steb list'."


def _open_store() -> ErrorStore:
    """Open the error database at the configured location."""
    return ErrorStore(get_settings().db_path)


@app.command(context_settings={"allow_interspersed_args": False, "ignore_unknown_options": True})
def run(
    command: Annotated[
        list[str],
        typer.Argument(help="The command to run, for example: steb run -- pytest -x"),
    ],
) -> None:
    """Run a command; if it fails, record the error and say if you have seen it before."""
    with _open_store() as store:
        code = run_command(command, store, out=sys.stdout, err=sys.stderr)
    raise typer.Exit(code)


@app.command()
def fix(
    error_id: Annotated[int, typer.Argument(help=_ID_HELP)],
    note: Annotated[str, typer.Option("--note", "-n", help="What fixed it.")],
    commit: Annotated[
        str | None,
        typer.Option("--commit", "-c", help="The commit that contains the fix."),
    ] = None,
) -> None:
    """Record how you fixed an error."""
    with _open_store() as store:
        code = add_fix(store, error_id, note, commit, out=sys.stdout, err=sys.stderr)
    raise typer.Exit(code)


@app.command("list")
def list_errors(
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, help="Maximum number of errors to show."),
    ] = 20,
) -> None:
    """List the most recently seen errors."""
    with _open_store() as store:
        code = show_recent(store, limit, out=sys.stdout)
    raise typer.Exit(code)


@app.command()
def show(error_id: Annotated[int, typer.Argument(help=_ID_HELP)]) -> None:
    """Show everything known about one error: fixes, occurrences and normalized text."""
    with _open_store() as store:
        code = show_error(store, error_id, out=sys.stdout, err=sys.stderr)
    raise typer.Exit(code)
