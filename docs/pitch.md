# steb — seen this error before

*Project proposal — Khaled & Haider*

## The problem

Every developer knows this moment: an error scrolls past and you think *"I've fixed this
before."* Maybe it was three months ago, in another project, on another branch. You remember
that you solved it, but not how. So you search the web again, read the same Stack Overflow threads
again, and lose the same half hour again.

Your fix is still there, buried in a commit, a Slack message or a terminal you closed long ago.
But nothing connects the error you're looking at now to the fix you already made.

The usual tools don't help much here:

- **Web search and Stack Overflow** know about other people's errors, not yours. They don't know
  your project, your library versions, or what worked for you last time.
- **General chat assistants** answer fluently but without sources, and they may suggest a fix for
  pandas 1.x when you're on pandas 2.x.
- **Error trackers like Sentry** group production crashes for a team. They don't follow an
  individual developer from terminal to terminal, and they don't remember the fix.

## The idea

**steb is a personal error memory for developers.** It quietly records every error you hit
and how you fixed it. When an error comes back, it says (illustrative example):

> *"You hit this on 12 March in `billing-service`. You fixed it in commit `a1b2c3d` by pinning
> `urllib3<2`. Your note: 'requests 2.28 breaks with urllib3 2.x'."* [record #142, commit a1b2c3d]

When you have never seen the error before, it falls back to an external knowledge base of
Stack Overflow answers and GitHub issues with their fix PRs, and cites those instead. When
nothing relevant exists, it says so honestly instead of making something up.

## How you use it

1. **Capture without changing habits.** Prefix any command: `steb run -- pytest`. If it
   fails, steb stores the stack trace together with the context: command, project, git branch
   and commit, language, package versions, OS and time.
2. **Link the fix.** `steb fix 142 --commit a1b2c3d --note "pin urllib3"`. steb can also
   notice when the same command succeeds again later in the same repo and propose the diff as
   the fix.
3. **Ask.** Paste or pipe an error into `steb ask`, or open the web app.
4. **Let your coding agent ask for you.** steb runs as an **MCP server**, so Claude Code,
   Claude Desktop or VS Code can query your error memory by themselves whenever they hit an
   error.

## The demo we're building towards

In Claude Code, we run a small script that crashes. The coding agent calls steb through MCP and
answers *"you fixed this on <date> in commit <sha>"*, with citations. Then we show the web UI
(the memory browser with its timeline) and the benchmark dashboard with our measured results.

## Why it's technically interesting

steb looks simple, but each step hides a real retrieval problem:

- **Stack traces are noisy.** The same bug shows up with different absolute paths, usernames,
  line numbers, memory addresses, temp file names and timestamps. We **normalize** traces and
  compute a stable **fingerprint** (exception type + message template + top user frames, similar
  in spirit to Sentry's issue grouping), and we measure how much this helps compared with raw
  text.
- **Error logs contain secrets.** API keys, tokens, JWTs, passwords inside URLs, emails, home
  directory usernames. Everything goes through **redaction before it is stored or embedded**, and
  that step has its own unit tests.
- **One retriever is not enough.** Exact fingerprint matches, keyword matches (BM25) and semantic
  matches (dense embeddings) each catch different cases. We **fuse them with Reciprocal Rank
  Fusion**, add optional cross-encoder reranking, and support metadata filters (language, library,
  version, project, source, resolved status).
- **Versions matter.** A correct fix for one major version can be wrong for the next. Retrieval and
  answers take package versions into account.
- **Agents should know when they don't know.** A **LangGraph** agent grades what it retrieved. If
  the results are weak, it rewrites the query or searches the external knowledge base, with a
  bounded number of loops, and it abstains when nothing fits.
- **Citations must be real.** Every claim cites a record id, commit sha or URL, and a separate
  **verification step** checks that the cited source actually supports the claim.
- **The memory changes over time.** Repeated errors increase an occurrence count instead of
  creating duplicates, and linking a fix turns an unresolved record into a resolved one. The SQLite
  store, the BM25 index and the vector index stay in sync across inserts, updates and deletes.

## How we will prove it works

We don't want to claim results we haven't measured, so evaluation is part of the design from day
one:

- **A "bug zoo"**: a reproducible set of small scripts that trigger common real Python errors
  (dependency and import problems, type and value errors, key and index errors, file paths,
  encodings, APIs removed in major version bumps, shape mismatches, timeouts...), each with a known
  fix. We run them through steb to build a realistic memory, then generate superficially
  different variants (other paths, line numbers, variable names) that must retrieve the original.
  This gives us exact ground truth. Target: about 150 evaluation questions.
- **An external set** from Stack Overflow duplicate links and GitHub issue -> fix PR pairs.
- **An unanswerable set** to test whether the agent abstains correctly.
- **Retrieval metrics**: Recall@1/3/5/10 and MRR, overall and per error category, with ablations:
  raw vs normalized text, BM25 vs dense vs hybrid vs hybrid + rerank.
- **Generation metrics**: faithfulness, citation precision, fix correctness against the reference
  fix (LLM-as-judge with a documented rubric, plus a hand-checked sample), abstention accuracy and
  latency.
- **A fine-tuning experiment**: we fine-tune a small open embedding model on (error variant,
  original error) pairs with hard negatives (same exception type, different cause). Train and test
  are split by bug, so variants of the same bug never appear on both sides. We compare it with the
  base model on held-out bugs.

Every number we report will come from a results file generated by a script and tagged with the
git commit and configuration it was produced with.

## How it maps to the course requirements

| Requirement | steb |
|---|---|
| R1 Document management (RAG, metadata, citations) | Error records with rich metadata; every answer cites records, commits or URLs |
| R2 Tool calling / MCP | MCP server with 5 tools (`search_past_errors`, `get_fix`, `record_error`, `link_fix`, `search_knowledge_base`) + demo client; used by our own agent and by Claude Code |
| R3 LangChain / LangGraph | Corrective, citation-verifying LangGraph agent |
| R4 Benchmarking | ~150 questions; retrieval and generation metrics; ablations |
| R5 Web interface | Streamlit app: Ask, Memory browser, Benchmark dashboard |
| R6 Ingestion pipeline with updates | Capture + external KB ingestion with redaction, dedup, incremental updates and deletes |
| R7 Fine-tuning vs baseline | Fine-tuned vs base embedding model on held-out bugs |

## Technology

Python, LangChain + LangGraph, the official MCP Python SDK, SQLite, a local vector store (Chroma or
Qdrant), BM25, sentence-transformers, Streamlit, Typer. The LLM provider is configurable: an API
provider by default, or a fully local model through Ollama for anyone who doesn't want their
error logs to leave their machine. It runs on Windows, macOS and Linux.

## Team and plan

| Member | Focus |
|---|---|
| Khaled | Capture and storage, normalization / fingerprinting / redaction, hybrid retrieval, LangGraph agent, MCP server |
| Haider | Bug zoo and evaluation datasets, external knowledge base ingestion, generation benchmark, embedding fine-tuning, web UI |

We will build it in ten small, tested phases, from capture and storage, through retrieval, the
agent and MCP, to benchmarks, fine-tuning and the UI. Every phase ends with passing tests and
updated documentation, and the git history will show the project growing one step at a time.

## In one sentence

**steb turns the fixes you've already made into an answer you can search, cite and check, for
you and for your coding agent.**
