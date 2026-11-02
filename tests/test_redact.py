"""Tests for secret redaction."""

import pytest

from steb.ingest.redact import redact

# Fake secrets are assembled at runtime so secret scanners (such as GitHub push protection)
# don't mistake this file for a real leak.
FAKE_ANTHROPIC = "sk-" + "ant-" + "a1b2c3d4e5f6g7h8i9j0"
FAKE_GITHUB = "gh" + "p_" + "A" * 36
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
FAKE_JWT = "eyJ" + "hbGciOiJIUzI1NiJ9.eyJ" + "zdWIiOiIxMjM0In0.abc123def456"
FAKE_PEM = (
    "-----BEGIN RSA " + "PRIVATE KEY-----\n"
    "MIIEabc123\n"
    "-----END RSA " + "PRIVATE KEY-----"
)


@pytest.mark.parametrize("secret", [FAKE_ANTHROPIC, FAKE_GITHUB, FAKE_AWS, FAKE_JWT])
def test_known_secret_formats_are_removed(secret: str) -> None:
    result = redact(f"Error calling the API with {secret} failed")
    assert secret not in result
    assert "[REDACTED:" in result


def test_private_key_block_is_removed() -> None:
    result = redact(f"loading key:\n{FAKE_PEM}\ndone")
    assert "MIIEabc123" not in result
    assert "[REDACTED:PRIVATE_KEY]" in result
    assert "loading key:" in result
    assert "done" in result


def test_password_in_url_is_removed() -> None:
    result = redact("could not connect to postgresql://admin:hunter2@db.example.com:5432/app")
    assert "hunter2" not in result
    assert "admin" in result
    assert "db.example.com" in result


@pytest.mark.parametrize(
    ("text", "secret", "kept"),
    [
        ("DB_PASSWORD=hunter2", "hunter2", "DB_PASSWORD"),
        ('api_key: "abc123xyz"', "abc123xyz", "api_key"),
        ('{"password": "hunter2"}', "hunter2", '"password"'),
        ("token = 'abcdef123456'", "abcdef123456", "token"),
    ],
)
def test_assignments_keep_the_name_but_hide_the_value(text: str, secret: str, kept: str) -> None:
    result = redact(text)
    assert secret not in result
    assert kept in result


def test_specific_label_is_kept_for_known_formats() -> None:
    result = redact("api_key=" + FAKE_ANTHROPIC)
    assert FAKE_ANTHROPIC not in result
    assert "[REDACTED:API_KEY]" in result


def test_bearer_token_is_removed() -> None:
    result = redact("Authorization: Bearer abcdefghijklmnop12345")
    assert "abcdefghijklmnop12345" not in result
    assert "Bearer" in result


def test_email_is_removed() -> None:
    result = redact("contact alice@example.com for access")
    assert "alice@example.com" not in result
    assert "[REDACTED:EMAIL]" in result


@pytest.mark.parametrize(
    ("text", "username"),
    [
        (r'File "C:\Users\ASUS\Desktop\app.py", line 3', "ASUS"),
        ('File "/home/alice/app.py", line 3', "alice"),
        ('File "/Users/bob/app.py", line 3', "bob"),
    ],
)
def test_home_directory_username_is_removed(text: str, username: str) -> None:
    result = redact(text)
    assert username not in result
    assert "app.py" in result


@pytest.mark.parametrize(
    "text",
    [
        "ValueError: invalid literal for int() with base 10: 'abc'",
        "KeyError: 'name'",
        "TypeError: unsupported operand type(s) for +: int and str",
    ],
)
def test_ordinary_error_text_is_unchanged(text: str) -> None:
    assert redact(text) == text


def test_redaction_is_idempotent() -> None:
    sample = "\n".join(
        [
            f"key {FAKE_GITHUB}",
            "DB_PASSWORD=hunter2",
            "postgresql://admin:hunter2@db.example.com/app",
            "Authorization: Bearer abcdefghijklmnop12345",
            "mail alice@example.com",
            r'File "C:\Users\ASUS\app.py"',
        ]
    )
    once = redact(sample)
    assert redact(once) == once