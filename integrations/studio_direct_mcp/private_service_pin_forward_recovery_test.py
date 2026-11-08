"""Crash and incumbent-history proofs for the closed forward Go pin.

All state is disposable. The native boundary is explicit synthetic evidence;
the original records, state transitions, file publication and startup owners run.
"""
import copy
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service_pin_transition_test as fx

svc = fx.svc


class ForwardRecoveryTests(unittest.TestCase):
    def setUp(self):
        fx.ForwardPinTransitionTests.setUp(self)
        # Patch the loader to return the actual loaded owner whose I/O boundary
        # is faulted. Source mode otherwise loads a fresh sealed module each call.
        for name in ("_pin_owner_module", "_fleet_status_successor_owner_module"):
            owner = getattr(svc, name)()
            patch = mock.patch.object(svc, name, return_value=owner)
            patch.start()
            self.addCleanup(patch.stop)
    capture = fx.ForwardPinTransitionTests.capture
    forward_context = fx.ForwardPinTransitionTests.forward_context
    invoke = fx.ForwardPinTransitionTests.invoke
    prepare = fx.ForwardPinTransitionTests.prepare

    @property
    def tx(self):
        return self.roots["state"] / "native-pool-pin-forward"

    def test_visible_intent_with_failed_parent_sync_cannot_change_live_pair(self):
        self.prepare()
        sync = os.fsync
        parent = self.tx.parent.stat()
        before = (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes())
        def unacknowledged_parent(fd):
            opened = os.fstat(fd)
            if (self.tx.exists() and stat.S_ISDIR(opened.st_mode)
                    and (opened.st_dev, opened.st_ino) == (parent.st_dev, parent.st_ino)):
                raise OSError("visible intent parent durability is unconfirmed")
            return sync(fd)
        with mock.patch.object(os, "fsync", unacknowledged_parent):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_PREPARATION"):
                self.invoke()
            self.assertTrue((self.tx / "intent.json").is_file())
            self.assertEqual(before, (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes()))
            self.args.operation = "reconcile"
            with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("intent is not durable")):
                with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_DURABILITY"):
                    self.invoke()
            self.assertEqual(before, (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes()))
        self.assertTrue(self.invoke()["receiptCommitted"])

    def test_every_original_payload_is_required_before_preparation(self):
        origin = self.roots["state"] / "native-pool-pin"
        before = self.roots["config"].read_bytes()
        for name in ("config.before.json", "config.after.json",
                     "manifest.before.json", "manifest.after.json"):
            with self.subTest(name=name):
                path = origin / name
                raw = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaises(SystemExit):
                        self.invoke()
                    self.assertFalse(self.tx.exists())
                    self.assertEqual(self.roots["config"].read_bytes(), before)
                finally:
                    svc._fabric_release_new(path, raw)

    def test_original_closed_shape_is_not_replaced_by_matching_receipt_hash(self):
        owner = svc._pin_owner_module()
        origin = self.roots["state"] / "native-pool-pin"
        plan = json.loads((origin / "plan.json").read_bytes())
        plan["foreign"] = True
        identity = owner.plan_sha(svc, plan)
        for name, value in {
            "plan.json": plan,
            "intent.json": {"schema": owner.SCHEMA, "planSha256": identity},
            "result.json": {"schema": owner.SCHEMA, "planSha256": identity, "effect": "APPLIED"},
        }.items():
            (origin / name).write_bytes(svc._fabric_release_json(value))
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertFalse(self.tx.exists())

    def test_go_predecessor_digest_must_match_even_when_pool_path_matches(self):
        self.binding["go_prior_successor_digest"] = "e" * 64
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertFalse(self.tx.exists())

    def test_changed_original_custody_blocks_partial_reconciliation(self):
        self.prepare()
        write = svc._atomic_write_bytes
        def lose_config_reply(path, data, **kwargs):
            write(path, data, **kwargs)
            if path == self.roots["config"]:
                raise OSError("lost original config reply")
        with mock.patch.object(svc, "_atomic_write_bytes", lose_config_reply):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        (self.roots["state"] / "native-pool-pin" / "config.after.json").unlink()
        before = self.roots["manifest"].read_bytes()
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("must not write")):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertEqual(self.roots["manifest"].read_bytes(), before)

    def test_completed_go_allows_only_same_complete_pair_acknowledgment(self):
        self.prepare()
        owner = svc._fleet_status_successor_owner_module()
        with mock.patch.object(owner, "_publish_result", side_effect=OSError("lost receipt")):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        self.assertFalse((self.tx / "result.json").exists())
        self.binding["phase"] = "SELECTED"
        self.args.operation = "reconcile"
        before = (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes())
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("pair replay")):
            value = self.invoke()
        self.assertTrue(value["receiptCommitted"])
        self.assertEqual(value["effect"], "APPLIED")
        self.assertEqual(before, (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes()))

    def test_completed_go_cannot_resume_a_partial_pair(self):
        self.prepare()
        write = svc._atomic_write_bytes
        def lose_reply(path, data, **kwargs):
            write(path, data, **kwargs)
            if path == self.roots["config"]:
                raise OSError("lost config reply")
        with mock.patch.object(svc, "_atomic_write_bytes", lose_reply):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.binding["phase"] = "SELECTED"
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("late pair mutation")):
            with self.assertRaisesRegex(SystemExit, "SUCCESSOR_ALREADY_ADVANCED"):
                self.invoke()

    def test_visible_receipt_requires_durability_before_acknowledgment(self):
        self.prepare()
        owner = svc._fleet_status_successor_owner_module()
        publish = owner._publish_result
        def lose_receipt_reply(*args):
            publish(*args)
            raise OSError("reply lost after visible receipt")
        with mock.patch.object(owner, "_publish_result", lose_receipt_reply):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN"):
                self.invoke()
        self.assertTrue((self.tx / "result.json").is_file())
        self.args.operation = "reconcile"
        with mock.patch.object(owner, "_sync_directory", side_effect=OSError("directory sync failed")):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_DURABILITY"):
                self.invoke()
        with mock.patch.object(owner, "_publish_result", side_effect=AssertionError("receipt replay")), \
             mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("pair replay")):
            self.assertTrue(self.invoke()["receiptCommitted"])

    def test_directory_open_failure_cannot_admit_start(self):
        self.prepare()
        self.invoke()
        self.binding["phase"] = "SELECTED"
        real_open = os.open
        def broken_open(path, flags, *args, **kwargs):
            if Path(path) == self.tx and flags & os.O_DIRECTORY:
                raise PermissionError("directory cannot be opened")
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(os, "open", broken_open), \
             mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_DURABILITY"):
                svc._pin_require_start(self.account, self.roots)
        self.assertFalse(self.loaded)

    def test_file_sync_failure_cannot_become_committed_status(self):
        self.prepare()
        self.invoke()
        self.args.operation = "status"
        with mock.patch.object(os, "fsync", side_effect=OSError("file sync failed")):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_DURABILITY"):
                self.invoke()

    def test_partial_prerequisites_never_publish_or_hold_the_active_transaction(self):
        self.prepare()
        before = (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes())
        write = svc._fabric_release_new
        def fail_staging(path, raw, **kwargs):
            if path.name == "config.before.json":
                raise OSError("interrupted prerequisite publication")
            return write(path, raw, **kwargs)
        with mock.patch.object(svc, "_fabric_release_new", fail_staging):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertFalse(self.tx.exists())
        self.assertEqual(before, (self.roots["config"].read_bytes(), self.roots["manifest"].read_bytes()))
        partial = list(self.roots["state"].glob(".native-pool-pin-forward.*"))
        self.assertEqual(len(partial), 1)
        self.assertTrue((partial[0] / "plan.json").is_file())
        self.args.operation = "preview"
        preview = self.invoke()
        self.assertEqual(preview["planSha256"], self.args.expected_plan_sha256)
        self.args.operation = "apply"
        self.assertTrue(self.invoke()["receiptCommitted"])

    def test_lost_intent_rename_reply_reconciles_the_original_complete_intent(self):
        self.prepare()
        owner = svc._fleet_status_successor_owner_module()
        rename = owner._rename_new
        def lose_reply(*args):
            rename(*args)
            raise OSError("lost exclusive publication reply")
        before = self.roots["config"].read_bytes()
        with mock.patch.object(owner, "_rename_new", lose_reply):
            with self.assertRaisesRegex(SystemExit, "EFFECT_UNKNOWN_PREPARATION"):
                self.invoke()
        self.assertTrue((self.tx / "intent.json").is_file())
        self.assertEqual(before, self.roots["config"].read_bytes())
        self.args.operation = "reconcile"
        pin = svc._pin_owner_module()
        with mock.patch.object(pin, "publish_forward_intent", side_effect=AssertionError("intent replay")):
            self.assertTrue(self.invoke()["receiptCommitted"])

    def test_new_or_missing_predecessor_record_cannot_bypass_original_start(self):
        self.prepare()
        self.invoke()
        self.binding["phase"] = "SELECTED"
        (self.roots["state"] / "fleet-status-module-successor").mkdir(mode=0o700)
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises((SystemExit, OSError)):
                svc._pin_require_start(self.account, self.roots)
        self.assertFalse(self.loaded)



def binding_for_existing(roots, new_pool):
    """Use the fixture's full original pin as the synthetic native predecessor."""
    p = json.loads((roots["state"] / "native-pool-pin" / "plan.json").read_bytes())
    original = {key: p[key] for key in (
        "successor_bundle", "successor_digest", "target_generation",
        "expected_selection", "pool_target", "pool_previous", "pool_bridge")}
    return {
        "go_digest": "a" * 64, "go_schema": "native-ingress-go-application-retained.v1",
        "go_generation": "b" * 64,
        "go_expected_selection": {"schema": "native-code-selection.v1",
            "generation": "c" * 64, "previous": "d" * 64, "sequence": 35},
        "go_bootstrap_digest": "e" * 64,
        "go_prior_successor_digest": p["successor_digest"],
        "go_component_sha256": "f" * 64, "go_manifest_sha256": "0" * 64,
        "pool_target": p["pool_target"], "pool_previous": p["pool_bridge"],
        "pool_bridge": hashlib.sha256(new_pool).hexdigest(),
        "store": str(roots["state"] / "synthetic-native-store"),
        "phase": "PREVIOUS", "original_successor": original,
    }


class ForwardEnrollmentTests(unittest.TestCase):
    capture = fx.ForwardPinTransitionTests.capture
    forward_context = fx.ForwardPinTransitionTests.forward_context
    invoke = fx.ForwardPinTransitionTests.invoke
    prepare = fx.ForwardPinTransitionTests.prepare

    def setUp(self):
        import private_service_pin_enrollment_test as enrollment_fixture
        self.case = enrollment_fixture.EnrollmentTests(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.applied()
        self.home, self.account, self.roots = self.case.home, self.case.account, self.case.roots
        self.new_pool = b"qualified-enrollment-forward-bridge"
        self.binding = binding_for_existing(self.roots, self.new_pool)
        # The unit native boundary names a real disposable predecessor path.
        Path(self.binding["original_successor"]["successor_bundle"]).mkdir(mode=0o700)
        self.args = SimpleNamespace(account=self.account,
            forward_go_bundle=str(self.home / "qualified-go"),
            expected_plan_sha256=None, operation="preview")

    def selected(self):
        self.prepare()
        self.invoke()
        Path(self.binding["pool_target"]).write_bytes(self.new_pool)
        self.binding["phase"] = "SELECTED"

    def test_real_enrollment_and_forward_owners_admit_the_same_start(self):
        original = {p.name: p.read_bytes() for p in self.case.tx.iterdir()}
        self.selected()
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            value = self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
        self.assertTrue(value["started"])
        self.assertTrue(self.case.loaded)
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.case.tx.iterdir()})

    def test_forward_start_keeps_the_enrollment_receipt_fence(self):
        self.selected()
        (self.case.tx / "result.json").write_bytes(b"{}")
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                svc.cmd_start(SimpleNamespace(account=self.account))
        self.assertFalse(self.case.loaded)

    def test_forward_start_keeps_the_enrollment_module_seal(self):
        self.selected()
        (self.roots["base"] / "workspace-access.mjs").write_bytes(b"foreign module")
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                svc.cmd_start(SimpleNamespace(account=self.account))
        self.assertFalse(self.case.loaded)


class ForwardStatusSuccessorTests(unittest.TestCase):
    capture = fx.ForwardPinTransitionTests.capture
    forward_context = fx.ForwardPinTransitionTests.forward_context
    invoke = fx.ForwardPinTransitionTests.invoke
    prepare = fx.ForwardPinTransitionTests.prepare

    def patch(self, target, name, value):
        p = mock.patch.dict(target, {name: value}) if isinstance(target, dict) else mock.patch.object(target, name, value)
        p.start()
        self.addCleanup(p.stop)

    def setUp(self):
        from contextlib import contextmanager
        fx.ForwardPinTransitionTests.setUp(self)
        pin = svc._pin_owner_module()
        status = svc._fleet_status_successor_owner_module()
        self.status = status
        self.patch(svc, "_pin_owner_module", lambda: pin)
        self.patch(svc, "_fleet_status_successor_owner_module", lambda: status)
        # Use the actual current fixture bridge for the completed original pin.
        config = json.loads(self.roots["config"].read_bytes())
        config["fleetStatus"]["fabricLauncherSha256"] = hashlib.sha256(self.pool.read_bytes()).hexdigest()
        self.roots["config"].write_bytes(svc._fabric_release_json(config))
        manifest = json.loads(self.roots["manifest"].read_bytes())
        manifest["configHash"] = pin.digest(self.roots["config"].read_bytes())
        self.roots["manifest"].write_bytes(svc._fabric_release_json(manifest))
        origin = self.roots["state"] / "native-pool-pin"
        for p in origin.iterdir():
            p.unlink()
        origin.rmdir()
        historical = dict(self.binding["original_successor"])
        historical["pool_bridge"] = hashlib.sha256(self.pool.read_bytes()).hexdigest()
        original = fx.install_original_pin_record(
            svc, self.roots, self.account, str(self.pool), "1" * 64,
            original_binding=historical)
        original_binding = dict(original["binding"], phase="SELECTED")
        @contextmanager
        def native(args):
            yield original_binding
        self.patch(svc, "_pin_native_context", native)
        old = (self.roots["base"] / status.MODULE).read_bytes()
        target = b"// qualified status successor fixture\n"
        before = self.roots["manifest"].read_bytes()
        future = json.loads(before)
        future["files"][status.MODULE] = status.digest(target)
        after = status.encoded_manifest(future)
        self.patch(status.PREDECESSOR_MANIFEST_SHA256, self.account, status.digest(before))
        self.patch(status.LEGACY_MODULE_SHA256, self.account, status.digest(old))
        self.patch(status, "TARGET_SOURCE_SHA256", status.digest(target))
        self.patch(status.POST_MANIFEST_RAW_SHA256, self.account, status.digest(after))
        self.patch(status.POST_MANIFEST_CANONICAL_SHA256, self.account,
                   svc._canonical_json_sha256(future))
        # Git publication is the external fixture boundary; the actual retained
        # status owner still derives and verifies every installed transition.
        self.patch(status, "_protected_source", lambda *args: (target, "a" * 40))
        args = SimpleNamespace(account=self.account, operation="preview",
            release_commit="e" * 40, expected_manifest_sha256=status.digest(before),
            expected_plan_sha256=None)
        preview = status.run(svc, args)
        args.expected_plan_sha256 = preview["planSha256"]
        args.operation = "apply"
        self.assertEqual(status.run(svc, args)["effect"], "APPLIED")
        self.tx = self.roots["state"] / status.TRANSACTION
        self.new_pool = b"qualified-status-successor-forward-bridge"
        self.binding = binding_for_existing(self.roots, self.new_pool)
        self.args = SimpleNamespace(account=self.account,
            forward_go_bundle=str(self.home / "qualified-go"),
            expected_plan_sha256=None, operation="preview")

    def selected(self):
        self.prepare()
        self.invoke()
        self.pool.write_bytes(self.new_pool)
        self.binding["phase"] = "SELECTED"

    def test_real_status_and_forward_owners_admit_the_same_start(self):
        before = {p.name: p.read_bytes() for p in self.tx.iterdir()}
        self.selected()
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            value = self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
        self.assertTrue(value["started"])
        self.assertTrue(self.loaded)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.tx.iterdir()})

    def test_forward_start_requires_the_original_status_receipt(self):
        self.selected()
        (self.tx / "result.json").write_bytes(b"{}")
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                svc.cmd_start(SimpleNamespace(account=self.account))
        self.assertFalse(self.loaded)

    def test_forward_start_retains_qualified_status_module_bytes(self):
        self.selected()
        (self.roots["base"] / self.status.MODULE).write_bytes(b"foreign status module")
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            with self.assertRaises(SystemExit):
                svc.cmd_start(SimpleNamespace(account=self.account))
        self.assertFalse(self.loaded)


class ForwardC4PublisherTests(unittest.TestCase):
    """The completed C4 child remains the same owner through native forward."""
    capture = fx.ForwardPinTransitionTests.capture
    forward_context = fx.ForwardPinTransitionTests.forward_context
    invoke = fx.ForwardPinTransitionTests.invoke
    prepare = fx.ForwardPinTransitionTests.prepare

    def setUp(self):
        import private_service_status_successor_test as status_fixture
        self.case = status_fixture.C4PublisherSuccessorTests(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.apply()
        self.home, self.account, self.roots = svc._user_root(), self.case.account, self.case.roots
        self.new_pool = b"qualified-c4-publisher-forward-bridge"
        self.binding = binding_for_existing(self.roots, self.new_pool)
        Path(self.binding["original_successor"]["successor_bundle"]).mkdir(mode=0o700)
        self.args = SimpleNamespace(account=self.account,
            forward_go_bundle=str(self.home / "qualified-go"),
            expected_plan_sha256=None, operation="preview")
        self.histories = {name: {p.name: p.read_bytes()
                                for p in (self.roots["state"] / name).iterdir()}
                          for name in ("native-pool-pin",
                                       svc._pin_enrollment_owner_module().TRANSACTION,
                                       svc._fleet_status_successor_owner_module().TRANSACTION,
                                       svc._pin_enrollment_owner_module().C4_PUBLISHER_TRANSACTION)}

    @property
    def tx(self):
        return self.roots["state"] / "native-pool-pin-forward"

    def selected(self):
        self.prepare()
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        Path(self.binding["pool_target"]).write_bytes(self.new_pool)
        self.binding["phase"] = "SELECTED"

    def assert_histories_unchanged(self):
        for name, expected in self.histories.items():
            self.assertEqual(expected, {p.name: p.read_bytes()
                                       for p in (self.roots["state"] / name).iterdir()})

    def start(self):
        with mock.patch.object(svc, "_pin_forward_native_context", self.forward_context):
            return self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))

    def test_complete_c4_chain_forwards_and_starts_without_rewriting_history(self):
        self.selected()
        plan = json.loads((self.tx / "plan.json").read_bytes())
        name = "native-pool-pin-enrollment-publisher"
        self.assertEqual(plan["predecessor_records"][name],
                         {k: hashlib.sha256(v).hexdigest() for k, v in self.histories[name].items()})
        self.assertTrue(self.start()["started"])
        self.assertTrue(any(call[:2] == ["launchctl", "bootstrap"]
                            for call in self.case.fixture["calls"]))
        self.assert_histories_unchanged()

    def test_config_only_interruption_reconciles_same_forward_without_publisher_writes(self):
        self.prepare()
        actual = svc._atomic_write_bytes
        def stop_after_config(path, data, mode=0o600):
            actual(path, data, mode=mode)
            if Path(path) == self.roots["config"]:
                raise OSError("inert interruption after forward config")
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=stop_after_config):
            with self.assertRaises(SystemExit):
                self.invoke()
        original_intent = (self.tx / "plan.json").read_bytes()
        writes = []
        def reconcile_write(path, data, mode=0o600):
            writes.append(Path(path))
            return actual(path, data, mode=mode)
        self.args.operation = "reconcile"
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=reconcile_write):
            self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.assertEqual(writes, [self.roots["manifest"]])
        self.assertEqual((self.tx / "plan.json").read_bytes(), original_intent)
        self.assert_histories_unchanged()

    def mutate_history(self, damage):
        target = self.case.target / ({"missing-result": "result.json", "changed-result": "result.json",
                                     "changed-payload": "publisher.before", "unexpected-file": "foreign.json"}[damage])
        original = target.read_bytes() if target.exists() else None
        if damage == "missing-result":
            target.unlink()
        else:
            target.write_bytes(b"foreign retained evidence")
            target.chmod(0o600)
        return target, original

    def restore_history(self, target, original):
        if original is None:
            target.unlink()
        else:
            target.write_bytes(original)
            target.chmod(0o600)

    def test_changed_c4_history_refuses_before_forward_effect(self):
        self.prepare()
        before = {name: self.roots[name].read_bytes() for name in ("config", "manifest")}
        for damage in ("missing-result", "changed-result", "changed-payload", "unexpected-file"):
            with self.subTest(damage=damage):
                target, original = self.mutate_history(damage)
                try:
                    with mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("forward write")):
                        with self.assertRaises(SystemExit):
                            self.invoke()
                    self.assertFalse(self.tx.exists())
                    self.assertEqual(before, {name: self.roots[name].read_bytes() for name in before})
                finally:
                    self.restore_history(target, original)

    def test_changed_c4_history_refuses_forward_start(self):
        self.selected()
        for damage in ("missing-result", "changed-result", "changed-payload", "unexpected-file"):
            with self.subTest(damage=damage):
                target, original = self.mutate_history(damage)
                try:
                    with self.assertRaises(SystemExit):
                        self.start()
                finally:
                    self.restore_history(target, original)
        self.assertFalse(any(call[:2] == ["launchctl", "bootstrap"]
                             for call in self.case.fixture["calls"]))

    def test_installed_c4_modules_remain_sealed_after_forward(self):
        self.selected()
        for name in ("git-publish.mjs", "workspace-access.mjs", svc._fleet_status_successor_owner_module().MODULE):
            with self.subTest(name=name):
                target = self.roots["base"] / name
                original = target.read_bytes()
                try:
                    target.write_bytes(b"foreign installed module")
                    with self.assertRaises(SystemExit):
                        self.start()
                finally:
                    target.write_bytes(original)
        self.assertFalse(any(call[:2] == ["launchctl", "bootstrap"]
                             for call in self.case.fixture["calls"]))

    def test_c4_receipt_durability_failure_prevents_forward_pair_write(self):
        self.prepare()
        owner = svc._fleet_status_successor_owner_module()
        actual = owner._confirm_retained_durability
        before = {name: self.roots[name].read_bytes() for name in ("config", "manifest")}
        def fail_c4(service, roots, target):
            if target == self.case.target:
                raise SystemExit("FLEET_STATUS_SUCCESSOR_DURABILITY_REFUSED")
            return actual(service, roots, target)
        with mock.patch.object(owner, "_confirm_retained_durability", side_effect=fail_c4):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertFalse(self.tx.exists())
        self.assertEqual(before, {name: self.roots[name].read_bytes() for name in before})

class ForwardPersonalPublisherTests(ForwardStatusSuccessorTests):
    fixture_account = fx.svc._pin_owner_module().PUBLISHER_ACCOUNT
    start = ForwardC4PublisherTests.start

    def setUp(self):
        super().setUp()
        from contextlib import nullcontext
        svc = fx.svc
        pin = svc._pin_owner_module()
        self.assertEqual(self.account, pin.PUBLISHER_ACCOUNT)
        source = self.home / "personal-publisher-source"
        source.mkdir(mode=0o700)
        before, after = {}, {}
        self.publisher_modules = {}
        for name in pin.PUBLISHER_FILES:
            original = (self.roots["base"] / name).read_bytes()
            successor = original + b"\n// Personal publisher composition fixture\n"
            (source / name).write_bytes(successor)
            (source / name).chmod(0o600)
            before[name] = pin.digest(original)
            after[name] = pin.digest(successor)
            self.publisher_modules[name] = successor
        self.patch(pin, "PUBLISHER_PREDECESSOR", before)
        self.patch(pin, "PUBLISHER_SUCCESSOR", after)
        self.patch(svc, "_native_selected_publication_lock_for_publisher",
                   lambda *args, **kwargs: nullcontext())
        args = SimpleNamespace(
            account=self.account, operation="preview", source=str(source),
            expected_manifest_sha256=pin.digest(self.roots["manifest"].read_bytes()),
            expected_plan_sha256=None,
        )
        preview = pin.run_publisher(svc, args)
        args.operation = "apply"
        args.expected_plan_sha256 = preview["planSha256"]
        applied = pin.run_publisher(svc, args)
        self.assertEqual(applied["phase"], "COMMITTED")
        self.assertEqual(applied["effect"], "APPLIED")
        self.assertTrue(self.status.require_start(svc, self.account, self.roots))
        self.binding = binding_for_existing(self.roots, self.new_pool)
        self.publisher_dir = self.roots["state"] / pin.PUBLISHER_TRANSACTION
        self.assertTrue((self.publisher_dir / "result.json").is_file())
        self.retained = {
            path: path.read_bytes()
            for path in self.roots["state"].rglob("*") if path.is_file()
        }
        self.assertGreater(len(self.retained), 3)

    def test_personal_publisher_forward_start_preserves_all_prior_histories(self):
        self.selected()
        self.assertTrue(self.start()["started"])
        for path, original in self.retained.items():
            self.assertEqual(path.read_bytes(), original)
        for name, expected in self.publisher_modules.items():
            self.assertEqual((self.roots["base"] / name).read_bytes(), expected)

    def test_missing_personal_publisher_completion_refuses_forward_start(self):
        self.selected()
        (self.publisher_dir / "result.json").unlink()
        with self.assertRaises(SystemExit):
            self.start()

    def test_changed_personal_publisher_module_refuses_forward_start(self):
        self.selected()
        name = next(iter(self.publisher_modules))
        target = self.roots["base"] / name
        target.write_bytes(target.read_bytes() + b"\nforeign publisher postimage\n")
        with self.assertRaises(SystemExit):
            self.start()
