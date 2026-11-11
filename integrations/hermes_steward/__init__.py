"""Hermes consumer for the existing read-only Steward MCP surface.

This package does not start Hermes, open a socket, store a credential, or
expose a write tool. Company reads stay on the injected Steward transport.
"""

from integrations.hermes_steward.client import (
    ALLOWED_TOOLS,
    REQUIRED_SCOPE,
    StewardReadClient,
)

__all__ = ["ALLOWED_TOOLS", "REQUIRED_SCOPE", "StewardReadClient"]
