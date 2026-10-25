"""Stable WP1 surface for sibling packages.

WP2 model routing (`integrations/hermes_models/`) reads
`RuntimeProfile.model_provider` and `model_default`, and may call
`register_child_secret_env` with provider env names that already live in the
0600 secrets file. This package does not call a model.

WP3 Steward, WP4 delegation (`integrations/hermes_delegate/`), and WP5
secretary skills (`integrations/hermes_secretary/`) call
`register_extension_tools` with names that are not Hermes built-ins. The
profile `tool_allowlist` must list those names or startup refuses. Hermes
toolsets in `REFUSED_HERMES_TOOLSETS` stay off; delegation and skills are not
enabled by adding the upstream toolset of the same name.

WP1 does not register the incumbent Steward reads
`list_responsibilities`, `get_responsibility`, `get_attention`,
`get_current_runtime`, `explain_blocker`, and `resolve_surface`. WP3 must
register that exact set itself. This package does not import or start the
Steward server.

Imports here do not start a process, bind a socket, or read a secrets file.
"""
from __future__ import annotations

from .constants import (
    DEFAULT_TOOL_ALLOWLIST,
    HEALTH_PATH,
    LOOPBACK_HOST,
    PINNED_UPSTREAM_SHA,
    PROFILE_SCHEMA,
    QUALIFIED_MODEL_ROUTES,
    REFUSED_HERMES_TOOLSETS,
    UPSTREAM_REPOSITORY,
)
from .errors import RuntimeRefusal
from .profile import RuntimeProfile, load_profile
from .registry import (
    assert_registered_tools_exact,
    clear_extension_tools,
    extension_tools_for,
    inspect_tool_registry,
    register_extension_tools,
)
from .secrets import clear_child_secret_env, register_child_secret_env

__all__ = [
    "DEFAULT_TOOL_ALLOWLIST",
    "HEALTH_PATH",
    "LOOPBACK_HOST",
    "PINNED_UPSTREAM_SHA",
    "PROFILE_SCHEMA",
    "QUALIFIED_MODEL_ROUTES",
    "REFUSED_HERMES_TOOLSETS",
    "UPSTREAM_REPOSITORY",
    "RuntimeProfile",
    "RuntimeRefusal",
    "assert_registered_tools_exact",
    "clear_child_secret_env",
    "clear_extension_tools",
    "extension_tools_for",
    "inspect_tool_registry",
    "load_profile",
    "register_child_secret_env",
    "register_extension_tools",
]
