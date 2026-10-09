"""Read-only Dot facade over real owner callbacks. Never executes a command.

The authenticated Executive/Business host supplies a fixed profile, exact typed
principal checker and already-authorized canonical read ports. The model does not
supply a host, identity, root, shell, source connector or output provenance.
This layer does not create an auth server, state database, queue, source reader,
background process, scheduler, retry loop, or MCP network listener.
"""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from .contracts import (
    DotRefusal, MAX_OUTPUT_BYTES, MAX_RESULT_LINES, PROFILES, REF_PATTERN,
    RESULT_SCHEMA, SERVER_VERSION, TOOL_SPECS, TOOLS, input_schema,
    schema_digest, validate_tool_arguments,
)

_SECRETS = (re.compile(p, re.I) for p in (
    r"github_pat_", r"\bgh[pousr]_[A-Za-z0-9]", r"\bxox[baprs]-",
    r"\bsk-[A-Za-z0-9]", r"\bBearer\s+\S+", r"-----BEGIN .*PRIVATE KEY-----",
    r"(?i)password\s*[:=]", r"(?i)authorization\s*[:=]",
))
_SECRET_PATTERNS = tuple(_SECRETS)
_FORBIDDEN_KEYS = frozenset(("password", "authorization", "token", "credential", "secret", "private_key", "access_token", "refresh_token", "environment", "env", "raw_log", "shell", "command", "argv", "home_directory"))
_STATES = frozenset(("PROVEN_LIVE", "BUILT_NOT_PROVEN", "PARTIAL", "DARK_OR_DISCONNECTED", "BROKEN", "SPEC_ONLY", "NOT_BUILT", "REJECTED_BY_DESIGN"))


@dataclasses.dataclass(frozen=True)
class PrincipalBinding:
    """Created by incumbent OAuth/JWT+organizational authorizer, never model input."""
    subject_ref: str
    client_ref: str
    resource_ref: str
    policy_generation: str
    scopes: tuple[str, ...]
    authorized: bool


@dataclasses.dataclass(frozen=True)
class OwnerEvidence:
    """A fresh owner-native observation; source refs never arrive from tool args."""
    owner: str
    observed_at: str
    source_refs: tuple[str, ...]
    capability_state: str
    data: Any
    issues: tuple[str, ...] = ()


def _valid_utc(raw: str) -> datetime:
    if type(raw) is not str or len(raw) > 32 or not raw.endswith("Z"):
        raise DotRefusal("invalid_owner_evidence")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DotRefusal("invalid_owner_evidence") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise DotRefusal("invalid_owner_evidence")
    return parsed


def _check_data(value: Any, *, depth: int = 0) -> Any:
    """Normalize JSON-only owner evidence and withhold secret-bearing trees."""
    if depth > 8:
        raise DotRefusal("unsafe_owner_evidence")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        import math
        if not math.isfinite(value): raise DotRefusal("unsafe_owner_evidence")
        return value
    if type(value) is str:
        if value.startswith(("/Users/", "/private/", "/Library/", "/Volumes/", "/home/", "/etc/")):
            raise DotRefusal("unsafe_owner_evidence")
        if len(value) > 12000 or any(p.search(value) for p in _SECRET_PATTERNS):
            raise DotRefusal("unsafe_owner_evidence")
        return value
    if type(value) in (list, tuple):
        if len(value) > 96: raise DotRefusal("output_too_large")
        return [_check_data(item, depth=depth+1) for item in value]
    if type(value) is dict:
        if len(value) > 96: raise DotRefusal("output_too_large")
        out = {}
        for k,v in value.items():
            if type(k) is not str or len(k)>128 or k.lower() in _FORBIDDEN_KEYS or any(p.search(k) for p in _SECRET_PATTERNS):
                raise DotRefusal("unsafe_owner_evidence")
            out[k] = _check_data(v, depth=depth+1)
        return out
    raise DotRefusal("unsafe_owner_evidence")


def _normalize_evidence(spec: Any, evidence: OwnerEvidence, now: datetime) -> dict[str, Any]:
    if type(evidence) is not OwnerEvidence or evidence.owner != spec.owner:
        raise DotRefusal("invalid_owner_evidence")
    observation = _valid_utc(evidence.observed_at)
    if now.tzinfo is None or now.utcoffset().total_seconds() != 0:
        raise DotRefusal("invalid_owner_evidence")
    if observation.timestamp() > now.timestamp() + 60:
        raise DotRefusal("invalid_owner_evidence")
    if now.timestamp() - observation.timestamp() > 600:
        raise DotRefusal("stale_owner_evidence")
    if evidence.capability_state not in _STATES:
        raise DotRefusal("invalid_owner_evidence")
    if type(evidence.source_refs) is not tuple or not (1 <= len(evidence.source_refs) <= 12):
        raise DotRefusal("invalid_owner_evidence")
    if any(type(ref) is not str or REF_PATTERN.fullmatch(ref) is None for ref in evidence.source_refs):
        raise DotRefusal("invalid_owner_evidence")
    if type(evidence.issues) is not tuple or len(evidence.issues) > 16:
        raise DotRefusal("invalid_owner_evidence")
    if any(type(v) is not str or REF_PATTERN.fullmatch(v) is None for v in evidence.issues):
        raise DotRefusal("invalid_owner_evidence")
    data = _check_data(evidence.data)
    return {"owner": evidence.owner, "observed_at": evidence.observed_at,
            "source_refs": list(evidence.source_refs), "capability_state": evidence.capability_state,
            "issues": list(evidence.issues), "data": data}


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class DotReadGateway:
    """One immutable host-selected read profile over exact already-authorized ports."""

    def __init__(self, *, profile: str, ports: Mapping[str, Callable[..., Any]],
                 reauthorize: Callable[[Any, str], Any], now: Callable[[], datetime] | None = None):
        if profile not in PROFILES: raise ValueError("unknown fixed Dot read profile")
        if type(ports) is not dict or not ports:
            raise ValueError("non-empty owner port mapping required")
        allowed = {t.name for t in TOOL_SPECS if t.profile == profile}
        if set(ports) - allowed or any(not callable(v) for v in ports.values()):
            raise ValueError("owner ports cannot cross a profile or be non-callable")
        if not callable(reauthorize): raise ValueError("current principal checker required")
        self.profile = profile
        self._ports = dict(ports)
        self._reauthorize = reauthorize
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.schema_digest = schema_digest(profile, tuple(self._ports))

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in TOOL_SPECS if spec.name in self._ports and spec.profile == self.profile)

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "inputSchema": input_schema(t),
                 "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                 "idempotentHint": True, "openWorldHint": False}}
                for t in TOOL_SPECS if t.name in self._ports and t.profile == self.profile]

    async def _admitted(self, principal: Any, scope: str) -> PrincipalBinding:
        try:
            grant = await _await(self._reauthorize(principal, scope))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise DotRefusal("authority_refused") from exc
        if type(grant) is not PrincipalBinding or not grant.authorized or scope not in grant.scopes:
            raise DotRefusal("authority_refused")
        for ident in (grant.subject_ref, grant.client_ref, grant.resource_ref, grant.policy_generation):
            if type(ident) is not str or REF_PATTERN.fullmatch(ident) is None:
                raise DotRefusal("authority_refused")
        if type(grant.scopes) is not tuple or len(grant.scopes) > 12 or any(
            type(s) is not str or REF_PATTERN.fullmatch(s) is None for s in grant.scopes
        ):
            raise DotRefusal("authority_refused")
        return grant

    async def call(self, tool: str, arguments: Any, *, principal: Any) -> dict[str, Any]:
        """One read. No retries. Reauthorize and compare full binding after await."""
        if tool not in self._ports:
            return self._error(tool, "not_found")
        spec = TOOLS[tool]
        try:
            args = validate_tool_arguments(tool, arguments)
            binding = await self._admitted(principal, spec.scope)
            evidence = await _await(self._ports[tool](args))
            after = await self._admitted(principal, spec.scope)
            if after != binding:
                raise DotRefusal("authority_refused")
            normalized = _normalize_evidence(spec, evidence, self._now())
            doc = {"schema": RESULT_SCHEMA, "server_version": SERVER_VERSION,
                   "profile": self.profile, "tool": tool, "ok": True,
                   "schema_digest": self.schema_digest, "data": normalized, "error": None}
            rendered = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False, allow_nan=False)
            if len(rendered.encode("utf-8")) > MAX_OUTPUT_BYTES or rendered.count("\n") >= MAX_RESULT_LINES:
                raise DotRefusal("output_too_large")
            return doc
        except DotRefusal as exc:
            return self._error(tool, exc.code)
        except asyncio.CancelledError:
            raise
        except Exception:
            return self._error(tool, "backend_unavailable")

    def _error(self, tool: str, code: str) -> dict[str, Any]:
        return {"schema": RESULT_SCHEMA, "server_version": SERVER_VERSION,
                "profile": self.profile, "tool": tool, "ok": False,
                "schema_digest": self.schema_digest, "data": None,
                "error": {"code": code, "message": "Dot read unavailable or refused; no modifying operation occurred."}}
