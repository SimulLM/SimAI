# H800 hardware profile v5

This candidate keeps v4 phase/context-aware compute prediction and replaces the wall-clock sampler field with the independently measured CUDA-synchronized sampler boundary. The synchronized run is diagnostic and must not be treated as E2E performance. It is used to avoid charging GPU wait twice.
