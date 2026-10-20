"""GLT T18 remaining-repricing projection (C31-C33 and the section 6/8 refusals).

Synthetic fixtures only: a ForwardLedger in tmp_path, hand-built T16 response
paths and remaining-interval panels dated inside the preregistration train/dev
windows.  Nothing here reads ``data/``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from datetime import date, datetime, time, timezone
from pathlib import Path

import numpy as np
import pytest

from brain.liquidity_lab import repricing
from brain.liquidity_lab.baselines import PopulationMismatch
from brain.liquidity_lab.contracts import ContractError, ForecastGrade, ForwardForecast
from brain.liquidity_lab.estimator import ResponseCurveCell
from brain.liquidity_lab.ledger import ForwardLedger, ShockRegistry
from brain.liquidity_lab.preregistration import load_card
from brain.liquidity_lab.repricing import (
    CutoffBeforeIssuanceError,
    DirectStateBaseline,
    ExitElapsedError,
    FuturePathPointError,
    HorizonExtensionError,
    MixedBasisError,
    ModelSourceMismatchError,
    NoGapComparator,
    ObservedPath,
    OriginalFixedResponse,
    OriginalOverwrittenError,
    PathPoint,
    RemainderCandidate,
    RemainderQualification,
    RemainingInterval,
    RepricingProjection,
    append_projection,
    ledger_model_version,
    load_original_forecast,
    load_rules,
    project,
    qualify_remainder,
    reference_path_discrepancy,
    reference_value,
    repricing_updates,
)
from brain.liquidity_lab.response_path import ResponsePath
from brain.liquidity_lab.validation import WalkForwardPrediction
from brain.liquidity_lab.window_guard import WindowGuard

REPO = Path(__file__).resolve().parents[1]
CARD_PATH = REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json"
RULES_PATH = REPO / "research/liquidity_transmission/glt_repricing_rules.v1.json"
RULES_HASH = "026efcf4320973b6e76b45bffd4d7f1c0a88bb51b882d7e3c86ccdb90e68623f"
CARD_HASH = "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"
UTC = timezone.utc
GRID = (1, 5, 10, 20, 40, 60, 90, 120)
SLOPE = 0.0015
H = 20
U = 8
TRAVELLED = 0.004
PATH_MV = "glt_t16_pooled.v1@da060bf4"
LEDGER_MV = "glt_t16_pooled.v1:da060bf4"
CAND_MV = "glt_t18_state_remainder.v1"
DIRECT_MV = "glt_t15_direct_funding.v1@da060bf4"
ISSUED = datetime(2021, 6, 1, 21, 0, tzinfo=UTC)


def _bday(day: date, n: int) -> date:
    return np.busday_offset(day.isoformat(), n, roll="forward").astype(date)


SESSIONS = tuple(_bday(date(2021, 6, 2), k) for k in range(40))


def _session(elapsed: int) -> date:
    return SESSIONS[elapsed - 1]


def _close(day: date) -> datetime:
    return datetime.combine(day, time(21, 0), tzinfo=UTC)


CUTOFF = _close(_session(U))


def _cell(horizon: int, mean: float, target: str = "spy") -> ResponseCurveCell:
    return ResponseCurveCell(
        target_id=target,
        shock_family="glt_composite",
        condition_bucket="all",
        horizon_bdays=horizon,
        sample_n=40,
        effective_n=30,
        raw_mean=mean,
        shrunk_mean=mean,
        interval_low=mean - 0.01,
        interval_high=mean + 0.01,
        prior_mean=None,
        prior_effective_n=0,
        evidence_state="discovered",
    )


def _path(*, target: str = "spy", model_version: str = PATH_MV) -> ResponsePath:
    return ResponsePath(
        model_version=model_version,
        family="pooled",
        partition="all",
        target_id=target,
        shock_family="glt_composite",
        condition_bucket="all",
        horizons=GRID,
        cells=tuple(_cell(h, SLOPE * h, target) for h in GRID),
    )


def _forecast(*, expected: float | None = None) -> ForwardForecast:
    value = SLOPE * H if expected is None else expected
    return ForwardForecast(
        shock_id="liq_live_1",
        target_id="spy",
        horizon_bdays=H,
        model_version=LEDGER_MV,
        predicted_at=ISSUED,
        relation_id="glt_t16_rel",
        relation_state="shadow",
        expected_return=value,
        interval_low=value - 0.03,
        interval_high=value + 0.03,
        probability_positive=None,
        effective_n=30,
        forecast_state="estimated",
    )


KEY = _forecast().forecast_key


def _observed(
    *,
    u: int = U,
    extra: tuple[PathPoint, ...] = (),
    basis: str = "total_return",
    currency: str = "USD",
    model_version: str = LEDGER_MV,
    source: str | None = None,
) -> ObservedPath:
    points = [
        PathPoint(_session(k), k, TRAVELLED * k / u, _close(_session(k))) for k in range(1, u + 1)
    ]
    return ObservedPath(
        forecast_key=KEY,
        target_id="spy",
        return_basis=basis,
        currency=currency,
        model_version=model_version,
        elapsed_cutoff=_close(_session(u)),
        elapsed_sessions=u,
        points=(*points, *extra),
        source_snapshot_hash=source,
    )


def _panel(n: int = 40, seed: int = 20261019, *, start: date = date(2009, 1, 5)):
    rng = np.random.default_rng(seed)
    signal = rng.normal(0.0, 0.02, n)
    noise = rng.normal(0.0, 0.004, n)
    travelled = rng.normal(TRAVELLED, 0.015, n)
    rows = []
    for i in range(n):
        anchor = _bday(start, 60 * i + U)
        rows.append(
            RemainingInterval(
                shock_id=f"liq_h{i:03d}",
                target_id="spy",
                horizon_bdays=H,
                elapsed_sessions=U,
                anchor_session=anchor,
                exit_session=_bday(anchor, H - U),
                travelled_return=float(travelled[i]),
                realized_remaining=float(signal[i] + noise[i]),
                split_index=i % 4,
            )
        )
    return tuple(rows), signal


def _wf(row: RemainingInterval, model_version: str, predicted: float, *, realized=None) -> WalkForwardPrediction:
    return WalkForwardPrediction(
        split_index=row.split_index,
        relation_id="glt_t18_remainder",
        model_version=model_version,
        shock_id=row.shock_id,
        target_id=row.target_id,
        horizon_bdays=row.horizon_bdays,
        anchor_session=row.anchor_session,
        exit_session=row.exit_session,
        predicted_return=float(predicted),
        realized_return=row.realized_remaining if realized is None else float(realized),
        effective_n_at_fit=30,
    )


def _candidate(panel, predictions, *, estimate=0.012, low=0.006, high=0.018, horizon=H, key=KEY, realized=None):
    realized = realized or [None] * len(panel)
    return RemainderCandidate(
        model_version=CAND_MV,
        predictions=tuple(_wf(r, CAND_MV, p, realized=x) for r, p, x in zip(panel, predictions, realized)),
        live_forecast_key=key,
        live_elapsed_sessions=U,
        live_horizon_bdays=horizon,
        live_estimate=estimate,
        live_interval_low=low,
        live_interval_high=high,
        live_known_at=CUTOFF,
    )


def _comparators(panel, signal):
    direct = DirectStateBaseline(
        DIRECT_MV, tuple(_wf(r, DIRECT_MV, 0.3 * s) for r, s in zip(panel, signal)), card_hash=CARD_HASH
    )
    return (NoGapComparator(), direct, OriginalFixedResponse({"spy": _path()}))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def guard():
    return WindowGuard.from_card(load_card(CARD_PATH))


@pytest.fixture()
def ledger(tmp_path):
    store = ForwardLedger(tmp_path / "forward_ledger.jsonl")
    assert store.record(_forecast()) == "created"
    return store


def _qualify(guard, **candidate_kwargs):
    panel, signal = _panel()
    candidate = _candidate(panel, signal, **candidate_kwargs)
    return qualify_remainder(candidate, _comparators(panel, signal), panel, guard)


@pytest.fixture()
def qualified(guard):
    qualification = _qualify(guard)
    assert qualification.passed, qualification.detail
    return qualification


def _project(ledger, qualification, **kwargs):
    original = load_original_forecast(ledger, KEY)
    observed = kwargs.pop("observed", None) or _observed()
    return project(
        original,
        observed,
        qualification,
        as_of=kwargs.pop("as_of", CUTOFF),
        reference_path=kwargs.pop("reference_path", _path()),
        **kwargs,
    )


# ------------------------------------------------------------------ the rules
def test_withholding_rules_are_frozen_with_their_definition_hash(guard, tmp_path):
    rules = load_rules()
    assert rules.definition_hash == RULES_HASH
    assert rules.preregistration_card_hash == guard.card_hash == CARD_HASH
    assert rules.comparators == ("no_gap", "direct_state", "original_fixed")
    assert (rules.margin, rules.min_paired_keys, rules.fold) == (0.98, 10, "dev")
    assert (rules.denominator_near_zero_abs, rules.not_economically_meaningful_abs) == (0.005, 0.0025)
    tampered = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    tampered["percent_withholding"]["denominator_near_zero_abs"] = 0.0001
    copy = tmp_path / "rules.json"
    copy.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ContractError, match="definition_hash"):
        load_rules(copy)


def test_t16_model_versions_map_onto_the_ledger_identifier_grammar():
    assert ledger_model_version(PATH_MV) == LEDGER_MV
    assert ledger_model_version("glt_t16_state_conditioned.v1+prior5@da060bf4") == (
        "glt_t16_state_conditioned.v1.prior5:da060bf4"
    )
    assert _forecast().model_version == LEDGER_MV


# ------------------------------------------------------------------------ C31
def test_c31_projection_carries_discrepancy_and_remainder_with_separate_support(ledger, qualified):
    projection = _project(ledger, qualified)
    m0_u = reference_value(_path(), U)
    assert m0_u == pytest.approx(0.012)
    assert projection.reference_path_discrepancy == pytest.approx(m0_u - TRAVELLED)
    assert projection.discrepancy_label == "observed divergence from the reference path"
    assert projection.remaining_response_estimate == qualified.live_estimate == 0.012
    assert projection.remaining_interval == (0.006, 0.018)
    assert projection.remaining_interval_kind == "pointwise"
    assert projection.remainder_model_version == CAND_MV
    assert projection.original_model_version == LEDGER_MV
    assert (projection.original_exit, projection.elapsed_sessions) == (H, U)
    assert projection.issued_at == ISSUED and projection.elapsed_cutoff == CUTOFF
    assert (projection.return_basis, projection.currency) == ("total_return", "USD")
    assert projection.percent_complete == pytest.approx(TRAVELLED / (TRAVELLED + 0.012))
    assert projection.percent_withheld_reason is None
    assert projection.thesis_status == "active"
    assert projection.remaining_response_estimate != pytest.approx(SLOPE * H - TRAVELLED)
    text = json.dumps(projection.to_payload()).lower()
    for term in load_rules().forbidden_terms:
        assert term not in text


def test_c31_the_m0H_minus_a_u_shortcut_is_unreachable(ledger, qualified):
    shortcut = reference_value(_path(), H) - TRAVELLED
    assert not any("remain" in name for name in inspect.signature(project).parameters)
    original = load_original_forecast(ledger, KEY)
    with pytest.raises(TypeError):
        project(original, _observed(), None, as_of=CUTOFF, reference_path=_path(), remaining_response_estimate=shortcut)
    withheld = _project(ledger, None)
    assert withheld.remaining_response_estimate is None
    assert withheld.remaining_reason == "no_qualified_remainder"
    assert withheld.percent_withheld_reason == "no_qualified_remainder"
    with pytest.raises(ContractError):
        dataclasses.replace(
            withheld,
            remaining_response_estimate=shortcut,
            remaining_interval=(shortcut - 0.01, shortcut + 0.01),
            remaining_interval_kind="pointwise",
            remaining_reason=None,
        )
    with pytest.raises(ContractError):
        dataclasses.replace(qualified, live_estimate=shortcut)
    forged = {f.name: getattr(qualified, f.name) for f in dataclasses.fields(qualified)}
    forged.update(live_estimate=shortcut, live_interval_low=shortcut - 0.01, live_interval_high=shortcut + 0.01, _seal=None)
    with pytest.raises(ContractError):
        RemainderQualification(**forged)


# ------------------------------------------------------------------------ C32
def test_c32_near_zero_denominator_withholds_percent_complete(ledger, guard):
    qualification = _qualify(guard, estimate=-0.002, low=-0.004, high=-0.001)
    projection = _project(ledger, qualification)
    assert projection.remaining_response_estimate == -0.002
    assert abs(TRAVELLED + projection.remaining_response_estimate) < load_rules().denominator_near_zero_abs
    assert projection.percent_complete is None
    assert projection.percent_withheld_reason == "denominator_near_zero"


def test_c32_sign_reversal_between_reference_exit_and_remainder_is_sign_uncertain(ledger, guard):
    qualification = _qualify(guard, estimate=-0.02, low=-0.03, high=-0.01)
    projection = _project(ledger, qualification)
    assert reference_value(_path(), H) > 0 > projection.remaining_response_estimate
    assert projection.percent_complete is None
    assert projection.percent_withheld_reason == "sign_uncertain"


def test_c32_exit_elapsed_raises_and_a_graded_forecast_is_expired(ledger, qualified):
    at_exit = _observed(u=H)
    with pytest.raises(ExitElapsedError):
        _project(ledger, qualified, observed=at_exit, as_of=at_exit.elapsed_cutoff)
    grade = ForecastGrade(KEY, at_exit.elapsed_cutoff, 0.01, "ab" * 8)
    assert ledger.grade(grade) == "created"
    projection = _project(ledger, qualified, observed=at_exit, as_of=at_exit.elapsed_cutoff)
    assert projection.thesis_status == "expired"
    assert projection.remaining_response_estimate is None
    assert projection.remaining_reason == "expired"
    assert projection.percent_complete is None
    assert projection.percent_withheld_reason == "expired"
    assert projection.original_exit == H


# ------------------------------------------------------------------------ C33
def test_c33_invalidating_information_eliminates_the_thesis_and_keeps_the_exit(ledger, qualified):
    before = ledger.path.read_bytes()
    projection = _project(ledger, qualified, invalidating_information=("docket:t11:liq_live_1:policy_reversal",))
    assert projection.thesis_status == "eliminated"
    assert projection.remaining_response_estimate is None
    assert projection.remaining_interval is None
    assert projection.remaining_reason == "invalidated_by_new_information"
    assert projection.percent_complete is None
    assert projection.invalidating_information == ("docket:t11:liq_live_1:policy_reversal",)
    ledger_exit = json.loads(before.decode("utf-8").splitlines()[0])["payload"]["horizon_bdays"]
    assert projection.original_exit == ledger_exit == H
    assert ledger.path.read_bytes() == before


def test_c33_a_later_exit_raises_horizon_extension(ledger, guard, qualified):
    with pytest.raises(HorizonExtensionError):
        _project(ledger, qualified, original_exit=40)
    with pytest.raises(HorizonExtensionError):
        _qualify(guard, horizon=40)
    assert _project(ledger, qualified, original_exit=H).original_exit == H


# ---------------------------------------------------- section 6 qualification
def test_no_gap_comparator_winning_withholds_the_remainder(ledger, guard):
    panel, signal = _panel()
    candidate = _candidate(panel, -signal)
    qualification = qualify_remainder(candidate, _comparators(panel, signal), panel, guard)
    assert not qualification.passed
    assert qualification.reason == "no_incremental_support"
    assert "no_gap" in qualification.detail
    projection = _project(ledger, qualification)
    assert projection.remaining_response_estimate is None
    assert projection.remaining_reason == "no_incremental_support"
    assert projection.remainder_model_version is None
    assert projection.percent_withheld_reason == "no_qualified_remainder"


def test_a_candidate_that_only_fits_the_travelled_path_is_not_qualified(guard):
    panel, signal = _panel()
    m0_h = reference_value(_path(), H)
    travelled_only = [m0_h - row.travelled_return for row in panel]
    qualification = qualify_remainder(
        _candidate(panel, travelled_only), _comparators(panel, signal), panel, guard
    )
    assert not qualification.passed
    assert qualification.reason == "no_incremental_support"
    assert qualification.live_estimate is None
    scored_on_the_path = _candidate(panel, signal, realized=[row.travelled_return for row in panel])
    with pytest.raises(ContractError, match="disagrees on the realized return"):
        qualify_remainder(scored_on_the_path, _comparators(panel, signal), panel, guard)


def test_negative_qualified_remainder_is_reported_negative_never_inverted(ledger, guard):
    qualification = _qualify(guard, estimate=-0.02, low=-0.03, high=-0.01)
    assert qualification.passed
    projection = _project(ledger, qualification)
    assert projection.remaining_response_estimate == -0.02
    assert projection.remaining_interval == (-0.03, -0.01)


def test_qualification_passes_only_against_all_three_comparators(qualified):
    names = [name for name, _ in qualified.comparator_mse]
    assert names == ["no_gap", "direct_state", "original_fixed"]
    for _, mse in qualified.comparator_mse:
        assert qualified.candidate_mse <= 0.98 * mse
    assert qualified.n_paired_keys == 40
    assert qualified.rules_hash == RULES_HASH


def test_fewer_paired_keys_than_the_floor_is_no_incremental_support(guard):
    panel, signal = _panel(n=6)
    qualification = qualify_remainder(_candidate(panel, signal), _comparators(panel, signal), panel, guard)
    assert not qualification.passed
    assert qualification.reason == "no_incremental_support"
    assert qualification.n_paired_keys == 6


def test_asymmetric_keys_are_refused(guard):
    panel, signal = _panel()
    short = _candidate(panel[:-1], signal[:-1])
    with pytest.raises(PopulationMismatch):
        qualify_remainder(short, _comparators(panel, signal), panel, guard)


def test_comparators_must_be_exactly_the_frozen_three(guard):
    panel, signal = _panel()
    no_gap, direct, _ = _comparators(panel, signal)
    with pytest.raises(ContractError):
        qualify_remainder(_candidate(panel, signal), (no_gap, direct), panel, guard)


def test_direct_state_must_be_a_t15_direct_rung_at_the_card():
    with pytest.raises(ContractError):
        DirectStateBaseline(PATH_MV, (), card_hash=CARD_HASH)
    with pytest.raises(ContractError):
        DirectStateBaseline("glt_t15_direct_funding.v1@00000000", (), card_hash=CARD_HASH)


def test_window_guard_refusals_are_counted_and_never_scored(guard):
    early, early_signal = _panel(n=2, seed=7, start=date(2006, 1, 3))
    early = tuple(dataclasses.replace(row, shock_id=f"liq_early_{i}") for i, row in enumerate(early))
    panel, signal = _panel()
    rows = panel + early
    signals = np.concatenate([signal, early_signal])
    qualification = qualify_remainder(_candidate(rows, signals), _comparators(rows, signals), rows, guard)
    assert qualification.passed
    assert qualification.n_paired_keys == 40
    assert qualification.guard_receipt["refused_count"] == guard.refused_count > 0
    assert set(qualification.guard_receipt["refused_by_reason"]) == {"before_train_start"}


def test_a_guard_from_another_card_is_refused(guard):
    guard.card_hash = "0" * 64
    with pytest.raises(ContractError):
        _qualify(guard)


# ------------------------------------------------------------ section 8 refusals
def test_future_path_point_is_refused(ledger, qualified):
    late = PathPoint(_session(U + 1), U + 1, 0.005, _close(_session(U + 1)))
    with pytest.raises(FuturePathPointError):
        reference_path_discrepancy(_path(), _observed(extra=(late,)))
    with pytest.raises(FuturePathPointError):
        _project(ledger, qualified, observed=_observed(extra=(late,)))
    restated = PathPoint(_session(U - 1), U - 1, 0.003, _close(_session(U + 2)))
    points = tuple(p for p in _observed().points if p.elapsed_sessions != U - 1) + (restated,)
    with pytest.raises(FuturePathPointError):
        reference_path_discrepancy(_path(), dataclasses.replace(_observed(), points=points))


def test_cutoff_before_issuance_is_refused(ledger, qualified):
    early_day = date(2021, 5, 28)
    observed = ObservedPath(
        forecast_key=KEY,
        target_id="spy",
        return_basis="total_return",
        currency="USD",
        model_version=LEDGER_MV,
        elapsed_cutoff=_close(early_day),
        elapsed_sessions=1,
        points=(PathPoint(early_day, 1, 0.001, _close(early_day)),),
    )
    with pytest.raises(CutoffBeforeIssuanceError):
        _project(ledger, qualified, observed=observed, as_of=_close(early_day))


def test_mixed_basis_or_currency_is_refused(ledger, qualified):
    with pytest.raises(MixedBasisError):
        _project(ledger, qualified, observed=_observed(basis="price_return"))
    with pytest.raises(MixedBasisError):
        _project(ledger, qualified, observed=_observed(currency="EUR"))


def test_model_or_source_mismatch_is_refused(ledger, qualified, tmp_path):
    with pytest.raises(ModelSourceMismatchError):
        _project(ledger, qualified, observed=_observed(model_version="glt_t16_local_projection.v1:da060bf4"))
    with pytest.raises(ModelSourceMismatchError):
        _project(ledger, qualified, reference_path=_path(model_version="glt_t16_local_projection.v1@da060bf4"))
    original = dataclasses.replace(load_original_forecast(ledger, KEY), source_snapshot_hash="cd" * 8)
    with pytest.raises(ModelSourceMismatchError):
        project(original, _observed(source="ab" * 8), qualified, as_of=CUTOFF, reference_path=_path())
    with pytest.raises(ModelSourceMismatchError):
        load_original_forecast(ledger, KEY, registry=ShockRegistry(tmp_path / "shocks.jsonl"))


def test_a_qualification_for_another_forecast_is_refused(ledger, guard):
    other = _qualify(guard, key="liq_other:spy:20:" + LEDGER_MV)
    assert other.passed
    with pytest.raises(ModelSourceMismatchError):
        _project(ledger, other)


def test_original_overwritten_is_refused(ledger, qualified):
    original = load_original_forecast(ledger, KEY)
    rewritten = dataclasses.replace(original, forecast=_forecast(expected=0.031))
    with pytest.raises(OriginalOverwrittenError):
        project(rewritten, _observed(), qualified, as_of=CUTOFF, reference_path=_path())
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["payload"]["expected_return"] = 0.05
    ledger.path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(OriginalOverwrittenError):
        load_original_forecast(ledger, KEY)
    projection = project(original, _observed(), qualified, as_of=CUTOFF, reference_path=_path())
    with pytest.raises(OriginalOverwrittenError):
        append_projection(ledger, projection)


# ------------------------------------------------------------------ the ledger
def test_read_only_projection_leaves_the_ledger_hash_identical(ledger, qualified):
    before = _sha(ledger.path)
    projection = _project(ledger, qualified)
    reference_path_discrepancy(_path(), _observed())
    assert repricing_updates(ledger, KEY) == []
    assert projection.percent_complete is not None
    assert _sha(ledger.path) == before


def test_an_update_appends_exactly_one_row_and_never_rewrites_the_original(ledger, qualified):
    before = ledger.path.read_bytes()
    before_hash = _sha(ledger.path)
    projection = _project(ledger, qualified, as_of=_close(_session(U + 1)))
    assert append_projection(ledger, projection) == "created"
    after = ledger.path.read_bytes()
    assert _sha(ledger.path) != before_hash
    assert after.startswith(before)
    added = after[len(before):].decode("utf-8").splitlines()
    assert len(added) == 1
    row = json.loads(added[0])
    assert row["kind"] == "forecast_repricing_update"
    assert row["forecast_key"] == KEY
    assert row["payload"]["original_exit"] == H
    assert row["payload"]["remaining_response_estimate"] == 0.012
    assert ledger.forecasts() == [_forecast().to_dict()]
    assert repricing_updates(ledger, KEY) == [projection.to_payload()]
    assert append_projection(ledger, projection) == "duplicate"
    assert ledger.path.read_bytes() == after
    assert ledger.record(_forecast()) == "duplicate"


def test_update_for_an_unknown_forecast_is_refused(tmp_path, ledger, qualified):
    projection = _project(ledger, qualified)
    empty = ForwardLedger(tmp_path / "empty.jsonl")
    with pytest.raises(ContractError):
        append_projection(empty, projection)
    with pytest.raises(ContractError):
        load_original_forecast(empty, KEY)


def test_projection_contract_refuses_inconsistent_states(ledger, qualified):
    projection = _project(ledger, qualified)
    assert isinstance(projection, RepricingProjection)
    with pytest.raises(ContractError):
        dataclasses.replace(projection, thesis_status="eliminated")
    with pytest.raises(ContractError):
        dataclasses.replace(projection, percent_complete=0.5, percent_withheld_reason="sign_uncertain")
    with pytest.raises(ContractError):
        dataclasses.replace(projection, discrepancy_label="mispricing")


def test_an_issued_percent_is_bound_to_the_sealed_interval_and_inputs(ledger, qualified):
    projection = _project(ledger, qualified)
    assert projection.percent_complete is not None
    # L4 F1 reproduction: an issued percent over a zero-straddling interval.
    with pytest.raises(ContractError):
        dataclasses.replace(projection, remaining_interval=(-0.005, 0.005))
    with pytest.raises(ContractError):
        dataclasses.replace(projection, remaining_interval=(0.007, 0.018))
    with pytest.raises(ContractError):
        dataclasses.replace(projection, travelled_return=projection.travelled_return + 0.001)
    with pytest.raises(ContractError):
        dataclasses.replace(projection, percent_complete=projection.percent_complete + 0.25)
    with pytest.raises(ContractError):
        dataclasses.replace(projection, _percent_seal=None)
    forged = {f.name: getattr(projection, f.name) for f in dataclasses.fields(projection)}
    forged.update(percent_complete=projection.percent_complete + 0.25, _percent_seal="0" * 64)
    with pytest.raises(ContractError):
        RepricingProjection(**forged)
    assert projection.to_payload()["percent_complete"] == projection.percent_complete


def test_module_language_avoids_the_forbidden_terms():
    text = Path(repricing.__file__).read_text(encoding="utf-8").lower()
    for term in load_rules().forbidden_terms:
        assert term not in text
