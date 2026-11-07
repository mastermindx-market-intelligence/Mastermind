"""Closed default-OFF canary admission on the ORIGINAL installed Executive documents.

No live user OAuth, Slack app, key provisioning, new policy file or host mutation.
"""
from __future__ import annotations

import copy

import pytest

from ops.executive_os.executive_mcp_entry import validate_document
from integrations.session_bridge.dot_canary_policy_selection import (
    validate_dot_canary_settings,
)
from integrations.session_bridge.reply_event_host_composition import (
    validate_reply_event_host_config,
)
from test_executive_coo_install_binding import base_document


def owner_document():
    config = base_document()
    config.update(
        executive_mcp_profile="web_ceo_v3",
        reply_events_armed=True,
        dot_canary={
            "armed":True,
            "subject_digest":"1"*64,
            "workspace_id":"T0BRD2AQXQV",
            "channel_id":"C0BSBM78V1N",
            "relay_bot_user_id":"U0BT71H4FQE",
            "owner_slack_user_id":"U0BRET6191C",
            "not_before_ts":"1794017500.000001",
        },
    )
    return config


def original_runtime_config():
    return {
        "armed":True,
        "mcp_config_path":"/fixture/owner.json",
        "storage_key_path":"/fixture/storage.key",
        "storage_key_id":"fixture-id",
    }


def test_original_executive_document_has_no_implicit_canary():
    default = base_document()
    assert validate_document(default) == default
    assert validate_dot_canary_settings(default) is None
    existing = original_runtime_config()
    assert validate_reply_event_host_config(existing) == existing
    assert "dot_canary_enabled" not in existing


def test_armed_chris_owner_is_accepted_by_original_document_schema():
    config = owner_document()
    assert validate_document(config) == config
    selected = validate_dot_canary_settings(config)
    assert selected is not None
    assert selected["subject_digest"] == "1"*64
    assert selected["owner_slack_user_id"] == "U0BRET6191C"
    config = original_runtime_config()
    config["dot_canary_enabled"] = True
    assert validate_reply_event_host_config(config) == config


@pytest.mark.parametrize("change", [
    {"dot_canary": {"armed":False, "subject_digest":"1"*64}},
    {"dot_canary": {"armed":"yes"}},
    {"dot_canary": {"armed":True}},
    {"dot_canary": {**owner_document()["dot_canary"],"extra":True}},
    {"dot_canary": {**owner_document()["dot_canary"],"subject_digest":"wrong"}},
    {"dot_canary": {**owner_document()["dot_canary"],"workspace_id":"Twrong"}},
    {"dot_canary": {**owner_document()["dot_canary"],"channel_id":"Cinvalid"}},
    {"dot_canary": {**owner_document()["dot_canary"],"relay_bot_user_id":"Uinvalid"}},
    {"dot_canary": {**owner_document()["dot_canary"],"not_before_ts":"invalid"}},
    {"reply_events_armed":False},
    {"executive_mcp_profile":"legacy"},
])
def test_unrecognized_or_incomplete_canary_enrollment_fails_closed(change):
    value=owner_document()
    value.update(copy.deepcopy(change))
    with pytest.raises(ValueError):
        validate_document(value)


@pytest.mark.parametrize("change", [
    {"dot_canary_enabled":"yes"},
    {"dot_canary_enabled":None},
    {"dot_canary_enabled":1},
    {"extra":True},
])
def test_original_runtime_canary_flag_must_be_closed_boolean(change):
    value=original_runtime_config()
    value.update(change)
    with pytest.raises(ValueError):
        validate_reply_event_host_config(value)


def test_explicitly_disarmed_host_has_no_canary_or_key_custody_args():
    assert validate_reply_event_host_config({"armed":False}) is None
    with pytest.raises(ValueError):
        validate_reply_event_host_config({
            "armed":False,"dot_canary_enabled":True,
        })
    with pytest.raises(ValueError):
        validate_reply_event_host_config({
            **original_runtime_config(),"storage_key_id":"bad key",
        })
