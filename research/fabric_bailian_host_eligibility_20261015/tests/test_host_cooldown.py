"""Synthetic host cooldown admission; no provider, real slot or transport access."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest
from test_host_account_composition import stage, module, envelope, broker, acquire


def observe(stage, tmp_path, marker=None, kind='file'):
    probe = module(stage, 'glm_host_account_probe')
    command = probe.build_probe('h1', 'h1-ssh', ['Kris', 'Ryan'],
        (stage/'bailian_keys.py').read_bytes(), mode='qwen')
    words = shlex.split(shlex.split(command)[-1]); i = words.index('python3')
    home = tmp_path/'synthetic-home'; (home/'.bailian').mkdir(parents=True)
    (home/'.bailian/config.json').write_text(json.dumps({'token-plan': {'api_keys': [
        {'name': 'Kris', 'api_key': 'SYNTHETIC_CREDENTIAL'},
        {'name': 'Ryan', 'api_key': 'SYNTHETIC_CREDENTIAL'}]}}))
    slot = home/'lanes/ext/slots/bailian/Kris.cooldown'
    if marker is not None:
        slot.parent.mkdir(parents=True)
        if kind == 'directory': slot.mkdir()
        elif kind == 'symlink':
            target = home/'marker'; target.write_text(marker); slot.symlink_to(target)
        else: slot.write_text(marker)
    before = {str(p.relative_to(home)): (p.lstat().st_mode, p.lstat().st_mtime_ns,
        p.read_bytes() if p.is_file() and not p.is_symlink() else None)
        for p in home.rglob('*')}
    proc = subprocess.run([sys.executable, '-c', words[i+2], words[i+3]],
        env={'HOME': str(home), 'PATH': os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=5)
    assert proc.returncode == 0, proc.stderr
    assert 'SYNTHETIC_CREDENTIAL' not in proc.stdout + proc.stderr
    assert 'access_denied' not in proc.stdout + proc.stderr
    after = {str(p.relative_to(home)): (p.lstat().st_mode, p.lstat().st_mtime_ns,
        p.read_bytes() if p.is_file() and not p.is_symlink() else None)
        for p in home.rglob('*')}
    assert before == after
    return json.loads(proc.stdout.split('=', 1)[1])


@pytest.mark.parametrize('marker,expected', [
    ('future access_denied', False), ('future quota_or_insufficient', False),
    ('future http_429', True), ('past access_denied', True),
    ('invalid timestamp', None), ('', None), ('future', False), (None, True),
])
def test_host_cooldown_filters_configured_account_without_mutation(stage, tmp_path, marker, expected):
    if marker is not None:
        marker = marker.replace('future', str(int(time.time()) + 3600)).replace('past', '1')
    got = observe(stage, tmp_path, marker)
    assert got['status'] == 'known'
    assert got['accounts'] == {'Kris': expected, 'Ryan': True}
    assert got['cooldown_checked'] is True


@pytest.mark.parametrize('kind', ['symlink', 'directory'])
def test_unsafe_marker_is_unknown_without_affecting_other_account(stage, tmp_path, kind):
    got = observe(stage, tmp_path, '1 access_denied', kind)
    assert got['accounts'] == {'Kris': None, 'Ryan': True}


@pytest.mark.parametrize('checked', [None, False, 'true', 1])
def test_legacy_config_only_observation_cannot_grant_qwen(stage, broker, checked):
    _, br = broker
    path = stage/'state/hosts/h1.json'; doc = json.loads(path.read_text())
    doc['bailian_local_account_readiness']['cooldown_checked'] = checked
    path.write_text(json.dumps(doc))
    got = acquire(br)
    assert not got.ok and got.reason == 'host_account_unavailable'
    with br._conn() as con:
        assert con.execute('select count(*) from leases').fetchone()[0] == 0
        assert con.execute('select count(*) from waiters').fetchone()[0] == 0


def test_broker_uses_actual_host_cooldown_even_when_controller_has_none(stage, broker, tmp_path):
    _, br = broker
    got = observe(stage, tmp_path, str(int(time.time()) + 3600) + ' access_denied')
    got['observed_at'] = 1000
    path = stage/'state/hosts/h1.json'; doc = json.loads(path.read_text())
    doc['bailian_local_account_readiness'] = got
    path.write_text(json.dumps(doc))
    result = acquire(br)
    assert result.ok and result.account == 'Ryan'
