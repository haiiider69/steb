# Architecture

> Stub (Phase 0). Sections are filled in as each phase lands.

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
_TODO (Phase 1)._

### Ingestion: redaction, normalization, fingerprinting, dedup (`src/steb/ingest`)
_TODO (Phases 1, 3)._

### Store and index sync (`src/steb/store`)
_TODO (Phases 1, 3, 4)._

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

_TODO (Phase 1): record schema, fix schema, metadata fields, fingerprint definition._
