"""Full protected broker composition for provably full pinned-account waiters."""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import socket
import sys

import pytest

from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, FIXTURES, ROOT, _apply, _module, broker, complete_broker, native_binding,
)


def _methods(source):
    cls = next(n for n in ast.parse(source).body
               if isinstance(n, ast.ClassDef) and n.name == "Broker")
    return {n.name: ast.dump(n, include_attributes=False)
            for n in cls.body if isinstance(n, ast.FunctionDef)}


@pytest.fixture
def eligible_broker(complete_broker, tmp_path, monkeypatch):
    before = _methods(complete_broker._composed_source)
    reference = (ROOT / "tests/fixtures/native_fabric_pinned_waiter_20261015/reference.py.txt").read_text()
    # The fast source-method tests must observe the actual protected composition,
    # not an approximation silently diverging from the full Broker methods.
    for name, shape in _methods(reference).items():
        assert before[name] == shape, name
    ext = tmp_path / "ext"
    ext.mkdir()
    target = ext / "lease_broker.py"
    target.write_text(complete_broker._composed_source)
    _apply(tmp_path, BUNDLE / "pinned_waiters/pinned_account_eligibility.patch")
    after = _methods(target.read_text())
    assert set(after) - set(before) == {"_waiter_pinned_account_full"}
    assert {n for n in before if before[n] != after[n]} == {
        "_front_of_queue", "_below_share_waiters"}
    shutil.copyfile(FIXTURES / "native_broker_admission.py.txt", ext / "native_broker_admission.py")
    def forbidden(*args, **kwargs):
        raise AssertionError("pinned waiter test attempted provider I/O")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    names = ("_pinned_waiter_native_test", "_pinned_waiter_complete_broker_test")
    originals = {name: sys.modules.get(name) for name in names}
    native = _module(names[0], ext / "native_broker_admission.py")
    monkeypatch.setitem(sys.modules, "native_broker_admission", native)
    value = _module(names[1], target)
    yield value
    for name in names:
        if originals[name] is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = originals[name]


def setup_accounts(module, tmp_path):
    return broker(module, tmp_path, [
        {"name": "busy", "per_account_cap": 1},
        {"name": "free", "per_account_cap": 3},
    ])


@pytest.mark.parametrize("same_root", [False, True])
def test_other_account_can_work_without_erasing_blocked_head(eligible_broker, tmp_path, same_root):
    br, _ = setup_accounts(eligible_broker, tmp_path)
    occupied = br.acquire("holder", "minimax", account="busy")
    assert occupied.ok
    waiting_root = "parent" if same_root else "waiting"
    blocked = br.acquire(waiting_root, "minimax", account="busy", job_class="heal", request_id="blocked")
    assert not blocked.ok and blocked.reason == "account_unavailable"
    ready = br.acquire("parent", "minimax", account="free", job_class="review", request_id="ready")
    assert ready.ok and ready.account == "free", ready.reason
    with br._conn() as conn:
        rows = list(conn.execute("SELECT id,account FROM waiters"))
        assert [(r["id"], r["account"]) for r in rows] == [
            (eligible_broker._request_waiter_id(waiting_root, "minimax", "blocked"), "busy")]
    # Reopening capacity restores the original waiter's right to compete.
    assert br.release(occupied.lease_id, "holder")
    next_grant = br.acquire(waiting_root, "minimax", account="busy", job_class="heal", request_id="blocked")
    assert next_grant.ok and next_grant.account == "busy"


def test_proven_full_pin_does_not_freeze_idle_surplus(eligible_broker, tmp_path):
    br, _ = setup_accounts(eligible_broker, tmp_path)
    assert br.acquire("holder", "minimax", account="busy").ok
    assert br.acquire("parent", "minimax", account="free", request_id="initial").ok
    assert not br.acquire("waiting", "minimax", account="busy", job_class="heal", request_id="blocked").ok
    with br._conn() as conn:
        assert br.fair_share(conn, "minimax", extra="parent") == 1
    result = br.acquire("parent", "minimax", account="free", job_class="review", request_id="second")
    assert result.ok and result.state == "rented", result.reason
    with br._conn() as conn:
        assert br.fair_share(conn, "minimax", extra="parent") == 1
        assert len(br._active_leases(conn, "minimax")) == 3


def test_unpinned_waiter_remains_a_real_capacity_contender(eligible_broker, tmp_path):
    br, _ = setup_accounts(eligible_broker, tmp_path)
    held = [br.acquire("holder", "minimax", account=a, request_id=f"seed-{i}")
            for i, a in enumerate(("busy", "free", "free", "free"))]
    assert all(result.ok for result in held)
    assert not br.acquire("waiting", "minimax", job_class="heal", request_id="first").ok
    assert br.release(held[-1].lease_id, "holder")
    result = br.acquire("parent", "minimax", account="free", job_class="review", request_id="second")
    assert not result.ok and result.reason == "priority_wait"


def test_native_uncertain_hold_is_not_released_to_help_another_account(eligible_broker, tmp_path):
    br, clock = setup_accounts(eligible_broker, tmp_path)
    original = {**native_binding(), "account": "busy"}
    native = br.acquire_native_admission(original)
    assert native["state"] == "RETAINED"
    clock[0] += 1000
    br.gc()
    assert br.read_native_admission(original)["reconciliation_required"]
    assert not br.acquire("waiting", "minimax", account="busy", job_class="heal", request_id="blocked").ok
    ready = br.acquire("parent", "minimax", account="free", job_class="review", request_id="ready")
    assert ready.ok
    assert br.release(native["grant"]["lease_id"], "native-root") is False
    assert br.read_native_admission(original)["lease_state"] in ("held", "rented")
