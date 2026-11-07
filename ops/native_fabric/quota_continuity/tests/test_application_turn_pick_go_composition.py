"""Pure APPLICATION selection joined to the real Go composition; loopback only.

The nested Go handler, A broker/gateway/codec, admission and effects stay real
(the same loopback-only fake upstream as the incumbent composition fixture);
select_application() is a pure observer over synthetic owner projections and
performs no Broker, admission, secret, provider or usage effect. Go-only: no
other pool driver and no future expected-grant transaction is pretended here.
"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from test_go_application_handler_composition import (
    NativeApplicationHTTPFixture, SERVICE_TOKEN)
import lease_broker
import pick
import quota_remote

ROOT = Path(__file__).resolve().parents[1]

ROUTE_KEY = "fabric-app-picker-native-20261105-01"


def _policy_document():
    return {
        "routing": {
            "execute_order": ["minimax", "glm-flash", "bailian", "grok", "cursor"],
            "judgment_order": ["glm-5.3", "grok", "cursor", "fable"],
            "acceptance_floor": "0.6 over last 20",
        },
        "pools": {
            "go": {"enabled": True, "task_classes": ["mechanical", "review", "build"],
                   "worker_models": ["fixture-model"], "default_model": "fixture-model"},
            "glm": {"enabled": True, "models": {"executor": "glm-5.3-flash"}},
            "grok": {"enabled": True, "windows": {"weekly": {}}},
            "minimax": {"enabled": True},
            "bailian": {"enabled": True},
            "cursor": {"enabled": True},
        },
    }


class ApplicationPickGoComposition(NativeApplicationHTTPFixture):
    def setUp(self):
        super().setUp()
        self.policy_path = self.directory / "pools.yaml"
        self.policy_path.write_text(json.dumps(_policy_document()), encoding="utf-8")
        policy_patch = patch.object(pick, "POOLS_YAML", str(self.policy_path))
        policy_patch.start()
        self.addCleanup(policy_patch.stop)
        self.policy = pick.read_application_policy()
        self.grant_digest = hashlib.sha256(
            lease_broker._application_json(self.grant).encode()).hexdigest()
        self.selection_task = {
            "task_class": "mechanical", "task_complexity": "C1_ROUTINE_BOUNDED",
            "needs": [], "subject_pool": None,
            "escalation_reason": "fixture application economic witness",
            "route_key": ROUTE_KEY}
        self.selection_catalogue = {
            "schema": "mastermind.fabric_application_catalogue.v1",
            "pool_order": ["go"],
            "pools": {"go": {"enabled": True, "recipes": [{
                "model": "fixture-model", "mode": "go-codex", "protocol": "chat",
                "streaming": False, "driver": "go-codex", "profile": "primary",
                "source": "go-router-owner", "capabilities": {}, "order_rank": 0,
                "max_turn_seconds": 300, "max_steps": 2,
                "qualification_ref": "fixture:controlled-qualification",
                "application_permission_ref": "fixture:ordinary-inference",
                "grant_ref": {"grant_id": "macro-app",
                              "digest": self.grant_digest}}]}}}
        self.now = datetime.fromtimestamp(self.clock[0], timezone.utc)
        self.selection_observations = {"go": {
            "source": "fixture-broker", "observed_at": self.now.timestamp(),
            "fresh_s": 600.0, "cooldown": False,
            "model_room": {"fixture-model": 2, "other-model": 1},
            "host": "vps", "mode": "go-codex"}}

    def select_pure(self, *, task=None, catalogue=None, observations=None,
                    quality=None, now=None, expected=None):
        trips = []
        broker_original = lease_broker.default_broker

        def broker_trip(*args):
            trips.append("broker")
            raise AssertionError("broker constructed during pure selection")

        def ledger_trip(*args):
            trips.append("ledger")
            return []

        def provider_trip(*args):
            trips.append("provider")
            raise AssertionError("provider read during pure selection")

        with patch.object(lease_broker, "default_broker", broker_trip), \
                patch.object(pick, "_ledger_records", ledger_trip), \
                patch.object(quota_remote, "read_provider", provider_trip):
            result = pick.select_application(
                task or self.selection_task,
                policy=self.policy,
                catalogue=catalogue or self.selection_catalogue,
                observations=observations or self.selection_observations,
                quality_records=[] if quality is None else quality,
                now=now or self.now,
                expected_identity=expected)
        self.assertEqual(broker_original.__name__, "default_broker")
        self.assertEqual(trips, [])
        return result

    def application_turns(self):
        return self.rows("application_turns")

    def test_pure_selection_matches_the_real_go_admission_and_b_wire(self):
        self.assertEqual((len(self.posts), len(self.gets)), (0, 0))
        result = self.select_pure()
        self.assertEqual(result["ok"], True)
        self.assertIs(result["execution_authorized"], False)
        self.assertIs(result["requires_fresh_admission"], True)
        selection = result["selection"]
        self.assertEqual((selection["pool"], selection["model"],
                          selection["protocol"], selection["streaming"],
                          selection["order_source"], selection["host"]),
                         ("go", "fixture-model", "chat", False,
                          "task_default_policy", "vps"))
        self.assertEqual(set(result["coverage"]), {
            "go", "glm", "minimax", "bailian", "grok", "cursor",
            "codex-native", "claude-native", "ocfree"})
        # Selection is not admission: nothing exists before the real flow.
        self.assertEqual((self.rows("leases"), self.application_turns(),
                          self.rows("application_requests")), ([], [], []))
        status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-MM-Application-Disposition"], "terminal")
        turn = self.application_turns()[0]
        identity = result["identity"]
        self.assertEqual(turn["model"], selection["model"])
        self.assertEqual(turn["pool"], selection["pool"])
        self.assertEqual(turn["grant_id"], selection["grant_ref"]["grant_id"])
        self.assertEqual(turn["grant_digest"], selection["grant_ref"]["digest"])
        self.assertEqual(turn["principal_id"], "macro")
        self.assertEqual(turn["admission_root"], "service:macro")
        self.assertEqual(turn["caller_host"], identity["host"])
        self.assertEqual(turn["workload"], "site_interactive")
        self.assertEqual(turn["max_steps"], identity["max_steps"])
        self.assertEqual(turn["expires_at"],
                         min(self.grant["expires_at"],
                             turn["created_at"] + 300))
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(json.loads(self.posts[0][1])["model"], selection["model"])
        usage = self.usage_rows()
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0]["model"], selection["model"])

    def test_two_intentional_steps_keep_the_selected_lease_account_and_model(self):
        result = self.select_pure()
        self.assertEqual(self.request(step="step-1")[0], 200)
        original = self.application_turns()[0]
        self.assertEqual(self.request(step="step-2")[0], 200)
        turn = self.application_turns()[0]
        for key in ("lease_id", "account", "model", "grant_id", "grant_digest"):
            self.assertEqual(turn[key], original[key])
        self.assertEqual(turn["model"], result["selection"]["model"])
        self.assertEqual(self.posts[0][2], self.posts[1][2])
        self.assertEqual(len(self.posts), 2)
        status, body, _ = self.request(path="/application-turns/close",
                                       payload={"turn_id": "turn-1"})
        self.assertEqual(status, 200)
        self.assertEqual(body["application"]["disposition"], "closed")
        self.assertEqual(self.rows("leases")[0]["state"], "released")

    def test_worker_and_application_share_the_one_granted_slot(self):
        self.document["providers"]["go"]["accounts"] = [
            {"name": "account-a", "per_account_cap": 1}]
        self.grant["accounts"] = ["account-a"]
        self.save()
        result = self.select_pure()
        self.assertEqual(result["selection"]["model"], "fixture-model")
        self.assertEqual(self.request(turn="turn-cap")[0], 200)
        turn = self.application_turns()[0]
        self.assertEqual(turn["account"], "account-a")
        held = [row for row in self.rows("leases")
                if row["state"] in ("held", "rented")]
        self.assertEqual(len(held), 1)
        worker = self.broker.acquire("worker-root", "go", host="vps",
                                     pid=os.getpid(), model="fixture-model", wait=0)
        self.assertFalse(worker.ok)
        self.assertEqual(len([row for row in self.rows("leases")
                              if row["state"] in ("held", "rented")]), 1)
        self.assertEqual(len(self.posts), 1)

    def test_unknown_holds_capacity_and_original_close_semantics(self):
        result = self.select_pure()
        self.assertEqual(self.rows("leases"), [])
        self.partial = True
        status, body, _ = self.request(turn="turn-u")
        self.assertEqual(status, 503)
        self.assertTrue(body["application"]["effect_unknown"])
        request_row = self.rows("application_requests")[0]
        self.assertEqual(request_row["state"], "unknown")
        self.assertIsNone(request_row["terminal_receipt"])
        self.assertEqual(self.rows("leases")[0]["state"], "held")
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.usage_rows(), [])
        replay = self.request(turn="turn-u")
        self.assertEqual(replay[1]["application"]["disposition"], "effect_unknown")
        next_step = self.request(turn="turn-u", step="step-2")
        self.assertEqual(next_step[0], 409)
        self.assertEqual(next_step[1]["application"]["disposition"], "effect_unknown")
        self.assertEqual(len(self.posts), 1)
        status, body, _ = self.request(path="/application-turns/close",
                                       payload={"turn_id": "turn-u"})
        self.assertEqual(body["application"]["disposition"], "effect_unknown")
        self.assertIn(self.rows("leases")[0]["state"], ("held", "rented"))
        self.assertEqual(result["selection"]["model"], "fixture-model")

    def test_selection_change_conflicts_and_never_admits(self):
        issued = self.select_pure()
        self.assertEqual((self.rows("leases"), self.application_turns(),
                          self.rows("application_requests")), ([], [], []))
        same = self.select_pure(expected={
            "pool": "go", "model": "fixture-model",
            "grant_ref": issued["identity"]["grant_ref"],
            "task": issued["identity"]["task"],
            "policy": issued["identity"]["policy"]})
        self.assertEqual(same["ok"], True)
        mutated = json.loads(json.dumps(self.selection_catalogue))
        mutated["pools"]["go"]["recipes"][0]["model"] = "other-model"
        conflict = self.select_pure(catalogue=mutated, expected=issued["identity"])
        self.assertEqual(conflict["reason"], "identity_conflict")
        self.assertIn("model", conflict["identity_conflicts"])
        policy_change = _policy_document()
        policy_change["routing"]["acceptance_floor"] = "0.5 over last 20"
        self.policy_path.write_text(json.dumps(policy_change), encoding="utf-8")
        fresh_policy = pick.read_application_policy()
        self.assertNotEqual(self.policy.critical_sha256, fresh_policy.critical_sha256)
        self.policy = fresh_policy
        policy_conflict = self.select_pure(
            expected={"policy": issued["identity"]["policy"]})
        self.assertEqual(policy_conflict["reason"], "identity_conflict")
        self.assertEqual(policy_conflict["identity_conflicts"], ["policy"])
        self.assertEqual((self.rows("leases"), self.application_turns(),
                          self.rows("application_requests")), ([], [], []))
        self.assertEqual(len(self.posts), 0)

    def test_go_only_composition_and_worker_lifetime_unchanged(self):
        result = self.select_pure()
        self.assertEqual(result["coverage"], {
            "go": "selected",
            "glm": "pool_not_in_catalogue",
            "minimax": "pool_not_in_catalogue",
            "bailian": "pool_not_in_catalogue",
            "grok": "pool_not_in_catalogue",
            "cursor": "pool_not_in_catalogue",
            "codex-native": "not_ordered_for_class",
            "claude-native": "not_ordered_for_class",
            "ocfree": "policy_not_ordered",
        })
        guard = pick.launch_policy("go-codex", "build", "fixture-model",
                                   task_complexity="C2_COMPLEX_BOUNDED")
        self.assertEqual((guard["allowed"], guard["reason"]),
                         (False, "go_short_capability_only_for_c0_c1"))
        status, _, _ = self.request()
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
