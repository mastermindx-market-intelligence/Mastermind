"""Static regression pins for the Sol active-execution discipline.

These checks prove that the protected procedural contract is present and internally
coherent. They do not prove fresh-model behavior or production execution.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "docs" / "sol_skills"
ACTIVE = SKILLS / "ACTIVE_EXECUTION.md"
INDEX = SKILLS / "INDEX.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "missing skill frontmatter"
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def test_active_execution_skill_is_compatible_with_current_pack():
    text = _read(ACTIVE)
    meta = _frontmatter(text)
    assert meta == {
        "schema": "mastermind.sol_skillpack.v1",
        "skillpack_version": "1.0.1",
        "minimum_bootstrap_major": "1",
        "skill": "active_execution",
    }


def test_index_registers_active_execution_and_forward_motion_law():
    text = _read(INDEX)
    assert "### `ACTIVE_EXECUTION.md`" in text
    assert re.search(r"^23\.\s+Forward execution\.", text, re.MULTILINE)
    assert "MORE_WORK_EXISTS" in text


def test_final_response_gate_is_closed_vocabulary_and_more_work_cannot_finalize():
    text = " ".join(_read(ACTIVE).split())
    for state in (
        "PROVEN_OUTCOME",
        "EXACT_HUMAN_GATE",
        "EFFECT_UNKNOWN",
        "ALL_SCOPED_LANES_BLOCKED",
        "PLATFORM_FAILURE",
        "DURABLE_EXECUTION_RUNNING",
        "MORE_WORK_EXISTS",
    ):
        assert state in text
    assert "If the truthful classification is `MORE_WORK_EXISTS`, **do not finalize**" in text


def test_non_delta_loop_forces_replan_before_third_artifact_cycle():
    text = " ".join(_read(ACTIVE).split())
    assert 'Two consecutive material cycles' in text
    assert "NO_DELTA_LOOP" in text
    assert "Do not produce a third equivalent" in text


def test_blocked_lane_does_not_end_turn_while_independent_work_exists():
    text = " ".join(_read(ACTIVE).split())
    assert "Treat a blocker as lane-local first" in text
    assert 'immediately advance the highest-value safe path-disjoint dependency' in text
    assert 'no materially useful lane remains' in text


def test_effect_unknown_is_terminal_only_when_no_safe_independent_lane_remains():
    text = " ".join(_read(ACTIVE).split())
    assert 'continue only work whose safety and result are provably independent of it' in text
    assert 'makes every useful action unsafe/dependent' in text
    assert 'independent of it; otherwise reconcile on the original carrier' in text


def test_tool_reprobe_requires_a_material_capability_reason():
    text = " ".join(_read(ACTIVE).split())
    assert 'discover each needed action family/schema once' in text
    assert 'Re-probe only after relevant' in text
    assert 'connection/device/schema/mode/session change' in text


def test_background_continuation_requires_a_real_durable_owner():
    text = " ".join(_read(ACTIVE).split())
    assert "A ChatGPT reasoning turn is not a daemon" in text
    assert 'Background claims require canonical accepted/started execution evidence' in text
    assert 'production-proven Executive, Workbench/process, provider-worker or watcher/dialogue owner' in text


def test_procedure_rejects_a_duplicate_control_plane():
    text = " ".join(_read(ACTIVE).split())
    assert "does **not** create a lifecycle, scheduler, retry engine, memory store, queue" in text
    assert "no new lifecycle, queue, retry, memory, permission, or control plane" in text


# Role-aware delegation amendments. These are source-contract checks only.
# Deleting/inverting each named policy rule must break its corresponding test;
# genuine Astra/Sol behavior must be measured by the existing fresh-session owner.
def _section(heading: str) -> str:
    text = _read(ACTIVE)
    marker = f"## {heading}\n"
    assert text.count(marker) == 1, f"missing or duplicate section: {heading}"
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def test_principal_preferences_are_not_duration_or_capability_guarantees():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert 'Astra Pro provisionally fits concentrated thesis/design/synthesis/architecture/adversarial judgment' in text
    assert 'Sol Pro fits sustained sequencing, return adjudication and integration' in text
    assert 'Either can do either when actual fit, capability and continuity support it' in text
    assert 'Duration is neither guarantee, minimum nor stopping target' in text


def test_assignment_boundary_cannot_be_shrunk_after_planning():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert 'Never narrow end-to-end delivery to design after writing a plan' in text
    assert 'Parent delivery continues across child milestones' in text
    assert 'finish an actually accepted assignment early' in text


def test_model_preference_does_not_transfer_incumbent_authority():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert 'exactly one action-authoritative owner per modifying mission' in text
    assert 'No mandatory principal chain' in text
    assert 'model preference transfers no incumbent or started operation' in text
    assert 'No mandatory principal chain, new role/alias, automatic Pro selection or fabricated admission receipt' in text


def test_complete_outcomes_default_to_fabric():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    assert 'Prefer paid Fabric for independently executable bounded outcomes when eligible' in text
    assert 'without command-by-command parent approval' in text
    assert 'an investigation need not prescribe its answer' in text
    assert 'framing, review, expected repair and delay' in text


def test_direct_work_has_closed_reasons_and_reassessment():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    for reason in ("LOWER_TOTAL_OVERHEAD", "PRINCIPAL_JUDGMENT", "UNIQUE_APPROVED_ACCESS",
                   "CRITICAL_PATH_SHORTCUT", "NO_ELIGIBLE_PRE_EFFECT_WORKER"):
        assert reason in text
    assert 'Reassess as discovery becomes routine' in text
    assert 'use neither a delegation percentage nor a tool-call or agent quota' in text


def test_dispatch_requires_existing_owner_admission():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    assert 'Submit only through approved Executive ingress' in text
    assert 'Confidentiality, bounded spend, provider activation, credentials and workspace custody' in text
    assert 'A listed model/realm is not admission' in text
    assert 'never duplicate STARTed/unknown work' in text


def test_parent_keeps_useful_work_after_dispatch():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert 'Dispatch does not end the turn' in text
    assert 'Advance independent principal judgment, integration or returned work' in text
    assert 'do not duplicate a worker or invent filler' in text
    assert 'Existing deterministic owners handle waits/placement' in text


def test_worker_repairs_are_budgeted_and_progress_sensitive():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert 'Repair allowance comes from the admitted job' in text
    assert 'Two equivalent failures require reassessment' in text
    assert 'A genuinely changed candidate/input/failure signature may justify another bounded attempt' in text
    assert 'Cancellation/reset/replacement retains its existing effect contract' in text


def test_result_summary_is_backed_by_exact_evidence():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert 'artifact identity/digest, validation, findings, blockers and next decision' in text
    assert 'A summary navigates to proof; it does not replace proof' in text
    assert 'without replaying full transcripts or all labor' in text
    assert 'Read decisive underlying evidence' in text


def test_parallelism_respects_global_admission_and_review_capacity():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert 'Global Capacity and existing child/depth/budget grants bound fanout' in text
    assert 'bound fanout across sessions' in text
    assert 'Unconsumed review backlogs require useful review/integration before more dispatch' in text


def test_checkpoint_does_not_transfer_authority_or_invent_continuation():
    text = _section("Step 7A — Preserve operational continuity before interruption")
    assert "Save material decisions and accepted capability changes at coherent milestones" in text
    assert 'not after each read/edit/test' in text
    assert 'A checkpoint/new chat transfers no lease, source writer or STARTed operation' in text
    assert 'Verify original-parent consumption' in text
    assert 'No supported continuation means a held result, not an invented wake' in text


def test_role_pressure_cases_are_explicit_and_not_behavioral_proof():
    text = _section("Role-aware pressure cases")
    for phrase in ('Whole-delivery Astra', 'Routine implementation to Sol',
                   'Consume returned workers without an artificial all-workers-finished barrier', 'Disarmed cheap provider',
                   'Repeated failed worker loop'):
        assert phrase in text
    assert 'These are specifications, not model receipts' in text


def test_measurement_rewards_accepted_outcomes_not_elapsed_time():
    text = _section("Step 7A — Preserve operational continuity before interruption")
    assert "accepted capability progress per Pro turn" in text
    assert 'separate waiting, early success, premature stop and platform failure' in text
    assert 'Neither elapsed time nor source tests prove hidden reasoning or fresh-model behavior' in text
    assert 'Through existing evaluators measure accepted capability progress' in text


def test_design_acceptance_has_a_designated_decision_owner():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert "Acceptance belongs to the decision owner named by the assignment or current source law" in text
    assert 'intended recipient or pickup alone is neither acceptance nor custody transfer' in text


def test_manual_carrier_cannot_be_self_approved_by_a_worker():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    assert "Manual-carrier acceptance comes from current source law and its designated authority" in text
    assert 'no raw spawn, self-approved transport or second queue' in text


def test_cosmetic_revision_does_not_reset_failed_loop_reassessment():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert 'cosmetic revisions do not reset the count' in text
    assert 'cosmetic revisions do not reset the count' in text


# Cross-skill enrollment/ownership boundaries, not fresh-model behavior.
def test_detailed_delegation_owner_requires_accepted_same_source_enrollment():
    text = _section("Procedural ownership and companion enrollment")
    assert "WEB_CEO_DELEGATION.md" in text
    assert 'Accepted same-pin INDEX enrollment' in text
    assert "Before accepted enrollment" in text
    assert 'candidates/evaluation bundles/other branches are not law' in text


def test_delegation_companion_does_not_duplicate_active_turn_controller():
    text = _section("Procedural ownership and companion enrollment")
    assert "ACTIVE_EXECUTION remains the sole active-turn owner" in text
    assert "capability delta, lane-local blocking, no-delta re-planning, and finalization" in text
    assert 'detailed role/economics/packet/capacity owner' in text
    assert 'no second stop machine, Runtime role or routing catalog' in text


def test_companion_disagreement_preserves_incumbent_effects_and_source_pin():
    text = _section("Procedural ownership and companion enrollment")
    assert "material disagreement requires RECONCILE_STATE" in text
    assert "Do not mix procedure revisions" in text
    assert 'Precedence resolution transfers no writer, retry or admission' in text
    assert 'Reason labels are explanatory, not Runtime enums' in text


# Adaptive attended-mode and recovery source contracts. These are procedural tests, not provider proof.
def test_attended_mode_recommendation_is_task_and_capability_adaptive():
    text = " ".join(_section("Step 1B — Adapt attended reasoning mode to the current phase").split())
    for phrase in (
        'Sol owns the mode recommendation',
        'Pro for deep research, synthesis, architecture and adjudication',
        'Extra High for iterative coding, terminal/browser work, tests and writes',
        'defaults, not guaranteed capabilities',
        'Pro may have or lose a write',
        'Extra High is only a recovery candidate',
        'One successful READ/WRITE',
        'Do not bounce mature Sol Pro to Extra High and back merely for tools',
    ):
        assert phrase in text


def test_attended_mode_switch_never_grants_authority_or_bypasses_denial():
    text = " ".join(_section("Step 1B — Adapt attended reasoning mode to the current phase").split())
    for phrase in (
        'Switching grants no authority, admission, permission, custody, carrier transfer or retry',
        'clears neither denial nor `EFFECT_UNKNOWN`',
        'clears neither denial nor `EFFECT_UNKNOWN`',
        'Automated Executive/ModelRouter admission',
        "`PRO_MODE_TASK_CLASS`",
        "Text cannot self-switch",
        'Reverify the exact needed capability after a relevant change',
    ):
        assert phrase in text


def test_context_rotation_is_procedural_and_effect_fenced():
    text = " ".join(_section("Step 7A — Preserve operational continuity before interruption").split())
    for phrase in (
        "exact surface is `ROTATION_REQUIRED`",
        'Before actual rotation reconcile effects',
        'persist the frontier, seal and use one lawful successor',
        '`CONTEXT_ROTATION` is procedural, not completion, acceptance, finalization, failover or custody transfer',
        '`EFFECT_UNKNOWN` blocks receiver change and rotation',
    ):
        assert phrase in text


def test_final_gate_projects_platform_and_ui_recovery_without_new_lifecycle_states():
    text = " ".join(_section("Step 8 — Final-response gate").split())
    assert "`PLATFORM_FAILURE` is a blocker reason, not a finalization classification" in text
    assert '`MODE_SWITCH`/`FRESH_CHAT`' in text
    assert 'are control/recovery reasons, not lifecycle states' in text
    assert "`CHECKPOINTED_CONTINUATION`" in text
    assert "`NOT_CANONICALLY_PERSISTED`" in text
    assert "`EFFECT_UNKNOWN` only for an ambiguous checkpoint write" in text
    assert "`EXACT_HUMAN_GATE` only for a real human/admin ceremony" in text
    assert "`ALL_SCOPED_LANES_BLOCKED`" in text
    assert "`MORE_WORK_EXISTS`" in text


def test_long_run_phase_contract_fences_breadth_without_shortening_productive_turns():
    text = " ".join(_section("Step 1 — Freeze the active-turn frame").split())
    for phrase in (
        "ACTIVE_PHASE",
        "PHASE_DONE_WHEN",
        "ALLOWED_SURFACES",
        "DEFERRED_NONBLOCKING_FINDINGS",
        "Depth is allowed; breadth is fenced",
        'One blocker may open one bounded subphase',
        'a second broad blocker requires re-evaluation',
    ):
        assert phrase in text


def test_attended_mode_policy_is_session_sticky_after_substantial_work_begins():
    text = " ".join(_section("Step 1B — Adapt attended reasoning mode to the current phase").split())
    for phrase in (
        'Mode stickiness is the default',
        'Mode stickiness is the default',
        'Do not bounce mature Sol Pro',
        "tool-heavy",
        "fresh-chat boundary",
    ):
        assert phrase in text


def test_phase_barrier_separates_mission_incomplete_from_current_turn_lifetime():
    text = " ".join(_section("Step 7A — Preserve operational continuity before interruption").split())
    for phrase in (
        "recovery gap",
        "PHASE BARRIER",
        "MORE_WORK_EXISTS",
        '**start that next phase in the same turn**',
        'same-chat continuation',
        'At a **PHASE BARRIER**, verify/save and reassess',
    ):
        assert phrase in text


def test_phase_barrier_pins_healthy_same_turn_continuation_decision():
    text = " ".join(_section("Step 7A — Preserve operational continuity before interruption").split())
    assert "**start that next phase in the same turn**" in text
    assert 'Healthy output pressure alone does not require a turn boundary' in text
    assert 'Healthy output pressure alone does not require a turn boundary' in text


def test_support_only_cycles_are_not_capability_delta_or_stop_reason():
    text = " ".join(_section("Step 3 — Require a capability delta, not activity").split())
    for phrase in (
        "review requests",
        'messages',
        'status/projection/CI reads',
        'status/projection/CI reads',
        'checkpoints',
        'status/projection/CI reads',
        'count only when they unlock, de-risk or prove the capability',
        "NO_DELTA_LOOP",
        'execute a useful ready action in the same scope',
    ):
        assert phrase in text


def test_waiting_external_is_lane_local_and_not_durable_execution():
    blocker = " ".join(_section("Step 4 — Treat a blocker as lane-local first").split())
    offload = " ".join(_section("Step 7 — Offload work that should outlive the reasoning turn").split())
    for phrase in (
        "`WAITING_EXTERNAL` is lane-local",
        "review request",
        "owner message",
        "pending CI/check",
        'immediately advance the highest-value safe path-disjoint dependency',
    ):
        assert phrase in blocker
    assert "is not `DURABLE_EXECUTION_RUNNING`" in offload
    assert 'proven STARTED/RUNNING and an armed lawful return/wake' in offload


def test_checkpointed_continuation_rejects_clean_phase_or_wait_as_exit_coupon():
    text = " ".join(_section("Step 8 — Final-response gate").split())
    for phrase in (
        "observed continuity risk",
        "materially heavy/context-expanding next phase",
        "ordinary clean task/phase/chunk/checkpoint boundary",
        "review request",
        "owner message",
        "pending CI",
        'cannot end healthy useful work',
        'Continue safe next units',
    ):
        assert phrase in text
    assert "A specific chunk boundary or observed continuity risk" not in text
    assert 'a specific chunk boundary alone is no longer sufficient' in text


def test_more_work_exists_continues_across_task_and_phase_boundaries():
    text = " ".join(_section("Step 8 — Final-response gate").split())
    assert "If the truthful classification is `MORE_WORK_EXISTS`, **do not finalize**" in text
    assert 'advance the highest-value unblocked dependency while healthy' in text
    assert 'support cycles or completed chunks cannot invent it' in text


def test_persistence_failure_does_not_invent_human_or_effect_state():
    text = " ".join(_section("Step 8 — Final-response gate").split())
    required = (
        "ambiguous checkpoint write",
        "`EFFECT_UNKNOWN` only for an ambiguous checkpoint write",
        "`EXACT_HUMAN_GATE` only for a real human/admin ceremony",
        "proven persistence/platform outage",
        "`ALL_SCOPED_LANES_BLOCKED`",
        "safe independent work remains",
        "`MORE_WORK_EXISTS`",
    )
    for phrase in required:
        assert phrase in text
