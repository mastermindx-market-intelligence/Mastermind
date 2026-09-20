"""Pure mission-workspace reduction over already composed owner snapshots.

The reducer acquires nothing.  It consumes the Control Room and Fabric Job
View documents supplied by their owners, retains only the frozen R2A
allowlist, and fails closed when identity, freshness, or shape is not proven.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.chairman_control_room_remote import _project_agent_os_freeform


SCHEMA = "mastermind.mission_workspace.v1"
CONTROL_ROOM_SCHEMA = "mastermind.chairman_control_room.v1"
FABRIC_VIEW_SCHEMA = "mastermind.fabric_job_view.v1"
SOURCE_VALIDITY_SCHEMA = "mastermind.control_room_source_validity.v1"
SOURCE_VALIDITY_PROFILE = "b5.darwin-chrome-paired-v1"
AUTONOMY_VALIDITY_SCHEMA = "mastermind.autonomy_validity.v1"
AUTONOMY_VALIDITY_POLICY = "mapper-inclusive-48h-future-1h.v1"

READ_STATES = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
SECTION_STATES = frozenset({"AVAILABLE", "EMPTY", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})
COVERAGE_STATES = frozenset(
    {"COMPLETE", "INCOMPLETE", "HISTORICAL_ONLY", "NOT_PROJECTED", "NOT_APPLICABLE"}
)
SOURCE_ROW_STATES = frozenset(
    {"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE", "CONFLICT", "NOT_PROJECTED", "NOT_APPLICABLE"}
)
MISSINGNESS_CLASSES = frozenset(
    {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}
)
EVIDENCE_OWNERS = frozenset(
    {
        "EXECUTIVE_OS", "EXECUTIVE_INBOX", "AGENT_OS", "GITHUB", "LINEAR",
        "SLACK", "AUTONOMY_PROJECTION", "CONTROL_ROOM_CACHE", "SOURCE_VALIDITY",
    }
)
EVIDENCE_FRESHNESS_STATES = frozenset({"CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE"})

ARM_KEYS = (
    "ceo_submit_armed", "coo_autonomy_armed", "ceo_ingress_app_armed",
    "dialogue_bridge_armed", "terminal_return_armed",
)
EXECUTION_STATES = frozenset(
    {"NOT_STARTED", "IN_PROGRESS", "ACCEPTED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED"}
)
DISPATCH_STATES = frozenset(
    {
        "WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED",
        "STARTED", "RETURNED", "CONTINUED", "STOPPED", "DELIVERY_UNCONSUMED",
        "WATCH_UNPROVEN", "RUNTIME_BINDING_RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN", "UNKNOWN",
    }
)
PROJECTED_DISPATCH_STATES = DISPATCH_STATES - {"CONTINUED", "STOPPED"}
REVIEW_VERDICTS = frozenset({"approve", "reject", "NOT_YET"})
ORCHESTRATION_ROLES = frozenset({"plan", "work", "review", "repair", "aggregation"})
CAPABILITY_STATES = frozenset({"PROVEN", "PARTIAL", "UNSUPPORTED", "NOT_INSTALLED"})
ACCOUNTABLE_SEATS = frozenset({"chairman", "ceo", "coo", "worker"})
OWED_SEATS = ACCOUNTABLE_SEATS | {"unknown"}
RUNTIME_ROOT_STATES = frozenset({"RESOLVED", "CONFLICT", "UNKNOWN"})
JOB_STATES = frozenset(
    {
        "QUEUED", "RUNNING", "CHECKPOINTED", "RATE_LIMITED", "FAILED", "LOST",
        "CANCEL_REQUESTED", "COMPLETED", "CANCELLED",
    }
)
ATTEMPT_STATES = frozenset(
    {
        "CLAIMED", "RUNNING", "CHECKPOINTED", "CANCEL_REQUESTED", "RATE_LIMITED",
        "FAILED", "LOST", "COMPLETED", "CANCELLED",
    }
)
CONTINUATION_STATES = frozenset({"NONE", "PREPARED", "ACKNOWLEDGED", "UNKNOWN"})
EFFECT_STATES = frozenset({"none", "applied", "effect_unknown"})
RUNTIME_CAPACITY_STATES = frozenset({"available", "degraded", "unknown"})
CARRIER_STATES = frozenset({"RESOLVED", "OWNER_HELD", "UNKNOWN"})
W3C_STATES = frozenset(
    {"RESOLVED", "ABSENT", "UNAVAILABLE", "CONFLICT", "AMBIGUOUS", "EFFECT_UNKNOWN"}
)
W3C_TERMINAL_STATES = frozenset(
    {"APPLIED", "MISSING", "UNAVAILABLE", "CONFLICT", "EFFECT_UNKNOWN"}
)
W3C_WAKE_STATES = frozenset(
    {
        "UNAVAILABLE", "ABSENT", "AMBIGUOUS", "OVERFLOW", "CONFLICT", "NOT_SEEN",
        "PENDING_RETRYABLE", "ATTEMPTED", "RECONCILIATION_REQUIRED", "ACCEPTED",
        "DELIVERED_UNACKNOWLEDGED", "TARGET_ACKNOWLEDGED", "SOURCE_RESOLVED",
    }
)

OUTPUT_KEYS = frozenset(
    {
        "schema", "generated_at", "source", "read_state", "program", "mission",
        "principal", "children", "execution", "review", "transport", "acceptance",
        "posture", "conversation", "missingness", "degraded", "budget", "feature_gates",
    }
)
SOURCE_KEYS = frozenset(
    {
        "control_room_schema", "control_room_generated_at", "fabric_view_schema",
        "fabric_view_generated_at", "source_generation", "source_coverage",
    }
)
PROGRAM_KEYS = frozenset(
    {
        "work_ref", "title", "state", "next_action", "github_prs", "attention_ids",
        "disagreements", "evidence",
    }
)
MISSION_KEYS = frozenset(
    {
        "root_job_id", "root_job_candidates", "root_job_ambiguous", "runtime_root_state",
        "status", "orchestration_role", "plan_step_id", "depth", "title", "armed",
        "submission_availability", "capability", "evidence",
    }
)
PRINCIPAL_KEYS = frozenset(
    {"accountable_seat", "current_worker", "current_sol_target", "owed_turn", "evidence"}
)
SECTION_KEYS = frozenset(
    {"state", "coverage", "reason_codes", "total_count", "items", "overflow_count"}
)
CHILDREN_KEYS = SECTION_KEYS | {"unjoined_job_count", "unjoined_job_ids"}
EXECUTION_KEYS = frozenset(
    {"state", "summary_present", "artifacts", "errors_present", "next_actions", "evidence"}
)
REVIEW_KEYS = frozenset({"required", "reviews_job_id", "verdict", "evidence"})
TRANSPORT_KEYS = frozenset(
    {"dispatch_state", "reason", "actionable", "historical", "watch_proven", "carrier", "w3c", "evidence"}
)
ACCEPTANCE_KEYS = frozenset(
    {"state", "reason_codes", "owner", "artifact_revision", "ruling", "evidence"}
)
POSTURE_KEYS = frozenset({"value", "rule", "evidence"})
EVIDENCE_KEYS = frozenset(
    {"owner", "ref", "field", "source_revision", "source_time", "observed_at", "freshness_state"}
)
READ_STATE_KEYS = frozenset({"state", "reason_codes", "usable_sections"})
ARM_OUTPUT_KEYS = frozenset({*ARM_KEYS, "source"})
CAPABILITY_KEYS = frozenset({"state", "installed", "version", "detail"})
RUNTIME_CARD_KEYS = frozenset(
    {
        "worker_id", "attempt_id", "status", "runtime_binding_id", "binding_generation",
        "continuation_state", "effect_state", "capacity_state", "previous_attempt_id",
        "movement_reason_code",
    }
)
OWED_TURN_KEYS = frozenset({"seat", "reason", "source_refs"})
SOURCE_RECEIPT_KEYS = frozenset({"owner", "ref", "observed_at", "freshness"})
CHILD_ITEM_KEYS = frozenset(
    {
        "job_id", "status", "parent_job_id", "depth", "orchestration_role", "plan_step_id",
        "attempt_count", "attempt_limit", "current_attempt_id", "latest_attempt", "worker_id",
    }
)
ATTEMPT_KEYS = frozenset(
    {
        "attempt_id", "attempt_number", "status", "started_at", "finished_at", "exit_code",
        "has_result", "error_present", "error_class",
    }
)
PR_KEYS = frozenset({"repo", "number", "url", "title", "branch", "draft", "merge_state"})
DISAGREEMENT_KEYS = frozenset({"source", "field", "values", "reason"})
CARRIER_KEYS = frozenset({"state", "reason", "historical", "actionable"})
W3C_KEYS = frozenset(
    {"state", "reason", "terminal_state", "wake_state", "terminal_applied", "source_receipt"}
)
W3C_RECEIPT_KEYS = frozenset(
    {"observed_at", "freshness", "snapshot_digest", "terminal_source_owner", "wake_source_owner"}
)
MISSINGNESS_KEYS = frozenset(
    {"missingness_class", "target_field", "producer_owner", "reason"}
)
SOURCE_GENERATION_KEYS = frozenset({"state", "version", "generation"})
FEATURE_GATE_KEYS = frozenset({"conversation", "actions", "advanced"})

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_URL = re.compile(r"^https://github\.com/[^/?#]+/[^/?#]+/pull/[1-9][0-9]*$")
_SECRET_SHAPE = re.compile(
    r"(?i)(?:\b(?:bearer|authorization|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"x-ccr-token)\b|\bxox[baprs]-|\bgh[pousr]_|\bsk-[a-z0-9])"
)
_ERROR_CLASS_WITHHELD = "WITHHELD"
_REDACTED_TEXT = "agent_os_detail_redacted"
_WITHHELD_REASON = "source detail withheld"
_MAX_TEXT = 4096
_MAX_ITEMS = 50
_FALSE_EXISTENTIAL_PREFIX = (
    "ceo_submit_armed: false; no Chairman-authenticated admitted job can exist yet"
)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _mapping_rows(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _safe_text(value: object) -> str | None:
    """Apply the incumbent redaction owner and a fixed secret-shaped refusal."""

    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT:
        return None
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        return _REDACTED_TEXT
    if _SECRET_SHAPE.search(value):
        return _REDACTED_TEXT
    projected = _project_agent_os_freeform(value)
    return projected if isinstance(projected, str) and projected else None


def _safe_identifier(value: object) -> str | None:
    text = _safe_text(value)
    if text in (None, _REDACTED_TEXT) or len(text) > 512:
        return None
    return text


def _safe_scalar(value: object) -> str | int | bool | None:
    if type(value) in (int, bool):
        return value
    return _safe_identifier(value)


def _closed_string(value: object, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _safe_timestamp(value: object) -> str | None:
    text = _safe_identifier(value)
    if text is None or not text.endswith("Z") or "T" not in text:
        return None
    return text


def _safe_items(value: object) -> tuple[list[str], bool]:
    source = _sequence(value)
    kept: list[str] = []
    excluded = False
    for item in source:
        projected = _safe_text(item)
        if (
            projected is None
            or projected == _REDACTED_TEXT
            or (isinstance(item, str) and item.startswith(("http://", "https://", "/", "~")))
        ):
            excluded = True
            continue
        if len(kept) == 16:
            excluded = True
            break
        kept.append(projected)
    return kept, excluded


def _fact(kind: str, field: str, owner: str | None, reason: str) -> dict[str, Any]:
    return {
        "missingness_class": kind,
        "target_field": field,
        "producer_owner": owner,
        "reason": reason,
    }


def _facts(values: object) -> list[dict[str, Any]]:
    found: dict[tuple[str, str, str | None, str], dict[str, Any]] = {}
    for row in _mapping_rows(values):
        kind = _closed_string(row.get("missingness_class"), MISSINGNESS_CLASSES)
        field = _safe_identifier(row.get("target_field"))
        owner = _safe_identifier(row.get("producer_owner"))
        if kind is None or field is None:
            continue
        item = _fact(kind, field, owner, _WITHHELD_REASON)
        found[(kind, field, owner, _WITHHELD_REASON)] = item
    return [found[key] for key in sorted(found, key=repr)]


def _evidence(values: object) -> list[dict[str, Any]]:
    """Retain only complete, already-qualified DF1 evidence tuples."""

    found: dict[tuple[object, ...], dict[str, Any]] = {}
    for row in _mapping_rows(values):
        if set(row) != EVIDENCE_KEYS:
            continue
        owner = _closed_string(row.get("owner"), EVIDENCE_OWNERS)
        ref = _safe_identifier(row.get("ref"))
        field = _safe_identifier(row.get("field"))
        freshness = _closed_string(row.get("freshness_state"), EVIDENCE_FRESHNESS_STATES)
        revision = _safe_identifier(row.get("source_revision"))
        source_time = _safe_timestamp(row.get("source_time"))
        observed_at = _safe_timestamp(row.get("observed_at"))
        if owner is None or ref is None or field is None or freshness is None or observed_at is None:
            continue
        if row.get("source_revision") is not None and revision is None:
            continue
        if row.get("source_time") is not None and source_time is None:
            continue
        item = {
            "owner": owner, "ref": ref, "field": field, "source_revision": revision,
            "source_time": source_time, "observed_at": observed_at, "freshness_state": freshness,
        }
        key = tuple(item[name] for name in (
            "owner", "ref", "field", "source_revision", "source_time", "observed_at", "freshness_state"
        ))
        found[key] = item
    return [found[key] for key in sorted(found, key=repr)[:32]]


def _section(
    state: str,
    coverage: str,
    reason_codes: Sequence[str],
    items: list[dict[str, Any]],
    *,
    total_count: int | None,
    overflow_count: int | None,
) -> dict[str, Any]:
    assert state in SECTION_STATES
    assert coverage in COVERAGE_STATES
    if coverage != "COMPLETE":
        total_count = None
        overflow_count = None
    if state == "EMPTY":
        coverage = "COMPLETE"
        items = []
        total_count = 0
        overflow_count = 0
    return {
        "state": state,
        "coverage": coverage,
        "reason_codes": sorted({code for code in reason_codes if isinstance(code, str)}),
        "total_count": total_count,
        "items": items,
        "overflow_count": overflow_count,
    }


def _project_source_receipts(value: object) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _mapping_rows(value)[:32]:
        owner = _safe_identifier(row.get("owner"))
        ref = _safe_identifier(row.get("ref"))
        observed_at = _safe_timestamp(row.get("observed_at"))
        freshness = _safe_identifier(row.get("freshness"))
        if owner is None or ref is None or observed_at is None or freshness is None:
            continue
        rows.append({"owner": owner, "ref": ref, "observed_at": observed_at, "freshness": freshness})
    return rows


def _project_runtime_card(value: object) -> dict[str, Any] | None:
    row = _mapping(value)
    if not row:
        return None
    return {
        "worker_id": _safe_identifier(row.get("worker_id")),
        "attempt_id": _safe_identifier(row.get("attempt_id")),
        "status": _closed_string(row.get("status"), ATTEMPT_STATES),
        "runtime_binding_id": _safe_identifier(row.get("runtime_binding_id")),
        "binding_generation": _safe_scalar(row.get("binding_generation")),
        "continuation_state": _closed_string(row.get("continuation_state"), CONTINUATION_STATES),
        "effect_state": _closed_string(row.get("effect_state"), EFFECT_STATES),
        "capacity_state": _closed_string(row.get("capacity_state"), RUNTIME_CAPACITY_STATES),
        "previous_attempt_id": _safe_identifier(row.get("previous_attempt_id")),
        "movement_reason_code": _safe_identifier(row.get("movement_reason_code")),
    }


def _project_owed_turn(value: object) -> dict[str, Any] | None:
    row = _mapping(value)
    if not row:
        return None
    return {
        "seat": _closed_string(row.get("seat"), OWED_SEATS),
        "reason": _safe_text(row.get("reason")),
        "source_refs": _project_source_receipts(row.get("source_refs")),
    }


def _project_attempt(value: object) -> dict[str, Any] | None:
    row = _mapping(value)
    if not row:
        return None
    error_present = row.get("error") is not None
    return {
        "attempt_id": _safe_identifier(row.get("attempt_id")),
        "attempt_number": row.get("attempt_number") if type(row.get("attempt_number")) is int else None,
        "status": _closed_string(row.get("status"), ATTEMPT_STATES),
        "started_at": _safe_timestamp(row.get("started_at")),
        "finished_at": _safe_timestamp(row.get("finished_at")),
        "exit_code": row.get("exit_code") if type(row.get("exit_code")) is int else None,
        "has_result": row.get("has_result") is True,
        "error_present": error_present,
        "error_class": _ERROR_CLASS_WITHHELD if error_present else None,
    }


def _project_child(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "job_id": _safe_identifier(value.get("job_id")),
        "status": _closed_string(value.get("status"), JOB_STATES),
        "parent_job_id": _safe_identifier(value.get("parent_job_id")),
        "depth": value.get("depth") if type(value.get("depth")) is int else None,
        "orchestration_role": _closed_string(value.get("orchestration_role"), ORCHESTRATION_ROLES),
        "plan_step_id": _safe_identifier(value.get("plan_step_id")),
        "attempt_count": value.get("attempt_count") if type(value.get("attempt_count")) is int else None,
        "attempt_limit": value.get("attempt_limit") if type(value.get("attempt_limit")) is int else None,
        "current_attempt_id": _safe_identifier(value.get("current_attempt_id")),
        "latest_attempt": _project_attempt(value.get("latest_attempt")),
        "worker_id": None,
    }


def _project_prs(value: object) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _mapping_rows(value)[:16]:
        url = _safe_text(row.get("url"))
        if url is not None and _GITHUB_URL.fullmatch(url) is None:
            url = None
        number = row.get("number") if type(row.get("number")) is int and row["number"] > 0 else None
        rows.append(
            {
                "repo": _safe_identifier(row.get("repo")), "number": number, "url": url,
                "title": _safe_text(row.get("title")), "branch": _safe_text(row.get("branch")),
                "draft": row.get("draft") if type(row.get("draft")) is bool else None,
                "merge_state": _safe_identifier(row.get("merge_state")),
            }
        )
    return rows


def _project_disagreements(work_value: object, autonomy_value: object) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for item in _sequence(work_value):
        if isinstance(item, str) and (reason := _safe_text(item)) is not None:
            projected.append({"source": "control_room", "field": None, "values": [], "reason": reason})
    for row in _mapping_rows(autonomy_value):
        values = [_safe_text(item) for item in _sequence(row.get("values"))]
        projected.append(
            {
                "source": "autonomy_projection", "field": _safe_identifier(row.get("field")),
                "values": [item for item in values if item is not None][:_MAX_ITEMS],
                "reason": _safe_text(row.get("reason")),
            }
        )
    return projected[:_MAX_ITEMS]


def _qualified_current(
    *,
    validity: Mapping[str, Any],
    cache: Mapping[str, Any],
    responsibility: Mapping[str, Any],
    responsibility_ref: object,
    root_job_id: object,
    control_generated_at: object,
    autonomy_generated_at: object,
) -> bool:
    """Consume the real B5 envelope and its paired mapper metadata."""

    publication_seq = validity.get("publication_seq")
    if (
        cache.get("state") != "fresh"
        or validity.get("schema") != SOURCE_VALIDITY_SCHEMA
        or validity.get("profile") != SOURCE_VALIDITY_PROFILE
        or type(publication_seq) is not int
        or publication_seq <= 0
        or type(cache.get("publication_seq")) is not int
        or cache.get("publication_seq") != publication_seq
        or not isinstance(responsibility_ref, str)
        or not isinstance(root_job_id, str)
        or not isinstance(control_generated_at, str)
        or autonomy_generated_at != control_generated_at
    ):
        return False

    cards = [
        row for row in _mapping_rows(validity.get("cards"))
        if row.get("responsibility_ref") == responsibility_ref and row.get("root_job_id") == root_job_id
    ]
    if len(cards) != 1:
        return False

    receipts = _mapping(cards[0].get("components"))
    metadata = _mapping(responsibility.get("validity"))
    for name in ("card", "dispatch", "owed_open_age"):
        receipt = _mapping(receipts.get(name))
        meta = _mapping(metadata.get(name))
        remaining = receipt.get("remaining_ms")
        budget = meta.get("valid_for_ms")
        proof_ref = meta.get("proof_ref")
        if (
            meta.get("schema") != AUTONOMY_VALIDITY_SCHEMA
            or meta.get("policy") != AUTONOMY_VALIDITY_POLICY
            or not isinstance(proof_ref, str)
            or _HEX_64.fullmatch(proof_ref) is None
            or receipt.get("proof_ref") != proof_ref
            or meta.get("qualified_at") != receipt.get("qualified_at")
            or meta.get("qualified_at") != control_generated_at
            or type(budget) is not int
            or budget < 0
            or type(remaining) is not int
            or remaining <= 0
            or remaining > budget
            or receipt.get("state") != "current"
        ):
            return False
    return True


def _posture(
    *, execution: str, dispatch: str, current: bool, conflict: bool, blocker: bool,
    acceptance: Mapping[str, Any], review: str,
) -> tuple[str, str]:
    """Apply the frozen §5.4 truth table, in order, first match wins."""

    if dispatch == "EFFECT_UNKNOWN":
        return "EFFECT_UNKNOWN", "A1"
    if dispatch == "RUNTIME_BINDING_RECONCILIATION_REQUIRED":
        return "RECONCILIATION_REQUIRED", "B1"
    if conflict:
        return "RECONCILIATION_REQUIRED", "B2"
    terminal = {
        "FAILED": ("EXECUTION_FAILED", "C1"),
        "CANCELLED": ("EXECUTION_CANCELLED", "C2"),
        "LOST": ("EXECUTION_LOST", "C3"),
        "RATE_LIMITED": ("EXECUTION_RATE_LIMITED", "C4"),
    }
    if execution in terminal:
        return terminal[execution]
    if blocker:
        return "BLOCKED", "D1"
    if dispatch == "DELIVERY_UNCONSUMED":
        return "DELIVERED_UNCONSUMED", "E1"
    if dispatch == "WATCH_UNPROVEN":
        return "CONSUMPTION_UNKNOWN", "E2"
    if dispatch == "RETURNED" and not current:
        return "CONSUMPTION_UNKNOWN", "E3"
    if dispatch == "RETURNED" and current:
        if execution != "ACCEPTED":
            return "RETURN_EXECUTION_MISMATCH", "F0"
        if acceptance.get("state") == "ACCEPTED" and review == "reject":
            return "ACCEPTANCE_REVIEW_CONFLICT", "F1"
        if acceptance.get("state") == "ACCEPTED" and acceptance.get("artifact_revision") and acceptance.get("ruling"):
            return "ACCEPTED_PRODUCT", "F2"
        if review == "reject":
            return "REVIEW_REJECTED", "F3"
        if review == "NOT_YET":
            return "RETURNED_UNREVIEWED", "F4"
        if review == "approve":
            return "REVIEWED_NOT_ACCEPTED", "F5"
    if dispatch == "STARTED":
        return ("RUNNING", "G1") if current else ("HISTORICAL_OBSERVATION", "G1h")
    if dispatch in {"WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED"}:
        return ("WAITING", "G2") if current else ("HISTORICAL_OBSERVATION", "G2h")
    if execution == "NOT_STARTED" and dispatch == "UNKNOWN":
        return "NOT_STARTED", "H1"
    return "UNKNOWN", "I1"


def _project_carrier(value: object) -> dict[str, Any] | None:
    row = _mapping(value)
    if not row:
        return None
    return {
        "state": _closed_string(row.get("state"), CARRIER_STATES),
        "reason": _safe_text(row.get("reason")),
        "historical": row.get("historical") if type(row.get("historical")) is bool else None,
        "actionable": row.get("actionable") if type(row.get("actionable")) is bool else None,
    }


def _project_w3c_receipt(value: object) -> dict[str, Any] | None:
    row = _mapping(value)
    if not row:
        return None
    snapshot_digest = row.get("snapshot_digest")
    return {
        "observed_at": _safe_timestamp(row.get("observed_at")),
        "freshness": (
            row.get("freshness") if row.get("freshness") == "SOURCE_EVIDENCE_TIME" else None
        ),
        "snapshot_digest": (
            snapshot_digest
            if isinstance(snapshot_digest, str) and _HEX_64.fullmatch(snapshot_digest)
            else None
        ),
        "terminal_source_owner": (
            row.get("terminal_source_owner")
            if row.get("terminal_source_owner") == "executive_terminal_return"
            else None
        ),
        "wake_source_owner": (
            row.get("wake_source_owner")
            if row.get("wake_source_owner") == "wake_ledger"
            else None
        ),
    }


def _project_w3c(value: object) -> dict[str, Any] | None:
    row = _mapping(value)
    if not row:
        return None
    return {
        "state": _closed_string(row.get("state"), W3C_STATES),
        "reason": _safe_text(row.get("reason")),
        "terminal_state": _closed_string(row.get("terminal_state"), W3C_TERMINAL_STATES),
        "wake_state": _closed_string(row.get("wake_state"), W3C_WAKE_STATES),
        "terminal_applied": (
            row.get("terminal_applied") if type(row.get("terminal_applied")) is bool else None
        ),
        "source_receipt": _project_w3c_receipt(row.get("source_receipt")),
    }


def _source_generation(value: object) -> dict[str, Any]:
    row = _mapping(value)
    return {
        "state": _safe_scalar(row.get("state")),
        "version": _safe_scalar(row.get("version")),
        "generation": _safe_scalar(row.get("generation")),
    }


def _root_identity(
    responsibility: Mapping[str, Any], requested_root: object,
) -> tuple[str | None, list[str], bool, str]:
    raw_candidates = _sequence(responsibility.get("root_job_candidates"))
    candidates = sorted(
        {
            candidate
            for candidate in (_safe_identifier(item) for item in raw_candidates)
            if candidate is not None
        }
    )
    malformed_candidates = len(candidates) != len(raw_candidates)
    owner_root = _safe_identifier(responsibility.get("root_job_id"))
    conflict = (
        responsibility.get("runtime_root_state") == "CONFLICT"
        or responsibility.get("root_job_ambiguous") is True
        or len(candidates) >= 2
        or malformed_candidates
    )
    if conflict:
        return None, candidates, True, "CONFLICT"
    if len(candidates) != 1:
        return None, candidates, False, "UNKNOWN"
    if owner_root != candidates[0]:
        return None, candidates, True, "CONFLICT"
    if not isinstance(requested_root, str) or requested_root != candidates[0]:
        return None, candidates, False, "UNKNOWN"
    return candidates[0], candidates, False, "RESOLVED"


def _children_section(
    *,
    fabric_valid: bool,
    historical: bool,
    resolved_root: str | None,
    fabric: Mapping[str, Any],
) -> dict[str, Any]:
    owner_fabric = fabric if fabric_valid else {}
    raw_count = owner_fabric.get("unjoined_job_count")
    unjoined_count = raw_count if type(raw_count) is int and raw_count >= 0 else None
    unjoined_ids = sorted(
        {
            item
            for item in (
                _safe_identifier(value)
                for value in _sequence(owner_fabric.get("unjoined_job_ids"))
            )
            if item is not None
        }
    )[:_MAX_ITEMS]
    raw_children = (
        [
            row for row in _mapping_rows(owner_fabric.get("children"))
            if row.get("root_job_id") == resolved_root
        ]
        if fabric_valid and resolved_root is not None
        else []
    )
    items = [_project_child(row) for row in raw_children]

    if not fabric_valid:
        section = _section(
            "UNAVAILABLE", "INCOMPLETE", ["FABRIC_VIEW_UNAVAILABLE"], [],
            total_count=None, overflow_count=None,
        )
    elif historical:
        section = _section(
            "HISTORICAL", "HISTORICAL_ONLY", ["STALE_SOURCE_RETAINED"], items,
            total_count=None, overflow_count=None,
        )
    elif resolved_root is None:
        reasons = ["ROOT_NOT_JOINED"]
        if unjoined_count or unjoined_ids:
            reasons.append("UNJOINED_JOBS_PRESENT")
        section = _section(
            "PARTIAL" if unjoined_ids else "UNAVAILABLE", "INCOMPLETE", reasons, [],
            total_count=None, overflow_count=None,
        )
    elif unjoined_count is None:
        section = _section(
            "PARTIAL", "INCOMPLETE", ["UNJOINED_COUNT_UNKNOWN"], items,
            total_count=None, overflow_count=None,
        )
    elif unjoined_count > 0 or unjoined_ids:
        section = _section(
            "PARTIAL", "INCOMPLETE", ["UNJOINED_JOBS_PRESENT"], items,
            total_count=None, overflow_count=None,
        )
    elif not items:
        section = _section("EMPTY", "COMPLETE", [], [], total_count=0, overflow_count=0)
    else:
        section = _section(
            "AVAILABLE", "COMPLETE", [], items,
            total_count=len(items), overflow_count=0,
        )
    section.update({"unjoined_job_count": unjoined_count, "unjoined_job_ids": unjoined_ids})
    return section


def compose_mission_workspace(
    *,
    control_room: Mapping[str, Any] | None,
    fabric_view: Mapping[str, Any] | None,
    work_ref: str,
    root_job_id: str | None,
    source_validity: Mapping[str, Any] | None,
    cache_currentness: Mapping[str, Any] | None,
    source_generation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Pure deterministic read-only mission workspace projection."""

    control = _mapping(control_room)
    fabric = _mapping(fabric_view)
    validity = _mapping(source_validity)
    cache = _mapping(cache_currentness)
    control_valid = control.get("schema") == CONTROL_ROOM_SCHEMA
    fabric_valid = fabric.get("schema") == FABRIC_VIEW_SCHEMA
    control_generation = _safe_timestamp(control.get("generated_at"))
    fabric_generation = _safe_timestamp(fabric.get("generated_at"))

    safe_work_ref = _safe_identifier(work_ref)
    matching_work = (
        [
            row for row in _mapping_rows(control.get("work"))
            if safe_work_ref is not None and row.get("work_ref") == safe_work_ref
        ]
        if control_valid
        else []
    )
    duplicate_program = len(matching_work) > 1
    work = matching_work[0] if len(matching_work) == 1 else {}

    autonomy = _mapping(control.get("autonomy")) if control_valid else {}
    responsibilities = _mapping_rows(autonomy.get("responsibilities"))
    joined_work_ref = safe_work_ref if len(matching_work) == 1 else None
    matching_responsibilities = [
        row for row in responsibilities
        if joined_work_ref is not None and row.get("responsibility_ref") == joined_work_ref
    ]
    duplicate_responsibility = len(matching_responsibilities) > 1
    responsibility = matching_responsibilities[0] if len(matching_responsibilities) == 1 else {}

    resolved_root, root_candidates, root_ambiguous, runtime_root_state = _root_identity(
        responsibility, root_job_id
    )
    if duplicate_program or duplicate_responsibility:
        resolved_root = None
        root_ambiguous = True
        runtime_root_state = "CONFLICT"

    root = _mapping(fabric.get("root")) if fabric_valid and resolved_root else {}
    if resolved_root is not None and not root:
        resolved_root = None
        root = {}
        if runtime_root_state == "RESOLVED":
            runtime_root_state = "UNKNOWN"
    elif resolved_root is not None and (
        root.get("job_id") != resolved_root
        or root.get("parent_job_id") is not None
        or root.get("root_job_id") != resolved_root
    ):
        resolved_root = None
        root = {}
        root_ambiguous = True
        runtime_root_state = "CONFLICT"

    dispatch = _mapping(responsibility.get("dispatch"))
    raw_dispatch_state = dispatch.get("dispatch_state")
    dispatch_state = (
        raw_dispatch_state if raw_dispatch_state in PROJECTED_DISPATCH_STATES else "UNKNOWN"
    )
    qualified = _qualified_current(
        validity=validity,
        cache=cache,
        responsibility=responsibility,
        responsibility_ref=safe_work_ref,
        root_job_id=resolved_root,
        control_generated_at=control_generation,
        autonomy_generated_at=_safe_timestamp(autonomy.get("generated_at")),
    )
    observation_current = qualified and dispatch.get("historical") is False

    result = _mapping(root.get("result"))
    execution_state = _closed_string(result.get("state"), EXECUTION_STATES) or "NOT_STARTED"
    review_source = _mapping(root.get("review"))
    review_verdict = _closed_string(review_source.get("verdict"), REVIEW_VERDICTS) or "NOT_YET"
    artifacts, artifacts_excluded = _safe_items(result.get("artifacts"))
    next_actions, actions_excluded = _safe_items(result.get("next_actions"))
    acceptance = {
        "state": "NOT_PROJECTED",
        "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"],
        "owner": None,
        "artifact_revision": None,
        "ruling": None,
        "evidence": [],
    }
    generation_conflict = _mapping(source_generation).get("conflict") is True
    blocker = bool(responsibility.get("blocker") or responsibility.get("declared_blocker"))
    posture_value, posture_rule = _posture(
        execution=execution_state,
        dispatch=dispatch_state,
        current=observation_current,
        conflict=(runtime_root_state == "CONFLICT" or generation_conflict),
        blocker=blocker,
        acceptance=acceptance,
        review=review_verdict,
    )

    armed_source = _mapping(fabric.get("armed")) if fabric_valid else {}
    armed = {
        key: armed_source.get(key) if type(armed_source.get(key)) is bool else None
        for key in ARM_KEYS
    }
    armed["source"] = _safe_identifier(armed_source.get("source")) or "absent"
    capability_source = _mapping(fabric.get("capability")) if fabric_valid else {}
    capability = {
        "state": _closed_string(capability_source.get("state"), CAPABILITY_STATES),
        "installed": (
            capability_source.get("installed")
            if type(capability_source.get("installed")) is bool
            else None
        ),
        "version": _safe_scalar(capability_source.get("version")),
        "detail": _safe_text(capability_source.get("detail")),
    }
    children = _children_section(
        fabric_valid=fabric_valid,
        historical=cache.get("state") == "historical_refresh_error",
        resolved_root=resolved_root,
        fabric=fabric,
    )

    if not control_valid and not fabric_valid:
        read_state = "UNAVAILABLE"
    elif cache.get("state") == "historical_refresh_error":
        read_state = "HISTORICAL"
    elif qualified and control_valid and fabric_valid and resolved_root is not None:
        read_state = "CURRENT"
    else:
        read_state = "PARTIAL"

    usable_sections: list[str] = []
    if work:
        usable_sections.append("program")
    if root:
        usable_sections.extend(["mission", "execution", "review"])
    if responsibility:
        usable_sections.extend(["principal", "transport"])
    if children["state"] in {"AVAILABLE", "EMPTY", "PARTIAL", "HISTORICAL"}:
        usable_sections.append("children")

    extra_facts = [
        _fact("MISSING_PRODUCER", "acceptance", None, "acceptance owner is not projected"),
        _fact("MISSING_PRODUCER", "children.worker_id", "executive_os", "worker identity is not projected"),
        _fact("MISSING_PRODUCER", "mission.title", "executive_os", "mission title is not projected"),
        _fact("MISSING_PRODUCER", "transport.continued", "slack", "continuation is not projected"),
        _fact("MISSING_PRODUCER", "transport.stopped", "slack", "terminal stop is not projected"),
        _fact("EXCLUDED", "conversation", "executive_os", "mission tree content is excluded"),
    ]
    if duplicate_program:
        extra_facts.append(_fact("DEGRADED", "program", "control_room_cache", "duplicate program identity"))
    if duplicate_responsibility:
        extra_facts.append(
            _fact("DEGRADED", "principal", "autonomy_projection", "duplicate responsibility identity")
        )
    if artifacts_excluded:
        extra_facts.append(
            _fact("EXCLUDED", "execution.artifacts", "executive_os", "unsafe artifact detail excluded")
        )
    if actions_excluded:
        extra_facts.append(
            _fact("EXCLUDED", "execution.next_actions", "executive_os", "unsafe next action detail excluded")
        )
    if raw_dispatch_state in {"CONTINUED", "STOPPED"}:
        extra_facts.append(
            _fact(
                "MISSING_PRODUCER", f"transport.{str(raw_dispatch_state).lower()}",
                "slack", "dialogue edge is not projected",
            )
        )
    if resolved_root is None and runtime_root_state == "UNKNOWN":
        extra_facts.append(
            _fact(
                "MISSING_PRODUCER", "mission.root_job_id", "autonomy_projection",
                "mission root is unavailable",
            )
        )
    missingness = _facts(
        [*(_mapping_rows(fabric.get("missingness")) if fabric_valid else []), *extra_facts]
    )

    degraded: list[str] = []
    owner_degraded = [
        *(_sequence(control.get("degraded")) if control_valid else []),
        *(_sequence(fabric.get("degraded")) if fabric_valid else []),
    ]
    for item in owner_degraded:
        if not isinstance(item, str) or item.startswith(_FALSE_EXISTENTIAL_PREFIX):
            continue
        projected = _safe_text(item)
        if projected is not None:
            degraded.append(projected)
    if resolved_root is None and runtime_root_state == "UNKNOWN":
        degraded.append("mission root unavailable")
    degraded = sorted(set(degraded))

    agent_os = _mapping(work.get("agent_os"))
    github = _mapping(work.get("github"))
    attention_ids = sorted(
        {
            item
            for item in (_safe_identifier(value) for value in _sequence(work.get("attention_ids")))
            if item is not None
        }
    )[:_MAX_ITEMS]
    program = {
        "work_ref": safe_work_ref,
        "title": _safe_text(agent_os.get("title") or work.get("title")),
        "state": _safe_identifier(agent_os.get("state") or agent_os.get("status")),
        "next_action": _safe_text(agent_os.get("next_action")),
        "github_prs": _project_prs(github.get("prs")),
        "attention_ids": attention_ids,
        "disagreements": _project_disagreements(
            work.get("disagreements"), responsibility.get("disagreements")
        ),
        "evidence": _evidence(work.get("evidence")),
    }
    mission = {
        "root_job_id": resolved_root,
        "root_job_candidates": root_candidates,
        "root_job_ambiguous": root_ambiguous,
        "runtime_root_state": runtime_root_state,
        "status": _closed_string(root.get("status"), JOB_STATES),
        "orchestration_role": _closed_string(root.get("orchestration_role"), ORCHESTRATION_ROLES),
        "plan_step_id": _safe_identifier(root.get("plan_step_id")),
        "depth": root.get("depth") if type(root.get("depth")) is int else None,
        "title": None,
        "armed": armed,
        "submission_availability": (
            "UNAVAILABLE_NEW_SUBMISSION" if armed["ceo_submit_armed"] is False else "UNKNOWN"
        ),
        "capability": capability,
        "evidence": _evidence(root.get("evidence")),
    }
    principal = {
        "accountable_seat": _closed_string(responsibility.get("accountable_seat"), ACCOUNTABLE_SEATS),
        "current_worker": _project_runtime_card(responsibility.get("current_worker")),
        "current_sol_target": _project_runtime_card(responsibility.get("current_sol_target")),
        "owed_turn": _project_owed_turn(responsibility.get("owed_turn")),
        "evidence": _evidence(responsibility.get("evidence")),
    }
    transport = {
        "dispatch_state": dispatch_state,
        "reason": _safe_text(dispatch.get("reason")),
        "actionable": dispatch.get("actionable") is True if dispatch_state != "UNKNOWN" else False,
        "historical": (
            dispatch.get("historical")
            if type(dispatch.get("historical")) is bool and dispatch_state != "UNKNOWN"
            else True
        ),
        "watch_proven": dispatch.get("watch_proven") if type(dispatch.get("watch_proven")) is bool else None,
        "carrier": _project_carrier(dispatch.get("carrier")),
        "w3c": _project_w3c(dispatch.get("w3c")),
        "evidence": _evidence(dispatch.get("evidence")),
    }
    source = {
        "control_room_schema": CONTROL_ROOM_SCHEMA if control_valid else None,
        "control_room_generated_at": control_generation,
        "fabric_view_schema": FABRIC_VIEW_SCHEMA if fabric_valid else None,
        "fabric_view_generated_at": fabric_generation,
        "source_generation": _source_generation(source_generation),
        "source_coverage": [
            name
            for name, available in (("control_room", control_valid), ("fabric_view", fabric_valid))
            if available
        ],
    }

    output = {
        "schema": SCHEMA,
        "generated_at": control_generation or fabric_generation,
        "source": source,
        "read_state": {
            "state": read_state,
            "reason_codes": [] if read_state == "CURRENT" else ["SOURCE_OR_VALIDITY_INCOMPLETE"],
            "usable_sections": usable_sections,
        },
        "program": program,
        "mission": mission,
        "principal": principal,
        "children": children,
        "execution": {
            "state": execution_state,
            "summary_present": isinstance(result.get("summary"), str),
            "artifacts": artifacts,
            "errors_present": bool(_sequence(result.get("errors"))),
            "next_actions": next_actions,
            "evidence": _evidence(result.get("evidence")),
        },
        "review": {
            "required": review_source.get("required") if type(review_source.get("required")) is bool else None,
            "reviews_job_id": _safe_identifier(review_source.get("reviews_job_id")),
            "verdict": review_verdict,
            "evidence": _evidence(review_source.get("evidence")),
        },
        "transport": transport,
        "acceptance": acceptance,
        "posture": {"value": posture_value, "rule": posture_rule, "evidence": []},
        "conversation": _section(
            "UNAVAILABLE", "NOT_PROJECTED", ["MISSION_TREE_SUBSLICE_EXCLUDES_CONTENT"], [],
            total_count=None, overflow_count=None,
        ),
        "missingness": missingness,
        "degraded": degraded,
        "budget": {},
        "feature_gates": {
            "conversation": "UNAVAILABLE", "actions": "READ_ONLY", "advanced": "AVAILABLE",
        },
    }

    assert set(output) == OUTPUT_KEYS
    assert set(output["source"]) == SOURCE_KEYS
    assert set(output["source"]["source_generation"]) == SOURCE_GENERATION_KEYS
    assert set(output["read_state"]) == READ_STATE_KEYS
    assert set(output["program"]) == PROGRAM_KEYS
    assert all(set(item) == PR_KEYS for item in output["program"]["github_prs"])
    assert all(set(item) == DISAGREEMENT_KEYS for item in output["program"]["disagreements"])
    assert set(output["mission"]) == MISSION_KEYS
    assert set(output["mission"]["armed"]) == ARM_OUTPUT_KEYS
    assert set(output["mission"]["capability"]) == CAPABILITY_KEYS
    assert set(output["principal"]) == PRINCIPAL_KEYS
    for runtime_card in (
        output["principal"]["current_worker"], output["principal"]["current_sol_target"],
    ):
        assert runtime_card is None or set(runtime_card) == RUNTIME_CARD_KEYS
    owed_turn = output["principal"]["owed_turn"]
    assert owed_turn is None or set(owed_turn) == OWED_TURN_KEYS
    if owed_turn is not None:
        assert all(set(item) == SOURCE_RECEIPT_KEYS for item in owed_turn["source_refs"])
    assert set(output["children"]) == CHILDREN_KEYS
    for child in output["children"]["items"]:
        assert set(child) == CHILD_ITEM_KEYS
        assert child["latest_attempt"] is None or set(child["latest_attempt"]) == ATTEMPT_KEYS
    assert set(output["execution"]) == EXECUTION_KEYS
    assert set(output["review"]) == REVIEW_KEYS
    assert set(output["transport"]) == TRANSPORT_KEYS
    carrier = output["transport"]["carrier"]
    assert carrier is None or set(carrier) == CARRIER_KEYS
    w3c = output["transport"]["w3c"]
    assert w3c is None or set(w3c) == W3C_KEYS
    if w3c is not None:
        receipt = w3c["source_receipt"]
        assert receipt is None or set(receipt) == W3C_RECEIPT_KEYS
    assert set(output["acceptance"]) == ACCEPTANCE_KEYS
    assert set(output["posture"]) == POSTURE_KEYS
    assert set(output["conversation"]) == SECTION_KEYS
    assert all(set(item) == MISSINGNESS_KEYS for item in output["missingness"])
    for evidence_owner in (
        output["program"], output["mission"], output["principal"], output["execution"],
        output["review"], output["transport"], output["acceptance"], output["posture"],
    ):
        assert all(set(item) == EVIDENCE_KEYS for item in evidence_owner["evidence"])
    assert set(output["feature_gates"]) == FEATURE_GATE_KEYS
    return output
