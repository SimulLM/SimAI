"""Independent serial vLLM PyNccl SimpleBuffer measurements, not E2E."""
import argparse,csv,json,os,subprocess,sys,time
from pathlib import Path

def worker(rank,out):
 import datetime
 import torch
 import torch.distributed as dist
 from vllm.config import KVTransferConfig
 from vllm.distributed.kv_transfer.kv_pipe.pynccl_pipe import PyNcclPipe
 from vllm.distributed.kv_transfer.kv_lookup_buffer.simple_buffer import SimpleBuffer
 torch.cuda.set_device(0)
 dist.init_process_group('gloo',init_method='tcp://127.0.0.1:14791',rank=rank,world_size=2,timeout=datetime.timedelta(seconds=300))
 cfg=KVTransferConfig(kv_connector='PyNcclConnector',kv_role='kv_producer' if rank==0 else 'kv_consumer',kv_rank=rank,kv_parallel_size=2,kv_ip='127.0.0.1',kv_port=14789,kv_buffer_size=8589934592)
 data=PyNcclPipe(local_rank=0,config=cfg,device='cuda',port_offset=0)
 signal=PyNcclPipe(local_rank=0,config=cfg,device='cpu',port_offset=1)
 buf=SimpleBuffer(signal,data,cfg.kv_buffer_size)
 outpath=out/f'rank{rank}.csv'
 with outpath.open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=['rank','tokens','iteration','warmup','start_ns','end_ns','duration_s','kv_bytes','hidden_bytes']);writer.writeheader(); stream.flush()
  for n in (512,1024,2048):
   tokens=torch.arange(n,dtype=torch.long,device='cuda'); roi=torch.ones(n,dtype=torch.bool,device='cuda')
   if rank==0:
    key=torch.full((32,n,32,128),0.125,device='cuda',dtype=torch.float16)
    value=torch.full((32,n,32,128),0.25,device='cuda',dtype=torch.float16)
    hidden=torch.full((n,4096),0.5,device='cuda',dtype=torch.float16)
   torch.cuda.synchronize()
   for iteration in range(40):
    dist.barrier(); torch.cuda.synchronize(); start=time.monotonic_ns()
    if rank==0: buf.insert(tokens,roi,key,value,hidden)
    else: result=buf.drop_select(tokens,roi)
    torch.cuda.synchronize(); end=time.monotonic_ns()
    if rank==1:
     ids,mask,k,v,h=result
     assert torch.equal(ids,tokens) and bool(torch.all(mask)) and k.shape==(32,n,32,128) and v.shape==k.shape and h.shape==(n,4096)
     assert float(k[0,0,0,0])==0.125 and float(v[-1,-1,-1,-1])==0.25 and float(h[-1,-1])==0.5
     del result,ids,mask,k,v,h
    writer.writerow(dict(rank=rank,tokens=n,iteration=iteration,warmup=int(iteration<10),start_ns=start,end_ns=end,duration_s=(end-start)/1e9,kv_bytes=n*524288,hidden_bytes=n*8192));stream.flush()
    dist.barrier()
   del tokens,roi
   if rank==0: del key,value,hidden
   torch.cuda.empty_cache()
 dist.barrier();buf.close();data.close();signal.close();dist.destroy_process_group()

def main():
 p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True,type=Path);p.add_argument('--worker',type=int,choices=[0,1]);a=p.parse_args(); out=a.run_dir
 if a.worker is not None: return worker(a.worker,out)
 out.mkdir(parents=True,exist_ok=False)
 (out/'config.json').write_text(json.dumps(dict(token_lengths=[512,1024,2048],warmups=10,measured=30,shape='key/value [32,tokens,32,128], hidden [tokens,4096]',dtype='float16',buffer_bytes=8589934592,measurement='CPU monotonic_ns around SimpleBuffer insert or drop_select followed by device-wide synchronize; serial with gloo barriers; integrity samples after timed region',clock='CLOCK_MONOTONIC',note='Not cache installation, batch concurrency or E2E; inputs synthetic, measured costs real'),indent=2)+'\n')
 procs=[];files=[]
 for rank in (0,1):
  env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(rank),VLLM_NO_USAGE_STATS='1',NCCL_DEBUG='INFO',NCCL_DEBUG_SUBSYS='INIT,GRAPH,P2P,SHM,NET',NCCL_DEBUG_FILE=str(out/f'nccl-rank{rank}.log'))
  log=(out/f'worker{rank}.log').open('w');files.append(log)
  procs.append(subprocess.Popen([sys.executable,__file__,'--run-dir',str(out),'--worker',str(rank)],env=env,stdout=log,stderr=subprocess.STDOUT))
 try:
  codes=[p.wait(timeout=600) for p in procs]
 except subprocess.TimeoutExpired:
  for p in procs: p.terminate()
  codes=[p.wait(timeout=10) for p in procs]
 finally:
  for f in files:f.close()
 (out/'exit-codes.json').write_text(json.dumps(codes)+'\n')
 if codes != [0,0]: raise SystemExit(1)
if __name__=='__main__': main()
