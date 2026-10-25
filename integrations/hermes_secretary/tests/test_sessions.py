from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from codex_accounts import choose_account, relaunch_wake_plan
from continuity import continuity_action
from sessions import service_sessions
from tab_sweep import plan_tabs


class SessionRoutine(unittest.TestCase):
    def test_registry_services_the_six_oldest_and_applies_each_rule(self):
        entries = [
            {"id": "running", "status": "running", "tier": "pro", "checked_at": "2026-10-25T01:00", "age_hours": 1},
            {"id": "finished", "status": "finished", "tier": "pro", "checked_at": "2026-10-25T02:00", "age_hours": 1},
            {"id": "stall-new", "status": "stalled", "tier": "pro", "checked_at": "2026-10-25T03:00", "age_hours": 1, "last_recovery_at": None},
            {"id": "stall-hot", "status": "stalled", "tier": "pro", "checked_at": "2026-10-25T04:00", "age_hours": 1, "last_recovery_at": "2026-10-25T08:40"},
            {"id": "age-eh", "status": "aging", "tier": "extra_high", "checked_at": "2026-10-25T05:00", "age_hours": 2},
            {"id": "age-pro", "status": "aging", "tier": "pro", "checked_at": "2026-10-25T06:00", "age_hours": 5},
            {"id": "seventh", "status": "finished", "tier": "pro", "checked_at": "2026-10-25T07:00", "age_hours": 1},
            {"id": "chris", "status": "chris_own", "tier": "pro", "checked_at": "2026-10-24T01:00", "age_hours": 30},
            {"id": "nosteer", "status": "do_not_steer", "tier": "extra_high", "checked_at": "2026-10-24T02:00", "age_hours": 1},
            {"id": "refusal", "status": "refusal", "tier": "pro", "checked_at": "2026-10-24T03:00", "age_hours": 1, "refusal_text": "I can't do that."},
            {"id": "waiting", "status": "stalled", "tier": "pro", "checked_at": "2026-10-24T04:00", "age_hours": 3, "waiting_on": "review"},
        ]
        actions = {item["id"]: item for item in service_sessions(entries, now="2026-10-25T09:00")}
        self.assertEqual(len(actions), 6)
        self.assertNotIn("seventh", actions)
        self.assertEqual(actions["chris"]["action"], "exclude_chris_own")
        self.assertEqual(actions["nosteer"]["action"], "exclude_do_not_steer")
        self.assertEqual(actions["refusal"]["action"], "hold_refusal")
        self.assertEqual(actions["refusal"]["refusal_text"], "I can't do that.")
        self.assertFalse(actions["refusal"]["retry"])
        self.assertEqual(actions["refusal"]["handoff"], "ACTION_NEEDED_RETURN")
        self.assertEqual(actions["waiting"]["action"], "leave_waiting")
        self.assertEqual(actions["running"]["action"], "leave_running")
        self.assertEqual(actions["finished"]["action"], "extract_finished")
        self.assertNotIn("stall-new", actions)

    def test_stall_cooldown_and_aging_thresholds(self):
        rows = service_sessions(
            [
                {"id": "stall-new", "status": "stalled", "tier": "pro", "checked_at": "2026-10-25T03:00", "age_hours": 1},
                {"id": "stall-hot", "status": "stalled", "tier": "pro", "checked_at": "2026-10-25T04:00", "age_hours": 1, "last_recovery_at": "2026-10-25T08:40"},
                {"id": "age-eh", "status": "aging", "tier": "extra_high", "checked_at": "2026-10-25T05:00", "age_hours": 2},
                {"id": "age-pro-under", "status": "aging", "tier": "pro", "checked_at": "2026-10-25T06:00", "age_hours": 5.9},
                {"id": "age-pro", "status": "aging", "tier": "pro", "checked_at": "2026-10-25T06:30", "age_hours": 6},
            ],
            now="2026-10-25T09:00",
        )
        by_id = {item["id"]: item for item in rows}
        self.assertEqual(by_id["stall-new"]["action"], "recover_once")
        self.assertEqual(by_id["stall-hot"]["action"], "hold_stall_cooldown")
        self.assertEqual(by_id["age-eh"]["state"], "stalled_pending")
        self.assertEqual(by_id["age-pro-under"]["action"], "leave_aging")
        self.assertEqual(by_id["age-pro"]["handoff"], "ACTION_NEEDED_RETURN")


class CodexAndContinuity(unittest.TestCase):
    def test_switch_order_skips_chatgpt4_and_401_entries(self):
        accounts = [
            {"name": "ChatGPT4", "remaining_pct": 100, "status": "ok"},
            {"name": "ChatGPT1", "remaining_pct": 4, "status": "ok"},
            {"name": "ChatGPT2", "remaining_pct": 40, "status": "401"},
            {"name": "ChatGPT2 Business", "remaining_pct": 20, "status": "ok"},
            {"name": "ChrisWong6031", "remaining_pct": 50, "status": "ok"},
            {"name": "ChatGPT3", "remaining_pct": 80, "status": "ok"},
        ]
        choice = choose_account(accounts, active="ChatGPT1")
        self.assertEqual(choice["action"], "switch")
        self.assertEqual(choice["target"], "ChatGPT2 Business")
        self.assertTrue(choice["relogin"])
        self.assertTrue(choice["message_chris"])
        holding = choose_account(accounts, active="ChatGPT3")
        self.assertEqual(holding["action"], "hold")
        self.assertFalse(holding["message_chris"])
        empty = choose_account(
            [
                {"name": "ChatGPT4", "remaining_pct": 90, "status": "ok"},
                {"name": "ChatGPT1", "remaining_pct": 1, "status": "401"},
            ],
            active="ChatGPT4",
        )
        self.assertEqual(empty["action"], "all_empty")
        self.assertIsNone(empty["target"])
        self.assertTrue(empty["message_chris"])

    def test_relaunch_does_not_message_running_pro_or_chris(self):
        plan = {item["id"]: item["action"] for item in relaunch_wake_plan([
            {"id": "a", "pinned": True, "tier": "extra_high", "state": "idle"},
            {"id": "b", "parked": True, "tier": "pro", "state": "running"},
            {"id": "c", "pinned": True, "status": "chris_own", "tier": "pro", "state": "idle"},
        ])}
        self.assertEqual(plan["a"], "would_paste_nudge")
        self.assertEqual(plan["b"], "leave_running_pro")
        self.assertEqual(plan["c"], "exclude")

    def test_continuity_states_and_four_hour_drift_dedup(self):
        self.assertEqual(continuity_action("FRESH", last_prompt_at=None, now="2026-10-25T10:00"), "none")
        self.assertEqual(continuity_action("STALE", last_prompt_at=None, now="2026-10-25T10:00"), "nudge_refresh")
        self.assertEqual(continuity_action("DRIFTING", last_prompt_at="2026-10-25T08:00", now="2026-10-25T10:00"), "hold")
        self.assertEqual(continuity_action("DRIFTING", last_prompt_at="2026-10-25T06:00", now="2026-10-25T10:00"), "continuity_prompt")
        self.assertEqual(continuity_action("LOST", last_prompt_at=None, now="2026-10-25T10:00"), "restore_relaunch")

    def test_tab_sweep_keeps_one_chatgpt_tab_and_skips_the_debug_banner(self):
        skipped = plan_tabs({"name": "Y7", "debugging_banner": True, "tabs": [{"index": 1, "url": "https://chatgpt.com/c/1"}]})
        self.assertEqual(skipped["action"], "skip")
        plan = plan_tabs({
            "name": "Y7",
            "debugging_banner": False,
            "tabs": [
                {"index": 1, "url": "https://chatgpt.com/c/1", "title": "Chat"},
                {"index": 2, "url": "https://chatgpt.com/c/2", "title": "Extra"},
                {"index": 3, "url": "https://console.cloud.tencent.com/cam", "title": "Tencent"},
                {"index": 4, "url": "https://auth.openai.com/log-in/password", "title": "Sign in"},
                {"index": 5, "url": "https://news.example.invalid/", "title": "News"},
            ],
        })
        self.assertEqual(plan["method"], "close_other_tabs")
        self.assertEqual(plan["keep"], [1, 3, 4])
        self.assertEqual(plan["close"], [2, 5])
        other = plan_tabs({
            "name": "ModernLuxe",
            "debugging_banner": False,
            "tabs": [{"index": 1, "url": "https://chatgpt.com/", "title": "Chat"}],
        })
        self.assertEqual(other["method"], "sweeptabs.scpt")


if __name__ == "__main__":
    unittest.main()
