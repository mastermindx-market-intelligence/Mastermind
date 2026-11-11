"""Real combined publisher regression proof; no live runtime or provider calls."""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

EXT = Path(sys.argv.pop(1)).resolve() / "native-code-stage/ext"
sys.path.insert(0, str(EXT))
import support_bundle as support
import fabric_policy_snapshot as policy

VALID = json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {}}}}}).encode() + b"\n"

class BootstrapPublication(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root / "controller/ext"
        self.source.mkdir(parents=True)
        self.stable = self.root / "remote/ext"
        self.stable.mkdir(parents=True)
        self.active = self.stable / "active"
        self.active.mkdir()
        self.lock = self.active / ".admission.lock"
        self.lock.touch(mode=0o600)
        self.lock_inode = self.lock.stat().st_ino
        self.releases = self.stable.parent / "support-releases"
        self.releases.mkdir()
        self.target = self.stable.parent / "orch/fabric/pools.yaml"
        self.target.parent.mkdir(parents=True)
        for name in support.SOURCE_FILES:
            if name == "pools.yaml":
                (self.source / name).write_bytes(VALID)
            else:
                shutil.copyfile(EXT / name, self.source / name)

    def manifest(self):
        return {name: hashlib.sha256((self.source / name).read_bytes()).hexdigest()
                for name in support.SOURCE_FILES}

    def publish(self):
        return support.publish(self.source, self.stable, self.manifest())

    def assert_unpublished(self):
        self.assertFalse(os.path.lexists(self.target))
        self.assertEqual(list(self.releases.iterdir()), [])
        self.assertEqual(self.lock.stat().st_ino, self.lock_inode)
        self.assertEqual(list(self.target.parent.glob(".pools-policy-*")), [])

    def test_missing_policy_initializes_and_reuses_complete_release(self):
        published = self.publish()
        self.assertEqual(self.target.read_bytes(), VALID)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertEqual(self.lock.stat().st_ino, self.lock_inode)
        self.assertEqual(self.publish(), published)
        self.assertEqual(json.loads((published.parent / "RELEASE.json").read_text())["files"], self.manifest())
        self.assertEqual((published / "active").resolve(), self.active.resolve())

    def test_invalid_policy_is_refused_before_initialization(self):
        for raw in (b"routing: {}\nrouting: {}\npools: {}\n", b"[]\n", b"routing: {}\npools: {}\n"):
            with self.subTest(raw=raw):
                (self.source / "pools.yaml").write_bytes(raw)
                with self.assertRaises(ValueError):
                    self.publish()
                self.assert_unpublished()

    def test_live_or_unknown_active_entry_is_preserved_and_blocks(self):
        marker = self.active / "original-worker.json"
        raw = b'{"state":"EFFECT_UNKNOWN"}\n'
        marker.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "SUPPORT_POLICY_STALE_ACTIVE_REFUSED"):
            self.publish()
        self.assertEqual(marker.read_bytes(), raw)
        self.assert_unpublished()

    def test_policy_appearing_under_lock_is_preserved(self):
        original = support._acquire_policy_lock
        concurrent = VALID + b" \n"
        def acquire(fd):
            original(fd)
            self.target.write_bytes(concurrent)
        with mock.patch.object(support, "_acquire_policy_lock", side_effect=acquire):
            with self.assertRaisesRegex(ValueError, "SUPPORT_POLICY_APPEARED"):
                self.publish()
        self.assertEqual(self.target.read_bytes(), concurrent)
        self.assertEqual(list(self.releases.iterdir()), [])
        self.assertEqual(self.lock.stat().st_ino, self.lock_inode)

    def test_policy_appearing_at_publication_is_not_overwritten(self):
        original = support.os.link
        concurrent = VALID + b"\n"
        def link(source, target, **kwargs):
            self.assertEqual(Path(target), self.target)
            self.target.write_bytes(concurrent)
            return original(source, target, **kwargs)
        with mock.patch.object(support.os, "link", side_effect=link):
            with self.assertRaisesRegex(ValueError, "SUPPORT_POLICY_APPEARED"):
                self.publish()
        self.assertEqual(self.target.read_bytes(), concurrent)
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertEqual(list(self.target.parent.glob(".pools-policy-*")), [])
        self.assertEqual(list(self.releases.iterdir()), [])

    def test_missing_source_is_not_bootstrapped(self):
        manifest = self.manifest()
        (self.source / "pools.yaml").unlink()
        with self.assertRaisesRegex(ValueError, "unavailable publication path"):
            support.publish(self.source, self.stable, manifest)
        self.assert_unpublished()

    def test_missing_policy_parent_is_not_created(self):
        self.target.parent.rmdir()
        with self.assertRaisesRegex(ValueError, "unavailable publication path"):
            self.publish()
        self.assertFalse(self.target.parent.exists())
        self.assertEqual(list(self.releases.iterdir()), [])
        self.assertEqual(self.lock.stat().st_ino, self.lock_inode)

    def test_target_symlink_is_refused_without_touching_referent(self):
        outside = self.root / "outside-policy.yaml"
        outside.write_bytes(VALID)
        self.target.symlink_to(outside)
        with self.assertRaises(OSError):
            self.publish()
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(outside.read_bytes(), VALID)
        self.assertEqual(list(self.releases.iterdir()), [])

    def test_target_directory_is_refused(self):
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError, "ROUTING_POLICY_FILE_INVALID"):
            self.publish()
        self.assertTrue(self.target.is_dir())
        self.assertEqual(list(self.releases.iterdir()), [])

    def test_missing_other_path_does_not_enter_bootstrap(self):
        error = FileNotFoundError(errno.ENOENT, "missing", str(self.active / "different-path"))
        with mock.patch.object(policy, "validate_publication", side_effect=error):
            with mock.patch.object(support, "ensure_policy", wraps=support.ensure_policy) as ensure:
                with self.assertRaises(FileNotFoundError):
                    self.publish()
                ensure.assert_not_called()
        self.assert_unpublished()

    def test_permission_error_does_not_enter_bootstrap(self):
        original = policy.bounded_file
        def read(path):
            if Path(path) == self.target:
                raise PermissionError(errno.EACCES, "denied", str(path))
            return original(path)
        with mock.patch.object(policy, "bounded_file", side_effect=read):
            with mock.patch.object(support, "ensure_policy", wraps=support.ensure_policy) as ensure:
                with self.assertRaises(PermissionError):
                    self.publish()
                ensure.assert_not_called()
        self.assert_unpublished()

    def test_original_admission_lock_busy_refuses(self):
        with self.lock.open("r+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with self.assertRaisesRegex(ValueError, "ROUTING_ADMISSION_LOCK_BUSY"):
                    self.publish()
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        self.assert_unpublished()

    def test_absence_and_maintenance_modes_cannot_be_combined(self):
        for kwargs in ({"expected_current_hash": "0" * 64}, {"rollback_source": self.root / "rollback"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, "SUPPORT_POLICY_ABSENCE_MODE_CONFLICT"):
                    support.ensure_policy(self.source / "pools.yaml", self.stable,
                        hashlib.sha256(VALID).hexdigest(), require_absent=True, **kwargs)
                self.assert_unpublished()

    def test_hash_mismatch_cannot_initialize(self):
        with self.assertRaisesRegex(ValueError, "SUPPORT_POLICY_HASH_MISMATCH"):
            support.ensure_policy(self.source / "pools.yaml", self.stable,
                                  "0" * 64, require_absent=True)
        self.assert_unpublished()

    def test_legacy_three_argument_owner_remains_unchanged(self):
        self.target.write_bytes(b"old: 1\n")
        data = b"new: 2\n"
        (self.source / "pools.yaml").write_bytes(data)
        result = support.ensure_policy(self.source / "pools.yaml", self.stable,
                                       hashlib.sha256(data).hexdigest())
        self.assertEqual(result, "POLICY_REFRESHED_IDLE")
        self.assertEqual(self.target.read_bytes(), data)

    def test_existing_compatible_policy_is_preserved(self):
        data = json.dumps({"routing": {}, "pools": {"grok": {"windows": {"weekly": {"remaining_pct": 37}}}}}).encode()
        self.target.write_bytes(data)
        inode = self.target.stat().st_ino
        self.publish()
        self.assertEqual(self.target.read_bytes(), data)
        self.assertEqual(self.target.stat().st_ino, inode)

if __name__ == "__main__":
    unittest.main(verbosity=2)
