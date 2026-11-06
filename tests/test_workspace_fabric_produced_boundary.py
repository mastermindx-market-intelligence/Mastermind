"""Actual paid/native producer output through the existing TypeScript App.

All identities, Runtime, journals and native artifacts are disposable fixtures.
The existing offline installation/peer fixtures remain the only host seams.
Neither catalog nor status response JSON is constructed by this test: the
current production producers generate both bodies from the retained evidence.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest

from common import executive_workspace_fabric_contract as wire
from control_plane import paid_model_execution_contract as paid_wire
from control_plane.executive_fabric_bridge_broker import BROKER_REQUEST_SCHEMA_VERSION
from control_plane.executive_worker_broker import PeerCredentials
from tests.test_workspace_fabric_read import owner, paid, run, selection
from tests.test_paid_fabric_native_status_read import native, original, _broker, _publish

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/mastermind_os"


def _bind_original(owner, original):
    """Use the very same real Runtime original start in the HMAC native log."""
    state = owner["state"]
    original.payload = copy.deepcopy(state["payload"])
    original.start = copy.deepcopy(state["start"])
    original.request = {
        "binding": copy.deepcopy(state["payload"]["binding"]),
        "run_id": state["running"].attempt_id,
        "physical_binding_sha256": state["payload"]["physical_binding_sha256"],
        "start_request_sha256": state["start"]["request_sha256"],
        "process_ref_sha256": paid_wire.digest(state["ref"].to_dict()),
        "parent_run_id": state["root"].job_id,
    }
    original.installed["bindings"] = [{
        "physical_binding": copy.deepcopy(state["payload"]["paid_physical_binding"]),
        "source_config": copy.deepcopy(state["payload"]["paid_source_config"]),
    }]
    original.log = original.owner._startup.log_dir / (original.request["run_id"] + ".log")
    original.result = original.ext / "lanes" / (original.request["run_id"] + ".remote.stdout")
    descriptor = os.open(original.log, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    try:
        original.owner._journal(SimpleNamespace(log_fd=descriptor, lock=threading.Lock()),
                                "start", original.start)
    finally:
        os.close(descriptor)


def _produce(case, owner, original, monkeypatch, tmp_path):
    _bind_original(owner, original)
    if case == "effect_unknown":
        with original.log.open("ab") as output:
            output.write(b"LEASE_PRESERVED effect_unknown=1\n")
    elif case != "active":
        _publish(original, monkeypatch,
            rc=1 if case == "failure" else 0,
            signal="provider_error" if case == "failure" else "ok",
            outcome="reviewer" if case == "accepted" else "none" if case == "rejected" else None)
        if case == "unverified_ledger":
            original.ledger.unlink()
    broker_dir = tmp_path / "native-broker"
    broker_dir.mkdir()
    broker = _broker(original, broker_dir, monkeypatch)
    calls = []

    class OriginalBrokerTransport:
        async def request(self, operation, payload, **kwargs):
            assert operation == "native-fabric-status"
            calls.append(copy.deepcopy(payload))
            response = await broker.execute({
                "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
                "request_id": "produced-browser-status",
                "operation": operation, "payload": payload,
            }, peer=PeerCredentials(uid=450, gid=450))
            assert response["ok"] is True
            return response["result"]

    # Inert transport routing only: execute the actual paid broker and native
    # reader. No fake successful native response or replaced producer method.
    monkeypatch.setattr("control_plane.executive_fabric_adapter._fixed_client",
                        lambda physical: OriginalBrokerTransport())
    catalog_envelope = run(owner)
    status_envelope = run(owner, operation=wire.STATUS_OPERATION, selection=selection(owner))
    assert catalog_envelope["ok"] is status_envelope["ok"] is True
    catalog, status = catalog_envelope["result"], status_envelope["result"]
    assert len(calls) == 2
    assert catalog["items"][0]["status"] == status
    assert original.source_reads == original.source_checks == [1, 1, 1, 1]
    assert status["run_id"] == owner["state"]["running"].attempt_id
    expected_acceptance = {"accepted": "ACCEPTED", "unaccepted": "NOT_ACCEPTED",
        "rejected": "NOT_ACCEPTED"}.get(case, "UNVERIFIED")
    assert status["acceptance_state"] == expected_acceptance
    assert status["state"] == {"active": "ACTIVE_OR_WAITING", "effect_unknown": "EFFECT_UNKNOWN"}.get(case, "TERMINAL")
    assert (status["root_id"] is None) == (case in {"active", "effect_unknown", "unverified_ledger"})
    material = {"case": case,
        "selection": {"rootId": selection(owner)["root_id"], "runId": selection(owner)["run_id"]},
        "catalog": catalog, "status": status}
    serialized = json.dumps(material, sort_keys=True)
    assert "Private retained answer" not in serialized
    assert str(original.ext) not in serialized
    return serialized

@pytest.mark.parametrize("case", [
    "active", "unaccepted", "accepted", "rejected", "failure", "effect_unknown", "unverified_ledger",
])
def test_actual_native_producer_payload_passes_typescript_and_app(
    case, owner, original, monkeypatch, tmp_path,
):
    payload = _produce(case, owner, original, monkeypatch, tmp_path)
    output = tmp_path / "actual-produced-fabric.json"
    output.write_text(payload + "\n")
    node = os.environ.get("MM_TEST_TYPESCRIPT_NODE") or shutil.which("node")
    assert node, "Node with the repository frontend dependencies is required"
    runner = APP / "node_modules/vitest/vitest.mjs"
    assert runner.is_file(), "Install the exact frontend package-lock before cross-boundary qualification"
    environment = dict(os.environ, MMOS_PAID_BROWSER_PRODUCED_JSON=str(output))
    completed = subprocess.run([
        node, str(runner), "run", "--config", "qualification/paid-browser-produced.vitest.config.ts",
        "--maxWorkers=1", "--reporter=dot",
    ], cwd=APP, env=environment, text=True, capture_output=True, timeout=90)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    print(f"Produced native {case}: TypeScript decoders + App consumption passed")
