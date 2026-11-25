"""Restore an exact source overlay to a native checkout and replay without GPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def write(p,value):p.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--environment',type=Path,required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    run=a.run.resolve();report=json.loads((a.environment/'environment-report.json').read_text())
    native=Path(report['checkout']).resolve();allowed=(Path.home()/'.cache/simai-finalize').resolve()
    if not native.is_relative_to(allowed) or not (native/'.git').is_dir():raise ValueError('invalid native checkout')
    head=subprocess.check_output(['git','-C',str(native),'rev-parse','HEAD'],text=True).strip()
    expected=json.loads((run/'identity-before.json').read_text(encoding='utf-8'))['head']['stdout'].strip()
    if head!=expected or head!=report['head']:raise ValueError('native/base commit mismatch')
    manifest=json.loads((run/'runtime-source.json').read_text(encoding='utf-8'))
    if hashlib.sha256((run/'runtime-source.zip').read_bytes()).hexdigest()!=manifest['archive_sha256']:raise ValueError('snapshot changed')
    with zipfile.ZipFile(run/'runtime-source.zip') as z:
        for name,h in manifest['source_sha256'].items():
            target=(native/name).resolve()
            if not target.is_relative_to(native):raise ValueError('snapshot escapes native checkout')
            payload=z.read(name)
            if hashlib.sha256(payload).hexdigest()!=h:raise ValueError('snapshot checksum mismatch: '+name)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    target=native/'results/dag/finalize'/(run.name+'-linux')
    regression=native/'results/dag/finalize'/(run.name+'-linux-regression');regression.mkdir(parents=True,exist_ok=False)
    (native/'.cache/p8t').mkdir(parents=True,exist_ok=True)
    temporary=tempfile.mkdtemp(dir=native/'.cache/p8t')
    env=dict(os.environ,PYTHONPATH=str(native)+':'+str(native/'vidur-alibabacloud'),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
        PYTHONHASHSEED='0',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',WANDB_MODE='disabled')
    argv=[report['env_a'],'-m','pytest','tests/test_dag_phase1_contracts.py','tests/dag','-q','-p','no:cacheprovider',
        '--basetemp',temporary,'--junitxml',str(regression/'pytest.xml')]
    write(regression/'command.json',argv)
    with (regression/'pytest.log').open('wb') as log:code=subprocess.run(argv,cwd=native,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    write(regression/'process-result.json',dict(exit_code=code))
    shutil.copytree(regression,run/'linux-regression')
    if code:raise RuntimeError('clean Linux regression failed')
    argv=[report['env_b'],str(native/'scripts/dag_finalize/main.py'),'--output',str(target),'--replay',
        '--reference-data',str(run/'reference-data/deepseek'),'--environment-evidence',str(a.environment)]
    write(run/'linux-replay-command.json',argv)
    with (run/'linux-replay.log').open('wb') as log:code=subprocess.run(argv,cwd=native,env=env,stdout=log,stderr=subprocess.STDOUT).returncode
    if target.exists():shutil.copytree(target,run/'linux-replay',ignore=shutil.ignore_patterns('predictor-cache','pytest-tmp','__pycache__'))
    write(run/'linux-process-result.json',dict(exit_code=code,native_output=str(target),regression_exit_code=0))
    if code not in (0,2):raise RuntimeError('clean Linux replay failed')


if __name__=='__main__':main()
