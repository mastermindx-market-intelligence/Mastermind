"""portfolio.decision_snapshot_contracts — closed V3 Decision Snapshot contract.

Pure schemas, vocabularies, UTC parsing, digesting, sealing, and validation for the
S0 Decision Snapshot. No filesystem, clock, network, model, or Portfolio-state
imports — reuses control_plane.wake_events.canonical_json_bytes as the single
canonical JSON serializer.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from control_plane.wake_events import canonical_json_bytes

SNAPSHOT_SCHEMA = "mastermind.portfolio_decision_snapshot.v1"
SOURCE_RECEIPT_SCHEMA = "mastermind.portfolio_source_receipt.v1"
SECTION_SCHEMA = "mastermind.portfolio_snapshot_section.v1"

SNAPSHOT_STATES = frozenset({
    "COMPLETE",
    "PARTIAL",
    "BLOCKED",
    "INVALID",
    "CORRECTED_GENERATION_AVAILABLE",
})
COVERAGE_STATES = frozenset({"COMPLETE", "PARTIAL", "BLOCKED", "UNKNOWN"})
SOURCE_STATUSES = frozenset({
    "AVAILABLE",
    "ABSENT_OPTIONAL",
    "MISSING",
    "MALFORMED",
    "OVERSIZE",
    "FUTURE_AT_CUTOFF",
    "UNQUALIFIED_CLOCK",
    "DEPENDENCY_PARTIAL",
    "RIGHTS_BLOCKED",
    "INVALID",
})
SECTION_IDS = (
    "book_truth",
    "risk_truth",
    "market_structure",
    "independence",
    "factor_risk",
    "candidate_geometry",
    "relationships",
    "fundamental_state",
    "positioning",
    "priceability",
    "event_state",
    "historical_memory",
)

FRESHNESS_STATES = frozenset({"FRESH", "STALE", "UNKNOWN"})
RIGHTS_CLASSES = frozenset({"FIRST_PARTY_INTERNAL", "MACRO_VENDORED"})
AUTHORITY_CLASSES = frozenset({
    "BOOK_STATE",
    "RISK_STATE",
    "MARKET_CONTEXT",
    "MARKET_RISK_CONTEXT",
    "CONTEXT_ONLY",
    "MEASUREMENT_ONLY",
    "DISPLAY_ONLY",
})
CLOCK_BASES = frozenset({
    "FILE_MTIME_FIRST_PARTY_STATE",
    "SOURCE_DECLARED",
    "CALLER_SUPPLIED",
    "UNKNOWN",
    "DECLARED_SOURCE_FIELD",
    "UNQUALIFIED_EXTERNAL_CLOCK",
})
CORRECTION_STATUSES = frozenset({"ORIGINAL", "CORRECTED", "SUPERSEDED"})

MAX_SNAPSHOT_BYTES = 262_144
MAX_SECTION_RESPONSE_BYTES = 65_536
MAX_SECTION_ROWS = 100
MAX_SOURCE_BYTES = 8_388_608
MAX_JSONL_TAIL_ROWS = 100
# Ceiling on the total encoded filename metadata a single directory manifest may carry.
# Deliberately far below MAX_SOURCE_BYTES: a manifest is metadata about an unbounded
# directory, and an unbounded name census is not bounded capture.
MAX_MANIFEST_METADATA_BYTES = 65_536

# Clock bases that do not establish point-in-time knowledge of the source's content.
UNQUALIFIED_CLOCK_BASES = frozenset({"UNKNOWN", "UNQUALIFIED_EXTERNAL_CLOCK"})

_DIGEST_PREFIX = "sha256:"
_DIGEST_HEX_LEN = 64


class DecisionSnapshotContractError(ValueError):
    """Raised when a Decision Snapshot payload violates the closed contract."""


def _fail(message: str) -> None:
    raise DecisionSnapshotContractError(message)


def _require_keys(obj: Mapping[str, Any], required: frozenset, *, what: str) -> None:
    if not isinstance(obj, Mapping):
        _fail(f"{what} must be a mapping")
    actual = set(obj.keys())
    missing = required - actual
    if missing:
        _fail(f"{what} missing required field(s): {sorted(missing)}")
    unknown = actual - required
    if unknown:
        _fail(f"{what} has unknown field(s): {sorted(unknown)}")


def _require_str(obj: Mapping[str, Any], field: str, *, what: str) -> None:
    value = obj.get(field)
    if not isinstance(value, str) or not value:
        _fail(f"{what}.{field} must be a non-empty string")


def _require_str_or_none(obj: Mapping[str, Any], field: str, *, what: str) -> None:
    value = obj.get(field)
    if value is not None and not isinstance(value, str):
        _fail(f"{what}.{field} must be a string or null")


def _require_bool(obj: Mapping[str, Any], field: str, *, what: str) -> None:
    value = obj.get(field)
    if not isinstance(value, bool):
        _fail(f"{what}.{field} must be a boolean")


def _require_int(obj: Mapping[str, Any], field: str, *, what: str, minimum: int = 0) -> None:
    value = obj.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{what}.{field} must be an integer")
    if value < minimum:
        _fail(f"{what}.{field} must be >= {minimum}")


def _require_enum(obj: Mapping[str, Any], field: str, allowed: frozenset, *, what: str) -> None:
    value = obj.get(field)
    if value not in allowed:
        _fail(f"{what}.{field}={value!r} is not one of {sorted(allowed)}")


def _require_digest(value: Any, *, what: str) -> None:
    if (
        not isinstance(value, str)
        or not value.startswith(_DIGEST_PREFIX)
        or len(value) != len(_DIGEST_PREFIX) + _DIGEST_HEX_LEN
    ):
        _fail(f"{what} must be a 'sha256:' digest with 64 lowercase hex characters")
    hex_part = value[len(_DIGEST_PREFIX):]
    if any(ch not in "0123456789abcdef" for ch in hex_part):
        _fail(f"{what} must be lowercase hex")


def parse_utc_timestamp(value: str, *, field: str) -> str:
    """Normalize a timezone-aware ISO-8601 timestamp to second-precision UTC 'Z'."""
    if not isinstance(value, str) or not value:
        _fail(f"{field} must be a non-empty timezone-aware UTC timestamp string")
    text = value
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _fail(f"{field}={value!r} is not a valid ISO-8601 timestamp")
        raise  # pragma: no cover - _fail always raises
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        _fail(f"{field}={value!r} must be timezone-aware")
    from datetime import timezone as _timezone
    normalized = parsed.astimezone(_timezone.utc).replace(microsecond=0)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_canonical_utc(value: str, *, field: str) -> None:
    normalized = parse_utc_timestamp(value, field=field)
    if normalized != value:
        _fail(
            f"{field} must already be second-precision UTC 'Z' "
            f"(got {value!r}, expected {normalized!r})"
        )


def content_digest(value: Any) -> str:
    import hashlib
    return _DIGEST_PREFIX + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


_RECEIPT_FIELDS = frozenset({
    "schema",
    "source_id",
    "domains",
    "producer",
    "owner",
    "artifact",
    "source_schema",
    "schema_version",
    "definition_id",
    "artifact_digest",
    "observed_at",
    "known_at",
    "as_of",
    "generated_at",
    "filesystem_observed_at",
    "correction_generation",
    "freshness_state",
    "coverage_state",
    "rights_class",
    "authority_class",
    "status",
    "required",
    "bytes",
    "rows_total",
    "rows_returned",
    "omitted_rows",
    "clock_basis",
    "error_code",
})


def validate_source_receipt(receipt: Mapping[str, Any]) -> None:
    what = "source_receipt"
    _require_keys(receipt, _RECEIPT_FIELDS, what=what)
    if receipt.get("schema") != SOURCE_RECEIPT_SCHEMA:
        _fail(f"{what}.schema must equal {SOURCE_RECEIPT_SCHEMA!r}")
    _require_str(receipt, "source_id", what=what)
    domains = receipt.get("domains")
    if not isinstance(domains, list) or not domains or not all(isinstance(d, str) and d for d in domains):
        _fail(f"{what}.domains must be a non-empty list of strings")
    _require_str(receipt, "producer", what=what)
    _require_str(receipt, "owner", what=what)
    _require_str(receipt, "artifact", what=what)
    _require_str_or_none(receipt, "source_schema", what=what)
    _require_str_or_none(receipt, "schema_version", what=what)
    _require_str_or_none(receipt, "definition_id", what=what)
    _require_digest(receipt.get("artifact_digest"), what=f"{what}.artifact_digest")
    _require_str_or_none(receipt, "observed_at", what=what)
    _require_str_or_none(receipt, "known_at", what=what)
    _require_str_or_none(receipt, "as_of", what=what)
    _require_str_or_none(receipt, "generated_at", what=what)
    _require_str_or_none(receipt, "filesystem_observed_at", what=what)
    # as_of is a source-owned date, not a timestamp — it is never parsed here.
    _require_digest(receipt.get("correction_generation"), what=f"{what}.correction_generation")
    _require_enum(receipt, "freshness_state", FRESHNESS_STATES, what=what)
    _require_enum(receipt, "coverage_state", COVERAGE_STATES, what=what)
    _require_enum(receipt, "rights_class", RIGHTS_CLASSES, what=what)
    _require_enum(receipt, "authority_class", AUTHORITY_CLASSES, what=what)
    _require_enum(receipt, "status", SOURCE_STATUSES, what=what)
    _require_bool(receipt, "required", what=what)
    _require_int(receipt, "bytes", what=what)
    _require_int(receipt, "rows_total", what=what)
    _require_int(receipt, "rows_returned", what=what)
    _require_int(receipt, "omitted_rows", what=what)
    _require_enum(receipt, "clock_basis", CLOCK_BASES, what=what)
    _require_str_or_none(receipt, "error_code", what=what)
    for field in ("observed_at", "known_at", "generated_at", "filesystem_observed_at"):
        value = receipt.get(field)
        if value is not None:
            _require_canonical_utc(value, field=f"{what}.{field}")
    # AVAILABLE is a *point-in-time* claim: the snapshot asserts this source's content was
    # true as of a knowable instant at or before the decision cutoff. A null known_at or an
    # unqualified clock basis means no such instant is known, so the state may not be
    # AVAILABLE — it must degrade to UNQUALIFIED_CLOCK or another lawful status instead.
    if receipt.get("status") == "AVAILABLE":
        if receipt.get("known_at") is None:
            _fail(f"{what}.status=AVAILABLE requires a non-null known_at")
        if receipt.get("clock_basis") in UNQUALIFIED_CLOCK_BASES:
            _fail(
                f"{what}.status=AVAILABLE cannot rest on "
                f"clock_basis={receipt.get('clock_basis')!r}"
            )


_SECTION_FIELDS = frozenset({
    "schema",
    "section_id",
    "coverage_state",
    "source_ids",
    "rows_total",
    "rows_returned",
    "omitted_rows",
    "rows",
    "gaps",
})


def validate_section(section: Mapping[str, Any]) -> None:
    what = "section"
    _require_keys(section, _SECTION_FIELDS, what=what)
    if section.get("schema") != SECTION_SCHEMA:
        _fail(f"{what}.schema must equal {SECTION_SCHEMA!r}")
    _require_enum(section, "section_id", frozenset(SECTION_IDS), what=what)
    source_ids = section.get("source_ids")
    if not isinstance(source_ids, list) or not all(isinstance(s, str) and s for s in source_ids):
        _fail(f"{what}.source_ids must be a list of strings")
    _require_enum(section, "coverage_state", COVERAGE_STATES, what=what)
    _require_int(section, "rows_total", what=what)
    _require_int(section, "rows_returned", what=what)
    _require_int(section, "omitted_rows", what=what)
    rows = section.get("rows")
    if not isinstance(rows, list):
        _fail(f"{what}.rows must be a list")
    if len(rows) > MAX_SECTION_ROWS:
        _fail(f"{what}.rows exceeds {MAX_SECTION_ROWS}-row limit")
    gaps = section.get("gaps")
    if not isinstance(gaps, list) or not all(isinstance(g, str) for g in gaps):
        _fail(f"{what}.gaps must be a list of strings")


_SUMMARY_FIELDS = frozenset({
    "sources_total",
    "sources_available",
    "domains_complete",
    "domains_partial",
    "domains_blocked",
})

_GENERATION_ENTRY_FIELDS = frozenset({"source_id", "correction_generation"})

_CORRECTION_FIELDS = frozenset({"status", "same_cutoff_prior_snapshot_ids"})

_AUTHORITY_FIELDS = frozenset({
    "write_permitted",
    "execution_authority",
    "numeric_target_authority",
})

_ROOT_FIELDS = frozenset({
    "schema",
    "book",
    "decision_cutoff",
    "recorded_at",
    "state",
    "coverage_state",
    "summary",
    "source_generation_set",
    "sources",
    "sections",
    "gaps",
    "correction",
    "authority",
})

_SEALED_ROOT_FIELDS = _ROOT_FIELDS | {"snapshot_id"}


def _validate_summary(summary: Any) -> None:
    what = "summary"
    _require_keys(summary, _SUMMARY_FIELDS, what=what)
    for field in _SUMMARY_FIELDS:
        _require_int(summary, field, what=what)


def _validate_source_generation_set(entries: Any) -> None:
    what = "source_generation_set"
    if not isinstance(entries, list):
        _fail(f"{what} must be a list")
    for entry in entries:
        _require_keys(entry, _GENERATION_ENTRY_FIELDS, what=f"{what}[]")
        _require_str(entry, "source_id", what=f"{what}[]")
        _require_digest(entry.get("correction_generation"), what=f"{what}[].correction_generation")


def _validate_correction(correction: Any) -> None:
    what = "correction"
    _require_keys(correction, _CORRECTION_FIELDS, what=what)
    _require_enum(correction, "status", CORRECTION_STATUSES, what=what)
    ids = correction.get("same_cutoff_prior_snapshot_ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
        _fail(f"{what}.same_cutoff_prior_snapshot_ids must be a list of strings")


def _validate_authority(authority: Any) -> None:
    what = "authority"
    _require_keys(authority, _AUTHORITY_FIELDS, what=what)
    for field in _AUTHORITY_FIELDS:
        _require_bool(authority, field, what=what)
    if authority.get("write_permitted") is not False:
        _fail(f"{what}.write_permitted must be false")
    if authority.get("execution_authority") is not False:
        _fail(f"{what}.execution_authority must be false")
    if authority.get("numeric_target_authority") is not False:
        _fail(f"{what}.numeric_target_authority must be false")


def _validate_root(snapshot: Mapping[str, Any], *, fields: frozenset) -> None:
    what = "snapshot"
    _require_keys(snapshot, fields, what=what)
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        _fail(f"{what}.schema must equal {SNAPSHOT_SCHEMA!r}")
    _require_str(snapshot, "book", what=what)
    for field in ("decision_cutoff", "recorded_at"):
        _require_canonical_utc(snapshot.get(field), field=field)
    _require_enum(snapshot, "state", SNAPSHOT_STATES, what=what)
    _require_enum(snapshot, "coverage_state", COVERAGE_STATES, what=what)
    _validate_summary(snapshot.get("summary"))
    _validate_source_generation_set(snapshot.get("source_generation_set"))
    sources = snapshot.get("sources")
    if not isinstance(sources, list):
        _fail(f"{what}.sources must be a list")
    for receipt in sources:
        validate_source_receipt(receipt)
    sections = snapshot.get("sections")
    if not isinstance(sections, Mapping):
        _fail(f"{what}.sections must be a mapping")
    for section_id, section in sections.items():
        if section_id not in SECTION_IDS:
            _fail(f"{what}.sections has unknown section_id {section_id!r}")
        validate_section(section)
        if section.get("section_id") != section_id:
            _fail(f"{what}.sections[{section_id!r}].section_id mismatch")
    gaps = snapshot.get("gaps")
    if not isinstance(gaps, list) or not all(isinstance(g, str) for g in gaps):
        _fail(f"{what}.gaps must be a list of strings")
    _validate_correction(snapshot.get("correction"))
    _validate_authority(snapshot.get("authority"))
    if fields is _SEALED_ROOT_FIELDS:
        _require_digest(snapshot.get("snapshot_id"), what=f"{what}.snapshot_id")


def validate_unsealed_snapshot(snapshot: Mapping[str, Any]) -> None:
    _validate_root(snapshot, fields=_ROOT_FIELDS)


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    _validate_root(snapshot, fields=_SEALED_ROOT_FIELDS)


def seal_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_unsealed_snapshot(snapshot)
    sealed = json.loads(canonical_json_bytes(snapshot))
    sealed["snapshot_id"] = content_digest(snapshot)
    validate_snapshot(sealed)
    if len(canonical_json_bytes(sealed)) > MAX_SNAPSHOT_BYTES:
        _fail("snapshot exceeds 262144-byte limit")
    return sealed


def verify_snapshot(snapshot: Mapping[str, Any]) -> None:
    validate_snapshot(snapshot)
    unsealed = {k: v for k, v in snapshot.items() if k != "snapshot_id"}
    expected = content_digest(unsealed)
    if snapshot.get("snapshot_id") != expected:
        _fail("snapshot_id does not match recomputed content digest")
