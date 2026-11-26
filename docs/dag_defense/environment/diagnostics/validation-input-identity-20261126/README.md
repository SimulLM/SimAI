# Validation input identity preflight

The candidate collector now refuses repeated request IDs, input IDs or input hashes, mismatched run IDs, invalid wave/index mapping, unsupported concurrency and an output length other than 128. The existing per-file SHA-256 check remains. A local synthetic-service fixture passed success, HTTP failure, timeout and interrupted-record tests, and deliberately rehashed malformed inputs to verify semantic rejection independently of checksums. All 30 existing candidate input files also passed this check using a temporary synthetic freeze solely to exercise code. No formal freeze file was created and no validation requests were sent.

This is one collector safeguard, not a full readiness decision: the preflight cannot establish the truth of the compatibility evidence, verify actual server startup or warmup/idle state, or supply required GPU/KV events. Existing scheduling and non-overlapping fee issues remain open; formal validation is 0/30.
