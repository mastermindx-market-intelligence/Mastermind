from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs" / "EXECUTIVE_SUBSCRIPTION_CAPACITY_ECONOMICS_LAW.md"
MEMO = ROOT / "research" / "SUBSCRIPTION_CAPACITY_OPENCODE_MINIMAX_2026-09-15.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_capacity_law_preserves_existing_authority_and_no_duplicate_control_plane() -> None:
    law = _text(LAW)
    for phrase in (
        "Model Router",
        "Shared AI Provider Control",
        "Executive OS",
        "RuntimeBinding / carrier law",
        "No new router, quota ledger, retry engine, lifecycle, account registry, or cost database",
        "A missing or stale fact stays unknown",
    ):
        assert phrase in law


def test_capacity_law_ranks_model_specific_expiring_inventory_after_hard_gates() -> None:
    law = _text(LAW)
    for phrase in (
        "Hard eligibility gates come before economics",
        "Capacity is model-specific inventory, not an account percentage",
        "entitlement × model × allocation/window × headroom × reset/expiry × concurrency/health",
        "Expiring-capacity harvest rule",
        "Scarcity-preservation rule",
        "accepted useful capability per marginal dollar and per scarce capacity unit",
        "No amount of expiring quota makes an ineligible route eligible",
    ):
        assert phrase in law


def test_capacity_law_forbids_quota_burn_theater_and_limit_circumvention() -> None:
    law = _text(LAW)
    for phrase in (
        'not a "burn quota at all costs" rule',
        "Do not manufacture low-value work",
        "Never create, maintain, pool, or rotate accounts to circumvent usage limits",
        "Do not scale a subscription because its advertised theoretical token or API-dollar allowance looks large",
        "Continuity beats micro-optimization after START",
        "EFFECT_UNKNOWN",
    ):
        assert phrase in law


def test_capacity_law_distinguishes_direct_workhorse_and_aggregator_breadth() -> None:
    law = _text(LAW)
    assert "Aggregator subscription:" in law
    assert "Direct subscription:" in law
    assert "large direct subscription" in law
    assert "aggregator bucket" in law
    assert "observed accepted-work demand" in law


def test_dated_application_does_not_claim_provider_activation_or_purchase_authority() -> None:
    memo = _text(MEMO)
    for phrase in (
        "does not arm a provider",
        "do not add more accounts to increase pooled capacity",
        "do not buy more MiniMax capacity until the existing plan is actually admitted and utilized",
        "repair/resume the existing #665 lane rather than rebuild",
        "do not average model buckets into account utilization",
        "subscription scale-up decision: hold purchases",
    ):
        assert phrase in memo
