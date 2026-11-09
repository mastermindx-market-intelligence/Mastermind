"""A6 bounded consult — r2 LIVE BOOT receipt pin.

Pins the committed secret-free receipt
``integrations/t3/live_proof/t3_admission_patch_boot_receipt_r2.json`` (schema
``mastermind.t3_admission_patch_boot_receipt/v1``), produced by re-running the
A5 driver (``integrations/t3/live_proof/t3_admission_patch_boot.py``) against
the A6 bounded-consult patch bytes for scenarios A0/A1/B2/B3/B4. The A5 r1
receipt is immutable and still pins the A5-era bytes; THIS receipt proves the
current committed patch closes A5 live finding #1:

* B4 (endpoint accepts but never answers) is no longer UNKNOWN: booted with
  ``MASTERMIND_ADMISSION_TIMEOUT_MS=3000``, the launch consult ABORTED at the
  bound and the launch FAILED CLOSED — ``isError``, no threadId,
  ``t3_thread_list`` total 0 — while the interrupt probe DURING the pending
  consult answered immediately with 0 admission consults;
* the regression scenarios keep their A5 verdicts: passthrough (A1) identical
  to the unpatched base boot (A0) in reply shapes AND singleton counts; the
  refusal fence (B2) and unreachable fail-closed (B3) unchanged;
* every boot still constructs each shared singleton exactly once.

A5 finding #2 (typed admission cause not surfaced over MCP — donor whitelist
in ``mcp/toolkits/project/handlers.ts``) remains open as an upstream-PR note:
the r2 B4 refusal is still the donor-generic ``orchestration_error``. No
network is used by this test.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "integrations" / "t3" / "live_proof"
DRIVER = LIVE / "t3_admission_patch_boot.py"
RECEIPT = LIVE / "t3_admission_patch_boot_receipt_r2.json"
PATCH = REPO / "integrations" / "t3" / "upstream_patches" / "mastermind_admission_0770446.patch"

PIN = "0770446869d247a8b28c27d7ed93f47f8ff0c1e4"
#: The A6 bounded-consult patch bytes (A5-era bytes were 5785ac95…).
PATCH_SHA256 = "999a1b1e9472e47955714235f9478ac7145569d1870436f3df06b5796e771a1f"
#: The committed r2 receipt is immutable live evidence: pin its own bytes.
RECEIPT_SHA256 = "8b844c1f1106437fa3417e58221a0b5d5705abd7436f22b1d9e7017f080a407c"

_SINGLETONS = ("ProjectionStore", "CommandOutputHub", "Orchestrator", "TextGeneration")
_R2_SCENARIOS = {
    "A1_patched_endpoint_unset",
    "A0_base_unpatched",
    "B2_endpoint_refuse",
    "B3_endpoint_unreachable",
    "B4_endpoint_hang",
}


def _receipt() -> dict:
    return json.loads(RECEIPT.read_text())


def _driver_module():
    spec = importlib.util.spec_from_file_location("a6_boot_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReceiptStructureTests(unittest.TestCase):
    def test_schema_pin_patch_and_outcome(self) -> None:
        receipt = _receipt()
        self.assertEqual(receipt["schema"], "mastermind.t3_admission_patch_boot_receipt/v1")
        self.assertEqual(receipt["donor_pin"], PIN)
        # the receipt's patch digest IS the CURRENT committed patch bytes
        self.assertEqual(receipt["patch_sha256"], PATCH_SHA256)
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), PATCH_SHA256)
        # B4 resolved: no hang finding remains, no scenario failed
        self.assertEqual(receipt["outcome"], "DONE")
        self.assertIsNone(receipt["blocked"])
        self.assertEqual(receipt["findings_summary"]["hard_fail_scenarios"], [])

    def test_receipt_bytes_are_pinned(self) -> None:
        self.assertEqual(hashlib.sha256(RECEIPT.read_bytes()).hexdigest(), RECEIPT_SHA256)

    def test_knobs_never_touch_the_real_desktop(self) -> None:
        knobs = _receipt()["knobs"]
        self.assertIn("--no-browser", knobs["boot_command"])
        for port in knobs["ports_used"]:
            self.assertNotEqual(port, 3773)
            self.assertGreater(port, 1024)
        self.assertEqual(knobs["real_desktop_port"], 3773)
        self.assertFalse(knobs["real_desktop_touched"])
        self.assertIn("devReplay", knobs["dev_instance_seed_env"])

    def test_timeout_knob_recorded_and_used(self) -> None:
        knobs = _receipt()["knobs"]
        self.assertIn("MASTERMIND_ADMISSION_TIMEOUT_MS", knobs["admission_timeout_env"])
        # the env override was actually exercised live (3 s bound << 10 s default)
        self.assertEqual(knobs["admission_timeout_ms_set"], 3000)

    def test_instrumentation_is_the_driver_module_and_covers_both_trees(self) -> None:
        instr = _receipt()["instrumentation"]
        driver = _driver_module()
        self.assertEqual(
            instr["module_sha256"],
            hashlib.sha256(driver.A5_COUNTS_MODULE.encode()).hexdigest(),
        )
        self.assertTrue(instr["same_module_in_both_trees"])
        self.assertEqual(
            instr["runtimeLayer_edits"],
            {"ProjectionStore.layer": 16, "CommandOutputHub.layer": 1,
             "Orchestrator.layer": 1, "TextGeneration.layer": 1},
        )
        self.assertEqual(
            instr["server_ts_edits"],
            {"ProjectionStoreV2.layer": 9, "TextGeneration.layer": 1},
        )

    def test_typecheck_gate_passed_in_both_trees(self) -> None:
        trees = _receipt()["instrumentation"]["typecheck"]["trees"]
        self.assertEqual(set(trees), {"patched", "base"})
        for name, note in trees.items():
            # the GATE is zero error-level diagnostics; the driver-captured
            # suggestion counts are informational only (this run's capture
            # undercounted the donor TS377141 baseline — canonical same-tree
            # re-runs recorded in LANE_T3_DIRECTOR_A.md § A6: 489 base / 492
            # patched, i.e. the patch adds exactly 3 TaggedError brands)
            self.assertEqual(note["error_level_diagnostics"], 0, name)
            self.assertEqual(note["exit"], 0, name)
            self.assertGreater(note["suggestion_level_diagnostics"], 0, name)


class ScenarioVerdictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = _receipt()
        self.s = self.receipt["scenarios"]

    def test_exactly_the_five_r2_scenarios_all_pass(self) -> None:
        self.assertEqual(set(self.s), _R2_SCENARIOS)
        for name in _R2_SCENARIOS:
            self.assertEqual(self.s[name]["verdict"], "PASS", name)

    def test_every_boot_constructs_each_singleton_exactly_once(self) -> None:
        for name, scenario in self.s.items():
            counts = scenario["singleton_counts"]
            self.assertEqual(set(counts), set(_SINGLETONS), name)
            for singleton in _SINGLETONS:
                self.assertEqual(counts[singleton], 1, f"{name}/{singleton}")

    def test_passthrough_still_matches_the_unpatched_base_boot(self) -> None:
        a1 = self.s["A1_patched_endpoint_unset"]
        a0 = self.s["A0_base_unpatched"]
        self.assertFalse(a1["launch"]["isError"])
        self.assertTrue(a1["launch_shape"]["threadId_present"])
        self.assertTrue(a1["matches_unpatched_shapes"])
        self.assertTrue(a1["matches_unpatched_counts"])
        self.assertFalse(a0["launch"]["isError"])
        self.assertIn(a1["run_statuses_observed"][0],
                      {"completed", "failed", "interrupted"})

    def test_b2_refusal_fence_unchanged(self) -> None:
        b2 = self.s["B2_endpoint_refuse"]
        self.assertTrue(b2["launch_is_error"])
        self.assertTrue(b2["refusal_consult_reply_was_blocked"])
        self.assertEqual(b2["threads_total_after_refusal"], 0)
        self.assertTrue(b2["smuggle_no_authority"])
        self.assertEqual(b2["interrupt_consults_delta"], 0)

    def test_b3_unreachable_still_fails_closed(self) -> None:
        b3 = self.s["B3_endpoint_unreachable"]
        self.assertTrue(b3["fail_closed"])
        self.assertEqual(b3["threads_total_after_failure"], 0)
        self.assertFalse(b3["interrupt_is_admission_block"])

    def test_b4_hang_now_fails_closed_at_the_bound(self) -> None:
        """The A6 core claim: a hung endpoint can no longer hang the funnel."""
        b4 = self.s["B4_endpoint_hang"]
        self.assertEqual(b4["launch_outcome_at_window"], "REFUSED_WITHIN_WINDOW")
        self.assertEqual(b4["consult_bound_ms"], 3000)
        self.assertTrue(b4["launch"]["isError"])
        # fail-closed chain: no threadId in the refusal, none in the store
        self.assertTrue(b4["refusal_threadId_absent"])
        self.assertEqual(b4["threads_total_after_timeout"], 0)
        # the bound actually fired: refusal landed well inside the observation
        # window and close to the configured 3 s bound (not the 10 s default)
        self.assertLess(b4["launch_elapsed_s"], b4["hang_window_s"])
        self.assertLess(b4["launch_elapsed_s"], 10.0)
        # interrupt DURING the pending consult: immediate, ungated, 0 consults
        self.assertTrue(b4["hang_consult_observed_while_pending"])
        self.assertTrue(b4["interrupt_never_blocked"])
        self.assertEqual(b4["interrupt_consults_delta"], 0)
        self.assertFalse(b4["interrupt_is_admission_block"])

    def test_findings_summary_reflects_the_resolved_hang_and_open_upstream_note(self) -> None:
        findings = self.receipt["findings_summary"]
        self.assertIn("bounded consult (A6)", findings["hang_case"])
        # A5 finding #2 remains open as an upstream-PR note (donor whitelist)
        self.assertIn("LIVE FINDING", findings["typed_admission_cause_not_surfaced_over_mcp"])
        self.assertIn("unavailable()", findings["typed_admission_cause_not_surfaced_over_mcp"])


class ReceiptIsSecretFreeTests(unittest.TestCase):
    def test_no_credentials_tokens_or_home_paths(self) -> None:
        raw = RECEIPT.read_text()
        for needle in ("Bearer", "access_token", "authorization", "Authorization",
                       "/Users/", "Token: ", "eyJ"):
            self.assertNotIn(needle, raw)

    def test_server_versions_are_recorded(self) -> None:
        for name, scenario in _receipt()["scenarios"].items():
            info = scenario.get("initialize_serverInfo")
            self.assertTrue(info, name)
            self.assertTrue(info.get("version"), name)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
