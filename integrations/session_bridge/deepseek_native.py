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
from integrations.deepseek_harness.runtime_compat.prepare_native_session import PIN

ASSOCIATION_SCHEMA = "mastermind.dsh.native_read_association.v1"
RESULT_SCHEMA = "mastermind.session_bridge.native_history.v1"
_SHA = re.compile(r"[0-9a-f]{64}")
_ROOT = re.compile(r"JOB-[0-9]{1,9}")
_MAX_SAFE = 2**53 - 1


def _guard(callback: Callable[[], None]) -> None:
    value = callback()
    if value is not None:
        if inspect.iscoroutine(value):
            value.close()
        raise BridgeError("ingress_unavailable", "installed native read guard is invalid")


def _text(value, maximum):
    return (type(value) is str and 0 < len(value) <= maximum
            and not any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value))


def principal_namespace(principal: NeutralPrincipalProjection) -> str:
    return principal_scope_from_identity(
        issuer_digest=principal.issuer_digest, subject_digest=principal.subject_digest,
        client_ref=principal.client_ref, resource=principal.resource)


def validate_native_read_arguments(value: Any) -> dict[str, Any]:
    """Closed selection/cursor syntax only; never a native-session association."""
    if type(value) is not dict or set(value) != {"selection", "read"}:
        raise BridgeError("invalid_input", "native history requires an exact selection and read")
    selected, request = value["selection"], value["read"]
    if (type(selected) is not dict or set(selected) != {"work_ref", "root_job_id"}
            or type(selected["root_job_id"]) is not str or _ROOT.fullmatch(selected["root_job_id"]) is None):
        raise BridgeError("invalid_input", "native history selection is invalid")
    try:
        work = canonical_work_ref(selected["work_ref"])
        if work != selected["work_ref"]:
            raise ValueError()
    except (TypeError, ValueError):
        raise BridgeError("invalid_input", "native history selection is invalid") from None
    if type(request) is not dict:
        raise BridgeError("invalid_input", "native history read is invalid")
    if request == {"kind": "snapshot"}:
        normalized = {"kind": "snapshot"}
    elif set(request) == {"kind", "through_seq", "before_seq", "max_messages"} and request["kind"] == "page":
        through, before, count = request["through_seq"], request["before_seq"], request["max_messages"]
        if (type(through) is not int or not -1 <= through <= _MAX_SAFE
                or (before is not None and (type(before) is not int or not 0 <= before <= min(_MAX_SAFE, through + 1)))
                or type(count) is not int or not 1 <= count <= 8):
            raise BridgeError("invalid_input", "native history cursor is invalid")
        normalized = {"kind": "page", "through_seq": through, "before_seq": before, "max_messages": count}
    elif set(request) == {"kind", "native_ref", "offset_bytes", "expected_sha256"} and request["kind"] == "result":
        from control_plane.native_conversation_result import NativeConversationResultRef
        try:
            reference = NativeConversationResultRef.from_wire(request["native_ref"])
        except (ValueError, TypeError):
            raise BridgeError("invalid_input", "native history result reference is invalid") from None
        offset, digest = request["offset_bytes"], request["expected_sha256"]
        if (type(offset) is not int or not 0 <= offset < 4*1024*1024
                or digest is not None and (type(digest) is not str or _SHA.fullmatch(digest) is None)
                or offset > 0 and digest is None):
            raise BridgeError("invalid_input", "native history result cursor is invalid")
        normalized = dict(kind="result", native_ref=reference.to_wire(), offset_bytes=offset, expected_sha256=digest)
    else:
        raise BridgeError("invalid_input", "native history read is invalid")
    return {"selection": {"work_ref": work, "root_job_id": selected["root_job_id"]}, "read": normalized}


@dataclasses.dataclass(frozen=True, slots=True)
class DeepSeekNativeAssociation:
    """One explicit installed selection, never discovered from local sessions."""

    work_ref: str
    root_job_id: str
    native_session_id: str
    owner_principal_scope: str
    composition_sha256: str
    native_package_sha256: str
    donor_sha: str = PIN

    def __post_init__(self):
        validate_native_read_arguments({"selection": {
            "work_ref": self.work_ref, "root_job_id": self.root_job_id}, "read": {"kind": "snapshot"}})
        if (not _text(self.native_session_id, 256) or self.donor_sha != PIN
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in (self.owner_principal_scope, self.composition_sha256, self.native_package_sha256))):
            raise TypeError("qualified installed native association required")

    def document(self) -> dict[str, Any]:
        return {"schema": ASSOCIATION_SCHEMA, **dataclasses.asdict(self)}

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical(self.document())).hexdigest()


class DeepSeekNativeReadSource:
    """One already-connected capability supplied by the original live launcher."""

    def __init__(self, association: DeepSeekNativeAssociation, port: OwnedNativeReadPort,
                 *, require_current: Callable[[], None]):
        from control_plane.native_conversation_read import RetainedNativeReadPort
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
