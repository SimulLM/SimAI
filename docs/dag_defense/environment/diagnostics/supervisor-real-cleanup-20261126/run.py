import json,os,pathlib,subprocess,sys
p=pathlib.Path(__file__).parent;repo=pathlib.Path('/root/autodl-tmp/SimAI-handoff');sys.path.insert(0,str(repo/'scripts/dag_defense'));from supervise_validation import supervise
vllm='/root/autodl-tmp/venvs/vllm-0.8.5/bin/python';env=dict(os.environ,PD_ROUTE_DIR=str(p/'service'));service=repo/'docs/dag_defense/environment/scripts/start-pd-stream.sh'
rc=supervise(p/'supervisor',['bash',str(service)],p/'service/ready',[vllm,str(p/'failed_collector.py')],lambda:{'ready':True,'status':'diagnostic_injected_gate_NOT_FORMAL'},env=env,startup_timeout_s=400,collector_timeout_s=45,grace_s=20)
(p/'supervisor.exit').write_text(str(rc)+'\n');s=json.loads((p/'supervisor/status.json').read_text());assert rc==1 and s['status']=='collector_failed' and s['service_group_gone'];n=subprocess.run(['nvidia-smi','--query-gpu=index,memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True);(p/'gpu-after.csv').write_text(n.stdout);mem=[int(l.split(',')[1].strip()) for l in n.stdout.splitlines()];assert mem==[0,0],mem
print(json.dumps({'rc':rc,'status':s['status'],'service_group_gone':s['service_group_gone'],'gpu_memory_mib':mem},indent=2))
