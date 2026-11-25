import csv,json,sys
from pathlib import Path
r=Path(sys.argv[1]);rows=list(csv.DictReader((r/'summary.csv').open()));lookup={(x['phase'],int(x['input_tokens']),int(x['actual_batch'])):x for x in rows}
target=[('prefill',n,b) for n in (512,1024,2048) for b in ((1,2,4) if n<2048 else (1,2))]+[('decode',n,b) for n in (512,575,638,1024,1087,1150,2048,2111,2174) for b in (1,2,4)]
coverage=[]
for phase,n,b in target:
 x=lookup.get((phase,n,b)); count=int(x['eligible_samples']) if x else 0
 coverage.append({'phase':phase,'input_tokens':n,'decode_context_tokens':n+1 if phase=='decode' else None,'actual_batch':b,'eligible_samples':count,'passed':count>=30})
report={'target_shapes':len(target),'passed_shapes':sum(x['passed'] for x in coverage),'shape_definition':'eager single GPU, layer 16; 2048 prefill batches of 4 split by 4096 token scheduler limit','shapes':coverage}
(r/'target-coverage.json').write_text(json.dumps(report,indent=2)+'\n');print(f"{report['passed_shapes']}/{report['target_shapes']} target shapes have at least 30 samples after 10 shape warmups")
assert all(x['passed'] for x in coverage)
