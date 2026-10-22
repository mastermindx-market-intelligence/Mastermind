"""Observation-basis regressions for portfolio.marks (A03 point-in-time marks, C2).

Every case is offline: Polygon is monkeypatched at the module seam, yahoo parquet rows are
injected through ``_yahoo_close_series``, and every clock is pinned with ``now=`` so the ET
session date never depends on the test machine's date or timezone.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from portfolio import marks as M


def _none_polygon(_symbol: str):
    return None


def _none_yahoo(_symbol: str, _asof: str):
    return None


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect the carry store + per-day audit logs into a temp dir."""
    monkeypatch.setattr(M, "_MARKS_DIR", tmp_path)
    monkeypatch.setattr(M, "_CARRY_PATH", tmp_path / "last_good.json")
    return tmp_path


def _fake_series(monkeypatch, closes: dict[str, float]):
    """Inject a yahoo close series ({'YYYY-MM-DD': close}) through the store seam."""
    idx = pd.DatetimeIndex(pd.to_datetime(sorted(closes)))
    s = pd.Series([float(closes[d.date().isoformat()]) for d in idx], index=idx, dtype=float)
    monkeypatch.setattr(M, "_yahoo_close_series", lambda _symbol: s)


# ── yahoo observation (D) ─────────────────────────────────────────────────────
def test_yahoo_row_carries_directional_age(sandbox, monkeypatch):
    _fake_series(monkeypatch, {"2026-10-01": 90.0, "2026-10-05": 91.5})
    res = M.mark_symbols(["AAPL"], "2026-10-08", polygon_fn=_none_polygon,
                         carry={}, persist=False)
    row = res["sources"]["AAPL"]
    assert res["prices"]["AAPL"] == pytest.approx(91.5)
    assert row["source"] == "yahoo-parquet"
    assert row["stale_days"] == 3                       # 2026-10-08 minus 2026-10-05
    assert row["observed_asof"] == "2026-10-05"


def test_yahoo_row_older_than_bound_is_ineligible(sandbox, monkeypatch):
    monkeypatch.setattr(M, "_stale_max_days", lambda: 5)
    _fake_series(monkeypatch, {"2026-09-29": 90.0})     # 9 days before asof
    res = M.mark_symbols(["AAPL"], "2026-10-08", polygon_fn=_none_polygon,
                         carry={}, persist=False)
    assert "AAPL" not in res["prices"]                  # no carry → unpriced
    assert res["counts"]["unpriced"] == 1
    res2 = M.mark_symbols(["AAPL"], "2026-10-08", polygon_fn=_none_polygon,
                          carry={"AAPL": {"price": 95.0, "asof": "2026-10-07", "source": "seed"}},
                          persist=False)
    assert res2["prices"]["AAPL"] == pytest.approx(95.0)   # a fresh carry still rescues it
    assert res2["sources"]["AAPL"]["source"] == M.SOURCE_CARRY


def test_yahoo_close_qualified_and_basis(monkeypatch):
    _fake_series(monkeypatch, {"2026-10-01": 90.0, "2026-10-05": 91.5, "2026-10-09": 92.0})
    newest = M._yahoo_observation("AAPL", "2026-10-09")
    assert newest["observed_asof"] == "2026-10-09"
    assert newest["close_qualified"] is True            # the newest row cannot be restated
    hist = M._yahoo_observation("AAPL", "2026-10-05")
    assert hist["observed_asof"] == "2026-10-05"
    assert hist["close_qualified"] is False             # later rows may carry restatements
    assert hist["basis"] == "split_div_adjusted_at_retrieval"
    assert hist["adjusted_through"] == "2026-10-09"
    assert M._yahoo_parquet("AAPL", "2026-10-05") == pytest.approx(91.5)   # float wrapper intact


# ── polygon observation, current session date (C) ─────────────────────────────
def test_after_close_today_uses_official_bar_never_snapshot(monkeypatch):
    from data_layer import polygon

    calls = {}

    def fake_daily(symbol, start, end, cache=True, adjusted=True):
        calls.update(symbol=symbol, start=start, end=end, cache=cache, adjusted=adjusted)
        return {"2026-10-21": 105.5}

    monkeypatch.setattr(polygon, "daily_closes", fake_daily)
    monkeypatch.setattr(polygon, "_snapshot",
                        lambda _s: pytest.fail("settled close must not read the snapshot"))
    now = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)   # 18:00 ET ≥ 16:20 ET settle
    obs = M._polygon_observation("AAPL", "2026-10-21", now=now)
    assert obs == {"price": 105.5, "source": "polygon-eod", "observed_asof": "2026-10-21",
                   "basis": "raw", "time_kind": "session_close", "close_qualified": True}
    assert calls == {"symbol": "AAPL", "start": "2026-10-21", "end": "2026-10-21",
                     "cache": False, "adjusted": False}
    res = M.mark_symbols(["AAPL"], "2026-10-21", yahoo_fn=_none_yahoo, persist=False, now=now)
    assert res["sources"]["AAPL"]["stale_days"] == 0
    assert res["sources"]["AAPL"]["close_qualified"] is True


def test_after_close_bar_missing_counts_and_falls_to_yahoo(sandbox, monkeypatch):
    from data_layer import polygon

    monkeypatch.setattr(polygon, "daily_closes", lambda *a, **k: {})
    monkeypatch.setattr(polygon, "_snapshot",
                        lambda _s: pytest.fail("settled close must not read the snapshot"))
    now = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
    assert M._polygon_observation("AAPL", "2026-10-21", now=now) is None
    res = M.mark_symbols(["AAPL"], "2026-10-21",
                         yahoo_fn=lambda s, a: {"price": 99.0, "observed_asof": "2026-10-21"},
                         persist=False, now=now)
    assert res["prices"]["AAPL"] == pytest.approx(99.0)
    assert res["sources"]["AAPL"]["source"] == "yahoo-parquet"
    assert res["counts"]["polygon_close_bar_missing"] == 1


def test_before_close_intraday_is_not_close_grade_and_not_carried(sandbox, monkeypatch):
    from data_layer import polygon

    monkeypatch.setattr(polygon, "daily_closes",
                        lambda *a, **k: pytest.fail("pre-close must not read aggregates"))
    monkeypatch.setattr(polygon, "_snapshot", lambda _s: {"lastTrade": {"p": 111.5}})
    now = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)   # 11:00 ET, trading day
    res = M.mark_symbols(["AAPL"], "2026-10-21", yahoo_fn=_none_yahoo, persist=True, now=now)
    row = res["sources"]["AAPL"]
    assert row["source"] == "polygon-intraday"
    assert row["time_kind"] == "intraday"
    assert row["close_qualified"] is False
    assert row["stale_days"] == 0
    assert row["price"] == pytest.approx(111.5)
    stored = json.loads((sandbox / "last_good.json").read_text())
    assert "AAPL" not in stored                          # an intraday print never refreshes carry


def test_before_close_prevday_fallback_is_labelled_and_not_carried(sandbox, monkeypatch):
    from data_layer import polygon

    monkeypatch.setattr(polygon, "daily_closes",
                        lambda *a, **k: pytest.fail("pre-close must not read aggregates"))
    monkeypatch.setattr(polygon, "_snapshot", lambda _s: {"prevDay": {"c": 98.0}})
    now = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)
    res = M.mark_symbols(["AAPL"], "2026-10-21", yahoo_fn=_none_yahoo, persist=True, now=now)
    row = res["sources"]["AAPL"]
    assert row["source"] == "polygon-prevday"
    assert row["observed_asof"] == "2026-10-20"
    assert row["stale_days"] == 1
    assert row["close_qualified"] is False
    assert row["basis"] == "unknown"
    stored = json.loads((sandbox / "last_good.json").read_text())
    assert "AAPL" not in stored


def test_intraday_observed_asof_comes_from_lasttrade_timestamp(sandbox, monkeypatch):
    from data_layer import polygon

    t_ns = int(datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc).timestamp() * 1e9)  # 16:00 ET Tue
    monkeypatch.setattr(polygon, "daily_closes",
                        lambda *a, **k: pytest.fail("pre-open must not read aggregates"))
    monkeypatch.setattr(polygon, "_snapshot",
                        lambda _s: {"lastTrade": {"p": 107.25, "t": t_ns}})
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)   # 08:00 ET pre-open
    obs = M._polygon_observation("AAPL", "2026-10-21", now=now)
    assert obs["source"] == "polygon-intraday"
    assert obs["observed_asof"] == "2026-10-20"         # the trade's own ET date, not today
    res = M.mark_symbols(["AAPL"], "2026-10-21", yahoo_fn=_none_yahoo, persist=False, now=now)
    assert res["sources"]["AAPL"]["stale_days"] == 1


def test_early_close_settlement_boundary(monkeypatch):
    from data_layer import polygon

    daily_calls = []

    def fake_daily(*a, **k):
        daily_calls.append(k)
        return {"2026-11-27": 100.0}

    monkeypatch.setattr(polygon, "daily_closes", fake_daily)
    monkeypatch.setattr(polygon, "_snapshot", lambda _s: {"lastTrade": {"p": 100.5}})
    after = datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc)   # 13:30 ET > 13:20 settle
    before = datetime(2026, 11, 27, 18, 10, tzinfo=timezone.utc)  # 13:10 ET
    assert M.session_final(date(2026, 11, 27), after) is True
    obs = M._polygon_observation("AAPL", "2026-11-27", now=after)
    assert obs["source"] == "polygon-eod"
    assert obs["price"] == pytest.approx(100.0)
    assert len(daily_calls) == 1 and daily_calls[0]["cache"] is False
    assert M.session_final(date(2026, 11, 27), before) is False
    obs2 = M._polygon_observation("AAPL", "2026-11-27", now=before)
    assert obs2["source"] == "polygon-intraday"
    assert obs2["price"] == pytest.approx(100.5)
    assert len(daily_calls) == 1


def test_non_trading_today_yields_no_polygon_observation(monkeypatch):
    from data_layer import polygon

    monkeypatch.setattr(polygon, "daily_closes",
                        lambda *a, **k: pytest.fail("non-trading day must not read aggregates"))
    monkeypatch.setattr(polygon, "_snapshot",
                        lambda _s: pytest.fail("non-trading day must not read the snapshot"))
    now = datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)   # Saturday
    assert M._polygon_observation("AAPL", "2026-10-24", now=now) is None


def test_historical_asof_reads_cached_raw_aggregate(monkeypatch):
    from data_layer import polygon

    calls = {}

    def fake_daily(symbol, start, end, cache=True, adjusted=True):
        calls.update(symbol=symbol, start=start, end=end, cache=cache, adjusted=adjusted)
        return {"2026-10-20": 101.0}

    monkeypatch.setattr(polygon, "daily_closes", fake_daily)
    monkeypatch.setattr(polygon, "_snapshot",
                        lambda _s: pytest.fail("historical mark must not read the snapshot"))
    now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
    obs = M._polygon_observation("AAPL", "2026-10-20", now=now)
    assert obs == {"price": 101.0, "source": "polygon-eod", "observed_asof": "2026-10-20",
                   "basis": "raw", "time_kind": "session_close", "close_qualified": True}
    assert calls == {"symbol": "AAPL", "start": "2026-10-20", "end": "2026-10-20",
                     "cache": True, "adjusted": False}


def test_future_asof_makes_no_call(monkeypatch):
    from data_layer import polygon

    monkeypatch.setattr(polygon, "daily_closes",
                        lambda *a, **k: pytest.fail("future as-of must not read aggregates"))
    monkeypatch.setattr(polygon, "_snapshot",
                        lambda _s: pytest.fail("future as-of must not read the snapshot"))
    now = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
    assert M._polygon_observation("AAPL", "2026-10-22", now=now) is None


# ── monotone carry refresh (G) ────────────────────────────────────────────────
def test_carry_store_never_moves_backward_on_replay(sandbox):
    (sandbox / "last_good.json").write_text(json.dumps(
        {"AAPL": {"price": 200.0, "asof": "2026-10-21", "source": "polygon-eod",
                  "basis": "raw", "retrieved_at": "2026-10-21T22:00:00+00:00"}}))
    now = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)
    replay_obs = {"price": 150.0, "observed_asof": "2026-10-15", "basis": "raw",
                  "time_kind": "session_close", "close_qualified": True}
    res = M.mark_symbols(["AAPL"], "2026-10-15", polygon_fn=lambda s: replay_obs,
                         yahoo_fn=_none_yahoo, persist=True, now=now)
    assert res["prices"]["AAPL"] == pytest.approx(150.0)   # the replay still marks
    stored = json.loads((sandbox / "last_good.json").read_text())["AAPL"]
    assert stored["asof"] == "2026-10-21"                # ...but the newer carry survives
    assert stored["price"] == pytest.approx(200.0)
    assert (sandbox / "2026-10-15.json").exists()         # per-asof audit still written


def test_carry_refresh_stores_observed_asof_not_mark_asof(sandbox, monkeypatch):
    _fake_series(monkeypatch, {"2026-10-02": 90.0, "2026-10-06": 91.0})
    now = datetime(2026, 10, 8, 22, 0, tzinfo=timezone.utc)
    res = M.mark_symbols(["AAPL"], "2026-10-08", polygon_fn=_none_polygon, persist=True, now=now)
    row = res["sources"]["AAPL"]
    assert row["source"] == "yahoo-parquet"
    assert row["observed_asof"] == "2026-10-06"
    assert row["stale_days"] == 2
    stored = json.loads((sandbox / "last_good.json").read_text())["AAPL"]
    assert stored["asof"] == "2026-10-06"                # the row's date, not the mark's
    assert stored["price"] == pytest.approx(91.0)
    assert stored["source"] == "yahoo-parquet"
    assert stored["basis"] == "split_div_adjusted_at_retrieval"
    assert stored["retrieved_at"] == "2026-10-08T22:00:00+00:00"


# ── row shape (A) and injected sources (E) ────────────────────────────────────
def test_source_row_shape(sandbox, monkeypatch):
    from data_layer import polygon

    now = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
    now_iso = now.isoformat(timespec="seconds")
    keys8 = {"source", "price", "stale_days", "observed_asof", "retrieved_at",
             "basis", "time_kind", "close_qualified"}

    def run(sym, *, asof="2026-10-20", now=now, **kw):
        return M.mark_symbols([sym], asof, persist=False, now=now, **kw)["sources"][sym]

    eod_obs = {"price": 100.0, "observed_asof": "2026-10-20", "basis": "raw",
               "time_kind": "session_close", "close_qualified": True}
    yahoo_obs = {"price": 90.0, "observed_asof": "2026-10-20",
                 "basis": "split_div_adjusted_at_retrieval", "time_kind": "session_close",
                 "close_qualified": False, "adjusted_through": "2026-10-20"}

    seed_row = run("SEED1", seed={"SEED1": 111.0}, polygon_fn=_none_polygon, yahoo_fn=_none_yahoo)
    eod_row = run("EOD1", polygon_fn=lambda s: eod_obs, yahoo_fn=_none_yahoo)
    yahoo_row = run("YHOO1", polygon_fn=_none_polygon, yahoo_fn=lambda s, a: yahoo_obs)

    monkeypatch.setattr(polygon, "daily_closes",
                        lambda *a, **k: pytest.fail("pre-close must not read aggregates"))
    monkeypatch.setattr(polygon, "_snapshot", lambda _s: {"lastTrade": {"p": 111.5}})
    intraday_row = run("INT1", asof="2026-10-21",
                       now=datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc),
                       yahoo_fn=_none_yahoo)
    monkeypatch.setattr(polygon, "_snapshot", lambda _s: {"prevDay": {"c": 98.0}})
    prevday_row = run("PRV1", asof="2026-10-21",
                      now=datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc),
                      yahoo_fn=_none_yahoo)

    carry_row = run("CAR1", polygon_fn=_none_polygon, yahoo_fn=_none_yahoo,
                    carry={"CAR1": {"price": 80.0, "asof": "2026-10-19", "source": "polygon-eod",
                                    "basis": "raw", "retrieved_at": "2026-10-19T22:00:00+00:00"}})
    legacy_carry_row = run("LGC1", polygon_fn=_none_polygon, yahoo_fn=_none_yahoo,
                           carry={"LGC1": {"price": 70.0, "asof": "2026-10-19"}})
    unpriced_row = run("UNP1", polygon_fn=_none_polygon, yahoo_fn=_none_yahoo, carry={})

    for row in (seed_row, eod_row, intraday_row, prevday_row, carry_row, legacy_carry_row,
                unpriced_row):
        assert set(row) == keys8
    assert set(yahoo_row) == keys8 | {"adjusted_through"}

    assert eod_row["retrieved_at"] == now_iso            # a live row carries this run's clock
    assert yahoo_row["retrieved_at"] == now_iso
    assert seed_row == {"source": "seed", "price": 111.0, "stale_days": 0,
                        "observed_asof": "2026-10-20", "retrieved_at": now_iso,
                        "basis": "unknown", "time_kind": "seed", "close_qualified": False}
    assert carry_row["retrieved_at"] == "2026-10-19T22:00:00+00:00"
    assert carry_row["time_kind"] == "carry"
    assert legacy_carry_row["retrieved_at"] is None      # a legacy carry has no stored clock
    assert legacy_carry_row["basis"] == "unknown"
    assert unpriced_row == {"source": None, "price": None, "stale_days": None,
                            "observed_asof": None, "retrieved_at": now_iso,
                            "basis": None, "time_kind": None, "close_qualified": False}


def test_legacy_float_injection_keeps_old_labels(sandbox):
    now = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)
    res = M.mark_symbols(["AAPL", "MSFT"], "2026-10-20",
                         polygon_fn=lambda s: {"AAPL": 101.0}.get(s),
                         yahoo_fn=lambda s, a: {"MSFT": 99.0}.get(s),
                         persist=False, now=now)
    a = res["sources"]["AAPL"]
    assert a["source"] == "polygon-eod"
    assert a["stale_days"] == 0
    assert a["basis"] == "unknown"
    assert a["close_qualified"] is False
    m = res["sources"]["MSFT"]
    assert m["source"] == "yahoo-parquet"
    assert m["stale_days"] == 0
    assert m["basis"] == "unknown"
    assert m["close_qualified"] is False


def test_future_injected_observation_is_ineligible(sandbox):
    now = datetime(2026, 10, 20, 22, 0, tzinfo=timezone.utc)
    future = {"price": 120.0, "observed_asof": "2026-10-25", "basis": "raw",
              "time_kind": "session_close", "close_qualified": True}
    res = M.mark_symbols(["AAPL"], "2026-10-20", polygon_fn=lambda s: future,
                         yahoo_fn=lambda s, a: 99.0, persist=False, now=now)
    assert res["sources"]["AAPL"]["source"] == "yahoo-parquet"   # fell through
    assert res["prices"]["AAPL"] == pytest.approx(99.0)


# ── data_layer.polygon raw/adjusted split (I) ────────────────────────────────
def test_daily_closes_raw_vs_adjusted_cache_names(tmp_path, monkeypatch):
    from data_layer import polygon

    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    monkeypatch.setattr(polygon, "_aggs_cache_dir", lambda: tmp_path)
    sent = []

    class _Resp:
        ok = True

        @staticmethod
        def json():
            ts_ms = int(datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)
            return {"results": [{"t": ts_ms, "c": 100.0}]}

    def fake_get(_url, params=None, timeout=None):
        sent.append(params)
        return _Resp()

    monkeypatch.setattr("requests.get", fake_get)

    out_raw = polygon.daily_closes("AAPL", "2026-10-20", "2026-10-20", cache=True, adjusted=False)
    assert out_raw == {"2026-10-20": 100.0}
    assert sent[-1]["adjusted"] == "false"
    assert (tmp_path / "AAPL_2026-10-20_2026-10-20_raw.json").exists()
    assert not (tmp_path / "AAPL_2026-10-20_2026-10-20.json").exists()

    out_adj = polygon.daily_closes("AAPL", "2026-10-20", "2026-10-20", cache=True)
    assert out_adj == {"2026-10-20": 100.0}
    assert sent[-1]["adjusted"] == "true"                # the default stays adjusted
    assert (tmp_path / "AAPL_2026-10-20_2026-10-20.json").exists()

    # a pre-existing ADJUSTED cache entry must never answer a RAW request
    (tmp_path / "AAPL_2026-10-20_2026-10-20_raw.json").unlink()
    (tmp_path / "AAPL_2026-10-20_2026-10-20.json").write_text(json.dumps({"2026-10-20": 555.0}))
    sent.clear()
    out_again = polygon.daily_closes("AAPL", "2026-10-20", "2026-10-20", cache=True, adjusted=False)
    assert out_again == {"2026-10-20": 100.0}            # re-fetched, not the 555.0 adjusted cache
    assert len(sent) == 1 and sent[0]["adjusted"] == "false"
