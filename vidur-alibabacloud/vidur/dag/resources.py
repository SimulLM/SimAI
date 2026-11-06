"""Deterministic capacity accounting for DAG task and KV resources."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math
from typing import Mapping

from schemas.dag.v1.contracts import (
    Lease,
    Owner,
    Pin,
    Reservation,
    ResourceDemand,
)


@dataclass(frozen=True)
class ResourceCapacity:
    """The fixed capacity and unit of one named resource."""

    amount: int
    unit: str


@dataclass(frozen=True)
class ResourceInterval:
    """One completed task-resource occupancy interval, expressed in seconds."""

    resource_id: str
    unit: str
    amount: int
    owner: Owner
    start_s: float
    end_s: float


@dataclass
class _StoredReservation:
    reservation: Reservation
    allocation_id: str | None = None


class CapacityResourceManager:
    """A deterministic, atomic manager for permit and byte capacities.

    ``capacities`` maps each resource ID to ``ResourceCapacity(amount, unit)``.
    A failed acquisition changes no usage counter.  The manager deliberately does
    not impose a scheduling policy: it returns all known waiters in stable arrival
    order and leaves the executor to apply its existing stable READY ordering.
    """

    def __init__(self, capacities: Mapping[str, ResourceCapacity]):
        if not isinstance(capacities, Mapping) or not capacities:
            raise ValueError("capacities must be a non-empty mapping")
        self._capacities = {}
        for resource_id, capacity in capacities.items():
            self._validate_capacity(resource_id, capacity)
            self._capacities[resource_id] = capacity
        self._used = {resource_id: 0 for resource_id in self._capacities}
        self._leases: dict[str, Lease] = {}
        self._owner_leases: dict[Owner, str] = {}
        self._waiters: OrderedDict[Owner, None] = OrderedDict()
        self._next_lease = 0
        self._reservations: dict[str, _StoredReservation] = {}
        self._allocations: dict[str, str] = {}
        self._pins: dict[str, Pin] = {}
        self._pin_counts: dict[str, int] = {}
        self._next_reservation = 0
        self._next_pin = 0

    @staticmethod
    def _valid_owner(owner: Owner) -> bool:
        return (isinstance(owner, tuple) and len(owner) == 2
                and all(isinstance(part, str) and part for part in owner))

    @staticmethod
    def _valid_amount(amount: int) -> bool:
        return isinstance(amount, int) and not isinstance(amount, bool) and amount > 0

    def _validate_capacity(self, resource_id: str, capacity: ResourceCapacity) -> None:
        if not isinstance(resource_id, str) or not resource_id:
            raise ValueError("resource ID must be a non-empty string")
        if not isinstance(capacity, ResourceCapacity):
            raise ValueError("capacity must be a ResourceCapacity")
        if not self._valid_amount(capacity.amount):
            raise ValueError("resource capacity must be a positive integer")
        if capacity.unit not in ("permits", "bytes"):
            raise ValueError("resource capacity unit must be permits or bytes")

    def _validate_demands(self, demands: tuple[ResourceDemand, ...]) -> None:
        if not isinstance(demands, tuple):
            raise ValueError("demands must be a tuple")
        seen = set()
        for demand in demands:
            if not isinstance(demand, ResourceDemand):
                raise ValueError("invalid resource demand")
            if demand.resource_id in seen:
                raise ValueError("duplicate resource demand")
            seen.add(demand.resource_id)
            capacity = self._capacities.get(demand.resource_id)
            if capacity is None:
                raise ValueError(f"unknown resource: {demand.resource_id}")
            if demand.unit != capacity.unit:
                raise ValueError(f"resource unit mismatch: {demand.resource_id}")
            if not self._valid_amount(demand.amount):
                raise ValueError("resource demand amount must be a positive integer")
            if demand.amount > capacity.amount:
                raise ValueError(f"resource demand exceeds capacity: {demand.resource_id}")

    def try_acquire(self, owner: Owner, demands: tuple[ResourceDemand, ...]) -> Lease | None:
        """Atomically acquire every demand, or record a waiter and acquire none."""
        if not self._valid_owner(owner):
            raise ValueError("owner must be a pair of non-empty strings")
        self._validate_demands(demands)
        if owner in self._owner_leases:
            raise RuntimeError(f"owner already has a lease: {owner}")
        if any(self._used[d.resource_id] + d.amount > self._capacities[d.resource_id].amount
               for d in demands):
            self._waiters.setdefault(owner, None)
            return None
        for demand in demands:
            self._used[demand.resource_id] += demand.amount
        self._next_lease += 1
        lease = Lease(f"capacity:{self._next_lease}", owner, demands)
        self._leases[lease.lease_id] = lease
        self._owner_leases[owner] = lease.lease_id
        self._waiters.pop(owner, None)
        return lease

    def _wakeups(self) -> tuple[Owner, ...]:
        return tuple(self._waiters)

    def _release_lease(self, lease: Lease) -> tuple[Owner, ...]:
        stored = self._leases.get(lease.lease_id)
        if stored != lease:
            raise RuntimeError(f"duplicate or unknown lease release: {lease.lease_id}")
        for demand in lease.demands:
            self._used[demand.resource_id] -= demand.amount
            if self._used[demand.resource_id] < 0:
                raise RuntimeError("resource usage became negative")
        del self._leases[lease.lease_id]
        del self._owner_leases[lease.owner]
        return self._wakeups()

    def reserve(self, owner: Owner, resource_id: str, storage_bytes: int) -> Reservation | None:
        """Reserve byte capacity for KV data without creating a task lease."""
        if not self._valid_owner(owner):
            raise ValueError("owner must be a pair of non-empty strings")
        capacity = self._capacities.get(resource_id)
        if capacity is None or capacity.unit != "bytes":
            raise ValueError("KV capacity must name a registered byte resource")
        if not self._valid_amount(storage_bytes):
            raise ValueError("KV storage bytes must be a positive integer")
        if storage_bytes > capacity.amount:
            raise ValueError(f"KV reservation exceeds capacity: {resource_id}")
        if self._used[resource_id] + storage_bytes > capacity.amount:
            self._waiters.setdefault(owner, None)
            return None
        self._used[resource_id] += storage_bytes
        self._next_reservation += 1
        reservation = Reservation(
            f"kv-reservation:{self._next_reservation}", owner, resource_id, storage_bytes
        )
        self._reservations[reservation.reservation_id] = _StoredReservation(reservation)
        self._waiters.pop(owner, None)
        return reservation

    def commit(self, reservation: Reservation, allocation_id: str) -> None:
        stored = self._stored_reservation(reservation)
        if stored.allocation_id is not None:
            raise RuntimeError("reservation has already been committed")
        if not isinstance(allocation_id, str) or not allocation_id:
            raise ValueError("allocation ID must be a non-empty string")
        if allocation_id in self._allocations:
            raise RuntimeError(f"allocation already exists: {allocation_id}")
        stored.allocation_id = allocation_id
        self._allocations[allocation_id] = reservation.reservation_id
        self._pin_counts[allocation_id] = 0

    def _stored_reservation(self, reservation: Reservation) -> _StoredReservation:
        if not isinstance(reservation, Reservation):
            raise ValueError("expected a Reservation")
        stored = self._reservations.get(reservation.reservation_id)
        if stored is None or stored.reservation != reservation:
            raise RuntimeError(f"duplicate or unknown reservation: {reservation.reservation_id}")
        return stored

    def pin(self, owner: Owner, allocation_id: str) -> Pin:
        if not self._valid_owner(owner):
            raise ValueError("owner must be a pair of non-empty strings")
        if allocation_id not in self._allocations:
            raise RuntimeError(f"unknown KV allocation: {allocation_id}")
        self._next_pin += 1
        pin = Pin(f"kv-pin:{self._next_pin}", owner, allocation_id)
        self._pins[pin.pin_id] = pin
        self._pin_counts[allocation_id] += 1
        return pin

    def unpin(self, pin: Pin, now: float) -> tuple[Owner, ...]:
        self._validate_time(now)
        stored = self._pins.get(pin.pin_id) if isinstance(pin, Pin) else None
        if stored != pin:
            raise RuntimeError(f"duplicate or unknown pin: {getattr(pin, 'pin_id', pin)}")
        del self._pins[pin.pin_id]
        self._pin_counts[pin.allocation_id] -= 1
        return self._wakeups()

    @staticmethod
    def _validate_time(now: float) -> None:
        if not isinstance(now, (float, int)) or isinstance(now, bool) or not math.isfinite(now) or now < 0:
            raise ValueError("time must be finite and nonnegative")

    def _release_reservation(self, reservation: Reservation) -> tuple[Owner, ...]:
        stored = self._stored_reservation(reservation)
        if stored.allocation_id is not None and self._pin_counts[stored.allocation_id]:
            raise RuntimeError("cannot release a pinned KV allocation")
        self._used[reservation.resource_id] -= reservation.storage_bytes
        if self._used[reservation.resource_id] < 0:
            raise RuntimeError("resource usage became negative")
        del self._reservations[reservation.reservation_id]
        if stored.allocation_id is not None:
            del self._allocations[stored.allocation_id]
            del self._pin_counts[stored.allocation_id]
        return self._wakeups()

    def release(self, handle: Lease | Reservation, now: float) -> tuple[Owner, ...]:
        """Release a task lease or a KV reservation exactly once."""
        self._validate_time(now)
        if isinstance(handle, Lease):
            return self._release_lease(handle)
        if isinstance(handle, Reservation):
            return self._release_reservation(handle)
        raise ValueError("release expects a Lease or Reservation")

    def usage_snapshot(self) -> dict[str, dict[str, int | str]]:
        """Return a detached capacity/usage view suitable for reports."""
        return {
            resource_id: {
                "unit": capacity.unit,
                "capacity": capacity.amount,
                "used": self._used[resource_id],
                "available": capacity.amount - self._used[resource_id],
            }
            for resource_id, capacity in self._capacities.items()
        }


def resource_timeline(executor) -> tuple[ResourceInterval, ...]:
    """Build a deterministic resource timeline from completed executor tasks."""
    intervals = []
    for graph_id, graph in sorted(executor.graphs.items()):
        for task_id, task in sorted(graph.tasks.items(), key=lambda item: item[1].sequence):
            if task.start_at is None or task.end_at is None:
                continue
            for demand in task.spec.demands:
                intervals.append(ResourceInterval(
                    demand.resource_id, demand.unit, demand.amount, (graph_id, task_id),
                    task.start_at, task.end_at,
                ))
    return tuple(intervals)
