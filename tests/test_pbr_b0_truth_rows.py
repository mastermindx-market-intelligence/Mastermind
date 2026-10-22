"""PBR B0 — spec §3 vocabulary and §6 display-rule truth rows, executed against shipped source.

Spec: ``docs/superpowers/specs/2026-10-22-pbr-product-views.md`` §3 (state vocabulary) and §6
(display rules 1–3, 6–8, 12–15), plus the D-ACCT-1 display rule: an existing-but-invalid
account file renders ONE canonical "book unavailable — state invalid" cell carrying the
quarantine sha16, never a zero NAV, an empty curve or "No positions".

The renderers run in a Node ``vm`` against the REAL sliced dashboard source (I18N table,
``t()``, ``esc``, formatters, the PBR-B0 primitives and each renderer) with a minimal stub DOM:
string presence alone is not proof of behaviour. Peripheral helpers a renderer calls but this
file does not bind (``securityName``, ``pnlCell``, ``helpIcon``, ``_heldPendingChange``,
``_safeRender``, ``renderAutoBanner``, ``renderPortfolioSwitch``) are stubbed and named here.

Truth rules bound: TR-C (an absent benchmark is a word, never 0 and never a down arrow) and
TR-D (an unknown value is never rendered as zero; a flat unpriced day is not a 0.00% day).
Every quantity is a synthetic round number — this repository is public.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "app" / "static" / "index.html").read_text()

requires_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is required to execute the shipped dashboard renderers",
)

SHA16 = "abababababababab"
INVALID = {"status": "invalid", "quarantine_sha16": SHA16}

# Spec §3 — binding strings (EN, ZH). The SPA must carry these exactly.
VOCAB = {
    "state.loading": ("Loading", "加载中"),
    "state.empty": ("Empty", "暂无"),
    "state.stale": ("Behind", "滞后"),
    "state.partial": ("Partial", "部分"),
    "state.error": ("Couldn't load", "加载失败"),
    "state.closed_market": ("Market closed", "休市"),
    "state.benchmark_unavailable": ("Benchmark unavailable", "基准不可用"),
    "state.provisional": ("Provisional", "暂定"),
    "state.withheld": ("Withheld", "暂不估值"),
    "state.unverified": ("Unverified", "未核实"),
    "state.queued": ("Queued", "已排队"),
    "state.unavailable": ("Unavailable", "不可用"),
    "state.qualified": ("Qualified", "已核实"),
    "state.retry": ("Retry", "重试"),
    "state.see_all": ("See all {n}", "查看全部 {n} 项"),
    "state.risk_unavailable": ("risk snapshot unavailable", "风险快照不可用"),
    "state.pricing_partial": (
        "pricing summary missing — showing the last complete holdings",
        "缺少定价汇总 — 显示上次完整持仓",
    ),
    "state.weight_unavailable": ("Unavailable", "不可用"),
    "state.book_invalid": ("Book unavailable — state invalid", "账本不可用 — 状态无效"),
    "state.quarantine_ref": ("Quarantine ref {sha}", "隔离编号 {sha}"),
}

FORBIDDEN_EMPTY = ("$1,000,000", "1,000,000", "0.00%", "0 actual", "HOLDING", "NaN", "undefined")


# ── shipped-source slicing ────────────────────────────────────────────────────


def _fn(name: str) -> str:
    """A top-level function, from its declaration to its first column-0 closing brace."""
    start = HTML.index("\nfunction " + name + "(") + 1
    return HTML[start:HTML.index("\n}\n", start) + 3]


def _var(name: str) -> str:
    """A top-level ``var name = ...`` statement (single line, or a block ending ``};``)."""
    start = HTML.index("\nvar " + name + " = ") + 1
    line = HTML[start:HTML.index("\n", start)]
    if line.rstrip().endswith(";") and line.count("{") == line.count("}"):
        return line + "\n"
    return HTML[start:HTML.index("\n};\n", start) + 4]


def _marked(begin: str, end: str) -> str:
    start = HTML.index(begin)
    return HTML[start:HTML.index(end, start) + len(end)]


def _i18n() -> str:
    start = HTML.index("var I18N = {")
    return HTML[start:HTML.index("\n};\n", start) + 4]


PRELUDE = r"""
var __lang = 'en';
var __els = {};
function __mk(id) {
  return { id: id, textContent: '', innerHTML: '', className: '', style: {}, clientWidth: 900,
           previousElementSibling: null, querySelector: function() { return null; },
           addEventListener: function() {} };
}
var document = {
  documentElement: { getAttribute: function(k) { return k === 'data-lang' ? __lang : null; } },
  getElementById: function() { return null; },
  querySelector: function() { return null; }
};
var window = {};
var E = function(id) { return __els[id] || null; };
var IDS = ['perf-evidence', 'perf-nav-label', 'perf-nav', 'perf-ret', 'perf-since',
  'perf-bench-label', 'perf-spy', 'perf-day', 'perf-day-range', 'perf-dd', 'perf-dd-range',
  'perf-cash-lbl', 'ec-wrap', 'ec-leg-portfolio', 'ec-leg-bench-line', 'ec-leg-bench',
  'ec-range-label', 'ec-legend', 'seg-lead', 'lbl-lead', 'seg-conv', 'lbl-conv', 'seg-cash',
  'lbl-cash', 'lbl-gross', 'safety', 'positions', 'live-marks-status'];
IDS.forEach(function(id) { __els[id] = __mk(id); });
__els['ec-leg-bench-line'].className = 'mm-ec-leg-line';
__els['ec-leg-bench'].previousElementSibling = __els['ec-leg-bench-line'];
__els['perf-nav'].previousElementSibling = __els['perf-nav-label'];
var _book = null, _perf = null, _liveMarks = null, _risk = null, _trades = null;
var _portfolios = [], _portfolio = 'autonomous', _expandedIdx = null, _self = null;
var _selfSettled = false;
// Peripheral callees this file does not bind (named in the module docstring).
var securityName = function() { return ''; };
var pnlCell = function() { return { cls: '', txt: '—' }; };
var helpIcon = function() { return ''; };
var _heldPendingChange = function() { return null; };
var __rendered = [];
var _safeRender = function(name, fn) { __rendered.push(name); };
var renderAutoBanner = function() {};
var renderPortfolioSwitch = function() {};
var renderSelf = function() {};
function __dump() {
  var out = {};
  IDS.forEach(function(id) {
    var el = __els[id];
    out[id] = { text: String(el.textContent), html: String(el.innerHTML),
                cls: String(el.className), display: el.style.display == null ? '' : String(el.style.display),
                width: el.style.width == null ? '' : String(el.style.width) };
  });
  return out;
}
"""


def _source() -> str:
    return "\n".join([
        _i18n(),
        _fn("t"),
        _marked("// PBR-B0-PRIMITIVES:BEGIN", "// PBR-B0-PRIMITIVES:END"),
        _var("esc"),
        _var("pct"),
        _var("pctInt"),
        _var("fmtDate"),
        _var("_parseLocalDate"),
        _var("fmtDateShort"),
        _fn("_ccySymOf"),
        _fn("_ccySym"),
        _var("fmtNav"),
        _var("fmtPctSign"),
        _fn("_performanceEvidenceText"),
        _fn("renderPerformance"),
        _fn("_equityAreaPath"),
        _fn("renderEquityCurve"),
        _fn("renderAllocation"),
        _fn("renderSafety"),
        _fn("renderPositions"),
        _fn("_liveTime"),
        _fn("renderLiveMarksStatus"),
        _fn("_mergeLiveMarks"),
    ])


def _run(tmp_path: Path, scenario: str, lang: str = "en") -> dict:
    """Run ``scenario`` (JS) after the real source; return the stub DOM plus ``__result``."""
    script = (PRELUDE + "\n" + _source() + "\n__lang = " + json.dumps(lang) + ";\n" +
              "var __result = null;\n" + scenario + "\n" +
              "process.stdout.write(JSON.stringify({dom: __dump(), result: __result}));\n")
    path = tmp_path / "run.js"
    path.write_text(script)
    proc = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[-4000:]
    return json.loads(proc.stdout)


def _slot(dom: dict, el: str) -> str:
    return dom[el]["text"] + dom[el]["html"]


# ── T1 vocabulary ─────────────────────────────────────────────────────────────


def test_t1_state_vocabulary_is_exact_in_en_and_zh():
    assert HTML.count("// PBR-B0-VOCAB:BEGIN") == 1
    assert HTML.count("// PBR-B0-VOCAB:END") == 1
    block = _marked("// PBR-B0-VOCAB:BEGIN", "// PBR-B0-VOCAB:END")
    found = {}
    for m in re.finditer(r"'(state\.[a-z_]+)':\s*\{\s*en:\s*(\"[^\"]*\"|'[^']*'),\s*zh:\s*'([^']*)'\s*\}",
                         block):
        found[m.group(1)] = (m.group(2)[1:-1], m.group(3))
    assert found == VOCAB


# ── T2 primitives ─────────────────────────────────────────────────────────────


@requires_node
def test_t2_primitives_in_en_and_zh(tmp_path):
    scenario = r"""
__result = {
  plain: _unavailHtml(), why: _unavailHtml('no quote <b>'),
  over: _overflowHtml(12, '#/x'), badge: _epiBadgeHtml('unverified'),
  unknown: _epiBadgeHtml('made-up'), none: _epiBadgeHtml()
};
"""
    en = _run(tmp_path, scenario)["result"]
    assert en["plain"] == '<span class="mm-unavail">Unavailable</span>'
    assert en["why"] == ('<span class="mm-unavail">Unavailable</span>'
                         '<span class="mm-unavail-why">no quote &lt;b&gt;</span>')
    assert en["over"] == '<a class="mm-overflow" href="#/x">See all 12</a>'
    assert en["badge"] == '<span class="mm-epi-badge unverified">Unverified</span>'
    assert en["unknown"] == "" and en["none"] == ""
    zh = _run(tmp_path, scenario, "zh")["result"]
    assert zh["plain"] == '<span class="mm-unavail">不可用</span>'
    assert ">查看全部 12 项<" in zh["over"]
    assert ">未核实<" in zh["badge"]


# ── T3 renderPerformance ──────────────────────────────────────────────────────

PERF_SLOTS = ("perf-nav", "perf-ret", "perf-day", "perf-dd")


@requires_node
@pytest.mark.parametrize("lang,word", [("en", "Unavailable"), ("zh", "不可用")])
def test_t3_absent_performance_values_render_the_word(tmp_path, lang, word):
    dom = _run(tmp_path, r"""
_perf = {availability: {status: 'unavailable', history_status: 'unavailable'},
         current_nav: null, total_return_pct: null, day_change_pct: null,
         max_drawdown_pct: null, cash: null, vs_benchmark_pct: null};
renderPerformance();
""", lang)["dom"]
    for el in PERF_SLOTS:
        s = _slot(dom, el)
        assert word in s, el
        for bad in ("—", "0.00%", "$0", "NaN"):
            assert bad not in s, (el, bad)
        assert dom[el]["cls"] == "mm-perf-stat-value neu" or el == "perf-nav"
    assert word in _slot(dom, "perf-cash-lbl")
    assert "$" not in _slot(dom, "perf-cash-lbl")
    bench = "Benchmark unavailable" if lang == "en" else "基准不可用"
    assert bench in _slot(dom, "perf-spy")
    assert "0.00%" not in _slot(dom, "perf-spy") and "-" not in dom["perf-spy"]["text"]


@requires_node
def test_t3_present_values_render_exactly_as_master(tmp_path):
    # Expected strings are master's fmtNav / fmtPctSign / drawdown output for this input.
    dom = _run(tmp_path, r"""
_perf = {availability: {status: 'qualified'}, current_nav: 1234567.89, total_return_pct: 12.3456,
         vs_benchmark_pct: -1.5, day_change_pct: 0.25, max_drawdown_pct: -3.2, cash: 50000};
renderPerformance();
""")["dom"]
    assert dom["perf-nav"]["text"] == "$1,234,568"
    assert (dom["perf-ret"]["text"], dom["perf-ret"]["cls"]) == ("+12.35%", "mm-perf-stat-value pos")
    assert (dom["perf-spy"]["text"], dom["perf-spy"]["cls"]) == ("-1.50%", "mm-perf-stat-value neg")
    assert (dom["perf-day"]["text"], dom["perf-day"]["cls"]) == ("+0.25%", "mm-perf-stat-value pos")
    assert (dom["perf-dd"]["text"], dom["perf-dd"]["cls"]) == ("-3.20%", "mm-perf-stat-value neg")
    assert dom["perf-cash-lbl"]["text"] == "cash: $50,000"
    assert "mm-epi-badge" not in dom["perf-nav-label"]["html"]


@requires_node
def test_t3_payload_without_availability_is_badged_unverified(tmp_path):
    dom = _run(tmp_path, "_perf = {current_nav: 1000}; renderPerformance();")["dom"]
    assert 'mm-epi-badge unverified' in dom["perf-nav-label"]["html"]
    assert ">Unverified<" in dom["perf-nav-label"]["html"]


# ── T4 renderEquityCurve ──────────────────────────────────────────────────────

REALISED = [("2026-03-02", 1050000, 1010000), ("2026-03-03", 1062000, 1012000),
            ("2026-03-04", 1058000, 1011000), ("2026-03-05", 1074000, 1016000),
            ("2026-03-06", 1080000, 1019000)]


def _curve_scenario(prefix_days: int, spy: bool, realised: bool = True) -> str:
    series = []
    for i in range(prefix_days):
        series.append({"date": "2026-01-%02d" % (i + 1), "nav": None, "spy_nav": None,
                       "kind": "pre_inception"})
    if realised:
        for d, nav, spy_nav in REALISED:
            series.append({"date": d, "nav": nav, "spy_nav": spy_nav if spy else None,
                           "kind": "realized"})
    perf = {"series": series, "starting_nav": 1000000, "benchmark": "SPY",
            "benchmark_name": "S&P 500", "realized_since": REALISED[0][0] if realised else None}
    return "_perf = " + json.dumps(perf) + ";\nrenderEquityCurve();\n"


_UP_PATH = re.compile(r'<path d="([^"]*)" fill="none" stroke="var\(--up\)" stroke-width="2.2"')


def _ys(d: str) -> list[str]:
    return re.findall(r"[ML][-\d.]+ ([-\d.]+)", d)


@requires_node
def test_t4_synthetic_prefix_does_not_rescale_the_realised_track(tmp_path):
    plain = _run(tmp_path, _curve_scenario(0, spy=True))["dom"]["ec-wrap"]["html"]
    padded = _run(tmp_path, _curve_scenario(40, spy=True))["dom"]["ec-wrap"]["html"]
    a, b = _UP_PATH.search(plain), _UP_PATH.search(padded)
    assert a and b
    assert _ys(a.group(1)) == _ys(b.group(1)) and len(_ys(a.group(1))) == len(REALISED)
    # The synthetic capital reference is dashed and muted, never a solid --up line.
    assert re.search(r'stroke="var\(--muted\)" stroke-width="1.5" stroke-dasharray="4 3"', padded)


@requires_node
def test_t4_all_synthetic_series_is_dashed_and_muted(tmp_path):
    html = _run(tmp_path, _curve_scenario(10, spy=False, realised=False))["dom"]["ec-wrap"]["html"]
    assert 'stroke-dasharray="4 3"' in html and "var(--muted)" in html
    assert not _UP_PATH.search(html)


@requires_node
@pytest.mark.parametrize("lang,word", [("en", "Benchmark unavailable"), ("zh", "基准不可用")])
def test_t4_no_finite_benchmark_draws_no_reference_and_names_it(tmp_path, lang, word):
    dom = _run(tmp_path, _curve_scenario(0, spy=False), lang)["dom"]
    assert 'stroke-dasharray="5 3"' not in dom["ec-wrap"]["html"]
    assert dom["ec-leg-bench"]["text"] == word
    assert dom["ec-leg-bench-line"]["display"] == "none"


@requires_node
def test_t4_finite_benchmark_keeps_legend_and_path(tmp_path):
    dom = _run(tmp_path, _curve_scenario(0, spy=True))["dom"]
    assert 'stroke-dasharray="5 3"' in dom["ec-wrap"]["html"]
    assert dom["ec-leg-bench"]["text"] == "S&P 500 (SPY) (reference series)"
    assert dom["ec-leg-bench-line"]["display"] == ""
    assert "NaN" not in dom["ec-wrap"]["html"]


# ── T5 renderAllocation ───────────────────────────────────────────────────────


@requires_node
def test_t5_absent_sleeve_weight_hides_segment_and_names_it(tmp_path):
    dom = _run(tmp_path, "_book = {sleeves: {leadership: 0.5, cash: 0.5}}; renderAllocation();")["dom"]
    assert dom["seg-conv"]["display"] == "none" and dom["seg-conv"]["text"] == ""
    assert dom["lbl-conv"]["text"] == "Conviction Unavailable"
    assert "0%" not in dom["lbl-conv"]["text"] + dom["seg-conv"]["text"]
    assert dom["lbl-lead"]["text"] == "Leadership 50%" and dom["seg-lead"]["width"] == "50.0%"
    assert dom["lbl-cash"]["text"] == "Cash 50%"
    zh = _run(tmp_path, "_book = {sleeves: {leadership: 0.5, cash: 0.5}}; renderAllocation();", "zh")
    assert zh["dom"]["lbl-conv"]["text"] == "重仓 不可用"


# ── T6 renderSafety ───────────────────────────────────────────────────────────


@requires_node
def test_t6_missing_risk_metrics_render_the_word_not_zero(tmp_path):
    html = _run(tmp_path, r"""
_risk = {safety_score: 61, grade: 'C', metrics: {max_drawdown_pct: -12.5}};
renderSafety();
""")["dom"]["safety"]["html"]
    assert "0 actual" not in html and "0.0%" not in html and "NaN" not in html
    eff = html.index("Effective names")
    cash = html.index("Cash buffer")
    for at in (eff, cash):
        tile = html[at:at + 900]
        assert "Unavailable" in tile and "risk snapshot unavailable" in tile


# ── T7 renderPositions verdict ────────────────────────────────────────────────


@requires_node
def test_t7_absent_verdict_is_unavailable_and_explicit_hold_unchanged(tmp_path):
    out = _run(tmp_path, r"""
_book = {positions: [{ticker: 'SYNA', weight: 0.1}]};
renderPositions();
var absentHtml = E('positions').innerHTML;
_book = {positions: [{ticker: 'SYNA', weight: 0.1, verdict: 'hold'}]};
renderPositions();
__result = {absent: absentHtml, hold: E('positions').innerHTML};
""")["result"]
    assert '<td class="neu"><span class="mm-unavail">Unavailable</span></td>' in out["absent"]
    assert "HOLDING" not in out["absent"] and "mm-verdict-chip" not in out["absent"]
    assert '<td><span class="mm-verdict-chip hold">HOLDING</span></td>' in out["hold"]


# ── T8 renderLiveMarksStatus ──────────────────────────────────────────────────


@requires_node
@pytest.mark.parametrize("session", [{"state": "mystery", "market": "US"}, {"market": "US"}])
def test_t8_unknown_session_state_is_unavailable_not_closed(tmp_path, session):
    scenario = ("_liveMarks = " + json.dumps({"portfolio": "autonomous", "session": session,
                                             "positions": []}) +
                ";\nrenderLiveMarksStatus();\n")
    en = _run(tmp_path, scenario)["dom"]["live-marks-status"]["html"]
    assert "US Unavailable" in en and "closed" not in en
    zh = _run(tmp_path, scenario, "zh")["dom"]["live-marks-status"]["html"]
    assert "US 不可用" in zh and "收市" not in zh


# ── T9 _mergeLiveMarks ────────────────────────────────────────────────────────


@requires_node
def test_t9_payload_without_pricing_keeps_cached_rows_and_says_partial(tmp_path):
    out = _run(tmp_path, r"""
var rows = [{ticker: 'SYNA', verdict: 'hold', weight: 0.1}];
_book = {positions: rows};
_mergeLiveMarks({portfolio: 'autonomous', session: {state: 'open', is_open: true, market: 'US'},
                 positions: [{ticker: 'SYNA', current_price: 110}, {ticker: 'SYNZ', current_price: 5}],
                 performance: {}});
__result = {same: _book.positions === rows, tickers: _book.positions.map(function(r) { return r.ticker; }),
            partial: _liveMarks.pricing_partial === true, rendered: __rendered};
""")
    res, dom = out["result"], out["dom"]
    assert res["same"] is True and res["tickers"] == ["SYNA"]
    assert res["partial"] is True
    status = dom["live-marks-status"]["html"]
    assert "Partial — pricing summary missing — showing the last complete holdings" in status
    assert "no held tickers to price" not in status


@requires_node
def test_t9_payload_with_pricing_still_reconciles(tmp_path):
    res = _run(tmp_path, r"""
_book = {positions: [{ticker: 'SYNA', verdict: 'hold', weight: 0.1}]};
_mergeLiveMarks({portfolio: 'autonomous', session: {state: 'open', is_open: true, market: 'US'},
                 positions: [{ticker: 'SYNA', current_price: 110}, {ticker: 'SYNZ', current_price: 5}],
                 pricing: {total_positions: 2, priced_positions: 2, complete: true}, performance: {}});
__result = {tickers: _book.positions.map(function(r) { return r.ticker; }),
            partial: !!_liveMarks.pricing_partial};
""")["result"]
    assert res == {"tickers": ["SYNA", "SYNZ"], "partial": False}


# ── T10 _archived_performance (python) ────────────────────────────────────────


def _archived(tmp_path, monkeypatch, *, starting_nav, rows):
    from app import web

    (tmp_path / "account.json").write_text(json.dumps({"starting_nav": starting_nav, "cash": 0}))
    (tmp_path / "latest.json").write_text("{}")
    (tmp_path / "nav_history.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: tmp_path)
    reg = web._portfolio_registry
    monkeypatch.setattr(reg, "get", lambda pid: {})
    monkeypatch.setattr(reg, "benchmark", lambda pid: "SPY")
    monkeypatch.setattr(reg, "benchmark_name", lambda pid: "S&P 500")
    monkeypatch.setattr(reg, "benchmark_name_zh", lambda pid: "标普500")
    return web._archived_performance("synthetic_archived")


def test_t10_zero_starting_nav_has_no_return(tmp_path, monkeypatch):
    out = _archived(tmp_path, monkeypatch, starting_nav=0, rows=[
        {"date": "2026-03-02", "nav": 100000, "invested": 50000, "spy_nav": 100000},
        {"date": "2026-03-03", "nav": 101000, "invested": 51000, "spy_nav": 100500}])
    assert out["total_return_pct"] is None and out["vs_benchmark_pct"] is None


def test_t10_flat_unpriced_pair_is_not_a_zero_day(tmp_path, monkeypatch):
    out = _archived(tmp_path, monkeypatch, starting_nav=100000, rows=[
        {"date": "2026-03-02", "nav": 101000, "invested": 60000},
        {"date": "2026-03-03", "nav": 101000, "invested": 60000}])
    assert out["day_change_pct"] is None
    out = _archived(tmp_path, monkeypatch, starting_nav=100000, rows=[
        {"date": "2026-03-02", "nav": 101000},
        {"date": "2026-03-03", "nav": 101000}])
    assert out["day_change_pct"] is None


def test_t10_all_cash_flat_pair_keeps_its_true_zero(tmp_path, monkeypatch):
    out = _archived(tmp_path, monkeypatch, starting_nav=100000, rows=[
        {"date": "2026-03-02", "nav": 100000, "invested": 0},
        {"date": "2026-03-03", "nav": 100000, "invested": 0}])
    assert out["day_change_pct"] == 0.0


def test_t10_moving_pair_matches_master_arithmetic(tmp_path, monkeypatch):
    out = _archived(tmp_path, monkeypatch, starting_nav=100000, rows=[
        {"date": "2026-03-02", "nav": 100000, "invested": 60000, "spy_nav": 100000},
        {"date": "2026-03-03", "nav": 102000, "invested": 62000, "spy_nav": 101000}])
    assert out["day_change_pct"] == round((102000 / 100000 - 1.0) * 100.0, 4)
    assert out["total_return_pct"] == round((102000 / 100000 - 1.0) * 100.0, 4)
    assert out["vs_benchmark_pct"] == round(2.0 - 1.0, 4)


# ── T11 empty-form closure ────────────────────────────────────────────────────

ALL_RENDERERS = r"""
renderPerformance(); renderEquityCurve(); renderAllocation(); renderSafety();
renderPositions(); renderLiveMarksStatus();
"""


@requires_node
@pytest.mark.parametrize("setup", [
    "",  # every global absent
    "_perf = {}; _book = {}; _risk = {metrics: {n: 1}}; "
    "_liveMarks = {portfolio: 'autonomous', positions: []};",
])
@pytest.mark.parametrize("lang", ["en", "zh"])
def test_t11_empty_form_closure(tmp_path, setup, lang):
    dom = _run(tmp_path, setup + ALL_RENDERERS, lang)["dom"]
    combined = "".join(v["text"] + v["html"] for v in dom.values())
    for bad in FORBIDDEN_EMPTY:
        assert bad not in combined, bad
    word = "Unavailable" if lang == "en" else "不可用"
    for el in PERF_SLOTS + ("perf-cash-lbl", "lbl-lead", "lbl-conv", "lbl-cash"):
        assert word in _slot(dom, el), el
    if setup:
        assert word in dom["safety"]["html"]


# ── T12 invalid account (python + node) ───────────────────────────────────────


@pytest.fixture
def no_account_load(monkeypatch):
    from portfolio import paper_account

    def _never(*_a, **_k):
        raise AssertionError("a display probe must never load the account")

    for name in ("_load_account", "_load_account_file", "load_account"):
        monkeypatch.setattr(paper_account, name, _never, raising=False)
    return paper_account


def _status(kind, sha=None):
    def _fn(*_a, path=None, **_k):
        return {"status": kind, "path": str(path), "sha256": sha, "size": None, "problems": []}
    return _fn


def test_t12_probe_reports_invalid_with_sha16(monkeypatch, no_account_load):
    from app import web

    monkeypatch.setattr(no_account_load, "account_file_status", _status("INVALID", "ab" * 32),
                        raising=False)
    assert web._account_state_probe("autonomous") == {"status": "invalid",
                                                      "quarantine_sha16": SHA16}
    # Unreadable bytes carry no sha: the state is still invalid, the ref is absent.
    monkeypatch.setattr(no_account_load, "account_file_status", _status("INVALID", None),
                        raising=False)
    assert web._account_state_probe("autonomous") == {"status": "invalid",
                                                      "quarantine_sha16": None}


@pytest.mark.parametrize("variant", ["VALID", "MISSING", "raises", "absent"])
def test_t12_probe_is_none_otherwise(monkeypatch, no_account_load, variant):
    from app import web

    if variant == "absent":
        monkeypatch.delattr(no_account_load, "account_file_status", raising=False)
    elif variant == "raises":
        def _boom(*_a, **_k):
            raise RuntimeError("synthetic probe failure")
        monkeypatch.setattr(no_account_load, "account_file_status", _boom, raising=False)
    else:
        monkeypatch.setattr(no_account_load, "account_file_status", _status(variant, "cd" * 32),
                            raising=False)
    assert web._account_state_probe("autonomous") is None


FIXED_UNAVAILABLE = {"current_nav": None, "series": [], "availability": {"status": "unavailable"}}


def _perf_route(monkeypatch, paper_account, *, probe_kind, raise_perf):
    from app import web

    if raise_perf:
        def _perf(*_a, **_k):
            raise RuntimeError("synthetic performance failure")
    else:
        def _perf(*_a, **_k):
            return {"current_nav": 100000.0, "series": []}
    monkeypatch.setattr(paper_account, "performance", _perf)
    monkeypatch.setattr(paper_account, "unavailable_performance",
                        lambda *_a, **_k: dict(FIXED_UNAVAILABLE))
    monkeypatch.setattr(paper_account, "account_file_status", _status(probe_kind, "ab" * 32),
                        raising=False)
    monkeypatch.setattr(web._portfolio_registry, "is_archived", lambda pid: False)
    return web.api_performance("autonomous")


@pytest.mark.parametrize("raise_perf", [True, False])
def test_t12_api_performance_carries_invalid_state(monkeypatch, no_account_load, raise_perf):
    resp = _perf_route(monkeypatch, no_account_load, probe_kind="INVALID", raise_perf=raise_perf)
    body = json.loads(resp.body)
    assert body["account_state"] == {"status": "invalid", "quarantine_sha16": SHA16}


def test_t12_api_performance_valid_is_byte_identical(monkeypatch, no_account_load):
    resp = _perf_route(monkeypatch, no_account_load, probe_kind="VALID", raise_perf=True)
    assert resp.body == JSONResponse(dict(FIXED_UNAVAILABLE)).body
    assert b"account_state" not in resp.body
    resp = _perf_route(monkeypatch, no_account_load, probe_kind="VALID", raise_perf=False)
    assert resp.body == JSONResponse({"current_nav": 100000.0, "series": []}).body


INVALID_SCENARIO = r"""
_perf = {account_state: STATE, current_nav: 0, cash: 0, total_return_pct: 0, day_change_pct: 0,
         max_drawdown_pct: 0, series: [{date: '2026-03-02', nav: 0, spy_nav: 0, kind: 'realized'}]};
_book = {account_state: STATE, positions: [{ticker: 'SYNA', weight: 0.1, verdict: 'hold'}]};
renderPerformance(); renderEquityCurve(); renderPositions();
"""


@requires_node
@pytest.mark.parametrize("lang,word,ref", [
    ("en", "Book unavailable — state invalid", "Quarantine ref " + SHA16),
    ("zh", "账本不可用 — 状态无效", "隔离编号 " + SHA16),
])
def test_t12_invalid_state_renders_one_canonical_cell(tmp_path, lang, word, ref):
    dom = _run(tmp_path, INVALID_SCENARIO.replace("STATE", json.dumps(INVALID)), lang)["dom"]
    for el in ("perf-nav", "ec-wrap", "positions"):
        html = dom[el]["html"]
        assert word in html and ref in html, el
        for bad in ("$0", "0.00%", "No positions", "暂无持仓", "NaN", "HOLDING"):
            assert bad not in html, (el, bad)
    assert "<path" not in dom["ec-wrap"]["html"]
    assert dom["ec-legend"]["display"] == "none"
    for el in ("perf-ret", "perf-day", "perf-dd"):
        assert "0.00%" not in _slot(dom, el)


@requires_node
def test_t12_malformed_sha_is_never_rendered(tmp_path):
    state = {"status": "invalid", "quarantine_sha16": "<b>x"}
    dom = _run(tmp_path, INVALID_SCENARIO.replace("STATE", json.dumps(state)))["dom"]
    for el in ("perf-nav", "ec-wrap", "positions"):
        html = dom[el]["html"]
        assert "Book unavailable — state invalid" in html
        assert "<b>x" not in html and "&lt;b&gt;x" not in html and "Quarantine ref" not in html


@requires_node
def test_t12_live_marks_invalid_flag_clears_on_next_valid_tick(tmp_path):
    out = _run(tmp_path, r"""
_book = {positions: [{ticker: 'SYNA', verdict: 'hold', weight: 0.1}]};
_mergeLiveMarks({portfolio: 'autonomous', account_state: STATE, positions: [], performance: {}});
var during = _accountStateInvalid() ? 'invalid' : 'valid';
var bookFlag = !!_book.account_state;
_mergeLiveMarks({portfolio: 'autonomous', session: {state: 'open', is_open: true, market: 'US'},
                 positions: [{ticker: 'SYNA', current_price: 110}],
                 pricing: {total_positions: 1, priced_positions: 1, complete: true}, performance: {}});
__result = {during: during, bookFlag: bookFlag, after: _accountStateInvalid() ? 'invalid' : 'valid'};
""".replace("STATE", json.dumps(INVALID)))["result"]
    assert out == {"during": "invalid", "bookFlag": False, "after": "valid"}


# ── p3b review NITs 2/3/5 folded into B0 ──────────────────────────────────────


@requires_node
def test_self_market_unknown_session_is_its_own_neutral_pill(tmp_path):
    res = _run(tmp_path, _fn("_mktLabel") + r"""
__result = {none: _mktLabel(null), empty: _mktLabel({}), odd: _mktLabel({session: 'mystery'}),
            closed: _mktLabel({session: 'closed'}), pre: _mktLabel({session: 'pre'}),
            open: _mktLabel({session: 'open'})};
""")["result"]
    unknown = {"cls": "unknown", "txt": "Market status unavailable"}
    assert res["none"] == unknown and res["empty"] == unknown and res["odd"] == unknown
    assert res["closed"]["cls"] == "closed" and res["closed"]["txt"].startswith("Closed")
    assert res["pre"]["cls"] == "closed" and res["open"] == {"cls": "open", "txt": "Market open"}
    assert '<span class="mm-sd-mkt unknown" id="sd-mkt">' in HTML
    assert re.search(r"\.mm-sd-mkt\.unknown \{[^}]*border: 1px dashed", HTML)


def test_self_ticket_is_inert_until_book_ok_and_status_is_announced():
    est = HTML[HTML.index("window.selfUpdateEst = function() {"):]
    est = est[:est.index("\nwindow.")]
    assert "_selfBookState(_self, _selfSettled) !== 'ok'" in est
    assert "=== 'unavailable'" not in est
    assert 'id="sd-nav-status" aria-live="polite"' in HTML
