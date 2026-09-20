"""Source and existing-evaluator packet contracts, NOT served-model proof."""
import json
from pathlib import Path
import pytest
from scripts.ohf.fresh_sol_eval import ScenarioPacket

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "docs/sol_skills"
CORPUS = ROOT / "research/fixtures/pro_continuity_reliability_2026-09-19.json"

def text(name):
    return (SKILLS / name).read_text(encoding="utf-8")

def section(name, heading):
    raw = text(name)
    marker = "## " + heading + "\n"
    assert raw.count(marker) == 1
    return " ".join(raw.split(marker, 1)[1].split("\n## ", 1)[0].split())

def test_only_existing_finalization_owner_defines_continuation_disposition():
    active = section("ACTIVE_EXECUTION.md", "Step 8 — Final-response gate")
    assert "`CHECKPOINTED_CONTINUATION`" in active
    assert "not an Executive Job/Attempt status" in active
    assert "MISSION_COMPLETE: false" in active
    for name in ("INDEX.md", "WEB_CEO_DELEGATION.md"):
        assert "CHECKPOINTED_CONTINUATION" in text(name)
        assert "ACTIVE_EXECUTION" in text(name)

@pytest.mark.parametrize("clause", [
    "specific chunk boundary or observed continuity risk",
    "verified persistence receipt/readback",
    "exact next action and intended resume surface",
    "elapsed time alone",
    "same-carrier reconciliation",
    "no autonomous wake",
])
def test_continuation_gate_preserves_required_guards(clause):
    assert clause in section("ACTIVE_EXECUTION.md", "Step 8 — Final-response gate")

def test_no_boundary_means_continue_not_checkpoint_as_excuse():
    active = section("ACTIVE_EXECUTION.md", "Step 8 — Final-response gate")
    assert "checkpoint is not itself a reason to stop" in active
    assert "If the truthful classification is `MORE_WORK_EXISTS`, **do not finalize**" in active
    assert "completed plan or arbitrary time target" in active

def test_checkpoint_precedes_risky_work_and_is_cumulative():
    raw = section("ACTIVE_EXECUTION.md", "Step 7A — Preserve operational continuity before interruption")
    for clause in ("before long/effectful/high-output operations", "Do not defer all persistence",
                   "last verified effect", "rejected approaches", "hypotheses and falsifiers",
                   "working checkpoint", "immutable transfer capsule"):
        assert clause in raw

def test_recovery_is_checkpoint_first_without_unconditional_history_replay():
    raw = text("COLD_START.md")
    for clause in ("latest verified cumulative checkpoint", "exact program/operation",
                   "material invalidators", "no valid checkpoint", "bounded canonical recovery",
                   "do not follow a handoff history chain"):
        assert clause in raw

def test_handoff_does_not_claim_web_compaction_or_custody_transfer():
    raw = text("COLD_START.md") + text("ACTIVE_EXECUTION.md")
    for clause in ("does not prove host-side transcript compaction", "genuinely new chat",
                   "does not transfer a lease", "Project history may still be supplied"):
        assert clause in raw

def test_resource_evidence_is_observed_not_fabricated():
    raw = text("ACTIVE_EXECUTION.md")
    for clause in ("hidden reasoning budgets and unexposed deadlines remain UNKNOWN",
                   "route-local observed payload", "not total ChatGPT context",
                   "requested work profile", "observed model/mode", "no fixed 20-minute"):
        assert clause in raw

def test_closeout_rejects_chat_only_checkpoint_and_ambiguous_write_retry():
    raw = text("CLOSEOUT.md")
    for clause in ("cumulative checkpoint", "verified persistence receipt/readback",
                   "chat-only or local scratch note is not a durable checkpoint",
                   "EFFECT_UNKNOWN", "same write carrier", "immutable transfer capsule"):
        assert clause in raw

def test_research_profile_requires_decision_not_first_outline():
    raw = text("WEB_CEO_DELEGATION.md")
    for clause in ("decision-ready", "credible alternatives", "strongest counterargument",
                   "discriminating acceptance", "not a minimum run length"):
        assert clause in raw

def test_bootstrap_still_uses_protected_source_and_contains_no_live_operation():
    # Bootstrap migration is a separate, explicitly uncompleted rollout gate.
    # Existing watcher/placement tests remain unchanged and mandatory.
    raw = text("BOOTSTRAP_KERNEL.md").split("```text\n", 1)[1].split("```", 1)[0]
    assert "docs/sol_skills/INDEX.md" in raw
    assert "protected master" in raw
    assert "SAME repository + commit" in raw
    assert "pro-continuity-reliability-20260919-sol-001" not in raw

@pytest.mark.parametrize("scenario_id", [f"PCR{i:02d}" for i in range(1,18)])
def test_pressure_cases_use_existing_fresh_sol_packet(scenario_id):
    rows = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert [r["scenario_id"] for r in rows] == [f"PCR{i:02d}" for i in range(1,18)]
    row = next(r for r in rows if r["scenario_id"] == scenario_id)
    assert set(row) == {"scenario_id", "prompt", "pass_requires"}
    packet = ScenarioPacket(**row)
    for value in (packet.prompt, packet.pass_requires):
        assert 40 <= len(value) <= 2500
    assert "PASS:" in packet.pass_requires and "FAIL:" in packet.pass_requires


def test_negative_capability_claim_requires_current_action_family_evidence():
    step6 = section("ACTIVE_EXECUTION.md", "Step 6 — Discover exact action capability, then react to evidence")
    for clause in (
        "`UNKNOWN` / `UNPROBED` is never equivalent to `UNAVAILABLE`",
        "successful READ does not prove that a WRITE/ADMIN action is unavailable",
        "non-mutating permission/capability/binding preflight",
        "Never perform a dummy mutation solely to prove capability",
        "requested action family",
        "discovery result",
        "exact explicit refusal/error",
        "technical tool/action exposure",
        "authenticated resource permission/serviceability",
        "organizational/source-writer authority",
        "effect state",
    ):
        assert clause in step6


def test_terminal_capability_blockers_are_evidence_gated():
    gate = section("ACTIVE_EXECUTION.md", "Step 8 — Final-response gate")
    for clause in (
        "capability-based `EXACT_HUMAN_GATE`",
        "`PLATFORM_FAILURE`",
        "`ALL_SCOPED_LANES_BLOCKED`",
        "current discovery result",
        "exhausted safe probes",
        "exact human/admin ceremony",
        "truthful classification is `MORE_WORK_EXISTS`",
    ):
        assert clause in gate


def test_github_read_only_observation_cannot_settle_write_capability():
    rows = {row["scenario_id"]: row for row in json.loads(CORPUS.read_text(encoding="utf-8"))}
    p12 = rows["PCR12"]
    assert "GitHub reads have succeeded" in p12["prompt"]
    assert "WRITE as UNKNOWN/UNPROBED" in p12["pass_requires"]
    assert "non-mutating repository permission/serviceability preflight" in p12["pass_requires"]
    assert "source-writer authority separately" in p12["pass_requires"]
    assert "EXACT_HUMAN_GATE" in p12["pass_requires"]


def test_explicit_write_refusal_is_negative_control_not_global_read_only_claim():
    rows = {row["scenario_id"]: row for row in json.loads(CORPUS.read_text(encoding="utf-8"))}
    p17 = rows["PCR17"]
    assert "explicitly refuses WRITE" in p17["prompt"]
    assert "technical/resource evidence" in p17["pass_requires"]
    assert "organizational/source-writer authority separate" in p17["pass_requires"]
    assert "dummy mutation" in p17["pass_requires"]
    assert "whole platform read-only" in p17["pass_requires"]
