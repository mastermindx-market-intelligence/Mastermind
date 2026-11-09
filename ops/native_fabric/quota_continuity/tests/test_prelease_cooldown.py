"""Causal pre-lease cooldown regression against untouched native owners.

No provider, SSH, credentials, live broker, or historical reconciliation is
used. The advisory route fixture supplies two existing allowed modes. The
request, Bash controller, broker CLI/acquire, circuit observation, status, and
foreground continuation execute the current production source unchanged.
"""
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import ModuleType
import unittest
from unittest.mock import patch

from test_commission_deadline import PYTHON_FIXTURE

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE / "candidate"), str(SOURCE / "source")]
import fabric_continuation
import lease_broker
import pool_ledger
import provider_outcome
import quota_circuit

historical = {}
for name in (
    "a04_terminal_reconcile", "native_completion_reconcile",
    "native_prestart_reconcile", "native_preexec_reconcile",
    "native_host_review_controller_reconcile",
):
    module = ModuleType(name)
    module.RUN = module.RUN_ID = "unavailable-historical-fixture"
    module.KNOWN_RUNS = ()
    historical[name] = module
spec = importlib.util.spec_from_file_location(
    "prelease_regression_adapter", SOURCE / "candidate/fabric_task.py")
api = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, historical):
    spec.loader.exec_module(api)


BROKER = r'''import json, os, sys
from pathlib import Path
import lease_broker
p = Path(os.environ["OFFLINE_REGRESSION_ROOT"])
br = lease_broker.Broker(db_path=str(p/"broker.db"),
    lock_path=str(p/"broker.lock"), accounts_path=str(p/"accounts.json"),
    now_fn=lambda:1000.0, check_pid=False, external_gates=False,
    this_host="fixture", hosts_path=str(p/"hosts.json"))
lease_broker.default_broker = lambda: br
with (p/"broker-calls.jsonl").open("a") as handle:
    handle.write(json.dumps({"argv":sys.argv[1:]})+"\n")
rc = lease_broker.main(sys.argv[1:])
with (p/"broker-returns.jsonl").open("a") as handle:
    handle.write(json.dumps({"rc":rc})+"\n")
raise SystemExit(rc)
'''

DENY_TRANSPORT = r'''import json, os, sys
from pathlib import Path
p=Path(os.environ["OFFLINE_REGRESSION_ROOT"])
with (p/"forbidden-transport.jsonl").open("a") as handle:
    handle.write(json.dumps({"argv":sys.argv[1:]})+"\n")
raise SystemExit(78)
'''


class PreleaseCooldownRace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fabric-prelease-regression-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "lanes").mkdir()
        (self.root / "state/remote_sub").mkdir(parents=True)
        self.accounts = {"providers": {
            pool: {"enabled": True, "concurrency_cap": 8,
                   "accounts": [{"name": "account", "per_account_cap": 8}]}
            for pool in ("minimax", "glm")
        }}
        (self.root / "accounts.json").write_text(json.dumps(self.accounts))
        (self.root / "hosts.json").write_text(json.dumps({"fixture": {
            "ssh_alias": "offline-never-contacted", "cores": 32,
            "max_active": 12, "load_gate": 4, "roles": ["lanes"],
            "allowed_modes": ["minimax", "glm"],
        }}))
        for name in ("remote_sub.sh", "commission_deadline.py", "remote_sub_helpers.py"):
            shutil.copyfile(SOURCE / "candidate" / name, self.root / name)
        interpreter = self.root / "fixture-python"
        interpreter.write_text("#!" + sys.executable + "\n" + PYTHON_FIXTURE)
        interpreter.chmod(0o700)
        for name, body in (("broker-cli", BROKER), ("deny-transport", DENY_TRANSPORT)):
            target = self.root / name
            target.write_text("#!" + sys.executable + "\n" + body)
            target.chmod(0o700)
        self.br = lease_broker.Broker(
            db_path=str(self.root / "broker.db"),
            lock_path=str(self.root / "broker.lock"),
            accounts_path=str(self.root / "accounts.json"),
            now_fn=lambda: 1000.0, check_pid=False, external_gates=False,
            this_host="fixture", hosts_path=str(self.root / "hosts.json"))
        self.route_calls = []
        self.native_calls = []
        self.native_returns = []
        self.selected_before_cooldown = False
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(api, "HERE", self.root))
        self.stack.enter_context(patch.object(pool_ledger, "LEDGER_PATH", str(self.root / "ledger.jsonl")))
        self.stack.enter_context(patch.object(lease_broker, "default_broker", return_value=self.br))
        self.stack.enter_context(patch.object(api.pick, "format_pick", side_effect=self.select))
        self.stack.enter_context(patch.object(api, "_route_with_deadline",
            side_effect=lambda task, options, *rest: self.select(task, **options)))
        self.stack.enter_context(patch.object(api.pick, "launch_policy", return_value={"allowed": True}))
        # These are inert configuration/telemetry boundaries. hard_filter and
        # the circuit/broker decisions themselves remain real.
        self.stack.enter_context(patch.object(api.pick, "_pool_cap", return_value=8))
        self.stack.enter_context(patch.object(api.pick, "_slot_concurrent", return_value=0))
        self.stack.enter_context(patch.object(api.pick, "_glm_enabled", return_value=True))
        self.stack.enter_context(patch.object(api.pick, "_selection_model", return_value=("glm-5.3-flash", "")))
        self.stack.enter_context(patch.object(api.pick, "_glm_broker_model_remaining", return_value=8))
        clean_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ["HOME"], "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join((str(SOURCE / "candidate"), str(SOURCE / "source"))),
            "OFFLINE_REGRESSION_ROOT": str(self.root),
            "REMOTE_SUB_BROKER_CMD": str(self.root / "broker-cli"),
            "REMOTE_SUB_SSH_CMD": str(self.root / "deny-transport"),
            "REMOTE_SUB_SCP_CMD": str(self.root / "deny-transport"),
            "REMOTE_SUB_RSYNC_CMD": str(self.root / "deny-transport"),
            "REMOTE_SUB_PYTHON": str(interpreter),
            "DEADLINE_FIXTURE_ROOT": str(self.root),
            "REMOTE_SUB_MAX_SECS": "60", "REMOTE_SUB_LEASE_WAIT": "0",
        }
        self.stack.enter_context(patch.dict(os.environ, clean_env, clear=True))
        native_run = subprocess.run

        def run_actual_controller(argv, **kwargs):
            self.native_calls.append(list(argv))
            if len(self.native_calls) == 1:
                # This event is deliberately after the adapter's actual route
                # decision and immutable launch-attempt reservation, but before
                # the child controller can ask the broker for a lease.
                self.assertEqual(self.route_calls[-1]["pool"], "minimax")
                self.assertTrue(self.path("origin", ".request-launch.json").is_file())
                self.assertFalse(quota_circuit.pool_blocked(self.br, "minimax"))
                self.selected_before_cooldown = True
                self.cool_from_settled_other_commission()
            result = native_run(argv, **kwargs, capture_output=True, timeout=10)
            self.native_returns.append(result)
            return result

        self.stack.enter_context(patch.object(api.subprocess, "run", side_effect=run_actual_controller))

    def path(self, run, suffix):
        return self.root / "state/remote_sub" / (run + suffix)

    def select(self, *args, **kwargs):
        for pool, model in (("minimax", "MiniMax-M2.7"), ("glm", "glm-5.3-flash")):
            allowed, reason = api.pick.hard_filter(pool, "mechanical", {})
            if allowed:
                self.route_calls.append({"pool": pool, "reason": reason})
                return f"POOL={pool} MODEL={model} HOST=fixture MODE={pool}"
        return "NONE reason=no_pool_available"

    def cool_from_settled_other_commission(self):
        lease = self.br.acquire("other-root", "minimax", model="MiniMax-M2.7",
            host="fixture", task_class="remote-minimax", ttl=1000, wait=0)
        self.assertTrue(lease.ok)
        out = dict(schema=provider_outcome.SCHEMA, run_id="other-run", lease_id=lease.lease_id,
            root_id="other-root", provider="minimax", account="account", host="fixture",
            model="MiniMax-M2.7", kind="rate_limit", command_rc=75, observed_at=1000,
            reset_at=None, initial_rejection=True, stdout_sha256=hashlib.sha256(b"").hexdigest())
        proc = dict(schema="mastermind.local_owned_process_receipt.v1", label="other-run",
            returncode=75, stdout_sha256=out["stdout_sha256"], stdout_truncated=False,
            stderr_truncated=False, timed_out=False, cleanup=dict(
                census_proven=True, identity_verified=True, residual_count=0, status="not_needed"))
        op, pp = self.root / "other.outcome.json", self.root / "other.process.json"
        op.write_text(json.dumps(out)); pp.write_text(json.dumps(proc))
        lock = self.br._lock()
        try:
            conn = self.br._conn()
            try:
                self.observation = quota_circuit.observe_locked(
                    self.br, conn, lease.lease_id, "other-root", "other-run", op, pp)
            finally:
                conn.close()
        finally:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
        self.assertTrue(self.br.release(lease.lease_id, "other-root"))
        self.assertTrue(quota_circuit.pool_blocked(self.br, "minimax"))

    def test_new_advisory_selection_observes_cooldown(self):
        self.assertIn("POOL=minimax ", self.select())
        self.cool_from_settled_other_commission()
        self.assertIn("POOL=glm ", self.select())
        # This alternate is truly grantable at the real broker, not merely a
        # route string. Its test-only check is released immediately.
        alternate = self.br.acquire("control-root", "glm", model="glm-5.3-flash",
            host="fixture", task_class="fixture", ttl=1000, wait=0)
        self.assertTrue(alternate.ok)
        self.assertTrue(self.br.release(alternate.lease_id, "control-root"))

    def test_already_selected_cooldown_is_handed_back_for_fresh_routing(self):
        rc = fabric_continuation.foreground(api, "origin", "mechanical", cwd="~",
            packet=None, stdin_bytes=b"PONG-only inert task\n", root_id="root",
            parent_run_id="parent", task_complexity="C0_MECHANICAL")
        route_calls_at_return = list(self.route_calls)
        status = api.inspect_run("origin")
        view = fabric_continuation.resolve(api, "origin")
        log = self.path("origin", ".log").read_text()
        with self.br._conn() as conn:
            contender_leases = conn.execute(
                "SELECT COUNT(*) FROM leases WHERE orchestrator_id='root'").fetchone()[0]
        self.assertTrue(self.selected_before_cooldown)
        self.assertTrue(self.observation["recorded"])
        self.assertIn("LEASE_REFUSED rc=75", log)
        self.assertNotIn("LAUNCH stdout=", log)
        self.assertEqual(contender_leases, 0)
        self.assertFalse((self.root / "forbidden-transport.jsonl").exists())
        self.assertIn("POOL=glm ", self.select())
        evidence = {
            "schema": "offline.prelease_cooldown_regression.v1",
            "source_hashes": {name: hashlib.sha256((SOURCE / "candidate" / name).read_bytes()).hexdigest()
                for name in ("fabric_continuation.py", "fabric_task.py", "remote_sub.sh",
                             "lease_broker.py", "quota_circuit.py")},
            "route_selected_before_cooldown": self.selected_before_cooldown,
            "cooldown_observation": self.observation,
            "route_calls_before_controller_return": route_calls_at_return,
            "native_controller_calls": len(self.native_calls),
            "controller_rc": rc, "origin_status": status, "continuation": view,
            "contender_lease_count": contender_leases, "ssh_scp_rsync_calls": 0,
            "fresh_route_after_return": self.route_calls[-1],
            "native_log": log,
            "broker_calls": [json.loads(line) for line in (self.root / "broker-calls.jsonl").read_text().splitlines()],
            "broker_returns": [json.loads(line) for line in (self.root / "broker-returns.jsonl").read_text().splitlines()],
        }
        (SOURCE / "PRELEASE_FIXED_OBSERVED.json").write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
        # The fixed owner must create a fresh route after the exact prelease
        # quota handoff. The alternate is deliberately stopped by an inert
        # fixture gate, so this proves no provider or remote task execution.
        self.assertGreaterEqual(len(route_calls_at_return), 2,
            "a broker-owned no-lease quota refusal stranded the selected commission while GLM remained available")

    def test_refusal_needs_exact_original_return_source_route_and_packet(self):
        rc = api.request("origin", "mechanical", cwd="~", packet=None,
            stdin_bytes=b"PONG-only inert task\n", root_id="root",
            parent_run_id="parent", task_complexity="C0_MECHANICAL",
            request_capacity_preflight=True, request_remaining_seconds=60,
            request_deadline_ns=time.monotonic_ns() + 60_000_000_000)
        self.assertEqual(rc, 75, self.native_returns[-1].stderr if self.native_returns else "no native return")
        status = api.inspect_run("origin")
        self.assertEqual((status["root_id"], status["parent_run_id"]), ("root", "parent"))
        self.assertTrue(status["execution_absence_proven"])
        proof = fabric_continuation.eligible(api, self.root, "origin", "root", "parent")
        self.assertEqual(proof["kind"], "prelease_quota_cooldown")
        returned = self.path("origin", ".request-return.json")
        return_bytes = returned.read_bytes()
        returned.unlink()
        try:
            self.assertEqual(api.inspect_run("origin")["state"], "SETTLING")
            with self.assertRaises(ValueError):
                fabric_continuation.eligible(api, self.root, "origin", "root", "parent")
        finally:
            returned.write_bytes(return_bytes)

        cases = (
            (".request-return.json", lambda value: value.update(controller_rc=0)),
            (".prelease-quota.json", lambda value: value.update(task_cli_started=True)),
            (".prelease-quota.json", lambda value: value.update(lease_granted=True)),
            (".prelease-quota.json", lambda value: value.update(root_id="different-root")),
            (".prelease-quota.json", lambda value: value["native_sources"].update(
                **{"remote_sub.sh": "0" * 64})),
            (".request-launch.json", lambda value: value["route"].update(HOST="different-host")),
            (".prelease-quota.json", lambda value: value["blockade"]["accounts"][0].update(kind="auth")),
        )
        for suffix, change in cases:
            with self.subTest(suffix=suffix, change=change):
                path = self.path("origin", suffix)
                original = path.read_bytes()
                try:
                    value = json.loads(original)
                    change(value)
                    path.write_text(json.dumps(value))
                    self.assertEqual(api.inspect_run("origin")["state"], "STATUS_UNREADABLE")
                    with self.assertRaises(ValueError):
                        fabric_continuation.eligible(api, self.root, "origin", "root", "parent")
                finally:
                    path.write_bytes(original)
        for suffix in (".request.packet", ".log"):
            with self.subTest(suffix=suffix):
                path = self.path("origin", suffix)
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed\n")
                    self.assertEqual(api.inspect_run("origin")["state"], "STATUS_UNREADABLE")
                    with self.assertRaises(ValueError):
                        fabric_continuation.eligible(api, self.root, "origin", "root", "parent")
                finally:
                    path.write_bytes(original)
        # A coherent digest is integrity, not permission to override sticky
        # execution uncertainty or evidence that this invocation already ran.
        log_path = self.path("origin", ".log")
        log_original = log_path.read_bytes()
        for marker in (*quota_circuit.PRELEASE_UNCERTAINTY_MARKERS,
                       "LEASE_OK pool=minimax", "LAUNCH stdout=remote"):
            with self.subTest(bound_contradiction=marker):
                try:
                    raw = log_original + marker.encode() + b"\n"
                    log_path.write_bytes(raw)
                    value = json.loads(return_bytes)
                    value["log_sha256"] = provider_outcome.digest(raw)
                    returned.write_text(json.dumps(value))
                    expected = "EFFECT_UNKNOWN" if marker in quota_circuit.PRELEASE_UNCERTAINTY_MARKERS else "STATUS_UNREADABLE"
                    self.assertEqual(api.inspect_run("origin")["state"], expected)
                    with self.assertRaises(ValueError):
                        fabric_continuation.eligible(api, self.root, "origin", "root", "parent")
                    with self.assertRaises(ValueError):
                        quota_circuit.validate_prelease_refusal(self.root, "origin", "root", "parent")
                finally:
                    log_path.write_bytes(log_original)
                    returned.write_bytes(return_bytes)
        for path in (api._paths("origin")[1], self.path("origin", ".process.jsonl"),
                     self.path("origin", ".support.json")):
            with self.subTest(contradictory_artifact=path.name):
                path.write_text("retained execution evidence\n")
                try:
                    self.assertEqual(api.inspect_run("origin")["state"], "STATUS_UNREADABLE")
                    with self.assertRaises(ValueError):
                        fabric_continuation.eligible(api, self.root, "origin", "root", "parent")
                finally:
                    path.unlink()
        self.assertEqual(len(self.native_calls), 1)
        self.assertFalse((self.root / "forbidden-transport.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
