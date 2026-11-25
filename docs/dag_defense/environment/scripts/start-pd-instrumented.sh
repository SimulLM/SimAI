#!/usr/bin/env bash
set -euo pipefail
root=/root/autodl-tmp
run=${PD_RUN_DIR:?Set PD_RUN_DIR to a new absolute run directory}
model=$root/models/Llama-2-7b-hf
venv=$root/venvs/vllm-0.8.5
mkdir "$run"
export PATH="$venv/bin:$PATH" HF_HOME="$root/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_NO_USAGE_STATS=1 VLLM_USE_V1=0
export VLLM_LOGGING_LEVEL=DEBUG NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,GRAPH,P2P,SHM,NET
export NCCL_DEBUG_FILE="$run/nccl.%h.%p.log"
export VLLM_HOST_IP=$(hostname -I | awk '{print $1}')
export PD_DIAG=1 PD_DIAG_DIR="$run" PYTHONPATH="$root/dag-handoff/scripts/pd-diag-instrument"
pids=()
cleanup(){ trap - EXIT INT TERM; if ((${#pids[@]})); then kill "${pids[@]}" 2>/dev/null || :; wait "${pids[@]}" 2>/dev/null || :; fi; }
trap cleanup EXIT INT TERM
common=(serve "$model" --host 127.0.0.1 --dtype float16 --tensor-parallel-size 1 --max-model-len 4096 --max-num-seqs 4 --gpu-memory-utilization 0.75 --enforce-eager --no-enable-prefix-caching --no-enable-chunked-prefill --generation-config vllm)
env CUDA_VISIBLE_DEVICES=0 PD_DIAG_ROLE=prefill vllm "${common[@]}" --port 18100 --kv-transfer-config '{"kv_connector":"PyNcclConnector","kv_role":"kv_producer","kv_rank":0,"kv_parallel_size":2,"kv_ip":"'"$VLLM_HOST_IP"'","kv_port":14679}' > "$run/prefill.log" 2>&1 & pids+=("$!")
env CUDA_VISIBLE_DEVICES=1 PD_DIAG_ROLE=decode vllm "${common[@]}" --port 18200 --kv-transfer-config '{"kv_connector":"PyNcclConnector","kv_role":"kv_consumer","kv_rank":1,"kv_parallel_size":2,"kv_ip":"'"$VLLM_HOST_IP"'","kv_port":14679}' > "$run/decode.log" 2>&1 & pids+=("$!")
printf '%s\n' "${pids[@]}" > "$run/pids"
for i in $(seq 1 180); do
 for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null || { echo "child $p exited"; exit 1; }; done
 if curl -sf http://127.0.0.1:18100/v1/models >/dev/null && curl -sf http://127.0.0.1:18200/v1/models >/dev/null; then date -Is > "$run/ready"; break; fi
 sleep 2
done
[[ -f "$run/ready" ]] || { echo 'health timeout'; exit 1; }
wait -n "${pids[@]}"
echo 'a server exited' >&2
exit 1
