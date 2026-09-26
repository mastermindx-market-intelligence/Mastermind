"""P1-R1 source-only carrier proof; target facts below are hermetic fixtures.

The real AF_UNIX service/engine are exercised, but no live Slack, provider,
Runtime admission, peer discovery, or production target resolver is claimed.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import importlib
import importlib.util
import json
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from common.agent_dialogue_consultation_contract import build_consultation
from control_plane.executive_runtime import StateConflict
from integrations.company_consultation_dispatch import (
    ConsultationPacketCarrierUnknown,
    ConsultationPacketCommitAborted,
    ConsultationPacketEffectUnknown,
)
from integrations.slack_agent_dialogue.service import DialogueServiceError
from tests.test_company_inbox_iac1 import (
    _binding,
    _BoundedInMemorySlackClient,
    _dialogue_binding,
    _packet_frame,
    _relay_parent,
    _relay_policy,
    _start_relay_service,
    _StaticDialogueBindingResolver,
    _stop_relay_service,
)


def _api():
    name = "integrations.company_consultation_targets"
    assert importlib.util.find_spec(name) is not None, (
        "P1-R1 has no trusted distinct-parent packet carrier yet"
    )
    return importlib.import_module(name)


def _parties():
    a = ("job-requester", "attempt-requester", "worker-requester", _binding("a"))
    b = ("job-recipient", "attempt-recipient", "worker-recipient", _binding("b"))
    c = ("job-foreign", "attempt-foreign", "worker-foreign", _binding("c"))
    bindings = (
        _dialogue_binding(a),
        _dialogue_binding(
            b, session_ref="asd-session-iac1-p1-recipient-0002",
            operation_key="iac-p1r1-recipient-20260926-sol-001",
            thread_ts="1787961700.000001",
        ),
        _dialogue_binding(c),
    )
    return a, b, c, bindings


def _target(binding):
    api = _api()
    facts = {
        "actor_ref": dict(binding.actor_ref),
        "work_ref": binding.work_ref,
        "commission_ref": dict(binding.commission_ref),
        "session_ref": binding.session_ref,
        "operation_key": binding.operation_key,
        "watch_mode": binding.watch_mode,
        "thread_ts": binding.thread_ts,
    }
    return api.ConsultationDeliveryTarget(
        **facts,
        evidence_digest=hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest(),
    )


class _ExactFixtureAccess:
    """Test-only stand-in for exact persisted Executive/Wake party facts."""

    def __init__(self, question, bindings):
        self.question = copy.deepcopy(question)
        self.bindings = bindings
        self.calls = 0
        self.transform = None

    def resolve(self, consultation_id, *, purpose, frame=None):
        self.calls += 1
        assert consultation_id == self.question["consultation_id"]
        access = _api().ConsultationPacketAccess(
            target=_target(self.bindings[1 if purpose == "QUESTION" else 0]),
            requester_actor_ref=self.question["requester_actor_ref"],
            recipient_actor_ref=self.question["recipient_actor_ref"],
        )
        return self.transform(access, self.calls) if self.transform else access


class _Service:
    def __init__(self, frame=None, *, error=None):
        self.frame = frame
        self.error = error
        self.calls = []
        self.commits = 0
        self.after_read = None

    async def __call__(self, socket_path, request, *, before_write=None, **kwargs):
        self.calls.append(copy.deepcopy(request))
        if before_write is not None:
            await before_write()
            self.commits += 1
        if self.error:
            raise DialogueServiceError(self.error)
        if request["operation"] == "send_consultation_packet":
            packet = request["args"]["message"]
            return {"ok": True, "result": {
                "message_key": packet["message_key"],
                "fingerprint": packet["fingerprint"],
                "thread_ts": request["args"]["thread_ts"],
            }}
        if self.after_read:
            self.after_read()
        return {"ok": True, "result": None if self.frame is None else {
            "packet": self.frame,
            "primary_ts": "1787961700.000002",
            "duplicate_timestamps": [],
        }}


async def _noop():
    return None


def _setup(*, purpose="QUESTION", actor=None, frame=None, error=None):
    a, b, c, bindings = _parties()
    packet = _packet_frame(a, b, purpose=purpose)
    question = _packet_frame(a, b)
    caller = actor if actor is not None else (0 if purpose == "QUESTION" else 1)
    binding = _StaticDialogueBindingResolver(bindings[caller])
    targets = _ExactFixtureAccess(question, bindings)
    service = _Service(frame=frame, error=error)
    carrier = _api().TargetedAgentDialogueConsultationPacketCarrier(
        binding_resolver=binding, targets=targets,
        socket_path=Path("/tmp/iac-p1r1-test-only.sock"), service_call=service,
    )
    return carrier, service, targets, binding, packet, bindings


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_sender_authority_and_physical_destination_are_separate(purpose):
    carrier, service, targets, binding, packet, bindings = _setup(purpose=purpose)
    asyncio.run(getattr(carrier, "put_" + purpose.lower())(
        packet["consultation_id"], packet, before_commit=_noop,
    ))
    args = service.calls[0]["args"]
    destination = bindings[1 if purpose == "QUESTION" else 0]
    assert args["thread_ts"] == destination.thread_ts
    assert args["context"]["operation_key"] == destination.operation_key
    assert args["context"]["actor_ref"] == dict(destination.actor_ref)
    assert args["message"] == packet
    assert service.commits == 1


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
@pytest.mark.parametrize("actor", ["destination", "foreign"])
def test_destination_or_foreign_binding_never_grants_sender_authority(purpose, actor):
    wrong = 2 if actor == "foreign" else (1 if purpose == "QUESTION" else 0)
    carrier, service, targets, binding, packet, bindings = _setup(purpose=purpose, actor=wrong)
    with pytest.raises(StateConflict):
        asyncio.run(getattr(carrier, "put_" + purpose.lower())(
            packet["consultation_id"], packet, before_commit=_noop,
        ))
    assert service.calls == []
    assert service.commits == 0


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_wrong_target_actor_is_refused_before_transport(purpose):
    carrier, service, targets, binding, packet, bindings = _setup(purpose=purpose)
    targets.transform = lambda access, count: dataclasses.replace(access, target=_target(bindings[2]))
    with pytest.raises(StateConflict):
        asyncio.run(getattr(carrier, "put_" + purpose.lower())(
            packet["consultation_id"], packet, before_commit=_noop,
        ))
    assert service.calls == []


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
@pytest.mark.parametrize("present", [False, True])
def test_nonparty_read_cannot_probe_absence_or_fetch_packet(purpose, present):
    a, b, _, _ = _parties()
    frame = _packet_frame(a, b, purpose=purpose) if present else None
    carrier, service, _, _, packet, _ = _setup(purpose=purpose, actor=2, frame=frame)
    with pytest.raises(StateConflict):
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert service.calls == []


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
@pytest.mark.parametrize("caller", [0, 1])
def test_either_exact_party_reads_original_destination_without_route_cache(purpose, caller):
    a, b, _, _ = _parties()
    frame = _packet_frame(a, b, purpose=purpose)
    carrier, service, _, _, _, bindings = _setup(purpose=purpose, actor=caller, frame=frame)
    assert asyncio.run(getattr(carrier, "get_" + purpose.lower())(frame["consultation_id"])) == frame
    assert service.calls[0]["args"]["thread_ts"] == bindings[1 if purpose == "QUESTION" else 0].thread_ts
    assert service.commits == 0


@pytest.mark.parametrize("stage", ["ready", "after_intent"])
@pytest.mark.parametrize("change", ["caller", "target"])
def test_binding_change_before_commit_aborts_without_packet(stage, change):
    carrier, service, targets, binding, packet, bindings = _setup()
    admitted = []

    def change_identity():
        if change == "caller":
            binding.binding = bindings[2]
        else:
            targets.transform = lambda access, count: dataclasses.replace(
                access, target=dataclasses.replace(access.target, thread_ts="1787961800.000001")
            )

    if stage == "ready":
        original = targets.resolve
        def resolve(*args, **kwargs):
            access = original(*args, **kwargs)
            if targets.calls == 1:
                change_identity()
            return access
        targets.resolve = resolve

    async def admit():
        admitted.append("INTENT")
        if stage == "after_intent":
            change_identity()

    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        asyncio.run(carrier.put_question(packet["consultation_id"], packet, before_commit=admit))
    assert service.commits == 0
    assert admitted == ([] if stage == "ready" else ["INTENT"])


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_missing_or_ambiguous_target_facts_do_not_become_absence(purpose):
    carrier, service, targets, _, packet, _ = _setup(purpose=purpose)
    def unavailable(*args, **kwargs):
        raise RuntimeError("AMBIGUOUS_PRIVATE_SOURCE")
    targets.resolve = unavailable
    with pytest.raises(ConsultationPacketCarrierUnknown) as caught:
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert "PRIVATE" not in str(caught.value)
    assert service.calls == []


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_tampered_packet_parties_are_not_returned(purpose):
    a, b, c, _ = _parties()
    frame = _packet_frame(a, c, purpose=purpose)
    carrier, service, _, _, packet, _ = _setup(purpose=purpose, frame=frame)
    with pytest.raises(ConsultationPacketCarrierUnknown):
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert service.commits == 0


@pytest.mark.parametrize("purpose", ["QUESTION", "ANSWER"])
def test_read_identity_drift_suppresses_even_absence(purpose):
    carrier, service, _, binding, packet, bindings = _setup(purpose=purpose)
    service.after_read = lambda: setattr(binding, "binding", bindings[2])
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        asyncio.run(getattr(carrier, "get_" + purpose.lower())(packet["consultation_id"]))
    assert service.commits == 0


@pytest.mark.parametrize("error,expected", [
    ("SEND_EFFECT_UNKNOWN", ConsultationPacketEffectUnknown),
    ("SERVICE_UNAVAILABLE", ConsultationPacketCarrierUnknown),
])
def test_transport_uncertainty_is_not_reclassified_as_safe_absence(error, expected):
    carrier, service, _, _, packet, _ = _setup(error=error)
    with pytest.raises(expected):
        asyncio.run(carrier.put_question(packet["consultation_id"], packet, before_commit=_noop))
    assert len(service.calls) == 1


def test_new_question_preintent_read_uses_frame_without_remembering_route():
    carrier, service, _, _, packet, bindings = _setup()
    assert asyncio.run(carrier.get_question_for(packet)) is None
    assert service.calls[0]["args"]["thread_ts"] == bindings[1].thread_ts
    assert service.commits == 0


def test_owner_abort_is_preserved_without_commit():
    carrier, service, _, _, packet, _ = _setup()
    async def abort():
        raise ConsultationPacketCommitAborted("intent lost the race")
    with pytest.raises(ConsultationPacketCommitAborted):
        asyncio.run(carrier.put_question(packet["consultation_id"], packet, before_commit=abort))
    assert service.commits == 0


def test_delivery_target_is_immutable_and_is_not_a_dialogue_grant():
    _, _, _, _, _, bindings = _setup()
    target = _target(bindings[1])
    with pytest.raises(TypeError):
        target.actor_ref["worker_id"] = "wrong"
    with pytest.raises(TypeError):
        target.commission_ref["path"] = "wrong"
    assert not hasattr(target, "allowed_message_types")
    assert not hasattr(target, "binding_id")


def test_real_af_unix_distinct_parent_roundtrip_and_restart():
    api = _api()
    a, b, _, bindings = _parties()
    question = _packet_frame(a, b)
    answer = _packet_frame(a, b, purpose="ANSWER")

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="iac-r1-", dir="/tmp") as root:
            socket = Path(root) / "r.sock"
            client = _BoundedInMemorySlackClient(
                relay_bot_user_id=_relay_policy().relay_bot_user_id,
                next_timestamp=Decimal("1787961900.000001"),
            )
            for binding in bindings[:2]:
                client.add_parent(_relay_parent(binding, _relay_policy()))
            admitted = []
            async def gate():
                admitted.append("admitted")

            def carrier(index):
                return api.TargetedAgentDialogueConsultationPacketCarrier(
                    binding_resolver=_StaticDialogueBindingResolver(bindings[index]),
                    targets=_ExactFixtureAccess(question, bindings),
                    socket_path=socket, timeout_seconds=2,
                )

            service, task = await _start_relay_service(socket_path=socket, client=client)
            try:
                await carrier(0).put_question(question["consultation_id"], question, before_commit=gate)
                assert await carrier(1).get_question(question["consultation_id"]) == question
            finally:
                await _stop_relay_service(service, task)

            service, task = await _start_relay_service(socket_path=socket, client=client)
            try:
                assert await carrier(1).get_question(question["consultation_id"]) == question
                await carrier(1).put_answer(answer["consultation_id"], answer, before_commit=gate)
                assert await carrier(0).get_answer(answer["consultation_id"]) == answer
                # Exact replay uses the Relay's existing deduplication, not a carrier cache.
                await carrier(0).put_question(question["consultation_id"], question, before_commit=gate)
                await carrier(1).put_answer(answer["consultation_id"], answer, before_commit=gate)
                assert admitted == ["admitted", "admitted"]
                page_a = await client.fetch_thread(channel_id=_relay_policy().channel_id,
                    thread_ts=bindings[0].thread_ts, limit=100)
                page_b = await client.fetch_thread(channel_id=_relay_policy().channel_id,
                    thread_ts=bindings[1].thread_ts, limit=100)
                assert len(page_a.messages) == 2  # A parent + ANSWER only.
                assert len(page_b.messages) == 2  # B parent + QUESTION only.
            finally:
                await _stop_relay_service(service, task)

    asyncio.run(scenario())
