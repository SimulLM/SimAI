"""Diagnostic CUDA event hooks for one actual vLLM model layer, not E2E."""
import os
if os.environ.get('COMPUTE_DIAG')=='1':
 import json,time,threading,torch
 from vllm.worker.model_runner import ModelRunner, CUDAGraphRunner
 local=threading.local(); run=os.environ['COMPUTE_DIAG_DIR']
 def log(row):
  with open(os.path.join(run,f'compute-events-{os.getpid()}.jsonl'),'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
 oldload=ModelRunner.load_model
 def load(self,*args,**kwargs):
  result=oldload(self,*args,**kwargs)
  # GPU model forward excludes KV recv/send and the later logits/sampler.
  def model_pre(mod,inputs):
   if getattr(local,'active',False):
    ev=torch.cuda.Event(enable_timing=True); ev.record(); local.pending['full_model_forward']=ev
  def model_post(mod,inputs,output):
   if getattr(local,'active',False) and 'full_model_forward' in local.pending:
    ev=torch.cuda.Event(enable_timing=True); ev.record(); local.pairs.append(('full_model_forward',local.pending.pop('full_model_forward'),ev))
  self.model.register_forward_pre_hook(model_pre); self.model.register_forward_hook(model_post)
  layer=self.model.model.layers[16]
  hooks={'input_layernorm':layer.input_layernorm,'attn_pre_proj':layer.self_attn.qkv_proj,'attn_rope':layer.self_attn.rotary_emb,'attention_combined':layer.self_attn.attn,'attn_post_proj':layer.self_attn.o_proj,'post_attention_layernorm':layer.post_attention_layernorm,'mlp_up_proj':layer.mlp.gate_up_proj,'mlp_act':layer.mlp.act_fn,'mlp_down_proj':layer.mlp.down_proj}
  for name,module in hooks.items():
   def pre(mod,inputs,name=name):
    if getattr(local,'active',False):
     start=torch.cuda.Event(enable_timing=True);start.record();local.pending[name]=start
   def post(mod,inputs,output,name=name):
    if getattr(local,'active',False) and name in local.pending:
     end=torch.cuda.Event(enable_timing=True);end.record();local.pairs.append((name,local.pending.pop(name),end))
   module.register_forward_pre_hook(pre);module.register_forward_hook(post)
  cfg=self.model.config
  log({'event':'hooks_installed','layer':16,'classes':{k:type(v).__name__ for k,v in hooks.items()},'rope_theta':getattr(cfg,'rope_theta',None),'rope_scaling':getattr(cfg,'rope_scaling',None),'pid':os.getpid()})
  return result
 ModelRunner.load_model=load
 oldprep=ModelRunner.prepare_model_input
 def prep(self,groups,*args,**kwargs):
  result=oldprep(self,groups,*args,**kwargs)
  object.__setattr__(result,'_compute_diag_groups',[{'request_id':g.request_id,'is_prompt':g.is_prompt} for g in groups])
  return result
 ModelRunner.prepare_model_input=prep
 oldexec=ModelRunner.execute_model
 def execute(self,model_input,*args,**kwargs):
  groups=getattr(model_input,'_compute_diag_groups',[])
  if not groups:
   qlens=list(getattr(model_input,'query_lens',[])); groups=[{'request_id':f'v0-{i}','is_prompt':int(q)>1} for i,q in enumerate(qlens)]
  if not groups:return oldexec(self,model_input,*args,**kwargs)
  local.active=True;local.pending={};local.pairs=[];start=time.monotonic_ns();step_start=torch.cuda.Event(enable_timing=True);step_start.record()
  try:
   result=oldexec(self,model_input,*args,**kwargs);step_end=torch.cuda.Event(enable_timing=True);step_end.record();torch.cuda.synchronize()
   timings={name:a.elapsed_time(b) for name,a,b in local.pairs}
   log({'event':'model_step','pid':os.getpid(),'host_start_ns':start,'host_after_sync_ns':time.monotonic_ns(),'clock_id':'CLOCK_MONOTONIC','groups':groups,'seq_lens':model_input.seq_lens,'query_lens':model_input.query_lens,'step_gpu_ms':step_start.elapsed_time(step_end),'gpu_event_ms':timings})
   return result
  finally:local.active=False;local.pending={};local.pairs=[]
 ModelRunner.execute_model=execute

 if True:
  _graph_forward=CUDAGraphRunner.forward
  def graph_forward(self,*args,**kwargs):
   if not getattr(local,'active',False): return _graph_forward(self,*args,**kwargs)
   start=torch.cuda.Event(enable_timing=True); start.record()
   result=_graph_forward(self,*args,**kwargs)
   end=torch.cuda.Event(enable_timing=True); end.record(); local.pairs.append(('full_model_forward',start,end))
   return result
  CUDAGraphRunner.forward=graph_forward
