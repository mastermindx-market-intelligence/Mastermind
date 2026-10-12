"""Closed source-only assignment wire; no real Backend or realm is substituted."""
import asyncio
import copy
import dataclasses
import errno

import pytest

from control_plane import broker_assignment_seal as seals
from tests import test_executive_fabric_bridge_broker as fixtures


def observation():
    ref = fixtures.start_result(fixtures.start_payload())["process_ref"]
    paths = {label: {"path": f"/inert/{label}/attempt-1", "uid": 450, "gid": 1001,
                    "mode": 0o770, "device": 1, "inode": index, "mtime_ns": 1}
             for index, label in enumerate(("workspace", "run"), 2)}
    snapshot = {"schema_version": "mastermind.worker_assignment_seal_prepare/v1",
        "run_id": "attempt-1", "job_id": "job-1", "worker_id": "worker-1",
        "effective_grant_digest": "a" * 64, "process_ref": ref, "paths": paths,
        "uid_sweep": {"schema_version": "mastermind.executive_uid_sweep/v2", "passed": True,
            "worker_uid": 1001, "broker_pid": 5555, "residual_pids_before": [],
            "residual_pids_after": [], "found_residuals": False, "ambient_pids": [],
            "ambient_identities": [], "ambient_attribution": "absent"}}
    return {"schema_version": "mastermind.worker_assignment_seal_commit/v1", "snapshot": snapshot,
        "snapshot_sha256": seals.digest(snapshot), "control_seal": {
            "schema_version": "mastermind.executive_assignment_seal/v1", "control_uid": 450,
            "sealed_at": "2026-10-12T00:00:00Z", "passed": True, "paths": {
                label: {"before": before, "after": {**before, "mode": 0o700},
                        "worker_traversal_revoked": True} for label, before in paths.items()}},
        "worker_denial": {label: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"}
                          for label in paths}}


class Backend(fixtures.Backend):
    def __init__(self):
        super().__init__()
        self.value = observation()
        self.fail = False

    async def execute(self, op, payload):
        if op == "status":
            result = await super().execute(op, payload)
            result["run"]["status"] = "SUCCEEDED"
            return result
        self.calls.append((op, copy.deepcopy(payload)))
        if self.fail:
            raise OSError(errno.EIO, "inert post-transmit loss")
        common = {"adapter_id": "attended-fabric", "binding": payload["binding"],
                  "physical_binding_sha256": payload["physical_binding_sha256"]}
        if op == "assignment-seal":
            return {**common, "observation": copy.deepcopy(self.value)}
        return {**common, "acknowledgement": {key: payload[key] for key in (
            "run_id", "observation_sha256", "retention_sha256")}}


def payload(value):
    return {"binding": fixtures.binding(), "run_id": "attempt-1",
            "worker_id": "worker-1",
            "process_ref": value["snapshot"]["process_ref"]}


def test_bridge_roundtrip_preserves_original_process_and_retention_ack(tmp_path, monkeypatch):
    backend = Backend()
    service = fixtures.broker(tmp_path, monkeypatch, backend)
    result = fixtures.execute(service, fixtures.envelope("assignment-seal", payload(backend.value)))
    assert result["result"]["observation"] == backend.value
    ack = {"observation_sha256": seals.digest(backend.value),
           "retention_sha256": seals.digest(seals.control_retention_record(backend.value))}
    result = fixtures.execute(service, fixtures.envelope("assignment-seal-finalize",
        {**payload(backend.value), **ack}))
    assert result["result"]["acknowledgement"] == {"run_id": "attempt-1", **ack}
    assert [op for op, _ in backend.calls] == ["status", "assignment-seal", "status", "assignment-seal-finalize"]


@pytest.mark.parametrize("damage", ["process", "worker", "grant", "same_uid", "denial", "loss"])
def test_assignment_transport_rejects_foreign_or_uncertain_return(tmp_path, monkeypatch, damage):
    backend = Backend()
    request = fixtures.envelope("assignment-seal", copy.deepcopy(payload(backend.value)))
    if damage == "process":
        backend.value["snapshot"]["process_ref"]["pid"] += 1
    elif damage == "grant":
        backend.value["snapshot"]["effective_grant_digest"] = "f" * 64
    elif damage == "worker":
        backend.value["snapshot"]["worker_id"] = "worker-other"
    elif damage == "same_uid":
        backend.value["snapshot"]["paths"]["workspace"]["uid"] = 1001
    elif damage == "denial":
        backend.value["worker_denial"]["run"]["open"] = "ENOENT"
    else:
        backend.fail = True
    backend.value["snapshot_sha256"] = seals.digest(backend.value["snapshot"])
    with pytest.raises(fixtures.api().BridgeProtocolError, match="EFFECT_UNKNOWN"):
        fixtures.execute(fixtures.broker(tmp_path, monkeypatch, backend), request)
    assert [op for op, _ in backend.calls] == ["status", "assignment-seal"]


def test_wrong_process_ref_stops_before_assignment_effect(tmp_path, monkeypatch):
    backend = Backend()
    request = fixtures.envelope("assignment-seal", copy.deepcopy(payload(backend.value)))
    request["payload"]["process_ref"]["pid"] += 1
    with pytest.raises(fixtures.api().BridgeProtocolError):
        fixtures.execute(fixtures.broker(tmp_path, monkeypatch, backend), request)
    assert [op for op, _ in backend.calls] == ["status"]


def test_supervisor_retains_and_reads_before_ack_and_rechecks_fence(tmp_path, monkeypatch):
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    async def run():
        runtime, supervisor, active, value = await retained_fixture(tmp_path)
        # Explicit test stand-in for the exact adapter; no production client.
        adapter = object.__new__(AttendedFabricWorkerAdapter)
        adapter.runtime = runtime
        supervisor.adapter = adapter
        supervisor.require_complete_launch_attestation = True
        events = []
        async def seal(ref):
            assert ref == active.process_ref
            events.append("seal")
            return value
        async def ack(ref, supplied):
            events.append("ack")
            path = supervisor.receipts_root / active.lease.attempt.attempt_id / "remote-assignment-observation.json"
            seals.verify_control_readback(path, seals.control_retention_record(value))
            assert supplied["retention_sha256"] == seals.digest(seals.control_retention_record(value))
            return supplied
        adapter.seal_assignment = seal
        adapter.finalize_assignment = ack
        result = await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert result.is_file() and events == ["seal", "ack"]
        def failed_retention(*args):
            raise OSError(errno.EIO, "inert retention failure")
        monkeypatch.setattr(supervisor, "_retain_remote_assignment_observation", failed_retention)
        events.clear()
        with pytest.raises(OSError):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert events == ["seal"]
    asyncio.run(run())


@pytest.mark.parametrize("operation", ["assignment-seal-prepare", "assignment-seal-commit", "assignment-seal-finalize"])
def test_real_client_already_admits_original_broker_operations(monkeypatch, operation):
    from control_plane.executive_worker_broker import WorkerBrokerClient
    async def no_transport(*args, **kwargs):
        raise RuntimeError("inert stop at transport boundary")
    monkeypatch.setattr(asyncio, "open_unix_connection", no_transport)
    with pytest.raises(RuntimeError, match="inert stop"):
        asyncio.run(WorkerBrokerClient("/inert/never-opened.sock").request(operation, {}))


def test_actual_adapter_rejects_stale_fence_before_sending_ack(tmp_path, monkeypatch):
    from tests.test_executive_fabric_adapter import _fixture, physical, result
    from control_plane.executive_worker_broker import _process_ref_from_json
    class Client:
        calls = []
        async def request(self, op, payload, **options):
            self.calls.append(op)
            raise AssertionError("stale owner must not transmit")
    client = Client()
    runtime, job, lease, adapter, spec, wire = _fixture(tmp_path, monkeypatch, client)
    raw = result(wire)["process_ref"]
    raw["run_id"] = spec.run_id
    ref = _process_ref_from_json(raw)
    adapter._leases[spec.run_id] = lease
    adapter._refs[spec.run_id] = ref
    adapter._bound[spec.run_id] = (client, wire, physical(), spec)
    runtime.attempts.adopt_attempt(spec.run_id,
        expected_fence_generation=lease.attempt.fence_generation, lease_owner="successor")
    with pytest.raises(Exception, match="stale fence"):
        asyncio.run(adapter.finalize_assignment(ref, {"run_id": spec.run_id,
            "observation_sha256": "a" * 64, "retention_sha256": "b" * 64}))
    assert client.calls == []
