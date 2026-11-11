# Bug zoo

Small, reproducible Python scripts that trigger common real errors, each with a known fix. They
give the evaluation its **ground truth**: we run them through `steb` to build a realistic memory,
then check that variants of each error find the original bug and its fix.

## Layout

```
eval/bug_zoo/<category>/<slug>/
    buggy.py     a short, realistic script that fails with a known exception
    fixed.py     the same script with the reference fix applied; runs cleanly
    meta.json    the ground truth
```

`meta.json` has exactly these fields (all non-empty strings, no others):

| Field | Meaning |
|---|---|
| `id` | `<category>/<slug>`, equal to the folder path |
| `category` | one of the categories below, equal to the parent folder |
| `title` | the mistake in one line |
| `exception` | the exception name exactly as Python prints it (`json.decoder.JSONDecodeError`, not `JSONDecodeError`) |
| `message_contains` | a fragment the exception message must contain |
| `fix_summary` | the reference fix, in words |

## Categories

| Category | Typical errors |
|---|---|
| `import_errors` | missing modules, wrong names, circular imports |
| `type_errors` | wrong operand types, wrong arguments, calling non-callables |
| `value_errors` | bad conversions, invalid values, parsing |
| `key_index_errors` | missing dict keys, list indexes out of range |
| `attribute_errors` | `None` has no attribute, typos in attribute names |
| `file_path_errors` | missing files and folders, directories used as files |
| `encoding_errors` | Unicode decode and encode problems |
| `removed_apis` | standard-library APIs removed in newer Python versions |
| `unpacking_errors` | wrong number of values when unpacking, length mismatches |
| `timeouts_and_limits` | timeouts, recursion limits, empty queues |
| `async_and_threads` | misuse of asyncio and threading |
| `syntax_errors` | scripts that do not even parse |

## Rules for a bug

- **Standard library only.** The zoo must run anywhere with the project's Python (3.12). The only
  version that matters is Python's, and bugs about removed APIs use APIs that were already removed
  in Python 3.11 or earlier.
- **Deterministic.** `buggy.py` must fail the same way on every run and on every operating system.
  Do not depend on the default text encoding, the current directory, the network or the clock.
- **Self-contained.** One file each. If a script needs files, it creates them in
  `tempfile.TemporaryDirectory()` and cleans up.
- **Realistic.** A short script a person might really write, with ordinary names, and a mistake a
  person might really make, not `raise Exception("boom")`.
- **A minimal fix.** `fixed.py` differs from `buggy.py` only by what the fix needs.
- **Fast.** Each script finishes in well under a second.

## Checking the zoo

```bash
uv run python eval/scripts/check_zoo.py
```

For every bug this runs `buggy.py` and `fixed.py` and verifies that the first fails with the
expected exception and message, and the second exits cleanly. The same check runs in the test
suite (`tests/test_zoo.py`), so a broken bug cannot be committed unnoticed.
