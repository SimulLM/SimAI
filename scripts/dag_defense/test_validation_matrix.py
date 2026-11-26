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
     name=f'{n}-{c}-{rep}';f=root/name;f.write_text(name)
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
