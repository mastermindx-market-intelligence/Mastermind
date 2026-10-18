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
function renderForwardEvaluation(){}
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


def receipt_payload(book="autonomous"):
    ticker = {"autonomous": "AAPL", "china": "600519.SS", "hk": "0700.HK"}[book]
    currency = {"autonomous": "USD", "china": "CNY", "hk": "HKD"}[book]
    data = payload(book, execution="receipt_identity_verified")
    decision_id = "decision.v1." + "a" * 24
    data["last_valid_decision"]["decision_id"] = decision_id
    data["accepted_target"]["settlement_transaction_id"] = "b" * 64
    source = {
        "schema": "mastermind.yahoo_daily_bar_evidence.v1", "ticker": ticker,
        "field": "Close", "price_local": 100.0, "status": "partial",
        "reason": "expired_generation_refresh_failed",
        "source_bar_label": "2026-08-12", "source_bar_label_kind": "daily_bar_label",
        "fetch_started_at": "2026-08-13T08:29:00+00:00",
        "download_returned_at": "2026-08-13T08:30:00+00:00",
        "fetch_age_seconds": 4000, "within_cache_ttl": False,
        "market_observed_at": None, "execution_qualification": "not_checked",
    }

    def converted(price, output_currency, input_price, input_currency, upstream, stage):
        return {
            "schema": "mastermind.price_read.v1", "ticker": ticker, "stage": stage,
            "source": "last_price", "price": price, "currency": output_currency,
            "input_price": input_price, "input_currency": input_currency,
            "fx_observation": "not_required" if input_currency == output_currency else "not_captured",
            "read_status": "returned", "upstream": upstream, "upstream_status": "matched",
            "upstream_reason": None, "source_bar_label": None, "source_bar_label_kind": None,
            "source_text_sha256": None, "attempts": [{"source": "yahoo", "outcome": "returned"}],
            "market_observed_at": None, "execution_qualification": "not_checked",
        }

    usd_price = 100.0 if currency == "USD" else 14.0
    usd = converted(usd_price, "USD", 100.0, currency, source, "native_to_usd")
    observation = converted(100.0, currency, usd_price, "USD", usd, "settle_book")
    data["settlement_price_inspection"] = {
        "schema": "mastermind.bot.settlement_price_inspection.v1", "portfolio_id": book,
        "decision_id": decision_id, "status": "available", "reason": None,
        "transaction_id": "b" * 64, "receipt_sha256": "c" * 64,
        "receipt_location": "acknowledged", "receipt_linkage": "matched",
        "verification_scope": "receipt_preimage_and_decision_reference",
        "durable_ledger_status": "not_checked", "execution_qualification": "not_checked",
        "consistency": "observed_stable", "book_consistency": "observed_stable",
        "settlement_asof": "2026-08-13", "fill_count": 0, "selected_price_count": 1,
        "context_status": "available",
        "price_context": {
            "schema": "mastermind.settlement_price_evidence.v1", "currency": currency,
            "quotes": {ticker: {
                "price": 100.0, "source": "last_price", "binding_status": "matched",
                "reason": None, "observation": observation,
            }},
            "omitted_quote_count": 0, "market_observed_at": None,
            "execution_qualification": "not_checked",
        },
    }
    return data


def render_receipt(data, book=None, zh=False):
    return node("console.log(JSON.stringify(_decisionAvailabilityHtml(" + json.dumps(data) + "," +
                json.dumps(book or data["portfolio_id"]) + "," + str(zh).lower() + ")));" )


@pytest.mark.parametrize("book,price", [("autonomous", "$100.00"), ("china", "¥100.00"), ("hk", "HK$100.00")])
def test_receipt_price_path_and_source_clock_are_visible_without_execution_qualification(book, price):
    html = render_receipt(receipt_payload(book))
    assert "Receipt and price evidence" in html
    assert "Receipt matches this decision" in html
    assert "Receipt fill rows: <strong>0</strong>" in html
    assert price in html
    assert "Yahoo Close" in html
    assert "2026-08-12 (date only)" in html
    assert "2026-08-13 08:30:00 UTC" in html
    assert "Outside cache TTL at capture" in html
    assert "Execution price quality and the fill ledger have not been checked." in html
    assert "Market observation time was not captured." in html
    if book != "autonomous":
        assert "FX timing was not captured" in html
        assert "USD 14" in html
    assert html.count('class="mm-da-card"') == 4


@pytest.mark.parametrize("field,value", [
    ("portfolio_id", "china"), ("decision_id", "decision.v1." + "f" * 24),
    ("schema", "mastermind.bot.settlement_price_inspection.v9"),
    ("execution_qualification", "qualified"),
    ("durable_ledger_status", "verified"),
    ("verification_scope", "fully_verified"),
    ("transaction_id", "d" * 64),
])
def test_receipt_projection_cannot_borrow_identity_or_promote_qualification(field, value):
    data = receipt_payload()
    data["settlement_price_inspection"][field] = value
    html = render_receipt(data)
    assert "Receipt inspection unavailable" in html
    assert "Yahoo Close" not in html
    assert "$100.00" not in html
    assert "$8,123.45" in html


@pytest.mark.parametrize("status,reason,context_status,expected", [
    ("unavailable", "receipt_missing", "unavailable", "Referenced receipt is missing"),
    ("partial", "price_context_not_captured", "not_captured", "Price context was not recorded"),
    ("partial", "price_context_decoder_unavailable", "unavailable", "Price context decoder unavailable"),
    ("inconsistent", "receipt_copies_disagree", "unavailable", "Receipt copies disagree"),
    ("provisional", "active_receipt_still_present", "available", "Receipt still awaiting acknowledgement"),
    ("provisional", "book_sources_not_stable", "unavailable", "Sources changed or a paper transaction is unfinished"),
])
def test_partial_missing_and_provisional_receipts_keep_their_reason(status, reason, context_status, expected):
    data = receipt_payload()
    data["settlement_price_inspection"].update(status=status, reason=reason, context_status=context_status)
    html = render_receipt(data)
    assert expected in html
    assert "Yahoo Close" not in html
    assert "$100.00" not in html
    assert "Execution price quality and the fill ledger have not been checked." in html


def test_price_context_is_bounded_and_escaped_and_omissions_are_visible():
    import copy
    data = receipt_payload()
    capture = data["settlement_price_inspection"]["price_context"]
    quote = capture["quotes"].pop("AAPL")
    quotes = {}
    for index in range(128):
        ticker = "S%03d" % index
        current = copy.deepcopy(quote)
        observation = current["observation"]
        while observation:
            observation["ticker"] = ticker
            observation = observation.get("upstream")
        quotes[ticker] = current
    quotes["S000"]["source"] = '<img src=x onerror="CANARY()">'
    quotes["S000"]["observation"]["source"] = quotes["S000"]["source"]
    capture.update(quotes=quotes, omitted_quote_count=2)
    data["settlement_price_inspection"]["selected_price_count"] = 130
    html = render_receipt(data)
    assert "<img" not in html
    assert "&lt;img" in html
    assert "Showing 12 of 128 captured quotes" in html
    assert "2 selected prices were omitted at capture" in html
    assert "S011" in html
    assert "S012" not in html


def test_unavailable_context_does_not_hide_selected_receipt_price_or_invent_source_time():
    data = receipt_payload()
    quote = data["settlement_price_inspection"]["price_context"]["quotes"]["AAPL"]
    quote.update(binding_status="unavailable", reason="not_captured", observation=None)
    html = render_receipt(data)
    assert "$100.00" in html
    assert "Source context unavailable" in html
    assert "Yahoo Close" not in html
    assert "08:30:00" not in html


def test_source_clock_is_frozen_at_capture_and_chinese_copy_is_complete():
    data = receipt_payload("china")
    first = render_receipt(data, zh=True)
    data["observed_at"] = "2026-10-18T11:00:00+00:00"
    later = render_receipt(data, zh=True)
    for html in (first, later):
        assert "结算凭证与价格证据" in html
        assert "2026-08-13 08:30:00 UTC" in html
        assert "捕获时已超过缓存有效期" in html
        assert "尚未核验执行价格质量与成交账簿" in html
    assert "2026-10-18 11:00:00 UTC" in later  # read clock still updates independently



def test_daily_bar_label_and_naive_capture_time_do_not_acquire_an_invented_timezone():
    data = receipt_payload()
    source = data["settlement_price_inspection"]["price_context"]["quotes"]["AAPL"]["observation"]["upstream"]["upstream"]
    source["source_bar_label"] = "2026-08-12T00:00:00"
    source["download_returned_at"] = "2026-08-13T08:30:00"
    html = render_receipt(data)
    assert "2026-08-12T00:00:00 (source label)" in html
    assert "2026-08-13T08:30:00 (timezone unavailable)" in html
    assert "2026-08-12 00:00:00 UTC" not in html
    assert "2026-08-13 08:30:00 UTC" not in html



def test_expired_cache_and_missing_context_are_visible_before_detailed_quote_rows():
    data = receipt_payload()
    html = render_receipt(data)
    warning = "1 selected quote exceeded the source cache TTL at capture."
    assert warning in html
    assert html.index(warning) < html.index('<div class="mm-da-evidence-table">')
    quote = data["settlement_price_inspection"]["price_context"]["quotes"]["AAPL"]
    quote.update(binding_status="unavailable", reason="not_captured", observation=None)
    html = render_receipt(data)
    warning = "1 selected quote has no retained source context."
    assert warning in html
    assert html.index(warning) < html.index('<div class="mm-da-evidence-table">')


def open_receipt_payload():
    data = receipt_payload()
    quote = data["settlement_price_inspection"]["price_context"]["quotes"]["AAPL"]
    quote["source"] = "yahoo_open"
    selected = quote["observation"]
    selected.update(source="yahoo_open", stage="settlement_selection", attempts=[])
    reader = selected["upstream"]
    reader.update(source="yahoo_open", stage="us_open_selection",
                  attempts=[{"source": "polygon_open", "outcome": "no_positive_price"},
                            {"source": "yahoo_open", "outcome": "selected"}])
    source = reader["upstream"]
    source.update(schema="mastermind.yahoo_daily_bar_evidence.v2", field="Open",
                  cache_refresh_basis="shared_close_cache", status="available", reason=None)
    return data, source


@pytest.mark.parametrize("zh", [False, True])
def test_open_price_evidence_uses_its_own_label_and_cache_warning(zh):
    data, source = open_receipt_payload()
    source["source_bar_label"] = "2026-08-12T00:00:00"
    html = render_receipt(data, zh=zh)
    assert ("Yahoo 开盘价" if zh else "Yahoo Open") in html
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") not in html
    assert ("开盘价与收盘价的获取时间分别记录" if zh else "Open retrieval is tracked separately from Close") in html
    assert "2026-08-12T00:00:00" in html
    assert "2026-08-12 00:00:00 UTC" not in html
    assert ("捕获时已超过来源缓存有效期" if zh else "selected quote exceeded the source cache TTL at capture") in html
    assert ("尚未核验执行价格质量与成交账簿" if zh else "Execution price quality and the fill ledger have not been checked.") in html


@pytest.mark.parametrize("schema,field,basis", [
    ("mastermind.yahoo_daily_bar_evidence.v1", "Open", None),
    ("mastermind.yahoo_daily_bar_evidence.v2", "Close", "shared_close_cache"),
    ("mastermind.yahoo_daily_bar_evidence.v2", "Open", "independent_open_cache"),
    ("mastermind.yahoo_daily_bar_evidence.v3", "Open", "shared_close_cache"),
])
def test_open_context_does_not_cross_schema_or_field_boundaries(schema, field, basis):
    data, source = open_receipt_payload()
    source.update(schema=schema, field=field)
    if basis is None:
        source.pop("cache_refresh_basis", None)
    else:
        source["cache_refresh_basis"] = basis
    html = render_receipt(data)
    assert "Source context unavailable" in html
    assert "Yahoo Open" not in html
    assert "Yahoo Close" not in html
    assert "$100.00" in html
    assert "08:30:00" not in html


@pytest.mark.parametrize("state,reason", [
    ("partial", "download_return_time_unavailable"),
    ("unavailable", "cache_binding_unavailable"),
])
@pytest.mark.parametrize("zh", [False, True])
@pytest.mark.parametrize("source_field", ["Open", "Close"])
def test_source_timing_limits_are_explicit_before_price_details(state, reason, zh, source_field):
    if source_field == "Open":
        data, source = open_receipt_payload()
    else:
        data = receipt_payload()
        source = data["settlement_price_inspection"]["price_context"]["quotes"]["AAPL"]["observation"]["upstream"]["upstream"]
    source.update(status=state, reason=reason, download_returned_at=None)
    if state == "unavailable":
        source.update(source_bar_label=None, fetch_started_at=None, fetch_age_seconds=None, within_cache_ttl=None)
    html = render_receipt(data, zh=zh)
    assert "$100.00" in html
    expected = {"Open": "Yahoo 开盘价" if zh else "Yahoo Open", "Close": "Yahoo 收盘价" if zh else "Yahoo Close"}[source_field]
    assert expected in html
    warning = "个所选报价的来源时间证据不完整或不可用" if zh else "selected quote has limited source timing evidence"
    assert warning in html
    assert html.index(warning) < html.index('<div class="mm-da-evidence-table">')
    if state == "unavailable":
        assert ("来源时间不可用" if zh else "Source timing unavailable") in html
    else:
        assert ("来源时间证据不完整" if zh else "Source timing partial") in html
    assert ("记录的缺口" if zh else "recorded gap") in html
