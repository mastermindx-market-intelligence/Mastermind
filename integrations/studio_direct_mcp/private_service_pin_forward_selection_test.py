"""Hermetic seven-seat native-selection forward-admission regressions.

The test executes the exact sandboxed subprocess proof from private_service,
using nonprivileged synthetic rollout modules and isolated files. It never
modifies host native generation, installed Studio accounts, or credentials.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import private_service as svc


ORIGINAL_SUCCESSOR = "77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7"
REVIEWED_SEATS = (
    "admin-business", "chatgpt1", "chatgpt2-business", "chatgpt2-personal",
    "chatgpt3", "chatgpt3-w570f6f34", "chatgpt3-wa2a9e6f9", "chatgpt4",
)
UNENROLLED = ("mastermind-os-publication", "fabric-read", "fabric-design",
              "chatgpt3-other", "chatgpt3-forged")

ORIGINAL_TARGET = "28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce"
CURRENT_TARGET = "9eec6f73903fabfdd6d15bfe6f815f652f0946b5838cef6d40e96ca5b7e7f185"
PRIOR_TARGET = "a" * 64
RECENT_PREVIOUS = "b" * 64


def original_subprocess_proof():
    """The test must run production's exact -I/-B subprocess script."""
    script = next(
        text for text in svc._pin_native_context.__wrapped__.__code__.co_consts
        if isinstance(text, str) and "import native_install as i" in text
    )
    assert "sys.argv[4]" in script
    return script


class NativeSelectionForwardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rollout = self.root / "rollout"
        self.bundle = self.root / "bundle"
        self.store = self.root / "store"
        self.rollout.mkdir()
        self.bundle.mkdir()
        self.store.mkdir()
        (self.rollout / "native_install.py").write_text(
            "import json\n"
            "from pathlib import Path\n"
            "def read_successor(bundle):\n"
            " return json.loads((bundle/'PLAN.json').read_text()), {}\n"
            "def _upgrade_entries(p, complete=False):\n"
            " raw=Path(p['entries']['pool']['target']).read_bytes()\n"
            " if raw != (b'COMPLETE_BRIDGE' if complete else b'PRIOR_BRIDGE'):\n"
            "  raise ValueError('ingress does not match reviewed bridge')\n"
        )
        (self.rollout / "native_generation.py").write_text(
            "import json\n"
            "from pathlib import Path\n"
            "POINTER_SCHEMA='native-code-selection.v1'\n"
            "def current(store):\n"
            " return json.loads((store/'CURRENT.json').read_text())\n"
            "def verify(store, identity):\n"
            " allowed=json.loads((store/'VERIFIED.json').read_text())\n"
            " if identity not in allowed: raise ValueError('unverified generation')\n"
            " return store / identity, {'generation':identity}\n"
        )
        self.prior = {
            "schema": "native-code-selection.v1",
            "generation": PRIOR_TARGET,
            "previous": "c" * 64,
            "sequence": 23,
        }
        self.selected = {
            "schema": "native-code-selection.v1",
            "generation": ORIGINAL_TARGET,
            "previous": PRIOR_TARGET,
            "sequence": 24,
        }
        self.forward = {
            "schema": "native-code-selection.v1",
            "generation": CURRENT_TARGET,
            "previous": RECENT_PREVIOUS,
            "sequence": 26,
        }
        self.plan = {
            "digest": ORIGINAL_SUCCESSOR,
            "store": str(self.store),
            "expected_selection": self.prior,
            "target_generation": ORIGINAL_TARGET,
            "entries": {"pool": {
                "target": str(self.root / "pool"),
                "previous": "reviewed-original-entry",
                "bridge": "reviewed-complete-entry",
            }},
        }
        self.write_plan()
        self.set_selection(self.forward)
        (self.store / "VERIFIED.json").write_text(
            json.dumps([ORIGINAL_TARGET, CURRENT_TARGET, RECENT_PREVIOUS])
        )
        (self.root / "pool").write_bytes(b"COMPLETE_BRIDGE")

    def write_plan(self):
        (self.bundle / "PLAN.json").write_text(json.dumps(self.plan))

    def set_selection(self, selected):
        (self.store / "CURRENT.json").write_text(json.dumps(selected))

    def run_proof(self, account="chatgpt4", operation="status", purpose=None):
        argv = [sys.executable, "-I", "-B", "-c", original_subprocess_proof(),
                str(self.rollout), str(self.bundle), self.plan["digest"], account,
                operation]
        if purpose is not None:
            argv.append(purpose)
        return subprocess.run(argv, capture_output=True, timeout=8, check=False)

    def test_reviewed_forward_selection_is_accepted_and_bound_to_pointer(self):
        response = self.run_proof()
        self.assertEqual(response.returncode, 0, response.stderr[-250:])
        proof = json.loads(response.stdout)
        self.assertEqual(proof["phase"], "SELECTED")
        self.assertEqual(proof["selection"], self.forward)
        self.assertEqual(proof["successor_digest"], ORIGINAL_SUCCESSOR)
        self.assertEqual(proof["pool_bridge"], "reviewed-complete-entry")

    def test_same_source_fences_a_change_of_pointer_between_proofs(self):
        first = json.loads(self.run_proof().stdout)
        later = dict(self.forward, generation=RECENT_PREVIOUS, previous=CURRENT_TARGET,
                     sequence=27)
        self.set_selection(later)
        second = json.loads(self.run_proof().stdout)
        self.assertNotEqual(first, second,
                            "lock-bound first/second proof must see a real selection change")

    def test_c4_original_selected_state_retains_exact_old_behavior(self):
        self.set_selection(self.selected)
        result = self.run_proof()
        self.assertEqual(result.returncode, 0, result.stderr[-250:])
        self.assertEqual(json.loads(result.stdout)["selection"], self.selected)

    def test_old_original_preselection_retains_prior_phase(self):
        self.set_selection(self.prior)
        (self.root / "pool").write_bytes(b"PRIOR_BRIDGE")
        result = self.run_proof()
        self.assertEqual(result.returncode, 0, result.stderr[-250:])
        self.assertEqual(json.loads(result.stdout)["phase"], "PREVIOUS")

    def test_eight_public_pins_include_non_paper_personal_but_not_fabric_services(self):
        # The eighth public account has its own completed native pin, not Paper v20.
        self.assertEqual(set(REVIEWED_SEATS) - {"chatgpt2-personal"},
                         set(svc.FLEET_V20_ENROLLED_ACCOUNTS) - {"mastermind-os-publication"})
        self.assertEqual(set(REVIEWED_SEATS),
                         set(svc.NATIVE_POOL_PIN_ACCOUNTS) - {"fabric-design", "fabric-read"})

    def test_all_eight_exact_original_seats_admit_selected_forward_pin(self):
        for account in REVIEWED_SEATS:
            with self.subTest(account=account):
                response = self.run_proof(account)
                self.assertEqual(response.returncode, 0, response.stderr[-250:])
                proof = json.loads(response.stdout)
                self.assertEqual(proof["phase"], "SELECTED")
                self.assertEqual(proof["selection"], self.forward)

    def test_unenrolled_accounts_cannot_use_historical_forward_exception(self):
        for account in UNENROLLED:
            with self.subTest(account=account):
                self.assertNotEqual(self.run_proof(account).returncode, 0)

    def test_newer_sequence_27_remains_admissible_for_all_eight(self):
        newer = dict(self.forward, sequence=27)
        self.set_selection(newer)
        for account in REVIEWED_SEATS:
            with self.subTest(account=account):
                response = self.run_proof(account)
                self.assertEqual(response.returncode, 0, response.stderr[-250:])
                self.assertEqual(json.loads(response.stdout)["selection"], newer)

    def test_wrong_pointer_schema_fails_for_every_seat(self):
        self.set_selection(dict(self.forward, schema="foreign-schema"))
        for account in REVIEWED_SEATS:
            with self.subTest(account=account):
                self.assertNotEqual(self.run_proof(account).returncode, 0)

    def test_wrong_pointer_sequence_type_is_refused(self):
        for bad in (None, "27", True, 27.5):
            with self.subTest(sequence=bad):
                self.set_selection(dict(self.forward, sequence=bad))
                self.assertNotEqual(self.run_proof("admin-business").returncode, 0)

    def test_mismatched_successor_digest_rejects_forward_exception(self):
        self.plan["digest"] = "f" * 64
        self.write_plan()
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_wrong_historical_generation_refuses(self):
        self.plan["target_generation"] = "d" * 64
        self.write_plan()
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_sequence_not_later_than_historical_pin_refuses(self):
        self.set_selection(dict(self.forward, sequence=24))
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_current_generation_missing_from_reviewed_store_refuses(self):
        (self.store / "VERIFIED.json").write_text(
            json.dumps([ORIGINAL_TARGET, RECENT_PREVIOUS])
        )
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_current_previous_generation_unverified_refuses(self):
        (self.store / "VERIFIED.json").write_text(
            json.dumps([ORIGINAL_TARGET, CURRENT_TARGET])
        )
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_current_pointer_self_reference_refuses(self):
        self.set_selection(dict(self.forward, previous=CURRENT_TARGET))
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_changed_original_bridge_refuses(self):
        (self.root / "pool").write_bytes(b"FOREIGN_ENTRY")
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_pruned_original_receipts_never_authorize_native_apply(self):
        # Production isolates the frozen retained-proof helper behind status.
        module = self.rollout / "native_install.py"
        source = module.read_text()
        old = ("def read_successor(bundle):\n"
               " return json.loads((bundle/'PLAN.json').read_text()), {}\n")
        replacement = (
            "def read_successor(bundle):\n"
            " raise FileNotFoundError('historical bootstrap artifact pruned')\n"
            "def read_retained_successor_after_bootstrap_prune(bundle):\n"
            " return json.loads((bundle/'PLAN.json').read_text()), {}\n"
        )
        self.assertEqual(source.count(old), 1)
        module.write_text(source.replace(old, replacement))
        self.assertEqual(self.run_proof("chatgpt2-personal", "status").returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt2-personal", "apply").returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt2-personal", "reconcile").returncode, 0)
        self.assertNotEqual(self.run_proof("fabric-design", "status").returncode, 0)

    def test_closed_formatter_purpose_shares_preview_and_apply_proof(self):
        module = self.rollout / "native_install.py"
        source = module.read_text()
        old = ("def read_successor(bundle):\n"
               " return json.loads((bundle/'PLAN.json').read_text()), {}\n")
        replacement = (
            "def read_successor(bundle):\n"
            " raise FileNotFoundError('historical bootstrap artifact pruned')\n"
            "def read_retained_successor_after_bootstrap_prune(bundle):\n"
            " return json.loads((bundle/'PLAN.json').read_text()), {}\n"
        )
        self.assertEqual(source.count(old), 1)
        module.write_text(source.replace(old, replacement))
        purpose = svc.C1_GATEWAY_RETAINED_PROOF_PURPOSE
        self.assertIn(purpose, original_subprocess_proof())
        preview = self.run_proof("chatgpt1", "preview", purpose)
        apply = self.run_proof("chatgpt1", "apply", purpose)
        self.assertEqual(preview.returncode, 0, preview.stderr[-250:])
        self.assertEqual(apply.returncode, 0, apply.stderr[-250:])
        preview_proof = json.loads(preview.stdout)
        apply_proof = json.loads(apply.stdout)
        self.assertEqual(preview_proof, apply_proof)
        self.assertEqual(preview_proof["phase"], "SELECTED")
        self.assertEqual(preview_proof["selection"], self.forward)
        self.assertNotEqual(self.run_proof("chatgpt1", "apply").returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt1", "reconcile", purpose).returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt1", "status", purpose).returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt4", "apply", purpose).returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt1", "apply", "foreign-purpose").returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt1", "preview", "foreign-purpose").returncode, 0)
        self.set_selection(dict(self.forward, previous=CURRENT_TARGET))
        self.assertNotEqual(self.run_proof("chatgpt1", "preview", purpose).returncode, 0)
        self.assertNotEqual(self.run_proof("chatgpt1", "apply", purpose).returncode, 0)

    def test_no_extra_native_or_installer_files_created(self):
        original = sorted(x.relative_to(self.root) for x in self.root.rglob("*")
                          if x.is_file() and not x.name.endswith(".pyc"))
        result = self.run_proof()
        self.assertEqual(result.returncode, 0, result.stderr[-250:])
        after = sorted(x.relative_to(self.root) for x in self.root.rglob("*")
                       if x.is_file() and not x.name.endswith(".pyc"))
        self.assertEqual(original, after)


if __name__ == "__main__":
    unittest.main()
