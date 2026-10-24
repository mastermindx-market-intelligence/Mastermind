"""Real controller support-input joins; only finite local transport fixtures run.

The actual economic launch-policy command and support metadata run. The SCP
fixture checks its real local operands, then deliberately stops at policy upload;
no provider, credential, SSH session or real broker lease is used.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
import unittest

import test_commission_deadline as harness


SCP_FIXTURE = r'''
import hashlib,json,os,sys
from pathlib import Path
root=Path(os.environ['DEADLINE_FIXTURE_ROOT'])
args=[arg for arg in sys.argv[1:] if arg!='-q']
target=args[-1]
sources=[Path(arg) for arg in args[:-1]]
for source in sources:
    if not source.is_file():
        print('fixture scp: local source is not a regular file: '+str(source),file=sys.stderr)
        raise SystemExit(1)
if target.endswith('/pools.yaml'):
    assert len(sources)==1
    source=sources[0]
    raw=source.read_bytes()
    manifest=json.loads((root/'ext/state/remote_sub/offline-plain_ok.support.json').read_text())
    row={'stage':'policy_upload','source':str(source),'sha256':hashlib.sha256(raw).hexdigest(),
         'manifest_sha256':manifest['pools.yaml'],'target':target}
    with (root/'events.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
    # Explicit inert stop after observing the actual SCP operands, before
    # support publication/readiness/worker launch could be reached.
    raise SystemExit(89)
raise SystemExit(0)
'''


class SupportPolicySource(unittest.TestCase):
    def fixture(self):
        case=harness.ControllerDeadline('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        harness.write(case.bin/'scp','#!'+sys.executable+'\n'+SCP_FIXTURE,executable=True)
        return case

    def check_policy_join(self,mode,model):
        case=self.fixture()
        result=case.run_controller('plain_ok',budget=20,mode=mode,model=model,
                                   escalation_reason='offline support policy source-join regression')
        self.assertEqual(result['returncode'],89,result['stderr'])
        rows=[row for row in result['events'] if row['stage']=='policy_upload']
        self.assertEqual(len(rows),1,result)
        row=rows[0]
        policy=case.root/'orch/fabric/pools.yaml'
        self.assertEqual(Path(row['source']),case.ext/'../orch/fabric/pools.yaml')
        self.assertTrue(Path(row['source']).samefile(policy))
        self.assertEqual(row['sha256'],hashlib.sha256(policy.read_bytes()).hexdigest())
        self.assertEqual(row['sha256'],row['manifest_sha256'])
        self.assertTrue(row['target'].endswith('/offline-plain_ok.support-src/pools.yaml'))
        stages=[row['stage'] for row in result['events']]
        self.assertEqual(stages.count('acquire'),1)
        self.assertEqual(stages.count('granted'),1)
        self.assertEqual(stages.count('release'),1)
        self.assertNotIn('support_publish',stages)
        self.assertNotIn('launch',stages)
        self.assertNotIn('LAUNCH_ATTEMPT',result['stderr'])
        if mode!='minimax':self.assertIn('ECONOMIC_POLICY ',result['stderr'])

    def test_glm_economic_policy_directory_does_not_replace_policy_file(self):
        self.check_policy_join('glm','glm-5.3-flash')

    def test_qwen_economic_policy_directory_does_not_replace_policy_file(self):
        self.check_policy_join('qwen','qwen3.8-flash')

    def test_minimax_existing_policy_file_join_is_unchanged(self):
        self.check_policy_join('minimax','fixture-model')

    def test_missing_policy_file_stays_closed_before_support_upload(self):
        case=self.fixture()
        (case.root/'orch/fabric/pools.yaml').unlink()
        result=case.run_controller('plain_ok',budget=20,mode='glm',model='glm-5.3-flash',
                                   escalation_reason='offline support policy source-join regression')
        self.assertNotEqual(result['returncode'],0)
        self.assertIn('SUPPORT_HASH_FAILED',result['stderr'])
        self.assertFalse(any(row['stage'] in ('policy_upload','support_publish','launch')
                             for row in result['events']))


class CurrentGenerationClosure(unittest.TestCase):
    def test_actual_96_member_builder_uses_ordinary_verified_selection(self):
        import contextlib
        import io
        import os
        import tempfile
        from unittest import mock
        rollout=harness.ROOT/'rollout'
        sys.path.insert(0,str(rollout))
        import build_review_stage as builder
        import native_generation as generation
        import native_install as installer

        temporary=tempfile.TemporaryDirectory(prefix='support-current-generation-',dir=harness.ROOT/'tests')
        root=Path(temporary.name)
        def cleanup():
            for directory,_,_ in os.walk(root,followlinks=False):Path(directory).chmod(0o700)
            temporary.cleanup()
        self.addCleanup(cleanup)
        built=root/'built'
        with mock.patch.object(sys,'argv',['builder','--output',str(built)]),contextlib.redirect_stdout(io.StringIO()):
            builder.main()
        raw=(built/'native-manifest.json').read_bytes()
        self.assertEqual(raw,(rollout/'native-manifest.json').read_bytes())
        self.assertEqual((built/'native-source-inventory.json').read_bytes(),
                         (rollout/'native-source-inventory.json').read_bytes())
        manifest=json.loads(raw)
        self.assertEqual(len(manifest),96)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '1acdc1e09ba67e12ad0df4859e3a899c24a2f9ffe40c544d55f39eb4238da3de')
        controller=(built/'native-code-stage/ext/remote_sub.sh').read_bytes()
        self.assertEqual(controller,(harness.ROOT/'candidate/remote_sub.sh').read_bytes())
        self.assertEqual(hashlib.sha256(controller).hexdigest(),manifest['ext/remote_sub.sh'])
        # The completed historical paired transition retains its exact target.
        self.assertEqual(installer.UPGRADE_MANIFEST,
                         '6ac208bbd80f706931b11e8147a879f6e3ced6fe704cde7b9f15e1c098e37ee4')
        stable=root/'inert-kit/ext';stable.mkdir(parents=True,mode=0o700)
        release=generation.publish(built/'native-code-stage',stable,manifest)
        store=stable.parent/generation.STORE_NAME
        verified,metadata=generation.verify(store,release.name)
        self.assertEqual(verified,release)
        self.assertEqual(metadata['files'],manifest)
        self.assertIsNone(generation.current(store))
        selected=generation.select(store,release.name,None)
        self.assertEqual(selected['sequence'],1)
        self.assertEqual(generation.current(store),selected)
        with self.assertRaises(ValueError):generation.select(store,release.name,'f'*64)
        self.assertEqual(generation.current(store),selected)
        # Staged byte drift cannot be published under this reviewed manifest.
        (built/'native-code-stage/ext/remote_sub.sh').write_bytes(controller+b'\n# unqualified\n')
        with self.assertRaises(ValueError):generation.publish(built/'native-code-stage',stable,manifest)
        self.assertEqual(generation.current(store),selected)
