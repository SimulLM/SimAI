"""Logged subprocesses and exact runtime snapshots for finalization."""
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

from scripts.dag_finalize.common import ROOT,digest,save,read


def command(output,name,argv,*,accepted=(0,),env=None,cwd=None):
    folder=Path(output)/'operations'/name;folder.mkdir(parents=True,exist_ok=False)
    save(folder/'command.json',dict(argv=list(map(str,argv)),cwd=str(cwd or ROOT),environment_overrides=env or {}))
    child=dict(os.environ);child.pop('PYTHONPATH',None)
    child.update(PYTHONPATH=os.pathsep.join((str(ROOT),str(ROOT/'vidur-alibabacloud'))),PYTHONNOUSERSITE='1',
        PYTHONDONTWRITEBYTECODE='1',PYTHONHASHSEED='0',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',WANDB_MODE='disabled')
    child.update(env or {})
    started=time.perf_counter();print('START',name,flush=True)
    with (folder/'process.log').open('wb') as log:
        code=subprocess.run(list(map(str,argv)),cwd=cwd or ROOT,env=child,stdout=log,stderr=subprocess.STDOUT).returncode
    result=dict(exit_code=code,wall_time_s=time.perf_counter()-started,accepted=list(accepted))
    save(folder/'process-result.json',result);print('END',name,code,flush=True)
    if code not in accepted:raise RuntimeError(name+' failed: '+str(code))
    return result


def identity():
    result={}
    for name,args in (('head',['rev-parse','HEAD']),('branch',['branch','--show-current']),
        ('status',['status','--short','--ignore-submodules=all']),('diff',['diff','--binary','--ignore-submodules=all','HEAD'])):
        p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,encoding='utf-8',errors='replace')
        result[name]=dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr)
    result.update(python=sys.version,prefix=sys.prefix,executable=sys.executable,
        dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions()})
    return result


def snapshot(output,sources):
    archive=Path(output)/'runtime-source.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for name,h in sorted(sources.items()):
            path=ROOT/name
            if digest(path)!=h:raise ValueError('source changed during snapshot: '+name)
            z.write(path,name)
    save(Path(output)/'runtime-source.json',dict(source_sha256=sources,archive_sha256=digest(archive)))


def wsl_path(path):
    path=Path(path).resolve()
    if os.name!='nt':return str(path)
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]
