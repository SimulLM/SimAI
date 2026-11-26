"""Fixed single receive-batch baseline diagnostic; not an unmodified baseline."""
import json,math,os
from vidur.events.batch_end_event import DecodeReadyEnqueueEvent
from vidur.events.base_event import BaseEvent
from vidur.events.replica_schedule_event import ReplicaScheduleEvent
from vidur.types import EventType
config=json.load(open(os.environ['FIXED_FIRST_TOKEN_CONFIG']));trace=os.environ['FIXED_FIRST_TOKEN_TRACE'];expected=tuple(str(x) for x in config['request_ids']);duration=float(config['cost_s'])
if not expected or len(set(expected))!=len(expected) or not math.isfinite(duration) or duration<=0:raise ValueError('invalid fixed batch configuration')
pending={};finished=set();scheduled=False
def record(row):
 with open(trace,'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
class FixedBatchComplete(BaseEvent):
 def __init__(self,time,replica_id):super().__init__(time,EventType.REPLICA_SCHEDULE);self.replica_id=replica_id
 def handle_event(self,scheduler,metrics_store):
  rs=scheduler.get_replica_scheduler(self.replica_id)
  if finished or set(pending)!=set(expected):raise RuntimeError('duplicate or incomplete fixed first-token group')
  for rid in expected:
   request=pending[rid]
   if request in rs._request_queue:raise RuntimeError('duplicate enqueue')
   rs._request_queue.append(request);finished.add(rid)
  record({'event':'complete','request_ids':expected,'time_s':self.time});return [ReplicaScheduleEvent(self.time,self.replica_id)]
 def to_dict(self):return {'time':self.time,'event_type':'fixed_first_token_complete','request_ids':expected}
def enqueue(self,scheduler,metrics_store):
 global scheduled
 rid=str(self.request.id)
 if rid not in expected or rid in pending or self.time<self.request.decode_arrived_at or scheduled:raise RuntimeError('unexpected or duplicate fixed batch arrival')
 pending[rid]=self.request
 if set(pending)!=set(expected):return []
 if len({x.decode_replica_id for x in pending.values()})!=1:raise RuntimeError('mixed destinations')
 scheduled=True;record({'event':'submit','request_ids':expected,'time_s':self.time,'cost_s':duration});return [FixedBatchComplete(self.time+duration,self.replica_id)]
DecodeReadyEnqueueEvent.handle_event=enqueue
from vidur.main import main
main()
if finished!=set(expected):raise RuntimeError('fixed diagnostic batch did not complete')
