"""Durable SQLite worker runtime for the Mastermind Executive OS.

The database is the only lifecycle authority.  Provider execution is performed
explicitly by a separate bounded adapter/supervisor; this module owns the durable
identity, authority receipt, process reference, lease, and result reconstruction
state around that execution.  All linked Job/Attempt/WorkerQuotaClass changes and
their Event receipt commit in one ``BEGIN IMMEDIATE`` transaction.

Phase 1A compatibility is intentional.  ``Runtime.workers``, ``Runtime.jobs``
and ``Runtime.broker`` retain the small registry API while delegating every
active-attempt mutation through a lease token and monotonically increasing
quota-class fence.  Tokens are stored in the protected database but are never
included in events or public ``to_dict`` output.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence
from uuid import uuid4

from common.commission_ref import (
    CommissionRef,
    CommissionRefError,
    normalize_commission_ref,
)
from control_plane.executive_authority import (
    AuthorityDenied,
    AuthorityPolicyError,
    ExecutiveAuthorityPolicy,
)
from control_plane.executive_coo_policy import (
    CooCyclePolicy,
    CooCyclePolicyError,
    EXPECTED_POLICY_SHA256,
)
from control_plane.executive_orchestration_principal import (
    OperatorPrincipalObservation,
    OrchestrationPrincipalError,
    build_execution_principal_snapshot,
    build_placement_snapshot,
    digest as orchestration_digest,
    validate_placement_snapshot,
    validate_provider_home_identity,
)
from control_plane.executive_retry_safety import (
    RetrySafety,
    RetrySafetyDecision,
    RetrySafetyEvidence,
    classify_retry_safety,
)
from control_plane.operator_harness_contract import (
    AttemptExecutionMode,
    CandidateResult,
    EventCursor,
    LaunchDecision,
    NormalizedEvent,
    OperationId,
    OperationIntentTarget,
    OperationKind,
    OperationReceiptKind,
    ObservedHarnessAttestation,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionEpochState,
    TurnRef,
    TurnStartObservation,
    operation_receipt_command_id,
    compare_launch,
)
from scripts.ohf.redaction import redact_evidence, redact_evidence_text


SCHEMA_VERSION = 4
OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION = (
    "mastermind.operator_harness_internal_generation_operation/v1"
)
OHF_RECONCILE_OBSERVATION_SCHEMA_VERSION = (
    "mastermind.operator_harness_reconcile_observation/v1"
)
OHF_CANDIDATE_EVIDENCE_SCHEMA_VERSION = (
    "mastermind.operator_harness_candidate_evidence/v1"
)
DEFAULT_LEASE_SECONDS = 60
DEFAULT_BUSY_TIMEOUT_MS = 5_000
_ROOT = Path(__file__).resolve().parent.parent
_DB_RELATIVE_PATH = Path("data") / "control_plane" / "executive.sqlite3"
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_COMMAND_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ROUTING_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SEAT_RE = re.compile(r"^[a-z][a-z0-9._-]{0,31}$")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_JOB_SEATS = frozenset({"coo", "ceo", "chairman"})
_BUSINESS_IMPACTS = frozenset({"routine", "material", "critical"})
OPERATOR_HARNESS_BINDING_KEYS = frozenset(
    {
        "operator_eligible_quota_classes",
        "operator_provider",
        "operator_model",
        "operator_effort",
        "operator_cost_class",
        "operator_routing_policy_version",
        "operator_execution_profile_id",
        "operator_execution_profile_digest",
        "operator_capability_policy_version",
        "operator_capability_policy_digest",
        "operator_harness_binary_digest",
        "operator_harness_version",
        "operator_harness_armed",
    }
)
V2_HOST_EXECUTION_BINDING_KEYS = frozenset(
    {
        "eligible_quota_classes",
        "provider",
        "model",
        "effort",
        "cost_class",
        "base_sha",
        "routing_policy_version",
        "execution_profile_id",
        "execution_profile_digest",
        "capability_policy_version",
        "capability_policy_digest",
    }
    | OPERATOR_HARNESS_BINDING_KEYS
)
EXECUTIVE_DIALOGUE_SOURCE_SCHEMA = "mastermind.executive_dialogue_source/v1"
_EXECUTIVE_DIALOGUE_SOURCE_KEYS = frozenset(
    {
        "schema_version",
        "work_ref",
        "commission_ref",
        "watch_mode",
    }
)
_ORCHESTRATION_ROLES = frozenset(
    {"plan", "work", "review", "repair", "aggregation"}
)
COO_CYCLE_BLOCK_REASONS = frozenset(
    {
        "invalid_root", "invalid_policy", "invalid_plan",
        "plan_capacity_exceeded", "fan_out_exceeded", "children_total_exceeded",
        "depth_exceeded", "unexpected_pre_admission_child", "lineage_invalid",
        "effective_grant_invalid", "validation_contract_invalid",
        "principal_snapshot_invalid", "result_protocol_invalid",
        "plan_terminal_adverse", "child_terminal_adverse",
        "review_not_independent", "review_jobs_exhausted",
        "repair_rounds_exhausted", "aggregation_handoff_invalid",
        "aggregation_terminal_adverse", "exact_dispatch_unavailable",
        "state_conflict",
    }
)
_ESCALATION_RANK = {"coo": 0, "ceo": 1, "chairman": 2}
_COST_CLASS_RANK = {"small": 0, "default": 1, "frontier": 2}
_MAX_JOB_DEPTH = 64
_SCHEMA_UPGRADE_BARRIER = "executive-schema-upgrade.in-progress.json"
_NORMALIZED_V4_SCHEMA_DIGEST = (
    "56054e6e64ca6e69e878ce6488bb5527e1051212db94bae0fbf625eed78ca6a4"
)
_V2_ROOT_CREATION_CAPABILITY = object()
_COO_CYCLE_PLANNER_CREATION_CAPABILITY = object()
_COO_CYCLE_CHILD_CREATION_CAPABILITY = object()
_COO_CYCLE_DISPATCH_CAPABILITY = object()


class RuntimeProofError(RuntimeError):
    """Base error for operator-visible Executive runtime failures."""


class PersistenceError(RuntimeProofError):
    """The durable SQLite state could not be safely opened or committed."""


class ExecutiveSchemaUpgradeRequired(PersistenceError):
    """An existing pre-v4 store requires the explicit offline upgrade lane."""


class StateConflict(RuntimeProofError):
    """The operation conflicts with the current state machine or lease."""


class WorkerStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    RATE_LIMITED = "RATE_LIMITED"
    OFFLINE = "OFFLINE"
    ERROR = "ERROR"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    LOST = "LOST"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AttemptStatus(str, Enum):
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    CHECKPOINTED = "CHECKPOINTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    LOST = "LOST"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


_LEASE_ACTIVE_ATTEMPT_STATUSES = {
    AttemptStatus.CLAIMED,
    AttemptStatus.RUNNING,
    AttemptStatus.CHECKPOINTED,
    AttemptStatus.CANCEL_REQUESTED,
}
_WORKER_MUTABLE_ATTEMPT_STATUSES = {
    AttemptStatus.CLAIMED,
    AttemptStatus.RUNNING,
    AttemptStatus.CHECKPOINTED,
}
_TERMINAL_ATTEMPT_STATUSES = {
    AttemptStatus.RATE_LIMITED,
    AttemptStatus.FAILED,
    AttemptStatus.LOST,
    AttemptStatus.COMPLETED,
    AttemptStatus.CANCELLED,
}
_TERMINAL_JOB_STATUSES = {
    JobStatus.RATE_LIMITED,
    JobStatus.FAILED,
    JobStatus.LOST,
    JobStatus.COMPLETED,
    JobStatus.CANCELLED,
}
_ACTIVE_JOB_STATUS_BY_ATTEMPT = {
    AttemptStatus.CLAIMED: JobStatus.RUNNING,
    AttemptStatus.RUNNING: JobStatus.RUNNING,
    AttemptStatus.CHECKPOINTED: JobStatus.CHECKPOINTED,
    AttemptStatus.CANCEL_REQUESTED: JobStatus.CANCEL_REQUESTED,
}


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise StateConflict(f"value is not valid JSON data: {exc}") from exc


def _migration_checksum(statements: Sequence[str]) -> str:
    return hashlib.sha256(
        "\n".join(statement.strip() for statement in statements).encode("utf-8")
    ).hexdigest()


def _normalize_schema_sql(sql: str) -> str:
    """Normalize SQLite formatting without changing quoted literal bytes."""

    result: list[str] = []
    quote_char: str | None = None
    bracket = False
    pending_space = False
    index = 0
    while index < len(sql):
        character = sql[index]
        if quote_char is not None:
            result.append(character)
            if character == quote_char:
                if index + 1 < len(sql) and sql[index + 1] == quote_char:
                    result.append(sql[index + 1])
                    index += 1
                else:
                    quote_char = None
            index += 1
            continue
        if bracket:
            result.append(character)
            if character == "]":
                bracket = False
            index += 1
            continue
        if character in {"'", '"', "`"}:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            quote_char = character
            result.append(character)
        elif character == "[":
            if pending_space and result:
                result.append(" ")
            pending_space = False
            bracket = True
            result.append(character)
        elif character.isspace():
            pending_space = True
        else:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            result.append(character)
        index += 1
    if quote_char is not None or bracket:
        raise PersistenceError("sqlite_schema contains unterminated quoted SQL")
    return "".join(result).strip()


def _normalized_schema_digest(connection: sqlite3.Connection) -> str:
    try:
        rows = connection.execute(
            """
            SELECT type,name,tbl_name,sql FROM sqlite_master
            WHERE sql IS NOT NULL
            ORDER BY type COLLATE BINARY,name COLLATE BINARY
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise PersistenceError(f"cannot inspect sqlite_schema: {exc}") from exc
    normalized: list[list[str]] = []
    for row in rows:
        if any(not isinstance(row[index], str) for index in range(4)):
            raise PersistenceError("sqlite_schema contains a malformed object")
        normalized.append(
            [str(row[0]), str(row[1]), str(row[2]), _normalize_schema_sql(str(row[3]))]
        )
    return hashlib.sha256(_json_dumps(normalized).encode("utf-8")).hexdigest()


def _json_loads(value: str | None, *, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError) as exc:
        raise PersistenceError(f"invalid persisted JSON: {exc}") from exc


def _strict_canonical_json_loads(value: str, *, name: str) -> Any:
    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = item
        return result

    try:
        parsed = json.loads(value, object_pairs_hook=_pairs)
    except (TypeError, ValueError) as exc:
        raise StateConflict(f"{name} is not strict JSON: {exc}") from exc
    if _json_dumps(parsed) != value:
        raise StateConflict(f"{name} is not canonical JSON")
    return parsed


def _load_canonical_digest_pair(
    json_text: Any,
    digest_text: Any,
    *,
    name: str,
) -> Any:
    if json_text is None and digest_text is None:
        return None
    if json_text is None or digest_text is None:
        raise PersistenceError(f"{name} JSON/digest pair is partial")
    if not isinstance(json_text, str) or not isinstance(digest_text, str):
        raise PersistenceError(f"{name} JSON/digest pair has wrong storage type")
    if re.fullmatch(r"[0-9a-f]{64}", digest_text) is None:
        raise PersistenceError(f"{name} digest is not lowercase SHA-256")
    try:
        parsed = _strict_canonical_json_loads(json_text, name=name)
    except StateConflict as exc:
        raise PersistenceError(str(exc)) from exc
    if hashlib.sha256(json_text.encode("utf-8")).hexdigest() != digest_text:
        raise PersistenceError(f"{name} digest does not match canonical JSON bytes")
    return parsed


def _iso(timestamp_ms: int | None) -> str:
    if timestamp_ms is None:
        return ""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _enum_value(value: str | Enum, enum_type: type[Enum]) -> str:
    try:
        return str(enum_type(value).value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(str(item.value) for item in enum_type)
        raise StateConflict(
            f"invalid {enum_type.__name__} {value!r}; expected one of {allowed}"
        ) from exc


def _normalise_capabilities(
    values: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    if isinstance(values, str):
        values = [values]
    elif values is not None and not isinstance(values, (list, tuple)):
        raise StateConflict("capabilities must be a string or list")
    return sorted(
        {str(value).strip().lower() for value in (values or []) if str(value).strip()}
    )


def _normalise_constraints(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is not None and not isinstance(value, dict):
        raise StateConflict("job constraints must be a mapping")
    raw = value or {}
    provider = str(raw.get("provider") or "").strip().lower()
    capabilities = _normalise_capabilities(
        raw.get("required_capabilities") or raw.get("capabilities") or []
    )
    quota_values = raw.get("eligible_quota_classes") or raw.get("quota_classes") or []
    if raw.get("quota_class"):
        quota_values = [raw["quota_class"]]
    if isinstance(quota_values, str):
        quota_values = [quota_values]
    if not isinstance(quota_values, (list, tuple)):
        raise StateConflict("eligible_quota_classes must be a list")
    eligible = sorted(
        {str(item).strip().lower() for item in quota_values if str(item).strip()}
    ) or ["default"]
    result: dict[str, Any] = {"eligible_quota_classes": eligible}

    aliases_raw = raw.get("preferred_model_aliases") or []
    if isinstance(aliases_raw, str):
        aliases_raw = [aliases_raw]
    if not isinstance(aliases_raw, (list, tuple)) or len(aliases_raw) > 16:
        raise StateConflict("preferred_model_aliases must be a bounded list")
    aliases: list[str] = []
    for item in aliases_raw:
        alias = str(item).strip().lower()
        if _ROUTING_VALUE_RE.fullmatch(alias) is None:
            raise StateConflict("preferred_model_aliases contains an invalid alias")
        if alias not in aliases:
            aliases.append(alias)
    if aliases:
        result["preferred_model_aliases"] = aliases

    excluded_raw = raw.get("excluded_worker_ids") or []
    if isinstance(excluded_raw, str):
        excluded_raw = [excluded_raw]
    if not isinstance(excluded_raw, (list, tuple)) or len(excluded_raw) > 16:
        raise StateConflict("excluded_worker_ids must be a bounded list")
    excluded: list[str] = []
    for item in excluded_raw:
        worker_id = str(item).strip()
        if _WORKER_ID_RE.fullmatch(worker_id) is None:
            raise StateConflict("excluded_worker_ids contains an invalid worker id")
        if worker_id not in excluded:
            excluded.append(worker_id)
    if excluded:
        result["excluded_worker_ids"] = excluded

    for key in (
        "task_kind",
        "risk",
        "ambiguity",
        "routing_policy_version",
        "execution_profile_id",
        "capability_policy_version",
    ):
        normalized = str(raw.get(key) or "").strip().lower()
        if normalized:
            if _ROUTING_VALUE_RE.fullmatch(normalized) is None:
                raise StateConflict(f"constraint {key} must be a bounded identifier")
            result[key] = normalized

    for key in ("execution_profile_digest", "capability_policy_digest"):
        normalized = str(raw.get(key) or "").strip().lower()
        if normalized:
            if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
                raise StateConflict(f"constraint {key} must be a lowercase SHA-256 digest")
            result[key] = normalized

    capability_keys = {
        "execution_profile_id",
        "execution_profile_digest",
        "capability_policy_version",
        "capability_policy_digest",
    }
    present_capability_keys = capability_keys & set(result)
    if present_capability_keys and present_capability_keys != capability_keys:
        raise StateConflict(
            "execution capability constraints must carry the complete profile/policy identity"
        )

    if aliases and "routing_policy_version" not in result:
        raise StateConflict(
            "preferred_model_aliases requires routing_policy_version"
        )
    if (
        result.get("routing_policy_version")
        in {
            "2026-08-24.stage2",
            "2026-08-24.stage3",
            "2026-08-24.stage4",
        }
        and present_capability_keys != capability_keys
    ):
        raise StateConflict(
            "stage2+ routed Jobs require an exact execution capability profile"
        )

    reason_codes_raw = raw.get("routing_reason_codes") or []
    if isinstance(reason_codes_raw, str):
        reason_codes_raw = [reason_codes_raw]
    if not isinstance(reason_codes_raw, (list, tuple)) or len(reason_codes_raw) > 16:
        raise StateConflict("routing_reason_codes must be a bounded list")
    reason_codes: list[str] = []
    for item in reason_codes_raw:
        reason = str(item).strip().lower()
        if _ROUTING_VALUE_RE.fullmatch(reason) is None:
            raise StateConflict("routing_reason_codes contains an invalid value")
        if reason not in reason_codes:
            reason_codes.append(reason)
    if reason_codes:
        result["routing_reason_codes"] = reason_codes
    if provider:
        result["provider"] = provider
    if capabilities:
        result["required_capabilities"] = capabilities
    for key in ("model", "effort", "cost_class"):
        normalized = str(raw.get(key) or "").strip().lower()
        if normalized:
            result[key] = normalized
    base_sha = str(raw.get("base_sha") or "").strip().lower()
    if base_sha:
        if re.fullmatch(r"[0-9a-f]{40,64}", base_sha) is None:
            raise StateConflict("constraint base_sha must be a full hexadecimal Git object id")
        result["base_sha"] = base_sha

    present_harness_keys = set(raw) & {
        "harness_binary_digest",
        "harness_version",
    }
    if present_harness_keys:
        if present_harness_keys != {
            "harness_binary_digest",
            "harness_version",
        }:
            raise StateConflict(
                "harness execution constraints require digest and version"
            )
        harness_digest = str(raw["harness_binary_digest"]).strip().lower()
        harness_version = str(raw["harness_version"]).strip()
        if re.fullmatch(r"[0-9a-f]{64}", harness_digest) is None:
            raise StateConflict(
                "harness_binary_digest must be a lowercase SHA-256 digest"
            )
        if (
            not harness_version
            or len(harness_version) > 64
            or _ROUTING_VALUE_RE.fullmatch(harness_version.lower()) is None
        ):
            raise StateConflict("harness_version must be a bounded identifier")
        result["harness_binary_digest"] = harness_digest
        result["harness_version"] = harness_version

    present_operator_keys = set(raw) & set(OPERATOR_HARNESS_BINDING_KEYS)
    if present_operator_keys:
        if present_operator_keys != set(OPERATOR_HARNESS_BINDING_KEYS):
            raise StateConflict(
                "operator harness constraints must carry the complete binding identity"
            )
        if "base_sha" not in raw:
            raise StateConflict(
                "operator harness constraints require the exact workspace base_sha"
            )
        if not isinstance(raw["operator_harness_armed"], bool):
            raise StateConflict("operator_harness_armed must be boolean")
        normalized_operator = _normalise_constraints(
            {
                "eligible_quota_classes": raw["operator_eligible_quota_classes"],
                "provider": raw["operator_provider"],
                "model": raw["operator_model"],
                "effort": raw["operator_effort"],
                "cost_class": raw["operator_cost_class"],
                "routing_policy_version": raw["operator_routing_policy_version"],
                "execution_profile_id": raw["operator_execution_profile_id"],
                "execution_profile_digest": raw[
                    "operator_execution_profile_digest"
                ],
                "capability_policy_version": raw[
                    "operator_capability_policy_version"
                ],
                "capability_policy_digest": raw[
                    "operator_capability_policy_digest"
                ],
                "base_sha": raw["base_sha"],
            }
        )
        for key in (
            "eligible_quota_classes",
            "provider",
            "model",
            "effort",
            "cost_class",
            "routing_policy_version",
            "execution_profile_id",
            "execution_profile_digest",
            "capability_policy_version",
            "capability_policy_digest",
        ):
            result[f"operator_{key}"] = normalized_operator[key]
        harness_digest = str(raw["operator_harness_binary_digest"]).strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", harness_digest) is None:
            raise StateConflict(
                "operator_harness_binary_digest must be a lowercase SHA-256 digest"
            )
        harness_version = str(raw["operator_harness_version"]).strip()
        if (
            not harness_version
            or len(harness_version) > 64
            or _ROUTING_VALUE_RE.fullmatch(harness_version.lower()) is None
        ):
            raise StateConflict("operator_harness_version must be a bounded identifier")
        result["operator_harness_binary_digest"] = harness_digest
        result["operator_harness_version"] = harness_version
        result["operator_harness_armed"] = raw["operator_harness_armed"]
    return result


def _normalise_seat(value: str, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if _SEAT_RE.fullmatch(normalized) is None or normalized not in _JOB_SEATS:
        raise StateConflict(
            f"{field} must be one of {', '.join(sorted(_JOB_SEATS))}"
        )
    return normalized


def _normalise_business_impact(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _BUSINESS_IMPACTS:
        raise StateConflict(
            "business_impact must be one of routine, material, critical"
        )
    return normalized


def _assert_child_does_not_widen_parent(
    parent_row: sqlite3.Row,
    *,
    requested: Sequence[str],
    allowed_write_paths: Sequence[str],
    constraints: dict[str, Any],
) -> None:
    """Refuse a child that would exceed its parent's grant.  Shrink-only (L6)."""

    parent_authorities = {
        str(item).strip().upper()
        for item in _json_loads(parent_row["requested_authorities_json"], fallback=[])
        if str(item).strip()
    }
    extra_authorities = sorted(set(requested) - parent_authorities)
    if extra_authorities:
        raise StateConflict(
            "child requested_authorities may only shrink relative to the parent: "
            + ", ".join(extra_authorities)
        )
    parent_paths = {
        str(item)
        for item in _json_loads(parent_row["allowed_write_paths_json"], fallback=[])
    }
    extra_paths = sorted(set(allowed_write_paths) - parent_paths)
    if extra_paths:
        raise StateConflict(
            "child allowed_write_paths may only shrink relative to the parent: "
            + ", ".join(extra_paths)
        )
    parent_constraints = _json_loads(
        parent_row["constraints_json"], fallback={}
    )
    parent_cost_value = parent_constraints.get("cost_class")
    if (
        parent_constraints.get("operator_harness_armed") is True
        and constraints.get("execution_profile_id")
        == parent_constraints.get("operator_execution_profile_id")
    ):
        parent_cost_value = parent_constraints.get("operator_cost_class")
    parent_cost = str(parent_cost_value or "").strip().lower()
    child_cost = str(constraints.get("cost_class") or "").strip().lower()
    if parent_cost and child_cost:
        parent_rank = _COST_CLASS_RANK.get(parent_cost)
        child_rank = _COST_CLASS_RANK.get(child_cost)
        if (
            parent_rank is None
            or child_rank is None
            or child_rank > parent_rank
        ):
            raise StateConflict(
                "child cost_class may only shrink relative to the parent"
            )


def _has_executive_provenance(
    provenance: dict[str, Any] | None, *, target: str
) -> bool:
    """Require a typed executive record before a job can name a higher seat."""

    if not isinstance(provenance, dict):
        return False
    schema = str(provenance.get("schema") or "")
    actor = str(provenance.get("actor") or "").strip().lower()
    if target == "ceo":
        return schema == "mastermind.ceo_intent.v1"
    return (
        schema in {"mastermind.executive_decision.v1", "mastermind.chairman_decision.v1"}
        and actor in {"chairman", "chris", "chairman-chris"}
    )


def _capacity_route_metadata(row: sqlite3.Row) -> dict[str, Any]:
    metadata = _json_loads(row["metadata_json"], fallback={})
    if not isinstance(metadata, dict):
        raise PersistenceError("worker quota-class metadata must be a mapping")
    return metadata


def _capacity_model_alias(row: sqlite3.Row) -> str:
    metadata = _capacity_route_metadata(row)
    return str(metadata.get("model_alias") or "").strip().lower()


def _capacity_matches_route(row: sqlite3.Row, constraints: dict[str, Any]) -> bool:
    if str(row["worker_id"]) in set(constraints.get("excluded_worker_ids") or []):
        return False
    aliases = constraints.get("preferred_model_aliases") or []
    profile_id = str(constraints.get("execution_profile_id") or "")
    if not aliases and not profile_id:
        return True
    metadata = _capacity_route_metadata(row)
    if aliases:
        worker_policy_version = str(
            metadata.get("routing_policy_version") or ""
        ).strip().lower()
        route_matches = (
            _capacity_model_alias(row) in aliases
            and worker_policy_version == constraints.get("routing_policy_version")
        )
        if not route_matches:
            return False
    if not profile_id:
        return True
    return all(
        str(metadata.get(key) or "").strip().lower()
        == str(constraints.get(key) or "").strip().lower()
        for key in (
            "execution_profile_id",
            "execution_profile_digest",
            "capability_policy_version",
            "capability_policy_digest",
        )
    )


def _capacity_route_rank(
    row: sqlite3.Row, constraints: dict[str, Any]
) -> tuple[int, str, str]:
    aliases = list(constraints.get("preferred_model_aliases") or [])
    model_alias = _capacity_model_alias(row)
    rank = aliases.index(model_alias) if model_alias in aliases else len(aliases)
    return rank, str(row["worker_id"]), str(row["quota_class"])


@dataclasses.dataclass(frozen=True)
class JobPayload:
    summary: str = ""
    completed_steps: list[str] = dataclasses.field(default_factory=list)
    current_state: str = ""
    artifacts: list[str] = dataclasses.field(default_factory=list)
    next_actions: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    verdict: str = ""

    @classmethod
    def from_value(cls, value: "JobPayload | dict[str, Any]") -> "JobPayload":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise StateConflict("checkpoint/result payload must be a JobPayload or mapping")

        def _strings(key: str) -> list[str]:
            raw = value.get(key, [])
            if raw is None:
                return []
            if not isinstance(raw, list):
                raise StateConflict(f"payload field {key!r} must be a list")
            return [str(item) for item in raw]

        verdict = str(value.get("verdict") or "").strip().lower()
        if verdict not in {"", "approve", "reject"}:
            raise StateConflict(
                "payload field 'verdict' must be empty, 'approve', or 'reject'"
            )
        return cls(
            summary=str(value.get("summary") or ""),
            completed_steps=_strings("completed_steps"),
            current_state=str(value.get("current_state") or ""),
            artifacts=_strings("artifacts"),
            next_actions=_strings("next_actions"),
            errors=_strings("errors"),
            verdict=verdict,
        )

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        # Verdict is an additive Phase 1F-B field.  Omitting the empty default
        # keeps legacy checkpoint/result payloads byte-shape compatible while
        # still persisting approve/reject on review jobs.
        if not self.verdict:
            value.pop("verdict", None)
        return value


@dataclasses.dataclass(frozen=True)
class WorkerQuotaClass:
    worker_id: str
    quota_class: str
    status: WorkerStatus
    provider: str
    model: str | None
    effort: str | None
    cost_class: str | None
    capabilities: list[str]
    active_attempt_id: str | None
    active_job_id: str | None
    fence_generation: int
    last_seen_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class Worker:
    worker_id: str
    provider: str
    account_label: str
    worker_type: str
    status: WorkerStatus
    capabilities: list[str]
    active_job_id: str | None
    last_seen_at: str
    metadata: dict[str, Any]
    quota_classes: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class Job:
    job_id: str
    objective: str
    department: str
    priority: int
    status: JobStatus
    assigned_worker_id: str | None
    assigned_quota_class: str | None
    authority_level: str
    branch: str | None
    worktree: str | None
    checkpoint: dict[str, Any] | None
    result: dict[str, Any] | None
    created_at: str
    updated_at: str
    constraints: dict[str, Any] = dataclasses.field(default_factory=dict)
    current_attempt_id: str | None = None
    attempt_count: int = 0
    attempt_limit: int = 10
    requested_authorities: list[str] = dataclasses.field(default_factory=list)
    authority_policy_hash: str = ""
    allowed_write_paths: list[str] = dataclasses.field(default_factory=list)
    validation_commands: list[list[str]] = dataclasses.field(default_factory=list)
    parent_job_id: str | None = None
    root_job_id: str = ""
    depth: int = 0
    owner_seat: str = "coo"
    escalation_target: str = "coo"
    business_impact: str = "routine"
    review_required: bool = False
    reviews_job_id: str | None = None
    orchestration_role: str | None = None
    orchestration_provenance: dict[str, Any] | None = None
    orchestration_provenance_digest: str | None = None
    plan_attempt_id: str | None = None
    plan_digest: str | None = None
    plan_step_id: str | None = None
    repair_round: int | None = None
    supersedes_job_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class Attempt:
    attempt_id: str
    job_id: str
    attempt_number: int
    worker_id: str
    quota_class: str
    status: AttemptStatus
    fence_generation: int
    lease_owner: str
    lease_expires_at: str
    heartbeat_at: str
    checkpoint_sequence: int
    checkpoint: dict[str, Any] | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: str
    finished_at: str
    version: int
    authority_policy_hash: str
    pid: int | None
    pgid: int | None
    process_start_identity: str | None
    boot_id: str | None
    provider_session_id: str | None
    stdout_path: str | None
    stderr_path: str | None
    result_path: str | None
    exit_code: int | None
    launch_metadata: dict[str, Any]
    execution_mode: str | None = None
    requested_execution_profile: dict[str, Any] | None = None
    requested_execution_profile_digest: str | None = None
    effective_grant: dict[str, Any] | None = None
    effective_grant_digest: str | None = None
    placement_snapshot: dict[str, Any] | None = None
    placement_snapshot_digest: str | None = None
    execution_principal_snapshot: dict[str, Any] | None = None
    execution_principal_snapshot_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return public attempt state.  The opaque lease token is never exposed."""
        value = dataclasses.asdict(self)
        value["status"] = self.status.value
        return value


@dataclasses.dataclass(frozen=True)
class AttemptLease:
    attempt: Attempt
    lease_token: str = dataclasses.field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Return safe claim output; callers access the token only as an attribute."""
        return {"attempt": self.attempt.to_dict()}


@dataclasses.dataclass(frozen=True)
class JobRequeueOutcome:
    """Durable command-aware Phase 1F-C requeue reconciliation."""

    job_id: str
    command_id: str
    event_id: int
    requeue_kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RetrySafetyProjection:
    """One caller expectation derived from a single Runtime snapshot."""

    attempt_id: str
    requeue_kind: str | None
    tx9_evidence_digest: str | None
    retry_evidence_digest: str
    evidence: RetrySafetyEvidence


@dataclasses.dataclass(frozen=True)
class CooRetryMutationOutcome:
    """Atomic COO retry decision, including no-effect reconciliation."""

    action: str
    command_id: str
    receipt: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class _RetrySafetyMaterial:
    projection: RetrySafetyProjection
    tx9_material: tuple[sqlite3.Row, dict[str, Any], str, dict[str, Any], str] | None


@dataclasses.dataclass(frozen=True, slots=True)
class ExecutiveDialogueSource:
    """Admission-owned immutable source for one strict-v2 dialogue family."""

    schema_version: str
    work_ref: str
    commission_ref: CommissionRef
    watch_mode: str | None

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTIVE_DIALOGUE_SOURCE_SCHEMA:
            raise StateConflict("v2 host dialogue source schema is invalid")
        if not isinstance(self.work_ref, str) or re.fullmatch(
            r"WS:[A-Z0-9][A-Z0-9-]{1,63}", self.work_ref
        ) is None:
            raise StateConflict("v2 dialogue source requires an exact work_ref")
        try:
            immutable_commission = normalize_commission_ref(self.commission_ref)
        except CommissionRefError:
            raise StateConflict(
                "v2 host dialogue source commission_ref is invalid"
            ) from None
        if self.watch_mode not in {None, "turn_watch_v1"}:
            raise StateConflict("v2 host dialogue source watch_mode is invalid")
        object.__setattr__(self, "commission_ref", immutable_commission)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "work_ref": self.work_ref,
            "commission_ref": self.commission_ref.to_dict(),
            "watch_mode": self.watch_mode,
        }


def normalize_executive_dialogue_source(
    value: Mapping[str, Any],
    *,
    work_ref: str | None = None,
) -> ExecutiveDialogueSource:
    """Validate immutable root-admission dialogue provenance."""

    if not isinstance(value, Mapping) or set(value) != _EXECUTIVE_DIALOGUE_SOURCE_KEYS:
        raise StateConflict("v2 host dialogue source fields are incomplete or drifted")
    source_work_ref = value.get("work_ref")
    if work_ref is not None and source_work_ref != work_ref:
        raise StateConflict("v2 dialogue source work_ref disagrees with admission")
    return ExecutiveDialogueSource(
        schema_version=value.get("schema_version"),
        work_ref=source_work_ref,
        commission_ref=value.get("commission_ref"),
        watch_mode=value.get("watch_mode"),
    )


def _dialogue_source_from_root_creation(
    connection: sqlite3.Connection,
    *,
    root_job_id: str,
) -> ExecutiveDialogueSource | None:
    """Re-read one optional host source from the immutable root creation Event."""

    root_row = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (root_job_id,)
    ).fetchone()
    if root_row is None:
        raise StateConflict("terminal completion lost its strict v2 root")
    root_role, root_orchestration, _root_digest = _decode_orchestration_job_fields(
        root_row
    )
    if (
        root_role != "aggregation"
        or not isinstance(root_orchestration, dict)
        or root_row["root_job_id"] != root_job_id
    ):
        raise StateConflict("terminal completion root is not a strict v2 root")
    event_rows = connection.execute(
        """SELECT * FROM events
           WHERE event_type='JOB_CREATED' AND job_id=?
           ORDER BY event_id""",
        (root_job_id,),
    ).fetchall()
    if len(event_rows) != 1:
        raise StateConflict("terminal completion root creation cardinality is not exact")
    event_row = event_rows[0]
    if (
        event_row["command_id"] != root_orchestration.get("command_id")
        or event_row["aggregate_type"] != "job"
        or event_row["aggregate_id"] != root_job_id
    ):
        raise StateConflict("terminal completion root creation Event drifted")
    try:
        payload = _strict_canonical_json_loads(
            str(event_row["payload_json"]),
            name="terminal completion root JOB_CREATED payload",
        )
    except PersistenceError as exc:
        raise StateConflict(
            f"terminal completion root creation evidence is invalid: {exc}"
        ) from exc
    provenance = payload.get("provenance") if isinstance(payload, dict) else None
    if not isinstance(provenance, dict):
        raise StateConflict("terminal completion root lost its host provenance")
    stored = provenance.get("dialogue_source")
    stored_digest = provenance.get("dialogue_source_digest")
    if stored is None:
        if stored_digest is not None:
            raise StateConflict("terminal completion dialogue source drifted")
        return None
    work_ref = provenance.get("workstream")
    if (
        not isinstance(stored, dict)
        or set(stored) != _EXECUTIVE_DIALOGUE_SOURCE_KEYS
        or stored.get("work_ref") != work_ref
        or not isinstance(stored_digest, str)
        or _DIGEST_RE.fullmatch(stored_digest) is None
        or stored_digest
        != hashlib.sha256(
            json.dumps(
                stored,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    ):
        raise StateConflict("terminal completion dialogue source drifted")
    normalized = normalize_executive_dialogue_source(
        stored,
        work_ref=str(work_ref),
    )
    if normalized.to_dict() != stored:
        raise StateConflict("terminal completion dialogue source is noncanonical")
    return normalized


@dataclasses.dataclass(frozen=True)
class ValidatedRoleCompletion:
    """One canonical Runtime snapshot for a completed orchestration child."""

    job: Job
    attempt: Attempt
    result_envelope: dict[str, Any]
    terminal_receipt: dict[str, Any]
    result_digest: str
    role_result_digest: str
    execution_mode: str
    dialogue_source: ExecutiveDialogueSource | None


@dataclasses.dataclass(frozen=True)
class OrchestrationDispatchOutcome:
    """Command-bound active lease or immutable terminal dispatch outcome."""

    command_id: str
    job_id: str
    attempt: Attempt
    outcome: str
    lease_token: str | None = dataclasses.field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.outcome == "ACTIVE":
            if self.attempt.status not in _LEASE_ACTIVE_ATTEMPT_STATUSES or not self.lease_token:
                raise StateConflict("ACTIVE dispatch outcome requires an active leased Attempt")
        elif self.outcome == "TERMINAL":
            if self.attempt.status not in _TERMINAL_ATTEMPT_STATUSES or self.lease_token is not None:
                raise StateConflict("TERMINAL dispatch outcome requires immutable terminal state")
        else:
            raise StateConflict("dispatch outcome must be ACTIVE or TERMINAL")

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "job_id": self.job_id,
            "attempt": self.attempt.to_dict(),
            "outcome": self.outcome,
        }


@dataclasses.dataclass(frozen=True)
class Event:
    event_id: int
    aggregate_type: str
    aggregate_id: str
    sequence: int
    event_type: str
    command_id: str
    actor: str
    job_id: str | None
    attempt_id: str | None
    worker_id: str | None
    quota_class: str | None
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


_MIGRATION_1: tuple[str, ...] = (
    """
    CREATE TABLE workers (
      worker_id TEXT PRIMARY KEY,
      provider TEXT NOT NULL,
      account_label TEXT NOT NULL,
      worker_type TEXT NOT NULL,
      identity_status TEXT NOT NULL DEFAULT 'ONLINE'
        CHECK(identity_status IN ('ONLINE','DRAINING','OFFLINE','ERROR')),
      metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
      last_seen_at_ms INTEGER NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
    )
    """,
    """
    CREATE TABLE worker_quota_classes (
      worker_id TEXT NOT NULL,
      quota_class TEXT NOT NULL,
      status TEXT NOT NULL
        CHECK(status IN ('AVAILABLE','BUSY','DRAINING','RATE_LIMITED','OFFLINE','ERROR')),
      provider TEXT NOT NULL,
      model TEXT,
      effort TEXT,
      cost_class TEXT,
      capabilities_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(capabilities_json) AND json_type(capabilities_json) = 'array'),
      metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
      held_attempt_id TEXT,
      fence_counter INTEGER NOT NULL DEFAULT 0 CHECK(fence_counter >= 0),
      last_seen_at_ms INTEGER NOT NULL,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
      PRIMARY KEY(worker_id, quota_class),
      UNIQUE(held_attempt_id),
      FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id, quota_class, held_attempt_id)
        REFERENCES attempts(worker_id, quota_class, attempt_id)
        DEFERRABLE INITIALLY DEFERRED,
      CHECK(status != 'AVAILABLE' OR held_attempt_id IS NULL),
      CHECK(status != 'BUSY' OR held_attempt_id IS NOT NULL)
    )
    """,
    """
    CREATE TABLE jobs (
      job_id TEXT PRIMARY KEY,
      objective TEXT NOT NULL CHECK(length(trim(objective)) > 0),
      department TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL
        CHECK(status IN ('QUEUED','RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED',
                         'LOST','CANCEL_REQUESTED','COMPLETED','CANCELLED')),
      assigned_worker_id TEXT,
      assigned_quota_class TEXT,
      current_attempt_id TEXT,
      authority_level TEXT NOT NULL,
      branch TEXT,
      worktree TEXT,
      constraints_json TEXT NOT NULL
        CHECK(json_valid(constraints_json) AND json_type(constraints_json) = 'object'),
      requested_authorities_json TEXT NOT NULL
        CHECK(json_valid(requested_authorities_json) AND json_type(requested_authorities_json) = 'array'),
      authority_policy_hash TEXT NOT NULL CHECK(length(authority_policy_hash) = 64),
      allowed_write_paths_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(allowed_write_paths_json) AND json_type(allowed_write_paths_json) = 'array'),
      validation_commands_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(validation_commands_json) AND json_type(validation_commands_json) = 'array'),
      checkpoint_json TEXT CHECK(
        checkpoint_json IS NULL OR (json_valid(checkpoint_json) AND json_type(checkpoint_json) = 'object')
      ),
      result_json TEXT CHECK(
        result_json IS NULL OR (json_valid(result_json) AND json_type(result_json) = 'object')
      ),
      attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
      attempt_limit INTEGER NOT NULL DEFAULT 10 CHECK(attempt_limit > 0),
      available_at_ms INTEGER NOT NULL,
      cancel_requested_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
      FOREIGN KEY(assigned_worker_id, assigned_quota_class)
        REFERENCES worker_quota_classes(worker_id, quota_class) ON DELETE RESTRICT,
      FOREIGN KEY(job_id, current_attempt_id, assigned_worker_id, assigned_quota_class)
        REFERENCES attempts(job_id, attempt_id, worker_id, quota_class)
        DEFERRABLE INITIALLY DEFERRED,
      CHECK((assigned_worker_id IS NULL) = (assigned_quota_class IS NULL)),
      CHECK((current_attempt_id IS NULL) = (assigned_worker_id IS NULL)),
      CHECK(status != 'QUEUED' OR current_attempt_id IS NULL),
      CHECK(status NOT IN ('RUNNING','CHECKPOINTED','RATE_LIMITED','FAILED','LOST',
                           'CANCEL_REQUESTED','COMPLETED') OR current_attempt_id IS NOT NULL),
      CHECK(status != 'COMPLETED' OR result_json IS NOT NULL)
    )
    """,
    """
    CREATE TABLE attempts (
      attempt_id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      attempt_number INTEGER NOT NULL CHECK(attempt_number > 0),
      worker_id TEXT NOT NULL,
      quota_class TEXT NOT NULL,
      status TEXT NOT NULL
        CHECK(status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED',
                         'RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')),
      fence_generation INTEGER NOT NULL CHECK(fence_generation > 0),
      authority_policy_hash TEXT NOT NULL CHECK(length(authority_policy_hash) = 64),
      lease_token TEXT,
      lease_owner TEXT NOT NULL,
      lease_expires_at_ms INTEGER NOT NULL,
      heartbeat_at_ms INTEGER NOT NULL,
      checkpoint_sequence INTEGER NOT NULL DEFAULT 0 CHECK(checkpoint_sequence >= 0),
      checkpoint_json TEXT CHECK(
        checkpoint_json IS NULL OR (json_valid(checkpoint_json) AND json_type(checkpoint_json) = 'object')
      ),
      result_json TEXT CHECK(
        result_json IS NULL OR (json_valid(result_json) AND json_type(result_json) = 'object')
      ),
      error_json TEXT CHECK(
        error_json IS NULL OR (json_valid(error_json) AND json_type(error_json) = 'object')
      ),
      pid INTEGER,
      pgid INTEGER,
      process_start_identity TEXT,
      boot_id TEXT,
      provider_session_id TEXT,
      stdout_path TEXT,
      stderr_path TEXT,
      result_path TEXT,
      exit_code INTEGER,
      launch_metadata_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(launch_metadata_json) AND json_type(launch_metadata_json) = 'object'),
      started_at_ms INTEGER NOT NULL,
      finished_at_ms INTEGER,
      created_at_ms INTEGER NOT NULL,
      updated_at_ms INTEGER NOT NULL,
      version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
      UNIQUE(job_id, attempt_number),
      UNIQUE(worker_id, quota_class, attempt_id),
      UNIQUE(job_id, attempt_id, worker_id, quota_class),
      FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id, quota_class)
        REFERENCES worker_quota_classes(worker_id, quota_class) ON DELETE RESTRICT,
      CHECK((status IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED'))
            = (finished_at_ms IS NOT NULL)),
      CHECK(status NOT IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')
            OR lease_token IS NULL),
      CHECK(status IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')
            OR lease_token IS NOT NULL),
      CHECK(status != 'COMPLETED' OR result_json IS NOT NULL),
      CHECK(pid IS NULL OR pid > 0),
      CHECK(pgid IS NULL OR pgid > 0),
      CHECK(
        (pid IS NULL AND pgid IS NULL AND process_start_identity IS NULL AND boot_id IS NULL)
        OR
        (pid IS NOT NULL AND pgid IS NOT NULL
         AND length(trim(process_start_identity)) > 0 AND length(trim(boot_id)) > 0)
      )
    )
    """,
    """
    CREATE TABLE events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      aggregate_type TEXT NOT NULL,
      aggregate_id TEXT NOT NULL,
      sequence INTEGER NOT NULL CHECK(sequence > 0),
      event_type TEXT NOT NULL,
      command_id TEXT NOT NULL UNIQUE,
      actor TEXT NOT NULL,
      job_id TEXT,
      attempt_id TEXT,
      worker_id TEXT,
      quota_class TEXT,
      payload_json TEXT NOT NULL DEFAULT '{}'
        CHECK(json_valid(payload_json) AND json_type(payload_json) = 'object'),
      created_at_ms INTEGER NOT NULL,
      UNIQUE(aggregate_type, aggregate_id, sequence),
      FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE RESTRICT,
      FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id) REFERENCES workers(worker_id) ON DELETE RESTRICT,
      FOREIGN KEY(worker_id, quota_class)
        REFERENCES worker_quota_classes(worker_id, quota_class) ON DELETE RESTRICT
    )
    """,
    """
    CREATE UNIQUE INDEX one_lease_active_attempt_per_job
      ON attempts(job_id)
      WHERE status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
    """,
    """
    CREATE UNIQUE INDEX one_lease_active_attempt_per_capacity
      ON attempts(worker_id, quota_class)
      WHERE status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
    """,
    "CREATE INDEX jobs_dispatch_order ON jobs(status, available_at_ms, priority DESC, created_at_ms, job_id)",
    "CREATE INDEX attempts_expiry ON attempts(status, lease_expires_at_ms)",
    """
    CREATE TRIGGER events_are_immutable_update
    BEFORE UPDATE ON events BEGIN
      SELECT RAISE(ABORT, 'events are immutable');
    END
    """,
    """
    CREATE TRIGGER events_are_immutable_delete
    BEFORE DELETE ON events BEGIN
      SELECT RAISE(ABORT, 'events are immutable');
    END
    """,
    """
    CREATE TRIGGER terminal_attempts_are_immutable
    BEFORE UPDATE ON attempts
    WHEN OLD.status IN ('RATE_LIMITED','FAILED','LOST','COMPLETED','CANCELLED')
    BEGIN
      SELECT RAISE(ABORT, 'terminal attempts are immutable');
    END
    """,
)

_MIGRATION_2: tuple[str, ...] = (
    "ALTER TABLE jobs ADD COLUMN parent_job_id TEXT REFERENCES jobs(job_id) ON DELETE RESTRICT",
    "ALTER TABLE jobs ADD COLUMN root_job_id TEXT",
    "ALTER TABLE jobs ADD COLUMN depth INTEGER NOT NULL DEFAULT 0 CHECK(depth >= 0)",
    "ALTER TABLE jobs ADD COLUMN owner_seat TEXT NOT NULL DEFAULT 'coo' CHECK(owner_seat IN ('coo','ceo','chairman'))",
    "ALTER TABLE jobs ADD COLUMN escalation_target TEXT NOT NULL DEFAULT 'coo' CHECK(escalation_target IN ('coo','ceo','chairman'))",
    "ALTER TABLE jobs ADD COLUMN business_impact TEXT NOT NULL DEFAULT 'routine' CHECK(business_impact IN ('routine','material','critical'))",
    "ALTER TABLE jobs ADD COLUMN review_required INTEGER NOT NULL DEFAULT 0 CHECK(review_required IN (0,1))",
    "ALTER TABLE jobs ADD COLUMN reviews_job_id TEXT REFERENCES jobs(job_id) ON DELETE RESTRICT",
    "UPDATE jobs SET root_job_id=job_id WHERE root_job_id IS NULL",
    "CREATE INDEX jobs_parent_dispatch ON jobs(parent_job_id,status,available_at_ms,priority DESC,created_at_ms,job_id)",
    "CREATE INDEX jobs_root_order ON jobs(root_job_id,depth,created_at_ms,job_id)",
    """
    CREATE TRIGGER jobs_hierarchy_is_immutable
    BEFORE UPDATE OF parent_job_id,root_job_id,depth,reviews_job_id ON jobs
    WHEN OLD.parent_job_id IS NOT NEW.parent_job_id
      OR OLD.root_job_id IS NOT NEW.root_job_id
      OR OLD.depth IS NOT NEW.depth
      OR OLD.reviews_job_id IS NOT NEW.reviews_job_id
    BEGIN
      SELECT RAISE(ABORT, 'job hierarchy and review pointer are immutable');
    END
    """,
    """
    CREATE TRIGGER jobs_review_pointer_contract
    BEFORE INSERT ON jobs
    WHEN NEW.reviews_job_id IS NOT NULL AND NEW.review_required != 0
    BEGIN
      SELECT RAISE(ABORT, 'a review job cannot require review');
    END
    """,
    """
    CREATE TRIGGER jobs_review_pointer_contract_update
    BEFORE UPDATE OF review_required,reviews_job_id ON jobs
    WHEN NEW.reviews_job_id IS NOT NULL AND NEW.review_required != 0
    BEGIN
      SELECT RAISE(ABORT, 'a review job cannot require review');
    END
    """,
    """
    CREATE TRIGGER jobs_root_contract
    BEFORE INSERT ON jobs
    WHEN NEW.root_job_id IS NULL OR length(trim(NEW.root_job_id)) = 0
    BEGIN
      SELECT RAISE(ABORT, 'root_job_id is required');
    END
    """,
    """
    CREATE TRIGGER jobs_parent_is_not_self
    BEFORE INSERT ON jobs
    WHEN NEW.parent_job_id IS NOT NULL AND NEW.parent_job_id = NEW.job_id
    BEGIN
      SELECT RAISE(ABORT, 'a job cannot be its own parent');
    END
    """,
)


# OHF state is deliberately additive to the existing Executive authority store.
# The old Attempt identity columns remain the sealed-worker projection; rich
# harness identity lives exclusively in the two tables below.
_MIGRATION_3: tuple[str, ...] = (
    """
    ALTER TABLE attempts ADD COLUMN execution_mode TEXT
    CHECK (execution_mode IN ('SEALED_WORKER','OPERATOR_HARNESS'))
    """,
    "ALTER TABLE attempts ADD COLUMN requested_execution_profile_json TEXT",
    "ALTER TABLE attempts ADD COLUMN requested_execution_profile_digest TEXT",
    """
    CREATE TABLE harness_session_epochs (
      session_epoch_id TEXT PRIMARY KEY,
      attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
      worker_id TEXT NOT NULL,
      epoch_number INTEGER NOT NULL CHECK (epoch_number >= 1),
      provider_session_id TEXT,
      state TEXT NOT NULL CHECK (state IN ('CURRENT','TERMINAL','ABANDONED')),
      created_at_ms INTEGER NOT NULL,
      ended_at_ms INTEGER,
      abandonment_class TEXT,
      UNIQUE(attempt_id,epoch_number)
    )
    """,
    """
    CREATE TABLE process_generations (
      process_generation_id TEXT PRIMARY KEY,
      session_epoch_id TEXT NOT NULL REFERENCES harness_session_epochs(session_epoch_id),
      worker_id TEXT NOT NULL,
      provider_session_id TEXT,
      generation_number INTEGER NOT NULL CHECK (generation_number >= 1),
      pid INTEGER CHECK (pid IS NULL OR pid > 0),
      pgid INTEGER CHECK (pgid IS NULL OR pgid > 0),
      process_start_identity TEXT,
      boot_id TEXT,
      started_at_ms INTEGER NOT NULL,
      last_observed_at_ms INTEGER,
      ended_at_ms INTEGER,
      termination_class TEXT,
      exit_code INTEGER,
      executive_writer_held INTEGER NOT NULL CHECK (executive_writer_held IN (0,1)),
      provider_writer_state TEXT NOT NULL CHECK (provider_writer_state IN ('HELD','RELEASED','UNKNOWN')),
      observed_attestation_json TEXT,
      observed_attestation_digest TEXT,
      created_at_ms INTEGER NOT NULL,
      UNIQUE(session_epoch_id,generation_number),
      CHECK((pid IS NULL AND pgid IS NULL AND process_start_identity IS NULL AND boot_id IS NULL)
        OR (pid IS NOT NULL AND pgid IS NOT NULL
          AND coalesce(length(trim(process_start_identity)),0) > 0
          AND coalesce(length(trim(boot_id)),0) > 0))
    )
    """,
    """
    CREATE UNIQUE INDEX harness_session_epochs_one_current
    ON harness_session_epochs(attempt_id) WHERE state='CURRENT'
    """,
    """
    CREATE UNIQUE INDEX harness_session_epochs_session_realm
    ON harness_session_epochs(worker_id,provider_session_id)
    WHERE provider_session_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX process_generations_one_epoch_writer
    ON process_generations(session_epoch_id) WHERE executive_writer_held=1
    """,
    """
    CREATE UNIQUE INDEX process_generations_one_executive_writer
    ON process_generations(worker_id,provider_session_id)
    WHERE executive_writer_held=1 AND provider_session_id IS NOT NULL
    """,
    """
    CREATE TRIGGER attempts_ohf_mode_immutable
    BEFORE UPDATE OF execution_mode ON attempts
    WHEN OLD.execution_mode IS NOT NULL AND OLD.execution_mode IS NOT NEW.execution_mode
    BEGIN SELECT RAISE(ABORT, 'attempt execution mode is immutable'); END
    """,
    """
    CREATE TRIGGER attempts_ohf_profile_pair
    BEFORE INSERT ON attempts
    WHEN (NEW.requested_execution_profile_json IS NULL) != (NEW.requested_execution_profile_digest IS NULL)
      OR (NEW.execution_mode='OPERATOR_HARNESS'
          AND NEW.requested_execution_profile_json IS NULL)
    BEGIN SELECT RAISE(ABORT, 'requested profile json and digest must be paired'); END
    """,
    """
    CREATE TRIGGER attempts_ohf_profile_pair_update
    BEFORE UPDATE OF requested_execution_profile_json,requested_execution_profile_digest ON attempts
    WHEN (NEW.requested_execution_profile_json IS NULL) != (NEW.requested_execution_profile_digest IS NULL)
      OR (NEW.execution_mode='OPERATOR_HARNESS'
          AND NEW.requested_execution_profile_json IS NULL)
      OR (OLD.requested_execution_profile_json IS NOT NULL AND
          (OLD.requested_execution_profile_json IS NOT NEW.requested_execution_profile_json
           OR OLD.requested_execution_profile_digest IS NOT NEW.requested_execution_profile_digest))
    BEGIN SELECT RAISE(ABORT, 'requested profile is immutable and paired'); END
    """,
    """
    CREATE TRIGGER attempts_ohf_mode_requires_profile
    BEFORE UPDATE OF execution_mode ON attempts
    WHEN NEW.execution_mode='OPERATOR_HARNESS'
      AND (NEW.requested_execution_profile_json IS NULL
           OR NEW.requested_execution_profile_digest IS NULL)
    BEGIN SELECT RAISE(ABORT, 'OHF mode requires a sealed requested profile'); END
    """,
    """
    CREATE TRIGGER harness_session_epoch_session_immutable
    BEFORE UPDATE OF provider_session_id ON harness_session_epochs
    WHEN OLD.provider_session_id IS NOT NULL AND OLD.provider_session_id IS NOT NEW.provider_session_id
    BEGIN SELECT RAISE(ABORT, 'epoch provider session is immutable'); END
    """,
    """
    CREATE TRIGGER harness_session_epoch_identity_immutable
    BEFORE UPDATE OF session_epoch_id,attempt_id,worker_id,epoch_number
    ON harness_session_epochs
    WHEN OLD.session_epoch_id IS NOT NEW.session_epoch_id
      OR OLD.attempt_id IS NOT NEW.attempt_id
      OR OLD.worker_id IS NOT NEW.worker_id
      OR OLD.epoch_number IS NOT NEW.epoch_number
    BEGIN SELECT RAISE(ABORT, 'epoch identity and projection are immutable'); END
    """,
    """
    CREATE TRIGGER harness_session_epoch_no_reopen
    BEFORE UPDATE OF state ON harness_session_epochs
    WHEN OLD.state IN ('TERMINAL','ABANDONED') AND NEW.state='CURRENT'
    BEGIN SELECT RAISE(ABORT, 'terminal or abandoned epoch cannot become current'); END
    """,
    """
    CREATE TRIGGER harness_epoch_worker_projection_insert
    BEFORE INSERT ON harness_session_epochs
    WHEN NEW.worker_id != (SELECT worker_id FROM attempts WHERE attempt_id=NEW.attempt_id)
      OR (NEW.provider_session_id IS NOT NULL AND length(trim(NEW.provider_session_id))=0)
    BEGIN SELECT RAISE(ABORT, 'epoch worker/session projection mismatch'); END
    """,
    """
    CREATE TRIGGER process_generation_projection_insert
    BEFORE INSERT ON process_generations
    WHEN NEW.worker_id != (SELECT worker_id FROM harness_session_epochs WHERE session_epoch_id=NEW.session_epoch_id)
      OR NEW.provider_session_id IS NOT
         (SELECT provider_session_id FROM harness_session_epochs WHERE session_epoch_id=NEW.session_epoch_id)
      OR (NEW.provider_session_id IS NOT NULL AND length(trim(NEW.provider_session_id))=0)
    BEGIN SELECT RAISE(ABORT, 'generation worker/session projection mismatch'); END
    """,
    """
    CREATE TRIGGER process_generation_projection_update
    BEFORE UPDATE OF process_generation_id,session_epoch_id,worker_id,
                     generation_number,provider_session_id ON process_generations
    WHEN OLD.process_generation_id IS NOT NEW.process_generation_id
      OR OLD.session_epoch_id IS NOT NEW.session_epoch_id
      OR OLD.worker_id IS NOT NEW.worker_id
      OR OLD.generation_number IS NOT NEW.generation_number
      OR NEW.worker_id != (SELECT worker_id FROM harness_session_epochs WHERE session_epoch_id=NEW.session_epoch_id)
      OR NEW.provider_session_id IS NOT
         (SELECT provider_session_id FROM harness_session_epochs WHERE session_epoch_id=NEW.session_epoch_id)
      OR (NEW.provider_session_id IS NOT NULL AND length(trim(NEW.provider_session_id))=0)
    BEGIN SELECT RAISE(ABORT, 'generation worker/session projection mismatch'); END
    """,
    """
    CREATE TRIGGER attempts_ohf_legacy_identity_null
    BEFORE UPDATE ON attempts
    WHEN NEW.execution_mode='OPERATOR_HARNESS' AND (
      NEW.pid IS NOT NULL OR NEW.pgid IS NOT NULL OR NEW.process_start_identity IS NOT NULL
      OR NEW.boot_id IS NOT NULL OR NEW.provider_session_id IS NOT NULL)
    BEGIN SELECT RAISE(ABORT, 'OHF legacy Attempt identity must remain NULL'); END
    """,
)


# Phase 1F-C is an additive schema.  SQL enforces the closed nullability,
# write-once, role, uniqueness, and immutable-routing floors; Runtime repeats
# canonical JSON/digest and cross-row lineage checks before every write.
_MIGRATION_4: tuple[str, ...] = (
    "ALTER TABLE jobs ADD COLUMN orchestration_role TEXT",
    "ALTER TABLE jobs ADD COLUMN orchestration_provenance_json TEXT",
    "ALTER TABLE jobs ADD COLUMN orchestration_provenance_digest TEXT",
    "ALTER TABLE jobs ADD COLUMN plan_attempt_id TEXT REFERENCES attempts(attempt_id) ON DELETE RESTRICT",
    "ALTER TABLE jobs ADD COLUMN plan_digest TEXT",
    "ALTER TABLE jobs ADD COLUMN plan_step_id TEXT",
    "ALTER TABLE jobs ADD COLUMN repair_round INTEGER",
    "ALTER TABLE jobs ADD COLUMN supersedes_job_id TEXT REFERENCES jobs(job_id) ON DELETE RESTRICT",
    "ALTER TABLE attempts ADD COLUMN effective_grant_json TEXT",
    "ALTER TABLE attempts ADD COLUMN effective_grant_digest TEXT",
    "ALTER TABLE attempts ADD COLUMN placement_snapshot_json TEXT",
    "ALTER TABLE attempts ADD COLUMN placement_snapshot_digest TEXT",
    "ALTER TABLE attempts ADD COLUMN execution_principal_snapshot_json TEXT",
    "ALTER TABLE attempts ADD COLUMN execution_principal_snapshot_digest TEXT",
    """
    CREATE UNIQUE INDEX jobs_one_plan_per_root
    ON jobs(root_job_id) WHERE orchestration_role='plan'
    """,
    """
    CREATE UNIQUE INDEX jobs_one_revision_per_round
    ON jobs(root_job_id,plan_digest,plan_step_id,repair_round)
    WHERE orchestration_role IN ('work','repair')
    """,
    """
    CREATE UNIQUE INDEX jobs_one_repair_per_predecessor
    ON jobs(supersedes_job_id) WHERE supersedes_job_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX events_one_coo_plan_admission_per_root
    ON events(job_id) WHERE event_type='COO_PLAN_ADMITTED'
    """,
    """
    CREATE UNIQUE INDEX events_one_coo_handoff_per_root
    ON events(job_id) WHERE event_type='COO_AGGREGATION_HANDOFF_READY'
    """,
    """
    CREATE UNIQUE INDEX events_one_work_admission_per_generation
    ON events(aggregate_type,aggregate_id)
    WHERE event_type='ORCHESTRATION_WORK_ADMITTED'
      AND aggregate_type='process_generation'
    """,
    """
    CREATE UNIQUE INDEX events_one_role_result_seal_per_attempt
    ON events(attempt_id)
    WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id IS NOT NULL
    """,
    """
    CREATE TRIGGER jobs_orchestration_contract_insert
    BEFORE INSERT ON jobs
    WHEN
      (NEW.orchestration_role IS NULL AND (
        NEW.orchestration_provenance_json IS NOT NULL OR
        NEW.orchestration_provenance_digest IS NOT NULL OR
        NEW.plan_attempt_id IS NOT NULL OR NEW.plan_digest IS NOT NULL OR
        NEW.plan_step_id IS NOT NULL OR NEW.repair_round IS NOT NULL OR
        NEW.supersedes_job_id IS NOT NULL
      )) OR
      (NEW.orchestration_role IS NOT NULL AND (
        NEW.orchestration_role NOT IN ('plan','work','review','repair','aggregation') OR
        NEW.orchestration_provenance_json IS NULL OR
        NOT json_valid(NEW.orchestration_provenance_json) OR
        json_type(NEW.orchestration_provenance_json) != 'object' OR
        NEW.orchestration_provenance_digest IS NULL OR
        length(NEW.orchestration_provenance_digest) != 64
      )) OR
      (NEW.orchestration_role IN ('aggregation','plan') AND (
        NEW.plan_attempt_id IS NOT NULL OR NEW.plan_digest IS NOT NULL OR
        NEW.plan_step_id IS NOT NULL OR NEW.repair_round IS NOT NULL OR
        NEW.supersedes_job_id IS NOT NULL
      )) OR
      (NEW.orchestration_role='work' AND (
        NEW.plan_attempt_id IS NULL OR NEW.plan_digest IS NULL OR
        NEW.plan_step_id IS NULL OR typeof(NEW.repair_round) != 'integer' OR
        NEW.repair_round != 0 OR
        NEW.supersedes_job_id IS NOT NULL
      )) OR
      (NEW.orchestration_role='review' AND (
        NEW.plan_attempt_id IS NULL OR NEW.plan_digest IS NULL OR
        NEW.plan_step_id IS NULL OR typeof(NEW.repair_round) != 'integer' OR
        NEW.repair_round NOT BETWEEN 0 AND 2 OR
        NEW.supersedes_job_id IS NOT NULL OR NEW.reviews_job_id IS NULL
      )) OR
      (NEW.orchestration_role='repair' AND (
        NEW.plan_attempt_id IS NULL OR NEW.plan_digest IS NULL OR
        NEW.plan_step_id IS NULL OR typeof(NEW.repair_round) != 'integer' OR
        NEW.repair_round NOT BETWEEN 1 AND 2 OR
        NEW.supersedes_job_id IS NULL
      ))
    BEGIN SELECT RAISE(ABORT, 'invalid orchestration job contract'); END
    """,
    """
    CREATE TRIGGER jobs_orchestration_fields_immutable
    BEFORE UPDATE OF orchestration_role,orchestration_provenance_json,
      orchestration_provenance_digest,plan_attempt_id,plan_digest,plan_step_id,
      repair_round,supersedes_job_id ON jobs
    WHEN OLD.orchestration_role IS NOT NEW.orchestration_role
      OR OLD.orchestration_provenance_json IS NOT NEW.orchestration_provenance_json
      OR OLD.orchestration_provenance_digest IS NOT NEW.orchestration_provenance_digest
      OR OLD.plan_attempt_id IS NOT NEW.plan_attempt_id
      OR OLD.plan_digest IS NOT NEW.plan_digest
      OR OLD.plan_step_id IS NOT NEW.plan_step_id
      OR OLD.repair_round IS NOT NEW.repair_round
      OR OLD.supersedes_job_id IS NOT NEW.supersedes_job_id
    BEGIN SELECT RAISE(ABORT, 'orchestration job fields are immutable'); END
    """,
    """
    CREATE TRIGGER attempts_orchestration_pairs_insert
    BEFORE INSERT ON attempts
    WHEN (NEW.effective_grant_json IS NULL) != (NEW.effective_grant_digest IS NULL)
      OR (NEW.placement_snapshot_json IS NULL) != (NEW.placement_snapshot_digest IS NULL)
      OR (NEW.execution_principal_snapshot_json IS NULL) !=
         (NEW.execution_principal_snapshot_digest IS NULL)
      OR (NEW.effective_grant_json IS NOT NULL AND
          (NOT json_valid(NEW.effective_grant_json) OR json_type(NEW.effective_grant_json) != 'object'
           OR length(NEW.effective_grant_digest) != 64))
      OR (NEW.placement_snapshot_json IS NOT NULL AND
          (NOT json_valid(NEW.placement_snapshot_json) OR json_type(NEW.placement_snapshot_json) != 'object'
           OR length(NEW.placement_snapshot_digest) != 64))
      OR (NEW.execution_principal_snapshot_json IS NOT NULL AND
          (NOT json_valid(NEW.execution_principal_snapshot_json)
           OR json_type(NEW.execution_principal_snapshot_json) != 'object'
           OR length(NEW.execution_principal_snapshot_digest) != 64))
    BEGIN SELECT RAISE(ABORT, 'orchestration attempt pairs are invalid'); END
    """,
    """
    CREATE TRIGGER attempts_orchestration_job_contract_insert
    BEFORE INSERT ON attempts
    WHEN (
        (SELECT orchestration_role FROM jobs WHERE job_id=NEW.job_id) IS NULL
        AND (
          NEW.effective_grant_json IS NOT NULL OR NEW.effective_grant_digest IS NOT NULL OR
          NEW.placement_snapshot_json IS NOT NULL OR NEW.placement_snapshot_digest IS NOT NULL OR
          NEW.execution_principal_snapshot_json IS NOT NULL OR
          NEW.execution_principal_snapshot_digest IS NOT NULL
        )
      ) OR (
        (SELECT orchestration_role FROM jobs WHERE job_id=NEW.job_id) IS NOT NULL
        AND (
          NEW.effective_grant_json IS NULL OR NEW.effective_grant_digest IS NULL OR
          NEW.placement_snapshot_json IS NULL OR NEW.placement_snapshot_digest IS NULL
        )
      )
    BEGIN SELECT RAISE(ABORT, 'attempt grant/placement does not match job role'); END
    """,
    """
    CREATE TRIGGER attempts_orchestration_job_contract_update
    BEFORE UPDATE OF effective_grant_json,effective_grant_digest,
      placement_snapshot_json,placement_snapshot_digest,
      execution_principal_snapshot_json,execution_principal_snapshot_digest ON attempts
    WHEN (
        (SELECT orchestration_role FROM jobs WHERE job_id=NEW.job_id) IS NULL
        AND (
          NEW.effective_grant_json IS NOT NULL OR NEW.effective_grant_digest IS NOT NULL OR
          NEW.placement_snapshot_json IS NOT NULL OR NEW.placement_snapshot_digest IS NOT NULL OR
          NEW.execution_principal_snapshot_json IS NOT NULL OR
          NEW.execution_principal_snapshot_digest IS NOT NULL
        )
      ) OR (
        (SELECT orchestration_role FROM jobs WHERE job_id=NEW.job_id) IS NOT NULL
        AND (
          NEW.effective_grant_json IS NULL OR NEW.effective_grant_digest IS NULL OR
          NEW.placement_snapshot_json IS NULL OR NEW.placement_snapshot_digest IS NULL
        )
      )
    BEGIN SELECT RAISE(ABORT, 'attempt grant/placement does not match job role'); END
    """,
    """
    CREATE TRIGGER attempts_orchestration_pairs_immutable
    BEFORE UPDATE OF effective_grant_json,effective_grant_digest,
      placement_snapshot_json,placement_snapshot_digest,
      execution_principal_snapshot_json,execution_principal_snapshot_digest
      ON attempts
    WHEN (OLD.effective_grant_json IS NOT NULL AND (
            OLD.effective_grant_json IS NOT NEW.effective_grant_json OR
            OLD.effective_grant_digest IS NOT NEW.effective_grant_digest))
      OR (OLD.placement_snapshot_json IS NOT NULL AND (
            OLD.placement_snapshot_json IS NOT NEW.placement_snapshot_json OR
            OLD.placement_snapshot_digest IS NOT NEW.placement_snapshot_digest))
      OR (OLD.execution_principal_snapshot_json IS NOT NULL AND (
            OLD.execution_principal_snapshot_json IS NOT NEW.execution_principal_snapshot_json OR
            OLD.execution_principal_snapshot_digest IS NOT NEW.execution_principal_snapshot_digest))
      OR (NEW.effective_grant_json IS NULL) != (NEW.effective_grant_digest IS NULL)
      OR (NEW.placement_snapshot_json IS NULL) != (NEW.placement_snapshot_digest IS NULL)
      OR (NEW.execution_principal_snapshot_json IS NULL) !=
         (NEW.execution_principal_snapshot_digest IS NULL)
      OR (NEW.effective_grant_json IS NOT NULL AND
          (NOT json_valid(NEW.effective_grant_json) OR json_type(NEW.effective_grant_json) != 'object'
           OR length(NEW.effective_grant_digest) != 64))
      OR (NEW.placement_snapshot_json IS NOT NULL AND
          (NOT json_valid(NEW.placement_snapshot_json) OR json_type(NEW.placement_snapshot_json) != 'object'
           OR length(NEW.placement_snapshot_digest) != 64))
      OR (NEW.execution_principal_snapshot_json IS NOT NULL AND
          (NOT json_valid(NEW.execution_principal_snapshot_json)
           OR json_type(NEW.execution_principal_snapshot_json) != 'object'
           OR length(NEW.execution_principal_snapshot_digest) != 64))
    BEGIN SELECT RAISE(ABORT, 'orchestration attempt pairs are immutable and paired'); END
    """,
    """
    CREATE TRIGGER workers_identity_contract_insert
    BEFORE INSERT ON workers
    WHEN NEW.provider != lower(trim(NEW.provider))
      OR NEW.provider GLOB '*[^a-z0-9._-]*'
      OR NEW.provider NOT GLOB '[a-z0-9]*'
      OR length(NEW.provider) NOT BETWEEN 1 AND 64
      OR NEW.account_label != lower(trim(NEW.account_label))
      OR NEW.account_label GLOB '*[^a-z0-9._@+:-]*'
      OR NEW.account_label NOT GLOB '[a-z0-9]*'
      OR length(NEW.account_label) NOT BETWEEN 1 AND 128
    BEGIN SELECT RAISE(ABORT, 'worker provider/account identity is not canonical'); END
    """,
    """
    CREATE TRIGGER workers_identity_immutable
    BEFORE UPDATE OF provider,account_label ON workers
    WHEN OLD.provider IS NOT NEW.provider OR OLD.account_label IS NOT NEW.account_label
    BEGIN SELECT RAISE(ABORT, 'worker provider/account identity is immutable'); END
    """,
    """
    CREATE TRIGGER worker_quota_provider_contract_insert
    BEFORE INSERT ON worker_quota_classes
    WHEN NEW.provider != lower(trim(NEW.provider))
      OR NEW.provider GLOB '*[^a-z0-9._-]*'
      OR NEW.provider NOT GLOB '[a-z0-9]*'
      OR length(NEW.provider) NOT BETWEEN 1 AND 64
      OR NEW.provider != (SELECT provider FROM workers WHERE worker_id=NEW.worker_id)
    BEGIN SELECT RAISE(ABORT, 'quota provider identity is invalid'); END
    """,
    """
    CREATE TRIGGER worker_quota_provider_immutable
    BEFORE UPDATE OF provider ON worker_quota_classes
    WHEN OLD.provider IS NOT NEW.provider
    BEGIN SELECT RAISE(ABORT, 'quota provider identity is immutable'); END
    """,
)

_MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "executive_runtime_core", _MIGRATION_1),
    (2, "durable_parent_child_review_contract", _MIGRATION_2),
    (3, "ohf_session_epochs_and_process_generations", _MIGRATION_3),
    (4, "executive_phase1fc_orchestration_contract", _MIGRATION_4),
)


class RuntimeStore:
    """SQLite connection, migration, transaction, and event boundary."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        clock: Callable[[], int | float | datetime] | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        create: bool = True,
        existing_writable: bool = False,
        database_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else _ROOT
        self.path = (
            Path(database_path).resolve()
            if database_path is not None
            else self.root / _DB_RELATIVE_PATH
        )
        self.clock = clock
        self.lease_seconds = int(lease_seconds)
        self.busy_timeout_ms = int(busy_timeout_ms)
        # `create=False` is the read-only accessor a PROJECTION opens the runtime
        # with.  It never creates the directory or the file, never migrates, never
        # chmods, and refuses `transaction()`, so a reader cannot manufacture an
        # Executive OS schema on top of an empty, foreign, or truncated file and
        # then report the result as a quiet company.
        #
        # `existing_writable=True` is the reviewed seam for tools that must write
        # into a positively verified current runtime without creating or migrating
        # one.  It still refuses a missing, empty, foreign, or stale schema.
        self.create = bool(create)
        self.existing_writable = bool(existing_writable)
        if self.create and self.existing_writable:
            raise StateConflict("existing_writable cannot also create a runtime")
        if self.lease_seconds <= 0:
            raise StateConflict("lease_seconds must be positive")
        if self.busy_timeout_ms < 0:
            raise StateConflict("busy_timeout_ms cannot be negative")
        self._schema_ready = False
        self.upgrade_barrier_path = self.path.parent / _SCHEMA_UPGRADE_BARRIER
        if (self.create or self.existing_writable) and os.path.lexists(
            self.upgrade_barrier_path
        ):
            raise PersistenceError(
                "Executive schema upgrade barrier is present; normal writers remain quarantined"
            )
        self._database_was_absent = not os.path.lexists(self.path)
        self._fresh_file_identity: tuple[int, int] | None = None
        self._database_file_identity: tuple[int, int] | None = None
        if not self._database_was_absent:
            try:
                metadata = os.stat(self.path)
            except OSError as exc:
                raise PersistenceError(
                    f"executive runtime database at {self.path} is unavailable: {exc}"
                ) from exc
            self._database_file_identity = (metadata.st_dev, metadata.st_ino)
        if (self.create or self.existing_writable) and not self._database_was_absent:
            if not self.path.is_file():
                raise PersistenceError(
                    f"executive runtime database at {self.path} is not a regular file"
                )
            self._inspect_existing_writable_schema()
        if self.create:
            try:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                self.path.parent.chmod(0o700)
            except OSError as exc:
                raise PersistenceError(
                    f"cannot protect Executive runtime database directory: {exc}"
                ) from exc
            if self._database_was_absent:
                try:
                    descriptor = os.open(
                        self.path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o600,
                    )
                except FileExistsError as exc:
                    raise ExecutiveSchemaUpgradeRequired(
                        "runtime database appeared during fresh-create preflight; "
                        "normal startup refuses it before SQLite or chmod"
                    ) from exc
                except OSError as exc:
                    raise PersistenceError(
                        f"cannot exclusively create Executive runtime database: {exc}"
                    ) from exc
                try:
                    metadata = os.fstat(descriptor)
                    self._fresh_file_identity = (metadata.st_dev, metadata.st_ino)
                    if self._upgrade_barrier_present():
                        # The state directory was just created/protected 0700 and
                        # this O_EXCL descriptor remains open.  Recheck the name
                        # against the held inode immediately before unlink, then
                        # prove the held inode lost its final link.
                        named = os.lstat(self.path)
                        if (
                            (named.st_dev, named.st_ino)
                            != self._fresh_file_identity
                            or named.st_size != 0
                        ):
                            raise PersistenceError(
                                "fresh runtime placeholder changed during barrier race"
                            )
                        self.path.unlink()
                        if os.fstat(descriptor).st_nlink != 0:
                            raise PersistenceError(
                                "owned runtime placeholder remained linked after barrier race"
                            )
                        raise PersistenceError(
                            "Executive schema upgrade barrier appeared during fresh creation"
                        )
                finally:
                    os.close(descriptor)
        elif self.existing_writable and not self.path.is_file():
            raise PersistenceError(
                f"executive runtime database at {self.path} is missing"
            )
        connection = self._open()
        try:
            metadata = os.stat(self.path)
            current_file_identity = (metadata.st_dev, metadata.st_ino)
            expected_file_identity = (
                self._fresh_file_identity
                if self._database_was_absent
                else self._database_file_identity
            )
            if (
                expected_file_identity is not None
                and current_file_identity != expected_file_identity
            ):
                raise PersistenceError(
                    "executive runtime database file identity changed during initialization"
                )
            self._database_file_identity = current_file_identity
        except OSError as exc:
            raise PersistenceError(
                f"executive runtime database at {self.path} is unavailable: {exc}"
            ) from exc
        finally:
            connection.close()

    def _upgrade_barrier_present(self) -> bool:
        """Use lstat semantics so a dangling barrier symlink still quarantines."""

        return os.path.lexists(self.upgrade_barrier_path)

    def _discard_owned_empty_placeholder(self) -> None:
        """Unlink the still-empty O_EXCL inode under the private state directory."""

        if self._fresh_file_identity is None:
            return
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.path, flags)
        try:
            held = os.fstat(descriptor)
            named = os.lstat(self.path)
            if (
                (held.st_dev, held.st_ino) != self._fresh_file_identity
                or (named.st_dev, named.st_ino) != self._fresh_file_identity
                or held.st_size != 0
                or named.st_size != 0
            ):
                raise PersistenceError(
                    "owned fresh placeholder identity changed before cleanup"
                )
            self.path.unlink()
            if os.fstat(descriptor).st_nlink != 0:
                raise PersistenceError("owned fresh placeholder cleanup was incomplete")
        finally:
            os.close(descriptor)

    def _inspect_existing_writable_schema(self) -> None:
        """Mutation-free preflight for every normal writable existing-store open.

        This runs before chmod, WAL selection, directory creation, or a writable
        SQLite connection.  Exact v1-v3 stores are therefore routed only to the
        separately explicit offline upgrade API; ordinary startup cannot append
        migration 4 or create a sidecar as a by-product of discovering staleness.
        """

        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro&immutable=1",
                uri=True,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            schema_digest = _normalized_schema_digest(connection)
        except sqlite3.Error as exc:
            raise PersistenceError(
                f"executive runtime database at {self.path} is not a verified Executive schema: {exc}"
            ) from exc
        finally:
            if connection is not None:
                connection.close()
        versions = [int(row["version"]) for row in rows]
        if not versions or versions != list(range(1, max(versions) + 1)):
            raise PersistenceError(
                f"executive runtime migration vector is not contiguous: {versions}"
            )
        known = {version: (name, statements) for version, name, statements in _MIGRATIONS}
        if any(version not in known for version in versions):
            raise PersistenceError(
                f"executive runtime schema is newer than this release: {versions}"
            )
        for row in rows:
            version = int(row["version"])
            name, statements = known[version]
            if row["name"] != name or row["checksum"] != _migration_checksum(statements):
                raise PersistenceError(
                    f"migration {version} checksum/name does not match code"
                )
        current = versions[-1]
        if current < SCHEMA_VERSION:
            raise ExecutiveSchemaUpgradeRequired(
                f"existing Executive schema v{current} requires explicit offline "
                f"upgrade_v3_to_v4; normal writable open is mutation-free"
            )
        if current != SCHEMA_VERSION:
            raise PersistenceError(
                f"executive runtime schema v{current} is unsupported by v{SCHEMA_VERSION} code"
            )
        if schema_digest != _NORMALIZED_V4_SCHEMA_DIGEST:
            raise PersistenceError(
                "existing Executive schema v4 does not match the exact reviewed DDL"
            )
        if self._upgrade_barrier_present():
            raise PersistenceError(
                "Executive schema upgrade barrier is present; normal writers remain quarantined"
            )

    def now_ms(self) -> int:
        value: int | float | datetime
        value = self.clock() if self.clock else datetime.now(timezone.utc)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return int(value.timestamp() * 1000)
        return int(value)

    def _assert_owned_snapshot_connection(
        self, connection: sqlite3.Connection
    ) -> None:
        """Prove a supplied snapshot's ``main`` is this store's stable file."""

        if connection.in_transaction is not True:
            raise StateConflict(
                "supplied connection must already own an active SQLite transaction"
            )
        try:
            database_rows = connection.execute("PRAGMA database_list").fetchall()
            main_rows = [row for row in database_rows if str(row[1]) == "main"]
            if len(main_rows) != 1 or not str(main_rows[0][2] or ""):
                raise StateConflict(
                    "supplied connection has no exact file-backed SQLite main"
                )
            connection_path = Path(str(main_rows[0][2])).resolve(strict=True)
            owned_path = self.path.resolve(strict=True)
            connection_metadata = os.stat(connection_path)
            owned_metadata = os.stat(owned_path)
        except StateConflict:
            raise
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            raise StateConflict(
                f"supplied connection database identity is unavailable: {exc}"
            ) from exc
        connection_identity = (
            connection_metadata.st_dev,
            connection_metadata.st_ino,
        )
        owned_identity = (owned_metadata.st_dev, owned_metadata.st_ino)
        if (
            self._database_file_identity is None
            or connection_path != owned_path
            or connection_identity != owned_identity
            or owned_identity != self._database_file_identity
        ):
            raise StateConflict(
                "supplied connection is not the stable database owned by this RuntimeStore"
            )

    def _open_readonly(self) -> sqlite3.Connection:
        """Open an EXISTING database read-only: no create, no chmod, no migration.

        SQLite's ``mode=ro`` makes the guarantee structural rather than
        conventional: it refuses to create the file and rejects every write.
        ``journal_mode`` and ``synchronous`` are deliberately NOT set here —
        setting a journal mode is itself a write, and a reader must leave a
        ``delete``-mode or ``wal``-mode database exactly as it found it.

        The schema is then verified rather than assumed.  Without this check an
        empty, truncated, or foreign file reads as a valid database with no rows,
        which a caller would report as "nothing is running".
        """
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self.path.as_uri()}?mode=ro",
                uri=True,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise PersistenceError(
                f"executive runtime database at {self.path} is unavailable: {exc}"
            ) from exc
        if not self._schema_ready:
            try:
                connection.execute(
                    "SELECT version FROM schema_migrations LIMIT 1"
                ).fetchone()
            except sqlite3.Error as exc:
                connection.close()
                message = str(exc)
                if "no such table" in message:
                    detail = "carries no Executive OS schema"
                elif "not a database" in message:
                    detail = "is not an Executive OS database"
                else:
                    detail = "could not be read"
                raise PersistenceError(
                    f"executive runtime database at {self.path} {detail}: {exc}"
                ) from exc
            self._schema_ready = True
        return connection

    def _verify_current_schema(self, connection: sqlite3.Connection) -> None:
        """Refuse anything except the already-applied current Executive schema."""

        try:
            rows = connection.execute(
                "SELECT version, name, checksum FROM schema_migrations"
            ).fetchall()
        except sqlite3.Error as exc:
            message = str(exc)
            if "no such table" in message:
                detail = "carries no Executive OS schema"
            elif "not a database" in message:
                detail = "is not an Executive OS database"
            else:
                detail = "could not be read"
            raise PersistenceError(
                f"executive runtime database at {self.path} {detail}: {exc}"
            ) from exc
        existing = {int(row["version"]): row for row in rows}
        known = {version: (name, statements) for version, name, statements in _MIGRATIONS}
        if set(existing) != set(known):
            raise PersistenceError(
                "executive runtime schema is not current: "
                f"have {sorted(existing)}, need {sorted(known)}"
            )
        for version, (name, statements) in known.items():
            checksum = _migration_checksum(statements)
            row = existing[version]
            if row["name"] != name or row["checksum"] != checksum:
                raise PersistenceError(
                    f"migration {version} checksum/name does not match code"
                )
        if _normalized_schema_digest(connection) != _NORMALIZED_V4_SCHEMA_DIGEST:
            raise PersistenceError(
                "executive runtime schema v4 does not match the exact reviewed DDL"
            )

    def _open_existing_writable(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier is present; normal writers remain quarantined"
                )
            connection = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
            )
            if self._upgrade_barrier_present():
                connection.close()
                connection = None
                if self._database_was_absent:
                    self._discard_owned_empty_placeholder()
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared before SQLite initialization"
                )
            self.path.chmod(0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            if not self._schema_ready:
                self._verify_current_schema(connection)
                self._schema_ready = True
            return connection
        except PersistenceError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise PersistenceError(
                f"executive runtime database at {self.path} is unavailable: {exc}"
            ) from exc

    def _open(self) -> sqlite3.Connection:
        if self.existing_writable:
            return self._open_existing_writable()
        if not self.create:
            return self._open_readonly()
        if self._upgrade_barrier_present():
            raise PersistenceError(
                "Executive schema upgrade barrier is present; normal writers remain quarantined"
            )
        connection: sqlite3.Connection | None = None
        try:
            if self._database_was_absent:
                try:
                    metadata = os.lstat(self.path)
                except OSError as exc:
                    raise PersistenceError(
                        "fresh Executive runtime inode disappeared before open"
                    ) from exc
                if (
                    self._fresh_file_identity is None
                    or (metadata.st_dev, metadata.st_ino) != self._fresh_file_identity
                    or not self.path.is_file()
                ):
                    raise PersistenceError(
                        "fresh Executive runtime inode changed before SQLite open"
                    )
            connection = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_ms / 1000,
                isolation_level=None,
            )
            if self._upgrade_barrier_present():
                connection.close()
                connection = None
                if self._database_was_absent:
                    self._discard_owned_empty_placeholder()
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared before SQLite initialization"
                )
            self.path.chmod(0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            if not self._schema_ready:
                if self._database_was_absent:
                    table = connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                    ).fetchone()
                    if table is not None:
                        raise ExecutiveSchemaUpgradeRequired(
                            "database appeared after fresh-open preflight; explicit schema inspection is required"
                        )
                    self._migrate(connection)
                else:
                    self._verify_current_schema(connection)
                self._schema_ready = True
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared after schema initialization"
                )
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            for sidecar in (
                self.path.with_name(f"{self.path.name}-wal"),
                self.path.with_name(f"{self.path.name}-shm"),
            ):
                if sidecar.exists():
                    sidecar.chmod(0o600)
            return connection
        except PersistenceError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as exc:
            if connection is not None:
                connection.close()
            raise PersistenceError(
                f"executive runtime database is unavailable: {exc}"
            ) from exc

    def _migrate(self, connection: sqlite3.Connection) -> None:
        if not self._database_was_absent:
            raise PersistenceError(
                "generic migration is fresh-database-only under schema v4"
            )
        try:
            connection.execute("BEGIN EXCLUSIVE")
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared after migration lock acquisition"
                )
            connection.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version INTEGER PRIMARY KEY,
                  name TEXT NOT NULL UNIQUE,
                  checksum TEXT NOT NULL,
                  applied_at_ms INTEGER NOT NULL
                )
                """)
            existing = {
                int(row["version"]): row
                for row in connection.execute("SELECT * FROM schema_migrations")
            }
            if existing:
                raise ExecutiveSchemaUpgradeRequired(
                    "generic migration refuses a pre-existing migration vector under schema v4"
                )
            known_versions = {version for version, _, _ in _MIGRATIONS}
            unknown = sorted(set(existing) - known_versions)
            if unknown:
                raise PersistenceError(
                    f"database schema is newer than this runtime: versions {unknown}"
                )
            for version, name, statements in _MIGRATIONS:
                checksum = _migration_checksum(statements)
                row = existing.get(version)
                if row is not None:
                    if row["name"] != name or row["checksum"] != checksum:
                        raise PersistenceError(
                            f"migration {version} checksum/name does not match code"
                        )
                    continue
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version,name,checksum,applied_at_ms) VALUES(?,?,?,?)",
                    (version, name, checksum, self.now_ms()),
                )
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise PersistenceError(
                    f"database foreign-key check failed: {violations!r}"
                )
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared before fresh schema commit"
                )
            connection.commit()
        except PersistenceError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PersistenceError(f"database migration failed: {exc}") from exc

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if not self.create and not self.existing_writable:
            # Fail closed: a store opened for projection has no write path at all,
            # so a lifecycle call cannot reach the database even by mistake.
            raise StateConflict(
                "read-only store: this RuntimeStore was opened with create=False "
                "and refuses every lifecycle mutation"
            )
        if self._upgrade_barrier_present():
            raise PersistenceError(
                "Executive schema upgrade barrier is present; normal writers remain quarantined"
            )
        connection = self._open()
        try:
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared before write transaction"
                )
            connection.execute("BEGIN IMMEDIATE")
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared after write lock acquisition"
                )
            yield connection
            if self._upgrade_barrier_present():
                raise PersistenceError(
                    "Executive schema upgrade barrier appeared before write commit"
                )
            connection.commit()
        except RuntimeProofError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            if connection.in_transaction:
                connection.rollback()
            raise StateConflict(f"database invariant rejected the operation: {exc}") from exc
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PersistenceError(f"database transaction failed: {exc}") from exc
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        connection = self._open()
        try:
            connection.execute("BEGIN")
            yield connection
            connection.commit()
        except RuntimeProofError:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise PersistenceError(f"database read failed: {exc}") from exc
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def append_event(
        self,
        connection: sqlite3.Connection,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        actor: str = "operator",
        job_id: str | None = None,
        attempt_id: str | None = None,
        worker_id: str | None = None,
        quota_class: str | None = None,
        payload: dict[str, Any] | None = None,
        command_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE aggregate_type=? AND aggregate_id=?",
                (aggregate_type, aggregate_id),
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO events(
              aggregate_type,aggregate_id,sequence,event_type,command_id,actor,
              job_id,attempt_id,worker_id,quota_class,payload_json,created_at_ms
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                aggregate_type,
                aggregate_id,
                sequence,
                event_type,
                command_id or uuid4().hex,
                actor,
                job_id,
                attempt_id,
                worker_id,
                quota_class,
                _json_dumps(payload or {}),
                self.now_ms() if timestamp_ms is None else timestamp_ms,
            ),
        )

    def get_event_by_command_id(
        self,
        command_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Event | None:
        """Return the full Event that owns ``command_id``, or None.

        When ``connection`` is supplied, the lookup uses that open transaction
        so a writer can reconcile UNIQUE ``command_id`` replay inside
        ``BEGIN IMMEDIATE``.  The public EventRegistry wrapper uses a read
        snapshot.  This does not expose arbitrary SQL.
        """

        token = str(command_id or "").strip()
        if not token:
            raise StateConflict("command_id is required")

        def _load(conn: sqlite3.Connection) -> Event | None:
            row = conn.execute(
                "SELECT * FROM events WHERE command_id=?",
                (token,),
            ).fetchone()
            return None if row is None else _event_from_row(row)

        if connection is not None:
            return _load(connection)
        with self.read() as conn:
            return _load(conn)

    def find_event_by_command_id(self, command_id: str) -> dict[str, Any] | None:
        """Return the essentials of the event that owns ``command_id``, or None.

        The reconciliation half of the UNIQUE ``command_id`` index: a caller that
        names its command can ask whether that command already committed instead
        of issuing it twice.  Read-only, no new table, no new store.
        """

        with self.read() as connection:
            row = connection.execute(
                """
                SELECT event_type,job_id,payload_json,created_at_ms
                FROM events WHERE command_id=?
                """,
                (str(command_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "event_type": str(row["event_type"]),
            "job_id": row["job_id"],
            "payload": _json_loads(row["payload_json"], fallback={}),
            "created_at_ms": int(row["created_at_ms"]),
        }

    def snapshot(self) -> dict[str, Any]:
        """Compatibility/debug snapshot assembled from authoritative rows."""
        runtime = Runtime.from_store(self)
        return {
            "schema_version": SCHEMA_VERSION,
            "workers": {item.worker_id: item.to_dict() for item in runtime.workers.list_workers()},
            "jobs": {item.job_id: item.to_dict() for item in runtime.jobs.list_jobs()},
            "attempts": {
                item.attempt_id: item.to_dict() for item in runtime.attempts.list_attempts()
            },
        }


def _quota_specifications(
    worker_provider: str,
    worker_capabilities: list[str],
    quota_classes: (
        dict[str, list[str] | tuple[str, ...] | dict[str, Any]]
        | list[str]
        | tuple[str, ...]
        | None
    ),
) -> dict[str, dict[str, Any]]:
    if quota_classes is None:
        declared: dict[str, Any] = {"default": worker_capabilities}
    elif isinstance(quota_classes, dict):
        declared = dict(quota_classes)
    elif isinstance(quota_classes, (list, tuple)):
        declared = {str(name): worker_capabilities for name in quota_classes}
    else:
        raise StateConflict("quota_classes must be a mapping or list of class names")
    result: dict[str, dict[str, Any]] = {}
    for raw_name, raw_value in declared.items():
        name = str(raw_name).strip().lower()
        if not name:
            raise StateConflict("quota class names cannot be empty")
        if name in result:
            raise StateConflict(f"duplicate normalized quota class {name!r}")
        if isinstance(raw_value, dict):
            raw_capabilities = (
                raw_value.get("capabilities")
                if "capabilities" in raw_value
                else raw_value.get("caps")
                if "caps" in raw_value
                else worker_capabilities
            )
            capabilities = _normalise_capabilities(
                raw_capabilities
            )
            raw_metadata = raw_value.get("metadata") or {}
            if not isinstance(raw_metadata, dict):
                raise StateConflict("quota-class metadata must be a mapping")
            metadata = dict(raw_metadata)
            provider = str(raw_value.get("provider") or worker_provider).strip().lower()
            model = (
                str(raw_value["model"]).strip().lower()
                if raw_value.get("model")
                else None
            )
            effort = (
                str(raw_value["effort"]).strip().lower()
                if raw_value.get("effort")
                else None
            )
            cost_class = (
                str(raw_value["cost_class"]).strip().lower()
                if raw_value.get("cost_class")
                else None
            )
        elif isinstance(raw_value, (list, tuple)):
            capabilities = _normalise_capabilities(raw_value)
            metadata = {}
            provider = worker_provider
            model = effort = cost_class = None
        else:
            raise StateConflict(
                "each quota class must declare a capability list or metadata mapping"
            )
        if not provider:
            raise StateConflict("quota-class provider is required")
        result[name] = {
            "capabilities": capabilities,
            "metadata": metadata,
            "provider": provider,
            "model": model,
            "effort": effort,
            "cost_class": cost_class,
        }
    if not result:
        raise StateConflict("at least one quota class is required")
    return result


def _decode_orchestration_job_fields(
    row: sqlite3.Row,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    role = row["orchestration_role"]
    extra_names = (
        "orchestration_provenance_json",
        "orchestration_provenance_digest",
        "plan_attempt_id",
        "plan_digest",
        "plan_step_id",
        "repair_round",
        "supersedes_job_id",
    )
    if role is None:
        if any(row[name] is not None for name in extra_names):
            raise PersistenceError("legacy role-null Job carries orchestration fields")
        return None, None, None
    role = str(role)
    if role not in _ORCHESTRATION_ROLES:
        raise PersistenceError("persisted orchestration role is unknown")
    provenance = _load_canonical_digest_pair(
        row["orchestration_provenance_json"],
        row["orchestration_provenance_digest"],
        name="orchestration provenance",
    )
    expected_keys = {
        "schema_version",
        "creator",
        "source_id",
        "source_digest",
        "command_id",
        "job_id",
        "parent_job_id",
        "root_job_id",
        "role",
    }
    if not isinstance(provenance, dict) or set(provenance) != expected_keys:
        raise PersistenceError("orchestration provenance is not the closed wire")
    if (
        provenance["schema_version"]
        != "mastermind.executive_orchestration_provenance/v1"
        or provenance["job_id"] != row["job_id"]
        or provenance["parent_job_id"] != row["parent_job_id"]
        or provenance["root_job_id"] != row["root_job_id"]
        or provenance["role"] != role
        or re.fullmatch(r"[0-9a-f]{64}", str(provenance["source_digest"])) is None
    ):
        raise PersistenceError("orchestration provenance identity mismatch")
    if role == "aggregation":
        if (
            provenance["creator"] != "ceo_intent"
            or row["parent_job_id"] is not None
            or row["root_job_id"] != row["job_id"]
        ):
            raise PersistenceError("aggregation root lacks strict v2 provenance")
    elif provenance["creator"] != "coo_cycle" or row["parent_job_id"] is None:
        raise PersistenceError("orchestration child lacks COO cycle provenance")
    return role, provenance, str(row["orchestration_provenance_digest"])


def _attempt_from_row(row: sqlite3.Row) -> Attempt:
    effective_grant = _load_canonical_digest_pair(
        row["effective_grant_json"],
        row["effective_grant_digest"],
        name="effective grant",
    )
    placement_snapshot = _load_canonical_digest_pair(
        row["placement_snapshot_json"],
        row["placement_snapshot_digest"],
        name="placement snapshot",
    )
    execution_principal_snapshot = _load_canonical_digest_pair(
        row["execution_principal_snapshot_json"],
        row["execution_principal_snapshot_digest"],
        name="execution principal snapshot",
    )
    return Attempt(
        attempt_id=str(row["attempt_id"]),
        job_id=str(row["job_id"]),
        attempt_number=int(row["attempt_number"]),
        worker_id=str(row["worker_id"]),
        quota_class=str(row["quota_class"]),
        status=AttemptStatus(row["status"]),
        fence_generation=int(row["fence_generation"]),
        lease_owner=str(row["lease_owner"]),
        lease_expires_at=_iso(int(row["lease_expires_at_ms"])),
        heartbeat_at=_iso(int(row["heartbeat_at_ms"])),
        checkpoint_sequence=int(row["checkpoint_sequence"]),
        checkpoint=_json_loads(row["checkpoint_json"], fallback=None),
        result=_json_loads(row["result_json"], fallback=None),
        error=_json_loads(row["error_json"], fallback=None),
        started_at=_iso(int(row["started_at_ms"])),
        finished_at=_iso(row["finished_at_ms"]),
        version=int(row["version"]),
        authority_policy_hash=str(row["authority_policy_hash"]),
        pid=row["pid"],
        pgid=row["pgid"],
        process_start_identity=row["process_start_identity"],
        boot_id=row["boot_id"],
        provider_session_id=row["provider_session_id"],
        stdout_path=row["stdout_path"],
        stderr_path=row["stderr_path"],
        result_path=row["result_path"],
        exit_code=row["exit_code"],
        launch_metadata=dict(
            _json_loads(row["launch_metadata_json"], fallback={})
        ),
        execution_mode=row["execution_mode"],
        requested_execution_profile=_json_loads(
            row["requested_execution_profile_json"], fallback=None
        ),
        requested_execution_profile_digest=row["requested_execution_profile_digest"],
        effective_grant=effective_grant,
        effective_grant_digest=row["effective_grant_digest"],
        placement_snapshot=placement_snapshot,
        placement_snapshot_digest=row["placement_snapshot_digest"],
        execution_principal_snapshot=execution_principal_snapshot,
        execution_principal_snapshot_digest=row[
            "execution_principal_snapshot_digest"
        ],
    )


def _job_from_row(row: sqlite3.Row) -> Job:
    orchestration_role, orchestration_provenance, orchestration_provenance_digest = (
        _decode_orchestration_job_fields(row)
    )
    return Job(
        job_id=str(row["job_id"]),
        objective=str(row["objective"]),
        department=str(row["department"]),
        priority=int(row["priority"]),
        status=JobStatus(row["status"]),
        assigned_worker_id=row["assigned_worker_id"],
        assigned_quota_class=row["assigned_quota_class"],
        authority_level=str(row["authority_level"]),
        branch=row["branch"],
        worktree=row["worktree"],
        checkpoint=_json_loads(row["checkpoint_json"], fallback=None),
        result=_json_loads(row["result_json"], fallback=None),
        created_at=_iso(int(row["created_at_ms"])),
        updated_at=_iso(int(row["updated_at_ms"])),
        constraints=_normalise_constraints(
            _json_loads(row["constraints_json"], fallback={})
        ),
        current_attempt_id=row["current_attempt_id"],
        attempt_count=int(row["attempt_count"]),
        attempt_limit=int(row["attempt_limit"]),
        requested_authorities=list(
            _json_loads(row["requested_authorities_json"], fallback=[])
        ),
        authority_policy_hash=str(row["authority_policy_hash"]),
        allowed_write_paths=list(
            _json_loads(row["allowed_write_paths_json"], fallback=[])
        ),
        validation_commands=list(
            _json_loads(row["validation_commands_json"], fallback=[])
        ),
        parent_job_id=row["parent_job_id"],
        root_job_id=str(row["root_job_id"] or row["job_id"]),
        depth=int(row["depth"]),
        owner_seat=str(row["owner_seat"]),
        escalation_target=str(row["escalation_target"]),
        business_impact=str(row["business_impact"]),
        review_required=bool(int(row["review_required"])),
        reviews_job_id=row["reviews_job_id"],
        orchestration_role=orchestration_role,
        orchestration_provenance=orchestration_provenance,
        orchestration_provenance_digest=orchestration_provenance_digest,
        plan_attempt_id=row["plan_attempt_id"],
        plan_digest=row["plan_digest"],
        plan_step_id=row["plan_step_id"],
        repair_round=row["repair_round"],
        supersedes_job_id=row["supersedes_job_id"],
    )


def _authorize_job_row(row: sqlite3.Row):
    """Re-authorize a durable job against the policy active at claim time."""
    requested = _json_loads(row["requested_authorities_json"], fallback=[])
    allowed_write_paths = _json_loads(row["allowed_write_paths_json"], fallback=[])
    validation_commands = _json_loads(row["validation_commands_json"], fallback=[])
    try:
        return ExecutiveAuthorityPolicy.load().authorize(
            requested,
            worktree=row["worktree"],
            allowed_write_paths=allowed_write_paths,
            validation_commands=validation_commands,
        )
    except (AuthorityDenied, AuthorityPolicyError) as exc:
        raise StateConflict(f"job authority is denied at claim time: {exc}") from exc


def _living_child_rows(
    connection: sqlite3.Connection, parent_job_id: str
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in _TERMINAL_JOB_STATUSES)
    terminal = [status.value for status in _TERMINAL_JOB_STATUSES]
    return connection.execute(
        f"SELECT * FROM jobs WHERE parent_job_id=? AND status NOT IN ({placeholders}) "
        "ORDER BY created_at_ms,job_id",
        (parent_job_id, *terminal),
    ).fetchall()


def _review_void_evidence(
    connection: sqlite3.Connection, *, job_id: str, worker_id: str
) -> dict[str, Any] | None:
    review = connection.execute(
        "SELECT reviews_job_id FROM jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    reviewed_id = review["reviews_job_id"] if review else None
    if not reviewed_id:
        return None
    reviewed = connection.execute(
        "SELECT assigned_worker_id,current_attempt_id FROM jobs WHERE job_id=?",
        (reviewed_id,),
    ).fetchone()
    if reviewed is None or not reviewed["assigned_worker_id"]:
        return None
    if str(reviewed["assigned_worker_id"]) != str(worker_id):
        return {"status": "INDEPENDENT", "reviews_job_id": str(reviewed_id)}
    return {
        "status": "VOID",
        "reason": "review_not_independent",
        "voids": reviewed["current_attempt_id"],
        "reviews_job_id": str(reviewed_id),
    }


def _assert_parent_aggregation_allowed(
    connection: sqlite3.Connection, *, parent_job_id: str
) -> None:
    """Fail closed until the explicit Phase 1F-C cycle is allowed to aggregate."""

    children = connection.execute(
        "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY created_at_ms,job_id",
        (parent_job_id,),
    ).fetchall()
    if not children:
        return
    living = [
        row
        for row in children
        if JobStatus(row["status"]) not in _TERMINAL_JOB_STATUSES
    ]
    if living:
        raise StateConflict(
            "aggregation_blocked: parent has living child job(s) "
            + ", ".join(str(row["job_id"]) for row in living)
        )
    for child in children:
        if not bool(int(child["review_required"])):
            continue
        reviews = connection.execute(
            """
            SELECT r.*,a.worker_id AS review_worker_id
            FROM jobs r
            LEFT JOIN attempts a ON a.attempt_id=r.current_attempt_id
            WHERE r.reviews_job_id=? AND r.status='COMPLETED'
            ORDER BY r.updated_at_ms,r.job_id
            """,
            (child["job_id"],),
        ).fetchall()
        independent_approval = False
        for review in reviews:
            payload = JobPayload.from_value(
                _json_loads(review["result_json"], fallback={})
            )
            if (
                payload.verdict == "approve"
                and review["review_worker_id"]
                and child["assigned_worker_id"]
                and str(review["review_worker_id"]) != str(child["assigned_worker_id"])
            ):
                independent_approval = True
                break
        if not independent_approval:
            raise StateConflict(
                "aggregation_blocked: child "
                f"{child['job_id']} requires an independent completed review "
                "with verdict=approve"
            )


def _event_from_row(row: sqlite3.Row) -> Event:
    return Event(
        event_id=int(row["event_id"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        sequence=int(row["sequence"]),
        event_type=str(row["event_type"]),
        command_id=str(row["command_id"]),
        actor=str(row["actor"]),
        job_id=row["job_id"],
        attempt_id=row["attempt_id"],
        worker_id=row["worker_id"],
        quota_class=row["quota_class"],
        payload=_json_loads(row["payload_json"], fallback={}),
        created_at=_iso(int(row["created_at_ms"])),
    )


def _quota_from_row(row: sqlite3.Row) -> WorkerQuotaClass:
    return WorkerQuotaClass(
        worker_id=str(row["worker_id"]),
        quota_class=str(row["quota_class"]),
        status=WorkerStatus(row["status"]),
        provider=str(row["provider"]),
        model=row["model"],
        effort=row["effort"],
        cost_class=row["cost_class"],
        capabilities=_normalise_capabilities(
            _json_loads(row["capabilities_json"], fallback=[])
        ),
        active_attempt_id=row["held_attempt_id"],
        active_job_id=row["active_job_id"] if "active_job_id" in row.keys() else None,
        fence_generation=int(row["fence_counter"]),
        last_seen_at=_iso(int(row["last_seen_at_ms"])),
        metadata=dict(_json_loads(row["metadata_json"], fallback={})),
    )


class WorkerRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def register_worker(
        self,
        worker_id: str,
        *,
        provider: str,
        account_label: str,
        worker_type: str,
        capabilities: str | list[str] | tuple[str, ...] | None = None,
        quota_classes: (
            dict[str, list[str] | tuple[str, ...] | dict[str, Any]]
            | list[str]
            | tuple[str, ...]
            | None
        ) = None,
        status: WorkerStatus | str = WorkerStatus.AVAILABLE,
        metadata: dict[str, Any] | None = None,
    ) -> Worker:
        worker_id = str(worker_id).strip()
        if not _WORKER_ID_RE.fullmatch(worker_id):
            raise StateConflict(
                "worker_id must be 1-64 characters using letters, digits, '.', '_' or '-'"
            )
        provider = str(provider).strip().lower()
        if not provider:
            raise StateConflict("provider is required")
        worker_status = WorkerStatus(_enum_value(status, WorkerStatus))
        if worker_status == WorkerStatus.BUSY:
            raise StateConflict("a worker cannot register BUSY without an assigned job")
        if metadata is not None and not isinstance(metadata, dict):
            raise StateConflict("worker metadata must be a mapping")
        worker_capabilities = _normalise_capabilities(capabilities)
        specifications = _quota_specifications(
            provider, worker_capabilities, quota_classes
        )
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM workers WHERE worker_id=?", (worker_id,)
            ).fetchone():
                raise StateConflict(f"worker {worker_id!r} is already registered")
            identity_status = (
                worker_status.value
                if worker_status
                in {WorkerStatus.DRAINING, WorkerStatus.OFFLINE, WorkerStatus.ERROR}
                else "ONLINE"
            )
            connection.execute(
                """
                INSERT INTO workers(
                  worker_id,provider,account_label,worker_type,identity_status,
                  metadata_json,last_seen_at_ms,created_at_ms,updated_at_ms
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    worker_id,
                    provider,
                    str(account_label),
                    str(worker_type),
                    identity_status,
                    _json_dumps(metadata or {}),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            for quota_class, spec in specifications.items():
                connection.execute(
                    """
                    INSERT INTO worker_quota_classes(
                      worker_id,quota_class,status,provider,model,effort,cost_class,
                      capabilities_json,metadata_json,last_seen_at_ms,created_at_ms,updated_at_ms
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        worker_id,
                        quota_class,
                        worker_status.value,
                        spec["provider"],
                        spec["model"],
                        spec["effort"],
                        spec["cost_class"],
                        _json_dumps(spec["capabilities"]),
                        _json_dumps(spec["metadata"]),
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
            self.store.append_event(
                connection,
                aggregate_type="worker",
                aggregate_id=worker_id,
                event_type="WORKER_REGISTERED",
                worker_id=worker_id,
                payload={"quota_classes": sorted(specifications)},
                timestamp_ms=timestamp,
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker

    def register_quota_class(
        self,
        worker_id: str,
        quota_class: str,
        *,
        provider: str,
        model: str | None = None,
        effort: str | None = None,
        cost_class: str | None = None,
        capabilities: str | list[str] | tuple[str, ...] | None = None,
        metadata: dict[str, Any] | None = None,
        status: WorkerStatus | str = WorkerStatus.AVAILABLE,
    ) -> WorkerQuotaClass:
        """Add or reconcile one exact capacity class on an existing worker.

        This is an additive host-composition seam, not a mutable policy update.
        An existing class must already be byte-equivalent after normalization;
        drift is refused.  A new class is inserted only while the worker has no
        held Attempt, so an upgrade cannot widen live capacity beneath a
        running provider process.
        """

        worker_token = str(worker_id).strip()
        quota_token = str(quota_class).strip().lower()
        provider_token = str(provider).strip().lower()
        if _WORKER_ID_RE.fullmatch(worker_token) is None:
            raise StateConflict("invalid worker_id for quota registration")
        if _WORKER_ID_RE.fullmatch(quota_token) is None:
            raise StateConflict("invalid quota_class for quota registration")
        if not provider_token:
            raise StateConflict("quota provider is required")
        if metadata is not None and not isinstance(metadata, dict):
            raise StateConflict("quota metadata must be a mapping")
        quota_status = WorkerStatus(_enum_value(status, WorkerStatus))
        if quota_status == WorkerStatus.BUSY:
            raise StateConflict("a quota class cannot register BUSY without an Attempt")
        normalized_capabilities = _normalise_capabilities(capabilities)
        normalized_metadata = dict(metadata or {})
        normalized = {
            "provider": provider_token,
            "model": str(model).strip().lower() if model else None,
            "effort": str(effort).strip().lower() if effort else None,
            "cost_class": str(cost_class).strip().lower() if cost_class else None,
            "capabilities": normalized_capabilities,
            "metadata": normalized_metadata,
        }
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            worker = connection.execute(
                "SELECT * FROM workers WHERE worker_id=?", (worker_token,)
            ).fetchone()
            if worker is None:
                raise StateConflict(f"worker {worker_token!r} does not exist")
            if str(worker["provider"]) != provider_token:
                raise StateConflict("quota provider differs from its worker identity")
            existing = connection.execute(
                "SELECT * FROM worker_quota_classes WHERE worker_id=? AND quota_class=?",
                (worker_token, quota_token),
            ).fetchone()
            if existing is not None:
                actual = {
                    "provider": str(existing["provider"]),
                    "model": existing["model"],
                    "effort": existing["effort"],
                    "cost_class": existing["cost_class"],
                    "capabilities": _normalise_capabilities(
                        _json_loads(existing["capabilities_json"], fallback=[])
                    ),
                    "metadata": dict(
                        _json_loads(existing["metadata_json"], fallback={})
                    ),
                }
                if actual != normalized:
                    raise StateConflict(
                        f"quota class {worker_token}:{quota_token} already exists with different policy"
                    )
                return _quota_from_row(existing)
            held = connection.execute(
                "SELECT 1 FROM worker_quota_classes WHERE worker_id=? AND held_attempt_id IS NOT NULL LIMIT 1",
                (worker_token,),
            ).fetchone()
            if held is not None:
                raise StateConflict(
                    "cannot add a quota class while the worker owns an active Attempt"
                )
            connection.execute(
                """
                INSERT INTO worker_quota_classes(
                  worker_id,quota_class,status,provider,model,effort,cost_class,
                  capabilities_json,metadata_json,last_seen_at_ms,created_at_ms,updated_at_ms
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    worker_token,
                    quota_token,
                    quota_status.value,
                    provider_token,
                    normalized["model"],
                    normalized["effort"],
                    normalized["cost_class"],
                    _json_dumps(normalized_capabilities),
                    _json_dumps(normalized_metadata),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="quota_class",
                aggregate_id=f"{worker_token}:{quota_token}",
                event_type="WORKER_QUOTA_REGISTERED",
                worker_id=worker_token,
                quota_class=quota_token,
                payload={
                    "provider": provider_token,
                    "model": normalized["model"],
                    "effort": normalized["effort"],
                    "cost_class": normalized["cost_class"],
                    "capabilities": normalized_capabilities,
                    "metadata": normalized_metadata,
                },
                timestamp_ms=timestamp,
            )
        created = self.get_quota_class(worker_token, quota_token)
        assert created is not None
        return created

    def get_quota_class(
        self, worker_id: str, quota_class: str
    ) -> WorkerQuotaClass | None:
        with self.store.read() as connection:
            row = connection.execute(
                """
                SELECT q.*, a.job_id AS active_job_id
                FROM worker_quota_classes q
                LEFT JOIN attempts a ON a.attempt_id=q.held_attempt_id
                WHERE q.worker_id=? AND q.quota_class=?
                """,
                (worker_id, str(quota_class).strip().lower()),
            ).fetchone()
            return _quota_from_row(row) if row else None

    def get_worker(self, worker_id: str) -> Worker | None:
        with self.store.read() as connection:
            worker_row = connection.execute(
                "SELECT * FROM workers WHERE worker_id=?", (worker_id,)
            ).fetchone()
            if worker_row is None:
                return None
            quota_rows = connection.execute(
                """
                SELECT q.*, a.job_id AS active_job_id
                FROM worker_quota_classes q
                LEFT JOIN attempts a ON a.attempt_id=q.held_attempt_id
                WHERE q.worker_id=? ORDER BY q.quota_class
                """,
                (worker_id,),
            ).fetchall()
        quotas = [_quota_from_row(row) for row in quota_rows]
        statuses = {quota.status for quota in quotas}
        if worker_row["identity_status"] != "ONLINE":
            aggregate_status = WorkerStatus(worker_row["identity_status"])
        else:
            for candidate in (
                WorkerStatus.AVAILABLE,
                WorkerStatus.BUSY,
                WorkerStatus.RATE_LIMITED,
                WorkerStatus.DRAINING,
                WorkerStatus.OFFLINE,
                WorkerStatus.ERROR,
            ):
                if candidate in statuses:
                    aggregate_status = candidate
                    break
            else:  # pragma: no cover - registration guarantees a class
                aggregate_status = WorkerStatus.ERROR
        active_jobs = sorted(
            {quota.active_job_id for quota in quotas if quota.active_job_id}
        )
        capabilities = sorted(
            {item for quota in quotas for item in quota.capabilities}
        )
        legacy_quotas = {
            quota.quota_class: {
                "status": quota.status.value,
                "capabilities": quota.capabilities,
                "active_job_id": quota.active_job_id,
            }
            for quota in quotas
        }
        return Worker(
            worker_id=str(worker_row["worker_id"]),
            provider=str(worker_row["provider"]),
            account_label=str(worker_row["account_label"]),
            worker_type=str(worker_row["worker_type"]),
            status=aggregate_status,
            capabilities=capabilities,
            active_job_id=active_jobs[0] if active_jobs else None,
            last_seen_at=_iso(int(worker_row["last_seen_at_ms"])),
            metadata=dict(_json_loads(worker_row["metadata_json"], fallback={})),
            quota_classes=legacy_quotas,
        )

    def list_workers(self) -> list[Worker]:
        with self.store.read() as connection:
            worker_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT worker_id FROM workers ORDER BY worker_id"
                )
            ]
        return [worker for item in worker_ids if (worker := self.get_worker(item))]

    def set_worker_status(
        self,
        worker_id: str,
        status: WorkerStatus | str,
        *,
        quota_class: str | None = None,
    ) -> Worker:
        new_status = WorkerStatus(_enum_value(status, WorkerStatus))
        if new_status == WorkerStatus.BUSY:
            raise StateConflict("assign a job instead of setting quota-class status BUSY")
        selected = str(quota_class).strip().lower() if quota_class else None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM worker_quota_classes WHERE worker_id=? ORDER BY quota_class",
                (worker_id,),
            ).fetchall()
            if not rows:
                raise StateConflict(f"worker {worker_id!r} does not exist")
            if selected:
                rows = [row for row in rows if row["quota_class"] == selected]
                if not rows:
                    raise StateConflict(
                        f"worker {worker_id!r} has no quota class {selected!r}"
                    )
            for row in rows:
                held_attempt_id = row["held_attempt_id"]
                if new_status == WorkerStatus.AVAILABLE and held_attempt_id:
                    attempt = connection.execute(
                        "SELECT job_id FROM attempts WHERE attempt_id=?", (held_attempt_id,)
                    ).fetchone()
                    raise StateConflict(
                        f"requeue, complete, fail, or cancel {attempt['job_id']} before making "
                        f"{row['quota_class']} AVAILABLE"
                    )
                if new_status == WorkerStatus.RATE_LIMITED and held_attempt_id:
                    self._rate_limit_held_attempt(
                        connection,
                        attempt_id=str(held_attempt_id),
                        timestamp=timestamp,
                    )
                else:
                    connection.execute(
                        """
                        UPDATE worker_quota_classes
                        SET status=?,last_seen_at_ms=?,updated_at_ms=?,version=version+1
                        WHERE worker_id=? AND quota_class=?
                        """,
                        (
                            new_status.value,
                            timestamp,
                            timestamp,
                            worker_id,
                            row["quota_class"],
                        ),
                    )
                    self.store.append_event(
                        connection,
                        aggregate_type="quota_class",
                        aggregate_id=f"{worker_id}:{row['quota_class']}",
                        event_type="QUOTA_STATUS_CHANGED",
                        worker_id=worker_id,
                        quota_class=str(row["quota_class"]),
                        payload={"status": new_status.value},
                        timestamp_ms=timestamp,
                    )
            if selected is None:
                identity_status = (
                    new_status.value
                    if new_status
                    in {
                        WorkerStatus.DRAINING,
                        WorkerStatus.OFFLINE,
                        WorkerStatus.ERROR,
                    }
                    else "ONLINE"
                )
                connection.execute(
                    """
                    UPDATE workers
                    SET identity_status=?,last_seen_at_ms=?,updated_at_ms=?,version=version+1
                    WHERE worker_id=?
                    """,
                    (identity_status, timestamp, timestamp, worker_id),
                )
            active_job_ids = [
                str(item[0])
                for item in connection.execute(
                    """
                    SELECT DISTINCT a.job_id
                    FROM worker_quota_classes q
                    JOIN attempts a ON a.attempt_id=q.held_attempt_id
                    WHERE q.worker_id=?
                    ORDER BY a.job_id
                    """,
                    (worker_id,),
                )
            ]
            self.store.append_event(
                connection,
                aggregate_type="worker",
                aggregate_id=worker_id,
                event_type="WORKER_STATUS_CHANGED",
                worker_id=worker_id,
                payload={
                    "status": new_status.value,
                    "quota_classes": [str(row["quota_class"]) for row in rows],
                    "active_job_ids": active_job_ids,
                },
                timestamp_ms=timestamp,
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker

    def _rate_limit_held_attempt(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        timestamp: int,
    ) -> None:
        row = connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise StateConflict(f"attempt {attempt_id!r} does not exist")
        if AttemptStatus(row["status"]) not in _WORKER_MUTABLE_ATTEMPT_STATUSES:
            raise StateConflict(f"attempt {attempt_id} cannot rate-limit from {row['status']}")
        if timestamp >= int(row["lease_expires_at_ms"]):
            raise StateConflict(f"attempt {attempt_id} lease has expired; reconcile it first")
        # The compatibility facade reads the protected credential, but the same
        # guarded predicate as an external worker mutation still owns the write.
        AttemptRegistry(self.store)._rate_limit_in_transaction(
            connection,
            row=row,
            fence_generation=int(row["fence_generation"]),
            lease_token=str(row["lease_token"]),
            payload=None,
            timestamp=timestamp,
            actor="operator",
        )

    def release_worker(
        self, worker_id: str, *, quota_class: str | None = None
    ) -> Worker:
        selected = str(quota_class).strip().lower() if quota_class else None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM worker_quota_classes WHERE worker_id=? ORDER BY quota_class",
                (worker_id,),
            ).fetchall()
            if not rows:
                raise StateConflict(f"worker {worker_id!r} does not exist")
            if selected is None:
                if len(rows) != 1:
                    raise StateConflict("quota_class is required for a multi-class worker")
                selected = str(rows[0]["quota_class"])
            row = next((item for item in rows if item["quota_class"] == selected), None)
            if row is None:
                raise StateConflict(
                    f"worker {worker_id!r} has no quota class {selected!r}"
                )
            if row["held_attempt_id"]:
                raise StateConflict(
                    "release assigned capacity through complete_job, fail_job, requeue_job, or cancel"
                )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET status='AVAILABLE',last_seen_at_ms=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id IS NULL
                """,
                (timestamp, timestamp, worker_id, selected),
            )
            self.store.append_event(
                connection,
                aggregate_type="quota_class",
                aggregate_id=f"{worker_id}:{selected}",
                event_type="QUOTA_RELEASED",
                worker_id=worker_id,
                quota_class=selected,
                timestamp_ms=timestamp,
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker

    def assign_job(
        self, worker_id: str, job_id: str, *, quota_class: str | None = None
    ) -> Worker:
        runtime = Runtime.from_store(self.store)
        lease = runtime.attempts.claim_job(
            job_id, worker_id=worker_id, quota_class=quota_class
        )
        if lease is None:  # explicit worker selection reports conflict rather than no-op
            raise StateConflict(
                f"worker {worker_id} is unavailable or does not match job constraints"
            )
        worker = self.get_worker(worker_id)
        assert worker is not None
        return worker


def _effective_grant_for_orchestration_job(
    row: sqlite3.Row, authority: Any
) -> tuple[dict[str, Any], str]:
    role = str(row["orchestration_role"] or "")
    if role not in _ORCHESTRATION_ROLES:
        raise StateConflict("orchestration job has no closed role")
    requested = list(authority.requested)
    writes = list(authority.allowed_write_paths)
    validations = [list(item) for item in authority.validation_commands]
    if role in {"plan", "aggregation"}:
        if "READ" not in requested:
            raise StateConflict(
                "plan/aggregation effective grant cannot add READ absent from the Job grant"
            )
        requested = ["READ"]
        writes = []
        validations = []
    elif role == "review":
        if "READ" not in requested or any(
            item not in {"READ", "RUN_TESTS"} for item in requested
        ):
            raise StateConflict(
                "review effective grant requires READ plus optional RUN_TESTS"
            )
        writes = []
    value = {
        "schema_version": "mastermind.executive_effective_grant/v1",
        "authorities": requested,
        "write_paths": writes,
        "validation_argv": validations,
        "policy_sha": authority.policy_sha256,
        "job_id": str(row["job_id"]),
        "role": role,
    }
    return value, orchestration_digest(value)


def _tx9_evidence_from_joined_row(row: sqlite3.Row) -> tuple[dict[str, Any], str]:
    """Validate and canonicalize one frozen TX-9 invalidation Event."""

    text_fields = (
        "aggregate_type",
        "aggregate_id",
        "command_id",
        "actor",
        "job_id",
        "attempt_id",
        "worker_id",
        "quota_class",
        "attempt_worker_id",
        "attempt_quota_class",
        "attempt_job_id",
    )
    if (
        row["event_id_type"] != "integer"
        or type(row["event_id"]) is not int
        or row["event_id"] <= 0
        or row["sequence_type"] != "integer"
        or type(row["sequence"]) is not int
        or row["sequence"] <= 0
        or row["created_at_ms_type"] != "integer"
        or type(row["created_at_ms"]) is not int
        or row["created_at_ms"] < 0
        or any(not isinstance(row[name], str) or not row[name] for name in text_fields)
        or row["attempt_worker_id"] != row["worker_id"]
        or row["attempt_quota_class"] != row["quota_class"]
        or row["attempt_job_id"] != row["job_id"]
        or row["aggregate_type"] != "attempt"
        or row["aggregate_id"] != row["attempt_id"]
        or row["actor"] != "restore"
        or row["command_id"] != f"ohf-restore:{row['attempt_id']}"
    ):
        raise StateConflict("OHF_RESTORE_INVALIDATED identity is malformed")
    payload = _strict_canonical_json_loads(
        str(row["payload_json"]), name="OHF_RESTORE_INVALIDATED payload"
    )
    if payload != {"transaction_group": "TX-9"}:
        raise StateConflict("OHF_RESTORE_INVALIDATED payload is malformed")
    evidence = {
        "schema_version": "mastermind.executive_tx9_requeue_evidence/v1",
        "event_id": row["event_id"],
        "aggregate_type": row["aggregate_type"],
        "aggregate_id": row["aggregate_id"],
        "sequence": row["sequence"],
        "event_type": "OHF_RESTORE_INVALIDATED",
        "command_id": row["command_id"],
        "actor": row["actor"],
        "job_id": row["job_id"],
        "attempt_id": row["attempt_id"],
        "worker_id": row["worker_id"],
        "quota_class": row["quota_class"],
        "payload": payload,
        "created_at_ms": row["created_at_ms"],
    }
    return evidence, orchestration_digest(evidence)


def _tx9_event_rows(
    connection: sqlite3.Connection, *, attempt_id: str | None = None
) -> list[sqlite3.Row]:
    predicate = "AND e.attempt_id=?" if attempt_id is not None else ""
    parameters: tuple[Any, ...] = (attempt_id,) if attempt_id is not None else ()
    return connection.execute(
        f"""
        SELECT e.event_id,typeof(e.event_id) AS event_id_type,
               e.aggregate_type,e.aggregate_id,e.sequence,
               typeof(e.sequence) AS sequence_type,e.event_type,e.command_id,
               e.actor,e.job_id,e.attempt_id,e.worker_id,e.quota_class,
               e.payload_json,e.created_at_ms,
               typeof(e.created_at_ms) AS created_at_ms_type,
               a.worker_id AS attempt_worker_id,
               a.quota_class AS attempt_quota_class,a.job_id AS attempt_job_id
        FROM events e LEFT JOIN attempts a ON a.attempt_id=e.attempt_id
        WHERE e.event_type='OHF_RESTORE_INVALIDATED' {predicate}
        ORDER BY e.event_id
        """,
        parameters,
    ).fetchall()


def _tx9_requeue_material(
    connection: sqlite3.Connection,
    job_row: sqlite3.Row,
) -> tuple[sqlite3.Row, dict[str, Any], str, dict[str, Any], str]:
    """Derive the exact detached requeue evidence and quota snapshot."""

    typed_job = connection.execute(
        """
        SELECT *,typeof(attempt_count) AS attempt_count_type,
                 typeof(attempt_limit) AS attempt_limit_type
        FROM jobs WHERE job_id=?
        """,
        (job_row["job_id"],),
    ).fetchone()
    if typed_job is None:
        raise StateConflict("TX-9 requeue Job disappeared")
    job_row = typed_job
    attempt_id = job_row["current_attempt_id"]
    if (
        job_row["orchestration_role"] is None
        or job_row["status"] != JobStatus.LOST.value
        or not isinstance(attempt_id, str)
        or not attempt_id
        or job_row["attempt_count_type"] != "integer"
        or type(job_row["attempt_count"]) is not int
        or job_row["attempt_count"] <= 0
        or job_row["attempt_limit_type"] != "integer"
        or type(job_row["attempt_limit"]) is not int
        or job_row["attempt_limit"] <= 0
        or job_row["attempt_count"] >= job_row["attempt_limit"]
    ):
        raise StateConflict("Job is not eligible for TX-9-detached requeue")
    attempt = connection.execute(
        "SELECT *,typeof(attempt_number) AS attempt_number_type FROM attempts WHERE attempt_id=?",
        (attempt_id,),
    ).fetchone()
    if (
        attempt is None
        or attempt["job_id"] != job_row["job_id"]
        or attempt["status"] != AttemptStatus.LOST.value
        or attempt["execution_mode"] != AttemptExecutionMode.OPERATOR_HARNESS.value
        or attempt["lease_token"] is not None
        or attempt["attempt_number_type"] != "integer"
        or type(attempt["attempt_number"]) is not int
        or attempt["attempt_number"] != job_row["attempt_count"]
        or job_row["assigned_worker_id"] != attempt["worker_id"]
        or job_row["assigned_quota_class"] != attempt["quota_class"]
    ):
        raise StateConflict("current orchestration Attempt is not exact TX-9 LOST state")
    tx9_rows = _tx9_event_rows(connection, attempt_id=attempt_id)
    if len(tx9_rows) != 1:
        raise StateConflict("TX-9-detached requeue requires exactly one invalidation Event")
    evidence, evidence_digest = _tx9_evidence_from_joined_row(tx9_rows[0])
    bad_epoch = connection.execute(
        """
        SELECT 1 FROM harness_session_epochs
        WHERE attempt_id=? AND state!='ABANDONED' LIMIT 1
        """,
        (attempt_id,),
    ).fetchone()
    live_writer = connection.execute(
        """
        SELECT 1 FROM process_generations
        WHERE session_epoch_id IN (
          SELECT session_epoch_id FROM harness_session_epochs WHERE attempt_id=?
        ) AND executive_writer_held=1 LIMIT 1
        """,
        (attempt_id,),
    ).fetchone()
    if bad_epoch is not None or live_writer is not None:
        raise StateConflict("TX-9-detached Attempt retains current epoch or writer")
    quota = connection.execute(
        """
        SELECT *,typeof(fence_counter) AS fence_counter_type,
               typeof(version) AS version_type,
               typeof(updated_at_ms) AS updated_at_ms_type
        FROM worker_quota_classes WHERE worker_id=? AND quota_class=?
        """,
        (attempt["worker_id"], attempt["quota_class"]),
    ).fetchone()
    if (
        quota is None
        or quota["status"] != WorkerStatus.ERROR.value
        or quota["held_attempt_id"] is not None
        or quota["fence_counter_type"] != "integer"
        or type(quota["fence_counter"]) is not int
        or quota["fence_counter"] < 0
        or quota["version_type"] != "integer"
        or type(quota["version"]) is not int
        or quota["version"] <= 0
        or quota["updated_at_ms_type"] != "integer"
        or type(quota["updated_at_ms"]) is not int
        or quota["updated_at_ms"] < 0
        or quota["updated_at_ms"] != evidence["created_at_ms"]
    ):
        raise StateConflict("TX-9 invalidated quota does not match the frozen state")
    later = connection.execute(
        """
        SELECT 1 FROM events
        WHERE event_id>? AND worker_id=? AND quota_class=? LIMIT 1
        """,
        (evidence["event_id"], attempt["worker_id"], attempt["quota_class"]),
    ).fetchone()
    if later is not None:
        raise StateConflict("later Event for the exact invalidated worker/quota blocks requeue")
    snapshot = {
        "schema_version": "mastermind.tx9_invalidated_quota_snapshot/v1",
        "worker_id": str(attempt["worker_id"]),
        "quota_class": str(attempt["quota_class"]),
        "status": WorkerStatus.ERROR.value,
        "held_attempt_id": None,
        "fence_counter": quota["fence_counter"],
        "version": quota["version"],
        "updated_at_ms": quota["updated_at_ms"],
    }
    return attempt, evidence, evidence_digest, snapshot, orchestration_digest(snapshot)


def _retry_safety_material(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    expected_attempt_id: str,
) -> _RetrySafetyMaterial:
    """Project every retry-classifier input from one caller-owned snapshot."""

    job_row = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    attempt_row = connection.execute(
        "SELECT * FROM attempts WHERE attempt_id=?", (expected_attempt_id,)
    ).fetchone()
    current_attempt_id = job_row["current_attempt_id"] if job_row is not None else None
    terminal_status = str(job_row["status"]) if job_row is not None else "UNKNOWN"
    attempt_job_id = str(attempt_row["job_id"]) if attempt_row is not None else ""
    retry_lineage_available = bool(
        job_row is not None
        and attempt_row is not None
        and current_attempt_id == expected_attempt_id
        and attempt_job_id == job_id
        and type(job_row["attempt_count"]) is int
        and type(job_row["attempt_limit"]) is int
        and job_row["attempt_count"] < job_row["attempt_limit"]
    )
    event_types = {
        str(row["event_type"])
        for row in connection.execute(
            "SELECT event_type FROM events WHERE attempt_id=?", (expected_attempt_id,)
        )
    }
    candidate_present = "OHF_CANDIDATE_RESULT_RECORDED" in event_types
    seal_present = "ORCHESTRATION_ROLE_RESULT_SEALED" in event_types
    operation_effect_unknown_present = (
        "OPERATOR_OPERATION_EFFECT_UNKNOWN" in event_types
    )
    result_present = bool(
        (job_row is not None and job_row["result_json"] is not None)
        or (attempt_row is not None and attempt_row["result_json"] is not None)
    )
    writer_or_provider_generation_live = (
        connection.execute(
            """
            SELECT 1
            FROM harness_session_epochs h
            LEFT JOIN process_generations g ON g.session_epoch_id=h.session_epoch_id
            WHERE h.attempt_id=? AND (
              h.state='CURRENT'
              OR coalesce(g.executive_writer_held,0)=1
              OR (
                h.state!='ABANDONED'
                AND coalesce(g.provider_writer_state,'UNKNOWN')!='RELEASED'
              )
            )
            LIMIT 1
            """,
            (expected_attempt_id,),
        ).fetchone()
        is not None
    )
    effective_grant_non_modifying = False
    if attempt_row is not None and attempt_row["effective_grant_json"] is not None:
        try:
            grant = _strict_canonical_json_loads(
                str(attempt_row["effective_grant_json"]),
                name="retry-safety effective grant",
            )
        except StateConflict:
            grant = None
        if isinstance(grant, dict):
            authorities = grant.get("authorities")
            effective_grant_non_modifying = bool(
                isinstance(authorities, list)
                and authorities
                and all(item in {"READ", "RUN_TESTS"} for item in authorities)
                and grant.get("write_paths") == []
            )
    tx9_material = None
    if job_row is not None and terminal_status == JobStatus.LOST.value:
        try:
            tx9_material = _tx9_requeue_material(connection, job_row)
        except StateConflict:
            pass
    tx9_evidence_digest = tx9_material[2] if tx9_material is not None else None
    if tx9_evidence_digest is not None:
        retry_safety = RetrySafety.SAFE_PRE_EFFECT_INFRASTRUCTURE
        requeue_kind = "TX9_DETACHED"
    elif terminal_status == JobStatus.FAILED.value:
        retry_safety = RetrySafety.GENERIC_FAILED
        requeue_kind = "ORDINARY"
    elif terminal_status == JobStatus.LOST.value:
        retry_safety = RetrySafety.EFFECT_UNKNOWN
        requeue_kind = None
    else:
        retry_safety = RetrySafety.UNKNOWN
        requeue_kind = None
    provenance_digest = tx9_evidence_digest
    if provenance_digest is None and job_row is not None:
        raw = job_row["orchestration_provenance_digest"]
        provenance_digest = str(raw) if raw is not None else None
    evidence = RetrySafetyEvidence(
        retry_safety=retry_safety,
        terminal_status=terminal_status,
        job_id=job_id,
        attempt_id=expected_attempt_id,
        attempt_job_id=attempt_job_id,
        current_attempt_id=(
            str(current_attempt_id) if current_attempt_id is not None else None
        ),
        provenance_digest=provenance_digest,
        retry_lineage_available=retry_lineage_available,
        effect_unknown=(
            operation_effect_unknown_present
            or (
                tx9_evidence_digest is None
                and terminal_status
                in {JobStatus.RATE_LIMITED.value, JobStatus.LOST.value}
            )
        ),
        writer_or_provider_generation_live=writer_or_provider_generation_live,
        candidate_present=candidate_present,
        result_present=result_present,
        seal_present=seal_present,
        effective_grant_non_modifying=effective_grant_non_modifying,
    )
    return _RetrySafetyMaterial(
        projection=RetrySafetyProjection(
            attempt_id=expected_attempt_id,
            requeue_kind=requeue_kind,
            tx9_evidence_digest=tx9_evidence_digest,
            retry_evidence_digest=evidence.evidence_digest,
            evidence=evidence,
        ),
        tx9_material=tx9_material,
    )


def _validated_retry_safety_receipt(
    value: Any, *, require_safe: bool
) -> tuple[dict[str, Any], RetrySafetyEvidence, RetrySafetyDecision]:
    """Parse one closed retry receipt and recompute all authority-bearing fields."""

    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "decision",
        "evidence",
        "evidence_digest",
    }:
        raise StateConflict("retry-safety receipt is not the closed wire")
    if value.get("schema_version") != "mastermind.executive_retry_safety_receipt/v1":
        raise StateConflict("retry-safety receipt schema is invalid")
    raw = value.get("evidence")
    expected_evidence_keys = {field.name for field in dataclasses.fields(RetrySafetyEvidence)}
    if not isinstance(raw, dict) or set(raw) != expected_evidence_keys:
        raise StateConflict("retry-safety evidence is not the closed wire")
    bool_fields = {
        "retry_lineage_available",
        "effect_unknown",
        "writer_or_provider_generation_live",
        "candidate_present",
        "result_present",
        "seal_present",
        "effective_grant_non_modifying",
    }
    string_fields = {"terminal_status", "job_id", "attempt_id", "attempt_job_id"}
    if any(type(raw.get(name)) is not bool for name in bool_fields) or any(
        not isinstance(raw.get(name), str) or not raw.get(name)
        for name in string_fields
    ):
        raise StateConflict("retry-safety evidence field type is invalid")
    if raw.get("current_attempt_id") is not None and (
        not isinstance(raw.get("current_attempt_id"), str)
        or not raw.get("current_attempt_id")
    ):
        raise StateConflict("retry-safety current Attempt identity is invalid")
    if raw.get("provenance_digest") is not None and (
        not isinstance(raw.get("provenance_digest"), str)
        or re.fullmatch(r"[0-9a-f]{64}", str(raw.get("provenance_digest"))) is None
    ):
        raise StateConflict("retry-safety provenance digest is invalid")
    try:
        evidence = RetrySafetyEvidence(
            retry_safety=RetrySafety(str(raw["retry_safety"])),
            terminal_status=str(raw["terminal_status"]),
            job_id=str(raw["job_id"]),
            attempt_id=str(raw["attempt_id"]),
            attempt_job_id=str(raw["attempt_job_id"]),
            current_attempt_id=(
                str(raw["current_attempt_id"])
                if raw["current_attempt_id"] is not None
                else None
            ),
            provenance_digest=(
                str(raw["provenance_digest"])
                if raw["provenance_digest"] is not None
                else None
            ),
            retry_lineage_available=raw["retry_lineage_available"],
            effect_unknown=raw["effect_unknown"],
            writer_or_provider_generation_live=raw[
                "writer_or_provider_generation_live"
            ],
            candidate_present=raw["candidate_present"],
            result_present=raw["result_present"],
            seal_present=raw["seal_present"],
            effective_grant_non_modifying=raw["effective_grant_non_modifying"],
        )
        decision = RetrySafetyDecision(str(value["decision"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise StateConflict("retry-safety receipt enum is invalid") from exc
    if evidence.to_dict() != raw:
        raise StateConflict("retry-safety evidence canonical form drifted")
    if (
        not isinstance(value.get("evidence_digest"), str)
        or value["evidence_digest"] != evidence.evidence_digest
        or decision is not classify_retry_safety(evidence)
        or (require_safe and decision is not RetrySafetyDecision.SAFE_REQUEUE)
    ):
        raise StateConflict("retry-safety receipt classification/digest drifted")
    return dict(value), evidence, decision


def _validated_retry_safety_block_evidence(
    connection: sqlite3.Connection,
    evidence_value: dict[str, Any],
    *,
    selected_job_id: str,
    attempt_id: str | None,
) -> None:
    """Bind an optional retry-backed block receipt to the live Runtime snapshot."""

    if "retry_safety" not in evidence_value:
        return
    if set(evidence_value) != {"retry_safety"}:
        raise StateConflict("COO retry block evidence is not the closed wire")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise StateConflict("COO retry block requires one exact current Attempt")
    _, retry_evidence, retry_decision = _validated_retry_safety_receipt(
        evidence_value["retry_safety"], require_safe=False
    )
    if (
        retry_decision is RetrySafetyDecision.SAFE_REQUEUE
        or retry_evidence.job_id != selected_job_id
        or retry_evidence.attempt_id != attempt_id
        or retry_evidence.attempt_job_id != selected_job_id
        or retry_evidence.current_attempt_id != attempt_id
    ):
        raise StateConflict("COO retry block receipt binding drifted")
    observed = _retry_safety_material(
        connection,
        job_id=selected_job_id,
        expected_attempt_id=attempt_id,
    ).projection
    if (
        retry_evidence.to_dict() != observed.evidence.to_dict()
        or retry_evidence.evidence_digest != observed.retry_evidence_digest
    ):
        raise StateConflict("COO retry block receipt no longer matches Runtime evidence")


def _validated_coo_cycle_block_event(
    connection: sqlite3.Connection,
    event_row: sqlite3.Row,
    *,
    expected_root_id: str,
) -> dict[str, Any]:
    """Validate one complete durable COO block Event before replay."""

    if (
        event_row["event_type"] != "COO_CYCLE_BLOCKED"
        or event_row["aggregate_type"] != "job"
        or event_row["aggregate_id"] != expected_root_id
        or event_row["job_id"] != expected_root_id
        or event_row["actor"] != "coo"
        or not isinstance(event_row["command_id"], str)
        or _COMMAND_ID_RE.fullmatch(event_row["command_id"]) is None
        or type(event_row["event_id"]) is not int
        or event_row["event_id"] <= 0
    ):
        raise StateConflict("COO_CYCLE_BLOCKED Event identity is malformed")
    payload = _strict_canonical_json_loads(
        str(event_row["payload_json"]), name="COO_CYCLE_BLOCKED payload"
    )
    expected_keys = {
        "schema_version",
        "root_job_id",
        "selected_job_id",
        "reason",
        "policy_sha",
        "plan_digest",
        "handoff_digest",
        "evidence",
        "evidence_digest",
        "command_id",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise StateConflict("COO_CYCLE_BLOCKED payload is not the closed wire")
    selected_id = payload.get("selected_job_id")
    reason = payload.get("reason")
    evidence_value = payload.get("evidence")
    if (
        payload.get("schema_version") != "mastermind.coo_cycle_block/v1"
        or payload.get("root_job_id") != expected_root_id
        or not isinstance(selected_id, str)
        or not selected_id
        or reason not in COO_CYCLE_BLOCK_REASONS
        or payload.get("policy_sha") != EXPECTED_POLICY_SHA256
        or not isinstance(evidence_value, dict)
        or not isinstance(payload.get("evidence_digest"), str)
        or payload["evidence_digest"] != orchestration_digest(evidence_value)
        or payload.get("command_id") != event_row["command_id"]
        or event_row["command_id"]
        != f"coo-cycle:{expected_root_id}:block:{reason}:{selected_id}"
    ):
        raise StateConflict("COO_CYCLE_BLOCKED payload identity/digest drifted")
    root = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (expected_root_id,)
    ).fetchone()
    selected = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (selected_id,)
    ).fetchone()
    if (
        root is None
        or selected is None
        or root["root_job_id"] != expected_root_id
        or selected["root_job_id"] != expected_root_id
        or (reason != "invalid_root" and root["orchestration_role"] != "aggregation")
        or event_row["attempt_id"] != selected["current_attempt_id"]
    ):
        raise StateConflict("COO_CYCLE_BLOCKED Job/Attempt binding drifted")
    plan_event = connection.execute(
        "SELECT payload_json FROM events WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?",
        (expected_root_id,),
    ).fetchone()
    handoff_event = connection.execute(
        """
        SELECT payload_json FROM events
        WHERE event_type='COO_AGGREGATION_HANDOFF_READY' AND job_id=?
        """,
        (expected_root_id,),
    ).fetchone()
    plan_digest = (
        _strict_canonical_json_loads(
            str(plan_event["payload_json"]), name="COO_PLAN_ADMITTED payload"
        ).get("plan_digest")
        if plan_event is not None
        else None
    )
    handoff_digest = (
        _strict_canonical_json_loads(
            str(handoff_event["payload_json"]),
            name="COO_AGGREGATION_HANDOFF_READY payload",
        ).get("handoff_digest")
        if handoff_event is not None
        else None
    )
    if (
        payload.get("plan_digest") != plan_digest
        or payload.get("handoff_digest") != handoff_digest
    ):
        raise StateConflict("COO_CYCLE_BLOCKED plan/handoff digest drifted")
    _validated_retry_safety_block_evidence(
        connection,
        evidence_value,
        selected_job_id=selected_id,
        attempt_id=event_row["attempt_id"],
    )
    return dict(payload)


def _validate_tx9_requeue_event(
    connection: sqlite3.Connection,
    event_row: sqlite3.Row,
    *,
    expected_job_id: str,
    require_current_quota: bool,
) -> dict[str, Any]:
    """Validate the historical detached-requeue receipt and optional live snapshot."""

    if (
        event_row["event_type"] != "JOB_REQUEUED"
        or event_row["aggregate_type"] != "job"
        or event_row["aggregate_id"] != expected_job_id
        or event_row["job_id"] != expected_job_id
        or not isinstance(event_row["attempt_id"], str)
        or not event_row["attempt_id"]
    ):
        raise StateConflict("TX-9 requeue command target is invalid")
    payload = _strict_canonical_json_loads(
        str(event_row["payload_json"]), name="TX-9 JOB_REQUEUED payload"
    )
    expected_keys = {
        "previous_status",
        "requeue_kind",
        "invalidated_attempt_id",
        "invalidated_worker_id",
        "invalidated_quota_class",
        "tx9_evidence_digest",
        "invalidated_quota_snapshot",
        "invalidated_quota_snapshot_digest",
    }
    if isinstance(payload, dict) and "retry_safety" in payload:
        expected_keys.add("retry_safety")
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise StateConflict("TX-9 JOB_REQUEUED payload is not the closed wire")
    if "retry_safety" in payload:
        _, retry_evidence, _ = _validated_retry_safety_receipt(
            payload["retry_safety"], require_safe=True
        )
        if (
            retry_evidence.retry_safety
            is not RetrySafety.SAFE_PRE_EFFECT_INFRASTRUCTURE
            or retry_evidence.terminal_status != JobStatus.LOST.value
            or retry_evidence.job_id != expected_job_id
            or retry_evidence.attempt_id != event_row["attempt_id"]
            or retry_evidence.attempt_job_id != expected_job_id
            or retry_evidence.current_attempt_id != event_row["attempt_id"]
            or retry_evidence.provenance_digest
            != payload.get("tx9_evidence_digest")
        ):
            raise StateConflict("TX-9 retry-safety receipt binding drifted")
    snapshot = payload.get("invalidated_quota_snapshot")
    snapshot_keys = {
        "schema_version",
        "worker_id",
        "quota_class",
        "status",
        "held_attempt_id",
        "fence_counter",
        "version",
        "updated_at_ms",
    }
    if (
        payload.get("previous_status") != JobStatus.LOST.value
        or payload.get("requeue_kind") != "TX9_DETACHED"
        or payload.get("invalidated_attempt_id") != event_row["attempt_id"]
        or not isinstance(snapshot, dict)
        or set(snapshot) != snapshot_keys
        or snapshot.get("schema_version")
        != "mastermind.tx9_invalidated_quota_snapshot/v1"
        or snapshot.get("worker_id") != payload.get("invalidated_worker_id")
        or snapshot.get("quota_class") != payload.get("invalidated_quota_class")
        or snapshot.get("status") != WorkerStatus.ERROR.value
        or snapshot.get("held_attempt_id") is not None
        or type(snapshot.get("fence_counter")) is not int
        or snapshot["fence_counter"] < 0
        or type(snapshot.get("version")) is not int
        or snapshot["version"] <= 0
        or type(snapshot.get("updated_at_ms")) is not int
        or snapshot["updated_at_ms"] < 0
        or re.fullmatch(
            r"[0-9a-f]{64}", str(payload.get("tx9_evidence_digest"))
        )
        is None
        or re.fullmatch(
            r"[0-9a-f]{64}", str(payload.get("invalidated_quota_snapshot_digest"))
        )
        is None
        or orchestration_digest(snapshot)
        != payload["invalidated_quota_snapshot_digest"]
    ):
        raise StateConflict("TX-9 JOB_REQUEUED evidence/snapshot is malformed")
    tx9_rows = _tx9_event_rows(
        connection, attempt_id=str(payload["invalidated_attempt_id"])
    )
    if len(tx9_rows) != 1:
        raise StateConflict("TX-9 JOB_REQUEUED no longer resolves one invalidation Event")
    evidence, evidence_digest = _tx9_evidence_from_joined_row(tx9_rows[0])
    if (
        evidence_digest != payload["tx9_evidence_digest"]
        or evidence["job_id"] != expected_job_id
        or evidence["worker_id"] != payload["invalidated_worker_id"]
        or evidence["quota_class"] != payload["invalidated_quota_class"]
        or evidence["created_at_ms"] != snapshot["updated_at_ms"]
    ):
        raise StateConflict("TX-9 JOB_REQUEUED evidence digest/identity drifted")
    if require_current_quota:
        quota = connection.execute(
            """
            SELECT *,typeof(fence_counter) AS fence_counter_type,
                     typeof(version) AS version_type,
                     typeof(updated_at_ms) AS updated_at_ms_type
            FROM worker_quota_classes WHERE worker_id=? AND quota_class=?
            """,
            (snapshot["worker_id"], snapshot["quota_class"]),
        ).fetchone()
        if (
            quota is None
            or quota["fence_counter_type"] != "integer"
            or quota["version_type"] != "integer"
            or quota["updated_at_ms_type"] != "integer"
            or {
                "schema_version": "mastermind.tx9_invalidated_quota_snapshot/v1",
                "worker_id": quota["worker_id"],
                "quota_class": quota["quota_class"],
                "status": quota["status"],
                "held_attempt_id": quota["held_attempt_id"],
                "fence_counter": quota["fence_counter"],
                "version": quota["version"],
                "updated_at_ms": quota["updated_at_ms"],
            }
            != snapshot
        ):
            raise StateConflict("TX-9 invalidated quota snapshot drifted before claim")
    return payload


def _requeue_outcome_from_event(
    connection: sqlite3.Connection,
    event_row: sqlite3.Row,
    *,
    expected_job_id: str,
) -> JobRequeueOutcome:
    if (
        event_row["event_type"] != "JOB_REQUEUED"
        or event_row["aggregate_type"] != "job"
        or event_row["aggregate_id"] != expected_job_id
        or event_row["job_id"] != expected_job_id
        or not isinstance(event_row["attempt_id"], str)
        or not event_row["attempt_id"]
        or event_row["actor"] != "operator"
        or not isinstance(event_row["command_id"], str)
        or _COMMAND_ID_RE.fullmatch(event_row["command_id"]) is None
        or type(event_row["event_id"]) is not int
        or event_row["event_id"] <= 0
    ):
        raise StateConflict("command-aware JOB_REQUEUED Event target is malformed")
    root_row = connection.execute(
        "SELECT root_job_id FROM jobs WHERE job_id=?", (expected_job_id,)
    ).fetchone()
    if root_row is None or event_row["command_id"] != (
        f"coo-cycle:{root_row['root_job_id']}:requeue:"
        f"{expected_job_id}:{event_row['attempt_id']}"
    ):
        raise StateConflict("command-aware JOB_REQUEUED command identity is invalid")
    bound_attempt = connection.execute(
        "SELECT worker_id,quota_class,job_id FROM attempts WHERE attempt_id=?",
        (event_row["attempt_id"],),
    ).fetchone()
    if (
        bound_attempt is None
        or bound_attempt["job_id"] != expected_job_id
        or event_row["worker_id"] != bound_attempt["worker_id"]
        or event_row["quota_class"] != bound_attempt["quota_class"]
    ):
        raise StateConflict("command-aware JOB_REQUEUED worker/quota binding is malformed")
    payload = _strict_canonical_json_loads(
        str(event_row["payload_json"]), name="command-aware JOB_REQUEUED payload"
    )
    if not isinstance(payload, dict):
        raise StateConflict("command-aware JOB_REQUEUED payload is malformed")
    kind = payload.get("requeue_kind")
    if kind == "TX9_DETACHED":
        payload = _validate_tx9_requeue_event(
            connection,
            event_row,
            expected_job_id=expected_job_id,
            require_current_quota=False,
        )
    elif (
        kind != "ORDINARY"
        or set(payload)
        != {"previous_status", "requeue_kind", "previous_attempt_id"}
        or payload.get("previous_status")
        not in {
            JobStatus.RATE_LIMITED.value,
            JobStatus.FAILED.value,
            JobStatus.LOST.value,
        }
        or payload.get("previous_attempt_id") != event_row["attempt_id"]
    ):
        raise StateConflict("ordinary command-aware JOB_REQUEUED payload is malformed")
    return JobRequeueOutcome(
        job_id=expected_job_id,
        command_id=str(event_row["command_id"]),
        event_id=int(event_row["event_id"]),
        requeue_kind=str(kind),
        payload=dict(payload),
    )


def _phase1fc_tx9_quarantined_workers(connection: sqlite3.Connection) -> set[str]:
    """Return the permanent worker-wide TX-9 quarantine set or refuse corruption."""

    result: set[str] = set()
    for row in _tx9_event_rows(connection):
        evidence, _ = _tx9_evidence_from_joined_row(row)
        result.add(str(evidence["worker_id"]))
    return result


def _sealed_role_result(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    expected_role: str,
) -> tuple[dict[str, Any], str]:
    rows = connection.execute(
        """
        SELECT command_id,payload_json FROM events
        WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?
        ORDER BY event_id
        """,
        (attempt_id,),
    ).fetchall()
    if len(rows) != 1:
        raise StateConflict("orchestration lineage requires one sealed role result")
    if str(rows[0]["command_id"]) != f"orchestration-result-seal:{attempt_id}":
        raise StateConflict("orchestration result seal command identity is invalid")
    payload = _strict_canonical_json_loads(
        str(rows[0]["payload_json"]), name="orchestration role result seal"
    )
    if (
        not isinstance(payload, dict)
        or payload.get("orchestration_role") != expected_role
        or not isinstance(payload.get("result_envelope"), dict)
        or re.fullmatch(r"[0-9a-f]{64}", str(payload.get("role_result_digest")))
        is None
    ):
        raise StateConflict("orchestration result seal is malformed")
    return dict(payload["result_envelope"]), str(payload["role_result_digest"])


def _sealed_role_result_payload(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    expected_role: str,
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT command_id,payload_json FROM events
        WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?
        ORDER BY event_id
        """,
        (attempt_id,),
    ).fetchall()
    if len(rows) != 1 or str(rows[0]["command_id"]) != (
        f"orchestration-result-seal:{attempt_id}"
    ):
        raise StateConflict("orchestration lineage requires one exact result seal")
    payload = _strict_canonical_json_loads(
        str(rows[0]["payload_json"]), name="orchestration role result seal"
    )
    keys = {
        "schema_version",
        "job_id",
        "attempt_id",
        "worker_id",
        "quota_class",
        "orchestration_role",
        "session_epoch_id",
        "process_generation_id",
        "turn_id",
        "provider_session_id",
        "provider_native_turn_id",
        "provider_turn_artifact_digest",
        "raw_result_observation_digest",
        "canonical_result_byte_length",
        "candidate_event_command_id",
        "candidate_event_digest",
        "result_envelope",
        "result_envelope_digest",
        "role_result_digest",
        "work_admission_command_id",
        "observed_attestation_digest",
        "execution_principal_snapshot_digest",
        "placement_snapshot_digest",
        "effective_grant_digest",
        "policy_sha",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != keys
        or payload.get("schema_version")
        != "mastermind.orchestration_role_result_seal/v1"
        or payload.get("attempt_id") != attempt_id
        or payload.get("orchestration_role") != expected_role
        or not isinstance(payload.get("result_envelope"), dict)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(payload.get(name))) is None
            for name in {
                "provider_turn_artifact_digest",
                "raw_result_observation_digest",
                "candidate_event_digest",
                "result_envelope_digest",
                "role_result_digest",
                "observed_attestation_digest",
                "execution_principal_snapshot_digest",
                "placement_snapshot_digest",
                "effective_grant_digest",
                "policy_sha",
            }
        )
        or type(payload.get("canonical_result_byte_length")) is not int
        or payload["canonical_result_byte_length"] <= 0
        or orchestration_digest(payload["result_envelope"])
        != payload["result_envelope_digest"]
    ):
        raise StateConflict("orchestration result seal receipt material is malformed")
    return dict(payload)


def _orchestration_terminal_receipt(
    connection: sqlite3.Connection,
    *,
    attempt_id: str,
    expected_role: str,
    seal: dict[str, Any],
) -> dict[str, Any]:
    """Read the post-shutdown supervisor receipt from terminal result_json.

    Packet D makes the ordinary fenced terminal transaction author this exact
    role-qualified payload in both Attempt and Job result_json.  Packet C only
    consumes the narrow durable interface; artifact/validation receipts are
    never falsely attributed to the pre-shutdown role-result seal.
    """

    row = connection.execute(
        "SELECT job_id,result_json,execution_mode FROM attempts WHERE attempt_id=?",
        (attempt_id,),
    ).fetchone()
    if row is None or row["result_json"] is None:
        raise StateConflict("completed orchestration role lacks a terminal receipt")
    payload = _strict_canonical_json_loads(
        str(row["result_json"]), name="orchestration terminal receipt"
    )
    return _validate_orchestration_terminal_receipt_value(
        payload,
        job_id=str(row["job_id"]),
        attempt_id=attempt_id,
        expected_role=expected_role,
        seal=seal,
        execution_mode=str(
            row["execution_mode"] or AttemptExecutionMode.SEALED_WORKER.value
        ),
    )


def _validate_orchestration_terminal_receipt_value(
    payload: Any,
    *,
    job_id: str,
    attempt_id: str,
    expected_role: str,
    seal: dict[str, Any],
    execution_mode: str,
) -> dict[str, Any]:
    keys = {
        "schema_version",
        "status",
        "job_id",
        "attempt_id",
        "orchestration_role",
        "execution_mode",
        "result_seal_command_id",
        "result_evidence",
        "result_envelope",
        "result_envelope_digest",
        "artifact_receipt_digest",
        "validation_receipt_digest",
        "effective_grant_digest",
        "terminal_evidence_digest",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != keys
        or payload.get("schema_version")
        != "mastermind.orchestration_terminal_receipt/v1"
        or payload.get("status") != JobStatus.COMPLETED.value
        or payload.get("job_id") != job_id
        or payload.get("attempt_id") != attempt_id
        or payload.get("orchestration_role") != expected_role
        or payload.get("execution_mode") != execution_mode
        or payload.get("result_seal_command_id")
        != (
            f"orchestration-result-seal:{attempt_id}"
            if execution_mode == AttemptExecutionMode.OPERATOR_HARNESS.value
            else f"sealed-worker-result:{attempt_id}"
        )
        or payload.get("result_envelope_digest")
        != seal.get("result_envelope_digest")
        or payload.get("result_envelope") != seal.get("result_envelope")
        or payload.get("effective_grant_digest")
        != seal.get("effective_grant_digest")
        or (
            execution_mode == AttemptExecutionMode.OPERATOR_HARNESS.value
            and payload.get("result_evidence") is not None
        )
        or (
            execution_mode == AttemptExecutionMode.SEALED_WORKER.value
            and not isinstance(payload.get("result_evidence"), dict)
        )
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(payload.get(name))) is None
            for name in {
                "result_envelope_digest",
                "artifact_receipt_digest",
                "validation_receipt_digest",
                "effective_grant_digest",
                "terminal_evidence_digest",
            }
        )
        or orchestration_digest(
            {
                key: value
                for key, value in payload.items()
                if key != "terminal_evidence_digest"
            }
        )
        != payload.get("terminal_evidence_digest")
    ):
        raise StateConflict("orchestration terminal receipt is malformed")
    return dict(payload)


def _validated_sealed_worker_launch_material(
    attempt_row: sqlite3.Row,
    *,
    allow_unsealed_principal: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Re-derive a SEALED_WORKER principal from its complete launch receipt.

    The launch attestation is an existing supervisor-authored receipt.  Its
    provider-home identity includes the receipt-only ``mtime_ns`` field, while
    the stable Phase 1F-C principal deliberately persists the reviewed six-field
    projection.  No caller text, Worker row, or later model result contributes
    to this identity.
    """

    metadata = _strict_canonical_json_loads(
        str(attempt_row["launch_metadata_json"]), name="sealed-worker launch metadata"
    )
    metadata_keys = {
        "schema_version",
        "launch_attestation",
        "launch_attestation_sha256",
        "launch_attestation_path",
        "authority_policy_hash",
        "authorities",
        "effective_grant_digest",
        "write_paths",
        "validation_argv",
        "quota_class",
        "routing",
    }
    attestation_keys = {
        "schema_version",
        "created_at",
        "executable_path",
        "binary",
        "rendered_argv",
        "environment_keys",
        "permission_profile_sha256",
        "prompt_sha256",
        "expected_base_sha",
        "observed_base_sha",
        "workspace_identity",
        "worker_identity",
        "provider_home_identity",
        "secret_canary_verdict",
        "launch_nonce",
        "process_identity",
        "effective_grant_digest",
    }
    worker_keys = {
        "requested_user",
        "observed_user",
        "expected_uid",
        "expected_gid",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
    }
    process_keys = {
        "pid",
        "pgid",
        "session_id",
        "start_identity",
        "boot_id",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
    }
    home_receipt_keys = {
        "path",
        "device",
        "inode",
        "uid",
        "gid",
        "mode",
        "mtime_ns",
    }
    binary_keys = {
        "path",
        "real_path",
        "version",
        "sha256",
        "team_identifier",
        "size",
        "device",
        "inode",
        "mode",
        "uid",
        "gid",
        "mtime_ns",
    }
    if not isinstance(metadata, dict) or set(metadata) != metadata_keys:
        raise StateConflict("sealed-worker launch metadata is not the closed wire")
    attestation = metadata.get("launch_attestation")
    worker = attestation.get("worker_identity") if isinstance(attestation, dict) else None
    process = attestation.get("process_identity") if isinstance(attestation, dict) else None
    raw_home = (
        attestation.get("provider_home_identity")
        if isinstance(attestation, dict)
        else None
    )
    binary = attestation.get("binary") if isinstance(attestation, dict) else None
    if (
        not isinstance(attestation, dict)
        or set(attestation) != attestation_keys
        or attestation.get("schema_version")
        != "mastermind.executive_launch_attestation/v1"
        or metadata.get("schema_version") != "mastermind.executive_process_launch/v1"
        or metadata.get("launch_attestation_sha256")
        != orchestration_digest(attestation)
        or not isinstance(metadata.get("launch_attestation_path"), str)
        or not str(metadata["launch_attestation_path"]).startswith("/")
        or metadata.get("authority_policy_hash")
        != attempt_row["authority_policy_hash"]
        or metadata.get("effective_grant_digest")
        != attempt_row["effective_grant_digest"]
        or attestation.get("effective_grant_digest")
        != attempt_row["effective_grant_digest"]
        or metadata.get("quota_class") != attempt_row["quota_class"]
        or not isinstance(metadata.get("authorities"), list)
        or not isinstance(metadata.get("routing"), dict)
        or not isinstance(worker, dict)
        or set(worker) != worker_keys
        or not isinstance(process, dict)
        or set(process) != process_keys
        or not isinstance(raw_home, dict)
        or set(raw_home) != home_receipt_keys
        or not isinstance(binary, dict)
        or set(binary) != binary_keys
        or re.fullmatch(r"[0-9a-f]{64}", str(binary.get("sha256"))) is None
        or not isinstance(attestation.get("rendered_argv"), list)
        or not attestation["rendered_argv"]
        or not isinstance(attestation.get("environment_keys"), list)
        or len(attestation["environment_keys"])
        != len(set(attestation["environment_keys"]))
        or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in attestation["environment_keys"]
        )
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(attestation.get(name))) is None
            for name in {"permission_profile_sha256", "prompt_sha256"}
        )
        or not isinstance(attestation.get("secret_canary_verdict"), dict)
        or attestation["secret_canary_verdict"].get("passed") is not True
        or not isinstance(attestation.get("launch_nonce"), str)
        or not attestation["launch_nonce"]
    ):
        raise StateConflict("sealed-worker complete launch attestation is invalid")

    observed_user = worker.get("observed_user")
    requested_user = worker.get("requested_user")
    uid_fields = (
        worker.get("expected_uid"),
        worker.get("effective_uid"),
        worker.get("real_uid"),
        process.get("effective_uid"),
        process.get("real_uid"),
        raw_home.get("uid"),
    )
    gid_fields = (
        worker.get("expected_gid"),
        worker.get("effective_gid"),
        worker.get("real_gid"),
        process.get("effective_gid"),
        process.get("real_gid"),
        raw_home.get("gid"),
    )
    integer_fields = (
        *uid_fields,
        *gid_fields,
        process.get("pid"),
        process.get("pgid"),
        process.get("session_id"),
        raw_home.get("device"),
        raw_home.get("inode"),
        raw_home.get("mode"),
        raw_home.get("mtime_ns"),
    )
    if (
        not isinstance(observed_user, str)
        or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}", observed_user)
        is None
        or requested_user != observed_user
        or any(type(value) is not int or value < 0 for value in integer_fields)
        or len(set(uid_fields)) != 1
        or len(set(gid_fields)) != 1
        or process["pid"] <= 0
        or process["pgid"] <= 0
        or process["session_id"] <= 0
        or process["pid"] != attempt_row["pid"]
        or process["pgid"] != attempt_row["pgid"]
        or process["start_identity"] != attempt_row["process_start_identity"]
        or process["boot_id"] != attempt_row["boot_id"]
        or not isinstance(process["start_identity"], str)
        or not process["start_identity"]
        or not isinstance(process["boot_id"], str)
        or not process["boot_id"]
    ):
        raise StateConflict("sealed-worker launch OS/process identity is invalid")
    try:
        home = validate_provider_home_identity(
            {name: raw_home[name] for name in {"path", "device", "inode", "uid", "gid", "mode"}}
        )
        placement = validate_placement_snapshot(
            _load_canonical_digest_pair(
                attempt_row["placement_snapshot_json"],
                attempt_row["placement_snapshot_digest"],
                name="sealed-worker placement snapshot",
            )
        )
        grant = _load_canonical_digest_pair(
            attempt_row["effective_grant_json"],
            attempt_row["effective_grant_digest"],
            name="sealed-worker effective grant",
        )
    except (OrchestrationPrincipalError, PersistenceError) as exc:
        raise StateConflict(f"sealed-worker immutable launch evidence is invalid: {exc}") from exc
    if (
        placement["worker_id"] != attempt_row["worker_id"]
        or placement["quota_class"] != attempt_row["quota_class"]
        or not isinstance(grant, dict)
        or grant.get("schema_version") != "mastermind.executive_effective_grant/v1"
        or grant.get("job_id") != attempt_row["job_id"]
        or grant.get("policy_sha") != attempt_row["authority_policy_hash"]
        or metadata["authorities"] != grant.get("authorities")
        or metadata["write_paths"] != grant.get("write_paths")
        or metadata["validation_argv"] != grant.get("validation_argv")
    ):
        raise StateConflict("sealed-worker placement/grant launch binding is invalid")
    principal = {
        "schema_version": "mastermind.execution_principal_snapshot/v1",
        "attempt_id": str(attempt_row["attempt_id"]),
        "worker_id": placement["worker_id"],
        "quota_class": placement["quota_class"],
        "provider": placement["provider"],
        "account_label": placement["account_label"],
        "placement_snapshot_digest": str(attempt_row["placement_snapshot_digest"]),
        "os_principal_name": observed_user,
        "os_principal_uid": int(worker["effective_uid"]),
        "provider_home_identity": home,
    }
    stored_principal = _load_canonical_digest_pair(
        attempt_row["execution_principal_snapshot_json"],
        attempt_row["execution_principal_snapshot_digest"],
        name="sealed-worker execution principal snapshot",
    )
    if stored_principal is None:
        if not allow_unsealed_principal:
            raise StateConflict("sealed-worker launch has no immutable principal snapshot")
    elif (
        stored_principal != principal
        or attempt_row["execution_principal_snapshot_digest"]
        != orchestration_digest(principal)
    ):
        raise StateConflict("sealed-worker principal snapshot drifted from launch")
    return dict(attestation), principal, placement, dict(grant)


def _sealed_worker_result_payload(
    connection: sqlite3.Connection,
    attempt_row: sqlite3.Row,
    *,
    expected_role: str,
    terminal_payload: Any,
) -> dict[str, Any]:
    """Build seal-equivalent evidence from the immutable sealed-worker receipt."""

    if not isinstance(terminal_payload, dict):
        raise StateConflict("sealed-worker terminal payload is not an object")
    evidence = terminal_payload.get("result_evidence")
    evidence_keys = {
        "schema_version",
        "collection_receipt",
        "collection_receipt_digest",
        "validation_receipts",
        "validation_receipts_digest",
        "assignment_seal_receipt",
        "assignment_seal_receipt_digest",
    }
    if not isinstance(evidence, dict) or set(evidence) != evidence_keys:
        raise StateConflict("sealed-worker result evidence is not the closed wire")
    collection_receipt = evidence.get("collection_receipt")
    validation_receipt = evidence.get("validation_receipts")
    assignment = evidence.get("assignment_seal_receipt")
    if (
        evidence.get("schema_version")
        != "mastermind.sealed_worker_result_evidence/v1"
        or not isinstance(collection_receipt, dict)
        or set(collection_receipt)
        != {
            "schema_version",
            "collection",
            "uid_sweep",
            "effective_grant_digest",
        }
        or collection_receipt.get("schema_version")
        != "mastermind.executive_collection_evidence/v1"
        or collection_receipt.get("effective_grant_digest")
        != attempt_row["effective_grant_digest"]
        or not isinstance(validation_receipt, dict)
        or set(validation_receipt)
        != {
            "attempt_id",
            "job_id",
            "commands",
            "uid_sweep",
            "effective_grant_digest",
        }
        or validation_receipt.get("effective_grant_digest")
        != attempt_row["effective_grant_digest"]
        or not isinstance(assignment, dict)
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(evidence.get(name))) is None
            for name in {
                "collection_receipt_digest",
                "validation_receipts_digest",
                "assignment_seal_receipt_digest",
            }
        )
        or orchestration_digest(collection_receipt)
        != evidence["collection_receipt_digest"]
        or orchestration_digest(validation_receipt)
        != evidence["validation_receipts_digest"]
        or orchestration_digest(assignment)
        != evidence["assignment_seal_receipt_digest"]
    ):
        raise StateConflict("sealed-worker receipt digests are invalid")
    from control_plane.executive_worker_broker import uid_sweep_receipt_is_passing

    if (
        not uid_sweep_receipt_is_passing(collection_receipt["uid_sweep"])
        or not uid_sweep_receipt_is_passing(validation_receipt["uid_sweep"])
        or not uid_sweep_receipt_is_passing(assignment.get("uid_sweep"))
    ):
        raise StateConflict("sealed-worker terminal UID cleanup is not proven")
    collection = collection_receipt.get("collection")
    if (
        not isinstance(collection, dict)
        or set(collection)
        != {"process_ref", "result", "stdout_sha256", "stderr_sha256", "result_sha256"}
    ):
        raise StateConflict("sealed-worker collection receipt is malformed")
    process_ref = collection.get("process_ref")
    result = collection.get("result")
    process_keys = {
        "run_id",
        "pid",
        "pgid",
        "process_start_identity",
        "boot_session_id",
        "launch_nonce",
        "provider_session_id",
        "stdout_path",
        "stderr_path",
        "result_path",
        "started_at",
        "binary",
        "base_sha",
        "session_id",
        "effective_uid",
        "effective_gid",
        "real_uid",
        "real_gid",
    }
    result_keys = {
        "job_id",
        "run_id",
        "worker_id",
        "status",
        "structured_output",
        "artifact_manifest",
        "git_manifest",
        "usage",
        "provider_session_id",
        "exit_code",
        "started_at",
        "finished_at",
        "error",
    }
    if (
        not isinstance(process_ref, dict)
        or set(process_ref) != process_keys
        or not isinstance(result, dict)
        or set(result) != result_keys
        or process_ref.get("run_id") != attempt_row["attempt_id"]
        or process_ref.get("pid") != attempt_row["pid"]
        or process_ref.get("pgid") != attempt_row["pgid"]
        or process_ref.get("process_start_identity")
        != attempt_row["process_start_identity"]
        or process_ref.get("boot_session_id") != attempt_row["boot_id"]
        or process_ref.get("provider_session_id") != attempt_row["provider_session_id"]
        or not isinstance(process_ref.get("binary"), dict)
        or re.fullmatch(r"[0-9a-f]{64}", str(collection.get("stdout_sha256"))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(collection.get("stderr_sha256"))) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(collection.get("result_sha256"))) is None
        or result.get("job_id") != attempt_row["job_id"]
        or result.get("run_id") != attempt_row["attempt_id"]
        or result.get("worker_id") != attempt_row["worker_id"]
        or result.get("status") != "SUCCEEDED"
        or result.get("provider_session_id") != attempt_row["provider_session_id"]
        or result.get("exit_code") != attempt_row["exit_code"]
        or result.get("error") is not None
        or not isinstance(result.get("structured_output"), dict)
        or not isinstance(result.get("artifact_manifest"), list)
        or not isinstance(result.get("git_manifest"), dict)
        or not isinstance(result.get("usage"), dict)
        or not isinstance(result.get("started_at"), str)
        or not result["started_at"]
        or not isinstance(result.get("finished_at"), str)
        or not result["finished_at"]
        or any(
            not isinstance(item, dict)
            or set(item) != {"path", "sha256", "size"}
            or re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256"))) is None
            or type(item.get("size")) is not int
            or item["size"] < 0
            for item in result.get("artifact_manifest", [])
        )
        or set(assignment)
        != {
            "schema_version",
            "sealed_at",
            "control_uid",
            "paths",
            "passed",
            "attempt_id",
            "job_id",
            "uid_sweep",
            "effective_grant_digest",
        }
        or assignment.get("schema_version")
        != "mastermind.executive_assignment_seal/v1"
        or assignment.get("passed") is not True
        or assignment.get("attempt_id") != attempt_row["attempt_id"]
        or assignment.get("job_id") != attempt_row["job_id"]
        or assignment.get("effective_grant_digest")
        != attempt_row["effective_grant_digest"]
        or type(assignment.get("control_uid")) is not int
        or assignment["control_uid"] < 0
        or not isinstance(assignment.get("sealed_at"), str)
        or not assignment["sealed_at"]
    ):
        raise StateConflict("sealed-worker collection/result identity is invalid")
    attestation, _principal, _placement, grant = (
        _validated_sealed_worker_launch_material(attempt_row)
    )
    job_row = connection.execute(
        "SELECT validation_commands_json,result_json FROM jobs WHERE job_id=?",
        (attempt_row["job_id"],),
    ).fetchone()
    if job_row is None:
        raise StateConflict("sealed-worker result lost its Job")
    expected_validations = grant.get("validation_argv")
    commands = validation_receipt.get("commands")
    validation_keys = {
        "argv",
        "exit_code",
        "stdout_sha256",
        "stdout_size",
        "stderr_sha256",
        "stderr_size",
        "timed_out",
        "error",
    }
    if (
        validation_receipt.get("attempt_id") != attempt_row["attempt_id"]
        or validation_receipt.get("job_id") != attempt_row["job_id"]
        or not isinstance(expected_validations, list)
        or not isinstance(commands, list)
        or len(commands) != len(expected_validations)
        or any(
            not isinstance(item, dict)
            or set(item) != validation_keys
            or item.get("argv") != expected_argv
            or item.get("exit_code") != 0
            or item.get("timed_out") is not False
            or item.get("error") is not None
            or re.fullmatch(r"[0-9a-f]{64}", str(item.get("stdout_sha256"))) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(item.get("stderr_sha256"))) is None
            or type(item.get("stdout_size")) is not int
            or item["stdout_size"] < 0
            or type(item.get("stderr_size")) is not int
            or item["stderr_size"] < 0
            for item, expected_argv in zip(commands, expected_validations, strict=True)
        )
    ):
        raise StateConflict("sealed-worker validation sequence is invalid")
    paths = assignment.get("paths")
    identity_keys = {"path", "device", "inode", "mode", "uid", "gid", "mtime_ns"}
    if not isinstance(paths, dict) or set(paths) != {"run", "workspace"}:
        raise StateConflict("sealed-worker assignment seal paths are invalid")
    for boundary in paths.values():
        before = boundary.get("before") if isinstance(boundary, dict) else None
        after = boundary.get("after") if isinstance(boundary, dict) else None
        if (
            not isinstance(boundary, dict)
            or set(boundary) != {"before", "after", "worker_traversal_revoked"}
            or boundary.get("worker_traversal_revoked") is not True
            or not isinstance(before, dict)
            or set(before) != identity_keys
            or not isinstance(after, dict)
            or set(after) != identity_keys
            or any(
                type(before.get(name)) is not int for name in identity_keys - {"path"}
            )
            or any(
                type(after.get(name)) is not int for name in identity_keys - {"path"}
            )
            or not isinstance(before.get("path"), str)
            or not before["path"].startswith("/")
            or after.get("path") != before["path"]
            or any(
                before.get(name) != after.get(name)
                for name in {"device", "inode", "uid", "gid"}
            )
            or after.get("mode") != 0o700
        ):
            raise StateConflict("sealed-worker assignment seal identity is invalid")
    workspace_identity = attestation.get("workspace_identity")
    if (
        not isinstance(workspace_identity, dict)
        or paths["workspace"]["after"]["path"] != workspace_identity.get("path")
        or paths["workspace"]["after"]["uid"] != assignment["control_uid"]
        or paths["run"]["after"]["uid"] != assignment["control_uid"]
        or process_ref.get("effective_uid")
        != attestation["process_identity"]["effective_uid"]
        or process_ref.get("effective_gid")
        != attestation["process_identity"]["effective_gid"]
        or process_ref.get("real_uid") != attestation["process_identity"]["real_uid"]
        or process_ref.get("real_gid") != attestation["process_identity"]["real_gid"]
        or process_ref.get("session_id") != attestation["process_identity"]["session_id"]
        or process_ref.get("launch_nonce") != attestation.get("launch_nonce")
        or process_ref.get("binary") != attestation.get("binary")
        or process_ref.get("base_sha") != attestation.get("observed_base_sha")
    ):
        raise StateConflict("sealed-worker collection lost its accepted launch identity")
    envelope = dict(result["structured_output"])
    envelope_digest = orchestration_digest(envelope)
    role_result = envelope.get("role_result")
    artifact_manifest = result["artifact_manifest"]
    declared_artifacts = (
        role_result.get("artifacts") if isinstance(role_result, dict) else None
    )
    if expected_role in {"plan", "review", "aggregation"}:
        artifacts_match = artifact_manifest == []
    else:
        try:
            from control_plane.codex_worker import _path_matches_patterns

            artifacts_match = (
                isinstance(declared_artifacts, list)
                and [
                    {"path": item.get("path"), "digest": item.get("sha256")}
                    for item in artifact_manifest
                ]
                == declared_artifacts
                and all(
                    _path_matches_patterns(
                        str(item["path"]), tuple(grant.get("write_paths") or ())
                    )
                    for item in artifact_manifest
                )
            )
        except (ImportError, KeyError, TypeError):
            artifacts_match = False
    if (
        not isinstance(role_result, dict)
        or not artifacts_match
        or terminal_payload.get("result_envelope") != envelope
        or terminal_payload.get("result_envelope_digest") != envelope_digest
        or terminal_payload.get("artifact_receipt_digest")
        != orchestration_digest(result["artifact_manifest"])
        or terminal_payload.get("validation_receipt_digest")
        != evidence["validation_receipts_digest"]
        or (
            job_row["result_json"] is not None
            and _strict_canonical_json_loads(
                str(job_row["result_json"]), name="sealed-worker Job terminal receipt"
            )
            != terminal_payload
        )
    ):
        raise StateConflict("sealed-worker terminal receipt lost collection evidence")
    attestation_digest = orchestration_digest(attestation)
    return {
        "schema_version": "mastermind.sealed_worker_result_receipt/v1",
        "job_id": str(attempt_row["job_id"]),
        "attempt_id": str(attempt_row["attempt_id"]),
        "worker_id": str(attempt_row["worker_id"]),
        "quota_class": str(attempt_row["quota_class"]),
        "orchestration_role": expected_role,
        "session_epoch_id": f"sealed-worker:{attempt_row['attempt_id']}",
        "process_generation_id": f"sealed-worker:{attempt_row['attempt_id']}",
        "turn_id": f"sealed-worker-turn:{attempt_row['attempt_id']}",
        "provider_session_id": str(attempt_row["provider_session_id"]),
        "provider_native_turn_id": str(attempt_row["provider_session_id"]),
        "provider_turn_artifact_digest": str(collection["result_sha256"]),
        "raw_result_observation_digest": str(evidence["collection_receipt_digest"]),
        "canonical_result_byte_length": len(_json_dumps(envelope).encode("utf-8")),
        "candidate_event_command_id": f"sealed-worker-result:{attempt_row['attempt_id']}",
        "candidate_event_digest": str(evidence["collection_receipt_digest"]),
        "result_envelope": envelope,
        "result_envelope_digest": envelope_digest,
        "role_result_digest": orchestration_digest(role_result),
        "work_admission_command_id": f"sealed-worker-launch:{attempt_row['attempt_id']}",
        "observed_attestation_digest": attestation_digest,
        "execution_principal_snapshot_digest": str(
            attempt_row["execution_principal_snapshot_digest"]
        ),
        "placement_snapshot_digest": str(attempt_row["placement_snapshot_digest"]),
        "effective_grant_digest": str(attempt_row["effective_grant_digest"]),
        "policy_sha": CooCyclePolicy.load().policy_sha256,
    }


def _validated_admission_principal(
    attempt_row: sqlite3.Row, admission: dict[str, Any]
) -> dict[str, Any]:
    try:
        from control_plane.executive_orchestration_principal import (
            OperatorPrincipalObservation,
            build_execution_principal_snapshot,
            digest as principal_digest,
        )

        observation = OperatorPrincipalObservation.from_dict(
            admission["principal_observation"]
        ).to_dict()
        placement = _load_canonical_digest_pair(
            attempt_row["placement_snapshot_json"],
            attempt_row["placement_snapshot_digest"],
            name="terminal placement snapshot",
        )
        principal = _load_canonical_digest_pair(
            attempt_row["execution_principal_snapshot_json"],
            attempt_row["execution_principal_snapshot_digest"],
            name="terminal execution principal snapshot",
        )
        expected_principal = build_execution_principal_snapshot(
            attempt_id=str(attempt_row["attempt_id"]),
            placement_snapshot=placement,
            observation=observation,
        )
    except Exception as exc:
        raise StateConflict(f"orchestration principal admission is invalid: {exc}") from exc
    if (
        observation != admission.get("principal_observation")
        or principal_digest(observation)
        != admission.get("principal_observation_digest")
        or principal != expected_principal
        or principal_digest(principal)
        != attempt_row["execution_principal_snapshot_digest"]
        or admission.get("execution_principal_snapshot_digest")
        != attempt_row["execution_principal_snapshot_digest"]
    ):
        raise StateConflict("orchestration principal admission/snapshot drifted")
    return observation


def _validated_orchestration_terminal_generation(
    connection: sqlite3.Connection,
    *,
    attempt_row: sqlite3.Row,
    seal: dict[str, Any],
) -> dict[str, Any]:
    """Re-derive the exact admitted, shut-down generation named by a role seal."""

    mode = AttemptExecutionMode(
        attempt_row["execution_mode"] or AttemptExecutionMode.SEALED_WORKER.value
    )
    if mode is AttemptExecutionMode.SEALED_WORKER:
        return _validated_sealed_worker_terminal_evidence(
            connection,
            attempt_row=attempt_row,
            seal=seal,
        )
    generation_id = str(seal["process_generation_id"])
    generation = connection.execute(
        """
        SELECT g.*,e.attempt_id,e.worker_id AS epoch_worker,e.epoch_number,
               e.provider_session_id AS epoch_provider_session,e.state AS epoch_state
        FROM process_generations g
        JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id
        WHERE g.process_generation_id=?
        """,
        (generation_id,),
    ).fetchone()
    if generation is None:
        raise StateConflict("orchestration terminal seal lost its process generation")
    latest = connection.execute(
        """
        SELECT g.process_generation_id,e.epoch_number,g.generation_number
        FROM process_generations g
        JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id
        WHERE e.attempt_id=?
        ORDER BY e.epoch_number DESC,g.generation_number DESC
        LIMIT 1
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()
    active = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM harness_session_epochs
           WHERE attempt_id=? AND state='CURRENT') AS current_epochs,
          (SELECT COUNT(*) FROM process_generations g
           JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id
           WHERE e.attempt_id=? AND g.executive_writer_held=1) AS writers
        """,
        (attempt_row["attempt_id"], attempt_row["attempt_id"]),
    ).fetchone()
    admission_event = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='ORCHESTRATION_WORK_ADMITTED'
          AND aggregate_type='process_generation' AND aggregate_id=?
        ORDER BY event_id
        """,
        (generation_id,),
    ).fetchall()
    if len(admission_event) != 1:
        raise StateConflict("orchestration terminal generation lacks one work admission")
    event = admission_event[0]
    admission = _strict_canonical_json_loads(
        str(event["payload_json"]), name="orchestration work admission"
    )
    admission_keys = {
        "schema_version",
        "job_id",
        "attempt_id",
        "worker_id",
        "quota_class",
        "orchestration_role",
        "process_generation_id",
        "provider_session_id",
        "tx3_applied_command_id",
        "observed_attestation_digest",
        "principal_observation",
        "principal_observation_digest",
        "execution_principal_snapshot_digest",
        "placement_snapshot_digest",
        "effective_grant_digest",
        "policy_sha",
        "launch_decision",
    }
    if not isinstance(admission, dict) or set(admission) != admission_keys:
        raise StateConflict("orchestration work admission is not the closed wire")
    observation = _validated_admission_principal(attempt_row, admission)
    decision_rows = connection.execute(
        """
        SELECT * FROM events
        WHERE aggregate_type='process_generation' AND aggregate_id=?
          AND event_type='OHF_LAUNCH_DECISION'
        ORDER BY event_id
        """,
        (generation_id,),
    ).fetchall()
    decision = (
        _strict_canonical_json_loads(
            str(decision_rows[0]["payload_json"]), name="OHF launch decision"
        )
        if len(decision_rows) == 1
        else None
    )
    tx3 = connection.execute(
        "SELECT * FROM events WHERE command_id=?",
        (admission.get("tx3_applied_command_id"),),
    ).fetchone()
    tx3_payload = (
        _strict_canonical_json_loads(
            str(tx3["payload_json"]), name="TX-3 APPLIED receipt"
        )
        if tx3 is not None
        else None
    )
    tx3_intent = (
        connection.execute(
            "SELECT * FROM events WHERE command_id=?", (tx3["aggregate_id"],)
        ).fetchone()
        if tx3 is not None
        else None
    )
    tx3_intent_payload = (
        _strict_canonical_json_loads(
            str(tx3_intent["payload_json"]), name="TX-3 INTENT receipt"
        )
        if tx3_intent is not None
        else None
    )
    if int(generation["generation_number"]) == 1:
        expected_launch_applied = {
            "operation_kind": OperationKind.START_SESSION.value,
            "provider_session_id": seal["provider_session_id"],
            "process_generation_id": generation_id,
        }
        expected_launch_intent = {
            "schema_version": "mastermind.operator_harness_intent/v1",
            "operation_kind": OperationKind.START_SESSION.value,
            "attempt_id": attempt_row["attempt_id"],
            "session_epoch_id": seal["session_epoch_id"],
            "process_generation_id": generation_id,
            "worker_id": attempt_row["worker_id"],
            "provider_session_id": None,
        }
    elif int(generation["generation_number"]) == 2:
        expected_launch_applied = {
            "operation_kind": OperationKind.RESUME_SESSION.value,
            "process_generation_id": generation_id,
            "provider_session_id": seal["provider_session_id"],
        }
        expected_launch_intent = {
            "operation_kind": OperationKind.RESUME_SESSION.value,
            "attempt_id": attempt_row["attempt_id"],
            "session_epoch_id": seal["session_epoch_id"],
            "process_generation_id": generation_id,
            "worker_id": attempt_row["worker_id"],
            "provider_session_id": seal["provider_session_id"],
        }
    else:
        raise StateConflict("orchestration terminal generation exceeds G1/G2")
    if (
        generation["attempt_id"] != attempt_row["attempt_id"]
        or generation["worker_id"] != attempt_row["worker_id"]
        or generation["epoch_worker"] != attempt_row["worker_id"]
        or generation["provider_session_id"] != seal["provider_session_id"]
        or generation["epoch_provider_session"] != seal["provider_session_id"]
        or generation["session_epoch_id"] != seal["session_epoch_id"]
        or generation["observed_attestation_digest"]
        != seal["observed_attestation_digest"]
        or generation["ended_at_ms"] is None
        or int(generation["executive_writer_held"]) != 0
        or generation["provider_writer_state"] != "RELEASED"
        or generation["epoch_state"] == "CURRENT"
        or latest is None
        or latest["process_generation_id"] != generation_id
        or active is None
        or int(active["current_epochs"]) != 0
        or int(active["writers"]) != 0
        or event["command_id"] != f"ohf-work-admit:{generation_id}"
        or event["actor"] != "supervisor"
        or event["job_id"] != attempt_row["job_id"]
        or event["attempt_id"] != attempt_row["attempt_id"]
        or event["worker_id"] != attempt_row["worker_id"]
        or event["quota_class"] != attempt_row["quota_class"]
        or tx3 is None
        or tx3["event_type"] != OperationReceiptKind.APPLIED.value
        or tx3["actor"] != "supervisor"
        or tx3["aggregate_type"] != "operator_operation"
        or tx3["attempt_id"] != attempt_row["attempt_id"]
        or tx3["worker_id"] != attempt_row["worker_id"]
        or tx3["quota_class"] != attempt_row["quota_class"]
        or tx3_payload != expected_launch_applied
        or tx3_intent is None
        or tx3_intent["event_type"] != OperationReceiptKind.INTENT.value
        or tx3_intent["aggregate_type"] != "operator_operation"
        or tx3_intent["aggregate_id"] != tx3["aggregate_id"]
        or tx3_intent["attempt_id"] != attempt_row["attempt_id"]
        or tx3_intent["worker_id"] != attempt_row["worker_id"]
        or tx3_intent_payload != expected_launch_intent
        or admission.get("schema_version")
        != "mastermind.orchestration_work_admission/v1"
        or admission.get("job_id") != attempt_row["job_id"]
        or admission.get("attempt_id") != attempt_row["attempt_id"]
        or admission.get("worker_id") != attempt_row["worker_id"]
        or admission.get("quota_class") != attempt_row["quota_class"]
        or admission.get("orchestration_role") != seal["orchestration_role"]
        or admission.get("process_generation_id") != generation_id
        or admission.get("provider_session_id") != seal["provider_session_id"]
        or admission.get("observed_attestation_digest")
        != seal["observed_attestation_digest"]
        or observation["attempt_id"] != attempt_row["attempt_id"]
        or observation["worker_id"] != attempt_row["worker_id"]
        or observation["process_generation_id"] != generation_id
        or observation["provider_session_id"] != seal["provider_session_id"]
        or observation["process_identity"]["pid"] != generation["pid"]
        or observation["process_identity"]["pgid"] != generation["pgid"]
        or observation["process_identity"]["process_start_identity"]
        != generation["process_start_identity"]
        or observation["process_identity"]["boot_id"] != generation["boot_id"]
        or admission.get("execution_principal_snapshot_digest")
        != attempt_row["execution_principal_snapshot_digest"]
        or admission.get("execution_principal_snapshot_digest")
        != seal["execution_principal_snapshot_digest"]
        or admission.get("placement_snapshot_digest")
        != attempt_row["placement_snapshot_digest"]
        or admission.get("placement_snapshot_digest")
        != seal["placement_snapshot_digest"]
        or admission.get("effective_grant_digest")
        != attempt_row["effective_grant_digest"]
        or admission.get("effective_grant_digest") != seal["effective_grant_digest"]
        or admission.get("policy_sha") != CooCyclePolicy.load().policy_sha256
        or admission.get("policy_sha") != seal["policy_sha"]
        or admission.get("launch_decision") != LaunchDecision.ALLOW.value
        or not isinstance(decision, dict)
        or decision.get("decision") != LaunchDecision.ALLOW.value
        or decision.get("attestation_digest")
        != seal["observed_attestation_digest"]
        or seal["work_admission_command_id"] != event["command_id"]
    ):
        raise StateConflict("orchestration terminal generation evidence is invalid")
    return admission


def _validated_sealed_worker_terminal_evidence(
    connection: sqlite3.Connection,
    *,
    attempt_row: sqlite3.Row,
    seal: dict[str, Any],
) -> dict[str, Any]:
    """Validate the sealed-worker equivalent without accepting OHF table evidence."""

    attestation, principal, placement, grant = (
        _validated_sealed_worker_launch_material(attempt_row)
    )
    attestation_digest = orchestration_digest(attestation)
    exit_events = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='ATTEMPT_PROCESS_EXITED' AND attempt_id=?
        ORDER BY event_id
        """,
        (attempt_row["attempt_id"],),
    ).fetchall()
    seal_event_count = connection.execute(
        """
        SELECT COUNT(*) FROM events
        WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    harness_rows = connection.execute(
        """
        SELECT COUNT(*) FROM harness_session_epochs WHERE attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    admission_rows = connection.execute(
        """
        SELECT COUNT(*) FROM events
        WHERE event_type='ORCHESTRATION_WORK_ADMITTED' AND attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    running_rows = connection.execute(
        """
        SELECT COUNT(*) FROM events
        WHERE event_type='ATTEMPT_RUNNING' AND attempt_id=?
        """,
        (attempt_row["attempt_id"],),
    ).fetchone()[0]
    attestation_process = (
        attestation.get("process_identity") if isinstance(attestation, dict) else None
    )
    if (
        seal["observed_attestation_digest"] != attestation_digest
        or seal["work_admission_command_id"]
        != f"sealed-worker-launch:{attempt_row['attempt_id']}"
        or seal["policy_sha"] != CooCyclePolicy.load().policy_sha256
        or seal["execution_principal_snapshot_digest"]
        != attempt_row["execution_principal_snapshot_digest"]
        or seal["placement_snapshot_digest"]
        != attempt_row["placement_snapshot_digest"]
        or seal["effective_grant_digest"] != attempt_row["effective_grant_digest"]
        or not isinstance(placement, dict)
        or placement.get("worker_id") != attempt_row["worker_id"]
        or placement.get("quota_class") != attempt_row["quota_class"]
        or not isinstance(principal, dict)
        or principal.get("attempt_id") != attempt_row["attempt_id"]
        or principal.get("worker_id") != attempt_row["worker_id"]
        or principal.get("quota_class") != attempt_row["quota_class"]
        or principal.get("placement_snapshot_digest")
        != attempt_row["placement_snapshot_digest"]
        or principal.get("os_principal_uid")
        != attestation["worker_identity"]["effective_uid"]
        or principal.get("os_principal_name")
        != attestation["worker_identity"]["observed_user"]
        or principal.get("provider_home_identity")
        != {
            name: attestation["provider_home_identity"][name]
            for name in {"path", "device", "inode", "uid", "gid", "mode"}
        }
        or not isinstance(grant, dict)
        or grant.get("job_id") != attempt_row["job_id"]
        or not isinstance(attestation_process, dict)
        or attestation_process.get("pid") != attempt_row["pid"]
        or attestation_process.get("pgid") != attempt_row["pgid"]
        or attestation_process.get("start_identity")
        != attempt_row["process_start_identity"]
        or attestation_process.get("boot_id") != attempt_row["boot_id"]
        or attempt_row["provider_session_id"] != seal["provider_session_id"]
        or attempt_row["exit_code"] is None
        or len(exit_events) != 1
        or exit_events[0]["actor"] != "supervisor"
        or exit_events[0]["aggregate_type"] != "attempt"
        or exit_events[0]["aggregate_id"] != attempt_row["attempt_id"]
        or exit_events[0]["job_id"] != attempt_row["job_id"]
        or exit_events[0]["attempt_id"] != attempt_row["attempt_id"]
        or exit_events[0]["worker_id"] != attempt_row["worker_id"]
        or exit_events[0]["quota_class"] != attempt_row["quota_class"]
        or _strict_canonical_json_loads(
            str(exit_events[0]["payload_json"]), name="sealed-worker exit receipt"
        )
        != {"exit_code": int(attempt_row["exit_code"])}
        or int(seal_event_count) != 0
        or int(harness_rows) != 0
        or int(admission_rows) != 0
        or int(running_rows) != 1
    ):
        raise StateConflict("sealed-worker terminal evidence is invalid")
    return {
        "schema_version": "mastermind.sealed_worker_terminal_evidence/v1",
        "attempt_id": str(attempt_row["attempt_id"]),
        "launch_attestation_digest": str(attestation_digest),
        "process_exit_event_id": int(exit_events[0]["event_id"]),
    }


def _validated_orchestration_role_result_payload(
    connection: sqlite3.Connection,
    *,
    attempt_row: sqlite3.Row,
    expected_role: str,
    terminal_payload: Any | None = None,
) -> dict[str, Any]:
    mode = AttemptExecutionMode(
        attempt_row["execution_mode"] or AttemptExecutionMode.SEALED_WORKER.value
    )
    if mode is AttemptExecutionMode.OPERATOR_HARNESS:
        seal = _sealed_role_result_payload(
            connection,
            attempt_id=str(attempt_row["attempt_id"]),
            expected_role=expected_role,
        )
        _validated_orchestration_terminal_generation(
            connection,
            attempt_row=attempt_row,
            seal=seal,
        )
        return seal
    if terminal_payload is None:
        if attempt_row["result_json"] is None:
            raise StateConflict("sealed-worker Attempt lacks its terminal receipt")
        terminal_payload = _strict_canonical_json_loads(
            str(attempt_row["result_json"]), name="sealed-worker terminal receipt"
        )
    seal = _sealed_worker_result_payload(
        connection,
        attempt_row,
        expected_role=expected_role,
        terminal_payload=terminal_payload,
    )
    _validated_sealed_worker_terminal_evidence(
        connection,
        attempt_row=attempt_row,
        seal=seal,
    )
    return seal


def _validated_orchestration_child_terminal_payload(
    connection: sqlite3.Connection,
    *,
    attempt_row: sqlite3.Row,
    job_row: sqlite3.Row,
    payload: Any,
) -> dict[str, Any]:
    """Validate one plan/work/review/repair result inside its terminal TX."""

    role = str(job_row["orchestration_role"] or "")
    if role not in {"plan", "work", "review", "repair"}:
        raise StateConflict("orchestration child terminal role is invalid")
    seal = _validated_orchestration_role_result_payload(
        connection,
        attempt_row=attempt_row,
        expected_role=role,
        terminal_payload=payload,
    )
    terminal = _validate_orchestration_terminal_receipt_value(
        payload,
        job_id=str(job_row["job_id"]),
        attempt_id=str(attempt_row["attempt_id"]),
        expected_role=role,
        seal=seal,
        execution_mode=str(
            attempt_row["execution_mode"] or AttemptExecutionMode.SEALED_WORKER.value
        ),
    )
    try:
        from control_plane.executive_orchestration_result import (
            canonical_digest as result_digest,
            validate_envelope,
        )

        envelope = validate_envelope(
            seal["result_envelope"],
            expected_job_id=str(job_row["job_id"]),
            expected_run_id=str(attempt_row["attempt_id"]),
            expected_worker_id=str(attempt_row["worker_id"]),
            expected_role=role,
            expected_root_job_id=str(job_row["root_job_id"]),
        )
    except Exception as exc:
        raise StateConflict(f"orchestration {role} result is invalid: {exc}") from exc
    body = envelope["role_result"]
    if result_digest(body) != seal.get("role_result_digest"):
        raise StateConflict("orchestration role body digest mismatches its seal")
    if role == "plan":
        if (
            job_row["parent_job_id"] != job_row["root_job_id"]
            or body.get("root_job_id") != job_row["root_job_id"]
            or body.get("plan_attempt_id") != attempt_row["attempt_id"]
        ):
            raise StateConflict("planner result lineage mismatches its strict root")
        return terminal
    if (
        body.get("root_job_id") != job_row["root_job_id"]
        or body.get("plan_attempt_id") != job_row["plan_attempt_id"]
        or body.get("plan_digest") != job_row["plan_digest"]
        or body.get("plan_step_id") != job_row["plan_step_id"]
        or body.get("repair_round") != job_row["repair_round"]
    ):
        raise StateConflict(f"{role} result lineage mismatches its immutable Job")
    if role == "review":
        reviewed = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_row["reviews_job_id"],)
        ).fetchone()
        if reviewed is None or reviewed["orchestration_role"] not in {"work", "repair"}:
            raise StateConflict("review result lost its reviewed revision")
        reviewed_attempt, _seal, _terminal, reviewed_digest = (
            _validated_role_completion_material(
                connection,
                job_row=reviewed,
                expected_role=str(reviewed["orchestration_role"]),
                root_job_id=str(job_row["root_job_id"]),
            )
        )
        if (
            body.get("reviewed_job_id") != reviewed["job_id"]
            or body.get("reviewed_attempt_id") != reviewed_attempt["attempt_id"]
            or body.get("reviewed_result_digest") != reviewed_digest
        ):
            raise StateConflict("review result does not bind the exact completed revision")
    elif role == "repair":
        predecessor = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_row["supersedes_job_id"],)
        ).fetchone()
        rejected_review = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?",
            (body.get("rejected_review_job_id"),),
        ).fetchone()
        if (
            predecessor is None
            or rejected_review is None
            or body.get("supersedes_job_id") != predecessor["job_id"]
            or rejected_review["reviews_job_id"] != predecessor["job_id"]
        ):
            raise StateConflict("repair result lost its predecessor/reject lineage")
        _attempt, rejected_seal, _terminal, rejected_digest = (
            _validated_role_completion_material(
                connection,
                job_row=rejected_review,
                expected_role="review",
                root_job_id=str(job_row["root_job_id"]),
            )
        )
        rejected_body = rejected_seal["result_envelope"]["role_result"]
        if (
            rejected_body.get("verdict") != "reject"
            or body.get("rejected_review_result_digest") != rejected_digest
        ):
            raise StateConflict("repair result is not bound to the exact reject")
    return terminal


def _validated_plan_admission(
    connection: sqlite3.Connection, root_row: sqlite3.Row
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the immutable reservation and its revalidated typed plan."""

    rows = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?
        ORDER BY event_id
        """,
        (root_row["job_id"],),
    ).fetchall()
    if len(rows) != 1:
        raise StateConflict("orchestration child requires one COO plan admission")
    event = rows[0]
    admission = _strict_canonical_json_loads(
        str(event["payload_json"]), name="COO plan admission"
    )
    keys = {
        "schema_version",
        "root_job_id",
        "policy_sha",
        "plan_attempt_id",
        "plan_digest",
        "steps",
        "reserved_children_total",
        "command_id",
        "reservation_digest",
    }
    if not isinstance(admission, dict) or set(admission) != keys:
        raise StateConflict("COO plan admission is not the closed wire")
    digest_input = dict(admission)
    reservation_digest = digest_input.pop("reservation_digest", None)
    policy = CooCyclePolicy.load()
    expected_command = (
        f"coo-cycle:{root_row['job_id']}:admit-plan:{admission.get('plan_attempt_id')}"
    )
    if (
        admission.get("schema_version") != "mastermind.coo_plan_admission/v1"
        or admission.get("root_job_id") != root_row["job_id"]
        or admission.get("policy_sha") != policy.policy_sha256
        or event["actor"] != "coo"
        or event["aggregate_type"] != "job"
        or event["aggregate_id"] != root_row["job_id"]
        or event["job_id"] != root_row["job_id"]
        or event["attempt_id"] != admission.get("plan_attempt_id")
        or event["worker_id"] is not None
        or event["quota_class"] is not None
        or event["command_id"] != expected_command
        or admission.get("command_id") != expected_command
        or re.fullmatch(r"[0-9a-f]{64}", str(reservation_digest)) is None
        or orchestration_digest(digest_input) != reservation_digest
    ):
        raise StateConflict("COO plan admission identity/digest is invalid")
    plan_attempt = connection.execute(
        """
        SELECT a.*,j.job_id AS plan_job_id,j.orchestration_role AS plan_role,
               j.parent_job_id AS plan_parent,j.root_job_id AS plan_root
        FROM attempts a JOIN jobs j ON j.job_id=a.job_id
        WHERE a.attempt_id=?
        """,
        (admission["plan_attempt_id"],),
    ).fetchone()
    if (
        plan_attempt is None
        or plan_attempt["status"] != AttemptStatus.COMPLETED.value
        or plan_attempt["plan_role"] != "plan"
        or plan_attempt["plan_parent"] != root_row["job_id"]
        or plan_attempt["plan_root"] != root_row["job_id"]
    ):
        raise StateConflict("COO plan admission lost its completed planner Attempt")
    seal = _validated_orchestration_role_result_payload(
        connection,
        attempt_row=plan_attempt,
        expected_role="plan",
    )
    if (
        seal["job_id"] != plan_attempt["plan_job_id"]
        or seal["worker_id"] != plan_attempt["worker_id"]
        or seal["quota_class"] != plan_attempt["quota_class"]
        or seal["effective_grant_digest"] != plan_attempt["effective_grant_digest"]
        or seal["placement_snapshot_digest"]
        != plan_attempt["placement_snapshot_digest"]
        or seal["execution_principal_snapshot_digest"]
        != plan_attempt["execution_principal_snapshot_digest"]
    ):
        raise StateConflict("sealed planner evidence does not match its Attempt")
    _orchestration_terminal_receipt(
        connection,
        attempt_id=str(admission["plan_attempt_id"]),
        expected_role="plan",
        seal=seal,
    )
    try:
        from control_plane.executive_orchestration_result import (
            canonical_digest as result_digest,
            validate_envelope,
        )

        envelope = validate_envelope(
            seal["result_envelope"],
            expected_job_id=str(plan_attempt["plan_job_id"]),
            expected_run_id=str(plan_attempt["attempt_id"]),
            expected_worker_id=str(plan_attempt["worker_id"]),
            expected_role="plan",
            expected_root_job_id=str(root_row["job_id"]),
        )
    except Exception as exc:
        raise StateConflict(f"sealed plan result is invalid: {exc}") from exc
    plan_body = dict(envelope["role_result"])
    if (
        result_digest(plan_body) != seal["role_result_digest"]
        or admission["plan_digest"] != seal["role_result_digest"]
        or plan_body.get("plan_attempt_id") != admission["plan_attempt_id"]
    ):
        raise StateConflict("COO admission plan digest drifted from the sealed body")
    reservation_steps = admission.get("steps")
    if not isinstance(reservation_steps, list) or len(reservation_steps) != len(
        plan_body["steps"]
    ):
        raise StateConflict("COO plan admission step manifest is malformed")
    requirements: list[bool] = []
    root_validations = _strict_canonical_json_loads(
        str(root_row["validation_commands_json"]), name="root validation commands"
    )
    root_validation_ids = [orchestration_digest(argv) for argv in root_validations]
    for ordinal, (reserved, step) in enumerate(
        zip(reservation_steps, plan_body["steps"], strict=True)
    ):
        required = bool(
            step["review_required"]
            or root_row["business_impact"] in {"material", "critical"}
            or step["business_impact"] in {"material", "critical"}
        )
        requirements.append(required)
        expected_member_command = f"{expected_command}:member:{ordinal}"
        if (
            not isinstance(reserved, dict)
            or set(reserved)
            != {
                "ordinal",
                "plan_step_id",
                "step_slots",
                "review_required",
                "work_job_id",
                "member_command_id",
            }
            or reserved["ordinal"] != ordinal
            or reserved["plan_step_id"] != step["step_id"]
            or reserved["review_required"] is not required
            or reserved["step_slots"]
            != policy.reserved_step_slots(review_required=required)
            or reserved["member_command_id"] != expected_member_command
        ):
            raise StateConflict("COO plan admission reservation arithmetic drifted")
        member = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (reserved["work_job_id"],)
        ).fetchone()
        member_event = connection.execute(
            "SELECT * FROM events WHERE command_id=?", (expected_member_command,)
        ).fetchone()
        expected_validation_ids = (
            root_validation_ids if "RUN_TESTS" in step["requested_authorities"] else []
        )
        expected_validation_argv = root_validations if expected_validation_ids else []
        if step["validation_ids"] != expected_validation_ids:
            raise StateConflict("typed plan changed the mandatory root validation set")
        if member is not None:
            member_role, member_provenance, _ = _decode_orchestration_job_fields(member)
            member_authorities = _strict_canonical_json_loads(
                str(member["requested_authorities_json"]),
                name="admitted work authorities",
            )
            member_paths = _strict_canonical_json_loads(
                str(member["allowed_write_paths_json"]),
                name="admitted work paths",
            )
            member_validations = _strict_canonical_json_loads(
                str(member["validation_commands_json"]),
                name="admitted work validations",
            )
            member_constraints = _strict_canonical_json_loads(
                str(member["constraints_json"]), name="admitted work constraints"
            )
        else:
            member_role = member_provenance = None
            member_authorities = member_paths = member_validations = member_constraints = None
        if (
            member is None
            or member_role != "work"
            or member["parent_job_id"] != root_row["job_id"]
            or member["plan_attempt_id"] != admission["plan_attempt_id"]
            or member["plan_digest"] != admission["plan_digest"]
            or member["plan_step_id"] != step["step_id"]
            or member["repair_round"] != 0
            or bool(member["review_required"]) is not required
            or member["objective"] != step["objective"]
            or member_authorities != step["requested_authorities"]
            or member_paths != step["allowed_write_paths"]
            or member_validations != expected_validation_argv
            or int(member["attempt_limit"]) != int(step["attempt_limit"])
            or not isinstance(member_constraints, dict)
            or member_constraints.get("cost_class") != step["cost_class"]
            or not isinstance(member_provenance, dict)
            or member_provenance.get("command_id") != expected_member_command
            or member_provenance.get("source_digest") != admission["plan_digest"]
            or member_event is None
            or member_event["event_type"] != "JOB_CREATED"
            or member_event["job_id"] != member["job_id"]
        ):
            raise StateConflict("COO plan admission member manifest drifted")
        _reconcile_cycle_child_creation(
            connection,
            event_row=member_event,
            root_row=root_row,
            role="work",
            objective=str(step["objective"]),
            requested_authorities=list(step["requested_authorities"]),
            allowed_write_paths=list(step["allowed_write_paths"]),
            validation_commands=expected_validation_argv,
            cost_class=str(step["cost_class"]),
            attempt_limit=int(step["attempt_limit"]),
            review_required=required,
            command_id=expected_member_command,
            plan_attempt_id=str(admission["plan_attempt_id"]),
            plan_digest=str(admission["plan_digest"]),
            plan_step_id=str(step["step_id"]),
            repair_round=0,
        )
    try:
        expected_total = policy.reserved_children_total(tuple(requirements))
    except CooCyclePolicyError as exc:
        raise StateConflict(f"COO plan reservation exceeds policy: {exc}") from exc
    if admission["reserved_children_total"] != expected_total:
        raise StateConflict("COO plan admission total reservation drifted")
    return admission, plan_body


def _review_attempt_is_independent(
    connection: sqlite3.Connection,
    *,
    review_attempt_id: str,
    reviewed_attempt_id: str,
) -> bool:
    rows = connection.execute(
        "SELECT * FROM attempts WHERE attempt_id IN (?,?)",
        (review_attempt_id, reviewed_attempt_id),
    ).fetchall()
    by_id = {str(row["attempt_id"]): row for row in rows}
    review = by_id.get(review_attempt_id)
    reviewed = by_id.get(reviewed_attempt_id)
    if review is None or reviewed is None:
        return False
    try:
        review_principal = _load_canonical_digest_pair(
            review["execution_principal_snapshot_json"],
            review["execution_principal_snapshot_digest"],
            name="review execution principal snapshot",
        )
        reviewed_principal = _load_canonical_digest_pair(
            reviewed["execution_principal_snapshot_json"],
            reviewed["execution_principal_snapshot_digest"],
            name="reviewed execution principal snapshot",
        )
        review_grant = _load_canonical_digest_pair(
            review["effective_grant_json"],
            review["effective_grant_digest"],
            name="review effective grant",
        )
    except PersistenceError:
        return False
    principal_keys = {
        "schema_version",
        "attempt_id",
        "worker_id",
        "quota_class",
        "provider",
        "account_label",
        "placement_snapshot_digest",
        "os_principal_name",
        "os_principal_uid",
        "provider_home_identity",
    }
    if (
        not isinstance(review_principal, dict)
        or not isinstance(reviewed_principal, dict)
        or set(review_principal) != principal_keys
        or set(reviewed_principal) != principal_keys
        or review_principal.get("schema_version")
        != "mastermind.execution_principal_snapshot/v1"
        or reviewed_principal.get("schema_version")
        != "mastermind.execution_principal_snapshot/v1"
        or review_principal.get("attempt_id") != review_attempt_id
        or reviewed_principal.get("attempt_id") != reviewed_attempt_id
        or review_principal.get("worker_id") == reviewed_principal.get("worker_id")
        or (
            review_principal.get("os_principal_name"),
            review_principal.get("os_principal_uid"),
        )
        == (
            reviewed_principal.get("os_principal_name"),
            reviewed_principal.get("os_principal_uid"),
        )
        or review_principal.get("account_label")
        == reviewed_principal.get("account_label")
        or not isinstance(review_principal.get("provider_home_identity"), dict)
        or not isinstance(reviewed_principal.get("provider_home_identity"), dict)
        or review_principal["provider_home_identity"].get("path")
        == reviewed_principal["provider_home_identity"].get("path")
        or orchestration_digest(review_principal["provider_home_identity"])
        == orchestration_digest(reviewed_principal["provider_home_identity"])
        or not isinstance(review_grant, dict)
        or "READ" not in (review_grant.get("authorities") or [])
        or set(review_grant.get("authorities") or []) - {"READ", "RUN_TESTS"}
        or review_grant.get("write_paths") != []
    ):
        return False
    return True


def _validated_role_completion_material(
    connection: sqlite3.Connection,
    *,
    job_row: sqlite3.Row,
    expected_role: str,
    root_job_id: str,
) -> tuple[sqlite3.Row, dict[str, Any], dict[str, Any], str]:
    attempt_id = job_row["current_attempt_id"]
    attempt = connection.execute(
        "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    if (
        job_row["status"] != JobStatus.COMPLETED.value
        or attempt is None
        or attempt["job_id"] != job_row["job_id"]
        or attempt["status"] != AttemptStatus.COMPLETED.value
        or attempt["effective_grant_digest"] is None
        or attempt["placement_snapshot_digest"] is None
        or attempt["execution_principal_snapshot_digest"] is None
    ):
        raise StateConflict(f"{expected_role} current revision lacks terminal evidence")
    seal = _validated_orchestration_role_result_payload(
        connection,
        attempt_row=attempt,
        expected_role=expected_role,
    )
    if (
        seal["job_id"] != job_row["job_id"]
        or seal["worker_id"] != attempt["worker_id"]
        or seal["quota_class"] != attempt["quota_class"]
        or seal["effective_grant_digest"] != attempt["effective_grant_digest"]
        or seal["placement_snapshot_digest"] != attempt["placement_snapshot_digest"]
        or seal["execution_principal_snapshot_digest"]
        != attempt["execution_principal_snapshot_digest"]
    ):
        raise StateConflict(f"sealed {expected_role} evidence mismatches its Attempt")
    try:
        from control_plane.executive_orchestration_result import (
            canonical_digest as result_digest,
            validate_envelope,
        )

        envelope = validate_envelope(
            seal["result_envelope"],
            expected_job_id=str(job_row["job_id"]),
            expected_run_id=str(attempt_id),
            expected_worker_id=str(attempt["worker_id"]),
            expected_role=expected_role,
            expected_root_job_id=root_job_id,
        )
    except Exception as exc:
        raise StateConflict(f"sealed {expected_role} result is invalid: {exc}") from exc
    role_result = dict(envelope["role_result"])
    if result_digest(role_result) != seal["role_result_digest"]:
        raise StateConflict(f"sealed {expected_role} result digest is invalid")
    _job_role, creation_provenance, _provenance_digest = (
        _decode_orchestration_job_fields(job_row)
    )
    if not isinstance(creation_provenance, dict):
        raise StateConflict(f"sealed {expected_role} Job lost its creation provenance")
    creation_event = connection.execute(
        "SELECT * FROM events WHERE command_id=?",
        (creation_provenance["command_id"],),
    ).fetchone()
    if (
        creation_event is None
        or creation_event["event_type"] != "JOB_CREATED"
        or creation_event["job_id"] != job_row["job_id"]
        or creation_event["aggregate_type"] != "job"
        or creation_event["aggregate_id"] != job_row["job_id"]
    ):
        raise StateConflict(f"sealed {expected_role} Job lost its creation Event")
    creation_payload = _strict_canonical_json_loads(
        str(creation_event["payload_json"]),
        name=f"{expected_role} JOB_CREATED payload",
    )
    if not isinstance(creation_payload, dict):
        raise StateConflict(f"sealed {expected_role} Job creation payload is malformed")
    if expected_role in {"work", "repair", "review"} and (
        role_result.get("root_job_id") != root_job_id
        or role_result.get("plan_attempt_id") != job_row["plan_attempt_id"]
        or role_result.get("plan_digest") != job_row["plan_digest"]
        or role_result.get("plan_step_id") != job_row["plan_step_id"]
        or role_result.get("repair_round") != job_row["repair_round"]
    ):
        raise StateConflict(f"sealed {expected_role} inner lineage mismatches its Job")
    if expected_role == "review":
        reviewed = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_row["reviews_job_id"],)
        ).fetchone()
        if reviewed is None or reviewed["orchestration_role"] not in {"work", "repair"}:
            raise StateConflict("sealed review lost its reviewed revision")
        reviewed_attempt, _reviewed_seal, _reviewed_terminal, reviewed_digest = (
            _validated_role_completion_material(
                connection,
                job_row=reviewed,
                expected_role=str(reviewed["orchestration_role"]),
                root_job_id=root_job_id,
            )
        )
        if (
            role_result.get("reviewed_job_id") != reviewed["job_id"]
            or role_result.get("reviewed_attempt_id")
            != reviewed_attempt["attempt_id"]
            or role_result.get("reviewed_result_digest") != reviewed_digest
            or role_result.get("repair_round") != reviewed["repair_round"]
            or creation_payload.get("reviewed_result_digest") != reviewed_digest
            or creation_provenance.get("source_id") != reviewed["job_id"]
            or creation_provenance.get("source_digest") != reviewed_digest
        ):
            raise StateConflict("sealed review body mismatches its exact reviewed revision")
    if expected_role == "repair":
        predecessor = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_row["supersedes_job_id"],)
        ).fetchone()
        rejected_review = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?",
            (role_result.get("rejected_review_job_id"),),
        ).fetchone()
        if (
            predecessor is None
            or rejected_review is None
            or role_result.get("supersedes_job_id") != predecessor["job_id"]
            or rejected_review["orchestration_role"] != "review"
            or rejected_review["reviews_job_id"] != predecessor["job_id"]
        ):
            raise StateConflict("sealed repair lost its exact rejected predecessor/review")
        reject_attempt, reject_seal, _reject_terminal, reject_digest = (
            _validated_role_completion_material(
                connection,
                job_row=rejected_review,
                expected_role="review",
                root_job_id=root_job_id,
            )
        )
        reject_body = reject_seal["result_envelope"]["role_result"]
        if (
            role_result.get("rejected_review_result_digest") != reject_digest
            or creation_payload.get("rejected_review_job_id")
            != rejected_review["job_id"]
            or creation_payload.get("rejected_review_result_digest") != reject_digest
            or creation_provenance.get("source_id") != rejected_review["job_id"]
            or creation_provenance.get("source_digest") != reject_digest
            or reject_body.get("verdict") != "reject"
            or not _review_attempt_is_independent(
                connection,
                review_attempt_id=str(reject_attempt["attempt_id"]),
                reviewed_attempt_id=str(predecessor["current_attempt_id"]),
            )
        ):
            raise StateConflict("sealed repair is not authorized by its exact reject")
    terminal = _orchestration_terminal_receipt(
        connection,
        attempt_id=str(attempt_id),
        expected_role=expected_role,
        seal=seal,
    )
    return attempt, seal, terminal, str(seal["role_result_digest"])


def _current_orchestration_tree_material_for_dispatch(
    connection: sqlite3.Connection,
    root_row: sqlite3.Row,
    admission: dict[str, Any],
    plan_body: dict[str, Any],
) -> list[dict[str, Any]]:
    """Re-derive reservation/current-lineage eligibility without terminal claims."""

    children = connection.execute(
        "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY job_id",
        (root_row["job_id"],),
    ).fetchall()
    if len(children) > int(admission["reserved_children_total"]):
        raise StateConflict("orchestration tree exceeds its reserved child total")
    policy = CooCyclePolicy.load()
    reservations = {
        str(item["plan_step_id"]): item for item in admission["steps"]
    }
    result: list[dict[str, Any]] = []
    for step in plan_body["steps"]:
        step_id = str(step["step_id"])
        reservation = reservations[step_id]
        revisions = sorted(
            [
                row
                for row in children
                if row["orchestration_role"] in {"work", "repair"}
                and row["plan_step_id"] == step_id
            ],
            key=lambda row: (int(row["repair_round"]), str(row["job_id"])),
        )
        if not revisions or revisions[0]["orchestration_role"] != "work":
            raise StateConflict("admitted step lost its initial work revision")
        for index, revision in enumerate(revisions):
            if (
                int(revision["repair_round"]) != index
                or revision["plan_attempt_id"] != admission["plan_attempt_id"]
                or revision["plan_digest"] != admission["plan_digest"]
                or revision["plan_step_id"] != step_id
                or (index == 0 and revision["supersedes_job_id"] is not None)
                or (
                    index > 0
                    and revision["supersedes_job_id"] != revisions[index - 1]["job_id"]
                )
            ):
                raise StateConflict("dispatch lineage is forked or skipped")
        reviews = [
            row
            for row in children
            if row["orchestration_role"] == "review"
            and row["plan_step_id"] == step_id
        ]
        for revision in revisions:
            if (
                len([row for row in reviews if row["reviews_job_id"] == revision["job_id"]])
                > policy.max_review_attempts_per_job
            ):
                raise StateConflict("revision exceeds its reserved review Job ceiling")
        if len(revisions) + len(reviews) > int(reservation["step_slots"]):
            raise StateConflict("dispatch tree consumed an unreserved step slot")
        current = revisions[-1]
        result.append(
            {
                "plan_step_id": step_id,
                "current_job_id": str(current["job_id"]),
                "review_required": bool(reservation["review_required"]),
            }
        )
    expected_ids = {str(step["step_id"]) for step in plan_body["steps"]}
    if any(
        row["orchestration_role"] not in {"plan", "work", "repair", "review"}
        or int(row["depth"]) != 1
        or (
            row["orchestration_role"] != "plan"
            and row["plan_step_id"] not in expected_ids
        )
        for row in children
    ):
        raise StateConflict("dispatch tree contains an unexpected child")
    return result


def _current_orchestration_tree_material(
    connection: sqlite3.Connection,
    root_row: sqlite3.Row,
    admission: dict[str, Any],
    plan_body: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Derive the exact current revisions, approvals, and adverse history."""

    children = connection.execute(
        "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY job_id",
        (root_row["job_id"],),
    ).fetchall()
    living = [
        str(row["job_id"])
        for row in children
        if JobStatus(row["status"]) not in _TERMINAL_JOB_STATUSES
    ]
    if living:
        raise StateConflict(
            "aggregation handoff refuses living child Jobs: " + ", ".join(living)
        )
    if any(int(row["depth"]) != 1 for row in children):
        raise StateConflict("orchestration tree contains a non-direct child")
    known_steps = {str(step["step_id"]) for step in plan_body["steps"]}
    allowed_roles = {"plan", "work", "repair", "review"}
    if any(
        row["orchestration_role"] not in allowed_roles
        or (
            row["orchestration_role"] != "plan"
            and row["plan_step_id"] not in known_steps
        )
        for row in children
    ):
        raise StateConflict("orchestration tree contains an unexpected child")
    plan_rows = [row for row in children if row["orchestration_role"] == "plan"]
    if len(plan_rows) != 1 or plan_rows[0]["current_attempt_id"] != admission["plan_attempt_id"]:
        raise StateConflict("orchestration tree planner identity drifted")
    policy = CooCyclePolicy.load()
    if len(children) > int(admission["reserved_children_total"]):
        raise StateConflict("orchestration tree exceeds its total reservation")

    revisions_out: list[dict[str, Any]] = []
    history_out: list[dict[str, Any]] = []
    reservation_by_step = {
        str(item["plan_step_id"]): item for item in admission["steps"]
    }
    for ordinal, step in enumerate(plan_body["steps"]):
        step_id = str(step["step_id"])
        reservation = reservation_by_step[step_id]
        revisions = [
            row
            for row in children
            if row["orchestration_role"] in {"work", "repair"}
            and row["plan_step_id"] == step_id
        ]
        revisions.sort(key=lambda row: (int(row["repair_round"]), str(row["job_id"])))
        if not revisions or revisions[0]["orchestration_role"] != "work":
            raise StateConflict("plan step has no initial work revision")
        for index, revision in enumerate(revisions):
            if (
                int(revision["repair_round"]) != index
                or revision["plan_attempt_id"] != admission["plan_attempt_id"]
                or revision["plan_digest"] != admission["plan_digest"]
                or (index == 0 and revision["supersedes_job_id"] is not None)
                or (
                    index > 0
                    and revision["supersedes_job_id"] != revisions[index - 1]["job_id"]
                )
            ):
                raise StateConflict("plan-step revision lineage is forked or skipped")
        review_rows = [
            row
            for row in children
            if row["orchestration_role"] == "review"
            and row["plan_step_id"] == step_id
        ]
        for revision in revisions:
            if (
                len(
                    [
                        row
                        for row in review_rows
                        if row["reviews_job_id"] == revision["job_id"]
                    ]
                )
                > policy.max_review_attempts_per_job
            ):
                raise StateConflict("revision exceeds its review Job record ceiling")
        used_slots = len(revisions) + len(review_rows)
        if used_slots > int(reservation["step_slots"]):
            raise StateConflict("plan step consumed another step's reserved slot")
        if not reservation["review_required"] and (
            len(revisions) != 1 or review_rows
        ):
            raise StateConflict("unreviewed plan step cannot consume review/repair slots")
        for revision in revisions[:-1]:
            attempt, _seal, _terminal, result_digest = _validated_role_completion_material(
                connection,
                job_row=revision,
                expected_role=str(revision["orchestration_role"]),
                root_job_id=str(root_row["job_id"]),
            )
            history_out.append(
                {
                    "kind": "superseded_revision",
                    "job_id": str(revision["job_id"]),
                    "attempt_id": str(attempt["attempt_id"]),
                    "status": "COMPLETED",
                    "verdict": None,
                    "result_digest": result_digest,
                    "independent": None,
                }
            )
        current = revisions[-1]
        current_attempt, current_seal, current_terminal, current_result_digest = (
            _validated_role_completion_material(
                connection,
                job_row=current,
                expected_role=str(current["orchestration_role"]),
                root_job_id=str(root_row["job_id"]),
            )
        )
        current_reviews = sorted(
            [row for row in review_rows if row["reviews_job_id"] == current["job_id"]],
            key=lambda row: str(row["job_id"]),
        )
        qualifying: tuple[sqlite3.Row, sqlite3.Row, dict[str, Any], str] | None = None
        current_independent_reject = False
        for review in review_rows:
            attempt_id = review["current_attempt_id"]
            if review["status"] != JobStatus.COMPLETED.value:
                history_out.append(
                    {
                        "kind": "review",
                        "job_id": str(review["job_id"]),
                        "attempt_id": str(attempt_id) if attempt_id else None,
                        "status": str(review["status"]),
                        "verdict": None,
                        "result_digest": None,
                        "independent": False,
                    }
                )
                continue
            review_attempt, review_seal, _review_terminal, review_digest = (
                _validated_role_completion_material(
                    connection,
                    job_row=review,
                    expected_role="review",
                    root_job_id=str(root_row["job_id"]),
                )
            )
            body = review_seal["result_envelope"]["role_result"]
            independent = _review_attempt_is_independent(
                connection,
                review_attempt_id=str(review_attempt["attempt_id"]),
                reviewed_attempt_id=str(body["reviewed_attempt_id"]),
            )
            exact_target = bool(
                review["reviews_job_id"] == current["job_id"]
                and body.get("reviewed_job_id") == current["job_id"]
                and body.get("reviewed_attempt_id") == current_attempt["attempt_id"]
                and body.get("reviewed_result_digest") == current_result_digest
                and body.get("repair_round") == current["repair_round"]
            )
            if (
                exact_target
                and independent
                and body.get("verdict") == "approve"
                and qualifying is None
            ):
                qualifying = (review, review_attempt, review_seal, review_digest)
            else:
                if exact_target and independent and body.get("verdict") == "reject":
                    current_independent_reject = True
                history_out.append(
                    {
                        "kind": "review",
                        "job_id": str(review["job_id"]),
                        "attempt_id": str(review_attempt["attempt_id"]),
                        "status": "COMPLETED",
                        "verdict": body.get("verdict"),
                        "result_digest": review_digest,
                        "independent": bool(independent),
                    }
                )
        if current_independent_reject:
            raise StateConflict(
                "current revision has an unresolved independent reject verdict"
            )
        if reservation["review_required"] and qualifying is None:
            raise StateConflict("current revision lacks a qualifying independent approval")
        if qualifying is None:
            qualifying_fields: dict[str, Any] = {
                "qualifying_review_job_id": None,
                "qualifying_review_attempt_id": None,
                "qualifying_review_result_digest": None,
                "qualifying_review_effective_grant_digest": None,
                "qualifying_review_principal_snapshot_digest": None,
            }
        else:
            review, review_attempt, _review_seal, review_digest = qualifying
            qualifying_fields = {
                "qualifying_review_job_id": str(review["job_id"]),
                "qualifying_review_attempt_id": str(review_attempt["attempt_id"]),
                "qualifying_review_result_digest": review_digest,
                "qualifying_review_effective_grant_digest": str(
                    review_attempt["effective_grant_digest"]
                ),
                "qualifying_review_principal_snapshot_digest": str(
                    review_attempt["execution_principal_snapshot_digest"]
                ),
            }
        revisions_out.append(
            {
                "ordinal": ordinal,
                "plan_step_id": step_id,
                "current_job_id": str(current["job_id"]),
                "current_attempt_id": str(current_attempt["attempt_id"]),
                "current_result_digest": current_result_digest,
                "current_raw_result_digest": str(
                    current_seal["raw_result_observation_digest"]
                ),
                "effective_grant_digest": str(current_attempt["effective_grant_digest"]),
                "artifact_receipt_digest": str(
                    current_terminal["artifact_receipt_digest"]
                ),
                "validation_receipt_digest": str(
                    current_terminal["validation_receipt_digest"]
                ),
                "placement_snapshot_digest": str(
                    current_attempt["placement_snapshot_digest"]
                ),
                "execution_principal_snapshot_digest": str(
                    current_attempt["execution_principal_snapshot_digest"]
                ),
                "repair_round": int(current["repair_round"]),
                "review_required": bool(reservation["review_required"]),
                **qualifying_fields,
            }
        )
    history_out.sort(
        key=lambda item: (
            str(item["job_id"]),
            str(item["attempt_id"] or ""),
            str(item["kind"]),
        )
    )
    return revisions_out, history_out


def _assert_orchestration_lineage_for_create(
    connection: sqlite3.Connection,
    *,
    role: str,
    parent_row: sqlite3.Row,
    plan_attempt_id: str | None,
    plan_digest: str | None,
    plan_step_id: str | None,
    repair_round: int | None,
    reviews_job_id: str | None,
    supersedes_job_id: str | None,
    rejected_review_job_id: str | None = None,
    rejected_review_result_digest: str | None = None,
) -> None:
    parent_role, parent_provenance, _ = _decode_orchestration_job_fields(parent_row)
    if (
        parent_role != "aggregation"
        or parent_provenance is None
        or parent_provenance.get("creator") != "ceo_intent"
        or parent_row["root_job_id"] != parent_row["job_id"]
    ):
        raise StateConflict("orchestration child requires a strict v2 aggregation root")
    if role == "plan":
        return
    plan_attempt = connection.execute(
        """
        SELECT a.*,j.orchestration_role AS plan_role,j.parent_job_id AS plan_parent,
               j.root_job_id AS plan_root
        FROM attempts a JOIN jobs j ON j.job_id=a.job_id
        WHERE a.attempt_id=?
        """,
        (plan_attempt_id,),
    ).fetchone()
    if (
        plan_attempt is None
        or plan_attempt["status"] != AttemptStatus.COMPLETED.value
        or plan_attempt["plan_role"] != "plan"
        or plan_attempt["plan_parent"] != parent_row["job_id"]
        or plan_attempt["plan_root"] != parent_row["root_job_id"]
    ):
        raise StateConflict("plan lineage does not name the completed plan child")
    _, sealed_plan_digest = _sealed_role_result(
        connection, attempt_id=str(plan_attempt_id), expected_role="plan"
    )
    if sealed_plan_digest != plan_digest:
        raise StateConflict("plan digest does not match the sealed plan role result")
    if role == "work":
        return
    if role == "review":
        reviewed = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (reviews_job_id,)
        ).fetchone()
        if (
            reviewed is None
            or reviewed["parent_job_id"] != parent_row["job_id"]
            or reviewed["root_job_id"] != parent_row["root_job_id"]
            or reviewed["orchestration_role"] not in {"work", "repair"}
            or reviewed["status"] != JobStatus.COMPLETED.value
            or reviewed["plan_attempt_id"] != plan_attempt_id
            or reviewed["plan_digest"] != plan_digest
            or reviewed["plan_step_id"] != plan_step_id
            or int(reviewed["repair_round"]) != repair_round
        ):
            raise StateConflict("review lineage does not match the completed current revision")
        return
    if role == "repair":
        predecessor = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (supersedes_job_id,)
        ).fetchone()
        if (
            predecessor is None
            or predecessor["parent_job_id"] != parent_row["job_id"]
            or predecessor["root_job_id"] != parent_row["root_job_id"]
            or predecessor["orchestration_role"] not in {"work", "repair"}
            or predecessor["status"] != JobStatus.COMPLETED.value
            or predecessor["plan_attempt_id"] != plan_attempt_id
            or predecessor["plan_digest"] != plan_digest
            or predecessor["plan_step_id"] != plan_step_id
            or int(predecessor["repair_round"]) + 1 != repair_round
        ):
            raise StateConflict("repair lineage must supersede the immediate current revision")
        if connection.execute(
            "SELECT 1 FROM jobs WHERE supersedes_job_id=?", (supersedes_job_id,)
        ).fetchone() is not None:
            raise StateConflict("repair lineage cannot fork an already superseded revision")
        if not rejected_review_job_id or not rejected_review_result_digest:
            raise StateConflict("repair requires the exact rejecting review evidence")
        review_row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?",
            (rejected_review_job_id,),
        ).fetchone()
        if (
            review_row is None
            or review_row["orchestration_role"] != "review"
            or review_row["reviews_job_id"] != supersedes_job_id
        ):
            raise StateConflict("repair rejecting review does not target its predecessor")
        review_attempt, review_seal, _terminal, review_digest = (
            _validated_role_completion_material(
                connection,
                job_row=review_row,
                expected_role="review",
                root_job_id=str(parent_row["job_id"]),
            )
        )
        role_result = review_seal["result_envelope"].get("role_result")
        if (
            not isinstance(role_result, dict)
            or review_digest != rejected_review_result_digest
            or role_result.get("verdict") != "reject"
            or role_result.get("root_job_id") != parent_row["job_id"]
            or role_result.get("plan_attempt_id") != plan_attempt_id
            or role_result.get("plan_digest") != plan_digest
            or role_result.get("plan_step_id") != plan_step_id
            or role_result.get("repair_round") != predecessor["repair_round"]
            or role_result.get("reviewed_job_id") != supersedes_job_id
            or role_result.get("reviewed_attempt_id")
            != predecessor["current_attempt_id"]
            or role_result.get("reviewed_result_digest") is None
            or not _review_attempt_is_independent(
                connection,
                review_attempt_id=str(review_attempt["attempt_id"]),
                reviewed_attempt_id=str(predecessor["current_attempt_id"]),
            )
        ):
            raise StateConflict("repair requires an independent sealed reject verdict")


def _validated_aggregation_handoff(
    connection: sqlite3.Connection, job_row: sqlite3.Row
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT * FROM events
        WHERE event_type='COO_AGGREGATION_HANDOFF_READY' AND job_id=?
        ORDER BY event_id
        """,
        (job_row["job_id"],),
    ).fetchall()
    if len(rows) != 1:
        raise StateConflict(
            "aggregation root is unclaimable until one immutable handoff is ready"
        )
    handoff = _strict_canonical_json_loads(
        str(rows[0]["payload_json"]), name="aggregation handoff"
    )
    keys = {
        "schema_version",
        "root_job_id",
        "policy_sha",
        "plan_attempt_id",
        "plan_digest",
        "reservation_digest",
        "revisions",
        "rejected_history",
        "aggregate_result_schema",
        "allowed_evidence_reads",
        "command_id",
        "handoff_digest",
    }
    if not isinstance(handoff, dict) or set(handoff) != keys:
        raise StateConflict("aggregation handoff is not the closed wire")
    digest = handoff.get("handoff_digest")
    digest_input = dict(handoff)
    digest_input.pop("handoff_digest")
    if (
        handoff.get("schema_version") != "mastermind.aggregation_handoff/v1"
        or handoff.get("root_job_id") != job_row["job_id"]
        or rows[0]["actor"] != "coo"
        or rows[0]["aggregate_type"] != "job"
        or rows[0]["aggregate_id"] != job_row["job_id"]
        or rows[0]["job_id"] != job_row["job_id"]
        or rows[0]["attempt_id"] != handoff.get("plan_attempt_id")
        or rows[0]["worker_id"] is not None
        or rows[0]["quota_class"] is not None
        or rows[0]["command_id"]
        != f"coo-cycle:{job_row['job_id']}:aggregation-handoff:1"
        or handoff.get("command_id") != rows[0]["command_id"]
        or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
        or orchestration_digest(digest_input) != digest
    ):
        raise StateConflict("aggregation handoff identity/digest is invalid")
    admission, plan_body = _validated_plan_admission(connection, job_row)
    revisions, rejected_history = _current_orchestration_tree_material(
        connection, job_row, admission, plan_body
    )
    if (
        handoff["policy_sha"] != admission["policy_sha"]
        or handoff["plan_attempt_id"] != admission["plan_attempt_id"]
        or handoff["plan_digest"] != admission["plan_digest"]
        or handoff["reservation_digest"] != admission["reservation_digest"]
        or handoff["revisions"] != revisions
        or handoff["rejected_history"] != rejected_history
        or handoff["aggregate_result_schema"]
        != "mastermind.aggregation_result/v1"
        or handoff["allowed_evidence_reads"] != ["attempts", "events", "jobs"]
    ):
        raise StateConflict("aggregation handoff no longer matches the current tree")
    return handoff


def _validated_aggregation_terminal_payload(
    connection: sqlite3.Connection,
    *,
    attempt_row: sqlite3.Row,
    payload: Any,
) -> dict[str, Any]:
    """Validate the exact sealed aggregation result at the fenced terminal seam."""

    root = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (attempt_row["job_id"],)
    ).fetchone()
    if root is None or root["orchestration_role"] != "aggregation":
        raise StateConflict("aggregation terminal target is not the strict root")
    handoff = _validated_aggregation_handoff(connection, root)
    seal = _validated_orchestration_role_result_payload(
        connection,
        attempt_row=attempt_row,
        expected_role="aggregation",
        terminal_payload=payload,
    )
    if (
        seal["job_id"] != root["job_id"]
        or seal["worker_id"] != attempt_row["worker_id"]
        or seal["quota_class"] != attempt_row["quota_class"]
        or seal["effective_grant_digest"]
        != attempt_row["effective_grant_digest"]
        or seal["placement_snapshot_digest"]
        != attempt_row["placement_snapshot_digest"]
        or seal["execution_principal_snapshot_digest"]
        != attempt_row["execution_principal_snapshot_digest"]
        or seal["policy_sha"] != handoff["policy_sha"]
    ):
        raise StateConflict("aggregation seal mismatches its exact Attempt/handoff")
    terminal = _validate_orchestration_terminal_receipt_value(
        payload,
        job_id=str(root["job_id"]),
        attempt_id=str(attempt_row["attempt_id"]),
        expected_role="aggregation",
        seal=seal,
        execution_mode=str(
            attempt_row["execution_mode"]
            or AttemptExecutionMode.SEALED_WORKER.value
        ),
    )
    try:
        from control_plane.executive_orchestration_result import (
            canonical_digest as result_digest,
            validate_envelope,
        )

        envelope = validate_envelope(
            terminal["result_envelope"],
            expected_job_id=str(root["job_id"]),
            expected_run_id=str(attempt_row["attempt_id"]),
            expected_worker_id=str(attempt_row["worker_id"]),
            expected_role="aggregation",
            expected_root_job_id=str(root["job_id"]),
        )
    except Exception as exc:
        raise StateConflict(f"typed aggregation result is invalid: {exc}") from exc
    body = dict(envelope["role_result"])
    expected_revisions = [
        {
            "ordinal": item["ordinal"],
            "plan_step_id": item["plan_step_id"],
            "current_job_id": item["current_job_id"],
            "current_attempt_id": item["current_attempt_id"],
            "current_result_digest": item["current_result_digest"],
            "repair_round": item["repair_round"],
            "review_required": item["review_required"],
            "qualifying_review_job_id": item["qualifying_review_job_id"],
            "qualifying_review_attempt_id": item[
                "qualifying_review_attempt_id"
            ],
            "qualifying_review_result_digest": item[
                "qualifying_review_result_digest"
            ],
        }
        for item in handoff["revisions"]
    ]
    if (
        result_digest(body) != seal["role_result_digest"]
        or body.get("root_job_id") != root["job_id"]
        or body.get("handoff_digest") != handoff["handoff_digest"]
        or body.get("policy_sha") != handoff["policy_sha"]
        or body.get("plan_attempt_id") != handoff["plan_attempt_id"]
        or body.get("plan_digest") != handoff["plan_digest"]
        or body.get("revisions") != expected_revisions
    ):
        raise StateConflict("typed aggregation body no longer matches the current handoff")
    return terminal


def _assert_orchestration_dispatch_eligible(
    connection: sqlite3.Connection, job_row: sqlite3.Row
) -> None:
    """Re-prove the role-specific cycle phase before any capacity mutation."""

    role, provenance, _ = _decode_orchestration_job_fields(job_row)
    if role is None or provenance is None:
        raise StateConflict("dispatch target is not a closed orchestration Job")
    root = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (job_row["root_job_id"],)
    ).fetchone()
    if root is None:
        raise StateConflict("orchestration dispatch lost its strict-v2 root")
    root_role, root_provenance, _ = _decode_orchestration_job_fields(root)
    if (
        root_role != "aggregation"
        or root_provenance is None
        or root_provenance.get("creator") != "ceo_intent"
        or root["parent_job_id"] is not None
        or root["root_job_id"] != root["job_id"]
    ):
        raise StateConflict("orchestration dispatch root is not strict CEO intent v2")
    if role == "aggregation":
        if (
            root["status"] != JobStatus.QUEUED.value
            or root["current_attempt_id"] is not None
            or root["cancel_requested_at_ms"] is not None
        ):
            raise StateConflict("aggregation dispatch requires an eligible queued root")
        _validated_aggregation_handoff(connection, job_row)
        return
    if job_row["parent_job_id"] != root["job_id"] or int(job_row["depth"]) != 1:
        raise StateConflict("orchestration dispatch target is outside the direct root subtree")
    if role == "plan":
        children = connection.execute(
            "SELECT job_id,orchestration_role FROM jobs WHERE parent_job_id=? ORDER BY job_id",
            (root["job_id"],),
        ).fetchall()
        admitted = connection.execute(
            "SELECT 1 FROM events WHERE event_type='COO_PLAN_ADMITTED' AND job_id=? LIMIT 1",
            (root["job_id"],),
        ).fetchone()
        if (
            root["status"] != JobStatus.QUEUED.value
            or root["current_attempt_id"] is not None
            or int(root["attempt_count"]) != 0
            or root["cancel_requested_at_ms"] is not None
            or len(children) != 1
            or children[0]["job_id"] != job_row["job_id"]
            or children[0]["orchestration_role"] != "plan"
            or admitted is not None
        ):
            raise StateConflict(
                "planner dispatch requires the unique sole pre-admission child of an eligible root"
            )
        return
    admission, plan_body = _validated_plan_admission(connection, root)
    revisions = _current_orchestration_tree_material_for_dispatch(
        connection, root, admission, plan_body
    )
    by_step = {str(item["plan_step_id"]): item for item in revisions}
    current = by_step.get(str(job_row["plan_step_id"]))
    if role in {"work", "repair"}:
        if current is None or current["current_job_id"] != job_row["job_id"]:
            raise StateConflict("dispatch target is not the current admitted revision")
        return
    if role == "review":
        if (
            current is None
            or not current["review_required"]
            or job_row["reviews_job_id"] != current["current_job_id"]
        ):
            raise StateConflict("review dispatch target is not current/admitted")
        return
    raise StateConflict("orchestration dispatch role is invalid")


def _assert_orchestration_requeue_eligible(
    connection: sqlite3.Connection, job_row: sqlite3.Row
) -> None:
    """Re-prove lineage for an adverse same-Job retry without requiring QUEUED."""

    role, provenance, _ = _decode_orchestration_job_fields(job_row)
    if role is None or provenance is None:
        raise StateConflict("requeue target is not a closed orchestration Job")
    root = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (job_row["root_job_id"],)
    ).fetchone()
    if root is None:
        raise StateConflict("orchestration requeue lost its strict-v2 root")
    root_role, root_provenance, _ = _decode_orchestration_job_fields(root)
    if (
        root_role != "aggregation"
        or root_provenance is None
        or root_provenance.get("creator") != "ceo_intent"
        or root["parent_job_id"] is not None
        or root["root_job_id"] != root["job_id"]
    ):
        raise StateConflict("orchestration requeue root is not strict CEO intent v2")
    if role == "aggregation":
        _validated_aggregation_handoff(connection, job_row)
        return
    if job_row["parent_job_id"] != root["job_id"] or int(job_row["depth"]) != 1:
        raise StateConflict("orchestration requeue target is outside the direct subtree")
    if role == "plan":
        children = connection.execute(
            "SELECT job_id,orchestration_role FROM jobs WHERE parent_job_id=? ORDER BY job_id",
            (root["job_id"],),
        ).fetchall()
        admitted = connection.execute(
            "SELECT 1 FROM events WHERE event_type='COO_PLAN_ADMITTED' AND job_id=? LIMIT 1",
            (root["job_id"],),
        ).fetchone()
        if (
            root["status"] != JobStatus.QUEUED.value
            or root["current_attempt_id"] is not None
            or int(root["attempt_count"]) != 0
            or root["cancel_requested_at_ms"] is not None
            or len(children) != 1
            or children[0]["job_id"] != job_row["job_id"]
            or children[0]["orchestration_role"] != "plan"
            or admitted is not None
        ):
            raise StateConflict("planner requeue phase is no longer current")
        return
    admission, plan_body = _validated_plan_admission(connection, root)
    revisions = _current_orchestration_tree_material_for_dispatch(
        connection, root, admission, plan_body
    )
    current = {
        str(item["plan_step_id"]): item for item in revisions
    }.get(str(job_row["plan_step_id"]))
    if role in {"work", "repair"}:
        if current is None or current["current_job_id"] != job_row["job_id"]:
            raise StateConflict("requeue target is not the current admitted revision")
        return
    if role == "review":
        if (
            current is None
            or not current["review_required"]
            or job_row["reviews_job_id"] != current["current_job_id"]
        ):
            raise StateConflict("review requeue target is not current/admitted")
        return
    raise StateConflict("orchestration requeue role is invalid")


def _assert_cycle_root_open_for_child_mutation(
    connection: sqlite3.Connection, root_row: sqlite3.Row
) -> None:
    """Require the pre-handoff, never-dispatched root phase for new child records."""

    if (
        root_row["status"] != JobStatus.QUEUED.value
        or root_row["current_attempt_id"] is not None
        or int(root_row["attempt_count"]) != 0
        or root_row["cancel_requested_at_ms"] is not None
    ):
        raise StateConflict("cycle root is not open for a new child mutation")
    advanced = connection.execute(
        """
        SELECT 1 FROM events
        WHERE job_id=? AND event_type IN ('COO_AGGREGATION_HANDOFF_READY','COO_CYCLE_BLOCKED')
        LIMIT 1
        """,
        (root_row["job_id"],),
    ).fetchone()
    if advanced is not None:
        raise StateConflict("cycle root already reached handoff or a blocked state")


def _insert_cycle_child(
    connection: sqlite3.Connection,
    store: RuntimeStore,
    *,
    root_row: sqlite3.Row,
    role: str,
    objective: str,
    requested_authorities: list[str],
    allowed_write_paths: list[str],
    validation_commands: list[list[str]],
    cost_class: str,
    attempt_limit: int,
    review_required: bool,
    command_id: str,
    plan_attempt_id: str,
    plan_digest: str,
    plan_step_id: str,
    repair_round: int,
    reviews_job_id: str | None = None,
    supersedes_job_id: str | None = None,
    provenance_source_id: str | None = None,
    provenance_source_digest: str | None = None,
    creation_evidence: dict[str, str] | None = None,
) -> sqlite3.Row:
    """Insert one cycle-owned direct child inside its caller's transaction."""

    policy = CooCyclePolicy.load()
    if role not in {"work", "review", "repair"}:
        raise StateConflict("cycle child insertion role is invalid")
    if _COMMAND_ID_RE.fullmatch(command_id) is None:
        raise StateConflict("cycle child command_id is invalid")
    root_constraints = _normalise_constraints(
        _strict_canonical_json_loads(
            str(root_row["constraints_json"]), name="root constraints"
        )
    )
    constraints = dict(root_constraints)
    constraints["cost_class"] = cost_class
    constraints = _normalise_constraints(constraints)
    try:
        authority = ExecutiveAuthorityPolicy.load().authorize(
            requested_authorities,
            worktree=root_row["worktree"],
            allowed_write_paths=allowed_write_paths,
            validation_commands=validation_commands,
        )
    except (AuthorityDenied, AuthorityPolicyError) as exc:
        raise StateConflict(f"cycle child authority is denied: {exc}") from exc
    _assert_child_does_not_widen_parent(
        root_row,
        requested=list(authority.requested),
        allowed_write_paths=list(authority.allowed_write_paths),
        constraints=constraints,
    )
    if cost_class not in policy.allowed_child_cost_classes:
        raise StateConflict("cycle child cost_class is outside policy")
    if role == "review":
        if (
            attempt_limit != policy.review_job_attempt_limit
            or "READ" not in authority.requested
            or set(authority.requested) - {"READ", "RUN_TESTS"}
            or authority.allowed_write_paths
        ):
            raise StateConflict("cycle review grant/Attempt limit is invalid")
    elif (
        attempt_limit > policy.max_attempts_per_orchestration_job
        or attempt_limit > int(root_row["attempt_limit"])
    ):
        raise StateConflict("cycle child Attempt limit exceeds policy/root")
    root_validations = _strict_canonical_json_loads(
        str(root_row["validation_commands_json"]), name="root validations"
    )
    child_validations = [list(item) for item in authority.validation_commands]
    if "RUN_TESTS" in authority.requested:
        if child_validations != root_validations:
            raise StateConflict("RUN_TESTS cycle child must inherit root validations")
    elif child_validations:
        raise StateConflict("cycle child without RUN_TESTS has validations")
    _assert_orchestration_lineage_for_create(
        connection,
        role=role,
        parent_row=root_row,
        plan_attempt_id=plan_attempt_id,
        plan_digest=plan_digest,
        plan_step_id=plan_step_id,
        repair_round=repair_round,
        reviews_job_id=reviews_job_id,
        supersedes_job_id=supersedes_job_id,
        rejected_review_job_id=(creation_evidence or {}).get(
            "rejected_review_job_id"
        ),
        rejected_review_result_digest=(creation_evidence or {}).get(
            "rejected_review_result_digest"
        ),
    )
    numbers = [
        int(match.group(1))
        for row in connection.execute("SELECT job_id FROM jobs")
        if (match := re.fullmatch(r"JOB-(\d+)", str(row[0])))
    ]
    job_id = f"JOB-{max(numbers, default=0) + 1:03d}"
    timestamp = store.now_ms()
    evidence = dict(creation_evidence or {})
    expected_evidence_keys = {
        "review": {"reviewed_result_digest"},
        "repair": {
            "rejected_review_job_id",
            "rejected_review_result_digest",
        },
        "work": set(),
    }[role]
    if set(evidence) != expected_evidence_keys or any(
        re.fullmatch(r"[0-9a-f]{64}", value) is None
        for key, value in evidence.items()
        if key.endswith("_digest")
    ):
        raise StateConflict("cycle child creation evidence is not the closed wire")
    source_id = provenance_source_id or str(root_row["job_id"])
    source_digest = provenance_source_digest or plan_digest
    if _COMMAND_ID_RE.fullmatch(source_id) is None or re.fullmatch(
        r"[0-9a-f]{64}", source_digest
    ) is None:
        raise StateConflict("cycle child provenance source is invalid")
    provenance = {
        "schema_version": "mastermind.executive_orchestration_provenance/v1",
        "creator": "coo_cycle",
        "source_id": source_id,
        "source_digest": source_digest,
        "command_id": command_id,
        "job_id": job_id,
        "parent_job_id": str(root_row["job_id"]),
        "root_job_id": str(root_row["job_id"]),
        "role": role,
    }
    provenance_digest = orchestration_digest(provenance)
    connection.execute(
        """
        INSERT INTO jobs(
          job_id,objective,department,priority,status,authority_level,branch,worktree,
          constraints_json,requested_authorities_json,authority_policy_hash,
          allowed_write_paths_json,validation_commands_json,attempt_limit,
          available_at_ms,created_at_ms,updated_at_ms,parent_job_id,root_job_id,depth,
          owner_seat,escalation_target,business_impact,review_required,reviews_job_id,
          orchestration_role,orchestration_provenance_json,
          orchestration_provenance_digest,plan_attempt_id,plan_digest,
          plan_step_id,repair_round,supersedes_job_id
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            job_id,
            objective,
            root_row["department"],
            int(root_row["priority"]),
            JobStatus.QUEUED.value,
            root_row["authority_level"],
            root_row["branch"],
            authority.worktree or root_row["worktree"],
            _json_dumps(constraints),
            _json_dumps(list(authority.requested)),
            authority.policy_sha256,
            _json_dumps(list(authority.allowed_write_paths)),
            _json_dumps(child_validations),
            int(attempt_limit),
            timestamp,
            timestamp,
            timestamp,
            root_row["job_id"],
            root_row["job_id"],
            1,
            "coo",
            "coo",
            root_row["business_impact"],
            int(review_required),
            reviews_job_id,
            role,
            _json_dumps(provenance),
            provenance_digest,
            plan_attempt_id,
            plan_digest,
            plan_step_id,
            repair_round,
            supersedes_job_id,
        ),
    )
    store.append_event(
        connection,
        aggregate_type="job",
        aggregate_id=job_id,
        event_type="JOB_CREATED",
        actor="coo",
        job_id=job_id,
        payload={
            "status": JobStatus.QUEUED.value,
            "parent_job_id": str(root_row["job_id"]),
            "root_job_id": str(root_row["job_id"]),
            "depth": 1,
            "owner_seat": "coo",
            "escalation_target": "coo",
            "business_impact": str(root_row["business_impact"]),
            "review_required": review_required,
            "reviews_job_id": reviews_job_id,
            "orchestration_role": role,
            "orchestration_provenance_digest": provenance_digest,
            "plan_attempt_id": plan_attempt_id,
            "plan_digest": plan_digest,
            "plan_step_id": plan_step_id,
            "repair_round": repair_round,
            "supersedes_job_id": supersedes_job_id,
            **evidence,
        },
        command_id=command_id,
        timestamp_ms=timestamp,
    )
    row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    assert row is not None
    return row


def _reconcile_cycle_child_creation(
    connection: sqlite3.Connection,
    *,
    event_row: sqlite3.Row,
    root_row: sqlite3.Row,
    role: str,
    objective: str,
    requested_authorities: list[str],
    allowed_write_paths: list[str],
    validation_commands: list[list[str]],
    cost_class: str,
    attempt_limit: int,
    review_required: bool,
    command_id: str,
    plan_attempt_id: str,
    plan_digest: str,
    plan_step_id: str,
    repair_round: int,
    reviews_job_id: str | None = None,
    supersedes_job_id: str | None = None,
    provenance_source_id: str | None = None,
    provenance_source_digest: str | None = None,
    creation_evidence: dict[str, str] | None = None,
) -> sqlite3.Row:
    """Reconcile one immutable child creation without consulting mutable phase state."""

    if (
        event_row["event_type"] != "JOB_CREATED"
        or event_row["command_id"] != command_id
        or event_row["actor"] != "coo"
        or event_row["aggregate_type"] != "job"
        or event_row["job_id"] is None
        or event_row["aggregate_id"] != event_row["job_id"]
    ):
        raise StateConflict("cycle child command is owned by another semantic action")
    row = connection.execute(
        "SELECT * FROM jobs WHERE job_id=?", (event_row["job_id"],)
    ).fetchone()
    if row is None:
        raise StateConflict("cycle child replay lost its Job")
    stored_role, provenance, provenance_digest = _decode_orchestration_job_fields(row)
    root_constraints = _normalise_constraints(
        _strict_canonical_json_loads(
            str(root_row["constraints_json"]), name="root constraints"
        )
    )
    expected_constraints = dict(root_constraints)
    expected_constraints["cost_class"] = cost_class
    expected_constraints = _normalise_constraints(expected_constraints)
    stored_authorities = _strict_canonical_json_loads(
        str(row["requested_authorities_json"]), name="cycle child authorities"
    )
    stored_paths = _strict_canonical_json_loads(
        str(row["allowed_write_paths_json"]), name="cycle child paths"
    )
    stored_validations = _strict_canonical_json_loads(
        str(row["validation_commands_json"]), name="cycle child validations"
    )
    stored_constraints = _strict_canonical_json_loads(
        str(row["constraints_json"]), name="cycle child constraints"
    )
    evidence = dict(creation_evidence or {})
    source_id = provenance_source_id or str(root_row["job_id"])
    source_digest = provenance_source_digest or plan_digest
    expected_payload: dict[str, Any] = {
        "status": JobStatus.QUEUED.value,
        "parent_job_id": str(root_row["job_id"]),
        "root_job_id": str(root_row["job_id"]),
        "depth": 1,
        "owner_seat": "coo",
        "escalation_target": "coo",
        "business_impact": str(root_row["business_impact"]),
        "review_required": review_required,
        "reviews_job_id": reviews_job_id,
        "orchestration_role": role,
        "orchestration_provenance_digest": provenance_digest,
        "plan_attempt_id": plan_attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": plan_step_id,
        "repair_round": repair_round,
        "supersedes_job_id": supersedes_job_id,
        **evidence,
    }
    payload = _strict_canonical_json_loads(
        str(event_row["payload_json"]), name="cycle child JOB_CREATED payload"
    )
    if (
        stored_role != role
        or not isinstance(provenance, dict)
        or provenance.get("creator") != "coo_cycle"
        or provenance.get("source_id") != source_id
        or provenance.get("source_digest") != source_digest
        or provenance.get("command_id") != command_id
        or row["objective"] != objective
        or row["department"] != root_row["department"]
        or row["priority"] != root_row["priority"]
        or row["authority_level"] != root_row["authority_level"]
        or row["branch"] != root_row["branch"]
        or row["parent_job_id"] != root_row["job_id"]
        or row["root_job_id"] != root_row["job_id"]
        or int(row["depth"]) != 1
        or row["owner_seat"] != "coo"
        or row["escalation_target"] != "coo"
        or row["business_impact"] != root_row["business_impact"]
        or bool(row["review_required"]) is not review_required
        or row["reviews_job_id"] != reviews_job_id
        or row["plan_attempt_id"] != plan_attempt_id
        or row["plan_digest"] != plan_digest
        or row["plan_step_id"] != plan_step_id
        or row["repair_round"] != repair_round
        or row["supersedes_job_id"] != supersedes_job_id
        or stored_authorities != requested_authorities
        or stored_paths != allowed_write_paths
        or stored_validations != validation_commands
        or stored_constraints != expected_constraints
        or int(row["attempt_limit"]) != int(attempt_limit)
        or payload != expected_payload
    ):
        raise StateConflict("cycle child command replay semantic payload drifted")
    return row


class JobRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def create_v2_orchestration_root(
        self,
        intent: dict[str, Any],
        *,
        fingerprint: str,
        command_id: str,
        workspace_root: str | Path | None,
        execution_binding: dict[str, Any] | None = None,
        dialogue_source: Mapping[str, Any] | None = None,
    ) -> Job:
        """The sole strict v2 intent -> Phase 1F-C aggregation-root boundary.

        Generic ``create_job`` refuses aggregation roots.  This method repeats
        the closed v2 validation/fingerprint and workspace fence, derives every
        Job field from that exact envelope, and passes an unforgeable in-process
        capability only for the final atomic Job/Event transaction.
        """

        from control_plane.ceo_intent import (  # local: avoids import cycle
            INTENT_SCHEMA_V2,
            command_id_for,
            intent_fingerprint,
            validate_intent,
        )

        normalized = validate_intent(intent)
        if normalized.get("schema") != INTENT_SCHEMA_V2:
            raise StateConflict("only strict mastermind.ceo_intent.v2 may create a COO root")
        expected_fingerprint = intent_fingerprint(normalized)
        if fingerprint != expected_fingerprint:
            raise StateConflict("v2 COO root fingerprint does not bind the exact intent")
        if command_id != command_id_for(str(normalized["intent_id"])):
            raise StateConflict("v2 COO root command_id is not intent-derived")
        contract = normalized["execution_contract"]
        constraints = dict(contract.get("constraints") or {})
        if execution_binding is not None:
            if not isinstance(execution_binding, dict) or set(execution_binding) != set(
                V2_HOST_EXECUTION_BINDING_KEYS
            ):
                raise StateConflict(
                    "v2 host execution binding fields are incomplete or drifted"
                )
            bound = _normalise_constraints(execution_binding)
            if set(bound) != set(V2_HOST_EXECUTION_BINDING_KEYS):
                raise StateConflict("v2 host execution binding did not normalize exactly")
            normalized_caller = _normalise_constraints(constraints)
            for key in set(constraints) & set(bound):
                if normalized_caller.get(key) != bound[key]:
                    raise StateConflict(
                        f"caller constraint {key} conflicts with reviewed host composition"
                    )
            normalized_caller.update(bound)
            constraints = _normalise_constraints(normalized_caller)
        worktree = contract.get("worktree")
        if worktree is not None:
            if workspace_root is None:
                raise StateConflict("v2 COO root worktree requires a reviewed workspace root")
            resolved = Path(worktree).expanduser().resolve(strict=False)
            root = Path(workspace_root).expanduser().resolve(strict=False)
            if root not in resolved.parents:
                raise StateConflict("v2 COO root worktree is outside the reviewed workspace root")
        provenance: dict[str, Any] = {
            "schema": INTENT_SCHEMA_V2,
            "intent_id": normalized["intent_id"],
            "actor": normalized["actor"],
            "fingerprint": fingerprint,
            "grounding": dict(normalized["grounding"]),
        }
        if "workstream" in normalized:
            provenance["workstream"] = normalized["workstream"]
        if dialogue_source is not None:
            work_ref = normalized.get("workstream")
            if not isinstance(work_ref, str):
                raise StateConflict(
                    "v2 dialogue source requires the intent's exact workstream"
                )
            normalized_source = normalize_executive_dialogue_source(
                dialogue_source,
                work_ref=work_ref,
            ).to_dict()
            provenance["dialogue_source"] = normalized_source
            provenance["dialogue_source_digest"] = hashlib.sha256(
                json.dumps(
                    normalized_source,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        return self.create_job(
            normalized["objective"],
            department=normalized["department"],
            priority=normalized["priority"],
            authority_level=contract.get("authority_level", "A0"),
            branch=contract.get("branch"),
            worktree=worktree,
            constraints=constraints,
            attempt_limit=contract["attempt_limit"],
            requested_authorities=contract["requested_authorities"],
            allowed_write_paths=contract.get("allowed_write_paths"),
            validation_commands=contract.get("validation_commands"),
            command_id=command_id,
            provenance=provenance,
            business_impact=normalized["business_impact"],
            orchestration_role="aggregation",
            orchestration_provenance={
                "schema_version": (
                    "mastermind.executive_orchestration_provenance_source/v1"
                ),
                "creator": "ceo_intent",
                "source_id": normalized["intent_id"],
                "source_digest": fingerprint,
            },
            _v2_root_capability=_V2_ROOT_CREATION_CAPABILITY,
        )

    def create_cycle_planner(
        self,
        root_job_id: str,
        *,
        command_id: str,
    ) -> Job:
        """Create or reconcile the sole deterministic planner child.

        This is intentionally narrower than ``create_job``.  The latter cannot
        create a Phase 1F-C planner directly: the cycle-owned path re-proves the
        strict-v2 root, absence of children and absence of plan admission inside
        the insertion transaction.  The deterministic command is the replay
        identity and is also bound into the immutable child provenance.
        """

        root_token = str(root_job_id or "").strip()
        expected_command = f"coo-cycle:{root_token}:create-planner:0"
        if command_id != expected_command:
            raise StateConflict("planner command_id is not exact-root deterministic")
        root = self.get_job(root_token)
        if root is None:
            raise StateConflict(f"root job {root_token!r} does not exist")
        if (
            root.orchestration_role != "aggregation"
            or root.parent_job_id is not None
            or root.root_job_id != root.job_id
            or not isinstance(root.orchestration_provenance, dict)
            or root.orchestration_provenance.get("creator") != "ceo_intent"
        ):
            raise StateConflict("planner creation requires a strict v2 aggregation root")
        root_constraints = dict(root.constraints)
        root_cost = str(root_constraints.get("cost_class") or "default")
        cost_class = "small" if root_cost in {"small", "default", "frontier"} else "small"
        operator_binding = {
            "eligible_quota_classes": root_constraints.get(
                "operator_eligible_quota_classes"
            ),
            "provider": root_constraints.get("operator_provider"),
            "model": root_constraints.get("operator_model"),
            "effort": root_constraints.get("operator_effort"),
            "cost_class": root_constraints.get("operator_cost_class"),
            "routing_policy_version": root_constraints.get(
                "operator_routing_policy_version"
            ),
            "execution_profile_id": root_constraints.get(
                "operator_execution_profile_id"
            ),
            "execution_profile_digest": root_constraints.get(
                "operator_execution_profile_digest"
            ),
            "capability_policy_version": root_constraints.get(
                "operator_capability_policy_version"
            ),
            "capability_policy_digest": root_constraints.get(
                "operator_capability_policy_digest"
            ),
            "harness_binary_digest": root_constraints.get(
                "operator_harness_binary_digest"
            ),
            "harness_version": root_constraints.get("operator_harness_version"),
            "base_sha": root_constraints.get("base_sha"),
        }
        if root_constraints.get("operator_harness_armed") is True and all(
            operator_binding.values()
        ):
            constraints = _normalise_constraints(operator_binding)
        else:
            constraints = {
                "eligible_quota_classes": list(
                    root_constraints.get("eligible_quota_classes") or ["default"]
                ),
                "cost_class": cost_class,
            }
            for key in (
                "provider",
                "model",
                "effort",
                "routing_policy_version",
                "execution_profile_id",
                "execution_profile_digest",
                "capability_policy_version",
                "capability_policy_digest",
                "base_sha",
            ):
                if root_constraints.get(key):
                    constraints[key] = root_constraints[key]
        return self.create_job(
            f"Produce the bounded execution plan for {root.job_id}: {root.objective}",
            department=root.department,
            priority=root.priority,
            authority_level=root.authority_level,
            branch=root.branch,
            worktree=root.worktree,
            constraints=constraints,
            attempt_limit=min(root.attempt_limit, CooCyclePolicy.load().max_attempts_per_orchestration_job),
            requested_authorities=["READ"],
            allowed_write_paths=[],
            validation_commands=[],
            command_id=command_id,
            parent_job_id=root.job_id,
            owner_seat="coo",
            escalation_target="coo",
            business_impact=root.business_impact,
            review_required=False,
            orchestration_role="plan",
            orchestration_provenance={
                "schema_version": "mastermind.executive_orchestration_provenance_source/v1",
                "creator": "coo_cycle",
                "source_id": root.job_id,
                "source_digest": str(root.orchestration_provenance_digest),
            },
            _coo_cycle_planner_capability=_COO_CYCLE_PLANNER_CREATION_CAPABILITY,
        )

    def admit_cycle_plan(
        self,
        root_job_id: str,
        *,
        command_id: str,
    ) -> list[Job]:
        """Atomically reserve the sealed plan and create its initial work wave."""

        root_token = str(root_job_id or "").strip()
        timestamp = self.store.now_ms()
        created_ids: list[str] = []
        with self.store.transaction() as connection:
            root = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_token,)
            ).fetchone()
            if root is None:
                raise StateConflict("plan admission root does not exist")
            role, provenance, _ = _decode_orchestration_job_fields(root)
            if (
                role != "aggregation"
                or provenance is None
                or provenance.get("creator") != "ceo_intent"
                or root["root_job_id"] != root["job_id"]
            ):
                raise StateConflict("plan admission requires a strict-v2 root")
            existing_command = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing_command is not None:
                if (
                    existing_command["event_type"] != "COO_PLAN_ADMITTED"
                    or existing_command["job_id"] != root_token
                ):
                    raise StateConflict("plan-admission command is owned by another action")
                admission, _plan = _validated_plan_admission(connection, root)
                reconciled: list[Job] = []
                for step in admission["steps"]:
                    member = connection.execute(
                        "SELECT * FROM jobs WHERE job_id=?", (step["work_job_id"],)
                    ).fetchone()
                    if member is None:
                        raise StateConflict("plan-admission replay lost a batch member")
                    reconciled.append(_job_from_row(member))
                return reconciled
            if (
                root["status"] != JobStatus.QUEUED.value
                or root["current_attempt_id"] is not None
                or int(root["attempt_count"]) != 0
                or root["cancel_requested_at_ms"] is not None
            ):
                raise StateConflict("plan admission requires an eligible strict-v2 root")
            _assert_cycle_root_open_for_child_mutation(connection, root)
            prior = connection.execute(
                "SELECT 1 FROM events WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?",
                (root_token,),
            ).fetchone()
            if prior is not None:
                raise StateConflict("root already has a different plan admission")
            children = connection.execute(
                "SELECT * FROM jobs WHERE parent_job_id=? ORDER BY job_id",
                (root_token,),
            ).fetchall()
            if len(children) != 1 or children[0]["orchestration_role"] != "plan":
                raise StateConflict(
                    "plan admission requires exactly one planner and no other child"
                )
            planner = children[0]
            plan_attempt = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (planner["current_attempt_id"],),
            ).fetchone()
            if (
                planner["status"] != JobStatus.COMPLETED.value
                or plan_attempt is None
                or plan_attempt["status"] != AttemptStatus.COMPLETED.value
            ):
                raise StateConflict("plan admission requires a completed planner")
            expected_command = (
                f"coo-cycle:{root_token}:admit-plan:{plan_attempt['attempt_id']}"
            )
            if command_id != expected_command:
                raise StateConflict("plan-admission command_id is not deterministic")
            seal = _validated_orchestration_role_result_payload(
                connection,
                attempt_row=plan_attempt,
                expected_role="plan",
            )
            _orchestration_terminal_receipt(
                connection,
                attempt_id=str(plan_attempt["attempt_id"]),
                expected_role="plan",
                seal=seal,
            )
            try:
                from control_plane.executive_orchestration_result import (
                    canonical_digest as result_digest,
                    validate_envelope,
                )

                envelope = validate_envelope(
                    seal["result_envelope"],
                    expected_job_id=str(planner["job_id"]),
                    expected_run_id=str(plan_attempt["attempt_id"]),
                    expected_worker_id=str(plan_attempt["worker_id"]),
                    expected_role="plan",
                    expected_root_job_id=root_token,
                )
            except Exception as exc:
                raise StateConflict(f"typed plan is invalid: {exc}") from exc
            plan_body = dict(envelope["role_result"])
            plan_digest = result_digest(plan_body)
            if plan_digest != seal["role_result_digest"]:
                raise StateConflict("typed plan digest differs from its seal")
            policy = CooCyclePolicy.load()
            requirements = tuple(
                bool(
                    step["review_required"]
                    or root["business_impact"] in {"material", "critical"}
                    or step["business_impact"] in {"material", "critical"}
                )
                for step in plan_body["steps"]
            )
            try:
                reserved_total = policy.reserved_children_total(requirements)
            except CooCyclePolicyError as exc:
                raise StateConflict(f"plan capacity exceeds policy: {exc}") from exc
            root_validations = _strict_canonical_json_loads(
                str(root["validation_commands_json"]), name="root validations"
            )
            root_validation_ids = [
                orchestration_digest(argv) for argv in root_validations
            ]
            reservation_steps: list[dict[str, Any]] = []
            for ordinal, step in enumerate(plan_body["steps"]):
                has_tests = "RUN_TESTS" in step["requested_authorities"]
                if step["validation_ids"] != (
                    root_validation_ids if has_tests else []
                ):
                    raise StateConflict(
                        "plan step validation IDs do not equal the reviewed root set"
                    )
                member_command = f"{command_id}:member:{ordinal}"
                member = _insert_cycle_child(
                    connection,
                    self.store,
                    root_row=root,
                    role="work",
                    objective=str(step["objective"]),
                    requested_authorities=list(step["requested_authorities"]),
                    allowed_write_paths=list(step["allowed_write_paths"]),
                    validation_commands=root_validations if has_tests else [],
                    cost_class=str(step["cost_class"]),
                    attempt_limit=int(step["attempt_limit"]),
                    review_required=requirements[ordinal],
                    command_id=member_command,
                    plan_attempt_id=str(plan_attempt["attempt_id"]),
                    plan_digest=plan_digest,
                    plan_step_id=str(step["step_id"]),
                    repair_round=0,
                )
                created_ids.append(str(member["job_id"]))
                reservation_steps.append(
                    {
                        "ordinal": ordinal,
                        "plan_step_id": str(step["step_id"]),
                        "step_slots": policy.reserved_step_slots(
                            review_required=requirements[ordinal]
                        ),
                        "review_required": requirements[ordinal],
                        "work_job_id": str(member["job_id"]),
                        "member_command_id": member_command,
                    }
                )
            admission: dict[str, Any] = {
                "schema_version": "mastermind.coo_plan_admission/v1",
                "root_job_id": root_token,
                "policy_sha": policy.policy_sha256,
                "plan_attempt_id": str(plan_attempt["attempt_id"]),
                "plan_digest": plan_digest,
                "steps": reservation_steps,
                "reserved_children_total": reserved_total,
                "command_id": command_id,
            }
            admission["reservation_digest"] = orchestration_digest(admission)
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=root_token,
                event_type="COO_PLAN_ADMITTED",
                actor="coo",
                job_id=root_token,
                attempt_id=str(plan_attempt["attempt_id"]),
                payload=admission,
                command_id=command_id,
                timestamp_ms=timestamp,
            )
            _validated_plan_admission(connection, root)
        return [self.get_job(job_id) for job_id in created_ids if self.get_job(job_id)]

    def create_cycle_review(
        self,
        root_job_id: str,
        reviewed_job_id: str,
        *,
        command_id: str,
    ) -> Job:
        """Create/reconcile one reserved review Job for the current revision."""

        created_id: str | None = None
        with self.store.transaction() as connection:
            root = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_job_id,)
            ).fetchone()
            reviewed = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (reviewed_job_id,)
            ).fetchone()
            if root is None or reviewed is None:
                raise StateConflict("review root/revision is unavailable")
            admission, plan_body = _validated_plan_admission(connection, root)
            reviewed_attempt, _seal, _terminal, reviewed_result_digest = (
                _validated_role_completion_material(
                    connection,
                    job_row=reviewed,
                    expected_role=str(reviewed["orchestration_role"]),
                    root_job_id=root_job_id,
                )
            )
            step = next(
                (
                    item
                    for item in plan_body["steps"]
                    if item["step_id"] == reviewed["plan_step_id"]
                ),
                None,
            )
            if step is None:
                raise StateConflict("review target is absent from the admitted plan")
            has_tests = "RUN_TESTS" in step["requested_authorities"]
            review_authorities = ["READ", *(["RUN_TESTS"] if has_tests else [])]
            root_validations = _strict_canonical_json_loads(
                str(root["validation_commands_json"]), name="root validations"
            )
            review_validations = root_validations if has_tests else []
            policy = CooCyclePolicy.load()
            reviews = connection.execute(
                "SELECT * FROM jobs WHERE reviews_job_id=? ORDER BY job_id",
                (reviewed_job_id,),
            ).fetchall()
            ordinal = len(reviews) + 1
            expected_command = (
                f"coo-cycle:{root_job_id}:create-review:{reviewed_job_id}:{ordinal}"
            )
            existing = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing is not None:
                existing_job = connection.execute(
                    "SELECT * FROM jobs WHERE job_id=?", (existing["job_id"],)
                ).fetchone()
                if existing_job is None:
                    raise StateConflict("review command replay lost its Job")
                ordered_review_events = connection.execute(
                    """
                    SELECT e.event_id,e.job_id FROM events e
                    JOIN jobs j ON j.job_id=e.job_id
                    WHERE e.event_type='JOB_CREATED' AND e.actor='coo'
                      AND j.orchestration_role='review' AND j.reviews_job_id=?
                    ORDER BY e.event_id
                    """,
                    (reviewed_job_id,),
                ).fetchall()
                positions = {
                    str(item["job_id"]): index
                    for index, item in enumerate(ordered_review_events, start=1)
                }
                existing_ordinal = positions.get(str(existing_job["job_id"]))
                if existing_ordinal is None:
                    raise StateConflict("review command replay lost its creation order")
                replay_command = (
                    f"coo-cycle:{root_job_id}:create-review:"
                    f"{reviewed_job_id}:{existing_ordinal}"
                )
                if command_id != replay_command:
                    raise StateConflict("review command replay ordinal drifted")
                row = _reconcile_cycle_child_creation(
                    connection,
                    event_row=existing,
                    root_row=root,
                    role="review",
                    objective=(
                        f"Independently review {reviewed_job_id}: {reviewed['objective']}"
                    ),
                    requested_authorities=review_authorities,
                    allowed_write_paths=[],
                    validation_commands=review_validations,
                    cost_class=str(step["cost_class"]),
                    attempt_limit=policy.review_job_attempt_limit,
                    review_required=False,
                    command_id=command_id,
                    plan_attempt_id=str(admission["plan_attempt_id"]),
                    plan_digest=str(admission["plan_digest"]),
                    plan_step_id=str(step["step_id"]),
                    repair_round=int(reviewed["repair_round"]),
                    reviews_job_id=reviewed_job_id,
                    provenance_source_id=reviewed_job_id,
                    provenance_source_digest=reviewed_result_digest,
                    creation_evidence={
                        "reviewed_result_digest": reviewed_result_digest
                    },
                )
                return _job_from_row(row)
            _assert_cycle_root_open_for_child_mutation(connection, root)
            current = {
                item["plan_step_id"]: item
                for item in _current_orchestration_tree_material_for_dispatch(
                    connection, root, admission, plan_body
                )
            }.get(str(reviewed["plan_step_id"]))
            if (
                current is None
                or current["current_job_id"] != reviewed_job_id
                or not current["review_required"]
                or reviewed["status"] != JobStatus.COMPLETED.value
            ):
                raise StateConflict("review creation target is not current/completed/required")
            if len(reviews) >= policy.max_review_attempts_per_job:
                raise StateConflict("review Job record ceiling is exhausted")
            if reviews:
                prior = reviews[0]
                prior_status = JobStatus(prior["status"])
                replaceable = prior_status == JobStatus.CANCELLED or (
                    prior_status
                    in {JobStatus.RATE_LIMITED, JobStatus.FAILED, JobStatus.LOST}
                    and int(prior["attempt_count"]) >= int(prior["attempt_limit"])
                )
                if prior_status == JobStatus.COMPLETED:
                    prior_attempt, _prior_seal, _prior_terminal, _prior_digest = (
                        _validated_role_completion_material(
                            connection,
                            job_row=prior,
                            expected_role="review",
                            root_job_id=root_job_id,
                        )
                    )
                    replaceable = not _review_attempt_is_independent(
                        connection,
                        review_attempt_id=str(prior_attempt["attempt_id"]),
                        reviewed_attempt_id=str(reviewed_attempt["attempt_id"]),
                    )
                if not replaceable:
                    raise StateConflict(
                        "replacement review requires one closed adverse or VOID review"
                    )
            if command_id != expected_command:
                raise StateConflict("review creation command_id is not deterministic")
            row = _insert_cycle_child(
                connection,
                self.store,
                root_row=root,
                role="review",
                objective=f"Independently review {reviewed_job_id}: {reviewed['objective']}",
                requested_authorities=review_authorities,
                allowed_write_paths=[],
                validation_commands=review_validations,
                cost_class=str(step["cost_class"]),
                attempt_limit=policy.review_job_attempt_limit,
                review_required=False,
                command_id=command_id,
                plan_attempt_id=str(admission["plan_attempt_id"]),
                plan_digest=str(admission["plan_digest"]),
                plan_step_id=str(step["step_id"]),
                repair_round=int(reviewed["repair_round"]),
                reviews_job_id=reviewed_job_id,
                provenance_source_id=reviewed_job_id,
                provenance_source_digest=reviewed_result_digest,
                creation_evidence={
                    "reviewed_result_digest": reviewed_result_digest
                },
            )
            created_id = str(row["job_id"])
        result = self.get_job(str(created_id))
        assert result is not None
        return result

    def create_cycle_repair(
        self,
        root_job_id: str,
        rejected_job_id: str,
        rejecting_review_job_id: str,
        *,
        command_id: str,
    ) -> Job:
        """Create/reconcile the next reserved repair for an independent reject."""

        created_id: str | None = None
        with self.store.transaction() as connection:
            root = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_job_id,)
            ).fetchone()
            rejected = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (rejected_job_id,)
            ).fetchone()
            rejecting_review = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (rejecting_review_job_id,)
            ).fetchone()
            if root is None or rejected is None or rejecting_review is None:
                raise StateConflict("repair root/revision/rejecting review is unavailable")
            admission, plan_body = _validated_plan_admission(connection, root)
            rejected_attempt, _work_seal, _work_terminal, rejected_result_digest = (
                _validated_role_completion_material(
                    connection,
                    job_row=rejected,
                    expected_role=str(rejected["orchestration_role"]),
                    root_job_id=root_job_id,
                )
            )
            review_attempt, review_seal, _review_terminal, review_result_digest = (
                _validated_role_completion_material(
                    connection,
                    job_row=rejecting_review,
                    expected_role="review",
                    root_job_id=root_job_id,
                )
            )
            review_body = review_seal["result_envelope"]["role_result"]
            if (
                rejecting_review["reviews_job_id"] != rejected_job_id
                or review_body.get("verdict") != "reject"
                or review_body.get("reviewed_job_id") != rejected_job_id
                or review_body.get("reviewed_attempt_id")
                != rejected_attempt["attempt_id"]
                or review_body.get("reviewed_result_digest")
                != rejected_result_digest
                or not _review_attempt_is_independent(
                    connection,
                    review_attempt_id=str(review_attempt["attempt_id"]),
                    reviewed_attempt_id=str(rejected_attempt["attempt_id"]),
                )
            ):
                raise StateConflict("repair requires the exact independent rejecting review")
            step = next(
                (
                    item
                    for item in plan_body["steps"]
                    if item["step_id"] == rejected["plan_step_id"]
                ),
                None,
            )
            if step is None:
                raise StateConflict("repair target is absent from the admitted plan")
            next_round = int(rejected["repair_round"]) + 1
            has_tests = "RUN_TESTS" in step["requested_authorities"]
            root_validations = _strict_canonical_json_loads(
                str(root["validation_commands_json"]), name="root validations"
            )
            repair_validations = root_validations if has_tests else []
            expected_command = (
                f"coo-cycle:{root_job_id}:create-repair:{rejected_job_id}:"
                f"{rejecting_review_job_id}:{review_result_digest}:{next_round}"
            )
            existing = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing is not None:
                if command_id != expected_command:
                    raise StateConflict("repair command replay semantic key drifted")
                row = _reconcile_cycle_child_creation(
                    connection,
                    event_row=existing,
                    root_row=root,
                    role="repair",
                    objective=f"Repair {rejected_job_id}: {step['objective']}",
                    requested_authorities=list(step["requested_authorities"]),
                    allowed_write_paths=list(step["allowed_write_paths"]),
                    validation_commands=repair_validations,
                    cost_class=str(step["cost_class"]),
                    attempt_limit=int(step["attempt_limit"]),
                    review_required=bool(
                        next(
                            item["review_required"]
                            for item in admission["steps"]
                            if item["plan_step_id"] == step["step_id"]
                        )
                    ),
                    command_id=command_id,
                    plan_attempt_id=str(admission["plan_attempt_id"]),
                    plan_digest=str(admission["plan_digest"]),
                    plan_step_id=str(step["step_id"]),
                    repair_round=next_round,
                    supersedes_job_id=rejected_job_id,
                    provenance_source_id=rejecting_review_job_id,
                    provenance_source_digest=review_result_digest,
                    creation_evidence={
                        "rejected_review_job_id": rejecting_review_job_id,
                        "rejected_review_result_digest": review_result_digest,
                    },
                )
                return _job_from_row(row)
            _assert_cycle_root_open_for_child_mutation(connection, root)
            current = {
                item["plan_step_id"]: item
                for item in _current_orchestration_tree_material_for_dispatch(
                    connection, root, admission, plan_body
                )
            }.get(str(rejected["plan_step_id"]))
            policy = CooCyclePolicy.load()
            if (
                current is None
                or current["current_job_id"] != rejected_job_id
                or next_round > policy.max_repair_rounds
            ):
                raise StateConflict("repair target is not current or rounds are exhausted")
            if command_id != expected_command:
                raise StateConflict("repair creation command_id is not deterministic")
            row = _insert_cycle_child(
                connection,
                self.store,
                root_row=root,
                role="repair",
                objective=f"Repair {rejected_job_id}: {step['objective']}",
                requested_authorities=list(step["requested_authorities"]),
                allowed_write_paths=list(step["allowed_write_paths"]),
                validation_commands=repair_validations,
                cost_class=str(step["cost_class"]),
                attempt_limit=int(step["attempt_limit"]),
                review_required=bool(current["review_required"]),
                command_id=command_id,
                plan_attempt_id=str(admission["plan_attempt_id"]),
                plan_digest=str(admission["plan_digest"]),
                plan_step_id=str(step["step_id"]),
                repair_round=next_round,
                supersedes_job_id=rejected_job_id,
                provenance_source_id=rejecting_review_job_id,
                provenance_source_digest=review_result_digest,
                creation_evidence={
                    "rejected_review_job_id": rejecting_review_job_id,
                    "rejected_review_result_digest": review_result_digest,
                },
            )
            created_id = str(row["job_id"])
        result = self.get_job(str(created_id))
        assert result is not None
        return result

    def create_cycle_handoff(
        self,
        root_job_id: str,
        *,
        command_id: str,
    ) -> dict[str, Any]:
        """Append or reconcile the sole provider-neutral aggregation handoff."""

        root_token = str(root_job_id or "").strip()
        expected_command = f"coo-cycle:{root_token}:aggregation-handoff:1"
        if command_id != expected_command:
            raise StateConflict("aggregation handoff command_id is not deterministic")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            root = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_token,)
            ).fetchone()
            if root is None:
                raise StateConflict("aggregation handoff root does not exist")
            role, provenance, _ = _decode_orchestration_job_fields(root)
            if (
                role != "aggregation"
                or provenance is None
                or provenance.get("creator") != "ceo_intent"
                or root["parent_job_id"] is not None
                or root["root_job_id"] != root["job_id"]
            ):
                raise StateConflict("aggregation handoff requires a strict-v2 root")
            existing = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["event_type"] != "COO_AGGREGATION_HANDOFF_READY"
                    or existing["job_id"] != root_token
                    or existing["aggregate_type"] != "job"
                    or existing["aggregate_id"] != root_token
                ):
                    raise StateConflict("handoff command is owned by another action")
                return _validated_aggregation_handoff(connection, root)
            prior = connection.execute(
                """
                SELECT 1 FROM events
                WHERE event_type='COO_AGGREGATION_HANDOFF_READY' AND job_id=?
                """,
                (root_token,),
            ).fetchone()
            if prior is not None:
                raise StateConflict("aggregation root already has a different handoff")
            _assert_cycle_root_open_for_child_mutation(connection, root)
            admission, plan_body = _validated_plan_admission(connection, root)
            revisions, rejected_history = _current_orchestration_tree_material(
                connection, root, admission, plan_body
            )
            handoff: dict[str, Any] = {
                "schema_version": "mastermind.aggregation_handoff/v1",
                "root_job_id": root_token,
                "policy_sha": admission["policy_sha"],
                "plan_attempt_id": admission["plan_attempt_id"],
                "plan_digest": admission["plan_digest"],
                "reservation_digest": admission["reservation_digest"],
                "revisions": revisions,
                "rejected_history": rejected_history,
                "aggregate_result_schema": "mastermind.aggregation_result/v1",
                "allowed_evidence_reads": ["attempts", "events", "jobs"],
                "command_id": command_id,
            }
            handoff["handoff_digest"] = orchestration_digest(handoff)
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=root_token,
                event_type="COO_AGGREGATION_HANDOFF_READY",
                actor="coo",
                job_id=root_token,
                attempt_id=str(admission["plan_attempt_id"]),
                payload=handoff,
                command_id=command_id,
                timestamp_ms=timestamp,
            )
            return _validated_aggregation_handoff(connection, root)

    def project_retry_safety(
        self, job_id: str, *, expected_attempt_id: str
    ) -> RetrySafetyProjection:
        """Return a read-only retry expectation from one exact snapshot."""

        with self.store.read() as connection:
            return _retry_safety_material(
                connection,
                job_id=str(job_id or "").strip(),
                expected_attempt_id=str(expected_attempt_id or "").strip(),
            ).projection

    @staticmethod
    def _retry_safety_receipt(
        projection: RetrySafetyProjection,
        decision: RetrySafetyDecision,
    ) -> dict[str, Any]:
        return {
            "schema_version": "mastermind.executive_retry_safety_receipt/v1",
            "decision": decision.value,
            "evidence": projection.evidence.to_dict(),
            "evidence_digest": projection.retry_evidence_digest,
        }

    @staticmethod
    def _retry_reconciliation(
        *,
        command_id: str,
        reason: str,
        expectation: RetrySafetyProjection,
        observed: RetrySafetyProjection | None,
    ) -> CooRetryMutationOutcome:
        return CooRetryMutationOutcome(
            action="RECONCILIATION_REQUIRED",
            command_id=command_id,
            receipt={
                "schema_version": "mastermind.executive_retry_reconciliation/v1",
                "decision": RetrySafetyDecision.NEEDS_RECONCILIATION.value,
                "effect_state": "NONE",
                "reason": reason,
                "expected": {
                    "attempt_id": expectation.attempt_id,
                    "requeue_kind": expectation.requeue_kind,
                    "tx9_evidence_digest": expectation.tx9_evidence_digest,
                    "retry_evidence_digest": expectation.retry_evidence_digest,
                },
                "observed": (
                    None
                    if observed is None
                    else {
                        "attempt_id": observed.attempt_id,
                        "requeue_kind": observed.requeue_kind,
                        "tx9_evidence_digest": observed.tx9_evidence_digest,
                        "retry_evidence_digest": observed.retry_evidence_digest,
                    }
                ),
            },
        )

    def commit_coo_retry_decision(
        self,
        root_job_id: str,
        *,
        selected_job_id: str,
        expectation: RetrySafetyProjection,
        policy_sha: str | None = None,
    ) -> CooRetryMutationOutcome:
        """Atomically rederive, classify, and commit one COO retry decision."""

        root_token = str(root_job_id or "").strip()
        selected_token = str(selected_job_id or "").strip()
        attempt_token = str(expectation.attempt_id or "").strip()
        requeue_command = (
            f"coo-cycle:{root_token}:requeue:{selected_token}:{attempt_token}"
        )
        block_command = f"coo-cycle:{root_token}:block:state_conflict:{selected_token}"
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            # Exact command receipts are reconciled before any mutable Job read.
            existing_requeue = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (requeue_command,)
            ).fetchone()
            if existing_requeue is not None:
                outcome = _requeue_outcome_from_event(
                    connection, existing_requeue, expected_job_id=selected_token
                )
                stored = outcome.payload.get("retry_safety")
                if (
                    not isinstance(stored, dict)
                    or stored.get("evidence_digest")
                    != expectation.retry_evidence_digest
                    or outcome.payload.get("invalidated_attempt_id") != attempt_token
                    or outcome.payload.get("requeue_kind") != expectation.requeue_kind
                    or outcome.payload.get("tx9_evidence_digest")
                    != expectation.tx9_evidence_digest
                ):
                    return self._retry_reconciliation(
                        command_id=requeue_command,
                        reason="command_expectation_conflict",
                        expectation=expectation,
                        observed=None,
                    )
                receipt = outcome.to_dict()
                receipt["retry_safety"] = stored
                return CooRetryMutationOutcome(
                    action="REQUEUED",
                    command_id=requeue_command,
                    receipt=receipt,
                )

            existing_block = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (block_command,)
            ).fetchone()
            if existing_block is not None:
                payload = _validated_coo_cycle_block_event(
                    connection,
                    existing_block,
                    expected_root_id=root_token,
                )
                if payload["selected_job_id"] != selected_token:
                    raise StateConflict("COO block command is owned by another target")
                stored_retry = payload["evidence"].get("retry_safety")
                if (
                    not isinstance(stored_retry, dict)
                    or stored_retry.get("evidence_digest")
                    != expectation.retry_evidence_digest
                ):
                    return self._retry_reconciliation(
                        command_id=block_command,
                        reason="command_expectation_conflict",
                        expectation=expectation,
                        observed=None,
                    )
                return CooRetryMutationOutcome(
                    action="BLOCKED", command_id=block_command, receipt=payload
                )

            material = _retry_safety_material(
                connection,
                job_id=selected_token,
                expected_attempt_id=attempt_token,
            )
            observed = material.projection
            if (
                expectation.retry_evidence_digest
                != expectation.evidence.evidence_digest
                or expectation.attempt_id != observed.attempt_id
                or expectation.requeue_kind != observed.requeue_kind
                or expectation.tx9_evidence_digest != observed.tx9_evidence_digest
                or expectation.retry_evidence_digest
                != observed.retry_evidence_digest
            ):
                return self._retry_reconciliation(
                    command_id=requeue_command,
                    reason="retry_expectation_drift",
                    expectation=expectation,
                    observed=observed,
                )
            decision = classify_retry_safety(observed.evidence)
            retry_receipt = self._retry_safety_receipt(observed, decision)

            root = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_token,)
            ).fetchone()
            selected = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (selected_token,)
            ).fetchone()
            if (
                root is None
                or selected is None
                or root["root_job_id"] != root_token
                or root["orchestration_role"] != "aggregation"
                or selected["root_job_id"] != root_token
                or selected["current_attempt_id"] != attempt_token
            ):
                return self._retry_reconciliation(
                    command_id=requeue_command,
                    reason="retry_target_drift",
                    expectation=expectation,
                    observed=observed,
                )

            prior_block = connection.execute(
                """
                SELECT 1 FROM events
                WHERE event_type='COO_CYCLE_BLOCKED' AND job_id=? LIMIT 1
                """,
                (root_token,),
            ).fetchone()
            if prior_block is not None:
                return self._retry_reconciliation(
                    command_id=requeue_command,
                    reason="prior_block_drift",
                    expectation=expectation,
                    observed=observed,
                )

            if decision is RetrySafetyDecision.SAFE_REQUEUE:
                if (
                    observed.requeue_kind != "TX9_DETACHED"
                    or material.tx9_material is None
                ):
                    return self._retry_reconciliation(
                        command_id=requeue_command,
                        reason="safe_kind_unavailable",
                        expectation=expectation,
                        observed=observed,
                    )
                _assert_orchestration_requeue_eligible(connection, selected)
                invalidated, _, evidence_digest, snapshot, snapshot_digest = (
                    material.tx9_material
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='QUEUED',assigned_worker_id=NULL,
                      assigned_quota_class=NULL,current_attempt_id=NULL,
                      updated_at_ms=?,version=version+1 WHERE job_id=?
                    """,
                    (timestamp, selected_token),
                )
                event_payload = {
                    "previous_status": JobStatus.LOST.value,
                    "requeue_kind": "TX9_DETACHED",
                    "invalidated_attempt_id": str(invalidated["attempt_id"]),
                    "invalidated_worker_id": str(invalidated["worker_id"]),
                    "invalidated_quota_class": str(invalidated["quota_class"]),
                    "tx9_evidence_digest": evidence_digest,
                    "invalidated_quota_snapshot": snapshot,
                    "invalidated_quota_snapshot_digest": snapshot_digest,
                    "retry_safety": retry_receipt,
                }
                self.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=selected_token,
                    event_type="JOB_REQUEUED",
                    command_id=requeue_command,
                    actor="operator",
                    job_id=selected_token,
                    attempt_id=attempt_token,
                    worker_id=str(invalidated["worker_id"]),
                    quota_class=str(invalidated["quota_class"]),
                    payload=event_payload,
                    timestamp_ms=timestamp,
                )
                written = connection.execute(
                    "SELECT * FROM events WHERE command_id=?", (requeue_command,)
                ).fetchone()
                assert written is not None
                durable = _requeue_outcome_from_event(
                    connection, written, expected_job_id=selected_token
                )
                receipt = durable.to_dict()
                receipt["retry_safety"] = retry_receipt
                return CooRetryMutationOutcome(
                    action="REQUEUED",
                    command_id=requeue_command,
                    receipt=receipt,
                )

            plan_event = connection.execute(
                "SELECT payload_json FROM events WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?",
                (root_token,),
            ).fetchone()
            handoff_event = connection.execute(
                "SELECT payload_json FROM events WHERE event_type='COO_AGGREGATION_HANDOFF_READY' AND job_id=?",
                (root_token,),
            ).fetchone()
            policy_digest = policy_sha or CooCyclePolicy.load().policy_sha256
            if policy_digest != EXPECTED_POLICY_SHA256:
                raise StateConflict("COO block policy digest is not the reviewed policy")
            evidence_value = {"retry_safety": retry_receipt}
            _validated_retry_safety_block_evidence(
                connection,
                evidence_value,
                selected_job_id=selected_token,
                attempt_id=attempt_token,
            )
            payload = {
                "schema_version": "mastermind.coo_cycle_block/v1",
                "root_job_id": root_token,
                "selected_job_id": selected_token,
                "reason": "state_conflict",
                "policy_sha": policy_digest,
                "plan_digest": (
                    _json_loads(plan_event["payload_json"], fallback={}).get("plan_digest")
                    if plan_event
                    else None
                ),
                "handoff_digest": (
                    _json_loads(handoff_event["payload_json"], fallback={}).get("handoff_digest")
                    if handoff_event
                    else None
                ),
                "evidence": evidence_value,
                "evidence_digest": orchestration_digest(evidence_value),
                "command_id": block_command,
            }
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=root_token,
                event_type="COO_CYCLE_BLOCKED",
                command_id=block_command,
                actor="coo",
                job_id=root_token,
                attempt_id=attempt_token,
                payload=payload,
                timestamp_ms=timestamp,
            )
            return CooRetryMutationOutcome(
                action="BLOCKED", command_id=block_command, receipt=payload
            )

    def validated_cycle_block(
        self, root_job_id: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Return one fully validated durable COO block for exact replay."""

        root_token = str(root_job_id or "").strip()
        with self.store.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM events
                WHERE event_type='COO_CYCLE_BLOCKED' AND job_id=?
                ORDER BY event_id
                """,
                (root_token,),
            ).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise StateConflict("COO root has multiple durable block Events")
            payload = _validated_coo_cycle_block_event(
                connection, rows[0], expected_root_id=root_token
            )
            return str(rows[0]["command_id"]), payload

    def block_cycle(
        self,
        root_job_id: str,
        *,
        selected_job_id: str,
        reason: str,
        command_id: str,
        evidence: dict[str, Any] | None = None,
        policy_sha: str | None = None,
    ) -> dict[str, Any]:
        """Append/reconcile one closed idempotent COO block receipt."""

        if reason not in COO_CYCLE_BLOCK_REASONS:
            raise StateConflict("COO block reason is outside the closed vocabulary")
        root_token = str(root_job_id or "").strip()
        selected_token = str(selected_job_id or "").strip()
        expected = f"coo-cycle:{root_token}:block:{reason}:{selected_token}"
        if command_id != expected:
            raise StateConflict("COO block command_id is not deterministic")
        evidence_value = dict(evidence or {})
        evidence_digest = orchestration_digest(evidence_value)
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            root = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_token,)
            ).fetchone()
            selected = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (selected_token,)
            ).fetchone()
            if (
                root is None
                or selected is None
                or root["root_job_id"] != root_token
                or selected["root_job_id"] != root_token
                or (
                    reason != "invalid_root"
                    and root["orchestration_role"] != "aggregation"
                )
            ):
                raise StateConflict("COO block target is outside the strict root tree")
            _validated_retry_safety_block_evidence(
                connection,
                evidence_value,
                selected_job_id=selected_token,
                attempt_id=selected["current_attempt_id"],
            )
            plan_event = connection.execute(
                """SELECT payload_json FROM events
                   WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?""",
                (root_token,),
            ).fetchone()
            handoff_event = connection.execute(
                """SELECT payload_json FROM events
                   WHERE event_type='COO_AGGREGATION_HANDOFF_READY' AND job_id=?""",
                (root_token,),
            ).fetchone()
            plan_payload = (
                _json_loads(plan_event["payload_json"], fallback={})
                if plan_event
                else {}
            )
            handoff_payload = (
                _json_loads(handoff_event["payload_json"], fallback={})
                if handoff_event
                else {}
            )
            policy_digest = policy_sha or CooCyclePolicy.load().policy_sha256
            if policy_digest != EXPECTED_POLICY_SHA256:
                raise StateConflict("COO block policy digest is not the reviewed policy")
            payload = {
                "schema_version": "mastermind.coo_cycle_block/v1",
                "root_job_id": root_token,
                "selected_job_id": selected_token,
                "reason": reason,
                "policy_sha": policy_digest,
                "plan_digest": plan_payload.get("plan_digest"),
                "handoff_digest": handoff_payload.get("handoff_digest"),
                "evidence": evidence_value,
                "evidence_digest": evidence_digest,
                "command_id": command_id,
            }
            existing = connection.execute(
                "SELECT * FROM events WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing is not None:
                if _validated_coo_cycle_block_event(
                    connection, existing, expected_root_id=root_token
                ) == payload:
                    return payload
                raise StateConflict("COO block command is owned by another semantic target")
            prior = connection.execute(
                """SELECT * FROM events
                   WHERE event_type='COO_CYCLE_BLOCKED' AND job_id=? ORDER BY event_id""",
                (root_token,),
            ).fetchall()
            if prior:
                if len(prior) != 1:
                    raise StateConflict("COO root has multiple durable block Events")
                prior_payload = _validated_coo_cycle_block_event(
                    connection, prior[0], expected_root_id=root_token
                )
                if prior_payload == payload:
                    return payload
                raise StateConflict("COO root is already blocked for another semantic state")
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=root_token,
                event_type="COO_CYCLE_BLOCKED",
                command_id=command_id,
                actor="coo",
                job_id=root_token,
                attempt_id=selected["current_attempt_id"],
                payload=payload,
                timestamp_ms=timestamp,
            )
        return payload

    def create_job(
        self,
        objective: str,
        *,
        department: str = "general",
        priority: int = 0,
        authority_level: str = "A0",
        branch: str | None = None,
        worktree: str | None = None,
        constraints: dict[str, Any] | None = None,
        attempt_limit: int = 10,
        available_at_ms: int | None = None,
        requested_authorities: str | list[str] | tuple[str, ...] | None = None,
        allowed_write_paths: list[str] | tuple[str, ...] | None = None,
        validation_commands: list[list[str]] | tuple[tuple[str, ...], ...] | None = None,
        command_id: str | None = None,
        provenance: dict[str, Any] | None = None,
        parent_job_id: str | None = None,
        owner_seat: str = "coo",
        escalation_target: str = "coo",
        business_impact: str = "routine",
        review_required: bool = False,
        reviews_job_id: str | None = None,
        orchestration_role: str | None = None,
        orchestration_provenance: dict[str, Any] | None = None,
        plan_attempt_id: str | None = None,
        plan_digest: str | None = None,
        plan_step_id: str | None = None,
        repair_round: int | None = None,
        supersedes_job_id: str | None = None,
        _v2_root_capability: object | None = None,
        _coo_cycle_planner_capability: object | None = None,
        _coo_cycle_child_capability: object | None = None,
    ) -> Job:
        """Insert one QUEUED Job and its ``JOB_CREATED`` receipt in one transaction.

        ``command_id`` lets a bounded caller name the creation command instead of
        taking the default ``uuid4().hex``.  The events table declares
        ``command_id TEXT NOT NULL UNIQUE``, so that is what makes a duplicate
        submission atomic rather than merely unlikely: two concurrent creators
        with the same command id both insert a job row, but the second one's
        event INSERT is rejected *inside* its transaction, and its job row rolls
        back with it.  Exactly one Job survives, with no advisory lock.

        ``provenance`` is recorded under the created event's payload for callers
        that must record who asked and on what grounding.  It changes no job
        column and confers no authority.
        """
        objective = str(objective).strip()
        if not objective:
            raise StateConflict("objective is required")
        if command_id is not None and _COMMAND_ID_RE.fullmatch(str(command_id)) is None:
            # A caller-named command id becomes a durable UNIQUE key, so its
            # shape is fenced here rather than trusted from the call site.
            raise StateConflict("command_id must be a bounded identifier")
        if int(attempt_limit) <= 0:
            raise StateConflict("attempt_limit must be positive")
        coo_policy: CooCyclePolicy | None = None
        owner_seat = _normalise_seat(owner_seat, field="owner_seat")
        escalation_target = _normalise_seat(
            escalation_target, field="escalation_target"
        )
        business_impact = _normalise_business_impact(business_impact)
        if not isinstance(review_required, bool):
            raise StateConflict("review_required must be a boolean")
        if reviews_job_id is not None and review_required:
            raise StateConflict(
                "a review job cannot itself require review when reviews_job_id is set"
            )
        orchestration_role = (
            str(orchestration_role).strip().lower() if orchestration_role else None
        )
        lineage_values = (
            plan_attempt_id,
            plan_digest,
            plan_step_id,
            repair_round,
            supersedes_job_id,
        )
        if orchestration_role is None:
            if orchestration_provenance is not None or any(
                value is not None for value in lineage_values
            ):
                raise StateConflict(
                    "legacy role-null job cannot carry orchestration provenance or lineage"
                )
        else:
            try:
                coo_policy = CooCyclePolicy.load()
            except CooCyclePolicyError as exc:
                raise StateConflict(f"COO cycle policy is invalid: {exc}") from exc
            if orchestration_role not in _ORCHESTRATION_ROLES:
                raise StateConflict("orchestration_role is not a closed Phase 1F-C role")
            if orchestration_role == "aggregation":
                if _v2_root_capability is not _V2_ROOT_CREATION_CAPABILITY:
                    raise StateConflict(
                        "aggregation root creation is restricted to strict CEO intent v2"
                    )
            elif _v2_root_capability is not None:
                raise StateConflict("v2 root capability cannot create a child role")
            if orchestration_role != "plan" and _coo_cycle_planner_capability is not None:
                raise StateConflict("planner capability cannot create another role")
            if orchestration_role not in {"work", "review", "repair"} and (
                _coo_cycle_child_capability is not None
            ):
                raise StateConflict("cycle child capability cannot create this role")
            if command_id is None:
                raise StateConflict("orchestration job creation requires command_id")
            if not isinstance(orchestration_provenance, dict) or set(
                orchestration_provenance
            ) != {"schema_version", "creator", "source_id", "source_digest"}:
                raise StateConflict("orchestration provenance source is not the closed wire")
            if orchestration_provenance.get("schema_version") != (
                "mastermind.executive_orchestration_provenance_source/v1"
            ):
                raise StateConflict("unsupported orchestration provenance source schema")
            if orchestration_provenance.get("creator") not in {
                "ceo_intent",
                "coo_cycle",
            }:
                raise StateConflict("orchestration provenance creator is invalid")
            source_id = str(orchestration_provenance.get("source_id") or "")
            source_digest = str(orchestration_provenance.get("source_digest") or "")
            if _COMMAND_ID_RE.fullmatch(source_id) is None or re.fullmatch(
                r"[0-9a-f]{64}", source_digest
            ) is None:
                raise StateConflict("orchestration provenance source identity is invalid")
            if orchestration_role == "review":
                assert coo_policy is not None
                if int(attempt_limit) != coo_policy.review_job_attempt_limit:
                    raise StateConflict("review Job attempt_limit must remain exactly 1")
            elif int(attempt_limit) > coo_policy.max_attempts_per_orchestration_job:
                raise StateConflict("orchestration Job attempt_limit exceeds policy")
            if orchestration_role in {"aggregation", "plan"}:
                if any(value is not None for value in lineage_values):
                    raise StateConflict("aggregation/plan Job cannot carry plan revision lineage")
            elif orchestration_role == "work":
                if (
                    not plan_attempt_id
                    or not plan_digest
                    or not plan_step_id
                    or isinstance(repair_round, bool)
                    or repair_round != 0
                    or supersedes_job_id is not None
                ):
                    raise StateConflict("work Job lineage is invalid")
            elif orchestration_role == "review":
                if (
                    not plan_attempt_id
                    or not plan_digest
                    or not plan_step_id
                    or isinstance(repair_round, bool)
                    or not isinstance(repair_round, int)
                    or not 0 <= repair_round <= coo_policy.max_repair_rounds
                    or supersedes_job_id is not None
                    or not reviews_job_id
                ):
                    raise StateConflict("review Job lineage is invalid")
            elif orchestration_role == "repair":
                if (
                    not plan_attempt_id
                    or not plan_digest
                    or not plan_step_id
                    or isinstance(repair_round, bool)
                    or not isinstance(repair_round, int)
                    or not 1 <= repair_round <= coo_policy.max_repair_rounds
                    or not supersedes_job_id
                ):
                    raise StateConflict("repair Job lineage is invalid")
            for name, value in {
                "plan_digest": plan_digest,
                "source_digest": source_digest,
            }.items():
                if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
                    raise StateConflict(f"{name} must be a lowercase SHA-256 digest")
        parent_job_id = str(parent_job_id).strip() if parent_job_id else None
        reviews_job_id = str(reviews_job_id).strip() if reviews_job_id else None
        if parent_job_id == "":
            parent_job_id = None
        if reviews_job_id == "":
            reviews_job_id = None
        if owner_seat != "coo" and not _has_executive_provenance(
            provenance, target=owner_seat
        ):
            raise StateConflict(
                f"owner_seat={owner_seat!r} requires its typed executive provenance"
            )
        if escalation_target != "coo" and not _has_executive_provenance(
            provenance, target=escalation_target
        ):
            raise StateConflict(
                f"escalation_target={escalation_target!r} requires its typed executive provenance"
            )
        normalized_constraints = _normalise_constraints(constraints)
        try:
            authority = ExecutiveAuthorityPolicy.load().authorize(
                ["READ"] if requested_authorities is None else requested_authorities,
                worktree=worktree,
                allowed_write_paths=list(allowed_write_paths or []),
                validation_commands=list(validation_commands or []),
            )
        except (AuthorityDenied, AuthorityPolicyError) as exc:
            raise StateConflict(f"job authority is denied: {exc}") from exc
        if (
            orchestration_role in {"plan", "aggregation"}
            and "READ" not in authority.requested
        ):
            raise StateConflict(
                "plan/aggregation orchestration Job grant must explicitly contain READ"
            )
        if orchestration_role == "plan" and (
            "RUN_TESTS" in authority.requested or authority.validation_commands
        ):
            raise StateConflict("plan Job must carry READ only and empty validation argv")
        if orchestration_role == "review" and (
            "READ" not in authority.requested
            or set(authority.requested) - {"READ", "RUN_TESTS"}
            or authority.allowed_write_paths
        ):
            raise StateConflict(
                "review orchestration Job grant requires READ plus optional RUN_TESTS and empty writes"
            )
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            if (
                orchestration_role == "plan"
                and _coo_cycle_planner_capability
                is _COO_CYCLE_PLANNER_CREATION_CAPABILITY
            ):
                existing = connection.execute(
                    """
                    SELECT e.event_type,e.job_id,e.aggregate_type,e.aggregate_id,
                           e.payload_json,j.*
                    FROM events e LEFT JOIN jobs j ON j.job_id=e.job_id
                    WHERE e.command_id=?
                    """,
                    (str(command_id),),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["event_type"] != "JOB_CREATED"
                        or existing["aggregate_type"] != "job"
                        or existing["aggregate_id"] != existing["job_id"]
                        or existing["job_id"] is None
                    ):
                        raise StateConflict("planner command_id is owned by another semantic action")
                    replay_job = _job_from_row(existing)
                    replay_provenance = replay_job.orchestration_provenance or {}
                    replay_payload = _strict_canonical_json_loads(
                        str(existing["payload_json"]), name="planner JOB_CREATED payload"
                    )
                    if (
                        replay_job.objective != objective
                        or replay_job.parent_job_id != parent_job_id
                        or replay_job.orchestration_role != "plan"
                        or replay_job.requested_authorities != list(authority.requested)
                        or replay_job.allowed_write_paths
                        != list(authority.allowed_write_paths)
                        or replay_job.validation_commands
                        != [list(item) for item in authority.validation_commands]
                        or replay_job.constraints != normalized_constraints
                        or replay_job.attempt_limit != int(attempt_limit)
                        or replay_provenance.get("command_id") != command_id
                        or replay_provenance.get("source_id")
                        != orchestration_provenance["source_id"]
                        or replay_provenance.get("source_digest")
                        != orchestration_provenance["source_digest"]
                        or not isinstance(replay_payload, dict)
                        or replay_payload.get("orchestration_role") != "plan"
                        or replay_payload.get("orchestration_provenance_digest")
                        != replay_job.orchestration_provenance_digest
                    ):
                        raise StateConflict("planner command replay semantic target drifted")
                    return replay_job
            parent_row = None
            if parent_job_id is not None:
                parent_row = connection.execute(
                    """
                    SELECT * FROM jobs WHERE job_id=?
                    """,
                    (parent_job_id,),
                ).fetchone()
                if parent_row is None:
                    raise StateConflict(f"parent job {parent_job_id!r} does not exist")
                _decode_orchestration_job_fields(parent_row)
                if (
                    orchestration_role is None
                    and parent_row["orchestration_role"] is not None
                ):
                    raise StateConflict(
                        "legacy role-null child cannot enter an orchestration subtree"
                    )
                if int(parent_row["depth"]) + 1 > _MAX_JOB_DEPTH:
                    raise StateConflict(
                        f"parent job {parent_job_id} would exceed the {_MAX_JOB_DEPTH}-level hierarchy bound"
                    )
                if (
                    orchestration_role is not None
                    and coo_policy is not None
                    and int(parent_row["depth"]) + 1 > coo_policy.max_depth
                ):
                    raise StateConflict(
                        f"child depth exceeds reviewed COO max_depth={coo_policy.max_depth}"
                    )
                if _ESCALATION_RANK[escalation_target] > _ESCALATION_RANK[
                    str(parent_row["escalation_target"])
                ]:
                    raise StateConflict(
                        "escalation_target may only shrink toward a less authoritative seat"
                    )
                _assert_child_does_not_widen_parent(
                    parent_row,
                    requested=list(authority.requested),
                    allowed_write_paths=list(authority.allowed_write_paths),
                    constraints=normalized_constraints,
                )
                if orchestration_role is not None:
                    if parent_row["orchestration_role"] != "aggregation":
                        raise StateConflict(
                            "orchestration children require the strict v2 aggregation root"
                        )
                    parent_validations = _strict_canonical_json_loads(
                        str(parent_row["validation_commands_json"]),
                        name="root validation_commands_json",
                    )
                    child_validations = [
                        list(item) for item in authority.validation_commands
                    ]
                    if "RUN_TESTS" in authority.requested:
                        if child_validations != parent_validations:
                            raise StateConflict(
                                "RUN_TESTS child must inherit the exact ordered root validations"
                            )
                    elif child_validations:
                        raise StateConflict(
                            "child without RUN_TESTS must carry empty validation argv"
                        )
                    if orchestration_role == "plan":
                        if (
                            parent_row["status"] != JobStatus.QUEUED.value
                            or parent_row["current_attempt_id"] is not None
                            or int(parent_row["attempt_count"]) != 0
                            or parent_row["cancel_requested_at_ms"] is not None
                            or timestamp < int(parent_row["available_at_ms"])
                        ):
                            raise StateConflict(
                                "planner creation requires an otherwise eligible QUEUED root"
                            )
                        existing_children = connection.execute(
                            "SELECT job_id FROM jobs WHERE parent_job_id=? ORDER BY job_id",
                            (parent_job_id,),
                        ).fetchall()
                        if existing_children:
                            raise StateConflict(
                                "planner creation requires an exact root with zero children"
                            )
                        admitted = connection.execute(
                            """
                            SELECT 1 FROM events
                            WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?
                            LIMIT 1
                            """,
                            (parent_job_id,),
                        ).fetchone()
                        if admitted is not None:
                            raise StateConflict(
                                "planner creation refuses after COO plan admission"
                            )
            if reviews_job_id is not None:
                reviewed_row = connection.execute(
                    "SELECT job_id,parent_job_id,root_job_id FROM jobs WHERE job_id=?",
                    (reviews_job_id,),
                ).fetchone()
                if reviewed_row is None:
                    raise StateConflict(f"reviewed job {reviews_job_id!r} does not exist")
                if reviewed_row["job_id"] == parent_job_id:
                    raise StateConflict("a job cannot review its own parent container")
                if parent_job_id is None or reviewed_row["parent_job_id"] != parent_job_id:
                    raise StateConflict(
                        "a review job must be a sibling of the job it reviews"
                    )
            if orchestration_role is not None and parent_row is not None:
                _assert_orchestration_lineage_for_create(
                    connection,
                    role=orchestration_role,
                    parent_row=parent_row,
                    plan_attempt_id=plan_attempt_id,
                    plan_digest=plan_digest,
                    plan_step_id=plan_step_id,
                    repair_round=repair_round,
                    reviews_job_id=reviews_job_id,
                    supersedes_job_id=supersedes_job_id,
                )
            if (
                orchestration_role == "plan"
                and _coo_cycle_planner_capability
                is not _COO_CYCLE_PLANNER_CREATION_CAPABILITY
            ):
                raise StateConflict(
                    "plan Job creation is restricted to the command-aware COO cycle"
                )
            if (
                orchestration_role in {"work", "review", "repair"}
                and _coo_cycle_child_capability
                is not _COO_CYCLE_CHILD_CREATION_CAPABILITY
            ):
                raise StateConflict(
                    f"{orchestration_role} Job creation is restricted to the command-aware COO cycle"
                )
            depth = 0 if parent_row is None else int(parent_row["depth"]) + 1
            numbers: list[int] = []
            for row in connection.execute("SELECT job_id FROM jobs"):
                match = re.fullmatch(r"JOB-(\d+)", str(row[0]))
                if match:
                    numbers.append(int(match.group(1)))
            number = max(numbers, default=0) + 1
            job_id = f"JOB-{number:03d}"
            root_job_id = (
                job_id
                if parent_row is None
                else str(parent_row["root_job_id"] or parent_row["job_id"])
            )
            if orchestration_role == "aggregation" and parent_job_id is not None:
                raise StateConflict("aggregation role is reserved for the root Job")
            if orchestration_role in {"plan", "work", "review", "repair"} and parent_row is None:
                raise StateConflict(f"{orchestration_role} role must be a direct child")
            if orchestration_role is not None and parent_row is not None:
                assert coo_policy is not None
                cost_class = str(normalized_constraints.get("cost_class") or "")
                if cost_class not in coo_policy.allowed_child_cost_classes:
                    raise StateConflict("orchestration child cost_class is outside policy")
                if int(attempt_limit) > int(parent_row["attempt_limit"]):
                    raise StateConflict("child attempt_limit may not exceed its parent")
            stored_orchestration_provenance: dict[str, Any] | None = None
            stored_orchestration_provenance_digest: str | None = None
            if orchestration_role is not None:
                assert orchestration_provenance is not None
                stored_orchestration_provenance = {
                    "schema_version": "mastermind.executive_orchestration_provenance/v1",
                    "creator": orchestration_provenance["creator"],
                    "source_id": orchestration_provenance["source_id"],
                    "source_digest": orchestration_provenance["source_digest"],
                    "command_id": str(command_id),
                    "job_id": job_id,
                    "parent_job_id": parent_job_id,
                    "root_job_id": root_job_id,
                    "role": orchestration_role,
                }
                stored_orchestration_provenance_digest = orchestration_digest(
                    stored_orchestration_provenance
                )
            connection.execute(
                """
                INSERT INTO jobs(
                  job_id,objective,department,priority,status,authority_level,branch,worktree,
                  constraints_json,requested_authorities_json,authority_policy_hash,
                  allowed_write_paths_json,validation_commands_json,attempt_limit,
                  available_at_ms,created_at_ms,updated_at_ms,parent_job_id,root_job_id,depth,
                  owner_seat,escalation_target,business_impact,review_required,reviews_job_id,
                  orchestration_role,orchestration_provenance_json,
                  orchestration_provenance_digest,plan_attempt_id,plan_digest,
                  plan_step_id,repair_round,supersedes_job_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    job_id,
                    objective,
                    str(department or "general"),
                    int(priority),
                    JobStatus.QUEUED.value,
                    str(authority_level or "A0"),
                    str(branch) if branch else None,
                    authority.worktree
                    if authority.worktree is not None
                    else (str(worktree) if worktree else None),
                    _json_dumps(normalized_constraints),
                    _json_dumps(list(authority.requested)),
                    authority.policy_sha256,
                    _json_dumps(list(authority.allowed_write_paths)),
                    _json_dumps([list(item) for item in authority.validation_commands]),
                    int(attempt_limit),
                    timestamp if available_at_ms is None else int(available_at_ms),
                    timestamp,
                    timestamp,
                    parent_job_id,
                    root_job_id,
                    depth,
                    owner_seat,
                    escalation_target,
                    business_impact,
                    int(review_required),
                    reviews_job_id,
                    orchestration_role,
                    _json_dumps(stored_orchestration_provenance)
                    if stored_orchestration_provenance is not None
                    else None,
                    stored_orchestration_provenance_digest,
                    plan_attempt_id,
                    plan_digest,
                    plan_step_id,
                    repair_round,
                    supersedes_job_id,
                ),
            )
            event_payload: dict[str, Any] = {
                "status": JobStatus.QUEUED.value,
                "parent_job_id": parent_job_id,
                "root_job_id": root_job_id,
                "depth": depth,
                "owner_seat": owner_seat,
                "escalation_target": escalation_target,
                "business_impact": business_impact,
                "review_required": review_required,
                "reviews_job_id": reviews_job_id,
            }
            if orchestration_role is not None:
                event_payload.update(
                    {
                        "orchestration_role": orchestration_role,
                        "orchestration_provenance_digest": stored_orchestration_provenance_digest,
                        "plan_attempt_id": plan_attempt_id,
                        "plan_digest": plan_digest,
                        "plan_step_id": plan_step_id,
                        "repair_round": repair_round,
                        "supersedes_job_id": supersedes_job_id,
                    }
                )
            if provenance is not None:
                event_payload["provenance"] = dict(provenance)
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="JOB_CREATED",
                job_id=job_id,
                payload=event_payload,
                command_id=command_id,
                timestamp_ms=timestamp,
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def get_job(self, job_id: str) -> Job | None:
        with self.store.read() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            return _job_from_row(row) if row else None

    def list_jobs(self) -> list[Job]:
        with self.store.read() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY priority DESC,created_at_ms,job_id"
            ).fetchall()
            return [_job_from_row(row) for row in rows]

    def get_cycle_handoff(self, root_job_id: str) -> dict[str, Any]:
        """Return a freshly revalidated immutable aggregation handoff."""

        root_token = str(root_job_id or "").strip()
        with self.store.read() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (root_token,)
            ).fetchone()
            if row is None:
                raise StateConflict(f"root job {root_token!r} does not exist")
            if row["orchestration_role"] != "aggregation":
                raise StateConflict("aggregation handoff is available only to a COO root")
            return _validated_aggregation_handoff(connection, row)

    def assign_job(
        self, job_id: str, worker_id: str, *, quota_class: str | None = None
    ) -> Job:
        runtime = Runtime.from_store(self.store)
        lease = runtime.attempts.claim_job(
            job_id, worker_id=worker_id, quota_class=quota_class
        )
        if lease is None:
            raise StateConflict(
                f"worker {worker_id} is unavailable or does not match job constraints"
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def _credential(self, job_id: str) -> tuple[str, int, str]:
        with self.store.read() as connection:
            row = connection.execute(
                """
                SELECT a.attempt_id,a.fence_generation,a.lease_token
                FROM jobs j JOIN attempts a ON a.attempt_id=j.current_attempt_id
                WHERE j.job_id=?
                """,
                (job_id,),
            ).fetchone()
        if row is None or row["lease_token"] is None:
            raise StateConflict(f"job {job_id} has no active leased attempt")
        return str(row["attempt_id"]), int(row["fence_generation"]), str(row["lease_token"])

    def checkpoint_job(
        self, job_id: str, payload: JobPayload | dict[str, Any]
    ) -> Job:
        attempt_id, fence, token = self._credential(job_id)
        return AttemptRegistry(self.store).checkpoint_attempt(
            attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=payload,
        )

    def complete_job(
        self, job_id: str, payload: JobPayload | dict[str, Any]
    ) -> Job:
        attempt_id, fence, token = self._credential(job_id)
        return AttemptRegistry(self.store).complete_attempt(
            attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=payload,
        )

    def fail_job(self, job_id: str, payload: JobPayload | dict[str, Any]) -> Job:
        job = self.get_job(job_id)
        if job is None:
            raise StateConflict(f"job {job_id!r} does not exist")
        if job.status in {
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
            JobStatus.LOST,
        }:
            raise StateConflict(f"job {job_id} cannot fail from {job.status.value}")
        attempt_id, fence, token = self._credential(job_id)
        return AttemptRegistry(self.store).fail_attempt(
            attempt_id,
            fence_generation=fence,
            lease_token=token,
            payload=payload,
        )

    def requeue_job(
        self, job_id: str, *, command_id: str | None = None
    ) -> Job | JobRequeueOutcome:
        timestamp = self.store.now_ms()
        if command_id is not None and _COMMAND_ID_RE.fullmatch(str(command_id)) is None:
            raise StateConflict("requeue command_id must be a bounded identifier")
        with self.store.transaction() as connection:
            # Command reconciliation is deliberately the first state-dependent
            # branch.  A later fresh claim may have advanced the Job and quota;
            # historical replay still resolves the immutable original outcome.
            if command_id is not None:
                existing = connection.execute(
                    "SELECT * FROM events WHERE command_id=?", (str(command_id),)
                ).fetchone()
                if existing is not None:
                    if (
                        existing["event_type"] != "JOB_REQUEUED"
                        or existing["job_id"] != job_id
                        or existing["aggregate_type"] != "job"
                        or existing["aggregate_id"] != job_id
                    ):
                        raise StateConflict("requeue command_id is owned by another target")
                    return _requeue_outcome_from_event(
                        connection, existing, expected_job_id=job_id
                    )
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            _job_from_row(job_row)
            orchestration_role = job_row["orchestration_role"]
            if orchestration_role is not None:
                raise StateConflict(
                    "fresh orchestration requeue requires atomic COO retry decision"
                )
            status = JobStatus(job_row["status"])
            if status not in {
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
                JobStatus.LOST,
            }:
                raise StateConflict(f"job {job_id} cannot requeue from {status.value}")
            if int(job_row["attempt_count"]) >= int(job_row["attempt_limit"]):
                raise StateConflict(f"job {job_id} exhausted its attempt limit")
            attempt_id = job_row["current_attempt_id"]
            if command_id is not None:
                raise StateConflict("legacy role-null requeue does not accept a COO command")
            tx9_material: (
                tuple[sqlite3.Row, dict[str, Any], str, dict[str, Any], str] | None
            ) = None
            if attempt_id:
                attempt_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if attempt_row is None or AttemptStatus(attempt_row["status"]) not in _TERMINAL_ATTEMPT_STATUSES:
                    raise StateConflict(f"job {job_id} still has a lease-active attempt")
                quota_row = connection.execute(
                    """
                    SELECT held_attempt_id FROM worker_quota_classes
                    WHERE worker_id=? AND quota_class=?
                    """,
                    (attempt_row["worker_id"], attempt_row["quota_class"]),
                ).fetchone()
                if quota_row is None:
                    raise PersistenceError(f"job {job_id} lost its quota-class record")
                if status in {JobStatus.RATE_LIMITED, JobStatus.LOST} and (
                    quota_row["held_attempt_id"] != attempt_id
                ):
                    raise PersistenceError(
                        f"job {job_id} terminal attempt is not held by its quota class"
                    )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET held_attempt_id=NULL,updated_at_ms=?,version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (
                        timestamp,
                        attempt_row["worker_id"],
                        attempt_row["quota_class"],
                        attempt_id,
                    ),
                )
            if tx9_material is not None:
                connection.execute(
                    """
                    UPDATE jobs
                    SET status='QUEUED',assigned_worker_id=NULL,
                        assigned_quota_class=NULL,current_attempt_id=NULL,
                        updated_at_ms=?,version=version+1
                    WHERE job_id=?
                    """,
                    (timestamp, job_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE jobs
                    SET status='QUEUED',assigned_worker_id=NULL,assigned_quota_class=NULL,
                        current_attempt_id=NULL,result_json=NULL,updated_at_ms=?,version=version+1
                    WHERE job_id=?
                    """,
                    (timestamp, job_id),
                )
            if orchestration_role is None:
                event_payload: dict[str, Any] = {"previous_status": status.value}
            elif tx9_material is None:
                event_payload = {
                    "previous_status": status.value,
                    "requeue_kind": "ORDINARY",
                    "previous_attempt_id": attempt_id,
                }
            else:
                invalidated_attempt, _, evidence_digest, snapshot, snapshot_digest = (
                    tx9_material
                )
                event_payload = {
                    "previous_status": JobStatus.LOST.value,
                    "requeue_kind": "TX9_DETACHED",
                    "invalidated_attempt_id": str(invalidated_attempt["attempt_id"]),
                    "invalidated_worker_id": str(invalidated_attempt["worker_id"]),
                    "invalidated_quota_class": str(invalidated_attempt["quota_class"]),
                    "tx9_evidence_digest": evidence_digest,
                    "invalidated_quota_snapshot": snapshot,
                    "invalidated_quota_snapshot_digest": snapshot_digest,
                }
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="JOB_REQUEUED",
                job_id=job_id,
                attempt_id=attempt_id,
                worker_id=(
                    str(attempt_row["worker_id"])
                    if orchestration_role is not None and attempt_id
                    else None
                ),
                quota_class=(
                    str(attempt_row["quota_class"])
                    if orchestration_role is not None and attempt_id
                    else None
                ),
                payload=event_payload,
                command_id=command_id,
                timestamp_ms=timestamp,
            )
            if orchestration_role is not None:
                written = connection.execute(
                    "SELECT * FROM events WHERE command_id=?", (str(command_id),)
                ).fetchone()
                assert written is not None
                return _requeue_outcome_from_event(
                    connection, written, expected_job_id=job_id
                )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def cancel_job(self, job_id: str) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            status = JobStatus(job_row["status"])
            if status == JobStatus.QUEUED:
                connection.execute(
                    "UPDATE jobs SET status='CANCELLED',updated_at_ms=?,version=version+1 WHERE job_id=?",
                    (timestamp, job_id),
                )
                event_type = "JOB_CANCELLED"
                attempt_id = None
            elif status in {JobStatus.RUNNING, JobStatus.CHECKPOINTED}:
                attempt_id = str(job_row["current_attempt_id"])
                attempt_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if attempt_row is None or attempt_row["lease_token"] is None:
                    raise StateConflict(f"job {job_id} has no cancellable attempt")
                AttemptRegistry(self.store)._leased_row(
                    connection,
                    attempt_id=attempt_id,
                    fence_generation=int(attempt_row["fence_generation"]),
                    lease_token=str(attempt_row["lease_token"]),
                    timestamp=timestamp,
                    statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
                )
                connection.execute(
                    """
                    UPDATE attempts SET status='CANCEL_REQUESTED',updated_at_ms=?,version=version+1
                    WHERE attempt_id=? AND status IN ('CLAIMED','RUNNING','CHECKPOINTED')
                    """,
                    (timestamp, attempt_id),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='CANCEL_REQUESTED',cancel_requested_at_ms=?,
                                    updated_at_ms=?,version=version+1
                    WHERE job_id=?
                    """,
                    (timestamp, timestamp, job_id),
                )
                event_type = "JOB_CANCEL_REQUESTED"
            elif status in {
                JobStatus.RATE_LIMITED,
                JobStatus.FAILED,
                JobStatus.LOST,
            }:
                attempt_id = str(job_row["current_attempt_id"])
                attempt_row = connection.execute(
                    "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
                if attempt_row is None or AttemptStatus(attempt_row["status"]) not in _TERMINAL_ATTEMPT_STATUSES:
                    raise PersistenceError(
                        f"terminal job {job_id} has no matching terminal attempt"
                    )
                quota_row = connection.execute(
                    """
                    SELECT held_attempt_id FROM worker_quota_classes
                    WHERE worker_id=? AND quota_class=?
                    """,
                    (attempt_row["worker_id"], attempt_row["quota_class"]),
                ).fetchone()
                if quota_row is None or quota_row["held_attempt_id"] not in {
                    None,
                    attempt_id,
                }:
                    raise PersistenceError(
                        f"terminal job {job_id} has an inconsistent quota-class hold"
                    )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET held_attempt_id=NULL,updated_at_ms=?,version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (
                        timestamp,
                        attempt_row["worker_id"],
                        attempt_row["quota_class"],
                        attempt_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status='CANCELLED',cancel_requested_at_ms=?,
                                    updated_at_ms=?,version=version+1
                    WHERE job_id=?
                    """,
                    (timestamp, timestamp, job_id),
                )
                event_type = "JOB_CANCELLED"
            elif status == JobStatus.CANCEL_REQUESTED:
                return _job_from_row(job_row)
            else:
                raise StateConflict(f"job {job_id} cannot cancel from {status.value}")
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type=event_type,
                job_id=job_id,
                attempt_id=attempt_id,
                payload={"previous_status": status.value},
                timestamp_ms=timestamp,
            )
        job = self.get_job(job_id)
        assert job is not None
        return job


class AttemptRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def get_attempt(self, attempt_id: str) -> Attempt | None:
        with self.store.read() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            return _attempt_from_row(row) if row else None

    def list_attempts(self, job_id: str | None = None) -> list[Attempt]:
        with self.store.read() as connection:
            if job_id:
                rows = connection.execute(
                    "SELECT * FROM attempts WHERE job_id=? ORDER BY attempt_number",
                    (job_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM attempts ORDER BY created_at_ms,attempt_id"
                ).fetchall()
            return [_attempt_from_row(row) for row in rows]

    def claim_job(
        self,
        job_id: str,
        *,
        worker_id: str | None = None,
        quota_class: str | None = None,
        lease_seconds: int | None = None,
        lease_owner: str = "local-supervisor",
        command_id: str | None = None,
        _coo_cycle_dispatch_capability: object | None = None,
    ) -> AttemptLease | OrchestrationDispatchOutcome | None:
        duration = self.store.lease_seconds if lease_seconds is None else int(lease_seconds)
        if duration <= 0:
            raise StateConflict("lease_seconds must be positive")
        owner = str(lease_owner).strip()
        if not owner:
            raise StateConflict("lease_owner is required")
        selected_quota = str(quota_class).strip().lower() if quota_class else None
        if command_id is not None and _COMMAND_ID_RE.fullmatch(str(command_id)) is None:
            raise StateConflict("dispatch command_id must be a bounded identifier")
        if (
            command_id is not None
            and _coo_cycle_dispatch_capability is not _COO_CYCLE_DISPATCH_CAPABILITY
        ):
            raise StateConflict("command-bound claim requires the COO dispatch boundary")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            if command_id is not None:
                existing_dispatch = connection.execute(
                    "SELECT * FROM events WHERE command_id=?", (str(command_id),)
                ).fetchone()
                if existing_dispatch is not None:
                    payload = _strict_canonical_json_loads(
                        str(existing_dispatch["payload_json"]),
                        name="command-bound JOB_CLAIMED payload",
                    )
                    if (
                        existing_dispatch["event_type"] != "JOB_CLAIMED"
                        or existing_dispatch["aggregate_type"] != "job"
                        or existing_dispatch["aggregate_id"] != job_id
                        or existing_dispatch["job_id"] != job_id
                        or existing_dispatch["attempt_id"] is None
                        or not isinstance(payload, dict)
                        or payload.get("cycle_command_id") != command_id
                        or payload.get("dispatch_job_id") != job_id
                        or payload.get("requested_worker_id") != worker_id
                        or payload.get("requested_quota_class") != selected_quota
                        or payload.get("lease_owner") != owner
                        or payload.get("lease_seconds") != duration
                    ):
                        raise StateConflict("dispatch command replay semantic target drifted")
                    attempt_row = connection.execute(
                        "SELECT * FROM attempts WHERE attempt_id=?",
                        (existing_dispatch["attempt_id"],),
                    ).fetchone()
                    if attempt_row is None or attempt_row["job_id"] != job_id:
                        raise PersistenceError("dispatch replay lost its bound Attempt")
                    replay_attempt = _attempt_from_row(attempt_row)
                    replay_token = attempt_row["lease_token"]
                    if replay_attempt.status in _LEASE_ACTIVE_ATTEMPT_STATUSES:
                        if replay_token is None:
                            raise PersistenceError(
                                "active dispatch replay lost its lease token"
                            )
                        outcome = "ACTIVE"
                    elif replay_attempt.status in _TERMINAL_ATTEMPT_STATUSES:
                        if replay_token is not None:
                            raise PersistenceError(
                                "terminal dispatch replay retained a lease token"
                            )
                        outcome = "TERMINAL"
                    else:
                        raise PersistenceError("dispatch replay Attempt status is invalid")
                    return OrchestrationDispatchOutcome(
                        command_id=str(command_id),
                        job_id=job_id,
                        attempt=replay_attempt,
                        outcome=outcome,
                        lease_token=str(replay_token) if replay_token is not None else None,
                    )
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"job {job_id!r} does not exist")
            _job_from_row(job_row)
            if JobStatus(job_row["status"]) != JobStatus.QUEUED:
                raise StateConflict(
                    f"job {job_id} is {job_row['status']}, not QUEUED"
                )
            living_children = _living_child_rows(connection, job_id)
            if living_children:
                raise StateConflict(
                    "container job cannot be claimed while child job(s) are living: "
                    + ", ".join(str(row["job_id"]) for row in living_children)
                )
            if timestamp < int(job_row["available_at_ms"]):
                return None
            if int(job_row["attempt_count"]) >= int(job_row["attempt_limit"]):
                raise StateConflict(f"job {job_id} exhausted its attempt limit")
            authority = _authorize_job_row(job_row)
            orchestration_role = job_row["orchestration_role"]
            quarantined_workers: set[str] = set()
            if orchestration_role is not None:
                try:
                    coo_policy = CooCyclePolicy.load()
                except CooCyclePolicyError as exc:
                    raise StateConflict(f"COO cycle policy is invalid: {exc}") from exc
                limit = int(job_row["attempt_limit"])
                if orchestration_role == "review":
                    if limit != coo_policy.review_job_attempt_limit:
                        raise StateConflict("review Job attempt_limit drifted from policy")
                elif limit > coo_policy.max_attempts_per_orchestration_job:
                    raise StateConflict("orchestration Job attempt_limit exceeds policy")
                quarantined_workers = _phase1fc_tx9_quarantined_workers(connection)
                _assert_orchestration_dispatch_eligible(connection, job_row)
                if (
                    int(job_row["attempt_count"]) > 0
                    and job_row["current_attempt_id"] is None
                ):
                    typed_job = connection.execute(
                        """
                        SELECT typeof(attempt_count) AS attempt_count_type,
                               typeof(attempt_limit) AS attempt_limit_type,
                               attempt_count,attempt_limit
                        FROM jobs WHERE job_id=?
                        """,
                        (job_id,),
                    ).fetchone()
                    if (
                        typed_job is None
                        or typed_job["attempt_count_type"] != "integer"
                        or typed_job["attempt_limit_type"] != "integer"
                        or type(typed_job["attempt_count"]) is not int
                        or type(typed_job["attempt_limit"]) is not int
                        or typed_job["attempt_count"] <= 0
                        or typed_job["attempt_count"] >= typed_job["attempt_limit"]
                    ):
                        raise StateConflict(
                            "orchestration queued continuation Attempt counters are invalid"
                        )
                    last_attempt = connection.execute(
                        """
                        SELECT *,typeof(attempt_number) AS attempt_number_type
                        FROM attempts
                        WHERE job_id=? AND attempt_number=?
                        """,
                        (job_id, typed_job["attempt_count"]),
                    ).fetchone()
                    requeues = connection.execute(
                        """
                        SELECT * FROM events
                        WHERE job_id=? AND attempt_id=? AND event_type='JOB_REQUEUED'
                        ORDER BY event_id
                        """,
                        (job_id, last_attempt["attempt_id"] if last_attempt else None),
                    ).fetchall()
                    if (
                        last_attempt is None
                        or last_attempt["attempt_number_type"] != "integer"
                        or type(last_attempt["attempt_number"]) is not int
                        or last_attempt["attempt_number"] != typed_job["attempt_count"]
                        or AttemptStatus(last_attempt["status"])
                        not in _TERMINAL_ATTEMPT_STATUSES
                        or len(requeues) != 1
                    ):
                        raise StateConflict(
                            "orchestration queued continuation lacks exact Attempt/requeue chain"
                        )
                    last_requeue = requeues[0]
                    latest_job_event = connection.execute(
                        """
                        SELECT event_id FROM events
                        WHERE aggregate_type='job' AND aggregate_id=?
                        ORDER BY event_id DESC LIMIT 1
                        """,
                        (job_id,),
                    ).fetchone()
                    if (
                        latest_job_event is None
                        or latest_job_event["event_id"] != last_requeue["event_id"]
                    ):
                        raise StateConflict(
                            "JOB_REQUEUED is not the current queued transition"
                        )
                    requeue_outcome = _requeue_outcome_from_event(
                        connection, last_requeue, expected_job_id=job_id
                    )
                    if requeue_outcome.requeue_kind == "TX9_DETACHED":
                        _validate_tx9_requeue_event(
                            connection,
                            last_requeue,
                            expected_job_id=job_id,
                            require_current_quota=True,
                        )
                if (
                    _coo_cycle_dispatch_capability
                    is not _COO_CYCLE_DISPATCH_CAPABILITY
                    or command_id is None
                ):
                    raise StateConflict(
                        "orchestration claim requires exact command-bound COO dispatch"
                    )
            elif _coo_cycle_dispatch_capability is not None or command_id is not None:
                raise StateConflict(
                    "COO dispatch capability cannot claim a legacy role-null Job"
                )
            constraints = _normalise_constraints(
                _json_loads(job_row["constraints_json"], fallback={})
            )
            candidate_rows = connection.execute(
                """
                SELECT q.*,w.provider AS worker_provider,w.account_label,
                       w.identity_status
                FROM worker_quota_classes q JOIN workers w ON w.worker_id=q.worker_id
                WHERE q.status='AVAILABLE' AND q.held_attempt_id IS NULL
                ORDER BY q.worker_id,q.quota_class
                """
            ).fetchall()
            required_provider = str(constraints.get("provider") or "")
            required_model = str(constraints.get("model") or "")
            required_effort = str(constraints.get("effort") or "")
            required_cost_class = str(constraints.get("cost_class") or "")
            required_capabilities = set(
                constraints.get("required_capabilities") or []
            )
            eligible_classes = set(constraints["eligible_quota_classes"])
            candidates: list[sqlite3.Row] = []
            for row in candidate_rows:
                if orchestration_role is not None and str(row["worker_id"]) in quarantined_workers:
                    continue
                if worker_id and row["worker_id"] != worker_id:
                    continue
                if selected_quota and row["quota_class"] != selected_quota:
                    continue
                if not _capacity_matches_route(row, constraints):
                    continue
                if row["quota_class"] not in eligible_classes:
                    continue
                if required_provider and row["provider"] != required_provider:
                    continue
                if required_model and (row["model"] or "") != required_model:
                    continue
                if required_effort and (row["effort"] or "") != required_effort:
                    continue
                if required_cost_class and (row["cost_class"] or "") != required_cost_class:
                    continue
                if row["identity_status"] != "ONLINE":
                    continue
                if orchestration_role is not None:
                    if (
                        not row["worker_provider"]
                        or not row["account_label"]
                        or str(row["provider"]) != str(row["worker_provider"])
                    ):
                        continue
                capabilities = set(
                    _normalise_capabilities(
                        _json_loads(row["capabilities_json"], fallback=[])
                    )
                )
                if not required_capabilities.issubset(capabilities):
                    continue
                candidates.append(row)
            if not candidates:
                return None
            candidates.sort(key=lambda row: _capacity_route_rank(row, constraints))
            capacity = candidates[0]
            effective_grant: dict[str, Any] | None = None
            effective_grant_digest: str | None = None
            placement_snapshot: dict[str, Any] | None = None
            placement_snapshot_digest: str | None = None
            if orchestration_role is not None:
                effective_grant, effective_grant_digest = (
                    _effective_grant_for_orchestration_job(job_row, authority)
                )
                try:
                    placement_snapshot = build_placement_snapshot(
                        worker_id=str(capacity["worker_id"]),
                        quota_class=str(capacity["quota_class"]),
                        provider=str(capacity["provider"]),
                        account_label=str(capacity["account_label"]),
                        observed_at_ms=timestamp,
                    )
                    placement_snapshot_digest = orchestration_digest(
                        placement_snapshot
                    )
                except OrchestrationPrincipalError as exc:
                    raise StateConflict(f"placement snapshot is invalid: {exc}") from exc
            attempt_id = f"ATT-{uuid4().hex}"
            lease_token = secrets.token_urlsafe(32)
            attempt_number = int(job_row["attempt_count"]) + 1
            updated = connection.execute(
                """
                UPDATE worker_quota_classes
                SET status='BUSY',held_attempt_id=?,fence_counter=fence_counter+1,
                    last_seen_at_ms=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND status='AVAILABLE'
                  AND held_attempt_id IS NULL
                """,
                (
                    attempt_id,
                    timestamp,
                    timestamp,
                    capacity["worker_id"],
                    capacity["quota_class"],
                ),
            )
            if updated.rowcount != 1:
                return None
            fence = int(
                connection.execute(
                    "SELECT fence_counter FROM worker_quota_classes WHERE worker_id=? AND quota_class=?",
                    (capacity["worker_id"], capacity["quota_class"]),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO attempts(
                  attempt_id,job_id,attempt_number,worker_id,quota_class,status,
                  fence_generation,authority_policy_hash,lease_token,lease_owner,lease_expires_at_ms,
                  heartbeat_at_ms,checkpoint_json,started_at_ms,created_at_ms,updated_at_ms,
                  effective_grant_json,effective_grant_digest,
                  placement_snapshot_json,placement_snapshot_digest
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    attempt_id,
                    job_id,
                    attempt_number,
                    capacity["worker_id"],
                    capacity["quota_class"],
                    AttemptStatus.CLAIMED.value,
                    fence,
                    authority.policy_sha256,
                    lease_token,
                    owner,
                    timestamp + duration * 1000,
                    timestamp,
                    job_row["checkpoint_json"],
                    timestamp,
                    timestamp,
                    timestamp,
                    _json_dumps(effective_grant)
                    if effective_grant is not None
                    else None,
                    effective_grant_digest,
                    _json_dumps(placement_snapshot)
                    if placement_snapshot is not None
                    else None,
                    placement_snapshot_digest,
                ),
            )
            updated_job = connection.execute(
                """
                UPDATE jobs
                SET status='RUNNING',assigned_worker_id=?,assigned_quota_class=?,
                    current_attempt_id=?,attempt_count=?,updated_at_ms=?,version=version+1
                WHERE job_id=? AND status='QUEUED' AND current_attempt_id IS NULL
                """,
                (
                    capacity["worker_id"],
                    capacity["quota_class"],
                    attempt_id,
                    attempt_number,
                    timestamp,
                    job_id,
                ),
            )
            if updated_job.rowcount != 1:
                raise StateConflict(f"job {job_id} lost the claim race")
            claim_payload: dict[str, Any] = {
                "attempt_number": attempt_number,
                "fence_generation": fence,
                "authority_policy_hash": authority.policy_sha256,
                "lease_expires_at_ms": timestamp + duration * 1000,
                "routing_policy_version": constraints.get("routing_policy_version"),
                "execution_profile_id": constraints.get("execution_profile_id"),
                "execution_profile_digest": constraints.get(
                    "execution_profile_digest"
                ),
                "capability_policy_version": constraints.get(
                    "capability_policy_version"
                ),
                "capability_policy_digest": constraints.get(
                    "capability_policy_digest"
                ),
                "preferred_model_aliases": constraints.get(
                    "preferred_model_aliases", []
                ),
                "selected_model_alias": _capacity_model_alias(capacity) or None,
                "routing_reason_codes": constraints.get("routing_reason_codes", []),
            }
            if orchestration_role is not None:
                claim_payload.update(
                    {
                        "orchestration_role": str(orchestration_role),
                        "effective_grant_digest": effective_grant_digest,
                        "placement_snapshot_digest": placement_snapshot_digest,
                        "cycle_command_id": command_id,
                        "dispatch_job_id": job_id,
                        "requested_worker_id": worker_id,
                        "requested_quota_class": selected_quota,
                        "lease_owner": owner,
                        "lease_seconds": duration,
                    }
                )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=job_id,
                event_type="JOB_CLAIMED",
                job_id=job_id,
                attempt_id=attempt_id,
                worker_id=str(capacity["worker_id"]),
                quota_class=str(capacity["quota_class"]),
                payload=claim_payload,
                command_id=command_id,
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return AttemptLease(attempt=attempt, lease_token=lease_token)

    def dispatch_cycle_job(
        self,
        job_id: str,
        *,
        command_id: str,
        worker_id: str | None = None,
        quota_class: str | None = None,
        lease_seconds: int | None = None,
        lease_owner: str = "executive-coo-cycle",
    ) -> OrchestrationDispatchOutcome | None:
        """Claim exactly one persisted orchestration Job under one command."""

        job = JobRegistry(self.store).get_job(job_id)
        if job is None:
            raise StateConflict(f"job {job_id!r} does not exist")
        prefix = f"coo-cycle:{job.root_job_id}:dispatch:{job.job_id}:attempt:"
        suffix = command_id[len(prefix) :] if command_id.startswith(prefix) else ""
        if (
            not suffix.isdigit()
            or suffix.startswith("0")
            or str(int(suffix)) != suffix
        ):
            raise StateConflict("dispatch command_id is not exact-root/job deterministic")
        ordinal = int(suffix)
        existing = self.store.get_event_by_command_id(command_id)
        if existing is None and ordinal != job.attempt_count + 1:
            raise StateConflict("dispatch command attempt ordinal is not the next Attempt")
        claimed = self.claim_job(
            job_id,
            worker_id=worker_id,
            quota_class=quota_class,
            lease_seconds=lease_seconds,
            lease_owner=lease_owner,
            command_id=command_id,
            _coo_cycle_dispatch_capability=_COO_CYCLE_DISPATCH_CAPABILITY,
        )
        if claimed is None:
            return None
        if isinstance(claimed, OrchestrationDispatchOutcome):
            return claimed
        return OrchestrationDispatchOutcome(
            command_id=command_id,
            job_id=job_id,
            attempt=claimed.attempt,
            outcome="ACTIVE",
            lease_token=claimed.lease_token,
        )

    def _leased_row(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        fence_generation: int,
        lease_token: str,
        timestamp: int,
        statuses: set[AttemptStatus],
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT a.*,j.current_attempt_id,j.status AS job_status,
                   q.held_attempt_id,q.status AS quota_status,
                   q.fence_counter AS quota_fence_counter
            FROM attempts a
            JOIN jobs j ON j.job_id=a.job_id
            JOIN worker_quota_classes q
              ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
            WHERE a.attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise StateConflict(f"attempt {attempt_id!r} does not exist")
        attempt_status = AttemptStatus(row["status"])
        if attempt_status not in statuses:
            raise StateConflict(
                f"attempt {attempt_id} cannot mutate from {row['status']}"
            )
        expected_job_status = _ACTIVE_JOB_STATUS_BY_ATTEMPT[attempt_status]
        if JobStatus(row["job_status"]) != expected_job_status:
            raise PersistenceError(
                f"attempt {attempt_id} and job have inconsistent active states"
            )
        if int(row["fence_generation"]) != int(fence_generation):
            raise StateConflict(f"attempt {attempt_id} has a stale fence")
        if int(row["quota_fence_counter"]) != int(row["fence_generation"]):
            raise PersistenceError(
                f"attempt {attempt_id} and quota class have inconsistent fences"
            )
        persisted_token = row["lease_token"]
        if persisted_token is None or not hmac.compare_digest(
            str(persisted_token), str(lease_token)
        ):
            raise StateConflict(f"attempt {attempt_id} has an invalid lease token")
        if timestamp >= int(row["lease_expires_at_ms"]):
            raise StateConflict(f"attempt {attempt_id} lease has expired")
        if row["current_attempt_id"] != attempt_id or row["held_attempt_id"] != attempt_id:
            raise StateConflict(f"attempt {attempt_id} is no longer current")
        return row

    def adopt_attempt(
        self,
        attempt_id: str,
        *,
        expected_fence_generation: int,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> AttemptLease:
        """Rotate a live persisted lease for a restarted trusted supervisor.

        Adoption is compare-and-swap on the public fence generation.  It does
        not assert that the reconstructed process is alive and does not change
        attempt status; the adopter must inspect the persisted process identity
        and then heartbeat, acknowledge cancellation, or explicitly mark it
        lost.  Rotating both fence and token makes every prior owner stale.
        """
        owner = str(lease_owner).strip()
        if not owner:
            raise StateConflict("lease_owner is required for adoption")
        duration = (
            self.store.lease_seconds if lease_seconds is None else int(lease_seconds)
        )
        if duration <= 0:
            raise StateConflict("lease_seconds must be positive")
        timestamp = self.store.now_ms()
        replacement_token = secrets.token_urlsafe(32)
        with self.store.transaction() as connection:
            row = connection.execute(
                """
                SELECT a.*,j.current_attempt_id,j.status AS job_status,q.held_attempt_id,
                       q.fence_counter AS quota_fence_counter
                FROM attempts a
                JOIN jobs j ON j.job_id=a.job_id
                JOIN worker_quota_classes q
                  ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE a.attempt_id=?
                """,
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise StateConflict(f"attempt {attempt_id!r} does not exist")
            if row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value:
                raise StateConflict(
                    "OPERATOR_HARNESS adoption uses epoch/generation state"
                )
            attempt_status = AttemptStatus(row["status"])
            if attempt_status not in _LEASE_ACTIVE_ATTEMPT_STATUSES:
                raise StateConflict(
                    f"attempt {attempt_id} cannot be adopted from {row['status']}"
                )
            if (
                JobStatus(row["job_status"])
                != _ACTIVE_JOB_STATUS_BY_ATTEMPT[attempt_status]
            ):
                raise PersistenceError(
                    f"attempt {attempt_id} and job have inconsistent active states"
                )
            current_fence = int(row["fence_generation"])
            if current_fence != int(expected_fence_generation):
                raise StateConflict(f"attempt {attempt_id} has a stale adoption fence")
            if int(row["quota_fence_counter"]) != current_fence:
                raise PersistenceError(
                    f"attempt {attempt_id} and quota class have inconsistent fences"
                )
            if timestamp >= int(row["lease_expires_at_ms"]):
                raise StateConflict(
                    f"attempt {attempt_id} lease has expired; reconcile it first"
                )
            if row["lease_token"] is None:
                raise PersistenceError(
                    f"active attempt {attempt_id} has no lease token"
                )
            if (
                row["current_attempt_id"] != attempt_id
                or row["held_attempt_id"] != attempt_id
            ):
                raise StateConflict(f"attempt {attempt_id} is no longer current")
            if row["pid"] is None and row["provider_session_id"] is None:
                raise StateConflict(
                    f"attempt {attempt_id} has no durable process/provider identity to adopt"
                )
            next_fence = current_fence + 1
            expiry = max(int(row["lease_expires_at_ms"]), timestamp + duration * 1_000)
            updated_quota = connection.execute(
                """
                UPDATE worker_quota_classes
                SET fence_counter=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                  AND fence_counter=?
                """,
                (
                    next_fence,
                    timestamp,
                    row["worker_id"],
                    row["quota_class"],
                    attempt_id,
                    current_fence,
                ),
            )
            if updated_quota.rowcount != 1:
                raise StateConflict(f"attempt {attempt_id} lost the adoption race")
            updated_attempt = connection.execute(
                """
                UPDATE attempts
                SET fence_generation=?,lease_token=?,lease_owner=?,lease_expires_at_ms=?,
                    heartbeat_at_ms=?,updated_at_ms=?,version=version+1
                WHERE attempt_id=? AND fence_generation=? AND lease_token=?
                  AND status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                """,
                (
                    next_fence,
                    replacement_token,
                    owner,
                    expiry,
                    timestamp,
                    timestamp,
                    attempt_id,
                    current_fence,
                    row["lease_token"],
                ),
            )
            if updated_attempt.rowcount != 1:
                raise StateConflict(f"attempt {attempt_id} lost the adoption race")
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_ADOPTED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={
                    "previous_fence_generation": current_fence,
                    "fence_generation": next_fence,
                    "previous_lease_owner": str(row["lease_owner"]),
                    "lease_owner": owner,
                    "lease_expires_at_ms": expiry,
                },
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return AttemptLease(attempt=attempt, lease_token=replacement_token)

    def heartbeat_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        extend_seconds: int | None = None,
    ) -> Attempt:
        duration = (
            self.store.lease_seconds if extend_seconds is None else int(extend_seconds)
        )
        if duration <= 0:
            raise StateConflict("extend_seconds must be positive")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_LEASE_ACTIVE_ATTEMPT_STATUSES,
            )
            expiry = max(int(row["lease_expires_at_ms"]), timestamp + duration * 1000)
            connection.execute(
                """
                UPDATE attempts SET heartbeat_at_ms=?,lease_expires_at_ms=?,updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (timestamp, expiry, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET last_seen_at_ms=?,updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (
                    timestamp,
                    timestamp,
                    row["worker_id"],
                    row["quota_class"],
                    attempt_id,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_HEARTBEAT",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"lease_expires_at_ms": expiry},
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def takeover_expired_operator_harness(
        self,
        attempt_id: str,
        *,
        expected_fence_generation: int,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> AttemptLease:
        """CAS-fence an expired OHF lease without adopting provider/process state."""

        owner = str(lease_owner or "").strip()
        duration = (
            self.store.lease_seconds if lease_seconds is None else int(lease_seconds)
        )
        if not owner or duration <= 0:
            raise StateConflict(
                "OHF takeover requires owner and positive lease_seconds"
            )
        timestamp = self.store.now_ms()
        token = secrets.token_urlsafe(32)
        with self.store.transaction() as connection:
            row = connection.execute(
                """SELECT a.*,j.current_attempt_id,j.status AS job_status,
                          q.held_attempt_id,q.fence_counter AS quota_fence_counter
                   FROM attempts a JOIN jobs j ON j.job_id=a.job_id
                   JOIN worker_quota_classes q
                     ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                   WHERE a.attempt_id=?""",
                (attempt_id,),
            ).fetchone()
            if (
                row is None
                or row["execution_mode"] != AttemptExecutionMode.OPERATOR_HARNESS.value
            ):
                raise StateConflict("expired takeover is only for OPERATOR_HARNESS")
            status = AttemptStatus(row["status"])
            current_fence = int(row["fence_generation"])
            if (
                status not in _LEASE_ACTIVE_ATTEMPT_STATUSES
                or JobStatus(row["job_status"]) != _ACTIVE_JOB_STATUS_BY_ATTEMPT[status]
                or row["current_attempt_id"] != attempt_id
                or row["held_attempt_id"] != attempt_id
                or int(row["quota_fence_counter"]) != current_fence
                or current_fence != int(expected_fence_generation)
                or timestamp < int(row["lease_expires_at_ms"])
            ):
                raise StateConflict("expired OHF takeover preconditions failed")
            authority = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM harness_session_epochs
                   WHERE attempt_id=? AND state='CURRENT') AS current_epochs,
                  (SELECT COUNT(*) FROM process_generations g
                   JOIN harness_session_epochs e
                     ON e.session_epoch_id=g.session_epoch_id
                   WHERE e.attempt_id=? AND g.executive_writer_held=1) AS writers
                """,
                (attempt_id, attempt_id),
            ).fetchone()
            cardinality = (int(authority["current_epochs"]), int(authority["writers"]))
            if cardinality not in {(0, 0), (1, 1)}:
                raise StateConflict(
                    "expired OHF takeover found incoherent epoch/writer cardinality"
                )
            next_fence = current_fence + 1
            expiry = timestamp + duration * 1000
            quota = connection.execute(
                """UPDATE worker_quota_classes SET fence_counter=?,updated_at_ms=?,version=version+1
                   WHERE worker_id=? AND quota_class=? AND held_attempt_id=? AND fence_counter=?""",
                (
                    next_fence,
                    timestamp,
                    row["worker_id"],
                    row["quota_class"],
                    attempt_id,
                    current_fence,
                ),
            )
            attempt = connection.execute(
                """UPDATE attempts SET fence_generation=?,lease_token=?,lease_owner=?,
                          lease_expires_at_ms=?,heartbeat_at_ms=?,updated_at_ms=?,version=version+1
                   WHERE attempt_id=? AND fence_generation=? AND lease_expires_at_ms<=?
                     AND status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')""",
                (
                    next_fence,
                    token,
                    owner,
                    expiry,
                    timestamp,
                    timestamp,
                    attempt_id,
                    current_fence,
                    timestamp,
                ),
            )
            if quota.rowcount != 1 or attempt.rowcount != 1:
                raise StateConflict("expired OHF takeover lost its CAS race")
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="OHF_EXPIRED_LEASE_TAKEN_OVER",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={
                    "previous_fence_generation": current_fence,
                    "fence_generation": next_fence,
                    "lease_owner": owner,
                    "lease_expires_at_ms": expiry,
                },
                timestamp_ms=timestamp,
            )
        value = self.get_attempt(attempt_id)
        assert value is not None
        return AttemptLease(attempt=value, lease_token=token)

    def record_process(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        pid: int | None = None,
        pgid: int | None = None,
        process_start_identity: str | None = None,
        boot_id: str | None = None,
        provider_session_id: str | None = None,
        stdout_path: str | None = None,
        stderr_path: str | None = None,
        result_path: str | None = None,
        launch_metadata: dict[str, Any] | None = None,
    ) -> Attempt:
        """Persist the identity needed to reconstruct one claimed invocation.

        A local process is identified by PID, process group, boot identity, and
        process-start identity together so PID reuse cannot be mistaken for the
        claimed process.  A provider-managed invocation may instead be
        reconstructed by its provider session id.
        """
        if launch_metadata is not None and not isinstance(launch_metadata, dict):
            raise StateConflict("launch_metadata must be a mapping")
        local_values = (pid, pgid, process_start_identity, boot_id)
        if pid is None:
            if any(value is not None for value in local_values):
                raise StateConflict(
                    "pid, pgid, process_start_identity, and boot_id must be recorded together"
                )
        else:
            if int(pid) <= 0 or pgid is None or int(pgid) <= 0:
                raise StateConflict("pid and pgid must be positive")
            if (
                not str(process_start_identity or "").strip()
                or not str(boot_id or "").strip()
            ):
                raise StateConflict(
                    "a local process requires process_start_identity and boot_id"
                )
        provider_session = str(provider_session_id or "").strip() or None
        if pid is None and provider_session is None:
            raise StateConflict(
                "record_process requires a local process identity or provider_session_id"
            )
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.CLAIMED},
            )
            if row["pid"] is not None or row["provider_session_id"] is not None:
                raise StateConflict(
                    f"attempt {attempt_id} already has a process identity"
                )
            if row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value:
                raise StateConflict(
                    "OPERATOR_HARNESS may not write legacy Attempt identity"
                )
            connection.execute(
                """
                UPDATE attempts
                SET execution_mode=COALESCE(execution_mode,'SEALED_WORKER'),
                    pid=?,pgid=?,process_start_identity=?,boot_id=?,provider_session_id=?,
                    stdout_path=?,stderr_path=?,result_path=?,launch_metadata_json=?,
                    updated_at_ms=?,version=version+1
                WHERE attempt_id=? AND status='CLAIMED'
                """,
                (
                    int(pid) if pid is not None else None,
                    int(pgid) if pgid is not None else None,
                    (
                        str(process_start_identity).strip()
                        if process_start_identity is not None
                        else None
                    ),
                    str(boot_id).strip() if boot_id is not None else None,
                    provider_session,
                    str(stdout_path) if stdout_path is not None else None,
                    str(stderr_path) if stderr_path is not None else None,
                    str(result_path) if result_path is not None else None,
                    _json_dumps(launch_metadata or {}),
                    timestamp,
                    attempt_id,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_PROCESS_RECORDED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"process_kind": "local" if pid is not None else "provider"},
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def mark_running(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        required_launch_attestation_schema: str | None = None,
    ) -> Attempt:
        """Fence the CLAIMED -> RUNNING transition after invocation identity is durable."""
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.CLAIMED},
            )
            if row["pid"] is None and row["provider_session_id"] is None:
                raise StateConflict(
                    f"attempt {attempt_id} has no durable process/provider identity"
                )
            if row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value:
                raise StateConflict(
                    "OPERATOR_HARNESS running transition is owned by harness state"
                )
            job_row = connection.execute(
                "SELECT orchestration_role FROM jobs WHERE job_id=?",
                (row["job_id"],),
            ).fetchone()
            if job_row is None:  # pragma: no cover - foreign key invariant
                raise PersistenceError(f"attempt {attempt_id} lost its Job")
            orchestration_principal: dict[str, Any] | None = None
            orchestration_principal_digest: str | None = None
            if job_row["orchestration_role"] is not None:
                if required_launch_attestation_schema not in {
                    None,
                    "mastermind.executive_launch_attestation/v1",
                }:
                    raise StateConflict(
                        f"attempt {attempt_id} launch attestation schema is not accepted"
                    )
                _attestation, orchestration_principal, _placement, _grant = (
                    _validated_sealed_worker_launch_material(
                        row, allow_unsealed_principal=True
                    )
                )
                if (
                    row["execution_principal_snapshot_json"] is not None
                    or row["execution_principal_snapshot_digest"] is not None
                ):
                    raise StateConflict(
                        "sealed-worker principal was populated before accepted launch"
                    )
                orchestration_principal_digest = orchestration_digest(
                    orchestration_principal
                )
            elif required_launch_attestation_schema is not None:
                metadata = _json_loads(row["launch_metadata_json"], fallback={})
                attestation = (
                    metadata.get("launch_attestation")
                    if isinstance(metadata, dict)
                    else None
                )
                required = {
                    "schema_version",
                    "created_at",
                    "executable_path",
                    "binary",
                    "rendered_argv",
                    "environment_keys",
                    "permission_profile_sha256",
                    "prompt_sha256",
                    "expected_base_sha",
                    "observed_base_sha",
                    "workspace_identity",
                    "worker_identity",
                    "provider_home_identity",
                    "secret_canary_verdict",
                    "launch_nonce",
                    "process_identity",
                }
                if not isinstance(attestation, dict) or not required.issubset(
                    attestation
                ):
                    raise StateConflict(
                        f"attempt {attempt_id} has no complete launch attestation"
                    )
                if (
                    attestation.get("schema_version")
                    != required_launch_attestation_schema
                ):
                    raise StateConflict(
                        f"attempt {attempt_id} launch attestation schema is not accepted"
                    )
                if (
                    not isinstance(attestation.get("rendered_argv"), list)
                    or not attestation["rendered_argv"]
                ):
                    raise StateConflict("launch attestation has no rendered argv")
                environment_keys = attestation.get("environment_keys")
                if (
                    not isinstance(environment_keys, list)
                    or any(
                        not isinstance(key, str) or not key for key in environment_keys
                    )
                    or len(environment_keys) != len(set(environment_keys))
                ):
                    raise StateConflict(
                        "launch attestation environment allow-list is invalid"
                    )
                for digest_field in ("permission_profile_sha256", "prompt_sha256"):
                    digest = attestation.get(digest_field)
                    if (
                        not isinstance(digest, str)
                        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    ):
                        raise StateConflict(
                            f"launch attestation {digest_field} is not a SHA-256"
                        )
                canary = attestation.get("secret_canary_verdict")
                if not isinstance(canary, dict) or canary.get("passed") is not True:
                    raise StateConflict("launch attestation secret canary did not pass")
                process_identity = attestation.get("process_identity")
                if not isinstance(process_identity, dict) or any(
                    process_identity.get(key) != expected
                    for key, expected in (
                        ("pid", row["pid"]),
                        ("pgid", row["pgid"]),
                        ("start_identity", row["process_start_identity"]),
                        ("boot_id", row["boot_id"]),
                    )
                ):
                    raise StateConflict(
                        "launch attestation process identity differs from durable columns"
                    )
            if orchestration_principal is None:
                updated = connection.execute(
                    """
                    UPDATE attempts SET status='RUNNING',updated_at_ms=?,version=version+1
                    WHERE attempt_id=? AND status='CLAIMED'
                    """,
                    (timestamp, attempt_id),
                )
            else:
                updated = connection.execute(
                    """
                    UPDATE attempts
                    SET status='RUNNING',execution_principal_snapshot_json=?,
                        execution_principal_snapshot_digest=?,updated_at_ms=?,version=version+1
                    WHERE attempt_id=? AND status='CLAIMED'
                      AND execution_principal_snapshot_json IS NULL
                      AND execution_principal_snapshot_digest IS NULL
                    """,
                    (
                        _json_dumps(orchestration_principal),
                        orchestration_principal_digest,
                        timestamp,
                        attempt_id,
                    ),
                )
            if updated.rowcount != 1:
                raise StateConflict(f"attempt {attempt_id} lost the running transition")
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_RUNNING",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def record_process_exit(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        exit_code: int,
        result_path: str | None = None,
        provider_session_id: str | None = None,
    ) -> Attempt:
        """Persist a fenced exit observation before the result transition."""
        provider_session = str(provider_session_id or "").strip() or None
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                    AttemptStatus.CANCEL_REQUESTED,
                },
            )
            if row["exit_code"] is not None:
                raise StateConflict(
                    f"attempt {attempt_id} already has an exit observation"
                )
            if row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value:
                raise StateConflict(
                    "OPERATOR_HARNESS may not write legacy Attempt identity"
                )
            if (
                provider_session is not None
                and row["provider_session_id"] is not None
                and row["provider_session_id"] != provider_session
            ):
                raise StateConflict(
                    f"attempt {attempt_id} provider session identity changed"
                )
            connection.execute(
                """
                UPDATE attempts SET exit_code=?,result_path=COALESCE(?,result_path),
                                    provider_session_id=COALESCE(provider_session_id,?),
                                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (
                    int(exit_code),
                    str(result_path) if result_path is not None else None,
                    provider_session,
                    timestamp,
                    attempt_id,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=attempt_id,
                event_type="ATTEMPT_PROCESS_EXITED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"exit_code": int(exit_code)},
                timestamp_ms=timestamp,
            )
        attempt = self.get_attempt(attempt_id)
        assert attempt is not None
        return attempt

    def checkpoint_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any],
        checkpoint_sequence: int | None = None,
    ) -> Job:
        checkpoint = JobPayload.from_value(payload).to_dict()
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
            )
            role = connection.execute(
                "SELECT orchestration_role FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            if (
                row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value
                and role is not None
                and role["orchestration_role"] is not None
            ):
                raise StateConflict(
                    "orchestration OHF checkpoints require a generation-bound API"
                )
            expected = int(row["checkpoint_sequence"]) + 1
            sequence = (
                expected if checkpoint_sequence is None else int(checkpoint_sequence)
            )
            if sequence != expected:
                raise StateConflict(
                    f"attempt {attempt_id} expected checkpoint sequence {expected}, got {sequence}"
                )
            expiry = max(
                int(row["lease_expires_at_ms"]),
                timestamp + self.store.lease_seconds * 1000,
            )
            connection.execute(
                """
                UPDATE attempts
                SET status='CHECKPOINTED',checkpoint_sequence=?,checkpoint_json=?,heartbeat_at_ms=?,
                    lease_expires_at_ms=?,updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (
                    sequence,
                    _json_dumps(checkpoint),
                    timestamp,
                    expiry,
                    timestamp,
                    attempt_id,
                ),
            )
            connection.execute(
                """
                UPDATE jobs SET status='CHECKPOINTED',checkpoint_json=?,updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=?
                """,
                (_json_dumps(checkpoint), timestamp, row["job_id"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type="JOB_CHECKPOINTED",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"checkpoint_sequence": sequence},
                timestamp_ms=timestamp,
            )
        job = JobRegistry(self.store).get_job(str(row["job_id"]))
        assert job is not None
        return job

    @staticmethod
    def _require_ohf_shutdown_before_legacy_terminal(
        connection: sqlite3.Connection, row: sqlite3.Row
    ) -> None:
        if row["execution_mode"] != AttemptExecutionMode.OPERATOR_HARNESS.value:
            return
        active = connection.execute(
            """SELECT 1 FROM harness_session_epochs e
               LEFT JOIN process_generations g ON g.session_epoch_id=e.session_epoch_id
               WHERE e.attempt_id=?
                 AND (e.state='CURRENT' OR COALESCE(g.executive_writer_held,0)=1)
               LIMIT 1""",
            (row["attempt_id"],),
        ).fetchone()
        if active is not None:
            raise StateConflict(
                "OHF Attempt requires shutdown/abandon evidence before legacy terminal transition"
            )

    def _terminal(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        status: AttemptStatus,
        job_status: JobStatus,
        payload: JobPayload | dict[str, Any],
        event_type: str,
    ) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
            )
            self._require_ohf_shutdown_before_legacy_terminal(connection, row)
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            if job_row is None:
                raise StateConflict("terminal Attempt lost its Job")
            orchestration_role = job_row["orchestration_role"]
            if status is AttemptStatus.COMPLETED:
                if orchestration_role == "aggregation":
                    structured = _validated_aggregation_terminal_payload(
                        connection,
                        attempt_row=row,
                        payload=payload,
                    )
                elif orchestration_role is not None:
                    structured = _validated_orchestration_child_terminal_payload(
                        connection,
                        attempt_row=row,
                        job_row=job_row,
                        payload=payload,
                    )
                else:
                    structured = JobPayload.from_value(payload).to_dict()
                    _assert_parent_aggregation_allowed(
                        connection, parent_job_id=str(row["job_id"])
                    )
            else:
                structured = JobPayload.from_value(payload).to_dict()
            review_evidence = _review_void_evidence(
                connection,
                job_id=str(row["job_id"]),
                worker_id=str(row["worker_id"]),
            )
            result_json = _json_dumps(structured)
            error_json = result_json if status == AttemptStatus.FAILED else None
            connection.execute(
                """
                UPDATE attempts
                SET status=?,lease_token=NULL,result_json=?,error_json=?,finished_at_ms=?,
                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (
                    status.value,
                    result_json,
                    error_json,
                    timestamp,
                    timestamp,
                    attempt_id,
                ),
            )
            connection.execute(
                """
                UPDATE jobs SET status=?,result_json=?,updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=?
                """,
                (job_status.value, result_json, timestamp, row["job_id"], attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET held_attempt_id=NULL,
                    status=CASE WHEN status='BUSY' THEN 'AVAILABLE' ELSE status END,
                    updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            event_payload: dict[str, Any] = {"status": job_status.value}
            if review_evidence is not None:
                event_payload["review"] = review_evidence
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type=event_type,
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload=event_payload,
                timestamp_ms=timestamp,
            )
            job_id = str(row["job_id"])
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def complete_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any],
    ) -> Job:
        return self._terminal(
            attempt_id,
            fence_generation=fence_generation,
            lease_token=lease_token,
            status=AttemptStatus.COMPLETED,
            job_status=JobStatus.COMPLETED,
            payload=payload,
            event_type="JOB_COMPLETED",
        )

    def fail_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any],
    ) -> Job:
        return self._terminal(
            attempt_id,
            fence_generation=fence_generation,
            lease_token=lease_token,
            status=AttemptStatus.FAILED,
            job_status=JobStatus.FAILED,
            payload=payload,
            event_type="JOB_FAILED",
        )

    def mark_lost(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        reason: str,
        verified_process_absent: bool = False,
    ) -> Job:
        """Record a verified missing/killed invocation before lease expiry.

        Callers must first compare the durable PID/start/boot identity (or
        provider session) with the live process.  Unverified suspicions wait for
        lease-expiry reconciliation and cannot prematurely free or fence work.
        """
        reason = str(reason).strip()
        if not reason:
            raise StateConflict("mark_lost requires a reason")
        if verified_process_absent is not True:
            raise StateConflict("mark_lost requires verified_process_absent=True")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses=_LEASE_ACTIVE_ATTEMPT_STATUSES,
            )
            if row["pid"] is None and row["provider_session_id"] is None:
                raise StateConflict(
                    f"attempt {attempt_id} has no durable process/provider identity to verify"
                )
            if row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value:
                raise StateConflict(
                    "OPERATOR_HARNESS LOST transition is owned by harness reconciliation"
                )
            error = {
                "reason": reason,
                "verified_process_absent": True,
            }
            connection.execute(
                """
                UPDATE attempts
                SET status='LOST',lease_token=NULL,error_json=?,finished_at_ms=?,
                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (_json_dumps(error), timestamp, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE jobs SET status='LOST',updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=?
                """,
                (timestamp, row["job_id"], attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET status='ERROR',updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type="ATTEMPT_LOST",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload=error,
                timestamp_ms=timestamp,
            )
            job_id = str(row["job_id"])
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def _rate_limit_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any] | None,
        timestamp: int,
        actor: str,
    ) -> str:
        # Re-run all guards even when the compatibility facade sourced the
        # credential from the database.
        guarded = self._leased_row(
            connection,
            attempt_id=str(row["attempt_id"]),
            fence_generation=fence_generation,
            lease_token=lease_token,
            timestamp=timestamp,
            statuses=_WORKER_MUTABLE_ATTEMPT_STATUSES,
        )
        self._require_ohf_shutdown_before_legacy_terminal(connection, guarded)
        checkpoint = (
            JobPayload.from_value(payload).to_dict() if payload is not None else None
        )
        checkpoint_json = (
            _json_dumps(checkpoint)
            if checkpoint is not None
            else guarded["checkpoint_json"]
        )
        checkpoint_sequence = int(guarded["checkpoint_sequence"]) + (
            1 if payload is not None else 0
        )
        connection.execute(
            """
            UPDATE attempts
            SET status='RATE_LIMITED',lease_token=NULL,checkpoint_sequence=?,checkpoint_json=?,
                finished_at_ms=?,updated_at_ms=?,version=version+1
            WHERE attempt_id=?
            """,
            (
                checkpoint_sequence,
                checkpoint_json,
                timestamp,
                timestamp,
                guarded["attempt_id"],
            ),
        )
        connection.execute(
            """
            UPDATE jobs SET status='RATE_LIMITED',checkpoint_json=?,updated_at_ms=?,version=version+1
            WHERE job_id=? AND current_attempt_id=?
            """,
            (checkpoint_json, timestamp, guarded["job_id"], guarded["attempt_id"]),
        )
        connection.execute(
            """
            UPDATE worker_quota_classes
            SET status='RATE_LIMITED',updated_at_ms=?,version=version+1
            WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
            """,
            (
                timestamp,
                guarded["worker_id"],
                guarded["quota_class"],
                guarded["attempt_id"],
            ),
        )
        self.store.append_event(
            connection,
            aggregate_type="job",
            aggregate_id=str(guarded["job_id"]),
            event_type="JOB_RATE_LIMITED",
            actor=actor,
            job_id=str(guarded["job_id"]),
            attempt_id=str(guarded["attempt_id"]),
            worker_id=str(guarded["worker_id"]),
            quota_class=str(guarded["quota_class"]),
            payload={"checkpoint_sequence": checkpoint_sequence},
            timestamp_ms=timestamp,
        )
        return str(guarded["job_id"])

    def rate_limit_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        payload: JobPayload | dict[str, Any] | None = None,
    ) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise StateConflict(f"attempt {attempt_id!r} does not exist")
            job_id = self._rate_limit_in_transaction(
                connection,
                row=row,
                fence_generation=fence_generation,
                lease_token=lease_token,
                payload=payload,
                timestamp=timestamp,
                actor="worker",
            )
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def acknowledge_cancel(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
    ) -> Job:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.CANCEL_REQUESTED},
            )
            self._require_ohf_shutdown_before_legacy_terminal(connection, row)
            connection.execute(
                """
                UPDATE attempts SET status='CANCELLED',lease_token=NULL,finished_at_ms=?,
                                    updated_at_ms=?,version=version+1
                WHERE attempt_id=?
                """,
                (timestamp, timestamp, attempt_id),
            )
            connection.execute(
                """
                UPDATE jobs SET status='CANCELLED',updated_at_ms=?,version=version+1
                WHERE job_id=? AND current_attempt_id=? AND status='CANCEL_REQUESTED'
                """,
                (timestamp, row["job_id"], attempt_id),
            )
            connection.execute(
                """
                UPDATE worker_quota_classes
                SET held_attempt_id=NULL,
                    status=CASE WHEN status='BUSY' THEN 'AVAILABLE' ELSE status END,
                    updated_at_ms=?,version=version+1
                WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                """,
                (timestamp, row["worker_id"], row["quota_class"], attempt_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=str(row["job_id"]),
                event_type="JOB_CANCELLED",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                timestamp_ms=timestamp,
            )
            job_id = str(row["job_id"])
        job = JobRegistry(self.store).get_job(job_id)
        assert job is not None
        return job

    def reconcile_expired(
        self,
        *,
        now_ms: int | None = None,
        attempt_id: str | None = None,
    ) -> list[Attempt]:
        """Fence expired current attempts, optionally one inspected attempt only.

        The targeted form lets a process-aware supervisor prove one persisted
        invocation absent before applying lease-expiry state transitions.  The
        untargeted form remains the registry-level compatibility operation.
        """
        timestamp = self.store.now_ms() if now_ms is None else int(now_ms)
        lost_ids: list[str] = []
        with self.store.transaction() as connection:
            target_clause = " AND a.attempt_id=?" if attempt_id is not None else ""
            parameters: tuple[Any, ...] = (
                (timestamp, str(attempt_id)) if attempt_id is not None else (timestamp,)
            )
            rows = connection.execute(
                f"""
                SELECT a.*,j.current_attempt_id,j.status AS job_status,q.held_attempt_id,
                       q.fence_counter AS quota_fence_counter
                FROM attempts a
                JOIN jobs j ON j.job_id=a.job_id
                JOIN worker_quota_classes q
                  ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
                WHERE a.status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                  AND a.lease_expires_at_ms<=?
                  {target_clause}
                ORDER BY a.lease_expires_at_ms,a.attempt_id
                """,
                parameters,
            ).fetchall()
            for row in rows:
                attempt_id = str(row["attempt_id"])
                if (
                    row["current_attempt_id"] != attempt_id
                    or row["held_attempt_id"] != attempt_id
                ):
                    raise PersistenceError(
                        f"expired attempt {attempt_id} has inconsistent current links"
                    )
                if int(row["quota_fence_counter"]) != int(row["fence_generation"]):
                    raise PersistenceError(
                        f"expired attempt {attempt_id} has an inconsistent quota fence"
                    )
                attempt_status = AttemptStatus(row["status"])
                if (
                    JobStatus(row["job_status"])
                    != _ACTIVE_JOB_STATUS_BY_ATTEMPT[attempt_status]
                ):
                    raise PersistenceError(
                        f"expired attempt {attempt_id} has an inconsistent job state"
                    )
                if row["execution_mode"] == AttemptExecutionMode.OPERATOR_HARNESS.value:
                    error = {
                        "reason": "ohf_lease_expired_fenced",
                        "expired_at_ms": int(row["lease_expires_at_ms"]),
                    }
                    connection.execute(
                        """UPDATE attempts
                           SET error_json=?,updated_at_ms=?,version=version+1
                           WHERE attempt_id=? AND lease_expires_at_ms<=?""",
                        (_json_dumps(error), timestamp, attempt_id, timestamp),
                    )
                    command_id = (
                        f"ohf-expiry-fence:{attempt_id}:{row['fence_generation']}"
                    )
                    if (
                        self.store.get_event_by_command_id(
                            command_id, connection=connection
                        )
                        is None
                    ):
                        self.store.append_event(
                            connection,
                            aggregate_type="attempt",
                            aggregate_id=attempt_id,
                            event_type="OHF_LEASE_EXPIRED_FENCED",
                            command_id=command_id,
                            actor="reconciler",
                            job_id=str(row["job_id"]),
                            attempt_id=attempt_id,
                            worker_id=str(row["worker_id"]),
                            quota_class=str(row["quota_class"]),
                            payload=error,
                            timestamp_ms=timestamp,
                        )
                    lost_ids.append(attempt_id)
                    continue
                cancel_was_requested = attempt_status == AttemptStatus.CANCEL_REQUESTED
                error = {
                    "reason": "lease_expired",
                    "expired_at_ms": int(row["lease_expires_at_ms"]),
                }
                connection.execute(
                    """
                    UPDATE attempts
                    SET status='LOST',lease_token=NULL,error_json=?,finished_at_ms=?,
                        updated_at_ms=?,version=version+1
                    WHERE attempt_id=? AND status IN ('CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED')
                      AND lease_expires_at_ms<=?
                    """,
                    (_json_dumps(error), timestamp, timestamp, attempt_id, timestamp),
                )
                connection.execute(
                    """
                    UPDATE jobs SET status=?,updated_at_ms=?,version=version+1
                    WHERE job_id=? AND current_attempt_id=?
                    """,
                    (
                        (
                            JobStatus.CANCELLED.value
                            if cancel_was_requested
                            else JobStatus.LOST.value
                        ),
                        timestamp,
                        row["job_id"],
                        attempt_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET status='ERROR',
                        held_attempt_id=CASE WHEN ? THEN NULL ELSE held_attempt_id END,
                        updated_at_ms=?,version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (
                        1 if cancel_was_requested else 0,
                        timestamp,
                        row["worker_id"],
                        row["quota_class"],
                        attempt_id,
                    ),
                )
                self.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=str(row["job_id"]),
                    event_type=(
                        "JOB_CANCELLED_AFTER_LEASE_LOSS"
                        if cancel_was_requested
                        else "ATTEMPT_LOST"
                    ),
                    actor="reconciler",
                    job_id=str(row["job_id"]),
                    attempt_id=attempt_id,
                    worker_id=str(row["worker_id"]),
                    quota_class=str(row["quota_class"]),
                    payload=error,
                    timestamp_ms=timestamp,
                )
                lost_ids.append(attempt_id)
        return [
            attempt
            for attempt_id in lost_ids
            if (attempt := self.get_attempt(attempt_id)) is not None
        ]

    restart_reconcile = reconcile_expired


def _ohf_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _ohf_jsonable(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _ohf_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_ohf_jsonable(item) for item in value]
    return value


def _ohf_json_digest(value: Any) -> tuple[str, str]:
    encoded = json.dumps(
        _ohf_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ohf_process(process: ProcessIdentityObservation) -> tuple[int, int, str, str]:
    try:
        pid, pgid = int(process.pid), int(process.pgid)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise StateConflict("OHF process identity is incomplete") from exc
    start, boot = (
        str(process.process_start_identity or "").strip(),
        str(process.boot_id or "").strip(),
    )
    if pid <= 0 or pgid <= 0 or not start or not boot:
        raise StateConflict("OHF process identity is incomplete")
    return pid, pgid, start, boot


class OperatorHarnessRegistry:
    """The sole durable OHF state-plane; it owns no provider or process calls."""

    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def _leased(
        self,
        connection: sqlite3.Connection,
        *,
        attempt_id: str,
        fence_generation: int,
        lease_token: str,
        timestamp: int,
        statuses: set[AttemptStatus] | None = None,
    ) -> sqlite3.Row:
        row = AttemptRegistry(self.store)._leased_row(
            connection,
            attempt_id=attempt_id,
            fence_generation=fence_generation,
            lease_token=lease_token,
            timestamp=timestamp,
            statuses=statuses or _LEASE_ACTIVE_ATTEMPT_STATUSES,
        )
        profile_json = row["requested_execution_profile_json"]
        profile_digest = row["requested_execution_profile_digest"]
        if (
            row["execution_mode"] != AttemptExecutionMode.OPERATOR_HARNESS.value
            or not profile_json
            or not profile_digest
            or hashlib.sha256(str(profile_json).encode("utf-8")).hexdigest()
            != profile_digest
        ):
            raise StateConflict("attempt has no valid sealed OPERATOR_HARNESS profile")
        return row

    def _event(
        self, connection: sqlite3.Connection, command_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM events WHERE command_id=?", (command_id,)
        ).fetchone()

    def _owned_generation(
        self,
        connection: sqlite3.Connection,
        *,
        leased: sqlite3.Row,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        require_current: bool = False,
        require_writer: bool = False,
    ) -> sqlite3.Row:
        durable = connection.execute(
            """SELECT g.*,e.attempt_id,e.worker_id AS epoch_worker,
                      e.epoch_number,e.state,e.provider_session_id AS epoch_session
               FROM process_generations g JOIN harness_session_epochs e
                 ON e.session_epoch_id=g.session_epoch_id
               WHERE e.session_epoch_id=? AND g.process_generation_id=?""",
            (epoch.session_epoch_id, generation.process_generation_id),
        ).fetchone()
        if (
            durable is None
            or durable["attempt_id"] != leased["attempt_id"]
            or durable["attempt_id"] != epoch.attempt_id
            or durable["epoch_worker"] != leased["worker_id"]
            or durable["epoch_worker"] != epoch.worker_id
            or int(durable["epoch_number"]) != epoch.epoch_number
            or durable["session_epoch_id"] != generation.session_epoch_id
            or durable["worker_id"] != leased["worker_id"]
            or durable["worker_id"] != generation.worker_id
            or int(durable["generation_number"]) != generation.generation_number
            or (require_current and durable["state"] != SessionEpochState.CURRENT.value)
            or (require_writer and not durable["executive_writer_held"])
        ):
            raise StateConflict(
                "OHF epoch/generation refs are not exactly owned by the lease"
            )
        return durable

    def _receipt(
        self,
        connection: sqlite3.Connection,
        *,
        op: OperationId,
        kind: OperationReceiptKind,
        row: sqlite3.Row,
        payload: dict[str, Any],
    ) -> None:
        opposite = {
            OperationReceiptKind.APPLIED: OperationReceiptKind.EFFECT_UNKNOWN,
            OperationReceiptKind.EFFECT_UNKNOWN: OperationReceiptKind.APPLIED,
        }.get(kind)
        if (
            opposite is not None
            and self._event(connection, operation_receipt_command_id(op, opposite))
            is not None
        ):
            raise StateConflict(
                f"operation cannot have both {kind.value} and {opposite.value} receipts"
            )
        command_id = (
            op.command_id
            if kind is OperationReceiptKind.INTENT
            else operation_receipt_command_id(op, kind)
        )
        self.store.append_event(
            connection,
            aggregate_type="operator_operation",
            aggregate_id=op.command_id,
            event_type=kind.value,
            command_id=command_id,
            actor="supervisor",
            job_id=str(row["job_id"]),
            attempt_id=str(row["attempt_id"]),
            worker_id=str(row["worker_id"]),
            quota_class=str(row["quota_class"]),
            payload=payload,
        )

    def seal_operator_harness_attempt(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        requested: RequestedExecutionProfile,
    ) -> Attempt:
        payload, digest = _ohf_json_digest(requested)
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = AttemptRegistry(self.store)._leased_row(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.CLAIMED,
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                },
            )
            if (
                requested.worker_id != row["worker_id"]
                or requested.authority_policy_hash != row["authority_policy_hash"]
            ):
                raise StateConflict("requested profile does not match Attempt")
            if row["execution_mode"] not in {
                None,
                AttemptExecutionMode.OPERATOR_HARNESS.value,
            } or row["requested_execution_profile_json"] not in {None, payload}:
                raise StateConflict("attempt execution mode/profile already sealed")
            if row["requested_execution_profile_json"] is None:
                if row["status"] != AttemptStatus.CLAIMED.value:
                    raise StateConflict(
                        "only a CLAIMED Attempt may seal its first OHF profile"
                    )
                connection.execute(
                    """
                    UPDATE attempts
                    SET execution_mode='OPERATOR_HARNESS',
                        requested_execution_profile_json=?,
                        requested_execution_profile_digest=?,
                        updated_at_ms=?,version=version+1
                    WHERE attempt_id=?
                    """,
                    (payload, digest, timestamp, attempt_id),
                )
                self.store.append_event(
                    connection,
                    aggregate_type="attempt",
                    aggregate_id=attempt_id,
                    event_type="OHF_PROFILE_SEALED",
                    actor="supervisor",
                    job_id=str(row["job_id"]),
                    attempt_id=attempt_id,
                    worker_id=str(row["worker_id"]),
                    quota_class=str(row["quota_class"]),
                    payload={"profile_digest": digest},
                    timestamp_ms=timestamp,
                )
        value = AttemptRegistry(self.store).get_attempt(attempt_id)
        assert value is not None
        return value

    def reserve_start(
        self,
        attempt_id: str,
        *,
        fence_generation: int,
        lease_token: str,
        operation_id: OperationId,
    ) -> tuple[SessionEpochRef, ProcessGenerationRef]:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.CLAIMED,
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                },
            )
            seal = connection.execute(
                """
                SELECT payload_json FROM events
                WHERE aggregate_type='attempt' AND aggregate_id=?
                  AND event_type='OHF_PROFILE_SEALED'
                  AND attempt_id=? AND worker_id=?
                ORDER BY event_id DESC LIMIT 1
                """,
                (attempt_id, attempt_id, row["worker_id"]),
            ).fetchone()
            seal_payload = (
                _json_loads(seal["payload_json"], fallback={}) if seal else {}
            )
            if seal is None or seal_payload != {
                "profile_digest": row["requested_execution_profile_digest"]
            }:
                raise StateConflict(
                    "TX-2 requires an exact committed TX-1 profile seal"
                )
            existing_intent = self._event(connection, operation_id.command_id)
            if existing_intent is not None:
                existing_payload = _json_loads(
                    existing_intent["payload_json"], fallback={}
                )
                allocated = connection.execute(
                    """SELECT e.*,g.process_generation_id,g.generation_number,
                                      g.worker_id AS generation_worker,g.executive_writer_held
                       FROM harness_session_epochs e JOIN process_generations g
                         ON g.session_epoch_id=e.session_epoch_id
                       WHERE e.session_epoch_id=? AND g.process_generation_id=?""",
                    (
                        existing_payload.get("session_epoch_id"),
                        existing_payload.get("process_generation_id"),
                    ),
                ).fetchone()
                if (
                    existing_intent["event_type"] != OperationReceiptKind.INTENT.value
                    or existing_intent["aggregate_id"] != operation_id.command_id
                    or existing_payload.get("operation_kind")
                    != OperationKind.START_SESSION.value
                    or existing_payload.get("attempt_id") != attempt_id
                    or allocated is None
                    or allocated["attempt_id"] != attempt_id
                    or allocated["state"] != SessionEpochState.CURRENT.value
                    or int(allocated["generation_number"]) != 1
                    or not allocated["executive_writer_held"]
                    or self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.APPLIED
                        ),
                    )
                    is not None
                    or self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.EFFECT_UNKNOWN
                        ),
                    )
                    is not None
                ):
                    raise StateConflict("OHF start operation is not retryable")
                return (
                    SessionEpochRef(
                        str(allocated["session_epoch_id"]),
                        attempt_id,
                        str(allocated["worker_id"]),
                        int(allocated["epoch_number"]),
                    ),
                    ProcessGenerationRef(
                        str(allocated["process_generation_id"]),
                        str(allocated["session_epoch_id"]),
                        1,
                        str(allocated["generation_worker"]),
                    ),
                )
            if connection.execute(
                "SELECT 1 FROM harness_session_epochs WHERE attempt_id=? AND state='CURRENT'",
                (attempt_id,),
            ).fetchone():
                raise StateConflict("CURRENT epoch already exists")
            epoch_stats = connection.execute(
                """
                SELECT COUNT(*) AS n,
                       COALESCE(MIN(epoch_number),0) AS first,
                       COALESCE(MAX(epoch_number),0) AS last
                FROM harness_session_epochs
                WHERE attempt_id=?
                """,
                (attempt_id,),
            ).fetchone()
            assert epoch_stats is not None
            job_role = connection.execute(
                "SELECT orchestration_role FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            if (
                int(epoch_stats["n"])
                and job_role is not None
                and job_role["orchestration_role"] is not None
            ):
                raise StateConflict(
                    "orchestration TX-2 permits only one session epoch per Attempt"
                )
            if int(epoch_stats["n"]):
                if int(epoch_stats["first"]) != 1 or int(epoch_stats["n"]) != int(
                    epoch_stats["last"]
                ):
                    raise StateConflict("OHF epoch ordinals are not contiguous")
                unsafe = connection.execute(
                    """SELECT 1 FROM harness_session_epochs e
                       LEFT JOIN process_generations g ON g.session_epoch_id=e.session_epoch_id
                       WHERE e.attempt_id=? AND (e.state!='ABANDONED' OR COALESCE(g.executive_writer_held,0)!=0)
                       LIMIT 1""",
                    (attempt_id,),
                ).fetchone()
                if unsafe is not None:
                    raise StateConflict(
                        "a replacement epoch requires only abandoned writer-free history"
                    )
            elif row["status"] != AttemptStatus.CLAIMED.value:
                raise StateConflict("the first epoch requires a CLAIMED Attempt")
            epoch_number = int(epoch_stats["last"]) + 1
            eid, gid = f"ohf-epoch-{uuid4().hex}", f"ohf-generation-{uuid4().hex}"
            connection.execute(
                """
                INSERT INTO harness_session_epochs(
                    session_epoch_id,attempt_id,worker_id,epoch_number,state,created_at_ms
                ) VALUES(?,?,?,?, 'CURRENT',?)
                """,
                (eid, attempt_id, row["worker_id"], epoch_number, timestamp),
            )
            connection.execute(
                """
                INSERT INTO process_generations(
                    process_generation_id,session_epoch_id,worker_id,generation_number,
                    started_at_ms,executive_writer_held,provider_writer_state,created_at_ms
                ) VALUES(?,?,?,?,?,1,'UNKNOWN',?)
                """,
                (gid, eid, row["worker_id"], 1, timestamp, timestamp),
            )
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.INTENT,
                row=row,
                payload={
                    "schema_version": "mastermind.operator_harness_intent/v1",
                    "operation_kind": "start_session",
                    "attempt_id": attempt_id,
                    "session_epoch_id": eid,
                    "process_generation_id": gid,
                    "worker_id": row["worker_id"],
                    "provider_session_id": None,
                },
            )
        return SessionEpochRef(
            eid, attempt_id, str(row["worker_id"]), epoch_number
        ), ProcessGenerationRef(gid, eid, 1, str(row["worker_id"]))

    def bind_start_result(
        self,
        *,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        fence_generation: int,
        lease_token: str,
        provider_session_id: str,
        process: ProcessIdentityObservation,
    ) -> ProcessGenerationRef:
        session = str(provider_session_id or "").strip()
        pid, pgid, start, boot = _ohf_process(process)
        if not session:
            raise StateConflict("TX-3 requires provider_session_id")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=epoch.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.CLAIMED,
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                },
            )
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=generation,
                require_current=True,
                require_writer=True,
            )
            intent = self._event(connection, operation_id.command_id)
            item = connection.execute(
                """
                SELECT g.*,e.provider_session_id AS epoch_session,e.state
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            intent_payload = (
                _json_loads(intent["payload_json"], fallback={}) if intent else {}
            )
            expected_intent = {
                "schema_version": "mastermind.operator_harness_intent/v1",
                "operation_kind": OperationKind.START_SESSION.value,
                "attempt_id": epoch.attempt_id,
                "session_epoch_id": epoch.session_epoch_id,
                "process_generation_id": generation.process_generation_id,
                "worker_id": epoch.worker_id,
                "provider_session_id": None,
            }
            if (
                intent is None
                or intent["event_type"] != OperationReceiptKind.INTENT.value
                or intent["aggregate_type"] != "operator_operation"
                or intent["aggregate_id"] != operation_id.command_id
                or intent["attempt_id"] != epoch.attempt_id
                or intent["worker_id"] != epoch.worker_id
                or intent_payload != expected_intent
                or item is None
                or item["session_epoch_id"] != epoch.session_epoch_id
                or item["state"] != "CURRENT"
                or not item["executive_writer_held"]
                or item["epoch_session"] not in {None, session}
            ):
                raise StateConflict("TX-3 target mismatch")
            applied = self._event(
                connection,
                operation_receipt_command_id(
                    operation_id, OperationReceiptKind.APPLIED
                ),
            )
            if applied:
                if (
                    item["pid"] == pid
                    and item["pgid"] == pgid
                    and item["process_start_identity"] == start
                    and item["boot_id"] == boot
                    and item["epoch_session"] == session
                ):
                    return generation
                raise StateConflict("TX-3 already applied differently")
            connection.execute(
                "UPDATE harness_session_epochs SET provider_session_id=? WHERE session_epoch_id=?",
                (session, epoch.session_epoch_id),
            )
            connection.execute(
                """
                UPDATE process_generations
                SET provider_session_id=?,pid=?,pgid=?,process_start_identity=?,
                    boot_id=?,last_observed_at_ms=?
                WHERE process_generation_id=?
                """,
                (
                    session,
                    pid,
                    pgid,
                    start,
                    boot,
                    timestamp,
                    generation.process_generation_id,
                ),
            )
            connection.execute(
                "UPDATE attempts SET status='RUNNING',updated_at_ms=?,version=version+1 WHERE attempt_id=?",
                (timestamp, epoch.attempt_id),
            )
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.APPLIED,
                row=row,
                payload={
                    "operation_kind": "start_session",
                    "provider_session_id": session,
                    "process_generation_id": generation.process_generation_id,
                },
            )
        return generation

    def seal_attestation(
        self,
        *,
        generation: ProcessGenerationRef,
        fence_generation: int,
        lease_token: str,
        requested: RequestedExecutionProfile,
        attestation: ObservedHarnessAttestation,
        principal_observation: OperatorPrincipalObservation | None = None,
    ) -> str:
        """TX-4: immutable, per-generation observed attestation receipt."""
        if not isinstance(attestation, ObservedHarnessAttestation):
            raise StateConflict("TX-4 requires typed ObservedHarnessAttestation")
        profile_json, profile_digest = _ohf_json_digest(requested)
        payload, digest = _ohf_json_digest(attestation)
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            found = connection.execute(
                """
                SELECT e.attempt_id,e.worker_id AS epoch_worker,e.state AS epoch_state,
                       e.provider_session_id AS epoch_provider_session,
                       g.session_epoch_id,g.worker_id,g.generation_number,
                       g.provider_session_id,g.pid,g.pgid,g.process_start_identity,
                       g.boot_id,g.executive_writer_held,g.ended_at_ms,
                       g.observed_attestation_json,g.observed_attestation_digest
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            if not found:
                raise StateConflict("unknown OHF generation")
            if (
                found["session_epoch_id"] != generation.session_epoch_id
                or found["worker_id"] != generation.worker_id
                or found["epoch_worker"] != generation.worker_id
                or int(found["generation_number"]) != generation.generation_number
            ):
                raise StateConflict("TX-4 generation ref mismatch")
            row = self._leased(
                connection,
                attempt_id=str(found["attempt_id"]),
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            job = connection.execute(
                "SELECT orchestration_role FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            orchestration_role = (
                str(job["orchestration_role"]) if job and job["orchestration_role"] else None
            )
            if (
                row["requested_execution_profile_json"] != profile_json
                or row["requested_execution_profile_digest"] != profile_digest
            ):
                raise StateConflict(
                    "TX-4 requested profile does not match the sealed Attempt"
                )
            if found["observed_attestation_json"] not in {None, payload}:
                raise StateConflict("generation attestation is already sealed")
            comparison = compare_launch(requested, attestation)
            if orchestration_role is None and principal_observation is not None:
                raise StateConflict("legacy OHF attestation cannot seal COO principal evidence")
            admission_command = f"ohf-work-admit:{generation.process_generation_id}"
            existing_admission = self._event(connection, admission_command)
            if existing_admission is not None:
                existing_payload = _strict_canonical_json_loads(
                    str(existing_admission["payload_json"]),
                    name="orchestration work admission replay",
                )
                supplied = (
                    principal_observation.to_dict()
                    if isinstance(principal_observation, OperatorPrincipalObservation)
                    else None
                )
                if (
                    orchestration_role is None
                    or comparison.decision is not LaunchDecision.ALLOW
                    or existing_admission["aggregate_type"] != "process_generation"
                    or existing_admission["aggregate_id"] != generation.process_generation_id
                    or existing_admission["attempt_id"] != row["attempt_id"]
                    or existing_admission["worker_id"] != row["worker_id"]
                    or existing_payload.get("principal_observation") != supplied
                    or existing_payload.get("observed_attestation_digest") != digest
                ):
                    raise StateConflict("TX-4 admission replay semantic target drifted")
                return digest
            connection.execute(
                """
                UPDATE process_generations
                SET observed_attestation_json=?,observed_attestation_digest=?
                WHERE process_generation_id=?
                """,
                (payload, digest, generation.process_generation_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="process_generation",
                aggregate_id=generation.process_generation_id,
                event_type="OHF_ATTESTATION_OBSERVED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=str(row["attempt_id"]),
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"attestation_digest": digest},
                timestamp_ms=timestamp,
            )
            self.store.append_event(
                connection,
                aggregate_type="process_generation",
                aggregate_id=generation.process_generation_id,
                event_type="OHF_LAUNCH_DECISION",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=str(row["attempt_id"]),
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={
                    "decision": comparison.decision.value,
                    "attestation_digest": digest,
                },
                timestamp_ms=timestamp,
            )
            if orchestration_role is not None and comparison.decision is LaunchDecision.ALLOW:
                if not isinstance(principal_observation, OperatorPrincipalObservation):
                    raise StateConflict("TX-4 ALLOW requires typed principal observation")
                observed_principal = OperatorPrincipalObservation.from_dict(
                    principal_observation.to_dict()
                )
                expected_process = {
                    "pid": found["pid"],
                    "pgid": found["pgid"],
                    "process_start_identity": found["process_start_identity"],
                    "boot_id": found["boot_id"],
                }
                latest = connection.execute(
                    """
                    SELECT g.process_generation_id
                    FROM process_generations g JOIN harness_session_epochs e
                      ON e.session_epoch_id=g.session_epoch_id
                    WHERE e.attempt_id=?
                    ORDER BY e.epoch_number DESC,g.generation_number DESC LIMIT 1
                    """,
                    (row["attempt_id"],),
                ).fetchone()
                launch_operation_kind = (
                    OperationKind.START_SESSION.value
                    if int(found["generation_number"]) == 1
                    else OperationKind.RESUME_SESSION.value
                )
                tx3_rows = []
                for event in connection.execute(
                    """SELECT * FROM events
                       WHERE aggregate_type='operator_operation' AND event_type=?
                         AND attempt_id=? ORDER BY event_id""",
                    (OperationReceiptKind.APPLIED.value, row["attempt_id"]),
                ):
                    applied_payload = _json_loads(event["payload_json"], fallback={})
                    if (
                        applied_payload.get("operation_kind")
                        == launch_operation_kind
                        and applied_payload.get("process_generation_id")
                        == generation.process_generation_id
                    ):
                        tx3_rows.append((event, applied_payload))
                try:
                    placement = validate_placement_snapshot(
                        _load_canonical_digest_pair(
                            row["placement_snapshot_json"],
                            row["placement_snapshot_digest"],
                            name="TX-4 placement snapshot",
                        )
                    )
                    grant = _load_canonical_digest_pair(
                        row["effective_grant_json"],
                        row["effective_grant_digest"],
                        name="TX-4 effective grant",
                    )
                    stable_principal = build_execution_principal_snapshot(
                        attempt_id=str(row["attempt_id"]),
                        placement_snapshot=placement,
                        observation=observed_principal,
                    )
                    stable_digest = orchestration_digest(stable_principal)
                except (OrchestrationPrincipalError, PersistenceError) as exc:
                    raise StateConflict(f"TX-4 principal evidence is invalid: {exc}") from exc
                if (
                    found["epoch_state"] != SessionEpochState.CURRENT.value
                    or not found["executive_writer_held"]
                    or found["ended_at_ms"] is not None
                    or found["provider_session_id"] != found["epoch_provider_session"]
                    or latest is None
                    or latest["process_generation_id"] != generation.process_generation_id
                    or len(tx3_rows) != 1
                    or observed_principal.attempt_id != row["attempt_id"]
                    or observed_principal.worker_id != row["worker_id"]
                    or observed_principal.process_generation_id
                    != generation.process_generation_id
                    or observed_principal.provider_session_id
                    != found["provider_session_id"]
                    or observed_principal.process_identity != expected_process
                    or placement.get("worker_id") != row["worker_id"]
                    or placement.get("quota_class") != row["quota_class"]
                    or not isinstance(grant, dict)
                    or grant.get("job_id") != row["job_id"]
                    or grant.get("policy_sha") != row["authority_policy_hash"]
                ):
                    raise StateConflict("TX-4 principal/admission binding is invalid")
                stored_principal = _load_canonical_digest_pair(
                    row["execution_principal_snapshot_json"],
                    row["execution_principal_snapshot_digest"],
                    name="TX-4 existing execution principal",
                )
                if stored_principal is None:
                    connection.execute(
                        """UPDATE attempts
                           SET execution_principal_snapshot_json=?,
                               execution_principal_snapshot_digest=?,
                               updated_at_ms=?,version=version+1
                           WHERE attempt_id=?""",
                        (
                            _json_dumps(stable_principal),
                            stable_digest,
                            timestamp,
                            row["attempt_id"],
                        ),
                    )
                elif stored_principal != stable_principal or (
                    row["execution_principal_snapshot_digest"] != stable_digest
                ):
                    raise StateConflict("TX-4 stable execution principal changed")
                observation_value = observed_principal.to_dict()
                admission_payload = {
                    "schema_version": "mastermind.orchestration_work_admission/v1",
                    "job_id": str(row["job_id"]),
                    "attempt_id": str(row["attempt_id"]),
                    "worker_id": str(row["worker_id"]),
                    "quota_class": str(row["quota_class"]),
                    "orchestration_role": orchestration_role,
                    "process_generation_id": generation.process_generation_id,
                    "provider_session_id": str(found["provider_session_id"]),
                    "tx3_applied_command_id": str(tx3_rows[0][0]["command_id"]),
                    "observed_attestation_digest": digest,
                    "principal_observation": observation_value,
                    "principal_observation_digest": orchestration_digest(
                        observation_value
                    ),
                    "execution_principal_snapshot_digest": stable_digest,
                    "placement_snapshot_digest": str(row["placement_snapshot_digest"]),
                    "effective_grant_digest": str(row["effective_grant_digest"]),
                    "policy_sha": CooCyclePolicy.load().policy_sha256,
                    "launch_decision": LaunchDecision.ALLOW.value,
                }
                self.store.append_event(
                    connection,
                    aggregate_type="process_generation",
                    aggregate_id=generation.process_generation_id,
                    event_type="ORCHESTRATION_WORK_ADMITTED",
                    command_id=admission_command,
                    actor="supervisor",
                    job_id=str(row["job_id"]),
                    attempt_id=str(row["attempt_id"]),
                    worker_id=str(row["worker_id"]),
                    quota_class=str(row["quota_class"]),
                    payload=admission_payload,
                    timestamp_ms=timestamp,
                )
        return digest

    def admitted_principal_observation(
        self, generation: ProcessGenerationRef
    ) -> OperatorPrincipalObservation | None:
        """Return the immutable same-generation observation for TX-4 replay."""

        with self.store.read() as connection:
            rows = connection.execute(
                """SELECT payload_json FROM events
                   WHERE event_type='ORCHESTRATION_WORK_ADMITTED'
                     AND aggregate_type='process_generation' AND aggregate_id=?
                   ORDER BY event_id""",
                (generation.process_generation_id,),
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise StateConflict("generation has duplicate orchestration admissions")
        payload = _strict_canonical_json_loads(
            str(rows[0]["payload_json"]), name="orchestration work admission"
        )
        return OperatorPrincipalObservation.from_dict(payload["principal_observation"])

    def _require_active_orchestration_generation(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        generation_id: str,
    ) -> dict[str, Any] | None:
        """Recompute the additive OHF active-work predicate for direct writes."""

        job = connection.execute(
            "SELECT orchestration_role FROM jobs WHERE job_id=?", (row["job_id"],)
        ).fetchone()
        role = str(job["orchestration_role"]) if job and job["orchestration_role"] else None
        if role is None:
            return None
        generations = connection.execute(
            """
            SELECT g.*,e.attempt_id,e.worker_id AS epoch_worker,e.epoch_number,
                   e.state AS epoch_state,e.provider_session_id AS epoch_provider_session
            FROM process_generations g JOIN harness_session_epochs e
              ON e.session_epoch_id=g.session_epoch_id
            WHERE e.attempt_id=?
            ORDER BY e.epoch_number DESC,g.generation_number DESC
            """,
            (row["attempt_id"],),
        ).fetchall()
        current = generations[0] if generations else None
        admissions = connection.execute(
            """SELECT * FROM events
               WHERE event_type='ORCHESTRATION_WORK_ADMITTED'
                 AND aggregate_type='process_generation' AND aggregate_id=?
               ORDER BY event_id""",
            (generation_id,),
        ).fetchall()
        decisions = connection.execute(
            """SELECT * FROM events
               WHERE event_type='OHF_LAUNCH_DECISION'
                 AND aggregate_type='process_generation' AND aggregate_id=?
               ORDER BY event_id""",
            (generation_id,),
        ).fetchall()
        seals = connection.execute(
            """SELECT 1 FROM events
               WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?""",
            (row["attempt_id"],),
        ).fetchall()
        if current is None or len(admissions) != 1 or len(decisions) != 1 or seals:
            raise StateConflict("orchestration generation is not active-work admitted")
        admission_event = admissions[0]
        admission = _strict_canonical_json_loads(
            str(admission_event["payload_json"]), name="active work admission"
        )
        decision = _strict_canonical_json_loads(
            str(decisions[0]["payload_json"]), name="active launch decision"
        )
        observation = _validated_admission_principal(row, admission)
        admission_keys = {
            "schema_version", "job_id", "attempt_id", "worker_id", "quota_class",
            "orchestration_role", "process_generation_id", "provider_session_id",
            "tx3_applied_command_id", "observed_attestation_digest",
            "principal_observation", "principal_observation_digest",
            "execution_principal_snapshot_digest", "placement_snapshot_digest",
            "effective_grant_digest", "policy_sha", "launch_decision",
        }
        if (
            set(admission) != admission_keys
            or admission.get("schema_version")
            != "mastermind.orchestration_work_admission/v1"
            or current["process_generation_id"] != generation_id
            or current["attempt_id"] != row["attempt_id"]
            or current["worker_id"] != row["worker_id"]
            or current["epoch_worker"] != row["worker_id"]
            or current["epoch_state"] != SessionEpochState.CURRENT.value
            or not current["executive_writer_held"]
            or current["ended_at_ms"] is not None
            or current["provider_session_id"] != current["epoch_provider_session"]
            or admission_event["command_id"] != f"ohf-work-admit:{generation_id}"
            or admission_event["attempt_id"] != row["attempt_id"]
            or admission_event["worker_id"] != row["worker_id"]
            or admission_event["quota_class"] != row["quota_class"]
            or admission.get("job_id") != row["job_id"]
            or admission.get("attempt_id") != row["attempt_id"]
            or admission.get("worker_id") != row["worker_id"]
            or admission.get("quota_class") != row["quota_class"]
            or admission.get("orchestration_role") != role
            or admission.get("process_generation_id") != generation_id
            or admission.get("provider_session_id") != current["provider_session_id"]
            or admission.get("observed_attestation_digest")
            != current["observed_attestation_digest"]
            or admission.get("execution_principal_snapshot_digest")
            != row["execution_principal_snapshot_digest"]
            or admission.get("placement_snapshot_digest")
            != row["placement_snapshot_digest"]
            or admission.get("effective_grant_digest") != row["effective_grant_digest"]
            or admission.get("policy_sha") != CooCyclePolicy.load().policy_sha256
            or admission.get("launch_decision") != LaunchDecision.ALLOW.value
            or decision
            != {
                "decision": LaunchDecision.ALLOW.value,
                "attestation_digest": current["observed_attestation_digest"],
            }
            or observation["process_identity"]
            != {
                "pid": current["pid"],
                "pgid": current["pgid"],
                "process_start_identity": current["process_start_identity"],
                "boot_id": current["boot_id"],
            }
        ):
            raise StateConflict("orchestration active-work admission evidence drifted")
        return admission

    def reserve_turn(
        self,
        *,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        fence_generation: int,
        lease_token: str,
    ) -> TurnRef:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=epoch.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            item = connection.execute(
                """
                SELECT e.attempt_id,e.worker_id AS epoch_worker,e.epoch_number,
                       e.provider_session_id,e.state,g.session_epoch_id,
                       g.worker_id AS generation_worker,g.generation_number,
                       g.executive_writer_held
                FROM harness_session_epochs e
                JOIN process_generations g
                  ON g.session_epoch_id=e.session_epoch_id
                WHERE e.session_epoch_id=? AND g.process_generation_id=?
                """,
                (epoch.session_epoch_id, generation.process_generation_id),
            ).fetchone()
            decision = connection.execute(
                """
                SELECT payload_json FROM events
                WHERE aggregate_type='process_generation' AND aggregate_id=?
                  AND event_type='OHF_LAUNCH_DECISION'
                ORDER BY event_id DESC LIMIT 1
                """,
                (generation.process_generation_id,),
            ).fetchone()
            decision_payload = (
                _json_loads(decision["payload_json"], fallback={}) if decision else {}
            )
            if (
                item is None
                or item["attempt_id"] != epoch.attempt_id
                or item["attempt_id"] != row["attempt_id"]
                or item["epoch_worker"] != epoch.worker_id
                or item["epoch_worker"] != row["worker_id"]
                or int(item["epoch_number"]) != epoch.epoch_number
                or item["session_epoch_id"] != generation.session_epoch_id
                or item["generation_worker"] != generation.worker_id
                or item["generation_worker"] != row["worker_id"]
                or int(item["generation_number"]) != generation.generation_number
                or item["state"] != "CURRENT"
                or not item["executive_writer_held"]
                or not item["provider_session_id"]
                or decision_payload.get("decision") != LaunchDecision.ALLOW.value
            ):
                raise StateConflict(
                    "TX-5 requires exact owned refs and typed attestation with ALLOW"
                )
            self._require_active_orchestration_generation(
                connection,
                row=row,
                generation_id=generation.process_generation_id,
            )
            job_role = connection.execute(
                "SELECT orchestration_role FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            if (
                job_role is not None
                and job_role["orchestration_role"] is not None
                and generation.generation_number == 2
            ):
                g1 = connection.execute(
                    """SELECT process_generation_id FROM process_generations
                       WHERE session_epoch_id=? AND generation_number=1""",
                    (epoch.session_epoch_id,),
                ).fetchone()
                if g1 is None:
                    raise StateConflict("orchestration G2 lost its G1 recovery source")
                self._require_orchestration_g1_recovery_predicate(
                    connection,
                    row=row,
                    epoch=epoch,
                    g1_generation_id=str(g1["process_generation_id"]),
                    expected_generation_count=2,
                    allowed_successor_turn_command_id=operation_id.command_id,
                )
            existing_intent = self._event(connection, operation_id.command_id)
            if existing_intent is not None:
                payload = _json_loads(existing_intent["payload_json"], fallback={})
                if (
                    existing_intent["event_type"] != OperationReceiptKind.INTENT.value
                    or existing_intent["aggregate_id"] != operation_id.command_id
                    or payload.get("operation_kind") != OperationKind.BEGIN_TURN.value
                    or payload.get("attempt_id") != epoch.attempt_id
                    or payload.get("session_epoch_id") != epoch.session_epoch_id
                    or payload.get("process_generation_id")
                    != generation.process_generation_id
                    or payload.get("worker_id") != epoch.worker_id
                    or self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.APPLIED
                        ),
                    )
                    is not None
                    or self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.EFFECT_UNKNOWN
                        ),
                    )
                    is not None
                ):
                    raise StateConflict("TX-5 operation is not retryable")
                return TurnRef(
                    str(payload.get("turn_id")),
                    epoch.session_epoch_id,
                    generation.process_generation_id,
                    epoch.attempt_id,
                )
            if job_role is not None and job_role["orchestration_role"] is not None:
                tx5_rows: list[dict[str, Any]] = []
                for prior in connection.execute(
                    """SELECT payload_json FROM events
                       WHERE aggregate_type='operator_operation' AND event_type=?
                         AND attempt_id=?""",
                    (OperationReceiptKind.INTENT.value, row["attempt_id"]),
                ):
                    prior_payload = _json_loads(prior["payload_json"], fallback={})
                    if prior_payload.get("operation_kind") == OperationKind.BEGIN_TURN.value:
                        tx5_rows.append(prior_payload)
                if len(tx5_rows) >= 2 or any(
                    item.get("process_generation_id") == generation.process_generation_id
                    for item in tx5_rows
                ):
                    raise StateConflict("orchestration TX-5 cardinality is exhausted")
            turn = TurnRef(
                f"ohf-turn-{uuid4().hex}",
                epoch.session_epoch_id,
                generation.process_generation_id,
                epoch.attempt_id,
            )
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.INTENT,
                row=row,
                payload={
                    "schema_version": "mastermind.operator_harness_turn_intent/v1",
                    "operation_kind": "begin_turn",
                    "attempt_id": epoch.attempt_id,
                    "session_epoch_id": epoch.session_epoch_id,
                    "process_generation_id": generation.process_generation_id,
                    "worker_id": row["worker_id"],
                    "provider_session_id": item["provider_session_id"],
                    "turn_id": turn.turn_id,
                },
            )
        return turn

    def acknowledge_turn(
        self,
        *,
        turn: TurnRef,
        operation_id: OperationId,
        fence_generation: int,
        lease_token: str,
        observation: TurnStartObservation | None = None,
    ) -> bool:
        timestamp = self.store.now_ms()
        if observation is not None and not observation.acknowledged:
            raise StateConflict("TX-5 provider did not acknowledge the turn")
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=turn.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            intent = self._event(connection, operation_id.command_id)
            intent_payload = (
                _json_loads(intent["payload_json"], fallback={}) if intent else {}
            )
            durable = connection.execute(
                """SELECT e.attempt_id,e.worker_id AS epoch_worker,e.provider_session_id,
                          e.state,g.worker_id AS generation_worker,g.executive_writer_held
                   FROM harness_session_epochs e JOIN process_generations g
                     ON g.session_epoch_id=e.session_epoch_id
                   WHERE e.session_epoch_id=? AND g.process_generation_id=?""",
                (turn.session_epoch_id, turn.process_generation_id),
            ).fetchone()
            expected_intent = {
                "schema_version": "mastermind.operator_harness_turn_intent/v1",
                "operation_kind": OperationKind.BEGIN_TURN.value,
                "attempt_id": turn.attempt_id,
                "session_epoch_id": turn.session_epoch_id,
                "process_generation_id": turn.process_generation_id,
                "worker_id": str(row["worker_id"]),
                "provider_session_id": (
                    None if durable is None else durable["provider_session_id"]
                ),
                "turn_id": turn.turn_id,
            }
            if (
                intent is None
                or intent["event_type"] != OperationReceiptKind.INTENT.value
                or intent["aggregate_id"] != operation_id.command_id
                or intent["attempt_id"] != turn.attempt_id
                or intent["worker_id"] != row["worker_id"]
                or intent_payload != expected_intent
                or durable is None
                or durable["attempt_id"] != turn.attempt_id
                or durable["epoch_worker"] != row["worker_id"]
                or durable["generation_worker"] != row["worker_id"]
                or durable["state"] != SessionEpochState.CURRENT.value
                or not durable["executive_writer_held"]
            ):
                raise StateConflict("TX-5 target mismatch")
            self._require_active_orchestration_generation(
                connection,
                row=row,
                generation_id=turn.process_generation_id,
            )
            applied_payload = {
                "schema_version": "mastermind.operator_harness_turn_applied/v1",
                "operation_kind": OperationKind.BEGIN_TURN.value,
                "attempt_id": turn.attempt_id,
                "session_epoch_id": turn.session_epoch_id,
                "process_generation_id": turn.process_generation_id,
                "turn_id": turn.turn_id,
                "provider_native_turn_id": (
                    None if observation is None else observation.provider_native_turn_id
                ),
                "acknowledged": (
                    True if observation is None else observation.acknowledged
                ),
            }
            applied_id = operation_receipt_command_id(
                operation_id, OperationReceiptKind.APPLIED
            )
            applied = self._event(connection, applied_id)
            if applied is not None:
                if _json_loads(applied["payload_json"], fallback={}) == applied_payload:
                    return
                raise StateConflict("TX-5 already applied differently")
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.APPLIED,
                row=row,
                payload=applied_payload,
            )

    def generation_refs(
        self, process_generation_id: str
    ) -> tuple[SessionEpochRef, ProcessGenerationRef]:
        """Reconstruct Executive identities from authoritative OHF rows."""

        with self.store.read() as connection:
            row = connection.execute(
                """
                SELECT g.process_generation_id,g.session_epoch_id,g.generation_number,
                       g.worker_id,e.attempt_id,e.epoch_number
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (process_generation_id,),
            ).fetchone()
        if row is None:
            raise StateConflict("unknown OHF generation")
        epoch = SessionEpochRef(
            str(row["session_epoch_id"]),
            str(row["attempt_id"]),
            str(row["worker_id"]),
            int(row["epoch_number"]),
        )
        generation = ProcessGenerationRef(
            str(row["process_generation_id"]),
            str(row["session_epoch_id"]),
            int(row["generation_number"]),
            str(row["worker_id"]),
        )
        return epoch, generation

    def current_writer_generation(self, epoch: SessionEpochRef) -> ProcessGenerationRef:
        """Return the one durable Executive writer for a CURRENT epoch."""

        with self.store.read() as connection:
            row = connection.execute(
                """
                SELECT g.process_generation_id,g.session_epoch_id,
                       g.generation_number,g.worker_id,e.attempt_id,e.state
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE e.session_epoch_id=? AND g.executive_writer_held=1
                """,
                (epoch.session_epoch_id,),
            ).fetchone()
        if (
            row is None
            or row["attempt_id"] != epoch.attempt_id
            or row["worker_id"] != epoch.worker_id
            or row["state"] != SessionEpochState.CURRENT.value
        ):
            raise StateConflict("CURRENT epoch has no matching Executive writer")
        return ProcessGenerationRef(
            str(row["process_generation_id"]),
            str(row["session_epoch_id"]),
            int(row["generation_number"]),
            str(row["worker_id"]),
        )

    def record_effect_unknown(
        self,
        *,
        attempt_id: str,
        operation_id: OperationId,
        fence_generation: int,
        lease_token: str,
        phase: str,
        detail: str,
    ) -> bool:
        """Persist EFFECT_UNKNOWN, returning False when APPLIED already won."""

        timestamp = self.store.now_ms()
        bounded_phase = str(phase or "").strip()[:64]
        bounded_detail = str(detail or "").strip()[:512]
        if not bounded_phase:
            raise StateConflict("EFFECT_UNKNOWN phase is required")
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            intent = self._event(connection, operation_id.command_id)
            if (
                intent is None
                or intent["event_type"] != OperationReceiptKind.INTENT.value
                or intent["attempt_id"] != attempt_id
            ):
                raise StateConflict("EFFECT_UNKNOWN requires its committed INTENT")
            receipt_id = operation_receipt_command_id(
                operation_id, OperationReceiptKind.EFFECT_UNKNOWN
            )
            existing = self._event(connection, receipt_id)
            payload = {
                "schema_version": "mastermind.operator_harness_effect_unknown/v1",
                "phase": bounded_phase,
                "detail": bounded_detail,
            }
            if existing is not None:
                if _json_loads(existing["payload_json"], fallback={}) == payload:
                    return True
                raise StateConflict("EFFECT_UNKNOWN already recorded differently")
            if (
                self._event(
                    connection,
                    operation_receipt_command_id(
                        operation_id, OperationReceiptKind.APPLIED
                    ),
                )
                is not None
            ):
                return False
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.EFFECT_UNKNOWN,
                row=row,
                payload=payload,
            )
            return True

    def record_candidate_evidence(
        self,
        *,
        turn: TurnRef,
        candidate: CandidateResult,
        events: Sequence[NormalizedEvent],
        cursor: EventCursor,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        """Persist provider output as evidence only; never mutate Job completion."""

        if candidate.complete_job_permitted:
            raise StateConflict("OHF candidate cannot complete a Job")
        candidate = dataclasses.replace(
            candidate,
            summary=(
                None
                if candidate.summary is None
                else redact_evidence_text(candidate.summary)
            ),
        )
        events = tuple(
            dataclasses.replace(
                event,
                provider_event_id=(
                    None
                    if event.provider_event_id is None
                    else redact_evidence_text(event.provider_event_id)
                ),
                payload_redacted=redact_evidence(event.payload_redacted),
            )
            for event in events
        )
        if (
            candidate.attempt_id != turn.attempt_id
            or candidate.session_epoch_id != turn.session_epoch_id
            or candidate.process_generation_id != turn.process_generation_id
            or cursor.attempt_id != turn.attempt_id
            or cursor.session_epoch_id != turn.session_epoch_id
            or cursor.process_generation_id != turn.process_generation_id
            or cursor.turn_id != turn.turn_id
        ):
            raise StateConflict("candidate/event evidence is outside the turn scope")
        for event in events:
            if (
                event.attempt_id != turn.attempt_id
                or event.session_epoch_id != turn.session_epoch_id
                or event.process_generation_id != turn.process_generation_id
                or event.turn_id not in {None, turn.turn_id}
            ):
                raise StateConflict("normalized event is outside the turn scope")
        timestamp = self.store.now_ms()
        command_id = f"ohf-candidate:{turn.turn_id}"
        payload = {
            "schema_version": OHF_CANDIDATE_EVIDENCE_SCHEMA_VERSION,
            "turn": _ohf_jsonable(turn),
            "candidate": _ohf_jsonable(candidate),
            "events": _ohf_jsonable(tuple(events)),
            "cursor": _ohf_jsonable(cursor),
        }
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=turn.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            self._require_active_orchestration_generation(
                connection,
                row=row,
                generation_id=turn.process_generation_id,
            )
            generation = connection.execute(
                """
                SELECT 1 FROM process_generations
                WHERE process_generation_id=? AND session_epoch_id=?
                """,
                (turn.process_generation_id, turn.session_epoch_id),
            ).fetchone()
            if generation is None:
                raise StateConflict("candidate generation does not exist")
            matching_intents: list[tuple[sqlite3.Row, dict[str, Any]]] = []
            for intent in connection.execute(
                """SELECT * FROM events
                   WHERE aggregate_type='operator_operation'
                     AND event_type=? AND attempt_id=?""",
                (OperationReceiptKind.INTENT.value, turn.attempt_id),
            ):
                intent_payload = _json_loads(intent["payload_json"], fallback={})
                if intent_payload.get("turn_id") == turn.turn_id:
                    matching_intents.append((intent, intent_payload))
            if len(matching_intents) != 1:
                raise StateConflict(
                    "candidate requires exactly one matching TX-5 INTENT"
                )
            intent, intent_payload = matching_intents[0]
            expected_intent = {
                "schema_version": "mastermind.operator_harness_turn_intent/v1",
                "operation_kind": OperationKind.BEGIN_TURN.value,
                "attempt_id": turn.attempt_id,
                "session_epoch_id": turn.session_epoch_id,
                "process_generation_id": turn.process_generation_id,
                "worker_id": str(row["worker_id"]),
                "provider_session_id": intent_payload.get("provider_session_id"),
                "turn_id": turn.turn_id,
            }
            if (
                intent["aggregate_id"] != intent["command_id"]
                or intent["worker_id"] != row["worker_id"]
                or not intent_payload.get("provider_session_id")
                or intent_payload != expected_intent
            ):
                raise StateConflict("candidate TX-5 INTENT provenance mismatch")
            operation = OperationId(str(intent["command_id"]))
            applied = self._event(
                connection,
                operation_receipt_command_id(operation, OperationReceiptKind.APPLIED),
            )
            applied_payload = (
                _json_loads(applied["payload_json"], fallback={}) if applied else {}
            )
            if (
                applied is None
                or applied["aggregate_type"] != "operator_operation"
                or applied["aggregate_id"] != operation.command_id
                or applied["event_type"] != OperationReceiptKind.APPLIED.value
                or applied["attempt_id"] != turn.attempt_id
                or applied["worker_id"] != row["worker_id"]
                or applied_payload.get("schema_version")
                != "mastermind.operator_harness_turn_applied/v1"
                or applied_payload.get("operation_kind")
                != OperationKind.BEGIN_TURN.value
                or applied_payload.get("attempt_id") != turn.attempt_id
                or applied_payload.get("session_epoch_id") != turn.session_epoch_id
                or applied_payload.get("process_generation_id")
                != turn.process_generation_id
                or applied_payload.get("turn_id") != turn.turn_id
                or applied_payload.get("acknowledged") is not True
                or set(applied_payload)
                != {
                    "schema_version",
                    "operation_kind",
                    "attempt_id",
                    "session_epoch_id",
                    "process_generation_id",
                    "turn_id",
                    "provider_native_turn_id",
                    "acknowledged",
                }
            ):
                raise StateConflict("candidate requires exact matching TX-5 APPLIED")
            existing = self._event(connection, command_id)
            if existing is not None:
                if _json_loads(existing["payload_json"], fallback={}) == payload:
                    return
                raise StateConflict("candidate evidence already recorded differently")
            self.store.append_event(
                connection,
                aggregate_type="operator_turn",
                aggregate_id=turn.turn_id,
                event_type="OHF_CANDIDATE_RESULT_RECORDED",
                command_id=command_id,
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=turn.attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload=payload,
                timestamp_ms=timestamp,
            )

    def seal_orchestration_role_result(
        self,
        *,
        turn: TurnRef,
        observation: Any,
        fence_generation: int,
        lease_token: str,
    ) -> dict[str, Any]:
        """Seal one complete typed OHF role result before process shutdown."""

        from control_plane.executive_orchestration_result import (
            RawRoleResultObservation,
            canonical_digest as result_digest,
            parse_and_validate_envelope,
        )

        if not isinstance(observation, RawRoleResultObservation):
            raise StateConflict("role result seal requires typed raw observation")
        if (
            observation.attempt_id != turn.attempt_id
            or observation.session_epoch_id != turn.session_epoch_id
            or observation.process_generation_id != turn.process_generation_id
            or observation.turn_id != turn.turn_id
        ):
            raise StateConflict("raw role result observation is outside the turn")
        timestamp = self.store.now_ms()
        command_id = f"orchestration-result-seal:{turn.attempt_id}"
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=turn.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            job = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
            ).fetchone()
            if job is None or job["orchestration_role"] is None:
                raise StateConflict("role result seal requires an orchestration Job")
            role = str(job["orchestration_role"])
            admission = self._require_active_orchestration_generation(
                connection,
                row=row,
                generation_id=turn.process_generation_id,
            )
            assert admission is not None
            candidate_rows = connection.execute(
                """SELECT * FROM events
                   WHERE event_type='OHF_CANDIDATE_RESULT_RECORDED' AND attempt_id=?
                   ORDER BY event_id""",
                (turn.attempt_id,),
            ).fetchall()
            if len(candidate_rows) != 1:
                raise StateConflict("role result requires exactly one candidate Event")
            candidate_event = candidate_rows[0]
            candidate_payload = _strict_canonical_json_loads(
                str(candidate_event["payload_json"]), name="OHF candidate Event"
            )
            candidate = (
                candidate_payload.get("candidate")
                if isinstance(candidate_payload, dict)
                else None
            )
            candidate_turn = (
                candidate_payload.get("turn")
                if isinstance(candidate_payload, dict)
                else None
            )
            tx5_applied_rows: list[tuple[sqlite3.Row, dict[str, Any]]] = []
            for event in connection.execute(
                """SELECT * FROM events
                   WHERE aggregate_type='operator_operation' AND event_type=?
                     AND attempt_id=? ORDER BY event_id""",
                (OperationReceiptKind.APPLIED.value, turn.attempt_id),
            ):
                value = _json_loads(event["payload_json"], fallback={})
                if (
                    value.get("operation_kind") == OperationKind.BEGIN_TURN.value
                    and value.get("turn_id") == turn.turn_id
                ):
                    tx5_applied_rows.append((event, value))
            if len(tx5_applied_rows) != 1:
                raise StateConflict("role result lost its exact TX-5 APPLIED receipt")
            _tx5_event, tx5_payload = tx5_applied_rows[0]
            try:
                envelope = parse_and_validate_envelope(
                    observation.canonical_result_json,
                    expected_job_id=str(job["job_id"]),
                    expected_run_id=str(row["attempt_id"]),
                    expected_worker_id=str(row["worker_id"]),
                    expected_role=role,
                    expected_root_job_id=str(job["root_job_id"]),
                )
            except Exception:
                raise StateConflict(
                    "raw orchestration result failed closed validation"
                ) from None
            observation_value = observation.to_dict()
            candidate_digest = orchestration_digest(candidate_payload)
            result_envelope_digest = result_digest(envelope)
            seal_payload = {
                "schema_version": "mastermind.orchestration_role_result_seal/v1",
                "job_id": str(job["job_id"]),
                "attempt_id": str(row["attempt_id"]),
                "worker_id": str(row["worker_id"]),
                "quota_class": str(row["quota_class"]),
                "orchestration_role": role,
                "session_epoch_id": turn.session_epoch_id,
                "process_generation_id": turn.process_generation_id,
                "turn_id": turn.turn_id,
                "provider_session_id": observation.provider_session_id,
                "provider_native_turn_id": observation.provider_native_turn_id,
                "provider_turn_artifact_digest": observation.provider_turn_artifact_digest,
                "raw_result_observation_digest": result_digest(observation_value),
                "canonical_result_byte_length": observation.canonical_result_byte_length,
                "candidate_event_command_id": str(candidate_event["command_id"]),
                "candidate_event_digest": candidate_digest,
                "result_envelope": envelope,
                "result_envelope_digest": result_envelope_digest,
                "role_result_digest": result_digest(envelope["role_result"]),
                "work_admission_command_id": f"ohf-work-admit:{turn.process_generation_id}",
                "observed_attestation_digest": admission["observed_attestation_digest"],
                "execution_principal_snapshot_digest": str(
                    row["execution_principal_snapshot_digest"]
                ),
                "placement_snapshot_digest": str(row["placement_snapshot_digest"]),
                "effective_grant_digest": str(row["effective_grant_digest"]),
                "policy_sha": CooCyclePolicy.load().policy_sha256,
            }
            existing = self._event(connection, command_id)
            if existing is not None:
                if (
                    existing["event_type"] == "ORCHESTRATION_ROLE_RESULT_SEALED"
                    and existing["attempt_id"] == row["attempt_id"]
                    and _strict_canonical_json_loads(
                        str(existing["payload_json"]),
                        name="orchestration result seal replay",
                    )
                    == seal_payload
                ):
                    return seal_payload
                raise StateConflict("role result seal command replay drifted")
            if (
                candidate_event["command_id"] != f"ohf-candidate:{turn.turn_id}"
                or candidate_event["aggregate_type"] != "operator_turn"
                or candidate_event["aggregate_id"] != turn.turn_id
                or candidate_event["attempt_id"] != row["attempt_id"]
                or not isinstance(candidate, dict)
                or not isinstance(candidate_turn, dict)
                or candidate.get("artifact_digest")
                != observation.provider_turn_artifact_digest
                or candidate.get("attempt_id") != turn.attempt_id
                or candidate.get("session_epoch_id") != turn.session_epoch_id
                or candidate.get("process_generation_id") != turn.process_generation_id
                or candidate_turn != _ohf_jsonable(turn)
                or observation.provider_session_id
                != tx5_payload.get("provider_session_id", admission["provider_session_id"])
                or observation.provider_session_id != admission["provider_session_id"]
                or observation.provider_native_turn_id
                != tx5_payload.get("provider_native_turn_id")
                or observation.canonical_result_digest != result_envelope_digest
            ):
                raise StateConflict("role result observation/candidate binding is invalid")
            self.store.append_event(
                connection,
                aggregate_type="attempt",
                aggregate_id=str(row["attempt_id"]),
                event_type="ORCHESTRATION_ROLE_RESULT_SEALED",
                command_id=command_id,
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=str(row["attempt_id"]),
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload=seal_payload,
                timestamp_ms=timestamp,
            )
            return seal_payload

    def reserve_generation_operation(
        self,
        *,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        operation_kind: str,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        """Commit an internal stop/cancel INTENT before the adapter call."""

        kind = str(operation_kind or "").strip()
        if kind not in {"graceful_stop", "cancel"}:
            raise StateConflict("unsupported internal generation operation")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            found = connection.execute(
                """
                SELECT g.*,e.attempt_id,e.state,e.epoch_number,
                       e.worker_id AS epoch_worker,
                       e.provider_session_id AS epoch_session
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            if found is None:
                raise StateConflict("unknown OHF generation")
            row = self._leased(
                connection,
                attempt_id=str(found["attempt_id"]),
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                    AttemptStatus.CANCEL_REQUESTED,
                },
            )
            epoch = SessionEpochRef(
                str(found["session_epoch_id"]),
                str(found["attempt_id"]),
                str(found["epoch_worker"]),
                int(found["epoch_number"]),
            )
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=generation,
                require_current=True,
                require_writer=True,
            )
            if (
                self._event(connection, operation_id.command_id) is not None
                or found["state"] != SessionEpochState.CURRENT.value
                or not found["executive_writer_held"]
                or found["ended_at_ms"] is not None
            ):
                raise StateConflict("generation operation INTENT preconditions failed")
            payload = {
                "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
                "operation_kind": kind,
                "attempt_id": str(found["attempt_id"]),
                "session_epoch_id": generation.session_epoch_id,
                "process_generation_id": generation.process_generation_id,
                "worker_id": generation.worker_id,
                "provider_session_id": found["epoch_session"],
            }
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.INTENT,
                row=row,
                payload=payload,
            )

    def apply_generation_operation(
        self,
        *,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        operation_kind: str,
        observation: ReconcileObservation,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        """Apply stop/cancel only from an exact committed internal INTENT."""

        kind = str(operation_kind or "").strip()
        if kind not in {"graceful_stop", "cancel"}:
            raise StateConflict("unsupported internal generation operation")
        if observation.process_liveness is not ProcessLiveness.PROVEN_DEAD:
            raise StateConflict("generation operation requires PROVEN_DEAD")
        if (
            kind == "graceful_stop"
            and observation.provider_writer_state is not ProviderWriterState.RELEASED
        ):
            raise StateConflict("graceful stop requires provider RELEASED")
        pid, pgid, start, boot = _ohf_process(observation.observed_process)
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            found = connection.execute(
                """
                SELECT g.*,e.attempt_id,e.state,e.epoch_number,
                       e.worker_id AS epoch_worker,
                       e.provider_session_id AS epoch_session
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            if found is None:
                raise StateConflict("unknown OHF generation")
            row = self._leased(
                connection,
                attempt_id=str(found["attempt_id"]),
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={
                    AttemptStatus.RUNNING,
                    AttemptStatus.CHECKPOINTED,
                    AttemptStatus.CANCEL_REQUESTED,
                },
            )
            epoch = SessionEpochRef(
                str(found["session_epoch_id"]),
                str(found["attempt_id"]),
                str(found["epoch_worker"]),
                int(found["epoch_number"]),
            )
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=generation,
                require_current=True,
                require_writer=True,
            )
            expected = {
                "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
                "operation_kind": kind,
                "attempt_id": str(found["attempt_id"]),
                "session_epoch_id": generation.session_epoch_id,
                "process_generation_id": generation.process_generation_id,
                "worker_id": generation.worker_id,
                "provider_session_id": found["epoch_session"],
            }
            intent = self._event(connection, operation_id.command_id)
            intent_payload = (
                _json_loads(intent["payload_json"], fallback={}) if intent else {}
            )
            if (
                intent is None
                or intent["event_type"] != OperationReceiptKind.INTENT.value
                or intent_payload != expected
                or (
                    found["pid"],
                    found["pgid"],
                    found["process_start_identity"],
                    found["boot_id"],
                )
                != (pid, pgid, start, boot)
                or observation.observed_provider_session_id
                not in {None, found["epoch_session"]}
            ):
                raise StateConflict("generation operation result does not match INTENT")
            applied_id = operation_receipt_command_id(
                operation_id, OperationReceiptKind.APPLIED
            )
            if self._event(connection, applied_id) is not None:
                return
            release = kind == "graceful_stop"
            connection.execute(
                """
                UPDATE process_generations
                SET ended_at_ms=?,last_observed_at_ms=?,provider_writer_state=?,
                    executive_writer_held=?
                WHERE process_generation_id=?
                """,
                (
                    timestamp,
                    timestamp,
                    observation.provider_writer_state.value,
                    0 if release else 1,
                    generation.process_generation_id,
                ),
            )
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.APPLIED,
                row=row,
                payload={
                    "schema_version": OHF_INTERNAL_GENERATION_OPERATION_SCHEMA_VERSION,
                    "operation_kind": kind,
                    "process_generation_id": generation.process_generation_id,
                    "process_liveness": observation.process_liveness.value,
                    "provider_writer_state": observation.provider_writer_state.value,
                    "executive_writer_released": release,
                },
            )

    def record_reconcile_observation(
        self,
        *,
        generation: ProcessGenerationRef,
        observation: ReconcileObservation,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        """Persist observations without accepting caller-supplied authority."""

        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            found = connection.execute(
                """
                SELECT g.*,e.attempt_id,e.state,e.epoch_number,
                       e.worker_id AS epoch_worker,
                       e.provider_session_id AS epoch_session
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            if found is None:
                raise StateConflict("unknown OHF generation")
            row = self._leased(
                connection,
                attempt_id=str(found["attempt_id"]),
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            epoch = SessionEpochRef(
                str(found["session_epoch_id"]),
                str(found["attempt_id"]),
                str(found["epoch_worker"]),
                int(found["epoch_number"]),
            )
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=generation,
                require_current=True,
            )
            if observation.process_liveness is ProcessLiveness.UNKNOWN:
                if observation.observed_process != ProcessIdentityObservation():
                    raise StateConflict(
                        "UNKNOWN liveness cannot assert process identity"
                    )
            else:
                pid, pgid, start, boot = _ohf_process(observation.observed_process)
                if (
                    found["pid"],
                    found["pgid"],
                    found["process_start_identity"],
                    found["boot_id"],
                ) != (pid, pgid, start, boot):
                    raise StateConflict("reconcile process identity mismatch")
            if observation.observed_provider_session_id not in {
                None,
                found["epoch_session"],
            }:
                raise StateConflict("reconcile provider session mismatch")
            if observation.observed_config_digest is not None:
                attestation = _json_loads(
                    found["observed_attestation_json"], fallback={}
                )
                if (
                    attestation.get("effective_config_digest")
                    != observation.observed_config_digest
                ):
                    raise StateConflict("reconcile config digest mismatch")
            ended = (
                timestamp
                if observation.process_liveness is ProcessLiveness.PROVEN_DEAD
                else found["ended_at_ms"]
            )
            connection.execute(
                """
                UPDATE process_generations
                SET ended_at_ms=?,last_observed_at_ms=?,provider_writer_state=?
                WHERE process_generation_id=?
                """,
                (
                    ended,
                    timestamp,
                    observation.provider_writer_state.value,
                    generation.process_generation_id,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="process_generation",
                aggregate_id=generation.process_generation_id,
                event_type="OHF_RECONCILE_OBSERVED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=str(row["attempt_id"]),
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={
                    "schema_version": OHF_RECONCILE_OBSERVATION_SCHEMA_VERSION,
                    "process_generation_id": generation.process_generation_id,
                    "observation": _ohf_jsonable(observation),
                },
                timestamp_ms=timestamp,
            )

    def record_hard_process_death(
        self,
        *,
        generation: ProcessGenerationRef,
        observation: ReconcileObservation,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        if observation.process_liveness is not ProcessLiveness.PROVEN_DEAD:
            raise StateConflict(
                "hard process death requires typed PROVEN_DEAD observation"
            )
        self.record_reconcile_observation(
            generation=generation,
            observation=observation,
            fence_generation=fence_generation,
            lease_token=lease_token,
        )

    def record_graceful_stop(
        self,
        *,
        generation: ProcessGenerationRef,
        observation: ReconcileObservation,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        if (
            observation.process_liveness is not ProcessLiveness.PROVEN_DEAD
            or observation.provider_writer_state is not ProviderWriterState.RELEASED
        ):
            raise StateConflict(
                "TX-6 requires typed PROVEN_DEAD and RELEASED observation"
            )
        self.record_reconcile_observation(
            generation=generation,
            observation=observation,
            fence_generation=fence_generation,
            lease_token=lease_token,
        )
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            found = connection.execute(
                """
                SELECT g.*,e.attempt_id,e.state,e.epoch_number,
                       e.worker_id AS epoch_worker
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            if found is None:
                raise StateConflict("unknown OHF generation")
            row = self._leased(
                connection,
                attempt_id=str(found["attempt_id"]),
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            epoch = SessionEpochRef(
                str(found["session_epoch_id"]),
                str(found["attempt_id"]),
                str(found["epoch_worker"]),
                int(found["epoch_number"]),
            )
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=generation,
                require_current=True,
                require_writer=True,
            )
            if found["ended_at_ms"] is None:
                raise StateConflict("TX-6 requires process PROVEN_DEAD")
            connection.execute(
                """
                UPDATE process_generations
                SET provider_writer_state='RELEASED',executive_writer_held=0,
                    last_observed_at_ms=?
                WHERE process_generation_id=?
                """,
                (timestamp, generation.process_generation_id),
            )
            self.store.append_event(
                connection,
                aggregate_type="process_generation",
                aggregate_id=generation.process_generation_id,
                event_type="OHF_GRACEFUL_STOP",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=str(row["attempt_id"]),
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"writer_released": True},
                timestamp_ms=timestamp,
            )

    def record_provider_writer_observation(
        self,
        *,
        generation: ProcessGenerationRef,
        observation: ReconcileObservation,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        """Persist a typed observation without clearing Executive writer authority."""
        self.record_reconcile_observation(
            generation=generation,
            observation=observation,
            fence_generation=fence_generation,
            lease_token=lease_token,
        )

    def abandon_epoch(
        self, *, epoch: SessionEpochRef, fence_generation: int, lease_token: str
    ) -> None:
        """TX-8: only an observed-dead epoch may lose its Executive writer."""
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=epoch.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            item = connection.execute(
                """
                SELECT state,worker_id,epoch_number
                FROM harness_session_epochs
                WHERE session_epoch_id=? AND attempt_id=?
                """,
                (epoch.session_epoch_id, epoch.attempt_id),
            ).fetchone()
            live = connection.execute(
                "SELECT 1 FROM process_generations WHERE session_epoch_id=? AND ended_at_ms IS NULL",
                (epoch.session_epoch_id,),
            ).fetchone()
            if (
                item is None
                or item["worker_id"] != epoch.worker_id
                or item["worker_id"] != row["worker_id"]
                or int(item["epoch_number"]) != epoch.epoch_number
                or item["state"] != "CURRENT"
                or live is not None
            ):
                raise StateConflict(
                    "TX-8 requires an exact CURRENT epoch with all processes PROVEN_DEAD"
                )
            connection.execute(
                "UPDATE harness_session_epochs SET state='ABANDONED',ended_at_ms=? WHERE session_epoch_id=?",
                (timestamp, epoch.session_epoch_id),
            )
            connection.execute(
                "UPDATE process_generations SET executive_writer_held=0 WHERE session_epoch_id=?",
                (epoch.session_epoch_id,),
            )
            self.store.append_event(
                connection,
                aggregate_type="harness_session_epoch",
                aggregate_id=epoch.session_epoch_id,
                event_type="OHF_EPOCH_ABANDONED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=epoch.attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={"transaction_group": "TX-8"},
                timestamp_ms=timestamp,
            )

    def _require_orchestration_g1_recovery_predicate(
        self,
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        epoch: SessionEpochRef,
        g1_generation_id: str,
        expected_generation_count: int,
        allowed_successor_turn_command_id: str | None = None,
    ) -> None:
        """Re-derive the closed Phase 1F-C G1 pre-candidate loss state.

        This is additive to ordinary P1B resume safety and is called inside both
        TX-10 allocation and the later G2 TX-5 reservation transaction.  It never
        trusts a supervisor boolean or model-authored assertion.
        """

        job = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
        ).fetchone()
        if job is None or job["orchestration_role"] is None:
            return
        epochs = connection.execute(
            "SELECT * FROM harness_session_epochs WHERE attempt_id=? ORDER BY epoch_number",
            (row["attempt_id"],),
        ).fetchall()
        generations = connection.execute(
            """SELECT g.* FROM process_generations g
               JOIN harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id
               WHERE e.attempt_id=? ORDER BY e.epoch_number,g.generation_number""",
            (row["attempt_id"],),
        ).fetchall()
        g1 = next(
            (
                item
                for item in generations
                if item["process_generation_id"] == g1_generation_id
            ),
            None,
        )
        if (
            len(epochs) != 1
            or epochs[0]["session_epoch_id"] != epoch.session_epoch_id
            or epochs[0]["state"] != SessionEpochState.CURRENT.value
            or epochs[0]["worker_id"] != row["worker_id"]
            or int(epochs[0]["epoch_number"]) != epoch.epoch_number
            or len(generations) != expected_generation_count
            or g1 is None
            or g1["session_epoch_id"] != epoch.session_epoch_id
            or g1["worker_id"] != row["worker_id"]
            or int(g1["generation_number"]) != 1
            or g1["ended_at_ms"] is None
            or g1["provider_writer_state"] != ProviderWriterState.RELEASED.value
            or not g1["observed_attestation_digest"]
        ):
            raise StateConflict("orchestration G1 recovery generation predicate failed")

        admission_rows = connection.execute(
            """SELECT * FROM events
               WHERE event_type='ORCHESTRATION_WORK_ADMITTED'
                 AND aggregate_type='process_generation' AND aggregate_id=?
                 AND attempt_id=? ORDER BY event_id""",
            (g1_generation_id, row["attempt_id"]),
        ).fetchall()
        decision_rows = connection.execute(
            """SELECT * FROM events
               WHERE event_type='OHF_LAUNCH_DECISION'
                 AND aggregate_type='process_generation' AND aggregate_id=?
                 AND attempt_id=? ORDER BY event_id""",
            (g1_generation_id, row["attempt_id"]),
        ).fetchall()
        if len(admission_rows) != 1 or len(decision_rows) != 1:
            raise StateConflict("orchestration G1 recovery lacks exact work admission")
        admission_event = admission_rows[0]
        admission = _strict_canonical_json_loads(
            str(admission_event["payload_json"]), name="G1 recovery work admission"
        )
        decision = _strict_canonical_json_loads(
            str(decision_rows[0]["payload_json"]), name="G1 recovery launch decision"
        )
        admission_keys = {
            "schema_version", "job_id", "attempt_id", "worker_id", "quota_class",
            "orchestration_role", "process_generation_id", "provider_session_id",
            "tx3_applied_command_id", "observed_attestation_digest",
            "principal_observation", "principal_observation_digest",
            "execution_principal_snapshot_digest", "placement_snapshot_digest",
            "effective_grant_digest", "policy_sha", "launch_decision",
        }
        _validated_admission_principal(row, admission)
        if (
            set(admission) != admission_keys
            or admission_event["command_id"] != f"ohf-work-admit:{g1_generation_id}"
            or admission_event["job_id"] != row["job_id"]
            or admission_event["worker_id"] != row["worker_id"]
            or admission_event["quota_class"] != row["quota_class"]
            or admission.get("schema_version")
            != "mastermind.orchestration_work_admission/v1"
            or admission.get("job_id") != row["job_id"]
            or admission.get("attempt_id") != row["attempt_id"]
            or admission.get("worker_id") != row["worker_id"]
            or admission.get("quota_class") != row["quota_class"]
            or admission.get("orchestration_role") != job["orchestration_role"]
            or admission.get("process_generation_id") != g1_generation_id
            or admission.get("provider_session_id") != epochs[0]["provider_session_id"]
            or admission.get("observed_attestation_digest")
            != g1["observed_attestation_digest"]
            or admission.get("execution_principal_snapshot_digest")
            != row["execution_principal_snapshot_digest"]
            or admission.get("placement_snapshot_digest")
            != row["placement_snapshot_digest"]
            or admission.get("effective_grant_digest") != row["effective_grant_digest"]
            or admission.get("policy_sha") != CooCyclePolicy.load().policy_sha256
            or admission.get("launch_decision") != LaunchDecision.ALLOW.value
            or decision
            != {
                "decision": LaunchDecision.ALLOW.value,
                "attestation_digest": g1["observed_attestation_digest"],
            }
        ):
            raise StateConflict("orchestration G1 recovery admission predicate failed")

        turn_intents: list[tuple[sqlite3.Row, dict[str, Any]]] = []
        for event in connection.execute(
            """SELECT * FROM events
               WHERE aggregate_type='operator_operation' AND event_type=?
                 AND attempt_id=? ORDER BY event_id""",
            (OperationReceiptKind.INTENT.value, row["attempt_id"]),
        ):
            payload = _json_loads(event["payload_json"], fallback={})
            if payload.get("operation_kind") == OperationKind.BEGIN_TURN.value:
                turn_intents.append((event, payload))
        g1_turn_intents = [
            item
            for item in turn_intents
            if item[1].get("process_generation_id") == g1_generation_id
        ]
        successor_turn_intents = [
            item
            for item in turn_intents
            if item[1].get("process_generation_id") != g1_generation_id
        ]
        if len(g1_turn_intents) != 1:
            raise StateConflict("orchestration G1 recovery requires one TX-5 INTENT")
        if successor_turn_intents and (
            allowed_successor_turn_command_id is None
            or len(successor_turn_intents) != 1
            or successor_turn_intents[0][0]["command_id"]
            != allowed_successor_turn_command_id
        ):
            raise StateConflict("orchestration G1 recovery found a competing TX-5 INTENT")
        intent_event, intent = g1_turn_intents[0]
        turn_id = str(intent.get("turn_id") or "")
        intent_keys = {
            "schema_version", "operation_kind", "attempt_id", "session_epoch_id",
            "process_generation_id", "worker_id", "provider_session_id", "turn_id",
        }
        op = OperationId(str(intent_event["command_id"]))
        applied = self._event(
            connection,
            operation_receipt_command_id(op, OperationReceiptKind.APPLIED),
        )
        unknown = self._event(
            connection,
            operation_receipt_command_id(op, OperationReceiptKind.EFFECT_UNKNOWN),
        )
        applied_payload = (
            _strict_canonical_json_loads(
                str(applied["payload_json"]), name="G1 recovery TX-5 APPLIED"
            )
            if applied is not None
            else None
        )
        applied_keys = {
            "schema_version", "operation_kind", "attempt_id", "session_epoch_id",
            "process_generation_id", "turn_id", "provider_native_turn_id", "acknowledged",
        }
        if (
            set(intent) != intent_keys
            or intent_event["aggregate_id"] != intent_event["command_id"]
            or intent_event["job_id"] != row["job_id"]
            or intent_event["worker_id"] != row["worker_id"]
            or intent_event["quota_class"] != row["quota_class"]
            or intent.get("schema_version")
            != "mastermind.operator_harness_turn_intent/v1"
            or intent.get("attempt_id") != row["attempt_id"]
            or intent.get("session_epoch_id") != epoch.session_epoch_id
            or intent.get("process_generation_id") != g1_generation_id
            or intent.get("worker_id") != row["worker_id"]
            or intent.get("provider_session_id") != epochs[0]["provider_session_id"]
            or not turn_id
            or applied is None
            or unknown is not None
            or applied["event_type"] != OperationReceiptKind.APPLIED.value
            or applied["aggregate_type"] != "operator_operation"
            or applied["aggregate_id"] != intent_event["command_id"]
            or applied["job_id"] != row["job_id"]
            or applied["worker_id"] != row["worker_id"]
            or applied["quota_class"] != row["quota_class"]
            or not isinstance(applied_payload, dict)
            or set(applied_payload) != applied_keys
            or applied_payload.get("schema_version")
            != "mastermind.operator_harness_turn_applied/v1"
            or applied_payload.get("operation_kind") != OperationKind.BEGIN_TURN.value
            or applied_payload.get("attempt_id") != row["attempt_id"]
            or applied_payload.get("session_epoch_id") != epoch.session_epoch_id
            or applied_payload.get("process_generation_id") != g1_generation_id
            or applied_payload.get("turn_id") != turn_id
            or not isinstance(applied_payload.get("provider_native_turn_id"), str)
            or not applied_payload["provider_native_turn_id"].strip()
            or applied_payload.get("acknowledged") is not True
        ):
            raise StateConflict("orchestration G1 recovery TX-5 evidence is incomplete")

        competing = connection.execute(
            """SELECT 1 FROM events WHERE attempt_id=? AND event_type IN (
                 'JOB_CHECKPOINTED','OHF_CANDIDATE_RESULT_RECORDED',
                 'ORCHESTRATION_ROLE_RESULT_SEALED','JOB_COMPLETED',
                 'SEALED_WORKER_RESULT_COLLECTED'
               ) LIMIT 1""",
            (row["attempt_id"],),
        ).fetchone()
        if (
            int(row["checkpoint_sequence"]) != 0
            or row["checkpoint_json"] is not None
            or row["result_json"] is not None
            or job["checkpoint_json"] is not None
            or job["result_json"] is not None
            or competing is not None
        ):
            raise StateConflict("orchestration G1 recovery was closed by durable work evidence")

    def reserve_same_epoch_resume(
        self,
        *,
        epoch: SessionEpochRef,
        old_generation: ProcessGenerationRef,
        operation_id: OperationId,
        fence_generation: int,
        lease_token: str,
    ) -> ProcessGenerationRef:
        """TX-10: derive safety from stored evidence and allocate G2 only."""

        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=epoch.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            existing_intent = self._event(connection, operation_id.command_id)
            if existing_intent is not None:
                applied = self._event(
                    connection,
                    operation_receipt_command_id(
                        operation_id, OperationReceiptKind.APPLIED
                    ),
                )
                unknown = self._event(
                    connection,
                    operation_receipt_command_id(
                        operation_id, OperationReceiptKind.EFFECT_UNKNOWN
                    ),
                )
                existing_payload = _json_loads(
                    existing_intent["payload_json"], fallback={}
                )
                allocated = connection.execute(
                    """SELECT g.*,e.attempt_id,e.worker_id AS epoch_worker,
                                      e.provider_session_id AS epoch_session,e.state
                       FROM process_generations g
                       JOIN harness_session_epochs e
                         ON e.session_epoch_id=g.session_epoch_id
                       WHERE g.process_generation_id=?""",
                    (existing_payload.get("process_generation_id"),),
                ).fetchone()
                expected = {
                    "operation_kind": OperationKind.RESUME_SESSION.value,
                    "attempt_id": epoch.attempt_id,
                    "session_epoch_id": epoch.session_epoch_id,
                    "process_generation_id": (
                        None
                        if allocated is None
                        else allocated["process_generation_id"]
                    ),
                    "worker_id": epoch.worker_id,
                    "provider_session_id": (
                        None if allocated is None else allocated["epoch_session"]
                    ),
                }
                if (
                    applied is not None
                    or unknown is not None
                    or existing_intent["event_type"]
                    != OperationReceiptKind.INTENT.value
                    or existing_intent["aggregate_type"] != "operator_operation"
                    or existing_intent["aggregate_id"] != operation_id.command_id
                    or existing_intent["attempt_id"] != epoch.attempt_id
                    or existing_intent["worker_id"] != epoch.worker_id
                    or allocated is None
                    or allocated["session_epoch_id"] != epoch.session_epoch_id
                    or allocated["epoch_worker"] != epoch.worker_id
                    or allocated["state"] != SessionEpochState.CURRENT.value
                    or int(allocated["generation_number"]) != 2
                    or not allocated["executive_writer_held"]
                    or existing_payload != expected
                ):
                    raise StateConflict("TX-10 existing operation is not retryable")
                self._require_orchestration_g1_recovery_predicate(
                    connection,
                    row=row,
                    epoch=epoch,
                    g1_generation_id=old_generation.process_generation_id,
                    expected_generation_count=2,
                )
                retry_generation = ProcessGenerationRef(
                    str(allocated["process_generation_id"]),
                    str(allocated["session_epoch_id"]),
                    2,
                    str(allocated["worker_id"]),
                )
                self._owned_generation(
                    connection,
                    leased=row,
                    epoch=epoch,
                    generation=retry_generation,
                    require_current=True,
                    require_writer=True,
                )
                return retry_generation
            old = connection.execute(
                """
                SELECT g.*,e.state,e.provider_session_id AS epoch_session,
                       e.worker_id AS epoch_worker
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=? AND e.session_epoch_id=?
                """,
                (
                    old_generation.process_generation_id,
                    epoch.session_epoch_id,
                ),
            ).fetchone()
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=old_generation,
                require_current=True,
                require_writer=True,
            )
            newest_number = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(generation_number),0)
                    FROM process_generations WHERE session_epoch_id=?
                    """,
                    (epoch.session_epoch_id,),
                ).fetchone()[0]
            )
            launch = connection.execute(
                """
                SELECT payload_json FROM events
                WHERE aggregate_type='process_generation' AND aggregate_id=?
                  AND event_type='OHF_LAUNCH_DECISION'
                ORDER BY event_id DESC LIMIT 1
                """,
                (old_generation.process_generation_id,),
            ).fetchone()
            reconcile = connection.execute(
                """
                SELECT payload_json FROM events
                WHERE aggregate_type='process_generation' AND aggregate_id=?
                  AND event_type='OHF_RECONCILE_OBSERVED'
                ORDER BY event_id DESC LIMIT 1
                """,
                (old_generation.process_generation_id,),
            ).fetchone()
            launch_payload = (
                _json_loads(launch["payload_json"], fallback={}) if launch else {}
            )
            reconcile_payload = (
                _json_loads(reconcile["payload_json"], fallback={}) if reconcile else {}
            )
            observed = reconcile_payload.get("observation") or {}
            observed_process = observed.get("observed_process") or {}
            if (
                old is None
                or old["state"] != SessionEpochState.CURRENT.value
                or old["epoch_worker"] != epoch.worker_id
                or not old["executive_writer_held"]
                or old["ended_at_ms"] is None
                or old["provider_writer_state"] != ProviderWriterState.RELEASED.value
                or not old["provider_session_id"]
                or old["provider_session_id"] != old["epoch_session"]
                or int(old["generation_number"]) != 1
                or newest_number != 1
                or not old["observed_attestation_json"]
                or not old["observed_attestation_digest"]
                or launch_payload.get("decision") != LaunchDecision.ALLOW.value
                or launch_payload.get("attestation_digest")
                != old["observed_attestation_digest"]
                or reconcile_payload.get("schema_version")
                != OHF_RECONCILE_OBSERVATION_SCHEMA_VERSION
                or reconcile_payload.get("process_generation_id")
                != old_generation.process_generation_id
                or observed.get("process_liveness") != ProcessLiveness.PROVEN_DEAD.value
                or observed.get("provider_writer_state")
                != ProviderWriterState.RELEASED.value
                or observed_process.get("pid") != old["pid"]
                or observed_process.get("pgid") != old["pgid"]
                or observed_process.get("process_start_identity")
                != old["process_start_identity"]
                or observed_process.get("boot_id") != old["boot_id"]
            ):
                raise StateConflict("TX-10 derived recovery preconditions failed")
            self._require_orchestration_g1_recovery_predicate(
                connection,
                row=row,
                epoch=epoch,
                g1_generation_id=old_generation.process_generation_id,
                expected_generation_count=1,
            )
            generation = ProcessGenerationRef(
                f"ohf-generation-{uuid4().hex}",
                epoch.session_epoch_id,
                2,
                epoch.worker_id,
            )
            connection.execute(
                """
                UPDATE process_generations SET executive_writer_held=0
                WHERE process_generation_id=?
                """,
                (old_generation.process_generation_id,),
            )
            connection.execute(
                """
                INSERT INTO process_generations(
                  process_generation_id,session_epoch_id,worker_id,
                  provider_session_id,generation_number,started_at_ms,
                  executive_writer_held,provider_writer_state,created_at_ms
                ) VALUES(?,?,?,?,?,?,1,'UNKNOWN',?)
                """,
                (
                    generation.process_generation_id,
                    epoch.session_epoch_id,
                    row["worker_id"],
                    old["provider_session_id"],
                    2,
                    timestamp,
                    timestamp,
                ),
            )
            self.store.append_event(
                connection,
                aggregate_type="process_generation",
                aggregate_id=old_generation.process_generation_id,
                event_type="OHF_RESUME_SAFETY_DERIVED",
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=epoch.attempt_id,
                worker_id=epoch.worker_id,
                quota_class=str(row["quota_class"]),
                payload={
                    "resume_safe": True,
                    "derived_from_reconcile": True,
                    "launch_decision": LaunchDecision.ALLOW.value,
                    "attestation_digest": old["observed_attestation_digest"],
                    "process_ended_at_ms": old["ended_at_ms"],
                    "provider_writer_state": old["provider_writer_state"],
                },
                timestamp_ms=timestamp,
            )
            target = OperationIntentTarget(
                OperationKind.RESUME_SESSION,
                epoch.attempt_id,
                epoch.session_epoch_id,
                generation.process_generation_id,
                epoch.worker_id,
                str(old["provider_session_id"]),
            )
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.INTENT,
                row=row,
                payload=target.to_event_payload(),
            )
        return generation

    def commit_provider_dispatch(
        self,
        *,
        attempt_id: str,
        operation_id: OperationId,
        operation_kind: OperationKind | str,
        fence_generation: int,
        lease_token: str,
    ) -> bool:
        """Commit a provider-call boundary; False means fail-closed replay."""

        timestamp = self.store.now_ms()
        kind_value = (
            operation_kind.value
            if isinstance(operation_kind, OperationKind)
            else str(operation_kind)
        )
        dispatch_id = f"{operation_id.command_id}:dispatch"
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            intent = self._event(connection, operation_id.command_id)
            intent_payload = (
                _json_loads(intent["payload_json"], fallback={}) if intent else {}
            )
            durable = connection.execute(
                """
                SELECT e.attempt_id,e.worker_id AS epoch_worker,e.state,
                       e.provider_session_id AS epoch_session,
                       g.worker_id AS generation_worker,g.executive_writer_held
                FROM harness_session_epochs e
                JOIN process_generations g
                  ON g.session_epoch_id=e.session_epoch_id
                WHERE e.session_epoch_id=? AND g.process_generation_id=?
                """,
                (
                    intent_payload.get("session_epoch_id"),
                    intent_payload.get("process_generation_id"),
                ),
            ).fetchone()
            expected_keys = {
                OperationKind.START_SESSION.value: {
                    "schema_version",
                    "operation_kind",
                    "attempt_id",
                    "session_epoch_id",
                    "process_generation_id",
                    "worker_id",
                    "provider_session_id",
                },
                OperationKind.BEGIN_TURN.value: {
                    "schema_version",
                    "operation_kind",
                    "attempt_id",
                    "session_epoch_id",
                    "process_generation_id",
                    "worker_id",
                    "provider_session_id",
                    "turn_id",
                },
                OperationKind.RESUME_SESSION.value: {
                    "operation_kind",
                    "attempt_id",
                    "session_epoch_id",
                    "process_generation_id",
                    "worker_id",
                    "provider_session_id",
                },
                "interrupt_turn": {
                    "schema_version",
                    "operation_kind",
                    "attempt_id",
                    "session_epoch_id",
                    "process_generation_id",
                    "worker_id",
                    "turn_id",
                },
            }.get(kind_value)
            expected_schema = {
                OperationKind.START_SESSION.value: "mastermind.operator_harness_intent/v1",
                OperationKind.BEGIN_TURN.value: "mastermind.operator_harness_turn_intent/v1",
                "interrupt_turn": "mastermind.operator_harness_turn_operation/v1",
            }.get(kind_value)
            if (
                intent is None
                or intent["command_id"] != operation_id.command_id
                or intent["aggregate_type"] != "operator_operation"
                or intent["aggregate_id"] != operation_id.command_id
                or intent["event_type"] != OperationReceiptKind.INTENT.value
                or intent["attempt_id"] != attempt_id
                or intent["worker_id"] != row["worker_id"]
                or intent["job_id"] != row["job_id"]
                or intent["quota_class"] != row["quota_class"]
                or intent_payload.get("operation_kind") != kind_value
                or intent_payload.get("attempt_id") != attempt_id
                or intent_payload.get("worker_id") != row["worker_id"]
                or expected_keys is None
                or set(intent_payload) != expected_keys
                or (
                    "schema_version" in expected_keys
                    and intent_payload.get("schema_version") != expected_schema
                )
                or durable is None
                or durable["attempt_id"] != attempt_id
                or durable["epoch_worker"] != row["worker_id"]
                or durable["generation_worker"] != row["worker_id"]
                or durable["state"] != SessionEpochState.CURRENT.value
                or not durable["executive_writer_held"]
                or (
                    "provider_session_id" in expected_keys
                    and intent_payload.get("provider_session_id")
                    != durable["epoch_session"]
                )
                or (
                    "turn_id" in expected_keys
                    and not str(intent_payload.get("turn_id") or "").strip()
                )
            ):
                raise StateConflict(
                    "provider dispatch requires matching operation INTENT"
                )
            existing = self._event(connection, dispatch_id)
            if existing is not None:
                if (
                    self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.APPLIED
                        ),
                    )
                    is not None
                ):
                    raise StateConflict("resume operation is already APPLIED")
                if (
                    self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.EFFECT_UNKNOWN
                        ),
                    )
                    is None
                ):
                    self._receipt(
                        connection,
                        op=operation_id,
                        kind=OperationReceiptKind.EFFECT_UNKNOWN,
                        row=row,
                        payload={
                            "schema_version": "mastermind.operator_harness_effect_unknown/v1",
                            "phase": f"{kind_value}_dispatch"[:64],
                            "detail": "dispatch_committed_without_terminal_receipt",
                        },
                    )
                return False
            self.store.append_event(
                connection,
                aggregate_type="operator_operation",
                aggregate_id=operation_id.command_id,
                event_type="OHF_PROVIDER_DISPATCH_COMMITTED",
                command_id=dispatch_id,
                actor="supervisor",
                job_id=str(row["job_id"]),
                attempt_id=attempt_id,
                worker_id=str(row["worker_id"]),
                quota_class=str(row["quota_class"]),
                payload={
                    "schema_version": "mastermind.operator_harness_provider_dispatch/v1",
                    "operation_kind": kind_value,
                },
                timestamp_ms=timestamp,
            )
            return True

    def reserve_turn_operation(
        self,
        *,
        turn: TurnRef,
        operation_id: OperationId,
        operation_kind: str,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        kind = str(operation_kind or "").strip()
        if kind != "interrupt_turn":
            raise StateConflict("unsupported turn operation")
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=turn.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            durable = connection.execute(
                """
                SELECT e.attempt_id,e.worker_id AS epoch_worker,e.state,
                       g.worker_id AS generation_worker,g.executive_writer_held
                FROM harness_session_epochs e
                JOIN process_generations g
                  ON g.session_epoch_id=e.session_epoch_id
                WHERE e.session_epoch_id=? AND g.process_generation_id=?
                """,
                (turn.session_epoch_id, turn.process_generation_id),
            ).fetchone()
            source = None
            for event in connection.execute(
                "SELECT * FROM events WHERE event_type=? AND attempt_id=?",
                (OperationReceiptKind.INTENT.value, turn.attempt_id),
            ):
                payload = _json_loads(event["payload_json"], fallback={})
                if (
                    payload.get("operation_kind") == OperationKind.BEGIN_TURN.value
                    and payload.get("turn_id") == turn.turn_id
                ):
                    source = (event, payload)
                    break
            source_applied = (
                None
                if source is None
                else self._event(
                    connection,
                    operation_receipt_command_id(
                        OperationId(str(source[0]["command_id"])),
                        OperationReceiptKind.APPLIED,
                    ),
                )
            )
            if (
                durable is None
                or durable["attempt_id"] != row["attempt_id"]
                or durable["epoch_worker"] != row["worker_id"]
                or durable["generation_worker"] != row["worker_id"]
                or durable["state"] != SessionEpochState.CURRENT.value
                or not durable["executive_writer_held"]
                or source is None
                or source_applied is None
            ):
                raise StateConflict("turn operation lacks exact durable TX-5 ownership")
            payload = {
                "schema_version": "mastermind.operator_harness_turn_operation/v1",
                "operation_kind": kind,
                "attempt_id": turn.attempt_id,
                "session_epoch_id": turn.session_epoch_id,
                "process_generation_id": turn.process_generation_id,
                "worker_id": str(row["worker_id"]),
                "turn_id": turn.turn_id,
            }
            existing = self._event(connection, operation_id.command_id)
            if existing is not None:
                if (
                    _json_loads(existing["payload_json"], fallback={}) == payload
                    and self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.APPLIED
                        ),
                    )
                    is None
                    and self._event(
                        connection,
                        operation_receipt_command_id(
                            operation_id, OperationReceiptKind.EFFECT_UNKNOWN
                        ),
                    )
                    is None
                ):
                    return
                raise StateConflict("turn operation is not retryable")
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.INTENT,
                row=row,
                payload=payload,
            )

    def apply_turn_operation(
        self,
        *,
        turn: TurnRef,
        operation_id: OperationId,
        operation_kind: str,
        fence_generation: int,
        lease_token: str,
    ) -> None:
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=turn.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
                statuses={AttemptStatus.RUNNING, AttemptStatus.CHECKPOINTED},
            )
            intent = self._event(connection, operation_id.command_id)
            expected = {
                "schema_version": "mastermind.operator_harness_turn_operation/v1",
                "operation_kind": "interrupt_turn",
                "attempt_id": turn.attempt_id,
                "session_epoch_id": turn.session_epoch_id,
                "process_generation_id": turn.process_generation_id,
                "worker_id": str(row["worker_id"]),
                "turn_id": turn.turn_id,
            }
            if (
                operation_kind != "interrupt_turn"
                or intent is None
                or _json_loads(intent["payload_json"], fallback={}) != expected
            ):
                raise StateConflict("turn operation INTENT mismatch")
            if (
                self._event(
                    connection,
                    operation_receipt_command_id(
                        operation_id, OperationReceiptKind.APPLIED
                    ),
                )
                is None
            ):
                self._receipt(
                    connection,
                    op=operation_id,
                    kind=OperationReceiptKind.APPLIED,
                    row=row,
                    payload={
                        "schema_version": "mastermind.operator_harness_turn_operation_applied/v1",
                        "operation_kind": "interrupt_turn",
                        "turn_id": turn.turn_id,
                    },
                )

    def bind_resume_result(
        self,
        *,
        epoch: SessionEpochRef,
        generation: ProcessGenerationRef,
        operation_id: OperationId,
        fence_generation: int,
        lease_token: str,
        provider_session_id: str,
        process: ProcessIdentityObservation,
    ) -> ProcessGenerationRef:
        """TX-11: validate full immutable INTENT in this transaction, then bind G2."""
        session = str(provider_session_id or "").strip()
        pid, pgid, start, boot = _ohf_process(process)
        timestamp = self.store.now_ms()
        with self.store.transaction() as connection:
            row = self._leased(
                connection,
                attempt_id=epoch.attempt_id,
                fence_generation=fence_generation,
                lease_token=lease_token,
                timestamp=timestamp,
            )
            intent = self._event(connection, operation_id.command_id)
            item = connection.execute(
                """
                SELECT g.*,e.attempt_id,e.worker_id AS epoch_worker,
                       e.provider_session_id AS epoch_session,e.state
                FROM process_generations g
                JOIN harness_session_epochs e
                  ON e.session_epoch_id=g.session_epoch_id
                WHERE g.process_generation_id=?
                """,
                (generation.process_generation_id,),
            ).fetchone()
            self._owned_generation(
                connection,
                leased=row,
                epoch=epoch,
                generation=generation,
                require_current=True,
                require_writer=True,
            )
            payload = _json_loads(intent["payload_json"], fallback={}) if intent else {}
            required = {
                "operation_kind": "resume_session",
                "attempt_id": epoch.attempt_id,
                "session_epoch_id": epoch.session_epoch_id,
                "process_generation_id": generation.process_generation_id,
                "worker_id": epoch.worker_id,
                "provider_session_id": None if item is None else item["epoch_session"],
            }
            resume_allocation = connection.execute(
                """SELECT COUNT(*) FROM process_generations
                   WHERE session_epoch_id=? AND generation_number=2
                     AND executive_writer_held=1""",
                (epoch.session_epoch_id,),
            ).fetchone()[0]
            tx10_safety = connection.execute(
                """SELECT 1 FROM events safety
                   JOIN process_generations old
                     ON old.process_generation_id=safety.aggregate_id
                   WHERE safety.aggregate_type='process_generation'
                     AND safety.event_type='OHF_RESUME_SAFETY_DERIVED'
                     AND safety.attempt_id=?
                     AND old.session_epoch_id=? AND old.generation_number=1
                     AND safety.event_id < ? LIMIT 1""",
                (
                    epoch.attempt_id,
                    epoch.session_epoch_id,
                    0 if intent is None else intent["event_id"],
                ),
            ).fetchone()
            if (
                intent is None
                or item is None
                or intent["command_id"] != operation_id.command_id
                or intent["aggregate_type"] != "operator_operation"
                or intent["aggregate_id"] != operation_id.command_id
                or intent["event_type"] != OperationReceiptKind.INTENT.value
                or intent["attempt_id"] != epoch.attempt_id
                or intent["worker_id"] != epoch.worker_id
                or set(payload) != set(required)
                or any(payload.get(k) != v for k, v in required.items())
                or item["state"] != "CURRENT"
                or item["attempt_id"] != epoch.attempt_id
                or item["session_epoch_id"] != epoch.session_epoch_id
                or item["epoch_worker"] != epoch.worker_id
                or item["worker_id"] != epoch.worker_id
                or generation.session_epoch_id != epoch.session_epoch_id
                or generation.worker_id != epoch.worker_id
                or generation.generation_number != 2
                or int(item["generation_number"]) != 2
                or resume_allocation != 1
                or tx10_safety is None
                or not item["executive_writer_held"]
                or not session
                or session != item["epoch_session"]
                or item["provider_session_id"] != session
            ):
                raise StateConflict("TX-11 intent target or provider session mismatch")
            applied = self._event(
                connection,
                operation_receipt_command_id(
                    operation_id, OperationReceiptKind.APPLIED
                ),
            )
            if applied:
                if (
                    item["pid"] == pid
                    and item["pgid"] == pgid
                    and item["process_start_identity"] == start
                    and item["boot_id"] == boot
                ):
                    return generation
                raise StateConflict("TX-11 already applied differently")
            if any(
                item[name] is not None
                for name in ("pid", "pgid", "process_start_identity", "boot_id")
            ):
                raise StateConflict("TX-11 refuses to overwrite process identity")
            connection.execute(
                """
                UPDATE process_generations
                SET pid=?,pgid=?,process_start_identity=?,boot_id=?,last_observed_at_ms=?
                WHERE process_generation_id=?
                """,
                (pid, pgid, start, boot, timestamp, generation.process_generation_id),
            )
            self._receipt(
                connection,
                op=operation_id,
                kind=OperationReceiptKind.APPLIED,
                row=row,
                payload={
                    "operation_kind": "resume_session",
                    "process_generation_id": generation.process_generation_id,
                    "provider_session_id": session,
                },
            )
        return generation

    def invalidate_after_restore(self) -> int:
        timestamp = self.store.now_ms()
        count = 0
        with self.store.transaction() as connection:
            rows = connection.execute("""
                SELECT * FROM attempts
                WHERE execution_mode='OPERATOR_HARNESS'
                  AND status IN (
                      'CLAIMED','RUNNING','CHECKPOINTED','CANCEL_REQUESTED'
                  )
                """).fetchall()
            for row in rows:
                aid = str(row["attempt_id"])
                count += 1
                connection.execute(
                    """
                    UPDATE process_generations SET executive_writer_held=0
                    WHERE session_epoch_id IN (
                        SELECT session_epoch_id FROM harness_session_epochs
                        WHERE attempt_id=?
                    )
                    """,
                    (aid,),
                )
                connection.execute(
                    """
                    UPDATE harness_session_epochs
                    SET state='ABANDONED',ended_at_ms=COALESCE(ended_at_ms,?)
                    WHERE attempt_id=? AND state='CURRENT'
                    """,
                    (timestamp, aid),
                )
                connection.execute(
                    """
                    UPDATE attempts
                    SET status='LOST',lease_token=NULL,finished_at_ms=?,
                        updated_at_ms=?,version=version+1
                    WHERE attempt_id=?
                    """,
                    (timestamp, timestamp, aid),
                )
                connection.execute(
                    """
                    UPDATE jobs
                    SET status='LOST',updated_at_ms=?,version=version+1
                    WHERE job_id=? AND current_attempt_id=?
                    """,
                    (timestamp, row["job_id"], aid),
                )
                connection.execute(
                    """
                    UPDATE worker_quota_classes
                    SET status='ERROR',held_attempt_id=NULL,updated_at_ms=?,
                        version=version+1
                    WHERE worker_id=? AND quota_class=? AND held_attempt_id=?
                    """,
                    (timestamp, row["worker_id"], row["quota_class"], aid),
                )
                self.store.append_event(
                    connection,
                    aggregate_type="attempt",
                    aggregate_id=aid,
                    event_type="OHF_RESTORE_INVALIDATED",
                    actor="restore",
                    job_id=str(row["job_id"]),
                    attempt_id=aid,
                    worker_id=str(row["worker_id"]),
                    quota_class=str(row["quota_class"]),
                    payload={"transaction_group": "TX-9"},
                    command_id=f"ohf-restore:{aid}",
                    timestamp_ms=timestamp,
                )
        return count


class EventRegistry:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def get_event_by_command_id(self, command_id: str) -> Event | None:
        """Full Event lookup by durable command id."""

        return self.store.get_event_by_command_id(command_id)

    def list_events(
        self,
        *,
        job_id: str | None = None,
        attempt_id: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        command_id_prefix: str | None = None,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list[str] = []
        if job_id:
            clauses.append("job_id=?")
            params.append(job_id)
        if attempt_id:
            clauses.append("attempt_id=?")
            params.append(attempt_id)
        if aggregate_type:
            clauses.append("aggregate_type=?")
            params.append(str(aggregate_type).strip())
        if aggregate_id:
            clauses.append("aggregate_id=?")
            params.append(str(aggregate_id).strip())
        if command_id_prefix:
            token = str(command_id_prefix).strip()
            if not token or any(ch in token for ch in "%_"):
                raise StateConflict("command_id_prefix must be a literal namespace")
            clauses.append("command_id LIKE ?")
            params.append(token + "%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.store.read() as connection:
            rows = connection.execute(
                f"SELECT * FROM events{where} ORDER BY event_id", params
            ).fetchall()
            return [_event_from_row(row) for row in rows]


class ResourceBroker:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def _matching_capacity(
        self, job: Job, worker_id: str | None = None
    ) -> WorkerQuotaClass | None:
        if job.orchestration_role is not None:
            raise StateConflict(
                "orchestration capacity selection is restricted to command-bound claim"
            )
        required_provider = str(job.constraints.get("provider") or "")
        required_model = str(job.constraints.get("model") or "")
        required_effort = str(job.constraints.get("effort") or "")
        required_cost_class = str(job.constraints.get("cost_class") or "")
        required_capabilities = set(job.constraints.get("required_capabilities") or [])
        eligible = set(job.constraints["eligible_quota_classes"])
        with self.store.read() as connection:
            rows = connection.execute("""
                SELECT q.*,a.job_id AS active_job_id,w.provider AS worker_provider,w.identity_status
                FROM worker_quota_classes q
                JOIN workers w ON w.worker_id=q.worker_id
                LEFT JOIN attempts a ON a.attempt_id=q.held_attempt_id
                WHERE q.status='AVAILABLE' AND q.held_attempt_id IS NULL
                ORDER BY q.worker_id,q.quota_class
                """).fetchall()
        candidates: list[sqlite3.Row] = []
        for row in rows:
            if worker_id and row["worker_id"] != worker_id:
                continue
            if not _capacity_matches_route(row, job.constraints):
                continue
            if row["quota_class"] not in eligible:
                continue
            if required_provider and row["provider"] != required_provider:
                continue
            if required_model and (row["model"] or "") != required_model:
                continue
            if required_effort and (row["effort"] or "") != required_effort:
                continue
            if required_cost_class and (row["cost_class"] or "") != required_cost_class:
                continue
            if row["identity_status"] != "ONLINE":
                continue
            quota = _quota_from_row(row)
            if required_capabilities.issubset(set(quota.capabilities)):
                candidates.append(row)
        if not candidates:
            return None
        candidates.sort(key=lambda row: _capacity_route_rank(row, job.constraints))
        return _quota_from_row(candidates[0])

    def select_worker(self, job: Job | str) -> Worker | None:
        selected_job = (
            JobRegistry(self.store).get_job(job) if isinstance(job, str) else job
        )
        if selected_job is None:
            raise StateConflict(f"job {job!r} does not exist")
        if selected_job.orchestration_role is not None:
            raise StateConflict(
                "orchestration worker selection is restricted to command-bound claim"
            )
        if selected_job.status != JobStatus.QUEUED:
            return None
        with self.store.read() as connection:
            if _living_child_rows(connection, selected_job.job_id):
                return None
        capacity = self._matching_capacity(selected_job)
        return (
            WorkerRegistry(self.store).get_worker(capacity.worker_id)
            if capacity
            else None
        )

    def claim(self, job_id: str, **kwargs: Any) -> AttemptLease | None:
        return AttemptRegistry(self.store).claim_job(job_id, **kwargs)

    def dispatch(self, job_id: str) -> Worker | None:
        lease = self.claim(job_id)
        if lease is None:
            return None
        return WorkerRegistry(self.store).get_worker(lease.attempt.worker_id)


def _runtime_binding_ordered_unique_strings(
    value: Any, *, require_nonempty: bool
) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not require_nonempty)
        and all(
            isinstance(item, str) and bool(item) and item == item.strip()
            for item in value
        )
        and value == sorted(set(value))
    )


def _runtime_binding_validation_argv(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(argv, list)
        and bool(argv)
        and all(isinstance(item, str) and bool(item) for item in argv)
        for argv in value
    )


@dataclasses.dataclass(frozen=True)
class ActiveOperatorBindingFacts:
    """One read-snapshot of the accepted current OHF binding source."""

    attempt_id: str
    session_epoch_id: str
    generation_number: int
    provider_session_id: str
    provider: str
    account_label: str
    owner_seat: str


@dataclasses.dataclass(frozen=True)
class Runtime:
    store: RuntimeStore
    workers: WorkerRegistry
    jobs: JobRegistry
    attempts: AttemptRegistry
    events: EventRegistry
    operator_harness: OperatorHarnessRegistry
    broker: ResourceBroker

    @classmethod
    def from_store(cls, store: RuntimeStore) -> "Runtime":
        return cls(
            store=store,
            workers=WorkerRegistry(store),
            jobs=JobRegistry(store),
            attempts=AttemptRegistry(store),
            events=EventRegistry(store),
            operator_harness=OperatorHarnessRegistry(store),
            broker=ResourceBroker(store),
        )

    @classmethod
    def at(
        cls,
        root: str | Path | None = None,
        *,
        clock: Callable[[], int | float | datetime] | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        create: bool = True,
        existing_writable: bool = False,
    ) -> "Runtime":
        return cls.from_store(
            RuntimeStore(
                root,
                clock=clock,
                lease_seconds=lease_seconds,
                busy_timeout_ms=busy_timeout_ms,
                create=create,
                existing_writable=existing_writable,
            )
        )

    def validated_role_completion(
        self,
        job_id: str,
        *,
        expected_attempt_id: str,
    ) -> ValidatedRoleCompletion:
        """Return one canonical terminal role snapshot from one read transaction.

        This is the sole public projection boundary for completed orchestration
        children.  It consumes both supported Runtime receipt families through
        the canonical validator and exposes no SQL or private validation law to
        downstream projectors.
        """

        job_token = str(job_id or "").strip()
        attempt_token = str(expected_attempt_id or "").strip()
        if not job_token or not attempt_token:
            raise StateConflict("terminal completion requires exact Job and Attempt ids")
        with self.store.read() as connection:
            job_row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_token,)
            ).fetchone()
            if job_row is None:
                raise StateConflict(f"terminal completion Job {job_token!r} does not exist")
            role = str(job_row["orchestration_role"] or "")
            if (
                role not in {"plan", "work", "review", "repair"}
                or job_row["current_attempt_id"] != attempt_token
            ):
                raise StateConflict("terminal completion binding is not current")
            attempt_row, seal, terminal, role_result_digest = (
                _validated_role_completion_material(
                    connection,
                    job_row=job_row,
                    expected_role=role,
                    root_job_id=str(job_row["root_job_id"]),
                )
            )
            if attempt_row["attempt_id"] != attempt_token:
                raise StateConflict("terminal completion validator returned another Attempt")
            try:
                job_result = _strict_canonical_json_loads(
                    str(job_row["result_json"]), name="terminal completion Job result"
                )
                attempt_result = _strict_canonical_json_loads(
                    str(attempt_row["result_json"]),
                    name="terminal completion Attempt result",
                )
                job = _job_from_row(job_row)
                attempt = _attempt_from_row(attempt_row)
            except PersistenceError as exc:
                raise StateConflict(
                    f"terminal completion durable material is invalid: {exc}"
                ) from exc
            if job_result != terminal or attempt_result != terminal:
                raise StateConflict("terminal completion Job/Attempt receipt drifted")
            envelope = seal.get("result_envelope")
            result_envelope_digest = seal.get("result_envelope_digest")
            if (
                not isinstance(envelope, dict)
                or not isinstance(result_envelope_digest, str)
                or not isinstance(role_result_digest, str)
            ):
                raise StateConflict("terminal completion validated material is incomplete")
            dialogue_source = _dialogue_source_from_root_creation(
                connection,
                root_job_id=job.root_job_id,
            )
            return ValidatedRoleCompletion(
                job=job,
                attempt=attempt,
                result_envelope=dict(envelope),
                terminal_receipt=dict(terminal),
                result_digest=result_envelope_digest,
                role_result_digest=role_result_digest,
                execution_mode=str(
                    attempt_row["execution_mode"]
                    or AttemptExecutionMode.SEALED_WORKER.value
                ),
                dialogue_source=dialogue_source,
            )

    def current_harness_binding_source(
        self,
        attempt_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ActiveOperatorBindingFacts:
        """Read exactly one current, admitted OHF writer from one snapshot.

        The caller may pass an already-open ``RuntimeStore.read()`` or
        ``RuntimeStore.transaction()`` connection.  In that case this method opens
        no nested read and all source facts remain from the caller's snapshot.
        """

        token = str(attempt_id or "").strip()
        if not token:
            raise StateConflict("runtime binding source requires an attempt_id")
        if connection is None:
            with self.store.read() as owned_connection:
                return self.current_harness_binding_source(
                    token, connection=owned_connection
                )
        self.store._assert_owned_snapshot_connection(connection)

        rows = connection.execute(
            """
            SELECT a.*,j.current_attempt_id AS job_current_attempt_id,
                   j.status AS job_status,j.owner_seat,j.orchestration_role,
                   j.parent_job_id,j.root_job_id,j.orchestration_provenance_json,
                   j.orchestration_provenance_digest,j.plan_attempt_id,j.plan_digest,
                   j.plan_step_id,j.repair_round,j.supersedes_job_id,
                   j.requested_authorities_json AS job_requested_authorities_json,
                   j.allowed_write_paths_json AS job_allowed_write_paths_json,
                   j.validation_commands_json AS job_validation_commands_json,
                   j.authority_policy_hash AS job_authority_policy_hash,
                   w.provider AS worker_provider,w.account_label AS worker_account_label,
                   q.worker_id AS quota_worker_id,q.quota_class AS quota_quota_class,
                   q.provider AS quota_provider,q.status AS quota_status,
                   q.held_attempt_id,q.fence_counter AS quota_fence_counter,
                   e.session_epoch_id,e.worker_id AS epoch_worker,e.state AS epoch_state,
                   e.provider_session_id AS epoch_provider_session,
                   g.process_generation_id,g.worker_id AS generation_worker,
                   g.generation_number,g.provider_session_id AS generation_provider_session,
                   g.pid AS generation_pid,g.pgid AS generation_pgid,
                   g.process_start_identity AS generation_process_start_identity,
                   g.boot_id AS generation_boot_id,g.executive_writer_held,g.ended_at_ms,
                   g.observed_attestation_digest
            FROM main.attempts a
            JOIN main.jobs j ON j.job_id=a.job_id
            JOIN main.workers w ON w.worker_id=a.worker_id
            JOIN main.worker_quota_classes q
              ON q.worker_id=a.worker_id AND q.quota_class=a.quota_class
            LEFT JOIN main.harness_session_epochs e ON e.attempt_id=a.attempt_id
              AND e.state='CURRENT'
            LEFT JOIN main.process_generations g ON g.session_epoch_id=e.session_epoch_id
              AND g.executive_writer_held=1
            WHERE a.attempt_id=?
            """,
            (token,),
        ).fetchall()
        cardinality = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM main.jobs WHERE current_attempt_id=?) AS current_jobs,
              (SELECT COUNT(*) FROM main.harness_session_epochs
                 WHERE attempt_id=? AND state='CURRENT') AS current_epochs,
              (SELECT COUNT(*) FROM main.process_generations g
                 JOIN main.harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id
                 WHERE e.attempt_id=? AND g.executive_writer_held=1) AS held_writers,
              (SELECT MAX(g.generation_number) FROM main.process_generations g
                 JOIN main.harness_session_epochs e ON e.session_epoch_id=g.session_epoch_id
                 WHERE e.attempt_id=? AND e.state='CURRENT') AS current_epoch_max_generation
            """,
            (token, token, token, token),
        ).fetchone()
        if len(rows) != 1 or cardinality is None:
            raise StateConflict("runtime binding source cardinality is not exact")
        row = rows[0]
        accepted_statuses = {
            AttemptStatus.RUNNING.value: JobStatus.RUNNING.value,
            AttemptStatus.CHECKPOINTED.value: JobStatus.CHECKPOINTED.value,
            AttemptStatus.CANCEL_REQUESTED.value: JobStatus.CANCEL_REQUESTED.value,
        }
        expected_job_status = accepted_statuses.get(str(row["status"]))
        if (
            int(cardinality["current_jobs"]) != 1
            or int(cardinality["current_epochs"]) != 1
            or int(cardinality["held_writers"]) != 1
            or cardinality["current_epoch_max_generation"] is None
            or row["job_current_attempt_id"] != token
            or expected_job_status is None
            or row["job_status"] != expected_job_status
            or row["lease_token"] is None
            or int(row["lease_expires_at_ms"]) <= self.store.now_ms()
            or row["execution_mode"] != AttemptExecutionMode.OPERATOR_HARNESS.value
            or row["orchestration_role"] not in _ORCHESTRATION_ROLES
            or row["quota_worker_id"] != row["worker_id"]
            or row["quota_quota_class"] != row["quota_class"]
            or row["quota_provider"] != row["worker_provider"]
            or row["quota_status"] != WorkerStatus.BUSY.value
            or row["held_attempt_id"] != token
            or int(row["quota_fence_counter"]) != int(row["fence_generation"])
            or row["session_epoch_id"] is None
            or row["process_generation_id"] is None
            or row["epoch_state"] != SessionEpochState.CURRENT.value
            or row["epoch_worker"] != row["worker_id"]
            or row["generation_worker"] != row["worker_id"]
            or not row["executive_writer_held"]
            or row["ended_at_ms"] is not None
            or not row["epoch_provider_session"]
            or row["generation_provider_session"] != row["epoch_provider_session"]
            or int(row["generation_number"])
            != int(cardinality["current_epoch_max_generation"])
            or not row["observed_attestation_digest"]
        ):
            raise StateConflict("runtime binding source is not one current actionable OHF writer")

        try:
            placement = _load_canonical_digest_pair(
                row["placement_snapshot_json"],
                row["placement_snapshot_digest"],
                name="runtime binding placement snapshot",
            )
        except PersistenceError as exc:
            raise StateConflict(f"runtime binding placement evidence is invalid: {exc}") from exc
        if (
            not isinstance(placement, dict)
            or placement.get("worker_id") != row["worker_id"]
            or placement.get("quota_class") != row["quota_class"]
            or placement.get("provider") != row["worker_provider"]
            or placement.get("account_label") != row["worker_account_label"]
        ):
            raise StateConflict("runtime binding placement evidence drifted")

        try:
            grant = _load_canonical_digest_pair(
                row["effective_grant_json"],
                row["effective_grant_digest"],
                name="runtime binding effective grant",
            )
        except PersistenceError as exc:
            raise StateConflict(
                f"runtime binding effective grant evidence is invalid: {exc}"
            ) from exc
        try:
            job_authorities = _strict_canonical_json_loads(
                str(row["job_requested_authorities_json"]),
                name="runtime binding Job requested authorities",
            )
            job_write_paths = _strict_canonical_json_loads(
                str(row["job_allowed_write_paths_json"]),
                name="runtime binding Job allowed write paths",
            )
            job_validation_argv = _strict_canonical_json_loads(
                str(row["job_validation_commands_json"]),
                name="runtime binding Job validation commands",
            )
        except PersistenceError as exc:
            raise StateConflict(
                f"runtime binding effective grant Job evidence is invalid: {exc}"
            ) from exc
        grant_keys = {
            "schema_version",
            "authorities",
            "write_paths",
            "validation_argv",
            "policy_sha",
            "job_id",
            "role",
        }
        if (
            not isinstance(grant, dict)
            or set(grant) != grant_keys
            or grant.get("schema_version")
            != "mastermind.executive_effective_grant/v1"
            or grant.get("job_id") != row["job_id"]
            or grant.get("role") != row["orchestration_role"]
            or grant.get("policy_sha") != row["authority_policy_hash"]
            or row["job_authority_policy_hash"] != row["authority_policy_hash"]
            or not _runtime_binding_ordered_unique_strings(
                job_authorities, require_nonempty=True
            )
            or not _runtime_binding_ordered_unique_strings(
                job_write_paths, require_nonempty=False
            )
            or not _runtime_binding_validation_argv(job_validation_argv)
            or not _runtime_binding_ordered_unique_strings(
                grant.get("authorities"), require_nonempty=True
            )
            or not _runtime_binding_ordered_unique_strings(
                grant.get("write_paths"), require_nonempty=False
            )
            or not _runtime_binding_validation_argv(grant.get("validation_argv"))
            or any(item not in job_authorities for item in grant["authorities"])
            or any(item not in job_write_paths for item in grant["write_paths"])
            or any(item not in job_validation_argv for item in grant["validation_argv"])
        ):
            raise StateConflict("runtime binding effective grant evidence drifted")
        if row["orchestration_role"] in {"plan", "aggregation"} and (
            grant["authorities"] != ["READ"]
            or grant["write_paths"]
            or grant["validation_argv"]
        ):
            raise StateConflict("runtime binding effective grant role semantics drifted")
        if row["orchestration_role"] == "review" and (
            grant["authorities"] != job_authorities
            or any(item not in {"READ", "RUN_TESTS"} for item in job_authorities)
            or "READ" not in job_authorities
            or job_write_paths
            or grant["write_paths"]
            or grant["validation_argv"] != job_validation_argv
            or bool(grant["validation_argv"])
            != ("RUN_TESTS" in grant["authorities"])
        ):
            raise StateConflict("runtime binding effective grant role semantics drifted")

        creation_events = connection.execute(
            """SELECT * FROM main.events
               WHERE event_type='JOB_CREATED' AND job_id=?
               ORDER BY event_id""",
            (row["job_id"],),
        ).fetchall()
        if len(creation_events) != 1:
            raise StateConflict("runtime binding Job creation cardinality is not exact")
        creation_event = creation_events[0]
        try:
            job_role, job_provenance, job_provenance_digest = (
                _decode_orchestration_job_fields(row)
            )
            creation_payload = _strict_canonical_json_loads(
                str(creation_event["payload_json"]),
                name="runtime binding JOB_CREATED payload",
            )
        except PersistenceError as exc:
            raise StateConflict(
                f"runtime binding Job creation evidence is invalid: {exc}"
            ) from exc
        expected_creation_actor = (
            "operator" if job_role in {"aggregation", "plan"} else "coo"
        )
        if (
            not isinstance(job_provenance, dict)
            or not isinstance(creation_payload, dict)
            or creation_event["sequence"] != 1
            or creation_event["actor"] != expected_creation_actor
            or creation_event["aggregate_type"] != "job"
            or creation_event["aggregate_id"] != row["job_id"]
            or creation_event["job_id"] != row["job_id"]
            or creation_event["attempt_id"] is not None
            or creation_event["worker_id"] is not None
            or creation_event["quota_class"] is not None
            or creation_event["command_id"] != job_provenance.get("command_id")
            or not isinstance(creation_payload.get("owner_seat"), str)
            or creation_payload.get("owner_seat") != row["owner_seat"]
            or creation_payload.get("orchestration_role") != job_role
            or creation_payload.get("orchestration_provenance_digest")
            != job_provenance_digest
        ):
            raise StateConflict("runtime binding Job creation evidence drifted")

        admissions = connection.execute(
            """SELECT * FROM main.events
               WHERE event_type='ORCHESTRATION_WORK_ADMITTED'
                 AND aggregate_type='process_generation' AND aggregate_id=?
               ORDER BY event_id""",
            (row["process_generation_id"],),
        ).fetchall()
        decisions = connection.execute(
            """SELECT * FROM main.events
               WHERE event_type='OHF_LAUNCH_DECISION'
                 AND aggregate_type='process_generation' AND aggregate_id=?
               ORDER BY event_id""",
            (row["process_generation_id"],),
        ).fetchall()
        seals = connection.execute(
            """SELECT 1 FROM main.events
               WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?""",
            (token,),
        ).fetchall()
        if len(admissions) != 1 or len(decisions) != 1 or seals:
            raise StateConflict("runtime binding source lacks one active work admission")
        admission_event = admissions[0]
        admission = _strict_canonical_json_loads(
            str(admission_event["payload_json"]), name="runtime binding work admission"
        )
        decision = _strict_canonical_json_loads(
            str(decisions[0]["payload_json"]), name="runtime binding launch decision"
        )
        admission_keys = {
            "schema_version", "job_id", "attempt_id", "worker_id", "quota_class",
            "orchestration_role", "process_generation_id", "provider_session_id",
            "tx3_applied_command_id", "observed_attestation_digest",
            "principal_observation", "principal_observation_digest",
            "execution_principal_snapshot_digest", "placement_snapshot_digest",
            "effective_grant_digest", "policy_sha", "launch_decision",
        }
        immutable_digests = (
            "observed_attestation_digest",
            "principal_observation_digest",
            "execution_principal_snapshot_digest",
            "placement_snapshot_digest",
            "effective_grant_digest",
            "policy_sha",
        )
        decision_event = decisions[0]
        tx3: sqlite3.Row | None = None
        tx3_payload: Any = None
        tx3_intent: sqlite3.Row | None = None
        tx3_intent_payload: Any = None
        expected_tx3_command_id: str | None = None
        expected_tx3_applied: dict[str, Any] | None = None
        expected_tx3_intent: dict[str, Any] | None = None
        try:
            generation_number = int(row["generation_number"])
            if generation_number == 1:
                expected_tx3_applied = {
                    "operation_kind": OperationKind.START_SESSION.value,
                    "provider_session_id": row["epoch_provider_session"],
                    "process_generation_id": row["process_generation_id"],
                }
                expected_tx3_intent = {
                    "schema_version": "mastermind.operator_harness_intent/v1",
                    "operation_kind": OperationKind.START_SESSION.value,
                    "attempt_id": token,
                    "session_epoch_id": row["session_epoch_id"],
                    "process_generation_id": row["process_generation_id"],
                    "worker_id": row["worker_id"],
                    "provider_session_id": None,
                }
            elif generation_number == 2:
                expected_tx3_applied = {
                    "operation_kind": OperationKind.RESUME_SESSION.value,
                    "provider_session_id": row["epoch_provider_session"],
                    "process_generation_id": row["process_generation_id"],
                }
                expected_tx3_intent = {
                    "operation_kind": OperationKind.RESUME_SESSION.value,
                    "attempt_id": token,
                    "session_epoch_id": row["session_epoch_id"],
                    "process_generation_id": row["process_generation_id"],
                    "worker_id": row["worker_id"],
                    "provider_session_id": row["epoch_provider_session"],
                }
            if expected_tx3_applied is not None and expected_tx3_intent is not None:
                tx3_rows = connection.execute(
                    """SELECT * FROM main.events
                       WHERE event_type=? AND attempt_id=?
                         AND json_extract(payload_json,'$.operation_kind')=?
                         AND json_extract(payload_json,'$.process_generation_id')=?
                       ORDER BY event_id""",
                    (
                        OperationReceiptKind.APPLIED.value,
                        token,
                        expected_tx3_applied["operation_kind"],
                        row["process_generation_id"],
                    ),
                ).fetchall()
                tx3_intent_rows = connection.execute(
                    """SELECT * FROM main.events
                       WHERE event_type=? AND attempt_id=?
                         AND json_extract(payload_json,'$.operation_kind')=?
                         AND json_extract(payload_json,'$.process_generation_id')=?
                       ORDER BY event_id""",
                    (
                        OperationReceiptKind.INTENT.value,
                        token,
                        expected_tx3_intent["operation_kind"],
                        row["process_generation_id"],
                    ),
                ).fetchall()
                tx3 = tx3_rows[0] if len(tx3_rows) == 1 else None
                tx3_intent = (
                    tx3_intent_rows[0] if len(tx3_intent_rows) == 1 else None
                )
            if tx3 is not None and tx3_intent is not None:
                tx3_payload = _strict_canonical_json_loads(
                    str(tx3["payload_json"]), name="runtime binding TX-3 APPLIED"
                )
                operation_id = OperationId(str(tx3["aggregate_id"]))
                expected_tx3_command_id = operation_receipt_command_id(
                    operation_id, OperationReceiptKind.APPLIED
                )
                tx3_intent_payload = _strict_canonical_json_loads(
                    str(tx3_intent["payload_json"]),
                    name="runtime binding TX-3 INTENT",
                )
        except (StateConflict, TypeError, ValueError) as exc:
            raise StateConflict(
                f"runtime binding TX-3/TX-11 evidence is invalid: {exc}"
            ) from exc
        if (
            tx3 is None
            or expected_tx3_applied is None
            or expected_tx3_intent is None
            or tx3["event_type"] != OperationReceiptKind.APPLIED.value
            or tx3["command_id"] != expected_tx3_command_id
            or tx3["command_id"] != admission.get("tx3_applied_command_id")
            or tx3["actor"] != "supervisor"
            or tx3["aggregate_type"] != "operator_operation"
            or tx3["job_id"] != row["job_id"]
            or tx3["attempt_id"] != token
            or tx3["worker_id"] != row["worker_id"]
            or tx3["quota_class"] != row["quota_class"]
            or tx3_payload != expected_tx3_applied
            or tx3_intent is None
            or tx3_intent["event_type"] != OperationReceiptKind.INTENT.value
            or tx3_intent["command_id"] != tx3["aggregate_id"]
            or tx3_intent["actor"] != "supervisor"
            or tx3_intent["aggregate_type"] != "operator_operation"
            or tx3_intent["aggregate_id"] != tx3["aggregate_id"]
            or tx3_intent["job_id"] != row["job_id"]
            or tx3_intent["attempt_id"] != token
            or tx3_intent["worker_id"] != row["worker_id"]
            or tx3_intent["quota_class"] != row["quota_class"]
            or int(tx3_intent["event_id"]) >= int(tx3["event_id"])
            or int(tx3["event_id"]) >= int(decision_event["event_id"])
            or int(decision_event["event_id"]) >= int(admission_event["event_id"])
            or tx3_intent_payload != expected_tx3_intent
        ):
            raise StateConflict("runtime binding TX-3/TX-11 evidence drifted")
        observation = _validated_admission_principal(row, admission)
        if (
            set(admission) != admission_keys
            or admission_event["command_id"]
            != f"ohf-work-admit:{row['process_generation_id']}"
            or admission_event["actor"] != "supervisor"
            or admission_event["aggregate_type"] != "process_generation"
            or admission_event["aggregate_id"] != row["process_generation_id"]
            or admission_event["job_id"] != row["job_id"]
            or admission_event["attempt_id"] != token
            or admission_event["worker_id"] != row["worker_id"]
            or admission_event["quota_class"] != row["quota_class"]
            or admission.get("schema_version")
            != "mastermind.orchestration_work_admission/v1"
            or admission.get("job_id") != row["job_id"]
            or admission.get("attempt_id") != token
            or admission.get("worker_id") != row["worker_id"]
            or admission.get("quota_class") != row["quota_class"]
            or admission.get("orchestration_role") != row["orchestration_role"]
            or admission.get("process_generation_id") != row["process_generation_id"]
            or admission.get("provider_session_id") != row["epoch_provider_session"]
            or admission.get("observed_attestation_digest")
            != row["observed_attestation_digest"]
            or admission.get("placement_snapshot_digest")
            != row["placement_snapshot_digest"]
            or admission.get("effective_grant_digest") != row["effective_grant_digest"]
            or any(
                not isinstance(admission.get(field), str)
                or re.fullmatch(r"[0-9a-f]{64}", str(admission.get(field))) is None
                for field in immutable_digests
            )
            or admission.get("launch_decision") != LaunchDecision.ALLOW.value
            or decision_event["actor"] != "supervisor"
            or decision_event["aggregate_type"] != "process_generation"
            or decision_event["aggregate_id"] != row["process_generation_id"]
            or decision_event["job_id"] != row["job_id"]
            or decision_event["attempt_id"] != token
            or decision_event["worker_id"] != row["worker_id"]
            or decision_event["quota_class"] != row["quota_class"]
            or decision
            != {
                "decision": LaunchDecision.ALLOW.value,
                "attestation_digest": row["observed_attestation_digest"],
            }
            or observation["process_generation_id"] != row["process_generation_id"]
            or observation["provider_session_id"] != row["epoch_provider_session"]
            or observation["process_identity"]
            != {
                "pid": row["generation_pid"],
                "pgid": row["generation_pgid"],
                "process_start_identity": row["generation_process_start_identity"],
                "boot_id": row["generation_boot_id"],
            }
        ):
            raise StateConflict("runtime binding admission evidence drifted")
        return ActiveOperatorBindingFacts(
            attempt_id=token,
            session_epoch_id=str(row["session_epoch_id"]),
            generation_number=int(row["generation_number"]),
            provider_session_id=str(row["epoch_provider_session"]),
            provider=str(placement["provider"]),
            account_label=str(placement["account_label"]),
            owner_seat=str(row["owner_seat"]),
        )


__all__ = [
    "ActiveOperatorBindingFacts",
    "Attempt",
    "AttemptLease",
    "AttemptRegistry",
    "AttemptStatus",
    "CooRetryMutationOutcome",
    "EXECUTIVE_DIALOGUE_SOURCE_SCHEMA",
    "Event",
    "EventRegistry",
    "ExecutiveDialogueSource",
    "ExecutiveSchemaUpgradeRequired",
    "Job",
    "JobPayload",
    "JobRegistry",
    "JobStatus",
    "OperatorHarnessRegistry",
    "PersistenceError",
    "ResourceBroker",
    "RetrySafetyProjection",
    "Runtime",
    "RuntimeProofError",
    "RuntimeStore",
    "SCHEMA_VERSION",
    "StateConflict",
    "V2_HOST_EXECUTION_BINDING_KEYS",
    "ValidatedRoleCompletion",
    "Worker",
    "WorkerQuotaClass",
    "WorkerRegistry",
    "WorkerStatus",
    "normalize_executive_dialogue_source",
]
