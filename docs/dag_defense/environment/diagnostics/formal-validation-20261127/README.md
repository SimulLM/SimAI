# Formal collection backup and replay progress

All 30 formal rounds and 960 requests completed collection and reconciliation. Both GPUs have no compute processes and zero memory usage. Remaining work is CPU replay, scoring and evidence export. GPU allocation is unnecessary for that work; the current host is still needed while its CPU process is running, until computation is migrated or paused with its state preserved.

The committed CSVs contain completed formal replay scores for the first two rounds, with original, fee-adapted reference and DAG columns. This is not the full 30-round scoring report. `score-summary.json` / `result.json` reuse historical `preacceptance_not_validation` labels from the frozen helper; these directories are formal data identified by the frozen input manifest and matrix run IDs. Do not treat those helper labels as a reclassification of these held-out requests.

Raw collection archive contains all 30 measured inputs/client/router/worker data, warmup and idle records, frozen manifest and captured collection/replay status. In-progress prediction outputs are deliberately excluded from this immutable raw-data backup; completed scores are committed separately. Archive SHA256: d82eaeb8a27d22fea05c4e558381ab13726e1778cc3ce09df9532fcfbc09f966. Release location is recorded in release.json after verified upload.
