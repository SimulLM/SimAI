# 2048/128 controlled three-way readiness and batch comparison

The same four synthetic arrival traces from `controlled-2048-shared-fees-20261126` are replayed with untouched original SimAI `cef83f9ddd96540e3e9f48934f11335d52d54fce`; its tracked worktree is checked clean at audit time. Those results are compared separately with the readiness-corrected fixed-group modified baseline and experimental DAG. The last two use first-token group fees; pristine does not implement that consumer stage and is not a full same-fee comparison. All runs use identical underlying original predictor inputs and transfer rate. This is CPU-only mechanics diagnosis, not real-arrival replay or formal validation.

| 2048/128 case | Pristine early memberships | Fixed / DAG early memberships | Pristine paired with DAG | Fixed paired with DAG |
|---|---:|---:|---:|---:|
| One | 0 | 0 / 0 | 128/128 vs 128 | 128/128 vs 128 |
| Two staggered | 1 | 0 / 0 | 10/133 vs 134 | 134/134 vs 134 |
| Two simultaneous | 0 | 0 / 0 | 128/128 vs 128 | 128/128 vs 128 |
| Four simultaneous | 4 | 0 / 0 | 14/135 vs 137 | 2/137 vs 137 |

An early membership means a Decode batch starts before that same request's own **modeled** `decode_arrived_at`; this is not an exact hardware KVReady assertion. Every version produces 127 later Decode steps per request. All paired model batch costs differ by less than 1 ns, but unmatched batches and the pristine missing first-token task are outside that assertion. In the four-request case, pristine's first Decode membership difference is positional step 6: pristine [0,1,2,3] versus DAG [0,1], with the former containing requests 2 and 3 before their own modeled arrival. Fixed baseline and DAG instead differ at their first Decode: fixed [0], DAG [0,1], following deliberately different first-token grouping and transfer scheduling; this is not a clean test of only one change. The original-predictor two-request readiness-only reproduction remains separately documented in `early-batch-minimal-20261126`.

Raw command lines, output metrics, execution traces and logs for pristine are in the hashed archive here; modified/DAG runs are in the sibling `controlled-2048-shared-fees-20261126` archive. `audit.py` verifies source commit, tracked diffs, counts, early memberships, batch pair cost and first Decode difference; candidate hashes identify each trace. It does not establish real event equivalence, natural 32-request batch distribution, model validity or zero prediction error. Formal validation remains 0/30.
