"""Inert Hermes delegation bridge (masterplan P3 / WP4).

Importing this package does not admit a child, start Fabric, or call Cursor.
"""
from integrations.hermes_delegate.bridge import Bridge
from integrations.hermes_delegate.policy import TOOL_NAME, load_policy
from integrations.hermes_delegate.tool import TOOL_REGISTRATION, dispatch, registered_tools

__all__ = [
    "Bridge",
    "TOOL_NAME",
    "TOOL_REGISTRATION",
    "dispatch",
    "load_policy",
    "registered_tools",
]
