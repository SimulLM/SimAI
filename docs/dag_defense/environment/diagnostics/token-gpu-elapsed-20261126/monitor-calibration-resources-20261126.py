import time,json,subprocess,sys,pathlib
p=pathlib.Path(sys.argv[1]);f=p.open('w')
while True:
 start=time.monotonic_ns(); row={'monotonic_before_ns':start,'wall_ns':time.time_ns()}
 try:
  row['cpu_stat']=pathlib.Path('/sys/fs/cgroup/cpu.stat').read_text();row['gpu']=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,clocks.sm,power.draw,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=4).stdout;row['monotonic_after_ns']=time.monotonic_ns();f.write(json.dumps(row,separators=(',',':'))+'\n');f.flush()
 except Exception as e:f.write(json.dumps({'error':repr(e),'monotonic_ns':time.monotonic_ns()})+'\n');f.flush()
 time.sleep(.5)
