"""Deterministic DAG state transitions; the host owns all event progression."""
from copy import deepcopy
from dataclasses import replace
import math

from schemas.dag.v1.contracts import (
    EventIntent, GraphAppend, GraphFragment, GraphHandle, Lease, TaskState,
)
from schemas.dag.v1.io import finite_nonnegative
from .runtime import GraphRuntime, TaskRuntime
from .serialization import snapshot_graph
from .testing import DependencyOnlyResources


class DagExecutor:
    def __init__(self, resource_manager=None, *, resource_units=None, dependency_only=False):
        if dependency_only and resource_manager is not None:
            raise ValueError("dependency_only cannot be combined with an injected resource manager")
        self._resources = DependencyOnlyResources() if dependency_only else resource_manager
        self.resource_mode = "dependency_only" if dependency_only else (
            "injected" if resource_manager is not None else "resource_free")
        self._resource_units = dict(resource_units or {})
        if any(not isinstance(key, str) or not key or unit not in ("permits", "bytes")
               for key, unit in self._resource_units.items()):
            raise ValueError("invalid resource unit registry")
        self._graphs = {}
        self._ready = {}  # owner -> stable submission sequence, including resource waiters
        self._sequence = 0
        self._now = 0.0
        self._in_callback = False

    @property
    def now(self):
        return self._now

    @property
    def graphs(self):
        """Detached inspection snapshots; callers cannot mutate engine state."""
        # Bound callbacks may capture a simulator, locks or file handles. Keep their
        # identity while copying runtime data, without traversing the host object.
        return deepcopy(self._graphs, {id(g.callback): g.callback for g in self._graphs.values()})

    def _check_now(self, now):
        if self._in_callback:
            raise RuntimeError("terminal callback cannot reenter the executor")
        now = finite_nonnegative(now)
        if now < self._now:
            raise ValueError(f"time went backwards: {now} < {self._now}")
        return now

    def _validate_demands(self, fragment):
        for task in fragment.tasks:
            for demand in task.demands:
                if self.resource_mode == "dependency_only":
                    continue
                if self._resources is None:
                    raise ValueError("resource demands require a ResourceManager or explicit dependency_only mode")
                if self._resource_units.get(demand.resource_id) != demand.unit:
                    raise ValueError(f"unknown resource or unit mismatch: {demand.resource_id}")

    def _make_ready(self, graph_id, task, now):
        if task.state != TaskState.PENDING or task.remaining_predecessors != 0:
            raise RuntimeError("illegal READY transition")
        task.state = TaskState.READY
        task.ready_at = now
        self._ready[(graph_id, task.spec.task_id)] = task.sequence

    def submit(self, fragment: GraphFragment, now, terminal_callback):
        now = self._check_now(now)
        fragment = snapshot_graph(fragment)
        if fragment.graph_id in self._graphs:
            raise ValueError(f"duplicate graph ID: {fragment.graph_id}")
        if not callable(terminal_callback):
            raise ValueError("terminal_callback must be callable")
        self._validate_demands(fragment)
        tasks = {spec.task_id: TaskRuntime(spec, self._sequence + i, 0)
                 for i, spec in enumerate(fragment.tasks)}
        for source, target in fragment.edges:
            tasks[source].successors.append(target)
            tasks[target].remaining_predecessors += 1
        self._sequence += len(tasks)
        self._graphs[fragment.graph_id] = GraphRuntime(fragment, tasks, terminal_callback, now)
        self._now = now
        for task in tasks.values():
            if task.remaining_predecessors == 0:
                self._make_ready(fragment.graph_id, task, now)
        return GraphHandle(fragment.graph_id, self.dispatch(now))

    def dispatch(self, now):
        now = self._check_now(now)
        self._now = now
        events = []
        for owner in sorted(tuple(self._ready), key=self._ready.__getitem__):
            # A previous resource failure may have removed the rest of its graph.
            if owner not in self._ready:
                continue
            graph = self._graphs[owner[0]]
            task = graph.tasks[owner[1]]
            if graph.state != "ACTIVE":
                continue
            finish = now + task.spec.cost.duration_s
            if not math.isfinite(finish):
                events.extend(self._fail_graph(owner, now, "completion time overflow"))
                continue
            if task.spec.cost.duration_s > 0 and finish == now:
                events.extend(self._fail_graph(owner, now, "positive duration lost at current float time precision"))
                continue
            try:
                lease = (self._resources.try_acquire(owner, task.spec.demands)
                         if self._resources is not None else None)
                if self._resources is not None and lease is None:
                    if task.resource_wait_started_at is None:
                        task.resource_wait_started_at = now
                    continue
                if lease is not None:
                    if not isinstance(lease, Lease):
                        raise RuntimeError("resource manager returned an invalid lease")
                    task.lease = lease
                    if (lease.owner != owner or lease.demands != task.spec.demands
                            or not isinstance(lease.lease_id, str) or not lease.lease_id):
                        raise RuntimeError("resource manager returned an invalid lease")
            except Exception as exc:
                events.extend(self._fail_graph(owner, now, f"resource acquire failed: {exc}"))
                continue
            del self._ready[owner]
            task.state = TaskState.RUNNING
            task.start_at = now
            task.scheduled_finish_at = finish
            if task.resource_wait_started_at is not None:
                task.resource_wait_s += now - task.resource_wait_started_at
                task.resource_wait_started_at = None
            events.append(EventIntent(finish, "task_complete", owner))
        return tuple(events)

    def _task(self, graph_id, task_id):
        if graph_id not in self._graphs or task_id not in self._graphs[graph_id].tasks:
            raise RuntimeError(f"unknown task: {(graph_id, task_id)}")
        graph = self._graphs[graph_id]
        return graph, graph.tasks[task_id]

    def _release(self, task, now):
        if task.lease is None:
            return ()
        if task.release_attempted:
            raise RuntimeError("lease release already attempted")
        task.release_attempted = True
        wakeups = self._resources.release(task.lease, now)
        # A successful release clears ownership even if its wakeup payload is invalid.
        task.lease = None
        if not isinstance(wakeups, tuple):
            raise RuntimeError("resource release must return a Wakeups tuple")
        for owner in wakeups:
            if (not isinstance(owner, tuple) or len(owner) != 2
                    or any(not isinstance(part, str) or not part for part in owner)):
                raise RuntimeError("invalid resource wakeup owner")
        return wakeups

    def on_task_complete(self, graph_id, task_id, now):
        now = self._check_now(now)
        graph, task = self._task(graph_id, task_id)
        if graph.state == "FAILED":
            self._now = now
            return ()  # Events scheduled before graph failure are intentionally stale.
        if task.state != TaskState.RUNNING:
            raise RuntimeError(f"completion requires RUNNING, got {task.state.value}")
        if now != task.scheduled_finish_at:
            raise RuntimeError(f"completion time mismatch: expected {task.scheduled_finish_at}, got {now}")
        self._now = now
        try:
            self._release(task, now)
        except Exception as exc:
            return self._fail_graph((graph_id, task_id), now, f"resource release failed: {exc}")
        task.state = TaskState.COMPLETED
        task.end_at = now
        task.completion_count += 1
        graph.completed_count += 1
        for successor in task.successors:
            child = graph.tasks[successor]
            child.remaining_predecessors -= 1
            if child.remaining_predecessors == 0:
                self._make_ready(graph_id, child, now)
        callback_events = ()
        if task_id == graph.fragment.terminal_task_id:
            graph.callback_count += 1  # Mark before invocation, including exception paths.
            try:
                self._in_callback = True
                callback_events = graph.callback(graph_id, now)
                self._validate_events(callback_events, now)
            except Exception as exc:
                return self._fail_graph((graph_id, task_id), now, f"terminal callback failed: {exc}")
            finally:
                self._in_callback = False
            graph.state = "COMPLETED"
            graph.finished_at = now
        return callback_events + self.dispatch(now)

    @staticmethod
    def _validate_events(events, now):
        if not isinstance(events, tuple):
            raise ValueError("callback must return an EventIntents tuple")
        for event in events:
            if not isinstance(event, EventIntent) or event.kind not in ("task_complete", "dispatch", "graph_failed"):
                raise ValueError("invalid event intent")
            if finite_nonnegative(event.time_s) < now:
                raise ValueError("cannot schedule a past event")
            if (not isinstance(event.owner, tuple) or len(event.owner) != 2
                    or any(not isinstance(part, str) or not part for part in event.owner)):
                raise ValueError("invalid event owner")

    def _fail_graph(self, owner, now, reason):
        graph, failed = self._task(*owner)
        if graph.state == "FAILED":
            return ()
        graph.state = "FAILED"
        graph.failure = reason
        graph.finished_at = now
        failed.state = TaskState.FAILED
        failed.failure = reason
        for task in graph.tasks.values():
            self._ready.pop((owner[0], task.spec.task_id), None)
            if task.state == TaskState.RUNNING:
                task.state = TaskState.FAILED
                task.failure = reason
            if task.lease is not None and not task.release_attempted:
                try:
                    self._release(task, now)
                except Exception as exc:
                    graph.cleanup_errors.append(f"{task.spec.task_id}: {exc}")
            if task.lease is not None:
                graph.cleanup_errors.append(f"{task.spec.task_id}: lease release not confirmed")
        return (EventIntent(now, "graph_failed", owner),)

    def fail_task(self, graph_id, task_id, now, reason):
        """Optional host failure hook; no retries or preemption are implied."""
        now = self._check_now(now)
        graph, task = self._task(graph_id, task_id)
        if graph.state != "ACTIVE" or task.state != TaskState.RUNNING:
            raise RuntimeError("host failure requires an active RUNNING task")
        self._now = now
        return self._fail_graph((graph_id, task_id), now, str(reason))

    def append(self, patch: GraphAppend, now):
        now = self._check_now(now)
        if not isinstance(patch, GraphAppend) or not isinstance(patch.graph_id, str):
            raise ValueError("expected GraphAppend with string graph_id")
        if patch.graph_id not in self._graphs:
            raise ValueError(f"append references unknown graph: {patch.graph_id}")
        graph = self._graphs[patch.graph_id]
        terminal = graph.tasks[graph.fragment.terminal_task_id]
        if graph.state != "ACTIVE" or terminal.state != TaskState.PENDING:
            raise ValueError("append requires an active graph with PENDING terminal")
        if not isinstance(patch.tasks, tuple) or not isinstance(patch.edges, tuple):
            raise ValueError("GraphAppend tasks and edges must be tuples")
        # Validate the complete candidate and allocate its indices before mutating
        # any live graph, READY entry, counter, sequence or clock.
        candidate = snapshot_graph(replace(graph.fragment,
                                          tasks=graph.fragment.tasks + patch.tasks,
                                          edges=graph.fragment.edges + patch.edges))
        self._validate_demands(candidate)
        for _, target in patch.edges:
            if target in graph.tasks and graph.tasks[target].state != TaskState.PENDING:
                raise ValueError(f"append edge target must be PENDING: {target}")
        new_specs = [t for t in candidate.tasks if t.task_id not in graph.tasks]
        new_tasks = {spec.task_id: TaskRuntime(spec, self._sequence+i, 0)
                     for i, spec in enumerate(new_specs)}
        merged = {**graph.tasks, **new_tasks}
        successors = {tid: [] for tid in merged}
        remaining = dict.fromkeys(merged, 0)
        for source, target in candidate.edges:
            successors[source].append(target)
            if merged[source].state != TaskState.COMPLETED:
                remaining[target] += 1
        graph.fragment = candidate
        graph.tasks = merged
        self._sequence += len(new_tasks)
        self._now = now
        for spec in candidate.tasks:
            task = merged[spec.task_id]
            task.spec = spec
            task.successors = successors[spec.task_id]
            if task.state == TaskState.PENDING:
                task.remaining_predecessors = remaining[spec.task_id]
                if task.remaining_predecessors == 0:
                    self._make_ready(patch.graph_id, task, now)
        return self.dispatch(now)
