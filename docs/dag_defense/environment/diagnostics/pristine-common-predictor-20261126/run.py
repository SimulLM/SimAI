import json,os,pathlib,subprocess,hashlib
out=pathlib.Path(__file__).parent
old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pristine-baseline-smoke-20261126')
repos={'dag':'/root/autodl-tmp/SimAI-pristine-predictor-dag','baseline':'/root/autodl-tmp/SimAI-pristine-baseline'}
for mode,repo in repos.items():
 dest=out/mode;dest.mkdir()
 cmd=json.loads((old/mode/'command.json').read_text());cmd=[x.replace(str(old/mode),str(dest)) for x in cmd]
 env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 (dest/'command.json').write_text(json.dumps(cmd,indent=2))
 with (dest/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT)
 (dest/'exit').write_text(str(r.returncode)+'\n');print(mode,r.returncode,flush=True)
