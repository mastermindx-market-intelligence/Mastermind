"""Fixed-owner repair in temporary directories only; no host/SSH/policy reader."""
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy
from tests import test_fabric_qualification_quiescence as quiescence
broker = quiescence.broker

ROOT = Path(__file__).resolve().parents[1]


class OrchRepair(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        # macOS Python lacks the Linux FD xattr API. This is explicit test-only
        # metadata; the real Linux action fails closed if the API is absent.
        acl = mock.patch.object(os, "listxattr", return_value=[], create=True)
        acl.start(); self.addCleanup(acl.stop)
        for p in ['lanes/ext/active', 'lanes/ext/state', 'lanes/orch/fabric']:
            (self.home/p).mkdir(parents=True, mode=0o700)
        self.orch = self.home/'lanes/orch'
        self.active = self.home/'lanes/ext/active'
        self.state = self.home/'lanes/ext/state'
        self.lock = self.active/'.admission.lock'
        self.lock.write_bytes(b''); self.lock.chmod(0o600)
        self.orch.chmod(0o775)
        self.original_policy = self.orch/'fabric/pools.yaml'
        self.original_receipt = self.state/policy.RECORD
        self.original_policy.write_bytes(b'PRIVATE original policy')
        self.original_receipt.write_bytes(b'PRIVATE original receipt')
        self.scope = dict(home=self.home, uid=os.getuid(), platform='linux',
                          account='ubuntu4', hostname='ubuntu4-MS-7E61')

    def call(self, **kw):
        return policy.repair_orch_group_write(operation_id='original-test-repair',
                                             **dict(self.scope, **kw))

    def no_original_contents(self):
        original = os.open
        def only_fixed_metadata_and_new_records(path, flags, *a, **kw):
            if not flags & os.O_DIRECTORY and path != '.admission.lock':
                self.assertIn(path, [policy.ORCH_REPAIR_RECORD, policy.ORCH_REPAIR_OUTCOME])
                self.assertTrue(flags & os.O_EXCL and flags & os.O_CREAT)
            return original(path, flags, *a, **kw)
        return mock.patch.object(os, 'open', side_effect=only_fixed_metadata_and_new_records)

    def test_success_preserves_all_other_mode_owner_inode_and_original_bodies(self):
        before = self.orch.stat()
        with self.no_original_contents(), \
             mock.patch.object(os, 'read', side_effect=AssertionError('content read')), \
             mock.patch.object(policy.storage, '_read', side_effect=AssertionError('old body')), \
             mock.patch.object(policy, 'operate', side_effect=AssertionError('old inspector')), \
             mock.patch.object(policy, 'inspect_custody', side_effect=AssertionError('old inspection')):
            value = self.call()
        after = self.orch.stat()
        self.assertEqual(stat.S_IMODE(after.st_mode), stat.S_IMODE(before.st_mode) & ~0o020)
        self.assertEqual((after.st_uid, after.st_gid, after.st_ino), (before.st_uid, before.st_gid, before.st_ino))
        self.assertEqual(value['state'], 'VERIFIED'); self.assertFalse(value['replay'])
        self.assertEqual(self.original_policy.read_bytes(), b'PRIVATE original policy')
        self.assertEqual(self.original_receipt.read_bytes(), b'PRIVATE original receipt')
        self.assertEqual(json.loads((self.state/policy.ORCH_REPAIR_RECORD).read_text())['state'], 'INTENT')
        self.assertEqual(json.loads((self.state/policy.ORCH_REPAIR_OUTCOME).read_text())['state'], 'VERIFIED')

    def test_special_and_read_execute_bits_preserved(self):
        for mode in [0o720, 0o2775, 0o3770, 0o4775]:
            with self.subTest(mode=oct(mode)):
                for n in [policy.ORCH_REPAIR_RECORD, policy.ORCH_REPAIR_OUTCOME]:
                    (self.state/n).unlink(missing_ok=True)
                self.orch.chmod(mode); self.call()
                self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode), mode & ~0o020)

    def test_existing_owner_and_original_inspect_remain_strict(self):
        with self.assertRaisesRegex(ValueError, 'owner_or_mode'):
            policy.storage._directory(self.orch, os.getuid())
        with self.assertRaisesRegex(ValueError, 'owner_or_mode'):
            policy.inspect_custody(**self.scope)
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode), 0o775)

    def test_any_prior_repair_name_blocks_new_id_without_reading_it(self):
        for name in [policy.ORCH_REPAIR_RECORD, policy.ORCH_REPAIR_OUTCOME]:
            with self.subTest(name=name):
                (self.state/name).symlink_to(self.original_policy)
                with self.no_original_contents(), self.assertRaisesRegex(ValueError, 'prior_hold'):
                    self.call()
                (self.state/name).unlink()
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode), 0o775)

    def test_noop_other_write_foreign_uid_and_primary_gid_refused(self):
        for mode in [0o755, 0o777]:
            self.orch.chmod(mode)
            with self.assertRaisesRegex(ValueError, 'preimage'): self.call()
        self.orch.chmod(0o775)
        with mock.patch.object(policy.pwd, 'getpwuid', return_value=SimpleNamespace(pw_gid=-1)):
            with self.assertRaisesRegex(ValueError, 'preimage'): self.call()
        original=os.fstat
        def foreign(fd):
            s=original(fd)
            if (s.st_dev,s.st_ino)==(self.orch.stat().st_dev,self.orch.stat().st_ino):
                values=list(s);values[4]=s.st_uid+1;return os.stat_result(values)
            return s
        with mock.patch.object(os,'fstat',side_effect=foreign):
            with self.assertRaisesRegex(ValueError,'preimage'):self.call()
        self.assertFalse((self.state/policy.ORCH_REPAIR_RECORD).exists())

    def test_wrong_platform_account_host_and_identity_refuse(self):
        for kw in [dict(platform='darwin'), dict(account='other'), dict(hostname='other'),dict(uid=0)]:
            with self.subTest(kw=kw), self.assertRaises(ValueError): self.call(**kw)
        for identity in ['', '../bad', 'x\n', 'x'*129]:
            with self.assertRaises(ValueError): policy.repair_orch_group_write(operation_id=identity,**self.scope)

    def test_acl_or_unsupported_acl_observation_never_changes_mode(self):
        for result in [['system.posix_acl_access'], ['system.posix_acl_default']]:
            with mock.patch.object(os, 'listxattr', return_value=result):
                with self.assertRaisesRegex(ValueError, 'acl'): self.call()
        with mock.patch.object(os, 'listxattr', side_effect=OSError('unknown')):
            with self.assertRaises(OSError): self.call()
        self.assertFalse((self.state/policy.ORCH_REPAIR_RECORD).exists())

    def test_orch_or_ancestor_symlink_not_followed(self):
        original=self.home/'other';self.orch.rename(original);self.orch.symlink_to(original)
        with self.assertRaises(OSError):self.call()
        self.orch.unlink();original.rename(self.orch)
        lanes=self.home/'lanes';other=self.home/'lanes-real';lanes.rename(other);lanes.symlink_to(other)
        with self.assertRaises(OSError):self.call()
        self.assertFalse((other/'ext/state'/policy.ORCH_REPAIR_RECORD).exists())

    def test_physical_busy_unknown_active_or_lock_replacement_refuses(self):
        with self.lock.open('r') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'busy'):self.call()
        (self.active/'unknown').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'active_or_unknown'):self.call()
        (self.active/'unknown').unlink();self.lock.unlink();self.lock.symlink_to(self.original_policy)
        with self.assertRaises(OSError):self.call()
        self.assertFalse((self.state/policy.ORCH_REPAIR_RECORD).exists())

    def test_target_replacement_before_intent_withholds_without_mode_change(self):
        old=self.home/'original-orch';original=os.listxattr;count=[0]
        def swap(fd):
            count[0]+=1
            if count[0]==1:
                self.orch.rename(old);self.orch.mkdir(mode=0o775)
            return original(fd)
        with mock.patch.object(os,'listxattr',side_effect=swap):
            with self.assertRaisesRegex(ValueError,'directory_changed'):self.call()
        self.assertEqual(stat.S_IMODE(old.stat().st_mode),0o775)
        self.assertFalse((self.state/policy.ORCH_REPAIR_RECORD).exists())

    def test_physical_lock_held_during_single_fchmod(self):
        original=os.fchmod;calls=[]
        def change(fd, mode):
            with self.lock.open('r') as f:
                with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            calls.append((fd,mode));return original(fd,mode)
        with mock.patch.object(os,'fchmod',side_effect=change):self.call()
        self.assertEqual(len(calls),1)

    def test_intent_partial_failure_no_replay_even_without_chmod(self):
        original=policy.storage._write_new
        def interrupted(fd,name,raw):
            original(fd,name,raw);raise OSError('lost fsync acknowledgement')
        with mock.patch.object(policy.storage,'_write_new',side_effect=interrupted), \
             mock.patch.object(os,'fchmod',side_effect=AssertionError('must not chmod')):
            with self.assertRaisesRegex(ValueError,'effect_unknown'):self.call()
        self.assertTrue((self.state/policy.ORCH_REPAIR_RECORD).exists())
        with self.assertRaisesRegex(ValueError,'prior_hold'):self.call()

    def test_chmod_or_outcome_failure_keeps_original_intent_no_replay(self):
        original=os.fchmod
        def lost(fd,mode):original(fd,mode);raise OSError('lost response')
        with mock.patch.object(os,'fchmod',side_effect=lost):
            with self.assertRaisesRegex(ValueError,'effect_unknown'):self.call()
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode),0o755)
        # Noop preimage also refuses; no new operation can rewrite history.
        with self.assertRaises(ValueError):self.call()
        self.assertTrue((self.state/policy.ORCH_REPAIR_RECORD).exists())
        self.assertFalse((self.state/policy.ORCH_REPAIR_OUTCOME).exists())

    def test_late_namespace_marker_and_mode_change_withhold_outcome(self):
        original=os.fchmod
        def late(fd,mode):original(fd,mode);(self.active/'late').write_bytes(b'x')
        with mock.patch.object(os,'fchmod',side_effect=late):
            with self.assertRaisesRegex(ValueError,'effect_unknown'):self.call()
        self.assertFalse((self.state/policy.ORCH_REPAIR_OUTCOME).exists())

    def test_fchmod_cannot_silently_change_other_bits(self):
        original=os.fchmod
        def changed(fd,mode):return original(fd, mode & ~0o100)
        with mock.patch.object(os,'fchmod',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'effect_unknown'):self.call()
        self.assertFalse((self.state/policy.ORCH_REPAIR_OUTCOME).exists())

    def test_scope_passwd_home_not_environment_or_caller_path(self):
        with mock.patch.object(policy.pwd,'getpwuid',return_value=SimpleNamespace(pw_dir='/other',pw_name='ubuntu4')):
            with self.assertRaisesRegex(ValueError,'fixed_account_home'):
                policy.repair_orch_group_write(operation_id='x')

    def args(self):
        return dict(operation_id='fixed-one-action',expected_module_sha=hashlib.sha256(Path(policy.__file__).read_bytes()).hexdigest(),
                    expected_storage_sha=hashlib.sha256(Path(policy.storage.__file__).read_bytes()).hexdigest())

    def public(self):
        return json.dumps({'ubuntu4':{'platform':'linux','ssh_alias':'fixed-u4','hostnames':['ubuntu4-MS-7E61']}}).encode(), b'Host fixed-u4\n HostName 192.0.2.4\n User ubuntu4\n'

    def test_transport_is_one_fixed_action_without_scope_or_policy_override(self):
        registry,config=self.public();driver=SimpleNamespace(SSH=['inert-ssh'])
        plan=policy.transport_plan(driver,registry,config,kind='repair-orch-group-write',**self.args())
        self.assertEqual(plan['target']['binding']['account'],'ubuntu4');self.assertFalse(plan['dispatch_authorized'])
        self.assertEqual(plan['timeout'],20);self.assertIsNone(plan['policy_sha256'])
        for kw in [dict(payload=b'x'),dict(expected_before='ABSENT'),dict(original_settled=True)]:
            with self.assertRaises(ValueError):policy.transport_plan(driver,registry,config,kind='repair-orch-group-write',**dict(self.args(),**kw))

    def broker_fixture(self):
        fixture=quiescence.Quiescence();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.args['orchestrator_id']=policy.ORCH_REPAIR_ROOT
        original=broker.Broker.qualification_maintenance_guard
        # Actual incumbent guard and SQLite/lock, only its fixture paths substituted.
        def bound(**kw):
            self.assertEqual(kw,dict(orchestrator_id=policy.ORCH_REPAIR_ROOT,pool='minimax',host='ubuntu4'))
            return original(**dict(kw,db_path=str(fixture.db),lock_path=str(fixture.lock)))
        return fixture,mock.patch.object(broker.Broker,'qualification_maintenance_guard',side_effect=bound)

    def test_actual_incumbent_broker_guard_held_across_physical_repair(self):
        fixture,bound=self.broker_fixture();calls=[]
        def run(argv,timeout):
            with fixture.lock.open('r') as f:
                with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            calls.append(argv);return self.call()
        driver=SimpleNamespace(SSH=['inert-ssh'],run=run);registry,config=self.public()
        with mock.patch.dict(sys.modules,{'lease_broker':broker}),bound:
            value=policy.guarded_orch_repair(driver,registry,config,**self.args())
        self.assertEqual(value['state'],'VERIFIED');self.assertEqual(len(calls),1)

    def test_detached_guard_or_paths_are_not_an_API(self):
        calls=[];driver=SimpleNamespace(SSH=[],run=lambda *a:calls.append(a));registry,config=self.public()
        for extra in [dict(live_guard={}),dict(root='foreign'),dict(db_path='/tmp/other')]:
            with self.assertRaises(TypeError):policy.guarded_orch_repair(driver,registry,config,**dict(self.args(),**extra))
        self.assertFalse(calls)

    def test_held_incumbent_broker_prevents_even_transport(self):
        fixture,bound=self.broker_fixture();fixture.lease(root=policy.ORCH_REPAIR_ROOT)
        calls=[];driver=SimpleNamespace(SSH=[],run=lambda *a:calls.append(a));registry,config=self.public()
        with mock.patch.dict(sys.modules,{'lease_broker':broker}),bound:
            with self.assertRaisesRegex(ValueError,'not_quiescent'):
                policy.guarded_orch_repair(driver,registry,config,**self.args())
        self.assertFalse(calls);self.assertFalse((self.state/policy.ORCH_REPAIR_RECORD).exists())

    def test_broker_expiry_after_effect_withholds_result_without_replay(self):
        fixture,bound=self.broker_fixture();calls=[];clock=[0.0]
        def run(argv,timeout):
            calls.append(argv);result=self.call();clock[0]=31.0;return result
        driver=SimpleNamespace(SSH=['inert-ssh'],run=run);registry,config=self.public()
        with mock.patch.dict(sys.modules,{'lease_broker':broker}),bound, \
             mock.patch.object(broker.time,'monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'expired'):
                policy.guarded_orch_repair(driver,registry,config,**self.args())
        self.assertEqual(len(calls),1);self.assertTrue((self.state/policy.ORCH_REPAIR_RECORD).exists())
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode),0o755)

    def test_missing_acl_API_fails_closed_without_intent(self):
        with mock.patch.object(os,'listxattr',None):
            with self.assertRaisesRegex(ValueError,'acl'):self.call()
        self.assertFalse((self.state/policy.ORCH_REPAIR_RECORD).exists())

    def test_late_outcome_failure_keeps_completed_mode_and_original_intent(self):
        original=policy.storage._write_new
        def write(fd,name,raw):
            if name==policy.ORCH_REPAIR_OUTCOME:raise OSError('outcome write interrupted')
            return original(fd,name,raw)
        with mock.patch.object(policy.storage,'_write_new',side_effect=write):
            with self.assertRaisesRegex(ValueError,'effect_unknown'):self.call()
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode),0o755)
        self.assertTrue((self.state/policy.ORCH_REPAIR_RECORD).exists())
        self.assertFalse((self.state/policy.ORCH_REPAIR_OUTCOME).exists())

    def test_ancestor_change_after_intent_never_reaches_chmod(self):
        original=policy.storage._write_new
        def write(fd,name,raw):
            value=original(fd,name,raw)
            if name==policy.ORCH_REPAIR_RECORD:(self.home/'lanes/ext').chmod(0o775)
            return value
        with mock.patch.object(policy.storage,'_write_new',side_effect=write), \
             mock.patch.object(os,'fchmod',side_effect=AssertionError('must not chmod')):
            with self.assertRaisesRegex(ValueError,'effect_unknown'):self.call()
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode),0o775)

    def trailing_rejoin_change(self, replacement):
        original_directory=policy.storage._directory;original_write=policy.storage._write_new
        armed=[False];visits=[0];displaced=self.home/'displaced-orch'
        def write(fd,name,raw):
            result=original_write(fd,name,raw)
            if name==policy.ORCH_REPAIR_RECORD:armed[0]=True
            return result
        def directory(path,uid):
            fd=original_directory(path,uid)
            if armed[0]:
                visits[0]+=1
                # Five first-pass ancestors, then the final STATE reopen in
                # trailing directories_current(), after the earlier ORCH check.
                if visits[0]==10:
                    if replacement:
                        self.orch.rename(displaced);self.orch.mkdir();self.orch.chmod(0o770)
                    else:self.orch.chmod(0o770)
            return fd
        with mock.patch.object(policy.storage,'_write_new',side_effect=write), \
             mock.patch.object(policy.storage,'_directory',side_effect=directory), \
             mock.patch.object(os,'fchmod',wraps=os.fchmod) as chmod:
            caught=None
            try:self.call()
            except policy.storage.InstallHeld as exc:caught=exc
        chmod.assert_not_called()
        self.assertIsNotNone(caught)
        self.assertRegex(str(caught),'effect_unknown')
        self.assertEqual(visits[0],10)
        self.assertEqual(stat.S_IMODE(self.orch.stat().st_mode),0o770)
        if replacement:self.assertEqual(stat.S_IMODE(displaced.stat().st_mode),0o775)
        self.assertTrue((self.state/policy.ORCH_REPAIR_RECORD).exists())
        self.assertFalse((self.state/policy.ORCH_REPAIR_OUTCOME).exists())

    def test_trailing_ancestor_rejoin_replacement_never_reaches_fchmod(self):
        self.trailing_rejoin_change(True)

    def test_trailing_ancestor_rejoin_mode_change_never_reaches_fchmod(self):
        self.trailing_rejoin_change(False)

    def test_original_inspect_operate_and_owned_AST_unchanged(self):
        old=subprocess.check_output(['git','show','f6800ba:ops/native_fabric/quota_continuity/rollout/ubuntu4_policy.py'],cwd=ROOT).decode()
        new=Path(policy.__file__).read_text()
        def functions(s):return {n.name:ast.dump(n) for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)}
        a,b=functions(old),functions(new)
        for n in ['operate','inspect_custody','_scope']:self.assertEqual(a[n],b[n])
