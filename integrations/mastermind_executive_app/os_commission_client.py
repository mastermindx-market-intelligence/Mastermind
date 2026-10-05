"""One bounded call to the incumbent Studio commission owner.

This client neither acquires a workspace nor runs Git. The original OS bearer
is forwarded only to an installation-bound loopback endpoint; there is no
redirect, environment proxy, retry, alternate host, credential store or submit.
The owner independently verifies that bearer and its separate publication grant.
A lost or malformed result conveys no permission to publish or submit again.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

SCHEMA = "mastermind.os.commission_preparation.v1"
ROUTE = "/os-internal/commission/prepare"
MAX_REQUEST_BYTES = 65_536
MAX_RESPONSE_BYTES = 4096
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_OPERATION = re.compile(r"mmos-launch-[0-9a-f]{40}")
_CODES = frozenset((
    "publication_refused", "publication_conflict", "publication_unavailable",
    "authentication_required", "publication_unknown",
))


@dataclass(frozen=True)
class PreparationResult:
    status: str
    operation_key: str
    head_sha: str | None = None
    content_sha256: str | None = None
    code: str | None = None


def _parse_result(raw: bytes, operation_key: str, principal_scope: str) -> PreparationResult:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate response member")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("operation_key") != operation_key:
        raise ValueError("unqualified preparation result")
    if value.get("status") == "prepared":
        if (set(value) != {"schema", "status", "operation_key", "principal_scope", "head_sha", "content_sha256"}
                or value["principal_scope"] != principal_scope
                or not isinstance(value["head_sha"], str) or not _HEX40.fullmatch(value["head_sha"])
                or not isinstance(value["content_sha256"], str) or not _HEX64.fullmatch(value["content_sha256"])):
            raise ValueError("unqualified preparation result")
        return PreparationResult("prepared", operation_key, value["head_sha"], value["content_sha256"])
    if (set(value) != {"schema", "status", "operation_key", "code"}
            or value.get("status") not in ("refused", "effect_unknown", "conflict")
            or value.get("code") not in _CODES):
        raise ValueError("unqualified preparation refusal")
    return PreparationResult(value["status"], operation_key, code=value["code"])


class StudioCommissionClient:
    """Installation chooses one loopback port, never a request-supplied URL."""

    def __init__(self, *, port: int, timeout_seconds: float = 90.0) -> None:
        if type(port) is not int or not 1024 <= port <= 65535 or port in (8443, 45017):
            raise ValueError("commission owner port refused")
        if type(timeout_seconds) not in (int, float) or not 1 <= timeout_seconds <= 120:
            raise ValueError("commission owner timeout refused")
        self._url = f"http://127.0.0.1:{port}{ROUTE}"
        self._timeout = timeout_seconds

    async def prepare(
        self, *, arguments: dict[str, Any], bearer: str, principal_scope: str,
    ) -> PreparationResult:
        # This is a second assertion after the public five-tool schema gate.
        operation = arguments.get("operation_key")
        if (not isinstance(operation, str) or not _OPERATION.fullmatch(operation)
                or not isinstance(principal_scope, str) or not _HEX64.fullmatch(principal_scope)
                or not isinstance(bearer, str) or not bearer or len(bearer) > 16_384
                or re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", bearer) is None):
            raise ValueError("commission preparation input refused")
        body = json.dumps({"arguments": arguments}, allow_nan=False, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("commission preparation body refused")
        # No injectable destination/transport or caller-selected environment.
        # Tests patch HTTPX at its existing I/O boundary.
        try:
            async with asyncio.timeout(self._timeout), httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=self._timeout,
            ) as client:
                async with client.stream(
                    "POST", self._url, content=body,
                    headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
                ) as response:
                    if response.status_code != 200:
                        return PreparationResult("effect_unknown", operation, code="publication_unknown")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise ValueError("commission result too large")
            return _parse_result(bytes(raw), operation, principal_scope)
        except Exception:
            return PreparationResult("effect_unknown", operation, code="publication_unknown")
