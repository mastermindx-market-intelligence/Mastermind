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
        'CAS/fencing',
        'act without a ghost ACK',
        'With assignment and no displaced writer/effect',
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
        "Reuse one existing observer when it reduces a genuinely long wait",
        "No merge/deploy action belongs in the observer",
        "do not push empty/rebase-only commits to restart CI",
        "repair it within the assigned scope",
    ):
        assert phrase in source


def test_action_gates_do_not_require_all_future_capabilities_before_first_work():
    source = text("docs/sol_skills/INDEX.md")
    assert 'Gate the next action/dependency, not the mission' in source
    assert 'Source work needs Executive only when it invokes/depends on that authority' in source
    assert 'Assignment, pin, custody, resource permission and effect fences still bind' in source


def test_pre_dispatch_platform_refusal_is_recoverable_without_effect_confusion():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "A platform refusal is action-scoped until evidence proves otherwise",
        "before tool dispatch",
        "TOOL_DEGRADED / EFFECT_NONE",
        'one bounded same-carrier reshaping after exact-target reread',
        "do not enter an identical third loop",
        'Possible dispatch means reconcile `EFFECT_UNKNOWN`, never replay/failover',
        'continue only a permitted missing suffix on the same carrier',
        'never overwrite known-good bytes after refusal',
    ):
        assert phrase in source


def test_repeated_refusals_preserve_provider_capacity_and_do_not_become_filter_probing():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "Preserve provider capacity; do not turn a refusal into filter-probing",
        'Unknown throttling thresholds do not justify blocked-call experiments',
        'no rephrasing or tool/carrier/account/model/provider substitution',
        "first explicit safety or permission denial ends retry",
        'other-account work requires ordinary routing and genuine independence',
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


def test_transport_outage_is_not_misclassified_as_provider_safety_pressure():
    active = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    bootstrap = text("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    spec = text("docs/superpowers/specs/2026-09-22-administrative-friction-relief.md")
    for phrase in (
        "Do not contaminate provider-refusal evidence with transport loss",
        'Offline/timeout without explicit safety evidence is transport, not throttling',
        'Cause differs from effect',
        'without explicit safety evidence is transport',
    ):
        assert phrase in active
    for phrase in (
        "Keep network/host/connector outages separate from provider safety refusals",
        "do not count an offline state or timeout as a blocked safety call or throttling datum",
        "connectivity loss can still require same-carrier EFFECT_UNKNOWN reconciliation",
    ):
        assert phrase in bootstrap
    for phrase in (
        "Treat network/host/connector loss as a negative control",
        "Do not count those events toward blocked-call or throttling observations",
        "Network/host/connector goes offline or times out without explicit provider safety evidence",
        "exclude the incident from safety/throttling counts",
    ):
        assert phrase in spec


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
        'The active assigned session owns the next recovery action',
        'These are action checks for all assigned provider sessions, not additional forms',
        'Two unchanged failures require new evidence/hypothesis',
    ):
        assert phrase in source


def test_current_handoff_does_not_need_another_human_confirmation():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    assert "Do not ask the Chairman to re-approve routine in-scope execution" in source
    assert 'material scope/risk/spend/authority expansions' in source
    assert 'playbooks add no approval round' in source
    assert 'actual platform confirmation/authentication/consent' in source


def test_root_delivery_summary_cannot_restore_a_global_wait():
    source = text("AGENTS.md")
    assert "open a PR; wait for required checks; merge" not in source
    assert "release gate" in source


def test_cold_start_does_not_assign_work_to_a_ghost_owner():
    source = text("docs/sol_skills/COLD_START.md")
    assert "Historical ownership is not current liveness" in source
    assert 'Current assignment owns the next recovery action' in source


def test_relief_does_not_waive_real_boundaries():
    source = text("docs/sol_skills/ACTIVE_EXECUTION.md")
    for phrase in (
        "EFFECT_UNKNOWN",
        "source-writer custody",
        "independent review",
        "no new lifecycle",
        'INDEX admission',
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
    assert "Independent review is not mandatory for CEO Web work" in source
    assert "protected source/release controls still apply" in source
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

def test_legacy_original_writer_note_does_not_override_current_assignment():
    for rel in ("AGENTS.md", "CLAUDE.md", "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md"):
        source = text(rel).lower()
        assert "original writer" in source
        assert "current" in source and "recovery" in source
        assert "lease" in source or "custody" in source
    kernel = text("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    assert 'Current assigned receiver owns recovery even if a handoff says "original writer"' in kernel


def test_web_scenarios_distinguish_ghost_parent_from_real_sticky_effect():
    import json

    cases = json.loads((ROOT / "tests/fixtures/web_ceo_skill_cases.json").read_text())["cases"]
    by_id = {item["id"]: item for item in cases}
    ids = {
        "ceo-archived-original-writer-live-delivery",
        "ceo-archived-chat-live-sticky-effect",
        "ceo-old-packet-no-current-assignment",
    }
    assert ids <= by_id.keys()
    for case_id in ids:
        case = by_id[case_id]
        assert case["expected_skills"] == ["mastermind-web-ceo"]
        assert case["must_observe"] and case["must_not_observe"]
    assert "original parent chat" in " ".join(
        by_id["ceo-archived-original-writer-live-delivery"]["must_not_observe"]
    )
    assert "EFFECT_UNKNOWN" in by_id["ceo-archived-chat-live-sticky-effect"]["prompt"]
    assert "no current Chairman assignment" in by_id["ceo-old-packet-no-current-assignment"]["prompt"]


def test_handoff_writer_never_disclaims_to_ghost_parent():
    closeout = text("docs/sol_skills/CLOSEOUT.md")
    assert "Do not write a continuation whose only next action is" in closeout
    assert "the original writer or parent must act" in closeout
    assert "a reachable currently assigned receiver" in closeout
    assert "STARTed" in closeout and "EFFECT_UNKNOWN" in closeout
    for rel in ("AGENTS.md", "CLAUDE.md", "docs/SOL_CEO_ACCOUNT_INSTRUCTIONS.md"):
        source = text(rel)
        assert "When writing a handoff, name a safe next action" in source
        assert "original parent" in source
    kernel = text("docs/sol_skills/BOOTSTRAP_KERNEL.md")
    assert "Handoffs name an executable successor action" in kernel
    import json
    cases = json.loads((ROOT / "tests/fixtures/web_ceo_skill_cases.json").read_text())["cases"]
    case = next(c for c in cases if c["id"] == "ceo-handoff-writer-no-ghost-receiver")
    assert case["expected_skills"] == ["mastermind-web-ceo"]
    assert case["must_observe"] and case["must_not_observe"]
