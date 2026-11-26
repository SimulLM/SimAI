"""Fee-only adapter for the pinned original and DAG. No scheduler patches.

The untouched reference is executed separately and is never relabelled here.
"""
import dataclasses,json,os,pathlib,sys
from composite_fee import CompositeFees,require,sha
from vidur.execution_time_predictor.base_execution_time_predictor import BaseExecutionTimePredictor
from vidur.entities.execution_time import ExecutionTime
fees=CompositeFees(os.environ['COMPOSITE_FEES']);ledger=pathlib.Path(os.environ['COMPOSITE_LEDGER']);mode=os.environ['COMPOSITE_MODE']
require(mode in ('fee-adapted-reference','dag'),'invalid role')
original_model=ExecutionTime.model_time.fget
ExecutionTime.model_time=property(lambda self:self._composite_worker_ms*.001 if hasattr(self,'_composite_worker_ms') else original_model(self))
def get(self,batch,pipeline_stage):
    require(pipeline_stage==0 and self._replica_config.tensor_parallel_size==1 and self._replica_config.num_pipeline_stages==1,'composite fees require TP1 PP1')
    reqs=batch.requests;flags={r.is_prefill_complete for r in reqs};lengths={r.num_prefill_tokens for r in reqs}
    require(len(flags)==len(lengths)==1,'mixed phase/input length unsupported')
    phase='decode' if next(iter(flags)) else 'prefill';n=next(iter(lengths));contexts=[r.num_processed_prefill_tokens+r.num_processed_decode_tokens for r in reqs]
    value=fees.get(phase,n,contexts,list(batch.num_tokens))
    # All old compute, prepare, sampler and communication components are zero.
    obj=ExecutionTime(self._num_layers_per_pipeline_stage,*([0.0]*14),value['schedule_ms'],0.0,0.0,value['output_ms'],0.0,self._config,self._replica_config,self.replica_scheduler_config)
    obj._composite_worker_ms=value['worker_ms'];obj._composite_lookup=value
    with ledger.open('a') as f:f.write(json.dumps({'kind':'model_batch','role':mode,'batch_id':batch.id,'replica':batch.replica_id,'request_ids':[r.id for r in reqs],'contexts':contexts,'tokens':list(batch.num_tokens),'fee':value,'fee_sha256':sha(fees.path),'charged':['worker','schedule','output'],'removed':['old_layer_compute','old_rope','old_head','old_sampler','old_prepare']})+'\n')
    return obj
BaseExecutionTimePredictor.get_execution_time=get
if mode=='dag':
    from vidur.dag.expanded import ExpandedStageBuilder
    original_build=ExpandedStageBuilder.build
    def build(self,context):
        fragment=original_build(self,context);require(hasattr(self.time,'_composite_worker_ms'),'composite worker fee absent')
        from schemas.dag.v1.contracts import CostEstimate
        tasks=[];charged=False
        for t in fragment.tasks:
            if t.task_id.startswith('layer'):
                ms=self.time._composite_worker_ms if not charged else 0.0;charged=True
                metadata=dict(t.metadata,op='worker.composite' if ms else 'excluded.layer_subfee',components={'worker_envelope_ms':ms},scope='prepare+all layers+head+sampler; no subfee addition')
                t=dataclasses.replace(t,cost=CostEstimate(ms*.001,'measured.worker_envelope',ms,'ms',.001,str(fees.path),('compute',)),demands=t.demands if ms else (),metadata=metadata)
                if ms and not t.demands:
                    from schemas.dag.v1.contracts import ResourceDemand
                    t=dataclasses.replace(t,demands=tuple(ResourceDemand(d,1,'permits') for d in t.placement.device_ids))
            tasks.append(t)
        require(charged,'no existing compute task')
        return dataclasses.replace(fragment,tasks=tuple(tasks))
    ExpandedStageBuilder.build=build
# KV fee uses the run's scalar effective-bandwidth coefficient, derived from the
# same receiver envelope in both command lines. It is not physical bandwidth.
from vidur.main import main
main()
