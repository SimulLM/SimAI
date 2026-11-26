import pathlib,json,sys
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/common-cost-matrix-v2-20261126');rows=[]
for case in sorted(x for x in p.iterdir() if x.is_dir()):
 for role in ('dag','baseline'):
  ev=json.loads(next((case/role).glob('*/chrome_trace.json')).read_text())['traceEvents'];counts=[sum(x['args']['num_tokens']) for x in ev if x.get('pid')==0 and x.get('ph')=='X' and x.get('args',{}).get('num_tokens')];rows.append({'case':case.name,'role':role,'prefill_batch_tokens':counts,'limit':4096,'within_limit':bool(counts) and all(x<=4096 for x in counts)})
out={'status':'pass' if all(x['within_limit'] for x in rows) else 'fail','rows':rows,'limits':'This checks simulator trace, not service scheduling equivalence.'};(p/'prefill-cap-audit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));sys.exit(out['status']!='pass')
