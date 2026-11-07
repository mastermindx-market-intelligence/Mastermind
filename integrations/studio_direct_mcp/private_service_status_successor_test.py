"""Hermetic status successor source planner negative contract tests.

No real account home, credentials, native pool selection or modification.
The source validator alone never authorizes an installed effect.
"""
import contextlib
import copy
from pathlib import Path
import json
import os
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc
import private_service_pin_enrollment as owner
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
                PROFILES=accepted_enrollment.PROFILES,
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



class EnrolledRetainedReceiptTests(unittest.TestCase):
    """Retained enrollment receipts stay binding on the status-successor path.

    Every profile builds one real native-pool-pin transaction and one real
    completed enrollment transaction through the existing owners. Only the
    native epoch proof, launchctl and the exact production cohort digests are
    replaced by inert fixture bytes; the enrollment owner's own frozen
    profile, original-pin proof, retained plan/intent/payload proof and
    completion receipt stay real, so a missing or corrupted receipt is
    rejected by the real verifier and not by a success stub.
    """

    ENROLLED = ("chatgpt4", "admin-business",
                "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9")
    NEWLY_COVERED = ("admin-business",
                     "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9")
    # The enrollment owner publishes ports only for its own four seats.
    PORTS = {"chatgpt1": 45018}
    SOURCE = b"qualified merged full-owner fleet-status projection"

    def manifest_shape(self, data, account, label):
        """Accept the inert fixture cohort only; every other rule stays real."""
        if not isinstance(data, dict) or set(data) != frozenset(svc.MANIFEST_KEYS_V2):
            return False
        if data.get("version") != svc.MANIFEST_VERSION:
            return False
        if data.get("account") != account or data.get("label") != label:
            return False
        files = data.get("files")
        if not isinstance(files, dict) or not files:
            return False
        digests = list(files.values()) + [data.get(key) for key in (
            "configHash", "plistHash", "nodeHash", "backendHash")]
        dependency = data.get("dependencyTreeHash")
        if dependency is not None:
            digests.append(dependency)
        return all(svc._sha256_hex(digest) for digest in digests)

    def build(self, account, enroll=True):
        """One real native-pool-pin and (optionally) enrollment transaction."""
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        home = Path(stack.enter_context(
            tempfile.TemporaryDirectory())).resolve() / "home"
        home.mkdir(mode=0o700)
        label = "com.mastermind.studio-direct-private." + account

        def patch(obj, attr, value):
            stack.enter_context(mock.patch.object(obj, attr, value))

        patch(svc, "_user_root", lambda: home)
        roots = svc._build_runtime_roots(account)
        calls = []
        patch(svc, "_pin_enrollment_owner_module", lambda: owner)
        patch(svc, "_fleet_status_successor_owner_module", lambda: s)
        real_valid = svc._valid_manifest
        patch(svc, "_valid_manifest", lambda d, a, l: (
            real_valid(d, a, l) or self.manifest_shape(d, a, l)))
        patch(svc, "_c2_lifecycle_mutex", lambda account: contextlib.nullcontext())

        def launchctl(argv, **kwargs):
            calls.append(argv)
            if argv[:2] == ["launchctl", "print"]:
                return svc.CmdResult(113, "", (
                    'Bad request.\nCould not find service "%s" in domain for '
                    'user gui: %d\n' % (label, os.getuid())))
            if argv[:2] == ["launchctl", "bootstrap"]:
                return svc.CmdResult(0, "", "")
            raise AssertionError("unexpected external effect")

        patch(svc, "_run", launchctl)
        reads = []
        real_read = svc._fabric_release_bytes

        def read(path, **kwargs):
            reads.append(str(path))
            return real_read(path, **kwargs)

        patch(svc, "_fabric_release_bytes", read)

        source = home / "initial-source"
        source.mkdir()
        for name in set(svc.STAGE_FILES) | set(svc.C2_PAPER_FILES_SHA256):
            (source / name).write_bytes(("// original fixture " + name).encode())
        node = home / "node"
        node.write_bytes(b"inert node")
        node.chmod(0o700)
        backend = home / "backend.mjs"
        backend.write_bytes(b"inert backend")
        port = (owner.PROFILES[account]["port"] if account in owner.PROFILES
                else self.PORTS[account])
        svc._write_install(source, node, backend, account, label, "127.0.0.1",
                           port, roots, result_key="staged", fabric_only=True)
        deps = roots["node_modules"] / "fixture"
        deps.mkdir(parents=True)
        (deps / "index.js").write_bytes(b"inert dependency")
        svc.cmd_seal_runtime(SimpleNamespace(account=account))
        original_modules = {}
        for name in svc.C2_PAPER_FILES_SHA256:
            data = (source / name).read_bytes()
            svc._atomic_write_bytes(roots["base"] / name, data)
            original_modules[name] = owner.digest(data)
        adapter = roots["base"] / "workspace-access.mjs"
        if adapter.exists():
            adapter.unlink()
        pool = home / "pool"
        pool.write_bytes(b"old-native-pool")
        future_pool = b"selected-native-pool"
        config = json.loads(roots["config"].read_bytes())
        config.pop("fabricOnly", None)
        config["gitPublish"] = svc._typed_git_config(home)
        config["fleetStatus"] = {
            "enabled": True, "launcherPath": str(home / "studio-direct"),
            "launcherSha256": "a" * 64, "timeoutMs": 15000,
            "fabricLauncherPath": str(pool), "fabricLauncherSha256": "9" * 64,
            "fabricTimeoutMs": 8000,
        }
        config["paperDesign"] = {"preserved": True, "fixture": "PRIVATE-CANARY"}
        roots["config"].write_bytes(owner.encode(config))
        manifest = json.loads(roots["manifest"].read_bytes())
        manifest["files"] = original_modules
        manifest["configHash"] = owner.digest(owner.encode(config))
        roots["manifest"].write_bytes(owner.encode(manifest))
        patch(svc, "C2_PAPER_FILES_SHA256", original_modules)
        native_store = home / "native-code-releases"
        native_store.mkdir(mode=0o700)
        binding = {
            "successor_digest": getattr(self, "native_successor_digest", "1" * 64),
            "target_generation": getattr(self, "native_target_generation", "2" * 64),
            "expected_selection": {"generation": "3" * 64, "sequence": 23},
            "pool_target": str(pool), "pool_previous": owner.digest(pool.read_bytes()),
            "pool_bridge": owner.digest(future_pool), "phase": "PREVIOUS",
            "store": str(native_store),
            "selection": {"generation": "3" * 64, "sequence": 23},
        }
        after_config = copy.deepcopy(config)
        after_config["fleetStatus"]["fabricLauncherSha256"] = binding["pool_bridge"]
        after_manifest = copy.deepcopy(manifest)
        after_manifest["configHash"] = owner.digest(owner.encode(after_config))
        nested = {"active": False}

        @contextlib.contextmanager
        def native(args):
            # The original selector lock must never be re-entered.
            self.assertFalse(nested["active"], "native selector contexts nested")
            nested["active"] = True
            try:
                yield binding
            finally:
                nested["active"] = False

        patch(svc, "_pin_native_context", native)
        pin_args = SimpleNamespace(
            account=account,
            expected_manifest_sha256=owner.digest(owner.encode(manifest)),
            successor_bundle=str(home / "successor"),
            successor_plan_sha256=binding["successor_digest"],
            operation="preview", expected_plan_sha256=None)
        preview = svc._pin_owner_module().run(svc, pin_args)
        pin_args.expected_plan_sha256 = preview["planSha256"]
        pin_args.operation = "apply"
        svc._pin_owner_module().run(svc, pin_args)
        pool.write_bytes(future_pool)
        binding["phase"] = "SELECTED"
        binding["selection"] = {"schema": "native-code-selection.v1",
                                "generation": binding["target_generation"],
                                "previous": binding["expected_selection"]["generation"],
                                "sequence": 24}
        original_receipt = {p.name: p.read_bytes()
                            for p in (roots["state"] / "native-pool-pin").iterdir()}
        fixture = {
            "roots": roots, "calls": calls,
            "tx": roots["state"] / owner.TRANSACTION,
            "successor_tx": roots["state"] / s.TRANSACTION,
        }
        if enroll:
            profile = dict(owner.PROFILES[account])
            profile["before_manifest"] = owner.digest(roots["manifest"].read_bytes())
            profile["before_config"] = owner.digest(roots["config"].read_bytes())
            profile["original_plan"] = owner.digest(original_receipt["plan.json"])
            stack.enter_context(mock.patch.dict(owner.PROFILES, {account: profile}))
            if account == owner.ACCOUNT:
                for key in ("BEFORE_MANIFEST", "BEFORE_CONFIG", "ORIGINAL_PLAN"):
                    patch(owner, key, profile[key.lower()])
            payload = home / "payload"
            payload.mkdir(mode=0o700)
            targets = {}
            for name in owner.TARGET_FILES:
                data = ("// qualified target fixture " + name).encode()
                (payload / name).write_bytes(data)
                targets[name] = owner.digest(data)
            patch(owner, "TARGET_FILES", targets)
            args = SimpleNamespace(
                account=account, operation="preview", source=str(payload),
                expected_manifest_sha256=profile["before_manifest"],
                expected_plan_sha256=None)
            result = owner.run(svc, args)
            args.expected_plan_sha256 = result["planSha256"]
            args.operation = "apply"
            owner.run(svc, args)
            fixture["plan"] = json.loads((fixture["tx"] / "plan.json").read_bytes())
            fixture["receipt"] = json.loads((fixture["tx"] / "result.json").read_bytes())
        # Bind the successor's own exact cohort projection to this fixture.
        manifest_bytes = roots["manifest"].read_bytes()
        module_bytes = (roots["base"] / s.MODULE).read_bytes()
        projected = copy.deepcopy(json.loads(manifest_bytes))
        projected["files"][s.MODULE] = s.digest(self.SOURCE)
        after_bytes = s.encoded_manifest(projected)
        canonical = s.digest(json.dumps(
            projected, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        for constants, value in (
                (s.PREDECESSOR_MANIFEST_SHA256, {account: s.digest(manifest_bytes)}),
                (s.LEGACY_MODULE_SHA256, {account: s.digest(module_bytes)}),
                (s.POST_MANIFEST_RAW_SHA256, {account: s.digest(after_bytes)}),
                (s.POST_MANIFEST_CANONICAL_SHA256, {account: canonical})):
            stack.enter_context(mock.patch.dict(constants, value))
        patch(s, "TARGET_SOURCE_SHA256", s.digest(self.SOURCE))
        patch(s, "_protected_source", lambda *a, **k: (self.SOURCE, "a" * 40))
        fixture["args"] = SimpleNamespace(
            account=account, operation="preview", release_commit="e" * 40,
            expected_manifest_sha256=s.digest(manifest_bytes),
            expected_plan_sha256=None)
        fixture["module_before"] = module_bytes
        fixture["manifest_before"] = manifest_bytes
        seen = len(reads)
        fixture["pin_sha"] = s._original_pin(svc, account, roots)
        fixture["enrollment_reads"] = reads[seen:]
        # Capture the valid CAS while every retained enrollment artifact exists.
        fixture["successor_plan_sha"] = s.run(svc, fixture["args"])["planSha256"]
        return fixture

    def corrupt(self, fixture, kind, action):
        """Remove or corrupt exactly one retained enrollment artifact."""
        names = {"plan": "plan.json", "intent": "intent.json",
                 "payload": "manifest.after", "result": "result.json"}
        target = fixture["tx"] / names[kind]
        if action == "remove":
            target.unlink()
            return
        data = json.loads(target.read_bytes())
        if kind == "plan":
            data["uid"] += 1
        elif kind == "intent":
            data["planSha256"] = "0" * 64
        elif kind == "payload":
            data["files"][s.MODULE] = "0" * 64
        else:
            data["effect"] = "NOT_APPLIED"
        target.write_bytes(json.dumps(data, indent=2, sort_keys=True).encode("utf-8"))

    def no_effect(self, fixture):
        self.assertFalse(fixture["successor_tx"].exists())
        self.assertEqual((fixture["roots"]["base"] / s.MODULE).read_bytes(),
                         fixture["module_before"])
        self.assertEqual(fixture["roots"]["manifest"].read_bytes(),
                         fixture["manifest_before"])

    def refuses(self, fixture):
        """Preview and apply both refuse before publication or installed writes."""
        with self.subTest(operation="preview"):
            with self.assertRaises(SystemExit):
                s.run(svc, fixture["args"])
            self.no_effect(fixture)
        apply_args = SimpleNamespace(
            **{**vars(fixture["args"]), "operation": "apply",
               "expected_plan_sha256": fixture["successor_plan_sha"]})
        with self.subTest(operation="apply"):
            with self.assertRaises(SystemExit):
                s.run(svc, apply_args)
            self.no_effect(fixture)

    def test_valid_retained_receipt_is_authenticated_for_every_enrolled_profile(self):
        for account in self.ENROLLED:
            with self.subTest(account=account):
                fixture = self.build(account)
                self.assertEqual(sorted(p.name for p in fixture["tx"].iterdir()),
                                 sorted(owner.FILES))
                # The real enrollment owner produced this completion receipt.
                self.assertEqual(fixture["receipt"],
                                 owner.result_record(fixture["plan"]))
                # The successor authenticates the same retained proof, and it
                # really consults this profile's retained enrollment receipt.
                self.assertEqual(s._original_pin(svc, account, fixture["roots"]),
                                 fixture["pin_sha"])
                self.assertTrue(any(owner.TRANSACTION in path
                                    for path in fixture["enrollment_reads"]))
                record = s.run(svc, fixture["args"])
                self.assertEqual((record["effect"], record["phase"]),
                                 ("NOT_APPLIED", "PREVIEW"))
                self.no_effect(fixture)

    def test_missing_or_corrupt_retained_receipt_refuses_preview_and_apply(self):
        for account in self.NEWLY_COVERED:
            for kind in ("plan", "intent", "payload", "result"):
                for action in ("remove", "corrupt"):
                    with self.subTest(account=account, kind=kind, action=action):
                        fixture = self.build(account)
                        self.corrupt(fixture, kind, action)
                        self.refuses(fixture)

    def test_absent_enrollment_directory_refuses_before_publication(self):
        for account in self.NEWLY_COVERED:
            with self.subTest(account=account):
                fixture = self.build(account)
                shutil.rmtree(fixture["tx"])
                self.refuses(fixture)

    def test_completed_successor_startup_accepts_intact_receipt(self):
        for account in self.ENROLLED:
            with self.subTest(account=account):
                fixture = self.build(account)
                apply_args = SimpleNamespace(
                    **{**vars(fixture["args"]), "operation": "apply",
                       "expected_plan_sha256": fixture["successor_plan_sha"]})
                self.assertEqual(s.run(svc, apply_args)["effect"], "APPLIED")
                self.assertEqual(svc.cmd_start(SimpleNamespace(account=account)), 0)
                self.assertEqual(sum(call[:2] == ["launchctl", "bootstrap"]
                                     for call in fixture["calls"]), 1)

    def test_completed_successor_startup_refuses_before_service_action(self):
        for account in self.NEWLY_COVERED:
            with self.subTest(account=account):
                fixture = self.build(account)
                apply_args = SimpleNamespace(
                    **{**vars(fixture["args"]), "operation": "apply",
                       "expected_plan_sha256": fixture["successor_plan_sha"]})
                s.run(svc, apply_args)
                self.assertTrue((fixture["successor_tx"] / "result.json").exists())
                (fixture["tx"] / "result.json").unlink()
                with self.assertRaises(SystemExit):
                    svc.cmd_start(SimpleNamespace(account=account))
                self.assertFalse(any(call[:2] == ["launchctl", "bootstrap"]
                                     for call in fixture["calls"]))

    def test_non_enrolled_predecessor_profiles_stay_unaffected(self):
        fixture = self.build("chatgpt1", enroll=False)
        self.assertFalse(fixture["tx"].exists())
        self.assertEqual(s._original_pin(svc, "chatgpt1", fixture["roots"]),
                         fixture["pin_sha"])
        record = s.run(svc, fixture["args"])
        self.assertEqual((record["effect"], record["phase"]),
                         ("NOT_APPLIED", "PREVIEW"))
        self.no_effect(fixture)

    def test_c4_paper_v20_state_still_authenticates_the_retained_receipt(self):
        """C4's newer Paper-only selection stays compatible with this path.

        C4's Paper-v20 selection replaces the installed config and manifest
        after enrollment. The retained enrollment proof must survive that,
        because it authenticates the retained transaction and the immutable
        enrollment modules, not the installed config/manifest postimage.
        """
        fixture = self.build("chatgpt4")
        raw_config = (fixture["tx"] / "config.after").read_bytes()
        raw_manifest = (fixture["tx"] / "manifest.after").read_bytes()
        after = json.loads(raw_config)
        after["paperDesign"] = {"enabled": True, "bridgeSha256": "a" * 64}
        future = json.loads(raw_manifest)
        future["configHash"] = owner.digest(owner.encode(after))
        svc._atomic_write_bytes(fixture["roots"]["config"], owner.encode(after))
        svc._atomic_write_bytes(fixture["roots"]["manifest"], owner.encode(future))
        self.assertNotEqual(fixture["roots"]["config"].read_bytes(), raw_config)
        self.assertNotEqual(fixture["roots"]["manifest"].read_bytes(), raw_manifest)
        self.assertEqual(s._original_pin(svc, "chatgpt4", fixture["roots"]),
                         fixture["pin_sha"])




class C4PublisherSuccessorTests(unittest.TestCase):
    """Real prior transactions and exclusive filesystem publication, inert runtime."""
    build = EnrolledRetainedReceiptTests.build
    manifest_shape = EnrolledRetainedReceiptTests.manifest_shape
    PORTS = EnrolledRetainedReceiptTests.PORTS
    SOURCE = EnrolledRetainedReceiptTests.SOURCE

    def setUp(self):
        self.fixture = self.build("chatgpt4")
        self.roots = self.fixture["roots"]
        self.account = "chatgpt4"
        self.patch = lambda obj, key, value: self._patch(obj, key, value)
        status_args = SimpleNamespace(**{
            **vars(self.fixture["args"]), "operation": "apply",
            "expected_plan_sha256": self.fixture["successor_plan_sha"]})
        self.assertEqual(s.run(svc, status_args)["effect"], "APPLIED")
        self.status_path = self.fixture["successor_tx"]
        self.status_plan = json.loads((self.status_path / "plan.json").read_bytes())
        self.status_raw = {n: (self.status_path / n).read_bytes() for n in (
            "manifest.before", "manifest.after", "module.before", "module.after")}
        before = self.roots["manifest"].read_bytes()
        config = self.roots["config"].read_bytes()
        self.before_publisher = (self.roots["base"] / "git-publish.mjs").read_bytes()
        self.after_publisher = b"// qualified inert C4 recovery publisher"
        self.before_adapter = (self.roots["base"] / "workspace-access.mjs").read_bytes()
        self.after_adapter = b"// qualified inert C4 recovery adapter"
        # Exercise the real Paper-origin verification path using an inert exact
        # selected cohort; no production credential/configuration is copied.
        for mapping, value in (
                (s.PREDECESSOR_MANIFEST_SHA256, "f" * 64),
                (s.PAPER_V20_PREDECESSOR_MANIFEST_SHA256, s.digest(self.status_raw["manifest.before"])),
                (s.PAPER_V20_PREDECESSOR_CONFIG_SHA256, s.digest(config)),
                (s.PAPER_V20_POST_MANIFEST_RAW_SHA256, s.digest(before)),
                (s.PAPER_V20_POST_MANIFEST_CANONICAL_SHA256,
                 s.digest(json.dumps(json.loads(before), sort_keys=True,
                                     separators=(",", ":")).encode()))):
            patcher = mock.patch.dict(mapping, {self.account: value})
            patcher.start()
            self.addCleanup(patcher.stop)
        self.paper_calls = []
        def paper_selection(*args, **kwargs):
            self.paper_calls.append((args, kwargs))
            return {"manifestBytes": self.status_raw["manifest.before"],
                    "configBytes": config}
        self.patch(svc, "_frozen_paper_fleet_module",
                   lambda: SimpleNamespace(plan_selection=paper_selection))
        for key, value in (
                ("C4_PUBLISHER_BEFORE_MANIFEST", s.digest(before)),
                ("C4_PUBLISHER_BEFORE_CONFIG", s.digest(config)),
                ("C4_PUBLISHER_BEFORE", s.digest(self.before_publisher)),
                ("C4_PUBLISHER_AFTER", s.digest(self.after_publisher)),
                ("C4_ADAPTER_BEFORE", s.digest(self.before_adapter)),
                ("C4_ADAPTER_AFTER", s.digest(self.after_adapter))):
            self.patch(owner, key, value)
        self.source = svc._user_root() / "publisher-source"
        self.source.mkdir(mode=0o700)
        self.write(self.source / "git-publish.mjs", self.after_publisher)
        self.write(self.source / "workspace-access.mjs", self.after_adapter)
        self.target = self.roots["state"] / owner.C4_PUBLISHER_TRANSACTION
        self.args = SimpleNamespace(account=self.account, operation="preview",
                                    source=str(self.source),
                                    expected_manifest_sha256=s.digest(before),
                                    expected_plan_sha256=None)
        self.originals = {
            n: {p.name: p.read_bytes() for p in (self.roots["state"] / n).iterdir()}
            for n in ("native-pool-pin", owner.TRANSACTION, s.TRANSACTION)
        }
        self.before = self.snapshot()

    def _patch(self, obj, name, value):
        patcher = mock.patch.object(obj, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, path, data):
        path.write_bytes(data)
        path.chmod(0o600)

    def snapshot(self):
        return {str(p.relative_to(self.roots["base"])): (p.read_bytes(), p.stat().st_mode)
                for p in self.roots["base"].rglob("*") if p.is_file()}

    def call(self, op, plan=None):
        return owner.run(svc, SimpleNamespace(**{
            **vars(self.args), "operation": op, "expected_plan_sha256": plan}))

    def apply(self):
        pd = self.call("preview")["planSha256"]
        result = self.call("apply", pd)
        return pd, result

    def assert_parents_unchanged(self):
        for name, blobs in self.originals.items():
            self.assertEqual({p.name: p.read_bytes()
                              for p in (self.roots["state"] / name).iterdir()}, blobs)

    def test_preview_is_readonly_and_requires_real_parent_chain(self):
        record = self.call("preview")
        self.assertEqual((record["effect"], record["phase"]), ("NOT_APPLIED", "PREVIEW"))
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.paper_calls)

    def test_apply_changes_publisher_then_adapter_then_manifest_and_commits_result_last(self):
        writes = []
        actual = svc._atomic_write_bytes
        def checked(path, data, mode=0o600):
            writes.append(path.name)
            return actual(path, data, mode=mode)
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=checked):
            pd, record = self.apply()
        self.assertEqual(writes, ["git-publish.mjs", "workspace-access.mjs", "manifest.json"])
        self.assertEqual(record["effect"], "APPLIED")
        self.assertTrue(record["durabilityConfirmed"])
        self.assertEqual((self.roots["base"] / "git-publish.mjs").read_bytes(), self.after_publisher)
        self.assertEqual((self.roots["base"] / "workspace-access.mjs").read_bytes(), self.after_adapter)
        self.assertEqual(record["adapterSha256"], s.digest(self.after_adapter))
        self.assert_parents_unchanged()
        self.assertTrue(s.require_start(svc, self.account, self.roots))
        self.assertEqual(s._static_state(svc, self.account, self.roots,
                                       self.status_plan, self.status_raw), "COMMITTED")
        self.assertEqual(self.call("status", pd)["effect"], "APPLIED")
        self.assertFalse(self.call("status", pd)["durabilityConfirmed"])
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed write")):
            self.assertEqual(self.call("reconcile", pd)["effect"], "APPLIED")

    def test_running_or_ambiguous_gateway_refuses_before_intent(self):
        pd = self.call("preview")["planSha256"]
        with mock.patch.object(svc, "_lifecycle_inspect", return_value={"pid": 1}):
            with self.assertRaises(SystemExit):
                self.call("apply", pd)
        with mock.patch.object(svc, "_lifecycle_inspect", side_effect=SystemExit("ambiguous")):
            with self.assertRaises(SystemExit):
                self.call("apply", pd)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_wrong_account_preimage_source_plan_and_unaccepted_global_target_refuse(self):
        pd = self.call("preview")["planSha256"]
        with self.assertRaises(SystemExit):
            self.call("apply", "f" * 64)
        self.args.expected_manifest_sha256 = "0" * 64
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.args.expected_manifest_sha256 = owner.C4_PUBLISHER_BEFORE_MANIFEST
        self.args.account = "chatgpt2-personal"
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.args.account = self.account
        self.write(self.source / "git-publish.mjs", b"future generic target")
        with self.assertRaises(SystemExit):
            self.call("apply", pd)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_source_symlink_and_foreign_directory_refuse(self):
        real = self.source / "git-publish.mjs"
        real.unlink()
        real.symlink_to(self.roots["base"] / "git-publish.mjs")
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.assertFalse(self.target.exists())

    def test_each_missing_parent_completion_refuses_preview_and_start(self):
        pd, _ = self.apply()
        for name in self.originals:
            path = self.roots["state"] / name / "result.json"
            saved = path.read_bytes()
            path.unlink()
            with self.subTest(parent=name):
                with self.assertRaises((SystemExit, OSError)):
                    self.call("status", pd)
                with self.assertRaises((SystemExit, OSError)):
                    s.require_start(svc, self.account, self.roots)
            self.write(path, saved)

    def test_paper_selection_change_refuses_even_with_exact_installed_hashes(self):
        self.patch(svc, "_frozen_paper_fleet_module", lambda: SimpleNamespace(
            plan_selection=lambda *a, **k: {"manifestBytes": b"forged", "configBytes": b"forged"}))
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.assertFalse(self.target.exists())

    def test_interrupted_private_preparation_never_publishes_partial_journal(self):
        pd = self.call("preview")["planSha256"]
        actual = svc._fabric_release_new
        def torn(path, data):
            if path.name == "publisher.after":
                actual(path, data[:1])
                raise OSError("interrupted preparation")
            return actual(path, data)
        with mock.patch.object(svc, "_fabric_release_new", side_effect=torn):
            with self.assertRaises(OSError):
                self.call("apply", pd)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_lost_intent_rename_requires_original_plan_reconcile_and_blocks_start(self):
        pd = self.call("preview")["planSha256"]
        actual = s._rename_new
        def lost(svc_arg, source, destination):
            actual(svc_arg, source, destination)
            if destination == self.target:
                raise OSError("lost callback after exclusive rename")
        with mock.patch.object(s, "_rename_new", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        self.assertEqual(self.call("status", pd)["phase"], "OLD")
        with self.assertRaises((SystemExit, OSError)):
            s.require_start(svc, self.account, self.roots)
        with self.assertRaises(SystemExit):
            self.call("apply", pd)
        self.assertEqual(self.call("reconcile", pd)["effect"], "APPLIED")

    def test_publisher_only_and_manifest_without_result_block_start(self):
        pd = self.call("preview")["planSha256"]
        actual = svc._atomic_write_bytes
        def lost(path, data, mode=0o600):
            actual(path, data, mode=mode)
            if path.name == "git-publish.mjs":
                raise OSError("lost publisher write")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        self.assertEqual(self.call("status", pd)["phase"], "PUBLISHER_ONLY")
        with self.assertRaises((SystemExit, OSError)):
            s.require_start(svc, self.account, self.roots)
        with mock.patch.object(s, "_publish_result", side_effect=OSError("missing receipt")):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("reconcile", pd)
        self.assertEqual(self.call("status", pd)["effect"], "EFFECT_UNKNOWN")
        with self.assertRaises((SystemExit, OSError)):
            s.require_start(svc, self.account, self.roots)
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed")):
            self.assertEqual(self.call("reconcile", pd)["effect"], "APPLIED")

    def test_nonprefix_foreign_module_and_mode_are_not_reconciled(self):
        pd, _ = self.apply()
        manifest = self.roots["manifest"]
        final = manifest.read_bytes()
        self.write(manifest, self.status_raw["manifest.after"])
        self.write(self.roots["base"] / "git-publish.mjs", b"foreign")
        with self.assertRaises(SystemExit):
            self.call("reconcile", pd)
        self.write(manifest, final)
        self.write(self.roots["base"] / "git-publish.mjs", self.after_publisher)
        other = self.roots["base"] / "workspace-access.mjs"
        old_mode = other.stat().st_mode & 0o777
        other.chmod(0o400 if old_mode == 0o600 else 0o600)
        with self.assertRaises(SystemExit):
            self.call("status", pd)

    def test_manifest_first_mixture_refuses_without_repair(self):
        pd, _ = self.apply()
        self.write(self.roots["base"] / "git-publish.mjs", self.before_publisher)
        with self.assertRaises(SystemExit):
            self.call("reconcile", pd)

    def test_result_forgery_and_extra_transaction_file_refuse(self):
        pd, _ = self.apply()
        result = self.target / "result.json"
        saved = result.read_bytes()
        self.write(result, b'{"effect":"APPLIED"}')
        with self.assertRaises(SystemExit):
            self.call("status", pd)
        self.write(result, saved)
        self.write(self.target / "foreign", b"unrelated")
        with self.assertRaises(SystemExit):
            s.require_start(svc, self.account, self.roots)

    def test_second_apply_and_foreign_racing_transaction_never_replace_evidence(self):
        pd, _ = self.apply()
        after = self.snapshot()
        with self.assertRaises(SystemExit):
            self.call("apply", pd)
        self.assertEqual(self.snapshot(), after)
        with self.assertRaises(SystemExit):
            self.call("status", "f" * 64)

    def test_existing_transaction_collision_is_exclusive(self):
        pd = self.call("preview")["planSha256"]
        actual = s._rename_new
        def collision(svc_arg, source, destination):
            if destination == self.target:
                destination.mkdir(mode=0o700)
                self.write(destination / "foreign", b"owned elsewhere")
            return actual(svc_arg, source, destination)
        with mock.patch.object(s, "_rename_new", side_effect=collision):
            with self.assertRaises((SystemExit, OSError)):
                self.call("apply", pd)
        self.assertEqual((self.target / "foreign").read_bytes(), b"owned elsewhere")
        self.assertEqual((self.roots["base"] / "git-publish.mjs").read_bytes(), self.before_publisher)

    def test_changed_native_or_status_receipt_cannot_be_resigned_as_new_plan(self):
        pd, _ = self.apply()
        for parent in ("native-pool-pin", owner.TRANSACTION, s.TRANSACTION):
            path = self.roots["state"] / parent / "plan.json"
            saved = path.read_bytes()
            value = json.loads(saved)
            value["uid"] = os.getuid() + 1
            self.write(path, owner.encode(value))
            with self.subTest(parent=parent):
                with self.assertRaises((SystemExit, OSError)):
                    self.call("status", pd)
            self.write(path, saved)

    def test_durability_failure_blocks_start_and_reconcile_does_not_replay(self):
        pd, _ = self.apply()
        with mock.patch.object(s, "_sync_directory", side_effect=OSError("fsync failed")):
            with self.assertRaises(SystemExit):
                s.require_start(svc, self.account, self.roots)
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed")):
            self.assertEqual(self.call("reconcile", pd)["effect"], "APPLIED")

    def test_source_not_needed_after_commit_and_c2_cannot_claim_c4_receipt(self):
        pd, _ = self.apply()
        (self.source / "git-publish.mjs").unlink()
        (self.source / "workspace-access.mjs").unlink()
        self.assertEqual(self.call("status", pd)["effect"], "APPLIED")
        self.assertFalse(owner.c4_publisher_postimage(svc, "chatgpt2-personal", self.roots))
        forged = dict(self.status_plan, account="chatgpt2-personal")
        with self.assertRaises(SystemExit):
            owner.c4_publisher_postimage(svc, self.account, self.roots, forged, self.status_raw)

    def test_only_four_ordered_byte_states_are_admitted_and_none_start_without_result(self):
        import itertools
        pd = self.call("preview")["planSha256"]
        actual = s._rename_new
        def lost(svc_arg, source, destination):
            actual(svc_arg, source, destination)
            if destination == self.target:
                raise OSError("intent published")
        with mock.patch.object(s, "_rename_new", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        manifest_after = (self.target / "manifest.after").read_bytes()
        states = {(0, 0, 0): "OLD", (1, 0, 0): "PUBLISHER_ONLY",
                  (1, 1, 0): "MODULES", (1, 1, 1): "COMMITTED"}
        for state in itertools.product((0, 1), repeat=3):
            self.write(self.roots["base"] / "git-publish.mjs",
                       (self.before_publisher, self.after_publisher)[state[0]])
            self.write(self.roots["base"] / "workspace-access.mjs",
                       (self.before_adapter, self.after_adapter)[state[1]])
            self.write(self.roots["manifest"],
                       (self.status_raw["manifest.after"], manifest_after)[state[2]])
            snapshot = self.snapshot()
            with self.subTest(state=state):
                if state in states:
                    self.assertEqual(self.call("status", pd)["phase"], states[state])
                else:
                    with self.assertRaises(SystemExit):
                        self.call("status", pd)
                    with self.assertRaises(SystemExit):
                        self.call("reconcile", pd)
                with self.assertRaises((SystemExit, OSError)):
                    s.require_start(svc, self.account, self.roots)
                self.assertEqual(self.snapshot(), snapshot)

    def test_adapter_missing_wrong_or_symlink_source_cannot_prepare_intent(self):
        pd = self.call("preview")["planSha256"]
        path = self.source / "workspace-access.mjs"
        for kind in ("missing", "wrong", "symlink"):
            path.unlink()
            if kind == "wrong":
                self.write(path, b"foreign adapter")
            elif kind == "symlink":
                path.symlink_to(self.roots["base"] / "workspace-access.mjs")
            with self.subTest(kind=kind):
                with self.assertRaises((SystemExit, OSError)):
                    self.call("apply", pd)
                self.assertFalse(self.target.exists())
                self.assertEqual(self.snapshot(), self.before)
            if path.is_symlink() or path.exists():
                path.unlink()
            self.write(path, self.after_adapter)

    def test_lost_adapter_write_reconciles_only_manifest_and_blocks_start(self):
        pd = self.call("preview")["planSha256"]
        actual = svc._atomic_write_bytes
        def lost(path, data, mode=0o600):
            actual(path, data, mode=mode)
            if path.name == "workspace-access.mjs":
                raise OSError("lost adapter write")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        self.assertEqual(self.call("status", pd)["phase"], "MODULES")
        with self.assertRaises((SystemExit, OSError)):
            s.require_start(svc, self.account, self.roots)
        writes = []
        def checked(path, data, mode=0o600):
            writes.append(path.name)
            return actual(path, data, mode=mode)
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=checked):
            self.assertEqual(self.call("reconcile", pd)["effect"], "APPLIED")
        self.assertEqual(writes, ["manifest.json"])
        self.assertTrue(s.require_start(svc, self.account, self.roots))
        self.assert_parents_unchanged()

    def test_adapter_only_prefix_and_foreign_adapter_refuse_without_repair(self):
        pd = self.call("preview")["planSha256"]
        actual = s._rename_new
        def lost(svc_arg, source, destination):
            actual(svc_arg, source, destination)
            if destination == self.target:
                raise OSError("intent published")
        with mock.patch.object(s, "_rename_new", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        adapter = self.roots["base"] / "workspace-access.mjs"
        for data in (self.after_adapter, b"foreign"):
            self.write(adapter, data)
            snapshot = self.snapshot()
            with self.subTest(data=data):
                with self.assertRaises(SystemExit):
                    self.call("reconcile", pd)
                with self.assertRaises((SystemExit, OSError)):
                    s.require_start(svc, self.account, self.roots)
                self.assertEqual(self.snapshot(), snapshot)

    def test_retained_adapter_payload_cannot_be_resigned_or_replaced(self):
        pd, _ = self.apply()
        for name in ("adapter.before", "adapter.after"):
            path = self.target / name
            saved = path.read_bytes()
            self.write(path, b"foreign retained adapter")
            with self.subTest(name=name):
                with self.assertRaises(SystemExit):
                    self.call("status", pd)
                with self.assertRaises((SystemExit, OSError)):
                    s.require_start(svc, self.account, self.roots)
            self.write(path, saved)

    def test_status_does_not_sync_or_mutate_any_retained_evidence(self):
        pd, _ = self.apply()
        snapshot = self.snapshot()
        with mock.patch.object(s, "_sync_directory", side_effect=AssertionError("status wrote")):
            self.assertEqual(self.call("status", pd)["effect"], "APPLIED")
        self.assertEqual(self.snapshot(), snapshot)



class HistoricalStatusPairTests(unittest.TestCase):
    """Qualify frozen forward input without reinterpreting a changed live pair."""

    patch = OwnerTransactionTests.patch
    patch_object = OwnerTransactionTests.patch_object
    write = OwnerTransactionTests.write
    preview = OwnerTransactionTests.preview
    apply = OwnerTransactionTests.apply

    def setUp(self):
        import private_service_pin as pin
        OwnerTransactionTests.setUp(self)
        self.original_plan = {
            "account": self.account, "fixture": "authenticated-original",
            "config_mode": 0o600, "manifest_mode": 0o600,
        }
        self.original_raw = {
            "config.before.json": self.config,
            "config.after.json": self.config,
            "manifest.before.json": self.before,
            "manifest.after.json": self.before,
        }
        self.pin = pin.plan_sha(self.svc, self.original_plan)
        self.original_path = self.roots["state"] / "native-pool-pin"
        self.original_path.mkdir(mode=0o700)
        for name, blob in self.original_raw.items():
            self.write(self.original_path / name, blob)
        self.write(self.original_path / "plan.json",
                   self.svc._fabric_release_json(self.original_plan))
        self.write(self.original_path / "intent.json",
                   self.svc._fabric_release_json({
                       "schema": pin.SCHEMA, "planSha256": self.pin}))
        self.write(self.original_path / "result.json",
                   self.svc._fabric_release_json({
                       "schema": pin.SCHEMA, "planSha256": self.pin,
                       "effect": "APPLIED"}))
        self.apply(self.preview())

    def qualify(self, **changes):
        args = dict(
            original_plan=self.original_plan, original_raw=self.original_raw,
            config_bytes=self.config, manifest_bytes=self.after,
        )
        args.update(changes)
        return s.historical_pair(self.svc, self.account, self.roots, **args)

    def test_complete_retained_status_chain_qualifies(self):
        self.assertTrue(self.qualify())

    def test_frozen_pair_survives_forward_after_pair_installation(self):
        self.write(self.roots["config"], b'{"forward":"new configured native pool"}')
        self.write(self.roots["manifest"], b'{"forward":"new manifest"}')
        with mock.patch.object(s, "_original_pin",
                               side_effect=AssertionError("native context reacquired")), \
             mock.patch.object(s, "_confirm_retained_durability",
                               side_effect=AssertionError("historical read acknowledged")):
            self.assertTrue(self.qualify())

    def test_missing_status_transaction_does_not_authorize_a_chain(self):
        shutil.rmtree(self.roots["state"] / s.TRANSACTION)
        self.assertFalse(self.qualify())

    def test_changed_original_applied_receipt_refuses(self):
        self.write(self.original_path / "result.json", b'{"effect":"APPLIED"}')
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_CHANGED"):
            self.qualify()

    def test_original_fingerprint_change_between_reads_refuses(self):
        actual = self.svc._fabric_release_bytes
        changed = False
        target = self.original_path / "config.before.json"
        def raced(path, *args, **kwargs):
            nonlocal changed
            result = actual(path, *args, **kwargs)
            if Path(path) == target and not changed:
                changed = True
                self.write(target, b"changed after fingerprint read")
            return result
        with mock.patch.object(self.svc, "_fabric_release_bytes", side_effect=raced):
            with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_CHANGED"):
                self.qualify()
        self.assertTrue(changed)

    def test_caller_original_snapshots_must_match_retained_bytes(self):
        raw = dict(self.original_raw)
        raw["config.after.json"] = b"substituted original"
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_CHANGED"):
            self.qualify(original_raw=raw)

    def test_changed_status_applied_receipt_refuses(self):
        self.write(self.roots["state"] / s.TRANSACTION / "result.json",
                   b'{"effect":"APPLIED","planSha256":"wrong"}')
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_PIN_CHANGED"):
            self.qualify()

    def test_status_must_be_successor_of_exact_authenticated_original(self):
        raw = dict(self.original_raw)
        raw["manifest.after.json"] = b'{"foreign":"intermediate manifest"}'
        self.write(self.original_path / "manifest.after.json",
                   raw["manifest.after.json"])
        with self.assertRaisesRegex(SystemExit, "ORIGINAL_SUCCESSOR_EDGE_CHANGED"):
            self.qualify(original_raw=raw)

    def test_frozen_endpoint_must_equal_retained_status_postimage(self):
        with self.assertRaisesRegex(SystemExit, "RETAINED_ENDPOINT_CHANGED"):
            self.qualify(manifest_bytes=self.before)

    def test_installed_status_module_tamper_refuses(self):
        self.write(self.roots["base"] / s.MODULE, b"unqualified status")
        with self.assertRaisesRegex(SystemExit, "RETAINED_ENDPOINT_CHANGED"):
            self.qualify()

    def test_other_installed_module_tamper_refuses(self):
        self.write(self.roots["base"] / "gateway.mjs", b"changed gateway")
        with self.assertRaisesRegex(SystemExit, "OTHER_MODULE_CHANGED"):
            self.qualify()

    def test_unqualified_enrollment_is_not_accepted_as_an_alternate_path(self):
        (self.roots["state"] / owner.TRANSACTION).mkdir(mode=0o700)
        with self.assertRaisesRegex(SystemExit, "ENROLLMENT_ACCOUNT_UNQUALIFIED"):
            self.qualify()

class C4InventorySourceIdentityTests(unittest.TestCase):
    def test_installed_successor_target_is_the_exact_shipped_publisher(self):
        publisher = Path(__file__).with_name("git-publish.mjs")
        self.assertEqual(owner.digest(publisher.read_bytes()), owner.C4_INVENTORY_AFTER)


class C4InventorySuccessorTests(unittest.TestCase):
    """The corrected publisher is a child of a real, retained v4 transaction."""
    build = C4PublisherSuccessorTests.build
    manifest_shape = C4PublisherSuccessorTests.manifest_shape
    PORTS = C4PublisherSuccessorTests.PORTS
    SOURCE = C4PublisherSuccessorTests.SOURCE
    _patch = C4PublisherSuccessorTests._patch
    write = C4PublisherSuccessorTests.write
    snapshot = C4PublisherSuccessorTests.snapshot
    call = C4PublisherSuccessorTests.call
    apply = C4PublisherSuccessorTests.apply
    assert_parents_unchanged = C4PublisherSuccessorTests.assert_parents_unchanged

    def setUp(self):
        C4PublisherSuccessorTests.setUp(self)
        pd, applied = self.apply()
        self.assertEqual(applied["effect"], "APPLIED")
        self.v4_target = self.target
        self.v4_manifest = self.roots["manifest"].read_bytes()
        self.originals[owner.C4_PUBLISHER_TRANSACTION] = {
            p.name: p.read_bytes() for p in self.v4_target.iterdir()}
        self.before_publisher = self.after_publisher
        self.after_publisher = b"// bounded streaming inventory publisher"
        for key, value in (
                ("C4_INVENTORY_PARENT_PLAN", pd),
                ("C4_INVENTORY_BEFORE_MANIFEST", owner.digest(self.v4_manifest)),
                ("C4_INVENTORY_AFTER", owner.digest(self.after_publisher))):
            self.patch(owner, key, value)
        self.write(self.source / "git-publish.mjs", self.after_publisher)
        self.args.expected_manifest_sha256 = owner.digest(self.v4_manifest)
        self.target = self.roots["state"] / owner.C4_INVENTORY_TRANSACTION
        self.before = self.snapshot()

    test_preview_is_readonly_and_requires_real_parent_chain = C4PublisherSuccessorTests.test_preview_is_readonly_and_requires_real_parent_chain
    test_running_or_ambiguous_gateway_refuses_before_intent = C4PublisherSuccessorTests.test_running_or_ambiguous_gateway_refuses_before_intent
    test_source_symlink_and_foreign_directory_refuse = C4PublisherSuccessorTests.test_source_symlink_and_foreign_directory_refuse
    test_each_missing_parent_completion_refuses_preview_and_start = C4PublisherSuccessorTests.test_each_missing_parent_completion_refuses_preview_and_start
    test_interrupted_private_preparation_never_publishes_partial_journal = C4PublisherSuccessorTests.test_interrupted_private_preparation_never_publishes_partial_journal
    test_lost_intent_rename_requires_original_plan_reconcile_and_blocks_start = C4PublisherSuccessorTests.test_lost_intent_rename_requires_original_plan_reconcile_and_blocks_start
    test_publisher_only_and_manifest_without_result_block_start = C4PublisherSuccessorTests.test_publisher_only_and_manifest_without_result_block_start
    test_result_forgery_and_extra_transaction_file_refuse = C4PublisherSuccessorTests.test_result_forgery_and_extra_transaction_file_refuse
    test_second_apply_and_foreign_racing_transaction_never_replace_evidence = C4PublisherSuccessorTests.test_second_apply_and_foreign_racing_transaction_never_replace_evidence
    test_existing_transaction_collision_is_exclusive = C4PublisherSuccessorTests.test_existing_transaction_collision_is_exclusive
    test_changed_native_or_status_receipt_cannot_be_resigned_as_new_plan = C4PublisherSuccessorTests.test_changed_native_or_status_receipt_cannot_be_resigned_as_new_plan
    test_durability_failure_blocks_start_and_reconcile_does_not_replay = C4PublisherSuccessorTests.test_durability_failure_blocks_start_and_reconcile_does_not_replay
    test_status_does_not_sync_or_mutate_any_retained_evidence = C4PublisherSuccessorTests.test_status_does_not_sync_or_mutate_any_retained_evidence

    def test_roundtrip_writes_only_publisher_then_manifest_and_preserves_all_v4_bytes(self):
        writes = []
        actual = svc._atomic_write_bytes
        def checked(path, data, mode=0o600):
            writes.append(path.name)
            return actual(path, data, mode=mode)
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=checked):
            pd, record = self.apply()
        self.assertEqual(writes, ["git-publish.mjs", "manifest.json"])
        self.assertEqual(record["generation"], owner.C4_INVENTORY_GENERATION)
        self.assertEqual(record["publisherSha256"], owner.digest(self.after_publisher))
        self.assertTrue(record["durabilityConfirmed"])
        self.assertEqual(record["effect"], "APPLIED")
        before = json.loads(self.v4_manifest)
        after = json.loads(self.roots["manifest"].read_bytes())
        before["files"]["git-publish.mjs"] = owner.digest(self.after_publisher)
        self.assertEqual(after, before)
        self.assert_parents_unchanged()
        self.assertTrue(s.require_start(svc, self.account, self.roots))
        self.assertEqual(s._static_state(svc, self.account, self.roots,
                                       self.status_plan, self.status_raw), "COMMITTED")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed write")):
            result = self.call("reconcile", pd)
        self.assertTrue(result["durabilityConfirmed"])
        self.assertFalse(self.call("status", pd)["durabilityConfirmed"])

    def test_wrong_account_parent_plan_source_and_preimage_refuse_before_intent(self):
        pd = self.call("preview")["planSha256"]
        with self.assertRaises(SystemExit):
            self.call("apply", "f" * 64)
        with mock.patch.object(owner, "C4_INVENTORY_PARENT_PLAN", "f" * 64):
            with self.assertRaises(SystemExit):
                self.call("preview")
        for field, value in (("account", "chatgpt2-personal"),
                             ("expected_manifest_sha256", "f" * 64)):
            with mock.patch.object(self.args, field, value):
                with self.assertRaises(SystemExit):
                    self.call("preview")
        self.write(self.source / "git-publish.mjs", b"unqualified future publisher")
        with self.assertRaises(SystemExit):
            self.call("apply", pd)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.snapshot(), self.before)

    def test_v4_retained_payloads_receipt_and_fingerprint_remain_required(self):
        pd, _ = self.apply()
        for name in owner.C4_PUBLISHER_FILES:
            path = self.v4_target / name
            saved = path.read_bytes()
            self.write(path, b"changed v4 retained parent")
            with self.subTest(name=name):
                with self.assertRaises((SystemExit, OSError, ValueError)):
                    self.call("status", pd)
                with self.assertRaises((SystemExit, OSError, ValueError)):
                    s.require_start(svc, self.account, self.roots)
            self.write(path, saved)
        self.assert_parents_unchanged()

    def test_three_prefix_states_only_and_incomplete_child_never_falls_back_to_v4(self):
        import itertools
        pd = self.call("preview")["planSha256"]
        actual = s._rename_new
        def lost(svc_arg, source, destination):
            actual(svc_arg, source, destination)
            if destination == self.target:
                raise OSError("intent published")
        with mock.patch.object(s, "_rename_new", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        final_manifest = (self.target / "manifest.after").read_bytes()
        states = {(0, 0): "OLD", (1, 0): "PUBLISHER_ONLY", (1, 1): "COMMITTED"}
        for state in itertools.product((0, 1), repeat=2):
            self.write(self.roots["base"] / "git-publish.mjs",
                       (self.before_publisher, self.after_publisher)[state[0]])
            self.write(self.roots["manifest"], (self.v4_manifest, final_manifest)[state[1]])
            snapshot = self.snapshot()
            with self.subTest(state=state):
                if state in states:
                    observed = self.call("status", pd)
                    self.assertEqual(observed["phase"], states[state])
                    if state == (1, 1):
                        self.assertEqual(observed["effect"], "EFFECT_UNKNOWN")
                else:
                    with self.assertRaises(SystemExit):
                        self.call("reconcile", pd)
                with self.assertRaises((SystemExit, OSError)):
                    s.require_start(svc, self.account, self.roots)
                self.assertEqual(self.snapshot(), snapshot)
        self.assert_parents_unchanged()

    def test_adapter_config_modes_and_manifest_projection_are_preserved(self):
        pd, _ = self.apply()
        for path in (self.roots["base"] / "workspace-access.mjs", self.roots["config"],
                     self.roots["manifest"], self.roots["base"] / "git-publish.mjs"):
            saved, file_mode = path.read_bytes(), path.stat().st_mode & 0o777
            for fault in ("bytes", "mode"):
                if fault == "bytes":
                    self.write(path, b"foreign installed state")
                else:
                    path.chmod(0o400 if file_mode == 0o600 else 0o600)
                with self.subTest(path=path.name, fault=fault):
                    with self.assertRaises((SystemExit, OSError)):
                        self.call("reconcile", pd)
                    with self.assertRaises((SystemExit, OSError)):
                        s.require_start(svc, self.account, self.roots)
                path.chmod(file_mode)
                self.write(path, saved)
                path.chmod(file_mode)
        self.assert_parents_unchanged()

    def test_lost_manifest_or_result_callback_reconciles_without_replacing_modules(self):
        pd = self.call("preview")["planSha256"]
        actual = svc._atomic_write_bytes
        def lost(path, data, mode=0o600):
            actual(path, data, mode=mode)
            if path == self.roots["manifest"]:
                raise OSError("lost manifest callback")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=lost):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("apply", pd)
        self.assertEqual(self.call("status", pd)["effect"], "EFFECT_UNKNOWN")
        actual_result = s._publish_result
        def lost_result(*args):
            actual_result(*args)
            raise OSError("lost result callback")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed write")), \
                mock.patch.object(s, "_publish_result", side_effect=lost_result):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.call("reconcile", pd)
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed write")):
            self.assertEqual(self.call("reconcile", pd)["effect"], "APPLIED")
        self.assert_parents_unchanged()


if __name__ == "__main__":
    unittest.main()
