#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/output-processing-boundary-v2-20261126
mkdir "$base" || exit 1
export PD_ROUTE_DIR="$base/service"
bash /root/autodl-tmp/dag-handoff/scripts/start-pd-output-boundary.sh > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 200); do
 kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit"; exit 91; }
 test -f "$PD_ROUTE_DIR/ready" && break
 sleep 2
done
test -f "$PD_ROUTE_DIR/ready" || { echo 92 > "$base/exit"; exit 92; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/single_stream_timeline_client.py /root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/isolated-calibration-first-20261126/real-request.json "$base/client.json" > "$base/client.log" 2>&1
code=$?; echo "$code" > "$base/exit"; exit "$code"
