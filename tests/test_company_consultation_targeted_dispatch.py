"""Source-only composed Company MCP / Runtime / Wake / real AF_UNIX journey."""
from __future__ import annotations

import asyncio
import dataclasses
import tempfile
from decimal import Decimal
from pathlib import Path

from common.agent_dialogue_contract_v2 import parse_parent_frame_v2
from control_plane.executive_delegation_identity import derive_delegation_identity
from integrations.company_consultation_dispatch import (
    CallerIdentity, NoSuchRecipient, RecipientBinding, RuntimeConsultationDispatcher,
)
from integrations.company_consultation_targets import TargetedAgentDialogueConsultationPacketCarrier
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_target_resolution import (
    CHANNEL, THREAD_A, THREAD_B, _event_count, _physical, _resolver, _seed, source,
)


def _bindings(seed):
    result = []
    for actor, thread in ((seed.a, THREAD_A), (seed.b, THREAD_B)):
        identity = derive_delegation_identity(seed.runtime.jobs.get_job(actor[0]))
        result.append(fixtures._dialogue_binding(actor, work_ref=source().work_ref,
            commission_ref=source().commission_ref.to_dict(), session_ref=identity.session_ref,
            operation_key=identity.operation_key, thread_ts=thread))
    return result


def _dispatch(seed, bindings, socket, *, caller_index=0, invocations=None):
    caller, recipient = (seed.a, seed.b) if caller_index == 0 else (seed.b, seed.a)
    caller_binding, recipient_binding = bindings[caller_index], bindings[1 - caller_index]
    carrier = TargetedAgentDialogueConsultationPacketCarrier(
        binding_resolver=fixtures._StaticDialogueBindingResolver(caller_binding),
        targets=_resolver(seed), socket_path=socket, timeout_seconds=2,
    )
    return RuntimeConsultationDispatcher(
        runtime=seed.runtime, repository_root=seed.repo,
        caller=CallerIdentity(job_id=caller[0], attempt_id=caller[1], worker_id=caller[2],
            reasoning_surface="codex", binding=caller[3], dialogue_binding=caller_binding),
        recipients=lambda peer: RecipientBinding(actor_ref=dict(recipient_binding.actor_ref),
            recipient_binding=recipient[3], dialogue_binding=recipient_binding),
        packets=carrier, invocations=invocations or fixtures._p1_invocations(),
        _clock=fixtures._ManualClock("2026-09-14T00:00:00Z"),
    )


def _client_and_sources(seed, bindings, *, persist_sources=True):
    policy = fixtures._relay_policy()
    client = fixtures._BoundedInMemorySlackClient(relay_bot_user_id=policy.relay_bot_user_id,
                                                next_timestamp=Decimal("1787961900.000001"))
    for index, binding in enumerate(bindings):
        parent = fixtures._relay_parent(binding, policy)
        client.add_parent(parent)
        if persist_sources:
            _physical(seed, (seed.a, seed.b)[index], binding.thread_ts,
                f"asd-composed-target-{index}-0001",
                parent_fingerprint=parse_parent_frame_v2(parent.text)["fingerprint"])
    return client


def test_composed_distinct_parent_journey_restarts_retries_wakes_and_consumes(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings)
    args = fixtures._consult_args(question="Question for the other orchestrator.",
                                  evidence_refs=[], artifact_revisions=[seed.revision])

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="iac-dsp-", dir="/tmp") as root:
            socket = Path(root) / "r.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                a = _dispatch(seed, bindings, socket)
                question = await fixtures._gateway_with_dispatcher(a).call("company.consult", args)
                assert question["ok"] is True, question
                consultation_id = question["data"]["consultation_ref"]
                assert question["data"]["attention_requested"] is True
                assert fixtures._consultation_event_count(seed.runtime, consultation_id, "INTENT") == 1
            finally:
                await fixtures._stop_relay_service(service, task)

            # All process-local objects are fresh, including the Runtime reader.
            seed.runtime = fixtures._runtime_at(tmp_path / "runtime")
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                b = _dispatch(seed, bindings, socket, caller_index=1)
                gateway = fixtures._gateway_with_dispatcher(b)
                before = _event_count(seed)
                read = await gateway.call("company.consultation", {"consultation_ref": consultation_id})
                assert read["ok"] is True, read
                assert read["data"]["question"]["text"] == args["question"]
                assert _event_count(seed) == before
                reply_args = {"consultation_ref": consultation_id, "answer": "Exact reply to the requester.", "evidence_refs": []}
                blocked = await gateway.call("company.reply", reply_args)
                assert blocked["ok"] is False
                assert _event_count(seed) == before
                fixtures._deliver_and_ack_wake_path(seed.runtime, consultation_id)
                answer = await gateway.call("company.reply", reply_args)
                assert answer["ok"] is True, answer
                repeated = await gateway.call("company.reply", reply_args)
                assert repeated["ok"] is True, repeated
            finally:
                await fixtures._stop_relay_service(service, task)

            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                a = _dispatch(seed, bindings, socket)
                peer_lookups = []
                def peer_no_longer_current(peer_ref):
                    peer_lookups.append(peer_ref)
                    raise NoSuchRecipient("current peer has rotated")
                a.recipients = peer_no_longer_current
                gateway = fixtures._gateway_with_dispatcher(a)
                before = _event_count(seed)
                replay = await gateway.call("company.consult", args)
                assert replay["ok"] is True, replay
                assert replay["data"]["consultation_ref"] == consultation_id
                assert peer_lookups == []
                assert _event_count(seed) == before
                answer = await gateway.call("company.consultation", {"consultation_ref": consultation_id})
                assert answer["ok"] is True, answer
                assert answer["data"]["answer"]["text"] == "Exact reply to the requester."
                assert _event_count(seed) == before
                consumed = await a.consume_answer(consultation_id)
                assert consumed["state"] == "CONSUMED"
                again = await a.consume_answer(consultation_id)
                assert again["inserted"] is False

                # A new invocation must use current resolution, not the old route.
                a.invocations = fixtures._StaticInvocations(dataclasses.replace(
                    a.invocations.current(), invocation_id="new-current-recipient-required"))
                unavailable = await gateway.call("company.consult", args)
                assert unavailable["ok"] is False
                assert len(peer_lookups) == 1
                for event in ("INTENT", "ANSWER_AVAILABLE", "CONSUMED_BY_REQUESTER"):
                    assert fixtures._consultation_event_count(seed.runtime, consultation_id, event) == 1
                assert fixtures._requested_count(seed.runtime, consultation_id) == 1
                assert len(fixtures._answer_attention_requested_records(seed.runtime)) == 1
                for thread in (THREAD_A, THREAD_B):
                    page = await client.fetch_thread(channel_id=CHANNEL, thread_ts=thread, limit=100)
                    assert len(page.messages) == 2
            finally:
                await fixtures._stop_relay_service(service, task)

    asyncio.run(scenario())


def test_composed_missing_destination_creates_no_intent_packet_or_wake(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings, persist_sources=False)
    before = _event_count(seed)

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="iac-dsp-no-", dir="/tmp") as root:
            socket = Path(root) / "r.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                dispatcher = _dispatch(seed, bindings, socket)
                response = await fixtures._gateway_with_dispatcher(dispatcher).call("company.consult",
                    fixtures._consult_args(question="No destination evidence.", evidence_refs=[],
                                           artifact_revisions=[seed.revision]))
                assert response["ok"] is False
                assert _event_count(seed) == before
                for thread in (THREAD_A, THREAD_B):
                    page = await client.fetch_thread(channel_id=CHANNEL, thread_ts=thread, limit=100)
                    assert len(page.messages) == 1
            finally:
                await fixtures._stop_relay_service(service, task)

    asyncio.run(scenario())
