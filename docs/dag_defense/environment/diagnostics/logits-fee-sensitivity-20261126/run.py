import json, os, subprocess
from pathlib import Path
root=Path('/root/autodl-tmp/dag-handoff/runs/logits-fee-sensitivity-20261126')
old=Path('/root/autodl-tmp/dag-handoff/runs/receive-sensitivity-single-20261126')
for mode in ['dag','baseline']:
 out=root/mode; out.mkdir(exist_ok=True)
 cmd=json.loads((old/mode/'command.json').read_text())
 cmd[1:3]=[str(root/'bootstrap.py')]
 cmd=[x.replace(str(old/mode),str(out)) for x in cmd]
 repo='/root/autodl-tmp/SimAI-handoff' if mode=='dag' else '/root/autodl-tmp/SimAI-baseline-first-token'
 env=os.environ.copy(); env.update(PYTHONPATH=repo+'/vidur-alibabacloud:/root/autodl-tmp/SimAI-handoff',FORWARD_DIAG_MODE=mode,FORWARD_DIAG_TRACE=str(out/'forward.jsonl'))
 if mode=='baseline': env.update(SIMAI_SERIAL_FIRST_TOKEN_S='0.000875779',SIMAI_SERIAL_FIRST_TOKEN_TRACE=str(out/'first-token.jsonl'),SIMAI_SERIAL_RECV_INTERCEPT_S='0.0045052672',SIMAI_SERIAL_RECV_PER_TOKEN_S='0.000015727422116815474')
 (out/'command.json').write_text(json.dumps(cmd,indent=2))
 with (out/'process.log').open('w') as f: result=subprocess.run(cmd,cwd=repo,env=env,stdout=f,stderr=subprocess.STDOUT)
 (out/'exit').write_text(str(result.returncode)+'\n')
 print(mode,result.returncode,flush=True)
