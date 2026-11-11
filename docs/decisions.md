# Design decisions

Log of notable design decisions. These feed the technical report.
Format: date, decision, alternatives considered, why.

---

### 2026-10-18 — uv + `pyproject.toml`, pinned to Python 3.12

- **Decision**: manage the environment and dependencies with uv; `requires-python >= 3.11`, local
  development pinned to 3.12 via `.python-version`.
- **Alternatives**: pip + `requirements.txt`; Poetry; the newest Python (3.14).
- **Why**: uv gives a reproducible lockfile and fast installs on all three OSes. 3.12 is chosen over
  the newest release because ML dependencies (PyTorch, sentence-transformers, vector stores) tend
  to publish wheels for new Python versions late.

### 2026-10-18 — Dependencies added per phase

- **Decision**: `pyproject.toml` starts with only dev tools (pytest, ruff); runtime dependencies are
  added in the phase that first uses them.
- **Alternatives**: declare the whole stack up front.
- **Why**: keeps each phase's commit self-contained and makes the history show when and why each
  library was introduced.

### 2026-10-18 — API LLM provider by default, Ollama supported

- **Decision**: the LLM provider is configurable via `.env`; the team will use an API provider by
  default (exact provider TBD). Local Ollama remains a supported option.
- **Alternatives**: local-only (Ollama) by default.
- **Why**: better answer and judge quality on the team's Windows machines without a local GPU
  requirement. Error logs can be sensitive, so redaction runs before anything is stored or sent,
  and users can switch to Ollama to keep everything local.

### 2026-10-18 — Docstrings enforced by the linter

- **Decision**: ruff's pydocstyle rules (`D`, Google convention) are enabled for `src/`.
- **Alternatives**: rely on review only.
- **Why**: documented code is graded; enforcing it in CI/lint avoids gaps.

### 2026-11-10 — The store only accepts raw text and redacts it itself

- **Decision**: `ErrorStore.record_error()` takes the raw error text and runs redact, normalize and
  fingerprint internally; the command line and fix notes are redacted too. No method accepts
  already-processed text from outside.
- **Alternatives**: redact only when displaying; redact only before calling an LLM; trust every
  caller to redact first.
- **Why**: a secret that reaches the database or an embedding cannot be taken back. Making the
  unsafe path impossible is more reliable than documenting a convention.

### 2026-11-10 — Regex redaction: specific rules first, labelled placeholders, over-redact

- **Decision**: ordered rules (private keys, JWTs, known API key formats, passwords in URLs, bearer
  tokens, `name=value` assignments with sensitive names, emails, usernames in home directories),
  each replaced by `[REDACTED:KIND]`. The function is idempotent.
- **Alternatives**: plain `***` masks; entropy-based detection; a third-party secret scanner.
- **Why**: labels keep the text readable and show what was removed; a false positive costs little
  while a leak costs a lot; no extra dependency. Known limit: a secret with no recognizable shape
  and no revealing variable name can slip through.

### 2026-11-10 — Normalization keeps library paths, drops project paths, keeps short hex codes

- **Decision**: absolute project paths become `<PATH>/file.py`, installed packages
  `<SITE>/pkg/mod.py`, the standard library `<STDLIB>/...`. Line numbers, memory addresses (10+ hex
  digits), UUIDs, timestamps and temp file names become placeholders. Short hex codes such as
  `0x80070005` are kept.
- **Alternatives**: reduce every path to its file name; leave paths untouched.
- **Why**: the same bug on Windows and Linux must give identical text, but which library failed
  helps identify a bug, and short hex numbers are meaningful error codes.

### 2026-11-10 — The fingerprint is an exact-match key that favors precision

- **Decision**: SHA-256 (first 16 hex characters) of a version tag, the exception type, the message
  template and the identifying frames: the last 3 project frames plus the innermost library frame.
  Library frames in between are ignored. `FINGERPRINT_VERSION` is part of the hash.
- **Alternatives**: hash of the whole normalized text; exception type and message only; fuzzy
  hashing.
- **Why**: finding similar errors is the job of retrieval (Phase 4); the fingerprint is the fast
  exact path, so wrongly merging two bugs is worse than splitting one. Library internals change
  between versions, and the version tag prevents comparing fingerprints from different algorithms.

### 2026-11-10 — Message templates keep identifier-like quoted names

- **Decision**: in an exception message, standalone numbers become `<N>` and quoted strings that
  are not identifier-like become `<STR>`. Identifier-like quotes (`'requests'`, `'name'`), version
  numbers and `Errno` codes stay.
- **Alternatives**: replace every quoted string; keep messages verbatim.
- **Why**: `No module named 'requests'` and `No module named 'numpy'` are different bugs, while
  `list index 5` and `list index 91` are the same one. Known cost: two data strings that look like
  identifiers (`'abc'` and `'xyz'`) stay separate, which is a split rather than a wrong merge.

### 2026-11-10 — SQLite with three tables and the standard library only

- **Decision**: `errors` (one row per fingerprint, with an occurrence counter), `occurrences` (one
  row each time the bug is seen, with its context) and `fixes`. Plain `sqlite3`, no ORM; one atomic
  `INSERT ... ON CONFLICT DO UPDATE`; foreign keys with cascade; UTC ISO 8601 timestamps.
- **Alternatives**: a single flat table; JSON files; SQLAlchemy.
- **Why**: a fix belongs to a bug, not to one occurrence, so it is found again when the bug
  returns; the upsert cannot create duplicates; no server and no extra dependency; ISO UTC text
  sorts correctly.

### 2026-11-10 — Schema version stored in `PRAGMA user_version`

- **Decision**: the database records its schema version (1). A database created by a newer steb is
  refused; future migrations run by comparing versions.
- **Alternatives**: no versioning; a migration tool such as Alembic.
- **Why**: later phases can add columns (working directory, OS, package versions) without breaking
  existing databases, without a heavy tool.

### 2026-11-10 — Capture merges stdout and stderr, streams live, passes the exit code through

- **Decision**: the command runs with stderr merged into stdout; output is shown as it arrives and
  kept. The exit code is returned unchanged. A failure is recorded only if the exit code is non-zero,
  the run was not interrupted (Ctrl+C), the program exists and the extracted text is not empty. The
  error text is the last Python traceback, else the last pytest `E` block, else the last 40 lines.
- **Alternatives**: capture stderr only; buffer and print at the end; record every non-zero exit.
- **Why**: pytest prints its failures on stdout; users need to see output live; wrapping a command
  must not change its exit code in scripts and CI; a mistyped command or an interrupt is not a bug
  in the user's code.

### 2026-11-10 — Typer command line with the logic kept out of the parsing layer

- **Decision**: `cli.py` only parses arguments; `commands.py` holds the behavior and takes the store
  and output streams as arguments. steb's own messages go to stderr, prefixed `steb:`. Exit codes:
  the wrapped command's own code, 1 failure, 2 usage error, 127 program not found. `steb run`
  accepts the command with or without `--`.
- **Alternatives**: `argparse`; logic inside the Typer functions.
- **Why**: Typer matches the planned stack; the behavior is testable without the framework; stdout
  stays clean for the wrapped command's output.

### 2026-11-10 — Phase 1 dependencies: pydantic-settings and Typer

- **Decision**: add `pydantic-settings` (typed, validated settings, with API keys as `SecretStr`)
  and `typer` (command line). Everything else in Phase 1 uses the standard library.
- **Alternatives**: read `os.environ` directly; `argparse`.
- **Why**: follows the rule of adding dependencies in the phase that first uses them; validation
  happens in one place; keys do not leak into logs or `repr`.
