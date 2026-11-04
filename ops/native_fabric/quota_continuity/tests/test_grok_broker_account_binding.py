#!/usr/bin/env python3
"""Real incumbent Broker in disposable fixture state; no provider/worker calls."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]
from lease_broker import Broker


class GrokBrokerAccountBindingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.accounts = self.root / 'accounts.yaml'
        self.hosts = self.root / 'hosts.json'
        self.account_spec = {
            "name": "default", "subscription_scope": "chris-main-grok",
        }
        self.host = "fixture-ubuntu0"
        self.enrollment = {
            "schema": "mastermind.grok_host_account_binding.v1",
            "host": self.host,
            "account": "default",
            "subscription_scope": "chris-main-grok",
            "auth_identity": {
                "uid": 1000, "dev": 33, "ino": 44, "size": 55,
                "mtime_ns": 600, "ctime_ns": 700,
            },
        }
        self.host_entry = {
            "roles": ["lanes"], "allowed_modes": ["grok"],
            "qualification_only_modes": [],
            "cores": 4, "max_active": 2, "lane_ceiling": 2,
            "grok_account_binding": self.enrollment,
        }
        self.write_config()
        self.write_hosts()
        self.broker = Broker(
            db_path=str(self.root / 'broker.sqlite'),
            lock_path=str(self.root / 'broker.lock'),
            accounts_path=str(self.accounts),
            hosts_path=str(self.hosts),
            grok_marker=str(self.root / 'missing-exhausted-marker'),
            external_gates=False, check_pid=False, this_host='fixture-broker',
            now_fn=lambda: 1000.0,
        )

    def write_config(self):
        self.accounts.write_text(json.dumps({
            "providers": {"grok": {
                "enabled": True, "capacity_policy": "host_admitted",
                "accounts": [self.account_spec],
            }},
        }))
        if hasattr(self, 'broker'):
            self.broker._accounts_cache = None
            self.broker._accounts_mtime = None

    def write_hosts(self):
        self.hosts.write_text(json.dumps({self.host: self.host_entry}))

    def grant(self, *, host=None, account="default", task_class="remote-grok"):
        return self.broker.acquire(
            orchestrator_id="fixture-original-parent",
            pool="grok", account=account, host=host or self.host,
            task_class=task_class, model="grok-4.7", pid=os.getpid(),
            ttl=60, wait=0,
        )

    def counts(self):
        conn = self.broker._conn()
        try:
            return (conn.execute("SELECT COUNT(*) FROM leases").fetchone()[0],
                    conn.execute("SELECT COUNT(*) FROM waiters").fetchone()[0])
        finally:
            conn.close()

    def test_exact_authorized_host_account_is_granted_in_fixture_only(self):
        row = self.grant()
        self.assertTrue(row.ok)
        self.assertEqual(row.account, "default")
        self.assertEqual(self.counts(), (1, 0))

    def test_missing_enrollment_denies_without_lease_or_waiter(self):
        self.host_entry.pop("grok_account_binding")
        self.write_hosts()
        row = self.grant()
        self.assertFalse(row.ok)
        self.assertEqual(row.reason, "host_account_unavailable")
        self.assertEqual(self.counts(), (0, 0))

    def test_wrong_host_account_or_scope_denies_prelease(self):
        for field, value in (("host", "fixture-ubuntu3"),
                             ("account", "secretary2"),
                             ("subscription_scope", "secretary2-pool")):
            with self.subTest(field=field):
                original = self.enrollment[field]
                self.enrollment[field] = value
                self.write_hosts()
                row = self.grant()
                self.assertFalse(row.ok)
                self.assertEqual(row.reason, "host_account_unavailable")
                self.assertEqual(self.counts(), (0, 0))
                self.enrollment[field] = original

    def test_account_catalog_scope_mismatch_refuses(self):
        self.account_spec["subscription_scope"] = "other-pool"
        self.write_config()
        row = self.grant()
        self.assertFalse(row.ok)
        self.assertEqual(row.reason, "host_account_unavailable")
        self.assertEqual(self.counts(), (0, 0))

    def test_account_catalog_missing_scope_refuses(self):
        del self.account_spec["subscription_scope"]
        self.write_config()
        row = self.grant()
        self.assertFalse(row.ok)
        self.assertEqual(row.reason, "host_account_unavailable")
        self.assertEqual(self.counts(), (0, 0))

    def test_unqualified_host_mode_or_held_qualification_refuses(self):
        self.host_entry["qualification_only_modes"] = ["grok"]
        self.write_hosts()
        row = self.grant()
        self.assertFalse(row.ok)
        self.assertEqual(row.reason, "host_account_unavailable")
        self.assertEqual(self.counts(), (0, 0))

    def test_malformed_mode_and_qualification_shapes_refuse(self):
        for key, value in (("roles", "lanes"), ("allowed_modes", "grok"),
                           ("qualification_only_modes", "nonsense")):
            with self.subTest(field=key):
                previous = self.host_entry[key]
                self.host_entry[key] = value
                self.write_hosts()
                row = self.grant()
                self.assertFalse(row.ok)
                self.assertEqual(row.reason, "host_account_unavailable")
                self.assertEqual(self.counts(), (0, 0))
                self.host_entry[key] = previous

    def test_unsafe_host_registry_path_refuses(self):
        self.hosts.unlink()
        self.hosts.symlink_to(self.accounts)
        row = self.grant()
        self.assertFalse(row.ok)
        self.assertEqual(row.reason, "host_account_unavailable")
        self.assertEqual(self.counts(), (0, 0))

    def test_malformed_enrollment_refuses(self):
        self.enrollment["auth_identity"]["uid"] = True
        self.write_hosts()
        row = self.grant()
        self.assertFalse(row.ok)
        self.assertEqual(row.reason, "host_account_unavailable")
        self.assertEqual(self.counts(), (0, 0))


if __name__ == '__main__':
    unittest.main()
