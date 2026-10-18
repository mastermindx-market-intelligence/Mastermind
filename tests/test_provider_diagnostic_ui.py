"""SDK diagnostic rendering through the existing complete dashboard function."""
from __future__ import annotations
import copy
import json
from pathlib import Path

import pytest

from test_decision_availability_ui import node, payload

FIXTURE = json.loads((Path(__file__).parent / "fixtures/bot_provider_diagnostics/recorded_sdk_v1.json").read_text())
RUN_ID = FIXTURE["run_id"]


def diagnostic(book="autonomous"):
    return {
        "schema": "mastermind.bot.provider_diagnostic_inspection.v1",
        "portfolio_id": book, "run_id": RUN_ID, "role": "deep",
        "status": "partial", "reason": "recorded_sdk_observations",
        "run_binding": "matched_recorded_run_id", "provider_start": "not_proven",
        "effect_reconciliation": "not_performed", "attempt_coverage": "partial",
        "source": {"status": "available", "sha256": "a" * 64},
        "unattributed_capture_events": 0, "candidate_omissions": 0,
        "candidates_observed": 1, "issues": ["candidate_observations_partial"],
        "candidates": [{
            "identity": {"run_id": RUN_ID, "book": book, "role": "deep", "candidate_ordinal": 0},
            "recorded_at": "2026-10-15T20:00:02+00:00",
            "capture_status": "available", "status": "partial",
            "observation": {"sdk_messages_observed": 1, "terminal_messages_observed": 1,
                "tool_use_blocks_observed": 0, "tool_result_blocks_observed": 0,
                "contradictory_terminals_observed": 1, "query_entered_observed": True},
            "terminals": {"count": 1, "omitted_middle_count": 0,
                "first": {"is_error": True, "subtype": "success", "reported_contradiction": True,
                          "api_error_status": 503},
                "last": {"is_error": True, "subtype": "success", "reported_contradiction": True,
                         "api_error_status": 503}},
            "exception": {"observed": True, "class": "ResultError",
                "fields": {"is_error": True, "subtype": "success", "reported_contradiction": True,
                           "api_error_status": 503}},
            "exit": {"end_state": "raised", "exit_code": 1},
            "completeness": "partial_abnormal_end_state",
            "versions_declared_only": {"sdk": "0.2.168", "bundled_cli": "2.1.0"},
        }],
    }


def data(book="autonomous", kind="failed"):
    result = payload(book, kind=kind)
    result["latest_attempt"]["run_id"] = RUN_ID
    result["provider_diagnostic_inspection"] = diagnostic(book)
    return result


def render(value, book="autonomous", zh=False):
    return node("console.log(JSON.stringify(_decisionAvailabilityHtml(" +
                json.dumps(value) + "," + json.dumps(book) + "," + json.dumps(zh) + ")));" )


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_new_sdk_panel_shows_bound_contradiction_without_changing_decision_cards(book):
    html = render(data(book), book)
    assert "SDK observations for the recorded attempt" in html
    assert "Contradictory success/error flags" in html
    assert "SDK raised an exception" in html
    assert "ResultError" in html and "0.2.168" in html
    assert "2026-10-15 20:00:02 UTC" in html
    assert "37 hours" in html
    assert "Latest recorded decision attempt failed" in html
    assert html.count('class="mm-da-card"') == 4
    assert html.count('data-sdk-candidate="0"') == 1
    assert "Observed message and tool counts do not prove accepted trades or absence of effects" in html
    assert html.index('data-provider-diagnostics="true"') < html.index("Attempt history is partial")


def test_new_chinese_panel_keeps_accepted_target_separate():
    html = render(data("china", "accepted_with_error"), "china", True)
    assert "本次记录尝试的 SDK 观察" in html
    assert "成功与错误标记相互矛盾" in html
    assert "此错误不会抹去已接受目标" in html
    assert "SDK 抛出异常" in html
    assert "37 小时" in html
    assert "8123" not in html  # Existing locale currency uses a thousands separator.
    assert "8,123.45" in html


@pytest.mark.parametrize("field,value", [("run_id", "other-run"), ("portfolio_id", "hk"),
                                        ("schema", "unknown"), ("provider_start", "proven")])
def test_wrong_top_binding_cannot_render_candidate(field, value):
    sample = data()
    sample["provider_diagnostic_inspection"][field] = value
    html = render(sample)
    assert "Diagnostic evidence unavailable" in html
    assert 'data-sdk-candidate=' not in html
    assert "ResultError" not in html


@pytest.mark.parametrize("field,value", [("run_id", "other-run"), ("book", "hk"), ("role", "analyst"),
                                        ("candidate_ordinal", True), ("candidate_ordinal", -1)])
def test_wrong_candidate_binding_is_withheld(field, value):
    sample = data()
    sample["provider_diagnostic_inspection"]["candidates"][0]["identity"][field] = value
    html = render(sample)
    assert 'data-sdk-candidate=' not in html
    assert "ResultError" not in html
    assert "Diagnostic evidence unavailable" in html


@pytest.mark.parametrize("stamp", ["2099-01-01T00:00:00+00:00", "bad", "2026-10-15T20:00:02"])
def test_candidate_time_cannot_be_future_or_unzoned(stamp):
    sample = data()
    sample["provider_diagnostic_inspection"]["candidates"][0]["recorded_at"] = stamp
    html = render(sample)
    assert 'data-sdk-candidate=' not in html


def test_unattributed_and_missing_capture_do_not_claim_zero_invocations():
    sample = data()
    p = sample["provider_diagnostic_inspection"]
    p.update(status="unavailable", reason="no_attributable_sdk_observation",
             candidates=[], candidates_observed=0, unattributed_capture_events=1)
    html = render(sample)
    assert "Capture failures without candidate attribution: 1" in html
    assert "no candidate is inferred" in html
    assert 'data-sdk-candidate=' not in html
    assert "No provider calls" not in html


def test_duplicate_candidate_records_are_withheld():
    sample = data()
    p = sample["provider_diagnostic_inspection"]
    p["candidates"].append(copy.deepcopy(p["candidates"][0]))
    html = render(sample)
    assert 'data-sdk-candidate=' not in html
    assert "Diagnostic evidence unavailable" in html


def test_free_form_and_unsupported_labels_are_not_rendered_or_executed():
    sample = data()
    p = sample["provider_diagnostic_inspection"]
    p["raw_error"] = '<img src=x onerror="CANARY_PRIVATE()">'
    c = p["candidates"][0]
    c["exception"]["class"] = "CANARY_PRIVATE_CLASS"
    c["terminals"]["first"]["subtype"] = "CANARY_PRIVATE_SUBTYPE"
    c["versions_declared_only"]["sdk"] = "CANARY_PRIVATE_VERSION"
    c["exception"]["fields"]["retained_failure_text"] = "CANARY_PRIVATE_RESULT"
    html = render(sample)
    assert "CANARY_PRIVATE" not in html
    assert "<img" not in html


def test_unknown_counts_are_unavailable_and_real_zero_remains_zero():
    sample = data()
    c = sample["provider_diagnostic_inspection"]["candidates"][0]
    c["observation"]["tool_use_blocks_observed"] = None
    c["observation"]["tool_result_blocks_observed"] = 0
    html = render(sample)
    assert "Tool-use blocks: <strong>—</strong>" in html
    assert "Tool-result blocks: <strong>0</strong>" in html
    assert "No effects" not in html


def test_provisional_binding_cannot_show_previous_candidate():
    sample = data()
    sample["provider_diagnostic_inspection"].update(
        status="provisional", reason="decision_source_changed_during_read")
    html = render(sample)
    assert "Diagnostic binding changed during the read" in html
    assert 'data-sdk-candidate=' not in html


def test_legacy_absent_diagnostic_remains_unavailable_with_original_memo():
    sample = payload()
    html = render(sample)
    assert "SDK observations for the recorded attempt" in html
    assert "Diagnostic evidence unavailable" in html
    assert "2026-10-09 20:00:00 UTC" in html
