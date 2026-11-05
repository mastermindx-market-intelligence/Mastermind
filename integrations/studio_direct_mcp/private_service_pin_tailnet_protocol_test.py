"""Parent integration proof: preserving Tailnet pin, selection and lifecycle.

Real temporary files/seals/transactions; only native epoch and launchctl are
external fixtures. No host seat, real successor or provider is invoked.
"""
import copy
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import private_service as svc
import private_service_pin_transition_test as incumbent_fixture


@contextmanager
def tailnet_seat(account):
    seat = incumbent_fixture.PinTransitionTests()
    seat.setUp()
    try:
        old_roots = seat.roots
        old_account = seat.account
        seat.account = account
        seat.label = "com.mastermind.studio-direct-private." + account
        seat.roots = svc._build_runtime_roots(account)
        old_roots["base"].rename(seat.roots["base"])
        old_roots["plist"].unlink()
        config = json.loads(json.dumps(seat.before_config).replace(old_account, account))
        seat.roots["config"].write_bytes(svc._fabric_release_json(config))
        manifest = copy.deepcopy(seat.before_manifest)
        manifest.update(account=account, label=seat.label)
        gateway = seat.roots["base"] / "tailnet-gateway.mjs"
        gateway.write_bytes(b"inert sealed Tailnet fixture\n")
        manifest["files"][gateway.name] = svc._sha256_file(gateway)
        plist = {"Label": seat.label, "ProgramArguments": [
            manifest["node"], str(gateway), str(seat.roots["config"])]}
        seat.roots["plist"].write_bytes(plistlib.dumps(plist))
        manifest["plistHash"] = svc._sha256_file(seat.roots["plist"])
        manifest["configHash"] = svc._sha256_file(seat.roots["config"])
        seat.roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
        seat.before_config, seat.before_manifest = config, manifest
        seat.args.account = account
        seat.args.expected_manifest_sha256 = svc._sha256_file(seat.roots["manifest"])
        after = copy.deepcopy(config)
        after["fleetStatus"]["fabricLauncherSha256"] = seat.binding["pool_bridge"]
        future = copy.deepcopy(manifest)
        future["configHash"] = hashlib.sha256(svc._fabric_release_json(after)).hexdigest()
        canonical = {**getattr(svc, "_NATIVE_POOL_PIN_TAILNET_CANONICAL", {}),
                     account: frozenset((svc._canonical_json_sha256(manifest),
                                         svc._canonical_json_sha256(future)))}
        original_run = svc._run

        def lifecycle(argv, **kwargs):
            if argv[:2] == ["launchctl", "bootout"]:
                seat.calls.append(argv)
                seat.loaded = False
                return svc.CmdResult(0, "", "")
            return original_run(argv, **kwargs)

        with mock.patch.dict(svc.NATIVE_POOL_PIN_PREDECESSORS,
                             {account: manifest["files"]}), \
                mock.patch.object(svc, "_NATIVE_POOL_PIN_TAILNET_CANONICAL",
                                  canonical, create=True), \
                mock.patch.object(svc, "_run", lifecycle):
            yield seat
    finally:
        seat.doCleanups()


class TailnetPinProtocolTests(unittest.TestCase):
    def _complete_preserving_transition(self, account):
        with tailnet_seat(account) as seat:
            before_plist = seat.roots["plist"].read_bytes()
            module_bytes = {n: (seat.roots["base"] / n).read_bytes()
                            for n in seat.before_manifest["files"]}
            preview = seat.prepare()
            self.assertEqual(preview["effect"], "NOT_APPLIED")
            applied = seat.invoke()
            self.assertEqual(applied["effect"], "APPLIED")
            self.assertTrue(applied["receiptCommitted"])
            self.assertFalse(seat.loaded)
            expected = copy.deepcopy(seat.before_config)
            expected["fleetStatus"]["fabricLauncherSha256"] = seat.binding["pool_bridge"]
            self.assertEqual(json.loads(seat.roots["config"].read_bytes()), expected)
            expected_manifest = copy.deepcopy(seat.before_manifest)
            expected_manifest["configHash"] = svc._sha256_file(seat.roots["config"])
            self.assertEqual(json.loads(seat.roots["manifest"].read_bytes()), expected_manifest)
            self.assertEqual(seat.roots["plist"].read_bytes(), before_plist)
            self.assertEqual({n: (seat.roots["base"] / n).read_bytes() for n in module_bytes},
                             module_bytes)
            # External epoch selection is a fixture, not a native verifier call.
            seat.pool.write_bytes(seat.future)
            seat.binding["phase"] = "SELECTED"
            with mock.patch.object(svc, "_pin_native_context", seat.native):
                seat.capture(lambda: svc.cmd_start(SimpleNamespace(account=account)))
                self.assertTrue(seat.loaded)
                seat.capture(lambda: svc.cmd_stop(SimpleNamespace(account=account)))
                self.assertFalse(seat.loaded)
                seat.capture(lambda: svc.cmd_seal_runtime(SimpleNamespace(account=account)))
                seat.args.operation = "status"
                status = seat.invoke()
                self.assertEqual(status["effect"], "APPLIED")
                self.assertTrue(status["receiptCommitted"])
            self.assertEqual(seat.roots["plist"].read_bytes(), before_plist)
            self.assertEqual(json.loads(seat.roots["config"].read_bytes()), expected)

    def test_design_pin_selection_start_stop_seal_preserves_entire_contract(self):
        self._complete_preserving_transition("fabric-design")

    def test_read_pin_selection_start_stop_seal_preserves_entire_contract(self):
        self._complete_preserving_transition("fabric-read")


if __name__ == "__main__":
    unittest.main()
