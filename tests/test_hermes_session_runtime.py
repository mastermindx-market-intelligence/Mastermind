"""Real Runtime/installed-owner proofs with a bounded fake native transport.

No enrolled credential, provider inference, service activation or product proof.
"""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.native_continuation import _PREFIX, _request_key, hermes_family, HERMES_KINDS
from control_plane.remote_worker_broker_client import RemoteWorkerBrokerClient
from control_plane.remote_worker_transport import TransportError, TransportEffect
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import AppPolicies, READ_SCOPE, SUBMIT_SCOPE
from integrations.session_bridge.hermes_native import HermesNativeSession, NATIVE_SCHEMA
from integrations.session_bridge.runtime_owner import (
    RuntimeFabricTargetProjector, RuntimeCodexTargetProjector,
)
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.session_bridge.schemas import BridgeError
from tests.test_executive_fabric_composition import root_stats
from tests.test_hermes_secretary_composition import document, dual_document, source_for
from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA, load_resource_policy


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(params=HERMES_KINDS)
def native(tmp_path, root_stats, monkeypatch, request):
    kind = request.param
    family = hermes_family(kind)
    runtime = Runtime.at(tmp_path / "runtime")
    job = runtime.jobs.create_job(
        "Native Secretary", command_id="test:secretary-root",
        provenance={"workstream": "WS:SECRETARY"})
    data = document(tmp_path) if kind == "hermes_secretary" else dual_document(tmp_path)
    data[kind + "_conversation"]["root_job_id"] = job.job_id
    data[kind + "_conversation"]["work_ref"] = "WS:SECRETARY"
    source = source_for(tmp_path, data)
    selected = (source.hermes_secretary_selection() if kind == "hermes_secretary"
                else source.hermes_meta_selection())
    target = {key: getattr(selected, key) for key in ("profile_id", "session_id", "principal_id")}
    target.update(instance_id="native-instance", authority_epoch=3, revision=0, execution_generation=0)
    state = SimpleNamespace(
        read_allowed=True, submit_allowed=True, calls=[], writes=0,
        before_submit=None, after_submit=None, before_observe=None, after_read=None,
        lose_submit=False, read_unavailable=False, target=target)
    now = int(time.time())
    issuer = "https://auth.example.test/"
    verified = VerifiedPrincipal(
        policy_id="test-submit", issuer=issuer,
        issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),
        resource="https://exec.example.test/mcp",
        subject_digest="1" * 64, client_ref="2" * 64,
        scopes=tuple(sorted((READ_SCOPE, SUBMIT_SCOPE))), issued_at=now-10,
        expires_at=now+3600, jti_digest=None)
    shared = dict(
        resource=verified.resource,
        resource_metadata_url=verified.resource+"/.well-known/oauth-protected-resource",
        issuer=issuer, authorization_servers=[issuer], jwks_uri=issuer+".well-known/jwks.json",
        allowed_subject_digests=[verified.subject_digest])
    def policy(policy_id, scopes):
        return load_resource_policy({
            "schema": AUTH_POLICY_SCHEMA, "policy_id": policy_id, **shared,
            "required_scopes": sorted(scopes), "allowed_algorithms": ["RS256"],
            "clock_skew_seconds": 30, "max_token_lifetime_seconds": 900,
            "jwks_cache_ttl_seconds": 300, "unknown_kid_refresh_cooldown_seconds": 30,
            "fetch_failure_backoff_seconds": 5})
    policies = AppPolicies(
        read=policy("test-read", [READ_SCOPE]),
        submit=policy("test-submit", [READ_SCOPE, SUBMIT_SCOPE]))

    def require_read():
        if not state.read_allowed:
            raise BridgeError("ingress_unavailable", "ingress changed")

    def require_submit():
        require_read()
        if not state.submit_allowed:
            raise BridgeError("authority_refused", "fresh submission is unavailable")

    def admission(status):
        return dict(
            admission_id="actual-admission",
            ref={"profile_id": selected.profile_id, "session_id": selected.session_id},
            sequence=1, status=status, outcome="completed" if status == "terminal" else None,
            authority_epoch=3, execution_generation=1 if status == "terminal" else None)

    class Client:
        async def request_conversation(self, request, *, before_write=None):
            operation = request["operation"]
            state.calls.append(operation)
            if operation == "observe":
                if state.before_observe is not None:
                    await state.before_observe()
                return dict(schema=family.native_schema, status="TARGET", target=copy.deepcopy(state.target))
            if operation == "read_original":
                assert before_write is None
                if state.read_unavailable:
                    raise TransportError("unavailable", TransportEffect.NO_EFFECT)
                if not state.writes:
                    return dict(schema=family.native_schema, status="NOT_SUBMITTED")
                if state.after_read is not None:
                    state.after_read()
                return dict(schema=family.native_schema, status="OBSERVED", admission=admission("terminal"),
                            answer="Actual original answer: 日本語 ✓", successful=True)
            assert operation == "submit" and callable(before_write)
            if state.before_submit is not None:
                state.before_submit()
            assert before_write(operation, copy.deepcopy(request)) is None
            # Independent connection observes COMMIT before simulated bytes.
            assert request["submission_id"].startswith(family.submission_prefix)
            key = request["submission_id"].removeprefix(family.submission_prefix)
            commit = runtime.events.get_event_by_command_id("session-bridge-continue-commit:"+key)
            assert commit is not None and commit.event_type == "SESSION_BRIDGE_CONTINUE_COMMIT_STARTED"
            state.writes += 1
            if state.after_submit is not None:
                state.after_submit()
            if state.lose_submit:
                raise TransportError("lost_response", TransportEffect.EFFECT_UNKNOWN)
            return dict(schema=family.native_schema, status="ADMITTED", admission=admission("queued"))

    suffix = "secretary" if kind == "hermes_secretary" else "meta"
    setattr(Client, "request_" + suffix, Client.request_conversation)
    monkeypatch.setattr(RemoteWorkerBrokerClient, "for_" + suffix + "_conversation",
                        lambda *a, **k: Client())
    hermes = HermesNativeSession(source, read_guard=require_read, submit_guard=require_submit)
    fabric = RuntimeFabricTargetProjector(runtime)
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: False)
    owner = RuntimeSessionReturn(
        runtime, fabric=fabric, codex=codex, socket_path=Path("/private/tmp/hermes-test.sock"),
        authorized_policies=policies, hermes=hermes)
    return SimpleNamespace(runtime=runtime, job=job, source=source, state=state, kind=kind, family=family,
                           hermes=hermes, owner=owner, policies=policies, verified=verified,
                           principal=principal_projection(verified))


async def arguments(s):
    target, = await s.owner.hermes_targets(s.principal, kind=s.kind)
    s.state.calls.clear()
    return dict(target_ref=target["target_ref"],
                operation_key=target["continuation_operation_key"],
                instruction="Read the bounded original task.", stop_condition="Return one finding.")


def original_events(s, args):
    key = _request_key(args["operation_key"])
    return s.runtime.store.bounded_aggregate_events("session_bridge_continue", key)


@pytest.mark.anyio
async def test_fresh_submit_commits_runtime_before_native_bytes_without_worker_identity(native):
    s = native
    args = await arguments(s)
    result = await s.owner.send_hermes(s.principal, args)
    assert result["native_status"] == "ADMITTED" and result["commit_started"] is True
    assert result["answer"] is None and result["parent_consumed"] is False
    assert s.state.calls == ["observe", "submit"] and s.state.writes == 1
    events = original_events(s, args)
    assert [e.sequence for e in events] == [1, 2]
    assert all(e.job_id == s.job.job_id and e.attempt_id is None and e.worker_id is None for e in events)


@pytest.mark.anyio
async def test_duplicate_send_recovers_original_despite_native_revision_and_fresh_gate_change(native):
    s = native
    args = await arguments(s)
    await s.owner.send_hermes(s.principal, args)
    before = [e.to_dict() for e in original_events(s, args)]
    s.state.submit_allowed = False
    s.state.target["revision"] = 99
    s.runtime.jobs.pause_workstream_admission("WS:SECRETARY", command_id="test:pause", actor="test")
    s.state.calls.clear()
    result = await s.owner.send_hermes(s.principal, args)
    assert result["answer"] == "Actual original answer: 日本語 ✓"
    assert s.state.calls == ["read_original"] and s.state.writes == 1
    assert before == [e.to_dict() for e in original_events(s, args)]


@pytest.mark.anyio
async def test_lost_response_reconciles_original_once_and_never_resubmits(native):
    s = native
    args = await arguments(s)
    s.state.lose_submit = True
    result = await s.owner.send_hermes(s.principal, args)
    assert result["native_status"] == "OBSERVED"
    assert s.state.calls == ["observe", "submit", "read_original"]
    assert s.state.writes == 1


@pytest.mark.anyio
async def test_lost_response_and_unavailable_read_retain_only_actual_journal_evidence(native):
    s = native
    args = await arguments(s)
    s.state.lose_submit = s.state.read_unavailable = True
    result = await s.owner.send_hermes(s.principal, args)
    assert result["commit_started"] is True and result["native_status"] is None
    assert result["answer"] is result["admission"] is None and s.state.writes == 1


@pytest.mark.anyio
async def test_concurrent_new_sends_share_one_original_and_one_native_write(native):
    s = native
    args = await arguments(s)
    s.state.before_observe = lambda: asyncio.sleep(0)
    first, second = await asyncio.gather(
        s.owner.send_hermes(s.principal, args), s.owner.send_hermes(s.principal, args))
    assert first["read_ref"] == second["read_ref"]
    assert s.state.writes == 1 and len(original_events(s, args)) == 2


@pytest.mark.anyio
async def test_request_only_recovery_never_calls_native_and_keeps_frozen_input(native):
    s = native
    args = await arguments(s)
    s.state.before_submit = lambda: setattr(s.state, "submit_allowed", False)
    with pytest.raises(BridgeError):
        await s.owner.send_hermes(s.principal, args)
    assert len(original_events(s, args)) == 1 and s.state.writes == 0
    s.state.calls.clear()
    ref = s.owner.resolve_operation_read_ref(principal=s.principal, operation_key=args["operation_key"])
    result = await s.owner.read_hermes(s.principal, ref)
    assert result["commit_started"] is False and result["native_status"] is None
    assert s.state.calls == []
    s.state.before_submit = None
    s.state.submit_allowed = True
    resumed = await s.owner.send_hermes(s.principal, args)
    assert resumed["native_status"] == "ADMITTED" and s.state.calls == ["submit"]


@pytest.mark.anyio
async def test_workstream_pause_between_requested_and_commit_prevents_native_write(native):
    s = native
    args = await arguments(s)
    s.state.before_submit = lambda: s.runtime.jobs.pause_workstream_admission(
        "WS:SECRETARY", command_id="test:pause-before-commit", actor="test")
    with pytest.raises(BridgeError):
        await s.owner.send_hermes(s.principal, args)
    assert s.state.writes == 0 and len(original_events(s, args)) == 1


@pytest.mark.anyio
async def test_foreign_original_and_changed_input_do_not_observe_or_submit(native):
    s = native
    args = await arguments(s)
    await s.owner.send_hermes(s.principal, args)
    s.state.calls.clear()
    with pytest.raises(BridgeError):
        await s.owner.send_hermes(s.principal, {**args, "instruction": "Changed"})
    foreign = dataclasses.replace(s.principal, subject_digest="f"*64)
    with pytest.raises(BridgeError):
        await s.owner.read_hermes(foreign, "session-reply-"+_request_key(args["operation_key"]))
    assert s.state.calls == [] and s.state.writes == 1


@pytest.mark.anyio
async def test_route_drift_retains_journal_but_ingress_revocation_withholds_it(native):
    s = native
    args = await arguments(s)
    result = await s.owner.send_hermes(s.principal, args)
    s.source.path.write_bytes(s.source.path.read_bytes()+b" ")
    s.state.calls.clear()
    recovered = await s.owner.read_hermes(s.principal, result["read_ref"])
    assert recovered["commit_started"] is True and recovered["native_status"] is None
    assert s.state.calls == []
    s.state.read_allowed = False
    with pytest.raises(BridgeError):
        await s.owner.read_hermes(s.principal, result["read_ref"])


@pytest.mark.anyio
async def test_trusted_read_policy_recovers_original_without_fresh_submit(native):
    s = native
    args = await arguments(s)
    result = await s.owner.send_hermes(s.principal, args)
    reader = principal_projection(dataclasses.replace(
        s.verified, policy_id="test-read", scopes=(READ_SCOPE,)))
    s.state.submit_allowed = False
    s.state.calls.clear()
    ref = s.owner.resolve_operation_read_ref(principal=reader, operation_key=args["operation_key"])
    assert ref == result["read_ref"]
    recovered = await s.owner.read_hermes(reader, ref)
    assert recovered["answer"] and s.state.calls == ["read_original"]
    page = s.owner.session_reply_references(principal=reader, work_ref="WS:SECRETARY",
                                            root_job_id=s.job.job_id)
    assert page["references"][0]["target_ref"] == args["target_ref"]


@pytest.mark.anyio
async def test_installed_bridge_and_public_reader_use_original_native_contract(native):
    from integrations.session_bridge.installed import (
        build_runtime_session_bridge, InstalledSessionBridgeClient,
    )
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse, TRANSPORT_SENT_OK
    from integrations.session_bridge.return_tools import NativeReplyReadTool
    s = native
    provider = build_runtime_session_bridge(
        s.runtime, dialogue_socket_path=Path("/private/tmp/unused-dialogue.sock"),
        authorized_policies=s.policies, hermes_session=s.hermes)
    class Ingress:
        async def send_frame(self, socket_path, frame):
            return CeoIngressResponse(transport=TRANSPORT_SENT_OK, ok=True,
                                     result=await provider.handle_frame(frame))
    client = InstalledSessionBridgeClient("/private/tmp/hermes-ingress.sock", client=Ingress())
    target, = await client.targets(s.verified, s.kind)
    args = dict(target_ref=target["target_ref"], operation_key=target["continuation_operation_key"],
                instruction="Read the original task.", stop_condition="One answer.")
    sent = await client.send(s.verified, args)
    assert sent["schema"] == s.family.result_schema
    s.state.calls.clear()
    result = await NativeReplyReadTool(client).handle(
        s.verified, "session_reply_read", {"operation_key": args["operation_key"]})
    assert result["ok"] is True and result["data"]["answer"]
    assert result["data"]["request_ref"] == _PREFIX+_request_key(args["operation_key"])
    assert s.state.calls == ["read_original"]


@pytest.mark.anyio
async def test_raced_commit_wins_before_changed_native_target_and_fresh_gate(native):
    s = native
    args = await arguments(s)
    s.state.before_observe = lambda: asyncio.sleep(0)
    def rotate():
        s.state.target["revision"] = 99
        s.state.submit_allowed = False
    s.state.after_submit = rotate
    results = await asyncio.gather(
        s.owner.send_hermes(s.principal, args), s.owner.send_hermes(s.principal, args))
    assert s.state.writes == 1 and all(r["commit_started"] for r in results)
    assert any(r["native_status"] == "OBSERVED" for r in results)


@pytest.mark.anyio
async def test_ingress_revocation_during_original_read_withholds_native_answer(native):
    s = native
    args = await arguments(s)
    result = await s.owner.send_hermes(s.principal, args)
    s.state.after_read = lambda: setattr(s.state, "read_allowed", False)
    with pytest.raises(BridgeError):
        await s.owner.read_hermes(s.principal, result["read_ref"])
