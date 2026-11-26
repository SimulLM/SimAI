"""Opt-in shared consumer-first-token diagnostic for DAG pull batches only."""
import json,math,os
from schemas.dag.v1.contracts import CostEstimate,GraphContext,GraphFragment,Placement,ResourceDemand,TaskSpec
from vidur.dag.pd_host import PDCoordinator,PDActionEvent
from vidur.events.replica_schedule_event import ReplicaScheduleEvent

def enable():
 costs=json.loads(open(os.environ['BATCH_FIRST_TOKEN_COSTS']).read());trace=os.environ['BATCH_FIRST_TOKEN_TRACE']
 if not costs or any(not isinstance(k,str) or not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<=0 for k,v in costs.items()):raise ValueError('invalid first-token diagnostic costs')
 old_release=PDCoordinator._release_pull_batch;old_handle=PDActionEvent.handle_event
 def record(obj):
  with open(trace,'a') as f:f.write(json.dumps(obj,separators=(',',':'))+'\n')
 def release(self,m,now):
  if self.config.transfer_start_mode!='decode_pull_candidate' or self.config.consumer_first_token_host_s:raise RuntimeError('batch first-token diagnostic requires pull mode and zero serial diagnostic')
  group=self.pull_groups[m.destination]
  if any(self.migrations[x].state=='PULL_QUEUED' for x in group):return old_release(self,m,now)
  if any(self.migrations[x].state!='KV_READY' for x in group):raise RuntimeError('first-token batch requires every KV ready')
  lengths={int(self.requests[x].num_prefill_tokens) for x in group}
  if len(lengths)!=1:raise ValueError('first-token mixed input lengths unsupported')
  key=f'{next(iter(lengths))}:{len(group)}'
  if key not in costs:raise ValueError('unmeasured first-token batch '+key)
  ids=tuple(group);duration=costs[key];destination=self.layouts[m.destination].shards(m.destination)[0];gid='pd/batch-first/'+','.join(ids)
  task=TaskSpec('consumer.first_token.batch','compute',Placement((destination,),gid),(ResourceDemand(destination,1,'permits'),),CostEstimate(duration,'diagnostic.batch_first_token',duration,'s',1,'explicit diagnostic cost table',('compute','cpu')),{ 'request_ids':ids,'diagnostic_only':True,'contains_cpu_gpu_wait':True})
  terminal=TaskSpec('terminal','sync',Placement(),(),CostEstimate(0,'join',0,'s',1,'batch first-token completed',('sync',)))
  graph=GraphFragment('1.0',gid,GraphContext(gid,0,str(m.destination),0,ids),(task,terminal),((task.task_id,'terminal'),),'terminal')
  for rid in ids:self.migrations[rid].state='FIRST_TOKEN_BATCH_RUNNING'
  def completed(graph_id,t):self.adapter._outbox.append(PDActionEvent(self,t,'batch_first_token_done',','.join(ids)));return ()
  event=PDActionEvent(self,now,'batch_first_token_done',','.join(ids));self.adapter.graph_anchors[gid]=event.id
  record({'event':'submit','request_ids':ids,'time_s':now,'cost_s':duration,'key':key,'graph_id':gid})
  handle=self.adapter.executor.submit(graph,now,completed);return self.adapter._wrap(handle.initial_events)
 def handle(self,scheduler,metrics_store):
  if self.operation!='batch_first_token_done':return old_handle(self,scheduler,metrics_store)
  pd=self.coordinator
  if pd.failure:return []
  pd.now=self.time;ids=self.request_id.split(',');m=pd.migrations[ids[0]]
  if tuple(pd.pull_groups[m.destination])!=tuple(ids) or any(pd.migrations[rid].state!='FIRST_TOKEN_BATCH_RUNNING' for rid in ids):raise RuntimeError('stale or duplicate first-token batch completion')
  for rid in ids:pd.migrations[rid].state='KV_READY'
  record({'event':'complete','request_ids':ids,'time_s':self.time})
  return old_release(pd,m,self.time)
 PDCoordinator._release_pull_batch=release;PDActionEvent.handle_event=handle
