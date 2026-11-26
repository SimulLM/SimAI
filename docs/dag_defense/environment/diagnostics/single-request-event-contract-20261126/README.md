# Single-request actual and simulated event contract

Reuses the first measured 512/64 serial request from `serial-prefix-comparison-20261126` and `first-last-output-boundary-20261126`, joined by router ID. The independent candidate DAG replay is `whole-forward-replay-20261126`, which uses the same selected input and a measured-forward sensitivity cost; it is not pristine SimAI or frozen. `audit.json` records actual CLOCK_MONOTONIC nanosecond timestamps reconstructed from original joined prefix offsets and the same request's first worker timestamp, plus simulation elapsed seconds, source hashes and event ordering. The original timestamps are not placed in the simulator clock domain. Historical detailed observations are host events, not GPU completion times.

| Event | Real time from router arrival (ms) | Simulated time from arrival (ms) | Interpretation |
|---|---:|---:|---|
| Prefill response / modeled Prefill end | 27.942 | 23.397 | Different endpoint scopes; worker and router steps differ |
| Decode worker start / modeled transfer start | 30.819 | 23.397 | Real consumer enters its first step before asking for KV; simulated transfer starts at Prefill end |
| Receive API start / modeled KVReady | 30.926 | 35.955 | Different events; neither host receive start nor API return is exact GPU KVReady |
| First consumer step return / modeled first-token task end | 41.001 | 36.830 | Candidate host and modeled boundaries, not GPU-equivalent timestamps |
| Router first token | 41.763 | no equivalent stream event | Producer's sampled token is not the router's streamed token |
| Last worker return / modeled last batch end | 854.655 | 939.207 | 63 later Decode steps after consumer first step; different costs and scopes |
| Router stream completion | 855.579 | no equivalent event | Includes output/stream tail; not proof client received bytes |

The real first-token-to-router and final-worker-to-choice intervals are measured in the linked 20-request one-session audit, while final-choice-to-stream completion for this request is 0.188 ms. These observations are not isolated additive cost and do not establish exact production bounds. Do not interpret the numerical end-time difference as one fee or tune fees against it. Both paths have one consumer first step plus 63 subsequent Decode batches, but the untouched original lacks the separately modeled consumer-first-token task and must remain a distinct reference.

This closes the explicit single-request event inventory, not the overall timing gate: the simulator does not model the router stream completion boundary, and communication start and GPU ready remain unaligned. Any final scoring contract must state those differences and whether the residual is a disclosed limitation or has independently justified non-overlapping treatment. Validate under actual service arrivals and preserve uncertainty; a near-zero prediction error or DAG improvement is not a gate. No formal validation was run. Reproduce via `/root/autodl-tmp/venvs/simai-simulator/bin/python docs/dag_defense/environment/diagnostics/single-request-event-contract-20261126/audit.py` with the recorded source paths.
