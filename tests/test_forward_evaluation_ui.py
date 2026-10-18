"""Exercise the dashboard's real qualification renderer and request boundary."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parent.parent / "app/static/index.html").read_text()
START = HTML.index("function _isAvailabilityBook(id)")
JS = HTML[START:HTML.index("// ── AUTONOMOUS BOOK: banner", START)]
NODE = shutil.which("node")


def node(code):
    if not NODE:
        pytest.skip("Node is required for dashboard behavior checks")
    escaping = r"""function esc(value) {return String(value).replace(/[&<>"']/g, function(c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; });}
"""
    result = subprocess.run([NODE], input=escaping + JS + code, text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)


def payload(book="autonomous", count=49, source_status="available", status="available"):
    return {
        "schema": "mastermind.portfolio_forward_evaluation.status.v1",
        "book": book, "status": status, "latest_asof": "2026-10-16",
        "evaluation_start": "2026-08-11",
        "snapshot": {
            "schema": "mastermind.portfolio_forward_evaluation.v1", "book": book,
            "asof": "2026-10-16",
            "metrics": {"marked_session_count": {"value": count, "status": source_status}},
        },
        "observation_qualification": {
            "schema": "mastermind.portfolio_forward_evaluation.observation_qualification.v1",
            "source_scope": "stored_snapshot_only", "source_metric": "marked_session_count",
            "count_unit": "recorded_nav_date_labels", "reported_mark_count": count,
            "reported_mark_count_status": source_status, "eligible_for_session_gate": False,
            "calendar_status": "not_checked", "calendar_session_count": None,
            "price_status": "not_checked", "price_qualified_session_count": None,
        },
    }


def render(data, book="autonomous", zh=False, pending=False):
    return node("console.log(JSON.stringify(_forwardEvaluationHtml(" +
                json.dumps(data) + "," + json.dumps(book) + "," +
                json.dumps(zh) + "," + json.dumps(pending) + ")));")


def test_recorded_dates_never_become_a_verified_session_horizon():
    html = render(payload())
    assert ">49</div>" in html
    assert "Recorded NAV dates" in html
    assert "Recorded through 2026-10-16" in html
    assert "Not yet qualified" in html
    assert html.count(">Unverified</div>") == 2
    assert "cannot establish an investment-skill verdict" in html
    assert "49 sessions" not in html
    assert "2026-08-11" in html


def test_true_zero_is_distinct_from_an_unavailable_count():
    assert ">0</div>" in render(payload(count=0))
    missing = render(None)
    assert ">0</div>" not in missing
    assert "Unavailable" in missing
    assert "Saved cutoff unavailable" in missing


@pytest.mark.parametrize("count", [None, True, -1, "49", 7.5, 9007199254740993])
def test_malformed_or_unsafe_count_stays_unavailable(count):
    html = render(payload(count=count))
    assert 'class="mm-eval-value">—</div>' in html
    assert "Not yet qualified" not in html
    assert ">0</div>" not in html


def test_partial_and_failed_latest_run_keep_saved_record_qualifications():
    html = render(payload(source_status="partial", status="stale_after_error"))
    assert ">49</div>" in html
    assert "Latest evaluation failed" in html
    assert "Partial source" in html
    assert '<span class="mm-eval-badge">Partial record</span>' in html
    assert "Recorded through 2026-10-16" in html
    assert "session checks remain unverified" in html


def test_wrong_book_dates_old_schema_and_contradictory_projection_are_withheld():
    cases = []
    wrong = payload("china")
    cases.append(wrong)
    wrong_snapshot = payload()
    wrong_snapshot["snapshot"]["book"] = "china"
    cases.append(wrong_snapshot)
    for part, field, value in [
        ("snapshot", "asof", "2026-02-30"),
        ("snapshot", "asof", "2026-10-15"),
        ("observation_qualification", "schema", "future_or_legacy_schema"),
        ("observation_qualification", "eligible_for_session_gate", True),
        ("observation_qualification", "count_unit", "trading_sessions"),
        ("observation_qualification", "calendar_session_count", 49),
        ("observation_qualification", "reported_mark_count", 99),
    ]:
        changed = payload()
        changed[part][field] = value
        cases.append(changed)
    old_server = payload()
    del old_server["observation_qualification"]
    cases.append(old_server)
    for data in cases:
        html = render(data)
        assert ">49</div>" not in html
        assert ">99</div>" not in html
        assert "Not yet qualified" not in html
    assert "2026-10-16" not in render(wrong)


def test_pending_language_and_manual_archive_states_are_explicit():
    pending = render(payload(), pending=True)
    assert "Reading this book" in pending
    assert ">49</div>" not in pending
    chinese = render(payload("hk"), book="hk", zh=True)
    assert "评估记录" in chinese and "已记录净值日期" in chinese
    assert "尚未验证" in chinese and chinese.count(">未验证</div>") == 2
    for book in ["self_directed", "flagship", "heavyweight", "etf"]:
        assert render(payload(), book=book) == ""


def test_unknown_status_and_untrusted_text_do_not_turn_into_displayed_evidence():
    data = payload(status='<img src=x onerror="CANARY()">')
    data["snapshot"]["asof"] = '<img src=x onerror="CANARY()">'
    html = render(data)
    assert "<img" not in html and "CANARY" not in html
    assert ">49</div>" not in html


@pytest.mark.parametrize("last_response", ["failed", "wrong_book"])
def test_request_binding_rejects_old_responses_and_current_failures(last_response):
    code = r"""
var waiting={}, calls=[], paints=[], _portfolio='autonomous', _pfFetchSeq=1;
var _forwardEvaluation=null, _forwardEvaluationPending=false;
function fetch(url,options){calls.push([url,options]);return new Promise(function(resolve){
 waiting[url]=resolve;});}
function answer(book,body,ok){waiting['/api/forward-evaluation?portfolio='+book]({
 ok:ok,json:function(){return Promise.resolve(body);}});}
function _safeRender(name,fn){fn();}
var host={innerHTML:''};
function E(id){return id==='forward-evaluation'?host:null;}
var document={documentElement:{getAttribute:function(){return 'en';}}};
(async function(){
 var old=_fetchForwardEvaluation('autonomous',1);
 _portfolio='china';_pfFetchSeq=2;
 var current=_fetchForwardEvaluation('china',2);
 answer('china',CN,true);await current;
 var accepted=[_forwardEvaluation.book,host.innerHTML];
 answer('autonomous',US,true);await old;
 var afterOld=[_forwardEvaluation.book,host.innerHTML];
 _pfFetchSeq=3;
 var last=_fetchForwardEvaluation('china',3);
 answer('china',US,LAST_OK);await last;
 var unavailable={value:_forwardEvaluation,pending:_forwardEvaluationPending,html:host.innerHTML};
 await _fetchForwardEvaluation('self_directed',3);
 await _fetchForwardEvaluation('china',2);
 console.log(JSON.stringify({accepted:accepted,afterOld:afterOld,unavailable:unavailable,calls:calls}));
})().catch(function(e){console.error(e);process.exit(1);});
""".replace("CN", json.dumps(payload("china", count=7))).replace(
        "US", json.dumps(payload())).replace("LAST_OK", json.dumps(last_response == "wrong_book"))
    result = node(code)
    assert result["accepted"] == result["afterOld"]
    assert result["accepted"][0] == "china"
    assert ">7</div>" in result["accepted"][1] and ">49</div>" not in result["accepted"][1]
    assert result["unavailable"]["value"] is None
    assert result["unavailable"]["pending"] is False
    assert ">7</div>" not in result["unavailable"]["html"]
    assert "Unavailable" in result["unavailable"]["html"]
    assert len(result["calls"]) == 3
    assert all(options == {"cache": "no-store"} for _, options in result["calls"])
