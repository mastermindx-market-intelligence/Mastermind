"""One authenticated request to the already-selected Secretary role gateway.

The existing native owner admits/deduplicates submissions. This adapter has no
retry, session state, token enrollment or provider capability of its own.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import hmac
import json
import os
import re
import socket

from common.hermes_role_status_contract import closed_json
from control_plane.remote_worker_transport import TransportEffect, TransportError
from integrations.hermes_runtime.constants import (
    SECRETARY_PATH, SECRETARY_ROLE_REQUEST_SCHEMA, SECRETARY_ROLE_RESPONSE_SCHEMA,
    conversation_contract,
)
from integrations.hermes_runtime.egress import ROLE_PROXY_HOST
from ops.executive_os.remote_worker_gateway_config import (
    HermesSecretaryConversationBinding, HermesMetaConversationBinding,
)
from ops.executive_os.hermes_role_metadata_observer import (
    _HeldRoleQualification, qualify_secretary_listener, qualify_meta_listener,
)

_MAX_REQUEST = 64 * 1024
_MAX_RESPONSE = 256 * 1024
_MAX_HEADERS = 8192
_TOKEN = re.compile(rb"[A-Za-z0-9._~+/=-]{16,256}")


class _HermesConversationForwarder:
    def __init__(self, binding, *, role: str,
                 expected_group_gid: int, timeout_seconds: float) -> None:
        self._contract = conversation_contract(role)
        expected_binding = (HermesSecretaryConversationBinding if role == "mmsecretary"
                            else HermesMetaConversationBinding)
        if (type(binding) is not expected_binding
                or type(expected_group_gid) is not int or expected_group_gid < 0
                or type(timeout_seconds) not in (int, float)
                or not 0.1 <= timeout_seconds <= 10.0):
            raise ValueError("Secretary forwarding binding is invalid")
        self.binding = binding
        self._group = expected_group_gid
        self._timeout = float(timeout_seconds)
        self._token = self._read_token()

    def has_same_credential(self, other) -> bool:
        if type(other) not in {HermesSecretaryForwarder, HermesMetaForwarder}:
            raise ValueError("conversation forwarding peer is invalid")
        return hmac.compare_digest(self._token, other._token)

    async def _qualify_listener(self, held, *, gateway_port, deadline):
        qualifier = (qualify_secretary_listener if self._contract.role == "mmsecretary"
                     else qualify_meta_listener)
        return await qualifier(held, gateway_port=gateway_port, deadline=deadline)

    def _read_token(self) -> bytes:
        from ops.executive_os.remote_worker_gateway_service import (
            LINUX_HOST_OBSERVATION_ROOT, _secure_regular_file, _trusted_observation_ancestors,
        )
        _trusted_observation_ancestors(LINUX_HOST_OBSERVATION_ROOT)
        raw = _secure_regular_file(
            self.binding.credential_path, root=LINUX_HOST_OBSERVATION_ROOT,
            expected_owner_uid=0, expected_group_gid=self._group,
            max_bytes=257, read_bytes=True,
        )
        token = raw[:-1] if raw.endswith(b"\n") else raw
        if _TOKEN.fullmatch(token) is None:
            raise ValueError("Secretary forwarding credential is invalid")
        return token

    def _require_current_token(self) -> None:
        if not hmac.compare_digest(self._token, self._read_token()):
            raise ValueError("Secretary forwarding credential changed")

    async def request(self, request: dict, *, deadline: float) -> dict:
        """Send once; every failure after possible transmission stays uncertain."""
        writer = None
        write_started = False
        loop = asyncio.get_running_loop()
        deadline = min(deadline, loop.time() + self._timeout)
        try:
            if type(request) is not dict:
                raise ValueError("Secretary request is invalid")
            # The outer mTLS grammar supplies all other closed-form validation.
            target = request.get("target") if request.get("operation") == "submit" else request
            if (type(target) is not dict or target.get("session_id") != self.binding.session_id
                    or request.get("operation") not in ("observe", "submit", "read_original")):
                raise ValueError("Secretary request retargets the selected session")
            native_request = dict(request)
            if request["operation"] == "read_original":
                # The wire omits an unknown admission ID; the native owner
                # requires its explicit null form for original-ID lookup.
                native_request["admission_id"] = request.get("admission_id")
            body = json.dumps({
                "schema": self._contract.request_schema,
                "implementation_sha": self.binding.implementation_sha,
                "request": native_request,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                allow_nan=False).encode("ascii")
            if len(body) > _MAX_REQUEST:
                raise ValueError("Secretary request exceeds its bound")
            self._require_current_token()
            host = ROLE_PROXY_HOST[self._contract.role]
            if loop.time() >= deadline:
                raise TimeoutError()
            with _HeldRoleQualification(self.binding.implementation_sha) as held:
                async with asyncio.timeout_at(deadline):
                    original = await self._qualify_listener(
                        held, gateway_port=self.binding.gateway_port, deadline=deadline,
                    )
                    reader, writer = await asyncio.open_connection(
                        host, self.binding.gateway_port, family=socket.AF_INET,
                        local_addr=(host, 0), limit=_MAX_HEADERS,
                    )
                    peer = writer.get_extra_info("peername")
                    local = writer.get_extra_info("sockname")
                    channel = writer.get_extra_info("socket")
                    if (peer != (host, self.binding.gateway_port)
                            or type(local) is not tuple or len(local) != 2 or local[0] != host
                            or channel is None or channel.family != socket.AF_INET):
                        raise ValueError("Secretary connection identity changed")
                    current = await self._qualify_listener(
                        held, gateway_port=self.binding.gateway_port, deadline=deadline,
                    )
                    if current != original:
                        raise ValueError("Secretary listener changed")
                    self._require_current_token()
                    header = (
                        f"POST {self._contract.path} HTTP/1.1\r\n"
                        f"Host: {host}:{self.binding.gateway_port}\r\n"
                        "Content-Type: application/json\r\n"
                        f"Content-Length: {len(body)}\r\n"
                        "Connection: close\r\n"
                    ).encode("ascii") + b"Authorization: Bearer " + self._token + b"\r\n\r\n"
                    if loop.time() >= deadline:
                        raise TimeoutError()
                    write_started = True
                    writer.write(header + body)
                    await writer.drain()
                    headers = await reader.readuntil(b"\r\n\r\n")
                    if len(headers) > _MAX_HEADERS:
                        raise ValueError("Secretary response headers exceed their bound")
                    lines = headers[:-4].split(b"\r\n")
                    if not lines or lines[0].split(b" ", 2)[:2] != [b"HTTP/1.1", b"200"]:
                        raise ValueError("Secretary response is unavailable")
                    values = {}
                    for line in lines[1:]:
                        if b":" not in line or line[:1] in (b" ", b"\t"):
                            raise ValueError("Secretary response headers are invalid")
                        key, value = line.split(b":", 1)
                        key = key.lower()
                        if not key or key in values or any(c < 33 or c > 126 for c in key):
                            raise ValueError("Secretary response headers are invalid")
                        values[key] = value.strip()
                    length = values.get(b"content-length", b"")
                    if (b"transfer-encoding" in values or re.fullmatch(rb"[0-9]{1,7}", length) is None
                            or not 0 < int(length) <= _MAX_RESPONSE
                            or values.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
                               != b"application/json"):
                        raise ValueError("Secretary response framing is invalid")
                    raw = await reader.readexactly(int(length))
                    document = closed_json(raw, limit=_MAX_RESPONSE)
                    if (type(document) is not dict
                            or set(document) != {"schema", "implementation_sha", "result"}
                            or document["schema"] != self._contract.response_schema
                            or document["implementation_sha"] != self.binding.implementation_sha
                            or type(document["result"]) is not dict):
                        raise ValueError("Secretary response source is invalid")
                    # Canonicalize after decoding so JSON escapes cannot conceal the token.
                    normalized = json.dumps(document, sort_keys=True, ensure_ascii=True,
                                            allow_nan=False).encode("ascii")
                    if self._token in normalized:
                        raise ValueError("Secretary response contains protected material")
                    current = await self._qualify_listener(
                        held, gateway_port=self.binding.gateway_port, deadline=deadline,
                    )
                    if current != original:
                        raise ValueError("Secretary listener changed")
                    self._require_current_token()
                    if loop.time() >= deadline:
                        raise TimeoutError()
                    return document["result"]
        except (asyncio.CancelledError, Exception):
            effect = TransportEffect.EFFECT_UNKNOWN if write_started else TransportEffect.NO_EFFECT
            code = ("secretary_forwarding_unavailable" if self._contract.role == "mmsecretary"
                    else "meta_forwarding_unavailable")
            raise TransportError(code, effect) from None
        finally:
            if writer is not None:
                with suppress(Exception):
                    writer.close()
                    transport = getattr(writer, "transport", None)
                    if transport is not None:
                        transport.abort()

class HermesSecretaryForwarder(_HermesConversationForwarder):
    def __init__(self, binding: HermesSecretaryConversationBinding, *,
                 expected_group_gid: int, timeout_seconds: float) -> None:
        super().__init__(binding, role="mmsecretary",
                         expected_group_gid=expected_group_gid, timeout_seconds=timeout_seconds)


class HermesMetaForwarder(_HermesConversationForwarder):
    def __init__(self, binding: HermesMetaConversationBinding, *,
                 expected_group_gid: int, timeout_seconds: float) -> None:
        super().__init__(binding, role="mmmeta",
                         expected_group_gid=expected_group_gid, timeout_seconds=timeout_seconds)
