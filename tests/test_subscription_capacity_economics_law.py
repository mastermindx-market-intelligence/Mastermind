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


def test_capacity_law_preserves_provider_native_depletion_identity_after_hard_gates() -> None:
    law = _text(LAW)
    for phrase in (
        "Hard eligibility gates come before economics",
        "Capacity follows provider-native depletion identity",
        "entitlement × native resource/window × scope × depletion/debit function × headroom × reset/expiry × concurrency/health",
        "Expiring-capacity harvest rule",
        "Scarcity-preservation rule",
        "accepted useful capability per marginal dollar and per scarce capacity unit",
        "No amount of expiring quota makes an ineligible route eligible",
    ):
        assert phrase in law


def test_capacity_law_never_splits_shared_quota_into_fictional_model_wallets() -> None:
    law = _text(LAW)
    for phrase in (
        "do not split that shared resource into fictional per-model wallets",
        "bind to the SAME canonical resource identity",
        "Switching models does not refill shared capacity",
        "Public plan tables and model-equivalent marketing rows",
        "mark the disputed dimension UNKNOWN",
        "SHARED_VS_MODEL_SCOPED_SEMANTICS",
    ):
        assert phrase in law


def test_capacity_law_forbids_quota_burn_theater_and_limit_circumvention() -> None:
    law = _text(LAW)
    for phrase in (
        '"burn quota at all costs" rule',
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
    assert "shared aggregator window" in law
    assert "observed accepted-work demand" in law


def test_dated_application_corrects_opencode_shared_window_semantics() -> None:
    memo = _text(MEMO)
    for phrase in (
        "ONE `rolling`, ONE `weekly`, and ONE `monthly`",
        "shared account/workspace five-hour + weekly + monthly native resources",
        "MUST NOT become dozens of fictional independent wallets",
        "changing models does not refill account usage",
        'scope="account_shared"',
        "bind all Go model options to the SAME shared native window identities",
    ):
        assert phrase in memo
    assert "many separate model buckets" not in memo
    assert "preserve each model/window bucket" not in memo


def test_dated_application_does_not_claim_provider_activation_or_purchase_authority() -> None:
    memo = _text(MEMO)
    for phrase in (
        "does not arm a provider",
        "do not add more accounts to increase pooled capacity",
        "do not buy more MiniMax capacity until the existing plan is actually admitted and utilized",
        "resume that SAME carrier when lawful",
        "Never create per-model balance rows from the public table alone",
        "subscription scale-up decision: hold purchases",
    ):
        assert phrase in memo
