"""Portfolio switcher badges preserve partial/unavailable quick-status truth."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def test_self_directed_unknown_valuation_stays_null_and_partial(monkeypatch):
    from app import web
    from brain import benchmark_ledger
    from portfolio import registry, self_directed

    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {"AAPL": {}}})
    monkeypatch.setattr(web, "_live_prices", lambda _held, refresh=False: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kwargs: {
        "nav": None,
        "inception_date": "2026-09-01",
        "valuation_complete": False,
        "unpriced_tickers": ["AAPL"],
        "positions": [{"ticker": "AAPL"}],
        "allocation": {"cash_pct": None, "total_return_pct": None, "n_positions": 1},
    })
    monkeypatch.setattr(benchmark_ledger, "latest", lambda: {"bogeys": {}})

    row = web._portfolio_status(registry.get("self_directed"))
    status = row["status"]
    assert status["cash_pct"] is None
    assert status["holdings"] == 1
    assert status["nav"] is None
    assert status["valuation_complete"] is False
    assert status["unpriced_tickers"] == ["AAPL"]
    assert status["read_status"] == "partial"
    assert status["status_reasons"] == ["valuation_incomplete"]


def test_self_directed_book_failure_is_unavailable_not_zero(monkeypatch):
    from app import web
    from brain import benchmark_ledger
    from portfolio import registry, self_directed

    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {"AAPL": {}}})
    monkeypatch.setattr(web, "_live_prices", lambda _held, refresh=False: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(benchmark_ledger, "latest", lambda: {"bogeys": {}})

    status = web._portfolio_status(registry.get("self_directed"))["status"]
    assert status["read_status"] == "unavailable"
    assert status["failed_sources"] == ["book"]
    assert status["nav"] is None
    assert status["holdings"] is None
    assert status["cash_pct"] is None


def test_managed_performance_failure_preserves_snapshot_as_partial(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    (tmp_path / "latest.json").write_text(json.dumps({"as_of": "2026-09-17", "positions": [{}, {}]}))
    monkeypatch.setattr(registry, "data_dir", lambda _pid: tmp_path)
    monkeypatch.setattr(web, "_book_marks", lambda _pid, refresh=False: {})
    monkeypatch.setattr(paper_account, "performance", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    status = web._portfolio_status(registry.get("autonomous"))["status"]
    assert status["read_status"] == "partial"
    assert status["failed_sources"] == ["performance"]
    assert status["nav"] is None
    assert status["holdings"] == 2
    assert status["as_of"] == "2026-09-17"


def test_managed_corrupt_snapshot_preserves_performance_as_partial(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    (tmp_path / "latest.json").write_text("{bad-json")
    monkeypatch.setattr(registry, "data_dir", lambda _pid: tmp_path)
    monkeypatch.setattr(web, "_book_marks", lambda _pid, refresh=False: {})
    monkeypatch.setattr(paper_account, "performance", lambda **_kwargs: {
        "current_nav": 1_010_000.0, "total_return_pct": 1.0,
        "vs_benchmark_pct": 0.2, "vs_spy_pct": 0.2,
        "day_change_pct": 0.1, "cash": 100_000.0, "realized_since": "2026-09-01",
    })

    status = web._portfolio_status(registry.get("autonomous"))["status"]
    assert status["read_status"] == "partial"
    assert status["failed_sources"] == ["snapshot"]
    assert status["nav"] == 1_010_000.0
    assert status["holdings"] is None


def test_degraded_rows_are_not_cached(monkeypatch):
    from app import web
    from portfolio import registry

    web._portfolios_cache.clear()
    meta = registry.get("autonomous")
    monkeypatch.setattr(registry, "all_portfolios", lambda: [meta])
    monkeypatch.setattr(web, "_portfolio_status", lambda _meta: {
        "id": "autonomous", "status": {"read_status": "partial", "nav": None}
    })
    payload = _body(web.api_portfolios())
    assert payload["portfolios"][0]["status"]["read_status"] == "partial"
    assert "payload" not in web._portfolios_cache


def test_full_rows_remain_cacheable(monkeypatch):
    from app import web
    from portfolio import registry

    web._portfolios_cache.clear()
    meta = registry.get("autonomous")
    monkeypatch.setattr(registry, "all_portfolios", lambda: [meta])
    monkeypatch.setattr(web, "_portfolio_status", lambda _meta: {
        "id": "autonomous", "status": {"read_status": "available", "nav": 1_000_000.0}
    })
    _body(web.api_portfolios())
    assert "payload" in web._portfolios_cache


def test_portfolios_outer_failure_is_closed(monkeypatch):
    from app import web
    from portfolio import registry

    web._portfolios_cache.clear()
    monkeypatch.setattr(registry, "all_portfolios", lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/registry")))
    response = web.api_portfolios()
    payload = _body(response)
    assert response.status_code == 503
    assert payload["read_status"] == "unavailable"
    assert payload["portfolios"] is None
    assert payload["error"] == "portfolios_unavailable"
    assert "secret" not in response.body.decode()


def test_switcher_renders_partial_and_unavailable_labels():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("function renderPortfolioSwitch()")
    end = html.index("function revealActivePortfolioTab", start)
    block = html[start:end]
    assert "st.read_status === 'partial'" in block
    assert "st.read_status === 'unavailable'" in block
    assert "PARTIAL" in block
    assert "UNAVAILABLE" in block
    assert "_portfoliosStatus === 'unavailable'" in block
    assert "Portfolios unavailable" in block

    load_start = html.index("async function loadPortfolios()")
    load_end = html.index("// ── AUTONOMOUS BOOK", load_start)
    load = html[load_start:load_end]
    assert "_portfoliosStatus = 'unavailable'" in load
    assert "renderPortfolioSwitch();" in load
