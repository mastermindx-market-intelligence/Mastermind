"""Repeated attended turns on one retained native conversation; no live I/O.

The incumbent fresh-conversation owner keeps ONE retained native writer for
successive explicitly submitted messages. Every turn is separately reserved,
executed and recorded as an immutable Event; no session, queue or history
store is added and the original identity never changes.
"""
import asyncio
import dataclasses
import time

import pytest

from control_plane.fresh_conversation import FreshConversationOwner
from control_plane.principal_projection import neutral_principal_projection
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.gateway import AppPolicies
from tests import test_mastermind_executive_app_asgi as auth
from tests.test_fresh_conversation import cleanup
from tests.test_fresh_conversation_http import mounted, post, rsa_key


async def _reader(service, runtime, calls, rsa_key, work_ref):
    """The actual read-only reader of the same original identity."""
    raw = calls[-1]["principal"]
    principal = neutral_principal_projection(**{**raw, "scopes": tuple(raw["scopes"])})
    expected = (principal.policy_id, principal.issuer_digest, principal.resource)
    policies = AppPolicies(auth._read_policy(), auth._submit_policy())
    read_auth = JwtAuthenticator(policy=policies.read, jwks_cache=auth._FakeJwksCache(rsa_key))
    now = int(time.time())
    read_token = auth._read_token(rsa_key, iat=now - 1, nbf=now - 1, exp=now + 600)
    actual = await read_auth.verify_token(read_token, now=now)
    read_principal = neutral_principal_projection(**dataclasses.asdict(actual))
    reader = FreshConversationOwner(service, expected_policy=expected, authorized_policies=policies)
    catalogue = reader.project_references(read_principal, {"work_ref": work_ref})
    reference = catalogue["entries"][0]["reference"]
    return reader, read_principal, reference


async def _original(app, token, wt, request):
    """One real original: preview, create, read and consume its first reply."""
    _, preview = await post(app, "preview", request, token, wt)
    _, created = await post(app, "create",
        {**request, "preview_digest": preview["data"]["preview"]["digest"]}, token, wt)
    assert created["ok"] and created["data"]["state"] == "CREATED", created
    selected = {key: request[key] for key in ("work_ref", "operation_key")}
    _, initial = await post(app, "read", selected, token)
    consume_request = {**selected, "initial_digest": initial["data"]["result"]["digest"]}
    _, consumed = await post(app, "consume", consume_request, token, wt)
    assert consumed["ok"] and consumed["data"]["state"] == "CONSUMED", consumed
    return created, initial, consume_request, consumed


def test_initial_and_two_followups_share_one_retained_original(tmp_path, rsa_key, monkeypatch):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            created, initial, consume_request, consumed = await _original(app, token, wt, request)
            messages = ["First follow-up message.", "Second follow-up message."]
            replies = []
            for index, message in enumerate(messages):
                turn = {**consume_request, "turn_key": f"repeated-turn-{index}", "message": message}
                code, response = await post(app, "turn", turn, token, wt)
                assert code == 200 and response["ok"] and response["data"]["state"] == "RECORDED", response
                # The original identity, its consumption and its locator never move.
                assert response["data"]["locator"] == consumed["data"]["locator"]
                assert response["data"]["initial_consumption"] == consumed["data"]["initial_consumption"]
                assert response["data"]["result"]["digest"]
                assert not response["data"]["parent_consumed"]
                # The same retained writer answered every message.
                assert message in adapters[0].prompts[-1]
                replies.append(response["data"])
            assert adapters[0].start_calls == 1 and adapters[0].begin_turn_calls == 3
            assert len(runtime.jobs.list_jobs()) == 2 and len(runtime.attempts.list_attempts()) == 1
            recorded = [event for event in runtime.events.list_events()
                if event.event_type == "FRESH_CONVERSATION_TURN_RECORDED"]
            assert len(recorded) == 2
            assert len({event.command_id for event in recorded}) == 2
            # The recorded window exposes every actual turn of this original.
            reader, read_principal, reference = await _reader(service, runtime, calls, rsa_key, request["work_ref"])
            archived = reader.read_reference(read_principal, reference)
            assert archived["state"] == "RETAINED" and archived["epoch"] is not None
            assert archived["initial_result"]["digest"] == initial["data"]["result"]["digest"]
            assert [turn["turn_key"] for turn in archived["turns"]] == ["repeated-turn-0", "repeated-turn-1"]
            assert [turn["message"] for turn in archived["turns"]] == messages
            assert all(turn["state"] == "RECORDED" for turn in archived["turns"])
            assert all(turn["result"]["digest"] == reply["result"]["digest"]
                for turn, reply in zip(archived["turns"], replies))
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_duplicate_and_conflicting_next_turn_keys(tmp_path, rsa_key, monkeypatch):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, _, consume_request, consumed = await _original(app, token, wt, request)
            turn = {**consume_request, "turn_key": "duplicate-turn-key", "message": "One bounded follow-up."}
            code, first = await post(app, "turn", turn, token, wt)
            assert code == 200 and first["ok"] and first["data"]["state"] == "RECORDED", first
            events = runtime.events.list_events()
            # The same key with the same payload returns the original turn.
            code, repeated = await post(app, "turn", turn, token, wt)
            assert code == 200 and repeated["ok"] and repeated["data"]["result"] == first["data"]["result"]
            assert runtime.events.list_events() == events and adapters[0].begin_turn_calls == 2
            # The same key with a changed payload is a conflict, never a new turn.
            code, conflict = await post(app, "turn", {**turn, "message": "A different payload."}, token, wt)
            assert code in {202, 400, 403} and not conflict["ok"], conflict
            assert runtime.events.list_events() == events and adapters[0].begin_turn_calls == 2
            # A distinct key is a genuine next message on the same original.
            next_turn = {**consume_request, "turn_key": "next-turn-key", "message": "The next bounded follow-up."}
            code, following = await post(app, "turn", next_turn, token, wt)
            assert code == 200 and following["ok"] and following["data"]["state"] == "RECORDED", following
            assert following["data"]["initial_consumption"] == consumed["data"]["initial_consumption"]
            assert adapters[0].begin_turn_calls == 3
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_concurrent_next_turn_is_refused_until_the_previous_reply_is_recorded(tmp_path, rsa_key, monkeypatch):
    async def run():
        import threading
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        release = threading.Event()
        try:
            _, _, consume_request, _ = await _original(app, token, wt, request)
            entered = asyncio.Event()
            loop = asyncio.get_running_loop()
            def before_io(_kwargs):
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(10)
            service._fixture_before_turn_io = before_io
            first = {**consume_request, "turn_key": "pending-turn-key", "message": "The pending follow-up."}
            running = asyncio.create_task(post(app, "turn", first, token, wt))
            await asyncio.wait_for(entered.wait(), 10)
            # The same key is still the one original request: not a second turn.
            code, same = await post(app, "turn", first, token, wt)
            assert code == 200 and same["ok"] and same["data"]["state"] == "RECONCILIATION_REQUIRED", same
            # A distinct key cannot overtake the unresolved original.
            code, foreign = await post(app, "turn",
                {**consume_request, "turn_key": "overtaking-turn-key", "message": "An overtaking message."}, token, wt)
            assert code in {202, 400, 403} and not foreign["ok"], foreign
            # The reserved turn has not reached the provider yet.
            assert adapters[0].begin_turn_calls == 1
            assert len([event for event in runtime.events.list_events()
                if event.event_type == "FRESH_CONVERSATION_TURN_REQUESTED"]) == 1
            release.set()
            code, completed = await running
            assert code == 200 and completed["ok"] and completed["data"]["state"] == "RECORDED", completed
            # Only after the validated reply may the next message be reserved.
            code, following = await post(app, "turn",
                {**consume_request, "turn_key": "overtaking-turn-key", "message": "An overtaking message."}, token, wt)
            assert code == 200 and following["ok"] and following["data"]["state"] == "RECORDED", following
            assert adapters[0].begin_turn_calls == 3
        finally:
            release.set()
            await cleanup(service)
    asyncio.run(run())


def test_unresolved_previous_turn_blocks_the_next_message(tmp_path, rsa_key, monkeypatch):
    async def run():
        from control_plane.fresh_conversation_turn import FreshConversationTurnSource
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, _, consume_request, _ = await _original(app, token, wt, request)
            def before_io(_kwargs):
                source = service._native_operator_dispatch._fresh_turn_source
                assert type(source) is FreshConversationTurnSource and source.check()
                raise OSError("inert accepted native turn return lost")
            service._fixture_before_turn_io = before_io
            broken = {**consume_request, "turn_key": "unresolved-turn-key", "message": "A lost follow-up."}
            code, unknown = await post(app, "turn", broken, token, wt)
            assert code == 200 and (not unknown["ok"] or unknown["data"]["state"] == "RECONCILIATION_REQUIRED"), unknown
            assert not any(event.event_type == "FRESH_CONVERSATION_TURN_RECORDED"
                for event in runtime.events.list_events())
            # The unresolved original keeps its own request identity and writer.
            code, following = await post(app, "turn",
                {**consume_request, "turn_key": "after-unresolved-key", "message": "A later message."}, token, wt)
            assert code in {202, 400, 403} and not following["ok"], following
            # The interrupted turn never reached the provider.
            assert adapters[0].begin_turn_calls == 1
            requested = [event for event in runtime.events.list_events()
                if event.event_type == "FRESH_CONVERSATION_TURN_REQUESTED"]
            assert len(requested) == 1 and requested[0].payload["turn_key"] == "unresolved-turn-key"
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_source_and_authority_drift_block_the_next_message(tmp_path, rsa_key, monkeypatch):
    async def run():
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            _, _, consume_request, _ = await _original(app, token, wt, request)
            first = {**consume_request, "turn_key": "drift-first-key", "message": "The first follow-up."}
            code, answered = await post(app, "turn", first, token, wt)
            assert code == 200 and answered["ok"] and answered["data"]["state"] == "RECORDED", answered
            events = runtime.events.list_events()
            # The Workspace authority is revalidated for every new message.
            workspace = service._ceo_ingress_app_binding.workspace_read_provider_factory(runtime)
            original_authorize = workspace.authorize
            workspace.authorize = lambda _: False
            code, refused = await post(app, "turn",
                {**consume_request, "turn_key": "drift-second-key", "message": "A later message."}, token, wt)
            assert code in {202, 400, 403} and not refused["ok"], refused
            assert runtime.events.list_events() == events and adapters[0].begin_turn_calls == 2
            # The original dialogue source is revalidated as well.
            workspace.authorize = original_authorize
            original_source = service._ceo_ingress_dialogue_source_provider
            def changed(*args):
                data = original_source(*args)
                return {**data, "commission_ref": {**data["commission_ref"], "content_sha256": "f" * 64}}
            service._ceo_ingress_dialogue_source_provider = changed
            code, refused = await post(app, "turn",
                {**consume_request, "turn_key": "drift-third-key", "message": "A later message."}, token, wt)
            assert code in {202, 400, 403} and not refused["ok"], refused
            assert runtime.events.list_events() == events and adapters[0].begin_turn_calls == 2
        finally:
            await cleanup(service)
    asyncio.run(run())


def test_turn_preview_refuses_while_a_previous_turn_is_unresolved(tmp_path, rsa_key, monkeypatch):
    async def run():
        import threading
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        release = threading.Event()
        try:
            _, _, consume_request, _ = await _original(app, token, wt, request)
            entered = asyncio.Event()
            loop = asyncio.get_running_loop()
            def before_io(_kwargs):
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(10)
            service._fixture_before_turn_io = before_io
            running = asyncio.create_task(post(app, "turn",
                {**consume_request, "turn_key": "preview-pending-key", "message": "A pending message."}, token, wt))
            await asyncio.wait_for(entered.wait(), 10)
            code, refused = await post(app, "turn_preview",
                {**consume_request, "turn_key": "preview-next-key", "message": "A previewed message."}, token, wt)
            assert code in {202, 400, 403} and not refused["ok"], refused
            release.set()
            code, completed = await running
            assert code == 200 and completed["ok"] and completed["data"]["state"] == "RECORDED", completed
            # A resolved predecessor opens the next preview on the same original.
            code, preview = await post(app, "turn_preview",
                {**consume_request, "turn_key": "preview-next-key", "message": "A previewed message."}, token, wt)
            assert code == 200 and preview["ok"], preview
            assert preview["data"]["state"] == "TURN_READY" and preview["data"]["can_send"] is True
            assert preview["data"]["turn_key"] == "preview-next-key"
        finally:
            release.set()
            await cleanup(service)
    asyncio.run(run())


def test_attended_conversation_settles_when_its_retention_window_ends(tmp_path, rsa_key, monkeypatch):
    async def run():
        from control_plane import executive_service
        monkeypatch.setattr(executive_service, "_NATIVE_ATTENDED_TURN_WAIT_SECONDS", 0.5)
        app, token, wt, service, runtime, request, adapters, calls, sink = await mounted(tmp_path, rsa_key, monkeypatch)
        try:
            created, initial, consume_request, consumed = await _original(app, token, wt, request)
            turn = {**consume_request, "turn_key": "settling-turn-key", "message": "A settling follow-up."}
            code, answered = await post(app, "turn", turn, token, wt)
            assert code == 200 and answered["ok"] and answered["data"]["state"] == "RECORDED", answered
            task = service._dispatch_tasks.get(created["data"]["locator"]["job_id"])
            assert task is not None
            await asyncio.wait_for(asyncio.shield(task), 30)
            # The settled original keeps every recorded turn and its identity.
            reader, read_principal, reference = await _reader(service, runtime, calls, rsa_key, request["work_ref"])
            archived = reader.read_reference(read_principal, reference)
            assert archived["state"] == "SETTLED" and archived["epoch"] is None
            assert archived["initial_result"]["digest"] == initial["data"]["result"]["digest"]
            assert [turn["turn_key"] for turn in archived["turns"]] == ["settling-turn-key"]
            assert archived["turns"][0]["result"] == answered["data"]["result"]
            # The settled writer accepts no further message.
            code, refused = await post(app, "turn",
                {**consume_request, "turn_key": "after-settle-key", "message": "A later message."}, token, wt)
            assert code in {202, 400, 403} and not refused["ok"], refused
            assert adapters[0].begin_turn_calls == 2
        finally:
            await cleanup(service)
    asyncio.run(run())
