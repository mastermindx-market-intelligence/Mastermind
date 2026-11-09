"""Source qualification for the existing M2 Slack gateway.

No Slack token, Socket Mode connection, Hermes process, model call or host
mutation is required. The user-visible stdout and native stderr receipt remain
separate; fresh session IDs are necessary for per-thread continuation.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[2] / "hermes_runtime" / "slack_gateway.py"
SPEC = importlib.util.spec_from_file_location("mmx_slack_gateway_candidate", PATH)
assert SPEC and SPEC.loader
gateway = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gateway
SPEC.loader.exec_module(gateway)


class HermesSessionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conf_patcher = patch.object(gateway, "CONF_DIR", Path(self.tmp.name))
        self.conf_patcher.start()
        self.addCleanup(self.conf_patcher.stop)

    def fake_subprocess(self, *, output, diagnostics="", returncode=0):
        def invoke(cmd, **kwargs):
            self.assertEqual(cmd[:4], ["hermes", "--profile", "secretary", "chat"])
            self.assertIn("--query-file", cmd)
            self.assertIn("--oneshot", cmd)
            self.assertIn("-Q", cmd)
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(Path(cmd[cmd.index("--query-file")+1]).is_file())
            self.assertEqual(
                Path(cmd[cmd.index("--query-file")+1]).read_text(),
                "Answer my question",
            )
            return subprocess.CompletedProcess(cmd, returncode, output, diagnostics)
        return invoke

    def test_quiet_mode_session_from_stderr_is_saved(self):
        session = "abcd1234-1234-1234-1234-123456789012"
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="My response", diagnostics="\nsession_id: " + session + "\n"
        )):
            ok, result, sid = gateway.dispatch("secretary", "Answer my question", None, 10)
        self.assertEqual((ok, result, sid), (True, "My response", session))
        self.assertEqual(list(Path(self.tmp.name).glob(".prompt-*")), [])

    def test_distinct_role_specific_native_profile_launches(self):
        command_lines = []
        for profile in ("engineering", "secretary", "meta-ceo-uncensored"):
            def invoke(cmd, **kwargs):
                command_lines.append(list(cmd))
                self.assertEqual(cmd[:4], ["hermes", "--profile", profile, "chat"])
                self.assertEqual(kwargs["env"].get("HERMES_PROFILE"), profile)
                self.assertNotIn("HERMES_HOME", kwargs["env"])
                return subprocess.CompletedProcess(cmd, 0, "answer", "session_id: native-session-12345678\n")
            with patch.object(gateway.subprocess, "run", side_effect=invoke):
                self.assertEqual(gateway.dispatch(profile, "separate prompt", None, 10)[0], True)
        self.assertEqual(len({x[2] for x in command_lines}), 3)
        self.assertEqual(gateway.DEFAULT_CONF["agents"]["meta-ceo"]["profile"], "meta-ceo-uncensored")

    def test_resumed_id_forwarded_to_original_cli(self):
        sid = "abcd1234-1234-1234-1234-123456789012"
        def invoke(cmd, **kwargs):
            self.assertEqual(cmd[cmd.index("--resume")+1], sid)
            self.assertEqual(cmd[cmd.index("-m")+1], "code-flash")
            return subprocess.CompletedProcess(cmd, 0, "Continued", "session_id: " + sid + "\n")
        with patch.object(gateway.subprocess, "run", side_effect=invoke):
            self.assertEqual(gateway.dispatch("secretary", "Answer my question", sid, 10, "code-flash"),
                             (True, "Continued", sid))

    def test_stdout_receipt_compatibility_without_user_visible_leak(self):
        sid = "abcd1234-1234-1234-1234-123456789012"
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="Text\nsession_id: " + sid + "\n",
        )):
            self.assertEqual(gateway.dispatch("secretary", "Answer my question", None, 10),
                             (True, "Text", sid))

    def test_nonzero_exit_never_claims_success_with_partial_stdout(self):
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="partial text", diagnostics="process crashed", returncode=42,
        )):
            result = gateway.dispatch("secretary", "Answer my question", None, 10)
        self.assertEqual(result, (False, "process crashed", None))

    def test_timeout_never_leaks_or_keeps_prompt_file(self):
        with patch.object(gateway.subprocess, "run", side_effect=subprocess.TimeoutExpired(
            "hermes", timeout=10
        )):
            result = gateway.dispatch("secretary", "Answer my question", None, 10)
        self.assertEqual(result[0], False)
        self.assertIsNone(result[2])
        self.assertEqual(list(Path(self.tmp.name).glob(".prompt-*")), [])

    def test_unrecognized_session_metadata_does_not_enter_native_resume(self):
        with patch.object(gateway.subprocess, "run", side_effect=self.fake_subprocess(
            output="Ordinary text", diagnostics="session_id: !unexpected\n"
        )):
            self.assertEqual(gateway.dispatch("secretary", "Answer my question", None, 10),
                             (True, "Ordinary text", None))


class InstalledGatewayRoutingTests(unittest.TestCase):
    def setUp(self):
        self.conf = gateway.DEFAULT_CONF

    def test_explicit_unbound_role_alias(self):
        self.assertEqual(
            gateway.route(self.conf, text="engineering: Please inspect this",
                          channel="C0CBC6AEAQZ", user="U0BRET6191C", is_dm=False),
            ("engineering", "alias:engineering"),
        )

    def test_bound_thread_prioritizes_existing_role_even_if_alias_changes(self):
        # A cross-role migration cannot silently steal an existing thread.
        self.assertEqual(
            gateway.route(self.conf, text="engineering: one more question",
                          channel="C0CBC6AEAQZ", user="U0BRET6191C",
                          is_dm=False, binding="secretary"),
            ("secretary", "thread-binding"),
        )

    def test_nine_routable_profiles_with_one_app(self):
        self.assertEqual(len(gateway.routable(self.conf)), 9)
        self.assertEqual(len(self.conf["apps"]), 1)



class InboundAdmissionSafetyTests(unittest.TestCase):
    """Check the original Socket Mode owner without opening a socket or token."""

    def setUp(self):
        import copy
        import threading
        self.conf = copy.deepcopy(gateway.DEFAULT_CONF)
        self.conf["allowed_users"] = ["U0BRET6191C"]
        self.conf["max_dispatches_per_minute"] = 1
        self.fleet = gateway.Fleet.__new__(gateway.Fleet)
        self.fleet.conf = self.conf
        self.fleet.state = {"recent": {}, "bindings": {}, "outbound": {}}
        self.fleet.lock = threading.Lock()
        self.fleet.bot_user_id = "U0BT71H4FQE"
        self.fleet.our_bot_users = {"U0BT71H4FQE"}
        self.logging = patch.object(gateway, "log", return_value=None)
        self.logging.start()
        self.addCleanup(self.logging.stop)

    def event(self, *, text, user="U0BRET6191C", ts="1794180011.111111",
              thread_ts=None):
        out = {"type": "message", "channel_type": "channel",
               "channel": "C0CBC6AEAQZ", "user": user, "ts": ts, "text": text}
        if thread_ts:
            out["thread_ts"] = thread_ts
        return out

    def test_unrelated_human_mention_is_inert_and_does_not_spend_limit(self):
        other = self.event(text="<@U0UNRELATE9> hello unrelated person")
        self.assertIsNone(self.fleet.admit(other, []))
        self.assertEqual(self.fleet.state["recent"], {})
        addressed = self.event(text="<@U0BT71H4FQE> engineering: help")
        self.assertEqual(self.fleet.admit(addressed, []), ("engineering", "alias:engineering"))

    def test_nonallowlisted_user_cannot_exhaust_budget(self):
        attack = self.event(text="<@U0BT71H4FQE> delivery: do this", user="U0OUTSIDER9")
        self.assertIsNone(self.fleet.admit(attack, []))
        self.assertEqual(self.fleet.state["recent"], {})
        self.assertEqual(
            self.fleet.admit(self.event(text="<@U0BT71H4FQE> delivery: do this"), []),
            ("delivery", "alias:delivery"))

    def test_bound_thread_continues_without_mention(self):
        self.fleet.state["bindings"]["C0CBC6AEAQZ:1794180000.123456"] = "secretary"
        self.assertEqual(self.fleet.admit(self.event(text="follow-up", thread_ts="1794180000.123456"), []),
                         ("secretary", "thread-binding"))

    def test_gateway_own_post_is_never_dispatched(self):
        self.assertIsNone(
            self.fleet.admit(self.event(text="<@U0BT71H4FQE> hello", user="U0BT71H4FQE"), []))
        self.assertEqual(self.fleet.state["recent"], {})



class SecurePromptFileTests(unittest.TestCase):
    def test_same_millisecond_multi_agent_prompts_never_collide_or_expose_content(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(gateway, "CONF_DIR", Path(root)):
                seen = []
                def invoke(cmd, **kwargs):
                    qfile = Path(cmd[cmd.index("--query-file") + 1])
                    seen.append(qfile)
                    self.assertEqual(qfile.stat().st_mode & 0o777, 0o600)
                    self.assertEqual(qfile.read_text(encoding="utf-8"),
                                     ("secretary private prompt" if len(seen) == 1
                                      else "engineering private prompt"))
                    return subprocess.CompletedProcess(cmd, 0, "answer", "")
                with patch.object(gateway.time, "time", return_value=1794200000.123), \
                     patch.object(gateway.subprocess, "run", side_effect=invoke):
                    self.assertEqual(
                        gateway.dispatch("secretary", "secretary private prompt", None, 5)[0], True)
                    self.assertEqual(
                        gateway.dispatch("engineering", "engineering private prompt", None, 5)[0], True)
                self.assertEqual(len(set(seen)), 2)
                self.assertFalse(list(Path(root).glob(".prompt-*")))


class ExactSlackEventDedupTests(unittest.TestCase):
    def test_dual_slack_delivery_is_one_dispatch_and_one_capacity_hit(self):
        import copy
        import threading
        config = copy.deepcopy(gateway.DEFAULT_CONF)
        config["allowed_users"] = ["U0BRET6191C"]
        config["max_dispatches_per_minute"] = 1
        fleet = gateway.Fleet.__new__(gateway.Fleet)
        fleet.conf = config
        fleet.state = {"seen": {}, "recent": {}, "bindings": {}, "outbound": {}}
        fleet.lock = threading.Lock()
        fleet.bot_user_id = "U0BT71H4FQE"
        fleet.our_bot_users = {"U0BT71H4FQE"}
        sent = []
        fleet.work = lambda *args: sent.append(args)

        class InlineThread:
            def __init__(self, *, target, args, daemon):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)

        event = {
            "type": "message", "channel_type": "channel",
            "channel": "C0CBC6AEAQZ", "ts": "1794180011.111111",
            "user": "U0BRET6191C",
            "text": "<@U0BT71H4FQE> engineering: check",
        }
        payload = lambda e: {"event": e, "authorizations": []}
        with patch.object(gateway, "save_state", return_value=None), \
             patch.object(gateway, "log", return_value=None), \
             patch.object(gateway.threading, "Thread", InlineThread):
            # An app_mention and a message.channels notification are the same
            # logical Slack message, even though Slack delivers two envelopes.
            fleet.handle(payload(event))
            fleet.handle(payload({**event, "type": "app_mention"}))
            self.assertEqual(len(sent), 1)
            self.assertEqual(len(fleet.state["seen"]), 1)
            self.assertEqual(len(fleet.state["recent"][event["channel"]]), 1)

            # An independently addressed message is rate-limited at one/min.
            fleet.handle(payload({**event, "ts": "1794180012.111111"}))
            self.assertEqual(len(sent), 1)

            # Once the existing window expires, new legitimate work is free.
            advanced = gateway.time.time() + 61
            with patch.object(gateway.time, "time", return_value=advanced):
                fleet.handle(payload({**event, "ts": "1794180013.111111"}))
            self.assertEqual(len(sent), 2)
            self.assertEqual(len(fleet.state["recent"][event["channel"]]), 1)


class PerThreadTurnSerializationTests(unittest.TestCase):
    """No two native replies to the same thread may overlap."""

    def setUp(self):
        import threading
        self.fleet = gateway.Fleet.__new__(gateway.Fleet)
        self.fleet.lock = threading.Lock()
        self.fleet._turn_gates = {}

    def test_same_thread_waits_then_releases_without_leaking_gates(self):
        import threading
        import time
        guard = threading.Lock()
        entered = threading.Event()
        release = threading.Event()
        active = [0]
        peak = [0]
        completed = []
        errors = []

        def one(_fleet, event, agent, reason, authorizations):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                completed.append(("enter", event["ts"]))
            if not entered.is_set():
                entered.set()
                if not release.wait(3):
                    errors.append("timed_out")
            with guard:
                active[0] -= 1
                completed.append(("exit", event["ts"]))

        self.fleet._work_serialized = one.__get__(self.fleet, gateway.Fleet)
        a = {"channel": "C0CBC6AEAQZ", "ts": "1794180000.123456"}
        b = {"channel": "C0CBC6AEAQZ", "thread_ts": "1794180000.123456",
             "ts": "1794180001.123456"}
        first = threading.Thread(target=self.fleet.work, args=(a, "secretary", "test", []))
        second = threading.Thread(target=self.fleet.work, args=(b, "secretary", "test", []))
        first.start()
        self.assertTrue(entered.wait(2))
        second.start()
        time.sleep(0.05)
        release.set()
        first.join(3)
        second.join(3)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(peak[0], 1)
        self.assertEqual(completed, [("enter", a["ts"]), ("exit", a["ts"]),
                                     ("enter", b["ts"]), ("exit", b["ts"])])
        self.assertEqual(self.fleet._turn_gates, {})

    def test_different_threads_do_not_share_lock(self):
        import threading
        barrier = threading.Barrier(2, timeout=2)
        errors = []
        def independent(_fleet, event, agent, reason, authorizations):
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                errors.append("serialized_different_thread")
        self.fleet._work_serialized = independent.__get__(self.fleet, gateway.Fleet)
        threads = [
            threading.Thread(target=self.fleet.work,
                             args=({"channel": "C0CBC6AEAQZ",
                                    "ts": f"179418000{i}.123456"}, "secretary", "test", []))
            for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(3)
        self.assertEqual(errors, [])
        self.assertEqual(self.fleet._turn_gates, {})



class InThreadRoleSwitchTests(unittest.TestCase):
    def setUp(self):
        import copy
        import threading
        self.conf = copy.deepcopy(gateway.DEFAULT_CONF)
        self.conf["dispatch"]["placeholder"] = False
        self.fleet = gateway.Fleet.__new__(gateway.Fleet)
        self.fleet.conf = self.conf
        self.fleet.state = {"sessions": {}, "bindings": {}, "recent": {}, "outbound": {}}
        self.fleet.lock = threading.Lock()
        self.fleet._turn_gates = {}
        self.fleet.say = lambda agent, channel, text, thread_ts=None, run_id="": "1794180009.123456"
        self.fleet._react = lambda *args: None
        self.fleet._unreact = lambda *args: None
        self.logging = patch.object(gateway, "log", return_value=None)
        self.logging.start()
        self.addCleanup(self.logging.stop)
        self.audit = patch.object(gateway, "audit", return_value=None)
        self.audit.start()
        self.addCleanup(self.audit.stop)
        self.persistence = patch.object(gateway, "save_state", return_value=None)
        self.persistence.start()
        self.addCleanup(self.persistence.stop)

    def test_shared_bot_role_selector_changes_binding_not_other_role_session(self):
        conf = self.conf
        text = "<@U0BT71H4FQE> engineering: please review this"
        result = gateway.route(
            conf, text=text, channel="C0CBC6AEAQZ", user="U0BRET6191C",
            is_dm=False, binding="secretary")
        self.assertEqual(result, ("engineering", "explicit-role-switch"))
        self.assertEqual(
            gateway.route(conf, text="engineering please review",
                          channel="C0CBC6AEAQZ", user="U0BRET6191C",
                          is_dm=False, binding="secretary"),
            ("secretary", "thread-binding"),
        )
        self.assertEqual(
            gateway.route(conf, text="<@U0UNRELATE9> engineering: review",
                          channel="C0CBC6AEAQZ", user="U0BRET6191C",
                          is_dm=False, binding="secretary"),
            ("secretary", "thread-binding"),
        )

    def test_each_role_resumes_only_its_own_session_in_same_thread(self):
        root = "1794180000.123456"
        channel = "C0CBC6AEAQZ"
        ids = {
            "engineering": "engineer-uuid-123456789",
            "secretary": "secretary-uuid-123456789",
        }
        calls = []
        def run(profile, prompt, sid, timeout, model):
            calls.append((profile, sid))
            return True, "model response", ids[profile]

        with patch.object(gateway, "dispatch", side_effect=run):
            self.fleet.work({"channel": channel, "ts": root, "text": "first"},
                            "engineering", "mention", [])
            self.fleet.work({"channel": channel, "thread_ts": root,
                             "ts": "1794180001.123456", "text": "switch"},
                            "secretary", "explicit-role-switch", [])
            self.fleet.work({"channel": channel, "thread_ts": root,
                             "ts": "1794180002.123456", "text": "back"},
                            "engineering", "explicit-role-switch", [])
        self.assertEqual(calls, [
            ("engineering", None),
            ("secretary", None),
            ("engineering", "engineer-uuid-123456789"),
        ])
        self.assertEqual(self.fleet.state["sessions"], {
            f"{channel}:{root}:engineering": ids["engineering"],
            f"{channel}:{root}:secretary": ids["secretary"],
        })
        self.assertEqual(self.fleet.state["bindings"][f"{channel}:{root}"], "engineering")
        turn_run_ids = [call.kwargs["run_id"] for call in gateway.audit.call_args_list]
        self.assertEqual(len(turn_run_ids), 3)
        self.assertEqual(len(set(turn_run_ids)), 3)

    def test_failed_native_turn_does_not_advance_resume_pointer(self):
        root = "1794180000.123456"
        channel = "C0CBC6AEAQZ"
        sessions = self.fleet.state["sessions"]
        sessions[f"{channel}:{root}:secretary"] = "previous-successful-id"
        with patch.object(gateway, "dispatch",
                          return_value=(False, "native error", "ambiguous-next-id")):
            self.fleet.work({"channel": channel, "thread_ts": root,
                             "ts": "1794180001.123456", "text": "attempt"},
                            "secretary", "thread-binding", [])
        self.assertEqual(sessions[f"{channel}:{root}:secretary"], "previous-successful-id")

    def test_legacy_single_role_session_migrates_only_to_its_bound_role(self):
        root = "1794180000.123456"
        channel = "C0CBC6AEAQZ"
        self.fleet.state["bindings"][f"{channel}:{root}"] = "secretary"
        self.fleet.state["sessions"][f"{channel}:{root}"] = "old-secretary-session"
        calls = []
        def run(profile, prompt, sid, timeout, model):
            calls.append((profile, sid))
            return True, "ok", "native-" + profile
        with patch.object(gateway, "dispatch", side_effect=run):
            self.fleet.work({"channel": channel, "thread_ts": root,
                             "ts": "1794180001.123456", "text": "more"},
                            "secretary", "thread-binding", [])
            self.fleet.work({"channel": channel, "thread_ts": root,
                             "ts": "1794180002.123456", "text": "new role"},
                            "engineering", "explicit-role-switch", [])
        self.assertEqual(calls, [("secretary", "old-secretary-session"),
                                 ("engineering", None)])


if __name__ == "__main__":
    unittest.main()
