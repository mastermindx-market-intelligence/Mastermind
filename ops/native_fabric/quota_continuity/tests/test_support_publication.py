"""Controller manifest to actual immutable remote-support publication."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'candidate'),str(ROOT/'source')]
import support_bundle as support

class Publication(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.source=self.root/'controller'/'ext';self.source.mkdir(parents=True)
        self.stable=self.root/'remote'/'ext';self.stable.mkdir(parents=True)
        (self.stable/'active').mkdir();(self.stable.parent/'support-releases').mkdir()
        policy=json.dumps({'routing':{},'pools':{'grok':{'windows':{'weekly':{}}}}})+'\n'
        for base in (self.source.parent,self.stable.parent):
            path=base/'orch'/'fabric';path.mkdir(parents=True)
            (path/'pools.yaml').write_text(policy)
        for name in support.SOURCE_FILES:
            if name=='pools.yaml':(self.source/name).write_text(policy);continue
            src=next((p for p in (ROOT/'candidate'/name,ROOT/'source'/name) if p.is_file()),None)
            if src:shutil.copyfile(src,self.source/name)
            else:(self.source/name).write_text('# Unchanged support dependency, not executed by this fixture\n')

    def manifest(self,files):
        path=self.root/('manifest-'+str(len(files))+'.json')
        result=subprocess.run([sys.executable,str(ROOT/'candidate'/'remote_sub_helpers.py'),
            'support-meta',str(self.source),str(path),*sorted(files)],text=True,capture_output=True,check=True)
        return json.loads(path.read_text()),result.stdout.split()[0]

    def test_runtime_transfer_manifest_matches_publisher_generation(self):
        shell=(ROOT/'candidate'/'remote_sub.sh').read_text()
        names=set(re.search(r'SUPPORT_FILES=\(\n(.*?)\n\)',shell,re.S).group(1).split())
        self.assertEqual(names,support.SOURCE_FILES)
        self.assertTrue({'provider_outcome.py','quota_circuit.py','recovery_artifacts.py'}<=names)

    def test_real_manifest_publish_reuse_and_shared_state_binding(self):
        manifest,digest=self.manifest(support.SOURCE_FILES)
        published=support.publish(self.source,self.stable,manifest)
        self.assertEqual(published.parent.name,digest)
        self.assertEqual(published,support.publish(self.source,self.stable,manifest))
        self.assertEqual((published/'active').resolve(),(self.stable/'active').resolve())
        for name in ('provider_outcome.py','quota_circuit.py','recovery_artifacts.py'):
            self.assertEqual(hashlib.sha256((published/name).read_bytes()).hexdigest(),manifest[name])
            self.assertEqual((published/name).stat().st_mode & 0o777,0o555)
        self.assertEqual(published.stat().st_mode & 0o777,0o555)

    def test_historical_generation_preserved_and_arbitrary_subset_refused(self):
        old,_=self.manifest(support.PRE_QUOTA_CONTINUITY_SOURCE_FILES)
        previous=support.publish(self.source,self.stable,old)
        current,_=self.manifest(support.SOURCE_FILES)
        current_path=support.publish(self.source,self.stable,current)
        self.assertNotEqual(current_path,previous);self.assertTrue(previous.exists())
        del current['provider_outcome.py']
        with self.assertRaisesRegex(ValueError,'exactly the fixed source files'):
            support.publish(self.source,self.stable,current)

if __name__=='__main__':unittest.main()
