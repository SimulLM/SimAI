# Synchronized sampler arrival replay

This 32-request serial replay uses the recorded calibration `server_arrival` and `server_complete` events. The v5 profile replaces wall-clock sampler timing with the independent CUDA-synchronized sampler diagnostic to avoid charging GPU wait twice.

Actual median service time: 0.841792883 s. DAG predicted median: 1.1291809507 s, median relative error 34.08%. Baseline predicted median: 1.1194572624 s, median relative error 33.00%. The common residual error keeps parameter freeze and formal validation blocked.
