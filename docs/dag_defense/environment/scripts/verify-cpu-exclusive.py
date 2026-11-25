import csv,json,sys
from pathlib import Path
p=Path(sys.argv[1]);rows=list(csv.DictReader((p/'summary.csv').open()));lookup={(x['event'],x['phase'],int(x['input_tokens']),int(x['actual_batch'])):x for x in rows}
names=('schedule','prepare_inputs','sampler_synchronized','process_model_outputs')
target=[(event,phase,n,b) for event in names for phase in ('prefill','decode') for n in (512,1024,2048) for b in ((1,2) if phase=='prefill' and n==2048 else (1,2,4))]
shapes=[]
for event,phase,n,b in target:
 row=lookup.get((event,phase,n,b));count=int(row['eligible_samples']) if row else 0
 shapes.append({'event':event,'phase':phase,'input_tokens':n,'actual_batch':b,'eligible_samples':count,'passed':count>=30})
report={'target_shapes':len(shapes),'passed_shapes':sum(x['passed'] for x in shapes),'shapes':shapes};(p/'target-coverage.json').write_text(json.dumps(report,indent=2)+'\n');print(f"{report['passed_shapes']}/{report['target_shapes']} host-timing shapes have at least 30 samples after 10 shape warmups");assert all(x['passed'] for x in shapes)
