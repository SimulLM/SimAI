import json,os,pathlib,subprocess
root=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pristine-real-arrival-20261126/concurrent-0/baseline');repo='/root/autodl-tmp/SimAI-baseline-kv-ready'
out=root/'corrected';out.mkdir(exist_ok=False)
cmd=[x.replace(str(old),str(out)) for x in json.loads((old/'command.json').read_text())]
env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
(out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
with (out/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT)
(out/'exit').write_text(str(r.returncode)+'\n');raise SystemExit(r.returncode)
