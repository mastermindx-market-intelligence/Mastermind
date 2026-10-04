"""Development-only baseline reconstruction over unchanged FIF owner responses.

This is an offline W1 fixture-lane witness, not a registered issuer transition
schema, financial interpreter, publisher, trial registry, or production reader.
It preserves owner states and references. It calculates no financial metric.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any

MAX_RESPONSE_BYTES = 1_048_576
MAX_NODES = 400
MAX_DEPTH = 40
ENTITY = {"cik": "0000320193", "entity_id": "ISS:US-XNAS-AAPL", "source_entity_id": "0000320193", "ticker": "AAPL"}
DELIVERY = {"kind": "committed_golden_fixture", "attested": False, "production_issuer_service": False}
AUTHORITY = {"class": "context_only", "display_only": True}
ACCESSIONS = {"0000320193-25-000079", "0000320193-26-000020"}
SOURCE_PIN = "37122b69fffa98cb160022c4831df0338ef3e7e3"
VARIABLE_STATES = {"value", "missing", "not_evaluable"}
HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
VALUE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", re.ASCII)

class ReplayRefusal(ValueError):
    """The fixture evidence cannot support this reconstruction."""

def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReplayRefusal(reason)

def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _object(pairs: list[tuple[str, Any]]) -> dict:
    out = {}
    for key, value in pairs:
        _require(key not in out, "duplicate_json_key")
        out[key] = value
    return out

def _invalid_constant(value: str) -> None:
    raise ReplayRefusal("nonfinite_json")

def _instant(value: Any) -> datetime:
    _require(type(value) is str and len(value) <= 48, "invalid_clock")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayRefusal("invalid_clock") from exc
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "timezone_missing")
    return parsed

def _key(metric: str, period: dict) -> tuple:
    return (metric, period["kind"], period.get("start"), period["end"], period["label"])

def _request(request: dict) -> tuple[list[tuple], dict]:
    _require(type(request) is dict, "request_not_object")
    _require(set(request) == {"schema", "entity_id", "metric_ids", "periods", "policy"}, "request_shape")
    _require(request["schema"] == "fundamental_forensics.financial_query_request/v1", "request_schema")
    _require(request["entity_id"] == ENTITY["entity_id"], "wrong_issuer")
    metrics = request["metric_ids"]; periods = request["periods"]; policy = request["policy"]
    _require(type(metrics) is list and metrics == ["revenue", "total_assets"], "fixture_metric_scope")
    _require(type(periods) is list and len(periods) == 2, "fixture_period_scope")
    expected = [
        {"kind": "duration", "start": "2024-09-29", "end": "2025-09-27", "label": "FY2025"},
        {"kind": "instant", "start": None, "end": "2025-09-27", "label": "2025-09-27"},
    ]
    _require(periods == expected, "fixture_period_scope")
    _require(type(policy) is dict and set(policy) == {"selection", "source_snapshot_at", "recorded_at"}, "policy_shape")
    _require(policy["selection"] == "latest_known_as_of", "selection_policy")
    _instant(policy["source_snapshot_at"]); _instant(policy["recorded_at"])
    return [_key(m, p) for m in metrics for p in periods], policy

def _load(raw: bytes, expected_sha256: str) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_RESPONSE_BYTES, "response_byte_bound")
    _require(type(expected_sha256) is str and HEX64.fullmatch(expected_sha256) is not None, "digest_shape")
    _require(digest(raw) == expected_sha256, "response_digest_mismatch")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ReplayRefusal): raise
        raise ReplayRefusal("unreadable_json") from exc
    stack = [(result, 0)]; visited = 0
    while stack:
        item, depth = stack.pop(); visited += 1
        _require(depth <= MAX_DEPTH and visited <= 100_000, "json_complexity_bound")
        if type(item) is dict: stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list: stack.extend((v, depth + 1) for v in item)
    _require(type(result) is dict, "response_not_object")
    return result

def owner_snapshot(raw: bytes, expected_sha256: str, request: dict) -> dict:
    """Extract a complete, reference-bearing view; hashes do not grant admission."""
    requested, policy = _request(request)
    response = _load(raw, expected_sha256)
    _require(response.get("schema") == "fundamental_forensics.financial_query_response/v1", "response_schema")
    _require(response.get("entity") == ENTITY, "wrong_issuer")
    authority = response.get("authority")
    _require(type(authority) is dict and set(authority) == set(AUTHORITY) and authority.get("class") == "context_only" and authority.get("display_only") is True, "authority_widened")
    delivery = response.get("delivery")
    _require(type(delivery) is dict and set(delivery) == set(DELIVERY), "delivery_shape")
    _require(delivery["kind"] == DELIVERY["kind"] and delivery["attested"] is False and delivery["production_issuer_service"] is False, "golden_promoted")
    receipt = response.get("receipt")
    _require(type(receipt) is dict, "receipt_missing")
    received_policy = receipt.get("policy")
    _require(type(received_policy) is dict and set(received_policy) == set(policy), "aggregate_policy_shape")
    _require(received_policy["selection"] == policy["selection"], "aggregate_policy_mismatch")
    for clock in ("source_snapshot_at", "recorded_at"):
        _require(_instant(received_policy[clock]) == _instant(policy[clock]), "aggregate_policy_mismatch")
    query_hash = receipt.get("query_hash")
    _require(type(query_hash) is str and HEX64.fullmatch(query_hash) is not None, "query_hash_missing")
    nodes = receipt.get("nodes"); roots = receipt.get("root_cell_ids")
    _require(type(nodes) is list and len(nodes) <= MAX_NODES, "node_bound")
    _require(type(roots) is list and len(roots) == len(requested) and all(type(x) is str for x in roots), "root_coverage")
    _require(len(set(roots)) == len(roots), "duplicate_root")
    by_id = {}
    for node in nodes:
        _require(type(node) is dict and type(node.get("cell_id")) is str, "node_shape")
        _require(node["cell_id"] not in by_id, "duplicate_node")
        by_id[node["cell_id"]] = node
    actual = {}
    for cell_id in roots:
        _require(cell_id in by_id, "missing_root_node")
        node = by_id[cell_id]
        _require({"cell_id", "metric_id", "period", "entity_id", "state", "value", "unit", "reason", "provenance"}.issubset(node), "root_fields_missing")
        period = node.get("period"); provenance = node.get("provenance")
        _require(type(period) is dict and type(provenance) is dict, "cell_shape")
        try: key = _key(node["metric_id"], period)
        except (KeyError, TypeError) as exc: raise ReplayRefusal("cell_key_missing") from exc
        _require(key in requested and key not in actual, "variable_coverage_mismatch")
        _require(node.get("entity_id") == ENTITY["source_entity_id"], "cell_issuer_mismatch")
        _require(type(node.get("state")) is str and node["state"] in VARIABLE_STATES, "owner_state_unknown")
        _require(provenance.get("policy") == policy["selection"], "receipt_policy_mismatch")
        for owner_clock, request_clock in (("source_snapshot_at", "source_snapshot_at"), ("recorded_cutoff_at", "recorded_at")):
            _require(_instant(provenance.get(owner_clock)) == _instant(policy[request_clock]), "receipt_cutoff_mismatch")
        selected = provenance.get("selected_raw_fact")
        if node["state"] == "value":
            _require(type(node.get("value")) is str and len(node["value"]) <= 96 and VALUE.fullmatch(node["value"]) is not None, "owner_value_shape")
            _require(type(selected) is dict and selected.get("is_nil") is False, "selected_fact_missing")
            source = selected.get("source"); clocks = selected.get("clocks")
            _require(type(source) is dict and type(clocks) is dict, "source_ref_missing")
            _require(all(type(source.get(k)) is str and bool(source[k]) for k in ("document_id", "source_url", "body_sha256", "entity_id", "accession", "source")), "source_ref_fields_missing")
            _require(re.fullmatch(r"sec_document_[0-9a-f]{64}", source["document_id"], flags=re.ASCII) is not None, "document_ref_shape")
            _require(source.get("source") == "sec-edgar" and type(source.get("accession")) is str and source["accession"] in ACCESSIONS and source.get("entity_id") == ENTITY["source_entity_id"], "source_ref_out_of_scope")
            _require(selected.get("parsed_value") == node["value"], "value_differs_from_owner_fact")
            _require(type(source.get("body_sha256")) is str and HEX64.fullmatch(source["body_sha256"]) is not None, "source_digest_shape")
            for source_field, provenance_field in (("body_sha256", "source_body_sha256"), ("document_id", "document_id"), ("accession", "accession"), ("source_url", "source_url")):
                _require(source.get(source_field) == provenance.get(provenance_field), "source_provenance_mismatch")
            occurrence = selected.get("occurrence_id"); occurrence_ids = provenance.get("source_occurrence_ids")
            _require(type(occurrence) is str and type(occurrence_ids) is list and occurrence in occurrence_ids, "selected_occurrence_not_in_receipt")
            span = selected.get("source_span")
            _require(type(span) is list and len(span) == 2 and all(type(x) is int for x in span) and 0 <= span[0] < span[1], "source_span_shape")
            for definition in ("metric_rule_digest", "mapping_digest"):
                _require(type(provenance.get(definition)) is str and HEX64.fullmatch(provenance[definition]) is not None, "definition_digest_missing")
            _require(_instant(clocks.get("accepted_at")) <= _instant(policy["source_snapshot_at"]), "future_source_fact")
            _require(_instant(clocks.get("recorded_at")) <= _instant(policy["recorded_at"]), "future_admitted_fact")
            _require(_instant(provenance.get("system_ready_at")) <= _instant(policy["recorded_at"]), "future_method_or_mapping")
            _require(selected.get("dimensions_known") is True, "unknown_dimension_scope")
            context = selected.get("context")
            _require(type(context) is dict and context.get("explicit_dimensions") == {} and context.get("typed_dimensions") == {}, "nonconsolidated_scope")
        else:
            _require(node.get("value") is None and selected is None, "refusal_value_or_selected_fact_leak")
            _require(type(node.get("reason")) is str and bool(node["reason"]), "refusal_reason_missing")
        actual[key] = node
    _require(set(actual) == set(requested), "incomplete_variable_universe")
    coverage = response.get("coverage")
    expected_counts = {"requested_cells": len(requested), "value_cells": sum(n["state"] == "value" for n in actual.values()), "missing_cells": sum(n["state"] == "missing" for n in actual.values()), "not_evaluable_cells": sum(n["state"] == "not_evaluable" for n in actual.values())}
    _require(type(coverage) is dict and set(coverage) == set(expected_counts) and all(type(v) is int and v >= 0 for v in coverage.values()) and coverage == expected_counts, "owner_coverage_mismatch")
    return {"owner_response_sha256": expected_sha256, "query_hash": query_hash, "policy": dict(policy), "coverage": expected_counts, "requested": requested, "nodes": actual}

def _reference(node: dict, snapshot: dict) -> dict:
    p = node["provenance"]; selected = p.get("selected_raw_fact")
    return {"owner_response_sha256": snapshot["owner_response_sha256"], "query_hash": snapshot["query_hash"], "cell_id": node["cell_id"], "metric_id": node["metric_id"], "period": node["period"], "state": node["state"], "value": node["value"], "unit": node.get("unit"), "reason": node.get("reason"), "definition_refs": {k:p.get(k) for k in ("metric_rule_id", "metric_rule_version", "metric_rule_digest", "mapping_rule_id", "mapping_rule_version", "mapping_digest")}, "selected_occurrence_ref": None if selected is None else {"occurrence_id": selected["occurrence_id"], "source": selected["source"], "source_span": selected.get("source_span"), "revision_of": selected.get("revision_of"), "clocks": selected["clocks"]}}

def compare_snapshots(before_raw: bytes, after_raw: bytes, *, before_sha256: str, after_sha256: str, before_request: dict, after_request: dict) -> dict:
    """Reconstruct all requested variables, including unchanged and refused ones."""
    before = owner_snapshot(before_raw, before_sha256, before_request)
    after = owner_snapshot(after_raw, after_sha256, after_request)
    _require(before["requested"] == after["requested"], "baseline_scope_changed")
    for clock in ("source_snapshot_at", "recorded_at"):
        _require(_instant(before["policy"][clock]) <= _instant(after["policy"][clock]), "cutoff_order_reversed")
    rows = []
    for key in before["requested"]:
        b = before["nodes"][key]; a = after["nodes"][key]
        br = _reference(b, before); ar = _reference(a, after)
        if b["state"] == a["state"] == "not_evaluable":
            status = "unchanged_refusal" if b["reason"] == a["reason"] else "refusal_reason_changed"
        elif a["state"] == "not_evaluable": status = "became_not_evaluable"
        elif b["state"] == a["state"] == "missing": status = "missing_at_both_cutoffs"
        elif b["state"] != "value" and a["state"] == "value": status = "became_available_not_economic_change"
        elif b["state"] == "value" and a["state"] == "missing": status = "became_missing"
        elif br["definition_refs"] != ar["definition_refs"] or b.get("unit") != a.get("unit"): status = "basis_changed_requires_owner_admission"
        elif b["value"] == a["value"]:
            status = "unchanged_value" if br["selected_occurrence_ref"] == ar["selected_occurrence_ref"] else "same_value_evidence_changed"
        else: status = "changed_value_requires_owner_admission"
        rows.append({"variable": {"metric_id": key[0], "period": {"kind": key[1], "start": key[2], "end": key[3], "label": key[4]}}, "baseline": br, "target": ar, "reconstruction_state": status, "economic_interpretation": None})
    payload = {"purpose": "development_fixture_baseline_reconstruction", "source_commit": SOURCE_PIN, "issuer_ref": ENTITY, "baseline_response_sha256": before_sha256, "target_response_sha256": after_sha256, "baseline_cutoffs": before["policy"], "target_cutoffs": after["policy"], "baseline_coverage": before["coverage"], "target_coverage": after["coverage"], "requested_variable_count": len(rows), "variables": rows, "counts": {s:sum(r["reconstruction_state"] == s for r in rows) for s in sorted({r["reconstruction_state"] for r in rows})}, "comparison_admitted": False, "registered_transition_schema": False, "trial_registered": False, "product_publication_admitted": False, "emitted_at": None, "authority": AUTHORITY, "limitations": ["Historical reconstruction with a present method; not a past system emission.", "Only the frozen AAPL owner fixture and four requested variable slots are covered.", "No new financial calculations, inferred source revisions, economic inflection label or product rights."]}
    serialized = canonical(payload)
    # Return detached evidence: caller edits cannot mutate constants, input policy or later calls.
    return {"artifact_sha256": digest(serialized), "payload": json.loads(serialized)}
