"""Static contracts that prevent mixed-owner portfolio state during phased hydration."""
from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "app" / "static" / "index.html").read_text()


def _slice(start: str, end: str) -> str:
    begin = HTML.index(start)
    return HTML[begin:HTML.index(end, begin)]


def test_cross_book_switch_hides_previous_owner_before_critical_read() -> None:
    switch = _slice("window.setPortfolio = function(id)", "async function loadPortfolios()")
    assert 'class="page-mm mm-pf-scope-loading"' in HTML
    assert 'id="portfolio-scope-state"' in HTML
    assert "function _setPortfolioScopeState(state)" in HTML
    assert "function _resetPortfolioScopedState()" in HTML
    assert "_setPortfolioScopeState('loading')" in switch
    assert "_resetPortfolioScopedState()" in switch
    assert switch.index("_setPortfolioScopeState('loading')") < switch.index("_portfolio = id;")
    assert switch.index("_resetPortfolioScopedState()") < switch.index("_portfolio = id;")


def test_critical_snapshot_rebinds_every_detail_panel_before_reveal() -> None:
    critical = _slice("function _fetchPortfolioCritical(id)", "function _fetchPortfolioDetails(id, base)")
    paint = _slice("function _paintPortfolioSnapshot(snapshot, requestLive)", "function _schedulePortfolioPrefetch()")

    assert "criticalStatus: book ? 'ready' : 'unavailable'" in critical
    assert "trades: _tradesLoading()" in critical
    assert "risk: _riskLoading()" in critical
    assert "performance: _performanceLoading()" in critical
    assert "decisionsStatus: 'loading'" in critical

    assert "snapshot.portfolio !== _portfolio" in paint
    assert "snapshot.criticalStatus === 'unavailable'" in paint
    assert "_portfolioScopeState === 'ready' || _portfolioScopeState === 'stale'" in paint
    assert "_applyPortfolioSnapshot(snapshot);" in paint
    assert "_setPortfolioScopeState('ready')" in paint
    assert paint.index("_applyPortfolioSnapshot(snapshot);") < paint.index("_setPortfolioScopeState('ready')")


def test_detail_transport_failure_stays_unavailable_not_empty() -> None:
    details = _slice("function _fetchPortfolioDetails(id, base)", "function _fetchPortfolioSnapshot(id)")
    assert "_tradesUnavailable()" in details
    assert "_performanceUnavailable()" in details
    assert "_riskUnavailable()" in details

    trades = _slice("function renderTrades()", "window.tradesPage")
    safety = _slice("function renderSafety()", "function renderPositions()")
    perf = _slice("function renderPerformance()", "function renderEquityCurve()")
    curve = _slice("function renderEquityCurve()", "function renderAllocation()")

    assert "snapshot_status === 'loading'" in trades
    assert trades.index("snapshot_status === 'loading'") < trades.index("var hist =")
    assert "report_status === 'loading'" in safety
    assert "load_status === 'loading'" in perf
    assert "series_status === 'loading'" in curve


def test_failed_revalidation_preserves_last_good_cache() -> None:
    fetch_all = _slice("async function fetchAll(opts)", "// ── langchange")
    failed = "scopedSnapshot && scopedSnapshot.criticalStatus === 'unavailable'"
    cache_write = "_portfolioDataCache[requestedPortfolio] = scopedSnapshot;"
    assert failed in fetch_all
    assert fetch_all.index(failed) < fetch_all.index(cache_write)

    paint = _slice("function _paintPortfolioSnapshot(snapshot, requestLive)", "function _schedulePortfolioPrefetch()")
    assert "_portfolioScopeState === 'stale'" in paint
