# H800 hardware profile v3

This candidate profile was generated from archived independent vLLM CUDA-event, attention, and host-call samples on the two-H800 server. It is independent of request completion times. The mapping contract folds RoPE into the pre-projection bucket, maps the combined FlashAttention/KV interval to the phase-specific attention bucket, keeps cache-save at zero to avoid double counting, and keeps sampler host timing as an inclusive model-boundary bucket. CPU rows retain phase, input context, and batch size.

This is a diagnostic candidate, not a formal accuracy claim. Router/frontend/IPC overhead and non-KV PD payloads remain outside the profile. Source paths and hashes are recorded in `profile-manifest.json`; raw samples remain under `/root/autodl-tmp/dag-handoff/runs/`.
