# H800 PD measurement handoff

Current acceptance state is **blocked before formal validation**. The server-side model, two-H800 environment, real vLLM 1P1D path, KVReady, NCCL route, concurrent KV sampled mapping, independent compute/host/KV profiles, and the complete 512/64 request calibration collection are archived in this tree. The pinned baseline and DAG functional regression suites pass, and an explicit TP1/PP1 zero-latency compatibility mode makes their synthetic PD transfer fees equal.

No formal validation request has been run. A parameter freeze and the required 30 runs × 32 requests cannot be signed yet because the real vLLM fused operations, RoPE, model-boundary work, CPU/GPU overlap, and service/router time boundary do not map one-to-one to the current predictor fields. The provisional communication candidate is documented separately and is not frozen. Do not claim an accuracy improvement or a completed 960-request experiment.

Read `acceptance-report.json`, then `environment/01-environment.md`, `environment/compatibility-20261126.json`, and the diagnostic/calibration directories. Evidence branch: `dev-h800-pd-measurement`.
