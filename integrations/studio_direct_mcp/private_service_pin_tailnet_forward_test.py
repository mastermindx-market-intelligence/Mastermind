"""Preserving Go-forward proof for the two exact original Tailnet consumers."""
import copy
import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc
import private_service_pin_tailnet_protocol_test as tailnet_fixture
import private_service_pin_forward_recovery_test as forward_fixture
import private_service_pin_transition_test as transition_fixture


class TailnetForwardTests(unittest.TestCase):
    capture = transition_fixture.ForwardPinTransitionTests.capture
    forward_context = transition_fixture.ForwardPinTransitionTests.forward_context
    invoke = transition_fixture.ForwardPinTransitionTests.invoke
    prepare = transition_fixture.ForwardPinTransitionTests.prepare
    accounts = ("fabric-design", "fabric-read")

    def setUp(self):
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)

    @contextmanager
    def seat(self, account):
        with tailnet_fixture.tailnet_seat(account) as original:
            original.prepare()
            self.assertEqual(original.invoke()["effect"], "APPLIED")
            original.pool.write_bytes(original.future)
            original.binding["phase"] = "SELECTED"
            self.account, self.roots = account, original.roots
            self.home = svc._user_root()
            self.new_pool = b"qualified-tailnet-go-forward:" + account.encode()
            self.binding = forward_fixture.binding_for_existing(self.roots, self.new_pool)
            Path(self.binding["original_successor"]["successor_bundle"]).mkdir(
                parents=True, exist_ok=True, mode=0o700)
            self.args = SimpleNamespace(
                account=account, forward_go_bundle=str(self.home / "qualified-go"),
                expected_plan_sha256=None, operation="preview")
            before_config = json.loads(self.roots["config"].read_bytes())
            before_manifest = json.loads(self.roots["manifest"].read_bytes())
            future_config = copy.deepcopy(before_config)
            future_config["fleetStatus"]["fabricLauncherSha256"] = self.binding["pool_bridge"]
            future_manifest = copy.deepcopy(before_manifest)
            future_manifest["configHash"] = hashlib.sha256(
                svc._fabric_release_json(future_config)).hexdigest()
            # Replace only the external frozen profile identity with the
            # deterministic inert fixture target; actual verifiers stay real.
            canonical = dict(svc._NATIVE_POOL_PIN_TAILNET_CANONICAL)
            canonical[account] = frozenset((*canonical[account],
                svc._canonical_json_sha256(future_manifest)))
            self.original_history = {
                p.name: p.read_bytes() for p in
                (self.roots["state"] / "native-pool-pin").iterdir()
            }
            self.before_plist = self.roots["plist"].read_bytes()
            self.module_bytes = {
                name: (self.roots["base"] / name).read_bytes()
                for name in before_manifest["files"]
            }
            self.original = original
            with mock.patch.object(svc, "_NATIVE_POOL_PIN_TAILNET_CANONICAL", canonical):
                yield original

    @property
    def tx(self):
        return self.roots["state"] / "native-pool-pin-forward"

    def start(self):
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            return self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))

    def selected(self):
        self.prepare()
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        Path(self.binding["pool_target"]).write_bytes(self.new_pool)
        self.binding["phase"] = "SELECTED"

    def assert_preserved(self):
        self.assertEqual(self.original_history, {
            p.name: p.read_bytes() for p in
            (self.roots["state"] / "native-pool-pin").iterdir()
        })
        self.assertEqual(self.roots["plist"].read_bytes(), self.before_plist)
        self.assertEqual(self.module_bytes, {
            name: (self.roots["base"] / name).read_bytes()
            for name in self.module_bytes
        })

    def test_both_roles_forward_select_start_stop_and_preserve_every_original_seal(self):
        for account in self.accounts:
            with self.subTest(account=account), self.seat(account) as original:
                self.selected()
                self.assertTrue(self.start()["started"])
                self.assertTrue(original.loaded)
                self.capture(lambda: svc.cmd_stop(SimpleNamespace(account=account)))
                self.assertFalse(original.loaded)
                self.assert_preserved()

    def test_target_profile_alone_never_authorizes_unselected_start(self):
        for account in self.accounts:
            with self.subTest(account=account), self.seat(account) as original:
                self.prepare()
                self.assertEqual(self.invoke()["effect"], "APPLIED")
                with self.assertRaises(SystemExit):
                    self.start()
                self.assertFalse(original.loaded)
                self.assert_preserved()

    def test_lost_forward_completion_and_original_receipt_refuse_start(self):
        for account in self.accounts:
            for which in ("forward", "original"):
                with self.subTest(account=account, receipt=which), self.seat(account) as original:
                    self.selected()
                    directory = self.tx if which == "forward" else self.roots["state"] / "native-pool-pin"
                    (directory / "result.json").write_bytes(b"{}")
                    with self.assertRaises(SystemExit):
                        self.start()
                    self.assertFalse(original.loaded)

    def test_config_only_interruption_reconciles_same_forward_and_preserves_history(self):
        for account in self.accounts:
            with self.subTest(account=account), self.seat(account):
                self.prepare()
                real_write = svc._atomic_write_bytes
                def interrupted(path, data, mode=0o600):
                    real_write(path, data, mode=mode)
                    if Path(path) == self.roots["config"]:
                        raise OSError("inert interruption after tailnet config")
                with mock.patch.object(svc, "_atomic_write_bytes", side_effect=interrupted):
                    with self.assertRaises(SystemExit):
                        self.invoke()
                plan = (self.tx / "plan.json").read_bytes()
                self.args.operation = "reconcile"
                self.assertEqual(self.invoke()["effect"], "APPLIED")
                self.assertEqual((self.tx / "plan.json").read_bytes(), plan)
                self.assert_preserved()

    def test_foreign_full_seal_refuses_before_any_start(self):
        for account in self.accounts:
            for component in ("tailnet-gateway.mjs", "node", "plist"):
                with self.subTest(account=account, component=component), self.seat(account) as original:
                    self.selected()
                    if component == "plist":
                        target = self.roots["plist"]
                    elif component == "node":
                        target = Path(json.loads(self.roots["manifest"].read_bytes())["node"])
                    else:
                        target = self.roots["base"] / component
                    target.write_bytes(target.read_bytes() + b"foreign")
                    with self.assertRaises(SystemExit):
                        self.start()
                    self.assertFalse(original.loaded)

    def test_self_consistent_unregistered_target_profile_is_refused(self):
        for account in self.accounts:
            with self.subTest(account=account), self.seat(account):
                self.selected()
                config = json.loads(self.roots["config"].read_bytes())
                config["requestTimeoutMs"] = config.get("requestTimeoutMs", 0) + 1
                self.roots["config"].write_bytes(svc._fabric_release_json(config))
                manifest = json.loads(self.roots["manifest"].read_bytes())
                manifest["configHash"] = svc._sha256_file(self.roots["config"])
                self.roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
                self.assertFalse(svc._native_pin_manifest_valid(
                    manifest, account, "com.mastermind.studio-direct-private." + account))
                with self.assertRaises(SystemExit):
                    self.start()

    def test_modern_fabric_and_unknown_roles_remain_outside_forward_admission(self):
        self.assertTrue(set(self.accounts).issubset(svc.NATIVE_POOL_PIN_FORWARD_ACCOUNTS))
        for account in ("fabric-c3-570f6f34", "fabric-other", "unknown"):
            self.assertNotIn(account, svc.NATIVE_POOL_PIN_FORWARD_ACCOUNTS)


if __name__ == "__main__":
    unittest.main()
