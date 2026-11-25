import os, csv, time, datetime
import torch
import torch.distributed as dist
import torch.multiprocessing as mp

OUT='/root/autodl-tmp/dag-handoff/runs/nccl-p2p-20261126'
SIZES=(256*1024*1024,512*1024*1024,1024*1024*1024)
def worker(rank):
    os.environ.update(MASTER_ADDR='127.0.0.1',MASTER_PORT='29617')
    torch.cuda.set_device(rank)
    dist.init_process_group('nccl',rank=rank,world_size=2,timeout=datetime.timedelta(seconds=180))
    rows=[]
    for n in SIZES:
        x=torch.full((n//4,), 1.25 if rank == 0 else 0.,device=f'cuda:{rank}',dtype=torch.float32)
        torch.cuda.synchronize()
        for i in range(40):
            dist.barrier(); torch.cuda.synchronize()
            start=time.monotonic_ns()
            if rank==0: dist.send(x,dst=1)
            else: dist.recv(x,src=0)
            torch.cuda.synchronize()
            elapsed=(time.monotonic_ns()-start)/1e9
            if i>=10: rows.append((rank,n,i-10,elapsed))
        if rank==1:
            assert torch.all(x==1.25).item(), 'payload mismatch'
        del x
    with open(f'{OUT}/rank{rank}.csv','w',newline='') as f:
        w=csv.writer(f);w.writerow(['rank','payload_bytes','iteration','elapsed_s']);w.writerows(rows)
    dist.destroy_process_group()
if __name__=='__main__':
    mp.spawn(worker,nprocs=2,join=True)
