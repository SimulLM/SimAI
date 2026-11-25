"""Prepare native Linux checkout, Python and backends; never clean the source tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.request

MODULES = ('SimCCL', 'aicb', 'ns-3-alibabacloud')


def save(p, value):
    p.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def command(evidence, name, argv, cwd=None, env=None):
    save(evidence/(name+'-command.json'), dict(argv=list(map(str, argv)),cwd=str(cwd)))
    started=time.time()
    with (evidence/(name+'.log')).open('wb') as f:
        p=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
    save(evidence/(name+'-result.json'),dict(exit_code=p.returncode,wall_time_s=time.time()-started))
    if p.returncode:
        raise RuntimeError(name+' failed: '+str(p.returncode))


def capture(argv):
    return subprocess.check_output(argv,text=True).strip()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--evidence',required=True,type=Path)
    p.add_argument('--name',required=True)
    a=p.parse_args()
    source=a.source.resolve();evidence=a.evidence.resolve()
    evidence.mkdir(parents=True,exist_ok=False)
    native=Path.home()/'.cache/simai-finalize'/a.name
    native.mkdir(parents=True,exist_ok=False)
    try:
        head=capture(['git','-C',str(source),'rev-parse','HEAD'])
        locked={name:capture(['git','-C',str(source),'rev-parse','HEAD:'+name]) for name in MODULES}
        save(evidence/'identity.json',dict(head=head,modules=locked,native=str(native),uname=list(os.uname())))
        checkout=native/'source'
        command(evidence,'clone-root',['git','-c','core.autocrlf=false','clone','--no-hardlinks','--no-checkout',source,checkout])
        command(evidence,'checkout-root',['git','-c','core.autocrlf=false','checkout','--detach',head],checkout)
        for name in MODULES:
            command(evidence,'clone-'+name,['git','-c','core.autocrlf=false','clone','--no-hardlinks','--no-checkout',source/'.git/modules'/name,checkout/name])
            command(evidence,'checkout-'+name,['git','-c','core.autocrlf=false','checkout','--detach',locked[name]],checkout/name)
            command(evidence,'clean-'+name,['git','diff','--exit-code','HEAD','--'],checkout/name)
            status=capture(['git','-C',str(checkout/name),'status','--porcelain'])
            if status:raise ValueError('native submodule is not clean: '+name)
        command(evidence,'absorb-modules',['git','submodule','absorbgitdirs'],checkout)
        headers=['/usr/include/openssl/ssl.h','/usr/include/zlib.h','/usr/include/bzlib.h','/usr/include/lzma.h','/usr/include/sqlite3.h','/usr/include/x86_64-linux-gnu/ffi.h']
        missing=[h for h in headers if not Path(h).exists()]
        save(evidence/'python-headers.json',dict(headers=headers,missing=missing))
        if missing:
            if os.getuid()!=0:raise RuntimeError('Python build dependencies require root')
            command(evidence,'apt-update',['apt-get','update'])
            command(evidence,'apt-python-build',['apt-get','install','-y','libssl-dev','zlib1g-dev','libbz2-dev','libffi-dev','liblzma-dev','libsqlite3-dev'])
        archive=native/'Python-3.12.10.tgz'
        url='https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tgz'
        with urllib.request.urlopen(url,timeout=120) as response,archive.open('wb') as out:
            while block:=response.read(1024*1024):out.write(block)
        save(evidence/'python-source.json',dict(url=url,sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
        with tarfile.open(archive) as t:
            for member in t.getmembers():
                if member.name.startswith('/') or '..' in Path(member.name).parts or member.issym() or member.islnk():
                    raise ValueError('unsafe Python source archive member')
            t.extractall(native)
        prefix=native/'python312';build=native/'Python-3.12.10'
        command(evidence,'python-configure',['./configure','--prefix='+str(prefix),'--with-ensurepip=install'],build)
        command(evidence,'python-build',['make','-j','6'],build)
        command(evidence,'python-install',['make','install'],build)
        python=prefix/'bin/python3.12'
        for name in ('env-a','env-b'):
            venv=native/name
            command(evidence,'venv-'+name,[python,'-m','venv',venv])
            command(evidence,'install-'+name,[venv/'bin/python','-m','pip','install','-r',checkout/'scripts/dag_phase8/requirements.txt','--disable-pip-version-check'])
            command(evidence,'freeze-'+name,[venv/'bin/python','-m','pip','freeze','--all'])
            command(evidence,'pip-check-'+name,[venv/'bin/python','-m','pip','check'])
        command(evidence,'backend-build',[python,checkout/'scripts/dag_phase8/build_reference.py','--output','.cache/finalize-backend'],checkout)
        backend=checkout/'.cache/finalize-backend'
        for f in backend.iterdir():
            if f.suffix=='.log' or f.name in ('build-status.txt','build-root.txt','binaries.sha256'):
                import shutil
                shutil.copyfile(f,evidence/f.name)
        save(evidence/'environment-report.json',dict(status='passed',head=head,modules=locked,native=str(native),checkout=str(checkout),python=str(python),
             env_a=str(native/'env-a/bin/python'),env_b=str(native/'env-b/bin/python'),binaries=str(backend)))
    except Exception as exc:
        import traceback
        save(evidence/'operation-error.json',dict(error=repr(exc),traceback=traceback.format_exc()))
        raise


if __name__=='__main__':main()
