"""Bounded authored-plan evidence for the existing leadership brief.

Not a plan writer, memory store, adoption engine, root-job binding or authority.
Raw adoption/proposal content is validated by the incumbent contract but is never
included in this small projection. Local read time is not source freshness.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from common import workspace_project_plan_contract as wire

MAX_BYTES = 12288
MISSING_FIELDS = ("objective", "done_when", "next_action", "unresolved_effects")
_FIELD_BUDGETS = {
    "title": 512, "status": 256, "owner": 256,
    "objective": 2048, "next_action": 2048,
}
_UNAVAILABLE_REASONS = frozenset({
    "source_unavailable", "owner_unavailable", "invalid_owner_document",
    "projection_over_budget", "brief_capacity_exceeded",
})


def unavailable_plan(reason: str) -> dict:
    if reason not in _UNAVAILABLE_REASONS:
        raise ValueError("invalid_plan_unavailability")
    return {"state": "UNAVAILABLE", "reason": reason}


def missing_plan_fields(context: dict) -> list[str]:
    coverage = context.get("field_coverage", {}) if context.get("state") == "AVAILABLE" else {}
    return [field for field in MISSING_FIELDS
            if coverage.get(field, {}).get("state") != "RETURNED"]


def project_plan_context(body: object, *, work_ref: str, read_completed_at: float) -> dict:
    """Project only validated authored fields; never interpret text as a command."""
    if type(body) is not dict or body.get("schema") not in wire.BODY_SCHEMAS:
        return unavailable_plan("source_unavailable")
    try:
        selected = wire.validate_selection({"work_ref": work_ref})
        body = wire.validate_body(body)
        if body["selection"] != selected:
            raise ValueError("selection_mismatch")
        if body["availability"] != "AVAILABLE":
            return {**unavailable_plan("owner_unavailable"),
                    "owner_reason_codes": list(body["reason_codes"])}
        plan = body["plan"]
        value = {
            "state": "AVAILABLE", "reason": None, "selection": selected,
            "source_schema": body["schema"], "source": body["source"],
            "read_completed_at": datetime.fromtimestamp(
                read_completed_at, timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_freshness": "NOT_REPORTED_BY_OWNER",
            "snapshot_relation": "SEPARATE_READS_NOT_ATOMIC",
            "content_basis": "AUTHORED_WORKSTREAM_RECORD",
            "root_job_binding": "NOT_ESTABLISHED",
            "adoption": plan["adoption"], "field_coverage": {},
            "waves": [],
            "wave_boundary": "Authored planning evidence only; omitted waves remain unknown. "
                             "Not runtime task, effect or acceptance state.",
            "wave_coverage": {"total": len(plan["waves"]), "returned": 0,
                              "omitted": len(plan["waves"])},
            "version_history": {"state": "NOT_PROJECTED"},
        }
        for field, limit in _FIELD_BUDGETS.items():
            text = plan[field]
            if text is None:
                value[field] = None
                value["field_coverage"][field] = {
                    "state": "NOT_SUPPLIED_BY_OWNER", "original_bytes": 0}
                continue
            raw = json.dumps(text, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
            included = len(raw) <= limit
            value[field] = text if included else None
            value["field_coverage"][field] = {
                "state": "RETURNED" if included else "OMITTED_OVER_BUDGET",
                "original_bytes": len(text.encode("utf-8")),
            }
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_BYTES:
            return unavailable_plan("projection_over_budget")
        # Carry complete authored rows in source order. An omitted predecessor
        # remains in a retained row's depends_on; omission never satisfies it.
        # The upstream closed validator already checks the entire graph.
        for wave in plan["waves"]:
            value["waves"].append({field: wave[field] for field in
                ("id", "title", "status", "depends_on", "next_action", "prs")})
            value["wave_coverage"]["returned"] += 1
            value["wave_coverage"]["omitted"] -= 1
            candidate = json.dumps(value, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":")).encode("utf-8")
            if len(candidate) > MAX_BYTES:
                value["waves"].pop()
                value["wave_coverage"]["returned"] -= 1
                value["wave_coverage"]["omitted"] += 1
            else:
                encoded = candidate
        return json.loads(encoded)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError,
            UnicodeError, AttributeError):
        return unavailable_plan("invalid_owner_document")
