"""Secret redaction: remove credentials and personal data from error text.

Everything steb stores, embeds or sends to an LLM must pass through ``redact()`` first.
Rules run from most specific to most generic. Each match is replaced by a labelled
placeholder such as ``[REDACTED:API_KEY]``. The function is idempotent: redacting text that
is already redacted changes nothing.

Redaction is pattern based, so it is best effort: a secret with no recognizable shape and no
revealing variable name can slip through.
"""

import re
from collections.abc import Callable

_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)

_JWT = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

_API_KEY = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{16,}"  # Anthropic and OpenAI
    r"|gh[pousr]_[A-Za-z0-9]{20,}"  # GitHub tokens
    r"|github_pat_[A-Za-z0-9_]{20,}"  # GitHub fine-grained tokens
    r"|(?:AKIA|ASIA)[0-9A-Z]{16}"  # AWS access key id
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"  # Slack
    r"|AIza[0-9A-Za-z_-]{35}"  # Google
    r")"
)

_URL_PASSWORD = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<user>[^\s:/@]+):(?P<pw>[^\s@/]+)@"
)

_BEARER = re.compile(r"\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)

_SENSITIVE_WORDS = r"(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)"
_ASSIGNMENT = re.compile(
    r"\b(?P<key>[\w.-]*" + _SENSITIVE_WORDS + r"[\w.-]*)"
    r"(?P<kq>[\"']?)"
    r"(?P<sep>\s*[:=]\s*)"
    r"(?P<quote>[\"']?)"
    r"(?!\[REDACTED)"
    r"(?P<value>[^\s\"',;&]+)"
    r"(?P=quote)",
    re.IGNORECASE,
)

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_HOME_DIR = re.compile(
    r"(?<!\w)((?:[A-Z]:)?[\\/](?:Users|home)[\\/])[^\\/\s]+",
    re.IGNORECASE,
)


def _redact_assignment(match: re.Match[str]) -> str:
    """Keep the variable name and separator, replace only the value."""
    quote = match.group("quote")
    return (
        f"{match.group('key')}{match.group('kq')}{match.group('sep')}"
        f"{quote}[REDACTED:SECRET]{quote}"
    )


# (pattern, replacement) pairs, applied in order: specific rules before generic ones.
_RULES: list[tuple[re.Pattern[str], str | Callable[[re.Match[str]], str]]] = [
    (_PRIVATE_KEY, "[REDACTED:PRIVATE_KEY]"),
    (_JWT, "[REDACTED:JWT]"),
    (_API_KEY, "[REDACTED:API_KEY]"),
    (_URL_PASSWORD, r"\g<scheme>\g<user>:[REDACTED:PASSWORD]@"),
    (_BEARER, r"\1 [REDACTED:TOKEN]"),
    (_ASSIGNMENT, _redact_assignment),
    (_EMAIL, "[REDACTED:EMAIL]"),
    (_HOME_DIR, r"\1[REDACTED:USER]"),
]


def redact(text: str) -> str:
    """Remove secrets and personal data from text.

    Args:
        text: Raw text, such as a stack trace or a command's stderr.

    Returns:
        The text with each secret replaced by a labelled placeholder.
    """
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text