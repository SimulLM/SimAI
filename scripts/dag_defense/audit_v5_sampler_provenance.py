"""Verify v5 sampler source values and flag its inclusive boundary."""
import csv,hashlib,json,math,pathlib,sys
profile=pathlib.Path(sys.argv[1]);source=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with (profile/'cpu.csv').open() as f:target=list(csv.DictReader(f))
with source.open() as f:rows=list(csv.DictReader(f))
select=[r for r in rows if r['event']=='sampler_synchronized'];lookup={(r['phase'],r['input_tokens'],r['actual_batch']):r for r in select};assert len(lookup)==len(select)==17 and len(target)==17
checks=[]
for t in target:
 key=(t['phase'],t['input_tokens'],t['batch_size']);r=lookup[key];actual=float(t['sampler_e2e_median']);measured=float(r['median_ms']);assert math.isclose(actual,measured,rel_tol=0,abs_tol=1e-12);assert int(r['warmups_seen'])>=10 and int(r['eligible_samples'])>=30
 checks.append({'phase':key[0],'input_tokens':int(key[1]),'batch_size':int(key[2]),'samples':int(r['eligible_samples']),'profile_ms':actual,'source_ms':measured})
manifest=json.loads((profile/'profile-manifest.json').read_text());assert str(source) in manifest['source_files'];recorded=manifest['source_sha256'].get(str(source));assert recorded is None
result={'status':'source_values_verified_manifest_hash_missing','profile_cpu_sha256':sha(profile/'cpu.csv'),'manifest_sha256':sha(profile/'profile-manifest.json'),'sampler_source_path':str(source),'sampler_source_sha256':sha(source),'rows_verified':len(checks),'checks':checks,'limitations':['Source sampler timer encloses device synchronization and sampler host call, including GPU work and waiting; it is an inclusive interval rather than pure CPU','Layer compute profile excludes logits and sampler, but scheduling and CPU overlap remain unproven','Matching values and source hash do not validate extrapolation, first-token or concurrent semantics','Historical manifest is not mutated; this audit records the missing source digest separately']}
(out/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
