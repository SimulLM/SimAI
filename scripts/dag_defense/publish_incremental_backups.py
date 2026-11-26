"""Back up completed immutable replay artifacts to the single task branch/Release.

Runs on Windows against a loopback SSH tunnel. Credentials are obtained from the
existing Git credential manager in memory, never printed or written to disk.
"""
import argparse,hashlib,json,pathlib,subprocess,time,urllib.request,urllib.error
from concurrent.futures import ThreadPoolExecutor

REPO='https://api.github.com/repos/SimulLM/SimAI'
TAG='dev-formal-predictions-20261127'
BRANCH='dev-h800-pd-measurement'
DOC=pathlib.Path('docs/dag_defense/environment/diagnostics/formal-validation-20261127/incremental')
RAW=pathlib.Path('results/dag_defense/formal-validation-20261127/incremental')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args,**kw):return subprocess.run(['git',*args],check=True,capture_output=True,text=True,**kw)
def token():
    x=git('credential','fill',input='protocol=https\nhost=github.com\n\n')
    return dict(line.split('=',1) for line in x.stdout.splitlines() if '=' in line)['password']
def api(url,method='GET',body=None,binary=False):
    headers={'Authorization':'Bearer '+token(),'Accept':'application/vnd.github+json','User-Agent':'SimAI-incremental-backup'}
    if body is not None:headers['Content-Type']='application/octet-stream' if binary else 'application/json'
    data=body if binary else json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=180) as r:return json.load(r)
    except urllib.error.HTTPError as e:raise RuntimeError('GitHub HTTP '+str(e.code)) from None
def release():
    try:return api(REPO+'/releases/tags/'+TAG)
    except RuntimeError as e:
        if str(e)!='GitHub HTTP 404':raise
    return api(REPO+'/releases','POST',{'tag_name':TAG,'target_commitish':BRANCH,'name':'Formal prediction evidence: incremental parts','prerelease':True,'draft':False,'body':'Immutable completed replay evidence, partitioned into three rounds per asset. Score CSVs and SHA256 manifests are incrementally committed to dev-h800-pd-measurement. Partial results do not establish the complete validation conclusion. Full 30-round raw GPU collection is separately backed up in dev-formal-raw-30rounds-20261127. No model weights or credentials.'})
def download(base,entry,target):
    if target.exists() and sha(target)==entry['sha256']:return
    target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_suffix(target.suffix+'.partial')
    with urllib.request.urlopen(base+'/'+entry['path'],timeout=120) as source,temp.open('wb') as dest:
        while True:
            chunk=source.read(1024*1024)
            if not chunk:break
            dest.write(chunk)
    if temp.stat().st_size!=entry['bytes'] or sha(temp)!=entry['sha256']:raise ValueError('backup checksum mismatch '+target.name)
    temp.replace(target)
def publish(base,once=False):
    DOC.mkdir(parents=True,exist_ok=True);RAW.mkdir(parents=True,exist_ok=True)
    rel=release();uploaded={a['name']:a for a in api(REPO+'/releases/'+str(rel['id'])+'/assets')}
    seen=set();deadline=time.monotonic()+4*3600
    while time.monotonic()<deadline:
        with urllib.request.urlopen(base+'/incremental-backup-20261127/index.json',timeout=20) as r:index=json.load(r)
        jobs=[]
        for run in index['runs']:
            for entry in run['files']:jobs.append((entry,DOC/run['run_id']/entry['name']))
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda item:download(base,*item),jobs))
        new={r['run_id'] for r in index['runs']}-seen
        # Push compact results before waiting on large evidence transfers.
        if new:
            (DOC/'backup-index.json').write_text(json.dumps(index,indent=2)+'\n')
            git('add','--',str(DOC))
            if subprocess.run(['git','diff','--cached','--quiet']).returncode:
                git('commit','-m','Back up completed formal replay results (%d/30)'%len(index['runs']))
            git('push','origin','HEAD:'+BRANCH);seen.update(new)
            print(json.dumps({'event':'scores_pushed','completed_rounds':len(index['runs']),'commit':git('rev-parse','HEAD').stdout.strip()}),flush=True)
        for entry in sorted(index['archives'],key=lambda e:e['bytes']):
            if entry['name'] in uploaded:
                if uploaded[entry['name']]['size']!=entry['bytes']:raise ValueError('existing Release asset size differs')
                continue
            target=RAW/entry['name'];print(json.dumps({'event':'downloading_evidence','name':entry['name'],'bytes':entry['bytes']}),flush=True)
            download(base,entry,target)
            asset=api(rel['upload_url'].split('{')[0]+'?name='+entry['name'],'POST',target.read_bytes(),True)
            if asset['size']!=entry['bytes']:raise ValueError('uploaded size mismatch')
            uploaded[entry['name']]=asset
            (DOC/(entry['name']+'.json')).write_text(json.dumps(dict(entry,asset_url=asset['browser_download_url'],release=rel['html_url'],local_sha256_verified=True),indent=2)+'\n')
            git('add','--',str(DOC));git('commit','-m','Archive '+entry['name']+' with verified SHA256');git('push','origin','HEAD:'+BRANCH)
            print(json.dumps({'event':'evidence_uploaded','name':entry['name'],'asset':asset['browser_download_url']}),flush=True)
        if index['status']=='complete' and len(uploaded)>=10:
            print(json.dumps({'event':'all_30_rounds_backed_up','release':rel['html_url']}),flush=True);return
        if once:return
        time.sleep(30)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:18489');p.add_argument('--once',action='store_true');a=p.parse_args();publish(a.base,a.once)
