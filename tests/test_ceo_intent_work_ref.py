"""Regression coverage for the strict-v2 receipt work reference."""
from __future__ import annotations

import copy

import pytest

from control_plane.ceo_intent import (
    CeoIntentError,
    CeoIntentConflict,
    command_id_for,
    resolve_intent,
)
from control_plane.executive_runtime import Runtime
from test_ceo_intent import _intent, _submit, _v2_intent


def test_v2_receipt_pins_original_workstream_across_retry_and_reopen(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _v2_intent(
        tmp_path,
        intent_id="CEO-WORK-REF-01",
        workstream="WS:ORIGINAL_PROGRAM",
    )

    first = _submit(runtime, intent, tmp_path)
    second = _submit(runtime, intent, tmp_path)
    reopened = Runtime.at(tmp_path / "runtime", create=False)
    status = resolve_intent(reopened, intent["intent_id"])

    assert first["schema"] == "mastermind.ceo_intent_receipt.v2"
    assert first["work_ref"] == "WS:ORIGINAL_PROGRAM"
    assert second["job_id"] == status["job_id"] == first["job_id"]
    assert second["work_ref"] == status["work_ref"] == first["work_ref"]
    assert second["duplicate"] is True
    assert len(runtime.jobs.list_jobs()) == 1
    assert runtime.attempts.list_attempts() == []


def test_v2_retry_cannot_relabel_workstream(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    original = _v2_intent(
        tmp_path,
        intent_id="CEO-WORK-REF-02",
        workstream="WS:ORIGINAL_PROGRAM",
    )
    first = _submit(runtime, original, tmp_path)

    changed = dict(original, workstream="WS:OTHER_PROGRAM")
    with pytest.raises(CeoIntentConflict):
        _submit(runtime, changed, tmp_path)

    status = resolve_intent(runtime, original["intent_id"])
    assert status["job_id"] == first["job_id"]
    assert status["work_ref"] == "WS:ORIGINAL_PROGRAM"
    assert len(runtime.jobs.list_jobs()) == 1


def test_legacy_v2_without_workstream_keeps_work_ref_absent(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _v2_intent(tmp_path, intent_id="CEO-WORK-REF-03")
    intent.pop("workstream")

    first = _submit(runtime, intent, tmp_path)
    duplicate = _submit(runtime, intent, tmp_path)
    status = resolve_intent(Runtime.at(tmp_path / "runtime", create=False), intent["intent_id"])

    assert "work_ref" not in first
    assert "work_ref" not in duplicate
    assert "work_ref" not in status


def test_malformed_durable_v2_workstream_fails_closed(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _v2_intent(
        tmp_path,
        intent_id="CEO-WORK-REF-04",
        workstream="WS:ORIGINAL_PROGRAM",
    )
    _submit(runtime, intent, tmp_path)
    event_id = command_id_for(intent["intent_id"])
    original_find = runtime.store.find_event_by_command_id

    def malformed_read(command_id):
        event = original_find(command_id)
        if command_id != event_id or event is None:
            return event
        forged = copy.deepcopy(event)
        forged["payload"]["provenance"]["workstream"] = "malformed-pointer"
        return forged

    monkeypatch.setattr(runtime.store, "find_event_by_command_id", malformed_read)

    with pytest.raises(CeoIntentError, match="workstream"):
        resolve_intent(runtime, intent["intent_id"])


def test_v1_workstream_receipt_shape_is_unchanged(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _intent(tmp_path, intent_id="CEO-WORK-REF-05", workstream="WS:V1_PROGRAM")

    receipt = _submit(runtime, intent, tmp_path)

    assert receipt["schema"] == "mastermind.ceo_intent_receipt.v1"
    assert set(receipt) == {
        "schema", "intent_id", "fingerprint", "job_id", "status", "accepted",
        "duplicate", "dispatched", "authority", "grounding", "created_at_ms",
    }
