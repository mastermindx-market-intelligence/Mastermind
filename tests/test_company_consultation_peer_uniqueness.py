"""Reject ambiguous current peer evidence before Company consultation dispatch."""
from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
    CompanyConsultationGateway,
)
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import (
    CompanyConsultationPeerResolver,
    ConsultationPeer,
    ConsultationPeerRefused,
)


def _peer() -> ConsultationPeer:
    return ConsultationPeer(
        peer_ref="peer-" + "a" * 32,
        display_name="Bounded recipient",
        program_ref="JOB-100/executive-communications",
        actor_ref={"kind": "worker_attempt", "job_id": "JOB-200",
                   "attempt_id": "ATT-200", "worker_id": "codex-att-200"},
        binding={"binding_id": "bind-" + "a" * 32,
                 "binding_generation": 1, "reasoning_surface": "codex"},
    )


def _conflicting_peer(kind: str) -> ConsultationPeer:
    peer = _peer()
    if kind == "actor":
        return replace(peer, actor_ref={**peer.actor_ref, "attempt_id": "ATT-201",
                                       "worker_id": "codex-att-201"})
    if kind == "generation":
        return replace(peer, binding={**peer.binding, "binding_generation": 2})
    if kind == "binding":
        return replace(peer, binding={**peer.binding, "binding_id": "bind-" + "b" * 32})
    return replace(peer, display_name="Conflicting public identity")


@pytest.mark.parametrize("kind", ["actor", "generation", "binding", "display"])
@pytest.mark.parametrize("reverse", [False, True])
def test_one_peer_identity_never_selects_first_conflicting_record(kind, reverse):
    peer, other = _peer(), _conflicting_peer(kind)
    rows = [other, peer] if reverse else [peer, other]
    with pytest.raises(ConsultationPeerRefused) as failure:
        CompanyConsultationPeerResolver(rows).resolve(peer.peer_ref, program_ref=peer.program_ref)
    assert failure.value.code == "AMBIGUOUS"


def test_duplicate_records_are_not_independent_current_identity_evidence():
    peer = _peer()
    with pytest.raises(ConsultationPeerRefused) as failure:
        CompanyConsultationPeerResolver([peer, replace(peer)]).resolve(
            peer.peer_ref, program_ref=peer.program_ref)
    assert failure.value.code == "AMBIGUOUS"


def test_expected_actor_does_not_authorize_filtering_an_ambiguous_snapshot():
    peer = _peer()
    resolver = CompanyConsultationPeerResolver(
        [peer, _conflicting_peer("actor")],
        expected_actor_ref=peer.actor_ref, expected_binding=peer.binding)
    with pytest.raises(ConsultationPeerRefused) as failure:
        resolver.resolve(peer.peer_ref, program_ref=peer.program_ref)
    assert failure.value.code == "AMBIGUOUS"


@pytest.mark.parametrize("selector", ["peer_ref", "display_name"])
def test_unique_authorized_peer_still_resolves(selector):
    peer = _peer()
    assert CompanyConsultationPeerResolver([peer]).resolve(
        getattr(peer, selector), program_ref=peer.program_ref) is peer


def test_another_program_does_not_make_the_authorized_scope_ambiguous():
    peer = _peer()
    foreign = replace(_conflicting_peer("actor"), program_ref="JOB-900/foreign")
    assert CompanyConsultationPeerResolver([foreign, peer]).resolve(
        peer.peer_ref, program_ref=peer.program_ref) is peer


@pytest.mark.parametrize("reverse", [False, True])
def test_gateway_refuses_conflicting_peer_before_any_dispatch(reverse):
    peer, other = _peer(), _conflicting_peer("actor")
    rows = [other, peer] if reverse else [peer, other]
    calls = []

    async def dispatch(operation, request):
        calls.append((operation, request))
        return {"ok": True, "result": {}}

    gateway = CompanyConsultationGateway(
        peer_resolver=CompanyConsultationPeerResolver(rows), dispatcher=dispatch,
        observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        utc_now=lambda: "2026-09-30T00:00:00Z", program_ref=peer.program_ref)
    response = asyncio.run(gateway.call("company.consult", {
        "to": peer.peer_ref, "question": "Resolve exactly one recipient.",
        "evidence_refs": [], "artifact_revisions": []}))
    assert response["ok"] is False
    assert response["error"]["code"] == "AMBIGUOUS"
    assert response["data"] == {"peers": []}
    assert calls == []
