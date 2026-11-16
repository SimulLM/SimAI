"""KV lifecycle transactions owned by PD, independent of task leases."""
from dataclasses import dataclass, field


@dataclass
class Migration:
    request_id: str
    source: int
    destination: int
    storage_bytes: int
    wire_bytes: int
    state: str = "PREFILL_RUNNING"
    source_handles: list = field(default_factory=list)
    destination_handles: list = field(default_factory=list)
    pins: list = field(default_factory=list)
    graph_ids: list[str] = field(default_factory=list)
    graph_id: str | None = None
    prefill_completed_at_s: float | None = None
    destination_reserved_at_s: float | None = None
    kv_ready_at_s: float | None = None
    first_decode_start_s: float | None = None
    completed_at_s: float | None = None


class KVTransactions:
    def __init__(self, manager, layout):
        self.manager = manager
        self.layout = layout
        self.events = []
        self.cleanup_errors = []

    def record(self, now, operation, rid, handle=None):
        self.events.append(dict(time_s=now, operation=operation, request_id=str(rid),
            resource_id=handle.resource_id if handle is not None else None,
            storage_bytes=handle.storage_bytes if handle is not None else None,
            usage=self.manager.usage_snapshot()))

    def reserve(self, rid, replica, amount, phase, now):
        owner = (f"pd:{rid}", phase)
        handles = []
        try:
            for device in self.layout.shards(replica):
                handle = self.manager.reserve(owner, "kv:" + device, amount)
                if handle is None:
                    self.release(rid, handles, now)
                    self.manager.cancel_waiters((owner,))
                    return None
                handles.append(handle)
                self.record(now, "reserve", rid, handle)
        except Exception:
            self.release(rid, handles, now)
            self.manager.cancel_waiters((owner,))
            raise
        return handles

    def commit(self, rid, handles, phase, now):
        for index, handle in enumerate(handles):
            self.manager.commit(handle, f"pd:{rid}:{phase}:{index}")
            self.record(now, "commit", rid, handle)

    def pin(self, migration, now):
        for index, _ in enumerate(migration.source_handles):
            pin = self.manager.pin((f"pd:{migration.request_id}", "transfer"),
                                   f"pd:{migration.request_id}:source:{index}")
            migration.pins.append(pin)
        self.record(now, "pin", migration.request_id)

    def unpin(self, migration, now):
        while migration.pins:
            self.manager.unpin(migration.pins[-1], now)
            migration.pins.pop()
            self.record(now, "unpin", migration.request_id)

    def release(self, rid, handles, now):
        while handles:
            handle = handles[-1]
            self.manager.release(handle, now)
            handles.pop()
            self.record(now, "release", rid, handle)
