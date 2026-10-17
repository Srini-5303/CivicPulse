# Evals

Run with `uv run python -m evals.run <suite> [--sample N]`. Results go to `evals/results/<suite>-<date>.json`.

| Suite | Dataset | Metrics | CI gate |
|---|---|---|---|
| triage | 1,000 historical Boston 311 records with real labels | Category and department accuracy, cost per complaint by tier | No drop > 2 points vs baseline |
| dedupe | 300 hand-labeled complaint pairs | Precision, recall | No drop > 2 points |
| hotspot | Replayed historical days with known incidents | Detection rate, minutes to detect | No drop > 2 points |
| rag | 50 questions with expected chunk IDs | Recall@5, MRR | No drop > 2 points |
| drafting | 50 incidents | Ragas faithfulness, uncited-commitment rate | No drop > 2 points |
| redaction | 500 drafts with Faker-seeded PII, contextual identifiers, and person-like street names | Recall, precision, address generalization accuracy | Recall >= 0.98 |
| e2e | 20 replayed incidents | p95 latency per stage, tokens and cost per incident | Report only |

- Baselines live in `evals/baseline.json`; change them only in a commit that explains why.
- PRs run `--sample 50`; full suites run nightly.
- Datasets are JSONL in `evals/datasets/`. Never commit real personal data.
