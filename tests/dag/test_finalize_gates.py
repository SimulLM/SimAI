"""A component success must not promote missing request E2E evidence."""
import pytest
from scripts.dag_finalize.common import final_exit_status


@pytest.mark.parametrize('functional,accuracy,reproduction,expected',[
    ('passed','blocked_missing_matched_reference','passed',2),
    ('passed','not_improved','passed',2),
    ('passed','passed','not_run',2),
    ('passed','passed','passed',0),
    ('failed','passed','passed',1),
    ('passed','rejected','passed',1),
    ('passed','passed','failed',1)])
def test_final_gate_keeps_reference_and_reproduction_requirements(functional,accuracy,reproduction,expected):
    assert final_exit_status(functional,accuracy,reproduction)==expected
