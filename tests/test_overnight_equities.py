"""Overnight equity quote boundary: never promote indicative, stale, or unverified data."""
from datetime import datetime, timedelta, timezone

from data_layer import overnight_equities as oq


def _reply(body, code=200):
    class Response:
        status_code = code
        def json(self):
            return body
    return Response()


def _now():
    return datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc)


def _bbo(now=None):
    now = now or _now()
    return {"quote": {"bp": 100.0, "ap": 100.25, "bs": 50, "as": 100,
                      "t": now.isoformat()}}


def _configure(monkeypatch, *, firm=False, paper=False):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test_id")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test_secret")
    monkeypatch.setenv("MASTERMIND_ALPACA_BOATS_REALTIME_CONFIRMED", "1" if firm else "0")
    monkeypatch.setenv("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED", "1" if paper else "0")


def test_no_credentials_yields_no_quote_and_no_fill(monkeypatch):
    for key in ("ALPACA_API_KEY_ID", "APCA_API_KEY_ID",
                "ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert oq.latest("AAPL", now=_now(), include_eligibility=True)["status"] == "not_configured"


def test_indicative_feed_must_not_fill(monkeypatch):
    _configure(monkeypatch, firm=False, paper=True)
    requests = []
    def get(url, headers=None, params=None, timeout=None):
        requests.append((url, params))
        return _reply(_bbo())
    monkeypatch.setattr(oq.requests, "get", get)
    got = oq.latest("AAPL", now=_now(), include_eligibility=True)
    assert got["status"] == "indicative"
    assert got["fresh"] and got["mid"] == 100.125
    assert got["executable"] is False and got["indicative"] is True
    assert len(requests) == 1 and requests[0][1]["feed"] == "overnight"


def test_firm_live_and_eligible_requires_two_explicit_flags(monkeypatch):
    _configure(monkeypatch, firm=True, paper=True)
    def get(url, headers=None, params=None, timeout=None):
        if "/assets/" in url:
            return _reply({"status": "active", "class": "us_equity",
                           "tradable": True, "attributes": ["overnight_tradable"]})
        return _reply(_bbo())
    monkeypatch.setattr(oq.requests, "get", get)
    got = oq.latest("AAPL", now=_now(), include_eligibility=True)
    assert got["feed"] == "boats" and got["executable"] is True
    assert got["eligible"] is True and got["indicative"] is False
    monkeypatch.setenv("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED", "0")
    assert oq.latest("AAPL", now=_now(), include_eligibility=True)["executable"] is False


def test_halted_asset_rejected(monkeypatch):
    _configure(monkeypatch, firm=True, paper=True)
    def get(url, headers=None, params=None, timeout=None):
        return (_reply({"status": "active", "class": "us_equity", "tradable": True,
                        "attributes": ["overnight_tradable", "overnight_halted"]})
                if "/assets/" in url else _reply(_bbo()))
    monkeypatch.setattr(oq.requests, "get", get)
    got = oq.latest("AAPL", now=_now(), include_eligibility=True)
    assert got["status"] == "ineligible_or_halted" and got["executable"] is False


def test_stale_and_future_quotes_never_fill(monkeypatch):
    _configure(monkeypatch, firm=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **k: _reply(_bbo(_now() - timedelta(minutes=15))))
    got = oq.latest("AAPL", now=_now(), include_eligibility=True)
    assert not got["fresh"] and not got["executable"] and got["status"] == "stale"
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **k: _reply(_bbo(_now() + timedelta(minutes=1))))
    assert not oq.latest("AAPL", now=_now())["fresh"]


def test_bad_price_spread_size_and_unsafe_symbol_fail_closed(monkeypatch):
    _configure(monkeypatch, firm=True, paper=True)
    calls = []
    def get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        if "/assets/" in url:
            return _reply({"status": "active", "class": "us_equity",
                           "tradable": True, "attributes": ["overnight_tradable"]})
        raw = _bbo()
        raw["quote"]["ap"] = 200
        raw["quote"]["as"] = 0
        return _reply(raw)
    monkeypatch.setattr(oq.requests, "get", get)
    assert oq.latest("AAPL", now=_now(), include_eligibility=True)["status"] == "invalid_quote"
    assert not oq.latest("../orders", now=_now())["executable"]
    assert len(calls) == 1


def test_failed_request_never_exposes_secret(monkeypatch):
    _configure(monkeypatch, firm=True, paper=True)
    def bad_get(*args, **kwargs):
        raise RuntimeError("sensitive test_secret in error")
    monkeypatch.setattr(oq.requests, "get", bad_get)
    result = oq.latest("AAPL", now=_now(), include_eligibility=True)
    assert result["status"] == "feed_unavailable" and "test_secret" not in str(result)
