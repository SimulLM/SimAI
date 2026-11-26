"""Matrix coverage and immutable-input checks; fixtures are not validation."""
import copy,hashlib,json,pathlib,tempfile
import pytest
from validation_matrix import validate_matrix

def test_matrix_requires_complete_distinct_verified_files():
 with tempfile.TemporaryDirectory() as td:
  root=pathlib.Path(td);manifest=root/'manifest.json';runs=[]
  for n in (1024,2048):
   for c in (1,2,4):
    for rep in range(5):
     name=f'{n}-{c}-{rep}';f=root/name;rows=[]
     for i in range(32):
      tokens=[1]+[4]*(n-2)+[4+len(runs)*32+i];digest=hashlib.sha256((json.dumps(tokens,separators=(',',':'))+'\n').encode()).hexdigest()
      rows.append({'run_id':name,'request_id':name+str(i),'input_id':name+'i'+str(i),'wave':i//c,'index_in_wave':i%c,'input_ids':tokens,'input_sha256':digest})
     f.write_text(''.join(json.dumps(row)+'\n' for row in rows))
     runs.append(dict(run_id=name,path=name,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),input_tokens=n,output_tokens=128,concurrency=c,requests=32,repeat=rep))
  original={'runs':runs};validate_matrix(original,manifest)
  for kind in ('missing','duplicate_id','duplicate_path','bad_shape','repetition','hash','escape'):
   d=copy.deepcopy(original)
   if kind=='missing':d['runs'].pop()
   elif kind=='duplicate_id':d['runs'][0]['run_id']=d['runs'][1]['run_id']
   elif kind=='duplicate_path':d['runs'][0]['path']=d['runs'][1]['path']
   elif kind=='bad_shape':d['runs'][0]['output_tokens']=64
   elif kind=='repetition':d['runs'][0]['concurrency']=2
   elif kind=='hash':d['runs'][0]['sha256']='0'*64
   else:d['runs'][0]['path']='../outside'
   with pytest.raises(ValueError):validate_matrix(d,manifest)

def test_cross_run_duplicate_rejected_after_rehash(tmp_path):
 root=tmp_path;manifest=root/'manifest.json';runs=[]
 for n in (1024,2048):
  for c in (1,2,4):
   for rep in range(5):
    name=f'{n}-{c}-{rep}';path=root/name;rows=[]
    for i in range(32):
     token=[1]+[4]*(n-2)+[4+len(runs)*32+i];h=hashlib.sha256((json.dumps(token,separators=(',',':'))+'\n').encode()).hexdigest()
     rows.append({'run_id':name,'request_id':name+str(i),'input_id':name+'i'+str(i),'wave':i//c,'index_in_wave':i%c,'input_ids':token,'input_sha256':h})
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows));runs.append({'run_id':name,'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'input_tokens':n,'output_tokens':128,'concurrency':c,'requests':32,'repeat':rep})
 data={'runs':runs};validate_matrix(data,manifest)
 first=json.loads((root/runs[0]['path']).read_text().splitlines()[0]);target=root/runs[1]['path'];rows=[json.loads(line) for line in target.read_text().splitlines()];rows[0]['input_ids']=first['input_ids'];rows[0]['input_sha256']=first['input_sha256'];target.write_text(''.join(json.dumps(r)+'\n' for r in rows));runs[1]['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
 with pytest.raises(ValueError,match='duplicate matrix input digest'):validate_matrix(data,manifest)
