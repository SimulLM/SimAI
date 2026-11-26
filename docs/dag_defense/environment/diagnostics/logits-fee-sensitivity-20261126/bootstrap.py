"""Single 512/64 diagnostic only: replace 63 decode layer sums with measured forward."""
import os, sys, json, math
from dataclasses import replace
from vidur.execution_time_predictor.base_execution_time_predictor import BaseExecutionTimePredictor
from vidur.entities.execution_time import ExecutionTime
from schemas.dag.v1.contracts import CostEstimate, GraphFragment

trace = os.environ['FORWARD_DIAG_TRACE']
original_get = BaseExecutionTimePredictor.get_execution_time
original_model = ExecutionTime.model_time.fget

def get(self, batch, pipeline_stage):
    if self._replica_config.tensor_parallel_size != 1 or self._replica_config.num_pipeline_stages != 1 or pipeline_stage != 0:
        raise ValueError('diagnostic requires TP1 PP1')
    if len(batch.requests) != 1:
        raise ValueError('diagnostic requires single request batches')
    r = batch.requests[0]
    if r.num_prefill_tokens != 512 or r.num_decode_tokens != 64:
        raise ValueError('diagnostic requires 512/64')
    result = original_get(self, batch, pipeline_stage)
    if r._is_prefill_complete:
        context = r.num_processed_prefill_tokens + r.num_processed_decode_tokens
        if not 513 <= context <= 575 or list(batch.num_tokens) != [1]:
            raise ValueError(f'unexpected decode batch: {context}, {batch.num_tokens}')
        ms = 13.360992431640625 + (context-512)*(13.24892807006836-13.360992431640625)/63
        result._serial_forward_diag_ms = ms
        with open(trace, 'a') as f:
            f.write(json.dumps({'context': context, 'forward_ms': ms})+'\n')
    return result

def model_time(self):
    if hasattr(self, '_serial_forward_diag_ms'):
        return (self._serial_forward_diag_ms + 0.14662399888038635) * .001
    return original_model(self)
BaseExecutionTimePredictor.get_execution_time = get
ExecutionTime.model_time = property(model_time)

if os.environ['FORWARD_DIAG_MODE'] == 'dag':
    from vidur.dag.expanded import ExpandedStageBuilder
    original_build = ExpandedStageBuilder.build
    def build(self, context):
        fragment = original_build(self, context)
        if not hasattr(self.time, '_serial_forward_diag_ms'):
            return fragment
        tasks = fragment.tasks
        core = [t for t in tasks if t.task_id.startswith('layer')]
        if len(core) != self.time.num_layers * 3 or any(t.kind != 'compute' or t.placement != core[0].placement or (t.demands and t.demands != core[0].demands) for t in core):
            raise ValueError('unexpected layer structure')
        ms = self.time._serial_forward_diag_ms
        cost = CostEstimate(ms*.001, 'serial-full-forward-diagnostic', ms, 'ms', .001, 'pd-eager-profile-20261126/candidate/forward-cost.csv', ('compute',))
        whole = replace(core[0], task_id='whole_forward', cost=cost, metadata={'op':'whole_forward','context_scope':'serial 512/64', 'replaces':'all layer compute'})
        logits_ms = 0.14662399888038635
        logits_cost = CostEstimate(logits_ms*.001, 'serial-logits-diagnostic', logits_ms, 'ms', .001, 'pd-accounting-20261126:30-request logits event medians', ('compute',))
        logits = replace(core[0], task_id='logits', cost=logits_cost, metadata={'op':'logits','scope':'serial batch1 512/64 diagnostic'})
        merged = tuple([t for t in tasks if not t.task_id.startswith('layer')][:1] + [whole, logits] + [t for t in tasks if not t.task_id.startswith('layer')][1:])
        return GraphFragment(fragment.schema_version, fragment.graph_id, fragment.context, merged, tuple((a.task_id,b.task_id) for a,b in zip(merged,merged[1:])), fragment.terminal_task_id)
    ExpandedStageBuilder.build = build
from vidur.main import main
main()
