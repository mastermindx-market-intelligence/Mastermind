"""Real sealed temp seats; only launchctl/native epoch fixture boundaries mocked."""

import copy, hashlib, io, json, os, subprocess, sys, tempfile, time, unittest
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
        partial = self.invoke()
        self.assertEqual(partial["phase"], "CONFIG_ONLY")
        self.assertEqual(partial["effect"], "PARTIAL")
        self.assertFalse(partial["receiptCommitted"])
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
        previous = self.binding["expected_selection"]
        selection = {
            "schema": "native-code-selection.v1",
            "generation": previous["generation"] if phase == "PREVIOUS"
                          else self.binding["target_generation"],
            "previous": None if phase == "PREVIOUS" else previous["generation"],
            "sequence": previous["sequence"] if phase == "PREVIOUS"
                        else previous["sequence"] + 1,
        }
        # The native pin source now binds first/second proofs to exact CURRENT
        # pointer identity, not merely the coarse PREVIOUS/SELECTED phase.
        value = dict(self.binding, store=str(store), phase=phase, selection=selection)
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


from private_service_backend_release_test import BackendReleaseFixture


class EnrolledFabricInstallerLockTests(BackendReleaseFixture, unittest.TestCase):
    def installer_args(self):
        manifest = json.loads(self.before[self.roots["manifest"]])
        return SimpleNamespace(
            account=self.account,
            port=manifest["port"],
            source=manifest["source"],
            node=manifest["node"],
            backend=manifest["backend"],
            fabric_only=True,
            modern_fabric_protocol=None,
            enable_repository_workspaces=False,
            os_commission_config_sha256=None,
        )

    def invoke_enrolled(self, operation):
        self.assertIn(self.account, svc.FABRIC_BACKEND_ACCOUNTS)
        self.assertNotIn(self.account, svc.NATIVE_POOL_PIN_ACCOUNTS)
        self.assertEqual(
            svc.FABRIC_BACKEND_ACCOUNTS & svc.NATIVE_POOL_PIN_ACCOUNTS, set()
        )
        real = svc.fcntl.flock
        acquired = []

        def flock(fd, mode):
            value = real(fd, mode)
            if mode & svc.fcntl.LOCK_EX:
                acquired.append(fd)
            return value

        with mock.patch.object(svc.fcntl, "flock", side_effect=flock):
            result = self.capture(lambda: operation(self.installer_args()))
        self.assertEqual(len(acquired), 1)
        self.assertTrue(result.get("staged") or result.get("upgraded"))

    def test_real_enrolled_fabric_stage_uses_one_lock(self):
        self.invoke_enrolled(svc.cmd_stage)

    def test_real_enrolled_fabric_upgrade_uses_one_lock(self):
        self.invoke_enrolled(svc.cmd_upgrade)


# -------------------------------------------------------------------
# The one closed forward Go bridge pin transition.
#
# The helpers below build one real sealed disposable seat and its incumbent
# original pin record. They are shared by the hermetic transaction cases and
# by the real retained-Go proof, so both observe the same owner surfaces.
# -------------------------------------------------------------------


@contextmanager
def launchd_fixture():
    """One positively stopped disposable seat: no loaded launchd job."""
    def run(argv, **kwargs):
        if argv[:2] == ["launchctl", "print"]:
            return svc.CmdResult(
                113, "",
                f'Bad request.\nCould not find service \"{argv[2].rsplit('/', 1)[-1]}\" in domain for user gui: {os.getuid()}\n')
        raise AssertionError("unexpected external effect")
    with mock.patch.object(svc, "_run", run):
        yield


def build_disposable_seat(svc, home, account, pool_path, pool_sha):
    """Install and seal one real disposable Studio seat under a disposable home.

    The incumbent owner writes the runtime, plist, manifest and dependency
    closure, so the forward transaction observes the real sealed profile. Only
    the disposable home is written; no live account, service or credential is
    touched.
    """
    label = "com.mastermind.studio-direct-private." + account
    roots = svc._build_runtime_roots(account)
    source = home / "source"
    source.mkdir()
    for name in svc.STAGE_FILES:
        (source / name).write_text("// fixture " + name + "\n")
    node = home / "node"
    node.write_text("node")
    node.chmod(0o700)
    backend = home / "backend.mjs"
    backend.write_text("backend")
    with redirect_stdout(io.StringIO()):
        svc._write_install(source, node, backend, account, label, "127.0.0.1",
                           45201, roots, result_key="staged", fabric_only=True)
        deps = roots["node_modules"] / "fixture"
        deps.mkdir(parents=True)
        (deps / "index.js").write_text("inert")
        svc.cmd_seal_runtime(SimpleNamespace(account=account))
    config = json.loads(roots["config"].read_bytes())
    config["fleetStatus"] = {
        "enabled": True,
        "launcherPath": str(home / "studio-direct"),
        "launcherSha256": "a" * 64,
        "timeoutMs": 15000,
        "fabricLauncherPath": str(pool_path),
        "fabricLauncherSha256": pool_sha,
        "fabricTimeoutMs": 8000,
    }
    config["opaque_existing_capability"] = {"args": ["PRIVATE-CANARY"], "enabled": True}
    roots["config"].write_bytes(svc._fabric_release_json(config))
    manifest = json.loads(roots["manifest"].read_bytes())
    manifest["configHash"] = svc._sha256_file(roots["config"])
    roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
    return roots, config, manifest


def install_original_pin_record(svc, roots, account, pool_target, successor_digest,
                                original_binding=None):
    """Generate genuine APPLIED snapshots through the incumbent pin owner.

    The unit fixture supplies historical native proof; the real native-Go
    composition supplies its authenticated predecessor projection. The real
    pin owner validates the sealed seat and writes all seven original records.
    """
    owner = svc._pin_owner_module()
    current = json.loads(roots["config"].read_bytes())
    bridge = current["fleetStatus"]["fabricLauncherSha256"]
    if original_binding is None:
        bundle = Path(pool_target).parent / "fixture-original-successor"
        bundle.mkdir(mode=0o700)
        original_binding = {
            "successor_bundle": str(bundle),
            "successor_digest": successor_digest,
            "target_generation": "2" * 64,
            "expected_selection": {
                "schema": "native-code-selection.v1", "generation": "3" * 64,
                "previous": "0" * 64, "sequence": 23},
            "pool_target": pool_target, "pool_previous": "4" * 64,
            "pool_bridge": bridge,
        }
    assert original_binding["pool_bridge"] == bridge
    prior_config = json.loads(roots["config"].read_bytes())
    prior_config["fleetStatus"]["fabricLauncherSha256"] = original_binding["pool_previous"]
    roots["config"].write_bytes(svc._fabric_release_json(prior_config))
    manifest = json.loads(roots["manifest"].read_bytes())
    manifest["configHash"] = svc._sha256_file(roots["config"])
    roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
    args = SimpleNamespace(
        account=account, expected_manifest_sha256=svc._sha256_file(roots["manifest"]),
        successor_bundle=original_binding["successor_bundle"],
        successor_plan_sha256=successor_digest,
        expected_plan_sha256=None, operation="preview")

    @contextmanager
    def historical_context(_):
        yield dict(original_binding, phase="PREVIOUS")

    with mock.patch.object(svc, "_pin_native_context", historical_context):
        preview = owner.run(svc, args)
        args.expected_plan_sha256 = preview["planSha256"]
        args.operation = "apply"
        applied = owner.run(svc, args)
    assert applied["effect"] == "APPLIED" and applied["receiptCommitted"]
    return {"plan_sha256": applied["planSha256"], "binding": original_binding}


class ForwardPinTransitionTests(unittest.TestCase):
    """The closed forward transaction on a real sealed disposable seat.

    Only the native epoch boundary is observed; the pin predecessor, the
    compare-and-swap, the retained record and the admission rules are real.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = (Path(self.temp.name) / "home").resolve()
        self.home.mkdir(mode=0o700)
        patch = mock.patch.object(svc, "_user_root", return_value=self.home)
        patch.start()
        self.addCleanup(patch.stop)
        self.loaded = False
        self.launch_error = False
        self.calls = []
        self.account = getattr(self, "fixture_account", "chatgpt1")
        self.label = "com.mastermind.studio-direct-private." + self.account

        def run(argv, **kwargs):
            self.calls.append(argv)
            if argv[:2] == ["launchctl", "print"]:
                if self.launch_error:
                    return svc.CmdResult(1, "", "private-error")
                if self.loaded:
                    return svc.CmdResult(
                        0,
                        f'{svc._launchd_target(self.label)} = {{\n\tpath = x\n\tstate = running\n\tpid = 1234\n}}\n',
                        "",
                    )
                return svc.CmdResult(
                    113, "",
                    f'Bad request.\nCould not find service "{self.label}" in domain for user gui: {os.getuid()}\n',
                )
            if argv[:2] == ["launchctl", "bootstrap"]:
                self.loaded = True
                return svc.CmdResult(0, "", "")
            raise AssertionError("unexpected external effect")

        patch = mock.patch.object(svc, "_run", run)
        patch.start()
        self.addCleanup(patch.stop)
        self.pool = self.home / "pool"
        self.pool.write_bytes(b"current-native-pool")
        self.pool_bridge = hashlib.sha256(self.pool.read_bytes()).hexdigest()
        self.roots, self.before_config, self.before_manifest = build_disposable_seat(
            svc, self.home, self.account, self.pool, "9" * 64)
        self.original = install_original_pin_record(
            svc, self.roots, self.account, str(self.pool), "1" * 64)
        self.original_bytes = {
            p.name: p.read_bytes()
            for p in (self.roots["state"] / "native-pool-pin").iterdir()
        }
        self.binding = {
            "original_successor": self.original["binding"],
            "go_digest": "a" * 64,
            "go_schema": "native-ingress-go-application-retained.v1",
            "go_generation": "b" * 64,
            "go_expected_selection": {
                "schema": "native-code-selection.v1",
                "generation": "c" * 64,
                "previous": "d" * 64,
                "sequence": 27,
            },
            "go_bootstrap_digest": "e" * 64,
            "go_prior_successor_digest": "1" * 64,
            "go_component_sha256": "f" * 64,
            "go_manifest_sha256": "0" * 64,
            "pool_target": str(self.pool),
            "pool_previous": "9" * 64,
            "pool_bridge": self.pool_bridge,
            "store": str(self.home / "native-code-releases"),
            "phase": "PREVIOUS",
        }
        self.args = SimpleNamespace(
            account=self.account,
            forward_go_bundle=str(self.home / "retained-go"),
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
    def forward_context(self, *args, **kwargs):
        yield self.binding

    def invoke(self):
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            return self.capture(lambda: svc.cmd_native_pool_pin_forward(self.args))

    def prepare(self):
        p = self.invoke()
        self.args.expected_plan_sha256 = p["planSha256"]
        self.args.operation = "apply"
        return p

    def test_preview_is_readonly_redacted_and_binds_the_go_plan(self):
        before = {
            p: p.read_bytes() for p in self.roots["base"].rglob("*") if p.is_file()
        }
        p = self.invoke()
        self.assertEqual(p["effect"], "NOT_APPLIED")
        self.assertEqual(p["phase"], "PREVIEW")
        self.assertEqual(p["goPlanSha256"], self.binding["go_digest"])
        self.assertEqual(p["originalPlanSha256"], self.original["plan_sha256"])
        self.assertEqual(p["poolBridgeSha256"], self.binding["pool_bridge"])
        self.assertNotIn("PRIVATE-CANARY", json.dumps(p))
        self.assertFalse(p["serviceStarted"])
        self.assertEqual(
            before,
            {p: p.read_bytes() for p in self.roots["base"].rglob("*") if p.is_file()},
        )

    def test_apply_changes_only_the_launcher_hash_and_the_config_hash(self):
        self.prepare()
        p = self.invoke()
        self.assertEqual(p["effect"], "APPLIED")
        self.assertEqual(p["phase"], "COMPLETE")
        self.assertTrue(p["receiptCommitted"])
        config = json.loads(self.roots["config"].read_bytes())
        manifest = json.loads(self.roots["manifest"].read_bytes())
        wanted = copy.deepcopy(self.before_config)
        wanted["fleetStatus"]["fabricLauncherSha256"] = self.binding["pool_bridge"]
        self.assertEqual(config, wanted)
        wanted = copy.deepcopy(self.before_manifest)
        wanted["configHash"] = svc._sha256_file(self.roots["config"])
        self.assertEqual(manifest, wanted)
        self.assertFalse(
            any(
                x[:2] in (["launchctl", "bootstrap"], ["launchctl", "bootout"])
                for x in self.calls
            )
        )

    def test_original_pin_record_stays_byte_identical(self):
        self.prepare()
        self.invoke()
        self.assertEqual(
            self.original_bytes,
            {
                p.name: p.read_bytes()
                for p in (self.roots["state"] / "native-pool-pin").iterdir()
            },
        )

    def test_loaded_seat_refuses_before_any_write(self):
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

    def test_second_transaction_is_refused(self):
        self.prepare()
        self.invoke()
        before = self.roots["config"].read_bytes()
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(self.roots["config"].read_bytes(), before)

    def test_preview_after_apply_is_refused(self):
        self.prepare()
        self.invoke()
        self.args.operation = "preview"
        self.args.expected_plan_sha256 = None
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_completed_go_transition_refuses_a_new_forward_transaction(self):
        self.prepare()
        self.binding["phase"] = "SELECTED"
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_unknown_account_refuses(self):
        self.args.account = "unknown-seat"
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_unenrolled_native_pin_account_refuses(self):
        self.args.account = "fabric-design"
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_missing_original_pin_record_refuses(self):
        for name in list(self.original_bytes):
            (self.roots["state"] / "native-pool-pin" / name).unlink()
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_foreign_original_receipt_refuses(self):
        path = self.roots["state"] / "native-pool-pin" / "result.json"
        path.unlink()
        svc._fabric_release_new(path, svc._fabric_release_json(
            {"schema": svc._pin_owner_module().SCHEMA, "planSha256": "0" * 64,
             "effect": "APPLIED"}))
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_already_bound_forward_target_refuses(self):
        config = json.loads(self.roots["config"].read_bytes())
        config["fleetStatus"]["fabricLauncherSha256"] = self.binding["pool_bridge"]
        self.roots["config"].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots["manifest"].read_bytes())
        manifest["configHash"] = svc._sha256_file(self.roots["config"])
        self.roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_changed_pool_target_binding_refuses(self):
        self.binding["pool_target"] = str(self.home / "other-pool")
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_foreign_config_refuses(self):
        self.prepare()
        self.roots["config"].write_text("{}")
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_interrupted_manifest_write_reconciles_the_same_plan(self):
        self.prepare()
        original = svc._atomic_write_bytes

        def write(path, data, **kwargs):
            if path == self.roots["manifest"]:
                raise OSError("PRIVATE-CANARY")
            original(path, data, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.args.operation = "status"
        partial = self.invoke()
        self.assertEqual(partial["phase"], "CONFIG_ONLY")
        self.assertEqual(partial["effect"], "PARTIAL")
        self.assertFalse(partial["receiptCommitted"])
        self.args.operation = "reconcile"
        self.assertEqual(self.invoke()["effect"], "APPLIED")

    def test_foreign_partial_is_never_overwritten(self):
        self.prepare()
        original = svc._atomic_write_bytes

        def write(path, data, **kwargs):
            if path == self.roots["manifest"]:
                raise OSError("PRIVATE-CANARY")
            original(path, data, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.roots["config"].write_bytes(b"foreign")
        self.args.operation = "reconcile"
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertEqual(self.roots["config"].read_bytes(), b"foreign")

    def test_receipt_loss_reconciles_without_rewriting_the_pair(self):
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

    def test_intent_bytes_are_durable_before_the_first_write(self):
        self.prepare()
        original_write = svc._atomic_write_bytes
        original_sync = svc._original_install_sync
        synchronized = set()
        order = []
        tx = self.roots["state"] / "native-pool-pin-forward"

        def sync(path, expected):
            original_sync(path, expected)
            if path.parent == tx:
                synchronized.add(path.name)

        def write(path, data, **kwargs):
            self.assertGreaterEqual(synchronized, {
                "plan.json", "intent.json", "config.before.json", "config.after.json",
                "manifest.before.json", "manifest.after.json"})
            order.append(path.name)
            original_write(path, data, **kwargs)

        with mock.patch.object(svc, "_original_install_sync", sync), \
                mock.patch.object(svc, "_atomic_write_bytes", write):
            self.invoke()
        self.assertEqual(order, ["config.json", "manifest.json"])

    def test_staging_symlink_refuses(self):
        self.prepare()
        (self.roots["state"] / "native-pool-pin-forward").symlink_to(
            self.home, target_is_directory=True)
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_modes_are_preserved(self):
        before = tuple(self.roots[n].stat().st_mode & 0o777
                       for n in ("config", "manifest"))
        self.prepare()
        self.invoke()
        self.assertEqual(before, tuple(self.roots[n].stat().st_mode & 0o777
                                      for n in ("config", "manifest")))

    def test_mode_drift_from_the_original_history_is_refused(self):
        self.roots["config"].chmod(0o400)
        with self.assertRaises(SystemExit):
            self.prepare()

    def test_existing_lifecycle_lock_blocks_apply_without_write(self):
        self.prepare()
        before = self.roots["config"].read_bytes()
        with svc._c2_lifecycle_mutex(self.account):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertEqual(self.roots["config"].read_bytes(), before)

    def test_start_is_held_until_the_completed_go_ingress_is_proven(self):
        self.prepare()
        self.invoke()
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                svc._pin_require_start(self.account, self.roots)
            self.assertFalse(self.loaded)

    def test_start_is_admitted_after_the_exact_completed_go_ingress(self):
        self.prepare()
        self.invoke()
        # The exact completed Go ingress and the live retained-Go bridge.
        self.binding["phase"] = "SELECTED"
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            svc._pin_require_start(self.account, self.roots)

    def test_start_is_refused_when_the_live_bridge_is_not_the_qualified_one(self):
        self.prepare()
        self.invoke()
        self.binding["phase"] = "SELECTED"
        self.pool.write_bytes(b"foreign-pool-bridge")
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                svc._pin_require_start(self.account, self.roots)

    def test_unexpected_owner_error_is_fixed_not_private_text(self):
        with mock.patch.object(
            svc, "_pin_forward_native_context", side_effect=SystemExit("PRIVATE-CANARY")
        ):
            with self.assertRaises(SystemExit) as caught:
                svc.cmd_native_pool_pin_forward(self.args)
        self.assertNotIn("PRIVATE-CANARY", str(caught.exception))

    def _rewrite_original_plan(self, **changed):
        owner = svc._pin_owner_module()
        tx = self.roots["state"] / "native-pool-pin"
        plan = json.loads((tx / "plan.json").read_bytes())
        plan.update(changed)
        identity = owner.plan_sha(svc, plan)
        for name, value in {
            "plan.json": plan,
            "intent.json": {"schema": owner.SCHEMA, "planSha256": identity},
            "result.json": {"schema": owner.SCHEMA, "planSha256": identity,
                            "effect": "APPLIED"},
        }.items():
            (tx / name).write_bytes(svc._fabric_release_json(value))

    def test_complete_original_snapshots_are_required(self):
        tx = self.roots["state"] / "native-pool-pin"
        (tx / "config.before.json").unlink()
        with mock.patch.object(svc, "_atomic_write_bytes",
                               side_effect=AssertionError("unverified history write")):
            with self.assertRaises(SystemExit):
                self.invoke()

    def test_original_postimage_hash_is_authenticated(self):
        tx = self.roots["state"] / "native-pool-pin"
        (tx / "config.after.json").write_bytes(b"{}\n")
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_locally_consistent_foreign_original_successor_is_refused(self):
        self._rewrite_original_plan(successor_digest="8" * 64)
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_locally_consistent_foreign_original_generation_is_refused(self):
        self._rewrite_original_plan(target_generation="8" * 64)
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_old_pin_must_equal_the_authenticated_go_preimage(self):
        config = json.loads(self.roots["config"].read_bytes())
        config["fleetStatus"]["fabricLauncherSha256"] = "6" * 64
        self.roots["config"].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots["manifest"].read_bytes())
        manifest["configHash"] = svc._sha256_file(self.roots["config"])
        self.roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_original_history_change_after_config_write_holds_manifest(self):
        self.prepare()
        original_write = svc._atomic_write_bytes
        before_manifest = self.roots["manifest"].read_bytes()
        tx = self.roots["state"] / "native-pool-pin"
        writes = []

        def write(path, data, **kwargs):
            writes.append(path)
            original_write(path, data, **kwargs)
            if path == self.roots["config"]:
                (tx / "result.json").write_bytes(b"{}\n")

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertEqual(writes, [self.roots["config"]])
        self.assertEqual(self.roots["manifest"].read_bytes(), before_manifest)
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes",
                               side_effect=AssertionError("history changed")):
            with self.assertRaises(SystemExit):
                self.invoke()

    def test_selected_go_recovers_only_the_original_complete_pair_receipt(self):
        self.prepare()
        original_new = svc._fabric_release_new

        def lose_receipt(path, data):
            if path.name == "result.json":
                raise OSError("receipt not acknowledged")
            original_new(path, data)

        with mock.patch.object(svc, "_fabric_release_new", lose_receipt):
            with self.assertRaises(SystemExit):
                self.invoke()
        tx = self.roots["state"] / "native-pool-pin-forward"
        retained = {p.name: p.read_bytes() for p in tx.iterdir()}
        pair = tuple(self.roots[n].read_bytes() for n in ("config", "manifest"))
        self.binding["phase"] = "SELECTED"
        self.args.operation = "reconcile"
        new_files = []

        def record(path, data):
            new_files.append(path.name)
            return original_new(path, data)

        with mock.patch.object(svc, "_atomic_write_bytes",
                               side_effect=AssertionError("selected pair rewrite")), \
                mock.patch.object(svc, "_fabric_release_new", record):
            result = self.invoke()
            self.assertTrue(result["receiptCommitted"])
            self.assertEqual(self.invoke(), result)
        self.assertEqual(new_files, ["result.json"])
        self.assertEqual(pair, tuple(self.roots[n].read_bytes()
                                     for n in ("config", "manifest")))
        for name, data in retained.items():
            self.assertEqual((tx / name).read_bytes(), data)
        self.assertEqual(self.original_bytes, {
            p.name: p.read_bytes()
            for p in (self.roots["state"] / "native-pool-pin").iterdir()})

    def test_selected_go_never_repairs_an_incomplete_pair(self):
        self.prepare()
        original_write = svc._atomic_write_bytes

        def write(path, data, **kwargs):
            if path == self.roots["manifest"]:
                raise OSError("manifest not applied")
            return original_write(path, data, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.binding["phase"] = "SELECTED"
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes",
                               side_effect=AssertionError("selected partial write")):
            with self.assertRaises(SystemExit):
                self.invoke()

    def _assert_sync_failure_recovers(self, name, parent=False):
        self.prepare()
        tx = self.roots["state"] / "native-pool-pin-forward"
        target = self.roots[name] if name in ("config", "manifest") else tx / name
        strict_sync = svc._original_install_sync
        real_fsync = os.fsync
        active = [False]
        failed = [False]
        acknowledgements = []

        def checked_sync(path, expected):
            # Pair faults happen after replacement becomes visible, not on
            # the original preimage that is synchronized before any write.
            postimage = (tx / (name + ".after.json")).read_bytes() if name in (
                "config", "manifest") else expected
            active[0] = path == target and expected == postimage
            try:
                strict_sync(path, expected)
                acknowledgements.append(path)
            finally:
                active[0] = False

        def fsync(fd):
            if active[0] and not failed[0]:
                selected = target.parent if parent else target
                expected = selected.lstat()
                actual = os.fstat(fd)
                if (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino):
                    failed[0] = True
                    raise OSError("injected durability failure")
            return real_fsync(fd)

        with mock.patch.object(svc, "_original_install_sync", checked_sync), \
                mock.patch.object(os, "fsync", fsync):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertTrue(failed[0], "the actual file or parent fsync must be reached")
        self.assertTrue(target.exists(), "bytes are visible despite the failed acknowledgment")
        self.args.operation = "reconcile"
        if name == "result.json":
            pair = tuple(self.roots[n].read_bytes() for n in ("config", "manifest"))
            self.binding["phase"] = "SELECTED"
            with mock.patch.object(svc, "_atomic_write_bytes",
                                   side_effect=AssertionError("pair replayed")), \
                    mock.patch.object(svc, "_fabric_release_new",
                                      side_effect=AssertionError("receipt recreated")), \
                    mock.patch.object(svc, "_original_install_sync", checked_sync):
                self.assertTrue(self.invoke()["receiptCommitted"])
            self.assertEqual(pair, tuple(self.roots[n].read_bytes()
                                         for n in ("config", "manifest")))
        else:
            with mock.patch.object(svc, "_original_install_sync", checked_sync):
                self.assertTrue(self.invoke()["receiptCommitted"])
        self.assertIn(target, acknowledgements)
        self.assertEqual(self.original_bytes, {
            p.name: p.read_bytes()
            for p in (self.roots["state"] / "native-pool-pin").iterdir()})

    def test_visible_intent_file_sync_failure_holds_then_recovers(self):
        self._assert_sync_failure_recovers("intent.json")

    def test_visible_intent_parent_sync_failure_holds_then_recovers(self):
        self._assert_sync_failure_recovers("intent.json", parent=True)

    def test_visible_config_sync_failure_holds_then_recovers(self):
        self._assert_sync_failure_recovers("config")

    def test_visible_manifest_parent_sync_failure_holds_then_recovers(self):
        self._assert_sync_failure_recovers("manifest", parent=True)

    def test_visible_result_file_sync_failure_recovers_without_rewrite(self):
        self._assert_sync_failure_recovers("result.json")

    def test_visible_result_parent_sync_failure_recovers_without_rewrite(self):
        self._assert_sync_failure_recovers("result.json", parent=True)

    def test_status_and_start_hold_when_visible_receipt_cannot_be_synchronized(self):
        self.prepare()
        self.invoke()
        tx = self.roots["state"] / "native-pool-pin-forward"
        original_sync = svc._original_install_sync

        def sync(path, expected):
            if path == tx / "result.json":
                raise OSError("receipt durability unconfirmed")
            return original_sync(path, expected)

        self.binding["phase"] = "SELECTED"
        self.args.operation = "status"
        with mock.patch.object(svc, "_original_install_sync", sync), \
                mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                self.invoke()
            with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_FORWARD_EFFECT_UNKNOWN_DURABILITY"):
                svc._pin_require_start(self.account, self.roots)



REAL_FORWARD_PROOF = '''
"""One real disposable intact or retained Go forward pin proof.

This process owns the real native kit and the real native transition. It
publishes the kit identity, refuses the native apply while one old Studio
seat still pins the old pool bridge, waits for the forward pin to land, then
commits the real selected Go transition exactly once. Native readers, CAS and
admission run against real fixture artifacts; no live path is read.
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(%(repo)r)
RETAINED = %(retained)r
sys.path.insert(0, str(REPO / "ops/native_fabric/quota_continuity/tests"))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "integrations/studio_direct_mcp"))

from test_go_native_install import (  # noqa: F401
    go_owner,
    retained_go_owner,
    assert_retained_history,
    native_stage,
    owner,
)
from test_go_native_stage import builds  # noqa: F401
from test_native_launcher_successor_transition import source_owners  # noqa: F401
import native_generation as g
import native_install as installer
import private_service as svc
from private_service_pin_transition_test import (
    build_disposable_seat,
    install_original_pin_record,
    launchd_fixture,
)

WORK = Path(os.environ["MM_FORWARD_WORK"])
HOME = WORK / "studio-home"
CONSUMERS = HOME / ".local/share/studio-direct-mcp/private"


def wait_for(name, seconds=300):
    path = WORK / name
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return path
        if (WORK / "abort.done").exists():
            raise AssertionError("the forward proof was aborted")
        time.sleep(0.05)
    raise AssertionError("forward proof step did not arrive: " + name)


def test_real_forward_pin_moves_a_seat_onto_the_go_ingress(request):
    case = request.getfixturevalue("retained_go_owner" if RETAINED else "go_owner")
    plan = case.retained_plan if RETAINED else case.go_plan
    bundle = case.retained_bundle if RETAINED else case.go_bundle
    apply = installer.apply_retained_go if RETAINED else installer.apply_go
    if RETAINED:
        assert not case.original.exists()
        with pytest.raises((ValueError, OSError)):
            installer.read_successor(case.successor)
        installer.read_retained_successor_after_bootstrap_prune(case.successor)
        assert_retained_history(case)
    entry = plan["entries"]["pool"]
    account = "chatgpt1"

    with launchd_fixture(), mock.patch.object(svc, "_user_root", return_value=HOME):
        roots, before_config, before_manifest = build_disposable_seat(
            svc, HOME, account, entry["target"], entry["previous"])
        if RETAINED:
            evidence = installer._retained_successor_evidence(
                case.successor, original_absent=True, current_bridges=False)
            prior_bundle, prior = evidence["bundle"], evidence["plan"]
        else:
            prior_bundle, prior, _, _, _ = installer._completed_successor(
                plan["prior_successor_bundle"])
        assert prior["digest"] == plan["prior_successor_digest"]
        assert prior["bootstrap_digest"] == plan["bootstrap_digest"]
        prior_pool = prior["entries"]["pool"]
        original_binding = {
            "successor_bundle": str(prior_bundle),
            "successor_digest": prior["digest"],
            "target_generation": prior["target_generation"],
            "expected_selection": prior["expected_selection"],
            "pool_target": prior_pool["target"],
            "pool_previous": prior_pool["previous"],
            "pool_bridge": prior_pool["bridge"],
        }
        install_original_pin_record(
            svc, roots, account, entry["target"], plan["prior_successor_digest"],
            original_binding=original_binding)
    assert CONSUMERS.is_dir()

    with mock.patch.object(installer.studio_consumer_owner,
                           "STUDIO_CONSUMER_ROOT", CONSUMERS):
        # One old Studio seat still pins the old pool bridge: the real native
        # transition is refused before any ingress write.
        with pytest.raises(ValueError, match="STUDIO_CONSUMER_PIN_MIGRATION_REQUIRED"):
            apply(bundle)
        assert g.current(case.store) == plan["expected_selection"]
        assert not (case.store / "bootstrap/.go-application-ingress-v1.json").exists()

    (WORK / "kit.json").write_text(json.dumps({
        "bundle": str(bundle),
        "store": str(case.store),
        "pool_target": entry["target"],
        "pool_bridge": entry["bridge"],
        "pool_previous": entry["previous"],
        "go_digest": plan["digest"],
        "go_schema": plan["schema"],
        "account": account,
        "retained": RETAINED,
        "retained_pins": case.pins if RETAINED else None,
        "retained_status_plan_digest": case.successor_plan["digest"] if RETAINED else None,
    }))

    wait_for("forward.done")
    with mock.patch.object(installer.studio_consumer_owner,
                           "STUDIO_CONSUMER_ROOT", CONSUMERS):
        receipt = apply(bundle)
    assert receipt["schema"] == (installer.GO_RETAINED_SCHEMA if RETAINED else installer.GO_SCHEMA)
    selected = {"schema": g.POINTER_SCHEMA, "generation": plan["target_generation"],
                "previous": plan["expected_selection"]["generation"],
                "sequence": plan["expected_selection"]["sequence"] + 1}
    assert receipt["selection"] == g.current(case.store) == selected
    assert set(plan["entries"]) == {"pool", "task", "go", "remote"}
    for name, installed in plan["entries"].items():
        expected = installed["previous"] if name == "remote" else installed["bridge"]
        assert g.digest(Path(installed["target"]).read_bytes()) == expected
    if RETAINED:
        # This old public reader must now reject the replaced live bridges.
        # The Studio forward path must instead authenticate retained history.
        with pytest.raises(ValueError):
            installer.read_retained_successor_after_bootstrap_prune(case.successor)
        historical = installer._retained_successor_evidence(
            case.successor, original_absent=True, current_bridges=False)
        assert historical["plan"]["digest"] == plan["prior_successor_digest"]
        assert_retained_history(case)
    (WORK / "applied.json").write_text(json.dumps({
        "receipt": receipt,
        "selection": g.current(case.store),
    }))
    wait_for("proof.done")
    assert g.current(case.store) == selected
    if RETAINED:
        assert_retained_history(case)
'''


class RealIntactGoForwardTests(unittest.TestCase):
    """The positive proof runs the real native owners, not a mock.

    The native kit and the real native transition run in one process under the
    incumbent installer fixture. The forward pin and the start proof run in
    this process, because the incumbent installer fixture forbids process
    creation while it holds the kit. Both sides exchange only bounded
    evidence through the disposable work directory.
    """

    def wait_for(self, name, process, output):
        path = self.work / name
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if path.exists():
                return path
            if process.poll() is not None:
                self.fail("the native proof process ended early:\n" + output())
            time.sleep(0.05)
        self.fail("the forward proof step did not arrive: " + name + "\n" + output())

    def capture(self, fn):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = fn()
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue())

    @contextmanager
    def native_fixture_proof(self, kit):
        """Share only the existing fixture's two trust anchors with its importer.

        The isolated process executes the unchanged generated native proof body
        and actual readers. No production override or synthetic proof JSON exists.
        Unrelated subprocesses are forwarded unchanged.
        """
        if not kit["retained"]:
            yield
            return
        run = subprocess.run
        prefix = (
            "import sys,json\n"
            "sys.path.insert(0,sys.argv[1])\n"
            "import native_install as fixture_owner\n"
            "fixture_owner.RETAINED_STATUS_PROOF_SHA256=json.loads(sys.argv[3])\n"
            "fixture_owner.RETAINED_STATUS_PLAN_DIGEST=sys.argv[4]\n"
        )
        calls = []
        def with_fixture_pins(command, *args, **kwargs):
            if (isinstance(command, (list, tuple)) and "-c" in command
                    and command[0] == sys.executable and command[-1] == kit["bundle"]):
                position = command.index("-c") + 1
                body = command[position]
                if "import native_install as i" in body:
                    self.assertIn("plan,payloads=i.read_retained_go(bundle)", body)
                    adapted = list(command)
                    adapted[position] = prefix + body
                    adapted.extend((json.dumps(kit["retained_pins"], sort_keys=True),
                                    kit["retained_status_plan_digest"]))
                    calls.append(body)
                    return run(adapted, *args, **kwargs)
            return run(command, *args, **kwargs)
        with mock.patch.object(subprocess, "run", with_fixture_pins):
            yield
        self.assertTrue(calls)

    def test_real_forward_pin_commits_with_the_native_go_transition(self):
        self.run_real_forward(False)

    def test_real_forward_pin_commits_after_retained_go_replaces_old_bridges(self):
        self.run_real_forward(True)

    def run_real_forward(self, retained):
        repo = Path(svc.__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            self.work = (Path(temporary) / "forward-proof").resolve()
            self.work.mkdir(mode=0o700)
            home = self.work / "studio-home"
            home.mkdir(mode=0o700)
            proof = self.work / "test_forward_pin_proof.py"
            proof.write_text(REAL_FORWARD_PROOF % {"repo": str(repo), "retained": retained})
            (self.work / "pytest.ini").write_text("[pytest]\n")
            environment = dict(os.environ, MM_FORWARD_WORK=str(self.work))
            process = subprocess.Popen(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "--basetemp", str(self.work / "basetemp"), str(proof)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                cwd=str(self.work), env=environment)
            lines = []

            def output():
                return "".join(lines)[-4000:]

            def drain():
                for line in process.stdout:
                    lines.append(line)

            import threading
            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            try:
                kit = json.loads(
                    self.wait_for("kit.json", process, output).read_bytes())
                with self.native_fixture_proof(kit):
                    account = kit["account"]
                    with launchd_fixture(), mock.patch.object(svc, "_user_root", return_value=home):
                        roots = svc._build_runtime_roots(account)
                        args = SimpleNamespace(
                            account=account,
                            forward_go_bundle=kit["bundle"],
                            expected_plan_sha256=None,
                            operation="preview")
                        preview = self.capture(
                            lambda: svc.cmd_native_pool_pin_forward(args))
                        self.assertEqual(preview["effect"], "NOT_APPLIED")
                        self.assertEqual(preview["goPlanSha256"], kit["go_digest"])
                        args.expected_plan_sha256 = preview["planSha256"]
                        args.operation = "apply"
                        applied = self.capture(
                            lambda: svc.cmd_native_pool_pin_forward(args))
                        self.assertEqual(applied["effect"], "APPLIED")
                        self.assertEqual(applied["poolBridgeSha256"], kit["pool_bridge"])
                        config = json.loads(roots["config"].read_bytes())
                        self.assertEqual(
                            config["fleetStatus"]["fabricLauncherSha256"],
                            kit["pool_bridge"])
                        # The prepared seat is start-held until the completed Go.
                        with self.assertRaises(SystemExit):
                            svc._pin_require_start(account, roots)
                    (self.work / "forward.done").write_text("ok")
                    applied_evidence = json.loads(
                        self.wait_for("applied.json", process, output).read_bytes())
                    self.assertEqual(
                        applied_evidence["receipt"]["schema"],
                        kit["go_schema"])
                    with launchd_fixture(), mock.patch.object(svc, "_user_root", return_value=home):
                        roots = svc._build_runtime_roots(account)
                        # The same source path now proves start readiness and the
                        # exact retained/intact identity after bridge replacement.
                        args.operation = "status"
                        with svc._pin_forward_native_context(args) as binding:
                            self.assertEqual(binding["phase"], "SELECTED")
                            self.assertEqual(binding["go_schema"], kit["go_schema"])
                            self.assertEqual(binding["go_digest"], kit["go_digest"])
                        svc._pin_require_start(account, roots)
                    (self.work / "proof.done").write_text("ok")
            finally:
                (self.work / "abort.done").write_text("ok")
                try:
                    process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=60)
                reader.join(timeout=30)
                if process.stdout is not None:
                    process.stdout.close()
            self.assertEqual(process.returncode, 0, output())


if __name__ == "__main__":
    unittest.main()
