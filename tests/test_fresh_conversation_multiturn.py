"""Signed sequential attended turns and complete bounded native history."""
import asyncio
import json

import pytest

from tests.test_fresh_conversation_http import mounted, post, rsa_key
from tests.test_fresh_conversation import cleanup
from control_plane.fresh_conversation import FreshConversationOwner
from control_plane.principal_projection import neutral_principal_projection
from integrations.mastermind_executive_app.project_conversation_transport import validate_result


def reader_for(service, calls):
    raw = calls[-1]["principal"]
    principal = neutral_principal_projection(**{**raw, "scopes": tuple(raw["scopes"])})
    return FreshConversationOwner(service, expected_policy=(
        principal.policy_id, principal.issuer_digest, principal.resource)), principal


def test_three_followups_same_native_writer_with_complete_unicode_history(tmp_path, rsa_key, monkeypatch):
    from tests.test_native_retained_runtime import _NativeAdapter
    from control_plane.executive_orchestration_result import canonical_bytes
    original = _NativeAdapter._canonical_result
    def large_result(self, turn):
        value = json.loads(original(self, turn))
        value["current_state"] = "完整" * 2400
        return canonical_bytes(value).decode("utf-8")
    monkeypatch.setattr(_NativeAdapter, "_canonical_result", large_result)
    monkeypatch.setattr("control_plane.executive_service._NATIVE_CONTINUATION_WAIT_SECONDS", 3.0)

    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, preview = await post(app, "preview", request, token, wt)
            _, created = await post(app, "create", {**request, "preview_digest": preview["data"]["preview"]["digest"]}, token, wt)
            assert created["ok"], created
            reader, principal = reader_for(service, calls)
            reference = reader.project_references(principal, {"work_ref": request["work_ref"]})["entries"][0]["reference"]
            initial = reader.read_reference(principal, reference)
            initial_digest = initial["initial_result"]["digest"]
            seal = runtime.events.get_event_by_command_id("orchestration-result-seal:" + created["data"]["locator"]["attempt_id"])
            selection = {"work_ref": request["work_ref"], "reference": reference}
            consume_request = {**selection, "initial_digest": initial_digest}
            _, consumed = await post(app, "consume", consume_request, token, wt)
            assert consumed["ok"], consumed
            stale_request = {**consume_request, "turn_key": "stale-tab-message", "message": "A different tab's earlier draft"}
            _, stale_preview = await post(app, "turn_preview", stale_request, token, wt)
            assert stale_preview["ok"], stale_preview
            replies = {}
            dispatch = service._native_operator_dispatch
            retained = dispatch.retained
            requests = []
            for index in range(3):
                turn = {**consume_request, "turn_key": f"sequential-{index}", "message": f"Follow-up {index}：完整保留"}
                _, reviewed = await post(app, "turn_preview", turn, token, wt)
                assert reviewed["ok"], reviewed
                sent = {**turn, "preview_digest": reviewed["data"]["preview_digest"]}
                _, reply = await post(app, "turn", sent, token, wt)
                assert reply["ok"] and reply["data"]["state"] == "RECORDED", reply
                assert service._native_operator_dispatch is dispatch and dispatch.retained is retained
                assert not dispatch.continuation.done() and dispatch._fresh_turn_source is None
                assert reply["data"]["result"]["envelope"]["current_state"] == "完整" * 2400
                replies[turn["turn_key"]] = reply["data"]["result"]
                requests.append(sent)
                if index == 0:
                    events = runtime.events.list_events()
                    _, stale = await post(app, "turn", {**stale_request,
                        "preview_digest": stale_preview["data"]["preview_digest"]}, token, wt)
                    assert not stale["ok"] and runtime.events.list_events() == events
                    assert adapters[0].begin_turn_calls == 2
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            assert adapters[0].start_calls == 1 and adapters[0].begin_turn_calls == 4
            assert runtime.events.get_event_by_command_id(seal.command_id) == seal
            events = runtime.events.list_events()
            for sent in requests:
                _, duplicate = await post(app, "turn", sent, token, wt)
                assert duplicate["ok"] and duplicate["data"]["result"] == replies[sent["turn_key"]]
            _, conflict = await post(app, "turn", {**requests[0], "message": "Changed same key"}, token, wt)
            assert not conflict["ok"] and runtime.events.list_events() == events
            assert adapters[0].begin_turn_calls == 4
            first = reader.read_reference(principal, reference)
            assert first["schema"] == "mastermind.fresh_conversation_window.v2"
            assert first["initial_result"] == initial["initial_result"]
            assert not first["turns"] and first["page"]["next_before_event_id"] is not None
            found = {}
            page = first
            args = reference
            while True:
                assert validate_result(page, "fresh_read", args) == page
                assert len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode()) <= 28000
                found.update({row["turn_key"]: row["result"] for row in page["turns"]})
                cursor = page["page"]["next_before_event_id"]
                if cursor is None:
                    break
                args = {**reference, "before_event_id": cursor}
                page = reader.read_reference(principal, args)
                assert page["initial_result"] is None and page["initial_digest"] == initial_digest
                assert page["page"]["before_event_id"] == cursor
                assert page["page"]["next_before_event_id"] is None or page["page"]["next_before_event_id"] < cursor
            assert found == replies
            _, consume_status = await post(app, "consume_status", consume_request, token)
            assert consume_status["ok"] and consume_status["data"]["state"] == "CONSUMED", consume_status
            assert runtime.events.list_events() == events
            task = service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None:
                await asyncio.wait_for(asyncio.shield(task), 5)
            assert service._native_operator_dispatch is None and service._service_state == "READY"
            archived = reader.read_reference(principal, reference)
            assert archived["state"] == "SETTLED" and archived["epoch"] is None
            assert archived["initial_result"] == initial["initial_result"]
            cursor = archived["page"]["next_before_event_id"]
            archived_page = reader.read_reference(principal, {**reference, "before_event_id": cursor})
            assert archived_page["turns"][0]["result"] == replies["sequential-2"]
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_initial_only_idle_conversation_finishes_without_quarantine(tmp_path, rsa_key, monkeypatch):
    monkeypatch.setattr("control_plane.executive_service._NATIVE_CONTINUATION_WAIT_SECONDS", 0.2)
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, preview = await post(app, "preview", request, token, wt)
            _, created = await post(app, "create", {**request, "preview_digest": preview["data"]["preview"]["digest"]}, token, wt)
            assert created["ok"], created
            task = service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None:
                await asyncio.wait_for(asyncio.shield(task), 5)
            reader, principal = reader_for(service, calls)
            reference = reader.project_references(principal, {"work_ref": request["work_ref"]})["entries"][0]["reference"]
            archived = reader.read_reference(principal, reference)
            assert archived["state"] == "SETTLED" and archived["initial_result"] and not archived["turns"]
            assert service._service_state == "READY" and not service._dispatch_errors
            assert adapters[0].start_calls == adapters[0].begin_turn_calls == 1
        finally:
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("cursor", [None, True, 0, -1, 1.5, "1", 2**53])
def test_history_cursor_is_strict_and_separate_from_identity(cursor):
    from common.project_conversation_read_contract import arguments
    from tests.test_project_conversation_read_contract import fresh_read_args
    with pytest.raises(ValueError):
        arguments({**fresh_read_args(), "before_event_id": cursor}, "fresh_read")
    assert arguments({**fresh_read_args(), "before_event_id": 42}, "fresh_read")["before_event_id"] == 42


def test_reader_closed_before_execution_settles_original_without_provider_io(tmp_path, rsa_key, monkeypatch):
    from control_plane import fresh_conversation_turn as module
    original = module.execute_attended_turn
    async def close_before_execute(service, dispatch, source):
        service._fixture_active_private_reader.feed_eof()
        return await original(service, dispatch, source)
    monkeypatch.setattr(module, "execute_attended_turn", close_before_execute)
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, preview = await post(app, "preview", request, token, wt)
            _, created = await post(app, "create", {**request, "preview_digest": preview["data"]["preview"]["digest"]}, token, wt)
            assert created["ok"], created
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            _, initial = await post(app, "read", selected, token)
            consumed_request = {**selected, "initial_digest": initial["data"]["result"]["digest"]}
            _, consumed = await post(app, "consume", consumed_request, token, wt)
            assert consumed["ok"], consumed
            turn = {**consumed_request, "turn_key": "closed-before-execute", "message": "Keep the original recovery identity"}
            _, response = await asyncio.wait_for(post(app, "turn", turn, token, wt), 3)
            assert not response["ok"] or response["data"]["state"] == "RECONCILIATION_REQUIRED"
            task = service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None: await asyncio.wait_for(asyncio.shield(task), 5)
            assert adapters[0].begin_turn_calls == 1
            assert len([event for event in runtime.events.list_events() if event.event_type == "FRESH_CONVERSATION_TURN_UNKNOWN"]) == 1
            before = runtime.events.list_events()
            _, status = await post(app, "turn_status", {**selected, "turn_key": turn["turn_key"]}, token)
            assert status["ok"] and status["data"]["state"] == "RECONCILIATION_REQUIRED", status
            await post(app, "turn", turn, token, wt)
            assert runtime.events.list_events() == before and adapters[0].begin_turn_calls == 1
        finally:
            await cleanup(service)
    asyncio.run(run())


@pytest.mark.parametrize("phase", ["before_executor", "after_reply_commit"])
def test_dispatch_cancel_wakes_original_without_fabricating_outcome(tmp_path, rsa_key, monkeypatch, phase):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, preview = await post(app, "preview", request, token, wt)
            _, created = await post(app, "create", {**request, "preview_digest": preview["data"]["preview"]["digest"]}, token, wt)
            assert created["ok"], created
            selected = {key: request[key] for key in ("work_ref", "operation_key")}
            _, initial = await post(app, "read", selected, token)
            consumed_request = {**selected, "initial_digest": initial["data"]["result"]["digest"]}
            _, consumed = await post(app, "consume", consumed_request, token, wt)
            assert consumed["ok"], consumed
            owned = service._run_owned_coroutine
            async def cancel_boundary(coroutine):
                if getattr(coroutine, "cr_code", None) and coroutine.cr_code.co_name == "execute_attended_turn":
                    if phase == "before_executor":
                        coroutine.close()
                    else:
                        await owned(coroutine)
                    raise asyncio.CancelledError()
                return await owned(coroutine)
            monkeypatch.setattr(service, "_run_owned_coroutine", cancel_boundary)
            turn = {**consumed_request, "turn_key": "cancelled-dispatch-"+phase, "message": "Original delivery remains readable"}
            await asyncio.wait_for(post(app, "turn", turn, token, wt), 4)
            task = service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            if task is not None: await asyncio.gather(task, return_exceptions=True)
            _, status = await post(app, "turn_status", {**selected, "turn_key": turn["turn_key"]}, token)
            expected = "RECORDED" if phase == "after_reply_commit" else "RECONCILIATION_REQUIRED"
            assert status["ok"] and status["data"]["state"] == expected, status
            assert not [event for event in runtime.events.list_events() if event.event_type == "FRESH_CONVERSATION_TURN_UNKNOWN"]
            assert adapters[0].begin_turn_calls == (2 if phase == "after_reply_commit" else 1)
        finally:
            await cleanup(service)
    asyncio.run(run())
