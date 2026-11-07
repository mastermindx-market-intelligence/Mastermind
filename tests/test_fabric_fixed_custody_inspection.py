"""Distinct metadata action on disposable directories; never host inspection."""
import ast
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy


class FixedCustodyInspection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        for path in ['lanes/ext/active', 'lanes/ext/state', 'lanes/orch/fabric']:
            (self.home/path).mkdir(parents=True, mode=0o700)
        self.active = self.home/'lanes/ext/active'
        self.lock = self.active/'.admission.lock'
        self.lock.write_bytes(b''); self.lock.chmod(0o600)
        self.file = self.home/'lanes/orch/fabric/pools.yaml'
        self.prior = self.home/'lanes/ext/state'/policy.RECORD
        self.scope = dict(home=self.home, uid=os.getuid(), platform='linux',
                          account='ubuntu4', hostname='ubuntu4-MS-7E61')

    def call(self):
        return policy.inspect_custody(**self.scope)

    def no_contents(self):
        original = os.open
        def only_directories_and_lock(path, flags, *args, **kwargs):
            if not flags & os.O_DIRECTORY and path != '.admission.lock':
                self.fail('content descriptor opened')
            return original(path, flags, *args, **kwargs)
        return mock.patch.object(os, 'open', side_effect=only_directories_and_lock)

    def test_qualified_files_no_content_opens_reads_hashes_or_original_inspect(self):
        self.file.write_bytes(b'PRIVATE policy')
        self.prior.write_bytes(b'PRIVATE receipt')
        with self.no_contents(), \
             mock.patch.object(policy.storage, '_read', side_effect=AssertionError('body read')), \
             mock.patch.object(os, 'read', side_effect=AssertionError('read')), \
             mock.patch.object(policy, 'operate', side_effect=AssertionError('original inspector')), \
             mock.patch.object(policy, '_sha', side_effect=AssertionError('preimage hash')):
            result = self.call()
        self.assertEqual(len(result['components']), 9)
        self.assertTrue(all(x['state']=='QUALIFIED' for x in result['components']))
        self.assertFalse(result['maintenance_authorized'])
        self.assertNotIn('PRIVATE', json.dumps(result)); self.assertNotIn('preimage', result)

    def test_absent_fixed_files_are_metadata_only(self):
        with self.no_contents(), mock.patch.object(policy.storage, '_read', side_effect=AssertionError('read')):
            result = self.call()
        self.assertEqual(result['components'][-2:], [dict(component='POLICY_FILE',state='ABSENT'),
                                                   dict(component='PRIOR_INSTALL_RECORD',state='ABSENT')])

    def test_home_refusal_stops_before_descendant_and_content_access(self):
        self.home.chmod(0o720)
        original = policy.storage._directory
        with self.no_contents(), mock.patch.object(policy.storage, '_read', side_effect=AssertionError('read')), \
             mock.patch.object(policy.storage, '_directory', wraps=original) as directories:
            with self.assertRaises(policy.storage.InstallHeld) as caught:
                self.call()
        self.assertEqual(directories.call_count,1)
        self.assertEqual(policy.public_refusal(caught.exception),dict(reason='OWNER_OR_MODE_UNQUALIFIED',
                         custody=dict(component='HOME',owner_matches=True,group_writable=True,other_writable=False)))

    def test_state_refusal_never_visits_orch_or_files(self):
        (self.home/'lanes/ext/state').chmod(0o702)
        original = policy.storage._directory
        with self.no_contents(), mock.patch.object(policy.storage,'_directory',wraps=original) as directories:
            with self.assertRaises(policy.storage.InstallHeld) as caught:self.call()
        self.assertEqual(directories.call_count,5)
        self.assertEqual(policy.public_refusal(caught.exception)['custody']['component'],'STATE')

    def test_policy_file_refusal_does_not_stat_receipt(self):
        self.file.write_bytes(b'private');self.file.chmod(0o620)
        original=os.stat
        def observe(path,*args,**kw):
            if path==policy.RECORD:self.fail('later fixed component visited')
            return original(path,*args,**kw)
        with self.no_contents(),mock.patch.object(os,'stat',side_effect=observe):
            with self.assertRaises(policy.storage.InstallHeld) as caught:self.call()
        self.assertEqual(policy.public_refusal(caught.exception)['custody']['component'],'POLICY_FILE')

    def test_symlink_and_hardlink_file_refused_without_content_open(self):
        outside=self.home/'outside';outside.write_bytes(b'private')
        for kind in ['symlink','hardlink']:
            if kind=='symlink':self.file.symlink_to(outside)
            else:os.link(outside,self.file)
            with self.subTest(kind=kind),self.no_contents(),self.assertRaises(policy.storage.InstallHeld):self.call()
            self.file.unlink()

    def test_active_marker_and_busy_lock_refuse(self):
        (self.active/'unknown').write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'active_or_unknown_marker'):self.call()
        (self.active/'unknown').unlink()
        with self.lock.open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'admission_lock_busy'):self.call()

    def test_late_marker_and_replaced_lock_withhold_success(self):
        original=os.stat
        for kind in ['marker','lock']:
            fired=[False]
            def mutate(path,*args,**kw):
                value=original(path,*args,**kw)
                if path==policy.RECORD and not fired[0]:
                    fired[0]=True
                    if kind=='marker':(self.active/'late').touch()
                    else:
                        self.lock.unlink();self.lock.write_bytes(b'');self.lock.chmod(0o600)
                        with self.lock.open('r+') as new:fcntl.flock(new,fcntl.LOCK_EX|fcntl.LOCK_NB)
                return value
            self.prior.write_bytes(b'private')
            with self.subTest(kind=kind),mock.patch.object(os,'stat',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'active_or_unknown_marker|admission_lock_changed'):self.call()
            if (self.active/'late').exists():(self.active/'late').unlink()

    def test_late_file_metadata_or_directory_replacement_withheld(self):
        self.file.write_bytes(b'private');self.prior.write_bytes(b'private')
        original=os.stat;fired=[False]
        def change(path,*args,**kw):
            value=original(path,*args,**kw)
            if path==policy.RECORD and not fired[0]:
                fired[0]=True;self.file.chmod(0o640)
            return value
        with mock.patch.object(os,'stat',side_effect=change):
            with self.assertRaisesRegex(ValueError,'file_changed'):self.call()
        fired[0]=False
        def replace(path,*args,**kw):
            value=original(path,*args,**kw)
            if path==policy.RECORD and not fired[0]:
                fired[0]=True
                state=self.prior.parent;state.rename(state.with_name('old-state'));state.mkdir(mode=0o700)
            return value
        with mock.patch.object(os,'stat',side_effect=replace):
            with self.assertRaisesRegex(ValueError,'directory_changed'):self.call()

    def final_receipt_stat_drift(self, kind):
        self.prior.write_bytes(b'private')
        original=os.stat;count=[0]
        def drift(path,*args,**kw):
            value=original(path,*args,**kw)
            if path==policy.RECORD:
                count[0]+=1
                if count[0]==2:  # Last fixed-file stat in final current(), not initial observation.
                    if kind=='marker':(self.active/'late').touch()
                    else:
                        self.lock.unlink();self.lock.write_bytes(b'');self.lock.chmod(0o600)
                        with self.lock.open('r+') as new:
                            fcntl.flock(new,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return value
        with mock.patch.object(os,'stat',side_effect=drift):
            with self.assertRaisesRegex(ValueError,'active_or_unknown_marker|admission_lock_changed'):
                self.call()
        self.assertEqual(count[0],2)

    def test_final_receipt_stat_marker_withholds_metadata(self):
        self.final_receipt_stat_drift('marker')

    def test_final_receipt_stat_acquirable_replacement_lock_withholds_metadata(self):
        self.final_receipt_stat_drift('lock')

    def test_fixed_scope_stays_closed(self):
        for field,value in [('uid',0),('account','other'),('hostname','other'),('platform','darwin')]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'fixed_host_account'):
                policy.inspect_custody(**dict(self.scope,**{field:value}))

    def test_original_inspector_ast_unchanged(self):
        name='ops/native_fabric/quota_continuity/rollout/ubuntu4_policy.py'
        old=ast.parse(subprocess.check_output(['git','show','6e947f1f777086837a752c4841c173f41016145e:'+name],text=True))
        new=ast.parse(Path(name).read_text())
        find=lambda tree:next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='operate')
        self.assertEqual(ast.dump(find(old)),ast.dump(find(new)))

    def test_transport_routes_distinct_action_only_with_existing_pins(self):
        registry=json.dumps({'ubuntu4':{'platform':'linux','ssh_alias':'mmx-ubuntu4',
                                         'hostnames':['ubuntu4-MS-7E61']}}).encode()
        ssh=b'Host mmx-ubuntu4\n HostName 192.168.8.220\n User ubuntu4\n'
        import hashlib
        sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
        plan=policy.transport_plan(SimpleNamespace(SSH=['ssh']),registry,ssh,kind='inspect-custody',
             expected_module_sha=sha(policy.__file__),expected_storage_sha=sha(policy.storage.__file__))
        self.assertFalse(plan['dispatch_authorized']);self.assertEqual(plan['timeout'],20)
        self.assertIsNone(plan['policy_sha256']);self.assertEqual(plan['argv'][-2],'mmx-ubuntu4')
        self.assertIn('p["inspect_custody"]()',plan['argv'][-1])
        self.assertNotIn('"payload"',plan['argv'][-1].split('r=json.loads(')[1].split(')\n')[0])


if __name__=='__main__':unittest.main()
