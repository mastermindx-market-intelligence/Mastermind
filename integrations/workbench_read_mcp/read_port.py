"""Stateless bridge from a verified read caller to the existing file observer.

This is not a grant issuer, project registry, thread/process owner, or root opener.
The deployment owner supplies current project bindings and its existing bounded
I/O executor. The returned callback is usable only behind authenticated_read_app.
A hand-constructed ReadCaller/ProjectReadBinding is not authentication evidence.
"""
from __future__ import annotations

import dataclasses
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .app import ReadCaller, ProjectReadRefused
from .observer import ReadScope, ReadRefusal, observe_file


@dataclasses.dataclass(frozen=True)
class ProjectReadBinding:
    """Request-local projection of an EXISTING owner decision; no persistence."""
    caller: ReadCaller
    project_ref: str
    scope: ReadScope


BindingResolver = Callable[[ReadCaller, str], ProjectReadBinding | None]
ReadExecutor = Callable[[Callable[[], dict[str, Any]]], Awaitable[dict[str, Any]]]
_REQUEST_KEYS = frozenset({'project_ref', 'relative_path', 'line_start', 'line_count', 'expected_sha256'})


def create_descriptor_read_port(
    *, resolve_binding: BindingResolver, clock_ms: Callable[[], int],
    run_io: ReadExecutor,
) -> Callable[[ReadCaller, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]:
    """Compose without starting I/O, acquiring roots, or minting access.

    resolve_binding MUST check the current approved subject/project configuration,
    resource/client scope, root identity and revocation. run_io MUST use the
    existing node's bounded I/O admission/deadline mechanism; no default executor
    or inline fallback is provided. Cancelling observation does not undo reads
    already in the kernel. This layer makes no Windows or atomic-snapshot claim.
    """
    if not all(callable(f) for f in (resolve_binding, clock_ms, run_io)):
        raise TypeError('explicit binding, clock and I/O integration required')

    async def read(caller: ReadCaller, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        if type(caller) is not ReadCaller:
            raise ProjectReadRefused()
        if (type(caller.expires_at) is not int or type(caller.scopes) is not tuple
            or caller.scopes != ('workbench.read',)
            or any(type(getattr(caller,n)) is not str for n in ('subject_digest','client_ref','resource'))):
            raise ProjectReadRefused()
        try:
            request = dict(arguments)
            if set(request) - _REQUEST_KEYS:
                raise ProjectReadRefused()
            project = request['project_ref']
            if type(project) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', project) is None:
                raise ProjectReadRefused()
            selected = {'relative_path': request['relative_path']}
            for old, new in [('line_start','start_line'),('line_count','max_lines'),('expected_sha256','expected_sha256')]:
                if old in request:
                    selected[new] = request[old]
        except ProjectReadRefused:
            raise
        except Exception:
            raise ProjectReadRefused() from None
        # Copy scalar caller fields before entering another owner's callback.
        expected_caller = dataclasses.replace(caller)

        def binding() -> ProjectReadBinding:
            try:
                timestamp = clock_ms()
                if type(timestamp) is not int or timestamp < 0 or timestamp >= expected_caller.expires_at * 1000:
                    raise ProjectReadRefused()
                value = resolve_binding(expected_caller, project)
                if (type(value) is not ProjectReadBinding or type(value.caller) is not ReadCaller
                    or value.caller != expected_caller or type(value.project_ref) is not str
                    or value.project_ref != project or type(value.scope) is not ReadScope):
                    raise ProjectReadRefused()
                # Cap file-scope lifetime at the request credential's lifetime.
                scope = dataclasses.replace(value.scope,
                    expires_at_ms=min(value.scope.expires_at_ms, expected_caller.expires_at * 1000))
                return ProjectReadBinding(expected_caller, project, scope)
            except ProjectReadRefused:
                raise
            except Exception:
                raise ProjectReadRefused() from None

        original = binding()  # Refuse foreign/unavailable projects before I/O admission.
        def current_scope() -> ReadScope:
            current = binding()
            if current != original:
                raise ProjectReadRefused('READ_BINDING_CHANGED')
            return current.scope

        def operation() -> dict[str, Any]:
            return observe_file(selected, current_scope, clock_ms=clock_ms)

        try:
            pending = run_io(operation)
            if not inspect.isawaitable(pending):
                raise ProjectReadRefused()
            observed = await pending
            # A queued/completed I/O result is not permission after revocation.
            current_scope()
            if type(observed) is not dict:
                raise ProjectReadRefused()
            return {**observed, 'project_ref': project}
        except ProjectReadRefused:
            raise
        except ReadRefusal as error:
            if error.code == 'PREIMAGE_MISMATCH':
                code = 'READ_PREIMAGE_MISMATCH'
            elif error.code in {'FILE_CHANGED','FILE_IDENTITY_CHANGED','ROOT_IDENTITY_CHANGED','ANCESTRY_CHANGED'}:
                code = 'READ_SOURCE_CHANGED'
            elif error.code in {'SCOPE_CHANGED','SCOPE_EXPIRED','SCOPE_UNAVAILABLE'}:
                code = 'READ_BINDING_CHANGED'
            else:
                code = 'PROJECT_READ_REFUSED'
            raise ProjectReadRefused(code) from None
        except Exception:
            raise ProjectReadRefused() from None

    return read
