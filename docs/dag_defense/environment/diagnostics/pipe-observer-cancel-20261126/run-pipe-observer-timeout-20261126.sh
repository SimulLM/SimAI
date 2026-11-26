#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/pipe-observer-timeout-20261126
mkdir "$base" || exit 1
export PD_ROUTE_DIR="$base/service" PD_BUFFER_OBSERVER_DIR="$base/observer"
export PYTHONPATH="/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/scripts/pd-buffer-pipe-observer"
bash /root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/scripts/start-pd-pipe-observer.sh > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 200); do
 kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit"; exit 91; }
 test -f "$PD_ROUTE_DIR/ready" && break
 sleep 2
done
test -f "$PD_ROUTE_DIR/ready" || { echo 92 > "$base/exit"; exit 92; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/idle_timeout_diagnostic_client.py "$base/warmup.json" > "$base/warmup.log" 2>&1
code=$?; test "$code" -eq 0 || { echo "$code" > "$base/exit"; exit "$code"; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/SimAI-handoff/scripts/dag_defense/probe_pd_idle.py --output "$base/probe" --router-events "$PD_ROUTE_DIR/router-events.jsonl" --samples 4 --interval 5 > "$base/probe.log" 2>&1
code=$?; echo "$code" > "$base/probe-exit"; echo 0 > "$base/exit"
