"""Real APPLICATION process carrier in the incumbent remote-sub owners.

The fixtures drive the actual controller, executor interpreter, physical
LaneLease and owned-process runtime against a harmless local child. The
trusted owner module is an explicitly SYNTHETIC authoritative boundary: not a
production grant, signer or permission.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "candidate"
SOURCE = ROOT / "source"
sys.path[:0] = [str(CANDIDATE), str(SOURCE), str(ROOT / "tests")]
import native_remote
import support_bundle

USER_TEXT = "fixture application payload"
SYSTEM_TEXT = "fixture system prompt"
CHILD = "import sys;sys.stdout.write('APPLICATION-OK:'+sys.stdin.read())"
POLICY_YAML = "routing: {}\npools:\n  grok:\n    windows:\n      weekly: {}\n"
OWNER_TEMPLATE = '''"""SYNTHETIC fixture owner: NOT a production grant, signer or permission.
It only lets the isolated carrier fixtures drive the real private branch."""
def application_owner_bind(envelope, *, support_digest, run_id, source_digests):
    if (envelope.get("purpose") != "APPLICATION" or envelope.get("support_digest") != support_digest
            or envelope.get("dispatch_id") != run_id or envelope.get("host") != {host!r}
            or envelope.get("account") != "account-fixture"
            or envelope.get("pool") != "pool-fixture" or envelope.get("model") != "model-fixture"):
        return None
    return {{"schema": "mastermind.application.native-profile.v1",
            "argv": {argv!r}, "cwd": {cwd!r}, "env": {{}},
            "system_text": {system!r}, "profile_digest": {profile_digest!r},
            "compiler_digest": {compiler_digest!r}, "policy_digest": {policy_digest!r},
            "max_output_bytes": 65536}}
def application_owner_check(envelope):
    if envelope.get("purpose") != "APPLICATION":
        raise ValueError("fixture_owner_check_refused")
'''
TRANSPORT_STUB = '''#!/usr/bin/env python3
"""Local stand-in for the incumbent SSH/SCP/RSYNC transport."""
import os, shutil, subprocess, sys
from pathlib import Path
HOME = Path(os.environ["FIXTURE_REMOTE_HOME"])
ROLE = Path(sys.argv[0]).name
expand = lambda path: str(HOME / path[2:]) if path.startswith("~/") else path
if ROLE == "scp":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dest = expand(args[-1].partition(":")[2])
    target = Path(dest)
    if len(args) > 2 or target.is_dir() or dest.endswith("/"):
        target.mkdir(parents=True, exist_ok=True)
        for item in args[:-1]:
            shutil.copyfile(item, target / Path(item).name)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args[0], target)
    raise SystemExit(0)
if ROLE == "rsync":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    shutil.copyfile(expand(args[0].partition(":")[2]), args[1])
    raise SystemExit(0)
command = sys.argv[-1]
if "support_bundle.py" in command:
    releases = HOME / "lanes" / "support-releases"
    raise SystemExit(0 if any(releases.glob("*/ext/remote_sub_exec.py")) else 1)
result = subprocess.run(["/bin/bash", "-c", command],
                         env=dict(os.environ, HOME=str(HOME)),
                         capture_output=True, text=True)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
raise SystemExit(result.returncode)
'''
SUPPORT_FILES = ("provider_outcome.py quota_circuit.py recovery_artifacts.py capacity_preflight.py "
    "native_runtime_bindings.py commission_deadline.py pools.yaml fabric_policy_snapshot.py "
    "remote_sub_exec.py fabric_cpu_scope.py native_remote.py fabric_operator_client.py "
    "fabric_operator_stop.py fabric_operator_diagnostics.py artifact_production.py "
    "artifact_reader.py lane_runtime.py sub.sh slot.py pick.py glm_bound_claude.py model_tier.py "
    "yes codex_usage.py go_remote_codex.py go_remote_capsule.py mm_codex_exec.sh glm_codex_exec.sh "
    "go_codex_exec.sh qwen_exec.sh fabric_client_projection.py studio_mcp_projection.sh "
    "mm_feeder_lib.py pool_ledger.py lease_broker.py glm_keys.py bailian_keys.py").split()
OWNER_NAME = "application_native_owner.py"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ApplicationFixture:

    def __init__(self, root: Path, *, child: str = CHILD,
                 host: str = "fixture-host", owner_extra: str = ""):
        self.root = root
        self.host = host
        self.home = root / "remote-home"
        self.stable = self.home / "lanes" / "ext"
        self.stable.mkdir(parents=True)
        # Match the incumbent remote interpreter path with the test runtime.
        (self.home / "lanes" / "venv").symlink_to(
            Path(sys.executable).parent.parent, target_is_directory=True)
        for name in ("active", "lanes", "slots", "state", "GROK_EXHAUSTED"):
            (self.stable / name).mkdir(exist_ok=True)
        for policy in (root / "orch" / "fabric",
                       self.home / "lanes" / "orch" / "fabric"):
            policy.mkdir(parents=True)
            (policy / "pools.yaml").write_text(POLICY_YAML)
        self.controller = root / "controller"
        shutil.copytree(CANDIDATE, self.controller)
        for name in SUPPORT_FILES:
            src = SOURCE / name
            if src.exists() and not (self.controller / name).exists():
                shutil.copyfile(src, self.controller / name)
        self.argv = [sys.executable, "-c", child]
        self.cwd = str(root)
        self.profile_digest = _sha("profile")
        self.compiler_digest = _sha("compiler")
        self.policy_digest = _sha("policy")
        (self.controller / OWNER_NAME).write_text(OWNER_TEMPLATE.format(
            argv=self.argv, cwd=self.cwd, system=SYSTEM_TEXT,
            profile_digest=self.profile_digest, compiler_digest=self.compiler_digest,
            policy_digest=self.policy_digest, host=self.host) + owner_extra)
        (self.controller / "hosts.json").write_text(json.dumps({self.host: {
            "ssh_alias": self.host, "cores": 4, "max_active": 2,
            "load_gate": 3.0, "roles": ["lanes"], "allowed_modes": ["application"],
            "hostnames": [socket.gethostname().split(".", 1)[0]]}}))
        shutil.copyfile(self.controller / "hosts.json", self.stable / "hosts.json")
        self.support_digest = self._publish()
        self.release = self.home / "lanes" / "support-releases" / self.support_digest
        self.ext = self.release / "ext"
        for role in ("ssh", "scp", "rsync"):
            (root / role).write_text(TRANSPORT_STUB)
            (root / role).chmod(0o755)

    def _publish(self):
        """Exercise the actual incumbent publisher and exact APPLICATION closure."""
        manifest = self.root / "support.json"
        shutil.copyfile(self.root / "orch" / "fabric" / "pools.yaml",
                        self.controller / "pools.yaml")
        result = subprocess.run(
            [sys.executable, str(self.controller / "remote_sub_helpers.py"),
             "support-meta", str(self.controller), str(manifest),
             *SUPPORT_FILES, OWNER_NAME], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise AssertionError("support-meta failed: " + result.stderr)
        digest = result.stdout.split()[0]
        files = json.loads(manifest.read_text())
        (self.stable.parent / "support-releases").mkdir(exist_ok=True)
        published = support_bundle.publish(self.controller, self.stable, files)
        assert published.parent.name == digest
        assert (published / OWNER_NAME).read_bytes() == (self.controller / OWNER_NAME).read_bytes()
        return digest

    def envelope(self, run: str = "app-run-1", **overrides) -> dict:
        now = int(time.time())
        reseal = overrides.pop("reseal", True)
        value = {
            "schema": native_remote.APPLICATION_SCHEMA, "purpose": "APPLICATION",
            "principal_id": "principal-fixture", "caller_host": "caller-fixture",
            "workload": "brainclient-plaintext", "turn_id": "turn-" + run,
            "request_id": "request-" + run, "dispatch_id": run,
            "lease_id": "lease-" + run, "pool": "pool-fixture",
            "account": "account-fixture", "model": "model-fixture",
            "host": self.host, "recipe_digest": _sha("recipe"),
            "logical_payload_digest": native_remote.application_payload_digest(
                USER_TEXT, SYSTEM_TEXT), "invocation_digest": "0" * 64,
            "source_generation": _sha("source"), "support_digest": self.support_digest,
            "profile_digest": self.profile_digest,
            "compiler_digest": self.compiler_digest, "policy_digest": self.policy_digest,
            "issued_at": now, "expires_at": now + 600, "remaining_seconds": 300,
            "user_text": USER_TEXT, "system_text": SYSTEM_TEXT,
            "max_output_bytes": 65536}
        value.update(overrides)
        if reseal:
            value["invocation_digest"] = native_remote.application_invocation_digest(
                value, self.argv, self.cwd)
        return value

    def env(self) -> dict:
        env = dict(os.environ)
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        env["LANE_REMOTE_HOST"] = self.host
        # The ambient lane floors belong to the live lane; this fixture is bounded.
        env.update(SUPPORT_DIGEST=self.support_digest, LANE_MAX_ACTIVE="2",
                   LANE_MAX_LOAD_RATIO="1.5", LANE_NICE="10",
                   LANE_MAX_CPU_TCTL_C="0", LANE_MIN_FREE_DISK_GB="0",
                   LANE_MIN_FREE_MEM_GB="0", PYTHONDONTWRITEBYTECODE="1")
        for name in ("FABRIC_OPERATOR_CAPSULE", "FABRIC_OPERATOR_CAPABILITY",
                     "FABRIC_NEW_MACRO_COMMIT", "FABRIC_CPU_SCOPE_QUOTA_PCT"):
            env.pop(name, None)
        return env

    def lanes(self):
        return self.ext / "lanes"

    def run(self, run: str, envelope: dict, *, extra_env=None):
        path = self.root / (run + ".dispatch.json")
        path.write_text(json.dumps(envelope))
        env = self.env()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(self.ext / "remote_sub_exec.py"), run, "application",
             str(path), "~", envelope.get("model", "model-fixture")],
            env=env, capture_output=True, timeout=120)

    def terminal(self, run: str):
        path = self.lanes() / (run + ".application-terminal.json")
        return json.loads(path.read_text()) if path.is_file() else None

    def run_controller(self, run: str, envelope: dict, *, extra_env=None):
        path = self.root / (run + ".dispatch.json")
        path.write_text(json.dumps(envelope))
        env = self.env()
        env.update(FIXTURE_REMOTE_HOME=str(self.home),
                   REMOTE_SUB_SSH_CMD=str(self.root / "ssh"),
                   REMOTE_SUB_SCP_CMD=str(self.root / "scp"),
                   REMOTE_SUB_RSYNC_CMD=str(self.root / "rsync"),
                   REMOTE_SUB_PYTHON=sys.executable,
                   REMOTE_SUB_LOG_DIR=str(self.root / "logs"),
                   REMOTE_SUB_MAX_SECS="60", REMOTE_SUB_POLL_SECS="1",
                   POOL_TASK_COMPLEXITY="C1_ROUTINE_BOUNDED")
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["/bin/bash", str(self.controller / "remote_sub.sh"), "--run-id", run,
             self.host, "application", str(path), "~"],
            env=env, capture_output=True, timeout=180)


class ApplicationCarrier(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = ApplicationFixture(self.root)

    def test_real_carrier_runs_one_child_and_reports_a_typed_result(self):
        envelope = self.fixture.envelope("app-real-1")
        result = self.fixture.run("app-real-1", envelope)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        terminal = self.fixture.terminal("app-real-1")
        self.assertEqual(terminal["schema"], native_remote.APPLICATION_RESULT_SCHEMA)
        self.assertEqual(terminal["kind"], "native_cli_v1")
        self.assertEqual(terminal["status"], "completed")
        self.assertTrue(terminal["started"])
        self.assertEqual(terminal["returncode"], 0)
        self.assertEqual(terminal["dispatch_id"], envelope["dispatch_id"])
        self.assertEqual(terminal["invocation_digest"], envelope["invocation_digest"])
        self.assertEqual(terminal["account"], envelope["account"])
        self.assertIsNone(terminal["usage"])
        self.assertIsNone(terminal["provider_settled"])
        self.assertNotIn("status_code", terminal)
        self.assertTrue(terminal["cleanup_proven"])
        self.assertTrue(terminal["output_complete"])
        self.assertEqual(terminal["process"]["label"], "app-real-1")
        receipt = json.loads(
            (self.fixture.lanes() / "app-real-1.process.jsonl").read_text()
            .splitlines()[-1])
        self.assertEqual(receipt["schema"], "mastermind.local_owned_process_receipt.v1")
        self.assertEqual(receipt["pid"], terminal["process"]["pid"])
        self.assertTrue(receipt["cleanup"]["census_proven"])
        self.assertEqual(receipt["cleanup"]["residual_count"], 0)
        self.assertIn(b"APPLICATION-OK:" + USER_TEXT.encode(), result.stdout)
        prepare = json.loads(
            (self.fixture.lanes() / "app-real-1.application-prepare.json").read_text())
        self.assertEqual(prepare["schema"], native_remote.APPLICATION_PREPARE_SCHEMA)
        self.assertEqual(prepare["dispatch_id"], envelope["dispatch_id"])
        self.assertEqual(prepare["invocation_digest"], envelope["invocation_digest"])
        self.assertNotIn(USER_TEXT, json.dumps(prepare))

    def test_a_duplicate_pending_or_malformed_dispatch_starts_no_second_process(self):
        lanes = self.fixture.lanes()
        envelope = self.fixture.envelope("app-fence-1")
        first = self.fixture.run("app-fence-1", envelope)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        receipt = (lanes / "app-fence-1.process.jsonl").read_text()
        again = self.fixture.run("app-fence-1", envelope)
        self.assertEqual(again.returncode, 0, again.stderr.decode())
        self.assertEqual((lanes / "app-fence-1.process.jsonl").read_text(), receipt)
        self.assertEqual(len(receipt.splitlines()), 1)
        # A pending attempt and an ambiguous terminal are never launch permits.
        for run, marker, expected in (
                ("app-fence-2", "app-fence-2.application-prepare.json", 75),
                ("app-fence-3", "app-fence-3.application-terminal.json", 76)):
            lanes.mkdir(exist_ok=True)
            (lanes / marker).write_text("{}" if "prepare" in marker else "{not json")
            result = self.fixture.run(run, self.fixture.envelope(run))
            self.assertEqual(result.returncode, expected)
            self.assertFalse((lanes / (run + ".process.jsonl")).exists())

    def test_forged_and_wrong_purpose_dispatches_refuse_before_the_child(self):
        now = int(time.time())
        cases = {
            "app-forged-1": self.fixture.envelope(
                "app-forged-1", purpose="WORKER", reseal=False),
            "app-forged-2": self.fixture.envelope(
                "app-forged-2", invocation_digest=_sha("forged"), reseal=False),
            "app-forged-3": self.fixture.envelope(
                "app-forged-3", user_text="tampered", reseal=False),
            "app-forged-4": self.fixture.envelope(
                "app-forged-4", account="other-account", reseal=False),
            "app-forged-5": self.fixture.envelope(
                "app-forged-5", profile_digest=_sha("other-profile"), reseal=False),
            "app-forged-6": self.fixture.envelope(
                "app-forged-6", history=[{"role": "user"}], reseal=False),
            "app-expired-1": self.fixture.envelope(
                "app-expired-1", issued_at=now - 600, expires_at=now - 300),
        }
        for run, envelope in cases.items():
            with self.subTest(run=run):
                result = self.fixture.run(run, envelope)
                self.assertEqual(result.returncode, 78, result.stderr.decode())
                self.assertFalse(
                    (self.fixture.lanes() / (run + ".process.jsonl")).exists())

    def test_only_the_sealed_context_is_accepted_and_the_production_entry_is_closed(self):
        envelope = self.fixture.envelope("app-ctx-1")
        closed = self.root / "closed"
        closed.mkdir()
        for name in ("remote_sub_exec.py", "native_remote.py", "lane_runtime.py",
                     "commission_deadline.py", "fabric_client_projection.py"):
            shutil.copyfile(self.fixture.ext / name, closed / name)
        cases = {
            "app-ctx-1": ("_application_context={'envelope': {}}",
                          b"APPLICATION_CONTEXT_REFUSED"),
            "app-ctx-2": ("_canonical_context=object(), _application_context=object()",
                          b"APPLICATION_CONTEXT_EXCLUSIVE_REFUSED"),
        }
        for run, (args, expected) in cases.items():
            with self.subTest(run=run):
                target = self.root / (run + ".dispatch.json")
                target.write_text(json.dumps(envelope))
                script = ("import sys\n"
                          "sys.path.insert(0, " + repr(str(self.fixture.ext)) + ")\n"
                          "import remote_sub_exec as remote\n"
                          "argv = ['remote_sub_exec.py', " + repr(run) + ", 'application', "
                          + repr(str(target)) + ", '~', 'model-fixture']\n"
                          "raise SystemExit(remote.main(argv, " + args + "))\n")
                result = subprocess.run([sys.executable, "-c", script],
                                        env=self.fixture.env(), capture_output=True,
                                        timeout=60)
                self.assertEqual(result.returncode, 78)
                self.assertIn(expected, result.stderr)
                self.assertFalse((self.fixture.lanes() /
                                  (run + ".process.jsonl")).exists())
        path = self.root / "app-ctx-3.dispatch.json"
        path.write_text(json.dumps(envelope))
        result = subprocess.run(
            [sys.executable, str(closed / "remote_sub_exec.py"), "app-ctx-3",
             "application", str(path), "~", "model-fixture"],
            env=self.fixture.env(), capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 78)
        self.assertIn(b"APPLICATION_AUTHORITY_REFUSED", result.stderr)

    def test_the_controller_branch_routes_launches_and_collects_the_typed_result(self):
        envelope = self.fixture.envelope("app-ctl-1")
        result = self.fixture.run_controller("app-ctl-1", envelope)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        terminal = self.fixture.terminal("app-ctl-1")
        self.assertIsNotNone(terminal)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["kind"], "native_cli_v1")
        self.assertEqual(terminal["dispatch_id"], envelope["dispatch_id"])
        self.assertEqual(terminal["account"], envelope["account"])
        self.assertEqual(terminal["model"], envelope["model"])
        collected = list((self.root / "logs").glob("*.application-terminal.json"))
        self.assertEqual(len(collected), 1)
        self.assertEqual(json.loads(collected[0].read_text())["kind"], "native_cli_v1")
        forged = self.fixture.envelope("app-ctl-2", purpose="WORKER", reseal=False)
        refused = self.fixture.run_controller("app-ctl-2", forged)
        self.assertEqual(refused.returncode, 78, refused.stderr.decode())
        self.assertIn(b"APPLICATION_DISPATCH_REFUSED", refused.stderr)
        self.assertFalse(self.fixture.terminal("app-ctl-2"))


if __name__ == "__main__":
    unittest.main()
