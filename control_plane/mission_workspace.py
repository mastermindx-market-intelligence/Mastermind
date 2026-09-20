"""Pure, held mission-workspace reduction over already-composed owner views.

This module deliberately acquires nothing.  In particular it is not a Runtime
reader, a control-room gatherer, a broker client, or an acceptance authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.chairman_control_room_remote import _project_agent_os_freeform


SCHEMA = "mastermind.mission_workspace.v1"
_MISSING = frozenset({"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"})
_READ = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
_SECTION = frozenset({"COMPLETE", "INCOMPLETE", "EMPTY", "UNAVAILABLE", "NOT_PROJECTED"})
_EXECUTION = frozenset({"NOT_STARTED", "IN_PROGRESS", "ACCEPTED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED"})
_DISPATCH = frozenset({"WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED", "STARTED", "RETURNED", "DELIVERY_UNCONSUMED", "WATCH_UNPROVEN", "RUNTIME_BINDING_RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN", "UNKNOWN"})
_ARM_KEYS = ("ceo_submit_armed", "coo_autonomy_armed", "ceo_ingress_app_armed", "dialogue_bridge_armed", "terminal_return_armed")


def _map(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return _project_agent_os_freeform(value)


def _fact(kind: str, field: str, owner: str | None, reason: str) -> dict[str, Any]:
    assert kind in _MISSING
    return {"missingness_class": kind, "target_field": field, "producer_owner": owner, "reason": reason}


def _facts(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[object, ...], dict[str, Any]] = {}
    for item in values:
        if set(item) != {"missingness_class", "target_field", "producer_owner", "reason"}:
            continue
        if item["missingness_class"] not in _MISSING or not isinstance(item["target_field"], str) or not isinstance(item["reason"], str):
            continue
        row = dict(item)
        unique[(row["missingness_class"], row["target_field"], row["producer_owner"], row["reason"])] = row
    return [unique[key] for key in sorted(unique, key=repr)]


def _evidence(owner: str, ref: str | None, field: str, observed_at: object) -> list[dict[str, Any]]:
    if not ref:
        return []
    return [{"owner": owner, "ref": ref, "field": field, "source_revision": None, "source_time": None, "observed_at": observed_at if isinstance(observed_at, str) else None, "freshness_state": "UNKNOWN"}]


def _section(state: str, coverage: str, reasons: Sequence[str], total: int | None, items: Sequence[object], overflow: int | None) -> dict[str, Any]:
    assert state in _SECTION
    if state == "INCOMPLETE" or state in {"UNAVAILABLE", "NOT_PROJECTED"}:
        total = overflow = None
    if state == "EMPTY":
        total, overflow = 0, 0
    return {"state": state, "coverage": coverage, "reason_codes": sorted(set(reasons)), "total_count": total, "items": list(items), "overflow_count": overflow}


def _posture(*, execution: str, dispatch: str, current: bool, conflict: bool, blocker: bool, acceptance: Mapping[str, Any], review: str) -> tuple[str, str]:
    if dispatch == "EFFECT_UNKNOWN": return "EFFECT_UNKNOWN", "A1"
    if dispatch == "RUNTIME_BINDING_RECONCILIATION_REQUIRED": return "RECONCILIATION_REQUIRED", "B1"
    if conflict: return "RECONCILIATION_REQUIRED", "B2"
    terminal = {"FAILED": "EXECUTION_FAILED", "CANCELLED": "EXECUTION_CANCELLED", "LOST": "EXECUTION_LOST", "RATE_LIMITED": "EXECUTION_RATE_LIMITED"}
    if execution in terminal: return terminal[execution], "C"
    if blocker: return "BLOCKED", "D1"
    if dispatch == "DELIVERY_UNCONSUMED": return "DELIVERED_UNCONSUMED", "E1"
    if dispatch == "WATCH_UNPROVEN" or (dispatch == "RETURNED" and not current): return "CONSUMPTION_UNKNOWN", "E2" if dispatch == "WATCH_UNPROVEN" else "E3"
    if dispatch == "RETURNED" and current:
        if execution != "ACCEPTED": return "RETURN_EXECUTION_MISMATCH", "F0"
        if acceptance.get("state") == "ACCEPTED" and review == "reject": return "ACCEPTANCE_REVIEW_CONFLICT", "F1"
        if acceptance.get("state") == "ACCEPTED" and acceptance.get("artifact_revision") and acceptance.get("ruling"): return "ACCEPTED_PRODUCT", "F2"
        if review == "reject": return "REVIEW_REJECTED", "F3"
        if review == "NOT_YET": return "RETURNED_UNREVIEWED", "F4"
        if review == "approve": return "REVIEWED_NOT_ACCEPTED", "F5"
    if dispatch == "STARTED": return ("RUNNING", "G1") if current else ("HISTORICAL_OBSERVATION", "G1h")
    if dispatch in {"WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED"}: return ("WAITING", "G2") if current else ("HISTORICAL_OBSERVATION", "G2h")
    if execution == "NOT_STARTED" and dispatch == "UNKNOWN": return "NOT_STARTED", "H1"
    return "UNKNOWN", "I1"


def compose_mission_workspace(*, control_room: Mapping[str, Any] | None, fabric_view: Mapping[str, Any] | None, work_ref: str, root_job_id: str | None, source_validity: Mapping[str, Any] | None, cache_currentness: Mapping[str, Any] | None, source_generation: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compose one deterministic, read-only mission view from supplied snapshots."""
    control, fabric, validity, currentness, generation = _map(control_room), _map(fabric_view), _map(source_validity), _map(cache_currentness), dict(_map(source_generation))
    work = next((row for row in _list(control.get("work")) if _map(row).get("work_ref") == work_ref), None)
    work = _map(work)
    autonomy = next((row for row in _list(_map(control.get("autonomy")).get("cards")) if _map(row).get("responsibility_ref") == work.get("responsibility_ref")), None)
    autonomy = _map(autonomy)
    candidates = sorted({item for item in _list(autonomy.get("root_job_candidates")) if isinstance(item, str)})
    conflict = autonomy.get("runtime_root_state") == "CONFLICT" or len(candidates) > 1
    resolved = root_job_id if isinstance(root_job_id, str) and root_job_id in candidates and not conflict else None
    root = _map(fabric.get("root")) if resolved and _map(fabric.get("root")).get("job_id") == resolved else {}
    dispatch = _map(autonomy.get("dispatch"))
    dispatch_state = dispatch.get("dispatch_state") if dispatch.get("dispatch_state") in _DISPATCH else "UNKNOWN"
    historical = dispatch.get("historical") is not False
    observed_current = currentness.get("state") == "CURRENT" and not historical
    armed_source = _map(fabric.get("armed")); armed = {key: armed_source.get(key) if type(armed_source.get(key)) is bool else None for key in _ARM_KEYS}; armed["source"] = armed_source.get("source") if isinstance(armed_source.get("source"), str) else "absent"
    availability = "UNAVAILABLE_NEW_SUBMISSION" if armed["ceo_submit_armed"] is False else "UNKNOWN"
    result, review = _map(root.get("result")), _map(root.get("review"))
    execution = result.get("state") if result.get("state") in _EXECUTION else "NOT_STARTED"
    verdict = review.get("verdict") if review.get("verdict") in {"approve", "reject", "NOT_YET"} else "NOT_YET"
    acceptance = {"state": "NOT_PROJECTED", "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"], "owner": None, "artifact_revision": None, "ruling": None, "evidence": []}
    posture, rule = _posture(execution=execution, dispatch=dispatch_state, current=observed_current, conflict=conflict or bool(generation.get("conflict")), blocker=bool(autonomy.get("blocker") or autonomy.get("declared_blocker")), acceptance=acceptance, review=verdict)
    raw_children = [_map(row) for row in _list(fabric.get("children"))]
    children = [{key: row.get(key) for key in ("job_id", "status", "parent_job_id", "depth", "orchestration_role", "plan_step_id", "attempt_count", "attempt_limit", "current_attempt_id", "latest_attempt")} for row in raw_children]
    unjoined = fabric.get("unjoined_job_count") if type(fabric.get("unjoined_job_count")) is int and fabric.get("unjoined_job_count") >= 0 else None
    child_section = _section("INCOMPLETE", "KNOWN_SUBSET", ["UNJOINED_JOBS_PRESENT"] if unjoined else [], None, children, None) if unjoined else _section("COMPLETE", "COMPLETE", [], len(children), children, 0)
    missing = _facts([*_list(fabric.get("missingness")), _fact("MISSING_PRODUCER", "acceptance", None, "acceptance owner is not projected"), *([_fact("DEGRADED", "mission.root_job_id", "executive_os", "ambiguous runtime roots are not selected")] if conflict else [])])
    degraded = sorted({item for item in _list(control.get("degraded")) + _list(fabric.get("degraded")) if isinstance(item, str)})
    read_state = "CURRENT" if control and fabric and validity.get("state", "CURRENT") == "CURRENT" and currentness.get("state", "CURRENT") == "CURRENT" else "PARTIAL" if control or fabric else "UNAVAILABLE"
    program_evidence = _evidence("agent_os", work_ref, "program", control.get("generated_at"))
    doc = {"schema": SCHEMA, "generated_at": control.get("generated_at") if isinstance(control.get("generated_at"), str) else fabric.get("generated_at"), "source": {"control_room_schema": control.get("schema"), "control_room_generated_at": control.get("generated_at"), "fabric_view_schema": fabric.get("schema"), "fabric_view_generated_at": fabric.get("generated_at"), "source_generation": generation, "source_coverage": sorted(key for key, value in (("control_room", bool(control)), ("fabric_view", bool(fabric))) if value)}, "read_state": {"state": read_state, "reason_codes": [] if read_state == "CURRENT" else ["SOURCE_INCOMPLETE"], "usable_sections": [name for name, value in (("program", bool(work)), ("mission", bool(root)), ("children", bool(fabric))) if value]}, "program": {"work_ref": work_ref, "title": _safe_text(_map(work.get("agent_os")).get("title") or work.get("title")), "state": _map(work.get("agent_os")).get("state") or _map(work.get("agent_os")).get("status"), "next_action": _safe_text(_map(work.get("agent_os")).get("next_action")), "evidence": program_evidence}, "mission": {"root_job_id": resolved, "root_job_candidates": candidates, "root_job_ambiguous": conflict, "runtime_root_state": "CONFLICT" if conflict else "RESOLVED" if resolved else "UNKNOWN", "status": root.get("status"), "orchestration_role": root.get("orchestration_role"), "plan_step_id": root.get("plan_step_id"), "depth": root.get("depth"), "title": None, "armed": armed, "submission_availability": availability, "capability": dict(_map(fabric.get("capability"))), "evidence": _evidence("executive_os", resolved, "mission", fabric.get("generated_at"))}, "principal": {"accountable_seat": autonomy.get("accountable_seat"), "current_worker": autonomy.get("current_worker"), "current_sol_target": autonomy.get("current_sol_target"), "owed_turn": autonomy.get("owed_turn"), "evidence": _evidence("steward", work_ref, "principal", control.get("generated_at"))}, "children": child_section, "execution": {"state": execution, "summary_present": bool(result.get("summary")), "artifacts": [], "errors_present": bool(result.get("errors")), "next_actions": [], "evidence": _evidence("executive_os", resolved, "execution", fabric.get("generated_at"))}, "review": {"required": review.get("required") if type(review.get("required")) is bool else None, "reviews_job_id": review.get("reviews_job_id"), "verdict": verdict, "evidence": _evidence("executive_os", resolved, "review", fabric.get("generated_at"))}, "transport": {"dispatch_state": dispatch_state, "reason": dispatch.get("reason"), "actionable": dispatch.get("actionable") is True, "historical": historical, "watch_proven": dispatch.get("watch_proven") if type(dispatch.get("watch_proven")) is bool else None, "carrier": dispatch.get("carrier"), "w3c": dispatch.get("w3c"), "evidence": _evidence("wake", resolved, "transport", control.get("generated_at"))}, "acceptance": acceptance, "posture": {"value": posture, "rule": rule, "evidence": []}, "conversation": _section("NOT_PROJECTED", "NOT_PROJECTED", ["MISSION_TREE_SUBSLICE_EXCLUDES_CONTENT"], None, [], None), "missingness": missing, "degraded": degraded, "budget": {}, "feature_gates": {"conversation": "UNAVAILABLE", "actions": "READ_ONLY", "advanced": "AVAILABLE"}}
    return doc
