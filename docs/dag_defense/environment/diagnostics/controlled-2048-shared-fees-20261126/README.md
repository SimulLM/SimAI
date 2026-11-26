# Controlled 2048/128 candidate-fee comparison

CPU-only synthetic-arrival diagnostic applies one candidate fee table to a readiness-corrected, fixed-group, exclusive-decode-slot modified baseline and the original-predictor DAG with experimental first-token groups. Four traces contain one request, two 0.481173 ms apart, two simultaneous and four simultaneous. The baseline groups are explicitly fixed from a previous 2048/8 instrumented four-request wave, whereas the DAG selects groups naturally; neither baseline is the untouched original nor is this a fixed-batch comparison of every Decode step. First-token fees are host medians from that 8-output synchronized capture for actual batch 1/2; overlap and transfer occupancy remain assumptions. No validation completion times informed costs.

| Case | Fixed baseline first-token groups | DAG first-token groups | Paired model batches (baseline / DAG total) | First Decode difference |
|---|---|---|---|---|
| One | [0] | [0] | 128 / 128, 128 | None |
| Two staggered | [0], [1] | [0], [1] | 134 / 134, 134 | None |
| Two simultaneous | [0], [1] | [0,1] | 128 / 128, 128 | None |
| Four simultaneous | [0], [1,2], [3] | [0,1], [2,3] | 2 / 137, 137 | First batch: [0] versus [0,1] |

All eight processes exit 0; each request gets 127 later Decode steps after its first-token group and all modeled KV arrivals precede its group. All paired model batch fees agree below 1 ns; this does not include comparing first-token groups with different membership. For two simultaneous, two batch-1 first-token tasks cost 2.220687 ms in the fixed baseline, while one batch-2 task costs 1.115814 ms in DAG; these are different group shapes and must not be called equal total fees. For four, first groups similarly differ. In this diagnostic baseline assigns both first requests modeled KV-ready at 161.289 ms, whereas DAG serializes their transfers and has 161.289 and 196.685 ms, then groups both. The baseline group membership was fixed independently; scheduling and resource differences can explain different timing, but no causal claim about the real system follows. Natural service batch distributions, physical resource overlap and pristine first-token treatment remain unresolved.

The comparison is not formal validation or an accuracy result. Full commands, fee inputs, events, logs and exit codes are in the hashed archive; `audit.py` reproduces counts and validates 2048/128 lengths. Preserve modified and original results separately. Formal validation remains 0/30.
