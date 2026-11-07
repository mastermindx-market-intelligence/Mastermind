"""Logical CEO selection custody, with no provider or worker effects."""
from __future__ import annotations

import copy
import dataclasses
from concurrent.futures import ThreadPoolExecutor

import pytest

from control_plane import ceo_intent, ceo_request
from control_plane.executive_inbox import ceo_intent_provenance
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.frontier_selection import (
    FrontierSelectionError, resolve_selection, selection_digest,
    selection_from_provenance, selection_provenance, validate_alias, validate_selection,
)
from control_plane.model_router import ModelRouter
from test_ceo_intent import _v2_intent


def _selection(model=None):
    record = resolve_selection(ModelRouter.load(), "frontier.orchestrator")
    if model is not None:
        record["model"] = model
    return record


def _intent(tmp_path):
    return _v2_intent(
        tmp_path, intent_id="CEO-SELECTION-01", workstream="WS:SELECTION",
        frontier_model_alias="frontier.orchestrator",
    )


def _submit(runtime, intent, tmp_path, **kwargs):
    return ceo_intent.submit_intent(
        runtime, intent, workspace_root=tmp_path, **kwargs,
    )


@pytest.mark.parametrize("alias", ["", " FRONTIER.ORCHESTRATOR", "Frontier.Orchestrator", "frontier.orchestrator ", None, 1, True, [], "a"*65])
def test_alias_is_exact_and_never_repaired(alias):
    with pytest.raises(FrontierSelectionError):
        validate_alias(alias)


def test_snapshot_pins_model_even_when_profile_is_shared():
    first = _selection()
    other = _selection("different-model")
    assert first["execution_profile_digest"] == other["execution_profile_digest"]
    assert selection_digest(first) != selection_digest(other)
    assert first["worker_eligible"] is False
    assert "account_label" not in first
    with pytest.raises(Exception):
        resolve_selection(ModelRouter.load(), "fast.engineering")


@pytest.mark.parametrize("change", [
    {"worker_eligible": True}, {"unknown": "field"},
    {"capabilities": ["research"]}, {"capabilities": ["planning", "planning", "judgment", "escalation"]},
    {"execution_profile_digest": "bad"}, {"model_alias": "another.alias"},
])
def test_closed_snapshot_refuses_malformed_or_mismatched_identity(change):
    record = {**_selection(), **change}
    with pytest.raises(FrontierSelectionError):
        validate_selection(record, requested_alias="frontier.orchestrator")


def test_fresh_selection_requires_trusted_resolution_at_both_sinks(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _intent(tmp_path)
    with pytest.raises(ceo_intent.CeoIntentError):
        _submit(runtime, intent, tmp_path)
    with pytest.raises(StateConflict):
        runtime.jobs.create_v2_orchestration_root(
            intent, fingerprint=ceo_intent.intent_fingerprint(intent),
            command_id=ceo_intent.command_id_for(intent["intent_id"]),
            workspace_root=tmp_path,
        )
    assert runtime.jobs.list_jobs() == []
    assert runtime.attempts.list_attempts() == []


def test_selection_survives_replay_reopen_and_bounded_projection(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent, record = _intent(tmp_path), _selection()
    first = _submit(runtime, intent, tmp_path, frontier_selection=record)
    record["model"] = "mutated-caller-copy"
    replay = _submit(runtime, intent, tmp_path)
    reopened = Runtime.at(tmp_path / "runtime", create=False)
    status = ceo_intent.resolve_intent(reopened, intent["intent_id"])
    projected, warning = ceo_intent_provenance(reopened, first["job_id"])
    assert warning is None
    assert selection_from_provenance(projected) == _selection()
    assert projected["frontier_model_alias"] == intent["frontier_model_alias"]
    assert first["job_id"] == replay["job_id"] == status["job_id"]
    assert first["dispatched"] is replay["dispatched"] is status["dispatched"] is False
    assert replay["duplicate"] is True
    assert len(reopened.jobs.list_jobs()) == 1
    assert reopened.attempts.list_attempts() == []


@pytest.mark.parametrize("replacement", [None, "other-model"])
def test_replay_cannot_remove_or_change_trusted_selection(tmp_path, replacement):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _intent(tmp_path)
    _submit(runtime, intent, tmp_path, frontier_selection=_selection())
    changed = None if replacement is None else _selection(replacement)
    with pytest.raises(ceo_intent.CeoIntentConflict):
        _submit(runtime, intent, tmp_path, frontier_selection=changed)
    assert len(runtime.jobs.list_jobs()) == 1


def test_changed_requested_alias_conflicts_under_original_intent(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _intent(tmp_path)
    _submit(runtime, intent, tmp_path, frontier_selection=_selection())
    changed = dict(intent, frontier_model_alias="different.alias")
    assert ceo_intent.intent_fingerprint(intent) != ceo_intent.intent_fingerprint(changed)
    with pytest.raises(ceo_intent.CeoIntentConflict):
        _submit(runtime, changed, tmp_path)


def test_legacy_absence_cannot_acquire_a_selection(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _intent(tmp_path)
    del intent["frontier_model_alias"]
    with pytest.raises(ceo_intent.CeoIntentError):
        _submit(runtime, intent, tmp_path, frontier_selection=_selection())
    first = _submit(runtime, intent, tmp_path)
    with pytest.raises(ceo_intent.CeoIntentConflict):
        _submit(runtime, intent, tmp_path, frontier_selection=_selection())
    provenance, warning = ceo_intent_provenance(runtime, first["job_id"])
    assert warning is None
    assert selection_from_provenance(provenance) is None


@pytest.mark.parametrize("key", ["frontier_model_alias", "frontier_selection", "frontier_selection_digest"])
def test_partial_provenance_refuses(key):
    provenance = {"schema": ceo_intent.INTENT_SCHEMA_V2, **selection_provenance("frontier.orchestrator", _selection())}
    del provenance[key]
    with pytest.raises(FrontierSelectionError):
        selection_from_provenance(provenance)


def test_corrupt_provenance_is_not_projected(tmp_path, monkeypatch):
    runtime = Runtime.at(tmp_path / "runtime")
    first = _submit(runtime, _intent(tmp_path), tmp_path, frontier_selection=_selection())
    original = runtime.events.list_events
    def corrupt(**kwargs):
        events = original(**kwargs)
        result = []
        for event in events:
            if event.event_type == "JOB_CREATED":
                payload = copy.deepcopy(event.payload)
                payload["provenance"]["frontier_selection_digest"] = "0" * 64
                event = dataclasses.replace(event, payload=payload)
            result.append(event)
        return result
    monkeypatch.setattr(runtime.events, "list_events", corrupt)
    projected, warning = ceo_intent_provenance(runtime, first["job_id"])
    assert projected is None and warning


def test_concurrent_resolution_conflict_keeps_exactly_one_original_root(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    runtime = Runtime.at(root)
    intent = _intent(tmp_path)
    import threading
    barrier, local = threading.Barrier(2), threading.local()
    original_find = runtime.store.find_event_by_command_id
    def concurrent_lookup(command_id):
        found = original_find(command_id)
        if not getattr(local, "looked_up", False):
            local.looked_up = True
            barrier.wait(timeout=10)
        return found
    monkeypatch.setattr(runtime.store, "find_event_by_command_id", concurrent_lookup)
    def submit(model):
        try:
            return _submit(runtime, intent, tmp_path,
                           frontier_selection=_selection(model))
        except ceo_intent.CeoIntentConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["model-one", "model-two"]))
    assert results.count("conflict") == 1
    runtime = Runtime.at(root, create=False)
    assert len(runtime.jobs.list_jobs()) == 1
    assert runtime.attempts.list_attempts() == []


def test_app_and_automated_extension_leave_legacy_request_frozen():
    request = {"operation_key": "selection-fixture", "objective": "Test selection",
               "department": "research", "priority": 2,
               "execution_profile": "research_only"}
    legacy = ceo_request.normalize_high_level_request(request)
    assert ceo_request.normalize_app_request(request) == legacy
    selected = {**request, "frontier_model_alias": "frontier.orchestrator"}
    assert ceo_request.normalize_app_request(selected)["frontier_model_alias"] == "frontier.orchestrator"
    with pytest.raises(ceo_request.CeoRequestInvalid):
        ceo_request.normalize_high_level_request(selected)

@pytest.mark.parametrize("mutation", ["remove", "relabel"])
def test_replay_checks_requested_alias_against_retained_record(tmp_path, monkeypatch, mutation):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _intent(tmp_path)
    _submit(runtime, intent, tmp_path, frontier_selection=_selection())
    original_find = runtime.store.find_event_by_command_id
    def forged_read(command_id):
        event = copy.deepcopy(original_find(command_id))
        if event is not None:
            provenance = event["payload"]["provenance"]
            if mutation == "remove":
                for key in ("frontier_model_alias", "frontier_selection", "frontier_selection_digest"):
                    del provenance[key]
            else:
                record = _selection()
                record["model_alias"] = "different.alias"
                provenance.update(selection_provenance("different.alias", record))
        return event
    monkeypatch.setattr(runtime.store, "find_event_by_command_id", forged_read)
    with pytest.raises(ceo_intent.CeoIntentConflict):
        _submit(runtime, intent, tmp_path)
