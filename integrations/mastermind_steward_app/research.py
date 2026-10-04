"""Deterministic Company Knowledge / Deep Research adapter for Steward.

This module adds no owner, crawler, index, cache, corpus, lifecycle, retry
plane, or persistence. It can only ask the protected Secretary contract the
same six questions the existing Steward app already exposes. Search is a
bounded deterministic catalogue over those returned facts. Fetch reconstructs
the selected document from current Steward evidence on every call.

Citation URLs intentionally remain empty until an authenticated, user-openable
same-app evidence surface is production-proven. An MCP bearer-only endpoint is
not treated as a browser-openable citation surface.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from integrations.mastermind_secretary_mcp.schemas import (
    ERROR_CODES as SECRETARY_ERROR_CODES,
    RESULT_SCHEMA as SECRETARY_RESULT_SCHEMA,
    SERVER_VERSION as SECRETARY_SERVER_VERSION,
    canonical_json as secretary_canonical_json,
    validate_result_data,
)
from integrations.mastermind_secretary_mcp.server import SecretaryGroundingContractServer

RESEARCH_GENERATION = 1
RESEARCH_SERVER_VERSION = "3.0.0"
SEARCH_TOOL = "search"
FETCH_TOOL = "fetch"
RESEARCH_TOOLS = (SEARCH_TOOL, FETCH_TOOL)
CITATION_URL_SURFACE_MISSING = "CITATION_URL_SURFACE_MISSING"
MAX_QUERY_CHARS = 512
MAX_QUERY_BYTES = 2048
MAX_QUERY_TOKENS = 32
MAX_SEARCH_RESULTS = 20
MAX_FETCH_TEXT_BYTES = 48 * 1024
MAX_RESULT_BYTES = 64 * 1024
_DOCUMENT_PREFIX = "steward:research:v1:"
_DOCUMENT_ID_RE = re.compile(r"\Asteward:research:v1:[0-9a-f]{64}\Z")
_WORD_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)
_BIDI_CONTROL = frozenset(
    {
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
)
_GENERIC_DIMENSION_TERMS = frozenset(
    {
        "attention",
        "blocker",
        "blockers",
        "capability",
        "capabilities",
        "company",
        "current",
        "evidence",
        "freshness",
        "mastermind",
        "missing",
        "responsibility",
        "responsibilities",
        "runtime",
        "source",
        "state",
        "status",
        "surface",
        "surfaces",
    }
)
_ATTENTION_TERMS = frozenset(
    {"attention", "decision", "decisions", "request", "requests", "urgent"}
)

SEARCH_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": MAX_QUERY_CHARS,
        }
    },
    "required": ["query"],
}
SEARCH_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "maxItems": MAX_SEARCH_RESULTS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "pattern": r"^steward:research:v1:[0-9a-f]{64}$"},
                    "title": {"type": "string", "minLength": 1, "maxLength": 256},
                    "url": {"type": "string", "maxLength": 2048},
                },
                "required": ["id", "title", "url"],
            },
        }
    },
    "required": ["results"],
}
FETCH_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {
            "type": "string",
            "pattern": r"^steward:research:v1:[0-9a-f]{64}$",
        }
    },
    "required": ["id"],
}
FETCH_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^steward:research:v1:[0-9a-f]{64}$"},
        "title": {"type": "string", "minLength": 1, "maxLength": 256},
        "text": {"type": "string", "minLength": 1, "maxLength": MAX_FETCH_TEXT_BYTES},
        "url": {"type": "string", "maxLength": 2048},
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "citation_status": {"const": CITATION_URL_SURFACE_MISSING},
                "document_kind": {
                    "type": "string",
                    "enum": ["attention", "responsibility"],
                },
                "research_generation": {"const": RESEARCH_GENERATION},
                "secretary_server_version": {"const": SECRETARY_SERVER_VERSION},
            },
            "required": [
                "citation_status",
                "document_kind",
                "research_generation",
                "secretary_server_version",
            ],
        },
    },
    "required": ["id", "title", "text", "url", "metadata"],
}

_TOOL_ANNOTATIONS = {
    "title": "Search Mastermind Steward",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


@dataclasses.dataclass(frozen=True)
class ResearchToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    annotations: dict[str, Any]


RESEARCH_TOOL_SPECS = (
    ResearchToolSpec(
        SEARCH_TOOL,
        (
            "Search current bounded Mastermind Steward company evidence. "
            "This reads only the existing protected Steward grounding surface; "
            "it does not search GitHub, hosts, Slack, Linear, files, or the web."
        ),
        SEARCH_INPUT_SCHEMA,
        SEARCH_OUTPUT_SCHEMA,
        _TOOL_ANNOTATIONS,
    ),
    ResearchToolSpec(
        FETCH_TOOL,
        (
            "Fetch one current bounded Mastermind Steward evidence document by "
            "the exact stable id returned from search. Missing source facts remain "
            "unknown/degraded and are never inferred."
        ),
        FETCH_INPUT_SCHEMA,
        FETCH_OUTPUT_SCHEMA,
        {**_TOOL_ANNOTATIONS, "title": "Fetch Mastermind Steward evidence"},
    ),
)


class ResearchError(RuntimeError):
    """One fixed, payload-free Steward research refusal."""

    CODES = frozenset(
        {
            "DOCUMENT_NOT_FOUND",
            "INTERNAL_ERROR",
            "INVALID_REQUEST",
            "RESPONSE_REFUSED",
            "STEWARD_UNAVAILABLE",
        }
    )

    def __init__(self, code: str) -> None:
        safe = code if code in self.CODES else "INTERNAL_ERROR"
        super().__init__(safe)
        self.code = safe


@dataclasses.dataclass(frozen=True)
class _Document:
    id: str
    kind: str
    title: str
    subject_ref: str | None
    index_text: str


def _research_id(kind: str, identity: str) -> str:
    digest = hashlib.sha256(
        b"mastermind-steward-research-v1\x00"
        + kind.encode("ascii")
        + b"\x00"
        + identity.encode("utf-8")
    ).hexdigest()
    return _DOCUMENT_PREFIX + digest


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ResearchError("RESPONSE_REFUSED") from None


def _bounded_result(value: dict[str, Any]) -> dict[str, Any]:
    if len(_canonical_bytes(value)) > MAX_RESULT_BYTES:
        raise ResearchError("RESPONSE_REFUSED")
    return value


def _validate_query(arguments: Any) -> tuple[str, tuple[str, ...]]:
    if not isinstance(arguments, Mapping):
        raise ResearchError("INVALID_REQUEST")
    try:
        raw = dict(arguments)
    except Exception:
        raise ResearchError("INVALID_REQUEST") from None
    if set(raw) != {"query"}:
        raise ResearchError("INVALID_REQUEST")
    query = raw["query"]
    if not isinstance(query, str) or query != query.strip() or not query:
        raise ResearchError("INVALID_REQUEST")
    if len(query) > MAX_QUERY_CHARS:
        raise ResearchError("INVALID_REQUEST")
    try:
        encoded = query.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ResearchError("INVALID_REQUEST") from None
    if len(encoded) > MAX_QUERY_BYTES:
        raise ResearchError("INVALID_REQUEST")
    for char in query:
        category = unicodedata.category(char)
        if category in {"Cc", "Cs"} or char in _BIDI_CONTROL:
            raise ResearchError("INVALID_REQUEST")
    normalized = unicodedata.normalize("NFC", query)
    tokens = tuple(sorted(set(_WORD_RE.findall(normalized.casefold()))))
    if not tokens or len(tokens) > MAX_QUERY_TOKENS:
        raise ResearchError("INVALID_REQUEST")
    return normalized, tokens


def _validate_fetch(arguments: Any) -> str:
    if not isinstance(arguments, Mapping):
        raise ResearchError("INVALID_REQUEST")
    try:
        raw = dict(arguments)
    except Exception:
        raise ResearchError("INVALID_REQUEST") from None
    if set(raw) != {"id"}:
        raise ResearchError("INVALID_REQUEST")
    document_id = raw["id"]
    if not isinstance(document_id, str) or _DOCUMENT_ID_RE.fullmatch(document_id) is None:
        raise ResearchError("INVALID_REQUEST")
    return document_id


def _validated_envelope(
    payload: Any,
    *,
    tool_name: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ResearchError("RESPONSE_REFUSED")
    try:
        row = dict(payload)
    except Exception:
        raise ResearchError("RESPONSE_REFUSED") from None
    if set(row) != {"schema", "tool", "ok", "server_version", "data", "error"}:
        raise ResearchError("RESPONSE_REFUSED")
    if (
        row["schema"] != SECRETARY_RESULT_SCHEMA
        or row["server_version"] != SECRETARY_SERVER_VERSION
        or row["tool"] != tool_name
        or type(row["ok"]) is not bool
    ):
        raise ResearchError("RESPONSE_REFUSED")
    if row["ok"]:
        if row["error"] is not None:
            raise ResearchError("RESPONSE_REFUSED")
        try:
            row["data"] = validate_result_data(row["data"])
        except Exception:
            raise ResearchError("RESPONSE_REFUSED") from None
    else:
        if row["data"] is not None or not isinstance(row["error"], Mapping):
            raise ResearchError("RESPONSE_REFUSED")
        error = dict(row["error"])
        if (
            set(error) != {"code", "message"}
            or error.get("code") not in SECRETARY_ERROR_CODES
            or error.get("message") != error.get("code")
        ):
            raise ResearchError("RESPONSE_REFUSED")
    try:
        secretary_canonical_json(row)
    except Exception:
        raise ResearchError("RESPONSE_REFUSED") from None
    return row


async def _call_contract(
    contract: SecretaryGroundingContractServer,
    tool_name: str,
    arguments: dict[str, str],
) -> dict[str, Any]:
    try:
        payload = await contract.call_tool(tool_name, arguments)
    except Exception:
        raise ResearchError("STEWARD_UNAVAILABLE") from None
    return _validated_envelope(payload, tool_name=tool_name)


def _facts_by_subject(data: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    subjects = data.get("subjects")
    if not isinstance(subjects, list):
        raise ResearchError("RESPONSE_REFUSED")
    for subject in subjects:
        if not isinstance(subject, Mapping):
            raise ResearchError("RESPONSE_REFUSED")
        subject_ref = subject.get("subject_ref")
        facts = subject.get("facts")
        if not isinstance(subject_ref, str) or not isinstance(facts, list):
            raise ResearchError("RESPONSE_REFUSED")
        result[subject_ref] = [dict(item) for item in facts]
    return result


def _fact_values(facts: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for fact in facts:
        predicate = fact.get("predicate")
        if isinstance(predicate, str) and predicate not in values:
            values[predicate] = fact.get("value")
    return values


def _catalog(listing: dict[str, Any]) -> list[_Document]:
    if listing["ok"] is not True:
        code = str(dict(listing["error"])["code"])
        if code == "STEWARD_UNAVAILABLE":
            raise ResearchError("STEWARD_UNAVAILABLE")
        raise ResearchError("RESPONSE_REFUSED")
    data = listing["data"]
    if not isinstance(data, Mapping):
        raise ResearchError("RESPONSE_REFUSED")
    documents: list[_Document] = []
    for subject_ref, facts in sorted(_facts_by_subject(data).items()):
        values = _fact_values(facts)
        title_value = values.get("responsibility.title")
        identity_value = values.get("responsibility.identity")
        if isinstance(title_value, str) and title_value:
            title = title_value
        elif isinstance(identity_value, str) and identity_value:
            prefix = "Mastermind responsibility — "
            available = 256 - len(prefix)
            title = prefix + identity_value[:available]
        else:
            title = "Mastermind responsibility — source limited"
        if not title or len(title) > 256:
            raise ResearchError("RESPONSE_REFUSED")
        searchable = " ".join(
            str(value)
            for value in (
                title,
                identity_value,
                values.get("responsibility.state"),
                values.get("responsibility.next_action"),
            )
            if isinstance(value, (str, int, bool))
        ).casefold()
        documents.append(
            _Document(
                id=_research_id("responsibility", subject_ref),
                kind="responsibility",
                title=title,
                subject_ref=subject_ref,
                index_text=searchable,
            )
        )
    documents.append(
        _Document(
            id=_research_id("attention", "global"),
            kind="attention",
            title="Mastermind executive attention",
            subject_ref=None,
            index_text=(
                "mastermind company executive attention decisions requests "
                "current state evidence freshness"
            ),
        )
    )
    return documents


def _score(document: _Document, tokens: tuple[str, ...]) -> int:
    score = 0
    generic = False
    for token in tokens:
        if token in document.index_text:
            score += 4
        if token in _GENERIC_DIMENSION_TERMS:
            generic = True
            if document.kind == "responsibility":
                score += 1
        if token in _ATTENTION_TERMS and document.kind == "attention":
            score += 8
    if generic and document.kind == "attention":
        score += 1
    return score


def _section(
    *,
    name: str,
    envelope: dict[str, Any],
    subject_ref: str | None = None,
) -> dict[str, Any]:
    if envelope["ok"] is not True:
        return {
            "name": name,
            "state": "ERROR",
            "reason_codes": [str(dict(envelope["error"])["code"])],
            "facts": [],
        }
    data = envelope["data"]
    if not isinstance(data, Mapping):
        raise ResearchError("RESPONSE_REFUSED")
    reasons = data.get("reason_codes")
    state = data.get("state")
    if not isinstance(state, str) or not isinstance(reasons, list):
        raise ResearchError("RESPONSE_REFUSED")
    subjects = _facts_by_subject(data)
    facts: list[dict[str, Any]] = []
    if subject_ref is None:
        for ref in sorted(subjects):
            for fact in subjects[ref]:
                facts.append({"subject_ref": ref, **fact})
    else:
        facts = [
            {"subject_ref": subject_ref, **fact}
            for fact in subjects.get(subject_ref, [])
        ]
    return {
        "name": name,
        "state": state,
        "reason_codes": list(reasons),
        "facts": facts,
    }


def _render_text(
    *,
    document: _Document,
    sections: list[dict[str, Any]],
) -> str:
    lines = [
        f"# {document.title}",
        "",
        "source: Mastermind Steward",
        f"document_kind: {document.kind}",
        f"citation_status: {CITATION_URL_SURFACE_MISSING}",
        (
            "truth_boundary: Missing or degraded Steward facts remain missing or "
            "degraded; this research adapter does not infer repairs."
        ),
    ]
    for section in sections:
        lines.extend(
            [
                "",
                f"## {section['name']}",
                f"state: {section['state']}",
                "reason_codes: "
                + (
                    ", ".join(str(code) for code in section["reason_codes"])
                    if section["reason_codes"]
                    else "none"
                ),
            ]
        )
        facts = section["facts"]
        if not facts:
            lines.append("facts: none")
            continue
        current_subject_ref: str | None = None
        for fact in facts:
            subject_ref = fact.get("subject_ref")
            if not isinstance(subject_ref, str) or not subject_ref:
                raise ResearchError("RESPONSE_REFUSED")
            if subject_ref != current_subject_ref:
                lines.append(f"subject_ref: {subject_ref}")
                current_subject_ref = subject_ref
            value = json.dumps(
                fact.get("value"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            lines.append(
                f"- {fact['predicate']} = {value} "
                f"[freshness={fact['freshness']}]"
            )
            sources = fact.get("sources")
            if not isinstance(sources, list):
                raise ResearchError("RESPONSE_REFUSED")
            for source in sources:
                if not isinstance(source, Mapping):
                    raise ResearchError("RESPONSE_REFUSED")
                observed = source.get("observed_at") or "unknown"
                lines.append(
                    "  source: "
                    f"{source.get('owner')} / {source.get('source_ref')} / "
                    f"observed_at={observed}"
                )
    text = "\n".join(lines)
    try:
        encoded = text.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ResearchError("RESPONSE_REFUSED") from None
    if not encoded or len(encoded) > MAX_FETCH_TEXT_BYTES:
        raise ResearchError("RESPONSE_REFUSED")
    return text


class StewardResearchGateway:
    """Research projection over the protected six-tool Secretary contract only."""

    def __init__(self, contract: SecretaryGroundingContractServer) -> None:
        if not isinstance(contract, SecretaryGroundingContractServer):
            raise TypeError("contract must be SecretaryGroundingContractServer")
        self._contract = contract

    async def search(self, arguments: Any) -> dict[str, Any]:
        _, tokens = _validate_query(arguments)
        listing = await _call_contract(
            self._contract, "list_responsibilities", {}
        )
        ranked = [
            (_score(document, tokens), document)
            for document in _catalog(listing)
        ]
        ranked = [row for row in ranked if row[0] > 0]
        ranked.sort(key=lambda row: (-row[0], row[1].title.casefold(), row[1].id))
        results = [
            {"id": document.id, "title": document.title, "url": ""}
            for _, document in ranked[:MAX_SEARCH_RESULTS]
        ]
        return _bounded_result({"results": results})

    async def fetch(self, arguments: Any) -> dict[str, Any]:
        document_id = _validate_fetch(arguments)
        listing = await _call_contract(
            self._contract, "list_responsibilities", {}
        )
        catalog = {document.id: document for document in _catalog(listing)}
        document = catalog.get(document_id)
        if document is None:
            raise ResearchError("DOCUMENT_NOT_FOUND")

        if document.kind == "attention":
            attention = await _call_contract(self._contract, "get_attention", {})
            sections = [_section(name="attention", envelope=attention)]
        else:
            assert document.subject_ref is not None
            subject = document.subject_ref
            responsibility = await _call_contract(
                self._contract,
                "get_responsibility",
                {"responsibility_ref": subject},
            )
            blocker = await _call_contract(
                self._contract,
                "explain_blocker",
                {"responsibility_ref": subject},
            )
            runtime = await _call_contract(
                self._contract,
                "get_current_runtime",
                {"responsibility_ref": subject},
            )
            surface = await _call_contract(
                self._contract,
                "resolve_surface",
                {"responsibility_ref": subject},
            )
            attention = await _call_contract(self._contract, "get_attention", {})
            sections = [
                _section(
                    name="responsibility",
                    envelope=responsibility,
                    subject_ref=subject,
                ),
                _section(
                    name="attention",
                    envelope=attention,
                    subject_ref=subject,
                ),
                _section(
                    name="blocker",
                    envelope=blocker,
                    subject_ref=subject,
                ),
                _section(
                    name="runtime",
                    envelope=runtime,
                    subject_ref=subject,
                ),
                _section(
                    name="surface",
                    envelope=surface,
                    subject_ref=subject,
                ),
            ]

        payload = {
            "id": document.id,
            "title": document.title,
            "text": _render_text(document=document, sections=sections),
            "url": "",
            "metadata": {
                "citation_status": CITATION_URL_SURFACE_MISSING,
                "document_kind": document.kind,
                "research_generation": RESEARCH_GENERATION,
                "secretary_server_version": SECRETARY_SERVER_VERSION,
            },
        }
        return _bounded_result(payload)

    async def call(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == SEARCH_TOOL:
            return await self.search(arguments)
        if name == FETCH_TOOL:
            return await self.fetch(arguments)
        raise ResearchError("INVALID_REQUEST")


def research_tool_schema_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": copy.deepcopy(spec.input_schema),
            "output_schema": copy.deepcopy(spec.output_schema),
            "annotations": copy.deepcopy(spec.annotations),
        }
        for spec in RESEARCH_TOOL_SPECS
    ]


def research_tool_schema_digest() -> str:
    return hashlib.sha256(_canonical_bytes(research_tool_schema_snapshot())).hexdigest()


def research_schema_snapshot() -> dict[str, Any]:
    return {
        "research_generation": RESEARCH_GENERATION,
        "research_server_version": RESEARCH_SERVER_VERSION,
        "secretary_result_schema": SECRETARY_RESULT_SCHEMA,
        "secretary_server_version": SECRETARY_SERVER_VERSION,
        "citation_status": CITATION_URL_SURFACE_MISSING,
        "limits": {
            "query_chars": MAX_QUERY_CHARS,
            "query_bytes": MAX_QUERY_BYTES,
            "query_tokens": MAX_QUERY_TOKENS,
            "search_results": MAX_SEARCH_RESULTS,
            "fetch_text_bytes": MAX_FETCH_TEXT_BYTES,
            "result_bytes": MAX_RESULT_BYTES,
        },
        "tools": research_tool_schema_snapshot(),
    }


def research_schema_snapshot_sha256() -> str:
    return hashlib.sha256(_canonical_bytes(research_schema_snapshot())).hexdigest()


RESEARCH_SCHEMA_SNAPSHOT_SHA256 = "89602f8d6baa76f644b5c41aa931531698a0626bb85e1eb36a593569e8982c7a"
RESEARCH_TOOL_SCHEMA_DIGEST = "8eec65289bf72818fe8362cb02587b6cc78c6eb526a1f602edbd22ffff030918"


def assert_research_contract_integrity() -> None:
    if (
        research_schema_snapshot_sha256() != RESEARCH_SCHEMA_SNAPSHOT_SHA256
        or research_tool_schema_digest() != RESEARCH_TOOL_SCHEMA_DIGEST
    ):
        raise ResearchError("INTERNAL_ERROR")


__all__ = [
    "CITATION_URL_SURFACE_MISSING",
    "FETCH_INPUT_SCHEMA",
    "FETCH_OUTPUT_SCHEMA",
    "FETCH_TOOL",
    "MAX_FETCH_TEXT_BYTES",
    "MAX_QUERY_BYTES",
    "MAX_QUERY_CHARS",
    "MAX_QUERY_TOKENS",
    "MAX_RESULT_BYTES",
    "MAX_SEARCH_RESULTS",
    "RESEARCH_GENERATION",
    "RESEARCH_SCHEMA_SNAPSHOT_SHA256",
    "RESEARCH_SERVER_VERSION",
    "RESEARCH_TOOL_SCHEMA_DIGEST",
    "RESEARCH_TOOL_SPECS",
    "RESEARCH_TOOLS",
    "ResearchError",
    "SEARCH_INPUT_SCHEMA",
    "SEARCH_OUTPUT_SCHEMA",
    "SEARCH_TOOL",
    "StewardResearchGateway",
    "assert_research_contract_integrity",
    "research_schema_snapshot",
    "research_schema_snapshot_sha256",
    "research_tool_schema_digest",
    "research_tool_schema_snapshot",
]
