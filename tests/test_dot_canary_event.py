"""Pure canary projection tests; no Slack, MCP or network side effects."""
import dataclasses
import hashlib

import pytest

from integrations.slack_agent_dialogue.dot_canary_event import (
    EVENT_NAME, MARKER, TrustedCanaryPolicy, VerifiedSlackCanaryMessage,
    canary_event_definition, project_canary_message,
)

PRINCIPAL = hashlib.sha256(b"chris-dot-candidate").hexdigest()
POLICY = TrustedCanaryPolicy(
    workspace_id="T0BRD2AQXQV", channel_id="C0BSBM78V1N",
    relay_bot_user_id="U0BT71H4FQE", owner_slack_user_id="U0BRET6191C",
    principal_digest=PRINCIPAL, not_before_ts="1794017500.000001", current=True,
)
MSG = VerifiedSlackCanaryMessage(
    workspace_id=POLICY.workspace_id, channel_id=POLICY.channel_id,
    ts="1794017600.000001", author_user_id=POLICY.owner_slack_user_id,
    text=MARKER + " hello, please acknowledge this canary.",
    thread_ts="1794017500.000002", history_complete=True,
    mutation_evidence_complete=True,
)


def project(policy=POLICY, message=MSG, principal=PRINCIPAL, arguments=None):
    return project_canary_message(policy, message,
        authenticated_principal_digest=principal,
        arguments=arguments or {"channel_id": POLICY.channel_id})


def test_exact_event_catalog_requires_current_policy():
    e = canary_event_definition(POLICY)
    assert e["name"] == EVENT_NAME
    assert e["delivery"] == ["webhook"]
    assert e["inputSchema"]["properties"]["channel_id"]["const"] == POLICY.channel_id
    assert e["inputSchema"]["additionalProperties"] is False
    assert e["payloadSchema"]["additionalProperties"] is False
    with pytest.raises(ValueError):
        canary_event_definition(dataclasses.replace(POLICY, current=False))


def test_owner_message_has_stable_event_without_instructions():
    event = project()
    assert event == project()
    assert event["eventId"].startswith("evt-")
    assert event["name"] == EVENT_NAME
    assert event["timestamp"].endswith("Z")
    assert set(event) == {"eventId", "name", "timestamp", "data", "cursor"}
    assert event["data"]["untrusted_text"] is True
    assert event["data"]["author_user_id"] == POLICY.owner_slack_user_id
    assert "instruction" not in event and "user_id" not in event


@pytest.mark.parametrize("changes", [
    {"author_user_id": "U0BT71H4FQE"},  # no bot feedback loops
    {"author_user_id": "U0BR1GQH7SB"},  # no foreign owner
    {"text": "ordinary conversation"},
    {"edited": True},
    {"deleted": True},
    {"ts": "1794017000.000001"},
])
def test_foreign_unmarked_or_mutated_message_is_ignored(changes):
    assert project(message=dataclasses.replace(MSG, **changes)) is None


@pytest.mark.parametrize("policy,message,principal,args", [
    (dataclasses.replace(POLICY, current=False), MSG, PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (POLICY, MSG, hashlib.sha256(b"wrong").hexdigest(), {"channel_id": POLICY.channel_id}),
    (POLICY, MSG, PRINCIPAL, {"channel_id": "C0BRFC9JXK8"}),
    (POLICY, dataclasses.replace(MSG, channel_id="C0BRFC9JXK8"), PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (POLICY, dataclasses.replace(MSG, history_complete=False), PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (POLICY, dataclasses.replace(MSG, mutation_evidence_complete=False), PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (POLICY, dataclasses.replace(MSG, text=MARKER + "X" * 400), PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (POLICY, dataclasses.replace(MSG, ts="bad"), PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (POLICY, dataclasses.replace(MSG, edited=1), PRINCIPAL, {"channel_id": POLICY.channel_id}),
    (dataclasses.replace(POLICY, not_before_ts="invalid"), MSG, PRINCIPAL, {"channel_id": POLICY.channel_id}),
])
def test_unauthorized_or_incomplete_inputs_refuse(policy, message, principal, args):
    with pytest.raises(ValueError):
        project(policy, message, principal, args)


def test_event_id_changes_only_with_message_identity_or_text():
    a = project()
    b = project(message=dataclasses.replace(MSG, ts="1794017600.000002"))
    assert a["eventId"] != b["eventId"]
    c = project(message=dataclasses.replace(MSG, text=MSG.text + "!"))
    assert a["eventId"] != c["eventId"]
