"""Independent #994 integration review: disposable fixtures, no real provider."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from control_plane.executive_capacity_observation import (
    CapacityObservationError,
    OBSERVATION_FIELDS,
    validate_worker_capacity_observation,
)
from control_plane.executive_worker_broker import (
    BrokerProtocolError,
    BrokerStateError,
    PeerAuthorizationError,
)
from test_executive_worker_broker import _fixture, _request
from test_worker_capacity_observer import NOW, SECRET, _validated_observer, harness


def make_broker(tmp_path):
    root = tmp_path / "broker-case"
    root.mkdir()
    return _fixture(root)


def test_real_sealed_observer_public_projection_reaches_broker(harness, monkeypatch, tmp_path):
    observer = _validated_observer(harness, monkeypatch)
    broker, adapter, sweeper, peer, _ = make_broker(tmp_path)
    captured = []

    def observe_public():
        result = observer.observe()
        captured.append(result)
        return result.to_dict()

    broker.capacity_observer = observe_public
    result = asyncio.run(broker.execute(_request("capacity-observe/v1", {}), peer=peer))
    assert result["ok"] is True
    assert len(captured) == 1
    payload = result["result"]
    assert set(payload) == set(OBSERVATION_FIELDS)
    assert payload == captured[0].to_dict()
    normalized = validate_worker_capacity_observation(
        payload,
        expected_host_ref=harness.source["host_ref"],
        expected_capacity_capability_id=harness.source["capacity_capability_id"],
        expected_source_config_digest=captured[0].source_config_digest,
        trusted_current_ms=int(NOW.timestamp() * 1000),
    )
    assert normalized.to_dict() == payload
    text = json.dumps(payload)
    for forbidden in ("_seal", SECRET.decode(), str(harness.source_path), str(harness.slot.auth_path)):
        assert forbidden not in text
    assert adapter.spec is None and sweeper.calls == []


def test_raw_sealed_dataclass_is_not_a_public_mapping(harness, monkeypatch, tmp_path):
    observer = _validated_observer(harness, monkeypatch)
    broker, _, _, peer, _ = make_broker(tmp_path)
    broker.capacity_observer = observer.observe
    with pytest.raises(BrokerStateError, match="invalid projection"):
        asyncio.run(broker.execute(_request("capacity-observe/v1", {}), peer=peer))


def test_wrong_peer_is_refused_before_observer(tmp_path):
    broker, adapter, sweeper, peer, _ = make_broker(tmp_path)
    calls = []
    broker.capacity_observer = lambda: calls.append("called") or {}
    wrong = dataclasses.replace(peer, uid=peer.uid + 1)
    with pytest.raises(PeerAuthorizationError):
        asyncio.run(broker.execute(_request("capacity-observe/v1", {}), peer=wrong))
    assert calls == [] and adapter.spec is None and sweeper.calls == []


@pytest.mark.parametrize("field,value", [
    ("_active_run_id", "already-active"), ("_operator_run", object()),
    ("_starting", True), ("_validation_busy", True), ("_status_sweep_busy", True),
])
def test_all_busy_states_refuse_before_observer(tmp_path, field, value):
    broker, _, _, peer, _ = make_broker(tmp_path)
    calls = []
    broker.capacity_observer = lambda: calls.append("called") or {}
    setattr(broker, field, value)
    with pytest.raises(BrokerStateError, match="idle broker"):
        asyncio.run(broker.execute(_request("capacity-observe/v1", {}), peer=peer))
    assert calls == []


@pytest.mark.parametrize("payload", [{"host_ref":"redirect"}, {"slot_id":"other"}, {"path":"/elsewhere"}, {"now_ms":0}])
def test_caller_has_no_target_or_time_override(tmp_path, payload):
    broker, _, _, peer, _ = make_broker(tmp_path)
    calls = []
    broker.capacity_observer = lambda: calls.append("called") or {}
    with pytest.raises(BrokerProtocolError, match="empty"):
        asyncio.run(broker.execute(_request("capacity-observe/v1", payload), peer=peer))
    assert calls == []


def test_real_source_binding_drift_does_not_become_success(harness, monkeypatch, tmp_path):
    observer = _validated_observer(harness, monkeypatch)
    broker, adapter, sweeper, peer, _ = make_broker(tmp_path)
    broker.capacity_observer = lambda: observer.observe().to_dict()
    changed = dict(harness.source)
    changed["host_ref"] = "host-" + "c" * 64
    harness.write_source(changed)
    with pytest.raises(CapacityObservationError, match="CONFIG_DRIFT"):
        asyncio.run(broker.execute(_request("capacity-observe/v1", {}), peer=peer))
    assert adapter.spec is None and sweeper.calls == []


def test_prior_autonomy_revocation_refuses_before_observer(tmp_path):
    broker, _, _, peer, _ = make_broker(tmp_path)
    calls = []
    broker.capacity_observer = lambda: calls.append("called") or {}
    broker.operator_harness_armed = True
    def revoked():
        raise ValueError("fixture-revoked")
    broker.autonomy_guard = revoked
    with pytest.raises(BrokerStateError, match="autonomy receipt refused"):
        asyncio.run(broker.execute(_request("capacity-observe/v1", {}), peer=peer))
    assert calls == []


def test_autonomy_revoked_while_waiting_for_state_lock_refuses(tmp_path):
    broker, _, _, peer, _ = make_broker(tmp_path)
    calls = []
    revocation = {"active": False}
    broker.capacity_observer = lambda: calls.append("called") or {}
    broker.operator_harness_armed = True
    def guard():
        if revocation["active"]:
            raise ValueError("fixture-revoked-after-precheck")
    broker.autonomy_guard = guard

    async def run():
        await broker._state_lock.acquire()
        task = asyncio.create_task(broker.execute(_request("capacity-observe/v1", {}), peer=peer))
        try:
            await asyncio.sleep(0)  # Task reaches the lock after its initial guard.
            assert not task.done()
            revocation["active"] = True
        finally:
            broker._state_lock.release()
        with pytest.raises(BrokerStateError, match="autonomy receipt refused"):
            await task
        assert calls == []
    asyncio.run(run())


def test_cancelled_waiter_does_not_later_observe(tmp_path):
    broker, _, _, peer, _ = make_broker(tmp_path)
    calls = []
    broker.capacity_observer = lambda: calls.append("called") or {}
    async def run():
        await broker._state_lock.acquire()
        task = asyncio.create_task(broker.execute(_request("capacity-observe/v1", {}), peer=peer))
        try:
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            broker._state_lock.release()
        await asyncio.sleep(0)
        assert calls == []
    asyncio.run(run())
