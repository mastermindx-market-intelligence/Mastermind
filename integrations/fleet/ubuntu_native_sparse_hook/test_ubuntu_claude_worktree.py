"""Real Git / temporary HOME proof for the host-native Claude hook."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).with_name('ubuntu_claude_worktree.py')


def cmd(*args, cwd=None, env=None, check=True):
    p = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    if check and p.returncode:
        raise AssertionError(f'{args}: {p.stderr[:600]}')
    return p


class HostHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.home.mkdir(mode=0o700)
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        cmd('git', 'init', '-q', str(self.repo))
        cmd('git', 'config', 'user.name', 'Fixture', cwd=self.repo)
        cmd('git', 'config', 'user.email', 'fixture@example.invalid', cwd=self.repo)
        (self.repo / 'README.md').write_text('fixture\n')
        (self.repo / 'engine').mkdir()
        (self.repo / 'engine' / 'main.py').write_text('print(1)\n')
        (self.repo / 'data').mkdir()
        (self.repo / 'data' / 'heavy.csv').write_text('tracked evidence\n')
        (self.repo / 'config').mkdir()
        (self.repo / 'config' / 'sparse_worktree.json').write_text(json.dumps({'enabled':True,'exclude_dirs':['data']}))
        cmd('git', 'add', '.', cwd=self.repo)
        cmd('git', 'commit', '-qm', 'seed', cwd=self.repo)
        self.env=dict(os.environ,HOME=str(self.home),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        self.event={'name':'worker-a','cwd':str(self.repo),'session_id':'test-native-001'}

    def run_hook(self, event=None, env=None):
        return subprocess.run([sys.executable, str(SOURCE)], text=True,
                              input=json.dumps(self.event if event is None else event),
                              capture_output=True, env=env or self.env,timeout=20)

    def test_sparse_first_no_heavy_materialization_and_resume(self):
        p=self.run_hook()
        self.assertEqual(p.returncode,0,p.stderr)
        out=Path(p.stdout.strip())
        self.assertTrue(out.is_dir())
        self.assertTrue((out/'engine/main.py').is_file())
        self.assertFalse((out/'data').exists())
        self.assertEqual(cmd('git','-C',str(out),'config','--get','core.sparseCheckout').stdout.strip(),'true')
        self.assertEqual(cmd('git','-C',str(out),'status','--porcelain=v1').stdout.strip(),'')
        table=cmd('git','-C',str(self.repo),'worktree','list','--porcelain').stdout
        self.assertIn('worktree '+str(out),table)
        self.assertIn('locked mastermind-ubuntu-claude-native:v1:',table)
        again=self.run_hook()
        self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual(again.stdout.strip(),str(out))
        self.assertEqual(table,cmd('git','-C',str(self.repo),'worktree','list','--porcelain').stdout)

    def test_project_hook_defers_without_effect(self):
        (self.repo/'.claude').mkdir()
        (self.repo/'.claude/settings.json').write_text(json.dumps({'hooks':{'WorktreeCreate':[{'hooks':[{'type':'command','command':'python3 project.py'}]}]}}))
        p=self.run_hook()
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(p.stdout,'')
        self.assertNotIn('claude/ubuntu-',cmd('git','-C',str(self.repo),'branch','--list').stdout)

    def test_dirty_original_source_refuses_before_git_effect(self):
        (self.repo/'README.md').write_text('dirty\n')
        p=self.run_hook()
        self.assertEqual(p.returncode,1)
        self.assertIn('SOURCE_DIRTY',p.stderr)
        self.assertFalse((self.home/'.claude/worktrees/mmx-sparse').exists())

    def test_missing_session_or_name_refuses(self):
        for event in [{**self.event,'session_id':''},{**self.event,'name':' '}]:
            p=self.run_hook(event)
            self.assertNotEqual(p.returncode,0)
        self.assertNotIn('claude/ubuntu-',cmd('git','-C',str(self.repo),'branch','--list').stdout)

    def test_no_profile_materializes_regular_repositories(self):
        (self.repo/'config/sparse_worktree.json').unlink()
        cmd('git','rm','-q','config/sparse_worktree.json',cwd=self.repo)
        cmd('git','commit','-qm','remove profile',cwd=self.repo)
        p=self.run_hook()
        self.assertEqual(p.returncode,0,p.stderr)
        out=Path(p.stdout.strip())
        self.assertTrue((out/'data/heavy.csv').is_file())
        self.assertEqual(cmd('git','-C',str(out),'config','--get','core.sparseCheckout').stdout.strip(),'true')

    def test_unqualified_profile_refuses(self):
        f=self.repo/'config/sparse_worktree.json'
        f.write_text('{"enabled":false,"exclude_dirs":["data"]}')
        cmd('git','add','.',cwd=self.repo)
        cmd('git','commit','-qm','disable sparse',cwd=self.repo)
        p=self.run_hook()
        self.assertEqual(p.returncode,1)
        self.assertIn('PROFILE_DISABLED_OR_INVALID',p.stderr)

    def test_foreign_destination_preserved(self):
        common=cmd('git','-C',str(self.repo),'rev-parse','--path-format=absolute','--git-common-dir').stdout.strip()
        digest=hashlib.sha256((common+'\0'+self.event['name']+'\0'+self.event['session_id']).encode()).hexdigest()
        key=hashlib.sha256(common.encode()).hexdigest()[:16]
        dest=self.home/'.claude/worktrees/mmx-sparse'/key/('worker-a-'+digest[:16])
        dest.mkdir(parents=True)
        for parent in (self.home/'.claude', self.home/'.claude/worktrees', self.home/'.claude/worktrees/mmx-sparse', dest.parent):
            parent.chmod(0o700)
        marker=dest/'foreign.txt'
        marker.write_text('preserve')
        p=self.run_hook()
        self.assertEqual(p.returncode,1)
        self.assertIn('DESTINATION_FOREIGN_OR_UNQUALIFIED',p.stderr)
        self.assertEqual(marker.read_text(),'preserve')

    def test_group_writable_source_refused(self):
        self.repo.chmod(0o775)
        p=self.run_hook()
        self.assertEqual(p.returncode,1)
        self.assertIn('SOURCE_DIRECTORY_CUSTODY',p.stderr)
        self.assertFalse((self.home/'.claude/worktrees/mmx-sparse').exists())

    def test_existing_foreign_path_not_adopted(self):
        p=self.run_hook();self.assertEqual(p.returncode,0,p.stderr)
        target=Path(p.stdout.strip())
        (target/'engine/main.py').write_text('local work\n')
        # Same, exact session is allowed to resume even with work in progress.
        p2=self.run_hook()
        self.assertEqual(p2.returncode,0,p2.stderr)
        changed={**self.event,'session_id':'another-session'}
        p3=self.run_hook(changed)
        self.assertEqual(p3.returncode,0,p3.stderr)
        self.assertNotEqual(p2.stdout,p3.stdout)


if __name__=='__main__':
    unittest.main()
