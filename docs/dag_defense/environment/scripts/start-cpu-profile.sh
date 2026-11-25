#!/usr/bin/env bash
set -euo pipefail
root=/root/autodl-tmp
run=${CPU_DIAG_DIR:?Set a new run directory}
mkdir "$run"
export PATH="$root/venvs/vllm-0.8.5/bin:$PATH" HF_HOME="$root/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_NO_USAGE_STATS=1 VLLM_USE_V1=0 CUDA_VISIBLE_DEVICES=0
export CPU_DIAG=1 PYTHONPATH="$root/dag-handoff/scripts/cpu-profile-instrument"
vllm serve "$root/models/Llama-2-7b-hf" --host 127.0.0.1 --port 18300 --dtype float16 --tensor-parallel-size 1 --max-model-len 4096 --max-num-seqs 4 --max-num-batched-tokens 4096 --gpu-memory-utilization 0.65 --enforce-eager --no-enable-prefix-caching --no-enable-chunked-prefill --generation-config vllm --disable-log-requests > "$run/server.log" 2>&1 & pid=$!
echo "$pid" > "$run/server.pid"
cleanup(){ kill "$pid" 2>/dev/null || :; wait "$pid" 2>/dev/null || :; }; trap cleanup EXIT INT TERM
for i in $(seq 1 180); do
 kill -0 "$pid" 2>/dev/null || { echo 'server exited'; exit 1; }
 if curl -sf http://127.0.0.1:18300/v1/models >/dev/null; then date -Is > "$run/ready"; break; fi
 sleep 2
done
[[ -f "$run/ready" ]] || { echo 'health timeout'; exit 1; }
wait "$pid"
