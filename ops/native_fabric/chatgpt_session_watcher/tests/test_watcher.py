"""Watcher tests. Fixtures are the attached registry sample and synthetic tails.

No browser, no network, no MiniMax credential on a process list.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from census import reconcile  # noqa: E402
from context import ReadOnlyGitHub, SlackReader, context_for_tail  # noqa: E402
from decision import decide  # noqa: E402
from loop import run_cycle  # noqa: E402
from minimax_client import MinimaxPoolClient, MinimaxUnavailable  # noqa: E402
from playbook import KNOWLEDGE, LESSON_SEED, load_playbook_text  # noqa: E402
from policy import (  # noqa: E402
    PT,
    PolicyRefusal,
    account_for,
    assert_safe_argv,
    human_is_active,
    parse_stamp,
    reply_ok,
    stamp_sort_key,
)
from prompts import accept_model_draft, render  # noqa: E402
from reflect import reflect  # noqa: E402
from states import classify  # noqa: E402
from stores import LedgerStore, MetricsStore, RegistryStore, WatcherStores  # noqa: E402
from tools import BrowserTools  # noqa: E402
from decision import Decision  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=PT)


def _obs(**kwargs):
    base = {
        "chat_id": "6adc4fdd-ac1c-83ea-b2c6-711fbc741e89",
        "title": "Resume Forex Project",
        "project": "MastermindX",
        "mode": "Pro",
        "button": "Idle",
        "tail": "Stopped after the checkpoint.",
        "flags": [],
    }
    base.update(kwargs)
    return base


class RegistryAndLedger(unittest.TestCase):
    def test_sample_registry_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(FIXTURES.joinpath("session_registry_sample.json").read_text(encoding="utf-8"), encoding="utf-8")
            store = RegistryStore(path)
            self.assertEqual(len(store.sessions), 4)
            ids = {row["chat_id"] for row in store.sessions}
            self.assertIn("6adc4fdd-ac1c-83ea-b2c6-711fbc741e89", ids)
            self.assertEqual(store.sessions[0]["profile"], "ModernLuxe")
            self.assertIsNone(store.sessions[0]["replaced_by"])
            store.upsert_seen({"chat_id": "new-chat", "title": "New census row", "profile": "Y7"})
            store.save()
            again = RegistryStore(path)
            self.assertEqual(len(again.sessions), 5)
            self.assertEqual(again.get("new-chat")["status"], "seen_sidebar")

    def test_owed_returns_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "owed.json"
            path.write_text(FIXTURES.joinpath("owed_returns_sample.json").read_text(encoding="utf-8"), encoding="utf-8")
            ledger = LedgerStore(path)
            self.assertGreaterEqual(len(ledger.entries), 2)
            self.assertEqual(ledger.open_returns(), [])
            self.assertEqual(ledger.entries[0]["slack_channel"], "C0CBC6AEAQZ")
            ledger.upsert({"task": "open-1", "state": "owed", "account": "Chris-Dot", "chat_id": "abc"})
            self.assertEqual(len(ledger.open_returns()), 1)

    def test_stamp_sort_uses_one_format(self):
        self.assertLess(stamp_sort_key("2026-10-24T08:46"), stamp_sort_key("2026-10-24 14:33"))
        self.assertIsNotNone(parse_stamp("2026-10-24T01:54:42-07:00"))


class Classification(unittest.TestCase):
    def test_synthetic_tails(self):
        cases = {
            "running": _obs(button="Stop", tail="Preparing preview"),
            "idle": _obs(button="Idle", tail="The turn finished."),
            "permission_card": _obs(flags=["CARD"], card_tool="Slack Send message", tail="Allow?"),
            "connection_interrupted": _obs(button="Stop", tail="Connection interrupted. Waiting for the complete answer"),
            "thinking_failed": _obs(tail="Thinking failed"),
            "error_in_message_stream": _obs(tail="Error in message stream"),
            "message_delivery_timed_out": _obs(tail="Message delivery timed out"),
            "could_not_load": _obs(tail="Could not load this ChatGPT conversation"),
            "maximum_length": _obs(tail="You've reached the maximum length for this conversation"),
            "hit_limit": _obs(tail="You've hit your limit. Please try again later."),
            "page_unresponsive": _obs(window_title="Y7: Page Unresponsive"),
            "crashed": _obs(window_title="Resume Forex Project - Crashed - Google Chrome - Chris"),
            "inactive_tab": _obs(window_title="ChatGPT - Inactive tab - 344 MB freed up"),
            "free_plan": _obs(account_badge="C4 Free", tail="You've hit your limit."),
            "out_of_credits": _obs(tail="Workspace out of credits. Turn on auto-reload"),
        }
        for symptom, obs in cases.items():
            self.assertEqual(classify(obs), symptom, symptom)


class Decisions(unittest.TestCase):
    def setUp(self):
        self.account = account_for("ModernLuxe")
        self.metrics = MetricsStore(Path(tempfile.mkdtemp()) / "metrics.json")

    def _decide(self, obs, entry=None, **kwargs):
        defaults = dict(
            now=NOW, active=3, pro_count=2, throttled=False, recovery_allowed=True,
            archive_ids=set(), metrics=self.metrics, limit_retry_allowed=False,
        )
        defaults.update(kwargs)
        return decide(obs, entry, self.account, **defaults)

    def test_running_pro_is_not_sent(self):
        choice = self._decide(_obs(button="Stop", mode="Pro"))
        self.assertEqual(choice.action, "hold")
        self.assertEqual(choice.tactic, "never_send_running_pro")
        self.assertIsNone(choice.reply_kind)

    def test_extra_high_idle_reprompts_immediately(self):
        choice = self._decide(_obs(mode="Extra High", button="Idle"))
        self.assertEqual(choice.action, "paste_send")
        self.assertEqual(choice.tactic, "eh_reprompt")

    def test_pro_cooloff(self):
        entry = {"mode": "Pro", "last_nudge_pt": (NOW - timedelta(minutes=10)).isoformat()}
        choice = self._decide(_obs(mode="Pro", button="Idle"), entry)
        self.assertEqual(choice.tactic, "pro_cooloff")
        entry["last_nudge_pt"] = (NOW - timedelta(minutes=45)).isoformat()
        later = self._decide(_obs(mode="Pro", button="Idle"), entry)
        self.assertEqual(later.action, "paste_send")
        self.assertEqual(later.mode_target, "Pro")

    def test_github_write_needs_details_then_allow_once(self):
        hidden = self._decide(_obs(flags=["CARD"], card_tool="GitHub Create Pull Request"))
        self.assertEqual(hidden.card_choice, "see_details")
        shown = self._decide(_obs(
            flags=["CARD"], card_tool="GitHub Create Pull Request",
            see_details="GitHub Create Pull Request",
        ))
        self.assertEqual(shown.card_choice, "allow_once")
        mismatch = self._decide(_obs(
            flags=["CARD"], card_tool="GitHub Create Pull Request",
            see_details="Slack Send message",
        ))
        self.assertEqual(mismatch.action, "hold")

    def test_other_cards_allow_for_conversation_and_merge_is_denied(self):
        slack = self._decide(_obs(flags=["CARD"], card_tool="Slack Send message"))
        self.assertEqual(slack.card_choice, "allow_conversation")
        merge = self._decide(_obs(flags=["CARD"], card_tool="GitHub Merge Pull Request"))
        self.assertEqual(merge.card_choice, "deny")
        self.assertNotIn("escape", (merge.card_choice or "").casefold())

    def test_holds(self):
        flovia = self._decide(_obs(title="Flovia design"), {"title": "Flovia design"})
        self.assertEqual(flovia.tactic, "never_touch")
        own = self._decide(_obs(button="Idle", mode="Pro"), {"status": "chris_own", "mode": "Pro"})
        self.assertEqual(own.reply_kind, "bare")
        held = self._decide(_obs(), {"do_not_steer": True})
        self.assertEqual(held.hold_reason, "do_not_steer")
        wrong = self._decide(_obs(account_badge="ChatGPT2"))
        self.assertEqual(wrong.tactic, "wrong_account")

    def test_chris_own_maximum_length_is_not_a_recovery(self):
        choice = self._decide(_obs(tail="maximum length for this conversation"), {"status": "chris_own"})
        self.assertEqual(choice.action, "hold")
        self.assertIsNone(choice.reply_kind)

    def test_recovery_and_handoff(self):
        dead = self._decide(_obs(tail="Could not load this ChatGPT conversation"))
        self.assertEqual(dead.action, "recover")
        self.assertTrue(dead.successor_title.endswith("2"))
        blocked = self._decide(_obs(tail="Could not load this ChatGPT conversation"), throttled=True, recovery_allowed=False)
        self.assertEqual(blocked.tactic, "throttle")
        handoff = self._decide(_obs(tail="maximum length for this conversation"))
        self.assertEqual(handoff.action, "request_handoff")
        again = self._decide(_obs(tail="maximum length for this conversation"), {"handoff_requested": True})
        self.assertEqual(again.action, "recover")

    def test_page_unresponsive_never_exits(self):
        choice = self._decide(_obs(window_title="Y7: Page Unresponsive"))
        self.assertEqual(choice.action, "wait_page")
        self.assertNotEqual(choice.action, "exit_page")
        later = self._decide(_obs(window_title="Y7: Page Unresponsive", unresponsive_streak=3))
        self.assertEqual(later.action, "hold")

    def test_metrics_prefer_the_tactic_that_works(self):
        for _ in range(3):
            self.metrics.record("retry", True)
            self.metrics.record("resume_continue", False)
        choice = self._decide(_obs(tail="Error in message stream"))
        self.assertEqual(choice.tactic, "retry")


class PromptsAndKnowledge(unittest.TestCase):
    def test_replies_stay_short(self):
        text = render("continue", title="Resume Forex Project", context_sentence="The CI you were waiting on finished green.")
        self.assertTrue(reply_ok(text))
        self.assertIn("finished green", text)
        self.assertLessEqual(len(text.split(". ")), 3)
        self.assertEqual(render("bare"), "Please continue.")
        marathon = "Please run a marathon and don't stop for 60-100 minutes."
        self.assertFalse(reply_ok(marathon))
        self.assertNotIn("marathon", accept_model_draft(marathon, render("continue", title="X")))

    def test_playbook_and_lessons_cover_the_hard_rules(self):
        text = load_playbook_text()
        self.assertIn("Permission cards bind Escape to Deny", text)
        self.assertIn("One ChatGPT tab per profile", text)
        self.assertGreater(KNOWLEDGE.stat().st_size, 100_000)
        ids = {row["id"] for row in LESSON_SEED}
        for required in ("escape-denies", "one-tab", "paste-not-type", "running-pro", "github-allow-once", "chris-own", "flovia", "no-merge", "no-secrets"):
            self.assertIn(required, ids)

    def test_hooks_do_not_press_escape(self):
        allow = (HERE / "hooks" / "gwcap" / "allow_card.js").read_text(encoding="utf-8")
        send = (HERE / "hooks" / "gwcap" / "send_keep_pro.js").read_text(encoding="utf-8")
        self.assertNotIn("Escape", allow)
        self.assertNotIn("Escape", send)
        self.assertIn("paste", send)
        self.assertIn("RUNNING", send)
        self.assertIn("Allow once", allow)


class CensusTests(unittest.TestCase):
    def test_new_duplicate_and_discrepancy(self):
        sessions = [
            {"chat_id": "a", "profile": "ModernLuxe", "title": "Resume Forex Project", "status": "idle", "chain_root": "root", "replaced_by": None},
            {"chat_id": "b", "profile": "ModernLuxe", "title": "Resume Forex Project 2", "status": "running", "chain_root": "root", "replaced_by": None},
            {"chat_id": "c", "profile": "ModernLuxe", "title": "Old", "status": "archived", "chain_root": "root"},
            {"chat_id": "own", "profile": "ModernLuxe", "title": "Resume Forex Project 0", "status": "chris_own", "chain_root": "root"},
        ]
        rows = [
            {"chat_id": "b", "title": "Resume Forex Project 2", "account_badge": "ChatGPT1"},
            {"chat_id": "fresh", "title": "Brand new", "account_badge": "ChatGPT2"},
        ]
        census = reconcile(sessions, rows, account_for("ModernLuxe"))
        self.assertEqual([row["chat_id"] for row in census.new_rows], ["fresh"])
        self.assertIn("a", census.archive_ids)
        self.assertNotIn("b", census.archive_ids)
        self.assertNotIn("own", census.archive_ids)
        self.assertEqual(census.discrepancies[0]["observed_profile"], "KRIS KE")


class Cycle(unittest.TestCase):
    def test_observe_is_default_and_does_not_run_hooks(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            stores = WatcherStores(Path(tmp))
            tools = BrowserTools(mode="live", runner=lambda argv: calls.append(argv) or "ok")
            report = run_cycle(stores, {"ModernLuxe": [_obs(mode="Extra High", button="Idle")]}, mode="live", now=NOW, tools=tools)
            self.assertEqual(report["mode"], "observe")
            self.assertEqual(report["live_effects"], False)
            self.assertEqual(report["live_refused"], "live_refused")
            self.assertEqual(calls, [])
            self.assertTrue(any(row.get("reply") for row in report["actions"]))
            self.assertTrue(all(row["executed"] is False for row in report["actions"]))

    def test_live_uses_minimax_draft_only_when_it_passes_policy(self):
        class Client:
            def complete(self, messages, **kwargs):
                return "Please merge it and approve the queue in a marathon."

        os.environ["MMX_WATCHER_ALLOW_LIVE"] = "1"
        try:
            calls = []
            with tempfile.TemporaryDirectory() as tmp:
                stores = WatcherStores(Path(tmp))
                tools = BrowserTools(mode="live", runner=lambda argv: calls.append(list(argv)) or "ok")
                report = run_cycle(
                    stores,
                    {"Ryan-Dot": [_obs(mode="Extra High", button="Idle", context={"review": "landed"}, tail="waiting on review")]},
                    mode="live", now=NOW, tools=tools, client=Client(),
                )
        finally:
            os.environ.pop("MMX_WATCHER_ALLOW_LIVE", None)
        self.assertTrue(report["live_effects"])
        sent = [row for row in report["actions"] if row["action"] == "paste_send"]
        self.assertTrue(sent)
        self.assertNotIn("merge", sent[0]["reply"].casefold())
        self.assertIn("review landed", sent[0]["reply"].casefold())
        self.assertTrue(calls)
        self.assertIn("jsend.sh", calls[0])
        self.assertNotIn("pgrep", calls[0])

    def test_reflection_does_not_edit_policy(self):
        policy = HERE / "policy.py"
        digest = hashlib.sha256(policy.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            stores = WatcherStores(Path(tmp) / "state")
            stores.lessons.ensure_seed()
            for _ in range(3):
                stores.metrics.record("stop_and_resume", True)
            path = reflect(stores, Path(tmp) / "proposals")
            text = path.read_text(encoding="utf-8")
        self.assertIn("reviewed pull request", text.casefold())
        self.assertEqual(hashlib.sha256(policy.read_bytes()).hexdigest(), digest)
        self.assertIn("Prefer this tactic", text)


class ToolsAndClient(unittest.TestCase):
    def test_process_listings_and_urls_are_refused(self):
        for argv in (["pgrep", "-f", "chrome"], ["pgrep", "-a", "x"], ["ps", "aux"], ["open", "https://chatgpt.com/c/abc"]):
            with self.assertRaises(PolicyRefusal):
                assert_safe_argv(argv)

    def test_title_and_running_pro_gate(self):
        tools = BrowserTools(mode="observe")
        running = Decision(profile="ModernLuxe", action="paste_send", tactic="pro_continue", symptom="idle",
                           chat_id="abc", title="Resume Forex Project", mode_target="Pro")
        with self.assertRaises(Exception) as caught:
            tools.plan(running, observed_title="Resume Forex Project", observed_id="abc", button="Stop")
        self.assertEqual(getattr(caught.exception, "code", ""), "running_pro")
        mismatch = tools.execute(running, observed_title="Other chat", observed_id="abc", button="Idle")
        self.assertEqual(mismatch["error"], "title_mismatch")
        stopped = Decision(profile="ModernLuxe", action="stop_and_resume", tactic="stop_and_resume", symptom="connection_interrupted",
                           chat_id="abc", title="Resume Forex Project", mode_target="Pro")
        plan = tools.plan(stopped, observed_title="Resume Forex Project", observed_id="abc", button="Stop")
        self.assertEqual(plan, [["hook", "stop.js", "ModernLuxe", "Resume Forex Project"]])
        self.assertFalse(any("send_keep_pro.js" in " ".join(argv) or "jsend.sh" in argv for argv in plan))

    def test_foreground_click_waits_for_a_real_idle_gap(self):
        self.assertFalse(human_is_active(1, 1))
        self.assertTrue(human_is_active(1, 30))
        tools = BrowserTools(mode="live", idle_seconds=lambda: 1, seconds_since_own_input=lambda: 30, runner=lambda argv: "clicked")
        decision = Decision(profile="Y7", action="wait_page", tactic="wait_not_exit", symptom="page_unresponsive", title="Y7: Page Unresponsive")
        result = tools.execute(decision, observed_title="Y7: Page Unresponsive")
        self.assertEqual(result["error"], "user_active")

    def test_minimax_pool_never_leaks_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"api_key": "sk-SENTINELKEY1234567890"}), encoding="utf-8")

            def boom(url, headers, body):
                raise RuntimeError(headers["Authorization"])

            client = MinimaxPoolClient(transport=boom, config_path=path)
            with self.assertRaises(MinimaxUnavailable) as caught:
                client.complete([{"role": "user", "content": "hello"}])
            self.assertNotIn("SENTINEL", str(caught.exception))
            self.assertIsNone(caught.exception.__cause__)

            def ok(url, headers, body):
                self.assertEqual(body["model"], "MiniMax-M2.7")
                self.assertEqual(client.pool, "minimax")
                self.assertNotIn("api_key", body)
                return {"choices": [{"message": {"content": "Please continue with the project. sk-SENTINELKEY1234567890"}}]}

            client = MinimaxPoolClient(transport=ok, config_path=path)
            text = client.complete([{"role": "user", "content": "hello"}])
            self.assertNotIn("SENTINEL", text)

    def test_github_and_slack_stay_read_only(self):
        def runner(argv):
            raise AssertionError(argv)

        github = ReadOnlyGitHub(runner)
        with self.assertRaises(Exception):
            github._run(["pr", "merge", "1", "--repo", "org/name"])
        with self.assertRaises(Exception):
            github._run(["pr", "review", "1", "--approve"])
        slack = SlackReader(reader=lambda channel: ["review landed"] if channel == "C0CBC6AEAQZ" else [])
        ctx = context_for_tail("waiting on review", slack=slack)
        self.assertEqual(ctx.review, "landed")
        self.assertFalse(hasattr(slack, "send"))


class Spawn(unittest.TestCase):
    def test_spawn_status_and_replay(self):
        cli = HERE / "cli.py"
        with tempfile.TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "obs.json"
            fixtures.write_text(json.dumps({"ModernLuxe": [_obs(button="Stop", mode="Pro")]}), encoding="utf-8")
            base = [sys.executable, str(cli), "--state-dir", tmp]
            # argparse is on the subcommand, so flags follow the command.
            first = subprocess.run(
                [sys.executable, str(cli), "spawn", "--state-dir", tmp, "--run-id", "watch-1",
                 "--root", "root-1", "--parent", "parent-1", "--fixtures", str(fixtures), "--stdin"],
                input=b"", capture_output=True, check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr.decode())
            report = json.loads(first.stdout.decode())
            self.assertEqual(report["mode"], "observe")
            self.assertEqual(report["live_effects"], False)
            status = subprocess.run(
                [sys.executable, str(cli), "status", "--state-dir", tmp, "--run-id", "watch-1"],
                capture_output=True, check=False,
            )
            body = json.loads(status.stdout.decode())
            self.assertEqual(body["state"], "TERMINAL")
            self.assertEqual(body["worker_kind"], "chatgpt_web_session_watcher")
            second = subprocess.run(
                [sys.executable, str(cli), "spawn", "--state-dir", tmp, "--run-id", "watch-1",
                 "--root", "root-1", "--parent", "parent-1", "--stdin"],
                input=b"", capture_output=True, check=False,
            )
            self.assertEqual(second.returncode, 2)
            self.assertEqual(json.loads(second.stdout.decode())["state"], "RUN_EXISTS")
            self.assertFalse(base and False)


if __name__ == "__main__":
    unittest.main()
