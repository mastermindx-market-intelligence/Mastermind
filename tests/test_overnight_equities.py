"""Tiingo BOATS adapter: venue timestamps, licensing and execution fail-closed."""
from datetime import datetime, timedelta, timezone

import pytest

from data_layer import overnight_equities as oq


def _reply(body, code=200):
    class Response:
        status_code = code

        def json(self):
            return body
    return Response()


def _now():
    return datetime(2026, 10, 9, 2, 0, tzinfo=timezone.utc)


def _boat_quote(**overrides):
    quote = {
        "ticker": "AAPL",
        "timestamp": "2026-10-09T02:00:00Z",
        "quoteTimestamp": "2026-10-08T22:00:00-04:00",
        "lastSaleTimestamp": "2026-10-08T21:59:59-04:00",
        "bidPrice": 100.0, "askPrice": 100.25,
        "mid": 100.125, "bidSize": 50, "askSize": 100,
        "last": 100.10, "lastSize": 25, "volume": 2500,
    }
    quote.update(overrides)
    return [quote]


def _configure(monkeypatch, *, display=False, non_display=False,
               paper=False, token=True):
    if token:
        monkeypatch.setenv("TIINGO_API_KEY", "test_private_tiingo_token")
    else:
        for k in ("TIINGO_API_KEY", "TIINGO_API_TOKEN", "TIINGO_TOKEN"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MASTERMIND_TIINGO_BOATS_DISPLAY_AUTHORIZED",
                       "1" if display else "0")
    monkeypatch.setenv("MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED",
                       "1" if non_display else "0")
    monkeypatch.setenv("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED",
                       "1" if paper else "0")


def test_unverified_display_license_prevents_all_provider_network(monkeypatch):
    _configure(monkeypatch, display=False, non_display=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: pytest.fail("display must not call Tiingo"))
    got = oq.latest("AAPL", now=_now(), purpose="display")
    assert got["status"] == "display_license_unverified"
    assert got["bid"] is None and not got["fresh"] and not got["executable"]


@pytest.mark.parametrize("display,non_display,paper,expected", [
    (False, True, True, "display_license_unverified"),
    (True, False, True, "non_display_license_unverified"),
    (True, True, False, "paper_fills_disabled"),
])
def test_paper_execution_requires_all_customer_facing_operator_gates(
        monkeypatch, display, non_display, paper, expected):
    _configure(monkeypatch, display=display, non_display=non_display, paper=paper)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: pytest.fail("paper hold must not call provider"))
    got = oq.latest("AAPL", now=_now(), purpose="execution", include_eligibility=True)
    assert got["status"] == expected and not got["executable"]


def test_missing_token_no_quote_and_no_fill(monkeypatch):
    _configure(monkeypatch, display=True, non_display=True, paper=True, token=False)
    monkeypatch.setattr(oq.requests, "get", lambda *a, **kw: pytest.fail("no token"))
    got = oq.latest("AAPL", now=_now(), purpose="execution", include_eligibility=True)
    assert got["status"] == "not_configured" and not got["executable"]


def test_tiingo_real_boats_payload_snapshot_get_header_and_display(monkeypatch):
    _configure(monkeypatch, display=True)
    called = []
    def fake_get(url, headers=None, timeout=None):
        called.append((url, headers, timeout))
        return _reply(_boat_quote())
    monkeypatch.setattr(oq.requests, "get", fake_get)
    got = oq.latest("AAPL", now=_now(), purpose="display", include_eligibility=True)
    assert got["provider"] == "tiingo" and got["venue"] == "BOATS"
    assert got["bid"] == 100 and got["ask"] == 100.25 and got["mid"] == 100.125
    assert got["bid_size"] == 50 and got["ask_size"] == 100
    assert got["last"] == 100.10 and got["last_size"] == 25
    assert got["fresh"] and got["status"] == "realtime_boats"
    assert got["executable"] is False and got["indicative"] is False
    assert called == [("https://api.tiingo.com/boats/aapl", {
        "Authorization": "Token test_private_tiingo_token",
        "Accept": "application/json",
    }, 4)]
    assert "test_private_tiingo_token" not in str(got)


def test_paper_execution_uses_same_tiingo_read_only_get(monkeypatch):
    _configure(monkeypatch, display=True, non_display=True, paper=True)
    seen = []
    def fake_get(url, headers=None, timeout=None):
        seen.append(url)
        return _reply(_boat_quote())
    monkeypatch.setattr(oq.requests, "get", fake_get)
    got = oq.latest("AAPL", now=_now(), purpose="execution", include_eligibility=True)
    assert got["executable"] is True and got["eligible"] is True
    assert seen == ["https://api.tiingo.com/boats/aapl"]
    assert "alpaca" not in str(got).lower()


def test_live_quote_requires_last_venue_quote_timestamp_not_refresh_time(monkeypatch):
    _configure(monkeypatch, display=True)
    # A later response update and a recent trade DO NOT freshen stale bid/ask.
    old = (_now() - timedelta(minutes=18)).isoformat()
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply(_boat_quote(
                            quoteTimestamp=old,
                            timestamp=_now().isoformat(),
                            lastSaleTimestamp=_now().isoformat())))
    got = oq.latest("AAPL", now=_now(), purpose="display")
    assert got["status"] == "stale" and not got["fresh"]
    assert got["quoted_at"] != got["last_trade_at"]


def test_missing_quote_timestamp_cannot_be_replaced_by_refresh_timestamp(monkeypatch):
    _configure(monkeypatch, display=True, non_display=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply(_boat_quote(quoteTimestamp=None)))
    got = oq.latest("AAPL", now=_now(), purpose="execution", include_eligibility=True)
    assert not got["fresh"] and not got["executable"] and got["status"] == "stale"


@pytest.mark.parametrize("bad_fields", [
    {"bidPrice": None}, {"askPrice": 0},
    {"bidPrice": 101.0, "askPrice": 100.0},
    {"askPrice": 200.0}, {"bidSize": 0}, {"askSize": None},
    {"quoteTimestamp": "bad-timestamp"},
    {"quoteTimestamp": "2026-10-09T03:00:00Z"},
])
def test_invalid_spread_liquidity_and_future_timestamp_fail_closed(monkeypatch, bad_fields):
    _configure(monkeypatch, display=True, non_display=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply(_boat_quote(**bad_fields)))
    got = oq.latest("AAPL", now=_now(), purpose="execution", include_eligibility=True)
    assert not got["fresh"] and not got["executable"]


@pytest.mark.parametrize("code,expected", [
    (401, "entitlement_required"),
    (402, "entitlement_required"),
    (403, "entitlement_required"),
    (404, "symbol_not_quoted"),
    (429, "rate_limited"),
    (500, "provider_unavailable"),
])
def test_provider_denials_and_rate_limits_no_fake_price(monkeypatch, code, expected):
    _configure(monkeypatch, display=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply({"secret": "must-never-echo"}, code))
    got = oq.latest("AAPL", now=_now(), purpose="display")
    assert got["status"] == expected and got["bid"] is None
    assert "secret" not in str(got)


@pytest.mark.parametrize("body,expected", [
    ([], "no_overnight_snapshot"),
    ([{"ticker": "MSFT"}], "ticker_mismatch"),
    ([{"ticker": "AAPL"}, {"ticker": "AAPL"}], "no_overnight_snapshot"),
    ("garbage", "invalid_provider_payload"),
])
def test_bad_payload_and_ticker_mismatch_never_cross_book(monkeypatch, body, expected):
    _configure(monkeypatch, display=True)
    monkeypatch.setattr(oq.requests, "get", lambda *a, **kw: _reply(body))
    assert oq.latest("AAPL", now=_now())["status"] == expected


def test_no_unsanitized_exception_or_path_injection(monkeypatch):
    _configure(monkeypatch, display=True)
    called = []
    def fails(*args, **kwargs):
        called.append(args)
        raise RuntimeError("test_private_tiingo_token secret in upstream exception")
    monkeypatch.setattr(oq.requests, "get", fails)
    unsafe = oq.latest("../orders", now=_now())
    assert unsafe["status"] == "invalid_symbol" and called == []
    clean = oq.latest("AAPL", now=_now())
    assert clean["status"] == "provider_unavailable"
    assert "test_private_tiingo_token" not in str(clean)


def test_tiingo_dict_response_is_accepted_when_symbol_matches(monkeypatch):
    _configure(monkeypatch, display=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply(_boat_quote()[0]))
    assert oq.latest("AAPL", now=_now())["fresh"] is True


def test_unknown_usage_purpose_fails_closed(monkeypatch):
    _configure(monkeypatch, display=True, non_display=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: pytest.fail("unknown usage"))
    assert oq.latest("AAPL", purpose="replay")["status"] == "invalid_purpose"


def test_real_ticket_quote_path_hides_tiingo_without_display_license(monkeypatch):
    """User-visible /self quote contract never exposes raw BOATS without rights."""
    from portfolio import self_directed as sd
    from data_layer import polygon
    monkeypatch.setattr(sd, "_market_status",
                        lambda: {"session": "overnight", "is_open": False})
    monkeypatch.setattr(sd, "_current_price", lambda ticker: 90.0)
    monkeypatch.setattr(polygon, "ticker_details", lambda ticker: None)
    _configure(monkeypatch, display=False, non_display=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: pytest.fail("customer API must not read unlicensed quotes"))
    got = sd.quote_info("AAPL")
    assert got["price"] == 90.0
    assert got["price_source"] == "regular_or_last_known"
    assert got["overnight"]["status"] == "display_license_unverified"
    assert got["overnight"]["bid"] is None


def test_real_ticket_quote_path_marks_only_licensed_tiingo_boats(monkeypatch):
    """The public API changes its mark only after a licensed live BOATS BBO."""
    from portfolio import self_directed as sd
    from data_layer import polygon
    monkeypatch.setattr(sd, "_market_status",
                        lambda: {"session": "overnight", "is_open": False})
    monkeypatch.setattr(sd, "_current_price", lambda ticker: 90.0)
    monkeypatch.setattr(polygon, "ticker_details", lambda ticker: {"name": "Apple"})
    _configure(monkeypatch, display=True)
    stamp = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply(_boat_quote(quoteTimestamp=stamp)))
    got = sd.quote_info("AAPL")
    assert got["price"] == 100.125
    assert got["price_source"] == "tiingo_boats_bbo_mid"
    assert got["overnight"]["provider"] == "tiingo"
    assert got["overnight"]["executable"] is False  # only approved non-display may fill


def test_customer_quote_enables_ticket_only_when_all_license_gates_are_armed(monkeypatch):
    """Display-grade quote is not a fill; it can enable a *rechecked* limit ticket."""
    _configure(monkeypatch, display=True, non_display=True, paper=True)
    monkeypatch.setattr(oq.requests, "get",
                        lambda *a, **kw: _reply(_boat_quote()))
    live = oq.latest("AAPL", now=_now(), purpose="display", include_eligibility=True)
    assert live["fresh"] is True and live["executable"] is True
    # Reading portfolio marks is never itself an order.
    preview = oq.latest("AAPL", now=_now(), purpose="display", include_eligibility=False)
    assert preview["fresh"] and not preview["executable"]
    monkeypatch.setenv("MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED", "0")
    display_only = oq.latest("AAPL", now=_now(), purpose="display", include_eligibility=True)
    assert display_only["fresh"] is True and not display_only["executable"]
    monkeypatch.setenv("MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED", "1")
    monkeypatch.setenv("MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED", "0")
    held = oq.latest("AAPL", now=_now(), purpose="display", include_eligibility=True)
    assert held["fresh"] and not held["executable"]


def test_tiingo_class_share_symbology_maps_dot_to_vendor_hyphen(monkeypatch):
    _configure(monkeypatch, display=True)
    urls = []
    def mock_get(url, headers=None, timeout=None):
        urls.append(url)
        return _reply(_boat_quote(ticker="BRK-B"))
    monkeypatch.setattr(oq.requests, "get", mock_get)
    result = oq.latest("BRK.B", now=_now(), purpose="display")
    assert result["ticker"] == "BRK.B" and result["fresh"] is True
    assert urls == ["https://api.tiingo.com/boats/brk-b"]
