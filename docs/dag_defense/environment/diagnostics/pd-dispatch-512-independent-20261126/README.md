# Independent 512-token dispatch-boundary diagnostic

On the new dual-H800 server, an instrumented vLLM eager FP16 TP1 1P1D run used 512 input and eight output tokens, serial concurrency 1, 10 warmup and 30 measured requests. All 40 completed with expected token counts and unique backend mappings; the launcher exited 0 and both GPUs were released. The audit joins producer and consumer model-step IDs to router records and checks host timestamp ordering.

The median host interval from producer after-sync to consumer step start was 5.5387335 ms (range 4.749023–7.046085 ms, nearest-rank p95 6.934878 ms). This includes router processing and consumer scheduling and is affected by synchronization/instrumentation. It is not an isolated CPU fee, a GPU completion timestamp, or proof that the same delay holds under concurrency or 64/128 output tokens. It is used only for a separately labelled sensitivity replay; no validation data or response completion times were used to fit it.

Per-request IDs, raw source hashes and timings are in `requests.csv` and `summary.json`. Reproduce the audit using `scripts/dag_defense/audit_dispatch_512.py` against the archived run. The archive named by `raw-archive-sha256.txt` contains service logs, requests, raw events, scripts, exit codes and the independent-wave replay. Costs remain unfrozen; formal validation is 0/30.
