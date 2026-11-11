"""Real original log/result/ledger reads with inert existing owner fixtures.

No installed owner, credential, provider, SSH or process launch is exercised.
The existing exact-class owner fixture supplies the incumbent/gateway/config
qualification seam. HMAC journal verification, native status inspection,
ledger terminal/outcome validation and broker payload/peer checks run unchanged.
Successful status is never replaced by a fake result or a mocked inspector.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import importlib
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from control_plane import paid_fabric_backend as backend
from control_plane import paid_fabric_wire as wire
from control_plane import paid_model_execution_contract as contract
from control_plane import executive_fabric_bridge_broker as bridge
from control_plane.paid_fabric_bridge_broker import PaidFabricBridgeBroker
from control_plane.executive_worker_broker import PeerCredentials
from tests.test_paid_fabric_capacity import _build_owner, _FakeAccountTable, _FakeGateway
from tests.test_paid_fabric_owner_wiring import material
from tests.test_executive_fabric_bridge_broker import config as bridge_config


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "ops/native_fabric/quota_continuity"
MODULES = (
    "fabric_task", "pool_ledger", "pick", "a04_terminal_reconcile",
    "native_completion_reconcile", "native_prestart_reconcile", "native_preexec_reconcile",
    "native_host_review_controller_reconcile", "remote_sub_helpers", "artifact_delivery",
    "native_runtime_bindings", "quota_circuit", "provider_outcome", "lease_broker",
)


@pytest.fixture
def native(monkeypatch):
    # Each fixture uses the actual current candidate/source owners without
    # leaking cached alternate native modules into other tests in the process.
    with monkeypatch.context() as imports:
        imports.syspath_prepend(str(NATIVE / "source"))
        imports.syspath_prepend(str(NATIVE / "candidate"))
        for name in MODULES:
            imports.delitem(sys.modules, name, raising=False)
        task = importlib.import_module("fabric_task")
        try:
            assert Path(task.__file__).resolve() == NATIVE / "candidate/fabric_task.py"
            assert Path(task.pool_ledger.__file__).resolve() == NATIVE / "candidate/pool_ledger.py"
            yield task
        finally:
            for name in MODULES:
                sys.modules.pop(name, None)


@pytest.fixture
def original(tmp_path, monkeypatch, native):
    """Actual private journal and native artifacts; disclosed source-only seam."""
    owner = _build_owner(_FakeAccountTable({}), _FakeGateway(tmp_path / "unused.db"))
    owner._gateway._signing_key = b"test-original-paid-owner-journal-only"
    ext = tmp_path / "original-owner/ext"
    logs = ext / "state/remote_sub"
    lanes = ext / "lanes"
    ledger = ext.parent / "orch/fabric/ledger.jsonl"
    for directory in (logs, lanes, ledger.parent):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    owner._startup.owner_ext = ext
    owner._startup.log_dir = logs
    owner._startup.native_ext = NATIVE / "candidate"
    payload, frame, capsule, lease, projection = material()
    start = wire.paid_start_from_owned_launch(payload, frame, capsule=capsule, lease=lease,
        controller={"process_start_identity": "controller-fixture", "boot_id": "m2-fixture"},
        authority=projection)
    wire.validate_paid_start_wire(start, payload)
    installed = {"bindings": [{"physical_binding": payload["paid_physical_binding"],
                               "source_config": payload["paid_source_config"]}]}
    source_reads, source_checks = [], []
    def installed_source():
        source_reads.append(1)
        return copy.deepcopy(installed)
    def require_source(physical, source):
        source_checks.append(1)
        wire.require_paid_source(physical, source)
    # Root installation/host qualification is the explicit offline fixture
    # seam; the production before/after calls and exact physical join remain.
    owner._installed_source = installed_source
    owner._require_source_data = require_source
    run = payload["binding"]["attempt_id"]
    path = logs / (run + ".log")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    operation = SimpleNamespace(log_fd=fd, lock=threading.Lock())
    owner._journal(operation, "start", start)
    os.close(fd)
    request = dict(binding=copy.deepcopy(payload["binding"]), run_id=run,
        physical_binding_sha256=payload["physical_binding_sha256"],
        start_request_sha256=start["request_sha256"],
        process_ref_sha256=contract.digest(start["process_ref"]),
        parent_run_id=payload["paid_route"]["parent_job_id"])
    def forbidden(*args, **kwargs):
        pytest.fail("read attempted a provider/launch/mutation operation")
    owner.start_owned = forbidden
    owner._quota_bootstrap_owned = forbidden
    owner.capacity_observation = forbidden
    return SimpleNamespace(owner=owner, ext=ext, log=path, result=lanes/(run+".remote.stdout"),
        ledger=ledger, native=native, request=request, payload=payload, start=start,
        installed=installed, source_reads=source_reads, source_checks=source_checks)


def _publish(original, monkeypatch, *, rc=0, signal="ok", outcome=None,
             root=None, parent=None, result=b"Private retained answer.\n"):
    request = original.request
    with original.log.open("ab") as output:
        output.write(f"LAUNCH stdout=owned-original\nDONE rc={rc} signal={signal}\n".encode())
    original.result.write_bytes(result)
    original.result.chmod(0o600)
    ledger = original.native.pool_ledger
    with monkeypatch.context() as selected:
        selected.setattr(ledger, "LEDGER_DIR", str(original.ledger.parent))
        selected.setattr(ledger, "LEDGER_PATH", str(original.ledger))
        assert ledger.append(pool="fixture-paid", window_id="fixture", task_class="remote-fixture",
            job_class="research", model="fixture-model", run_id=request["run_id"],
            root_id=root or request["binding"]["root_id"],
            parent_run_id=parent or request["parent_run_id"], rc=rc, signal=signal, strict=True)
        if outcome is not None:
            assert ledger.record_outcome(request["run_id"], accepted_by=outcome, strict=True)


def _read(original, request=None):
    return asyncio.run(original.owner.execute("native-fabric-status",
        copy.deepcopy(original.request if request is None else request)))


@pytest.mark.parametrize("outcome,accepted,reason", [
    (None, False, "NO_OUTCOME"), ("reviewer", True, "VALIDATED_OUTCOME"),
    ("none", False, "OUTCOME_NOT_ACCEPTED"),
])
def test_actual_native_ledger_distinguishes_success_acceptance_and_no_outcome(
    original, monkeypatch, outcome, accepted, reason
):
    _publish(original, monkeypatch, outcome=outcome)
    # A deliberately unusable module default cannot redirect this fixed-owner
    # read; the explicit owner namespace must select its own original ledger.
    monkeypatch.setattr(original.native.pool_ledger, "LEDGER_PATH", str(original.ext / "other-ledger"))
    files = {path: path.read_bytes() for path in (original.log, original.result, original.ledger)}
    response = _read(original)
    status = response["status"]
    assert status["state"] == "TERMINAL" and status["rc"] == 0
    assert status["accepted"] is accepted and status["acceptance_reason"] == reason
    assert status["accepted_by"] == outcome
    assert status["result_bytes"] == len(files[original.result])
    assert status["root_id"] == original.request["binding"]["root_id"]
    assert status["parent_run_id"] == original.request["parent_run_id"]
    assert response["process_ref_sha256"] == original.request["process_ref_sha256"]
    assert response["request_sha256"] == original.request["start_request_sha256"]
    assert files == {path: path.read_bytes() for path in files}
    assert original.source_reads == original.source_checks == [1, 1]
    assert "Private retained answer" not in json.dumps(response)
    assert str(original.ext) not in json.dumps(response)


def test_default_native_status_contract_is_unchanged(original, monkeypatch):
    _publish(original, monkeypatch, outcome="reviewer")
    monkeypatch.setattr(original.native, "HERE", original.ext)
    monkeypatch.setattr(original.native.pool_ledger, "LEDGER_PATH", str(original.ledger))
    assert original.native.inspect_run(original.request["run_id"]) == original.native.inspect_run(
        original.request["run_id"], owner_ext=original.ext)


def test_terminal_failure_keeps_real_execution_lineage_without_acceptance(original, monkeypatch):
    _publish(original, monkeypatch, rc=1, signal="provider_error")
    status = _read(original)["status"]
    assert status["state"] == "TERMINAL" and status["rc"] == 1
    assert status["accepted"] is None and status["acceptance_state"] == "UNVERIFIED"
    assert status["root_id"] == original.request["binding"]["root_id"]
    assert status["parent_run_id"] == original.request["parent_run_id"]


@pytest.mark.parametrize("fault,reason", [
    ("missing_ledger", "LEDGER_UNAVAILABLE"),
    ("unsafe_ledger", "LEDGER_UNVERIFIED"),
    ("duplicate_terminal", "LEDGER_UNVERIFIED"),
    ("symlink_result", "ARTIFACT_UNVERIFIED"),
])
def test_actual_unavailable_or_conflicting_native_evidence_never_becomes_accepted(
    original, monkeypatch, fault, reason
):
    _publish(original, monkeypatch, outcome="reviewer")
    if fault == "missing_ledger":
        original.ledger.unlink()
    elif fault == "unsafe_ledger":
        original.ledger.chmod(0o666)
    elif fault == "duplicate_terminal":
        first = original.ledger.read_bytes().splitlines()[0]
        with original.ledger.open("ab") as output:
            output.write(first + b"\n")
    else:
        target = original.result.with_suffix(".target")
        original.result.rename(target)
        original.result.symlink_to(target)
    status = _read(original)["status"]
    assert status["accepted"] is None and status["accepted_by"] is None
    assert status["acceptance_state"] == "UNVERIFIED"
    if fault != "symlink_result":
        assert status["acceptance_reason"] == reason
    else:
        assert status["result_available"] is False


@pytest.mark.parametrize("field", ["start_request_sha256", "process_ref_sha256", "physical_binding_sha256"])
def test_original_start_mismatch_refuses_before_native_read(original, monkeypatch, field):
    changed = copy.deepcopy(original.request)
    changed[field] = "0" * 64
    monkeypatch.setattr(original.native, "inspect_run",
        lambda *a, **kw: pytest.fail("mismatched original reached native status"))
    with pytest.raises(backend.PaidOwnerRefused):
        _read(original, changed)


def test_journal_hmac_and_single_original_start_are_required(original, monkeypatch):
    raw = original.log.read_bytes()
    parsed = json.loads(raw[len(backend._JOURNAL):])
    parsed["tag"] = "0" * 64
    original.log.write_bytes(backend._JOURNAL + contract.canonical(parsed) + b"\n")
    monkeypatch.setattr(original.native, "inspect_run",
        lambda *a, **kw: pytest.fail("unverified journal reached native status"))
    with pytest.raises(backend.PaidOwnerRefused):
        _read(original)
    original.log.write_bytes(raw + raw)
    with pytest.raises(backend.PaidOwnerRefused):
        _read(original)


@pytest.mark.parametrize("field", ["root", "parent"])
def test_actual_native_foreign_lineage_is_refused(original, monkeypatch, field):
    _publish(original, monkeypatch, outcome="reviewer", **{field: "foreign-original"})
    with pytest.raises(ValueError, match="invalid_fabric_status"):
        _read(original)


@pytest.mark.parametrize("fault", ["installed", "journal", "gateway"])
def test_post_read_owner_rechecks_discard_a_late_changed_read(original, monkeypatch, fault):
    _publish(original, monkeypatch, outcome="reviewer")
    inspect = original.native.inspect_run
    def changed(*args, **kwargs):
        result = inspect(*args, **kwargs)
        if fault == "installed":
            original.installed["bindings"] = []
        elif fault == "journal":
            raw = original.log.read_bytes()
            first = next(line for line in raw.splitlines() if line.startswith(backend._JOURNAL))
            with original.log.open("ab") as output:
                output.write(first + b"\n")
        else:
            original.owner._gateway._canonical_owner = None
        return result
    monkeypatch.setattr(original.native, "inspect_run", changed)
    with pytest.raises(backend.PaidOwnerRefused):
        _read(original)


def _broker(original, tmp_path, monkeypatch):
    # Reuse the existing root-config fixture. Restore its filesystem-stat seam
    # before reading actual native artifacts; only immutable config DATA remain.
    with monkeypatch.context() as config_fixture:
        config = bridge_config(tmp_path, config_fixture)
    config = dataclasses.replace(config, adapter_id=contract.ADAPTER_ID, bridge_uid=os.geteuid())
    return PaidFabricBridgeBroker(config, original.owner)


def _request(original, *, payload=None):
    return dict(schema_version=bridge.BROKER_REQUEST_SCHEMA_VERSION,
        request_id="native-status-read", operation="native-fabric-status",
        payload=copy.deepcopy(original.request if payload is None else payload))


def test_narrow_broker_returns_actual_native_status(original, tmp_path, monkeypatch):
    _publish(original, monkeypatch, outcome="reviewer")
    service = _broker(original, tmp_path, monkeypatch)
    response = asyncio.run(service.execute(_request(original),
        peer=PeerCredentials(uid=450, gid=450)))
    assert response["ok"] is True
    assert response["result"]["status"]["accepted"] is True
    assert response["operation"] == "native-fabric-status"


@pytest.mark.parametrize("uid", [0, 501, 451])
def test_broker_denies_non_control_peer_before_native_read(original, tmp_path, monkeypatch, uid):
    service = _broker(original, tmp_path, monkeypatch)
    monkeypatch.setattr(original.owner, "execute", lambda *a, **kw: pytest.fail("wrong peer reached backend"))
    with pytest.raises(bridge.BridgeProtocolError, match="PeerAuthorizationError"):
        asyncio.run(service.execute(_request(original), peer=PeerCredentials(uid=uid, gid=uid)))


@pytest.mark.parametrize("fault", ["path", "missing_process", "wrong_run", "replacement_root"])
def test_broker_closed_read_payload_refuses_before_native_read(original, tmp_path, monkeypatch, fault):
    service = _broker(original, tmp_path, monkeypatch)
    request = _request(original)
    if fault == "path":
        request["payload"]["owner_ext"] = str(original.ext)
    elif fault == "missing_process":
        del request["payload"]["process_ref_sha256"]
    elif fault == "wrong_run":
        request["payload"]["run_id"] = "replacement-run"
    else:
        request["payload"]["root_id"] = "replacement-root"
    monkeypatch.setattr(original.owner, "execute", lambda *a, **kw: pytest.fail("invalid payload reached backend"))
    with pytest.raises(bridge.BridgeProtocolError):
        asyncio.run(service.execute(request, peer=PeerCredentials(uid=450, gid=450)))
