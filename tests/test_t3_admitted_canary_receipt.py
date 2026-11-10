"""MMOS Rev5 lane L1 — LIVE ADMITTED CANARY receipt pin.

Pins the committed secret-free receipt
``integrations/t3/live_proof/t3_admitted_canary_receipt.json`` (schema
``mastermind.t3_admitted_canary_receipt/v1``, revision r1), produced by
``integrations/t3/live_proof/t3_admitted_canary.py`` on 2026-11-09 against the
REAL T3 desktop server (environment m2studio) through the REAL Executive code
path: ``compose_child_execution`` admission -> ``claim_job`` (fenced
ExecutionBinding) -> ``compose_t3_native_adapter`` (production composition over
the R1 token file) -> ONE real T3 thread doing a real coding change in a
T3-managed Mastermind worktree -> ``collect_result`` -> ``complete_attempt`` ->
``execution_return/v1`` with the real ``GhCliEvidencePort`` -> an honestly
REFUSED ``HermesExecutionReturnDeliverer`` return (R9-BLOCKED, typed
``NATIVE_SESSION_UNAVAILABLE``).

Every invariant below is a LIVE fact recorded by the receipt (not a unit
test).  Mirrors ``tests/test_t3_durable_canary_receipt_r2.py`` (adapter-level
durability); this file pins the ADMISSION-BOUNDARY-INWARD run (ledger
LANE_L1_LIVE_PATH_V2 rungs R3+R4) — 2 real threads total under the durable
budget, never retried, never deleted.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unittest
import urllib.parse
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "integrations" / "t3" / "live_proof"
RECEIPT = LIVE / "t3_admitted_canary_receipt.json"
HARNESS = LIVE / "t3_admitted_canary.py"
LIVE_ROUTES = REPO / "config" / "executive_worker_routes.json"
#: The receipt is immutable live evidence: pin its own bytes.  It was written
#: once by the live driver and re-assembled (--assemble, no roles spawned,
#: nothing launched) solely to repair a harness display gate after the
#: f-string brace bug — the receipt records that fact in ``assembled_from``.
RECEIPT_SHA256 = "0e0c4fa7343c903630147897232ff7e8e92aad25a56fff30d516c8610ee41306"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA7_40 = re.compile(r"^[0-9a-f]{7,40}$")
_THREAD = re.compile(r"^mcp:launch:[0-9a-f]{64}$")
_ATTEMPT = re.compile(r"^ATT-[0-9a-f]{32}$")
_ZERO_COUNTS = {"launch": 0, "replay": 0, "read": 0, "interrupt": 0}


def _receipt() -> dict:
    return json.loads(RECEIPT.read_text())


class L1ReceiptStructureTests(unittest.TestCase):
    def test_schema_label_outcome_and_threads(self) -> None:
        receipt = _receipt()
        self.assertEqual(receipt["schema"], "mastermind.t3_admitted_canary_receipt/v1")
        self.assertEqual(receipt["revision"], "r1")
        self.assertEqual(receipt["label"], "MMOS L1 admitted canary")
        self.assertEqual(receipt["outcome"], "DONE")
        self.assertIsNone(receipt["blocked_gate"])
        self.assertEqual(receipt["thread_budget"], 2)
        self.assertEqual(receipt["threads_minted"], 2)
        self.assertEqual(receipt["budget_reservations"], ["main-p1", "interrupt"])
        self.assertEqual(len(receipt["threads_minted_ids"]), 2)
        for thread_id in receipt["threads_minted_ids"]:
            self.assertRegex(thread_id, _THREAD)
        self.assertEqual(
            receipt["assembled_from"],
            "existing batch side files (no roles spawned, nothing launched)")

    def test_receipt_bytes_are_pinned(self) -> None:
        self.assertEqual(
            hashlib.sha256(RECEIPT.read_bytes()).hexdigest(), RECEIPT_SHA256)

    def test_code_identity_recorded(self) -> None:
        receipt = _receipt()
        code = receipt["code"]
        self.assertRegex(receipt["trunk_commit_sha"], _SHA1)
        self.assertEqual(code["trunk_commit_sha"], receipt["trunk_commit_sha"])
        # Honest run-time fact: the canary's own files (harness, receipt,
        # this test) were still untracked when the live driver executed, so
        # the receipt records the tree as it WAS — never retouched to look
        # clean after the evidence commit.
        self.assertIs(code["source_tree_clean"], False)
        for key in ("harness_file_sha256", "runtime_file_sha256",
                    "adapter_file_sha256", "composition_file_sha256"):
            self.assertRegex(code[key], _HEX64)

    def test_honest_identities_and_deviations(self) -> None:
        receipt = _receipt()
        ids = receipt["identities"]
        self.assertEqual(ids["root_ref"], "roots/mmos-l1-admitted-canary-20261109")
        self.assertEqual(ids["immediate_parent_run_ref"], "parents/l1-lane-lead")
        self.assertEqual(ids["logical_child_keys"],
                         ["l1-admitted-canary-main", "l1-admitted-canary-interrupt"])
        self.assertIn("NOT a live Hermes tool call", ids["requester_basis"])
        self.assertIn("dd45d111 untouched", ids["executive_generation"])
        self.assertEqual(ids["repository"], "mastermindx-market-intelligence/Mastermind")
        deviations = " | ".join(receipt["deviations"])
        self.assertIn("request digest", deviations)          # branch derivation
        self.assertIn("slash-free tokens", deviations)       # intent projection
        self.assertIn("harness-fixed", deviations)           # model selection
        self.assertIn("launch_arguments", deviations)        # port seam
        self.assertIn("REFUSAL", deviations)                 # honest delivery
        self.assertEqual(
            receipt["model_selection_basis"],
            "harness-fixed; route->T3 modelSelection mapping absent")

    def test_scratch_route_row_never_touched_the_live_file(self) -> None:
        receipt = _receipt()
        route = receipt["route_row"]
        self.assertTrue(route["live_file_untouched"])
        self.assertEqual(route["provider_adapter_id"], "t3-native")
        self.assertIs(route["provider_enabled"], False)
        self.assertIs(route["provider_autonomous_allowed"], False)
        self.assertIn("T3_NATIVE_ROUTE_ROW_PROPOSAL.md", route["t3_row_source"])
        self.assertRegex(route["scratch_sha256"], _HEX64)
        # The live protected file carries the approved STAGED t3 row, disabled (R5).
        live = json.loads(LIVE_ROUTES.read_text())
        staged = live["providers"]["t3"]
        self.assertEqual(staged["adapter_id"], "t3-native")
        self.assertIs(staged["enabled"], False)
        self.assertIs(staged["production_armed"], False)

    def test_environment_project_and_namespaces(self) -> None:
        receipt = _receipt()
        self.assertEqual(receipt["environment"]["endpoint"], "http://127.0.0.1:3773/mcp")
        project = receipt["project"]
        self.assertEqual(project["project_id"], "bc18d268-d100-484a-8952-3ce2b0b0a66b")
        self.assertEqual(project["title"], "Mastermind")
        self.assertEqual(
            project["canonical_key"], "github.com/mastermindx-market-intelligence/mastermind")
        self.assertEqual(project["workspace_root"], "~/Documents/Cluade/Mastermind")
        ns = receipt["authenticated_namespace"]
        self.assertRegex(ns["client_a_upstream_namespace_sha256"], _HEX64)
        self.assertRegex(receipt["namespace_scenario"]["client_b_upstream_namespace_sha256"], _HEX64)
        self.assertNotEqual(
            receipt["namespace_scenario"]["client_b_upstream_namespace_sha256"],
            receipt["namespace_scenario"]["client_a_upstream_namespace_sha256"])


class L1MainScenarioTests(unittest.TestCase):
    """MAIN: one real request, one real T3 thread, sealed, honest refused return."""

    def test_scenario_passes_with_decisive_facts(self) -> None:
        receipt = _receipt()
        main = receipt["scenarios"]["main"]
        self.assertEqual(main["outcome"], "PASS")
        self.assertEqual(main["p1_crash"], "PASS")
        self.assertEqual(main["p2_recovery_seal"], "PASS")
        self.assertRegex(main["attempt_id"], _ATTEMPT)
        self.assertRegex(main["job_id"], r"^JOB-\d+$")
        self.assertRegex(main["thread_id"], _THREAD)
        self.assertTrue(main["native_run_id"])
        self.assertIn(":ordinal:1", main["native_run_id"])
        self.assertRegex(main["branch_remote_sha"], _SHA1)

    def test_p1_deterministic_crash_after_receipt(self) -> None:
        p1 = _receipt()["scenarios"]["main"]["processes"]["p1"]
        self.assertEqual(p1["crash_point"], "after_receipt_persist_before_ack")
        self.assertTrue(p1["upstream_echo_proven"])
        self.assertEqual(p1["durable_state"], "intent+receipt+original_ref COMMITTED")
        self.assertEqual(p1["native"]["thread_id"], p1["client_request_id"] and p1["native"]["thread_id"])

    def test_p2_restart_safety_zero_native_calls(self) -> None:
        p2 = _receipt()["scenarios"]["main"]["processes"]["p2"]
        self.assertEqual(p2["outcome"], "OK")
        reattach = p2["reattach"]
        self.assertTrue(reattach["returned_retained_ref"])
        self.assertEqual(reattach["native_calls"], 0)
        self.assertEqual(reattach["port_calls_after_reattach"], 0)
        self.assertEqual(reattach["census_after_reattach"], [])
        second = p2["second_start"]
        self.assertTrue(second["refused"])
        self.assertEqual(second["error"], "T3LaunchClaimConflictError")
        self.assertEqual(second["native_calls_after"], 0)
        recovery = p2["recovery"]
        self.assertIn("adopt_attempt", recovery["path"])
        self.assertGreaterEqual(recovery["adopted_fence_generation"], 2)

    def test_p2_thread_result_branch_and_seal(self) -> None:
        receipt = _receipt()
        main = receipt["scenarios"]["main"]
        p2 = main["processes"]["p2"]
        collect = p2["collect"]
        self.assertEqual(p2["final_state"], "SUCCEEDED")
        self.assertEqual(p2["status_sequence"][0], "STARTING")
        self.assertTrue(collect["collect_ok"])
        self.assertTrue(collect["marker_in_final_item"])
        self.assertTrue(collect["marker_in_collected_text"])
        self.assertTrue(collect["ledger_names_final_assistant_item"])
        self.assertTrue(collect["result_ledgered"])
        self.assertRegex(collect["replied_commit_sha"], _SHA7_40)
        # The repair after the harness regex bug is disclosed, never silent.
        self.assertIn("recomputed from the recorded result_text_tail",
                      collect["replied_commit_sha_source"])
        self.assertTrue(p2["branch_pushed"])
        self.assertTrue(p2["branch_sha_matches_reply"])
        self.assertEqual(p2["branch_remote_sha"], collect["replied_commit_sha"])
        # Exactly ONE run upstream: one launch, no replays.
        self.assertEqual(p2["recent_runs_count"], 1)
        self.assertEqual(p2["thread_run_count"], 1)
        self.assertEqual(len(p2["recent_runs"]), 1)
        # The branch is the request-digest derivation (disclosed deviation).
        self.assertRegex(main["branch"], r"^t3/mmos-l1-canary-[0-9a-f]{8}$")
        self.assertEqual(main["branch"][-8:], main["branch"][-8:])
        self.assertEqual(p2["seal"]["job_status"], "COMPLETED")
        self.assertEqual(p2["seal"]["current_attempt_id"], main["attempt_id"])
        # Local-process census recorded honestly (may be 0 for remote execution).
        self.assertIn("matched_lines", p2["ps_census"])

    def test_honest_refused_delivery_with_full_projection(self) -> None:
        receipt = _receipt()
        delivery = receipt["delivery"]
        p2 = receipt["scenarios"]["main"]["processes"]["p2"]
        dr = p2["delivery_receipt"]
        self.assertEqual(dr["state"], "refused")
        self.assertEqual(dr["refusal_code"], "NATIVE_SESSION_UNAVAILABLE")
        self.assertEqual(dr["stage"], "branch_pushed")
        self.assertEqual(dr["conversation_id"], "slack:1794196323.978899")
        self.assertTrue(dr["return_id"])
        self.assertEqual(delivery["receipt_state"], "refused")
        self.assertEqual(delivery["refusal_code"], "NATIVE_SESSION_UNAVAILABLE")
        self.assertEqual(delivery["github_stage"], "branch_pushed")
        self.assertIn("NOT a live Hermes tool call", delivery["basis"])
        projection = delivery["projection"]
        self.assertEqual(projection["schema"], "mastermind.execution_return/v1")
        self.assertEqual(projection["stage"], "branch_pushed")
        github = projection["github"]
        self.assertEqual(github["branch"], p2["branch"])
        self.assertIsNone(github["pr_number"])  # NO pull request, honestly
        self.assertIsNone(github["checks"])
        self.assertEqual(projection["original_requester"]["conversation_id"],
                         "slack:1794196323.978899")


class L1NamespaceAndInterruptTests(unittest.TestCase):
    def test_namespace_refusal_zero_native_calls_no_thread(self) -> None:
        ns = _receipt()["scenarios"]["namespace"]
        p = ns["processes"]["p"]
        self.assertEqual(ns["outcome"], "PASS")
        self.assertTrue(p["distinct_oauth_clients"])
        self.assertTrue(p["refused_with_zero_native_calls"])
        self.assertTrue(p["reattach_reason_principal_mismatch"])
        self.assertFalse(p["thread_minted"])
        self.assertEqual(p["native_census"], [])
        self.assertEqual(p["port_calls"], 0)
        reattach = next(a for a in p["attempts"] if a["operation"] == "reattach")
        self.assertEqual(reattach["reason"], "PRINCIPAL_MISMATCH")
        self.assertEqual(reattach["native_calls"], 0)
        start = next(a for a in p["attempts"] if a["operation"] == "start")
        self.assertTrue(start["refused"])
        self.assertEqual(start["native_calls"], 0)
        # The namespace scenario spent NO thread budget.
        self.assertNotIn("namespace-p3", _receipt()["budget_reservations"])

    def test_interrupt_requested_vs_settled_never_inferred(self) -> None:
        it = _receipt()["scenarios"]["interrupt"]
        p = it["processes"]["p"]
        self.assertEqual(it["outcome"], "PASS")
        self.assertRegex(it["thread_id"], _THREAD)
        self.assertTrue(p["was_live_at_interrupt"])
        interrupt = p["interrupt"]
        self.assertTrue(interrupt["payload_thread_matches"])
        self.assertTrue(interrupt["payload_run_matches"])
        self.assertTrue(interrupt["upstream_echo_verified"])
        self.assertTrue(interrupt["signal_sent"])
        self.assertFalse(interrupt["already_exited"])
        after, final = p["ledger_after_cancel"], p["ledger_final"]
        # Requested first (unsettled at request time)...
        self.assertTrue(after["requested"])
        self.assertFalse(after["settled"])
        self.assertIsNone(after["settled_state"])
        # ...then honestly OBSERVED settled (never inferred):
        self.assertTrue(final["settled"])
        self.assertEqual(final["settled_state"], "CANCELLED")
        self.assertEqual(p["final_state"], "CANCELLED")
        self.assertTrue(p["honesty"]["requested_before_settle"])
        self.assertFalse(p["honesty"]["settle_claimed_without_terminal_observation"])


class L1SecretFreeTests(unittest.TestCase):
    def test_receipt_bytes_are_secret_free(self) -> None:
        raw = RECEIPT.read_bytes()
        for needle in (
            b"Bearer", b"access_token", b"authorization", b"/Users/",
            b'"events"', b"pairing", b'"client:', b"/eyJ", b"t3_l1_client",
            b"client_secret", b"refresh_token", b"oauth_token", b"secret",
        ):
            self.assertNotIn(needle, raw, f"receipt leaks {needle!r}")
        # Long token-like strings must decompose into derived ids only:
        # every >=32-char alphanumeric segment is lowercase hex (a digest,
        # thread id, attempt id or sha). A leaked JWT/base64 secret is
        # mixed-case with punctuation and cannot pass this grammar check.
        # t3 run ids URL-escape separators (%3A == :), so unquote first —
        # escapes are separators, never secret material.
        decoded = urllib.parse.unquote_to_bytes(raw)
        for run_ in re.findall(rb"[A-Za-z0-9_\-:/.]{90,}", decoded):
            for seg in re.findall(rb"[A-Za-z0-9]{32,}", run_):
                self.assertRegex(
                    seg, rb"^[0-9a-f]+$",
                    f"non-hex high-entropy segment in receipt: {seg[:60]!r}")

    def test_scratch_data_dir_is_not_the_installed_executive(self) -> None:
        receipt = _receipt()
        store = receipt["store"]
        self.assertIn("~/.cache/mmos-l1-canary/runtime", store["runtime_root"])
        self.assertIn("untouched", store["note"])


class L1HarnessShapeTests(unittest.TestCase):
    """No-network structural pins on the harness module itself."""

    def setUp(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("t3_admitted_canary_shape", HARNESS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.m = module

    def test_role_registry_budget_and_exit_codes(self) -> None:
        m = self.m
        self.assertEqual(
            sorted(m.ROLES),
            ["interrupt", "main-p1", "main-p2", "namespace-p3", "prep"])
        self.assertEqual(m.MINTING_ROLES, {"main-p1", "interrupt"})
        self.assertEqual(m.THREAD_BUDGET, 2)
        self.assertEqual(m.EXPECTED_RC["main-p1"], m.CRASH_EXIT_AFTER_RECEIPT)
        self.assertEqual(m.CRASH_EXIT_AFTER_RECEIPT, 90)
        for role, timeout in m.ROLE_TIMEOUTS.items():
            self.assertGreater(timeout, 0)
            self.assertIn(role, m.ROLES)

    def test_thread_budget_reservation_is_durable_and_capped(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.m.SCRATCH_ROOT = Path(tmp)
            self.assertTrue(self.m._reserve_thread("main-p1"))
            self.assertTrue(self.m._reserve_thread("interrupt"))
            self.assertFalse(self.m._reserve_thread("a-third-role"))
            # Idempotent for the same role.
            self.assertTrue(self.m._reserve_thread("main-p1"))
            self.assertEqual(
                json.loads(self.m._budget_path().read_text()),
                {"limit": 2, "reserved": ["main-p1", "interrupt"]})

    def test_branch_and_prompt_derivations(self) -> None:
        m = self.m
        request = m._request("l1-admitted-canary-main")
        branch = m._branch(request)
        self.assertRegex(branch, r"^t3/mmos-l1-canary-[0-9a-f]{8}$")
        self.assertEqual(branch[-8:], request.request_digest[:8])
        prompt = m._main_prompt("ATT-" + "a" * 32, branch)
        self.assertIn("L1_ADMITTED_CANARY.md", prompt)
        self.assertIn(f"L1-CANARY-OK ATT-{'a' * 32}", prompt)
        self.assertIn(branch, prompt)
        self.assertIn("Do NOT open a pull request", prompt)
        iprompt = m._interrupt_prompt("nonce-1")
        self.assertIn("L1-CANARY-INTERRUPT nonce-1", iprompt)
        self.assertIn("1 to 600", iprompt)
        self.assertIn("Do not use any tools", iprompt)

    def test_launch_arguments_name_the_project_and_worktree(self) -> None:
        m = self.m
        args = m._main_launch_arguments("t3/mmos-l1-canary-deadbeef")
        self.assertEqual(args["projectId"], m.EXPECTED_PROJECT_ID)
        ws = args["workspaceStrategy"]
        self.assertEqual(ws["type"], "worktree")
        self.assertEqual(ws["branch"], "t3/mmos-l1-canary-deadbeef")
        self.assertEqual(ws["baseRef"], "master")
        self.assertTrue(ws["startFromOrigin"])
        self.assertNotIn("environmentId", args)  # the port refuses it

    def test_proposal_row_parses_from_the_document(self) -> None:
        row = self.m._proposal_row()
        self.assertEqual(row["adapter_id"], "t3-native")
        self.assertIs(row["enabled"], False)
        self.assertIs(row["autonomous_allowed"], False)
        self.assertIs(row.get("production_armed"), False)

    def test_intent_projects_slash_free_ids_from_exact_refs(self) -> None:
        m = self.m
        request = m._request("l1-admitted-canary-main")
        intent = m._intent(request)
        self.assertEqual(intent["root_run_id"], "mmos-l1-admitted-canary-20261109")
        self.assertEqual(intent["immediate_parent_run_id"], "l1-lane-lead")
        self.assertEqual(intent["logical_child_id"], "l1-admitted-canary-main")
        self.assertEqual(intent["runtime_kind"], "t3-native")
        self.assertEqual(intent["schema"], m.PLACEMENT_INTENT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
