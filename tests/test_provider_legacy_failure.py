"""Replay the retained October 2026 legacy authentication failure without effects."""
from __future__ import annotations

import copy
import json

import pytest

from app import decision_availability, provider_diagnostic_read, web
from portfolio import paper_account
from test_provider_diagnostic_read import (
    OBSERVED, RUN_ID, book_state, client_for, inspect, snapshot, write_log,
)
from test_provider_diagnostic_ui import render

BANNER = "Failed to authenticate. API Error: 401 OAuth access token has been revoked."
ERROR = "Exception('Claude Code returned an error result: success')"


def legacy_rows():
    # Same five-row bridge emission shape as the three retained October 20 logs.
    # The default legacy metadata intentionally has no book or candidate identity.
    return [
        {"_meta": {"run_id": RUN_ID, "kind": "research", "ts": "2026-10-15T20:00:00+00:00"}},
        {"type": "reasoning", "title": "session start", "ts": "2026-10-15T20:00:00.010+00:00",
         "detail": "CANARY_PRIVATE_PROMPT"},
        {"type": "reasoning", "title": "assistant text", "ts": "2026-10-15T20:00:01+00:00",
         "detail": BANNER},
        {"type": "reasoning", "title": "sdk error", "ts": "2026-10-15T20:00:02+00:00",
         "detail": ERROR},
        {"type": "reasoning", "title": "result", "ts": "2026-10-15T20:00:03+00:00", "detail": ""},
    ]


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_incident_is_visible_without_inventing_structured_candidate_evidence(tmp_path, book):
    write_log(tmp_path, legacy_rows())
    before = snapshot(tmp_path)
    result = inspect(tmp_path, book)
    legacy = result["legacy_failure_observation"]
    assert legacy["kind"] == "recorded_authentication_revoked"
    assert legacy["run_id"] == RUN_ID and legacy["portfolio_id"] == book
    assert legacy["book_binding"] == "selected_decision_run_reference"
    assert legacy["candidate_identity"] == "unavailable"
    assert legacy["recorded_at"] == "2026-10-15T20:00:02+00:00"
    assert legacy["banner_recorded_at"] == "2026-10-15T20:00:01+00:00"
    assert legacy["observation_age_seconds"] == 136798
    assert result["status"] == "unavailable"
    assert result["reason"] == "no_sdk_diagnostic_event"
    assert result["candidates"] == [] and result["candidates_observed"] == 0
    assert result["latest_observation_at"] is None
    assert result["observation_age_seconds"] is None
    assert result["attempt_coverage"] == "partial"
    assert result["provider_start"] == "not_proven"
    assert result["effect_reconciliation"] == "not_performed"
    assert "CANARY_PRIVATE" not in json.dumps(result)
    assert BANNER not in json.dumps(result) and ERROR not in json.dumps(result)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("mode", [
    "quoted_banner", "banner_suffix", "wrong_error", "error_object", "wrong_type",
    "wrong_title", "result_text", "extra_event", "missing_result", "out_of_order",
    "future", "unzoned", "before_seed", "wrong_book", "wrong_row_book", "wrong_row_run",
    "wrong_meta_run", "duplicate_meta", "partial_json", "structured_event",
    "session_detail_nonstring", "extra_field", "missing_detail",
])
def test_unqualified_sequences_do_not_become_authentication_observations(tmp_path, mode):
    rows = legacy_rows()
    if mode == "quoted_banner":
        rows[2]["detail"] = 'Research discusses: "' + BANNER + '"'
    elif mode == "banner_suffix":
        rows[2]["detail"] += " CANARY_PRIVATE"
    elif mode == "wrong_error":
        rows[3]["detail"] = "another error"
    elif mode == "error_object":
        rows[3]["detail"] = {"text": ERROR}
    elif mode == "wrong_type":
        rows[2]["type"] = "tool_result"
    elif mode == "wrong_title":
        rows[2]["title"] = "research quote"
    elif mode == "result_text":
        rows[4]["detail"] = "successful response"
    elif mode == "extra_event":
        rows.insert(3, {"type": "tool_call", "ts": rows[2]["ts"], "title": "call submit"})
    elif mode == "missing_result":
        rows.pop()
    elif mode == "out_of_order":
        rows[3]["ts"] = "2026-10-15T20:00:00+00:00"
    elif mode == "future":
        rows[4]["ts"] = "2099-01-01T00:00:00+00:00"
    elif mode == "unzoned":
        rows[2]["ts"] = "2026-10-15T20:00:01"
    elif mode == "before_seed":
        rows[1]["ts"] = "2026-10-14T20:00:00+00:00"
    elif mode == "wrong_book":
        rows[0]["_meta"]["book"] = "hk"
    elif mode == "wrong_row_book":
        rows[3]["portfolio_id"] = "hk"
    elif mode == "wrong_row_run":
        rows[3]["run_id"] = "other-run"
    elif mode == "wrong_meta_run":
        rows[0]["_meta"]["run_id"] = "other-run"
    elif mode == "duplicate_meta":
        rows.insert(0, copy.deepcopy(rows[0]))
    elif mode == "structured_event":
        rows.append({"type": "provider_diagnostic", "ts": rows[-1]["ts"]})
    elif mode == "session_detail_nonstring":
        rows[1]["detail"] = None
    elif mode == "extra_field":
        rows[3]["candidate_ordinal"] = 2
    elif mode == "missing_detail":
        rows[1].pop("detail")
    path = write_log(tmp_path, rows)
    if mode == "partial_json":
        path.write_bytes(path.read_bytes() + b'{"unfinished":\n')
    assert inspect(tmp_path)["legacy_failure_observation"] is None


def test_changed_run_clears_legacy_projection_and_its_clock(tmp_path, monkeypatch):
    write_log(tmp_path, legacy_rows())
    monkeypatch.setattr(provider_diagnostic_read, "_signature", lambda path: ("changed",))
    result = inspect(tmp_path)
    assert result["status"] == "provisional"
    assert result["legacy_failure_observation"] is None


@pytest.mark.parametrize("changed", ["decisions", "account"])
def test_only_changed_decision_source_invalidates_selected_legacy_run(tmp_path, changed):
    base, logs = tmp_path / "book", tmp_path / "runs"
    book_state(base, "autonomous")
    write_log(logs, legacy_rows())

    def callback(attempt):
        result = inspect(logs, attempt=attempt)
        assert result["legacy_failure_observation"] is not None
        path = base / ("decisions.jsonl" if changed == "decisions" else "account.json")
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    result = decision_availability.read_decision_availability(
        "autonomous", base_dir=base, observed_at=OBSERVED,
        verify_receipt=web._decision_execution_receipt_verified,
        validate_pending=paper_account.pending_target_contract_error,
        inspect_provider_diagnostics=callback,
    )
    diagnostic = result["provider_diagnostic_inspection"]
    assert (diagnostic["legacy_failure_observation"] is None) == (changed == "decisions")
    assert result["last_valid_decision"]["run_id"] == "synthetic-original"
    assert result["account"]["cash"] == 8123.45


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
@pytest.mark.parametrize("accepted", [False, True])
def test_real_route_and_renderer_show_failure_and_preserve_decision_authority(
    tmp_path, monkeypatch, book, accepted,
):
    client, base, logs = client_for(tmp_path, monkeypatch, book, accepted_error=accepted)
    write_log(logs, legacy_rows())
    before = snapshot(tmp_path)
    response = client.get("/api/portfolio", params={"portfolio": book, "view": "decision_availability"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["latest_attempt_kind"] == ("accepted_with_error" if accepted else "failed")
    assert data["last_valid_decision"]["run_id"] == (RUN_ID if accepted else "synthetic-original")
    assert data["accepted_target"]["target_status"] == "queued"
    assert data["account"]["cash"] == 8123.45
    assert data["provider_diagnostic_inspection"]["legacy_failure_observation"] is not None
    for zh in (False, True):
        html = render(data, book, zh)
        assert 'data-recorded-auth-failure="true"' in html
        assert ("已记录身份验证失败" if zh else "Recorded authentication failure") in html
        assert "2026-10-15 20:00:02 UTC" in html
        assert ("旧版日志中的观察记录" if zh else "legacy log observation") in html
        assert ("尝试历史仍不完整" if zh else "Attempt history remains partial") in html
        assert 'data-sdk-candidate=' not in html
        assert "CANARY_PRIVATE" not in html and ERROR not in html
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("field,value", [
    ("schema", "unknown"), ("kind", "CANARY_PRIVATE"),
    ("run_id", "other-run"), ("portfolio_id", "hk"),
    ("candidate_identity", "verified"), ("book_binding", "metadata_match"),
    ("source_kind", "provider_attestation"), ("verification_scope", "all_credentials"),
    ("recorded_at", "2099-01-01T00:00:00+00:00"),
    ("banner_recorded_at", "2099-01-01T00:00:00+00:00"),
])
def test_ui_refuses_unqualified_or_forged_legacy_projection(tmp_path, monkeypatch, field, value):
    client, base, logs = client_for(tmp_path, monkeypatch)
    write_log(logs, legacy_rows())
    data = client.get("/api/portfolio?portfolio=autonomous&view=decision_availability").json()
    data["provider_diagnostic_inspection"]["legacy_failure_observation"][field] = value
    html = render(data)
    assert 'data-recorded-auth-failure=' not in html
    assert "CANARY_PRIVATE" not in html


@pytest.mark.parametrize("field,value", [
    ("status", "provisional"), ("run_binding", "provisional"),
    ("decision_binding_consistency", "changed_during_read"), ("attempt_coverage", "complete"),
    ("provider_start", "proven"), ("effect_reconciliation", "performed"),
    ("source", {"status": "partial"}),
])
def test_ui_withholds_failure_when_outer_evidence_is_unqualified(tmp_path, monkeypatch, field, value):
    client, base, logs = client_for(tmp_path, monkeypatch)
    write_log(logs, legacy_rows())
    data = client.get("/api/portfolio?portfolio=autonomous&view=decision_availability").json()
    data["provider_diagnostic_inspection"][field] = value
    assert 'data-recorded-auth-failure=' not in render(data)


def test_refresh_ages_the_retained_observation_without_refreshing_structured_evidence(tmp_path):
    write_log(tmp_path, legacy_rows())
    original = inspect(tmp_path)
    refreshed = inspect(tmp_path, observed="2026-10-17T11:00:00+00:00")
    old = original["legacy_failure_observation"]
    new = refreshed["legacy_failure_observation"]
    assert new["recorded_at"] == old["recorded_at"]
    assert new["observation_age_seconds"] == old["observation_age_seconds"] + 3600
    assert refreshed["latest_observation_at"] is None
    assert refreshed["status"] == original["status"] == "unavailable"
