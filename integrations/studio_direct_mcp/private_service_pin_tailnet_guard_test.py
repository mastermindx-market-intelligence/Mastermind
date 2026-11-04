"""Canonical negative integration checks; no host or real native verifier calls."""
import copy
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import private_service as svc
import private_service_pin_tailnet_protocol_test as protocol


class TailnetOwnerGuardTests(unittest.TestCase):
    def test_complete_private_verifier_stays_private_only(self):
        for account in ("fabric-design", "fabric-read"):
            with self.subTest(account=account), protocol.tailnet_seat(account) as seat:
                with self.assertRaisesRegex(SystemExit, "plist is not our exact install"):
                    svc._verify_staged_install(account, seat.label, seat.roots)
                self.assertEqual(svc._verify_native_pin_install(account, seat.label, seat.roots),
                                 seat.before_manifest)

    def test_every_physical_seal_drift_refuses_without_lifecycle_effect(self):
        for account in ("fabric-design", "fabric-read"):
            for field in ("module", "config", "plist", "node", "backend", "dependency"):
                with self.subTest(account=account, field=field), protocol.tailnet_seat(account) as seat:
                    if field == "module":
                        path = seat.roots["base"] / "tailnet-gateway.mjs"
                    elif field == "dependency":
                        path = seat.roots["node_modules"] / "fixture" / "index.js"
                    elif field in ("node", "backend"):
                        path = Path(seat.before_manifest[field])
                    else:
                        path = seat.roots[field]
                    path.write_bytes(path.read_bytes() + b"\nforeign drift")
                    before = list(seat.calls)
                    with self.assertRaises(SystemExit):
                        svc._verify_native_pin_install(account, seat.label, seat.roots)
                    self.assertEqual(seat.calls, before)

    def test_self_consistent_unknown_profile_cannot_select_tailnet(self):
        for account in ("fabric-design", "fabric-read"):
            with self.subTest(account=account), protocol.tailnet_seat(account) as seat:
                cfg = copy.deepcopy(seat.before_config)
                cfg["unreviewed_capability"] = True
                seat.roots["config"].write_bytes(svc._fabric_release_json(cfg))
                manifest = copy.deepcopy(seat.before_manifest)
                manifest["configHash"] = svc._sha256_file(seat.roots["config"])
                seat.roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
                with self.assertRaisesRegex(SystemExit, "preserved Tailnet profile differs"):
                    svc._verify_native_pin_install(account, seat.label, seat.roots)

    def test_unknown_account_and_exact_argv_path_mismatch_refuse(self):
        with protocol.tailnet_seat("fabric-design") as seat:
            with self.assertRaises(SystemExit):
                svc._verify_native_pin_install("unknown-seat", seat.label, seat.roots)
            # Same sealed bytes at a different supplied config address must not
            # pass merely because the content hash matches the manifest.
            alias = seat.roots["base"] / "config.alias.json"
            alias.write_bytes(seat.roots["config"].read_bytes())
            altered = {**seat.roots, "config": alias}
            with self.assertRaisesRegex(SystemExit, "exact preserved Tailnet install"):
                svc._verify_native_pin_install(seat.account, seat.label, altered)

    def test_symlink_or_writable_module_refuses(self):
        for attack in ("symlink", "writable"):
            with self.subTest(attack=attack), protocol.tailnet_seat("fabric-read") as seat:
                path = seat.roots["base"] / "tailnet-gateway.mjs"
                if attack == "symlink":
                    target = seat.home / "identical-public-module.mjs"
                    target.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(target)
                else:
                    path.chmod(0o666)
                with self.assertRaises(SystemExit):
                    svc._verify_native_pin_install(seat.account, seat.label, seat.roots)

    def test_full_runtime_seal_is_required_even_for_stop_or_seal(self):
        for account in ("fabric-design", "fabric-read"):
            with self.subTest(account=account), protocol.tailnet_seat(account) as seat:
                (seat.roots["node_modules"] / "foreign.js").write_bytes(b"drift")
                with self.assertRaises(SystemExit):
                    svc._verify_native_pin_install(account, seat.label, seat.roots,
                                                   require_runtime_seal=False)

    def test_generic_stage_and_upgrade_still_refuse_legacy_capability_rebuild(self):
        for account in ("fabric-design", "fabric-read"):
            for command in (svc.cmd_stage, svc.cmd_upgrade):
                with self.subTest(account=account, command=command.__name__), protocol.tailnet_seat(account):
                    with self.assertRaisesRegex(SystemExit, "PROFILE_REQUIRES_PIN_OWNER"):
                        command(SimpleNamespace(account=account))

    def test_config_only_status_and_owned_reconcile_preserve_effect_truth(self):
        for account in ("fabric-design", "fabric-read"):
            with self.subTest(account=account), protocol.tailnet_seat(account) as seat:
                seat.prepare()
                real = svc._atomic_write_bytes

                def interrupted(path, raw, **kwargs):
                    if Path(path) == seat.roots["manifest"]:
                        raise OSError("synthetic manifest-write interruption")
                    return real(path, raw, **kwargs)

                with mock.patch.object(svc, "_atomic_write_bytes", interrupted):
                    with self.assertRaises(SystemExit):
                        seat.invoke()
                seat.args.operation = "status"
                status = seat.invoke()
                self.assertEqual((status["phase"], status["effect"]), ("CONFIG_ONLY", "PARTIAL"))
                self.assertFalse(status["receiptCommitted"])
                seat.args.operation = "reconcile"
                self.assertEqual(seat.invoke()["effect"], "APPLIED")
                self.assertEqual(json.loads(seat.roots["config"].read_bytes())[
                    "opaque_existing_capability"], seat.before_config["opaque_existing_capability"])
                before = (seat.roots["config"].read_bytes(), seat.roots["manifest"].read_bytes())
                seat.args.operation = "apply"
                with self.assertRaises(SystemExit):
                    seat.invoke()
                self.assertEqual(before, (seat.roots["config"].read_bytes(),
                                          seat.roots["manifest"].read_bytes()))

    def test_unselected_future_pin_cannot_start(self):
        with protocol.tailnet_seat("fabric-design") as seat:
            seat.prepare()
            seat.invoke()
            with mock.patch.object(svc, "_pin_native_context", seat.native):
                with self.assertRaises(SystemExit):
                    seat.capture(lambda: svc.cmd_start(SimpleNamespace(account=seat.account)))
            self.assertFalse(seat.loaded)

    def test_indeterminate_lifecycle_does_not_start_or_reseal(self):
        for command in (svc.cmd_start, svc.cmd_seal_runtime):
            with self.subTest(command=command.__name__), protocol.tailnet_seat("fabric-read") as seat:
                seat.launch_error = True
                before = seat.roots["manifest"].read_bytes()
                with self.assertRaises(SystemExit):
                    seat.capture(lambda: command(SimpleNamespace(account=seat.account)))
                self.assertFalse(seat.loaded)
                self.assertEqual(seat.roots["manifest"].read_bytes(), before)
                self.assertFalse(any(a[:2] == ["launchctl", "bootstrap"] for a in seat.calls))

    def test_post_bootout_unknown_is_effect_unknown(self):
        with protocol.tailnet_seat("fabric-read") as seat:
            seat.loaded = True
            normal = svc._run
            booted = False

            def lifecycle(argv, **kwargs):
                nonlocal booted
                if argv[:2] == ["launchctl", "bootout"]:
                    booted = True
                    seat.loaded = False
                    return svc.CmdResult(0, "", "")
                if booted and argv[:2] == ["launchctl", "print"]:
                    return svc.CmdResult(1, "", "synthetic unknown")
                return normal(argv, **kwargs)

            with mock.patch.object(svc, "_run", lifecycle):
                with self.assertRaisesRegex(SystemExit, "Tailnet stop: EFFECT_UNKNOWN"):
                    seat.capture(lambda: svc.cmd_stop(SimpleNamespace(account=seat.account)))
            self.assertTrue(booted)


if __name__ == "__main__":
    unittest.main()
