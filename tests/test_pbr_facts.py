"""PBR L-S5 — typed fact records + verification rules (spec §5.1, seat rulings Q1/Q2/SR-1).

Baseline tests pass on master and document the gap (normalize() carries no
fact/thesis/budget audit).  Contract tests import the new module inside the
test body, so on code without ``brain/facts.py`` they FAIL with
ModuleNotFoundError — no importorskip, no xfail, no try/except.

SR-1 discipline: fixtures are redacted; every narrative string is a
``pbr.prose_digest.v1`` object.  Strings fed to string-typed seams are
rehydrated into the rule-(1) placeholder; claim values that live only inside
prose are declared typed facts whose provenance is the digest's fixture path
(rule (3)).  No original PM prose appears in this file.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "pbr" / "decision_cases"
CONFIG = ROOT / "config" / "pbr_shadow_risk_budget.yml"

MU_ENTRY = "mu_2026-10-02_entry.json"
XOM_CONTROL = "xom_2026-08-12_positive_control.json"
CN_SIZING = "cn_688062_2026-08-12_sizing.json"
PLANLESS = "mu_2026-10-22_planless_summary.json"

MU_DECISION_ASOF = "2026-10-02"
XOM_DECISION_ASOF = "2026-08-12"

AUDIT_KEYS_BASELINE = {
    "carried",
    "blocked_early_exits",
    "blocked_exits",
    "blocked_actions",
    "invalid_exit_requests",
    "ignored_exit_requests",
    "rejected",
    "quarantined",
    "mandatory_instrument_migrations",
    "identity",
    "unallocated_adds",
    "quote_fallback_holdings",
    "sizing",
}

# SR-1 rule (3): declared claims — typed values that live only inside redacted
# prose.  ``digest_path`` is the fixture path of the pbr.prose_digest.v1 object
# the value was declared from; ``tokens`` are the literal spellings the
# env-gated occurrence check asserts against the original string.  The
# 688062.SS probability is typed 0.62; its original states it as "62%".
DECLARED_CLAIMS = (
    {"case": "mu_2026-10-02_entry", "line": 75, "digest_path": "case_holding.why_now", "kind": "event_date", "value": "2026-10-22", "tokens": ("10/22",)},
    {"case": "mu_2026-10-02_entry", "line": 75, "digest_path": "case_holding.exit_plan", "kind": "event_date", "value": "2026-10-22", "tokens": ("10/22",)},
    {"case": "mu_2026-10-02_entry", "line": 75, "digest_path": "case_holding.exit_plan", "kind": "price_level", "value": 107.5, "tokens": ("107.5",)},
    {"case": "mu_2026-10-02_entry", "line": 75, "digest_path": "case_holding.rationale", "kind": "price_target", "value": 130.0, "tokens": ("130",)},
    {"case": "mu_2026-10-02_entry", "line": 75, "digest_path": "case_holding.rationale", "kind": "price_target", "value": 140.0, "tokens": ("140",)},
    {"case": "mu_2026-10-02_entry", "line": 75, "digest_path": "case_holding.falsifier", "kind": "metric", "value": 35.5, "tokens": ("35.5",)},
    {"case": "xom_2026-08-12_positive_control", "line": 38, "digest_path": "case_holding.falsifier", "kind": "price_level", "value": 153.0, "tokens": ("153",)},
    {"case": "xom_2026-08-12_positive_control", "line": 38, "digest_path": "case_holding.falsifier", "kind": "price_level", "value": 137.5, "tokens": ("137.50",)},
    {"case": "cn_688062_2026-08-12_sizing", "line": 35, "digest_path": "case_holding.rationale", "kind": "metric", "value": 0.62, "tokens": ("62%",)},
)


# ─────────────────────────────── helpers ────────────────────────────────────


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _record_by_line(fix: dict, line: int) -> dict:
    for record in fix["records"]:
        if record["line_index_0based"] == line:
            return record
    raise AssertionError(f"line {line} not among records")


def _is_digest(value) -> bool:
    return isinstance(value, dict) and value.get("redacted") == "pbr.prose_digest.v1"


def _placeholder(digest: dict) -> str:
    """SR-1 rule (1): deterministic placeholder for one redacted prose string."""
    return (
        "<redacted sha256={sha} len={n} dates={dates} periods={periods} terms={terms}>".format(
            sha=digest["sha256"][:12],
            n=digest["length"],
            dates=",".join(digest.get("iso_dates") or []) or "none",
            periods=",".join(digest.get("period_labels") or []) or "none",
            terms=",".join(digest.get("terms") or []) or "none",
        )
    )


def _rehydrate(node):
    """Rule (1): replace every digest in a fixture fragment by its placeholder."""
    if _is_digest(node):
        return _placeholder(node)
    if isinstance(node, dict):
        return {key: _rehydrate(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_rehydrate(value) for value in node]
    return node


def _scan(node, needles):
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found |= _scan(key, needles)
            found |= _scan(value, needles)
    elif isinstance(node, (list, tuple)):
        for value in node:
            found |= _scan(value, needles)
    elif isinstance(node, str):
        for needle in needles:
            if needle in node:
                found.add(needle)
    return found


def _resolve_digest(fix: dict, line: int, path: str) -> dict:
    node = _record_by_line(fix, line)
    for part in path.split("."):
        node = node[part]
    if not _is_digest(node):
        raise AssertionError(f"{path} at line {line} is not a prose digest")
    return node


def _econ_union_mark_double(value: float, symbol: str, asof: str, currency: str = "USD") -> dict:
    """Test double for the ECON union-mark store (seat ruling Q2).

    ``store_ref`` and ``mark_source`` are pinned to "test-double"; the VALUE is
    the cited fixture fill price; ``asof`` is pinned to the decision asof so
    the double satisfies the ruling's point-in-time qualification (mark asof ≤
    the fact's decision asof) — the live wave pins the canonical mark at
    decision time, which is exactly what ruling Q2 requires.
    """
    import brain.facts as facts

    return {
        "schema": facts.REFERENCE_MARK_SCHEMA,
        "value": value,
        "currency": currency,
        "basis": {"adjustment": "unadjusted_close", "split_assumption": "current_shares"},
        "symbol": symbol,
        "asof": asof,
        "source": facts.MARK_SOURCE_ECON_UNION_MARK,
        "store_ref": "test-double",
        "mark_source": "test-double",
    }


def _instrument_of(fix: dict, record: dict) -> dict:
    holding = record.get("case_holding") or {}
    return {
        "ticker": fix["ticker"],
        "book": fix["provenance"][0]["source_book"],
        "venue": holding.get("venue"),
        "identity_status": holding.get("identity_status"),
    }


def _fact(fix, record, digest, *, kind, value, source_ref, unit=None, currency=None, basis=None, period=None):
    import brain.facts as facts

    instrument = _instrument_of(fix, record)
    return {
        "fact_id": facts.fact_id_for(_placeholder(digest), instrument, kind, source_ref),
        "claim_text": _placeholder(digest),
        "kind": kind,
        "instrument": instrument,
        "value": value,
        "unit": unit,
        "currency": currency,
        "period": period
        if period is not None
        else ((digest.get("period_labels") or [None])[0]),
        "published_at": None,
        "available_at": None,
        "observed_at": None,
        "basis": basis,
        "source_class": "model_interpretation",
        "source_family": "decision_package",
        "source_ref": source_ref,
        "decision_asof": record["row"]["asof"],
    }


PRICE_BASIS = {"adjustment": "unadjusted_close", "split_assumption": "current_shares"}


def _prior_book(fix: dict, line: int, extra_rows=()) -> dict:
    """Prior book from the fixture row: holdings minus the case ticker, at recorded weights."""
    prior = {}
    for other in fix["redaction"]["other_holdings"]:
        if other["line_index_0based"] == line:
            prior[other["ticker"]] = {
                "ticker": other["ticker"],
                "weight": float(other["weight"]),
                "conviction": other["conviction"],
            }
    for row in extra_rows:
        prior[row["ticker"]] = row
    return prior


def _run_normalize(monkeypatch, fix, record, prior, *, extra_args=None, holdings=None):
    """Baseline normalize() with only READ seams patched (each listed in RETURN).

    Seams: ``brain.decision_submission._latest_holdings`` (live account reader),
    ``brain.decision_submission._instrument_identity_for_book`` (identity
    classifier), ``portfolio.registry.requires_single_name_equity`` (mandate
    lookup).  No write path is patched: normalize() writes nothing.
    """
    from brain import decision_submission
    from portfolio import registry

    holding = record.get("case_holding") or {}
    row = record["row"]

    def _fake_latest_holdings(book):
        return copy.deepcopy(prior)

    def _fake_identity(book, ticker):
        status = holding.get("identity_status") or "trusted_company_profile.v1"
        return {"kind": "common_stock", "status": status, "verified": True, "market": book}

    monkeypatch.setattr(decision_submission, "_latest_holdings", _fake_latest_holdings)
    monkeypatch.setattr(decision_submission, "_instrument_identity_for_book", _fake_identity)
    monkeypatch.setattr(registry, "requires_single_name_equity", lambda book: True)

    if holdings is None:
        holdings = (
            [{**_rehydrate(holding), "action": holding["action_requested"]}] if holding else []
        )
    args = {"holdings": holdings, "risk_posture": row.get("risk_posture")}
    if extra_args:
        args.update(extra_args)
    book = fix["provenance"][0]["source_book"]
    return decision_submission.normalize(
        book, args, deterministic_sizing=True, decision_asof=row.get("asof")
    )


def _mu_catalyst_components(fix):
    """One event_date fact per entry-package component (spec §2.2(i) — no privileged field).

    Dates per SR-1 rule (2) from the digest's recorded iso_dates where the
    digest carries them (falsifier, memo timing); declared under rule (3) for
    the why_now and exit_plan digests, whose originals give the catalyst date
    only as the month/day token (fixture DECISION_CASES.md records no
    iso_dates for them).
    """
    record = _record_by_line(fix, 75)
    components = []
    for name, path in (
        ("why_now", "case_holding.why_now"),
        ("case_holding.falsifier", "case_holding.falsifier"),
        ("case_holding.exit_plan", "case_holding.exit_plan"),
        ("decision_memo.timing", "row.decision_memo.timing"),
    ):
        digest = _resolve_digest(fix, 75, path)
        if name == "why_now":
            value = "2026-10-22"  # SR-1 rule (3) declared date; token "10/22"
        elif name == "case_holding.exit_plan":
            value = "2026-10-22"  # SR-1 rule (3) declared date; token "10/22"
        else:
            assert digest["iso_dates"] == ["2026-10-22"], (name, digest["iso_dates"])
            value = digest["iso_dates"][0]  # SR-1 rule (2)
        components.append(
            (
                name,
                _fact(
                    fix,
                    record,
                    digest,
                    kind="event_date",
                    value=value,
                    source_ref=f"records@75.{path}",
                    # SR-1 rule (3) declared identity: the claimed catalyst is
                    # the fiscal Q4 2026 results release. The why_now/exit_plan
                    # digests carry no period label and the falsifier digest
                    # records another form, so one canonical label is declared.
                    period="FY2026-Q4",
                ),
            )
        )
    return record, components


# ───────────────────────────── baseline (master) ─────────────────────────────


def test_baseline_master_normalize_accepts_entry_adds_without_findings(monkeypatch):
    from brain import decision_submission  # existing module; imported for clarity

    for name, line, expected_cap in (
        (MU_ENTRY, 75, 0.10),
        (CN_SIZING, 35, 0.12),
    ):
        fix = _load(name)
        record = _record_by_line(fix, line)
        holding = record["case_holding"]
        assert holding["action_requested"] == "add"
        assert holding["conviction"] == "medium"
        payload, audit = _run_normalize(monkeypatch, fix, record, _prior_book(fix, line))
        held = [h for h in payload["holdings"] if h["ticker"] == fix["ticker"]]
        assert len(held) == 1, name
        assert held[0]["action_effective"] == "add"
        assert held[0]["weight"] == expected_cap, (
            f"{name}: add-row weight must equal the categorical conviction cap"
        )
        assert held[0]["weight_source"] == holding["weight_source"]
        assert audit["unallocated_adds"] == []
        assert audit["rejected"] == []
        # The audit vocabulary on master has no fact/thesis/budget sections.
        assert set(audit) == AUDIT_KEYS_BASELINE
        assert not ({"fact_verification", "thesis_continuity", "risk_budget"} & set(audit))
        assert (
            _scan(
                payload,
                [
                    "CONTRADICTED",
                    "BASIS_UNRECONCILED",
                    "UNRECORDED_AMENDMENT",
                    "fact_verification",
                    "thesis_continuity",
                    "risk_budget",
                ],
            )
            == set()
        )
    assert decision_submission is not None


def test_baseline_master_normalize_accepts_exit_without_thesis_finding(monkeypatch):
    fix = _load(PLANLESS)
    row89 = _record_by_line(fix, 89)
    row78 = _record_by_line(fix, 78)
    assert row89["case_holding"] is None
    prior = _prior_book(
        fix,
        89,
        extra_rows=[
            {
                "ticker": fix["ticker"],
                "weight": float(row78["case_holding"]["weight"]),
                "conviction": row78["case_holding"]["conviction"],
            }
        ],
    )
    exits = _rehydrate(row89["row"]["requested_exit_decisions"])
    assert exits and exits[0]["ticker"] == fix["ticker"]
    payload, audit = _run_normalize(
        monkeypatch, fix, row89, prior, extra_args={"exit_decisions": exits}, holdings=[]
    )
    accepted = [e for e in payload["exit_decisions"] if e["ticker"] == fix["ticker"]]
    assert len(accepted) == 1
    assert accepted[0]["reason_code"] == "risk_limit"
    assert payload["requested_exit_decisions"] == accepted
    assert audit["ignored_exit_requests"] == []
    assert audit["invalid_exit_requests"] == []
    assert set(audit) == AUDIT_KEYS_BASELINE
    assert (
        _scan(
            payload,
            [
                "PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT",
                "UNRECORDED_AMENDMENT",
                "thesis_continuity",
                "thesis_id",
                "risk_budget",
            ],
        )
        == set()
    )


# ────────────────────────────── contract tests ───────────────────────────────


def test_mu_entry_catalyst_contradicted_in_every_component():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(MU_ENTRY)
    record, components = _mu_catalyst_components(fix)
    assert record["row"]["asof"] == MU_DECISION_ASOF
    external = [
        # SR-1 rule (3) declared identity: the fixture external facts concern
        # the fiscal Q4 2026 results release dated 2026-09-30 (the same event
        # as the claimed catalyst); the fixture carries no period label on them.
        {**fact_item, "source_class": "company_release", "period": "FY2026-Q4"}
        for fact_item in fix["external_facts"]
        if fact_item.get("event_date")
    ]
    assert external and all(item["event_date"] == "2026-09-30" for item in external)
    seen_ids = set()
    for name, fact in components:
        outcome = facts.verify_fact(fact, primary_evidence=external, config=cfg)
        assert outcome["verdict"] == facts.VerificationOutcome.CONTRADICTED, name
        assert outcome["compared"]["claimed_event_date"] == "2026-10-22"
        assert outcome["compared"]["decision_asof"] == MU_DECISION_ASOF
        assert "2026-09-30" in outcome["compared"]["primary_event_dates"]
        assert fact["fact_id"] not in seen_ids, "each component fact is distinct"
        seen_ids.add(fact["fact_id"])


def test_mu_perturbation_event_after_asof_not_contradicted():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(MU_ENTRY)
    record, components = _mu_catalyst_components(fix)
    _, fact = components[0]
    perturbed = [
        # Same declared identity as the claim (SR-1 rule (3)): the fiscal Q4
        # 2026 results release, perturbed to after the decision asof.
        {"event_date": "2026-10-30", "source_class": "company_release", "period": "FY2026-Q4"}
    ]
    outcome = facts.verify_fact(fact, primary_evidence=perturbed, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.VERIFIED
    assert outcome["verdict"] != facts.VerificationOutcome.CONTRADICTED
    assert outcome["compared"]["primary_event_dates"] == ["2026-10-30"]


def _probe_event_fact(claimed, asof, *, period="FY2026-Q4", event=None):
    """Hand-built event_date probe fact (typed test data; no PM prose)."""
    import brain.facts as facts

    instrument = {"ticker": "PROBE", "book": "test", "venue": None, "identity_status": None}
    claim = f"declared probe claim: event dated {claimed} for period {period}"
    return {
        "fact_id": facts.fact_id_for(
            claim, instrument, "event_date", f"probe:{claimed}:{asof}:{period}:{event}"
        ),
        "claim_text": claim,
        "kind": "event_date",
        "instrument": instrument,
        "value": claimed,
        "unit": None,
        "currency": None,
        "period": period,
        "event": event,
        "published_at": None,
        "available_at": None,
        "observed_at": None,
        "basis": None,
        "source_class": "model_interpretation",
        "source_family": "decision_package",
        "source_ref": "probe",
        "decision_asof": asof,
    }


def _probe_record(event_date, period=None, *, source_class="company_release", event=None):
    """Hand-built primary-evidence probe record (typed test data)."""
    record = {"event_date": event_date, "source_class": source_class}
    if period is not None:
        record["period"] = period
    if event is not None:
        record["event"] = event
    return record


def test_event_date_unrelated_period_never_contradicts():
    """R-1750 F1: an unrelated past release of a different period never
    contradicts a correct forward claim — only a SAME-event record can."""
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fact = _probe_event_fact("2026-10-22", "2026-10-02", period="FY2026-Q4")
    evidence = [_probe_record("2026-08-26", "FY2026-Q3")]
    outcome = facts.verify_fact(fact, primary_evidence=evidence, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.UNVERIFIED
    assert outcome["verdict"] != facts.VerificationOutcome.CONTRADICTED
    assert outcome["reason"] == "no_identity_matched_primary_record"
    compared = outcome["compared"]
    assert compared["claimed_period"] == "FY2026-Q4"
    assert compared["matched_record_count"] == 0
    assert compared["other_identity_record_count"] == 1
    assert compared["primary_event_dates"] == []


def test_event_date_unrelated_past_record_does_not_mask_matching_forward_record():
    """R-1750 F1: an unrelated past release must not mask a same-event record
    that confirms the forward catalyst."""
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fact = _probe_event_fact("2026-10-22", "2026-10-02", period="FY2026-Q4")
    evidence = [
        _probe_record("2026-08-26", "FY2026-Q3"),
        _probe_record("2026-10-22", "FY2026-Q4"),
    ]
    outcome = facts.verify_fact(fact, primary_evidence=evidence, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.VERIFIED
    assert outcome["reason"] == "forward_catalyst_confirmed_by_primary"
    compared = outcome["compared"]
    assert compared["primary_event_dates"] == ["2026-10-22"]
    assert compared["matched_record_count"] == 1
    assert compared["other_identity_record_count"] == 1


def test_event_date_requires_identity_and_primary_class():
    """R-1750 F1: identity and primary class gate every date comparison."""
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fact = _probe_event_fact("2026-10-22", "2026-10-02", period="FY2026-Q4")

    # (a) A dated record without a period identity is unidentified: it never
    # matches, so it can neither contradict nor confirm.
    outcome = facts.verify_fact(
        fact, primary_evidence=[_probe_record("2026-09-30", None)], config=cfg
    )
    assert outcome["verdict"] == facts.VerificationOutcome.UNVERIFIED
    assert outcome["reason"] == "no_identity_matched_primary_record"
    assert outcome["compared"]["unidentified_record_count"] == 1

    # (b) A same-period record without a source_class is not primary evidence:
    # it is excluded and counted, and never contradicts.
    outcome = facts.verify_fact(
        fact,
        primary_evidence=[{"event_date": "2026-09-30", "period": "FY2026-Q4"}],
        config=cfg,
    )
    assert outcome["verdict"] != facts.VerificationOutcome.CONTRADICTED
    assert outcome["compared"]["excluded_non_primary_record_count"] == 1
    assert outcome["compared"]["matched_record_count"] == 0

    # (c) A fact with no period identity of its own is recorded unverified.
    fact_no_period = _probe_event_fact("2026-10-22", "2026-10-02", period=None)
    outcome = facts.verify_fact(
        fact_no_period,
        primary_evidence=[_probe_record("2026-09-30", "FY2026-Q4")],
        config=cfg,
    )
    assert outcome["verdict"] == facts.VerificationOutcome.UNVERIFIED
    assert outcome["reason"] == "event_identity_absent"

    # (d) A conflicting short event label on both sides breaks identity too.
    labelled = _probe_event_fact(
        "2026-10-22", "2026-10-02", period="FY2026-Q4", event="earnings_release"
    )
    outcome = facts.verify_fact(
        labelled,
        primary_evidence=[
            _probe_record("2026-09-30", "FY2026-Q4", event="guidance_update")
        ],
        config=cfg,
    )
    assert outcome["verdict"] != facts.VerificationOutcome.CONTRADICTED
    assert outcome["reason"] == "no_identity_matched_primary_record"


def test_event_date_past_claim_checked_only_against_same_identity():
    """R-1750 F1 item 3b: the <=-asof contradiction applies to FORWARD claims
    only; a past claim is confirmed by its own event, contradicted only by a
    SAME-event record dating it differently."""
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    asof = "2026-10-02"

    # (a) A same-period record dating the past event differently contradicts.
    fact = _probe_event_fact("2026-09-15", asof, period="FY2026-Q4")
    outcome = facts.verify_fact(
        fact, primary_evidence=[_probe_record("2026-09-30", "FY2026-Q4")], config=cfg
    )
    assert outcome["verdict"] == facts.VerificationOutcome.CONTRADICTED
    assert outcome["reason"] == "primary_dates_past_event_differently"

    # (b) A different-period record never contradicts a past claim either.
    outcome = facts.verify_fact(
        fact, primary_evidence=[_probe_record("2026-08-26", "FY2026-Q3")], config=cfg
    )
    assert outcome["verdict"] == facts.VerificationOutcome.UNVERIFIED
    assert outcome["reason"] == "no_identity_matched_primary_record"

    # (c) A past claim confirmed by its own same-event record: a correct past
    # claim is not "already published before asof".
    fact = _probe_event_fact("2026-09-30", asof, period="FY2026-Q4")
    outcome = facts.verify_fact(
        fact, primary_evidence=[_probe_record("2026-09-30", "FY2026-Q4")], config=cfg
    )
    assert outcome["verdict"] == facts.VerificationOutcome.VERIFIED
    assert outcome["reason"] == "past_event_confirmed_by_primary"


def test_mu_price_claims_basis_unreconciled():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(MU_ENTRY)
    record = _record_by_line(fix, 75)
    # Reference mark: the qualified ECON union-mark test double at the cited
    # fixture fill value 1069.68 (ruling Q2 — a fill price is only a mark when
    # it arrives as a typed ECON_UNION_MARK record with provenance).
    mark = _econ_union_mark_double(1069.68, fix["ticker"], MU_DECISION_ASOF)
    expected = {
        "case_holding.rationale:130": 130.0,
        "case_holding.rationale:140": 140.0,
        "case_holding.exit_plan:107.5": 107.5,
    }
    digest_by_path = {
        "case_holding.rationale": _resolve_digest(fix, 75, "case_holding.rationale"),
        "case_holding.exit_plan": _resolve_digest(fix, 75, "case_holding.exit_plan"),
    }
    for source_ref, value in expected.items():
        path = source_ref.split(":")[0]
        fact = _fact(
            fix,
            record,
            digest_by_path[path],
            kind="price_target" if "rationale" in path else "price_level",
            value=value,
            source_ref=f"records@75.{source_ref}",
            unit="price_per_share",
            currency="USD",
            basis=dict(PRICE_BASIS, currency="USD"),
        )
        outcome = facts.verify_fact(fact, reference_mark=mark, config=cfg)
        assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED, source_ref
        assert outcome["reason"] == "price_ratio_outside_tolerance_band"
        assert outcome["compared"]["ratio"] == pytest.approx(value / 1069.68)
        assert outcome["compared"]["reference_mark_status"] == facts.MARK_QUALIFIED
        band = outcome["compared"]["tolerance_band"]
        assert not (band["low"] <= outcome["compared"]["ratio"] <= band["high"])
        assert outcome["compared"]["bridge_declared"] is False


def test_xom_price_levels_reconciled_positive_control():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(XOM_CONTROL)
    record = _record_by_line(fix, 38)
    assert record["row"]["asof"] == XOM_DECISION_ASOF
    mark = _econ_union_mark_double(158.03, fix["ticker"], XOM_DECISION_ASOF)
    digest = _resolve_digest(fix, 38, "case_holding.falsifier")
    outcomes = []
    for value in (153.0, 137.5):  # SR-1 rule (3) declared levels; tokens "153" / "137.50"
        fact = _fact(
            fix,
            record,
            digest,
            kind="price_level",
            value=value,
            source_ref=f"records@38.case_holding.falsifier:{value}",
            unit="price_per_share",
            currency="USD",
            basis=dict(PRICE_BASIS, currency="USD"),
        )
        outcome = facts.verify_fact(fact, reference_mark=mark, config=cfg)
        assert outcome["verdict"] != facts.VerificationOutcome.BASIS_UNRECONCILED
        assert outcome["verdict"] == facts.VerificationOutcome.UNVERIFIED
        assert outcome["reason"] == "price_ratio_inside_tolerance_band"
        band = outcome["compared"]["tolerance_band"]
        assert band["low"] <= outcome["compared"]["ratio"] <= band["high"]
        outcomes.append((fact, outcome))
    # Every XOM fact eligible for the add.
    findings = facts.entry_fact_findings(
        [fact for fact, _ in outcomes], [outcome for _, outcome in outcomes], "add"
    )
    assert findings["eligible"] is True
    assert findings["blocked_by"] == []


def test_risk_increase_ineligible_when_any_supporting_fact_bad():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(MU_ENTRY)
    record, components = _mu_catalyst_components(fix)
    mark = _econ_union_mark_double(1069.68, fix["ticker"], MU_DECISION_ASOF)
    external = [
        # SR-1 rule (3) declared identity: the fixture external facts concern
        # the fiscal Q4 2026 results release dated 2026-09-30 (the same event
        # as the claimed catalyst); the fixture carries no period label on them.
        {**item, "source_class": "company_release", "period": "FY2026-Q4"}
        for item in fix["external_facts"]
        if item.get("event_date")
    ]
    facts_list = [fact for _, fact in components]
    outcomes = [
        facts.verify_fact(fact, primary_evidence=external, config=cfg) for fact in facts_list
    ]
    rationale = _resolve_digest(fix, 75, "case_holding.rationale")
    exit_plan = _resolve_digest(fix, 75, "case_holding.exit_plan")
    for digest, kind, value in (
        (rationale, "price_target", 130.0),  # SR-1 rule (3); token "130"
        (rationale, "price_target", 140.0),  # SR-1 rule (3); token "140"
        (exit_plan, "price_level", 107.5),  # SR-1 rule (3); token "107.5"
    ):
        fact = _fact(
            fix,
            record,
            digest,
            kind=kind,
            value=value,
            source_ref=f"records@75.declared:{value}",
            unit="price_per_share",
            currency="USD",
            basis=dict(PRICE_BASIS, currency="USD"),
        )
        facts_list.append(fact)
        outcomes.append(facts.verify_fact(fact, reference_mark=mark, config=cfg))

    rollup = facts.summarize_outcomes(outcomes)
    assert rollup["counts"].get(facts.VerificationOutcome.CONTRADICTED) == 4
    assert rollup["counts"].get(facts.VerificationOutcome.BASIS_UNRECONCILED) == 3

    findings = facts.entry_fact_findings(facts_list, outcomes, "add")
    assert findings["eligible"] is False
    assert findings["risk_increasing"] is True
    verdicts = {entry["verdict"] for entry in findings["blocked_by"]}
    assert verdicts == {
        facts.VerificationOutcome.CONTRADICTED,
        facts.VerificationOutcome.BASIS_UNRECONCILED,
    }
    assert {entry["kind"] for entry in findings["blocked_by"]} >= {"event_date", "price_level", "price_target"}


def test_missing_advisory_coverage_never_blocks_hold_or_risk_reduction():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(MU_ENTRY)
    record = _record_by_line(fix, 75)
    falsifier = _resolve_digest(fix, 75, "case_holding.falsifier")
    # No primary evidence supplied (provider/advisory coverage absent): the
    # gross-margin metric claim and the undated forward claim both resolve
    # UNVERIFIED and are recorded — never discarded.
    metric = _fact(
        fix,
        record,
        falsifier,
        kind="metric",
        value=35.5,  # SR-1 rule (3) declared; token "35.5"
        source_ref="records@75.case_holding.falsifier:metric",
        unit="gross_margin_percent",
        period=falsifier["period_labels"][0],
    )
    undated = _fact(
        fix,
        record,
        falsifier,
        kind="event_date",
        value="2026-10-22",
        source_ref="records@75.case_holding.falsifier:no-evidence",
    )
    facts_list = [metric, undated]
    outcomes = [
        facts.verify_fact(metric, primary_evidence=(), config=cfg),
        facts.verify_fact(undated, primary_evidence=(), config=cfg),
    ]
    assert [o["verdict"] for o in outcomes] == [
        facts.VerificationOutcome.UNVERIFIED,
        facts.VerificationOutcome.UNVERIFIED,
    ]
    for action in ("hold", "exit", "trim"):
        findings = facts.entry_fact_findings(facts_list, outcomes, action)
        assert findings["eligible"] is True, action
        assert findings["risk_increasing"] is False
        assert findings["blocked_by"] == []
    # Only the risk-increasing action is conditioned at all.
    add = facts.entry_fact_findings(facts_list, outcomes, "add")
    assert add["risk_increasing"] is True
    assert add["eligible"] is True
    assert add["blocked_by"] == []
    assert len(add["conditioned_by"]) == len(outcomes)
    # And a blocking verdict still never blocks an authorized risk reduction.
    contradicted = dict(outcomes[1], verdict=facts.VerificationOutcome.CONTRADICTED)
    exit_findings = facts.entry_fact_findings(facts_list, [outcomes[0], contradicted], "exit")
    assert exit_findings["eligible"] is True
    assert exit_findings["blocked_by"] == []
    assert len(exit_findings["observed_but_non_blocking"]) == 1


def test_caller_supplied_reference_mark_never_qualifies():
    import brain.facts as facts
    import brain.shadow_risk_budget as shadow_risk_budget

    cfg = shadow_risk_budget.load_params(CONFIG)
    fix = _load(XOM_CONTROL)
    record = _record_by_line(fix, 38)
    digest = _resolve_digest(fix, 38, "case_holding.falsifier")

    def _level_fact(value):
        return _fact(
            fix,
            record,
            digest,
            kind="price_level",
            value=value,
            source_ref=f"records@38.case_holding.falsifier:{value}",
            unit="price_per_share",
            currency="USD",
            basis=dict(PRICE_BASIS, currency="USD"),
        )

    # The SAME value as the in-band mark, supplied by the caller → never qualifies.
    caller_mark = {
        "schema": facts.REFERENCE_MARK_SCHEMA,
        "value": 158.03,
        "currency": "USD",
        "basis": dict(PRICE_BASIS),
        "symbol": fix["ticker"],
        "asof": XOM_DECISION_ASOF,
        "source": facts.MARK_SOURCE_CALLER_SUPPLIED,
    }
    for fact in (_level_fact(153.0), _level_fact(137.5)):
        outcome = facts.verify_fact(fact, reference_mark=caller_mark, config=cfg)
        assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED
        assert outcome["reason"] == "reference_mark_not_qualified"
        assert outcome["compared"]["reference_mark_status"] == facts.MARK_NOT_QUALIFIED
        assert "ratio" not in outcome["compared"]

    # No mark at all.
    outcome = facts.verify_fact(_level_fact(153.0), reference_mark=None, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED
    assert outcome["reason"] == "reference_mark_absent"

    # An ECON double whose asof is after the decision asof is not qualified.
    late_mark = _econ_union_mark_double(158.03, fix["ticker"], "2026-08-17")
    outcome = facts.verify_fact(_level_fact(153.0), reference_mark=late_mark, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED
    assert outcome["reason"] == "reference_mark_not_qualified"
    assert "not point-in-time" in outcome["compared"]["reference_mark_detail"]

    # The removed fill fallback: a bare fill price is not a qualifying mark.
    outcome = facts.verify_fact(_level_fact(153.0), reference_mark=158.03, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED
    assert outcome["reason"] == "reference_mark_not_qualified"

    # An ECON double with incomplete provenance is not qualified either.
    incomplete = _econ_union_mark_double(158.03, fix["ticker"], XOM_DECISION_ASOF)
    incomplete.pop("mark_source")
    outcome = facts.verify_fact(_level_fact(153.0), reference_mark=incomplete, config=cfg)
    assert outcome["verdict"] == facts.VerificationOutcome.BASIS_UNRECONCILED
    assert outcome["reason"] == "reference_mark_not_qualified"
    assert "mark_source" in outcome["compared"]["reference_mark_detail"]


def test_declared_values_occur_in_original_prose():
    """ENV-GATED (SR-1 rule 3): every declared claim value occurs in the original
    string whose sha256 matches the cited digest; declared dates are checked via
    their month/day token.  Skips with an SR-1 reason when
    ``PBR_DECISION_CASE_INPUT_DIR`` is unset or its files are absent."""
    input_dir = Path(os.environ.get("PBR_DECISION_CASE_INPUT_DIR", "/nonexistent/pbr-decision-case-inputs"))
    inputs = (input_dir / "case_rows.jsonl", input_dir / "case_fills.jsonl")
    if not all(path.exists() for path in inputs):
        pytest.skip(
            f"SR-1: original capture extracts not present at {input_dir} "
            "(set PBR_DECISION_CASE_INPUT_DIR); production prose stays outside the repository"
        )

    def _leaves(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from _leaves(value)
        elif isinstance(node, list):
            for value in node:
                yield from _leaves(value)
        elif isinstance(node, str):
            yield node

    originals = {}
    for path in inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for leaf in _leaves(json.loads(line)["row"]):
                if any(ch.isspace() for ch in leaf):
                    originals[hashlib.sha256(leaf.encode("utf-8")).hexdigest()] = leaf

    checked = 0
    for claim in DECLARED_CLAIMS:
        fix = _load(f"{claim['case']}.json")
        digest = _resolve_digest(fix, claim["line"], claim["digest_path"])
        text = originals.get(digest["sha256"])
        assert text is not None, (
            f"{claim['case']} {claim['digest_path']}: digest matches no original string"
        )
        assert digest["length"] == len(text)
        for token in claim["tokens"]:
            assert token in text, (
                f"{claim['case']} {claim['digest_path']}: declared token {token!r} "
                "does not occur in the matched original"
            )
            checked += 1
    assert checked == sum(len(claim["tokens"]) for claim in DECLARED_CLAIMS)
