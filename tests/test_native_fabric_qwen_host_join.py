"""Protect installed #1512 Qwen host/account admission inside native-routing join.

All grants are synthetic SQLite with no host, provider, credential or live
lease effects. Current #1443 model-waiter assembly is a source-only fixture.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import shutil
import socket
import sys
import types

import pytest
import yaml

# Make the whole composed fixture ancestry visible when pytest runs this module
# in an independent CI shard. Imported functions alone do not expose their
# nested fixtures to this module's fixture namespace.
from tests.test_native_fabric_protected_broker_composition import complete_broker
from tests.test_native_fabric_quota_admission_composition import current_candidate
from tests.test_native_fabric_advisory_reset_boundary import advisory_reader
from tests.test_native_fabric_quota_pinned_reclaim_composition import joined_candidate
from tests.test_native_fabric_quota_waiter_transition import quota_yield_candidate
from tests.test_native_fabric_pinned_ready_memo import optimized_module
from tests.test_native_fabric_model_pinned_waiters import model_module
from tests.test_native_fabric_protected_broker_composition import (
    BUNDLE, FIXTURES, _apply, _module,
)

MODEL_JOIN_PREIMAGE = "4df8e2b56554b0b5ffc98a851bd40ed86d2387ca8f6872c14bf6638f65f5bc3f"


@pytest.fixture
def qwen_module(model_module, tmp_path, monkeypatch):
    original = Path(model_module.__file__).read_bytes()
    assert hashlib.sha256(original).hexdigest() == MODEL_JOIN_PREIMAGE
    # Upstream joined_candidate uses tmp_path/ext. Keep this dependent
    # composition in its own working root so pytest can run the full
    # fixture chain in one isolated CI shard without colliding directories.
    stage = tmp_path / "qwen-host-join"
    ext = stage / "ext"
    ext.mkdir(parents=True)
    target = ext / "lease_broker.py"
    target.write_bytes(original)
    _apply(stage, BUNDLE / "qwen_compat/qwen_host_after_model_waiters.patch")
    modified = target.read_bytes()
    assert modified != original

    def methods(source):
        node = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.ClassDef) and n.name == "Broker")
        return {n.name: ast.dump(n, include_attributes=False)
                for n in node.body if isinstance(n, ast.FunctionDef)}
    before, after = methods(original), methods(modified)
    assert before.keys() == after.keys()
    assert [name for name in before if before[name] != after[name]] == ["_try_acquire"]
    for protected in ("_ensure_schema", "_gc_locked", "_pick_account",
                      "heartbeat", "release", "fair_share", "_active_orchestrators"):
        assert before[protected] == after[protected]
    shutil.copyfile(FIXTURES / "native_broker_admission.py.txt",
                    ext / "native_broker_admission.py")
    helper_name, name = "_qwen_join_native", "_qwen_join_broker"
    old = {k: sys.modules.get(k) for k in (helper_name, name)}
    try:
        helper = _module(helper_name, ext / "native_broker_admission.py")
        monkeypatch.setitem(sys.modules, "native_broker_admission", helper)
        result = _module(name, target)
        yield result
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


@pytest.fixture
def rig(qwen_module, tmp_path, monkeypatch):
    config = tmp_path / "accounts.yaml"
    config.write_text(yaml.safe_dump({"providers": {
        "bailian": {"enabled": True, "accounts": [
            {"name": "a", "per_account_cap": 2},
            {"name": "b", "per_account_cap": 2},
        ]},
        "glm": {"enabled": True, "accounts": [
            {"name": "glm-a", "per_account_cap": 2},
        ]},
    }}))
    br = qwen_module.Broker(
        db_path=str(tmp_path / "leases.sqlite"),
        lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config),
        status_json=str(tmp_path / "status.json"),
        hosts_path=str(tmp_path / "hosts.json"),
        grok_marker=str(tmp_path / "not-exhausted"),
        this_host="synthetic", now_fn=lambda: 2_000_000_000.0,
        external_gates=False, check_pid=False,
    )
    eligible = {"a": False, "b": True, "glm-a": True}
    calls = []

    def observed(accounts, *, host, model, now, preferred, hosts_path, mode="glm"):
        calls.append((mode, host, model, preferred,
                      tuple(a["name"] for a in accounts)))
        accepted = [a for a in accounts if eligible.get(a["name"])]
        if preferred is not None:
            accepted = [a for a in accepted if a["name"] == preferred]
        return accepted, {"source": "synthetic_closed_observation"}

    monkeypatch.setitem(sys.modules, "glm_host_account_source",
                        types.SimpleNamespace(filter_observed_accounts=observed))
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Qwen compatibility test attempted provider network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    return br, eligible, calls


def qwen(br, *, account=None, task_class="remote-qwen", root="original-root"):
    return br.acquire(root, "bailian", account=account,
                      task_class=task_class, job_class="review",
                      request_id="stable-qwen-child", model="qwen3.8-flash",
                      host="ubuntu1", wait=0)


def test_unknown_pinned_host_account_refuses_without_waiter_or_lease(rig):
    br, _, calls = rig
    refused = qwen(br, account="a")
    assert not refused.ok and refused.reason == "host_account_unavailable"
    assert calls and calls[-1][:4] == ("qwen", "ubuntu1", "qwen3.8-flash", "a")
    with br._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 0


def test_unpinned_qwen_can_only_use_host_qualified_account(rig):
    br, _, calls = rig
    granted = qwen(br)
    assert granted.ok and granted.account == "b", granted.reason
    assert calls[-1][:3] == ("qwen", "ubuntu1", "qwen3.8-flash")
    with br._conn() as conn:
        row = conn.execute("SELECT * FROM leases WHERE id=?",
                           (granted.lease_id,)).fetchone()
        assert row["orchestrator_id"] == "original-root"
        assert row["task_class"] == "remote-qwen"
        assert row["native_key"] is None
    assert br.release(granted.lease_id, "original-root")


def test_qualified_explicit_account_remains_pinned(rig):
    br, _, calls = rig
    granted = qwen(br, account="b")
    assert granted.ok and granted.account == "b"
    assert calls[-1][3] == "b"


def test_observation_refusal_does_not_enqueue_unknown_host_demand(rig):
    br, eligible, _ = rig
    eligible["b"] = False
    refused = qwen(br, account="b")
    assert refused.reason == "host_account_unavailable"
    with br._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 0


def test_non_remote_qwen_class_keeps_incumbent_bailian_behavior(rig):
    br, _, calls = rig
    granted = qwen(br, task_class="review")
    assert granted.ok and granted.account == "a"
    assert calls == []


def test_glm_pairing_and_native_signature_remain_intact(rig, qwen_module):
    br, _, calls = rig
    result = br.acquire("glm-root", "glm", account="glm-a",
                        task_class="remote-glm", job_class="review",
                        request_id="glm-child", model="glm-5.3",
                        host="ubuntu1")
    assert result.ok and result.account == "glm-a"
    assert calls[-1][:4] == ("glm", "ubuntu1", "glm-5.3", "glm-a")
    import inspect
    assert "native_binding" in inspect.signature(qwen_module.Broker._try_acquire).parameters
    assert "request_id" in inspect.signature(qwen_module.Broker.acquire).parameters


def test_source_only_baseline_still_lacks_qwen_join(model_module):
    # This is the frozen baseline for the source-compatibility regression,
    # not a permission to install an older broker.
    source = Path(model_module.__file__).read_text()
    assert "remote-qwen" not in source
