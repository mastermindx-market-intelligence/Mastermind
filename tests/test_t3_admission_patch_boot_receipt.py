"""DONE_WHEN 4 invariant 11 (Director A5) — admission patch LIVE BOOT receipt pin.

Pins the committed secret-free receipt
``integrations/t3/live_proof/t3_admission_patch_boot_receipt.json`` (schema
``mastermind.t3_admission_patch_boot_receipt/v1``), produced by
``integrations/t3/live_proof/t3_admission_patch_boot.py``. That driver booted a
REAL T3 server — built from the pinned donor clone + the committed admission
patch — headlessly on an isolated port/data dir (never the desktop app on 3773,
never ``~/.t3``) and recorded the patch's live behavior:

* scenario A (``MASTERMIND_ADMISSION_ENDPOINT`` unset): pure passthrough —
  launch/read/send/interrupt reply shapes match the unpatched base boot and the
  four shared singletons (ProjectionStore, CommandOutputHub, Orchestrator,
  TextGeneration) are constructed exactly once per process;
* scenario B (endpoint = local fake admission server): admitted launches start
  and the ledger binding reaches later revalidate consults; refusals are typed,
  mint no thread, and smuggled request fields carry no authority; an
  unreachable endpoint fails closed; interrupts NEVER consult admission and are
  never blocked in any mode.

This closes the "admission patch never booted live" SOURCE_ONLY gap flagged by
all three Opus audits. The B4 hang case is honestly bounded: the patch uses a
plain ``fetch`` with no client-side timeout, so the recorded verdict there is
UNKNOWN-by-observation, not fabricated. No network is used by this test.
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
RECEIPT = LIVE / "t3_admission_patch_boot_receipt.json"
PATCH = REPO / "integrations" / "t3" / "upstream_patches" / "mastermind_admission_0770446.patch"

PIN = "0770446869d247a8b28c27d7ed93f47f8ff0c1e4"
PATCH_SHA256 = "5785ac9525a852d0c19c3668f2ae4e9cb3fcd779a62b2a084affa2004f4e922f"
#: The committed receipt is immutable live evidence: pin its own bytes.
RECEIPT_SHA256 = "a72abb5263f62235422951af9dc9b62d605e5c10367d8f525dad215811de850c"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_SINGLETONS = ("ProjectionStore", "CommandOutputHub", "Orchestrator", "TextGeneration")


def _receipt() -> dict:
    return json.loads(RECEIPT.read_text())


def _driver_module():
    spec = importlib.util.spec_from_file_location("a5_boot_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReceiptStructureTests(unittest.TestCase):
    def test_schema_pin_patch_and_outcome(self) -> None:
        receipt = _receipt()
        self.assertEqual(receipt["schema"], "mastermind.t3_admission_patch_boot_receipt/v1")
        self.assertEqual(receipt["donor_pin"], PIN)
        self.assertEqual(receipt["patch_sha256"], PATCH_SHA256)
        # the receipt's patch digest IS the committed patch bytes
        self.assertEqual(hashlib.sha256(PATCH.read_bytes()).hexdigest(), PATCH_SHA256)
        self.assertIn(receipt["outcome"], {"DONE", "DONE_WITH_FINDINGS"})
        self.assertIsNone(receipt["blocked"])

    def test_receipt_bytes_are_pinned(self) -> None:
        self.assertEqual(hashlib.sha256(RECEIPT.read_bytes()).hexdigest(), RECEIPT_SHA256)

    def test_knobs_never_touch_the_real_desktop(self) -> None:
        knobs = _receipt()["knobs"]
        self.assertIn("--no-browser", knobs["boot_command"])
        self.assertEqual(knobs["admission_endpoint_env"], "MASTERMIND_ADMISSION_ENDPOINT")
        ports = knobs["ports_used"]
        self.assertGreaterEqual(len(ports), 6)
        for port in ports:
            self.assertNotEqual(port, 3773)
            self.assertGreater(port, 1024)
        self.assertEqual(knobs["real_desktop_port"], 3773)
        self.assertFalse(knobs["real_desktop_touched"])
        # the paid-model-free provider knob is named
        self.assertIn("devReplay", knobs["dev_instance_seed_env"])

    def test_instrumentation_is_the_driver_module_and_covers_both_trees(self) -> None:
        instr = _receipt()["instrumentation"]
        driver = _driver_module()
        self.assertEqual(
            instr["module_sha256"],
            hashlib.sha256(driver.A5_COUNTS_MODULE.encode()).hexdigest(),
        )
        self.assertTrue(instr["same_module_in_both_trees"])
        # every composition path goes through the counters: both files that
        # reference the singleton layers directly are rewritten.
        self.assertEqual(
            instr["runtimeLayer_edits"],
            {"ProjectionStore.layer": 16, "CommandOutputHub.layer": 1,
             "Orchestrator.layer": 1, "TextGeneration.layer": 1},
        )
        self.assertEqual(
            instr["server_ts_edits"],
            {"ProjectionStoreV2.layer": 9, "TextGeneration.layer": 1},
        )
        self.assertIn("no nested Layer.build", instr["note"])

    def test_typecheck_gate_passed_in_both_trees(self) -> None:
        trees = _receipt()["instrumentation"]["typecheck"]["trees"]
        self.assertEqual(set(trees), {"patched", "base"})
        for name, note in trees.items():
            self.assertEqual(note["error_level_diagnostics"], 0, name)
            # donor-baseline suggestions are recorded, not gated
            self.assertGreater(note["suggestion_level_diagnostics"], 400, name)


class ScenarioVerdictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = _receipt()
        self.s = self.receipt["scenarios"]

    def test_all_six_scenarios_recorded(self) -> None:
        expected = {
            "A1_patched_endpoint_unset", "A0_base_unpatched",
            "B1_endpoint_admit", "B2_endpoint_refuse",
            "B3_endpoint_unreachable", "B4_endpoint_hang",
        }
        self.assertEqual(set(self.s), expected)

    def test_a1_patched_endpoint_unset_is_clean_passthrough(self) -> None:
        a1 = self.s["A1_patched_endpoint_unset"]
        self.assertEqual(a1["verdict"], "PASS")
        self.assertFalse(a1["launch"]["isError"])
        self.assertTrue(a1["launch_shape"]["threadId_present"])
        self.assertFalse(a1["interrupt_is_admission_block"])
        self.assertIn(a1["run_statuses_observed"][0],
                      {"completed", "failed", "interrupted"})
        # identical to the unpatched base boot
        self.assertTrue(a1["matches_unpatched_shapes"])
        self.assertTrue(a1["matches_unpatched_counts"])

    def test_a0_base_boot_matches(self) -> None:
        a0 = self.s["A0_base_unpatched"]
        self.assertEqual(a0["verdict"], "PASS")
        self.assertFalse(a0["launch"]["isError"])

    def test_every_boot_constructs_each_singleton_exactly_once(self) -> None:
        for name, scenario in self.s.items():
            counts = scenario["singleton_counts"]
            self.assertEqual(set(counts), set(_SINGLETONS), name)
            for singleton in _SINGLETONS:
                self.assertEqual(counts[singleton], 1, f"{name}/{singleton}")

    def test_b1_admit_launches_and_revalidates_with_binding(self) -> None:
        b1 = self.s["B1_endpoint_admit"]
        self.assertEqual(b1["verdict"], "PASS")
        self.assertFalse(b1["launch"]["isError"])
        self.assertTrue(b1["launch_shape"]["threadId_present"])
        self.assertTrue(b1["revalidate_carries_binding"])
        self.assertEqual(b1["interrupt_consults_delta"], 0)
        self.assertFalse(b1["interrupt_is_admission_block"])
        # consult: wire-protocol body, donor-derived creationSource, and the
        # endpoint's actual admit decision (authority chain endpoint->ledger)
        self.assertEqual(b1["launch_consult"]["body"]["kind"], "launch")
        self.assertEqual(b1["launch_consult"]["body"]["creationSource"], "mcp")
        self.assertEqual(b1["launch_consult"]["reply"]["decision"], "admitted")
        self.assertEqual(b1["launch_consult"]["reply"]["rootRef"], "a5-fake-root-1")
        # revalidate consults carry the endpoint-issued rootRef, not client/env claims
        self.assertTrue(any(
            c.get("hasLocalBinding") is True
            and c.get("binding", {}).get("rootRef") == "a5-fake-root-1"
            for c in b1["revalidate_consult_bodies"]
        ))

    def test_b2_refusal_chain_mints_no_thread_and_smuggle_has_no_authority(self) -> None:
        b2 = self.s["B2_endpoint_refuse"]
        self.assertEqual(b2["verdict"], "PASS")
        self.assertTrue(b2["launch_is_error"])
        # observed chain: endpoint consulted -> replied blocked_with_reason
        # -> launch refused -> no thread anywhere in the store
        self.assertTrue(b2["refusal_consult_reply_was_blocked"])
        self.assertTrue(b2["refusal_threadId_absent"])
        self.assertFalse(b2["launch_shape"]["threadId_present"])
        self.assertEqual(b2["threads_total_after_refusal"], 0)
        self.assertGreaterEqual(b2["launch_consult_count"], 1)
        # LIVE FINDING pinned: the MCP reply is the donor-generic failure, the
        # typed admission cause is NOT surfaced over MCP
        self.assertTrue(b2["refusal_reply_is_generic_orchestration_error"])
        # smuggle: client-claimed authority fields never reached the gate
        self.assertTrue(b2["smuggle_is_error"])
        self.assertTrue(b2["smuggle_no_authority"])
        self.assertTrue(b2["smuggle_threadId_absent"])
        self.assertFalse(b2["smuggle_consult_saw_client_fields"])
        self.assertTrue(b2["smuggle_consult_reply_was_blocked"])
        self.assertEqual(b2["smuggle_consult"]["body"]["creationSource"], "mcp")
        # interrupts never consult admission, never blocked
        self.assertEqual(b2["interrupt_consults_delta"], 0)
        self.assertFalse(b2["interrupt_is_admission_block"])

    def test_b3_unreachable_fails_closed(self) -> None:
        b3 = self.s["B3_endpoint_unreachable"]
        self.assertEqual(b3["verdict"], "PASS")
        self.assertTrue(b3["fail_closed"])
        self.assertTrue(b3["threadId_absent"])
        self.assertEqual(b3["threads_total_after_failure"], 0)
        self.assertTrue(b3["failure_reply_is_generic_orchestration_error"])
        self.assertFalse(b3["interrupt_is_admission_block"])

    def test_b4_hang_is_honestly_bounded_and_interrupts_still_free(self) -> None:
        b4 = self.s["B4_endpoint_hang"]
        self.assertIn(b4["verdict"], {"UNKNOWN", "REFUSED_WITHIN_WINDOW"})
        self.assertTrue(b4["hang_consult_observed_while_pending"])
        self.assertTrue(b4["interrupt_never_blocked"])
        self.assertEqual(b4["interrupt_consults_delta"], 0)
        self.assertFalse(b4["interrupt_is_admission_block"])
        self.assertGreater(b4["hang_window_s"], 0)

    def test_findings_summary_shape(self) -> None:
        findings = self.receipt["findings_summary"]
        self.assertEqual(findings["hard_fail_scenarios"], [])
        self.assertIn("hang_case", findings)
        # the honest donor-behavior finding is recorded, not patched around
        self.assertIn("LIVE FINDING", findings["typed_admission_cause_not_surfaced_over_mcp"])
        self.assertIn("unavailable()", findings["typed_admission_cause_not_surfaced_over_mcp"])


class ReceiptIsSecretFreeTests(unittest.TestCase):
    def test_no_credentials_tokens_or_home_paths(self) -> None:
        raw = RECEIPT.read_text()
        # (the knobs block DESCRIBES the pairing-code flow in prose; the needles
        # below guard against actual credential material leaking)
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
