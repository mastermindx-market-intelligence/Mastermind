import importlib.util
from pathlib import Path
import unittest
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
    def test_ledger_model_is_47(self):
        source = (HERE/'pool_ledger.py').read_text()
        self.assertIn('"grok": "grok-4.7"',source)
    def test_both_grok_models_are_accepted(self):
        remote = load('native_remote')
        for name in ('grok-4.6','grok-4.7'):
            with self.subTest(model=name):
                args=remote.command('grok',name,'test','/tmp',validated=True)
                self.assertEqual(args[args.index('-m')+1],name)
        with self.assertRaises(ValueError):
            remote.command('grok','grok-4.7-unknown','test','/tmp',validated=True)
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
