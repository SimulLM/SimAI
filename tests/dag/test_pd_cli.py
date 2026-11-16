from scripts.dag_phase6.main import original_cli


def test_original_cli_pd_and_no_decode(tmp_path):
    checks = original_cli(tmp_path, scenarios=[
        ("single", 1, 1, 134217728, [(0, 8, 4)]),
        ("no_decode", 1, 1, 134217728, [(0, 8, 1)]),
    ])
    assert all(check["passed"] for check in checks), checks
