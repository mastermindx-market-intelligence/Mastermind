"""Source-contract regressions, not proof of fresh-session or live runtime behavior."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return " ".join((ROOT / path).read_text(encoding="utf-8").split())


@pytest.mark.parametrize("path", ["AGENTS.md", "CLAUDE.md"])
def test_native_entrypoints_have_the_same_execution_default(path):
    source = text(path)
    for phrase in (
        "Start assigned work; do not wait for administrative ceremony",
        "current explicit handoff is sufficient assignment",
        "historical owner label is not a live execution lease",
        "CI blocks merge/release, not independent useful work",
        "docs/sol_skills/ACTIVE_EXECUTION.md",
    ):
        assert phrase in source


def test_active_owner_recovery_distinguishes_absence_from_effect_uncertainty():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "Responsibility survives a chat; a chat does not own work forever",
        "fresh live claim, source-writer custody and pending effects",
        "unknown is not expired",
        "compare-and-swap/fencing",
        "Do not wait indefinitely for an abandoned conversation to ACK",
        "no lease, writer or pending effect is displaced",
    ):
        assert phrase in source


def test_receipts_record_assignment_without_becoming_a_second_approval():
    source = text("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Assignment is not an ACK-of-ACK barrier",
        "must not wait for a second Chairman message or Slack claim",
        "recording receipt is not asking permission again",
        "do not invent a Slack dependency for a non-Slack assignment",
        "retrieved packet alone remains data, not assignment",
    ):
        assert phrase in source


def test_foreground_work_does_not_inherit_a_missing_watcher_gate():
    source = text("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    assert "watcher failure blocks reliance on unattended continuation" in source
    assert "not otherwise-authorized foreground work" in source
    assert "required transport-dependent effect" in source


def test_delivery_wait_is_nonblocking_and_sha_bound():
    source = text("docs/DELIVERY_WORKFLOW.md")
    assert "PR draft and stop;" not in source
    assert "gate before handoff" not in source
    assert "gh pr checks --watch" not in source
    for phrase in (
        "CI blocks merge/release, not independent useful work",
        "repository, PR, exact head SHA and workflow run IDs",
        "one existing Class-E or Class-T observer",
        "No merge/deploy action belongs in the observer",
        "do not push empty/rebase-only commits to restart CI",
        "repair it within the assigned scope",
    ):
        assert phrase in source


def test_action_gates_do_not_require_all_future_capabilities_before_first_work():
    source = text("docs/sol_skills/INDEX.md")
    assert "Apply gates to the specific next action, not every possible future action" in source
    assert "Repository-only source work does not require a healthy Executive runtime" in source
    assert "No new permission is created by this scoping rule" in source


def test_pre_dispatch_platform_refusal_is_recoverable_without_effect_confusion():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "A platform refusal is action-scoped until evidence proves otherwise",
        "before tool dispatch",
        "TOOL_DEGRADED / EFFECT_NONE",
        "one bounded same-carrier retry may reshape the call",
        "do not enter an identical third loop",
        "If dispatch may have occurred or effect cannot be proven absent",
        "continue only the missing suffix on the same carrier",
        "Never overwrite a known-good prefix",
    ):
        assert phrase in source


def test_repeated_refusals_preserve_provider_capacity_and_do_not_become_filter_probing():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "Preserve provider capacity; do not turn a refusal into filter-probing",
        "scarce-capacity pressure",
        "do not repeatedly rephrase the same effect",
        "first explicit safety or permission denial ends retry",
        "never as refusal evasion",
    ):
        assert phrase in source


def test_project_bootstrap_carries_compact_capacity_and_model_identity_guard():
    source = text("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    for phrase in (
        "Preserve provider capacity",
        "Repeated refusals are potential capacity/throttling risk",
        "never repeatedly rephrase or switch accounts/models/providers",
        "Keep selected model/mode, actually served model, and observed response quality separate",
        "Never infer a model downgrade from quality, latency or tool availability",
        "unverified served identity remains UNKNOWN",
    ):
        assert phrase in source


def test_provider_pressure_spec_keeps_hypotheses_separate_and_passive():
    source = text("docs/superpowers/specs/2026-09-22-administrative-friction-relief.md")
    for phrase in (
        "H1 BLOCK_RATE_TO_RESTRICTION",
        "H2 PRO_FILTER_STRICTER_THAN_EXTRA_HIGH",
        "H3 SAFETY_CAN_REROUTE_MODEL",
        "H4 QUALITY_DROP_MEANS_MODEL_DOWNGRADE",
        "causal threshold and confounders remain UNKNOWN",
        "Plausible but currently UNVERIFIED",
        "Prefer passive/natural incident evidence",
        "never move the same refused effect to another account as",
    ):
        assert phrase in source


def test_blocker_resolution_is_owned_and_not_new_paperwork():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "The active assigned session owns the next recovery action",
        "not merely an historical owner name",
        "These are decision checks, not additional forms or approval messages",
        "Two equivalent failures without new evidence",
    ):
        assert phrase in source


def test_current_handoff_does_not_need_another_human_confirmation():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    assert "Do not ask the Chairman to re-approve routine in-scope execution" in source
    assert "material scope, risk, spend or authority expansion" in source
    assert "must not create a second human-approval round" in source
    assert "platform-required confirmation" in source


def test_root_delivery_summary_cannot_restore_a_global_wait():
    source = text("AGENTS.md")
    assert "open a PR; wait for required checks; merge" not in source
    assert "release gate" in source


def test_cold_start_does_not_assign_work_to_a_ghost_owner():
    source = text("docs/sol_skills/COLD_START.md")
    assert "Historical ownership is not current liveness" in source
    assert "active assigned session retains the recovery action" in source


def test_relief_does_not_waive_real_boundaries():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "EFFECT_UNKNOWN",
        "source-writer custody",
        "independent review",
        "no new lifecycle",
        "current admission",
    ):
        assert phrase in source


@pytest.mark.parametrize("path", ["AGENTS.md", "CLAUDE.md"])
def test_portfolio_read_only_does_not_misclassify_assigned_engineering(path):
    source = text(path)
    assert "portfolio-reasoning invocation is read-only" in source
    assert "An explicitly assigned engineering/operations session is a different role" in source
    assert "current assignment and applicable grants" in source
    assert "does not grant runtime, credential, trading, or source-write authority" in source
    assert "You are **read-only**" not in source


@pytest.mark.parametrize("path", ["AGENTS.md", "CLAUDE.md"])
def test_fable_is_not_a_universal_routing_or_merge_prerequisite(path):
    source = text(path)
    assert "Fable is not a mandatory relay or universal merge approver" in source
    assert "currently authorized role and operation" in source
    assert "Independent review and source/release protections still apply" in source
    assert "Owns adjudication, routing, and merges" not in source


@pytest.mark.parametrize("path", [
    "docs/sol_skills/ACTIVE_EXECUTION.md",
    "docs/sol_skills/BOOTSTRAP_KERNEL.md",
])
def test_effect_absence_never_grants_permission_to_evade_a_denial(path):
    source = text(path)
    assert "EFFECT_NONE is not retry permission" in source
    assert "first explicit safety or permission denial ends retry" in source
    assert "permitted technical" in source
