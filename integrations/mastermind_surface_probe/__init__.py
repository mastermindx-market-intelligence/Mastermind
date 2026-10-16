"""Read-only Business Sol surface-context falsifier.

The package is production-inert until an explicit MCP adapter is configured and
started.  Importing it performs no network, persistence, authentication,
binding, or lifecycle action.
"""
from .probe import (
    HostContextProbeConfig,
    HostContextProbeError,
    inspect_surface_context,
)
from .schemas import (
    CONTRACT_DIGEST,
    RESULT_SCHEMA,
    SERVER_IDENTITY,
    SERVER_VERSION,
)

__all__ = [
    "CONTRACT_DIGEST",
    "HostContextProbeConfig",
    "HostContextProbeError",
    "RESULT_SCHEMA",
    "SERVER_IDENTITY",
    "SERVER_VERSION",
    "inspect_surface_context",
]
