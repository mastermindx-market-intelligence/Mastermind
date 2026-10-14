"""Fixture-only offline tests; none of these numbers is a real market observation."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from reaction_replay import ReplayError, replay, main

ET = ZoneInfo("America/New_York")


def stamp(day, hh):
    return datetime.combine(day, datetime.min.time(), ET).replace(hour=hh).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_packet(announce="after", asof_idx=31, dates=None):
    if dates is None:
        dates = [date(2026, 3, 2) + timedelta(days=i) for i in range(46) if (date(2026, 3, 2) + timedelta(days=i)).weekday() < 5]
    sessions = [{"date": d.isoformat(), "open_utc": stamp(d, 9).replace("13:00", "13:30"), "close_utc": stamp(d, 16)} for d in dates]
    # DST holds throughout this case; direct market-local 09:30 -> UTC.
    for s, d in zip(sessions, dates):
        op = datetime.combine(d, datetime.min.time(), ET).replace(hour=9, minute=30).astimezone(timezone.utc)
        s["open_utc"] = op.isoformat().replace("+00:00", "Z")
    at = dates[1]  # prior day index 1 for after-hours; affected day index 2
    if announce == "after":
        announced = datetime.combine(at, datetime.min.time(), ET).replace(hour=16, minute=5)
    elif announce == "pre":
        announced = datetime.combine(dates[2], datetime.min.time(), ET).replace(hour=8)
    elif announce == "intra":
        announced = datetime.combine(dates[2], datetime.min.time(), ET).replace(hour=12)
    elif announce == "at_close":
        announced = datetime.combine(at, datetime.min.time(), ET).replace(hour=16)
    else:
        raise ValueError(announce)
    def bars(start, factor):
        return {"adjustment": "split_dividend_adjusted_close", "source_ref": "fixture-bundle", "bars": [{"date": d.isoformat(), "adjusted_close": start * (factor**i)} for i,d in enumerate(dates)]}
    result = {"event": {"issuer_ref":"CIK:TEST", "fiscal_target":"2026Q1", "event_ref":"ev:test", "first_public_source_ref":"fixture-release", "first_publication_clock_status":"VERIFIED_FIRST_PUBLIC_RELEASE", "first_published_utc":announced.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")},
              "evaluated_asof_utc": (datetime.combine(dates[asof_idx],datetime.min.time(),ET).replace(hour=20).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")),
              "sessions":sessions,
              "price_series":{"issuer":bars(100,1.02),"market":bars(100,1.01),"sector":bars(100,1.015)}}
    return result


def test_after_close_next_session_event_return():
    r = replay(make_packet())
    assert r["reaction"]["status"] == "AVAILABLE"
    assert r["first_affected_session"] == "2026-03-04"
    assert r["unaffected_last_close_session"] == "2026-03-03"
    assert r["reaction"]["returns"]["issuer"] == pytest.approx(.02)
    assert r["reaction"]["returns"]["issuer_minus_market"] == pytest.approx(.01)
    assert r["reaction"]["returns"]["issuer_minus_sector"] == pytest.approx(.005)
    assert r["drift"]["H5"]["returns"]["issuer"] == pytest.approx(1.02**5-1)
    assert r["drift"]["H20"]["returns"]["issuer"] == pytest.approx(1.02**20-1)


def test_premarket_release_and_no_lookahead():
    r = replay(make_packet("pre"))
    assert r["reaction"]["status"] == "AVAILABLE"
    assert r["unaffected_last_close_session"] == "2026-03-03"
    p = make_packet("pre")
    p["evaluated_asof_utc"] = "2026-03-04T14:00:00Z"
    r = replay(p)
    assert r["reaction"]["status"] == "AFFECTED_CLOSE_NOT_YET_KNOWN"
    assert r["drift"]["H5"]["status"] == "HORIZON_NOT_YET_OBSERVABLE"


def test_intraday_close_only_refuses_reaction_not_h5():
    r = replay(make_packet("intra"))
    assert r["reaction"]["status"] == "INTRADAY_CLOSE_WINDOW_CONTAMINATED"
    assert r["drift"]["H5"]["status"] == "AVAILABLE"


def test_release_at_close_refuses_ambiguous_reaction():
    r = replay(make_packet("at_close"))
    assert r["reaction"]["status"] == "AMBIGUOUS_RELEASE_AT_REGULAR_CLOSE"


def test_price_gap_missing_does_not_erase_other_evidence():
    p = make_packet()
    p["price_series"]["market"]["bars"].pop(1)
    r = replay(p)
    assert r["reaction"]["status"] == "MISSING_MARKET_CLOSE"
    assert r["drift"]["H5"]["status"] == "AVAILABLE"


def test_no_prior_session():
    p = make_packet()
    p["event"]["first_published_utc"] = "2026-03-02T10:00:00Z"
    r = replay(p)
    assert r["reaction"]["status"] == "NO_UNAFFECTED_PRIOR_CLOSE"


def test_no_affected_session():
    p = make_packet()
    p["event"]["first_published_utc"] = "2026-05-01T22:00:00Z"
    p["evaluated_asof_utc"] = "2026-05-02T22:00:00Z"
    r = replay(p)
    assert r["reaction"]["status"] == "NO_AFFECTED_FUTURE_SESSION"


def test_future_horizon_missing_not_zero():
    p = make_packet()
    p["sessions"] = p["sessions"][:7]
    for series in p["price_series"].values():
        series["bars"] = series["bars"][:7]
    r = replay(p)
    assert r["drift"]["H5"]["status"] == "INSUFFICIENT_FUTURE_SESSIONS"
    assert r["drift"]["H20"]["status"] == "INSUFFICIENT_FUTURE_SESSIONS"


@pytest.mark.parametrize("mutator,reason", [
    (lambda p: p["event"].update(first_published_utc="2026-03-03T16:05:00"), "TIMESTAMP_WITH_OFFSET_REQUIRED"),
    (lambda p: p["event"].update(event_ref=""), "IMMUTABLE_EVENT_IDENTITY_REQUIRED"),
    (lambda p: p["price_series"]["issuer"].update(adjustment="raw_close"), "ADJUSTMENT_PROVENANCE_REQUIRED"),
    (lambda p: p["price_series"]["issuer"].update(source_ref=""), "PRICE_SOURCE_REQUIRED"),
    (lambda p: p["price_series"]["issuer"]["bars"][0].update(adjusted_close=0), "INVALID_ADJUSTED_CLOSE"),
    (lambda p: p["price_series"]["issuer"]["bars"][0].update(adjusted_close=float("nan")), "INVALID_ADJUSTED_CLOSE"),
    (lambda p: p["price_series"]["issuer"]["bars"].append(dict(p["price_series"]["issuer"]["bars"][0])), "DUPLICATE_PRICE_BAR"),
    (lambda p: p["sessions"].reverse(), "DUPLICATE_OR_UNSORTED_SESSION"),
    (lambda p: p["price_series"].pop("market"), "THREE_PRICE_SERIES_REQUIRED"),
    (lambda p: p.update(evaluated_asof_utc="2026-03-01T20:00:00Z"), "EVALUATION_BEFORE_PUBLICATION"),
    (lambda p: p["sessions"][0].update(open_utc="2026-03-02T23:00:00Z"), "INVALID_EXCHANGE_SESSION_CLOCK"),
])
def test_source_refusals(mutator, reason):
    p = make_packet()
    mutator(p)
    with pytest.raises(ReplayError) as e:
        replay(p)
    assert e.value.reason == reason


def test_weekend_uses_supplied_sessions_only():
    p = make_packet()
    p["event"]["first_published_utc"] = "2026-03-07T14:00:00Z"  # Saturday
    r = replay(p)
    assert r["unaffected_last_close_session"] == "2026-03-06"
    assert r["first_affected_session"] == "2026-03-09"
    assert r["reaction"]["status"] == "AVAILABLE"


def test_only_observed_h5_and_not_h20():
    p = make_packet()
    p["evaluated_asof_utc"] = "2026-03-15T23:00:00Z"
    r = replay(p)
    assert r["drift"]["H5"]["status"] == "AVAILABLE"
    assert r["drift"]["H20"]["status"] == "HORIZON_NOT_YET_OBSERVABLE"


def test_role_adjustments_all_required_even_if_values_missing():
    p = make_packet()
    p["price_series"]["sector"]["bars"].clear()
    r = replay(p)
    assert r["reaction"]["status"] == "MISSING_SECTOR_CLOSE"


def test_no_trade_signal_leaks():
    r = replay(make_packet())
    assert r["authority"] == "RESEARCH_ONLY_NO_TRADING"
    assert set(r.keys()).isdisjoint({"signal", "score", "size", "recommendation", "buy"})


def test_cli_payload(tmp_path, capsys):
    import json
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(make_packet()))
    assert main([str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["reaction"]["status"] == "AVAILABLE"
    path.write_text("not json")
    assert main([str(path)]) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["status"] == "REFUSED"


def test_sec_acceptance_clock_alone_is_insufficient():
    p = make_packet()
    p["event"]["first_publication_clock_status"] = "SEC_ACCEPTANCE_ONLY"
    with pytest.raises(ReplayError) as e:
        replay(p)
    assert e.value.reason == "FIRST_PUBLIC_RELEASE_CLOCK_NOT_VERIFIED"


def test_no_first_public_clock_classification_refuses():
    p = make_packet()
    p["event"].pop("first_publication_clock_status")
    with pytest.raises(ReplayError) as e:
        replay(p)
    assert e.value.reason == "FIRST_PUBLIC_RELEASE_CLOCK_NOT_VERIFIED"


def test_sec_casebook_nine_real_filing_clocks_remain_unadmitted():
    import json
    from pathlib import Path
    casebook = json.loads((Path(__file__).parent / "sec_acceptance_2026.json").read_text())
    rows = casebook["events"]
    assert casebook["first_public_release_clocks_verified"] == 0
    assert len(rows) == 9
    assert len({r["sec_accession"] for r in rows}) == 9
    assert all(r["first_publication_utc"] is None and r["first_publication_clock_status"] == "SEC_ACCEPTANCE_ONLY" for r in rows)
    assert all(r["sec_index_url"].startswith("https://www.sec.gov/Archives/edgar/") for r in rows)
    for row in rows:
        p = make_packet()
        p["event"]["first_publication_clock_status"] = row["first_publication_clock_status"]
        with pytest.raises(ReplayError) as exc:
            replay(p)
        assert exc.value.reason == "FIRST_PUBLIC_RELEASE_CLOCK_NOT_VERIFIED"
