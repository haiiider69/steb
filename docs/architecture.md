# Architecture

> Phases 0 and 1 are documented. Sections marked _TODO_ are filled in as each phase lands.

## Overview

```
            capture CLI (steb run / fix)             external corpora (SO, GitHub issues)
                        |                                         |
                        v                                         v
             ingest: parse -> redact -> normalize -> fingerprint -> dedup / content hash
                                          |
                                          v
        store: SQLite (records + metadata, source of truth) <-> BM25 index <-> vector index
                                          |
                                          v
        retrieval: exact fingerprint + BM25 + dense -> RRF fusion -> optional rerank
                                          |
                                          v
        MCP server (FastMCP, stdio)  <---  LangGraph agent
              ^                                 ^
     Claude Code / Desktop / VS Code    CLI `steb ask`, Streamlit web UI
```

## Agent graph (sketch, to be refined in Phase 5)

```
parse_error
  -> normalize_and_fingerprint
  -> exact_match_lookup
       hit  -> answer_from_memory ------------------------------+
       miss -> hybrid_retrieve (memory + KB)                    |
                 -> grade_relevance                             |
                      weak   -> rewrite_query | external_search |
                                (loop back, max N iterations)   |
                      strong -> generate_with_citations <-------+
                                  -> verify_citations
                                       -> final answer | honest abstention
```

## Components

### Capture (`src/steb/capture`)

Implemented in Phase 1.

- `runner.py`, `run_and_capture(command, store, cwd, echo)`:
  1. resolves the program with `shutil.which` (so `npm` finds `npm.cmd` on Windows); an unknown
     program raises `CommandNotFoundError` and records nothing;
  2. runs it with stderr merged into stdout (pytest prints its failures on stdout), with
     `PYTHONUNBUFFERED=1` and `PYTHONIOENCODING=utf-8` so Python children stream live and decode
     reliably;
  3. reads the pipe in chunks with an incremental UTF-8 decoder, shows each chunk live and keeps a
     copy (a prompt without a newline still appears immediately);
  4. returns the exit code unchanged. A failure is recorded only if the exit code is non-zero, the
     run was not interrupted with Ctrl+C, and the extracted error text is not empty.
- Error extraction (`extract_error_text`): the last Python traceback; otherwise the last block of
  pytest `E   ...` lines; otherwise the last 40 lines. Terminal color codes are removed and the
  text is capped at 20,000 characters (the end is kept).
- `git.py`, `git_context()`: current branch and short commit hash. Outside a repository, without
  git, or with no commit yet, the value is `None`; missing context never stops a recording.
- Language guess: a Python traceback means Python; otherwise the program name decides
  (`uv run X` looks at `X`).

Known limits: output is piped, so tools that detect a terminal may drop colors and interactive
programs (such as a REPL) behave poorly; only the last error of a run is recorded; the working
directory, OS and package versions are not captured yet.

### Ingestion: redaction, normalization, fingerprinting, dedup (`src/steb/ingest`)

Redaction, normalization and fingerprinting are implemented (Phase 1). Dedup and content hashing for
external documents are _TODO (Phase 3)._

Every error goes through the same pipeline, always in this order:

```
raw text -> redact() -> normalize() -> fingerprint()
```

- `redact.py`: ordered regex rules, most specific first: private key blocks, JWTs, known API key
  formats (Anthropic/OpenAI, GitHub, AWS, Slack, Google), passwords in URLs, bearer tokens,
  `name=value` assignments whose name looks sensitive, emails, and usernames in home directories
  (`C:\Users\<name>`, `/home/<name>`). Each match becomes `[REDACTED:KIND]`. The function is
  idempotent. It is best effort: a secret with no recognizable shape and no revealing name can slip
  through.
- `normalize.py`: replaces what changes between machines and runs, so the same bug gives the same
  text:

  | Volatile part | Becomes |
  |---|---|
  | project file path | `<PATH>/file.py` |
  | installed package path | `<SITE>/package/module.py` |
  | standard library path | `<STDLIB>/module.py` |
  | `line 42`, `file.py:42:7` | `line <N>`, `file.py:<N>` |
  | memory address (10+ hex digits) | `<ADDR>` |
  | UUID | `<UUID>` |
  | timestamp, date, time | `<TIMESTAMP>`, `<DATE>`, `<TIME>` |
  | temp file name (`tmp` + 8 characters) | `<TMPNAME>` |

  Short hex codes (`0x80070005`) are kept because they are meaningful error codes. Line endings and
  blank lines are cleaned. The function is idempotent.
- `fingerprint.py`: `parse_error()` extracts the exception type, message and stack frames from a
  Python traceback (for chained exceptions only the last one counts; other languages fall back to
  type and message). `message_template()` and `fingerprint()` are described in the data model below.

### Store and index sync (`src/steb/store`)

The SQLite store is implemented (Phase 1). The BM25 and vector indexes and their sync logic are
_TODO (Phases 3, 4)._

- `database.py`, `ErrorStore`: the source of truth. It uses the standard `sqlite3` module (no ORM),
  works as a context manager, and creates its folder and schema on first use.
- Safety rule: `record_error()` accepts only raw text and runs redact, normalize and fingerprint
  itself; the command line and fix notes are redacted as well. Nothing unredacted can be written.
- `record_error()` uses one atomic `INSERT ... ON CONFLICT DO UPDATE`: a new fingerprint creates a
  bug, a known one increments its counter. The bug and its occurrence are written in one
  transaction.
- Read methods: `get_error`, `find_by_fingerprint`, `list_errors`, `occurrences_for`, `fixes_for`;
  write methods: `record_error`, `add_fix`.
- The schema version lives in SQLite's `PRAGMA user_version` (currently 1). Opening a database from
  a newer steb raises `DatabaseVersionError`; later phases add migrations in `_migrate()`.
- Timestamps are UTC, ISO 8601, so they sort correctly as text.

### Configuration (`src/steb/config.py`)

Typed settings (pydantic-settings) read from environment variables and `.env`; real environment
variables win over the file. Everything has a default, API keys are `SecretStr` (hidden in `repr`),
and `get_settings()` returns one cached instance. The database lives at `STEB_HOME/steb.db`
(default `./data`, relative to where steb is run).

### Command line (`src/steb/cli.py`, `src/steb/commands.py`)

Implemented in Phase 1: `steb run`, `steb fix`, `steb list`, `steb show`. `ask` and `ingest` are
_TODO (Phases 3, 5)._

- `cli.py` (Typer) only parses arguments, opens the store and calls `commands.py`.
- `commands.py` holds the behavior. Each function takes the store and output streams and returns an
  exit code, so it is tested without Typer.
- steb's own messages go to stderr and start with `steb:`; the wrapped command's output goes to
  stdout. Exit codes: the wrapped command's own code, 1 failure, 2 usage error, 127 program not
  found.
- On a repeated error, `steb run` reports `seen this error before!`, the occurrence count and the
  most recent fix.

### Retrieval (`src/steb/retrieval`)
_TODO (Phase 4)._

### Agent (`src/steb/agent`)
_TODO (Phase 5)._

### MCP server and client (`src/steb/mcp_server`, `src/steb/mcp_client`)

Planned tools: `search_past_errors`, `get_fix`, `record_error`, `link_fix`,
`search_knowledge_base`. _TODO (Phase 6)._

### Web UI (`src/steb/web`)
_TODO (Phase 9)._

## Data model

### Tables (schema version 1)

```
errors       one row per distinct bug (one fingerprint)
  id INTEGER PRIMARY KEY            the number used by `steb fix <id>`
  fingerprint TEXT UNIQUE           stable identifier of the bug
  exc_type TEXT                     exception class, or "Unknown"
  normalized_text TEXT              redacted and normalized error text
  first_seen, last_seen TEXT        UTC ISO 8601
  occurrence_count INTEGER          how many times the bug was recorded

occurrences  one row each time the bug was seen
  id INTEGER PRIMARY KEY
  error_id -> errors(id)            ON DELETE CASCADE
  occurred_at TEXT                  UTC ISO 8601
  command TEXT                      the failed command, redacted
  git_branch, git_commit TEXT       context at that moment (may be empty)
  language TEXT                     guessed language (may be empty)
  redacted_text TEXT                the error as printed, secrets removed, real line numbers kept

fixes        what solved a bug
  id INTEGER PRIMARY KEY
  error_id -> errors(id)            ON DELETE CASCADE
  git_commit TEXT                   commit containing the fix (optional)
  note TEXT                         what was done, redacted
  created_at TEXT                   UTC ISO 8601
```

A fix belongs to a bug, not to one occurrence, so it is found again whenever the bug returns.

### Metadata

| Stored in Phase 1 | Planned |
|---|---|
| command, git branch, git commit, language, timestamps, occurrence count | working directory and project, package versions, OS |
| fix note and commit | fix diff or URL, resolved status and re-indexing |

Adding fields later is done with a schema migration (see `user_version`).

### Fingerprint definition

`fingerprint(normalized_text)` is the first 16 hex characters of the SHA-256 of these parts, joined
by an invisible separator character:

1. a version tag, `v1` (`FINGERPRINT_VERSION`), so fingerprints from different algorithms are never
   compared;
2. the exception type, for example `KeyError`;
3. the message template: standalone numbers become `<N>`, quoted strings that are not
   identifier-like become `<STR>`; identifier-like quotes (`'requests'`), version numbers and
   `Errno` codes are kept;
4. the identifying frames, as `file:function` without line numbers: the last 3 project frames,
   plus the innermost frame if it belongs to a library. Library frames in between are ignored,
   because library internals change between versions. If there are no project frames, the last
   3 frames are used.

The fingerprint is an exact-match key and favors precision: two errors stay separate when in doubt.
Finding similar errors is the job of retrieval (Phase 4).

### Known limits (Phase 1)

- Only Python tracebacks yield stack frames. Other languages are identified by type and message,
  and pytest's default output gives type and message only (`pytest --tb=native` gives full
  tracebacks).
- Only the first line of a multi-line exception message is used.
- Paths with spaces are cut at the first space during normalization, and relative Windows paths
  with backslashes are not unified with their Linux form.
- Only the last error of a run is recorded.
- The database location is relative to the working directory; a per-user default is a Phase 10
  hardening item.
