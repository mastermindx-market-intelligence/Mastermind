"""Operator-only construction must never manufacture a legacy provider route."""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.executive_worker_broker import (
    BrokerStateError, ExecutiveWorkerBroker, PeerAuthorizationError,
    PeerCredentials, WorkerBrokerError,
)
from control_plane.operator_harness_contract import (
    ProcessGenerationRef, SessionEpochRef,
)
from control_plane.operator_harness_wire import to_wire
from test_executive_operator_broker import _fixture, _materialization_payload, _request


def configured(tmp_path):
    old, peer, profile, sweeper, adapters = _fixture(tmp_path)
    kwargs = dict(
        adapter_id=None,
        operator_binary_attestation=old.adapter.binary,
        operator_adapter_factory=old.operator_adapter_factory,
        operator_harness_armed=True,
        autonomy_guard=old.autonomy_guard,
        autonomy_canary_factory=old.autonomy_canary_factory,
    )
    return old.policy, peer, profile, sweeper, adapters, kwargs


@pytest.mark.parametrize("field,value", [
    ("adapter_id", "codex-cli"),
    ("validation_adapter", object()),
    ("validation_adapter_id", "codex-cli"),
    ("operator_binary_attestation", None),
    ("operator_binary_attestation", {"sha256": "a" * 64}),
    ("operator_adapter_factory", None),
    ("operator_adapter_factory", "not-callable"),
    ("operator_harness_armed", False),
    ("operator_harness_armed", "true"),
    ("autonomy_guard", None),
    ("autonomy_canary_factory", None),
])
def test_operator_only_requires_all_existing_admission_and_identity_inputs(tmp_path, field, value):
    policy, _, _, sweeper, _, kwargs = configured(tmp_path)
    kwargs[field] = value
    with pytest.raises(WorkerBrokerError):
        ExecutiveWorkerBroker(None, policy, sweeper, **kwargs)
    assert sweeper.calls == []


@pytest.mark.parametrize("operation", ["start", "status", "collect", "cancel", "validate"])
def test_flat_wire_and_direct_paths_refuse_before_payload_or_provider_work(tmp_path, operation):
    policy, peer, _, sweeper, adapters, kwargs = configured(tmp_path)
    broker = ExecutiveWorkerBroker(None, policy, sweeper, **kwargs)

    async def scenario():
        with pytest.raises(BrokerStateError, match="refuses flat worker operations"):
            await broker.execute(_request(operation, {}, operation), peer=peer)
        with pytest.raises(BrokerStateError, match="refuses flat worker operations"):
            await getattr(broker, "_" + operation)({})
        with pytest.raises(PeerAuthorizationError):
            await broker.execute(_request(operation, {}, "wrong-peer"),
                                 peer=PeerCredentials(peer.uid+1, peer.gid, peer.pid))

    asyncio.run(scenario())
    assert broker.adapter is None and broker.validation_adapter is None
    assert broker._runs == {} and adapters == [] and sweeper.calls == []


def test_existing_operator_materialization_identity_and_shutdown_need_no_flat_adapter(tmp_path):
    policy, peer, profile, sweeper, adapters, kwargs = configured(tmp_path)
    broker = ExecutiveWorkerBroker(None, policy, sweeper, **kwargs)

    async def scenario():
        identity = (await broker.execute(_request("ohf-identity", {}, "identity"), peer=peer))["result"]
        assert identity["binary_sha256"] == kwargs["operator_binary_attestation"].sha256
        assert identity["binary_version"] == kwargs["operator_binary_attestation"].version
        await broker.execute(_request("ohf-validate", {"requested": to_wire(profile)}, "validate"), peer=peer)
        broker.startup_sweep = sweeper.sweep("fixture-startup")
        epoch = SessionEpochRef("epoch-only", "ATT-ONLY", profile.worker_id, 1)
        generation = ProcessGenerationRef("generation-only", "epoch-only", 1, profile.worker_id)
        await broker.execute(_request("ohf-start", _materialization_payload(profile, epoch, generation), "start"), peer=peer)
        assert broker._operator_run is not None
        await broker.shutdown()
        assert broker._operator_run is None
        assert broker.last_sweep.passed

    asyncio.run(scenario())
    assert adapters
    assert sweeper.calls[-1] == "broker_shutdown"
    assert broker.adapter is None and broker.validation_adapter is None


def test_flat_broker_cannot_replace_its_bound_binary_identity(tmp_path):
    old, _, _, sweeper, _ = _fixture(tmp_path)
    with pytest.raises(WorkerBrokerError, match="identity must remain"):
        ExecutiveWorkerBroker(old.adapter, old.policy, sweeper,
                              operator_binary_attestation=dataclasses.replace(
                                  old.adapter.binary, sha256="f" * 64))


@pytest.mark.parametrize("change", [{"sha256": "unknown"}, {"version": ""}])
def test_operator_only_refuses_unobserved_binary_identity(tmp_path, change):
    policy, _, _, sweeper, _, kwargs = configured(tmp_path)
    kwargs["operator_binary_attestation"] = dataclasses.replace(
        kwargs["operator_binary_attestation"], **change)
    with pytest.raises(WorkerBrokerError, match="typed binary attestation"):
        ExecutiveWorkerBroker(None, policy, sweeper, **kwargs)


def test_operator_only_rechecks_revocation_before_factory(tmp_path):
    policy, peer, profile, sweeper, adapters, kwargs = configured(tmp_path)
    revoked = False

    def guard():
        if revoked:
            raise RuntimeError("private revocation diagnostic")

    kwargs["autonomy_guard"] = guard
    broker = ExecutiveWorkerBroker(None, policy, sweeper, **kwargs)

    async def scenario():
        nonlocal revoked
        request = _request("ohf-validate", {"requested": to_wire(profile)}, "profile")
        await broker.execute(request, peer=peer)
        previous = len(adapters)
        revoked = True
        with pytest.raises(BrokerStateError, match="autonomy receipt refused") as failure:
            await broker.execute(request, peer=peer)
        assert "private revocation" not in str(failure.value)
        assert len(adapters) == previous

    asyncio.run(scenario())
