"""Synthetic namespace resource tests; no live paths/FDs/commands/probes."""
import errno
import importlib.util
from pathlib import Path
import stat
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
S=types.SimpleNamespace
P=types.ModuleType('control_plane.executive_installed_peer')
P._GATEWAY_MCP_PROFILES=('release_control_v1','web_ceo_release_v1')
P._SYSCTL_OSRELEASE_ARGV=('/usr/sbin/sysctl','-n','kern.osrelease')
P._SYSCTL_BOOT_ID_ARGV=('/usr/sbin/sysctl','-n','kern.bootsessionuuid')
P._object_identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
OWN=(10,110,1)
class Budget:
    def __init__(self,endpoint):self.endpoint=endpoint
    def call(self,function,*args,**kwargs):return function(*args,**kwargs)
    def check(self,*args,**kwargs):pass

with patch.dict(sys.modules):
    pkg=types.ModuleType('control_plane');pkg.__path__=[]
    sys.modules['control_plane']=pkg
    sys.modules['control_plane.executive_installed_peer']=P
    release_spec=importlib.util.spec_from_file_location('control_plane.executive_release_observation',ROOT/'control_plane/executive_release_observation.py')
    R=importlib.util.module_from_spec(release_spec);sys.modules[release_spec.name]=R
    canonical=types.ModuleType('control_plane.executive_release_contract');canonical.canonical_release_bytes=lambda _:b'unused'
    sys.modules[canonical.__name__]=canonical
    release_spec.loader.exec_module(R)
    host=types.ModuleType('control_plane.executive_recovery_host_observation');host._instance=Mock(side_effect=AssertionError('inject kernel identity'))
    sys.modules[host.__name__]=host
    security=types.ModuleType('control_plane.fs_security');security.ACL_TYPE_EXTENDED=0x100
    sys.modules[security.__name__]=security
    spec=importlib.util.spec_from_file_location('control_plane.executive_recovery_namespace',ROOT/'control_plane/executive_recovery_namespace.py')
    M=importlib.util.module_from_spec(spec);sys.modules[spec.name]=M;spec.loader.exec_module(M)

REAL_SOCKET_ACL=M._require_no_socket_acl

class NamespaceTests(unittest.TestCase):
    def setUp(self):
        self.budget=Budget(1000)
        self.infos={}
        for index,path in enumerate(M._DIRECTORIES+(M._ALIAS,)):
            # Retained host profile: runtime ancestors are root:daemon; only
            # /private/var/run is group writable. Never broaden other paths.
            mode=0o775 if path=='/private/var/run' else 0o755
            gid=1 if path in ('/private/var/run','/private/var/run/mastermind-executive') else 0
            self.infos[path]=self.info(100+index,stat.S_IFLNK if path==M._ALIAS else stat.S_IFDIR,mode,0,gid)
        self.fd_paths={};self.next_fd=20;self.closed=[];self.socket=None
        self.opened=[];self.fail_open=None;self.fail_close=None;self.acl_path=None
        self.native=S(getpid=lambda:10,geteuid=lambda:0,O_RDONLY=0,O_NOFOLLOW=1,O_CLOEXEC=2,O_SYMLINK=4,
                      O_DIRECTORY=8,O_NONBLOCK=16,open=Mock(side_effect=self.native_open),
                      fstat=Mock(side_effect=self.fstat),stat=Mock(side_effect=self.relative))
        self.patches=[patch.object(M,'os',self.native),patch.object(M,'sys',S(platform='darwin')),
                      patch.object(M,'_instance',return_value=OWN),patch.object(R,'_Budget',return_value=self.budget),
                      patch.object(R,'_boot',return_value='boot'),patch.object(M,'_require_no_socket_acl',return_value=None),
                      patch.object(P,'_lstat',side_effect=self.lstat,create=True),patch.object(P,'_readlink',return_value='private/var',create=True),
                      patch.object(P,'_open_trusted',side_effect=self.open,create=True),patch.object(P,'_require_no_acl',side_effect=self.acl,create=True),
                      patch.object(P,'_close',side_effect=self.close,create=True)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def info(self,ino,kind=stat.S_IFSOCK,mode=0o660,uid=450,gid=453,**kw):
        args=dict(st_dev=1,st_ino=ino,st_mode=kind|mode,st_uid=uid,st_gid=gid,st_nlink=1,st_size=0,st_mtime_ns=20,st_ctime_ns=20,st_flags=0)
        args.update(kw);return S(**args)
    def missing(self): raise FileNotFoundError(errno.ENOENT,'synthetic absent')
    def lstat(self,path):
        if path in self.infos:return self.infos[path]
        if path in (M._CANONICAL,M._LEXICAL):return self.socket if self.socket is not None else self.missing()
        raise AssertionError('unexpected path '+path)
    def fstat(self,fd):
        if fd not in self.fd_paths:raise OSError('closed')
        return self.infos[self.fd_paths[fd]]
    def relative(self,path,*,dir_fd,follow_symlinks):
        assert path==M._LEAF and self.fd_paths[dir_fd]==M._DIRECTORIES[-1] and follow_symlinks is False
        return self.socket if self.socket is not None else self.missing()
    def open(self,path,*,budget,allow_symlink):
        assert budget is self.budget
        assert allow_symlink==(M._ALIAS if path==M._ALIAS else None)
        if path==self.fail_open:raise OSError('open failed')
        fd=self.next_fd;self.next_fd+=1;self.fd_paths[fd]=path;self.opened.append(fd)
        return fd,self.infos[path],self.infos[path]
    def native_open(self,path,flags):
        alias=path==M._ALIAS
        expected=self.native.O_CLOEXEC|self.native.O_NONBLOCK
        expected|=self.native.O_SYMLINK if alias else self.native.O_NOFOLLOW|self.native.O_DIRECTORY
        self.assertEqual(flags,expected)
        return self.open(path,budget=self.budget,allow_symlink=M._ALIAS if alias else None)[0]
    def close(self,fd):
        self.closed.append(fd)
        if fd==self.fail_close:raise OSError('close ambiguous')
        self.fd_paths.pop(fd,None)
    def acl(self,path,*a,**kw):return path==self.acl_path
    def acquire(self):return M._acquire_namespace(deadline_monotonic_ns=1000)

    def test_retained_actual_runtime_profile_qualifies_without_generic_opener(self):
        with patch.object(P,'_open_trusted',side_effect=AssertionError('generic trust must not be weakened')):
            h=self.acquire()
            self.assertEqual(len(self.native.open.call_args_list),len(M._DIRECTORIES)+1)
            M._release_namespace(h)
        self.assertEqual(self.fd_paths,{})

    def test_directory_child_link_count_is_not_retained_incarnation(self):
        before=self.info(300,stat.S_IFDIR,0o755,0,1,st_nlink=2)
        after=S(**(vars(before)|dict(st_nlink=3,st_size=40,st_mtime_ns=40,st_ctime_ns=40)))
        self.assertEqual(M._structural(before),M._structural(after))

    def test_directory_native_flags_are_retained_security_metadata(self):
        before=self.info(300,stat.S_IFDIR,0o755,0,1)
        after=S(**(vars(before)|dict(st_flags=2)))
        self.assertNotEqual(M._structural(before),M._structural(after))

    def test_holds_exact_qualified_chain_and_alias_then_closes_reverse(self):
        h=self.acquire()
        self.assertEqual(tuple(x.path for x in h.held),M._DIRECTORIES+(M._ALIAS,))
        self.assertEqual(len(self.closed),0)
        M._require_socket_absent(h)
        M._release_namespace(h)
        self.assertEqual(self.closed,list(reversed(self.opened)))
        self.assertEqual(self.fd_paths,{})

    def test_wrong_owner_platform_or_missing_native_flags_fail_before_open(self):
        for field,value in [('O_SYMLINK',None),('O_NOFOLLOW',0),('O_CLOEXEC',True),('O_DIRECTORY',0),('O_NONBLOCK',None)]:
            with patch.object(self.native,field,value),self.assertRaises(M.NamespaceObservationError):self.acquire()
        with patch.object(self.native,'geteuid',return_value=501),self.assertRaises(M.NamespaceObservationError):self.acquire()
        with patch.object(M.sys,'platform','linux'),self.assertRaises(M.NamespaceObservationError):self.acquire()
        self.assertFalse(self.opened)

    def test_partial_acquisition_failure_closes_every_acquired_handle(self):
        self.fail_open=M._DIRECTORIES[3]
        with self.assertRaises(OSError):self.acquire()
        self.assertEqual(self.closed,list(reversed(self.opened)))
        self.assertEqual(self.fd_paths,{})

    def test_deadline_after_fd_return_does_not_leak_handle(self):
        def check(*a,**kw):
            if self.opened:raise R.ReleaseObservationError('deadline')
        self.budget.check=check
        with self.assertRaises(R.ReleaseObservationError):self.acquire()
        self.assertEqual(self.opened,[20]);self.assertEqual(self.closed,[20])

    def test_wrong_type_mode_uid_gid_link_or_alias_refuses_and_cleans(self):
        original=self.infos[M._ALIAS]
        for change in [dict(st_uid=501),dict(st_gid=1),dict(st_nlink=2),dict(st_mode=stat.S_IFLNK|0o777),dict(st_mode=stat.S_IFREG|0o755)]:
            self.infos[M._ALIAS]=S(**(vars(original)|change));self.opened=[];self.closed=[]
            with self.subTest(change=change),self.assertRaises(M.NamespaceObservationError):self.acquire()
            self.assertEqual(self.closed,list(reversed(self.opened)))
        self.infos[M._ALIAS]=original
        with patch.object(P,'_readlink',return_value='/foreign'),self.assertRaises(M.NamespaceObservationError):self.acquire()

    def test_acl_present_or_unobservable_refuses(self):
        self.acl_path=M._DIRECTORIES[-1]
        with self.assertRaises(M.NamespaceObservationError):self.acquire()
        self.assertEqual(self.fd_paths,{})
        self.acl_path=None
        with patch.object(P,'_require_no_acl',side_effect=OSError('ACL unknown')),self.assertRaises(OSError):self.acquire()
        self.assertEqual(self.fd_paths,{})

    def test_parent_replacement_is_sticky_even_after_path_restored(self):
        h=self.acquire();before=self.infos[M._DIRECTORIES[-1]]
        self.infos[M._DIRECTORIES[-1]]=self.info(999,stat.S_IFDIR,0o755,0,0)
        with self.assertRaises(M.NamespaceObservationError):M._recheck_namespace(h)
        self.infos[M._DIRECTORIES[-1]]=before
        with self.assertRaises(M.NamespaceObservationError):M._recheck_namespace(h)
        M._release_namespace(h)

    def test_expected_child_metadata_change_does_not_pretend_parent_is_a_lock(self):
        h=self.acquire();old=self.infos[M._DIRECTORIES[-1]]
        self.infos[M._DIRECTORIES[-1]]=S(**(vars(old)|dict(st_nlink=old.st_nlink+1,st_size=40,st_mtime_ns=40,st_ctime_ns=40)))
        M._recheck_namespace(h)
        M._release_namespace(h)

    def test_exact_path_profiles_refuse_wrong_group_mode_or_owner_before_open(self):
        for path in M._DIRECTORIES:
            original=self.infos[path]
            for change in (dict(st_gid=2),dict(st_gid=0 if original.st_gid else 1),dict(st_uid=501),
                           dict(st_mode=stat.S_IFDIR|0o777),dict(st_mode=stat.S_IFDIR|0o750),
                           dict(st_mode=stat.S_IFDIR|(0o755 if path=='/private/var/run' else 0o775))):
                self.infos[path]=S(**(vars(original)|change));self.opened=[];self.closed=[]
                with self.subTest(path=path,change=change),self.assertRaises(M.NamespaceObservationError):self.acquire()
                self.assertEqual(self.closed,list(reversed(self.opened)))
                self.assertEqual(self.fd_paths,{})
            self.infos[path]=original

    def test_fixed_opener_refuses_unknown_path_without_lookup_or_open(self):
        P._lstat.reset_mock();self.native.open.reset_mock()
        with self.assertRaisesRegex(M.NamespaceObservationError,'PROFILE_DRIFT'):
            M._open_namespace_object('/private/var/run/other',self.budget)
        P._lstat.assert_not_called();self.native.open.assert_not_called()

    def test_native_flags_change_between_observations_invalidates_context(self):
        h=self.acquire();path=M._DIRECTORIES[-1];old=self.infos[path]
        self.infos[path]=S(**(vars(old)|dict(st_flags=2)))
        with self.assertRaisesRegex(M.NamespaceObservationError,'REPLACED'):M._recheck_namespace(h)
        M._release_namespace(h)

    def test_link_count_or_flags_change_during_read_is_not_excused(self):
        for change in (dict(st_nlink=3),dict(st_flags=2)):
            h=self.acquire();real=self.lstat;calls=0
            def changed(path):
                nonlocal calls
                value=real(path)
                if path=='/':
                    calls+=1
                    if calls==2:return S(**(vars(value)|change))
                return value
            with self.subTest(change=change),patch.object(P,'_lstat',side_effect=changed),self.assertRaisesRegex(M.NamespaceObservationError,'CHANGED_DURING_READ'):
                M._recheck_namespace(h)
            M._release_namespace(h)

    def test_object_replacement_between_lstat_and_open_refuses_and_closes(self):
        real=self.native_open
        def replaced(path,flags):
            descriptor=real(path,flags)
            self.infos[path]=S(**(vars(self.infos[path])|dict(st_ino=999)))
            return descriptor
        with patch.object(self.native,'open',side_effect=replaced),self.assertRaisesRegex(M.NamespaceObservationError,'REPLACED'):
            self.acquire()
        self.assertEqual(self.opened,[20]);self.assertEqual(self.closed,[20]);self.assertEqual(self.fd_paths,{})

    def test_change_during_single_read_refuses(self):
        h=self.acquire();real=self.lstat;calls=0
        def changed(path):
            nonlocal calls
            value=real(path)
            if path=='/':
                calls+=1
                if calls==2:return S(**(vars(value)|dict(st_mtime_ns=99)))
            return value
        with patch.object(P,'_lstat',side_effect=changed),self.assertRaises(M.NamespaceObservationError):M._recheck_namespace(h)
        M._release_namespace(h)

    def test_boot_or_own_instance_change_invalidates_context(self):
        for target,value in [('boot','other'),('instance',(10,999,1))]:
            h=self.acquire()
            patcher=patch.object(R,'_boot',return_value=value) if target=='boot' else patch.object(M,'_instance',return_value=value)
            with patcher,self.assertRaises(M.NamespaceObservationError):M._recheck_namespace(h)
            self.assertTrue(h.failed);M._release_namespace(h)

    def test_preexisting_any_object_blocks_absence_without_unlink(self):
        for kind in (stat.S_IFSOCK,stat.S_IFREG,stat.S_IFLNK):
            h=self.acquire();self.socket=self.info(200,kind)
            with self.assertRaisesRegex(M.NamespaceObservationError,'PREEXISTS'):M._require_socket_absent(h)
            self.assertIsNotNone(self.socket);M._release_namespace(h);self.socket=None

    def test_only_enoent_counts_as_absence(self):
        for error in [PermissionError(errno.EACCES,'denied'),FileNotFoundError(errno.ENOTDIR,'wrong parent'),FileNotFoundError('ambiguous')]:
            h=self.acquire()
            with patch.object(self.native,'stat',side_effect=error),self.assertRaises(OSError):M._require_socket_absent(h)
            self.assertTrue(h.failed);M._release_namespace(h)

    def test_namespace_lexical_canonical_and_dirfd_leaf_must_all_match(self):
        h=self.acquire();self.socket=self.info(200)
        real=self.lstat
        def replaced(path):return self.info(201) if path==M._LEXICAL else real(path)
        with patch.object(P,'_lstat',side_effect=replaced),self.assertRaisesRegex(M.NamespaceObservationError,'REPLACED'):M._observe_socket_node(h)
        M._release_namespace(h)

    def test_created_node_observation_and_same_node_revalidation(self):
        h=self.acquire();M._require_socket_absent(h);self.socket=self.info(200)
        observed=M._observe_socket_node(h);M._require_same_socket(h,observed)
        M._require_no_socket_acl.assert_called_with(self.budget)
        M._release_namespace(h)

    def test_node_owner_type_mode_link_drift_refuses(self):
        for change in [dict(st_uid=0),dict(st_gid=450),dict(st_mode=stat.S_IFSOCK|0o666),dict(st_nlink=2),dict(st_mode=stat.S_IFREG|0o660)]:
            h=self.acquire();self.socket=S(**(vars(self.info(200))|change))
            with self.subTest(change=change),self.assertRaises(M.NamespaceObservationError):M._observe_socket_node(h)
            M._release_namespace(h)

    def test_socket_acl_unavailable_and_deadline_refuse(self):
        for error in [M.NamespaceObservationError('ACL_PRESENT'),M.NamespaceObservationError('ACL_UNPROVEN'),R.ReleaseObservationError('deadline')]:
            h=self.acquire();self.socket=self.info(200)
            with patch.object(M,'_require_no_socket_acl',side_effect=error),self.assertRaises((M.NamespaceObservationError,R.ReleaseObservationError)):M._observe_socket_node(h)
            M._release_namespace(h)

    def test_socket_replacement_after_native_acl_query_refuses(self):
        h=self.acquire();self.socket=self.info(200)
        def query(*a):self.socket=self.info(201)
        with patch.object(M,'_require_no_socket_acl',side_effect=query),self.assertRaises(M.NamespaceObservationError):M._observe_socket_node(h)
        M._release_namespace(h)

    def test_prior_node_does_not_authorize_changed_node_or_plain_dict(self):
        h=self.acquire();self.socket=self.info(200);previous=M._observe_socket_node(h);self.socket=self.info(201)
        with self.assertRaises(M.NamespaceObservationError):M._require_same_socket(h,previous)
        M._release_namespace(h)
        h=self.acquire()
        with self.assertRaises(M.NamespaceObservationError):M._require_same_socket(h,{'identity':previous.identity})
        M._release_namespace(h)

    def test_close_failure_attempts_all_and_cannot_reuse_context(self):
        h=self.acquire();self.fail_close=self.opened[-1]
        with self.assertRaisesRegex(M.NamespaceObservationError,'CLEANUP_UNPROVEN'):M._release_namespace(h)
        self.assertEqual(self.closed,list(reversed(self.opened)))
        with self.assertRaises(M.NamespaceObservationError):M._recheck_namespace(h)
        with self.assertRaises(M.NamespaceObservationError):M._release_namespace(h)

    def test_expired_cleanup_still_closes_all_owned_handles(self):
        h=self.acquire();self.budget.check=Mock(side_effect=R.ReleaseObservationError('deadline'))
        with self.assertRaises(R.ReleaseObservationError):M._release_namespace(h)
        self.assertEqual(self.fd_paths,{})

    def test_actual_acl_present_is_rejected_even_when_permission_text_has_no_plus(self):
        # Apple stat's real source renders only st_mode. The modeled inode has
        # an ACL, but its truthful permission text remains srw-rw----. The old
        # producer accepts that text without ever consulting this ACL getter.
        import ctypes
        h=self.acquire();self.socket=self.info(200)
        state={'errno':0}
        def get_acl(*args):state['errno']=0;return 1234
        lib=S(acl_get_link_np=Mock(side_effect=get_acl),acl_free=Mock(return_value=0))
        native=S(CDLL=Mock(return_value=lib),c_char_p=ctypes.c_char_p,c_int=ctypes.c_int,c_void_p=ctypes.c_void_p,
                 set_errno=lambda v:state.update(errno=v),get_errno=lambda:state['errno'])
        with patch.object(M,'ctypes',native,create=True),patch.object(M,'_require_no_socket_acl',REAL_SOCKET_ACL):
            try:
                with self.assertRaises(M.NamespaceObservationError):M._observe_socket_node(h)
            finally:M._release_namespace(h)

class NativeAclTests(unittest.TestCase):
    def setUp(self):
        import ctypes
        self.budget=Budget(1000)
        self.state={'errno':99}
        self.pointer=None;self.native_errno=errno.ENOENT
        def acquire(path,kind):
            self.assertEqual(self.state['errno'],0)
            self.state['errno']=self.native_errno
            return self.pointer
        self.lib=S(acl_get_link_np=Mock(side_effect=acquire),acl_free=Mock(return_value=0))
        self.native=S(CDLL=Mock(return_value=self.lib),c_char_p=ctypes.c_char_p,c_int=ctypes.c_int,c_void_p=ctypes.c_void_p,
                      set_errno=lambda value:self.state.update(errno=value),get_errno=lambda:self.state['errno'])
        self.patchers=[patch.object(M,'ctypes',self.native),patch.object(M,'sys',S(platform='darwin')),patch.object(M,'os',S(geteuid=lambda:0))]
        for p in self.patchers:p.start();self.addCleanup(p.stop)

    def test_null_enoent_only_after_errno_clear_uses_exact_nofollow_api(self):
        REAL_SOCKET_ACL(self.budget)
        self.lib.acl_get_link_np.assert_called_once_with(M._CANONICAL.encode('ascii'),0x100)
        self.native.CDLL.assert_called_once_with(None,use_errno=True)
        self.lib.acl_free.assert_not_called()
        self.assertEqual(self.lib.acl_get_link_np.argtypes,[self.native.c_char_p,self.native.c_int])
        self.assertIs(self.lib.acl_get_link_np.restype,self.native.c_void_p)

    def test_null_uncertain_or_error_errno_cannot_count_as_no_acl(self):
        for number in (0,errno.EACCES,errno.EIO,errno.EINVAL,errno.ENOTSUP):
            self.native_errno=number
            with self.subTest(number=number),self.assertRaisesRegex(M.NamespaceObservationError,'ACL_UNPROVEN'):REAL_SOCKET_ACL(self.budget)
        self.lib.acl_free.assert_not_called()

    def test_any_returned_acl_is_refused_and_freed_once(self):
        self.pointer=1234
        for number in (0,errno.EIO,errno.ENOENT):
            self.native_errno=number;self.lib.acl_free.reset_mock()
            with self.subTest(number=number),self.assertRaisesRegex(M.NamespaceObservationError,'ACL_PRESENT'):REAL_SOCKET_ACL(self.budget)
            self.lib.acl_free.assert_called_once_with(1234)

    def test_expiry_after_allocating_query_still_frees(self):
        self.pointer=1234;self.native_errno=0
        self.budget.check=Mock(side_effect=[None,R.ReleaseObservationError('deadline')])
        with self.assertRaisesRegex(R.ReleaseObservationError,'deadline'):REAL_SOCKET_ACL(self.budget)
        self.lib.acl_free.assert_called_once_with(1234)

    def test_failed_acl_free_never_reports_qualified_absence(self):
        self.pointer=1234;self.native_errno=0
        for value in (-1,False,None):
            self.lib.acl_free.return_value=value
            with self.subTest(value=value),self.assertRaisesRegex(M.NamespaceObservationError,'CLEANUP_UNPROVEN'):REAL_SOCKET_ACL(self.budget)
        self.lib.acl_free.side_effect=OSError('free failed')
        with self.assertRaisesRegex(M.NamespaceObservationError,'CLEANUP_UNPROVEN'):REAL_SOCKET_ACL(self.budget)

    def test_unavailable_api_refuses_without_fallback_command(self):
        self.native.CDLL.return_value=S()
        with self.assertRaisesRegex(M.NamespaceObservationError,'API_UNAVAILABLE'):REAL_SOCKET_ACL(self.budget)
        self.lib.acl_get_link_np.assert_not_called()

    def test_wrong_principal_or_platform_refuses_before_library_load(self):
        with patch.object(M.sys,'platform','linux'),self.assertRaises(M.NamespaceObservationError):REAL_SOCKET_ACL(self.budget)
        with patch.object(M.os,'geteuid',return_value=501),self.assertRaises(M.NamespaceObservationError):REAL_SOCKET_ACL(self.budget)
        self.native.CDLL.assert_not_called()

    def test_failing_native_call_does_not_invent_allocation_or_absence(self):
        self.lib.acl_get_link_np.side_effect=OSError('unavailable')
        with self.assertRaises(OSError):REAL_SOCKET_ACL(self.budget)
        self.lib.acl_free.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
