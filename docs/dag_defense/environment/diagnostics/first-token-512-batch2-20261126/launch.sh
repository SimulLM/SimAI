#!/bin/bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/first-token-512-batch2-20261126
export COMPUTE_DIAG_DIR="$base"
bash "$base/service.sh" > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader > "$base/gpu-immediate.csv"; }
trap cleanup EXIT INT TERM
for i in $(seq 1 200); do kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit";exit 91; }; if curl -sf http://127.0.0.1:8100/v1/models >/dev/null && curl -sf http://127.0.0.1:8200/v1/models >/dev/null && curl -s http://127.0.0.1:18300/ >/dev/null 2>&1;then break;fi; sleep 2; done
# Quart returns 404 at /; readiness of listening proxy is checked by its HTTP status.
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-kv-ready-bound-20261126/pd-mapped-forward-client.py --run-dir "$base/coverage" --warmups 12 --samples 30 --lengths 512 --batches 2 --timeout 120 --out-tokens 8 > "$base/client.log" 2>&1
code=$?;echo "$code" > "$base/exit";exit "$code"
