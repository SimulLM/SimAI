"""Join worker CUDA barriers with surrounding host observations and identities."""
import csv,json,pathlib,sys
root=pathlib.Path(sys.argv[1]);host=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
assert (root/'exit').read_text().strip()=='0';warm=json.loads((root/'warmup.json').read_text());sync=json.loads((root/'worker-sync.json').read_text());audit=json.loads(host.read_text());assert len(warm)==4 and sync['status']=='completed' and audit['status']=='concurrent_host_idle_observations_consistent'
workers={x['role']:x for x in sync['workers']};assert set(workers)=={'producer','consumer'} and len({x['pid'] for x in workers.values()})==2
processes={}
for line in (root/'gpu-processes-during.csv').read_text().splitlines():
 parts=[x.strip() for x in line.split(',')];assert len(parts)==3;processes[int(parts[0])]=parts[1]
assert set(x['pid'] for x in workers.values()).issubset(processes) and len({processes[x['pid']] for x in workers.values()})==2
last_client=max(x['complete_ns'] for x in warm);first_observation=audit['samples'][0]['monotonic_ns'];routes=[json.loads(x) for x in (root/'service/router-events.jsonl').read_text().splitlines()];assert len({x['request_id'] for x in routes if x['event']=='server_arrival'})==4
assert all(last_client<=w['start_ns']<=w['end_ns']<=first_observation for w in workers.values())
joined={}
for role,w in workers.items():
 files=list((root/'observer').glob(f'{role}-{w["pid"]}.jsonl'));assert len(files)==1
 rows=[json.loads(x) for x in files[0].read_text().splitlines()];before=[x for x in rows if x['monotonic_ns']<=w['start_ns']];after=[x for x in rows if x['monotonic_ns']>=w['end_ns']];assert before and after
 for snap in (before[-1],after[0]):
  assert snap['lock_acquired'] and snap['queue_items']==snap['buffer_bytes']==snap['pipe_buffer_bytes']==0 and not any(snap['active'].values()) and not any(snap['pipe_active'].values())
 assert (w['start_ns']-before[-1]['monotonic_ns'])/1e9<=1.5 and (after[0]['monotonic_ns']-w['end_ns'])/1e9<=1.5
 assert before[-1]['counts']==after[0]['counts'] and before[-1]['pipe_counts']==after[0]['pipe_counts']
 assert all(s['roles'][role]['pid']==w['pid'] for s in audit['samples'])
 joined[role]={'pid':w['pid'],'gpu_uuid':processes[w['pid']],'sync_start_ns':w['start_ns'],'sync_end_ns':w['end_ns'],'before_ns':before[-1]['monotonic_ns'],'after_ns':after[0]['monotonic_ns'],'counts':after[0]['counts'],'pipe_counts':after[0]['pipe_counts']}
result={'status':'diagnostic_worker_sync_and_host_window_observed','warmup_requests':4,'last_client_complete_ns':last_client,'first_observation_ns':first_observation,'workers':joined,'limitations':['CUDA synchronization covers prior work in each responding process context, not all system or future work','Host snapshots bracket synchronization but are not atomic across threads or processes','No active-request injection or live identity verification during formal collection; timeout and crash cleanup remain unverified','Synchronization occurs before the window and must not run in the E2E measurement path','This is one diagnostic session, not a formal readiness or validation claim']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
