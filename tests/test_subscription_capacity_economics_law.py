import re
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


def test_capacity_law_pins_vector_ordering_and_provider_preference_role() -> None:
    law = _text(LAW)
    for phrase in (
        "Ranking MUST preserve a **Pareto/lexicographic** decision boundary",
        "strictly dominated",
        "documented lexicographic ordering",
        "MUST NOT override a stronger stage",
        "Static provider preference is a deterministic tie-break only",
        "ORDERING_STAGE / DOMINANCE_REASON",
    ):
        assert phrase in law


def test_changing_external_numbers_are_not_routing_authority_without_receipts() -> None:
    memo = _text(MEMO)
    assert "This is current research only, **not routing authority**." in memo
    assert (
        "No consumer may size capacity, choose a route, authorize a purchase, or satisfy `capacity_known` "
        "from this memo."
    ) in memo
    assert memo.count("UNVERIFIED_FOR_ROUTING") >= 4
    for phrase in (
        "MUST NOT size capacity, choose a route, authorize a purchase",
        "does **not** establish current Go utilization or `capacity_known`",
        "changing MiniMax allowances, concurrency counts, subscription prices",
        "UTC observation time",
        "receipt/snapshot digest",
    ):
        assert phrase in memo


_DECISION_BEARING = re.compile(
    r"\b(?:route|routing|size|sizing|allocate|allocation|rank|ranks|ranking|headroom|capacity_known)\b",
    re.IGNORECASE,
)
_VOLATILE_QUANTITATIVE = re.compile(
    r"(?:\$\s*\d|\b\d+(?:\.\d+)?\s*(?:%|[KMBT]\b|tokens?\b|agents?\b|lanes?\b|concurrent\b))",
    re.IGNORECASE,
)
_ROUTING_AUTHORITY_MARKERS = (
    "UNVERIFIED_FOR_ROUTING",
    "fresh Provider Control",
    "receipt/snapshot digest",
    "immutable source commit",
)


def _unreceipted_decision_quantitative_claims(text: str) -> list[str]:
    violations: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            if not _DECISION_BEARING.search(sentence):
                continue
            if not _VOLATILE_QUANTITATIVE.search(sentence):
                continue
            if any(marker in sentence for marker in _ROUTING_AUTHORITY_MARKERS):
                continue
            violations.append(sentence)
    return violations


def test_dated_application_routes_direct_minimax_only_from_fresh_provider_control() -> None:
    memo = _text(MEMO)
    assert (
        "If a fresh Provider Control observation shows the direct MiniMax pool eligible with headroom, "
        "test routine M3-family demand against that direct pool first under the ordering law; absent "
        "that observation the pool ranks from UNKNOWN."
    ) in memo
    assert "while a large legitimate direct MiniMax pool is idle and eligible" not in memo


def test_dated_application_rejects_unreceipted_quantitative_routing_claims() -> None:
    memo = _text(MEMO)
    assert _unreceipted_decision_quantitative_claims(memo) == []

    violating_mutant = memo + """

The MiniMax Ultra Token Plan provides 12.5B M3 tokens per month and 7 concurrent agents at $1,188/year. Size the M3 cohort at 6 concurrent lanes and route all routine M3 demand to the direct plan on that basis; this establishes current headroom for allocation.
"""
    assert _unreceipted_decision_quantitative_claims(violating_mutant)


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
