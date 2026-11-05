"""Finite native history must preserve exact candidate identity and raw-reader parity."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from control_plane import codex_operator_adapter as module
from control_plane.codex_operator_adapter import CodexAdapterError
from scripts.ohf.laboratory import PrivateRawTurnPage
from tests.test_codex_turn_evidence_scope import _fixture, _turn, _begin, _cursor


def _started(harness, launch):
    turn = _turn(harness, "turn-paged")
    started = _begin(harness, launch, turn)
    harness.adapter.read_events(_cursor(turn))
    state = harness.adapter._generations[turn.process_generation_id]
    doc = state.client.request("thread/turns/list", {"threadId": state.provider_session_id})
    row = next(copy.deepcopy(row) for row in doc["data"]
               if row["id"] == started.provider_native_turn_id)
    return turn, state, row


def _pages(monkeypatch, state, pages, *, frame_bytes=100, clock=None):
    calls = []
    original = state.client.request
    def page(cursor, timeout):
        index = 0 if cursor is None else int(cursor.removeprefix("page-"))
        calls.append((cursor, timeout))
        if clock is not None:
            clock[0] += 1
        return copy.deepcopy(pages[index])
    def ordinary(method, params=None, *, timeout=15.0):
        if method == "thread/turns/list":
            return page((params or {}).get("cursor"), timeout)
        return original(method, params, timeout=timeout)
    def private(*, thread_id, native_turn_id, cursor=None, timeout=15.0):
        assert thread_id == state.provider_session_id
        assert native_turn_id in state.turns.values()
        return PrivateRawTurnPage(page(cursor, timeout), frame_bytes)
    monkeypatch.setattr(state.client, "request", ordinary)
    monkeypatch.setattr(state.client, "request_raw_turn_page", private)
    return calls


@pytest.mark.parametrize("selected_page", [0, 1, 2])
def test_candidate_collects_one_exact_result_across_finite_pages(tmp_path, monkeypatch, selected_page):
    with _fixture(tmp_path) as (harness, launch):
        turn, state, row = _started(harness, launch)
        reference = harness.adapter.collect_candidate_result(turn)
        pages = [{"data": [], "nextCursor": "page-1"},
                 {"data": [], "nextCursor": "page-2"},
                 {"data": [], "nextCursor": None}]
        pages[selected_page]["data"] = [row]
        calls = _pages(monkeypatch, state, pages)
        assert harness.adapter.collect_candidate_result(turn) == reference
        assert [x[0] for x in calls] == [None, "page-1", "page-2"]
        assert state.candidate_artifact_digests[turn.turn_id] == reference.artifact_digest


@pytest.mark.parametrize("selected_page", [0, 1])
def test_first_paged_collection_and_raw_result_share_the_existing_reader(tmp_path, monkeypatch, selected_page):
    with _fixture(tmp_path) as (harness, launch):
        turn, state, row = _started(harness, launch)
        row["items"] = [{"type": "agentMessage", "text": "{}"}]
        row["text"] = "{}"
        pages = [{"data": [], "nextCursor": "page-1"}, {"data": [], "nextCursor": None}]
        pages[selected_page]["data"] = [row]
        calls = _pages(monkeypatch, state, pages)
        candidate = harness.adapter.collect_candidate_result(turn)
        observed = harness.adapter.observe_raw_role_result(turn)
        assert observed.provider_turn_artifact_digest == candidate.artifact_digest
        assert observed.canonical_result_json == "{}"
        assert [x[0] for x in calls] == [None, "page-1", None, "page-1"]


@pytest.mark.parametrize("defect", ["duplicate", "missing", "repeated", "malformed_cursor",
    "non_mapping", "non_list", "in_progress", "changed", "page_limit", "byte_limit"])
def test_paged_refusal_never_replaces_prior_candidate(tmp_path, monkeypatch, defect):
    with _fixture(tmp_path) as (harness, launch):
        turn, state, row = _started(harness, launch)
        first = harness.adapter.collect_candidate_result(turn)
        pages = [{"data": [row], "nextCursor": "page-1"}, {"data": [], "nextCursor": None}]
        if defect == "duplicate": pages[1]["data"] = [copy.deepcopy(row)]
        elif defect == "missing": pages[0]["data"] = []
        elif defect == "repeated": pages[1]["nextCursor"] = "page-1"
        elif defect == "malformed_cursor": pages[1]["nextCursor"] = []
        elif defect == "non_mapping": pages[1]["data"] = ["unclassified"]
        elif defect == "non_list": pages[1]["data"] = {}
        elif defect == "in_progress": row["status"] = "inProgress"
        elif defect == "changed": row["items"] = [{"type": "agentMessage", "text": "changed"}]
        elif defect == "page_limit": monkeypatch.setattr(module, "MAX_RAW_TURN_PAGES", 1)
        elif defect == "byte_limit": monkeypatch.setattr(module, "MAX_RAW_TURN_CUMULATIVE_FRAME_BYTES", 150)
        calls = _pages(monkeypatch, state, pages)
        with pytest.raises(CodexAdapterError) as exc:
            harness.adapter.collect_candidate_result(turn)
        assert exc.value.effect_unknown is True
        assert state.candidate_artifact_digests[turn.turn_id] == first.artifact_digest
        assert len(calls) <= 2


def test_paged_read_has_one_absolute_deadline_and_does_not_accept_late_last_page(tmp_path, monkeypatch):
    with _fixture(tmp_path) as (harness, launch):
        turn, state, row = _started(harness, launch)
        clock = [100.0]
        monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        monkeypatch.setattr(module, "RAW_TURN_TOTAL_TIMEOUT_SECONDS", 2.0)
        pages = [{"data": [row], "nextCursor": "page-1"}, {"data": [], "nextCursor": None}]
        calls = _pages(monkeypatch, state, pages, clock=clock)
        with pytest.raises(CodexAdapterError) as exc:
            harness.adapter.collect_candidate_result(turn)
        assert exc.value.effect_unknown is True
        assert turn.turn_id not in state.candidate_artifact_digests
        assert calls == [(None, 2.0), ("page-1", 1.0)]


@pytest.mark.parametrize("frame_bytes", [-1, True, "100"])
def test_private_frame_accounting_is_strict(tmp_path, monkeypatch, frame_bytes):
    with _fixture(tmp_path) as (harness, launch):
        turn, state, row = _started(harness, launch)
        _pages(monkeypatch, state, [{"data": [row], "nextCursor": None}], frame_bytes=frame_bytes)
        with pytest.raises(CodexAdapterError) as exc:
            harness.adapter.collect_candidate_result(turn)
        assert exc.value.effect_unknown is True
        assert turn.turn_id not in state.candidate_artifact_digests


def test_paged_read_refuses_changed_session_before_any_second_request(tmp_path, monkeypatch):
    with _fixture(tmp_path) as (harness, launch):
        turn, state, row = _started(harness, launch)
        old_session = state.provider_session_id
        pages = [{"data": [row], "nextCursor": "page-1"}, {"data": [], "nextCursor": None}]
        calls = _pages(monkeypatch, state, pages)
        private = state.client.request_raw_turn_page
        def drift(**kwargs):
            page = private(**kwargs)
            state.provider_session_id = "changed-native-session"
            return page
        monkeypatch.setattr(state.client, "request_raw_turn_page", drift)
        try:
            with pytest.raises(CodexAdapterError) as exc:
                harness.adapter.collect_candidate_result(turn)
            assert exc.value.effect_unknown is True
            assert len(calls) == 1
            assert turn.turn_id not in state.candidate_artifact_digests
        finally:
            state.provider_session_id = old_session
