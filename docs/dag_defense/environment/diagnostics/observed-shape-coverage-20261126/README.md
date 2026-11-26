# Candidate replay observed shape coverage

CPU-only reanalysis of previously completed synthetic simultaneous-arrival replays `common-cost-matrix-v2-20261126` for input 1024/2048 and wave 1/2/4, output 128. It applies the strict full-forward lookup to reconstructed batch shapes in both predictor-adapted baseline and DAG; it does not run inference or validation, and does not establish the final schedule. Synthetic input CSV, trace and cost table SHA256s are in summary.json; each batch and missing key is in batches.csv. Context reconstruction uses input length + 1 + the number of prior consumer batches containing each request; it matches all 768 adapter-recorded batches across six independent completed strict-forward trace files, but those cover only single and two requests. The synthetic runs use earlier candidate costs and change if the eventual cost model changes. Counts must not be treated as coverage of actual validation arrivals.

| Input / wave | Baseline decode covered / total | DAG decode covered / total |
|---|---:|---:|
| 1024 / 1 | 127/127 | 127/127 |
| 1024 / 2 | 127/127 | 2/128 |
| 1024 / 4 | 0/127 | 128/128 |
| 2048 / 1 | 127/127 | 127/127 |
| 2048 / 2 | 15/127 | 128/128 |
| 2048 / 4 | 8/135 | 19/137 |

All synthetic prefill lookups were covered. Every synthetic request has 127 later decode batches under this reconstruction. The uneven coverage reflects different candidate scheduling and context composition, not evidence either implementation is more accurate. In particular 1024/4 uniform and 1024/2 mixed-context bins lack strict samples, and 2048/4 mixed gaps include distinct context patterns. The legacy common-cost replay's fees and concurrent receive/first-token ownership are still not established as physical or final. Later actual arrival traces may generate other shapes; strict lookup must remain fail-closed. Avoid fitting to validation completion times, zero-filling or treating these counts as measured accuracy.

Reproduce on server: `/root/autodl-tmp/venvs/vllm-0.8.5/bin/python docs/dag_defense/environment/diagnostics/observed-shape-coverage-20261126/analyze.py`. Raw original traces remain in the previously hashed common-cost-matrix archive, and individual reconstructed source hashes are recorded. Formal validation remains 0/30.
