from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md"
COMPLETION_MODE = ROOT / "docs/superpowers/plans/2026-09-02-autonomy-completion-mode.md"
SOL_ACTION_TARGET = ROOT / "control_plane/sol_action_target.py"
CEO_INTENT = ROOT / "control_plane/ceo_intent.py"
COMMISSION_REF = ROOT / "common/commission_ref.py"

BEGIN = "<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->"
END = "<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->"
BODY_SCHEMA = "mastermind.executive_semantic_directive_body/v1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contract(path: Path) -> dict[str, Any]:
    match = re.search(
        re.escape(BEGIN) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(END),
        _read(path),
        re.S,
    )
    assert match, f"missing closure-spine contract in {path}"
    value = json.loads(match.group(1))
    assert isinstance(value, dict)
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _payload_digest(decision: str, body: dict[str, object]) -> str:
    return hashlib.sha256(
        _canonical_json_bytes({"decision": decision, "decision_body": body})
    ).hexdigest()


def test_design_and_plan_publish_one_identical_closed_contract() -> None:
    design, plan = _contract(DESIGN), _contract(PLAN)
    assert design == plan
    assert design["schema"] == "mastermind.autonomy_closure_spine.v1"
    assert design["operation"] == "autonomy-closure-spine-f0-20260903-sol-001"
    assert design["parent_incident"] == "Mastermind#386"
    assert design["closed_duplicate_not_owner"] == "Mastermind#400"
    assert design["protected_pickup"] == "7022e70640637a4fa07f073442dc693301290e2a"
    assert design["record_paths"] == [
        "docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md",
        "docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md",
        "tests/test_autonomy_closure_spine_source_law.py",
    ]
    assert design["current_state"] == {
        "capability": "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT",
        "implementation_started": False,
        "runtime_effect": False,
        "provider_effect": False,
        "production_armed": False,
        "worker_assigned": False,
    }


def test_exception_owner_map_and_no_rebuild_are_closed() -> None:
    completion = _read(COMPLETION_MODE)
    contract = _contract(DESIGN)
    assert "NO_NEW_AUTONOMY_ARCHITECTURE" in completion
    assert contract["architecture_exception"]["default_preserved"] == (
        "NO_NEW_AUTONOMY_ARCHITECTURE"
    )
    assert contract["architecture_exception"]["observed_incident_class"] == [
        "conflicting W3C scope directives",
        "stale C2 retreat after START_RESUMED",
    ]
    assert contract["authorized_pre_fleet_layers"] == ["ACF-1"]
    assert contract["owners"] == {
        "lifecycle_and_atomic_commit": "Executive Runtime",
        "current_sol_target": (
            "control_plane.sol_action_target / SessionTargetRegistry / "
            "RuntimeBindingSnapshot"
        ),
        "terminal_return": "existing Executive terminal-return owner",
        "attention_delivery_ack": "Wake / W3C / Agent Relay",
        "dialogue_transport": "Agent Dialogue",
        "next_orchestration_mutation": "existing COO cycle",
        "operational_projection": "existing Control Room",
        "organizational_memory": "Agent OS",
        "implementation_evidence": "GitHub",
    }
    no_rebuild = contract["no_rebuild"]
    assert no_rebuild["slack_as_runtime_authority"] is False
    for key, value in no_rebuild.items():
        if key != "slack_as_runtime_authority":
            assert value == [], key


def test_acf1_reuses_the_exact_existing_action_target_owner() -> None:
    acf1 = _contract(DESIGN)["acf1_semantic_directive_convergence"]
    assert acf1["command_schema"] == (
        "mastermind.executive_semantic_directive_command/v1"
    )
    assert acf1["event_schema"] == "mastermind.executive_semantic_directive/v1"
    assert acf1["event_type"] == "EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED"
    assert acf1["decisions"] == ["CONTINUE", "REPAIR", "STOP", "ESCALATE"]
    assert acf1["actor_classes"] == ["ACTION_TARGET"]
    owner = acf1["actor_authority_owner"]
    assert owner == {
        "module": "control_plane.sol_action_target",
        "schema": "mastermind.sol_action_target.v1",
        "resolver": "require_sol_action_authority",
        "resolution_type": "SolActionTargetResolution",
        "receipt_field": "evidence_digest",
        "inputs": [
            "root_job_id",
            "SessionTargetRegistry",
            "RuntimeBindingSnapshot",
            "actor_binding",
        ],
        "transaction_law": [
            "resolve from current canonical inputs inside the Runtime write transaction",
            "require state RESOLVED and action_authoritative true",
            (
                "bind alias, binding id, generation and reasoning surface from "
                "the same resolution"
            ),
            (
                "re-resolve immediately before append because the resolution is "
                "evidence, not a reusable authority token"
            ),
        ],
        "non_authorities": [
            "Slack sender or prose",
            "browser session label",
            "model output",
            "provider account",
            "carrier_reference",
            "current Chairman chat text as a Runtime principal",
        ],
    }

    source = _read(SOL_ACTION_TARGET)
    assert 'SCHEMA = "mastermind.sol_action_target.v1"' in source
    assert "class SolActionTargetResolution:" in source
    assert "def require_sol_action_authority(" in source
    assert "evidence_digest: str" in source
    assert "evidence, not a reusable authority" in source


def test_direct_chairman_runtime_actor_is_deliberately_absent_from_v1() -> None:
    contract = _contract(DESIGN)
    acf1 = contract["acf1_semantic_directive_convergence"]
    assert "CHAIRMAN" not in acf1["actor_classes"]
    assert (
        acf1["supersession_semantics"][
            "direct_machine_authenticated_chairman_actor_in_v1"
        ]
        is False
    )
    assert (
        acf1["supersession_semantics"][
            "fresh_chairman_intervention_is_submitted_by_then_current_action_target_as_revision_n_plus_1"
        ]
        is True
    )
    assert acf1["supersession_semantics"]["projection_reason"] == (
        "DIRECTIVE_SUPERSEDED"
    )
    serialized = json.dumps(contract, sort_keys=True)
    assert "CHAIRMAN_SUPERSEDED" not in serialized
    assert "CHAIRMAN_AUTHORITY_INVALID" not in serialized
    assert "new_authority_registries" in contract["no_rebuild"]
    assert contract["no_rebuild"]["new_authority_registries"] == []


def test_decision_body_union_is_exact_bounded_and_owned() -> None:
    acf1 = _contract(DESIGN)["acf1_semantic_directive_convergence"]
    body = acf1["decision_body_contract"]
    assert acf1["body_schema"] == BODY_SCHEMA
    assert body["python_type"] == "built-in dict"
    assert body["max_canonical_utf8_bytes"] == 4096
    assert body["canonicalizer"] == "control_plane.ceo_intent.canonical_json_bytes"
    assert body["payload_digest"] == (
        "sha256(canonical_json_bytes({'decision': decision, "
        "'decision_body': body}))"
    )
    assert body["null_allowed"] is False
    assert body["list_allowed"] is False
    assert body["extension_keys_allowed"] is False
    assert body["outer_and_body_decision_must_match"] is True

    assert body["shapes"]["CONTINUE"] == {
        "schema": BODY_SCHEMA,
        "decision": "CONTINUE",
    }
    repair = body["shapes"]["REPAIR"]
    assert repair["schema"] == BODY_SCHEMA
    assert repair["decision"] == "REPAIR"
    assert repair["repair_ref"]["owner"] == (
        "common.commission_ref.normalize_commission_ref"
    )
    assert repair["repair_ref"]["authority"] == "immutable source identity only"
    assert body["shapes"]["STOP"]["reason_code"] == [
        "MISSION_COMPLETE",
        "WORK_CANCELLED",
        "NONRECOVERABLE_CONFLICT",
        "SUPERSEDED_CHILD",
    ]
    assert body["shapes"]["ESCALATE"]["reason_code"] == [
        "CHAIRMAN_DECISION_REQUIRED",
        "EFFECT_RECONCILIATION_REQUIRED",
        "AUTHORITY_BOUNDARY_REQUIRED",
        "PRODUCTION_ACCEPTANCE_REQUIRED",
    ]
    assert set(body["shapes"]) == {"CONTINUE", "REPAIR", "STOP", "ESCALATE"}
    assert "arbitrary prose or generic action maps" in body["refuses"]
    assert "cross-decision fields" in body["refuses"]
    assert "payload over 4096 canonical UTF-8 bytes" in body["refuses"]

    ceo_intent = _read(CEO_INTENT)
    commission_ref = _read(COMMISSION_REF)
    assert "def canonical_json_bytes(" in ceo_intent
    assert "def normalize_commission_ref(" in commission_ref


def test_all_body_variants_have_stable_canonical_payload_digests() -> None:
    continue_body = {"schema": BODY_SCHEMA, "decision": "CONTINUE"}
    repair_body = {
        "schema": BODY_SCHEMA,
        "decision": "REPAIR",
        "repair_ref": {
            "repository": "mastermindx-market-intelligence/Mastermind",
            "commit": "1" * 40,
            "path": "docs/repair.md",
            "content_sha256": "2" * 64,
        },
    }
    stop_body = {
        "schema": BODY_SCHEMA,
        "decision": "STOP",
        "reason_code": "MISSION_COMPLETE",
    }
    escalate_body = {
        "schema": BODY_SCHEMA,
        "decision": "ESCALATE",
        "reason_code": "CHAIRMAN_DECISION_REQUIRED",
    }
    variants = {
        "CONTINUE": continue_body,
        "REPAIR": repair_body,
        "STOP": stop_body,
        "ESCALATE": escalate_body,
    }
    digests = {
        decision: _payload_digest(decision, body)
        for decision, body in variants.items()
    }
    assert len(set(digests.values())) == 4
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in digests.values())
    assert _payload_digest("CONTINUE", continue_body) == _payload_digest(
        "CONTINUE", dict(reversed(list(continue_body.items())))
    )
    changed = dict(stop_body)
    changed["reason_code"] = "WORK_CANCELLED"
    assert _payload_digest("STOP", changed) != digests["STOP"]


def test_command_identity_forces_competing_decisions_to_collide() -> None:
    identity = _contract(DESIGN)["acf1_semantic_directive_convergence"][
        "command_identity"
    ]
    assert identity["scope"] == "one terminal-return revision"
    assert identity["fields"] == [
        "root_job_id",
        "consumed_terminal_event_id",
        "consumed_terminal_event_digest",
        "predecessor_directive_id",
        "revision",
    ]
    assert "decision" in identity["excludes"]
    assert "decision_body" in identity["excludes"]
    assert "actor_identity_receipt_digest" in identity["excludes"]
    assert "must collide in one command domain" in identity["reason"]


def test_commit_supersession_and_consumer_boundaries_are_closed() -> None:
    acf1 = _contract(DESIGN)["acf1_semantic_directive_convergence"]
    assert acf1["commit_semantics"] == {
        "compare_root_return_and_predecessor_revision": True,
        "one_effective_directive_per_return_revision": True,
        "exact_replay_is_idempotent_after_current_revalidation": True,
        "changed_payload_is_command_replay_conflict": True,
        "observer_sol_is_zero_effect_refusal": True,
        "stale_target_generation_is_zero_effect_refusal": True,
        "late_superseded_attempt_is_zero_effect_refusal": True,
        "transport_loss_after_commit_uses_event_readback": True,
        "transport_success_without_runtime_commit_is_not_effective": True,
        "continue_and_stop_cannot_both_be_effective": True,
    }
    supersession = acf1["supersession_semantics"]
    assert supersession["history_is_immutable"] is True
    assert (
        supersession[
            "current_action_target_may_supersede_own_unconsumed_directive_with_same_generation_and_effect_none"
        ]
        is True
    )
    assert (
        supersession[
            "consumed_applied_or_effect_unknown_requires_reconciliation"
        ]
        is True
    )
    assert supersession["normal_target_rotation_never_supersedes"] is True
    assert supersession["new_revision_binds_predecessor_and_supersedes_ids"] is True

    consumer = acf1["consumer"]
    assert consumer["owner"] == "existing COO cycle"
    assert consumer["reads_slack_prose"] is False
    assert consumer["consumes_effective_event_once"] is True
    assert (
        consumer["consumption_and_downstream_mutation_share_one_existing_transaction"]
        is True
    )
    assert consumer["separate_consumption_table_created"] is False
    assert consumer["directive_is_not_provider_start_retry_merge_or_deploy"] is True
    assert consumer["fixed_meanings"] == {
        "CONTINUE": "run the already-lawful next transition for the same root",
        "REPAIR": (
            "resume or amend only the existing same-root child identified by "
            "repair_ref"
        ),
        "STOP": (
            "terminalize the current child or root boundary without originating "
            "a successor"
        ),
        "ESCALATE": (
            "hold the root for external decision without creating a Job, queue, "
            "watcher, or provider effect"
        ),
    }


def test_closed_results_and_proof_matrix_cover_release_blockers() -> None:
    acf1 = _contract(DESIGN)["acf1_semantic_directive_convergence"]
    assert set(acf1["closed_results"]) == {
        "COMMITTED",
        "IDEMPOTENT_REPLAY",
        "DIRECTIVE_REPLAY_CONFLICT",
        "RETURN_NOT_TERMINAL",
        "TERMINAL_EVENT_MISMATCH",
        "ACTION_TARGET_AUTHORITY_INVALID",
        "STALE_TARGET_GENERATION",
        "DIRECTIVE_SUPERSEDED",
        "DIRECTIVE_ALREADY_CONSUMED",
        "DOWNSTREAM_EFFECT_UNKNOWN",
        "INVALID_COMMAND",
    }
    proof = acf1["proof_requirements"]
    required_fragments = (
        "all four exact body variants",
        "observer, stale generation",
        "CONTINUE and STOP collide",
        "consumed, applied or effect-unknown",
        "REPAIR cannot originate a successor",
        "no direct CHAIRMAN actor",
        "restart and transport loss",
    )
    assert all(any(fragment in item for item in proof) for fragment in required_fragments)


def test_only_acf1_is_authorized_and_later_layers_are_evidence_gated() -> None:
    contract = _contract(DESIGN)
    assert contract["authorized_pre_fleet_layers"] == ["ACF-1"]
    assert set(contract["conditional_layers"]) == {
        "ACF-2",
        "ACF-3",
        "ACF-4",
        "ACF-5",
        "ACF-6",
    }
    assert all(
        "only" in description or "after" in description
        for description in contract["conditional_layers"].values()
    )
    stop = contract["stop_condition"]
    assert stop["architecture_release"] == "three protected records only"
    assert stop["implementation_state_after_release"] == (
        "WAITING_RUNTIME_PATH_RELEASE / needs_placement"
    )
    assert stop["runtime_owner_gate"] == (
        "C2-R1A releases control_plane/executive_runtime.py"
    )
    assert "no Runtime Event" in stop["no_effect_claims"]
    assert "no production proof" in stop["no_effect_claims"]


def test_design_and_plan_prose_preserve_capability_honesty() -> None:
    design = _read(DESIGN)
    plan = _read(PLAN)
    for text in (design, plan):
        assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in text
        assert "no machine-authenticated `CHAIRMAN` actor in v1" in text or (
            "No direct `CHAIRMAN` Runtime actor" in text
        )
        assert "control_plane.sol_action_target" in text
        assert "4096" in text
        assert (
            "do not originate successor" in text
            or "does not originate successor" in text
            or "cannot originate a successor" in text
        )
    assert "WAITING_RUNTIME_PATH_RELEASE" in plan
    assert "No implementation worker or successor wave may start" in design
