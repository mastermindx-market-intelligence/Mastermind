from __future__ import annotations

import copy
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = (
    ROOT
    / "docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md"
)
PLAN = (
    ROOT
    / "docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md"
)
SESSION_TARGETS = ROOT / "control_plane/session_targets.py"
RUNTIME_BINDING_PROJECTION = ROOT / "control_plane/runtime_binding_projection.py"
WAKE_LEDGER = ROOT / "control_plane/wake_ledger.py"
WAKE_ACK_INGRESS = ROOT / "control_plane/wake_ack_ingress.py"
EXECUTIVE_RUNTIME = ROOT / "control_plane/executive_runtime.py"


DESIGN_BEGIN = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->"
DESIGN_END = "<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->"
PLAN_BEGIN = "<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->"
PLAN_END = "<!-- STAGE_B1_CORRECTION_GATE_END -->"
PATHS_BEGIN = "<!-- STAGE_B1_EXPECTED_PATHS_BEGIN -->"
PATHS_END = "<!-- STAGE_B1_EXPECTED_PATHS_END -->"
ORDER_BEGIN = "<!-- STAGE_B1_IMPLEMENTATION_ORDER_BEGIN -->"
ORDER_END = "<!-- STAGE_B1_IMPLEMENTATION_ORDER_END -->"


_REQUIRED_TOP_LEVEL = {
    "schema",
    "correction_operation",
    "supersedes_schema",
    "protected_source_disposition",
    "first_implementation_wave",
    "implementation_gate",
    "command_schema",
    "event_schema",
    "snapshot_schema",
    "event_aggregate_type",
    "event_types",
    "supported_reasoning_surfaces",
    "held_reasoning_surfaces",
    "mode_support",
    "command_wire",
    "authority_evidence_by_mode",
    "evidence_contracts",
    "projection_merge_algorithm",
    "transaction_order",
    "failure_states",
    "no_rebuild",
    "truthful_maximum_stage_b1_claim",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _json_block(text: str, begin: str, end: str) -> dict[str, object]:
    pattern = re.compile(
        re.escape(begin) + r"\s*```json\s*(.*?)\s*```\s*" + re.escape(end),
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"missing JSON block {begin}"
    value = json.loads(match.group(1))
    assert isinstance(value, dict)
    return value


def _text_block(text: str, begin: str, end: str) -> tuple[str, ...]:
    pattern = re.compile(
        re.escape(begin) + r"\s*```text\s*(.*?)\s*```\s*" + re.escape(end),
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"missing text block {begin}"
    return tuple(line.strip() for line in match.group(1).splitlines() if line.strip())


def _contract() -> dict[str, object]:
    return _json_block(_read(DESIGN), DESIGN_BEGIN, DESIGN_END)


def _gate() -> dict[str, object]:
    return _json_block(_read(PLAN), PLAN_BEGIN, PLAN_END)


def _assert_contract_shape(contract: dict[str, object]) -> None:
    assert set(contract) == _REQUIRED_TOP_LEVEL
    assert contract["schema"] == "mastermind.autonomy_stage_b_f0_contract.v2"
    assert contract["supersedes_schema"] == "mastermind.autonomy_stage_b_f0_contract.v1"
    assert contract["event_aggregate_type"] == "job"
    assert contract["event_types"] == [
        "SOL_ACTION_TARGET_ASSIGNED",
        "SOL_ACTION_TARGET_TRANSFERRED",
    ]

    modes = contract["mode_support"]
    assert isinstance(modes, dict)
    assert set(modes) == {
        "INITIAL_ASSIGNMENT",
        "SAME_ALIAS_GENERATION_SUCCESSION",
        "CROSS_ALIAS_RESPONSIBILITY_TRANSFER",
    }
    for name, value in modes.items():
        assert isinstance(name, str)
        assert isinstance(value, dict)
        assert set(value) == {
            "state",
            "stage",
            "reasoning_surfaces",
            "authority_owner",
            "required_preconditions",
            "refusal_when_missing",
        }
        assert isinstance(value["required_preconditions"], list)
        assert value["required_preconditions"]

    authority = contract["authority_evidence_by_mode"]
    assert isinstance(authority, dict)
    assert set(authority) == set(modes)
    for value in authority.values():
        assert isinstance(value, dict)
        assert set(value) == {
            "state",
            "owner",
            "source_ref_format",
            "fingerprint_fields",
            "action_time_revalidation",
        }
        assert isinstance(value["fingerprint_fields"], list)
        assert isinstance(value["action_time_revalidation"], list)
        assert value["action_time_revalidation"]

    evidence = contract["evidence_contracts"]
    assert isinstance(evidence, dict)
    assert set(evidence) == {
        "root_job",
        "session_target_policy",
        "destination_current_binding",
        "destination_target_ack",
        "source_generation_release",
        "current_assignment_history",
    }
    for value in evidence.values():
        assert isinstance(value, dict)
        assert set(value) == {
            "owner",
            "lookup",
            "aggregate_type",
            "event_type",
            "command_id_law",
            "schema_or_typed_shape",
            "required_identity",
            "effect_known_rule",
        }
        assert isinstance(value["required_identity"], list)
        assert value["required_identity"]

    command = contract["command_wire"]
    assert isinstance(command, dict)
    assert set(command) == {
        "caller_fields",
        "caller_may_supply_command_id",
        "canonical_digest_fields",
        "derived_command_id",
        "identical_replay",
        "occupied_derived_id",
        "different_semantics_same_revision",
        "transport_claimed_id_rule",
    }
    assert command["caller_may_supply_command_id"] is False
    assert "command_id" not in command["caller_fields"]
    assert command["canonical_digest_fields"] == command["caller_fields"]

    algorithm = contract["projection_merge_algorithm"]
    assert isinstance(algorithm, list)
    assert len(algorithm) == 5
    assert algorithm[0].startswith("copy every existing root")
    assert algorithm[-1] == "call with_root_job_bindings exactly once with the complete mapping"

    no_rebuild = contract["no_rebuild"]
    assert isinstance(no_rebuild, dict)
    assert no_rebuild == {
        "new_tables": [],
        "new_migrations": [],
        "new_registries": [],
        "runtime_binding_rows_mutated": False,
        "job_attempt_worker_rows_mutated": False,
        "provider_calls_in_transaction": False,
        "slack_calls_in_transaction": False,
        "ack_written_by_stage_b": False,
        "source_resolution_written_by_stage_b": False,
        "stage_a_resolver_signature_changed": False,
        "production_armed_in_stage_b1": False,
    }


def test_protected_source_incident_and_correction_are_explicit() -> None:
    design = _read(DESIGN)
    plan = _read(PLAN)
    contract = _contract()

    assert "autonomy-stage-b0-protected-source-correction-r1-20260902-sol-001" in design
    assert "autonomy-stage-b0-protected-source-correction-r1-20260902-sol-001" in plan
    assert "PROTECTED_SOURCE_CORRECTION_REQUIRED" in design
    assert "The protected v1 source law must not be implemented" in design
    assert "post-merge exact-head review" in _normalized(design)
    assert contract["protected_source_disposition"] == (
        "PROTECTED_SOURCE_CORRECTION_REQUIRED / V1_NOT_IMPLEMENTATION_AUTHORITY"
    )
    assert contract["implementation_gate"] == "HELD_UNTIL_V2_CORRECTION_PROTECTED"
    assert "SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT" in plan


def test_machine_contract_has_exact_closed_shape() -> None:
    _assert_contract_shape(_contract())


def test_supported_surface_and_modes_are_truthful() -> None:
    contract = _contract()
    modes = contract["mode_support"]

    assert contract["supported_reasoning_surfaces"] == ["codex"]
    assert contract["held_reasoning_surfaces"] == [
        {
            "reasoning_surface": "chatgpt-web",
            "state": "HELD_NOT_PROVEN",
            "missing_owners": [
                "accepted_current_runtime_binding_writer",
                "exact_semantic_ack_owner",
            ],
        }
    ]

    initial = modes["INITIAL_ASSIGNMENT"]
    assert initial["state"] == "SUPPORTED_WITH_EXISTING_ROOT_BINDING"
    assert initial["stage"] == "STAGE-B1"
    assert initial["reasoning_surfaces"] == ["codex"]
    assert initial["authority_owner"] == (
        "control_plane.session_targets.SessionTargetRegistry.policy_digest"
    )
    assert initial["refusal_when_missing"] == "INITIAL_AUTHORITY_OWNER_UNRESOLVED"

    succession = modes["SAME_ALIAS_GENERATION_SUCCESSION"]
    assert succession["state"] == "SUPPORTED_AFTER_VALID_INITIAL_ASSIGNMENT"
    assert succession["stage"] == "STAGE-B1"
    assert succession["reasoning_surfaces"] == ["codex"]
    assert succession["authority_owner"] == (
        "current Stage-B assignment + unchanged SessionTargetRegistry root/ceo alias"
    )
    assert succession["refusal_when_missing"] == "SUCCESSION_EVIDENCE_UNRESOLVED"

    cross_alias = modes["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"]
    assert cross_alias["state"] == "HELD_OWNER_UNRESOLVED"
    assert cross_alias["stage"] == "NOT_AUTHORIZED_FOR_STAGE-B1"
    assert cross_alias["reasoning_surfaces"] == []
    assert cross_alias["authority_owner"] == "NONE_ACCEPTED_IN_CURRENT_PROTECTED_SOURCE"
    assert cross_alias["refusal_when_missing"] == "CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED"


def test_authority_sources_are_exact_and_never_self_authorizing() -> None:
    contract = _contract()
    authority = contract["authority_evidence_by_mode"]

    assert authority["INITIAL_ASSIGNMENT"] == {
        "state": "SUPPORTED_WITH_EXISTING_ROOT_BINDING",
        "owner": "control_plane.session_targets.SessionTargetRegistry",
        "source_ref_format": (
            "session-target-policy:<policy_digest>:root:<root_job_id>:seat:ceo"
        ),
        "fingerprint_fields": [
            "policy_digest",
            "root_job_id",
            "target_seat",
            "session_alias",
            "reasoning_surface",
        ],
        "action_time_revalidation": [
            "root Job exists in Runtime",
            "root_job_bindings[root_job_id][ceo] exists",
            "target alias exists and target_seat is ceo",
            "target reasoning_surface is codex",
            "caller destination alias equals the policy-owned alias",
            "policy digest is recomputed inside the transaction input boundary",
        ],
    }
    assert authority["SAME_ALIAS_GENERATION_SUCCESSION"] == {
        "state": "SUPPORTED_AFTER_VALID_INITIAL_ASSIGNMENT",
        "owner": (
            "current Stage-B assignment event + control_plane.session_targets."
            "SessionTargetRegistry"
        ),
        "source_ref_format": (
            "sol-target-assignment:<root_job_id>:revision:<assignment_revision>"
        ),
        "fingerprint_fields": [
            "root_job_id",
            "assignment_revision",
            "current_assignment_event_command_id",
            "session_target_policy_digest",
            "session_alias",
        ],
        "action_time_revalidation": [
            "current assignment history is contiguous and unique",
            "previous target equals the folded current assignment",
            "source and destination aliases are identical",
            "registry root/ceo alias remains identical",
            "destination binding generation is strictly greater",
            "source generation release and destination ACK are exact and effect-known",
        ],
    }
    assert authority["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"]["state"] == (
        "HELD_OWNER_UNRESOLVED"
    )
    assert authority["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"]["owner"] == (
        "NONE_ACCEPTED_IN_CURRENT_PROTECTED_SOURCE"
    )
    assert authority["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"]["source_ref_format"] is None
    assert authority["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"]["fingerprint_fields"] == []
    assert authority["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"][
        "action_time_revalidation"
    ] == [
        "refuse: no current receipt schema binds root, source alias, destination alias, mode, scope, and Chairman/Executive authority",
        "refuse Slack prose, actor labels, RuntimeBinding identity, target aliases, Stage-B events, and placement results as substitute authority",
    ]


def test_evidence_contracts_name_existing_owners_and_closed_identity() -> None:
    evidence = _contract()["evidence_contracts"]

    root = evidence["root_job"]
    assert root["owner"] == "control_plane.executive_runtime.Runtime"
    assert root["lookup"] == "jobs row by exact root_job_id on the Stage-B transaction connection"
    assert root["aggregate_type"] == "job"
    assert root["event_type"] == "JOB_CREATED"
    assert root["command_id_law"] == "read existing event identity; caller supplies no Job event command id"
    assert root["required_identity"] == [
        "root_job_id",
        "root_job_id equals Job.root_job_id",
        "Job is not malformed or foreign",
    ]

    policy = evidence["session_target_policy"]
    assert policy["owner"] == "control_plane.session_targets.SessionTargetRegistry"
    assert policy["lookup"] == (
        "policy_digest() + root_job_bindings[root_job_id][ceo] + targets[session_alias]"
    )
    assert policy["aggregate_type"] is None
    assert policy["event_type"] is None
    assert policy["command_id_law"] == "not an Event; persist the recomputed policy digest and derived source_ref"

    binding = evidence["destination_current_binding"]
    assert binding["owner"] == (
        "control_plane.runtime_binding_projection.active_operator_binding_facts + "
        "project_runtime_binding"
    )
    assert binding["lookup"] == (
        "Runtime.current_harness_binding_source(attempt_id, connection=tx) then canonical projection"
    )
    assert binding["aggregate_type"] == "process_generation"
    assert binding["event_type"] == (
        "ORCHESTRATION_WORK_ADMITTED + unique OHF_LAUNCH_DECISION(ALLOW)"
    )
    assert binding["command_id_law"] == (
        "work admission is ohf-work-admit:<process_generation_id>; launch decision is selected by exact aggregate/event uniqueness, never a caller id"
    )
    assert binding["schema_or_typed_shape"] == (
        "control_plane.executive_runtime.ActiveOperatorBindingFacts"
    )
    assert "provider_session_id is consumed transiently but never persisted by Stage B" in binding[
        "effect_known_rule"
    ]

    ack = evidence["destination_target_ack"]
    assert ack["owner"] == (
        "control_plane.wake_ack_ingress.WakeAckIngressOperation + "
        "control_plane.wake_ledger"
    )
    assert ack["lookup"] == (
        "derive ledger_command_id(destination_wake_id, TARGET_ACKNOWLEDGED) and read exact wake aggregate"
    )
    assert ack["aggregate_type"] == "wake"
    assert ack["event_type"] == "TARGET_ACKNOWLEDGED"
    assert ack["command_id_law"] == "<destination_wake_id>:ACK; caller cannot override"
    assert ack["schema_or_typed_shape"] == "mastermind.wake_consumption_ack/v1"
    assert ack["required_identity"] == [
        "destination_wake_id",
        "target_seat=ceo",
        "session_alias",
        "binding_id",
        "binding_generation",
        "delivered_command_id",
        "consumed_turn_reference",
        "acknowledgement_token",
    ]

    release = evidence["source_generation_release"]
    assert release["owner"] == "control_plane.executive_runtime.Runtime"
    assert release["lookup"] == (
        "exact prior process_generation row plus its unique OHF_RECONCILE_OBSERVATION on tx"
    )
    assert release["aggregate_type"] == "process_generation"
    assert release["event_type"] == "OHF_RECONCILE_OBSERVATION"
    assert release["command_id_law"] == (
        "read the existing event command id after exact aggregate lookup; caller supplies process_generation_id only as a comparison claim"
    )
    assert release["schema_or_typed_shape"] == (
        "mastermind.operator_harness_reconcile_observation/v1"
    )
    assert release["required_identity"] == [
        "source_process_generation_id",
        "attempt_id",
        "session_epoch_id",
        "generation_number",
        "process_liveness=PROVEN_DEAD",
        "provider_writer_state=RELEASED",
        "exact observed process identity",
    ]

    history = evidence["current_assignment_history"]
    assert history["owner"] == (
        "control_plane.executive_runtime.RuntimeStore events on the root Job aggregate"
    )
    assert history["aggregate_type"] == "job"
    assert history["event_type"] == (
        "SOL_ACTION_TARGET_ASSIGNED | SOL_ACTION_TARGET_TRANSFERRED"
    )
    assert history["command_id_law"] == (
        "SOL-TARGET-<first-32-lowercase-hex-of-sha256-canonical-command-semantics>"
    )


def test_command_wire_has_nonfictional_replay_and_revision_race_semantics() -> None:
    command = _contract()["command_wire"]

    assert command["caller_fields"] == [
        "schema",
        "root_job_id",
        "mode",
        "expected_assignment_revision",
        "expected_previous_target",
        "expected_destination",
        "session_target_policy_digest",
        "destination_wake_id",
        "source_process_generation_id",
    ]
    assert command["caller_may_supply_command_id"] is False
    assert command["canonical_digest_fields"] == command["caller_fields"]
    assert command["derived_command_id"] == (
        "SOL-TARGET-<first-32-lowercase-hex-of-sha256-canonical-command-semantics>"
    )
    assert command["identical_replay"] == (
        "same canonical semantics -> same derived id -> return identical existing event"
    )
    assert command["occupied_derived_id"] == (
        "foreign or corrupt event at the derived id -> COMMAND_REPLAY_CONFLICT"
    )
    assert command["different_semantics_same_revision"] == (
        "different derived ids serialize; one append may win and the other returns EXPECTED_REVISION_MISMATCH"
    )
    assert command["transport_claimed_id_rule"] == (
        "if transport carries a claimed id, exact recomputation equality is required before lookup"
    )


def test_projection_merge_preserves_unrelated_roots_and_sibling_seats() -> None:
    contract = _contract()
    assert contract["projection_merge_algorithm"] == [
        "copy every existing root and every existing seat map from registry.root_job_bindings",
        "copy the selected root seat map or create an empty map only for that root",
        "replace only selected_root[ceo] with the folded Stage-B session_alias",
        "preserve every unrelated root and every non-ceo seat byte-semantically",
        "call with_root_job_bindings exactly once with the complete mapping",
    ]

    source = _normalized(_read(SESSION_TARGETS))
    assert "def with_root_job_bindings" in source
    assert "return dataclasses.replace(self, root_job_bindings=resolved)" in source
    assert "with_root_job_bindings replaces the complete mapping" in _normalized(_read(DESIGN))


def test_current_source_corroborates_codex_ack_and_release_boundaries() -> None:
    projection = _read(RUNTIME_BINDING_PROJECTION)
    ledger = _read(WAKE_LEDGER)
    ack_ingress = _read(WAKE_ACK_INGRESS)
    runtime = _read(EXECUTIVE_RUNTIME)

    assert '_PROVIDER_TO_REASONING_SURFACE = {"openai-codex": "codex"}' in projection
    assert "Runtime.current_harness_binding_source" in projection
    assert 'WAKE_AGGREGATE_TYPE = "wake"' in ledger
    assert 'return f"{oid}:ACK"' in ledger
    assert 'ACK_OPERATION_SCHEMA = "mastermind.wake_ack_ingress/v1"' in ack_ingress
    assert "mastermind.wake_consumption_ack/v1" in ack_ingress
    assert 'OHF_RECONCILE_OBSERVATION_SCHEMA_VERSION = (' in runtime
    assert '"mastermind.operator_harness_reconcile_observation/v1"' in runtime
    assert 'admission_command = f"ohf-work-admit:{generation.process_generation_id}"' in runtime
    assert 'event_type="ORCHESTRATION_WORK_ADMITTED"' in runtime
    assert 'aggregate_type="process_generation"' in runtime


def test_transaction_order_is_command_first_and_owner_exact() -> None:
    contract = _contract()
    assert contract["transaction_order"] == [
        "validate exact command schema and recompute command_id",
        "RuntimeStore.transaction -> BEGIN IMMEDIATE",
        "lookup derived command_id before mutable assignment or binding reads",
        "identical replay returns; corrupt occupancy conflicts",
        "read exact root Job and fold contiguous Stage-B history",
        "compare expected revision and previous target",
        "revalidate mode authority and SessionTarget policy",
        "read destination binding through current_harness_binding_source on tx",
        "read exact Wake ACK and source release evidence on tx",
        "derive observed destination and compare caller claims",
        "append one immutable event",
        "commit; response ambiguity reconciles only by the same derived command_id",
    ]
    design = _normalized(_read(DESIGN))
    assert "no automatic retry at the new assignment revision" in design
    assert "no provider, Slack, browser, filesystem, subprocess, or network call" in design


def test_failure_vocabulary_names_held_owners_and_effect_uncertainty() -> None:
    failures = _contract()["failure_states"]
    assert failures == [
        "APPLIED",
        "REPLAYED",
        "NO_ASSIGNMENT",
        "COMMAND_REPLAY_CONFLICT",
        "ASSIGNMENT_HISTORY_CONFLICT",
        "EXPECTED_REVISION_MISMATCH",
        "INITIAL_AUTHORITY_OWNER_UNRESOLVED",
        "SUCCESSION_EVIDENCE_UNRESOLVED",
        "CROSS_ALIAS_AUTHORITY_OWNER_UNRESOLVED",
        "UNSUPPORTED_REASONING_SURFACE",
        "SOURCE_TARGET_MISMATCH",
        "SOURCE_RELEASE_MISSING",
        "DESTINATION_TARGET_INVALID",
        "DESTINATION_RUNTIME_UNAVAILABLE",
        "DESTINATION_RUNTIME_CONFLICT",
        "DESTINATION_ACK_MISSING",
        "AUTHORITY_SOURCE_NOT_CURRENT",
        "EFFECT_UNKNOWN_RECONCILE_FIRST",
        "RUNTIME_TRANSACTION_UNAVAILABLE",
    ]


def test_expected_stage_b1_surface_is_exact_and_adjacent_owners_are_read_only() -> None:
    paths = _text_block(_read(DESIGN), PATHS_BEGIN, PATHS_END)
    assert paths == (
        "control_plane/sol_action_target_transfer.py",
        "control_plane/executive_runtime.py",
        "tests/test_sol_action_target_transfer.py",
        "tests/test_sol_action_target.py",
        "tests/test_executive_runtime.py",
    )
    design = _read(DESIGN)
    for protected in (
        "control_plane/session_targets.py",
        "control_plane/runtime_binding_projection.py",
        "control_plane/wake_ack_ingress.py",
        "control_plane/wake_ledger.py",
        "all provider adapters and materializers",
        "all Capacity / Model Router / Worker Browser paths",
        "all Agent OS / Linear / Slack transport paths",
    ):
        assert protected in design


def test_plan_gate_blocks_old_v1_and_cross_alias_or_web_implementation() -> None:
    gate = _gate()
    assert gate == {
        "schema": "mastermind.autonomy_stage_b1_correction_gate.v1",
        "requires_protected_design_schema": "mastermind.autonomy_stage_b_f0_contract.v2",
        "v1_implementation_authority": "REVOKED_BY_POST_MERGE_REVIEW",
        "stage_b1_state": "HELD_UNTIL_V2_CORRECTION_PROTECTED",
        "authorized_modes_after_gate": [
            "INITIAL_ASSIGNMENT",
            "SAME_ALIAS_GENERATION_SUCCESSION",
        ],
        "held_modes": ["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"],
        "supported_reasoning_surfaces": ["codex"],
        "held_reasoning_surfaces": ["chatgpt-web"],
        "requires_exact_evidence_contracts": True,
        "requires_full_root_binding_merge_preservation": True,
        "requires_derived_command_id": True,
        "production_arming": False,
    }

    order = _text_block(_read(PLAN), ORDER_BEGIN, ORDER_END)
    assert order == (
        "1. PROTECT_STAGE_B0_R1_CORRECTION",
        "2. RE_PIN_AND_COLLISION_FREEZE",
        "3. RED_COMMAND_AUTHORITY_EVIDENCE_AND_FOLD_TESTS",
        "4. IMPLEMENT_CLOSED_TYPES_AND_FULL_MAPPING_PROJECTOR",
        "5. RED_RUNTIME_TRANSACTION_REPLAY_AND_RELEASE_TESTS",
        "6. IMPLEMENT_EXISTING_RUNTIME_TRANSACTION_SEAM",
        "7. RED_REAL_STAGE_A_CONSUMER_TESTS",
        "8. INTEGRATE_CODEX_ONLY_INITIAL_AND_SAME_ALIAS_MODES",
        "9. RUN_MUTATION_FORBIDDEN_PLANE_AND_ROW_INTEGRITY_PROOF",
        "10. RUN_FOCUSED_ADJACENT_FULL_AND_SECURITY_GATES",
        "11. PUBLISH_ONE_DRAFT_HOLD_CARRIER",
        "12. INDEPENDENT_EXACT_HEAD_REVIEW",
        "13. SOL_EXPECTED_HEAD_SOURCE_RELEASE",
    )
    plan = _normalized(_read(PLAN))
    assert "Do not start Stage-B1 from the protected v1 source law" in plan
    assert "Cross-alias responsibility transfer remains held" in plan
    assert "ChatGPT-Web remains held" in plan


def test_source_law_validation_is_mutation_discriminating() -> None:
    contract = _contract()
    _assert_contract_shape(contract)

    mutations: list[dict[str, object]] = []

    missing_top = copy.deepcopy(contract)
    missing_top.pop("authority_evidence_by_mode")
    mutations.append(missing_top)

    missing_mode_owner = copy.deepcopy(contract)
    missing_mode_owner["mode_support"]["INITIAL_ASSIGNMENT"].pop("authority_owner")
    mutations.append(missing_mode_owner)

    missing_evidence_command_law = copy.deepcopy(contract)
    missing_evidence_command_law["evidence_contracts"]["destination_target_ack"].pop(
        "command_id_law"
    )
    mutations.append(missing_evidence_command_law)

    caller_command_id = copy.deepcopy(contract)
    caller_command_id["command_wire"]["caller_fields"].append("command_id")
    mutations.append(caller_command_id)

    caller_command_allowed = copy.deepcopy(contract)
    caller_command_allowed["command_wire"]["caller_may_supply_command_id"] = True
    mutations.append(caller_command_allowed)

    destructive_overlay = copy.deepcopy(contract)
    destructive_overlay["projection_merge_algorithm"] = [
        "replace registry.root_job_bindings with only the selected root"
    ]
    mutations.append(destructive_overlay)

    web_widened = copy.deepcopy(contract)
    web_widened["supported_reasoning_surfaces"] = ["codex", "chatgpt-web"]
    mutations.append(web_widened)

    cross_alias_unheld = copy.deepcopy(contract)
    cross_alias_unheld["mode_support"]["CROSS_ALIAS_RESPONSIBILITY_TRANSFER"][
        "state"
    ] = "SUPPORTED"
    mutations.append(cross_alias_unheld)

    for mutation in mutations:
        try:
            _assert_contract_shape(mutation)
        except AssertionError:
            continue
        raise AssertionError("source-law mutation unexpectedly preserved a valid contract")


def test_truthful_claim_and_no_rebuild_boundaries_are_explicit() -> None:
    contract = _contract()
    assert contract["truthful_maximum_stage_b1_claim"] == (
        "BUILT_NOT_PROVEN / CODEX_INITIAL_AND_SAME_ALIAS_SOURCE_ONLY / PRODUCTION_DISARMED"
    )
    design = _normalized(_read(DESIGN))
    plan = _normalized(_read(PLAN))

    for phrase in (
        "A Stage-B event is evidence, not a reusable authority token",
        "Stage B never writes target acknowledgement or source resolution",
        "Stage B never mutates RuntimeBinding, Job, Attempt, or Worker rows",
        "Cross-alias responsibility transfer is not built by Stage-B1",
        "ChatGPT-Web succession is not built by Stage-B1",
        "Green CI and a protected merge are not production proof",
    ):
        assert phrase in design

    for non_goal in (
        "no target pointer table",
        "no second SessionTargetRegistry",
        "no provider process or session action",
        "no Capacity selection or placement commitment",
        "no Control Room UI work",
        "no deployment, installer, credential, or production target arming",
    ):
        assert non_goal in plan
