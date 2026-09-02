from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_watcher_action_loop_is_canonical_and_action_oriented() -> None:
    skill_path = ROOT / "docs/sol_skills/WATCHER_ACTION_LOOP.md"
    assert skill_path.exists(), "watcher action-loop law must be a canonical Sol skill"

    skill = skill_path.read_text(encoding="utf-8")
    normalized = " ".join(skill.split())
    index = _read("docs/sol_skills/INDEX.md")
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")

    assert "WATCHER_ACTION_LOOP.md" in index
    assert "WATCHER_ACTION_LOOP.md" in kernel

    required = (
        "A Sol watcher is an action re-entry hook, not a notification service.",
        "DETECT -> RE-PIN -> ADJUDICATE -> ACT -> REPORT",
        "Do not stop at `Sol action required`",
        "post the actual Sol edge in the same lawful carrier",
        "Chairman-only boundary",
        "terminal return does not authorize a new independent wave",
        "never creates or mutates Executive Job/Attempt/Worker/Event state",
    )
    for phrase in required:
        assert phrase in normalized, f"missing watcher action-loop law: {phrase}"

    assert "notification-only watcher" in index
    assert "detect -> re-pin -> adjudicate -> act -> report" in kernel.lower()


def test_watcher_lifetime_survives_nonterminal_events_until_stop() -> None:
    normalized = " ".join(_read("docs/sol_skills/WATCHER_ACTION_LOOP.md").split())
    required = (
        "ACK, WATCH_ARMED, START, and PROGRESS are nonterminal watcher events",
        "advance the consumed baseline and keep or re-arm the Sol watcher",
        "BLOCKED, DECISION_REQUEST, and RESULT are action-required watcher events",
        "Never disable Sol's continuation watcher before sending the worker's terminal STOP.",
        "ACK -> WATCH_ARMED -> START -> RESULT -> STOP",
        "Only after the terminal STOP edge is sent may Sol disarm its watcher for that child operation",
    )
    for phrase in required:
        assert phrase in normalized, f"missing watcher lifetime invariant: {phrase}"


def test_watcher_prompts_are_renderer_owned_canonical_documents() -> None:
    normalized = " ".join(_read("docs/sol_skills/WATCHER_ACTION_LOOP.md").split())
    required = (
        "MMX_SOL_WATCHER_V1",
        "MMX_SOL_WATCHER_BODY_V1",
        "render_watcher_prompt",
        "CANONICAL_PROMPT_MISMATCH",
        "ACTION_AUTHORITATIVE",
        "OBSERVER_ONLY",
        "PARENT_ORCHESTRATOR",
        "TRIAGE_ONLY",
        "SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
        "ACTION_AUTHORITATIVE always requires an exact Slack carrier",
        "aggregate:<stable-scope-id>",
        "audit_kind: NON_WATCHER",
        "canonical action-target transfer",
        "never elect by recency",
        "natural-language polarity is not a validity boundary",
        "CRLF and lone-CR",
        "terminal newline",
        "python3 -m scripts.audit_sol_watchers",
    )
    for phrase in required:
        assert phrase in normalized, f"missing canonical watcher document law: {phrase}"


def test_rollout_requires_exact_render_replace_readback_not_prompt_patching() -> None:
    normalized = " ".join(_read("docs/sol_skills/WATCHER_ACTION_LOOP.md").split())
    required = (
        "render the complete replacement prompt",
        "replace the complete native task prompt",
        "read the native task back",
        "byte-for-byte",
        "Do not prepend a header to arbitrary English",
        "Do not repair a watcher by adding synonyms",
        "EFFECT_UNKNOWN",
        "no cross-account retry or failover",
    )
    for phrase in required:
        assert phrase in normalized, f"missing exact rollout law: {phrase}"
