"""Coarse Stage adapter; Simulator owns the only event heap and clock."""
from dataclasses import replace
from itertools import count

from schemas.dag.v1.contracts import (
    CostEstimate, GraphContext, GraphFragment, Placement, ResourceDemand, TaskSpec,
)
from vidur.dag.executor import DagExecutor
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity
from vidur.events.base_event import BaseEvent
from vidur.types import EventType


class DagHostEvent(BaseEvent):
    def __init__(self, adapter, intent):
        super().__init__(intent.time_s, EventType.DAG)
        self.adapter = adapter
        self.intent = intent
        # Reserve the legacy StageEnd's position among equal-time host events.
        # Internal completion/zero-duration terminal events occupy that position
        # until the real StageEnd becomes eligible; no premature end is queued.
        end = adapter.stage_ends[intent.owner[0]]
        self._priority_number = (self.time, end.id, None, self.id)

    def handle_event(self, scheduler, metrics_store):
        return self.adapter.handle(replace(self.intent, time_s=self.time))

    def to_dict(self):
        return {"time": self.time, "event_type": "dag_" + self.intent.kind,
                "graph_id": self.intent.owner[0], "task_id": self.intent.owner[1]}


class CoarseDagAdapter:
    def __init__(self, stage_keys, *, resources=()):
        capacities = {self.resource_id(*key): ResourceCapacity(1, "permits") for key in stage_keys}
        capacities.update({key: ResourceCapacity(1, "permits") for key in resources})
        self.executor = DagExecutor(CapacityResourceManager(capacities),
                                    resource_units={key: "permits" for key in capacities})
        self.stage_ends = {}
        self.events = []
        self.now = 0.0
        self.failure = None
        self.queue_peak = 0
        self.pending_event_count = 0
        self._sequence = count()
        self._outbox = []
        self._stage_starts = {}
        self._stage_finishes = {}

    @staticmethod
    def resource_id(replica_id, stage_id):
        # A compatibility Stage permit, not a claim about physical GPU overlap.
        return f"stage:{replica_id}:{stage_id}"

    def submit_stage(self, now, replica_id, stage_id, is_last_stage, batch, batch_stage,
                     *, on_stage_start=None, execution_time=None, record=None):
        if self.failure:
            raise RuntimeError(self.failure)
        graph_id, context = self._identity(replica_id, stage_id, batch)
        resource = self.resource_id(replica_id, stage_id)
        cost = CostEstimate(batch_stage.execution_time, "legacy_execution_time.total_time",
                            batch_stage.execution_time, "s", 1.0,
                            "vidur/entities/execution_time.py:ExecutionTime.total_time; "
                            "snapshot already stored by ReplicaStageScheduler in BatchStage.execution_time",
                            ("compute", "tp", "pp", "cpu"), ("ep",))
        terminal = CostEstimate(0.0, "dag_terminal", 0.0, "s", 1.0, "zero-duration join", ("sync",))
        fragment = GraphFragment("1.0", graph_id, context, (
            TaskSpec("coarse", "coarse", Placement(), (ResourceDemand(resource, 1, "permits"),), cost),
            TaskSpec("terminal", "sync", Placement(), (), terminal),
        ), (("coarse", "terminal"),), "terminal")
        return self._submit(fragment, now, replica_id, stage_id, is_last_stage,
                            batch, batch_stage, on_stage_start)

    def _identity(self, replica_id, stage_id, batch):
        sequence = next(self._sequence)
        return (f"replica{replica_id}/stage{stage_id}/batch{batch.id}/iteration{sequence}",
                GraphContext(str(batch.id), sequence, str(replica_id), stage_id,
                             tuple(str(request.id) for request in batch.requests)))

    def _submit(self, fragment, now, replica_id, stage_id, is_last_stage, batch,
                batch_stage, on_stage_start, on_stage_finish=None):
        if self.failure:
            raise RuntimeError(self.failure)
        from vidur.events.batch_stage_end_event import BatchStageEndEvent
        graph_id = fragment.graph_id
        # Allocate exactly where legacy allocates its end event, preserving its
        # equal-time ordering identity. It is NOT queued until terminal callback.
        end = BatchStageEndEvent(now + batch_stage.execution_time, replica_id, stage_id,
                                 is_last_stage, batch, batch_stage)
        self.stage_ends[graph_id] = end
        if on_stage_start is not None:
            self._stage_starts[graph_id] = on_stage_start
        if on_stage_finish is not None:
            self._stage_finishes[graph_id] = on_stage_finish

        def on_terminal(completed_graph_id, finished_at):
            finish = self._stage_finishes.pop(completed_graph_id, None)
            if finish is not None:
                finish(finished_at)
            end._time = finished_at
            end._priority_number = end._get_priority_number()
            self._outbox.append(end)
            return ()

        handle = self.executor.submit(fragment, now, on_terminal)
        return self._wrap(handle.initial_events)

    def _wrap(self, intents):
        events = []
        for intent in intents:
            if intent.kind == "task_complete":
                start = self._stage_starts.pop(intent.owner[0], None)
                if start is not None:
                    # dispatch creates completion intents at the actual start.
                    # Use its clock, avoiding finish-duration float cancellation.
                    start(self.executor.now)
            events.append(DagHostEvent(self, intent))
        return events

    def handle(self, intent):
        if self.failure:
            return []  # Completion events queued before a host abort are stale.
        self.now = intent.time_s
        self.events.append({"time_s": intent.time_s, "insertion_sequence": len(self.events),
                            "kind": intent.kind, "graph_id": intent.owner[0], "task_id": intent.owner[1]})
        try:
            if intent.kind == "task_complete":
                intents = self.executor.on_task_complete(*intent.owner, intent.time_s)
            elif intent.kind == "dispatch":
                intents = self.executor.dispatch(intent.time_s)
            elif intent.kind == "graph_failed":
                raise RuntimeError(self.executor.graphs[intent.owner[0]].failure)
            else:
                raise ValueError(f"unknown DAG intent: {intent.kind}")
            events = self._wrap(intents) + self._outbox
            self._outbox = []
            return events
        except Exception as exc:
            self.abort(intent.time_s, str(exc))
            raise

    def abort(self, now, reason):
        self.failure = self.failure or str(reason)
        self.now = now
        self._outbox = []
        self._stage_starts.clear()
        self._stage_finishes.clear()
        self.executor.abort(now, self.failure)

    def assert_completed(self):
        if any(graph.state != "COMPLETED" for graph in self.executor.graphs.values()):
            raise RuntimeError("host queue exhausted with unfinished DAG graphs")
