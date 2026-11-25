#!/usr/bin/env bash
set -euo pipefail
root=/root/autodl-tmp
wheels="$root/models/vllm-0.8.5-linux-cp312-wheels"
python3 -m venv "$root/venvs/vllm-0.8.5"
PIP_NO_INDEX=1 "$root/venvs/vllm-0.8.5/bin/python" -m pip install --no-index --find-links="$wheels" vllm==0.8.5 quart
"$root/venvs/vllm-0.8.5/bin/python" -m pip check
"$root/venvs/vllm-0.8.5/bin/python" -m pip freeze > "$root/dag-handoff/pip-freeze.txt"
