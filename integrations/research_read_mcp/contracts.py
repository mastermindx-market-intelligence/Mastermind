"""Closed wire contracts for the read-only Research Read MCP tools.

Import-inert: no SDK, authenticator, store, filesystem, or network.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

import jsonschema
import jsonschema.validators
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from . import CONTRACT

TOOL_NAMES = (
    "research_status",
    "research_search",
    "research_fetch",
    "research_find_evidence",
)
TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
MAX_ARGUMENT_BYTES = 4096
MAX_RESULT_BYTES = 131072
RATE_LIMIT_CALLS = 120
RATE_LIMIT_WINDOW_SECONDS = 600
ERROR_CODES = (
    "AUTHENTICATION_REQUIRED",
    "INSUFFICIENT_SCOPE",
    "NOT_ENTITLED",
    "INVALID_REQUEST",
    "TOOL_NOT_AVAILABLE",
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
)
ERROR_MESSAGES = {
    "AUTHENTICATION_REQUIRED": "authentication is required",
    "INSUFFICIENT_SCOPE": "the token lacks the required scope",
    "NOT_ENTITLED": "this caller is not entitled to research reads",
    "INVALID_REQUEST": "the request is invalid",
    "TOOL_NOT_AVAILABLE": "this tool is not available",
    "NOT_FOUND": "the requested report was not found",
    "SOURCE_UNAVAILABLE": "the research source is unavailable",
    "RATE_LIMITED": "the request rate limit was exceeded",
    "INTERNAL_ERROR": "an internal error occurred",
}
FORBIDDEN_FIELD_NAMES = frozenset({
    "bucket",
    "key",
    "prefix",
    "root",
    "path",
    "store",
    "url",
    "principal",
    "tier",
    "policy",
    "grant",
    "credential",
    "visibility",
})
REPORT_ID_PATTERN = "^[a-z0-9][a-z0-9-]{0,120}$"
DATE_PATTERN = "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
# F10 engine/research_vault/read_port.py:31-49 and :75-83, fulltext.py:20, read_service.py:33-37 @ Macro bd6f27c8163 (#8610). Pasted values; this module does not import Macro.
SOURCE_STATES = (
    "SOURCE_FRESH",
    "PRODUCER_STALE",
    "CATALOG_UNAVAILABLE",
    "NO_REPORTS",
    "LATEST_REPORT_INVALID",
    "FUTURE_REPORT_CLOCK",
)
COVERAGE_STATES = (
    "FULL_TEXT",
    "PREFIX_ONLY_LEGACY",
    "NO_TEXT_LAYER",
    "EXTRACTION_UNAVAILABLE",
    "SEGMENT_INDEX_PENDING",
    "PARTIAL_CORPUS",
    "SOURCE_REVISION_CHANGED",
)
TEXT_LAYER_STATES = (
    "full",
    "thin",
    "none",
    "unavailable",
)
RIO_STATES = (
    "CURRENT",
    "MISSING",
    "STALE",
    "INVALID",
    "NOT_REQUESTED",
)
EVIDENCE_OUTCOMES = (
    "FOUND",
    "NOT_FOUND",
    "UNAVAILABLE",
    "PARTIAL",
)
DEGRADATION_CODES = (
    "PRODUCER_STALE",
    "PARTIAL_CORPUS",
    "FULL_TEXT_PARTIAL",
    "RIO_PARTIAL",
    "METADATA_PARTIAL",
    "SCAN_NO_TEXT",
    "INDEX_REBUILD_PENDING",
)
SEGMENT_MAX_BYTES = 4000
FETCH_MAX_SEGMENTS = 4
FETCH_DEFAULT_SEGMENTS = 2
FETCH_MAX_TEXT_BYTES = 24000

_NO_CONTROL_PATTERN = r"^[^\u0000-\u001f\u007f-\u009f]*$"
_SHA256_PATTERN = "^[0-9a-f]{64}$"
_COMMIT_PATTERN = "^[0-9a-f]{40}$"
_TOOL_DESCRIPTIONS = {
    "research_status": (
        "Report the research vault's freshness, coverage and catalog state. "
        "Degraded states are reported, never hidden."
    ),
    "research_search": (
        "Search the private institutional research catalog by text with optional "
        "institution and date filters. Returns report metadata only, never body text."
    ),
    "research_fetch": (
        "Read up to max_segments consecutive segments of a report's extracted text, "
        "starting at segment_start; use next_segment_start to continue."
    ),
    "research_find_evidence": (
        "Find literal passages in research reports that bear on a claim. "
        "Each passage is an exact substring of the extracted text with UTF-8 byte offsets and hashes."
    ),
}


def _fullmatch_pattern(validator: Any, patrn: str, instance: Any, schema: Any):
    if isinstance(instance, str) and re.fullmatch(patrn, instance) is None:
        yield ValidationError("pattern mismatch")


def _strict_int(checker: Any, x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


_Validator = jsonschema.validators.extend(
    Draft202012Validator,
    validators={"pattern": _fullmatch_pattern},
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", _strict_int),
)


def _object(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }
    if title is not None:
        schema["title"] = title
    return schema


def _bounded_text(min_length: int, max_length: int) -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": min_length,
        "maxLength": max_length,
        "pattern": _NO_CONTROL_PATTERN,
    }


_COUNT = {"type": "integer", "minimum": 0}
_REPORT_ID = {"type": "string", "pattern": REPORT_ID_PATTERN}
_SHA256 = {"type": "string", "pattern": _SHA256_PATTERN}
_SIDE = {
    "type": "string",
    "minLength": 0,
    "maxLength": 40,
    "pattern": _NO_CONTROL_PATTERN,
}
_PUBLISHED_AT = {
    "type": "string",
    "minLength": 0,
    "maxLength": 64,
    "pattern": _NO_CONTROL_PATTERN,
}
_SIDE_OR_NULL = {
    "type": ["string", "null"],
    "minLength": 0,
    "maxLength": 40,
    "pattern": _NO_CONTROL_PATTERN,
}
_PUBLISHED_AT_OR_NULL = {
    "type": ["string", "null"],
    "minLength": 0,
    "maxLength": 64,
    "pattern": _NO_CONTROL_PATTERN,
}
_RATIO = {"type": "number", "minimum": 0, "maximum": 1}
_PAGE = {"type": ["integer", "null"], "minimum": 1}


def _input_schemas() -> dict[str, dict[str, Any]]:
    return {
        "research_status": _object({}, required=[]),
        "research_search": _object(
            {
                "query": _bounded_text(1, 200),
                "institution": _bounded_text(0, 80),
                "from": {"type": "string", "pattern": DATE_PATTERN},
                "to": {"type": "string", "pattern": DATE_PATTERN},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            required=["query"],
        ),
        "research_fetch": _object(
            {
                "report_id": _REPORT_ID,
                "segment_start": {"type": "integer", "minimum": 0},
                "max_segments": {"type": "integer", "minimum": 1, "maximum": FETCH_MAX_SEGMENTS},
            },
            required=["report_id"],
        ),
        "research_find_evidence": _object(
            {
                "claim": _bounded_text(1, 300),
                "report_ids": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 10,
                    "uniqueItems": True,
                    "items": _REPORT_ID,
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            required=["claim"],
        ),
    }


def _candidate_schema() -> dict[str, Any]:
    return _object({
        "report_id": _REPORT_ID,
        "title": {"type": "string", "minLength": 0, "maxLength": 300},
        "institution": {"type": "string", "minLength": 0, "maxLength": 80},
        "side": _SIDE_OR_NULL,
        "published_at": _PUBLISHED_AT_OR_NULL,
        "rank": {"type": "integer", "minimum": 1, "maximum": 20},
    })


def _report_schema() -> dict[str, Any]:
    return _object({
        "report_id": _REPORT_ID,
        "title": {"type": "string", "minLength": 0, "maxLength": 300},
        "institution": {"type": "string", "minLength": 0, "maxLength": 80},
        "side": _SIDE,
        "published_at": _PUBLISHED_AT,
    })


def _segment_schema() -> dict[str, Any]:
    return _object({
        "segment_index": _COUNT,
        "page_start": _PAGE,
        "page_end": _PAGE,
        "byte_start": _COUNT,
        "byte_end": {"type": "integer", "minimum": 1},
        "text": {"type": "string", "minLength": 1, "maxLength": SEGMENT_MAX_BYTES},
    })


def _passage_schema() -> dict[str, Any]:
    return _object(
        {
            "report_id": _REPORT_ID,
            "passage_text": {"type": "string", "minLength": 1, "maxLength": 1200},
            "byte_start": _COUNT,
            "byte_end": {"type": "integer", "minimum": 1},
            "text_sha256": _SHA256,
            "canonical_text_sha256": _SHA256,
            "segment_index": _COUNT,
        },
        title="research.evidence_passage.v1",
    )


def _output_schemas() -> dict[str, dict[str, Any]]:
    source_state = {"type": "string", "enum": list(SOURCE_STATES)}
    rio_state = {"type": "string", "enum": list(RIO_STATES)}
    contract = {"const": CONTRACT}
    return {
        "research_status": _object({
            "contract": contract,
            "source_state": source_state,
            "producer": _object({
                "last_success_at": {"type": ["string", "null"], "maxLength": 64},
                "age_seconds": {"type": ["number", "null"], "minimum": 0},
                "stale": {"type": "boolean"},
            }),
            "catalog": _object({
                "report_count": _COUNT,
            }),
            "coverage": _object({
                "full_text_ratio": _RATIO,
                "rio_ratio": _RATIO,
            }),
            "degradation": {
                "type": "array",
                "uniqueItems": True,
                "maxItems": len(DEGRADATION_CODES),
                "items": {"type": "string", "enum": list(DEGRADATION_CODES)},
            },
            "generation": _object({
                "server_contract": {"const": CONTRACT},
                "read_port_contract": {"type": "string", "minLength": 1, "maxLength": 120},
                "mastermind_commit": {"type": "string", "pattern": _COMMIT_PATTERN},
            }),
        }),
        "research_search": _object({
            "contract": contract,
            "source_state": source_state,
            "candidates": {
                "type": "array",
                "maxItems": 20,
                "items": _candidate_schema(),
            },
            "coverage_state": {"type": ["string", "null"], "enum": [*COVERAGE_STATES, None]},
        }),
        "research_fetch": _object({
            "contract": contract,
            "source_state": source_state,
            "report": _report_schema(),
            "provenance": _object({
                "source_class": {"const": "mastermind_private_institutional"},
                "license_class": {"const": "internal_licensed"},
            }),
            "text_layer_state": {
                "type": ["string", "null"],
                "enum": [*TEXT_LAYER_STATES, None],
            },
            "coverage_state": {"type": "string", "enum": list(COVERAGE_STATES)},
            "segment_count_total": _COUNT,
            "segments": {
                "type": "array",
                "maxItems": FETCH_MAX_SEGMENTS,
                "items": _segment_schema(),
            },
            "next_segment_start": {"type": ["integer", "null"], "minimum": 0},
            "rio_state": rio_state,
        }),
        "research_find_evidence": _object(
            {
                "contract": contract,
                "source_state": source_state,
                "outcome": {"type": "string", "enum": list(EVIDENCE_OUTCOMES)},
                "passages": {
                    "type": "array",
                    "maxItems": 10,
                    "items": _passage_schema(),
                },
                "rio_state": rio_state,
            },
            title="research_vault.evidence_result.v1",
        ),
    }


INPUT_SCHEMAS = _input_schemas()
OUTPUT_SCHEMAS = _output_schemas()
ERROR_SCHEMA = _object({
    "code": {"type": "string", "enum": list(ERROR_CODES)},
    "message": {"type": "string", "enum": [ERROR_MESSAGES[code] for code in ERROR_CODES]},
})


class ContractViolation(Exception):
    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown error code")
        self.code = code
        super().__init__(code)


def validate_arguments(tool_name: object, arguments: object) -> dict[str, Any]:
    if not isinstance(tool_name, str) or tool_name not in TOOL_NAMES:
        raise ContractViolation("TOOL_NOT_AVAILABLE") from None
    if not isinstance(arguments, dict):
        raise ContractViolation("INVALID_REQUEST") from None
    try:
        encoded = json.dumps(
            arguments,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ContractViolation("INVALID_REQUEST") from None
    if len(encoded) > MAX_ARGUMENT_BYTES:
        raise ContractViolation("INVALID_REQUEST") from None
    if not _Validator(INPUT_SCHEMAS[tool_name]).is_valid(arguments):
        raise ContractViolation("INVALID_REQUEST") from None
    normalized = copy.deepcopy(arguments)
    if tool_name == "research_search":
        normalized.setdefault("limit", 8)
    elif tool_name == "research_fetch":
        normalized.setdefault("segment_start", 0)
        normalized.setdefault("max_segments", FETCH_DEFAULT_SEGMENTS)
    elif tool_name == "research_find_evidence":
        normalized.setdefault("limit", 5)
    return normalized


def result_wire_bytes(result: object) -> int:
    compact = json.dumps(result, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    rendered = json.dumps(result, indent=2, allow_nan=False).encode("utf-8")
    return len(compact) + len(rendered)


def _fail_output() -> None:
    raise ContractViolation("INTERNAL_ERROR") from None


def _check_output_invariants(tool_name: str, result: dict[str, Any], quote_limit_chars: object) -> None:
    """Check invariants JSON Schema cannot express.

    Passage length identity is checked here. The canonical-bytes identity
    passage_text.encode("utf-8") == canonical_utf8[byte_start:byte_end]
    cannot be checked here, because this module never holds the canonical text.
    That identity is the producer's (F10/L4) obligation.
    """
    if tool_name == "research_find_evidence":
        passages = result["passages"]
        for passage in passages:
            raw = passage["passage_text"].encode("utf-8")
            start = passage["byte_start"]
            end = passage["byte_end"]
            if end <= start or end - start != len(raw):
                _fail_output()
            if passage["text_sha256"] != hashlib.sha256(raw).hexdigest():
                _fail_output()
            if isinstance(quote_limit_chars, int) and not isinstance(quote_limit_chars, bool):
                if len(passage["passage_text"]) > min(1200, quote_limit_chars):
                    _fail_output()
        outcome = result["outcome"]
        if outcome in ("FOUND", "PARTIAL") and len(passages) < 1:
            _fail_output()
        if outcome in ("NOT_FOUND", "UNAVAILABLE") and len(passages) != 0:
            _fail_output()
    elif tool_name == "research_fetch":
        segments = result["segments"]
        total = result["segment_count_total"]
        nxt = result["next_segment_start"]
        segment_max_bytes = SEGMENT_MAX_BYTES
        fetch_max_text_bytes = FETCH_MAX_TEXT_BYTES
        if result["coverage_state"] != "FULL_TEXT":
            if segments or total != 0:
                _fail_output()
        encoded_lengths: list[int] = []
        for segment in segments:
            raw = segment["text"].encode("utf-8")
            start = segment["byte_start"]
            end = segment["byte_end"]
            if end <= start or end - start != len(raw):
                _fail_output()
            if len(raw) > segment_max_bytes:
                _fail_output()
            if segment["segment_index"] >= total:
                _fail_output()
            page_start = segment["page_start"]
            page_end = segment["page_end"]
            both_null = page_start is None and page_end is None
            both_int = (
                isinstance(page_start, int)
                and not isinstance(page_start, bool)
                and isinstance(page_end, int)
                and not isinstance(page_end, bool)
            )
            if not both_null and not (both_int and 1 <= page_start <= page_end):
                _fail_output()
            encoded_lengths.append(len(raw))
        for prev, following in zip(segments, segments[1:]):
            if following["segment_index"] != prev["segment_index"] + 1:
                _fail_output()
            if following["byte_start"] != prev["byte_end"]:
                _fail_output()
        if sum(encoded_lengths) > fetch_max_text_bytes:
            _fail_output()
        if not segments:
            if nxt is not None:
                _fail_output()
        else:
            following_index = segments[-1]["segment_index"] + 1
            expected = following_index if following_index < total else None
            if nxt != expected:
                _fail_output()
    elif tool_name == "research_search":
        seen: set[str] = set()
        for index, candidate in enumerate(result["candidates"]):
            if candidate["rank"] != index + 1:
                _fail_output()
            report_id = candidate["report_id"]
            if report_id in seen:
                _fail_output()
            seen.add(report_id)


def validate_output(tool_name: object, result: object, *, quote_limit_chars: object = None) -> None:
    if not isinstance(tool_name, str) or tool_name not in OUTPUT_SCHEMAS:
        _fail_output()
    if not isinstance(result, dict):
        _fail_output()
    if not _Validator(OUTPUT_SCHEMAS[tool_name]).is_valid(result):
        _fail_output()
    try:
        wire_bytes = result_wire_bytes(result)
    except (TypeError, ValueError):
        _fail_output()
    if wire_bytes > MAX_RESULT_BYTES:
        _fail_output()
    try:
        _check_output_invariants(tool_name, result, quote_limit_chars)
    except ContractViolation:
        raise
    except Exception:
        _fail_output()


def error_payload(code: str) -> dict[str, str]:
    if code not in ERROR_MESSAGES:
        raise ValueError("unknown error code")
    return {"code": code, "message": ERROR_MESSAGES[code]}


def tool_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for name in TOOL_NAMES:
        definitions.append({
            "name": name,
            "description": _TOOL_DESCRIPTIONS[name],
            "inputSchema": copy.deepcopy(INPUT_SCHEMAS[name]),
            "outputSchema": copy.deepcopy(OUTPUT_SCHEMAS[name]),
            "annotations": copy.deepcopy(TOOL_ANNOTATIONS),
        })
    return definitions


__all__ = [
    "validate_arguments",
    "validate_output",
    "result_wire_bytes",
    "error_payload",
    "tool_definitions",
    "ContractViolation",
    "TOOL_NAMES",
    "TOOL_ANNOTATIONS",
    "MAX_ARGUMENT_BYTES",
    "MAX_RESULT_BYTES",
    "RATE_LIMIT_CALLS",
    "RATE_LIMIT_WINDOW_SECONDS",
    "ERROR_CODES",
    "ERROR_MESSAGES",
    "ERROR_SCHEMA",
    "FORBIDDEN_FIELD_NAMES",
    "INPUT_SCHEMAS",
    "OUTPUT_SCHEMAS",
    "REPORT_ID_PATTERN",
    "DATE_PATTERN",
    "SOURCE_STATES",
    "COVERAGE_STATES",
    "TEXT_LAYER_STATES",
    "RIO_STATES",
    "EVIDENCE_OUTCOMES",
    "DEGRADATION_CODES",
    "SEGMENT_MAX_BYTES",
    "FETCH_MAX_SEGMENTS",
    "FETCH_DEFAULT_SEGMENTS",
    "FETCH_MAX_TEXT_BYTES",
]
