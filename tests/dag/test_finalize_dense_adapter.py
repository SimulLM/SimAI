"""Honor the reused experiment's integer return contract and frozen fees."""
import pytest
from scripts.dag_finalize.common import save
from scripts.dag_finalize.dense import score


def test_legacy_integer_success_is_adapted_to_saved_report(tmp_path,monkeypatch):
    import scripts.dag_phase8.simulated_reference as library
    save(tmp_path/'calibration.json',dict(frozen=1))
    def legacy(output,backend,frozen_calibration):
        assert frozen_calibration==tmp_path/'calibration.json'
        save(output/'simulation-report.json',dict(status='passed',calibration_refitted=False))
        return 0
    monkeypatch.setattr(library,'run_experiment',legacy)
    assert score(tmp_path,tmp_path/'backend')['status']=='passed'


@pytest.mark.parametrize('exit_code',[1,2])
def test_legacy_failure_cannot_be_hidden_by_successful_looking_json(tmp_path,monkeypatch,exit_code):
    import scripts.dag_phase8.simulated_reference as library
    save(tmp_path/'calibration.json',dict(frozen=1))
    save(tmp_path/'simulation-report.json',dict(status='passed',calibration_refitted=False))
    monkeypatch.setattr(library,'run_experiment',lambda *a,**k:exit_code)
    with pytest.raises(RuntimeError):score(tmp_path,tmp_path/'backend')


def test_frozen_calibration_mutation_is_rejected(tmp_path,monkeypatch):
    import scripts.dag_phase8.simulated_reference as library
    save(tmp_path/'calibration.json',dict(frozen=1))
    def mutated(output,backend,**kwargs):
        save(output/'calibration.json',dict(frozen=2))
        save(output/'simulation-report.json',dict(status='passed',calibration_refitted=False))
        return 0
    monkeypatch.setattr(library,'run_experiment',mutated)
    with pytest.raises(ValueError):score(tmp_path,tmp_path/'backend')
