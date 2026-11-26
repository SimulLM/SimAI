"""Opt-in measured whole-forward *diagnostic* in adapted baseline and DAG.

Not the pristine baseline or a frozen cost model. See README in this directory.
"""
import json,os
from dataclasses import replace
from lookup import ForwardLookup,CoverageError
from vidur.execution_time_predictor.base_execution_time_predictor import BaseExecutionTimePredictor
from vidur.entities.execution_time import ExecutionTime
from schemas.dag.v1.contracts import CostEstimate,GraphFragment
lookup=ForwardLookup(os.environ['FORWARD_PREFILL_CSV'],os.environ['FORWARD_DECODE_CSV'],os.environ.get('FORWARD_PATTERN_CSV'))
mode=os.environ['FORWARD_DIAG_MODE'];trace=os.environ['FORWARD_DIAG_TRACE']
if mode not in ('baseline','dag'):raise ValueError('invalid FORWARD_DIAG_MODE')
orig_get=BaseExecutionTimePredictor.get_execution_time;orig_model=ExecutionTime.model_time.fget
def get(self,batch,pipeline_stage):
 if self._replica_config.tensor_parallel_size!=1 or self._replica_config.num_pipeline_stages!=1 or pipeline_stage!=0:raise CoverageError('requires TP1 PP1')
 requests=batch.requests;phase_flags=[r.is_prefill_complete for r in requests]
 if not requests or len(set(phase_flags))!=1:raise CoverageError('mixed prefill and decode')
 phase='decode' if phase_flags[0] else 'prefill'
 lengths=[r.num_prefill_tokens for r in requests];contexts=[r.num_processed_prefill_tokens+r.num_processed_decode_tokens for r in requests]
 key,ms=lookup.get(phase,lengths,contexts,list(batch.num_tokens))
 result=orig_get(self,batch,pipeline_stage);result._measured_forward_ms=ms
 with open(trace,'a') as f:f.write(json.dumps({'phase':phase,'batch_id':batch.id,'request_ids':[r.id for r in requests],'contexts':contexts,'lookup_key':key,'forward_ms':ms,'sources_sha256':lookup.hashes})+'\n')
 return result
def model_time(self):return self._measured_forward_ms*.001 if hasattr(self,'_measured_forward_ms') else orig_model(self)
BaseExecutionTimePredictor.get_execution_time=get;ExecutionTime.model_time=property(model_time)
if mode=='dag':
 from vidur.dag.expanded import ExpandedStageBuilder
 original_build=ExpandedStageBuilder.build
 def build(self,context):
  fragment=original_build(self,context)
  if not hasattr(self.time,'_measured_forward_ms'):raise CoverageError('missing forward cost')
  tasks=fragment.tasks;core=[t for t in tasks if t.task_id.startswith('layer')]
  if len(core)!=self.time.num_layers*3 or any(t.kind!='compute' or t.placement!=core[0].placement or (t.demands and t.demands!=core[0].demands) for t in core):raise CoverageError('unexpected layer structure')
  ms=self.time._measured_forward_ms;cost=CostEstimate(ms*.001,'measured-full-forward-diagnostic',ms,'ms',.001,'forward_diagnostic/lookup.py',('compute',))
  whole=replace(core[0],task_id='whole_forward',cost=cost,metadata={'op':'whole_forward','replaces':'all layer compute','diagnostic':True})
  others=[t for t in tasks if not t.task_id.startswith('layer')];merged=tuple(others[:1]+[whole]+others[1:])
  return GraphFragment(fragment.schema_version,fragment.graph_id,fragment.context,merged,tuple((a.task_id,b.task_id) for a,b in zip(merged,merged[1:])),fragment.terminal_task_id)
 ExpandedStageBuilder.build=build
from vidur.main import main
main()
