"""Test diagnostic enqueue boundary against the modified original checkout."""
from types import SimpleNamespace
from vidur.events.batch_end_event import DecodeReadyEnqueueEvent
from vidur.events.replica_schedule_event import ReplicaScheduleEvent
request=SimpleNamespace(id=7,decode_arrived_at=2.0)
queue=[];scheduler=SimpleNamespace(get_replica_scheduler=lambda _:SimpleNamespace(_request_queue=queue))
try:DecodeReadyEnqueueEvent(1.999,1,request).handle_event(scheduler,None);raise AssertionError('premature enqueue accepted')
except RuntimeError:pass
assert queue==[]
events=DecodeReadyEnqueueEvent(2.0,1,request).handle_event(scheduler,None)
assert queue==[request] and len(events)==1 and isinstance(events[0],ReplicaScheduleEvent) and events[0].time==2.0
try:DecodeReadyEnqueueEvent(2.0,1,request).handle_event(scheduler,None);raise AssertionError('duplicate accepted')
except RuntimeError:pass
print('PASS: premature/duplicate enqueue rejected, on-time enqueue schedules worker')
