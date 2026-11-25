"""Pinned public trace acquisition and fractional-microsecond interval analysis."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.dag_finalize.common import digest,read,save

REPOSITORY='https://github.com/deepseek-ai/profile-data'
UNIT_EVIDENCE='https://perfetto.dev/docs/getting-started/other-formats#chrome-json-format'


def download(url):
    request=urllib.request.Request(url,headers={'User-Agent':'SimAI-finalize-reference-audit'})
    with urllib.request.urlopen(request,timeout=180) as response:
        return response.read()


def acquire(output,lock):
    output=Path(output);lock=Path(lock)
    output.mkdir(parents=True,exist_ok=False)
    existing=read(lock) if lock.exists() else None
    if existing:
        commit=existing['commit']
    else:
        commit=json.loads(download('https://api.github.com/repos/deepseek-ai/profile-data/commits/main'))['sha']
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('invalid source commit')
    files={}
    for name in ('README.md','prefill.json','decode.json'):
        url=f'https://raw.githubusercontent.com/deepseek-ai/profile-data/{commit}/{name}'
        path=output/name
        path.write_bytes(download(url))
        files[name]=dict(url=url,sha256=digest(path),bytes=path.stat().st_size)
        if existing and files[name]['sha256']!=existing['files'][name]['sha256']:
            raise ValueError('pinned reference checksum mismatch: '+name)
        print('Fetched',name,files[name]['bytes'],flush=True)
    value=dict(repository=REPOSITORY,commit=commit,files=files,
        unit='us',unit_evidence=UNIT_EVIDENCE,
        scopes=dict(prefill=dict(tp=1,ep=32),decode=dict(tp=1,ep=128)),
        routing='artificially balanced per upstream README',group_policy='one entire trace per group, no kernel-wise split')
    if not existing:save(lock,value)
    save(output/'source.json',value)
    return value


def number(value):
    if isinstance(value,bool):raise ValueError('boolean timing')
    n=Decimal(str(value))
    if not n.is_finite() or n<0:raise ValueError('invalid trace timing')
    return n


def merge(intervals):
    result=[]
    for start,end in sorted(intervals):
        if result and start<=result[-1][1]:result[-1]=(result[-1][0],max(end,result[-1][1]))
        else:result.append((start,end))
    return result


def length(intervals):
    return sum((end-start for start,end in merge(intervals)),Decimal(0))


def overlap(left,right):
    left,right=merge(left),merge(right);i=j=0;total=Decimal(0)
    while i<len(left) and j<len(right):
        total+=max(Decimal(0),min(left[i][1],right[j][1])-max(left[i][0],right[j][0]))
        if left[i][1]<right[j][1]:i+=1
        else:j+=1
    return total


def category(name):
    name=name.lower()
    if 'notify_dispatch' in name or 'internode::dispatch' in name or 'internode::combine' in name:
        return 'ep_kernel'
    if any(x in name for x in ('gemm','flash','rotary','swiglu','layer_norm','mla_metadata')):
        return 'compute_kernel'
    return 'other_kernel'


def analyze(path,*,unit=None,unit_evidence=None):
    path=Path(path)
    if unit!='us' or not unit_evidence:
        raise ValueError('explicit Chrome trace microsecond unit evidence is required')
    data=json.loads(path.read_text(encoding='utf-8'),parse_float=Decimal)
    if not isinstance(data.get('traceEvents'),list):raise ValueError('missing traceEvents')
    lanes=defaultdict(lambda:defaultdict(list));streams=set();categories=Counter();fractional=0;invalid=0;seen=set();duplicates=0
    for event in data['traceEvents']:
        if event.get('ph')!='X' or 'kernel' not in str(event.get('cat','')).lower():continue
        try:
            start=number(event['ts']);duration=number(event['dur'])
        except (ValueError,KeyError):
            invalid+=1;continue
        args=event.get('args',{})
        # Never merge independent ranks/devices into a single unsynchronized clock.
        rank=args.get('rank',data.get('distributedInfo',{}).get('rank','unknown'))
        device=f"{rank}:{event.get('pid','unknown')}:{args.get('device','unknown')}"
        stream=str(args.get('stream',event.get('tid','unknown')))
        name=str(event.get('name',''))
        identity=(device,stream,start,duration,name)
        if identity in seen:duplicates+=1;continue
        seen.add(identity)
        fractional+=int(start!=int(start) or duration!=int(duration))
        kind=category(name);categories[kind]+=1;streams.add((device,stream))
        lanes[device][kind].append((start,start+duration))
    scale=Decimal('0.000001')
    devices={}
    for device,groups in sorted(lanes.items()):
        all_intervals=[v for values in groups.values() for v in values]
        devices[device]=dict(kernel_union_s=float(length(all_intervals)*scale),
            compute_union_s=float(length(groups['compute_kernel'])*scale),
            ep_kernel_union_s=float(length(groups['ep_kernel'])*scale),
            compute_ep_kernel_overlap_s=float(overlap(groups['compute_kernel'],groups['ep_kernel'])*scale),
            observation_window_s=float((max(v[1] for v in all_intervals)-min(v[0] for v in all_intervals))*scale))
    properties=data.get('deviceProperties',[])
    return dict(source_sha256=digest(path),group_id='deepseek_'+path.stem+'_'+digest(path)[:12],raw_unit='us',
        unit_evidence=unit_evidence,conversion_to_s='0.000001',kernel_events=len(seen),fractional_events_preserved=fractional,
        duplicate_events_excluded=duplicates,invalid_events=invalid,categories=dict(categories),streams=len(streams),devices=devices,
        device_properties=[{k:v for k,v in d.items() if k in ('id','name','totalGlobalMem','major','minor')} for d in properties if isinstance(d,dict)],
        metadata_keys=sorted(k for k in data if k!='traceEvents'),
        distributed_info=data.get('distributedInfo'),trace_name=data.get('traceName'),
        admission='behavior_reference' if devices and not invalid else 'blocked',
        numeric_accuracy_status='blocked_missing_matched_independent_prediction_and_identity',
        request_e2e_eligible=False,full_rdma_duration_validated=False,
        reason='GPU kernel/overlap observation only; no inferred request arrival/completion, physical topology or full RDMA completion.')


def analyze_directory(folder,output):
    folder=Path(folder);source=read(folder/'source.json')
    reports={}
    for phase in ('prefill','decode'):
        path=folder/(phase+'.json')
        if digest(path)!=source['files'][path.name]['sha256']:raise ValueError('reference changed')
        reports[phase]=dict(analyze(path,unit=source['unit'],unit_evidence=source['unit_evidence']),declared_scope=source['scopes'][phase])
    result=dict(status='passed' if all(r['devices'] and not r['invalid_events'] for r in reports.values()) else 'failed',
        source_commit=source['commit'],traces=reports,primary_e2e_status='blocked',hardware_accuracy_claim=False)
    save(output,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--lock',type=Path,default=ROOT/'configs/dag/finalize/deepseek-source.json')
    p.add_argument('--analyze-only',action='store_true')
    a=p.parse_args()
    if not a.analyze_only:acquire(a.output,a.lock)
    result=analyze_directory(a.output,a.output/'analysis.json')
    print(json.dumps(dict(status=result['status'],source_commit=result['source_commit'])))
