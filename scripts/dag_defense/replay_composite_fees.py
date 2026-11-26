"""Fee-only replay of retained real requests, including backlog/resource audit."""
import argparse,collections,csv,hashlib,json,os,pathlib,subprocess,sys
from composite_fee import CompositeFees,require,sha
from run_preacceptance import score_and_audit,csvrows,writecsv,dump

ROOT=pathlib.Path('/root/autodl-tmp');REPO=ROOT/'SimAI-handoff'

def launch(mode,trace,dest,fees_path,n):
    fees=CompositeFees(fees_path);dag=mode=='dag';original=ROOT/('SimAI-pristine-predictor-repro' if dag else 'SimAI-pristine-baseline')
    template=ROOT/'dag-handoff/runs/preaccept-2048-128-c4-20261126-2236/prediction-retry-01'/('dag' if dag else 'baseline')/'command.json'
    cmd=json.loads(template.read_text());bootstrap=REPO/'scripts/dag_defense/composite_fee_bootstrap.py'
    require(cmd[1:3]==['-m','vidur.main'],'unexpected template')
    cmd[1:3]=[str(bootstrap)];dest.mkdir(parents=True,exist_ok=False)
    receiver_s=fees.receiver(n);billing=(n+1)*524288;bytes_per_s=billing/receiver_s;gibit=bytes_per_s*8/1024**3
    options={'--trace_request_generator_config_trace_file':str(trace),'--trace_request_generator_config_max_tokens':str(n+128),
             '--metrics_config_output_dir':str(dest),'--metrics_config_cache_dir':str(dest/'cache'),
             '--random_forrest_execution_time_predictor_config_simai_dir':str(dest),
             '--replica_config_pd_p2p_comm_bandwidth':str(gibit)}
    if dag:
        original_pd=ROOT/'dag-handoff/runs/pd-pull-calibration-replay-20261126/pd-config.json'
        pd=json.loads(original_pd.read_text());pd.update(bandwidth_bytes_per_s=bytes_per_s,evidence=str(fees_path)+'; composite receiver coefficient, NOT physical link bandwidth')
        dump(dest/'pd-config.json',pd);options['--dag_pd_config']=str(dest/'pd-config.json')
    for i,x in enumerate(cmd):
        if x in options:cmd[i+1]=options[x]
    ledger=dest/'fee-calls.jsonl';env=dict(os.environ,PYTHONPATH=str(original/'vidur-alibabacloud')+':'+str(original)+':'+str(REPO/'scripts/dag_defense'),WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1',COMPOSITE_FEES=str(fees_path),COMPOSITE_LEDGER=str(ledger),COMPOSITE_MODE=mode)
    for k in list(env):
        if k.startswith(('BATCH_FIRST_TOKEN','FORWARD_','FIXED_','SIMAI_SERIAL_')):env.pop(k)
    dump(dest/'command.json',cmd);dump(dest/'identity.json',{'role':mode,'source':str(original),'commit':subprocess.check_output(['git','-C',str(original),'rev-parse','HEAD'],text=True).strip(),'source_diff_sha256':hashlib.sha256(subprocess.check_output(['git','-C',str(original),'diff','HEAD'])).hexdigest(),'bootstrap_sha256':sha(bootstrap),'fees_sha256':sha(fees_path),'receiver_s':receiver_s,'effective_bandwidth_is_fee_coefficient':True,'scheduler_patch':False,'readiness_patch':False})
    with (dest/'process.log').open('w') as log:code=subprocess.run(cmd,cwd=original,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    (dest/'exit').write_text(str(code)+'\n');require(code==0,mode+' exited '+str(code)+'; see '+str(dest/'process.log'))
    pp=list(dest.glob('2026*/request_metrics.csv'));require(len(pp)==1,'metrics ambiguous');return pp[0]

def audit_resources(actual,metrics,out,fees):
    # Actual stream and host worker wave boundaries remain unmodified.
    rr=[json.loads(x) for x in (actual/'reconciled/requests.jsonl').read_text().splitlines()];waves=collections.defaultdict(list)
    for i,r in enumerate(rr):waves[r['wave']].append((i,r))
    actual_waves=[]
    for wave,group in sorted(waves.items()):
        start=min(r['server_arrival_ns'] for i,r in group);end=max(r['server_complete_ns'] for i,r in group)
        prev=max((r['server_complete_ns'] for w,g in waves.items() if w<wave for i,r in g),default=start)
        require(start>=prev,'ACTUAL_CROSS_WAVE_OVERLAP '+str(wave));actual_waves.append({'wave':wave,'arrival_ns':start,'complete_ns':end,'previous_complete_to_arrival_s':(start-prev)/1e9})
    report={'actual_waves':actual_waves,'resource_assumptions':fees.data['resource_assumptions'],'models':{}}
    origin=min(r['server_arrival_ns'] for r in rr)
    for mode,mp in metrics.items():
        mm={int(float(r['Request Id'])):r for r in csvrows(mp)};backlog=[]
        for wave,group in sorted(waves.items()):
            t=(min(r['server_arrival_ns'] for i,r in group)-origin)/1e9
            prior=[i for w,g in waves.items() if w<wave for i,r in g];unfinished=[i for i in prior if float(mm[i]['completed_at'])>t+1e-9]
            backlog.append({'wave':wave,'actual_arrival_s':t,'prior_requests_not_completed':unfinished,'backlog_requests':len(unfinished),'model_previous_completion_lag_s':max([float(mm[i]['completed_at'])-t for i in prior]+[0])})
        entry={'cross_wave_backlog':backlog,'max_prior_backlog_requests':max(x['backlog_requests'] for x in backlog),'classification':'Prediction-induced backlog is reported, not an accuracy threshold. Resource accounting and dependency correctness are checked independently.'}
        if mode=='dag':
            tasks=csvrows(mp.parent/'timeline.csv');totals=collections.defaultdict(lambda:{'tasks':0,'service_s':0.,'resource_wait_s':0.,'max_wait_s':0.})
            for r in tasks:
                for k in ('duration_s','resource_wait_s'):require(float(r[k])>=-1e-12,'negative resource duration')
                require(abs((float(r['start_at_s'])-float(r['ready_at_s']))-float(r['resource_wait_s']))<1e-8,'WAIT_ACCOUNTING '+r['graph_id']+'/'+r['task_id'])
                category='receiver' if r['graph_id'].startswith('pd/') else 'engine_cpu' if r['task_id'].startswith('cpu.') else 'worker' if float(r['duration_s'])>0 else 'zero_excluded'
                t=totals[category];t['tasks']+=1;t['service_s']+=float(r['duration_s']);t['resource_wait_s']+=float(r['resource_wait_s']);t['max_wait_s']=max(t['max_wait_s'],float(r['resource_wait_s']))
            byresource=collections.defaultdict(list)
            for r in tasks:
                if float(r['duration_s'])==0:continue
                for d in json.loads(r['demands']):
                    require(d['amount']==1,'non-unit resource demand');byresource[d['resource_id']].append((float(r['start_at_s']),float(r['end_at_s']),r['graph_id'],r['task_id']))
            for resource,intervals in byresource.items():
                intervals.sort()
                for a,b in zip(intervals,intervals[1:]):require(a[1]<=b[0]+1e-8,'RESOURCE_OVERLAP '+str((resource,a,b)))
            entry.update(resource_wait_by_scope=dict(totals),exclusive_resources_checked=len(byresource),overlapping_resource_intervals=0)
        report['models'][mode]=entry
    dump(out/'backlog-and-resources.json',report);return report

def run(actual,fees_path,out):
    out.mkdir(parents=True,exist_ok=False);fees=CompositeFees(fees_path);n=json.loads((actual/'spec.json').read_text())['input_tokens']
    # Source identity and all existing input/raw records remain pinned.
    base=ROOT/'SimAI-pristine-baseline';dag=ROOT/'SimAI-pristine-predictor-repro';predictor='vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'
    require(not subprocess.check_output(['git','-C',str(base),'diff','HEAD']),'pristine changed')
    require(set(subprocess.check_output(['git','-C',str(dag),'diff','HEAD','--name-only'],text=True).splitlines()).issubset({predictor}),'DAG scheduling/readiness changed')
    frozen={str(p):sha(p) for p in (actual/'inputs.jsonl',actual/'trace.csv',actual/'reconciled/requests.jsonl',fees_path,REPO/'scripts/dag_defense/composite_fee_bootstrap.py')}
    dump(out/'pin.json',{'files':frozen,'pristine_unchanged_reference':str(actual/'prediction-retry-01/baseline-predictions.csv'),'not_formal_validation':True,'roles':['pristine-original','fee-adapted-reference','dag']})
    metrics={m:launch('fee-adapted-reference' if m=='baseline' else 'dag',actual/'trace.csv',out/m,fees_path,n) for m in ('baseline','dag')}
    audit=score_and_audit(out,ROOT,actual/'reconciled/requests.jsonl',metrics)
    resource=audit_resources(actual,metrics,out,fees)
    calls={m:[json.loads(x) for x in (out/m/'fee-calls.jsonl').read_text().splitlines()] for m in ('baseline','dag')}
    for m,cc in calls.items():
        require(len(cc)==len({c['batch_id'] for c in cc}),'duplicate model fee call '+m)
        require(all(c['charged']==['worker','schedule','output'] for c in cc),'duplicate/extra fee scope')
    tasks=csvrows(metrics['dag'].parent/'timeline.csv');graphs=collections.defaultdict(list)
    for r in tasks:graphs[r['graph_id']].append(r)
    transfer=[]
    for name,rr in graphs.items():
        positive=[r for r in rr if float(r['duration_s'])>0]
        if name.startswith('pd/'):
            require(len(positive)==1 and positive[0]['task_id']=='transfer.0','KV composite plus subfee '+name)
            require(abs(float(positive[0]['duration_s'])-fees.receiver(n))<1e-12,'receiver fee parity '+name);transfer.append(name)
        else:
            layer=[r for r in positive if r['task_id'].startswith('layer')]
            require(len(layer)==1 and layer[0]['task_id']=='layer0.attention.compute','duplicate model subfee '+name)
    require(len(transfer)==32,'receiver must be charged once per request')
    require(not audit['dag']['early_events'],'DAG_EARLY_DECODE '+str(audit['dag']['early_events'][:3]))
    require(not audit['task_ledger']['duplicate_keys'] and not audit['task_ledger']['invalid_or_early_tasks'],'duplicate/incomplete/early DAG task')
    require(not audit['paired_batches']['count'] or audit['paired_batches']['max_fee_difference_s']<1e-9,'matched batch fees differ')
    require(all(sha(pathlib.Path(p))==h for p,h in frozen.items()),'source/input changed during replay')
    # Preserve the untouched original as a third prediction column.
    original={r['request_id']:r for r in csvrows(actual/'prediction-retry-01/baseline-predictions.csv')}
    scored=csvrows(out/'scores.csv');full=[]
    for r in scored:
        r={k.replace('baseline','fee_adapted_reference'):v for k,v in r.items()};r['pristine_original_s']=original[r['request_id']]['predicted_e2e_s'];full.append(r)
    writecsv(out/'three-way-scores.csv',full)
    result={'status':'passed','kind':'fee-only_reacceptance_not_validation','actual_requests_reused':32,'new_gpu_e2e_requests':0,'fee_calls':{m:len(c) for m,c in calls.items()},'receiver_charges':len(transfer),'checks':['actual arrivals and token rounds','complete measured-domain lookup','one worker envelope and no old sampler/head/prepare/layer subfees','one receiver composite and no first-token subfee','exclusive resources and waiting arithmetic','cross-wave backlog reported','same paired batch fees','scoring boundaries and all failures retained'],
            'score':json.loads((out/'score-summary.json').read_text()),'baseline_column_role':'fee-adapted-reference; untouched original is separate','resource_assumption_status':'待验证近似','resource_wait_and_backlog_report':'backlog-and-resources.json','not_gates':['small prediction error','no predicted backlog','matching batches','DAG improvement']}
    dump(out/'result.json',result);print(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--actual',type=pathlib.Path,required=True);p.add_argument('--fees',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
    try:run(a.actual,a.fees,a.output)
    except BaseException as e:
        if a.output.exists():dump(a.output/'failure.json',{'status':'failed','assertion':type(e).__name__+': '+str(e)})
        raise
