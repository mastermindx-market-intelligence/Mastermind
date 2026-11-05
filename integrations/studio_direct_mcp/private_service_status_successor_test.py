"""Hermetic status successor source planner negative contract tests.

No real account home, credentials, native pool selection or modification.
The source validator alone never authorizes an installed effect.
"""
import copy
from pathlib import Path
import json
import unittest
from unittest import mock

import private_service_status_successor as s


class ExactStatusSuccessorPlanTests(unittest.TestCase):
    def setUp(self):
        self.account = "chatgpt1"
        self.old_module = b"old sealed public projected source"
        self.new_module = b"new redacted and validated full-owner source"
        self.config = b'{"grants":"exact","paper":"preserved"}'
        self.manifest = {
            "version": 2,
            "account": self.account,
            "label": "com.mastermind.studio-direct-private." + self.account,
            "configHash": s.digest(self.config),
            "plistHash": "a" * 64,
            "files": {"gateway.mjs": "b" * 64,
                      s.MODULE: s.digest(self.old_module)},
            "backend": "/reviewed/backend.mjs",
            "node": "/reviewed/node",
            "nodeHash": "c" * 64,
            "backendHash": "d" * 64,
        }
        self.manifest_bytes = s.encoded_manifest(self.manifest)
        p1 = mock.patch.dict(s.PREDECESSOR_MANIFEST_SHA256,
                             {self.account: s.digest(self.manifest_bytes)})
        p2 = mock.patch.dict(s.LEGACY_MODULE_SHA256,
                             {self.account: s.digest(self.old_module)})
        p3 = mock.patch.object(s, "TARGET_SOURCE_SHA256",
                               s.digest(self.new_module))
        after = copy.deepcopy(self.manifest)
        after["files"][s.MODULE] = s.digest(self.new_module)
        p4 = mock.patch.dict(s.POST_MANIFEST_RAW_SHA256,
                             {self.account: s.digest(s.encoded_manifest(after))})
        p5 = mock.patch.dict(s.POST_MANIFEST_CANONICAL_SHA256, {
            self.account: s.digest(json.dumps(
                after, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        })
        for p in (p1, p2, p3, p4, p5):
            p.start()
            self.addCleanup(p.stop)

    def qualify(self, **overrides):
        values = {
            "manifest_bytes": self.manifest_bytes,
            "config_bytes": self.config,
            "module_before_bytes": self.old_module,
            "source_module_bytes": self.new_module,
        }
        values.update(overrides)
        return s.qualify_exact_predecessor(self.account, **values)

    def test_sealed_single_module_projection_preserves_other_bytes(self):
        row = self.qualify()
        after = json.loads(row.manifest_after_bytes)
        before = json.loads(self.manifest_bytes)
        self.assertEqual(row.account, self.account)
        self.assertEqual(row.module_after_sha256, s.digest(self.new_module))
        self.assertEqual(row.module_before_sha256, s.digest(self.old_module))
        self.assertNotEqual(row.manifest_before_sha256, row.manifest_after_sha256)
        self.assertEqual(after["files"]["gateway.mjs"],
                         before["files"]["gateway.mjs"])
        self.assertEqual(after["configHash"], before["configHash"])
        self.assertEqual(after["backend"], before["backend"])
        self.assertEqual({k: v for k, v in after.items() if k != "files"},
                         {k: v for k, v in before.items() if k != "files"})
        self.assertEqual(row.public_receipt()["effect"], "NOT_APPLIED")
        self.assertFalse(row.public_receipt()["runtimeReady"])

    def test_new_publisher_and_paper_modules_survive_status_only_successor(self):
        extra = copy.deepcopy(self.manifest)
        extra['files'].update({'workspace-access.mjs': '1' * 64,
                               'git-publish.mjs': '2' * 64,
                               'paper-design.mjs': '3' * 64})
        extra['nativePinProof'] = {'preserve': True}
        before = s.encoded_manifest(extra)
        after = copy.deepcopy(extra)
        after['files'][s.MODULE] = s.digest(self.new_module)
        with mock.patch.dict(s.PREDECESSOR_MANIFEST_SHA256, {self.account: s.digest(before)}), \
             mock.patch.dict(s.POST_MANIFEST_RAW_SHA256, {self.account: s.digest(s.encoded_manifest(after))}), \
             mock.patch.dict(s.POST_MANIFEST_CANONICAL_SHA256, {
                 self.account: s.digest(json.dumps(after, sort_keys=True, separators=(',', ':')).encode())}):
            projected = json.loads(self.qualify(manifest_bytes=before).manifest_after_bytes)
            self.assertEqual(projected['nativePinProof'], extra['nativePinProof'])
            self.assertEqual({k: v for k, v in projected['files'].items() if k != s.MODULE},
                             {k: v for k, v in extra['files'].items() if k != s.MODULE})
            with self.assertRaisesRegex(s.SourceRefused, 'PREDECESSOR_MANIFEST_CHANGED'):
                self.qualify(manifest_bytes=before+b'\n')

    def test_transition_recheck_rejects_any_changed_byte(self):
        row = self.qualify()
        inputs = {
            "manifest_before_bytes": self.manifest_bytes,
            "module_before_bytes": self.old_module,
            "config_bytes": self.config,
            "manifest_after_bytes": row.manifest_after_bytes,
            "module_after_bytes": self.new_module,
        }
        self.assertTrue(s.qualify_unchanged_transition(row, **inputs))
        for field in inputs:
            tampered = dict(inputs)
            tampered[field] += b"\n"
            with self.subTest(field=field):
                with self.assertRaisesRegex(s.SourceRefused,
                                            "STATE_OR_SOURCE_CHANGED"):
                    s.qualify_unchanged_transition(row, **tampered)

    def test_forged_account_and_unknown_cohort_refuse(self):
        for name in ("not-enrolled", "../chatgpt1", "fabric-design",
                     "mastermind-os-publication", "", None, 1):
            with self.subTest(name=name):
                with self.assertRaisesRegex(s.SourceRefused, "ACCOUNT_UNQUALIFIED"):
                    s.qualify_exact_predecessor(
                        name, manifest_bytes=self.manifest_bytes,
                        config_bytes=self.config, module_before_bytes=self.old_module,
                        source_module_bytes=self.new_module)

    def test_stale_manifest_and_module_refuse(self):
        with self.assertRaisesRegex(s.SourceRefused, "PREDECESSOR_MANIFEST_CHANGED"):
            self.qualify(manifest_bytes=self.manifest_bytes + b"\n")
        with self.assertRaisesRegex(s.SourceRefused, "PREDECESSOR_MODULE_CHANGED"):
            self.qualify(module_before_bytes=self.old_module + b"?")

    def test_unreviewed_future_manifest_cannot_be_admitted(self):
        with mock.patch.dict(s.POST_MANIFEST_RAW_SHA256,
                             {self.account: "0" * 64}):
            with self.assertRaisesRegex(s.SourceRefused,
                                        "TARGET_COHORT_NOT_SEALED"):
                self.qualify()
        with mock.patch.dict(s.POST_MANIFEST_CANONICAL_SHA256,
                             {self.account: "0" * 64}):
            with self.assertRaisesRegex(s.SourceRefused,
                                        "TARGET_COHORT_NOT_SEALED"):
                self.qualify()

    def test_target_source_digest_refuses_unreviewed_payload(self):
        with self.assertRaisesRegex(s.SourceRefused, "TARGET_SOURCE_NOT_ACCEPTED"):
            self.qualify(source_module_bytes=self.new_module + b"malicious")

    def test_label_config_and_fleet_module_identity_are_bound(self):
        for key, val in (("label", "com.mastermind.studio-direct-private.other"),
                         ("account", "other"), ("configHash", "f" * 64)):
            m = copy.deepcopy(self.manifest)
            m[key] = val
            raw = s.encoded_manifest(m)
            with mock.patch.dict(s.PREDECESSOR_MANIFEST_SHA256,
                                 {self.account: s.digest(raw)}):
                with self.subTest(key=key):
                    with self.assertRaisesRegex(s.SourceRefused,
                                                "PREDECESSOR_IDENTITY_INVALID"):
                        self.qualify(manifest_bytes=raw)
        m = copy.deepcopy(self.manifest)
        m["files"][s.MODULE] = "f" * 64
        raw = s.encoded_manifest(m)
        with mock.patch.dict(s.PREDECESSOR_MANIFEST_SHA256,
                             {self.account: s.digest(raw)}):
            with self.assertRaisesRegex(s.SourceRefused,
                                        "PREDECESSOR_IDENTITY_INVALID"):
                self.qualify(manifest_bytes=raw)

    def test_unqualified_bytes_and_json_refuse(self):
        for v in (None, "", b"", b"x" * (256 * 1024 + 1)):
            with self.subTest(type=type(v).__name__):
                with self.assertRaises(s.SourceRefused):
                    self.qualify(config_bytes=v)
        raw = b"{ invalid }"
        with mock.patch.dict(s.PREDECESSOR_MANIFEST_SHA256,
                             {self.account: s.digest(raw)}):
            with self.assertRaisesRegex(s.SourceRefused, "MANIFEST_UNQUALIFIED"):
                self.qualify(manifest_bytes=raw)

    def test_source_planner_has_no_runtime_or_credential_hooks(self):
        self.assertEqual(len(s.PREDECESSOR_MANIFEST_SHA256), 8)
        self.assertEqual(set(s.PREDECESSOR_MANIFEST_SHA256),
                         set(s.LEGACY_MODULE_SHA256))
        receipt = self.qualify().public_receipt()
        self.assertNotIn("credential", json.dumps(receipt).lower())
        self.assertNotIn("token", json.dumps(receipt).lower())
        self.assertNotIn("ready", json.dumps(receipt).lower().replace("runtimeready", ""))
        self.assertTrue(self.qualify().no_runtime_effect)


class OwnerTransactionTests(unittest.TestCase):
    """Real temp files/manifest-last writer; mock only native selection + Git commit."""

    def setUp(self):
        import tempfile
        import os
        from types import SimpleNamespace
        from contextlib import nullcontext
        import private_service as svc
        self.svc = svc
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        self.account = "chatgpt1"
        self.new = b"qualified merged full-owner projection"
        self.old = b"original status module"
        self.plist = b"original launchd plist"
        self.node = self.home / "runtime-node"
        self.backend = self.home / "backend.mjs"
        self.node.write_bytes(b"node")
        self.backend.write_bytes(b"backend")
        self.config = b'{"accountLabel":"chatgpt1","grant":"preserved"}'
        self.deps_digest = "d" * 64
        self.release = "e" * 40
        self.pin = "f" * 64
        self.patch(svc, "_user_root", lambda: self.home)
        self.patch(svc, "_c2_lifecycle_mutex", lambda account: nullcontext())
        self.patch(svc, "_lifecycle_inspect", lambda *args, **kwargs: None)
        self.patch(svc, "_dependency_tree_hash", lambda root: self.deps_digest)
        self.patch(svc, "_verify_staged_install",
                   lambda *args, **kwargs: {"sealed": True})
        self.patch(s, "_original_pin", lambda *args, **kwargs: self.pin)
        self.patch(s, "_protected_source", lambda *args, **kwargs:
                   (self.new, "a" * 40))
        self.roots = svc._build_runtime_roots(self.account)
        self.roots["base"].mkdir(parents=True, exist_ok=True)
        self.roots["base"].chmod(0o700)
        self.roots["state"].mkdir(parents=True, exist_ok=True)
        self.roots["plist"].parent.mkdir(parents=True, exist_ok=True)
        self.roots["node_modules"].mkdir(parents=True, exist_ok=True)
        self.write(self.roots["base"] / s.MODULE, self.old)
        self.write(self.roots["base"] / "gateway.mjs", b"original gateway")
        self.write(self.roots["plist"], self.plist)
        self.write(self.roots["config"], self.config)
        self.original_manifest = {
            "version": 2, "account": self.account,
            "label": "com.mastermind.studio-direct-private." + self.account,
            "configHash": s.digest(self.config),
            "plistHash": s.digest(self.plist),
            "node": str(self.node), "backend": str(self.backend),
            "nodeHash": s.digest(self.node.read_bytes()),
            "backendHash": s.digest(self.backend.read_bytes()),
            "dependencyTreeHash": self.deps_digest,
            "files": {
                "gateway.mjs": s.digest(b"original gateway"),
                s.MODULE: s.digest(self.old),
            },
        }
        self.before = s.encoded_manifest(self.original_manifest)
        self.write(self.roots["manifest"], self.before)
        future = dict(self.original_manifest)
        future["files"] = dict(self.original_manifest["files"])
        future["files"][s.MODULE] = s.digest(self.new)
        self.after = s.encoded_manifest(future)
        self.patch(s.PREDECESSOR_MANIFEST_SHA256, self.account, s.digest(self.before))
        self.patch(s.LEGACY_MODULE_SHA256, self.account, s.digest(self.old))
        self.patch_object(s, "TARGET_SOURCE_SHA256", s.digest(self.new))
        self.patch(s.POST_MANIFEST_RAW_SHA256, self.account, s.digest(self.after))
        self.patch(s.POST_MANIFEST_CANONICAL_SHA256, self.account,
                   s.digest(json.dumps(
                       future, sort_keys=True, separators=(",", ":"),
                   ).encode("utf-8")))
        self.args = SimpleNamespace(
            account=self.account, operation="preview",
            release_commit=self.release,
            expected_manifest_sha256=s.digest(self.before),
            expected_plan_sha256=None,
        )

    def patch(self, target, name, value):
        if isinstance(target, dict):
            p = mock.patch.dict(target, {name: value})
        else:
            p = mock.patch.object(target, name, value)
        p.start()
        self.addCleanup(p.stop)

    def patch_object(self, target, name, value):
        self.patch(target, name, value)

    def write(self, path, blob):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        path.chmod(0o600)

    def preview(self):
        return s.run(self.svc, self.args)

    def apply(self, plan):
        from types import SimpleNamespace
        return s.run(self.svc, SimpleNamespace(
            **{**vars(self.args), "operation": "apply",
               "expected_plan_sha256": plan["planSha256"]}))

    def run_op(self, operation):
        from types import SimpleNamespace
        return s.run(self.svc, SimpleNamespace(
            **{**vars(self.args), "operation": operation}))

    def test_preview_has_no_file_effect(self):
        old = self.roots["manifest"].read_bytes()
        preview = self.preview()
        self.assertEqual(preview["phase"], "PREVIEW")
        self.assertEqual(preview["effect"], "NOT_APPLIED")
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())
        self.assertEqual(self.roots["manifest"].read_bytes(), old)

    def test_atomic_module_then_manifest_apply_and_start(self):
        preview = self.preview()
        result = self.apply(preview)
        self.assertEqual(result["effect"], "APPLIED")
        self.assertTrue(result["existingNativePinPreserved"])
        self.assertEqual(self.roots["manifest"].read_bytes(), self.after)
        self.assertEqual((self.roots["base"] / s.MODULE).read_bytes(), self.new)
        self.assertEqual(self.roots["config"].read_bytes(), self.config)
        self.assertEqual((self.roots["base"] / "gateway.mjs").read_bytes(),
                         b"original gateway")
        self.assertTrue(s.require_start(self.svc, self.account, self.roots))
        self.assertEqual(self.run_op("status")["effect"], "APPLIED")
        self.assertEqual(self.run_op("reconcile")["effect"], "APPLIED")
        self.assertEqual(self.roots["manifest"].read_bytes(), self.after)

    def test_loaded_service_refuses_before_creating_transaction(self):
        self.patch(self.svc, "_lifecycle_inspect",
                   lambda *args, **kwargs: {"loaded": True})
        with self.assertRaisesRegex(SystemExit, "SERVICE_LOADED_STOP_FIRST"):
            self.apply(self.preview())
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())

    def test_wrong_plan_refuses_pre_effect(self):
        from types import SimpleNamespace
        with self.assertRaisesRegex(SystemExit, "PLAN_CAS_INVALID"):
            s.run(self.svc, SimpleNamespace(**{
                **vars(self.args), "operation": "apply",
                "expected_plan_sha256": "0" * 64}))
        self.assertEqual(self.roots["manifest"].read_bytes(), self.before)
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())

    def test_partial_module_write_keeps_original_intent_and_requires_reconcile(self):
        plan = self.preview()
        actual = self.svc._atomic_write_bytes
        count = 0
        def interrupted(path, blob, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("simulated partial commit")
            return actual(path, blob, **kwargs)
        with mock.patch.object(self.svc, "_atomic_write_bytes",
                               side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.apply(plan)
        self.assertEqual(self.run_op("status")["phase"], "MODULE_ONLY")
        with self.assertRaisesRegex(SystemExit, "START_NOT_COMMITTED"):
            s.require_start(self.svc, self.account, self.roots)
        self.assertEqual(self.run_op("reconcile")["effect"], "APPLIED")
        self.assertTrue(s.require_start(self.svc, self.account, self.roots))

    def test_wrong_startup_receipt_and_tampering_refuse_closed(self):
        plan = self.preview()
        self.apply(plan)
        receipt = self.roots["state"] / s.TRANSACTION / "result.json"
        self.write(receipt, b'{"effect":"APPLIED","planSha256":"fake"}')
        with self.assertRaisesRegex(SystemExit, "START_NOT_COMMITTED"):
            s.require_start(self.svc, self.account, self.roots)

    def test_status_file_drift_refuses_even_with_committed_receipt(self):
        self.apply(self.preview())
        self.write(self.roots["base"] / s.MODULE,
                   b"unreviewed private module")
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            s.require_start(self.svc, self.account, self.roots)

    def test_future_source_ineligible_and_old_pin_receipt_mismatch(self):
        preview = self.preview()
        self.patch(s, "_original_pin", lambda *args, **kwargs: "0" * 64)
        # The preview is tied to the selected original pin SHA. A changed
        # native pin must refuse *before* the first installation effect.
        with self.assertRaisesRegex(SystemExit, "PLAN_CAS_INVALID"):
            self.apply(preview)
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())

    def test_selected_original_pin_must_still_match_after_install(self):
        self.apply(self.preview())
        self.patch(s, "_original_pin", lambda *args, **kwargs: "0" * 64)
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_CHANGED"):
            s.require_start(self.svc, self.account, self.roots)

    def test_preserved_manifest_fails_if_other_module_changes(self):
        self.apply(self.preview())
        self.write(self.roots["base"] / "gateway.mjs", b"gateway changed")
        with self.assertRaisesRegex(SystemExit, "OTHER_MODULE_CHANGED"):
            s.require_start(self.svc, self.account, self.roots)


    def test_torn_result_is_never_visible_and_reconcile_does_not_replay_modules(self):
        plan = self.preview()
        actual = self.svc._fabric_release_new
        def torn(path, blob):
            if path.name == "result.json":
                self.write(path, blob[:1])
                raise OSError("injected result write failure")
            return actual(path, blob)
        with mock.patch.object(self.svc, "_fabric_release_new", side_effect=torn):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.apply(plan)
        result = self.roots["state"] / s.TRANSACTION / "result.json"
        self.assertFalse(result.exists(), "partial result became an active receipt")
        self.assertEqual(self.run_op("status")["phase"], "COMMITTED")
        with mock.patch.object(self.svc, "_atomic_write_bytes",
                               side_effect=AssertionError("completed module write replayed")):
            self.assertEqual(self.run_op("reconcile")["effect"], "APPLIED")
        self.assertEqual(result.stat().st_nlink, 1)
        self.assertTrue(s.require_start(self.svc, self.account, self.roots))


    def assert_original_bytes(self):
        self.assertEqual((self.roots["base"] / s.MODULE).read_bytes(), self.old)
        self.assertEqual(self.roots["manifest"].read_bytes(), self.before)

    def test_intent_rename_then_interrupt_retains_complete_same_owner_recovery(self):
        target = self.roots["state"] / s.TRANSACTION
        actual = s._rename_new
        def interrupted(svc, source, destination):
            actual(svc, source, destination)
            if destination == target:
                raise KeyboardInterrupt("after successful intent rename")
        with mock.patch.object(s, "_rename_new", side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_PREPARATION"):
                self.apply(self.preview())
        self.assertEqual({p.name for p in target.iterdir()}, s.FILE_NAMES - {"result.json"})
        self.assert_original_bytes()
        self.assertEqual(self.run_op("status")["phase"], "OLD")
        self.assertFalse(self.run_op("status")["durabilityConfirmed"])
        with self.assertRaisesRegex(SystemExit, "START_NOT_COMMITTED"):
            s.require_start(self.svc, self.account, self.roots)
        self.assertTrue(self.run_op("reconcile")["durabilityConfirmed"])

    def test_result_rename_then_interrupt_is_complete_and_never_replayed(self):
        actual = s._rename_new
        def interrupted(svc, source, destination):
            actual(svc, source, destination)
            if destination.name == "result.json":
                raise KeyboardInterrupt("after successful result rename")
        with mock.patch.object(s, "_rename_new", side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.apply(self.preview())
        target = self.roots["state"] / s.TRANSACTION
        result = target / "result.json"
        before = result.read_bytes()
        self.assertEqual(json.loads(before)["effect"], "APPLIED")
        self.assertEqual({p.name for p in target.iterdir()}, s.FILE_NAMES)
        self.assertEqual(result.stat().st_nlink, 1)
        with mock.patch.object(self.svc, "_atomic_write_bytes",
                               side_effect=AssertionError("completed write replayed")):
            self.assertTrue(self.run_op("reconcile")["durabilityConfirmed"])
        self.assertEqual(result.read_bytes(), before)

    def test_intent_parent_sync_failure_keeps_complete_old_phase(self):
        target = self.roots["state"] / s.TRANSACTION
        actual = s.os.fsync
        state_identity = s._identity(target.parent)
        def interrupted(fd):
            info = s.os.fstat(fd)
            if (info.st_dev, info.st_ino) == state_identity and target.exists():
                raise OSError("parent sync after intent publication")
            return actual(fd)
        with mock.patch.object(s.os, "fsync", side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_PREPARATION"):
                self.apply(self.preview())
        self.assert_original_bytes()
        self.assertEqual(self.run_op("status")["phase"], "OLD")
        self.assertTrue(self.run_op("reconcile")["durabilityConfirmed"])

    def test_result_parent_sync_failure_recovers_without_module_replay(self):
        target = self.roots["state"] / s.TRANSACTION
        actual = s.os.fsync
        def interrupted(fd):
            info = s.os.fstat(fd)
            if ((target / "result.json").exists()
                    and (info.st_dev, info.st_ino) == s._identity(target)):
                raise OSError("result directory sync failure")
            return actual(fd)
        with mock.patch.object(s.os, "fsync", side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.apply(self.preview())
        self.assertEqual(json.loads((target / "result.json").read_bytes())["effect"], "APPLIED")
        with mock.patch.object(self.svc, "_atomic_write_bytes",
                               side_effect=AssertionError("completed write replayed")):
            self.assertTrue(self.run_op("reconcile")["durabilityConfirmed"])

    def test_strict_directory_open_failure_cannot_publish_an_intent(self):
        actual = s.os.open
        def refused(path, flags, *args, **kwargs):
            if (str(path).split("/")[-1].startswith(".fleet-status-intent.")
                    and flags & s.os.O_DIRECTORY):
                raise OSError("staging directory open refused")
            return actual(path, flags, *args, **kwargs)
        with mock.patch.object(s.os, "open", side_effect=refused):
            with self.assertRaises(OSError):
                self.apply(self.preview())
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())
        self.assert_original_bytes()

    def test_manifest_parent_sync_interruption_requires_strict_recovery_without_replay(self):
        actual = self.svc._fsync_dir
        parent = self.roots["manifest"].parent
        def interrupted(path):
            if Path(path) == parent and self.roots["manifest"].read_bytes() == self.after:
                raise OSError("manifest rename succeeded but base sync failed")
            return actual(path)
        with mock.patch.object(self.svc, "_fsync_dir", side_effect=interrupted):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.apply(self.preview())
        self.assertEqual(self.run_op("status")["phase"], "COMMITTED")
        self.assertFalse((self.roots["state"] / s.TRANSACTION / "result.json").exists())
        with mock.patch.object(s, "_sync_directory", wraps=s._sync_directory) as synced:
            with mock.patch.object(self.svc, "_atomic_write_bytes",
                                   side_effect=AssertionError("completed write replayed")):
                self.assertTrue(self.run_op("reconcile")["durabilityConfirmed"])
        self.assertIn(parent, [call.args[1] for call in synced.call_args_list])

    def test_persistent_base_sync_failure_never_claims_durable_or_allows_start(self):
        self.apply(self.preview())
        target = self.roots["state"] / s.TRANSACTION
        receipt = (target / "result.json").read_bytes()
        actual = s._sync_directory
        def refused(svc, path):
            if path == self.roots["base"]:
                raise OSError("installed base sync unavailable")
            return actual(svc, path)
        with mock.patch.object(s, "_sync_directory", side_effect=refused):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_DURABILITY"):
                self.run_op("reconcile")
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_DURABILITY"):
                s.require_start(self.svc, self.account, self.roots)
        self.assertEqual((target / "result.json").read_bytes(), receipt)
        self.assertTrue(self.run_op("reconcile")["durabilityConfirmed"])

    def test_status_remains_read_only_and_does_not_claim_new_durability_proof(self):
        self.apply(self.preview())
        with mock.patch.object(s, "_sync_directory",
                               side_effect=AssertionError("status attempted a durability effect")):
            observed = self.run_op("status")
        self.assertEqual(observed["effect"], "APPLIED")
        self.assertFalse(observed["durabilityConfirmed"])

    def test_real_native_exclusive_publication_retains_inode_and_single_link(self):
        for is_directory in (False, True):
            with self.subTest(directory=is_directory):
                source = self.roots["state"] / ("source-dir" if is_directory else "source-file")
                destination = self.roots["state"] / ("final-dir" if is_directory else "final-file")
                if is_directory:
                    source.mkdir(mode=0o700)
                    self.write(source / "retained", b"complete")
                else:
                    self.write(source, b"complete")
                source.parent.chmod(0o700)
                identity = s._identity(source)
                s._rename_new(self.svc, source, destination)
                self.assertFalse(source.exists())
                self.assertEqual(s._identity(destination), identity)
                file = destination / "retained" if is_directory else destination
                self.assertEqual(file.read_bytes(), b"complete")
                self.assertEqual(file.stat().st_nlink, 1)

    def test_result_collision_preserves_foreign_receipt_and_committed_postimages(self):
        actual = s._rename_new
        foreign = s._encode({"schema": s.SCHEMA, "planSha256": "0" * 64, "effect": "APPLIED"})
        def collision(svc, source, destination):
            if destination.name == "result.json":
                self.write(destination, foreign)
            return actual(svc, source, destination)
        with mock.patch.object(s, "_rename_new", side_effect=collision):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.apply(self.preview())
        result = self.roots["state"] / s.TRANSACTION / "result.json"
        self.assertEqual(result.read_bytes(), foreign)
        self.assertEqual((self.roots["base"] / s.MODULE).read_bytes(), self.new)
        self.assertEqual(self.roots["manifest"].read_bytes(), self.after)
        with self.assertRaisesRegex(SystemExit, "RESULT_OR_STATE_CHANGED"):
            self.run_op("reconcile")
        self.assertEqual(result.read_bytes(), foreign)

    def test_unsupported_publication_platform_refuses_without_fallback(self):
        with mock.patch.object(s.sys, "platform", "unsupported"):
            with mock.patch.object(s.os, "rename", side_effect=AssertionError("rename fallback")):
                with mock.patch.object(s.os, "replace", side_effect=AssertionError("replace fallback")):
                    with self.assertRaisesRegex(SystemExit, "EXCLUSIVE_PUBLICATION_UNAVAILABLE"):
                        self.apply(self.preview())
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())
        self.assert_original_bytes()

    def test_missing_exclusive_symbol_refuses_without_fallback(self):
        with mock.patch.object(s.ctypes, "CDLL", return_value=object()):
            with mock.patch.object(s.os, "rename", side_effect=AssertionError("rename fallback")):
                with self.assertRaisesRegex(SystemExit, "EXCLUSIVE_PUBLICATION_UNAVAILABLE"):
                    self.apply(self.preview())
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())
        self.assert_original_bytes()

    def test_unsupported_filesystem_preserves_error_and_refuses_without_fallback(self):
        import errno
        from types import SimpleNamespace
        def unsupported(*args):
            s.ctypes.set_errno(errno.ENOTSUP)
            return -1
        operation = mock.Mock(side_effect=unsupported)
        name = "renameatx_np" if s.sys.platform == "darwin" else "renameat2"
        library = SimpleNamespace(**{name: operation})
        with mock.patch.object(s.ctypes, "CDLL", return_value=library):
            with mock.patch.object(s.os, "rename", side_effect=AssertionError("rename fallback")):
                with self.assertRaises(OSError) as raised:
                    self.apply(self.preview())
        self.assertEqual(raised.exception.errno, errno.ENOTSUP)
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists())
        self.assert_original_bytes()


def _torn_preparation_case(artifact):
    def test(self):
        plan = self.preview()
        actual = self.svc._fabric_release_new
        def torn(path, blob):
            if path.name == artifact:
                self.write(path, blob[:1])
                raise OSError("injected retained artifact write failure")
            return actual(path, blob)
        with mock.patch.object(self.svc, "_fabric_release_new", side_effect=torn):
            with self.assertRaises((OSError, SystemExit)):
                self.apply(plan)
        self.assertFalse((self.roots["state"] / s.TRANSACTION).exists(),
                         "incomplete preparation became an active transaction")
        self.assertEqual((self.roots["base"] / s.MODULE).read_bytes(), self.old)
        self.assertEqual(self.roots["manifest"].read_bytes(), self.before)
        self.assertFalse(s.require_start(self.svc, self.account, self.roots))
    return test


for _artifact in ("plan.json", "manifest.before", "module.before",
                  "manifest.after", "module.after", "intent.json"):
    setattr(OwnerTransactionTests, "test_torn_preparation_" + _artifact.replace(".", "_"),
            _torn_preparation_case(_artifact))



def _foreign_intent_case(kind):
    def test(self):
        actual = s._rename_new
        captured = {}
        def collision(svc, source, destination):
            if destination.name == s.TRANSACTION:
                if kind == "directory":
                    destination.mkdir(mode=0o700)
                elif kind == "file":
                    self.write(destination, b"foreign retained evidence")
                else:
                    destination.symlink_to(self.home / "foreign-missing")
                captured["identity"] = s._identity(destination)
            return actual(svc, source, destination)
        with mock.patch.object(s, "_rename_new", side_effect=collision):
            with mock.patch.object(s.os, "rename", side_effect=AssertionError("rename fallback")):
                with mock.patch.object(s.os, "replace", side_effect=AssertionError("replace fallback")):
                    with self.assertRaises((OSError, SystemExit)):
                        self.apply(self.preview())
        target = self.roots["state"] / s.TRANSACTION
        self.assertEqual(s._identity(target), captured["identity"])
        if kind == "file":
            self.assertEqual(target.read_bytes(), b"foreign retained evidence")
        elif kind == "directory":
            self.assertEqual(list(target.iterdir()), [])
        else:
            self.assertTrue(target.is_symlink())
        self.assert_original_bytes()
    return test


for _kind in ("directory", "file", "symlink"):
    setattr(OwnerTransactionTests, "test_foreign_intent_at_atomic_boundary_" + _kind,
            _foreign_intent_case(_kind))


class SelectedC4LockTests(unittest.TestCase):
    """No nested native selector when qualifying retained C4 enrollment."""

    def test_existing_pin_and_c4_enrollment_are_checked_sequentially(self):
        import os
        import tempfile
        from contextlib import contextmanager
        from types import SimpleNamespace
        import private_service_pin_enrollment as accepted_enrollment
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ep = root / "state" / "native-pool-pin-enrollment"
            ep.mkdir(parents=True)
            pin_root = root / "state" / "native-pool-pin"
            pin_root.mkdir()
            original = {
                "schema": "original_pin_v1", "account": "chatgpt4",
                "uid": os.getuid(), "manifest_before": "a" * 64,
                "successor_bundle": "/exact/immutable/plan",
                "successor_digest": "b" * 64,
                "pool_target": str(root / "pool"),
                "pool_bridge": "c" * 64,
            }
            encoded = lambda x: json.dumps(x).encode()
            result = {
                "schema": "original_pin_v1", "planSha256": "d" * 64,
                "effect": "APPLIED",
            }
            nested = {"active": False, "checks": []}
            enrolled_plan = {"account": "chatgpt4", "epoch": 23}
            enrolled_result = {"schema": "c4_enrollment_v1", "effect": "APPLIED"}

            @contextmanager
            def selected_pin(args):
                self.assertFalse(nested["active"])
                nested["active"] = True
                nested["checks"].append("pin")
                try:
                    yield {"phase": "SELECTED"}
                finally:
                    nested["active"] = False

            @contextmanager
            def selected_enrollment(svc, roots, operation, profile):
                self.assertEqual(profile, accepted_enrollment.frozen_profile("chatgpt4"))
                self.assertFalse(nested["active"], "C4 reentered the live pin selector")
                nested["checks"].append("enrollment")
                yield fake_pin, {}, {}

            fake_pin = SimpleNamespace(
                SCHEMA="original_pin_v1",
                directory=lambda *a: None,
                decode=lambda b: json.loads(b),
                plan_sha=lambda *a: "d" * 64,
                read_transaction=lambda *a: (original, {}),
            )
            fake_enrollment = SimpleNamespace(
                TRANSACTION="native-pool-pin-enrollment",
                TARGET_FILES={},
                frozen_profile=accepted_enrollment.frozen_profile,
                original_pin=mock.create_autospec(
                    accepted_enrollment.original_pin, side_effect=selected_enrollment),
                encode=encoded, digest=s.digest,
                retained=mock.create_autospec(
                    accepted_enrollment.retained, return_value=(enrolled_plan, {})),
                result_record=lambda *a: enrolled_result,
            )
            def read(path):
                if path == pin_root / "plan.json":
                    return encoded(original)
                if path == pin_root / "result.json":
                    return encoded(result)
                if path == ep / "plan.json":
                    return encoded(enrolled_plan)
                if path == ep / "result.json":
                    return encoded(enrolled_result)
                raise AssertionError("unexpected read")
            fake_svc = SimpleNamespace(
                _pin_owner_module=lambda: fake_pin,
                _pin_enrollment_owner_module=lambda: fake_enrollment,
                _pin_native_context=selected_pin,
                _fabric_release_bytes=read,
                _stable_regular_file_hash=lambda *a, **kw: "c" * 64,
            )
            roots = {"state": root / "state", "base": root / "base"}
            self.assertEqual(s._original_pin(fake_svc, "chatgpt4", roots),
                             "d" * 64)
            self.assertEqual(nested["checks"], ["pin", "enrollment"])
            self.assertFalse(nested["active"])



if __name__ == "__main__":
    unittest.main()
