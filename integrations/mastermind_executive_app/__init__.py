"""integrations.mastermind_executive_app — BSC-E1 authenticated Executive app.

A stateless A1-authenticated ASGI edge exposing the EXISTING five-tool
Executive MCP (read tools reused as-is; the single modifying tool,
``submit_ceo_intent``, admitted ONLY through the dedicated PR-A/AD-ID1
CeoIngress socket, never in-process and never over the general Executive
control socket).

This package invents no new authority, no new durable store, and no second
admission path.  See ``docs/runbooks/mastermind-executive-app.md`` for the
operational contract and ``integrations/mastermind_executive_app/app.py`` for
the ASGI wiring.
"""
from __future__ import annotations

__all__: list[str] = []
