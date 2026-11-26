#!/bin/bash
set -uo pipefail
base=/root/autodl-tmp/dag-handoff/runs/mixed-span-nine-20261126
export COMPUTE_DIAG=1 COMPUTE_DIAG_DIR="$base" CUDA_VISIBLE_DEVICES=1 VLLM_USE_V1=0 VLLM_NO_USAGE_STATS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PROFILE_WAVES=40
export HF_HOME=/root/autodl-tmp/huggingface PYTHONPATH=/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/pd-context-batch3-20261126
/root/autodl-tmp/venvs/vllm-0.8.5/bin/python "$base/profile.py" > "$base/process.log" 2>&1
