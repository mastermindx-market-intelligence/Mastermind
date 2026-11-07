"""Real Company gateway composition; the dispatcher is explicitly a test double."""
import asyncio
from dataclasses import replace
import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationGrant, CoordinationIdentity as Identity,
    CoordinationParticipant as Participant, CoordinationRefused,
    CoordinationRole as Role, CoordinationSnapshot as Snapshot,
)
from integrations.mastermind_company_mcp.consultation import (
    COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
)
from integrations.fabric_coordination import (
    CoordinationConsultationParties as Parties, CoordinationObservation as Observation,
    HierarchyCompanyConsultationGateway as Gateway,
    HierarchyScopedPeerResolver as Resolver,
)
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import ConsultationPeer

NOW = 1000
REFERENCE = "consult-" + "a" * 32


def participant(n, **kwargs):
    identity = Identity(f"JOB-{n}", "ATT-" + f"{n:032x}", f"worker-{n}", "bind-" + f"{n:040x}", 1)
    values = dict(identity=identity, role=Role.WORKER, tenant_ref="tenant-a", portfolio_ref="portfolio-a", project_ref="project-a", program_ref=f"JOB-{n}/task-{n}", workstream_ref="workstream-a", coordination_group_ref="group-a")
    values.update(kwargs)
    return Participant(**values)


def peer(p, surface="codex"):
    n = int(p.identity.job_id.split("-")[1])
    return ConsultationPeer(
        "peer-" + f"{n:032x}", f"participant-{n}", p.program_ref,
        {"kind":"worker_attempt", "job_id":p.identity.job_id, "attempt_id":p.identity.attempt_id, "worker_id":p.identity.worker_id},
        {"binding_id":p.identity.binding_id, "binding_generation":p.identity.binding_generation, "reasoning_surface":surface},
    )


def observation(*participants, grants=(), surfaces=None):
    surfaces = surfaces or ["codex"] * len(participants)
    return Observation(Snapshot("rev-1", NOW, NOW+30, tuple(participants), grants), tuple(peer(p,s) for p,s in zip(participants,surfaces)))


class Owner:
    def __init__(self, *participants, grants=(), surfaces=None):
        self.value = observation(*participants, grants=grants, surfaces=surfaces)
        self.observations = 0
        self.calls = []
        self.parties = Parties(REFERENCE, participants[0].identity, participants[1].identity, "topic-a")
        self.error = None
        self.on_observe = None

    def observe(self):
        self.observations += 1
        if self.on_observe:
            self.on_observe(self.observations)
        return self.value

    async def dispatch(self, name, request):
        self.calls.append((name,request))
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return {"ok":True, "result":{"test_double_only":True, "consultation_ref":REFERENCE}}

    def gateway(self, caller, **kwargs):
        resolver = Resolver(caller=caller.identity, program_ref=caller.program_ref, topic_ref="topic-a", observe=self.observe, consultation_parties=lambda ref: self.parties, now=lambda: NOW)
        return Gateway(peer_resolver=resolver, dispatcher=self.dispatch, observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST, utc_now=lambda:"2026-10-10T12:00:00Z", **kwargs)


def request(p):
    return {"to":peer(p).peer_ref, "question":"Which immutable interface revision should this task consume?", "evidence_refs":[], "artifact_revisions":[]}


def call(gateway, name, arguments):
    return asyncio.run(gateway.call(name, arguments))


def test_discovery_only_shows_permitted_peers_not_self_or_foreign():
    a,b = participant(1),participant(2)
    hidden = participant(3,project_ref="project-b")
    owner = Owner(a,b,hidden)
    result = call(owner.gateway(a), "company.peers", {})
    assert result["ok"] is True
    assert result["data"]["peers"] == [peer(b).public_projection()]
    assert owner.calls == []


@pytest.mark.parametrize("surface", ["codex","claude","grok-bot"])
def test_admitted_provider_neutral_send_reaches_existing_dispatcher(surface):
    a,b = participant(1),participant(2)
    owner = Owner(a,b,surfaces=["codex",surface])
    gateway = owner.gateway(a)
    result = call(gateway,"company.consult",request(b))
    assert result["ok"] is True
    assert len(owner.calls) == 1
    assert owner.observations == 2
    payload = owner.calls[0][1]
    assert payload["budget"]["max_forward_hops"] == 0
    assert payload["budget"]["max_answers"] == 1
    assert gateway.peer_resolver._selection.get() is None


@pytest.mark.parametrize("change", [
    {"project_ref":"other"}, {"workstream_ref":"other"},
    {"coordination_group_ref":"other"}, {"tenant_ref":"other"},
    {"portfolio_ref":"other"}, {"role":Role.PROJECT_CEO}, {"active":False},
])
def test_direct_guessed_target_cannot_bypass_discovery(change):
    a,b = participant(1),participant(2,**change)
    owner = Owner(a,b)
    result = call(owner.gateway(a),"company.consult",request(b))
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "BINDING_UNAVAILABLE"
    assert owner.calls == []


@pytest.mark.parametrize("field,value", [("role","project_ceo"),("host","ubuntu1"),("action","approve"),("forward_to","peer-forged"),("caller",{"role":"project_ceo"})])
def test_tool_arguments_cannot_author_role_or_forwarding(field,value):
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    result=call(owner.gateway(a),"company.consult",{**request(b),field:value})
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_REQUEST"
    assert owner.calls == []


def test_rebinding_between_selection_and_dispatch_is_refused_without_send():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    replacement=replace(b,identity=replace(b.identity,binding_generation=2))
    owner.on_observe=lambda n: setattr(owner,"value",observation(a,replacement)) if n==2 else None
    result=call(owner.gateway(a),"company.consult",request(b))
    assert result["ok"] is False
    assert result["error"]["code"] == "BINDING_UNAVAILABLE"
    assert owner.calls == []


def test_revocation_between_selection_and_dispatch_is_refused():
    a,b=participant(1),participant(2,project_ref="project-b")
    grant=CoordinationGrant("grant-1",a.identity,b.identity,"topic-a",("project-a","project-b"),NOW-1,NOW+10)
    owner=Owner(a,b,grants=(grant,))
    owner.on_observe=lambda n: setattr(owner,"value",observation(a,b,grants=(replace(grant,revoked=True),))) if n==2 else None
    result=call(owner.gateway(a),"company.consult",request(b))
    assert result["ok"] is False
    assert owner.calls == []


def test_cross_project_exchange_requires_exact_bilateral_topic_grant():
    a,b=participant(1),participant(2,project_ref="project-b")
    grant=CoordinationGrant("grant-1",a.identity,b.identity,"topic-a",("project-a","project-b"),NOW-1,NOW+10)
    owner=Owner(a,b,grants=(grant,))
    assert call(owner.gateway(a),"company.consult",request(b))["ok"] is True
    assert call(owner.gateway(b),"company.reply",{"consultation_ref":REFERENCE,"answer":"Use revision recorded in the artifact.","evidence_refs":[]})["ok"] is True
    assert len(owner.calls)==2


@pytest.mark.parametrize("tool",["company.reply","company.consultation"])
def test_foreign_consultation_cannot_be_read_or_answered(tool):
    a,b,c=participant(1),participant(2),participant(3)
    owner=Owner(a,b,c)
    args={"consultation_ref":REFERENCE}
    if tool=="company.reply": args.update(answer="Forged answer",evidence_refs=[])
    result=call(owner.gateway(c),tool,args)
    assert result["ok"] is False
    assert owner.calls == []


def test_requester_cannot_impersonate_answering_recipient():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    result=call(owner.gateway(a),"company.reply",{"consultation_ref":REFERENCE,"answer":"Forged answer", "evidence_refs":[]})
    assert result["ok"] is False
    assert owner.calls == []


@pytest.mark.parametrize("caller_index",[0,1])
def test_each_exact_party_can_read_its_consultation(caller_index):
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    assert call(owner.gateway((a,b)[caller_index]),"company.consultation",{"consultation_ref":REFERENCE})["ok"] is True


def test_replayed_old_consultation_binding_cannot_be_answered():
    a,b=participant(1),participant(2)
    changed=replace(b,identity=replace(b.identity,attempt_id="ATT-"+"f"*32,binding_generation=2))
    owner=Owner(a,changed)
    owner.parties=Parties(REFERENCE,a.identity,b.identity,"topic-a")
    result=call(owner.gateway(changed),"company.reply",{"consultation_ref":REFERENCE,"answer":"Old message", "evidence_refs":[]})
    assert result["ok"] is False
    assert owner.calls == []


def test_unknown_post_dispatch_effect_is_not_retried_or_downgraded():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    owner.error=TimeoutError("test transport loss")
    result=call(owner.gateway(a),"company.consult",request(b))
    assert result["error"]["code"] == "EFFECT_UNKNOWN"
    assert len(owner.calls)==1


def test_missing_owner_evidence_is_not_empty_success_or_dispatch():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    owner.on_observe=lambda _: (_ for _ in ()).throw(RuntimeError("private diagnostic"))
    result=call(owner.gateway(a),"company.peers",{})
    assert result["ok"] is False
    assert "private diagnostic" not in str(result)
    assert owner.calls == []


def test_duplicate_opaque_peer_rejected_before_gateway():
    a,b=participant(1),participant(2)
    with pytest.raises(CoordinationRefused):
        Observation(Snapshot("r",NOW,NOW+30,(a,b)),(peer(b),peer(b)))


def test_owner_peer_dicts_are_frozen_at_observation_boundary():
    a,b=participant(1),participant(2)
    original=peer(b)
    value=Observation(Snapshot("r",NOW,NOW+30,(a,b)),(original,))
    original.actor_ref["worker_id"]="forged"
    assert value.peers[0].actor_ref["worker_id"]==b.identity.worker_id
    with pytest.raises(TypeError): value.peers[0].binding["binding_generation"]=99


def test_missing_or_stale_schema_attestation_never_dispatches():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    gateway=owner.gateway(a)
    gateway.observed_tool_schema_digest="wrong"
    result=call(gateway,"company.consult",request(b))
    assert result["error"]["code"]=="CAPABILITY_NOT_ATTESTED"
    assert owner.calls==[]


def test_concurrent_calls_keep_selection_request_local():
    a,b,c=participant(1),participant(2),participant(3)
    owner=Owner(a,b,c)
    gateway=owner.gateway(a)
    async def run():
        return await asyncio.gather(gateway.call("company.consult",request(b)),gateway.call("company.consult",request(c)))
    results=asyncio.run(run())
    assert all(result["ok"] for result in results)
    assert {r[1]["semantic"]["to"] for r in owner.calls}=={peer(b).peer_ref,peer(c).peer_ref}
    assert gateway.peer_resolver._selection.get() is None


@pytest.mark.parametrize("result", [False, True, {}, "allowed"])
def test_nonvoid_authorization_callback_never_dispatches(result):
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    gateway=owner.gateway(a)
    gateway.before_dispatch=lambda *_: result
    response=call(gateway,"company.consult",request(b))
    assert response["error"]["code"]=="BINDING_UNAVAILABLE"
    assert owner.calls==[]


def test_async_authorization_callback_is_rejected_at_construction():
    from integrations.mastermind_company_mcp.consultation import CompanyConsultationGateway
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    async def guard(*_):
        return None
    with pytest.raises(TypeError):
        CompanyConsultationGateway(peer_resolver=owner.gateway(a).peer_resolver,
            dispatcher=owner.dispatch, observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
            utc_now=lambda:"2026-10-10T12:00:00Z", program_ref=a.program_ref, before_dispatch=guard)


def test_async_callable_object_is_rejected_at_construction():
    from integrations.mastermind_company_mcp.consultation import CompanyConsultationGateway
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    class Guard:
        async def __call__(self,*_):
            return None
    with pytest.raises(TypeError):
        CompanyConsultationGateway(peer_resolver=owner.gateway(a).peer_resolver,
            dispatcher=owner.dispatch, observed_tool_schema_digest=COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
            utc_now=lambda:"2026-10-10T12:00:00Z", program_ref=a.program_ref, before_dispatch=Guard())


def test_sync_wrapper_returning_coroutine_is_closed_and_denied():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    gateway=owner.gateway(a)
    async def not_executed():
        raise AssertionError("coroutine guard must not execute")
    gateway.before_dispatch=lambda *_: not_executed()
    response=call(gateway,"company.consult",request(b))
    assert response["error"]["code"]=="BINDING_UNAVAILABLE"
    assert owner.calls==[]


def test_guard_cannot_rewrite_the_normalized_dispatch_request():
    a,b=participant(1),participant(2)
    owner=Owner(a,b)
    gateway=owner.gateway(a)
    original_guard=gateway.before_dispatch
    def guard(name,payload):
        original_guard(name,payload)
        payload["semantic"]["to"]="peer-"+"f"*32
        payload["budget"]["max_forward_hops"]=99
    gateway.before_dispatch=guard
    response=call(gateway,"company.consult",request(b))
    assert response["ok"] is True
    sent=owner.calls[0][1]
    assert sent["semantic"]["to"]==peer(b).peer_ref
    assert sent["budget"]["max_forward_hops"]==0
