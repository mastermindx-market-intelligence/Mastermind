"""Cursor MCP metadata is not a Fabric admission or worker receipt."""
from __future__ import annotations

import pytest

from integrations.cursor_agent_mastermind.qualification import classify, REQUIRED


def test_live_readonly_style_catalog_never_implies_dispatch() -> None:
    text = """Tools for mastermindStudio (5):
- paper_catalog ()
- paper_inspect ()
- paper_read (tool, arguments)
- studio_fleet_status ()
- studio_ping ()
"""
    row = classify(text, 0, "mastermindStudio")
    assert row["state"] == "READ_ONLY_OR_UNRELATED_MCP"
    assert row["fabric_dispatch_authorized"] is False
    assert row["worker_started"] is False
    assert row["fabric_tool_names"] == []


def test_exact_full_fabric_catalog_still_not_proven_admitted() -> None:
    text = "Tools for mastermindFabric (7):\n" + "".join("- " + t + " ()\n" for t in REQUIRED)
    row = classify(text, 0, "mastermindFabric")
    assert row["state"] == "FABRIC_CATALOG_EXPOSED_NOT_ADMITTED"
    assert row["provider_admission_proven"] is False
    assert not row["worker_started"]


def test_partial_mutating_catalog_is_fail_closed() -> None:
    row = classify("- fabric_request (run_id, root_id)\n", 0, "mastermindStudio")
    assert row["state"] == "PARTIAL_FABRIC_CATALOG_REFUSED"
    assert row["fabric_dispatch_authorized"] is False


def test_failure_and_no_tools_are_not_ready() -> None:
    assert classify("", 1, "mastermindStudio")["state"] == "MCP_CATALOG_UNAVAILABLE"
    assert classify("No tools", 0, "mastermindStudio")["state"] == "NO_OBSERVED_TOOLS"


def test_no_arbitrary_server_probe() -> None:
    with pytest.raises(ValueError, match="unknown MCP binding"):
        classify("", 0, "other")
