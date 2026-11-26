#!/bin/bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/fenced-idle-diagnostic-20261126
export PD_ROUTE_DIR="$base/service" PD_BUFFER_OBSERVER_DIR="$base/observer" PYTHONPATH=/root/autodl-tmp/dag-handoff/scripts/pd-signal-observer
bash /root/autodl-tmp/dag-handoff/scripts/fenced-idle-diagnostic-20261126/start.sh > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 200); do kill -0 "$server" 2>/dev/null || exit 91; test -f "$PD_ROUTE_DIR/ready" && break; sleep 2; done
test -f "$PD_ROUTE_DIR/ready" || exit 92
python=/root/autodl-tmp/venvs/vllm-0.8.5/bin/python
"$python" /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/idle_concurrent_warmup.py "$base/warmup.json" > "$base/warmup.log" 2>&1 || exit 93
: > "$PD_ROUTE_DIR/admission-fence"
status=$(curl -s -o "$base/fence-response.json" -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"stream":true}' http://127.0.0.1:18300/v1/completions)
test "$status" = 503 || exit 94
"$python" /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/request_worker_idle_sync.py --observer "$base/observer" --output "$base/sync-before.json" > "$base/sync-before.log" 2>&1 || exit 95
nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader,nounits > "$base/gpu-processes-before.csv" || exit 96
"$python" /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/probe_pd_idle.py --output "$base/probe" --router-events "$PD_ROUTE_DIR/router-events.jsonl" --samples 4 --interval 5 > "$base/probe.log" 2>&1
code=$?; echo "$code" > "$base/probe-exit"; test "$code" = 2 || exit 97
rm -f "$base/observer/sync-request.json"
"$python" /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/request_worker_idle_sync.py --observer "$base/observer" --output "$base/sync-after.json" > "$base/sync-after.log" 2>&1 || exit 98
nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader,nounits > "$base/gpu-processes-after.csv" || exit 99
