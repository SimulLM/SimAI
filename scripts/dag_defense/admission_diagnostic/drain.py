"""Fence new requests and wait for active ASGI handlers; not backend idle proof."""
import argparse,json,pathlib,time,urllib.request
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18300/_diagnostic/admission');p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--timeout',type=float,default=30);a=p.parse_args()
if a.output.exists():raise FileExistsError(a.output)
def query(action):
 req=urllib.request.Request(a.url,data=json.dumps({'action':action}).encode(),headers={'Content-Type':'application/json'});return json.load(urllib.request.urlopen(req,timeout=3))
start=time.monotonic();rows=[query('fence')]
while rows[-1]['active'] and time.monotonic()-start<a.timeout:
 time.sleep(.2);rows.append(query('status'))
result={'status':'drained_asgi_only' if rows[-1]['fenced'] and rows[-1]['active']==0 and rows[-1]['accepted']==rows[-1]['finished'] else 'not_drained','observations':rows,'limitations':['does not establish backend/connector idle or cancellation cleanup','one router process only','formal readiness is not granted']};a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='drained_asgi_only' else 2)
