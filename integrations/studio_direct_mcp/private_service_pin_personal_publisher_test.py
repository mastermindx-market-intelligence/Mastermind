"""C2 Personal selected-pin publisher successor: disposable real-file CAS tests.

No installed service, network or Git ref is modified. The source code's reviewed
publisher generations are replaced with synthetic fixture hashes only in tests.
"""
from __future__ import annotations

from contextlib import nullcontext
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc
import private_service_pin as pin
import private_service_status_successor as status_owner


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PersonalPublisherSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        self.account = "chatgpt2-personal"
        self.before_a, self.before_b = b"older publisher", b"older workspace"
        self.after_a, self.after_b = b"reviewed new publisher", b"reviewed new workspace"
        self.old = {"git-publish.mjs": sha(self.before_a),
                    "workspace-access.mjs": sha(self.before_b)}
        self.new = {"git-publish.mjs": sha(self.after_a),
                    "workspace-access.mjs": sha(self.after_b)}
        self.patch(svc, "_user_root", lambda: self.home)
        self.patch(svc, "_c2_lifecycle_mutex", lambda account: nullcontext())
        self.patch(svc, "_native_selected_publication_lock_for_publisher",
                   lambda account: nullcontext())
        self.loaded = False
        self.patch(svc, "_lifecycle_inspect",
                   lambda *a, **k: {} if self.loaded else None)
        self.patch(svc, "_native_pin_manifest_valid", lambda *a, **k: True)
        self.patch(svc, "_verify_staged_install", lambda *a, **k: {"seal": True})
        self.patch(svc, "_dependency_tree_hash", lambda *a, **k: "d" * 64)
        self.patch(pin, "PUBLISHER_PREDECESSOR", self.old)
        self.patch(pin, "PUBLISHER_SUCCESSOR", self.new)
        self.roots = svc._build_runtime_roots(self.account)
        for n in ("base", "state", "node_modules"):
            self.roots[n].mkdir(parents=True, mode=0o700, exist_ok=True)
        self.roots["plist"].parent.mkdir(parents=True, exist_ok=True)
        self.node = self.home / "runtime-node"
        self.backend = self.home / "backend.mjs"
        self.write(self.node, b"node")
        self.write(self.backend, b"backend")
        self.config = b'{"accountLabel":"chatgpt2-personal","closed":true}'
        self.write(self.roots["config"], self.config)
        self.write(self.roots["plist"], b"plist")
        self.write(self.roots["base"] / "git-publish.mjs", self.before_a)
        self.write(self.roots["base"] / "workspace-access.mjs", self.before_b)
        self.write(self.roots["base"] / "fleet-status.mjs", b"fleet successor")
        self.before_manifest = {
            "version": 2, "account": self.account,
            "label": "com.mastermind.studio-direct-private." + self.account,
            "configHash": sha(self.config),
            "plistHash": sha(b"plist"),
            "node": str(self.node), "backend": str(self.backend),
            "nodeHash": sha(b"node"), "backendHash": sha(b"backend"),
            "dependencyTreeHash": "d" * 64,
            "files": {**self.old, "fleet-status.mjs": sha(b"fleet successor")},
        }
        self.before_bytes = svc._fabric_release_json(self.before_manifest)
        self.write(self.roots["manifest"], self.before_bytes)
        self.expected_manifest = sha(self.before_bytes)
        self.status_plan = {
            "schema": status_owner.SCHEMA,
            "account": self.account,
            "configSha256": sha(self.config),
            "manifestAfterSha256": self.expected_manifest,
            "originalPinPlan": "0" * 64,
            "moduleMode": 0o600,
            "manifestMode": 0o600,
        }
        previous_status_manifest = copy.deepcopy(self.before_manifest)
        previous_status_manifest["files"]["fleet-status.mjs"] = sha(b"older fleet")
        self.status_raw = {
            "manifest.after": self.before_bytes,
            "manifest.before": svc._fabric_release_json(previous_status_manifest),
            "module.after": b"fleet successor",
            "module.before": b"older fleet",
        }
        self.status_digest = sha(svc._fabric_release_json(self.status_plan))
        self.fake_owner = SimpleNamespace(
            TRANSACTION="fleet-status-module-successor",
            SCHEMA=status_owner.SCHEMA,
            json=json,
            _identity=status_owner._identity,
            _same_identity=status_owner._same_identity,
            _sync_directory=status_owner._sync_directory,
            _rename_new=status_owner._rename_new,
            _retained=lambda *a: (self.status_plan, self.status_raw, self.status_digest),
            require_start=lambda *a: True,
        )
        self.patch(svc, "_fleet_status_successor_owner_module", lambda: self.fake_owner)
        self.patch(svc, "_pin_owner_module", lambda: pin)
        self.patch(status_owner, "_original_pin", lambda *a, forward_original=False: '0' * 64)
        self.status_dir = self.roots["state"] / self.fake_owner.TRANSACTION
        self.status_dir.mkdir(mode=0o700)
        self.write(self.status_dir / "result.json", svc._fabric_release_json({
            "schema": self.fake_owner.SCHEMA, "planSha256": self.status_digest,
            "effect": "APPLIED",
        }))
        self.source = self.home / "reviewed-source"
        self.source.mkdir(mode=0o700)
        self.write(self.source / "git-publish.mjs", self.after_a)
        self.write(self.source / "workspace-access.mjs", self.after_b)
        self.old_bytes = self.snapshot()
        self.args = SimpleNamespace(
            account=self.account, operation="preview", source=str(self.source),
            expected_manifest_sha256=self.expected_manifest,
            expected_plan_sha256=None,
        )

    def patch(self, target, name, value):
        p = mock.patch.object(target, name, value)
        p.start()
        self.addCleanup(p.stop)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o600)

    def snapshot(self):
        return tuple((self.roots["base"] / n).read_bytes() for n in pin.PUBLISHER_FILES) + (
            self.roots["manifest"].read_bytes(), self.roots["config"].read_bytes(),
            self.roots["plist"].read_bytes(),
        )

    def call(self, op, plan=None):
        return pin.run_publisher(svc, SimpleNamespace(
            **{**vars(self.args), "operation": op,
               "expected_plan_sha256": plan}))

    def test_preview_immutable_real_file_cas(self):
        result = self.call("preview")
        self.assertEqual(result["effect"], "NOT_APPLIED")
        self.assertEqual(result["phase"], "PREVIEW")
        self.assertTrue(result["retainedOriginalNativePin"])
        self.assertEqual(self.snapshot(), self.old_bytes)
        self.assertFalse((self.roots["state"] / pin.PUBLISHER_TRANSACTION).exists())

    def test_protected_target_hash_and_source_match_required(self):
        self.write(self.source / "git-publish.mjs", b"not-reviewed")
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.assertEqual(self.snapshot(), self.old_bytes)

    def test_wrong_manifest_and_account_refuse_before_effect(self):
        self.args.expected_manifest_sha256 = "f" * 64
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.args.account = "chatgpt2-business"
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.assertEqual(self.snapshot(), self.old_bytes)

    def test_missing_retained_status_successor_receipt_refuses(self):
        (self.status_dir / "result.json").unlink()
        with self.assertRaises(SystemExit):
            self.call("preview")
        self.assertEqual(self.snapshot(), self.old_bytes)

    def test_running_gateway_refuses_apply_before_intent(self):
        plan = self.call("preview")["planSha256"]
        self.loaded = True
        with self.assertRaises(SystemExit):
            self.call("apply", plan)
        self.assertFalse((self.roots["state"] / pin.PUBLISHER_TRANSACTION).exists())
        self.assertEqual(self.snapshot(), self.old_bytes)

    def test_wrong_plan_cas_refuses_before_journal(self):
        self.call("preview")
        with self.assertRaises(SystemExit):
            self.call("apply", "f" * 64)
        self.assertFalse((self.roots["state"] / pin.PUBLISHER_TRANSACTION).exists())
        self.assertEqual(self.snapshot(), self.old_bytes)

    def test_apply_manifest_last_receipt_then_original_start_recognition(self):
        plan = self.call("preview")["planSha256"]
        result = self.call("apply", plan)
        self.assertEqual(result["phase"], "COMMITTED")
        self.assertEqual(result["effect"], "APPLIED")
        expected = copy.deepcopy(self.before_manifest)
        expected["files"].update(self.new)
        self.assertEqual(self.roots["manifest"].read_bytes(),
                         svc._fabric_release_json(expected))
        self.assertEqual((self.roots["base"] / "git-publish.mjs").read_bytes(),
                         self.after_a)
        self.assertEqual((self.roots["base"] / "workspace-access.mjs").read_bytes(),
                         self.after_b)
        self.assertEqual(self.roots["config"].read_bytes(), self.config)
        self.assertTrue(pin.publisher_postimage(
            svc, self.account, self.roots, self.status_plan, self.status_raw,
            self.roots["manifest"].read_bytes()))
        self.assertEqual(self.call("status")["effect"], "APPLIED")
        self.assertEqual(self.call("reconcile", plan)["effect"], "APPLIED")

    def test_interrupt_after_first_module_refuses_start_until_reconciled(self):
        plan = self.call("preview")["planSha256"]
        original = svc._atomic_write_bytes
        def interrupted(path, data, mode):
            original(path, data, mode=mode)
            if path.name == "git-publish.mjs":
                raise OSError("simulated crash after first atomic file effect")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.call("apply", plan)
        self.assertEqual(self.call("status")["phase"], "PUBLISHER_ONLY")
        with self.assertRaises((OSError, SystemExit)):
            pin.publisher_postimage(svc, self.account, self.roots, self.status_plan,
                                    self.status_raw, self.roots["manifest"].read_bytes())
        with self.assertRaises(SystemExit):
            self.call("apply", plan)
        self.assertEqual(self.call("reconcile", plan)["effect"], "APPLIED")

    def test_tampered_result_and_module_refuse_completed_state(self):
        plan = self.call("preview")["planSha256"]
        self.call("apply", plan)
        journal = self.roots["state"] / pin.PUBLISHER_TRANSACTION
        self.write(journal / "result.json", b'{"effect":"APPLIED"}')
        with self.assertRaises(SystemExit):
            self.call("status")
        with self.assertRaises(SystemExit):
            pin.publisher_postimage(svc, self.account, self.roots, self.status_plan,
                                    self.status_raw, self.roots["manifest"].read_bytes())

    def test_original_predecessor_cannot_be_replaced_by_global_future_target(self):
        plan = self.call("preview")["planSha256"]
        self.call("apply", plan)
        # The immutable C2 successor's receipt survives a future generic fleet
        # publisher release, without being re-pinned to a moving global target.
        with mock.patch.dict(svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256, {
            "git-publish.mjs": "0" * 64,
            "workspace-access.mjs": "1" * 64,
        }):
            self.assertEqual(self.call("status")["effect"], "APPLIED")
            self.assertTrue(pin.publisher_postimage(
                svc, self.account, self.roots, self.status_plan, self.status_raw,
                self.roots["manifest"].read_bytes()))

    def test_existing_fleet_status_owner_allows_only_fully_committed_successor(self):
        self.assertEqual(status_owner._static_state(
            svc, self.account, self.roots, self.status_plan, self.status_raw), "COMMITTED")
        plan = self.call("preview")["planSha256"]
        self.call("apply", plan)
        self.assertEqual(status_owner._static_state(
            svc, self.account, self.roots, self.status_plan, self.status_raw), "COMMITTED")
        # The real fleet-status retained reader is separately tested; this
        # fixture supplies its already authenticated predecessor transaction.
        self.patch(status_owner, "_retained",
                   lambda *a, forward_original=False: (self.status_plan, self.status_raw, self.status_digest))
        self.assertTrue(status_owner.require_start(svc, self.account, self.roots))
        result = self.roots["state"] / pin.PUBLISHER_TRANSACTION / "result.json"
        result.unlink()
        with self.assertRaises((OSError, SystemExit)):
            status_owner.require_start(svc, self.account, self.roots)

    def test_native_publication_lock_encloses_every_module_and_manifest_write(self):
        from contextlib import contextmanager
        active = [False]
        writes = []
        original = svc._atomic_write_bytes
        @contextmanager
        def selected_lock(_account):
            self.assertFalse(active[0])
            active[0] = True
            try:
                yield
            finally:
                active[0] = False
        def checked_write(path, data, mode):
            self.assertTrue(active[0])
            writes.append(path.name)
            return original(path, data, mode=mode)
        self.patch(svc, "_native_selected_publication_lock_for_publisher", selected_lock)
        plan = self.call("preview")["planSha256"]
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=checked_write):
            self.assertEqual(self.call("apply", plan)["effect"], "APPLIED")
        self.assertEqual(writes, ["git-publish.mjs", "workspace-access.mjs", "manifest.json"])
        self.assertFalse(active[0])

    def test_foreign_module_or_mode_cannot_be_admitted_as_new_generation(self):
        plan = self.call("preview")["planSha256"]
        self.call("apply", plan)
        path = self.roots["base"] / "workspace-access.mjs"
        self.write(path, b"foreign")
        with self.assertRaises(SystemExit):
            self.call("status")
        self.write(path, self.after_b)
        path.chmod(0o644)
        with self.assertRaises(SystemExit):
            self.call("status")


    def test_torn_journal_staging_never_exposes_partial_transaction(self):
        plan = self.call("preview")["planSha256"]
        original = svc._fabric_release_new

        def torn(path, blob):
            if path.name == "workspace-access.mjs.after":
                original(path, blob[:1])
                raise OSError("simulated interrupted private journal staging")
            return original(path, blob)

        with mock.patch.object(svc, "_fabric_release_new", side_effect=torn):
            with self.assertRaises(OSError):
                self.call("apply", plan)
        self.assertEqual(self.snapshot(), self.old_bytes)
        self.assertFalse((self.roots["state"] / pin.PUBLISHER_TRANSACTION).exists())
        self.assertEqual(
            [x.name for x in self.roots["state"].iterdir()
             if x.name.startswith(".native-pin-publisher-intent.")], [])

    def test_lost_reply_after_atomic_journal_requires_same_plan_reconcile(self):
        plan = self.call("preview")["planSha256"]
        original_rename = self.fake_owner._rename_new

        def lost_result(svc_arg, staged, target):
            original_rename(svc_arg, staged, target)
            raise OSError("callback lost after journal publication")

        with mock.patch.object(self.fake_owner, "_rename_new", side_effect=lost_result):
            with self.assertRaises(SystemExit) as raised:
                self.call("apply", plan)
        self.assertEqual(
            str(raised.exception), "NATIVE_POOL_PIN_PREPARATION_EFFECT_UNKNOWN")
        self.assertEqual(self.snapshot(), self.old_bytes)
        self.assertEqual(self.call("status")["phase"], "OLD")
        with self.assertRaises(SystemExit) as refused:
            self.call("apply", plan)
        self.assertEqual(str(refused.exception),
                         "NATIVE_POOL_PIN_RECONCILIATION_REQUIRED")
        self.assertEqual(self.call("reconcile", plan)["effect"], "APPLIED")

    def test_completed_action_cannot_be_reapplied_as_a_second_write(self):
        plan = self.call("preview")["planSha256"]
        self.assertEqual(self.call("apply", plan)["effect"], "APPLIED")
        after = self.snapshot()
        with self.assertRaises(SystemExit) as refused:
            self.call("apply", plan)
        self.assertEqual(str(refused.exception),
                         "NATIVE_POOL_PIN_RECONCILIATION_REQUIRED")
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(self.call("status")["effect"], "APPLIED")

    def test_foreign_transaction_cannot_be_overwritten_by_atomic_journal(self):
        plan = self.call("preview")["planSha256"]
        actual_rename = self.fake_owner._rename_new
        target = self.roots["state"] / pin.PUBLISHER_TRANSACTION

        def racing_writer(svc_arg, source, dest):
            self.assertEqual(dest, target)
            dest.mkdir(mode=0o700)
            self.write(dest / "foreign.txt", b"unrelated owner's receipt")
            return actual_rename(svc_arg, source, dest)

        with mock.patch.object(self.fake_owner, "_rename_new", side_effect=racing_writer):
            with self.assertRaises((OSError, SystemExit)):
                self.call("apply", plan)
        self.assertEqual((target / "foreign.txt").read_bytes(),
                         b"unrelated owner's receipt")
        self.assertEqual(self.snapshot(), self.old_bytes)
        with self.assertRaises(SystemExit):
            self.call("status")


if __name__ == "__main__":
    unittest.main()
