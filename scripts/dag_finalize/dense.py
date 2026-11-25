"""Replay the already frozen TP calibration without refitting validation data."""
import io
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.dag_finalize.common import digest,read,save
from scripts.dag_phase4.main import hashes

ARCHIVE=ROOT/'docs/dag/phase8/artifacts/20261118-phase8-simulated-reference.zip'
PREFIX='results/dag/phase8/20261118-simulated-reference-01/'


def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    expected={line.split()[1]:line.split()[0] for line in (ARCHIVE.parent/'SHA256SUMS').read_text(encoding='utf-8').splitlines()}
    if digest(ARCHIVE)!=expected[ARCHIVE.name]:raise ValueError('frozen calibration archive changed')
    with zipfile.ZipFile(ARCHIVE) as z:
        manifest=json.loads(z.read(PREFIX+'run-manifest.json'))
        for name in z.namelist():
            if not name.startswith(PREFIX):continue
            rel=name[len(PREFIX):]
            if not (rel.startswith(('inputs/','profiles/')) or rel in ('experiment.json','calibration.json')):continue
            payload=z.read(name)
            from hashlib import sha256
            if manifest['artifact_sha256'].get(rel)!=sha256(payload).hexdigest():raise ValueError('frozen fixture checksum mismatch: '+rel)
            path=output/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
    save(output/'frozen-calibration-provenance.json',dict(archive=ARCHIVE.relative_to(ROOT).as_posix(),archive_sha256=digest(ARCHIVE),
        calibration_sha256=digest(output/'calibration.json'),action='Reuse existing offset and scope; no fit in this run.'))
    files={p for name in ('inputs','profiles') for p in (output/name).rglob('*') if p.is_file()}
    files.add(output/'experiment.json')
    save(output/'experiment-freeze.json',dict(status='frozen_historical_inputs_before_new_backend_execution',primary_metric='request_e2e',
        input_sha256=hashes(output,files),specification_sha256=digest(output/'experiment.json')))
    return output/'calibration.json'


def score(output,backend):
    from scripts.dag_phase8.simulated_reference import run_experiment
    output=Path(output);calibration=output/'calibration.json';frozen=digest(calibration)
    code=run_experiment(output,Path(backend),frozen_calibration=calibration)
    # The legacy library returns a CLI exit code, not its JSON report.
    if code!=0:raise RuntimeError('controlled dense experiment failed: '+str(code))
    report=read(output/'simulation-report.json')
    if report['status']!='passed' or report['calibration_refitted'] or digest(calibration)!=frozen:
        raise ValueError('dense report or frozen calibration failed verification')
    return report
