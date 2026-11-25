"""Diagnostic host timing hooks for actual vLLM V0; no added CUDA synchronization."""
import os
if os.environ.get('CPU_DIAG')=='1':
 import json,time,threading
 from vllm.core.scheduler import Scheduler
 from vllm.worker.model_runner import ModelRunner
 from vllm.engine.llm_engine import LLMEngine
 from vllm.model_executor.layers.sampler import Sampler
 local=threading.local();out=os.environ['CPU_DIAG_DIR']
 def rec(name,start,groups,**extra):
  end=time.monotonic_ns();row=dict(event=name,start_ns=start,end_ns=end,duration_ns=end-start,clock_id='CLOCK_MONOTONIC',pid=os.getpid(),groups=groups,**extra)
  with open(os.path.join(out,f'cpu-events-{os.getpid()}.jsonl'),'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
 def ids(groups):return [{'request_id':g.request_id,'is_prompt':g.is_prompt} for g in groups]
 schedule=Scheduler.schedule
 def do_schedule(self,*args,**kw):
  start=time.monotonic_ns();result=schedule(self,*args,**kw);meta=result[0]
  if meta:rec('schedule',start,ids(meta))
  return result
 Scheduler.schedule=do_schedule
 prepare=ModelRunner.prepare_model_input
 def do_prepare(self,groups,*args,**kw):
  start=time.monotonic_ns();result=prepare(self,groups,*args,**kw);info=ids(groups)
  object.__setattr__(result,'_cpu_diag_groups',info)
  if info and all(x['request_id'].startswith('cmpl-') for x in info):rec('prepare_inputs',start,info,seq_lens=result.seq_lens,query_lens=result.query_lens)
  return result
 ModelRunner.prepare_model_input=do_prepare
 execute=ModelRunner.execute_model
 def do_execute(self,model_input,*args,**kw):
  local.groups=getattr(model_input,'_cpu_diag_groups',[])
  try:return execute(self,model_input,*args,**kw)
  finally:local.groups=[]
 ModelRunner.execute_model=do_execute
 sample=Sampler.forward
 def do_sample(self,*args,**kw):
  start=time.monotonic_ns();result=sample(self,*args,**kw);groups=getattr(local,'groups',[])
  if groups:rec('sampler_host_call',start,groups)
  return result
 Sampler.forward=do_sample
 process=LLMEngine._process_model_outputs
 def do_process(self,ctx,*args,**kw):
  groups=[]
  if len(ctx.output_queue):groups=ids(ctx.output_queue[0][1])
  start=time.monotonic_ns();result=process(self,ctx,*args,**kw)
  if groups:rec('process_model_outputs',start,groups)
  return result
 LLMEngine._process_model_outputs=do_process
