"""H24-06: bounded, stateless operator cards over authorized owner reads.

The host verifies signed Workspace requests and revalidates EACH principal's
grant before releasing these bytes. This function neither authenticates a
caller nor acquires/caches a source. Mission v3 is the primary input; optional
results use the existing compound Mission/Result read and product acceptance
uses the complete Mission v4 companion. No command, wake, or decision is sent.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from common import executive_workspace_mission_result_contract as pair_contract
from common import product_acceptance_read_contract as acceptance_contract
from common.executive_workspace_contract import (
    MAX_RESPONSE_BYTES, MAX_RESULT_RESPONSE_BYTES, RESULT_BODY_SCHEMA,
    RESULT_OBSERVATION_SCHEMA, PROJECTION_SCHEMA, canonical, v2_selection,
    _check_job_id, _check_attempt_id,
)
from control_plane import mission_workspace as owner
from integrations.secretary_team_access.mission import (
    LOCAL_FRESHNESS_GUARD_SECONDS, _consumed_facts, _fingerprint_facts, _parse_utc,
)

SCHEMA = "mastermind.secretary_team_operator_view.v1"
MAX_CARDS = 32
DEFAULT_CARDS = 8
MAX_OUTPUT_BYTES = 32_768
MAX_INPUT_NODES = 30_000
MAX_INPUT_DEPTH = 32
MAX_RESULT_PAIRS = owner.FABRIC_V3_MAX_INCLUDED_SLOTS
_HEX = re.compile(r"^[0-9a-f]{64}$")
DISPLAY_ACTIONS = (
    "Inspect evidence", "Inspect result", "Review result", "Review rejection",
    "Inspect lineage", "Reconcile source", "Inspect acceptance",
)

# The exact currentness sub-schema is public adoption data, not a permission
# or lifecycle contract. The complete view/card contract is in H24_TEAM_OPERATOR_VIEW.md.
CURRENTNESS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["state", "owner_state", "freshness", "generated_at", "age_seconds",
                 "guard_seconds", "reason_codes"],
    "properties": {
        "state": {"enum": sorted(owner.READ_STATES)},
        "owner_state": {"enum": sorted(owner.READ_STATES)},
        "freshness": {"enum": ["FRESH", "AGED", "UNKNOWN", "FUTURE"]},
        "generated_at": {"type": ["string", "null"]},
        "age_seconds": {"type": ["integer", "null"], "minimum": 0},
        "guard_seconds": {"const": LOCAL_FRESHNESS_GUARD_SECONDS},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
    },
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _closed(value: Any, keys: Any, reason: str) -> dict:
    _require(type(value) is dict and set(value) == set(keys), reason)
    return value


def _bounded_json(value: Any, limit: int, reason: str) -> Any:
    """Bound shape before serialization; detach inputs and reject custom objects."""
    try:
        stack, count, size = [(value, 0)], 0, 1  # Include the socket's trailing LF.
        while stack:
            item, depth = stack.pop()
            count += 1
            _require(count <= MAX_INPUT_NODES and depth <= MAX_INPUT_DEPTH, reason)
            if type(item) is dict:
                _require(all(type(k) is str and len(k) <= 256 for k in item), reason)
                _require(count + len(stack) + len(item) <= MAX_INPUT_NODES, reason)
                size += 2 + max(0, len(item) - 1)
                for key in item:
                    size += len(canonical(key)) + 1
                    _require(size <= limit, reason)
                stack.extend((v, depth + 1) for v in item.values())
            elif type(item) is list:
                _require(count + len(stack) + len(item) <= MAX_INPUT_NODES, reason)
                size += 2 + max(0, len(item) - 1)
                stack.extend((v, depth + 1) for v in item)
            else:
                if type(item) is str:
                    _require(len(item) <= limit - size, reason)
                elif type(item) is float:
                    _require(math.isfinite(item), reason)
                else:
                    _require(item is None or type(item) in (bool, int), reason)
                size += len(canonical(item))
            _require(size <= limit, reason)
        # Repeated references count at every occurrence above. A large shared
        # string cannot expand into an unbounded temporary JSON allocation here.
        raw = canonical(value)
        _require(len(raw) + 1 <= limit, reason)
        return json.loads(raw)
    except (TypeError, OverflowError, RecursionError, UnicodeError):
        raise ValueError(reason) from None


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _hash(value: Any) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _generation(value: Any, *, same: bool = False) -> dict:
    value = _closed(value, owner.FABRIC_V3_GENERATION_KEYS, "invalid_generation")
    _require(value["schema"] == owner.RUNTIME_OBSERVATION_SCHEMA, "invalid_generation")
    _require(type(value["state"]) is str and value["state"] in owner.OWNER_OBSERVATION_STATES,
             "invalid_generation")
    _require(value["source_identity"] is None or (
        type(value["source_identity"]) is str and 1 <= len(value["source_identity"]) <= 128),
        "invalid_generation")
    _require(all(value[k] is None or _count(value[k]) for k in ("before", "after")),
             "invalid_generation")
    if same or value["state"] == "SAME":
        _require(value["state"] == "SAME" and type(value["source_identity"]) is str
                 and 1 <= len(value["source_identity"]) <= 128
                 and _count(value["before"]) and value["before"] == value["after"],
                 "unqualified_generation")
    return value


def _observation_facts(observation: Any, selected: dict) -> dict:
    """Consume nullable owner receipts without manufacturing replacement receipts."""
    observation = _closed(observation, owner.OWNER_OBSERVATION_KEYS, "invalid_observation")
    _require(observation["schema"] == owner.OWNER_OBSERVATION_SCHEMA
             and observation["selection"] == selected
             and type(observation["state"]) is str
             and observation["state"] in owner.OWNER_OBSERVATION_STATES, "invalid_observation")
    control, runtime = observation["control_room"], observation["runtime"]
    if observation["state"] == "UNKNOWN":
        _require(control is None and runtime is None, "invalid_unknown_observation")
    if observation["state"] == "SAME":
        _require(control is not None and runtime is not None, "unqualified_current_mission")
    if control is not None:
        _closed(control, owner.OWNER_OBSERVATION_CONTROL_ROOM_KEYS, "invalid_control_observation")
        for key in ("instance_before", "instance_after"):
            _require(control[key] is None or (type(control[key]) is str
                     and owner._OPAQUE_REF.fullmatch(control[key]) is not None),
                     "invalid_control_observation")
        for key in ("publication_before", "publication_after"):
            _require(control[key] is None or (_count(control[key]) and control[key] >= 1),
                     "invalid_control_observation")
        for key in ("document_digest", "source_validity_digest", "cache_currentness_digest"):
            _require(control[key] is None or _hash(control[key]), "invalid_control_observation")
    if runtime is not None:
        _closed(runtime, owner.OWNER_OBSERVATION_RUNTIME_KEYS, "invalid_runtime_observation")
        _generation({k: runtime[k] for k in owner.FABRIC_V3_GENERATION_KEYS})
        _require(runtime["snapshot_digest"] is None or _hash(runtime["snapshot_digest"]),
                 "invalid_runtime_observation")
    control, runtime = control or {}, runtime or {}
    return {"state": observation["state"], "runtime_state": runtime.get("state", "UNKNOWN"),
            "runtime_source_identity": runtime.get("source_identity"),
            "runtime_snapshot_digest": runtime.get("snapshot_digest"),
            "control_room_document_digest": control.get("document_digest"),
            "source_validity_digest": control.get("source_validity_digest"),
            "cache_currentness_digest": control.get("cache_currentness_digest")}


def _mission(body: dict, selected: dict) -> dict:
    _closed(body, owner.OUTPUT_KEYS_V3, "invalid_mission_shape")
    _closed(body.get("source"), owner.SOURCE_KEYS_V2, "invalid_mission_source")
    observation = body["source"]["owner_observation"]
    observed = _observation_facts(observation, selected)
    # The incumbent summary assumes non-null subreceipts. Reuse all its other
    # consumed-field checks and consume the owner's nullable subreceipts here.
    # The original body remains unchanged for digests and compound association.
    consumed_body = {**body, "source": {k: v for k, v in body["source"].items()
                                      if k != "owner_observation"}}
    facts = _consumed_facts(consumed_body, selected)
    facts["source"]["owner_observation"] = observed
    _require(body["acceptance"]["state"] == "NOT_PROJECTED", "v3_cannot_accept")
    runtime = observation["runtime"]
    generation = ({k: runtime[k] for k in owner.FABRIC_V3_GENERATION_KEYS}
                  if runtime is not None else None)
    index = body["result_refs"]
    if index["availability"] != "UNAVAILABLE":
        _require(facts["read_state"]["state"] == "CURRENT"
                 and observation["state"] == "SAME", "noncurrent_result_refs")
        _generation(generation, same=True)
        _require(index["generation"] == generation, "source_generation_mismatch")
        _require(_hash(index["snapshot_digest"])
                 and index["snapshot_digest"] == runtime["snapshot_digest"],
                 "source_digest_mismatch")
    else:
        _require(not index["refs"] and not index["absent_job_ids"]
                 and not index["omitted_job_ids"], "unavailable_result_refs")
    if facts["read_state"]["state"] == "CURRENT":
        _require(observation["state"] == "SAME", "unqualified_current_mission")
        _generation(generation, same=True)
        control = observation["control_room"]
        _require(type(control["instance_before"]) is str
                 and bool(control["instance_before"])
                 and control["instance_before"] == control["instance_after"]
                 and _count(control["publication_before"])
                 and control["publication_before"] == control["publication_after"]
                 and all(_hash(control[k]) for k in (
                     "document_digest", "source_validity_digest", "cache_currentness_digest"))
                 and _hash(runtime["snapshot_digest"]), "unqualified_current_mission")
        _require(body["mission"]["root_job_id"] == selected["root_job_id"]
                 and body["mission"]["runtime_root_state"] == "RESOLVED"
                 and body["mission"]["root_job_ambiguous"] is False,
                 "unqualified_mission_root")
    for name in ("total_count", "overflow_count", "unjoined_job_count"):
        _require(body["children"][name] is None or _count(body["children"][name]),
                 "invalid_coverage_count")
    rows = facts["children"]["rows"]
    _require(len(rows) < MAX_CARDS, "too_many_children")
    _require(body["children"]["total_count"] is None
             or body["children"]["total_count"] >= len(rows), "invalid_coverage_count")
    seen = {selected["root_job_id"]}
    for row in rows:
        _require(_check_job_id(row["job_id"]) and row["job_id"] not in seen,
                 "duplicate_or_invalid_job")
        seen.add(row["job_id"])
        _require(row["parent_job_id"] is None or _check_job_id(row["parent_job_id"]),
                 "invalid_parent")
        _require(row["depth"] is None or _count(row["depth"]), "invalid_depth")
        _require(row["status"] is None or row["status"] in owner.JOB_STATES,
                 "invalid_job_status")
        attempt = row["latest_attempt"]
        _require(row["current_attempt_id"] is None
                 or _check_attempt_id(row["current_attempt_id"]), "invalid_attempt")
        if attempt is not None:
            _require(_check_attempt_id(attempt["attempt_id"])
                     and attempt["attempt_id"] == row["current_attempt_id"]
                     and attempt["status"] in owner.ATTEMPT_STATES, "attempt_mismatch")
            for key in ("started_at", "finished_at"):
                _require(attempt[key] is None or _parse_utc(attempt[key]) is not None,
                         "invalid_lifecycle_time")
    for ref in index["refs"]:
        _require(_check_job_id(ref["job_id"]) and _check_attempt_id(ref["attempt_id"]),
                 "invalid_result_reference")
        row = next((r for r in rows if r["job_id"] == ref["job_id"]), None)
        if row is not None:
            _require(row["orchestration_role"] == ref["orchestration_role"]
                     and row["current_attempt_id"] == ref["attempt_id"], "reference_mismatch")
    return facts


def _currentness(body: dict, now: float) -> dict:
    stamp = _parse_utc(body["generated_at"])
    age = None if stamp is None or stamp > now else int(now - stamp)
    freshness = ("UNKNOWN" if stamp is None else "FUTURE" if stamp > now else
                 "AGED" if now - stamp > LOCAL_FRESHNESS_GUARD_SECONDS else "FRESH")
    state = body["read_state"]["state"]
    reasons = list(body["read_state"]["reason_codes"])
    if freshness in ("UNKNOWN", "FUTURE"):
        state = "UNAVAILABLE"
        reasons.append("SOURCE_TIME_" + freshness)
    elif freshness == "AGED" and state != "UNAVAILABLE":
        state = "HISTORICAL"
        reasons.append("LOCAL_FRESHNESS_EXPIRED")
    if body["source"]["owner_observation"]["state"] != "SAME":
        state = "UNAVAILABLE"
        reasons.append("SOURCE_OBSERVATION_UNQUALIFIED")
    if state == "CURRENT" and (
        body["children"]["coverage"] not in ("COMPLETE", "NOT_APPLICABLE")
        or body["children"]["overflow_count"] not in (0,)
        or body["children"]["unjoined_job_count"] not in (0,)
        or body["result_refs"]["availability"] != "AVAILABLE"
    ):
        state = "PARTIAL"
        reasons.append("OBSERVATION_INCOMPLETE")
    return {"state": state, "owner_state": body["read_state"]["state"],
            "freshness": freshness, "generated_at": (
                body["generated_at"] if type(body["generated_at"]) is str else None),
            "age_seconds": age, "guard_seconds": LOCAL_FRESHNESS_GUARD_SECONDS,
            "reason_codes": sorted(set(reasons))}


def _wake(body: dict) -> dict:
    transport = body["transport"]
    wake = transport.get("w3c")
    result = {"scope": "MISSION", "dispatch_state": transport["dispatch_state"],
              "historical": transport["historical"], "watch_proven": transport["watch_proven"],
              "w3c_state": None, "wake_state": None, "terminal_state": None, "terminal_applied": None,
              "source_receipt": None, "result_consumption": "UNPROVEN"}
    if wake is not None:
        _closed(wake, owner.W3C_KEYS, "invalid_wake")
        for key, allowed in (("state", owner.W3C_STATES),
                             ("wake_state", owner.W3C_WAKE_STATES),
                             ("terminal_state", owner.W3C_TERMINAL_STATES)):
            _require(wake[key] is None or (type(wake[key]) is str and wake[key] in allowed),
                     "invalid_wake")
        _require(wake["terminal_applied"] is None or type(wake["terminal_applied"]) is bool,
                 "invalid_wake")
        receipt = wake["source_receipt"]
        if receipt is not None:
            _closed(receipt, owner.W3C_RECEIPT_KEYS, "invalid_wake_receipt")
            qualified, invalid = owner._project_w3c_receipt(receipt)
            _require(not invalid and qualified == receipt, "invalid_wake_receipt")
        for key in ("wake_state", "terminal_state", "terminal_applied", "source_receipt"):
            result[key] = wake[key]
        result["w3c_state"] = wake["state"]
    return result


def _result_pairs(body: dict, selected: dict, pairs: Any) -> dict:
    _require(type(pairs) in (list, tuple) and len(pairs) <= MAX_RESULT_PAIRS,
             "too_many_result_pairs")
    refs = {row["job_id"]: row for row in body["result_refs"]["refs"]}
    results = {}
    for original in pairs:
        pair = _bounded_json(original, MAX_RESPONSE_BYTES, "result_pair_over_budget")
        pair_contract.validate_body(pair)
        pick = v2_selection(pair["selection"], "result")
        _require(all(pick[k] == selected[k] for k in selected), "foreign_result")
        _require(pick["job_id"] not in results, "duplicate_result")
        ref = refs.get(pick["job_id"])
        _require(ref is not None and all(pick[k] == ref[k] for k in (
            "root_job_id", "job_id", "attempt_id", "result_envelope_digest")),
            "result_reference_mismatch")
        if pair["availability"] == "UNAVAILABLE":
            results[pick["job_id"]] = {"state": "UNAVAILABLE",
                "reason_codes": sorted(pair["reason_codes"]), "review": None}
            continue
        _require(canonical(pair["mission"]) == canonical(body), "result_mission_mismatch")
        role_body = pair["role_result"]
        _bounded_json({"ok": True, "result": role_body}, MAX_RESULT_RESPONSE_BYTES,
                      "result_over_budget")
        _closed(role_body, ("schema", "selection", "availability", "reason_codes",
                            "source_observation", "result"), "invalid_result")
        _require(role_body["schema"] == RESULT_BODY_SCHEMA
                 and role_body["selection"] == pick, "foreign_result")
        obs = _closed(role_body["source_observation"], owner.OWNER_OBSERVATION_KEYS,
                      "invalid_result_observation")
        _require(obs["schema"] == RESULT_OBSERVATION_SCHEMA
                 and obs["state"] == "SAME" and obs["selection"] == pick,
                 "invalid_result_observation")
        generation = _generation(obs["runtime"], same=True)
        mission_obs = body["source"]["owner_observation"]
        _require(body["read_state"]["state"] == "CURRENT"
                 and obs["control_room"] == mission_obs["control_room"]
                 and generation == body["result_refs"]["generation"],
                 "result_source_mismatch")
        value = _closed(role_body["result"], (
            "schema", "selection", "role", "execution_status", "acceptance",
            "role_result_digest", "generation", "availability", "content_complete",
            "review", "counts", "content", "omitted"), "invalid_result_projection")
        _require(value["schema"] == PROJECTION_SCHEMA
                 and value["selection"] == {k: pick[k] for k in pick if k != "work_ref"}
                 and value["role"] == ref["orchestration_role"]
                 and value["execution_status"] == "COMPLETED"
                 and value["acceptance"] == "NOT_PROJECTED"
                 and value["generation"] == generation and _hash(value["role_result_digest"]),
                 "invalid_result_projection")
        available = value["availability"]
        _require(available in ("AVAILABLE", "CONTENT_OVER_BUDGET")
                 and role_body["availability"] == available
                 and value["content_complete"] is (available == "AVAILABLE"),
                 "invalid_result_availability")
        expected_reasons = [] if available == "AVAILABLE" else ["CONTENT_OVER_BUDGET"]
        _require(role_body["reason_codes"] == expected_reasons, "invalid_result_availability")
        if available == "AVAILABLE":
            content = _closed(value["content"], ("role_result", "summary", "next_actions"),
                              "invalid_result_content")
            _require(type(content["role_result"]) is dict and value["omitted"] == []
                     and _digest(content["role_result"])
                     == value["role_result_digest"], "result_content_digest_mismatch")
        else:
            _require(value["content"] is None
                     and value["omitted"] == ["role_result", "summary", "next_actions"],
                     "invalid_result_content")
        review = value["review"]
        if value["role"] == "review":
            _closed(review, ("verdict", "reviewed_job_id", "reviewed_attempt_id",
                             "reviewed_result_digest", "latest_revision_currentness"),
                    "invalid_review")
            _require(review["verdict"] in ("approve", "reject")
                     and _check_job_id(review["reviewed_job_id"])
                     and _check_attempt_id(review["reviewed_attempt_id"])
                     and _hash(review["reviewed_result_digest"])
                     and review["latest_revision_currentness"] == "UNPROVEN", "invalid_review")
            if available == "AVAILABLE":
                _require(all(review[k] == value["content"]["role_result"].get(k)
                             for k in review if k != "latest_revision_currentness"),
                         "review_content_mismatch")
        else:
            _require(review is None, "invalid_review")
        results[pick["job_id"]] = {"state": available, "reason_codes": expected_reasons,
            "role_result_digest": value["role_result_digest"], "review": review}
    return results


def _acceptance(body: dict, selected: dict, companion: Any, request_message_key: Any) -> dict:
    if companion is None:
        _require(request_message_key is None, "acceptance_companion_required")
        return {"state": "NOT_PROJECTED", "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"],
                "receipt": None}
    value = _bounded_json(companion, MAX_RESPONSE_BYTES, "acceptance_over_budget")
    _closed(value, ("schema", "mission", "product_acceptance"), "invalid_acceptance_companion")
    _require(value["schema"] == acceptance_contract.MISSION_SCHEMA
             and canonical(value["mission"]) == canonical(body), "acceptance_mission_mismatch")
    pick = {**selected, "request_message_key": request_message_key}
    view = acceptance_contract.validate_view(value["product_acceptance"], selected=pick)
    if view["state"] == "ACCEPTED":
        index = body["result_refs"]
        receipt = view["receipt"]
        refs = {r["job_id"]: r for r in index["refs"]}
        parent, subject = refs.get(selected["root_job_id"]), refs.get(receipt["subject_job_id"])
        _require(body["read_state"]["state"] == "CURRENT"
                 and index["availability"] == "AVAILABLE" and index["truncated"] is False
                 and not index["omitted_job_ids"] and parent is not None and subject is not None
                 and parent["attempt_id"] == receipt["parent_attempt_id"]
                 and parent["result_envelope_digest"] == receipt["parent_result_envelope_digest"]
                 and subject["result_envelope_digest"] == receipt["subject_result_envelope_digest"],
                 "acceptance_reference_mismatch")
    return {k: view[k] for k in ("state", "reason_codes", "receipt")}


def _cards(body: dict, facts: dict, results: dict, acceptance: dict, currentness: dict) -> list[dict]:
    root = facts["mission"]["root_job_id"]
    rows = list(facts["children"]["rows"])
    if root is not None:
        depth = body["mission"].get("depth")
        _require(depth is None or _count(depth), "invalid_depth")
        rows.append({"job_id": root, "parent_job_id": None, "depth": depth,
                     "orchestration_role": facts["mission"]["orchestration_role"],
                     "status": facts["mission"]["status"], "current_attempt_id": None,
                     "latest_attempt": None})
    by_id = {r["job_id"]: r for r in rows}
    refs = {r["job_id"]: r for r in body["result_refs"]["refs"]}
    cards = []
    fresh = currentness["state"] in ("CURRENT", "PARTIAL") and currentness["freshness"] == "FRESH"
    for row in sorted(rows, key=lambda r: (r["depth"] is None, r["depth"] or 0, r["job_id"])):
        job, parent = row["job_id"], row["parent_job_id"]
        visited, cursor = {job}, parent
        while cursor in by_id:
            _require(cursor not in visited, "cyclic_lineage")
            visited.add(cursor)
            cursor = by_id[cursor]["parent_job_id"]
        lineage = "ROOT" if job == root else "MISSING_PARENT" if parent not in by_id else "JOINED"
        if lineage == "JOINED":
            pdepth = by_id[parent]["depth"]
            if pdepth is not None and row["depth"] is not None and row["depth"] != pdepth + 1:
                lineage = "DEPTH_CONFLICT"
        attempt = row["latest_attempt"]
        start = "OBSERVED" if attempt is not None and (
            attempt["started_at"] is not None or attempt["status"] == "RUNNING") else "UNPROVEN"
        reference = refs.get(job)
        result = results.get(job)
        result_state = (result["state"] if result else "REFERENCE_ONLY" if reference else
                        "ABSENT_IN_SNAPSHOT" if job in body["result_refs"]["absent_job_ids"] else
                        "OMITTED" if job in body["result_refs"]["omitted_job_ids"] else "UNAVAILABLE")
        accepted = acceptance["receipt"] is not None and acceptance["receipt"]["subject_job_id"] == job
        review = result.get("review") if result else None
        reasons = []
        if review and review["verdict"] == "reject":
            reasons.append("REVIEW_REJECTED")
        if lineage not in ("ROOT", "JOINED"):
            reasons.append(lineage)
        if row["status"] in ("FAILED", "LOST", "RATE_LIMITED"):
            reasons.append("EXECUTION_" + row["status"])
        if job == root and facts["principal"]["owed_turn"] is not None:
            reasons.append("OWNER_OWES_TURN")
        actions = ["Inspect evidence"]
        if reference:
            actions.append("Inspect result")
        if result and result["state"] == "AVAILABLE":
            actions.append("Review rejection" if review and review["verdict"] == "reject" else "Review result")
        if lineage not in ("ROOT", "JOINED"):
            actions.append("Inspect lineage")
        if not fresh:
            actions.append("Reconcile source")
        if accepted:
            actions.append("Inspect acceptance")
        cards.append({
            "job_id": job, "original_root_job_id": body["result_refs"]["root_job_id"],
            "parent_job_id": parent, "depth": row["depth"], "lineage": lineage,
            "role": row["orchestration_role"], "job_state": row["status"],
            "current_attempt_id": row["current_attempt_id"], "latest_attempt": attempt,
            "start_evidence": start, "currentness": currentness["state"],
            "effects": {"state": None, "reason_code": "PER_JOB_EFFECT_NOT_PROJECTED"},
            "placement": {"state": "UNAVAILABLE", "reason_code": "PLACEMENT_NOT_PROJECTED"},
            "result": {"state": result_state, "reference": reference,
                       "reason_codes": result["reason_codes"] if result else [],
                       "role_result_digest": result.get("role_result_digest") if result else None,
                       "review": review, "consumption": "PROVEN_BY_ACCEPTANCE_OWNER" if accepted else "UNPROVEN"},
            "product_acceptance": {"state": "ACCEPTED" if accepted else "NOT_PROJECTED",
                                   "accepted": True if accepted else None,
                                   "current": bool(accepted and fresh)},
            "decision_needed": bool(reasons) if fresh else None,
            "decision_reason_codes": sorted(reasons), "display_actions": actions,
        })
    return cards


def project_team(
    mission: Any, *, selection: dict, now: float,
    result_pairs: tuple | list = (), acceptance_companion: Any = None,
    request_message_key: str | None = None, previous_fingerprint: str | None = None,
    limit: int = DEFAULT_CARDS, suppress_unchanged_details: bool = True,
) -> dict:
    """Project authorized owner bytes; fail closed on foreign or over-budget joins.

    ``selection`` and ``request_message_key`` must come from the host's original
    request, not from the response being checked. The host must not serve cached
    projection bytes after denial/revocation. Fingerprints are view comparisons,
    never authorization, a durable cursor, or a wake/dispatch permission.
    """
    selected = v2_selection(selection, "mission_v3")
    _require(type(now) in (int, float), "invalid_now")
    try:
        clock = float(now)
    except OverflowError:
        raise ValueError("invalid_now") from None
    _require(math.isfinite(clock), "invalid_now")
    _require(type(limit) is int and 0 <= limit <= MAX_CARDS, "invalid_limit")
    _require(type(suppress_unchanged_details) is bool, "invalid_detail_policy")
    _require(previous_fingerprint is None or _hash(previous_fingerprint), "invalid_previous_fingerprint")
    body = _bounded_json(mission, MAX_RESPONSE_BYTES, "mission_over_budget")
    facts = _mission(body, selected)
    currentness = _currentness(body, clock)
    wake = _wake(body)
    results = _result_pairs(body, selected, result_pairs)
    acceptance = _acceptance(body, selected, acceptance_companion, request_message_key)
    cards = _cards(body, facts, results, acceptance, currentness)
    if any(c["lineage"] in ("MISSING_PARENT", "DEPTH_CONFLICT") for c in cards):
        if currentness["state"] == "CURRENT":
            currentness["state"] = "PARTIAL"
            currentness["reason_codes"].append("LINEAGE_INCOMPLETE")
            for card in cards:
                card["currentness"] = "PARTIAL"
    semantic_wake = {k: v for k, v in wake.items() if k != "source_receipt"}
    if wake["source_receipt"] is not None:
        semantic_wake["source_receipt"] = {k: v for k, v in wake["source_receipt"].items()
                                           if k != "observed_at"}
    semantics = {"schema": SCHEMA, "selection": selected,
                 "facts": _fingerprint_facts(facts), "cards": cards,
                 "currentness": {k: v for k, v in currentness.items()
                                 if k not in ("generated_at", "age_seconds")},
                 "wake": semantic_wake, "acceptance": acceptance}
    fingerprint = _digest(semantics)
    changed = None if previous_fingerprint is None else fingerprint != previous_fingerprint
    suppress = changed is False and suppress_unchanged_details
    visible = [] if suppress else cards[:limit]
    known = {card["job_id"] for card in visible}
    children = facts["children"]
    refs = facts["result_refs"]
    coverage = {
        "scope": "SINGLE_AUTHORIZED_MISSION", "full_fleet": False,
        "children_state": children["state"], "children_coverage": children["coverage"],
        "children_total_count": children["total_count"],
        "children_returned_count": children["row_count"],
        "source_omitted_child_count": children["overflow_count"],
        "unjoined_job_count": children["unjoined_job_count"],
        "unjoined_job_ids": children["unjoined_job_ids"][:MAX_CARDS],
        "unjoined_ids_omitted_count": max(0, len(children["unjoined_job_ids"]) - MAX_CARDS),
        "result_ref_availability": refs["availability"], "result_ref_count": refs["row_count"],
        "result_details_provided": len(results),
        "qualified_result_count": sum(r["state"] in ("AVAILABLE", "CONTENT_OVER_BUDGET")
                                      for r in results.values()),
        "result_absent_count": refs["absent_count"], "result_omitted_count": refs["omitted_count"],
        "result_omitted_job_ids": refs["omitted_job_ids"], "result_refs_truncated": refs["truncated"],
        "cards_in_snapshot": len(cards), "cards_visible": len(visible),
        "display_omitted_count": len(cards) - min(limit, len(cards)),
        "unchanged_suppressed_count": min(limit, len(cards)) if suppress else 0,
        "unseen_population": "UNKNOWN",
        "missingness_count": len(facts["coverage"]["missingness_rows"]),
    }
    output = {
        "schema": SCHEMA, "selection": selected, "currentness": currentness,
        "source": {"owner": "WORKSPACE_MISSION_V3", "mission_digest": _digest(body),
                   "snapshot_digest": refs["snapshot_digest"],
                   "control_room_document_digest": facts["source"]["owner_observation"]["control_room_document_digest"],
                   "source_coverage": facts["source"]["source_coverage"]},
        "fingerprint": fingerprint, "changed": changed,
        "attention": {"reasoning_wake_recommended": changed is True, "dispatch_permitted": False},
        "coverage": coverage, "cards": visible,
        "hierarchy": [{"job_id": card["job_id"], "parent_job_id": card["parent_job_id"],
                       "parent_visible": card["parent_job_id"] in known}
                      for card in visible],
        "principal": facts["principal"], "transport": wake, "acceptance": acceptance,
        "missingness": facts["coverage"]["missingness_rows"][:MAX_CARDS],
        "missingness_omitted_count": max(0, len(facts["coverage"]["missingness_rows"]) - MAX_CARDS),
        "display_only": True, "details_included": not suppress,
    }
    return _bounded_json(output, MAX_OUTPUT_BYTES, "projection_over_budget")


def render_operator_text(view: dict) -> str:
    """Compact accessible text for one projection; text contains no command links."""
    _require(type(view) is dict and view.get("schema") == SCHEMA, "invalid_operator_view")
    rows = [f"{view['selection']['work_ref']} / {view['selection']['root_job_id']} — "
            f"{view['currentness']['state']} (owner {view['currentness']['owner_state']})"]
    for card in view["cards"]:
        parent = card["parent_job_id"] or "root"
        verdict = card["result"]["review"]
        review = f"; review {verdict['verdict']}" if verdict else ""
        rows.append(f"{card['job_id']} [{card['role']}] parent={parent} depth={card['depth']} "
                    f"{card['job_state']}; start {card['start_evidence']}; "
                    f"result {card['result']['state']}{review}; "
                    f"acceptance {card['product_acceptance']['state']}; "
                    f"consumption {card['result']['consumption']}; lineage {card['lineage']}")
    coverage = view["coverage"]
    rows.append(f"Coverage: {coverage['cards_visible']}/{coverage['cards_in_snapshot']} cards; "
                f"source omitted={coverage['source_omitted_child_count']}; "
                f"unjoined={coverage['unjoined_job_count']}; unseen population UNKNOWN")
    if coverage["unchanged_suppressed_count"]:
        rows.append(f"Details unchanged; {coverage['unchanged_suppressed_count']} cards suppressed; "
                    "source coverage retained.")
    rows.append(f"Mission delivery: {view['transport']['dispatch_state']}; "
                f"wake={view['transport']['wake_state']}; per-result consumption stays separate")
    rows.append("Display only. Each principal's host revalidates access; no action is dispatched.")
    return "\n".join(rows)
