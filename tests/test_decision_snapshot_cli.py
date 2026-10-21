"""Exercise the actual read-only CLI in an isolated, source-identical fixture."""
from importlib import util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from test_decision_snapshot import sealed, snapshots


@pytest.fixture
def cli_repo(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    assert (root / 'scripts/portfolio_decision_snapshot.py').is_file(), 'missing snapshot inspector CLI'
    for package in ('scripts', 'portfolio', 'control_plane'):
        (tmp_path / package).mkdir()
        (tmp_path / package / '__init__.py').write_text('')
    for name in ('scripts/portfolio_decision_snapshot.py', 'portfolio/decision_snapshot.py',
                 'portfolio/decision_snapshot_contracts.py', 'control_plane/wake_events.py'):
        shutil.copyfile(root / name, tmp_path / name)
    monkeypatch.setattr(snapshots(), '_ROOT', tmp_path)
    return tmp_path


def run_cli(root, *args):
    return subprocess.run([sys.executable, '-B', '-m', 'scripts.portfolio_decision_snapshot', *args],
        cwd=root, env={'PATH': os.defpath, 'PYTHONPATH': str(root), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=15)


def file_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_status_on_empty_store_is_absent_and_read_only(cli_repo):
    before = file_bytes(cli_repo); result = run_cli(cli_repo, 'status')
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body['status'] == 'ABSENT' and body['snapshot'] is None
    assert file_bytes(cli_repo) == before


def test_show_exact_snapshot_and_section_without_mutation(cli_repo):
    p = sealed(); snapshots().persist_snapshot(p); before = file_bytes(cli_repo)
    result = run_cli(cli_repo, 'show', '--snapshot-id', p['snapshot_id'], '--section', 'book_truth', '--limit', '1')
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body['snapshot']['snapshot_id'] == p['snapshot_id']
    assert body['section']['rows'][0]['cash'] == 1000000.0
    assert file_bytes(cli_repo) == before


@pytest.mark.parametrize('args', [
    ['compose'], ['status', '--book', 'self_directed'], ['show', '--snapshot-id', '../../private'],
    ['show', '--section', 'private_file'], ['show', '--limit', '101'], ['show', '--offset', '-1'],
    ['show', '--path', '/private/secret'], ['show', '--root', '/tmp/foreign'],
])
def test_cli_refuses_invalid_or_write_requests_without_io(cli_repo, args):
    before = file_bytes(cli_repo); result = run_cli(cli_repo, *args)
    assert result.returncode == 2
    body = json.loads(result.stdout)
    assert body['error'] == 'INVALID_REQUEST'
    assert '/private' not in result.stdout and '/tmp/foreign' not in result.stdout
    assert file_bytes(cli_repo) == before


def test_missing_snapshot_has_stable_error_without_path_disclosure(cli_repo):
    result = run_cli(cli_repo, 'show', '--snapshot-id', 'sha256:' + 'f' * 64)
    assert result.returncode == 3
    assert json.loads(result.stdout)['error'] == 'SNAPSHOT_NOT_FOUND'
    assert str(cli_repo) not in result.stdout


def test_corrupt_snapshot_is_not_reported_as_absent(cli_repo):
    p = sealed(); r = snapshots().persist_snapshot(p); Path(r['path']).write_text('{}')
    result = run_cli(cli_repo, 'status')
    assert result.returncode == 4
    assert json.loads(result.stdout)['error'] == 'SNAPSHOT_CORRUPT'


def test_importing_cli_has_no_filesystem_model_or_network_effect(tmp_path, monkeypatch):
    name = 'scripts.portfolio_decision_snapshot'
    assert util.find_spec(name) is not None, 'missing snapshot inspector CLI'
    import builtins
    import socket
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('network opened during import'))
    monkeypatch.setattr(builtins, 'open', lambda *a, **k: pytest.fail('data file opened during import'))
    __import__(name)
