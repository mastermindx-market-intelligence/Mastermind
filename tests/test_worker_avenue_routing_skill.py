from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_worker_avenue_routing_is_canonical_and_chairman_binds_accounts() -> None:
    skill_path = ROOT / "docs/sol_skills/WORKER_AVENUE_ROUTING.md"
    assert skill_path.exists(), "manual worker avenue routing law must be a canonical Sol skill"

    skill = skill_path.read_text(encoding="utf-8")
    index = _read("docs/sol_skills/INDEX.md")
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")

    assert "WORKER_AVENUE_ROUTING.md" in index
    assert "PREFERRED_AVENUE" in kernel
    assert "Concrete account allocation remains Chairman-owned" in kernel

    for avenue in ("Fable", "Opus", "Grok", "CTO Sol", "Terra"):
        assert f"PREFERRED_AVENUE: {avenue}" in skill

    required_skill_phrases = (
        "The Chairman chooses the concrete account/session",
        "ACCOUNT_BINDING: CHAIRMAN_SELECTS",
        "RECEIVER_MODE: OPEN_PICKUP",
        "Prefer **Terra**",
        "Prefer **CTO Sol**",
        "Fable is for the hardest principal-level problems, not the default.",
        "Automated Executive routing is separate",
    )
    for phrase in required_skill_phrases:
        assert phrase in skill, f"missing worker avenue routing law: {phrase}"

    assert "PREFERRED_AVENUE: Luna" not in skill
    assert "PREFERRED_AVENUE: Sonnet" not in skill


def test_capacity_selectable_prestart_rebind_is_distinct_from_exact_session_continuation() -> None:
    skill = _read("docs/sol_skills/WORKER_AVENUE_ROUTING.md")
    commission = _read("docs/sol_skills/COMMISSION_WAVE.md")
    index = _read("docs/sol_skills/INDEX.md")
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")

    required_skill_phrases = (
        "RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE",
        "RECEIVER_BINDING_MODE: EXACT_SESSION_REQUIRED",
        "PRESTART_REBIND",
        "Before `START`, the Chairman may replace the concrete account/session",
        "newest explicit live Chairman assignment",
        "same operation key and carrier",
        "After `START`, the selected concrete runtime binding is sticky",
        "A numbered-account mismatch is not a blocker",
        "exact provider conversation/session is part of the target",
    )
    for phrase in required_skill_phrases:
        assert phrase in skill, f"missing pre-START receiver rebinding law: {phrase}"

    assert "RECEIVER_BINDING_MODE" in commission
    assert "PRESTART_REBIND" in commission
    assert "capacity-selectable" in index.lower()
    assert "capacity-selectable" in kernel.lower()
    assert "exact-session-required" in kernel.lower()
