"""Bounded shared-team Mission v3 projection for the Secretary access lane.

Pure reduction of one already-composed public ``mastermind.mission_workspace.v3``
body into a compact summary two Workspace members can share.  The module owns
no IO, state, scheduler, model, authentication, acceptance, routing, cursor or
wake permission: the Workspace read service and its owners keep every original
semantic, and a revoked grant can never be upgraded here.  The validator below
covers only the fields this projection consumes — it is not a whole public
response decoder — and unknown schema, mismatched selection or malformed
consumed fields refuse before any output is produced.  Raw payloads are never
serialized through; only the closed bounded fields listed below are emitted.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from collections.abc import Mapping
from typing import Any

from common.executive_workspace_contract import bounded_canonical, canonical, v2_selection
from control_plane.mission_workspace import (
    ATTEMPT_KEYS,
    CHILDREN_KEYS,
    CHILD_ITEM_KEYS,
    COVERAGE_STATES,
    CARRIER_KEYS,
    EXECUTION_STATES_V2,
    JOB_STATES,
    MISSINGNESS_KEYS,
    ORCHESTRATION_ROLES,
    OWNER_OBSERVATION_CONTROL_ROOM_KEYS,
    OWNER_OBSERVATION_KEYS,
    OWNER_OBSERVATION_RUNTIME_KEYS,
    OWNER_OBSERVATION_STATES,
    OWED_TURN_KEYS,
    PROJECTED_DISPATCH_STATES,
    READ_STATE_KEYS,
    READ_STATES,
    RUNTIME_CARD_KEYS,
    SCHEMA_V3,
    SECTION_STATES,
    _validate_result_reference_index,
)

SUMMARY_SCHEMA = "mastermind.secretary_team_mission_summary.v1"
#: Fixed output ceiling for one summary serialization (UTF-8, canonical form).
SUMMARY_MAX_BYTES = 16_384
#: Fixed row cap for any bounded list; ``limit`` selects the display window.
MAX_ROWS = 32
DEFAULT_ROWS = 8
#: Conservative local-only freshness guard.  It is a derived diagnostic that
#: never upgrades the source owner's own read_state or freshness evidence.
LOCAL_FRESHNESS_GUARD_SECONDS = 120
_ID_MAX = 128
_TEXT_MAX = 160
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,6}))?(?:Z|\+00:00)$"
)


# ---------------------------------------------------------------------------
# Closed input validation helpers (consumed subset only).
# ---------------------------------------------------------------------------


def _map_at(container: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid_mission_body:{key}")
    return value


def _closed(container: Mapping[str, Any], key: str, keys: frozenset[str]) -> Mapping[str, Any]:
    value = _map_at(container, key)
    if set(value) != keys:
        raise ValueError(f"invalid_mission_body:{key}")
    return value


def _req_str(container: Mapping[str, Any], key: str) -> str:
    value = container.get(key)
    if type(value) is not str or not value:
        raise ValueError(f"invalid_mission_body:{key}")
    return value


def _opt_str(value: Any) -> str | None:
    return value if type(value) is str else None


def _bounded_str(value: Any, cap: int) -> str | None:
    """Producer-guaranteed ``str | None``; any other type is malformed."""

    if value is None:
        return None
    if type(value) is not str:
        raise ValueError("invalid_mission_body:field_type")
    return value[:cap]


def _req_enum(container: Mapping[str, Any], key: str, allowed: frozenset[str]) -> str:
    value = container.get(key)
    if type(value) is not str or value not in allowed:
        raise ValueError(f"invalid_mission_body:{key}")
    return value


def _opt_enum(value: Any, allowed: frozenset[str]) -> str | None:
    if value is None:
        return None
    if type(value) is str and value in allowed:
        return value
    raise ValueError("invalid_mission_body:field_enum")


def _req_bool(container: Mapping[str, Any], key: str) -> bool:
    value = container.get(key)
    if type(value) is not bool:
        raise ValueError(f"invalid_mission_body:{key}")
    return value


def _opt_bool(value: Any) -> bool | None:
    if value is None or type(value) is bool:
        return value
    raise ValueError("invalid_mission_body:field_type")


def _opt_int(value: Any) -> int | None:
    if value is None or type(value) is int:
        return value
    raise ValueError("invalid_mission_body:field_type")


def _opt_scalar(value: Any) -> str | int | bool | None:
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("invalid_mission_body:field_type")


def _str_list(container: Mapping[str, Any], key: str) -> list[str]:
    value = container.get(key)
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise ValueError(f"invalid_mission_body:{key}")
    return value


def _hex_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or _HEX_64.fullmatch(value) is None:
        raise ValueError("invalid_mission_body:digest")
    return value


def _parse_utc(value: Any) -> float | None:
    """Parse the producer's canonical UTC stamp into epoch seconds, or None."""

    text = value if type(value) is str else None
    if text is None or (match := _UTC_TIMESTAMP.fullmatch(text)) is None:
        return None
    fraction = float("0." + match.group(7)) if match.group(7) else 0.0
    moment = datetime.datetime(
        int(match.group(1)), int(match.group(2)), int(match.group(3)),
        int(match.group(4)), int(match.group(5)), int(match.group(6)),
        tzinfo=datetime.timezone.utc,
    )
    return moment.timestamp() + fraction


# ---------------------------------------------------------------------------
# Consumed-fact extraction: validate exactly what this projection consumes.
# ---------------------------------------------------------------------------


def _validate_read_state(body: Mapping[str, Any]) -> dict[str, Any]:
    read_state = _closed(body, "read_state", READ_STATE_KEYS)
    return {
        "state": _req_enum(read_state, "state", READ_STATES),
        "reason_codes": sorted(set(_str_list(read_state, "reason_codes"))),
        "usable_sections": sorted(set(_str_list(read_state, "usable_sections"))),
    }


def _validate_program(body: Mapping[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    program = _map_at(body, "program")
    work_ref = _req_str(program, "work_ref")
    if work_ref != selected["work_ref"]:
        raise ValueError("selection_mismatch:program.work_ref")
    attention_ids = sorted(set(_str_list(program, "attention_ids")))
    return {
        "work_ref": work_ref,
        "title": _bounded_str(program.get("title"), _TEXT_MAX),
        "state": _bounded_str(program.get("state"), _ID_MAX),
        "next_action": _bounded_str(program.get("next_action"), _TEXT_MAX),
        "attention_ids": attention_ids[:MAX_ROWS],
        "attention_count": len(attention_ids),
    }


def _validate_mission(body: Mapping[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    mission = _map_at(body, "mission")
    root_job_id = mission.get("root_job_id")
    if root_job_id is not None:
        if type(root_job_id) is not str:
            raise ValueError("invalid_mission_body:mission.root_job_id")
        if root_job_id != selected["root_job_id"]:
            raise ValueError("selection_mismatch:mission.root_job_id")
    candidates = _str_list(mission, "root_job_candidates")
    posture = _map_at(body, "posture")
    return {
        "root_job_id": root_job_id,
        "root_job_candidates": sorted(set(candidates))[:MAX_ROWS],
        "root_job_ambiguous": _opt_bool(mission.get("root_job_ambiguous")),
        "runtime_root_state": _bounded_str(mission.get("runtime_root_state"), _ID_MAX),
        "status": _opt_enum(mission.get("status"), JOB_STATES),
        "orchestration_role": _opt_enum(mission.get("orchestration_role"), ORCHESTRATION_ROLES),
        "posture_value": _bounded_str(posture.get("value"), _ID_MAX),
        "posture_rule": _bounded_str(posture.get("rule"), _ID_MAX),
    }


def _validate_runtime_card(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != RUNTIME_CARD_KEYS:
        raise ValueError("invalid_mission_body:principal.runtime_card")
    return {
        "worker_id": _bounded_str(value.get("worker_id"), _ID_MAX),
        "attempt_id": _bounded_str(value.get("attempt_id"), _ID_MAX),
        "status": _bounded_str(value.get("status"), _ID_MAX),
        "runtime_binding_id": _bounded_str(value.get("runtime_binding_id"), _ID_MAX),
        "binding_generation": _opt_scalar(value.get("binding_generation")),
        "continuation_state": _bounded_str(value.get("continuation_state"), _ID_MAX),
        "effect_state": _bounded_str(value.get("effect_state"), _ID_MAX),
        "capacity_state": _bounded_str(value.get("capacity_state"), _ID_MAX),
        "previous_attempt_id": _bounded_str(value.get("previous_attempt_id"), _ID_MAX),
        "movement_reason_code": _bounded_str(value.get("movement_reason_code"), _ID_MAX),
    }


def _validate_principal(body: Mapping[str, Any]) -> dict[str, Any]:
    principal = _map_at(body, "principal")
    owed_turn = principal.get("owed_turn")
    if owed_turn is not None:
        if not isinstance(owed_turn, Mapping) or set(owed_turn) != OWED_TURN_KEYS:
            raise ValueError("invalid_mission_body:principal.owed_turn")
        owed = {
            "seat": _bounded_str(owed_turn.get("seat"), _ID_MAX),
            "reason": _bounded_str(owed_turn.get("reason"), _ID_MAX),
        }
    else:
        owed = None
    return {
        "accountable_seat": _bounded_str(principal.get("accountable_seat"), _ID_MAX),
        "current_worker": _validate_runtime_card(principal.get("current_worker")),
        "current_sol_target": _validate_runtime_card(principal.get("current_sol_target")),
        "owed_turn": owed,
    }


def _validate_attempt(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != ATTEMPT_KEYS:
        raise ValueError("invalid_mission_body:children.attempt")
    return {
        "attempt_id": _bounded_str(value.get("attempt_id"), _ID_MAX),
        "attempt_number": _opt_int(value.get("attempt_number")),
        "status": _bounded_str(value.get("status"), _ID_MAX),
        # True lifecycle times stay in facts and fingerprint; only
        # per-observation stamps are excluded from change detection.
        "started_at": _opt_str(value.get("started_at")),
        "finished_at": _opt_str(value.get("finished_at")),
        "exit_code": _opt_int(value.get("exit_code")),
        "has_result": _opt_bool(value.get("has_result")),
        "error_present": _opt_bool(value.get("error_present")),
        "error_class": _bounded_str(value.get("error_class"), _ID_MAX),
    }


def _validate_children(body: Mapping[str, Any]) -> dict[str, Any]:
    children = _closed(body, "children", CHILDREN_KEYS)
    state = _req_enum(children, "state", SECTION_STATES)
    coverage = _req_enum(children, "coverage", COVERAGE_STATES)
    rows = children.get("items")
    if not isinstance(rows, list):
        raise ValueError("invalid_mission_body:children.items")
    projected = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != CHILD_ITEM_KEYS:
            raise ValueError("invalid_mission_body:children.row")
        projected.append({
            "job_id": _bounded_str(row.get("job_id"), _ID_MAX),
            "status": _bounded_str(row.get("status"), _ID_MAX),
            "parent_job_id": _bounded_str(row.get("parent_job_id"), _ID_MAX),
            "depth": _opt_int(row.get("depth")),
            "orchestration_role": _opt_enum(row.get("orchestration_role"), ORCHESTRATION_ROLES),
            "plan_step_id": _bounded_str(row.get("plan_step_id"), _ID_MAX),
            "attempt_count": _opt_int(row.get("attempt_count")),
            "attempt_limit": _opt_int(row.get("attempt_limit")),
            "current_attempt_id": _bounded_str(row.get("current_attempt_id"), _ID_MAX),
            "worker_id": _bounded_str(row.get("worker_id"), _ID_MAX),
            "latest_attempt": _validate_attempt(row.get("latest_attempt")),
        })
    projected.sort(key=lambda row: (row["job_id"] or "", row["parent_job_id"] or ""))
    unjoined_ids = _str_list(children, "unjoined_job_ids")
    return {
        "state": state,
        "coverage": coverage,
        "reason_codes": sorted(set(_str_list(children, "reason_codes"))),
        "total_count": _opt_int(children.get("total_count")),
        "overflow_count": _opt_int(children.get("overflow_count")),
        "rows": projected,
        "row_count": len(projected),
        "unjoined_job_count": _opt_int(children.get("unjoined_job_count")),
        "unjoined_job_ids": sorted(set(unjoined_ids)),
        "unjoined_visible_count": min(len(set(unjoined_ids)), MAX_ROWS),
    }


def _validate_execution(body: Mapping[str, Any]) -> dict[str, Any]:
    execution = _map_at(body, "execution")
    artifacts = execution.get("artifacts")
    next_actions = execution.get("next_actions")
    if not isinstance(artifacts, list) or not isinstance(next_actions, list):
        raise ValueError("invalid_mission_body:execution")
    return {
        "state": _opt_enum(execution.get("state"), EXECUTION_STATES_V2),
        "summary_present": _req_bool(execution, "summary_present"),
        "errors_present": _req_bool(execution, "errors_present"),
        "artifact_count": min(len(artifacts), MAX_ROWS),
        "artifact_overflow_count": max(0, len(artifacts) - MAX_ROWS),
        "next_action_count": min(len(next_actions), MAX_ROWS),
        "next_action_overflow_count": max(0, len(next_actions) - MAX_ROWS),
    }


def _validate_review(body: Mapping[str, Any]) -> dict[str, Any]:
    review = _map_at(body, "review")
    verdict = _req_str(review, "verdict")
    return {
        "required": _opt_bool(review.get("required")),
        "reviews_job_id": _bounded_str(review.get("reviews_job_id"), _ID_MAX),
        "verdict": verdict,
    }


def _validate_acceptance(body: Mapping[str, Any]) -> dict[str, Any]:
    acceptance = _map_at(body, "acceptance")
    return {
        "state": _bounded_str(acceptance.get("state"), _ID_MAX),
        "reason_codes": sorted(set(_str_list(acceptance, "reason_codes"))),
    }


def _validate_transport(body: Mapping[str, Any]) -> dict[str, Any]:
    transport = _map_at(body, "transport")
    dispatch_state = _req_str(transport, "dispatch_state")
    if (dispatch_state not in PROJECTED_DISPATCH_STATES
            and dispatch_state != "UNKNOWN"):
        raise ValueError("invalid_mission_body:transport.dispatch_state")
    carrier = transport.get("carrier")
    carrier_state = None
    if carrier is not None:
        if not isinstance(carrier, Mapping) or set(carrier) != CARRIER_KEYS:
            raise ValueError("invalid_mission_body:transport.carrier")
        carrier_state = _bounded_str(carrier.get("state"), _ID_MAX)
    return {
        "dispatch_state": dispatch_state,
        "watch_proven": _opt_bool(transport.get("watch_proven")),
        "historical": _req_bool(transport, "historical"),
        "actionable": _req_bool(transport, "actionable"),
        "carrier_state": carrier_state,
    }


def _validate_owner_observation(source: Mapping[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    observation = _closed(source, "owner_observation", OWNER_OBSERVATION_KEYS)
    state = _req_enum(observation, "state", OWNER_OBSERVATION_STATES)
    observed_selection = observation.get("selection")
    if (not isinstance(observed_selection, Mapping)
            or dict(observed_selection) != selected):
        raise ValueError("selection_mismatch:owner_observation.selection")
    receipts = _closed(observation, "control_room", OWNER_OBSERVATION_CONTROL_ROOM_KEYS)
    runtime = _closed(observation, "runtime", OWNER_OBSERVATION_RUNTIME_KEYS)
    return {
        "state": state,
        "runtime_state": _req_enum(runtime, "state", OWNER_OBSERVATION_STATES),
        "runtime_source_identity": _bounded_str(runtime.get("source_identity"), _ID_MAX),
        "runtime_snapshot_digest": _hex_or_none(runtime.get("snapshot_digest")),
        "control_room_document_digest": _hex_or_none(receipts.get("document_digest")),
        "source_validity_digest": _hex_or_none(receipts.get("source_validity_digest")),
        "cache_currentness_digest": _hex_or_none(receipts.get("cache_currentness_digest")),
    }


def _validate_source(body: Mapping[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    source = _map_at(body, "source")
    generation = source.get("source_generation")
    facts = {
        "control_room_schema": _bounded_str(source.get("control_room_schema"), _ID_MAX),
        "fabric_view_schema": _bounded_str(source.get("fabric_view_schema"), _ID_MAX),
        "source_coverage": sorted(set(_str_list(source, "source_coverage"))),
        "source_generation_state": _bounded_str(
            generation.get("state"), _ID_MAX
        ) if isinstance(generation, Mapping) else None,
    }
    if "owner_observation" in source:
        facts["owner_observation"] = _validate_owner_observation(source, selected)
    return facts


def _validate_result_refs(body: Mapping[str, Any], selected: dict[str, str]) -> dict[str, Any]:
    """The reused authoritative index validator covers this consumed section."""

    index = _validate_result_reference_index(_map_at(body, "result_refs"))
    if index["root_job_id"] != selected["root_job_id"]:
        raise ValueError("selection_mismatch:result_refs.root_job_id")
    generation = index["generation"]
    refs = [dict(row) for row in index["refs"]]
    refs.sort(key=lambda row: (row["job_id"], row["attempt_id"]))
    absent = sorted(set(index["absent_job_ids"]))
    omitted = sorted(set(index["omitted_job_ids"]))
    return {
        "availability": index["availability"],
        "truncated": index["truncated"],
        "snapshot_digest": index["snapshot_digest"],
        "generation_state": generation["state"],
        "generation_source_identity": generation.get("source_identity"),
        "rows": refs,
        "row_count": len(refs),
        "absent_job_ids": absent,
        "omitted_job_ids": omitted,
        "absent_count": len(absent),
        "omitted_count": len(omitted),
    }


def _validate_missingness(body: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    missingness = body.get("missingness")
    degraded = body.get("degraded")
    if not isinstance(missingness, list) or not isinstance(degraded, list):
        raise ValueError("invalid_mission_body:missingness")
    rows = []
    for row in missingness:
        if not isinstance(row, Mapping) or set(row) != MISSINGNESS_KEYS:
            raise ValueError("invalid_mission_body:missingness.row")
        rows.append({
            "missingness_class": _req_str(row, "missingness_class"),
            "target_field": _bounded_str(row.get("target_field"), _ID_MAX),
            "producer_owner": _bounded_str(row.get("producer_owner"), _ID_MAX),
            "reason": _bounded_str(row.get("reason"), _TEXT_MAX),
        })
    rows.sort(key=lambda row: (row["target_field"] or "", row["missingness_class"],
                               row["reason"] or ""))
    texts = []
    for item in degraded:
        if type(item) is not str:
            raise ValueError("invalid_mission_body:degraded")
        texts.append(item[:_TEXT_MAX])
    return rows, sorted(set(texts))


def _consumed_facts(body: Any, selected: dict[str, str]) -> dict[str, Any]:
    """Validate the consumed subset and return closed semantic facts."""

    if not isinstance(body, Mapping):
        raise ValueError("invalid_mission_body")
    if body.get("schema") != SCHEMA_V3:
        raise ValueError("unknown_schema")
    generated_at = body.get("generated_at")
    facts = {
        "read_state": _validate_read_state(body),
        "program": _validate_program(body, selected),
        "mission": _validate_mission(body, selected),
        "principal": _validate_principal(body),
        "children": _validate_children(body),
        "execution": _validate_execution(body),
        "review": _validate_review(body),
        "acceptance": _validate_acceptance(body),
        "transport": _validate_transport(body),
        "source": _validate_source(body, selected),
        "result_refs": _validate_result_refs(body, selected),
        "coverage": {},
    }
    facts["coverage"]["missingness_rows"], facts["coverage"]["degraded"] = (
        _validate_missingness(body))
    facts["generated_at"] = generated_at if type(generated_at) is str else None
    return facts


# ---------------------------------------------------------------------------
# Fingerprint: stateless semantic-fact digest, no per-observation churn.
# ---------------------------------------------------------------------------


def _fingerprint_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Semantic facts only: no generated_at, no before/after samples, no age."""

    source = {
        key: facts["source"][key]
        for key in ("control_room_schema", "fabric_view_schema",
                    "source_coverage", "source_generation_state")
    }
    observation = facts["source"].get("owner_observation")
    if observation is not None:
        source["owner_observation_state"] = observation["state"]
        source["runtime_state"] = observation["runtime_state"]
        # The per-observation source_identity churns between rereads of the
        # same source; the qualified snapshot digest is the stable identity.
        source["runtime_snapshot_digest"] = observation["runtime_snapshot_digest"]
        source["control_room_document_digest"] = observation["control_room_document_digest"]
        source["source_validity_digest"] = observation["source_validity_digest"]
        source["cache_currentness_digest"] = observation["cache_currentness_digest"]
    refs = facts["result_refs"]
    children = facts["children"]
    missingness_rows, degraded = facts["coverage"]["missingness_rows"], facts["coverage"]["degraded"]
    return {
        "read_state": facts["read_state"],
        "program": facts["program"],
        "mission": facts["mission"],
        "principal": facts["principal"],
        "execution": facts["execution"],
        "review": facts["review"],
        "acceptance": facts["acceptance"],
        "transport": facts["transport"],
        "children": {
            "state": children["state"], "coverage": children["coverage"],
            "reason_codes": children["reason_codes"],
            "total_count": children["total_count"],
            "overflow_count": children["overflow_count"],
            "row_count": children["row_count"],
            "unjoined_job_count": children["unjoined_job_count"],
            "unjoined_job_ids": children["unjoined_job_ids"][:MAX_ROWS],
            "unjoined_job_count_visible": children["unjoined_visible_count"],
            "rows": children["rows"][:MAX_ROWS],
        },
        "result_refs": {
            "availability": refs["availability"], "truncated": refs["truncated"],
            "snapshot_digest": refs["snapshot_digest"],
            "generation_state": refs["generation_state"],
            "rows": refs["rows"],
            "absent_job_ids": refs["absent_job_ids"],
            "omitted_job_ids": refs["omitted_job_ids"],
            "absent_count": refs["absent_count"],
            "omitted_count": refs["omitted_count"],
        },
        "missingness": {
            "row_count": len(missingness_rows),
            "rows": missingness_rows[:MAX_ROWS],
            "degraded": degraded[:MAX_ROWS],
            "degraded_count": len(degraded),
        },
        "source": source,
    }


# ---------------------------------------------------------------------------
# Summary composition.
# ---------------------------------------------------------------------------


def _local_freshness(generated_at: str | None, now: float) -> dict[str, Any]:
    stamp = _parse_utc(generated_at)
    if stamp is None:
        return {"state": "UNKNOWN", "age_seconds": None,
                "guard_seconds": LOCAL_FRESHNESS_GUARD_SECONDS}
    age = int(max(0, now - stamp))
    return {
        "state": "FRESH" if age <= LOCAL_FRESHNESS_GUARD_SECONDS else "AGED",
        "age_seconds": age,
        "guard_seconds": LOCAL_FRESHNESS_GUARD_SECONDS,
    }


def _window(items: list[Any], limit: int) -> tuple[list[Any], int]:
    return items[:limit], max(0, len(items) - limit)


def _compose_summary(
    facts: dict[str, Any], selected: dict[str, str], fingerprint: str,
    changed: bool | None, now: float, limit: int,
) -> dict[str, Any]:
    unchanged = changed is False
    read_state = facts["read_state"]
    children = facts["children"]
    refs = facts["result_refs"]
    rows, children_overflow = _window(children["rows"], limit)
    ref_rows, ref_overflow = _window(refs["rows"], limit)
    unjoined, unjoined_overflow = _window(children["unjoined_job_ids"], MAX_ROWS)
    missingness, missingness_overflow = _window(
        facts["coverage"]["missingness_rows"], MAX_ROWS)
    degraded, degraded_overflow = _window(facts["coverage"]["degraded"], MAX_ROWS)
    summary: dict[str, Any] = {
        "schema": SUMMARY_SCHEMA,
        "selection": dict(selected),
        "fingerprint": fingerprint,
        "changed": changed,
        "details_included": not unchanged,
        "read_state": read_state,
        "freshness": {
            "generated_at": facts["generated_at"],
            "owner_observation_state": (
                facts["source"]["owner_observation"]["state"]
                if "owner_observation" in facts["source"] else None),
            "runtime_source_identity": (
                facts["source"]["owner_observation"]["runtime_source_identity"]
                if "owner_observation" in facts["source"] else None),
            "runtime_snapshot_digest": (
                facts["source"]["owner_observation"]["runtime_snapshot_digest"]
                if "owner_observation" in facts["source"] else None),
            "control_room_schema": facts["source"]["control_room_schema"],
            "fabric_view_schema": facts["source"]["fabric_view_schema"],
            "source_coverage": facts["source"]["source_coverage"],
            "source_generation_state": facts["source"]["source_generation_state"],
            "local": _local_freshness(facts["generated_at"], now),
        },
        "coverage": {
            # One joined mission only — never a fleet claim.
            "scope": "single_mission",
            "full_fleet": False,
            "usable_sections": read_state["usable_sections"],
            "children": {
                "state": children["state"], "coverage": children["coverage"],
                "reason_codes": children["reason_codes"],
                "total_count": children["total_count"],
                "overflow_count": children["overflow_count"],
                "returned_count": children["row_count"],
                "display_overflow_count": children_overflow,
                "unjoined_job_count": children["unjoined_job_count"],
                "unjoined_visible_count": children["unjoined_visible_count"],
                "unjoined_overflow_count": unjoined_overflow,
            },
            "result_refs": {
                "availability": refs["availability"], "truncated": refs["truncated"],
                "returned_count": refs["row_count"],
                "display_overflow_count": ref_overflow,
                "absent_count": refs["absent_count"],
                "omitted_count": refs["omitted_count"],
            },
            "missingness_count": len(facts["coverage"]["missingness_rows"]),
            "missingness_overflow_count": missingness_overflow,
            "degraded_count": len(facts["coverage"]["degraded"]),
            "degraded_overflow_count": degraded_overflow,
        },
    }
    if unchanged:
        summary["omitted_detail_count"] = (
            children["row_count"] + refs["row_count"] + refs["absent_count"]
            + refs["omitted_count"] + len(facts["coverage"]["missingness_rows"])
            + len(facts["coverage"]["degraded"]) + 8)
        return summary
    summary["omitted_detail_count"] = 0
    summary["program"] = facts["program"]
    summary["mission"] = facts["mission"]
    summary["principal"] = facts["principal"]
    summary["execution"] = facts["execution"]
    summary["review"] = facts["review"]
    summary["acceptance"] = facts["acceptance"]
    summary["transport"] = facts["transport"]
    summary["children_rows"] = rows
    summary["result_ref_rows"] = ref_rows
    summary["unjoined_job_ids"] = unjoined
    summary["absent_job_ids"] = refs["absent_job_ids"][:MAX_ROWS]
    summary["omitted_job_ids"] = refs["omitted_job_ids"][:MAX_ROWS]
    summary["missingness_rows"] = missingness
    summary["degraded"] = degraded
    return summary


def summarize_mission(
    body: Any,
    *,
    selection: Mapping[str, Any],
    now: float,
    previous_fingerprint: str | None = None,
    limit: int = DEFAULT_ROWS,
) -> dict[str, Any]:
    """Project one public Mission v3 body into a bounded shared-team summary.

    Raises ``ValueError`` on an unknown schema, a malformed consumed field or
    any selection mismatch across program/mission/result_refs/owner
    observation, and on ``summary_over_budget`` when the fixed 16 KiB output
    ceiling cannot hold the bounded summary.  A fresh reread of the same
    source yields the same fingerprint; a change to source identity,
    qualification, coverage, native status or any consumed semantic fact
    changes it.  ``changed`` is ``None`` when no previous fingerprint was
    supplied, ``False`` suppresses detail rows (with an explicit omission
    count) while coverage and freshness stay returned.
    """

    selected = v2_selection(selection, "mission_v3")
    if type(now) not in (int, float):
        raise ValueError("invalid_now")
    if type(limit) is not int or not 0 <= limit <= MAX_ROWS:
        raise ValueError("invalid_limit")
    if previous_fingerprint is not None and (
            type(previous_fingerprint) is not str
            or _HEX_64.fullmatch(previous_fingerprint) is None):
        raise ValueError("invalid_previous_fingerprint")
    facts = _consumed_facts(body, selected)
    fingerprint = hashlib.sha256(
        canonical(_fingerprint_facts(facts))).hexdigest()
    changed = None if previous_fingerprint is None else fingerprint != previous_fingerprint
    summary = _compose_summary(facts, selected, fingerprint, changed, float(now), limit)
    try:
        bounded_canonical(summary, limit=SUMMARY_MAX_BYTES)
    except (TypeError, ValueError):
        raise ValueError("summary_over_budget") from None
    return summary
