"""Consumed completeness fields must agree before diagnostic availability is shown."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from test_provider_diagnostic_read import RUN_ID, client_for, inspect, snapshot, write_log
from test_provider_diagnostic_ui import render

FIXTURE = json.loads((Path(__file__).parent / "fixtures/bot_provider_diagnostics/recorded_sdk_completeness_v1.json").read_text())
assert FIXTURE["run_id"] == RUN_ID


def control_rows(name="complete_one", book="autonomous"):
    result = copy.deepcopy(FIXTURE["controls"][name])
    result[1]["provider_diagnostic"]["identity"]["book"] = book
    return result


def envelope(rows):
    return rows[1]["provider_diagnostic"]


def mutate(rows, mode):
    value = envelope(rows)
    if mode == "query_not_observed":
        value["observation"]["query_entered_observed"] = False
    elif mode == "snapshots_missing":
        value["terminals"].update(first=None, last=None)
    elif mode == "impossible_omissions":
        value["terminals"]["omitted_middle_count"] = 1
    else:
        raise AssertionError(mode)


@pytest.mark.parametrize("name,expected", [
    ("complete_one", "available"), ("complete_two", "available"), ("complete_four", "available"),
    ("query_not_observed", "partial"), ("no_terminal", "partial"), ("projection_degraded", "partial"),
])
def test_actual_collector_complete_and_partial_controls_remain_inspectable(tmp_path, name, expected):
    data = control_rows(name)
    write_log(tmp_path, data)
    before = snapshot(tmp_path)
    result = inspect(tmp_path)
    assert result["status"] == expected
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["status"] == expected
    assert candidate["completeness"] == envelope(data)["qualifications"]["completeness"]
    assert candidate["terminals"]["count"] == envelope(data)["terminals"]["count"]
    assert candidate["terminals"]["omitted_middle_count"] == envelope(data)["terminals"]["omitted_middle_count"]
    assert result["attempt_coverage"] == "partial"
    assert result["provider_start"] == "not_proven"
    assert result["effect_reconciliation"] == "not_performed"
    assert "CANARY_PRIVATE" not in json.dumps(result)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("query", [False, None])
def test_claimed_completeness_requires_observed_query_entry(tmp_path, query):
    data = control_rows()
    envelope(data)["observation"]["query_entered_observed"] = query
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["status"] == "partial"
    candidate = result["candidates"][0]
    assert candidate["status"] == "partial"
    assert candidate["observation"]["query_entered_observed"] is query
    assert "contradictory_completeness_fields" in candidate["issues"]


@pytest.mark.parametrize("name,missing", [
    ("complete_one", ("first", "last")), ("complete_four", ("first",)), ("complete_four", ("last",)),
])
def test_positive_terminal_count_with_absent_snapshots_is_qualified(tmp_path, name, missing):
    data = control_rows(name)
    for key in missing:
        envelope(data)["terminals"][key] = None
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["status"] == "partial"
    candidate = result["candidates"][0]
    assert candidate["status"] == "partial"
    assert "terminal_snapshots_unavailable" in candidate["issues"]
    assert all(candidate["terminals"][key] is None for key in missing)


@pytest.mark.parametrize("name,omissions", [
    ("complete_one", 1), ("complete_four", 0), ("complete_four", 3),
])
def test_impossible_omission_count_is_withheld_and_cannot_lend_freshness(tmp_path, name, omissions):
    data = control_rows(name)
    envelope(data)["terminals"]["omitted_middle_count"] = omissions
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["candidates"] == []
    assert "diagnostic_terminal_counts_conflict" in result["issues"]
    assert result["latest_observation_at"] is None


def test_missing_omission_count_stays_unknown_and_qualifies_completeness(tmp_path):
    data = control_rows("complete_four")
    envelope(data)["terminals"].pop("omitted_middle_count")
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    candidate = result["candidates"][0]
    assert candidate["terminals"]["omitted_middle_count"] is None
    assert candidate["status"] == result["status"] == "partial"
    assert "terminal_omission_count_unavailable" in candidate["issues"]


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
@pytest.mark.parametrize("mode", ["query_not_observed", "snapshots_missing", "impossible_omissions"])
def test_actual_api_and_renderer_qualify_evidence_without_changing_decision_target_or_account(
    tmp_path, monkeypatch, book, mode,
):
    client, base, logs = client_for(tmp_path, monkeypatch, book, accepted_error=True)
    rows = control_rows(book=book)
    write_log(logs, rows)
    url = "/api/portfolio?portfolio=" + book + "&view=decision_availability"
    original_response = client.get(url)
    assert original_response.status_code == 200
    original = original_response.json()
    assert original["provider_diagnostic_inspection"]["status"] == "available"
    mutate(rows, mode)
    write_log(logs, rows)
    before = snapshot(tmp_path)
    response = client.get(url)
    assert response.status_code == 200
    changed = response.json()
    diagnostic = changed["provider_diagnostic_inspection"]
    assert diagnostic["status"] != "available"
    assert changed["latest_attempt_kind"] == "accepted_with_error"
    assert changed["accepted_target"] == original["accepted_target"]
    assert changed["account"] == original["account"]
    assert response.headers["cache-control"] == "no-store"
    assert "CANARY_PRIVATE" not in response.text
    assert snapshot(tmp_path) == before
    if book == "autonomous":
        for zh in (False, True):
            html = render(changed, book, zh)
            assert "SDK observations for the recorded attempt" in html if not zh else "本次记录尝试的 SDK 观察" in html
            if mode == "impossible_omissions":
                assert 'data-sdk-candidate=' not in html
                assert ("Diagnostic evidence unavailable" if not zh else "诊断证据不可用") in html
            else:
                assert 'data-sdk-candidate="0"' in html
                assert ("Capture is partial, interrupted, or limited; missing detail stays unavailable."
                        if not zh else "捕获不完整、已中断或受限；缺失详情保持不可用。") in html
                assert ("Limited to observed SDK messages." if not zh else "仅限已观察到的 SDK 消息。") not in html
    del original["provider_diagnostic_inspection"]
    del changed["provider_diagnostic_inspection"]
    assert changed == original
