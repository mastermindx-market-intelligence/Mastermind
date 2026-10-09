"""Provider-free flat Claude realm revalidation at the incumbent Broker boundary.

This does not enroll a subscription or arm a production provider descriptor.
"""
from __future__ import annotations

import asyncio
import dataclasses

import pytest

from control_plane.executive_worker_broker import (
    BrokerStateError,
    ExecutiveWorkerBroker,
    WorkerBrokerError,
)
from control_plane import worker_adapter
from control_plane.worker_adapter import construct_reviewed_adapter
from test_executive_claude_worker import (
    _EXACT_MODEL,
    _FIXTURE_VERSION,
    _fixture_claude_binary,
    _observer_for,
)
from test_executive_worker_broker import _fixture, _reviewed_codex_adapter


def _native_fixture(tmp_path, monkeypatch, guard):
    original, _fake, sweeper, _peer, launch_spec = _fixture(tmp_path)
    binary = _fixture_claude_binary(tmp_path)
    primary = construct_reviewed_adapter(
        "claude-code",
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=_observer_for(binary),
    )
    validation = _reviewed_codex_adapter(tmp_path / "validator")
    old_descriptor = worker_adapter.ADAPTER_DESCRIPTORS["claude-code"]
    monkeypatch.setitem(
        worker_adapter.ADAPTER_DESCRIPTORS,
        "claude-code",
        dataclasses.replace(old_descriptor, implemented=True),
    )
    broker = ExecutiveWorkerBroker(
        primary,
        original.policy,
        sweeper,
        adapter_id="claude-code",
        validation_adapter=validation,
        validation_adapter_id="codex-cli",
        operator_harness_armed=False,
        native_realm_guard=guard,
    )

    class RecordingAdapter:
        starts = 0

        async def start(self, spec):
            self.starts += 1
            raise AssertionError("model invocation would have started")

    recorder = RecordingAdapter()
    broker.adapter = recorder
    payload = {"launch_spec": launch_spec, "validation_commands": [["/usr/bin/true"]]}
    return broker, recorder, payload, sweeper


def test_sealed_claude_requires_guard_not_operator_autonomy(tmp_path, monkeypatch):
    with pytest.raises(WorkerBrokerError, match="native realm guard"):
        _native_fixture(tmp_path, monkeypatch, None)


def test_revoked_native_realm_refuses_before_flat_start_and_quarantines(
    tmp_path, monkeypatch
):
    invoked = []

    def revoked():
        invoked.append("guard")
        raise RuntimeError("redacted revoked realm")

    broker, recorder, payload, sweeper = _native_fixture(
        tmp_path, monkeypatch, revoked
    )
    assert broker.operator_harness_armed is False

    async def scenario():
        with pytest.raises(BrokerStateError, match="native realm"):
            await broker._start(payload)
        with pytest.raises(BrokerStateError, match="native_realm_refused"):
            await broker._start(payload)

    asyncio.run(scenario())
    assert invoked == ["guard"]
    assert recorder.starts == 0
    assert sweeper.calls == []
    assert broker._quarantined_reason == "native_realm_refused"


def test_current_native_realm_is_checked_on_every_new_start(tmp_path, monkeypatch):
    calls = []

    def allowed():
        calls.append("fresh")

    broker, recorder, payload, _sweeper = _native_fixture(
        tmp_path, monkeypatch, allowed
    )

    async def scenario():
        with pytest.raises(AssertionError, match="model invocation"):
            await broker._start(payload)

    asyncio.run(scenario())
    assert calls == ["fresh"]
    assert recorder.starts == 1


def test_codex_broker_rejects_foreign_native_realm_guard(tmp_path):
    broker, _adapter, sweeper, _peer, _spec = _fixture(tmp_path)
    reviewed = _reviewed_codex_adapter(tmp_path / "codex")
    with pytest.raises(WorkerBrokerError, match="native realm guard"):
        ExecutiveWorkerBroker(
            reviewed,
            broker.policy,
            sweeper,
            native_realm_guard=lambda: None,
        )


def test_revocation_after_accepted_boot_still_blocks_first_worker_start(
    tmp_path, monkeypatch
):
    ready = [True]
    observations = []

    def observed_host_realm():
        observations.append(ready[0])
        if not ready[0]:
            raise RuntimeError("native config/enrollment changed")

    broker, recorder, payload, sweeper = _native_fixture(
        tmp_path, monkeypatch, observed_host_realm
    )
    broker.initialize()
    assert observations == [True]
    ready[0] = False

    async def scenario():
        with pytest.raises(BrokerStateError, match="native realm"):
            await broker._start(payload)

    asyncio.run(scenario())
    assert observations == [True, False]
    assert recorder.starts == 0
    assert sweeper.calls == ["broker_startup"]
    assert broker._quarantined_reason == "native_realm_refused"
