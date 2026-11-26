"""Verify validation-matrix coverage and immutable input files."""
import hashlib,json

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_matrix(manifest, manifest_file):
 runs=manifest.get('runs')
 if not isinstance(runs,list) or len(runs)!=30:raise ValueError('validation matrix must have exactly 30 runs')
 groups={};ids=set();paths=set();repetitions=set();request_ids=set();input_ids=set();digests=set()
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
  try:rows=[json.loads(line) for line in path.read_text().splitlines()]
  except (ValueError,UnicodeError) as exc:raise ValueError('invalid matrix input JSON') from exc
  if len(rows)!=32:raise ValueError('matrix input count mismatch')
  for index,row in enumerate(rows):
   tokens=row.get('input_ids');request=row.get('request_id');input_id=row.get('input_id');digest=row.get('input_sha256')
   if (not isinstance(request,str) or not request or request in request_ids or not isinstance(input_id,str) or not input_id or input_id in input_ids
       or not isinstance(tokens,list) or len(tokens)!=length or tokens[0]!=1 or any(type(t) is not int or t<4 or t>=32000 for t in tokens[1:])
       or row.get('run_id')!=rid or row.get('wave')!=index//concurrency or row.get('index_in_wave')!=index%concurrency):raise ValueError('invalid or duplicate matrix input identity, token, or wave')
   actual=hashlib.sha256((json.dumps(tokens,separators=(',',':'),ensure_ascii=True)+'\n').encode()).hexdigest()
   if digest!=actual or digest in digests:raise ValueError('invalid or duplicate matrix input digest')
   request_ids.add(request);input_ids.add(input_id);digests.add(digest)
  repeat=spec.get('repeat')
  if type(repeat) is not int or repeat not in range(5) or (length,concurrency,repeat) in repetitions:raise ValueError('invalid or duplicate repetition')
  repetitions.add((length,concurrency,repeat))
  key=(length,concurrency);groups[key]=groups.get(key,0)+1
 if any(groups.get((n,c))!=5 for n in (1024,2048) for c in (1,2,4)):raise ValueError('each validation shape requires five repetitions')

