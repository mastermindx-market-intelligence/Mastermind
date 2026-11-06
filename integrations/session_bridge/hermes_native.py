"""Secretary transport projection for the existing installed Session Bridge.

The selected composition owns the route. Runtime owns original requests and
commit evidence; Hermes owns its session, admission and answer. This adapter
creates no session, retry, state store or listener.
"""
from __future__ import annotations

import json
import inspect
import re

from control_plane.executive_fabric_composition import FabricBindingSource
from control_plane.remote_worker_transport import (
    validate_secretary_native_id, validate_secretary_native_target,
)
from .schemas import BridgeError
from control_plane.native_continuation import (
    HERMES_KIND, HERMES_RESULT_SCHEMAS, hermes_family, hermes_family_for_schema,
    hermes_family_for_target, _hermes_operation_key,
)

BINDING_SCHEMA = "mastermind.session_bridge.hermes_secretary_binding.v1"
RESULT_SCHEMA = "mastermind.session_bridge.hermes_secretary_result.v1"
RESULT_SCHEMAS = HERMES_RESULT_SCHEMAS
META_RESULT_SCHEMA = hermes_family("hermes_meta").result_schema
NATIVE_SCHEMA = "mastermind.hermes_secretary_native_control/v1"
# Fits the incumbent 32 KiB private frame and 24 KiB public tool wrapper.
MAX_PUBLIC_RESULT_BYTES = 23 * 1024
_RESULT_FIELDS = frozenset({
    "schema", "target_ref", "operation_key", "read_ref", "request_ref",
    "request_revision", "native_input_sha256", "commit_started", "native_status",
    "admission", "answer", "successful", "parent_consumed",
})
_ADMISSION_FIELDS = frozenset({
    "admission_id", "sequence", "status", "outcome", "authority_epoch",
    "execution_generation",
})
_NATIVE_STATUSES = frozenset({
    "OBSERVED", "ADMITTED", "NOT_SUBMITTED", "REFUSED", "EFFECT_UNKNOWN", "UNAVAILABLE",
})
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _text(value, *, empty=False, limit=1024):
    if (type(value) is not str or (not empty and not value) or len(value) > limit
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("invalid native text")
    value.encode("utf-8", "strict")
    return value


def _admission(value, binding=None):
    expected = _ADMISSION_FIELDS | ({"ref"} if binding is not None else set())
    if type(value) is not dict or set(value) != expected:
        raise ValueError("invalid native admission")
    validate_secretary_native_id(value["admission_id"])
    if binding is not None and value["ref"] != {
            "profile_id": binding["profile_id"], "session_id": binding["session_id"]}:
        raise ValueError("native admission belongs to another session")
    if value["status"] not in {"queued", "started", "unknown", "terminal"}:
        raise ValueError("invalid native admission state")
    for key in ("sequence", "authority_epoch"):
        if type(value[key]) is not int or value[key] < 1:
            raise ValueError("invalid native admission revision")
    generation = value["execution_generation"]
    if generation is not None and (type(generation) is not int or generation < 0):
        raise ValueError("invalid native execution generation")
    if value["outcome"] is not None:
        _text(value["outcome"], empty=True)
    return {key: value[key] for key in _ADMISSION_FIELDS}


def _answer(value):
    if (type(value) is not str or len(value.encode("utf-8", "strict")) > 64 * 1024
            or any(ord(c) < 32 and c not in "\n\r\t" for c in value)):
        raise ValueError("invalid native answer")
    return value


def validate_public_result(value):
    """Closed public evidence; original IDs join without claiming consumption."""
    from control_plane.native_continuation import _digest, _request_key

    if type(value) is not dict or set(value) != _RESULT_FIELDS:
        raise ValueError("invalid native conversation result")
    family = hermes_family_for_schema(value["schema"], component="result")
    if (hermes_family_for_target(value["target_ref"]) != family
            or type(value["operation_key"]) is not str
            or re.fullmatch(r"session-continue-[0-9a-f]{64}", value["operation_key"]) is None):
        raise ValueError("invalid native conversation result")
    expected_operation = _hermes_operation_key(value["target_ref"])
    if value["operation_key"] != expected_operation:
        raise ValueError("original operation differs from target")
    key = _request_key(value["operation_key"])
    if (value["read_ref"] != "session-reply-" + key
            or value["request_ref"] != "session-bridge-continue:" + key
            or any(type(value[k]) is not str or _SHA.fullmatch(value[k]) is None
                   for k in ("request_revision", "native_input_sha256"))
            or type(value["commit_started"]) is not bool
            or value["parent_consumed"] is not False):
        raise ValueError("invalid original request evidence")
    status = value["native_status"]
    if status is not None and status not in _NATIVE_STATUSES:
        raise ValueError("invalid native result status")
    if not value["commit_started"] and any(value[k] is not None for k in (
            "native_status", "admission", "answer", "successful")):
        raise ValueError("uncommitted request cannot claim native evidence")
    admission = value["admission"]
    if status in {"ADMITTED", "OBSERVED"}:
        _admission(admission)
    elif admission is not None:
        raise ValueError("native admission has no matching status")
    if value["answer"] is not None:
        if (status != "OBSERVED" or admission["status"] != "terminal"
                or type(value["successful"]) is not bool):
            raise ValueError("answer is not a terminal original result")
        _answer(value["answer"])
    elif value["successful"] is not None:
        raise ValueError("success has no original answer")
    if len(_canonical(value)) > MAX_PUBLIC_RESULT_BYTES:
        raise BridgeError("output_too_large", "original answer exceeds the installed response budget")
    return json.loads(_canonical(value))


def public_result(request_event, request, *, commit_started, native_result=None):
    """Project only actual native evidence joined to the stored original request."""
    from control_plane.native_continuation import _digest

    family = hermes_family_for_schema(request["schema"], component="request")
    if request["binding"]["schema"] != family.binding_schema:
        raise ValueError("native conversation result binding family changed")
    status = admission = answer = successful = None
    if native_result is not None:
        if (type(native_result) is not dict or native_result.get("schema") != family.native_schema
                or native_result.get("status") not in _NATIVE_STATUSES):
            raise ValueError("invalid native result")
        status = native_result["status"]
        if status in {"ADMITTED", "OBSERVED"}:
            keys = {"schema", "status", "admission"}
            if status == "OBSERVED" and "answer" in native_result:
                keys |= {"answer", "successful"}
            if set(native_result) != keys:
                raise ValueError("invalid native result fields")
            admission = _admission(native_result["admission"], request["binding"])
            if "answer" in native_result:
                answer = _answer(native_result["answer"])
                successful = native_result["successful"]
                if type(successful) is not bool or admission["status"] != "terminal":
                    raise ValueError("invalid terminal native answer")
        else:
            if set(native_result) not in ({"schema", "status"}, {"schema", "status", "reason"}):
                raise ValueError("invalid native refusal fields")
            if "reason" in native_result and (
                    type(native_result["reason"]) is not str
                    or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", native_result["reason"]) is None):
                raise ValueError("invalid native refusal")
    return validate_public_result({
        "schema": family.result_schema, "target_ref": request["target_ref"],
        "operation_key": request["operation_key"], "read_ref": request["read_ref"],
        "request_ref": request_event.command_id,
        "request_revision": _digest(request_event.to_dict()),
        "native_input_sha256": request["native_input_sha256"],
        "commit_started": commit_started, "native_status": status,
        "admission": admission, "answer": answer, "successful": successful,
        "parent_consumed": False,
    })


class HermesNativeSession:
    """Request-local access to one immutable host-owned native selection."""

    def __init__(self, source, *, read_guard, submit_guard):
        if (type(source) is not FabricBindingSource or not callable(read_guard)
                or not callable(submit_guard)):
            raise TypeError("installed Secretary composition and admission guards required")
        if any(inspect.iscoroutinefunction(guard)
               or inspect.iscoroutinefunction(getattr(guard, "__call__", None))
               for guard in (read_guard, submit_guard)):
            raise TypeError("synchronous installed admission guards required")
        self._source = source
        self._read_guard, self._submit_guard = read_guard, submit_guard

    @staticmethod
    def _guard(callback):
        value = callback()
        if value is not None:
            if inspect.iscoroutine(value):
                value.close()
            raise BridgeError("ingress_unavailable", "installed admission guard is invalid")

    def require_read(self):
        """Fresh ingress/custody admission independent of route availability."""
        self._guard(self._read_guard)

    def selected_binding(self, *, kind=HERMES_KIND):
        family = hermes_family(kind)
        self.require_read()
        selected = (self._source.hermes_secretary_selection() if family.kind == HERMES_KIND
                    else self._source.hermes_meta_selection())
        if selected is None:
            return None
        return {
            "schema": family.binding_schema,
            "composition_sha256": self._source.expected_sha256,
            **{key: getattr(selected, key) for key in (
                "host_ref", "root_id", "root_job_id", "work_ref", "session_id",
                "profile_id", "principal_id", "expected_host_binding_sha256",
                "expected_implementation_sha",
            )},
        }

    def require_binding(self, binding):
        try:
            if type(binding) is not dict:
                raise ValueError
            family = hermes_family_for_schema(binding.get("schema"), component="binding")
        except ValueError:
            raise BridgeError("binding_unavailable", "original native binding is unavailable") from None
        if self.selected_binding(kind=family.kind) != binding:
            raise BridgeError("binding_unavailable", "original native binding is unavailable")

    def require_submit(self, binding):
        self._guard(self._submit_guard)
        self.require_binding(binding)

    async def request(self, binding, native_request, *, before_write=None):
        self.require_binding(binding)
        family = hermes_family_for_schema(binding["schema"], component="binding")
        factory = (self._source.hermes_secretary_client if family.kind == HERMES_KIND
                   else self._source.hermes_meta_client)
        client = factory(root_id=binding["root_id"], session_id=binding["session_id"])
        if client is None:
            raise BridgeError("backend_unavailable", "installed Secretary owner is unavailable")
        send = client.request_secretary if family.kind == HERMES_KIND else client.request_meta
        result = await send(native_request, before_write=before_write)
        self.require_binding(binding)
        if binding["schema"] != family.binding_schema:
            raise BridgeError("binding_unavailable", "original native family changed")
        return result

    async def observe(self, binding):
        family = hermes_family_for_schema(binding["schema"], component="binding")
        result = await self.request(binding, {
            "operation": "observe", "session_id": binding["session_id"],
        })
        if (type(result) is not dict or set(result) != {"schema", "status", "target"}
                or result["schema"] != family.native_schema or result["status"] != "TARGET"):
            raise BridgeError("binding_unavailable", "native Secretary session is unavailable")
        target = validate_secretary_native_target(result["target"])
        if any(target[key] != binding[key] for key in ("profile_id", "session_id", "principal_id")):
            raise BridgeError("binding_unavailable", "native Secretary selection differs")
        return target
