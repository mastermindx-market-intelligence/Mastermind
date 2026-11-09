"""Compatibility import for the unchanged Executive principal namespace.

The canonical pure recipe is shared below both transport and Runtime layers.
This module authenticates and grants nothing.
"""
from common.executive_principal_namespace import NAMESPACE_SCOPE, principal_scope_from_identity

__all__ = ["NAMESPACE_SCOPE", "principal_scope_from_identity"]
