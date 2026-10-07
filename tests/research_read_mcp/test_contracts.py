"""Closed Research Read MCP contract tests. No network, store, or server."""
from __future__ import annotations

import ast
import copy
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
        "Read one window of a report's extracted text by report_id; use next_cursor to continue."
    ),
    "research_find_evidence": (
        "Find literal passages in research reports that bear on a claim. "
        "Each passage is an exact substring of the extracted text with offsets and a hash."
    ),
}
OPTIONAL_INPUTS = {
    "research_status": set(),
    "research_search": {"institution", "from", "to", "limit"},
    "research_fetch": {"cursor", "max_chars"},
    "research_find_evidence": {"report_ids", "limit"},
}
SHA = "ab" * 32
MACRO_COMMIT = "a" * 40
MASTERMIND_COMMIT = "b" * 40
CANONICAL = "Institutional demand remains concentrated in the front end of the curve."


def _invalid(tool: str, arguments: object) -> None:
    with pytest.raises(c.ContractViolation) as caught:
        c.validate_arguments(tool, arguments)
    assert caught.value.code == "INVALID_REQUEST"


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
        "published_date": "2026-10-07",
        "tickers": ["AAPL", "BRK.B"],
        "text_layer": "FULL_TEXT",
        "rio_state": "CURRENT",
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
            "read_port_contract": "research.vault.read_port.v1",
            "macro_commit": MACRO_COMMIT,
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


def _fetch_result(*, truncated: bool, text: str = "hello", total: int | None = None) -> dict:
    start = 0
    end = len(text)
    total_chars = end + (5 if truncated else 0) if total is None else total
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
            "start": start,
            "end": end,
            "total_chars": total_chars,
            "truncated": truncated,
            "next_cursor": end if truncated else None,
        },
        "text_sha256": SHA,
        "rio_state": "CURRENT",
    }


def _passage(text: str, start: int, report_id: str = "abc-1") -> dict:
    return {
        "report_id": report_id,
        "passage_text": text,
        "char_start": start,
        "char_end": start + len(text),
        "text_sha256": SHA,
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
    first = CANONICAL[0:13]
    second = CANONICAL[14:20]
    assert first == CANONICAL[0:13]
    assert second == CANONICAL[14:20]
    return [_passage(first, 0), _passage(second, 14, report_id="abc-2")]


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
    length_mismatch["passages"][0]["char_end"] = 1
    same_offset = _evidence_result("FOUND", [_passage("ab", 4)])
    same_offset["passages"][0]["char_end"] = same_offset["passages"][0]["char_start"]
    long_passage = _evidence_result("FOUND", [_passage("p" * 1201, 0)])
    quote_passage = _evidence_result("FOUND", [_passage("q" * 101, 0)])
    fetch = _fetch_result(truncated=True)
    bad_length = copy.deepcopy(fetch)
    bad_length["text"] = "hell"
    bad_truncated = copy.deepcopy(fetch)
    bad_truncated["window"]["truncated"] = False
    bad_truncated["window"]["next_cursor"] = None
    bad_cursor = copy.deepcopy(fetch)
    bad_cursor["window"]["next_cursor"] = 0
    bad_total = copy.deepcopy(fetch)
    bad_total["window"]["total_chars"] = 1
    bad_total["window"]["truncated"] = False
    bad_total["window"]["next_cursor"] = None
    huge_text = _fetch_result(truncated=False, text="x" * 12001, total=12001)
    status = _status_result()
    bad_server = copy.deepcopy(status)
    bad_server["generation"]["server_contract"] = "other"
    bad_macro = copy.deepcopy(status)
    bad_macro["generation"]["macro_commit"] = "a" * 39
    bad_mastermind = copy.deepcopy(status)
    bad_mastermind["generation"]["mastermind_commit"] = ("b" * 40) + "\n"
    bad_license = _fetch_result(truncated=False)
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
        ("fetch_window_length_mismatch", "research_fetch", bad_length, {}),
        ("fetch_truncated_inconsistent", "research_fetch", bad_truncated, {}),
        ("fetch_next_cursor_inconsistent", "research_fetch", bad_cursor, {}),
        ("fetch_end_past_total", "research_fetch", bad_total, {}),
        ("fetch_text_12001", "research_fetch", huge_text, {}),
        ("status_server_contract_wrong", "research_status", bad_server, {}),
        ("status_macro_commit_39_hex", "research_status", bad_macro, {}),
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
    assert accepted["cursor"] == 0
    assert accepted["max_chars"] == 6000


def test_fetch_defaults_do_not_mutate_the_caller() -> None:
    original = {"report_id": "abc-1"}
    snapshot = copy.deepcopy(original)
    accepted = c.validate_arguments("research_fetch", original)
    assert accepted["cursor"] == 0
    assert accepted["max_chars"] == 6000
    assert original == snapshot
    explicit = {"report_id": "abc-1", "cursor": 4, "max_chars": 500}
    assert c.validate_arguments("research_fetch", explicit) == explicit
    assert explicit == {"report_id": "abc-1", "cursor": 4, "max_chars": 500}


@pytest.mark.parametrize("cursor", [-1, 2000001])
def test_fetch_cursor_rejects_outside_closed_range(cursor: int) -> None:
    _invalid("research_fetch", {"report_id": "abc-1", "cursor": cursor})


@pytest.mark.parametrize("cursor", [0, 2000000])
def test_fetch_cursor_accepts_closed_range(cursor: int) -> None:
    assert c.validate_arguments("research_fetch", {"report_id": "abc-1", "cursor": cursor})["cursor"] == cursor


@pytest.mark.parametrize("max_chars", [499, 12001])
def test_fetch_max_chars_rejects_outside_closed_range(max_chars: int) -> None:
    _invalid("research_fetch", {"report_id": "abc-1", "max_chars": max_chars})


@pytest.mark.parametrize("max_chars", [500, 12000])
def test_fetch_max_chars_accepts_closed_range(max_chars: int) -> None:
    assert c.validate_arguments(
        "research_fetch", {"report_id": "abc-1", "max_chars": max_chars}
    )["max_chars"] == max_chars


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


def test_valid_outputs_pass_including_windows_ranks_and_literal_passages() -> None:
    c.validate_output("research_status", _status_result())
    search = _search_result()
    c.validate_output("research_search", search)
    assert [item["rank"] for item in search["candidates"]] == [1, 2]
    truncated = _fetch_result(truncated=True)
    whole = _fetch_result(truncated=False)
    c.validate_output("research_fetch", truncated)
    c.validate_output("research_fetch", whole)
    assert truncated["window"]["next_cursor"] == len(truncated["text"])
    assert whole["window"]["next_cursor"] is None
    passages = _found_passages()
    assert passages[0]["passage_text"] == CANONICAL[passages[0]["char_start"]:passages[0]["char_end"]]
    assert passages[1]["passage_text"] == CANONICAL[passages[1]["char_start"]:passages[1]["char_end"]]
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
    fetch = _fetch_result(truncated=False, text="文" * 12000, total=12000)
    passages = [
        _passage("证" * 1200, index * 1200, report_id=f"report-{index}")
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
    assert c.TEXT_LAYER_STATES == (
        "FULL_TEXT",
        "PREFIX_ONLY_LEGACY",
        "NO_TEXT_LAYER",
        "EXTRACTION_UNAVAILABLE",
        "SEGMENT_INDEX_PENDING",
        "PARTIAL_CORPUS",
        "SOURCE_REVISION_CHANGED",
    )
    assert c.RIO_STATES == ("CURRENT", "MISSING", "STALE", "INVALID", "NOT_REQUESTED")
    assert c.EVIDENCE_OUTCOMES == ("FOUND", "NOT_FOUND", "UNAVAILABLE", "PARTIAL")
    source = Path(c.__file__).read_text(encoding="utf-8")
    assert "read_port.py:30-49 @ 00efb3621a6e" in source
    assert CONTRACT == "mastermind.research_read_mcp.v1"
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
    candidate = c.OUTPUT_SCHEMAS["research_search"]["properties"]["candidates"]["items"]
    assert candidate["properties"]["text_layer"]["enum"] == list(c.TEXT_LAYER_STATES)
    assert candidate["properties"]["rio_state"]["enum"] == list(c.RIO_STATES)
    assert c.OUTPUT_SCHEMAS["research_fetch"]["properties"]["rio_state"]["enum"] == list(c.RIO_STATES)
    assert evidence["properties"]["rio_state"]["enum"] == list(c.RIO_STATES)
    assert evidence["properties"]["outcome"]["enum"] == list(c.EVIDENCE_OUTCOMES)


def test_contract_modules_import_only_the_allowlisted_modules() -> None:
    allowed = {
        "__future__",
        "copy",
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
