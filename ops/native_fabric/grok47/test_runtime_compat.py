"""Offline worker-output and role-boundary tests for Grok 4.7 migration."""
from __future__ import annotations
import importlib.util
import ast
import hashlib
import re
from types import SimpleNamespace, ModuleType
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

OVERLAY = Path(__file__).resolve().parent / 'overlay'
SOURCE = Path(__file__).resolve().parents[1] / 'quota_continuity' / 'source'
for path in (str(SOURCE),str(OVERLAY)):
    if path not in sys.path:
        sys.path.insert(0,path)


def load(name):
    spec = importlib.util.spec_from_file_location('grok47_'+name, OVERLAY/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker_functions():
    """Compile the actual source functions without bootstrapping host controllers."""
    src = OVERLAY / 'remote_sub_exec.py'
    tree = ast.parse(src.read_text())
    selected = [n for n in tree.body if isinstance(n,ast.FunctionDef)
                and n.name in ('grok_plaintext_and_usage','grok_output_binding')]
    if len(selected)!=2:
        raise AssertionError('Grok worker producer functions missing')
    ns={'json':json,'hashlib':hashlib,'Path':Path,
        'native_remote':SimpleNamespace(IDENT=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')),
        'cleanup_receipt_is_proven':lambda _cleanup: True}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(src),'exec'),ns)
    return SimpleNamespace(**{name:ns[name] for name in ('grok_plaintext_and_usage','grok_output_binding')})


def final(raw_model):
    return {
        'text': 'VISIBLE_RESULT', 'privateReasoning': 'HIDDEN_DATA',
        'sessionId': 'session-123',
        'usage': {'input_tokens':8, 'cache_read_input_tokens':3,
                  'output_tokens':4,'total_tokens':15},
    }

class Grok47WorkerContracts(unittest.TestCase):
    def test_selector_default_stays_grok47_without_provider_effect(self):
        picker=load('pick')
        value,_=picker._selection_model('grok','integration',doc={'pools':{'grok':{}}})
        self.assertEqual(value,'grok-4.7')
        self.assertEqual(picker._default_model('grok'),'grok-4.7')

    def test_grok_output_removes_private_fields_and_preserves_model_metadata(self):
        worker=worker_functions()
        raw=json.dumps(final('grok-4.7'))
        for model in ('grok-4.6','grok-4.7'):
            with self.subTest(model=model):
                text,usage=worker.grok_plaintext_and_usage(raw,'run-xyz',model)
                self.assertEqual(text,'VISIBLE_RESULT')
                self.assertNotIn('HIDDEN_DATA',text)
                self.assertEqual(usage['served_model'],model)
                self.assertEqual((usage['input_tokens'],usage['cached_tokens'],usage['output_tokens'],usage['total_tokens']),(11,3,4,15))

    def test_reject_malformed_private_json_without_leaking_reasoning(self):
        worker=worker_functions()
        text,usage=worker.grok_plaintext_and_usage('{"privateReasoning":"secret",','run','grok-4.7')
        self.assertEqual((text,usage),('',None))

    def test_exact_requested_model_bound_in_artifact_receipt(self):
        worker=worker_functions()
        raw=json.dumps(final('grok-4.7'))
        env={'POOL_ORCHESTRATOR_ID':'root-1','POOL_PARENT_RUN_ID':'root-1',
             'REMOTE_SUB_RUN_ID':'run-1','LANE_REMOTE_HOST':'ubuntu1',
             'POOL_LEASE_ID':'lease-1','POOL_ACCOUNT':'default',
             'SUPPORT_DIGEST':'a'*64}
        contract={'root':'root-1','parent':'root-1','run_id':'run-1','support_digest':'a'*64}
        import hashlib
        payload={'schema':'mastermind.local_owned_process_receipt.v1','label':'run-1',
                 'returncode':0,'timed_out':False,'stdout_truncated':False,
                 'stderr_truncated':False,'cleanup':{},
                 'stdout_bytes':len(raw.encode()),
                 'stdout_sha256':hashlib.sha256(raw.encode()).hexdigest()}
        with tempfile.TemporaryDirectory() as td:
            receipt=Path(td)/'receipt.jsonl';receipt.write_text(json.dumps(payload)+'\n')
            with patch.dict(sys.modules, {'artifact_production':ModuleType('artifact_production')}):
                for model in ('grok-4.6','grok-4.7'):
                    binding=worker.grok_output_binding(receipt,contract,{},raw,'VISIBLE_RESULT',env,model)
                    self.assertEqual(binding['model'],model)
                    self.assertEqual(binding['run_id'],'run-1')
                    self.assertEqual(binding['normalized_bytes'],len('VISIBLE_RESULT'))

    def test_usage_validator_accepts_both_versions_not_unknown(self):
        usage={'schema':'mastermind.grok_usage.v1','status':'observed',
               'reason':'native_headless_final','session_ids':['s1'],
               'input_tokens':11,'cached_tokens':3,'output_tokens':4,'total_tokens':15,
               'source':'grok_native_headless','served_model':'grok-4.7','run_id':'run123'}
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'usage.json'
            for model,valid in [('grok-4.6',True),('grok-4.7',True),('grok-4.8',False)]:
                with self.subTest(model=model):
                    usage['served_model']=model;file.write_text(json.dumps(usage))
                    call=subprocess.run([sys.executable,str(OVERLAY/'remote_sub_helpers.py'),
                                         'validate-usage',str(file),'run123'],capture_output=True,text=True,timeout=5)
                    self.assertEqual(call.returncode==0,valid,(call.stdout,call.stderr))
                    if valid:self.assertIn('grok_native_headless',call.stdout)

    def test_cursor_grok_46_alias_does_not_inherit_47_quality_floor(self):
        picker = load('pick')
        seen = []
        def check_floor(*args, **kwargs):
            seen.append(kwargs.get('model'))
            return True
        with patch.object(picker, '_cursor_grok_quota_affinity', return_value=True), \
             patch.object(picker, '_subject_ok', return_value=(True, 'ok')), \
             patch.object(picker, 'is_execute_class', return_value=True), \
             patch.object(picker, 'floor_demotes', side_effect=check_floor):
            value = picker._format_pick('execute',pool='cursor',
                                        requested_model='cursor-grok-4.6-high')
        self.assertIn('quality floor', value)
        self.assertEqual(seen, ['grok-4.6'])

    def test_operator_model_pairs_closed(self):
        contract=load('fabric_operator_contract')
        self.assertIn(('grok','grok-4.7'),contract.ALLOWED_POOL_MODEL)
        self.assertIn(('grok','grok-4.6'),contract.ALLOWED_POOL_MODEL)
        self.assertNotIn(('grok','grok-4.8'),contract.ALLOWED_POOL_MODEL)
        self.assertNotIn(('cursor','grok-4.7'),contract.ALLOWED_POOL_MODEL)

if __name__=='__main__':unittest.main()
