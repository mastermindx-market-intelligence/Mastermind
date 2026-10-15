"""Compose the two NEW source repairs, never the denied native fixture suite.

This checks one assembled broker-method fragment and synthetic SQLite state.
It does not reconstruct a full broker, acquire a lease, or prove installation.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Tuple
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'ops/native_fabric/routing_audit_20261013'
REQUEST = BUNDLE / 'request_waiters'
ACCOUNT = BUNDLE / 'account_balance'
PATCHES = (REQUEST / 'request_waiters.patch', ACCOUNT / 'normalized_account_balance.patch')


def original_fragment():
    request = (REQUEST / 'reference.py.txt').read_text()
    account = (ACCOUNT / 'reference.py.txt').read_text()
    assert account.startswith('class Broker:\n')
    # Preserve each method's bytes; only the redundant class declaration is omitted.
    return request + '\n' + account.split('\n', 1)[1]


def compose(path, patches=PATCHES):
    (path / 'ext').mkdir(parents=True)
    target = path / 'ext/lease_broker.py'
    target.write_text(original_fragment())
    for patch in patches:
        result = subprocess.run(['git', 'apply', str(patch)], cwd=path,
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    source = target.read_text()
    ast.parse(source)
    return source


def load_broker(source):
    namespace = {'sqlite3': sqlite3, 'Optional': Optional, 'List': List,
                 'Dict': Dict, 'Any': Any, 'Tuple': Tuple, 'uuid': uuid,
                 'CLASS_PRIORITY': {'heal': 0, 'build': 1, 'review': 2, 'mechanical': 3}}
    exec(compile(source, '<combined-broker-method-fragment>', 'exec'), namespace)
    return namespace['Broker'](), namespace['_request_waiter_id']


def database():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
        CREATE TABLE waiters (
            id TEXT PRIMARY KEY, orchestrator_id TEXT NOT NULL, pool TEXT NOT NULL,
            account TEXT, task_class TEXT NOT NULL, host TEXT, enqueued_at REAL NOT NULL,
            priority INTEGER NOT NULL, need INTEGER NOT NULL DEFAULT 1,
            last_heartbeat REAL);
        CREATE TABLE leases (
            id TEXT PRIMARY KEY, orchestrator_id TEXT, pool TEXT, account TEXT,
            model TEXT, state TEXT, granted_at REAL);
    ''')
    return conn


def test_both_patch_orders_produce_identical_combined_source(tmp_path):
    first = compose(tmp_path / 'first')
    second = compose(tmp_path / 'second', patches=PATCHES[::-1])
    assert first == second
    names = [node.name for node in ast.parse(first).body if isinstance(node, ast.ClassDef)]
    assert names == ['Broker']


def test_root_accounting_and_demand_registration_bodies_are_unchanged(tmp_path):
    before = ast.parse(original_fragment())
    after = ast.parse(compose(tmp_path))
    def methods(tree):
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        return {node.name: ast.dump(node, include_attributes=False)
                for node in cls.body if isinstance(node, ast.FunctionDef)}
    old, new = methods(before), methods(after)
    for name in ('_active_orchestrators', 'fair_share', '_register_demand'):
        assert new[name] == old[name], name
    assert len(new) == len(old) + 1  # only the exact-cleanup method is added


@pytest.mark.parametrize('pool', ['minimax', 'glm', 'bailian'])
def test_one_class_combines_fifo_balancing_and_exact_cleanup(tmp_path, pool):
    broker, request_id = load_broker(compose(tmp_path))
    with database() as conn:
        accounts = [{'name': 'small', '_eff_cap': 2}, {'name': 'large', '_eff_cap': 12}]
        broker.provider_name = lambda value: value
        broker.pool_cap = lambda value: 12
        broker.now = lambda: 1000.0
        broker.grantable_accounts = lambda value: accounts
        broker.account_model_cap = lambda p, a, m: None
        broker._fresh_glm_expiring_accounts = lambda names: {}
        broker._account_held = lambda c, p, a: c.execute(
            "SELECT COUNT(*) FROM leases WHERE pool=? AND account=? AND state='held'", (p, a)
        ).fetchone()[0]
        for index, account in enumerate(('small', 'large', 'large')):
            conn.execute('INSERT INTO leases VALUES (?,?,?,?,?,?,?)',
                         (str(index), 'load-owner', pool, account, 'synthetic', 'held', float(index)))
        urgent = request_id('root-a', pool, 'urgent')
        sibling = request_id('root-a', pool, 'sibling')
        for rid, task in ((urgent, 'heal'), (sibling, 'mechanical')):
            broker._enqueue_waiter(conn, rid, 'root-a', pool, None, 'remote-synthetic',
                                   'synthetic-host', job_class=task)
        assert broker._front_of_queue(conn, pool, 'root-a', 'remote-synthetic', 'heal', urgent)
        assert not broker._front_of_queue(conn, pool, 'root-a', 'remote-synthetic', 'mechanical', sibling)
        before = list(conn.iterdump())
        assert broker._pick_account(conn, pool, None, 'synthetic') == 'large'
        assert list(conn.iterdump()) == before  # ranking grants nothing and changes no demand
        broker._clear_acquired_waiter(conn, pool, 'root-a', urgent)
        assert [r['id'] for r in conn.execute('SELECT id FROM waiters')] == [sibling]
        assert broker.fair_share(conn, pool) == 6  # load-owner + root-a, not one root per request
        assert broker._front_of_queue(conn, pool, 'root-a', 'remote-synthetic', 'mechanical', sibling)


def test_preserved_expiry_priority_cannot_widen_host_compatible_accounts(tmp_path):
    broker, _ = load_broker(compose(tmp_path))
    with database() as conn:
        eligible = {'name': 'compatible', '_eff_cap': 2}
        broker.provider_name = lambda value: value
        broker.grantable_accounts = lambda _: [eligible, {'name': 'outside', '_eff_cap': 12}]
        broker.account_model_cap = lambda p, a, m: None
        broker._account_held = lambda c, p, a: 0
        seen = []
        def expiry(names):
            seen.append(names)
            return {n: 100.0 for n in names if n == 'outside'}
        broker._fresh_glm_expiring_accounts = expiry
        assert broker._pick_account(conn, 'glm', None, 'synthetic', [eligible]) == 'compatible'
        assert seen == [{'compatible'}]
        assert broker._pick_account(conn, 'glm', 'outside', 'synthetic', [eligible]) is None


def test_source_and_patch_inputs_match_published_manifests():
    # Exact reviewed component hashes prevent a silently changed reference from
    # presenting a different algorithm as the same source-method proof.
    expected = {
        REQUEST / 'reference.py.txt': 'dbb190daf150ca7de8526a9f63709b584de69eba0d5bb9a471c1761f5692a894',
        REQUEST / 'request_waiters.patch': '5736d880e62658c335ae2a10addf680a868e46b4918483c934a472d8b658281c',
        ACCOUNT / 'reference.py.txt': '4e44ba48ebe43ec28bff4d4ac41ee288288d0dbeb66ec9315fdd4329d03845cd',
        ACCOUNT / 'normalized_account_balance.patch': '13327989d0703cad7a3f966af8f5a90a404a2278b40c3e4ee23f63c930aaf85e',
    }
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
