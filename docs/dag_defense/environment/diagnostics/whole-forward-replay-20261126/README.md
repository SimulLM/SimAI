# Single-request whole-forward fee replay (diagnostic)

This is an isolated 512-input/64-output request replay. It replaces the 63 Decode layer-compute tasks with one measured whole-model forward cost per Decode step, using linear interpolation between independent batch-1 eager profiling anchors: 13.360992431640625 ms at context 512 and 13.24892807006836 ms at context 575. Prefill, receiver, first-token, CPU, sampler, and routing costs are unchanged.

Both the expanded DAG and predictor-adapted baseline completed with exit code 0. They produced identical request metrics: predicted E2E 0.939206706298157 s, model execution 0.860418735474348 s, and decode execution 0.915809692946856 s. The DAG and baseline each recorded 63 decode forward samples. This confirms the replacement is wired consistently for this diagnostic request; it is not a frozen fee, formal validation, or an accuracy result.

The first DAG attempt is retained at `/root/autodl-tmp/dag-handoff/runs/whole-forward-replay-20261126/dag-failed-attempt-1`; the successful raw outputs are under `/root/autodl-tmp/dag-handoff/runs/whole-forward-replay-20261126/{dag,baseline}`. The bootstrap is `/root/autodl-tmp/dag-handoff/runs/whole-forward-replay-20261126/bootstrap.py`. It enforces TP1, PP1, single-request batches, and the 512/64 shape; this does not by itself reject multiple sequential requests, and is not part of the default simulator path.

Source evidence: `serial-forward-interpolation-20261126/summary.json`, `pd-eager-profile-20261126/candidate/forward-cost.csv`, and the two request_metrics.csv files in the raw run. The measured hooks and interpolation remain diagnostic and require the single-request boundary, concurrent mechanism checks, and independent fee freeze before formal validation.

Graph audit: 64 stage graphs contain one Prefill graph with 96 layer tasks and 63 Decode graphs each with exactly one whole_forward task and no layer tasks. Both predictor traces contain contexts 513 through 575 and equal aggregate forward cost 838.156463623 ms. Batch guards alone do not prove global single-request input; the selected replay trace contains one request.
