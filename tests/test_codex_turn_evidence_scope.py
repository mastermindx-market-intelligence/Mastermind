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
        assert {event.turn_id for event in events if event.turn_id is not None} == {
            "turn-first", "turn-second"}
        # Trailing redacted/generation notifications remain globally visible;
        # they must not be mislabeled as evidence of a completed logical turn.
        for name in ("turn-first", "turn-second"):
            selected = [event for event in events if event.turn_id == name]
            assert selected and selected[-1].kind == "turn/completed"
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
            return [completion]
        state.client.drain_notifications = drain
        state.client.wait_notifications_through = wait
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


# Completed snapshots are a projection of the existing generation event stream.
# A replay must not turn into another provider read or borrow a later turn.
def test_completed_turn_replay_does_not_read_new_provider_notifications(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        turn = _turn(harness, "turn-replay")
        _begin(harness, launch, turn)
        before, endpoint = harness.adapter.read_events(_cursor(turn))
        state = harness.adapter._generations[turn.process_generation_id]
        def no_new_read():
            raise AssertionError("completed evidence replay must not poll provider")
        state.client.drain_notifications = no_new_read
        assert harness.adapter.read_events(_cursor(turn)) == (before, endpoint)
        assert harness.adapter.read_events(endpoint) == ((), endpoint)


def test_completed_turn_cursor_is_stable_after_a_later_turn(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        first = _turn(harness, "turn-first-frozen")
        _begin(harness, launch, first)
        expected = harness.adapter.read_events(_cursor(first))
        second = _turn(harness, "turn-second-live")
        _begin(harness, launch, second)
        new_events, new_cursor = harness.adapter.read_events(_cursor(second))
        assert new_events and new_cursor.local_sequence > expected[1].local_sequence
        assert harness.adapter.read_events(_cursor(first)) == expected
        assert harness.adapter.read_events(expected[1]) == ((), expected[1])


def _completion(state, started):
    return {"method": "turn/completed", "params": {
        "threadId": state.provider_session_id,
        "turn": {"id": started.provider_native_turn_id, "status": "completed"}}}


def test_late_generation_notification_is_not_added_to_completed_snapshot(tmp_path):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-late-generation")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        pending = list(state.client.drain_notifications())
        late = {"method": "account/rateLimits/updated", "params": {}}
        batches = iter([pending + [_completion(state, started), late], []])
        state.client.drain_notifications = lambda: next(batches, [])
        snapshot, endpoint = harness.adapter.read_events(_cursor(turn))
        assert not any(event.kind == late["method"] for event in snapshot)
        assert endpoint.local_sequence < len(state.events)
        global_events, global_cursor = harness.adapter.read_events(EventCursor(
            turn.attempt_id, turn.session_epoch_id, turn.process_generation_id))
        recorded = [event for event in global_events if event.kind == late["method"]]
        assert len(recorded) == 1 and recorded[0].turn_id is None
        assert global_cursor.local_sequence == len(state.events)
        assert harness.adapter.read_events(_cursor(turn)) == (snapshot, endpoint)


def test_turn_cursor_past_its_completion_is_refused_instead_of_rewinding(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        first = _turn(harness, "turn-closed-cursor")
        _begin(harness, launch, first)
        _, first_end = harness.adapter.read_events(_cursor(first))
        second = _turn(harness, "turn-later-cursor")
        _begin(harness, launch, second)
        _, second_end = harness.adapter.read_events(_cursor(second))
        assert second_end.local_sequence > first_end.local_sequence
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter.read_events(_cursor(first, second_end.local_sequence))
        assert "completion" in str(failure.value)


def test_post_completion_foreign_native_id_still_refuses(tmp_path):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-foreign-after-completion")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        foreign = _completion(state, started)
        foreign["params"]["turn"]["id"] = "unknown-foreign-native"
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter._ingest_turn_notifications(
                state, turn, [_completion(state, started), foreign])
        assert failure.value.effect_unknown is True


def test_post_completion_ungranted_helper_still_refuses(tmp_path):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-helper-after-completion")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        helper = {"method": "thread/started", "params": {"thread": {
            "id": "unexpected-helper", "parentThreadId": state.provider_session_id}}}
        with pytest.raises(CodexAdapterError) as failure:
            harness.adapter._ingest_turn_notifications(
                state, turn, [_completion(state, started), helper])
        assert failure.value.effect_unknown is True


def test_post_completion_skill_invalidation_is_not_discarded(tmp_path):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-skill-after-completion")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        harness.adapter.skill_canary_binding = object()
        harness.adapter._ingest_turn_notifications(state, turn, [
            _completion(state, started), {"method": "skills/changed", "params": {}}])
        assert state.skills_changed is True



def test_waited_completion_preserves_actual_queue_order(tmp_path):
    with _fixture(tmp_path, delayed=True) as (harness, launch):
        turn = _turn(harness, "turn-ordered-wait")
        started = _begin(harness, launch, turn)
        state = harness.adapter._generations[turn.process_generation_id]
        state.client.drain_notifications()
        before = {"method": "item/completed", "params": {
            "threadId": state.provider_session_id,
            "item": {"id": "before-waited-completion", "type": "agentMessage"}}}
        after = {"method": "account/rateLimits/updated", "params": {}}
        # Exercise the old method on the RED source and the ordered owner on
        # repaired source; both inject the identical actual notification queue.
        wait_name = ("wait_notifications_through"
                     if hasattr(state.client, "wait_notifications_through")
                     else "wait_notification")
        real_wait = getattr(state.client, wait_name)
        def enqueue_then_wait(method, *, timeout):
            with state.client._notification_condition:
                state.client.notifications.extend([before, _completion(state, started), after])
            return real_wait(method, timeout=timeout)
        setattr(state.client, wait_name, enqueue_then_wait)
        events, end = harness.adapter.read_events(_cursor(turn), timeout_seconds=0.01)
        assert any(event.provider_event_id == "before-waited-completion" for event in events)
        assert events[-1].kind == "turn/completed"
        assert not any(event.kind == after["method"] for event in events)
        assert state.client.drain_notifications() == [after]
        assert harness.adapter.read_events(_cursor(turn)) == (events, end)


def test_interturn_notification_is_generation_only_before_next_provider_start(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        first, second = _turn(harness, "turn-before-idle"), _turn(harness, "turn-after-idle")
        _begin(harness, launch, first)
        first_snapshot = harness.adapter.read_events(_cursor(first))
        state = harness.adapter._generations[first.process_generation_id]
        idle = {"method": "account/rateLimits/updated", "params": {}}
        with state.client._notification_condition:
            state.client.notifications.append(idle)
        send = state.client._send
        witnessed = []
        def start_after_generation_ingestion(payload):
            if payload.get("method") == "turn/start":
                matches = [event for event in state.events if event.kind == idle["method"]]
                assert len(matches) == 1 and matches[0].turn_id is None
                witnessed.append(True)
            return send(payload)
        state.client._send = start_after_generation_ingestion
        _begin(harness, launch, second)
        events, _ = harness.adapter.read_events(_cursor(second))
        assert witnessed == [True]
        assert not any(event.kind == idle["method"] for event in events)
        assert harness.adapter.read_events(_cursor(first)) == first_snapshot


def test_interturn_ungranted_helper_refuses_before_next_provider_start(tmp_path):
    with _fixture(tmp_path) as (harness, launch):
        first, second = _turn(harness, "turn-helper-before"), _turn(harness, "turn-helper-after")
        _begin(harness, launch, first)
        harness.adapter.read_events(_cursor(first))
        state = harness.adapter._generations[first.process_generation_id]
        with state.client._notification_condition:
            state.client.notifications.append({"method": "thread/started", "params": {
                "thread": {"id": "ungranted-idle-helper", "parentThreadId": state.provider_session_id}}})
        send = state.client._send
        started = []
        def record_request(payload):
            if payload.get("method") == "turn/start":
                started.append(True)
            return send(payload)
        state.client._send = record_request
        with pytest.raises(CodexAdapterError):
            _begin(harness, launch, second)
        assert started == []


@pytest.mark.parametrize("helper", [False, True], ids=["ordinary", "ungranted-helper"])
def test_notification_between_old_drain_and_request_send_is_guarded(tmp_path, helper):
    with _fixture(tmp_path) as (harness, launch):
        first, second = _turn(harness, "turn-before-race"), _turn(harness, "turn-after-race")
        _begin(harness, launch, first)
        harness.adapter.read_events(_cursor(first))
        state = harness.adapter._generations[first.process_generation_id]
        notification = (
            {"method": "thread/started", "params": {"thread": {
                "id": "ungranted-race-helper", "parentThreadId": state.provider_session_id}}}
            if helper else {"method": "c3/interturn-race", "params": {}}
        )
        request = state.client.request
        send = state.client._send
        actual_starts = []
        def inject_after_adapter_drain(method, params, **kwargs):
            if method == "turn/start":
                with state.client._notification_condition:
                    state.client.notifications.append(notification)
            return request(method, params, **kwargs)
        def witness_actual_send(payload):
            if payload.get("method") == "turn/start":
                actual_starts.append(payload["id"])
                if not helper:
                    matches = [event for event in state.events
                               if event.kind == notification["method"]]
                    assert len(matches) == 1 and matches[0].turn_id is None
            return send(payload)
        state.client.request = inject_after_adapter_drain
        state.client._send = witness_actual_send
        if helper:
            with pytest.raises(CodexAdapterError):
                _begin(harness, launch, second)
            assert actual_starts == []
        else:
            _begin(harness, launch, second)
            events, _ = harness.adapter.read_events(_cursor(second))
            assert len(actual_starts) == 1
            assert not any(event.kind == notification["method"] for event in events)
