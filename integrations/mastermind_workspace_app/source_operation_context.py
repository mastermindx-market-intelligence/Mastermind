"""Current source-action context from the existing verified Workspace owner.

This is an integration-side binding, not an issuer or a login-to-Git mapping.
Only the authenticated fixed HTTP owner may supply VerifiedPrincipal. It is
independent of Macro/source acquisition so an original operation remains
inspectable when current project-source refresh is unavailable.
"""
from __future__ import annotations
import time

from common.workspace_project_journal_contract import validate_selection
from integrations.mastermind_workspace_app.source_operation_principal import (
    is_private_source_principal, source_principal_scope, source_principal_frame)
from integrations.mastermind_workspace_app.project_authoring_grant import workspace_project_authorizers

_ACTIONS = frozenset({"publish_project_proposal", "publish_project_plan_proposal", "ADOPT_PLAN", "ACCEPT_DIRECTION",
                      "add_project_file", "set_project_communication_preference"})


class WorkspaceSourceOperationContextFactory:
    """Bind the actual installed policy and sealed reload, never client claims."""
    def __init__(self, *, policy, load_bindings, now=lambda: int(time.time())):
        if not callable(load_bindings) or not callable(now):
            raise ValueError("access_denied")
        self.policy, self._load_bindings, self._now = policy, load_bindings, now

    def bind(self, principal, *, action, work_ref):
        return WorkspaceSourceOperationPermission(policy=self.policy,
            load_bindings=self._load_bindings, principal=principal, action=action, work_ref=work_ref,
            now=self._now)


class WorkspaceSourceOperationPermission:
    """Private fixed-owner context; callbacks and public labels grant nothing."""
    def __init__(self, *, policy, load_bindings, principal, action, work_ref, now=lambda: int(time.time())):
        if type(action) is not str or action not in _ACTIONS:
            raise ValueError("access_denied")
        if action != "publish_project_proposal" or work_ref is not None:
            validate_selection({"work_ref": work_ref})
        # Nominal verified-principal extraction is owned in the integration
        # layer. Caller dicts/Acquisition labels/Executive contexts are refused.
        context = {"principal_scope": source_principal_scope(principal)}
        authorize_principal, authorize_frame = workspace_project_authorizers(
            policy=policy, load_bindings=load_bindings, action=action,
            work_ref=None if action == "publish_project_proposal" else work_ref)
        gate = authorize_frame if is_private_source_principal(principal) else authorize_principal
        def authorize_current(who):
            return gate(source_principal_frame(who) if is_private_source_principal(who) else who)
        def current_stamp(who):
            return gate.binding_digest(source_principal_frame(who) if is_private_source_principal(who) else who)
        authorize_current.binding_digest = current_stamp
        authorize = authorize_current
        stamp = authorize.binding_digest(principal)
        if not authorize(principal) or stamp is None:
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        if not callable(now):
            raise ValueError("access_denied")
        self._principal, self._authorize, self._now = principal, authorize, now
        self._stamp, self._context = stamp, context
        self.action, self.work_ref = action, work_ref

    @property
    def principal_scope(self):
        if not self.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return self._context["principal_scope"]

    @property
    def permission_binding_digest(self):
        if not self.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return self._stamp

    def check(self):
        current = self._now()
        return (type(current) is int and 0 <= current < self._principal.expires_at
                and self._authorize(self._principal)
                and self._authorize.binding_digest(self._principal) == self._stamp
                and {"principal_scope": source_principal_scope(self._principal)} == self._context)

    def public_context(self):
        if not self.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        result = {"schema": "mastermind.workspace_source_operation_context.v1",
                  "selection": {"action": self.action, "work_ref": self.work_ref},
                  "owner_context": dict(self._context), "can_inspect": True}
        if not self.check():
            raise PermissionError("SOURCE_OPERATION_UNAUTHORIZED")
        return result
