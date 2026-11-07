"""Past earnings labels must be invariant to unobservable future price data.

This is an as-of and source-integrity regression suite, using synthetic data only.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from reaction_replay import ReplayError, replay
from test_reaction_replay import make_packet


def _cutoff_packet():
    packet = make_packet()
    published = datetime.fromisoformat(packet["event"]["first_published_utc"].replace("Z", "+00:00"))
    packet["evaluated_asof_utc"] = (published + timedelta(minutes=10)).astimezone(
        timezone.utc).isoformat().replace("+00:00", "Z")
    return packet


def _early_result():
    result = replay(_cutoff_packet())
    assert result["reaction"]["status"] == "AFFECTED_CLOSE_NOT_YET_KNOWN"
    assert result["drift"]["H5"]["status"] == "HORIZON_NOT_YET_OBSERVABLE"
    return result


@pytest.mark.parametrize("role", ["issuer", "market", "sector"])
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), None])
def test_post_asof_undisclosed_close_cannot_poison_earlier_result(role, bad):
    packet = _cutoff_packet()
    packet["price_series"][role]["bars"][3]["adjusted_close"] = bad
    assert replay(packet) == _early_result()


@pytest.mark.parametrize("role", ["issuer", "market", "sector"])
def test_post_asof_duplicate_price_does_not_retroactively_reject(role):
    packet = _cutoff_packet()
    packet["price_series"][role]["bars"].append(
        deepcopy(packet["price_series"][role]["bars"][3])
    )
    assert replay(packet) == _early_result()


def test_unknown_later_session_price_outside_supplied_calendar_does_not_retroactively_reject():
    packet = _cutoff_packet()
    packet["price_series"]["issuer"]["bars"].append({
        "date": "2027-01-04", "adjusted_close": 995.0
    })
    assert replay(packet) == _early_result()


def test_price_after_asof_is_never_counted_as_a_known_close():
    packet = _cutoff_packet()
    after = packet["sessions"][2]["date"]
    packet["price_series"]["issuer"]["bars"][2]["adjusted_close"] = 5000.0
    result = replay(packet)
    assert result["reaction"]["status"] == "AFFECTED_CLOSE_NOT_YET_KNOWN"
    assert result["drift"]["H5"]["status"] == "HORIZON_NOT_YET_OBSERVABLE"
    assert result["evaluated_asof_utc"] == packet["evaluated_asof_utc"]
    assert result["first_affected_session"] == after


@pytest.mark.parametrize("mutation,reason", [
    ("bad_price", "INVALID_ADJUSTED_CLOSE"),
    ("duplicate", "DUPLICATE_PRICE_BAR"),
])
def test_future_price_becomes_strictly_validated_after_it_is_observable(mutation, reason):
    packet = _cutoff_packet()
    packet["evaluated_asof_utc"] = "2026-03-06T23:00:00Z"
    if mutation == "bad_price":
        packet["price_series"]["issuer"]["bars"][3]["adjusted_close"] = -10
    else:
        packet["price_series"]["issuer"]["bars"].append(
            deepcopy(packet["price_series"]["issuer"]["bars"][3])
        )
    with pytest.raises(ReplayError) as exc:
        replay(packet)
    assert exc.value.reason == reason


def test_past_unmatched_session_price_remains_strictly_refused():
    packet = _cutoff_packet()
    packet["price_series"]["issuer"]["bars"].append({
        "date": "2026-02-01", "adjusted_close": 110.0
    })
    with pytest.raises(ReplayError) as exc:
        replay(packet)
    assert exc.value.reason == "BAR_OUTSIDE_EXCHANGE_SESSIONS"


def test_future_only_unobservable_price_does_not_erase_known_pre_event():
    packet = make_packet()
    packet["event"]["first_published_utc"] = "2026-04-01T20:05:00Z"
    packet["evaluated_asof_utc"] = "2026-04-01T20:12:00Z"
    known = replay(packet)
    assert known["pre_event"]["P5"]["status"] == "AVAILABLE"
    packet["price_series"]["sector"]["bars"][-1]["adjusted_close"] = 0
    assert replay(packet) == known
