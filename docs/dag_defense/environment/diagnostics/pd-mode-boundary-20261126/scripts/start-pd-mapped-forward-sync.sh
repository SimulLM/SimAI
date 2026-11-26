#!/usr/bin/env bash
set -euo pipefail
root=/root/autodl-tmp
model=$root/models/Llama-2-7b-hf
log=${COMPUTE_DIAG_DIR:?}
mkdir -p "$log"
export PATH=$root/venvs/vllm-0.8.5/bin:$PATH
export HF_HOME=$root/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_NO_USAGE_STATS=1 VLLM_USE_V1=0
export VLLM_LOGGING_LEVEL=INFO NCCL_DEBUG=INFO
export COMPUTE_DIAG=1 PYTHONPATH=/root/autodl-tmp/dag-handoff/scripts/pd-mapped-forward-instrument
export VLLM_HOST_IP=$(hostname -I | awk '{print $1}')
# Stop only processes started by this script via saved pidfile.
cleanup(){ test -f "$log/pids" && xargs -r kill < "$log/pids" || true; }
trap cleanup EXIT INT TERM
: > "$log/pids"
CUDA_VISIBLE_DEVICES=0 vllm serve "$model" --host 127.0.0.1 --port 8100 --dtype float16 --tensor-parallel-size 1 --max-model-len 4096 --max-num-seqs 4 --gpu-memory-utilization 0.80 --disable-async-output-proc --no-enable-prefix-caching --no-enable-chunked-prefill --generation-config vllm --override-generation-config '{"temperature":0,"top_p":1,"top_k":-1,"max_new_tokens":128,"min_new_tokens":128,"ignore_eos":true}' --kv-transfer-config '{"kv_connector":"PyNcclConnector","kv_buffer_size":5000000000,"kv_role":"kv_producer","kv_rank":0,"kv_parallel_size":2,"kv_ip":"'"$VLLM_HOST_IP"'","kv_port":14579}' > "$log/prefill.log" 2>&1 & echo $! >> "$log/pids"
CUDA_VISIBLE_DEVICES=1 vllm serve "$model" --host 127.0.0.1 --port 8200 --dtype float16 --tensor-parallel-size 1 --max-model-len 4096 --max-num-seqs 4 --gpu-memory-utilization 0.80 --disable-async-output-proc --no-enable-prefix-caching --no-enable-chunked-prefill --generation-config vllm --override-generation-config '{"temperature":0,"top_p":1,"top_k":-1,"max_new_tokens":128,"min_new_tokens":128,"ignore_eos":true}' --kv-transfer-config '{"kv_connector":"PyNcclConnector","kv_buffer_size":5000000000,"kv_role":"kv_consumer","kv_rank":1,"kv_parallel_size":2,"kv_ip":"'"$VLLM_HOST_IP"'","kv_port":14579}' > "$log/decode.log" 2>&1 & echo $! >> "$log/pids"
for port in 8100 8200; do timeout 600 bash -c "until curl -sf http://127.0.0.1:$port/v1/models >/dev/null; do sleep 2; done"; done
python "$root/dag-handoff/scripts/proxy-18300.py" > "$log/proxy.log" 2>&1 & echo $! >> "$log/pids"
wait
