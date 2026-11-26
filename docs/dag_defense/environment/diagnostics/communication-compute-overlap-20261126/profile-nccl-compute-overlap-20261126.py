import os,csv,time,datetime,json,argparse,torch,torch.distributed as dist,torch.multiprocessing as mp
from pathlib import Path

def worker(rank,out):
 os.environ.update(MASTER_ADDR='127.0.0.1',MASTER_PORT='29657');torch.cuda.set_device(rank);dist.init_process_group('nccl',rank=rank,world_size=2,timeout=datetime.timedelta(seconds=90));device=f'cuda:{rank}'
 size=545259520;x=torch.full((size//2,),.125 if rank==0 else 0,dtype=torch.float16,device=device);stream=torch.cuda.Stream(device=rank)
 if rank==0:a=torch.ones((4096,4096),dtype=torch.float16,device=device);b=torch.ones_like(a);c=torch.empty_like(a)
 torch.cuda.synchronize();path=Path(out)/f'rank{rank}.csv'
 with path.open('w',newline='') as f:
  cols=['rank','mode','iteration','warmup','host_start_ns','host_end_ns','compute_gpu_ms','payload_bytes','integrity'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader();f.flush()
  for mode in ('compute_only','transfer_only','concurrent'):
   for i in range(40):
    dist.barrier();torch.cuda.synchronize();start=time.monotonic_ns();gpu_ms='';integrity='';work=None
    if mode!='compute_only':work=dist.isend(x,1) if rank==0 else dist.irecv(x,0)
    if rank==0 and mode!='transfer_only':
     s=torch.cuda.Event(enable_timing=True);e=torch.cuda.Event(enable_timing=True)
     with torch.cuda.stream(stream):
      s.record()
      for _ in range(64):torch.mm(a,b,out=c)
      e.record()
    if work is not None:work.wait()
    torch.cuda.synchronize();end=time.monotonic_ns()
    if rank==0 and mode!='transfer_only':gpu_ms=s.elapsed_time(e)
    if rank==1 and mode!='compute_only':integrity=int(float(x[0])==.125 and float(x[-1])==.125)
    w.writerow(dict(rank=rank,mode=mode,iteration=i,warmup=int(i<10),host_start_ns=start,host_end_ns=end,compute_gpu_ms=gpu_ms,payload_bytes=size,integrity=integrity));f.flush()
 dist.barrier();dist.destroy_process_group()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);a=p.parse_args();o=Path(a.run_dir);o.mkdir(parents=True,exist_ok=False);(o/'config.json').write_text(json.dumps({'kind':'synthetic microbenchmark; not vLLM connector or E2E','payload_bytes':545259520,'payload_note':'1024 tokens KV plus hidden, represented as one FP16 tensor; excludes metadata','compute':'64 x 4096x4096 FP16 torch.mm on GPU0 non-default stream','backend':'torch.distributed NCCL point-to-point','timing':'CPU CLOCK_MONOTONIC, GPU compute CUDA events, explicit sync','warmups':10,'samples':30,'limitations':'GPU communication start/end are not directly anchored to host; comparison is diagnostic only'},indent=2)+'\n');mp.spawn(worker,args=(str(o),),nprocs=2,join=True)
