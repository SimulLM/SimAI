import collections,csv,hashlib,json,pathlib
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');original=root/'dynamic-calibration-512-20261126/concurrent-0/dag';new=root/'calibration-transfer-occupancy-20261126';baseline=root/'dynamic-calibration-512-20261126/concurrent-0/baseline';out=pathlib.Path(__file__).parent
assert all((p/'exit').read_text().strip()=='0' for p in (original,new,baseline));oc=json.loads((original/'command.json').read_text());nc=json.loads((new/'command.json').read_text());outflags={'--metrics_config_output_dir','--metrics_config_cache_dir','--random_forrest_execution_time_predictor_config_simai_dir','--dag_pd_config'}
def normalized(cmd):
 a=cmd[:]
 for i,v in enumerate(a[:-1]):
  if v in outflags:a[i+1]='<output>'
 return a
assert normalized(oc)==normalized(nc)
configs=[pathlib.Path(oc[i+1]) for i,x in enumerate(oc) if x=='--dag_pd_config'];orig=json.loads(configs[0].read_text());changed=json.loads((new/'pd-config.json').read_text());assert orig['occupies_gpu'] is True and changed['occupies_gpu'] is False and all(orig[k]==changed[k] for k in orig if k not in ('occupies_gpu','evidence'))
data={};keys={};seqs={}
for mode,folder in [('baseline',baseline),('dag_true',original),('dag_false',new)]:
 d=next(folder.glob('2026*'));metrics={int(x['Request Id']):x for x in csv.DictReader((d/'request_metrics.csv').open())};assert len(metrics)==32 and all(float(m['request_num_prefill_tokens'])==512 and float(m['request_num_decode_tokens'])==64 for m in metrics.values());ev=sorted(json.loads((d/'chrome_trace.json').read_text())['traceEvents'],key=lambda x:x.get('ts',0));hist=collections.Counter();seen={};seq=[]
 for x in ev:
  a=x.get('args',{});ids=tuple(sorted(a.get('request_ids',[])))
  if x.get('ph')!='X' or x.get('pid') not in (0,1) or not ids:continue
  k=(x['pid'],ids,tuple((i,hist[i]) for i in ids),tuple(sorted(zip(a['request_ids'],a['num_tokens']))));assert k not in seen;seen[k]=x
  if x['pid']==1:
   assert all(x['ts']/1e6+1e-9>=float(metrics[i]['decode_arrived_at']) for i in ids)
   seq.append({'key':str(k),'ids':ids,'start_s':x['ts']/1e6,'end_s':(x['ts']+x['dur'])/1e6});hist.update(ids)
 assert len(hist)==32 and all(hist[i]==63 for i in metrics);keys[mode]=seen;seqs[mode]=seq;tasks=[json.loads(x) for x in (folder/'first-token.jsonl').read_text().splitlines()];sub=[x for x in tasks if x['event']=='submit'];done={rid:x['time_s'] for x in tasks if x['event']=='complete' for rid in x['request_ids']};assert len(done)==32 and sum(len(x['request_ids']) for x in sub)==32
 for x in sub:
  assert all(x['time_s']+1e-9>=float(metrics[int(i)]['decode_arrived_at']) for i in x['request_ids'])
 for x in seq:
  assert all(x['start_s']+1e-9>=done[str(i)] for i in x['ids'])
 data[mode]={'batch_count':len(seen),'first_token_groups':dict(collections.Counter(str(len(x['request_ids'])) for x in sub)),'request8_ready_s':float(metrics[8]['decode_arrived_at']),'request8_first_end_s':done['8'],'request_complete_s':{str(i):float(x['completed_at']) for i,x in metrics.items()}}
for mode in ('dag_true','dag_false'):
 a=keys['baseline'];b=keys[mode];common=a.keys()&b.keys();d=next((original if mode=='dag_true' else new).glob('2026*'));costs=collections.defaultdict(float)
 for x in csv.DictReader((d/'timeline.csv').open()):costs[x['graph_id']]+=float(x['duration_s'])
 differences=[]
 for k in common:
  e=b[k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/";g=[x for x in costs if x.startswith(prefix)];assert len(g)==1;differences.append(abs(float(a[k]['dur'])/1e6-costs[g[0]]))
 assert not differences or max(differences)<1e-9
 first=next(({'position':i,'baseline':x,'dag':y} for i,(x,y) in enumerate(zip(seqs['baseline'],seqs[mode])) if x['key']!=y['key']),None)
 data[mode]['against_baseline']={'paired':len(common),'baseline_batches':len(a),'dag_batches':len(b),'max_fee_difference_s':max(differences) if differences else None,'first_decode_difference':first}
res={'cases':data,'command_difference':'only GPU occupancy flag/evidence and output paths','limitations':['single calibration sequence','both occupancy settings are model hypotheses not physical bounds','modified baseline not pristine','no production cost or formal validation']};(out/'audit.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
