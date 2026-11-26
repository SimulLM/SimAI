#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/token-latency-diagnostic-20261126
mkdir "$base" || exit 1
export PD_ROUTE_DIR="$base/server"
server='';monitor=''
cleanup(){ if [[ -n "$monitor" ]];then kill "$monitor" 2>/dev/null || :;wait "$monitor" 2>/dev/null || :;fi; if [[ -n "$server" ]];then kill "$server" 2>/dev/null || :;wait "$server" 2>/dev/null || :;fi; }
trap cleanup EXIT INT TERM
bash /root/autodl-tmp/dag-handoff/scripts/start-pd-stream.sh > "$base/server-launch.log" 2>&1 & server=$!
for i in $(seq 1 180); do kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit";exit 91; }; [[ -f "$PD_ROUTE_DIR/ready" ]] && break; sleep 2; done
[[ -f "$PD_ROUTE_DIR/ready" ]] || { echo 92 > "$base/exit";exit 92; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/dag-handoff/scripts/monitor-calibration-resources-20261126.py "$base/resources.jsonl" > "$base/monitor.log" 2>&1 & monitor=$!
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/dag-handoff/scripts/diagnose-token-latency-20261126.py "$base/client" > "$base/client.log" 2>&1; code=$?
cleanup;server='';monitor='';nvidia-smi --query-gpu=index,memory.used --format=csv,noheader > "$base/resource-after.csv";echo "$code" > "$base/exit";exit "$code"
