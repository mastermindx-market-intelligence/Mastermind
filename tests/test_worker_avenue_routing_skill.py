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
