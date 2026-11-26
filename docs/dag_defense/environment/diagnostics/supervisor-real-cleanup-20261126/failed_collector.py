import pathlib,subprocess,sys,time
p=pathlib.Path(__file__).parent
result=subprocess.run([sys.executable,str(p/'client.py'),str(p/'client.json'),str(p/'service/router-events.jsonl')]);print('cancellation client exit',result.returncode,flush=True)
if result.returncode:raise SystemExit(3)
time.sleep(.5)
raise SystemExit(1)
