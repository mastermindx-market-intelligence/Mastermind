"""Real sealed temp seats; only launchctl/native epoch fixture boundaries mocked."""

import copy, io, json, os, tempfile, unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import private_service as svc


class PinTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        patch = mock.patch.object(svc, "_user_root", return_value=self.home)
        patch.start()
        self.addCleanup(patch.stop)
        self.account = "chatgpt1"
        self.label = "com.mastermind.studio-direct-private." + self.account
        self.loaded = False
        self.launch_error = False
        self.calls = []
        self.roots = svc._build_runtime_roots(self.account)

        def run(argv, **kwargs):
            self.calls.append(argv)
            if argv[:2] == ["launchctl", "print"]:
                if self.launch_error:
                    return svc.CmdResult(1, "", "private-error")
                if self.loaded:
                    return svc.CmdResult(
                        0,
                        f'{svc._launchd_target(self.label)} = {{\n\tpath = {self.roots["plist"]}\n\tstate = running\n\tpid = 1234\n}}\n',
                        "",
                    )
                return svc.CmdResult(
                    113,
                    "",
                    f'Bad request.\nCould not find service "{self.label}" in domain for user gui: {os.getuid()}\n',
                )
            if argv[:2] == ["launchctl", "bootstrap"]:
                self.loaded = True
                return svc.CmdResult(0, "", "")
            raise AssertionError("unexpected external effect")

        patch = mock.patch.object(svc, "_run", run)
        patch.start()
        self.addCleanup(patch.stop)
        source = self.home / "source"
        source.mkdir()
        for n in svc.STAGE_FILES:
            (source / n).write_text("// fixture " + n + "\n")
        node = self.home / "node"
        node.write_text("node")
        node.chmod(0o700)
        backend = self.home / "backend.mjs"
        backend.write_text("backend")
        a = SimpleNamespace(
            account=self.account,
            port=45201,
            source=str(source),
            node=str(node),
            backend=str(backend),
            fabric_only=False,
            modern_fabric_protocol=None,
            enable_repository_workspaces=False,
            os_commission_config_sha256=None,
        )
        self.capture(
            lambda: svc._write_install(
                source,
                node,
                backend,
                self.account,
                self.label,
                "127.0.0.1",
                45201,
                self.roots,
                result_key="staged",
                fabric_only=True,
            )
        )
        deps = self.roots["node_modules"] / "fixture"
        deps.mkdir(parents=True)
        (deps / "index.js").write_text("inert")
        self.capture(
            lambda: svc.cmd_seal_runtime(SimpleNamespace(account=self.account))
        )
        self.pool = self.home / "pool"
        self.pool.write_bytes(b"current-native-pool")
        c = json.loads(self.roots["config"].read_bytes())
        c["fleetStatus"] = {
            "enabled": True,
            "launcherPath": str(self.home / "studio-direct"),
            "launcherSha256": "a" * 64,
            "timeoutMs": 15000,
            "fabricLauncherPath": str(self.pool),
            "fabricLauncherSha256": "9" * 64,
            "fabricTimeoutMs": 8000,
        }
        c["opaque_existing_capability"] = {"args": ["PRIVATE-CANARY"], "enabled": True}
        self.roots["config"].write_bytes(svc._fabric_release_json(c))
        m = json.loads(self.roots["manifest"].read_bytes())
        m["configHash"] = svc._sha256_file(self.roots["config"])
        self.roots["manifest"].write_bytes(svc._fabric_release_json(m))
        self.before_config = copy.deepcopy(c)
        self.before_manifest = copy.deepcopy(m)
        self.future = b"future-native-pool"
        self.binding = {
            "successor_digest": "1" * 64,
            "target_generation": "2" * 64,
            "expected_selection": {"generation": "3" * 64, "sequence": 23},
            "pool_target": str(self.pool),
            "pool_previous": svc._sha256_file(self.pool),
            "pool_bridge": __import__("hashlib").sha256(self.future).hexdigest(),
            "phase": "PREVIOUS",
        }
        self.args = SimpleNamespace(
            account=self.account,
            expected_manifest_sha256=svc._sha256_file(self.roots["manifest"]),
            successor_bundle=str(self.home / "successor"),
            successor_plan_sha256="1" * 64,
            expected_plan_sha256=None,
            operation="preview",
        )

    def capture(self, fn):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = fn()
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue())

    @contextmanager
    def native(self, *args, **kwargs):
        yield self.binding

    def invoke(self):
        with mock.patch.object(svc, "_pin_native_context", self.native):
            return self.capture(lambda: svc.cmd_native_pool_pin(self.args))

    def prepare(self):
        p = self.invoke()
        self.args.expected_plan_sha256 = p["planSha256"]
        self.args.operation = "apply"
        return p

    def test_cli_exposes_explicit_pin_operation(self):
        a = svc.build_parser().parse_args(
            [
                "native-pool-pin",
                "--account",
                "chatgpt1",
                "--expected-manifest-sha256",
                "a" * 64,
                "--successor-bundle",
                "/fixture",
                "--successor-plan-sha256",
                "b" * 64,
                "--operation",
                "preview",
            ]
        )
        self.assertEqual(a.func, svc.cmd_native_pool_pin)

    def test_preview_loaded_is_readonly_and_redacted(self):
        self.loaded = True
        before = {
            p: p.read_bytes() for p in self.roots["base"].rglob("*") if p.is_file()
        }
        p = self.invoke()
        self.assertEqual(p["effect"], "NOT_APPLIED")
        self.assertNotIn("PRIVATE-CANARY", json.dumps(p))
        self.assertEqual(
            before,
            {p: p.read_bytes() for p in self.roots["base"].rglob("*") if p.is_file()},
        )

    def test_apply_only_changes_pin_and_manifest_config_hash(self):
        self.prepare()
        p = self.invoke()
        self.assertEqual(p["effect"], "APPLIED")
        c = json.loads(self.roots["config"].read_bytes())
        m = json.loads(self.roots["manifest"].read_bytes())
        wanted = copy.deepcopy(self.before_config)
        wanted["fleetStatus"]["fabricLauncherSha256"] = self.binding["pool_bridge"]
        self.assertEqual(c, wanted)
        wantm = copy.deepcopy(self.before_manifest)
        wantm["configHash"] = svc._sha256_file(self.roots["config"])
        self.assertEqual(m, wantm)
        svc._verify_staged_install(self.account, self.label, self.roots)
        self.assertFalse(
            any(
                x[:2] in (["launchctl", "bootstrap"], ["launchctl", "bootout"])
                for x in self.calls
            )
        )

    def test_loaded_apply_refuses_before_write(self):
        self.prepare()
        self.loaded = True
        before = self.roots["config"].read_bytes()
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(self.roots["config"].read_bytes(), before)

    def test_indeterminate_lifecycle_refuses(self):
        self.prepare()
        self.launch_error = True
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_stale_plan_refuses(self):
        self.prepare()
        self.args.expected_plan_sha256 = "f" * 64
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_foreign_config_refuses(self):
        self.prepare()
        self.roots["config"].write_text("{}")
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_completed_status_is_readonly(self):
        self.prepare()
        self.invoke()
        before = {
            p: p.read_bytes() for p in self.roots["state"].rglob("*") if p.is_file()
        }
        self.args.operation = "status"
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.assertEqual(
            before,
            {p: p.read_bytes() for p in self.roots["state"].rglob("*") if p.is_file()},
        )

    def test_unknown_account_refuses(self):
        self.args.account = "unknown-seat"
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_stale_manifest_refuses(self):
        self.args.expected_manifest_sha256 = "e" * 64
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_all_intent_bytes_durable_before_first_write(self):
        self.prepare()
        original = svc._atomic_write_bytes
        order = []

        def write(path, data, **kwargs):
            tx = self.roots["state"] / "native-pool-pin"
            self.assertTrue(
                all(
                    (tx / n).is_file()
                    for n in [
                        "plan.json",
                        "intent.json",
                        "config.before.json",
                        "config.after.json",
                        "manifest.before.json",
                        "manifest.after.json",
                    ]
                )
            )
            order.append(path.name)
            original(path, data, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            self.invoke()
        self.assertEqual(order, ["config.json", "manifest.json"])

    def fail_before_manifest(self):
        self.prepare()
        original = svc._atomic_write_bytes

        def write(path, data, **kwargs):
            if path == self.roots["manifest"]:
                raise OSError("PRIVATE-CANARY")
            original(path, data, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            with self.assertRaises(SystemExit):
                self.invoke()

    def test_owned_config_only_reconcile_finishes_same_plan(self):
        self.fail_before_manifest()
        self.args.operation = "status"
        self.assertEqual(self.invoke()["phase"], "CONFIG_ONLY")
        self.args.operation = "reconcile"
        self.assertEqual(self.invoke()["effect"], "APPLIED")

    def test_foreign_partial_never_overwritten(self):
        self.fail_before_manifest()
        self.roots["config"].write_bytes(b"foreign")
        self.args.operation = "reconcile"
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(self.roots["config"].read_bytes(), b"foreign")

    def test_partial_static_backend_drift_refuses_reconcile(self):
        self.fail_before_manifest()
        Path(self.before_manifest["backend"]).write_bytes(b"foreign-backend")
        self.args.operation = "reconcile"
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(
            self.roots["manifest"].read_bytes(),
            svc._fabric_release_json(self.before_manifest),
        )

    def test_terminal_receipt_cannot_replay_old_pair(self):
        self.prepare()
        self.invoke()
        self.roots["config"].write_bytes(svc._fabric_release_json(self.before_config))
        self.roots["manifest"].write_bytes(
            svc._fabric_release_json(self.before_manifest)
        )
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(
            json.loads(self.roots["config"].read_bytes()), self.before_config
        )

    def test_staging_symlink_refuses(self):
        self.prepare()
        (self.roots["state"] / "native-pool-pin").symlink_to(
            self.home, target_is_directory=True
        )
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_duplicate_and_nonfinite_json_refused(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.subTest(raw=raw):
                self.roots["config"].write_bytes(raw)
                m = copy.deepcopy(self.before_manifest)
                m["configHash"] = svc._sha256_file(self.roots["config"])
                self.roots["manifest"].write_bytes(svc._fabric_release_json(m))
                self.args.expected_manifest_sha256 = svc._sha256_file(
                    self.roots["manifest"]
                )
                with self.assertRaises(SystemExit):
                    self.invoke()

    def test_modes_preserved(self):
        self.roots["config"].chmod(0o400)
        self.roots["manifest"].chmod(0o400)
        self.prepare()
        self.invoke()
        self.assertEqual(self.roots["config"].stat().st_mode & 0o777, 0o400)
        self.assertEqual(self.roots["manifest"].stat().st_mode & 0o777, 0o400)

    def test_existing_lifecycle_lock_blocks_apply_without_write(self):
        self.prepare()
        before = self.roots["config"].read_bytes()
        with svc._c2_lifecycle_mutex(self.account):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertEqual(self.roots["config"].read_bytes(), before)

    def test_untouched_historical_drift_does_not_add_start_refusal(self):
        self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
        self.assertTrue(self.loaded)

    def test_future_pin_start_refuses_until_selected_bridge(self):
        self.prepare()
        self.invoke()
        with mock.patch.object(svc, "_pin_native_context", self.native):
            with self.assertRaises(SystemExit):
                self.capture(
                    lambda: svc.cmd_start(SimpleNamespace(account=self.account))
                )
            self.assertFalse(self.loaded)
            self.pool.write_bytes(self.future)
            self.binding["phase"] = "SELECTED"
            self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
        self.assertTrue(self.loaded)

    def test_exact_legacy_profiles_no_unknown_account_or_digest_wildcard(self):
        for account, files in svc.NATIVE_POOL_PIN_PREDECESSORS.items():
            with self.subTest(account=account):
                m = copy.deepcopy(self.before_manifest)
                m.update(
                    account=account,
                    label="com.mastermind.studio-direct-private." + account,
                    files=copy.deepcopy(files),
                )
                self.assertTrue(svc._valid_manifest(m, account, m["label"]))
                first = next(iter(m["files"]))
                m["files"][first] = "0" * 64
                self.assertFalse(svc._valid_manifest(m, account, m["label"]))
                m["files"] = copy.deepcopy(files)
                m["account"] = "unknown-seat"
                m["label"] = "com.mastermind.studio-direct-private.unknown-seat"
                self.assertFalse(svc._valid_manifest(m, "unknown-seat", m["label"]))

    def test_generic_restage_not_newly_enabled(self):
        with mock.patch.object(
            svc,
            "NATIVE_POOL_PIN_PREDECESSORS",
            {self.account: self.before_manifest["files"]},
        ):
            with self.assertRaises(SystemExit):
                svc._pin_reject_generic_restage(self.account)

    def test_real_successor_verifier_refuses_missing_bundle(self):
        with self.assertRaises(SystemExit) as c:
            with svc._pin_native_context(self.args):
                self.fail("missing bundle admitted")
        self.assertNotIn("PRIVATE-CANARY", str(c.exception))

    def test_unexpected_owner_error_is_fixed_not_private_text(self):
        with mock.patch.object(
            svc, "_pin_native_context", side_effect=SystemExit("PRIVATE-CANARY")
        ):
            with self.assertRaises(SystemExit) as c:
                svc.cmd_native_pool_pin(self.args)
        self.assertNotIn("PRIVATE-CANARY", str(c.exception))

    def test_exponent_nonfinite_is_refused_by_closed_reader(self):
        with self.assertRaises(SystemExit):
            svc._pin_owner_module().decode(b'{"opaque":1e999}')

    def test_receipt_loss_reconcile_records_without_rewriting_pair(self):
        self.prepare()
        original = svc._fabric_release_new

        def write(path, data):
            if path.name == "result.json":
                raise OSError("PRIVATE-CANARY")
            return original(path, data)

        with mock.patch.object(svc, "_fabric_release_new", write):
            with self.assertRaises(SystemExit):
                self.invoke()
        before = (
            self.roots["config"].read_bytes(),
            self.roots["manifest"].read_bytes(),
        )
        self.args.operation = "reconcile"
        with mock.patch.object(
            svc, "_atomic_write_bytes", side_effect=AssertionError("pair replayed")
        ):
            self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.assertEqual(
            before,
            (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes()),
        )

    def native_proof_response(self, phase="PREVIOUS"):
        store = self.home / "native-code-releases"
        store.mkdir(mode=0o700, exist_ok=True)
        value = dict(self.binding, store=str(store), phase=phase)
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(value).encode(), stderr=b""
        )

    def test_existing_native_publication_lock_is_held_during_apply_context(self):
        self.args.operation = "apply"
        response = self.native_proof_response()
        rollout = (
            Path(svc.__file__).resolve().parents[2]
            / "ops/native_fabric/quota_continuity/rollout"
        )
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "pin_test_generation", rollout / "native_generation.py"
        )
        generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generation)
        with mock.patch.object(svc.subprocess, "run", return_value=response):
            with svc._pin_native_context(self.args):
                with self.assertRaises(ValueError):
                    with generation.publication_lock(
                        self.home / "native-code-releases"
                    ):
                        self.fail("native publisher lock was not retained")

    def test_readonly_preview_context_does_not_create_publication_lock(self):
        response = self.native_proof_response()
        with mock.patch.object(svc.subprocess, "run", return_value=response):
            with svc._pin_native_context(self.args):
                pass
        self.assertFalse(
            (self.home / "native-code-releases/.publication.lock").exists()
        )

    def test_changed_successor_proof_refuses_before_parent_mutation(self):
        first = self.native_proof_response()
        second = self.native_proof_response("SELECTED")
        with mock.patch.object(svc.subprocess, "run", side_effect=[first, second]):
            with self.assertRaises(SystemExit):
                with svc._pin_native_context(self.args):
                    self.fail("changed native binding admitted")


if __name__ == "__main__":
    unittest.main()
