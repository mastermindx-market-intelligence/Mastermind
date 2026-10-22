#!/usr/bin/env python3
"""Credential-custody tests: fixture config and a local fake Codex only.

The production helper is imported by a subprocess fixture that binds only its
file paths to a temporary directory. The wrapper's one host-provider-home path
is likewise bound in its fixture copy; HOME/CODEX_HOME are never repurposed.
No production credential file, executable, service or network is consulted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest


CANDIDATE = Path(__file__).resolve().parents[1] / "candidate"
FIXTURE_VALUES = {
    "account-a": "fixture-private-value-a-'-$()-only",
    "account-b": "fixture-private-value-b-\"-;-$()-only",
}
INHERITED_FIXTURE_VALUE = "fixture-inherited-value-must-be-discarded"


class Harness:
    def __init__(self, root: Path):
        self.root = root
        self.ext = root / "ext"
        self.bin = root / "bin"
        self.work = root / "work"
        self.config = root / "fixture-config.json"
        self.policy = root / "fixture-policy.json"
        self.slots = root / "fixture-slots"
        self.audit = root / "helper-audit.jsonl"
        self.calls = root / "codex-calls.jsonl"
        self.behavior = root / "codex-behavior.json"
        self.broker_calls = root / "broker-calls.jsonl"
        self.provider_home = root / "provider-home"
        self.prompt = root / "prompt.txt"
        for path in (self.ext, self.bin, self.work, self.provider_home):
            path.mkdir()
        self.prompt.write_text("Caller prompt bytes: spaces, 'quotes', $() and \u03bb.\n")
        (self.provider_home / "config.toml").write_text('model_provider = "fixture"\n')
        self.configure()
        self.policy.write_text(json.dumps({
            "per_key_cap": 7, "onpeak_per_key_cap": 7,
            "offpeak_window": {"start": "22:00", "end": "08:00", "tz": "UTC"},
        }))
        self.behavior.write_text(json.dumps([{"message": "STATUS: COMPLETE\nfixture final"}]))

        # Patch path dependencies in this test copy, never the production code
        # or a process-wide home directory. There is exactly one host binding.
        wrapper = (CANDIDATE / "qwen_exec.sh").read_text()
        host_binding = 'CODEX_HOME_DIR="$HOME/lanes/codex_bailian"'
        assert wrapper.count(host_binding) == 1
        wrapper = wrapper.replace(host_binding, 'CODEX_HOME_DIR="$CUSTODY_TEST_PROVIDER_HOME"')
        self.wrapper = self.ext / "qwen_exec.sh"
        self.wrapper.write_text(wrapper)
        self.wrapper.chmod(0o700)
        self.driver = self.ext / "bailian_keys.py"
        self.driver.write_text(textwrap.dedent(f'''\
            import importlib.util
            import json
            import os
            from pathlib import Path
            import sys

            spec = importlib.util.spec_from_file_location("custody_fixture_keys", {str(CANDIDATE / 'bailian_keys.py')!r})
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            module.CONFIG_PATH = {str(self.config)!r}
            module.POLICY_PATH = {str(self.policy)!r}
            module.SLOTS_ROOT = {str(self.slots)!r}
            module.LOCK_PATH = {str(self.slots / '.lock')!r}

            def audit(kind):
                with open({str(self.audit)!r}, "a", encoding="utf-8") as out:
                    out.write(json.dumps({{
                        "kind": kind, "argv": sys.argv[1:],
                        "pid": os.getpid(), "ppid": os.getppid(),
                        "inherited_credential_present": "BAILIAN_API_KEY" in os.environ,
                    }}) + "\\n")

            original_load = module._load_config
            def fixture_load():
                audit("config-read")
                return original_load()
            module._load_config = fixture_load
            audit("command")
            rc = module.main()
            if (sys.argv[1] == os.environ.get("CUSTODY_TEST_REMOVE_AFTER") and rc == 0):
                Path(module.CONFIG_PATH).write_text('{{"token-plan":{{"api_keys":[]}}}}')
            raise SystemExit(rc)
        '''))
        self.fake_codex = self.bin / "codex"
        self.fake_codex.write_text(f"#!{sys.executable}\n" + textwrap.dedent(f'''\
            import json
            import os
            from pathlib import Path
            import signal
            import sys

            fixture_values = {FIXTURE_VALUES!r}
            calls_path = Path({str(self.calls)!r})
            previous = calls_path.read_text().splitlines() if calls_path.exists() else []
            scenario = json.loads(Path({str(self.behavior)!r}).read_text())
            step = scenario[min(len(previous), len(scenario) - 1)]
            received = os.environ.get("BAILIAN_API_KEY")
            aliases = [name for name, value in fixture_values.items() if received == value]
            record = {{
                "argv": sys.argv[1:], "stdin": sys.stdin.read(),
                "pid": os.getpid(), "ppid": os.getppid(),
                "credential_matches_aliases": aliases,
                "inherited_value_reused": received == {INHERITED_FIXTURE_VALUE!r},
                "pool_account": os.environ.get("POOL_ACCOUNT"),
                "codex_home": os.environ.get("CODEX_HOME"),
                "slots": {{path.name: sorted(int(p.name) for p in path.iterdir() if p.name.isdigit())
                          for path in Path({str(self.slots)!r}).glob("*") if path.is_dir()}},
            }}
            with calls_path.open("a") as output:
                output.write(json.dumps(record) + "\\n")
            if "signal" in step:
                os.kill(os.getpid(), int(step["signal"]))
                raise SystemExit(99)
            tid = sys.argv[3] if sys.argv[1:3] == ["exec", "resume"] else "fixture-thread"
            print(json.dumps({{"type": "thread.started", "thread_id": tid}}))
            print(json.dumps({{"type": "turn.started"}}))
            framing = step.get("framing", "good")
            if framing == "failed":
                print(json.dumps({{"type": "turn.failed", "error": {{"message": "fixture turn failed"}}}}))
            else:
                if framing == "invalid":
                    print("fixture invalid JSONL")
                print(json.dumps({{"type": "item.completed", "item": {{
                    "type": "agent_message", "text": step.get("message", "STATUS: COMPLETE\\nfixture final")
                }}}}))
                print(json.dumps({{"type": "turn.completed"}}))
            if step.get("stderr"):
                print(step["stderr"], file=sys.stderr)
            raise SystemExit(int(step.get("rc", 0)))
        '''))
        self.fake_codex.chmod(0o700)
        (self.bin / "python3").symlink_to(sys.executable)
        (self.ext / "studio_mcp_projection.sh").write_text(
            '#!/bin/bash\n'
            'if [ -n "${BAILIAN_API_KEY:-}" ]; then exit 91; fi\n'
            "printf '%s\\n' 'mcp_servers={}'\n"
        )
        (self.ext / "studio_mcp_projection.sh").chmod(0o700)
        (self.ext / "pool_ledger.py").write_text("raise SystemExit(0)\n")
        (self.ext / "lease_broker.py").write_text(textwrap.dedent(f'''\
            import json
            import sys
            with open({str(self.broker_calls)!r}, "a") as out:
                out.write(json.dumps(sys.argv[1:]) + "\\n")
            raise SystemExit(91)
        '''))

    def configure(self, values=None):
        values = FIXTURE_VALUES if values is None else values
        self.config.write_text(json.dumps({"token-plan": {"api_keys": [
            {"name": name, "api_key": value} for name, value in values.items()
        ]}}))
        self.config.chmod(0o600)

    def env(self, **updates):
        # Whitelist only test inputs; no inherited provider environment is read.
        env = {
            "PATH": str(self.bin) + os.pathsep + os.defpath,
            "LANG": "C.UTF-8",
            "TMPDIR": str(self.work),
            "QWEN_EXEC_SLOTTED": "1",
            "QWEN_EXEC_KEY_WAIT": "0",
            "QWEN_EXEC_MAX_CONTINUES": "2",
            "CUSTODY_TEST_PROVIDER_HOME": str(self.provider_home),
            "BAILIAN_API_KEY": INHERITED_FIXTURE_VALUE,
        }
        env.update(updates)
        return env

    @staticmethod
    def read_jsonl(path):
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def run_helper(self, *args, env=None, stdin="", bash_x=False):
        cmd = [sys.executable, str(self.driver), *args]
        if bash_x:
            cmd = ["/bin/bash", "-x", "-c", 'exec "$@"', "custody-test", *cmd]
        return self.run(cmd, env=env, stdin=stdin)

    def run_wrapper(self, env=None):
        return self.run(["/bin/bash", "-x", str(self.wrapper), str(self.root),
                         "fixture model", str(self.prompt)], env=env)

    def run(self, cmd, *, env=None, stdin=""):
        proc = subprocess.Popen(cmd, cwd=self.root, env=env or self.env(),
                                text=True, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = proc.communicate(stdin, timeout=15)
        except BaseException:
            proc.kill()
            proc.communicate()
            raise
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr), proc.pid


class CredentialCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fabric-credential-custody-")
        self.addCleanup(self.tmp.cleanup)
        self.h = Harness(Path(self.tmp.name))

    def assert_no_value_output(self, result):
        for value in [*FIXTURE_VALUES.values(), INHERITED_FIXTURE_VALUE]:
            self.assertNotIn(value, result.stdout)
            self.assertNotIn(value, result.stderr)
            self.assertNotIn(value, self.h.calls.read_text() if self.h.calls.exists() else "")
            self.assertNotIn(value, self.h.audit.read_text() if self.h.audit.exists() else "")

    def assert_slots_released(self):
        self.assertEqual([], [p for p in self.h.slots.glob("*/*") if p.name.isdigit()])

    def assert_custody(self, result, wrapper_pid, expected_aliases):
        self.assert_no_value_output(result)
        calls = self.h.read_jsonl(self.h.calls)
        self.assertEqual([c["credential_matches_aliases"] for c in calls],
                         [[name] for name in expected_aliases])
        commands = [r for r in self.h.read_jsonl(self.h.audit) if r["kind"] == "command"]
        self.assertTrue(commands)
        self.assertFalse(any(r["inherited_credential_present"] for r in commands))
        handoffs = [r for r in commands if r["argv"][0] == "exec-codex"]
        self.assertEqual([c["pid"] for c in calls], [r["pid"] for r in handoffs])
        for call, name in zip(calls, expected_aliases):
            self.assertFalse(call["inherited_value_reused"])
            self.assertEqual(call["ppid"], wrapper_pid)
            self.assertEqual(call["slots"][name], [wrapper_pid])
            self.assertNotEqual(call["pid"], wrapper_pid)
            self.assertNotIn(call["pid"], sum(call["slots"].values(), []))
        self.assert_slots_released()
        return calls

    def test_retired_env_never_reads_config_or_emits_value(self):
        self.h.config.write_text("malformed " + FIXTURE_VALUES["account-a"])
        result, _ = self.h.run_helper("env", "account-a", bash_x=True)
        self.assertEqual(result.returncode, 78)
        self.assertEqual(result.stdout, "")
        self.assertIn("BAILIAN_ENV_EXPORT_RETIRED", result.stderr)
        self.assertFalse(any(r["kind"] == "config-read" for r in self.h.read_jsonl(self.h.audit)))
        self.assertFalse(self.h.calls.exists())
        self.assert_no_value_output(result)

    def test_check_key_has_no_output_and_starts_no_worker(self):
        result, _ = self.h.run_helper("check-key", "account-a")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.h.calls.exists())
        self.assertFalse(self.h.slots.exists())
        self.assert_no_value_output(result)

    def test_public_pick_and_status_contain_names_without_private_values(self):
        picked, _ = self.h.run_helper("pick", "--require", "account-a")
        self.assertEqual(picked.returncode, 0)
        self.assertEqual(picked.stdout, "account-a\n")
        status, _ = self.h.run_helper("status")
        self.assertEqual(status.returncode, 0)
        self.assertIn("name=account-a ", status.stdout)
        self.assertIn("name=account-b ", status.stdout)
        self.assert_no_value_output(picked)
        self.assert_no_value_output(status)
        released, _ = self.h.run_helper("release", "account-a", str(os.getpid()))
        self.assertEqual(released.returncode, 0)
        self.assert_slots_released()

    def test_direct_handoff_under_bash_x_preserves_pid_io_argv_and_exit(self):
        self.h.behavior.write_text(json.dumps([{"rc": 23, "stderr": "fixture child diagnostic"}]))
        args = ["resume", "thread with spaces", "-m", "model with spaces", "literal $() ; ' "]
        result, pid = self.h.run_helper(
            "exec-codex", "account-b", "--", *args, stdin="unchanged stdin\n",
            env=self.h.env(LANE_LEASED="1", POOL_ACCOUNT="account-b"), bash_x=True)
        self.assertEqual(result.returncode, 23)
        call, = self.h.read_jsonl(self.h.calls)
        self.assertEqual(call["pid"], pid)
        self.assertEqual(call["argv"], ["exec", *args])
        self.assertEqual(call["stdin"], "unchanged stdin\n")
        self.assertEqual(call["credential_matches_aliases"], ["account-b"])
        self.assertFalse(call["inherited_value_reused"])
        self.assertIn("fixture child diagnostic", result.stderr)
        self.assertEqual(json.loads(result.stdout.splitlines()[0])["thread_id"], "thread with spaces")
        self.assert_no_value_output(result)

    def test_bad_or_missing_credential_refuses_before_codex(self):
        cases = [
            ("unknown", {}, "account-a", 75),
            ("empty", {"account-a": ""}, "account-a", 75),
            ("nul", {"account-a": "fixture\x00value"}, "account-a", 75),
            ("wrong-type", {"account-a": {"fixture": "value"}}, "account-a", 75),
            ("bad-name", FIXTURE_VALUES, "bad/name", 78),
        ]
        for label, config, name, rc in cases:
            with self.subTest(label=label):
                self.h.configure(config)
                result, _ = self.h.run_helper("exec-codex", name, "--", "-", bash_x=True)
                self.assertEqual(result.returncode, rc)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.h.calls.exists())
                self.assert_no_value_output(result)
        self.h.config.unlink()
        result, _ = self.h.run_helper("exec-codex", "account-a", "--", "-")
        self.assertEqual(result.returncode, 75)
        self.assertFalse(self.h.calls.exists())
        self.h.config.write_text("malformed " + FIXTURE_VALUES["account-a"])
        result, _ = self.h.run_helper("exec-codex", "account-a", "--", "-")
        self.assertEqual(result.returncode, 75)
        self.assertFalse(self.h.calls.exists())
        self.assert_no_value_output(result)

    def test_outer_account_mismatch_and_bad_syntax_do_not_read_config(self):
        result, _ = self.h.run_helper("exec-codex", "account-a", "--", "-",
                                     env=self.h.env(LANE_LEASED="1", POOL_ACCOUNT="account-b"))
        self.assertEqual(result.returncode, 78)
        self.assertIn("BAILIAN_CODEX_OUTER_ACCOUNT_MISMATCH", result.stderr)
        syntax, _ = self.h.run_helper("exec-codex", "account-a", "/bin/sh", "-c", "exit 0")
        self.assertEqual(syntax.returncode, 2)
        self.assertFalse(any(r["kind"] == "config-read" for r in self.h.read_jsonl(self.h.audit)))
        self.assertFalse(self.h.calls.exists())
        self.assert_no_value_output(result)
        self.assert_no_value_output(syntax)

    def test_exec_lookup_and_permission_failures_preserve_shell_statuses(self):
        # Restrict lookup to this fixture directory: never fall through to a
        # host-installed Codex when testing the missing-executable case.
        env = self.h.env(PATH=str(self.h.bin))
        self.h.fake_codex.unlink()
        missing, _ = self.h.run_helper("exec-codex", "account-a", "--", "-", env=env)
        self.assertEqual(missing.returncode, 127)
        self.assertIn("BAILIAN_CODEX_EXEC_UNAVAILABLE", missing.stderr)
        self.h.fake_codex.write_text("fixture non-executable")
        self.h.fake_codex.chmod(0o600)
        refused, _ = self.h.run_helper("exec-codex", "account-a", "--", "-", env=env)
        self.assertEqual(refused.returncode, 126)
        self.assertIn("BAILIAN_CODEX_EXEC_REFUSED", refused.stderr)
        self.assertFalse(self.h.calls.exists())
        self.assert_no_value_output(missing)
        self.assert_no_value_output(refused)

    def test_initial_wrapper_preserves_args_prompt_slot_and_output(self):
        prompt_before = self.h.prompt.read_bytes()
        result, pid = self.h.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "STATUS: COMPLETE\nfixture final\n")
        call, = self.assert_custody(result, pid, ["account-a"])
        self.assertEqual(call["argv"], [
            "exec", "-c", "mcp_servers={}", "--json",
            "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
            "-C", str(self.h.root), "-m", "fixture model", "-",
        ])
        self.assertTrue(call["stdin"].startswith(prompt_before.decode()))
        self.assertEqual(call["stdin"].count("<<<TERMINAL RESPONSE CONTRACT>>>"), 1)
        self.assertEqual(self.h.prompt.read_bytes(), prompt_before)
        self.assertFalse(self.h.broker_calls.exists())

    def test_explicit_resume_preserves_thread_prompt_and_empty_stdin(self):
        resume_prompt = "literal resume $() ; ' prompt"
        result, pid = self.h.run_wrapper(self.h.env(
            QWEN_EXEC_RESUME="existing-thread", QWEN_EXEC_RESUME_PROMPT=resume_prompt))
        self.assertEqual(result.returncode, 0, result.stderr)
        call, = self.assert_custody(result, pid, ["account-a"])
        self.assertEqual(call["argv"], [
            "exec", "resume", "existing-thread", "-c", "mcp_servers={}", "--json",
            "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
            "-m", "fixture model", resume_prompt,
        ])
        self.assertEqual(call["stdin"], "")

    def test_leased_auto_continue_keeps_exact_account_and_parent_slot(self):
        self.h.behavior.write_text(json.dumps([
            {"message": "fixture progress"}, {"message": "STATUS: COMPLETE\nfixture final"},
        ]))
        result, pid = self.h.run_wrapper(self.h.env(
            LANE_LEASED="1", POOL_ACCOUNT="account-b", POOL_LEASE_ID="fixture-lease"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "STATUS: COMPLETE\nfixture final\n")
        calls = self.assert_custody(result, pid, ["account-b", "account-b"])
        self.assertEqual(calls[0]["argv"][0], "exec")
        self.assertEqual(calls[1]["argv"][:3], ["exec", "resume", "fixture-thread"])
        self.assertEqual(calls[1]["stdin"], "")
        self.assertEqual(calls[0]["codex_home"], calls[1]["codex_home"])
        self.assertTrue(calls[0]["codex_home"].startswith(str(self.h.work) + "/"))
        self.assertFalse(Path(calls[0]["codex_home"]).exists())
        self.assertFalse(self.h.broker_calls.exists())

    def test_unleased_auth_rotation_resumes_same_thread_with_new_account(self):
        self.h.behavior.write_text(json.dumps([
            {"framing": "failed", "stderr": "HTTP 401 Unauthorized", "rc": 41},
            {"message": "STATUS: COMPLETE\nfixture final"},
        ]))
        result, pid = self.h.run_wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.assert_custody(result, pid, ["account-a", "account-b"])
        self.assertEqual(calls[1]["argv"][:3], ["exec", "resume", "fixture-thread"])
        self.assertTrue((self.h.slots / "account-a.cooldown").is_file())
        self.assertFalse(self.h.broker_calls.exists())

    def test_leased_quota_failure_does_not_switch_account(self):
        self.h.behavior.write_text(json.dumps([
            {"framing": "failed", "stderr": "HTTP 429 rate limit", "rc": 42},
        ]))
        result, pid = self.h.run_wrapper(self.h.env(
            LANE_LEASED="1", POOL_ACCOUNT="account-a", POOL_LEASE_ID="fixture-lease"))
        self.assertEqual(result.returncode, 42)
        self.assertEqual(result.stdout, "")
        self.assert_custody(result, pid, ["account-a"])
        self.assertFalse(self.h.broker_calls.exists())

    def test_missing_key_at_preflight_releases_slot_without_worker(self):
        result, _ = self.h.run_wrapper(self.h.env(CUSTODY_TEST_REMOVE_AFTER="pick"))
        self.assertEqual(result.returncode, 75)
        self.assertEqual(result.stdout, "")
        self.assertIn("NO_USABLE_KEY", result.stderr)
        self.assertFalse(self.h.calls.exists())
        self.assert_slots_released()
        self.assert_no_value_output(result)

    def test_key_disappearing_after_preflight_fails_before_task_without_retry(self):
        result, _ = self.h.run_wrapper(self.h.env(CUSTODY_TEST_REMOVE_AFTER="check-key"))
        self.assertEqual(result.returncode, 75)
        self.assertEqual(result.stdout, "")
        self.assertIn("BAILIAN_CODEX_KEY_UNAVAILABLE", result.stderr)
        self.assertFalse(self.h.calls.exists())
        handoffs = [r for r in self.h.read_jsonl(self.h.audit)
                    if r["kind"] == "command" and r["argv"][0] == "exec-codex"]
        self.assertEqual(len(handoffs), 1)
        self.assert_slots_released()
        self.assert_no_value_output(result)

    def test_unknown_worker_failure_keeps_rc_and_never_retries(self):
        self.h.behavior.write_text(json.dumps([
            {"framing": "failed", "stderr": "fixture transport disconnected", "rc": 37},
        ]))
        result, pid = self.h.run_wrapper()
        self.assertEqual(result.returncode, 37)
        self.assertEqual(result.stdout, "")
        self.assert_custody(result, pid, ["account-a"])
        self.assertFalse(list(self.h.slots.glob("*.cooldown")))

    def test_unconfirmed_stream_keeps_rc_77_without_retry(self):
        self.h.behavior.write_text(json.dumps([{"framing": "invalid"}]))
        result, pid = self.h.run_wrapper()
        self.assertEqual(result.returncode, 77)
        self.assertEqual(result.stdout, "")
        self.assert_custody(result, pid, ["account-a"])

    def test_signal_status_is_preserved_by_exec_and_wrapper(self):
        self.h.behavior.write_text(json.dumps([{"signal": signal.SIGTERM}]))
        direct, _ = self.h.run_helper("exec-codex", "account-a", "--", "-")
        self.assertEqual(direct.returncode, -signal.SIGTERM)
        self.assert_no_value_output(direct)
        self.h.calls.unlink()
        self.h.audit.unlink()
        wrapped, pid = self.h.run_wrapper()
        self.assertEqual(wrapped.returncode, 128 + signal.SIGTERM)
        self.assertEqual(wrapped.stdout, "")
        self.assert_custody(wrapped, pid, ["account-a"])


if __name__ == "__main__":
    unittest.main()
