"""GLT T17 identification receipts and the separately labelled causal estimate.

Synthetic fixtures only; no real observation is read.  Named acceptance cases:

* C20 - a residual, threshold crossing or orthogonalised series never implies
  exogeneity (``test_c20_*``);
* C23 - confounder, mediator and collider choices match the estimand card, and
  anticipation, pre-trend and reverse response are tested (``test_c23_*``);
* C30 - weak or invalid identification yields NOT_IDENTIFIED (``test_c30_*``).

Fixture windows: every announcement event carries three pre-announcement
windows (anticipation: the 5 sessions ending the session before; pre-trend: the
20 sessions before that; reaction lookback: the 25 sessions ending the session
before).  Each window's synthetic return is drawn independently, so the
reaction-lookback return is deliberately NOT the sum of the other two; each
test perturbs exactly one window.  Clean windows use noise made exactly
orthogonal to the instrument, so the clean fixture's falsifier slopes are 0.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import math
from dataclasses import dataclass, fields, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from statistics import NormalDist
from types import SimpleNamespace

import numpy as np
import pytest

from brain.liquidity_lab.contracts import TARGET_BY_ID, ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation, ResponseCurveCell
from brain.liquidity_lab.eventization import label_shock
from brain.liquidity_lab.identification import (
    ANTICIPATION_WINDOW,
    CAUSAL_EVIDENCE_TIER,
    CAUSAL_LABEL,
    EVENT_KEY,
    IDENTIFIED_FOR_CONTEXT,
    PRE_TREND_WINDOW,
    REACTION_WINDOW,
    WINDOW_KEY,
    CalendarEvent,
    CausalEstimateCard,
    IdentificationReceipt,
    IdentificationRequired,
    InstrumentObservation,
    build_identification_card,
    causal_response,
    identification_definition_hash,
    load_identification_card,
    qualify_identification,
    validate_identification_card,
    validate_specification,
)
from brain.liquidity_lab.ledger import ForwardLedger
from brain.liquidity_lab.preregistration import load_card
from brain.liquidity_lab.response_evidence import (
    IdentificationReceiptMissing,
    ResponseEvidenceProjection,
    coverage_record,
    project_cell,
)
from brain.liquidity_lab.response_path import ResponsePathSpec
from brain.liquidity_lab.validation import StatisticalDependencyUnavailable
from brain.liquidity_lab.window_guard import ReservedWindowTouched, WindowGuard

REPO = Path(__file__).resolve().parents[1]
RLT = REPO / "research/liquidity_transmission"
ID_CARD_PATH = RLT / "glt_identification_card.v1.json"
ESTIMAND_PATH = RLT / "glt_estimand_card.v1.json"
PREREG_PATH = RLT / "glt_preregistration_card.v1.json"
MODULE_PATH = REPO / "brain/liquidity_lab/identification.py"

FROZEN_DEFINITION_HASH = "a55f05e1e0e389e548840dc1c70da93278d9f935d4dbb623a8cb9895f5aaa81b"
FROZEN = json.loads(ID_CARD_PATH.read_text(encoding="utf-8"))
ESTIMAND = json.loads(ESTIMAND_PATH.read_text(encoding="utf-8"))
EST_BYTES = ESTIMAND_PATH.read_bytes()
PRE_BYTES = PREREG_PATH.read_bytes()
CONFOUNDERS = [item["id"] for item in ESTIMAND["confounders"]]

UTC = timezone.utc
AS_OF = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
FIRST_EVENT = date(2008, 3, 3)
INSTR = "fixture_policy_surprise"
PURGED = "fomc_policy_surprise_information_purged"
CANDIDATE = {
    "instrument_id": INSTR,
    "source_ref": {"repo": "synthetic", "path": "tests/test_liquidity_lab_identification.py", "sha": "0" * 40},
    "rights_state": "RIGHTS_PROVEN",
    "clock_rule": "first_system_known",
    "announcement_type": PURGED,
}
BETA = 0.01
HAC_MESSAGE = (
    "UNTESTED:first_stage_relevance:StatisticalDependencyUnavailable: "
    "engine.validation.newey_west_tstat is required for T17 identification tests"
)


# ------------------------------------------------------------------ judges
def _nw(values, lags=4):
    """Deterministic Newey-West (Bartlett) mean test with the Macro judge's return shape."""

    x = np.asarray(values, dtype=float)
    n = len(x)
    mean = float(x.mean())
    u = x - mean
    lrv = float(u @ u) / n
    for lag in range(1, min(lags, n - 1) + 1):
        lrv += 2.0 * (1.0 - lag / (lags + 1.0)) * float(u[lag:] @ u[:-lag]) / n
    se = math.sqrt(max(lrv, 0.0) / n)
    if se == 0.0:
        return {"mean": mean, "se": None, "t": None, "p": None, "n": n}
    t = mean / se
    return {"mean": mean, "se": se, "t": t, "p": 2.0 * (1.0 - NormalDist().cdf(abs(t))), "n": n}


def _bh(pvals, alpha=0.10):
    """Benjamini-Hochberg step-up with the Macro judge's return shape {key: {p, q, reject}}."""

    keys = sorted(pvals, key=lambda key: pvals[key])
    m = len(keys)
    out, running = {}, 1.0
    for rank in range(m, 0, -1):
        key = keys[rank - 1]
        running = min(running, pvals[key] * m / rank)
        out[key] = {"p": pvals[key], "q": running, "reject": running <= alpha}
    return out


# ----------------------------------------------------------------- fixtures
def _card(doc):
    doc = copy.deepcopy(doc)
    doc["definition_hash"] = identification_definition_hash(doc)
    return build_identification_card(doc, estimand_bytes=EST_BYTES, preregistration_bytes=PRE_BYTES)


def _fixture_doc(**candidate_over):
    doc = copy.deepcopy(FROZEN)
    doc["instrument_candidates"] = [{**copy.deepcopy(CANDIDATE), **candidate_over}]
    return doc


def _fixture_card(**candidate_over):
    return _card(_fixture_doc(**candidate_over))


def _guard():
    return WindowGuard.from_card(load_card(PREREG_PATH))


def _bday(day, n):
    return np.busday_offset(day.isoformat(), n, roll="forward").astype(date)


def _orth(rng, z, sd):
    """Mean-zero noise exactly orthogonal to the centred instrument."""

    zc = z - z.mean()
    e = rng.normal(0.0, sd, len(z))
    e = e - e.mean()
    return e - zc * float(e @ zc) / float(zc @ zc)


def _row(shock_id, anchor, exit_, horizon, value, conditions):
    return ForwardReturnObservation(
        shock_id=shock_id,
        first_detected=datetime.combine(anchor, time(21, 0)),
        target_id="spy",
        asset_class=TARGET_BY_ID["spy"].asset_class,
        hierarchy_parent=TARGET_BY_ID["spy"].hierarchy_parent,
        shock_family="glt_policy_surprise_fixture",
        shock_type="instrument_surprise",
        horizon_bdays=int(horizon),
        anchor_session=anchor,
        exit_session=exit_,
        forward_return=float(value),
        conditions=conditions,
    )


@dataclass
class World:
    sessions: list
    panel: list
    calendar: list
    frame: list
    outcomes: list
    pool: list


def _world(
    *,
    n=40,
    seed=7,
    gamma=0.8,
    anticipation=0.0,
    pre_trend=0.0,
    reverse=0.0,
    late=(),
    announcement_type=PURGED,
):
    rng = np.random.default_rng(seed)
    sessions = [_bday(FIRST_EVENT, 40 * i) for i in range(n)]
    z = rng.normal(0.0, 1.0, n)
    d = gamma * z + _orth(rng, z, 0.3)
    panel = [
        InstrumentObservation(
            instrument_id=INSTR,
            event_id=f"ev{i:02d}",
            session=s,
            known_at=datetime.combine(s, time(18, 15), tzinfo=UTC) + (timedelta(days=3) if i in late else timedelta(0)),
            surprise=float(z[i]),
            treatment=float(d[i]),
            announcement_type=announcement_type,
        )
        for i, s in enumerate(sessions)
    ]
    frame = []
    for name, start, end, slope in (
        (ANTICIPATION_WINDOW, -6, -1, anticipation),
        (PRE_TREND_WINDOW, -26, -6, pre_trend),
        (REACTION_WINDOW, -26, -1, reverse),
    ):
        y = slope * z + _orth(rng, z, 0.006)
        for i, s in enumerate(sessions):
            frame.append(
                _row(
                    f"ev{i:02d}:{name}", _bday(s, start), _bday(s, end), end - start, y[i],
                    {EVENT_KEY: f"ev{i:02d}", WINDOW_KEY: name},
                )
            )
    controls = {name: rng.normal(0.0, 1.0, n) for name in CONFOUNDERS}
    outcomes = []
    for h in (5, 20):
        y = BETA * math.sqrt(h / 20) * d + rng.normal(0.0, 0.004, n)
        for i, s in enumerate(sessions):
            conditions = {EVENT_KEY: f"ev{i:02d}", **{c: float(controls[c][i]) for c in CONFOUNDERS}}
            outcomes.append(_row(f"ev{i:02d}", s, _bday(s, h), h, y[i], conditions))
    pool = []
    for h in (5, 20):
        for i, s in enumerate(sessions):
            for offset in (15, 25):
                anchor = _bday(s, offset)
                pool.append(_row(f"pl{i:02d}_{offset}", anchor, _bday(anchor, h), h, rng.normal(0.0, 0.004), {}))
    calendar = [
        CalendarEvent("ev05", "central_bank_information_release", sessions[5]),
        CalendarEvent("cpi_far", "scheduled_cpi_or_payrolls_release", _bday(sessions[3], 10)),
    ]
    return World(sessions, panel, calendar, frame, outcomes, pool)


def _qualify(world, card=None, **over):
    kwargs = dict(
        instrument_panel=world.panel,
        event_calendar=world.calendar,
        outcome_frame=world.frame,
        guard=_guard(),
        as_of=AS_OF,
        mean_test_fn=_nw,
    )
    kwargs.update(over)
    return qualify_identification(card if card is not None else _fixture_card(), **kwargs)


def _spec(spec_id="rf_no_controls"):
    for spec in FROZEN["admissible_specifications"]:
        if spec["spec_id"] == spec_id:
            return copy.deepcopy(spec)
    raise KeyError(spec_id)


def _estimate(world, receipt, card=None, spec=None, guard=None, **over):
    kwargs = dict(
        horizons=(5, 20),
        guard=guard or _guard(),
        card=card if card is not None else _fixture_card(),
        instrument_panel=world.panel,
        placebo_observations=world.pool,
        mean_test_fn=_nw,
        fdr_fn=_bh,
    )
    kwargs.update(over)
    return causal_response(receipt, spec or _spec(), world.outcomes, **kwargs)


@pytest.fixture(scope="module")
def clean():
    world = _world()
    return world, _qualify(world)


def _codes_with(receipt, prefix):
    return [reason for reason in receipt.reasons if reason.startswith(prefix)]


def _only_t_code(receipt, code):
    assert receipt.status == "NOT_IDENTIFIED"
    assert len(receipt.reasons) == 1 and receipt.reasons[0].startswith(f"{code}:t="), receipt.reasons
    assert abs(float(receipt.reasons[0].split("=")[1])) > 1.96
    with pytest.raises(IdentificationRequired):
        receipt.label_receipt()


# ------------------------------------------------------------- frozen card
def _array_block(text, key):
    start = text.index(f'"{key}": [')
    depth = 0
    for j in range(text.index("[", start), len(text)):
        depth += {"[": 1, "]": -1}.get(text[j], 0)
        if depth == 0:
            return text[start : j + 1]
    raise ValueError(key)


def test_frozen_card_hash_recomputes():
    assert FROZEN["definition_hash"] == identification_definition_hash(FROZEN) == FROZEN_DEFINITION_HASH
    card = load_identification_card(ID_CARD_PATH)
    assert card.definition_hash == FROZEN_DEFINITION_HASH
    assert card.estimand_card_hash == hashlib.sha256(EST_BYTES).hexdigest() == card.estimand_sha256
    assert FROZEN["validated"] is False and FROZEN["instrument_candidates"] == []


def test_forbidden_controls_bytes_equal_estimand_card():
    card_block = _array_block(ID_CARD_PATH.read_text(encoding="utf-8"), "forbidden_controls").encode("utf-8")
    estimand_block = _array_block(ESTIMAND_PATH.read_text(encoding="utf-8"), "forbidden_controls").encode("utf-8")
    assert card_block == estimand_block
    assert FROZEN["forbidden_controls"] == ESTIMAND["forbidden_controls"]


def test_frozen_card_validates_clean():
    assert validate_identification_card(load_identification_card(ID_CARD_PATH)) == ()
    assert validate_identification_card(_fixture_card()) == ()


def _set(path, value, *, rehash=True, candidate=False):
    def mutate():
        doc = _fixture_doc() if candidate else copy.deepcopy(FROZEN)
        node = doc
        parts = path.split(".")
        for part in parts[:-1]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        if isinstance(node, list):
            node[int(parts[-1])] = value
        else:
            node[parts[-1]] = value
        if not rehash:
            return build_identification_card(doc, estimand_bytes=EST_BYTES, preregistration_bytes=PRE_BYTES)
        return _card(doc)

    return mutate


def _drop_forbidden():
    doc = copy.deepcopy(FROZEN)
    doc["forbidden_controls"] = doc["forbidden_controls"][:-1]
    return _card(doc)


MUTATIONS = [
    ("BLANK_FIELD:relevance_rule.statistic", _set("relevance_rule.statistic", "  ")),
    ("UNPROVEN_INSTRUMENT_RIGHTS:" + INSTR, _set("instrument_candidates.0.rights_state", "LICENCE_UNVERIFIED", candidate=True)),
    ("FORBIDDEN_CONTROLS_DIVERGE", _drop_forbidden),
    ("HASH_MISMATCH", _set("relevance_rule.min_value", 30.0, rehash=False)),
    ("NON_FINITE_PLACEBO", _set("placebo_design.n_placebo_dates", 0)),
    ("RESERVED_WINDOW_IN_RULE", _set("placebo_design.pool_window.end", "2022-03-31")),
    ("NON_FINITE_THRESHOLD:relevance_rule.min_value", _set("relevance_rule.min_value", -1.0)),
    ("SHOCK_CLASS_NOT_INSTRUMENT:observed_state_change", _set("shock_class", "observed_state_change")),
    ("NON_EXOGENOUS_INSTRUMENT:" + INSTR, _set("instrument_candidates.0.announcement_type", "ols_residual", candidate=True)),
    ("CLOCK_RULE_NOT_POINT_IN_TIME:" + INSTR, _set("instrument_candidates.0.clock_rule", "end_of_day_revised", candidate=True)),
    ("HASH_MISMATCH:estimand_card_ref", _set("estimand_card_ref.card_hash", "0" * 64)),
    ("HASH_MISMATCH:preregistration_card_ref", _set("preregistration_card_ref.card_hash", "0" * 64)),
    ("HASH_MISMATCH:event_definition_id", _set("event_definition_id", "evdef_" + "0" * 64)),
    ("HASH_MISMATCH:relation_id", _set("relation_id", "glt_rel_other.v1")),
]


@pytest.mark.parametrize("code,mutate", MUTATIONS, ids=[code for code, _ in MUTATIONS])
def test_card_mutation_names_its_code(code, mutate):
    assert validate_identification_card(mutate()) == (code,)


# ---------------------------------------------------------------------- C20
@pytest.mark.parametrize("construction", [item["id"] for item in ESTIMAND["non_exogenous_constructions"]])
def test_c20_non_exogenous_construction_never_identifies(construction):
    receipt = _qualify(_world(), _fixture_card(announcement_type=construction))
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (f"CARD_INVALID:NON_EXOGENOUS_INSTRUMENT:{INSTR}",)
    # every statistical test passed: strength and clean pre-trends never cure exogeneity
    assert all(test.passed for test in receipt.tests_run if test.name != "card_admissible")
    with pytest.raises(IdentificationRequired):
        receipt.label_receipt()


@pytest.mark.parametrize("shock_class", ["observed_state_change", "identified_intervention"])
def test_c20_state_change_shock_class_is_not_an_instrument(shock_class):
    doc = _fixture_doc()
    doc["shock_class"] = shock_class
    receipt = _qualify(_world(), _card(doc))
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (f"CARD_INVALID:SHOCK_CLASS_NOT_INSTRUMENT:{shock_class}",)


# ---------------------------------------------------------------------- C23
ESTIMAND_ROLES = (
    [("FORBIDDEN_CONTROL", item["id"]) for item in ESTIMAND["forbidden_controls"]]
    + [("MEDIATOR_AS_CONTROL", item["id"]) for item in ESTIMAND["mediators"]]
    + [("COLLIDER_AS_CONTROL", item["id"]) for item in ESTIMAND["colliders"]]
)


@pytest.mark.parametrize("code,name", ESTIMAND_ROLES, ids=[f"{c}:{n}" for c, n in ESTIMAND_ROLES])
def test_c23_controls_named_by_the_estimand_card_are_refused(code, name):
    codes = validate_specification({"spec_id": "probe", "controls": ["lagged_growth_news", f"  {name.upper()} "]}, ESTIMAND)
    assert f"{code}:{name}" in codes
    assert not any(c.startswith("UNDECLARED_CONTROL") for c in codes)


def test_c23_undeclared_control_is_refused():
    assert validate_specification({"spec_id": "p", "controls": ["vix_level"]}, ESTIMAND) == ("UNDECLARED_CONTROL:vix_level",)
    assert validate_specification({"spec_id": "p", "controls": CONFOUNDERS}, ESTIMAND) == ()
    for spec in FROZEN["admissible_specifications"]:
        assert validate_specification(spec, load_identification_card(ID_CARD_PATH)) == ()


def test_c23_card_specifications_are_checked_at_qualification():
    doc = _fixture_doc()
    doc["admissible_specifications"][1]["controls"].append("contemporaneous_broad_dollar")
    receipt = _qualify(_world(), _card(doc))
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (
        "FORBIDDEN_CONTROL:contemporaneous_broad_dollar",
        "MEDIATOR_AS_CONTROL:contemporaneous_broad_dollar",
    )


def test_c23_anticipation_defeats_the_label():
    _only_t_code(_qualify(_world(anticipation=0.004)), "ANTICIPATION")


def test_c23_pre_trend_defeats_the_label():
    _only_t_code(_qualify(_world(pre_trend=0.004)), "PRE_TREND")


def test_c23_reverse_response_defeats_the_label():
    _only_t_code(_qualify(_world(reverse=0.004)), "REVERSE_RESPONSE")


# ---------------------------------------------------------------------- C30
def test_c30_weak_relevance_is_not_identified():
    receipt = _qualify(_world(gamma=0.05))
    assert receipt.status == "NOT_IDENTIFIED"
    assert len(receipt.reasons) == 1 and receipt.reasons[0].startswith("WEAK_RELEVANCE:first_stage_F=")
    assert receipt.reasons[0].endswith("<23.1")
    assert float(receipt.reasons[0].split("=")[1].split("<")[0]) < 23.1
    few = _qualify(_world(n=12))
    assert "WEAK_RELEVANCE:thinned_events=12<20" in few.reasons and few.status == "NOT_IDENTIFIED"


def test_c30_future_instrument_is_not_identified():
    world = _world(late=(3,))
    receipt = _qualify(world)
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (f"FUTURE_INSTRUMENT:{world.sessions[3].isoformat()}",)
    early = datetime(2010, 1, 4, tzinfo=UTC)
    clean_world = _world()
    as_of_early = _qualify(clean_world, as_of=early)
    expected = [f"FUTURE_INSTRUMENT:{s.isoformat()}" for s in clean_world.sessions if s >= early.date()]
    assert expected and _codes_with(as_of_early, "FUTURE_INSTRUMENT:") == expected


def test_c30_confounding_news_is_not_identified():
    world = _world()
    near = CalendarEvent("cpi_near", "scheduled_cpi_or_payrolls_release", _bday(world.sessions[7], 1))
    receipt = _qualify(world, event_calendar=[*world.calendar, near])
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (f"CONFOUNDING_NEWS:scheduled_cpi_or_payrolls_release:{world.sessions[7].isoformat()}",)


def test_c30_bundled_information_release_counts_unless_purged(clean):
    _world_, receipt = clean
    assert receipt.status == IDENTIFIED_FOR_CONTEXT  # the same-event SEP release is purged
    bundled = _world(announcement_type="fomc_policy_surprise")
    unpurged = _qualify(bundled, _fixture_card(announcement_type="fomc_policy_surprise"))
    assert unpurged.reasons == (f"CONFOUNDING_NEWS:central_bank_information_release:{bundled.sessions[5].isoformat()}",)


def test_c30_no_instrument_on_the_frozen_card():
    receipt = _qualify(_world(), load_identification_card(ID_CARD_PATH))
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == ("NO_INSTRUMENT", f"UNDECLARED_INSTRUMENT:{INSTR}")


def test_c30_unproven_rights_is_not_identified():
    receipt = _qualify(_world(), _fixture_card(rights_state="LICENCE_UNVERIFIED"))
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (f"NO_RIGHTS:{INSTR}",)


# ------------------------------------------------------------ completeness
def test_two_violations_are_both_reported():
    world = _world(gamma=0.05, late=(3,))
    receipt = _qualify(world)
    assert receipt.status == "NOT_IDENTIFIED"
    assert len(receipt.reasons) == 2
    assert receipt.reasons[0] == f"FUTURE_INSTRUMENT:{world.sessions[3].isoformat()}"
    assert receipt.reasons[1].startswith("WEAK_RELEVANCE:first_stage_F=")


def _receipt_fields(receipt):
    return {f.name: getattr(receipt, f.name) for f in fields(receipt)}


def test_missing_inputs_are_failure_codes():
    receipt = qualify_identification(
        _fixture_card(), instrument_panel=None, event_calendar=None, outcome_frame=None, guard=None,
        as_of=AS_OF, mean_test_fn=_nw,
    )
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (
        "MISSING_INPUT:guard",
        "MISSING_INPUT:instrument_panel",
        "MISSING_INPUT:event_calendar",
        "MISSING_INPUT:outcome_frame",
    )
    no_guard = _qualify(_world(), guard=None)
    assert no_guard.reasons == ("MISSING_INPUT:guard",)  # the frame is never read without a guard
    with pytest.raises(ContractError):
        IdentificationReceipt(**{**_receipt_fields(no_guard), "status": IDENTIFIED_FOR_CONTEXT})
    with pytest.raises(ContractError):
        IdentificationReceipt(**{**_receipt_fields(no_guard), "reasons": ()})


# ---------------------------------------------------------- causal refusals
def test_causal_response_refuses_without_an_identified_receipt(clean):
    world, _receipt = clean
    with pytest.raises(IdentificationRequired, match="no identification receipt"):
        _estimate(world, None)
    blocked = _qualify(_world(anticipation=0.004))
    with pytest.raises(IdentificationRequired, match="NOT_IDENTIFIED"):
        _estimate(world, blocked)


def test_causal_response_refuses_a_mismatched_hash(clean):
    world, receipt = clean
    with pytest.raises(IdentificationRequired, match="estimand_card_hash"):
        _estimate(world, replace(receipt, estimand_card_hash="0" * 64))
    with pytest.raises(IdentificationRequired, match="event_definition_id"):
        _estimate(world, replace(receipt, event_definition_id="evdef_" + "0" * 64))
    doc = _fixture_doc()
    doc["relevance_rule"]["min_thinned_events"] = 21
    with pytest.raises(IdentificationRequired, match="definition_hash"):
        _estimate(world, receipt, card=_card(doc))
    with pytest.raises(IdentificationRequired, match="different estimand card"):
        _estimate(world, receipt, spec={**_spec(), "estimand_card_hash": "f" * 64})


def test_causal_response_refuses_another_panel_spec_or_horizon(clean):
    world, receipt = clean
    other = [replace(world.panel[0], surprise=world.panel[0].surprise + 0.5), *world.panel[1:]]
    with pytest.raises(IdentificationRequired, match="instrument panel differs"):
        _estimate(world, receipt, instrument_panel=other)
    bad = _spec("rf_lagged_market_state")
    bad["controls"].append("post_treatment_market_stress_response")
    with pytest.raises(IdentificationRequired, match="COLLIDER_AS_CONTROL"):
        _estimate(world, receipt, spec=bad)
    with pytest.raises(IdentificationRequired, match="not admissible"):
        _estimate(world, receipt, spec={"spec_id": "rf_custom", "controls": ["lagged_growth_news"]})
    with pytest.raises(IdentificationRequired, match="horizons"):
        _estimate(world, receipt, horizons=(5, 40))


# ------------------------------------------------------- identified fixture
def test_identified_fixture_reports_placebo_and_bh_per_horizon(clean):
    world, receipt = clean
    assert receipt.status == IDENTIFIED_FOR_CONTEXT and receipt.reasons == ()
    assert receipt.context["instrument_id"] == INSTR and receipt.context["horizons"] == (5, 20, 60)
    names = [test.name for test in receipt.tests_run]
    assert names == [
        "card_admissible", "specifications_admissible", "instrument_declared", "point_in_time_instrument",
        "confounding_news", "first_stage_relevance", "outcome_firewall", "anticipation", "pre_trend", "reverse_response",
    ]
    relevance = receipt.tests_run[names.index("first_stage_relevance")]
    assert relevance.passed and relevance.value > relevance.threshold == 23.1
    guard = _guard()
    card = _estimate(world, receipt, guard=guard)
    assert isinstance(card, CausalEstimateCard)
    assert card.label == CAUSAL_LABEL == "identified_causal_for_context"
    assert card.evidence_tier == CAUSAL_EVIDENCE_TIER == "identified_causal (context-bound)"
    assert card.validated is False and card.receipt is receipt
    for h in (5, 20):
        cell = card.per_horizon[h]
        assert cell["effective_n"] == 40 and cell["abstention_reason"] is None
        assert abs(cell["estimate"] - BETA * math.sqrt(h / 20)) < 0.003
        assert cell["first_stage"]["F"] > 23.1
        interval = cell["interval"]
        assert interval["kind"] == "pointwise" and interval["shape"] == "bounded"
        assert interval["lower"] <= cell["estimate"] <= interval["upper"]
        assert cell["placebo_p"] == pytest.approx(1 / 201)
        assert cell["bh_q"] == pytest.approx(1 / 201) and cell["bh_reject"] is True
    assert card.joint["status"] == "adjusted" and card.joint["rejected"] == ["h20", "h5"]
    assert card.joint["simultaneous_band"] is None and card.joint["path_claim_allowed"] is False
    assert [s["spec_id"] for s in card.specifications_run] == [s["spec_id"] for s in FROZEN["admissible_specifications"]]
    assert all(v["status"] == "run" for s in card.specifications_run for v in s["per_horizon"].values())
    assert card.window_guard["refused_count"] == 0 and guard.refused_count == 0
    record = card.to_causal_record()
    assert json.loads(json.dumps(record)) == record
    assert record["receipt_id"] == receipt.receipt_id


def test_label_travels_only_with_the_receipt(clean):
    world, receipt = clean
    shock = SimpleNamespace(shock_id="glt_fixture_ev00")
    label = label_shock(shock, shock_class="identified_intervention", identification_receipt=receipt.label_receipt())
    assert label.identification_status == "IDENTIFIED"
    assert label.identification_receipt["receipt_id"] == receipt.receipt_id
    blocked = _qualify(_world(pre_trend=0.004))
    with pytest.raises(IdentificationRequired):
        blocked.label_receipt()
    estimate = _estimate(world, receipt)
    with pytest.raises(IdentificationRequired):
        replace(estimate, receipt=blocked)
    with pytest.raises(ContractError):
        replace(estimate, label="identified_causal")
    with pytest.raises(ContractError):
        replace(estimate, validated=True)
    with pytest.raises(ContractError):
        replace(estimate, evidence_tier="identified_causal")


def _project(**over):
    cell = ResponseCurveCell(
        target_id="spy",
        shock_family="glt_composite",
        condition_bucket="all",
        horizon_bdays=20,
        sample_n=30,
        effective_n=14,
        raw_mean=0.0041,
        shrunk_mean=0.0036,
        interval_low=-0.0010,
        interval_high=0.0082,
        prior_mean=0.0020,
        prior_effective_n=40,
        evidence_state="estimated",
    )
    kwargs = dict(
        spec=ResponsePathSpec.from_card(load_card(PREREG_PATH)),
        shock_definition=FROZEN["event_definition_id"],
        target_calendar="XNYS",
        return_basis="total_return_fixture",
        currency="USD",
        train_cutoff=date(2017, 12, 29),
        coverage=coverage_record(59, 60),
        model_version="glt_t14_m1.v1",
    )
    kwargs.update(over)
    return project_cell(cell, **kwargs)


def test_j_projection_stays_not_identified(clean):
    world, receipt = clean
    _estimate(world, receipt)  # an identified causal card now exists in this context
    projection = _project()
    assert projection.identification_status == "NOT_IDENTIFIED"
    assert projection.estimand_kind == "predictive_response"
    assert "receipt" not in " ".join(inspect.signature(project_cell).parameters)  # no hook to attach one
    with pytest.raises(IdentificationReceiptMissing, match="T17 owns the identification receipt"):
        _project(estimand_kind="causal_response")


def test_causal_card_is_not_a_projection(clean):
    world, receipt = clean
    estimate = _estimate(world, receipt)
    assert not isinstance(estimate, ResponseEvidenceProjection)
    assert not issubclass(CausalEstimateCard, ResponseEvidenceProjection)
    names = {f.name for f in fields(CausalEstimateCard)}
    for absent in ("estimand_kind", "effect_estimate", "identification_status", "interval_or_band", "path_claim_allowed"):
        assert absent not in names and not hasattr(estimate, absent)
    assert not hasattr(estimate, "as_record")


# ---------------------------------------------------------------- firewall
def _reserved_row():
    anchor = date(2022, 1, 3)
    return _row("reserved_probe", anchor, _bday(anchor, 5), 5, 0.0, {EVENT_KEY: "ev00", WINDOW_KEY: ANTICIPATION_WINDOW})


def test_reserved_row_raises_and_counts_refusal():
    world = _world()
    guard = _guard()
    with pytest.raises(ReservedWindowTouched):
        _qualify(world, guard=guard, outcome_frame=[*world.frame, _reserved_row()])
    assert guard.refused_count == 1 and guard.receipt()["refused_by_reason"] == {"reserved_window": 1}


def test_causal_response_reserved_row_raises_and_counts_refusal(clean):
    world, receipt = clean
    guard = _guard()
    with pytest.raises(ReservedWindowTouched):
        causal_response(
            receipt, _spec(), [*world.outcomes, _reserved_row()], horizons=(5, 20), guard=guard, card=_fixture_card(),
            instrument_panel=world.panel, placebo_observations=world.pool, mean_test_fn=_nw, fdr_fn=_bh,
        )
    assert guard.refused_count == 1


def test_reserved_instrument_session_raises():
    world = _world()
    reserved = replace(
        world.panel[-1], event_id="ev_reserved", session=date(2022, 1, 26), known_at=datetime(2022, 1, 26, 19, 0, tzinfo=UTC)
    )
    with pytest.raises(ReservedWindowTouched):
        _qualify(world, instrument_panel=[*world.panel, reserved])


def test_post_announcement_outcome_is_a_firewall_breach(clean):
    world, _receipt = clean
    leaked = [replace(row, conditions={**row.conditions, WINDOW_KEY: ANTICIPATION_WINDOW}) for row in world.outcomes[:3]]
    receipt = _qualify(world, outcome_frame=[*world.frame, *leaked])
    assert receipt.status == "NOT_IDENTIFIED" and receipt.reasons == ("OUTCOME_FIREWALL_BREACH",)


def test_clean_run_refuses_nothing(clean):
    world, _receipt = clean
    guard = _guard()
    assert _qualify(world, guard=guard).status == IDENTIFIED_FOR_CONTEXT
    assert guard.receipt()["refused_count"] == 0 and guard.receipt()["admitted_count"] == len(world.frame)


def test_forward_ledger_is_byte_identical(tmp_path, clean):
    world, receipt = clean
    ledger = ForwardLedger(tmp_path / "liquidity_forward_ledger.jsonl")
    before = (ledger.forecasts(), ledger.grades())
    snapshot = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    _qualify(world)
    _estimate(world, receipt)
    assert (ledger.forecasts(), ledger.grades()) == before == ([], [])
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == snapshot


# --------------------------------------------------------- real-cell state
def test_real_cell_is_not_identified():
    receipt = qualify_identification(
        load_identification_card(ID_CARD_PATH),
        instrument_panel=None,
        event_calendar=None,
        outcome_frame=None,
        guard=None,
        as_of=AS_OF,
    )
    assert receipt.status == "NOT_IDENTIFIED"
    assert receipt.reasons == (
        "NO_INSTRUMENT",
        "MISSING_INPUT:guard",
        "MISSING_INPUT:instrument_panel",
        "MISSING_INPUT:event_calendar",
        "MISSING_INPUT:outcome_frame",
    )
    assert receipt.definition_hash == FROZEN_DEFINITION_HASH
    with pytest.raises(IdentificationRequired):
        receipt.label_receipt()


def _engine_available():
    try:
        import engine.validation  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


@pytest.mark.skipif(_engine_available(), reason="the Macro judges are importable here")
def test_default_judges_abstain_verbatim(clean):
    world, receipt = clean
    natural = _qualify(world, mean_test_fn=None)
    assert natural.status == "NOT_IDENTIFIED" and HAC_MESSAGE in natural.reasons
    assert all(reason.startswith("UNTESTED:") for reason in natural.reasons)
    with pytest.raises(StatisticalDependencyUnavailable, match="newey_west_tstat is required for T17"):
        _estimate(world, receipt, mean_test_fn=None)
    no_fdr = _estimate(world, receipt, fdr_fn=None)
    assert no_fdr.joint["status"] == "abstained"
    assert no_fdr.joint["reason"] == (
        "StatisticalDependencyUnavailable: engine.validation.benjamini_hochberg is required for W-LIQ.3 FDR"
    )
    assert all(cell["bh_q"] is None for cell in no_fdr.per_horizon.values())


def test_module_hygiene():
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "identified_intervention" not in text and "liquiditydata" not in text
    tree = ast.parse(text)
    top = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            top.add(node.module or "")
        elif isinstance(node, ast.Import):
            top.update(alias.name for alias in node.names)
    assert not {m for m in top if m.startswith("engine")}
    every = {
        (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not {m for m in every if m.endswith((".ledger", ".response_evidence", "network", "requests"))}
