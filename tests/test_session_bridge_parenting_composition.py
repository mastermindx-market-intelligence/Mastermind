"""Production parenting composition with real Runtime, Relay and Wake owners.

Slack/provider effects and the native reply producer are fixture boundaries.
This does not prove installed native consumption or a live parent roundtrip.
"""
import asyncio
import copy
import pytest
import os
from decimal import Decimal

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.dialogue_wake_canary_activation import (
    DialogueWakeCanaryActivationGrant, DialogueWakeCanaryProfile, SCHEMA,
)
from control_plane.executive_service import ExecutiveControlService, ExecutiveDialogueWakeBridge
from control_plane.operator_harness_contract import (
    AttentionTurnObservation, ProcessLiveness, ProviderWriterState, ReconcileObservation,
)
from control_plane.session_targets import route_obligation
from control_plane.wake_events import mint_obligation
from control_plane.wake_ledger import LedgerPhase, WakeRetryPolicy, requested_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.session_bridge.installed import PRIVATE_SCHEMA, build_runtime_session_bridge
from integrations.session_bridge.native_reply import NativeReplyWriter
from integrations.session_bridge.runtime_owner import RuntimeFabricTargetProjector, RuntimeCodexTargetProjector
from integrations.session_bridge.runtime_return import RuntimeSessionReturn
from integrations.slack_agent_dialogue.contract_v2 import (
    build_message_v2, build_parent_v2, render_message_v2, render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import DialogueEngine, DialoguePolicy, SlackMessage
from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.service import AgentDialogueService, ServiceConfig
from integrations.slack_agent_dialogue import runtime as relay_runtime
from scripts.executive_os_phase1c import _build_executive_dialogue_wake_carrier
from tests.test_executive_service import _strict_dialogue_runtime, _config, _FakeSupervisor
from tests.test_session_bridge_installed import principal_frame
from tests.test_slack_agent_dialogue_engine_v2 import ExactV2AuthorityPolicy

THREAD = "1788000000.123456"
NATIVE = "11111111-2222-4444-8888-999999999999"
BOT = "U0RELAY001"


def _material(f, message):
    observation = DialogueSourceObservation(
        "T0BRD2AQXQV", "C0BSBM78V1N", THREAD,
        message["message_key"], message["fingerprint"])
    logical = correlated_source_ref(
        attention_source_ref=attention_source_ref(
            parent_fingerprint=f.parent["fingerprint"],
            message_key=message["message_key"], target_seat="coo"),
        parent_fingerprint=f.parent["fingerprint"],
        operation_key=f.parent["operation_key"], candidate=f.candidate.to_dict())
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending", source_kind="agent_dialogue_attention",
        source_ref=logical, declared_target_seat="coo",
        job_id=f.sealed.job_id, attempt_id=f.sealed.attempt_id,
        root_job_id=f.root.job_id, source_workstream=f.source["work_ref"],
        source_created_at=message["created_at"], emitted_at="2026-09-03T01:00:02Z")
    physical = PhysicalDialogueSourceIdentity.create(
        logical_source_ref=logical, obligation_id=obligation.obligation_id,
        observation=observation, parent_fingerprint=f.parent["fingerprint"],
        operation_key=f.parent["operation_key"], target_seat="coo",
        candidate=f.candidate.to_dict())
    return obligation, physical


@pytest.mark.parametrize("source_fault", [None, "parent_during_read", "foreign_parent_attestation"])
def test_session_send_real_w3c_persists_once_and_original_parent_reads(
    tmp_path, short_socket_root, monkeypatch, source_fault,
):
    f = _strict_dialogue_runtime(tmp_path, monkeypatch, provider_session_id=NATIVE)
    # NativeReplyReader binds its default clock at import, so refresh the exact
    # fixture principal instead of changing production clock behavior.
    import time
    principal = principal_frame()
    principal["issued_at"], principal["expires_at"] = int(time.time()) - 60, int(time.time()) + 3600

    actor = {"kind": "worker_attempt", "job_id": f.sealed.job_id,
             "attempt_id": f.sealed.attempt_id, "worker_id": "worker-a"}
    applies = {"kind": "executive_attempt", **{k: actor[k] for k in ("job_id", "attempt_id", "worker_id")}}
    prior = build_message_v2({
        "schema": "mastermind.agent_dialogue.v2", "message_key": "asd-prior-result-001",
        "message_type": "PROGRESS", "work_ref": f.parent["work_ref"],
        "commission_ref": f.parent["commission_ref"], "session_ref": f.parent["session_ref"],
        "actor_ref": actor, "reply_to_message_key": None, "applies_to": applies,
        "summary": "Existing child is ready for a bounded continuation.",
        "body": {"stage": "source", "completed": "Prior work recorded.", "next": "Await continuation."},
        "evidence_refs": [], "requires_response": False, "created_at": "2026-09-03T01:00:00Z"})
    # The already-existing child has a previously persisted physical carrier.
    # No dispatch/attempt is manufactured by this prior-state fixture.
    prior_obligation, prior_physical = _material(f, prior)
    repository = WakeLedgerRepository(f.runtime)
    repository.append_record(requested_record(prior_obligation, physical_source=prior_physical),
                             obligation=prior_obligation)

    class Operator:
        calls = 0
        reconciles = 0

        def deliver_attention(self, **kwargs):
            self.calls += 1
            return AttentionTurnObservation(
                process_generation_id=f.generation.process_generation_id,
                provider_session_id=NATIVE, nudge_id=kwargs["nudge_id"],
                provider_native_turn_id="turn-parenting-one", accepted=True, delivered=False)

        def reconcile(self, generation):
            assert generation == f.generation
            self.reconciles += 1
            return ReconcileObservation(
                process_liveness=ProcessLiveness.ALIVE, observed_process=f.process,
                provider_session_reachable=True, provider_writer_state=ProviderWriterState.HELD,
                observed_provider_session_id=NATIVE)

    async def run():
        client = InMemorySlackClient(relay_bot_user_id=BOT)
        client.add_parent(SlackMessage(ts=THREAD, author_user_id=BOT, text=render_parent_v2(f.parent)))
        client.add_reply(SlackMessage(ts="1788000001.123456", author_user_id=BOT,
                                     text=render_message_v2(prior), thread_ts=THREAD))
        # Keep fixture posts later than the existing parent/predecessor.
        client.next_timestamp = Decimal("1788000010.000001")
        policy = DialoguePolicy(
            workspace_id="T0BRD2AQXQV", channel_id="C0BSBM78V1N",
            relay_bot_user_id=BOT, allowed_sol_user_ids=("U0BRETDUAS2",),
            allowed_parent_user_ids=(BOT,), poll_interval_seconds=0, method_timeout_seconds=1)
        authority = ExactV2AuthorityPolicy()
        relay_path = short_socket_root / "relay" / "parenting.sock"
        relay = AgentDialogueService(
            ServiceConfig(socket_path=relay_path, allowed_peer_uids=(os.geteuid(),)),
            DialogueEngine(policy, client, authority_policy=authority),
            engine_v2=DialogueEngineV2(policy, client, authority_policy=authority,
                                      active_waiter_registry=relay_runtime.ActiveWaiterRegistry()))
        await relay.start()
        control = None
        try:
            owner = build_runtime_session_bridge(
                f.runtime, dialogue_socket_path=relay_path, codex_owner_configured=lambda: True)
            async def call(tool, args):
                return await owner.handle_frame({
                    "schema": PRIVATE_SCHEMA, "tool": tool,
                    "principal": principal, "arguments": args})
            targets = await call("session_targets", {"kind": "codex"})
            assert targets["ok"] and len(targets["data"]) == 1, targets
            target = targets["data"][0]
            args = {"target_ref": target["target_ref"],
                    "operation_key": target["continuation_operation_key"],
                    "instruction": "Read the exact bounded finding.",
                    "stop_condition": "Return one correlated finding."}
            sent = await call("session_send", args)
            assert sent["ok"] and sent["data"]["carrier"]["reply_committed"], sent
            assert sent["data"]["attention"] == {"state": "UNAVAILABLE"}
            assert client.post_call_count == 1
            event = f.runtime.events.list_events(aggregate_type="session_bridge_continue")[0]
            request_key = event.payload["request_message_key"]
            fabric = RuntimeFabricTargetProjector(f.runtime)
            codex = RuntimeCodexTargetProjector(fabric, owner_configured=lambda: True)
            returns = RuntimeSessionReturn(f.runtime, fabric=fabric, codex=codex, socket_path=relay_path)
            context = returns.resolve(native_session_id=NATIVE, operation_key=args["operation_key"],
                                      in_reply_to=request_key).context
            view = await relay.engine_v2.read_thread(thread_ts=THREAD, context=context)
            continuation = next(x.message for x in view.messages if x.message["message_key"] == request_key)
            if source_fault:
                from integrations.session_bridge.schemas import BridgeError
                original_call = returns.service_call
                parent_reads = 0
                async def changing_carrier(path, frame):
                    nonlocal parent_reads
                    response = await original_call(path, frame)
                    if frame["operation"] == "read_bound_parent":
                        parent_reads += 1
                        if source_fault == "foreign_parent_attestation":
                            response["result"]["attestation"] = "foreign"
                        elif parent_reads == 2:
                            changed = copy.deepcopy(response["result"]["parent"])
                            changed.pop("fingerprint")
                            changed["created_at"] = "2026-09-03T00:59:00Z"
                            response["result"]["parent"] = build_parent_v2(changed)
                    return response
                returns.service_call = changing_carrier
                with pytest.raises(BridgeError, match="canonical continuation"):
                    await returns.read_continuation_source(read_ref=event.payload["read_ref"])
                assert client.post_call_count == 1
                return
            source = await returns.read_continuation_source(read_ref=event.payload["read_ref"])
            assert source["parent"] == f.parent
            assert source["message"] == continuation
            assert source["event"] == event.to_dict()
            assert client.post_call_count == 1  # the read introduced no send
            obligation, physical = _material(f, continuation)
            route = route_obligation(obligation, f.registry, binding=f.binding)
            grant = DialogueWakeCanaryActivationGrant(
                schema=SCHEMA, installed_release_sha="a" * 40,
                operation_key=f.parent["operation_key"], source_root_job_id=f.root.job_id,
                source_job_id=f.sealed.job_id, source_attempt_id=f.sealed.attempt_id,
                source_worker_id="worker-a", source_semantic_digest=f.candidate.evidence_digest,
                obligation_id=obligation.obligation_id, target_seat="coo",
                target_session_alias=f.target.session_alias, target_attempt_id=f.sealed.attempt_id,
                binding_id=f.binding.binding_id, binding_generation=f.binding.binding_generation,
                process_generation_id=f.generation.process_generation_id, policy_digest=route.policy_digest,
                valid_from_epoch_seconds=1700000000, expires_at_epoch_seconds=1700000600)
            operator = Operator()
            bridge = ExecutiveDialogueWakeBridge(
                target_provider=None, retry_policy=WakeRetryPolicy(1, 1, 60, 1, False, True),
                operator_adapter=operator, carrier_factory=_build_executive_dialogue_wake_carrier,
                canary_profile=DialogueWakeCanaryProfile(grant),
                canary_now_epoch_seconds=lambda: 1700000100, installed_release_sha="a" * 40)
            observation_path = short_socket_root / "observation" / "parenting.sock"
            monkeypatch.setattr("control_plane.executive_service._peer_uid", lambda _: 457)
            control = ExecutiveControlService(
                _config(tmp_path / "service", socket_root=short_socket_root / "operator",
                        runtime_root=f.runtime.store.root),
                runtime_factory=lambda _: f.runtime, supervisor_factory=lambda r: _FakeSupervisor(r),
                dialogue_observation_socket_path=observation_path,
                dialogue_observation_peer_uid=457,
                dialogue_observation_group_gid=os.getegid(), dialogue_wake_handler=bridge)
            await control.start()
            monkeypatch.setattr(relay_runtime, "EXECUTIVE_OBSERVATION_SOCKET_PATH", observation_path)
            def observer():
                return relay_runtime.build_turn_runtime(
                    relay, registry=f.registry,
                    observation_client=ExecutiveDialogueObservationClient(
                        observation_path, timeout_seconds=2),
                    emitted_at=lambda: "2026-09-03T01:00:02Z")
            turn = observer()
            first = await turn.reconcile_once()
            assert [(r.outcome.value, r.reason) for r in first] == [
                ("WAKE_SUBMITTED", "DIALOGUE_TURN_PENDING")]
            assert operator.calls == 1
            assert codex.resolve(target["target_ref"]).reply_binding().reply_to_message_key == request_key
            def attempts():
                return [x for x in repository.list_records(obligation.obligation_id)
                        if x.record.phase is LedgerPhase.DELIVERY_ATTEMPT]
            assert len(attempts()) == 1
            original_attempt = attempts()[0].record
            phases = [x.record.phase for x in repository.list_records(obligation.obligation_id)]
            assert LedgerPhase.ACCEPTED in phases and LedgerPhase.DELIVERED not in phases
            # Restart loses only the observer's in-memory submitted set.
            # Persisted uncertainty must reconcile the original attempt.
            second = await observer().reconcile_once()
            assert [(r.outcome.value, r.reason) for r in second] == [
                ("EFFECT_UNKNOWN_HOLD", "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD")]
            assert operator.calls == 1
            assert operator.reconciles >= 1
            assert [x.record for x in attempts()] == [original_attempt]
            replay = await call("session_send", args)
            assert replay["ok"] and replay["data"]["carrier"]["action"] == "DUPLICATE", replay
            assert replay["data"]["read_ref"] == sent["data"]["read_ref"]
            assert client.post_call_count == 1 and operator.calls == 1
            pending = await call("session_reply_read", {"read_ref": sent["data"]["read_ref"]})
            assert pending["ok"] is False, pending

            # Explicit fixture producer: installed production still lacks this
            # exact native consumption-to-reply binding; do not claim live proof.
            reply = await NativeReplyWriter(returns, native_session_id=NATIVE, socket_path=relay_path)({
                "operation_key": args["operation_key"], "in_reply_to": request_key,
                "text": "The exact bounded finding is confirmed.", "next_step": "Continue the parent task."})
            assert reply["parent_consumed"] is False
            result = await call("session_reply_read", {"read_ref": sent["data"]["read_ref"]})
            assert result["ok"], result
            assert result["data"]["in_reply_to"] == request_key
            assert result["data"]["text"] == "The exact bounded finding is confirmed."
            assert operator.calls == 1 and len(attempts()) == 1
        finally:
            if control is not None:
                await control.close()
            await relay.close()
    asyncio.run(run())
