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


WORKSPACE_PREIMAGES = {'chatgpt3-w570f6f34': (45032, 'aa24bddbad7e989cedf566f4fbf4288fa333ee8fac8d2585cdcd9c954736eab3', '6e527360ba76034d0bde30943cb1025f82489525445bcac2ab86c8b190df8fbc', '1239d26202ea93279e356578910fd6ca326006cf39db41b82aefd3fb16213051'), 'chatgpt3-wa2a9e6f9': (45034, '38d5427f418f9f3f7aa1ff671befa55555f276cd4b639a6312e24fa0672965a3', '4e9aad915c1ea46e5de79c158d233d911e5aef7832d2016a2616a2996fa8fa68', 'bf798b50b2c25df035c6ddd7d4e9a09db8246423a2176c1983fdde56f8c2da45')}

class ChatGPT3WorkspaceBatchProfilesTests(unittest.TestCase):
    """Frozen, exact-account enrollment profiles; no account or repo globbing."""

    def test_two_exact_installed_preimages(self):
        for account, expected in WORKSPACE_PREIMAGES.items():
            with self.subTest(account=account):
                p=owner.frozen_profile(account)
                self.assertEqual((p["port"], p["before_manifest"],
                                  p["before_config"],p["original_plan"]), expected)
                self.assertEqual(p["account"], account)
                self.assertEqual(p["generation"],
                                 "chatgpt3-workspaces-closed-repositories-20261104-v1")

    def test_both_keep_immutable_three_repositories_and_timeouts(self):
        home=Path("/Users/fixture")
        original={"gitPublish":svc._typed_git_config(home), "survives":{"opaque":True}}
        for account in WORKSPACE_PREIMAGES:
            with self.subTest(account=account):
                p=owner.frozen_profile(account)
                before={**original,"accountLabel":account}
                after=owner.target_config(home,before,p)
                self.assertEqual(after["survives"],before["survives"])
                self.assertEqual([r["repository"] for r in after["gitPublish"]["repositories"]],
                                 ["mastermind","macro","terminal"])
                self.assertEqual(after["repositoryWorkspaces"]["allowedRepositories"],
                                 ["mastermind","macro","terminal"])
                self.assertEqual(after["gitPublish"]["commandTimeoutMs"],45000)
                self.assertEqual(after["gitPublish"]["pushTimeoutMs"],60000)
                self.assertNotIn("repositoryWorkspaces",before)

    def test_wrong_account_label_refused_even_with_matching_legacy_git(self):
        home=Path("/Users/fixture")
        for account in WORKSPACE_PREIMAGES:
            with self.subTest(account=account):
                other=next(x for x in WORKSPACE_PREIMAGES if x!=account)
                before={"accountLabel":other,"gitPublish":svc._typed_git_config(home)}
                with self.assertRaisesRegex(SystemExit, "PROFILE_REFUSED"):
                    owner.target_config(home,before,owner.frozen_profile(account))

    def test_only_exact_four_owner_profiles_not_glob_or_other_seats(self):
        self.assertEqual(set(owner.PROFILES),
                         {"chatgpt4","admin-business",*WORKSPACE_PREIMAGES})
        for excluded in ("chatgpt1", "chatgpt2-business", "chatgpt2-personal",
                         "chatgpt3","chatgpt3-unknown","fabric-read","admin-business-2"):
            with self.subTest(account=excluded),self.assertRaisesRegex(
                    SystemExit,"INPUT_REFUSED"):
                owner.frozen_profile(excluded)

    def test_cli_has_two_frozen_workspace_accounts_not_repository_input(self):
        for account in WORKSPACE_PREIMAGES:
            with self.subTest(account=account):
                a=svc.build_parser().parse_args([
                    "native-pool-pin-enrollment","--account",account,
                    "--operation","preview","--expected-manifest-sha256",
                    owner.frozen_profile(account)["before_manifest"],"--source","/fixture"])
                self.assertEqual(a.func,svc.cmd_native_pool_pin_enrollment)
                self.assertFalse(hasattr(a,"repository"))


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

    def _select_paper_after_enrollment(self):
        """Test-only exact Paper-v20 selection after one completed C4 enrollment."""
        self.applied()
        raw_c = (self.tx / "config.after").read_bytes()
        raw_m = (self.tx / "manifest.after").read_bytes()
        current = json.loads(raw_c)
        current_manifest = json.loads(raw_m)
        old_paper = copy.deepcopy(current["paperDesign"])
        new_paper = {
            "enabled": True,
            "bridgeSha256": svc.PAPER_V20_BRIDGE_SHA256,
            "bridgePath": str(self.home / ".local/share/mastermind-paper/runtime/v20/source/bridge.py"),
            "pythonPath": str(self.home / ".local/share/mastermind-paper/runtime/v20/venv/bin/python"),
            "appPath": str(self.home / "Applications/Paper.app"),
            "commandTimeoutMs": 70000,
        }
        def paper(_home, *, rel=None, bridge_sha256=None):
            if rel is None:
                return old_paper
            if rel != svc.PAPER_RUNTIME_V20_REL or bridge_sha256 != svc.PAPER_V20_BRIDGE_SHA256:
                raise AssertionError("foreign Paper runtime request")
            return new_paper
        self.patch(svc, "_paper_design_config", paper)
        after = copy.deepcopy(current)
        after["paperDesign"] = new_paper
        future = copy.deepcopy(current_manifest)
        future["configHash"] = owner.digest(owner.encode(after))
        new_config = owner.encode(after)
        new_manifest = owner.encode(future)
        self.patch(owner, "C4_ENROLLED_CONFIG_SHA256", owner.digest(raw_c))
        self.patch(owner, "C4_ENROLLED_MANIFEST_SHA256", owner.digest(raw_m))
        self.patch(owner, "C4_PAPER_V20_CONFIG_SHA256", owner.digest(new_config))
        self.patch(owner, "C4_PAPER_V20_MANIFEST_SHA256", owner.digest(new_manifest))
        svc._atomic_write_bytes(self.roots["config"], new_config)
        svc._atomic_write_bytes(self.roots["manifest"], new_manifest)
        return current, current_manifest, new_config, new_manifest

    def test_post_enrollment_paper_v20_allows_only_existing_owner_start(self):
        self._select_paper_after_enrollment()
        frozen_original_pin = {x.name: x.read_bytes() for x in self.pin_path.iterdir()}
        frozen_enrollment = {x.name: x.read_bytes() for x in self.tx.iterdir()}
        before = self.snapshot()
        self.assertFalse(self.loaded)
        self.assertEqual(self.start()["started"], True)
        self.assertEqual(self.native_operations[-1], "status")
        self.assertEqual(before, {
            key: value for key, value in self.snapshot().items()
        })
        self.assertEqual(frozen_original_pin, {
            x.name: x.read_bytes() for x in self.pin_path.iterdir()})
        self.assertEqual(frozen_enrollment, {
            x.name: x.read_bytes() for x in self.tx.iterdir()})

    def test_post_enrollment_paper_v20_status_is_readonly_and_reports_selected(self):
        self._select_paper_after_enrollment()
        self.args.operation = "status"
        before = self.snapshot()
        status = self.invoke()
        self.assertEqual((status["effect"], status["phase"]), ("APPLIED", "COMPLETE"))
        self.assertTrue(status["paperV20Selected"])
        self.assertEqual(self.snapshot(), before)
        self.args.operation = "reconcile"
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            self.invoke()

    def test_post_enrollment_paper_v20_requires_original_result_and_native_pool(self):
        self._select_paper_after_enrollment()
        receipt = self.tx / "result.json"
        retained = receipt.read_bytes()
        receipt.unlink()
        with self.assertRaises(SystemExit):
            self.start()
        receipt.write_bytes(retained)
        native_bytes = self.pool.read_bytes()
        self.pool.write_bytes(b"unreviewed-pool")
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_REFUSED"):
            self.start()
        self.pool.write_bytes(native_bytes)
        self.assertFalse(self.loaded)

    def test_post_enrollment_paper_v20_refuses_config_and_module_drift(self):
        _, _, after_c, after_m = self._select_paper_after_enrollment()
        tampered = json.loads(after_c)
        tampered["gitPublish"]["commandTimeoutMs"] = 10
        svc._atomic_write_bytes(self.roots["config"], owner.encode(tampered))
        with self.assertRaises(SystemExit):
            self.start()
        svc._atomic_write_bytes(self.roots["config"], after_c)
        tampered = json.loads(after_m)
        tampered["configHash"] = "0" * 64
        svc._atomic_write_bytes(self.roots["manifest"], owner.encode(tampered))
        with self.assertRaises(SystemExit):
            self.start()
        svc._atomic_write_bytes(self.roots["manifest"], after_m)
        p = self.roots["base"] / "git-publish.mjs"
        old = p.read_bytes()
        svc._atomic_write_bytes(p, b"foreign publisher code")
        with self.assertRaises(SystemExit):
            self.start()
        svc._atomic_write_bytes(p, old)
        self.roots["config"].chmod(0o644)
        with self.assertRaises(SystemExit):
            self.start()
        self.roots["config"].chmod(0o600)
        self.assertFalse(self.loaded)

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





class C4PublisherFrozenContractTests(unittest.TestCase):
    def test_c4_successor_is_exact_and_preserves_original_profiles(self):
        self.assertEqual(owner.C4_PUBLISHER_BEFORE_MANIFEST,
                         "c440f2ba4c0bdfbba3aff86303a483e3ab42a1093f330ba9e3fd6c6f923783b4")
        self.assertEqual(owner.C4_PUBLISHER_BEFORE_CONFIG, owner.C4_PAPER_V20_CONFIG_SHA256)
        self.assertEqual(owner.C4_PUBLISHER_BEFORE, owner.TARGET_FILES["git-publish.mjs"])
        self.assertEqual(owner.C4_ADAPTER_BEFORE, owner.TARGET_FILES["workspace-access.mjs"])
        self.assertEqual(owner.C4_ADAPTER_AFTER,
                         "290cf5e961db2fa30e37c32da473595518df0ded80fc850a84cf5bdae1a1ec3c")
        self.assertNotEqual(owner.C4_ADAPTER_BEFORE, owner.C4_ADAPTER_AFTER)
        self.assertEqual(owner.C4_PUBLISHER_AFTER,
                         "a8ce5f25f4fc606e294f58de5748a73a36de5178d8e30b27132c3660e161d58e")
        self.assertEqual(set(owner.PROFILES), {
            "chatgpt4", "admin-business", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9"})
        self.assertNotEqual(owner.C4_PUBLISHER_TRANSACTION, owner.TRANSACTION)

    def test_current_protected_payload_matches_inventory_successor(self):
        payload = Path(__file__).with_name("git-publish.mjs").read_bytes()
        self.assertEqual(owner.digest(payload), owner.C4_INVENTORY_AFTER)
        adapter = Path(__file__).with_name("workspace-access.mjs").read_bytes()
        self.assertEqual(owner.digest(adapter), owner.C4_ADAPTER_AFTER)

    def test_existing_cli_selects_c4_successor_without_new_control(self):
        args = svc.build_parser().parse_args([
            "native-pool-pin-enrollment", "--account", "chatgpt4",
            "--operation", "preview", "--expected-manifest-sha256",
            owner.C4_PUBLISHER_BEFORE_MANIFEST])
        self.assertEqual(args.func, svc.cmd_native_pool_pin_enrollment)
        self.assertFalse(any(hasattr(args, key) for key in
                             ("credential", "remote", "branch", "force", "skip_integrity")))

    def test_foreign_account_cannot_recognize_c4_transaction(self):
        for account in ("chatgpt2-personal", "chatgpt2-business", "admin-business",
                        "chatgpt3", "chatgpt3-w570f6f34", "unknown"):
            self.assertFalse(owner.c4_publisher_postimage(svc, account, {}))


if __name__ == "__main__":
    unittest.main()
