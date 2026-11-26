# Isolated request: candidate event and fee ledger

This ledger is generated from every task in the isolated first 512/64 calibration replay. The full individual task table with units and evidence is retained in `isolated-calibration-first-20261126/dag-cost-breakdown.csv`. `task-cost-sums.csv` is a work sum by stage and operation, not necessarily a wall-clock breakdown.

| Item | Existing candidate assignment | Measurement and open boundary |
|---|---|---|
| Producer Prefill | 32 attention and 32 MLP layer costs, CPU prepare and finish once | Independently profiled CUDA layer components plus host CPU profile; layer-only timings exclude unmodeled head work. CPU sampler host call may contain GPU waiting. |
| KV transfer | One 0.007858456 s effective transfer for 513-token billing at 255 Gibit/s | Independent PyNccl microbenchmark includes KV, hidden, matching/control and synchronization through receive but not paged-KV installation. Reported KV-only byte count is not total actual payload. |
| Consumer first token after KV installation | No separate task in this candidate | Real consumer runs a KV-bypass prompt-shaped step with logits and sampling. Independent synchronized serial 512-token post-KV host interval median 0.875779 ms includes CPU, GPU work and waiting. Its CUDA subintervals overlap it. No consumer first-token fee can be asserted as independently covered by the existing 63 Decode tasks. |
| Subsequent Decode | 63 iterations, each with 32 attention, 32 MLP, CPU prepare and finish tasks | This agrees with the 63 later real model steps by count, but matching count alone does not establish timing, context, scheduling or token equivalence. |
| Request completion | Simulator ends at final modeled batch completion | Real streaming router completion is after the response stream is forwarded; it is not a GPU kernel-completion timestamp. Router/protocol overhead is not independently charged. |

Task costs come from shared candidate profiles in the diagnostic adapted-baseline/DAG replay. Earlier matched batch audit found agreement for identical observed batch keys, but unmatched batches and consumer first-token semantics remain open. The effective bandwidth already folds in hidden transfer; adding hidden bytes again at the same fitted bandwidth double counts. Measured sampler host time can wait on GPU and must not be added blindly to GPU sampler time. No fees were adjusted from real request total duration; no freeze or formal validation was performed.
