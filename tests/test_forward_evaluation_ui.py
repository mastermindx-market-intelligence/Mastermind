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
    assert "independent return samples or investment skill" in html
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
    assert html.count(">Unverified</div>") == 2


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
@pytest.mark.parametrize("schema_version", [1, 2])
def test_request_binding_rejects_old_responses_and_current_failures(last_response, schema_version):
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
""".replace("CN", json.dumps(calendar_payload("china") if schema_version == 2
                                 else payload("china", count=7))).replace(
        "US", json.dumps(calendar_payload() if schema_version == 2 else payload())).replace(
        "LAST_OK", json.dumps(last_response == "wrong_book"))
    result = node(code)
    assert result["accepted"] == result["afterOld"]
    assert result["accepted"][0] == "china"
    expected_count = 3 if schema_version == 2 else 7
    assert f">{expected_count}</div>" in result["accepted"][1]
    assert ">49</div>" not in result["accepted"][1]
    assert result["unavailable"]["value"] is None
    assert result["unavailable"]["pending"] is False
    assert f">{expected_count}</div>" not in result["unavailable"]["html"]
    assert "Unavailable" in result["unavailable"]["html"]
    assert len(result["calls"]) == 3
    assert all(options == {"cache": "no-store"} for _, options in result["calls"])


def calendar_payload(book="autonomous", partial=False):
    """Synthetic wire records; full browser proof uses the real composed API."""
    from copy import deepcopy

    dates, closed, venue = {
        "autonomous": (["2026-09-04", "2026-09-07", "2026-09-08"], "2026-09-07", "US"),
        "china": (["2026-09-24", "2026-09-25", "2026-09-28"], "2026-09-25", "CN"),
        "hk": (["2026-09-30", "2026-10-01", "2026-10-02"], "2026-10-01", "HK"),
    }[book]
    status = "partial" if partial else "available"
    data = payload(book, count=3, source_status=status)
    begin, end = dates[0], dates[-1]
    data["evaluation_start"], data["latest_asof"] = begin, end
    snapshot = data["snapshot"]
    snapshot["asof"] = end
    snapshot["cohort"] = {"evaluation_start": begin, "deployment_sha": "a" * 40}
    basis = {
        "schema": "mastermind.portfolio_forward_evaluation.nav_date_basis.v1",
        "book": book, "evaluation_start": begin, "asof": end,
        "deployment_sha": "a" * 40, "status": status, "selected_row_count": 3,
        "date_labels": dates, "fingerprint": "b" * 64,
    }
    snapshot["nav_date_basis"] = deepcopy(basis)
    scheduled = [day for day in dates if day != closed]
    calendar = {
        "schema": "mastermind.cash_session_date_evidence.v1",
        "calendar_owner": "portfolio.market_calendar" if venue == "US"
                          else "portfolio.china_calendar",
        "venue": venue, "start": begin, "end": end,
        "coverage_start": "2026-01-01", "coverage_end": "2026-12-31",
        "source_checked_on": "2026-10-18", "scope": "published_static_cash_session_dates",
        "exceptional_closures": "listed_only",
        "rule_version": "monday_friday_excluding_listed_closures.v1",
        "status": "available", "missing_reason": None, "price_or_cutoff_qualified": False,
        "scheduled_dates": scheduled,
    }
    q = data["observation_qualification"]
    q.update({
        "schema": "mastermind.portfolio_forward_evaluation.observation_qualification.v2",
        "source_scope": "stored_snapshot_and_current_calendar_evidence",
        "date_basis": deepcopy(basis), "calendar_session_count": 2,
        "calendar_status": status,
        "calendar_missing_reason": "partial_nav_date_basis" if partial else None,
        "calendar_count_unit": "selected_nav_dates_on_scheduled_cash_sessions",
        "calendar_basis": {
            "schema": "mastermind.portfolio_forward_evaluation.calendar_basis.v1",
            "interpretation": "current_published_calendar_on_saved_nav_dates",
            "book": book, "nav_date_basis_fingerprint": basis["fingerprint"],
            "nav_date_basis_status": status, "calendar_content_fingerprint": "c" * 64,
            "fingerprint": "d" * 64, "calendar_evidence": calendar,
            "selected_session_dates": list(scheduled), "non_session_mark_dates": [closed],
            "scheduled_dates_without_forward_mark": [], "scheduled_session_count": 2,
        },
    })
    return data


def calendar_fact(html, label):
    needle = '<div class="mm-eval-label">' + label + '</div><div class="mm-eval-value">'
    assert needle in html
    return html.split(needle, 1)[1].split("</div>", 1)[0]


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_calendar_projection_displays_matched_dates_without_price_or_skill_claim(book):
    data = calendar_payload(book)
    before = json.dumps(data, sort_keys=True)
    html = render(data, book=book)
    assert calendar_fact(html, "Recorded NAV dates") == "3"
    assert calendar_fact(html, "Dates matching exchange schedule") == "2"
    assert calendar_fact(html, "Price-checked sessions") == "Unverified"
    assert "Prices unverified" in html
    assert "recorded NAV date falls outside" in html
    assert "Inspect evidence record" in html
    assert json.dumps(data, sort_keys=True) == before


def test_calendar_projection_chinese_copy_separates_schedule_and_price_checks():
    html = render(calendar_payload("hk"), book="hk", zh=True)
    assert calendar_fact(html, "已记录净值日期") == "3"
    assert calendar_fact(html, "符合交易日历的记录日期") == "2"
    assert calendar_fact(html, "价格已验证交易日") == "未验证"
    assert "查看完整证据记录" in html


@pytest.mark.parametrize("reason,expected", [
    ("saved_nav_date_basis_unavailable", "exact NAV-date basis is unavailable"),
    ("outside_published_calendar_coverage", "outside published calendar coverage"),
    ("calendar_evidence_contract_unavailable", "Calendar evidence is unavailable"),
])
def test_calendar_projection_unavailable_does_not_erase_saved_count(reason, expected):
    data = calendar_payload()
    q = data["observation_qualification"]
    q.update({"calendar_basis": None, "calendar_session_count": None,
              "calendar_status": "unavailable", "calendar_missing_reason": reason})
    if reason == "saved_nav_date_basis_unavailable":
        q["date_basis"] = {"status": "unavailable"}
    html = render(data)
    assert calendar_fact(html, "Recorded NAV dates") == "3"
    assert calendar_fact(html, "Dates matching exchange schedule") == "Unverified"
    assert expected in html


@pytest.mark.parametrize("holiday_only", [False, True])
def test_calendar_projection_true_zero_is_preserved(holiday_only):
    data = calendar_payload()
    q = data["observation_qualification"]
    projection = q["calendar_basis"]
    dates = list(projection["non_session_mark_dates"]) if holiday_only else []
    data["snapshot"]["metrics"]["marked_session_count"]["value"] = len(dates)
    q["reported_mark_count"], q["calendar_session_count"] = len(dates), 0
    for basis in (q["date_basis"], data["snapshot"]["nav_date_basis"]):
        basis["date_labels"], basis["selected_row_count"] = list(dates), len(dates)
    projection["selected_session_dates"] = []
    projection["non_session_mark_dates"] = list(dates)
    projection["scheduled_dates_without_forward_mark"] = list(
        projection["calendar_evidence"]["scheduled_dates"])
    html = render(data)
    assert calendar_fact(html, "Recorded NAV dates") == str(len(dates))
    assert calendar_fact(html, "Dates matching exchange schedule") == "0"
    assert "Scheduled dates without a selected forward mark" in html
    if not holiday_only:
        assert "No selected forward NAV dates were recorded" in html
        assert "All recorded dates match" not in html


def test_calendar_projection_partial_and_stale_evidence_remain_visible():
    data = calendar_payload("china", partial=True)
    data["status"] = "stale_after_error"
    html = render(data, book="china")
    assert calendar_fact(html, "Dates matching exchange schedule") == "2"
    assert "Partial record" in html and "recorded source is partial" in html
    assert "Latest evaluation failed. Showing the saved record" in html
    assert "2026-09-28" in html and "mm-eval-failed" in html


@pytest.mark.parametrize("path,value", [
    (("calendar_basis", "book"), "hk"),
    (("calendar_basis", "calendar_evidence", "venue"), "HK"),
    (("calendar_basis", "nav_date_basis_fingerprint"), "e" * 64),
    (("date_basis", "asof"), "2026-09-09"),
    (("calendar_session_count",), True),
    (("calendar_session_count",), "2"),
    (("calendar_session_count",), -1),
    (("calendar_basis", "selected_session_dates"), ["2026-09-04"]),
    (("calendar_basis", "calendar_evidence", "scheduled_dates"), ["2026-09-04"]),
    (("calendar_basis", "scheduled_dates_without_forward_mark"), ["2026-09-04"]),
    (("calendar_status",), "partial"),
    (("calendar_basis", "calendar_evidence", "price_or_cutoff_qualified"), True),
    (("calendar_basis", "calendar_content_fingerprint"), "fake"),
    (("calendar_basis", "calendar_evidence", "scheduled_dates"), ["2026-09-04"] * 4097),
])
def test_calendar_projection_malformed_calendar_keeps_independent_saved_count(path, value):
    data = calendar_payload()
    target = data["observation_qualification"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    html = render(data)
    assert calendar_fact(html, "Recorded NAV dates") == "3"
    assert calendar_fact(html, "Dates matching exchange schedule") == "Unverified"


def test_calendar_projection_missing_cohort_start_cannot_certify_zero():
    data = calendar_payload()
    q = data["observation_qualification"]
    projection = q["calendar_basis"]
    data["evaluation_start"] = data["snapshot"]["cohort"]["evaluation_start"] = None
    data["snapshot"]["metrics"]["marked_session_count"]["value"] = 0
    q["reported_mark_count"] = q["calendar_session_count"] = 0
    for basis in (q["date_basis"], data["snapshot"]["nav_date_basis"]):
        basis.update({"evaluation_start": None, "date_labels": [], "selected_row_count": 0})
    projection["calendar_evidence"].update({"start": None, "scheduled_dates": []})
    projection.update({"selected_session_dates": [], "non_session_mark_dates": [],
                       "scheduled_dates_without_forward_mark": [], "scheduled_session_count": 0})
    assert calendar_fact(render(data), "Dates matching exchange schedule") == "Unverified"
