"""Pin the Executive MCP gateway's SDK to the maintained security-fixed v1 floor.

This does not change the frozen public MCP surface. It advances the exact
hosted-CI dependency from 1.28.0 to the maintained 1.28.1 v1 release without
floating to a later SDK or beginning the separately governed MCP 2.x migration.
"""
from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PINNED_MCP_VERSION = "1.28.1"


def test_pyproject_pins_the_maintained_v1_mcp_sdk() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mcp>=1.2"' not in text
    assert f'"mcp=={PINNED_MCP_VERSION}"' in text


def test_installed_mcp_sdk_matches_the_maintained_v1_pin() -> None:
    pytest.importorskip("mcp")
    assert importlib.metadata.version("mcp") == PINNED_MCP_VERSION


def test_pinned_sdk_preserves_the_reviewed_server_surface() -> None:
    pytest.importorskip("mcp")
    from mcp.server.lowlevel import Server
    from mcp.types import ToolAnnotations

    assert callable(getattr(Server, "list_tools", None))
    assert callable(getattr(Server, "call_tool", None))
    annotations = ToolAnnotations(readOnlyHint=True)
    assert annotations.readOnlyHint is True
