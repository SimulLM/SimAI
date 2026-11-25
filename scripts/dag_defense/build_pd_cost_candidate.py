"""Derive a provisional shared scalar fee from independent KV-pipe observations."""
import argparse,csv,hashlib,json,statistics
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--rank1-csv',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 raw=a.rank1_csv.read_bytes();rows=[r for r in csv.DictReader(raw.decode().splitlines()) if r['warmup']=='0']
 lengths=(512,1024,2048)
 assert len(rows)==90 and all(sum(int(r['tokens'])==n for r in rows)==30 for n in lengths)
 x=[(int(r['tokens'])+1)*524288 for r in rows];y=[float(r['duration_s']) for r in rows]
 assert all(t>0 for t in y)
 slope=sum(a*b for a,b in zip(x,y))/sum(a*a for a in x)
 continuous=1/slope;gibps=round(continuous*8/1024**3);bw=gibps*1024**3/8
 by_length=[]
 for n in lengths:
  samples=[float(r['duration_s']) for r in rows if int(r['tokens'])==n];median=statistics.median(samples);pred=(n+1)*524288/bw
  by_length.append(dict(tokens=n,samples=len(samples),observed_median_s=median,predicted_s=pred,relative_error=(pred-median)/median))
 result=dict(status='provisional_not_frozen',nature='independent synthetic-tensor GPU microbenchmark; no validation completion times',source=str(a.rank1_csv),source_sha256=hashlib.sha256(raw).hexdigest(),method='least squares through origin over all 90 receiver samples using legacy billed bytes=(tokens+1)*524288; round to integer Gi-bits/s to match baseline',continuous_bandwidth_bytes_per_s=continuous,baseline_pd_p2p_comm_bandwidth_gibits_per_s=gibps,dag_bandwidth_bytes_per_s=bw,dag_latency_s=0,dag_legacy_prefill_billing_extra_token=True,by_length=by_length,limitations=['serial PyNccl SimpleBuffer wall time includes lookup and producer wait','does not include destination KV installation or full service frontend','concurrent contention and CPU/GPU overlap not captured','legacy billed bytes are a comparison cost basis, not physical tensor bytes','no accuracy or calibration acceptance claim'])
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
