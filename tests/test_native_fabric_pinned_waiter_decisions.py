"""Actual pinned-account patch on source-backed decision methods.

The complete-broker test separately checks these reference methods against the
composed protected source. No account, provider or native host is contacted.
"""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
from typing import List, Optional
import subprocess
import tempfile
import pytest

PRIORITY = {"heal": 0, "build": 1, "review": 2, "mechanical": 3}
ns = {"sqlite3": sqlite3, "List": List, "Optional": Optional,
      "_class_priority": lambda tc, jc=None: PRIORITY.get(jc or tc, 4)}
ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests/fixtures/native_fabric_pinned_waiter_20261015/reference.py.txt"
PATCH = ROOT / "ops/native_fabric/routing_audit_20261013/pinned_waiters/pinned_account_eligibility.patch"
with tempfile.TemporaryDirectory(prefix="pinned-waiter-source-") as work:
    source_root = Path(work)
    (source_root / "ext").mkdir()
    target = source_root / "ext/lease_broker.py"
    target.write_bytes(REFERENCE.read_bytes())
    if os.environ.get("FABRIC_PINNED_TEST_PREIMAGE") != "1":
        applied = subprocess.run(["git", "apply", str(PATCH)], cwd=source_root,
                                 capture_output=True, text=True, check=False)
        assert applied.returncode == 0, applied.stderr
    source = target.read_text()
exec(compile(source, "<source-backed-methods>", "exec"), ns)
Broker = ns["Broker"]


def make(tmp_path, account="a", held=1, cap=1, request_root="waiting"):
    conn = sqlite3.connect(tmp_path/"test.sqlite")
    conn.row_factory=sqlite3.Row
    conn.execute("CREATE TABLE leases (account TEXT, orchestrator_id TEXT, pool TEXT)")
    for _ in range(held):
        conn.execute("INSERT INTO leases VALUES (?,?,?)", ("a","holder","synthetic"))
    conn.commit()
    row={"id":"rq-other","orchestrator_id":request_root,"account":account,"priority":0}
    br=Broker()
    br._waiters=lambda *_: [row]
    br.grantable_accounts=lambda _: [{"name":"a","_eff_cap":cap},{"name":"b","_eff_cap":5}]
    br._account_held=lambda c,p,a: c.execute("SELECT COUNT(*) FROM leases WHERE pool=? AND account=?",(p,a)).fetchone()[0]
    br._held_by=lambda c,o,p: list(c.execute("SELECT * FROM leases WHERE pool=? AND orchestrator_id=?",(p,o)))
    return br,conn,row


@pytest.mark.parametrize("root",["waiting","parent"])
def test_full_pinned_head_does_not_block_ready_request(tmp_path, root):
    br,c,_=make(tmp_path,request_root=root)
    assert br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")


def test_full_pin_does_not_claim_idle_account_share(tmp_path):
    br,c,_=make(tmp_path)
    assert br._below_share_waiters(c,"synthetic","parent",1)==[]


def test_becomes_contender_again_when_capacity_frees(tmp_path):
    br,c,_=make(tmp_path)
    assert br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")
    c.execute("DELETE FROM leases")
    assert not br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")
    assert len(br._below_share_waiters(c,"synthetic","parent",1))==1


@pytest.mark.parametrize("account,held,cap",[(None,1,1),("a",0,1),("missing",1,1),("a",1,0),("a",1,True),("a",1,1.5)])
def test_unknown_or_available_demand_keeps_priority(tmp_path,account,held,cap):
    br,c,_=make(tmp_path,account=account,held=held,cap=cap)
    assert not br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")
    assert len(br._below_share_waiters(c,"synthetic","parent",1))==1


@pytest.mark.parametrize("exc", [ValueError, OSError, ImportError, sqlite3.DatabaseError])
def test_observation_failure_preserves_blocking(tmp_path,exc):
    br,c,_=make(tmp_path)
    def broken(_):raise exc("synthetic observation unavailable")
    br.grantable_accounts=broken
    assert not br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")
    assert len(br._below_share_waiters(c,"synthetic","parent",1))==1


def test_account_observation_is_pool_scoped(tmp_path):
    br,c,_=make(tmp_path)
    c.execute("UPDATE leases SET pool='other'")
    assert not br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")


def test_eligibility_check_does_not_mutate_rows(tmp_path):
    br,c,row=make(tmp_path)
    before=list(c.execute("SELECT * FROM leases")); original=dict(row)
    br._front_of_queue(c,"synthetic","parent","review",waiter_id="rq-new")
    br._below_share_waiters(c,"synthetic","parent",1)
    assert list(c.execute("SELECT * FROM leases"))==before and row==original
