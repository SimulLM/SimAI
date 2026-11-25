"""Diagnostic-only synchronous vLLM 0.8.5 instrumentation; not for E2E."""
import os
if os.environ.get('PD_DIAG') == '1':
 import json, time, threading, hashlib
 import torch
 from vllm.worker.model_runner import ModelRunner
 from vllm.distributed.kv_transfer.kv_connector.simple_connector import SimpleConnector
 from vllm.distributed.kv_transfer.kv_pipe.pynccl_pipe import PyNcclPipe
 role=os.environ['PD_DIAG_ROLE']; out=os.environ['PD_DIAG_DIR']; local=threading.local()
 def record(event, **fields):
  row={'event':event,'timestamp_ns':time.monotonic_ns(),'clock_id':'CLOCK_MONOTONIC','role':role,'pid':os.getpid(),'thread':threading.get_ident(),**fields}
  with open(os.path.join(out,f'events-{role}-{os.getpid()}.jsonl'),'a') as f: f.write(json.dumps(row,separators=(',',':'))+'\n')
 def sync(): torch.cuda.synchronize()
 def token_hash(tensor): return hashlib.sha256(tensor.detach().to('cpu').contiguous().numpy().tobytes()).hexdigest()
 def sample_hash(tensor):
  sample=tensor[:, :3, :1, :8] if tensor.ndim==4 else tensor[:3, :8]
  return token_hash(sample)
 old_prepare=ModelRunner.prepare_model_input
 def prepare(self,groups,*args,**kw):
  result=old_prepare(self,groups,*args,**kw)
  object.__setattr__(result,'_diag_groups',[{'request_id':g.request_id,'is_prompt':g.is_prompt,'seq_ids':list(g.seq_data)} for g in groups])
  return result
 ModelRunner.prepare_model_input=prepare
 old_execute=ModelRunner.execute_model
 def execute(self, model_input, *args, **kw):
  groups=getattr(model_input,'_diag_groups',[])
  if not groups: return old_execute(self,model_input,*args,**kw)
  local.groups=groups
  sync(); record('model_step_cpu_start',groups=groups)
  try:
   result=old_execute(self,model_input,*args,**kw)
   sync(); record('model_step_gpu_complete',groups=groups)
   return result
  finally: local.groups=[]
 ModelRunner.execute_model=execute
 old_send=SimpleConnector.send_kv_caches_and_hidden_states
 def send(self,*args,**kw):
  sync(); record('prefill_gpu_complete_before_kv_insert',groups=getattr(local,'groups',[]))
  result=old_send(self,*args,**kw)
  sync(); record('kv_insert_gpu_complete',groups=getattr(local,'groups',[]))
  return result
 SimpleConnector.send_kv_caches_and_hidden_states=send
 old_insert=SimpleConnector.insert
 def insert(self,input_tokens,roi,key,value,hidden):
  record('kv_insert_cpu',groups=getattr(local,'groups',[]),token_sha256=token_hash(input_tokens),key_sample_sha256=sample_hash(key),value_sample_sha256=sample_hash(value),hidden_sample_sha256=sample_hash(hidden),tokens=input_tokens.numel(),key_bytes=key.numel()*key.element_size(),value_bytes=value.numel()*value.element_size(),hidden_bytes=hidden.numel()*hidden.element_size())
  return old_insert(self,input_tokens,roi,key,value,hidden)
 SimpleConnector.insert=insert
 old_select=SimpleConnector.select
 def select(self,input_tokens,roi):
  result=old_select(self,input_tokens,roi)
  record('kv_select_match',groups=getattr(local,'groups',[]),query_sha256=token_hash(input_tokens),returned_sha256=token_hash(result[0]) if result[0] is not None else None,key_sample_sha256=sample_hash(result[2]) if result[2] is not None else None,value_sample_sha256=sample_hash(result[3]) if result[3] is not None else None,hidden_sample_sha256=sample_hash(result[4]) if result[4] is not None else None,tokens=input_tokens.numel())
  return result
 SimpleConnector.select=select
 old_recv=SimpleConnector.recv_kv_caches_and_hidden_states
 def recv(self,*args,**kw):
  record('kv_receive_cpu_start',groups=getattr(local,'groups',[]))
  result=old_recv(self,*args,**kw)
  sync(); record('kv_ready_gpu_complete',groups=getattr(local,'groups',[]),bypass_model_exec=result[1])
  return result
 SimpleConnector.recv_kv_caches_and_hidden_states=recv
 old_s=PyNcclPipe._send_impl; old_r=PyNcclPipe._recv_impl
 def ps(self,tensor):
  if self.device.type!='cuda': return old_s(self,tensor)
  size=0 if tensor is None else tensor.numel()*tensor.element_size()
  record('transport_send_cpu_start',bytes=size)
  result=old_s(self,tensor); sync(); record('transport_send_gpu_complete',bytes=size)
  return result
 def pr(self):
  if self.device.type!='cuda': return old_r(self)
  record('transport_recv_cpu_start')
  result=old_r(self); sync(); size=0 if result is None else result.numel()*result.element_size(); record('transport_recv_gpu_complete',bytes=size)
  return result
 PyNcclPipe._send_impl=ps; PyNcclPipe._recv_impl=pr
 record('instrument_loaded',version='diagnostic-v1')
