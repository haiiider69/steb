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
