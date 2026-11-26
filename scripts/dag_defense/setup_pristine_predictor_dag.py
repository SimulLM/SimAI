"""Create a disposable DAG worktree with the pinned pristine predictor.

This is a cost-compatibility diagnostic, not proof the original cost model is accurate.
"""
import argparse, hashlib, pathlib, subprocess

PIN='cef83f9ddd96540e3e9f48934f11335d52d54fce'
REL='vidur-alibabacloud/vidur/execution_time_predictor/sklearn_execution_time_predictor.py'
EXPECTED='53b4f15d86385c9aad931223b1b58dc38beb3f385be049e27031ebf99146375d'

def setup(repo, baseline, dest, dag_commit):
 repo,baseline,dest=map(pathlib.Path,(repo,baseline,dest))
 if dest.exists():raise FileExistsError(dest)
 def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args])
 if git(baseline,'rev-parse','HEAD').decode().strip()!=PIN:raise ValueError('unexpected baseline revision')
 if git(baseline,'diff','--name-only','HEAD').strip():raise ValueError('baseline tracked files changed')
 content=git(baseline,'show',f'{PIN}:{REL}')
 if hashlib.sha256(content).hexdigest()!=EXPECTED:raise ValueError('pristine predictor hash mismatch')
 resolved=git(repo,'rev-parse',dag_commit+'^{commit}').decode().strip()
 subprocess.run(['git','-C',str(repo),'worktree','add','--detach',str(dest),resolved],check=True)
 (dest/REL).write_bytes(content)
 if hashlib.sha256((dest/REL).read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('predictor write verification failed')
 print(f'DAG commit: {resolved}\npristine predictor SHA256: {EXPECTED}\nworktree: {dest}')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--baseline',required=True);p.add_argument('--destination',required=True);p.add_argument('--dag-commit',required=True);a=p.parse_args();setup(a.repo,a.baseline,a.destination,a.dag_commit)
