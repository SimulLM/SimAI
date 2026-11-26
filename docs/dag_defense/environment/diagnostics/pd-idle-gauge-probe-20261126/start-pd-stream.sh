#!/usr/bin/env bash
set -euo pipefail
root=/root/autodl-tmp
run=${PD_ROUTE_DIR:?Set a new run directory}
mkdir "$run"
export PATH="$root/venvs/vllm-0.8.5/bin:$PATH" HF_HOME="$root/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 VLLM_NO_USAGE_STATS=1 VLLM_USE_V1=0
export VLLM_HOST_IP=$(hostname -I | awk '{print $1}')
pids=()
cleanup(){ trap - EXIT INT TERM; if ((${#pids[@]})); then kill "${pids[@]}" 2>/dev/null || :; wait "${pids[@]}" 2>/dev/null || :; fi; }
trap cleanup EXIT INT TERM
common=(serve "$root/models/Llama-2-7b-hf" --host 127.0.0.1 --dtype float16 --tensor-parallel-size 1 --max-model-len 4096 --max-num-seqs 4 --max-num-batched-tokens 4096 --gpu-memory-utilization 0.75 --enforce-eager --no-enable-prefix-caching --no-enable-chunked-prefill --generation-config vllm --disable-log-requests)
env CUDA_VISIBLE_DEVICES=0 vllm "${common[@]}" --port 18100 --kv-transfer-config '{"kv_connector":"PyNcclConnector","kv_role":"kv_producer","kv_rank":0,"kv_parallel_size":2,"kv_buffer_size":8589934592,"kv_ip":"'"$VLLM_HOST_IP"'","kv_port":14679}' > "$run/prefill.log" 2>&1 & pids+=("$!")
env CUDA_VISIBLE_DEVICES=1 vllm "${common[@]}" --port 18200 --kv-transfer-config '{"kv_connector":"PyNcclConnector","kv_role":"kv_consumer","kv_rank":1,"kv_parallel_size":2,"kv_buffer_size":8589934592,"kv_ip":"'"$VLLM_HOST_IP"'","kv_port":14679}' > "$run/decode.log" 2>&1 & pids+=("$!")
for i in $(seq 1 180); do
 for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null || { echo "child $p exited"; exit 1; }; done
 if curl -sf http://127.0.0.1:18100/v1/models >/dev/null && curl -sf http://127.0.0.1:18200/v1/models >/dev/null; then break; fi
 sleep 2
done
curl -sf http://127.0.0.1:18100/v1/models >/dev/null && curl -sf http://127.0.0.1:18200/v1/models >/dev/null || { echo 'health timeout';exit 1; }
export PD_ROUTE_DIR="$run"
uvicorn --app-dir "$root/dag-handoff/scripts" pd_stream_proxy:app --host 127.0.0.1 --port 18300 > "$run/router.log" 2>&1 & pids+=("$!")
printf '%s\n' "${pids[@]}" > "$run/pids"
for i in $(seq 1 30); do
 for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null || { echo "child $p exited";exit 1; }; done
 if curl -sf http://127.0.0.1:18300/openapi.json >/dev/null; then date -Is > "$run/ready";break;fi
 sleep 1
done
[[ -f "$run/ready" ]] || { echo 'router timeout';exit 1; }
wait -n "${pids[@]}"
echo 'a child exited' >&2
exit 1
