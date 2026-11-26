"""Compare layer-16 events against matching candidate layer component fields."""
import collections,csv,json,pathlib,re,statistics,sys
real=pathlib.Path(sys.argv[1]);ref=pathlib.Path(sys.argv[2]);cost=pathlib.Path(sys.argv[3]);out=pathlib.Path(sys.argv[4]);out.mkdir(parents=True,exist_ok=False)
a=json.loads(ref.read_text());rid=a['router']['decode_id']+'-0';events=[]
for file in (real/'service').glob('compute-events-*.jsonl'):
 for line in file.read_text().splitlines():
  e=json.loads(line)
  if rid in e.get('request_ids_to_seq_ids',{}) and e.get('query_lens')==[1]:events.append(e)
events.sort(key=lambda x:x['host_start_ns']);assert len(events)==63 and [e['seq_lens'] for e in events]==[[x] for x in range(513,576)]
table=collections.defaultdict(dict)
with cost.open() as f:
 for r in csv.DictReader(f):
  if r['layer']=='16' and r['op'] in ('attention.compute','mlp.compute') and r['graph_id'].startswith('replica1/'):
   m=re.fullmatch(r'replica1/stage0/batch(\d+)/iteration(\d+)',r['graph_id']);assert m and m.group(1)==m.group(2);i=int(m.group(1));assert r['op'] not in table[i];table[i][r['op']]=json.loads(r['metadata'])['components']
assert set(table)==set(range(1,64));rows=[]
for i,e in enumerate(events,1):
 g=e['gpu_event_ms'];att=table[i]['attention.compute'];mlp=table[i]['mlp.compute']
 pairs={'input_norm':(g['input_layernorm'],att['attn_norm_time']),'pre_projection_plus_rope':(g['attn_pre_proj']+g['attn_rope'],att['attention_pre_proj_time']+att['attention_rope_execution_time']),'attention_combined':(g['attention_combined'],att['attention_decode_execution_time']+att['attention_kv_cache_save_execution_time']),'post_projection':(g['attn_post_proj'],att['attention_post_proj_time']),'post_norm':(g['post_attention_layernorm'],mlp['mlp_norm_time']),'mlp_up':(g['mlp_up_proj'],mlp['mlp_layer_up_proj_execution_time']),'mlp_activation':(g['mlp_act'],mlp['mlp_layer_act_execution_time']),'mlp_down':(g['mlp_down_proj'],mlp['mlp_layer_down_proj_execution_time'])}
 for name,(observed,predicted) in pairs.items():rows.append({'iteration':i,'context_tokens':e['seq_lens'][0],'component':name,'observed_layer16_gpu_ms':observed,'simulated_layer_ms':predicted,'difference_ms':predicted-observed})
with (out/'components.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary=[]
for component in sorted({x['component'] for x in rows}):
 group=[x for x in rows if x['component']==component];summary.append({'component':component,'steps':len(group),'observed_median_ms':statistics.median(x['observed_layer16_gpu_ms'] for x in group),'simulated_median_ms':statistics.median(x['simulated_layer_ms'] for x in group),'paired_difference_median_ms':statistics.median(x['difference_ms'] for x in group)})
result={'status':'one_request_layer16_diagnostic','input_sha256':a['input_sha256'],'components':summary,'limitations':['Layer 16 only; cannot extrapolate its difference to all 32 layers without evidence','63 steps from one request are correlated, not independent measurements','Observed CUDA event intervals and candidate medians are from different instrumented sessions and timing scopes may overlap','Paired medians are not additive and cannot directly explain total E2E difference','No formal validation data or completion times were used to choose costs']};(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
