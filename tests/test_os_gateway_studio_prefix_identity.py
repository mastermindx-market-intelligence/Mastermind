"""Finite prefix guard tests: owned inert fixtures only, no host observation.

Mechanical queue tests inject only the private kernel boundary. Native tests
retain the real Darwin queue/FD/ACL functions; pwd/UID fixture rebinding is
explicit and never evidence of actual host qualification or3354 causality.
"""
from __future__ import annotations
import contextlib
import os
from pathlib import Path
import select
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from ops.executive_os import os_gateway_studio_reader as reader


class MechanicalPrefixGuard:
    """Existing synthetic-filesystem suites: NOT kernel-event qualification."""
    def __init__(self): self._held = {}
    def watch(self, path, fd, expected): self._held.setdefault(path, (None, expected))
    def check(self): pass
    def close(self): self._held.clear()


class QueueFixture:
    def __init__(self, directory):
        self.fd = os.open(directory, reader._DIR_FLAGS)
        self.events = []
        self.error = False
        self.register = None
        self.registrations = []
    def fileno(self): return self.fd
    def control(self, changes, count, timeout):
        if self.error: raise OSError('inert queue failure')
        if changes:
            self.registrations.extend(changes)
            if self.register: self.register(changes)
        result, self.events = self.events[:count], self.events[count:]
        return result
    def close(self):
        if self.fd >= 0: os.close(self.fd); self.fd = -1


class PrefixGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prefix-guard-', dir=Path(__file__).resolve().parents[1])
        self.root = Path(self.temp.name)
        self.prefix = self.root/'prefix'; self.prefix.mkdir(mode=0o700)
        self.protected = self.prefix/'protected'; self.protected.mkdir(mode=0o700)
        self.leaf = self.protected/'leaf'; self.leaf.write_bytes(b'INERT'); self.leaf.chmod(0o600)
        (self.root/'new').mkdir(mode=0o700)
        self.queue = QueueFixture(self.root)
        self.stack = contextlib.ExitStack()
        constants = dict(KQ_NOTE_RENAME=32,KQ_NOTE_DELETE=1,KQ_NOTE_REVOKE=64,
                         KQ_NOTE_ATTRIB=8,KQ_FILTER_VNODE=-4,KQ_EV_ADD=1,KQ_EV_CLEAR=32)
        self.stack.enter_context(mock.patch.multiple(select, create=True, **constants))
        self.stack.enter_context(mock.patch.object(select,'kevent',create=True,
            side_effect=lambda ident,**kw:SimpleNamespace(ident=ident,**kw)))
        self.stack.enter_context(mock.patch.object(select,'kqueue',create=True,return_value=self.queue))
        self.walk = reader._Walk(None,lambda:None,frozenset({(),('prefix',)}),frozenset({('prefix','protected')}))
        self.fd = self.walk.adopt(os.open(self.root,reader._DIR_FLAGS))
        self.walk._root_fd=self.fd; self.walk._root_info=os.fstat(self.fd); self.walk._paths[self.fd]=()
        self.walk._watch_directory((),self.fd,self.walk._root_info)
        policy=reader._make_owned_dir_policy(os.getuid(),os.getgid(),enumerated=False)
        self.prefix_fd,self.prefix_stat=self.walk.open_child(self.fd,'prefix',directory=True,policy=policy)
        self.child_fd,self.child_stat=self.walk.open_child(self.prefix_fd,'protected',directory=True,policy=policy)
    def tearDown(self):
        try:
            self.queue.events=[]; self.queue.error=False
            with contextlib.suppress(reader.StudioObservationError): self.walk.close_all()
        finally: self.stack.close(); self.temp.cleanup()
    def churn(self,path):
        p=path/'unrelated';p.write_bytes(b'OWNED');p.unlink()
    def test_benign_prefix_timestamps_preserve_original_baseline(self):
        old=self.walk._records[('prefix',)][0];self.churn(self.prefix)
        self.assertNotEqual(old.st_ctime_ns,self.prefix.stat().st_ctime_ns)
        self.walk.recheck_all();self.assertEqual(self.walk._records[('prefix',)][0],old)
    def test_only_four_hazards_subscribed(self):
        self.assertTrue(self.queue.registrations)
        self.assertTrue(all(x.fflags==105 for x in self.queue.registrations))
    def test_unknown_or_overflow_event_refuses(self):
        for event in (object(),SimpleNamespace(flags=16384),SimpleNamespace(fflags=0)):
            self.queue.events=[event]
            with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
    def test_queue_drain_error_refuses(self):
        self.queue.error=True
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
    def test_closed_queue_refuses(self):
        self.queue.close()
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
    def test_closed_watch_duplicate_refuses(self):
        fd,_=self.walk._prefix_guard._held[('prefix',)];os.close(fd)
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
        self.walk._prefix_guard._held.pop(('prefix',))
    def test_ordinary_close_retains_watch_until_disposal(self):
        owned,_=self.walk._prefix_guard._held[('prefix',)]
        self.walk.close(self.child_fd);self.walk.close(self.prefix_fd)
        os.fstat(owned);self.queue.events=[object()]
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
    def test_all_duplicates_closed_at_success(self):
        held=[x[0] for x in self.walk._prefix_guard._held.values()]
        self.walk.close_all()
        for fd in held:
            with self.assertRaises(OSError):os.fstat(fd)
    def test_registration_race_is_not_adopted(self):
        p=self.root/'new';fd=self.walk.adopt(os.open(p,reader._DIR_FLAGS));pre=os.fstat(fd)
        entered=[]
        self.queue.register=lambda changes:(entered.append(True),self.churn(p))
        with self.assertRaises(reader.StudioObservationError):self.walk._prefix_guard.watch(('new',),fd,pre)
        self.assertTrue(entered)
        self.assertNotIn(('new',),self.walk._prefix_guard._held)
    def test_registration_error_closes_new_duplicate(self):
        p=self.root/'new';fd=self.walk.adopt(os.open(p,reader._DIR_FLAGS));owned=[];dup=os.dup
        def record(value):new=dup(value);owned.append(new);return new
        self.queue.register=lambda changes:(_ for _ in ()).throw(OSError('inert registration error'))
        with mock.patch.object(os,'dup',side_effect=record):
            with self.assertRaises(OSError):self.walk._prefix_guard.watch(('new',),fd,os.fstat(fd))
        self.assertEqual(len(owned),1)
        for value in owned:
            with self.assertRaises(OSError):os.fstat(value)
    def test_capacity_refuses_without_new_dup(self):
        with mock.patch.object(reader,'_PREFIX_DIRECTORY_LIMIT',2),mock.patch.object(os,'dup') as dup:
            with self.assertRaises(reader.StudioObservationError):self.walk._prefix_guard.watch(('overflow',),self.child_fd,self.child_stat)
            dup.assert_not_called()
    def test_manifest_prefix_depth_refuses_before_prefix_set_growth(self):
        before=set(self.walk._traversal_prefixes)
        with self.assertRaises(reader.StudioObservationError):
            self.walk.register_tool_prefixes(('part',)*(reader._PREFIX_DIRECTORY_LIMIT+1))
        self.assertEqual(self.walk._traversal_prefixes,before)
    def test_home_depth_refuses_before_monitor_or_open(self):
        home=Path('/').joinpath(*(['part']*(reader._PREFIX_DIRECTORY_LIMIT+1)))
        with mock.patch.object(os,'open') as opened:
            with self.assertRaises(reader.StudioObservationError):
                reader.observe_studio_files(home=home,uid=reader.FIXED_OBSERVED_UID,
                    gid=os.getgid(),source_file_names=('app.py',))
            opened.assert_not_called()
    def test_unavailable_native_monitor_has_no_fallback(self):
        with mock.patch.object(select,'kqueue',side_effect=AttributeError('unavailable')):
            with self.assertRaises(reader.StudioObservationError):reader._PrefixMutationGuard()
    def test_failed_constructor_disposes_created_queue(self):
        q=QueueFixture(self.root);fd=q.fileno()
        with mock.patch.object(select,'kqueue',return_value=q), \
             mock.patch.object(os,'get_inheritable',side_effect=OSError('inert inheritance query failure')):
            with self.assertRaises(reader.StudioObservationError):reader._PrefixMutationGuard()
        with self.assertRaises(OSError):os.fstat(fd)
    def test_strict_publication_namespace_timestamp_change_refuses(self):
        self.churn(self.protected)
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
    def test_strict_role_cannot_be_promoted_to_traversal(self):
        self.walk.register_tool_prefixes(('prefix','protected','nested','node'))
        self.assertFalse(self.walk._traversal_only(('prefix','protected')))
        self.churn(self.protected)
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
    def test_other_five_directory_fields_stay_exact(self):
        pre=self.prefix_stat
        for field in reader._DIRECTORY_CUSTODY_FIELDS:
            post=SimpleNamespace(**{k:getattr(pre,k)+(1 if k==field else 0) for k in reader._IDENTITY_FIELDS})
            with self.subTest(field=field),self.assertRaises(reader.StudioObservationError):reader._require_directory_custody(pre,post)
    def test_namespace_change_during_registration_still_refuses_full_identity(self):
        p=self.root/'new';fd=self.walk.adopt(os.open(p,reader._DIR_FLAGS));pre=os.fstat(fd)
        self.queue.register=lambda changes:(p/'unrelated').write_bytes(b'OWNED')
        with self.assertRaises(reader.StudioObservationError):
            self.walk._prefix_guard.watch(('new',),fd,pre)
        self.assertNotIn(('new',),self.walk._prefix_guard._held)
    def test_strict_role_promotion_keeps_original_namespace_baseline(self):
        old=self.walk._records[('prefix',)][0]
        (self.prefix/'unrelated-directory').mkdir(mode=0o700)
        self.walk._strict_directories.add(('prefix',))
        with self.assertRaises(reader.StudioObservationError):self.walk.recheck_all()
        self.assertEqual(self.walk._records[('prefix',)][0],old)
    def test_acl_uses_fresh_actual_full_identity_after_prefix_churn(self):
        self.churn(self.prefix);seen=[]
        def acl(name,*,descriptor,expected_identity):
            reader._require_same_object(expected_identity,os.fstat(descriptor));seen.append(expected_identity);return False
        with mock.patch.object(reader,'has_macos_acl',side_effect=acl):self.walk.recheck_all()
        self.assertTrue(seen)
    def test_regular_leaf_version_remains_strict(self):
        leaf,info=self.walk.open_child(self.child_fd,'leaf',directory=False,
            policy=reader._make_owned_leaf_policy(os.getuid(),os.getgid(),executable=False))
        self.leaf.write_bytes(b'OTHER')
        with self.assertRaises(reader.StudioObservationError):self.walk.read_bounded(leaf,info,limit=32,positive=True)
    def test_terminal_cleanup_on_refusal_closes_duplicates(self):
        held=[x[0] for x in self.walk._prefix_guard._held.values()];self.queue.events=[object()]
        with self.assertRaises(reader.StudioObservationError):self.walk.close_all()
        for fd in held:
            with self.assertRaises(OSError):os.fstat(fd)


@unittest.skipUnless(hasattr(select,'kqueue'),'real Darwin vnode qualification only')
class NativePrefixTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='native-prefix-',dir=Path(__file__).resolve().parents[1])
        self.root=Path(self.temp.name);self.path=self.root/'prefix';self.path.mkdir(mode=0o700)
        self.fd=os.open(self.path,reader._DIR_FLAGS);self.guard=reader._PrefixMutationGuard()
        self.guard.watch(('prefix',),self.fd,os.fstat(self.fd))
    def tearDown(self):
        self.guard.close();os.close(self.fd);self.temp.cleanup()
    def test_actual_sibling_write_is_not_hazard(self):
        p=self.path/'unrelated';p.write_bytes(b'OWNED');p.unlink();self.guard.check()
    def test_actual_sibling_file_entry_is_not_custody(self):
        before=os.fstat(self.fd)
        (self.path/'unrelated-file').write_bytes(b'OWNED')
        after=os.fstat(self.fd)
        self.assertNotEqual((before.st_nlink,before.st_size),(after.st_nlink,after.st_size))
        self.guard.check()
    def test_actual_sibling_directory_entry_is_not_custody(self):
        before=os.fstat(self.fd)
        (self.path/'unrelated-directory').mkdir(mode=0o700)
        after=os.fstat(self.fd)
        self.assertNotEqual((before.st_nlink,before.st_size),(after.st_nlink,after.st_size))
        self.guard.check()
    def test_actual_rename_restore_is_hazard(self):
        moved=self.root/'moved';self.path.rename(moved);moved.rename(self.path)
        with self.assertRaises(reader.StudioObservationError):self.guard.check()
    def test_actual_directory_delete_is_hazard(self):
        self.path.rmdir()
        with self.assertRaises(reader.StudioObservationError):self.guard.check()
    def test_actual_same_mode_chmod_is_hazard(self):
        self.path.chmod(0o700)
        with self.assertRaises(reader.StudioObservationError):self.guard.check()
    def test_actual_guard_survives_original_traversal_close(self):
        os.close(self.fd);self.fd=os.open(self.path,reader._DIR_FLAGS)
        moved=self.root/'moved';self.path.rename(moved);moved.rename(self.path)
        with self.assertRaises(reader.StudioObservationError):self.guard.check()
    def test_repeated_success_and_failure_dispose_descriptors(self):
        for n in range(25):
            g=reader._PrefixMutationGuard();g.watch(('prefix',),self.fd,os.fstat(self.fd));owned=g._held[('prefix',)][0]
            self.assertFalse(os.get_inheritable(owned));self.assertFalse(os.get_inheritable(g._queue.fileno()))
            if n%2:
                self.path.chmod(0o700)
                with self.assertRaises(reader.StudioObservationError):g.check()
            g.close()
            with self.assertRaises(OSError):os.fstat(owned)
        # Clear the outer fixture guard only at teardown; repeated attribute
        # mutations are never treated as fresh baseline by that original guard.


# Existing inert publication/account fixture; native ACL and queue backends
# remain real on Darwin. Importing it does not observe an actual user Home.
import test_os_gateway_studio_home_acl as acl_fixture


@unittest.skipUnless(acl_fixture.IS_DARWIN,'real Darwin reader/ACL/event composition only')
class NativeObservationTests(acl_fixture.HomeAclReaderTestCase):
    def observe_native(self, mutation):
        original=reader._Walk.recheck_all
        def final(walk):
            mutation()
            return original(walk)
        with acl_fixture.reader_overrides(pwd_fixture=acl_fixture.PwdFixture(
                acl_fixture.pwd_record(str(self.fx.home),acl_fixture.CURRENT_UID,acl_fixture.CURRENT_GID))), \
             mock.patch.object(reader._Walk,'recheck_all',new=final):
            return self.fx.observe()
    def churn(self,path):
        leaf=path/'unrelated-prefix-write';leaf.write_bytes(b'OWNED-INERT');leaf.unlink()
    def test_native_home_acl_reclassifies_fresh_identity_after_sibling_churn(self):
        import subprocess
        subprocess.run(['/bin/chmod','+a','everyone deny delete',str(self.fx.home)],check=True,capture_output=True)
        result=self.observe_native(lambda:self.churn(self.fx.home))
        self.assertTrue(result.node_sha256)
    def test_native_closed_tool_traversal_fd_still_observes_benign_write(self):
        result=self.observe_native(lambda:self.churn(self.fx.tools/'backend'))
        self.assertTrue(result.backend_sha256)
    def test_native_closed_tool_prefix_allows_unrelated_file_entry(self):
        result=self.observe_native(lambda:(self.fx.tools/'backend'/'unrelated-file').write_bytes(b'INERT'))
        self.assertTrue(result.backend_sha256)
    def test_native_home_prefix_allows_unrelated_directory_entry(self):
        result=self.observe_native(lambda:(self.fx.home/'unrelated-directory').mkdir(mode=0o700))
        self.assertTrue(result.manifest_bytes)
    def test_native_closed_tool_traversal_fd_still_rejects_rename_restore(self):
        path=self.fx.tools/'backend';moved=self.fx.tools/'moved-backend'
        def rename():path.rename(moved);moved.rename(path)
        with self.assertRaises(reader.StudioObservationError):self.observe_native(rename)
    def test_native_library_acl_reclassifies_fresh_identity_after_sibling_churn(self):
        import subprocess
        path=self.fx.home/'Library'
        subprocess.run(['/bin/chmod','+a','everyone deny delete',str(path)],check=True,capture_output=True)
        result=self.observe_native(lambda:self.churn(path))
        self.assertTrue(result.plist_bytes)
    def test_native_prefix_custody_change_stays_strict(self):
        def change():
            before=self.fx.home.stat()
            self.fx.home.chmod(0o750 if before.st_mode&0o777 != 0o750 else 0o700)
            after=self.fx.home.stat()
            self.assertTrue(any(getattr(before,k)!=getattr(after,k)
                                for k in reader._DIRECTORY_CUSTODY_FIELDS))
        with self.assertRaises(reader.StudioObservationError):self.observe_native(change)
    def test_native_launchagents_unrelated_file_entry_stays_strict(self):
        with self.assertRaises(reader.StudioObservationError):
            self.observe_native(lambda:(self.fx.home/'Library'/'LaunchAgents'/'unrelated-file').write_bytes(b'INERT'))
    def test_native_publication_unrelated_directory_entry_stays_strict(self):
        with self.assertRaises(reader.StudioObservationError):
            self.observe_native(lambda:(self.fx.base/'unrelated-directory').mkdir(mode=0o700))
    def test_native_dependency_unrelated_directory_entry_stays_strict(self):
        with self.assertRaises(reader.StudioObservationError):
            self.observe_native(lambda:(self.fx.node_modules/'unrelated-directory').mkdir(mode=0o700))
    def test_native_late_even_permitted_acl_change_still_refuses(self):
        import subprocess
        def change():
            subprocess.run(['/bin/chmod','+a','everyone deny delete',str(self.fx.home)],
                           check=True,capture_output=True)
        with self.assertRaises(reader.StudioObservationError):self.observe_native(change)
    def test_native_launchagents_namespace_stays_strict(self):
        with self.assertRaises(reader.StudioObservationError):
            self.observe_native(lambda:self.churn(self.fx.home/'Library'/'LaunchAgents'))
    def test_native_publication_namespace_stays_strict(self):
        with self.assertRaises(reader.StudioObservationError):self.observe_native(lambda:self.churn(self.fx.base))
    def test_native_dependency_namespace_stays_strict(self):
        with self.assertRaises(reader.StudioObservationError):self.observe_native(lambda:self.churn(self.fx.node_modules))


if __name__=='__main__':unittest.main(verbosity=2)
