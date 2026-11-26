import pathlib,csv,json,collections,statistics,re
p=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/calibration-concurrent-independent-20261126');out=[]
def number(s):
 m=re.search(r'-?\d+(?:\.\d+)?',s);return float(m.group()) if m else None
for rep in range(3):
 data=list(csv.reader((p/f'server-{rep}-telemetry.csv').open()))[1:]
 for gpu in (0,1):
  a=[r for r in data if len(r)>=7 and r[1].strip()==str(gpu)];sm=[number(r[3]) for r in a];temp=[number(r[6]) for r in a];power=[number(r[5]) for r in a];sm=[x for x in sm if x is not None];temp=[x for x in temp if x is not None];power=[x for x in power if x is not None];out.append({'repeat':rep,'gpu':gpu,'samples':len(a),'sm_mhz_min':min(sm) if sm else None,'sm_mhz_median':statistics.median(sm) if sm else None,'sm_mhz_max':max(sm) if sm else None,'temperature_c_min':min(temp) if temp else None,'temperature_c_max':max(temp) if temp else None,'power_w_median':statistics.median(power) if power else None})
r={'summary':out,'limits':['One-second device samples cannot attribute request latency to clocks or identify short throttling.','Wall-clock telemetry was not directly correlated to monotonic request timestamps.','GPU clocks/temperature do not include CPU scheduling, network, storage, or software contention; causation remains unknown.']};(p/'telemetry-summary.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
