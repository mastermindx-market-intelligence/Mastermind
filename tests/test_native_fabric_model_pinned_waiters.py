"""GLM per-model pinned waiter: synthetic exact-source regression and migration."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest
import yaml

from tests.test_native_fabric_protected_broker_composition import BUNDLE, FIXTURES, _apply, _module, complete_broker
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests.test_native_fabric_quota_pinned_reclaim_composition import joined_candidate
from tests.test_native_fabric_advisory_reset_boundary import advisory_reader
from tests.test_native_fabric_quota_waiter_transition import quota_yield_candidate
from tests.test_native_fabric_pinned_ready_memo import optimized_module

BEFORE = "8195ae4630a4876f929256bf78e74012f7659585d7db375654257df374e10c4c"
AFTER = "4df8e2b56554b0b5ffc98a851bd40ed86d2387ca8f6872c14bf6638f65f5bc3f"


@pytest.fixture
def model_module(optimized_module, tmp_path, monkeypatch):
    original = Path(optimized_module.__file__).read_bytes()
    assert hashlib.sha256(original).hexdigest() == BEFORE
    directory = tmp_path / "model-waiter-source"
    ext = directory / "ext"
    ext.mkdir(parents=True)
    target = ext / "lease_broker.py"
    target.write_bytes(original)
    _apply(directory, BUNDLE / "model_waiters/model_aware_waiters.patch")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == AFTER
    shutil.copyfile(FIXTURES / "native_broker_admission.py.txt",
                    ext / "native_broker_admission.py")
    helper = _module("_model_waiter_native_admission_test",
                     ext / "native_broker_admission.py")
    monkeypatch.setitem(sys.modules, "native_broker_admission", helper)
    module = _module("_model_waiter_composed_test", target)
    yield module


def broker(module, tmp_path, *, model_cap_a=1):
    config = tmp_path / "accounts.yaml"
    config.write_text(yaml.safe_dump({"providers": {"glm": {
        "enabled": True, "accounts": [
            {"name": "a", "per_account_cap": 3, "per_model_caps": {"glm-5.3": model_cap_a}},
            {"name": "b", "per_account_cap": 3, "per_model_caps": {"glm-5.3": 3}},
        ],
    }}}))
    return module.Broker(
        db_path=str(tmp_path / "leases.sqlite"),
        lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config), status_json=str(tmp_path / "status.json"),
        hosts_path=str(tmp_path / "hosts.json"), grok_marker=str(tmp_path / "absent"),
        this_host="synthetic", external_gates=False, check_pid=False,
        now_fn=lambda: 2_000_000_000.0,
    )


def sequence(module, tmp_path):
    br = broker(module, tmp_path)
    seed = br.acquire("seed", "glm", account="a", task_class="review",
                      job_class="review", request_id="seed", model="glm-5.3")
    blocked = br.acquire("waiting", "glm", account="a", task_class="review",
                         job_class="heal", request_id="blocked", model="glm-5.3")
    ready = br.acquire("ready", "glm", account="b", task_class="review",
                       job_class="review", request_id="ready", model="glm-5.3")
    return br, seed, blocked, ready


def test_before_model_only_pinned_waiter_blocks_unrelated_room(optimized_module, tmp_path):
    br, seed, blocked, ready = sequence(optimized_module, tmp_path)
    assert seed.ok and blocked.reason == "account_unavailable"
    assert not ready.ok and ready.reason == "priority_wait"
    with br._conn() as conn:
        assert br._account_held(conn, "glm", "b") == 0
        assert "model" not in {row[1] for row in conn.execute("PRAGMA table_info(waiters)")}


def test_model_only_waiter_yields_without_erasing_or_rerouting(model_module, tmp_path):
    br, seed, blocked, ready = sequence(model_module, tmp_path)
    assert seed.ok and blocked.reason == "account_unavailable"
    assert ready.ok and ready.account == "b"
    with br._conn() as conn:
        rows = list(conn.execute("SELECT account,model FROM waiters WHERE orchestrator_id='waiting'"))
        assert len(rows) == 1 and rows[0]["account"] == "a" and rows[0]["model"] == "glm-5.3"
    assert br.release(seed.lease_id, "seed")
    resumed = br.acquire("waiting", "glm", account="a", task_class="review",
                         job_class="heal", request_id="blocked", model="glm-5.3")
    assert resumed.ok and resumed.account == "a"


def test_unobserved_model_cap_keeps_unknown_demand_blocking(model_module, tmp_path):
    br = broker(model_module, tmp_path)
    with br._conn() as conn:
        wid = model_module._request_waiter_id("waiting", "glm", "unobserved")
        br._enqueue_waiter(conn, wid, "waiting", "glm", "a", "review",
                           "synthetic", job_class="heal", model="unknown-model")
    ready = br.acquire("ready", "glm", account="b", task_class="review",
                       job_class="review", request_id="ready", model="glm-5.3")
    assert not ready.ok and ready.reason == "priority_wait"


def test_known_zero_model_allowance_does_not_block_other_account(model_module, tmp_path):
    br = broker(model_module, tmp_path, model_cap_a=0)
    refused = br.acquire("waiting", "glm", account="a", task_class="review",
                         job_class="heal", request_id="zero", model="glm-5.3")
    assert refused.reason == "account_unavailable"
    ready = br.acquire("ready", "glm", account="b", task_class="review",
                       job_class="review", request_id="ready", model="glm-5.3")
    assert ready.ok


def test_request_model_change_requeues_at_same_clock_tick(model_module, tmp_path):
    br = broker(model_module, tmp_path)
    one = model_module._request_waiter_id("parent", "glm", "one")
    two = model_module._request_waiter_id("parent", "glm", "two")
    with br._conn() as conn:
        for rid in (one, two):
            br._enqueue_waiter(conn, rid, "parent", "glm", "a", "review",
                               "synthetic", job_class="review", model="glm-5.3")
        older = {row["id"]: row["rowid"] for row in conn.execute("SELECT rowid,id FROM waiters")}
        br._enqueue_waiter(conn, one, "parent", "glm", "a", "review",
                           "synthetic", job_class="review", model="glm-5.3-flash")
        newer = {row["id"]: row["rowid"] for row in conn.execute("SELECT rowid,id FROM waiters")}
        assert older[one] < older[two] < newer[one]
        assert conn.execute("SELECT model FROM waiters WHERE id=?", (one,)).fetchone()["model"] == "glm-5.3-flash"
        assert br.fair_share(conn, "glm") >= 1


def test_legacy_waiter_migration_preserves_unknown_model_priority(optimized_module, model_module, tmp_path):
    # Use the unchanged broker to create a historical demand in another synthetic database.
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    original = broker(optimized_module, legacy_dir)
    with original._conn() as conn:
        original._enqueue_waiter(conn, None, "old-root", "glm", "a", "review",
                                 "synthetic", job_class="heal")
    # Instantiating the current candidate on the original database migrates only
    # the waiter column. Existing unmapped demand remains a priority contender.
    new = model_module.Broker(
        db_path=original.db_path, lock_path=original.lock_path,
        accounts_path=original.accounts_path, status_json=original.status_json,
        hosts_path=original.hosts_path, grok_marker=original.grok_marker,
        this_host="synthetic", external_gates=False, check_pid=False,
        now_fn=lambda: 2_000_000_000.0)
    with new._conn() as conn:
        row = conn.execute("SELECT model FROM waiters WHERE orchestrator_id='old-root'").fetchone()
        assert row["model"] == ""
    later = new.acquire("ready", "glm", account="b", task_class="review",
                        job_class="review", request_id="ready", model="glm-5.3")
    assert later.reason == "priority_wait"


def test_native_and_root_accounting_methods_unchanged(optimized_module, model_module):
    def methods(source):
        node = next(n for n in ast.parse(Path(source.__file__).read_text()).body
                    if isinstance(n, ast.ClassDef) and n.name == "Broker")
        return {n.name: ast.dump(n, include_attributes=False)
                for n in node.body if isinstance(n, ast.FunctionDef)}
    prior, current = methods(optimized_module), methods(model_module)
    for name in ("_active_orchestrators", "fair_share", "_gc_locked",
                 "release", "heartbeat", "_active_leases", "_account_model_held",
                 "_pick_account"):
        assert current[name] == prior[name], name
    assert set(current) - set(prior) == {"_waiter_pinned_model_full"}
    assert {name for name in prior if prior[name] != current[name]} == {
        "_init_db", "_ensure_schema", "_enqueue_waiter", "_register_demand",
        "_try_acquire", "_waiter_skips_ready_queue", "_front_of_queue",
        "_below_share_waiters",
    }


def test_native_retained_model_capacity_is_not_released_to_help_other_account(
    model_module, tmp_path
):
    # An original native grant on a model-saturated account may make a waiter
    # yield in the READY queue, but never grants ordinary release authority.
    from tests.test_native_fabric_protected_broker_composition import native_binding
    br = broker(model_module, tmp_path)
    binding = {**native_binding(),
               "pool": "glm", "account": "a", "model": "glm-5.3",
               "host": "synthetic", "task_class": "review"}
    original = br.acquire_native_admission(binding)
    assert original["state"] == "RETAINED"
    lid = original["grant"]["lease_id"]
    blocked = br.acquire("waiting", "glm", account="a", task_class="review",
                         job_class="heal", request_id="blocked", model="glm-5.3")
    ready = br.acquire("ready", "glm", account="b", task_class="review",
                       job_class="review", request_id="ready", model="glm-5.3")
    assert blocked.reason == "account_unavailable" and ready.ok
    assert br.release(lid, "native-root") is False
    with br._conn() as conn:
        row = conn.execute("SELECT state,native_key FROM leases WHERE id=?", (lid,)).fetchone()
        assert row["state"] in ("held", "rented") and row["native_key"]
    assert br.read_native_admission(binding)["state"] == "RETAINED"
