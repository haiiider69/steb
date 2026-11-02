# eval/

Benchmarks for steb (requirement R4). Planned contents:

- `bug_zoo/` — reproducible small scripts that trigger common real errors, each with a pinned
  version and a reference fix. Run through `steb run` to build a realistic personal memory.
- `datasets/` — frozen evaluation datasets (query variants, external pairs, unanswerable set).
  Tracked in git.
- `scripts/` — benchmark runners for retrieval (Recall@k, MRR, ablations) and generation
  (faithfulness, citation precision, fix correctness, abstention, latency).
- `results/` — results files produced by the scripts, each logged with the git commit hash and
  config. Tracked in git. **Every number in the report must come from a file here.**
