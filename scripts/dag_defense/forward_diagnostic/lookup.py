"""Strict candidate full-forward lookup; unsupported shapes fail rather than extrapolate."""
import csv,hashlib,math,pathlib
class CoverageError(ValueError):pass
class ForwardLookup:
 def __init__(self,prefill_path,decode_path,pattern_path=None):
  self.prefill={};self.decode={};self.patterns={};self.hashes={}
  for path in (pathlib.Path(prefill_path),pathlib.Path(decode_path),*([pathlib.Path(pattern_path)] if pattern_path else [])):
   self.hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  with open(prefill_path,newline='') as f:
   for row in csv.DictReader(f):
    if row['nature']!='producer_prefill':continue
    if int(row['warmup_waves'])<10 or int(row['measured_waves'])<30:raise CoverageError('unqualified prefill')
    k=(int(row['input_tokens']),int(row['actual_batch']));self._add(self.prefill,k,row['median_of_wave_medians_ms'])
  with open(decode_path,newline='') as f:
   for row in csv.DictReader(f):
    if row['eligible']!='1' or int(row['warmup_waves'])<10 or int(row['measured_waves'])<30:raise CoverageError('unqualified decode')
    k=tuple(int(row[x]) for x in ('input_tokens','actual_batch','rounded_mean_context','mixed_context'));self._add(self.decode,k,row['median_forward_ms'])
  if pattern_path:
   with open(pattern_path,newline='') as f:
    for row in csv.DictReader(f):
     if row['eligible']!='1' or int(row['warmup_waves'])<10 or int(row['measured_waves'])<30:raise CoverageError('unqualified pattern')
     pattern=tuple(int(x) for x in row['context_pattern'].split(','));batch=int(row['actual_batch'])
     if len(pattern)!=batch or sorted(pattern)!=list(pattern) or pattern[0]!=0:raise CoverageError('invalid context pattern')
     key=(int(row['input_tokens']),batch,int(row['rounded_mean_context']),pattern);self._add(self.patterns,key,row['median_forward_ms'])
 @staticmethod
 def _add(table,key,value):
  n=float(value)
  if key in table or not math.isfinite(n) or n<=0:raise CoverageError('duplicate or invalid measured cost: '+str(key))
  table[key]=n
 def get(self,phase,input_lengths,contexts,tokens):
  if not input_lengths or len(input_lengths)!=len(contexts) or len(tokens)!=len(contexts):raise CoverageError('inconsistent batch shape')
  if any(not math.isfinite(float(x)) or float(x)!=int(x) or x<0 for x in (*input_lengths,*contexts,*tokens)):raise CoverageError('non-integral or invalid token count')
  if len(set(input_lengths))!=1:raise CoverageError('mixed input lengths unsupported')
  length=input_lengths[0];batch=len(input_lengths)
  if phase=='prefill':
   if any(t!=length for t in tokens):raise CoverageError('chunked prefill unsupported')
   key=(length,batch);table=self.prefill
  elif phase=='decode':
   if any(t!=1 for t in tokens) or any(c<=length or c>length+127 for c in contexts):raise CoverageError('unsupported decode step or context')
   rounded=((sum(contexts)//batch+15)//16)*16
   if max(contexts)-min(contexts)>1:
    pattern=tuple(sorted(int(c-min(contexts)) for c in contexts));key=(length,batch,rounded,pattern);table=self.patterns
   else:key=(length,batch,rounded,int(max(contexts)!=min(contexts)));table=self.decode
  else:raise CoverageError('mixed or unknown phase')
  if key not in table:raise CoverageError(f'unmeasured {phase} shape {key}')
  return key,table[key]
