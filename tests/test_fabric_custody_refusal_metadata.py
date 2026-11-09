"""Already-observed refusal data only; no host, reader, or permission action."""
import ast
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

from ops.fleet_storage_cleanup import preview_install as storage
from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy


class CustodyMetadata(unittest.TestCase):
    def reject(self, *, uid_matches=True, mode=0o700, component='HOME', directory=True, required_directory=True):
        uid=os.getuid()
        observed=SimpleNamespace(st_uid=uid if uid_matches else uid+1,
                                 st_mode=(stat.S_IFDIR if directory else stat.S_IFREG)|mode)
        with self.assertRaises(storage.InstallHeld) as caught:
            policy._custody_call(component,storage._owned,observed,uid,required_directory)
        self.assertEqual(type(caught.exception),storage.InstallHeld)
        self.assertEqual(caught.exception.args,('owner_or_mode',))
        self.assertEqual(str(caught.exception),'owner_or_mode')
        return caught.exception

    def test_uid_vs_group_vs_other_are_original_stat_booleans(self):
        for kwargs,expected in [
            (dict(uid_matches=False),dict(owner_matches=False,group_writable=False,other_writable=False)),
            (dict(mode=0o720),dict(owner_matches=True,group_writable=True,other_writable=False)),
            (dict(mode=0o702),dict(owner_matches=True,group_writable=False,other_writable=True)),
        ]:
            result=policy.public_refusal(self.reject(**kwargs))
            self.assertEqual(result,{'reason':'OWNER_OR_MODE_UNQUALIFIED','custody':dict(component='HOME',**expected)})

    def test_first_failure_is_not_retagged_by_outer_component(self):
        def first():raise self.reject(mode=0o720,component='ACTIVE')
        with self.assertRaises(storage.InstallHeld) as caught:
            policy._custody_call('HOME',first)
        self.assertEqual(policy.public_refusal(caught.exception)['custody']['component'],'ACTIVE')

    def test_no_new_stat_or_observation_to_explain_rejection(self):
        with mock.patch.object(storage.os,'stat',side_effect=AssertionError('extra stat forbidden')), \
             mock.patch.object(storage.os,'lstat',side_effect=AssertionError('extra lstat forbidden')), \
             mock.patch.object(storage.os,'fstat',side_effect=AssertionError('extra fstat forbidden')):
            result=policy.public_refusal(self.reject(mode=0o720))
        self.assertTrue(result['custody']['group_writable'])

    def test_no_descendant_or_policy_read_after_home_refusal(self):
        observed=SimpleNamespace(st_uid=os.getuid(),st_mode=stat.S_IFDIR|0o720)
        def original_directory(path,uid):
            storage._owned(observed,uid,True)
            self.fail('rejection bypassed')
        with mock.patch.object(storage,'_directory',side_effect=original_directory) as opens, \
             mock.patch.object(storage,'_read',side_effect=AssertionError('descendant read forbidden')) as reads:
            with self.assertRaises(storage.InstallHeld) as caught:
                policy.operate(kind='inspect',home=Path('/inert/not-opened'),uid=os.getuid(),
                               platform='linux',account='ubuntu4',hostname='ubuntu4-MS-7E61')
        self.assertEqual(opens.call_count,1);reads.assert_not_called()
        self.assertEqual(policy.public_refusal(caught.exception)['custody']['component'],'HOME')

    def test_state_failure_stops_at_that_component_before_file_read(self):
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            home=Path(name).resolve(strict=True)
            def directory(path,uid):
                if path==home/'lanes/ext/state':
                    storage._owned(SimpleNamespace(st_uid=uid,st_mode=stat.S_IFDIR|0o720),uid,True)
                return os.open(home,os.O_RDONLY|os.O_DIRECTORY)
            with mock.patch.object(storage,'_directory',side_effect=directory) as opens, \
                 mock.patch.object(storage,'_read',side_effect=AssertionError('file read forbidden')) as reads:
                with self.assertRaises(storage.InstallHeld) as caught:
                    policy.operate(kind='inspect',home=home,uid=os.getuid(),platform='linux',
                                   account='ubuntu4',hostname='ubuntu4-MS-7E61')
            self.assertEqual(opens.call_count,5);reads.assert_not_called()
            self.assertEqual(policy.public_refusal(caught.exception)['custody']['component'],'STATE')

    def test_fixed_policy_file_refusal_is_labeled_without_content(self):
        exc=self.reject(mode=0o720,component='POLICY_FILE',directory=False,required_directory=False)
        result=policy.public_refusal(exc)
        self.assertEqual(result['custody']['component'],'POLICY_FILE')
        self.assertEqual(set(result['custody']),{'component','owner_matches','group_writable','other_writable'})
        self.assertNotIn('path',json.dumps(result));self.assertNotIn('uid',json.dumps(result))

    def test_unknown_component_or_malformed_fields_do_not_leak(self):
        for component,facts in [('private/path',(False,False,False)),('HOME',(123,False,False)),
                                ('HOME',('private',True,False)),('HOME',{'uid':'private'}),
                                ('HOME',(True,False,False))]:
            exc=storage.InstallHeld('owner_or_mode')
            exc._custody_component=component;exc._custody_predicates=facts
            result=policy.public_refusal(exc)
            self.assertEqual(result,{'reason':'OWNER_OR_MODE_UNQUALIFIED'})
            self.assertNotIn('private',json.dumps(result))

    def test_historical_exception_has_no_fabricated_custody(self):
        self.assertEqual(policy.public_refusal(storage.InstallHeld('owner_or_mode')),
                         {'reason':'OWNER_OR_MODE_UNQUALIFIED'})

    def test_foreign_exception_or_os_permission_has_no_fabricated_fields(self):
        class Foreign(storage.InstallHeld):pass
        exc=Foreign('owner_or_mode');exc._custody_component='HOME';exc._custody_predicates=(False,True,True)
        self.assertEqual(policy.public_refusal(exc),{'reason':'UNCLASSIFIED'})
        result=policy.public_refusal(PermissionError(errno.EACCES,'private'))
        self.assertEqual(result,{'reason':'OS_ACCESS_REFUSED'})

    def test_kind_only_failure_stays_refused_without_false_uid_mode_claim(self):
        result=policy.public_refusal(self.reject(directory=False))
        self.assertEqual(result,{'reason':'OWNER_OR_MODE_UNQUALIFIED'})

    def test_effect_unknown_wrapper_does_not_reinterpret_inner_refusal(self):
        inner=self.reject(mode=0o720,component='STATE')
        outer=storage.InstallHeld('install_effect_unknown_no_replay')
        outer.__cause__=inner
        self.assertEqual(policy.public_refusal(outer),{'reason':'INSTALL_EFFECT_UNKNOWN'})

    def test_success_stays_success_and_has_no_new_channel(self):
        observed=SimpleNamespace(st_uid=os.getuid(),st_mode=stat.S_IFDIR|0o700)
        self.assertIsNone(policy._custody_call('HOME',storage._owned,observed,os.getuid(),True))

    def test_legacy_exception_constructor_and_repr_unchanged(self):
        self.assertEqual(str(storage.InstallHeld()),'')
        self.assertEqual(storage.InstallHeld('a','b').args,('a','b'))
        self.assertEqual(repr(storage.InstallHeld('owner_or_mode')),"InstallHeld('owner_or_mode')")

    def test_original_owned_rejection_predicate_is_ast_exact(self):
        path='ops/fleet_storage_cleanup/preview_install.py'
        old=ast.parse(subprocess.check_output(['git','show','4fabf472c962e1ac889dd1a4ebef752afd8edc01:'+path],text=True))
        new=ast.parse(Path(path).read_text())
        find=lambda tree:next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_owned')
        self.assertEqual(ast.dump(find(old).body[0].test,include_attributes=False),
                         ast.dump(find(new).body[0].test,include_attributes=False))


if __name__=='__main__':unittest.main()
