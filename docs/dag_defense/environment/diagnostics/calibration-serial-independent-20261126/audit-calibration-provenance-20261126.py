import json,pathlib,collections,hashlib,csv
root=pathlib.Path('/root/autodl-tmp/dag-handoff/runs');out=root/'calibration-provenance-audit-20261126';out.mkdir(exist_ok=False)
paths={'main':root/'calibration-requests-20261126/requests.json','supplement':root/'calibration-serial-supplement-20261126/requests.json','merged':root/'calibration-merged-20261126/requests.json'};data={k:json.loads(v.read_text()) for k,v in paths.items()}; lookup=collections.defaultdict(list)
for source in ('main','supplement'):
 for r in data[source]:lookup[r.get('router_id')].append((source,r))
rows=[];errors=[]
for r in data['merged']:
 matches=lookup[r.get('router_id')];expected=([1,450+r['repeat']*10+r['index']]+[7483,310,3444,338]*130)[:512];h=hashlib.sha256(bytes(str(expected),'utf8')).hexdigest();same=len(matches)==1 and matches[0][1]==r
 if not same or r['input_sha256']!=h:errors.append({'id':r.get('router_id'),'source_count':len(matches),'source_row_equal':same,'input_hash_match':r['input_sha256']==h})
 rows.append({'repeat':r['repeat'],'mode':r['mode'],'index':r['index'],'source':matches[0][0] if len(matches)==1 else 'ambiguous','router_id':r.get('router_id'),'input_sha256':r['input_sha256'],'input_hash_match':r['input_sha256']==h,'send_ns':r['send_ns'],'complete_ns':r['complete_ns'],'status':r['status']})
for r in rows:r['wave']=r['index'] if r['mode']=='serial' else r['index']//2
waves=collections.defaultdict(list)
for r in rows:waves[(r['source'],r['repeat'],r['mode'],r['wave'])].append(r)
groups=collections.defaultdict(list)
for key,rs in waves.items():groups[key[:3]].append((min(x['send_ns'] for x in rs),max(x['complete_ns'] for x in rs),key[3],len(rs)))
checks=[]
for key,seq in sorted(groups.items()):
 seq.sort();overlaps=sum(seq[i][1]>seq[i+1][0] for i in range(len(seq)-1));checks.append({'source':key[0],'repeat':key[1],'mode':key[2],'waves':len(seq),'requests':sum(x[3] for x in seq),'overlapping_adjacent_waves':overlaps,'minimum_gap_ms':min(((seq[i+1][0]-seq[i][1])/1e6 for i in range(len(seq)-1)),default=None)})
with (out/'provenance.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
res={'status':'provenance_checked_not_final_calibration','source_counts':{k:len(v) for k,v in data.items()},'merged_sources':dict(collections.Counter(x['source'] for x in rows)),'input_hash_unique':len(set(x['input_sha256'] for x in rows)),'errors':errors,'wave_checks':checks,'source_hashes':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()},'limits':['Serial repeats are assembled from main indices 0-15 and a later supplement 16-31; they are not 32 consecutive requests in one independent repeat. Do not claim they satisfy the plan independent-repeat requirement without new runs.','Non-overlapping client waves do not prove server KV cleanup, empty queues, or GPU idle at repeat start.','Input hashes are reconstructed from script and checked, but some inputs repeat across modes/repeats; no claim of independent contents.','Supplement script writes requests.json then fails its unrelated 144-row assertion; recovered requests must be independently audited.']};(out/'audit.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res,indent=2))
