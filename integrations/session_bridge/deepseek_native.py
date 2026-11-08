"""Request-local cold history access through the installed native process owner.

The association and connected port are trusted composition capabilities. No
browser selector, cookie, JSON FD, path, URL or principal projection creates
them. This module owns no session, transcript, operation ledger or provider.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import re
from collections.abc import Mapping
from typing import Any, Callable

from common.executive_principal_namespace import principal_scope_from_identity
from common.session_bridge_private_contract import BridgeError, private_result
from control_plane.executive_ceo_ingress import MAX_RESPONSE_BYTES
from control_plane.principal_projection import NeutralPrincipalProjection
from control_plane.workstream_admission_contract import canonical_work_ref
from integrations.deepseek_harness.native_read_port import (
    OwnedNativeReadPort, NativeReadUnavailable, canonical,
)

from control_plane.native_conversation_read_contract import (
    ASSOCIATION_SCHEMA,
    RESULT_SCHEMA,
    PIN,
    _SHA,
    _ROOT,
    _MAX_SAFE,
    _text,
    principal_namespace,
    validate_native_read_arguments,
    DeepSeekNativeAssociation,
)


def _guard(callback: Callable[[], None]) -> None:
    value = callback()
    if value is not None:
        if inspect.iscoroutine(value):
            value.close()
        raise BridgeError("ingress_unavailable", "installed native read guard is invalid")


class DeepSeekNativeReadSource:
    """One already-connected capability supplied by the original live launcher."""

    def __init__(self, association: DeepSeekNativeAssociation, port: OwnedNativeReadPort,
                 *, require_current: Callable[[], None]):
        from integrations.session_bridge.retained_native_read import RetainedNativeReadPort
        if (type(association) is not DeepSeekNativeAssociation or type(port) not in (OwnedNativeReadPort, RetainedNativeReadPort)
                or not callable(require_current) or inspect.iscoroutinefunction(require_current)
                or inspect.iscoroutinefunction(getattr(require_current, "__call__", None))
                or port.association_sha256 != association.digest):
            raise TypeError("trusted native process capability and association required")
        self._association, self._port, self._guard = association, port, require_current
        self._captured = (association, port, require_current, association.digest)
        self.require_current()

    def require_current(self) -> None:
        association, port, guard, digest = self._captured
        if (self._association is not association or self._port is not port or self._guard is not guard
                or association.digest != digest or port.association_sha256 != digest):
            raise BridgeError("binding_unavailable", "native session association changed")
        _guard(guard)
        try:
            port.require_current()
        except NativeReadUnavailable:
            raise BridgeError("backend_unavailable", "original native read port is unavailable") from None

    def binding(self) -> DeepSeekNativeAssociation:
        self.require_current()
        return self._association

    async def read(self, binding, principal, request, *, before_write):
        self.require_current()
        if binding is not self._association:
            raise BridgeError("binding_unavailable", "original native association is unavailable")
        try:
            value = await self._port.read(
                principal_scope=principal_namespace(principal),
                issued_at=principal.issued_at, expires_at=principal.expires_at,
                request=request, before_write=before_write)
        except NativeReadUnavailable:
            raise BridgeError("backend_unavailable", "original native read port is unavailable") from None
        self.require_current()
        if value["status"] == "PAGE_TOO_LARGE":
            raise BridgeError("response_too_large", "complete native history page exceeds the read limit")
        if value["status"] != "READ":
            raise BridgeError("backend_unavailable", "original native history is unavailable")
        return value["data"]


class DeepSeekNativeSession:
    """Request-local installed READ guard; no submit/follow/resume capability."""

    def __init__(self, source: DeepSeekNativeReadSource, *, read_guard: Callable[[], None]):
        if (type(source) is not DeepSeekNativeReadSource or not callable(read_guard)
                or inspect.iscoroutinefunction(read_guard)
                or inspect.iscoroutinefunction(getattr(read_guard, "__call__", None))):
            raise TypeError("installed native read source and synchronous guard required")
        self._source, self._read_guard = source, read_guard

    def require_read(self):
        _guard(self._read_guard)
        self._source.require_current()

    def selected_binding(self):
        self.require_read()
        return self._source.binding()

    def require_binding(self, binding):
        if type(binding) is not DeepSeekNativeAssociation or self.selected_binding() is not binding:
            raise BridgeError("binding_unavailable", "original native association is unavailable")

    async def read_history(self, binding, principal, request, *, before_read):
        self.require_binding(binding)
        if principal_namespace(principal) != binding.owner_principal_scope:
            raise BridgeError("reply_unavailable", "authorized native history is unavailable")

        def before_write():
            self.require_binding(binding)
            _guard(before_read)

        value = await self._source.read(binding, principal, request, before_write=before_write)
        self.require_binding(binding)
        _guard(before_read)
        return value


def bounded_native_result(data: Mapping[str, Any]) -> dict[str, Any]:
    """Check the actual private wrapper plus CeoIngress wrapper and newline."""
    output = dict(data)
    response = {"ok": True, "result": private_result("session_native_read", data=output)}
    if len(canonical(response)) + 1 > MAX_RESPONSE_BYTES:
        raise BridgeError("response_too_large", "complete native history page exceeds the read limit")
    return output
