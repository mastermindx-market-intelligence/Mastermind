"""Exercise shipped performance render functions with adverse synthetic observations."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

HTML = (Path(__file__).resolve().parent.parent / "app/static/index.html").read_text()
NODE = shutil.which("node")


def run_js(code):
    if not NODE:
        pytest.skip("Node is required")
    # renderPerformance now calls the §3 vocabulary primitives (_unavailHtml,
    # _epiBadgeHtml, _accountStateInvalid), which ship immediately after t().
    primitives = HTML[HTML.index("// PBR-B0-PRIMITIVES:BEGIN"):
                      HTML.index("// PBR-B0-PRIMITIVES:END") + len("// PBR-B0-PRIMITIVES:END")] + "\n"
    start = HTML.index("function _performanceEvidenceText")
    script = primitives + HTML[start:HTML.index("// ── EQUITY CURVE", start)] + code
    result = subprocess.run([NODE], input=script, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_performance_clears_previous_cash_when_new_response_is_unavailable():
    result = run_js("""
    var els = new Map();
    function E(id) { if(!els.has(id)) els.set(id, {textContent:'',className:'',innerHTML:''}); return els.get(id); }
    var document = {documentElement:{getAttribute:function(){return 'en';}}};
    function t(key) {return key;}
    function esc(v) {return String(v);}
    function fmtDate(v) {return v;}
    function fmtNav(v) {return v==null ? '—' : '$'+v;}
    function fmtPctSign(v) {return {text:v==null?'—':v+'%', cls:'neu'};}
    var _perf = {cash:1234,current_nav:3000,day_change_pct:10,max_drawdown_pct:0,
      day_change_window:{from:'2026-10-09',to:'2026-10-16'},
      drawdown_window:{from:'2026-10-01',to:'2026-10-16'}};
    // renderPerformance reads the page globals to decide the invalid-account cell.
    var _book = null, _liveMarks = null;
    renderPerformance();
    var first = E('perf-cash-lbl').textContent;
    var firstRange = E('perf-day-range').textContent;
    _perf = {cash:null,current_nav:null,total_return_pct:null,vs_benchmark_pct:null,
      availability:{status:'unavailable',valuation_basis:'unavailable',history_status:'missing'}};
    renderPerformance();
    console.log(JSON.stringify({first:first,cash:E('perf-cash-lbl').textContent,
      navHtml:E('perf-nav').innerHTML,note:E('perf-evidence').textContent,
      firstRange:firstRange,dayRange:E('perf-day-range').textContent,ddRange:E('perf-dd-range').textContent}));
    """)
    assert "$1234" in result["first"]
    # An absent cash is the §3 Unavailable WORD (PBR B0), not an em dash and not the
    # previous figure: the stale value must be gone and no fabricated number shown.
    assert result["cash"].endswith("state.unavailable")
    assert "$1234" not in result["cash"]
    assert "mm-unavail" in result["navHtml"]
    assert "state.unavailable" in result["navHtml"]
    assert "$" not in result["navHtml"] and "NaN" not in result["navHtml"]
    assert "unavailable" in result["note"]
    assert "zero return" in result["note"]
    assert result["firstRange"] == "2026-10-09 → 2026-10-16"
    assert "2026-" not in result["dayRange"]
    assert "2026-" not in result["ddRange"]


def test_recorded_and_provisional_labels_are_distinct_in_both_languages():
    result = run_js("""
    var records={availability:{status:'available',history_status:'available',
      valuation_basis:'last_recorded_nav',as_of:'2026-10-09'}};
    var provisional={availability:{status:'provisional',history_status:'available',
      valuation_basis:'provided_prices'}};
    console.log(JSON.stringify([_performanceEvidenceText(records,false),
      _performanceEvidenceText(records,true),_performanceEvidenceText(provisional,false),
      _performanceEvidenceText(provisional,true)]));
    """)
    assert "2026-10-09" in result[0] and "Last recorded" in result[0]
    assert "最近记录" in result[1]
    assert "Provisional" in result[2]
    assert "暂定" in result[3]


def test_chart_area_does_not_bridge_or_value_null_gap():
    result = run_js("""
    var d=_equityAreaPath([10,11,null,12,13], i=>i*10, v=>50-v, 100, 0, 4);
    var z=_equityAreaPath([1,0], i=>i*10, v=>50-v, 100, 0, 1);
    console.log(JSON.stringify({d:d,z:z}));
    """)
    assert result["d"].count(" Z") == 2
    assert "20.0" not in result["d"]
    assert "NaN" not in result["d"]
    assert "L10.0 50.0" in result["z"]  # real zero is retained


def test_initial_html_has_no_fabricated_performance_values():
    for key in ("perf-nav", "perf-ret", "perf-spy", "perf-day"):
        assert 'id="' + key + '">—</div>' in HTML
    assert "alpha vs benchmark" not in HTML


def test_critical_fetch_omits_unqualified_preview_but_preserves_qualified_zero():
    if not NODE:
        pytest.skip("Node is required")
    start = HTML.index("function _fetchPortfolioCritical")
    # Include the actual helper when composed with decision availability.
    helper_start = HTML.find("function _isAvailabilityBook(")
    helper = "" if helper_start < 0 else HTML[helper_start:HTML.index("\n}", helper_start) + 2] + "\n"
    script = helper + HTML[start:HTML.index("function _fetchPortfolioDetails", start)] + """
    var preview = {current_nav:777777,cash:777777};
    function fetch() {return Promise.resolve({ok:true,json:()=>Promise.resolve({account_preview:preview})});}
    (async function() {
      var unqualified = await _fetchPortfolioCritical('us');
      preview = {current_nav:0,cash:0,availability:{status:'provisional',valuation_basis:'cash_only'}};
      var qualified = await _fetchPortfolioCritical('china');
      console.log(JSON.stringify({unqualified:unqualified,qualified:qualified}));
    })().catch(function(error) {console.error(error);process.exitCode=1;});
    """
    result = subprocess.run([NODE], input=script, text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert "performance" not in data["unqualified"]
    assert data["qualified"]["performance"]["current_nav"] == 0
    assert data["qualified"]["performance"]["cash"] == 0
    assert data["qualified"]["performance"]["availability"]["status"] == "provisional"
