"""Tests for error text normalization."""

import pytest

from steb.ingest.normalize import normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            r'File "C:\Users\bob\Desktop\proj\app.py", line 3',
            'File "<PATH>/app.py", line <N>',
        ),
        (
            'File "/home/alice/work/proj/app.py", line 3',
            'File "<PATH>/app.py", line <N>',
        ),
        (
            r"File C:\Users\[REDACTED:USER]\Desktop\app.py, line 3",
            "File <PATH>/app.py, line <N>",
        ),
        (
            "No such file or directory: '/Users/bob/data/input.csv'",
            "No such file or directory: '<PATH>/input.csv'",
        ),
    ],
)
def test_project_paths_keep_only_the_file_name(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_same_bug_on_two_machines_normalizes_identically() -> None:
    windows = r'File "C:\Users\ASUS\Desktop\proj\app.py", line 12, in main'
    linux = 'File "/home/alice/code/proj/app.py", line 97, in main'
    assert normalize(windows) == normalize(linux)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            r'File "C:\Python312\Lib\site-packages\requests\api.py", line 59',
            'File "<SITE>/requests/api.py", line <N>',
        ),
        (
            'File "/usr/lib/python3/dist-packages/yaml/loader.py", line 5',
            'File "<SITE>/yaml/loader.py", line <N>',
        ),
        (
            'File "/usr/lib/python3.12/json/decoder.py", line 355',
            'File "<STDLIB>/json/decoder.py", line <N>',
        ),
        (
            r'File "C:\Python312\Lib\json\decoder.py", line 355',
            'File "<STDLIB>/json/decoder.py", line <N>',
        ),
    ],
)
def test_library_paths_keep_the_package_path(text: str, expected: str) -> None:
    assert normalize(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("app.py:42", "app.py:<N>"),
        ("src/main.ts:10:5 - error", "src/main.ts:<N> - error"),
        ("SyntaxError at line 7", "SyntaxError at line <N>"),
    ],
)
def test_line_numbers_are_replaced(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_memory_addresses_are_replaced_but_short_codes_are_kept() -> None:
    assert normalize("<Foo object at 0x7f3a2b1c4d50>") == "<Foo object at <ADDR>>"
    assert normalize("failed with 0x80070005") == "failed with 0x80070005"


def test_uuids_are_replaced() -> None:
    text = "request 123e4567-e89b-12d3-a456-426614174000 failed"
    assert normalize(text) == "request <UUID> failed"


def test_timestamps_and_dates_are_replaced() -> None:
    assert normalize("2026-11-02T10:15:30.123Z ERROR boom") == "<TIMESTAMP> ERROR boom"
    assert normalize("2026-11-02 10:15:30,123 ERROR boom") == "<TIMESTAMP> ERROR boom"
    assert normalize("built on 2026-11-02") == "built on <DATE>"
    assert normalize("at 10:15:30 it broke") == "at <TIME> it broke"


def test_temp_file_names_are_replaced() -> None:
    assert normalize("cannot open tmpab12cd34.py") == "cannot open <TMPNAME>.py"


def test_whitespace_and_line_endings_are_cleaned() -> None:
    text = "Error: boom   \r\n\r\n\r\n\r\nnext line  \r\n"
    assert normalize(text) == "Error: boom\n\nnext line"


@pytest.mark.parametrize(
    "text",
    [
        "ValueError: invalid literal for int() with base 10: 'abc'",
        "KeyError: 'name'",
        "ConnectionError: could not reach https://api.example.com/v1/users",
        "ModuleNotFoundError: No module named 'requests'",
        "connect to localhost:5432 refused",
    ],
)
def test_ordinary_error_text_is_unchanged(text: str) -> None:
    assert normalize(text) == text


def test_normalization_is_idempotent() -> None:
    sample = "\n".join(
        [
            "Traceback (most recent call last):",
            r'  File "C:\Users\[REDACTED:USER]\proj\app.py", line 12, in main',
            r'  File "C:\Python312\Lib\site-packages\requests\api.py", line 59, in get',
            "  at 2026-11-02T10:15:30Z <Foo object at 0x7f3a2b1c4d50>",
            "  request 123e4567-e89b-12d3-a456-426614174000 tmpab12cd34.py",
            "app.py:42:7 failed",
        ]
    )
    once = normalize(sample)
    assert normalize(once) == once
