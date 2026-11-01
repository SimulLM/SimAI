"""DAG v1 contracts only; no scheduler, resource implementation or Vidur imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal, Mapping, Protocol

TaskKind = Literal["coarse", "compute", "comm", "sync"]
ResourceUnit = Literal["permits", "bytes"]
Owner = tuple[str, str]  # graph_id, task_id


class TaskState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class GraphContext:
    batch_id: str
    iteration_id: int
    replica_id: str
    stage_id: int
    request_ids: tuple[str, ...]


@dataclass(frozen=True)
class Placement:
    device_ids: tuple[str, ...] = ()
    comm_group: str | None = None


@dataclass(frozen=True)
class ResourceDemand:
    resource_id: str
    amount: int
    unit: ResourceUnit


@dataclass(frozen=True)
class CostEstimate:
    duration_s: float
    source: str
    raw_value: float
    raw_unit: Literal["s", "ms", "us", "ns"]
    conversion_to_s: float
    evidence: str
    includes: tuple[str, ...]
    unknown_components: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    kind: TaskKind
    placement: Placement
    demands: tuple[ResourceDemand, ...]
    cost: CostEstimate
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphFragment:
    schema_version: Literal["1.0"]
    graph_id: str
    context: GraphContext
    tasks: tuple[TaskSpec, ...]
    edges: tuple[tuple[str, str], ...]
    terminal_task_id: str


@dataclass(frozen=True)
class GraphAppend:
    """Append-only patch; edges may reference existing or newly added task IDs."""
    graph_id: str
    tasks: tuple[TaskSpec, ...]
    edges: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EventIntent:
    time_s: float
    kind: Literal["task_complete", "dispatch", "graph_failed"]
    owner: Owner


EventIntents = tuple[EventIntent, ...]
Wakeups = tuple[Owner, ...]
TerminalCallback = Callable[[str, float], EventIntents]


@dataclass(frozen=True)
class GraphHandle:
    graph_id: str
    initial_events: EventIntents


@dataclass(frozen=True)
class Lease:
    lease_id: str
    owner: Owner
    demands: tuple[ResourceDemand, ...]


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    owner: Owner
    resource_id: str
    storage_bytes: int


@dataclass(frozen=True)
class Pin:
    pin_id: str
    owner: Owner
    allocation_id: str


class GraphBuilder(Protocol):
    def build(self, context: GraphContext) -> GraphFragment: ...


class CostProvider(Protocol):
    def estimate(self, task: TaskSpec, context: GraphContext) -> CostEstimate: ...


class DagExecutor(Protocol):
    def submit(self, fragment: GraphFragment, now: float,
               terminal_callback: TerminalCallback) -> GraphHandle: ...
    def on_task_complete(self, graph_id: str, task_id: str,
                         now: float) -> EventIntents: ...
    def dispatch(self, now: float) -> EventIntents: ...
    def append(self, fragment: GraphAppend, now: float) -> EventIntents: ...


class ResourceManager(Protocol):
    def try_acquire(self, owner: Owner,
                    demands: tuple[ResourceDemand, ...]) -> Lease | None: ...
    def release(self, lease: Lease, now: float) -> Wakeups: ...


class KVCapacity(Protocol):
    def reserve(self, owner: Owner, resource_id: str,
                storage_bytes: int) -> Reservation | None: ...
    def commit(self, reservation: Reservation, allocation_id: str) -> None: ...
    def release(self, reservation: Reservation, now: float) -> Wakeups: ...
    def pin(self, owner: Owner, allocation_id: str) -> Pin: ...
    def unpin(self, pin: Pin, now: float) -> Wakeups: ...
