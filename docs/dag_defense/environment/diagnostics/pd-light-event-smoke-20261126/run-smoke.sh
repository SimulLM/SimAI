#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/pd-light-event-smoke-20261126
mkdir "$base" || exit 1
export PD_ROUTE_DIR="$base/service"
bash /root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/scripts/start-pd-light-events.sh > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader > "$base/gpu-after.csv" 2>&1 || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 200); do
 kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit"; exit 91; }
 test -f "$PD_ROUTE_DIR/ready" && break
 sleep 2
done
test -f "$PD_ROUTE_DIR/ready" || { echo 92 > "$base/exit"; exit 92; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/dag-handoff/scripts/correlation-smoke-client.py "$base/request.json" > "$base/client.log" 2>&1
code=$?; echo "$code" > "$base/exit"; exit "$code"
