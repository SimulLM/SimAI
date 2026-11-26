"""Read-only experimental freeze preflight. Never starts validation."""
import argparse,hashlib,json,pathlib,subprocess,sys
from validation_matrix import validate_matrix
REQUIRED=('common_cost_and_no_double_charge','arrival_completion_boundary','concurrent_readiness_batching','freeze_and_preflight')
WEIGHTS={'model-00001-of-00002.safetensors':'4ec71fd53e99766de38f24753b30c9e8942630e9e576a1ba27b0ec531e87be41','model-00002-of-00002.safetensors':'41780b5dac322ac35598737e99208d90bdc632a1ba3389ebedbb46a1d8385a7f'}
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def run(repo,baseline,model,manifest,register,freeze):
 checks=[]
 def check(name,fn):
  try:detail=fn();checks.append({'name':name,'status':'passed','detail':detail})
  except Exception as e:checks.append({'name':name,'status':'open','detail':type(e).__name__+': '+str(e)[:400]})
 def model_check():
  for name,sha in WEIGHTS.items():
   if digest(model/name)!=sha:raise ValueError('weight mismatch '+name)
  for name in ('model.safetensors.index.json','config.json','generation_config.json','tokenizer.json','tokenizer.model','tokenizer_config.json','special_tokens_map.json','README.md','LICENSE.txt','USE_POLICY.md'):
   if not (model/name).is_file():raise ValueError('missing '+name)
  return 'both weights verified and required tokenizer/config/license files present; revision must be recorded in freeze'
 def baseline_check():
  head=subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip()
  if head!='cef83f9ddd96540e3e9f48934f11335d52d54fce':raise ValueError('baseline commit mismatch')
  for args in (['diff','--quiet'],['diff','--cached','--quiet']):
   if subprocess.run(['git','-C',str(baseline),*args]).returncode:raise ValueError('baseline tracked changes')
  return {'commit':head,'untracked_note':'untracked files require separate provenance review'}
 def matrix_check():validate_matrix(json.loads(manifest.read_text()),manifest);return '30 files, 960 unique request identities and tokens checked'
 def gate_check():
  data=json.loads(register.read_text());g=data['required']
  if set(g)!=set(REQUIRED):raise ValueError('invalid blocker register')
  open_names=[]
  for name in REQUIRED:
   item=g[name];evidence=(repo/item['evidence']).resolve()
   if not evidence.is_relative_to(repo.resolve()) or not evidence.is_file():raise ValueError('missing evidence '+name)
   if item['status']!='closed':open_names.append(name)
  if open_names:raise ValueError('open blockers: '+', '.join(open_names))
  return 'all four blockers declared closed; inspect evidence independently'
 def freeze_check():
  obj=json.loads(freeze.read_text())
  if obj.get('status')!='frozen':raise ValueError('not frozen')
  if obj.get('validation_manifest_sha256')!=digest(manifest):raise ValueError('input manifest mismatch')
  for key in ('source','baseline_source','compute_cost','communication_cost','service_configuration','scoring_rule','compatibility_evidence'):
   entry=obj['artifacts'][key];p=pathlib.Path(entry['path'])
   if not p.is_file() or digest(p)!=entry['sha256']:raise ValueError('missing or changed artifact '+key)
  return 'freeze artifact hashes valid; live per-run idle and failure policy still required'
 for n,f in [('model_files',model_check),('pristine_baseline',baseline_check),('validation_inputs',matrix_check),('blocker_register',gate_check),('freeze_manifest',freeze_check)]:check(n,f)
 return {'status':'blocked' if any(x['status']!='passed' for x in checks) else 'static_preflight_passed_live_idle_still_required','checks':checks,'formal_validation_started':False,'caveat':'Read-only static checks do not validate live service idle or prove scientific validity of evidence.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/SimAI-handoff'));p.add_argument('--baseline',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/SimAI-pristine-baseline'));p.add_argument('--model',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/models/Llama-2-7b-hf'));p.add_argument('--manifest',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/dag-handoff/validation-input-candidate-20261126/candidate-manifest.json'));p.add_argument('--register',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/SimAI-handoff/docs/dag_defense/freeze_gate/blockers.json'));p.add_argument('--freeze',type=pathlib.Path,default=pathlib.Path('/root/autodl-tmp/dag-handoff/parameter-freeze.json'));p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 result=run(a.repo,a.baseline,a.model,a.manifest,a.register,a.freeze);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if result['status']=='blocked' else 0
if __name__=='__main__':sys.exit(main())
