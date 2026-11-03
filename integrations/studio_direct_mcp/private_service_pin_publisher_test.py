"""Exact native-pool-owner publisher successor, real isolated lifecycle and files."""
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import copy
import io
import json
import os
import tempfile
import unittest

import private_service as svc
import private_service_pin as pin


class C2NativePublisherSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        p = mock.patch.object(svc, "_user_root", return_value=self.home)
        p.start()
        self.addCleanup(p.stop)
        self.account = "chatgpt2-business"
        self.label = "com.mastermind.studio-direct-private." + self.account
        self.roots = svc._build_runtime_roots(self.account)
        self.loaded = False
        self.calls = []

        def run(argv, **_kwargs):
            self.calls.append(argv)
            if argv[:2] == ["launchctl", "print"]:
                if self.loaded:
                    return svc.CmdResult(
                        0,
                        f'{svc._launchd_target(self.label)} = {{\n'
                        f'\tpath = {self.roots["plist"]}\n'
                        '\tstate = running\n\tpid = 789\n}\n',
                        "",
                    )
                return svc.CmdResult(
                    113, "", f'Bad request.\nCould not find service "{self.label}" '
                             f'in domain for user gui: {os.getuid()}\n',
                )
            if argv[:2] == ["launchctl", "bootstrap"]:
                self.loaded = True
                return svc.CmdResult(0, "", "")
            raise AssertionError("unexpected external effect")

        p = mock.patch.object(svc, "_run", run)
        p.start()
        self.addCleanup(p.stop)
        self.source = self.home / "source"
        self.source.mkdir()
        for name in svc.STAGE_FILES:
            (self.source / name).write_bytes(("source-old-" + name).encode())
        node = self.home / "node"
        node.write_bytes(b"fixture-node")
        node.chmod(0o700)
        backend = self.home / "backend.mjs"
        backend.write_bytes(b"fixture-backend")
        self.capture(lambda: svc._write_install(
            self.source, node, backend, self.account, self.label,
            "127.0.0.1", 45028, self.roots,
            result_key="staged", fabric_only=True,
        ))
        deps = self.roots["node_modules"] / "fixture"
        deps.mkdir(parents=True)
        (deps / "index.js").write_bytes(b"inert")
        self.capture(lambda: svc.cmd_seal_runtime(SimpleNamespace(account=self.account)))

        self.pool = self.home / "pool"
        self.pool.write_bytes(b"previous-pool")
        c = json.loads(self.roots["config"].read_bytes())
        c["fleetStatus"] = {
            "enabled": True,
            "launcherPath": str(self.home / "studio"),
            "launcherSha256": "a" * 64,
            "timeoutMs": 15000,
            "fabricLauncherPath": str(self.pool),
            "fabricLauncherSha256": "9" * 64,
            "fabricTimeoutMs": 8000,
        }
        c["preserved_app_config"] = ["no changes to Paper", "no new grants"]
        self.roots["config"].write_bytes(svc._fabric_release_json(c))
        m = json.loads(self.roots["manifest"].read_bytes())
        m["configHash"] = svc._sha256_file(self.roots["config"])
        self.roots["manifest"].write_bytes(svc._fabric_release_json(m))
        self.future_pool = b"native-next-generation"
        self.binding = {
            "successor_digest": "1" * 64,
            "target_generation": "2" * 64,
            "expected_selection": {"generation": "3" * 64, "sequence": 23},
            "pool_target": str(self.pool),
            "pool_previous": svc._sha256_file(self.pool),
            "pool_bridge": __import__("hashlib").sha256(self.future_pool).hexdigest(),
            "phase": "PREVIOUS",
        }

        @contextmanager
        def native(*_args, **_kwargs):
            yield self.binding

        p = mock.patch.object(svc, "_pin_native_context", native)
        p.start()
        self.addCleanup(p.stop)
        original = SimpleNamespace(
            account=self.account,
            expected_manifest_sha256=svc._sha256_file(self.roots["manifest"]),
            successor_bundle=str(self.home / "native-successor"),
            successor_plan_sha256=self.binding["successor_digest"],
            expected_plan_sha256=None,
            operation="preview",
        )
        preview = pin.run(svc, original)
        original.expected_plan_sha256 = preview["planSha256"]
        original.operation = "apply"
        self.assertEqual(pin.run(svc, original)["effect"], "APPLIED")
        self.pool.write_bytes(self.future_pool)
        self.binding["phase"] = "SELECTED"

        prior = json.loads(self.roots["manifest"].read_bytes())
        old = copy.deepcopy(prior["files"])
        next_hashes = {}
        for name in pin.PUBLISHER_FILES:
            (self.source / name).write_bytes(("target-publisher-" + name).encode())
            next_hashes[name] = svc._sha256_file(self.source / name)
        old_hashes = {name: old[name] for name in pin.PUBLISHER_FILES}
        for target, value in (
            ("PUBLISHER_BEFORE_MANIFEST", svc._sha256_file(self.roots["manifest"])),
        ):
            p = mock.patch.object(pin, target, value)
            p.start()
            self.addCleanup(p.stop)
        for target, value in (
            ("FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256", old_hashes),
            ("FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256", next_hashes),
            ("C2_NATIVE_PUBLISHER_FILES_PREIMAGE", old),
            ("C2_NATIVE_PUBLISHER_FILES_POSTIMAGE", {**old, **next_hashes}),
        ):
            p = mock.patch.object(svc, target, value)
            p.start()
            self.addCleanup(p.stop)
        self.start_manifest = self.roots["manifest"].read_bytes()
        self.start_config = self.roots["config"].read_bytes()
        self.start_pin_receipt = (self.roots["state"] / "native-pool-pin" / "result.json").read_bytes()
        self.args = SimpleNamespace(
            account=self.account, source=str(self.source),
            expected_manifest_sha256=svc._sha256_file(self.roots["manifest"]),
            expected_plan_sha256=None, operation="preview",
        )

    @staticmethod
    def capture(fn):
        out = io.StringIO()
        with redirect_stdout(out):
            fn()
        return json.loads(out.getvalue())

    def preview(self):
        p = pin.run_publisher(svc, self.args)
        self.assertEqual(p["effect"], "NOT_APPLIED")
        self.assertTrue(p["preflight"])
        self.args.expected_plan_sha256 = p["planSha256"]
        return p

    def apply(self):
        self.preview()
        self.args.operation = "apply"
        return pin.run_publisher(svc, self.args)

    def test_new_command_requires_explicit_opt_in(self):
        a = svc.build_parser().parse_args([
            "native-pool-pin-publisher", "--account", self.account,
            "--source", str(self.source),
            "--expected-manifest-sha256", self.args.expected_manifest_sha256,
            "--operation", "preview",
        ])
        self.assertEqual(a.func, svc.cmd_native_pool_pin_publisher)
        with self.assertRaises(SystemExit):
            svc._pin_reject_generic_restage(self.account)

    def test_preflight_is_readonly_even_when_loaded(self):
        before = {p: p.read_bytes() for p in self.roots["base"].rglob("*") if p.is_file()}
        self.loaded = True
        self.preview()
        self.assertEqual(before, {
            p: p.read_bytes() for p in self.roots["base"].rglob("*") if p.is_file()
        })

    def test_exact_apply_changes_two_modules_and_manifest_only(self):
        before = {p: p.read_bytes() for p in self.roots["base"].iterdir() if p.is_file()}
        result = self.apply()
        self.assertEqual(result["effect"], "APPLIED")
        self.assertEqual(self.roots["config"].read_bytes(), self.start_config)
        changed = {p.name for p, raw in before.items() if p.read_bytes() != raw}
        self.assertEqual(changed, {*pin.PUBLISHER_FILES, "manifest.json"})
        self.assertEqual(
            (self.roots["state"] / "native-pool-pin" / "result.json").read_bytes(),
            self.start_pin_receipt,
        )
        self.assertEqual(pin.publisher_require_start(svc, self.account, self.roots), None)

    def test_loaded_apply_refuses_without_any_state_write(self):
        self.preview()
        self.loaded = True
        self.args.operation = "apply"
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.assertFalse((self.roots["state"] / "native-pool-pin-publisher").exists())

    def test_stale_plan_and_modified_source_refuse(self):
        self.preview()
        self.args.operation = "apply"
        self.args.expected_plan_sha256 = "0" * 64
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.assertFalse((self.roots["state"] / "native-pool-pin-publisher").exists())
        self.args.expected_plan_sha256 = None
        self.args.operation = "preview"
        self.preview()
        (self.source / "git-publish.mjs").write_bytes(b"foreign-target")
        self.args.operation = "apply"
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.assertFalse((self.roots["state"] / "native-pool-pin-publisher").exists())

    def test_wrong_account_and_absent_original_receipt_refuse(self):
        self.args.account = "chatgpt1"
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.args.account = self.account
        (self.roots["state"] / "native-pool-pin" / "result.json").unlink()
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)

    def test_partial_module_failure_retains_original_transaction_and_reconciles(self):
        self.preview()
        real = svc._atomic_write_bytes
        self.args.operation = "apply"

        def fail_manifest(path, raw, **kwargs):
            if path == self.roots["manifest"]:
                raise OSError("synthetic before manifest")
            return real(path, raw, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", fail_manifest):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                pin.run_publisher(svc, self.args)
        self.assertEqual(self.roots["manifest"].read_bytes(), self.start_manifest)
        self.assertEqual(
            (self.roots["state"] / "native-pool-pin" / "result.json").read_bytes(),
            self.start_pin_receipt,
        )
        self.args.operation = "status"
        self.assertEqual(pin.run_publisher(svc, self.args)["effect"], "PARTIAL")
        self.args.operation = "reconcile"
        self.assertEqual(pin.run_publisher(svc, self.args)["effect"], "APPLIED")

    def test_foreign_partial_refused_without_rewrite(self):
        self.preview()
        self.args.operation = "apply"
        real = svc._atomic_write_bytes

        def fail_second(path, raw, **kwargs):
            if path.name == "workspace-access.mjs":
                raise OSError("synthetic")
            return real(path, raw, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", fail_second):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                pin.run_publisher(svc, self.args)
        target = self.roots["base"] / "git-publish.mjs"
        target.write_bytes(b"foreign-writer")
        self.args.operation = "reconcile"
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.assertEqual(target.read_bytes(), b"foreign-writer")

    def test_startup_refuses_until_complete_original_chain(self):
        self.apply()
        tx = self.roots["state"] / "native-pool-pin-publisher"
        (tx / "result.json").unlink()
        with self.assertRaises(SystemExit):
            pin.require_start(svc, self.account, self.roots)
        result = {"schema": pin.PUBLISHER_SCHEMA,
                  "planSha256": self.args.expected_plan_sha256, "effect": "APPLIED"}
        svc._fabric_release_new(tx / "result.json", svc._fabric_release_json(result))
        pin.require_start(svc, self.account, self.roots)
        (self.roots["base"] / "git-publish.mjs").write_bytes(b"foreign")
        with self.assertRaises(SystemExit):
            pin.require_start(svc, self.account, self.roots)

    def test_committed_receipt_cannot_replay(self):
        self.apply()
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.args.operation = "status"
        self.assertEqual(pin.run_publisher(svc, self.args)["effect"], "APPLIED")
        self.assertTrue(pin.run_publisher(svc, self.args)["resultCommitted"])


    def test_original_seven_files_immutable_and_manifest_last(self):
        original_pin = self.roots["state"] / "native-pool-pin"
        before = {p.name: p.read_bytes() for p in original_pin.iterdir() if p.is_file()}
        order = []
        real = svc._atomic_write_bytes

        def capture_write(path, contents, **kwargs):
            tx = self.roots["state"] / "native-pool-pin-publisher"
            self.assertTrue(all((tx / name).is_file()
                for name in pin.PUBLISHER_TX_FILES - {"result.json"}))
            order.append(path.name)
            if path == self.roots["manifest"]:
                self.assertTrue(all(
                    svc._sha256_file(self.roots["base"] / name) ==
                    svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256[name]
                    for name in pin.PUBLISHER_FILES))
            return real(path, contents, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", capture_write):
            self.apply()
        self.assertEqual(order, [*pin.PUBLISHER_FILES, "manifest.json"])
        self.assertEqual(before, {p.name: p.read_bytes()
            for p in original_pin.iterdir() if p.is_file()})
        svc._verify_staged_install(self.account, self.label, self.roots)

    def test_lost_postmanifest_receipt_requires_same_transaction_reconcile(self):
        self.preview()
        self.args.operation = "apply"
        real = svc._fabric_release_new

        def interrupt_result(path, raw):
            if path.name == "result.json" and "native-pool-pin-publisher" in str(path):
                raise OSError("synthetic terminal receipt loss")
            return real(path, raw)

        with mock.patch.object(svc, "_fabric_release_new", interrupt_result):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                pin.run_publisher(svc, self.args)
        self.assertNotEqual(self.roots["manifest"].read_bytes(), self.start_manifest)
        self.args.operation = "status"
        observation = pin.run_publisher(svc, self.args)
        self.assertEqual(observation["phase"], "COMPLETE")
        self.assertEqual(observation["effect"], "EFFECT_UNKNOWN")
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes",
                               side_effect=AssertionError("must not replay committed bytes")):
            self.assertEqual(pin.run_publisher(svc, self.args)["effect"], "APPLIED")

    def test_unselected_native_generation_refuses_even_readonly_preview(self):
        self.binding["phase"] = "PREVIOUS"
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_UNQUALIFIED"):
            pin.run_publisher(svc, self.args)
        self.assertFalse((self.roots["state"] / "native-pool-pin-publisher").exists())

    def test_foreign_unrelated_module_or_config_refuses_before_intent(self):
        other = self.roots["base"] / "paper-design.mjs"
        other.write_bytes(b"unauthorized-paper-drift")
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.assertFalse((self.roots["state"] / "native-pool-pin-publisher").exists())
        other.write_bytes((self.source / "paper-design.mjs").read_bytes())
        self.roots["config"].write_bytes(b"unauthorized-config-drift")
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        self.assertFalse((self.roots["state"] / "native-pool-pin-publisher").exists())

    def test_foreign_successor_file_and_module_mode_refused(self):
        self.apply()
        tx = self.roots["state"] / "native-pool-pin-publisher"
        self.args.operation = "status"
        (tx / "foreign.json").write_text("{}")
        with self.assertRaises(SystemExit):
            pin.run_publisher(svc, self.args)
        (tx / "foreign.json").unlink()
        (self.roots["base"] / "git-publish.mjs").chmod(0o700)
        with self.assertRaisesRegex(SystemExit, "FOREIGN_MODE"):
            pin.run_publisher(svc, self.args)

    def test_real_normal_start_requires_complete_native_owner_chain(self):
        self.apply()
        self.assertFalse(self.loaded)
        # The owner dynamically imports a fresh module in production. Bind its
        # fixture module here so the synthetic digest pins are identical.
        with mock.patch.object(svc, "_pin_owner_module", return_value=pin):
            self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
            self.assertTrue(self.loaded)
            self.loaded = False
            (self.roots["state"] / "native-pool-pin" / "result.json").write_bytes(b"foreign")
            with self.assertRaises(SystemExit):
                self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
            self.assertFalse(self.loaded)

    def test_ordinary_upgrade_remains_explicitly_refused(self):
        self.apply()
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER"):
            svc.cmd_upgrade(SimpleNamespace(account=self.account,
                                            c2_business_merge_publisher_only=True))
        self.assertEqual(self.roots["config"].read_bytes(), self.start_config)

if __name__ == "__main__":
    unittest.main()
