"""Write a small report into a reports/ folder."""

import os
import tempfile


def write_report(base_dir, lines):
    target = os.path.join(base_dir, "reports", "summary.txt")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return target


def main():
    with tempfile.TemporaryDirectory() as workdir:
        path = write_report(workdir, ["total: 42", "errors: 0"])
        print(f"report written to {path}")


if __name__ == "__main__":
    main()
