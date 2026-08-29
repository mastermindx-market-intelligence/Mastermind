from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _flat(path: str) -> str:
    return " ".join(_read(path).split())


def test_universal_dialogue_law_has_resource_classes_and_model_wake_floor() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Class E",
        "Class T",
        "Class M",
        "Default interval: 60 minutes",
        "Absolute minimum interval: 15 minutes",
        "15m -> 30m -> 60m",
        "principals, not polling daemons",
    ):
        assert phrase in law


def test_universal_dialogue_law_makes_watcher_attention_not_scope() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "watcher prompt is not a scope fence",
        "cannot override a later valid same-operation carrier edge",
        "qualifying carrier event",
        "re-enter normal worker procedure",
        "notification-only anti-pattern",
    ):
        assert phrase in law


def test_universal_dialogue_law_requires_fresh_read_before_substantive_write() -> None:
    law = _flat("docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md")
    for phrase in (
        "Fresh-read the exact bound carrier/thread in the same interactive turn",
        "after the latest local evidence-producing action",
        "WATCH_ARMED",
        "never satisfies this freshness fence",
        "Pickup ACK",
    ):
        assert phrase in law


def test_commission_wave_rejects_fastest_supported_reasoning_polling() -> None:
    commission = _flat("docs/sol_skills/COMMISSION_WAVE.md")
    assert "fastest lawful/practical cadence" not in commission
    for phrase in (
        "Default Class-M interval is 60 minutes",
        "hard floor is 15 minutes",
        "15m -> 30m -> 60m",
        "watcher prompt is not a scope fence",
        "re-enter normal worker procedure",
    ):
        assert phrase in commission


def test_root_worker_bootstraps_carry_codex_continuation_invariant() -> None:
    for path in ("AGENTS.md", "CLAUDE.md"):
        text = _flat(path)
        for phrase in (
            "Reciprocal dialogue and watcher invariant",
            "watcher prompt is not a scope fence",
            "Default Class-M interval is 60 minutes",
            "hard floor is 15 minutes",
            "fresh-read the exact bound carrier",
            "Slack delivery is not target consumption",
        ):
            assert phrase in text
