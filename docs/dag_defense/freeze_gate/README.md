# Freeze blocker register

The sole current register is `blockers.json`. The four entries distinguish required experimental validity from reportable limitations. A gate may be marked closed only after its concrete `close_when` evidence is present and reviewed; the preflight additionally checks artifacts, model identity, baseline and the complete input matrix. The register does not require near-zero error, DAG improvement, or automatic reopen after failure. On failure or timeout, preserve the failed attempt, stop the round, restart or clean the service, and verify idle before continuing; preserve all retry links.

The real original baseline and the diagnostic corrected baseline must be labelled separately. Any cost change after validation makes those results diagnostic and requires a newly frozen independent validation batch. The preflight is conservative and cannot alone certify a live idle service or scientific validity of cost scopes. Formal validation remains 0/30.
