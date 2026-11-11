"""Real temporary admin enrollment/status/Paper/forward lifecycle qualification."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc
import private_service_status_successor as status
import private_service_status_successor_test as history_fixture
import private_service_pin_forward_recovery_test as forward_fixture
import private_service_pin_transition_test as transition_fixture


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


class AdminV22ForwardTests(unittest.TestCase):
    capture = transition_fixture.ForwardPinTransitionTests.capture
    forward_context = transition_fixture.ForwardPinTransitionTests.forward_context
    invoke = transition_fixture.ForwardPinTransitionTests.invoke
    prepare = transition_fixture.ForwardPinTransitionTests.prepare

    def patch(self, target, name, value):
        p = mock.patch.object(target, name, value)
        p.start()
        self.addCleanup(p.stop)

    def setUp(self):
        prior_umask = os.umask(0o077)
        self.addCleanup(os.umask, prior_umask)
        self.case = history_fixture.EnrolledRetainedReceiptTests(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.account = "admin-business"
        with contextlib.redirect_stdout(io.StringIO()):
            self.fixture = self.case.build(self.account)
            args = self.fixture["args"]
            args.operation = "apply"
            args.expected_plan_sha256 = self.fixture["successor_plan_sha"]
            self.assertEqual(status.run(svc, args)["effect"], "APPLIED")
        self.roots = self.fixture["roots"]
        self.home = svc._user_root()
        self.runtime_rel = Path(".local/share/mastermind-paper/runtime/v22")
        self.runtime = self.home / self.runtime_rel
        self.runtime.mkdir(parents=True, mode=0o700)
        (self.runtime / "source").mkdir(parents=True, mode=0o700)
        (self.runtime / "venv/bin").mkdir(parents=True, mode=0o700)
        # External reviewed-source identity is inert; the actual runtime
        # verifier, history owners and filesystem checks remain in use.
        self.bridge_bytes = b"# reviewed v22 fixture bridge\n"
        self.bridge_sha = hashlib.sha256(self.bridge_bytes).hexdigest()
        self.bridge = self.runtime / "source/bridge.py"
        self.bridge.write_bytes(self.bridge_bytes)
        self.bridge.chmod(0o600)
        self.python = self.runtime / "venv/bin/python"
        self.python.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.python.chmod(0o700)
        self.runtime_receipt = self.runtime / "RUNTIME.json"
        self.runtime_receipt.write_bytes(encoded({
            "schema": "mastermind.paper_runtime.v1",
            "generation": "v22",
            "bridge_sha256": self.bridge_sha,
            "source_sha256": {"bridge.py": self.bridge_sha},
            "network_install_performed": False,
            "production_acceptance": False,
        }))
        self.runtime_receipt.chmod(0o600)
        # create=True keeps the pre-repair red test executable.
        patch = mock.patch.object(svc, "PAPER_RUNTIME_V22_BRIDGE_SHA256",
                                  self.bridge_sha, create=True)
        patch.start()
        self.addCleanup(patch.stop)
        before_config = self.roots["config"].read_bytes()
        before_manifest = self.roots["manifest"].read_bytes()
        config = json.loads(before_config)
        paper = svc._paper_design_config(
            self.home, rel=self.runtime_rel, bridge_sha256=self.bridge_sha)
        for key in ("bridgePath", "bridgeSha256", "pythonPath"):
            config["paperDesign"][key] = paper[key]
        after_config = encoded(config)
        manifest = json.loads(before_manifest)
        manifest["configHash"] = hashlib.sha256(after_config).hexdigest()
        self.roots["config"].write_bytes(after_config)
        self.roots["manifest"].write_bytes(encoded(manifest))
        self.paper_pair = {
            name: self.roots[name].read_bytes() for name in ("config", "manifest")
        }
        self.histories = {
            name: {p.name: p.read_bytes() for p in (self.roots["state"] / name).iterdir()}
            for name in ("native-pool-pin", "native-pool-pin-enrollment",
                         "fleet-status-module-successor")
        }
        self.new_pool = b"qualified-admin-v22-forward-bridge"
        self.binding = forward_fixture.binding_for_existing(self.roots, self.new_pool)
        Path(self.binding["original_successor"]["successor_bundle"]).mkdir(
            parents=True, exist_ok=True, mode=0o700)
        self.args = SimpleNamespace(
            account=self.account, forward_go_bundle=str(self.home / "qualified-go"),
            expected_plan_sha256=None, operation="preview")

    @property
    def tx(self):
        return self.roots["state"] / "native-pool-pin-forward"

    def selected(self):
        self.prepare()
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        Path(self.binding["pool_target"]).write_bytes(self.new_pool)
        self.binding["phase"] = "SELECTED"

    def start(self):
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            return self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))

    def assert_histories_unchanged(self):
        for name, expected in self.histories.items():
            self.assertEqual(expected, {
                p.name: p.read_bytes() for p in (self.roots["state"] / name).iterdir()
            })

    def test_admin_enrollment_status_v22_forward_and_start_preserve_history(self):
        self.selected()
        self.assertTrue(self.start()["started"])
        self.assertTrue(any(call[:2] == ["launchctl", "bootstrap"]
                            for call in self.fixture["calls"]))
        self.assert_histories_unchanged()
        self.assertNotEqual(self.roots["config"].read_bytes(), self.paper_pair["config"])

    def test_exact_v22_runtime_retains_existing_verifier_and_rejects_wrong_hash(self):
        svc._verify_paper_runtime(
            self.home, runtime_rel=self.runtime_rel, rel=self.runtime_rel,
            expected_sha=self.bridge_sha)
        with self.assertRaises(SystemExit):
            svc._verify_paper_runtime(
                self.home, runtime_rel=self.runtime_rel, rel=self.runtime_rel,
                expected_sha="0" * 64)
        self.python.chmod(0o600)
        with self.assertRaises(SystemExit):
            svc._verify_paper_runtime(
                self.home, runtime_rel=self.runtime_rel, rel=self.runtime_rel,
                expected_sha=self.bridge_sha)

    def test_other_config_or_manifest_change_refuses_before_forward_write(self):
        for field in ("requestTimeoutMs", "manifest"):
            with self.subTest(field=field):
                before = dict(self.paper_pair)
                try:
                    if field == "manifest":
                        m = json.loads(before["manifest"])
                        m["source"] = "/foreign/source"
                        self.roots["manifest"].write_bytes(encoded(m))
                    else:
                        c = json.loads(before["config"])
                        c[field] = c.get(field, 0) + 1
                        data = encoded(c)
                        m = json.loads(before["manifest"])
                        m["configHash"] = hashlib.sha256(data).hexdigest()
                        self.roots["config"].write_bytes(data)
                        self.roots["manifest"].write_bytes(encoded(m))
                    with mock.patch.object(svc, "_atomic_write_bytes",
                                           side_effect=AssertionError("unexpected write")):
                        with self.assertRaises(SystemExit):
                            self.invoke()
                    self.assertFalse(self.tx.exists())
                finally:
                    for name, data in before.items():
                        self.roots[name].write_bytes(data)
        self.assert_histories_unchanged()

    def test_each_original_completion_receipt_remains_required(self):
        for history in self.histories:
            with self.subTest(history=history):
                target = self.roots["state"] / history / "result.json"
                original = target.read_bytes()
                try:
                    target.write_bytes(b"{}")
                    with self.assertRaises(SystemExit):
                        self.invoke()
                    self.assertFalse(self.tx.exists())
                finally:
                    target.write_bytes(original)

    def test_runtime_change_and_symlink_refuse_after_complete_forward(self):
        self.selected()
        self.bridge.write_bytes(b"foreign bridge")
        with self.assertRaises(SystemExit):
            self.start()
        self.bridge.write_bytes(self.bridge_bytes)
        self.python.unlink()
        self.python.symlink_to("/bin/sh")
        with self.assertRaises(SystemExit):
            self.start()
        self.assertFalse(any(call[:2] == ["launchctl", "bootstrap"]
                             for call in self.fixture["calls"]))

    def test_missing_forward_completion_cannot_fall_back_to_status_start(self):
        self.selected()
        (self.tx / "result.json").unlink()
        with self.assertRaises(SystemExit):
            self.start()
        self.assertFalse(any(call[:2] == ["launchctl", "bootstrap"]
                             for call in self.fixture["calls"]))

    def test_config_only_interruption_uses_original_forward_reconcile(self):
        self.prepare()
        actual = svc._atomic_write_bytes
        def interrupted(path, data, mode=0o600):
            actual(path, data, mode=mode)
            if Path(path) == self.roots["config"]:
                raise OSError("inert interruption after config")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=interrupted):
            with self.assertRaises(SystemExit):
                self.invoke()
        retained = (self.tx / "plan.json").read_bytes()
        self.args.operation = "reconcile"
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.assertEqual((self.tx / "plan.json").read_bytes(), retained)
        self.assert_histories_unchanged()


if __name__ == "__main__":
    unittest.main()
