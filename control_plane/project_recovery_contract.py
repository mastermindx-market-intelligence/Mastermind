"""Strict deterministic contract for Project Recovery Sentinel R8-A."""
from __future__ import annotations
import copy
from collections.abc import Mapping
from datetime import date
from typing import Any
from control_plane.session_truth_contract import RECEIPT_SCHEMA, semantic_hash

ASSESSMENT_SCHEMA = "mastermind.project_recovery_assessment.v1"
AGENTOS_SCHEMA = "agent_os_state.v1"
PROGRAM_REGISTRY_SCHEMA = "agentos.program_registry.v1"
DISPOSITIONS = frozenset({"NO_RECOVERY_ACTION","VALID_INTENTIONAL_WAIT","CEO_ATTENTION","RECOVERY_REQUIRED","UNKNOWN_RECONCILE"})
RECOVERY_CODES = frozenset({"ORPHAN_BUILDING_PROGRAM","PROGRAM_LIFECYCLE_DISAGREEMENT","ACTIVE_WITHOUT_CARRIER","UNCLAIMED_COMMISSION","MISSED_REVIEW_GATE","MERGED_PROOF_DEBT","ACTIVE_BUT_COMPLETE","SUPERSEDED_NEXT_ACTION","CEO_DECISION_OVERDUE","RUNTIME_OWNERSHIP_UNKNOWN","MULTIPLE_ACTIVE_CARRIERS"})
TERMINAL_WORKSTREAM = frozenset({"done","parked","killed","complete","completed","dropped","cancelled","canceled","closed","terminal"})
TERMINAL_WAVE = TERMINAL_WORKSTREAM
_WAIT_KEYS = frozenset({"kind", "review_after", "condition"})

class ProjectRecoveryContractError(ValueError):
    pass

def _iso_date(value: str) -> str:
    try: parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc: raise ProjectRecoveryContractError("as_of must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value: raise ProjectRecoveryContractError("as_of must be YYYY-MM-DD")
    return value

def _validate_wait(raw: Any, label: str) -> None:
    if raw is None:
        return
    if not isinstance(raw, Mapping):
        raise ProjectRecoveryContractError(f"{label} must be an object")
    keys = set(raw)
    if keys != _WAIT_KEYS:
        raise ProjectRecoveryContractError(f"{label} must contain exactly kind, review_after, condition")
    for field in ("kind", "condition"):
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ProjectRecoveryContractError(f"{label}.{field} must be non-empty")
    review_after = raw.get("review_after")
    if not isinstance(review_after, str):
        raise ProjectRecoveryContractError(f"{label}.review_after must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(review_after)
    except ValueError as exc:
        raise ProjectRecoveryContractError(f"{label}.review_after must be YYYY-MM-DD") from exc
    if parsed.isoformat() != review_after:
        raise ProjectRecoveryContractError(f"{label}.review_after must be YYYY-MM-DD")

def _unique(rows: Any, key: str, label: str) -> None:
    if not isinstance(rows, list): raise ProjectRecoveryContractError(f"{label} must be a list")
    seen=set()
    for row in rows:
        if not isinstance(row, Mapping): raise ProjectRecoveryContractError(f"{label} rows must be objects")
        value=row.get(key)
        if not isinstance(value,str) or not value: raise ProjectRecoveryContractError(f"{label}.{key} must be non-empty")
        if value in seen: raise ProjectRecoveryContractError(f"duplicate {label} {value}")
        seen.add(value)

def workstream_wave_rows(row: Mapping[str, Any], *, label: str) -> list[Any]:
    """Return the canonical Agent OS wave rows without reading its rollup as rows."""
    if "wave_detail" in row:
        waves = row.get("wave_detail")
        if not isinstance(waves, list):
            raise ProjectRecoveryContractError(f"{label}.wave_detail must be a list")
        return waves
    waves = row.get("waves") or []
    if not isinstance(waves, list):
        raise ProjectRecoveryContractError(f"{label}.wave_detail must be a list")
    return waves

def validate_inputs(session_truth: Mapping[str,Any], agentos_state: Mapping[str,Any], *, as_of: str) -> tuple[dict[str,Any],dict[str,Any],str]:
    if not isinstance(session_truth, Mapping) or session_truth.get("schema") != RECEIPT_SCHEMA: raise ProjectRecoveryContractError("session_truth schema is incompatible")
    if not isinstance(session_truth.get("scope"), Mapping): raise ProjectRecoveryContractError("session_truth.scope must be an object")
    scope_workstreams = session_truth["scope"].get("workstreams")
    if not isinstance(scope_workstreams, list) or any(not isinstance(item, str) for item in scope_workstreams): raise ProjectRecoveryContractError("session_truth.scope.workstreams must be a list of strings")
    if not isinstance(session_truth.get("findings"), list): raise ProjectRecoveryContractError("session_truth.findings must be a list")
    if not isinstance(session_truth.get("observations"), Mapping): raise ProjectRecoveryContractError("session_truth.observations must be an object")
    if not isinstance(session_truth.get("semantic_hash"), str): raise ProjectRecoveryContractError("session_truth.semantic_hash required")
    if not isinstance(agentos_state, Mapping) or agentos_state.get("schema") != AGENTOS_SCHEMA: raise ProjectRecoveryContractError("agentos schema is incompatible")
    rows = agentos_state.get("workstreams")
    _unique(rows, "key", "workstream")
    for index, row in enumerate(rows):
        _validate_wait(row.get("wait"), f"workstream[{index}].wait")
        waves = workstream_wave_rows(row, label=f"workstream[{index}]")
        for wave_index, wave in enumerate(waves):
            if not isinstance(wave, Mapping): raise ProjectRecoveryContractError(f"workstream[{index}].waves rows must be objects")
            _validate_wait(wave.get("wait"), f"workstream[{index}].waves[{wave_index}].wait")
    registry=agentos_state.get("program_registry")
    if not isinstance(registry, Mapping) or registry.get("schema") != PROGRAM_REGISTRY_SCHEMA: raise ProjectRecoveryContractError("program_registry schema is incompatible")
    if type(registry.get("available")) is not bool: raise ProjectRecoveryContractError("program_registry.available must be boolean")
    if registry.get("available") is True: _unique(registry.get("programs"), "key", "program")
    elif not isinstance(registry.get("reason"), str) or not registry.get("reason"): raise ProjectRecoveryContractError("program_registry.reason required when unavailable")
    return copy.deepcopy(dict(session_truth)), copy.deepcopy(dict(agentos_state)), _iso_date(as_of)

def assessment_semantic_hash(value: Mapping[str,Any]) -> str:
    return semantic_hash(value)
