"""Compare actual instrumented consumer forward batch memberships with replay."""
import collections,json,pathlib,sys,tarfile
root=pathlib.Path(sys.argv[1]);archive=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(exist_ok=False)
if json.loads((root/'status.json').read_text())['status']!='completed':raise ValueError('replays incomplete')
cases={p.name:p for p in root.iterdir() if (p/'request-map.json').exists()};ids={};real=collections.defaultdict(list)
for name,case in cases.items():
 for m in json.loads((case/'request-map.json').read_text()):ids[m['decode_id']+'-0']=(name,int(m['simulator_request_id']))
with tarfile.open(archive) as t:
 for line in t.extractfile('compute-events-85025.jsonl'):
  e=json.loads(line)
  if e.get('event')!='model_step':continue
  groups=e.get('groups',[]);hits=[g for g in groups if g['request_id'] in ids and not g['is_prompt']]
  if not hits:continue
  if len(hits)!=len(groups) or len({ids[g['request_id']][0] for g in hits})!=1:raise ValueError('real mixed/unmapped step cannot be compared')
  case=ids[hits[0]['request_id']][0];real[case].append((e['host_start_ns'],tuple(sorted(ids[g['request_id']][1] for g in hits))))
results=[]
for name,case in sorted(cases.items()):
 actual=[x[1] for x in sorted(real[name])];caseout={'case':name,'real_decode_steps':len(actual),'real_batch_sizes':dict(collections.Counter(map(len,actual))),'roles':{}}
 expected_requests=len(json.loads((case/'request-map.json').read_text()))
 if sum(map(len,actual))!=7*expected_requests:raise ValueError('real decode coverage mismatch: '+name)
 for role in ('dag','adapted_baseline'):
  f=list((case/role).glob('*/chrome_trace.json'))
  if len(f)!=1:raise ValueError('trace missing')
  trace=json.loads(f[0].read_text())['traceEvents'];steps=[(e['ts'],tuple(sorted(int(i) for i in e['args']['request_ids']))) for e in trace if e.get('ph')=='X' and e.get('pid')==1 and e.get('args',{}).get('request_ids') and e['args'].get('batch_size')]
  steps=[x[1] for x in sorted(steps)]
  if sum(map(len,steps))!=7*expected_requests:raise ValueError('sim decode coverage mismatch: '+name+' '+role)
  def per_request(seq):
   out=collections.defaultdict(list)
   for group in seq:
    for rid in group:out[rid].append(list(group))
   return out
  x,y=per_request(actual),per_request(steps);equal=sum(a==b for rid in x for a,b in zip(x[rid],y[rid]));total=sum(map(len,x.values()))
  caseout['roles'][role]={'sim_decode_steps':len(steps),'sim_batch_sizes':dict(collections.Counter(map(len,steps))),'per_request_step_group_matches':equal,'per_request_steps':total,'interpretation':'compares members at each request decode index, not execution time'}
 results.append(caseout)
result={'status':'instrumented_real_wave_diagnostic','cases':results,'limitations':['One preselected measured wave per shape, 8 output tokens; not representative of full validation','Real synchronization and hooks perturb scheduling','Exact request-step membership compares model grouping, not its predicted fee or timing','Candidate transfer cost and scheduling still provisional','Adapted baseline is not pristine original','No formal validation or accuracy claim']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
