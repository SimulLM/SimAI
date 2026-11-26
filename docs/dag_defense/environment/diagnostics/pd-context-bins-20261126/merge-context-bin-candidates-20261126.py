import csv,json,pathlib,collections,hashlib
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');inputs={'original':root/'pd-context-bin-profile-20261126','supplement':root/'pd-context-bin-supplement-20261126'};out=root/'pd-context-bin-combined-20261126';out.mkdir(exist_ok=False);groups=collections.defaultdict(list)
for source,folder in inputs.items():
 for r in csv.DictReader((folder/'forward-context-bins.csv').open()):
  k=(int(r['input_tokens']),int(r['actual_batch']),int(r['rounded_mean_context']),int(r['mixed_context']));r['source']=source
  if r['eligible']=='1':groups[k].append(r)
rows=[max(v,key=lambda x:(int(x['measured_waves']),int(x['warmup_waves']),x['source'])) for k,v in sorted(groups.items())]
with (out/'forward-context-bins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
summary=[]
for n in (1024,2048):
 for b in (1,2,3,4):
  v=[r for r in rows if int(r['input_tokens'])==n and int(r['actual_batch'])==b];summary.append({'input_tokens':n,'actual_batch':b,'point_count':len(v),'uniform_bins':sorted({int(r['rounded_mean_context']) for r in v if r['mixed_context']=='0'}),'mixed_bins':sorted({int(r['rounded_mean_context']) for r in v if r['mixed_context']=='1'})})
res={'status':'candidate_not_frozen','selection':'each selected source independently has >=10 distinct warmup and >=30 measured waves; choose most measured waves, never pool correlated steps across sources; preserve actual batch and mixed-context label','source_hashes':{k:{'bins_sha256':hashlib.sha256((v/'forward-context-bins.csv').read_bytes()).hexdigest(),'manifest_sha256':hashlib.sha256((v/'manifest.json').read_bytes()).hexdigest()} for k,v in inputs.items()},'points':len(rows),'summary':summary,'limitations':['full model forward only; excludes logits, sampler, CPU, router and KV','context bins do not prove equivalence across mixed shapes','GPU events and synchronization perturb service','no interpolation or missing-point imputation','candidate is not a frozen complete common-cost profile']};(out/'manifest.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
