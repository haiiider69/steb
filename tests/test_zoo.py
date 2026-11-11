"""Tests for the bug zoo format, the checker and the zoo itself."""

import json
from pathlib import Path

import pytest

from steb.zoo import (
    CATEGORIES,
    BugFormatError,
    check_bug,
    iter_bug_dirs,
    load_bug,
    load_zoo,
    run_script,
)

GOOD_META = {
    "id": "value_errors/divide_by_zero",
    "category": "value_errors",
    "title": "Dividing by zero",
    "exception": "ZeroDivisionError",
    "message_contains": "division by zero",
    "fix_summary": "Check the divisor before dividing.",
}
BUGGY = "print(1 / 0)\n"
FIXED = "print(1 / 1)\n"


def make_bug(
    root: Path,
    category: str = "value_errors",
    slug: str = "divide_by_zero",
    *,
    buggy: str | None = BUGGY,
    fixed: str | None = FIXED,
    meta: dict | str | None = None,
) -> Path:
    """Create a bug folder in a temporary zoo and return it."""
    folder = root / category / slug
    folder.mkdir(parents=True)
    if buggy is not None:
        (folder / "buggy.py").write_text(buggy, encoding="utf-8")
    if fixed is not None:
        (folder / "fixed.py").write_text(fixed, encoding="utf-8")
    if meta is None:
        meta = {**GOOD_META, "id": f"{category}/{slug}", "category": category}
    if isinstance(meta, str):
        (folder / "meta.json").write_text(meta, encoding="utf-8")
    else:
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def test_a_valid_bug_is_loaded(tmp_path: Path) -> None:
    bug = load_bug(make_bug(tmp_path))
    assert bug.id == "value_errors/divide_by_zero"
    assert bug.category == "value_errors"
    assert bug.slug == "divide_by_zero"
    assert bug.exception == "ZeroDivisionError"
    assert bug.buggy_path.name == "buggy.py"
    assert bug.fixed_path.name == "fixed.py"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"id": "value_errors/other"}, "says id"),
        ({"category": "type_errors"}, "says category"),
        ({"title": ""}, "non-empty string"),
        ({"exception": 42}, "non-empty string"),
        ({"surprise": "x"}, "unknown meta.json field"),
    ],
)
def test_inconsistent_metadata_is_rejected(tmp_path: Path, changes: dict, message: str) -> None:
    meta = {**GOOD_META, **changes}
    with pytest.raises(BugFormatError, match=message):
        load_bug(make_bug(tmp_path, meta=meta))


def test_missing_metadata_field_is_rejected(tmp_path: Path) -> None:
    meta = {key: value for key, value in GOOD_META.items() if key != "fix_summary"}
    with pytest.raises(BugFormatError, match="fix_summary"):
        load_bug(make_bug(tmp_path, meta=meta))


def test_missing_files_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(BugFormatError, match="fixed.py is missing"):
        load_bug(make_bug(tmp_path, fixed=None))


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(BugFormatError, match="not valid JSON"):
        load_bug(make_bug(tmp_path, meta="{not json"))


def test_metadata_must_be_an_object(tmp_path: Path) -> None:
    with pytest.raises(BugFormatError, match="JSON object"):
        load_bug(make_bug(tmp_path, meta="[1, 2]"))


def test_unknown_category_is_rejected(tmp_path: Path) -> None:
    meta = {**GOOD_META, "id": "made_up/divide_by_zero", "category": "made_up"}
    with pytest.raises(BugFormatError, match="not a known category"):
        load_bug(make_bug(tmp_path, category="made_up", meta=meta))


def test_bad_folder_name_is_rejected(tmp_path: Path) -> None:
    meta = {**GOOD_META, "id": "value_errors/Bad-Name"}
    with pytest.raises(BugFormatError, match="folder name"):
        load_bug(make_bug(tmp_path, slug="Bad-Name", meta=meta))


def test_zoo_is_loaded_sorted_and_ignores_stray_entries(tmp_path: Path) -> None:
    make_bug(tmp_path, "value_errors", "zeta")
    make_bug(tmp_path, "type_errors", "alpha")
    make_bug(tmp_path, "value_errors", "beta")
    (tmp_path / "notes.txt").write_text("not a category", encoding="utf-8")
    (tmp_path / "_drafts").mkdir()
    (tmp_path / "value_errors" / ".hidden").mkdir()
    ids = [bug.id for bug in load_zoo(tmp_path)]
    assert ids == ["type_errors/alpha", "value_errors/beta", "value_errors/zeta"]


def test_missing_zoo_folder_gives_an_empty_zoo(tmp_path: Path) -> None:
    assert iter_bug_dirs(tmp_path / "does_not_exist") == []


def test_run_script_captures_output_and_exit_code(tmp_path: Path) -> None:
    script = tmp_path / "script.py"
    script.write_text(
        "import sys\nprint('out')\nprint('err', file=sys.stderr)\nsys.exit(4)\n", encoding="utf-8"
    )
    result = run_script(script)
    assert result.exit_code == 4
    assert "out" in result.output
    assert "err" in result.output
    assert not result.timed_out


def test_run_script_stops_scripts_that_take_too_long(tmp_path: Path) -> None:
    script = tmp_path / "forever.py"
    script.write_text("while True:\n    pass\n", encoding="utf-8")
    result = run_script(script, timeout=1)
    assert result.timed_out
    assert result.exit_code is None


def test_run_script_uses_a_fresh_working_directory(tmp_path: Path) -> None:
    script = tmp_path / "cwd.py"
    script.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    result = run_script(script)
    assert Path(result.output.strip()).resolve() != Path.cwd().resolve()


def test_a_correct_bug_has_no_problems(tmp_path: Path) -> None:
    assert check_bug(load_bug(make_bug(tmp_path))) == []


@pytest.mark.parametrize(
    ("buggy", "fixed", "expected"),
    [
        ("print('fine')\n", FIXED, "supposed to fail"),
        ("raise ValueError('x')\n", FIXED, "did not report ZeroDivisionError"),
        ("print(1 / 0)  # same\n", "print(1 / 0)  # same\n", "identical"),
        (BUGGY, "raise RuntimeError('still broken')\n", "fixed.py exited with code"),
        (BUGGY, "while True:\n    pass\n", "fixed.py did not finish"),
        ("while True:\n    pass\n", FIXED, "buggy.py did not finish"),
        (
            BUGGY,
            "import traceback\ntry:\n    1 / 0\nexcept ZeroDivisionError:\n"
            "    traceback.print_exc()\n",
            "printed a traceback",
        ),
    ],
)
def test_broken_bugs_are_reported(tmp_path: Path, buggy: str, fixed: str, expected: str) -> None:
    bug = load_bug(make_bug(tmp_path, buggy=buggy, fixed=fixed))
    problems = check_bug(bug, timeout=1)
    assert any(expected in problem for problem in problems), problems


def test_wrong_message_fragment_is_reported(tmp_path: Path) -> None:
    meta = {**GOOD_META, "message_contains": "something else entirely"}
    bug = load_bug(make_bug(tmp_path, meta=meta))
    problems = check_bug(bug)
    assert any("does not contain" in problem for problem in problems), problems


@pytest.mark.parametrize(
    "bug_dir",
    iter_bug_dirs(),
    ids=lambda path: f"{path.parent.name}/{path.name}",
)
def test_every_bug_in_the_zoo_behaves_as_documented(bug_dir: Path) -> None:
    bug = load_bug(bug_dir)
    assert check_bug(bug) == []


def test_zoo_ids_are_unique_and_titles_are_distinct() -> None:
    bugs = load_zoo()
    assert len({bug.id for bug in bugs}) == len(bugs)
    assert len({bug.title for bug in bugs}) == len(bugs)


def test_category_list_has_no_duplicates() -> None:
    assert len(set(CATEGORIES)) == len(CATEGORIES)
