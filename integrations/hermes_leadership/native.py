"""Read-only leadership tool through the incumbent Hermes registration owner.

No plugin installation, profile editing, credential discovery or service start.
The installed host must compose the actual current authenticated reader. The
model can request the fixed brief, not choose a role, mission, model or account.
"""
from __future__ import annotations
import inspect
import json
from dataclasses import dataclass
from typing import Any,Callable
from integrations.hermes_harness.native_tool_registration import (
    NativeToolRegistrationError as _NativeRegistrationError, _ctx_profile_name, _ctx_scope,
    _loading_mode_refusal, _registry,
)
from .reader import LeadershipReader,outcome

TOOL_NAME='mmx_leadership_brief'
TOOLSET='mmx_leadership'
TOOL_SCHEMA={
    'name':TOOL_NAME,
    'description':'Read the host-bound role charter and original mission facts. Read only; no assignment, admission or acceptance.',
    'parameters':{'type':'object','additionalProperties':False,'properties':{}},
}


class NativeToolRegistrationError(_NativeRegistrationError):
    """Retain the exact leadership slot on an ambiguous native-owner effect."""
    def __init__(self, code: str, **origin):
        super().__init__(code, **origin)
        if self.original_context is not None:
            self.original_tool_name = TOOL_NAME


def _current(check: Callable[[],bool]) -> bool:
    try:
        result=check()
        if inspect.iscoroutine(result):
            result.close()
            return False
        return result is True
    except Exception:
        return False


@dataclass(frozen=True)
class HostLeadershipBinding:
    """Resolver owned by the existing native host, never a new session table.

    The host retains each reader in its original session context. Resolving the
    same still-current session must return that same object. Replacement or
    revocation during a read discards the original result.
    """
    profile_id: str
    resolve_reader: Callable[[str], LeadershipReader | None]
    currentness_guard: Callable[[], bool]

    def __post_init__(self):
        if (type(self.profile_id) is not str or not self.profile_id
                or not callable(self.resolve_reader) or not callable(self.currentness_guard)
                or inspect.iscoroutinefunction(self.resolve_reader)
                or inspect.iscoroutinefunction(self.currentness_guard)):
            raise NativeToolRegistrationError('NATIVE_HOST_BINDING_INVALID')

    def is_current(self) -> bool:
        return _current(self.currentness_guard)

    def resolve(self, session_id: Any) -> LeadershipReader | None:
        if type(session_id) is not str or not session_id or len(session_id)>128:
            return None
        try:
            reader=self.resolve_reader(session_id)
            if inspect.iscoroutine(reader):
                reader.close()
                return None
            if isinstance(reader,LeadershipReader) and reader.session_id==session_id:
                return reader
        except Exception:
            pass
        return None


def native_handler(binding: LeadershipReader | HostLeadershipBinding, *, native_current: Callable[[],bool] | None=None):
    if not isinstance(binding,(LeadershipReader,HostLeadershipBinding)):
        raise NativeToolRegistrationError('NATIVE_BINDING_INVALID')
    check=native_current if native_current is not None else binding.is_current
    async def handle(arguments: Any, *, session_id: Any=None, task_id: Any=None) -> str:
        if type(arguments) is not dict or arguments:
            result=outcome('REFUSED','closed_empty_arguments_required')
        elif task_id is not None and (type(task_id) is not str or task_id != session_id):
            result=outcome('REFUSED','native_task_mismatch')
        elif not _current(check):
            result=outcome('REFUSED','native_registration_not_current')
        else:
            reader=binding.resolve(session_id) if isinstance(binding,HostLeadershipBinding) else binding
            if reader is None:
                result=outcome('REFUSED','native_session_not_enrolled')
            else:
                result=await reader.read(session_id=session_id)
                if (not _current(check) or isinstance(binding,HostLeadershipBinding)
                        and binding.resolve(session_id) is not reader):
                    result=outcome('REFUSED','native_registration_not_current')
        return json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    return handle


@dataclass(frozen=True)
class NativeLeadershipRegistration:
    handler: Callable
    check_fn: Callable
    handle: Any
    entry: Any
    scope: str
    _live: dict

    def dispose(self) -> None:
        # Prevent retained handlers from serving after unload, even if disposal fails.
        self._live['active']=False
        self.handle.dispose()


def register_native_tool(ctx: Any, reader: LeadershipReader | HostLeadershipBinding, *, profile_id: str) -> NativeLeadershipRegistration:
    """Register once; exact owner lease/readback, no collision override."""
    if not isinstance(reader,(LeadershipReader,HostLeadershipBinding)) or not reader.is_current():
        raise NativeToolRegistrationError('NATIVE_BINDING_INVALID')
    if not callable(getattr(ctx,'register_tool',None)):
        raise NativeToolRegistrationError('NATIVE_PLUGIN_CONTEXT_INVALID')
    refusal=_loading_mode_refusal(ctx)
    if refusal:
        raise NativeToolRegistrationError(refusal)
    scope=_ctx_scope(ctx)
    if type(profile_id) is not str or not profile_id or _ctx_profile_name(ctx)!=profile_id:
        raise NativeToolRegistrationError('NATIVE_PROFILE_MISMATCH')
    if isinstance(reader,HostLeadershipBinding) and reader.profile_id!=profile_id:
        raise NativeToolRegistrationError('NATIVE_PROFILE_MISMATCH')
    registry=_registry()
    try:
        from registration_lifecycle import replacement_coordinator
    except Exception:
        raise NativeToolRegistrationError('NATIVE_PLUGIN_API_UNAVAILABLE') from None
    live={'entry':None,'active':False}
    def current():
        return (live['active'] and _ctx_scope(ctx)==scope
            and _ctx_profile_name(ctx)==profile_id
            and registry.snapshot_registration(TOOL_NAME,scope=scope) is live['entry']
            and reader.is_current())
    handler=native_handler(reader,native_current=current)
    check_fn=lambda: _current(current)
    # Native replacement owner serializes registration, not a second lock/registry.
    with replacement_coordinator.transaction():
        if registry.snapshot_registration(TOOL_NAME,scope=scope) is not None:
            raise NativeToolRegistrationError('NATIVE_TOOL_COLLISION')
        if registry.get_entry(TOOL_NAME,scope=scope) is not None:
            raise NativeToolRegistrationError('NATIVE_TOOL_NAME_TAKEN')
        try:
            handle=ctx.register_tool(name=TOOL_NAME,toolset=TOOLSET,schema=TOOL_SCHEMA,
                handler=handler,check_fn=check_fn,is_async=True,
                description=TOOL_SCHEMA['description'],emoji='mmx')
        except Exception:
            raise NativeToolRegistrationError('NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN',
                context=ctx,binding=reader,scope=scope) from None
        if handle is None:
            code=('NATIVE_TOOL_NOT_REGISTERED' if registry.snapshot_registration(TOOL_NAME,scope=scope) is None
                  else 'NATIVE_TOOL_REGISTRATION_EFFECT_UNKNOWN')
            raise NativeToolRegistrationError(code,context=ctx,binding=reader,scope=scope)
        try:
            entry=registry.snapshot_registration(TOOL_NAME,scope=scope)
            if (entry is None or entry.handler is not handler or entry.check_fn is not check_fn
                    or entry.schema!=TOOL_SCHEMA or entry.toolset!=TOOLSET or entry.is_async is not True):
                raise NativeToolRegistrationError('NATIVE_TOOL_READBACK_MISMATCH')
        except Exception:
            try:
                handle.dispose()
            except Exception:
                raise NativeToolRegistrationError('NATIVE_TOOL_ROLLBACK_EFFECT_UNKNOWN',
                    context=ctx,binding=reader,scope=scope,handle=handle) from None
            raise NativeToolRegistrationError('NATIVE_TOOL_READBACK_MISMATCH') from None
        live.update(entry=entry,active=True)
        return NativeLeadershipRegistration(handler,check_fn,handle,entry,scope,live)
