import json,pathlib,collections
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/uniform-forward-2048-four-replay-v4-20261126');rows={}
for mode,exitcode in (('baseline','1'),('dag','0')):
 assert (p/mode/'exit').read_text().strip()==exitcode
 rows[mode]=[json.loads(x) for x in (p/mode/'forward.jsonl').read_text().splitlines()]
log=(p/'baseline/process.log').read_text();assert 'mixed context span > 1 unsupported' in log and '2058.0' in log and '2049.0' in log
def key(r):return r['phase'],tuple(r['request_ids']),tuple(r['contexts']),tuple(r['lookup_key'])
a={key(r):r for r in rows['baseline']};b={key(r):r for r in rows['dag']};common=a.keys()&b.keys();assert len(a)==11 and len(b)==130 and len(common)==3 and all(a[k]['forward_ms']==b[k]['forward_ms'] for k in common)
r={'baseline':'failed on contexts [2058,2058,2049,2049] after 11 forward batches','dag':'completed 130 forward batches','paired':len(common),'baseline_batches_before_failure':len(a),'dag_batches':len(b),'matched_costs_equal':True,'note':'synthetic trace; adapted baseline; incomplete comparison; first-token fee omitted; no formal validation'}
pathlib.Path(__file__).with_name('replay-audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
