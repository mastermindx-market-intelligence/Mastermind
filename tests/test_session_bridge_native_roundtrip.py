"""Actual Relay service/engine roundtrips, with ONLY Slack/native provider faked."""
import asyncio
import dataclasses
import os
from pathlib import Path
import tempfile

import pytest

from integrations.session_bridge.native_reply import NativeReplyWriter
from integrations.session_bridge.schemas import BridgeError
from integrations.slack_agent_dialogue.contract_v2 import build_message_v2, render_message_v2
from integrations.slack_agent_dialogue.engine import DialogueEngine, DialoguePolicy, SlackMessage
from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.service import AgentDialogueService, ServiceConfig, call_service
from test_session_bridge_native_reply import Resolver, NATIVE, arguments, request, ACTOR

BOT = "U0BST4WG996"
SOL = "U0BRETDUAS2"


class WithinCommission:
    def minimum_authority(self, *, request, option):
        return "WITHIN_COMMISSION"
    def allows_continuation(self, *, request, reply):
        return True


@pytest.mark.parametrize("scenario", ["roundtrip", "concurrent_duplicate", "lost_response"])
@pytest.mark.parametrize("native_role", ["worker", "codex_ceo", "claude_coo"])
def test_real_relay_original_parent_roundtrip(scenario, native_role):
    async def exercise(directory):
        resolver = Resolver()
        actor = ACTOR
        if native_role != "worker":
            actor = {"kind": "executive_surface", "seat": "ceo" if native_role == "codex_ceo" else "coo",
                     "reasoning_surface": "codex" if native_role == "codex_ceo" else "claude"}
            applies = {"kind": "repository", "repository": "mastermindx-market-intelligence/Mastermind",
                       "head_sha": "1" * 40, "pr": "mastermindx-market-intelligence/Mastermind#1112"}
            resolver.binding = dataclasses.replace(resolver.binding, context=dataclasses.replace(
                resolver.binding.context, actor_ref=actor, applies_to=applies))
        original = request()
        original.pop("fingerprint")
        original["applies_to"] = dict(resolver.binding.context.applies_to)
        original = build_message_v2(original)
        policy = DialoguePolicy(workspace_id="T0BRD2AQXQV", channel_id="C0BRUL9F2V7",
            relay_bot_user_id=BOT, allowed_sol_user_ids=(SOL,), allowed_parent_user_ids=(SOL,),
            poll_interval_seconds=0, max_wait_attempts=3)
        client = InMemorySlackClient(relay_bot_user_id=BOT)
        engine = DialogueEngineV2(policy, client, authority_policy=WithinCommission())
        parent = await engine.ensure_thread(resolver.binding.context, created_at="2026-10-01T19:59:00Z")
        thread = parent.thread_ts
        resolver.binding = dataclasses.replace(resolver.binding, thread_ts=thread)
        prior = dict(original)
        prior.pop("fingerprint")
        prior.update(message_key="asd-worker-result-0001", message_type="RESULT", actor_ref=actor,
            reply_to_message_key=None, summary="Fixture worker returned.", body={"status": "PASS", "result": "Fixture only."})
        client.add_reply(SlackMessage(ts=client._mint_ts(), author_user_id=BOT,
            text=render_message_v2(build_message_v2(prior)), thread_ts=thread))
        client.add_reply(SlackMessage(ts=client._mint_ts(), author_user_id=SOL,
            text=render_message_v2(original), thread_ts=thread))
        path = Path(directory) / "relay.sock"
        service = AgentDialogueService(ServiceConfig(socket_path=path, allowed_peer_uids=(os.geteuid(),)),
            DialogueEngine(policy, client, authority_policy=WithinCommission()), engine_v2=engine)
        await service.start()
        try:
            def make_writer(service_call=call_service):
                return NativeReplyWriter(resolver, native_session_id=NATIVE, socket_path=path,
                    service_call=service_call)
            if scenario == "concurrent_duplicate":
                replies = await asyncio.gather(make_writer()(arguments()), make_writer()(arguments()))
                assert len({r["message_key"] for r in replies}) == 1
            elif scenario == "lost_response":
                async def lose_response(socket_path, payload):
                    response = await call_service(socket_path, payload)
                    if payload["operation"] == "send_message":
                        raise TimeoutError("simulated post-commit client response loss")
                    return response
                with pytest.raises(BridgeError) as raised:
                    await make_writer(lose_response)(arguments())
                assert raised.value.code == "carrier_effect_unknown"
                replies = [await make_writer()(arguments())]
                assert replies[0]["action"] == "DUPLICATE"
            else:
                replies = [await make_writer()(arguments()), await make_writer()(arguments())]
                assert replies[1]["action"] == "DUPLICATE"
            assert client.post_call_count == 1
            assert all(r["thread_ts"] == thread and not r["parent_consumed"] for r in replies)
            view = await engine.read_thread(thread_ts=thread, context=resolver.binding.context)
            messages = [item.message for item in view.messages]
            returned = [m for m in messages if m["message_key"] == replies[0]["message_key"]]
            assert len(returned) == 1 and returned[0]["actor_ref"] == actor
            assert returned[0]["body"]["completed"] == arguments()["text"]
            assert returned[0]["reply_to_message_key"] == arguments()["in_reply_to"]
            # Resolve the notification's read_ref through the actual read-only
            # Relay path, preserving original principal and message provenance.
            from integrations.session_bridge.native_read import NativeReplyReader, NativeReplyReadBinding
            from integrations.session_bridge.web_reply_events import CanonicalReplyEventProjector, ReplyEventBinding
            from integrations.business_mcp_auth.principal_projection import principal_projection
            from test_session_bridge_native_read import PRINCIPAL, NOW, READ_REF
            from dataclasses import replace
            physical = next(item for item in view.messages if item.message["message_key"] == replies[0]["message_key"])
            read_binding = NativeReplyReadBinding(authorized_principal=principal_projection(PRINCIPAL),
                read_ref=READ_REF, request_ref="request-001", request_message_key=arguments()["in_reply_to"],
                thread_ts=thread, reply_message_key=returned[0]["message_key"],
                reply_fingerprint=returned[0]["fingerprint"], context=resolver.binding.context,
                authorization_revision="current-auth-001")
            class ReadResolver:
                def resolve_read(self, **kwargs):
                    return read_binding
            event_binding = ReplyEventBinding(principal_ref=PRINCIPAL.subject_digest,
                request_ref="request-001", request_message_key=arguments()["in_reply_to"],
                thread_ts=thread, context=resolver.binding.context, reply_message=returned[0],
                reply_primary_ts=physical.primary_ts, read_ref=READ_REF, access_current=True)
            class EventResolver:
                def resolve_reply(self, **kwargs):
                    return event_binding
            event = CanonicalReplyEventProjector(EventResolver()).project(
                principal_ref=PRINCIPAL.subject_digest, arguments={"request_ref": "request-001"},
                message_key=returned[0]["message_key"])
            read = NativeReplyReader(ReadResolver(), socket_path=path, clock=lambda: NOW)
            content = await read(PRINCIPAL, {"read_ref": event["data"]["read_ref"]})
            assert content["text"] == arguments()["text"] and content["parent_consumed"] is False
            assert content["fingerprint"] == returned[0]["fingerprint"]
            with pytest.raises(BridgeError):
                await read(replace(PRINCIPAL, subject_digest="9" * 64), {"read_ref": READ_REF})
            assert client.post_call_count == 1
        finally:
            await service.close()
    with tempfile.TemporaryDirectory(prefix="native-return-", dir=("/private/tmp" if Path("/private/tmp").is_dir() else "/tmp")) as directory:
        asyncio.run(exercise(directory))
