"""Fixed-group diagnostic with exclusive decode slot; not pristine or natural."""
import json,math,os
from vidur.events.batch_end_event import DecodeReadyEnqueueEvent
from vidur.events.base_event import BaseEvent
from vidur.events.replica_schedule_event import ReplicaScheduleEvent
from vidur.types import EventType
cfg=json.load(open(os.environ['FIXED_GROUPS_CONFIG']));trace=os.environ['FIXED_GROUPS_TRACE'];groups=[];by_id={};pending={};ready={};started=set();finished=set()
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
  if rs._num_running_batches!=1:raise RuntimeError('decode slot lost')
  rs._num_running_batches-=1
  for rid in ids:
   request=pending[rid]
   if request in rs._request_queue:raise RuntimeError('duplicate enqueue')
   rs._request_queue.append(request)
  finished.add(self.index);record({'event':'complete','group':self.index,'request_ids':ids,'time_s':self.time});return [ReplicaScheduleEvent(self.time,self.replica_id)]
 def to_dict(self):return {'time':self.time,'event_type':'fixed_group_complete','group':self.index,'replica_id':self.replica_id}
def enqueue(self,scheduler,metrics_store):
 rid=str(self.request.id)
 if rid not in by_id or rid in pending or self.time<self.request.decode_arrived_at:raise RuntimeError('unexpected, duplicate or premature request')
 pending[rid]=self.request;index=by_id[rid];ids,_=groups[index]
 if not all(x in pending for x in ids):return []
 if index in ready or len({pending[x].decode_replica_id for x in ids})!=1:raise RuntimeError('invalid group')
 ready[index]=(self.replica_id,self.time);return [ReplicaScheduleEvent(self.time,self.replica_id)]
old_schedule=ReplicaScheduleEvent.handle_event
def schedule(self,scheduler,metrics_store):
 replica=self._replica_id;rs=scheduler.get_replica_scheduler(replica)
 eligible=sorted((t,i) for i,(r,t) in ready.items() if r==replica and i not in started)
 if eligible and rs._num_running_batches==0:
  ready_time,index=eligible[0];ids,cost=groups[index];started.add(index);rs._num_running_batches+=1
  record({'event':'submit','group':index,'request_ids':ids,'ready_s':ready_time,'time_s':self.time,'cost_s':cost});return [GroupComplete(self.time+cost,replica,index)]
 return old_schedule(self,scheduler,metrics_store)
DecodeReadyEnqueueEvent.handle_event=enqueue
ReplicaScheduleEvent.handle_event=schedule
from vidur.main import main
main()
if finished!=set(range(len(groups))) or set(pending)!=set(by_id):raise RuntimeError('incomplete fixed groups')
