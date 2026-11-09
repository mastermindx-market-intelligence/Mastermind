"""Offline Slack ingress qualification: no network, tokens, service or model."""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from slack_ingress import (  # noqa: E402
    CurrentTarget, CurrentThread, IngressRefusal, SlackHermesIngress,
    verify_signed_event,
)

TEAM = "T0BRD2AQXQV"
APP = "A0TESTAPPP1"
BOT = "U0BT71H4FQE"
CHRIS = "U0BRET6191C"
ROOM = "C0C5FCK1F45"
DOTS = "C0CBC6AEAQZ"
DM = "D0RELAYTEST"
SOURCE_TS = "1794180060.123456"
THREAD_TS = "1794180000.123456"
SIGNING = b"example-signing-secret-not-real"
NOW = 1794180100


def envelope(*, kind="app_mention", text=None, channel=ROOM, ts=SOURCE_TS,
             thread_ts=None, user=CHRIS, **extra):
    event = {"type": kind, "channel": channel, "user": user, "ts": ts,
             "text": text if text is not None else f"<@{BOT}> engineering: repair test"}
    if thread_ts is not None:
        event["thread_ts"] = thread_ts
    event.update(extra)
    return {"type": "event_callback", "team_id": TEAM, "api_app_id": APP,
            "event_id": "Ev0TEST123456", "event": event}


def signed(payload, *, timestamp=NOW):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = "v0=" + hmac.new(
        SIGNING, b"v0:" + str(timestamp).encode() + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return body, {"X-Slack-Request-Timestamp": str(timestamp),
                  "X-Slack-Signature": signature}


class _Harness:
    def __init__(self):
        self.current = {}
        self.call_count = {"target": 0, "thread": 0, "principal": 0}
        self.targets = {
            "mmsecretary": CurrentTarget("mmsecretary", "native-secretary-1", "gen-7"),
            "mmmeta": CurrentTarget("mmmeta", "native-meta-1", "gen-2"),
            "engineering": CurrentTarget("engineering", "native-engineering-1", "gen-5"),
        }
        self.router = SlackHermesIngress(
            workspace_id=TEAM, app_id=APP, relay_bot_user_id=BOT,
            allowed_channel_ids=frozenset({ROOM, DOTS, DM}),
            role_handles={"secretary": "mmsecretary", "meta-ceo": "mmmeta",
                          "engineering": "engineering"},
            channel_defaults={ROOM: "mmmeta", DOTS: "mmsecretary", DM: "mmsecretary"},
            principal_for=self._principal,
            thread_binding=self._thread,
            current_target=self._target,
        )

    def _principal(self, team, user):
        self.call_count["principal"] += 1
        return "executive:chris" if team == TEAM and user == CHRIS else None

    def _thread(self, team, channel, thread):
        self.call_count["thread"] += 1
        return self.current.get((team, channel, thread))

    def _target(self, principal, role):
        self.call_count["target"] += 1
        return self.targets.get(role) if principal == "executive:chris" else None

    def bind(self, channel, thread, role):
        target = self.targets[role]
        self.current[(TEAM, channel, thread)] = CurrentThread(
            TEAM, channel, thread, role, target.target_ref, target.session_generation)


class SignedEnvelopeTests(unittest.TestCase):
    def test_valid_signature_reproduces_exact_payload(self):
        payload = envelope()
        body, headers = signed(payload)
        self.assertEqual(verify_signed_event(body, headers, signing_secret=SIGNING, now=NOW), payload)

    def test_wrong_signature_refuses(self):
        body, headers = signed(envelope())
        headers["X-Slack-Signature"] = "v0=" + "0" * 64
        with self.assertRaisesRegex(IngressRefusal, "SIGNATURE_INVALID"):
            verify_signed_event(body, headers, signing_secret=SIGNING, now=NOW)

    def test_missing_expired_and_malformed_signature_refuse(self):
        body, headers = signed(envelope())
        for changed, now, code in (({}, NOW, "SIGNATURE_MISSING"),
                                   (headers, NOW + 301, "SIGNATURE_EXPIRED"),
                                   ({**headers, "X-Slack-Request-Timestamp": "abc"}, NOW, "SIGNATURE_INVALID")):
            with self.subTest(code=code), self.assertRaisesRegex(IngressRefusal, code):
                verify_signed_event(body, changed, signing_secret=SIGNING, now=now)

    def test_large_payload_and_duplicate_keys_refuse(self):
        body, headers = signed(envelope())
        with self.assertRaisesRegex(IngressRefusal, "EVENT_BODY_INVALID"):
            verify_signed_event(b" " * 65537, headers, signing_secret=SIGNING, now=NOW)
        bad = b'{"type":"event_callback","type":"event_callback"}'
        sign = "v0=" + hmac.new(SIGNING, b"v0:" + str(NOW).encode() + b":" + bad,
                                hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(IngressRefusal, "DUPLICATE_JSON_KEY"):
            verify_signed_event(bad, {"X-Slack-Request-Timestamp": str(NOW),
                                      "X-Slack-Signature": sign}, signing_secret=SIGNING, now=NOW)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.h = _Harness()

    def test_explicit_engineering_mention_selects_current_native_target(self):
        item = self.h.router.route_verified(envelope())
        self.assertEqual((item.role, item.action, item.target_ref),
                         ("engineering", "NEW", "native-engineering-1"))
        self.assertEqual((item.thread_ts, item.source_ts), (SOURCE_TS, SOURCE_TS))
        self.assertEqual(item.message, "repair test")
        self.assertEqual(self.h.call_count["target"], 1)

    def test_existing_thread_follows_up_without_remention(self):
        self.h.bind(ROOM, THREAD_TS, "engineering")
        item = self.h.router.route_verified(envelope(kind="message", text="test next change",
                                                    thread_ts=THREAD_TS))
        self.assertEqual((item.action, item.role, item.thread_ts),
                         ("CONTINUE", "engineering", THREAD_TS))

    def test_switch_role_requires_native_handoff_authorization(self):
        self.h.bind(ROOM, THREAD_TS, "engineering")
        item = self.h.router.route_verified(envelope(text=f"<@{BOT}> meta-ceo: review decision",
                                                    thread_ts=THREAD_TS))
        self.assertEqual((item.action, item.role),
                         ("HANDOFF_REQUIRES_AUTHORIZATION", "mmmeta"))
        self.assertEqual(item.target_ref, "native-meta-1")
        self.assertEqual(self.h.current[(TEAM, ROOM, THREAD_TS)].role, "engineering")

    def test_thread_continuation_denied_after_generation_change(self):
        self.h.bind(ROOM, THREAD_TS, "engineering")
        self.h.targets["engineering"] = CurrentTarget("engineering", "native-engineering-1", "gen-8")
        with self.assertRaisesRegex(IngressRefusal, "THREAD_NATIVE_BINDING_CHANGED"):
            self.h.router.route_verified(envelope(kind="message", text="still working?",
                                                  thread_ts=THREAD_TS))

    def test_unchanged_source_ref_across_duplicate_slack_event_types(self):
        a = self.h.router.route_verified(envelope(kind="app_mention"))
        b = self.h.router.route_verified(envelope(kind="message"))
        self.assertEqual(a.source_ref, b.source_ref)

    def test_freeform_unmentioned_message_does_not_start_task(self):
        item = self.h.router.route_verified(envelope(kind="message", text="engineering: run tests"))
        self.assertIsNone(item)
        self.assertEqual(self.h.call_count["target"], 0)

    def test_default_room_and_dm_route_existing_roles(self):
        a = self.h.router.route_verified(envelope(text=f"<@{BOT}> please summarize"))
        b = self.h.router.route_verified(envelope(kind="message", channel=DM,
                                                  text="please summarize", channel_type="im"))
        self.assertEqual((a.role, b.role), ("mmmeta", "mmsecretary"))

    def test_no_host_target_or_unsupported_handle_refuses(self):
        self.h.targets.pop("engineering")
        with self.assertRaisesRegex(IngressRefusal, "ROLE_NOT_CURRENTLY_ENROLLED"):
            self.h.router.route_verified(envelope())
        with self.assertRaisesRegex(IngressRefusal, "UNKNOWN_ROLE_HANDLE"):
            self.h.router.route_verified(envelope(text=f"<@{BOT}> unregistered: do thing"))

    def test_disallowed_user_channel_and_foreign_workspace_refuse(self):
        invalid = [envelope(user="U0FORGNSEND"), envelope(channel="C0FORGNROOM"),
                   {**envelope(), "team_id": "T0FORGNTEAM"}]
        for item in invalid:
            with self.subTest(item=item["event"].get("user")), self.assertRaises(IngressRefusal):
                self.h.router.route_verified(item)

    def test_bot_echo_edit_and_other_events_never_trigger(self):
        for fields in ({"user": BOT}, {"bot_id": "B0BOTSENDER"},
                       {"subtype": "message_changed"}, {"app_id": APP},
                       {"type": "reaction_added"}):
            item = envelope()
            item["event"].update(fields)
            with self.subTest(fields=fields):
                try:
                    result = self.h.router.route_verified(item)
                    self.assertIsNone(result)
                except IngressRefusal as exc:
                    self.assertEqual(exc.code, "UNAUTHORIZED_OR_INVALID_MESSAGE")

    def test_wrong_app_or_invalid_mention_refuses(self):
        changed = {**envelope(), "api_app_id": "A0FOREIGNAP"}
        with self.assertRaisesRegex(IngressRefusal, "WRONG_SLACK_INSTALLATION"):
            self.h.router.route_verified(changed)
        with self.assertRaisesRegex(IngressRefusal, "MENTION_EVENT_MISMATCH"):
            self.h.router.route_verified(envelope(text="engineering: test"))

    def test_suspicious_secret_and_empty_request_refuse(self):
        for text in (f"<@{BOT}> engineering: password=not-for-model",
                     f"<@{BOT}> engineering: "):
            with self.subTest(text=text), self.assertRaises(IngressRefusal):
                self.h.router.route_verified(envelope(text=text))

    def test_bound_thread_cannot_be_spoofed_to_other_channel(self):
        self.h.bind(DOTS, THREAD_TS, "mmsecretary")
        with self.assertRaisesRegex(IngressRefusal, "MENTION_EVENT_MISMATCH"):
            self.h.router.route_verified(envelope(kind="app_mention", text="no mention",
                                                  channel=ROOM, thread_ts=THREAD_TS))
        self.assertIsNone(self.h.router.route_verified(envelope(kind="message", text="continuation",
                                                                channel=ROOM, thread_ts=THREAD_TS)))


if __name__ == "__main__":
    unittest.main()
