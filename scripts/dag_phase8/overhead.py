"""Measure the snapshot-copy optimization on finalized production adapter graphs."""
import gc
from statistics import median
import time
import tracemalloc
from types import SimpleNamespace

from scripts.dag_phase4.main import ROOT, write_json
from scripts.dag_phase7.main import drain
from vidur.dag.expanded import ATTENTION, CPU_POST, CPU_PRE, MLP
from vidur.dag.moe import load_config
from vidur.dag.moe_host import DynamicMoeDagAdapter
from vidur.entities import BatchStage, Request
from schemas.dag.v1.io import read_json


def measure(output):
    host = DynamicMoeDagAdapter([(0, 0), (1, 0)], 1, "vidur", "synthetic",
        read_json(ROOT / "configs/dag/phase7/resources.json"), load_config(ROOT / "configs/dag/phase7/alternating.json"))
    fields = dict.fromkeys((*ATTENTION, *MLP, *CPU_PRE, *CPU_POST, "add_time",
                           "attention_all_reduce_time", "mlp_all_reduce_time", "pipeline_parallel_communication_time"), 0)
    now = 0
    for index in range(8):
        request = Request(now, 8, 4)
        request.on_batch_schedule(now)
        batch = SimpleNamespace(id=index, requests=[request], total_num_tokens=8,
                                num_prefill_tokens=8, num_decode_tokens=0)
        stage = BatchStage(index, 0, 0, 0, 0, [request], [8])
        end, = drain(host.submit_stage(now, 0, 0, True, batch, stage, on_stage_start=stage.on_schedule,
                                     execution_time=SimpleNamespace(**fields, num_layers=4)))
        now = end.time
    def before():
        return sum(len(host.executor.graph_snapshot(record["graph_id"]).tasks) for record in host.rounds)
    def after():
        graphs = host.executor.graphs
        return sum(len(graphs[record["graph_id"]].tasks) for record in host.rounds)
    samples = {"before_per_round_snapshot": [], "after_one_bulk_snapshot": []}
    checksums = []
    for _ in range(3):
        for name, operation in (("before_per_round_snapshot", before), ("after_one_bulk_snapshot", after)):
            gc.collect()
            tracemalloc.start()
            started = time.perf_counter()
            checksum = operation()
            elapsed = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            checksums.append(checksum)
            samples[name].append(dict(wall_time_s=elapsed, peak_python_allocation_bytes=peak))
    assert len(set(checksums)) == 1
    result = dict(scope="Graph snapshot portion of finalized MoE export, not model execution or full CLI speedup",
                  graph_count=8, routing_count=len(host.rounds), matching_task_count_checksum=checksums[0],
                  copied_graphs_before=len(host.rounds), copied_graphs_after=8,
                  samples=samples, median_wall_time_s={name: median(s["wall_time_s"] for s in group)
                                                     for name, group in samples.items()},
                  limitation="Bulk snapshot can increase temporary peak memory; graph histories and routing records are retained.")
    write_json(output / "snapshot-overhead.json", result)
    return result
