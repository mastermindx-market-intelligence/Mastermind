"""Read-only incumbent broker recovery against disposable local SQLite fixtures."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
CAND=ROOT/'ops/native_fabric/quota_continuity/candidate'
SOURCE=ROOT/'ops/native_fabric/quota_continuity/source'
original_path=list(sys.path)
try:
    sys.path[:0]=[str(CAND),str(SOURCE)]
    spec=importlib.util.spec_from_file_location('inert_qualification_broker',CAND/'lease_broker.py')
    broker=importlib.util.module_from_spec(spec);sys.modules[spec.name]=broker;spec.loader.exec_module(broker)
finally:
    sys.path[:]=original_path


class Quiescence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(strict=True)
        self.db=self.root/'leases.sqlite';self.lock=self.root/'leases.lock'
        self.lock.write_bytes(b'');self.lock.chmod(0o600)
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE leases (orchestrator_id TEXT,pool TEXT,host TEXT,account TEXT,state TEXT,ttl INTEGER)')
            db.execute('CREATE TABLE waiters (orchestrator_id TEXT,pool TEXT,host TEXT)')
        self.db.chmod(0o600)
        self.args=dict(orchestrator_id='original-root',pool='minimax',host='ubuntu4',db_path=str(self.db),lock_path=str(self.lock))

    def read(self,**kwargs):
        return broker.Broker.inspect_qualification_quiescence(**dict(self.args,**kwargs))

    def lease(self,state='held',root='original-root',pool='minimax',host='ubuntu4',account='account-a'):
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:
            db.execute('INSERT INTO leases VALUES(?,?,?,?,?,?)',(root,pool,host,account,state,-999))

    def test_empty_scope_is_current_quiescence_not_release_ack(self):
        before=self.db.read_bytes();files=sorted(x.name for x in self.root.iterdir())
        result=self.read()
        self.assertEqual(result['state'],'QUIESCENT_IN_SCOPE')
        self.assertFalse(result['historical_release_ack']);self.assertFalse(result['maintenance_authorized'])
        self.assertEqual(result['held_lease_count'],0)
        self.assertEqual(before,self.db.read_bytes());self.assertEqual(files,sorted(x.name for x in self.root.iterdir()))

    def test_old_ttl_is_not_gc_or_expiry(self):
        self.lease()
        self.assertEqual(self.read()['state'],'HELD_IN_SCOPE')
        self.assertEqual(self.read()['held_lease_count'],1)
        with contextlib.closing(sqlite3.connect(self.db)) as db, db:self.assertEqual(db.execute('SELECT state FROM leases').fetchone()[0],'held')

    def test_rented_other_account_is_held(self):
        self.lease('rented',account='not-the-guessed-account')
        self.assertEqual(self.read()['state'],'HELD_IN_SCOPE')
        self.assertEqual(self.read()['account_coverage'],'ALL_ACCOUNTS')

    def test_unrelated_scope_does_not_become_own_lease(self):
        self.lease(root='another-root');self.lease(pool='grok');self.lease(host='ubuntu1')
        self.assertEqual(self.read()['state'],'QUIESCENT_IN_SCOPE')

    def test_owner_terminal_states_do_not_claim_original_ack(self):
        self.lease('released');self.lease('expired')
        result=self.read();self.assertEqual(result['state'],'QUIESCENT_IN_SCOPE')
        self.assertFalse(result['historical_release_ack'])

    def test_matching_or_unknown_host_waiter_holds(self):
        for host in ['ubuntu4',None]:
            with self.subTest(host=host):
                with contextlib.closing(sqlite3.connect(self.db)) as db, db:
                    db.execute('DELETE FROM waiters');db.execute('INSERT INTO waiters VALUES(?,?,?)',('original-root','minimax',host))
                self.assertEqual(self.read()['state'],'HELD_IN_SCOPE')

    def test_unknown_lease_state_and_scope_are_unknown(self):
        self.lease('unrecognized')
        self.assertEqual(self.read()['state'],'UNKNOWN')
        for kwargs in [dict(orchestrator_id='../root'),dict(pool='minimxa'),dict(host='ubuntu0')]:
            self.assertEqual(self.read(**kwargs)['state'],'UNKNOWN')

    def test_missing_files_not_created(self):
        self.db.unlink();files=sorted(x.name for x in self.root.iterdir())
        self.assertEqual(self.read()['state'],'UNKNOWN')
        self.assertEqual(files,sorted(x.name for x in self.root.iterdir()))
        self.lock.unlink()
        self.assertEqual(self.read()['state'],'UNKNOWN');self.assertFalse(self.lock.exists())

    def test_busy_original_lock_is_unknown(self):
        import fcntl
        with self.lock.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.read()['state'],'UNKNOWN')

    def test_symlink_and_hardlink_are_not_followed(self):
        original=self.db.with_name('original.sqlite');self.db.rename(original);self.db.symlink_to(original)
        self.assertEqual(self.read()['state'],'UNKNOWN')
        self.db.unlink();os.link(original,self.db)
        self.assertEqual(self.read()['state'],'UNKNOWN')

    def test_wal_committed_held_lease_is_not_ignored(self):
        db=sqlite3.connect(self.db);self.addCleanup(db.close)
        db.execute('PRAGMA journal_mode=WAL');db.execute('INSERT INTO leases VALUES(?,?,?,?,?,?)',('original-root','minimax','ubuntu4','a','held',-999));db.commit()
        self.assertTrue(Path(str(self.db)+'-wal').exists())
        result=self.read();self.assertEqual(result['state'],'HELD_IN_SCOPE');self.assertEqual(result['held_lease_count'],1)

    def test_namespace_replacement_after_read_is_unknown(self):
        original_connect=sqlite3.connect;lock=self.lock
        class Changed(sqlite3.Connection):
            def execute(self,sql,*args,**kwargs):
                result=super().execute(sql,*args,**kwargs)
                if sql.startswith('SELECT COUNT(*) FROM waiters'):
                    lock.unlink();lock.write_bytes(b'');lock.chmod(0o600)
                return result
        def connect(*args,**kwargs):return original_connect(*args,**dict(kwargs,factory=Changed))
        with mock.patch.object(broker.sqlite3,'connect',side_effect=connect):
            self.assertEqual(self.read()['state'],'UNKNOWN')

    def test_rollback_journal_requires_owner_recovery_not_immutable_guess(self):
        journal=Path(str(self.db)+'-journal');journal.write_bytes(b'possibly hot');journal.chmod(0o600)
        before=self.db.read_bytes()
        self.assertEqual(self.read()['state'],'UNKNOWN')
        self.assertEqual(before,self.db.read_bytes());self.assertEqual(journal.read_bytes(),b'possibly hot')

    def test_live_guard_holds_original_broker_lock_and_retires(self):
        import fcntl
        with broker.Broker.qualification_maintenance_guard(**self.args) as guard:
            self.assertEqual(guard.require_current()['state'],'QUIESCENT_IN_SCOPE')
            with self.lock.open('r') as writer:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(TypeError):json.dumps(guard)
        with self.assertRaisesRegex(ValueError,'retired'):
            guard.require_current()

    def test_expired_guard_cannot_refresh_from_old_snapshot(self):
        with broker.Broker.qualification_maintenance_guard(**self.args) as guard:
            with mock.patch.object(broker.time,'monotonic',return_value=float('inf')):
                with self.assertRaisesRegex(ValueError,'expired'):
                    guard.require_current()

    def test_guard_exception_releases_only_read_lock(self):
        import fcntl
        with self.assertRaisesRegex(RuntimeError,'fixture-only'):
            with broker.Broker.qualification_maintenance_guard(**self.args):
                raise RuntimeError('fixture-only')
        with self.lock.open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_held_scope_cannot_issue_live_guard(self):
        self.lease()
        with self.assertRaisesRegex(ValueError,'not_quiescent'):
            with broker.Broker.qualification_maintenance_guard(**self.args):
                self.fail('guard issued for held scope')

    def test_replaced_guard_lock_withholds_handoff(self):
        with self.assertRaisesRegex(ValueError,'changed'):
            with broker.Broker.qualification_maintenance_guard(**self.args) as guard:
                self.lock.unlink();self.lock.write_bytes(b'');self.lock.chmod(0o600)
                guard.require_current()

    def test_guard_rejoins_held_lock_after_blocking_inspector(self):
        import fcntl
        original=broker.Broker.inspect_qualification_quiescence
        def replaced(**kwargs):
            self.lock.unlink();self.lock.write_bytes(b'');self.lock.chmod(0o600)
            result=original(**kwargs)
            with self.lock.open('r') as replacement:
                fcntl.flock(replacement,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return result
        handoff=[]
        with self.assertRaisesRegex(ValueError,'changed'):
            with broker.Broker.qualification_maintenance_guard(**self.args) as guard:
                with mock.patch.object(broker.Broker,'inspect_qualification_quiescence',side_effect=replaced):
                    guard.require_current()
                    handoff.append('unsafe action could begin before context exit')
        self.assertEqual(handoff,[])

    def test_guard_rejoins_deadline_after_blocking_inspector(self):
        clock={'now':0.0};original=broker.Broker.inspect_qualification_quiescence
        def delayed(**kwargs):
            result=original(**kwargs);clock['now']=31.0;return result
        handoff=[]
        with mock.patch.object(broker.time,'monotonic',side_effect=lambda:clock['now']):
            with self.assertRaisesRegex(ValueError,'expired'):
                with broker.Broker.qualification_maintenance_guard(**self.args) as guard:
                    with mock.patch.object(broker.Broker,'inspect_qualification_quiescence',side_effect=delayed):
                        guard.require_current()
                        handoff.append('unsafe action could begin after deadline')
        self.assertEqual(handoff,[])

    def test_cli_does_not_construct_broker_or_gc_or_write_snapshot(self):
        out=io.StringIO()
        with mock.patch.object(broker,'default_broker',side_effect=AssertionError('constructor forbidden')),mock.patch.dict(os.environ,{'POOL_BROKER_DB':str(self.db),'POOL_BROKER_LOCK':str(self.lock)}),contextlib.redirect_stdout(out):
            result=broker.main(['inspect-qualification-quiescence','--orchestrator-id','original-root','--pool','minimax','--host','ubuntu4'])
        self.assertEqual(result,0);self.assertEqual(json.loads(out.getvalue())['state'],'QUIESCENT_IN_SCOPE')


if __name__=='__main__':unittest.main()
