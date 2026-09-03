from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCH = ROOT / "research" / "MASTERMIND_AI_OPERATING_HUB_F0_ARCHITECTURE_2026-09-02.md"
PLAN = ROOT / "docs" / "superpowers" / "plans" / "2026-09-02-ai-operating-hub-h0-h4-rollout.md"
EVIDENCE = ROOT / "research" / "evidence" / "ai_operating_hub_f0_archaeology_2026-09-02.json"


def _text(path: pathlib.Path) -> str:
    assert path.is_file(), f"missing protected source-law record: {path}"
    return path.read_text(encoding="utf-8")


def _evidence() -> dict:
    value = json.loads(_text(EVIDENCE))
    assert value["schema"] == "mastermind.ai_operating_hub_f0_archaeology.v2"
    return value


def test_ai_hub_is_an_umbrella_projection_not_a_second_control_plane() -> None:
    text = _text(ARCH)
    for phrase in [
        "`UMBRELLA_EXTENSION`",
        "derived operational experience and action surface",
        "Executive OS remains lifecycle and action-admission owner",
        "Agent OS remains durable organizational-memory owner",
        "Linear remains projection",
        "Slack remains transport",
        "never a canonical truth store",
        "No hidden retry, failover, optimistic completion, or status synthesis",
    ]:
        assert phrase in text


def test_protected_project_workroom_and_live_portfolio_are_consumed_not_rebuilt() -> None:
    text = _text(ARCH)
    for phrase in [
        "Project Workroom Fabric",
        "existing Chairman Control Room",
        "7 Initiatives / 64 Projects / 62 exact one-primary memberships / 2 deliberate exceptions",
        "`WS:CHAIRMAN-CONTROL-ROOM`",
        "must never fork their identity, navigation, mutation, lifecycle, or correction laws",
    ]:
        assert phrase in text
    evidence = _evidence()
    ruler = next(row for row in evidence["canonical_internal_sources"] if row["owner"] == "Linear portfolio source")["live_ruler"]
    assert ruler == {"initiatives": 7, "projects": 64, "memberships": 62, "exceptions": 2, "multi_parent_projects": 0}


def test_ai_hub_freezes_exact_authority_model_and_effect_unknown_boundaries() -> None:
    text = _text(ARCH)
    for phrase in [
        "Deterministic only:",
        "Model-generated:",
        "zero lifecycle, ranking, merge, deployment, or trading authority",
        "Same key + same fingerprint is one operation",
        "A timeout is not proof of failure",
        "EFFECT_UNKNOWN",
    ]:
        assert phrase in text


def test_first_vertical_preserves_read_only_h1_and_separate_h2_action_proof() -> None:
    text = _text(ARCH)
    block = text.split("## First independently useful vertical", 1)[1].split("## Wave architecture", 1)[0]
    for phrase in [
        "one real, active workstream",
        "Evidence Drawer",
        "disabled H1 preflight",
        "existing canonical admission path",
        "canonical receipt",
        "Duplicate submit returns the same receipt",
        "Desktop and mobile browser evidence",
    ]:
        assert phrase in block


def test_failure_states_are_explicit_and_do_not_false_green() -> None:
    text = _text(ARCH)
    block = text.split("## Required failure states", 1)[1].split("## First independently useful vertical", 1)[0]
    for phrase in [
        "partial source outage",
        "permission denied",
        "Slack delivered but runtime unconsumed",
        "effect unknown after submit",
        "implementation merged but production proof absent",
        "false-green",
    ]:
        assert phrase in block


def test_official_benchmark_learns_jobs_without_copying_authority_or_assets() -> None:
    text = _text(ARCH)
    block = text.split("## Official-source product benchmark", 1)[1].split("## Security and rights", 1)[0]
    for phrase in [
        "Linear Initiatives and Projects",
        "GitHub Copilot coding agent",
        "Microsoft Copilot Studio",
        "Atlassian Rovo Request Router",
        "copies no proprietary implementation, corpus, wording, assets, or brand identity",
    ]:
        assert phrase in block
    assert len(_evidence()["official_source_benchmark"]) == 5


def test_h0_is_only_eligible_next_wave_and_codex_h1_is_source_gated() -> None:
    text = _text(PLAN)
    assert "Only H0 is eligible" in text
    assert "H1–H4 are held" in text
    h0 = text.split("## H0", 1)[1].split("## H1", 1)[0]
    assert "No UI, API, database, cache, runtime action" in h0
    assert "One bounded H1 implementation handoff" in h0
    assert "BLOCKED SOURCE_PREDECESSOR_UNPROTECTED effect=NONE" in h0
    gate = _evidence()["h1_delivery_gate"]
    assert gate["canonical_pickup_observed"] is False
    assert gate["canonical_start_observed"] is False
    assert gate["canonical_branch_or_pr_observed"] is False


def test_collision_and_dialogue_reconciliation_are_exact() -> None:
    evidence = _evidence()
    assert evidence["protected_master"] == "e7d91bfe0f6ef176878a6a281afd459c0905e5aa"
    census = evidence["collision_census"]
    assert census["exact_branch_present_before_start"] is False
    assert census["exact_operation_pr_present_before_start"] is False
    assert census["owned_paths_present_on_protected_master_before_start"] == []
    assert len(census["owned_paths"]) == 4
    dialogue = evidence["dialogue_reconciliation"]
    assert "BLOCKED SOURCE_NOT_FOUND" in dialogue["worker_return"]
    assert "SOL CLOSED / STOP" in dialogue["sol_terminal_edge"]


def test_closed_capability_vocabulary_is_present() -> None:
    text = _text(ARCH)
    vocabulary = {
        "PROVEN_LIVE",
        "BUILT_NOT_PROVEN",
        "PARTIAL",
        "DARK_OR_DISCONNECTED",
        "BROKEN",
        "SPEC_ONLY",
        "NOT_BUILT",
        "REJECTED_BY_DESIGN",
    }
    assert vocabulary.issubset(set(re.findall(r"[A-Z_]{4,}", text)))
