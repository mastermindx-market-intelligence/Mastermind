"""Keep native turn completion and returned event evidence on the exact turn."""
from __future__ import annotations

from contextlib import contextmanager

import copy

import pytest

from scripts.ohf.laboratory import PrivateRawTurnPage
from control_plane.codex_operator_adapter import CodexAdapterError
from control_plane.operator_harness_contract import EventCursor, TurnRef
from tests.test_codex_operator_adapter import _make_harness, _op, _start


@contextmanager
def _fixture(tmp_path, *, delayed=False):
    harness = _make_harness(
        tmp_path.resolve(), fault_server=delayed,
        extra_env={"OHF_FAKE_DELAY_COMPLETION": "1"} if delayed else None)
    try:
        _, _, launch = _start(harness)
        yield harness, launch
    finally:
        for state in harness.adapter._generations.values():
            state.client.close()


def _turn(harness, name):
    return TurnRef(name, harness.epoch.session_epoch_id,
                   harness.generation.process_generation_id, harness.epoch.attempt_id)


def _begin(harness, launch, turn):
    return harness.adapter.begin_turn(
        operation_id=_op(turn.turn_id), turn=turn,
        generation=harness.generation, launch=launch)


def _cursor(turn, sequence=0):
    return EventCursor(turn.attempt_id, turn.session_epoch_id,
                       turn.process_generation_id, local_sequence=sequence,
                       turn_id=turn.turn_id)


def test_second_native_turn_returns_only_its_own_events(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        first, second = _turn(harness, "turn-first"), _turn(harness, "turn-second")
        _begin(harness, launch, first)
        first_events, first_cursor = harness.adapter.read_events(_cursor(first))
        assert first_events
        _begin(harness, launch, second)
        second_events, second_cursor = harness.adapter.read_events(_cursor(second))
        assert second_events
        assert all(event.turn_id in {None, second.turn_id} for event in second_events)
        # Local sequence remains generation-global even when the projection is scoped.
        assert second_cursor.local_sequence > first_cursor.local_sequence
        assert second_cursor.local_sequence > len(second_events)
        delta_events, delta_cursor = harness.adapter.read_events(
            _cursor(second, first_cursor.local_sequence))
        assert delta_events == second_events
        assert delta_cursor == second_cursor
        empty, same = harness.adapter.read_events(second_cursor)
        assert empty == () and same == second_cursor


def test_generation_wide_read_retains_both_turns(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        for name in ("turn-first", "turn-second"):
            turn = _turn(harness, name)
            _begin(harness, launch, turn)
            harness.adapter.read_events(_cursor(turn))
        events, cursor = harness.adapter.read_events(EventCursor(
            harness.epoch.attempt_id, harness.epoch.session_epoch_id,
            harness.generation.process_generation_id))
        assert {event.turn_id for event in events} == {"turn-first", "turn-second"}
        assert cursor.local_sequence == len(events)


@pytest.mark.parametrize("native_id", ["late-previous-native-turn", None, 123])
@pytest.mark.parametrize("edge", ["drain", "wait"])
def test_foreign_or_missing_completion_never_finishes_current_turn(
    tmp_path, native_id, edge
):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-current")
        started = _begin(harness, launch, turn)
        assert started.acknowledged
        state = harness.adapter._generations[turn.process_generation_id]
        pending = list(state.client.drain_notifications())
        completion = {"method": "turn/completed", "params": {
            "threadId": state.provider_session_id,
            "turn": {"id": native_id, "status": "completed"}}}
        delivered = []
        def drain():
            if delivered:
                return []
            delivered.append(True)
            return pending + ([completion] if edge == "drain" else [])
        def wait(method, *, timeout):
            return completion
        state.client.drain_notifications = drain
        state.client.wait_notification = wait
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.read_events(_cursor(turn), timeout_seconds=0.01)
        assert failure.value.effect_unknown is True
        assert not any(event.kind == "turn/completed" and event.turn_id == turn.turn_id
                       for event in state.events)


def test_exact_current_completion_still_passes(tmp_path):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-current")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        pending = list(state.client.drain_notifications())
        completion = {"method": "turn/completed", "params": {
            "threadId": state.provider_session_id,
            "turn": {"id": started.provider_native_turn_id, "status": "completed"}}}
        batches = iter([pending + [completion], []])
        state.client.drain_notifications = lambda: next(batches, [])
        events, cursor = harness.adapter.read_events(_cursor(turn), timeout_seconds=.01)
        assert any(event.kind == "turn/completed" and
                   event.provider_event_id == started.provider_native_turn_id
                   for event in events)
        assert cursor.local_sequence == len(state.events)


@pytest.mark.parametrize("top,nested", [
    ([], None), ({}, None), (None, []), (None, {}),
    ("current", "foreign"), ("foreign", "current"),
])
def test_malformed_or_contradictory_thread_identity_is_typed_refusal(tmp_path, top, nested):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-current")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        state.client.drain_notifications()
        def value(item):
            return state.provider_session_id if item == "current" else item
        completion = {"method": "turn/completed", "params": {
            "turn": {"id": started.provider_native_turn_id, "status": "completed"}}}
        if top is not None:
            completion["params"]["threadId"] = value(top)
        if nested is not None:
            completion["params"]["turn"]["threadId"] = value(nested)
        batches = iter([[completion], []])
        state.client.drain_notifications = lambda: next(batches, [])
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.read_events(_cursor(turn), timeout_seconds=.01)
        assert failure.value.effect_unknown is True
        assert not any(event.kind == "turn/completed" for event in state.events)


@pytest.mark.parametrize("defect", [
    "duplicate", "remaining_page", "non_list_data", "non_mapping_row",
    "in_progress", "failed", "status_container", "payload_drift",
])
def test_candidate_identity_failure_preserves_the_original_receipt(tmp_path, defect):
    with _fixture(tmp_path) as (harness, launch):
        turn = _turn(harness, "turn-current")
        started = _begin(harness, launch, turn)
        harness.adapter.read_events(_cursor(turn))
        state = harness.adapter._generations[turn.process_generation_id]
        first = harness.adapter.collect_candidate_result(turn)
        request = state.client.request
        document = copy.deepcopy(request("thread/turns/list", {
            "threadId": state.provider_session_id}))
        selected = [row for row in document["data"]
                    if row.get("id") == started.provider_native_turn_id][0]
        if defect == "duplicate":
            document["data"].append(copy.deepcopy(selected))
        elif defect == "remaining_page":
            document["nextCursor"] = "unread-next-page"
        elif defect == "non_list_data":
            document["data"] = {"id": started.provider_native_turn_id}
        elif defect == "non_mapping_row":
            document["data"].append("unclassified-row")
        elif defect in {"in_progress", "failed", "status_container"}:
            selected["status"] = {
                "in_progress": "inProgress", "failed": "failed",
                "status_container": []}[defect]
        else:
            selected["items"] = [{"type": "agentMessage", "text": "changed output"}]
        # Collection shares the existing private full-page reader with the
        # canonical-result path. Repeated unfinished pages remain a refusal.
        state.client.request_raw_turn_page = lambda **kwargs: PrivateRawTurnPage(
            copy.deepcopy(document), 100)
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_candidate_result(turn)
        assert failure.value.effect_unknown is True
        assert state.candidate_artifact_digests[turn.turn_id] == first.artifact_digest


def test_same_candidate_recollection_preserves_identity(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        turn = _turn(harness, "turn-current")
        _begin(harness, launch, turn)
        harness.adapter.read_events(_cursor(turn))
        first = harness.adapter.collect_candidate_result(turn)
        assert harness.adapter.collect_candidate_result(turn) == first


@pytest.mark.parametrize("defect", [
    "duplicate", "remaining_page", "non_mapping_row", "non_list_data",
    "in_progress", "failed", "status_container",
])
def test_first_candidate_must_be_unique_complete_and_consistent(tmp_path, defect):
    with _fixture(tmp_path) as (harness, launch):
        turn = _turn(harness, "turn-current")
        started = _begin(harness, launch, turn)
        harness.adapter.read_events(_cursor(turn))
        state = harness.adapter._generations[turn.process_generation_id]
        assert turn.turn_id not in state.candidate_artifact_digests
        request = state.client.request
        document = copy.deepcopy(request("thread/turns/list", {
            "threadId": state.provider_session_id}))
        selected = [row for row in document["data"]
                    if row.get("id") == started.provider_native_turn_id][0]
        if defect == "duplicate":
            document["data"].append(copy.deepcopy(selected))
        elif defect == "remaining_page":
            document["nextCursor"] = "unread-next-page"
        elif defect == "non_mapping_row":
            document["data"].append("unclassified-row")
        elif defect == "non_list_data":
            document["data"] = {"id": started.provider_native_turn_id}
        else:
            selected["status"] = {
                "in_progress": "inProgress", "failed": "failed",
                "status_container": []}[defect]
        # Collection shares the existing private full-page reader with the
        # canonical-result path. Repeated unfinished pages remain a refusal.
        state.client.request_raw_turn_page = lambda **kwargs: PrivateRawTurnPage(
            copy.deepcopy(document), 100)
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.collect_candidate_result(turn)
        assert failure.value.effect_unknown is True
        assert turn.turn_id not in state.candidate_artifact_digests
