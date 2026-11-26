"""Fail-closed static gate fixtures; never grant live readiness."""
import json,pathlib,tempfile
import freeze_preflight as f
with tempfile.TemporaryDirectory() as tmp:
 p=pathlib.Path(tmp);repo=p/'repo';repo.mkdir();baseline=p/'baseline';baseline.mkdir();model=p/'model';model.mkdir();manifest=p/'manifest';manifest.write_text('{}');register=p/'blockers.json';freeze=p/'freeze.json'
 for name in ('config.json','generation_config.json','model.safetensors.index.json','tokenizer.json','tokenizer.model','tokenizer_config.json','special_tokens_map.json','README.md','LICENSE.txt','USE_POLICY.md',*f.WEIGHTS):(model/name).write_text('fixture')
 for n in f.REQUIRED:(repo/n).write_text('evidence')
 reg={'required':{n:{'status':'open','evidence':n} for n in f.REQUIRED}};register.write_text(json.dumps(reg))
 old_digest,old_check,old_run,old_matrix=f.digest,f.subprocess.check_output,f.subprocess.run,f.validate_matrix
 try:
  f.digest=lambda path: f.WEIGHTS.get(path.name,'hash')
  f.subprocess.check_output=lambda *a,**k:'cef83f9ddd96540e3e9f48934f11335d52d54fce\n'
  class Result:returncode=0
  f.subprocess.run=lambda *a,**k:Result()
  f.validate_matrix=lambda *a:None
  result=f.run(repo,baseline,model,manifest,register,freeze);assert result['status']=='blocked';block=next(x for x in result['checks'] if x['name']=='blocker_register');assert all(n in block['detail'] for n in f.REQUIRED)
  for item in reg['required'].values():item['status']='closed'
  register.write_text(json.dumps(reg));artifact=p/'artifact';artifact.write_text('fixture');keys=('source','baseline_source','compute_cost','communication_cost','service_configuration','scoring_rule','compatibility_evidence');freeze.write_text(json.dumps({'status':'frozen','validation_manifest_sha256':'hash','artifacts':{k:{'path':str(artifact),'sha256':'hash'} for k in keys}}))
  result=f.run(repo,baseline,model,manifest,register,freeze);assert result['status']=='static_preflight_passed_live_idle_still_required'
  (model/'tokenizer.model').unlink();assert f.run(repo,baseline,model,manifest,register,freeze)['status']=='blocked'
  print('PASS: open blockers, missing freeze, positive static fixture, missing model file; live readiness not granted')
 finally:f.digest,f.subprocess.check_output,f.subprocess.run,f.validate_matrix=old_digest,old_check,old_run,old_matrix
