import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import io
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "quota_continuity" / "source"))

HERE = Path(__file__).parent / 'overlay'

def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class GrokUpgrade(unittest.TestCase):
    def test_default_model_is_47(self):
        picker = load('pick')
        self.assertEqual(picker._default_model('grok'), 'grok-4.7')
    def test_legacy_ledger_fallback_unchanged(self):
        source = (HERE.parent.parent/'quota_continuity/source/pool_ledger.py').read_text()
        self.assertIn('"grok": "grok-4.6"', source)
    def test_both_grok_models_are_accepted(self):
        remote = load('native_remote')
        for name in ('grok-4.6','grok-4.7'):
            with self.subTest(model=name):
                args=remote.command('grok',name,'test','/tmp',validated=True)
                self.assertEqual(args[args.index('-m')+1],name)
        with self.assertRaises(ValueError):
            remote.command('grok','grok-4.7-unknown','test','/tmp',validated=True)
    def test_grok_pins_survive_default_and_policy_default(self):
        picker=load('pick')
        for policy_default in (None, 'grok-4.6'):
            spec={} if policy_default is None else {'default_model':policy_default}
            doc={'pools':{'grok':spec}}
            for requested in ('grok-4.6','grok-4.7'):
                with self.subTest(policy=policy_default,requested=requested):
                    actual,_=picker._selection_model('grok','review',doc,model=requested)
                    self.assertEqual(actual,requested)
            expected=policy_default or 'grok-4.7'
            self.assertEqual(picker._selection_model('grok','review',doc)[0],expected)

    def test_public_affinity_route_propagates_exact_pin(self):
        picker=load('pick')
        captured=[]
        def fake_pick(_task_class, **kwargs):
            captured.append(kwargs)
            return 'POOL=grok KEY=- MODEL='+str(kwargs.get('requested_model'))+' REASON=fixture'
        for requested in ('grok-4.6','grok-4.7'):
            with patch.object(picker,'_format_pick_host',side_effect=fake_pick), \
                 patch.object(picker,'_grok_exhausted',return_value=False):
                returned=picker.format_pick('review',pool='grok',requested_model=requested)
            self.assertIn('MODEL='+requested,returned)
            self.assertEqual(captured[-1]['requested_model'],requested)
        self.assertEqual(len(captured),2)

    def test_forced_grok_pin_reaches_model_aware_launch_guard(self):
        picker=load('pick')
        doc={'pools':{'grok':{'default_model':'grok-4.6'}}}
        gate_models=[]
        def guard(_mode,_task_class,model,**_kw):
            gate_models.append(model)
            return {'allowed':True,'reason':'fixture'}
        with patch.object(picker,'load_pools',return_value=doc), \
             patch.object(picker,'policy_allows',return_value=(True,'ok')), \
             patch.object(picker,'_needs_ok',return_value=(True,'ok')), \
             patch.object(picker,'_subject_ok',return_value=(True,'ok')), \
             patch.object(picker,'hard_filter',return_value=(True,'ok')), \
             patch.object(picker,'is_execute_class',return_value=False), \
             patch.object(picker,'launch_policy',side_effect=guard):
            for requested in ('grok-4.6','grok-4.7'):
                result=picker._format_pick('review',pool='grok',requested_model=requested)
                self.assertIn('MODEL='+requested,result)
                self.assertEqual(gate_models[-1],requested)
            refused=picker._format_pick('review',pool='cursor',requested_model='grok-4.7')
            self.assertTrue(refused.startswith('NONE reason=exact Grok Build model'))
            invalid=picker._format_pick('review',pool='grok',requested_model='grok-4.8')
            self.assertTrue(invalid.startswith('NONE reason=unknown requested_model'))

    def test_unknown_requested_model_not_echoed_in_cli_response(self):
        picker=load('pick')
        secret_input='private-password-secret-should-never-echo'
        with patch.object(picker,'load_pools',return_value={'pools':{'grok':{}}}):
            result=picker._format_pick('review',pool='grok',requested_model=secret_input)
        self.assertEqual(result,'NONE reason=unknown requested_model')
        self.assertNotIn(secret_input,result)

    def test_advisory_bailian_result_never_exposes_account_alias(self):
        picker=load('pick')
        secret='credential-label-should-not-leak'
        fake=SimpleNamespace(usable_names=lambda:[secret])
        with patch.dict(sys.modules, {'bailian_keys':fake}), \
             patch.object(picker,'_selection_model',return_value=('qwen3.8-flash','')), \
             patch.object(picker,'launch_policy',return_value={'allowed':True}), \
             patch.object(picker,'is_execute_class',return_value=False):
            result=picker._emit('bailian','fixture','review',doc={'pools':{'bailian':{}}})
        self.assertIn('POOL=bailian KEY=- MODEL=qwen3.8-flash',result)
        self.assertNotIn(secret,result)

    def test_picker_cli_emits_one_bounded_response_line(self):
        picker=load('pick')
        out=io.StringIO()
        with patch.object(picker,'load_pools',return_value={}), \
             patch.object(picker,'format_pick',
                          return_value='POOL=grok KEY=- MODEL=grok-4.6 REASON=fixture'), \
             patch('sys.stdout',out):
            picker.pick('review')
        self.assertEqual(out.getvalue(),'POOL=grok KEY=- MODEL=grok-4.6 REASON=fixture\n')

    def test_normalized_result_keeps_explicit_model(self):
        source=(HERE/'remote_sub_exec.py').read_text()
        self.assertIn("model=model, raw_bytes",source)
        self.assertIn('display_stdout, child_env, model)',source)
        self.assertNotIn("contract['model']",source)
    def test_no_cursor_model_alias_substitution(self):
        picker=(HERE/'pick.py').read_text()
        self.assertIn('cursor-grok-4.6-high',picker)
        self.assertIn('MODEL_CHANGED=true',picker)
if __name__=='__main__':unittest.main()
