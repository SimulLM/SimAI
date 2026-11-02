"""Internal mutable execution state. Public readers receive copied snapshots."""
from dataclasses import dataclass, field

from schemas.dag.v1.contracts import GraphFragment, Lease, TaskSpec, TaskState, TerminalCallback


@dataclass
class TaskRuntime:
    spec: TaskSpec
    sequence: int
    remaining_predecessors: int
    successors: list[str] = field(default_factory=list)
    state: TaskState = TaskState.PENDING
    ready_at: float | None = None
    start_at: float | None = None
    end_at: float | None = None
    scheduled_finish_at: float | None = None
    lease: Lease | None = None
    release_attempted: bool = False
    resource_wait_started_at: float | None = None
    resource_wait_s: float = 0.0
    completion_count: int = 0
    failure: str | None = None


@dataclass
class GraphRuntime:
    fragment: GraphFragment
    tasks: dict[str, TaskRuntime]
    callback: TerminalCallback
    submitted_at: float
    state: str = "ACTIVE"
    finished_at: float | None = None
    callback_count: int = 0
    completed_count: int = 0
    failure: str | None = None
    cleanup_errors: list[str] = field(default_factory=list)
