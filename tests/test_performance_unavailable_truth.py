"""PR #737 residual: distinguish unavailable evidence from a valid empty chart.

The accepted backend contract is retained and covered by test_performance_availability
and the existing PBR T12 route controls. Its old error flag is not reintroduced here.
Reuse the shipped-source PBR renderer harness; no new DOM or backend substitutes.
"""
from __future__ import annotations

import json
from pathlib import Path
import runpy

import pytest

_PBR = runpy.run_path(str(Path(__file__).with_name("test_pbr_b0_truth_rows.py")))
_run = _PBR["_run"]
requires_node = _PBR["requires_node"]

WORDS = [
    ("en", "Unavailable", "No recorded performance observations available"),
    ("zh", "不可用", "暂无可用的业绩记录"),
]


@requires_node
@pytest.mark.parametrize("lang,word,empty", WORDS)
def test_unavailable_empty_chart_names_failure(tmp_path, lang, word, empty):
    payload = {"series": [], "availability": {"status": "unavailable", "history_status": "unavailable"}}
    dom = _run(tmp_path, "_perf = " + json.dumps(payload) +
               "; renderPerformance(); renderEquityCurve();", lang)["dom"]
    chart = dom["ec-wrap"]["html"]
    assert '<span class="mm-unavail">' + word + "</span>" in chart
    assert empty not in chart
    assert "<svg" not in chart and "<path" not in chart
    assert all(value not in chart for value in ("$0", "0.00%", "NaN", "undefined"))
    assert dom["ec-range-label"]["text"] == ""
    assert dom["ec-leg-bench-line"]["display"] == "none"


@requires_node
@pytest.mark.parametrize("lang,word,empty", WORDS)
@pytest.mark.parametrize("status", [None, "available", "provisional"])
def test_successfully_empty_history_stays_empty(tmp_path, lang, word, empty, status):
    payload = {"series": []}
    if status is not None:
        payload["availability"] = {"status": status}
    dom = _run(tmp_path, "_perf = " + json.dumps(payload) +
               "; renderEquityCurve();", lang)["dom"]
    chart = dom["ec-wrap"]["html"]
    assert empty in chart
    assert '<span class="mm-unavail">' not in chart
    assert "<svg" not in chart
    assert dom["ec-range-label"]["text"] == ""


@requires_node
@pytest.mark.parametrize("lang,word,empty", WORDS)
def test_switch_to_unavailable_replaces_chart_cash_and_range(tmp_path, lang, word, empty):
    scenario = _PBR["_curve_scenario"](0, spy=True) + r"""
_perf.cash = 25000;
renderPerformance();
var before = {chart: __els['ec-wrap'].innerHTML,
              cash: __els['perf-cash-lbl'].textContent,
              range: __els['ec-range-label'].textContent};
_perf = {series: [], cash: null,
         availability: {status: 'unavailable', history_status: 'unavailable'}};
renderPerformance(); renderEquityCurve();
__result = before;
"""
    result = _run(tmp_path, scenario, lang)
    assert "<svg" in result["result"]["chart"]
    assert "25,000" in result["result"]["cash"]
    assert result["result"]["range"]
    dom = result["dom"]
    assert '<span class="mm-unavail">' + word + "</span>" in dom["ec-wrap"]["html"]
    assert "<svg" not in dom["ec-wrap"]["html"] and empty not in dom["ec-wrap"]["html"]
    assert dom["ec-range-label"]["text"] == ""
    assert word in dom["perf-cash-lbl"]["text"]
    assert "25,000" not in dom["perf-cash-lbl"]["text"]
    assert dom["ec-leg-bench-line"]["display"] == "none"


@requires_node
def test_same_unavailable_payload_uses_current_language(tmp_path):
    result = _run(tmp_path, r"""
_perf = {series: [], availability: {status: 'unavailable'}};
renderEquityCurve();
var english = __els['ec-wrap'].innerHTML;
__lang = 'zh';
renderEquityCurve();
__result = english;
""")
    assert ">Unavailable<" in result["result"]
    assert ">不可用<" in result["dom"]["ec-wrap"]["html"]
    assert ">Unavailable<" not in result["dom"]["ec-wrap"]["html"]


@requires_node
@pytest.mark.parametrize("lang,word,ref", [
    ("en", "Book unavailable — state invalid", "Quarantine ref "),
    ("zh", "账本不可用 — 状态无效", "隔离编号 "),
])
def test_invalid_account_keeps_priority_over_empty_unavailable(tmp_path, lang, word, ref):
    payload = {"series": [], "availability": {"status": "unavailable"},
               "account_state": _PBR["INVALID"]}
    dom = _run(tmp_path, "_perf = " + json.dumps(payload) +
               "; renderEquityCurve();", lang)["dom"]
    chart = dom["ec-wrap"]["html"]
    assert word in chart and ref + _PBR["SHA16"] in chart
    assert dom["ec-legend"]["display"] == "none"
    assert "<svg" not in chart
    assert "No recorded performance observations available" not in chart
    assert "暂无可用的业绩记录" not in chart
