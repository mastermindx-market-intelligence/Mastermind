"""tests.operation_assurance_fixture_lib — shared OLS-A1 model builders.

Not a test module (no ``test_`` prefix). Provides a minimal-valid
``mastermind.operation_assurance_model.v1`` dict plus small composable
mutators so every OLS-A1 test/fixture builds on one known-good baseline
instead of hand-authoring 20-field JSON documents from scratch.

Every builder returns a plain JSON-able ``dict`` (never one of the frozen
dataclasses in ``control_plane.operation_assurance_model``) so callers can
freely mutate before calling the parser.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from control_plane.operation_assurance_model import canonical_json, sha256_hex

REF = "Mastermind@1111111111111111111111111111111111111111"


def source_record(**overrides: Any) -> dict:
    rec = {
        "owner": "EXECUTIVE_OS",
        "source_kind": "JOB_RECORD",
        "source_identity": "src_job_1",
        "schema_version": "1",
        "digest": "deadbeef",
        "effective_at": None,
        "observed_at": None,
        "correction_ref": None,
        "freshness": "FRESH",
        "conflict": "NONE",
        "coverage": "COMPLETE",
        "truncated": False,
        "continuation": None,
    }
    rec.update(overrides)
    return rec


def source_snapshot(sources: list[dict] | None = None) -> dict:
    sources = sources if sources is not None else []
    body = {"schema": "mastermind.operation_assurance.source_snapshot.v1", "sources": sources}
    snapshot_hash = sha256_hex(canonical_json(body))
    out = dict(body)
    out["snapshot_hash"] = snapshot_hash
    return out


def abstraction_contract(**overrides: Any) -> dict:
    ac = {
        "kind": "DECLARED_EXACT",
        "concrete_scope": "one closed pre-admission fixture operation",
        "preserves": [
            "SAFETY",
            "OPTION_TO_COMPLETE",
            "UNIVERSAL_PROGRESS",
            "LIVENESS_UNDER_DECLARED_FAIRNESS",
        ],
        "introduced_behavior": "NONE_DECLARED",
        "excluded_behavior": "NONE_DECLARED",
        "validation_kind": "AUTHOR_DECLARATION",
        "validation_refs": [REF],
        "notes": [],
    }
    ac.update(overrides)
    return ac


def guard(variable: str, op: str, value: Any) -> dict:
    return {"variable": variable, "op": op, "value": value}


def effect(variable: str, value: str) -> dict:
    return {"variable": variable, "value": value}


def transition(
    transition_id: str,
    guards: list[dict],
    effects: list[dict],
    *,
    kind: str = "MODIFY",
    actor_class: str = "WORKER",
    authority_requirement: str = "NONE",
    progress_tags: list[str] | None = None,
    source_refs: list[str] | None = None,
    fairness_ref: str | None = None,
    external_assumption_ref: str | None = None,
    gate_refs: list[str] | None = None,
    required_reachable: bool = False,
) -> dict:
    return {
        "transition_id": transition_id,
        "kind": kind,
        "actor_class": actor_class,
        "authority_requirement": authority_requirement,
        "guards": guards,
        "effects": effects,
        "progress_tags": progress_tags if progress_tags is not None else ["PROGRESS"],
        "source_refs": source_refs if source_refs is not None else [REF],
        "fairness_ref": fairness_ref,
        "external_assumption_ref": external_assumption_ref,
        "gate_refs": gate_refs if gate_refs is not None else [],
        "required_reachable": required_reachable,
    }


def outcome(
    outcome_id: str,
    kind: str,
    guards: list[dict],
    *,
    owned_persistent_obligation_ids: list[str] | None = None,
    owned_persistent_resource_ids: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "outcome_id": outcome_id,
        "kind": kind,
        "guards": guards,
        "owned_persistent_obligation_ids": owned_persistent_obligation_ids or [],
        "owned_persistent_resource_ids": owned_persistent_resource_ids or [],
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def obligation(
    obligation_id: str,
    state_variable: str,
    pending_values: list[str],
    discharged_values: list[str],
    *,
    kind: str = "GENERIC_OBLIGATION",
    persistent: bool = False,
    owner_or_authority: str = "OPERATION",
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "obligation_id": obligation_id,
        "kind": kind,
        "state_variable": state_variable,
        "pending_values": pending_values,
        "discharged_values": discharged_values,
        "persistent": persistent,
        "owner_or_authority": owner_or_authority,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def resource(
    resource_id: str,
    holder_variable: str,
    released_values: list[str],
    *,
    persistent: bool = False,
    owner_or_authority: str = "OPERATION",
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "resource_id": resource_id,
        "holder_variable": holder_variable,
        "released_values": released_values,
        "persistent": persistent,
        "owner_or_authority": owner_or_authority,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def gate(
    gate_id: str,
    disposition: str,
    state_guards: list[dict],
    release_transition_ids: list[str],
    escalation_or_close_path: str,
    *,
    owner_or_authority: str = "CHAIRMAN",
    release_condition: str = "release condition recorded through exact carrier",
    return_or_observation_source: str = "operation-carrier",
    wake_or_review_path: str = "existing Wake or explicit return",
    time_contract: str = "no synthetic TTL; source-owned review boundary",
    correction_contract: str = "new decision supersedes prior projection",
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "gate_id": gate_id,
        "disposition": disposition,
        "state_guards": state_guards,
        "owner_or_authority": owner_or_authority,
        "release_condition": release_condition,
        "release_transition_ids": release_transition_ids,
        "return_or_observation_source": return_or_observation_source,
        "wake_or_review_path": wake_or_review_path,
        "time_contract": time_contract,
        "correction_contract": correction_contract,
        "escalation_or_close_path": escalation_or_close_path,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def fairness(fairness_id: str, transition_ids: list[str], *, source_refs: list[str] | None = None) -> dict:
    return {
        "fairness_id": fairness_id,
        "kind": "WEAK",
        "transition_ids": transition_ids,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def environment_assumption(
    assumption_id: str,
    transition_ids: list[str],
    required_for_property_ids: list[str],
    *,
    kind: str = "EXTERNAL_EVENT_MAY_OCCUR",
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "assumption_id": assumption_id,
        "kind": kind,
        "transition_ids": transition_ids,
        "required_for_property_ids": required_for_property_ids,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def state_forbidden(property_id: str, violation_when: list[dict], *, source_refs: list[str] | None = None) -> dict:
    return {
        "property_id": property_id,
        "kind": "STATE_FORBIDDEN",
        "violation_when": violation_when,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def transition_forbidden(
    property_id: str,
    when: list[dict],
    forbidden_transition_kinds: list[str],
    *,
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "property_id": property_id,
        "kind": "TRANSITION_FORBIDDEN",
        "when": when,
        "forbidden_transition_kinds": forbidden_transition_kinds,
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def model_gap(
    gap_id: str,
    reason: str,
    load_bearing: bool,
    *,
    affects_property_ids: list[str] | None = None,
    affects_transition_ids: list[str] | None = None,
    affects_variable_ids: list[str] | None = None,
    source_refs: list[str] | None = None,
) -> dict:
    return {
        "gap_id": gap_id,
        "reason": reason,
        "load_bearing": load_bearing,
        "affects_property_ids": affects_property_ids or [],
        "affects_transition_ids": affects_transition_ids or [],
        "affects_variable_ids": affects_variable_ids or [],
        "source_refs": source_refs if source_refs is not None else [REF],
    }


def minimal_model(model_id: str = "om_minimal_v1") -> dict:
    """START --finish--> DONE. The smallest model that satisfies every parser rule."""
    return {
        "schema": "mastermind.operation_assurance_model.v1",
        "model_id": model_id,
        "operation_ref": {
            "operation_key": "op_minimal",
            "root_job_id": "job_minimal",
            "pre_admission_identity": None,
        },
        "compiler": {"name": "author", "version": "1", "invocation_mode": "AUTHORED_INPUT"},
        "source_snapshot": source_snapshot([]),
        "abstraction_contract": abstraction_contract(),
        "state_domains": {"phase": ["START", "DONE"]},
        "initial_state": {"phase": "START"},
        "transitions": [
            transition(
                "finish",
                [guard("phase", "EQ", "START")],
                [effect("phase", "DONE")],
                required_reachable=True,
            )
        ],
        "terminal_outcomes": [
            outcome("done", "TERMINAL_SUCCESS", [guard("phase", "EQ", "DONE")]),
        ],
        "recurring_progress_outcomes": [],
        "obligations": [],
        "resources": [],
        "external_gates": [],
        "fairness_assumptions": [],
        "environment_assumptions": [],
        "safety_properties": [],
        "property_set": "mastermind.operation_assurance.properties.v1",
        "exploration_limits": {"max_states": 1000, "max_depth": 1000},
        "known_model_gaps": [],
    }


def clone(model: dict) -> dict:
    return copy.deepcopy(model)


def dumps(model: dict) -> str:
    return json.dumps(model)
