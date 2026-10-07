#!/usr/bin/env python3
"""Development-only descriptive comparison over one immutable FIF response.

The comparator deliberately does *not* infer annual, fiscal-year, YoY,
materiality, economic inflection, rights, or trading semantics. It can describe
two equal-length, adjacent generic duration intervals only when the same
owner-issued response proves one issuer/metric/definition/unit/scope/source
revision and matching reported XBRL precision metadata.

This module is a W1 development witness. It is not a registered runtime schema,
a financial fact owner, an admitted publisher, or a trial/exposure writer.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import gcd
from pathlib import Path
import json
import re
from typing import Any

from baseline_replay import ENTITY, ReplayRefusal, _load, canonical, digest, owner_snapshot

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
METHOD_SHA256 = "b183fa79087c1f2bc4f53f6eba345553cfbb1eed55d6751c1ce3af525dbf7c08"
RESPONSE_SHA256 = "a752302d0d11457920be1425cb9ebb6d1f29560b7f1e8f41a5de98075083c6af"
CASE = "aapl_same_filing_annual_revenue"
SCHEMA = "issuer_inflection.equal_duration_comparison.dev/v1"
METHOD = "i3.equal_duration_descriptive_change/v1"
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", re.ASCII)
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class ComparisonRefusal(ValueError):
    """Typed refusal for a non-admissible development comparison."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ComparisonRefusal(reason)


def _parsed_date(value: Any, *, reason: str) -> date:
    _require(type(value) is str, reason)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ComparisonRefusal(reason) from exc


def _scaled(value: Any) -> tuple[int, int]:
    _require(type(value) is str and len(value) <= 96 and NUMBER.fullmatch(value) is not None, "numeric_value")
    unsigned = value[1:] if value.startswith("-") else value
    whole, dot, fraction = unsigned.partition(".")
    _require(len(whole) + len(fraction) <= 64 and len(fraction) <= 24, "numeric_bound")
    coefficient = int(whole + fraction)
    return (-coefficient if value.startswith("-") else coefficient), len(fraction)


def _fixed(coefficient: int, scale: int) -> str:
    if coefficient == 0:
        return "0"
    sign = "-" if coefficient < 0 else ""
    digits = str(abs(coefficient))
    if not scale:
        return sign + digits
    digits = digits.rjust(scale + 1, "0")
    fraction = digits[-scale:].rstrip("0")
    return sign + digits[:-scale] + (("." + fraction) if fraction else "")


def _display_two(numerator: int, denominator: int) -> str:
    quotient, remainder = divmod(abs(numerator) * 100, denominator)
    if remainder * 2 > denominator or (remainder * 2 == denominator and quotient % 2):
        quotient += 1
    digits = str(quotient).rjust(3, "0")
    return ("-" if numerator < 0 and quotient else "") + digits[:-2] + "." + digits[-2:]


def _change(before: str, after: str) -> dict[str, Any]:
    before_coefficient, before_scale = _scaled(before)
    after_coefficient, after_scale = _scaled(after)
    scale = max(before_scale, after_scale)
    before_aligned = before_coefficient * (10 ** (scale - before_scale))
    after_aligned = after_coefficient * (10 ** (scale - after_scale))
    _require(before_aligned > 0, "positive_baseline")
    difference = after_aligned - before_aligned
    numerator = difference * 100
    denominator = before_aligned
    divisor = gcd(abs(numerator), denominator)
    numerator //= divisor
    denominator //= divisor
    _require(
        max(len(str(abs(numerator))), len(str(denominator))) <= 128,
        "rational_bound",
    )
    return {
        "absolute_change": _fixed(difference, scale),
        "relative_change_exact": {
            "numerator": str(numerator),
            "denominator": str(denominator),
        },
        "relative_change_percent_display": _display_two(numerator, denominator),
    }


def _provenance(cell: dict[str, Any], *, owner_entity_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    _require(type(cell) is dict, "cell_shape")
    _require(type(owner_entity_id) is str and bool(owner_entity_id), "owner_entity")
    _require(cell.get("entity_id") == owner_entity_id, "owner_entity")
    _require(cell.get("status") == cell.get("state") == "value" and type(cell.get("value")) is str, "owner_value")
    provenance = cell.get("provenance")
    _require(type(provenance) is dict and provenance.get("kind") == "direct", "direct_owner_fact")
    _require(provenance.get("source_entity_id") == owner_entity_id, "owner_entity")
    _require(cell.get("reason") is None and provenance.get("reason") is None, "owner_value_reason")
    selected = provenance.get("selected_raw_fact")
    _require(type(selected) is dict and selected.get("is_nil") is False, "selected_owner_fact")
    source = selected.get("source")
    context = selected.get("context")
    _require(type(source) is dict and source.get("entity_id") == owner_entity_id, "owner_entity")
    _require(type(context) is dict and context.get("entity_identifier") == owner_entity_id, "owner_entity")
    _require(selected.get("parsed_value") == cell["value"], "selected_value")
    return provenance, selected


def _period_basis(cell: dict[str, Any], selected: dict[str, Any]) -> tuple[date, date, int]:
    period = cell.get("period")
    context = selected.get("context")
    _require(type(period) is dict and type(context) is dict, "period_shape")
    _require(period.get("kind") == "duration", "period_kind")
    _require(period.get("calendar_kind") == "unknown", "calendar_kind")
    _require(period.get("fiscal_year") is None, "owner_fiscal_year_not_typed")
    _require(period.get("fiscal_quarter") is None, "owner_fiscal_quarter_not_typed")
    _require(period.get("fiscal_year_weeks") is None, "owner_fiscal_year_weeks_not_typed")
    _require(period.get("week_count") is None, "owner_week_count_not_typed")
    _require(period.get("semantics") == ["duration"], "period_semantics")
    start = _parsed_date(period.get("start"), reason="period_date")
    end = _parsed_date(period.get("end"), reason="period_date")
    _require(start <= end, "period_order")
    _require(
        context.get("start") == period.get("start")
        and context.get("end") == period.get("end")
        and context.get("instant") is None,
        "source_period",
    )
    days = (end - start).days + 1
    inferred_weeks = (days + 3) // 7
    _require(period.get("inferred_week_count") == inferred_weeks, "inferred_week_count")
    return start, end, days


def _source_revision(selected: dict[str, Any]) -> dict[str, str]:
    source = selected.get("source")
    _require(type(source) is dict, "source_revision")
    keys = ("source", "entity_id", "accession", "document_id", "body_sha256", "source_url")
    _require(all(type(source.get(key)) is str and source[key] for key in keys), "source_revision")
    _require(HEX64.fullmatch(source["body_sha256"]) is not None, "source_revision")
    return {key: source[key] for key in keys}


def _definition_basis(cell: dict[str, Any], provenance: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    _require(type(cell.get("metric_id")) is str and cell["metric_id"], "metric")
    fields = (
        "metric_rule_id",
        "metric_rule_version",
        "metric_rule_digest",
        "mapping_rule_id",
        "mapping_rule_version",
        "mapping_digest",
    )
    basis = {field: provenance.get(field) for field in fields}
    _require(
        all(
            (type(value) is str and value)
            for value in basis.values()
        ),
        "definition_basis",
    )
    _require(
        HEX64.fullmatch(basis["metric_rule_digest"]) is not None
        and HEX64.fullmatch(basis["mapping_digest"]) is not None,
        "definition_basis",
    )
    concept = selected.get("concept_qname")
    _require(type(concept) is str and concept == provenance.get("concept_qname"), "concept")
    unit = selected.get("unit")
    _require(type(unit) is dict, "unit")
    _require(
        cell.get("unit") == "USD"
        and provenance.get("unit") == "USD"
        and unit.get("measures") == ["iso4217:USD"]
        and unit.get("denominator_measures") == [],
        "unit",
    )
    context = selected.get("context")
    _require(
        type(context) is dict
        and context.get("explicit_dimensions") == {}
        and context.get("typed_dimensions") == {},
        "dimensions",
    )
    decimals = selected.get("decimals")
    precision = selected.get("precision")
    _require(type(decimals) is str and decimals, "reported_precision")
    _require(precision is None or type(precision) is str, "reported_precision")
    return {
        "metric_id": cell["metric_id"],
        **basis,
        "concept_qname": concept,
        "unit": "USD",
        "decimals": decimals,
        "precision": precision,
    }


def compare_owner_cells(prior: dict[str, Any], current: dict[str, Any], *, owner_entity_id: str) -> dict[str, Any]:
    """Compare two already-owner-issued generic duration cells.

    The output is descriptive arithmetic only. Labels are intentionally excluded
    from the semantic comparison basis and cannot establish fiscal semantics.
    """
    prior_provenance, prior_selected = _provenance(prior, owner_entity_id=owner_entity_id)
    current_provenance, current_selected = _provenance(current, owner_entity_id=owner_entity_id)

    _require(prior.get("metric_id") == current.get("metric_id"), "metric")
    prior_basis = _definition_basis(prior, prior_provenance, prior_selected)
    current_basis = _definition_basis(current, current_provenance, current_selected)
    _require(prior_basis["metric_id"] == current_basis["metric_id"], "metric")
    _require(
        {k: v for k, v in prior_basis.items() if k not in {"decimals", "precision"}}
        == {k: v for k, v in current_basis.items() if k not in {"decimals", "precision"}},
        "definition_basis",
    )
    _require(
        prior_basis["decimals"] == current_basis["decimals"]
        and prior_basis["precision"] == current_basis["precision"],
        "reported_precision",
    )

    prior_source = _source_revision(prior_selected)
    current_source = _source_revision(current_selected)
    _require(prior_source == current_source, "source_revision")

    prior_start, prior_end, prior_days = _period_basis(prior, prior_selected)
    current_start, current_end, current_days = _period_basis(current, current_selected)
    _require(prior_days == current_days, "equal_duration")
    _require(current_start == prior_end + timedelta(days=1), "contiguous_duration")

    change = _change(prior["value"], current["value"])
    semantic = {
        "method": METHOD,
        "owner_entity_id": owner_entity_id,
        "metric_id": prior["metric_id"],
        "unit": prior["unit"],
        "definition_basis": prior_basis,
        "source_revision": prior_source,
        "prior_cell_id": prior["cell_id"],
        "current_cell_id": current["cell_id"],
        "prior_interval": {
            "kind": "duration",
            "start": prior_start.isoformat(),
            "end": prior_end.isoformat(),
            "days": prior_days,
        },
        "current_interval": {
            "kind": "duration",
            "start": current_start.isoformat(),
            "end": current_end.isoformat(),
            "days": current_days,
        },
        "prior_value": prior["value"],
        "current_value": current["value"],
        **change,
    }
    return {
        "schema": SCHEMA,
        "comparison_id": "i3devcmp_" + digest(canonical(semantic))[:24],
        "relationship_state": "descriptive_equal_duration_source_intervals",
        "owner_entity_id": owner_entity_id,
        "metric_id": prior["metric_id"],
        "unit": prior["unit"],
        "prior_value": prior["value"],
        "current_value": current["value"],
        **change,
        "interval_days": prior_days,
        "inferred_week_count": (prior_days + 3) // 7,
        "semantic_period_basis": {
            "kind": "duration",
            "calendar_kind": "unknown",
            "prior_start": prior_start.isoformat(),
            "prior_end": prior_end.isoformat(),
            "current_start": current_start.isoformat(),
            "current_end": current_end.isoformat(),
            "contiguous": True,
            "equal_duration": True,
        },
        "source_revision": prior_source,
        "definition_basis": prior_basis,
        "owner_cell_ids": [prior["cell_id"], current["cell_id"]],
        "source_labels": [prior["period"].get("label"), current["period"].get("label")],
        "owner_typed_annual": False,
        "annual_or_yoy_claim_permitted": False,
        "economic_interpretation": None,
        "comparison_admitted": False,
        "product_publication_admitted": False,
        "trial_registered": False,
        "emitted_at": None,
        "authority": {"class": "context_only", "display_only": True},
        "limitations": [
            "Generic equal-duration source intervals only; source labels do not establish annual or YoY semantics.",
            "Reported decimals match but do not create economic materiality or signal authority.",
            "Development fixture only; source-owner, rights, publication, trial, and production admissions remain open.",
        ],
    }


def _verified_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        return _load(path.read_bytes(), expected_sha256)
    except (OSError, ReplayRefusal) as exc:
        raise ComparisonRefusal("evidence_unavailable_or_invalid") from exc


def load_verified_comparison(
    *,
    evidence_dir: Path | None = None,
    expected_response_sha256: str = RESPONSE_SHA256,
) -> dict[str, Any]:
    """Load one immutable captured response and derive the bounded comparison."""
    _require(expected_response_sha256 == RESPONSE_SHA256, "response_identity")
    evidence = Path(evidence_dir) if evidence_dir is not None else EVIDENCE
    method = _verified_json(evidence / "method-before-execution.json", METHOD_SHA256)
    response_path = evidence / f"{CASE}.response.json"
    try:
        response_raw = response_path.read_bytes()
    except OSError as exc:
        raise ComparisonRefusal("evidence_unavailable_or_invalid") from exc

    request = method.get("requests", {}).get(CASE)
    _require(type(request) is dict, "request_missing")
    _require(request.get("schema") == "fundamental_forensics.financial_query_request/v1", "request_schema")
    _require(request.get("entity_id") == "ISS:US-XNAS-AAPL", "request_issuer")
    _require(request.get("metric_ids") == ["revenue"], "request_metric")
    periods = request.get("periods")
    _require(type(periods) is list and len(periods) == 2, "request_periods")
    _require(all(type(item) is dict and item.get("kind") == "duration" for item in periods), "request_period_kind")

    try:
        snapshot = owner_snapshot(response_raw, RESPONSE_SHA256, request)
    except ReplayRefusal as exc:
        raise ComparisonRefusal("owner_response_invalid") from exc
    cells = list(snapshot["nodes"].values())
    _require(len(cells) == 2, "root_cells")
    cells.sort(key=lambda cell: cell["period"]["start"])
    owner_entity_id = snapshot["entity"]["source_entity_id"]
    result = compare_owner_cells(cells[0], cells[1], owner_entity_id=owner_entity_id)
    result["owner_response_sha256"] = RESPONSE_SHA256
    result["owner_query_hash"] = snapshot["query_hash"]
    result["method_before_execution_sha256"] = METHOD_SHA256
    result["source_commit"] = method.get("source_commit")
    return json.loads(canonical(result))
