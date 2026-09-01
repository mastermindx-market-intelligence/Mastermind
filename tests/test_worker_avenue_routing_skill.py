from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_worker_avenue_routing_is_canonical_and_routes_by_avenue() -> None:
    skill_path = ROOT / "docs/sol_skills/WORKER_AVENUE_ROUTING.md"
    assert skill_path.exists(), "worker avenue routing law must be a canonical Sol skill"

    skill = skill_path.read_text(encoding="utf-8")
    index = _read("docs/sol_skills/INDEX.md")
    kernel = _read("docs/sol_skills/BOOTSTRAP_KERNEL.md")

    assert "WORKER_AVENUE_ROUTING.md" in index
    assert "PREFERRED_AVENUE" in kernel
    for avenue in ("Fable", "Opus", "Grok", "CTO Sol", "Terra"):
        assert f"PREFERRED_AVENUE: {avenue}" in skill

    required = (
        "Routine concrete placement is not Chairman labor",
        "WAITING_CAPACITY / needs_placement",
        "explicit manual exception only",
        "Fable is for the hardest",
        "principal-level problems, not the default",
        "Automated Executive routing is separate",
    )
    normalized = _normalized(skill)
    for phrase in required:
        assert phrase in normalized, f"missing worker avenue routing law: {phrase}"


def test_routine_capacity_selectable_work_does_not_create_chairman_gated_precommission() -> None:
    skill = _normalized(_read("docs/sol_skills/WORKER_AVENUE_ROUTING.md"))
    index = _normalized(_read("docs/sol_skills/INDEX.md"))
    kernel = _normalized(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))

    for text in (skill, index, kernel):
        assert "WAITING_CAPACITY / needs_placement" in text

    required_skill = (
        "turn that placement debt into a worker-facing `PRECOMMISSION`, `OPEN_PICKUP`, or `ACCOUNT_BINDING: CHAIRMAN_SELECTS`",
        "ask the Chairman to choose a numbered Claude/Codex account/session",
        "`PRECOMMISSION` is not a canonical worker lifecycle state or required ceremony",
        "do not emit a worker-facing Slack commission merely to advertise the job",
        "`ACCOUNT_BINDING: CHAIRMAN_SELECTS` remains an **explicit manual exception only**",
    )
    for phrase in required_skill:
        assert phrase in skill, f"missing no-precommission rule: {phrase}"

    assert "do not emit a worker-facing PRECOMMISSION" in kernel
    assert "Routine worker placement is not Chairman labor" in index


def test_capacity_selectable_direct_delivery_binds_without_second_ceremony() -> None:
    skill = _normalized(_read("docs/sol_skills/WORKER_AVENUE_ROUTING.md"))
    commission = _normalized(_read("docs/sol_skills/COMMISSION_WAVE.md"))
    index = _normalized(_read("docs/sol_skills/INDEX.md"))
    kernel = _normalized(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))

    required_skill = (
        "that delivery is the receiver-assignment edge",
        "a second Chairman assignment",
        "a separate Slack claim/comment",
        "mutation of an earlier packet",
    )
    for phrase in required_skill:
        assert phrase in skill, f"missing direct-delivery binding rule: {phrase}"

    assert "that live delivery is the receiver assignment" in commission
    assert "must not require a separate Slack comment" in commission
    assert "that delivery is the receiver-assignment edge" in index
    assert "that delivery is the receiver-assignment edge" in kernel


def test_manual_chairman_selection_remains_explicit_exception_and_exact_session_is_strict() -> None:
    skill = _normalized(_read("docs/sol_skills/WORKER_AVENUE_ROUTING.md"))

    required = (
        "ACCOUNT_BINDING: CHAIRMAN_SELECTS",
        "RECEIVER_MODE: OPEN_PICKUP",
        "RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE",
        "RECEIVER_BINDING_MODE: EXACT_SESSION_REQUIRED",
        "current live Chairman explicitly opts into manual account/session allocation for this exact operation",
        "selected concrete runtime binding is sticky",
        "`EFFECT_UNKNOWN` always blocks a receiver change",
    )
    for phrase in required:
        assert phrase in skill, f"missing manual-exception/exact-session law: {phrase}"


def test_current_detailed_routing_law_is_preserved_while_placement_owner_changes() -> None:
    skill = _normalized(_read("docs/sol_skills/WORKER_AVENUE_ROUTING.md"))

    for phrase in (
        "Codex-capacity preference",
        "WHY NOT FABLE",
        "WHY FABLE",
        "PRESTART_REBIND",
        "Exact-receiver and live-target rules",
        "Automated Executive routing is separate",
        "Terra",
        "CTO Sol",
        "Fable",
    ):
        assert phrase in skill, f"current routing detail was accidentally dropped: {phrase}"


def test_placement_law_applies_to_every_project_seat() -> None:
    skill = _normalized(_read("docs/sol_skills/WORKER_AVENUE_ROUTING.md"))
    index = _normalized(_read("docs/sol_skills/INDEX.md"))
    kernel = _normalized(_read("docs/sol_skills/BOOTSTRAP_KERNEL.md"))

    assert "Account-neutral enforcement" in skill
    assert "No ChatGPT, Codex, Claude, Fable, Grok or another surface is exempt" in kernel
    assert "No ChatGPT, Codex, Claude, Fable, Grok or another surface" in index
