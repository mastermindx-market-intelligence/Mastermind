"""Real immutable Runtime request events; fake carrier is not a native live proof."""
import asyncio
import copy
import dataclasses
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_runtime import Runtime
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.session_bridge import runtime_return as module
from integrations.session_bridge.dialogue_reply import AgentDialogueContinueWriter
from integrations.session_bridge.native_read import NativeReplyReader
from integrations.session_bridge.native_reply import NativeReplyWriter
from integrations.session_bridge.runtime_owner import (
    RuntimeFabricTarget, RuntimeFabricTargetProjector, RuntimeCodexTargetProjector,
)
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2
from tests.test_workspace_agent_runtime_binding import target, source, physical

NATIVE = "11111111-2222-4444-8888-999999999999"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker("worker-01", provider="codex", account_label="test",
                                    worker_type="codex", quota_classes=["default"])
    job = runtime.jobs.create_job("Original bounded continuation")
    lease = runtime.attempts.claim_job(job.job_id, worker_id="worker-01", quota_class="default")
    assert lease is not None
    epoch = target(root_job_id=job.job_id, job_id=job.job_id, attempt_id=lease.attempt.attempt_id,
                   harness_provider_session_id=NATIVE)
    original = RuntimeFabricTarget(
        target_ref="fabric_attempt:" + "1" * 64, operation_key="exec-job-001", epoch=epoch,
        source=source(), physical=physical(root_job_id=job.job_id, job_id=job.job_id,
            attempt_id=lease.attempt.attempt_id, operation_key="exec-job-001"), generation="g1")
    fabric = RuntimeFabricTargetProjector(runtime)
    monkeypatch.setattr(fabric, "resolve", lambda ref: original if ref == original.target_ref else None)
    enabled = [True]
    codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: enabled[0])
    facts = SimpleNamespace(job_id=job.job_id, worker_id=epoch.worker_id,
        attempt_id=lease.attempt.attempt_id, session_epoch_id=epoch.harness_session_epoch_id,
        generation_number=epoch.harness_generation_number, provider_session_id=NATIVE,
        process_generation_id="process-01")
    monkeypatch.setattr(Runtime, "current_harness_binding_source", lambda *a, **k: facts)
    monkeypatch.setattr(module, "_read_current_target", lambda *a: epoch)
    monkeypatch.setattr(module, "_read_dialogue_source", lambda *a: source())
    service = Service()
    owner = module.RuntimeSessionReturn(runtime, fabric=fabric, codex=codex,
        socket_path=Path("/private/tmp/runtime-return.sock"), service_call=service)
    binding = codex.resolve("codex:" + "1" * 64).reply_binding()
    now = int(time.time())
    principal = VerifiedPrincipal(policy_id="test", issuer="https://auth.test/",
        issuer_digest=hashlib.sha256(b"https://auth.test/").hexdigest(),
        resource="https://executive.test/mcp", subject_digest="2" * 64,
        client_ref="3" * 64, scopes=("mastermind.executive.read", "mastermind.executive.intent.submit"),
        issued_at=now-10, expires_at=now+3600, jti_digest=None)
    args = dict(target_ref=binding.target_ref, operation_key=binding.continuation_operation_key,
                instruction="Read and return the bounded finding.", stop_condition="Return one finding.")
    state = SimpleNamespace(runtime=runtime, owner=owner, binding=binding, principal=principal,
                            projection=principal_projection(principal), args=args, facts=facts,
                            service=service, enabled=enabled, epoch=epoch, target=original)
    seed_wake(state)
    return state


class Service:
    def __init__(self):
        self.items, self.calls = [], []
        self.on_read = None
    async def __call__(self, path, payload):
        self.calls.append(copy.deepcopy(payload))
        if payload["operation"] == "read_thread":
            if self.on_read:
                self.on_read()
            return {"ok":True,"result":{"thread_ts":payload["args"]["thread_ts"],
                "messages":copy.deepcopy(self.items),"historical_messages":[],"mutated_count":0}}
        message = payload["args"]["message"]
        self.items.append({"message":message,"primary_ts":"1788000002.123456"})
        return {"ok":True,"result":{"action":"POSTED","message_key":message["message_key"],
                                    "fingerprint":message["fingerprint"]}}


def bind(s, principal=None, args=None):
    return s.owner.bind_request(s.projection if principal is None else principal,
                                s.args if args is None else args)


def populate(s):
    ref = bind(s)
    context = AgentDialogueContinueWriter._context(s.binding)
    request = AgentDialogueContinueWriter._message(
        request_message={"message_key":s.binding.reply_to_message_key,
                         "created_at":"2026-10-01T20:00:00Z"},
        context=context, instruction=s.args["instruction"], stop_condition=s.args["stop_condition"],
        operation_key=s.args["operation_key"])
    s.service.items = [{"message":request,"primary_ts":"1788000001.123456"}]
    receipt = asyncio.run(NativeReplyWriter(s.owner, native_session_id=NATIVE,
        socket_path=Path("/private/tmp/runtime-return.sock"), service_call=s.service)({
            "operation_key":s.args["operation_key"], "in_reply_to":request["message_key"],
            "text":"The bounded finding is confirmed.", "next_step":"Continue the parent task."}))
    assert receipt["parent_consumed"] is False
    return ref


def read(s, ref, principal=None):
    return asyncio.run(NativeReplyReader(s.owner, socket_path=Path("/private/tmp/runtime-return.sock"),
        service_call=s.service)(s.principal if principal is None else principal, {"read_ref":ref}))


def test_request_event_is_provenance_only_and_replays_exactly(setup):
    s = setup
    ref = bind(s)
    assert bind(s) == ref
    events = s.runtime.events.list_events(aggregate_type="session_bridge_continue")
    assert len(events) == 1 and events[0].event_type.endswith("_REQUESTED")
    assert s.args["instruction"] not in repr(events[0].payload)
    assert NATIVE not in repr(events[0].payload)
    assert "reply_committed" not in events[0].payload and not s.service.calls
    with pytest.raises(BridgeError):
        read(s, ref)
    assert all(c["operation"] == "read_thread" for c in s.service.calls)


def test_concurrent_same_operation_has_one_provenance_event(setup):
    s = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        refs = list(pool.map(lambda _: bind(s), range(2)))
    assert refs[0] == refs[1]
    assert len(s.runtime.events.list_events(aggregate_type="session_bridge_continue")) == 1


@pytest.mark.parametrize("field,value", [
    ("subject_digest","4"*64), ("client_ref","5"*64), ("policy_id","foreign"),
    ("resource","https://foreign.test/mcp"), ("issuer_digest","6"*64)])
def test_foreign_principal_cannot_claim_or_read_same_operation(setup, field, value):
    s = setup
    ref = populate(s)
    foreign = dataclasses.replace(s.projection, **{field:value})
    with pytest.raises(BridgeError):
        bind(s, principal=foreign)
    before = len(s.service.calls)
    with pytest.raises(BridgeError):
        asyncio.run(s.owner.resolve_read(principal=foreign, read_ref=ref))
    assert len(s.service.calls) == before


def test_changed_input_conflicts_and_never_calls_carrier(setup):
    s = setup
    bind(s)
    with pytest.raises(BridgeError):
        bind(s, args={**s.args,"instruction":"Different instruction."})
    assert not s.service.calls


def test_native_reply_and_authenticated_parent_read_share_original_request(setup):
    s = setup
    ref = populate(s)
    before = s.runtime.events.list_events()
    result = read(s, ref)
    assert result["text"] == "The bounded finding is confirmed."
    assert result["request_ref"].startswith("session-bridge-continue:")
    assert result["parent_consumed"] is False
    assert s.service.items[0]["message"]["actor_ref"]["kind"] == "executive_surface"
    assert s.service.items[1]["message"]["actor_ref"]["kind"] == "worker_attempt"
    assert s.runtime.events.list_events() == before


def test_token_rotation_keeps_same_parent_identity(setup):
    s = setup
    ref = populate(s)
    assert read(s, ref, dataclasses.replace(s.principal, jti_digest="7"*64))["reply_committed"]


def test_epoch_rotation_refuses_original_read(setup):
    s = setup
    ref = populate(s)
    s.facts.generation_number += 1
    with pytest.raises(BridgeError):
        read(s, ref)


def test_native_write_requires_codex_owner_but_committed_read_survives_disarm(setup):
    s = setup
    ref = populate(s)
    s.enabled[0] = False
    with pytest.raises(BridgeError):
        s.owner.resolve(native_session_id=NATIVE, operation_key=s.args["operation_key"],
                        in_reply_to=s.service.items[0]["message"]["message_key"])
    assert read(s, ref)["reply_committed"]


@pytest.mark.parametrize("change", ["extra","missing","digest","generation","context"])
def test_closed_event_payload_rejects_drift(setup, change):
    s = setup
    bind(s)
    value = copy.deepcopy(s.runtime.events.list_events(aggregate_type="session_bridge_continue")[0].payload)
    if change == "extra": value["claim"] = "consumed"
    elif change == "missing": value.pop("principal")
    elif change == "digest": value["input_sha256"] = "bad"
    elif change == "generation": value["generation"]["binding_generation"] = True
    else: value["context"]["extra"] = "unexpected"
    with pytest.raises((ValueError,TypeError)):
        module._validate_payload(value)


def test_duplicate_reply_candidates_refuse(setup):
    s = setup
    ref = populate(s)
    s.service.items.append(copy.deepcopy(s.service.items[-1]))
    with pytest.raises(BridgeError):
        read(s, ref)


def test_tampered_reply_fingerprint_refuses(setup):
    s = setup
    ref = populate(s)
    s.service.items[-1]["message"]["fingerprint"] = "0"*64
    with pytest.raises(BridgeError):
        read(s, ref)


def test_same_context_reply_with_different_native_key_refuses(setup):
    s = setup
    ref = populate(s)
    message = copy.deepcopy(s.service.items[-1]["message"])
    message.pop("fingerprint")
    message["message_key"] = "asd-native-reply-" + "9" * 40
    s.service.items[-1]["message"] = build_message_v2(message)
    with pytest.raises(BridgeError):
        read(s, ref)


def test_original_continue_cannot_expand_scope(setup):
    s = setup
    ref = populate(s)
    message = copy.deepcopy(s.service.items[0]["message"])
    from common.agent_dialogue_contract import semantic_fingerprint
    message["body"]["scope_change"] = True
    message["fingerprint"] = semantic_fingerprint(message)
    s.service.items[0]["message"] = message
    with pytest.raises(BridgeError):
        read(s, ref)


def seed_wake(s, identity=None):
    from control_plane.wake_events import mint_obligation
    from control_plane.wake_ledger import requested_record
    from control_plane.wake_persist import WakeLedgerRepository
    physical = s.target.physical
    identity = physical.identity if identity is None else identity
    candidate = identity.candidate
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending", source_kind="agent_dialogue_attention",
        source_ref=identity.logical_source_ref, declared_target_seat=identity.target_seat,
        job_id=candidate.job_id, attempt_id=candidate.attempt_id,
        root_job_id=candidate.root_job_id, source_workstream=physical.source_workstream,
        emitted_at="2026-10-03T00:00:00Z")
    assert obligation.obligation_id == identity.obligation_id
    return WakeLedgerRepository(s.runtime).append_record(
        requested_record(obligation, physical_source=identity), obligation=obligation)


def advanced_identity(s, **changes):
    from control_plane.dialogue_source_resolution import (
        DialogueSourceObservation, PhysicalDialogueSourceIdentity,
        attention_source_ref, correlated_source_ref)
    from control_plane.wake_events import mint_obligation_id
    old = s.target.physical.identity
    candidate = old.candidate.to_dict()
    parent = "d" * 64
    observation = DialogueSourceObservation(
        workspace_id=changes.get("workspace_id", old.workspace_id),
        channel_id=changes.get("channel_id", old.channel_id),
        thread_ts=changes.get("thread_ts", old.thread_ts),
        predecessor_message_key="asd-progress-002",
        predecessor_message_fingerprint="e" * 64)
    attention = attention_source_ref(parent_fingerprint=parent,
        message_key=observation.predecessor_message_key, target_seat=old.target_seat)
    logical = correlated_source_ref(attention_source_ref=attention,
        parent_fingerprint=parent, operation_key=old.operation_key, candidate=candidate)
    return PhysicalDialogueSourceIdentity.create(logical_source_ref=logical,
        obligation_id=mint_obligation_id(source_kind="agent_dialogue_attention",
            source_ref=logical, wake_kind="dialogue_turn_pending"),
        observation=observation, parent_fingerprint=parent, operation_key=old.operation_key,
        target_seat=old.target_seat, candidate=candidate)


def test_real_wake_parent_can_advance_on_same_physical_thread(setup):
    s = setup
    ref = populate(s)
    seed_wake(s, advanced_identity(s))
    assert read(s, ref)["reply_committed"]


@pytest.mark.parametrize("changes", [
    {"workspace_id": "T1234567890"}, {"channel_id": "C1234567890"},
    {"thread_ts": "1788000009.123456"}])
def test_real_wake_cannot_move_return_to_another_physical_thread(setup, changes):
    s = setup
    ref = populate(s)
    seed_wake(s, advanced_identity(s, **changes))
    with pytest.raises(BridgeError):
        read(s, ref)


@pytest.mark.parametrize("fault", ["absent", "malformed"])
def test_missing_or_malformed_matching_wake_refuses(setup, monkeypatch, fault):
    s = setup
    ref = populate(s)
    original = s.runtime.events.list_events
    def events(**kwargs):
        rows = original(**kwargs)
        if kwargs.get("attempt_id") != s.epoch.attempt_id:
            return rows
        altered = []
        for event in rows:
            if event.event_type != "WAKE_REQUESTED":
                altered.append(event)
            elif fault == "malformed":
                payload = copy.deepcopy(event.payload)
                payload["physical_source"]["candidate"] = {}
                altered.append(dataclasses.replace(event, payload=payload))
        return altered
    monkeypatch.setattr(s.runtime.events, "list_events", events)
    with pytest.raises(BridgeError):
        read(s, ref)
