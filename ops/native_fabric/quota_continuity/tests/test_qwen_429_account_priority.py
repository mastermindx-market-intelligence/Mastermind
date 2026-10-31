"""Source-exact, credential-free regression of new Qwen account admission.

This extracts the candidate broker's *actual* account-selection method rather
than reproducing its ordering algorithm. No live broker, provider, accounts
configuration, disk quota file, or remote host is touched.
"""
import ast
from pathlib import Path
import sqlite3
import sys
import types
import unittest
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "candidate" / "lease_broker.py"


def selected_method():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    classes = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "Broker"]
    assert len(classes) == 1
    methods = [node for node in classes[0].body
               if isinstance(node, ast.FunctionDef) and node.name == "_pick_account"]
    assert len(methods) == 1
    namespace = {
        "sqlite3": sqlite3, "Optional": Optional, "List": List,
        "Dict": Dict, "Tuple": Tuple, "Any": Any,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])),
                 str(SOURCE), "exec"), namespace)
    return namespace["_pick_account"]


class BrokerStub:
    external_gates = True
    def __init__(self):
        self.names = ["Ryan", "Chris", "Kris"]
        self.held = {}
        self.blocked = set()
        self.model_held = {}
        self.model_caps = {}

    def provider_name(self, pool):
        return pool

    def grantable_accounts(self, pool):
        return [{"name": name, "_eff_cap": 7} for name in self.names]

    def _account_held(self, conn, pool, name):
        return self.held.get(name, 0)

    def account_model_cap(self, pool, acct, model):
        return self.model_caps.get(acct["name"])

    def _account_model_held(self, conn, pool, name, model):
        return self.model_held.get(name, 0)


class Qwen429AccountPriorityTests(unittest.TestCase):
    def setUp(self):
        self.method = selected_method()
        self.broker = BrokerStub()
        self.statuses = {}
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE leases (pool TEXT, account TEXT, granted_at REAL)")
        # Under the installed historical rotation, oldest Ryan wins all-equal.
        self.conn.executemany("INSERT INTO leases VALUES (?,?,?)",
                              [("bailian", "Ryan", 1), ("bailian", "Chris", 2),
                               ("bailian", "Kris", 3)])

        def cooldown_rank_readonly(name):
            state = self.statuses.get(name)
            return {
                None: 0, "expired": 0, "unreadable": 1,
                "http_429": 2, "access_denied": 3,
                "invalid_api_key": 3, "quota_or_insufficient": 3,
            }.get(state, 1)

        qwen = types.ModuleType("bailian_keys")
        qwen.cooldown_rank_readonly = cooldown_rank_readonly
        quota = types.ModuleType("quota_circuit")
        quota.admission_room = lambda broker, conn, pool, acct: (
            acct["name"] not in self.broker.blocked)
        self.modules = patch.dict(sys.modules, {
            "bailian_keys": qwen, "quota_circuit": quota,
        })
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        self.conn.close()

    def pick(self, *, pool="bailian", preferred=None, model="", host_rows=None):
        return self.method(self.broker, self.conn, pool, preferred, model=model,
                           grantable_override=host_rows)

    def observed(self, rankings):
        return [dict(name=name, _eff_cap=7, _host_qwen_429_rank=rank)
                for name, rank in rankings.items()]

    def test_healthy_keeps_existing_history(self):
        self.assertEqual(self.pick(), "Ryan")

    def test_recent_429_yields_to_unthrottled_account(self):
        self.statuses["Ryan"] = "http_429"
        self.assertEqual(self.pick(), "Chris")

    def test_429_on_two_accounts_selects_remaining_healthy(self):
        self.statuses.update(Ryan="http_429", Chris="http_429")
        self.assertEqual(self.pick(), "Kris")

    def test_all_429_keeps_soft_cap_and_rotation(self):
        self.statuses.update(Ryan="http_429", Chris="http_429", Kris="http_429")
        self.assertEqual(self.pick(), "Ryan")

    def test_exact_account_pin_does_not_move(self):
        self.statuses["Ryan"] = "http_429"
        self.assertEqual(self.pick(preferred="Ryan"), "Ryan")

    def test_exact_pin_at_cap_is_refused_not_rebound(self):
        self.statuses["Ryan"] = "http_429"
        self.broker.held["Ryan"] = 7
        self.assertIsNone(self.pick(preferred="Ryan"))

    def test_all_healthy_preserves_held_slot_priority(self):
        self.broker.held.update(Ryan=2, Chris=1, Kris=0)
        self.assertEqual(self.pick(), "Kris")

    def test_429_can_be_used_if_other_accounts_at_cap(self):
        self.statuses["Ryan"] = "http_429"
        self.broker.held.update(Chris=7, Kris=7)
        self.assertEqual(self.pick(), "Ryan")

    def test_unknown_cooldown_is_not_scored_healthy(self):
        self.statuses["Ryan"] = "unreadable"
        self.assertEqual(self.pick(), "Chris")

    def test_hard_local_denial_never_gets_unpinned_lease(self):
        self.statuses["Ryan"] = "access_denied"
        self.assertEqual(self.pick(), "Chris")

    def test_all_hard_local_denials_refuse(self):
        self.statuses.update(Ryan="access_denied", Chris="invalid_api_key",
                             Kris="quota_or_insufficient")
        self.assertIsNone(self.pick())

    def test_exact_pinned_hard_denial_is_refused(self):
        self.statuses["Ryan"] = "access_denied"
        self.assertIsNone(self.pick(preferred="Ryan"))

    def test_expired_cooldown_is_healthy_without_mutating(self):
        self.statuses.update(Ryan="expired", Chris="http_429")
        self.assertEqual(self.pick(), "Ryan")

    def test_malformed_local_rank_not_accepted_as_healthy(self):
        self.statuses["Ryan"] = "invalid_state"
        self.assertEqual(self.pick(), "Chris")

    def test_unknown_ranked_between_healthy_and_throttled(self):
        self.statuses.update(Ryan="unreadable", Chris="http_429")
        self.assertEqual(self.pick(), "Kris")

    def test_absent_grantable_account_is_not_reintroduced(self):
        self.broker.names = ["Chris"]
        self.statuses["Ryan"] = "http_429"
        self.assertIsNone(self.pick(preferred="Ryan"))
        self.assertEqual(self.pick(), "Chris")

    def test_unqualified_account_excluded_before_priority(self):
        self.broker.blocked = {"Chris", "Kris"}
        self.statuses["Ryan"] = "http_429"
        self.assertEqual(self.pick(), "Ryan")

    def test_model_capacity_exclusion_precedes_preference(self):
        self.statuses["Ryan"] = "http_429"
        self.broker.model_caps["Chris"] = 1
        self.broker.model_held["Chris"] = 1
        self.assertEqual(self.pick(model="qwen3.8-max"), "Kris")

    def test_other_provider_unchanged(self):
        self.statuses["Ryan"] = "http_429"
        # Non-Bailian ties use alphabetical order, not Qwen grant history.
        self.assertEqual(self.pick(pool="glm"), "Chris")

    def test_host_reported_429_beats_stale_local_healthy(self):
        rows = self.observed({"Ryan": 2, "Kris": 0})
        self.assertEqual(self.pick(host_rows=rows), "Kris")

    def test_host_unknown_rank_is_not_healthy(self):
        rows = self.observed({"Ryan": 1, "Kris": 0})
        self.assertEqual(self.pick(host_rows=rows), "Kris")

    def test_hard_denied_host_account_is_not_reintroduced(self):
        rows = self.observed({"Ryan": 2, "Kris": 0})
        self.assertIsNone(self.pick(preferred="Chris", host_rows=rows))

    def test_exact_host_account_pin_does_not_rotate(self):
        rows = self.observed({"Ryan": 2, "Kris": 0})
        self.assertEqual(self.pick(preferred="Ryan", host_rows=rows), "Ryan")

    def test_all_host_accounts_429_remain_soft_eligible(self):
        rows = self.observed({"Ryan": 2, "Kris": 2})
        self.assertEqual(self.pick(host_rows=rows), "Ryan")

    def test_malformed_host_hint_cannot_claim_health(self):
        rows = self.observed({"Ryan": False, "Kris": 0})
        self.assertEqual(self.pick(host_rows=rows), "Kris")

    def test_disabled_external_gate_keeps_original_ranking(self):
        self.statuses["Ryan"] = "http_429"
        self.broker.external_gates = False
        self.assertEqual(self.pick(), "Ryan")


if __name__ == "__main__":
    unittest.main()
