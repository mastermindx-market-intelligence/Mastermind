"""One finite read on an already-owned native-process socket-pair endpoint.

No address, FD number, credential, listener, child, reconnect, queue or retry is
accepted here. The trusted existing process composition supplies the capability;
wire projections never authenticate themselves.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import secrets
import socket
from collections.abc import Callable, Mapping
from typing import Any

from control_plane.executive_ceo_ingress import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES

REQUEST_SCHEMA = "mastermind.dsh.native_read.v1"
RESPONSE_SCHEMA = "mastermind.dsh.native_read_result.v1"
_SHA = re.compile(r"[0-9a-f]{64}")


class NativeReadUnavailable(Exception):
    """Fixed private failure, with no host path or arbitrary backend text."""


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
    from integrations.deepseek_harness.native_protocol import NativeClaim, NativeTerminal
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
    from integrations.session_bridge.deepseek_native import DeepSeekNativeAssociation
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
    from integrations.deepseek_harness.native_protocol import NativeClaim, NativeTerminal
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


def validate_native_read_binding(value: Any) -> dict[str, str]:
    from integrations.deepseek_harness.runtime_compat.prepare_native_session import PIN
    from integrations.deepseek_harness.native_protocol import native_id
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


class OwnedNativeReadPort:
    """Nominal capability for one anonymous endpoint, under its original owner."""

    def __init__(self, endpoint: socket.socket, *, association_sha256: str):
        try:
            valid_endpoint = (
                type(endpoint) is socket.socket and endpoint.family == socket.AF_UNIX
                and endpoint.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM
                and endpoint.getsockname() in ("", b"")
                and endpoint.getpeername() in ("", b""))
        except OSError:
            valid_endpoint = False
        # getpeername proves connection and excludes listeners. SO_ACCEPTCONN
        # is unavailable on Darwin AF_UNIX socket pairs and adds no authority.
        if (not valid_endpoint or type(association_sha256) is not str
                or _SHA.fullmatch(association_sha256) is None):
            raise TypeError("owned anonymous native socket-pair capability required")
        self._endpoint = endpoint
        self._fd = endpoint.fileno()
        info = os.fstat(self._fd)
        self._identity = (info.st_dev, info.st_ino)
        self._association_sha256 = association_sha256
        self._retired = False
        self._busy = False
        endpoint.setblocking(False)

    @property
    def association_sha256(self) -> str:
        return self._association_sha256

    def require_current(self) -> None:
        try:
            info = os.fstat(self._endpoint.fileno())
            if (self._retired or self._endpoint.fileno() != self._fd
                    or (info.st_dev, info.st_ino) != self._identity):
                raise NativeReadUnavailable()
        except (OSError, ValueError):
            raise NativeReadUnavailable() from None

    def retire(self) -> None:
        if self._retired:
            return
        self._retired = True
        self._endpoint.close()

    async def read(self, *, principal_scope: str, issued_at: int, expires_at: int,
                   request: Mapping[str, Any], before_write: Callable[[], None]) -> dict[str, Any]:
        self.require_current()
        if self._busy or not callable(before_write):
            raise NativeReadUnavailable()
        if (type(principal_scope) is not str or _SHA.fullmatch(principal_scope) is None
                or type(issued_at) is not int or type(expires_at) is not int
                or not 0 <= issued_at < expires_at <= 2**53-1):
            raise NativeReadUnavailable()
        # Correlation for one finite invocation, never an authorization epoch.
        request_id = secrets.token_hex(32)
        frame = {"schema": REQUEST_SCHEMA, "request_id": request_id,
                 "association_sha256": self._association_sha256,
                 "principal": {"principal_scope": principal_scope,
                               "issued_at": issued_at, "expires_at": expires_at},
                 "read": dict(request)}
        try:
            encoded = canonical(frame) + b"\n"
        except (TypeError, ValueError, UnicodeError):
            raise NativeReadUnavailable() from None
        if len(encoded) > MAX_REQUEST_BYTES:
            raise NativeReadUnavailable()
        self._busy = True
        try:
            async with asyncio.timeout(4.0):
                self.require_current()
                guard_result = before_write()
                if guard_result is not None:
                    if inspect.iscoroutine(guard_result):
                        guard_result.close()
                    raise NativeReadUnavailable()
                loop = asyncio.get_running_loop()
                await loop.sock_sendall(self._endpoint, encoded)
                received = bytearray()
                while b"\n" not in received:
                    block = await loop.sock_recv(self._endpoint, min(4096, MAX_RESPONSE_BYTES + 1-len(received)))
                    if not block:
                        raise NativeReadUnavailable()
                    received.extend(block)
                    if len(received) > MAX_RESPONSE_BYTES:
                        raise NativeReadUnavailable()
                line, extra = bytes(received).split(b"\n", 1)
                if extra:
                    raise NativeReadUnavailable()
                value = json.loads(line.decode("utf-8", errors="strict"),
                                   object_pairs_hook=_unique_object, parse_constant=_invalid_number)
                value = validate_native_read_response(value, frame)
                self.require_current()
                return value
        except BaseException:
            # A partial frame or interrupted read cannot be re-homed/replayed.
            # Closing the original endpoint retires its native Peer as well.
            self.retire()
            raise
        finally:
            self._busy = False
