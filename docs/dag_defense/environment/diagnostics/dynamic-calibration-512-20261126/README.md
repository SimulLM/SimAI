# Dynamic first-token grouping on two real calibration arrival sequences

CPU-only replay of two existing 32-request 512/64 calibration repetitions using their router arrival timestamps: serial-0 and requested-concurrency-2 concurrent-0. Compare untouched original, readiness-corrected dynamic-group modified baseline, and DAG with grouped-first-token candidate. The modified baseline and DAG use the same original predictor and candidate first-token fees: batch 1 0.875779 ms from independent 512/8 serial profile, batch 2 0.833501 ms from controlled 512/8 1P1D profile. Those synchronized host intervals include logits, sampler and synchronization and are approximated as exclusive decode tasks. Pristine lacks the consumer first-token task and is not a full same-fee comparator. This is calibration diagnosis, not validation or a production fee freeze.

| Calibration repeat | Pristine early memberships | Dynamic / DAG early memberships | Pristine paired / pristine total / DAG total | Dynamic paired / dynamic total / DAG total |
|---|---:|---:|---:|---:|
| serial-0 | 7 | 0 / 0 | 1754 / 1859 / 1851 | 1750 / 1860 / 1851 |
| concurrent-0 | 16 | 0 / 0 | 107 / 1025 / 1027 | 986 / 1033 / 1027 |

Early means a batch starts before the request's own modeled KV arrival, not an exact hardware KVReady timestamp. All versions have 63 later Decode iterations per request. Modified/DAG each charge exactly 32 batch-1 first-token tasks; each follows modeled ready and finishes before that request's Decode. All paired model batches match costs within 1 ns, but those claims do not extend to unmatched batches or the pristine missing first-token work. The dynamic-vs-DAG first Decode difference in serial-0 is position 51, [0] versus [0,1]; concurrent-0 position 258 is [7] versus [7,8]. These are descriptive ordering differences under the candidate rules, not proof of real execution or improvement. Two calibration repetitions are not the formal 30-round matrix.

Raw logs, input commands, first-token traces and model traces are in the hashed archive, with original-pristine outputs and actual arrival source preserved by `pristine-real-arrival-20261126`. No validation duration was used to tune cost; physical transfer/compute overlap and response completion boundary remain open. Formal validation remains 0/30.
