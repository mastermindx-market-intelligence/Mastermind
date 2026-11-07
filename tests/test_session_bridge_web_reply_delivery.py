"""MCP Events signed-delivery contract: no HTTP, storage, subscription or runtime effects."""
from __future__ import annotations
import base64
import hashlib
import hmac
import importlib
import json
from datetime import datetime, timezone

import pytest

SOURCE = "integrations.session_bridge.web_reply_delivery"
SECRET = "whsec_" + base64.b64encode(b"z" * 32).decode("ascii")
OLD_SECRET = "whsec_" + base64.b64encode(b"y" * 32).decode("ascii")


def api():
    return importlib.import_module(SOURCE)


def event():
    return {
        "eventId": "evt-" + "a" * 64,
        "name": "session.reply_committed",
        "timestamp": "2026-10-12T01:00:00.000001Z",
        "data": {
            "request_ref": "request-001",
            "message_key": "asd-native-reply-001",
            "in_reply_to": "asd-original-001",
            "summary": "Worker result retained. Read through the canonical owner.",
            "read_ref": "native-return-read-001",
            "reply_committed": True,
            "parent_consumed": False,
        },
        "cursor": None,
    }


def binding(**changes):
    return api().VerifiedReplySubscription(
        subscription_id=changes.pop("subscription_id", "sub-001"),
        principal_ref=changes.pop("principal_ref", "principal-001"),
        request_ref=changes.pop("request_ref", "request-001"),
        event_name=changes.pop("event_name", "session.reply_committed"),
        access_current=changes.pop("access_current", True),
        active=changes.pop("active", True),
        expires_at=changes.pop("expires_at", 1_800_000_000),
        signing_secrets=changes.pop("signing_secrets", (SECRET,)),
        **changes,
    )


def sign(*, target=None, payload=None, signed_at=1791766800):
    return api().prepare_reply_webhook(
        subscription=binding() if target is None else target,
        event=event() if payload is None else payload,
        signed_at=signed_at,
    )


def test_exact_signed_bytes_and_headers_interoperate_with_standard_webhooks():
    result = sign()
    assert type(result.body) is bytes
    assert len(result.body) < 8192
    assert set(result.headers) == {
        "Content-Type", "webhook-id", "webhook-timestamp",
        "webhook-signature", "X-MCP-Subscription-Id",
    }
    assert result.headers["Content-Type"] == "application/json"
    assert result.headers["webhook-id"] == event()["eventId"]
    assert result.headers["webhook-timestamp"] == "1791766800"
    assert result.headers["X-MCP-Subscription-Id"] == "sub-001"
    assert json.loads(result.body) == event()
    expected = hmac.new(
        b"z" * 32,
        (event()["eventId"] + ".1791766800.").encode("ascii") + result.body,
        hashlib.sha256,
    ).digest()
    assert result.headers["webhook-signature"] == "v1," + base64.b64encode(expected).decode("ascii")
    assert result.body == sign().body
    assert result.headers == sign().headers
    assert "whsec_" not in repr(result)


def test_return_packet_is_immutable_and_attempt_timestamp_is_fresh():
    first = sign()
    with pytest.raises(TypeError):
        first.headers["webhook-id"] = "evt-forged"
    second = sign(signed_at=1791766801)
    assert first.body == second.body
    assert first.headers["webhook-id"] == second.headers["webhook-id"]
    assert first.headers["webhook-signature"] != second.headers["webhook-signature"]
    assert second.headers["webhook-timestamp"] == "1791766801"


def test_real_canonical_projector_output_is_signed_without_rewriting_event_identity():
    from test_session_bridge_web_reply_events import Resolver, project
    projected = project(Resolver())
    result = sign(payload=projected)
    assert json.loads(result.body) == projected
    assert result.headers["webhook-id"] == projected["eventId"]
    assert projected["data"]["parent_consumed"] is False
    assert projected["cursor"] is None


def test_validated_rotating_secrets_sign_identical_body_with_two_keys():
    result = sign(target=binding(signing_secrets=(SECRET, OLD_SECRET)))
    signatures = result.headers["webhook-signature"].split(" ")
    assert len(signatures) == 2
    for key, signature in zip((b"z" * 32, b"y" * 32), signatures):
        expect = base64.b64encode(hmac.new(
            key,
            (event()["eventId"] + ".1791766800.").encode() + result.body,
            hashlib.sha256,
        ).digest()).decode()
        assert signature == "v1," + expect


@pytest.mark.parametrize("changes", [
    {"request_ref": "request-002"}, {"event_name": "other.event"},
    {"access_current": False}, {"access_current": 1},
    {"active": False}, {"active": 1},
    {"expires_at": 1791766799}, {"expires_at": True},
    {"principal_ref": ""}, {"subscription_id": "invalid\nheader"},
    {"signing_secrets": ()}, {"signing_secrets": (SECRET, SECRET)},
    {"signing_secrets": ("whsec_a",)}, {"signing_secrets": ("raw-key",)},
    {"signing_secrets": (SECRET, OLD_SECRET, SECRET)},
])
def test_untrusted_or_expired_subscription_is_never_signed(changes):
    with pytest.raises(ValueError):
        sign(target=binding(**changes))


@pytest.mark.parametrize("change", [
    {"eventId": "evt-foreign"}, {"name": "other.event"},
    {"cursor": "cursor-1"}, {"type": "instruction"},
    {"timestamp": "invalid"},
])
def test_foreign_or_malformed_event_is_never_signed(change):
    payload = {**event(), **change}
    with pytest.raises(ValueError):
        sign(payload=payload)


@pytest.mark.parametrize("data_change", [
    {"request_ref": "request-002"},
    {"read_ref": ""}, {"summary": "x" * 361},
    {"reply_committed": False}, {"parent_consumed": True},
    {"message_key": "x\ninjected"}, {"unexpected_route": "second-parent"},
])
def test_untrusted_event_data_cannot_select_visitor_or_fake_parent_consumption(data_change):
    payload = event()
    payload["data"] = {**event()["data"], **data_change}
    with pytest.raises(ValueError):
        sign(payload=payload)


def test_invalid_timing_and_signing_inputs_are_refused():
    for value in [True, -1, 17999999999, 1.2, "1791766800"]:
        with pytest.raises(ValueError):
            sign(signed_at=value)


@pytest.mark.parametrize("status,expected", [
    (200, "TRANSPORT_ACCEPTED_PARENT_UNPROVEN"),
    (202, "TRANSPORT_ACCEPTED_PARENT_UNPROVEN"),
    (204, "TRANSPORT_ACCEPTED_PARENT_UNPROVEN"),
    (410, "DELIVERY_TERMINAL_REFUSAL"),
    (413, "DELIVERY_TERMINAL_REFUSAL"),
    (429, "RETRY_DECISION_BY_EXISTING_OWNER"),
    (500, "RETRY_DECISION_BY_EXISTING_OWNER"),
    (503, "RETRY_DECISION_BY_EXISTING_OWNER"),
    (408, "RETRY_DECISION_BY_EXISTING_OWNER"),
    (302, "REFUSED_NO_REDIRECT"),
    (401, "DELIVERY_REFUSED"),
    (400, "DELIVERY_REFUSED"),
])
def test_http_response_is_transport_status_not_worker_or_parent_acceptance(status, expected):
    result = api().classify_reply_webhook_response(status)
    assert result == expected
    if 200 <= status < 300:
        assert result.endswith("PARENT_UNPROVEN")
    else:
        assert "ACCEPTED_PARENT" not in result


def test_missing_or_invalid_response_never_proves_undelivered_or_consumed():
    for status in [None, 0, False, True, 600, "200"]:
        assert api().classify_reply_webhook_response(status) == "EFFECT_UNKNOWN"


def test_no_network_or_store_and_no_implicit_retry():
    module = api()
    assert not hasattr(module, "send_webhook")
    assert not hasattr(module, "create_subscription")
    assert "secret" not in repr(binding())


def pending(**changes):
    return api().PendingReplyCallback(
        subscription_id=changes.pop("subscription_id", "sub-001"),
        principal_ref=changes.pop("principal_ref", "principal-001"),
        request_ref=changes.pop("request_ref", "request-001"),
        access_current=changes.pop("access_current", True),
        expires_at=changes.pop("expires_at", 1_800_000_000),
        signing_secret=changes.pop("signing_secret", SECRET),
        **changes,
    )


def test_callback_verification_uses_signed_one_time_challenge_bytes():
    nonce = "challenge_0123456789abcdef"
    message_id = "msg_verification_0123456789"
    result = api().prepare_reply_webhook_verification(
        callback=pending(), challenge=nonce,
        message_id=message_id, signed_at=1791766800,
    )
    assert json.loads(result.body) == {"type": "verification", "challenge": nonce}
    assert result.headers["webhook-id"] == message_id
    assert result.headers["X-MCP-Subscription-Id"] == "sub-001"
    expected = hmac.new(b"z" * 32, (
        message_id + ".1791766800.").encode() + result.body, hashlib.sha256).digest()
    assert result.headers["webhook-signature"] == "v1," + base64.b64encode(expected).decode()
    assert "whsec_" not in repr(result) and "whsec_" not in repr(pending())


def test_callback_challenge_echo_requires_2xx_exact_reply_and_original_nonce():
    f = api().verify_reply_webhook_challenge_response
    nonce = "challenge_0123456789abcdef"
    reply = json.dumps({"challenge": nonce}).encode()
    assert f(challenge=nonce, response_body=reply, status=200) is True
    assert f(challenge=nonce, response_body=reply, status=204) is True
    assert f(challenge=nonce, response_body=reply, status=302) is False
    assert f(challenge=nonce, response_body=reply, status=None) is False
    for bad in [
        b"", b"not-json", json.dumps({"challenge": "wrong"}).encode(),
        json.dumps({"challenge": nonce, "unexpected": True}).encode(),
        json.dumps([nonce]).encode(),
        json.dumps({"challenge": nonce + "1"}).encode(),
    ]:
        assert f(challenge=nonce, response_body=bad, status=200) is False


@pytest.mark.parametrize("changes", [
    {"access_current": False}, {"access_current": 1},
    {"expires_at": 1}, {"expires_at": True},
    {"signing_secret": "wrong"}, {"subscription_id": "wrong\nheader"},
])
def test_inactive_pending_callback_cannot_be_signed(changes):
    with pytest.raises(ValueError):
        api().prepare_reply_webhook_verification(
            callback=pending(**changes), challenge="challenge_0123456789abcdef",
            message_id="msg_verification_0123456789", signed_at=1791766800,
        )


@pytest.mark.parametrize("challenge,message_id", [
    ("", "msg_verification_0123456789"),
    ("test", "msg_verification_0123456789"),
    ("x" * 512, "msg_verification_0123456789"),
    ("challenge_0123456789abcdef", "msg.evil"),
    ("challenge_0123456789abcdef", "other_123"),
])
def test_invalid_nonce_or_message_identity_is_rejected(challenge, message_id):
    with pytest.raises(ValueError):
        api().prepare_reply_webhook_verification(
            callback=pending(), challenge=challenge,
            message_id=message_id, signed_at=1791766800,
        )
