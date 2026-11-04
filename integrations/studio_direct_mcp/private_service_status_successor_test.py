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


class SelectedC4LockTests(unittest.TestCase):
    """No nested native selector when qualifying retained C4 enrollment."""

    def test_existing_pin_and_c4_enrollment_are_checked_sequentially(self):
        import os
        import tempfile
        from contextlib import contextmanager
        from types import SimpleNamespace
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
            def selected_enrollment(svc, roots, operation):
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
                original_pin=selected_enrollment,
                encode=encoded, digest=s.digest,
                retained=lambda *a: (enrolled_plan, {}),
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
