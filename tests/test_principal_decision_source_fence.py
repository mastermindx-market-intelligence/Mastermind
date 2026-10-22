"""Actual Runtime, Relay wire and host gateway meet at the fresh source fence.

Principals, provider identity and physical Slack storage are explicit fixtures.
This proves the local effect composition, not enrolled-account authentication.
Receiving authority revocation uses an explicit guard fixture; its real owner
is separately tested by test_principal_dialogue_authority_commit.py.
"""
import asyncio
import dataclasses
from decimal import Decimal
import pytest

from integrations.mastermind_company_principal_host import build_principal_company_dialogue_host
from integrations.mastermind_company_principal_runtime_fence import PRINCIPAL_RUNTIME_AGGREGATE_TYPE, PrincipalCommitObservationState
from integrations.slack_agent_dialogue.principal_decision_source_fence import PrincipalDecisionSource
from integrations.slack_agent_dialogue.service import call_service
from tests.test_company_dialogue_principal_runtime_fence import Resolver
from tests.test_slack_agent_dialogue_turn_watcher import _body

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation, PhysicalDialogueSourceIdentity,
    attention_source_ref, correlated_source_ref,
)
from control_plane.executive_dialogue_observation import (
    parse_observation_request, reduce_dialogue_observation, response_bytes,
)
from control_plane.wake_events import mint_obligation_id
from integrations.slack_agent_dialogue.contract_v2 import (
    build_message_v2, render_message_v2, render_parent_v2,
)
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.executive_observation_client import ExecutiveDialogueObservationClient
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.principal_current_reader import read_current_principal_source
from tests.test_executive_service import _strict_dialogue_runtime
from tests.test_company_dialogue_runtime_binding import principal_caller
from tests import test_principal_source_reader as relay


@pytest.mark.parametrize("change", ["none", "mutated", "answered", "lease_expired", "authority_revoked", "binding_drift", "continue", "stop", "invalid_option", "policy_denied", "policy_revoked_at_commit"])
def test_fresh_source_fence_through_actual_host_runtime_and_relay(tmp_path, monkeypatch, change):
    fixture = _strict_dialogue_runtime(tmp_path, monkeypatch)
    parent, candidate = fixture.parent, fixture.candidate
    caller = principal_caller(work_ref=parent["work_ref"], root_job_id=fixture.root.job_id)
    worker = {"job_id": candidate.job_id, "attempt_id": candidate.attempt_id,
              "worker_id": candidate.worker_id}
    message = build_message_v2({"schema": "mastermind.agent_dialogue.v2",
        "message_key": "asd-request-runtime-fence-001", "message_type": "DECISION_REQUEST",
        "work_ref": parent["work_ref"], "commission_ref": parent["commission_ref"],
        "session_ref": parent["session_ref"], "actor_ref": {"kind": "worker_attempt", **worker},
        "reply_to_message_key": None, "applies_to": {"kind": "executive_attempt", **worker},
        "summary": "Current source evidence.", "body": _body("DECISION_REQUEST"),
        "evidence_refs": [], "requires_response": True, "created_at": "2026-09-03T01:00:01Z"})
    observed_source = DialogueSourceObservation(relay.WORKSPACE, relay.CHANNEL, relay.THREAD,
        message["message_key"], message["fingerprint"])
    logical = correlated_source_ref(attention_source_ref=attention_source_ref(
        parent_fingerprint=parent["fingerprint"], message_key=message["message_key"],
        target_seat="coo"), parent_fingerprint=parent["fingerprint"],
        operation_key=parent["operation_key"], candidate=candidate.to_dict())
    physical = PhysicalDialogueSourceIdentity.create(logical_source_ref=logical,
        obligation_id=mint_obligation_id(source_kind="agent_dialogue_attention", source_ref=logical,
            wake_kind="dialogue_turn_pending"), observation=observed_source,
        parent_fingerprint=parent["fingerprint"], operation_key=parent["operation_key"],
        target_seat="coo", candidate=candidate.to_dict())
    admission = caller.admission_context
    context = DialogueContextV2(work_ref=parent["work_ref"], commission_ref=parent["commission_ref"],
        session_ref=parent["session_ref"], operation_key=parent["operation_key"],
        watch_mode=parent["watch_mode"], actor_ref={"kind": "executive_principal", "seat": "coo",
            "reasoning_surface": caller.reasoning_surface, "root_job_id": caller.root_job_id,
            "principal_binding_digest": admission.principal_binding_digest,
            "mission_authority_ref": admission.mission_authority_ref,
            "authority_generation_digest": admission.authority_generation_digest,
            "capability_profile_digest": caller.capability_profile_digest},
        applies_to={"kind": "executive_attempt", **worker})

    async def scenario():
        calls = []
        async def observe(reader, writer):
            try:
                request = parse_observation_request(await reader.readline())
                calls.append(request.parent)
                facts = fixture.facts_reader._runtime_dialogue_observation_facts(
                    fixture.runtime, request.parent)
                response = reduce_dialogue_observation(parent=request.parent, facts=facts,
                    thread_ts=relay.THREAD)
                writer.write(response_bytes(response))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        observation_path = tmp_path / "observation.sock"
        server = await asyncio.start_unix_server(observe, path=str(observation_path))
        slack = InMemorySlackClient(relay_bot_user_id=relay.BOT,
            next_timestamp=Decimal(relay.LATER_TS) + Decimal("0.000001"))
        slack.add_parent(SlackMessage(ts=relay.THREAD, author_user_id=relay.BOT,
            text=render_parent_v2(parent)))
        slack.add_reply(SlackMessage(ts=relay.PREDECESSOR_TS, author_user_id=relay.BOT,
            text=render_message_v2(message), thread_ts=relay.THREAD))
        relay_path = tmp_path / "relay.sock"
        service = await relay._start_relay(relay_path, slack)
        denied_policy = service.engine_v2.authority_policy
        class DecisionFixturePolicy:
            def minimum_authority(self, *, request, option):
                return ("WITHIN_COMMISSION" if request["message_key"] == message["message_key"]
                        and option["id"] == "opt-continue" else "CHAIRMAN_REQUIRED")
            def allows_continuation(self, *, request, reply):
                return False
        if change != "policy_denied":
            service.engine_v2.authority_policy = DecisionFixturePolicy()
        try:
            observer = ExecutiveDialogueObservationClient(observation_path)
            initial = await read_current_principal_source(caller=caller, context=context,
                physical_source=physical, socket_path=relay_path, observation_client=observer)
            resolver = Resolver(initial.binding)
            authority = {"current": True, "checks": 0}
            def guard(**_scope):
                authority["checks"] += 1
                if not authority["current"]:
                    raise ValueError("revoked")
            async def service_call(path, request, **kwargs):
                callback = kwargs.get("before_write")
                if callback is not None:
                    async def before_write():
                        if change == "mutated":
                            slack.mutate_reply(thread_ts=relay.THREAD,
                                message_ts=relay.PREDECESSOR_TS, edited=True)
                        elif change == "answered":
                            reply = build_message_v2({**{k: v for k, v in message.items() if k != "fingerprint"},
                                "message_key": "asd-existing-ruling-001", "message_type": "RULING",
                                "actor_ref": dict(initial.binding.actor_ref), "body": _body("RULING"),
                                "reply_to_message_key": message["message_key"], "requires_response": False})
                            slack.add_reply(SlackMessage(ts=relay.LATER_TS, author_user_id=relay.BOT,
                                text=render_message_v2(reply), thread_ts=relay.THREAD))
                        elif change == "lease_expired":
                            monkeypatch.setattr(fixture.runtime.store, "now_ms", lambda: 10**16)
                        elif change == "authority_revoked":
                            authority["current"] = False
                        elif change == "binding_drift":
                            resolver.value = dataclasses.replace(resolver.value,
                                commission_ref={**resolver.value.commission_ref, "commit": "e" * 40})
                        elif change == "policy_revoked_at_commit":
                            service.engine_v2.authority_policy = denied_policy
                        await callback()
                    kwargs["before_write"] = before_write
                return await call_service(path, request, **kwargs)
            host = build_principal_company_dialogue_host(runtime=fixture.runtime,
                binding_resolver=resolver, socket_path=relay_path, service_call=service_call,
                principal_authority_guard=guard,
                principal_decision_source=PrincipalDecisionSource(caller, context, physical, observer))
            tool = change if change in {"continue", "stop"} else "ruling"
            arguments = ({"instruction": "Continue", "stop_condition": "One result"}
                if tool == "continue" else {key: value for key, value in _body("RULING").items()
                                           if key != "canonical_ref"})
            if tool == "stop":
                arguments = _body("STOP")
            if change == "invalid_option":
                arguments["selected_option"] = "opt-not-offered"
            result = await host.gateway.call(tool, arguments)
            events = fixture.runtime.events.list_events(aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE)
            if change == "none":
                assert result["ok"] is True, result
                assert len(events) == 1
                assert slack.post_call_count == 1
                assert authority["checks"] == 1
                key = events[0].aggregate_id
                assert (await host.reconcile(key)).state is PrincipalCommitObservationState.APPLIED
                consumed = await service.engine_v2.wait_for_reply(
                    thread_ts=relay.THREAD,
                    context=dataclasses.replace(context, actor_ref=message["actor_ref"]),
                    request_message_key=message["message_key"], expected_types=("RULING",),
                    max_attempts=1,
                )
                assert consumed["reply"]["message_key"] == key
                assert consumed["authority"]["executable"] is True
                assert consumed["authority"]["disposition"] == "CONTINUE"
                await host.gateway.call(tool, arguments)
                assert slack.post_call_count == 1
                assert len(fixture.runtime.events.list_events(
                    aggregate_type=PRINCIPAL_RUNTIME_AGGREGATE_TYPE)) == 1
            else:
                assert result["ok"] is False, result
                assert result["error"]["code"] == (
                    "DIALOGUE_REFUSED" if change in {"invalid_option", "continue", "policy_denied",
                        "policy_revoked_at_commit"} else "EFFECT_FENCE_UNAVAILABLE")
                if change == "policy_revoked_at_commit":
                    assert len(events) == 1
                    assert (await host.reconcile(events[0].aggregate_id)).state is PrincipalCommitObservationState.EFFECT_UNKNOWN
                else:
                    assert events == []
                assert slack.post_call_count == 0
            assert slack.parent_post_call_count == 0
        finally:
            await service.close()
            server.close()
            await server.wait_closed()
    asyncio.run(scenario())
