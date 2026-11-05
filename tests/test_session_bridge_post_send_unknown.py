"""Unknown post-send callback settlement is never downgraded to unavailable."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from integrations.session_bridge.installed_reply_events import RuntimeReplyEventHost
from integrations.session_bridge.runtime_reply_authorization import BoundedReplyAuthorizationUnavailable
from integrations.session_bridge.runtime_reply_delivery import ReplyDeliveryUnavailable


def _host(delivery):
    host = object.__new__(RuntimeReplyEventHost)
    host.enabled = True
    host.returns = SimpleNamespace(
        _stored_request=lambda _ref: (SimpleNamespace(command_id="request-one"), {}),
        resolve_read=lambda **_kwargs: asyncio.sleep(
            0, result=SimpleNamespace(
                reply_message_key="reply-one", reply_fingerprint="fingerprint-one"
            )
        ),
    )
    host.store = SimpleNamespace(
        subscriptions_for_reply=lambda _request, _ref: ("subscription-one",)
    )
    host.audiences = SimpleNamespace(
        capture=lambda _ident: "audience",
        current=lambda _audience: "principal",
        revoke_observed=lambda _denial: asyncio.sleep(0),
    )
    host.delivery = delivery
    return host


def _observe(host):
    return asyncio.run(host.handle_committed(
        read_ref="read-one", message_key="reply-one",
        fingerprint="fingerprint-one",
    ))[0]


def test_post_send_settlement_error_keeps_original_effect_unknown():
    class AfterSendFailure:
        callback_attempted = False

        async def deliver_subscription(self, _ident):
            self.callback_attempted = True
            raise RuntimeError("post-send settlement unknown")

    delivery = AfterSendFailure()
    result = _observe(_host(delivery))
    assert delivery.callback_attempted is True
    assert result == {"state": "EFFECT_UNKNOWN", "parent_consumed": False}


def test_expired_authorization_before_send_is_unavailable():
    class NotCalled:
        def deliver_subscription(self, _ident):
            raise AssertionError("expired authorization must not enter delivery")

    host = _host(NotCalled())

    def refuse(_ident):
        raise BoundedReplyAuthorizationUnavailable()

    host.audiences.capture = refuse
    assert _observe(host) == {"state": "UNAVAILABLE", "parent_consumed": False}


def test_typed_pre_send_refusal_stays_unavailable():
    class BeforeSendRefusal:
        callback_attempted = False

        async def deliver_subscription(self, _ident):
            raise ReplyDeliveryUnavailable("current authorization unavailable")

    delivery = BeforeSendRefusal()
    result = _observe(_host(delivery))
    assert delivery.callback_attempted is False
    assert result == {"state": "UNAVAILABLE", "parent_consumed": False}
