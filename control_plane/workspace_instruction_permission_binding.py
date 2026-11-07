"""Private nominal instruction-grant source; no SDK, grant copy or authority."""
from dataclasses import dataclass,field
from types import MethodType
from control_plane.workspace_project_permission_binding import _context,_FIELDS,ProjectPermissionSourceUnavailable
from common.workspace_instruction_admission_contract import selection

_SEAL=object()


@dataclass(frozen=True,slots=True)
class InstructionAdmissionPermissions:
    _seal:object=field(repr=False)
    _owner:object=field(repr=False)
    _context:tuple=field(repr=False)
    _callback:MethodType=field(repr=False)
    _qualified_owner:object=field(repr=False)

    def __post_init__(self):self.check()

    def check(self):
        try:
            if self._seal is not _SEAL or self._qualified_owner(self._owner) is not True:raise ValueError()
            live=getattr(self._owner,'_instruction_authorizer');current=_context(self._owner)
            if (len(self._context)!=len(_FIELDS) or any(a is not b for a,b in zip(current,self._context))
                    or type(self._callback) is not MethodType or self._callback.__self__ is not self._owner
                    or type(live) is not MethodType or live.__self__ is not self._owner
                    or live.__func__ is not self._callback.__func__
                    or type(self._owner).__dict__.get('_instruction_authorizer') is not self._callback.__func__):raise ValueError()
        except Exception:raise ProjectPermissionSourceUnavailable('INSTRUCTION_PERMISSION_SOURCE_UNAVAILABLE') from None

    def authorizer(self,*,work_ref,instruction_ref):
        self.check();selected=selection({'work_ref':work_ref,'instruction_ref':instruction_ref})
        result=self._callback(**selected);self.check()
        if not callable(result) or not callable(getattr(result,'binding_digest',None)):raise ProjectPermissionSourceUnavailable('INSTRUCTION_PERMISSION_SOURCE_UNAVAILABLE')
        return result


def _issue_instruction_permissions(owner,*,qualified_owner):
    if not callable(qualified_owner) or qualified_owner(owner) is not True:raise ProjectPermissionSourceUnavailable('INSTRUCTION_PERMISSION_SOURCE_UNAVAILABLE')
    callback=getattr(owner,'_instruction_authorizer',None)
    return InstructionAdmissionPermissions(_SEAL,owner,_context(owner),callback,qualified_owner)
