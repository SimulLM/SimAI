"""Real StageEnd and request accounting after a delayed coarse dispatch."""
import pytest
from types import SimpleNamespace

from schemas.dag.v1.contracts import ResourceDemand
from vidur.dag.host import CoarseDagAdapter
from vidur.entities import Request
from vidur.events.batch_stage_end_event import BatchStageEndEvent
from vidur.events.replica_stage_schedule_event import ReplicaStageScheduleEvent
from vidur.scheduler.replica_stage_scheduler.replica_stage_schduler import ReplicaStageScheduler


def waiting_stage(submitted_at=0, *, previous_stage=False, duration=2):
    request = Request(0, 8, 4)
    request.on_batch_schedule(0)
    if previous_stage:
        request.on_batch_stage_schedule(0.5)
        request.on_batch_stage_end(1, 0.5, 0.4)
    predictor = SimpleNamespace(get_execution_time=lambda *_: SimpleNamespace(total_time=duration, model_time=1))
    stage = ReplicaStageScheduler(1, 0, True, predictor)
    batch = SimpleNamespace(id=1, requests=[request], request_ids=[request.id], num_tokens=[8])
    stage.add_batch(batch)
    adapter = CoarseDagAdapter([(1, 0)])
    manager = adapter.executor._resources
    held = manager.try_acquire(("external", "holder"), (ResourceDemand("stage:1:0", 1, "permits"),))
    scheduler = SimpleNamespace(_replica_schedulers={1: SimpleNamespace(_replica_stage_schedulers={0: stage})},
        get_replica_stage_scheduler=lambda *_: stage, dag_adapter=adapter, stage_execution_records=[])
    starts, ends = [], []
    metrics = SimpleNamespace(on_replica_stage_schedule=lambda time, *_: starts.append(time),
                              on_batch_stage_end=lambda batch_stage, time, *rest: ends.append(time))
    event = ReplicaStageScheduleEvent(submitted_at, 1, 0)
    assert event.handle_event(scheduler, metrics) == []
    return request, event, adapter, manager, held, scheduler, metrics, starts, ends


@pytest.mark.parametrize("submitted_at,previous_stage", [(0, False), (2, True)])
def test_real_stage_end_keeps_wait_separate_from_execution(submitted_at, previous_stage):
    request, event, adapter, manager, held, scheduler, metrics, starts, ends = waiting_stage(
        submitted_at, previous_stage=previous_stage)
    record, = scheduler.stage_execution_records
    assert record["submitted_at_s"] == submitted_at
    assert record["start_at_s"] is None and record["resource_wait_s"] is None
    assert not event._batch_stage._scheduled and starts == []
    assert request.to_dict()["stage_resource_wait_time_s"] == 0
    manager.release(held, 5)
    completion, = adapter._wrap(adapter.executor.dispatch(5))
    assert starts == [5] and event._batch_stage.scheduled_at == 5
    assert record["start_at_s"] == 5 and record["resource_wait_s"] == 5 - submitted_at
    terminal, = completion.handle_event(scheduler, metrics)
    end, = terminal.handle_event(scheduler, metrics)
    assert isinstance(end, BatchStageEndEvent)
    successors = end.handle_event(scheduler, metrics)  # Run real StageEnd, not just collect it.
    assert successors and ends == [7]
    assert event._batch_stage.completed_at == 7
    assert not scheduler.get_replica_stage_scheduler(1, 0)._is_busy
    assert record["completion_count"] == 1 and record["end_at_s"] == 7
    assert request.execution_time == 2 + (0.5 if previous_stage else 0)
    assert request.to_dict()["stage_resource_wait_time_s"] == 5 - submitted_at
    assert request.preempted_time == (4 if previous_stage else 0)
    assert manager.usage_snapshot()["stage:1:0"]["used"] == 0
    with pytest.raises(RuntimeError, match="duplicate"):
        end.handle_event(scheduler, metrics)
    assert request.execution_time == 2 + (0.5 if previous_stage else 0)


def test_abort_before_dispatch_never_marks_stage_running():
    request, event, adapter, manager, held, scheduler, metrics, starts, ends = waiting_stage()
    adapter.abort(1, "cancel while waiting")
    manager.release(held, 5)
    assert adapter._wrap(adapter.executor.dispatch(5)) == []
    assert not adapter._stage_starts and starts == ends == []
    assert not event._batch_stage._scheduled
    assert scheduler.stage_execution_records[0]["start_at_s"] is None
    assert request.to_dict()["stage_resource_wait_time_s"] == 0


def test_zero_duration_after_wait_runs_real_stage_end():
    request, event, adapter, manager, held, scheduler, metrics, starts, ends = waiting_stage(duration=0)
    manager.release(held, 5)
    completion, = adapter._wrap(adapter.executor.dispatch(5))
    terminal, = completion.handle_event(scheduler, metrics)
    end, = terminal.handle_event(scheduler, metrics)
    end.handle_event(scheduler, metrics)
    assert starts == ends == [5] and request.execution_time == 0
    assert request.to_dict()["stage_resource_wait_time_s"] == 5


def test_waiting_stage_snapshot_at_time_limit(tmp_path):
    from vidur.simulator import Simulator
    request, event, adapter, manager, held, scheduler, metrics, starts, ends = waiting_stage()
    simulator = Simulator.__new__(Simulator)
    simulator._config = SimpleNamespace(metrics_config=SimpleNamespace(write_json_trace=False, enable_chrome_trace=False))
    simulator._time, simulator._time_limit, simulator._terminate, simulator._failure = 0, 3, False, None
    simulator._scheduler, simulator._metric_store = scheduler, metrics
    simulator._cluster, simulator._requests, simulator._event_queue = "controlled waiting stage", [request], []
    scheduler.is_empty = lambda: False
    simulator._add_event(SimpleNamespace(time=5, _time=5, _priority_number=(5, 0, None)))
    simulator.run()
    assert simulator._time == 3 and simulator._terminate
    assert not event._batch_stage._scheduled and not starts
    assert scheduler.stage_execution_records[0]["start_at_s"] is None
    assert request.execution_time == 0
