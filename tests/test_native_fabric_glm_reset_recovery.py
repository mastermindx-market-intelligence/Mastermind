"""Manual-reset recovery through the real original broker, cache and settlement.

All state is temporary. Provider reads are fixtures; no live database, credential,
request, voucher, runtime selection or worker launch is used.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "ops/native_fabric/quota_continuity/candidate"
OVERLAY = ROOT / "ops/native_fabric/grok47/quota_billing"
PICK_BASE = OVERLAY.parent / "overlay/pick.py"
MODEL_TIER = BASE.parent / "source/model_tier.py"
STAMP = datetime(2026, 11, 7, 12, tzinfo=timezone.utc).timestamp()
BINDING = {"config_generation": "config-a", "endpoint": "https://api.z.ai/api/coding/paas/v4"}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class GlmResetBrokerJourney(unittest.TestCase):
    def runtime_sources(self):
        """The component fixture; staged integration supplies actual emitted files."""
        ext = self.root / "ext"
        ext.mkdir()
        (ext / "lease_broker.py").write_bytes((BASE / "lease_broker.py").read_bytes())
        (ext / "pick.py").write_bytes(PICK_BASE.read_bytes())
        applied = subprocess.run(["git", "apply", "--unsafe-paths", str(OVERLAY / "lease_broker.py.patch"),
                                  str(OVERLAY / "pick.py.patch")],
                                 cwd=self.root, capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        return {"quota_remote.py": OVERLAY / "quota_remote.py",
                "quota_circuit.py": OVERLAY / "quota_circuit.py",
                "lease_broker.py": ext / "lease_broker.py", "pick.py": ext / "pick.py"}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="glm-reset-offline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = [STAMP]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(sys.modules))
        self.stack.enter_context(patch.object(sys, "path", [str(BASE), str(BASE.parent / "source")] + sys.path))
        self.outcome = load("provider_outcome", BASE / "provider_outcome.py")
        load("commission_deadline", BASE / "commission_deadline.py")
        runtime = self.runtime_sources()
        self.q = load("quota_remote", runtime["quota_remote.py"])
        self.c = load("quota_circuit", runtime["quota_circuit.py"])
        self.broker_module = load("h2_reset_broker", runtime["lease_broker.py"])
        sys.modules["lease_broker"] = self.broker_module
        load("model_tier", MODEL_TIER)
        self.pick = load("h2_reset_pick", runtime["pick.py"])
        self.cache = self.root / "quota_cache.json"
        self.stack.enter_context(patch.object(self.q, "CACHE_PATH", str(self.cache)))
        self.stack.enter_context(patch.object(self.q, "_config_binding", return_value=BINDING))
        self.stack.enter_context(patch.object(self.q, "_utc_now",
            side_effect=lambda: datetime.fromtimestamp(self.clock[0], timezone.utc)))
        self.stack.enter_context(patch.object(self.q, "_glm_accounts_dict", return_value={"account": {}}))
        self.remote = self.stack.enter_context(patch.object(self.q, "_live_glm",
            side_effect=AssertionError("broker must not perform provider I/O")))
        self.config = {"providers": {"glm": {
            "enabled": True, "concurrency_cap": 8, "pool_aliases": ["glm-alias"],
            "accounts": [{"name": "account", "per_account_cap": 8}],
        }}}
        self.accounts = self.root / "accounts.json"
        self.accounts.write_text(json.dumps(self.config))
        self.br = self.broker_module.Broker(
            db_path=str(self.root / "broker.db"), lock_path=str(self.root / "broker.lock"),
            accounts_path=str(self.accounts), now_fn=lambda: self.clock[0],
            check_pid=False, external_gates=True, this_host="fixture",
            status_json=str(self.root / "status.json"), hosts_path=str(self.root / "hosts.json"))
        self.stack.enter_context(patch.object(self.broker_module, "default_broker", return_value=self.br))
        self.publish(remaining=80, started=STAMP-20)

    def publish(self, remaining=99, *, started=None, rows=None):
        started = self.clock[0]-1 if started is None else started
        rows = self.rows(remaining) if rows is None else rows
        return self.q._publish_observation(str(self.cache), "glm", "account", rows, BINDING, started)

    def rows(self, remaining=99):
        return [self.q.ProviderQuotaState(
            "glm", window, 100-remaining, 100, remaining,
            self.q._iso(self.clock[0] + (5*3600 if window == "5h" else 7*86400)),
            "PROVIDER_AUTHORITATIVE", self.q._iso(self.clock[0]), .98, "offline fixture",
            account="account", config_generation="config-a", endpoint=BINDING["endpoint"])
            for window in ("5h", "weekly")]

    def acquire(self, root="worker", pool="glm", model="glm-5.3"):
        return self.br.acquire(root, pool, account="account", task_class="build",
                               host="fixture", model=model, wait=0, ttl=3600)

    def raw(self):
        conn = self.br._conn()
        try:
            row = conn.execute("SELECT * FROM quota_cooldowns WHERE scope='glm:account'").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def observe(self, lease, root, run, kind="quota_exhausted", *, reset_after=7*86400):
        rc = 0 if kind == "success" else 75
        empty = hashlib.sha256(b"").hexdigest()
        value = dict(schema=self.outcome.SCHEMA, run_id=run, lease_id=lease.lease_id,
                     root_id=root, provider="glm", account="account", host="fixture",
                     model="glm-5.3", kind=kind, command_rc=rc, observed_at=self.clock[0],
                     reset_at=self.clock[0]+reset_after if rc else None,
                     reset_source="provider_event" if rc else None,
                     initial_rejection=bool(rc), stdout_sha256=empty)
        process = dict(schema="mastermind.local_owned_process_receipt.v1", label=run,
                       returncode=rc, stdout_sha256=empty, stdout_truncated=False,
                       stderr_truncated=False, timed_out=False, cleanup=dict(
                           census_proven=True, identity_verified=True, residual_count=0, status="not_needed"))
        op, pp = self.root / (run+".outcome.json"), self.root / (run+".process.json")
        op.write_text(json.dumps(value))
        pp.write_text(json.dumps(process))
        lock = self.br._lock()
        conn = self.br._conn()
        try:
            return self.c.observe_locked(self.br, conn, lease.lease_id, root, run, op, pp)
        finally:
            conn.close()
            lock.close()

    def exhaust(self, kind="quota_exhausted"):
        original = self.acquire("original")
        self.assertTrue(original.ok, original.reason)
        self.clock[0] += 10
        self.observe(original, "original", "original-failed", kind)
        self.assertTrue(self.br.release(original.lease_id, "original"))
        self.publish(remaining=0)
        self.assertTrue(self.c.pool_blocked(self.br, "glm"))
        return original

    def refill(self):
        self.clock[0] += 31
        self.remote.side_effect = None
        self.remote.return_value = self.rows()
        result = self.q.reconcile_glm_reset("account", now_ts=self.clock[0], cache_path=str(self.cache))
        self.assertEqual(result["state"], "QUOTA_READY")
        self.assertEqual(result["redemption"], "NOT_PERFORMED")
        self.remote.reset_mock()
        self.remote.side_effect = AssertionError("broker must not perform provider I/O")

    def test_manual_refill_opens_one_real_broker_lease_then_settled_success_clears_hold(self):
        self.exhaust()
        original = self.raw()
        self.refill()
        projection = self.c.cooldown(self.br, "glm", "account")
        self.assertEqual(projection["recovery_state"], "HALF_OPEN")
        self.assertEqual(self.raw(), original)
        self.assertFalse(self.c.pool_blocked(self.br, "glm"))
        probe = self.acquire("probe")
        self.assertTrue(probe.ok, probe.reason)
        self.assertFalse(self.acquire("second").ok)
        conn = self.br._conn()
        captured = dict(conn.execute("SELECT * FROM leases WHERE id=?", (probe.lease_id,)).fetchone())
        conn.close()
        self.assertEqual(captured["quota_config_generation"], "config-a")
        self.assertEqual(json.loads(captured["quota_recovery_json"])["cooldown"]["source_run"], "original-failed")
        self.clock[0] += 1
        self.observe(probe, "probe", "probe-success", "success")
        self.assertIsNone(self.raw())
        self.remote.assert_not_called()

    def test_actual_atomic_claim_allows_only_one_contender_across_pool_and_model_aliases(self):
        self.exhaust()
        self.refill()
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda n: self.acquire("contender-"+str(n),
                "glm" if n == 0 else "glm-alias", "glm-5.3" if n == 0 else "glm-5.3-flash"), range(2)))
        self.assertEqual(sum(result.ok for result in results), 1)

    def test_active_rate_limit_survives_a_later_quota_failure_and_refill(self):
        first, second = self.acquire("rate-worker"), self.acquire("quota-worker")
        self.assertTrue(first.ok and second.ok)
        self.clock[0] += 1
        self.observe(first, "rate-worker", "rate-failed", "rate_limit", reset_after=120)
        rate_until = self.raw()["until_ts"]
        self.br.release(first.lease_id, "rate-worker")
        self.clock[0] += 1
        self.observe(second, "quota-worker", "quota-failed")
        self.br.release(second.lease_id, "quota-worker")
        self.assertEqual(self.raw()["non_quota_until_ts"], rate_until)
        self.assertEqual(self.raw()["kind"], "quota_exhausted")
        self.refill()
        self.assertTrue(self.c.pool_blocked(self.br, "glm"))
        self.assertFalse(self.acquire("waiting-for-rate").ok)
        self.clock[0] = rate_until + 1
        self.publish()
        probe = self.acquire("waiting-for-rate")
        self.assertTrue(probe.ok, probe.reason)
        self.observe(probe, "waiting-for-rate", "after-rate-success", "success")
        self.assertIsNone(self.raw())

    def test_refresh_during_claim_precedes_stored_grant_and_can_settle(self):
        self.exhaust()
        self.refill()
        original = self.c.claim_binding
        def later_binding(*args, **kwargs):
            self.clock[0] += 2
            self.publish()
            return original(*args, **kwargs)
        with patch.object(self.c, "claim_binding", side_effect=later_binding):
            probe = self.acquire("later-proof")
        self.assertTrue(probe.ok, probe.reason)
        self.observe(probe, "later-proof", "later-proof-success", "success")
        self.assertIsNone(self.raw())

    def test_rate_component_is_not_extended_to_an_earlier_longer_quota_deadline(self):
        leases = [(self.acquire(root), root) for root in ("quota-one", "rate", "quota-two")]
        self.assertTrue(all(lease.ok for lease, root in leases))
        rate_until = None
        for lease, root in leases:
            self.clock[0] += 1
            kind = "rate_limit" if root == "rate" else "quota_exhausted"
            self.observe(lease, root, root+"-failed", kind,
                         reset_after=120 if kind == "rate_limit" else 7*86400)
            self.br.release(lease.lease_id, root)
            if kind == "rate_limit":
                rate_until = self.clock[0] + 120
        self.assertEqual(self.raw()["non_quota_until_ts"], rate_until)
        self.assertGreater(self.raw()["until_ts"], rate_until)
        self.clock[0] = rate_until + 1
        self.publish()
        self.assertFalse(self.c.pool_blocked(self.br, "glm"))

    def test_unpublished_refusal_blocks_a_separate_real_broker_admission(self):
        self.exhaust()
        self.refill()
        self.remote.side_effect = self.q.ProviderQuotaRefusal()
        original = self.q._atomic_write
        calls = []
        def fail_completion(path, value):
            calls.append(path)
            if len(calls) == 1:
                return original(path, value)
            raise self.q.QuotaCacheWriteError("fixture completion failure")
        with patch.object(self.q, "_atomic_write", side_effect=fail_completion):
            with self.assertRaises(self.q.QuotaCacheWriteError):
                self.q.reconcile_glm_reset("account", now_ts=self.clock[0], cache_path=str(self.cache))
        self.assertTrue(self.c.pool_blocked(self.br, "glm"))
        self.assertFalse(self.acquire("separate-invocation").ok)
        self.q.reconcile_glm_reset("account", now_ts=self.clock[0]+1000, cache_path=str(self.cache))
        self.remote.assert_called_once()

    def test_new_failure_after_probe_claim_wins_over_late_success(self):
        self.exhaust()
        self.refill()
        probe = self.acquire("probe")
        self.assertTrue(probe.ok)
        self.clock[0] += 2
        conn = self.br._conn()
        conn.execute("UPDATE quota_cooldowns SET observed_at=?, source_run='newer-failure', failures=failures+1",
                     (self.clock[0],))
        conn.commit()
        conn.close()
        expected = self.raw()
        self.observe(probe, "probe", "late-success", "success")
        self.assertEqual(self.raw(), expected)

    def test_refresh_started_before_failure_cannot_reopen_even_if_response_arrives_after(self):
        self.exhaust()
        failed = self.raw()["observed_at"]
        self.clock[0] += 3
        self.publish(started=failed-0.5)
        self.assertTrue(self.c.pool_blocked(self.br, "glm"))
        self.assertFalse(self.acquire().ok)

    def test_paired_window_and_identity_fences_preserve_hard_hold(self):
        self.exhaust()
        self.clock[0] += 20
        valid = self.rows()
        cases = [valid[:1], valid+[valid[0]],
                 [valid[0], replace(valid[1], remaining_pct=5)],
                 [replace(s, account="different") for s in valid],
                 [replace(s, config_generation="config-b") for s in valid],
                 [replace(s, endpoint="https://other.example/v1") for s in valid],
                 [replace(s, observed_at=self.q._iso(self.clock[0]-601)) for s in valid],
                 [replace(s, observed_at=self.q._iso(self.clock[0]+1000)) for s in valid],
                 [replace(s, reset_at=self.q._iso(self.clock[0])) for s in valid]]
        for rows in cases:
            with self.subTest(rows=rows):
                self.clock[0] += 1
                self.publish(rows=rows)
                self.assertTrue(self.c.pool_blocked(self.br, "glm"))
                self.assertFalse(self.acquire().ok)

    def test_permission_refusal_is_not_cleared_by_reset_or_positive_cache(self):
        self.exhaust()
        self.refill()
        self.q._record_refresh_failure(str(self.cache), "glm", "account", None,
                                      BINDING, self.clock[0], self.q.ProviderQuotaRefusal())
        self.assertTrue(self.c.pool_blocked(self.br, "glm"))
        self.assertFalse(self.acquire().ok)

    def test_rate_limit_legacy_generation_and_shared_scope_do_not_gain_early_recovery(self):
        self.exhaust()
        self.refill()
        conn = self.br._conn()
        for column, value in (("kind", "rate_limit"), ("config_generation", None),
                              ("config_generation", "config-b"), ("mode", "SOFT")):
            conn.execute("UPDATE quota_cooldowns SET kind='quota_exhausted', config_generation='config-a', mode='HARD'")
            conn.execute("UPDATE quota_cooldowns SET "+column+"=?", (value,))
            conn.commit()
            self.assertTrue(self.c.pool_blocked(self.br, "glm"))
        conn.execute("UPDATE quota_cooldowns SET kind='quota_exhausted', config_generation='config-a', mode='HARD', scope='declared:shared'")
        conn.commit()
        conn.close()
        self.config["providers"]["glm"]["quota_scope"] = "shared"
        self.accounts.write_text(json.dumps(self.config))
        self.br._accounts_mtime = None
        self.assertTrue(self.c.pool_blocked(self.br, "glm"))

    def test_provider_disable_and_unqualified_cache_are_still_admission_gates(self):
        self.exhaust()
        self.refill()
        self.config["providers"]["glm"]["enabled"] = False
        self.accounts.write_text(json.dumps(self.config))
        self.br._accounts_mtime = None
        self.assertFalse(self.acquire().ok)

    def test_new_failure_between_projection_and_claim_is_rechecked(self):
        self.exhaust()
        self.refill()
        self.assertFalse(self.c.pool_blocked(self.br, "glm"))
        conn = self.br._conn()
        conn.execute("UPDATE quota_cooldowns SET observed_at=?, source_run='between-preview-claim'", (self.clock[0],))
        conn.commit()
        conn.close()
        self.assertFalse(self.acquire().ok)

    def test_normal_picker_refreshes_a_blocked_account_before_filtering_and_real_claim(self):
        self.exhaust()
        self.clock[0] += self.q.REFRESH_INTERVAL_S
        self.remote.side_effect = None
        self.remote.return_value = self.rows()
        with patch.object(self.pick, "_glm_enabled", return_value=True), \
             patch.object(self.pick, "_selection_model", return_value=("glm-5.3", "")), \
             patch.object(self.pick, "_glm_broker_model_remaining", return_value=1):
            self.assertEqual(self.pick.hard_filter("glm", "build", {}), (True, "ok"))
        self.remote.assert_called_once()
        self.assertTrue(self.acquire("normal-work").ok)
        self.assertFalse(self.acquire("competing-work").ok)

    def test_failed_due_picker_refresh_holds_and_does_not_repeat_network_on_same_attempt(self):
        self.exhaust()
        self.clock[0] += self.q.REFRESH_INTERVAL_S
        self.remote.side_effect = OSError("offline fixture")
        self.assertEqual(self.pick.hard_filter("glm", "build", {}), (False, "provider quota cooldown"))
        self.assertEqual(self.pick.hard_filter("glm", "build", {}), (False, "provider quota cooldown"))
        self.remote.assert_called_once()

    def test_host_account_filter_also_refreshes_before_removing_the_blocked_glm_route(self):
        self.exhaust()
        self.clock[0] += self.q.REFRESH_INTERVAL_S
        self.remote.side_effect = None
        self.remote.return_value = self.rows()
        observed_accounts = []
        def qualify(accounts, **kwargs):
            observed_accounts.extend(a["name"] for a in accounts)
            return accounts, []
        host = SimpleNamespace(load_registry=lambda: {"fixture": {"platform": "darwin"}},
                               HOSTS_STATE_DIR=self.root)
        placement = SimpleNamespace(_default_read_bytes=lambda path: b"{}",
                                    build_placement_view=lambda *args, **kwargs: {"host_choice": "fixture"})
        with patch.dict(sys.modules, {"host_pick": host, "placement_view": placement,
                        "glm_host_account_source": SimpleNamespace(filter_observed_accounts=qualify)}):
            routes = self.pick._eligible_host_routes("fixture", required_modes=["glm"], glm_model="glm-5.3")
        self.assertEqual(routes, {"glm": ("fixture", "glm")})
        self.assertEqual(observed_accounts, ["account"])
        self.remote.assert_called_once()


if __name__ == "__main__":
    unittest.main()
