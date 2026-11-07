"""C4 child continuation with the real native proof context and publication lock.

The completed C4 parent/child filesystem owners and native proof subprocess are
real. Native release contents are isolated fixtures, as in the existing C1
pruned-bootstrap integration tests; the actual retained-reader verifier has its
own native_install_retained_successor_test coverage. No host service, native
selection, credential, or Git effect is used.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import private_service as svc
import private_service_pin_enrollment as owner
import private_service_status_successor as status
import private_service_status_successor_test as fixtures


REAL_NATIVE_CONTEXT = svc._pin_native_context
RETAINED_DIGEST = "77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7"
RETAINED_GENERATION = "28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce"


class C4CompletedParentProofTests(unittest.TestCase):
    FIXTURE = fixtures.C4PublisherSuccessorTests
    EXPECTED_WRITES = ["git-publish.mjs", "workspace-access.mjs", "manifest.json"]

    def setUp(self):
        self.f = self.FIXTURE()
        self.f.native_successor_digest = RETAINED_DIGEST
        self.f.native_target_generation = RETAINED_GENERATION
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.home = svc._user_root()
        self.store = self.home / "native-code-releases"
        self.parent = json.loads((self.f.roots["state"] /
                                  "native-pool-pin/plan.json").read_bytes())
        self.bundle = Path(self.parent["successor_bundle"])
        self.bundle.mkdir(mode=0o700)
        native_plan = {
            "digest": self.parent["successor_digest"],
            "store": str(self.store),
            "expected_selection": self.parent["expected_selection"],
            "target_generation": self.parent["target_generation"],
            "entries": {"pool": {
                "target": self.parent["pool_target"],
                "previous": self.parent["pool_previous"],
                "bridge": self.parent["pool_bridge"]}},
        }
        plan_bytes = owner.encode(native_plan)
        (self.bundle / "PLAN.json").write_bytes(plan_bytes)
        (self.bundle / "receipt.json").write_bytes(owner.encode({
            "planSha256": owner.digest(plan_bytes)}))
        self.selection = {"schema": "native-code-selection.v1",
                          "generation": "a" * 64, "previous": "b" * 64,
                          "sequence": 26}
        (self.store / "CURRENT.json").write_bytes(owner.encode(self.selection))
        (self.store / "VERIFIED.json").write_bytes(owner.encode([
            RETAINED_GENERATION, self.selection["generation"],
            self.selection["previous"]]))
        rollout = self.home / "fixture-rollout"
        rollout.mkdir(mode=0o700)
        (rollout / "native_install.py").write_text(
            "import hashlib,json\n"
            "from pathlib import Path\n"
            "def read_successor(bundle):\n"
            " raise FileNotFoundError('historical bootstrap artifact pruned')\n"
            "def read_retained_successor_after_bootstrap_prune(bundle):\n"
            " bundle=Path(bundle); raw=(bundle/'PLAN.json').read_bytes()\n"
            " expected={'planSha256':hashlib.sha256(raw).hexdigest()}\n"
            " if json.loads((bundle/'receipt.json').read_bytes())!=expected:\n"
            "  raise ValueError('retained successor evidence changed')\n"
            " return json.loads(raw),{}\n"
            "def _upgrade_entries(p,complete=False):\n"
            " e=p['entries']['pool']\n"
            " if hashlib.sha256(Path(e['target']).read_bytes()).hexdigest()!=e['bridge']:\n"
            "  raise ValueError('ingress differs from retained bridge')\n")
        (rollout / "native_generation.py").write_text(
            "import json\n"
            "from pathlib import Path\n"
            "POINTER_SCHEMA='native-code-selection.v1'\n"
            "def current(store):\n"
            " store=Path(store); path=store/'CURRENT.json'\n"
            " value=json.loads(path.read_bytes())\n"
            " if (store/'DIVERGE').exists():\n"
            "  count_path=store/'proof-calls'\n"
            "  count=int(count_path.read_text()) if count_path.exists() else 0\n"
            "  count_path.write_text(str(count+1))\n"
            "  if count==2:\n"
            "   value['sequence']+=1; path.write_text(json.dumps(value))\n"
            " return value\n"
            "def verify(store,identity):\n"
            " allowed=json.loads((Path(store)/'VERIFIED.json').read_bytes())\n"
            " if identity not in allowed: raise ValueError('unverified generation')\n")
        actual_rollout = (Path(svc.__file__).resolve().parents[2] /
                          "ops/native_fabric/quota_continuity/rollout")
        spec = importlib.util.spec_from_file_location(
            "_c4_test_native_generation", actual_rollout / "native_generation.py")
        self.generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.generation)
        actual_run = svc.subprocess.run
        self.operations = []

        def native_run(argv, *args, **kwargs):
            argv = list(argv)
            at = next((i for i, value in enumerate(argv)
                       if isinstance(value, str) and
                       "import native_install as i" in value), None)
            if at is not None:
                argv[at + 1] = str(rollout)
                self.operations.append(argv[at + 5])
            return actual_run(argv, *args, **kwargs)

        self.patch(svc.subprocess, "run", native_run)
        self.patch(svc, "_pin_native_context", REAL_NATIVE_CONTEXT)
        native_lock = self.store / ".publication.lock"
        self.native_lock_before = ((native_lock.stat().st_ino, native_lock.read_bytes())
                                   if native_lock.exists() else None)

    def patch(self, obj, name, value):
        patcher = mock.patch.object(obj, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def assert_native_locked(self):
        with self.assertRaisesRegex(ValueError, "native publication already in progress"):
            with self.generation.publication_lock(self.store):
                self.fail("child released the native publication lock")

    def assert_native_released(self):
        with self.generation.publication_lock(self.store):
            pass

    def assert_native_lock_unmodified(self):
        native_lock = self.store / ".publication.lock"
        observed = ((native_lock.stat().st_ino, native_lock.read_bytes())
                    if native_lock.exists() else None)
        self.assertEqual(observed, self.native_lock_before)

    def native_args(self, operation):
        return SimpleNamespace(
            account="chatgpt4", operation=operation,
            successor_bundle=str(self.bundle),
            successor_plan_sha256=self.parent["successor_digest"])

    def test_completed_parent_apply_holds_native_lock_through_result_and_fingerprint(self):
        writes = []
        actual_write = svc._atomic_write_bytes
        actual_result = status._publish_result
        actual_fingerprint = owner.pin_fingerprint
        applied = {"result": False, "final_fingerprint": False}

        def write(path, data, mode=0o600):
            self.assert_native_locked()
            writes.append(path.name)
            return actual_write(path, data, mode=mode)

        def result(*args, **kwargs):
            self.assert_native_locked()
            value = actual_result(*args, **kwargs)
            applied["result"] = True
            return value

        def fingerprint(*args, **kwargs):
            if applied["result"]:
                self.assert_native_locked()
                applied["final_fingerprint"] = True
            return actual_fingerprint(*args, **kwargs)

        selected_before = (self.store / "CURRENT.json").read_bytes()
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=write), \
                mock.patch.object(status, "_publish_result", side_effect=result), \
                mock.patch.object(owner, "pin_fingerprint", side_effect=fingerprint):
            pd, record = self.f.apply()
        self.assertEqual(record["effect"], "APPLIED")
        self.assertTrue(record["durabilityConfirmed"])
        self.assertEqual(writes, self.EXPECTED_WRITES)
        self.assertTrue(applied["final_fingerprint"])
        self.assertEqual(set(self.operations), {"status"})
        self.assertEqual((self.store / "CURRENT.json").read_bytes(), selected_before)
        self.assertFalse((self.home / "historical-bootstrap").exists())
        self.f.assert_parents_unchanged()
        self.assert_native_released()
        self.assertEqual(self.f.call("status", pd)["effect"], "APPLIED")

    def test_preview_and_status_do_not_create_native_lock(self):
        pd = self.f.call("preview")["planSha256"]
        self.assert_native_lock_unmodified()
        with self.assertRaises(FileNotFoundError):
            self.f.call("status", pd)
        self.assert_native_lock_unmodified()
        self.assertEqual(self.f.snapshot(), self.f.before)

    def test_generic_native_apply_and_reconcile_still_refuse_pruned_bootstrap(self):
        for operation in ("apply", "reconcile"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_SUCCESSOR_REFUSED"):
                    with REAL_NATIVE_CONTEXT(self.native_args(operation)):
                        self.fail("generic native modification was admitted")
        self.assert_native_lock_unmodified()
        self.assertFalse(self.f.target.exists())
        self.assertEqual(self.f.snapshot(), self.f.before)

    def test_existing_native_lock_blocks_child_before_preparation(self):
        pd = self.f.call("preview")["planSha256"]
        with self.generation.publication_lock(self.store):
            for operation in ("apply", "reconcile"):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(ValueError, "native publication already in progress"):
                        self.f.call(operation, pd)
        self.assertFalse(self.f.target.exists())
        self.assertEqual(self.f.snapshot(), self.f.before)
        self.f.assert_parents_unchanged()

    def test_full_forward_selection_change_between_proofs_refuses_before_intent(self):
        pd = self.f.call("preview")["planSha256"]
        (self.store / "DIVERGE").write_text("1")
        with self.assertRaisesRegex(SystemExit, "NATIVE_PIN_ENROLLMENT_ORIGINAL_PIN_REFUSED"):
            self.f.call("apply", pd)
        self.assertEqual(json.loads((self.store / "CURRENT.json").read_bytes())["sequence"], 27)
        self.assertFalse(self.f.target.exists())
        self.assertEqual(self.f.snapshot(), self.f.before)
        self.assert_native_released()

    def test_changed_retained_evidence_refuses_preview_and_apply(self):
        pd = self.f.call("preview")["planSha256"]
        (self.bundle / "receipt.json").write_bytes(b'{"planSha256":"changed"}')
        for operation in ("preview", "apply"):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_SUCCESSOR_REFUSED"):
                    self.f.call(operation, pd)
        self.assertFalse(self.f.target.exists())
        self.assertEqual(self.f.snapshot(), self.f.before)

    def test_exception_releases_lock_and_retained_child_reconciles_in_place(self):
        pd = self.f.call("preview")["planSha256"]
        with mock.patch.object(svc, "_atomic_write_bytes", side_effect=OSError("write interrupted")):
            with self.assertRaisesRegex(SystemExit, "NATIVE_PIN_ENROLLMENT_EFFECT_UNKNOWN"):
                self.f.call("apply", pd)
        self.assertTrue(self.f.target.is_dir())
        self.assertFalse((self.f.target / "result.json").exists())
        self.assert_native_released()
        self.assertEqual(self.f.call("reconcile", pd)["effect"], "APPLIED")
        self.f.assert_parents_unchanged()
        self.assert_native_released()

    def test_committed_reconcile_holds_lock_without_replaying_writes(self):
        pd, _ = self.f.apply()
        actual = status._confirm_retained_durability
        checked = []

        def durability(*args, **kwargs):
            self.assert_native_locked()
            checked.append(True)
            return actual(*args, **kwargs)

        with mock.patch.object(status, "_confirm_retained_durability", side_effect=durability), \
                mock.patch.object(svc, "_atomic_write_bytes", side_effect=AssertionError("replayed write")):
            self.assertEqual(self.f.call("reconcile", pd)["effect"], "APPLIED")
        self.assertTrue(checked)
        self.f.assert_parents_unchanged()
        self.assert_native_released()


class C4InventoryCompletedParentProofTests(C4CompletedParentProofTests):
    FIXTURE = fixtures.C4InventorySuccessorTests
    EXPECTED_WRITES = ["git-publish.mjs", "manifest.json"]


if __name__ == "__main__":
    unittest.main()
