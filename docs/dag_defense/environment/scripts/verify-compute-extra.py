import csv,json,sys
from pathlib import Path
p=Path(sys.argv[1]);rows=list(csv.DictReader((p/'summary.csv').open()));lookup={(x['phase'],int(x['input_tokens']),int(x['actual_batch'])):x for x in rows};targets=[(phase,n,b) for phase in ('prefill','decode') for n in (512,1024,2048) for b in ((1,2) if phase=='prefill' and n==2048 else (1,2,4))];out=[]
for phase,n,b in targets:
 row=lookup.get((phase,n,b)); count=int(row['eligible_samples']) if row else 0
 out.append({'phase':phase,'input_tokens':n,'actual_batch':b,'eligible_samples':count,'passed':count>=30})
report={'target_shapes':len(out),'passed_shapes':sum(x['passed'] for x in out),'shapes':out};(p/'target-coverage.json').write_text(json.dumps(report,indent=2)+'\n');print(f"{report['passed_shapes']}/{report['target_shapes']} shapes pass");assert all(x['passed'] for x in out)
