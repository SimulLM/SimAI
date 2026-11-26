"""Validate host observations for a fixed window; never certify GPU readiness."""
import argparse,json,pathlib,sys
if not __debug__:raise RuntimeError("optimized Python disables required checks")

def read_lines(path):
 with path.open() as f:return [json.loads(line) for line in f if line.strip()]
def check(probe_path,observer_dir,expected_requests,max_age_s,min_window_s):
 if expected_requests<1 or max_age_s<=0 or min_window_s<=0:raise ValueError('invalid limits')
 samples=read_lines(probe_path);assert len(samples)>=2,'insufficient gauge samples'
 times=[x['monotonic_ns'] for x in samples];assert all(a<b for a,b in zip(times,times[1:])),'sample clock not strictly increasing'
 assert (times[-1]-times[0])/1e9>=min_window_s,'observation window too short'
 assert not list(observer_dir.glob('observer-error-*.log')),'observer import failure'
 observers={}
 for path in observer_dir.glob('*.jsonl'):
  rows=read_lines(path);assert rows,'empty observer log';role=rows[0]['role'];assert role in ('producer','consumer') and role not in observers,'missing or ambiguous worker'
  assert all(x['schema']==2 and x['role']==role and x['pid']==rows[0]['pid'] for x in rows),'observer identity changed'
  assert all(a['monotonic_ns']<b['monotonic_ns'] and a['sequence']<b['sequence'] for a,b in zip(rows,rows[1:])),'observer timestamps or sequence invalid';observers[role]=rows
 assert set(observers)=={'producer','consumer'},'missing worker observer'
 expected={'producer':'insert','consumer':'select'};joined=[]
 for sample in samples:
  assert sample['router']['status']=='observed' and sample['router']['inflight']==0 and sample['router']['unresolved_errors']==0,'router busy or unknown'
  row={'sample':sample['sample'],'monotonic_ns':sample['monotonic_ns'],'roles':{}}
  for role,endpoint in (('producer','prefill'),('consumer','decode')):
   gauges=sample['servers'][endpoint].get('gauges',{});assert len(gauges)==5 and all(value==0 for value in gauges.values()),'missing or nonzero metrics'
   prior=[x for x in observers[role] if x['monotonic_ns']<=sample['monotonic_ns']];assert prior,'missing prior observer';x=prior[-1];age=(sample['monotonic_ns']-x['monotonic_ns'])/1e9
   assert age<=max_age_s and x['lock_acquired'],'stale or locked observer'
   assert x['queue_items']==x['buffer_bytes']==x['pipe_buffer_bytes']==0 and not any(x['active'].values()) and not any(x['pipe_active'].values()),'host buffer or pipe active'
   kind=expected[role];counts=x['counts'];pipe=x['pipe_counts']
   assert counts[kind+'_started']==counts[kind+'_completed']==expected_requests,'unexpected connector call count'
   assert pipe['send_started']==pipe['send_completed'] and pipe['recv_started']==pipe['recv_completed'],'unbalanced transport calls'
   assert pipe['send_completed']>0 and pipe['recv_completed']>0,'no data-pipe activity observed'
   row['roles'][role]={'pid':x['pid'],'snapshot_age_s':age,'counts':counts,'pipe_counts':pipe}
  joined.append(row)
 return {'status':'host_observations_consistent_gpu_unverified','window_s':(times[-1]-times[0])/1e9,'expected_requests':expected_requests,'samples':joined,'limitations':['Recorded host calls and zero buffers do not prove GPU or NCCL work has completed','Process identities are not checked for live ownership by this offline checker','Observer may perturb timing; signal pipe and transient states are not fully observed','Timeout and crash cleanup require separate evidence; no formal readiness certification']}
def main():
 p=argparse.ArgumentParser();p.add_argument('--probe',type=pathlib.Path,required=True);p.add_argument('--observer',type=pathlib.Path,required=True);p.add_argument('--expected-requests',type=int,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--max-age',type=float,default=1.5);p.add_argument('--min-window',type=float,default=15);a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 try:result=check(a.probe,a.observer,a.expected_requests,a.max_age,a.min_window)
 except Exception as e:result={'status':'host_observations_incomplete','error':type(e).__name__+': '+str(e),'gpu_ready':False}
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 2
if __name__=='__main__':sys.exit(main())
