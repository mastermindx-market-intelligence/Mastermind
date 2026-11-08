"""Closed native READ data contracts; no transport, account or session owner."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from typing import Any
from common.executive_principal_namespace import principal_scope_from_identity
from common.session_bridge_private_contract import BridgeError
from control_plane.executive_ceo_ingress import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES
from control_plane.principal_projection import NeutralPrincipalProjection
from control_plane.workstream_admission_contract import canonical_work_ref
from control_plane.native_provider_attestation import DSH_DONOR_SHA as PIN

REQUEST_SCHEMA = "mastermind.dsh.native_read.v1"
RESPONSE_SCHEMA = "mastermind.dsh.native_read_result.v1"
ASSOCIATION_SCHEMA = "mastermind.dsh.native_read_association.v1"
RESULT_SCHEMA = "mastermind.session_bridge.native_history.v1"
_SHA = re.compile(r"[0-9a-f]{64}")
_ROOT = re.compile(r"JOB-[0-9]{1,9}")
_MAX_SAFE = 2**53 - 1

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


class NativeReadUnavailable(Exception):
    """Fixed private failure, with no host path or arbitrary backend text."""


class NativeReadPhysicalUnknown(NativeReadUnavailable):
    """The original finite read child has not proved physical settlement."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8", errors="strict")


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate native frame field")
        value[key] = item
    return value


def _invalid_number(_):
    raise ValueError("non-JSON native number")


def _result_data(value, request):
    """Validate bounded bytes from the original native result content owner."""
    import base64
    import hashlib
    from control_plane.native_conversation_protocol import NativeClaim, NativeTerminal
    keys = {"kind", "state", "claim", "terminal", "turn_start_seq", "turn_end_seq",
            "user_message_seq", "assistant_message_seqs", "content"}
    if type(value) is not dict or set(value) != keys or value["kind"] != "result":
        raise NativeReadUnavailable()
    claim, terminal = NativeClaim.parse(value["claim"]), NativeTerminal.parse(value["terminal"])
    if (value["claim"] != request["claim"] or value["terminal"] != request["terminal"]
            or terminal.claim != claim):
        raise NativeReadUnavailable()
    start, end, user, assistants = (value[k] for k in (
        "turn_start_seq", "turn_end_seq", "user_message_seq", "assistant_message_seqs"))
    if (type(start) is not int or type(end) is not int
            or not 0 <= start <= claim.through_seq <= end <= terminal.through_seq
            or user is not None and (type(user) is not int or not claim.through_seq < user < end)
            or type(assistants) is not list or len(assistants) > 4096
            or any(type(seq) is not int or not start < seq < end for seq in assistants)
            or assistants != sorted(set(assistants))):
        raise NativeReadUnavailable()
    if value["state"] == "NO_ANSWER":
        if (assistants or value["content"] is not None or request["offset_bytes"] != 0
                or request["expected_sha256"] is not None):
            raise NativeReadUnavailable()
        return
    if value["state"] != "CONTENT" or user is None or not assistants or assistants[0] <= user:
        raise NativeReadUnavailable()
    part = value["content"]
    if (type(part) is not dict or set(part) != {
            "encoding", "format", "sha256", "total_bytes", "offset_bytes", "next_offset_bytes", "data"}
            or part["encoding"] != "base64" or part["format"] != "dsh-session-history-records-json"
            or type(part["sha256"]) is not str or _SHA.fullmatch(part["sha256"]) is None
            or type(part["total_bytes"]) is not int or not 1 <= part["total_bytes"] <= 4*1024*1024
            or type(part["offset_bytes"]) is not int or part["offset_bytes"] != request["offset_bytes"]
            or not 0 <= part["offset_bytes"] < part["total_bytes"]
            or type(part["data"]) is not str or not 1 <= len(part["data"]) <= 5464
            or request["expected_sha256"] is not None and part["sha256"] != request["expected_sha256"]):
        raise NativeReadUnavailable()
    raw = base64.b64decode(part["data"], validate=True)
    after = part["offset_bytes"] + len(raw)
    expected = None if after == part["total_bytes"] else after
    if (not 1 <= len(raw) <= 4096 or after > part["total_bytes"]
            or base64.b64encode(raw).decode("ascii") != part["data"]
            or part["next_offset_bytes"] != expected
            or expected is not None and type(part["next_offset_bytes"]) is not int
            or part["offset_bytes"] == 0 and expected is None and hashlib.sha256(raw).hexdigest() != part["sha256"]):
        raise NativeReadUnavailable()


def validate_native_read_association(value: Any) -> dict[str, Any]:
    """Validate a projection; only the original installed source gives it authority."""
    from common.session_bridge_private_contract import BridgeError
    if type(value) is not dict or set(value) != {
            "schema", "work_ref", "root_job_id", "native_session_id", "owner_principal_scope",
            "composition_sha256", "native_package_sha256", "donor_sha"}:
        raise NativeReadUnavailable()
    try:
        fields = {k: v for k, v in value.items() if k != "schema"}
        selected = DeepSeekNativeAssociation(**fields)
        if selected.document() != value:
            raise ValueError()
        return json.loads(canonical(value))
    except (TypeError, ValueError, UnicodeError, RecursionError, BridgeError):
        raise NativeReadUnavailable() from None


def validate_native_read_request(value: Any, association_sha256: str) -> dict[str, Any]:
    """The same bounded finite request on the original raw or ACP carrier."""
    from control_plane.native_conversation_protocol import NativeClaim, NativeTerminal
    try:
        if (type(value) is not dict or set(value) != {
                "schema", "request_id", "association_sha256", "principal", "read"}
                or value["schema"] != REQUEST_SCHEMA
                or type(value["request_id"]) is not str or _SHA.fullmatch(value["request_id"]) is None
                or value["association_sha256"] != association_sha256
                or type(association_sha256) is not str or _SHA.fullmatch(association_sha256) is None
                or len(canonical(value)) + 1 > MAX_REQUEST_BYTES):
            raise ValueError()
        principal = value["principal"]
        if (type(principal) is not dict or set(principal) != {"principal_scope", "issued_at", "expires_at"}
                or type(principal["principal_scope"]) is not str or _SHA.fullmatch(principal["principal_scope"]) is None
                or type(principal["issued_at"]) is not int or type(principal["expires_at"]) is not int
                or not 0 <= principal["issued_at"] < principal["expires_at"] <= 2**53-1):
            raise ValueError()
        read = value["read"]
        if type(read) is not dict:
            raise ValueError()
        if read == {"kind": "snapshot"}:
            pass
        elif set(read) == {"kind", "through_seq", "before_seq", "max_messages"} and read["kind"] == "page":
            through, before, count = (read[k] for k in ("through_seq", "before_seq", "max_messages"))
            if (type(through) is not int or not -1 <= through <= 2**53-1
                    or before is not None and (type(before) is not int or not 0 <= before <= min(through+1, 2**53-1))
                    or type(count) is not int or not 1 <= count <= 8):
                raise ValueError()
        elif set(read) == {"kind", "claim", "terminal", "offset_bytes", "expected_sha256"} and read["kind"] == "result":
            claim, terminal = NativeClaim.parse(read["claim"]), NativeTerminal.parse(read["terminal"])
            offset, digest = read["offset_bytes"], read["expected_sha256"]
            if (terminal.claim != claim or type(offset) is not int or not 0 <= offset < 4*1024*1024
                    or digest is not None and (type(digest) is not str or _SHA.fullmatch(digest) is None)
                    or offset > 0 and digest is None):
                raise ValueError()
        else:
            raise ValueError()
        return json.loads(canonical(value))
    except (TypeError, ValueError, UnicodeError, KeyError, RecursionError):
        raise NativeReadUnavailable() from None


def validate_native_read_response(value: Any, request: dict[str, Any]) -> dict[str, Any]:
    try:
        if (type(value) is not dict
                or set(value) != {"schema", "request_id", "association_sha256", "status", "data"}
                or value["schema"] != RESPONSE_SCHEMA or value["request_id"] != request["request_id"]
                or value["association_sha256"] != request["association_sha256"]
                or value["status"] not in ("READ", "PAGE_TOO_LARGE", "UNAVAILABLE")
                or len(canonical(value)) + 1 > MAX_RESPONSE_BYTES
                or value["status"] == "READ" and request["read"]["kind"] != "result" and (
                    type(value["data"]) is not dict or set(value["data"]) != {"projections", "page"})
                or value["status"] != "READ" and value["data"] is not None):
            raise NativeReadUnavailable()
        if value["status"] == "READ" and request["read"]["kind"] == "result":
            _result_data(value["data"], request["read"])
        return json.loads(canonical(value))
    except (TypeError, ValueError, UnicodeError, KeyError, RecursionError):
        raise NativeReadUnavailable() from None


def native_read_frame(*, association_sha256: str, principal_scope: str,
                      issued_at: int, expires_at: int, request: Mapping[str, Any]) -> dict[str, Any]:
    return validate_native_read_request({
        "schema": REQUEST_SCHEMA, "request_id": secrets.token_hex(32),
        "association_sha256": association_sha256,
        "principal": {"principal_scope": principal_scope, "issued_at": issued_at, "expires_at": expires_at},
        "read": dict(request)}, association_sha256)


def validate_native_history_binding(value):
    """Actual Worker receipt plus the current reader; never execution authority."""
    if (type(value) is not dict or set(value) != {
            "schema", "binding", "materialization_receipt_sha256"}
            or value["schema"] != "mastermind.dsh.native_history_binding.v1"
            or type(value["materialization_receipt_sha256"]) is not str
            or _SHA.fullmatch(value["materialization_receipt_sha256"]) is None):
        raise NativeReadUnavailable()
    return {"schema": value["schema"],
            "binding": validate_native_read_binding(value["binding"]),
            "materialization_receipt_sha256": value["materialization_receipt_sha256"]}


def validate_native_read_binding(value: Any) -> dict[str, str]:
    from control_plane.native_conversation_protocol import native_id
    try:
        if (type(value) is not dict or set(value) != {
                "schema", "native_session_id", "native_package_sha256", "donor_sha"}
                or value["schema"] != "mastermind.dsh.native_read_binding.v1"
                or value["donor_sha"] != PIN
                or type(value["native_package_sha256"]) is not str
                or _SHA.fullmatch(value["native_package_sha256"]) is None):
            raise ValueError()
        native_id(value["native_session_id"])
        return dict(value)
    except (TypeError, ValueError, KeyError):
        raise NativeReadUnavailable() from None
