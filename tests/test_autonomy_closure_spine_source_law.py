from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md"
PLAN = ROOT / "docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md"
COMPLETION_MODE = ROOT / "docs/superpowers/plans/2026-09-02-autonomy-completion-mode.md"

BEGIN = "<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_BEGIN -->"
END = "<!-- AUTONOMY_CLOSURE_SPINE_V1_CONTRACT_END -->"
OPERATION = "autonomy-closure-spine-f0-20260903-sol-001"
PROTECTED_PICKUP = "7022e70640637a4fa07f073442dc693301290e2a"
RECORD_PATHS = [
    "docs/superpowers/specs/2026-09-03-autonomy-closure-spine-v1-design.md",
    "docs/superpowers/plans/2026-09-03-autonomy-closure-spine-v1.md",
    "tests/test_autonomy_closure_spine_source_law.py",
]


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


def test_design_and_plan_publish_one_identical_closed_contract() -> None:
    design = _contract(DESIGN)
    plan = _contract(PLAN)
    assert design == plan
    assert design["schema"] == "mastermind.autonomy_closure_spine.v1"
    assert design["operation"] == OPERATION
    assert design["parent_incident"] == "Mastermind#386"
    assert design["closed_duplicate_not_owner"] == "Mastermind#400"
    assert design["protected_pickup"] == PROTECTED_PICKUP
    assert design["record_paths"] == RECORD_PATHS
    assert design["current_state"] == {
        "capability": "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT",
        "implementation_started": False,
        "runtime_effect": False,
        "provider_effect": False,
        "production_armed": False,
        "worker_assigned": False,
    }


def test_architecture_exception_is_one_observed_golden_path_blocker() -> None:
    completion = _read(COMPLETION_MODE)
    assert "NO_NEW_AUTONOMY_ARCHITECTURE" in completion
    assert "closes a concrete blocker" in completion
    exception = _contract(DESIGN)["architecture_exception"]
    assert exception == {
        "default_preserved": "NO_NEW_AUTONOMY_ARCHITECTURE",
        "concrete_blocker": (
            "the exact action-authoritative Sol target exists, but no Runtime-owned "
            "compare-and-swap semantic directive binds one exact return to one effective "
            "CONTINUE, REPAIR, STOP, or ESCALATE decision"
        ),
        "golden_path_edge_unlocked": (
            "terminal return -> exact Sol attention -> one effective Sol decision -> "
            "one next same-root transition"
        ),
        "observed_incident_class": [
            "conflicting W3C scope directives",
            "stale C2 retreat after START_RESUMED",
        ],
    }
    assert _contract(DESIGN)["authorized_pre_fleet_layers"] == ["ACF-1"]


def test_existing_owners_and_no_rebuild_boundary_are_closed() -> None:
    contract = _contract(DESIGN)
    assert contract["owners"] == {
        "lifecycle_and_atomic_commit": "Executive Runtime",
        "current_sol_target": "SessionTargetRegistry / RuntimeBinding / Stage B",
        "terminal_return": "existing Executive terminal-return owner",
        "attention_delivery_ack": "Wake / W3C / Agent Relay",
        "dialogue_transport": "Agent Dialogue",
        "next_orchestration_mutation": "existing COO cycle",
        "operational_projection": "existing Control Room",
        "organizational_memory": "Agent OS",
        "implementation_evidence": "GitHub",
    }
    assert contract["no_rebuild"] == {
        "new_lifecycles": [],
        "new_databases": [],
        "new_queues": [],
        "new_schedulers": [],
        "new_retry_planes": [],
        "new_watcher_registries": [],
        "new_runtime_binding_stores": [],
        "new_authority_registries": [],
        "new_transcript_stores": [],
        "new_control_room_truth_stores": [],
        "slack_as_runtime_authority": False,
    }


def test_directive_wire_binds_return_target_actor_revision_and_closed_body() -> None:
    acf1 = _contract(DESIGN)["acf1_semantic_directive_convergence"]
    assert acf1["command_schema"] == "mastermind.executive_semantic_directive_command/v1"
    assert acf1["event_schema"] == "mastermind.executive_semantic_directive/v1"
    assert acf1["event_type"] == "EXECUTIVE_SEMANTIC_DIRECTIVE_COMMITTED"
    assert acf1["decisions"] == ["CONTINUE", "REPAIR", "STOP", "ESCALATE"]
    assert acf1["actor_classes"] == ["ACTION_TARGET", "CHAIRMAN"]
    assert acf1["runtime_generated_fields"] == ["directive_id", "created_at"]
    assert acf1["required_fields"] == [
        "directive_id",
        "root_job_id",
        "source_job_id",
        "source_attempt_id",
        "source_worker_id",
        "consumed_terminal_event_id",
        "consumed_terminal_event_digest",
        "current_target_alias",
        "current_target_binding_id",
        "current_target_binding_generation",
        "current_target_reasoning_surface",
        "actor_class",
        "actor_identity_receipt_digest",
        "carrier_reference",
        "predecessor_directive_id",
        "revision",
        "decision",
        "decision_body",
        "decision_payload_digest",
        "supersedes_directive_id",
        "created_at",
    ]
    assert acf1["forbidden_fields"] == [
        "prompt",
        "model_output",
        "transcript",
        "arbitrary_slack_prose",
        "credential",
        "account_email",
        "provider_secret",
        "browser_content",
        "raw_url",
        "reusable_authority_token",
    ]


def test_command_identity_forces_competing_decisions_into_one_conflict_domain() -> None:
    identity = _contract(DESIGN)["acf1_semantic_directive_convergence"]["command_identity"]
    assert identity["scope"] == "one terminal-return revision"
    assert identity["fields"] == [
        "root_job_id",
        "consumed_terminal_event_id",
        "consumed_terminal_event_digest",
        "predecessor_directive_id",
        "revision",
    ]
    assert identity["excludes"] == [
        "decision",
        "decision_body",
        "decision_payload_digest",
        "actor_class",
        "actor_identity_receipt_digest",
        "current_target_binding_id",
        "current_target_binding_generation",
        "created_at",
    ]
    assert "CONTINUE and STOP" in identity["reason"]
    assert "parallel directives" in identity["reason"]


def test_authority_commit_supersession_and_consumption_fail_closed() -> None:
    acf1 = _contract(DESIGN)["acf1_semantic_directive_convergence"]
    assert acf1["authority_semantics"] == {
        "carrier_reference_is_provenance_only": True,
        "runtime_reresolves_current_target_and_actor": True,
        "model_slack_browser_and_provider_labels_grant_no_authority": True,
    }
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
    assert acf1["supersession_semantics"] == {
        "history_is_immutable": True,
        "chairman_may_supersede_only_before_consumption_with_downstream_effect_none": True,
        "consumed_applied_or_effect_unknown_requires_reconciliation": True,
        "normal_target_rotation_never_supersedes": True,
        "new_revision_binds_predecessor_and_supersedes_ids": True,
    }
    assert acf1["consumer"] == {
        "owner": "existing COO cycle",
        "reads_slack_prose": False,
        "consumes_effective_event_once": True,
        "downstream_command_binds_directive_event_id_digest_and_revision": True,
        "downstream_event_is_consumption_receipt": True,
        "separate_consumption_table_created": False,
        "directive_is_not_provider_start_retry_merge_or_deploy": True,
    }


def test_only_acf1_is_pre_fleet_and_later_layers_are_evidence_gated() -> None:
    layers = _contract(DESIGN)["conditional_follow_on_layers"]
    assert list(layers) == ["ACF-2", "ACF-3", "ACF-4", "ACF-5", "ACF-6"]
    assert layers == {
        "ACF-2": {
            "name": "mission-envelope enforcement",
            "start_gate": "post-golden-root evidence of admission/accounting gap",
            "reuse_owner": "existing DelegationPacket and Executive admission",
        },
        "ACF-3": {
            "name": "useful-progress versus heartbeat",
            "start_gate": "post-golden-root stall falsifier cannot close through checkpoints",
            "reuse_owner": "existing Attempt checkpoint and Event plane",
        },
        "ACF-4": {
            "name": "truthful production acceptance",
            "start_gate": "one real golden-root result exists",
            "reuse_owner": "existing root Event and production-proof owners",
        },
        "ACF-5": {
            "name": "resource finalization",
            "start_gate": "installed golden root exposes concrete required resources",
            "reuse_owner": "the existing owner of each created resource",
        },
        "ACF-6": {
            "name": "producer-consumer compatibility receipt",
            "start_gate": "an installed-generation incompatibility is reproduced",
            "reuse_owner": "existing release and capability owners",
        },
    }


def test_acf1_routing_is_waiting_not_a_false_assignment() -> None:
    assert _contract(DESIGN)["acf1_routing"] == {
        "future_operation_key": "autonomy-semantic-directive-convergence-acf1-20260903-sol-001",
        "preferred_avenue": "CTO Sol",
        "why_not_fable": (
            "the Chairman outcome, owner map, event semantics, failure matrix, "
            "no-rebuild boundaries, and acceptance are frozen"
        ),
        "receiver_binding_mode": "CAPACITY_SELECTABLE",
        "placement_state": (
            "WAITING_ARCHITECTURE_PROTECTION / WAITING_RUNTIME_PATH_RELEASE / needs_placement"
        ),
        "cognition_route": "CHAT_INCLUDED_DEFAULT",
        "chat_reasoning_mode": "NON_PRO_DEFAULT",
        "worker_facing_commission_created": False,
        "implementation_branch_created": False,
        "implementation_started": False,
    }


def test_records_remain_honest_about_source_and_production_state() -> None:
    for path in (DESIGN, PLAN):
        text = _read(path)
        for phrase in (
            "records-only",
            "source protection is not production proof",
            "zero Chairman message shuttle",
            "one independently useful vertical",
            "no implementation START",
            "post-consumption reversal",
        ):
            assert phrase in text, f"{path} must preserve {phrase!r}"
    assert _contract(DESIGN)["f0_stop_condition"] == (
        "one current-base three-path Draft/HOLD PR with source-law proof, terminal "
        "hosted repository/security checks, and one independent exact-head review; "
        "no Runtime Event, worker, provider call, deployment, canary, or fleet promotion"
    )
