"""Opaque in-process composition with the incumbent upper permission owner.

This is neither a grant nor a permission store. It imports no integration/auth
SDK and never accepts a serialized principal label or duck-typed authorizer.
The installed upper factory alone issues this nominal source after its checks.
"""
from dataclasses import dataclass,field
from types import MethodType
from typing import Callable
from common.workspace_project_admission_contract import OPERATION as PAUSE
from common.workspace_project_resumption_contract import OPERATION as RESUME
from common.workspace_project_plan_contract import validate_selection

_SEAL=object()
_FIELDS=('_policy','_load_bindings','_factory','_policy_snapshot')


class ProjectPermissionSourceUnavailable(ValueError):pass


def _context(owner):return tuple(getattr(owner,key) for key in _FIELDS)


@dataclass(frozen=True,slots=True)
class ProjectAdmissionPermissions:
    _seal:object=field(repr=False)
    _owner:object=field(repr=False)
    _context:tuple=field(repr=False)
    _callback:MethodType=field(repr=False)
    _qualified_owner:Callable[[object],bool]=field(repr=False)

    def __post_init__(self):
        self.check()

    def check(self):
        try:
            if self._seal is not _SEAL or self._qualified_owner(self._owner) is not True:
                raise ValueError()
            current=_context(self._owner)
            live=getattr(self._owner,'_authorizer')
            if (len(self._context)!=len(_FIELDS) or any(left is not right for left,right in zip(current,self._context))
                    or type(self._callback) is not MethodType or self._callback.__self__ is not self._owner
                    or type(live) is not MethodType or live.__self__ is not self._owner
                    or live.__func__ is not self._callback.__func__
                    or type(self._owner).__dict__.get('_authorizer') is not self._callback.__func__):
                raise ValueError()
        except Exception:
            raise ProjectPermissionSourceUnavailable('PROJECT_PERMISSION_SOURCE_UNAVAILABLE') from None

    def authorizer(self,*,action,work_ref):
        self.check()
        if action not in (PAUSE,RESUME):raise ProjectPermissionSourceUnavailable('PROJECT_PERMISSION_SOURCE_UNAVAILABLE')
        selected=validate_selection({'work_ref':work_ref})
        value=self._callback(action=action,work_ref=selected['work_ref'])
        self.check()
        # These are the incumbent owner-issued functions. A plain callable can
        # never create this source; stamps remain mandatory in the lower owner.
        if not callable(value) or not callable(getattr(value,'binding_digest',None)):
            raise ProjectPermissionSourceUnavailable('PROJECT_PERMISSION_SOURCE_UNAVAILABLE')
        return value


def _issue_project_admission_permissions(owner,*,qualified_owner):
    if not callable(qualified_owner) or qualified_owner(owner) is not True:
        raise ProjectPermissionSourceUnavailable('PROJECT_PERMISSION_SOURCE_UNAVAILABLE')
    callback=getattr(owner,'_authorizer',None)
    if type(callback) is not MethodType or callback.__self__ is not owner or type(owner).__dict__.get('_authorizer') is not callback.__func__:
        raise ProjectPermissionSourceUnavailable('PROJECT_PERMISSION_SOURCE_UNAVAILABLE')
    return ProjectAdmissionPermissions(_SEAL,owner,_context(owner),callback,qualified_owner)
