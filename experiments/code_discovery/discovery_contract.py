"""Closed, model-facing request contract for the disposable Z0 experiment."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final


class DiscoveryRequestError(ValueError):
    """A caller attempted to leave the bounded discovery contract."""


_MAX_QUERY_BYTES: Final = 512
_MAX_REGEX_BYTES: Final = 256
_MAX_LIST_ITEMS: Final = 12
_MAX_LIMIT: Final = 100
_MAX_CONTEXT_LINES: Final = 8
_LOGICAL_ID_RE: Final = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_LANGUAGES: Final = frozenset(
    {
        "c",
        "cpp",
        "csharp",
        "css",
        "go",
        "html",
        "java",
        "javascript",
        "json",
        "markdown",
        "php",
        "python",
        "ruby",
        "rust",
        "shell",
        "sql",
        "tsx",
        "typescript",
        "yaml",
        "yml",
    }
)


DISCOVERY_TOOL_SCHEMAS: Final[tuple[dict[str, object], ...]] = (
    {
        "name": "search_code",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": _MAX_QUERY_BYTES},
                "repositories": {"type": "array", "maxItems": _MAX_LIST_ITEMS},
                "path_prefixes": {"type": "array", "maxItems": _MAX_LIST_ITEMS},
                "languages": {"type": "array", "maxItems": _MAX_LIST_ITEMS},
                "refs": {"type": "array", "maxItems": _MAX_LIST_ITEMS},
                "case_sensitive": {"type": "boolean"},
                "regex": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
                "context_lines": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": _MAX_CONTEXT_LINES,
                },
            },
        },
    },
    {
        "name": "list_repositories",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    },
    {
        "name": "index_status",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "repositories": {"type": "array", "maxItems": _MAX_LIST_ITEMS},
                "refs": {"type": "array", "maxItems": _MAX_LIST_ITEMS},
            },
        },
    },
)

_SCHEMAS_BY_TOOL: Final = {schema["name"]: schema for schema in DISCOVERY_TOOL_SCHEMAS}
_SEARCH_FIELDS: Final = frozenset(
    {
        "query",
        "repositories",
        "path_prefixes",
        "languages",
        "refs",
        "case_sensitive",
        "regex",
        "limit",
        "context_lines",
    }
)
_STATUS_FIELDS: Final = frozenset({"repositories", "refs"})


@dataclass(frozen=True)
class DiscoveryRequest:
    """A canonical, immutable request awaiting host-owned manifest resolution."""

    tool: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class RepositoryIndexStatus:
    """Observed health and exact source identity for one indexed repository/ref."""

    repository_id: str
    ref_label: str
    indexed_commit_sha: str | None
    source_tree_digest: str | None
    shard_namespace: str | None
    health: str
    coverage: str
    generated_at: datetime
    observed_at: datetime
    freshness_seconds: float | None


@dataclass(frozen=True)
class CodeMatch:
    """A bounded source match with its indexed repository/ref provenance."""

    repository_id: str
    ref_label: str
    indexed_commit_sha: str
    path: str
    line_start: int
    line_end: int
    preview: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    engine_score: float | None


@dataclass(frozen=True)
class SearchResult:
    """A complete discovery response whose absence semantics stay explicit."""

    matches: tuple[CodeMatch, ...]
    repository_statuses: tuple[RepositoryIndexStatus, ...]
    query_completed: bool
    truncated: bool
    negative_result_authority: str
    negative_result_reasons: tuple[str, ...]


def discovery_tool_schema_digest() -> str:
    """Return the exact SHA-256 of canonical ASCII JSON schema bytes."""

    encoded = json.dumps(
        DISCOVERY_TOOL_SCHEMAS,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def validate_discovery_request(
    tool: str, arguments: Mapping[str, object]
) -> DiscoveryRequest:
    """Validate a model request without resolving host-owned repository state.

    Repository and ref labels remain logical identifiers here.  The facade
    resolves them against the reviewed manifest before any search is issued.
    """

    if tool not in _SCHEMAS_BY_TOOL:
        raise DiscoveryRequestError(f"unknown discovery tool: {tool!r}")
    if not isinstance(arguments, Mapping):
        raise DiscoveryRequestError("discovery arguments must be an object")

    supplied = dict(arguments)
    if tool == "search_code":
        canonical = _validate_search(supplied)
    elif tool == "index_status":
        _reject_unknown(supplied, _STATUS_FIELDS)
        canonical = {
            "repositories": _logical_ids(supplied.get("repositories", ()), "repositories"),
            "refs": _logical_ids(supplied.get("refs", ()), "refs"),
        }
    else:
        _reject_unknown(supplied, frozenset())
        canonical = {}

    return DiscoveryRequest(tool=tool, arguments=MappingProxyType(canonical))


def _validate_search(supplied: dict[str, object]) -> dict[str, object]:
    _reject_unknown(supplied, _SEARCH_FIELDS)
    if "query" not in supplied:
        raise DiscoveryRequestError("search_code requires query")

    query = _bounded_text(supplied["query"], field="query", maximum=_MAX_QUERY_BYTES)
    regex = _strict_bool(supplied.get("regex", False), field="regex")
    if regex:
        if len(query.encode("utf-8")) > _MAX_REGEX_BYTES:
            raise DiscoveryRequestError("regex query exceeds byte limit")
        if "(?" in query:
            raise DiscoveryRequestError("regex contains unsupported construct")

    return {
        "query": query,
        "repositories": _logical_ids(supplied.get("repositories", ()), "repositories"),
        "path_prefixes": _path_prefixes(supplied.get("path_prefixes", ())),
        "languages": _languages(supplied.get("languages", ())),
        "refs": _logical_ids(supplied.get("refs", ()), "refs"),
        "case_sensitive": _strict_bool(
            supplied.get("case_sensitive", False), field="case_sensitive"
        ),
        "regex": regex,
        "limit": _bounded_int(
            supplied.get("limit", 20), field="limit", minimum=1, maximum=_MAX_LIMIT
        ),
        "context_lines": _bounded_int(
            supplied.get("context_lines", 0),
            field="context_lines",
            minimum=0,
            maximum=_MAX_CONTEXT_LINES,
        ),
    }


def _reject_unknown(supplied: Mapping[str, object], allowed: frozenset[str]) -> None:
    unknown = set(supplied) - allowed
    if unknown:
        raise DiscoveryRequestError(f"unknown discovery arguments: {sorted(unknown)}")


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise DiscoveryRequestError(f"{field} must be a string")
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > maximum:
        raise DiscoveryRequestError(f"{field} is outside byte bounds")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise DiscoveryRequestError(f"{field} contains a control character")
    return value


def _strict_bool(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise DiscoveryRequestError(f"{field} must be a boolean")
    return value


def _bounded_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DiscoveryRequestError(f"{field} is outside integer bounds")
    return value


def _text_list(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise DiscoveryRequestError(f"{field} must be a list")
    if len(value) > _MAX_LIST_ITEMS:
        raise DiscoveryRequestError(f"{field} has too many values")
    result: list[str] = []
    for item in value:
        result.append(_bounded_text(item, field=field, maximum=128))
    if len(set(result)) != len(result):
        raise DiscoveryRequestError(f"{field} contains duplicate values")
    return tuple(result)


def _logical_ids(value: object, field: str) -> tuple[str, ...]:
    labels = _text_list(value, field=field)
    if any(_LOGICAL_ID_RE.fullmatch(label) is None for label in labels):
        raise DiscoveryRequestError(f"{field} must contain logical identifiers")
    return labels


def _path_prefixes(value: object) -> tuple[str, ...]:
    prefixes = _text_list(value, field="path_prefixes")
    for prefix in prefixes:
        if prefix.startswith(("/", "\\\\")) or "\\" in prefix:
            raise DiscoveryRequestError("path_prefixes must be repository-relative")
        if any(segment in {"", ".", ".."} for segment in prefix.split("/")):
            raise DiscoveryRequestError("path_prefixes must not traverse")
    return prefixes


def _languages(value: object) -> tuple[str, ...]:
    languages = _text_list(value, field="languages")
    if any(language not in _LANGUAGES for language in languages):
        raise DiscoveryRequestError("languages must use the closed normalized set")
    return languages
