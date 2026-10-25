"""Pure source-compatibility tests; never connect to a live Steward/Executive."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from integrations.mastermind_secretary_mcp.server import build_tools
from integrations.hermes_qualification import steward_contract as subject


class StewardCandidateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = build_tools()

    def test_exact_original_read_only_owner_is_qualified_only_as_source(self) -> None:
        result = subject.inspect_advertisement(self.rows)
        self.assertEqual(result["status"], "PASS_SOURCE_CONTRACT_ONLY", result)
        self.assertEqual(len(result["tool_names"]), 6)
        for marker in ("mcp_server_connected", "identity_or_authority_granted",
                       "steward_live_data_read", "provider_or_model_called",
                       "runtime_tools_admitted"):
            self.assertFalse(result[marker])

    def test_write_tool_injection_is_refused_without_echo(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad.append({"name": "dangerously_publish_A_SECRET_SENTINEL",
                    "annotations": {"readOnlyHint": False}})
        result = subject.inspect_advertisement(bad)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("ADVERTISED_TOOL_SET_INVALID", result["issues"])
        self.assertNotIn("A_SECRET_SENTINEL", json.dumps(result))

    def test_missing_tool_is_refused(self) -> None:
        self.assertIn("ADVERTISED_TOOL_SET_INVALID",
                      subject.inspect_advertisement(self.rows[:-1])["issues"])

    def test_out_of_order_tools_are_not_silently_rebound(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad[0], bad[1] = bad[1], bad[0]
        self.assertEqual(subject.inspect_advertisement(bad)["status"], "REFUSED")

    def test_renamed_tool_is_refused(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad[2]["name"] = "call_any_api"
        self.assertEqual(subject.inspect_advertisement(bad)["status"], "REFUSED")

    def test_false_read_only_advertisement_refused(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad[0]["annotations"]["readOnlyHint"] = False
        self.assertIn("ADVERTISED_SOURCE_DRIFT",
                      subject.inspect_advertisement(bad)["issues"])

    def test_changed_input_schema_refused(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad[0]["inputSchema"]["additionalProperties"] = True
        self.assertEqual(subject.inspect_advertisement(bad)["status"], "REFUSED")

    def test_malformed_rows_are_not_echoed_or_executed(self) -> None:
        for value in (None, "a string", {}, [123] * 6, [object()] * 6):
            with self.subTest(value_type=type(value).__name__):
                result = subject.inspect_advertisement(value)
                self.assertEqual(result["status"], "REFUSED")
                self.assertFalse(result["mcp_server_connected"])

    def test_oversized_advertisement_is_refused(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad[0]["description"] = "x" * (subject.MAX_ADVERTISEMENT_BYTES + 3)
        self.assertIn("ADVERTISED_SIZE_EXCEEDED",
                      subject.inspect_advertisement(bad)["issues"])

    def test_changed_owner_version_is_not_silently_accepted(self) -> None:
        with patch.object(subject, "SERVER_GENERATION", 3):
            self.assertIn("OWNER_GENERATION_UNQUALIFIED",
                          subject.inspect_advertisement(self.rows)["issues"])

    def test_owner_expanded_tool_set_requires_new_review(self) -> None:
        expanded = copy.deepcopy(self.rows)
        expanded.append({"name": "new_owner_tool"})
        with patch.object(subject, "build_tools", return_value=expanded):
            result = subject.inspect_advertisement(self.rows)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("OWNER_TOOL_SET_CHANGED", result["issues"])

    def test_owner_dynamic_resource_capability_is_refused(self) -> None:
        widened = dict(subject.STATIC_CAPABILITIES)
        widened["resources"] = True
        with patch.object(subject, "STATIC_CAPABILITIES", widened):
            result = subject.inspect_advertisement(self.rows)
        self.assertIn("OWNER_CAPABILITIES_CHANGED", result["issues"])

    def test_output_contract_change_refused(self) -> None:
        bad = copy.deepcopy(self.rows)
        bad[0]["outputSchema"] = {"type": "object", "additionalProperties": True}
        self.assertIn("ADVERTISED_SOURCE_DRIFT",
                      subject.inspect_advertisement(bad)["issues"])


if __name__ == "__main__":
    unittest.main()
