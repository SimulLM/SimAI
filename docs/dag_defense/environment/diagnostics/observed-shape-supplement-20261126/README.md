# Candidate replay coverage with existing supplements

Re-runs the sibling `observed-shape-coverage-20261126` audit over the same saved synthetic traces, adding the independently measured `uniform-forward-targeted-20261126/candidate-context-bins.csv` (which includes single-GPU uniform batch-four) and `mixed-span-nine-20261126/coverage.csv` exact-pattern table. All input, trace and lookup hashes, reconstructed batch rows and the six reconstruction cross-checks are retained in summary.json and batches.csv. This is a retrospective lookup audit: it does not re-simulate with the newer fees, and the actual final scheduling can change. The single-GPU and synchronized PD sources have different environments, so lookup availability is not proof of a valid common physical end-to-end fee.

| Input / wave | Adapted baseline decode covered / total | DAG decode covered / total |
|---|---:|---:|
| 1024 / 1 | 127/127 | 127/127 |
| 1024 / 2 | 127/127 | 2/128 |
| 1024 / 4 | 127/127 | 128/128 |
| 2048 / 1 | 127/127 | 127/127 |
| 2048 / 2 | 127/127 | 128/128 |
| 2048 / 4 | 16/135 | 19/137 |

The supplemental uniform measurements cover the formerly missing uniform 1024 batch 4 and 2048 batch 2 in these saved traces. Eight missing 1024 batch-two mixed bins remain for the DAG. Eight 2048 batch-four exact-pattern bins with span 8 remain for the adapted baseline, and nine keys for the DAG include pattern [0,0,9,10]. Existing exact [0,0,9,9] measurements cannot be treated as the other patterns without a justified composition model. Previously completed strict replay with changed fees produced a different [0,0,9,9] schedule, illustrating why these counts cannot be assumed to predict the next replay. No formal runs or new GPU measurements occurred.

Reproduce: `/root/autodl-tmp/venvs/vllm-0.8.5/bin/python docs/dag_defense/environment/diagnostics/observed-shape-supplement-20261126/analyze.py`. The next useful action is to check independent 1024 mixed batch-two and 2048 mixed-pattern profiles for their exact qualifying coverage, then choose explicit scoped interpolation or a targeted profile; reject unsupported keys during final replay. Separate first-token, transfer and overlap boundaries remain open.
