"""GLT T15/T16 WindowGuard: card-window admission; reserved rows refused and counted."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pytest

from brain.liquidity_lab.contracts import ContractError
from brain.liquidity_lab.estimator import ForwardReturnObservation
from brain.liquidity_lab.preregistration import load_card
from brain.liquidity_lab.window_guard import ReservedWindowTouched, WindowGuard

REPO = Path(__file__).resolve().parents[1]
CARD_PATH = REPO / "research/liquidity_transmission/glt_preregistration_card.v1.json"
CARD_HASH = "da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee"


def _bday(day: date, n: int) -> date:
    return np.busday_offset(day.isoformat(), n, roll="forward").astype(date)


def _row(anchor: date, exit_: date, *, shock: str = "liq_x", horizon: int = 20, target: str = "spy"):
    return ForwardReturnObservation(
        shock_id=shock,
        first_detected=datetime.combine(_bday(anchor, -1), time(21, 0)),
        target_id=target,
        asset_class="us_equity",
        hierarchy_parent="us_broad_equity",
        shock_family="glt_composite",
        shock_type="composite_z",
        horizon_bdays=horizon,
        anchor_session=anchor,
        exit_session=exit_,
        forward_return=0.0,
        conditions={},
    )


@pytest.fixture()
def guard():
    return WindowGuard.from_card(load_card(CARD_PATH))


def test_guard_is_built_from_the_frozen_card(guard):
    assert guard.card_hash == CARD_HASH
    assert (guard.train_start, guard.train_end) == (date(2008, 1, 4), date(2017, 12, 29))
    assert (guard.dev_start, guard.dev_end) == (date(2018, 1, 2), date(2021, 12, 31))
    assert guard.reserved_start == date(2022, 1, 3)
    assert guard.purge_sessions == 60
    assert guard.refused_count == 0


def test_exit_on_reserved_start_is_refused_and_counted(guard):
    reserved = guard.reserved_start
    touching = _row(_bday(reserved, -20), reserved, shock="liq_touch")
    inside = _row(_bday(reserved, -40), _bday(reserved, -20), shock="liq_ok")
    admitted = guard.admit([touching, inside], fold="dev")
    assert admitted == [inside]
    assert guard.refused_count == 1
    assert guard.refusals[0].shock_id == "liq_touch"
    assert guard.refusals[0].reason == "reserved_window"
    assert guard.receipt() == {
        "card_hash": CARD_HASH,
        "admitted_count": 1,
        "refused_count": 1,
        "refused_by_reason": {"reserved_window": 1},
    }


def test_assert_no_reserved_raises(guard):
    reserved = guard.reserved_start
    clean = [_row(date(2019, 3, 1), _bday(date(2019, 3, 1), 20))]
    guard.assert_no_reserved(clean)
    with pytest.raises(ReservedWindowTouched, match="reach reserved_start 2022-01-03"):
        guard.assert_no_reserved([*clean, _row(_bday(reserved, -20), reserved, shock="liq_touch")])
    with pytest.raises(ReservedWindowTouched):
        guard.assert_no_reserved([_row(reserved, _bday(reserved, 20))])


def test_train_fold_purges_outcomes_that_mature_in_dev(guard):
    late = _row(_bday(guard.dev_start, -5), _bday(guard.dev_start, 15), shock="liq_late")
    early = _row(date(2010, 6, 1), _bday(date(2010, 6, 1), 20), shock="liq_early")
    before = _row(date(2007, 6, 1), _bday(date(2007, 6, 1), 20), shock="liq_before")
    dev_row = _row(date(2019, 6, 3), _bday(date(2019, 6, 3), 20), shock="liq_dev")
    assert guard.admit([late, early, before, dev_row], fold="train") == [early]
    reasons = sorted(r.reason for r in guard.refusals)
    assert reasons == ["anchor_after_train_end", "before_train_start", "outcome_matures_in_dev"]
    assert guard.refused_count == 3


def test_dev_fold_refuses_anchor_after_dev_end_and_unknown_fold(guard):
    after = _row(date(2022, 1, 3), _bday(date(2022, 1, 3), 5))
    assert guard.admit([after], fold="dev") == []
    assert guard.refusals[-1].reason == "reserved_window"
    with pytest.raises(ContractError, match="unknown fold"):
        guard.admit([], fold="reserved")


def test_horizon_counting_rule_marks_missing_sessions_immature(guard):
    anchor = date(2019, 3, 1)
    declared = [_bday(anchor, i) for i in range(0, 30)]
    row = _row(anchor, _bday(anchor, 20))
    complete = {"spy": declared}
    assert guard.admit([row], fold="dev", declared_sessions=declared, supplied_sessions=complete) == [row]
    gappy = {"spy": [d for d in declared if d != _bday(anchor, 7)]}
    assert guard.admit([row], fold="dev", declared_sessions=declared, supplied_sessions=gappy) == []
    assert guard.refusals[-1].reason == "immature_outcome:missing_sessions=1"
    short = _row(anchor, _bday(anchor, 19))
    assert guard.admit([short], fold="dev", declared_sessions=declared) == []
    assert guard.refusals[-1].reason == "horizon_count_mismatch:declared=19"


def test_tampered_card_is_refused():
    payload = load_card(CARD_PATH).payload
    payload["windows"]["reserved_start"] = "2030-01-02"
    with pytest.raises(ContractError, match="card_hash mismatch"):
        WindowGuard.from_card(payload)
