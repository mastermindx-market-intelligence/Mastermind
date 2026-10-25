"""Pinned, loopback-only Hermes runtime for the Secretary and Meta-CEO harness.

This is a process supervisor and installer. It is not an Executive, Agent OS,
capacity, or Steward authority.
"""
from .contract import (
    DEFAULT_TOOL_ALLOWLIST,
    HEALTH_PATH,
    PINNED_UPSTREAM_SHA,
    PROFILE_SCHEMA,
    REFUSED_HERMES_TOOLSETS,
    RuntimeProfile,
    RuntimeRefusal,
    assert_registered_tools_exact,
    load_profile,
    register_child_secret_env,
    register_extension_tools,
)

__all__ = [
    "DEFAULT_TOOL_ALLOWLIST",
    "HEALTH_PATH",
    "PINNED_UPSTREAM_SHA",
    "PROFILE_SCHEMA",
    "REFUSED_HERMES_TOOLSETS",
    "RuntimeProfile",
    "RuntimeRefusal",
    "assert_registered_tools_exact",
    "load_profile",
    "register_child_secret_env",
    "register_extension_tools",
]
