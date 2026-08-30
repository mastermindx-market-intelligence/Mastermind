from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_watcher_action_loop_is_canonical_and_action_oriented() -> None:
    skill_path = ROOT / "docs/sol_skills/WATCHER_ACTION_LOOP.md"
    assert skill_path.exists(), "watcher action-loop law must be a canonical Sol skill"

    skill = skill_path.read_text(encoding="utf-8")
    normalized_skill = " ".join(skill.split())
    index = _read("docs/sol_skills/INDEX.md")
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")

    assert "WATCHER_ACTION_LOOP.md" in index
    assert "WATCHER_ACTION_LOOP.md" in kernel

    required_skill_phrases = (
        "A Sol watcher is an action re-entry hook, not a notification service.",
        "DETECT -> RE-PIN -> ADJUDICATE -> ACT -> REPORT",
        "Do not stop at `Sol action required`",
        "post the actual Sol edge in the same lawful carrier",
        "Chairman-only boundary",
        "terminal return does not authorize a new independent wave",
        "never creates or mutates Executive Job/Attempt/Worker/Event state",
    )
    for phrase in required_skill_phrases:
        assert phrase in normalized_skill, f"missing watcher action-loop law: {phrase}"

    assert "notification-only watcher" in index
    assert "detect -> re-pin -> adjudicate -> act -> report" in kernel.lower()


def test_watcher_lifetime_survives_nonterminal_events_until_stop() -> None:
    skill = _read("docs/sol_skills/WATCHER_ACTION_LOOP.md")
    normalized = " ".join(skill.split())

    required_lifetime_phrases = (
        "ACK, WATCH_ARMED, START, and PROGRESS are nonterminal watcher events",
        "advance the consumed baseline and keep or re-arm the Sol watcher",
        "BLOCKED, DECISION_REQUEST, and RESULT are action-required watcher events",
        "Never disable Sol's continuation watcher before sending the worker's terminal STOP.",
        "ACK -> WATCH_ARMED -> START -> RESULT -> STOP",
        "Only after the terminal STOP edge is sent may Sol disarm its watcher for that child operation",
    )
    for phrase in required_lifetime_phrases:
        assert phrase in normalized, f"missing watcher lifetime invariant: {phrase}"


def test_temporary_sol_watchers_use_structured_role_contract() -> None:
    skill = _read("docs/sol_skills/WATCHER_ACTION_LOOP.md")
    normalized = " ".join(skill.split())

    required_contract_phrases = (
        "MMX_SOL_WATCHER_V1",
        "ACTION_AUTHORITATIVE",
        "OBSERVER_ONLY",
        "PARENT_ORCHESTRATOR",
        "TRIAGE_ONLY",
        "SAME_CARRIER_SOL_EDGE_OR_TYPED_BLOCKER",
        "NOTIFICATION_ONLY_SELF_DEADLOCK",
        "python3 scripts/audit_sol_watchers.py",
        "canonical action-target transfer",
        "never elect by recency",
    )
    for phrase in required_contract_phrases:
        assert phrase in normalized, f"missing structured watcher contract law: {phrase}"
