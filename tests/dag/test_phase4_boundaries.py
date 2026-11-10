"""Regression evidence for time cutoffs, global abort and durable failures."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from schemas.dag.v1.contracts import TaskState
from scripts.dag_phase4.main import ROOT, cli_command, compare, synthetic_profiles
from vidur.dag.host import CoarseDagAdapter
from vidur.events.batch_stage_end_event import BatchStageEndEvent
from vidur.simulator import Simulator


def host(tmp_path, adapter=None, limit=float("inf")):
    simulator = Simulator.__new__(Simulator)
    simulator._config = SimpleNamespace(execution_mode="dag_coarse" if adapter else "legacy",
        metrics_config=SimpleNamespace(output_dir=str(tmp_path), write_json_trace=False,
                                       enable_chrome_trace=False))
    simulator._time = 0
    simulator._time_limit = limit
    simulator._terminate = False
    simulator._failure = None
    simulator._requests = []
    simulator._event_queue = []
    simulator._cluster = "boundary regression"
    simulator._scheduler = SimpleNamespace(dag_adapter=adapter, stage_execution_records=[], is_empty=lambda: True)
    simulator._metric_store = SimpleNamespace(plot=lambda: None)
    return simulator


def stage(adapter, replica=1, batch_id=1, duration=10):
    return adapter.submit_stage(0, replica, 0, True,
        SimpleNamespace(id=batch_id, requests=[SimpleNamespace(id=1)]),
        SimpleNamespace(id=batch_id, execution_time=duration))


@pytest.mark.parametrize("duration,completed", [(0, True), (1, True), (1.00001, False)])
@pytest.mark.parametrize("mode", ["legacy", "dag_coarse"])
def test_cutoff_is_inclusive_and_drains_same_time_terminal(tmp_path, monkeypatch, duration, completed, mode):
    adapter = CoarseDagAdapter([(1, 0)]) if mode == "dag_coarse" else None
    simulator = host(tmp_path, adapter, limit=1)
    observed = []
    monkeypatch.setattr(BatchStageEndEvent, "handle_event", lambda self, *_: observed.append(self.time) or [])
    events = stage(adapter, duration=duration) if adapter else [
        BatchStageEndEvent(duration, 1, 0, True, SimpleNamespace(), SimpleNamespace())]
    simulator._add_events(events)
    simulator.run()
    assert observed == ([duration] if completed else [])
    assert simulator._time == (duration if completed else 1)
    assert simulator._terminate is not completed
    assert len(simulator._event_queue) == (0 if completed else 1)
    if adapter:
        graph, = adapter.executor.graphs.values()
        assert graph.callback_count == int(completed)


@pytest.mark.parametrize("source", ["graph", "host"])
def test_global_abort_cleans_running_and_waiting_graphs_once(tmp_path, source):
    adapter = CoarseDagAdapter([(1, 0), (2, 0)])
    simulator = host(tmp_path, adapter)
    initial = stage(adapter, 1, 1) + stage(adapter, 2, 2) + stage(adapter, 2, 3)
    simulator._add_events(initial)
    first = next(iter(adapter.executor.graphs))
    manager = adapter.executor._resources
    releases = []
    original_release = manager.release

    def release(lease, now):
        releases.append(lease.lease_id)
        return original_release(lease, now)

    manager.release = release

    def fail(*_):
        if source == "host":
            raise RuntimeError("injected host failure")
        return adapter._wrap(adapter.executor.fail_task(first, "coarse", 1, "injected graph failure"))

    simulator._add_event(SimpleNamespace(time=1, _time=1, _event_type="failure",
        _priority_number=(1, -1, None), handle_event=fail))
    with pytest.raises(RuntimeError, match="injected"):
        simulator.run()
    adapter.abort(1, "repeat cleanup")
    assert not simulator._event_queue and adapter.pending_event_count == 0
    assert len(releases) == len(set(releases)) == 2
    assert not manager._waiters
    assert all(value["used"] == 0 for value in manager.usage_snapshot().values())
    for graph in adapter.executor.graphs.values():
        assert graph.state == "FAILED" and graph.callback_count == 0
        assert not graph.cleanup_errors
        assert all(task.state == TaskState.FAILED and task.lease is None for task in graph.tasks.values())
    waiter = list(adapter.executor.graphs.values())[-1].tasks["coarse"]
    assert waiter.resource_wait_s == 1 and waiter.resource_wait_started_at is None
    # Stale completion events cannot run callbacks or release leases again.
    assert all(event.handle_event(None, None) == [] for event in initial)
    assert len(releases) == 2
    with pytest.raises(RuntimeError, match="injected"):
        stage(adapter, 1, 4)
    simulator.write_output()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert not summary["resource_capacity_check_errors"]


def test_abort_keeps_completed_results_and_reports_failed_release(tmp_path):
    adapter = CoarseDagAdapter([(1, 0), (2, 0)])
    events = stage(adapter, 1, 1, duration=0)
    while events:
        event = events.pop(0)
        if not isinstance(event, BatchStageEndEvent):
            events.extend(event.handle_event(None, None))
    stage(adapter, 2, 2)
    completed_id, failed_id = adapter.executor.graphs
    releases = []

    def broken(lease, now):
        releases.append(lease.lease_id)
        raise OSError("injected release error")

    adapter.executor._resources.release = broken
    adapter.abort(1, "global abort")
    adapter.abort(1, "repeat")
    assert len(releases) == 1
    assert adapter.executor.graphs[completed_id].state == "COMPLETED"
    assert adapter.executor.graphs[completed_id].callback_count == 1
    graph = adapter.executor.graphs[failed_id]
    assert graph.state == "FAILED" and graph.callback_count == 0
    assert graph.tasks["coarse"].lease is not None
    assert any("not confirmed" in error for error in graph.cleanup_errors)


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1])
@pytest.mark.parametrize("mode", ["legacy", "dag_coarse"])
def test_invalid_stage_cost_is_rejected_before_metrics_and_saved(tmp_path, duration, mode):
    from vidur.events.replica_stage_schedule_event import ReplicaStageScheduleEvent
    from vidur.scheduler.replica_stage_scheduler.replica_stage_schduler import ReplicaStageScheduler
    from vidur.entities import Request

    predictor = SimpleNamespace(get_execution_time=lambda *_: SimpleNamespace(total_time=duration, model_time=0))
    scheduler = ReplicaStageScheduler(1, 0, True, predictor)
    request = Request(0, 8, 4)
    request.on_batch_schedule(0)
    scheduler.add_batch(SimpleNamespace(id=1, requests=[request], request_ids=[request.id], num_tokens=[8]))
    adapter = CoarseDagAdapter([(1, 0)]) if mode == "dag_coarse" else None
    simulator = host(tmp_path, adapter)
    simulator._requests = [request]
    simulator._scheduler._replica_schedulers = {1: SimpleNamespace(_replica_stage_schedulers={0: scheduler})}
    metrics = []
    simulator._metric_store.on_replica_stage_schedule = lambda *_: metrics.append(True)
    simulator._add_event(ReplicaStageScheduleEvent(0, 1, 0))
    with pytest.raises(ValueError, match="invalid Stage execution time"):
        simulator.run()
    assert not metrics
    simulator.write_output()
    result = json.loads((tmp_path / "execution-summary.json").read_text())
    assert result["status"] == "failed"
    record, = result["stages"]
    assert record["predicted_duration_s"] is None
    assert record["invalid_predicted_duration"] == repr(duration)
    assert record["completion_count"] == 0 and record["validation_error"]
    if adapter:
        assert json.loads((tmp_path / "summary.json").read_text())["status"] == "failed"


def test_failure_sections_are_independent_and_json_is_atomic(tmp_path, monkeypatch):
    import vidur.utils.diagnostics as diagnostics

    adapter = CoarseDagAdapter([(1, 0)])
    simulator = host(tmp_path, adapter)
    simulator._failure = "original execution error"
    simulator._scheduler.stage_execution_records = [{"raw": float("nan")}]
    simulator.write_output()
    summary_path = tmp_path / "execution-summary.json"
    original = summary_path.read_bytes()
    assert json.loads(original)["stages"] == [{"raw": "nan"}]
    assert json.loads((tmp_path / "summary.json").read_text())["error"] == "original execution error"
    replace = diagnostics.os.replace

    def broken_replace(source, destination):
        if Path(destination) == summary_path:
            raise OSError("injected summary write failure")
        replace(source, destination)

    monkeypatch.setattr(diagnostics.os, "replace", broken_replace)
    (tmp_path / "summary.json").unlink()
    simulator._failure = "updated execution error"
    with pytest.raises(OSError, match="injected summary write failure"):
        simulator.write_output()
    assert summary_path.read_bytes() == original and not list(tmp_path.glob("*.tmp"))
    assert json.loads((tmp_path / "summary.json").read_text())["error"] == "updated execution error"
    errors = json.loads((tmp_path / "output-errors.json").read_text())
    assert errors["output_errors"][0]["section"] == "execution_summary"


def test_cli_preserves_execution_error_when_output_also_fails(monkeypatch):
    import vidur.main as entry

    class BrokenSimulator:
        def __init__(self, _):
            pass

        def run(self):
            raise ValueError("primary execution failure")

        def write_output(self):
            raise OSError("secondary output failure")

    monkeypatch.setattr(entry.SimulationConfig, "create_from_cli_args", lambda: SimpleNamespace(seed=42))
    monkeypatch.setattr(entry, "Simulator", BrokenSimulator)
    with pytest.raises(ValueError, match="primary execution failure") as error:
        entry.main()
    assert any("secondary output failure" in note for note in error.value.__notes__)


def test_secondary_error_notes_work_without_python311_method():
    from vidur.utils.diagnostics import add_exception_note

    class OlderError(Exception):
        add_note = None

    error = OlderError("primary")
    add_exception_note(error, "first")
    add_exception_note(error, "second")
    assert error.__notes__ == ["first", "second"]


@pytest.fixture(scope="module")
def profiles(tmp_path_factory):
    folder = tmp_path_factory.mktemp("boundary-cli") / "profiles"
    synthetic_profiles(folder)
    return folder


def run_original_cli(tmp_path, profiles, mode, *, invalid_cost=False):
    trace = tmp_path / "requests.csv"
    trace.write_text("arrived_at,num_prefill_tokens,num_decode_tokens\n0.9995,8,4\n", encoding="utf-8")
    command = cli_command(mode, tmp_path / "run", profiles, trace)
    command += ["--time_limit", "1", "--no-metrics_config_store_utilization_metrics"]
    if invalid_cost:
        wrapper = tmp_path / "inject.py"
        wrapper.write_text('''from vidur.execution_time_predictor import BaseExecutionTimePredictor
from vidur.main import main
original = BaseExecutionTimePredictor.get_execution_time
class InvalidCost:
    total_time = float("nan")
    def __init__(self, result):
        self.result = result
    def __getattr__(self, name):
        return getattr(self.result, name)
def predict(self, *args, **kwargs):
    return InvalidCost(original(self, *args, **kwargs))
BaseExecutionTimePredictor.get_execution_time = predict
main()
''', encoding="utf-8")
        command[1:3] = [str(wrapper)]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT / "vidur-alibabacloud"), str(ROOT), env.get("PYTHONPATH", "")))
    env["WANDB_MODE"] = "disabled"
    (tmp_path / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    with (tmp_path / "process.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    (tmp_path / "process-result.json").write_text(json.dumps({"exit_code": process.returncode}), encoding="utf-8")
    summary_path, = (tmp_path / "run").glob("*/execution-summary.json")
    return process.returncode, json.loads(summary_path.read_text()), summary_path.parent


def test_real_cli_time_limit_has_identical_request_and_stage_state(tmp_path, profiles):
    results = []
    for mode in ("legacy", "dag_coarse"):
        folder = tmp_path / mode
        folder.mkdir()
        code, result, _ = run_original_cli(folder, profiles, mode)
        assert code == 0 and result["status"] == "truncated"
        assert result["final_time_s"] == 1
        assert result["stages"][0]["completion_count"] == 0
        assert result["stages"][0]["end_at_s"] is None
        results.append(result)
    assert compare(results[0]["requests"], results[1]["requests"])
    assert compare(results[0]["stages"], results[1]["stages"])
    (tmp_path / "comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


@pytest.mark.parametrize("mode", ["legacy", "dag_coarse"])
def test_real_cli_nan_keeps_parseable_failure_reports(tmp_path, profiles, mode):
    code, result, output = run_original_cli(tmp_path, profiles, mode, invalid_cost=True)
    assert code == 1 and result["status"] == "failed"
    assert "invalid Stage execution time" in result["error"]
    assert result["stages"][0]["invalid_predicted_duration"] == "nan"
    assert result["stages"][0]["predicted_duration_s"] is None
    assert "Out of range float values" not in (tmp_path / "process.log").read_text()
    if mode == "dag_coarse":
        summary = json.loads((output / "summary.json").read_text())
        assert summary["status"] == "failed" and summary["error"] == result["error"]
