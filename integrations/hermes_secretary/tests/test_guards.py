from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from guards import GuardRefusal, StandingRules


FORBIDDEN = (
    ("github_approve", {}, "NEVER_APPROVE"),
    ("github_merge", {}, "NEVER_MERGE"),
    ("self_approve", {}, "NEVER_SELF_APPROVE"),
    ("approval_card", {"tool": "terminal", "choice": "Always allow"}, "APPROVAL_SCOPE"),
    ("approval_card", {"tool": "terminal", "choice": "Allow once"}, "APPROVAL_SCOPE"),
    ("approval_card", {"tool": "terminal", "choice": "Allow other for this conversation"}, "APPROVAL_SCOPE"),
    ("composer_input", {"method": "speed_type"}, "PASTE_ONLY"),
    ("composer_input", {"method": "type"}, "PASTE_ONLY"),
    ("message_chat", {"tier": "pro", "state": "running", "input_method": "paste"}, "RUNNING_PRO"),
    ("message_chat", {"tier": "extra_high", "state": "running", "input_method": "paste"}, "RUNNING_CHAT"),
    ("message_chat", {"tier": "extra_high", "state": "idle", "input_method": "paste", "last_nudge_age_min": 5}, "NUDGE_COOLDOWN"),
    ("message_chat", {"tier": "extra_high", "state": "idle", "input_method": "paste", "waiting_on": "ci"}, "WAITING_EXTERNAL"),
    ("message_chat", {"tier": "pro", "state": "idle", "input_method": "paste", "waiting_on": "review"}, "WAITING_EXTERNAL"),
    ("message_chat", {"status": "chris_own", "tier": "extra_high", "state": "idle", "input_method": "paste"}, "CHRIS_OWN"),
    ("message_chat", {"status": "do_not_steer", "tier": "extra_high", "state": "idle", "input_method": "paste"}, "DO_NOT_STEER"),
    ("retry_refusal", {"chat_id": "chat-1"}, "REFUSAL_VERBATIM"),
    ("replay_refusal", {"chat_id": "chat-1", "prompt": "please try again"}, "REFUSAL_VERBATIM"),
    ("rewrite_refusal", {"chat_id": "chat-1", "text": "a shorter refusal"}, "REFUSAL_VERBATIM"),
    ("fabric_retry", {"run_id": "run-1"}, "FABRIC_ONCE"),
    ("scrape_cookies", {}, "NO_SCRAPE"),
    ("backend_api", {}, "NO_BACKEND_API"),
    ("post_secret", {"text": "xoxb-not-a-real-token"}, "NO_SECRETS"),
    ("send_email", {"to": "chris@example.invalid"}, "DRAFT_ONLY"),
    ("slack_as_chris", {"channel": "COUTSIDE01"}, "DRAFT_ONLY"),
    ("act_during_wait", {}, "CHRIS_WAIT"),
    ("switch_account", {"name": "ChatGPT4", "status": "ok"}, "NEVER_CHATGPT4"),
    ("switch_account", {"name": "ChatGPT2", "status": "401"}, "NEVER_401"),
    ("open_chat_new_tab", {}, "ONE_TAB"),
    ("open_chat_by_url", {"url": "https://chatgpt.com/c/example"}, "ONE_TAB"),
    ("slack_post", {"channel": "C0BSBM78V1N", "text": "ACK"}, "SHADOW_NO_POST"),
    ("comment_review", {"body": "looks good"}, "VERDICT_REQUIRED"),
    ("comment_review", {"body": "VERDICT: APPROVE"}, "NEVER_APPROVE"),
    ("comment_review", {"body": "VERDICT: MERGE"}, "NEVER_MERGE"),
    ("not_a_real_action", {}, "UNKNOWN_ACTION"),
)


class StandingRuleGuards(unittest.TestCase):
    def test_every_forbidden_action_is_refused(self):
        rules = StandingRules()
        seen = set()
        for action, ctx, code in FORBIDDEN:
            seen.add(code)
            with self.subTest(action=action, code=code):
                with self.assertRaises(GuardRefusal) as caught:
                    rules.consider(action, **ctx)
                self.assertEqual(caught.exception.code, code)
        self.assertGreaterEqual(len(seen), 16)

    def test_allowed_paths_stay_inside_the_guards(self):
        rules = StandingRules(shadow_mode=False, voice_rooms=("CONE000001", "CTWO000001"))
        rules.consider("approval_card", tool="terminal", choice="Allow terminal for this conversation")
        rules.consider("composer_input", method="paste")
        rules.consider(
            "message_chat",
            tier="extra_high",
            state="idle",
            input_method="paste",
            last_nudge_age_min=30,
        )
        rules.consider("comment_review", body="VERDICT: COMMENT_ONLY\nNo merge.")
        rules.consider("draft_email", to="chris@example.invalid")
        rules.consider("slack_as_chris", channel="CONE000001")
        rules.consider("switch_account", name="ChatGPT1", status="ok")
        rules.consider(
            "fabric_submit",
            run_id="run-1",
            parent="parent-1",
            root="root-1",
            task_class="mechanical",
            complexity="C0_MECHANICAL",
            cwd="/workspace",
            task_text="Read the file and stop. Do not touch incumbents.",
        )
        rules.consider("fabric_status", run_id="run-1")
        with self.assertRaises(GuardRefusal) as caught:
            rules.consider(
                "fabric_submit",
                run_id="run-1",
                parent="parent-1",
                root="root-1",
                task_class="mechanical",
                complexity="C0_MECHANICAL",
                cwd="/workspace",
                task_text="again",
            )
        self.assertEqual(caught.exception.code, "FABRIC_ONCE")

    def test_incomplete_fabric_packet_does_not_consume_the_run_id(self):
        rules = StandingRules()
        with self.assertRaises(GuardRefusal) as caught:
            rules.consider("fabric_submit", run_id="run-2", task_text="")
        self.assertEqual(caught.exception.code, "PACKET_INCOMPLETE")
        rules.consider(
            "fabric_submit",
            run_id="run-2",
            parent="parent-1",
            root="root-1",
            task_class="mechanical",
            complexity="C0_MECHANICAL",
            cwd="/workspace",
            task_text="one bounded read",
        )
        self.assertEqual(rules.fabric_state("run-2"), "submitted")
        rules.consider("fabric_uncertain", run_id="run-2")
        self.assertEqual(rules.fabric_state("run-2"), "uncertain")
        with self.assertRaises(GuardRefusal):
            rules.consider(
                "fabric_submit",
                run_id="run-2",
                parent="parent-1",
                root="root-1",
                task_class="mechanical",
                complexity="C0_MECHANICAL",
                cwd="/workspace",
                task_text="retry after uncertainty",
            )

    def test_refusal_text_stays_verbatim_and_is_not_replayed(self):
        rules = StandingRules()
        original = "I can't help with that exact request."
        rules.consider("record_refusal", chat_id="chat-9", text=original)
        rules.consider("record_refusal", chat_id="chat-9", text=original)
        with self.assertRaises(GuardRefusal):
            rules.consider("record_refusal", chat_id="chat-9", text="A shorter version.")
        self.assertEqual(rules.refusal_text("chat-9"), original)
        with self.assertRaises(GuardRefusal) as caught:
            rules.consider("replay_refusal", chat_id="chat-9", prompt=original)
        self.assertEqual(caught.exception.code, "REFUSAL_VERBATIM")
        with self.assertRaises(GuardRefusal):
            rules.consider("message_chat", chat_id="chat-9", tier="extra_high", state="idle", input_method="paste")

    def test_chris_wait_holds_until_chris_releases_it(self):
        rules = StandingRules()
        rules.consider("chris_wait")
        with self.assertRaises(GuardRefusal) as caught:
            rules.consider("composer_input", method="paste")
        self.assertEqual(caught.exception.code, "CHRIS_WAIT")
        with self.assertRaises(GuardRefusal):
            rules.consider("release_wait", authority="secretary")
        rules.consider("release_wait", authority="chris")
        rules.consider("composer_input", method="paste")

    def test_one_configured_voice_room_fails_closed(self):
        rules = StandingRules(shadow_mode=False, voice_rooms=("CONE000001",))
        with self.assertRaises(GuardRefusal) as caught:
            rules.consider("slack_as_chris", channel="CONE000001")
        self.assertEqual(caught.exception.code, "DRAFT_ONLY")

    def test_shadow_mode_refuses_a_chris_voice_send_inside_the_two_rooms(self):
        rules = StandingRules(shadow_mode=True, voice_rooms=("CONE000001", "CTWO000001"))
        with self.assertRaises(GuardRefusal) as caught:
            rules.consider("slack_as_chris", channel="CTWO000001")
        self.assertEqual(caught.exception.code, "SHADOW_NO_POST")


if __name__ == "__main__":
    unittest.main()
