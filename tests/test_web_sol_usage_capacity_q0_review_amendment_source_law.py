from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-09-02-web-sol-q0-adversarial-review-amendment.md"
)


def _text() -> str:
    return AMENDMENT.read_text(encoding="utf-8").lower()


def test_review_amendment_is_same_records_only_operation():
    text = _text()

    assert "web-sol-pro-usage-observability-20260902-sol-001" in text
    assert "records_only / spec_only / production_inert" in text
    assert "current protected mastermind review pin" in text


def test_quota_observability_cannot_smuggle_send_authority():
    text = _text()

    assert "inspect" in text and "foreground" in text
    assert "the current extension has no `send`" in text
    assert "wsx-q1/wsx-q2 may not add send/type/model-selection authority" in text
    assert "quota observability cannot create that capability as a side effect" in text
    assert "passive/bounded observation only" in text


def test_local_count_scope_and_coverage_are_explicit():
    text = _text()

    for phrase in (
        "governed_mastermind_actions_only",
        "this_managed_browser_realm_only",
        "provider_account_total",
        "complete_for_governed_scope",
        "best_effort_partial",
        "gap_detected",
    ):
        assert phrase in text

    assert "provider_account_total` requires provider-supported evidence" in text
    assert "recorded/observed submissions" in text
    assert "provider quota units consumed" in text


def test_unknown_or_lost_local_telemetry_never_retries_provider_activity():
    text = _text()

    assert "provider activity is never retried to recover a missing telemetry event" in text
    assert "the aggregate becomes incomplete" in text
    assert "undercount/coverage degradation" in text


def test_reasoning_mode_is_not_inferred_from_behavior_or_generic_generation_state():
    text = _text()

    assert "passive local submit can be attributed to `sol_pro` only" in text
    assert "do not read arbitrary rendered text" in text
    assert "response latency" in text
    assert "infer `sol_pro` from generic generation active state -> reject/unknown" in text


def test_identity_and_entitlement_generations_are_separate():
    text = _text()

    assert "`realm_generation` alone cannot safely invalidate" in text
    assert "entitlement_generation" in text
    assert "resource_generation" in text
    assert "personal pro $100 -> $200" in text
    assert "business standard <-> premium" in text
    assert "generation mismatch makes them stale/invalid" in text


def test_shared_pool_topology_is_mandatory_for_cap_web_f0():
    text = _text()

    assert "capacityrealmslot" in text
    assert "capacityresourcepool" in text
    assert "capacityresourcelink" in text
    assert "shared resource state is canonical once" in text
    assert "shared-resource deduplication across multiple realm slots" in text
    assert "shared-pool amendment is a required member" in text


def test_current_public_source_findings_do_not_become_timeless_quota_truth():
    text = _text()

    assert "current public-source pre-census (not qf0 completion)" in text
    assert "no documented personal-pro api" in text
    assert "workspace credit usage is therefore not total chat activity" in text
    assert "a configured usage limit is not automatically live model headroom" in text
    assert "time-sensitive public-source findings" in text
    assert "qf0 must revalidate" in text


def test_current_v1_and_spend_authority_remain_separate():
    text = _text()

    assert "mastermind.provider_capacity.v1" in text
    assert "leaves `mastermind.provider_capacity.v1` semantics unchanged" in text
    assert "separate spend/budget authority from capacity availability" in text
    assert "shared credits available as spend-authorized -> reject" in text


def test_review_does_not_claim_release_or_live_capability():
    text = _text()

    assert "source architecture remains **spec_only**" in text
    assert "does **not** satisfy the independent-review gate" in text
    assert "green hosted ci on exact head" in text
    assert "only then source protection/release ruling" in text
