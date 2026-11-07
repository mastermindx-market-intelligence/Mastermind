"""Local refusal diagnostics under explicit synthetic run binding; no caller lineage claim."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import pytest

from test_provider_diagnostic_read import OBSERVED, client_for, snapshot, write_log
from test_provider_diagnostic_ui import render

FIXTURE = json.loads((Path(__file__).parent / "fixtures/bot_provider_diagnostics/recorded_local_veto_v1.json").read_text())
RUN_ID = FIXTURE["run_id"]


def recorded_rows(book):
    return copy.deepcopy(FIXTURE["by_book"][book]["rows"])


def read(base, book, attempt):
    from app.provider_diagnostic_read import read_provider_diagnostic_evidence
    return read_provider_diagnostic_evidence(book, attempt, runs_dir=base, observed_at=OBSERVED)


def assert_qualified(d):
    assert d["status"] == "partial"
    assert d["provider_start"] == "not_proven"
    assert d["effect_reconciliation"] == "not_performed"
    assert d["attempt_coverage"] == "partial"
    assert len(d["candidates"]) == 1
    c = d["candidates"][0]
    assert c["status"] == "partial"
    assert c["observation"]["query_entered_observed"] is False
    assert c["observation"]["sdk_messages_observed"] == 0
    assert c["terminals"]["count"] == 0
    assert c["exit"]["end_state"] == "raised"
    assert c["exception"]["class"] == "ProviderStartRefused"
    assert "unsupported_label_omitted" not in c["issues"]


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_recorded_local_veto_class_decodes_without_promoting_query_or_effects(tmp_path, book):
    write_log(tmp_path, recorded_rows(book), run_id=RUN_ID)
    before = snapshot(tmp_path)
    d = read(tmp_path, book, {"book": book, "run_id": RUN_ID})
    assert_qualified(d)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("book", ["autonomous", "china", "hk"])
def test_bound_veto_api_and_bilingual_renderer_preserve_account_and_target(tmp_path, monkeypatch, book):
    # client_for supplies an explicitly synthetic accepted decision and its run ID.
    # This test qualifies decoding/presentation, not actual book-caller provenance.
    client, base, logs = client_for(tmp_path, monkeypatch, book, accepted_error=True)
    route = "/api/portfolio"
    params = {"portfolio": book, "view": "decision_availability"}
    control = client.get(route, params=params).json()
    assert control["latest_attempt"]["run_id"] == RUN_ID
    write_log(logs, recorded_rows(book), run_id=RUN_ID)
    before = snapshot(tmp_path)
    response = client.get(route, params=params)
    assert response.status_code == 200
    data = response.json()
    assert {k:v for k,v in data.items() if k != "provider_diagnostic_inspection"} == {
        k:v for k,v in control.items() if k != "provider_diagnostic_inspection"
    }
    assert data["latest_attempt_kind"] == "accepted_with_error"
    assert data["accepted_target"] == control["accepted_target"]
    assert data["account"] == control["account"]
    for zh in (False, True):
        html = render(data, book, zh)
        assert ("调用因异常结束" if zh else "Invocation ended with an exception") in html
        assert ("调用结束状态" if zh else "Invocation end") in html
        assert ("调用结束与终端信息" if zh else "Invocation end and terminal") in html
        assert "ProviderStartRefused" in html
        assert ("已观察到查询入口" if zh else "Query entry observed") in html
        assert ("否" if zh else "No") in html
        assert ("此错误不会抹去已接受目标" if zh else "The error does not erase that target") in html
        assert ("SDK 抛出异常" if zh else "SDK raised an exception") not in html
        assert "SDK never started" not in html and "No provider calls" not in html and "No effects" not in html
    assert_qualified(data["provider_diagnostic_inspection"])
    assert "SYNTHETIC_PRIVATE_CLEANUP" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert snapshot(tmp_path) == before


def test_unknown_exception_class_is_still_omitted(tmp_path):
    rs = recorded_rows("autonomous")
    rs[1]["provider_diagnostic"]["exit"]["exception_class"] = "SYNTHETIC_PRIVATE_CLASS"
    write_log(tmp_path, rs, run_id=RUN_ID)
    d = read(tmp_path, "autonomous", {"run_id": RUN_ID})
    assert d["candidates"][0]["exception"]["class"] is None
    assert "unsupported_label_omitted" in d["candidates"][0]["issues"]
    assert "SYNTHETIC_PRIVATE_CLASS" not in json.dumps(d)


def test_unbound_synthetic_attempt_keeps_diagnostics_unavailable_in_api_and_renderer(tmp_path, monkeypatch):
    client, base, logs = client_for(tmp_path, monkeypatch, accepted_error=True)
    decisions = base / "decisions.jsonl"
    records = [json.loads(line) for line in decisions.read_text().splitlines()]
    records[-1]["run_id"] = None
    decisions.write_text("".join(json.dumps(row) + "\n" for row in records))
    write_log(logs, recorded_rows("autonomous"), run_id=RUN_ID)
    before = snapshot(tmp_path)
    data = client.get("/api/portfolio?portfolio=autonomous&view=decision_availability").json()
    assert data["latest_attempt"]["run_id"] is None
    d = data["provider_diagnostic_inspection"]
    assert d["status"] == "unavailable" and d["reason"] == "attempt_run_identity_unavailable"
    assert d["candidates"] == []
    assert data["latest_attempt_kind"] == "accepted_with_error"
    assert data["accepted_target"]["target_status"] == "queued"
    for zh in (False, True):
        html = render(data, zh=zh)
        assert ("诊断证据不可用" if zh else "Diagnostic evidence unavailable") in html
        assert "ProviderStartRefused" not in html and "data-sdk-candidate=" not in html
    assert snapshot(tmp_path) == before
