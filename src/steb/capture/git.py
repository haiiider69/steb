"""Git context: which branch and commit were active when an error happened.

Every lookup fails quietly. Outside a git repository, without git installed, or in a repository
with no commit yet, the corresponding value is simply ``None``: missing context must never stop
steb from recording an error.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

_TIMEOUT_SECONDS = 5


@dataclass(frozen=True, slots=True)
class GitContext:
    """The git state of a working directory.

    Attributes:
        branch: The current branch name, or ``None`` (not a repository, or detached HEAD).
        commit: The short hash of the current commit, or ``None`` if there is none.
    """

    branch: str | None
    commit: str | None


def _git(args: list[str], cwd: Path | None) -> str | None:
    """Run one git command and return its trimmed output, or ``None`` on any failure."""
    try:
        completed = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def git_context(cwd: Path | None = None) -> GitContext:
    """Read the current git branch and commit of a directory.

    Args:
        cwd: The directory to inspect (defaults to the current directory).

    Returns:
        The branch and commit, with ``None`` for anything that could not be determined.
    """
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch == "HEAD":
        branch = None
    commit = _git(["rev-parse", "--short", "HEAD"], cwd)
    return GitContext(branch=branch, commit=commit)
