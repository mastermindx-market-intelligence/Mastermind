"""Hierarchy gateway through real temporary Runtime, dispatcher and AF_UNIX.

Roles/membership and native-consumption signals are explicit synthetic fixtures.
Slack is in memory. No live worker, provider, credential or installed service is
used. This tests source composition, never fleet enrollment or production proof.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.fabric_coordination_policy import (
    CoordinationGrant, CoordinationIdentity, CoordinationParticipant,
    CoordinationRefused, CoordinationRole, CoordinationSnapshot,
)
from integrations.fabric_coordination import (
    CoordinationConsultationParties, CoordinationObservation,
    HierarchyCompanyConsultationGateway, HierarchyScopedPeerResolver,
)
from integrations.mastermind_company_mcp.consultation import COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import ConsultationPeer
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_target_resolution import (
    CHANNEL, THREAD_A, THREAD_B, _event_count, _seed,
)
from tests.test_company_consultation_targeted_dispatch import (
    _bindings, _client_and_sources, _dispatch,
)

NOW = 1_789_344_000
TOPIC = "interface-contract"


class FixtureOwner:
    """Synthetic organizational facts, exact actors from the temporary Runtime."""

    def __init__(self, seed):
        self.seed = seed
        participants = []
        peers = []
        for index, actor in enumerate((seed.a, seed.b)):
            lineage = derive_delegation_identity(seed.runtime.jobs.get_job(actor[0]))
            identity = CoordinationIdentity(
                actor[0], actor[1], actor[2],
                actor[3]["binding_id"], actor[3]["binding_generation"],
            )
            participant = CoordinationParticipant(
                identity=identity, role=CoordinationRole.WORKER,
                tenant_ref="fixture-tenant", portfolio_ref="fixture-portfolio",
                project_ref="fixture-project", program_ref=f"{lineage.root_job_id}/{lineage.operation_key}",
                workstream_ref="fixture-workstream", coordination_group_ref="fixture-group",
            )
            participants.append(participant)
            peers.append(ConsultationPeer(
                "peer-" + "a" * 32 if index == 0 else fixtures.PEER_REF,
                f"Fixture peer {index}", participant.program_ref,
                {"kind": "worker_attempt", "job_id": actor[0],
                 "attempt_id": actor[1], "worker_id": actor[2]},
                actor[3],
            ))
        self.participants = tuple(participants)
        self.peers = tuple(peers)
        self.snapshot = CoordinationSnapshot("fixture-revision-1", NOW, NOW + 30, self.participants)
        self.observations = 0
        self.on_observe = None

    def observe(self):
        self.observations += 1
        if self.on_observe is not None:
            self.on_observe(self)
        return CoordinationObservation(self.snapshot, self.peers)

    def parties(self, reference):
        intents = [event for event in self.seed.runtime.events.list_events(
            aggregate_type="consultation", aggregate_id=reference
        ) if event.event_type == "INTENT"]
        if len(intents) != 1:
            raise CoordinationRefused("CONSULTATION_UNAVAILABLE")
        payload = intents[0].payload
        for key, peer in zip(("requester_actor_ref", "recipient_actor_ref"), self.peers):
            if payload.get(key) != dict(peer.actor_ref):
                raise CoordinationRefused("CONSULTATION_UNAVAILABLE")
        return CoordinationConsultationParties(
            reference, self.participants[0].identity, self.participants[1].identity, TOPIC,
        )

    def gateway(self, dispatcher, index=0):
        caller = self.participants[index]
        resolver = HierarchyScopedPeerResolver(
            caller=caller.identity, program_ref=caller.program_ref, topic_ref=TOPIC,
            observe=self.observe, consultation_parties=self.parties, now=lambda: NOW,
        )
        return HierarchyCompanyConsultationGateway(
            peer_resolver=resolver, dispatcher=dispatcher,
            observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
            utc_now=lambda: "2026-09-14T00:00:00Z",
        )


def _request(seed):
    return fixtures._consult_args(
        question="Which immutable interface revision should this worker consume?",
        evidence_refs=[], artifact_revisions=[seed.revision],
    )


def test_hierarchy_question_answer_reaches_existing_runtime_and_socket(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings)
    owner = FixtureOwner(seed)
    jobs_before = tuple(job.job_id for job in seed.runtime.jobs.list_jobs())

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="fabric-journey-", dir="/tmp") as root:
            socket = Path(root) / "relay.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                requester = owner.gateway(_dispatch(seed, bindings, socket))
                peers = await requester.call("company.peers", {})
                assert peers["data"]["peers"] == [owner.peers[1].public_projection()]
                question = await requester.call("company.consult", _request(seed))
                assert question["ok"] is True, question
                reference = question["data"]["consultation_ref"]
                assert question["data"]["attention_requested"] is True
                assert fixtures._consultation_event_count(seed.runtime, reference, "INTENT") == 1

                # Recreate the Runtime reader and scoped gateways from durable records.
                seed.runtime = fixtures._runtime_at(tmp_path / "runtime")
                recipient = owner.gateway(_dispatch(seed, bindings, socket, caller_index=1), 1)
                read = await recipient.call("company.consultation", {"consultation_ref": reference})
                assert read["ok"] is True, read
                assert read["data"]["question"]["text"] == _request(seed)["question"]
                reply_args = {"consultation_ref": reference,
                              "answer": "Consume the exact artifact revision attached to this question.",
                              "evidence_refs": []}
                before = _event_count(seed)
                premature = await recipient.call("company.reply", reply_args)
                assert premature["ok"] is False
                assert _event_count(seed) == before

                # This is a fixture acknowledgment, not a live model-consumption receipt.
                fixtures._deliver_and_ack_wake_path(seed.runtime, reference)
                reply = await recipient.call("company.reply", reply_args)
                assert reply["ok"] is True, reply
                repeated = await recipient.call("company.reply", reply_args)
                assert repeated["ok"] is True, repeated
                requester_dispatcher = _dispatch(seed, bindings, socket)
                requester = owner.gateway(requester_dispatcher)
                result = await requester.call("company.consultation", {"consultation_ref": reference})
                assert result["ok"] is True, result
                assert result["data"]["answer"]["text"] == reply_args["answer"]
                consumed = await requester_dispatcher.consume_answer(reference)
                assert consumed["state"] == "CONSUMED"
                repeated_consume = await requester_dispatcher.consume_answer(reference)
                assert repeated_consume["inserted"] is False
                for event in ("INTENT", "ANSWER_AVAILABLE", "CONSUMED_BY_REQUESTER"):
                    assert fixtures._consultation_event_count(seed.runtime, reference, event) == 1
                assert fixtures._requested_count(seed.runtime, reference) == 1
                assert tuple(job.job_id for job in seed.runtime.jobs.list_jobs()) == jobs_before
                for thread in (THREAD_A, THREAD_B):
                    page = await client.fetch_thread(channel_id=CHANNEL, thread_ts=thread, limit=100)
                    assert len(page.messages) == 2
            finally:
                await fixtures._stop_relay_service(service, task)

    asyncio.run(scenario())


@pytest.mark.parametrize("change", [
    {"coordination_group_ref": "foreign-group"}, {"project_ref": "foreign-project"},
    {"tenant_ref": "foreign-tenant"}, {"active": False},
])
def test_denied_peer_never_creates_runtime_intent_or_socket_packet(tmp_path, monkeypatch, change):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings)
    owner = FixtureOwner(seed)
    owner.snapshot = replace(owner.snapshot, participants=(
        owner.participants[0], replace(owner.participants[1], **change),
    ))
    before = _event_count(seed)

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="fabric-denied-", dir="/tmp") as root:
            socket = Path(root) / "relay.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                gateway = owner.gateway(_dispatch(seed, bindings, socket))
                result = await gateway.call("company.consult", _request(seed))
                assert result["error"]["code"] == "BINDING_UNAVAILABLE", result
                assert _event_count(seed) == before
                for thread in (THREAD_A, THREAD_B):
                    page = await client.fetch_thread(channel_id=CHANNEL, thread_ts=thread, limit=100)
                    assert len(page.messages) == 1
            finally:
                await fixtures._stop_relay_service(service, task)

    asyncio.run(scenario())


def test_grant_revoked_at_dispatch_prevents_real_runtime_effect(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings)
    owner = FixtureOwner(seed)
    grant = CoordinationGrant(
        "fixture-dependency", owner.participants[0].identity, owner.participants[1].identity,
        TOPIC, ("fixture-project",), NOW - 1, NOW + 60,
    )
    owner.snapshot = replace(owner.snapshot, participants=(
        owner.participants[0], replace(owner.participants[1], coordination_group_ref="other-group"),
    ), grants=(grant,))

    def revoke(observed):
        if observed.observations == 2:
            observed.snapshot = replace(observed.snapshot, grants=(replace(grant, revoked=True),))
    owner.on_observe = revoke
    before = _event_count(seed)

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="fabric-revoked-", dir="/tmp") as root:
            socket = Path(root) / "relay.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                result = await owner.gateway(_dispatch(seed, bindings, socket)).call("company.consult", _request(seed))
                assert result["error"]["code"] == "BINDING_UNAVAILABLE", result
                assert owner.observations == 2
                assert _event_count(seed) == before
            finally:
                await fixtures._stop_relay_service(service, task)

    asyncio.run(scenario())


def test_lost_response_preserves_effect_unknown_and_reconciles_without_resend(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings)
    owner = FixtureOwner(seed)
    completed = []

    async def scenario():
        with tempfile.TemporaryDirectory(prefix="fabric-lost-", dir="/tmp") as root:
            socket = Path(root) / "relay.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                dispatcher = _dispatch(seed, bindings, socket)

                async def lose_response(name, request):
                    response = await dispatcher(name, request)
                    completed.append(response)
                    raise ConnectionError("simulated response loss after the real owner completed")

                response = await owner.gateway(lose_response).call("company.consult", _request(seed))
                assert response["error"]["code"] == "EFFECT_UNKNOWN", response
                assert len(completed) == 1  # The gateway must not auto-replay.
                reference = completed[0]["result"]["consultation_ref"]
                assert fixtures._consultation_event_count(seed.runtime, reference, "INTENT") == 1
                assert fixtures._requested_count(seed.runtime, reference) == 1
                before = _event_count(seed)
                read = await owner.gateway(dispatcher).call(
                    "company.consultation", {"consultation_ref": reference},
                )
                assert read["ok"] is True, read
                assert read["data"]["question"]["text"] == _request(seed)["question"]
                assert _event_count(seed) == before
                page = await client.fetch_thread(channel_id=CHANNEL, thread_ts=THREAD_B, limit=100)
                assert len(page.messages) == 2
            finally:
                await fixtures._stop_relay_service(service, task)

    asyncio.run(scenario())
