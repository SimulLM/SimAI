"""Separate diagnostic: bound CUDA event times with host monotonic queries, no cuda synchronize."""
import os
if os.environ.get('COMPUTE_DIAG')=='1':
 import json,time,threading,torch
 from vllm.worker.model_runner import ModelRunner
 from vllm.distributed.device_communicators.pynccl import PyNcclCommunicator
 root=os.environ['COMPUTE_DIAG_DIR'];q=[];lock=threading.Lock();active=threading.local();started=False
 def write(row):
  with open(os.path.join(root,f'gpu-bounds-{os.getpid()}.jsonl'),'a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
 def poll():
  torch.cuda.set_device(0)
  while True:
   with lock: entries=list(q)
   for item in entries:
    try:
     for k in ('start','end'):
      if item[k] is not None and item[k+'_upper'] is None:
       before=time.monotonic_ns();done=item[k].query();after=time.monotonic_ns()
       if done:item[k+'_upper']=after
       else:item[k+'_lower']=before
     if item['start_upper'] is not None and item['end_upper'] is not None:
      row={k:v for k,v in item.items() if k not in ('start','end')};row.update(event='cuda_event_bounds',pid=os.getpid(),clock_id='CLOCK_MONOTONIC');write(row)
      with lock:q.remove(item)
    except Exception as e:
     write({'event':'poll_error','error':repr(e),'pid':os.getpid()})
     with lock:
      if item in q:q.remove(item)
   time.sleep(.0005)
 def begin(name,start,lower,meta):
  global started
  item={'name':name,'start':start,'end':None,'start_lower':lower,'end_lower':lower,'start_upper':None,'end_upper':None,'metadata':meta}
  with lock:
   q.append(item)
   if not started:
    started=True;threading.Thread(target=poll,daemon=True,name='gpu-bound-poller').start()
  return item
 def finish(item,end):
  with lock:item['end']=end
 def event_pair():
  stream=torch.cuda.current_stream();lower=time.monotonic_ns();start=torch.cuda.Event();start.record(stream);return stream,lower,start
 oldload=ModelRunner.load_model
 def load(self,*a,**kw):
  r=oldload(self,*a,**kw)
  def pre(mod,inputs):
   if getattr(active,'on',False):
    stream,lower,start=event_pair();item=begin('model_forward',start,lower,{'request_ids':active.ids,'seq_lens':active.lens,'query_lens':active.qlens});active.forward=(stream,item)
  def post(mod,inputs,output):
   if getattr(active,'on',False) and getattr(active,'forward',None):
    stream,item=active.forward;end=torch.cuda.Event();end.record(stream);finish(item,end);active.forward=None
  self.model.register_forward_pre_hook(pre);self.model.register_forward_hook(post);return r
 ModelRunner.load_model=load
 oldexec=ModelRunner.execute_model
 def execute(self,model_input,*a,**kw):
  active.on=True;active.ids=list((getattr(model_input,'request_ids_to_seq_ids',None) or {}).keys());active.lens=list(getattr(model_input,'seq_lens',[]) or []);active.qlens=list(getattr(model_input,'query_lens',[]) or [])
  try:return oldexec(self,model_input,*a,**kw)
  finally:active.on=False;active.forward=None
 ModelRunner.execute_model=execute
 def wrap(name):
  old=getattr(PyNcclCommunicator,name)
  def fn(self,tensor,*args,**kw):
   if tensor.numel()*tensor.element_size()<1048576:return old(self,tensor,*args,**kw)
   stream=kw.get('stream') or (args[1] if len(args)>1 else None) or torch.cuda.current_stream();lower=time.monotonic_ns();start=torch.cuda.Event();start.record(stream);item=begin('nccl_'+name,start,lower,{'bytes':tensor.numel()*tensor.element_size(),'shape':list(tensor.shape)});result=old(self,tensor,*args,**kw);end=torch.cuda.Event();end.record(stream);finish(item,end);return result
  setattr(PyNcclCommunicator,name,fn)
 wrap('send');wrap('recv')
