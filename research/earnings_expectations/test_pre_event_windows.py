"""Pre-event anticipation windows are available only from prior known sessions."""
from datetime import datetime, timedelta, timezone

import pytest

from reaction_replay import replay
from test_reaction_replay import make_packet


def _later_event(*, idx=22):
    packet = make_packet()
    stamp = datetime.fromisoformat(packet["sessions"][idx]["close_utc"].replace("Z", "+00:00"))
    packet["event"]["first_published_utc"] = (
        stamp + timedelta(minutes=5)
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return packet


def test_pre5_pre10_pre20_compound_known_adjusted_prior_sessions():
    x = replay(_later_event())
    for n in (5, 10, 20):
        val = x["pre_event"][f"P{n}"]
        assert val["status"] == "AVAILABLE"
        assert val["returns"]["issuer"] == pytest.approx(1.02 ** n - 1)
        assert val["returns"]["market"] == pytest.approx(1.01 ** n - 1)
        assert val["returns"]["sector"] == pytest.approx(1.015 ** n - 1)
        assert val["returns"]["issuer_minus_market"] == pytest.approx(1.02 ** n - 1.01 ** n)
    assert x["calendar_basis"] == "SUPPLIED_SESSION_CLOCKS_NOT_INDEPENDENTLY_EXCHANGE_VERIFIED"


def test_short_history_is_unestimable_not_a_zero_pre_run():
    data = replay(make_packet())
    for n in (5, 10, 20):
        assert data["pre_event"][f"P{n}"] == {"status": "INSUFFICIENT_PRIOR_SESSIONS"}
    assert data["reaction"]["status"] == "AVAILABLE"


def test_preceding_missing_market_close_is_explicit():
    packet = _later_event()
    day = packet["sessions"][17]["date"]
    packet["price_series"]["market"]["bars"] = [
        row for row in packet["price_series"]["market"]["bars"] if row["date"] != day
    ]
    data = replay(packet)
    assert data["pre_event"]["P5"]["status"] == "MISSING_MARKET_CLOSE"
    assert data["pre_event"]["P10"]["status"] == "AVAILABLE"
    assert data["reaction"]["status"] == "AVAILABLE"


def test_pre_event_observable_even_when_post_close_not_yet_known():
    packet = _later_event()
    event_time = datetime.fromisoformat(
        packet["event"]["first_published_utc"].replace("Z", "+00:00")
    )
    packet["evaluated_asof_utc"] = (event_time + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    data = replay(packet)
    assert data["reaction"]["status"] == "AFFECTED_CLOSE_NOT_YET_KNOWN"
    assert data["pre_event"]["P5"]["status"] == "AVAILABLE"
    assert data["pre_event"]["P20"]["status"] == "AVAILABLE"
    assert data["drift"]["H5"]["status"] == "HORIZON_NOT_YET_OBSERVABLE"


def test_pre_event_remains_available_when_no_future_session():
    packet = make_packet()
    final = len(packet["sessions"]) - 1
    packet = _later_event(idx=final)
    pub = datetime.fromisoformat(packet["event"]["first_published_utc"].replace("Z", "+00:00"))
    packet["evaluated_asof_utc"] = (pub + timedelta(minutes=6)).isoformat().replace("+00:00", "Z")
    data = replay(packet)
    assert data["reaction"]["status"] == "NO_AFFECTED_FUTURE_SESSION"
    assert data["pre_event"]["P20"]["status"] == "AVAILABLE"


def test_without_first_prior_close_pre_event_is_unestimable():
    packet = make_packet()
    packet["event"]["first_published_utc"] = "2026-03-02T10:00:00Z"
    data = replay(packet)
    assert data["reaction"]["status"] == "NO_UNAFFECTED_PRIOR_CLOSE"
    assert all(
        data["pre_event"][f"P{n}"]["status"] == "NO_UNAFFECTED_PRIOR_CLOSE"
        for n in (5, 10, 20)
    )


def test_two_session_casebook_events_do_not_fabricate_price_anticipation():
    import json
    from pathlib import Path
    folder = Path(__file__).parent / "sourced_event_packets"
    cases = list(folder.glob("*.json"))
    assert len(cases) == 9
    for case in cases:
        data = replay(json.loads(case.read_text()))
        assert all(
            data["pre_event"][f"P{n}"]["status"] == "INSUFFICIENT_PRIOR_SESSIONS"
            for n in (5, 10, 20)
        )
        assert data["reaction"]["status"] == "AVAILABLE"


def test_casebook_json_preserves_pre_event_unestimable_windows():
    from replay_casebook import build_report
    result = build_report()
    assert result["sample_size"] == 9
    assert all(
        row["pre_event"][f"P{n}"]["status"] == "INSUFFICIENT_PRIOR_SESSIONS"
        for row in result["cases"] for n in (5, 10, 20)
    )
    assert all(
        row["calendar_basis"] == "SUPPLIED_SESSION_CLOCKS_NOT_INDEPENDENTLY_EXCHANGE_VERIFIED"
        for row in result["cases"]
    )


def test_casebook_markdown_renders_valid_synthetic_pre_windows_only(tmp_path):
    import json
    from replay_casebook import build_report, markdown
    packet = _later_event()
    (tmp_path / "synthetic_case.json").write_text(json.dumps(packet))
    missing = tmp_path / "not_present.json"
    result = build_report(tmp_path, guidance_path=missing, media_path=missing)
    assert result["sample_size"] == 1
    assert result["cases"][0]["pre_event"]["P20"]["status"] == "AVAILABLE"
    narrative = markdown(result)
    assert "Pre-event relative appreciation (supplied-session research only)" in narrative
    assert "ev:test" in narrative
    assert "No" not in narrative.split("## Pre-event relative appreciation")[1][:45]
