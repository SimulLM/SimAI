import csv,json,math,pathlib,statistics,hashlib
source=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics/light-serial-512-20261126/analysis.csv');out=pathlib.Path(__file__).parent
rows=[r for r in csv.DictReader(source.open()) if r['stage'].startswith('measured-')];assert len(rows)==20 and len({r['router_id'] for r in rows})==20
pairs=[]
for r in rows:
 a=int(r['first_step_return_ns']);b=int(r['router_first_ns']);c=int(r['last_step_return_ns']);d=int(r['final_choice_ns']);e=int(r['completion_ns']);assert a<=b<=c<=d<=e
 pairs.append({'router_id':r['router_id'],'first_step_return_ns':a,'first_router_observed_ns':b,'last_step_return_ns':c,'final_choice_ns':d,'server_complete_ns':e,'first_host_to_router_ms':(b-a)/1e6,'last_host_to_choice_ms':(d-c)/1e6,'choice_to_complete_ms':(e-d)/1e6})
with (out/'paired.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=pairs[0]);w.writeheader();w.writerows(pairs)
def stat(key):
 a=sorted(x[key] for x in pairs);return {'median_ms':statistics.median(a),'min_ms':a[0],'p95_ms':a[math.ceil(.95*len(a))-1],'max_ms':a[-1]}
result={'requests':len(pairs),'first_host_to_router':stat('first_host_to_router_ms'),'last_host_to_choice':stat('last_host_to_choice_ms'),'choice_to_complete':stat('choice_to_complete_ms'),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'limitations':['worker host return is not GPU completion','first and final intervals include frontend output handling and may include waiting for device work','one input and instrumented session, no independent restarts','observed quantiles are descriptive, not upper bounds','no additive fee or validation claim']}
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
