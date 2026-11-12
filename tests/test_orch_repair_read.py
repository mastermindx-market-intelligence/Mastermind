"""Disposable fixed-owner receipts only; no host, SSH, Broker or runtime read.

Fixture scope/ACL metadata substitute Linux installation. They are not grants.
"""
import ast
import builtins
import contextlib
import io
import subprocess
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import unittest
from types import SimpleNamespace
from unittest import mock

from tests import test_orch_custody_repair as repair_fixture
from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy
from ops.native_fabric.quota_continuity.rollout import orch_repair_read as reader


class OriginalRepairRead(unittest.TestCase):
    def setUp(self):
        self.fixture = repair_fixture.OrchRepair()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.op = reader.ORCH_REPAIR_ORIGINAL_OPERATION
        self.state = self.fixture.state

    def prepare(self):
        return policy.repair_orch_group_write(operation_id=self.op, **self.fixture.scope)

    def read(self, **kwargs):
        return reader.read_orch_repair(operation_id=self.op, **dict(self.fixture.scope, **kwargs))

    def record(self, name):
        return self.state/name

    def rewrite(self, name, change):
        p = self.record(name)
        value = json.loads(p.read_bytes()); change(value)
        p.write_text(json.dumps(value)); p.chmod(0o600)

    def test_original_mutator_to_read_exact_receipts_without_any_write_or_policy_read(self):
        self.prepare()
        paths = sorted(self.fixture.home.rglob('*'))
        snapshot = {str(p): (p.lstat().st_ino, p.lstat().st_mode, p.read_bytes() if p.is_file() else None)
                    for p in paths}
        original_open = os.open
        def only_fixed(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if not flags & os.O_DIRECTORY:
                self.assertIn(path, ['.admission.lock', reader.ORCH_REPAIR_RECORD, reader.ORCH_REPAIR_OUTCOME])
            return original_open(path, flags, *args, **kwargs)
        with mock.patch.object(os, 'open', side_effect=only_fixed), \
             mock.patch.object(os, 'fchmod', side_effect=AssertionError('no chmod')), \
             mock.patch.object(policy.storage, '_write_new', side_effect=AssertionError('no write')), \
             mock.patch.object(policy, 'repair_orch_group_write', side_effect=AssertionError('no replay')), \
             mock.patch.object(policy, 'operate', side_effect=AssertionError('no policy')):
            result = self.read()
        self.assertEqual(result['state'], 'VERIFIED')
        self.assertEqual(result['reason'], 'ORIGINAL_RECEIPTS_VERIFIED')
        self.assertTrue(result['current_postimage_qualified'])
        self.assertFalse(result['replay']); self.assertFalse(result['retry_authorized'])
        self.assertFalse(result['lifecycle_authority'])
        self.assertEqual(result['intent_sha256'], hashlib.sha256(self.record(reader.ORCH_REPAIR_RECORD).read_bytes()).hexdigest())
        self.assertEqual(snapshot, {str(p): (p.lstat().st_ino, p.lstat().st_mode, p.read_bytes() if p.is_file() else None)
                                    for p in self.fixture.home.rglob('*')})

    def test_absence_is_unknown_not_absent_effect_or_retry_authority(self):
        value = self.read()
        self.assertEqual((value['state'], value['reason']), ('UNKNOWN', 'ORIGINAL_RECORDS_ABSENT'))
        self.assertFalse(value['retry_authorized']); self.assertFalse(value['current_postimage_qualified'])

    def test_intent_only_even_after_real_chmod_is_unknown(self):
        self.prepare(); self.record(reader.ORCH_REPAIR_OUTCOME).unlink()
        value = self.read()
        self.assertEqual((value['state'], value['reason']), ('UNKNOWN', 'ORIGINAL_INTENT_ONLY'))
        self.assertFalse(value['current_postimage_qualified'])

    def test_historical_verified_survives_later_mode_drift_but_current_qualification_does_not(self):
        self.prepare(); self.fixture.orch.chmod(0o775)
        value = self.read()
        self.assertEqual(value['state'], 'VERIFIED')
        self.assertEqual(value['current_reason'], 'RECORDED_POSTIMAGE_CHANGED')
        self.assertFalse(value['current_postimage_qualified']); self.assertFalse(value['retry_authorized'])

    def test_historical_verified_with_unknown_current_acl_is_not_new_qualification(self):
        self.prepare()
        with mock.patch.object(os, 'listxattr', side_effect=OSError('unavailable')):
            value = self.read()
        self.assertEqual(value['state'], 'VERIFIED')
        self.assertFalse(value['current_postimage_qualified'])
        self.assertEqual(value['current_reason'], 'CURRENT_ACL_UNQUALIFIED')

    def test_receipt_without_intent_foreign_id_root_and_numeric_boolean_refuse(self):
        self.prepare()
        original = {n: self.record(n).read_bytes() for n in [reader.ORCH_REPAIR_RECORD, reader.ORCH_REPAIR_OUTCOME]}
        for name, change in [(reader.ORCH_REPAIR_RECORD, lambda v:v.update(root='foreign')),
                             (reader.ORCH_REPAIR_OUTCOME, lambda v:v.update(operation_id='foreign')),
                             (reader.ORCH_REPAIR_OUTCOME, lambda v:v.update(replay=0)),
                             (reader.ORCH_REPAIR_OUTCOME, lambda v:v.update(extra=True)),
                             (reader.ORCH_REPAIR_OUTCOME, lambda v:v['postimage'].__setitem__(1, 999))]:
            with self.subTest(name=name, change=change):
                self.rewrite(name, change)
                with self.assertRaisesRegex(ValueError, 'record_unqualified'): self.read()
                self.record(name).write_bytes(original[name])
        self.record(reader.ORCH_REPAIR_RECORD).unlink()
        with self.assertRaisesRegex(ValueError, 'record_unqualified'): self.read()

    def test_malformed_duplicate_oversized_receipts_refuse(self):
        self.prepare(); p = self.record(reader.ORCH_REPAIR_RECORD)
        for raw in [b'{', b'{"state":1,"state":2}', b'{}' * 20000, b'['*1200+b']'*1200]:
            p.write_bytes(raw)
            with self.assertRaises(ValueError): self.read()

    def test_wrong_original_operation_and_scope_override_cannot_retarget_transport(self):
        for op in ['', 'foreign', self.op+'x']:
            with self.assertRaisesRegex(ValueError, 'identity'):
                reader.read_orch_repair(operation_id=op, **self.fixture.scope)
        for kw in [dict(platform='darwin'), dict(uid=0), dict(account='root'), dict(hostname='other')]:
            with self.assertRaises(ValueError): self.read(**kw)

    def test_symlink_hardlink_and_writable_receipt_refuse(self):
        self.prepare(); p = self.record(reader.ORCH_REPAIR_RECORD); saved = p.read_bytes(); p.unlink()
        p.symlink_to(self.fixture.original_policy)
        with self.assertRaises(ValueError): self.read()
        p.unlink(); p.write_bytes(saved); p.chmod(0o600)
        os.link(p, self.state/'other-link')
        with self.assertRaises(ValueError): self.read()
        (self.state/'other-link').unlink(); p.chmod(0o620)
        with self.assertRaises(ValueError): self.read()

    def test_busy_lock_unknown_active_and_foreign_directory_refuse(self):
        self.prepare()
        with self.fixture.lock.open('r') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'busy'): self.read()
        (self.fixture.active/'unclassified').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'active_or_unknown'): self.read()
        (self.fixture.active/'unclassified').unlink(); self.fixture.orch.chmod(0o777)
        with self.assertRaisesRegex(ValueError, 'preimage'): self.read()

    def test_late_receipt_replacement_and_ancestor_withdrawal_no_verdict_escape(self):
        self.prepare(); original = policy.storage._read
        for mutation in ['receipt', 'ancestor']:
            with self.subTest(mutation=mutation):
                def changed(fd, name, uid):
                    raw = original(fd, name, uid)
                    if name == reader.ORCH_REPAIR_OUTCOME:
                        if mutation == 'receipt':
                            p = self.record(name); raw2 = p.read_bytes(); p.unlink(); p.write_bytes(raw2); p.chmod(0o600)
                        else: (self.fixture.home/'lanes/ext').chmod(0o775)
                    return raw
                with mock.patch.object(policy.storage, '_read', side_effect=changed):
                    with self.assertRaises(ValueError): self.read()
                (self.fixture.home/'lanes/ext').chmod(0o700)

    def test_last_acl_observation_leaf_change_no_verified_escape(self):
        self.prepare()
        def late(fd):
            self.fixture.orch.chmod(0o775)
            return []
        with mock.patch.object(os, 'listxattr', side_effect=late):
            with self.assertRaisesRegex(ValueError, 'directory_changed'): self.read()

    def test_same_embedded_source_dispatch_with_declared_inert_scope_only(self):
        self.prepare()
        registry, config = self.fixture.public()
        sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        plan = policy.transport_plan(SimpleNamespace(SSH=['inert-ssh']), registry, config,
                    kind='read-orch-repair', operation_id=self.op,
                    expected_module_sha=sha(policy.__file__), expected_storage_sha=sha(policy.storage.__file__),
                    expected_reader_sha=sha(reader.__file__))
        code = compile(shlex.split(plan['argv'][-1])[2], '<inert-embedded-transport>', 'exec')
        original_exec = builtins.exec
        def fixture_exec(compiled, namespace, *args):
            result = original_exec(compiled, namespace, *args)
            if getattr(compiled, 'co_filename', None) == 'ubuntu4_policy.py':
                # Explicit Linux installation substitution, AFTER exact source
                # compilation. No production body or request is rewritten.
                namespace['_scope'] = lambda *ignored: policy._scope(**self.fixture.scope)
            return result
        out = io.StringIO()
        with mock.patch.object(builtins, 'exec', side_effect=fixture_exec), contextlib.redirect_stdout(out):
            original_exec(code, {})
        value = json.loads(out.getvalue())
        self.assertEqual(value['state'], 'VERIFIED')
        self.assertEqual(value['operation_id'], self.op)
        self.assertTrue(value['current_postimage_qualified'])

    def test_original_mutator_storage_driver_and_other_owners_ast_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        before = subprocess.check_output(['git', 'show',
            'c4d54b52f55cb2c536bb18824120c66ede383295:ops/native_fabric/quota_continuity/rollout/ubuntu4_policy.py'], cwd=root)
        def functions(raw):
            return {n.name:ast.dump(n, include_attributes=False) for n in ast.parse(raw).body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        old, new = functions(before), functions(Path(policy.__file__).read_bytes())
        self.assertEqual(set(old),set(new))
        for name in old.keys()-{'transport_plan','public_reason'}:
            self.assertEqual(old[name],new[name],name)
        path = 'ops/fleet_storage_cleanup/preview_install.py'
        self.assertEqual(subprocess.check_output(['git','show','c4d54b52f55cb2c536bb18824120c66ede383295:'+path],cwd=root), (root/path).read_bytes())
        path = 'ops/fleet_storage_cleanup/fleet_remote_sweep.py'
        old = ast.parse(subprocess.check_output(['git','show','c4d54b52f55cb2c536bb18824120c66ede383295:'+path],cwd=root))
        new = ast.parse((root/path).read_bytes())
        # Exactly ONE opt-in fixed-read function; the ENTIRE predecessor module
        # (generic run/SSH/main and every old function/import) remains AST exact.
        new.body = [n for n in new.body if not isinstance(n,ast.FunctionDef) or n.name != 'read_original_orch_result']
        self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(new,include_attributes=False))

    def test_closed_source_pinned_transport_and_dispatch_only_original_reader(self):
        registry, config = self.fixture.public()
        sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        args = dict(kind='read-orch-repair', operation_id=self.op,
                    expected_module_sha=sha(policy.__file__), expected_storage_sha=sha(policy.storage.__file__),
                    expected_reader_sha=sha(reader.__file__))
        driver = SimpleNamespace(SSH=['inert-ssh'])
        plan = policy.transport_plan(driver, registry, config, **args)
        self.assertEqual(plan['timeout'],20); self.assertFalse(plan['dispatch_authorized'])
        code = shlex.split(plan['argv'][-1])[2]
        tree = ast.parse(code); self.assertIn('q["read_orch_repair"]', code)
        self.assertEqual(len(ast.literal_eval(tree.body[1].value)),3)
        for change in [dict(operation_id='foreign'), dict(payload=b'x'), dict(expected_before='ABSENT'),
                       dict(original_settled=True), dict(expected_reader_sha='0'*64)]:
            with self.assertRaises(ValueError): policy.transport_plan(driver,registry,config,**dict(args,**change))
        self.assertLess(Path(policy.__file__).stat().st_size, policy.storage.LIMIT)
        self.assertLess(Path(reader.__file__).stat().st_size, policy.storage.LIMIT)


if __name__ == '__main__': unittest.main()
