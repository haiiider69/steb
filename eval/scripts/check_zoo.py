"""Check every bug in the zoo: buggy.py must fail as described and fixed.py must run cleanly.

Run from the repository root:

    uv run python eval/scripts/check_zoo.py

Prints one line per bug and exits with status 1 if any bug is invalid.
"""

import sys

from steb.zoo import check_bug, load_zoo


def main() -> int:
    """Check the whole zoo and report the result.

    Returns:
        0 if every bug is valid, 1 otherwise.
    """
    bugs = load_zoo()
    invalid = 0
    for bug in bugs:
        problems = check_bug(bug)
        print(f"{'ok  ' if not problems else 'FAIL'} {bug.id}")
        for problem in problems:
            print(f"       - {problem}")
        invalid += bool(problems)
    print(f"\n{len(bugs) - invalid}/{len(bugs)} bugs ok")
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
