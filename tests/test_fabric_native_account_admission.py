"""Inert Broker database proof; never imports the installed broker or its DB."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "integrations/session_bridge/native_broker_admission"


@pytest.fixture(scope="module")
def broker_module(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-broker-source")
    shutil.copyfile(SOURCE / "fixtures/lease_broker.base.py", root / "lease_broker.py")
    subprocess.run(["git", "apply", str(SOURCE / "lease_broker.py.patch")], cwd=root, check=True)
    sys.path.insert(0, str(SOURCE))
    try:
        spec = importlib.util.spec_from_file_location("native_admission_broker_fixture", root / "lease_broker.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(SOURCE))


@pytest.fixture
def setup(tmp_path, broker_module):
    accounts = {"providers": {p: {"enabled": True, "accounts": [
        {"name": "enrolled", "per_account_cap": 1}]} for p in ("minimax", "grok")}}
    (tmp_path / "accounts.yaml").write_text(json.dumps(accounts))
    (tmp_path / "hosts.json").write_text(json.dumps({"studio": {
        "roles": ["lanes"], "allowed_modes": ["grok"], "cores": 4,
        "max_active": 4, "lane_ceiling": 4}}))
    clock = [1000.0]
    def make():
        return broker_module.Broker(
            db_path=str(tmp_path / "leases.sqlite"), lock_path=str(tmp_path / "leases.lock"),
            accounts_path=str(tmp_path / "accounts.yaml"), status_json=str(tmp_path / "status.json"),
            hosts_path=str(tmp_path / "hosts.json"), grok_marker=str(tmp_path / "GROK_EXHAUSTED"),
            this_host="studio", external_gates=False, check_pid=False, now_fn=lambda: clock[0])
    binding = dict(schema="mastermind.fabric_native_admission.v1", root_id="original-root",
        parent_id="original-parent", job_id="runtime-job", attempt_id="runtime-attempt", fence=1,
        start_request_sha256="1" * 64, configuration_sha256="2" * 64,
        realm_binding_sha256="3" * 64, control_identity_sha256="4" * 64,
        pool="minimax", account="enrolled", model="MiniMax-M2.7", host="studio",
        task_class="review", owner_pid=1234)
    return make(), make, binding, clock, tmp_path


def proof():
    return dict(process_receipt_sha256="5" * 64, cleanup_record_sha256="6" * 64,
                assignment_observation_sha256="7" * 64, control_retention_sha256="8" * 64,
                physical_release_sha256="9" * 64)


def test_lost_response_reconstruction_retains_original_uuid(setup):
    broker, make, binding, _, _ = setup
    original = broker.acquire_native_admission(binding)
    assert original["state"] == "RETAINED"
    assert make().acquire_native_admission(binding) == original
    assert make().read_native_admission(binding) == original
    with broker._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 1


def test_concurrent_duplicate_admission_uses_one_grant(setup):
    broker, make, binding, _, _ = setup
    other = make()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda b: b.acquire_native_admission(binding), [broker, other]))
    assert rows[0] == rows[1]
    with broker._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 1


@pytest.mark.parametrize("field,value", [
    ("root_id", "wrong-root"), ("parent_id", "wrong-parent"), ("fence", 2),
    ("start_request_sha256", "a" * 64), ("configuration_sha256", "a" * 64),
    ("realm_binding_sha256", "a" * 64), ("control_identity_sha256", "a" * 64),
    ("pool", "grok"), ("account", "other"), ("model", "other"),
    ("host", "other"), ("task_class", "build"), ("owner_pid", 5678),
])
def test_changed_original_refuses_before_a_second_grant(setup, field, value):
    broker, _, binding, _, _ = setup
    original = broker.acquire_native_admission(binding)
    with pytest.raises(ValueError, match="native_original_changed"):
        broker.acquire_native_admission({**binding, field: value})
    assert broker.read_native_admission(binding) == original


def test_original_is_visible_after_provider_exhaustion(setup):
    broker, _, binding, _, root = setup
    binding = {**binding, "pool": "grok", "model": "grok-4.6"}
    original = broker.acquire_native_admission(binding)
    assert original["state"] == "RETAINED"
    (root / "GROK_EXHAUSTED").write_text("fixture exhausted")
    assert broker.acquire_native_admission(binding) == original


def test_settled_original_cannot_reacquire_or_change_receipt(setup):
    broker, make, binding, _, _ = setup
    original = broker.acquire_native_admission(binding)
    lease = original["grant"]["lease_id"]
    settled = broker.settle_native_admission(binding, lease, proof())
    assert settled["state"] == "SETTLED" and settled["lease_state"] == "released"
    assert make().acquire_native_admission(binding) == settled
    assert make().settle_native_admission(binding, lease, proof()) == settled
    with pytest.raises(ValueError, match="native_settlement_changed"):
        broker.settle_native_admission(binding, lease, {**proof(), "control_retention_sha256": "a" * 64})
    with pytest.raises(ValueError, match="native_original_changed"):
        broker.settle_native_admission(binding, "wrong-lease", proof())


@pytest.mark.parametrize("field,value", [("fence", True), ("owner_pid", 0),
    ("root_id", ""), ("start_request_sha256", "x" * 64), ("unexpected", "x")])
def test_invalid_bindings_have_no_effect(setup, field, value):
    broker, _, binding, _, _ = setup
    with pytest.raises(ValueError, match="native_binding"):
        broker.acquire_native_admission({**binding, field: value})
    with broker._conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0] == 0


def test_native_ttl_expiry_preserves_accounted_capacity(setup):
    broker, _, binding, clock, _ = setup
    original = broker.acquire_native_admission(binding)
    clock[0] += 2000
    assert broker.gc() == 0
    row = broker.read_native_admission(binding)
    assert row["reconciliation_required"] and row["lease_state"] in ("held", "rented")
    assert not broker.heartbeat_native_admission(binding, original["grant"]["lease_id"])["ok"]
    assert not broker.acquire("other-root", "minimax", account="enrolled").ok


def test_unconfirmed_pid_never_recycles_native_capacity(setup, broker_module, monkeypatch):
    broker, _, binding, _, _ = setup
    original = broker.acquire_native_admission(binding)
    broker.check_pid = True
    monkeypatch.setattr(broker_module.os, "kill", lambda *args: (_ for _ in ()).throw(PermissionError()))
    assert broker.gc() == 0
    row = broker.read_native_admission(binding)
    assert row["grant"] == original["grant"] and row["reconciliation_required"]


def test_ordinary_mutators_cannot_settle_or_renew_native(setup):
    broker, _, binding, _, _ = setup
    lease = broker.acquire_native_admission(binding)["grant"]["lease_id"]
    assert not broker.release(lease, orchestrator_id=binding["root_id"])
    assert broker.heartbeat(lease).reason == "native_owner_required"
    assert broker.heartbeat_native_admission(binding, lease)["ok"]
    with pytest.raises(ValueError, match="native_exact_terminal_receipts_required"):
        broker.settle_native_admission(binding, lease, {"cleanup_proven": True})


def test_ordinary_operations_keep_existing_behavior(setup):
    broker, _, _, clock, _ = setup
    first = broker.acquire("ordinary", "minimax", account="enrolled")
    assert first.ok and broker.heartbeat(first.lease_id)
    assert broker.release(first.lease_id, orchestrator_id="ordinary")
    second = broker.acquire("ordinary", "minimax", account="enrolled")
    assert second.ok and second.lease_id != first.lease_id
    clock[0] += 2000
    assert broker.gc() == 1
