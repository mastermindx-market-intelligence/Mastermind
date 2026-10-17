"""Market-data absence must never be labeled a reassuring overnight signal.

All fixtures are synthetic and offline; no trading, quote-provider call, or
portfolio write is permitted by these tests.
"""
from __future__ import annotations

import pytest


def test_no_risk_signals_is_unknown_not_calm():
    from data_layer import overnight as source
    result = source.risk_read({})
    assert result["state"] == "unknown"
    assert result["reasons"] == ["no qualified overnight risk signals"]
    assert result["futures_avg_pct"] is None
    assert result["intl_avg_pct"] is None
    assert source.is_material({"risk": result}) is False


def test_crypto_only_cannot_be_marked_overnight_risk_calm(monkeypatch):
    from data_layer import overnight as source
    monkeypatch.setattr(source, "_fetch_changes", lambda _symbols: {
        "BTC-USD": {"price": 70000.0, "prev": 68000.0, "change_pct": 2.94},
    })
    source.clear_cache()
    report = source.tape(force=True)
    assert report["n_symbols"] == 1
    assert report["live"] is False
    assert report["source_quality"]["classification"] == "EOD_NOT_LIVE"
    assert report["risk"]["state"] == "unknown"
    assert report["risk"]["reasons"] == ["no qualified overnight risk signals"]
    assert source.is_material(report) is False
    source.clear_cache()


def test_partial_qualified_us_signal_remains_calm_when_nonmaterial():
    from data_layer import overnight as source
    result = source.risk_read({
        "us_futures": [{"ticker": "ES=F", "change_pct": 0.2}],
        "international": [], "vol": [],
    })
    assert result["state"] == "calm"
    assert source.is_material({"risk": result}) is False


@pytest.mark.parametrize("force", [False, True])
def test_overnight_watch_does_not_redecide_on_missing_risk_evidence(
    monkeypatch, force,
):
    from bot import overnight as watcher, settle, autonomous, derisk
    from data_layer import overnight as source
    from portfolio import registry, autonomous_migration, paper_account

    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    monkeypatch.setattr(autonomous_migration, "is_pending_migration", lambda: False)
    monkeypatch.setattr(settle, "is_open", lambda _pid: False)
    monkeypatch.setattr(paper_account, "preflight_pending_target", lambda _pid: {
        "ok": True, "pending": True,
    })
    monkeypatch.setattr(derisk, "enabled", lambda: False)
    monkeypatch.setattr(source, "tape", lambda force=False: {
        "live": False, "groups": {}, "risk": {
            "state": "unknown", "reasons": ["no qualified overnight risk signals"],
        },
    })

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError("unknown risk must never be sent as a live tape")

    monkeypatch.setattr(autonomous, "run_autonomous", _must_not_run)
    result = watcher.watch("autonomous", "2026-10-15", force=force)
    assert result["skipped"] == "tape_unavailable"
    assert result["overnight_risk"] == "unknown"
    assert "refined" not in result
    assert "error" not in result


@pytest.mark.parametrize("bad_change", [float("nan"), float("inf"), float("-inf"), True, "-0.8"])
def test_nonfinite_or_untyped_provider_changes_are_not_calming_evidence(bad_change):
    from data_layer import overnight as source
    result = source.risk_read({
        "us_futures": [{"ticker": "ES=F", "change_pct": bad_change}],
        "international": [{"ticker": "^N225", "change_pct": None}],
        "vol": [{"ticker": "^VIX", "change_pct": bad_change}],
    })
    assert result["state"] == "unknown"
    assert result["intl_n"] == 0
    assert result["futures_avg_pct"] is None
    assert result["vix_change_pct"] is None


def test_exact_zero_is_qualified_calm_and_not_unknown():
    from data_layer import overnight as source
    result = source.risk_read({
        "us_futures": [{"ticker": "ES=F", "change_pct": 0.0}],
        "vol": [{"ticker": "^VIX", "change_pct": 0}],
    })
    assert result["state"] == "calm"
    assert result["futures_avg_pct"] == 0.0
    assert result["vix_change_pct"] == 0.0


def test_dashboard_overnight_api_exception_never_reports_calm_or_leaks_provider_text(monkeypatch):
    import json

    from app import web
    from data_layer import overnight as source

    sensitive = "internal data path /private/market-data and bearer eyJsyntheticsecret"

    def _failed():
        raise RuntimeError(sensitive)

    monkeypatch.setattr(source, "tape", _failed)
    response = web.api_overnight_tape()
    document = json.loads(response.body)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert document["risk"]["state"] == "unknown"
    assert document["live"] is False
    assert document["error"] == "overnight_source_unavailable"
    assert sensitive not in response.body.decode()


def test_dashboard_overnight_api_distinguishes_empty_but_valid_read(monkeypatch):
    import json

    from app import web
    from data_layer import overnight as source

    monkeypatch.setattr(source, "tape", lambda: {
        "groups": {}, "risk": {"state": "unknown", "reasons": [
            "no qualified overnight risk signals"
        ]}, "live": False, "n_symbols": 0,
    })
    response = web.api_overnight_tape()
    data = json.loads(response.body)
    assert response.status_code == 200
    assert data["risk"]["state"] == "unknown"
    assert data["n_symbols"] == 0


def test_daily_yahoo_history_cannot_be_promoted_to_live_overnight_risk(monkeypatch):
    from data_layer import overnight as source

    # A dramatic *daily* close-to-close move is not a qualified overnight
    # observation. The true economic overnight feed has not been admitted.
    monkeypatch.setattr(source, "_fetch_changes", lambda _symbols: {
        "ES=F": {"price": 5200.0, "prev": 5400.0, "change_pct": -3.7},
        "^VIX": {"price": 27.0, "prev": 21.0, "change_pct": 28.6},
    })
    source.clear_cache()
    report = source.tape(force=True)
    assert report["n_symbols"] == 2
    assert report["groups"]["us_futures"][0]["change_pct"] == -3.7
    assert report["live"] is False
    assert report["risk"]["state"] == "unknown"
    assert report["source_quality"]["classification"] == "EOD_NOT_LIVE"
    assert source.is_material(report) is False
    source.clear_cache()


def test_indicative_daily_stress_can_never_trigger_material_redecision():
    from data_layer import overnight as source
    historical = {
        "live": False,
        "risk": {"state": "stressed", "reasons": ["prior daily close was down"]},
        "source_quality": {"classification": "EOD_NOT_LIVE"},
    }
    assert source.is_material(historical) is False


def test_historical_yahoo_fetch_explicitly_declares_daily_resolution(monkeypatch):
    import sys
    from types import SimpleNamespace

    from data_layer import overnight as source
    calls = []

    class NoBars:
        def dropna(self):
            return []

    def guarded_download(symbols, **kwargs):
        calls.append((tuple(symbols), kwargs))
        return {"Close": NoBars()}

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=guarded_download))
    result = source._fetch_changes(["ES=F"])
    assert result == {}
    assert len(calls) == 1
    assert calls[0][1]["interval"] == "1d"
    assert calls[0][1]["period"] == "5d"
    assert calls[0][1]["threads"] is False
