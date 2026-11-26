"""Fixed receive groups for diagnostic comparison; not pristine or natural scheduling."""
import json,math,os
from vidur.events.batch_end_event import DecodeReadyEnqueueEvent
from vidur.events.base_event import BaseEvent
from vidur.events.replica_schedule_event import ReplicaScheduleEvent
from vidur.types import EventType
cfg=json.load(open(os.environ['FIXED_GROUPS_CONFIG']));trace=os.environ['FIXED_GROUPS_TRACE'];groups=[];by_id={};pending={};started=set();finished=set();available={}
for i,g in enumerate(cfg['groups']):
 ids=tuple(str(x) for x in g['request_ids']);cost=float(g['cost_s'])
 if not ids or len(set(ids))!=len(ids) or not math.isfinite(cost) or cost<=0:raise ValueError('invalid fixed group')
 for rid in ids:
  if rid in by_id:raise ValueError('duplicate group member')
  by_id[rid]=i
 groups.append((ids,cost))
if not groups:raise ValueError('empty fixed groups')
def record(row):
 with open(trace,'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
class GroupComplete(BaseEvent):
 def __init__(self,time,replica_id,index):super().__init__(time,EventType.REPLICA_SCHEDULE);self.replica_id=replica_id;self.index=index
 def handle_event(self,scheduler,metrics_store):
  if self.index in finished:raise RuntimeError('duplicate group completion')
  ids,_=groups[self.index];rs=scheduler.get_replica_scheduler(self.replica_id)
  for rid in ids:
   request=pending[rid]
   if request in rs._request_queue:raise RuntimeError('duplicate enqueue')
   rs._request_queue.append(request)
  finished.add(self.index);record({'event':'complete','group':self.index,'request_ids':ids,'time_s':self.time});return [ReplicaScheduleEvent(self.time,self.replica_id)]
 def to_dict(self):return {'time':self.time,'event_type':'fixed_group_complete','group':self.index,'replica_id':self.replica_id}
def enqueue(self,scheduler,metrics_store):
 rid=str(self.request.id)
 if rid not in by_id or rid in pending or self.time<self.request.decode_arrived_at:raise RuntimeError('unexpected, duplicate or premature request')
 pending[rid]=self.request;index=by_id[rid];ids,cost=groups[index]
 if not all(x in pending for x in ids):return []
 if index in started or len({pending[x].decode_replica_id for x in ids})!=1:raise RuntimeError('invalid group')
 started.add(index);begin=max(self.time,available.get(self.replica_id,0));end=begin+cost;available[self.replica_id]=end
 record({'event':'submit','group':index,'request_ids':ids,'ready_s':self.time,'time_s':begin,'cost_s':cost});return [GroupComplete(end,self.replica_id,index)]
DecodeReadyEnqueueEvent.handle_event=enqueue
from vidur.main import main
main()
if finished!=set(range(len(groups))) or set(pending)!=set(by_id):raise RuntimeError('incomplete fixed groups')
