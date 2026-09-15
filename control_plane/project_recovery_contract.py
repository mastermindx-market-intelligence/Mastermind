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

class ProjectRecoveryContractError(ValueError):
    pass

def _iso_date(value: str) -> str:
    try: parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc: raise ProjectRecoveryContractError("as_of must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value: raise ProjectRecoveryContractError("as_of must be YYYY-MM-DD")
    return value

def _unique(rows: Any, key: str, label: str) -> None:
    if not isinstance(rows, list): raise ProjectRecoveryContractError(f"{label} must be a list")
    seen=set()
    for row in rows:
        if not isinstance(row, Mapping): raise ProjectRecoveryContractError(f"{label} rows must be objects")
        value=row.get(key)
        if not isinstance(value,str) or not value: raise ProjectRecoveryContractError(f"{label}.{key} must be non-empty")
        if value in seen: raise ProjectRecoveryContractError(f"duplicate {label} {value}")
        seen.add(value)

def validate_inputs(session_truth: Mapping[str,Any], agentos_state: Mapping[str,Any], *, as_of: str) -> tuple[dict[str,Any],dict[str,Any],str]:
    if not isinstance(session_truth, Mapping) or session_truth.get("schema") != RECEIPT_SCHEMA: raise ProjectRecoveryContractError("session_truth schema is incompatible")
    if not isinstance(session_truth.get("findings"), list): raise ProjectRecoveryContractError("session_truth.findings must be a list")
    if not isinstance(session_truth.get("observations"), Mapping): raise ProjectRecoveryContractError("session_truth.observations must be an object")
    if not isinstance(session_truth.get("semantic_hash"), str): raise ProjectRecoveryContractError("session_truth.semantic_hash required")
    if not isinstance(agentos_state, Mapping) or agentos_state.get("schema") != AGENTOS_SCHEMA: raise ProjectRecoveryContractError("agentos schema is incompatible")
    _unique(agentos_state.get("workstreams"), "key", "workstream")
    registry=agentos_state.get("program_registry")
    if not isinstance(registry, Mapping) or registry.get("schema") != PROGRAM_REGISTRY_SCHEMA: raise ProjectRecoveryContractError("program_registry schema is incompatible")
    if type(registry.get("available")) is not bool: raise ProjectRecoveryContractError("program_registry.available must be boolean")
    if registry.get("available") is True: _unique(registry.get("programs"), "key", "program")
    elif not isinstance(registry.get("reason"), str) or not registry.get("reason"): raise ProjectRecoveryContractError("program_registry.reason required when unavailable")
    return copy.deepcopy(dict(session_truth)), copy.deepcopy(dict(agentos_state)), _iso_date(as_of)

def assessment_semantic_hash(value: Mapping[str,Any]) -> str:
    return semantic_hash(value)
