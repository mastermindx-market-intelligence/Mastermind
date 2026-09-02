from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAW = ROOT / "docs" / "EXECUTIVE_WEB_SOL_USAGE_CAPACITY_LAW.md"
DESIGN = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-09-02-web-sol-pro-usage-observability-design.md"
)
PLAN = (
    ROOT
    / "docs"
    / "superpowers"
    / "plans"
    / "2026-09-02-web-sol-pro-usage-observability.md"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_usage_capacity_source_law_files_exist_and_are_records_only():
    law = _read(LAW)
    design = _read(DESIGN)
    plan = _read(PLAN)

    assert "web-sol-pro-usage-observability-20260902-sol-001" in law
    assert "RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT" in law
    assert "SPEC_ONLY / PRODUCTION_INERT" in design
    assert "SPEC_ONLY / PRODUCTION_INERT" in plan


def test_macro_provider_control_remains_canonical_capacity_owner():
    text = (_read(LAW) + "\n" + _read(DESIGN)).lower()

    assert "macro shared ai provider control" in text
    assert "canonical provider/account-slot availability" in text
    assert "web-sol senses; macro owns quota truth" in text
    assert "there is no web-sol quota database" in text
    assert "surface_bindings remains navigation-only" in text


def test_provider_capacity_v1_is_not_patched_in_place():
    law = _read(LAW).lower()
    design = _read(DESIGN).lower()
    plan = _read(PLAN).lower()

    assert "must **not patch that v1 contract in place**" in law
    assert "does not patch v1 in place" in design
    assert "current `mastermind.provider_capacity.v1` is unchanged" in plan
    assert "versioned provider control contract evolution" in plan


def test_observed_provider_and_estimated_usage_remain_distinct():
    law = _read(LAW).lower()
    design = _read(DESIGN).lower()

    for phrase in (
        "mastermind-observed reasoning activity",
        "provider-reported quota/reset evidence",
        "estimated runway",
        "unknown is not zero, full, unlimited, available, or exhausted",
    ):
        assert phrase in law

    assert "own activity, provider quota and forecast are separate objects" in design
    assert "scope": "mastermind_observed_only"  # source-law vocabulary sentinel


def test_no_universal_reset_or_fixed_turn_assumption():
    text = _read(LAW).lower()

    for phrase in (
        "chatgpt pro resets weekly",
        "chatgpt pro resets monthly",
        "billing renewal == quota reset",
        "20x == a fixed number of pro turns",
        "one pro turn == one fixed quota unit",
    ):
        assert phrase in text

    assert "crossing `t` does **not** automatically assert `remaining = 100%`" in text


def test_private_authenticated_quota_extraction_is_rejected():
    text = (_read(LAW) + "\n" + _read(DESIGN)).lower()

    for phrase in (
        "undocumented/private chatgpt backend endpoints",
        "browser cookies or session tokens",
        "copied oauth/access/refresh tokens",
        "network interception",
        "local/session storage extraction",
        "normal openai api key as a proxy for chatgpt subscription allowance",
    ):
        assert phrase in text

    assert "private-endpoint/cookie quota scraping | `rejected_by_design`" in text


def test_generic_provider_error_cannot_be_relabelled_usage_limit():
    law = _read(LAW).lower()
    design = _read(DESIGN).lower()

    assert "provider error exists but cannot be classified as a usage-limit signal" in law
    assert "a generic error boolean does not equal `usage_limit_observed`" in design


def test_local_pro_counter_requires_known_mode_and_exact_submission():
    law = _read(LAW).lower()
    design = _read(DESIGN).lower()

    assert "a pro-specific local counter increments only when both are proven" in law
    assert "the reasoning/model class for that submission is known" in law
    assert "unknown reasoning mode" in design
    assert "service-worker restart after receipt" in design
    assert "same event id, no second count" in design


def test_effect_unknown_accounting_never_causes_provider_retry():
    text = (_read(LAW) + "\n" + _read(DESIGN) + "\n" + _read(PLAN)).lower()

    assert "accounting uncertainty must never cause an extra provider request" in text
    assert "do not increment confirmed count and do not resend" in text
    assert "effect-unknown send -> no blind repeat" in text


def test_context_rotation_and_quota_exhaustion_are_orthogonal():
    law = _read(LAW).lower()
    design = _read(DESIGN).lower()

    assert "context exhaustion and account quota exhaustion are orthogonal" in law
    assert "context rotation is not quota failover" in law
    assert "context succession is not quota failover" in design


def test_no_automatic_cross_account_quota_failover_authority():
    law = _read(LAW).lower()
    design = _read(DESIGN).lower()
    plan = _read(PLAN).lower()

    assert "automatic cross-account quota failover | `rejected_by_design`" in law
    assert "switch the chairman's account/profile automatically" in design
    assert "no automatic placement is required by q-d1" in plan
    assert "planning integration requires its own current-policy review" in plan


def test_q2_waits_for_current_web_sol_reliability_and_installation_gates():
    plan = _read(PLAN).lower()

    assert "t1 pr #308" in plan
    assert "install1 has produced an accepted disposable installed generation" in plan
    assert "no active pr owns the same extension/native-host paths" in plan


def test_qf0_precedes_automated_provider_quota_collection():
    plan = _read(PLAN).lower()

    assert "wsx-qf0" in plan
    assert "no private endpoint calls" in plan
    assert "return to sol before any automated quota acquisition implementation" in plan
    assert "run **wsx-qf0**, not extension implementation" in plan
