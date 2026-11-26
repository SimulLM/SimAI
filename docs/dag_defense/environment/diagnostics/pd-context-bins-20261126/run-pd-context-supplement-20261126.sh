#!/usr/bin/env bash
set -uo pipefail
export COMPUTE_DIAG_DIR=/root/autodl-tmp/dag-handoff/runs/pd-context-supplement-20261126
mkdir "$COMPUTE_DIAG_DIR" || exit 1
bash /root/autodl-tmp/dag-handoff/scripts/start-pd-flow.sh > "$COMPUTE_DIAG_DIR/launcher.log" 2>&1 & server=$!
cleanup(){ kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; }
trap cleanup EXIT INT TERM
for i in $(seq 1 150); do
 kill -0 "$server" 2>/dev/null || { echo 91 > "$COMPUTE_DIAG_DIR/exit"; exit 91; }
 if curl -sf http://127.0.0.1:8100/v1/models >/dev/null && curl -sf http://127.0.0.1:8200/v1/models >/dev/null && curl -s -o /dev/null http://127.0.0.1:18300/; then break; fi
 sleep 2
done
curl -sf http://127.0.0.1:8100/v1/models >/dev/null && curl -sf http://127.0.0.1:8200/v1/models >/dev/null && curl -s -o /dev/null http://127.0.0.1:18300/ || { echo 92 > "$COMPUTE_DIAG_DIR/exit"; exit 92; }
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/dag-handoff/scripts/pd-mapped-forward-client.py --run-dir "$COMPUTE_DIAG_DIR/client" --warmups 20 --samples 40 --lengths 1024 2048 --batches 2 4 --out-tokens 128 --timeout 120 > "$COMPUTE_DIAG_DIR/client.log" 2>&1
code=$?; echo "$code" > "$COMPUTE_DIAG_DIR/exit"; exit "$code"
