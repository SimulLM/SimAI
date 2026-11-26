import argparse,csv,json,os,subprocess,sys,time
from pathlib import Path

def worker(rank,out):
 import datetime,torch,torch.distributed as dist
 from vllm.config import KVTransferConfig
 from vllm.distributed.kv_transfer.kv_pipe.pynccl_pipe import PyNcclPipe
 from vllm.distributed.kv_transfer.kv_lookup_buffer.simple_buffer import SimpleBuffer
 torch.cuda.set_device(0);dist.init_process_group('gloo',init_method='tcp://127.0.0.1:14841',rank=rank,world_size=2,timeout=datetime.timedelta(seconds=180))
 cfg=KVTransferConfig(kv_connector='PyNcclConnector',kv_role='kv_producer' if rank==0 else 'kv_consumer',kv_rank=rank,kv_parallel_size=2,kv_ip='127.0.0.1',kv_port=14839,kv_buffer_size=8589934592)
 data=PyNcclPipe(local_rank=0,config=cfg,device='cuda',port_offset=0);signal=PyNcclPipe(local_rank=0,config=cfg,device='cpu',port_offset=1);buf=SimpleBuffer(signal,data,cfg.kv_buffer_size)
 n=1024; tokens=torch.arange(n,dtype=torch.long,device='cuda');roi=torch.ones(n,dtype=torch.bool,device='cuda');stream=torch.cuda.Stream()
 if rank==0:
  key=torch.full((32,n,32,128),.125,device='cuda',dtype=torch.float16);value=torch.full_like(key,.25);hidden=torch.full((n,4096),.5,device='cuda',dtype=torch.float16)
  a=torch.ones((4096,4096),dtype=torch.float16,device='cuda');b=torch.ones_like(a);c=torch.empty_like(a)
 torch.cuda.synchronize()
 with (out/f'rank{rank}.csv').open('w',newline='') as f:
  cols=['rank','mode','iteration','warmup','host_start_ns','host_end_ns','compute_gpu_ms','payload_kv_bytes','hidden_bytes','integrity'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader();f.flush()
  for mode in ('compute_only','transfer_only','concurrent'):
   for i in range(40):
    if rank==0 and mode!='compute_only':buf.insert(tokens,roi,key,value,hidden);torch.cuda.synchronize()
    dist.barrier();begin=time.monotonic_ns();gpu_ms='';integrity=''
    if rank==0 and mode!='transfer_only':
     s=torch.cuda.Event(enable_timing=True);e=torch.cuda.Event(enable_timing=True)
     with torch.cuda.stream(stream):
      s.record()
      for _ in range(64):torch.mm(a,b,out=c)
      e.record()
     e.synchronize();gpu_ms=s.elapsed_time(e)
    if rank==1 and mode!='compute_only':
     result=buf.drop_select(tokens,roi);torch.cuda.synchronize();ids,mask,k,v,h=result
     integrity=int(torch.equal(ids,tokens) and bool(torch.all(mask)) and k.shape==(32,n,32,128) and float(k[0,0,0,0])==.125 and float(v[-1,-1,-1,-1])==.25 and float(h[0,0])==.5)
     del result,ids,mask,k,v,h
    end=time.monotonic_ns();w.writerow(dict(rank=rank,mode=mode,iteration=i,warmup=int(i<10),host_start_ns=begin,host_end_ns=end,compute_gpu_ms=gpu_ms,payload_kv_bytes=n*524288,hidden_bytes=n*8192,integrity=integrity));f.flush()
    dist.barrier();torch.cuda.synchronize()
 dist.barrier();buf.close();data.close();signal.close();dist.destroy_process_group()

def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--worker',type=int,choices=[0,1]);a=p.parse_args();o=a.run_dir
 if a.worker is not None:return worker(a.worker,o)
 o.mkdir(parents=True,exist_ok=False);(o/'config.json').write_text(json.dumps({'model':'synthetic GEMM, not model forward','token_length':1024,'kv_shape':'[32,1024,32,128] key and value FP16','hidden_shape':'[1024,4096] FP16','gemm':'64 x (4096x4096) FP16 on separate CUDA stream GPU0','backend':'vLLM 0.8.5 SimpleBuffer PyNcclPipe','modes':['compute_only','transfer_only','concurrent'],'warmups':10,'measured':30,'timing':'host CLOCK_MONOTONIC and GPU CUDA events; explicit synchronization','limitations':'invasive synthetic microbenchmark; does not measure actual model forward nor exact GPU communication start/end; host durations include launch and synchronization'},indent=2)+'\n')
 processes=[];files=[]
 for rank in (0,1):
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(rank),VLLM_NO_USAGE_STATS='1',NCCL_DEBUG='INFO',NCCL_DEBUG_SUBSYS='INIT,GRAPH,P2P,SHM,NET',NCCL_DEBUG_FILE=str(o/f'nccl-rank{rank}.log'))
  f=(o/f'worker{rank}.log').open('w');files.append(f);processes.append(subprocess.Popen([sys.executable,__file__,'--run-dir',str(o),'--worker',str(rank)],env=env,stdout=f,stderr=subprocess.STDOUT))
 try:codes=[x.wait(timeout=600) for x in processes]
 except subprocess.TimeoutExpired:
  for x in processes:x.terminate()
  codes=[x.wait(timeout=10) for x in processes]
 finally:
  for f in files:f.close()
 (o/'exit-codes.json').write_text(json.dumps(codes)+'\n');sys.exit(0 if codes==[0,0] else 1)
if __name__=='__main__':main()
