"""Original-receipt qualification; no live run, provider, result or lease access."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE / "candidate"), str(SOURCE / "source")]
import artifact_delivery
import lane_runtime
import pool_ledger
import remote_sub_helpers

historical = {}
for name in ("a04_terminal_reconcile", "native_completion_reconcile", "native_prestart_reconcile",
             "native_preexec_reconcile", "native_host_review_controller_reconcile"):
    module = ModuleType(name)
    module.RUN = module.RUN_ID = "unavailable-historical-fixture"
    module.KNOWN_RUNS = ()
    historical[name] = module
spec = importlib.util.spec_from_file_location("completed_poll_adapter", SOURCE / "candidate/fabric_task.py")
api = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, historical):
    spec.loader.exec_module(api)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()


def cleanup():
    return {"census_proven": True, "identity_verified": True, "residual_count": 0,
            "status": "not_needed", "reason": "normal_completion", "sigterm_sent": False,
            "sigkill_sent": False, "error_code": None, "stdout_capture_complete": True,
            "stderr_capture_complete": True, "stdin_delivery_complete": True,
            "stdout_capture_error": None, "stderr_capture_error": None, "stdin_delivery_error": None}


def process(label, rc, pid, start, end, output=b""):
    return {"schema": "mastermind.local_owned_process_receipt.v1", "label": label,
            "pid": pid, "pgid": pid, "started_at": f"2026-11-05T12:00:{start:02d}.000Z",
            "ended_at": f"2026-11-05T12:00:{end:02d}.000Z", "returncode": rc,
            "timed_out": False, "nice_requested": None, "nice_applied": False,
            "stdout_bytes": len(output), "stdout_sha256": digest(output), "stderr_bytes": 0,
            "stdout_truncated": False, "stderr_truncated": False,
            "runtime_failure_code": None, "cleanup": cleanup()}


class CompletedPollReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="completed-poll-",
            dir=os.environ.get("NATIVE_ROLLOUT_TEST_ROOT", str(SOURCE / "tests")))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.ext = self.root / "ext"
        self.state = self.ext / "state/remote_sub"
        self.state.mkdir(parents=True, mode=0o700)
        self.ledger = self.root / "orch/fabric/ledger.jsonl"
        self.ledger.parent.mkdir(parents=True, mode=0o700)
        (self.ext / "lanes").mkdir(mode=0o700)
        self.rid = "offline-original-completed-poll"
        self.root_id = "unrelated-fixture-root"
        self.parent = "unrelated-fixture-parent"
        self.packet = b"Inert original request; no worker may start.\n"
        self.request = {"schema": "mastermind.fabric_request_artifact.v1", "run_id": self.rid,
            "root_id": self.root_id, "parent_run_id": self.parent, "task_class": "mechanical",
            "cwd": "~", "packet": self.rid + ".request.packet", "packet_bytes": len(self.packet),
            "packet_sha256": digest(self.packet), "created_at": 1000.0,
            "automatic_background_execution": False}
        self.route = {"ESCALATE_TO": "glm-flash", "HOST": "fixture", "KEY": "-",
            "MODE": "minimax", "MODEL": "fixture-model", "POOL": "minimax", "REASON": "minimax_first"}
        self.launch = {"schema": "mastermind.fabric_request_launch.v1", "run_id": self.rid,
            "root_id": self.root_id, "parent_run_id": self.parent, "packet_sha256": digest(self.packet),
            "state": "LAUNCH_ATTEMPT_RESERVED", "created_at": 1001.0, "request_sha256": "",
            "capacity_handoff": True, "route": self.route,
            "native_sources": {"remote_sub.sh": "e24d6123ae1c303fe7a72b88c9ae6093979dcf35a9984d7ba16ccb9689700b05",
                "lease_broker.py": "a" * 64, "quota_circuit.py": "b" * 64}}
        self.returned = {"schema": "mastermind.fabric_request_return.v1", "run_id": self.rid,
            "root_id": self.root_id, "parent_run_id": self.parent, "state": "NATIVE_CONTROLLER_RETURNED",
            "controller_rc": 0, "request_sha256": "", "launch_sha256": "", "log_sha256": "",
            "prelease_sha256": None}
        self.worker = process(self.rid, 0, 9001, 2, 5, b"inert worker answer\n")
        self.controllers = [process("commission-launch", 0, 1001, 0, 1),
            process("commission-poll", 255, 1002, 3, 4),
            process("commission-poll", 0, 1003, 6, 7, b"0\n")]
        self.provider = {"schema": "mastermind.provider_outcome.v1", "run_id": self.rid,
            "root_id": self.root_id, "host": "fixture", "model": "fixture-model", "provider": "minimax",
            "kind": "success", "cli_subtype": "success", "cli_terminal_reason": "completed",
            "command_rc": 0, "cli_command_rc": 0, "complete_event_capture": True,
            "initial_rejection": False, "permission_denial_count": 0, "permission_denials_role": "none",
            "lease_id": "123456789abc", "account": "default", "stdout_sha256": self.worker["stdout_sha256"]}
        self.events = ["RUN_RESERVED explicit=1", "LEASE_OK pool=minimax",
            f"LAUNCH stdout=lanes_{self.rid}.stdout rc_file=ext/lanes_{self.rid}.rc cwd=~",
            "LAUNCH_ATTEMPT attempt=1", f"POLL 1/60 elapsed=1 file=/fixture/ext/lanes_{self.rid}.rc",
            "CONTROLLER_PROCESS_UNPROVEN stage=poll rc=255", "POLL_TRANSPORT_FAILED rc=255 poll=1",
            f"POLL 2/60 elapsed=2 file=/fixture/ext/lanes_{self.rid}.rc", "RC value=0 poll=2",
            "REMOTE_DONE rc=0", f"PROCESS_RECEIPT_SAVED file={self.rid}.process.jsonl", "USAGE_RECEIPT_MISSING",
            f"PROVIDER_OUTCOME_RECORDED file={self.rid}.provider.json",
            "REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=0", "DONE rc=0 signal=ok",
            "LEASE_PRESERVED effect_unknown=1 lease=123456789abc"]
        self.terminal = {"ts": 1002, "run_id": self.rid, "root_id": self.root_id,
            "parent_run_id": self.parent, "pool": "minimax", "key": "default", "window_id": "fixture",
            "task_class": "mechanical", "model": "fixture-model", "rc": 0, "signal": "ok"}
        self.publish()

    def write(self, suffix, raw):
        path = self.state / (self.rid + suffix)
        path.write_bytes(raw)
        path.chmod(0o600)

    def publish(self):
        self.log = "".join(f"2026-11-05T12:00Z [remote_sub id={self.rid} host=fixture] {e}\n"
                           for e in self.events).encode()
        self.launch["request_sha256"] = digest(encoded(self.request))
        self.returned.update(request_sha256=digest(encoded(self.request)),
            launch_sha256=digest(encoded(self.launch)), log_sha256=digest(self.log))
        for suffix, raw in {
            ".request.json": encoded(self.request), ".request-launch.json": encoded(self.launch),
            ".request-return.json": encoded(self.returned), ".request.packet": self.packet,
            ".log": self.log, ".process.jsonl": encoded(self.worker),
            ".controller-process.jsonl": b"".join(encoded(r) for r in self.controllers),
            ".provider.json": encoded(self.provider),
        }.items():
            self.write(suffix, raw)
        self.ledger.write_bytes(encoded(self.terminal))
        self.ledger.chmod(0o600)

    def qualifies(self):
        return api._qualify_completed_poll255(self.rid, self.log, owner_ext=self.ext)

    def test_complete_original_chain_is_read_only_and_run_independent(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        original_open = os.open
        def readonly(path, flags, *a, **kw):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            self.assertNotIn("remote.stdout", str(path))
            self.assertNotIn("capture", str(path))
            return original_open(path, flags, *a, **kw)
        with ExitStack() as stack:
            stack.enter_context(patch.object(os, "open", side_effect=readonly))
            stack.enter_context(patch.object(os, "write", side_effect=AssertionError("write forbidden")))
            stack.enter_context(patch.object(api.subprocess, "run", side_effect=AssertionError("process forbidden")))
            stack.enter_context(patch.object(api.subprocess, "Popen", side_effect=AssertionError("process forbidden")))
            stack.enter_context(patch.object(api, "_result_snapshot", side_effect=AssertionError("result forbidden")))
            self.assertTrue(self.qualifies())
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_status_uses_ordinary_not_accepted_projection(self):
        result = self.ext / "lanes" / (self.rid + ".remote.stdout")
        result.write_text("inert worker answer\n")
        result.chmod(0o600)
        status = api.inspect_run(self.rid, owner_ext=self.ext)
        self.assertEqual((status["state"], status["rc"], status["signal"]), ("TERMINAL", 0, "ok"))
        self.assertIs(status["accepted"], False)
        self.assertIsNone(status["accepted_by"])
        self.assertEqual(status["acceptance_state"], "NOT_ACCEPTED")
        self.assertNotIn("result_consumption_authorized", status)
        self.assertEqual((status["root_id"], status["parent_run_id"]), (self.root_id, self.parent))

    def test_each_original_file_is_required(self):
        for path in list(self.state.iterdir()):
            with self.subTest(suffix=path.suffix):
                raw = path.read_bytes(); path.unlink()
                self.assertFalse(self.qualifies())
                path.write_bytes(raw); path.chmod(0o600)

    def test_original_chain_mutations_stay_unknown(self):
        mutations = [("returned", "controller_rc", False), ("returned", "controller_rc", 76),
            ("returned", "root_id", "foreign-root"), ("launch", "parent_run_id", "foreign-parent"),
            ("returned", "prelease_sha256", "c" * 64), ("request", "packet", "../foreign.packet"),
            ("request", "packet_bytes", True), ("launch", "capacity_handoff", False)]
        for target, key, value in mutations:
            with self.subTest(target=target, key=key, value=value):
                obj = getattr(self, target); before = obj[key]; obj[key] = value; self.publish()
                self.assertFalse(self.qualifies()); obj[key] = before; self.publish()
        for suffix in (".request.json", ".request-launch.json", ".request-return.json", ".request.packet", ".log"):
            with self.subTest(drift=suffix):
                path = self.state / (self.rid + suffix); before = path.read_bytes()
                self.write(suffix, before + b" "); self.assertFalse(self.qualifies()); self.write(suffix, before)

    def test_unknown_wrapper_or_foreign_route_stays_unknown(self):
        for target, key, value in ((self.launch["native_sources"], "remote_sub.sh", "f" * 64),
                                  (self.route, "HOST", "foreign"), (self.route, "MODE", "glm")):
            before = target[key]; target[key] = value; self.publish()
            self.assertFalse(self.qualifies()); target[key] = before; self.publish()

    def test_process_and_provider_negatives(self):
        mutations = [("returncode", False), ("returncode", 76), ("timed_out", True),
            ("stdout_truncated", True), ("stderr_truncated", True), ("runtime_failure_code", "interrupted"),
            ("pid", True), ("stdout_sha256", "0" * 64)]
        for key, value in mutations:
            with self.subTest(process=key):
                before = self.worker[key]; self.worker[key] = value; self.publish()
                self.assertFalse(self.qualifies()); self.worker[key] = before; self.publish()
        for key, value in (("residual_count", False), ("residual_count", 1), ("status", "terminated"),
                           ("sigterm_sent", True), ("stdin_delivery_complete", False),
                           ("stdout_capture_complete", False), ("stderr_capture_error", "capture_error")):
            with self.subTest(cleanup=key):
                before = self.worker["cleanup"][key]; self.worker["cleanup"][key] = value; self.publish()
                self.assertFalse(self.qualifies()); self.worker["cleanup"][key] = before; self.publish()
        for key, value in (("root_id", "foreign"), ("host", "foreign"), ("model", "foreign"),
                           ("lease_id", "ffffffffffff"), ("command_rc", False), ("kind", "unknown"),
                           ("complete_event_capture", False), ("permission_denial_count", 1)):
            with self.subTest(provider=key):
                before = self.provider[key]; self.provider[key] = value; self.publish()
                self.assertFalse(self.qualifies()); self.provider[key] = before; self.publish()

    def test_launch_failure_interruption_and_unmatched_poll_stay_unknown(self):
        original = deepcopy(self.controllers)
        for changed in ((0, "returncode", 255), (1, "returncode", 76), (1, "returncode", 0),
                        (1, "stdout_bytes", 1), (2, "stdout_sha256", "f" * 64)):
            index, key, value = changed; self.controllers[index][key] = value; self.publish()
            self.assertFalse(self.qualifies()); self.controllers = deepcopy(original)
        for rows in (original[1:], original[:1] + original[2:], original + [original[-1]],
                     [original[1], original[0], original[2]]):
            self.controllers = deepcopy(rows); self.publish(); self.assertFalse(self.qualifies())
        self.controllers = original; self.publish()

    def test_extra_launch_uncertainty_or_incomplete_terminal_stays_unknown(self):
        original = self.events[:]
        for extra in ("LAUNCH_ATTEMPT attempt=2", "CONTROLLER_PROCESS_UNPROVEN stage=launch rc=255",
                      "CONTROLLER_PROCESS_UNPROVEN stage=poll rc=76", "RESULT_UNAVAILABLE worker_rc=0",
                      "ADMISSION_RETRY same_run=1 same_host=1 next_attempt=2",
                      "SETTLEMENT signal=effect_unknown", "POLL_TRANSPORT_FAILED rc=255 poll=1",
                      "POLL_PENDING poll=1", "RC value=0 poll=2"):
            self.events = original[:4] + [extra] + original[4:]; self.publish(); self.assertFalse(self.qualifies())
        for index in (5, 6, 8, 9, 10, 12, 13, 14, 15):
            self.events = original[:index] + original[index + 1:]; self.publish(); self.assertFalse(self.qualifies())
        self.events = original; self.publish()

    def test_hash_bound_log_cannot_change_original_cwd(self):
        self.events[2] = self.events[2].replace("cwd=~", "cwd=/another/tree")
        self.publish()
        self.assertFalse(self.qualifies())

    def test_duplicate_keys_and_duplicate_worker_receipts_refuse(self):
        for suffix in (".request.json", ".request-launch.json", ".request-return.json", ".provider.json"):
            path = self.state / (self.rid + suffix); before = path.read_bytes()
            self.write(suffix, b'{"schema":"duplicate",' + before[1:])
            self.assertFalse(self.qualifies()); self.write(suffix, before)
        self.write(".process.jsonl", encoded(self.worker) * 2)
        self.assertFalse(self.qualifies())

    def test_original_terminal_must_be_unique_matching_and_stable(self):
        original = encoded(self.terminal)
        for key, value in (("root_id", "foreign"), ("parent_run_id", "foreign"), ("rc", False), ("signal", "effect_unknown")):
            changed = {**self.terminal, key: value}; self.ledger.write_bytes(encoded(changed))
            self.assertFalse(self.qualifies())
        self.ledger.write_bytes(original * 2); self.assertFalse(self.qualifies())
        self.ledger.write_bytes(original + encoded({**self.terminal, "run_id": "unrelated-run"}))
        self.assertTrue(self.qualifies())
        self.ledger.write_bytes(original)
        reader = pool_ledger.read_execution_identity
        calls = []
        def drift(*a, **kw):
            result = reader(*a, **kw); calls.append(True)
            if len(calls) == 1:
                self.ledger.write_bytes(original + encoded({"kind": "outcome", "run_id": self.rid,
                    "ts": 1003, "accepted_by": None, "rc": 76}))
            return result
        with patch.object(pool_ledger, "read_execution_identity", side_effect=drift):
            self.assertFalse(self.qualifies())

    def test_receipt_replacement_mode_and_hardlinks_refuse(self):
        path = self.state / (self.rid + ".provider.json")
        path.chmod(0o620); self.assertFalse(self.qualifies()); path.chmod(0o600)
        link = self.root / "hardlink"; os.link(path, link)
        self.assertFalse(self.qualifies()); link.unlink()
        saved = self.root / "saved-provider"; path.rename(saved); path.symlink_to(saved)
        self.assertFalse(self.qualifies()); path.unlink(); saved.rename(path)
        reader = artifact_delivery.read_local_at
        changed = []
        def drift(chain, name, limit):
            data = reader(chain, name, limit)
            if name.endswith(".provider.json") and not changed:
                changed.append(True)
                self.write(".request.json", encoded(self.request) + b" ")
            return data
        with patch.object(artifact_delivery, "read_local_at", side_effect=drift):
            self.assertFalse(self.qualifies())


class FuturePollTransport(unittest.TestCase):
    def result(self, **change):
        fields = dict(returncode=255, stdout="", stderr="inert SSH error", timed_out=False,
            pid=1, pgid=1, cleanup=cleanup(), stdout_bytes=0, stderr_bytes=15,
            stdout_truncated=False, stderr_truncated=False)
        fields.update(change)
        return lane_runtime.OwnedProcessResult(**fields)

    def test_only_normal_readonly_poll255_is_an_ordinary_transport_failure(self):
        self.assertTrue(remote_sub_helpers._normal_poll_transport_failure("poll", self.result()))
        for stage in ("launch", "setup", "poll-sleep", "admission-read"):
            self.assertFalse(remote_sub_helpers._normal_poll_transport_failure(stage, self.result()))
        for change in ({"returncode": 76}, {"returncode": -15}, {"returncode": True},
                       {"timed_out": True}, {"stdout_truncated": True}, {"stderr_truncated": True},
                       {"stdout": "0\n", "stdout_bytes": 2}):
            self.assertFalse(remote_sub_helpers._normal_poll_transport_failure("poll", self.result(**change)))
        for key, value in (("residual_count", False), ("residual_count", 1), ("status", "terminated"),
                           ("reason", "interrupted"), ("sigkill_sent", True), ("stdout_capture_complete", False)):
            evidence = cleanup(); evidence[key] = value
            self.assertFalse(remote_sub_helpers._normal_poll_transport_failure("poll", self.result(cleanup=evidence)))


if __name__ == "__main__":
    unittest.main()
