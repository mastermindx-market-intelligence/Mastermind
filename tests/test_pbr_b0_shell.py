"""PBR B0 view shell: hash routes, view tabset, book-switch invalidation and the G5 skeleton.

Spec: docs/superpowers/specs/2026-10-22-pbr-product-views.md §2 (shell, hash routing, cache
invalidation) and §3 (state vocabulary, loading = true-geometry skeleton). Every behavioural
test executes the SHIPPED functions sliced out of app/static/index.html inside a node vm with a
minimal DOM stub; nothing here re-implements the router. Fixtures are synthetic.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

VIEWS = ["overview", "decision", "pending", "performance", "opportunities", "position", "operations"]
TAB_LABELS = [
    ("overview", "Overview", "总览"),
    ("decision", "Decision", "决策"),
    ("pending", "Pending", "待处理"),
    ("performance", "Performance", "业绩"),
    ("opportunities", "Opportunities", "机会"),
    ("position", "Position review", "持仓复盘"),
    ("operations", "Operations", "运行状态"),
]
# panel id contained by the wrapper -> the wrapper's data-mm-views (spec §2 view mapping)
VIEW_MAP = {
    "decision-availability": "decision",
    "auto-banner": "decision",
    "forward-evaluation": "operations",
    "performance": "overview performance",
    "alloc": "overview",
    "positions": "overview position",
    "trades": "pending position",
    "safety": "overview",
    "decisions": "decision",
    "sizing-card": "position",
    "brainlog": "decision",
    "runs": "operations",
    "rejected": "opportunities",
    "shadow-books": "opportunities",
    "xsec": "opportunities",
    "engine-bt": "operations",
    "factor-zoo": "opportunities",
    "fundamentals": "opportunities",
    "learning-models": "operations",
}
SCOPE_ERROR_EN = "Couldn't load — this panel's read failed; other panels still work."
SCOPE_ERROR_ZH = "加载失败 — 此面板读取失败；其他面板仍可用。"


# ── source slicing (shipped code only) ────────────────────────────────────────


def _between(start: str, end: str) -> str:
    i = HTML.index(start)
    j = HTML.index(end, i)
    return HTML[i:j + len(end)]


def _top_fn(name: str) -> str:
    """A top-level `function name(...) { ... }` whose closing brace sits at column 0."""
    start = HTML.index("\nfunction " + name + "(") + 1
    return HTML[start:HTML.index("\n}\n", start) + 3]


def _window_fn(name: str) -> str:
    """A top-level `window.name = function(...) { ... };` assignment."""
    start = HTML.index("\nwindow." + name + " = function") + 1
    return HTML[start:HTML.index("\n};\n", start) + 4]


ROUTER = _between("// PBR-B0-ROUTER:BEGIN", "// PBR-B0-ROUTER:END")
I18N_SRC = HTML[HTML.index("var I18N = {"):HTML.index("\n};\n", HTML.index("var I18N = {")) + 4]
PF_ORDER_SRC = re.search(r"var _PF_ORDER = \[[^\]]*\];", HTML).group(0)
INIT = _between("var _path0 = location.pathname", "fetchAll({ showBar: true });")
SHELL_CSS = _between("/* ── PBR B0 view shell + G5 skeleton", "</style>")


# ── node harness ──────────────────────────────────────────────────────────────

PRELUDE = r"""
var window = this;
var __calls = [];
var __history = [];
var __els = {};
var __sections = [];
var __links = [];
var __rows = {};
function __classList() {
  var s = {};
  return {
    toggle: function(c, on) { if (on === undefined) on = !s[c]; if (on) s[c] = true; else delete s[c]; return !!on; },
    contains: function(c) { return !!s[c]; },
    add: function(c) { s[c] = true; },
    remove: function(c) { delete s[c]; },
    list: function() { return Object.keys(s).sort(); }
  };
}
function __mk(id, attrs) {
  var el = {id: id, attrs: {}, style: {display: ''}, hidden: false, textContent: '', innerHTML: '',
            offsetWidth: 0, listeners: [], scrolled: 0};
  el.classList = __classList();
  el.setAttribute = function(k, v) { el.attrs[k] = String(v); };
  el.getAttribute = function(k) { return Object.prototype.hasOwnProperty.call(el.attrs, k) ? el.attrs[k] : null; };
  el.removeAttribute = function(k) { delete el.attrs[k]; };
  el.toggleAttribute = function(k, on) { if (on) el.attrs[k] = ''; else delete el.attrs[k]; };
  el.addEventListener = function(ev) { el.listeners.push(ev); };
  el.scrollIntoView = function() { el.scrolled += 1; };
  el.closest = function() { return null; };
  for (var k in (attrs || {})) el.attrs[k] = attrs[k];
  return el;
}
function E(id) { if (!__els[id]) __els[id] = __mk(id); return __els[id]; }
function __section(views, display) {
  var s = __mk('', {'data-mm-views': views}); s.style.display = display || ''; __sections.push(s); return s;
}
function __tabs() {
  ['overview', 'decision', 'pending', 'performance', 'opportunities', 'position', 'operations'].forEach(function(v) {
    __links.push(__mk('tab-' + v, {'data-mm-view': v}));
  });
}
function __allSections() {
  __section('decision'); __section('overview performance'); __section('overview');
  __section('overview position'); __section('pending position'); __section('opportunities');
  __section('operations');
}
var document = {
  documentElement: __mk('html'),
  body: __mk('body'),
  getElementById: function(id) { return __els[id] || null; },
  querySelectorAll: function(sel) {
    var m = /^\.mm-section\[data-mm-views~="([a-z]+)"\]$/.exec(sel);
    if (m) return __sections.filter(function(s) {
      return (' ' + s.getAttribute('data-mm-views') + ' ').indexOf(' ' + m[1] + ' ') !== -1;
    });
    if (sel === '#mm-tabset a[data-mm-view]') return __links;
    throw new Error('unstubbed selector: ' + sel);
  },
  querySelector: function(sel) {
    var m = /^tr\.pos-row\[data-idx="(\d+)"\]$/.exec(sel);
    if (m) return __rows[m[1]] || null;
    throw new Error('unstubbed selector: ' + sel);
  }
};
var location = {hash: '', pathname: '/'};
function __setUrl(u) {
  var i = u.indexOf('#');
  location.hash = i === -1 ? '' : u.slice(i);
  location.pathname = i === -1 ? u : u.slice(0, i);
}
var history = {
  pushState: function(s, t, u) { __history.push(['push', u]); __setUrl(u); },
  replaceState: function(s, t, u) { __history.push(['replace', u]); __setUrl(u); }
};
window.scrollTo = function() { __calls.push('scrollTo'); };
window.matchMedia = function() { return {matches: false}; };
function clearTimeout() {}
// page globals the shipped functions read (defaults as declared on master)
var _portfolios = [];
var _portfolio = 'autonomous';
var _currentView = 'dashboard';
var _book = null, _perf = null, _trades = null, _risk = null, _decisions = [], _rejected = [];
var _decisionAvailability = null, _forwardEvaluation = null, _liveMarks = null;
var _expandedIdx = null, _tradesPage = 0, _decisionsExpanded = false, _autoThesisExpanded = false;
var _self = null, _selfHist = null;
var _liveTimer = null, _liveFetchSeq = 0, _portfolioDataCache = {}, PORTFOLIO_SNAPSHOT_MAX_AGE_MS = 30000;
var _decisionAvailabilityPending = true, _forwardEvaluationPending = true;
var _researchSub = 'papers';
// collaborators outside the unit under test
function fetchAll(opts) { __calls.push('fetchAll:' + JSON.stringify(opts || {})); }
function renderPortfolioSwitch() { __calls.push('renderPortfolioSwitch'); }
function _safeRender(name) { __calls.push('render:' + name); }
function renderDecisionAvailability() {}
function renderForwardEvaluation() {}
function renderAutoBanner() {}
function renderDecisions() {}
function _paintPortfolioSnapshot() { __calls.push('paintSnapshot'); }
function _ensureResearchPapers() {}
function _ensureCalibration() {}
function loadDesk() {}
var __out = null;
"""

HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const context = vm.createContext({});
for (const [i, p] of process.argv.slice(1).entries()) {
  vm.runInContext(fs.readFileSync(p, "utf8"), context, {filename: "part" + i + ".js"});
}
console.log(JSON.stringify(context.__out));
"""


def _run(tmp_path: Path, name: str, scenario: str, *, units: list[str], stubs: str = ""):
    node = shutil.which("node")
    assert node is not None
    parts = [PRELUDE, I18N_SRC + "\n" + _top_fn("t") + "\n" + PF_ORDER_SRC, *units, stubs, scenario]
    paths = []
    for i, src in enumerate(parts):
        p = tmp_path / f"{name}.{i}.js"
        p.write_text(src, encoding="utf-8")
        paths.append(str(p))
    done = subprocess.run([node, "-e", HARNESS, *paths], capture_output=True, text=True,
                          timeout=30, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout)


# ── S1 parse / format ─────────────────────────────────────────────────────────


@requires_node
def test_s1_parse_and_format_hash(tmp_path):
    cases = ["#/autonomous/overview", "#/china/performance", "#/autonomous/position/AAA",
             "#/hk/position/0700.HK", "#/autonomous/position/aaa", "#/hk/position/%5EHSI",
             "#/autonomous/xyz", "#/autonomous/position", "#/nope/overview", "", "#",
             "#positions", "#/", "#/autonomous/position/%3Cimg%3E", "#/autonomous/position/%E0%A4%A"]
    scenario = "var __cases = " + json.dumps(cases) + ";\n" + r"""
var rows = __cases.map(function(h) {
  var p = _parseHash(h);
  return {h: h, p: p, fmt: p.valid ? _formatHash(p.book, p.view, p.ticker) : null};
});
_portfolios = [{id: 'autonomous'}, {id: 'newbook'}];
__out = {rows: rows, registryKnown: _parseHash('#/newbook/overview'),
         registryUnknown: _parseHash('#/china/overview'), nonString: _parseHash(null)};
"""
    out = _run(tmp_path, "s1", scenario, units=[ROUTER])
    got = {r["h"]: r for r in out["rows"]}

    def p(h):
        return got[h]["p"]

    assert p("#/autonomous/overview") == {"book": "autonomous", "view": "overview", "ticker": None, "valid": True}
    assert p("#/china/performance") == {"book": "china", "view": "performance", "ticker": None, "valid": True}
    assert p("#/autonomous/position/AAA")["ticker"] == "AAA"
    assert p("#/hk/position/0700.HK") == {"book": "hk", "view": "position", "ticker": "0700.HK", "valid": True}
    assert p("#/autonomous/position/aaa")["ticker"] == "AAA"
    assert p("#/hk/position/%5EHSI")["ticker"] == "^HSI"
    assert p("#/autonomous/xyz") == {"book": "autonomous", "view": "overview", "ticker": None, "valid": True}
    assert p("#/autonomous/position") == {"book": "autonomous", "view": "position", "ticker": None, "valid": True}
    for bad in ["#/nope/overview", "", "#", "#positions", "#/"]:
        assert p(bad)["valid"] is False, bad
        assert got[bad]["fmt"] is None
    # an unsafe or undecodable segment never becomes a ticker
    assert p("#/autonomous/position/%3Cimg%3E")["ticker"] is None
    assert p("#/autonomous/position/%E0%A4%A")["ticker"] is None
    # round trip for the canonical forms; a lower-case ticker and an unknown view normalise
    for canonical in ["#/autonomous/overview", "#/china/performance", "#/autonomous/position/AAA",
                      "#/hk/position/0700.HK", "#/hk/position/%5EHSI", "#/autonomous/position"]:
        assert got[canonical]["fmt"] == canonical
    assert got["#/autonomous/position/aaa"]["fmt"] == "#/autonomous/position/AAA"
    assert got["#/autonomous/xyz"]["fmt"] == "#/autonomous/overview"
    # once the registry lands it, not the hard-coded order, decides which books exist
    assert out["registryKnown"]["valid"] is True
    assert out["registryUnknown"]["valid"] is False
    assert out["nonString"]["valid"] is False


# ── S2 tabs ───────────────────────────────────────────────────────────────────

S2_SCENARIO = r"""
function snap() {
  return {
    view: _mmView,
    body: document.body.getAttribute('data-mm-view'),
    current: __links.filter(function(a) { return a.getAttribute('aria-current') === 'page'; })
                    .map(function(a) { return a.getAttribute('data-mm-view'); }),
    hidden: __links.filter(function(a) { return a.hidden; }).map(function(a) { return a.getAttribute('data-mm-view'); }),
    hrefs: __links.map(function(a) { return a.getAttribute('href'); }),
    label: E('mm-tabset').getAttribute('aria-label')
  };
}
E('mm-tabset'); __tabs(); __allSections();
var res = {};
_portfolios = [{id: 'autonomous', lifecycle: 'active'}, {id: 'flagship', lifecycle: 'archived', active: false}];
_portfolio = 'autonomous'; _mmView = 'pending'; _mmSyncTabs(); res.active = snap();
_portfolio = 'flagship'; _mmView = 'pending'; _mmPositionTicker = 'AAA'; _mmSyncTabs();
res.archived = snap(); res.archivedTicker = _mmPositionTicker;
_portfolios = []; _portfolio = 'flagship'; _mmView = 'pending'; _mmSyncTabs(); res.fallbackArchived = snap();
_portfolio = 'autonomous'; _mmView = 'decision';
__sections.forEach(function(s) { if (s.getAttribute('data-mm-views') === 'decision') s.style.display = 'none'; });
_mmSyncTabs(); res.hiddenView = snap();
document.documentElement.setAttribute('data-lang', 'zh'); _mmSyncTabs(); res.zh = snap();
__out = res;
"""


@requires_node
def test_s2_tabset_follows_book_and_view_availability(tmp_path):
    out = _run(tmp_path, "s2", S2_SCENARIO, units=[ROUTER])
    active = out["active"]
    assert active["view"] == "pending" and active["body"] == "pending"
    assert active["current"] == ["pending"]
    assert active["hidden"] == []
    assert active["hrefs"] == ["#/autonomous/" + v for v in VIEWS]
    assert active["label"] == "View"
    # archived books are read-only: no pending view, and a selected pending view falls back
    for key in ("archived", "fallbackArchived"):
        snap = out[key]
        assert snap["hidden"] == ["pending"], key
        assert snap["view"] == "overview" and snap["body"] == "overview", key
        assert snap["current"] == ["overview"], key
        assert snap["hrefs"] == ["#/flagship/" + v for v in VIEWS], key
    assert out["archivedTicker"] is None
    # a view whose every section is hidden for this book is unavailable
    hidden = out["hiddenView"]
    assert hidden["view"] == "overview" and hidden["current"] == ["overview"]
    assert "decision" in hidden["hidden"]
    assert out["zh"]["label"] == "视图"


# ── S3 invalidation ───────────────────────────────────────────────────────────


@requires_node
def test_s3_book_switch_invalidates_every_book_scoped_global(tmp_path):
    scenario = r"""
var S = {sentinel: true};
_book = S; _perf = S; _trades = S; _risk = S; _decisions = [S]; _rejected = [S];
_decisionAvailability = S; _forwardEvaluation = S; _liveMarks = S;
_expandedIdx = 3; _tradesPage = 2; _decisionsExpanded = true; _autoThesisExpanded = true;
_mmPositionApplied = 'autonomous:AAA';
_self = S; _selfHist = S;
_invalidateBookScopedState();
__out = {book: _book, perf: _perf, trades: _trades, risk: _risk, decisions: _decisions, rejected: _rejected,
         da: _decisionAvailability, fe: _forwardEvaluation, live: _liveMarks, expanded: _expandedIdx,
         page: _tradesPage, decExp: _decisionsExpanded, thesisExp: _autoThesisExpanded,
         applied: _mmPositionApplied, self: _self, selfHist: _selfHist};
"""
    out = _run(tmp_path, "s3", scenario, units=[ROUTER])
    for key in ("book", "perf", "trades", "risk", "da", "fe", "live", "expanded"):
        assert out[key] is None, key
    assert out["decisions"] == [] and out["rejected"] == []
    assert out["page"] == 0
    assert out["decExp"] is False and out["thesisExp"] is False
    assert out["applied"] == ""
    # the Self-Directed book has its own lifecycle; a dashboard switch must not wipe it
    assert out["self"] == {"sentinel": True} and out["selfHist"] == {"sentinel": True}


# ── S4 setPortfolio history ───────────────────────────────────────────────────

S4_STUBS = r"""
function applyPortfolioScope() { __calls.push('applyPortfolioScope'); }
function _updateScopedPanelAvailability(p) { __calls.push('availability:' + p); }
function _isAvailabilityBook(id) { return id === 'autonomous' || id === 'china' || id === 'hk'; }
"""


@requires_node
def test_s4_set_portfolio_writes_one_history_entry(tmp_path):
    scenario = r"""
var res = {};
E('mm-tabset'); __tabs(); __allSections();
location.hash = '#/autonomous/overview'; _mmHashActive = true;
_mmPositionTicker = 'AAA'; _book = {sentinel: true};
setPortfolio('china');
res.afterSwitch = {history: __history.slice(), ticker: _mmPositionTicker, book: _book, portfolio: _portfolio,
                   owns: _hashOwnsBook};
setPortfolio('china');
res.sameBookHistory = __history.length;
setPortfolio('hk', {replace: true});
res.replace = __history.slice(-1)[0];
_mmView = 'position'; _mmPositionTicker = 'BBB'; location.hash = '#/hk/overview';
var before = __history.length;
setPortfolio('autonomous', {fromHash: true});
res.fromHash = {added: __history.slice(before), ticker: _mmPositionTicker};
res.pushes = __history.filter(function(e) { return e[0] === 'push'; }).length;
res.fetches = __calls.filter(function(c) { return c.indexOf('fetchAll:') === 0; });
__out = res;
"""
    out = _run(tmp_path, "s4", scenario, units=[ROUTER, _window_fn("setPortfolio")], stubs=S4_STUBS)
    first = out["afterSwitch"]
    assert first["history"] == [["push", "/#/china/overview"]]
    assert first["ticker"] is None, "an explicit switch must not carry a ticker to another book"
    assert first["book"] is None, "the previous book's payload must be invalidated before paint"
    assert first["portfolio"] == "china" and first["owns"] is True
    assert out["sameBookHistory"] == 1, "re-selecting the open book must not add a history entry"
    assert out["replace"] == ["replace", "/#/hk/overview"]
    assert out["fromHash"]["added"] == [["replace", "/#/autonomous/position/BBB"]]
    assert out["fromHash"]["ticker"] == "BBB"
    assert out["pushes"] == 1
    assert all('"scopedOnly":true' in f for f in out["fetches"])


# ── S5 scoped panel availability (skeleton / failed / reveal) ─────────────────

S5_SCENARIO = r"""
var PANELS = ['performance', 'positions', 'alloc', 'trades', 'safety', 'rejected'];
PANELS.forEach(function(id) { E(id); });
E('mm-scope-retry').hidden = true; E('mm-scope-status');
function snap() {
  var o = {};
  PANELS.forEach(function(id) {
    var p = E(id);
    o[id] = {cls: p.classList.list(), busy: p.getAttribute('aria-busy'), msg: p.getAttribute('data-scope-message'),
             listeners: p.listeners.slice()};
  });
  return {panels: o, retryHidden: E('mm-scope-retry').hidden, status: E('mm-scope-status').textContent};
}
var res = {};
_portfolio = 'autonomous';
_updateScopedPanelAvailability(true); res.loading = snap();
_perf = {}; _book = {}; _trades = {};
_updateScopedPanelAvailability(false); res.failedEn = snap();
document.documentElement.setAttribute('data-lang', 'zh');
_updateScopedPanelAvailability(false); res.failedZh = snap();
document.documentElement.setAttribute('data-lang', 'en');
PANELS.forEach(function(id) { var p = E(id); p.classList.list().forEach(function(c) { p.classList.remove(c); }); p.listeners = []; });
_perf = null; _book = null; _trades = null; _risk = {};
_updateScopedPanelAvailability(true);
_perf = {}; _book = {}; _trades = {};
_updateScopedPanelAvailability(false); res.revealed = snap();
_portfolio = 'self_directed'; _perf = null; _book = null; _trades = null; _risk = null;
_updateScopedPanelAvailability(false); res.self = snap();
__out = res;
"""


@requires_node
def test_s5_scoped_panels_skeleton_failure_and_reveal(tmp_path):
    out = _run(tmp_path, "s5", S5_SCENARIO, units=[_top_fn("_updateScopedPanelAvailability")])
    loading = out["loading"]
    for pid, panel in loading["panels"].items():
        assert panel["cls"] == ["mm-pf-awaiting", "mm-skel"], pid
        assert panel["busy"] == "true", pid
        assert panel["msg"] == "", pid
    assert loading["status"] == "Loading"
    assert loading["retryHidden"] is True

    failed = out["failedEn"]
    assert failed["panels"]["safety"]["cls"] == ["mm-pf-awaiting", "mm-pf-failed"]
    assert failed["panels"]["safety"]["busy"] is None
    assert failed["panels"]["safety"]["msg"] == SCOPE_ERROR_EN
    assert failed["retryHidden"] is False
    assert failed["status"] == "Couldn't load"
    for pid in ("performance", "positions", "alloc", "trades", "rejected"):
        assert "mm-pf-awaiting" not in failed["panels"][pid]["cls"], pid
        assert failed["panels"][pid]["msg"] == "", pid
    zh = out["failedZh"]
    assert zh["panels"]["safety"]["msg"] == SCOPE_ERROR_ZH
    assert zh["status"] == "加载失败"

    revealed = out["revealed"]
    for pid in ("performance", "positions", "alloc", "trades", "rejected"):
        assert revealed["panels"][pid]["cls"] == ["mm-pf-reveal"], pid
        assert revealed["panels"][pid]["listeners"] == ["animationend"], pid
    # #safety never awaited in this pass, so it must not animate
    assert revealed["panels"]["safety"]["cls"] == []
    assert revealed["retryHidden"] is True and revealed["status"] == ""

    self_book = out["self"]
    assert self_book["retryHidden"] is True
    assert self_book["status"] == ""


# ── S6 position deep link ─────────────────────────────────────────────────────


@requires_node
def test_s6_position_route_opens_once_and_drops_unheld_ticker(tmp_path):
    scenario = r"""
window.toggleExpand = function(i) { __calls.push('toggle:' + i); _expandedIdx = i; };
__rows['1'] = __mk('row-1');
_portfolio = 'autonomous'; _mmView = 'position'; _mmPositionTicker = 'BBB';
_book = {positions: [{ticker: 'AAA'}, {ticker: 'bbb'}]};
_mmApplyPositionRoute();
_mmApplyPositionRoute();
var res = {toggles: __calls.filter(function(c) { return c.indexOf('toggle:') === 0; }),
           scrolled: __rows['1'].scrolled, history: __history.slice()};
_mmPositionTicker = 'ZZZ'; _mmPositionApplied = '';
_mmApplyPositionRoute();
res.unheld = {ticker: _mmPositionTicker, history: __history.slice(),
              toggles: __calls.filter(function(c) { return c.indexOf('toggle:') === 0; }).length};
__out = res;
"""
    out = _run(tmp_path, "s6", scenario, units=[ROUTER])
    assert out["toggles"] == ["toggle:1"]
    assert out["scrolled"] == 1
    assert out["history"] == []
    assert out["unheld"]["ticker"] is None
    assert out["unheld"]["history"] == [["replace", "/#/autonomous/position"]]
    assert out["unheld"]["toggles"] == 1


# ── S7 route handler idempotency ──────────────────────────────────────────────


@requires_node
def test_s7_route_handler_is_idempotent(tmp_path):
    scenario = r"""
var __realSet = window.setPortfolio;
window.setPortfolio = function(id, opts) { __calls.push('set:' + id); return __realSet(id, opts); };
E('mm-tabset'); __tabs(); __allSections();
_portfolio = 'autonomous';
location.hash = '#/china/performance';
_mmOnRoute(); _mmOnRoute();   // hashchange and popstate both fire for one back/forward
var res = {sets: __calls.filter(function(c) { return c.indexOf('set:') === 0; }),
           pushes: __history.filter(function(e) { return e[0] === 'push'; }).length,
           portfolio: _portfolio, view: _mmView, active: _mmHashActive};
var n = __history.length;
location.hash = '#/nope/overview';
_mmOnRoute();
res.invalid = {portfolio: _portfolio, view: _mmView, added: __history.length - n};
__out = res;
"""
    out = _run(tmp_path, "s7", scenario, units=[ROUTER, _window_fn("setPortfolio")], stubs=S4_STUBS)
    assert out["sets"] == ["set:china"]
    assert out["pushes"] == 0
    assert out["portfolio"] == "china" and out["view"] == "performance" and out["active"] is True
    assert out["invalid"] == {"portfolio": "china", "view": "performance", "added": 0}


# ── S8 showView URL ───────────────────────────────────────────────────────────


@requires_node
def test_s8_show_view_dashboard_url(tmp_path):
    scenario = r"""
E('mm-tabset'); __tabs(); __allSections();
_portfolio = 'hk'; _mmView = 'performance'; _mmHashActive = true;
showView('dashboard');
var res = {active: __history.slice(-1)[0]};
_mmHashActive = false;
showView('dashboard');
res.plain = __history.slice(-1)[0];
showView('research');
res.research = __history.slice(-1)[0];
__out = res;
"""
    out = _run(tmp_path, "s8", scenario, units=[ROUTER, _window_fn("showView")])
    assert out["active"] == ["replace", "/#/hk/performance"]
    assert out["plain"] == ["replace", "/"], "without a hash route the root URL stays exactly as master"
    assert out["research"] == ["replace", "/research"]


# ── S9 static contract ────────────────────────────────────────────────────────


def _wrapper_tag_for(panel_id: str) -> str:
    pos = HTML.index('id="' + panel_id + '"')
    head = HTML[:pos]
    tags = list(re.finditer(r'<div class="[^"]*\bmm-section\b[^"]*"[^>]*>', head))
    assert tags, panel_id
    return tags[-1].group(0)


def test_s9_view_mapping_on_section_wrappers():
    dashboard = HTML[:HTML.index('<div id="view-research">')]
    for panel_id, views in VIEW_MAP.items():
        tag = _wrapper_tag_for(panel_id)
        m = re.search(r'data-mm-views="([^"]*)"', tag)
        assert m, (panel_id, tag)
        assert m.group(1) == views, (panel_id, m.group(1))
    # every mapped wrapper is on the dashboard, and nothing inside the research/desk/self views is
    assert dashboard.count("data-mm-views=") == 19
    assert HTML.count("data-mm-views=") == 19


def test_s9_view_filter_rules_and_tab_labels():
    for view in VIEWS:
        rule = ('body.page-mm[data-mm-view="' + view + '"]:not(.view-research):not(.view-desk):not(.view-self) '
                '.mm-section[data-mm-views]:not([data-mm-views~="' + view + '"]){display:none!important}')
        assert HTML.count(rule) == 1, view
    nav = _between('<nav class="mm-tabset" id="mm-tabset"', "</nav>")
    tabs = re.findall(r'<a href="#/autonomous/([a-z]+)" data-mm-view="([a-z]+)"><span class="l-en">([^<]+)</span>'
                      r'<span class="l-zh">([^<]+)</span></a>', nav)
    assert [(slug, en, zh) for slug, _, en, zh in tabs] == TAB_LABELS
    assert all(a == b for a, b, _, _ in tabs)
    assert 'id="mm-scope-status" role="status" aria-live="polite"' in HTML
    assert 'id="mm-scope-retry" type="button" hidden onclick="_mmRetryScope()"' in HTML


def test_s9_markers_once_and_paired():
    markers = re.findall(r"PBR-B0-[A-Z-]+:(?:BEGIN|END)", HTML)
    assert markers, "no PBR-B0 markers"
    for marker in set(markers):
        assert HTML.count(marker) == 1, marker
    names = {m.rsplit(":", 1)[0] for m in markers}
    for name in names:
        assert HTML.index(name + ":BEGIN") < HTML.index(name + ":END"), name
    assert "PBR-B0-ROUTER" in names and "PBR-B0-SHELL-KEYS" in names


def _strip_js_comments(src: str) -> str:
    """Drop whole-line and trailing `//` comments (the shipped units keep `//` out of strings)."""
    out = []
    for line in src.splitlines():
        if line.lstrip().startswith("//"):
            continue
        out.append(re.sub(r"\s//\s.*$", "", line))
    return "\n".join(out)


def test_s9_es5_only_in_new_and_changed_code():
    units = {
        "router": ROUTER,
        "showView": _window_fn("showView"),
        "setPortfolio": _window_fn("setPortfolio"),
        "applyPortfolioScope": _top_fn("applyPortfolioScope"),
        "_updateScopedPanelAvailability": _top_fn("_updateScopedPanelAvailability"),
        "init": INIT,
    }
    banned = ["=>", "let ", "const ", "`", "?.", "??", "...", ".includes("]
    for name, src in units.items():
        code = _strip_js_comments(src)
        for token in banned:
            assert token not in code, (name, token)


def test_s9_init_parses_the_hash_before_the_first_scope_paint():
    parse = INIT.index("_parseHash(location.hash)")
    hashchange = INIT.index("window.addEventListener('hashchange', _mmOnRoute);")
    popstate = INIT.index("window.addEventListener('popstate', _mmOnRoute);")
    scope = INIT.index("applyPortfolioScope();")
    assert parse < hashchange < scope and popstate < scope
    assert INIT.index("if (_mmHashActive) _mmWriteHash(false);") > scope


def test_s9_skeleton_has_no_decorative_motion():
    assert re.findall(r"@keyframes\s+([\w-]+)", SHELL_CSS) == ["mm-pf-reveal"]
    for decl in re.findall(r"animation(?:-name)?\s*:\s*([^;}]+)", SHELL_CSS):
        assert decl.strip().startswith("mm-pf-reveal") or decl.strip() == "none", decl
    assert "140ms" in SHELL_CSS
    assert "@media (prefers-reduced-motion:reduce){.mm-pf-reveal{animation:none}}" in SHELL_CSS
    # loading is a static true-geometry skeleton: no prose in the pseudo-element, no shimmer sweep
    assert ".mm-pf-awaiting.mm-skel::after{content:''" in SHELL_CSS
    rules = re.sub(r"/\*.*?\*/", "", SHELL_CSS, flags=re.S).lower()
    assert "shimmer" not in rules and "pulse" not in rules
