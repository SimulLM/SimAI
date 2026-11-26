#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/isolated-first-instrumented-20261126
mkdir "$base" || exit 1
export COMPUTE_DIAG_DIR="$base/service"
bash /root/autodl-tmp/dag-handoff/scripts/start-pd-kv-ready.sh > "$base/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; if test -f "$COMPUTE_DIAG_DIR/pids"; then xargs -r kill < "$COMPUTE_DIAG_DIR/pids" 2>/dev/null || :; fi; nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader > "$base/gpu-after.csv" 2>&1 || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 200); do
 kill -0 "$server" 2>/dev/null || { echo 91 > "$base/exit"; exit 91; }
 curl -sf http://127.0.0.1:8100/v1/models >/dev/null && curl -sf http://127.0.0.1:8200/v1/models >/dev/null && curl -s -o /dev/null http://127.0.0.1:18300/ && break
 sleep 2
done
input=/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/isolated-calibration-first-20261126/real-request.json
for stage in warmup measured; do
 /root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/dag-handoff/scripts/isolated-first-instrumented-client.py "$base/$stage.json" "$input" > "$base/$stage.log" 2>&1
 code=$?; if test "$code" -ne 0; then echo "$code" > "$base/exit"; exit "$code"; fi
done
echo 0 > "$base/exit"
