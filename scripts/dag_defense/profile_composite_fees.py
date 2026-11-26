"""Independent single-GPU vLLM worker envelopes; never runs PD/E2E requests.

The profile replaces prepare/layers/head/sampler fees. Synchronized host envelopes
include CPU launches, GPU work and waiting once; GPU subevents are not additive.
"""
import argparse,json,os,pathlib,time

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    import torch
    from vllm import LLM,SamplingParams
    from vllm.worker.model_runner import ModelRunner
    from vllm.core.scheduler import Scheduler
    from vllm.engine.llm_engine import LLMEngine
    state={'active':False,'wave':None,'n':None,'b':None,'step':0};records=[];pending={}
    def record(row):
        records.append(dict(row,wave=state['wave'],input_tokens=state['n'],offered_batch=state['b'],step=state['step'],warmup=state['wave']<10))
    oldprep=ModelRunner.prepare_model_input
    def prep(self,groups,*args,**kw):
        if not state['active']:return oldprep(self,groups,*args,**kw)
        torch.cuda.synchronize();start=time.monotonic_ns()
        result=oldprep(self,groups,*args,**kw)
        pending[id(result)]={'start_ns':start,'groups':[{'request_id':g.request_id,'is_prompt':bool(g.is_prompt)} for g in groups]}
        return result
    ModelRunner.prepare_model_input=prep
    oldexecute=ModelRunner.execute_model
    def execute(self,model_input,*args,**kw):
        item=pending.pop(id(model_input),None)
        if item is None:return oldexecute(self,model_input,*args,**kw)
        result=oldexecute(self,model_input,*args,**kw);torch.cuda.synchronize();end=time.monotonic_ns()
        phase='prefill' if all(g['is_prompt'] for g in item['groups']) else 'decode'
        assert all(g['is_prompt']==(phase=='prefill') for g in item['groups'])
        seq=list(model_input.seq_lens);query=list(model_input.query_lens)
        record({'kind':'worker','phase':phase,'batch':len(item['groups']),'seq_lens':seq,'query_lens':query,'groups':item['groups'],'start_ns':item['start_ns'],'end_ns':end,'duration_ms':(end-item['start_ns'])/1e6})
        return result
    ModelRunner.execute_model=execute
    oldschedule=Scheduler.schedule
    def schedule(self,*args,**kw):
        if not state['active']:return oldschedule(self,*args,**kw)
        torch.cuda.synchronize();start=time.monotonic_ns();result=oldschedule(self,*args,**kw);end=time.monotonic_ns()
        groups=result[0]
        if groups:record({'kind':'schedule','duration_ms':(end-start)/1e6,'start_ns':start,'end_ns':end,'batch':len(groups)})
        return result
    Scheduler.schedule=schedule
    oldprocess=LLMEngine._process_model_outputs
    def process(self,*args,**kw):
        if not state['active']:return oldprocess(self,*args,**kw)
        torch.cuda.synchronize();start=time.monotonic_ns();result=oldprocess(self,*args,**kw);torch.cuda.synchronize();end=time.monotonic_ns()
        record({'kind':'output','duration_ms':(end-start)/1e6,'start_ns':start,'end_ns':end})
        return result
    LLMEngine._process_model_outputs=process
    llm=LLM(model='/root/autodl-tmp/models/Llama-2-7b-hf',dtype='float16',tensor_parallel_size=1,enforce_eager=True,max_model_len=4096,max_num_seqs=4,max_num_batched_tokens=8192,gpu_memory_utilization=.75,enable_prefix_caching=False,enable_chunked_prefill=False,disable_log_stats=True,generation_config='vllm')
    engine=llm.llm_engine
    cfg=engine.model_config.hf_config
    (a.output/'config.json').write_text(json.dumps({'model':'NousResearch/Llama-2-7b-hf','revision':'8efe6c9b93655b934e27bd9981e3ec13e55aee9d','dtype':'float16','tp':1,'rope_theta':cfg.rope_theta,'rope_scaling':cfg.rope_scaling,'warmups':10,'measured':30,'scope':'single GPU offline prepare_model_input through synchronized execute_model; separate disjoint schedule/output; no KV transport'},indent=2)+'\n')
    for n in (2048,1024):
        for b in (3,1,2,4):
            for wave in range(40):
                state.update(active=True,wave=wave,n=n,b=b);records.clear();outputs={}
                ids=[f'fee-n{n}-b{b}-w{wave}-r{i}' for i in range(b)]
                for i,rid in enumerate(ids):
                    prompt=[1,450+i]+[7483,310,3444,338]*((n+3)//4)
                    engine.add_request(rid,{'prompt_token_ids':prompt[:n]},SamplingParams(temperature=0,top_p=1,seed=0,ignore_eos=True,max_tokens=128,min_tokens=128))
                while engine.has_unfinished_requests():
                    state['step']+=1
                    for result in engine.step():
                        if result.finished:outputs[result.request_id]={'prompt':len(result.prompt_token_ids),'output':len(result.outputs[0].token_ids),'finish_reason':result.outputs[0].finish_reason}
                state['active']=False
                assert set(outputs)==set(ids) and all(r=={'prompt':n,'output':128,'finish_reason':'length'} for r in outputs.values())
                with (a.output/'samples.jsonl').open('a') as f:
                    for row in records:f.write(json.dumps(row,separators=(',',':'))+'\n')
                with (a.output/'waves.jsonl').open('a') as f:f.write(json.dumps({'n':n,'batch':b,'wave':wave,'warmup':wave<10,'outputs':outputs,'records':len(records)})+'\n')
                print('completed',n,b,wave,flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
