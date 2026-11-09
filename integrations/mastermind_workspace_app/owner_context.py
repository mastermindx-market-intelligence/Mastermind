"""Stable Workspace operation scope from the incumbent verified principal.

This observation is neither an action grant nor an Executive account mapping.
Expose it only from an owner-qualified response after its own authorization.
"""
from __future__ import annotations

import hashlib

from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.contract import principal_frame


def workspace_principal_scope(principal):
    """Hash the exact six-field VerifiedPrincipal frame used by Workspace.

    Deliberately excludes permission bindings and token/host generations: those
    change independently, while unresolved operations retain this scope.
    principal_frame rejects caller dictionaries and unrelated auth contexts.
    """
    return hashlib.sha256(canonical(principal_frame(principal))).hexdigest()


def workspace_owner_context(principal):
    """Return the closed context for a previously owner-qualified response."""
    return {"principal_scope": workspace_principal_scope(principal)}
