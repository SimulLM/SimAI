import json,os,pathlib,subprocess,time
root=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pd-pull-calibration-replay-20261126')
repos={'dag':'/root/autodl-tmp/SimAI-pristine-predictor-repro','baseline':'/root/autodl-tmp/SimAI-pristine-baseline'}
for case in ('serial-0','concurrent-0'):
 for mode,repo in repos.items():
  olddir=old/case/('dag' if mode=='dag' else 'adapted_baseline');out=root/case/mode;out.mkdir(parents=True)
  cmd=json.loads((olddir/'command.json').read_text());cmd=[x.replace(str(olddir),str(out)) for x in cmd]
  env=dict(os.environ,PYTHONPATH=f'{repo}/vidur-alibabacloud:{repo}',WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
  (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
  with (out/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT)
  (out/'exit').write_text(str(r.returncode)+'\n');print(case,mode,r.returncode,flush=True)
