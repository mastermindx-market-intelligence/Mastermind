"""Bounded parser for the exact loopback Zoekt JSON search route."""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .processes import LoopbackEndpoint


_MAX_RESPONSE_BYTES: Final = 8 * 1024 * 1024
_MAX_PREVIEW_BYTES: Final = 4 * 1024
_MAX_CONTEXT_BYTES: Final = 2 * 1024
_TOP_LEVEL_KEYS: Final = frozenset({"result"})
_RESULT_KEYS: Final = frozenset(
    {"Last", "QueryStr", "Query", "Stats", "Duration", "FileMatches"}
)
_LAST_KEYS: Final = frozenset({"Query", "Num", "Ctx", "AutoFocus", "Debug"})
_STATS_KEYS: Final = frozenset(
    {
        "ContentBytesLoaded",
        "IndexBytesLoaded",
        "Crashes",
        "Duration",
        "FileCount",
        "ShardFilesConsidered",
        "FilesConsidered",
        "FilesLoaded",
        "FilesSkipped",
        "FilesSkippedDueToCancellation",
        "ShardsScanned",
        "ShardsSkipped",
        "ShardsSkippedFilter",
        "MatchCount",
        "NgramMatches",
        "NgramLookups",
        "Wait",
        "MatchTreeConstruction",
        "MatchTreeSearch",
        "RegexpsConsidered",
        "FlushReason",
    }
)
_FILE_MATCH_KEYS: Final = frozenset(
    {
        "FileName",
        "Repo",
        "ResultID",
        "Language",
        "DuplicateID",
        "Branches",
        "Matches",
        "URL",
    }
)
_MATCH_REQUIRED_KEYS: Final = frozenset({"URL", "FileName", "LineNum", "Fragments"})
_MATCH_OPTIONAL_KEYS: Final = frozenset({"Before", "After"})
_FRAGMENT_KEYS: Final = frozenset({"Pre", "Match", "Post"})


class ZoektClientError(RuntimeError):
    """The fixed local Zoekt HTTP boundary was unavailable or unsafe."""


class ZoektResponseValidationError(ZoektClientError):
    """The pinned response schema changed or was malformed."""


class ZoektResponseTooLarge(ZoektClientError):
    """The loopback process exceeded the bounded response contract."""


class ZoektResponseTimeout(ZoektClientError):
    """The one permitted loopback request did not finish in time."""


@dataclass(frozen=True)
class RawZoektMatch:
    """A normalized raw upstream line match before manifest identity attachment."""

    repository_name: str
    branches: tuple[str, ...]
    language: str
    path: str
    line_start: int
    line_end: int
    preview: str
    context_before: tuple[str, ...]
    context_after: tuple[str, ...]
    file_url: str = ""
    match_url: str = ""


@dataclass(frozen=True)
class RawZoektResult:
    """The limited facts the facade may consume from the pinned HTTP response."""

    matches: tuple[RawZoektMatch, ...]
    total_match_count: int
    query_completed: bool
    truncated: bool
    pinned_response_contract_digest: str | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, request: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> Request | None:
        return None


class ZoektClient:
    """Issue exactly one bounded request to a host-injected loopback endpoint."""

    def __init__(
        self,
        endpoint: LoopbackEndpoint,
        *,
        timeout_seconds: float,
        maximum_response_bytes: int = _MAX_RESPONSE_BYTES,
        pinned_response_contract_digest: str | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if maximum_response_bytes <= 0 or maximum_response_bytes > _MAX_RESPONSE_BYTES:
            raise ValueError("maximum_response_bytes must be in 1..8MiB")
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes
        self._pinned_response_contract_digest = _optional_sha256(
            pinned_response_contract_digest, "pinned_response_contract_digest"
        )
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def search(
        self,
        query: str,
        *,
        limit: int,
        context_lines: int,
        case_sensitive: bool,
        regex: bool,
        repository_names: tuple[str, ...] = (),
        refs: tuple[str, ...] = (),
        path_prefixes: tuple[str, ...] = (),
        languages: tuple[str, ...] = (),
    ) -> RawZoektResult:
        """Submit one request; network and semantic ambiguity are never retried."""

        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be in 1..100")
        if type(context_lines) is not int or not 0 <= context_lines <= 8:
            raise ValueError("context_lines must be in 0..8")
        if type(case_sensitive) is not bool or type(regex) is not bool:
            raise ValueError("case_sensitive and regex must be booleans")
        backend_query = _backend_query(
            query,
            case_sensitive=case_sensitive,
            regex=regex,
            repository_names=_safe_query_terms(repository_names, "repository_names"),
            refs=_safe_query_terms(refs, "refs"),
            path_prefixes=_safe_query_terms(path_prefixes, "path_prefixes"),
            languages=_safe_query_terms(languages, "languages"),
        )
        parameters = urlencode(
            {
                "format": "json",
                "q": backend_query,
                "num": str(limit),
                "ctx": str(context_lines),
            }
        )
        request = Request(
            f"{self._endpoint.url}/search?{parameters}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                status = response.getcode()
                if status != 200:
                    raise ZoektClientError(f"Zoekt returned status {status}")
                body = response.read(self._maximum_response_bytes + 1)
        except HTTPError as error:
            if 300 <= error.code < 400:
                raise ZoektClientError("Zoekt response redirect is forbidden") from error
            raise ZoektClientError(f"Zoekt returned status {error.code}") from error
        except (TimeoutError, socket.timeout) as error:
            raise ZoektResponseTimeout("Zoekt response timed out") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise ZoektResponseTimeout("Zoekt response timed out") from error
            raise ZoektClientError("Zoekt loopback request failed") from error

        if len(body) > self._maximum_response_bytes:
            raise ZoektResponseTooLarge("Zoekt response exceeds 8MiB contract")
        return _parse_response(
            body,
            limit=limit,
            pinned_response_contract_digest=self._pinned_response_contract_digest,
        )


def _backend_query(
    query: str,
    *,
    case_sensitive: bool,
    regex: bool,
    repository_names: tuple[str, ...] = (),
    refs: tuple[str, ...] = (),
    path_prefixes: tuple[str, ...] = (),
    languages: tuple[str, ...] = (),
) -> str:
    if not isinstance(query, str) or not query:
        raise ValueError("query must be non-empty")
    case = "yes" if case_sensitive else "no"
    content = f"content:{query}" if regex else f"content:{json.dumps(query)}"
    filters = (
        _or_filter("repo", repository_names, quoted=True),
        _or_filter("branch", refs),
        _or_filter("file", tuple(f"^{prefix.rstrip('/')}/" for prefix in path_prefixes)),
        _or_filter("lang", languages),
    )
    return " ".join(filter(None, (f"case:{case}", content, *filters)))


def _parse_response(
    body: bytes, *, limit: int, pinned_response_contract_digest: str | None = None
) -> RawZoektResult:
    try:
        decoded = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ZoektResponseValidationError("Zoekt response is not valid strict JSON") from error
    top = _object(decoded, "response")
    _exact_keys(top, _TOP_LEVEL_KEYS, "response")
    result = _object(top["result"], "response.result")
    _exact_keys(result, _RESULT_KEYS, "response.result")
    _validate_last(_object(result["Last"], "response.result.Last"))
    _validate_stats(_object(result["Stats"], "response.result.Stats"))
    if not isinstance(result["QueryStr"], str) or not isinstance(result["Query"], str):
        raise ZoektResponseValidationError("response query fields must be strings")
    if not _strict_int(result["Duration"]):
        raise ZoektResponseValidationError("response duration must be an integer")

    stats = _object(result["Stats"], "response.result.Stats")
    total_match_count = stats["MatchCount"]
    assert isinstance(total_match_count, int)
    if total_match_count < 0:
        raise ZoektResponseValidationError("response MatchCount must be non-negative")
    # Zoekt's current empty-result serializer may emit null instead of []; the
    # engine count remains authoritative.  A nonzero count with no rows is
    # therefore accepted only as an explicitly truncated result below.
    matches = (
        []
        if result["FileMatches"] is None
        else _parse_file_matches(result["FileMatches"])
    )
    if total_match_count < len(matches):
        raise ZoektResponseValidationError("response MatchCount is below parsed match count")
    truncated = (
        total_match_count > len(matches)
        or stats["FilesSkipped"] > 0
        or stats["FilesSkippedDueToCancellation"] > 0
        or stats["ShardsSkipped"] > 0
        or len(matches) > limit
    )
    return RawZoektResult(
        matches=tuple(matches[:limit]),
        total_match_count=total_match_count,
        query_completed=(
            stats["Crashes"] == 0
            and stats["FilesSkippedDueToCancellation"] == 0
            and stats["ShardsSkipped"] == 0
        ),
        truncated=truncated,
        pinned_response_contract_digest=_optional_sha256(
            pinned_response_contract_digest, "pinned_response_contract_digest"
        ),
    )


def _parse_file_matches(value: object) -> list[RawZoektMatch]:
    if not isinstance(value, list):
        raise ZoektResponseValidationError("response FileMatches must be a list")
    parsed: list[RawZoektMatch] = []
    for file_index, raw_file in enumerate(value):
        file_match = _object(raw_file, f"response FileMatches[{file_index}]")
        _exact_keys(file_match, _FILE_MATCH_KEYS, f"response FileMatches[{file_index}]")
        for field in ("FileName", "Repo", "ResultID", "Language", "DuplicateID", "URL"):
            if not isinstance(file_match[field], str):
                raise ZoektResponseValidationError(f"{field} must be a string")
        branches = _strings(file_match["Branches"], "Branches")
        if not branches:
            raise ZoektResponseValidationError("Branches must not be empty")
        path = _repository_relative_path(file_match["FileName"])
        file_url = _safe_relative_uri(file_match["URL"], "file URL")
        language = _language(file_match["Language"])
        raw_lines = file_match["Matches"]
        if not isinstance(raw_lines, list):
            raise ZoektResponseValidationError("Matches must be a list")
        for line_index, raw_line in enumerate(raw_lines):
            line = _object(raw_line, f"response Match[{line_index}]")
            _required_optional_keys(
                line,
                _MATCH_REQUIRED_KEYS,
                _MATCH_OPTIONAL_KEYS,
                f"response Match[{line_index}]",
            )
            if not isinstance(line["URL"], str) or not isinstance(line["FileName"], str):
                raise ZoektResponseValidationError("match URL and FileName must be strings")
            if _repository_relative_path(line["FileName"]) != path:
                raise ZoektResponseValidationError("match path disagrees with file match path")
            if not _strict_int(line["LineNum"]) or line["LineNum"] < 1:
                raise ZoektResponseValidationError("match LineNum must be positive")
            fragments = line["Fragments"]
            if not isinstance(fragments, list) or not fragments:
                raise ZoektResponseValidationError("match Fragments must be a non-empty list")
            preview = ""
            for fragment in fragments:
                fragment_object = _object(fragment, "match fragment")
                _exact_keys(fragment_object, _FRAGMENT_KEYS, "match fragment")
                if not all(isinstance(fragment_object[key], str) for key in _FRAGMENT_KEYS):
                    raise ZoektResponseValidationError("match fragment values must be strings")
                preview += (
                    fragment_object["Pre"]
                    + fragment_object["Match"]
                    + fragment_object["Post"]
                )
            _bounded_response_text(preview, "match preview", _MAX_PREVIEW_BYTES)
            before = line.get("Before", "")
            after = line.get("After", "")
            if not isinstance(before, str) or not isinstance(after, str):
                raise ZoektResponseValidationError("match context must be strings")
            _bounded_response_text(before, "match context", _MAX_CONTEXT_BYTES)
            _bounded_response_text(after, "match context", _MAX_CONTEXT_BYTES)
            parsed.append(
                RawZoektMatch(
                    repository_name=file_match["Repo"],
                    branches=branches,
                    language=language,
                    path=path,
                    line_start=line["LineNum"],
                    line_end=line["LineNum"],
                    preview=preview,
                    context_before=(before,) if before else (),
                    context_after=(after,) if after else (),
                    file_url=file_url,
                    match_url=_safe_relative_uri(line["URL"], "match URL"),
                )
            )
    return parsed


def _validate_last(value: Mapping[str, object]) -> None:
    _exact_keys(value, _LAST_KEYS, "response.result.Last")
    if not isinstance(value["Query"], str):
        raise ZoektResponseValidationError("Last.Query must be a string")
    if not _strict_int(value["Num"]) or not _strict_int(value["Ctx"]):
        raise ZoektResponseValidationError("Last numeric fields must be integers")
    if type(value["AutoFocus"]) is not bool or type(value["Debug"]) is not bool:
        raise ZoektResponseValidationError("Last boolean fields must be booleans")


def _validate_stats(value: Mapping[str, object]) -> None:
    _exact_keys(value, _STATS_KEYS, "response.result.Stats")
    if any(not _strict_int(item) for item in value.values()):
        raise ZoektResponseValidationError("response statistics must be integers")
    if any(item < 0 for item in value.values()):
        raise ZoektResponseValidationError("response statistics must be non-negative")


def _optional_sha256(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be lowercase SHA-256")
    return value


def _safe_query_terms(value: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{field} must be a tuple of non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{field} must not contain duplicates")
    return value


def _or_filter(field: str, values: tuple[str, ...], *, quoted: bool = False) -> str:
    if not values:
        return ""
    terms = tuple(
        f"{field}:{json.dumps(value)}" if quoted else f"{field}:{value}"
        for value in values
    )
    return terms[0] if len(terms) == 1 else f"({' or '.join(terms)})"


def _language(value: str) -> str:
    normalized = value.lower()
    if not normalized or len(normalized.encode("utf-8")) > 128:
        raise ZoektResponseValidationError("Language must be a bounded non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ZoektResponseValidationError("Language contains a control character")
    return normalized


def _safe_relative_uri(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ZoektResponseValidationError(f"{label} must be a string")
    if not value:
        return ""
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ZoektResponseValidationError(f"{label} must be a relative local URI")
    raise ZoektResponseValidationError(
        f"{label} has unknown URI semantic without a pinned manifest mapping"
    )


def _bounded_response_text(value: str, label: str, maximum: int) -> None:
    if len(value.encode("utf-8")) > maximum:
        raise ZoektResponseValidationError(f"{label} exceeds bounded bytes")


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ZoektResponseValidationError(f"{label} must be an object")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ZoektResponseValidationError(f"{label} must be a list of strings")
    return tuple(value)


def _repository_relative_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ZoektResponseValidationError("match path must be repository-relative")
    return value


def _strict_int(value: object) -> bool:
    return type(value) is int


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], label: str
) -> None:
    if set(value) != expected:
        raise ZoektResponseValidationError(
            f"{label} has semantic schema drift: {sorted(set(value) ^ expected)}"
        )


def _required_optional_keys(
    value: Mapping[str, object],
    required: frozenset[str],
    optional: frozenset[str],
    label: str,
) -> None:
    if not required <= set(value) or not set(value) <= required | optional:
        raise ZoektResponseValidationError(f"{label} has semantic schema drift")


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")
