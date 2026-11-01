"""Run selected original methods via AST with controlled inputs, no Vidur import."""
import ast
from types import SimpleNamespace

from common import ROOT, sha256


def probe():
    path = ROOT / "vidur-alibabacloud/vidur/entities/execution_time.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ExecutionTime")
    names = {"_get_attention_layer_execution_time_from_aicb", "_get_mlp_layer_execution_time_from_aicb",
             "_get_moe_layer_execution_time_from_aicb", "_get_block_execution_time_by_layer_id",
             "model_time", "pipeline_parallel_communication_time"}
    methods = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(methods) == len(names)
    extracted = ast.ClassDef(name="Probe", bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[extracted], type_ignores=[]))
    namespace = {}
    exec(compile(module, str(path), "exec"), namespace)
    obj = namespace["Probe"]()
    obj._aicb_data = {0: {name: {"comp_time": 1_000_000, "comm_size": 0}
                          for name in ("attention", "mlp", "moe")}}
    obj._config = SimpleNamespace(backend="aicb")
    obj._replica_config = SimpleNamespace(model_name="deepseek-671B", num_pipeline_stages=1,
                                         rdma_bandwidth=100, nvlink_bandwidth=100)
    obj._num_layers_per_pipeline_stage = 1
    obj._pipeline_parallel_communication_time = 0
    layer = obj._get_block_execution_time_by_layer_id(0)
    stage = obj.model_time
    return {"source": path.relative_to(ROOT).as_posix(), "sha256": sha256(path),
            "method_lines": {n.name: n.lineno for n in methods},
            "scope": "controlled 1-layer deepseek-671B/aicb/PP1; no hardware measurement",
            "raw_component_ns": 1_000_000, "component_count": 3,
            "layer_duration_s": layer, "stage_duration_s": stage,
            "stage_to_layer_ratio": stage / layer,
            "finding": "AICB seconds are scaled again by 1e-3; legacy behavior preserved"}
