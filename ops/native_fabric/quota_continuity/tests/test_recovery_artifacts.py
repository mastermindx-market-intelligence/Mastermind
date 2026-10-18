"""Exercise retained state and explicit reclamation with real nonempty homes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'candidate'), str(ROOT/'source')]
import recovery_artifacts as rec
from lane_runtime import PROCESS_RECEIPT_SCHEMA

ROOT_ID = 'fabric-quota-fixture-root'
PARENT_ID = 'fabric-quota-fixture-parent'
BINDINGS = dict(root_id=ROOT_ID, parent_id=PARENT_ID, lease_id='lease-fixture',
                account='account-1', host='fixture-host', model='fixture-model')

class Recovery(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.here = self.root/'ext'; self.here.mkdir()
        self.lanes = self.here/'lanes'; self.lanes.mkdir(mode=0o755)
        self.active = self.here/'active'; self.active.mkdir(mode=0o755)
        self.run = 'fixture-run-01'

    def fixture(self, *, created_only=False):
        home = rec.create_codex_home(self.here, self.run, 'minimax', BINDINGS)
        (home/'sessions').mkdir()
        (home/'sessions'/'unfinished.jsonl').write_text('{"private":"unfinished session"}\n')
        (home/'config.toml').write_text('# private configuration\n')
        if not created_only:
            rec.record_retained(self.here, self.run, home, ROOT_ID, PARENT_ID,
                'minimax', 'fixture-model', 'lease-fixture', 'account-1', 'fixture-host', 1)
        receipt = dict(schema=PROCESS_RECEIPT_SCHEMA, label=self.run, returncode=1,
            cleanup=dict(census_proven=True, identity_verified=True, residual_count=0, status='not_needed'))
        self.process = self.lanes/(self.run+'.process.jsonl')
        self.process.write_text(json.dumps(receipt)+'\n')
        return home

    def plan(self):
        return rec.plan_reclaim(self.here, self.run, ROOT_ID, PARENT_ID)

    def reclaim(self, digest, **kwargs):
        return rec.reclaim_abandoned(self.here, self.run, ROOT_ID, PARENT_ID, digest, **kwargs)

    def test_private_index_and_named_root_binding(self):
        home = self.fixture()
        plan = self.plan()
        self.assertEqual(plan['home_inode'], home.stat().st_ino)
        self.assertEqual(plan['root_id'], ROOT_ID)
        self.assertFalse(plan['cleanup_authorized'])
        index = self.lanes/plan['index_file']
        self.assertEqual(plan['index_receipt_sha256'], hashlib.sha256(index.read_bytes()).hexdigest())
        self.assertEqual(index.stat().st_mode & 0o777, 0o600)
        self.assertEqual(home.stat().st_mode & 0o777, 0o700)
        with self.assertRaisesRegex(rec.Err, 'home_already_exists'):
            rec.create_codex_home(self.here, self.run, 'minimax', BINDINGS)

    def test_publisher_shared_links_and_created_only_signal_state(self):
        # Immutable support releases use these exact top-level shared-state links.
        linked = self.root/'release-ext'; linked.mkdir()
        (linked/'lanes').symlink_to(self.lanes, target_is_directory=True)
        (linked/'active').symlink_to(self.active, target_is_directory=True)
        self.here = linked
        home = self.fixture(created_only=True)
        plan = self.plan()
        self.assertEqual(plan['retention_state'], 'created_only')
        self.assertEqual(plan['home_path'], str(home))
        self.assertTrue(self.reclaim(plan['index_receipt_sha256'], abandon=True)['home_removed'])

    def test_wrong_root_hash_and_active_marker_refuse(self):
        self.fixture()
        with self.assertRaisesRegex(rec.Err, 'index_root_mismatch'):
            rec.plan_reclaim(self.here, self.run, 'wrong-root', PARENT_ID)
        with self.assertRaisesRegex(rec.Err, 'index_receipt_hash_mismatch'):
            self.reclaim('0'*64, abandon=True)
        (self.active/self.run).write_text('active')
        with self.assertRaisesRegex(rec.Err, 'active_marker_present'):
            self.plan()

    def test_changed_home_inode_and_symlink_refuse(self):
        home = self.fixture()
        original = home.with_name('original-home')
        home.rename(original)
        home.mkdir(mode=0o700)
        with self.assertRaisesRegex(rec.Err, 'index_home_identity_mismatch'):
            self.plan()
        home.rmdir(); home.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(rec.Err, 'home_is_symlink'):
            self.plan()
        self.assertTrue((original/'sessions'/'unfinished.jsonl').exists())

    def test_unproven_cleanup_or_wrong_process_refuses(self):
        self.fixture()
        value = json.loads(self.process.read_text())
        value['label'] = 'foreign-run'; self.process.write_text(json.dumps(value)+'\n')
        with self.assertRaisesRegex(rec.Err, 'process_receipt_binding_invalid'):
            self.plan()
        value['label'] = self.run; value['cleanup']['census_proven'] = False
        self.process.write_text(json.dumps(value)+'\n')
        with self.assertRaisesRegex(rec.Err, 'process_receipt_cleanup_unproven'):
            self.plan()

    def test_explicit_abandonment_and_reviewed_index_required(self):
        home = self.fixture(); digest = self.plan()['index_receipt_sha256']
        with self.assertRaisesRegex(rec.Err, 'abandon_required'):
            self.reclaim(digest)
        with self.assertRaisesRegex(rec.Err, 'index_receipt_hash_required'):
            self.reclaim(None, abandon=True)
        self.assertTrue(home.exists())
        self.assertFalse((self.lanes/(self.run+rec.INT)).exists())

    def test_nonempty_home_reclaimed_preserving_other_files_and_receipts(self):
        home = self.fixture()
        outside = self.root/'unrelated'; outside.mkdir()
        sentinel = outside/'keep'; sentinel.write_text('unrelated state')
        (home/'unrelated-link').symlink_to(outside, target_is_directory=True)
        digest = self.plan()['index_receipt_sha256']
        result = self.reclaim(digest, abandon=True)
        self.assertTrue(result['home_removed']); self.assertFalse(home.exists())
        self.assertEqual(sentinel.read_text(), 'unrelated state')
        intent = self.lanes/(self.run+rec.INT)
        self.assertEqual(result['intent_sha256'], hashlib.sha256(intent.read_bytes()).hexdigest())
        self.assertTrue(self.process.exists())
        self.assertTrue((self.lanes/(self.run+rec.IDX)).exists())
        with self.assertRaisesRegex(rec.Err, 'completed_marker_present'):
            self.reclaim(digest, abandon=True)

    def test_existing_intent_never_replays_cleanup(self):
        home = self.fixture()
        (self.lanes/(self.run+rec.INT)).write_text('{}')
        with self.assertRaisesRegex(rec.Err, 'intent_marker_present'):
            self.plan()
        self.assertTrue(home.exists())

    def test_cli_create_binds_identity_before_a_possible_interruption(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT/'candidate')+os.pathsep+str(ROOT/'source'),
            POOL_ORCHESTRATOR_ID=ROOT_ID, POOL_PARENT_RUN_ID=PARENT_ID,
            POOL_LEASE_ID='lease-fixture', POOL_ACCOUNT='account-1',
            LANE_REMOTE_HOST='fixture-host', POOL_RECOVERY_MODEL='fixture-model')
        result = subprocess.run([sys.executable, str(ROOT/'candidate'/'recovery_artifacts.py'),
            'create', str(self.here), self.run, 'glm'], env=env, capture_output=True, text=True, check=True)
        home = Path(result.stdout.strip())
        self.assertTrue(home.is_dir())
        value = json.loads((self.lanes/(self.run+'.session-created.json')).read_text())
        self.assertEqual(value['root_id'], ROOT_ID)
        self.assertEqual(value['home_inode'], home.stat().st_ino)

if __name__ == '__main__':
    unittest.main()
