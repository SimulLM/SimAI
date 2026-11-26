#!/bin/bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/controlled-batches-20261126
for x in staggered2 simultaneous2 simultaneous4; do
 cd "$base/$x" || exit 1
 /root/autodl-tmp/venvs/simai-simulator/bin/python run.py > run.log 2>&1
 code=$?; echo "$code" > run.exit
 if [ "$code" -ne 0 ]; then exit "$code"; fi
 /root/autodl-tmp/venvs/simai-simulator/bin/python audit.py > audit.log 2>&1
 code=$?; echo "$code" > audit.exit
 if [ "$code" -ne 0 ]; then exit "$code"; fi
done
