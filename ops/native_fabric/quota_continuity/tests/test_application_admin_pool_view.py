"""Real authenticated metadata GET over retained A/SQLite; no live provider."""
from contextlib import ExitStack
from dataclasses import replace
import copy
import http.client
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from test_application_turn_selection_admission import SelectedIngressFixture
from test_go_application_handler_composition import SERVICE_TOKEN, CONTROLLER_TOKEN
from test_application_turn_admission import ROOT
import lease_broker
import pick


class AdminPoolViewFixture(SelectedIngressFixture):
    def setUp(self):
        super().setUp()
        ext = Path(self.go.__file__).parent.parent
        for name in ("go_lease_gateway.py", "go_lease_capability.py"):
            (ext / name).write_bytes((ROOT / "candidate" / name).read_bytes())
        self.enable_metadata()

    def enable_metadata(self, allowed=True):
        self.server.shutdown()
        self.server.server_close()
        self.service = replace(self.service, admin_pool_view=allowed)
        self.server = self.go.make_server(self.router, lease_gateway=self.gateway, application_services=(self.service,))
        self.server.handle_error = lambda *args: None
        self._serve(self.server)

    def view(self, token=SERVICE_TOKEN, path="/application-pools/view", headers=None, duplicate=False):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.putrequest("GET", path)
            if token is not None:
                connection.putheader("Authorization", "Bearer " + token)
            if duplicate:
                connection.putheader("Authorization", "Bearer " + SERVICE_TOKEN)
            for key, value in (headers or {}).items():
                connection.putheader(key, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    @staticmethod
    def go_row(body):
        return next(row for row in body["pools"] if row["pool"] == "go")


class AdminPoolViewTests(AdminPoolViewFixture):
    def test_real_view_has_nine_pools_original_timestamps_and_no_effects(self):
        for pool in pick._APPLICATION_POOL_ORDER:
            self.document["providers"].setdefault(pool, {"enabled": True,
                "accounts": [{"name": pool + "-fixture", "per_account_cap": 3,
                              "api_key": "secret-never-exported", "usage": {"raw": "private"}}]})
        self.save()
        before = {table: self.rows(table) for table in ("leases", "application_turns", "application_requests", "waiters")}
        with ExitStack() as stack:
            for target, name in ((lease_broker.Broker, "__init__"), (self.broker, "_conn"),
                    (self.broker, "_gc_locked"), (self.broker, "snapshot"), (self.broker, "_lock"),
                    (self.gateway, "begin_application"), (self.gateway, "prepare_application"),
                    (self.gateway, "close_application_turn"), (self.router, "refresh"),
                    (self.router, "choose"), (self.router, "status"), (pick, "select_application")):
                stack.enter_context(patch.object(target, name, side_effect=AssertionError("metadata side effect")))
            status, body, headers = self.view()
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual([p["pool"] for p in body["pools"]], list(pick._APPLICATION_POOL_ORDER))
        self.assertEqual((body["observed_at"], body["stale_after"]), (1000, 1005))
        self.assertIs(body["execution_authorized"], False)
        self.assertIs(body["requires_fresh_admission"], True)
        self.assertEqual(body["coverage"]["provider_quota"], "unobserved")
        self.assertEqual(self.go_row(body)["models"][0]["ledger_room"], 4)
        self.assertNotIn("ledger_room", self.go_row(body))  # shared account models are not summed
        for pool in body["pools"]:
            if pool["pool"] != "go":
                self.assertEqual(pool["models"], [])
                self.assertEqual(pool["application_state"], "unqualified")
        wire = json.dumps(body)
        for private in ("secret-never-exported", "api_key", "account-a", "MACRO_APPLICATION_TOKEN", str(self.directory)):
            self.assertNotIn(private, wire)
        self.assertEqual(before, {table: self.rows(table) for table in before})
        self.assertEqual((self.gets, self.posts, self.usage_rows()), ([], [], []))

    def test_authentication_and_explicit_permission_precede_all_reads(self):
        with patch.object(self.gateway, "application_pool_view", side_effect=AssertionError("unauthorized read")) as observer:
            for token in (None, "wrong", CONTROLLER_TOKEN, "v1.worker-token"):
                self.assertEqual(self.view(token)[0], 401)
            self.assertEqual(self.view(duplicate=True)[0], 401)
            self.enable_metadata(False)
            self.assertEqual(self.view()[0], 403)
            observer.assert_not_called()

    def test_no_request_context_can_broaden_the_metadata_scope(self):
        with patch.object(self.gateway, "application_pool_view", side_effect=AssertionError("invalid request read")):
            self.assertEqual(self.view(path="/application-pools/view?pool=glm")[0], 400)
            for headers in ({"Content-Length": "1"}, {"Transfer-Encoding": "chunked"},
                            {"X-MM-Application-Turn-ID": "forged"}, {"X-MM-Admin-Permission": "1"}):
                self.assertEqual(self.view(headers=headers)[0], 400)

    def test_expired_or_disabled_grant_is_visible_without_inference_permission(self):
        self.grant["expires_at"] = self.clock[0] - 1
        self.save()
        status, body, _ = self.view()
        self.assertEqual(status, 200)
        for model in self.go_row(body)["models"]:
            self.assertEqual(model["application_state"], "held")
            self.assertEqual(model["blockers"], ["grant_unavailable"])
            self.assertIsNone(model["ledger_room"])

    def test_unknown_effect_remains_held_after_expiry_without_gc(self):
        self.reset = True
        self.assertEqual(self.request()[0], 503)
        self.clock[0] += 10000
        before = {table: self.rows(table) for table in ("leases", "application_turns", "application_requests")}
        status, body, _ = self.view()
        self.assertEqual(status, 200)
        self.assertEqual(self.go_row(body)["held_leases"], 1)
        self.assertEqual(before, {table: self.rows(table) for table in before})

    def test_fresh_same_mtime_inventory_and_disabled_account_room(self):
        self.assertEqual(self.view()[0], 200)
        old = self.accounts.stat()
        self.document["providers"]["go"]["accounts"][0]["enabled"] = False
        self.save()
        os.utime(self.accounts, ns=(old.st_atime_ns, old.st_mtime_ns))
        status, body, _ = self.view()
        self.assertEqual(status, 200)
        row = self.go_row(body)
        self.assertEqual((row["configured_accounts"], row["enabled_accounts"]), (2, 1))
        self.assertTrue(all(m["ledger_room"] == 2 for m in row["models"]))

    def test_missing_pool_inventory_is_null_and_not_a_zero_account_claim(self):
        status, body, _ = self.view()
        self.assertEqual(status, 200)
        for row in body["pools"]:
            if row["pool"] != "go":
                self.assertIsNone(row["configured_accounts"])
                self.assertIsNone(row["enabled"])
                self.assertIn("account_inventory_unobserved", row["blockers"])

    def test_corrupt_or_unvalidated_ungranted_inventory_refuses_without_cache(self):
        original = self.accounts.read_bytes()
        bad = copy.deepcopy(self.document)
        bad["providers"]["glm"] = {"enabled": True, "accounts": [{"name": "duplicate", "per_account_cap": 1},
                                                                  {"name": "duplicate", "per_account_cap": 1}]}
        for raw in (b'{"schema":"x","schema":"y"}', json.dumps(bad).encode()):
            self.accounts.write_bytes(raw)
            self.assertEqual(self.view()[0], 503)
        self.accounts.write_bytes(original)
        self.assertEqual(self.view()[0], 200)
        self.accounts.unlink()
        self.assertEqual(self.view()[0], 503)

    def test_missing_or_replaced_db_never_constructs_a_fallback_owner(self):
        path = Path(self.broker.db_path)
        original = path.with_suffix(".original")
        path.rename(original)
        with patch.object(lease_broker.Broker, "__init__", side_effect=AssertionError("replacement owner")):
            self.assertEqual(self.view()[0], 503)
            self.assertFalse(path.exists())
            sqlite3.connect(path).close()
            self.assertEqual(self.view()[0], 503)
        path.unlink()
        original.rename(path)

    def test_unpriced_wire_denied_and_training_models_are_not_qualified(self):
        priced = copy.deepcopy(self.router.prices)
        for fault in ("unpriced", "wire", "training"):
            self.router.prices = copy.deepcopy(priced)
            self.router.wire_compat = {}
            if fault == "unpriced":
                del self.router.prices["models"]["fixture-model"]
                self.router.prices["unpriced"].append("fixture-model")
            elif fault == "wire":
                self.router.wire_compat["fixture-model"] = ["chat"]
            else:
                self.router.prices["models"]["fixture-model"]["training_consent"] = True
                self.router.allow_training = False
            status, body, _ = self.view()
            self.assertEqual(status, 200)
            model = next(m for m in self.go_row(body)["models"] if m["model"] == "fixture-model")
            self.assertEqual(model["transport_state"], "unqualified")
            self.assertIsNone(model["ledger_room"])
            self.assertEqual(self.request()[0], 400)
        self.assert_no_effect()

    def test_one_accounts_read_and_readonly_connection_for_all_models(self):
        original = lease_broker._read_application_accounts
        with patch.object(lease_broker, "_read_application_accounts", wraps=original) as read:
            self.assertEqual(self.view()[0], 200)
            self.assertEqual(read.call_count, 1)
        connection = self.gateway._connection()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM leases")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
