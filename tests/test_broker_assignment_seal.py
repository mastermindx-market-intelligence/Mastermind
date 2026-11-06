"""Original broker state tests; all host/provider observations are inert fakes."""
import asyncio
import dataclasses
import json
import os
from pathlib import Path

import pytest

import control_plane.broker_assignment_seal as filesystem
from control_plane.executive_worker_broker import BrokerStateError, BrokerProtocolError
from control_plane.executive_workspace import _seal_identity
from tests.test_executive_worker_broker import _fixture, _request


def fixture(tmp_path, monkeypatch):
    broker, adapter, sweeper, peer, spec = _fixture(tmp_path)
    broker.policy = dataclasses.replace(broker.policy, require_assignment_seal=True,
                                        allowed_supplementary_gids=frozenset())
    evidence = tmp_path / "broker-evidence"
    evidence.mkdir(mode=0o700)
    sweeper.receipt_path = evidence / "uid-sweep.json"
    broker.startup_sweep = sweeper.sweep("broker_startup")
    monkeypatch.setattr(filesystem, "observe_roots", lambda paths, _policy, _manifest: {
        label: _seal_identity(Path(path), Path(path).stat()) for label, path in paths.items()})
    calls = []
    def deny(snapshot, seal, policy):
        calls.append((snapshot, seal))
        return {name: {"open": "EACCES", "traverse": "EACCES", "list": "EACCES"}
                for name in snapshot["paths"]}
    monkeypatch.setattr(filesystem, "verify_control_seal", deny)
    async def call(op, payload):
        return (await broker.execute(_request(op, payload), peer=peer))["result"]
    return broker, adapter, sweeper, spec, call, calls


def test_original_admission_spans_collection_seal_and_durable_readback(tmp_path, monkeypatch):
    async def run():
        broker, adapter, sweeper, spec, call, observations = fixture(tmp_path, monkeypatch)
        start = {"launch_spec": spec, "validation_commands": []}
        await call("start", start)
        adapter.finished.set()
        await call("collect", {"run_id": spec["run_id"]})
        assert broker._active_run_id == spec["run_id"]
        other = {**spec, "run_id": "run-2"}
        with pytest.raises(BrokerStateError, match="active work"):
            await call("start", {"launch_spec": other, "validation_commands": []})
        prepared = await call("assignment-seal-prepare", {"run_id": spec["run_id"]})
        with pytest.raises(BrokerStateError, match="settlement"):
            await call("cancel", {"run_id": spec["run_id"], "reason": "late"})
        assert adapter.cancel_calls == 0
        payload = {"run_id": spec["run_id"], "snapshot_sha256": prepared["snapshot_sha256"],
                   "seal": {"inert_control_receipt": True}}
        receipt = await call("assignment-seal-commit", payload)
        assert broker._active_run_id == spec["run_id"] and len(observations) == 1
        with pytest.raises(BrokerStateError, match="active work"):
            await call("start", {"launch_spec": other, "validation_commands": []})
        final = {"run_id": spec["run_id"], "observation_sha256": filesystem.digest(receipt),
                 "retention_sha256": filesystem.digest(filesystem.control_retention_record(receipt))}
        with pytest.raises(BrokerStateError, match="retention"):
            await call("assignment-seal-finalize", {**final, "retention_sha256": "0" * 64})
        await call("assignment-seal-finalize", final)
        assert broker._active_run_id is None
        await call("start", {"launch_spec": other, "validation_commands": []})
        assert await call("assignment-seal-commit", payload) == receipt
        assert await call("assignment-seal-finalize", final) == final
        assert broker._active_run_id == "run-2" and len(observations) == 1
        with pytest.raises(BrokerStateError, match="cannot be changed"):
            await call("assignment-seal-commit", {**payload, "seal": {"changed": True}})
    asyncio.run(run())


def test_failed_seal_holds_original_run_and_does_not_repeat_effect(tmp_path, monkeypatch):
    async def run():
        broker, adapter, _, spec, call, _ = fixture(tmp_path, monkeypatch)
        await call("start", {"launch_spec": spec, "validation_commands": []})
        adapter.finished.set()
        await call("collect", {"run_id": spec["run_id"]})
        prepared = await call("assignment-seal-prepare", {"run_id": spec["run_id"]})
        attempted = []
        def fail(*args):
            attempted.append(True)
            raise OSError("inert failure")
        monkeypatch.setattr(filesystem, "verify_control_seal", fail)
        payload = {"run_id": spec["run_id"], "snapshot_sha256": prepared["snapshot_sha256"], "seal": {}}
        for _ in range(2):
            with pytest.raises(OSError):
                await call("assignment-seal-commit", payload)
        assert len(attempted) == 1 and broker._active_run_id == spec["run_id"]
    asyncio.run(run())


def test_disconnected_commit_keeps_original_task_and_admission(tmp_path, monkeypatch):
    import threading
    async def run():
        broker, adapter, _, spec, call, _ = fixture(tmp_path, monkeypatch)
        await call("start", {"launch_spec": spec, "validation_commands": []})
        adapter.finished.set()
        await call("collect", {"run_id": spec["run_id"]})
        prepared = await call("assignment-seal-prepare", {"run_id": spec["run_id"]})
        entered, release = threading.Event(), threading.Event()
        original = filesystem.verify_control_seal
        def delayed(*args):
            entered.set()
            assert release.wait(5)
            return original(*args)
        monkeypatch.setattr(filesystem, "verify_control_seal", delayed)
        payload = {"run_id": spec["run_id"], "snapshot_sha256": prepared["snapshot_sha256"], "seal": {}}
        caller = asyncio.create_task(call("assignment-seal-commit", payload))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            assert broker._active_run_id == spec["run_id"]
        finally:
            release.set()
        await call("assignment-seal-commit", payload)
        assert broker._active_run_id == spec["run_id"]
    asyncio.run(run())


def test_preparation_requires_settled_collection_and_cancel_is_shielded(tmp_path, monkeypatch):
    async def run():
        broker, adapter, _, spec, call, _ = fixture(tmp_path, monkeypatch)
        await call("start", {"launch_spec": spec, "validation_commands": []})
        with pytest.raises(BrokerStateError, match="settle"):
            await call("assignment-seal-prepare", {"run_id": spec["run_id"]})
        entered, release = asyncio.Event(), asyncio.Event()
        original = adapter.cancel
        async def delayed(ref, reason):
            entered.set()
            await release.wait()
            return await original(ref, reason)
        monkeypatch.setattr(adapter, "cancel", delayed)
        payload = {"run_id": spec["run_id"], "reason": "original close"}
        caller = asyncio.create_task(call("cancel", payload))
        await entered.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert not broker._run(spec["run_id"]).assignment_cancel_task.done()
        release.set()
        await call("cancel", payload)
        await call("cancel", payload)
        assert adapter.cancel_calls == 1 and broker._active_run_id == spec["run_id"]
        await call("collect", {"run_id": spec["run_id"]})
        await call("assignment-seal-prepare", {"run_id": spec["run_id"]})
    asyncio.run(run())


def test_branch_refuses_validation_and_unqualified_startup(tmp_path, monkeypatch):
    async def run():
        broker, _, _, spec, call, _ = fixture(tmp_path, monkeypatch)
        with pytest.raises(BrokerProtocolError, match="validation"):
            await call("start", {"launch_spec": spec, "validation_commands": [["/bin/true"]]})
        broker.startup_sweep = None
        with pytest.raises(BrokerStateError, match="startup"):
            await call("start", {"launch_spec": spec, "validation_commands": []})
    asyncio.run(run())


def test_restart_does_not_turn_empty_stores_into_admission(tmp_path, monkeypatch):
    broker, _, sweeper, _, _, _ = fixture(tmp_path, monkeypatch)
    broker.startup_sweep = None
    monkeypatch.setattr(os, "getgroups", lambda: [os.getegid()])
    count = len(sweeper.calls)
    with pytest.raises(BrokerStateError, match="producer unavailable"):
        broker.initialize()
    with pytest.raises(BrokerStateError, match="reconciliation"):
        broker.initialize()
    assert len(sweeper.calls) == count


def test_shutdown_drains_disconnected_original_observation(tmp_path, monkeypatch):
    import threading
    async def run():
        broker, adapter, sweeper, spec, call, _ = fixture(tmp_path, monkeypatch)
        await call("start", {"launch_spec": spec, "validation_commands": []})
        adapter.finished.set()
        await call("collect", {"run_id": spec["run_id"]})
        prepared = await call("assignment-seal-prepare", {"run_id": spec["run_id"]})
        entered, release = threading.Event(), threading.Event()
        original = filesystem.verify_control_seal
        def delayed(*args):
            entered.set()
            assert release.wait(5)
            return original(*args)
        monkeypatch.setattr(filesystem, "verify_control_seal", delayed)
        caller = asyncio.create_task(call("assignment-seal-commit", {
            "run_id": spec["run_id"], "snapshot_sha256": prepared["snapshot_sha256"], "seal": {}}))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            stopping = asyncio.create_task(broker.shutdown())
            await asyncio.sleep(0)
            assert not stopping.done() and "broker_shutdown" not in sweeper.calls
        finally:
            release.set()
        await stopping
        assert broker._active_run_id == spec["run_id"]
        assert sweeper.calls[-1] == "broker_shutdown"
    asyncio.run(run())
