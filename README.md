# steb — seen this error before

**A personal error memory for developers.** steb captures every error you hit and how you
fixed it. When an error shows up again, it answers *"last time you fixed this by ..."*, citing
your past commit, your note, or a Stack Overflow / GitHub source. Coding agents (Claude Code,
Claude Desktop, VS Code) can query it via MCP.

> Status: **Phase 0 — scaffolding.** No features are implemented yet. See the roadmap below.
> The idea in detail: [docs/pitch.md](docs/pitch.md).

## How it works

1. **Capture** — `steb run -- <command>` runs any command. On failure it stores the redacted
   stack trace plus context (command, cwd, project, git branch/commit, language, package versions,
   OS, timestamp).
2. **Fix linking** — `steb fix <id>` attaches the fix (commit sha / diff, a note, a URL) and
   re-indexes the record as resolved.
3. **Knowledge base** — an external corpus of Stack Overflow Q&A and GitHub issues with fix PRs
   covers errors you've never seen.
4. **Ask** — paste or pipe an error; a LangGraph agent retrieves similar past errors and external
   solutions and answers with verified citations, or abstains honestly.
5. **Use from anywhere** — an MCP server exposes the memory to coding agents.

## Course requirements

| Req | Description | Where | Status |
|---|---|---|---|
| R1 | Document management: RAG, metadata, citations, docs | `src/steb/ingest`, `src/steb/store`, `docs/` | todo |
| R2 | Tool calling / MCP server (≥ 2 tools) + client | `src/steb/mcp_server`, `src/steb/mcp_client` | todo |
| R3 | LangChain / LangGraph | `src/steb/agent` | todo |
| R4 | Benchmarking: retrieval (Recall@k, MRR) + generation, ≥ 50 questions | `eval/` | todo |
| R5 | Web interface | `src/steb/web` (Streamlit) | todo |
| R6 | Ingestion pipeline with metadata and updates | `src/steb/ingest`, `src/steb/store` | todo |
| R7 | Fine-tuning experiment vs baseline | `finetune/` | todo |

## Setup

Requires [uv](https://docs.astral.sh/uv/). On Windows:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then, from the repo root:

```bash
uv sync              # creates .venv with Python 3.12 and dev tools
cp .env.example .env # then fill in your LLM provider and keys
uv run pytest        # smoke test
uv run ruff check .
```

Usage instructions (CLI, MCP server, web app, benchmarks) will be added as each feature lands.

## Repository layout

```
src/steb/      capture, ingest, store, retrieval, agent, mcp_server, mcp_client, web, cli, config
eval/          bug_zoo, datasets, scripts, results
finetune/      embedding fine-tuning experiment
data/          local data (gitignored, populated by scripts)
docs/          architecture, decisions, data sources, pitch, report drafts
tests/
```

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Scaffolding, tooling, pitch | in progress |
| 1 | Capture CLI, SQLite store, normalization, fingerprinting, secret redaction | todo |
| 2 | Bug zoo + personal memory + eval dataset v1 | todo |
| 3 | External KB ingestion with dedup and incremental updates | todo |
| 4 | Hybrid retrieval (exact, BM25, dense, RRF, rerank) + retrieval benchmark | todo |
| 5 | LangGraph agent with corrective loop, cited generation, citation verification | todo |
| 6 | MCP server + demo client | todo |
| 7 | Generation benchmark | todo |
| 8 | Embedding fine-tuning, base vs fine-tuned | todo |
| 9 | Streamlit web UI | todo |
| 10 | Hardening, report, demo | todo |

## Team

| Member | Focus |
|---|---|
| Khaled | Capture & store, normalization/fingerprinting/redaction, retrieval, LangGraph agent, MCP |
| Haider | Bug zoo & eval datasets, external KB ingestion, generation benchmark, fine-tuning, web UI |

## Documentation

- [docs/pitch.md](docs/pitch.md) — the idea and why it matters
- [docs/architecture.md](docs/architecture.md) — system design
- [docs/decisions.md](docs/decisions.md) — design decision log
- [docs/data.md](docs/data.md) — data sources and licenses
