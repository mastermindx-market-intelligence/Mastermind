from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW_PATH = "docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md"
ROUTING_PATH = "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md"
PERSONAL_PRO_PATH = (
    "research/MASTERMIND_SOL_EXECUTIVE_SHELL_PRO_NATIVE_ARCHITECTURE_2026-08-20.md"
)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_chat_native_meta_ceo_law_is_canonical_and_reached_from_mandatory_routing() -> None:
    law_path = ROOT / LAW_PATH
    assert law_path.exists(), "Chat-native Meta-CEO law must exist in protected Mastermind docs"

    law = _normalized(law_path.read_text(encoding="utf-8"))
    routing = _normalized(_read(ROUTING_PATH))
    personal_pro = _normalized(_read(PERSONAL_PRO_PATH))

    assert LAW_PATH in routing
    assert "ChatGPT Personal Pro / GPT-5.6 Sol" in personal_pro
    assert "ChatGPT Pro Chat is the default Sol-class cognition surface" in routing
    assert "Personal-Pro Chat remains the primary Sol cognition plane" in law


def test_metered_sol_cognition_requires_a_complete_exception_receipt() -> None:
    law = _normalized(_read(LAW_PATH))
    routing = _normalized(_read(ROUTING_PATH))

    required = (
        "COGNITION_ROUTE: CHAT_PRO_DEFAULT",
        "COGNITION_ROUTE: METERED_EXCEPTION",
        "WHY_METERED",
        "WHY_PRO_CHAT_INSUFFICIENT",
        "EXPECTED_MAX_COST",
        "HARD_BUDGET_CAP",
        "STOP_CONDITION",
        "BUDGET_AUTHORITY",
        "METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE",
    )
    for phrase in required:
        assert phrase in law, f"missing Chat-native cognition route law: {phrase}"
        assert phrase in routing, f"mandatory routing addendum omits metered receipt: {phrase}"

    assert "Convenience is not a metered-route justification" in routing
    assert "larger advertised context window" in law


def test_meta_ceo_and_sol_hierarchy_default_to_chat_without_gaining_blanket_authority() -> None:
    law = _normalized(_read(LAW_PATH))

    required = (
        "one logical Meta-CEO office",
        "META_CEO",
        "PROGRAM_CEO",
        "PROJECT_SOL",
        "INTEGRATOR_SOL",
        "AUDITOR_SOL",
        "exactly one Sol target is action-authoritative",
        "Shared Sol cognition or naming never grants equal authority",
        "RuntimeBinding",
        "lease/fence",
    )
    for phrase in required:
        assert phrase in law, f"missing hierarchy/authority boundary: {phrase}"


def test_always_on_control_is_deterministic_and_chat_reasoning_is_event_driven() -> None:
    law = _normalized(_read(LAW_PATH))

    required = (
        "The always-on layer is deterministic",
        "Executive OS",
        "Agent OS",
        "Wake",
        "Capacity Fabric",
        "No language model must remain continuously generating",
        "wake the exact Chat responsibility only when judgment is required",
    )
    for phrase in required:
        assert phrase in law, f"missing deterministic-control law: {phrase}"


def test_scaling_uses_durable_responsibilities_not_hundreds_of_generating_tabs() -> None:
    law = _normalized(_read(LAW_PATH))

    required = (
        "Scale by durable responsibilities, not continuously generating tabs",
        "multiplexing",
        "parking",
        "session recycling",
        "bounded fanout",
        "backpressure",
        "hundreds of recoverable responsibilities",
    )
    for phrase in required:
        assert phrase in law, f"missing portfolio scaling law: {phrase}"


def test_business_agents_work_and_api_are_companions_or_metered_exceptions() -> None:
    law = _normalized(_read(LAW_PATH))
    routing = _normalized(_read(ROUTING_PATH))

    required_law = (
        "Business and plugin work remains valuable as an optional companion connection layer",
        "Workspace Agents",
        "ChatGPT Work",
        "API inference is default-off for Sol-class cognition",
        "must not replace Personal-Pro Chat as the default Sol cognition plane",
    )
    for phrase in required_law:
        assert phrase in law, f"missing paid-surface boundary: {phrase}"

    assert "Workspace-Agent-front-end plus API-Meta-CEO default stack is REJECTED_BY_DESIGN" in routing
    assert "Business / plugins / MCP remain optional companion surfaces" in routing


def test_existing_mastermind_owners_remain_canonical() -> None:
    law = _normalized(_read(LAW_PATH))

    required = (
        "This law creates no new canonical owner",
        "Job / Attempt / Worker / Event lifecycle",
        "durable responsibility / decision / discovery / handoff",
        "current exact reasoning surface",
        "attention, delivery, ACK, and source resolution",
        "implementation and immutable evidence",
        "Forbidden replacements include a Meta-CEO database",
        "API supervisor lifecycle",
        "browser-tab election service",
        "transcript memory store",
    )
    for phrase in required:
        assert phrase in law, f"missing no-duplicate-owner boundary: {phrase}"
