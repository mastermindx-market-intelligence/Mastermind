"""Bounded ChatGPT MCP gateway over the existing Mastermind Executive OS.

Import layout is load-bearing (commission R5):

* :mod:`integrations.executive_mcp.schemas` — stdlib + first-party only.
* :mod:`integrations.executive_mcp.adapter` — stdlib + first-party only.
* :mod:`integrations.executive_mcp.server`  — the ONLY MCP SDK importer.

``__init__`` deliberately re-exports nothing from ``server``: importing this
package must never require the MCP SDK, because ``control_plane`` runs under a
sealed Python runtime that does not have it installed.
"""
from __future__ import annotations

__all__ = ["adapter", "schemas"]
