from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_watcher_action_loop_is_canonical_and_action_oriented() -> None:
    skill_path = ROOT / "docs/sol_skills/WATCHER_ACTION_LOOP.md"
    assert skill_path.exists(), "watcher action-loop law must be a canonical Sol skill"

    skill = skill_path.read_text(encoding="utf-8")
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
        assert phrase in skill, f"missing watcher action-loop law: {phrase}"

    assert "notification-only watcher" in index
    assert "detect -> re-pin -> adjudicate -> act -> report" in kernel.lower()
