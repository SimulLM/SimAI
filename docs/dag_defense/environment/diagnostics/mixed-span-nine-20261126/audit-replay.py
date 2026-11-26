import json,pathlib,collections
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/mixed-span-nine-replay-20261126');r={}
for mode in ('baseline','dag'):
 assert (p/mode/'exit').read_text().strip()=='0';r[mode]=[json.loads(x) for x in (p/mode/'forward.jsonl').read_text().splitlines()]
def key(row):return (row['phase'],tuple(row['request_ids']),tuple(row['contexts']),tuple(tuple(v) if isinstance(v,list) else v for v in row['lookup_key']))
a={key(x):x for x in r['baseline']};b={key(x):x for x in r['dag']};assert len(a)==len(r['baseline'])==138 and len(b)==len(r['dag'])==130
common=a.keys()&b.keys();assert len(common)==4 and all(a[k]['forward_ms']==b[k]['forward_ms'] for k in common)
patterns={m:{str(k):v for k,v in collections.Counter(tuple(sorted(int(t-min(x['contexts'])) for t in x['contexts'])) for x in rows if x['phase']=='decode').items()} for m,rows in r.items()}
out={'baseline_batches':138,'dag_batches':130,'paired_batches':4,'paired_forward_costs_equal':True,'patterns':patterns,'limitations':['adapted baseline not pristine','synthetic trace','first-token fee omitted','not full E2E or validation']};pathlib.Path(__file__).with_name('replay-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
