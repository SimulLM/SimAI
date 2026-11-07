"""Original Stage boundary, host ordering, single-clock and failure regressions."""
import heapq
from types import SimpleNamespace

import pytest

from vidur.dag.host import CoarseDagAdapter, DagHostEvent
from vidur.events.batch_stage_end_event import BatchStageEndEvent


def submit(adapter, *, duration=2.0, replica=1, stage=0, batch_id=1, now=0):
    batch = SimpleNamespace(id=batch_id, requests=[SimpleNamespace(id=1)])
    batch_stage = SimpleNamespace(id=batch_id, execution_time=duration)
    return adapter.submit_stage(now, replica, stage, True, batch, batch_stage)


def drain(events):
    queue = [(e._priority_number, e) for e in events]
    heapq.heapify(queue)
    ends = []
    while queue:
        _, event = heapq.heappop(queue)
        if isinstance(event, BatchStageEndEvent):
            ends.append(event)
        else:
            for successor in event.handle_event(None, None):
                heapq.heappush(queue, (successor._priority_number, successor))
    return ends


def test_terminal_alone_emits_stage_end_and_cost_is_charged_once():
    adapter = CoarseDagAdapter([(1, 0)])
    events = submit(adapter)
    assert len(events) == 1 and isinstance(events[0], DagHostEvent)
    terminal, = events[0].handle_event(None, None)
    assert isinstance(terminal, DagHostEvent) and terminal.time == 2
    end, = terminal.handle_event(None, None)
    assert isinstance(end, BatchStageEndEvent) and end.time == 2
    graph, = adapter.executor.graphs.values()
    assert graph.callback_count == 1
    assert graph.tasks["coarse"].spec.cost.duration_s == 2
    assert graph.tasks["terminal"].spec.cost.duration_s == 0
    with pytest.raises(RuntimeError):
        terminal.handle_event(None, None)
    assert graph.callback_count == 1


def test_stage_end_moves_when_host_completion_is_delayed():
    adapter = CoarseDagAdapter([(1, 0)])
    from schemas.dag.v1.contracts import ResourceDemand
    manager = adapter.executor._resources
    held = manager.try_acquire(("external", "holder"), (ResourceDemand("stage:1:0", 1, "permits"),))
    assert submit(adapter) == []
    manager.release(held, 5)
    end, = drain(adapter._wrap(adapter.executor.dispatch(5)))
    assert end.time == 7
    graph, = adapter.executor.graphs.values()
    assert graph.finished_at == 7 and graph.callback_count == 1


def test_internal_events_keep_reserved_legacy_order_at_equal_time():
    adapter = CoarseDagAdapter([(1, 0), (2, 0)])
    first = submit(adapter, replica=1)
    second = submit(adapter, replica=2, batch_id=2)
    ends = drain(first + second)
    assert [end._replica_id for end in ends] == [1, 2]
    assert [end.time for end in ends] == [2, 2]


def test_arrival_between_completion_and_terminal_cannot_overtake_stage_end():
    from vidur.events.replica_stage_schedule_event import ReplicaStageScheduleEvent
    adapter = CoarseDagAdapter([(1, 0)])
    completion, = submit(adapter)
    other = ReplicaStageScheduleEvent(2, 1, 0)
    terminal, = completion.handle_event(None, None)
    assert terminal._priority_number < other._priority_number
    end, = terminal.handle_event(None, None)
    assert end._priority_number < other._priority_number


def test_replica_stage_resources_are_independent():
    adapter = CoarseDagAdapter([(1, 0), (1, 1), (2, 0)])
    events = submit(adapter) + submit(adapter, stage=1, batch_id=2) + submit(adapter, replica=2, batch_id=3)
    ends = drain(events)
    assert len(ends) == 3 and all(end.time == 2 for end in ends)
    assert all(value["used"] == 0 for value in adapter.executor._resources.usage_snapshot().values())


def test_resource_wait_really_delays_stage_end():
    adapter = CoarseDagAdapter([(1, 0)])
    first = submit(adapter)
    blocked = submit(adapter, batch_id=2)
    assert blocked == []
    ends = drain(first)
    assert [end.time for end in ends] == [2, 4]


def test_zero_duration_coarse_converges_and_iteration_ids_are_unique():
    adapter = CoarseDagAdapter([(1, 0)])
    assert drain(submit(adapter, duration=0))[0].time == 0
    assert drain(submit(adapter, duration=0))[0].time == 0
    assert len(adapter.executor.graphs) == 2
    assert all(graph.callback_count == 1 for graph in adapter.executor.graphs.values())


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf")])
def test_invalid_predictor_cost_is_rejected(duration):
    adapter = CoarseDagAdapter([(1, 0)])
    with pytest.raises(ValueError):
        submit(adapter, duration=duration)
    assert not adapter.executor.graphs
    assert all(value["used"] == 0 for value in adapter.executor._resources.usage_snapshot().values())


def test_failed_graph_stops_host_without_success_callback():
    adapter = CoarseDagAdapter([(1, 0)])
    submit(adapter, duration=10)
    graph_id, = adapter.executor.graphs
    failure, = adapter.executor.fail_task(graph_id, "coarse", 5, "injected failure")
    with pytest.raises(RuntimeError, match="injected failure"):
        adapter.handle(failure)
    assert adapter.failure and not adapter._outbox
    assert adapter.executor.graphs[graph_id].callback_count == 0
    assert adapter.executor._resources.usage_snapshot()["stage:1:0"]["used"] == 0


def test_original_stage_predictor_is_not_called_again_by_dag():
    from vidur.events.replica_stage_schedule_event import ReplicaStageScheduleEvent
    from vidur.scheduler.replica_stage_scheduler.replica_stage_schduler import ReplicaStageScheduler
    from vidur.entities import Request
    calls = []

    def predict(batch, stage):
        calls.append((batch.id, stage))
        return SimpleNamespace(total_time=2, model_time=1.5)

    stage = ReplicaStageScheduler(1, 0, True, SimpleNamespace(get_execution_time=predict))
    request = Request(0, 8, 4)
    request.on_batch_schedule(0)
    batch = SimpleNamespace(id=1, requests=[request], num_tokens=[8], request_ids=[request.id])
    stage.add_batch(batch)
    adapter = CoarseDagAdapter([(1, 0)])
    scheduler = SimpleNamespace(_replica_schedulers={1: SimpleNamespace(_replica_stage_schedulers={0: stage})},
                                dag_adapter=adapter, stage_execution_records=[])
    metrics = SimpleNamespace(on_replica_stage_schedule=lambda *_: None)
    events = ReplicaStageScheduleEvent(0, 1, 0).handle_event(scheduler, metrics)
    assert stage._is_busy and calls == [(1, 0)]
    assert drain(events)[0].time == 2
    assert calls == [(1, 0)] and stage._is_busy  # Original StageEnd owns busy-state release.


def test_original_trace_replica_sets_are_serializable(tmp_path):
    import json
    from vidur.simulator import Simulator
    simulator = Simulator.__new__(Simulator)
    simulator._config = SimpleNamespace(metrics_config=SimpleNamespace(output_dir=str(tmp_path)))
    simulator._event_trace = [{"replica_set": {2, 1}}]
    simulator._write_event_trace()
    assert json.loads((tmp_path / "event_trace.json").read_text()) == [{"replica_set": [1, 2]}]


def test_host_rejects_past_and_nonfinite_events():
    from vidur.simulator import Simulator
    simulator = Simulator.__new__(Simulator)
    simulator._time = 5
    simulator._event_queue = []
    for time in (4, float("inf"), float("nan")):
        with pytest.raises(ValueError, match="finite time"):
            simulator._add_event(SimpleNamespace(time=time))
    assert not simulator._event_queue


def test_simulator_runtime_failure_is_recorded(monkeypatch):
    from vidur.simulator import Simulator
    simulator = Simulator.__new__(Simulator)

    def crash():
        raise RuntimeError("injected host failure")

    monkeypatch.setattr(simulator, "_run", crash)
    with pytest.raises(RuntimeError, match="injected host failure"):
        simulator.run()
    assert simulator._failure == "RuntimeError: injected host failure"


def test_output_errors_propagate_to_cli(monkeypatch):
    from vidur.simulator import Simulator
    simulator = Simulator.__new__(Simulator)

    def crash():
        raise OSError("injected output error")

    monkeypatch.setattr(simulator, "_write_output", crash)
    with pytest.raises(OSError, match="injected output error"):
        simulator.write_output()


def test_default_mode_keeps_legacy_path(tmp_path):
    from vidur.config import MetricsConfig, SimulationConfig
    config = SimulationConfig(metrics_config=MetricsConfig(output_dir=str(tmp_path)))
    assert config.execution_mode == "legacy"


def test_invalid_execution_mode_fails_before_simulation(tmp_path):
    from vidur.config import MetricsConfig, SimulationConfig
    with pytest.raises(ValueError, match="execution_mode"):
        SimulationConfig(execution_mode="invalid", metrics_config=MetricsConfig(output_dir=str(tmp_path)))
