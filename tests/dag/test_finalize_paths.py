"""Protect result boundaries and caller-owned files while fixing MAX_PATH."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import pytest
from scripts.dag_finalize import common


def test_default_temp_is_short_exclusive_and_independent_of_output():
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths=list(pool.map(lambda _:common.allocate_pytest_temp(),range(2)))
    assert paths[0]!=paths[1]
    assert all(p.is_dir() and p.parent==common.ROOT/'.cache/p8t' for p in paths)


def test_explicit_existing_temp_is_never_deleted():
    path=common.allocate_pytest_temp()
    marker=path/'caller.txt';marker.write_text('keep',encoding='utf-8')
    with pytest.raises(FileExistsError):common.allocate_pytest_temp(path)
    assert marker.read_text(encoding='utf-8')=='keep'


def test_unicode_explicit_cache_path():
    path=common.ROOT/'.cache'/('收尾-'+uuid4().hex[:8])
    assert common.allocate_pytest_temp(path)==path.resolve()


@pytest.mark.parametrize('path',['../escape','results/dag/finalize/run','.cache/../tests','.cache'])
def test_reject_unsafe_temp_paths(path):
    with pytest.raises(ValueError):common.allocate_pytest_temp(path)


@pytest.mark.parametrize('path',['results/dag/phase8/x','results/dag/finalize/x'])
def test_only_explicit_result_roots_are_admitted(path):
    assert common.result_path(path)==(common.ROOT/path).resolve()


@pytest.mark.parametrize('path',['results/dag','results/dag/phase8','results/dag/finalize','results/dag/finalize/../../other','outside'])
def test_result_root_escape_rejected(path):
    with pytest.raises(ValueError):common.result_path(path)


def test_operation_failure_is_not_converted_to_success(tmp_path):
    import sys
    from scripts.dag_finalize.execution import command
    with pytest.raises(RuntimeError,match='failed: 7'):
        command(tmp_path,'failure',[sys.executable,'-c','raise SystemExit(7)'])
    assert common.read(tmp_path/'operations/failure/process-result.json')['exit_code']==7
