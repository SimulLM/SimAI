"""Separate bounded CUDA-profiler diagnostic; never use for production E2E."""
import os
if os.environ.get('COMPUTE_DIAG')=='1':
 import torch,json,time
 from vllm.worker.model_runner import ModelRunner
 root=os.environ['COMPUTE_DIAG_DIR'];state={'n':0,'prof':None,'done':False}
 def log(x):
  with open(os.path.join(root,f'profiler-control-{os.getpid()}.jsonl'),'a') as f:f.write(json.dumps(x,separators=(',',':'))+'\n')
 old=ModelRunner.execute_model
 def run(self,model_input,*args,**kwargs):
  ids=list((getattr(model_input,'request_ids_to_seq_ids',None) or {}).keys());q=list(getattr(model_input,'query_lens',[]) or []);is_real=bool(ids) and all(str(x).startswith('cmpl-') for x in ids);prefill=is_real and bool(q) and min(q)>1
  if prefill and not state['done']:
   state['n']+=1
   if state['n']==3:
    try:
     prof=torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,torch.profiler.ProfilerActivity.CUDA],record_shapes=False,profile_memory=False,with_stack=False);prof.__enter__();state['prof']=prof;log({'event':'started','pid':os.getpid(),'monotonic_ns':time.monotonic_ns(),'step':state['n']})
    except Exception as exc:state['done']=True;log({'event':'start_error','error':repr(exc),'pid':os.getpid()})
  if state['prof'] is not None:
   label='real_pd_step_'+str(state['n'])+'_'+('_'.join(ids) if ids else 'empty')
   with torch.profiler.record_function(label): result=old(self,model_input,*args,**kwargs)
  else: result=old(self,model_input,*args,**kwargs)
  if prefill and state['prof'] is not None and state['n']>=30:
   prof=state['prof'];state['prof']=None;state['done']=True
   try:
    prof.__exit__(None,None,None);path=os.path.join(root,f'kineto-trace-{os.getpid()}.json');prof.export_chrome_trace(path);log({'event':'finished','pid':os.getpid(),'monotonic_ns':time.monotonic_ns(),'step':state['n'],'trace':path})
   except Exception as exc:log({'event':'finish_error','error':repr(exc),'pid':os.getpid()})
  return result
 ModelRunner.execute_model=run
