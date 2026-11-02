"""Explicit dependency-only resource double; not a capacity model."""
from schemas.dag.v1.contracts import Lease


class DependencyOnlyResources:
    """Accept demands without capacity accounting. Never use as hardware evidence."""

    def __init__(self):
        self.acquires = []
        self.releases = []
        self.active = {}
        self.blocked = set()

    def try_acquire(self, owner, demands):
        self.acquires.append(owner)
        if owner in self.blocked:
            return None
        if owner in self.active:
            raise RuntimeError(f"owner already has a lease: {owner}")
        lease = Lease(f"dependency-only:{len(self.acquires)}", owner, demands)
        self.active[owner] = lease
        return lease

    def release(self, lease, now):
        if self.active.get(lease.owner) != lease:
            raise RuntimeError(f"duplicate or unknown lease release: {lease.lease_id}")
        del self.active[lease.owner]
        self.releases.append(lease.owner)
        return ()
