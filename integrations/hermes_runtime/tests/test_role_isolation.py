"""Synthetic-only OS identity, ownership and pre-credential isolation tests."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import stat
import tempfile
import unittest
from unittest import mock

from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime import role_isolation as iso
from integrations.hermes_runtime.errors import RuntimeRefusal


class RoleIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hermes-isolation-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.users = {
            role: SimpleNamespace(pw_name=role, pw_uid=uid, pw_gid=uid)
            for role, uid in (("mmsecretary", 60001), ("mmmeta", 60002))
        }
        self.groups = {
            role: SimpleNamespace(gr_name=role, gr_gid=value.pw_gid)
            for role, value in self.users.items()
        }

    def profile(self, role="mmsecretary"):
        return compose_profile(role, state_dir=self.root / role / "state",
                               secrets_file=self.root / role / "private" / "role.env")

    def run_guard(self, role="mmsecretary", *, uid=None, groups=None, mode=0o600, links=1):
        own = self.users[role]
        actual = own.pw_uid if uid is None else uid
        item = SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=own.pw_uid,
                               st_gid=own.pw_gid, st_nlink=links)
        profile = self.profile(role)
        with (
            mock.patch.object(iso.pwd, "getpwnam", side_effect=self.users.__getitem__),
            mock.patch.object(iso.grp, "getgrnam", side_effect=self.groups.__getitem__),
            mock.patch.object(iso.os, "getuid", return_value=actual),
            mock.patch.object(iso.os, "geteuid", return_value=actual),
            mock.patch.object(iso.os, "getgid", return_value=own.pw_gid),
            mock.patch.object(iso.os, "getegid", return_value=own.pw_gid),
            mock.patch.object(iso.os, "getgroups", return_value=[own.pw_gid] if groups is None else groups),
            mock.patch.object(iso, "_private_directory") as private,
            mock.patch.object(Path, "lstat", return_value=item),
        ):
            iso.assert_role_credential_isolation(profile)
        self.assertEqual(private.call_count, 2)

    def test_both_distinct_role_identities(self):
        self.run_guard("mmsecretary")
        self.run_guard("mmmeta")

    def test_shared_operator_name_refused(self):
        for role in iso.ROLE_ACCOUNTS:
            with self.assertRaisesRegex(RuntimeRefusal, "ROOT_UNIT_ROLE_ACCOUNT_REQUIRED"):
                iso.assert_service_account_names(role, "longr", "longr")
            iso.assert_service_account_names(role, role, role)

    def test_cross_role_account_refused(self):
        with self.assertRaises(RuntimeRefusal):
            iso.assert_service_account_names("mmsecretary", "mmmeta", "mmmeta")

    def test_different_names_with_same_numeric_uid_refused(self):
        self.users["mmmeta"].pw_uid = 60001
        with self.assertRaisesRegex(RuntimeRefusal, "ROLE_OS_IDENTITY_COLLISION"):
            self.run_guard()

    def test_different_names_with_same_numeric_gid_refused(self):
        self.users["mmmeta"].pw_gid = 60001
        self.groups["mmmeta"].gr_gid = 60001
        with self.assertRaisesRegex(RuntimeRefusal, "ROLE_OS_IDENTITY_COLLISION"):
            self.run_guard()

    def test_nss_role_missing_refused(self):
        del self.users["mmmeta"]
        with self.assertRaisesRegex(RuntimeRefusal, "ROLE_OS_ACCOUNT_UNAVAILABLE"):
            self.run_guard()

    def test_root_uid_refused(self):
        self.users["mmmeta"].pw_uid = 0
        with self.assertRaisesRegex(RuntimeRefusal, "ROLE_OS_ACCOUNT_UNQUALIFIED"):
            self.run_guard()

    def test_process_uid_mismatch_refused(self):
        with self.assertRaisesRegex(RuntimeRefusal, "ROLE_OS_PROCESS_IDENTITY_MISMATCH"):
            self.run_guard(uid=500)

    def test_supplementary_shared_group_refused(self):
        with self.assertRaisesRegex(RuntimeRefusal, "ROLE_OS_PROCESS_IDENTITY_MISMATCH"):
            self.run_guard(groups=[60001, 60002])

    def test_loose_secret_mode_or_hardlink_refused(self):
        for kw in ({"mode": 0o644}, {"mode": 0o700}, {"links": 2}):
            with self.subTest(kw=kw), self.assertRaisesRegex(RuntimeRefusal, "ROLE_PRIVATE_SECRET_UNQUALIFIED"):
                self.run_guard(**kw)

    def test_private_directory_mode_owner_and_ancestors(self):
        path = Path("/srv/mmsecretary/private")
        good = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=60001, st_gid=60001)
        parent = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_gid=0)
        with mock.patch.object(Path, "resolve", return_value=path), \
                mock.patch.object(Path, "lstat", side_effect=[good, parent, parent, parent]):
            iso._private_directory(path, 60001, 60001)
        for field, value in (("st_mode", stat.S_IFDIR | 0o755), ("st_uid", 60002), ("st_gid", 60002)):
            bad = SimpleNamespace(**vars(good))
            setattr(bad, field, value)
            with mock.patch.object(Path, "resolve", return_value=path), \
                    mock.patch.object(Path, "lstat", return_value=bad), \
                    self.assertRaisesRegex(RuntimeRefusal, "ROLE_PRIVATE_DIRECTORY_UNQUALIFIED"):
                iso._private_directory(path, 60001, 60001)

    def test_writable_or_foreign_ancestor_refused(self):
        path = Path("/srv/mmsecretary/private")
        good = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=60001, st_gid=60001)
        for mode, uid in ((0o777, 0), (0o755, 60002)):
            parent = SimpleNamespace(st_mode=stat.S_IFDIR | mode, st_uid=uid, st_gid=0)
            with mock.patch.object(Path, "resolve", return_value=path), \
                    mock.patch.object(Path, "lstat", side_effect=[good, parent]), \
                    self.assertRaisesRegex(RuntimeRefusal, "ROLE_PRIVATE_ANCESTOR_UNQUALIFIED"):
                iso._private_directory(path, 60001, 60001)

    def test_symlink_directory_refused(self):
        path = Path("/srv/mmsecretary/private")
        item = SimpleNamespace(st_mode=stat.S_IFLNK | 0o700, st_uid=60001, st_gid=60001)
        with mock.patch.object(Path, "resolve", return_value=Path("/elsewhere")), \
                mock.patch.object(Path, "lstat", return_value=item), self.assertRaises(RuntimeRefusal):
            iso._private_directory(path, 60001, 60001)


if __name__ == "__main__":
    unittest.main()
