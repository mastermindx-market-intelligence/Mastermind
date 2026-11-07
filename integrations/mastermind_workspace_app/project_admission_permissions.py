"""Nominal adapter over unchanged sealed Workspace project-grant authorizers."""
from dataclasses import astuple,dataclass,field
from typing import Callable
from common.executive_workspace_contract import RESOURCE,SCOPE
from integrations.business_mcp_auth.contracts import ResourcePolicy
from integrations.mastermind_workspace_app import project_authoring_grant as grant_owner
from control_plane.workspace_project_permission_binding import _issue_project_admission_permissions


@dataclass(frozen=True,slots=True,repr=False)
class _WorkspaceProjectAdmissionPermissionsOwner:
    _policy:ResourcePolicy
    _load_bindings:Callable
    _factory:Callable=field(default=grant_owner.workspace_project_authorizers)
    _policy_snapshot:tuple=field(init=False)

    def __post_init__(self):
        if type(self._policy) is not ResourcePolicy or self._policy.resource!=RESOURCE or SCOPE not in self._policy.required_scopes or not callable(self._load_bindings):
            raise ValueError('current Workspace permission owner required')
        object.__setattr__(self,'_policy_snapshot',astuple(self._policy))

    def _authorizer(self,*,action,work_ref):
        return self._factory(policy=self._policy,load_bindings=self._load_bindings,action=action,work_ref=work_ref)[1]

    def _instruction_authorizer(self,*,work_ref,instruction_ref):
        return self._factory(policy=self._policy,load_bindings=self._load_bindings,
            action=grant_owner.INSTRUCTION_SUSPEND_ACTION,work_ref=work_ref,instruction_ref=instruction_ref)[1]


def project_admission_permissions(*,policy,load_bindings):
    """Existing installer composes this source; construction grants nothing."""
    owner=_WorkspaceProjectAdmissionPermissionsOwner(policy,load_bindings)
    def qualified(value):
        return (type(value) is _WorkspaceProjectAdmissionPermissionsOwner
            and type(value._policy) is ResourcePolicy and astuple(value._policy)==value._policy_snapshot
            and value._factory is grant_owner.workspace_project_authorizers)
    return _issue_project_admission_permissions(owner,qualified_owner=qualified)


def instruction_admission_permissions(*,policy,load_bindings):
    """Same sealed owner, distinct stable instruction-scoped grant function."""
    from control_plane.workspace_instruction_permission_binding import _issue_instruction_permissions
    owner=_WorkspaceProjectAdmissionPermissionsOwner(policy,load_bindings)
    def qualified(value):
        return (type(value) is _WorkspaceProjectAdmissionPermissionsOwner
            and type(value._policy) is ResourcePolicy and astuple(value._policy)==value._policy_snapshot
            and value._factory is grant_owner.workspace_project_authorizers)
    return _issue_instruction_permissions(owner,qualified_owner=qualified)
