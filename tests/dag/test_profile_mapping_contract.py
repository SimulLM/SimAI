import pytest

from scripts.dag_defense.profile_mapping_contract import (
    MappingContract,
    merge_rope_into_pre_proj,
    phase_code,
)


def test_mapping_contract_is_explicit():
    data = MappingContract().as_dict()
    assert data["rope_policy"] == "merge_into_attn_pre_proj"
    assert data["attention_policy"] == "combined_interval_to_phase_attention"
    assert data["boundary_policy"] == "inclusive_sampler_host_interval"


def test_rope_is_added_once_to_schema_bucket():
    assert merge_rope_into_pre_proj(0.25, 0.05) == (0.30, 0.0)


def test_negative_profile_values_are_rejected():
    with pytest.raises(ValueError):
        merge_rope_into_pre_proj(-0.1, 0.05)


@pytest.mark.parametrize(("phase", "expected"), [("prefill", 0), ("decode", 1)])
def test_phase_code(phase, expected):
    assert phase_code(phase) == expected


def test_unknown_phase_is_rejected():
    with pytest.raises(ValueError):
        phase_code("mixed")
