"""Closed Research Read MCP contract tests. No network, store, or server."""
from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from integrations.research_read_mcp import CONTRACT
from integrations.research_read_mcp import contracts as c

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements" / "research-read-linux-x86_64-py312.in"
LOCK = ROOT / "requirements" / "research-read-linux-x86_64-py312.lock"
DIRECT_PINS = [
    "mcp==1.28.1",
    "PyJWT[crypto]==2.13.0",
    "httpx==0.28.1",
    "jsonschema==4.26.0",
    "pydantic==2.13.5",
    "starlette==1.6.0",
    "uvicorn[standard]==0.52.4",
    "boto3==1.43.62",
    "botocore==1.43.62",
]
DESCRIPTIONS = {
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
OPTIONAL_INPUTS = {
    "research_status": set(),
    "research_search": {"institution", "from", "to", "limit"},
    "research_fetch": {"segment_start", "max_segments"},
    "research_find_evidence": {"report_ids", "limit"},
}
MASTERMIND_COMMIT = "b" * 40
CANONICAL = "Institutional demand remains concentrated in the front end of the curve. 研报"


def _invalid(tool: str, arguments: object) -> None:
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_arguments(tool, arguments)
    assert caught.value.code == "INVALID_REQUEST"


def _internal(tool: str, result: object, **kwargs: object) -> None:
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_output(tool, result, **kwargs)
    assert caught.value.code == "INTERNAL_ERROR"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _walk(schema: object):
    if isinstance(schema, dict):
        yield schema
        for key in ("properties", "$defs"):
            child = schema.get(key)
            if isinstance(child, dict):
                for sub in child.values():
                    yield from _walk(sub)
        items = schema.get("items")
        if isinstance(items, dict):
            yield from _walk(items)
        elif isinstance(items, list):
            for sub in items:
                yield from _walk(sub)
        prefix = schema.get("prefixItems")
        if isinstance(prefix, list):
            for sub in prefix:
                yield from _walk(sub)
        for key in ("anyOf", "oneOf", "allOf"):
            group = schema.get(key)
            if isinstance(group, list):
                for sub in group:
                    yield from _walk(sub)
    elif isinstance(schema, list):
        for sub in schema:
            yield from _walk(sub)


def _object_schemas(schema: object):
    for node in _walk(schema):
        if isinstance(node, dict) and (node.get("type") == "object" or "properties" in node):
            yield node


def _candidate(index: int, *, report_id: str | None = None, rank: int | None = None) -> dict:
    return {
        "report_id": report_id or f"report-{index}",
        "title": "Rates outlook",
        "institution": "Example",
        "side": "long",
        "published_at": "2026-10-07T00:00:00Z",
        "rank": index if rank is None else rank,
    }


def _status_result() -> dict:
    return {
        "contract": CONTRACT,
        "source_state": "SOURCE_FRESH",
        "producer": {
            "last_success_at": "2026-10-07T00:00:00Z",
            "age_seconds": 1.5,
            "stale": False,
        },
        "catalog": {
            "report_count": 2,
        },
        "coverage": {
            "full_text_ratio": 1.0,
            "rio_ratio": 0.5,
        },
        "degradation": [],
        "generation": {
            "server_contract": CONTRACT,
            "read_port_contract": "research_vault.read_status.v1",
            "mastermind_commit": MASTERMIND_COMMIT,
        },
    }


def _search_result() -> dict:
    return {
        "contract": CONTRACT,
        "source_state": "PRODUCER_STALE",
        "candidates": [_candidate(1), _candidate(2, report_id="report-2")],
        "coverage_note": "catalog is stale",
    }


def _segment(
    index: int,
    text: str,
    byte_start: int,
    *,
    page_start: int | None = 1,
    page_end: int | None = 1,
) -> dict:
    raw = text.encode("utf-8")
    return {
        "segment_index": index,
        "page_start": page_start,
        "page_end": page_end,
        "byte_start": byte_start,
        "byte_end": byte_start + len(raw),
        "text": text,
    }


def _fetch_result(
    *,
    segments: list[dict] | None = None,
    total: int | None = None,
    coverage_state: str = "FULL_TEXT",
    text: str | None = None,
    text_layer_state: str | None = "full",
) -> dict:
    if segments is None:
        body = "hello" if text is None else text
        segments = [_segment(0, body, 0)]
    if total is None:
        total = len(segments) if coverage_state == "FULL_TEXT" else 0
    if segments:
        following = segments[-1]["segment_index"] + 1
        nxt = following if following < total else None
    else:
        nxt = None
    return {
        "contract": CONTRACT,
        "source_state": "SOURCE_FRESH",
        "report": {
            "report_id": "abc-1",
            "title": "Rates outlook",
            "institution": "Example",
            "side": "long",
            "published_at": "2026-10-07T00:00:00Z",
        },
        "provenance": {
            "source_class": "mastermind_private_institutional",
            "license_class": "internal_licensed",
        },
        "text_layer_state": text_layer_state,
        "coverage_state": coverage_state,
        "segment_count_total": total,
        "segments": segments,
        "next_segment_start": nxt,
        "rio_state": "CURRENT",
    }


def _passage(
    text: str,
    byte_start: int,
    report_id: str = "abc-1",
    *,
    segment_index: int = 0,
) -> dict:
    raw_text = text.encode("utf-8")
    return {
        "report_id": report_id,
        "passage_text": text,
        "byte_start": byte_start,
        "byte_end": byte_start + len(raw_text),
        "text_sha256": _sha256(raw_text),
        "canonical_text_sha256": _sha256(CANONICAL.encode("utf-8")),
        "segment_index": segment_index,
    }


def _evidence_result(outcome: str, passages: list[dict]) -> dict:
    return {
        "contract": CONTRACT,
        "source_state": "SOURCE_FRESH",
        "outcome": outcome,
        "passages": passages,
        "rio_state": "MISSING",
    }


def _found_passages() -> list[dict]:
    raw = CANONICAL.encode("utf-8")
    first = "Institutional"
    suffix = "研报"
    assert CANONICAL.startswith(first)
    assert suffix in CANONICAL
    assert len(suffix.encode("utf-8")) != len(suffix)
    char_at = CANONICAL.index(suffix)
    spans = (
        (0, len(first.encode("utf-8")), "abc-1"),
        (len(CANONICAL[:char_at].encode("utf-8")), len(CANONICAL[:char_at].encode("utf-8")) + len(suffix.encode("utf-8")), "abc-2"),
    )
    passages = []
    for byte_start, byte_end, report_id in spans:
        passage_text = raw[byte_start:byte_end].decode("utf-8")
        assert raw[byte_start:byte_end] == passage_text.encode("utf-8")
        passages.append(_passage(passage_text, byte_start, report_id=report_id))
    return passages


def _output_cases() -> list[tuple[str, str, object, dict]]:
    search = _search_result()
    swapped = copy.deepcopy(search)
    swapped["candidates"][0]["rank"] = 2
    swapped["candidates"][1]["rank"] = 1
    duplicate = copy.deepcopy(search)
    duplicate["candidates"][1]["report_id"] = duplicate["candidates"][0]["report_id"]
    snippet = copy.deepcopy(search)
    snippet["candidates"][0]["snippet"] = "secret"
    many = copy.deepcopy(search)
    many["candidates"] = [_candidate(i) for i in range(1, 22)]
    length_mismatch = _evidence_result("FOUND", [_passage("ab", 0)])
    length_mismatch["passages"][0]["byte_end"] = 1
    same_offset = _evidence_result("FOUND", [_passage("ab", 4)])
    same_offset["passages"][0]["byte_end"] = same_offset["passages"][0]["byte_start"]
    long_passage = _evidence_result("FOUND", [_passage("p" * 1201, 0)])
    quote_passage = _evidence_result("FOUND", [_passage("q" * 101, 0)])
    fetch = _fetch_result(text="hello", total=4)
    bad_length = copy.deepcopy(fetch)
    bad_length["segments"][0]["text"] = "hell"
    bad_next_missing = copy.deepcopy(fetch)
    bad_next_missing["next_segment_start"] = None
    bad_next_wrong = copy.deepcopy(fetch)
    bad_next_wrong["next_segment_start"] = 0
    done = _fetch_result(text="hello")
    bad_next_when_done = copy.deepcopy(done)
    bad_next_when_done["next_segment_start"] = 1
    bad_index = copy.deepcopy(done)
    bad_index["segments"][0]["segment_index"] = 1
    huge_text = _fetch_result(text="x" * 12001)
    status = _status_result()
    bad_server = copy.deepcopy(status)
    bad_server["generation"]["server_contract"] = "other"
    bad_commit = copy.deepcopy(status)
    bad_commit["generation"]["mastermind_commit"] = "b" * 39
    bad_mastermind = copy.deepcopy(status)
    bad_mastermind["generation"]["mastermind_commit"] = ("b" * 40) + "\n"
    bad_license = _fetch_result(text="hello")
    bad_license["provenance"]["license_class"] = "public"
    wrong_contract = _search_result()
    wrong_contract["contract"] = "other"
    missing_state = _search_result()
    del missing_state["source_state"]
    bad_state = _search_result()
    bad_state["source_state"] = "OK"
    extra = _search_result()
    extra["unexpected"] = 1
    return [
        ("wrong_contract", "research_search", wrong_contract, {}),
        ("missing_source_state", "research_search", missing_state, {}),
        ("source_state_ok", "research_search", bad_state, {}),
        ("extra_top_level_field", "research_search", extra, {}),
        ("search_candidate_snippet", "research_search", snippet, {}),
        ("twenty_one_candidates", "research_search", many, {}),
        ("ranks_reversed", "research_search", swapped, {}),
        ("duplicate_report_id", "research_search", duplicate, {}),
        ("passage_length_mismatch", "research_find_evidence", length_mismatch, {}),
        ("passage_zero_width", "research_find_evidence", same_offset, {}),
        ("found_with_no_passages", "research_find_evidence", _evidence_result("FOUND", []), {}),
        ("not_found_with_passage", "research_find_evidence", _evidence_result("NOT_FOUND", [_passage("ab", 0)]), {}),
        ("passage_text_1201", "research_find_evidence", long_passage, {}),
        ("quote_limit_exceeded", "research_find_evidence", quote_passage, {"quote_limit_chars": 100}),
        ("fetch_segment_byte_length_mismatch", "research_fetch", bad_length, {}),
        ("fetch_next_segment_start_missing", "research_fetch", bad_next_missing, {}),
        ("fetch_next_segment_start_wrong", "research_fetch", bad_next_wrong, {}),
        ("fetch_next_segment_start_when_done", "research_fetch", bad_next_when_done, {}),
        ("fetch_segment_index_past_total", "research_fetch", bad_index, {}),
        ("fetch_text_over_segment_cap", "research_fetch", huge_text, {}),
        ("status_server_contract_wrong", "research_status", bad_server, {}),
        ("status_mastermind_commit_39_hex", "research_status", bad_commit, {}),
        ("status_mastermind_commit_trailing_newline", "research_status", bad_mastermind, {}),
        ("provenance_license_class_changed", "research_fetch", bad_license, {}),
        ("unknown_tool_name", "research_delete", _status_result(), {}),
        ("non_dict_result", "research_status", [], {}),
    ]


def test_tool_names_schemas_and_definitions_match_the_closed_census() -> None:
    assert c.TOOL_NAMES == (
        "research_status",
        "research_search",
        "research_fetch",
        "research_find_evidence",
    )
    assert set(c.INPUT_SCHEMAS) == set(c.OUTPUT_SCHEMAS) == set(c.TOOL_NAMES)
    definitions = c.tool_definitions()
    assert [item["name"] for item in definitions] == list(c.TOOL_NAMES)
    for item in definitions:
        assert item["annotations"] == c.TOOL_ANNOTATIONS
        assert item["description"] == DESCRIPTIONS[item["name"]]
        assert set(item) == {"name", "description", "inputSchema", "outputSchema", "annotations"}
    definitions[1]["inputSchema"]["properties"]["query"]["maxLength"] = 1
    definitions[1]["inputSchema"]["required"].append("institution")
    assert c.INPUT_SCHEMAS["research_search"]["properties"]["query"]["maxLength"] == 200
    assert c.INPUT_SCHEMAS["research_search"]["required"] == ["query"]


def test_schemas_are_draft2020_closed_objects_without_schema_keyword() -> None:
    schemas = [*c.INPUT_SCHEMAS.values(), *c.OUTPUT_SCHEMAS.values()]
    assert len(schemas) == 8
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        for node in _walk(schema):
            if isinstance(node, dict):
                assert "$schema" not in node
    for tool_name, schema in c.OUTPUT_SCHEMAS.items():
        for node in _object_schemas(schema):
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        assert tool_name in c.TOOL_NAMES
    for tool_name, schema in c.INPUT_SCHEMAS.items():
        for node in _object_schemas(schema):
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"]) - OPTIONAL_INPUTS[tool_name]


def test_forbidden_field_names_are_absent_from_schemas_and_public_parameters() -> None:
    assert c.FORBIDDEN_FIELD_NAMES == frozenset({
        "bucket", "key", "prefix", "root", "path", "store", "url",
        "principal", "tier", "policy", "grant", "credential", "visibility",
    })
    for schema in [*c.INPUT_SCHEMAS.values(), *c.OUTPUT_SCHEMAS.values()]:
        for node in _walk(schema):
            if isinstance(node, dict) and isinstance(node.get("properties"), dict):
                assert c.FORBIDDEN_FIELD_NAMES.isdisjoint(node["properties"])
    for name in c.__all__:
        value = getattr(c, name)
        if not callable(value):
            continue
        for parameter in inspect.signature(value).parameters:
            assert parameter not in c.FORBIDDEN_FIELD_NAMES


@pytest.mark.parametrize("field", sorted(c.FORBIDDEN_FIELD_NAMES))
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("research_status", {}),
        ("research_search", {"query": "a"}),
        ("research_fetch", {"report_id": "abc-1"}),
        ("research_find_evidence", {"claim": "a"}),
    ],
)
def test_forbidden_input_field_is_invalid_request(tool: str, arguments: dict, field: str) -> None:
    payload = dict(arguments)
    payload[field] = "x"
    _invalid(tool, payload)


@pytest.mark.parametrize(
    "query",
    ["", "a" * 201, "a\x00b", "a\nb", "a\x7fb", "a\x85b"],
)
def test_search_query_rejects_empty_overlong_and_control_characters(query: str) -> None:
    _invalid("research_search", {"query": query})


def test_search_query_accepts_bounds_and_cjk_and_applies_limit_default_without_mutating() -> None:
    for query in ["a", "a" * 200, "研" * 200]:
        original = {"query": query}
        snapshot = copy.deepcopy(original)
        accepted = c.validate_arguments("research_search", original)
        assert accepted["query"] == query
        assert accepted["limit"] == 8
        assert original == snapshot
        assert accepted is not original
    explicit = {"query": "kept", "limit": 3}
    assert c.validate_arguments("research_search", explicit)["limit"] == 3
    assert explicit == {"query": "kept", "limit": 3}


def test_search_institution_accepts_80_and_rejects_81() -> None:
    assert c.validate_arguments("research_search", {"query": "a", "institution": "i" * 80})["institution"] == "i" * 80
    _invalid("research_search", {"query": "a", "institution": "i" * 81})


@pytest.mark.parametrize("field", ["from", "to"])
@pytest.mark.parametrize("value", ["2026-1-07", "2026-10-07\n", "٢٠٢٦-١٠-٠٧"])
def test_search_dates_reject_short_newline_and_non_ascii_digits(field: str, value: str) -> None:
    _invalid("research_search", {"query": "a", field: value})


def test_search_dates_accept_iso_day() -> None:
    accepted = c.validate_arguments(
        "research_search",
        {"query": "a", "from": "2026-10-07", "to": "2026-10-07"},
    )
    assert accepted["from"] == "2026-10-07"
    assert accepted["to"] == "2026-10-07"


@pytest.mark.parametrize("limit", [0, 21, True, 8.0, "8"])
def test_search_limit_rejects_out_of_range_bool_float_and_string(limit: object) -> None:
    _invalid("research_search", {"query": "a", "limit": limit})


@pytest.mark.parametrize("limit", [1, 20])
def test_search_limit_accepts_closed_range(limit: int) -> None:
    assert c.validate_arguments("research_search", {"query": "a", "limit": limit})["limit"] == limit


@pytest.mark.parametrize(
    "report_id",
    ["Abc", "-abc", "abc\n", "a/b", "a" + ("b" * 121)],
)
def test_fetch_report_id_rejects_shape_and_122_chars(report_id: str) -> None:
    assert len("a" + ("b" * 121)) == 122
    _invalid("research_fetch", {"report_id": report_id})


@pytest.mark.parametrize("report_id", ["abc-1", "a" + ("b" * 120)])
def test_fetch_report_id_accepts_pattern_and_121_chars(report_id: str) -> None:
    assert len("a" + ("b" * 120)) == 121
    accepted = c.validate_arguments("research_fetch", {"report_id": report_id})
    assert accepted["report_id"] == report_id
    assert accepted["segment_start"] == 0
    assert accepted["max_segments"] == 2


def test_fetch_defaults_do_not_mutate_the_caller() -> None:
    original = {"report_id": "abc-1"}
    snapshot = copy.deepcopy(original)
    accepted = c.validate_arguments("research_fetch", original)
    assert accepted["segment_start"] == 0
    assert accepted["max_segments"] == 2
    assert original == snapshot
    explicit = {"report_id": "abc-1", "segment_start": 4, "max_segments": 1}
    assert c.validate_arguments("research_fetch", explicit) == explicit
    assert explicit == {"report_id": "abc-1", "segment_start": 4, "max_segments": 1}


@pytest.mark.parametrize("claim", ["a" * 301, "a\nb"])
def test_find_evidence_claim_rejects_overlong_and_newline(claim: str) -> None:
    _invalid("research_find_evidence", {"claim": claim})


@pytest.mark.parametrize("claim", ["a", "a" * 300])
def test_find_evidence_claim_accepts_bounds_and_limit_defaults_to_5(claim: str) -> None:
    original = {"claim": claim}
    snapshot = copy.deepcopy(original)
    accepted = c.validate_arguments("research_find_evidence", original)
    assert accepted["claim"] == claim
    assert accepted["limit"] == 5
    assert original == snapshot


def test_find_evidence_report_ids_reject_empty_duplicate_overflow_and_bad_id() -> None:
    _invalid("research_find_evidence", {"claim": "a", "report_ids": []})
    _invalid("research_find_evidence", {"claim": "a", "report_ids": [f"r{i}" for i in range(11)]})
    _invalid("research_find_evidence", {"claim": "a", "report_ids": ["abc-1", "abc-1"]})
    _invalid("research_find_evidence", {"claim": "a", "report_ids": ["Abc"]})


def test_find_evidence_report_ids_accept_ten_unique_without_mutating_caller() -> None:
    report_ids = [f"r{i}" for i in range(10)]
    original = {"claim": "a", "report_ids": report_ids}
    accepted = c.validate_arguments("research_find_evidence", original)
    assert accepted["report_ids"] == report_ids
    assert accepted["report_ids"] is not original["report_ids"]
    accepted["report_ids"].append("extra-id")
    assert original["report_ids"] == report_ids
    assert accepted["limit"] == 5


@pytest.mark.parametrize("limit", [0, 11])
def test_find_evidence_limit_rejects_outside_closed_range(limit: int) -> None:
    _invalid("research_find_evidence", {"claim": "a", "limit": limit})


@pytest.mark.parametrize("limit", [1, 10])
def test_find_evidence_limit_accepts_closed_range(limit: int) -> None:
    assert c.validate_arguments("research_find_evidence", {"claim": "a", "limit": limit})["limit"] == limit


def test_status_requires_an_empty_object() -> None:
    original: dict = {}
    accepted = c.validate_arguments("research_status", original)
    assert accepted == {}
    assert accepted is not original
    _invalid("research_status", {"x": 1})
    _invalid("research_status", None)
    _invalid("research_status", [])


def test_argument_byte_cap_is_read_from_the_module_global(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"query": "hello world"}
    assert c.validate_arguments("research_search", payload)["query"] == "hello world"
    monkeypatch.setattr(c, "MAX_ARGUMENT_BYTES", 10)
    _invalid("research_search", payload)


def test_non_json_arguments_are_invalid_request() -> None:
    _invalid("research_search", {"query": "x", "limit": float("nan")})
    _invalid("research_search", {"query": object()})


def test_unknown_or_non_string_tool_is_not_available() -> None:
    with pytest.raises(c.ContractViolation) as unknown:
        c.validate_arguments("research_delete", {})
    assert unknown.value.code == "TOOL_NOT_AVAILABLE"
    with pytest.raises(c.ContractViolation) as untyped:
        c.validate_arguments(None, {"query": "a"})
    assert untyped.value.code == "TOOL_NOT_AVAILABLE"


def test_invalid_request_does_not_echo_input_or_chain_a_cause() -> None:
    canary = "CANARY-7f3e\x00"
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_arguments("research_search", {"query": canary})
    exc = caught.value
    assert str(exc) == "INVALID_REQUEST"
    assert exc.args == ("INVALID_REQUEST",)
    assert exc.code == "INVALID_REQUEST"
    assert canary not in str(exc)
    assert canary not in repr(exc)
    assert all(canary not in str(part) for part in exc.args)
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    with pytest.raises(ValueError):
        c.ContractViolation("BOGUS")


def test_valid_outputs_pass_including_segments_ranks_and_literal_passages() -> None:
    c.validate_output("research_status", _status_result())
    search = _search_result()
    c.validate_output("research_search", search)
    assert [item["rank"] for item in search["candidates"]] == [1, 2]
    continued = _fetch_result(total=3)
    whole = _fetch_result()
    c.validate_output("research_fetch", continued)
    c.validate_output("research_fetch", whole)
    assert continued["next_segment_start"] == 1
    assert whole["next_segment_start"] is None
    passages = _found_passages()
    raw = CANONICAL.encode("utf-8")
    for passage in passages:
        byte_start = passage["byte_start"]
        byte_end = passage["byte_end"]
        assert raw[byte_start:byte_end] == passage["passage_text"].encode("utf-8")
    c.validate_output("research_find_evidence", _evidence_result("FOUND", passages))
    c.validate_output("research_find_evidence", _evidence_result("PARTIAL", passages[:1]))
    c.validate_output("research_find_evidence", _evidence_result("NOT_FOUND", []))
    c.validate_output("research_find_evidence", _evidence_result("UNAVAILABLE", []))


@pytest.mark.parametrize(
    ("label", "tool", "result", "kwargs"),
    _output_cases(),
    ids=[case[0] for case in _output_cases()],
)
def test_output_invariant_or_schema_failure_is_internal_error(
    label: str, tool: str, result: object, kwargs: dict
) -> None:
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_output(tool, result, **kwargs)
    assert caught.value.code == "INTERNAL_ERROR"
    assert label


def test_maximal_cjk_results_fit_under_the_result_cap() -> None:
    unit = "文" * 1333
    raw_len = len(unit.encode("utf-8"))
    assert raw_len == 3999
    segments = []
    byte_at = 0
    for index in range(c.FETCH_MAX_SEGMENTS):
        segments.append(_segment(index, unit, byte_at, page_start=index + 1, page_end=index + 1))
        byte_at += raw_len
    fetch = _fetch_result(segments=segments, total=c.FETCH_MAX_SEGMENTS)
    passage_text = "文" * 1200
    passage_bytes = len(passage_text.encode("utf-8"))
    passages = [
        _passage(passage_text, index * passage_bytes, report_id=f"report-{index}", segment_index=index)
        for index in range(10)
    ]
    evidence = _evidence_result("FOUND", passages)
    fetch_bytes = c.result_wire_bytes(fetch)
    evidence_bytes = c.result_wire_bytes(evidence)
    assert fetch_bytes < 131072, fetch_bytes
    assert evidence_bytes < 131072, evidence_bytes
    for result in (fetch, evidence):
        manual = (
            len(json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            + len(json.dumps(result, indent=2).encode("utf-8"))
        )
        assert c.result_wire_bytes(result) == manual
    c.validate_output("research_fetch", fetch)
    c.validate_output("research_find_evidence", evidence)


def test_result_byte_cap_is_read_from_the_module_global(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "MAX_RESULT_BYTES", 100)
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_output("research_status", _status_result())
    assert caught.value.code == "INTERNAL_ERROR"


def test_error_codes_messages_and_caps_match_the_closed_table() -> None:
    assert c.ERROR_CODES == (
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
    assert set(c.ERROR_MESSAGES) == set(c.ERROR_CODES)
    assert c.ERROR_MESSAGES == {
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
    for code in c.ERROR_CODES:
        payload = c.error_payload(code)
        assert Draft202012Validator(c.ERROR_SCHEMA).is_valid(payload)
        assert payload == {"code": code, "message": c.ERROR_MESSAGES[code]}
    with pytest.raises(ValueError):
        c.error_payload("BOGUS")
    assert c.RATE_LIMIT_CALLS == 120
    assert c.RATE_LIMIT_WINDOW_SECONDS == 600
    assert c.MAX_ARGUMENT_BYTES == 4096
    assert c.MAX_RESULT_BYTES == 131072


def test_enums_contract_id_and_evidence_titles_match_the_frozen_contract() -> None:
    assert c.SOURCE_STATES == (
        "SOURCE_FRESH",
        "PRODUCER_STALE",
        "CATALOG_UNAVAILABLE",
        "NO_REPORTS",
        "LATEST_REPORT_INVALID",
        "FUTURE_REPORT_CLOCK",
    )
    assert c.COVERAGE_STATES == (
        "FULL_TEXT",
        "PREFIX_ONLY_LEGACY",
        "NO_TEXT_LAYER",
        "EXTRACTION_UNAVAILABLE",
        "SEGMENT_INDEX_PENDING",
        "PARTIAL_CORPUS",
        "SOURCE_REVISION_CHANGED",
    )
    assert c.TEXT_LAYER_STATES == ("full", "thin", "none", "unavailable")
    assert c.DEGRADATION_CODES == (
        "PRODUCER_STALE",
        "PARTIAL_CORPUS",
        "FULL_TEXT_PARTIAL",
        "RIO_PARTIAL",
        "METADATA_PARTIAL",
        "SCAN_NO_TEXT",
        "INDEX_REBUILD_PENDING",
    )
    assert c.RIO_STATES == ("CURRENT", "MISSING", "STALE", "INVALID", "NOT_REQUESTED")
    assert c.EVIDENCE_OUTCOMES == ("FOUND", "NOT_FOUND", "UNAVAILABLE", "PARTIAL")
    assert c.SEGMENT_MAX_BYTES == 4000
    assert c.FETCH_MAX_SEGMENTS == 4
    assert c.FETCH_DEFAULT_SEGMENTS == 2
    assert c.FETCH_MAX_TEXT_BYTES == 24000
    source = Path(c.__file__).read_text(encoding="utf-8")
    assert (
        "F10 engine/research_vault/read_port.py:31-49 and :75-83, fulltext.py:20, "
        "read_service.py:33-37 @ Macro bd6f27c8163 (#8610)."
    ) in source
    assert CONTRACT == "mastermind.research_read_mcp.v1.1"
    for schema in c.OUTPUT_SCHEMAS.values():
        assert schema["properties"]["contract"] == {"const": CONTRACT}
        assert schema["properties"]["source_state"]["enum"] == list(c.SOURCE_STATES)
    evidence = c.OUTPUT_SCHEMAS["research_find_evidence"]
    assert evidence["title"] == "research_vault.evidence_result.v1"
    assert "title" not in evidence["properties"]
    passage = evidence["properties"]["passages"]["items"]
    assert passage["title"] == "research.evidence_passage.v1"
    assert "title" not in passage["properties"]
    assert c.OUTPUT_SCHEMAS["research_status"]["properties"]["generation"]["properties"]["server_contract"] == {
        "const": CONTRACT
    }
    fetch = c.OUTPUT_SCHEMAS["research_fetch"]["properties"]
    assert fetch["coverage_state"]["enum"] == list(c.COVERAGE_STATES)
    assert fetch["text_layer_state"]["enum"] == [*c.TEXT_LAYER_STATES, None]
    assert fetch["text_layer_state"]["type"] == ["string", "null"]
    assert fetch["rio_state"]["enum"] == list(c.RIO_STATES)
    assert evidence["properties"]["rio_state"]["enum"] == list(c.RIO_STATES)
    assert evidence["properties"]["outcome"]["enum"] == list(c.EVIDENCE_OUTCOMES)


def test_contract_modules_import_only_the_allowlisted_modules() -> None:
    allowed = {
        "__future__",
        "copy",
        "hashlib",
        "json",
        "re",
        "typing",
        "collections",
        "collections.abc",
        "jsonschema",
        "jsonschema.validators",
        "jsonschema.exceptions",
    }
    contracts_tree = ast.parse(Path(c.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(contracts_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1 and node.module is None
                assert [alias.name for alias in node.names] == ["CONTRACT"]
            else:
                assert node.module in allowed
    package = Path(c.__file__).resolve().parent / "__init__.py"
    package_tree = ast.parse(package.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(package_tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert len(imports) == 1
    future = imports[0]
    assert isinstance(future, ast.ImportFrom)
    assert future.module == "__future__"
    assert [alias.name for alias in future.names] == ["annotations"]


def test_importing_the_package_does_not_load_sdk_auth_or_store_modules() -> None:
    forbidden = (
        "mcp",
        "starlette",
        "uvicorn",
        "httpx",
        "pydantic",
        "boto3",
        "botocore",
        "engine",
        "control_plane",
        "integrations.business_mcp_auth",
    )
    probe = (
        "import sys\n"
        "import integrations.research_read_mcp.contracts\n"
        f"forbidden = {forbidden!r}\n"
        "missing = [name for name in forbidden if name not in sys.modules]\n"
        "assert missing == list(forbidden), sorted(set(forbidden) - set(missing))\n"
    )
    first = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    second_probe = (
        "import sys\n"
        "import integrations.research_read_mcp\n"
        "assert 'integrations.research_read_mcp.contracts' not in sys.modules\n"
    )
    second = subprocess.run(
        [sys.executable, "-c", second_probe],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr


def _canonicalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def test_requirements_in_lists_the_nine_direct_pins_in_order() -> None:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    assert text.startswith("# Research Read MCP direct runtime roots — linux x86_64 / CPython 3.12\n")
    pins = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert pins == DIRECT_PINS


def test_lock_if_present_is_hashed_and_pins_the_same_direct_versions() -> None:
    if not LOCK.exists():
        return
    text = LOCK.read_text(encoding="utf-8")
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        assert not stripped.startswith("-e ")
        assert stripped != "-e"
        assert "git+" not in stripped
        assert not stripped.startswith("http://")
        assert not stripped.startswith("https://")
        if stripped.startswith("--"):
            index += 1
            continue
        matched = re.match(
            r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\\\s]+)\s*\\?$",
            stripped,
        )
        assert matched, stripped
        chunk = [lines[index]]
        if lines[index].rstrip().endswith("\\"):
            index += 1
            while index < len(lines):
                chunk.append(lines[index])
                if not lines[index].rstrip().endswith("\\"):
                    break
                index += 1
        block = "\n".join(chunk)
        assert "--hash=sha256:" in block
        for row in chunk:
            row_stripped = row.strip()
            if row_stripped.startswith("#"):
                continue
            assert not row_stripped.startswith("-e")
            assert "git+" not in row_stripped
            assert "http://" not in row_stripped
            assert "https://" not in row_stripped
        blocks.append((_canonicalize(matched.group(1)), matched.group(2)))
        index += 1
    locked = dict(blocks)
    for line in DIRECT_PINS:
        name, version = line.split("==", 1)
        name = name.split("[", 1)[0]
        assert locked[_canonicalize(name)] == version


_FETCH_RESULT_KEYS = [
    "contract",
    "source_state",
    "report",
    "provenance",
    "text_layer_state",
    "coverage_state",
    "segment_count_total",
    "segments",
    "next_segment_start",
    "rio_state",
]
_SEGMENT_KEYS = ["segment_index", "page_start", "page_end", "byte_start", "byte_end", "text"]
_CANDIDATE_KEYS = ["report_id", "title", "institution", "side", "published_at", "rank"]
_PASSAGE_KEYS = [
    "report_id",
    "passage_text",
    "byte_start",
    "byte_end",
    "text_sha256",
    "canonical_text_sha256",
    "segment_index",
]
_STATUS_KEYS = [
    "contract",
    "source_state",
    "producer",
    "catalog",
    "coverage",
    "degradation",
    "generation",
]
_BANNED_V1_KEYS = {
    "char_start",
    "char_end",
    "cursor",
    "max_chars",
    "tickers",
    "text_layer",
    "text_layer_ok",
    "text_layer_missing",
    "rio_available",
    "institution_count",
    "newest_report_date",
    "oldest_report_date",
    "macro_commit",
    "window",
    "published_date",
}


def _require_v11_fetch_schema() -> None:
    props = c.OUTPUT_SCHEMAS["research_fetch"]["properties"]
    assert list(props) == _FETCH_RESULT_KEYS
    assert "window" not in props


def _require_v11_passage_schema() -> None:
    props = c.OUTPUT_SCHEMAS["research_find_evidence"]["properties"]["passages"]["items"]["properties"]
    assert list(props) == _PASSAGE_KEYS
    assert "char_start" not in props


def _legacy_fetch() -> dict:
    text = "hello"
    return {
        "contract": CONTRACT,
        "source_state": "SOURCE_FRESH",
        "report": {
            "report_id": "abc-1",
            "title": "Rates outlook",
            "institution": "Example",
            "published_date": "2026-10-07",
        },
        "provenance": {
            "source_class": "mastermind_private_institutional",
            "license_class": "internal_licensed",
        },
        "text": text,
        "window": {
            "start": 0,
            "end": len(text),
            "total_chars": len(text),
            "truncated": False,
            "next_cursor": None,
        },
        "text_sha256": "ab" * 32,
        "rio_state": "CURRENT",
    }


def _legacy_search() -> dict:
    return {
        "contract": CONTRACT,
        "source_state": "SOURCE_FRESH",
        "candidates": [{
            "report_id": "report-1",
            "title": "Rates outlook",
            "institution": "Example",
            "published_date": "2026-10-07",
            "tickers": ["AAPL"],
            "text_layer": "FULL_TEXT",
            "rio_state": "CURRENT",
            "rank": 1,
        }],
        "coverage_note": "",
    }


def _legacy_passage() -> dict:
    text = "Institutional"
    return {
        "report_id": "abc-1",
        "passage_text": text,
        "char_start": 0,
        "char_end": len(text),
        "text_sha256": "ab" * 32,
    }


def _legacy_status() -> dict:
    return {
        "contract": CONTRACT,
        "source_state": "SOURCE_FRESH",
        "producer": {
            "last_success_at": "2026-10-07T00:00:00Z",
            "age_seconds": 1.5,
            "stale": False,
        },
        "catalog": {
            "report_count": 2,
            "institution_count": 1,
            "newest_report_date": "2026-10-07",
            "oldest_report_date": None,
        },
        "coverage": {
            "text_layer_ok": 2,
            "text_layer_missing": 0,
            "rio_available": 1,
        },
        "generation": {
            "server_contract": CONTRACT,
            "read_port_contract": "research_vault.read_status.v1",
            "macro_commit": "a" * 40,
            "mastermind_commit": MASTERMIND_COMMIT,
        },
    }


def _schema_keys(schema: object, found: set[str]) -> None:
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            found.update(properties)
            for child in properties.values():
                _schema_keys(child, found)
        required = schema.get("required")
        if isinstance(required, list):
            found.update(item for item in required if isinstance(item, str))
        for key in ("items", "additionalProperties", "contains"):
            child = schema.get(key)
            if isinstance(child, (dict, list)):
                _schema_keys(child, found)
        for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
            group = schema.get(key)
            if isinstance(group, list):
                for child in group:
                    _schema_keys(child, found)
    elif isinstance(schema, list):
        for child in schema:
            _schema_keys(child, found)


def test_row1_search_omits_cursor_and_limits_1_to_20_default_8() -> None:
    props = c.INPUT_SCHEMAS["research_search"]["properties"]
    assert "cursor" not in props
    assert props["limit"]["minimum"] == 1
    assert props["limit"]["maximum"] == 20
    original = {"query": "a"}
    snapshot = copy.deepcopy(original)
    assert c.validate_arguments("research_search", original)["limit"] == 8
    assert original == snapshot
    _invalid("research_search", {"query": "a", "limit": 0})
    _invalid("research_search", {"query": "a", "limit": 21})
    _invalid("research_search", {"query": "a", "cursor": 0})


def test_row2_fetch_inputs_are_segment_selectors() -> None:
    schema = c.INPUT_SCHEMAS["research_fetch"]
    assert list(schema["properties"]) == ["report_id", "segment_start", "max_segments"]
    assert schema["required"] == ["report_id"]
    assert schema["properties"]["segment_start"] == {"type": "integer", "minimum": 0}
    assert "maximum" not in schema["properties"]["segment_start"]
    assert schema["properties"]["max_segments"]["minimum"] == 1
    assert schema["properties"]["max_segments"]["maximum"] == 4
    original = {"report_id": "abc-1"}
    snapshot = copy.deepcopy(original)
    accepted = c.validate_arguments("research_fetch", original)
    assert accepted["segment_start"] == 0
    assert accepted["max_segments"] == 2
    assert original == snapshot
    large = c.validate_arguments("research_fetch", {"report_id": "abc-1", "segment_start": 10**6})
    assert large["segment_start"] == 10**6
    assert large["max_segments"] == 2
    assert c.validate_arguments(
        "research_fetch", {"report_id": "abc-1", "max_segments": 4}
    )["max_segments"] == 4
    for arguments in (
        {"report_id": "abc-1", "segment_start": -1},
        {"report_id": "abc-1", "max_segments": 0},
        {"report_id": "abc-1", "max_segments": 5},
        {"report_id": "abc-1", "segment_start": True},
        {"report_id": "abc-1", "segment_start": False},
        {"report_id": "abc-1", "max_segments": True},
        {"report_id": "abc-1", "max_segments": False},
    ):
        _invalid("research_fetch", arguments)


def test_row2_fetch_rejects_cursor_and_max_chars() -> None:
    _invalid("research_fetch", {"report_id": "abc-1", "cursor": 0})
    _invalid("research_fetch", {"report_id": "abc-1", "max_chars": 6000})


def test_row2_fetch_result_matches_segment_schema() -> None:
    _require_v11_fetch_schema()
    result = _fetch_result(total=3)
    c.validate_output("research_fetch", result)
    assert list(result) == _FETCH_RESULT_KEYS
    segment_schema = c.OUTPUT_SCHEMAS["research_fetch"]["properties"]["segments"]["items"]
    assert list(segment_schema["properties"]) == _SEGMENT_KEYS
    assert list(result["segments"][0]) == _SEGMENT_KEYS
    both_null = _fetch_result()
    both_null["segments"][0]["page_start"] = None
    both_null["segments"][0]["page_end"] = None
    c.validate_output("research_fetch", both_null)
    nullable_layer = _fetch_result()
    nullable_layer["text_layer_state"] = None
    c.validate_output("research_fetch", nullable_layer)
    extra = _fetch_result()
    extra["segments"][0]["extra"] = 1
    _internal("research_fetch", extra)
    missing = _fetch_result()
    del missing["segments"][0]["text"]
    _internal("research_fetch", missing)


def test_row2_legacy_window_fetch_is_refused() -> None:
    legacy = _legacy_fetch()
    assert "text" in legacy and "window" in legacy and "text_sha256" in legacy
    _internal("research_fetch", legacy)


def test_row2_non_full_text_empty_segments_pass() -> None:
    assert "coverage_state" in c.OUTPUT_SCHEMAS["research_fetch"]["properties"]
    result = _fetch_result(segments=[], total=0, coverage_state="NO_TEXT_LAYER", text_layer_state=None)
    assert result["segments"] == []
    assert result["segment_count_total"] == 0
    assert result["next_segment_start"] is None
    c.validate_output("research_fetch", result)


def test_row3_candidate_is_six_fields() -> None:
    props = c.OUTPUT_SCHEMAS["research_search"]["properties"]["candidates"]["items"]["properties"]
    assert list(props) == _CANDIDATE_KEYS
    result = _search_result()
    result["candidates"][0]["published_at"] = ""
    result["candidates"][0]["side"] = ""
    c.validate_output("research_search", result)
    for field, value in (
        ("tickers", ["AAPL"]),
        ("text_layer", "full"),
        ("rio_state", "CURRENT"),
        ("published_date", "2026-10-07"),
    ):
        broken = _search_result()
        broken["candidates"][0][field] = value
        _internal("research_search", broken)


def test_row3_legacy_candidate_fields_are_refused() -> None:
    _internal("research_search", _legacy_search())


def test_row4_non_ascii_byte_passage_passes_and_char_span_is_refused() -> None:
    _require_v11_passage_schema()
    non_ascii = _found_passages()[1]
    assert len(non_ascii["passage_text"].encode("utf-8")) != len(non_ascii["passage_text"])
    c.validate_output("research_find_evidence", _evidence_result("FOUND", [non_ascii]))
    char_sized = copy.deepcopy(non_ascii)
    char_sized["byte_end"] = char_sized["byte_start"] + len(char_sized["passage_text"])
    _internal("research_find_evidence", _evidence_result("FOUND", [char_sized]))
    with_char_keys = copy.deepcopy(non_ascii)
    with_char_keys["char_start"] = 0
    with_char_keys["char_end"] = 2
    _internal("research_find_evidence", _evidence_result("FOUND", [with_char_keys]))


def test_row4_legacy_char_offsets_are_refused() -> None:
    passage = _legacy_passage()
    assert passage["char_end"] - passage["char_start"] == len(passage["passage_text"])
    _internal("research_find_evidence", _evidence_result("FOUND", [passage]))


def test_row4_missing_fields_and_wrong_passage_hash_are_refused() -> None:
    _require_v11_passage_schema()
    missing_canonical = _found_passages()[1]
    del missing_canonical["canonical_text_sha256"]
    _internal("research_find_evidence", _evidence_result("FOUND", [missing_canonical]))
    missing_segment = _found_passages()[1]
    del missing_segment["segment_index"]
    _internal("research_find_evidence", _evidence_result("FOUND", [missing_segment]))
    wrong_hash = _found_passages()[1]
    wrong_hash["text_sha256"] = "ab" * 32
    assert wrong_hash["text_sha256"] != _sha256(wrong_hash["passage_text"].encode("utf-8"))
    _internal("research_find_evidence", _evidence_result("FOUND", [wrong_hash]))


def test_row5_status_shape_ratios_and_degradation() -> None:
    status = c.OUTPUT_SCHEMAS["research_status"]["properties"]
    assert list(status) == _STATUS_KEYS
    assert list(status["catalog"]["properties"]) == ["report_count"]
    assert list(status["coverage"]["properties"]) == ["full_text_ratio", "rio_ratio"]
    assert list(status["generation"]["properties"]) == [
        "server_contract",
        "read_port_contract",
        "mastermind_commit",
    ]
    read_port = status["generation"]["properties"]["read_port_contract"]
    assert read_port == {"type": "string", "minLength": 1, "maxLength": 120}
    assert "const" not in read_port
    c.validate_output("research_status", _status_result())
    empty = _status_result()
    assert empty["degradation"] == []
    c.validate_output("research_status", empty)
    every_code = _status_result()
    every_code["degradation"] = list(c.DEGRADATION_CODES)
    c.validate_output("research_status", every_code)
    for value in ("x", "y" * 120, "research_vault.read_status.v1"):
        projected = _status_result()
        projected["generation"]["read_port_contract"] = value
        c.validate_output("research_status", projected)
    removed = (
        ("catalog", "institution_count", 1),
        ("catalog", "newest_report_date", "2026-10-07"),
        ("catalog", "oldest_report_date", None),
        ("coverage", "text_layer_ok", 1),
        ("coverage", "text_layer_missing", 0),
        ("coverage", "rio_available", 1),
        ("generation", "macro_commit", "a" * 40),
    )
    for parent, field, value in removed:
        broken = _status_result()
        broken[parent][field] = value
        _internal("research_status", broken)
    unknown = _status_result()
    unknown["degradation"] = ["NOT_A_CODE"]
    _internal("research_status", unknown)
    duplicate = _status_result()
    duplicate["degradation"] = ["PRODUCER_STALE", "PRODUCER_STALE"]
    _internal("research_status", duplicate)
    ratio = _status_result()
    ratio["coverage"]["full_text_ratio"] = 1.01
    _internal("research_status", ratio)
    rio_ratio = _status_result()
    rio_ratio["coverage"]["rio_ratio"] = 1.01
    _internal("research_status", rio_ratio)


def test_row5_legacy_status_counts_are_refused() -> None:
    _internal("research_status", _legacy_status())


def test_row6_evidence_outcomes_are_the_closed_four() -> None:
    assert c.EVIDENCE_OUTCOMES == ("FOUND", "NOT_FOUND", "UNAVAILABLE", "PARTIAL")
    outcome = c.OUTPUT_SCHEMAS["research_find_evidence"]["properties"]["outcome"]
    assert outcome["enum"] == list(c.EVIDENCE_OUTCOMES)
    _internal("research_find_evidence", _evidence_result("MAYBE", []))


def test_row7_passage_byte_span_must_match_utf8_length() -> None:
    _require_v11_passage_schema()
    passage = _passage("ab", 0)
    passage["byte_end"] = passage["byte_start"] + len(passage["passage_text"].encode("utf-8")) + 1
    _internal("research_find_evidence", _evidence_result("FOUND", [passage]))


def test_row7_quote_limit_refuses_without_trimming_or_mutating() -> None:
    _require_v11_passage_schema()
    passage = _passage("q" * 10, 0)
    evidence = _evidence_result("FOUND", [passage])
    snapshot = copy.deepcopy(evidence)
    c.validate_output("research_find_evidence", evidence, quote_limit_chars=10)
    assert evidence == snapshot
    _internal("research_find_evidence", evidence, quote_limit_chars=9)
    assert evidence == snapshot
    assert passage["passage_text"] == "q" * 10


def test_row7_segment_index_must_be_consecutive() -> None:
    _require_v11_fetch_schema()
    segments = [_segment(0, "ab", 0), _segment(2, "cd", 2)]
    _internal("research_fetch", _fetch_result(segments=segments, total=3))


def test_row7_adjacent_segments_must_be_byte_contiguous() -> None:
    _require_v11_fetch_schema()
    gap = [_segment(0, "ab", 0), _segment(1, "cd", 4)]
    _internal("research_fetch", _fetch_result(segments=gap, total=2))
    overlap = [_segment(0, "ab", 0), _segment(1, "cd", 1)]
    _internal("research_fetch", _fetch_result(segments=overlap, total=2))


def test_row7_next_segment_start_must_follow_when_more_remain() -> None:
    _require_v11_fetch_schema()
    result = _fetch_result(text="ab", total=3)
    assert result["next_segment_start"] == 1
    result["next_segment_start"] = 0
    _internal("research_fetch", result)


def test_row7_next_segment_start_must_be_null_when_done() -> None:
    _require_v11_fetch_schema()
    result = _fetch_result(text="ab")
    assert result["next_segment_start"] is None
    result["next_segment_start"] = 1
    _internal("research_fetch", result)


def test_row7_non_full_text_cannot_carry_segments() -> None:
    _require_v11_fetch_schema()
    _internal("research_fetch", _fetch_result(text="ab", coverage_state="PREFIX_ONLY_LEGACY"))


def test_row7_segment_index_must_be_below_total() -> None:
    _require_v11_fetch_schema()
    result = _fetch_result(text="ab")
    result["segments"][0]["segment_index"] = 1
    result["segment_count_total"] = 1
    result["next_segment_start"] = None
    _internal("research_fetch", result)


def test_row7_page_start_must_not_exceed_page_end() -> None:
    _require_v11_fetch_schema()
    result = _fetch_result()
    result["segments"][0]["page_start"] = 3
    result["segments"][0]["page_end"] = 2
    _internal("research_fetch", result)


def test_row7_page_bounds_must_be_both_null_or_both_int() -> None:
    _require_v11_fetch_schema()
    start_only = _fetch_result()
    start_only["segments"][0]["page_end"] = None
    _internal("research_fetch", start_only)
    end_only = _fetch_result()
    end_only["segments"][0]["page_start"] = None
    _internal("research_fetch", end_only)


def test_row7_segment_over_segment_max_bytes_is_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_v11_fetch_schema()
    monkeypatch.setattr(c, "SEGMENT_MAX_BYTES", 4)
    _internal("research_fetch", _fetch_result(text="hello"))


def test_row7_total_over_fetch_max_text_bytes_is_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _require_v11_fetch_schema()
    monkeypatch.setattr(c, "FETCH_MAX_TEXT_BYTES", 5)
    segments = [_segment(0, "abc", 0), _segment(1, "def", 3)]
    _internal("research_fetch", _fetch_result(segments=segments, total=2))


def test_v1_1_schemas_carry_no_v1_field_names() -> None:
    found: set[str] = set()
    for schema in [*c.INPUT_SCHEMAS.values(), *c.OUTPUT_SCHEMAS.values()]:
        _schema_keys(schema, found)
    assert found.isdisjoint(_BANNED_V1_KEYS)
    source = Path(c.__file__).read_text(encoding="utf-8")
    for name in ("char_start", "char_end", "cursor", "max_chars", "tickers", "text_layer_ok"):
        assert name not in source
