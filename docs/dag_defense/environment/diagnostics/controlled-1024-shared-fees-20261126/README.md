# Controlled 1024/128 first-token fee comparison

CPU-only diagnostics compare a fixed-group, readiness-corrected and decode-slot-reserving baseline with the original-predictor DAG plus experimental grouped-first-token task. Four synthetic input traces exercise one request, two 0.481173 ms apart, two simultaneous and four simultaneous. The stagger amount came from a prior measured calibration arrival pair; the resulting traces are synthetic, not full validation or an unchanged original. The same underlying predictor and explicit measured-candidate first-token fee table are used; the 1024 batch-two stratum has only seven warmup waves. The fixed baseline group membership is preset, while DAG chooses its own. Source GPU occupancy, transfer wait and actual physical overlap remain hypotheses.

| Case | Baseline / DAG exits | Baseline / DAG batches | Paired batches | First Decode difference |
|---|---|---|---|---|
| One | 0 / 0 | 128 / 128 | 128 | None |
| Two staggered | 0 / 0 | 132 / 132 | 132 | None |
| Two simultaneous | 0 / 0 | 128 / 128 | 128 | None |
| Four simultaneous | 0 / 1 | Baseline completed; DAG stopped | unavailable | DAG requested unmeasured first-token batch 4 |

All completed cases charge each group once, have modeled KV-ready no later than first-token submission, first-token completion before member Decode and exactly 127 later Decode steps per request. Matched batch costs differ by less than 1 ns. The baseline four-request fixed groups [0],[1,2,3] completed, but DAG selected four together and rejected the missing `1024:4` fee; no output from that failed run is treated as complete. A batch-3 measurement cannot be silently used for batch 4. These are local fixed-group/diagnostic observations, not a claim that all natural-scheduling costs or batches match. Model compute and transfer overlap, original baseline first-token stage, 2048 configurations, and server completion boundary remain open.

Source commands, each exit, complete and failed logs and partial DAG output are in the hashed raw server archive; audit.py reproduces the counts against those runs. The next direct action is to obtain an independently measured actual batch-four post-KV first-token fee or choose and document a justified bounded cost model, then rerun the four-request check without replacing original failure. Do not use validation completion times to choose this fee. Formal validation remains 0/30.
