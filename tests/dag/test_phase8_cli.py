from scripts.dag_phase4.main import synthetic_profiles
from scripts.dag_phase8.joint import run_case


def test_original_cli_joint_prefill_transfer_and_decode(tmp_path):
    profiles = tmp_path / "profiles"
    synthetic_profiles(profiles)
    result = run_case(tmp_path, profiles, "joint", [(0, 8, 2)])
    assert result["passed"], result["checks"]
    assert result["routing_count"] > 0 and result["peak_rss_bytes"] > 0
