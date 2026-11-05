"""Render unchanged API responses from controlled real FX/receipt/API composition.

The two frozen responses are synthetic source-proof data, not portfolio history.
Adversarial copies below test display claims; they are not new canonical receipts.
"""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
import pytest
from test_decision_availability_ui import render_receipt

FIXTURES = Path(__file__).parent / "fixtures" / "bot_fx_receipt"

def api(book="china"):
    return json.loads((FIXTURES / (book + ".json")).read_bytes())

def reads(data):
    result = []
    for quote in data["settlement_price_inspection"]["price_context"]["quotes"].values():
        node = quote["observation"]
        while node:
            if node.get("schema") == "mastermind.price_read.v2":
                result.append(node)
            node = node.get("upstream")
    return result

def source_unavailable(node):
    f = node["fx_rate"]
    f.update(source="unavailable", symbol=None, source_path=None, source_bar_label=None,
             source_bar_label_kind="not_provided", source_text_sha256=None,
             source_text_digest_basis=None, source_read_started_at=None,
             source_read_returned_at=None, status="unavailable", reason="cache_context_unavailable")

def static(node):
    f = node["fx_rate"]
    f.update(source="static_fallback", symbol=None, source_path=None, source_bar_label=None,
             source_bar_label_kind="not_provided", source_text_sha256=None,
             source_text_digest_basis=None, source_read_started_at=None,
             source_read_returned_at=None, status="available", reason=None)

def test_frozen_api_fixture_bytes_match_recorded_composition():
    proof = json.loads((FIXTURES / "provenance.json").read_bytes())
    for book in ("china", "hk"):
        assert hashlib.sha256((FIXTURES / (book + ".json")).read_bytes()).hexdigest() == proof["responses"][book]["sha256"]
        assert proof["responses"][book]["unmodified_full_api_response"] is True

@pytest.mark.parametrize("book,symbol", [("china", "CNH=X"), ("hk", "HKD=X")])
@pytest.mark.parametrize("zh", [False, True], ids=["en", "zh"])
def test_real_api_fx_response_keeps_price_source_and_both_conversion_legs(book, symbol, zh):
    data = api(book)
    before = copy.deepcopy(data)
    html = render_receipt(data, zh=zh)
    assert data == before
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") in html
    assert symbol in html
    match = "记录的换算结果与捕获汇率相符" if zh else "Recorded conversion matches the captured rate"
    assert html.count(match) == 4  # Security and benchmark, with two actual conversion uses each.
    assert ("缓存建档日期（进程本地日期）" if zh else "Cache entry day (process-local date)") in html
    assert ("原始来源读取返回" if zh else "Original source read returned") in html
    assert ("尚未确定来源报价方向及代理汇率的适用性" if zh else
            "Source quote direction and proxy suitability have not been established") in html
    assert ("外汇市场观测时间不可用" if zh else "FX market observation time unavailable") in html
    assert ("尚未核验该汇率是否适用于执行" if zh else "FX execution suitability has not been checked") in html
    assert ("缺少留存的来源背景证据" if zh else "no retained source context") not in html

@pytest.mark.parametrize("zh", [False, True])
def test_matched_rate_does_not_promote_missing_source_metadata(zh):
    data = api()
    for node in reads(data): source_unavailable(node)
    html = render_receipt(data, zh=zh)
    assert ("记录的换算结果与捕获汇率相符" if zh else "Recorded conversion matches the captured rate") in html
    assert ("原始外汇来源元数据不可用" if zh else "Original FX source metadata unavailable") in html
    assert ("2 个所选报价的外汇证据不完整或无法显示" if zh else "2 selected quotes have limited or undisplayable FX evidence") in html
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") in html
    assert "FX verified" not in html
    assert "CNH=X" not in html

@pytest.mark.parametrize("zh", [False, True])
def test_static_fallback_stays_explicit_even_when_capture_metadata_is_available(zh):
    data = api()
    for node in reads(data): static(node)
    html = render_receipt(data, zh=zh)
    assert ("静态备用汇率" if zh else "Static fallback rate") in html
    assert ("已记录外汇来源背景" if zh else "FX source context recorded") in html
    assert "market rate verified" not in html
    assert "limited or undisplayable FX evidence" not in html
    assert "CNH=X" not in html

@pytest.mark.parametrize("gap", ["cache_day", "observation", "read_clock", "source_label", "regressed"])
@pytest.mark.parametrize("zh", [False, True])
def test_partial_fx_clocks_keep_the_specific_gap(gap, zh):
    data = api()
    reason = {
        "cache_day":"cache_day_unavailable", "observation":"observation_clock_unavailable",
        "read_clock":"source_read_clock_unavailable", "source_label":"source_label_unavailable",
        "regressed":"local_clock_regressed",
    }[gap]
    for node in reads(data):
        f = node["fx_rate"]
        f.update(status="partial", reason=reason)
        if gap == "cache_day": f["cache_population_day"] = None
        elif gap == "observation": f["cache_observed_at"] = None
        elif gap == "read_clock": f["source_read_returned_at"] = None
        elif gap == "source_label": f.update(source_bar_label=None, source_bar_label_kind="not_provided")
        else: f["source_read_started_at"] = "2026-08-13T15:00:00+00:00"
    html = render_receipt(data, zh=zh)
    assert ("外汇来源背景不完整" if zh else "FX source context incomplete") in html
    assert ("记录的换算结果与捕获汇率相符" if zh else "Recorded conversion matches the captured rate") in html
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") in html
    assert ("外汇背景证据无法显示" if zh else "FX context cannot be displayed") not in html

@pytest.mark.parametrize("field,value", [
    ("rate", True), ("rate", 8.0), ("rate", 0.0), ("rate", float("inf")),
    ("currency", "HKD"), ("symbol", "HKD=X"), ("symbol", "<img src=x onerror=CANARY()>"),
    ("schema", "mastermind.fx_rate_evidence.v9"),
    ("source_convention_qualification", "established"),
    ("market_observed_at", "2026-08-13T14:00:00+00:00"),
    ("execution_qualification", "qualified"), ("source_path", "../private"),
    ("extra", "not part of this schema"), ("source_bar_label", "x" * 10000),
    ("source_read_returned_at", "not a clock"), ("cache_population_day", "2026-02-31"),
    ("status", "partial"), ("reason", "invented_reason"),
])
def test_malformed_fx_child_cannot_make_a_match_claim_or_hide_supported_price_source(field, value):
    data = api()
    for node in reads(data): node["fx_rate"][field] = value
    html = render_receipt(data)
    assert "FX context cannot be displayed" in html
    assert "Recorded conversion matches the captured rate" not in html
    assert "Yahoo Close" in html and "¥700.00" in html
    assert "<img" not in html
    assert "no retained source context" not in html

@pytest.mark.parametrize("field,value", [
    ("fx_operation", "invented"), ("fx_operation", "multiply"),
    ("fx_binding_reason", "invalid_fx_context"), ("fx_rate", None),
    ("fx_observation", "unavailable"), ("input_price", 999.0),
])
def test_malformed_conversion_cannot_promote_the_fx_child(field, value):
    data = api()
    for node in reads(data):
        node[field] = value if field != "fx_operation" or value != "multiply" else (
            "multiply" if node["fx_operation"] == "divide" else "divide"
        )
    html = render_receipt(data)
    assert "FX context cannot be displayed" in html
    assert "Recorded conversion matches the captured rate" not in html
    assert "Yahoo Close" in html

@pytest.mark.parametrize("zh", [False, True])
def test_explicit_unbound_fx_keeps_independent_yahoo_source_context(zh):
    data = api()
    for node in reads(data):
        node.update(fx_observation="unavailable", fx_rate=None, fx_binding_reason="invalid_fx_context")
    html = render_receipt(data, zh=zh)
    assert ("外汇证据无法与本次换算对应" if zh else "FX evidence could not be matched to this conversion") in html
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") in html
    assert "no retained source context" not in html

def test_hkdusd_symbol_is_literal_and_never_inverted_by_the_renderer():
    data = api("hk")
    for node in reads(data):
        f = node["fx_rate"]
        f.update(source="forex_snapshot", symbol="HKDUSD", source_path="data/forex/latest.json",
                 source_bar_label_kind="snapshot_asof", source_text_sha256="a" * 64,
                 source_text_digest_basis="decoded_text_utf8", rate=0.128)
        node["price"] = node["input_price"] * f["rate"] if node["fx_operation"] == "multiply" else node["input_price"] / f["rate"]
    html = render_receipt(data)
    assert "HKDUSD" in html and "0.128 HKD per USD" in html
    assert "decoded source text encoded as UTF-8" in html
    assert "7.8125 HKD per USD" not in html

def test_small_positive_rate_keeps_its_value_instead_of_rounding_to_zero():
    data = api()
    for node in reads(data):
        f = node["fx_rate"]
        f["rate"] = 1e-12
        node["price"] = node["input_price"] * f["rate"] if node["fx_operation"] == "multiply" else node["input_price"] / f["rate"]
    html = render_receipt(data)
    assert "1e-12 CNY per USD" in html
    assert "as 0 CNY per USD" not in html

def test_two_fx_uses_keep_distinct_cache_observation_clocks_and_do_not_claim_ttl():
    data = api()
    for node in reads(data):
        if node["fx_operation"] == "multiply":
            node["fx_rate"]["cache_observed_at"] = "2026-08-13T15:00:00+00:00"
    html = render_receipt(data)
    assert "Cache observed at capture: 2026-08-13 15:00:00 UTC" in html
    assert "Original source read returned: 2026-08-13 14:00:00 UTC" in html
    assert "FX cache TTL" not in html
    assert "FX rate refreshed" not in html

@pytest.mark.parametrize("field,value", [
    ("receipt_location", "active"), ("status", "provisional"),
    ("book_consistency", "inconsistent"), ("execution_qualification", "qualified"),
])
def test_fx_details_cannot_override_existing_receipt_gates(field, value):
    data = api()
    data["settlement_price_inspection"][field] = value
    html = render_receipt(data)
    assert "Recorded conversion matches the captured rate" not in html
    assert "CNH=X" not in html


@pytest.mark.parametrize("zh", [False, True])
def test_submillisecond_fx_regression_preserves_the_canonical_partial_observation(zh):
    data = api()
    for node in reads(data):
        node["fx_rate"].update(
            source_read_started_at="2026-08-13T14:00:00.000002+00:00",
            source_read_returned_at="2026-08-13T14:00:00.000001+00:00",
            cache_observed_at="2026-08-13T14:00:00.000003+00:00",
            status="partial", reason="local_clock_regressed",
        )
    html = render_receipt(data, zh=zh)
    assert ("记录的本地时钟出现回退" if zh else "Recorded local clocks regressed") in html
    assert ("记录的换算结果与捕获汇率相符" if zh else "Recorded conversion matches the captured rate") in html
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") in html
    assert "14:00:00.000002 UTC" in html and "14:00:00.000001 UTC" in html
    assert ("外汇背景证据无法显示" if zh else "FX context cannot be displayed") not in html


@pytest.mark.parametrize("zh", [False, True])
def test_compact_source_date_remains_a_literal_label(zh):
    data = api()
    for node in reads(data): node["fx_rate"]["source_bar_label"] = "20260811"
    html = render_receipt(data, zh=zh)
    assert ("原始来源标签：20260811（来源标签）" if zh else
            "Original source label: 20260811 (source label)") in html
    assert ("记录的换算结果与捕获汇率相符" if zh else "Recorded conversion matches the captured rate") in html
    assert ("外汇背景证据无法显示" if zh else "FX context cannot be displayed") not in html


@pytest.mark.parametrize("zh", [False, True])
def test_fx_offset_clocks_compare_instants_and_keep_the_original_offset_text(zh):
    data = api()
    for node in reads(data):
        node["fx_rate"].update(
            source_read_started_at="2026-08-13T22:00:00.000002+08:00",
            source_read_returned_at="2026-08-13T14:00:00.000001Z",
            cache_observed_at="2026-08-13T10:00:00.000003-04:00",
            status="partial", reason="local_clock_regressed",
        )
    html = render_receipt(data, zh=zh)
    assert ("记录的本地时钟出现回退" if zh else "Recorded local clocks regressed") in html
    assert "22:00:00.000002+08:00" in html
    assert "14:00:00.000001 UTC" in html
    assert "10:00:00.000003-04:00" in html
    assert ("外汇背景证据无法显示" if zh else "FX context cannot be displayed") not in html


@pytest.mark.parametrize("zh", [False, True])
def test_submillisecond_regression_cannot_claim_available_context(zh):
    data = api()
    for node in reads(data):
        node["fx_rate"].update(
            source_read_started_at="2026-08-13T14:00:00.000002+00:00",
            source_read_returned_at="2026-08-13T14:00:00.000001+00:00",
            cache_observed_at="2026-08-13T14:00:00.000003+00:00",
            status="available", reason=None,
        )
    html = render_receipt(data, zh=zh)
    assert ("外汇背景证据无法显示" if zh else "FX context cannot be displayed") in html
    assert ("记录的换算结果与捕获汇率相符" if zh else "Recorded conversion matches the captured rate") not in html
    assert ("Yahoo 收盘价" if zh else "Yahoo Close") in html


@pytest.mark.parametrize("clock", ["2026-02-31T14:00:00+00:00", "0000-08-13T14:00:00+00:00"])
def test_invalid_capture_calendar_cannot_be_normalized_into_source_context(clock):
    data = api()
    for node in reads(data):
        node["fx_rate"]["source_read_started_at"] = clock
    html = render_receipt(data)
    assert "FX context cannot be displayed" in html
    assert "Recorded conversion matches the captured rate" not in html
    assert "Yahoo Close" in html
