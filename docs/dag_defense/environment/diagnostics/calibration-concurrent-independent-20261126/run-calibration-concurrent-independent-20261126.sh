#!/usr/bin/env bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/calibration-concurrent-independent-20261126
mkdir "$base" || exit 1
server=''
monitor=''
cleanup(){ if [[ -n "$monitor" ]]; then kill "$monitor" 2>/dev/null || :; wait "$monitor" 2>/dev/null || :; monitor=''; fi; if [[ -n "$server" ]]; then kill "$server" 2>/dev/null || :; wait "$server" 2>/dev/null || :; fi; }
trap cleanup EXIT INT TERM
for rep in 0 1 2; do
 export PD_ROUTE_DIR="$base/server-$rep"
 bash /root/autodl-tmp/dag-handoff/scripts/start-pd-stream.sh > "$base/server-$rep-launch.log" 2>&1 & server=$!
 for i in $(seq 1 180); do
  kill -0 "$server" 2>/dev/null || { echo "server_died $rep" >> "$base/progress.log"; echo 91 > "$base/exit"; exit 91; }
  [[ -f "$PD_ROUTE_DIR/ready" ]] && break
  sleep 2
done
 [[ -f "$PD_ROUTE_DIR/ready" ]] || { echo 92 > "$base/exit"; exit 92; }
 nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader > "$base/server-$rep-resource-before.csv"
 nvidia-smi --query-gpu=timestamp,index,utilization.gpu,clocks.sm,clocks.mem,power.draw,temperature.gpu --format=csv -l 1 > "$base/server-$rep-telemetry.csv" 2>&1 & monitor=$!
 /root/autodl-tmp/venvs/vllm-0.8.5/bin/python /root/autodl-tmp/dag-handoff/scripts/calibration-concurrent-independent-20261126.py "$base/client-$rep" "$rep" > "$base/client-$rep.log" 2>&1; code=$?
 echo "repeat=$rep client_exit=$code" >> "$base/progress.log"
 if ((code)); then echo "$code" > "$base/exit"; exit "$code"; fi
 cleanup; server=''
 nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader > "$base/server-$rep-resource-after.csv"
done
echo 0 > "$base/exit"
