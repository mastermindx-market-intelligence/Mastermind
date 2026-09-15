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
    text = _read(ACTIVE)
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
    text = _read(ACTIVE)
    assert "two consecutive material work cycles" in text
    assert "NO_DELTA_LOOP" in text
    assert "Do not produce a third equivalent" in text


def test_blocked_lane_does_not_end_turn_while_independent_work_exists():
    text = _read(ACTIVE)
    assert "Treat a blocker as lane-local first" in text
    assert "switch to it immediately and continue" in text
    assert "every materially useful in-scope lane is blocked" in text


def test_effect_unknown_is_terminal_only_when_no_safe_independent_lane_remains():
    text = _read(ACTIVE)
    assert "does not itself permit finalization while another useful lane is provably independent" in text
    assert "makes every remaining useful in-scope action" in text
    assert "independent of that uncertainty" in text


def test_tool_reprobe_requires_a_material_capability_reason():
    text = _read(ACTIVE)
    assert "discover the needed schema/capability once" in text
    assert "do not repeatedly rediscover the same failure" in text
    assert "connection/device/schema change" in text


def test_background_continuation_requires_a_real_durable_owner():
    text = _read(ACTIVE)
    assert "A ChatGPT reasoning turn is not a daemon" in text
    assert "Never claim work will continue in the background" in text
    assert "real external durable owner" in text


def test_procedure_rejects_a_duplicate_control_plane():
    text = _read(ACTIVE)
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
    assert "Prefer Astra Pro for concentrated design and judgment" in text
    assert "Prefer Sol Pro for sustained delivery orchestration" in text
    assert "provisional task-fit preferences, not capability guarantees" in text
    assert "Never turn observed duration into a minimum run, timeout promise, or stopping target" in text


def test_assignment_boundary_cannot_be_shrunk_after_planning():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert "Never shrink an end-to-end assignment to a design-only assignment" in text
    assert "A design result does not complete its parent delivery programme" in text
    assert "finish early when its actual assigned outcome is accepted" in text


def test_model_preference_does_not_transfer_incumbent_authority():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert "Exactly one current action-authoritative owner" in text
    assert "No mandatory Astra-to-Sol-to-worker chain" in text
    assert "Do not replace an incumbent principal" in text
    assert "not new runtime roles, model aliases, or permission grants" in text


def test_complete_outcomes_default_to_fabric():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    assert "Default to the existing fabric for independently executable bounded outcomes" in text
    assert "Delegate an outcome, not a command-by-command conversation" in text
    assert "investigation may ask a bounded question without prescribing its answer" in text
    assert "framing + review + expected repair + critical-path delay" in text


def test_direct_work_has_closed_reasons_and_reassessment():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    for reason in ("LOWER_TOTAL_OVERHEAD", "PRINCIPAL_JUDGMENT", "UNIQUE_APPROVED_ACCESS",
                   "CRITICAL_PATH_SHORTCUT", "NO_ELIGIBLE_PRE_EFFECT_WORKER"):
        assert reason in text
    assert "Reassess when discovery becomes routine execution" in text
    assert "No fixed delegation percentage or tool-call quota" in text


def test_dispatch_requires_existing_owner_admission():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    assert "All actual submissions use the current approved Executive ingress" in text
    assert "Confidentiality, budget, provider activation, credential state, and workspace custody" in text
    assert "A listed model or reviewed realm alone is not positive admission" in text
    assert "never duplicate a STARTed or EFFECT_UNKNOWN operation" in text


def test_parent_keeps_useful_work_after_dispatch():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert "Dispatch is not a finalization reason" in text
    assert "Continue the highest-leverage unblocked principal work" in text
    assert "Do not duplicate the worker's assigned investigation" in text
    assert "Deterministic waits and routine placement remain with existing owners" in text


def test_worker_repairs_are_budgeted_and_progress_sensitive():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert "repair allowance comes from the admitted job" in text
    assert "Two equivalent failures with no new evidence trigger reassessment" in text
    assert "A new failure signature or changed candidate can justify another bounded attempt" in text
    assert "Do not kill, reset, or replace a worker outside the existing cancellation" in text


def test_result_summary_is_backed_by_exact_evidence():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert "exact artifact revision/digest, actual validation results" in text
    assert "Summaries are navigation, not proof" in text
    assert "Do not replay full worker transcripts" in text
    assert "Review deeply where consequence or uncertainty requires it" in text


def test_parallelism_respects_global_admission_and_review_capacity():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert "Global Capacity and the existing child/depth/budget policy bound fanout" in text
    assert "Do not multiply a per-chat allowance across sessions" in text
    assert "Unconsumed review work applies backpressure" in text


def test_checkpoint_does_not_transfer_authority_or_invent_continuation():
    text = _section("Step 7A — Preserve operational continuity before interruption")
    assert "Checkpoint after a material accepted result and before a long or effectful operation" in text
    assert "A checkpoint never transfers a lease, source writer, or STARTed operation" in text
    assert "Exact parent consumption must be proven" in text
    assert "No supported continuation means an honest held result, not a fabricated wake" in text


def test_role_pressure_cases_are_explicit_and_not_behavioral_proof():
    text = _section("Role-aware pressure cases")
    for phrase in ("Astra owns the whole delivery", "Sol receives a routine implementation",
                   "One worker returns while another runs", "A cheap provider is disarmed",
                   "A worker repeats the same unsuccessful loop"):
        assert phrase in text
    assert "These cases are specifications, not recorded model behavior" in text


def test_measurement_rewards_accepted_outcomes_not_elapsed_time():
    text = _section("Step 7A — Preserve operational continuity before interruption")
    assert "accepted capability progress per Pro turn" in text
    assert "Separate successful early completion from premature stopping and platform interruption" in text
    assert "Do not score longer runtime as better performance" in text
    assert "existing evaluation and evidence owners; no new telemetry store" in text


def test_design_acceptance_has_a_designated_decision_owner():
    text = _section("Step 1A — Select principal duty without inventing authority")
    assert "Acceptance belongs to the decision owner named by the assignment or current source law" in text
    assert "pickup acknowledgment is not by itself design acceptance or a transfer of source custody" in text


def test_manual_carrier_cannot_be_self_approved_by_a_worker():
    text = _section("Step 2A — Decide execution ownership before routine labor")
    assert "Manual-carrier acceptance comes from current source law and its designated authority" in text
    assert "neither a worker nor this procedure can self-approve a new transport" in text


def test_cosmetic_revision_does_not_reset_failed_loop_reassessment():
    text = _section("Step 2B — Overlap judgment and execution without multiplying management")
    assert "A changed revision alone is not evidence of useful repair" in text
    assert "a cosmetic edit does not reset reassessment" in text


# Cross-skill enrollment/ownership boundaries, not fresh-model behavior.
def test_detailed_delegation_owner_requires_accepted_same_source_enrollment():
    text = _section("Procedural ownership and companion enrollment")
    assert "WEB_CEO_DELEGATION.md" in text
    assert "accepted enrollment in the same pinned INDEX" in text
    assert "Before accepted enrollment" in text
    assert "candidate file, an evaluation bundle, or another branch is not enrollment" in text


def test_delegation_companion_does_not_duplicate_active_turn_controller():
    text = _section("Procedural ownership and companion enrollment")
    assert "ACTIVE_EXECUTION remains the sole active-turn owner" in text
    assert "capability delta, lane-local blocking, no-delta re-planning, and finalization" in text
    assert "detailed role selection, delegation economics, worker packets, and capacity policy" in text
    assert "do not create another stop-state machine or routing catalog" in text


def test_companion_disagreement_preserves_incumbent_effects_and_source_pin():
    text = _section("Procedural ownership and companion enrollment")
    assert "material disagreement requires RECONCILE_STATE" in text
    assert "Do not mix procedure revisions" in text
    assert "does not transfer an incumbent writer, authorize a retry, or relax admission" in text
    assert "explanatory notes, not a second closed routing taxonomy" in text
