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
    def __init__(self, stage_keys):
        capacities = {self.resource_id(*key): ResourceCapacity(1, "permits") for key in stage_keys}
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

    @staticmethod
    def resource_id(replica_id, stage_id):
        # A compatibility Stage permit, not a claim about physical GPU overlap.
        return f"stage:{replica_id}:{stage_id}"

    def submit_stage(self, now, replica_id, stage_id, is_last_stage, batch, batch_stage):
        from vidur.events.batch_stage_end_event import BatchStageEndEvent
        sequence = next(self._sequence)
        graph_id = f"replica{replica_id}/stage{stage_id}/batch{batch.id}/iteration{sequence}"
        context = GraphContext(str(batch.id), sequence, str(replica_id), stage_id,
                               tuple(str(request.id) for request in batch.requests))
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
        # Allocate exactly where legacy allocates its end event, preserving its
        # equal-time ordering identity. It is NOT queued until terminal callback.
        end = BatchStageEndEvent(now + cost.duration_s, replica_id, stage_id, is_last_stage, batch, batch_stage)
        self.stage_ends[graph_id] = end

        def on_terminal(completed_graph_id, finished_at):
            end._time = finished_at
            end._priority_number = end._get_priority_number()
            self._outbox.append(end)
            return ()

        handle = self.executor.submit(fragment, now, on_terminal)
        return self._wrap(handle.initial_events)

    def _wrap(self, intents):
        return [DagHostEvent(self, intent) for intent in intents]

    def handle(self, intent):
        if self.failure:
            raise RuntimeError(self.failure)
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
            self.failure = str(exc)
            self._outbox = []
            raise

    def assert_completed(self):
        if any(graph.state != "COMPLETED" for graph in self.executor.graphs.values()):
            raise RuntimeError("host queue exhausted with unfinished DAG graphs")
