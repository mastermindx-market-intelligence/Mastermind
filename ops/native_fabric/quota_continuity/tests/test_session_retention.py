"""Exercise the complete shell wrappers with inert subprocess fixtures."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Retention(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'; self.bin.mkdir()
        self.ext = self.root / 'ext'; self.ext.mkdir()
        self.tmp = self.root / 'tmp'; self.tmp.mkdir()
        for name in ('mm_codex_exec.sh', 'glm_codex_exec.sh'):
            shutil.copy(ROOT / 'candidate' / name, self.ext / name)
        for name in ('recovery_artifacts.py','provider_outcome.py'):
            shutil.copy(ROOT / 'candidate' / name, self.ext / name)
        self.serial = 0
        for name in ('codex_glm', 'codex_minimax'):
            path = self.ext / name; path.mkdir()
            (path / 'config.toml').write_text('# inert test configuration\n')
        self.script(self.ext / 'studio_mcp_projection.sh', '#!/bin/sh\nprintf "mcp_servers={}\\n"\n')
        self.script(self.ext / 'sub.sh', '#!/bin/sh\nexit 0\n')
        (self.ext / 'codex_usage.py').write_text('import os,sys\nif os.environ.get("FAKE_USAGE_FAIL"): sys.exit(9)\nprint("{}")\n')
        # Intercept the wrapper's exact credential-reader invocation. HOME and
        # user configuration remain untouched; the real reader never executes.
        self.script(self.bin / 'python3', f'''#!{sys.executable}
import os,sys
if len(sys.argv)>2 and sys.argv[1]=='-c' and '.minimax/config.json' in sys.argv[2]:
    print('inert-fixture-value'); sys.exit(0)
os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])
''')
        self.script(self.bin / 'codex', f'''#!{sys.executable}
import os,sys,json,signal
from pathlib import Path
home=Path(os.environ['CODEX_HOME'])
Path(os.environ['FAKE_HOME_RECEIPT']).write_text(str(home))
(home/'sessions').mkdir(exist_ok=True)
(home/'sessions'/'fixture.jsonl').write_text('{{"fixture":"unfinished state"}}\\n')
args=sys.argv[1:]
last=Path(args[args.index('-o')+1])
kind=os.environ['FAKE_KIND']
if kind=='signal':
    os.kill(os.getppid(),signal.SIGTERM)
    sys.exit(1)
last.write_text({{'complete':'STATUS: COMPLETE\\n', 'blocked':'STATUS: BLOCKED\\n',
    'pong':'PONG\\n','progress':'Working on task\\n'}}.get(kind,''))
sys.exit(1 if kind=='failure' else 0)
''')
        self.prompt = self.root / 'packet.txt'; self.prompt.write_text('Inert fixture task')

    def script(self, path, text):
        path.write_text(text); path.chmod(0o700)

    def run_wrapper(self, wrapper, kind, missing=False, usage_fail=False, scoped=False):
        marker = self.root / 'home.path'
        env = {'PATH': str(self.bin) + os.pathsep + '/usr/bin:/bin',
               'TMPDIR': str(self.tmp), 'GLM_SHIM_TOKEN': 'inert-fixture',
               'MM_CODEX_SLOTTED': '1', 'GLM_CODEX_SLOTTED': '1',
               'MM_CODEX_MAX_CONTINUES': '0', 'GLM_CODEX_MAX_CONTINUES': '0',
               'FAKE_HOME_RECEIPT': str(marker), 'FAKE_KIND': kind,
               'POOL_USAGE_FILE': str(self.root / 'usage.json'), 'POOL_USAGE_RUN_ID': 'fixture'}
        if usage_fail:
            env['FAKE_USAGE_FAIL'] = '1'
        self.serial += 1
        if scoped:
            env.update(REMOTE_SUB_RUN_ID='scoped-fixture-'+str(self.serial),
                POOL_ORCHESTRATOR_ID='fixture-root', POOL_PARENT_RUN_ID='fixture-parent',
                POOL_ACCOUNT='fixture-account', POOL_LEASE_ID='fixture-lease',
                LANE_REMOTE_HOST='fixture-host')
        result = subprocess.run(['/bin/bash', str(self.ext / wrapper), str(self.root),
            'fixture-model', str(self.root / 'missing' if missing else self.prompt)],
            env=env, text=True, capture_output=True, timeout=15)
        retained = list(self.tmp.iterdir())
        self.assertNotIn('inert-fixture-value', result.stderr)
        self.assertNotIn('unfinished state', result.stderr)
        self.assertNotIn('inert test configuration', result.stderr)
        return result, retained

    def test_fabric_homes_indexed_before_and_after_interruption(self):
        for wrapper in ('mm_codex_exec.sh','glm_codex_exec.sh'):
            for kind in ('failure','progress','blocked','signal'):
                with self.subTest(wrapper=wrapper, kind=kind):
                    result, _ = self.run_wrapper(wrapper, kind, scoped=True)
                    run = 'scoped-fixture-'+str(self.serial)
                    created = json.loads((self.ext/'lanes'/(run+'.session-created.json')).read_text())
                    home = Path(created['home_path'])
                    self.assertEqual(created['root_id'],'fixture-root')
                    self.assertEqual(created['home_inode'],home.stat().st_ino)
                    self.assertTrue((home/'sessions'/'fixture.jsonl').exists())
                    if kind != 'signal':
                        index = json.loads((self.ext/'lanes'/(run+'.session-retained.json')).read_text())
                        self.assertEqual(index['command_rc'],result.returncode)
                        self.assertEqual(index['home_path'],str(home))

    def test_fabric_completed_home_removed_and_creation_receipt_preserved(self):
        result, _ = self.run_wrapper('mm_codex_exec.sh','complete',scoped=True)
        self.assertEqual(result.returncode,0,result.stderr)
        run = 'scoped-fixture-'+str(self.serial)
        created = json.loads((self.ext/'lanes'/(run+'.session-created.json')).read_text())
        self.assertFalse(Path(created['home_path']).exists())
        self.assertFalse((self.ext/'lanes'/(run+'.session-retained.json')).exists())

    def test_failed_and_incomplete_sessions_survive(self):
        for wrapper in ('mm_codex_exec.sh','glm_codex_exec.sh'):
            for kind, rc in [('failure',1),('progress',77),('blocked',0)]:
                with self.subTest(wrapper=wrapper, kind=kind):
                    before = set(self.tmp.iterdir())
                    result, retained = self.run_wrapper(wrapper, kind)
                    self.assertEqual(result.returncode, rc, result.stderr)
                    new = set(retained)-before
                    self.assertEqual(len(new),1)
                    self.assertEqual(next(iter(new)).stat().st_mode & 0o777, 0o700)
                    self.assertIn('CODEX_SESSION_RETAINED', result.stderr)

    def test_complete_success_cleans_private_home_even_if_usage_fails(self):
        for wrapper in ('mm_codex_exec.sh','glm_codex_exec.sh'):
            for kind in ('complete','pong'):
                for fail in (False,True):
                    with self.subTest(wrapper=wrapper, kind=kind, usage_fail=fail):
                        result, retained = self.run_wrapper(wrapper, kind, usage_fail=fail)
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertEqual(retained,[])

    def test_early_failure_preserves_rc_and_home(self):
        for wrapper in ('mm_codex_exec.sh','glm_codex_exec.sh'):
            before=set(self.tmp.iterdir())
            result, retained=self.run_wrapper(wrapper,'failure',missing=True)
            self.assertEqual(result.returncode,2,result.stderr)
            self.assertEqual(len(set(retained)-before),1)

    def test_signal_never_deletes_interrupted_session(self):
        for wrapper in ('mm_codex_exec.sh','glm_codex_exec.sh'):
            before=set(self.tmp.iterdir())
            result, retained=self.run_wrapper(wrapper,'signal')
            self.assertIn(result.returncode,(-signal.SIGTERM,128+signal.SIGTERM),result.stderr)
            self.assertEqual(len(set(retained)-before),1)


if __name__ == '__main__':
    unittest.main()
