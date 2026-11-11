"""Locked pre-lease handoff and real lock-wait deadline regressions."""
import fcntl
import json
import sqlite3
import time
import unittest

import test_quota_continuity as fixture


class BrokerPreleaseDeadline(unittest.TestCase):
    def setUp(self):
        self.case = fixture.BrokerCircuit(
            methodName="test_shared_allowance_blocks_aliases_but_not_healthy_pool")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.br = self.case.br

    def cool(self):
        prior = self.case.acquire(root="other-root")
        self.assertTrue(prior.ok)
        self.case.observe(prior)
        self.assertTrue(self.br.release(prior.lease_id, "other-root"))

    def acquire(self, **extra):
        return self.br.acquire("new-root", "minimax", model="fixture-model",
            host="fixture", task_class="remote-minimax", wait=0,
            capacity_handoff=True, **extra)

    def test_current_locked_capacity_cooldown_returns_without_a_lease(self):
        self.cool()
        result = self.acquire()
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "quota_cooldown")
        self.assertFalse(result.lease_id)
        self.assertEqual(result.quota_blockade["accounts"][0]["scope"], "declared:same-shared-allowance")
        with self.br._conn() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM leases WHERE orchestrator_id='new-root'").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM waiters WHERE orchestrator_id='new-root'").fetchone()[0], 0)

    def test_disabled_parked_and_malformed_accounts_never_become_quota_handoff(self):
        self.cool()
        path = self.case.root / "accounts.json"
        original = json.loads(path.read_text())
        changes = (
            lambda p: p.update(enabled=False),
            lambda p: p["accounts"][0].update(parked_until="2099-01-01T00:00:00Z"),
            lambda p: p["accounts"].append(dict(p["accounts"][0])),
        )
        for change in changes:
            with self.subTest(change=change):
                doc = json.loads(json.dumps(original))
                change(doc["providers"]["minimax"])
                path.write_text(json.dumps(doc))
                self.br._accounts_mtime = None
                result = self.acquire()
                self.assertFalse(result.ok)
                self.assertNotEqual(result.reason, "quota_cooldown")
                self.assertIsNone(result.quota_blockade)

    def test_one_independent_usable_account_prevents_all_account_refusal(self):
        self.cool()
        path = self.case.root / "accounts.json"
        doc = json.loads(path.read_text())
        doc["providers"]["minimax"]["accounts"].append({
            "name": "independent", "per_account_cap": 8, "quota_scope": "independent"})
        path.write_text(json.dumps(doc)); self.br._accounts_mtime = None
        result = self.acquire()
        self.assertTrue(result.ok)
        self.assertEqual(result.account, "independent")
        self.assertIsNone(result.quota_blockade)
        self.assertTrue(self.br.release(result.lease_id, "new-root"))

    def test_noncapacity_and_malformed_stored_rows_never_authorize_handoff(self):
        self.cool()
        with self.br._conn() as conn:
            original = dict(conn.execute("SELECT * FROM quota_cooldowns").fetchone())
        cases = [{"kind": kind} for kind in ("authentication", "billing", "permission", "unknown")]
        cases += [{"observed_at": self.case.clock[0] + 1},
                  {"until_ts": float("inf")}, {"source_run": "../unknown"}]
        for change in cases:
            with self.subTest(change=change):
                with self.br._conn() as conn:
                    values = dict(original, **change)
                    conn.execute("UPDATE quota_cooldowns SET kind=?,observed_at=?,until_ts=?,source_run=?",
                        (values["kind"], values["observed_at"], values["until_ts"], values["source_run"]))
                result = self.acquire()
                self.assertFalse(result.ok)
                self.assertNotEqual(result.reason, "quota_cooldown")
                self.assertIsNone(result.quota_blockade)
        with self.br._conn() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM leases WHERE orchestrator_id='new-root'").fetchone()[0], 0)

    def test_expired_cooldown_and_busy_probe_are_not_current_quota_refusals(self):
        self.cool()
        self.case.clock[0] += 61
        probe = self.case.acquire(pool="glm", root="probe-root")
        self.assertTrue(probe.ok)
        result = self.acquire()
        self.assertFalse(result.ok)
        self.assertNotEqual(result.reason, "quota_cooldown")
        self.assertIsNone(result.quota_blockade)
        self.assertTrue(self.br.release(probe.lease_id, "probe-root"))

    def test_original_deadline_bounds_actual_broker_file_lock(self):
        lock = open(self.br.lock_path, "a+")
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            started = time.monotonic()
            result = self.br.acquire("new-root", "minimax", host="fixture",
                model="fixture-model", task_class="remote-minimax", wait=3600,
                deadline_ns=time.monotonic_ns() + 200_000_000)
            elapsed = time.monotonic() - started
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "commission_time_exhausted")
        self.assertIsNone(result.quota_blockade)
        self.assertLess(elapsed, 1.5)
        # The ended acquire context cannot contaminate a later caller or its
        # normal release/settlement owner.
        granted = self.acquire()
        self.assertTrue(granted.ok)
        self.assertTrue(self.br.release(granted.lease_id, "new-root"))

    def test_original_deadline_bounds_actual_sqlite_writer_wait(self):
        holder = sqlite3.connect(self.br.db_path)
        holder.execute("BEGIN IMMEDIATE")
        try:
            started = time.monotonic()
            try:
                result = self.br.acquire("new-root", "minimax", host="fixture",
                    model="fixture-model", task_class="remote-minimax", wait=3600,
                    deadline_ns=time.monotonic_ns() + 200_000_000)
                self.assertFalse(result.ok)
                self.assertIsNone(result.quota_blockade)
            except sqlite3.OperationalError as exc:
                # An early SQLite busy return is an ordinary unqualified error,
                # never quota evidence. The operation still has to be bounded.
                self.assertIn(exc.sqlite_errorcode, (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED))
            elapsed = time.monotonic() - started
        finally:
            holder.rollback(); holder.close()
        self.assertLess(elapsed, 1.5)
        with self.br._conn() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM leases WHERE orchestrator_id='new-root'").fetchone()[0], 0)

    def test_expired_deadline_never_grants_a_free_account(self):
        result = self.acquire(deadline_ns=time.monotonic_ns() - 1)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "commission_time_exhausted")
        self.assertIsNone(result.quota_blockade)
        with self.br._conn() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM leases WHERE orchestrator_id='new-root'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
