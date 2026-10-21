"""Trusted initial-prompt risk evidence carried by the existing decision log.

This is a value contract, not a store, event registry, evaluator or source of
decision authority. The autonomous runner creates it before provider dispatch;
model-submitted provenance is never used to mint it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any

_SCHEMA = "perception_input.v1"
_SCOPE = "initial_prompt_market_perception"
_READER = "current_perception_withdrawal.v1"


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _time(value: Any) -> datetime:
    clock = datetime.fromisoformat(str(value))
    if clock.tzinfo is None:
        raise ValueError("receipt clock must be aware")
    return clock.astimezone(timezone.utc)


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _projection_shape(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    publication = value.get("publication", {})
    if not isinstance(publication, dict):
        return False
    digest = publication.get("artifact_sha256")
    if digest is not None and not _digest(digest):
        return False
    if not isinstance(value.get("serving_freshness", {}), dict):
        return False
    rows = value.get("plane_summaries", [])
    if not isinstance(rows, list):
        return False
    names = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        name = row.get("name")
        if not isinstance(name, str) or not name or name in names:
            return False
        names.add(name)
        fresh = row.get("freshness", {})
        if not isinstance(fresh, dict):
            return False
        if "stale" in fresh and type(fresh["stale"]) is not bool:
            return False
        if row.get("direction") not in {None, "risk_on", "risk_off", "neutral"}:
            return False
    return True


def capture_projection(projection: dict[str, Any], rendered: str) -> dict[str, Any]:
    """Record the projection used to render this exact initial-prompt section."""
    copied = copy.deepcopy(projection)
    freshness = copied.get("serving_freshness") if isinstance(copied, dict) else None
    checked = freshness.get("checked_at") if isinstance(freshness, dict) else None
    return {
        "schema_version": _SCHEMA, "scope": _SCOPE, "reader_contract": _READER,
        "checked_at": checked,
        "projection": copied, "rendered_context": rendered,
        "supplied": bool(rendered),
    }


def seal(receipt: dict[str, Any] | None, final_prompt: str) -> dict[str, Any]:
    """Bind a section still present in the final prompt before provider dispatch.

    Invalid legacy projection data cannot abort reasoning or become historical
    entry evidence. Preserve the rendered text and mark its projection unavailable.
    """
    captured = receipt if isinstance(receipt, dict) else capture_projection({}, "")
    sealed_at = datetime.now(timezone.utc).isoformat()
    rendered = captured.get("rendered_context")
    rendered = rendered if isinstance(rendered, str) else ""
    projection = copy.deepcopy(captured.get("projection", {}))
    checked = captured.get("checked_at")
    projection_status = "captured"
    try:
        if not _projection_shape(projection):
            raise ValueError("invalid projection shape")
        _bytes(projection)
        if _time(checked) > _time(sealed_at):
            raise ValueError("projection checked after dispatch seal")
    except (TypeError, ValueError):
        projection = {}
        checked = sealed_at
        projection_status = "unavailable"
    result = {
        "schema_version": _SCHEMA, "scope": _SCOPE, "reader_contract": _READER,
        "checked_at": checked, "projection": projection,
        "projection_status": projection_status,
        "rendered_context": rendered,
        "supplied": bool(rendered and rendered in final_prompt),
        "prompt_sha256": hashlib.sha256(final_prompt.encode("utf-8")).hexdigest(),
        "sealed_at": sealed_at,
    }
    if projection_status == "unavailable":
        result["projection_reason"] = "invalid_shape_clock_or_nonfinite_value"
    if rendered and not result["supplied"]:
        result["supply_reason"] = "rendered_section_absent_from_final_prompt"
    result["receipt_sha256"] = hashlib.sha256(_bytes(result)).hexdigest()
    return result


def valid(receipt: Any, *, decision_timestamp: str | None = None) -> bool:
    """Integrity validation within the existing trusted decision-writer boundary."""
    try:
        if not isinstance(receipt, dict):
            return False
        if (receipt.get("schema_version") != _SCHEMA or receipt.get("scope") != _SCOPE
                or receipt.get("reader_contract") != _READER):
            return False
        if not _projection_shape(receipt.get("projection")):
            return False
        if (type(receipt.get("supplied")) is not bool
                or not isinstance(receipt.get("rendered_context"), str)
                or (receipt["supplied"] and not receipt["rendered_context"])
                or not _digest(receipt.get("prompt_sha256"))
                or not _digest(receipt.get("receipt_sha256"))):
            return False
        status = receipt.get("projection_status")
        if status not in {"captured", "unavailable"}:
            return False
        if status == "unavailable" and receipt["projection"]:
            return False
        if status == "captured" and (
                receipt["projection"].get("serving_freshness", {}).get("checked_at")
                != receipt.get("checked_at")):
            return False
        unsigned = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        if hashlib.sha256(_bytes(unsigned)).hexdigest() != receipt["receipt_sha256"]:
            return False
        if _time(receipt["checked_at"]) > _time(receipt["sealed_at"]):
            return False
        if decision_timestamp is not None and _time(receipt["sealed_at"]) > _time(decision_timestamp):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def entry_planes(
    receipt: Any, *, decision_timestamp: str | None, entry_date: str | None = None
) -> dict[str, str] | None:
    """Read original eligible observations; never infer a replacement aggregate.

    The complete receipt preserves unavailable aggregate status and advisory
    provenance. A date-only file or an unbound row supplies no entry evidence.
    """
    if not decision_timestamp or not valid(receipt, decision_timestamp=decision_timestamp):
        return None
    if receipt["supplied"] is not True or receipt["projection_status"] != "captured":
        return None
    try:
        decision_day = _time(decision_timestamp).date()
        entry_day = date.fromisoformat(entry_date) if entry_date is not None else decision_day
        # A later/backdated run proves its actual prompt, not the earlier entry
        # cohort. Preserve that receipt separately without rewriting cohort dates.
        if (decision_day != entry_day
                or _time(receipt["checked_at"]).date() > entry_day
                or _time(receipt["sealed_at"]).date() > entry_day):
            return None
    except (TypeError, ValueError):
        return None
    projection = receipt["projection"]
    if not _digest(projection.get("publication", {}).get("artifact_sha256")):
        return None
    result = {}
    for row in projection.get("plane_summaries", []):
        fresh = row.get("freshness", {})
        if row.get("direction") not in {"risk_on", "risk_off", "neutral"} or fresh.get("stale") is not False:
            continue
        try:
            source_day = date.fromisoformat(str(fresh.get("asof"))[:10])
            if source_day > min(entry_day, _time(receipt["checked_at"]).date()):
                continue
        except (TypeError, ValueError):
            continue
        result[row["name"]] = row["direction"]
    return result or None
