# finetune/

Embedding fine-tuning experiment (requirement R7, Phase 8). Planned contents:

- data preparation: (error variant, original error / solution) pairs with hard negatives
  (same exception type, different cause), split train/test by fingerprint cluster;
- training with sentence-transformers on a small open embedding model;
- comparison against the base model with the same retrieval metrics as `eval/`.

Model checkpoints go to `finetune/outputs/` (gitignored).
