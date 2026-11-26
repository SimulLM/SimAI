"""Opt-in host API events for vLLM 0.8.5; no CUDA synchronization."""
import os
if os.environ.get('PD_LIGHT_EVENTS_DIR'):
 import json, threading, time
 from vllm.worker.model_runner import ModelRunner
 from vllm.distributed.kv_transfer.kv_connector.simple_connector import SimpleConnector
 root=os.environ['PD_LIGHT_EVENTS_DIR'];role=os.environ['PD_LIGHT_ROLE'];local=threading.local()
 os.makedirs(root,exist_ok=True)
 def emit(name,**fields):
  row={'event':name,'timestamp_ns':time.monotonic_ns(),'clock_id':'CLOCK_MONOTONIC','role':role,'pid':os.getpid(),'thread_id':threading.get_ident(),**fields}
  fd=os.open(os.path.join(root,f'light-{role}-{os.getpid()}.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
  try:os.write(fd,(json.dumps(row,separators=(',',':'))+'\n').encode())
  finally:os.close(fd)
 old_prepare=ModelRunner.prepare_model_input
 def prepare(self,groups,*args,**kwargs):
  result=old_prepare(self,groups,*args,**kwargs)
  object.__setattr__(result,'_light_groups',[{'request_id':g.request_id,'is_prompt':bool(g.is_prompt),'seq_ids':list(g.seq_data)} for g in groups])
  return result
 ModelRunner.prepare_model_input=prepare
 old_execute=ModelRunner.execute_model
 def execute(self,model_input,*args,**kwargs):
  groups=getattr(model_input,'_light_groups',[])
  if not groups:return old_execute(self,model_input,*args,**kwargs)
  local.groups=groups; step=f'{os.getpid()}-{threading.get_ident()}-{time.monotonic_ns()}'
  local.step=step;emit('model_step_host_start',step_id=step,groups=groups)
  try:
   result=old_execute(self,model_input,*args,**kwargs)
   emit('model_step_host_return',step_id=step,groups=groups)
   return result
  except BaseException as exc:
   emit('model_step_host_error',step_id=step,groups=groups,error=type(exc).__name__);raise
  finally:local.groups=[];local.step=None
 ModelRunner.execute_model=execute
 def wrap(name):
  original=getattr(SimpleConnector,name)
  def wrapped(self,*args,**kwargs):
   groups=getattr(local,'groups',[]);step=getattr(local,'step',None)
   emit(name+'_host_start',step_id=step,groups=groups)
   try:
    result=original(self,*args,**kwargs)
    extra={'kv_bypass':bool(result[1])} if name.startswith('recv') else {}
    emit(name+'_host_return',step_id=step,groups=groups,**extra)
    return result
   except BaseException as exc:
    emit(name+'_host_error',step_id=step,groups=groups,error=type(exc).__name__);raise
  setattr(SimpleConnector,name,wrapped)
 wrap('send_kv_caches_and_hidden_states');wrap('recv_kv_caches_and_hidden_states')
 emit('instrument_loaded',version='host-events-v1',gpu_synchronized=False)
