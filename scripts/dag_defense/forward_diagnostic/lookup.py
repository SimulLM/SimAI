"""Strict candidate full-forward lookup; unsupported shapes fail rather than extrapolate."""
import csv,hashlib,math,pathlib
class CoverageError(ValueError):pass
class ForwardLookup:
 def __init__(self,prefill_path,decode_path):
  self.prefill={};self.decode={};self.hashes={}
  for path in (pathlib.Path(prefill_path),pathlib.Path(decode_path)):
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
   if max(contexts)-min(contexts)>1:raise CoverageError('mixed context span > 1 unsupported')
   key=(length,batch,((sum(contexts)//batch+15)//16)*16,int(max(contexts)!=min(contexts)));table=self.decode
  else:raise CoverageError('mixed or unknown phase')
  if key not in table:raise CoverageError(f'unmeasured {phase} shape {key}')
  return key,table[key]
