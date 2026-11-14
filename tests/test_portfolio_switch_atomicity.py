"""Static contracts and executed behaviour for phased portfolio hydration.

The static contracts below pin the shape of the portfolio switcher state machine.
The behavioural tests execute the ACTUAL inline JavaScript taken from
``app/static/index.html`` inside an offline Node harness with a controlled network
and a minimal DOM. They never re-implement the implementation: every asserted
value is produced by the extracted candidate code, so a passing run is evidence
about the shipped script rather than about a copy of it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text()


def _slice(start: str, end: str) -> str:
    begin = HTML.index(start)
    return HTML[begin:HTML.index(end, begin)]


# ── static contracts ──────────────────────────────────────────────────────────


def test_cross_book_switch_hides_previous_owner_before_critical_read() -> None:
    switch = _slice("window.setPortfolio = function(id, opts)", "async function loadPortfolios()")
    assert 'class="page-mm mm-pf-scope-loading"' in HTML
    assert 'id="portfolio-scope-state"' in HTML
    assert "function _setPortfolioScopeState(state)" in HTML
    assert "function _invalidateBookScopedState()" in HTML
    assert "_setPortfolioScopeState('loading')" in switch
    assert "_invalidateBookScopedState()" in switch
    assert switch.index("_setPortfolioScopeState('loading')") < switch.index("_portfolio = id;")
    assert switch.index("_invalidateBookScopedState()") < switch.index("_portfolio = id;")


def test_critical_snapshot_rebinds_every_detail_panel_before_reveal() -> None:
    critical = _slice("function _fetchPortfolioCritical(id, onAvailability)", "function _fetchPortfolioDetails(id, base)")
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


def test_critical_failure_path_still_reaches_shared_hydration() -> None:
    """Structural guard complementing the executed behaviour below.

    The critical-unavailable branch must paint the truthful unavailable state and
    clear the loading bar BEFORE it reaches the singleton shared hydration, and it
    must not hoist that hydration above the critical first paint.
    """
    fetch_all = _slice("async function fetchAll(opts)", "// ── langchange")
    failed = "scopedSnapshot && scopedSnapshot.criticalStatus === 'unavailable'"
    begin = fetch_all.index(failed)
    end = fetch_all.index("_portfolioDataCache[requestedPortfolio] = scopedSnapshot;")
    branch = fetch_all[begin:end]
    assert "_paintPortfolioSnapshot(scopedSnapshot, false);" in branch
    assert "loadBarDone();" in branch
    assert "_hydrateShared();" in branch
    assert branch.index("_paintPortfolioSnapshot(scopedSnapshot, false);") < branch.index("_hydrateShared();")
    assert branch.index("loadBarDone();") < branch.index("_hydrateShared();")
    # The shared group stays behind the critical first paint on the success path too.
    success_hydration = fetch_all.rindex("_hydrateShared();")
    assert fetch_all.index("_portfolioDataCache[requestedPortfolio] = scopedSnapshot;") < success_hydration
    assert fetch_all.index("_portfolioDataCache[requestedPortfolio] = detailedSnapshot;") < success_hydration


def test_background_prefetch_never_stores_an_unavailable_envelope() -> None:
    """Structural guard complementing the executed behaviour below.

    The idle background prefetch must refuse an explicit critical-unavailable
    envelope, must not replace a cache entry another owner has taken over, and
    must not require a 'ready' criticalStatus (the self-directed critical branch
    carries no such field).
    """
    prefetch = _slice("function _schedulePortfolioPrefetch()", "function _scheduleWorkspacePrefetch()")
    assert "_portfolioDataCache[id] = snapshot;" in prefetch
    assert "snapshot.criticalStatus === 'unavailable'" in prefetch
    assert "current !== prior" in prefetch
    assert "criticalStatus === 'ready'" not in prefetch


# ── executed behaviour ────────────────────────────────────────────────────────


def _inline_script() -> str:
    """Return the page's inline portfolio JavaScript exactly as served."""
    hydration = HTML.index("async function fetchAll(opts)")
    start = HTML.rindex("<script>", 0, hydration)
    end = HTML.index("</script>", hydration)
    script = HTML[start + len("<script>"):end]
    for required in (
        "function _fetchPortfolioSnapshot(id)",
        "function _schedulePortfolioPrefetch()",
        "async function fetchAll(opts)",
        "function _hydrateShared()",
        "window.setPortfolio = function(id, opts)",
    ):
        assert required in script, f"inline script is missing {required!r}"
    return script


_HARNESS_JS = r"""
'use strict';
// Offline harness that executes the ACTUAL inline portfolio JavaScript taken from
// app/static/index.html inside a Node vm context with a controlled network and a
// minimal DOM. It never re-implements the implementation: every value the Python
// test asserts on is produced by the extracted candidate code.
const fs = require('fs');
const vm = require('vm');

const appPath = process.argv[2];
const scenarioNames = process.argv.slice(3);
const src = fs.readFileSync(appPath, 'utf8');

// ── minimal DOM ──────────────────────────────────────────────────────────────
function mkStyle() {
  const values = Object.create(null);
  return {
    setProperty(name, value) { values[name] = value; },
    removeProperty(name) { delete values[name]; },
    getPropertyValue(name) { return name in values ? values[name] : ''; },
  };
}
function mkEl(id) {
  return {
    id: id, innerHTML: '', textContent: '', className: '', value: '', style: mkStyle(),
    dataset: {}, children: [], scrollWidth: 0, clientWidth: 0, scrollLeft: 0,
    offsetLeft: 0, offsetWidth: 0,
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    setAttribute() {}, getAttribute() { return null; }, removeAttribute() {},
    appendChild() {}, removeChild() {}, addEventListener() {}, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; }, focus() {}, click() {}, scrollTo() {},
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
    insertAdjacentHTML() {},
  };
}

// ── network helpers ──────────────────────────────────────────────────────────
function okResponse(data) {
  return { ok: true, status: 200, json() { return Promise.resolve(data); } };
}
function parked() {
  return new Promise(function () {});
}
function deferred() {
  let resolve, reject;
  const promise = new Promise(function (res, rej) { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const tick = () => new Promise(function (r) { setImmediate(r); });
async function settle(rounds) {
  for (let i = 0; i < (rounds || 8); i += 1) await tick();
}

const BOOK_A = { id: 'bookA', name: 'Book A', kind: 'autonomous', currency: 'USD', tagline: 'A', status: { nav: 1000, total_return_pct: 1 } };
const BOOK_B = { id: 'bookB', name: 'Book B', kind: 'autonomous', currency: 'USD', tagline: 'B', status: { nav: 2000, total_return_pct: 2 } };
const SELF = { id: 'self_directed', name: 'Self', kind: 'self_directed', currency: 'USD', tagline: 'S', status: { nav: 500, total_return_pct: 0 } };

// Build a fresh context per scenario so no state leaks between them.
function buildContext(registry) {
  const elements = Object.create(null);
  const fetchLog = [];
  const callCounts = Object.create(null);
  const handlers = Object.create(null);
  let phase = 'boot';
  let timerFirings = 0;
  const TIMER_LIMIT = 50000;

  const document = {
    hidden: false,
    documentElement: { lang: 'en', getAttribute() { return 'en'; }, setAttribute() {}, style: {} },
    body: mkEl('body'),
    head: { appendChild() {} },
    getElementById(id) {
      if (!elements[id]) elements[id] = mkEl(id);
      return elements[id];
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    createElement() { return mkEl('created'); },
    addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
  };

  function setTimeoutStub(fn) {
    timerFirings += 1;
    if (timerFirings > TIMER_LIMIT) throw new Error('timer storm');
    Promise.resolve().then(function () { fn(); });
    return timerFirings;
  }

  function fetchStub(url) {
    const u = String(url);
    fetchLog.push(u);
    if (phase === 'boot') return parked();
    const n = callCounts[u] || 0;
    callCounts[u] = n + 1;
    const handler = handlers[u];
    if (handler) return handler(n, u);
    return Promise.resolve(okResponse([]));
  }

  const sandbox = {
    console: console,
    document: document,
    location: { pathname: '/dashboard', search: '', hash: '', href: 'http://localhost/dashboard' },
    localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    navigator: { language: 'en-US', clipboard: { writeText() { return Promise.resolve(); } } },
    history: { replaceState() {}, pushState() {} },
    fetch: fetchStub,
    setTimeout: setTimeoutStub,
    clearTimeout() {},
    setInterval() { return 0; },
    clearInterval() {},
    requestAnimationFrame(fn) { return setTimeoutStub(fn); },
    cancelAnimationFrame() {},
    requestIdleCallback(fn) { return setTimeoutStub(fn); },
    cancelIdleCallback() {},
    matchMedia() {
      return { matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} };
    },
    performance: { now() { return Date.now(); } },
    getComputedStyle() { return { getPropertyValue() { return ''; } }; },
    addEventListener() {}, removeEventListener() {},
    alert() {}, confirm() { return true; }, prompt() { return ''; },
    atob(s) { return Buffer.from(String(s), 'base64').toString('binary'); },
    btoa(s) { return Buffer.from(String(s), 'binary').toString('base64'); },
    URL: URL, TextEncoder: TextEncoder, TextDecoder: TextDecoder,
  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;

  const ctx = vm.createContext(sandbox);
  // A controlled clock makes cache timestamps deterministic and lets a scenario prove
  // that a stale completion did not extend the entry's freshness window.
  const clock = { t: 1750000000000 };
  ctx.__clock = clock;
  vm.runInContext('Date.now = function () { return __clock.t; };', ctx);
  vm.runInContext(src, ctx, { filename: 'mastermind-inline.js' });

  // The page's own bootstrap fired one fetchAll() while the script was evaluated.
  // Every request was parked, so it never resolved; reset the driven state.
  ctx._portfolio = 'autonomous';
  ctx._portfolios = [];
  ctx._portfolioDataCache = {};
  ctx._portfolioPrefetches = {};
  ctx._portfolioPrefetchStarted = false;
  ctx._workspacePrefetchStarted = false;
  ctx._sharedLoaded = false;
  ctx._sharedLoad = null;
  ctx._pfFetchSeq = 0;
  ctx._portfolioScopeState = 'loading';
  ctx._book = null;
  ctx._trades = null;
  ctx._perf = null;
  ctx._risk = null;
  ctx._decisions = [];
  ctx._decisionsStatus = 'loading';
  ctx._liveMarks = null;
  ctx._liveFetchSeq = 0;
  ctx._liveTimer = null;

  // The scenario owns the network from here on.
  phase = 'scenario';
  fetchLog.length = 0;

  // spy on fetchAll so switch-driven loads can be awaited
  const fetchAllPromises = [];
  const originalFetchAll = ctx.fetchAll;
  ctx.fetchAll = function (opts) {
    const promise = originalFetchAll(opts);
    fetchAllPromises.push(promise);
    return promise;
  };

  function route(url, handler) { handlers[url] = handler; }
  function installCommonRoutes() {
    route('/api/portfolios', function () { return Promise.resolve(okResponse(registry)); });
    ['/api/activity', '/api/research'].forEach(function (u) {
      route(u, function () { return Promise.resolve(okResponse([])); });
    });
    ['/api/shadow_books', '/api/predictions', '/api/engine_backtest', '/api/factor_zoo',
      '/api/fundamentals', '/api/student', '/api/distill'].forEach(function (u) {
      route(u, function () { return Promise.resolve(okResponse(null)); });
    });
    ['bookA', 'bookB', 'self_directed'].forEach(function (id) {
      route('/api/live_marks?portfolio=' + id, function () { return parked(); });
      route('/api/trades?portfolio=' + id, function () { return Promise.resolve(okResponse({ trades: [] })); });
      route('/api/performance?portfolio=' + id, function () { return Promise.resolve(okResponse({ series: [] })); });
      route('/api/decisions?portfolio=' + id, function () { return Promise.resolve(okResponse({ decisions: [] })); });
      route('/api/risk?portfolio=' + id, function () { return Promise.resolve(okResponse({ report: {} })); });
    });
    route('/api/self_directed', function () { return Promise.resolve(okResponse({ id: 'self_directed', nav: 500 })); });
    route('/api/self_directed/history', function () { return Promise.resolve(okResponse({ history: [] })); });
  }

  function countFetch(prefix) {
    return fetchLog.filter(function (u) { return u.indexOf(prefix) === 0; }).length;
  }
  function switcherHtml() {
    const el = document.getElementById('pf-switch');
    return el ? el.innerHTML : '';
  }
  function cacheEntry(id) {
    const entry = ctx._portfolioDataCache[id];
    if (!entry) return null;
    return {
      present: true,
      criticalStatus: entry.criticalStatus === undefined ? null : entry.criticalStatus,
      hasCriticalStatus: Object.prototype.hasOwnProperty.call(entry, 'criticalStatus'),
      cachedAt: entry.cachedAt === undefined ? null : entry.cachedAt,
      hasBook: Object.prototype.hasOwnProperty.call(entry, 'book'),
      bookId: entry.book && entry.book.id ? entry.book.id : null,
      hasSelf: Object.prototype.hasOwnProperty.call(entry, 'self'),
      complete: entry.complete === undefined ? null : entry.complete,
    };
  }
  async function lastFetchAll() {
    if (!fetchAllPromises.length) return;
    await fetchAllPromises[fetchAllPromises.length - 1];
  }

  return {
    ctx: ctx, document: document, fetchLog: fetchLog, route: route, clock: clock,
    installCommonRoutes: installCommonRoutes, countFetch: countFetch,
    switcherHtml: switcherHtml, cacheEntry: cacheEntry, lastFetchAll: lastFetchAll,
    okResponse: okResponse, parked: parked, deferred: deferred, settle: settle,
  };
}

// ── scenarios ────────────────────────────────────────────────────────────────

// A cold critical failure of the selected book must still reach the shared
// navigation hydration, exactly once, and must leave the scope visibly unavailable.
async function scenarioColdFailure() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.reject(new Error('critical read failed')); });
  h.route('/api/portfolio?portfolio=bookB', function (n) {
    // call 0 is the idle background prefetch (held); later calls are the foreground switch
    return n === 0 ? h.parked() : Promise.resolve(h.okResponse({ id: 'bookB', nav: 2000 }));
  });

  h.ctx._portfolio = 'bookA';
  const steps = [];

  await h.ctx.fetchAll({ showBar: true });
  await h.settle(10);
  steps.push({
    step: 'after-cold-failure',
    sharedRegistryFetches: h.countFetch('/api/portfolios'),
    sharedLoaded: h.ctx._sharedLoaded === true,
    sharedLoadInFlight: h.ctx._sharedLoad !== null,
    scopeState: h.ctx._portfolioScopeState,
    registryCount: h.ctx._portfolios.length,
    switcherHasBookA: h.switcherHtml().indexOf('data-pf="bookA"') !== -1,
    switcherHasBookB: h.switcherHtml().indexOf('data-pf="bookB"') !== -1,
  });

  // Join the shared singleton. On unrepaired bytes this call is what STARTS the
  // hydration, because the critical failure path never reached it.
  await h.ctx._hydrateShared();
  await h.settle(10);
  steps.push({
    step: 'after-shared-hydration',
    sharedRegistryFetches: h.countFetch('/api/portfolios'),
    sharedGroupFetches: h.countFetch('/api/activity'),
    sharedLoaded: h.ctx._sharedLoaded === true,
    scopeState: h.ctx._portfolioScopeState,
    registryCount: h.ctx._portfolios.length,
    switcherHasBookA: h.switcherHtml().indexOf('data-pf="bookA"') !== -1,
    switcherHasBookB: h.switcherHtml().indexOf('data-pf="bookB"') !== -1,
    selectedPortfolio: h.ctx._portfolio,
  });

  h.ctx.setPortfolio('bookB');
  await h.settle(3);
  await h.lastFetchAll();
  await h.settle(8);
  steps.push({
    step: 'after-selecting-healthy-book',
    scopeState: h.ctx._portfolioScopeState,
    selectedPortfolio: h.ctx._portfolio,
    bookLoaded: !!h.ctx._book,
    bookId: h.ctx._book && h.ctx._book.id ? h.ctx._book.id : null,
    cacheBookB: h.cacheEntry('bookB'),
    sharedRegistryFetches: h.countFetch('/api/portfolios'),
    sharedGroupFetches: h.countFetch('/api/activity'),
  });
  return { steps: steps, fetchLog: h.fetchLog.slice() };
}

// A background prefetch that fails late must not destroy newer foreground truth.
async function scenarioStaleBackground() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 })); });
  const backgroundBookB = h.deferred();
  h.route('/api/portfolio?portfolio=bookB', function (n) {
    if (n === 0) return backgroundBookB.promise;                              // held background prefetch
    if (n === 1) return Promise.resolve(h.okResponse({ id: 'bookB', nav: 2000 })); // foreground success
    return Promise.reject(new Error('revalidation failed'));                   // later revalidation fails
  });

  h.ctx._portfolio = 'bookA';
  const steps = [];

  await h.ctx.fetchAll({ showBar: true });
  await h.settle(10);
  steps.push({ step: 'cold-load', cacheBookB: h.cacheEntry('bookB') });

  h.ctx.setPortfolio('bookB');
  await h.settle(3);
  await h.lastFetchAll();
  await h.settle(8);
  const goodEntry = h.cacheEntry('bookB');
  steps.push({
    step: 'foreground-commit',
    cacheBookB: goodEntry,
    bookLoaded: !!h.ctx._book,
    bookId: h.ctx._book && h.ctx._book.id ? h.ctx._book.id : null,
  });

  // The held background prefetch now fails, late.
  h.clock.t += 1000;
  backgroundBookB.reject(new Error('background read failed'));
  await h.settle(10);
  const afterLateFailure = h.cacheEntry('bookB');
  steps.push({
    step: 'after-late-background-failure',
    cacheBookB: afterLateFailure,
    timestampPreserved: !!(goodEntry && afterLateFailure && goodEntry.cachedAt === afterLateFailure.cachedAt),
    truthPreserved: !!(afterLateFailure && afterLateFailure.criticalStatus === 'ready' && afterLateFailure.bookId === 'bookB'),
  });

  // Genuine revisit: switch away and back so the scoped state is reset first.
  h.clock.t += 1000;
  h.ctx.setPortfolio('bookA');
  await h.settle(3);
  await h.lastFetchAll();
  await h.settle(5);
  h.clock.t += 1000;
  h.ctx.setPortfolio('bookB');
  await h.settle(3);
  await h.lastFetchAll();
  await h.settle(8);
  steps.push({
    step: 'after-revisit-with-failed-revalidation',
    scopeState: h.ctx._portfolioScopeState,
    bookLoaded: !!h.ctx._book,
    bookId: h.ctx._book && h.ctx._book.id ? h.ctx._book.id : null,
    cacheBookB: h.cacheEntry('bookB'),
  });
  return { steps: steps, fetchLog: h.fetchLog.slice() };
}

// A successful background prefetch must still populate the cache.
async function scenarioUsefulPrefetch() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 })); });
  h.route('/api/portfolio?portfolio=bookB', function () { return Promise.resolve(h.okResponse({ id: 'bookB', nav: 2000 })); });

  h.ctx._portfolio = 'bookA';
  await h.ctx.fetchAll({ showBar: true });
  await h.settle(12);
  return {
    steps: [{ step: 'useful-prefetch', cacheBookB: h.cacheEntry('bookB'), bookLoaded: !!h.ctx._book }],
    fetchLog: h.fetchLog.slice(),
  };
}

// One in-flight prefetch per book, cleaned up after settlement.
async function scenarioCoalescing() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 })); });
  h.route('/api/portfolio?portfolio=bookB', function () { return Promise.resolve(h.okResponse({ id: 'bookB', nav: 2000 })); });

  h.ctx._portfolio = 'bookA';
  const first = h.ctx._fetchPortfolioSnapshot('bookB');
  const second = h.ctx._fetchPortfolioSnapshot('bookB');
  const coalesced = first === second;
  const inflightRegistered = !!h.ctx._portfolioPrefetches['bookB'];
  await first;
  await h.settle(6);
  return {
    steps: [{
      step: 'in-flight-coalescing',
      coalesced: coalesced,
      inflightRegistered: inflightRegistered,
      inflightCleanedUp: !h.ctx._portfolioPrefetches['bookB'],
      bookBCriticalReads: h.fetchLog.filter(function (u) { return u === '/api/portfolio?portfolio=bookB'; }).length,
    }],
    fetchLog: h.fetchLog.slice(),
  };
}

// The shared request group is a singleton.
async function scenarioSharedSingleton() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 })); });

  h.ctx._portfolio = 'bookA';
  const a = h.ctx._hydrateShared();
  const b = h.ctx._hydrateShared();
  const samePromise = a === b;
  await a;
  await h.settle(8);
  return {
    steps: [{
      step: 'shared-singleton',
      samePromise: samePromise,
      registryFetches: h.countFetch('/api/portfolios'),
      sharedGroupFetches: h.countFetch('/api/activity'),
      sharedLoaded: h.ctx._sharedLoaded === true,
    }],
    fetchLog: h.fetchLog.slice(),
  };
}

// An obsolete sequence must not repaint another book.
async function scenarioObsoleteSequence() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B] });
  h.installCommonRoutes();
  const heldBookA = h.deferred();
  h.route('/api/portfolio?portfolio=bookA', function (n) {
    return n === 0 ? heldBookA.promise : Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 }));
  });
  h.route('/api/portfolio?portfolio=bookB', function () { return Promise.resolve(h.okResponse({ id: 'bookB', nav: 2000 })); });

  h.ctx._portfolio = 'bookA';
  const obsolete = h.ctx.fetchAll({ showBar: true });
  await h.settle(4);

  h.ctx.setPortfolio('bookB');
  await h.settle(3);
  await h.lastFetchAll();
  await h.settle(8);
  const afterSwitch = {
    bookId: h.ctx._book && h.ctx._book.id ? h.ctx._book.id : null,
    portfolio: h.ctx._portfolio,
  };

  // Release the superseded bookA critical read.
  heldBookA.resolve(h.okResponse({ id: 'bookA', nav: 1000 }));
  await obsolete.catch(function () {});
  await h.settle(10);
  const afterRelease = {
    bookId: h.ctx._book && h.ctx._book.id ? h.ctx._book.id : null,
    portfolio: h.ctx._portfolio,
    scopeState: h.ctx._portfolioScopeState,
  };

  // A snapshot belonging to another book must never repaint the current one.
  await h.ctx._paintPortfolioSnapshot({ portfolio: 'bookA', book: { id: 'bookA' }, criticalStatus: 'ready', cachedAt: Date.now() }, false);
  await h.settle(4);
  const afterForeignPaint = {
    bookId: h.ctx._book && h.ctx._book.id ? h.ctx._book.id : null,
  };
  return {
    steps: [{
      step: 'obsolete-sequence',
      afterSwitch: afterSwitch,
      afterRelease: afterRelease,
      afterForeignPaint: afterForeignPaint,
      obsoleteRepainted: afterRelease.bookId === 'bookA',
      foreignRepainted: afterForeignPaint.bookId === 'bookA',
    }],
    fetchLog: h.fetchLog.slice(),
  };
}

// Critical -> live -> details -> shared ordering on the normal success path.
async function scenarioOrdering() {
  const h = buildContext({ portfolios: [BOOK_A, BOOK_B], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 })); });

  h.ctx._portfolio = 'bookA';
  await h.ctx.fetchAll({ showBar: true });
  await h.settle(4);
  const order = h.fetchLog.filter(function (u) {
    return u.indexOf('/api/portfolio?') === 0
      || u.indexOf('/api/live_marks') === 0
      || u.indexOf('/api/trades') === 0
      || u.indexOf('/api/performance') === 0
      || u.indexOf('/api/decisions') === 0
      || u.indexOf('/api/risk') === 0
      || u === '/api/portfolios'
      || u.indexOf('/api/activity') === 0;
  });
  return { steps: [{ step: 'ordering', order: order }], fetchLog: h.fetchLog.slice() };
}

// The self-directed critical branch carries no criticalStatus and must stay cacheable.
async function scenarioSelfDirected() {
  const h = buildContext({ portfolios: [BOOK_A, SELF], default: 'bookA' });
  h.installCommonRoutes();
  h.route('/api/portfolio?portfolio=bookA', function () { return Promise.resolve(h.okResponse({ id: 'bookA', nav: 1000 })); });

  h.ctx._portfolio = 'bookA';
  const critical = await h.ctx._fetchPortfolioCritical('self_directed');
  await h.ctx.fetchAll({ showBar: true });
  await h.settle(12);
  return {
    steps: [{
      step: 'self-directed',
      criticalHasCriticalStatus: Object.prototype.hasOwnProperty.call(critical, 'criticalStatus'),
      criticalHasSelf: Object.prototype.hasOwnProperty.call(critical, 'self'),
      cacheSelfDirected: h.cacheEntry('self_directed'),
    }],
    fetchLog: h.fetchLog.slice(),
  };
}

const SCENARIOS = {
  cold_failure: scenarioColdFailure,
  stale_background: scenarioStaleBackground,
  useful_prefetch: scenarioUsefulPrefetch,
  coalescing: scenarioCoalescing,
  shared_singleton: scenarioSharedSingleton,
  obsolete_sequence: scenarioObsoleteSequence,
  ordering: scenarioOrdering,
  self_directed: scenarioSelfDirected,
};

(async function () {
  const out = {};
  for (const name of scenarioNames) {
    const fn = SCENARIOS[name];
    if (!fn) {
      process.stderr.write('unknown scenario: ' + name + '\n');
      process.exit(2);
    }
    out[name] = await fn();
  }
  process.stdout.write(JSON.stringify(out));
})().catch(function (err) {
  process.stderr.write('harness error: ' + (err && err.stack ? err.stack : String(err)) + '\n');
  process.exit(1);
});
"""

_SCENARIOS = (
    "cold_failure",
    "stale_background",
    "useful_prefetch",
    "coalescing",
    "shared_singleton",
    "obsolete_sequence",
    "ordering",
    "self_directed",
)


def _node() -> str:
    node = shutil.which("node")
    assert node is not None, (
        "node is required to execute the inline portfolio JavaScript; "
        "this host does not provide it"
    )
    return node


@lru_cache(maxsize=1)
def _harness_results() -> dict:
    """Execute the candidate's inline JavaScript once and return its observations."""
    node = _node()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        script_path = tmp_path / "mastermind-inline.js"
        script_path.write_text(_inline_script())
        harness_path = tmp_path / "portfolio_switch_harness.js"
        harness_path.write_text(_HARNESS_JS)
        run = subprocess.run(
            [node, str(harness_path), str(script_path), *_SCENARIOS],
            capture_output=True,
            text=True,
            timeout=120,
        )
    assert run.returncode == 0, f"portfolio harness failed:\n{run.stderr}"
    return json.loads(run.stdout)


def _steps(scenario: str) -> dict:
    results = _harness_results()
    assert scenario in results, f"harness did not report scenario {scenario!r}"
    return {step["step"]: step for step in results[scenario]["steps"]}


def test_inline_portfolio_javascript_parses() -> None:
    node = _node()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mastermind-inline.js"
        path.write_text(_inline_script())
        run = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr


def test_cold_critical_failure_still_hydrates_shared_navigation() -> None:
    """A failed selected book must not strand the switcher.

    With an empty registry the critical read of the selected book fails. The book
    must stay truthfully unavailable, the shared/navigation hydration must already
    be running on that failure path, the real switcher must end up populated, and
    switching to a healthy book must reach its own successful snapshot.
    """
    steps = _steps("cold_failure")
    cold = steps["after-cold-failure"]

    # The failure is truthful: the selected book is visibly unavailable.
    assert cold["scopeState"] == "unavailable"
    # The shared/navigation hydration was already reached by the failure path.
    assert cold["sharedRegistryFetches"] == 1
    assert cold["sharedLoaded"] is True
    # The registry and the real switcher are populated from that same path.
    assert cold["registryCount"] == 2
    assert cold["switcherHasBookA"] is True
    assert cold["switcherHasBookB"] is True

    shared = steps["after-shared-hydration"]
    # Exactly one shared request group, however many callers join the singleton.
    assert shared["sharedRegistryFetches"] == 1
    assert shared["sharedGroupFetches"] == 1
    assert shared["scopeState"] == "unavailable"
    assert shared["selectedPortfolio"] == "bookA"

    selected = steps["after-selecting-healthy-book"]
    assert selected["scopeState"] == "ready"
    assert selected["selectedPortfolio"] == "bookB"
    assert selected["bookLoaded"] is True
    assert selected["bookId"] == "bookB"
    assert selected["cacheBookB"]["criticalStatus"] == "ready"
    # The healthy book's own switch did not start a second shared request group.
    assert selected["sharedRegistryFetches"] == 1
    assert selected["sharedGroupFetches"] == 1


def test_late_failed_background_prefetch_cannot_overwrite_newer_truth() -> None:
    """A background prefetch that fails late must not destroy good cached truth.

    The older background read for book B is held, the foreground read for the same
    book succeeds and commits good truth, and only then does the held background
    read fail. The good entry and its original timestamp must survive, and a later
    revisit whose revalidation fails must still show the last-good book as stale
    truth rather than an empty one.
    """
    steps = _steps("stale_background")

    committed = steps["foreground-commit"]
    assert committed["cacheBookB"]["criticalStatus"] == "ready"
    assert committed["cacheBookB"]["bookId"] == "bookB"
    assert committed["bookLoaded"] is True

    late = steps["after-late-background-failure"]
    assert late["truthPreserved"] is True
    assert late["timestampPreserved"] is True
    assert late["cacheBookB"]["criticalStatus"] == "ready"
    assert late["cacheBookB"]["bookId"] == "bookB"
    # The failed work did not extend the entry's freshness window.
    assert late["cacheBookB"]["cachedAt"] == committed["cacheBookB"]["cachedAt"]

    revisit = steps["after-revisit-with-failed-revalidation"]
    assert revisit["scopeState"] == "stale"
    assert revisit["bookLoaded"] is True
    assert revisit["bookId"] == "bookB"
    assert revisit["cacheBookB"]["criticalStatus"] == "ready"
    assert revisit["cacheBookB"]["bookId"] == "bookB"


def test_successful_background_prefetch_still_populates_the_cache() -> None:
    """The repair must not block a useful background warm-up."""
    step = _steps("useful_prefetch")["useful-prefetch"]
    assert step["cacheBookB"] is not None
    assert step["cacheBookB"]["criticalStatus"] == "ready"
    assert step["cacheBookB"]["bookId"] == "bookB"


def test_in_flight_prefetch_is_coalesced_and_cleaned_up() -> None:
    step = _steps("coalescing")["in-flight-coalescing"]
    assert step["coalesced"] is True
    assert step["inflightRegistered"] is True
    assert step["inflightCleanedUp"] is True
    assert step["bookBCriticalReads"] == 1


def test_shared_hydration_issues_one_request_group() -> None:
    step = _steps("shared_singleton")["shared-singleton"]
    assert step["samePromise"] is True
    assert step["registryFetches"] == 1
    assert step["sharedGroupFetches"] == 1
    assert step["sharedLoaded"] is True


def test_obsolete_sequence_cannot_repaint_another_book() -> None:
    step = _steps("obsolete_sequence")["obsolete-sequence"]
    assert step["afterSwitch"]["bookId"] == "bookB"
    assert step["obsoleteRepainted"] is False
    assert step["afterRelease"]["bookId"] == "bookB"
    assert step["foreignRepainted"] is False
    assert step["afterForeignPaint"]["bookId"] == "bookB"


def test_normal_load_keeps_critical_live_details_shared_order() -> None:
    order = _steps("ordering")["ordering"]["order"]
    assert order[:8] == [
        "/api/portfolio?portfolio=bookA",
        "/api/live_marks?portfolio=bookA",
        "/api/trades?portfolio=bookA",
        "/api/performance?portfolio=bookA",
        "/api/decisions?portfolio=bookA",
        "/api/risk?portfolio=bookA",
        "/api/portfolios",
        "/api/activity",
    ]


def test_self_directed_snapshot_without_critical_status_stays_cacheable() -> None:
    """The self-directed critical branch carries no criticalStatus at all."""
    step = _steps("self_directed")["self-directed"]
    assert step["criticalHasCriticalStatus"] is False
    assert step["criticalHasSelf"] is True
    assert step["cacheSelfDirected"] is not None
    assert step["cacheSelfDirected"]["hasCriticalStatus"] is False
    assert step["cacheSelfDirected"]["hasSelf"] is True
    assert step["cacheSelfDirected"]["complete"] is True
