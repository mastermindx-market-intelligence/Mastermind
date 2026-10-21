"""Exact-run SDK display fixtures. No provider, quote, account recovery or retry."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, decision_availability, response_cache, web
from brain import runlog
from portfolio import paper_account, registry

OBSERVED = "2026-10-17T10:00:00+00:00"
FIXTURE = json.loads((Path(__file__).parent / "fixtures/bot_provider_diagnostics/recorded_sdk_v1.json").read_text())
RUN_ID = FIXTURE["run_id"]


def rows(book="autonomous", ordinal=0):
    result = copy.deepcopy(FIXTURE["rows"])
    identity = result[1]["provider_diagnostic"]["identity"]
    identity.update(book=book, candidate_ordinal=ordinal)
    return result


def write_log(base, data=None, run_id=RUN_ID):
    base.mkdir(parents=True, exist_ok=True)
    path = base / (run_id + ".jsonl")
    path.write_text("\n".join(json.dumps(row) for row in (rows() if data is None else data)) + "\n")
    return path


def inspect(base, book="autonomous", attempt=None, observed=OBSERVED):
    from app.provider_diagnostic_read import read_provider_diagnostic_evidence
    return read_provider_diagnostic_evidence(
        book, {"run_id": RUN_ID} if attempt is None else attempt,
        runs_dir=base, observed_at=observed,
    )


def snapshot(base):
    return {str(path.relative_to(base)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in base.rglob("*") if path.is_file()}


def book_state(base, book, accepted_error=False):
    base.mkdir(parents=True, exist_ok=True)
    origin = {
        "asof": "2026-10-09", "ts": "2026-10-09T20:00:00+00:00",
        "run_id": "synthetic-original", "decision_id": "decision.v1." + "a" * 24,
        "decision_effective": True, "target_status": "queued",
        "holdings": [], "effective_holdings": [],
        "submission_sha256": "b" * 64, "target_sha256": paper_account._target_sha256({}),
        "summary": "Original investment intent",
    }
    latest = {
        "asof": "2026-10-15", "ts": "2026-10-15T20:00:03+00:00",
        "run_id": RUN_ID, "decision_effective": False,
        "target_status": "rejected_no_submission", "holdings": [],
        "error": "CANARY_PRIVATE_DECISION_ERROR",
    }
    if accepted_error:
        latest.update(origin, run_id=RUN_ID, asof="2026-10-15",
                      ts="2026-10-15T20:00:03+00:00",
                      decision_id="decision.v1." + "c" * 24)
    (base / "decisions.jsonl").write_text(json.dumps(origin) + "\n" + json.dumps(latest) + "\n")
    (base / "account.json").write_text(json.dumps({"cash": 8123.45, "positions": {}}))
    return origin, latest


def client_for(tmp_path, monkeypatch, book="autonomous", accepted_error=False):
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "books")
    base = registry.data_dir(book)
    book_state(base, book, accepted_error)
    logs = tmp_path / "runs"
    write_log(logs, rows(book))
    monkeypatch.setattr(runlog, "_RUNS_DIR", logs)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(OBSERVED)
    monkeypatch.setattr(web, "datetime", Clock)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected_effect_or_replacement_read")
    for name in ("_load_account", "_load_account_file", "_fresh_account", "mark", "nav",
                 "settle_target", "rebalance", "preflight_pending_target", "quarantine_pending_target",
                 "accrue_cash_yield", "_recover_paper_transaction_unlocked"):
        monkeypatch.setattr(paper_account, name, forbidden)
    monkeypatch.setattr(runlog, "read_run", forbidden)
    monkeypatch.setattr(runlog, "list_runs", forbidden)
    monkeypatch.setattr(runlog, "start_run", forbidden)
    monkeypatch.setattr(runlog, "log_step", forbidden)
    app = FastAPI()
    app.include_router(web.router)
    response_cache.install(app)
    auth.install(app)
    response_cache.clear()
    return TestClient(app), base, logs


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_new_mounted_diagnostics_bind_latest_record_without_private_text_or_effects(tmp_path, monkeypatch, book):
    client, base, logs = client_for(tmp_path, monkeypatch, book)
    before = snapshot(tmp_path)
    for _ in range(2):
        response = client.get("/api/portfolio", params={"portfolio": book, "view": "decision_availability"})
        assert response.status_code == 200
        data = response.json()
        assert "provider_diagnostic_inspection" in data
        diagnostic = data["provider_diagnostic_inspection"]
        assert diagnostic["run_id"] == RUN_ID and diagnostic["portfolio_id"] == book
        assert diagnostic["status"] == "partial"
        candidate = diagnostic["candidates"][0]
        assert candidate["identity"] == {"run_id": RUN_ID, "book": book, "role": "deep", "candidate_ordinal": 0}
        assert candidate["terminals"]["count"] == 1
        assert candidate["terminals"]["first"]["is_error"] is True
        assert candidate["terminals"]["first"]["subtype"] == "success"
        assert candidate["terminals"]["first"]["reported_contradiction"] is True
        assert candidate["exception"]["class"] == "ResultError"
        assert candidate["exception"]["fields"]["api_error_status"] == 503
        assert candidate["observation"]["tool_use_blocks_observed"] == 0
        assert data["last_valid_decision"]["run_id"] == "synthetic-original"
        assert data["account"]["cash"] == 8123.45
        assert data["latest_attempt_kind"] == "failed"
        assert diagnostic["effect_reconciliation"] == "not_performed"
        assert diagnostic["provider_start"] == "not_proven"
        assert diagnostic["attempt_coverage"] == "partial"
        assert "CANARY_PRIVATE" not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert "x-mm-cache" not in response.headers
    assert snapshot(tmp_path) == before
    assert not response_cache._CACHE


def test_new_mounted_accepted_target_survives_later_sdk_error(tmp_path, monkeypatch):
    client, base, logs = client_for(tmp_path, monkeypatch, accepted_error=True)
    before = snapshot(tmp_path)
    data = client.get("/api/portfolio?portfolio=autonomous&view=decision_availability").json()
    assert "provider_diagnostic_inspection" in data
    assert data["latest_attempt_kind"] == "accepted_with_error"
    assert data["last_valid_decision"]["run_id"] == RUN_ID
    assert data["accepted_target"]["target_status"] == "queued"
    assert data["accepted_target"]["weights"] == {}
    assert data["provider_diagnostic_inspection"]["candidates"][0]["exit"]["end_state"] == "raised"
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("field,value", [
    ("run_id", "other-run"), ("book", "china"), ("role", "analyst"),
    ("candidate_ordinal", True), ("candidate_ordinal", -1),
])
def test_wrong_identity_is_never_attached(tmp_path, field, value):
    data = rows()
    data[1]["provider_diagnostic"]["identity"][field] = value
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["candidates"] == []
    assert "diagnostic_identity_mismatch" in result["issues"]
    assert result["latest_observation_at"] is None


@pytest.mark.parametrize("attempt", [{}, {"run_id": None}, {"run_id": "../other"}, {"run_id": ""}])
def test_missing_or_unsafe_run_identity_never_selects_latest(tmp_path, monkeypatch, attempt):
    from app import provider_diagnostic_read as reader
    monkeypatch.setattr(reader, "_read", lambda *a, **kw: pytest.fail("Unexpected source read"))
    result = inspect(tmp_path / "missing", attempt=attempt)
    assert result["status"] == "unavailable"
    assert result["candidates_observed"] is None
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("book", ["self_directed", "flagship", "heavyweight", "etf"])
def test_manual_and_archived_books_never_read_runs(tmp_path, monkeypatch, book):
    from app import provider_diagnostic_read as reader
    monkeypatch.setattr(reader, "_read", lambda *a, **kw: pytest.fail("Unexpected source read"))
    assert inspect(tmp_path / "missing", book)["status"] == "not_applicable"


@pytest.mark.parametrize("change", ["missing_meta", "wrong_meta", "duplicate_meta", "future_meta"])
def test_exact_run_metadata_is_required(tmp_path, change):
    data = rows()
    if change == "missing_meta":
        data.pop(0)
    elif change == "wrong_meta":
        data[0]["_meta"]["run_id"] = "other"
    elif change == "duplicate_meta":
        data.insert(0, copy.deepcopy(data[0]))
    else:
        data[0]["_meta"]["ts"] = "2099-01-01T00:00:00+00:00"
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["status"] == "unavailable" and result["candidates"] == []
    assert result["run_binding"] == "unavailable"


def test_malformed_tail_keeps_partial_scope_with_actual_parsed_candidate(tmp_path):
    path = write_log(tmp_path)
    path.write_bytes(path.read_bytes() + b'{"unclosed":\n')
    result = inspect(tmp_path)
    assert result["source"]["status"] == "partial"
    assert result["candidates_observed"] == 1
    assert "run_source_partial" in result["issues"]


@pytest.mark.parametrize("capture", [
    {"status": "unavailable", "reason": "collector_unavailable"},
    {"status": "unavailable", "reason": "finalization_failed"},
])
def test_unavailable_capture_has_only_run_level_attribution(tmp_path, capture):
    data = rows()
    data[1].pop("provider_diagnostic")
    data[1]["provider_diagnostic_capture"] = capture
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["run_binding"] == "matched_recorded_run_id"
    assert result["candidates"] == [] and result["candidates_observed"] == 0
    assert result["unattributed_capture_events"] == 1
    assert result["unattributed_capture_reasons"] == [capture["reason"]]
    assert result["latest_observation_at"] is None


@pytest.mark.parametrize("capture", [
    {"status": [], "reason": "observer_call_failed"},
    {"status": "unavailable", "reason": []},
    {"status": "partial", "reason": "unknown"}, {},
])
def test_malformed_capture_is_qualified_not_an_api_exception(tmp_path, capture):
    data = rows()
    data[1]["provider_diagnostic_capture"] = capture
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["candidates"] == []
    assert "capture_qualification_unavailable" in result["issues"]


def test_duplicate_candidate_identity_withholds_both_records(tmp_path):
    data = rows()
    data.append(copy.deepcopy(data[1]))
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["candidates"] == []
    assert result["duplicate_candidate_ordinals"] == [0]
    assert result["latest_observation_at"] is None


def test_unrelated_later_event_cannot_lend_freshness_to_bound_candidate(tmp_path):
    data = rows()
    wrong = copy.deepcopy(data[1])
    wrong["provider_diagnostic"]["identity"]["book"] = "hk"
    wrong["ts"] = "2026-10-17T09:59:59+00:00"
    data.append(wrong)
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["latest_observation_at"] == "2026-10-15T20:00:02+00:00"
    assert result["observation_age_seconds"] == 136798
    assert len(result["candidates"]) == 1


@pytest.mark.parametrize("field,value", [
    ("sdk_messages_observed", True), ("tool_use_blocks_observed", "0"),
    ("tool_result_blocks_observed", -1),
])
def test_malformed_counts_stay_null(tmp_path, field, value):
    data = rows()
    data[1]["provider_diagnostic"]["observation"][field] = value
    write_log(tmp_path, data)
    candidate = inspect(tmp_path)["candidates"][0]
    assert candidate["observation"][field] is None
    assert candidate["status"] == "partial"
    assert "malformed_numeric_field" in candidate["issues"]


@pytest.mark.parametrize("change", ["terminal_count", "overclaim_effect", "single_terminal"])
def test_conflicting_diagnostic_fields_are_withheld(tmp_path, change):
    data = rows()
    envelope = data[1]["provider_diagnostic"]
    if change == "terminal_count":
        envelope["terminals"]["count"] = 0
    elif change == "overclaim_effect":
        envelope["qualifications"]["effect_reconciliation"] = "performed"
    else:
        envelope["terminals"]["last"]["is_error"] = False
    write_log(tmp_path, data)
    assert inspect(tmp_path)["candidates"] == []


def test_unknown_labels_and_all_free_form_details_are_omitted(tmp_path):
    data = rows()
    envelope = data[1]["provider_diagnostic"]
    for key in ("first", "last"):
        envelope["terminals"][key]["subtype"] = "CANARY_PRIVATE_SUBTYPE"
        envelope["terminals"][key]["terminal_reason"] = "CANARY_PRIVATE_REASON"
    envelope["exit"]["exception_class"] = "CANARY_PRIVATE_CLASS"
    envelope["dependencies"]["sdk_package_version"]["declared_value"] = "CANARY_PRIVATE_VERSION"
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert "CANARY_PRIVATE" not in json.dumps(result)
    assert result["candidates"][0]["terminals"]["first"]["subtype"] is None


def test_source_change_during_projection_withholds_stale_candidates(tmp_path, monkeypatch):
    from app import provider_diagnostic_read as reader
    path = write_log(tmp_path)
    original = reader._project
    def changing(*args, **kwargs):
        result = original(*args, **kwargs)
        path.write_bytes(path.read_bytes() + b'{"changed": true}\n')
        return result
    monkeypatch.setattr(reader, "_project", changing)
    result = inspect(tmp_path)
    assert result["status"] == "provisional"
    assert result["reason"] == "run_source_changed_during_read"
    assert result["candidates"] == [] and result["candidates_observed"] is None


def test_symlink_run_is_withheld_without_reading_target(tmp_path, monkeypatch):
    from app import provider_diagnostic_read as reader
    target = tmp_path / "unrelated"
    target.write_text("private")
    (tmp_path / (RUN_ID + ".jsonl")).symlink_to(target)
    monkeypatch.setattr(reader, "_read", lambda *a, **kw: pytest.fail("Unexpected target read"))
    assert inspect(tmp_path)["reason"] == "run_source_symlink"


def test_candidate_limit_and_gaps_are_explicit_without_summing_effects(tmp_path):
    data = rows()
    template = data.pop()
    for ordinal in range(18):
        item = copy.deepcopy(template)
        item["provider_diagnostic"]["identity"]["candidate_ordinal"] = ordinal + 1
        data.append(item)
    write_log(tmp_path, data)
    result = inspect(tmp_path)
    assert result["candidates_observed"] == 18
    assert len(result["candidates"]) == 16
    assert result["candidate_omissions"] == 2
    assert "candidate_ordinal_gap" in result["issues"]
    assert "candidate_display_limit" in result["issues"]
    assert "total_tools" not in result and result["effect_reconciliation"] == "not_performed"

@pytest.mark.parametrize("failure", ["raises", "wrong_run", "wrong_book", "wrong_schema", "overclaimed_effect"])
def test_inspector_failure_cannot_change_existing_decision_account_or_target(tmp_path, failure):
    base = tmp_path / "book"
    book_state(base, "autonomous")
    kwargs = dict(base_dir=base, observed_at=OBSERVED,
                  verify_receipt=web._decision_execution_receipt_verified,
                  validate_pending=paper_account.pending_target_contract_error)
    expected = decision_availability.read_decision_availability("autonomous", **kwargs)
    seen = []
    def callback(attempt):
        seen.append(copy.deepcopy(attempt))
        if failure == "raises":
            raise RuntimeError("CANARY_PRIVATE_INSPECTOR")
        from app.provider_diagnostic_read import unavailable
        result = unavailable("autonomous", RUN_ID, "synthetic")
        if failure == "wrong_run":
            result["run_id"] = "other"
        elif failure == "wrong_book":
            result["portfolio_id"] = "hk"
        elif failure == "wrong_schema":
            result["schema"] = "unknown"
        else:
            result["effect_reconciliation"] = "performed"
        result["private"] = "CANARY_PRIVATE_BAD_RESULT"
        attempt["run_id"] = "mutated_copy"
        return result
    actual = decision_availability.read_decision_availability(
        "autonomous", **kwargs, inspect_provider_diagnostics=callback)
    assert "CANARY_PRIVATE" not in json.dumps(seen)
    assert seen[0]["run_id"] == RUN_ID
    assert {key: actual[key] for key in expected} == expected
    assert actual["provider_diagnostic_inspection"]["status"] == "unavailable"
    assert "CANARY_PRIVATE" not in json.dumps(actual)


@pytest.mark.parametrize("changed", ["decisions", "account", "wal"])
def test_run_binding_uses_decision_source_and_preserves_independent_account_state(tmp_path, changed):
    base = tmp_path / "book"
    book_state(base, "autonomous")
    logs = tmp_path / "runs"
    write_log(logs)
    def callback(attempt):
        result = inspect(logs, attempt=attempt)
        if changed == "decisions":
            path = base / "decisions.jsonl"
            path.write_bytes(path.read_bytes() + b'{"changed": true}\n')
        elif changed == "account":
            path = base / "account.json"
            path.write_bytes(path.read_bytes() + b'\n')
        else:
            (base / "paper_transaction.json").write_text('{"state":"prepared"}')
        return result
    actual = decision_availability.read_decision_availability(
        "autonomous", base_dir=base, observed_at=OBSERVED,
        verify_receipt=web._decision_execution_receipt_verified,
        validate_pending=paper_account.pending_target_contract_error,
        inspect_provider_diagnostics=callback)
    diagnostic = actual["provider_diagnostic_inspection"]
    if changed == "decisions":
        assert diagnostic["status"] == "provisional"
        assert diagnostic["candidates"] == []
        assert diagnostic["latest_observation_at"] is None
        assert diagnostic["reason"] == "decision_source_changed_during_read"
    else:
        assert diagnostic["status"] == "partial"
        assert len(diagnostic["candidates"]) == 1
        assert diagnostic["decision_binding_consistency"] == "observed_stable"
    assert actual["account"]["cash"] == 8123.45
    assert actual["last_valid_decision"]["summary"] == "Original investment intent"
