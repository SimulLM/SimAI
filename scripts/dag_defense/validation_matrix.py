"""Verify validation-matrix coverage and immutable input files."""
import hashlib

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_matrix(manifest, manifest_file):
 runs=manifest.get('runs')
 if not isinstance(runs,list) or len(runs)!=30:raise ValueError('validation matrix must have exactly 30 runs')
 groups={};ids=set();paths=set();repetitions=set()
 for spec in runs:
  rid=spec.get('run_id');length=spec.get('input_tokens');concurrency=spec.get('concurrency')
  if not isinstance(rid,str) or not rid or rid in ids:raise ValueError('duplicate or missing matrix run ID')
  ids.add(rid)
  if length not in (1024,2048) or concurrency not in (1,2,4) or spec.get('output_tokens')!=128 or spec.get('requests')!=32:raise ValueError('invalid validation matrix shape')
  name=spec.get('path')
  if not isinstance(name,str) or not name:raise ValueError('missing matrix input path')
  path=(manifest_file.parent/name).resolve()
  if path.parent!=manifest_file.parent.resolve() or path in paths:raise ValueError('duplicate or invalid matrix input path')
  paths.add(path)
  if not path.is_file() or sha(path)!=spec.get('sha256'):raise ValueError('missing or mismatched matrix input')
  repeat=spec.get('repeat')
  if type(repeat) is not int or repeat not in range(5) or (length,concurrency,repeat) in repetitions:raise ValueError('invalid or duplicate repetition')
  repetitions.add((length,concurrency,repeat))
  key=(length,concurrency);groups[key]=groups.get(key,0)+1
 if any(groups.get((n,c))!=5 for n in (1024,2048) for c in (1,2,4)):raise ValueError('each validation shape requires five repetitions')

