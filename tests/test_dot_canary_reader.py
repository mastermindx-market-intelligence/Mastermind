"""One-shot Chris-Dot canary from existing Slack A2 read transport; no API network."""
from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

from integrations.slack_agent_dialogue.dot_canary_event import (
    MARKER, TrustedCanaryPolicy,
)
from integrations.slack_agent_dialogue.dot_canary_reader import (
    ExistingA2CanaryReader, CanarySourceUnavailable,
)
from integrations.slack_agent_dialogue.slack_web_api import (
    SlackHttpResponse, SlackWebApiDialogueClient, _request_url,
)

ROOT = "1794017500.000002"
MESSAGE = "1794017600.000001"
CHANNEL = "C0BSBM78V1N"
USER = "U0BRET6191C"
BOT = "U0BT71H4FQE"
TEAM = "T0BRD2AQXQV"
POLICY = TrustedCanaryPolicy(
    workspace_id=TEAM, channel_id=CHANNEL, relay_bot_user_id=BOT,
    owner_slack_user_id=USER, principal_digest="a"*64,
    not_before_ts="1794017500.000001", current=True,
)


def messages():
    return [
        {"type":"message","ts":ROOT,"user":USER,"text":"Parent"},
        {"type":"message","ts":MESSAGE,"user":USER,
         "thread_ts":ROOT,"text":MARKER+" test account."},
    ]


class FakeSlack:
    def __init__(self, records=None, *, complete=True):
        self.records=messages() if records is None else records
        self.complete=complete
        self.calls=[]

    async def request(self, *, method,path,token,query,json_body):
        self.calls.append((method,path,dict(query or {})))
        body={"ok":True,"messages":self.records,
              "has_more":not self.complete,
              "response_metadata":{"next_cursor":"cursor1" if not self.complete else ""}}
        return SlackHttpResponse(
            status_code=200, final_url=_request_url(path,query),
            headers={"Content-Type":"application/json"}, body=json.dumps(body).encode(),
        )


def run(source, *, thread_ts=ROOT, message_ts=MESSAGE):
    return asyncio.run(source.observe(thread_ts=thread_ts, message_ts=message_ts))


def source(fake=None, policy=POLICY):
    fake = FakeSlack() if fake is None else fake
    client = SlackWebApiDialogueClient(
        token="fixture-only",workspace_id=TEAM,channel_id=CHANNEL,
        bot_user_id=BOT,transport=fake,
    )
    return ExistingA2CanaryReader(client,policy),fake


def test_exact_original_a2_read_proves_sender_workspace_and_thread():
    reader,fake=source()
    result=run(reader)
    assert result.ts==MESSAGE and result.author_user_id==USER
    assert result.text.startswith(MARKER) and result.thread_ts==ROOT
    assert result.history_complete and result.mutation_evidence_complete
    assert fake.calls[0][:2]==("GET","conversations.replies")
    assert fake.calls[0][2]["channel"]==CHANNEL
    assert fake.calls[0][2]["ts"]==ROOT


@pytest.mark.parametrize("change",[
    {"user":"U0BR1GQH7SB"},
    {"text":"No marker"},
    {"bot_id":"B0BUDHZ137A","user":"U0BT71H4FQE"},
])
def test_foreign_or_unmarked_message_never_projects(change):
    data=messages();data[1].update(change)
    reader,_=source(FakeSlack(data))
    assert run(reader) is None


def test_incomplete_history_cannot_look_like_observed_canary():
    reader,_=source(FakeSlack(complete=False))
    with pytest.raises(CanarySourceUnavailable):
        run(reader)


@pytest.mark.parametrize("wrong",[
    {"channel_id":"C0BRFC9JXK8"},
    {"relay_bot_user_id":"U0BTF3QGABF"},
    {"workspace_id":"T0BRD2AQXQW"},
])
def test_owner_policy_must_match_actual_enrolled_a2_client(wrong):
    with pytest.raises(CanarySourceUnavailable):
        source(policy=dataclasses.replace(POLICY,**wrong))


def test_missing_and_wrong_message_ts_refuse_without_slack_writer():
    reader,fake=source()
    with pytest.raises(CanarySourceUnavailable):
        run(reader,message_ts="1794017600.000002")
    with pytest.raises(CanarySourceUnavailable):
        run(reader,thread_ts="bad")
    assert all(call[0]=="GET" for call in fake.calls)


def test_edited_message_or_mutation_uncertainty_refuses():
    data=messages()
    data[1]["edited"]={"user":USER,"ts":MESSAGE}
    reader,_=source(FakeSlack(data))
    with pytest.raises(CanarySourceUnavailable):
        run(reader)
