"""Original A2 closed service operation plus Executive existing-socket read adapter.

One synthetic Slack HTTP reply; never starts a live relay or delivers webhook.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from integrations.slack_agent_dialogue.engine import DialoguePolicy
from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
from integrations.slack_agent_dialogue.runtime import (
    AGENT_RELAY_SOCKET_PATH,PrivateRelayAuthorityPolicy,
)
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService, ServiceConfig, DialogueServiceError,
)
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from integrations.session_bridge.installed_dot_canary_source import InstalledA2CanaryReader
from integrations.slack_agent_dialogue.dot_canary_reader import CanarySourceUnavailable
from test_dot_canary_reader import (
    FakeSlack, POLICY, CHANNEL, ROOT, MESSAGE, TEAM, BOT, USER, messages,
)


def create(tmp_path,*,enabled=True,raw=None,selected_policy=POLICY):
    http=FakeSlack() if raw is None else raw
    client=SlackWebApiDialogueClient(
        token="fixture-token",workspace_id=TEAM,channel_id=CHANNEL,
        bot_user_id=BOT,transport=http,
    )
    policy=DialoguePolicy(
        workspace_id=TEAM,channel_id=CHANNEL,relay_bot_user_id=BOT,
        allowed_sol_user_ids=("U0BRETDUAS2",),
        allowed_parent_user_ids=("U0BRETDUAS2",),
    )
    engine=DialogueEngineV2(
        policy,client,authority_policy=PrivateRelayAuthorityPolicy(),
    )
    service=AgentDialogueService(
        ServiceConfig(socket_path=tmp_path/"existing-a2.sock",
                      allowed_peer_uids=(os.geteuid(),)),
        engine=None,engine_v2=engine,dot_canary_armed=enabled,
    )
    async def transport(path, request, *, timeout_seconds):
        assert path==AGENT_RELAY_SOCKET_PATH
        assert request["version"]=="mastermind.agent_dialogue_control.v2"
        return {"ok":True,"result":await service._dispatch_v2(
            request["operation"],request["args"],
        )}
    client=InstalledA2CanaryReader(
        AGENT_RELAY_SOCKET_PATH,selected_policy,transport=transport,
    )
    return client,http,service


def run(reader):
    return asyncio.run(reader.observe(thread_ts=ROOT,message_ts=MESSAGE))


def test_existing_a2_service_and_executive_reader_preserve_exact_source(tmp_path):
    reader,http,service=create(tmp_path)
    observed=run(reader)
    assert observed.workspace_id==TEAM and observed.author_user_id==USER
    assert observed.text.startswith("MMX_CHRIS_DOT_CANARY_V1:")
    assert observed.ts==MESSAGE and observed.thread_ts==ROOT
    assert len(http.calls)==1 and http.calls[0][1]=="conversations.replies"


def test_default_off_A2_cannot_supply_existing_gateway(tmp_path):
    reader,http,service=create(tmp_path,enabled=False)
    with pytest.raises(CanarySourceUnavailable):
        run(reader)
    assert not http.calls


def test_foreign_sender_returns_no_message_even_in_approved_channel(tmp_path):
    data=messages();data[1]["user"]="U0BR1GQH7SB"
    reader,http,service=create(tmp_path,raw=FakeSlack(data))
    assert run(reader) is None


def test_incomplete_A2_history_is_not_treated_as_valid_remote_attestation(tmp_path):
    reader,http,service=create(tmp_path,raw=FakeSlack(complete=False))
    with pytest.raises(CanarySourceUnavailable):
        run(reader)


def test_wrong_channel_in_request_refused_without_network(tmp_path):
    reader,http,service=create(tmp_path)
    async def bad():
        return await service._dispatch_v2("read_dot_canary",{
            "thread_ts":ROOT,"message_ts":MESSAGE,
            "owner_slack_user_id":USER,
            "principal_digest":POLICY.principal_digest,
            "not_before_ts":POLICY.not_before_ts,
            "channel_id":"C0BRFC9JXK8",
        })
    with pytest.raises(Exception):
        asyncio.run(bad())
    assert not http.calls



def test_real_local_A2_socket_roundtrip_with_existing_peer_identity(tmp_path,monkeypatch):
    """Use a disposable actual AF_UNIX socket; no Slack/production token."""
    import integrations.session_bridge.installed_dot_canary_source as installed_source
    reader,http,service=create(tmp_path)
    private_socket=service.config.socket_path
    monkeypatch.setattr(installed_source,"AGENT_RELAY_SOCKET_PATH",private_socket)
    native=installed_source.InstalledA2CanaryReader(private_socket,POLICY)

    async def exercise():
        task=asyncio.create_task(service.serve_one())
        for _ in range(100):
            if private_socket.exists():
                break
            await asyncio.sleep(.01)
        assert private_socket.exists()
        result=await native.observe(thread_ts=ROOT,message_ts=MESSAGE)
        await asyncio.wait_for(task,timeout=3)
        return result
    observed=asyncio.run(exercise())
    assert observed.ts==MESSAGE and observed.author_user_id==USER
    assert observed.text.startswith("MMX_CHRIS_DOT_CANARY_V1:")
    assert http.calls and http.calls[0][1]=="conversations.replies"
    assert not private_socket.exists()
