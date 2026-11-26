"""Freeze the sole accepted composite-fee configuration before any validation."""
import argparse,hashlib,json,pathlib,subprocess,time
from composite_fee import CompositeFees,require,sha
from validation_matrix import validate_matrix
from run_preacceptance import dump
ROOT=pathlib.Path('/root/autodl-tmp');REPO=ROOT/'SimAI-handoff'
CODE=['run_frozen_matrix.py','collect_validation_run.py','reconcile_validation_run.py','export_validation_requests.py','run_preacceptance.py','probe_pd_idle.py','validation_matrix.py','composite_fee.py','composite_fee_bootstrap.py','replay_composite_fees.py']
def source_pin(repo):
    paths=subprocess.check_output(['git','-C',str(repo),'ls-files','-z','vidur-alibabacloud/vidur','schemas']).decode().split('\0')
    return {'path':str(repo),'head':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),'diff_sha256':hashlib.sha256(subprocess.check_output(['git','-C',str(repo),'diff','HEAD'])).hexdigest(),'files':{str(repo/p):sha(repo/p) for p in paths if p.endswith('.py')}}
def main():
    p=argparse.ArgumentParser();p.add_argument('--preaccept',type=pathlib.Path,required=True);p.add_argument('--fees',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,default=ROOT/'dag-handoff/parameter-freeze.json');a=p.parse_args()
    require(not a.output.exists(),'refuse overwriting freeze');result=json.loads((a.preaccept/'result.json').read_text());require(result['status']=='passed','preacceptance failed')
    fee=CompositeFees(a.fees)
    for n in (1024,2048):
        fee.receiver(n)
        for b in range(1,5):
            fee.get('prefill',n,[0]*b,[n]*b)
            for c in range(n+1,n+128):fee.get('decode',n,[c]*b,[1]*b)
    manifest=ROOT/'dag-handoff/validation-input-candidate-20261126/candidate-manifest.json';validate_matrix(json.loads(manifest.read_text()),manifest)
    work=a.output.parent/'frozen-composite-20261126';work.mkdir(exist_ok=False)
    source={'dag':source_pin(ROOT/'SimAI-pristine-predictor-repro'),'handoff_runtime_files':{str(REPO/'scripts/dag_defense'/n):sha(REPO/'scripts/dag_defense'/n) for n in CODE}}
    baseline=source_pin(ROOT/'SimAI-pristine-baseline');require(baseline['head']=='cef83f9ddd96540e3e9f48934f11335d52d54fce','original commit')
    require(not subprocess.check_output(['git','-C',baseline['path'],'diff','HEAD']),'original tracked changes')
    dump(work/'source.json',source);dump(work/'baseline-source.json',baseline)
    paths=[REPO/'docs/dag_defense/environment/scripts'/n for n in ['start-pd-light-events.sh','pd_stream_proxy.py','pd-light-events/sitecustomize.py']]
    dump(work/'service.json',{'files':{str(p):sha(p) for p in paths},'framework':'vLLM 0.8.5 V0','model':'NousResearch/Llama-2-7b-hf','revision':'8efe6c9b93655b934e27bd9981e3ec13e55aee9d','dtype':'float16','tp':1,'deployment':'1P1D','max_seqs':4,'chunked_prefill':False,'prefix_cache':False,'max_model_len':4096,'max_batched_tokens':4096,'eager':True,'generation_config':'vllm (repository generation_config ignored; config PAD=0)','sampling':{'temperature':0,'top_p':1,'seed':0,'ignore_eos':True,'min_tokens':128,'max_tokens':128},'rope_theta':10000,'rope_scaling':None})
    dump(work/'score-rule.json',{'status':'frozen','comparison':'absolute_error_s','tie_tolerance_s':0.,'actual':'router.server_complete_ns-router.server_arrival_ns','prediction':'modelled.completed_at-modelled.arrived_at','arrival':'actual router CLOCK_MONOTONIC arrival','completion_correction_s':0,'primary_reference':'fee-adapted-reference','pristine_reference':'separate unmodified original','aggregation':'first per repetition and load; all failed/not-submitted attempts retained; no accuracy or DAG improvement acceptance threshold','backlog':'report predicted cross-wave backlog; no zero-backlog requirement','resource_assumption_status':'待验证近似'})
    dump(work/'compatibility.json',{'preacceptance':{'path':str(a.preaccept/'result.json'),'sha256':sha(a.preaccept/'result.json')},'resource_audit':{'path':str(a.preaccept/'backlog-and-resources.json'),'sha256':sha(a.preaccept/'backlog-and-resources.json')},'limitations':fee.data['limitations'],'resource_assumptions':fee.data['resource_assumptions'],'stages':fee.data['stages']})
    artifacts={}
    for key,path in {'source':work/'source.json','baseline_source':work/'baseline-source.json','compute_cost':a.fees,'communication_cost':a.fees,'service_configuration':work/'service.json','scoring_rule':work/'score-rule.json','compatibility_evidence':work/'compatibility.json'}.items():artifacts[key]={'path':str(path),'sha256':sha(path)}
    inputs=json.loads(manifest.read_text());all_files={str(manifest):sha(manifest),**{str(manifest.parent/s['path']):s['sha256'] for s in inputs['runs']}}
    for obj in (source['dag'],baseline):all_files.update(obj['files'])
    all_files.update(source['handoff_runtime_files']);all_files.update({str(p):sha(p) for p in paths});all_files.update({r['path']:r['sha256'] for r in fee.data['sources']})
    for p in (ROOT/'models/Llama-2-7b-hf').iterdir():
        if p.is_file() and (p.suffix in ('.json','.model') or p.name=='SHA256SUMS'):all_files[str(p)]=sha(p)
    from freeze_preflight import WEIGHTS,digest
    model_weights={}
    for name,wanted in WEIGHTS.items():
        p=ROOT/'models/Llama-2-7b-hf'/name;require(digest(p)==wanted,'weight hash mismatch '+name);st=p.stat()
        model_weights[str(p)]={'sha256':wanted,'size':st.st_size,'mtime_ns':st.st_mtime_ns,'inode':st.st_ino}
    freeze={'status':'frozen','version':'composite-fees-v1','frozen_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'validation_manifest_sha256':sha(manifest),'artifacts':artifacts,'files':all_files,'source_identities':{'dag':source['dag']['head'],'pristine':baseline['head']},'failure_policy':{'on_failure':'abort_round_and_matrix','retain_all_attempts':True,'restart_before_retry':True,'automatic_reopen':False},'resource_assumption_status':'待验证近似; fixed modelling assumption, not a claim of proven physical GPU occupancy','formal_entry':'scripts/dag_defense/run_frozen_matrix.py','acceptance_not_accuracy':True}
    freeze['model_weights']=model_weights
    dump(a.output,freeze);print(json.dumps({'status':'frozen','path':str(a.output),'files':len(all_files),'sha256':sha(a.output)},indent=2))
if __name__=='__main__':main()
