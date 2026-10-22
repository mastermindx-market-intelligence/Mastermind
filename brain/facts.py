"""Typed fact records and verification rules for PBR decision materials.

Spec: ``docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md``
§2 (``pbr.fact.v1``).  A fact is a single verifiable claim lifted verbatim from
decision materials (why-now, falsifier, exit plan, rationale, memo, top-level
falsifiers), carrying its source class/family, its point-in-time stamps and —
for price kinds — its price/adjustment basis.

This module is verification and findings ONLY:

- it is shadow in this wave — nothing here is called from
  ``brain.decision_submission.normalize`` and no output vetoes a live action
  (§2.2(iii): "Shadow output only; it does not veto anything live");
- it writes nothing anywhere: records are plain dicts and every parameter comes
  from the caller-supplied config (the frozen
  ``config/pbr_shadow_risk_budget.yml``, schema
  ``pbr.shadow_risk_budget_params.v1``);
- it imports stdlib only — no sibling module, no writer, no network client.

Reference marks (seat ruling Q2, 2026-10-22): the §2.2(ii) price-basis bridge
is computed only against a **typed** ``ReferenceMark`` (schema
``pbr.reference_mark.v1``).  Only an ``ECON_UNION_MARK`` record with complete
provenance (``store_ref``, ``asof``, ``symbol``, ``mark_source`` all non-empty;
mark ``asof`` ≤ the fact's decision asof; ``symbol`` equal to the fact's)
qualifies.  A ``CALLER_SUPPLIED`` mark, an incomplete-provenance mark, or no
mark at all yields ``BASIS_UNRECONCILED`` (reason ``reference_mark_not_qualified``
/ ``reference_mark_absent``) — never VERIFIED, never "inside band".  The
spec's earlier "else the episode entry fill" fallback is REMOVED: a fill price
is not a qualifying mark.  Tests emulate the union-mark store with test doubles
marked ``store_ref="test-double"`` / ``mark_source="test-double"``.

Precedents: ``brain/decision_context.py`` for typed, unit-carrying,
authority-labelled records; the claim contract (V3 spec §13.1) for
``source_family`` semantics; MASTERPLAN §7.5 for point-in-time discipline and
primary-vs-derived discrimination.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Any, Mapping, Sequence, TypedDict

SCHEMA_VERSION = "pbr.fact.v1"

#: Closed vocabulary for ``kind``.
KINDS = ("event_date", "price_level", "price_target", "metric", "other")

#: Closed vocabulary for ``source_class`` (MASTERPLAN §7.5).
SOURCE_CLASSES = (
    "primary_filing",
    "company_release",
    "vendor_derived",
    "news_summary",
    "model_interpretation",
)

#: Source classes that count as primary evidence for rule (i).
PRIMARY_EVIDENCE_CLASSES = ("primary_filing", "company_release")

#: Schema constant for the typed reference mark (seat ruling Q2).
REFERENCE_MARK_SCHEMA = "pbr.reference_mark.v1"

#: Closed vocabulary for ``ReferenceMark.source`` (seat ruling Q2).
MARK_SOURCE_ECON_UNION_MARK = "ECON_UNION_MARK"
MARK_SOURCE_CALLER_SUPPLIED = "CALLER_SUPPLIED"
MARK_SOURCES = (MARK_SOURCE_ECON_UNION_MARK, MARK_SOURCE_CALLER_SUPPLIED)

#: Qualification statuses for a supplied reference mark.  Exactly one reason
#: code travels on every non-qualified outcome (seat ruling Q2).
MARK_QUALIFIED = "qualified"
MARK_ABSENT = "reference_mark_absent"
MARK_NOT_QUALIFIED = "reference_mark_not_qualified"


class ReferenceMark(TypedDict, total=False):
    """Typed decision-time reference mark (schema ``pbr.reference_mark.v1``).

    ``source`` says who asserted the mark: an ``ECON_UNION_MARK`` record is the
    union-mark store's decision-time price with its per-symbol provenance
    (``store_ref`` names the store record, ``mark_source`` names the feed that
    priced it); ``CALLER_SUPPLIED`` is any mark a caller asserts directly and
    never qualifies (seat ruling Q2).
    """

    schema: str
    value: float
    currency: str
    basis: dict
    symbol: str
    asof: str
    source: str
    store_ref: str
    mark_source: str


class VerificationOutcome:
    """Closed verdict vocabulary for :func:`verify_fact` (spec §2.2).

    Verdicts travel as plain strings (the ``.value`` of these constants) so
    records stay JSON-serializable; the class exists to keep the vocabulary
    closed and single-sourced.
    """

    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    UNVERIFIED = "UNVERIFIED"
    BASIS_UNRECONCILED = "BASIS_UNRECONCILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    ALL = (
        VERIFIED,
        CONTRADICTED,
        UNVERIFIED,
        BASIS_UNRECONCILED,
        NOT_APPLICABLE,
    )


#: Verdicts that make a risk-increasing action ineligible (rule iii, frozen
#: law 13 — contradiction is not averaged away).
BLOCKING_VERDICTS = (
    VerificationOutcome.CONTRADICTED,
    VerificationOutcome.BASIS_UNRECONCILED,
)

#: Actions that increase risk and are therefore conditioned by rule (iii).
RISK_INCREASING_ACTIONS = ("add", "new_entry", "increase", "size_up")

#: Risk-neutral or risk-reducing actions — rule (iv) keeps them eligible.
RISK_NEUTRAL_OR_REDUCING_ACTIONS = ("hold", "trim", "exit", "reduce", "size_down")

_KNOWN_ACTIONS = frozenset(RISK_INCREASING_ACTIONS) | frozenset(
    RISK_NEUTRAL_OR_REDUCING_ACTIONS
)

_WS_RE = re.compile(r"\s+")


class FactRecord(TypedDict, total=False):
    """One verifiable claim (schema ``pbr.fact.v1``, spec §2.1)."""

    fact_id: str
    claim_text: str
    kind: str
    instrument: dict
    value: Any
    unit: str
    currency: str
    period: str | None
    published_at: str | None
    available_at: str | None
    observed_at: str | None
    basis: dict | None
    source_class: str
    source_family: str
    source_ref: str
    decision_asof: str


class Outcome(TypedDict):
    """Result of verifying one fact: verdict + reason + compared values."""

    fact_id: str
    verdict: str
    reason: str
    compared: dict


# ─────────────────────────────── construction ───────────────────────────────


def fact_id_for(
    claim_text: str, instrument: Mapping, kind: str, source_ref: str
) -> str:
    """Stable fact id: sha256 of (claim_text, instrument, kind, source_ref), truncated.

    Truncated to 16 hex chars, matching the id-width precedent of
    ``decision.v1.<16hex>``.  Canonical JSON keeps the derivation independent
    of dict ordering and of non-ASCII escapes.
    """
    payload = json.dumps(
        {
            "claim_text": str(claim_text or ""),
            "instrument": dict(instrument or {}),
            "kind": str(kind or ""),
            "source_ref": str(source_ref or ""),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def normalize_claim_text(text: str) -> str:
    """Collapse whitespace in a verbatim claim (the text itself is untouched)."""
    return _WS_RE.sub(" ", str(text or "")).strip()


# ──────────────────────────────── reference marks ───────────────────────────


def _fact_symbol(fact: Mapping) -> str:
    instrument = fact.get("instrument") or {}
    if isinstance(instrument, Mapping):
        return str(instrument.get("symbol") or instrument.get("ticker") or "").strip()
    return ""


def _reference_mark_status(
    reference_mark: Any, fact: Mapping
) -> tuple[str, str, dict]:
    """Qualify the supplied reference mark (seat ruling Q2).

    Returns ``(status, detail, normalized_mark)``.  Only an ``ECON_UNION_MARK``
    with complete provenance — ``store_ref``, ``asof``, ``symbol`` and
    ``mark_source`` all non-empty, mark ``asof`` ≤ the fact's decision asof,
    and ``symbol`` equal to the fact's — qualifies.  Anything else (a
    ``CALLER_SUPPLIED`` mark, an incomplete mark, a bare fill price, or no
    mark) fails closed to ``reference_mark_not_qualified`` /
    ``reference_mark_absent``; the caller turns that into
    ``BASIS_UNRECONCILED`` without ever reaching the tolerance band.
    """
    if reference_mark is None:
        return (
            MARK_ABSENT,
            "no reference mark was supplied; a fill price is not a qualifying mark",
            {},
        )
    if not isinstance(reference_mark, Mapping):
        return (
            MARK_NOT_QUALIFIED,
            "reference mark is not a typed ReferenceMark mapping (a bare fill price "
            "is a caller assertion, not a store record)",
            {},
        )
    normalized: dict = dict(reference_mark)
    source = str(reference_mark.get("source") or "").strip()
    if source != MARK_SOURCE_ECON_UNION_MARK:
        return (
            MARK_NOT_QUALIFIED,
            f"reference mark source {source or '(absent)'!r} is not "
            f"{MARK_SOURCE_ECON_UNION_MARK}: caller-supplied marks never qualify",
            normalized,
        )
    if str(reference_mark.get("schema") or "") != REFERENCE_MARK_SCHEMA:
        return (
            MARK_NOT_QUALIFIED,
            f"reference mark schema must be {REFERENCE_MARK_SCHEMA}",
            normalized,
        )
    missing = [
        key
        for key in ("store_ref", "asof", "symbol", "mark_source")
        if not str(reference_mark.get(key) or "").strip()
    ]
    if missing:
        return (
            MARK_NOT_QUALIFIED,
            f"incomplete union-mark provenance, missing: {', '.join(missing)}",
            normalized,
        )
    try:
        value = float(reference_mark.get("value"))
    except (TypeError, ValueError):
        return (
            MARK_NOT_QUALIFIED,
            "reference mark value is not a usable number",
            normalized,
        )
    if not math.isfinite(value) or value <= 0.0:
        return (
            MARK_NOT_QUALIFIED,
            f"reference mark value {reference_mark.get('value')!r} is not a positive "
            "finite price",
            normalized,
        )
    asof = _parse_date(reference_mark.get("asof"))
    decision_asof = _parse_date(fact.get("decision_asof"))
    if asof is None or decision_asof is None:
        return (
            MARK_NOT_QUALIFIED,
            "reference mark asof and the fact's decision_asof must both be parseable dates",
            normalized,
        )
    if asof > decision_asof:
        return (
            MARK_NOT_QUALIFIED,
            f"mark asof {asof.isoformat()} is after the decision asof "
            f"{decision_asof.isoformat()}: not point-in-time at the decision",
            normalized,
        )
    mark_symbol = str(reference_mark.get("symbol") or "").strip()
    fact_symbol = _fact_symbol(fact)
    if not fact_symbol or mark_symbol != fact_symbol:
        return (
            MARK_NOT_QUALIFIED,
            f"mark symbol {mark_symbol!r} does not equal the fact's instrument symbol "
            f"{fact_symbol!r}",
            normalized,
        )
    normalized["value"] = value
    return MARK_QUALIFIED, "qualified union-mark record with complete provenance", normalized


# ──────────────────────────────── verification ──────────────────────────────


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _outcome(fact: Mapping, verdict: str, reason: str, compared: Mapping) -> Outcome:
    return {
        "fact_id": str(fact.get("fact_id") or ""),
        "verdict": verdict,
        "reason": reason,
        "compared": dict(compared),
    }


def _primary_records(primary_evidence: Sequence[Mapping]) -> list[dict]:
    """Normalize caller evidence records to primary records with a resolved event date.

    A record qualifies when its ``source_class`` is a primary class (or it
    carries no class but does carry a date — fixture evidence is supplied by
    the caller and is primary by construction).  The event date is
    ``event_date`` when present, else ``published_at``/``published``, else
    ``available_at``: a release's publication *is* its event when no separate
    event date is stated.
    """
    out: list[dict] = []
    for raw in primary_evidence or ():
        if not isinstance(raw, Mapping):
            continue
        source_class = str(raw.get("source_class") or "").strip()
        if source_class and source_class not in PRIMARY_EVIDENCE_CLASSES:
            continue
        event = _parse_date(
            raw.get("event_date")
            or raw.get("published_at")
            or raw.get("published")
            or raw.get("available_at")
        )
        if event is None:
            continue
        out.append(
            {
                "event_date": event,
                "source_class": source_class or PRIMARY_EVIDENCE_CLASSES[1],
                "source_ref": str(raw.get("source_ref") or raw.get("url") or ""),
            }
        )
    return out


def _band(config: Mapping) -> tuple[float, float]:
    def _value(node: Any) -> float:
        if isinstance(node, Mapping) and "value" in node:
            node = node["value"]
        return float(node)

    bridge = (config or {}).get("price_basis_bridge") or {}
    band = bridge.get("tolerance_band") or {}
    low = _value(band.get("low"))
    high = _value(band.get("high"))
    if not (0.0 < low < high):
        raise ValueError(
            "config price_basis_bridge.tolerance_band must satisfy 0 < low < high"
        )
    return low, high


def _basis_matches(fact: Mapping, mark: Mapping) -> tuple[bool, str]:
    """Currency and basis of the claim must match the reference mark's."""
    fact_basis = dict(fact.get("basis") or {})
    mark_basis = dict(mark.get("basis") or {})
    fact_ccy = str(fact.get("currency") or fact_basis.get("currency") or "").upper()
    mark_ccy = str(mark.get("currency") or mark_basis.get("currency") or "").upper()
    if fact_ccy and mark_ccy and fact_ccy != mark_ccy:
        return False, f"currency mismatch: claim {fact_ccy} vs mark {mark_ccy}"
    for key in ("adjustment", "split_assumption"):
        a = str(fact_basis.get(key) or "").strip().lower()
        b = str(mark_basis.get(key) or "").strip().lower()
        if a and b and a != b:
            return False, f"basis mismatch on {key}: claim {a!r} vs mark {b!r}"
    return True, ""


def _verify_event_date(fact: Mapping, primary: list[dict]) -> Outcome:
    """Rule (i): a dated catalyst claimed ahead of the decision must still be ahead.

    Fires on every event_date fact extracted from the entry package — the rule
    is keyed on the fact's kind and value, never on which component
    (why_now / falsifier / exit_plan / rationale / memo) carried it.  Reasons
    are stable short codes; the human-readable detail travels on ``compared``.
    """
    claimed = _parse_date(fact.get("value"))
    asof = _parse_date(fact.get("decision_asof"))
    compared = {
        "claimed_event_date": claimed.isoformat() if claimed else None,
        "decision_asof": asof.isoformat() if asof else None,
        "primary_event_dates": sorted(r["event_date"].isoformat() for r in primary),
    }

    def _reason(verdict: str, reason: str, detail: str) -> Outcome:
        compared["detail"] = detail
        return _outcome(fact, verdict, reason, compared)

    if claimed is None or asof is None:
        return _reason(
            VerificationOutcome.UNVERIFIED,
            "event_date_missing_parseable_dates",
            "event_date fact lacks a parseable claimed date or decision_asof; "
            "recorded, not discarded",
        )
    if primary:
        already = [r for r in primary if r["event_date"] <= asof]
        if already:
            return _reason(
                VerificationOutcome.CONTRADICTED,
                "catalyst_already_published_before_asof",
                (
                    "primary evidence shows the claimed catalyst was already published "
                    f"on/before the decision asof ({already[0]['event_date'].isoformat()} "
                    f"<= {asof.isoformat()}); a decision may not lean on an "
                    "already-reported catalyst as a forward gate"
                ),
            )
    if claimed > asof:
        if primary:
            return _reason(
                VerificationOutcome.VERIFIED,
                "forward_catalyst_confirmed_by_primary",
                (
                    "primary evidence dates the catalyst after the decision asof; the "
                    "forward-catalyst claim stands as of the decision"
                ),
            )
        return _reason(
            VerificationOutcome.UNVERIFIED,
            "forward_catalyst_without_primary_evidence",
            "forward-dated catalyst with no primary evidence; recorded, not discarded",
        )
    # Claim asserts an already-past date: checkable against primary evidence.
    matching = [r for r in primary if r["event_date"] == claimed]
    if matching:
        return _reason(
            VerificationOutcome.VERIFIED,
            "past_event_confirmed_by_primary",
            "primary evidence confirms the claimed past event date",
        )
    if primary:
        return _reason(
            VerificationOutcome.CONTRADICTED,
            "primary_dates_past_event_differently",
            (
                "primary evidence dates the past event differently "
                f"({primary[0]['event_date'].isoformat()} != {claimed.isoformat()})"
            ),
        )
    return _reason(
        VerificationOutcome.UNVERIFIED,
        "past_event_without_primary_evidence",
        "past-dated claim with no primary evidence; recorded, not discarded",
    )


def _has_bridge(fact: Mapping) -> bool:
    basis = fact.get("basis") or {}
    return bool(normalize_claim_text(str(basis.get("bridge") or "")))


def _verify_price_basis(fact: Mapping, reference_mark: Any, config: Mapping) -> Outcome:
    """Rule (ii) against a typed reference mark (seat ruling Q2).

    The mark must qualify first (see :func:`_reference_mark_status`); a
    ``CALLER_SUPPLIED`` mark, an incomplete mark, or no mark at all is
    ``BASIS_UNRECONCILED`` with reason ``reference_mark_not_qualified`` /
    ``reference_mark_absent`` — never VERIFIED, never "inside band".  With a
    qualified mark, ``ratio = claim_value / mark_value`` outside the declared
    tolerance band without an explicit bridge in ``fact.basis`` is
    ``BASIS_UNRECONCILED``: an unexplained scale/basis discontinuity finding —
    **not** a claim that the mark or any fill was wrong (MASTERPLAN §2.6).
    Reasons are stable short codes; the human-readable detail travels on
    ``compared``.
    """
    low, high = _band(config)
    claim_value: float | None
    try:
        claim_value = float(fact.get("value"))
    except (TypeError, ValueError):
        claim_value = None

    status, detail, mark = _reference_mark_status(reference_mark, fact)
    mark_value = mark.get("value")
    mark_value = float(mark_value) if isinstance(mark_value, (int, float)) else None
    compared: dict[str, Any] = {
        "claim_value": claim_value,
        "reference_mark_status": status,
        "reference_mark_detail": detail,
        "reference_mark_value": mark_value,
        "reference_mark_source": (
            str(mark.get("source")) if isinstance(mark, Mapping) and mark else None
        ),
        "tolerance_band": {"low": low, "high": high},
        "bridge_declared": _has_bridge(fact),
        "currency": str(fact.get("currency") or "") or None,
    }

    def _reason(verdict: str, reason: str, prose: str) -> Outcome:
        compared["detail"] = prose
        return _outcome(fact, verdict, reason, compared)

    if status != MARK_QUALIFIED:
        # Seat ruling Q2: fail closed — never VERIFIED, never "inside band".
        return _reason(
            VerificationOutcome.BASIS_UNRECONCILED,
            status,
            (
                f"{status}: {detail}. No qualified reference mark means the claim's "
                "basis cannot be reconciled, whatever its nominal size"
            ),
        )
    if claim_value is None:
        return _reason(
            VerificationOutcome.UNVERIFIED,
            "price_fact_lacks_numeric_claim_value",
            "price fact lacks a numeric claim value; recorded, not discarded",
        )
    ratio = claim_value / mark_value
    compared["ratio"] = ratio
    ok_basis, basis_reason = _basis_matches(fact, mark)
    compared["basis_reconciled"] = ok_basis
    if not ok_basis:
        return _reason(
            VerificationOutcome.BASIS_UNRECONCILED,
            "reference_mark_basis_mismatch",
            f"claim basis does not match the qualified reference mark: {basis_reason}",
        )
    if low <= ratio <= high:
        return _reason(
            VerificationOutcome.UNVERIFIED,
            "price_ratio_inside_tolerance_band",
            (
                f"ratio {ratio:.4f} inside the declared band [{low}, {high}] against a "
                "qualified reference mark: no basis discontinuity detected. Passing "
                "this screen corroborates the basis only, never the level's truth — "
                "the fact stays recorded, never discarded"
            ),
        )
    if _has_bridge(fact):
        return _reason(
            VerificationOutcome.UNVERIFIED,
            "explicit_bridge_declared",
            (
                f"ratio {ratio:.4f} outside the declared band [{low}, {high}] but the "
                "record carries an explicit currency/adjustment/split bridge"
            ),
        )
    return _reason(
        VerificationOutcome.BASIS_UNRECONCILED,
        "price_ratio_outside_tolerance_band",
        (
            f"ratio {ratio:.4f} outside the declared band [{low}, {high}] against the "
            "qualified reference mark, with no explicit bridge in fact.basis: "
            "unexplained scale/basis discontinuity (split, unit, share-class or "
            "wrong-instrument class of error). This is not a claim that any mark or "
            "fill was wrong"
        ),
    )


def verify_fact(
    fact: Mapping,
    *,
    primary_evidence: Sequence[Mapping] = (),
    reference_mark: Any = None,
    config: Mapping,
) -> Outcome:
    """Verify one fact against primary evidence / a reference mark (spec §2.2 i–ii).

    ``config`` is the parsed ``pbr.shadow_risk_budget_params.v1`` mapping (the
    tolerance band lives there per §4.3).  Facts with insufficient evidence
    resolve UNVERIFIED and are recorded, never discarded; kind ``other``
    without a check resolves NOT_APPLICABLE.
    """
    kind = str(fact.get("kind") or "").strip()
    if kind not in KINDS:
        raise ValueError(f"unknown fact kind {kind!r}; expected one of {KINDS}")
    missing = [
        key
        for key in ("fact_id", "claim_text", "instrument", "source_ref", "decision_asof")
        if not fact.get(key)
    ]
    if missing:
        raise ValueError(f"fact record missing required fields: {missing}")
    source_class = str(fact.get("source_class") or "").strip()
    if source_class not in SOURCE_CLASSES:
        raise ValueError(f"unknown source_class {source_class!r}")

    if kind in ("price_level", "price_target", "metric"):
        # Unit/carrying metadata prevents incomparable magnitudes from
        # masquerading as one scale (decision_context precedent).
        if not str(fact.get("unit") or "").strip():
            raise ValueError(f"{kind} facts require a non-null unit")
        if kind in ("price_level", "price_target"):
            if not str(fact.get("currency") or "").strip():
                raise ValueError(f"{kind} facts require a non-null currency")
            if not isinstance(fact.get("basis"), Mapping) or not fact.get("basis"):
                raise ValueError(f"{kind} facts require a basis mapping")

    if kind == "event_date":
        return _verify_event_date(fact, _primary_records(primary_evidence))
    if kind in ("price_level", "price_target"):
        return _verify_price_basis(fact, reference_mark, config)
    if kind == "metric":
        return _outcome(
            fact,
            VerificationOutcome.UNVERIFIED,
            "metric_check_out_of_scope",
            {
                "value": fact.get("value"),
                "unit": fact.get("unit"),
                "detail": (
                    "no metric verification rule in this wave (prose extraction and "
                    "metric checks are out of scope); fact recorded, not discarded"
                ),
            },
        )
    return _outcome(
        fact,
        VerificationOutcome.NOT_APPLICABLE,
        "other_kind_no_check",
        {
            "value": fact.get("value"),
            "detail": "kind 'other' carries no check in this wave; fact recorded, not discarded",
        },
    )


def verify_facts(
    facts: Sequence[Mapping],
    *,
    primary_evidence: Sequence[Mapping] = (),
    reference_mark: Any = None,
    config: Mapping,
) -> list[Outcome]:
    """Verify every fact in the entry package — no component is privileged (spec §2.2 i)."""
    return [
        verify_fact(
            fact,
            primary_evidence=primary_evidence,
            reference_mark=reference_mark,
            config=config,
        )
        for fact in facts
    ]


def summarize_outcomes(outcomes: Sequence[Outcome]) -> dict:
    """Roll up outcomes: per-verdict counts, fact ids per verdict, blocking ids."""
    by_verdict: dict[str, list[str]] = {}
    for outcome in outcomes or ():
        by_verdict.setdefault(outcome["verdict"], []).append(outcome["fact_id"])
    counts = {verdict: len(ids) for verdict, ids in by_verdict.items()}
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "by_verdict": by_verdict,
        "blocking": [fid for verdict in BLOCKING_VERDICTS for fid in by_verdict.get(verdict, [])],
    }


# ─────────────────────────── findings / eligibility ─────────────────────────


def entry_fact_findings(
    facts: Sequence[Mapping],
    outcomes: Sequence[Outcome],
    action: str,
) -> dict:
    """Risk-increase eligibility from fact outcomes (spec §2.2 iii–iv).

    An add/new-entry claim is ineligible when any supporting fact is
    CONTRADICTED or BASIS_UNRECONCILED (frozen law 13).  Missing advisory
    facts, missing provider coverage and UNVERIFIED facts never make a hold or
    an authorized risk reduction (exit/trim) ineligible: rule (iii) conditions
    only risk-increasing actions.  Shadow output only — it vetoes nothing live.
    """
    normalized = str(action or "").strip().lower()
    if normalized not in _KNOWN_ACTIONS:
        raise ValueError(
            f"unknown action {action!r}; expected one of {sorted(_KNOWN_ACTIONS)}"
        )
    outcomes = list(outcomes or ())
    if len(facts or ()) and len(outcomes) != len(facts or ()):
        raise ValueError("outcomes must be parallel to facts (one outcome per fact)")
    by_id = {str(fact.get("fact_id")): fact for fact in (facts or ())}
    blocking: list[dict] = []
    conditioned: list[dict] = []
    for outcome in outcomes:
        entry = {
            "fact_id": outcome["fact_id"],
            "verdict": outcome["verdict"],
            "kind": str(by_id.get(outcome["fact_id"], {}).get("kind") or ""),
            "claim_excerpt": normalize_claim_text(
                str(by_id.get(outcome["fact_id"], {}).get("claim_text") or "")
            )[:160],
            "reason": outcome["reason"],
        }
        if outcome["verdict"] in BLOCKING_VERDICTS:
            blocking.append(entry)
        elif outcome["verdict"] == VerificationOutcome.UNVERIFIED:
            conditioned.append(entry)

    risk_increasing = normalized in RISK_INCREASING_ACTIONS
    notes: list[str] = []
    observed_but_non_blocking: list[dict] = []
    if risk_increasing:
        eligible = not blocking
        if blocking:
            notes.append(
                "risk-increasing action conditioned by blocking fact outcomes "
                f"({', '.join(sorted({e['verdict'] for e in blocking}))})"
            )
        else:
            notes.append(
                "risk-increasing action carries no blocking fact outcome; UNVERIFIED "
                "facts are recorded but never average a contradiction away"
            )
    else:
        # Rule (iv): missing advisory facts, missing provider coverage, UNVERIFIED
        # facts — and equally CONTRADICTED/BASIS_UNRECONCILED findings, which are
        # recorded for the lineage — never make a hold or an authorized risk
        # reduction (exit/trim) ineligible.  Blocking verdicts are reported as
        # observed context here, never as a block.
        eligible = True
        observed_but_non_blocking = blocking
        notes.append(
            "advisory-coverage asymmetry: missing advisory facts, missing provider "
            "coverage and UNVERIFIED facts never make a hold or an authorized risk "
            "reduction (exit/trim) ineligible"
        )
    return {
        "action": normalized,
        "risk_increasing": risk_increasing,
        "eligible": eligible,
        "blocked_by": blocking if risk_increasing else [],
        "observed_but_non_blocking": observed_but_non_blocking,
        "conditioned_by": conditioned,
        "notes": notes,
    }
