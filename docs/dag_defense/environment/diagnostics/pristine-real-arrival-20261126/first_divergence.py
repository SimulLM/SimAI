import glob,json,pathlib
root=pathlib.Path(__file__).parent;out={}
for case in ('serial-0','concurrent-0'):
 seqs=[]
 for mode in ('dag','baseline'):
  files=list((root/case/mode).glob('2026*/chrome_trace.json'));assert len(files)==1
  ev=json.loads(files[0].read_text())['traceEvents']; seq=[]
  for e in ev:
   a=e.get('args',{})
   if e.get('ph')=='X' and e.get('pid')==1 and a.get('request_ids'):
    seq.append({'ts_us':e['ts'],'duration_us':e['dur'],'request_ids':sorted(a['request_ids']),'num_tokens':sorted(a['num_tokens'])})
  seq.sort(key=lambda x:x['ts_us']);seqs.append(seq)
 index=next((i for i,(a,b) in enumerate(zip(*seqs)) if (a['request_ids'],a['num_tokens'])!=(b['request_ids'],b['num_tokens'])),None)
 out[case]={'first_sequence_index':index,'dag':seqs[0][index] if index is not None else None,'baseline':seqs[1][index] if index is not None else None,'limitations':'first positional divergence; not itself proof of cause; timing and prior history must be inspected'}
(root/'first-divergence.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
