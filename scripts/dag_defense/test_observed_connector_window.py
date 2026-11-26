"""Exercise the checker against captured observations and adverse variants."""
import json,pathlib,tarfile,tempfile
from scripts.dag_defense.check_observed_connector_window import check
ARCHIVE=pathlib.Path(__file__).resolve().parents[2]/'docs/dag_defense/environment/diagnostics/pipe-observer-concurrent-20261126/raw.tar.gz'
PREFIX='pipe-observer-concurrent-20261126/'
def test_captured_and_missing_stale_or_busy_states():
 with tempfile.TemporaryDirectory() as directory:
  root=pathlib.Path(directory);obs=root/'observer';obs.mkdir();probe=root/'probe.jsonl'
  with tarfile.open(ARCHIVE) as archive:
   for item in archive:
    if not item.isfile():continue
    if item.name==PREFIX+'probe/observations.jsonl':dest=probe
    elif item.name.startswith(PREFIX+'observer/') and item.name.endswith('.jsonl'):dest=obs/pathlib.PurePosixPath(item.name).name
    else:continue
    dest.write_bytes(archive.extractfile(item).read())
  original=probe.read_bytes()
  result=check(probe,obs,4,1.5,15);assert result['status']=='host_observations_consistent_gpu_unverified'
  samples=[json.loads(x) for x in probe.read_text().splitlines()];samples[0]['router']['inflight']=1;probe.write_text(''.join(json.dumps(x)+'\n' for x in samples))
  try:check(probe,obs,4,1.5,15)
  except AssertionError:pass
  else:raise AssertionError('busy router accepted')
  probe.write_bytes(original)
  try:check(probe,obs,5,1.5,15)
  except AssertionError:pass
  else:raise AssertionError('wrong expected count accepted')
  try:check(probe,obs,4,0.000000001,15)
  except AssertionError:pass
  else:raise AssertionError('stale observer accepted')
  next(obs.glob('producer-*.jsonl')).unlink()
  try:check(probe,obs,4,1.5,15)
  except AssertionError:pass
  else:raise AssertionError('missing observer accepted')
