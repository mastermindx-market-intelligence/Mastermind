"""Compose routing candidates with the COMPLETE protected #1391 broker fixture.

Every fixture is an unchanged repository blob, not installed source. Temporary
SQLite and synthetic configuration only; no host probe, provider or live lease.
This does not run or clear the separately held original native fixture suite.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/native_fabric_protected_20261014"
BUNDLE = ROOT / "ops/native_fabric/routing_audit_20261013"
PROTECTED_SOURCE = "e1cacf9eb310cbdf25a3a22defedb7b086c6c179"
FIXTURE_HASHES = {
    "lease_broker.py.txt": "a72bc031ddb81e559e0cf48fcbf824a959edfcf445c1d3d2d89348c3c66c6f0c",
    "native_broker_admission.py.txt": "b47b3861e6c4384fc7ca9a70c49c1dace12993a4a6e29afa855953af587b2b48",
    "native_admission.patch": "c98d2ffebd87c18177067d1b69146d0979c571019d57e1b3697c400669f7448e",
    "glm_expiry.patch": "9fc2376397f58819c7a2debab389ef9bd4b9abef9f9400ecd210f011591ef95e",
}
NATIVE_POSTIMAGE = "4cac678defac9116c2324a651a7cd90c5144822d8cd1c2aa64e20c299a2a9267"


def _apply(root, patch, *options):
    result = subprocess.run(
        ["git", "apply", *options, str(patch)], cwd=root,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, f"{patch.name}: {result.stderr}"


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


@pytest.fixture(scope="module")
def complete_broker(tmp_path_factory):
    for name, digest in FIXTURE_HASHES.items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    root = tmp_path_factory.mktemp("routing-protected-source")
    ext = root / "ext"
    ext.mkdir()
    target = ext / "lease_broker.py"
    shutil.copyfile(FIXTURES / "lease_broker.py.txt", target)
    shutil.copyfile(FIXTURES / "native_broker_admission.py.txt", ext / "native_broker_admission.py")
    _apply(root, FIXTURES / "native_admission.patch", "--directory=ext")
    assert hashlib.sha256(target.read_bytes()).hexdigest() == NATIVE_POSTIMAGE
    protected = target.read_text()
    _apply(root, FIXTURES / "glm_expiry.patch", "--include=ext/lease_broker.py")
    for relative in (
        "protected_composition/logical_priority_after_native.patch",
        "queue_priority/queue_priority_isolation.patch",
        "request_waiters/request_waiters.patch",
        "request_waiters/request_waiters_wiring.patch",
        "account_balance/normalized_account_balance.patch",
    ):
        _apply(root, BUNDLE / relative, "--include=ext/lease_broker.py")
    # The native helper is unchanged; the import exists only while constructing
    # this isolated module. Do not alter another test's incumbent module binding.
    previous = sys.modules.get("native_broker_admission")
    name = "_fabric_routing_protected_broker_test"
    prior_broker = sys.modules.get(name)
    try:
        _module("native_broker_admission", ext / "native_broker_admission.py")
        value = _module(name, target)
    finally:
        if previous is None:
            sys.modules.pop("native_broker_admission", None)
        else:
            sys.modules["native_broker_admission"] = previous
    value._composed_source = target.read_text()
    value._protected_source = protected
    value._composed_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    yield value
    if prior_broker is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = prior_broker


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("protected-composition test attempted network I/O")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def broker(module, tmp_path, accounts=None):
    config = tmp_path / "synthetic.yaml"
    config.write_text(yaml.safe_dump({"providers": {"minimax": {
        "enabled": True,
        "accounts": accounts or [{"name": "synthetic", "per_account_cap": 4}],
    }}}))
    clock = [2_000_000_000.0]
    value = module.Broker(
        db_path=str(tmp_path / "leases.sqlite"), lock_path=str(tmp_path / "leases.lock"),
        accounts_path=str(config), now_fn=lambda: clock[0], check_pid=False,
        external_gates=False, grok_marker=str(tmp_path / "absent"),
        status_json=str(tmp_path / "status.json"), hosts_path=str(tmp_path / "hosts.json"),
        this_host="synthetic",
    )
    return value, clock


def native_binding():
    return {
        "schema": "mastermind.fabric_native_admission.v1",
        "root_id": "native-root", "parent_id": "native-root", "job_id": "native-job",
        "attempt_id": "native-attempt", "pool": "minimax", "account": "synthetic",
        "model": "MiniMax-M3", "host": "synthetic", "task_class": "remote-minimax",
        "fence": 1, "owner_pid": 1,
        "start_request_sha256": "a" * 64, "configuration_sha256": "b" * 64,
        "realm_binding_sha256": "c" * 64, "control_identity_sha256": "d" * 64,
    }


def test_native_parameter_and_keyword_forwarding_survive_full_composition(complete_broker):
    import inspect
    params = list(inspect.signature(complete_broker.Broker._try_acquire).parameters)
    assert params.index("native_binding") < params.index("job_class")
    tree = ast.parse(complete_broker._composed_source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Broker")
    acquire = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "acquire")
    call = next(n for n in ast.walk(acquire) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "_try_acquire")
    assert len(call.args) == 10
    assert [k.arg for k in call.keywords] == ["job_class"]


@pytest.mark.parametrize("logical", ["heal", "review", "mechanical"])
def test_complete_ordinary_acquire_never_attaches_native_binding(complete_broker, tmp_path, logical):
    br, _ = broker(complete_broker, tmp_path)
    result = br.acquire("ordinary-root", "minimax", task_class="remote-minimax",
                        job_class=logical, request_id="ordinary-request", model="MiniMax-M3")
    assert result.ok, result.reason
    with br._conn() as conn:
        row = conn.execute("SELECT * FROM leases WHERE id=?", (result.lease_id,)).fetchone()
        assert row["native_key"] is None and row["native_binding"] is None
        assert row["task_class"] == "remote-minimax"
    assert br.release(result.lease_id, "ordinary-root")


def test_complete_request_success_retains_sibling_demand(complete_broker, tmp_path):
    br, _ = broker(complete_broker, tmp_path, [{"name": "synthetic", "per_account_cap": 1}])
    held = br.acquire("holder", "minimax")
    assert held.ok
    for rid in ("child-a", "child-b"):
        refused = br.acquire("parent", "minimax", task_class="remote-minimax",
                             job_class="review", request_id=rid)
        assert not refused.ok and refused.reason == "cap_full"
    with br._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM waiters").fetchone()[0] == 2
        assert br.fair_share(conn, "minimax") == 1
    assert br.release(held.lease_id, "holder")
    result = br.acquire("parent", "minimax", task_class="remote-minimax",
                        job_class="review", request_id="child-a")
    assert result.ok, result.reason
    with br._conn() as conn:
        rows = list(conn.execute("SELECT id,orchestrator_id FROM waiters"))
        assert len(rows) == 1 and rows[0]["orchestrator_id"] == "parent"
        assert rows[0]["id"] == complete_broker._request_waiter_id("parent", "minimax", "child-b")


def test_native_original_binding_and_ordinary_release_fences_survive(complete_broker, tmp_path):
    br, _ = broker(complete_broker, tmp_path)
    original = native_binding()
    result = br.acquire_native_admission(original)
    assert result["state"] == "RETAINED"
    lid = result["grant"]["lease_id"]
    assert br.release(lid, "native-root") is False
    heartbeat = br.heartbeat(lid)
    assert not heartbeat and heartbeat.reason == "native_owner_required"
    with pytest.raises(ValueError, match="native_original_changed"):
        br.acquire_native_admission({**original, "parent_id": "other-parent"})
    assert br.read_native_admission(original)["grant"] == result["grant"]
    with br._conn() as conn:
        row = conn.execute("SELECT native_binding FROM leases WHERE id=?", (lid,)).fetchone()
        assert json.loads(row["native_binding"]) == original


def test_native_uncertainty_retains_capacity_while_ordinary_ttl_expires(complete_broker, tmp_path):
    br, clock = broker(complete_broker, tmp_path)
    original = native_binding()
    retained = br.acquire_native_admission(original)
    ordinary = br.acquire("ordinary-root", "minimax", job_class="review", request_id="other")
    assert ordinary.ok
    clock[0] += 1000
    br.gc()
    state = br.read_native_admission(original)
    assert state["lease_state"] in ("held", "rented")
    assert state["reconciliation_required"] is True
    with br._conn() as conn:
        row = conn.execute("SELECT state FROM leases WHERE id=?", (ordinary.lease_id,)).fetchone()
        assert row["state"] == "expired"
        native = conn.execute("SELECT state FROM leases WHERE id=?", (retained["grant"]["lease_id"],)).fetchone()
        assert native["state"] in ("held", "rented")


def test_native_grant_still_consumes_shared_capacity(complete_broker, tmp_path):
    br, _ = broker(complete_broker, tmp_path, [{"name": "synthetic", "per_account_cap": 1}])
    assert br.acquire_native_admission(native_binding())["state"] == "RETAINED"
    result = br.acquire("ordinary-root", "minimax", job_class="heal", request_id="urgent")
    assert not result.ok and result.reason == "cap_full"
    with br._conn() as conn:
        assert len(br._active_leases(conn, "minimax")) == 1


def test_normalized_choice_uses_full_broker_account_counts(complete_broker, tmp_path):
    br, _ = broker(complete_broker, tmp_path, [
        {"name": "small", "per_account_cap": 2}, {"name": "large", "per_account_cap": 12},
    ])
    for index, acct in enumerate(("small", "large", "large")):
        assert br.acquire("seed", "minimax", account=acct, request_id=f"seed-{index}").ok
    with br._conn() as conn:
        assert br._pick_account(conn, "minimax", None, model="MiniMax-M3") == "large"
        subset = [a for a in br.grantable_accounts("minimax") if a["name"] == "small"]
        assert br._pick_account(conn, "minimax", None, model="MiniMax-M3", grantable_override=subset) == "small"


def test_native_and_root_protection_bodies_are_unchanged(complete_broker):
    def methods(source):
        cls = next(n for n in ast.parse(source).body
                   if isinstance(n, ast.ClassDef) and n.name == "Broker")
        return {n.name: ast.dump(n, include_attributes=False) for n in cls.body if isinstance(n, ast.FunctionDef)}
    protected = methods(complete_broker._protected_source)
    candidate = methods(complete_broker._composed_source)
    for name in ("_ensure_schema", "_gc_locked", "heartbeat", "release", "_active_orchestrators", "fair_share"):
        assert candidate[name] == protected[name], name
