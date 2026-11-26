> **Correction:** The previous calibration replays used 255 Gi-bit/s for DAG and the default 800 Gi-bit/s for baseline. They are not same-cost comparisons. The preliminary v8 profile also combined producer and consumer measurements; see `../pd-profile-wave-audit-20261126/README.md`. All figures here are exploratory and formal validation remains blocked.

# Aggregate model-step diagnostic (2026-11-26)

This is an independent diagnostic, not formal validation. A default vLLM V0 server used the same Llama-2-7b-hf FP16 model and H800 GPU configuration but did not use `--enforce-eager`. `ModelRunner.execute_model` was wrapped with an outer CUDA-event pair and one synchronization after the event. The raw JSONL is under `raw/`; `step-summary.csv` contains per-phase/context/batch medians. No request completion times were used to build the profile.

`profile-v6/` is a candidate profile that scales the prior per-operation profile so its aggregate GPU step equals the independent outer CUDA median for each measured shape. `replay-v6-direct2/` is an arrival replay diagnostic using exact profile rows where available and direct phase-aware attention/CPU lookups. It reduced the common bias versus the earlier profile but remains outside the acceptance tolerance; formal validation is still blocked. The replay was not used to fit the profile or fees.

The actual 32-request server-arrival reference is retained in the earlier v3 archive. The v6 diagnostic medians and the unchanged `formal_validation: false` status are in `replay-summary.json`.
