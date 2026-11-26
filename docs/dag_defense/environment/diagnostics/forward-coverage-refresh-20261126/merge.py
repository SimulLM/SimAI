import csv,pathlib,hashlib,json
root=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/environment/diagnostics');out=pathlib.Path(__file__).parent
first=root/'pd-context-bins-20261126/pd-context-bin-combined-20261126/forward-context-bins.csv';second=root/'pd-context-batch3-20261126/forward-context-bins.csv'; base=root/'pd-eager-profile-20261126/candidate/forward-cost.csv'
def read(p):
 with p.open() as f:return list(csv.DictReader(f))
rows=read(first);keys={(r['input_tokens'],r['actual_batch'],r['rounded_mean_context'],r['mixed_context']) for r in rows};added=[];overlaps=[]
for row in read(second):
 if row['eligible']!='1':continue
 assert int(row['warmup_waves'])>=10 and int(row['measured_waves'])>=30
 key=tuple(row[x] for x in ('input_tokens','actual_batch','rounded_mean_context','mixed_context'))
 if key in keys:overlaps.append(key);continue
 row['source']='batch3-supplement';rows.append(row);keys.add(key);added.append(key)
fields=['input_tokens','actual_batch','rounded_mean_context','mixed_context','warmup_waves','measured_waves','median_forward_ms','eligible','source'];rows.sort(key=lambda r:tuple(int(r[k]) for k in fields[:4]))
with (out/'strict-forward-context-bins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(out/'merge-audit.json').write_text(json.dumps({'original_points':len(read(first)),'added':added,'overlap_uses_original':overlaps,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (first,second,base)},'not_included':'pooled composition-specific 1024 batch3 candidates are kept separate','frozen':False},indent=2)+'\n')
print('original',len(read(first)),'added',len(added),'duplicate kept original',len(overlaps),'total',len(rows))
