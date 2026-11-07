"""Read-only original operator binding, using inert private broker fixtures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m
    spec.loader.exec_module(m); return m


@pytest.fixture
def env(tmp_path, monkeypatch):
    source = Path(os.environ['OPERATOR_BINDING_CANDIDATE'])
    x = Path(os.environ['FABRIC_INSTALLED_EXT'])
    monkeypatch.syspath_prepend(str(x))
    d = load('artifact_delivery', source / 'artifact_delivery.py')
    o = load('fabric_operator_owner', source / 'fabric_operator_owner.py')
    monkeypatch.setattr(d, 'HERE', tmp_path)
    b = tmp_path / 'broker'; b.mkdir()
    (b / 'leases.lock').write_bytes(b'')
    db = b / 'leases.sqlite'
    fields = dict(root='original-root', lease_id='old-lease', pool='glm-frontier', model='glm-5.3',
                  account='account-one', host='ubuntu2', support_sha256='a' * 64, packet_sha256='b' * 64)
    grant = dict(fields, schema='mastermind.fabric_operator_grant.v1', operator_run='original-run',
                 expires_at=1, child_budget=2)
    launch = dict(fields, run_id='original-run', task_class='domain_orchestration')
    with sqlite3.connect(db) as con:
        con.execute('CREATE TABLE operator_grants(operator_run TEXT PRIMARY KEY,root TEXT,token_digest TEXT,grant_json TEXT,launch_json TEXT)')
        con.execute('INSERT INTO operator_grants VALUES(?,?,?,?,?)',
                    ('original-run', 'original-root', 'NEVER_RETURN_THIS_TOKEN_DIGEST', json.dumps(grant), json.dumps(launch)))
        con.execute('CREATE TABLE leases(id TEXT,orchestrator_id TEXT,host TEXT,account TEXT,model TEXT,state TEXT,pool TEXT)')
        con.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,?)',
                    ('old-lease', 'original-root', 'ubuntu2', 'account-one', 'glm-5.3', 'rented', 'glm-frontier'))
    owner = o.OperatorOwner(here=tmp_path)
    monkeypatch.setattr(owner, 'transaction', lambda: pytest.fail('live mutating transaction reached'))
    monkeypatch.setattr(owner, '_authorized', lambda *a: pytest.fail('bearer authorization reached'))
    monkeypatch.setattr(owner, '_schema', lambda *a: pytest.fail('schema mutation reached'))
    return owner, d, db, grant, launch


def test_expired_original_grant_is_historical_only_and_db_unchanged(env):
    owner, d, db, grant, launch = env
    before = db.read_bytes()
    result = owner.original_delivery_binding('original-run', root='original-root')
    assert result['packet_sha256'] == 'b' * 64 and not result['current_authority']
    assert result['parent_binding'] == 'NOT_RECORDED_IN_OPERATOR_GRANT'
    assert result['lease_settlement'] == result['children_settlement'] == 'UNKNOWN'
    assert 'token' not in json.dumps(result) and 'expires_at' not in result
    assert db.read_bytes() == before and not list(db.parent.glob('leases.sqlite-*'))
    assert d.retained_lease('old-lease', include_pool=True)['pool'] == 'glm-frontier'
    assert db.read_bytes() == before


@pytest.mark.parametrize('run,root', [('other','original-root'), ('original-run','other')])
def test_absent_or_wrong_identity_does_not_mutate(env, run, root):
    owner, d, db, grant, launch = env
    before = db.read_bytes()
    with pytest.raises(ValueError, match='unavailable'):
        owner.original_delivery_binding(run, root=root)
    assert db.read_bytes() == before


@pytest.mark.parametrize('key,value', [('root','wrong'), ('packet_sha256','c' * 64),
    ('host','ubuntu1'), ('task_class','build')])
def test_conflicting_launch_refuses(env, key, value):
    owner, d, db, grant, launch = env
    launch[key] = value
    with sqlite3.connect(db) as con: con.execute('UPDATE operator_grants SET launch_json=?', (json.dumps(launch),))
    with pytest.raises(ValueError, match='mismatch'):
        owner.original_delivery_binding('original-run', root='original-root')


def test_duplicate_json_key_refuses(env):
    owner, d, db, grant, launch = env
    raw = json.dumps(grant)[:-1] + ',"root":"other"}'
    with sqlite3.connect(db) as con: con.execute('UPDATE operator_grants SET grant_json=?', (raw,))
    with pytest.raises(ValueError): owner.original_delivery_binding('original-run', root='original-root')


@pytest.mark.parametrize('suffix', ['-wal', '-journal'])
def test_live_sidecar_preserves_existing_refusal(env, suffix):
    owner, d, db, grant, launch = env
    Path(str(db) + suffix).write_bytes(b'held')
    with pytest.raises(ValueError, match='live_sidecar'):
        owner.original_delivery_binding('original-run', root='original-root')


def test_snapshot_query_only_blocks_writes(env):
    owner, d, db, grant, launch = env
    before = db.read_bytes()
    with pytest.raises(sqlite3.OperationalError):
        d._retained_broker_row('DELETE FROM operator_grants', (), here=db.parent.parent)
    assert db.read_bytes() == before
