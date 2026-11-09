"""Inert causal transport checks. Popen/selector/clock are substituted; NO SSH.

Original source receipts come from the unchanged mutator in disposable fixtures.
"""
import ast
import builtins
import shlex
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock
from tests import test_orch_custody_repair as fixture_module
from ops.fleet_storage_cleanup import fleet_remote_sweep as driver
from ops.native_fabric.quota_continuity.rollout import ubuntu4_policy as policy
from ops.native_fabric.quota_continuity.rollout import orch_repair_read as reader


class FixedReadTransport(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.OrchRepair(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.registry, self.config = self.fixture.public()
        sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        self.pins = dict(expected_module_sha=sha(policy.__file__), expected_storage_sha=sha(policy.storage.__file__),
                         expected_reader_sha=sha(reader.__file__), expected_driver_sha=sha(driver.__file__))
        self.plan = policy.transport_plan(driver,self.registry,self.config,kind='read-orch-repair-framed',
                       operation_id=policy.ORCH_REPAIR_ORIGINAL_OPERATION,**self.pins)
        self.context = self.plan['context']

    def frame(self, kind, result=None, context=None):
        return reader._canonical(dict(schema=reader.FRAME_SCHEMA, context=context or self.context,
                                      kind=kind,result=result))+b'\n'

    def genuine(self):
        policy.repair_orch_group_write(operation_id=policy.ORCH_REPAIR_ORIGINAL_OPERATION,**self.fixture.scope)
        out=io.StringIO()
        with mock.patch.object(reader,'_scope',side_effect=lambda *a:policy._scope(**self.fixture.scope)),contextlib.redirect_stdout(out):
            reader.stream_original_read(self.context)
        return out.getvalue().encode()

    def invoke(self, chunks, *, timeout=False):
        # No actual OS process, socket, transport, host or identity lookup.
        class Pipe:
            def fileno(self):return 987654321
            def close(self):pass
        process=SimpleNamespace(stdout=Pipe(),returncode=None)
        killed=[]
        def wait(timeout=None):
            if process.returncode is None:process.returncode=0
            return process.returncode
        def kill():killed.append(True);process.returncode=-9
        process.wait=wait;process.kill=kill;process.poll=lambda:process.returncode
        pending=list(chunks)
        class Selector:
            active=False
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def register(self,*args):self.active=True
            def unregister(self,*args):self.active=False
            def get_map(self):return {1:1} if self.active else {}
            def select(self,budget):
                assert 0 <= budget <= 20
                return [(None,None)] if pending or not timeout else []
        original=os.read
        def read(fd,size):
            if fd != 987654321:return original(fd,size)
            raw=pending.pop(0) if pending else b''
            self.assertLessEqual(len(raw),size)
            return raw
        with mock.patch.object(driver.subprocess,'Popen',return_value=process) as popen, \
             mock.patch('selectors.DefaultSelector',return_value=Selector()), \
             mock.patch.object(os,'read',side_effect=read),mock.patch.object(driver.time,'monotonic',return_value=0):
            value=driver.read_original_orch_result(self.registry,self.config,**self.pins)
        args,kw=popen.call_args
        self.assertEqual(args[0],self.plan['argv']);self.assertEqual(kw['stderr'],driver.subprocess.DEVNULL)
        self.assertEqual(kw['stdin'],driver.subprocess.DEVNULL);self.assertNotIn('env',kw)
        self.assertEqual(popen.call_count,1)
        return value,killed

    def test_actual_mutator_reader_frames_through_actual_driver_completed(self):
        raw=self.genuine();value,killed=self.invoke([raw])
        self.assertEqual(value['transport_state'],'PROCESS_RETURNED');self.assertEqual(value['phase'],'RESULT_RETAINED')
        self.assertEqual(value['result']['state'],'VERIFIED');self.assertTrue(value['result']['current_postimage_qualified'])
        self.assertFalse(killed);self.assertFalse(value['retry_authorized']);self.assertFalse(value['stderr_retained'])

    def test_actual_complete_result_before_local_timeout_is_retained_without_transport_success(self):
        raw=self.genuine();value,killed=self.invoke([raw],timeout=True)
        self.assertEqual(value['transport_state'],'TIMED_OUT');self.assertEqual(value['phase'],'RESULT_RETAINED')
        self.assertEqual(value['result']['state'],'VERIFIED');self.assertEqual(killed,[True])
        self.assertFalse(value['retry_authorized'])

    def test_timeout_with_valid_entry_and_partial_result_keeps_only_entry(self):
        raw=self.frame('READ_ENTERED')+b'{"INERT_PARTIAL_SECRET'
        value,killed=self.invoke([raw],timeout=True)
        self.assertEqual(value['transport_state'],'TIMED_OUT');self.assertEqual(value['phase'],'READ_ENTERED')
        self.assertIsNone(value['result']);self.assertNotIn('SECRET',json.dumps(value));self.assertEqual(killed,[True])

    def test_timeout_before_any_frame_stays_unobserved_not_connection_refusal(self):
        value,_=self.invoke([],timeout=True)
        self.assertEqual(value['phase'],'UNOBSERVED');self.assertEqual(value['transport_state'],'TIMED_OUT')
        self.assertIsNone(value['result']);self.assertFalse(value['retry_authorized'])

    def test_bound_connect_budget_is_ten_total_twenty_without_global_ssh_change(self):
        self.assertEqual(self.plan['timeout'],20);self.assertEqual(self.plan['connect_timeout'],10)
        self.assertEqual(driver.SSH,reader.FIXED_SSH)
        self.assertEqual(self.plan['argv'].count('ConnectTimeout=10'),1)
        self.assertNotIn('ConnectTimeout=20',self.plan['argv'])
        self.assertEqual(self.plan['argv'][:-2],[s.replace('ConnectTimeout=20','ConnectTimeout=10') for s in driver.SSH])
        self.assertFalse(self.plan['dispatch_authorized'])
        for path in [policy.__file__,reader.__file__,driver.__file__]:self.assertLess(Path(path).stat().st_size,policy.storage.LIMIT)

    def test_wrong_source_or_extra_command_or_operation_never_starts_process(self):
        with mock.patch.object(driver.subprocess,'Popen',side_effect=AssertionError('no process')) as process:
            for name in self.pins:
                with self.subTest(pin=name),self.assertRaises(ValueError):
                    driver.read_original_orch_result(self.registry,self.config,**dict(self.pins,**{name:'0'*64}))
            for extra in [dict(argv=['ssh']),dict(operation_id='foreign'),dict(timeout=40),dict(root='other')]:
                with self.assertRaises(TypeError):driver.read_original_orch_result(self.registry,self.config,**self.pins,**extra)
            self.assertEqual(process.call_count,0)

    def test_foreign_target_source_or_root_frames_never_escape(self):
        for field in ['target_sha256','root','operation_id','sources']:
            c=dict(self.context);c[field] = dict(c[field],driver='0'*64) if field=='sources' else 'foreign'
            value,_=self.invoke([self.frame('READ_ENTERED',context=c)])
            self.assertEqual(value['phase'],'UNQUALIFIED');self.assertIsNone(value['result'])
            self.assertEqual(value['transport_state'],'OUTPUT_UNQUALIFIED')

    def test_malformed_duplicate_banners_extra_frames_and_oversize_do_not_disclose(self):
        entry=self.frame('READ_ENTERED')
        for raw in [b'INERT_SECRET_BANNER\n'+entry,entry+entry,b'{"kind":1,"kind":2}\n', b'x'*(reader.FRAME_LIMIT+1)]:
            value,_=self.invoke([raw])
            self.assertEqual(value['transport_state'],'OUTPUT_UNQUALIFIED');self.assertIsNone(value['result'])
            self.assertNotIn('SECRET',json.dumps(value))

    def test_partial_after_a_complete_result_is_not_silently_accepted(self):
        raw=self.genuine()+b'INERT_EXTRA'
        value,_=self.invoke([raw],timeout=True)
        self.assertEqual(value['transport_state'],'OUTPUT_UNQUALIFIED');self.assertIsNone(value['result'])

    def test_scope_refusal_is_closed_without_claiming_read_entry(self):
        out=io.StringIO()
        with mock.patch.object(reader,'_scope',side_effect=ValueError('INERT_PRIVATE_PATH')),contextlib.redirect_stdout(out):
            reader.stream_original_read(self.context)
        value,_=self.invoke([out.getvalue().encode()])
        self.assertEqual(value['phase'],'SCOPE_REFUSED');self.assertEqual(value['result']['state'],'HELD_OR_UNKNOWN')
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertFalse(value['result']['retry_authorized'])

    def test_exact_embedded_framed_source_compiles_and_emits_genuine_read(self):
        policy.repair_orch_group_write(operation_id=policy.ORCH_REPAIR_ORIGINAL_OPERATION,**self.fixture.scope)
        code=compile(shlex.split(self.plan['argv'][-1])[2],'<inert-transport>','exec')
        original=builtins.exec
        def fixture_exec(compiled,namespace,*args):
            result=original(compiled,namespace,*args)
            if getattr(compiled,'co_filename',None)=='ubuntu4_policy.py':
                # Explicit installed-Linux fixture, AFTER exact source compilation.
                namespace['_scope']=lambda *a:policy._scope(**self.fixture.scope)
            return result
        out=io.StringIO()
        with mock.patch.object(builtins,'exec',side_effect=fixture_exec),contextlib.redirect_stdout(out):
            original(code,{})
        value=reader.transport_observation(out.getvalue().encode(),self.context,returncode=0)
        self.assertEqual(value['phase'],'RESULT_RETAINED');self.assertEqual(value['result']['state'],'VERIFIED')

    def test_foreign_refusal_text_and_verified_scope_refusal_are_rejected(self):
        for supplied in [dict(state='HELD_OR_UNKNOWN',reason='INERT_SECRET',replay=False,retry_authorized=False,lifecycle_authority=False),
                         dict(state='VERIFIED')]:
            value,_=self.invoke([self.frame('SCOPE_REFUSED',supplied)])
            self.assertEqual(value['transport_state'],'OUTPUT_UNQUALIFIED');self.assertIsNone(value['result'])
            self.assertNotIn('SECRET',json.dumps(value))

    def test_known_closed_owner_busy_reason_retained_without_raw_exception(self):
        value,_=self.invoke([self.frame('SCOPE_REFUSED',dict(state='HELD_OR_UNKNOWN',reason='OWNER_BUSY',
                           replay=False,retry_authorized=False,lifecycle_authority=False))])
        self.assertEqual(value['result']['reason'],'OWNER_BUSY')

    def test_start_failure_is_closed_no_second_process_or_secret_error(self):
        with mock.patch.object(driver.subprocess,'Popen',side_effect=OSError('INERT_SECRET')) as p:
            value=driver.read_original_orch_result(self.registry,self.config,**self.pins)
        self.assertEqual(p.call_count,1);self.assertEqual(value['transport_state'],'LOCAL_PROCESS_UNAVAILABLE')
        self.assertNotIn('SECRET',json.dumps(value));self.assertIsNone(value['result'])


if __name__=='__main__':unittest.main()
