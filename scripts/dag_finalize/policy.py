"""Reuse frozen phase-8 workload definitions under the finalization result root."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.dag_finalize.execution import command
from scripts.dag_finalize.common import result_path


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--family',choices=('original','expanded','holdout'),required=True);a=p.parse_args()
    out=result_path(a.output);out.mkdir(parents=True,exist_ok=False)
    spec={'original':'mechanism-experiment','expanded':'mechanism-expanded','holdout':'mechanism-fcfs-holdout'}[a.family]
    for policy in ('submission','fcfs'):
        command(out,policy,[sys.executable,ROOT/'scripts/dag_phase8/mechanism_experiment.py','--spec',ROOT/f'configs/dag/finalize/{spec}.json',
            '--ready-queue-policy',policy,'--output',out/policy],accepted=(0,2) if policy=='submission' else (0,))
    command(out,'comparison',[sys.executable,ROOT/'scripts/dag_phase8/queue_policy_comparison.py','--before-run',out/'submission','--after-run',out/'fcfs','--output',out/'comparison'])
