# H800 hardware profile v4

This candidate uses the same independent vLLM samples as v3, but retains phase and input context in the compute profile and queries the fitted predictor with the current batch context. This prevents decode contexts from colliding on a batch-token-only key. Full DAG regression after this change: 357 passed. The profile remains diagnostic; calibration arrival replay still shows about 37% common overprediction, so no formal validation was started.
