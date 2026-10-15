"""Memoize account-only readiness per locked scan, never across lease grants.

Exact existing full broker/reader join plus a bounded source patch; synthetic
SQLite, no provider calls, installed host or native process effects.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from tests.test_native_fabric_protected_broker_composition import BUNDLE, _apply, _module, complete_broker
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests.test_native_fabric_quota_pinned_reclaim_composition import joined_candidate
from tests.test_native_fabric_advisory_reset_boundary import advisory_reader
from tests.test_native_fabric_quota_waiter_transition import quota_yield_candidate

BEFORE_SHA = "72fd13153e81349a76acae001ecc38e860f30cf055cdb2ba42411fbe209aa4d5"
AFTER_SHA = "8195ae4630a4876f929256bf78e74012f7659585d7db375654257df374e10c4c"


@pytest.fixture
def optimized_module(quota_yield_candidate, tmp_path, monkeypatch):
    source_module, reader = quota_yield_candidate
    before = Path(source_module.__file__).read_bytes()
    assert hashlib.sha256(before).hexdigest() == BEFORE_SHA
    root = tmp_path / "ready-memo-source"
    (root / "ext").mkdir(parents=True)
    target = root / "ext/lease_broker.py"
    target.write_bytes(before)
    _apply(root, BUNDLE / "pinned_waiters/pinned_ready_memo.patch")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == AFTER_SHA
    monkeypatch.setitem(sys.modules, "quota_remote", reader)
    name = "_fabric_ready_queue_memo_test"
    previous = sys.modules.get(name)
    try:
        module = _module(name, target)
        yield module
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


@pytest.fixture
def broker(optimized_module, tmp_path):
    config = tmp_path / "accounts.yaml"
    config.write_text(json.dumps({"providers": {"minimax": {"enabled": True,
        "accounts": [{"name": "busy", "per_account_cap": 1000},
                     {"name": "other", "per_account_cap": 1000}]}}}))
    return optimized_module.Broker(
        db_path=str(tmp_path / "leases.sqlite"), lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config), status_json=str(tmp_path / "status.json"),
        hosts_path=str(tmp_path / "hosts.json"), grok_marker=str(tmp_path / "absent"),
        now_fn=lambda: 2_000_000_000., check_pid=False, external_gates=False,
        this_host="synthetic")


def register(conn, number, pin):
    for i in range(number):
        conn.execute("INSERT INTO waiters "
                     "(id, orchestrator_id, pool, account, task_class, host, "
                     "enqueued_at, priority, need, last_heartbeat) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (f"rq-{i:04d}", f"root-{i}", "minimax", pin, "review",
                      "synthetic", float(i), 2, 1, 2_000_000_000.))
    conn.commit()


@pytest.mark.parametrize("operation", ["front", "below"])
def test_readiness_observed_once_per_account_not_per_waiter(broker, monkeypatch, operation):
    calls = {"full": 0, "quota": 0}
    def full(*_):
        calls["full"] += 1
        return False
    def quota(*_):
        calls["quota"] += 1
        return False
    monkeypatch.setattr(broker, "_waiter_pinned_account_full", full)
    monkeypatch.setattr(broker, "_waiter_pinned_quota_parked", quota)
    with broker._conn() as conn:
        register(conn, 96, "busy")
        if operation == "front":
            assert broker._front_of_queue(conn, "minimax", "late-root", "heal", job_class="heal")
        else:
            assert len(broker._below_share_waiters(conn, "minimax", "", share=1)) == 96
    assert calls == {"full": 1, "quota": 1}, calls


def test_distinct_accounts_receive_distinct_readiness_decisions(broker, monkeypatch):
    calls = []
    def full(conn, pool, waiter):
        calls.append(waiter["account"])
        return waiter["account"] == "busy"
    monkeypatch.setattr(broker, "_waiter_pinned_account_full", full)
    monkeypatch.setattr(broker, "_waiter_pinned_quota_parked", lambda *args: False)
    with broker._conn() as conn:
        register(conn, 48, "busy")
        for i in range(48, 96):
            conn.execute("INSERT INTO waiters "
                         "(id, orchestrator_id, pool, account, task_class, host, "
                         "enqueued_at, priority, need, last_heartbeat) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"rq-{i:04d}", f"root-{i}", "minimax", "other", "review",
                          "synthetic", float(i), 2, 1, 2_000_000_000.))
        conn.commit()
        assert not broker._front_of_queue(conn, "minimax", "late-root", "review", job_class="review")
    assert calls == ["busy", "other"], calls


def test_quota_only_skip_is_observed_once_for_shared_pin(broker, monkeypatch):
    calls = {"quota": 0}
    monkeypatch.setattr(broker, "_waiter_pinned_account_full", lambda *args: False)
    def quota(*args):
        calls["quota"] += 1
        return True
    monkeypatch.setattr(broker, "_waiter_pinned_quota_parked", quota)
    with broker._conn() as conn:
        register(conn, 96, "busy")
        assert broker._front_of_queue(conn, "minimax", "late-root", "review", job_class="review")
        assert broker._below_share_waiters(conn, "minimax", "", 1) == []
    # Independent locked decisions each assess the account exactly once.
    assert calls == {"quota": 2}


def test_no_cross_arbitration_cache_after_account_state_changes(broker, monkeypatch):
    state = {"full": True, "observed": 0}
    def full(*args):
        state["observed"] += 1
        return state["full"]
    monkeypatch.setattr(broker, "_waiter_pinned_account_full", full)
    monkeypatch.setattr(broker, "_waiter_pinned_quota_parked", lambda *args: False)
    with broker._conn() as conn:
        register(conn, 96, "busy")
        assert broker._front_of_queue(conn, "minimax", "late-root", "review", job_class="review")
        state["full"] = False
        assert not broker._front_of_queue(conn, "minimax", "late-root", "review", job_class="review")
    assert state["observed"] == 2


def test_full_pin_yields_other_account_without_losing_own_place(optimized_module, tmp_path):
    config = tmp_path / "accounts.yaml"
    config.write_text(json.dumps({"providers": {"minimax": {"enabled": True,
        "accounts": [{"name": "busy", "per_account_cap": 1},
                     {"name": "other", "per_account_cap": 3}]}}}))
    br = optimized_module.Broker(
        db_path=str(tmp_path / "leases.sqlite"), lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config), status_json=str(tmp_path / "status.json"),
        hosts_path=str(tmp_path / "hosts.json"), grok_marker=str(tmp_path / "absent"),
        now_fn=lambda: 2_000_000_000., check_pid=False, external_gates=False,
        this_host="synthetic")
    holder = br.acquire("holder", "minimax", account="busy", request_id="held")
    assert holder.ok
    waiting = br.acquire("waiting", "minimax", account="busy", job_class="heal", request_id="blocked")
    assert not waiting.ok
    ready = br.acquire("ready", "minimax", account="other", job_class="review", request_id="ready")
    assert ready.ok and ready.account == "other"
    with br._conn() as conn:
        assert len(list(conn.execute("SELECT id FROM waiters WHERE orchestrator_id='waiting'"))) == 1
    assert br.release(holder.lease_id, "holder")
    resumed = br.acquire("waiting", "minimax", account="busy", job_class="heal", request_id="blocked")
    assert resumed.ok and resumed.account == "busy"


def test_reclaim_view_never_invokes_ready_pin_predicate(broker, monkeypatch):
    def forbidden(*args):
        raise AssertionError("reclaim must inspect all demand")
    monkeypatch.setattr(broker, "_waiter_pinned_account_full", forbidden)
    monkeypatch.setattr(broker, "_waiter_pinned_quota_parked", forbidden)
    with broker._conn() as conn:
        register(conn, 96, "busy")
        assert len(broker._below_share_waiters(conn, "minimax", "", 1,
                   include_full_pins=True)) == 96
