"""Rev 5 P0 (Director A2) — LIVE durable canary receipt pin.

Pins the structure and the durability invariants of the committed secret-free
receipt ``integrations/t3/live_proof/t3_durable_canary_receipt.json``
(schema ``mastermind.t3_durable_canary_receipt/v1``), produced by
``integrations/t3/live_proof/t3_durable_canary.py`` against the REAL T3
server (environment m2studio) with SEPARATE OS PROCESSES per scenario sharing
one ``SQLiteT3AdapterStateStore``.

Invariants pinned here (each is a LIVE fact, not a unit test):

* exactly ONE minted thread per scenario run — S1's crash happened AFTER the
  receipt was durable, so P2 reattached with ZERO native launch/replay calls;
  S2's crash happened AFTER the native launch but BEFORE the receipt write,
  so P2 recovered through exactly ONE replay that returned P1's ORIGINAL
  thread (id equality + exactly one run on the thread);
* S3: a port reporting a DIFFERENT authenticated principal is refused LOCALLY
  (message mentions the authenticated namespace) with ZERO native calls;
* S4: the interrupt ledger NEVER claims a settle without a terminal
  observation — the live m2studio finding is that T3 reclaims interrupted
  scratch threads from the exact-run read path, so the settle evidence is
  upstream's own thread row (status "interrupted", settled false), never an
  inference;
* the reply text comes from the ASSISTANT item carrying the labeled nonce
  line (the prompt quotes the nonce too, and a human appended a manual
  "test" message to the S2 thread through the T3 app AFTER the run — the
  canary's own run stayed ordinal 1/completed); read-only ``verification``
  records re-observed each terminal thread with ZERO launch/replay calls;
* ids are consistent: distinct thread ids per run, at most the 3-thread
  budget, and every P2 thread id equals its P1 side-file record;
* the receipt is secret-free (no bearer material, no long opaque strings).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECEIPT = (
    REPO / "integrations" / "t3" / "live_proof" / "t3_durable_canary_receipt.json"
)

_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _receipt() -> dict:
    return json.loads(RECEIPT.read_text())


class LiveDurableCanaryReceiptStructureTests(unittest.TestCase):
    def test_schema_and_outcome(self) -> None:
        receipt = _receipt()
        self.assertEqual(
            receipt["schema"], "mastermind.t3_durable_canary_receipt/v1"
        )
        self.assertIn(receipt["outcome"], {"DONE", "PARTIAL"})
        self.assertEqual(receipt["label"], "MMOS durable canary")
        self.assertIsNone(receipt["blocked_gate"])
        self.assertTrue(receipt["started_at"])
        self.assertTrue(receipt["recorded_at"])

    def test_environment_and_provider(self) -> None:
        receipt = _receipt()
        env = receipt["environment"]
        self.assertEqual(env["label"], "m2studio")
        self.assertEqual(env["endpoint"], "http://127.0.0.1:3773/mcp")
        self.assertTrue(env["environmentId"])
        self.assertTrue(env["serverVersion"])
        provider = receipt["provider"]
        self.assertEqual(provider["providerInstanceId"], "capacity_fabric")
        self.assertEqual(provider["model"], "glm-5.3-flash")
        self.assertIn("capacity_fabric", receipt["providers_enabled"])
        # The legacy GLM2 provider is disabled at this server revision and
        # must not have been selected.
        disabled_ids = {row["id"] for row in receipt["providers_disabled"]}
        self.assertIn("GLM2", disabled_ids)

    def test_authenticated_namespace_is_a_projection_not_a_secret(self) -> None:
        ns = _receipt()["authenticated_namespace"]
        self.assertRegex(ns["principal"], _HEX16)
        self.assertIn("sha256", ns["principal_projection"])
        self.assertTrue(ns["qualified_namespace"].endswith(ns["principal"]))

    def test_store_is_scratch_not_executive_data_plane(self) -> None:
        store = _receipt()["store"]
        self.assertEqual(store["implementation"], "SQLiteT3AdapterStateStore")
        self.assertTrue(store["path"].endswith("state.sqlite3"))
        self.assertNotIn("data/control_plane", store["path"])
        self.assertRegex(store["sha256"], _HEX64)


class LiveDurableCanaryInvariantTests(unittest.TestCase):
    """One minted thread per run; recovery never minted a replacement."""

    def setUp(self) -> None:
        self.receipt = _receipt()
        self.scenarios = self.receipt["scenarios"]

    def test_verified_reply_texts_come_from_assistant_items(self) -> None:
        """Post-run verification scanned ASSISTANT items for the nonce.

        The canary prompt itself QUOTES the nonce as the instruction, and a
        human appended a manual message to the S2 thread after the run, so
        a tail-only capture would be wrong twice over.  Each verification
        record re-observed the terminal thread with ZERO launch/replay
        calls (retained-ref reattach) and found the labeled reply as an
        assistant item; the canary's own run stayed ordinal 1/completed.
        """
        for key in ("s1", "s2"):
            verify = (
                self.scenarios[key]["processes"]["p2"]["verification"]
            )
            counts = verify["reattach"]["counts_after_reattach"]
            self.assertEqual(counts["launch"], 0)
            self.assertEqual(counts["replay"], 0)
            self.assertTrue(verify["result_nonce_present"])
            self.assertTrue(verify["result_excerpt"].strip())
            self.assertEqual(verify["canary_run_status"], "completed")
            self.assertEqual(verify["thread_id"], self.scenarios[key]["thread_id"])

    def test_s1_crash_after_receipt_reattach_zero_native(self) -> None:
        s1 = self.scenarios["s1"]
        self.assertEqual(s1["outcome"], "PASS")
        p1, p2 = s1["processes"]["p1"], s1["processes"]["p2"]
        self.assertEqual(p1["crash_point"], "after_receipt_persist_before_ack")
        # P1's crash record (written by the store wrapper AFTER the receipt
        # committed) names the ONE natively launched thread it never ACKed;
        # the one-mint-per-run budget is pinned by the thread-id test below.
        self.assertTrue(p1["native"]["thread_id"])
        self.assertEqual(p1["durable_state"], "intent+receipt+original_ref COMMITTED")
        # P2 recovered from the DURABLE receipt with zero native calls.
        after = p2["reattach"]["counts_after_reattach"]
        self.assertEqual(after["launch"], 0)
        self.assertEqual(after["replay"], 0)
        self.assertEqual(after["read"], 0)
        self.assertTrue(p2["reattach"]["zero_native_launch_or_replay"])
        self.assertTrue(p2["reattach"]["returned_retained_ref"])
        self.assertTrue(p2["reattach"]["second_start_refused"])
        # The reattached execution IS the one P1 recorded before crashing.
        self.assertEqual(p2["thread_id"], p1["native"]["thread_id"])
        self.assertTrue(p2["thread_matches_p1_side_file"])
        # It ran to a terminal state and produced the labeled reply.
        self.assertEqual(p2["final_state"], "SUCCEEDED")
        self.assertTrue(p2["result_nonce_present"])
        self.assertIn("T3-CANARY-OK durable-s1", p2["result_excerpt"])
        self.assertTrue(p2["result_excerpt_source"])
        self.assertTrue(p2["single_run_observed"])
        self.assertTrue(p2["result_ledgered"])

    def test_s2_crash_after_launch_replays_original_thread(self) -> None:
        s2 = self.scenarios["s2"]
        self.assertEqual(s2["outcome"], "PASS")
        p1, p2 = s2["processes"]["p1"], s2["processes"]["p2"]
        self.assertEqual(p1["crash_point"], "after_launch_before_receipt_persist")
        self.assertEqual(p1["port_counts"]["launch"], 1)
        after = p2["recovery"]["counts_after_reattach"]
        # Exactly ONE replay — never a fresh launch mint — and no reads
        # before the adoption completed.
        self.assertEqual(after["replay"], 1)
        self.assertEqual(after["read"], 0)
        # Upstream idempotency returned P1's ORIGINAL thread: same id, and
        # the thread shows exactly one run (no duplicate execution).
        self.assertEqual(p2["thread_id"], p1["native"]["thread_id"])
        self.assertTrue(p2["thread_equals_p1_side_file"])
        self.assertTrue(p2["single_run_observed"])
        self.assertEqual(len(p2["runs_last_observed"]), 1)
        self.assertEqual(p2["final_state"], "SUCCEEDED")
        self.assertTrue(p2["result_nonce_present"])
        self.assertIn("T3-CANARY-OK durable-s2", p2["result_excerpt"])
        self.assertTrue(p2["result_excerpt_source"])
        # The replay carried the SAME idempotency identity as the intent.
        self.assertTrue(p2["recovery"]["client_request_id"])
        self.assertTrue(p2["recovery"]["request_namespace"])

    def test_s3_foreign_namespace_refused_with_zero_native_calls(self) -> None:
        s3 = self.scenarios["s3"]
        self.assertEqual(s3["outcome"], "PASS")
        payload = s3["processes"]["p"]
        self.assertEqual(len(payload["attempts"]), 2)
        for attempt in payload["attempts"]:
            self.assertTrue(attempt["refused"])
            self.assertTrue(attempt["namespace_message"])
        # No native call of any kind left the refused process.
        self.assertEqual(
            payload["port_counts"], {"launch": 0, "replay": 0, "read": 0, "interrupt": 0}
        )

    def test_s4_interrupt_honesty(self) -> None:
        """Requested-vs-settled honesty: a settle is never claimed without
        a terminal observation.

        Live m2studio facts this pins: the interrupt was sent while the run
        was genuinely RUNNING (live target); the ledger recorded
        requested-not-settled immediately after; the exact-run status loop
        ended on CANCELLING at its deadline (T3 kept processing the
        interrupt); and T3 reclaims interrupted scratch threads from the
        exact-run read path, so the settle EVIDENCE is upstream's own
        thread row (status "interrupted", upstream settled false).  The
        ledger never claimed a settle it did not observe.
        """
        s4 = self.scenarios["s4"]
        self.assertIn(s4["outcome"], {"PASS", "SKIPPED"})
        if s4["outcome"] == "SKIPPED":
            self.skipTest("S4 not run (optional lane)")
        payload = s4["processes"]["p"]
        self.assertTrue(s4.get("thread_id"))
        self.assertTrue(payload["was_live_at_interrupt"])
        self.assertEqual(payload["pre_interrupt_states"], ["RUNNING"])
        cancel = payload["cancel"]
        self.assertTrue(cancel["signal_sent"])
        self.assertTrue(cancel["requested_before_settle"])
        self.assertFalse(cancel["settle_claimed_without_terminal_observation"])
        self.assertIsNone(cancel["settled_state"])
        settle = payload["settle_observation"]
        terminal = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT",
                    "INVALID_RESULT"}
        if payload["final_state"] in terminal:
            self.assertEqual(
                settle["exact_run_read"], "terminal_observed_before_deadline"
            )
        else:
            # Deadline reached while the interrupt was still processing:
            # the settle evidence must come from upstream, never an inference.
            self.assertIn(
                settle["exact_run_read"],
                {"ok", "thread_no_longer_available"},
            )
            if settle["exact_run_read"] == "ok":
                self.assertIn(
                    settle["native_status"], {"completed", "interrupted", "failed"}
                )
            else:
                row = settle["project_row"]
                self.assertEqual(row["status"], "interrupted")
                self.assertFalse(row["settled"])
        # Upstream's own flags for the interrupted thread.
        row = settle.get("project_row") or {}
        if row:
            self.assertEqual(row["status"], "interrupted")
            self.assertFalse(row["settled"])
            self.assertIsNone(row["settled_at"])
        # The post-run verification pass stayed read-only.
        verify = payload["post_run_verification"]
        counts = verify["reattach"]["counts_after_reattach"]
        self.assertEqual(counts["launch"], 0)
        self.assertEqual(counts["replay"], 0)

    def test_thread_ids_distinct_and_within_budget(self) -> None:
        ids = [
            self.scenarios[key].get("thread_id")
            for key in ("s1", "s2", "s4")
            if self.scenarios[key].get("thread_id")
        ]
        self.assertGreaterEqual(len(ids), 2)  # s1 + s2 at minimum
        self.assertEqual(len(ids), len(set(ids)), "each run minted its own thread")
        self.assertLessEqual(len(ids), 3)
        self.assertEqual(self.receipt["threads_minted"], len(ids))
        self.assertEqual(self.receipt["threads_minted_ids"], ids)
        self.assertEqual(self.receipt["thread_budget"], 3)

    def test_every_role_process_reported_expected_exit(self) -> None:
        by_role = {p["role"]: p for p in self.receipt["processes"]}
        for role in ("prep", "s1-p2", "s2-p2", "s3", "s4"):
            self.assertTrue(by_role[role].get("ok"), f"{role} must exit cleanly")
        self.assertTrue(by_role["s1-p1"].get("ok"))  # expected crash code 90
        self.assertTrue(by_role["s2-p1"].get("ok"))  # expected crash code 91
        self.assertEqual(by_role["s1-p1"]["expected_returncode"], 90)
        self.assertEqual(by_role["s2-p1"]["expected_returncode"], 91)
        # Read-only verification roles, when present, exited cleanly.
        for role in ("s1-verify", "s2-verify", "s4-verify"):
            if role in by_role:
                self.assertTrue(by_role[role].get("ok"), f"{role} must exit cleanly")


class ReceiptIsSecretFreeTests(unittest.TestCase):
    def test_no_bearer_or_token_material(self) -> None:
        raw = RECEIPT.read_text()
        self.assertNotIn("Bearer", raw)
        self.assertNotIn("authorization", raw.lower())
        self.assertNotIn("access_token", raw)
        # No opaque credential-sized strings anywhere in the receipt.
        for match in re.finditer(r'"([^"\\]{120,})"', raw):
            self.fail(f"unpinned long string in receipt: {match.group(1)[:60]}…")

    def test_client_request_ids_are_sha256_not_credentials(self) -> None:
        receipt = _receipt()
        for key in ("s1", "s2"):
            crid = (
                receipt["scenarios"][key]["processes"]["p2"]
                .get("recovery", {})
                .get("client_request_id")
            )
            if crid:
                self.assertRegex(crid, _HEX64)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
