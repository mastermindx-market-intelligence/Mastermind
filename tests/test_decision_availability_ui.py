"""Behavioral checks of the shipped dashboard functions, using synthetic API responses."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parent.parent / "app/static/index.html").read_text()
NODE = shutil.which("node")


def section(start, end):
    position = HTML.index(start)
    return HTML[position:HTML.index(end, position)]


JS = section("function _isAvailabilityBook(id)", "// ── AUTONOMOUS BOOK: banner")


def node(code):
    if not NODE:
        pytest.skip("Node is required for dashboard behavior checks")
    script = r"""function esc(value) {return String(value).replace(/[&<>"']/g, function(c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; });}
""" + JS + code
    result = subprocess.run([NODE], input=script, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def payload(book="autonomous", *, kind="failed", execution="unverified"):
    return {
        "schema": "mastermind.bot.decision_availability.v1", "portfolio_id": book,
        "observed_at": "2026-10-17T10:00:00+00:00", "origin_lineage_status": "complete",
        "last_valid_decision": {"asof": "2026-10-09", "ts": "2026-10-09T20:00:00+00:00",
                                "summary": "Original memo", "submitted_holding_count": 0},
        "latest_attempt": {"asof": "2026-10-15", "ts": "2026-10-15T20:00:00+00:00",
                           "run_id": "synthetic-latest"},
        "latest_attempt_kind": kind,
        "accepted_target": {"execution_evidence": execution, "fill_count": 0,
                            "gross_exposure": 0, "pending": {"status": "none"}},
        "account": {"status": "available", "cash": 8123.45, "position_count": 0,
                    "valuation": {"status": "cash_only", "nav": 8123.45,
                                  "gross_exposure": 0, "cash_weight": 1},
                    "last_recorded_nav": {}},
        "consistency": {"status": "observed_stable"}, "sources": {}, "issues": [],
    }


@pytest.mark.parametrize("book,currency", [("autonomous", "$8,123.45"), ("china", "¥8,123.45"),
                                          ("hk", "HK$8,123.45")])
def test_regional_cards_expose_failure_origin_and_account_separately(book, currency):
    rendered = node("console.log(JSON.stringify(_decisionAvailabilityHtml(" +
                    json.dumps(payload(book)) + "," + json.dumps(book) + ",false)));")
    assert rendered.count('class="mm-da-card"') == 4
    assert "Latest recorded decision attempt failed" in rendered
    assert "2026-10-09 20:00:00 UTC" in rendered
    assert "2026-10-15 20:00:00 UTC" in rendered
    assert currency in rendered
    assert "Scheduled opportunity status is unverified" in rendered
    assert "carried unchanged" not in rendered
    assert rendered.index("Latest recorded decision attempt failed") < rendered.index('class="mm-da-grid"')


def test_wrong_book_or_failed_fetch_cannot_display_previous_book_truth():
    values = node("console.log(JSON.stringify([" +
                  "_decisionAvailabilityHtml(" + json.dumps(payload()) + ",'hk',false)," +
                  "_decisionAvailabilityHtml(null,'hk',false)]));")
    for rendered in values:
        assert "Decision status unavailable" in rendered
        assert "8,123.45" not in rendered
        assert "2026-10-09" not in rendered


@pytest.mark.parametrize("evidence,expected", [
    ("unverified", "Recorded execution · unverified"),
    ("receipt_identity_verified", "Recorded no trade · identity checked"),
])
def test_no_trade_requires_receipt_evidence(evidence, expected):
    rendered = node("console.log(JSON.stringify(_decisionAvailabilityHtml(" +
                    json.dumps(payload(execution=evidence)) + ",'autonomous',false)));")
    assert expected in rendered
    if evidence == "unverified":
        assert "Recorded no trade · identity checked" not in rendered


def test_null_money_is_not_zero_and_html_is_escaped():
    data = payload()
    data["latest_attempt"]["run_id"] = '<img src=x onerror="CANARY()">'
    data["account"]["cash"] = None
    data["account"]["valuation"] = {"status": "unavailable", "nav": None}
    rendered = node("console.log(JSON.stringify(_decisionAvailabilityHtml(" +
                    json.dumps(data) + ",'autonomous',false)));")
    assert "Valuation unavailable" in rendered
    assert "$0" not in rendered
    assert "<img" not in rendered
    assert "&lt;img" in rendered


def test_chinese_and_manual_archive_scope():
    result = node("console.log(JSON.stringify({html:_decisionAvailabilityHtml(" +
                  json.dumps(payload("china")) + ",'china',true),scope:" +
                  "['autonomous','china','hk','self_directed','flagship','heavyweight','etf'].map(_isAvailabilityBook)}));")
    assert "最近记录的决策尝试失败" in result["html"]
    assert result["scope"] == [True, True, True, False, False, False, False]


def test_live_marks_and_latest_snapshot_cannot_refresh_original_memo():
    banner = section("function renderAutoBanner()", "var _autoThesisExpanded")
    code = r"""
var meta = {}, sum = {};
function E(id) {return id === 'auto-meta' ? meta : id === 'auto-sum' ? sum : null;}
var _portfolio='autonomous', _portfolios=[], _book={summary:'Wrong refreshed memo',as_of:'2026-10-17'};
var _perf={current_nav:999999}, _decisionAvailability=DATA;
function _isBrainBook(){return true;} function _pfLabel(){return 'US Brain';}
function _pfKind(){return 'autonomous';} function fmtDateShort(x){return x;}
var document={documentElement:{getAttribute:function(){return 'en';}}};
BANNER
renderAutoBanner();
var before = [meta.innerHTML,sum.textContent];
_book={summary:'New quote payload',as_of:'2026-10-18'};_perf={current_nav:1000001};
renderAutoBanner();
console.log(JSON.stringify({before:before,after:[meta.innerHTML,sum.textContent]}));
""".replace("DATA", json.dumps(payload())).replace("BANNER", banner)
    result = node(code)
    assert result["before"] == result["after"]
    assert result["after"][1] == "Original memo"
    assert "Original decision date 2026-10-09" in result["after"][0]
    assert "2026-10-17" not in result["after"][0]


def test_actual_fetch_driver_ignores_reverse_order_responses_from_previous_book():
    critical = section("function _fetchPortfolioCritical", "function _fetchPortfolioDetails")
    driver = section("async function fetchAll(opts)", "// ── langchange")
    code = r"""
var waiting={}, paints=[], _portfolio='autonomous', _pfFetchSeq=0, _portfolioDataCache={};
var _decisionAvailability=null, window={setTimeout:setTimeout};
function fetch(url){return new Promise(function(resolve){waiting[url]=resolve;});}
function answer(url,body){if(!waiting[url])throw Error('no pending request '+url);
 waiting[url]({ok:true,json:function(){return Promise.resolve(body);}});}
function loadBarStart(){} function loadBarDone(){} function applyColl(){} function _hydrateShared(){}
function _safeRender(name,fn){fn();}
function renderDecisionAvailability(){paints.push(_decisionAvailability && _decisionAvailability.portfolio_id);}
function renderAutoBanner(){}
function _paintPortfolioSnapshot(data){paints.push(data.portfolio);return Promise.resolve();}
function _fetchPortfolioDetails(id,base){return Promise.resolve(base);}
CRITICAL
DRIVER
async function tick(){await Promise.resolve();await Promise.resolve();await Promise.resolve();
 await Promise.resolve();await Promise.resolve();await Promise.resolve();}
(async function(){
 var old=fetchAll();_portfolio='china';var current=fetchAll();
 answer('/api/portfolio?portfolio=china&view=decision_availability',CN);
 await tick();answer('/api/portfolio?portfolio=china',{portfolio_id:'china'});
 await current;
 answer('/api/portfolio?portfolio=autonomous&view=decision_availability',US);
 await tick();answer('/api/portfolio?portfolio=autonomous',{portfolio_id:'autonomous'});
 await old;
 console.log(JSON.stringify({paints:paints,current:_decisionAvailability.portfolio_id}));
})().catch(function(e){console.error(e);process.exit(1);});
""".replace("CRITICAL", critical).replace("DRIVER", driver).replace(
        "CN", json.dumps(payload("china"))).replace("US", json.dumps(payload()))
    result = node(code)
    assert result["current"] == "china"
    assert result["paints"] and set(result["paints"]) == {"china"}


def test_apply_snapshot_rejects_wrong_book_and_mismatched_availability():
    apply = section("function _applyPortfolioSnapshot", "function _paintPortfolioSnapshot")
    result = node(r"""
function _updateScopedPanelAvailability(){}
var _portfolio='china',_decisionAvailability={portfolio_id:'china'},_book=null,_trades=null,
_perf=null,_risk=null,_decisions=[],_rejected=[],_self=null,_selfHist=null;
""" + apply + r"""
_applyPortfolioSnapshot({portfolio:'autonomous',book:{summary:'WRONG'},decisionAvailability:{portfolio_id:'autonomous'}});
var first=_decisionAvailability.portfolio_id;
_applyPortfolioSnapshot({portfolio:'china',book:null,decisionAvailability:{portfolio_id:'autonomous'}});
console.log(JSON.stringify({first:first,second:_decisionAvailability,book:_book}));
""")
    assert result == {"first": "china", "second": None, "book": None}
