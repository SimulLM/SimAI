"""Cross-stage finalization: functional closure and explicitly limited references."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shutil
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'vidur-alibabacloud')]
from scripts.dag_finalize.common import read,save,digest,result_path,FinalizationParser,final_exit_status
from scripts.dag_finalize.execution import command,identity,snapshot,wsl_path
from scripts.dag_phase4.main import synthetic_profiles,write_csv,hashes
from scripts.dag_phase8.main import source_hashes,regression
from scripts.dag_phase8.accuracy import evaluate,historical_component_evidence
from scripts.dag_phase8.joint import run_case
from scripts.dag_finalize.deepseek import analyze_directory
from scripts.dag_finalize.controlled import run as controlled_run
from scripts.dag_finalize.dense import prepare as prepare_dense,score as score_dense


def compare_replay(out):
    other=read(out/'linux-replay/acceptance-report.json');current=read(out/'progress.json')
    checks={}
    for name in ('scale-small','joint-backpressure'):
        a=next(r for r in current['joint_cases'] if r['name']==name)
        b=next(r for r in other['joint_cases'] if r['name']==name)
        checks[name]=all(a[k]==b[k] for k in ('request_count','task_count','event_count','graph_count','routing_count')) and abs(a['simulated_final_time_s']-b['simulated_final_time_s'])<=1e-12
    a=read(out/'controlled/mechanism-consistency.json');b=read(out/'linux-replay/controlled/mechanism-consistency.json')
    checks['controlled']=a==b
    checks['deepseek']=read(out/'deepseek-analysis.json')==read(out/'linux-replay/deepseek-analysis.json')
    a=read(out/'dense/simulation-report.json');b=read(out/'linux-replay/dense/simulation-report.json')
    checks['dense']=all(abs(a[k]-b[k])<=1e-12 for k in ('old_mean_relative_error','same_cost_mean_relative_error','revised_mean_relative_error'))
    checks['linux_functional']=other['functional_status']=='passed'
    checks['isolated_environment']=other['environment']['prefix']!=sys.prefix
    result=dict(status='passed' if all(checks.values()) else 'failed',checks=checks,tolerance_s=1e-12,
        confirmation=dict(actor='Codex',kind='automated_cross_environment',user_authorized=True),
        hardware_accuracy_claim=False)
    save(out/'reproduction-report.json',result)
    if result['status']!='passed':raise ValueError('cross-environment replay differs')
    return result


def main(argv=None):
    p=FinalizationParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pytest-basetemp',type=Path)
    p.add_argument('--expected-commit')
    p.add_argument('--environment-evidence',type=Path,required=True)
    p.add_argument('--reference-data',type=Path,required=True)
    p.add_argument('--replay',action='store_true',help='Linux major-results replay; full regression is run by the bridge first')
    a=p.parse_args(argv)
    if a.pytest_basetemp is not None:
        from scripts.dag_finalize.common import validate_pytest_temp
        try:validate_pytest_temp(a.pytest_basetemp)
        except (ValueError,OSError) as exc:p.error(str(exc))
    try:out=result_path(a.output)
    except ValueError as exc:p.error(str(exc))
    if not out.is_relative_to(ROOT/'results/dag/finalize'):p.error('finalization output must be below results/dag/finalize')
    if not re.fullmatch(r'\d{8}-finalize-[a-z0-9-]+-\d{2}(?:-linux)?',out.name):p.error('run_id must be YYYYMMDD-finalize-purpose-NN')
    before=identity()
    if a.expected_commit and before['head']['stdout'].strip()!=a.expected_commit:p.error('unexpected tested commit')
    out.mkdir(parents=True,exist_ok=False)
    os.environ.update(PYTHONPATH=os.pathsep.join((str(ROOT),str(ROOT/'vidur-alibabacloud'))),PYTHONNOUSERSITE='1',PYTHONHASHSEED='0',
        PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',WANDB_MODE='disabled')
    started=time.perf_counter();save(out/'identity-before.json',before)
    report=dict(functional_status='failed',overall_project_acceptance='pending',full_scope_accuracy='blocked',joint_cases=[],
        hardware_accuracy_claim=False,reproduction_status='not_run',scope='linux_replay' if a.replay else 'finalize',environment=before,
        confirmation_policy='Codex automated confirmation authorized by user; additional natural-person signature not required')
    code=1;sources=source_hashes();snapshot(out,sources)
    try:
        env_folder=a.environment_evidence.resolve();environment=read(env_folder/'environment-report.json')
        if environment['status']!='passed':raise ValueError('Linux environment/build not passed')
        save(out/'linux-environment.json',environment)
        reference=out/'reference-data/deepseek';shutil.copytree(a.reference_data.resolve(),reference)
        lock=read(ROOT/'configs/dag/finalize/deepseek-source.json')
        if read(reference/'source.json')!=lock:raise ValueError('DeepSeek lock differs')
        for name,record in lock['files'].items():
            if digest(reference/name)!=record['sha256']:raise ValueError('DeepSeek reference bytes changed: '+name)
        print('Analyzing pinned DeepSeek traces',flush=True)
        parsed=analyze_directory(reference,out/'deepseek-analysis.json')
        if parsed['status']!='passed':raise ValueError('trace parse failed')
        print('Checking 24 controlled workflows',flush=True)
        controlled=controlled_run(out/'controlled',ROOT/'configs/dag/finalize/controlled-cases.json')
        if controlled['status']!='passed':raise ValueError('mechanism reference differs')
        accuracy=evaluate(out/'accuracy',ROOT/'configs/dag/finalize/validation.json')
        if accuracy['status']=='rejected':raise ValueError('official accuracy records rejected')
        report['full_scope_accuracy']=accuracy['status'];historical_component_evidence(out)
        profiles=out/'synthetic-profiles';synthetic_profiles(profiles)
        for tier,count in (('small',1),) if a.replay else (('small',1),('medium',2),('large',4)):
            print('Joint scale',tier,flush=True)
            report['joint_cases'].append(run_case(out,profiles,'scale-'+tier,[(0,8,2)]*count,config_dir=ROOT/'configs/dag/finalize'))
        report['joint_cases'].append(run_case(out,profiles,'joint-backpressure',[(0,8,8)]*4,require_backpressure=True,config_dir=ROOT/'configs/dag/finalize'))
        if not a.replay:
            write_csv(out/'scale-overhead.csv',[{k:r[k] for k in ('name','request_count','task_count','event_count','graph_count','routing_count','wall_time_s','event_queue_peak','peak_rss_bytes','simulated_final_time_s')} for r in report['joint_cases'][:3]])
            from scripts.dag_phase8.overhead import measure
            measure(out)
            print('Full regression with short owned basetemp',flush=True)
            report['regression']=regression(out,a.pytest_basetemp)
            if report['regression']['exit_code']!=0:raise ValueError('complete regression failed')
        dense=out/'dense';calibration=prepare_dense(dense)
        backend_argv=[environment['python'],str(ROOT/'scripts/dag_phase8/simulation_backend.py'),'--inputs',str(dense/'inputs'),
            '--binaries',environment['binaries'],'--output',str(dense/'backend-reference')]
        if os.name=='nt':
            backend_argv=['wsl','-d','Ubuntu-22.04','--',environment['python'],wsl_path(ROOT/'scripts/dag_phase8/simulation_backend.py'),
                '--inputs',wsl_path(dense/'inputs'),'--binaries',environment['binaries'],'--output',wsl_path(dense/'backend-reference')]
        command(out,'fresh-communication-reference',backend_argv)
        print('Dense four-way replay, calibration remains frozen',flush=True)
        dense_report=score_dense(dense,dense/'backend-reference')
        if dense_report['status']!='passed':raise ValueError('controlled dense accuracy gate failed')
        if not a.replay:
            print('Replaying 38 frozen policy scenarios (concurrent; not overhead measurements)',flush=True)
            def policy(family):
                return command(out,'policy-'+family,[sys.executable,ROOT/'scripts/dag_finalize/policy.py','--family',family,'--output',out/('policy-'+family)])
            with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(policy,('original','expanded','holdout')))
        if not all(r['passed'] for r in report['joint_cases']):raise ValueError('joint checks failed')
        report['functional_status']='passed';save(out/'progress.json',report)
        if not a.replay:
            command(out,'source-audit',['wsl','-d','Ubuntu-22.04','--',environment['python'],wsl_path(ROOT/'scripts/dag_finalize/source_audit.py'),
                '--source',wsl_path(ROOT),'--native',environment['checkout'],'--output',wsl_path(out/'source-audit.json')])
            if read(out/'source-audit.json')['status']!='passed':raise ValueError('submodule substantive differences unresolved')
            command(out,'linux-replay',['wsl','-d','Ubuntu-22.04','--',environment['env_a'],wsl_path(ROOT/'scripts/dag_finalize/bridge.py'),
                '--environment',wsl_path(env_folder),'--run',wsl_path(out)])
            report['reproduction_status']=compare_replay(out)['status']
            command(out,'independent-output-audit',[sys.executable,ROOT/'docs/dag/phase8/acceptance/audit_outputs.py','--run',out])
        if source_hashes()!=sources:raise ValueError('tested source changed during execution')
        report['engineering_closeout']='passed'
        code=final_exit_status(report['functional_status'],accuracy['status'],report['reproduction_status'])
        report['overall_project_acceptance']='passed' if code==0 else 'pending_reference_data'
    except Exception as exc:
        report.update(functional_status='failed',error=repr(exc))
        save(out/'operation-error.json',dict(error=repr(exc),traceback=traceback.format_exc()))
    report['exit_code']=code;report['wall_time_s']=time.perf_counter()-started
    save(out/'acceptance-report.json',report);save(out/'identity-after.json',identity())
    save(out/'run-manifest.json',dict(source_sha256=sources,exit_code=code,command=[sys.executable,*sys.argv],
        artifact_sha256=hashes(out,{f for f in out.rglob('*') if f.is_file() and not {'predictor-cache','pytest-tmp','__pycache__'}.intersection(f.relative_to(out).parts)})))
    print('Finalization',report['functional_status'],'exit',code,flush=True)
    return code


if __name__=='__main__':raise SystemExit(main())
