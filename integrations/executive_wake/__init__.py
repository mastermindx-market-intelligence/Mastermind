"""Provider integration boundary for Executive Wake Fabric transports.

Provider-native wake clients live under this package.  Canonical wake identity,
ledger, retry/reconciliation and lifecycle remain in Executive OS/control_plane.
Importing this package performs no provider discovery, network I/O or state
mutation.
"""

from integrations.executive_wake.registry import WakeDispatcherRegistry

__all__ = ["WakeDispatcherRegistry"]
