"""Actual Runtime fact producer and Relay wire meet at the principal read join.

Principals, provider identity and physical Slack storage are explicit fixtures.
This proves the local source composition, not enrolled-account authentication.
"""
import asyncio
import traceback

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


def test_actual_runtime_projection_crosses_the_client_and_relay_readers(tmp_path, monkeypatch):
    fixture = _strict_dialogue_runtime(tmp_path, monkeypatch)
    parent, candidate = fixture.parent, fixture.candidate
    caller = principal_caller(work_ref=parent["work_ref"], root_job_id=fixture.root.job_id)
    worker = {"job_id": candidate.job_id, "attempt_id": candidate.attempt_id,
              "worker_id": candidate.worker_id}
    message = build_message_v2({"schema": "mastermind.agent_dialogue.v2",
        "message_key": "asd-progress-runtime-reader-001", "message_type": "PROGRESS",
        "work_ref": parent["work_ref"], "commission_ref": parent["commission_ref"],
        "session_ref": parent["session_ref"], "actor_ref": {"kind": "worker_attempt", **worker},
        "reply_to_message_key": None, "applies_to": {"kind": "executive_attempt", **worker},
        "summary": "Current source evidence.", "body": {"stage": "source",
            "completed": "Read the original source.", "next": "Return the bounded result."},
        "evidence_refs": [], "requires_response": False, "created_at": "2026-09-03T01:00:01Z"})
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
    before = fixture.runtime.events.list_events()

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
        slack = InMemorySlackClient(relay_bot_user_id=relay.BOT)
        slack.add_parent(SlackMessage(ts=relay.THREAD, author_user_id=relay.BOT,
            text=render_parent_v2(parent)))
        slack.add_reply(SlackMessage(ts=relay.PREDECESSOR_TS, author_user_id=relay.BOT,
            text=render_message_v2(message), thread_ts=relay.THREAD))
        relay_path = tmp_path / "relay.sock"
        service = await relay._start_relay(relay_path, slack)
        try:
            result = await read_current_principal_source(caller=caller, context=context,
                physical_source=physical, socket_path=relay_path,
                observation_client=ExecutiveDialogueObservationClient(observation_path))
        except Exception as error:
            # Identify the failing local contract without dumping fixture state.
            contexts = []
            current = error
            while current is not None:
                contexts.append((type(current).__name__, [
                    (frame.name, frame.lineno) for frame in traceback.extract_tb(current.__traceback__)]))
                current = current.__context__
            raise AssertionError(contexts) from error
        finally:
            await service.close()
            server.close()
            await server.wait_closed()
        assert calls == [parent]
        assert slack.post_call_count == slack.parent_post_call_count == 0
        assert result.observation.candidate == fixture.candidate
        assert result.binding.applies_to["attempt_id"] == fixture.sealed.attempt_id
        assert result.binding.reply_to_message_key == message["message_key"]
    asyncio.run(scenario())
    assert fixture.runtime.events.list_events() == before
