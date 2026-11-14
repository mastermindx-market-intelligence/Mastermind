"""Rev 5 P0 (Director A4) — LIVE durable canary r2 receipt pin.

Pins the committed secret-free receipt
``integrations/t3/live_proof/t3_durable_canary_receipt_r2.json`` (schema
``mastermind.t3_durable_canary_receipt/v1``, revision r2), produced by
``integrations/t3/live_proof/t3_durable_canary.py`` against the REAL T3 desktop
server (environment m2studio, T3 0.1.7) with SEPARATE OS PROCESSES per role
sharing one FRESH ``SQLiteT3AdapterStateStore`` — and, unlike r1, through the
adapter's REFERENCE live port ``T3McpToolPort`` (token-attested ``client:<sid>``
namespace, receipt echoes proven ONLY by the upstream thread-id derivation,
``recentRuns[].runId`` exact-run reads, re-audit N1 lost-reply classification,
exact-run interrupt, terminal result read).

Every invariant below is a LIVE fact recorded by the receipt (not a unit
test); mirrors ``tests/test_t3_durable_canary_receipt.py`` (r1), which stays
pinned to its own immutable receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "integrations" / "t3" / "live_proof"
RECEIPT = LIVE / "t3_durable_canary_receipt_r2.json"
R1_RECEIPT = LIVE / "t3_durable_canary_receipt.json"
#: r1 is immutable evidence: r2 never rewrote it.
R1_RECEIPT_SHA256 = "e18afad965eba1a2d3755760bc480158cb72774de449612eaa9ba915f24d0038"
#: The r2 receipt is immutable live evidence (re-audit #3 R5): pin its own bytes.
R2_RECEIPT_SHA256 = "29692b54b421c4913976f138ebbe232fc3b87ab4ba276db6b2d8d953cdeff3b1"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_THREAD = re.compile(r"^mcp:launch:[0-9a-f]{64}$")
_ZERO = {"launch": 0, "replay": 0, "read": 0, "interrupt": 0}


def _receipt() -> dict:
    return json.loads(RECEIPT.read_text())


class R2ReceiptStructureTests(unittest.TestCase):
    def test_schema_revision_port_and_outcome(self) -> None:
        receipt = _receipt()
        self.assertEqual(receipt["schema"], "mastermind.t3_durable_canary_receipt/v1")
        self.assertEqual(receipt["revision"], "r2")
        self.assertEqual(receipt["harness_port"], "T3McpToolPort")
        self.assertEqual(receipt["outcome"], "DONE")
        self.assertIsNone(receipt["blocked_gate"])
        self.assertEqual(receipt["label"], "MMOS durable canary r2")
        self.assertNotIn("assembled_from", receipt)  # written by the live driver itself

    def test_exact_adapter_commit_is_recorded(self) -> None:
        receipt = _receipt()
        code = receipt["code"]
        sha = receipt["adapter_commit_sha"]
        self.assertRegex(sha, _SHA1)
        self.assertEqual(code["adapter_commit_sha"], sha)
        self.assertTrue(code["adapter_and_harness_tree_clean"])
        self.assertRegex(code["adapter_file_sha256"], _HEX64)
        self.assertRegex(code["harness_file_sha256"], _HEX64)
        shown = subprocess.run(
            ["git", "-C", str(REPO), "show", f"{sha}:control_plane/t3_execution_adapter.py"],
            capture_output=True, check=False,
        )
        if shown.returncode != 0:
            self.skipTest("adapter commit not available in this checkout (shallow clone)")
        # The recorded adapter bytes ARE that commit's adapter file.
        self.assertEqual(hashlib.sha256(shown.stdout).hexdigest(), code["adapter_file_sha256"])

    def test_environment_provider_and_fresh_store(self) -> None:
        receipt = _receipt()
        env = receipt["environment"]
        self.assertEqual(env["label"], "m2studio")
        self.assertEqual(env["endpoint"], "http://127.0.0.1:3773/mcp")
        self.assertEqual(env["serverVersion"], "0.1.7")
        self.assertEqual(
            receipt["provider"]["providerInstanceId"] + "/" + receipt["provider"]["model"],
            "capacity_fabric/glm-5.3-flash",
        )
        store = receipt["store"]
        self.assertEqual(store["implementation"], "SQLiteT3AdapterStateStore")
        self.assertTrue(store["fresh_state_file"])
        self.assertTrue(store["path"].startswith("~/"))
        self.assertTrue(store["path"].endswith("t3_durable_canary_r2/batch/state.sqlite3"))
        self.assertNotIn("data/control_plane", store["path"])
        self.assertRegex(store["sha256"], _HEX64)

    def test_namespaces_are_sha256_projections_only(self) -> None:
        ns = _receipt()["authenticated_namespace"]
        self.assertRegex(ns["client_a_upstream_namespace_sha256"], _HEX64)
        self.assertRegex(ns["client_a_qualified_namespace_sha256"], _HEX64)
        self.assertIn("client:<auth session id>", ns["attestation"])

    def test_r2_receipt_bytes_are_pinned(self) -> None:
        self.assertEqual(hashlib.sha256(RECEIPT.read_bytes()).hexdigest(), R2_RECEIPT_SHA256)

    def test_r1_receipt_is_untouched(self) -> None:
        self.assertEqual(hashlib.sha256(R1_RECEIPT.read_bytes()).hexdigest(), R1_RECEIPT_SHA256)


class R2LiveScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = _receipt()
        self.s = self.receipt["scenarios"]

    def test_s1_crash_after_receipt_zero_native_reattach_and_final_item_collect(self) -> None:
        s1 = self.s["s1"]
        self.assertEqual(s1["outcome"], "PASS")
        p1, p2 = s1["processes"]["p1"], s1["processes"]["p2"]
        self.assertEqual(p1["crash_point"], "after_receipt_persist_before_ack")
        self.assertTrue(p1["upstream_echo_proven"])
        self.assertEqual(p1["durable_state"], "intent+receipt+original_ref COMMITTED")
        self.assertEqual(p2["reattach"]["counts_after_reattach"], _ZERO)
        self.assertEqual(p2["reattach"]["native_calls"], 0)
        self.assertTrue(p2["second_start"]["refused"])
        self.assertEqual(p2["second_start"]["error"], "T3LaunchClaimConflictError")
        self.assertEqual(p2["second_start"]["counts_after"], _ZERO)
        self.assertEqual(p2["thread_id"], p1["native"]["thread_id"])
        self.assertTrue(p2["thread_id_matches_client_a_derivation"])
        self.assertEqual(p2["final_state"], "SUCCEEDED")
        collect = p2["collect"]
        # N2 live: the ledgered reference names the run's FINAL assistant item.
        self.assertTrue(collect["ledger_names_final_assistant_item"])
        self.assertTrue(collect["result_ref"].endswith("/item/" + collect["final_assistant_item_id"]))
        self.assertIn("T3-CANARY-OK r2-s1", collect["result_text_tail"])
        self.assertEqual(collect["thread_run_count"], 1)

    def test_s2_same_client_replay_adopts_the_original_with_one_launch(self) -> None:
        s2 = self.s["s2"]
        self.assertEqual(s2["outcome"], "PASS")
        p1, p2 = s2["processes"]["p1"], s2["processes"]["p2"]
        self.assertEqual(p1["crash_point"], "after_launch_before_receipt_persist")
        self.assertEqual(p1["port_counts"]["launch"], 1)
        self.assertTrue(p1["upstream_echo_proven"])
        rec = p2["recovery"]
        self.assertEqual(rec["counts_after_reattach"],
                         {"launch": 0, "replay": 1, "read": 0, "interrupt": 0})
        self.assertTrue(rec["upstream_echo_proven"])
        self.assertRegex(rec["client_request_id"], _HEX64)
        self.assertEqual(p2["native_launch_calls_total"], 1)
        self.assertEqual(p2["thread_id"], p1["native"]["thread_id"])
        self.assertTrue(p2["thread_id_matches_client_a_derivation"])
        self.assertEqual(p2["collect"]["thread_run_count"], 1)
        self.assertEqual(p2["final_state"], "SUCCEEDED")
        self.assertIn("T3-CANARY-OK r2-s2", p2["collect"]["result_text_tail"])

    def test_s3_real_second_oauth_client(self) -> None:
        s3 = self.s["s3"]
        self.assertEqual(s3["outcome"], "PASS")
        self.assertEqual(s3["local_refusal"], "PASS")
        self.assertEqual(s3["upstream_namespace_proof"], "PASS")
        p = s3["processes"]["p"]
        self.assertNotEqual(p["client_b_upstream_namespace_sha256"],
                            p["client_a_upstream_namespace_sha256"])
        self.assertEqual(len(p["attempts"]), 4)
        for attempt in p["attempts"]:
            self.assertTrue(attempt["refused"])
            self.assertEqual(attempt["native_calls"], 0)
            if attempt["operation"] == "reattach":
                self.assertEqual(attempt["reason"], "PRINCIPAL_MISMATCH")
            else:
                self.assertEqual(attempt["error"], "T3LaunchClaimConflictError")
        self.assertEqual(p["adapter_port_calls"], 0)
        # Upstream: the SAME clientRequestId under the second OAuth client
        # minted a DIFFERENT thread — namespace = OAuth client, live.
        self.assertEqual(p["same_key_client_request_id"],
                         self.s["s1"]["processes"]["p1"]["client_request_id"])
        direct = p["direct_upstream_probe"]
        self.assertTrue(direct["attempted"])
        self.assertFalse(direct["message_sent"])
        self.assertIsNone(direct["run_id"])  # no message: no model turn
        self.assertTrue(direct["differs_from_s1_thread"])
        self.assertTrue(direct["matches_client_b_derivation"])
        self.assertTrue(direct["client_a_derivation_is_s1_thread"])
        self.assertNotEqual(direct["thread_id"], self.s["s1"]["thread_id"])

    def test_s4_exact_run_interrupt_settles_only_on_observation(self) -> None:
        s4 = self.s["s4"]
        self.assertEqual(s4["outcome"], "PASS")
        p = s4["processes"]["p"]
        self.assertTrue(p["was_live_at_interrupt"])
        self.assertEqual(p["pre_interrupt_states"][-1], "RUNNING")
        interrupt = p["interrupt"]
        self.assertTrue(interrupt["payload_thread_matches"])
        self.assertTrue(interrupt["payload_run_matches"])
        self.assertTrue(interrupt["upstream_echo_verified"])
        self.assertTrue(interrupt["signal_sent"])
        after, final = p["ledger_after_cancel"], p["ledger_final"]
        self.assertTrue(after["requested"])
        self.assertFalse(after["settled"])  # requested, not yet settled
        self.assertIsNone(after["settled_state"])
        self.assertTrue(final["settled"])
        self.assertEqual(final["settled_state"], "CANCELLED")
        self.assertGreater(final["settled_at"], final["requested_at"])
        self.assertEqual(p["status_sequence_after_interrupt"], ["CANCELLING", "CANCELLED"])
        self.assertEqual(p["final_state"], "CANCELLED")
        self.assertFalse(p["honesty"]["settle_claimed_without_terminal_observation"])
        # The settle came from the exact run's OWN upstream status (D1).
        settle = p["settle_observation"]
        self.assertEqual(settle["exact_run_read"], "ok")
        self.assertEqual(settle["exact_run_native_status"], "interrupted")
        self.assertEqual(p["port_counts"]["interrupt"], 1)

    def test_s5_post_commit_is_error_keeps_the_intent_and_replay_adopts(self) -> None:
        s5 = self.s["s5"]
        self.assertEqual(s5["outcome"], "PASS")
        p1, p2 = s5["processes"]["p1"], s5["processes"]["p2"]
        self.assertEqual(p1["start_outcome"], "T3LaunchEffectUnknownError")
        self.assertFalse(p1["classifier_definitive_refusal"])
        self.assertTrue(p1["intent_kept"])
        self.assertFalse(p1["receipt_persisted"])
        self.assertTrue(p1["committed_thread_matches_client_a_derivation"])
        self.assertEqual(p1["port_counts"]["launch"], 1)
        self.assertEqual(p2["recovery"]["counts_after_reattach"],
                         {"launch": 0, "replay": 1, "read": 0, "interrupt": 0})
        self.assertTrue(p2["recovery"]["upstream_echo_proven"])
        self.assertTrue(p2["adopted_original_committed_thread"])
        self.assertEqual(p2["thread_id"], p1["transport_observed_committed_thread"]["thread_id"])
        self.assertEqual(p2["native_launch_calls_total"], 1)
        self.assertEqual(p2["collect"]["thread_run_count"], 1)
        self.assertEqual(p2["final_state"], "SUCCEEDED")
        self.assertIn("T3-CANARY-OK r2-s5", p2["collect"]["result_text_tail"])

    def test_thread_budget_and_ids(self) -> None:
        ids = [self.s[k]["thread_id"] for k in ("s1", "s2", "s3", "s4", "s5")]
        for thread_id in ids:
            self.assertRegex(thread_id, _THREAD)
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(self.receipt["threads_minted_ids"], ids)
        self.assertEqual(self.receipt["threads_minted"], 5)
        self.assertEqual(self.receipt["thread_budget"], 5)
        self.assertEqual(self.receipt["budget_reservations"],
                         ["s1-p1", "s2-p1", "s3", "s4", "s5-p1"])

    def test_every_role_process_exited_as_expected(self) -> None:
        by_role = {p["role"]: p for p in self.receipt["processes"]}
        expected = {"prep": 0, "s1-p1": 90, "s1-p2": 0, "s2-p1": 91, "s2-p2": 0,
                    "s3": 0, "s4": 0, "s5-p1": 0, "s5-p2": 0}
        self.assertEqual(set(by_role), set(expected))
        for role, rc in expected.items():
            self.assertEqual(by_role[role]["returncode"], rc, role)
            self.assertTrue(by_role[role]["ok"], role)


class R2ReceiptIsSecretFreeTests(unittest.TestCase):
    def test_no_credentials_raw_namespaces_or_home_paths(self) -> None:
        raw = RECEIPT.read_text()
        for needle in ("Bearer", "access_token", "authorization", "Authorization",
                       "/Users/", '"events"', "pairing", '"client:'):
            self.assertNotIn(needle, raw)
        # Session tokens are base64url(JSON claims) + "." + signature; JSON
        # claims encode to an "eyJ" prefix.  None may appear.
        self.assertNotIn("eyJ", raw)

    def test_long_strings_are_only_derived_ids(self) -> None:
        """Long strings exist (thread/run/item refs) but are all derived ids."""
        allowed = re.compile(r"^(t3://thread/)?mcp:launch:[0-9a-f]{64}|^run:thread:mcp%3Alaunch%3A[0-9a-f]{64}")
        for match in re.finditer(r'"([^"\\]{120,})"', RECEIPT.read_text()):
            self.assertRegex(match.group(1), allowed)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
