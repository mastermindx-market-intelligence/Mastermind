"""Actual Relay engine/service and Runtime owners; only Slack is in memory.

The injected authority floor is a fixture. This proves local composition, not
authenticated Slack delivery, installed policy selection or product acceptance.
"""

import dataclasses
import os
from pathlib import Path

import pytest

from integrations.product_acceptance_request_owner import (
    ProductAcceptanceRequestUnavailable,
)
from integrations.product_acceptance_ruling_owner import AGGREGATE
from integrations.slack_agent_dialogue.contract_v2 import render_message_v2
from integrations.slack_agent_dialogue.engine import DialogueEngineError, SlackMessage
from integrations.slack_agent_dialogue.fake_slack import InMemorySlackClient
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService,
    DialogueServiceError,
    ServiceConfig,
)
from tests.test_product_acceptance_ruling_owner import (
    complete_parent,
    qualify,
    ready,
)
from tests.test_slack_agent_dialogue_engine_v2 import (
    BOT,
    make_engine,
    parent_message,
)


class BoundAuthorityFloor:
    def __init__(self, request_key, floor):
        self.request_key, self.floor = request_key, floor
        self.calls = 0

    def minimum_authority(self, *, request, option):
        assert request["message_key"] == self.request_key
        assert option["id"] == "opt-product-accept"
        self.calls += 1
        return self.floor

    def allows_continuation(self, *, request, reply):
        raise AssertionError("this qualification only accepts a RULING")


def actual_relay(values, *, variant="valid"):
    _runtime, _requester, binding, _target, _basis, prepared, owner, relay, _ = values
    client = InMemorySlackClient(relay_bot_user_id=BOT)
    client.add_parent(
        parent_message(
            ts=binding.thread_ts,
            work_ref=binding.work_ref,
            commission_ref=binding.commission_ref,
            session_ref=binding.session_ref,
            operation_key=binding.operation_key,
            watch_mode=binding.watch_mode,
        )
    )
    request_frame = SlackMessage(
        ts="1787896129.625239",
        thread_ts=binding.thread_ts,
        author_user_id=BOT,
        text=render_message_v2(prepared.message),
    )
    reply_frame = SlackMessage(
        ts="1787896130.625239",
        thread_ts=binding.thread_ts,
        author_user_id="U0000000000" if variant == "unauthorized_sender" else BOT,
        text=render_message_v2(relay.reply),
    )
    if variant == "edited_request":
        request_frame = dataclasses.replace(
            request_frame, edited=True, created_text=request_frame.text
        )
    if variant == "reply_before_request":
        reply_frame = dataclasses.replace(reply_frame, ts="1787896128.725239")
    client.add_reply(request_frame)
    client.add_reply(reply_frame)
    if variant == "duplicate_reply":
        client.add_reply(dataclasses.replace(reply_frame, ts="1787896131.625239"))
    if variant == "incomplete_history":
        client.thread_history_complete = False
    authority = BoundAuthorityFloor(
        prepared.message["message_key"],
        (
            "CHAIRMAN_REQUIRED"
            if variant == "higher_authority_floor"
            else "WITHIN_COMMISSION"
        ),
    )
    engine = make_engine(client, authority_policy=authority)
    # No socket is created. The actual dispatcher and serializer are exercised
    # through the same injected service seam used by the production owners.
    service = AgentDialogueService(
        ServiceConfig(Path("/private/tmp/r2-relay-fixture.sock"), (os.geteuid(),)),
        engine,
        engine_v2=engine,
    )
    calls = []

    async def dispatch(_path, request):
        calls.append(request["operation"])
        assert request["operation"] in {"read_thread", "wait_for_reply"}
        try:
            return {"ok": True, "result": await service._dispatch(request)}
        except (DialogueEngineError, DialogueServiceError) as exc:
            return {"ok": False, "error": {"code": exc.code}}

    owner.principal_owner.service_call = dispatch
    return client, authority, calls


def test_actual_relay_service_qualifies_then_requires_both_terminal_returns(
    tmp_path, monkeypatch
):
    values = ready(tmp_path, monkeypatch)
    client, authority, calls = actual_relay(values)
    qualified = qualify(values)
    runtime, requester, _binding, _target, _basis, prepared, owner, *_ = values
    assert qualified["state"] == "RULING_QUALIFIED_PARENT_RETURN_PENDING"
    with pytest.raises(
        ProductAcceptanceRequestUnavailable, match="PRODUCT_PARENT_RETURN_UNVERIFIED"
    ):
        owner.observe_acceptance(prepared.message["message_key"])
    complete_parent(runtime, requester, [qualified["evidence_digest"]])
    assert (
        owner.observe_acceptance(prepared.message["message_key"])["state"]
        == "PRODUCT_ACCEPTED"
    )
    assert authority.calls >= 1
    assert "read_thread" in calls and "wait_for_reply" in calls
    assert client.post_call_count == client.parent_post_call_count == 0


@pytest.mark.parametrize(
    "variant",
    [
        "unauthorized_sender",
        "reply_before_request",
        "duplicate_reply",
        "edited_request",
        "incomplete_history",
        "higher_authority_floor",
    ],
)
def test_real_relay_rejection_never_creates_a_qualified_ruling(
    tmp_path, monkeypatch, variant
):
    values = ready(tmp_path, monkeypatch)
    client, _authority, _calls = actual_relay(values, variant=variant)
    with pytest.raises(ProductAcceptanceRequestUnavailable):
        qualify(values)
    assert values[0].events.list_events(aggregate_type=AGGREGATE) == []
    assert client.post_call_count == client.parent_post_call_count == 0
