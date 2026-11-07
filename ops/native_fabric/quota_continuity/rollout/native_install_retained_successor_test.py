"""Hermetic positive/negative proof of the one frozen historical bootstrap-prune status route.

No private host files, native selections, services, credentials or Git effects.
The original strict read_successor() implementation is deliberately unchanged.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import native_install as native


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return native.generation.canonical(value)


class RetainedNativeStatusProofTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.store = self.mkdir("store")
        self.receipts = self.mkdir("store/bootstrap")
        self.mkdir("store/launchers")
        self.bundle = self.mkdir("successor")
        self.prior = self.mkdir("prior")
        original_parent = self.mkdir("pruned-source")
        self.original = original_parent / "bootstrap"  # deliberately absent
        self.bootstrap_digest = "9" * 64
        self.initial = "1" * 64
        self.prior_old = "2" * 64
        self.prior_target = "3" * 64
        self.successor_old = "4" * 64
        self.successor_target = "5" * 64
        self.to_launcher = digest(b"sealed successor launcher")
        self.from_launcher = digest(b"sealed prior launcher")
        self.new = self.pointer(self.successor_target, self.successor_old, 24)
        self.old = self.pointer(self.successor_old, "8" * 64, 23)
        self.prior_previous = self.pointer(self.prior_old, "7" * 64, 16)
        self.prior_selected = self.pointer(self.prior_target, self.prior_old, 17)
        self.write("pool", b"pool bridge", 0o755)
        self.write("task", b"task bridge", 0o755)
        self.write("remote", b"original remote", 0o755)
        self.write("store/launchers/" + self.to_launcher + ".py",
                   b"sealed successor launcher", 0o555)

        self.predecessor = {
            "schema": native.UPGRADE_SCHEMA,
            "original_bundle": str(self.original),
            "bootstrap_digest": self.bootstrap_digest,
            "store": str(self.store),
            "expected_selection": self.prior_previous,
            "target_generation": self.prior_target,
            "from_launcher": digest(b"earlier launcher"),
            "to_launcher": self.from_launcher,
            "manifest_sha256": "a" * 64,
            "entries": {},
        }
        self.predecessor["digest"] = digest(canonical(self.predecessor))
        self.plan = {
            "schema": native.SUCCESSOR_SCHEMA,
            "prior_upgrade_bundle": str(self.prior),
            "prior_upgrade_digest": self.predecessor["digest"],
            "bootstrap_digest": self.bootstrap_digest,
            "store": str(self.store),
            "expected_selection": self.old,
            "target_generation": self.successor_target,
            "from_launcher": self.from_launcher,
            "to_launcher": self.to_launcher,
            "manifest_sha256": "b" * 64,
            "entries": {
                "pool": {"target": str(self.root / "pool"), "mode": 0o755,
                         "previous": "c" * 64, "bridge": digest(b"pool bridge")},
                "task": {"target": str(self.root / "task"), "mode": 0o755,
                         "previous": "d" * 64, "bridge": digest(b"task bridge")},
                "remote": {"target": str(self.root / "remote"), "mode": 0o755,
                           "previous": digest(b"original remote")},
            },
        }
        self.plan["digest"] = digest(canonical(self.plan))
        self.files = {
            "prior": {
                "PLAN.json": canonical(self.predecessor),
                "native_generation.py": b"sealed prior launcher",
                "pool.bridge": b"prior pool bridge",
                "task.bridge": b"prior task bridge",
            },
            "successor": {
                "PLAN.json": canonical(self.plan),
                "native_generation.py": b"sealed successor launcher",
                "pool.bridge": b"pool bridge",
                "task.bridge": b"task bridge",
            },
        }
        self.receipt_files = {
            ".launcher-successor-v1.json": {
                "schema": native.SUCCESSOR_SCHEMA,
                "plan_digest": self.plan["digest"],
                "prior_upgrade_digest": self.predecessor["digest"],
                "bootstrap_digest": self.bootstrap_digest,
            },
            ".paired-launcher-upgrade.json": {
                "schema": native.UPGRADE_SCHEMA,
                "plan_digest": self.predecessor["digest"],
                "bootstrap_digest": self.bootstrap_digest,
            },
            self.plan["digest"] + ".successor.json": {
                "schema": native.SUCCESSOR_SCHEMA,
                "plan_digest": self.plan["digest"],
                "prior_upgrade_digest": self.predecessor["digest"],
                "bootstrap_digest": self.bootstrap_digest,
                "previous_selection": self.old,
                "selection": self.new,
            },
            self.predecessor["digest"] + ".upgrade.json": {
                "schema": native.UPGRADE_SCHEMA,
                "plan_digest": self.predecessor["digest"],
                "bootstrap_digest": self.bootstrap_digest,
                "previous_selection": self.prior_previous,
                "selection": self.prior_selected,
            },
            self.bootstrap_digest + ".phase1.json": {
                "schema": native.SCHEMA,
                "phase": 1,
                "plan_digest": self.bootstrap_digest,
                "initial_generation": self.initial,
            },
        }
        for key, files in self.files.items():
            for name, data in files.items():
                self.write(key + "/" + name, data)
        for name, value in self.receipt_files.items():
            self.write("store/bootstrap/" + name, canonical(value))
        pins = {
            **{category: {name: digest(raw) for name, raw in files.items()}
               for category, files in self.files.items()},
            "receipts": {name: digest(canonical(value))
                         for name, value in self.receipt_files.items()},
        }
        self.expected_generations = {
            self.initial, self.prior_old, self.prior_target,
            self.successor_old, self.successor_target,
        }
        self.patch = mock.patch.object(native, "RETAINED_STATUS_PROOF_SHA256", pins)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.patch_digest = mock.patch.object(
            native, "RETAINED_STATUS_PLAN_DIGEST", self.plan["digest"])
        self.patch_digest.start()
        self.addCleanup(self.patch_digest.stop)
        self.verified = []
        def verify(store, identity):
            self.assertEqual(store, self.store)
            if identity not in self.expected_generations:
                raise ValueError("unverified native generation")
            self.verified.append(identity)
            return self.store / identity, {"files": {"safe": "true"}}
        self.verify_patch = mock.patch.object(native.generation, "verify",
                                              side_effect=verify)
        self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)

    def mkdir(self, relative):
        path = self.root / relative
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
        return path

    def write(self, relative, raw, mode=0o600):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(mode)
        return path

    def pointer(self, generation, previous, sequence):
        return {"schema": native.generation.POINTER_SCHEMA,
                "generation": generation, "previous": previous,
                "sequence": sequence}

    def status(self):
        return native.read_retained_successor_after_bootstrap_prune(self.bundle)

    def snapshot(self):
        return {str(p.relative_to(self.root)): digest(p.read_bytes())
                for p in self.root.rglob("*") if p.is_file()}

    def test_exact_retained_receipts_admit_read_only_status_without_effect(self):
        before = self.snapshot()
        plan, payloads = self.status()
        self.assertEqual(plan, self.plan)
        self.assertEqual(payloads["pool.bridge"], b"pool bridge")
        self.assertEqual(set(self.verified), self.expected_generations)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.original.exists())

    def test_any_retained_receipt_mutation_refuses(self):
        for filename in self.receipt_files:
            with self.subTest(filename=filename):
                path = self.receipts / filename
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" ")
                    with self.assertRaises(ValueError):
                        self.status()
                finally:
                    path.write_bytes(original)

    def test_any_successor_or_predecessor_artifact_mutation_refuses(self):
        for category, files in self.files.items():
            for filename in files:
                with self.subTest(category=category, filename=filename):
                    path = self.root / category / filename
                    original = path.read_bytes()
                    try:
                        path.write_bytes(original + b" ")
                        with self.assertRaises(ValueError):
                            self.status()
                    finally:
                        path.write_bytes(original)

    def test_absent_or_unreviewed_receipt_refuses(self):
        p = self.receipts / (self.bootstrap_digest + ".phase1.json")
        p.rename(self.receipts / "held.phase1")
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.status()

    def test_restored_bootstrap_requires_original_full_verifier(self):
        self.original.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "strict original"):
            self.status()

    def test_additional_unapproved_bundle_file_refuses(self):
        self.write("successor/foreign.bin", b"payload")
        with self.assertRaisesRegex(ValueError, "artifact set changed"):
            self.status()

    def test_native_ingress_byte_drift_refuses(self):
        self.write("pool", b"new pool bridge", 0o755)
        with self.assertRaises(ValueError):
            self.status()

    def test_native_generation_absence_refuses(self):
        self.expected_generations.remove(self.initial)
        with self.assertRaisesRegex(ValueError, "unverified native generation"):
            self.status()

    def test_legacy_epoch_rollback_receipt_refuses(self):
        self.write("store/bootstrap/" + self.bootstrap_digest + ".rollback.json",
                   b"previously rolled back")
        with self.assertRaisesRegex(ValueError, "historical epoch changed"):
            self.status()

    def test_symlinked_source_artifact_refuses(self):
        p = self.bundle / "task.bridge"
        p.unlink()
        p.symlink_to(self.root / "task")
        with self.assertRaises(ValueError):
            self.status()

    def test_partial_bootstrap_pruning_does_not_rebuild_artifact(self):
        self.assertFalse(self.original.exists())
        self.status()
        self.assertFalse(self.original.exists())

    def test_strict_native_apply_does_not_use_the_retained_reader(self):
        before = self.snapshot()
        with self.assertRaises(FileNotFoundError):
            native.apply_successor(self.bundle)
        self.assertFalse(self.original.exists())
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
