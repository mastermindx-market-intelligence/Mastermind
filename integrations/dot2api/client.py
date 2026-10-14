"""Compatibility import for the shared Dot2API transport contract.

The implementation lives in :mod:`common.dot2api_client` so Executive control
code never depends on an integration package. This module owns no state.
"""
from common.dot2api_client import (
    Dot2ApiClient,
    Dot2ApiClientError,
    Dot2ApiEffectUnknown,
    Dot2ApiProtocolError,
    Dot2ApiTask,
)

__all__ = [
    "Dot2ApiClient",
    "Dot2ApiClientError",
    "Dot2ApiEffectUnknown",
    "Dot2ApiProtocolError",
    "Dot2ApiTask",
]
