"""Real temporary Runtime/Relay composition with synthetic admitted MCP facts.

Kernel/authentication qualification is exercised in the separate authority suite;
these tests neither provision a provider nor claim native answer consumption.
"""
import asyncio
from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile

import pytest

from common.company_consultation_host_contract import encode_request
from control_plane.executive_runtime import ActiveMcpCapabilityBindingFacts, StateConflict
from control_plane.operator_harness_contract import CapabilityIdentity, ObservedCapabilityIdentity
from integrations.mastermind_company_mcp import host as module
from integrations import company_consultation_dispatch as dispatch_module
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_target_resolution import (
    WORKSPACE, CHANNEL, _event_count, _seed,
)
from tests.test_company_consultation_targeted_dispatch import _bindings, _client_and_sources


@pytest.fixture
def composed(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    client = _client_and_sources(seed, _bindings(seed))
    cap = CapabilityIdentity(
        name=module.COMPANY_MCP_CONFIG_NAME, kind="mcp_server", harness_binary_digest="a" * 64,
        tool_schema_digest=module.COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST,
        mcp_server_identity=module.COMPANY_CONSULTATION_SERVER_IDENTITY,
        mcp_server_version=module.COMPANY_CONSULTATION_SERVER_VERSION, mcp_auth_status="unsupported",
    )
    raw = asdict(cap)
    raw.pop("harness_binary_digest")
    def capability(self, attempt_id, *, connection=None):
        return ActiveMcpCapabilityBindingFacts(
            binding=self.runtime.current_harness_binding_source(attempt_id, connection=connection),
            requested_capability=cap, observed_capability=ObservedCapabilityIdentity(**raw),
            requested_profile_digest="b" * 64, observed_attestation_digest="c" * 64,
        )
    monkeypatch.setattr(module.CompanyConsultationHost, "_capability", capability)
    authorities = []
    class QualifiedTestAuthority:
        def __init__(self, *, runtime, peer, **kwargs):
            self.runtime, self.attempt_id, self.closed = runtime, peer, False
            authorities.append(self)
        def revalidate(self):
            assert not self.closed
            return capability(self, self.attempt_id)
        def close(self):
            self.closed = True
    monkeypatch.setattr(module, "CompanyCallerAuthority", QualifiedTestAuthority)
    now = lambda: "2026-09-14T00:00:00Z"
    monkeypatch.setattr(module, "utc_now_iso", now)
    monkeypatch.setattr(dispatch_module, "utc_now_iso", now)
    def build(path):
        return module.CompanyConsultationHost(
            runtime=seed.runtime, repository_root=seed.repo, worker_uid=451,
            relay_socket_path=path, workspace_id=WORKSPACE, channel_id=CHANNEL,
        )
    failures = []
    original_dispatch = module.RuntimeConsultationDispatcher.__call__
    async def traced(self, *args, **kwargs):
        try:
            return await original_dispatch(self, *args, **kwargs)
        except Exception:
            import traceback
            failures.append(traceback.format_exc())
            raise
    monkeypatch.setattr(module.RuntimeConsultationDispatcher, "__call__", traced)
    seed.failures = failures
    seed.client, seed.build_host, seed.authorities = client, build, authorities
    return seed


async def call(host, attempt, tool, args):
    return json.loads(await host.call(attempt, encode_request(tool, args)))


def test_host_peers_and_caller_have_consultation_only_binding(composed):
    host = composed.build_host(Path("/private/tmp/unused-company.sock"))
    before = _event_count(composed)
    result = asyncio.run(call(host, composed.a[1], "company.peers", {}))
    assert result["ok"], result
    assert len(result["data"]["peers"]) == 1
    assert result["data"]["peers"][0]["peer_ref"].startswith("peer-")
    facts = host._capability(composed.a[1])
    binding = module._dialogue_binding(host._caller(facts).target)
    assert binding.allowed_message_types == ()
    assert _event_count(composed) == before
    assert all(authority.closed for authority in composed.authorities)


def test_host_real_relay_question_answer_and_read_never_claim_consumption(composed):
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="c-host-", dir="/tmp") as directory:
            path = Path(directory) / "r.sock"
            service, task = await fixtures._start_relay_service(socket_path=path, client=composed.client)
            host = composed.build_host(path)
            try:
                peers = await call(host, composed.a[1], "company.peers", {})
                args = fixtures._consult_args(question="Bounded cross-session answer.",
                    evidence_refs=[], artifact_revisions=[composed.revision])
                args["to"] = peers["data"]["peers"][0]["peer_ref"]
                question = await call(host, composed.a[1], "company.consult", args)
                assert question["ok"], (question, composed.failures)
                ref = question["data"]["consultation_ref"]
                read = await call(host, composed.b[1], "company.consultation", {"consultation_ref": ref})
                assert read["ok"], read
                assert read["data"]["question"]["text"] == args["question"]
                fixtures._deliver_and_ack_wake_path(composed.runtime, ref)
                answer = await call(host, composed.b[1], "company.reply", {
                    "consultation_ref": ref, "answer": "The bounded answer.", "evidence_refs": [],
                })
                assert answer["ok"], answer
                before = _event_count(composed)
                returned = await call(host, composed.a[1], "company.consultation", {"consultation_ref": ref})
                assert returned["ok"], returned
                assert returned["data"]["answer"]["text"] == "The bounded answer."
                assert _event_count(composed) == before
                assert fixtures._consultation_event_count(composed.runtime, ref, "CONSUMED_BY_REQUESTER") == 0
                assert fixtures._consultation_event_count(composed.runtime, ref, "INTENT") == 1
                assert fixtures._consultation_event_count(composed.runtime, ref, "ANSWER_AVAILABLE") == 1
            finally:
                await fixtures._stop_relay_service(service, task)
        assert all(authority.closed for authority in composed.authorities)
    asyncio.run(scenario())


@pytest.mark.parametrize("tool,args", [
    ("company.peers", {"attempt_id": "ATT-spoof"}),
    ("company.consultation", {"consultation_ref": "invalid", "caller": "CEO"}),
])
def test_caller_identity_in_arguments_is_refused_before_authority(composed, tool, args):
    host = composed.build_host(Path("/private/tmp/unused-company.sock"))
    before = _event_count(composed)
    response = asyncio.run(call(host, composed.a[1], tool, args))
    assert response["error"]["code"] == "INVALID_REQUEST"
    assert composed.authorities == []
    assert _event_count(composed) == before


def test_foreign_relay_scope_discloses_no_peers(composed):
    host = composed.build_host(Path("/private/tmp/unused-company.sock"))
    host.channel_id = "C0BSBM78V1N"
    result = asyncio.run(call(host, composed.a[1], "company.peers", {}))
    assert result["error"]["code"] == "ACCESS_REFUSED"


def test_read_disclosure_rechecks_authority_after_dispatch(composed, monkeypatch):
    host = composed.build_host(Path("/private/tmp/unused-company.sock"))
    original = module.CompanyConsultationGateway.call
    async def changed(self, tool, args):
        result = await original(self, tool, args)
        host.channel_id = "C0BSBM78V1N"
        return result
    monkeypatch.setattr(module.CompanyConsultationGateway, "call", changed)
    result = asyncio.run(call(host, composed.a[1], "company.peers", {}))
    assert result["error"]["code"] == "ACCESS_REFUSED"
    assert result["data"] is None


@pytest.mark.parametrize("phase,expected_intents", [("INTENT", 0), ("QUESTION_WAKE", 1)])
def test_authority_loss_at_effect_edge_preserves_prior_truth(composed, monkeypatch, phase, expected_intents):
    original = module._RequestContext.guard
    def guard(self, current_phase=None):
        if current_phase == phase:
            raise StateConflict("test caller revoked")
        return original(self, current_phase)
    monkeypatch.setattr(module._RequestContext, "guard", guard)
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="c-guard-", dir="/tmp") as directory:
            path = Path(directory) / "r.sock"
            service, task = await fixtures._start_relay_service(socket_path=path, client=composed.client)
            try:
                host = composed.build_host(path)
                peers = await call(host, composed.a[1], "company.peers", {})
                args = fixtures._consult_args(question="Guard this effect.", evidence_refs=[],
                                              artifact_revisions=[composed.revision])
                args["to"] = peers["data"]["peers"][0]["peer_ref"]
                response = await call(host, composed.a[1], "company.consult", args)
                with composed.runtime.store.read() as connection:
                    count = connection.execute("SELECT count(*) FROM events WHERE aggregate_type='consultation' AND event_type='INTENT'").fetchone()[0]
                assert count == expected_intents, response
                if not expected_intents:
                    assert response["error"]["code"] == "EFFECT_UNKNOWN"
                else:
                    assert response["ok"] and response["data"]["blocker"] == "WAKE_REQUEST_UNRESOLVED"
            finally:
                await fixtures._stop_relay_service(service, task)
    asyncio.run(scenario())


@pytest.mark.parametrize("phase,expected_answers", [("ANSWER_AVAILABLE", 0), ("ANSWER_WAKE", 1), ("CONSUMED_BY_REQUESTER", 1)])
def test_answer_and_consumption_effect_fences(composed, monkeypatch, phase, expected_answers):
    from tests.test_company_consultation_targeted_dispatch import _dispatch
    from integrations.company_consultation_dispatch import ConsultationRefusal
    original = module._RequestContext.guard
    seen = []
    def guard(self, current_phase=None):
        if current_phase == phase:
            seen.append(current_phase)
            raise StateConflict("test caller revoked")
        return original(self, current_phase)
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="c-ans-", dir="/tmp") as directory:
            path = Path(directory) / "r.sock"
            service, task = await fixtures._start_relay_service(socket_path=path, client=composed.client)
            host = composed.build_host(path)
            try:
                peers = await call(host, composed.a[1], "company.peers", {})
                args = fixtures._consult_args(question="Guard the answer.", evidence_refs=[],
                                              artifact_revisions=[composed.revision])
                args["to"] = peers["data"]["peers"][0]["peer_ref"]
                question = await call(host, composed.a[1], "company.consult", args)
                assert question["ok"], (question, composed.failures)
                ref = question["data"]["consultation_ref"]
                fixtures._deliver_and_ack_wake_path(composed.runtime, ref)
                monkeypatch.setattr(module._RequestContext, "guard", guard)
                answer = await call(host, composed.b[1], "company.reply", {
                    "consultation_ref": ref, "answer": "The fenced answer.", "evidence_refs": [],
                })
                assert fixtures._consultation_event_count(composed.runtime, ref, "ANSWER_AVAILABLE") == expected_answers
                if phase == "ANSWER_AVAILABLE":
                    assert answer["error"]["code"] == "EFFECT_UNKNOWN"
                else:
                    assert answer["ok"], answer
                if phase == "CONSUMED_BY_REQUESTER":
                    dispatcher = _dispatch(composed, _bindings(composed), path)
                    def consume_guard(current_phase):
                        assert current_phase == phase
                        seen.append(current_phase)
                        raise StateConflict("requester consumption revoked")
                    dispatcher._before_effect = consume_guard
                    with pytest.raises(ConsultationRefusal):
                        await dispatcher.consume_answer(ref)
                assert fixtures._consultation_event_count(composed.runtime, ref, "CONSUMED_BY_REQUESTER") == 0
                assert seen == [phase]
            finally:
                await fixtures._stop_relay_service(service, task)
    asyncio.run(scenario())


def test_caller_rotates_during_recipient_check_before_intent(composed, monkeypatch):
    state = {"selected_guard": False, "revoked": False}
    original_guard = module._RequestContext.guard
    original_recipient = module.CompanyConsultationHost._recipient
    original_capability = module.CompanyConsultationHost._capability
    def guard(self, phase=None):
        state["selected_guard"] = self.selected is not None
        try:
            return original_guard(self, phase)
        finally:
            state["selected_guard"] = False
    def recipient(self, target):
        result = original_recipient(self, target)
        if state["selected_guard"]:
            state["revoked"] = True
        return result
    def capability(self, attempt_id, **kwargs):
        result = original_capability(self, attempt_id, **kwargs)
        if state["revoked"] and attempt_id == composed.a[1]:
            return replace(result, observed_attestation_digest="f" * 64)
        return result
    monkeypatch.setattr(module._RequestContext, "guard", guard)
    monkeypatch.setattr(module.CompanyConsultationHost, "_recipient", recipient)
    monkeypatch.setattr(module.CompanyConsultationHost, "_capability", capability)
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="c-drift-", dir="/tmp") as directory:
            path = Path(directory) / "r.sock"
            service, task = await fixtures._start_relay_service(socket_path=path, client=composed.client)
            try:
                host = composed.build_host(path)
                peers = await call(host, composed.a[1], "company.peers", {})
                args = fixtures._consult_args(question="Refuse rotation.", evidence_refs=[],
                                              artifact_revisions=[composed.revision])
                args["to"] = peers["data"]["peers"][0]["peer_ref"]
                before = _event_count(composed)
                response = await call(host, composed.a[1], "company.consult", args)
                assert state["revoked"]
                assert response["error"]["code"] == "EFFECT_UNKNOWN"
                assert _event_count(composed) == before
            finally:
                await fixtures._stop_relay_service(service, task)
    asyncio.run(scenario())
