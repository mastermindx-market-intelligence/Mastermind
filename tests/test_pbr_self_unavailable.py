"""A Self-Directed book that could not be read must render `unavailable`, never a fabricated book.

The failure shape (MASTERMIND §10.2): "An unavailable benchmark displays unavailable rather than
zero." ``/api/self_directed`` used to catch ANY read failure and return a synthetic funded book
(``nav``/``cash`` = 1_000_000, ``invested`` = 0, 100% cash, 0% return, market closed) and the blotter
returned a fabricated empty trade record. On the dashboard that is indistinguishable from a real
all-cash, break-even book — a read failure was displayed as a healthy account.

These tests execute the real shipped helper source in a Node ``vm`` — source-string presence alone
is not proof of behavior — and bind it to the actual ``/api/self_directed`` /
``/api/self_directed/history`` route output so the API and the renderer cannot drift apart. No
network, no live data: every quantity is a synthetic round number (this repository is public).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "app" / "static" / "index.html"
HTML = HTML_PATH.read_text()

BEGIN_MARKER = "// PBR-SELF-UNAVAILABLE:BEGIN"
END_MARKER = "// PBR-SELF-UNAVAILABLE:END"

requires_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is required to execute the shipped dashboard helpers",
)


# ── shipped-source extraction ─────────────────────────────────────────────────


def _fn_source(name: str) -> str:
    """One shipped top-level function, sliced from its declaration to the next one."""
    start = HTML.index("function " + name + "(")
    tail = HTML.index("\nfunction ", start + 1)
    return HTML[start:tail]


def _helpers_source() -> str:
    start = HTML.index(BEGIN_MARKER)
    end = HTML.index(END_MARKER) + len(END_MARKER)
    return HTML[start:end]


def _render_source() -> str:
    return "\n".join([
        _helpers_source(),
        _fn_source("_mktLabel"),
        _fn_source("renderSelfHeader"),
        _fn_source("renderSelfAlloc"),
        _fn_source("renderSelfPositions"),
        _fn_source("renderSelfHistory"),
    ])


# ── 1./2./3. the API contract ─────────────────────────────────────────────────


def _book_payload() -> dict:
    """A fully readable synthetic Self-Directed book (round numbers; this repo is public)."""
    return {
        "nav": 123456.78,
        "cash": 23456.78,
        "invested": 100000.0,
        "positions": [],
        "pending": [],
        "allocation": {
            "cash_pct": 0.19, "gross": 0.81, "n_positions": 0, "largest_weight": 0.0,
            "total_unrealized_pnl": 0.0, "total_return_pct": 0.0,
        },
        "market": {"is_open": False, "session": "closed", "next_open": None},
    }


def _boom(_exc=None):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("synthetic")
    return _raise


def test_api_self_directed_unreadable_book_reports_unavailable_never_a_funded_book(monkeypatch):
    """The error branch must not manufacture a $1M all-cash, 0%-return book."""
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "_load_account", _boom())
    monkeypatch.setattr(self_directed, "_market_status",
                        lambda: {"is_open": False, "session": "closed", "next_open": None})

    response = web.api_self_directed()
    assert response.status_code == 200, "a failed read must never 500 the dashboard"
    raw = response.body if isinstance(response.body, bytes) else response.body.encode()
    data = json.loads(raw)

    assert data["status"] == "unavailable"
    assert data["reason_code"] == "self_directed_book_unreadable"
    for field in ("nav", "cash", "invested", "starting_nav", "allocation"):
        assert data[field] is None, f"{field} must be None, not {data[field]!r}"
    assert data["positions"] == []
    assert data["pending"] == []
    assert data["error"] == "synthetic"
    # The market clock does not depend on the account read, so it may still be shown truthfully.
    assert data["market"] == {"is_open": False, "session": "closed", "next_open": None}

    # No fabricated starting capital anywhere in the wire bytes.
    assert b"1000000" not in raw
    assert b"1e6" not in raw
    assert b"1000000.0" not in raw


def test_api_self_directed_unreadable_book_drops_market_when_the_clock_also_fails(monkeypatch):
    """If the clock cannot be read either, `market` is None — never a fabricated "closed"."""
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "_load_account", _boom())
    monkeypatch.setattr(self_directed, "_market_status", _boom())

    data = json.loads(web.api_self_directed().body)
    assert data["status"] == "unavailable"
    assert data["market"] is None


def test_api_self_directed_success_path_is_unchanged(monkeypatch):
    """A readable book is returned verbatim and carries NO `status` key."""
    from app import web
    from portfolio import self_directed

    payload = _book_payload()
    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {}})
    monkeypatch.setattr(self_directed, "_load_pending", lambda: [])
    monkeypatch.setattr(web, "_live_prices", lambda tickers, **_kw: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kwargs: payload)

    response = web.api_self_directed()
    assert response.status_code == 200
    data = json.loads(response.body)
    assert data == payload
    assert "status" not in data
    assert "reason_code" not in data


def test_api_self_directed_history_unreadable_reports_unavailable_never_an_empty_blotter(monkeypatch):
    """Unreadable is not empty: a fabricated 0-fill blotter reads as "no trades yet"."""
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "_load_account", _boom())

    response = web.api_self_directed_history()
    assert response.status_code == 200
    raw = response.body if isinstance(response.body, bytes) else response.body.encode()
    data = json.loads(raw)

    assert data["status"] == "unavailable"
    assert data["reason_code"] == "self_directed_history_unreadable"
    for field in ("realized_total", "n_closed", "n_buys", "win_rate"):
        assert data[field] is None, f"{field} must be None, not {data[field]!r}"
    assert data["history"] == []
    assert data["pending"] == []
    assert data["error"] == "synthetic"


# ── 4. static wiring ──────────────────────────────────────────────────────────


def test_sd_nav_seed_is_a_neutral_placeholder_not_a_funded_number():
    """The pre-load seed must not claim a $1M book before any read has happened."""
    match = re.search(r'<div class="mm-perf-nav-value" id="sd-nav"[^>]*>([^<]*)</div>', HTML)
    assert match, "sd-nav seed not found"
    assert match.group(1).strip() == "—", f"sd-nav seed must be neutral, got {match.group(1)!r}"

    # ... and the reason line sits immediately after it, hidden until a read fails.
    after = HTML[match.end():match.end() + 200]
    assert '<div class="mm-perf-stat-sub" id="sd-nav-status" hidden></div>' in after
    assert HTML.count('id="sd-nav-status"') == 1


def test_unavailable_nav_is_muted_with_the_existing_token_only():
    """The unavailable hero reuses `var(--muted)` and beats the page-scoped `--text` rule."""
    rule = re.search(
        r'\.mm-perf-nav-value\[data-availability="unavailable"\],\s*'
        r'body\.page-mm \.mm-perf-nav-value\[data-availability="unavailable"\]\s*'
        r'\{\s*color:\s*var\(--muted\);\s*\}', HTML)
    assert rule, "muted rule for the unavailable NAV slot not found"
    # It must come after the page-scoped `color: var(--text)` rule it has to override.
    assert rule.start() > HTML.index("body.page-mm .mm-perf-nav-value {")
    # The heartbeat beside the hero is a health cue: it goes static and muted, nothing else.
    hb = re.search(r'\.mm-hb\[data-availability="unavailable"\]\s*'
                   r'\{\s*background:\s*var\(--muted\);\s*animation:\s*none;\s*\}', HTML)
    assert hb, "static muted heartbeat rule for the unavailable book not found"
    assert hb.start() > HTML.index(".mm-hb {")
    assert '<span class="mm-hb" id="sd-hb"></span>' in HTML and HTML.count('id="sd-hb"') == 1
    assert HTML.count('data-availability="unavailable"]') == 3


def test_render_self_header_has_no_fabricated_nav_fallback():
    source = _fn_source("renderSelfHeader")
    assert "1000000" not in source
    assert "1_000_000" not in source
    assert "fmtNav(b.nav)" in source


def test_helpers_are_wrapped_by_exactly_one_marker_pair_immediately_above_render_self_header():
    assert HTML.count(BEGIN_MARKER) == 1
    assert HTML.count(END_MARKER) == 1
    assert HTML.index(BEGIN_MARKER) < HTML.index(END_MARKER)
    assert "function _selfBookState(book, settled) {" in HTML
    assert "function _selfHistState(hist, settled) {" in HTML

    between = HTML[HTML.index(END_MARKER) + len(END_MARKER):HTML.index("function renderSelfHeader(")]
    assert between.strip() == "", "helpers must sit immediately above renderSelfHeader()"

    # ES5, matching the rest of this file: no arrow functions / let / const / template literals.
    helpers = _helpers_source()
    for banned in ("=>", "let ", "const ", "`"):
        assert banned not in helpers, f"helpers must stay ES5 (found {banned!r})"


@pytest.mark.parametrize(
    ("key", "en", "zh"),
    [
        ("sd.unavailable", "unavailable", "不可用"),
        ("sd.unavailable_reason",
         "Book unavailable — the account could not be read, so no balances are shown.",
         "组合数据不可用 —— 无法读取账户，因此不显示任何余额。"),
        ("sd.hist_unavailable",
         "Trade history unavailable — the fill log could not be read.",
         "交易记录不可用 —— 无法读取成交记录。"),
        ("sd.mkt.unknown", "Market status unavailable", "市场状态不可用"),
    ],
)
def test_unavailable_labels_are_localized(key: str, en: str, zh: str):
    match = re.search(r"'" + re.escape(key) + r"':\s*\{([^}]*)\}", HTML)
    assert match, f"missing i18n key {key}"
    body = match.group(1)
    assert "en:" in body and "zh:" in body, f"{key} must carry both languages"
    assert f"en: '{en}'" in body
    assert f"zh: '{zh}'" in body


def test_buying_power_and_ticket_refuse_to_render_or_act_on_an_unreadable_account():
    """No "$0 buying power" and no blind trade when cash cannot be read."""
    selected = HTML[HTML.index("function renderSelfSelected("):]
    selected = selected[:selected.index("\nfunction ")]
    assert "fmtNav((_self || {}).cash || 0)" not in selected
    assert "t('sd.unavailable')" in selected
    assert "t('sd.buying_power') + ' ' +" in selected

    est_src = HTML[HTML.index("window.selfUpdateEst = function() {"):]
    est_src = est_src[:est_src.index("\nwindow.")]
    assert "cash = (_self || {}).cash || 0" not in est_src
    assert "cashKnown ? fmtNav(rawCash) : t('sd.unavailable')" in est_src
    assert "buy.disabled = bookUnknown || !canBuy || _selfBusy;" in est_src
    assert "sell.disabled = bookUnknown || !canSell || _selfBusy;" in est_src


# ── node harness ──────────────────────────────────────────────────────────────

PRELUDE = r"""
var __els = {};
function __mk(text) {
  var el = {textContent: text, className: '', innerHTML: '', hidden: true, value: '', attrs: {}};
  el.setAttribute = function(k, v) { el.attrs[k] = String(v); };
  el.removeAttribute = function(k) { delete el.attrs[k]; };
  el.getAttribute = function(k) { return Object.prototype.hasOwnProperty.call(el.attrs, k) ? el.attrs[k] : null; };
  return el;
}
function E(id) {
  if (!__els[id]) __els[id] = __mk('');
  return __els[id];
}
function t(k) { return k; }
function fmtNav(n) { return '$' + n; }
function pctInt(n) { return String(n); }
function esc(s) { return s == null ? '' : String(s); }
function fmtShares(n) { return n == null ? '—' : String(n); }
function fmtDate(d) { return String(d == null ? '' : d); }
function pnlCell() { return {cls: 'neu', txt: '—'}; }
function securityName() { return ''; }
var _SD_PALETTE = ['var(--q1)', 'var(--up)'];
var _selfExpanded = null;
var _liveMarks = null;
"""

HELPER_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(process.argv[2], "utf8");
const cases = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const context = vm.createContext({});
vm.runInContext(source, context, {filename: "_selfState.js"});

function materialise(c) {
  if (c.special === "undefined") return undefined;
  if (c.special === "null") return null;
  if (c.special === "nan_nav") return {nav: NaN};
  if (c.special === "infinite_nav") return {nav: Infinity};
  return c.input;
}

const results = cases.map(function(c) {
  const out = {name: c.name};
  const fn = c.kind === "hist" ? context._selfHistState : context._selfBookState;
  try {
    const snapshot = materialise(c);
    const before = JSON.stringify(snapshot);
    out.result = fn(snapshot, c.settled);
    out.mutated = JSON.stringify(snapshot) !== before;
  } catch (error) {
    out.error = String((error && error.message) || error);
  }
  return out;
});
console.log(JSON.stringify(results));
"""

RENDER_PRELUDE = PRELUDE + "\nvar window = {};\n"

RENDER_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const prelude = fs.readFileSync(process.argv[1], "utf8");
const source = fs.readFileSync(process.argv[2], "utf8");
const payload = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const context = vm.createContext({});
vm.runInContext(prelude, context, {filename: "prelude.js"});
vm.runInContext(source, context, {filename: "self_render.js"});

// Seed the element registry with the SHIPPED static markup so "untouched" is measurable.
for (const id of Object.keys(payload.seed || {})) {
  context.__els[id] = context.__mk(payload.seed[id]);
}
// Optional prior DOM state (e.g. a previous unavailable render) that the renderer must clear.
for (const id of Object.keys(payload.pre_attrs || {})) {
  Object.assign(context.E(id).attrs, payload.pre_attrs[id]);
}

// Feed the REAL API payloads straight into the shipped renderers' globals.
context._self = payload.book;
context._selfSettled = payload.settled === true;
context._selfHist = payload.history;
context._selfHistSettled = payload.settled === true;

const errors = [];
for (const name of payload.calls) {
  try {
    context[name]();
  } catch (error) {
    errors.push(name + ": " + String((error && error.message) || error));
  }
}

const els = {};
for (const id of Object.keys(context.__els)) {
  const el = context.__els[id];
  els[id] = {textContent: el.textContent, className: el.className,
             innerHTML: el.innerHTML, hidden: el.hidden, attrs: el.attrs};
}
const rendered = JSON.stringify(els);
console.log(JSON.stringify({
  errors: errors,
  elements: els,
  mktLabelUnknown: context._mktLabel(payload.market === "__undefined__" ? undefined : payload.market),
  containsFabricatedNav: rendered.indexOf("1000000") !== -1,
}));
"""


def _run_node(tmp_path, name: str, prelude: str, source: str, arg3, harness: str):
    node = shutil.which("node")
    assert node is not None, "node is required to execute the shipped dashboard helpers"
    prelude_path = tmp_path / f"{name}.prelude.js"
    prelude_path.write_text(prelude, encoding="utf-8")
    source_path = tmp_path / f"{name}.js"
    source_path.write_text(source, encoding="utf-8")
    arg_path = tmp_path / f"{name}.arg.json"
    arg_path.write_text(json.dumps(arg3), encoding="utf-8")

    completed = subprocess.run(
        [node, "-e", harness, str(prelude_path), str(source_path), str(arg_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


# ── 5. helper contract in node ────────────────────────────────────────────────


@requires_node
def test_book_state_contract(tmp_path):
    cases = [
        {"name": "pending_not_settled", "kind": "book", "settled": False, "special": "null"},
        {"name": "pending_with_book", "kind": "book", "settled": False, "input": {"nav": 123456.78}},
        {"name": "ok", "kind": "book", "settled": True, "input": {"nav": 123456.78}},
        {"name": "status_unavailable", "kind": "book", "settled": True,
         "input": {"status": "unavailable", "nav": None}},
        {"name": "nav_missing", "kind": "book", "settled": True, "input": {"cash": 1.0}},
        {"name": "nav_null", "kind": "book", "settled": True, "input": {"nav": None}},
        {"name": "nav_nan", "kind": "book", "settled": True, "special": "nan_nav"},
        {"name": "nav_infinite", "kind": "book", "settled": True, "special": "infinite_nav"},
        {"name": "nav_string", "kind": "book", "settled": True, "input": {"nav": "123456.78"}},
        {"name": "null_book", "kind": "book", "settled": True, "special": "null"},
        {"name": "undefined_book", "kind": "book", "settled": True, "special": "undefined"},
        {"name": "scalar_book", "kind": "book", "settled": True, "input": "healthy"},
    ]
    results = _run_node(tmp_path, "helpers", "", _helpers_source(), cases, HELPER_HARNESS)
    assert isinstance(results, list)
    got = {r["name"]: r for r in results}

    for name in ("pending_not_settled", "pending_with_book"):
        assert "error" not in got[name], got[name].get("error")
        assert got[name]["result"] == "pending", name
    assert got["ok"]["result"] == "ok"
    assert got["ok"]["mutated"] is False, "the helper must not rewrite the book it was handed"
    for name in ("status_unavailable", "nav_missing", "nav_null", "nav_nan", "nav_infinite",
                 "nav_string", "null_book", "undefined_book", "scalar_book"):
        assert "error" not in got[name], got[name].get("error")
        assert got[name]["result"] == "unavailable", name


@requires_node
def test_hist_state_contract(tmp_path):
    cases = [
        {"name": "pending", "kind": "hist", "settled": False, "special": "null"},
        {"name": "ok", "kind": "hist", "settled": True, "input": {"history": []}},
        {"name": "status_unavailable", "kind": "hist", "settled": True,
         "input": {"status": "unavailable", "history": []}},
        {"name": "history_missing", "kind": "hist", "settled": True, "input": {"n_closed": 3}},
        {"name": "history_null", "kind": "hist", "settled": True, "input": {"history": None}},
        {"name": "history_scalar", "kind": "hist", "settled": True, "input": {"history": "none"}},
        {"name": "null_hist", "kind": "hist", "settled": True, "special": "null"},
        {"name": "undefined_hist", "kind": "hist", "settled": True, "special": "undefined"},
    ]
    results = _run_node(tmp_path, "helpers2", "", _helpers_source(), cases, HELPER_HARNESS)
    got = {r["name"]: r for r in results}

    assert got["pending"]["result"] == "pending"
    assert got["ok"]["result"] == "ok"
    assert got["ok"]["mutated"] is False
    for name in ("status_unavailable", "history_missing", "history_null", "history_scalar",
                 "null_hist", "undefined_hist"):
        assert "error" not in got[name], got[name].get("error")
        assert got[name]["result"] == "unavailable", name


# ── 6. the API and the renderer must agree ────────────────────────────────────


def _unreadable_api_payloads(monkeypatch) -> tuple[dict, dict]:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "_load_account", _boom())
    monkeypatch.setattr(self_directed, "_market_status", _boom())
    return (json.loads(web.api_self_directed().body),
            json.loads(web.api_self_directed_history().body))


def _shipped_seed(element_id: str) -> str:
    """The static seed text the browser would already be showing before any fetch settles."""
    match = re.search(r'id="' + element_id + r'"[^>]*>([^<]*)<', HTML)
    assert match, f"static seed for {element_id} not found"
    return match.group(1)


def _render(tmp_path, tag: str, book, hist, settled: bool, market="__undefined__",
            pre_attrs=None):
    payload = {
        "pre_attrs": pre_attrs or {},
        "calls": ["renderSelfHeader", "renderSelfAlloc", "renderSelfPositions", "renderSelfHistory"],
        "book": book,
        "history": hist,
        "settled": settled,
        "market": market,
        "seed": {i: _shipped_seed(i) for i in
                 ("sd-nav", "sd-cash", "sd-invested", "sd-unreal", "sd-return")},
    }
    return _run_node(tmp_path, tag, RENDER_PRELUDE, _render_source(), payload, RENDER_HARNESS)


@requires_node
def test_unavailable_api_payload_renders_unavailable_everywhere(tmp_path, monkeypatch):
    """The headline agreement test: a failed read may not render as a $1M book or an empty one."""
    book, hist = _unreadable_api_payloads(monkeypatch)
    out = _render(tmp_path, "unavailable", book, hist, True)

    assert out["errors"] == [], out["errors"]
    els = out["elements"]

    # NAV reads `unavailable`, and the reason line is shown.
    assert els["sd-nav"]["textContent"] == "sd.unavailable"
    # The hero numeral slot is marked as a state (muted), never given a value's emphasis.
    assert els["sd-nav"]["attrs"] == {"data-availability": "unavailable"}
    # ...and the heartbeat stops signalling a live, healthy book.
    assert els["sd-hb"]["attrs"] == {"data-availability": "unavailable"}
    assert els["sd-nav-status"]["textContent"] == "sd.unavailable_reason"
    assert els["sd-nav-status"]["hidden"] is False

    # Every balance tile is `unavailable` in the neutral class — no number, no zero.
    for tile in ("sd-cash", "sd-invested", "sd-unreal", "sd-return"):
        assert els[tile]["textContent"] == "sd.unavailable", tile
        assert els[tile]["className"] == "mm-perf-stat-value neu", tile
    assert els["sd-cash-pct"]["textContent"] == ""
    assert els["sd-gross"]["textContent"] == ""

    # An unreadable book is NOT an empty book: neither the "100% cash" nor "no positions" claim.
    assert "sd.unavailable_reason" in els["sd-alloc-host"]["innerHTML"]
    assert "sd.alloc_empty" not in els["sd-alloc-host"]["innerHTML"]
    assert "sd.unavailable_reason" in els["sd-positions-host"]["innerHTML"]

    # An unreadable blotter is NOT an empty blotter.
    assert "sd.hist_unavailable" in els["sd-history-host"]["innerHTML"]
    assert "sd.hist_empty" not in els["sd-history-host"]["innerHTML"]

    # No fabricated starting capital survives anywhere in the rendered tree.
    assert out["containsFabricatedNav"] is False

    # An unknown market is `unavailable`, never an unverified "Closed — next open".
    assert out["mktLabelUnknown"] == {"cls": "closed", "txt": "sd.mkt.unknown"}


@requires_node
def test_success_api_payload_renders_the_api_nav_exactly(tmp_path, monkeypatch):
    """The positive control: a readable book renders the API's own NAV — agreement, not a fallback."""
    from app import web
    from portfolio import self_directed

    payload = _book_payload()
    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {}})
    monkeypatch.setattr(self_directed, "_load_pending", lambda: [])
    monkeypatch.setattr(web, "_live_prices", lambda tickers, **_kw: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kwargs: payload)

    data = json.loads(web.api_self_directed().body)
    hist = {"history": [], "pending": [], "realized_total": 0.0,
            "n_closed": 0, "n_buys": 0, "win_rate": None}
    # Start from a previous unavailable render: a readable book must clear the muted state.
    out = _render(tmp_path, "success", data, hist, True,
                  pre_attrs={"sd-nav": {"data-availability": "unavailable"},
                             "sd-hb": {"data-availability": "unavailable"}})

    assert out["errors"] == [], out["errors"]
    els = out["elements"]

    # The rendered NAV is the API NAV — no fallback number can stand in for it.
    assert els["sd-nav"]["textContent"] == "$123456.78"
    assert els["sd-nav"]["attrs"] == {}, "a readable book must clear the unavailable state"
    assert els["sd-hb"]["attrs"] == {}, "a readable book restores the live heartbeat"
    assert els["sd-nav"]["textContent"] != "1000000"
    assert els["sd-nav-status"]["hidden"] is True
    assert els["sd-nav-status"]["textContent"] == ""

    # A genuinely empty book still renders the genuinely-empty copy (empty ≠ unavailable).
    assert "sd.alloc_empty" in els["sd-alloc-host"]["innerHTML"]
    assert "sd.unavailable_reason" not in els["sd-alloc-host"]["innerHTML"]
    assert "sd.hist_empty" in els["sd-history-host"]["innerHTML"]
    assert "sd.hist_unavailable" not in els["sd-history-host"]["innerHTML"]
    assert out["containsFabricatedNav"] is False

    # A present market still renders its real session.
    assert out["mktLabelUnknown"] == {"cls": "closed", "txt": "sd.mkt.unknown"}


@requires_node
def test_unsettled_load_leaves_the_preload_placeholders_untouched(tmp_path):
    """Before any load settles, the neutral `—` seeds stand: pending is not unavailable."""
    out = _render(tmp_path, "pending", None, None, False)

    assert out["errors"] == [], out["errors"]
    els = out["elements"]
    assert _shipped_seed("sd-nav") == "—"
    for tile in ("sd-nav", "sd-cash", "sd-invested", "sd-unreal", "sd-return"):
        assert els[tile]["textContent"] == "—", f"{tile} must keep its pre-load placeholder"
    assert els["sd-nav-status"]["hidden"] is True
    assert els["sd-nav-status"]["textContent"] == ""
    # A pending load is not an unreadable one: the alloc/history hosts keep their shipped
    # pre-load rendering rather than claiming `unavailable`.
    assert "sd.unavailable_reason" not in els["sd-alloc-host"]["innerHTML"]
    assert "sd.hist_unavailable" not in els["sd-history-host"]["innerHTML"]
    assert out["containsFabricatedNav"] is False