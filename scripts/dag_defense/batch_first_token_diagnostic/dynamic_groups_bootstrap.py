"""Opt-in readiness-corrected baseline with dynamic first-token groups; diagnostic only."""
import collections,json,math,os
from vidur.events.batch_end_event import DecodeReadyEnqueueEvent
from vidur.events.base_event import BaseEvent
from vidur.events.replica_schedule_event import ReplicaScheduleEvent
from vidur.types import EventType
costs=json.load(open(os.environ['BATCH_FIRST_TOKEN_COSTS']));trace=os.environ['BATCH_FIRST_TOKEN_TRACE'];waiting=collections.defaultdict(collections.OrderedDict);seen=set();finished=set()
if not costs or any(not isinstance(v,(float,int)) or isinstance(v,bool) or not math.isfinite(v) or v<=0 for v in costs.values()):raise ValueError('invalid fee table')
def record(row):
 with open(trace,'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
class GroupComplete(BaseEvent):
 def __init__(self,time,replica,ids):super().__init__(time,EventType.REPLICA_SCHEDULE);self.replica=replica;self.ids=ids
 def handle_event(self,scheduler,metrics_store):
  rs=scheduler.get_replica_scheduler(self.replica)
  if rs._num_running_batches!=1:raise RuntimeError('decode slot lost')
  rs._num_running_batches-=1
  for rid,request in self.ids:
   if rid in finished or request in rs._request_queue:raise RuntimeError('duplicate release')
   finished.add(rid);rs._request_queue.append(request)
  record({'event':'complete','request_ids':[x[0] for x in self.ids],'time_s':self.time});return [ReplicaScheduleEvent(self.time,self.replica)]
 def to_dict(self):return {'time':self.time,'event_type':'diagnostic_first_token_complete','replica_id':self.replica,'request_ids':[x[0] for x in self.ids]}
def enqueue(self,scheduler,metrics_store):
 rid=str(self.request.id)
 if rid in seen or self.time<self.request.decode_arrived_at:raise RuntimeError('duplicate or premature readiness')
 seen.add(rid);waiting[self.replica_id][rid]=self.request;return [ReplicaScheduleEvent(self.time,self.replica_id)]
old_schedule=ReplicaScheduleEvent.handle_event
def schedule(self,scheduler,metrics_store):
 replica=self._replica_id;rs=scheduler.get_replica_scheduler(replica);queue=waiting[replica]
 if queue and rs._num_running_batches==0:
  selected=[];tokens=0;length=None;limit=min(rs._max_batch_size,rs._max_micro_batch_size)
  for rid,r in queue.items():
   raw=r.num_prefill_tokens
   if not math.isfinite(raw) or raw!=int(raw) or raw<=0:raise ValueError('invalid input length')
   n=int(raw)
   if length is None:length=n
   if n!=length or len(selected)>=limit or tokens+n>rs._config.max_tokens_in_batch:break
   selected.append((rid,r));tokens+=n
  if not selected:raise RuntimeError('no feasible group')
  key=f'{length}:{len(selected)}'
  if key not in costs:raise ValueError('unmeasured first-token batch '+key)
  for rid,_ in selected:del queue[rid]
  rs._num_running_batches+=1;duration=costs[key];record({'event':'submit','request_ids':[x[0] for x in selected],'time_s':self.time,'key':key,'cost_s':duration});return [GroupComplete(self.time+duration,replica,selected)]
 return old_schedule(self,scheduler,metrics_store)
DecodeReadyEnqueueEvent.handle_event=enqueue;ReplicaScheduleEvent.handle_event=schedule
from vidur.main import main
main()
if any(waiting.values()) or seen!=finished:raise RuntimeError('unfinished first-token groups')
