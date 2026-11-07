"""Concrete carrier recovery and source-publication regressions.

Only synthetic owner modules and harmless local children execute. These tests
do not enroll a production profile or exercise an account/provider credential.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "candidate"), str(ROOT / "source")]
import native_remote
import support_bundle
from test_remote_sub_application_carrier import ApplicationFixture, OWNER_NAME


def injected_run(fixture, run, envelope, setup):
    path = fixture.root / (run + ".dispatch.json")
    path.write_text(json.dumps(envelope))
    script = ("import sys, os, json, stat, dataclasses\n"
              "sys.path.insert(0, " + repr(str(fixture.ext)) + ")\n"
              "import remote_sub_exec as remote\n" + setup + "\n"
              "raise SystemExit(remote.main(sys.argv[1:]))\n")
    return subprocess.run(
        [sys.executable, "-c", script, str(fixture.ext / "remote_sub_exec.py"),
         run, "application", str(path), "~", envelope["model"]],
        env=fixture.env(), capture_output=True, timeout=60)


class ApplicationCarrierRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, **kwargs):
        return ApplicationFixture(self.root, **kwargs)

    def test_original_duration_and_absolute_expiry_include_owner_binding(self):
        slow_owner = """
import time
_original_bind = application_owner_bind
def application_owner_bind(*args, **kwargs):
    time.sleep(1.2)
    return _original_bind(*args, **kwargs)
"""
        for label, duration, expiry in (("duration", 1, 600), ("expiry", 300, 1)):
            with self.subTest(label=label):
                root = self.root / label
                root.mkdir()
                fixture = ApplicationFixture(root, owner_extra=slow_owner)
                envelope = fixture.envelope("budget-" + label, remaining_seconds=duration)
                envelope["expires_at"] = envelope["issued_at"] + expiry
                envelope["invocation_digest"] = native_remote.application_invocation_digest(
                    envelope, fixture.argv, fixture.cwd)
                result = fixture.run("budget-" + label, envelope)
                self.assertEqual(result.returncode, 78, result.stderr.decode())
                self.assertIn(b"APPLICATION_EXPIRED", result.stderr)
                self.assertFalse((fixture.lanes() / ("budget-" + label + ".process.jsonl")).exists())

    def test_prepare_file_and_directory_fsync_failures_never_launch_or_relaunch(self):
        for kind in ("file", "directory"):
            with self.subTest(kind=kind):
                root = self.root / kind
                root.mkdir()
                fixture = ApplicationFixture(root)
                run = "barrier-" + kind
                envelope = fixture.envelope(run)
                setup = """
_real_record = remote._write_application_record
def fail_record(path, value):
    _fsync = remote.os.fsync
    def fail_selected(fd):
        directory = stat.S_ISDIR(os.fstat(fd).st_mode)
        if directory == WANT_DIRECTORY:
            raise OSError("synthetic fsync interruption")
        return _fsync(fd)
    remote.os.fsync = fail_selected
    try:
        return _real_record(path, value)
    finally:
        remote.os.fsync = _fsync
remote._write_application_record = fail_record
""".replace("WANT_DIRECTORY", repr(kind == "directory"))
                first = injected_run(fixture, run, envelope, setup)
                self.assertEqual(first.returncode, 78, first.stderr.decode())
                self.assertTrue((fixture.lanes() / (run + ".application-prepare.json")).exists())
                self.assertFalse((fixture.lanes() / (run + ".process.jsonl")).exists())
                again = fixture.run(run, envelope)
                self.assertEqual(again.returncode, 75, again.stderr.decode())
                self.assertFalse((fixture.lanes() / (run + ".process.jsonl")).exists())

    def test_truncated_zero_exit_remains_held_on_every_replay(self):
        fixture = self.fixture(child="import sys;sys.stdin.read();sys.stdout.write('x'*100000)")
        run = "truncated-original"
        envelope = fixture.envelope(run)
        first = fixture.run(run, envelope)
        self.assertEqual(first.returncode, 76, first.stderr.decode())
        value = fixture.terminal(run)
        self.assertEqual(value["returncode"], 0)
        self.assertEqual(value["status"], "incomplete")
        self.assertFalse(value["output_complete"])
        receipt = (fixture.lanes() / (run + ".process.jsonl")).read_bytes()
        again = fixture.run(run, envelope)
        self.assertEqual(again.returncode, 76, again.stderr.decode())
        self.assertEqual((fixture.lanes() / (run + ".process.jsonl")).read_bytes(), receipt)

    def test_unproven_cleanup_zero_exit_remains_held_on_every_replay(self):
        fixture = self.fixture()
        run = "cleanup-original"
        envelope = fixture.envelope(run)
        setup = """
_real_run = remote.run_owned_process
def unproven(*args, **kwargs):
    result = _real_run(*args, **kwargs)
    cleanup = dict(result.cleanup)
    cleanup.update(status="process_census_unproven", identity_verified=False,
                   census_proven=False, residual_count=None, error_code="synthetic_census_unknown")
    path = kwargs["receipt_path"]
    row = json.loads(path.read_text().splitlines()[-1])
    row["cleanup"] = cleanup
    path.write_text(json.dumps(row) + "\\n")
    return dataclasses.replace(result, cleanup=cleanup)
remote.run_owned_process = unproven
"""
        first = injected_run(fixture, run, envelope, setup)
        self.assertEqual(first.returncode, 76, first.stderr.decode())
        terminal = fixture.terminal(run)
        self.assertEqual(terminal["returncode"], 0)
        self.assertEqual(terminal["status"], "effect_unknown")
        self.assertFalse(terminal["cleanup_proven"])
        receipt = (fixture.lanes() / (run + ".process.jsonl")).read_bytes()
        again = fixture.run(run, envelope)
        self.assertEqual(again.returncode, 76, again.stderr.decode())
        self.assertEqual((fixture.lanes() / (run + ".process.jsonl")).read_bytes(), receipt)

    def test_changed_carrier_key_account_or_host_cannot_launch(self):
        fixture = self.fixture()
        run = "bound-original"
        envelope = fixture.envelope(run)
        first = fixture.run(run, envelope)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        changed_key = fixture.run("different-carrier", envelope)
        self.assertEqual(changed_key.returncode, 78, changed_key.stderr.decode())
        self.assertFalse((fixture.lanes() / "different-carrier.process.jsonl").exists())
        for key, value in (("account", "other-account"), ("host", "other-host")):
            other = "wrong-" + key
            changed = fixture.envelope(other, **{key: value})
            result = fixture.run(other, changed)
            self.assertEqual(result.returncode, 78, result.stderr.decode())
            self.assertFalse((fixture.lanes() / (other + ".process.jsonl")).exists())
        wrong_route = fixture.envelope("wrong-route", host="other-host")
        routed = fixture.run_controller("wrong-route", wrong_route)
        self.assertEqual(routed.returncode, 78, routed.stderr.decode())
        self.assertIn(b"APPLICATION_ROUTE_SCOPE_REFUSED", routed.stderr)

    def test_terminal_corruption_and_contradictions_refuse_without_new_process(self):
        fixture = self.fixture()
        run = "terminal-original"
        envelope = fixture.envelope(run)
        first = fixture.run(run, envelope)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        path = fixture.lanes() / (run + ".application-terminal.json")
        original = fixture.terminal(run)
        receipt = (fixture.lanes() / (run + ".process.jsonl")).read_bytes()
        mutations = (
            lambda x: x.update(status="failed"),
            lambda x: x.update(status=["completed"]),
            lambda x: x.update(returncode=False),
            lambda x: x.update(usage={}),
            lambda x: x.update(provider_settled=True),
            lambda x: x.update(output_complete=False),
            lambda x: x["cleanup"].update(residual_count=False),
            lambda x: x["cleanup"].update(census_proven=False),
            lambda x: x["process"].update(pid=str(x["process"]["pid"])),
            lambda x: x["process"].update(receipt_returncode=7),
            lambda x: x["capture"].update(stdout_sha256="f"*64),
            lambda x: x["capture"].update(stdout_bytes=x["capture"]["stdout_bytes"]+1),
            lambda x: x["capture"].update(stdout_complete=False),
            lambda x: x["capture"].update(unrecognized=True),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                value = copy.deepcopy(original)
                mutate(value)
                path.write_text(json.dumps(value))
                again = fixture.run(run, envelope)
                self.assertEqual(again.returncode, 76, again.stderr.decode())
                self.assertEqual((fixture.lanes() / (run + ".process.jsonl")).read_bytes(), receipt)

    def test_actual_publisher_keeps_worker_and_application_memberships_distinct(self):
        fixture = self.fixture()
        files = json.loads((fixture.root / "support.json").read_text())
        self.assertEqual(frozenset(files), support_bundle.APPLICATION_SOURCE_FILES)
        self.assertNotIn(OWNER_NAME, support_bundle.SOURCE_FILES)
        worker = {k: v for k, v in files.items() if k != OWNER_NAME}
        self.assertEqual(frozenset(worker), support_bundle.SOURCE_FILES)
        published = support_bundle.publish(fixture.controller, fixture.stable, worker)
        self.assertNotEqual(published.parent.name, fixture.support_digest)
        self.assertFalse((published / OWNER_NAME).exists())
        invalid = dict(files, unqualified_member="0"*64)
        with self.assertRaises(ValueError):
            support_bundle.publish(fixture.controller, fixture.stable, invalid)

    def test_m2_uses_the_same_application_executor_and_receipt_path(self):
        fixture = self.fixture(host="m2")
        run = "m2-application"
        result = fixture.run_controller(run, fixture.envelope(run))
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        terminal = fixture.terminal(run)
        self.assertEqual(terminal["status"], "completed")
        self.assertEqual(terminal["host"], "m2")
        self.assertEqual(terminal["process"]["label"], run)


if __name__ == "__main__":
    unittest.main()
