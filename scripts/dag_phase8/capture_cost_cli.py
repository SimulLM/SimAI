"""Observe predictor return values without modifying costs, scheduling or events."""
import argparse
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "vidur-alibabacloud")]

# Independent of the DAG builder's constants: these are public predictor fields.
FIELDS = (
    "attention_pre_proj_time", "attention_post_proj_time", "attention_rope_execution_time",
    "attention_kv_cache_save_execution_time", "attention_prefill_execution_time", "attention_decode_execution_time",
    "attn_norm_time", "mlp_norm_time", "mlp_layer_up_proj_execution_time", "mlp_layer_act_execution_time",
    "mlp_layer_down_proj_execution_time", "add_time", "attention_all_reduce_time", "mlp_all_reduce_time",
    "pipeline_parallel_communication_time", "schedule_time", "prepare_inputs_e2e_time", "sampler_e2e_time",
    "process_model_outputs_time", "ray_comm_time",
)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--capture-output", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    from vidur.execution_time_predictor.base_execution_time_predictor import BaseExecutionTimePredictor
    original = BaseExecutionTimePredictor.get_execution_time
    observations = []

    def capture(self, batch, pipeline_stage):
        result = original(self, batch, pipeline_stage)
        observations.append(dict(stage=pipeline_stage, replica=batch.replica_id,
            request_ids=batch.request_ids, tokens=list(batch.num_tokens),
            cost=dict(total_s=result.total_time, model_s=result.model_time, layers=result.num_layers,
                      components_ms={name: float(getattr(result, name)) for name in FIELDS})))
        return result

    BaseExecutionTimePredictor.get_execution_time = capture
    sys.argv = ["vidur.main", *remaining]
    try:
        runpy.run_module("vidur.main", run_name="__main__")
    finally:
        BaseExecutionTimePredictor.get_execution_time = original
        args.capture_output.write_text(json.dumps(dict(snapshot_only=True, observations=observations),
            indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
