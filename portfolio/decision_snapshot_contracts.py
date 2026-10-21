"""Closed evidence contracts for Portfolio V3; a seal grants no decision authority.

A digest proves content identity, not authenticity, data rights, market accuracy,
or complete opportunity coverage. Clocks are caller/source facts, never inferred.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from control_plane.wake_events import canonical_json_bytes

SNAPSHOT_SCHEMA = "mastermind.portfolio_decision_snapshot.v1"
SOURCE_RECEIPT_SCHEMA = "mastermind.portfolio_source_receipt.v1"
SECTION_SCHEMA = "mastermind.portfolio_snapshot_section.v1"
SNAPSHOT_STATES = frozenset({"COMPLETE", "PARTIAL", "BLOCKED", "INVALID", "CORRECTED_GENERATION_AVAILABLE"})
COVERAGE_STATES = frozenset({"COMPLETE", "PARTIAL", "BLOCKED", "UNKNOWN"})
SOURCE_STATUSES = frozenset({"AVAILABLE", "ABSENT_OPTIONAL", "MISSING", "MALFORMED", "OVERSIZE", "FUTURE_AT_CUTOFF", "UNQUALIFIED_CLOCK", "DEPENDENCY_PARTIAL", "RIGHTS_BLOCKED", "INVALID"})
SECTION_IDS = ("book_truth", "risk_truth", "market_structure", "independence", "factor_risk", "candidate_geometry", "relationships", "fundamental_state", "positioning", "priceability", "event_state", "historical_memory")
MAX_SNAPSHOT_BYTES = 262_144
MAX_SECTION_RESPONSE_BYTES = 65_536
MAX_SECTION_ROWS = 100
MAX_SOURCE_BYTES = 8_388_608
MAX_JSONL_TAIL_ROWS = 100

_ROOT_KEYS = frozenset({"schema", "book", "decision_cutoff", "recorded_at", "state", "coverage_state", "summary", "source_generation_set", "sources", "sections", "gaps", "correction", "authority"})
_RECEIPT_KEYS = frozenset({"schema", "source_id", "domains", "producer", "owner", "artifact", "source_schema", "schema_version", "definition_id", "artifact_digest", "observed_at", "known_at", "as_of", "generated_at", "filesystem_observed_at", "correction_generation", "freshness_state", "coverage_state", "rights_class", "authority_class", "status", "required", "bytes", "rows_total", "rows_returned", "omitted_rows", "clock_basis", "error_code"})
_SECTION_KEYS = frozenset({"schema", "section_id", "coverage_state", "source_ids", "rows_total", "rows_returned", "omitted_rows", "rows", "gaps"})
_SUMMARY_KEYS = frozenset({"sources_total", "sources_available", "domains_complete", "domains_partial", "domains_blocked"})
_AUTHORITY_KEYS = frozenset({"write_permitted", "execution_authority", "numeric_target_authority"})
_AUTHORITY_CLASSES = frozenset({"BOOK_STATE", "MARKET_RISK_CONTEXT", "CONTEXT_ONLY", "MEASUREMENT_ONLY", "DISPLAY_ONLY"})
_RIGHTS_CLASSES = frozenset({"FIRST_PARTY_INTERNAL", "LICENSED_INTERNAL", "UNKNOWN", "BLOCKED"})
_CLOCK_BASES = frozenset({"FILE_MTIME_FIRST_PARTY_STATE", "DECLARED_SOURCE_FIELD", "UNQUALIFIED_EXTERNAL_CLOCK", "UNKNOWN"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class DecisionSnapshotContractError(ValueError):
    """The value is not a closed, bounded, non-authoritative snapshot."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DecisionSnapshotContractError(message)


def _keys(value: Any, expected: frozenset[str], field: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{field} must be an object")
    actual = set(value)
    _require(not (actual - expected), f"{field}: unknown fields")
    _require(not (expected - actual), f"{field}: missing fields")
    return value


def _text(value: Any, field: str, *, nullable: bool = False, limit: int = 2048) -> None:
    if value is None and nullable:
        return
    _require(isinstance(value, str) and 0 < len(value) <= limit, f"{field} must be bounded nonempty text")


def _enum(value: Any, allowed: frozenset[str] | tuple[str, ...], field: str) -> None:
    _require(isinstance(value, str) and value in allowed, f"invalid {field}")


def _count(value: Any, field: str) -> None:
    _require(type(value) is int and 0 <= value <= 2**53 - 1, f"{field} must be a nonnegative integer")


def _digest(value: Any, field: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    _require(isinstance(value, str) and _DIGEST.fullmatch(value) is not None, f"invalid {field} digest")


def _unique_strings(value: Any, field: str, *, nonempty: bool = False) -> None:
    _require(isinstance(value, list), f"{field} must be a list")
    _require(all(isinstance(item, str) and item for item in value), f"invalid {field}")
    _require(len(value) == len(set(value)), f"duplicate {field}")
    _require(not nonempty or bool(value), f"empty {field}")


def _json_bytes(value: Any, *, limit: int = MAX_SNAPSHOT_BYTES) -> bytes:
    # Bound nesting and object size before handing values to the canonical owner.
    stack = [(value, 0)]
    visited = 0
    text_characters = 0
    while stack:
        item, depth = stack.pop()
        visited += 1
        _require(depth <= 24 and visited <= 50_000, "JSON structure exceeds limit")
        if isinstance(item, Mapping):
            _require(all(isinstance(k, str) for k in item), "JSON object keys must be strings")
            _require(len(item) <= 10_000, "JSON object exceeds limit")
            stack.extend((k, depth + 1) for k in item)
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            _require(len(item) <= 10_000, "JSON list exceeds limit")
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            text_characters += len(item)
            _require(text_characters <= limit, "JSON aggregate text exceeds limit")
        elif type(item) is float:
            _require(math.isfinite(item), "JSON number must be finite")
        else:
            _require(item is None or type(item) in (bool, int), "unsupported JSON value")
    try:
        encoded = canonical_json_bytes(value)
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise DecisionSnapshotContractError("invalid canonical JSON") from exc
    _require(len(encoded) <= limit, f"JSON exceeds {limit}-byte limit")
    return encoded


def parse_utc_timestamp(value: str, *, field: str) -> str:
    _text(value, field, limit=64)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(stamp.tzinfo is not None and stamp.utcoffset() is not None, f"{field} must be timezone aware")
        _require(stamp.microsecond == 0, f"{field} has unsupported subsecond precision")
        return stamp.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, OverflowError) as exc:
        raise DecisionSnapshotContractError(f"invalid {field} timestamp") from exc


def _clock(value: Any, field: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    _require(parse_utc_timestamp(value, field=field) == value, f"{field} must be canonical UTC")


def content_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json_bytes(value)).hexdigest()


def _rows(value: Mapping[str, Any], field: str, *, materialized: bool) -> None:
    for key in ("rows_total", "rows_returned", "omitted_rows"):
        _count(value[key], f"{field}.{key}")
    _require(value["rows_total"] == value["rows_returned"] + value["omitted_rows"], f"{field} row counts disagree")
    _require(value["rows_returned"] <= MAX_SECTION_ROWS, f"{field} exceeds row limit")
    if materialized:
        _require(isinstance(value["rows"], list), f"{field}.rows must be a list")
        _require(len(value["rows"]) == value["rows_returned"], f"{field} materialized row count disagrees")
        _require(all(isinstance(row, Mapping) for row in value["rows"]), f"{field} rows must be objects")


def validate_source_receipt(receipt: Mapping[str, Any]) -> None:
    r = _keys(receipt, _RECEIPT_KEYS, "source")
    _require(r["schema"] == SOURCE_RECEIPT_SCHEMA, "invalid source schema")
    for key in ("source_id", "producer", "owner", "artifact"):
        _text(r[key], f"source.{key}")
    _require(_IDENTIFIER.fullmatch(r["source_id"]) is not None, "invalid source identity")
    for key in ("source_schema", "schema_version", "definition_id", "as_of", "error_code"):
        _text(r[key], f"source.{key}", nullable=True)
    _unique_strings(r["domains"], "source.domains", nonempty=True)
    for domain in r["domains"]:
        _enum(domain, SECTION_IDS, "source domain")
    for key in ("artifact_digest", "correction_generation"):
        _digest(r[key], key, nullable=True)
    for key in ("observed_at", "known_at", "generated_at", "filesystem_observed_at"):
        _clock(r[key], key, nullable=True)
    _enum(r["freshness_state"], ("FRESH", "STALE", "UNKNOWN"), "freshness")
    _enum(r["coverage_state"], COVERAGE_STATES, "source coverage")
    _enum(r["status"], SOURCE_STATUSES, "source status")
    _enum(r["authority_class"], _AUTHORITY_CLASSES, "source authority")
    _enum(r["rights_class"], _RIGHTS_CLASSES, "source rights")
    _enum(r["clock_basis"], _CLOCK_BASES, "clock basis")
    _require(type(r["required"]) is bool, "source.required must be boolean")
    _count(r["bytes"], "source.bytes")
    _rows(r, "source", materialized=False)
    if r["status"] == "AVAILABLE":
        _digest(r["artifact_digest"], "artifact_digest")
        _digest(r["correction_generation"], "correction_generation")
        _require(r["known_at"] is not None and r["clock_basis"] in {"FILE_MTIME_FIRST_PARTY_STATE", "DECLARED_SOURCE_FIELD"}, "available source needs a qualified clock")
        _require(r["rights_class"] in {"FIRST_PARTY_INTERNAL", "LICENSED_INTERNAL"}, "available source needs qualified rights")
        _require(r["bytes"] <= MAX_SOURCE_BYTES, "available source exceeds byte limit")
        _require(r["error_code"] is None, "available source has an error")
    if r["coverage_state"] == "COMPLETE":
        _require(r["status"] == "AVAILABLE" and r["freshness_state"] == "FRESH" and r["omitted_rows"] == 0, "complete source must be fresh, available and untruncated")
    if r["status"] == "ABSENT_OPTIONAL":
        _require(r["required"] is False, "required source cannot be absent optional")
    _json_bytes(r, limit=MAX_SECTION_RESPONSE_BYTES)


def validate_section(section: Mapping[str, Any]) -> None:
    s = _keys(section, _SECTION_KEYS, "section")
    _require(s["schema"] == SECTION_SCHEMA, "invalid section schema")
    _enum(s["section_id"], SECTION_IDS, "section identity")
    _enum(s["coverage_state"], COVERAGE_STATES, "section coverage")
    _unique_strings(s["source_ids"], "section source identities")
    _rows(s, "section", materialized=True)
    _require(isinstance(s["gaps"], list), "section gaps must be a list")
    if s["coverage_state"] == "COMPLETE":
        _require(bool(s["source_ids"]) and not s["gaps"] and s["omitted_rows"] == 0, "complete section cannot omit evidence")
    _json_bytes(s, limit=MAX_SECTION_RESPONSE_BYTES)


def validate_unsealed_snapshot(snapshot: Mapping[str, Any]) -> None:
    p = _keys(snapshot, _ROOT_KEYS, "snapshot")
    _require(p["schema"] == SNAPSHOT_SCHEMA and p["book"] == "autonomous", "invalid snapshot schema or book")
    _clock(p["decision_cutoff"], "decision_cutoff")
    _clock(p["recorded_at"], "recorded_at")
    _require(p["recorded_at"] >= p["decision_cutoff"], "recording precedes decision cutoff")
    _enum(p["state"], SNAPSHOT_STATES, "snapshot state")
    _enum(p["coverage_state"], COVERAGE_STATES, "snapshot coverage")
    authority = _keys(p["authority"], _AUTHORITY_KEYS, "authority")
    _require(all(value is False for value in authority.values()), "snapshot authority must be false")
    summary = _keys(p["summary"], _SUMMARY_KEYS, "summary")
    for key, value in summary.items():
        _count(value, f"summary.{key}")
    _require(isinstance(p["sources"], list), "sources must be a list")
    by_id: dict[str, Mapping[str, Any]] = {}
    for r in p["sources"]:
        validate_source_receipt(r)
        _require(r["source_id"] not in by_id, "duplicate source identity")
        by_id[r["source_id"]] = r
        if r["status"] == "AVAILABLE":
            _require(r["known_at"] <= p["decision_cutoff"], "available source is future at cutoff")
            if r["generated_at"] is not None:
                _require(r["generated_at"] <= p["decision_cutoff"], "available source generation is future at cutoff")
        if r["filesystem_observed_at"] is not None:
            _require(r["filesystem_observed_at"] <= p["recorded_at"], "source observation is after recording")
    _require(isinstance(p["source_generation_set"], list), "generation set must be a list")
    generations: dict[str, Any] = {}
    for g in p["source_generation_set"]:
        _keys(g, frozenset({"source_id", "correction_generation"}), "generation")
        _text(g["source_id"], "generation.source_id")
        _require(g["source_id"] not in generations, "duplicate generation identity")
        _digest(g["correction_generation"], "generation", nullable=True)
        generations[g["source_id"]] = g["correction_generation"]
    _require(generations == {sid: r["correction_generation"] for sid, r in by_id.items()}, "source generation set disagrees")
    _require(isinstance(p["sections"], Mapping) and bool(p["sections"]), "sections must be a nonempty object")
    states: list[str] = []
    for section_id, s in p["sections"].items():
        _enum(section_id, SECTION_IDS, "section key")
        validate_section(s)
        _require(section_id == s["section_id"], "section identity disagrees with key")
        states.append(s["coverage_state"])
        for sid in s["source_ids"]:
            _require(sid in by_id and section_id in by_id[sid]["domains"], "section source/domain reference disagrees")
            if s["coverage_state"] == "COMPLETE":
                _require(by_id[sid]["coverage_state"] == "COMPLETE", "complete section references partial source")
    expected_summary = {"sources_total": len(by_id), "sources_available": sum(r["status"] == "AVAILABLE" for r in by_id.values()), "domains_complete": states.count("COMPLETE"), "domains_partial": states.count("PARTIAL") + states.count("UNKNOWN"), "domains_blocked": states.count("BLOCKED")}
    _require(dict(summary) == expected_summary, "summary disagrees with evidence")
    _require(isinstance(p["gaps"], list), "snapshot gaps must be a list")
    if p["coverage_state"] == "COMPLETE":
        _require(all(state == "COMPLETE" for state in states) and not p["gaps"], "complete snapshot hides gaps")
        _require(all(r["coverage_state"] == "COMPLETE" or r["status"] == "ABSENT_OPTIONAL" for r in by_id.values()), "complete snapshot hides an unqualified source")
    if p["state"] == "COMPLETE":
        _require(p["coverage_state"] == "COMPLETE", "complete state disagrees with coverage")
    if p["state"] == "PARTIAL":
        _require(p["coverage_state"] in {"PARTIAL", "UNKNOWN"}, "partial state disagrees with coverage")
    if p["state"] == "BLOCKED":
        _require(p["coverage_state"] == "BLOCKED", "blocked state disagrees with coverage")
    correction = _keys(p["correction"], frozenset({"status", "same_cutoff_prior_snapshot_ids"}), "correction")
    _enum(correction["status"], ("ORIGINAL", "CORRECTED_GENERATION_AVAILABLE"), "correction status")
    prior = correction["same_cutoff_prior_snapshot_ids"]
    _unique_strings(prior, "correction predecessors")
    for value in prior:
        _digest(value, "predecessor")
    corrected = correction["status"] == "CORRECTED_GENERATION_AVAILABLE"
    _require(corrected == bool(prior) and corrected == (p["state"] == "CORRECTED_GENERATION_AVAILABLE"), "correction state disagrees")
    _json_bytes(p)


def seal_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_unsealed_snapshot(snapshot)
    sealed = json.loads(_json_bytes(snapshot))
    sealed["snapshot_id"] = content_digest(snapshot)
    validate_snapshot(sealed)
    return sealed


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    p = _keys(snapshot, _ROOT_KEYS | {"snapshot_id"}, "sealed snapshot")
    _digest(p["snapshot_id"], "snapshot_id")
    validate_unsealed_snapshot({key: value for key, value in p.items() if key != "snapshot_id"})
    _require(p["snapshot_id"] not in p["correction"]["same_cutoff_prior_snapshot_ids"], "snapshot cannot precede itself")
    _json_bytes(p)


def verify_snapshot(snapshot: Mapping[str, Any]) -> None:
    validate_snapshot(snapshot)
    unsealed = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    _require(content_digest(unsealed) == snapshot["snapshot_id"], "snapshot digest mismatch")
