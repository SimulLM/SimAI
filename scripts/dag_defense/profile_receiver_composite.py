"""Independent serial receiver envelope benchmark, never the retained 32 E2E requests."""
import argparse,collections,csv,json,os,pathlib,subprocess,sys,time
from run_preacceptance import stop,require,sha,dump,writecsv

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
    repo=pathlib.Path('/root/autodl-tmp/SimAI-handoff');instrument=out/'instrument';instrument.mkdir()
    source=(repo/'docs/dag_defense/environment/scripts/pd-transport-sync/sitecustomize.py').read_text()
    source=source.replace('  result=old_prepare(self,groups,*args,**kwargs)','  torch.cuda.synchronize();prepared_start=time.monotonic_ns()\n  result=old_prepare(self,groups,*args,**kwargs)\n  object.__setattr__(result,"_composite_prepared_start_ns",prepared_start)')
    source=source.replace("local.step=step;emit('model_step_host_start',step_id=step,groups=groups)","local.step=step;emit('model_step_host_start',step_id=step,groups=groups,prepare_start_ns=model_input._composite_prepared_start_ns)")
    source=source.replace("   emit('model_step_host_return',step_id=step,groups=groups)","   torch.cuda.synchronize()\n   emit('model_step_host_return',step_id=step,groups=groups,after_device_sync=True)")
    require('after_device_sync=True' in source and '_composite_prepared_start_ns' in source,'measurement hook binding failed')
    (instrument/'sitecustomize.py').write_text(source)
    launcher=(repo/'docs/dag_defense/environment/scripts/start-pd-transport-sync.sh').read_text().replace('$root/SimAI-handoff/docs/dag_defense/environment/scripts/pd-transport-sync',str(instrument))
    (out/'launch.sh').write_text(launcher)
    client=(repo/'scripts/dag_defense/serial_kv_install_client.py').read_text().replace('for length in (512,1024,2048):','for length in (1024,2048):')
    (out/'client.py').write_text(client);proc=None
    try:
        require(not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPU not free before receiver microbenchmark')
        with (out/'launcher.log').open('w') as log:proc=subprocess.Popen(['bash',str(out/'launch.sh')],env=dict(os.environ,PD_ROUTE_DIR=str(out/'service')),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        end=time.monotonic()+420
        while not (out/'service/ready').exists():
            require(proc.poll() is None,'receiver service failed');require(time.monotonic()<end,'receiver startup timeout');time.sleep(1)
        with (out/'client.log').open('w') as log:code=subprocess.run([sys.executable,str(out/'client.py'),str(out/'client.jsonl')],stdout=log,stderr=subprocess.STDOUT).returncode
        (out/'client-exit').write_text(str(code));require(code==0,'receiver microbenchmark failed')
    finally:stop(proc)
    router=collections.defaultdict(dict)
    for line in (out/'service/router-events.jsonl').read_text().splitlines():
        r=json.loads(line);require(r['event'] not in router[r['request_id']],'duplicate router event');router[r['request_id']][r['event']]=r
    steps=collections.defaultdict(list)
    for file in (out/'service/events').glob('*.jsonl'):
        for line in file.read_text().splitlines():
            r=json.loads(line)
            if r['role']=='consumer' and r.get('step_id'):
                for g in r.get('groups',[]):steps[(g['request_id'],r['step_id'])].append(r)
    samples=[]
    for line in (out/'client.jsonl').read_text().splitlines():
        c=json.loads(line);ev=router[c['router_id']];rid=ev['decode_mapping']['backend_request_id']+'-0'
        matches=[rr for (request,step),rr in steps.items() if request==rid and any(r['event']=='kv_install_sync_complete' for r in rr)];require(len(matches)==1,'first token identity')
        rr=matches[0]
        def one(event):
            r=[x for x in rr if x['event']==event];require(len(r)==1,'missing/duplicate '+event);return r[0]
        start=one('model_step_host_start');end=one('model_step_host_return');recv=one('recv_kv_caches_and_hidden_states_host_start');install=one('kv_install_sync_complete')
        require(end.get('after_device_sync') is True,'first token final device sync absent')
        ts=[start['prepare_start_ns'],start['timestamp_ns'],recv['timestamp_ns'],install['timestamp_ns'],end['timestamp_ns']];require(ts==sorted(ts),'receiver composite order')
        samples.append({'length':c['length'],'wave':c['wave'],'warmup':c['warmup'],'router_id':c['router_id'],'decode_id':rid,'consumer_prepare_start_ns':ts[0],'receive_start_ns':ts[2],'receive_return_ns':one('recv_kv_caches_and_hidden_states_host_return')['timestamp_ns'],'install_sync_ns':ts[3],'step_return_ns':ts[4],'after_device_sync':True})
    require(len(samples)==80,'expected two lengths x40 independent serial measurements');writecsv(out/'samples.csv',samples)
    dump(out/'result.json',{'status':'passed','kind':'independent_receiver_microbenchmark','samples':80,'warmup_per_length':10,'measured_per_length':30,'boundary':'consumer prepare start after device synchronization through first-token execute completion followed by device synchronization','not_validation':True,'instrument_sha256':sha(instrument/'sitecustomize.py')})
    print((out/'result.json').read_text());return 0
if __name__=='__main__':raise SystemExit(main())
