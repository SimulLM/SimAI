import json,pathlib,hashlib,sys
from transformers import AutoTokenizer,AutoConfig
p=pathlib.Path('/root/autodl-tmp/models/Llama-2-7b-hf');root=pathlib.Path('/root/autodl-tmp/dag-handoff/validation-input-candidate-20261126');out=pathlib.Path(__file__).parent
sys.path.insert(0,'/root/autodl-tmp/SimAI-handoff/scripts/dag_defense');from validation_matrix import validate_matrix
manifest=root/'candidate-manifest.json';m=json.loads(manifest.read_text());validate_matrix(m,manifest)
t=AutoTokenizer.from_pretrained(p,local_files_only=True);c=AutoConfig.from_pretrained(p,local_files_only=True);generation=json.loads((p/'generation_config.json').read_text());revision=(p/'REVISION.txt').read_text().splitlines();assert revision==['NousResearch/Llama-2-7b-hf','8efe6c9b93655b934e27bd9981e3ec13e55aee9d']
assert (len(t),t.vocab_size,t.bos_token_id,t.eos_token_id,t.pad_token_id,c.vocab_size,c.pad_token_id)==(32000,32000,1,2,0,32000,0)
assert getattr(c,'rope_theta',None)==10000 and getattr(c,'rope_scaling',None) is None and generation['pad_token_id']==32000
sums={}
for line in (p/'SHA256SUMS').read_text().splitlines():
 digest,name=line.split('  ',1);sums[name]=digest
assert sums['model-00001-of-00002.safetensors']=='4ec71fd53e99766de38f24753b30c9e8942630e9e576a1ba27b0ec531e87be41' and sums['model-00002-of-00002.safetensors']=='41780b5dac322ac35598737e99208d90bdc632a1ba3389ebedbb46a1d8385a7f'
log=pathlib.Path('/root/autodl-tmp/dag-handoff/model-sha256-recheck-20261126.log');lines=log.read_text().splitlines();assert len(lines)==len(sums) and set(lines)=={name+': OK' for name in sums}
report={'status':'model_and_candidate_input_checks_only_not_freeze','model':revision[0],'revision':revision[1],'model_manifest_sha256':hashlib.sha256((p/'SHA256SUMS').read_bytes()).hexdigest(),'weights':{k:v for k,v in sums.items() if k.endswith('.safetensors')},'file_check_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'validation_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'candidate_runs':30,'candidate_requests':960,'tokenizer_class':type(t).__name__,'vocab_size':len(t),'bos':t.bos_token_id,'eos':t.eos_token_id,'tokenizer_pad':t.pad_token_id,'model_pad':c.pad_token_id,'raw_generation_pad':generation['pad_token_id'],'config_rope_theta':c.rope_theta,'config_rope_scaling':c.rope_scaling,'limitations':['Does not verify actual server runtime settings or historical weight equivalence to Meta','Candidate input is not frozen; no validation requests run','Raw generation pad is outside vocabulary; runtime override and observed service behavior must be frozen and verified']}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
