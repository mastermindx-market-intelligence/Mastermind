"""Fixed Library ACL exception: fixture wiring plus real Darwin descriptor ACLs.

Only disposable owned fixture trees are changed. UID/pwd rebinding follows the
existing home tests; native tests retain the real descriptor ACL functions.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_os_gateway_studio_home_acl as fx

reader = fx.reader


class LibraryAclWiringTests(fx.HomeAclReaderTestCase):
    def binding(self, *records):
        return fx.PwdFixture(*(records or (fx.pwd_record(str(self.fx.home), fx.CURRENT_UID, fx.CURRENT_GID),)))

    def observe_with(self, paths, *, classifier=None, pwd=None):
        calls = []
        with fx.reader_overrides(
            pwd_fixture=pwd or self.binding(),
            acl_presence=fx.acl_presence_for({self.fx.inode(p) for p in paths}),
            classifier=classifier or fx.permissive_classifier(calls),
        ):
            result = self.fx.observe()
        return result, calls

    def test_library_0700_uses_descriptor_classifier(self):
        library = self.fx.home / 'Library'
        library.chmod(0o700)
        result, calls = self.observe_with([library])
        self.assertTrue(result.node_sha256)
        self.assertIn(self.fx.inode(library), calls)

    def test_home_and_library_can_both_qualify(self):
        library = self.fx.home / 'Library'
        _, calls = self.observe_with([self.fx.home, library])
        self.assertIn(self.fx.inode(library), calls)
        self.assertIn(self.fx.inode(self.fx.home), calls)

    def test_classifier_rejection_precedes_all_payload(self):
        counts = {}
        with fx.counted_reads(counts):
            self.assertRefused(self.observe_with, [self.fx.home / 'Library'],
                               classifier=fx.refusing_classifier([]))
        self.assertEqual(counts, {})

    def test_other_locations_remain_forbidden(self):
        for path in (self.fx.home / 'Library' / 'LaunchAgents', self.fx.home / '.local',
                     self.fx.base / 'manifest.json', self.fx.tools):
            with self.subTest(path=path):
                counts = {}
                with fx.counted_reads(counts):
                    self.assertRefused(self.observe_with, [path])
                # Library/LaunchAgents and .local are checked before any byte IO.
                if path in (self.fx.home / 'Library' / 'LaunchAgents', self.fx.home / '.local'):
                    self.assertEqual(counts, {})
                self.assertNotIn(self.fx.inode(path), counts)

    def test_pwd_mismatch_and_drift_refuse_before_payload(self):
        good = fx.pwd_record(str(self.fx.home), fx.CURRENT_UID, fx.CURRENT_GID)
        wrong = fx.pwd_record(str(self.fx.home / 'other'), fx.CURRENT_UID, fx.CURRENT_GID)
        wrong_uid = fx.pwd_record(str(self.fx.home), fx.CURRENT_UID + 1, fx.CURRENT_GID)
        wrong_gid = fx.pwd_record(str(self.fx.home), fx.CURRENT_UID, fx.CURRENT_GID + 1)
        for records in ((wrong,), (wrong_uid,), (wrong_gid,), (good, wrong)):
            with self.subTest(records=records):
                counts = {}
                with fx.counted_reads(counts):
                    self.assertRefused(self.observe_with, [self.fx.home / 'Library'], pwd=self.binding(*records))
                self.assertEqual(counts, {})

    def test_library_search_permission_is_required(self):
        library = self.fx.home / 'Library'
        library.chmod(0o400)
        try:
            self.assertRefused(self.observe_with, [library])
        finally:
            library.chmod(0o700)

    def test_library_wrong_uid_or_gid_refuses_before_payload(self):
        library = self.fx.home / 'Library'
        inode = self.fx.inode(library)
        actual_stat = os.stat
        for changes in ({'st_uid': fx.CURRENT_UID + 1}, {'st_gid': fx.CURRENT_GID + 1}):
            def named_stat(*args, **kwargs):
                info = actual_stat(*args, **kwargs)
                return fx._mutate_stat(info, **changes) if info.st_ino == inode else info
            with self.subTest(changes=changes), mock.patch.object(reader.os, 'stat', side_effect=named_stat):
                counts = {}
                with fx.counted_reads(counts):
                    self.assertRefused(self.observe_with, [library])
                self.assertEqual(counts, {})

    def test_library_symlink_refuses(self):
        library = self.fx.home / 'Library'
        moved = self.fx.home / 'original-library'
        library.rename(moved)
        library.symlink_to(moved, target_is_directory=True)
        self.assertRefused(self.observe_with, [moved])
        library.unlink()
        moved.rename(library)

    def test_library_swap_during_classifier_reads_no_foreign_bytes(self):
        library = self.fx.home / 'Library'
        replacement = self.fx.home / 'replacement'
        replacement.mkdir()
        (replacement / 'sentinel').write_bytes(b'foreign-fixture-payload')
        counts = {}
        swapped = False
        def classify(*, descriptor, expected_identity):
            nonlocal swapped
            if not swapped:
                swapped = True
                library.rename(self.fx.home / 'held-library')
                replacement.rename(library)
            return True
        with fx.counted_reads(counts):
            self.assertRefused(self.observe_with, [library], classifier=classify)
        self.assertTrue(swapped)
        self.assertEqual(counts, {})


@unittest.skipUnless(fx.IS_DARWIN, 'real descriptor ACL qualification is Darwin-only')
class LibraryAclNativeTests(fx.HomeAclReaderTestCase):
    def add_acl(self, path, entry):
        subprocess.run(['/bin/chmod', '+a', entry, str(path)], check=True, capture_output=True)

    def observe_native(self):
        with fx.reader_overrides(pwd_fixture=fx.PwdFixture(
                fx.pwd_record(str(self.fx.home), fx.CURRENT_UID, fx.CURRENT_GID))):
            return self.fx.observe()

    def test_native_library_0700_exact_acl_accepts(self):
        library = self.fx.home / 'Library'
        library.chmod(0o700)
        self.add_acl(library, 'everyone deny delete')
        self.assertTrue(self.observe_native().node_sha256)

    def test_native_home_and_library_exact_acl_accept(self):
        self.add_acl(self.fx.home, 'everyone deny delete')
        self.add_acl(self.fx.home / 'Library', 'everyone deny delete')
        self.assertTrue(self.observe_native().node_sha256)

    def test_native_extra_entry_refuses_before_payload(self):
        library = self.fx.home / 'Library'
        self.add_acl(library, 'everyone deny delete')
        self.add_acl(library, 'everyone allow read')
        counts = {}
        with fx.counted_reads(counts):
            self.assertRefused(self.observe_native)
        self.assertEqual(counts, {})

    def test_native_allow_extra_permission_other_principal_refuse(self):
        library = self.fx.home / 'Library'
        for entry in ('everyone allow delete', 'everyone deny delete,writeattr',
                      'group:wheel deny delete'):
            with self.subTest(entry=entry):
                self.add_acl(library, entry)
                counts = {}
                with fx.counted_reads(counts):
                    self.assertRefused(self.observe_native)
                self.assertEqual(counts, {})
                subprocess.run(['/bin/chmod', '-N', str(library)], check=True, capture_output=True)

    def test_native_inherited_entry_refuses_before_payload(self):
        library = self.fx.home / 'Library'
        fx.cleanup_owned_fixture(library)
        self.add_acl(self.fx.home, 'everyone deny delete,file_inherit,directory_inherit')
        library.mkdir(mode=0o700)
        launch = library / 'LaunchAgents'
        launch.mkdir()
        (launch / fx.PLIST_NAME).write_bytes(b'<plist/>')
        subprocess.run(['/bin/chmod', '-N', str(self.fx.home)], check=True, capture_output=True)
        counts = {}
        with fx.counted_reads(counts):
            self.assertRefused(self.observe_native)
        self.assertEqual(counts, {})

    def test_native_launchagents_acl_still_refuses(self):
        self.add_acl(self.fx.home / 'Library', 'everyone deny delete')
        self.add_acl(self.fx.home / 'Library' / 'LaunchAgents', 'everyone deny delete')
        counts = {}
        with fx.counted_reads(counts):
            self.assertRefused(self.observe_native)
        self.assertEqual(counts, {})


if __name__ == '__main__':
    unittest.main()
