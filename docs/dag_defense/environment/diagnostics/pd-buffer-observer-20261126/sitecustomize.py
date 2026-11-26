"""Opt-in diagnostic of SimpleBuffer host state; performs no GPU sync."""
import os,sys
if os.environ.get('PD_BUFFER_OBSERVER_DIR'):
 try:
  import json,pathlib,threading,time,traceback
  from vllm.distributed.kv_transfer.kv_lookup_buffer.simple_buffer import SimpleBuffer
  from vllm.distributed.kv_transfer.kv_connector.simple_connector import SimpleConnector
  root=pathlib.Path(os.environ['PD_BUFFER_OBSERVER_DIR']);root.mkdir(parents=True,exist_ok=True)
  old_init=SimpleConnector.__init__;old_insert=SimpleBuffer._add_to_buffer;old_select=SimpleBuffer.drop_select
  def observed_connector(self,*args,**kwargs):
   old_init(self,*args,**kwargs)
   role='producer' if self.config.is_kv_producer else 'consumer';buf=self.producer_buffer if role=='producer' else self.consumer_buffer
   buf._observer_lock=threading.Lock();buf._observer_active={'insert':0,'select':0};buf._observer_counts={'insert_started':0,'insert_completed':0,'select_started':0,'select_completed':0}
   def sample():
    seq=0;log=root/f'{role}-{os.getpid()}.jsonl'
    while True:
     now=time.monotonic_ns();lock=buf.buffer_cv.acquire(blocking=False)
     try:
      with buf._observer_lock:active=dict(buf._observer_active);counts=dict(buf._observer_counts)
      row={'schema':1,'role':role,'pid':os.getpid(),'sequence':seq,'monotonic_ns':now,'lock_acquired':lock,'active':active,'counts':counts,'queue_items':len(buf.buffer) if lock else None,'buffer_bytes':buf.buffer_size if lock else None,'gpu_synchronized':False}
     finally:
      if lock:buf.buffer_cv.release()
     try:
      with log.open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
      dest=root/f'{role}-{os.getpid()}.json';tmp=root/f'.{role}-{os.getpid()}.tmp';tmp.write_text(json.dumps(row)+'\n');os.replace(tmp,dest)
     except Exception:pass
     seq+=1;time.sleep(.5)
   threading.Thread(target=sample,name='pd-buffer-observer',daemon=True).start()
  def wrap(old,name):
   def call(self,*args,**kwargs):
    lock=getattr(self,'_observer_lock',None)
    if lock is None:return old(self,*args,**kwargs)
    with lock:self._observer_active[name]+=1;self._observer_counts[name+'_started']+=1
    try:return old(self,*args,**kwargs)
    finally:
     with lock:self._observer_active[name]-=1;self._observer_counts[name+'_completed']+=1
   return call
  SimpleBuffer._add_to_buffer=wrap(old_insert,'insert');SimpleBuffer.drop_select=wrap(old_select,'select');SimpleConnector.__init__=observed_connector
 except Exception:
  try:
   with open(os.path.join(os.environ['PD_BUFFER_OBSERVER_DIR'],f'observer-error-{os.getpid()}.log'),'w') as f:traceback.print_exc(file=f)
  except Exception:pass
