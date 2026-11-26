import os,pathlib,sys
p=pathlib.Path(__file__).parent;repo=pathlib.Path('/root/autodl-tmp/SimAI-handoff');sys.path.insert(0,str(repo/'scripts/dag_defense'));from supervise_validation import supervise
vllm='/root/autodl-tmp/venvs/vllm-0.8.5/bin/python';env=dict(os.environ,PD_ROUTE_DIR=str(p/'service'));service=repo/'docs/dag_defense/environment/scripts/start-pd-stream.sh'
supervise(p/'supervisor',['bash',str(service)],p/'service/ready',[vllm,'-c','import time;time.sleep(300)'],lambda:{'ready':True,'status':'diagnostic_injected_gate_NOT_FORMAL'},env=env,startup_timeout_s=400,collector_timeout_s=360,grace_s=20)
