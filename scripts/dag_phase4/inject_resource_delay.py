"""Controlled CLI probe: hold the first Stage permit until 10ms, then dispatch.

This process-local injection exercises the original Simulator, StageEnd, request
updates and metrics; it does not replace the predictor or completion handlers.
"""
from schemas.dag.v1.contracts import ResourceDemand
from vidur.events.base_event import BaseEvent
from vidur.simulator import Simulator
from vidur.types import EventType
from vidur.main import main

DELAY_S = 0.01
original_init = Simulator.__init__


class ReleasePermit(BaseEvent):
    def __init__(self, adapter, lease):
        super().__init__(DELAY_S, EventType.DAG)
        self.adapter = adapter
        self.lease = lease

    def handle_event(self, scheduler, metrics_store):
        self.adapter.executor._resources.release(self.lease, self.time)
        return self.adapter._wrap(self.adapter.executor.dispatch(self.time))


def initialize(self, config):
    original_init(self, config)
    adapter = self.scheduler.dag_adapter
    resource = next(iter(adapter.executor._resources.usage_snapshot()))
    lease = adapter.executor._resources.try_acquire(
        ("external", "phase4-delay-holder"), (ResourceDemand(resource, 1, "permits"),))
    self._add_event(ReleasePermit(adapter, lease))


if __name__ == "__main__":
    Simulator.__init__ = initialize
    main()
