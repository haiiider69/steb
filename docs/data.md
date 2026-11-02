# Data sources and licenses

Raw data is never committed. Only download / prepare scripts are tracked; their output goes to
`data/raw/` and `data/processed/` (gitignored). Availability and licenses must be verified before
downloading, and recorded here.

| Source | What we use | How obtained | License / terms | Attribution | Status |
|---|---|---|---|---|---|
| Bug zoo (ours) | Small scripts triggering real errors + reference fixes | `eval/bug_zoo/` | Same as this repo | — | planned (Phase 2) |
| Stack Overflow / Stack Exchange | Python-tagged Q&A subset + duplicate-question links | _TBD: verify a currently legitimate access route_ | CC BY-SA (version depends on post date) | Required: link to post + author | to verify (Phase 3) |
| GitHub issues | Issues with stack traces + linked fix PRs from a few popular Python libraries | GitHub REST/GraphQL API | Per-repository license; GitHub Terms of Service | Link to issue / PR | to verify (Phase 3) |

## Notes

- Everything ingested passes through secret redaction before storage or embedding.
- Each stored external record keeps its source URL, author (where required), and license so that
  answers can cite and attribute it.
