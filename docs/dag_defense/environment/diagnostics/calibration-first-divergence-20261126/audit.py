import collections,csv,hashlib,json,pathlib
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/dynamic-calibration-512-20261126/concurrent-0');out=pathlib.Path(__file__).parent;res={}
for mode in ('baseline','dag'):
 p=root/mode;d=next(p.glob('2026*'));files=[d/'chrome_trace.json',d/'request_metrics.csv',p/'first-token.jsonl'];m={int(x['Request Id']):x for x in csv.DictReader(files[1].open())};ev=sorted(json.loads(files[0].read_text())['traceEvents'],key=lambda x:x.get('ts',0));hist=collections.Counter();seq=[]
 for x in ev:
  a=x.get('args',{});ids=sorted(a.get('request_ids',[]))
  if x.get('ph')=='X' and x.get('pid')==1 and ids:
   seq.append({'ids':ids,'prior_decode':[hist[i] for i in ids],'start_s':x['ts']/1e6,'end_s':(x['ts']+x['dur'])/1e6,'batch_id':a['batch_id']});hist.update(ids)
 steps=seq[254:262];tokens=[x for x in map(json.loads,files[2].open()) if any(str(i) in x['request_ids'] for i in (8,9))];res[mode]={'batch_window':steps,'requests':{str(i):{k:float(m[i][k]) for k in ('arrived_at','prefill_completed_at','decode_arrived_at','completed_at')} for i in (7,8,9)},'first_token_events':tokens,'source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
a=res['baseline'];b=res['dag'];assert a['batch_window'][4]['ids']==[7] and b['batch_window'][4]['ids']==[7,8];assert a['batch_window'][3]['ids']==b['batch_window'][3]['ids']==[6,7]
for mode,v in res.items():
 sub=next(x for x in v['first_token_events'] if x['event']=='submit' and x['request_ids']==['8']);end=next(x for x in v['first_token_events'] if x['event']=='complete' and x['request_ids']==['8']);assert sub['time_s']>=v['requests']['8']['decode_arrived_at'] and end['time_s']>sub['time_s']
 if mode=='baseline':assert v['batch_window'][4]['start_s']<sub['time_s'] and sub['time_s']>=v['batch_window'][4]['end_s']-1e-9
 else:assert sub['time_s']>=v['batch_window'][3]['end_s'] and v['batch_window'][4]['start_s']>=end['time_s']-1e-9
(out/'audit.json').write_text(json.dumps({'scope':'one calibration arrival replay, modeled event evidence','modes':res,'limitations':['not a single-variable causal experiment','modeled ready is not physical KVReady','different prior timeline and source transfer contention affect event timing','not formal validation']},indent=2)+'\n');print('PASS first difference and ordering')
