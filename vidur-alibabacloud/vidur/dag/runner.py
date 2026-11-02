"""Standalone host adapter. Its heap is the only event queue in CLI mode."""
import heapq
from itertools import count

from .executor import DagExecutor
from schemas.dag.v1.io import finite_nonnegative


class SimulationFailure(RuntimeError):
    pass


class DagRunner:
    def __init__(self, executor=None):
        self.executor = executor if executor is not None else DagExecutor()
        self.now = self.executor.now
        self._queue = []
        self._sequence = count()
        self.events = []
        self.queue_peak = 0
        self.failure = None

    @property
    def pending_event_count(self):
        return len(self._queue)

    def enqueue(self, intents):
        if self.failure is not None:
            raise SimulationFailure(self.failure)
        self.executor._validate_events(intents, self.now)
        for event in intents:
            heapq.heappush(self._queue, (event.time_s, next(self._sequence), event))
        self.queue_peak = max(self.queue_peak, len(self._queue))

    def submit(self, fragment, now=None, terminal_callback=None):
        now = self._check_admission_time(now)
        callback = (lambda *_: ()) if terminal_callback is None else terminal_callback
        handle = self.executor.submit(fragment, now, callback)
        self.now = now
        self.enqueue(handle.initial_events)
        return handle

    def _check_admission_time(self, now):
        if self.failure is not None:
            raise SimulationFailure(self.failure)
        now = self.now if now is None else finite_nonnegative(now)
        if now < self.now:
            raise ValueError("runner submission time went backwards")
        if self._queue and now > self._queue[0][0]:
            raise ValueError("consume earlier queued events before submitting at a later time")
        return now

    def append(self, patch, now=None):
        now = self._check_admission_time(now)
        intents = self.executor.append(patch, now)
        self.now = now
        self.enqueue(intents)
        return intents

    def step(self):
        if self.failure is not None:
            raise SimulationFailure(self.failure)
        if not self._queue:
            return False
        now, sequence, event = heapq.heappop(self._queue)
        self.events.append({"time_s": now, "insertion_sequence": sequence,
                            "kind": event.kind, "graph_id": event.owner[0],
                            "task_id": event.owner[1]})
        try:
            if now < self.now:
                raise RuntimeError("event time went backwards")
            self.now = now
            if event.kind == "task_complete":
                intents = self.executor.on_task_complete(*event.owner, now)
            elif event.kind == "dispatch":
                intents = self.executor.dispatch(now)
            elif event.kind == "graph_failed":
                graph = self.executor.graphs.get(event.owner[0])
                raise SimulationFailure(graph.failure if graph and graph.failure else
                                        f"host graph_failed event: {event.owner}")
            else:
                raise RuntimeError(f"unknown event kind: {event.kind}")
            self.enqueue(intents)
        except Exception as exc:
            self.failure = str(exc)
            raise SimulationFailure(self.failure) from exc
        return True

    def run(self):
        while self.step():
            pass
        incomplete = [gid for gid, graph in self.executor.graphs.items() if graph.state != "COMPLETED"]
        if incomplete:
            self.failure = f"event queue exhausted with unfinished graphs: {', '.join(incomplete)}"
            raise SimulationFailure(self.failure)
        return self.now
