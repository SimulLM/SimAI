"""Strict output admission and short, owned pytest temporary directories."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOTS = (ROOT / 'results/dag/phase8', ROOT / 'results/dag/finalize')


class FinalizationParser(argparse.ArgumentParser):
    def error(self,message):
        self.print_usage()
        self.exit(1,self.prog+': error: '+message+'\n')


def final_exit_status(functional,accuracy,reproduction):
    if functional!='passed' or accuracy=='rejected' or reproduction=='failed':return 1
    return 0 if accuracy=='passed' and reproduction=='passed' else 2


def result_path(path):
    value = (ROOT / path).resolve()
    if not any(value != root and value.is_relative_to(root) for root in RESULT_ROOTS):
        raise ValueError('output must be a child of results/dag/phase8 or results/dag/finalize')
    return value


def validate_pytest_temp(explicit):
    cache = (ROOT / '.cache').resolve()
    if not cache.is_relative_to(ROOT.resolve()):raise ValueError('project cache resolves outside workspace')
    value = (ROOT / explicit).resolve()
    if value == cache or not value.is_relative_to(cache):
        raise ValueError('pytest basetemp must be a new directory below project .cache')
    if value.exists():raise FileExistsError('pytest basetemp already exists; no existing directory will be deleted: '+str(value))
    return value


def allocate_pytest_temp(explicit=None):
    cache = (ROOT / '.cache').resolve()
    if explicit is not None:
        value = validate_pytest_temp(explicit)
        value.parent.mkdir(parents=True, exist_ok=True)
        value.mkdir(exist_ok=False)
        return value
    parent = (cache / 'p8t').resolve()
    if not parent.is_relative_to(cache):raise ValueError('short temp root resolves outside project cache')
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix='', dir=parent))


def digest(path):
    h = sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def read(path):
    def invalid(value):
        raise ValueError('nonfinite JSON: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=invalid)
