import json,pathlib,time,os
from vllm import LLM,SamplingParams
out=pathlib.Path(os.environ['COMPUTE_DIAG_DIR']);model='/root/autodl-tmp/models/Llama-2-7b-hf';waves=int(os.environ.get('PROFILE_WAVES','40'))
llm=LLM(model=model,dtype='float16',tensor_parallel_size=1,enforce_eager=True,max_model_len=4096,max_num_seqs=4,max_num_batched_tokens=4096,gpu_memory_utilization=.75,enable_prefix_caching=False,enable_chunked_prefill=False,disable_log_stats=True,generation_config='vllm')
e=llm.llm_engine;params=SamplingParams(temperature=0,top_p=1,seed=0,ignore_eos=True,max_tokens=128,min_tokens=128)
for case,n,batch,steps in [('1024-mixed2',1024,2,2),('2048-span8',2048,4,9)]:
 for wave in range(waves):
  start=time.monotonic_ns();ids=[f'{case}-w{wave}-r{i}' for i in range(batch)]
  def add(i):e.add_request(ids[i],{'prompt_token_ids':([1,450+i]+[7483,310,3444,338]*((n+3)//4))[:n]},params)
  for i in range(batch//2):add(i)
  for _ in range(steps):e.step()
  for i in range(batch//2,batch):add(i)
  outputs={}
  while e.has_unfinished_requests():
   for x in e.step():
    if x.finished:outputs[x.request_id]={'input_tokens':len(x.prompt_token_ids),'output_tokens':len(x.outputs[0].token_ids),'finish_reason':x.outputs[0].finish_reason}
  assert set(outputs)==set(ids) and all(x['input_tokens']==n and x['output_tokens']==128 and x['finish_reason']=='length' for x in outputs.values())
  with (out/'waves.jsonl').open('a') as f:f.write(json.dumps({'case':case,'wave':wave,'start_ns':start,'end_ns':time.monotonic_ns(),'outputs':outputs})+'\n');f.flush()
  print('completed',case,wave,flush=True)
