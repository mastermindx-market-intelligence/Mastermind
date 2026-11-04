"""C4 enrollment tests: real temp files and owner code; no host installation.

Exact production profile/source digests are substituted with inert fixture bytes.
Only native epoch proof and launchctl are mocked; transaction parsing, original
pin transformation, file seals, locks, writes and startup validators are real.
"""
import copy
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc
import private_service_pin_enrollment as owner


class EnrollmentContractTests(unittest.TestCase):
    def test_exact_source_generation_is_independent_of_generic_targets(self):
        self.assertEqual(owner.ACCOUNT, "chatgpt4")
        self.assertEqual(owner.BEFORE_MANIFEST, "168bb25afd7d710799fb86f8912389d49c86371c107ee9544d65fdc2b9d390e2")
        self.assertEqual(owner.BEFORE_CONFIG, "f02e385e234f7f88619058485b61f17834d3cfc33896ce3f5606bd64fcecce21")
        self.assertEqual(owner.ORIGINAL_PLAN, "4732de6c370ca3385d17749e411f634d149b7701971219baea65707d6c069818")
        self.assertEqual(owner.TARGET_FILES, {
            "gateway.mjs": "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30",
            "git-publish.mjs": "f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c",
            "workspace-access.mjs": "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
        })
        self.assertIsNot(owner.TARGET_FILES, svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256)

    def test_fixed_enrollment_matches_existing_catalog_without_new_destinations(self):
        home = Path("/Users/c4-fixture")
        before = {"accountLabel": "chatgpt4", "gitPublish": svc._typed_git_config(home),
                  "preserved": {"value": 7}}
        after = owner.target_config(home, before)
        expected = svc._typed_git_config(home, closed_repositories=True)
        expected["commandTimeoutMs"] = 45000
        self.assertEqual(after["gitPublish"], expected)
        self.assertEqual(before["gitPublish"]["commandTimeoutMs"], 15000)
        self.assertEqual(after["gitPublish"]["pushTimeoutMs"], 60000)
        self.assertEqual(after["repositoryWorkspaces"], {
            "enabled": True, "allowedRepositories": ["mastermind", "macro", "terminal"]})
        self.assertEqual(after["preserved"], before["preserved"])
        self.assertNotIn("repositoryWorkspaces", before)

    def test_cli_selects_only_frozen_accounts_and_no_repository_or_lifecycle_arguments(self):
        args = svc.build_parser().parse_args([
            "native-pool-pin-enrollment", "--account", "chatgpt4", "--operation", "preview",
            "--expected-manifest-sha256", owner.BEFORE_MANIFEST, "--source", "/fixture"])
        self.assertEqual(args.func, svc.cmd_native_pool_pin_enrollment)
        self.assertFalse(hasattr(args, "repository"))
        admin = svc.build_parser().parse_args([
            "native-pool-pin-enrollment", "--account", "admin-business",
            "--operation", "preview",
            "--expected-manifest-sha256", owner.PROFILES["admin-business"]["before_manifest"],
            "--source", "/fixture"])
        self.assertEqual(admin.func, svc.cmd_native_pool_pin_enrollment)
        self.assertFalse(hasattr(admin, "repository"))
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                svc.build_parser().parse_args([
                    "native-pool-pin-enrollment", "--account", "chatgpt2-business",
                    "--operation", "status", "--expected-manifest-sha256", owner.BEFORE_MANIFEST])


class AdminBusinessProfileTests(unittest.TestCase):
    """Frozen admin account transformation; live owner preflight is a separate proof."""

    def test_original_pin_identity_and_config_are_exact(self):
        profile = owner.frozen_profile("admin-business")
        self.assertEqual(profile["generation"], "admin-business-closed-repositories-20261104-v1")
        self.assertEqual(profile["port"], 45030)
        self.assertEqual(profile["before_manifest"],
                         "35903622d2e10b3ba56aedbf64cc2484d8b53bdb67ab71a8e0f9b0b7ebacc148")
        self.assertEqual(profile["before_config"],
                         "2f0fd933062a0168093caa6a675dc27c91746837701fd28d74b7baf5ff3f4863")
        self.assertEqual(profile["original_plan"],
                         "25870fe238760b16ccc41b005c3a4289b8327dbe5a4d8b10015c00faaac15bac")

    def test_admin_config_preserves_unrelated_bytes_and_closes_repos(self):
        home = Path("/Users/admin-fixture")
        before = {"accountLabel": "admin-business", "gitPublish": svc._typed_git_config(home),
                  "preserved": {"opaque": True}}
        after = owner.target_config(home, before, owner.frozen_profile("admin-business"))
        self.assertEqual(after["preserved"], before["preserved"])
        self.assertEqual([r["repository"] for r in after["gitPublish"]["repositories"]],
                         ["mastermind", "macro", "terminal"])
        self.assertEqual(after["repositoryWorkspaces"]["allowedRepositories"],
                         ["mastermind", "macro", "terminal"])
        self.assertEqual(after["gitPublish"]["commandTimeoutMs"], 45000)
        self.assertEqual(after["gitPublish"]["pushTimeoutMs"], 60000)
        self.assertNotIn("repositoryWorkspaces", before)

    def test_account_mismatch_refuses_closed_config(self):
        home = Path("/Users/admin-fixture")
        before = {"accountLabel": "chatgpt4", "gitPublish": svc._typed_git_config(home)}
        with self.assertRaisesRegex(SystemExit, "PROFILE_REFUSED"):
            owner.target_config(home, before, owner.frozen_profile("admin-business"))

    def test_no_other_account_can_consume_this_enrollment(self):
        for account in ("chatgpt1", "chatgpt2-business", "chatgpt2-personal",
                        "chatgpt3", "fabric-read", "admin-business-2"):
            with self.subTest(account=account), self.assertRaisesRegex(
                SystemExit, "INPUT_REFUSED"
            ):
                owner.frozen_profile(account)

    def test_c4_original_profile_stays_pinned(self):
        profile = owner.frozen_profile("chatgpt4")
        self.assertEqual(profile["generation"], owner.GENERATION)
        self.assertEqual(profile["before_manifest"], owner.BEFORE_MANIFEST)
        self.assertEqual(profile["before_config"], owner.BEFORE_CONFIG)
        self.assertEqual(profile["original_plan"], owner.ORIGINAL_PLAN)


class EnrollmentTests(unittest.TestCase):
    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def capture(self, fn):
        stream = io.StringIO()
        with redirect_stdout(stream):
            self.assertEqual(fn(), 0)
        return json.loads(stream.getvalue())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        self.patch(svc, "_user_root", lambda: self.home)
        self.patch(svc, "_pin_enrollment_owner_module", lambda: owner)
        self.account = "chatgpt4"
        self.label = "com.mastermind.studio-direct-private.chatgpt4"
        self.roots = svc._build_runtime_roots(self.account)
        self.loaded = False
        self.ambiguous = False
        self.calls = []
        self.native_operations = []
        self.real_native_context = svc._pin_native_context

        def launchctl(argv, **kwargs):
            self.calls.append(argv)
            if argv[:2] == ["launchctl", "print"]:
                if self.ambiguous:
                    return svc.CmdResult(1, "", "PRIVATE-CANARY")
                if self.loaded:
                    return svc.CmdResult(0, f'{svc._launchd_target(self.label)} = {{\n\tpath = {self.roots["plist"]}\n\tstate = running\n\tpid = 1234\n}}\n', "")
                return svc.CmdResult(113, "", f'Bad request.\nCould not find service "{self.label}" in domain for user gui: {os.getuid()}\n')
            if argv[:2] == ["launchctl", "bootstrap"]:
                self.loaded = True
                return svc.CmdResult(0, "", "")
            raise AssertionError("unexpected external effect")

        self.patch(svc, "_run", launchctl)
        source = self.home / "initial-source"
        source.mkdir()
        for name in set(svc.STAGE_FILES) | set(svc.C2_PAPER_FILES_SHA256):
            (source / name).write_bytes(("// original fixture " + name).encode())
        node = self.home / "node"
        node.write_bytes(b"inert node")
        node.chmod(0o700)
        backend = self.home / "backend.mjs"
        backend.write_bytes(b"inert backend")
        self.capture(lambda: svc._write_install(
            source, node, backend, self.account, self.label, "127.0.0.1", 45024,
            self.roots, result_key="staged", fabric_only=True))
        deps = self.roots["node_modules"] / "fixture"
        deps.mkdir(parents=True)
        (deps / "index.js").write_bytes(b"inert dependency")
        self.capture(lambda: svc.cmd_seal_runtime(SimpleNamespace(account=self.account)))
        original_modules = {}
        for name in svc.C2_PAPER_FILES_SHA256:
            data = (source / name).read_bytes()
            svc._atomic_write_bytes(self.roots["base"] / name, data)
            original_modules[name] = owner.digest(data)
        # The original eleven-file cohort has no adapter at all.
        adapter = self.roots["base"] / "workspace-access.mjs"
        if adapter.exists():
            adapter.unlink()
        self.pool = self.home / "pool"
        self.pool.write_bytes(b"old-native-pool")
        self.future_pool = b"selected-native-pool"
        config = json.loads(self.roots["config"].read_bytes())
        config.pop("fabricOnly", None)
        config["gitPublish"] = svc._typed_git_config(self.home)
        config["fleetStatus"] = {
            "enabled": True, "launcherPath": str(self.home / "studio-direct"),
            "launcherSha256": "a" * 64, "timeoutMs": 15000,
            "fabricLauncherPath": str(self.pool), "fabricLauncherSha256": "9" * 64,
            "fabricTimeoutMs": 8000,
        }
        config["fleetRouting"] = {"enabled": True, "routes": ["fixture-3", "fixture-4"]}
        config["paperDesign"] = {"preserved": True, "fixture": "PRIVATE-CANARY"}
        config["maxPerSessionConcurrency"] = 8
        config["maxQueuedPerSession"] = 16
        self.roots["config"].write_bytes(owner.encode(config))
        manifest = json.loads(self.roots["manifest"].read_bytes())
        manifest["files"] = original_modules
        manifest["configHash"] = owner.digest(owner.encode(config))
        self.roots["manifest"].write_bytes(owner.encode(manifest))
        self.patch(svc, "C2_PAPER_FILES_SHA256", original_modules)
        self.patch(svc, "C4_PAPER_RUNTIME_IDENTITY", {key: manifest[key] for key in (
            "host", "port", "nodeHash", "backendHash", "dependencyTreeHash")})
        self.binding = {
            "successor_digest": "1" * 64, "target_generation": "2" * 64,
            "expected_selection": {"generation": "3" * 64, "sequence": 23},
            "pool_target": str(self.pool), "pool_previous": owner.digest(self.pool.read_bytes()),
            "pool_bridge": owner.digest(self.future_pool), "phase": "PREVIOUS",
        }
        after_config = copy.deepcopy(config)
        after_config["fleetStatus"]["fabricLauncherSha256"] = self.binding["pool_bridge"]
        after_manifest = copy.deepcopy(manifest)
        after_manifest["configHash"] = owner.digest(owner.encode(after_config))
        self.patch(svc, "C4_PAPER_MANIFEST_CANONICAL_SHA256", frozenset((
            svc._canonical_json_sha256(manifest), svc._canonical_json_sha256(after_manifest))))

        @contextmanager
        def native(args):
            self.native_operations.append(args.operation)
            yield self.binding

        self.patch(svc, "_pin_native_context", native)
        pin_args = SimpleNamespace(
            account=self.account, expected_manifest_sha256=owner.digest(owner.encode(manifest)),
            successor_bundle=str(self.home / "successor"), successor_plan_sha256="1" * 64,
            operation="preview", expected_plan_sha256=None)
        preview = self.capture(lambda: svc.cmd_native_pool_pin(pin_args))
        pin_args.expected_plan_sha256 = preview["planSha256"]
        pin_args.operation = "apply"
        self.capture(lambda: svc.cmd_native_pool_pin(pin_args))
        self.pool.write_bytes(self.future_pool)
        self.binding["phase"] = "SELECTED"
        self.pin_path = self.roots["state"] / "native-pool-pin"
        self.original_receipt = {p.name: p.read_bytes() for p in self.pin_path.iterdir()}
        self.before_manifest = self.roots["manifest"].read_bytes()
        self.before_config = self.roots["config"].read_bytes()
        self.patch(owner, "BEFORE_MANIFEST", owner.digest(self.before_manifest))
        self.patch(owner, "BEFORE_CONFIG", owner.digest(self.before_config))
        self.patch(owner, "ORIGINAL_PLAN", owner.digest(self.original_receipt["plan.json"]))
        self.payload = self.home / "payload"
        self.payload.mkdir(mode=0o700)
        targets = {}
        for name in owner.TARGET_FILES:
            data = ("// qualified target fixture " + name).encode()
            (self.payload / name).write_bytes(data)
            targets[name] = owner.digest(data)
        self.patch(owner, "TARGET_FILES", targets)
        self.args = SimpleNamespace(account=self.account, operation="preview", source=str(self.payload),
                                    expected_manifest_sha256=owner.BEFORE_MANIFEST, expected_plan_sha256=None)
        self.tx = self.roots["state"] / owner.TRANSACTION
        self.native_operations.clear()
        self.calls.clear()

    def invoke(self):
        return self.capture(lambda: svc.cmd_native_pool_pin_enrollment(self.args))

    def prepare(self):
        result = self.invoke()
        self.args.expected_plan_sha256 = result["planSha256"]
        self.args.operation = "apply"
        return result

    def applied(self):
        self.prepare()
        return self.invoke()

    def snapshot(self):
        return {str(p.relative_to(self.home)): (p.read_bytes(), p.stat().st_mode)
                for p in self.home.rglob("*") if p.is_file()}

    def start(self):
        return self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))

    def test_loaded_preview_has_zero_writes_and_no_private_text(self):
        self.loaded = True
        before = self.snapshot()
        value = self.invoke()
        self.assertEqual(value["effect"], "NOT_APPLIED")
        self.assertEqual(value["phase"], "PREVIEW")
        self.assertNotIn("PRIVATE-CANARY", json.dumps(value))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.native_operations, ["status"])

    def test_apply_preserves_original_chain_unrelated_files_and_configuration(self):
        before = self.snapshot()
        value = self.applied()
        self.assertEqual(value["effect"], "APPLIED")
        self.assertTrue(value["resultCommitted"])
        self.assertFalse(value["clientAdoptionProven"])
        self.assertEqual(self.original_receipt, {p.name: p.read_bytes() for p in self.pin_path.iterdir()})
        after = json.loads(self.roots["config"].read_bytes())
        wanted = owner.target_config(self.home, json.loads(self.before_config))
        self.assertEqual(after, wanted)
        changed_paths = {str(owner.destination(self.roots, name).relative_to(self.home)) for name in owner.ORDER}
        for name, data in before.items():
            if name not in changed_paths:
                self.assertEqual(self.snapshot()[name], data)
        svc._verify_native_pin_install(self.account, self.label, self.roots)
        self.assertIn("apply", self.native_operations)
        self.assertFalse(any(call[:2] in (["launchctl", "bootstrap"], ["launchctl", "bootout"]) for call in self.calls))
        self.start()
        self.assertTrue(self.loaded)

    def test_loaded_apply_refuses_before_transaction(self):
        self.prepare()
        self.loaded = True
        with self.assertRaisesRegex(SystemExit, "SERVICE_LOADED"):
            self.invoke()
        self.assertFalse(self.tx.exists())
        self.assertEqual(self.roots["config"].read_bytes(), self.before_config)

    def test_ambiguous_lifecycle_refuses_without_leaking_stderr(self):
        self.prepare()
        self.ambiguous = True
        with self.assertRaises(SystemExit) as error:
            self.invoke()
        self.assertNotIn("PRIVATE-CANARY", str(error.exception))
        self.assertFalse(self.tx.exists())

    def test_wrong_input_and_stale_plan_refuse(self):
        self.prepare()
        for key, value in (("account", "chatgpt2-business"), ("expected_manifest_sha256", "f" * 64),
                           ("expected_plan_sha256", "e" * 64), ("operation", "rollback")):
            with self.subTest(key=key), mock.patch.object(self.args, key, value):
                with self.assertRaises(SystemExit):
                    self.invoke()
                self.assertFalse(self.tx.exists())

    def test_source_hash_drift_refuses(self):
        (self.payload / "gateway.mjs").write_bytes(b"foreign source")
        with self.assertRaisesRegex(SystemExit, "SOURCE_REFUSED"):
            self.invoke()
        self.assertFalse(self.tx.exists())

    def test_source_symlink_and_foreign_home_refuse(self):
        source = self.payload / "gateway.mjs"
        source.unlink()
        source.symlink_to(self.roots["base"] / "gateway.mjs")
        with self.assertRaises(SystemExit):
            self.invoke()
        with mock.patch.object(self.args, "source", str(self.home.parent)):
            with self.assertRaisesRegex(SystemExit, "SOURCE_REFUSED"):
                self.invoke()

    def test_new_module_must_be_absent_not_a_dangling_link(self):
        (self.roots["base"] / "workspace-access.mjs").symlink_to(self.home / "absent")
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            self.invoke()

    def test_original_receipt_and_selected_pool_are_not_hash_only_claims(self):
        for field, value in (("phase", "PREVIOUS"), ("target_generation", "f" * 64)):
            with self.subTest(field=field), mock.patch.dict(self.binding, {field: value}):
                with self.assertRaises(SystemExit):
                    self.invoke()
        self.pool.write_bytes(b"foreign bridge")
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_original_receipt_tamper_refuses(self):
        (self.pin_path / "result.json").write_bytes(owner.encode({"effect": "APPLIED"}))
        with self.assertRaises(SystemExit):
            self.invoke()

    def test_foreign_original_pin_file_refuses(self):
        (self.pin_path / "foreign.json").write_bytes(b"{}")
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_REFUSED"):
            self.invoke()

    def test_unrelated_installed_bytes_refuse(self):
        for path in (self.roots["base"] / "fleet-routing.mjs", Path(json.loads(self.before_manifest)["backend"])):
            original = path.read_bytes()
            path.write_bytes(b"foreign static byte")
            with self.subTest(path=path.name), self.assertRaisesRegex(SystemExit, "STATIC_SEAL_REFUSED"):
                self.invoke()
            path.write_bytes(original)

    def test_existing_lifecycle_lock_prevents_apply(self):
        self.prepare()
        with svc._c2_lifecycle_mutex(self.account), self.assertRaises(SystemExit):
            self.invoke()
        self.assertFalse(self.tx.exists())

    def test_native_context_keeps_exact_modifying_lock_verb(self):
        self.applied()
        self.args.operation = "reconcile"
        self.invoke()
        self.assertEqual(self.native_operations, ["status", "apply", "reconcile"])

    def test_apply_is_single_use_and_status_is_readonly(self):
        self.applied()
        with self.assertRaisesRegex(SystemExit, "RECONCILIATION_REQUIRED"):
            self.invoke()
        self.args.operation = "status"
        before = self.snapshot()
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.assertEqual(self.snapshot(), before)

    def test_all_intent_files_precede_installation_writes(self):
        self.prepare()
        original = svc._atomic_write_bytes
        order = []

        def write(path, data, **kwargs):
            self.assertEqual(set(p.name for p in self.tx.iterdir()), owner.FILES - {"result.json"})
            order.append(path)
            original(path, data, **kwargs)

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            self.invoke()
        self.assertEqual(order, [owner.destination(self.roots, name) for name in owner.ORDER])

    def crash_at(self, index, after):
        self.prepare()
        original = svc._atomic_write_bytes
        target = owner.destination(self.roots, owner.ORDER[index])

        def write(path, data, **kwargs):
            if path == target and not after:
                raise OSError("PRIVATE-CANARY")
            original(path, data, **kwargs)
            if path == target and after:
                raise OSError("PRIVATE-CANARY")

        with mock.patch.object(svc, "_atomic_write_bytes", write):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        self.assertEqual(self.original_receipt, {p.name: p.read_bytes() for p in self.pin_path.iterdir()})
        self.args.operation = "status"
        status = self.invoke()
        self.assertEqual(status["completedWrites"], index + int(after))
        self.assertFalse(status["resultCommitted"])
        with self.assertRaises((SystemExit, OSError)):
            self.start()
        self.assertFalse(self.loaded)
        self.args.operation = "reconcile"
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.start()
        self.assertTrue(self.loaded)

    def test_receipt_loss_is_unknown_until_same_transaction_reconciliation(self):
        self.prepare()
        original = svc._fabric_release_new

        def write(path, data):
            if path == self.tx / "result.json":
                raise OSError("PRIVATE-CANARY")
            return original(path, data)

        with mock.patch.object(svc, "_fabric_release_new", write):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        self.args.operation = "status"
        self.assertEqual(self.invoke()["effect"], "EFFECT_UNKNOWN")
        with self.assertRaises(SystemExit):
            self.start()
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed")):
            self.assertEqual(self.invoke()["effect"], "APPLIED")

    def test_completed_result_cannot_attest_restored_old_bytes(self):
        self.applied()
        self.roots["manifest"].write_bytes(self.before_manifest)
        self.args.operation = "reconcile"
        with self.assertRaisesRegex(SystemExit, "RESULT_REFUSED"):
            self.invoke()
        self.assertEqual(self.roots["manifest"].read_bytes(), self.before_manifest)

    def test_foreign_partial_bytes_are_never_overwritten(self):
        self.prepare()
        original = svc._atomic_write_bytes
        def write(path, data, **kwargs):
            if path.name == "git-publish.mjs":
                raise OSError("fixture crash")
            original(path, data, **kwargs)
        with mock.patch.object(svc, "_atomic_write_bytes", write), self.assertRaises(SystemExit):
            self.invoke()
        target = self.roots["base"] / "gateway.mjs"
        target.write_bytes(b"foreign gateway")
        self.args.operation = "reconcile"
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            self.invoke()
        self.assertEqual(target.read_bytes(), b"foreign gateway")

    def test_non_prefix_mixture_is_foreign(self):
        self.prepare()
        original = svc._atomic_write_bytes
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=OSError("stop")), self.assertRaises(SystemExit):
            self.invoke()
        original(self.roots["base"] / "git-publish.mjs", (self.payload / "git-publish.mjs").read_bytes())
        self.args.operation = "reconcile"
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            self.invoke()

    def test_missing_successor_receipt_does_not_bypass_original_start_guard(self):
        self.applied()
        self.tx.rename(self.roots["state"] / "fixture-moved-enrollment")
        with self.assertRaises(SystemExit):
            self.start()
        self.assertFalse(self.loaded)

    def test_future_generic_target_and_policy_changes_do_not_break_completed_generation(self):
        self.applied()
        with mock.patch.object(svc, "FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256", {"git-publish.mjs": "f" * 64}), \
             mock.patch.object(svc, "C2_BUSINESS_TARGET_PATCH_SHA256", {}), \
             mock.patch.object(svc, "_typed_git_config", side_effect=AssertionError("moving policy used")):
            self.args.operation = "status"
            self.assertEqual(self.invoke()["effect"], "APPLIED")
            self.start()
            self.assertTrue(self.loaded)

    def test_generic_restage_remains_refused(self):
        self.applied()
        with self.assertRaisesRegex(SystemExit, "REQUIRES_PIN_OWNER"):
            svc._pin_reject_generic_restage(self.account)

    def test_source_payload_not_required_after_completed_transaction(self):
        self.applied()
        for path in self.payload.iterdir():
            path.unlink()
        self.args.source = None
        self.args.operation = "status"
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.start()

    def test_preparation_interruption_is_retained_without_installation_changes(self):
        self.prepare()
        before = {name: owner.destination(self.roots, name).read_bytes()
                  for name in owner.ORDER if name != "workspace-access.mjs"}
        original = svc._fabric_release_new
        def write(path, data):
            if path == self.tx / "config.after":
                raise OSError("PRIVATE-CANARY")
            return original(path, data)
        with mock.patch.object(svc, "_fabric_release_new", write):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        self.assertTrue(self.tx.exists())
        for name, raw in before.items():
            self.assertEqual(owner.destination(self.roots, name).read_bytes(), raw)
        self.assertFalse((self.roots["base"] / "workspace-access.mjs").exists())
        with self.assertRaisesRegex(SystemExit, "RECONCILIATION_REQUIRED"):
            self.invoke()
        self.args.operation = "reconcile"
        with self.assertRaisesRegex(SystemExit, "TRANSACTION_REFUSED"):
            self.invoke()
        with self.assertRaises(SystemExit):
            self.start()

    def test_owner_exit_failure_after_commit_is_not_reported_as_pre_effect_refusal(self):
        self.prepare()
        original = owner.original_pin
        @contextmanager
        def fail_after(svc_arg, roots, operation, profile):
            with original(svc_arg, roots, operation, profile) as value:
                yield value
            raise SystemExit("PRIVATE-CANARY")
        with mock.patch.object(owner, "original_pin", fail_after):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        self.args.operation = "status"
        self.assertEqual(self.invoke()["effect"], "APPLIED")

    def test_changed_file_modes_refuse_without_writing(self):
        self.prepare()
        path = self.roots["base"] / "gateway.mjs"
        path.chmod(0o640)
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            self.invoke()
        self.assertFalse(self.tx.exists())

    def test_malformed_retained_plan_is_redacted(self):
        self.applied()
        (self.tx / "plan.json").write_bytes(b'{"schema":"PRIVATE-CANARY"}')
        self.args.operation = "status"
        with self.assertRaises(SystemExit) as error:
            self.invoke()
        self.assertNotIn("PRIVATE-CANARY", str(error.exception))


for _index, _name in enumerate(owner.ORDER):
    for _after in (False, True):
        def _test(self, index=_index, after=_after):
            self.crash_at(index, after)
        setattr(EnrollmentTests, "test_crash_" + ("after_" if _after else "before_")
                + _name.replace(".", "_"), _test)


if __name__ == "__main__":
    unittest.main()
