# Independent calibration phase variability

This reanalyzes the 192 measured 512-input/64-output real eager PD calibration requests from the three separately restarted serial and three two-concurrent repeats; no new requests were run. Router event IDs join arrival, prefill response, decode submission, first streamed token and stream completion. All 192 rows mapped without errors; raw request, service and router records are in the sibling calibration-serial-independent-20261126 and calibration-concurrent-independent-20261126 evidence.

Median host intervals in milliseconds by repeat are:

| Mode | Repeat | Server E2E | Prefill response | Decode submit to first token | First token to completion |
|---|---:|---:|---:|---:|---:|
| Serial | 0 | 1033.8 | 28.5 | 14.9 | 984.7 |
| Serial | 1 | 899.2 | 29.1 | 15.0 | 854.6 |
| Serial | 2 | 862.4 | 28.7 | 15.2 | 818.3 |
| Concurrent 2 | 0 | 1156.5 | 46.7 | 26.2 | 1079.0 |
| Concurrent 2 | 1 | 898.0 | 45.9 | 26.1 | 826.3 |
| Concurrent 2 | 2 | 1299.2 | 46.9 | 29.3 | 1220.7 |

These are medians of individual intervals, which do not generally sum to the median E2E. Most between-repeat difference is visible after the first streamed token. This interval includes subsequent Decode, output handling, routing and waiting; it cannot locate the cause within GPU, CPU or stream processing. Inputs differ per repeat. One-second GPU telemetry from concurrent runs was not directly joined to request monotonic time and cannot establish causal correlation. No outliers removed, no fees fitted to validation. Formal validation remains 0/30 and timing/fee compatibility is unresolved.
