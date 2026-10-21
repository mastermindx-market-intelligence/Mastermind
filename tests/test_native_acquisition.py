"""Synthetic source tests: no native command, socket, process or host probe."""
import ast
import ctypes
import importlib.util
from pathlib import Path
import socket as socket_constants
import stat
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
def _load_fixture_world():
    # Restore every prior module after importing the actual source against
    # injected native collaborators. This suite must not contaminate peers.
    with patch.dict(sys.modules):
        PKG = types.ModuleType('control_plane')
        PKG.__path__ = [str(ROOT / 'control_plane')]
        sys.modules['control_plane'] = PKG
        PEER = types.ModuleType('control_plane.executive_installed_peer')
        PEER._GATEWAY_MCP_PROFILES = ('release_control_v1', 'web_ceo_release_v1')
        PEER._SYSCTL_OSRELEASE_ARGV = ('/usr/sbin/sysctl', '-n', 'kern.osrelease')
        PEER._SYSCTL_BOOT_ID_ARGV = ('/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid')
        PEER._LAUNCHD_ENVIRONMENT = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}
        PEER._PYTHON_MAIN_EXECUTABLE = '/qualified/main/Python'
        PEER._verify_python_runtime = Mock(return_value='runtime-pin')
        PEER._recheck_python_runtime = Mock()
        PEER._object_identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        sys.modules[PEER.__name__] = PEER
        contract = types.ModuleType('control_plane.executive_release_contract')
        contract.canonical_release_bytes = lambda _: b'unused'
        sys.modules[contract.__name__] = contract
        for name, attr in [('executive_ambient_process', '_proc_pid_path'), ('executive_process_identity', '_observe_process_instance')]:
            mod = types.ModuleType('control_plane.' + name)
            setattr(mod, attr, Mock(side_effect=AssertionError('native acquisition must be injected')))
            sys.modules[mod.__name__] = mod

        def load(name, rel):
            spec = importlib.util.spec_from_file_location(name, ROOT / rel)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module

        R = load('control_plane.executive_release_observation', 'control_plane/executive_release_observation.py')
        H = load('control_plane.executive_recovery_host_observation', 'control_plane/executive_recovery_host_observation.py')
        N = sys.modules['control_plane.executive_recovery_observation_normalization']
        return PEER, R, H, N

PEER, R, H, N = _load_fixture_world()
S = types.SimpleNamespace

class Budget:
    def __init__(self, endpoint=1000):
        self.endpoint = endpoint
        self.started = 10
        self.last = 20
        self.calls = []
    def call(self, function, *a, **kw):
        self.calls.append((function, a, kw))
        return function(*a, **kw)
    def check(self, *a, **kw):
        pass
    def remaining(self):
        return .1

MAIN = (1, 30, stat.S_IFREG | 0o755, 0, 0, 1, 10, 20, 20)
OTHER = (1, 40, stat.S_IFREG | 0o755, 0, 0, 1, 10, 20, 20)
OWN = N.Instance(10, 110, 1)
def row(pid, identity=OTHER, path='/bin/positive-image'):
    return H._ImageRow(N.Instance(pid, pid + 100, 1), path, identity)
def absent(label='com.mastermind.executive.privileged', prefix=False):
    return (113, b'', (b'Bad request.\n' if prefix else b'') + f'Could not find service "{label}" in domain for system\n'.encode())
DISABLED = (0, b'disabled services = {\n\t"com.mastermind.executive.privileged" => true\n}\n', b'')

class HostTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(H, 'os', S(getpid=lambda: 10, geteuid=lambda: 0, lstat=Mock(side_effect=AssertionError('no native lstat')))),
            patch.object(H, 'sys', S(platform='darwin')),
        ]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        self.budget = Budget()

    def test_fixture_imports_leave_shared_modules_unchanged(self):
        # Compare around the actual fixture load, not with module collection:
        # later pytest imports are legitimate changes to the shared registry.
        before = dict(sys.modules)
        _load_fixture_world()
        self.assertEqual(dict(sys.modules), before)

    def test_exact_absence_encodings_and_closed_labels(self):
        for spec in R._SPECS:
            for prefix in (False, True):
                self.assertEqual(R._parse_service(spec, *absent(spec.label, prefix), (), ''), ('UNLOADED', None))
        for value in [(1,b'',b'permission denied\n'), (113,b'noise',absent()[2]), (113,b'',b'unknown error\n'), (0,b'',b''), (True,b'',absent()[2])]:
            with self.subTest(value=value):
                try: result=R._exact_unloaded_reply(R._SPECS[-1].label, *value)
                except R.ReleaseObservationError: result=False
                self.assertFalse(result)
        with self.assertRaises(R.ReleaseObservationError): R._exact_unloaded_reply('foreign', *absent())
        with self.assertRaises(R.ReleaseObservationError): R._exact_unloaded_reply(R._SPECS[-1].label, 113, b'x'*65537, b'')
        self.assertFalse(hasattr(N, 'normalize_unloaded'))

    def test_inventory_owned_child_only_removed_from_own_snapshot(self):
        with patch.object(R, '_command', return_value=(0,b'1 0\n10 0\n22 501\n90 0\n',b'',90)) as command:
            self.assertEqual(H._root_pids(self.budget), (1,10))
            command.assert_called_once_with(R._ROOT_PID_UID_ARGV, self.budget, include_owned_inventory_pid=True)

    def test_inventory_refuses_missing_wrong_or_unsettled_child(self):
        for child in (True, 1, 10, 91, '90'):
            with self.subTest(child=child), patch.object(R, '_command', return_value=(0,b'1 0\n10 0\n90 0\n',b'',child)):
                with self.assertRaises(H.HostObservationError): H._root_pids(self.budget)
        with patch.object(R, '_command', side_effect=TimeoutError('unreaped')):
            with self.assertRaises(TimeoutError): H._root_pids(self.budget)

    def test_inventory_rejects_partial_stderr_duplicate_and_nonroot_child(self):
        for reply in [(0,b'1 0\n10 0\n90 501\n',b'',90),(0,b'1 0\n90 0',b'',90),(0,b'1 0\n90 0\n',b'warning',90),(0,b'1 0\n90 0\n90 0\n',b'',90)]:
            with self.subTest(reply=reply), patch.object(R, '_command', return_value=reply):
                with self.assertRaises(H.HostObservationError): H._root_pids(self.budget)

    def image(self, instances=None, paths=None, files=None):
        instances = instances or [OWN, OWN]
        paths = paths or ['/qualified/main/Python']*2
        files = files or [MAIN,MAIN]
        return [patch.object(H,'_instance',side_effect=instances),patch.object(H,'_proc_pid_path',side_effect=paths),patch.object(H,'_physical_file',side_effect=files)]

    def test_image_joins_kernel_instance_path_and_file(self):
        with self.image()[0], self.image()[1], self.image()[2]:
            self.assertEqual(H._image_row(10,self.budget),row(10,MAIN,'/qualified/main/Python'))

    def test_image_refuses_exec_birth_path_and_inode_drift(self):
        cases=[dict(instances=[OWN,N.Instance(10,111,1)]),dict(instances=[OWN,N.Instance(10,110,2)]),dict(paths=['/a','/b']),dict(paths=['/a',None]),dict(paths=['/a/../b','/a/../b']),dict(files=[MAIN,OTHER])]
        for case in cases:
            p=self.image(**case)
            with self.subTest(case=case),p[0],p[1],p[2]:
                with self.assertRaises(H.HostObservationError): H._image_row(10,self.budget)

    def test_physical_mapping_rejects_symlink_or_missing(self):
        with patch.object(H.os,'lstat',return_value=S(st_mode=stat.S_IFLNK|0o777,st_nlink=1)):
            with self.assertRaises(H.HostObservationError): H._physical_file('/synthetic',self.budget)
        with patch.object(H.os,'lstat',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError): H._physical_file('/synthetic',self.budget)

    def census_patches(self, pids=None, rows=None, own=None, files=None):
        rows=rows or [row(1),row(10,MAIN),row(20)]*2
        return [patch.object(H,'_root_pids',side_effect=pids or [(1,10,20)]*2),patch.object(H,'_image_row',side_effect=rows),patch.object(H,'_instance',side_effect=own or [OWN,OWN]),patch.object(H,'_physical_file',side_effect=files or [MAIN,MAIN])]

    def census(self, **kw):
        a,b,c,d=self.census_patches(**kw)
        with a,b,c,d: return H._root_census(self.budget)

    def test_complete_census_retains_every_positive_row(self):
        value=self.census()
        self.assertEqual(tuple(r.instance.pid for r in value.rows),(1,10,20))
        self.assertEqual(value.matching_runtime_instances,(OWN,))
        PEER._recheck_python_runtime.assert_called_with('runtime-pin',self.budget)

    def test_census_matches_physical_image_even_different_path(self):
        rows=[row(1),row(10,MAIN),row(20,MAIN,'/unexpected/alias')]*2
        value=self.census(rows=rows)
        self.assertEqual(value.matching_runtime_instances,(OWN,N.Instance(20,120,1)))

    def test_census_refuses_birth_exit_reuse_and_unknown_image(self):
        # Complete inventory churn may reacquire, but three unstable candidates
        # still refuse. Identity/image errors are never converted into retries.
        churn=dict(pids=[(1,10,20),(1,10)]*3,rows=[row(1),row(10,MAIN),row(20)]*3,own=[OWN]*4,files=[MAIN]*4)
        cases=[churn,dict(own=[OWN,N.Instance(10,111,1)]),dict(rows=[row(1),row(10,MAIN),row(20),row(1),row(10,MAIN),row(20,MAIN)]),dict(rows=[row(1),row(10,MAIN),OSError('vanished')]),dict(files=[MAIN,OTHER])]
        for case in cases:
            with self.subTest(case=case),self.assertRaises((H.HostObservationError,OSError)):
                self.census(**case)

    def test_census_requires_qualified_observer_and_self_in_inventory(self):
        for case in (dict(pids=[(1,20)]),dict(rows=[row(1),row(10),row(20)]*2)):
            with self.subTest(case=case),self.assertRaises(H.HostObservationError): self.census(**case)

    def test_strict_maintenance_requires_disabled_and_exact_unloaded(self):
        with patch.object(R,'_command',side_effect=[DISABLED,absent()]): H._strict_disabled_unloaded(self.budget)
        for values in ([DISABLED,(1,b'',b'permission denied')],[(0,b'disabled services = {\n}\n',b''),absent()]):
            with self.subTest(values=values),patch.object(R,'_command',side_effect=values):
                with self.assertRaises(H.HostObservationError): H._strict_disabled_unloaded(self.budget)
        with patch.object(R,'_command',side_effect=[DISABLED,(0,b'loaded idle',b'')]),patch.object(R,'_parse_service',return_value=('LOADED_IDLE',None)):
            with self.assertRaises(H.HostObservationError): H._strict_disabled_unloaded(self.budget)

    def old_context(self, census=None, boots=None):
        return [patch.object(R,'_Budget',return_value=self.budget),patch.object(R,'_boot',side_effect=boots or ['boot','boot']),patch.object(H,'_strict_disabled_unloaded'),patch.object(H,'_root_census',return_value=census or H._RootCensus(OWN,(row(1),row(10,MAIN)),(OWN,)))]

    def test_old_owner_two_maintenance_reads_same_budget(self):
        a,b,c,d=self.old_context()
        with a as constructor,b,c as maintenance,d:
            observed=H._observe_old_owner_exclusion(deadline_monotonic_ns=1000)
        self.assertEqual(maintenance.call_args_list,[((self.budget,),{}),((self.budget,),{})])
        constructor.assert_called_once_with(1000)
        self.assertEqual(observed.deadline_monotonic_ns,1000)

    def test_old_owner_rejects_extra_root_interpreter_or_boot_change(self):
        for kwargs in [dict(census=H._RootCensus(OWN,(),(OWN,N.Instance(20,120,1)))),dict(boots=['old','new'])]:
            a,b,c,d=self.old_context(**kwargs)
            with self.subTest(kwargs=kwargs),a,b,c,d,self.assertRaises(H.HostObservationError):
                H._observe_old_owner_exclusion(deadline_monotonic_ns=1000)

    def test_old_owner_rejects_wrong_principal_and_native_failure(self):
        for uid, platform in [(501,'darwin'),(0,'linux')]:
            with patch.object(H.os,'geteuid',return_value=uid),patch.object(H.sys,'platform',platform),patch.object(R,'_Budget',return_value=self.budget):
                with self.assertRaises(H.HostObservationError): H._observe_old_owner_exclusion(deadline_monotonic_ns=1000)
        a,b,c,d=self.old_context()
        with a,b,c,d,patch.object(H,'_root_census',side_effect=OSError('nonsecret suppression')):
            with self.assertRaisesRegex(H.HostObservationError,'^RECOVERY_HOST_OBSERVATION_UNAVAILABLE$'):
                H._observe_old_owner_exclusion(deadline_monotonic_ns=1000)

    def test_installer_bounded_readback_preserves_one_endpoint(self):
        label=R._SPECS[-1].label
        with patch.object(R,'_Budget',return_value=self.budget) as constructor,patch.object(R,'_command',side_effect=[DISABLED,(0,b'loaded',b''),DISABLED,absent()]) as command,patch.object(H,'time',S(sleep=Mock())) as clock:
            H._wait_installer_unloaded(label,deadline_monotonic_ns=1000)
            constructor.assert_called_once_with(1000)
            self.assertEqual(command.call_count,4)
            clock.sleep.assert_called_once_with(.1)
            self.assertTrue(all(x.args[-1] is self.budget for x in command.call_args_list))

    def test_installer_nonzero_is_not_absence_and_idle_stays_loaded(self):
        label=R._SPECS[0].label
        for reply in [(1,b'',b'no permission'),(113,b'',b'not the exact label')]:
            with patch.object(R,'_Budget',return_value=self.budget),patch.object(R,'_command',return_value=reply) as command:
                with self.assertRaises(H.HostObservationError): H._wait_installer_unloaded(label,deadline_monotonic_ns=1000)
                self.assertEqual(command.call_count,1)
        with patch.object(R,'_Budget',return_value=self.budget),patch.object(R,'_command',return_value=(0,b'idle',b'')) as command,patch.object(H,'time',S(sleep=Mock())):
            with self.assertRaisesRegex(H.HostObservationError,'STILL_LOADED'): H._wait_installer_unloaded(label,deadline_monotonic_ns=1000)
            self.assertEqual(command.call_count,5)

    def test_installer_backup_is_probe_only_and_gateway_cannot_be_selected(self):
        with patch.object(R,'_Budget',return_value=self.budget),patch.object(R,'_command',return_value=absent('com.mastermind.executive.backup')):
            H._wait_installer_unloaded('com.mastermind.executive.backup',deadline_monotonic_ns=1000)
        with self.assertRaises(H.HostObservationError): H._wait_installer_unloaded(R._SPECS[3].label,deadline_monotonic_ns=1000)
        self.assertEqual(len(R._SPECS),5)

    def test_installer_deadline_failure_cannot_refresh_budget(self):
        budget=Budget(); budget.remaining=Mock(side_effect=R.ReleaseObservationError('DEADLINE'))
        with patch.object(R,'_Budget',return_value=budget) as constructor,patch.object(R,'_command',return_value=(0,b'idle',b'')):
            with self.assertRaises(H.HostObservationError): H._wait_installer_unloaded(R._SPECS[0].label,deadline_monotonic_ns=1000)
            constructor.assert_called_once_with(1000)

    def whole(self, boot='boot', state='UNLOADED', roles=None):
        return S(boot_id=boot,roles=tuple(S(role=r,state=state) for r in (roles or ('control','worker','relay','gateway','broker'))))
    def old(self, boot='boot', observer=OWN):
        return S(boot_id=boot,census=S(observer=observer))

    def test_whole_content_is_sandwiched_and_same_absolute_endpoint(self):
        calls=[]
        def old(**kw): calls.append(('old',kw)); return self.old()
        def whole(**kw): calls.append(('whole',kw)); return self.whole()
        with patch.object(R,'_Budget',return_value=self.budget),patch.object(H,'_observe_old_owner_exclusion',side_effect=old),patch.object(R,'_observe_release',side_effect=whole):
            result=H._observe_whole_content_before_bootstrap(deadline_monotonic_ns=1000)
        self.assertEqual(calls,[(x,{'deadline_monotonic_ns':1000}) for x in ('old','whole','old')])
        self.assertEqual(result.whole_release.roles[-1].state,'UNLOADED')

    def test_whole_content_refuses_mixed_release_and_boot_role_self_drift(self):
        for whole, old in [(self.whole(boot='new'),[self.old()]*2),(self.whole(state='LOADED_IDLE'),[self.old()]*2),(self.whole(roles=('control','broker')),[self.old()]*2),(self.whole(),[self.old(),self.old(observer=N.Instance(10,999,1))])]:
            with patch.object(R,'_Budget',return_value=self.budget),patch.object(H,'_observe_old_owner_exclusion',side_effect=old),patch.object(R,'_observe_release',return_value=whole):
                with self.assertRaises(H.HostObservationError): H._observe_whole_content_before_bootstrap(deadline_monotonic_ns=1000)
        with patch.object(R,'_Budget',return_value=self.budget),patch.object(H,'_observe_old_owner_exclusion',return_value=self.old()),patch.object(R,'_observe_release',side_effect=R.ReleaseObservationError('MIXED_RELEASE')):
            with self.assertRaises(R.ReleaseObservationError): H._observe_whole_content_before_bootstrap(deadline_monotonic_ns=1000)

    def test_whole_content_outer_budget_detects_between_reader_rollback(self):
        ticks = iter([10,11,12,13,9])
        with patch.object(R,'time',S(monotonic_ns=lambda:next(ticks))),patch.object(H,'_observe_old_owner_exclusion',return_value=self.old()) as old,patch.object(R,'_observe_release',return_value=self.whole()) as whole:
            with self.assertRaisesRegex(R.ReleaseObservationError,'CLOCK_ROLLBACK'):
                H._observe_whole_content_before_bootstrap(deadline_monotonic_ns=1000)
            old.assert_called_once()
            whole.assert_not_called()

class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.budget=Budget(10**18)
        self.stdout=Mock(); self.stdout.fileno.return_value=4
        self.stderr=Mock(); self.stderr.fileno.return_value=5
        self.process=Mock(pid=90,stdout=self.stdout,stderr=self.stderr)
        self.process.wait.return_value=0; self.process.poll.return_value=0
        self.selector=Mock(); self.selector.get_map.return_value={}
        self.popen=Mock(return_value=self.process)
        self.patchers=[patch.object(R,'subprocess',S(Popen=self.popen,DEVNULL=-3,PIPE=-1)),patch.object(R,'selectors',S(DefaultSelector=lambda:self.selector,EVENT_READ=1)),patch.object(R,'os',S(set_blocking=Mock(),read=Mock())),patch.object(R,'time',S(monotonic_ns=lambda:100))]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)

    def test_owned_pid_return_waits_reaps_and_closes(self):
        self.assertEqual(R._command(R._ROOT_PID_UID_ARGV,self.budget,include_owned_inventory_pid=True),(0,b'',b'',90))
        self.assertEqual(self.process.wait.call_count,2)
        self.stdout.close.assert_called_once(); self.stderr.close.assert_called_once(); self.selector.close.assert_called_once()
        self.popen.assert_called_once_with(R._ROOT_PID_UID_ARGV,stdin=-3,stdout=-1,stderr=-1,env=PEER._LAUNCHD_ENVIRONMENT,close_fds=True)

    def test_ordinary_command_result_unchanged(self):
        self.assertEqual(R._command(R._PRINT_DISABLED_ARGV,self.budget),(0,b'',b''))

    def test_pid_metadata_refused_before_spawn_for_other_commands(self):
        for argv, flag in [(R._PRINT_DISABLED_ARGV,True),(R._ROOT_PID_UID_ARGV,1),(('/bin/sh',),False)]:
            with self.subTest(argv=argv,flag=flag),self.assertRaises(R.ReleaseObservationError): R._command(argv,self.budget,include_owned_inventory_pid=flag)
        self.popen.assert_not_called()

    def test_any_cleanup_failure_prevents_pid_return(self):
        for subject in (self.stdout.close,self.stderr.close,self.selector.close):
            subject.side_effect=OSError('cleanup failure')
            with self.subTest(subject=subject),self.assertRaises(OSError): R._command(R._ROOT_PID_UID_ARGV,self.budget,include_owned_inventory_pid=True)
            subject.side_effect=None
        self.process.wait.side_effect=[0,TimeoutError('unreaped')]
        with self.assertRaises(TimeoutError): R._command(R._ROOT_PID_UID_ARGV,self.budget,include_owned_inventory_pid=True)

    def test_timeout_kills_only_owned_child_and_never_returns_exemption(self):
        self.selector.get_map.return_value={4:'open'}
        self.process.poll.return_value=None
        ticks=iter([100,4_000_000_100])
        with patch.object(R,'time',S(monotonic_ns=lambda:next(ticks))):
            with self.assertRaisesRegex(R.ReleaseObservationError,'TIMEOUT'): R._command(R._ROOT_PID_UID_ARGV,self.budget,include_owned_inventory_pid=True)
        self.process.kill.assert_called_once(); self.process.wait.assert_called_once_with(timeout=.5)

    def test_real_budget_is_absolute_and_clock_violation_sticky(self):
        with patch.object(R,'time',S(monotonic_ns=Mock(side_effect=[10,11,9,12]))):
            b=R._Budget(100)
            with self.assertRaisesRegex(R.ReleaseObservationError,'CLOCK_ROLLBACK'): b.check(force=True)
            with self.assertRaisesRegex(R.ReleaseObservationError,'CLOCK_ROLLBACK'): b.check(force=True)
        with patch.object(R,'time',S(monotonic_ns=Mock(side_effect=[10,11,100]))):
            b=R._Budget(100)
            with self.assertRaisesRegex(R.ReleaseObservationError,'DEADLINE_EXCEEDED'): b.remaining()

class ListenerTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((ROOT/'control_plane/executive_privileged_broker.py').read_text())
        selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_validate_adopted_listener','activate_launchd_socket')]
        self.listener=Mock(family=socket_constants.AF_UNIX)
        self.listener.getsockopt.return_value=socket_constants.SOCK_STREAM
        self.listener.getsockname.return_value='/var/run/mastermind-executive/privileged.sock'
        self.socket=S(socket=Mock(return_value=self.listener),AF_UNIX=socket_constants.AF_UNIX,SOCK_STREAM=socket_constants.SOCK_STREAM,SOL_SOCKET=socket_constants.SOL_SOCKET,SO_TYPE=socket_constants.SO_TYPE)
        self.values=[42]
        def activate(name,descriptors,count):
            self.array=(ctypes.c_int*len(self.values))(*self.values)
            ctypes.cast(descriptors,ctypes.POINTER(ctypes.POINTER(ctypes.c_int)))[0]=ctypes.cast(self.array,ctypes.POINTER(ctypes.c_int))
            ctypes.cast(count,ctypes.POINTER(ctypes.c_size_t))[0]=len(self.values)
            return 0
        self.lib=S(launch_activate_socket=Mock(side_effect=activate),free=Mock())
        fake_ctypes=S(**{name:getattr(ctypes,name) for name in ('c_char_p','POINTER','c_int','c_size_t','byref','c_void_p')},CDLL=Mock(return_value=self.lib))
        self.ns={'socket':self.socket,'platform':S(system=lambda:'Darwin'),'ctypes':fake_ctypes,'os':S(close=Mock()),'_LAUNCHD_SOCKET_NAME':'PrivilegedActions','BrokerTrustError':type('BrokerTrustError',(ValueError,),{})}
        # Production function bodies; annotations postponed so fake sockets need
        # no real native socket creation. Imports are deliberately not executed.
        code='from __future__ import annotations\n'+ast.unparse(ast.Module(body=selected,type_ignores=[]))
        exec(compile(code,'production_listener_functions','exec'),self.ns)

    def test_own_listener_shape_validated_before_return(self):
        order=[]
        self.listener.getsockname.side_effect=lambda:order.append('validate') or '/var/run/mastermind-executive/privileged.sock'
        self.listener.setblocking.side_effect=lambda _:order.append('blocking')
        self.assertIs(self.ns['activate_launchd_socket'](),self.listener)
        self.assertEqual(order,['validate','blocking'])
        self.lib.launch_activate_socket.assert_called_once()
        self.assertEqual(self.lib.launch_activate_socket.call_args.args[0],b'PrivilegedActions')
        self.lib.free.assert_called_once(); self.listener.close.assert_not_called()

    def test_family_type_and_address_mismatch_close_adopted_fd(self):
        for member,value in [('family',socket_constants.AF_INET),('getsockopt',socket_constants.SOCK_DGRAM),('getsockname','/other/socket')]:
            with self.subTest(member=member):
                self.listener.family=socket_constants.AF_UNIX; self.listener.getsockopt.return_value=socket_constants.SOCK_STREAM; self.listener.getsockname.return_value='/var/run/mastermind-executive/privileged.sock'
                self.listener.close.reset_mock(); self.listener.setblocking.reset_mock()
                if member=='family': self.listener.family=value
                else: getattr(self.listener,member).return_value=value
                with self.assertRaises(self.ns['BrokerTrustError']): self.ns['activate_launchd_socket']()
                self.listener.close.assert_called_once(); self.listener.setblocking.assert_not_called()

    def test_wrong_key_or_platform_cannot_activate(self):
        with self.assertRaises(self.ns['BrokerTrustError']): self.ns['activate_launchd_socket']('other')
        self.ns['platform']=S(system=lambda:'Linux')
        with self.assertRaises(self.ns['BrokerTrustError']): self.ns['activate_launchd_socket']()
        self.lib.launch_activate_socket.assert_not_called()

    def test_wrong_descriptor_count_closes_all_and_refuses(self):
        self.values=[42,43]
        with self.assertRaises(self.ns['BrokerTrustError']): self.ns['activate_launchd_socket']()
        self.assertEqual(self.ns['os'].close.call_args_list,[((42,),{}),((43,),{})])
        self.socket.socket.assert_not_called()

    def test_setblocking_failure_also_closes(self):
        self.listener.setblocking.side_effect=OSError('failure')
        with self.assertRaises(OSError): self.ns['activate_launchd_socket']()
        self.listener.close.assert_called_once()

if __name__ == '__main__': unittest.main(verbosity=2)
