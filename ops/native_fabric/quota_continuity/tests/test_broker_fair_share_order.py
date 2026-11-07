"""Real broker fairness regressions with temporary state and no provider I/O."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "source")]
sys.path.insert(0, os.path.dirname(__file__))
from _offline_boundary import acquire as _offline_acquire, release as _offline_release
import lease_broker


def setUpModule():
    _offline_acquire()


def tearDownModule():
    _offline_release()


class FairShareOrder(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.clock = [1000.0]
        accounts = {"providers": {"minimax": {
            "enabled": True, "concurrency_cap": 3,
            "accounts": [{"name": "fixture", "per_account_cap": 3}],
        }}}
        (self.root / "accounts.json").write_text(json.dumps(accounts))
        self.broker = lease_broker.Broker(
            db_path=str(self.root / "broker.sqlite"),
            lock_path=str(self.root / "broker.lock"),
            accounts_path=str(self.root / "accounts.json"),
            now_fn=lambda: self.clock[0], check_pid=False, external_gates=False,
            grok_marker=str(self.root / "absent"), this_host="fixture",
        )

    def acquire(self, root, task_class="fixture"):
        self.clock[0] += 1
        return self.broker.acquire(
            root, "minimax", model="fixture-model", host="fixture",
            task_class=task_class, ttl=1000, wait=0,
        )

    def filled_pool(self):
        leases = [self.acquire(root) for root in ("A", "A", "B")]
        self.assertTrue(all(row.ok for row in leases))
        return leases

    def rows(self, table):
        conn = self.broker._conn()
        try:
            return [dict(row) for row in conn.execute("SELECT * FROM " + table)]
        finally:
            conn.close()

    def test_below_share_root_uses_free_slot_behind_ineligible_oldest(self):
        a1, a2, _ = self.filled_pool()
        self.assertEqual(self.acquire("A").reason, "cap_full")
        self.assertEqual(self.acquire("C").reason, "cap_full")
        self.broker.release(a2.lease_id, "A")
        self.assertEqual(self.acquire("A").reason, "lending_blocked")
        before_lease = next(r for r in self.rows("leases") if r["id"] == a1.lease_id)
        before_waiter = next(r for r in self.rows("waiters") if r["orchestrator_id"] == "A")
        self.assertTrue(self.acquire("C").ok)
        self.assertEqual(next(r for r in self.rows("leases") if r["id"] == a1.lease_id),
                         before_lease)
        self.assertEqual(next(r for r in self.rows("waiters") if r["orchestrator_id"] == "A"),
                         before_waiter)
        self.assertEqual(len([r for r in self.rows("leases")
                              if r["state"] in ("held", "rented")]), 3)
        self.assertFalse(self.acquire("D").ok)

    def test_new_caller_without_waiter_has_its_existing_entitlement(self):
        _, a2, _ = self.filled_pool()
        self.assertEqual(self.acquire("A", "heal").reason, "cap_full")
        self.broker.release(a2.lease_id, "A")
        self.assertEqual([r["orchestrator_id"] for r in self.rows("waiters")], ["A"])
        self.assertTrue(self.acquire("C", "fixture").ok)

    def test_priority_is_preserved_among_eligible_roots(self):
        _, a2, _ = self.filled_pool()
        self.assertEqual(self.acquire("A", "heal").reason, "cap_full")
        self.assertEqual(self.acquire("C", "review").reason, "cap_full")
        self.assertEqual(self.acquire("D", "fix_build").reason, "cap_full")
        self.broker.release(a2.lease_id, "A")
        self.assertEqual(self.acquire("A", "heal").reason, "lending_blocked")
        self.assertEqual(self.acquire("C", "review").reason, "priority_wait")
        self.assertTrue(self.acquire("D", "fix_build").ok)

    def test_fifo_is_preserved_among_eligible_same_priority_roots(self):
        _, a2, _ = self.filled_pool()
        self.assertEqual(self.acquire("A").reason, "cap_full")
        self.assertEqual(self.acquire("C").reason, "cap_full")
        self.assertEqual(self.acquire("D").reason, "cap_full")
        self.broker.release(a2.lease_id, "A")
        self.assertEqual(self.acquire("D").reason, "priority_wait")
        c1 = self.acquire("C")
        self.assertTrue(c1.ok)
        self.assertEqual(self.acquire("A").reason, "lending_blocked")

    def test_surplus_borrowing_remains_available_without_below_share_demand(self):
        _, a2, _ = self.filled_pool()
        self.assertEqual(self.acquire("A").reason, "cap_full")
        self.broker.release(a2.lease_id, "A")
        lease = self.acquire("A")
        self.assertTrue(lease.ok)
        self.assertEqual(next(r for r in self.rows("leases")
                              if r["id"] == lease.lease_id)["state"], "rented")


if __name__ == "__main__":
    unittest.main()
