"""Closed source-only assignment wire; no real Backend or realm is substituted."""
import asyncio
import copy
import dataclasses
import errno
import json

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
        adapter.assignment_launch_identity = lambda ref: {"inert": "original launch pin"}
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
        terminal = json.loads(result.read_bytes())
        assert terminal["schema_version"] == "mastermind.executive_assignment_seal/v1"
        assert terminal["uid_sweep"] == value["snapshot"]["uid_sweep"]
        assert terminal["paths"] == value["control_seal"]["paths"]
        events.clear()
        with pytest.raises(Exception, match="reconciliation required"):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert events == []
    asyncio.run(run())


@pytest.mark.parametrize("name", ["remote-assignment-request.json", "remote-assignment-observation.json", "assignment-seal-receipt.json"])
def test_any_existing_settlement_evidence_refuses_before_transmission(tmp_path, name):
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    async def run():
        runtime, supervisor, active, _ = await retained_fixture(tmp_path)
        adapter = object.__new__(AttendedFabricWorkerAdapter)
        adapter.runtime = runtime
        adapter.assignment_launch_identity = lambda ref: {"inert": "original launch pin"}
        supervisor.adapter = adapter
        supervisor.require_complete_launch_attestation = True
        events = []
        async def fail(ref):
            events.append("unexpected send")
        adapter.seal_assignment = fail
        previous = supervisor.receipts_root / active.lease.attempt.attempt_id / name
        previous.write_bytes(b"inert incomplete prior exchange")
        before = previous.read_bytes()
        with pytest.raises(Exception, match="reconciliation required"):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert events == [] and previous.read_bytes() == before
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
    # Adoption needs the original durable process identity. This stays inside
    # the fixture SQLite store; no host process or transport is involved.
    runtime.attempts.record_process(spec.run_id,
        fence_generation=lease.attempt.fence_generation, lease_token=lease.lease_token,
        provider_session_id=ref.provider_session_id)
    runtime.attempts.adopt_attempt(spec.run_id,
        expected_fence_generation=lease.attempt.fence_generation, lease_owner="successor")
    with pytest.raises(Exception, match="stale fence"):
        asyncio.run(adapter.finalize_assignment(ref, {"run_id": spec.run_id,
            "observation_sha256": "a" * 64, "retention_sha256": "b" * 64}))
    assert client.calls == []


@pytest.mark.parametrize("failure", ["seal", "retention", "ack", "cancel"])
def test_remote_settlement_interruption_never_replays_original_exchange(tmp_path, monkeypatch, failure):
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    async def run():
        runtime, supervisor, active, value = await retained_fixture(tmp_path)
        adapter = object.__new__(AttendedFabricWorkerAdapter)
        adapter.runtime = runtime
        adapter.assignment_launch_identity = lambda ref: {"inert": "original launch pin"}
        supervisor.adapter = adapter
        supervisor.require_complete_launch_attestation = True
        events = []
        async def seal(ref):
            events.append("seal")
            if failure == "seal":
                raise OSError("inert lost seal reply")
            if failure == "cancel":
                raise asyncio.CancelledError()
            return value
        async def ack(ref, supplied):
            events.append("ack")
            raise OSError("inert lost ACK reply")
        adapter.seal_assignment, adapter.finalize_assignment = seal, ack
        if failure == "retention":
            def fail(*args):
                raise OSError("inert failed retention")
            monkeypatch.setattr(supervisor, "_retain_remote_assignment_observation", fail)
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else OSError):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        old_events = list(events)
        with pytest.raises(Exception, match="reconciliation required"):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert events == old_events
        assert events == (["seal", "ack"] if failure == "ack" else ["seal"])
    asyncio.run(run())


@pytest.mark.parametrize("fail_at", range(1, 7))
def test_request_file_and_namespace_durability_precede_any_remote_effect(tmp_path, monkeypatch, fail_at):
    import os
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    async def run():
        runtime, supervisor, active, _ = await retained_fixture(tmp_path)
        adapter = object.__new__(AttendedFabricWorkerAdapter)
        adapter.runtime = runtime
        adapter.assignment_launch_identity = lambda ref: {"inert": "original launch pin"}
        supervisor.adapter = adapter
        supervisor.require_complete_launch_attestation = True
        events, syncs = [], []
        async def seal(ref):
            events.append("seal")
            raise AssertionError("durability failure must not transmit")
        adapter.seal_assignment = seal
        original = os.fsync
        def sync(fd):
            syncs.append(fd)
            if len(syncs) == fail_at:
                raise OSError(errno.EIO, "inert sync failure")
            return original(fd)
        monkeypatch.setattr(os, "fsync", sync)
        with pytest.raises(OSError, match="sync failure"):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert events == [] and len(syncs) == fail_at
        monkeypatch.setattr(os, "fsync", original)
        with pytest.raises(Exception, match="reconciliation required"):
            await supervisor.retain_and_acknowledge_remote_assignment(active)
        assert events == []
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["seal", "ack"])
@pytest.mark.parametrize("outcome", ["complete", "fence_lost", "cancelled"])
def test_remote_exchange_keeps_original_lease_and_joins_local_await(tmp_path, monkeypatch, stage, outcome):
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    from control_plane.executive_runtime import StateConflict

    async def run():
        runtime, supervisor, active, value = await retained_fixture(tmp_path)
        adapter = object.__new__(AttendedFabricWorkerAdapter)
        adapter.runtime = runtime
        adapter.assignment_launch_identity = lambda ref: {"inert": "original launch pin"}
        supervisor.adapter = adapter
        supervisor.require_complete_launch_attestation = True
        supervisor.heartbeat_interval_seconds = 0.01
        calls, beats, stopped = [], [], []
        entered = asyncio.Event()
        original_heartbeat = runtime.attempts.heartbeat_attempt
        def heartbeat(*args, **kwargs):
            beats.append(tuple(calls))
            if outcome == "fence_lost" and calls and calls[-1] == stage:
                raise StateConflict("inert stale fence")
            return original_heartbeat(*args, **kwargs)
        monkeypatch.setattr(runtime.attempts, "heartbeat_attempt", heartbeat)
        async def rpc(name, result):
            calls.append(name)
            if name == stage:
                entered.set()
                try:
                    await asyncio.sleep(0.04 if outcome == "complete" else 60)
                finally:
                    stopped.append(name)
            return result
        async def seal(ref):
            return await rpc("seal", value)
        async def ack(ref, payload):
            return await rpc("ack", payload)
        adapter.seal_assignment, adapter.finalize_assignment = seal, ack
        task = asyncio.create_task(supervisor.retain_and_acknowledge_remote_assignment(active))
        await asyncio.wait_for(entered.wait(), 2)
        if outcome == "cancelled":
            task.cancel()
        if outcome == "complete":
            assert (await task).is_file()
            assert any(beat and beat[-1] == stage for beat in beats)
            assert calls == ["seal", "ack"]
        else:
            with pytest.raises(asyncio.CancelledError if outcome == "cancelled" else StateConflict):
                await task
            assert calls == (["seal"] if stage == "seal" else ["seal", "ack"])
            sent = list(calls)
            with pytest.raises(Exception, match="reconciliation required"):
                await supervisor.retain_and_acknowledge_remote_assignment(active)
            assert calls == sent
        assert stopped == [stage]
    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["completed", "lost_ack", "cancel_requested"])
def test_normal_terminal_path_waits_for_original_remote_settlement(tmp_path, monkeypatch, outcome):
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    from control_plane.executive_supervisor import CleanupPolicy, TerminalAssignmentSealError
    from control_plane.executive_runtime import JobStatus
    async def run():
        runtime, supervisor, active, value = await retained_fixture(tmp_path)
        collection = await supervisor.adapter.collect_result(active.process_ref)
        collection = dataclasses.replace(collection, process_ref=dataclasses.replace(
            collection.process_ref, provider_session_id=collection.result.provider_session_id))
        from control_plane.executive_supervisor import _write_private_json, _collection_to_dict
        collection_path = supervisor.receipts_root / active.lease.attempt.attempt_id / "collection-receipt.json"
        _write_private_json(collection_path, {
            "schema_version": "mastermind.executive_collection_evidence/v1",
            "collection": _collection_to_dict(collection), "fabric_cleanup": {"inert": True}})
        adapter = object.__new__(AttendedFabricWorkerAdapter)
        adapter.runtime = runtime
        adapter.assignment_launch_identity = lambda ref: {"inert": "original launch pin"}
        supervisor.adapter = adapter
        supervisor.cleanup_policy = CleanupPolicy.FABRIC_PROCESS_GROUP
        supervisor.require_complete_launch_attestation = True
        events = []
        async def cleanup(*args, **kwargs):
            events.append("cleanup")
        async def validations(*args):
            events.append("validation")
            return (), tmp_path / "inert-validations.json", None
        monkeypatch.setattr(supervisor, "_prepare_fabric_cleanup", cleanup)
        monkeypatch.setattr(supervisor, "_run_supervisor_validations", validations)
        async def seal(ref):
            events.append("seal")
            return value
        async def ack(ref, supplied):
            events.append("ack")
            if outcome == "lost_ack":
                raise OSError("inert lost ACK")
            if outcome == "cancel_requested":
                runtime.jobs.cancel_job(active.lease.attempt.job_id)
            return supplied
        adapter.seal_assignment, adapter.finalize_assignment = seal, ack
        if outcome == "lost_ack":
            with pytest.raises(TerminalAssignmentSealError):
                await supervisor._terminalize(active, collection, tmp_path / "inert-collection.json")
            assert runtime.jobs.get_job(active.lease.attempt.job_id).status is JobStatus.CHECKPOINTED
        else:
            result = await supervisor._terminalize(active, collection, tmp_path / "inert-collection.json")
            assert result[0].status is (JobStatus.CANCELLED if outcome == "cancel_requested" else JobStatus.COMPLETED)
            assert result[3].is_file()
        assert events == ["cleanup", "validation", "seal", "ack"]
    asyncio.run(run())


@pytest.mark.parametrize("damage", ["none", "process", "result_session", "exit_code", "missing"])
def test_terminal_provider_session_enrichment_requires_exact_retained_collection(tmp_path, damage):
    from tests.test_assignment_control_retention import retained_fixture
    from control_plane.executive_supervisor import _collection_to_dict, _write_private_json
    async def run():
        runtime, supervisor, active, _ = await retained_fixture(tmp_path)
        receipt = await supervisor.adapter.collect_result(active.process_ref)
        receipt = dataclasses.replace(receipt, process_ref=dataclasses.replace(
            receipt.process_ref, provider_session_id=receipt.result.provider_session_id))
        runtime.attempts.record_process_exit(active.lease.attempt.attempt_id,
            fence_generation=active.lease.attempt.fence_generation,
            lease_token=active.lease.lease_token, exit_code=receipt.result.exit_code,
            provider_session_id=receipt.result.provider_session_id,
            result_path=receipt.process_ref.result_path)
        current = runtime.attempts.get_attempt(active.lease.attempt.attempt_id)
        wire = _collection_to_dict(receipt)
        if damage == "process": wire["process_ref"]["pid"] += 1
        if damage == "result_session": wire["result"]["provider_session_id"] = "foreign"
        if damage == "exit_code": wire["result"]["exit_code"] = 7
        if damage != "missing":
            path = supervisor.receipts_root / current.attempt_id / "collection-receipt.json"
            _write_private_json(path, {"schema_version": "mastermind.executive_collection_evidence/v1", "collection": wire})
        # No collection context is available to ordinary restart validation.
        with pytest.raises(Exception, match="durable Attempt identity"):
            supervisor._validated_recovery_binding(current)
        if damage == "none":
            binding, _, _ = supervisor._validated_remote_assignment_recovery(active, current)
            assert binding.process_ref == active.process_ref
            assert binding.process_ref.provider_session_id is None
            assert runtime.attempts.get_attempt(current.attempt_id).provider_session_id == receipt.result.provider_session_id
        else:
            with pytest.raises(Exception):
                supervisor._validated_remote_assignment_recovery(active, current)
    asyncio.run(run())
