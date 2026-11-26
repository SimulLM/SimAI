import json,pathlib,time,os
from vllm import LLM,SamplingParams
out=pathlib.Path(os.environ['COMPUTE_DIAG_DIR']);model='/root/autodl-tmp/models/Llama-2-7b-hf'
llm=LLM(model=model,dtype='float16',tensor_parallel_size=1,enforce_eager=True,max_model_len=4096,max_num_seqs=4,max_num_batched_tokens=4096,gpu_memory_utilization=.75,enable_prefix_caching=False,enable_chunked_prefill=False,disable_log_stats=True,generation_config='vllm')
params=SamplingParams(temperature=0,top_p=1,seed=0,ignore_eos=True,max_tokens=128,min_tokens=128)
for n,batch in ((2048,2),(1024,3)):
 for wave in range(40):
  prompts=[{'prompt_token_ids':([1,450+i]+[7483,310,3444,338]*((n+3)//4))[:n]} for i in range(batch)]
  start=time.monotonic_ns();outputs=llm.generate(prompts,params,use_tqdm=False);end=time.monotonic_ns()
  rows=[{'request_id':o.request_id,'input_tokens':len(o.prompt_token_ids),'output_tokens':len(o.outputs[0].token_ids),'finish_reason':o.outputs[0].finish_reason} for o in outputs]
  row={'input_length':n,'batch':batch,'wave':wave,'warmup':wave<10,'start_ns':start,'end_ns':end,'outputs':rows}
  with (out/'waves.jsonl').open('a') as f:f.write(json.dumps(row)+'\n');f.flush()
  assert len(rows)==batch and all(x['input_tokens']==n and x['output_tokens']==128 and x['finish_reason']=='length' for x in rows)
  print('completed',n,batch,wave,flush=True)
