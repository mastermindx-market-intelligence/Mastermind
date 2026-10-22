"""An atomic quota refresh updates the original cache through a code generation."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NativeAlias(unittest.TestCase):
    def test_atomic_cache_replace_preserves_generation_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();stable=root/'stable';stable.mkdir()
            generation=root/'generation';generation.mkdir()
            original=stable/'quota_cache.json';original.write_text('{"before":true}')
            alias=generation/'quota_cache.json';alias.symlink_to(original)
            shutil.copyfile(ROOT/'candidate/quota_remote.py',generation/'quota_remote.py')
            name='quota_runtime_alias_fixture'
            spec=importlib.util.spec_from_file_location(name,generation/'quota_remote.py')
            module=importlib.util.module_from_spec(spec);sys.modules[name]=module
            self.addCleanup(sys.modules.pop,name,None)
            spec.loader.exec_module(module)
            self.assertEqual(Path(module.CACHE_PATH),original)
            module._atomic_write(module.CACHE_PATH,{'after':True})
            self.assertTrue(alias.is_symlink())
            self.assertEqual(json.loads(original.read_text()),{'after':True})
            self.assertEqual({p.name for p in generation.iterdir() if p.name!='__pycache__'},
                             {'quota_remote.py','quota_cache.json'})

if __name__=='__main__':unittest.main()
