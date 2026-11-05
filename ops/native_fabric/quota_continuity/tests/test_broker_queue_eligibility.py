"""Offline regression tests for lending/FIFO queue eligibility (C1 convoy).

Actual Broker.acquire against all-temporary SQLite/lock/accounts/hosts/status
paths and a fake provider config; no live broker, provider or network access.
The lending-blocked head must not convoy eligible later demand: only waiters
the current lending predicate would refuse are skipped, keeping their exact
id, enqueued_at and priority.
"""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]

import lease_broker


def fixture_broker(root, clock):
    accounts = root / 'accounts.json'
    accounts.write_text(json.dumps({'providers': {'fixture': {
        'enabled': True, 'concurrency_cap': 7,
        'accounts': [{'name': 'account', 'per_account_cap': 7}]}}}))
    return lease_broker.Broker(
        db_path=str(root / 'broker.sqlite'),
        lock_path=str(root / 'broker.lock'),
        accounts_path=str(accounts),
        now_fn=lambda: clock[0],
        check_pid=False, external_gates=False,
        grok_marker=str(root / 'no-marker'),
        this_host='fixture',
        status_json=str(root / 'status.json'),
        hosts_path=str(root / 'hosts.json'))


class QueueEligibility(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='broker-queue-eligibility-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = [1000.0]
        self.br = fixture_broker(self.root, self.clock)

    # ── helpers ──────────────────────────────────────────────────────────────

    def acquire(self, br=None, root='root', task_class='fixture'):
        return (br or self.br).acquire(root, 'fixture', task_class=task_class,
                                       host='fixture', model='fixture',
                                       ttl=1000, wait=0)

    def enqueue(self, names, task_classes=None):
        task_classes = task_classes or {}
        lock = self.br._lock()
        try:
            conn = self.br._conn()
            try:
                for name in names:
                    self.clock[0] += 1
                    self.br._enqueue_waiter(conn, None, name, 'fixture', None,
                                            task_classes.get(name, 'fixture'),
                                            'fixture', 1)
                conn.commit()
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def waiters(self):
        conn = self.br._conn()
        try:
            return [(r['id'], r['orchestrator_id'], r['priority'], r['enqueued_at'])
                    for r in self.br._waiters(conn, 'fixture')]
        finally:
            conn.close()

    def active(self):
        conn = self.br._conn()
        try:
            return list(self.br._active_leases(conn, 'fixture'))
        finally:
            conn.close()

    def held_by(self, orch):
        conn = self.br._conn()
        try:
            return len(self.br._held_by(conn, orch, 'fixture'))
        finally:
            conn.close()

    # ── cases ────────────────────────────────────────────────────────────────

    def test_ineligible_head_is_retained_while_eligible_later_demand_grants(self):
        # cap7 active2 share1; six waiters. The oldest already holds its full
        # share so the current lending predicate refuses it, but it must not
        # convoy the eligible later demand behind it.
        self.assertTrue(self.acquire(root='oldest').ok)
        self.assertTrue(self.acquire(root='other-held').ok)
        names = ['oldest', 'later', 'demand-c', 'demand-d', 'demand-e', 'demand-f']
        self.enqueue(names)
        before = {w[1]: w for w in self.waiters()}
        blocked = self.acquire(root='oldest')
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.reason, 'lending_blocked')
        conn = self.br._conn()
        try:
            share = self.br.fair_share(conn, 'fixture')
            active = len(self.br._active_leases(conn, 'fixture'))
        finally:
            conn.close()
        self.assertEqual((share, active, self.br.pool_cap('fixture')), (1, 2, 7))
        granted = [name for name in names[1:] if self.acquire(root=name).ok]
        self.assertEqual(granted,
                         ['later', 'demand-c', 'demand-d', 'demand-e', 'demand-f'])
        self.assertEqual(len(self.active()), 7)
        # The ineligible borrower was never deleted or requeued, and kept its
        # exact queued identity, age and priority.
        after = {w[1]: w for w in self.waiters()}
        self.assertEqual(list(after), ['oldest'])
        self.assertEqual(after['oldest'], before['oldest'])
        self.assertEqual(self.held_by('oldest'), 1)
        self.assertEqual(self.held_by('other-held'), 1)

    def test_oldest_eligible_waiter_wins_at_same_priority(self):
        self.enqueue(['first', 'second'])
        jump = self.acquire(root='jump')
        self.assertFalse(jump.ok)
        self.assertEqual(jump.reason, 'priority_wait')
        self.assertTrue(self.acquire(root='first').ok)
        self.assertTrue(self.acquire(root='second').ok)
        self.assertEqual(sorted(w[1] for w in self.waiters()), ['jump'])
        self.assertEqual(self.held_by('jump'), 0)

    def test_priority_is_preserved_among_eligible_waiters(self):
        self.enqueue(['census-root', 'heal-root'],
                     task_classes={'census-root': 'census', 'heal-root': 'heal'})
        jump = self.acquire(root='fix-root', task_class='fix')
        self.assertFalse(jump.ok)
        self.assertEqual(jump.reason, 'priority_wait')
        # heal(0) outranks the later fix(1) demand, then the queued fix(1)
        # outranks the older census(3) waiter: priority among eligible is
        # preserved, not raw queue age.
        self.assertTrue(self.acquire(root='heal-root', task_class='heal').ok)
        self.assertTrue(self.acquire(root='fix-root', task_class='fix').ok)
        self.assertTrue(self.acquire(root='census-root', task_class='census').ok)

    def test_new_arrival_uses_the_same_share_as_the_preceding_acquire_gate(self):
        self.assertTrue(self.acquire(root='oldest').ok)
        self.assertTrue(self.acquire(root='other-held').ok)
        self.enqueue(['oldest', 'below-share'],
                     task_classes={'oldest': 'heal', 'below-share': 'census'})
        before = {row[1]: row for row in self.waiters()}
        # Before this new root joins demand, 7//3 gives share2. The actual
        # acquire gate counts its caller too: 7//4 gives share1, making the
        # high-priority holder ineligible while the census waiter is eligible.
        with self.br._conn() as conn:
            self.assertEqual(self.br.fair_share(conn, 'fixture'), 2)
            self.assertEqual(self.br.fair_share(conn, 'fixture', extra='new-fix'), 1)
        result = self.acquire(root='new-fix', task_class='fix')
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(self.held_by('new-fix'), 1)
        self.assertEqual({row[1]: row for row in self.waiters()}, before)

    def test_surplus_waits_for_below_share_demand_then_resumes(self):
        # Surplus is not granted while another waiting root is below share;
        # after that demand is served and a slot frees, the same root may
        # borrow again without losing anything to starvation.
        for _ in range(7):
            self.assertTrue(self.acquire(root='holder').ok)
        self.assertEqual(len(self.active()), 7)
        denied = self.acquire(root='newbie')
        self.assertFalse(denied.ok)
        self.assertEqual(denied.reason, 'cap_full')
        newbie_row = {w[1]: w for w in self.waiters()}['newbie']
        blocked = self.acquire(root='holder')
        self.assertFalse(blocked.ok)
        self.assertEqual(blocked.reason, 'lending_blocked')
        self.assertEqual(self.held_by('holder'), 7)
        # Newbie's queued age survived holder's blocked surplus attempt.
        self.assertEqual({w[1]: w for w in self.waiters()}['newbie'], newbie_row)
        self.assertTrue(self.br.release(self.active()[0]['id'], 'holder'))
        served = self.acquire(root='newbie')
        self.assertTrue(served.ok)
        self.assertEqual(served.state, 'held')
        self.assertNotIn('newbie', [w[1] for w in self.waiters()])
        self.assertTrue(self.br.release(self.active()[0]['id'], 'holder'))
        surplus = self.acquire(root='holder')
        self.assertTrue(surplus.ok)
        self.assertEqual(surplus.state, 'rented')
        self.assertEqual(len(self.active()), 7)

    def test_priority_and_original_age_survive_an_ineligible_head(self):
        self.assertTrue(self.acquire(root='oldest').ok)
        self.assertTrue(self.acquire(root='other-held').ok)
        self.enqueue(['oldest', 'census-root', 'fix-root'],
                     task_classes={'oldest': 'heal', 'census-root': 'census',
                                   'fix-root': 'fix'})
        original = {w[1]: w for w in self.waiters()}['oldest']
        denied = self.acquire(root='census-root', task_class='census')
        self.assertFalse(denied.ok)
        self.assertEqual(denied.reason, 'priority_wait')
        self.assertTrue(self.acquire(root='fix-root', task_class='fix').ok)
        self.assertTrue(self.acquire(root='census-root', task_class='census').ok)
        self.assertEqual({w[1]: w for w in self.waiters()}['oldest'], original)
        # Once the eligible below-share demand is served, the retained oldest
        # row participates again and can borrow without requeueing or age loss.
        resumed = self.acquire(root='oldest', task_class='heal')
        self.assertTrue(resumed.ok, resumed.reason)
        self.assertEqual(resumed.state, 'rented')
        self.assertNotIn('oldest', [w[1] for w in self.waiters()])

    def test_cap_is_never_overgranted_with_concurrent_independent_roots(self):
        brokers = [fixture_broker(self.root, self.clock) for _ in range(12)]
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(self.acquire, br, 'concurrent-%d' % i)
                       for i, br in enumerate(brokers)]
            results = [f.result() for f in futures]
        grants = [r for r in results if r.ok]
        self.assertGreater(len(grants), 0, 'concurrent admission must make progress')
        self.assertLessEqual(len(grants), 7)
        self.assertLessEqual(len(self.active()), 7)
        self.assertEqual(len({r.lease_id for r in grants}), len(grants))
        for r in results:
            if not r.ok:
                self.assertIn(r.reason,
                              ('priority_wait', 'cap_full', 'lending_blocked'))


if __name__ == '__main__':
    unittest.main()
