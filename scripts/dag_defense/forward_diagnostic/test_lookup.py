import pathlib,sys
from lookup import ForwardLookup,CoverageError
root=pathlib.Path(__file__).resolve().parents[3]/'docs/dag_defense/environment/diagnostics'
f=ForwardLookup(root/'pd-eager-profile-20261126/candidate/forward-cost.csv',root/'forward-coverage-refresh-20261126/strict-forward-context-bins.csv')
assert f.get('prefill',[1024],[0],[1024])[0]==(1024,1)
assert f.get('decode',[1024],[1025],[1])[0]==(1024,1,1040,0)
assert f.get('decode',[2048]*3,[2049,2049,2050],[1]*3)[0]==(2048,3,2064,1)
for args in [('prefill',[1024],[0],[512]),('decode',[1024]*3,[1025,1025,1026],[1]*3),('decode',[1024,1024],[1025,1027],[1,1]),('decode',[1024,2048],[1025,2049],[1,1]),('decode',[1024],[1024],[1]),('mixed',[1024],[1025],[1]),('decode',[1024],[1025.5],[1])]:
 try:f.get(*args)
 except CoverageError:pass
 else:raise AssertionError('unsupported shape accepted '+str(args))
print('PASS measured keys and fail-closed unsupported shapes')
import tempfile,csv
with tempfile.TemporaryDirectory() as d:
 path=pathlib.Path(d)/'patterns.csv'
 with path.open('w',newline='') as file:
  writer=csv.DictWriter(file,fieldnames=['input_tokens','actual_batch','rounded_mean_context','context_pattern','warmup_waves','measured_waves','median_forward_ms','eligible']);writer.writeheader();writer.writerow({'input_tokens':2048,'actual_batch':4,'rounded_mean_context':2064,'context_pattern':'0,0,9,9','warmup_waves':10,'measured_waves':30,'median_forward_ms':13.2,'eligible':1})
 h=ForwardLookup(root/'pd-eager-profile-20261126/candidate/forward-cost.csv',root/'forward-coverage-refresh-20261126/strict-forward-context-bins.csv',path)
 assert h.get('decode',[2048]*4,[2058,2049,2058,2049],[1]*4)[1]==13.2
 for ctx in ([2057,2049,2057,2049],[2058,2049,2058,2048],[2058,2049,2049,2049]):
  try:h.get('decode',[2048]*4,ctx,[1]*4)
  except CoverageError:pass
  else:raise AssertionError('unmeasured pattern accepted')
print('PASS exact measured pattern only')
