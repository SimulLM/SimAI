"""Run the frozen 30-round matrix; abort conservatively and retain every attempt."""
import argparse,asyncio,json,os,pathlib,subprocess,time
from collect_validation_run import preflight,run_case
from run_preacceptance import stop,idle,worker_audit,dump,sha,require,writecsv
from reconcile_validation_run import reconcile
from export_validation_requests import export
ROOT=pathlib.Path('/root/autodl-tmp');REPO=ROOT/'SimAI-handoff'

def verify(freeze,weights=False):
    obj=json.loads(freeze.read_text());require(obj['status']=='frozen','not frozen')
    for name,a in obj['artifacts'].items():require(sha(a['path'])==a['sha256'],'frozen artifact changed '+name)
    for name,digest in obj['files'].items():require(sha(name)==digest,'frozen file changed '+name)
    from freeze_preflight import digest as streamed_digest
    for name,entry in obj['model_weights'].items():
        p=pathlib.Path(name);st=p.stat()
        require((st.st_size,st.st_mtime_ns,st.st_ino)==(entry['size'],entry['mtime_ns'],entry['inode']),'weight file identity changed '+name)
        if weights:require(streamed_digest(p)==entry['sha256'],'weight hash changed '+name)
    return obj

def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=pathlib.Path,default=ROOT/'dag-handoff/parameter-freeze.json');p.add_argument('--manifest',type=pathlib.Path,default=ROOT/'dag-handoff/validation-input-candidate-20261126/candidate-manifest.json');p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--collect-only',action='store_true');a=p.parse_args()
    obj=verify(a.freeze,weights=True);matrix=json.loads(a.manifest.read_text());out=a.output;out.mkdir(parents=True,exist_ok=False);proc=None
    ledger={'status':'starting','freeze_sha256':sha(a.freeze),'formal':True,'planned_rounds':30,'planned_requests':960,'completed_rounds':0,'completed_requests':0,'attempts':[]};dump(out/'matrix-status.json',ledger)
    try:
        require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU in use before formal service')
        launcher=REPO/'docs/dag_defense/environment/scripts/start-pd-light-events.sh'
        with (out/'launcher.log').open('w') as log:proc=subprocess.Popen(['bash',str(launcher)],env=dict(os.environ,PD_ROUTE_DIR=str(out/'service')),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+420
        while not (out/'service/ready').exists():
            require(proc.poll() is None,'service failed to start');require(time.monotonic()<deadline,'startup timeout');time.sleep(1)
        for spec in matrix['runs']:
            verify(a.freeze);_,_,spec,rows=preflight(a.freeze,a.manifest,spec['run_id']);rid=spec['run_id'];dest=out/rid;dest.mkdir()
            dump(dest/'spec.json',spec);(dest/'inputs.jsonl').write_bytes((a.manifest.parent/spec['path']).read_bytes())
            entry={'run_id':rid,'input_tokens':spec['input_tokens'],'concurrency':spec['concurrency'],'repeat':spec['repeat'],'status':'warmup','attempt':1};ledger['attempts'].append(entry);dump(out/'matrix-status.json',ledger)
            warm=[dict(r,run_id=rid+'-warm',request_id=rid+'-warm'+str(i),input_id=rid+'-wi'+str(i),wave=0) for i,r in enumerate(rows[:4])]
            # Explicit one four-request warmup wave independent of measured requests.
            wspec=dict(spec,run_id=rid+'-warm',concurrency=4)
            result=asyncio.run(run_case(wspec,warm,dest/'warmup','http://127.0.0.1:18300/v1/completions',str(ROOT/'models/Llama-2-7b-hf'),180));require(result['failure'] is None,'warmup failed '+rid)
            idle(out/'service',dest);require(proc.poll() is None,'service failed before collection')
            entry['status']='collecting';dump(out/'matrix-status.json',ledger)
            result=asyncio.run(run_case(spec,rows,dest/'client','http://127.0.0.1:18300/v1/completions',str(ROOT/'models/Llama-2-7b-hf'),180));require(result['failure'] is None,'collection failed '+rid)
            clients=[json.loads(x) for x in (dest/'client/client-events.jsonl').read_text().splitlines()];routerids={r['router_id'] for r in clients}
            # Retain complete shared service logs and a round-specific raw event view.
            router=[json.loads(x) for x in (out/'service/router-events.jsonl').read_text().splitlines()]
            selected=[r for r in router if r['request_id'] in routerids];(dest/'measured-router-events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in selected))
            rec=reconcile(dest/'inputs.jsonl',dest/'client/client-events.jsonl',dest/'measured-router-events.jsonl',dest/'reconciled');require(rec['status']=='complete','reconciliation failed '+rid)
            export(dest/'reconciled/requests.jsonl',dest/'client/run-spec.json',dest/'actual')
            (dest/'service').symlink_to(out/'service',target_is_directory=True)
            worker_audit(dest,dest/'reconciled/requests.jsonl')
            rr=[json.loads(x) for x in (dest/'reconciled/requests.jsonl').read_text().splitlines()];origin=min(r['server_arrival_ns'] for r in rr)
            writecsv(dest/'trace.csv',[{'arrived_at':(r['server_arrival_ns']-origin)/1e9,'num_prefill_tokens':spec['input_tokens'],'num_decode_tokens':128} for r in rr])
            # Idle after each round is evidence, not inferred from low GPU utilization.
            after=dest/'postrun-idle';after.mkdir();idle(out/'service',after)
            entry['status']='data_complete';entry['requests']=32;ledger['completed_rounds']+=1;ledger['completed_requests']+=32;dump(out/'matrix-status.json',ledger)
            print(json.dumps({'completed_rounds':ledger['completed_rounds'],'run_id':rid,'requests':32}),flush=True)
        ledger['status']='real_collection_complete';dump(out/'matrix-status.json',ledger)
    except BaseException as e:
        ledger['status']='aborted_restart_required';ledger['error']=type(e).__name__+': '+str(e)
        if ledger['attempts']:ledger['attempts'][-1]['status']='failed_retained'
        dump(out/'matrix-status.json',ledger);raise
    finally:
        stop(proc);dump(out/'gpu-after.json',{'query':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,memory.used,utilization.gpu','--format=csv'],text=True)});dump(out/'matrix-status.json',ledger)
    if not a.collect_only:
        ledger['status']='cpu_prediction_replay';dump(out/'matrix-status.json',ledger)
        for entry in ledger['attempts']:
            verify(a.freeze);dest=out/entry['run_id']
            cmd=[sys.executable,str(REPO/'scripts/dag_defense/replay_composite_fees.py'),'--actual',str(dest),'--fees',obj['artifacts']['compute_cost']['path'],'--output',str(dest/'predictions')]
            # Simulation uses the CPU environment, even though collection runs under vLLM.
            cmd[0]=str(ROOT/'venvs/simai-simulator/bin/python')
            with (dest/'replay.log').open('w') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
            entry['prediction_exit']=code;dump(out/'matrix-status.json',ledger)
            require(code==0,'formal replay failed '+entry['run_id'])
        ledger['status']='complete';dump(out/'matrix-status.json',ledger)
    return 0
if __name__=='__main__':
    import sys
    raise SystemExit(main())
