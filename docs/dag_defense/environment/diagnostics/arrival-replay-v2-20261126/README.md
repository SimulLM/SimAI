# Calibration server-arrival replay

This diagnostic replay uses 32 serial calibration requests and the recorded router `server_arrival` and `server_complete` events from `CLOCK_MONOTONIC`. It does not use client send times and it is not part of the 960-request validation.

Both baseline and DAG completed the replay. The actual service metric `server_complete - server_arrival` has median 0.841792883 s. DAG predicted median is 1.1584884924 s (median relative error 37.59%); baseline predicted median is 1.1540151995 s (37.00%). This discrepancy is evidence that the current inclusive CPU/model-boundary profile and service boundary are not yet valid for a frozen accuracy comparison. Keep the acceptance state blocked; do not infer a DAG improvement.

The raw simulator logs are compressed here and the full uncompressed logs remain under `/root/autodl-tmp/dag-handoff/runs/arrival-replay-v2-20261126/`.
