"""Fingerprinting: give every bug a short, stable identifier.

A fingerprint is computed from a *normalized* error text (see ``normalize()``). It combines:

    * the exception type (``KeyError``),
    * the message template (volatile numbers and data strings replaced by placeholders),
    * the stack frames that identify where the bug lives: the last few *user* frames and the
      innermost library frame.

Two occurrences of the same bug get the same fingerprint even on different machines, while
different bugs get different ones. Fingerprints are used for exact matching only; fuzzy
matching is the job of the retrieval layer. For that reason the rules favor precision: when in
doubt, two errors stay separate rather than being merged.

Parsing understands Python tracebacks. Other languages fall back to the exception type and
message only, which is a known limit.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

# Bump when the algorithm changes, so old and new fingerprints are never compared by accident.
FINGERPRINT_VERSION = 1

_MAX_USER_FRAMES = 3
_UNKNOWN_TYPE = "Unknown"
_EXCEPTION_SUFFIXES = ("Error", "Exception", "Warning", "Exit", "Interrupt", "Fault")

_CHAIN_MARKER = re.compile(
    r"^(?:During handling of the above exception, another exception occurred:"
    r"|The above exception was the direct cause of the following exception:)\s*$",
    re.MULTILINE,
)
_FRAME_LINE = re.compile(
    r'^\s*File "(?P<path>[^"]+)", line (?:\d+|<N>), in (?P<function>.+?)\s*$'
)
_EXCEPTION_LINE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*)(?P<colon>:(?:\s+(?P<message>.*))?)?$")

# A quoted token that looks like an identifier (a module, a key, a name) is kept in the template
# because it usually distinguishes bugs. Anything else inside quotes is treated as data.
_QUOTED = re.compile(r"(?<!\w)(?P<quote>['\"])(?P<inner>.*?)(?P=quote)(?!\w)")
_IDENTIFIER_LIKE = re.compile(r"[\w.-]{1,64}")
# Standalone numbers only: version numbers (2.28.1), words with digits (utf8) and the number
# after "Errno" (which identifies the error) are left alone.
_NUMBER = re.compile(r"(?<![\w.<])(?<!Errno )\d+(?![\w>]|\.\d)")


@dataclass(frozen=True, slots=True)
class Frame:
    """One line of a stack trace.

    Attributes:
        kind: ``user`` for the project's own code, ``library`` for installed packages,
            ``stdlib`` for the language's standard library.
        file: The normalized file, such as ``app.py`` or ``<SITE>/requests/api.py``.
        function: The function name, such as ``main`` or ``<module>``.
    """

    kind: Literal["user", "library", "stdlib"]
    file: str
    function: str

    @property
    def key(self) -> str:
        """A short string identifying this frame, without any line number."""
        return f"{self.file}:{self.function}"


@dataclass(frozen=True, slots=True)
class ParsedError:
    """The parts of an error text that matter for identification.

    Attributes:
        exc_type: The exception class name, or ``Unknown`` if none was found.
        message: The exception message (first line only).
        frames: The stack frames, oldest first (innermost call last).
    """

    exc_type: str
    message: str
    frames: tuple[Frame, ...]


def _frame_from_path(path: str, function: str) -> Frame:
    """Build a ``Frame`` from a normalized path and a function name."""
    if path.startswith("<SITE>/"):
        return Frame("library", path, function)
    if path.startswith("<STDLIB>/"):
        return Frame("stdlib", path, function)
    return Frame("user", path.removeprefix("<PATH>/"), function)


def _parse_exception_line(lines: list[str]) -> tuple[str, str] | None:
    """Find the final ``Type: message`` line, scanning from the bottom."""
    for line in reversed(lines):
        if not line or line[0].isspace():
            continue
        match = _EXCEPTION_LINE.match(line)
        if not match:
            continue
        exc_type = match.group("type")
        if not exc_type.rsplit(".", 1)[-1][:1].isupper():
            continue
        if match.group("colon") is None and not exc_type.endswith(_EXCEPTION_SUFFIXES):
            continue
        return exc_type, (match.group("message") or "").strip()
    return None


def parse_error(text: str) -> ParsedError:
    """Extract the exception type, message and frames from a normalized error text.

    For chained exceptions only the last one (the one that finally escaped) is used.

    Args:
        text: Normalized error text.

    Returns:
        The parsed error. If nothing looks like an exception, the type is ``Unknown`` and the
        message is the first non-empty line.
    """
    last_block = _CHAIN_MARKER.split(text)[-1]
    lines = last_block.splitlines()

    frames = []
    for line in lines:
        frame_match = _FRAME_LINE.match(line)
        if frame_match:
            frames.append(_frame_from_path(frame_match["path"], frame_match["function"]))

    found = _parse_exception_line(lines)
    if found is None:
        first_line = next((line.strip() for line in lines if line.strip()), "")
        return ParsedError(_UNKNOWN_TYPE, first_line, tuple(frames))

    exc_type, message = found
    return ParsedError(exc_type, message, tuple(frames))


def _template_quoted(match: re.Match[str]) -> str:
    """Keep identifier-like quoted tokens, replace any other quoted data."""
    inner = match.group("inner")
    if _IDENTIFIER_LIKE.fullmatch(inner) and not inner.isdigit():
        return match.group(0)
    quote = match.group("quote")
    return f"{quote}<STR>{quote}"


def message_template(message: str) -> str:
    """Turn an exception message into a template by replacing volatile data.

    Args:
        message: The message of an exception.

    Returns:
        The message with data strings replaced by ``<STR>``, standalone numbers replaced by
        ``<N>`` and whitespace collapsed.
    """
    message = _QUOTED.sub(_template_quoted, message)
    message = _NUMBER.sub("<N>", message)
    return " ".join(message.split())


def _identifying_frames(frames: tuple[Frame, ...]) -> list[Frame]:
    """Pick the frames that identify a bug.

    The last few user frames locate the bug in the project. The innermost frame is added when
    it belongs to a library, because the place where a library fails is part of the bug. Other
    library frames are left out on purpose: library internals change between versions.
    """
    user_frames = [frame for frame in frames if frame.kind == "user"]
    if not user_frames:
        return list(frames[-_MAX_USER_FRAMES:])
    selected = user_frames[-_MAX_USER_FRAMES:]
    if frames[-1].kind != "user":
        selected.append(frames[-1])
    return selected


def fingerprint(text: str) -> str:
    """Compute the fingerprint of a normalized error text.

    Args:
        text: Error text that already went through ``redact()`` and ``normalize()``.

    Returns:
        A 16-character hexadecimal identifier, stable for the same bug.
    """
    error = parse_error(text)
    parts = [
        f"v{FINGERPRINT_VERSION}",
        error.exc_type,
        message_template(error.message),
        *(frame.key for frame in _identifying_frames(error.frames)),
    ]
    material = "\x1f".join(parts)#invisible “unit separator” character
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
#keeps 64 bits of SHA-256. That’s plenty for a personal error database
