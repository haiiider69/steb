"""Normalization: make the same bug look the same everywhere.

The same error shows up with different absolute paths, line numbers, memory addresses, temp
file names, UUIDs and timestamps. ``normalize()`` replaces each of these volatile parts by a
stable placeholder such as ``<N>`` or ``<ADDR>``, so two occurrences of one bug produce the same
text. The result is used for fingerprinting and for retrieval, never shown as the original.

Run ``redact()`` first: this module expects secrets to be gone already and understands the
``[REDACTED:...]`` placeholders that ``redact()`` leaves in paths.

Design choices:
    * Library frames keep their package path (``<SITE>/requests/api.py``) because the library
      is part of what identifies a bug; other paths keep only the file name.
    * Short hex numbers such as Windows error codes (``0x80070005``) are kept: they are
      meaningful. Only long ones (10+ digits), which are memory addresses, are replaced.
    * The function is idempotent: ``normalize(normalize(x)) == normalize(x)``.
"""

import re

# A path segment character: anything except whitespace, quotes, brackets used as delimiters and
# colons, OR a whole ``[REDACTED:...]`` placeholder (which contains a colon).
_REDACTED = r"\[REDACTED:[A-Z_]+\]"
_SEG_CHAR = r"(?:" + _REDACTED + r"|[^\s\"'<>|*?:])"
_UNIX_SEG_CHAR = r"(?:" + _REDACTED + r"|[\w.@+~-])"

_WINDOWS_PATH = re.compile(r"(?<![\w])[A-Za-z]:[\\/]" + _SEG_CHAR + r"*")
_UNIX_PATH = re.compile(
    r"(?<![\w:/<>])/(?:" + _UNIX_SEG_CHAR + r"+/)+" + _UNIX_SEG_CHAR + r"+"
)

_SITE_PACKAGES = re.compile(r"(?:site|dist)-packages/(.+)$")
_UNIX_STDLIB = re.compile(r"/lib/python\d+(?:\.\d+)?/(.+)$", re.IGNORECASE)
_WINDOWS_STDLIB = re.compile(r"/Lib/(.+)$")

_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{10,}\b")
_TMP_NAME = re.compile(r"\btmp[a-z0-9_]{8}\b")

_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b")

_SOURCE_POSITION = re.compile(
    r"(?P<file>[\w<>-]+\.(?:pyi?|jsx?|tsx?|java|kt|go|rs|c|cc|cpp|h|hpp|cs|rb|php|sh|ipynb))"
    r":\d+(?::\d+)?"
)
_LINE_NUMBER = re.compile(r"\b(line|lines)\s+\d+", re.IGNORECASE)

_TRAILING_PUNCTUATION = ".,;)"


def _simplify_path(match: re.Match[str]) -> str:
    """Replace one absolute path by a stable, shorter form."""
    raw = match.group(0)
    stripped = raw.rstrip(_TRAILING_PUNCTUATION)
    tail = raw[len(stripped) :]
    path = stripped.replace("\\", "/")

    for pattern, prefix in (
        (_SITE_PACKAGES, "<SITE>/"),
        (_UNIX_STDLIB, "<STDLIB>/"),
        (_WINDOWS_STDLIB, "<STDLIB>/"),
    ):
        found = pattern.search(path)
        if found:
            return prefix + found.group(1) + tail

    return "<PATH>/" + path.rsplit("/", 1)[-1] + tail


def normalize(text: str) -> str:
    """Replace the volatile parts of an error text by stable placeholders.

    Args:
        text: Error text, already passed through ``redact()``.

    Returns:
        The normalized text, with consistent line endings and no volatile details.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = _WINDOWS_PATH.sub(_simplify_path, text)
    text = _UNIX_PATH.sub(_simplify_path, text)

    text = _UUID.sub("<UUID>", text)
    text = _ADDRESS.sub("<ADDR>", text)
    text = _TMP_NAME.sub("<TMPNAME>", text)

    text = _TIMESTAMP.sub("<TIMESTAMP>", text)
    text = _DATE.sub("<DATE>", text)
    text = _TIME.sub("<TIME>", text)

    text = _SOURCE_POSITION.sub(r"\g<file>:<N>", text)
    text = _LINE_NUMBER.sub(r"\1 <N>", text)

    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
