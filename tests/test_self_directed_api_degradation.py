"""Secret-safe, truth-preserving degradation for Self-Directed interaction surfaces."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _body(response) -> dict:
    return json.loads(response.body)


def _secret_failure(*_args, **_kwargs):
    raise RuntimeError("secret backend detail api_key=do-not-return /Users/private/state.json")


def test_search_failure_is_unavailable_not_empty(monkeypatch) -> None:
    from app import web
    from data_layer import polygon

    monkeypatch.setattr(polygon, "search_tickers", _secret_failure)
    response = web.api_self_directed_search("AAPL")
    payload = _body(response)

    assert payload == {
        "search_status": "unavailable",
        "results": None,
        "error": "self_directed_search_unavailable",
    }
    assert "api_key" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_successful_empty_search_remains_available_empty(monkeypatch) -> None:
    from app import web
    from data_layer import polygon

    monkeypatch.setattr(polygon, "search_tickers", lambda _q: [])
    payload = _body(web.api_self_directed_search("NOPE"))
    assert payload == {"search_status": "available", "results": []}


def test_quote_failure_is_unavailable_not_no_price(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "quote_info", _secret_failure)
    response = web.api_self_directed_quote("aapl")
    payload = _body(response)

    assert payload == {
        "quote_status": "unavailable",
        "ticker": "AAPL",
        "price": None,
        "name": None,
        "market": None,
        "error": "self_directed_quote_unavailable",
    }
    assert "api_key" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_successful_quote_without_price_remains_available(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(
        self_directed,
        "quote_info",
        lambda _ticker: {"ticker": "AAPL", "price": None, "name": "Apple", "market": {"session": "closed"}},
    )
    payload = _body(web.api_self_directed_quote("AAPL"))
    assert payload["quote_status"] == "available"
    assert payload["price"] is None
    assert payload["name"] == "Apple"
    assert "error" not in payload


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        ("order", "self_directed_order_unavailable"),
        ("thesis", "self_directed_thesis_unavailable"),
        ("cancel", "self_directed_cancel_unavailable"),
    ],
)
def test_mutation_exception_codes_are_closed(monkeypatch, operation, code) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "place_order", _secret_failure)
    monkeypatch.setattr(self_directed, "set_thesis", _secret_failure)
    monkeypatch.setattr(self_directed, "cancel_order", _secret_failure)

    if operation == "order":
        response = web.api_self_directed_order(
            web._OrderReq(ticker="AAPL", side="buy", shares=1.0)
        )
    elif operation == "thesis":
        response = web.api_self_directed_thesis(
            web._ThesisReq(ticker="AAPL", note="note")
        )
    else:
        response = web.api_self_directed_cancel("order-1")

    payload = _body(response)
    assert response.status_code == 500
    assert payload == {"ok": False, "error": code}
    assert "secret backend detail" not in response.body.decode()


def test_expected_order_rejection_remains_user_visible(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(
        self_directed,
        "place_order",
        lambda *args, **kwargs: {"ok": False, "error": "insufficient cash"},
    )

    payload = _body(web.api_self_directed_order(
        web._OrderReq(ticker="AAPL", side="buy", shares=1.0)
    ))
    assert payload == {"ok": False, "error": "insufficient cash"}


def test_cancel_miss_is_explicit_not_ambiguous_false(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "cancel_order", lambda _oid: False)
    payload = _body(web.api_self_directed_cancel("already-gone"))
    assert payload == {"ok": False, "error": "self_directed_cancel_not_found"}


def test_ui_distinguishes_unavailable_no_data_and_effect_unknown() -> None:
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    search_start = html.index("window.selfSearch = function()")
    search_end = html.index("function renderSelfResults", search_start)
    search = html[search_start:search_end]
    assert "d.search_status !== 'available'" in search
    assert "Array.isArray(d.results)" in search
    assert "renderSelfResults([], 'err')" in search

    select_start = html.index("window.selectSelfTicker = function")
    select_end = html.index("function renderSelfSelected", select_start)
    select = html[select_start:select_end]
    assert "d.quote_status !== 'available'" in select
    assert "quote_status: 'unavailable'" in select

    render_start = html.index("function renderSelfSelected")
    render_end = html.index("var _selfUnit", render_start)
    render = html[render_start:render_end]
    assert "s.quote_status === 'unavailable'" in render
    assert "sd.quote_unavail" in render
    assert "sd.no_price" in render

    order_start = html.index("window.placeSelfOrder = function")
    order_end = html.index("window.saveSelfThesis", order_start)
    order = html[order_start:order_end]
    assert "if (_selfBusy || _selfOrderEffectUnknown)" in order
    assert "self_directed_order_unavailable" in order
    assert "_selfOrderEffectUnknown = true" in order
    assert "sd.order_unknown" in order
    assert "!String(d.error).startsWith('self_directed_')" in order

    thesis_start = html.index("window.saveSelfThesis = function")
    thesis_end = html.index("window.cancelSelfOrder", thesis_start)
    thesis = html[thesis_start:thesis_end]
    assert "sd.thesis_failed" in thesis
    assert ".catch(function(){});" not in thesis

    cancel_start = html.index("window.cancelSelfOrder = function")
    cancel_end = html.index("// close the search dropdown", cancel_start)
    cancel = html[cancel_start:cancel_end]
    assert "if (!d || !d.ok)" in cancel
    assert "sd.cancel_failed" in cancel
    assert cancel.index("if (!d || !d.ok)") < cancel.index("return refreshSelf()")


def test_order_ticket_uses_current_quote_and_preserves_effect_certainty():
    import subprocess

    html = (Path(__file__).parents[1] / "app/static/index.html").read_text()
    def handler(name, until):
        start = html.index("window." + name + " = function")
        return html[start:html.index(until, start)]

    selection = handler("selectSelfTicker", "function renderSelfSelected")
    submit = handler("placeSelfOrder", "window.saveSelfThesis")
    script = r"""
const assert = require('node:assert/strict');
var window = globalThis;
var _selfSearchTimer = null, _selfResults = [], _selfSel = null, _selfBusy = false;
var _selfOrderEffectUnknown = false, _selfSettled = true, _selfUnit = 'shares';
var _self = {cash:5000}, inputs = {}, replies = [], orders = [], quotes = [], message = '';
function E(k) {return inputs[k] || (inputs[k] = {value:'1'});}
function renderSelfResults() {}
function renderSelfSelected() {}
function selfUpdateEst() {}
function _selfBookState(){return 'ok';}
function _selfMsg(_kind, text){message = text;}
function t(k){return k;}
function esc(x){return String(x);}
let refreshFails = false;
function refreshSelf(){return refreshFails ? Promise.reject(new Error('read failed')) : Promise.resolve();}
function fetch(url, opts){
  if (!opts) return new Promise(resolve=>quotes.push(resolve));
  orders.push(JSON.parse(opts.body).ticker);
  return Promise.resolve(replies.shift());
}
const response = (ok,body)=>({ok,json:async()=>body});
const flush = ()=>new Promise(resolve=>setImmediate(resolve));
""" + selection + submit + r"""
(async()=>{
  selectSelfTicker('AAA'); selectSelfTicker('BBB'); selectSelfTicker('AAA');
  quotes[2](response(true,{quote_status:'available',ticker:'AAA',price:10}));
  await flush();
  quotes[0](response(true,{quote_status:'available',ticker:'AAA',price:90}));
  quotes[1](response(true,{quote_status:'available',ticker:'BBB',price:80}));
  await flush();
  assert.equal(E('sd-search').value,'AAA');
  assert.equal(_selfSel.ticker,'AAA'); assert.equal(_selfSel.price,10);
  _self.cash=null;
  placeSelfOrder('buy','BBB'); placeSelfOrder('buy');
  assert.deepEqual(orders,[]);
  _self.cash=5000;
  replies.push(response(true,{ok:false,error:'insufficient cash'}));
  placeSelfOrder('buy'); await flush();
  assert.match(message,/insufficient cash/); assert.equal(_selfOrderEffectUnknown,false);
  replies.push(response(false,{ok:false,error:'self_directed_busy_retry'}));
  placeSelfOrder('buy'); await flush();
  assert.equal(message,'sd.busy_retry'); assert.equal(_selfOrderEffectUnknown,false);
  refreshFails=true;
  replies.push(response(true,{ok:true,status:'pending'}));
  placeSelfOrder('buy'); await flush();
  assert.equal(message,'sd.order_refresh_failed'); assert.equal(_selfOrderEffectUnknown,false);
  refreshFails=false;
  for(const bad of [response(false,{detail:'Bad Gateway'}),response(true,{ok:true,status:'bad'}),
                    response(true,{ok:false}),response(true,{ok:false,error:'self_directed_order_unavailable'})]){
    // Each case starts a fresh page with its own known state.
    _selfOrderEffectUnknown=false; E('sd-shares').value='1';
    replies.push(bad); const before=orders.length;
    placeSelfOrder('buy'); await flush();
    assert.equal(orders[before],'AAA'); assert.equal(_selfOrderEffectUnknown,true);
    assert.equal(message,'sd.order_unknown');
    placeSelfOrder('buy','BBB'); placeSelfOrder('buy'); await flush();
    assert.equal(orders.length,before+1);
  }
})().catch(err=>{console.error(err);process.exitCode=1;});
"""
    subprocess.run(["node", "-e", script], check=True, timeout=20)
