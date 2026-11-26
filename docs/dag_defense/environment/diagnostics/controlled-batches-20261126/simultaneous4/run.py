import json,os,pathlib,subprocess
root=pathlib.Path(__file__).parent;old=pathlib.Path('/root/autodl-tmp/dag-handoff/runs/pristine-real-arrival-20261126/concurrent-0')
repos={'original':'/root/autodl-tmp/SimAI-pristine-baseline','corrected':'/root/autodl-tmp/SimAI-baseline-kv-ready','dag':'/root/autodl-tmp/SimAI-pristine-predictor-repro'}
for name,repo in repos.items():
 src=old/('dag' if name=='dag' else 'baseline');out=root/name;out.mkdir(exist_ok=False)
 cmd=json.loads((src/'command.json').read_text());cmd=[v.replace(str(src),str(out)) for v in cmd]
 i=cmd.index('--trace_request_generator_config_trace_file');cmd[i+1]=str(root/'trace.csv')
 env=dict(os.environ,PYTHONPATH=repo+'/vidur-alibabacloud:'+repo,WANDB_MODE='disabled',PYTHONDONTWRITEBYTECODE='1')
 (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
 with (out/'process.log').open('w') as f:r=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT)
 (out/'exit').write_text(str(r.returncode)+'\n');print(name,r.returncode,flush=True)
 if r.returncode:raise SystemExit(r.returncode)
