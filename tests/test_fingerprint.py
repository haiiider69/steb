"""Tests for error fingerprinting."""

import pytest

from steb.ingest.fingerprint import Frame, fingerprint, message_template, parse_error
from steb.ingest.normalize import normalize

WINDOWS_TRACEBACK = r"""Traceback (most recent call last):
  File "C:\Users\ASUS\Desktop\proj\app.py", line 12, in <module>
    main()
  File "C:\Users\ASUS\Desktop\proj\app.py", line 8, in main
    data = load("users.json")
  File "C:\Users\ASUS\Desktop\proj\loader.py", line 21, in load
    return config["name"]
KeyError: 'name'
"""

LINUX_TRACEBACK = """Traceback (most recent call last):
  File "/home/alice/code/proj/app.py", line 99, in <module>
    main()
  File "/home/alice/code/proj/app.py", line 70, in main
    data = load("users.json")
  File "/home/alice/code/proj/loader.py", line 44, in load
    return config["name"]
KeyError: 'name'
"""


def fp(text: str) -> str:
    """Fingerprint a raw text the way the pipeline will: normalize first."""
    return fingerprint(normalize(text))


def test_parse_python_traceback() -> None:
    error = parse_error(normalize(WINDOWS_TRACEBACK))
    assert error.exc_type == "KeyError"
    assert error.message == "'name'"
    assert error.frames == (
        Frame("user", "app.py", "<module>"),
        Frame("user", "app.py", "main"),
        Frame("user", "loader.py", "load"),
    )


def test_frame_kinds_are_detected() -> None:
    text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "<PATH>/app.py", line <N>, in main',
            '  File "<SITE>/requests/api.py", line <N>, in get',
            '  File "<STDLIB>/json/decoder.py", line <N>, in decode',
            "JSONDecodeError: Expecting value",
        ]
    )
    kinds = [frame.kind for frame in parse_error(text).frames]
    assert kinds == ["user", "library", "stdlib"]


def test_chained_exceptions_use_the_last_one() -> None:
    text = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "<PATH>/a.py", line <N>, in first',
            "KeyError: 'x'",
            "",
            "During handling of the above exception, another exception occurred:",
            "",
            "Traceback (most recent call last):",
            '  File "<PATH>/b.py", line <N>, in second',
            "RuntimeError: wrapped",
        ]
    )
    error = parse_error(text)
    assert error.exc_type == "RuntimeError"
    assert error.frames == (Frame("user", "b.py", "second"),)


def test_exception_without_a_message() -> None:
    error = parse_error("Traceback (most recent call last):\nKeyboardInterrupt")
    assert error.exc_type == "KeyboardInterrupt"
    assert error.message == ""


def test_unparseable_text_falls_back_to_unknown() -> None:
    error = parse_error("something went wrong\nsecond line")
    assert error.exc_type == "Unknown"
    assert error.message == "something went wrong"
    assert error.frames == ()


def test_non_python_error_still_gets_type_and_message() -> None:
    text = "TypeError: Cannot read properties of undefined\n    at foo (<PATH>/app.js:<N>)"
    error = parse_error(text)
    assert error.exc_type == "TypeError"
    assert error.message == "Cannot read properties of undefined"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("'name'", "'name'"),
        ("No module named 'requests'", "No module named 'requests'"),
        (
            "invalid literal for int() with base 10: 'a b'",
            "invalid literal for int() with base <N>: '<STR>'",
        ),
        ("list index 5 out of range", "list index <N> out of range"),
        ("[Errno 2] No such file: '<PATH>/input.csv'", "[Errno 2] No such file: '<STR>'"),
        ("needs requests 2.28.1 or newer", "needs requests 2.28.1 or newer"),
        ("can't open file, don't retry", "can't open file, don't retry"),
        ("value   with    spaces", "value with spaces"),
    ],
)
def test_message_template(message: str, expected: str) -> None:
    assert message_template(message) == expected


def test_same_bug_on_two_machines_has_the_same_fingerprint() -> None:
    assert fp(WINDOWS_TRACEBACK) == fp(LINUX_TRACEBACK)
    #must give same fingerprints on windows and linux


def test_fingerprint_is_a_short_stable_hex_string() -> None:
    value = fp(WINDOWS_TRACEBACK)
    assert len(value) == 16
    int(value, 16)
    assert value == fp(WINDOWS_TRACEBACK)

#the diffrent tests checks the change of the fingerprints
def test_different_exception_type_gives_a_different_fingerprint() -> None:
    other = LINUX_TRACEBACK.replace("KeyError: 'name'", "ValueError: 'name'")
    assert fp(LINUX_TRACEBACK) != fp(other)


def test_different_user_frame_gives_a_different_fingerprint() -> None:
    other = LINUX_TRACEBACK.replace("in load", "in read")
    assert fp(LINUX_TRACEBACK) != fp(other)


def test_different_quoted_name_gives_a_different_fingerprint() -> None:
    other = LINUX_TRACEBACK.replace("KeyError: 'name'", "KeyError: 'email'")
    assert fp(LINUX_TRACEBACK) != fp(other)


def test_volatile_numbers_in_the_message_do_not_change_the_fingerprint() -> None:
    first = "Traceback (most recent call last):\nIndexError: list index 5 out of range"
    second = "Traceback (most recent call last):\nIndexError: list index 91 out of range"
    assert fp(first) == fp(second)


def test_library_internals_do_not_change_the_fingerprint() -> None:
    #proves that swapping a middle library frame doesn’t change anything.
    site = r"C:\Python312\Lib\site-packages\requests"

    def traceback_with(middle: str) -> str:
        return "\n".join(
            [
                "Traceback (most recent call last):",
                r'  File "C:\proj\app.py", line 5, in main',
                middle,
                f'  File "{site}\\adapters.py", line 9, in send',
                "ConnectionError: refused",
            ]
        )

    old_version = traceback_with(f'  File "{site}\\api.py", line 1, in get')
    new_version = traceback_with(f'  File "{site}\\sessions.py", line 2, in request')
    assert fp(old_version) == fp(new_version)
