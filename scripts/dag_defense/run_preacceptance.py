"""One pinned 2048/128 x concurrency-4 x 32 real run, predictions and scoring.

Not validation. No E2E-based fitting or diagnostic variant selection. Never overwrites
an attempt, and always stops its own service process group before CPU replay.
"""
import argparse,asyncio,collections,csv,hashlib,json,os,pathlib,random,signal,statistics,subprocess,sys,time,urllib.request
from collect_validation_run import run_case
from reconcile_validation_run import reconcile
from export_validation_requests import export

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def read(p):return json.loads(p.read_text())
def require(v,s):
    if not v:raise ValueError(s)
def csvrows(p):
    with p.open(newline='') as f:return list(csv.DictReader(f))
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
def identity(repo):
    return {'head':git(repo,'rev-parse','HEAD'),'diff_sha256':hashlib.sha256(git(repo,'diff','HEAD').encode()).hexdigest()}
def writecsv(p,rr):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
def stop(proc):
    if proc is None:return
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=15)

def idle(service,out):
    # Use already-existing gauge collector; successful KV receives and host events
    # are reconciled separately. No automatic retry or admission reopening.
    from probe_pd_idle import fetch,router_state
    samples=[]
    for i in range(3):
        record={'timestamp_ns':time.monotonic_ns(),'router':router_state(service/'router-events.jsonl'),
                'producer':fetch('http://127.0.0.1:18100/metrics'),'consumer':fetch('http://127.0.0.1:18200/metrics')}
        samples.append(record);dump(out/'idle.json',samples)
        require(record['router']['inflight']==0 and record['router']['unresolved_errors']==0,'router not idle')
        for role in ('producer','consumer'):
            for name in ('vllm:num_requests_running','vllm:num_requests_waiting','vllm:gpu_cache_usage_perc'):
                require(record[role][name]==0,'nonzero/missing required idle gauge '+role+'/'+name)
            for name in ('vllm:num_requests_swapped','vllm:cpu_cache_usage_perc'):
                value=record[role][name]
                require(value is None or value==0,'nonzero optional idle gauge '+role+'/'+name)
        if i<2:time.sleep(2)

def worker_audit(out,reconciled):
    events=[]
    for p in (out/'service/events').glob('*.jsonl'):
        events.extend(json.loads(x) for x in p.read_text().splitlines())
    require(events,'no worker events')
    errors=[e for e in events if e['event'].endswith('_error')];require(not errors,'worker error '+str(errors[:1]))
    results=[]
    for r in (json.loads(x) for x in reconciled.read_text().splitlines()):
        ev={e['event']:e for e in r['server_events']}
        pid=ev['prefill_mapping']['backend_request_id']+'-0';did=ev['decode_mapping']['backend_request_id']+'-0'
        def find(role,name,rid):return [e for e in events if e['role']==role and e['event']==name and any(g['request_id']==rid for g in e.get('groups',[]))]
        ps=find('producer','send_kv_caches_and_hidden_states_host_start',pid);pe=find('producer','send_kv_caches_and_hidden_states_host_return',pid)
        ds=find('consumer','recv_kv_caches_and_hidden_states_host_start',did);de=find('consumer','recv_kv_caches_and_hidden_states_host_return',did)
        require(len(ps)==len(pe)==len(ds)==len(de)==1,'missing/duplicate KV host event '+r['request_id'])
        require(de[0]['kv_bypass'] is True,'KV bypass not observed '+r['request_id'])
        require(r['server_arrival_ns']<=ps[0]['timestamp_ns']<=pe[0]['timestamp_ns']<=ds[0]['timestamp_ns']<=de[0]['timestamp_ns']<=r['server_complete_ns'],'KV host event order '+r['request_id'])
        starts=find('consumer','model_step_host_start',did);ends=find('consumer','model_step_host_return',did)
        require(len(starts)==len(ends)==128,'consumer step count differs from 128 '+r['request_id'])
        require({x['step_id'] for x in starts}=={x['step_id'] for x in ends},'unreturned model step')
        results.append({'request_id':r['request_id'],'producer_id':pid,'consumer_id':did,'consumer_steps':len(ends),'kv_bypass':True,
                        'kv_recv_host_return_ns':de[0]['timestamp_ns']})
    dump(out/'worker-audit.json',{'requests':results,'limitations':['Host API return is not exact GPU KVReady.','Consumer bypass step emits token 1; following 127 steps generate tokens 2..128. Producer token is not sent to client.']})

def replay(out,root,mode,trace):
    repo=root/('SimAI-pristine-baseline' if mode=='baseline' else 'SimAI-pristine-predictor-repro')
    cmd=read(root/'dag-handoff/runs/pristine-real-arrival-20261126/concurrent-0'/mode/'command.json')
    dest=out/mode;dest.mkdir()
    options={'--trace_request_generator_config_trace_file':str(trace),'--trace_request_generator_config_max_tokens':'2176',
             '--metrics_config_output_dir':str(dest),'--metrics_config_cache_dir':str(dest/'cache'),
             '--random_forrest_execution_time_predictor_config_simai_dir':str(dest)}
    for i,x in enumerate(cmd):
        if x in options:cmd[i+1]=options[x]
    # Preserve source and cost selection; request only the existing trace exporter.
    for flag in ('--metrics_config_write_json_trace','--metrics_config_enable_chrome_trace'):
        if flag not in cmd:cmd.append(flag)
    dump(dest/'command.json',cmd)
    env=dict(os.environ,PYTHONPATH=str(repo/'vidur-alibabacloud')+':'+str(repo),WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
    for key in list(env):
        if key.startswith(('BATCH_FIRST_TOKEN','FIXED_','FORWARD_','SIMAI_SERIAL_')):env.pop(key)
    with (dest/'process.log').open('w') as log:code=subprocess.run(cmd,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    (dest/'exit').write_text(str(code)+'\n');require(code==0,mode+' replay exit '+str(code))
    mm=list(dest.glob('2026*/request_metrics.csv'));require(len(mm)==1,'missing/ambiguous metrics '+mode)
    return mm[0]

def score_and_audit(out,root,reconciled,metrics):
    actual=[json.loads(x) for x in reconciled.read_text().splitlines()];pred={};audit={};batchsets={};events_by_mode={}
    for mode,mp in metrics.items():
        rr=csvrows(mp);require(len(rr)==32,'prediction rows !=32 '+mode)
        mi={int(float(r['Request Id'])):r for r in rr};require(set(mi)==set(range(32)),'prediction IDs '+mode)
        pred[mode]=mi;events=read(mp.parent/'chrome_trace.json')['traceEvents']
        events=sorted((e for e in events if e.get('ph')=='X' and e.get('pid') in (0,1) and e.get('args',{}).get('request_ids')),key=lambda e:e['ts'])
        history=collections.Counter();prefill=collections.Counter();keys={};early=[]
        for e in events:
            a=e['args'];ids=a['request_ids'];require(len(ids)==len(set(ids)),'duplicate batch member')
            key=(e['pid'],tuple(sorted(ids)),tuple((i,history[i]) for i in sorted(ids)),tuple(sorted(zip(ids,a['num_tokens']))))
            require(key not in keys,'duplicate batch charge '+mode);keys[key]=e
            for rid,n in zip(ids,a['num_tokens']):
                require(int(n)==(2048 if e['pid']==0 else 1),'wrong per-step token amount')
                require(e['ts']/1e6+1e-9>=float(mi[rid]['arrived_at']),'executed before request arrival '+mode)
                if e['pid']==1 and e['ts']/1e6+1e-9<float(mi[rid]['decode_arrived_at']):
                    early.append({'request_id':rid,'batch_id':a['batch_id'],'start_s':e['ts']/1e6,'ready_s':float(mi[rid]['decode_arrived_at'])})
            (prefill if e['pid']==0 else history).update(ids)
        require(all(history[i]==127 and prefill[i]==1 for i in range(32)),'token or Decode rounds mismatch '+mode)
        predictions=[]
        for i,a in enumerate(actual):
            m=mi[i];require(int(float(m['request_num_prefill_tokens']))==2048 and int(float(m['request_num_decode_tokens']))==128,'clipped model tokens')
            predictions.append({'request_id':a['request_id'],'input_id':a['input_id'],'predicted_e2e_s':float(m['completed_at'])-float(m['arrived_at'])})
        writecsv(out/(mode+'-predictions.csv'),predictions)
        audit[mode]={'batches':len(keys),'early_events':early,'early_is_gate':mode=='dag','token_counts_passed':True};batchsets[mode]=keys;events_by_mode[mode]=events
    common=batchsets['baseline'].keys() & batchsets['dag'].keys()
    taskrows=csvrows(metrics['dag'].parent/'timeline.csv')
    graphs=collections.defaultdict(list)
    for r in taskrows:graphs[r['graph_id']].append(r)
    matched_diff=[]
    for k in common:
        e=batchsets['dag'][k];prefix=f"replica{e['pid']}/stage0/batch{e['args']['batch_id']}/"
        matches=[g for g in graphs if g.startswith(prefix)];require(len(matches)==1,'ambiguous model graph')
        modeled_fee=sum(float(r['duration_s']) for r in graphs[matches[0]])
        matched_diff.append(abs(batchsets['baseline'][k]['dur']/1e6-modeled_fee))
    audit['paired_batches']={'count':len(common),'baseline_fraction':len(common)/len(batchsets['baseline']),'dag_fraction':len(common)/len(batchsets['dag']),
                             'max_fee_difference_s':max(matched_diff,default=None),'not_a_pairing_threshold':True}
    keys=[(r['graph_id'],r['task_id']) for r in taskrows]
    duplicates=len(keys)-len(set(keys));bad=[r for r in taskrows if r['state']!='COMPLETED' or int(r['completion_count'])!=1 or float(r['start_at_s'])+1e-9<float(r['ready_at_s'])]
    audit['task_ledger']={'duplicate_keys':duplicates,'invalid_or_early_tasks':bad[:10]}
    result=[]
    for i,a in enumerate(actual):
        b=float(pred['baseline'][i]['completed_at'])-float(pred['baseline'][i]['arrived_at']);d=float(pred['dag'][i]['completed_at'])-float(pred['dag'][i]['arrived_at']);t=a['server_e2e_s']
        result.append({'request_id':a['request_id'],'input_id':a['input_id'],'status':a['status'],'actual_s':t,'baseline_s':b,'dag_s':d,'baseline_abs_error_s':abs(b-t),'dag_abs_error_s':abs(d-t),'baseline_relative_error':abs(b-t)/t,'dag_relative_error':abs(d-t)/t})
    writecsv(out/'scores.csv',result)
    summary={'kind':'preacceptance_not_validation','requests':32,'baseline_mae_s':statistics.mean(r['baseline_abs_error_s'] for r in result),'dag_mae_s':statistics.mean(r['dag_abs_error_s'] for r in result),'baseline_mean_relative_error':statistics.mean(r['baseline_relative_error'] for r in result),'dag_mean_relative_error':statistics.mean(r['dag_relative_error'] for r in result),'boundary':{'actual':'router stream completion minus router arrival','prediction':'last modeled batch end minus same actual router arrival','correction_s':0,'residual':'Unmodeled router/host tail stays in error; not subtracted or fitted.'}}
    dump(out/'score-summary.json',summary);dump(out/'simulation-audit.json',audit)
    return audit

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--retry-of',type=pathlib.Path);p.add_argument('--data-root',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp'));a=p.parse_args()
    out=a.output;out.mkdir(parents=True,exist_ok=False);root=a.data_root;repo=root/'SimAI-handoff';proc=None;checks=[]
    dump(out/'attempt.json',{'kind':'preacceptance_not_validation','retry_of':str(a.retry_of) if a.retry_of else None,'prior_attempt_result_sha256':sha(a.retry_of/'result.json') if a.retry_of else None})
    def check(name,fn):
        try:r=fn();checks.append({'assertion':name,'status':'passed','detail':r});return r
        except Exception as e:checks.append({'assertion':name,'status':'failed','failure':str(e)});return None
        finally:dump(out/'assertions.json',checks)
    try:
        original=root/'SimAI-pristine-baseline';dag=root/'SimAI-pristine-predictor-repro'
        require(identity(original)['head']=='cef83f9ddd96540e3e9f48934f11335d52d54fce' and not git(original,'diff','HEAD'),'original reference modified')
        predictor='vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'
        require(set(git(dag,'diff','HEAD','--name-only').splitlines()).issubset({predictor}),'DAG scheduler/readiness changed')
        require(sha(original/predictor)==sha(dag/predictor),'predictors differ')
        launcher=repo/'docs/dag_defense/environment/scripts/start-pd-light-events.sh'
        tracked=[launcher,repo/'docs/dag_defense/environment/scripts/pd_stream_proxy.py',repo/'docs/dag_defense/environment/scripts/pd-light-events/sitecustomize.py',pathlib.Path(__file__),repo/'scripts/dag_defense/collect_validation_run.py']
        before={str(x):sha(x) for x in tracked}
        dump(out/'candidate-pin.json',{'kind':'preacceptance_candidate_not_formal_freeze','original':identity(original),'dag_fee_provider_only':identity(dag),'service':identity(repo),'files':before,'no_parameter_fitting':True})
        (out/'original-source.diff').write_text(git(original,'diff','HEAD'));(out/'dag-source.diff').write_text(git(dag,'diff','HEAD'))
        rng=random.Random(2026112604);runid=out.name;inputs=[]
        for i in range(32):
            tokens=[1]+[rng.randrange(4,32000) for _ in range(2047)];h=hashlib.sha256((json.dumps(tokens,separators=(',',':'))+'\n').encode()).hexdigest()
            inputs.append({'run_id':runid,'request_id':runid+'-r'+str(i),'input_id':runid+'-i'+str(i),'wave':i//4,'index_in_wave':i%4,'input_ids':tokens,'input_sha256':h})
        (out/'inputs.jsonl').write_text(''.join(json.dumps(r,separators=(',',':'))+'\n' for r in inputs))
        spec={'run_id':runid,'input_tokens':2048,'output_tokens':128,'concurrency':4,'requests':32,'seed':2026112604,'kind':'preacceptance_not_validation'};dump(out/'spec.json',spec)
        require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU already has compute processes')
        env=dict(os.environ,PD_ROUTE_DIR=str(out/'service'))
        with (out/'launcher.log').open('w') as log:proc=subprocess.Popen(['bash',str(launcher)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+420
        while not (out/'service/ready').exists():
            require(proc.poll() is None,'service exited before ready')
            require(time.monotonic()<deadline,'service startup timeout');time.sleep(1)
        # Warm one complete wave, outside the measured 32; separate input IDs and files.
        warm=[]
        for i,r in enumerate(inputs[:4]):warm.append(dict(r,run_id=runid+'-warm',request_id=runid+'-warm'+str(i),input_id=runid+'-wi'+str(i),wave=0))
        warmresult=asyncio.run(run_case(dict(spec,run_id=runid+'-warm'),warm,out/'warmup','http://127.0.0.1:18300/v1/completions',str(root/'models/Llama-2-7b-hf'),180))
        require(warmresult['failure'] is None,'warmup failed; abort and retain')
        idle(out/'service',out)
        collected=asyncio.run(run_case(spec,inputs,out/'client','http://127.0.0.1:18300/v1/completions',str(root/'models/Llama-2-7b-hf'),180))
        require(collected['failure'] is None,'measured collection failed; abort, retain not-submitted rows')
        stop(proc);proc=None
        require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU process remained after service stop')
        allrouter=[json.loads(x) for x in (out/'service/router-events.jsonl').read_text().splitlines()]
        measured_ids={e['request_id'] for e in allrouter if e['event']=='server_arrival' and e.get('client_request_id') in {r['request_id'] for r in inputs}}
        (out/'measured-router-events.jsonl').write_text(''.join(json.dumps(e,separators=(',',':'))+'\n' for e in allrouter if e['request_id'] in measured_ids))
        rec=check('32_complete_router_token_records',lambda:reconcile(out/'inputs.jsonl',out/'client/client-events.jsonl',out/'measured-router-events.jsonl',out/'reconciled'))
        require(rec is not None and rec['status']=='complete','reconciliation failed')
        export(out/'reconciled/requests.jsonl',out/'client/run-spec.json',out/'actual')
        check('physical_PD_host_events_and_128_consumer_steps',lambda:worker_audit(out,out/'reconciled/requests.jsonl'))
        rr=[json.loads(x) for x in (out/'reconciled/requests.jsonl').read_text().splitlines()];origin=min(r['server_arrival_ns'] for r in rr)
        writecsv(out/'trace.csv',[{'arrived_at':(r['server_arrival_ns']-origin)/1e9,'num_prefill_tokens':2048,'num_decode_tokens':128} for r in rr])
        dump(out/'request-map.json',[{'simulator_request_id':i,'request_id':r['request_id'],'router_id':r['router_id'],'server_arrival_ns':r['server_arrival_ns'],'server_complete_ns':r['server_complete_ns']} for i,r in enumerate(rr)])
        metrics={mode:replay(out,root,mode,out/'trace.csv') for mode in ('baseline','dag')}
        audit=score_and_audit(out,root,out/'reconciled/requests.jsonl',metrics)
        check('DAG_no_decode_before_modeled_KV_ready',lambda:require(not audit['dag']['early_events'],'EARLY_DECODE '+str(audit['dag']['early_events'][:3])))
        check('unique_completed_DAG_tasks',lambda:require(audit['task_ledger']['duplicate_keys']==0 and not audit['task_ledger']['invalid_or_early_tasks'],'duplicate/incomplete/early task'))
        check('paired_batch_fee_parity',lambda:require(not audit['paired_batches']['count'] or audit['paired_batches']['max_fee_difference_s']<1e-9,'matched fees differ'))
        # Use only this selected primary profile; no revised-candidate gap tables.
        from formal_preflight import coverage
        cov=coverage(root/'dag-handoff/runs/pd-pull-calibration-replay-20261126/profile');dump(out/'fee-domain.json',cov)
        check('reachable_fee_domain',lambda:require(not cov['gaps'],'FEE_DOMAIN_GAPS '+json.dumps(cov['gaps'])))
        fee=repo/'docs/dag_defense/environment/diagnostics/pristine-dag-fee-contract-20261126/README.md'
        check('physical_fee_nonoverlap_contract',lambda:require('**Missing from original**' not in fee.read_text(),'FEE_SCOPE_UNRESOLVED: consumer bypass-first-token, producer head, KV install and sampler/GPU overlap lack common exclusive mapping; '+str(fee)))
        check('candidate_unchanged',lambda:require({str(x):sha(x) for x in tracked}==before,'candidate changed during run'))
    except Exception as e:checks.append({'assertion':'end_to_end_execution','status':'failed','failure':type(e).__name__+': '+str(e)})
    finally:
        stop(proc)
        dump(out/'assertions.json',checks)
        failed=[c for c in checks if c['status']=='failed']
        dump(out/'result.json',{'status':'failed' if failed else 'passed','kind':'preacceptance_not_validation','formal_rounds_added':0,'assertions':checks,'no_accuracy_or_batch_match_threshold':True,'automatic_formal_start':False})
        files=[x for x in out.rglob('*') if x.is_file() and x.name!='SHA256SUMS'];(out/'SHA256SUMS').write_text(''.join(sha(x)+'  '+str(x.relative_to(out))+'\n' for x in sorted(files)))
    print((out/'result.json').read_text(),flush=True);return 2 if failed else 0
if __name__=='__main__':raise SystemExit(main())
