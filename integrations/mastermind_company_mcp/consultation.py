"""Frozen four-tool Company MCP consultation facet (hermetic producer slice)."""
from __future__ import annotations

import asyncio
import copy
import datetime as dt
import dataclasses
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any

from common.agent_dialogue_consultation_contract import (
    CONSULTATION_SCHEMA,
    GROK_CONSULTATION_SCHEMA,
)
from integrations.slack_agent_dialogue.company_consultation_peer_resolver import (
    CompanyConsultationPeerResolver,
    ConsultationPeerRefused,
)

COMPANY_CONSULTATION_SCHEMA = "mastermind.company_consultation_mcp.v1"
COMPANY_CONSULT_DISPATCH_SCHEMA = "mastermind.company_consult_dispatch.v1"
COMPANY_CONSULTATION_CAPABILITY = COMPANY_CONSULTATION_SCHEMA
COMPANY_CONSULTATION_SERVER_NAME = "mastermind-company-consultation"
COMPANY_CONSULTATION_SERVER_IDENTITY = "mastermind-company-consultation-mcp"
COMPANY_CONSULTATION_SERVER_VERSION = "1.0.0"
COMPANY_CONSULTATION_RESULT_SCHEMA = "mastermind.company_consultation_mcp_result.v1"
COMPANY_CONSULTATION_MAX_REQUEST_BYTES = 32768
COMPANY_CONSULTATION_MAX_RESPONSE_BYTES = 65536
COMPANY_CONSULTATION_ERROR_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "UNAVAILABLE",
        "AMBIGUOUS",
        "BINDING_UNAVAILABLE",
        "CAPABILITY_NOT_ATTESTED",
        "ACCESS_REFUSED",
        "CONFLICT",
        "EFFECT_UNKNOWN",
        "INTERNAL_ERROR",
    }
)
_PEER_REF_RE = re.compile(r"\Apeer-[0-9a-f]{32}\Z")
_CONSULTATION_REF_RE = re.compile(r"\Aconsult-[0-9a-f]{32}\Z")
_UTC_SECOND_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_COMPANY_CONSULT_DISPATCH_BUDGET = MappingProxyType(
    {
        "max_answers": 1,
        "max_evidence_reads": 4,
        "max_forward_hops": 0,
        "max_payload_bytes": 32768,
    }
)
_SECRET_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|bearer\s+[A-Za-z0-9._~-]{16,})"
)
_ARTIFACT_REPOSITORY_RE = re.compile(r"\A[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_ARTIFACT_PATH_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9_./-]{1,254}\Z")
_EVIDENCE_RE = re.compile(
    r"\Ahttps://(?:github\.com|linear\.app)/[^\s?#]{1,470}\Z"
)
_FORBIDDEN_FIELDS = frozenset(
    {
        "provider", "account", "host", "session_id", "native_session_id", "channel",
        "channel_id", "thread", "thread_ts", "runtime_binding", "binding_id",
        "binding_generation", "job_id", "attempt_id", "worker_id", "operation_key",
        "session_ref", "work_ref", "commission_ref", "reply_to_message_key",
        "token", "secret", "credential", "password", "api_key", "action",
    }
)


class CompanyConsultationToolError(RuntimeError):
    def __init__(self, code: str) -> None:
        if code not in COMPANY_CONSULTATION_ERROR_CODES:
            raise ValueError("unknown Company consultation refusal code")
        self.code = code
        super().__init__(code)


@dataclasses.dataclass(frozen=True)
class CompanyConsultationToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_description: str
    read_only: bool

    @property
    def annotations(self) -> dict[str, Any]:
        return {
            "title": self.name,
            "readOnlyHint": self.read_only,
            "destructiveHint": False,
            "idempotentHint": self.read_only,
            "openWorldHint": False,
        }


def _object(properties: Mapping[str, Any], required: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


def _string(max_length: int, *, pattern: str | None = None) -> dict[str, Any]:
    result = {"type": "string", "minLength": 1, "maxLength": max_length}
    if pattern is not None:
        result["pattern"] = pattern
    return result


_EVIDENCE_REFS = {
    "type": "array",
    "maxItems": 4,
    "uniqueItems": True,
    "items": _string(500, pattern=r"^https://(?:github\.com|linear\.app)/"),
}
_ARTIFACT_REVISION = {
    "type": "object",
    "properties": {
        "repository": _string(200, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"),
        "path": _string(255, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_./-]+$"),
        "commit": _string(40, pattern=r"^[0-9a-f]{40}$"),
        "content_sha256": _string(64, pattern=r"^[0-9a-f]{64}$"),
    },
    "required": ["repository", "path", "commit", "content_sha256"],
    "additionalProperties": False,
}

COMPANY_CONSULTATION_TOOL_SPECS: tuple[CompanyConsultationToolSpec, ...] = (
    CompanyConsultationToolSpec(
        name="company.peers",
        description=(
            "List opaque peer references for the resolver-owned current program. "
            "No identity, provider, session, channel, or native handle can be supplied."
        ),
        input_schema=_object({}, ()),
        output_description="Opaque peer references and closed display facts only.",
        read_only=True,
    ),
    CompanyConsultationToolSpec(
        name="company.consult",
        description=(
            "Create one bounded same-program consultation for an opaque peer. "
            "This producer facet performs no provider I/O and confers no write authority."
        ),
        input_schema=_object(
            {
                "to": _string(128, pattern=r"^peer-[0-9a-f]{32}$"),
                "question": _string(16000),
                "evidence_refs": _EVIDENCE_REFS,
                "artifact_revisions": {
                    "type": "array", "minItems": 0, "maxItems": 8, "uniqueItems": True,
                    "items": _ARTIFACT_REVISION,
                },
            },
            ("to", "question", "evidence_refs", "artifact_revisions"),
        ),
        output_description="Gateway-minted consultation identity and frozen refusal policy.",
        read_only=False,
    ),
    CompanyConsultationToolSpec(
        name="company.reply",
        description=(
            "Append one correlated bounded answer or correction to a consultation. "
            "No second reply, forwarding, spawning, or lifecycle authority is granted."
        ),
        input_schema=_object(
            {
                "consultation_ref": _string(128, pattern=r"^consult-[0-9a-f]{32}$"),
                "answer": _string(16000),
                "supersedes_message_key": {"oneOf": [{"type": "null"}, _string(128)]},
                "evidence_refs": _EVIDENCE_REFS,
            },
            ("consultation_ref", "answer", "evidence_refs"),
        ),
        output_description="One correlated append receipt intent only.",
        read_only=False,
    ),
    CompanyConsultationToolSpec(
        name="company.consultation",
        description="Read one resolver-owned consultation packet and immutable revisions.",
        input_schema=_object(
            {"consultation_ref": _string(128, pattern=r"^consult-[0-9a-f]{32}$")},
            ("consultation_ref",),
        ),
        output_description="The named consultation packet with no transcript expansion.",
        read_only=True,
    ),
)


def canonical_company_consultation_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CompanyConsultationToolError("INVALID_REQUEST") from None


def _reject_semantics(arguments: Mapping[str, Any]) -> None:
    if set(arguments) & _FORBIDDEN_FIELDS:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    for value in arguments.values():
        if isinstance(value, Mapping):
            if set(value) & _FORBIDDEN_FIELDS:
                raise CompanyConsultationToolError("INVALID_REQUEST")
        elif isinstance(value, str) and _SECRET_RE.search(value):
            raise CompanyConsultationToolError("INVALID_REQUEST")
        elif isinstance(value, list):
            for nested in value:
                if (
                    isinstance(nested, Mapping)
                    and set(nested) & _FORBIDDEN_FIELDS
                ):
                    raise CompanyConsultationToolError("INVALID_REQUEST")
                if isinstance(nested, str) and _SECRET_RE.search(nested):
                    raise CompanyConsultationToolError("INVALID_REQUEST")


def validate_company_consultation_tool_arguments(
    tool_name: str, arguments: Any
) -> dict[str, Any]:
    specs = {spec.name: spec for spec in COMPANY_CONSULTATION_TOOL_SPECS}
    spec = specs.get(tool_name)
    if spec is None or not isinstance(arguments, Mapping):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    raw = dict(arguments)
    if len(canonical_company_consultation_json({"arguments": raw})) > COMPANY_CONSULTATION_MAX_REQUEST_BYTES:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    allowed = set(spec.input_schema["properties"])
    required = set(spec.input_schema["required"])
    if set(raw) != (set(raw) & allowed) or not required <= set(raw):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    _reject_semantics(raw)
    if tool_name == "company.peers":
        return {}
    if tool_name == "company.consult":
        if _PEER_REF_RE.fullmatch(raw["to"] if isinstance(raw.get("to"), str) else "") is None:
            raise CompanyConsultationToolError("INVALID_REQUEST")
        question = _validated_text(raw["question"])
        if len(question) > 16000:
            raise CompanyConsultationToolError("INVALID_REQUEST")
        evidence_refs = _validated_evidence_refs(raw["evidence_refs"])
        artifact_revisions = _validated_artifact_revisions(raw["artifact_revisions"])
        return {
            "to": raw["to"], "question": question,
            "evidence_refs": evidence_refs, "artifact_revisions": artifact_revisions,
        }
    if tool_name == "company.reply":
        consultation_ref = raw.get("consultation_ref")
        if (
            not isinstance(consultation_ref, str)
            or _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None
        ):
            raise CompanyConsultationToolError("INVALID_REQUEST")
        supersedes = raw.get("supersedes_message_key")
        if supersedes is not None and _MESSAGE_KEY_OK(supersedes) is False:
            raise CompanyConsultationToolError("INVALID_REQUEST")
        answer = _validated_text(raw["answer"])
        evidence_refs = _validated_evidence_refs(raw["evidence_refs"])
        return {
            "consultation_ref": consultation_ref, "answer": answer,
            "supersedes_message_key": supersedes,
            "evidence_refs": evidence_refs,
        }
    consultation_ref = raw.get("consultation_ref")
    if (
        not isinstance(consultation_ref, str)
        or _CONSULTATION_REF_RE.fullmatch(consultation_ref) is None
    ):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    return {"consultation_ref": consultation_ref}


def _MESSAGE_KEY_OK(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"asd-[a-z0-9][a-z0-9-]{7,95}", value) is not None


def _validated_text(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value.strip() != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or _SECRET_RE.search(value)
    ):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    return value


def _validated_evidence_refs(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 4:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    refs = []
    for item in value:
        if not isinstance(item, str) or _EVIDENCE_RE.fullmatch(item) is None:
            raise CompanyConsultationToolError("INVALID_REQUEST")
        refs.append(item)
    if len(refs) != len(set(refs)):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    return refs


def _validated_artifact_revisions(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 8:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    revisions = []
    for revision in value:
        if not isinstance(revision, Mapping) or set(revision) != {
            "repository", "path", "commit", "content_sha256"
        }:
            raise CompanyConsultationToolError("INVALID_REQUEST")
        normalized = {
            "repository": revision["repository"],
            "path": revision["path"],
            "commit": revision["commit"],
            "content_sha256": revision["content_sha256"],
        }
        if (
            not isinstance(normalized["repository"], str)
            or len(normalized["repository"]) > 200
            or _ARTIFACT_REPOSITORY_RE.fullmatch(normalized["repository"]) is None
            or _SECRET_RE.search(normalized["repository"]) is not None
            or not isinstance(normalized["path"], str)
            or _ARTIFACT_PATH_RE.fullmatch(normalized["path"]) is None
            # Immutable artifact identities must not be normalized after admission.
            or any(part in {"", ".", ".."} for part in normalized["path"].split("/"))
            or _SECRET_RE.search(normalized["path"]) is not None
            or not isinstance(normalized["commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", normalized["commit"]) is None
            or not isinstance(normalized["content_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", normalized["content_sha256"]) is None
        ):
            raise CompanyConsultationToolError("INVALID_REQUEST")
        revisions.append(normalized)
    fingerprints = [canonical_company_consultation_json(item) for item in revisions]
    if len(fingerprints) != len(set(fingerprints)):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    return revisions


def _validated_dispatch_peer(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"peer_ref", "display_name"}:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    peer_ref = value.get("peer_ref")
    display_name = value.get("display_name")
    if not isinstance(peer_ref, str) or _PEER_REF_RE.fullmatch(peer_ref) is None:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    if (
        not isinstance(display_name, str)
        or not display_name.strip()
        or display_name.strip() != display_name
        or len(display_name) > 128
        or any(ord(character) < 32 or ord(character) == 127 for character in display_name)
        or _SECRET_RE.search(display_name)
    ):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    return {"peer_ref": peer_ref, "display_name": display_name}


def _validated_dispatch_budget(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(_COMPANY_CONSULT_DISPATCH_BUDGET):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    for key, expected in _COMPANY_CONSULT_DISPATCH_BUDGET.items():
        if type(value.get(key)) is not int or value.get(key) != expected:
            raise CompanyConsultationToolError("INVALID_REQUEST")
    return dict(_COMPANY_CONSULT_DISPATCH_BUDGET)


def validate_company_consult_dispatch_request(value: Any) -> dict[str, Any]:
    """Validate the closed provider-free request consumed by a future dispatcher.

    ``issued_at`` records the exact trusted-owner observation time. This inert
    source wave validates representation only and grants no temporal admission.
    """
    required = {
        "schema",
        "operation",
        "consultation_schema",
        "peer",
        "semantic",
        "budget",
        "issued_at",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    if value.get("schema") != COMPANY_CONSULT_DISPATCH_SCHEMA:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    if value.get("operation") != "consult":
        raise CompanyConsultationToolError("INVALID_REQUEST")
    consultation_schema = value.get("consultation_schema")
    if (
        not isinstance(consultation_schema, str)
        or consultation_schema
        not in (CONSULTATION_SCHEMA, GROK_CONSULTATION_SCHEMA)
    ):
        raise CompanyConsultationToolError("INVALID_REQUEST")
    issued_at = value.get("issued_at")
    if not isinstance(issued_at, str) or _UTC_SECOND_RE.fullmatch(issued_at) is None:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    try:
        dt.datetime.strptime(issued_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise CompanyConsultationToolError("INVALID_REQUEST") from None
    request = {
        "schema": COMPANY_CONSULT_DISPATCH_SCHEMA,
        "operation": "consult",
        "consultation_schema": consultation_schema,
        "peer": _validated_dispatch_peer(value.get("peer")),
        "semantic": copy.deepcopy(
            validate_company_consultation_tool_arguments(
                "company.consult", value.get("semantic")
            )
        ),
        "budget": _validated_dispatch_budget(value.get("budget")),
        "issued_at": issued_at,
    }
    if request["semantic"]["to"] != request["peer"]["peer_ref"]:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    if len(canonical_company_consultation_json(request)) > COMPANY_CONSULTATION_MAX_REQUEST_BYTES:
        raise CompanyConsultationToolError("INVALID_REQUEST")
    return request


def build_company_consult_dispatch_request(
    *,
    peer: Mapping[str, Any],
    consultation_schema: str,
    semantic: Mapping[str, Any],
    issued_at: str,
) -> dict[str, Any]:
    """Build one exact internal ``company.consult`` dispatcher request.

    The caller supplies the trusted observation time; this wave invents no
    expiry or temporal admission and has no live dispatcher consumer.
    """
    return validate_company_consult_dispatch_request(
        {
            "schema": COMPANY_CONSULT_DISPATCH_SCHEMA,
            "operation": "consult",
            "consultation_schema": consultation_schema,
            "peer": dict(peer),
            "semantic": dict(semantic),
            "budget": dict(_COMPANY_CONSULT_DISPATCH_BUDGET),
            "issued_at": issued_at,
        }
    )


def company_consultation_tool_schema_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "annotations": dict(spec.annotations),
            "input_schema": copy.deepcopy(spec.input_schema),
            "name": spec.name,
            "output_schema": None,
        }
        for spec in sorted(COMPANY_CONSULTATION_TOOL_SPECS, key=lambda item: item.name)
    ]


def company_consultation_tool_schema_digest() -> str:
    return hashlib.sha256(
        canonical_company_consultation_json(company_consultation_tool_schema_snapshot())
    ).hexdigest()


def company_consult_dispatch_schema_snapshot() -> dict[str, Any]:
    """Return a fresh closed schema for the internal ``company.consult`` request."""
    consult_input = next(
        spec.input_schema
        for spec in COMPANY_CONSULTATION_TOOL_SPECS
        if spec.name == "company.consult"
    )
    return _object(
        {
            "schema": {
                "type": "string",
                "const": COMPANY_CONSULT_DISPATCH_SCHEMA,
            },
            "operation": {"type": "string", "const": "consult"},
            "consultation_schema": {
                "type": "string",
                "enum": [CONSULTATION_SCHEMA, GROK_CONSULTATION_SCHEMA],
            },
            "peer": _object(
                {
                    "peer_ref": _string(
                        128, pattern=r"^peer-[0-9a-f]{32}$"
                    ),
                    "display_name": _string(128),
                },
                ("peer_ref", "display_name"),
            ),
            "semantic": copy.deepcopy(consult_input),
            "budget": _object(
                {
                    key: {"type": "integer", "const": value}
                    for key, value in _COMPANY_CONSULT_DISPATCH_BUDGET.items()
                },
                tuple(_COMPANY_CONSULT_DISPATCH_BUDGET),
            ),
            "issued_at": {
                "type": "string",
                "minLength": 20,
                "maxLength": 20,
                "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            },
        },
        (
            "schema",
            "operation",
            "consultation_schema",
            "peer",
            "semantic",
            "budget",
            "issued_at",
        ),
    )


def company_consult_dispatch_schema_digest() -> str:
    return hashlib.sha256(
        canonical_company_consultation_json(
            company_consult_dispatch_schema_snapshot()
        )
    ).hexdigest()


COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST = company_consultation_tool_schema_digest()
COMPANY_CONSULT_DISPATCH_SCHEMA_DIGEST = company_consult_dispatch_schema_digest()


def _capped_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if len(canonical_company_consultation_json(envelope)) <= COMPANY_CONSULTATION_MAX_RESPONSE_BYTES:
        return envelope
    return {
        "schema": COMPANY_CONSULTATION_RESULT_SCHEMA,
        "tool": envelope["tool"],
        "ok": False,
        "server_identity": COMPANY_CONSULTATION_SERVER_IDENTITY,
        "server_version": COMPANY_CONSULTATION_SERVER_VERSION,
        "data": None,
        "error": {"code": "INTERNAL_ERROR", "message": "INTERNAL_ERROR"},
    }


def _result(tool: str, data: Any) -> dict[str, Any]:
    return _capped_envelope(
        {
            "schema": COMPANY_CONSULTATION_RESULT_SCHEMA,
            "tool": tool,
            "ok": True,
            "server_identity": COMPANY_CONSULTATION_SERVER_IDENTITY,
            "server_version": COMPANY_CONSULTATION_SERVER_VERSION,
            "data": data,
            "error": None,
        }
    )


def _result_after_dispatch(tool: str, data: Any) -> dict[str, Any]:
    """Preserve effect uncertainty when an effectful dispatch result cannot fit."""
    envelope = {
        "schema": COMPANY_CONSULTATION_RESULT_SCHEMA,
        "tool": tool,
        "ok": True,
        "server_identity": COMPANY_CONSULTATION_SERVER_IDENTITY,
        "server_version": COMPANY_CONSULTATION_SERVER_VERSION,
        "data": data,
        "error": None,
    }
    if len(canonical_company_consultation_json(envelope)) <= COMPANY_CONSULTATION_MAX_RESPONSE_BYTES:
        return envelope
    if tool in {"company.consult", "company.reply"}:
        return _error(tool, "EFFECT_UNKNOWN")
    return _capped_envelope(envelope)


def _closed_ambiguous_error_data(data: Any) -> dict[str, list[dict[str, str]]]:
    empty: dict[str, list[dict[str, str]]] = {"peers": []}
    try:
        if (
            not isinstance(data, Mapping)
            or set(data) != {"peers"}
            or not isinstance(data.get("peers"), list)
        ):
            return empty
        peers = [_validated_dispatch_peer(peer) for peer in data["peers"]]
        peer_refs = [peer["peer_ref"] for peer in peers]
        if len(peer_refs) != len(set(peer_refs)):
            return empty
        return {"peers": peers}
    except Exception:
        return empty


def _error(tool: str, code: str, data: Any = None) -> dict[str, Any]:
    if code not in COMPANY_CONSULTATION_ERROR_CODES:
        code = "INTERNAL_ERROR"
    closed_data = (
        _closed_ambiguous_error_data(data) if code == "AMBIGUOUS" else None
    )
    envelope = {
        "schema": COMPANY_CONSULTATION_RESULT_SCHEMA,
        "tool": tool,
        "ok": False,
        "server_identity": COMPANY_CONSULTATION_SERVER_IDENTITY,
        "server_version": COMPANY_CONSULTATION_SERVER_VERSION,
        "data": closed_data,
        "error": {"code": code, "message": code},
    }
    if (
        code == "AMBIGUOUS"
        and len(canonical_company_consultation_json(envelope))
        > COMPANY_CONSULTATION_MAX_RESPONSE_BYTES
    ):
        envelope["data"] = {"peers": []}
    return _capped_envelope(envelope)


class CompanyConsultationGateway:
    """Translate four semantic tools onto one injected dispatch interface."""

    def __init__(
        self,
        *,
        peer_resolver: CompanyConsultationPeerResolver,
        dispatcher: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        observed_tool_schema_digest: str,
        utc_now: Callable[[], str],
        program_ref: str = "JOB-100/agent-fabric-end-to-end-fable-integration",
    ) -> None:
        self.peer_resolver = peer_resolver
        self.dispatcher = dispatcher
        self.observed_tool_schema_digest = observed_tool_schema_digest
        self.utc_now = utc_now
        self.program_ref = program_ref

    async def call(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if self.observed_tool_schema_digest != COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST:
            return _error(tool_name, "CAPABILITY_NOT_ATTESTED")
        try:
            normalized = validate_company_consultation_tool_arguments(tool_name, arguments)
        except CompanyConsultationToolError as exc:
            return _error(tool_name, exc.code)
        dispatch_invoked = False
        try:
            if tool_name == "company.peers":
                peers = [
                    peer.public_projection()
                    for peer in self.peer_resolver.peers
                    if peer.program_ref == self.program_ref
                ]
                if not peers:
                    raise ConsultationPeerRefused("UNAVAILABLE")
                return _result(tool_name, {"peers": peers})
            if tool_name == "company.consult":
                try:
                    peer = self.peer_resolver.resolve(
                        normalized["to"], program_ref=self.program_ref
                    )
                    consultation_schema = peer.consultation_schema
                    issued_at = self.utc_now()
                    request = build_company_consult_dispatch_request(
                        peer=peer.public_projection(),
                        consultation_schema=consultation_schema,
                        semantic=normalized,
                        issued_at=issued_at,
                    )
                except ConsultationPeerRefused:
                    raise
                except Exception:
                    return _error(tool_name, "INTERNAL_ERROR")
                dispatch_invoked = True
                response = await self.dispatcher(tool_name, request)
                return _result_after_dispatch(tool_name, self._service_data(response))
            request = {
                "schema": COMPANY_CONSULTATION_SCHEMA,
                "operation": "reply" if tool_name == "company.reply" else "read",
                "semantic": normalized,
            }
            dispatch_invoked = True
            response = await self.dispatcher(tool_name, request)
            return _result_after_dispatch(tool_name, self._service_data(response))
        except ConsultationPeerRefused as exc:
            if dispatch_invoked:
                return _error(tool_name, "EFFECT_UNKNOWN")
            return _error(tool_name, exc.code, data=exc.data)
        except asyncio.CancelledError:
            if dispatch_invoked:
                return _error(tool_name, "EFFECT_UNKNOWN")
            raise
        except Exception:
            return _error(
                tool_name,
                "EFFECT_UNKNOWN" if dispatch_invoked else "INTERNAL_ERROR",
            )

    @staticmethod
    def _service_data(response: Any) -> Any:
        if not isinstance(response, Mapping) or set(response) != {"ok", "result"} or response.get("ok") is not True:
            raise ValueError("invalid dispatcher response")
        return response["result"]


__all__ = [
    "COMPANY_CONSULTATION_CAPABILITY",
    "COMPANY_CONSULT_DISPATCH_SCHEMA",
    "COMPANY_CONSULT_DISPATCH_SCHEMA_DIGEST",
    "COMPANY_CONSULTATION_ERROR_CODES",
    "COMPANY_CONSULTATION_RESULT_SCHEMA",
    "COMPANY_CONSULTATION_SCHEMA",
    "COMPANY_CONSULTATION_SERVER_IDENTITY",
    "COMPANY_CONSULTATION_SERVER_NAME",
    "COMPANY_CONSULTATION_SERVER_VERSION",
    "COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST",
    "COMPANY_CONSULTATION_TOOL_SPECS",
    "CompanyConsultationGateway",
    "CompanyConsultationToolError",
    "CompanyConsultationToolSpec",
    "build_company_consult_dispatch_request",
    "company_consult_dispatch_schema_digest",
    "company_consult_dispatch_schema_snapshot",
    "validate_company_consult_dispatch_request",
    "validate_company_consultation_tool_arguments",
]
