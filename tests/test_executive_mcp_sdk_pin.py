"""Pin the Executive MCP gateway's SDK to the known-good PR #64 version.

This does not change MCP product behavior. It restores the deterministic
hosted-CI surface that `mcp>=1.2` allowed to float.
"""
from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PINNED_MCP_VERSION = "1.28.0"


def test_pyproject_pins_the_pr64_mcp_sdk() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mcp>=1.2"' not in text
    assert f'"mcp=={PINNED_MCP_VERSION}"' in text


def test_installed_mcp_sdk_matches_the_pr64_pin() -> None:
    pytest.importorskip("mcp")
    assert importlib.metadata.version("mcp") == PINNED_MCP_VERSION


def test_pinned_sdk_exposes_the_reviewed_server_surface() -> None:
    pytest.importorskip("mcp")
    from mcp.server.lowlevel import Server
    from mcp.types import ToolAnnotations

    assert callable(getattr(Server, "list_tools", None))
    annotations = ToolAnnotations(readOnlyHint=True)
    assert annotations.readOnlyHint is True
