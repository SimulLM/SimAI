#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/logits-2048-128-20261126
mkdir "$base" || exit 1
export COMPUTE_DIAG_DIR="$base/service"
bash /root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-accounting-20261126/start-pd-accounting.sh > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 240); do
 kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit"; exit 91; }
 if curl -sf http://127.0.0.1:8100/v1/models >/dev/null && curl -sf http://127.0.0.1:8200/v1/models >/dev/null && curl -s -o /dev/null http://127.0.0.1:18300/; then break; fi
 sleep 2
done
curl -s -o /dev/null http://127.0.0.1:18300/ || { echo 92 > "$base/exit"; exit 92; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-accounting-20261126/pd-mapped-forward-client.py --run-dir "$base/client" --warmups 10 --samples 30 --lengths 2048 --batches 4 --out-tokens 128 --timeout 180 > "$base/client.log" 2>&1
code=$?; echo "$code" > "$base/exit"; exit "$code"
