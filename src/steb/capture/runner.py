"""Capture: run a command, show its output live, and record its failure.

``run_and_capture()`` is what ``steb run -- <command>`` uses. The command's stdout and stderr
are merged into one stream (many tools, pytest included, print their errors on stdout), shown to
the user as they arrive, and kept in memory. If the command fails, the relevant part of the
output is recorded in the ``ErrorStore`` together with the command, git branch and commit, and
the guessed language. The command's own exit code is always passed back unchanged.

Known limits: output is piped, so tools that detect a terminal may drop colors; and only the
last error of a run is recorded.
"""

import codecs
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from steb.capture.git import git_context
from steb.store.database import ErrorStore, RecordResult

MAX_ERROR_CHARS = 20_000
TAIL_LINES = 40

_CHUNK_SIZE = 4096
_INTERRUPT_GRACE_SECONDS = 5
_TRACEBACK_START = "Traceback (most recent call last):"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_PYTEST_ERROR_LINE = re.compile(r"^E\s{2,}(?P<body>.*)$")

_LANGUAGE_BY_PROGRAM = {
    "python": "python",
    "python3": "python",
    "py": "python",
    "pytest": "python",
    "pip": "python",
    "node": "javascript",
    "npm": "javascript",
    "npx": "javascript",
    "yarn": "javascript",
    "pnpm": "javascript",
    "tsc": "typescript",
    "java": "java",
    "javac": "java",
    "mvn": "java",
    "gradle": "java",
    "cargo": "rust",
    "rustc": "rust",
    "go": "go",
    "dotnet": "csharp",
}


class CommandNotFoundError(LookupError):
    """Raised when the program to run cannot be found on the PATH."""


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """The outcome of running a command.

    Attributes:
        exit_code: The command's exit code, unchanged.
        output: Everything the command printed (stdout and stderr merged).
        recorded: What the store did with the failure, or ``None`` if nothing was recorded
            (the command succeeded, was interrupted, or printed nothing).
    """

    exit_code: int
    output: str
    recorded: RecordResult | None


def _pytest_error_block(lines: list[str]) -> str | None:
    """Return the last block of pytest ``E   ...`` lines, without their prefix."""
    current: list[str] = []
    previous: list[str] = []
    for line in lines:
        match = _PYTEST_ERROR_LINE.match(line)
        if match:
            current.append(match["body"].rstrip())
        elif current:
            previous, current = current, []
    block = current or previous
    return "\n".join(block) if block else None


def extract_error_text(output: str) -> str:
    """Pick the part of a command's output that describes the failure."""
    clean = _ANSI_ESCAPE.sub("", output)
    index = clean.rfind(_TRACEBACK_START)
    if index != -1:
        text = clean[index:]
    else:
        lines = clean.splitlines()
        text = _pytest_error_block(lines) or "\n".join(lines[-TAIL_LINES:])
    return text.strip()[-MAX_ERROR_CHARS:]


def guess_language(command: Sequence[str], error_text: str) -> str | None:
    """Guess the programming language of a failed command."""
    if _TRACEBACK_START in error_text:
        return "python"
    words = list(command)
    if len(words) > 2 and Path(words[0]).stem.lower() == "uv" and words[1] == "run":
        words = words[2:]
    if not words:
        return None
    return _LANGUAGE_BY_PROGRAM.get(Path(words[0]).stem.lower())


def _echo(stream: TextIO, text: str) -> None:
    """Write text to the user's terminal, surviving characters it cannot display."""
    try:
        stream.write(text)
    except UnicodeEncodeError:
        stream.write(text.encode("ascii", "replace").decode("ascii"))
    stream.flush()


def _stream_output(process: subprocess.Popen[bytes], echo: TextIO | None) -> tuple[str, bool]:
    """Read a running process's output until it ends, echoing it as it arrives.

    Returns:
        The decoded output and whether the user interrupted the run with Ctrl+C.
    """
    if process.stdout is None:
        message = "process was started without a stdout pipe"
        raise RuntimeError(message)
    descriptor = process.stdout.fileno()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    parts: list[str] = []
    interrupted = False
    try:
        while chunk := os.read(descriptor, _CHUNK_SIZE):
            text = decoder.decode(chunk)
            parts.append(text)
            if echo is not None:
                _echo(echo, text)
        parts.append(decoder.decode(b"", final=True))
        process.wait()
    except KeyboardInterrupt:
        interrupted = True
        try:
            process.wait(timeout=_INTERRUPT_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return "".join(parts), interrupted


def run_and_capture(
    command: Sequence[str],
    store: ErrorStore,
    *,
    cwd: Path | None = None,
    echo: TextIO | None = None,
) -> CaptureResult:
    """Run a command and record its failure, if any.

    Args:
        command: The program and its arguments, for example ``["pytest", "-x"]``.
        store: Where to record a failure.
        cwd: The directory to run in (defaults to the current directory).
        echo: Where to show the output live (for example ``sys.stdout``); ``None`` stays silent.

    Returns:
        The exit code, the full output, and what was recorded.

    Raises:
        ValueError: If ``command`` is empty.
        CommandNotFoundError: If the program cannot be found. Nothing is recorded: a mistyped
            command is not a bug in the user's code.
    """
    if not command:
        message = "command must not be empty"
        raise ValueError(message)
    executable = shutil.which(command[0])
    if executable is None:
        message = f"command not found: {command[0]}"
        raise CommandNotFoundError(message)

    # Unbuffered, UTF-8 output makes Python children stream live and decode reliably.
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    with subprocess.Popen(
        [executable, *command[1:]],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=environment,
    ) as process:
        output, interrupted = _stream_output(process, echo)
    exit_code = process.returncode

    recorded = None
    if exit_code != 0 and not interrupted:
        error_text = extract_error_text(output)
        if error_text:
            context = git_context(cwd)
            recorded = store.record_error(
                error_text,
                command=subprocess.list2cmdline(list(command)),
                git_branch=context.branch,
                git_commit=context.commit,
                language=guess_language(command, error_text),
            )
    return CaptureResult(exit_code=exit_code, output=output, recorded=recorded)
