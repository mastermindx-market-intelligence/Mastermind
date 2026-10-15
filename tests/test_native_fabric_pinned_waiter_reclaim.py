"""Pinned-account bypass must preserve original-root surplus reclamation.

Runs the published complete broker in temporary SQLite only. These are scheduling
regressions, not provider execution, installation or native owner enrollment.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import shutil
import sys

import pytest

from tests.test_native_fabric_pinned_waiter_composition import eligible_broker
from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, FIXTURES, _apply, _module, broker, complete_broker,
)
from tests import test_native_fabric_pinned_waiter_composition as existing


@pytest.fixture
def reclaim_broker(eligible_broker, tmp_path):
    root = tmp_path / "reclaim-source"
    ext = root / "ext"
    ext.mkdir(parents=True)
    target = ext / "lease_broker.py"
    source = Path(eligible_broker.__file__).read_bytes()
    target.write_bytes(source)
    shutil.copyfile(FIXTURES / "native_broker_admission.py.txt", ext / "native_broker_admission.py")
    if os.environ.get("FABRIC_PINNED_RECLAIM_PREIMAGE") != "1":
        _apply(root, BUNDLE / "pinned_waiters/pinned_account_reclaim.patch")
    name = "_fabric_pinned_reclaim_broker_test"
    previous = sys.modules.get(name)
    try:
        value = _module(name, target)
        value._before_reclaim_source = source.decode()
        value._after_reclaim_source = target.read_text()
        yield value
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def seed_full_account(module, tmp_path):
    br, clock = broker(module, tmp_path, [
        {"name": "busy", "per_account_cap": 3},
        {"name": "free", "per_account_cap": 1},
    ])
    held = [br.acquire("holder", "minimax", account="busy", request_id=f"seed-{i}")
            for i in range(3)]
    assert all(result.ok for result in held)
    blocked = br.acquire("waiting", "minimax", account="busy",
                         job_class="heal", request_id="blocked")
    assert not blocked.ok and blocked.reason == "account_unavailable"
    return br, clock, held


def test_full_pinned_demand_still_marks_excess_leases_for_reclaim(reclaim_broker, tmp_path):
    br, _, held = seed_full_account(reclaim_broker, tmp_path)
    with br._conn() as conn:
        assert br.fair_share(conn, "minimax") == 2
        rows = br._held_by(conn, "holder", "minimax")
        assert len(rows) == 3
        assert sum(row["renewable"] == 0 for row in rows) == 1
        assert all(row["state"] in ("held", "rented") for row in rows)
        assert conn.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 1


def test_ready_other_account_does_not_rearm_pinned_account_surplus(reclaim_broker, tmp_path):
    br, _, _ = seed_full_account(reclaim_broker, tmp_path)
    ready = br.acquire("ready", "minimax", account="free", job_class="review",
                       request_id="ready-work")
    assert ready.ok and ready.account == "free"
    with br._conn() as conn:
        assert br.fair_share(conn, "minimax") == 1
        rows = br._held_by(conn, "holder", "minimax")
        assert sum(row["renewable"] == 0 for row in rows) >= 1
        assert conn.execute("SELECT COUNT(*) FROM waiters WHERE orchestrator_id='waiting'").fetchone()[0] == 1


def test_heartbeat_cannot_extend_borrowed_surplus_past_its_granted_step(reclaim_broker, tmp_path):
    br, clock, held = seed_full_account(reclaim_broker, tmp_path)
    clock[0] += 80
    for result in held:
        assert br.heartbeat(result.lease_id)
    blocked = br.acquire("waiting", "minimax", account="busy",
                         job_class="heal", request_id="blocked")
    assert not blocked.ok
    clock[0] += 80
    for result in held:
        assert br.heartbeat(result.lease_id)
    assert not br.acquire("waiting", "minimax", account="busy",
                          job_class="heal", request_id="blocked").ok
    clock[0] += 21
    # The most recently refreshed original step is still inside heartbeat TTL,
    # but a surplus step must respect its original absolute grant boundary.
    reclaimed = br.acquire("waiting", "minimax", account="busy",
                           job_class="heal", request_id="blocked")
    assert reclaimed.ok, reclaimed.reason
    with br._conn() as conn:
        assert len(br._active_leases(conn, "minimax")) == 3
        assert len(br._held_by(conn, "holder", "minimax")) == 2
        assert not list(conn.execute("SELECT * FROM waiters WHERE orchestrator_id='waiting'"))


@pytest.mark.parametrize("same_root", [False, True])
def test_existing_ready_account_and_waiter_retention_contract(reclaim_broker, tmp_path, same_root):
    existing.test_other_account_can_work_without_erasing_blocked_head(reclaim_broker, tmp_path, same_root)


@pytest.mark.parametrize("case", [
    existing.test_proven_full_pin_does_not_freeze_idle_surplus,
    existing.test_unpinned_waiter_remains_a_real_capacity_contender,
    existing.test_native_uncertain_hold_is_not_released_to_help_another_account,
])
def test_existing_borrowing_priority_and_native_hold_contract(reclaim_broker, tmp_path, case):
    case(reclaim_broker, tmp_path)


def test_eligibility_and_reclamation_have_distinct_demand_views(reclaim_broker, tmp_path):
    br, _, _ = seed_full_account(reclaim_broker, tmp_path)
    with br._conn() as conn:
        share = br.fair_share(conn, "minimax")
        assert br._below_share_waiters(conn, "minimax", "", share) == []
        demand = br._below_share_waiters(conn, "minimax", "", share, include_full_pins=True)
        assert len(demand) == 1 and demand[0]["orchestrator_id"] == "waiting"
        assert br._below_share_waiters(conn, "minimax", "waiting", share, include_full_pins=True) == []


def test_many_pinned_siblings_keep_original_root_denominator(reclaim_broker, tmp_path):
    br, _, _ = seed_full_account(reclaim_broker, tmp_path)
    for index in range(5):
        assert not br.acquire("waiting", "minimax", account="busy", job_class="heal",
                              request_id=f"blocked-sibling-{index}").ok
    with br._conn() as conn:
        assert br.fair_share(conn, "minimax") == 2
        assert len(br._below_share_waiters(conn, "minimax", "", 2, include_full_pins=True)) == 6
        assert sum(row["renewable"] == 0 for row in br._held_by(conn, "holder", "minimax")) == 1


def test_only_reclamation_callers_and_demand_view_change(reclaim_broker):
    def methods(source):
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "Broker")
        return {n.name: ast.dump(n, include_attributes=False) for n in cls.body if isinstance(n, ast.FunctionDef)}
    before = methods(reclaim_broker._before_reclaim_source)
    after = methods(reclaim_broker._after_reclaim_source)
    assert set(before) == set(after)
    assert {name for name in before if before[name] != after[name]} == {
        "_below_share_waiters", "_register_demand", "_try_acquire"}
    for name in ("_waiter_pinned_account_full", "_front_of_queue", "_mark_surplus_nonrenewable",
                 "_gc_locked", "_ensure_schema", "release", "heartbeat", "fair_share", "_pick_account"):
        assert before[name] == after[name], name
