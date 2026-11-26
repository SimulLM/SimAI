"""The sole candidate/freeze gate. Audits preserved real-arrival replays, never validation totals.

Exit 2 is a concrete scientific/artifact failure, not an accuracy threshold.
No fresh simulator variant is created. Optional --rerun repeats the selected commands verbatim
apart from new output directories, using the same source, input and fees.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
import pathlib
import subprocess
import sys
import statistics
import time

ORIGINAL = 'cef83f9ddd96540e3e9f48934f11335d52d54fce'
DAG = 'b3ce1b661d39510192652457ce1266ebfa417b1b'
PREDICTOR = 'vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'
GROUPS = ('common_cost_and_no_double_charge', 'arrival_completion_boundary',
          'concurrent_readiness_batching', 'freeze_and_preflight')
PROFILE_FLAGS = ('compute_input_file','attention_input_file','send_recv_input_file',
                 'all_reduce_input_file','cpu_overhead_input_file')

def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()

def read(path): return json.loads(pathlib.Path(path).read_text())
def rows(path):
    with pathlib.Path(path).open(newline='') as f: return list(csv.DictReader(f))
def require(condition, message):
    if not condition: raise ValueError(message)
def git(repo, *args):
    return subprocess.check_output(['git','-C',str(repo),*args], text=True).strip()
def option(cmd, name):
    values = [cmd[i+1] for i,x in enumerate(cmd) if x == name]
    require(values and len(set(values)) == 1, 'missing/conflicting option '+name)
    return values[0]

def source_identity(root):
    original = root/'SimAI-pristine-baseline'
    dag = root/'SimAI-pristine-predictor-repro'
    require(git(original,'rev-parse','HEAD') == ORIGINAL, 'pristine commit changed')
    require(not git(original,'diff','HEAD','--name-only'), 'pristine tracked source changed')
    require(not git(original,'ls-files','--others','--exclude-standard','--','*.py'), 'pristine has untracked executable Python')
    require(git(dag,'rev-parse','HEAD') == DAG, 'selected DAG commit changed')
    changed = git(dag,'diff','HEAD','--name-only').splitlines()
    require(set(changed).issubset({PREDICTOR}), 'DAG changes include scheduler/runtime: '+str(changed))
    require(not git(dag,'ls-files','--others','--exclude-standard','--','*.py'), 'DAG has untracked executable Python')
    require(digest(original/PREDICTOR) == digest(dag/PREDICTOR), 'shared predictor differs')
    return {'original_commit':ORIGINAL,'dag_commit':DAG,
            'dag_overlay':'fee-provider replacement only; exact original predictor',
            'predictor_sha256':digest(dag/PREDICTOR),
            'pristine_dirty':False,'source_diff_sha256':hashlib.sha256(git(dag,'diff','HEAD').encode()).hexdigest()}

def audit_replay(folder, trace, mapping, expected_output=64):
    require((folder/'exit').read_text().strip() == '0', 'simulator exit is nonzero: '+str(folder))
    dirs = list(folder.glob('2026*/request_metrics.csv'))
    require(len(dirs) == 1, 'ambiguous/missing metrics: '+str(folder))
    metric_rows = rows(dirs[0])
    metrics = {int(float(r['Request Id'])):r for r in metric_rows}
    require(len(metric_rows) == len(metrics), 'duplicate metrics request ID')
    require(len(metrics) == len(trace) == len(mapping) == 32, 'expected 32 unique request rows')
    require(set(metrics) == set(range(32)), 'simulator ID set differs from arrival map')
    for i,t in enumerate(trace):
        m = metrics[i]
        require(abs(float(m['arrived_at'])-float(t['arrived_at'])) < 1e-9, f'request {i}: not actual-arrival replay')
        require(int(float(m['request_num_prefill_tokens'])) == int(float(t['num_prefill_tokens'])), f'request {i}: prompt clipped')
        require(int(float(m['request_num_decode_tokens'])) == expected_output, f'request {i}: output clipped')
    events = read(dirs[0].parent/'chrome_trace.json')['traceEvents']
    events = sorted((e for e in events if e.get('ph') == 'X' and e.get('pid') in (0,1)
                     and e.get('args',{}).get('request_ids')), key=lambda e:e['ts'])
    history = collections.Counter(); prefill = collections.Counter(); batch = {}; early = []; shapes = collections.Counter()
    for e in events:
        a = e['args']; ids = tuple(sorted(a['request_ids']))
        require(set(ids).issubset(metrics), 'unexpected request ID in batch')
        require(len(ids) == len(a['num_tokens']) == a['batch_size'], 'batch metadata count mismatch')
        require(math.isfinite(e['dur']) and e['dur'] >= 0, 'negative/nonfinite model fee')
        require(all(int(n) == (512 if e['pid'] == 0 else 1) for n in a['num_tokens']), 'unexpected per-round token amount')
        for rid in ids:
            require(e['ts']/1e6+1e-9 >= float(metrics[rid]['arrived_at']), 'batch precedes real request arrival')
        require(len(ids) == len(set(ids)), 'duplicate member in batch '+str(a['batch_id']))
        key = (e['pid'],ids,tuple((i,history[i]) for i in ids),tuple(sorted(zip(a['request_ids'],a['num_tokens']))))
        require(key not in batch, 'duplicate model batch key '+str(key))
        batch[key] = e
        if e['pid'] == 0:
            prefill.update(ids)
            shapes[('prefill',sum(a['num_tokens']),0)] += 1
        else:
            contexts = [512+1+history[rid] for rid in ids]
            shapes[('decode',len(ids),int(sum(contexts)/len(contexts)))] += 1
            for rid in ids:
                ready = float(metrics[rid]['decode_arrived_at']); start = e['ts']/1e6
                if start+1e-9 < ready:
                    early.append({'request_id':rid,'batch_id':a['batch_id'],
                                  'start_s':start,'modeled_ready_s':ready})
            history.update(ids)
    require(set(history) == set(range(32)) and all(history[i] == expected_output-1 for i in metrics), 'missing/duplicate Decode round')
    require(set(prefill) == set(range(32)) and all(prefill[i] == 1 for i in metrics), 'missing/duplicate Prefill round')
    return {'directory':str(folder),'batches':len(batch),'early':early,
            'input_tokens':512,'output_tokens':expected_output,
            'reachable_observed_shapes':[{'phase':k[0],'tokens_or_batch':k[1],'mean_context':k[2],'count':v} for k,v in sorted(shapes.items())],
            'metrics_sha256':digest(dirs[0]),'chrome_trace_sha256':digest(dirs[0].parent/'chrome_trace.json')}, batch, dirs[0].parent

def audit_tasks(directory):
    task_rows = rows(directory/'timeline.csv'); keys = [(r['graph_id'],r['task_id']) for r in task_rows]
    require(len(keys) == len(set(keys)), 'duplicate graph/task charged')
    graphs = collections.defaultdict(list)
    for r in task_rows:
        duration = float(r['duration_s'])
        require(math.isfinite(duration) and duration >= 0, 'negative/nonfinite task cost')
        require(r['state'] == 'COMPLETED' and int(r['completion_count']) == 1, 'task incomplete or completed twice')
        require(float(r['start_at_s'])+1e-9 >= float(r['ready_at_s']), 'task executed before DAG predecessors')
        graphs[r['graph_id']].append(r)
    for name,rr in graphs.items():
        task_ids = {r['task_id'] for r in rr}
        require(not (any('whole_forward' in x for x in task_ids) and any(x.startswith('layer') for x in task_ids)), 'whole forward and layer costs both charged: '+name)
    return graphs

def real_arrival_evidence(root, case):
    base = root/'dag-handoff/runs/pd-pull-calibration-replay-20261126'/case
    trace = rows(base/'trace.csv'); mapping = read(base/'request-map.json')
    clock = root/'SimAI-handoff/docs/dag_defense/environment/diagnostics/calibration-client-router-boundaries-20261126/requests.csv'
    clocks = {r['router_id']:r for r in rows(clock)}
    clients = {r['router_id']:r for r in read(root/'dag-handoff/runs/calibration-merged-20261126/requests.json')}
    require(len(mapping) == len({r['router_id'] for r in mapping}) == 32, 'duplicate real request map')
    require([r['simulator_request_id'] for r in mapping] == list(range(32)), 'request mapping order')
    origin = min(r['server_arrival_ns'] for r in mapping)
    for i,(r,t) in enumerate(zip(mapping,trace)):
        c = clocks[r['router_id']]; raw = clients[r['router_id']]
        require(int(c['server_arrival_ns']) == r['server_arrival_ns'] and int(c['server_complete_ns']) == r['server_complete_ns'], f'{case}/{i}: server clock source mismatch')
        require(raw['input_sha256'] == r['input_sha256'], f'{case}/{i}: real input hash mismatch')
        require(raw['status'] == 200 and raw['usage']['prompt_tokens'] == 512 and raw['usage']['completion_tokens'] == 64, f'{case}/{i}: actual token/status mismatch')
        require(abs(float(t['arrived_at'])-(r['server_arrival_ns']-origin)/1e9) < 1e-9, f'{case}/{i}: trace arrival differs from server')
        require(r['server_complete_ns'] > r['server_arrival_ns'], f'{case}/{i}: reversed real endpoints')
    return trace,mapping,{'requests':32,'trace_sha256':digest(base/'trace.csv'),
                          'raw_mapping_sha256':digest(base/'request-map.json'),'clock_csv_sha256':digest(clock)}

def replay_pair(root, case, output, rerun=False):
    trace,mapping,real = real_arrival_evidence(root,case)
    templates = root/'dag-handoff/runs/pristine-real-arrival-20261126'/case
    modes = {}; batches = {}; dirs = {}; commands = {}
    repos = {'baseline':root/'SimAI-pristine-baseline','dag':root/'SimAI-pristine-predictor-repro'}
    for mode in ('baseline','dag'):
        folder = templates/mode; cmd = read(folder/'command.json')
        require(cmd[1:3] == ['-m','vidur.main'], 'comparison may not use a diagnostic bootstrap')
        expected_trace = root/'dag-handoff/runs/pd-pull-calibration-replay-20261126'/case/'trace.csv'
        require(pathlib.Path(option(cmd,'--trace_request_generator_config_trace_file')) == expected_trace, 'wrong real-arrival input')
        require(not (folder/'first-token.jsonl').exists(), 'primary replay contains added first-token stage')
        if rerun:
            dest = output/'replays'/case/mode; dest.mkdir(parents=True,exist_ok=False)
            for flag in ('--metrics_config_output_dir','--metrics_config_cache_dir','--random_forrest_execution_time_predictor_config_simai_dir'):
                for i,x in enumerate(cmd):
                    if x == flag: cmd[i+1] = str(dest/'cache') if flag.endswith('cache_dir') else str(dest)
            (dest/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
            env = dict(os.environ,PYTHONPATH=str(repos[mode]/'vidur-alibabacloud')+':'+str(repos[mode]),
                       WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
            for key in list(env):
                if key.startswith(('BATCH_FIRST_TOKEN','FIXED_','FORWARD_','SIMAI_SERIAL_')): env.pop(key)
            with (dest/'process.log').open('w') as log:
                code = subprocess.run(cmd,cwd=repos[mode],env=env,stdout=log,stderr=subprocess.STDOUT).returncode
            (dest/'exit').write_text(str(code)+'\n'); folder = dest
        result,batch,directory = audit_replay(folder,trace,mapping)
        modes[mode] = result; batches[mode] = batch; dirs[mode] = directory; commands[mode] = cmd
    for suffix in PROFILE_FLAGS:
        flag = '--random_forrest_execution_time_predictor_config_'+suffix
        x,y = (pathlib.Path(option(commands[m],flag)) for m in ('baseline','dag'))
        require(digest(x) == digest(y), 'different profile file: '+suffix)
    require(option(commands['baseline'],'--replica_config_pd_p2p_comm_bandwidth') == option(commands['dag'],'--replica_config_pd_p2p_comm_bandwidth'), 'transfer bandwidth differs')
    graphs = audit_tasks(dirs['dag']); common = batches['baseline'].keys() & batches['dag'].keys()
    differences = []
    for key in common:
        b = batches['dag'][key]; prefix = f"replica{b['pid']}/stage0/batch{b['args']['batch_id']}/"
        selected = [g for g in graphs if g.startswith(prefix)]
        require(len(selected) == 1, 'model batch has ambiguous graph')
        differences.append(abs(sum(float(t['duration_s']) for t in graphs[selected[0]])-batches['baseline'][key]['dur']/1e6))
    require(not differences or max(differences) < 1e-9, 'matched model-batch fees differ')
    (output/(case+'-replay.json')).write_text(json.dumps(modes,indent=2)+'\n')
    require(not modes['dag']['early'], 'DAG Decode before modeled KV arrival: '+str(modes['dag']['early'][:2]))
    return {'real':real,'modes':modes,'paired':len(common),
            'paired_fraction_baseline':len(common)/len(batches['baseline']),
            'paired_fraction_dag':len(common)/len(batches['dag']),
            'max_matched_fee_difference_s':max(differences,default=0),
            'original_early_events_are_observations_not_a_gate':True,
            'task_duplicates':0,'source':'fresh same-command replay' if rerun else 'preserved completed replay; hashes revalidated'}


def coverage(profile):
    """Check the selected predictor's measured feature domain, not another adapter's bins.

    The original uses a regressor, not exact shape lookup. Bounding intervals permit
    interpolation; they do not establish accuracy or physical mixed-context coverage.
    """
    compute=rows(profile/'compute.csv'); attention=rows(profile/'attention.csv'); cpu=rows(profile/'cpu.csv')
    gaps=[]; tested=0
    def bounded(values, target, key):
        nonlocal tested
        tested+=1
        values=[float(x) for x in values]
        if not values or not min(values)<=target<=max(values):
            gaps.append({'key':key,'wanted':target,'measured_bounds':[min(values),max(values)] if values else None})
    # Superset of reachable shapes in 1P1D cap=4, unchunked Prefill, TP1.
    # Batch 3 is reachable even though offered concurrency is only 1,2,4.
    for n in (512,1024,2048):
        bounded([r['num_tokens'] for r in compute if r['phase']=='prefill'],n,['compute','prefill',n])
        bounded([r['prefill_chunk_size'] for r in attention if float(r['kv_cache_size'])==0],n,['attention','prefill',n])
        for b in range(1,5):
            bounded([r['num_tokens'] for r in compute if r['phase']=='decode'],b,['compute','decode',b])
            bounded([r['batch_size'] for r in cpu],b,['cpu',b])
            aa=[r for r in attention if int(r['batch_size'])==b and float(r['prefill_chunk_size'])==0]
            for ctx in (n,n+(64 if n==512 else 128)):
                bounded([r['kv_cache_size'] for r in aa],ctx,['attention','decode',b,ctx])
    # All loaded numerical targets must be finite and nonnegative.
    for name,rr in [('compute',compute),('attention',attention),('cpu',cpu)]:
        for i,r in enumerate(rr):
            for k,v in r.items():
                if k.startswith('time_stats.') or k.endswith(('_median','_mean')):
                    require(math.isfinite(float(v)) and float(v)>=0,f'{name} row {i}: invalid fee {k}')
    return {'checked_bounds':tested,'gaps':gaps,'profile_sha256':{p.name:digest(p) for p in profile.glob('*.csv')},
            'limitations':['Original compute and CPU regressors ignore phase/context features.',
                           'Attention uses average context and batch, not per-request context vector.',
                           'Domain coverage is not physical fee ownership or measured accuracy.']}


def fee_contract(contract, root):
    """Reject missing scopes and overlapping ownership; never accept a closed status flag.

    Each resolved scope must bind measured source, executable mapping and exclusive
    physical components. Pending scopes are emitted verbatim as actionable gaps.
    Runtime task uniqueness and matched-batch parity are checked independently above.
    """
    required={'consumer_first_token','producer_output_head','kv_receive_install','cpu_sampler_overlap'}
    entries=contract['scopes']; require({e['id'] for e in entries}==required,'fee scope inventory changed')
    require(len(entries)==len(required),'duplicate fee scope')
    gaps=[]; owned={}
    for e in entries:
        if e['resolution']!='mapped':
            gaps.append({'scope':e['id'],'missing':e['missing'],'evidence':e['evidence'],'next_action':e['next_action']})
            continue
        require(e['physical_components'] and e['mappings'],'empty fee scope mapping '+e['id'])
        for component in e['physical_components']:
            require(component not in owned,'physical work charged twice: '+component)
            owned[component]=e['id']
        for mode in ('baseline','dag'):
            m=e['mappings'][mode]
            for artifact in ('measurement','implementation'):
                p=pathlib.Path(m[artifact]['path'])
                require(p.is_absolute() and p.is_relative_to(root),'fee artifact outside data root')
                require(digest(p)==m[artifact]['sha256'],'fee mapping source changed '+e['id'])
            require(m['shape_rule'] and m['charge_selector'] and m['excluded_overlap'],'incomplete fee ownership '+e['id'])
    return {'gaps':gaps,'exclusive_components':owned}


def timing_contract(repo):
    contract=read(repo/'docs/dag_defense/freeze_gate/score-boundary.json')
    require(contract['actual']=='router.server_complete_ns-router.server_arrival_ns','actual score boundary changed')
    require(contract['prediction']=='simulator.completed_at-simulator.arrived_at','prediction score boundary changed')
    require(contract['arrival_replay']=='router.server_arrival_ns','scheduled/client arrival used for replay')
    require(contract['residual_policy']=='report_unmodeled_no_fitted_correction','unapproved timing correction')
    require(contract['additive_correction_s']==0,'tail compensation is not allowed')
    raw=repo/contract['tail_evidence']; rr=rows(raw)
    require(rr and len({r['router_id'] for r in rr})==len(rr),'missing/duplicate tail requests')
    values=[]
    for r in rr:
        times=[int(r[k]) for k in ('first_step_return_ns','first_router_observed_ns','last_step_return_ns','final_choice_ns','server_complete_ns')]
        require(times==sorted(times),'reversed raw timing event '+r['router_id'])
        values.append((times[-1]-times[-3])/1e6)
    return {'contract':contract,'raw_sha256':digest(raw),'tail_samples':len(values),
            'host_last_step_return_to_router_complete_ms':{'min':min(values),'median':statistics.median(values),'max':max(values)},
            'limitations':['Host step return is not a CUDA-completion timestamp.',
                           '20 retained calibration samples do not establish a validation tail distribution.',
                           'Model-end prediction is scored against router completion; residual stays in prediction error.']}


def failure_policy(repo):
    f=read(repo/'docs/dag_defense/freeze_gate/failure-policy.json')
    require(f['on_failure']=='abort_round' and f['retain_all_attempts'] and f['restart_before_retry'],'failure policy must retain/abort/restart')
    require(not f['automatic_reopen_after_failure'],'automatic reopen disallowed')
    # Verify the existing collector/supervisor implementation, without adding a new reliability layer.
    collector=(repo/'scripts/dag_defense/collect_validation_run.py').read_text()
    supervisor=(repo/'scripts/dag_defense/supervise_validation.py').read_text()
    for snippet in ("if any(x['status']!='success'", "'status':'not_submitted'", "'restart-required.jsonl'"):
        require(snippet in collector,'collector abort/retention implementation missing '+snippet)
    require('finally:' in supervisor and 'stop_group(service' in supervisor,'service cleanup missing')
    return {'policy':f,'collector_sha256':digest(repo/'scripts/dag_defense/collect_validation_run.py'),
            'supervisor_sha256':digest(repo/'scripts/dag_defense/supervise_validation.py'),
            'integration_pending':'Formal per-round idle CLI must be executable before freeze; policy alone does not certify idle.'}


def frozen_artifacts(path, candidate_passed):
    require(candidate_passed,'candidate validity assertions failed; frozen-validation cannot proceed')
    obj=read(path); require(obj['status']=='frozen','freeze status is not frozen')
    artifacts=obj['artifacts']
    for key in ('source','baseline_source','compute_cost','communication_cost','service_configuration','scoring_rule','compatibility_evidence'):
        a=artifacts[key]; require(digest(a['path'])==a['sha256'],'frozen artifact changed: '+key)
    require(artifacts,'empty freeze')
    return {'freeze_sha256':digest(path),'artifacts':len(artifacts)}


def run(repo,root,out,rerun=True,skip_weights=False,phase='candidate'):
    out.mkdir(parents=True,exist_ok=False); checks=[]
    def check(name,group,fn):
        try:
            detail=fn(); checks.append({'assertion':name,'group':group,'status':'passed','evidence':detail}); return detail
        except Exception as e:
            checks.append({'assertion':name,'group':group,'status':'failed','failure':type(e).__name__+': '+str(e)})
        finally:
            (out/'progress.json').write_text(json.dumps(checks,indent=2)+'\n')
    identity=check('source_roles_and_identity',GROUPS[3],lambda:source_identity(root))
    def static():
        from validation_matrix import validate_matrix
        manifest=root/'dag-handoff/validation-input-candidate-20261126/candidate-manifest.json'
        validate_matrix(read(manifest),manifest)
        if not skip_weights:
            from freeze_preflight import WEIGHTS
            for name,wanted in WEIGHTS.items():
                require(digest(root/'models/Llama-2-7b-hf'/name)==wanted,'model shard hash '+name)
        return {'manifest_sha256':digest(manifest),'planned_runs':30,'planned_requests':960,'weights_checked':not skip_weights}
    check('inputs_and_model',GROUPS[3],static)
    for case in ('serial-0','concurrent-0'):
        def pair(c=case):
            require(identity is not None,'source identity failed; do not execute unidentified code')
            return replay_pair(root,c,out,rerun)
        check('real_arrival_tokens_tasks_readiness_'+case,GROUPS[2],pair)
    check('source_unchanged_after_replay',GROUPS[3],lambda:require(source_identity(root)==identity,'source changed during replay'))
    def shapes():
        profile=root/'dag-handoff/runs/pd-pull-calibration-replay-20261126/profile'
        result=coverage(profile); (out/'reachable-fee-gaps.json').write_text(json.dumps(result,indent=2)+'\n')
        require(not result['gaps'],'REACHABLE_FEE_DOMAIN_GAPS: '+json.dumps(result['gaps'][:6])+'; full list in reachable-fee-gaps.json')
        return result
    check('reachable_common_profile_domain',GROUPS[0],shapes)
    def costs():
        result=fee_contract(read(repo/'docs/dag_defense/freeze_gate/fee-contract.json'),root)
        (out/'fee-ownership-gaps.json').write_text(json.dumps(result,indent=2)+'\n')
        require(not result['gaps'],'UNRESOLVED_FEE_OWNERSHIP: '+json.dumps(result['gaps']))
        return result
    check('physical_fee_ownership_and_nonoverlap',GROUPS[0],costs)
    check('score_endpoint_contract',GROUPS[1],lambda:timing_contract(repo))
    check('failure_retention',GROUPS[3],lambda:failure_policy(repo))
    def operational():
        contract=read(repo/'docs/dag_defense/freeze_gate/formal-entry.json')
        require(contract['primary']==['pristine_original','dag_original_fee_provider'],'unregistered comparison roles')
        require(contract['entrypoint']=='scripts/dag_defense/formal_preflight.py','multiple formal preflight entrypoints')
        # A declared launch command alone cannot pass: inspect the currently selected CLI.
        source=(repo/contract['round_supervisor']).read_text()
        require('Do not start paid GPU processes until the missing formal readiness gate exists.' not in source,
                'ROUND_ENTRY_NOT_CONNECTED: supervise_validation.main unconditionally exits 2; no round can run after freeze. Next action: wire the conservative fresh-service/idle/collect/stop procedure into this existing CLI, without auto-reopen.')
        return {'contract_sha256':digest(repo/'docs/dag_defense/freeze_gate/formal-entry.json')}
    check('conservative_round_entry',GROUPS[3],operational)
    def eligible():
        require(rerun and not skip_weights,'cached/skip-weight mode cannot authorize freeze')
        return {'fresh_replay':True,'full_model_hashes':True}
    check('acceptance_mode',GROUPS[3],eligible)
    candidate_passed=all(x['status']=='passed' for x in checks)
    if phase=='frozen-validation':
        check('frozen_artifact_hashes',GROUPS[3],lambda:frozen_artifacts(root/'dag-handoff/parameter-freeze.json',candidate_passed))
    failed=[x for x in checks if x['status']=='failed']
    result={'schema_version':2,'phase':phase,'status':'blocked' if failed else 'passed',
            'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'formal_validation_authorized':phase=='frozen-validation' and not failed,
            'formal_collection_started_by_this_command':False,
            'primary_roles':{'pristine_original':'unchanged original reference',
                             'dag_original_fee_provider':'DAG with original fee predictor replacement only; scheduler and readiness unchanged'},
            'diagnostic_variants_excluded_from_primary':['readiness-only repair','fixed groups','dynamic first token','whole-forward fees'],
            'checks':checks,'gate_failures':{g:[x['assertion'] for x in failed if x['group']==g] for g in GROUPS},
            'not_gates':['small prediction error','identical batches','DAG improvement'],
            'next':'Freeze exact sources, fees, service and scoring only after candidate passes; frozen-validation rechecks hashes before a round.'}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.name+'\n' for p in sorted(out.glob('*.json'))))
    print(json.dumps({'status':result['status'],'phase':phase,'output':str(out),'failures':result['gate_failures']},indent=2),flush=True)
    return 2 if failed else 0


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/SimAI-handoff'))
    ap.add_argument('--data-root',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp'))
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--phase',choices=('candidate','frozen-validation'),default='candidate')
    ap.add_argument('--use-preserved-replays',action='store_true',help='debug only: audit retained replay outputs; cannot authorize freeze')
    ap.add_argument('--skip-weights',action='store_true',help='debug only; cannot authorize freeze')
    a=ap.parse_args(); return run(a.repo,a.data_root,a.output,not a.use_preserved_replays,a.skip_weights,a.phase)
if __name__=='__main__':sys.exit(main())
