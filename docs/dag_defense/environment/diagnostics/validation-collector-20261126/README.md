# Validation collector prototype checkpoint

The fixture uses a synthetic localhost service solely to test collector and reconciliation software; it is not measurement, calibration, or validation. The fixture covers successful streams, HTTP failure, timeout, duplicate server events, missing client records after interruption, missing freeze, and changed frozen artifacts. On failure or timeout, further waves are not submitted because server idleness is unknown. The reconciler preserves missing and unsuccessful requests and checks router monotonic event sequence and ID/usage consistency.

No parameter freeze exists and no formal validation requests have been run. Preflight verifies named artifact hashes but cannot establish the truth or sufficiency of claimed compatibility evidence. Actual service startup arguments, clock assumptions, GPU/service idle state, warmup, and run orchestration still require independent verification. A successful reconciliation alone is not an acceptance result. The router's first-token event is based on streaming usage and must be validated against actual service behavior. Semantics of KV pull, scheduling, and non-overlapping costs remain unresolved.

Run the isolated fixture with `/root/autodl-tmp/venvs/vllm-0.8.5/bin/python scripts/dag_defense/test_collect_validation_run.py`.
