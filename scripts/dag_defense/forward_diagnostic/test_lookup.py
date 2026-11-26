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
