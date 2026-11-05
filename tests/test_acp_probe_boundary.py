"""Provider-free tests. No installed provider, host service, or SDK is required."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.ohf.acp_probe_boundary import (
    BoundaryViolation, ProbeClient, ProbeLimits, StrictFrameReader, observe_prompt,
)


def execute(coro):
    return asyncio.run(coro)


def wire(payload):
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


def chunk(session="fixture-1", text="useful result"):
    return {"session_id": session, "update": {
        "sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}}


class FrameTests(unittest.TestCase):
    def read(self, data, *, limit=256, eof=True):
        async def run():
            client = ProbeClient(ProbeLimits(frame_bytes=limit))
            source = asyncio.StreamReader(limit=limit)
            source.feed_data(data)
            if eof:
                source.feed_eof()
            reader = StrictFrameReader(source, client)
            return await reader.readuntil(b"\n"), client
        return execute(run())

    def test_valid_response_bytes_are_preserved(self):
        data = wire({"jsonrpc": "2.0", "id": 1, "result": {"stopReason": "end_turn"}})
        actual, client = self.read(data)
        self.assertEqual(actual, data)
        self.assertIsNone(client.violation)

    def test_oversized_line_is_not_accumulated(self):
        with self.assertRaisesRegex(BoundaryViolation, "FRAME_TOO_LARGE"):
            self.read(b"x" * 1024 + b"\n", limit=128)

    def test_oversized_unterminated_line_is_not_drained(self):
        with self.assertRaisesRegex(BoundaryViolation, "FRAME_TOO_LARGE"):
            self.read(b"x" * 1024, limit=128, eof=False)

    def test_no_partial_eof_can_be_a_complete_response(self):
        with self.assertRaisesRegex(BoundaryViolation, "PARTIAL_FRAME"):
            self.read(b'{"jsonrpc":"2.0","id":1,"result":{}}')

    def test_clean_eof_is_preserved(self):
        with self.assertRaises(asyncio.IncompleteReadError) as caught:
            self.read(b"")
        self.assertEqual(caught.exception.partial, b"")

    def test_bad_frames_latch_and_fail_instead_of_being_skipped(self):
        cases = [
            b'not-json\n', b'\xff\n', b'[]\n', b'null\n', b'\n',
            b'{"jsonrpc":"2.0","id":1,"result":{},"result":{}}\n',
            b'{"jsonrpc":"2.0","id":1,"result":{"x":1,"x":2}}\n',
            b'{"jsonrpc":"2.0","id":1,"result":{"x":NaN}}\n',
            b'{"jsonrpc":"1.0","id":1,"result":{}}\n',
            b'{"jsonrpc":"2.0","id":true,"result":{}}\n',
            b'{"jsonrpc":"2.0","id":1,"result":{},"error":{}}\n',
            b'{"jsonrpc":"2.0","result":{}}\n',
        ]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(BoundaryViolation):
                self.read(data)

    def test_first_bad_frame_cannot_be_recovered_by_next_good_frame(self):
        async def run():
            client = ProbeClient()
            source = asyncio.StreamReader()
            source.feed_data(b'bad\n' + wire({"jsonrpc": "2.0", "id": 1, "result": {}}))
            reader = StrictFrameReader(source, client)
            for _ in range(2):
                with self.assertRaisesRegex(BoundaryViolation, "INVALID_FRAME"):
                    await reader.readuntil(b"\n")
            self.assertEqual(client.violation, "INVALID_FRAME")
        execute(run())

    def test_nonfinite_numeric_and_excessive_nesting_refuse(self):
        for result in ('{"x":1e999}', '[' * 40 + '0' + ']' * 40):
            data = ('{"jsonrpc":"2.0","id":1,"result":' + result + '}\n').encode()
            with self.subTest(result=result), self.assertRaises(BoundaryViolation):
                self.read(data, limit=1024)

    def test_frame_flood_is_bounded_before_sdk_handler_queue(self):
        async def run():
            client = ProbeClient(ProbeLimits(frames=2))
            source = asyncio.StreamReader(limit=client.limits.frame_bytes)
            data = wire({"jsonrpc": "2.0", "id": 1, "result": {}})
            source.feed_data(data * 3)
            reader = StrictFrameReader(source, client)
            await reader.readuntil(); await reader.readuntil()
            with self.assertRaisesRegex(BoundaryViolation, "FRAME_BUDGET_EXCEEDED"):
                await reader.readuntil()
        execute(run())

    def test_reader_limit_must_be_qualified_not_merely_documented(self):
        async def run():
            with self.assertRaisesRegex(BoundaryViolation, "READER_LIMIT_UNQUALIFIED"):
                StrictFrameReader(asyncio.StreamReader(limit=1024), ProbeClient(ProbeLimits(frame_bytes=64)))
        execute(run())

    def test_wire_types_are_preserved_before_pydantic_coercion(self):
        for result in ({"protocolVersion": True}, {"protocolVersion": "1"},
                       {"sessionId": 1}, {"stopReason": 0}):
            with self.subTest(result=result), self.assertRaises(BoundaryViolation):
                self.read(wire({"jsonrpc": "2.0", "id": 1, "result": result}))

    def test_wrong_session_is_rejected_before_asynchronous_callback_scheduling(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1"); client.begin_prompt()
            source = asyncio.StreamReader(limit=client.limits.frame_bytes)
            source.feed_data(wire({"jsonrpc": "2.0", "method": "session/update", "params": {
                "sessionId": "wrong", "update": {"sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "not admitted"}}}}))
            with self.assertRaisesRegex(BoundaryViolation, "SESSION_MISMATCH"):
                await StrictFrameReader(source, client).readuntil()
            self.assertEqual(client.snapshot()["text_bytes"], 0)
        execute(run())

    def test_exact_frame_budget_then_clean_eof_is_valid(self):
        async def run():
            client = ProbeClient(ProbeLimits(frames=1))
            source = asyncio.StreamReader(limit=client.limits.frame_bytes)
            source.feed_data(wire({"jsonrpc": "2.0", "id": 1, "result": {}})); source.feed_eof()
            reader = StrictFrameReader(source, client)
            await reader.readuntil()
            with self.assertRaises(asyncio.IncompleteReadError):
                await reader.readuntil()
            self.assertIsNone(client.violation)
        execute(run())

    def test_oversized_otherwise_valid_json_is_refused(self):
        with self.assertRaisesRegex(BoundaryViolation, "FRAME_TOO_LARGE"):
            self.read(wire({"jsonrpc": "2.0", "id": 1, "result": {"text": "x" * 1024}}), limit=128)

    def test_bad_callback_cannot_disappear_in_sdk_schema_validation(self):
        async def run():
            for params in ({"sessionId": "fixture-1", "update": None},
                           {"sessionId": "fixture-1", "update": {"sessionUpdate": "agent_message_chunk"}},
                           {"sessionId": "fixture-1"}):
                client = ProbeClient(); client.bind_session("fixture-1"); client.begin_prompt()
                source = asyncio.StreamReader(limit=client.limits.frame_bytes)
                source.feed_data(wire({"jsonrpc": "2.0", "method": "session/update", "params": params}))
                with self.subTest(params=params), self.assertRaisesRegex(BoundaryViolation, "UPDATE_NOT_ADMITTED"):
                    await StrictFrameReader(source, client).readuntil()
        execute(run())

    def test_pre_prompt_notification_is_not_accepted_by_sdk_coercion(self):
        async def run():
            client = ProbeClient()
            source = asyncio.StreamReader(limit=client.limits.frame_bytes)
            source.feed_data(wire({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": None}}))
            with self.assertRaisesRegex(BoundaryViolation, "CALLBACK_OUTSIDE_PROMPT"):
                await StrictFrameReader(source, client).readuntil()
        execute(run())

    def test_unknown_rpc_method_cannot_be_silently_ignored(self):
        with self.assertRaisesRegex(BoundaryViolation, "TOOL_NOT_GRANTED"):
            self.read(wire({"jsonrpc": "2.0", "method": "_new_tool", "params": {}}))


class CallbackTests(unittest.TestCase):
    def client(self, **limits):
        client = ProbeClient(ProbeLimits(**limits))
        client.bind_session("fixture-1")
        client.begin_prompt()
        return client

    def test_same_session_text_observation(self):
        client = self.client()
        execute(client.session_update(**chunk(text="result \u2713")))
        receipt = client.snapshot()
        self.assertEqual(receipt["text_bytes"], len("result \u2713".encode()))
        self.assertEqual(receipt["updates"], 1)
        self.assertNotIn("text", receipt)

    def test_wrong_session_poison_is_sticky(self):
        client = self.client()
        execute(client.session_update(**chunk(session="wrong")))
        execute(client.session_update(**chunk()))
        self.assertEqual(client.violation, "SESSION_MISMATCH")
        self.assertEqual(client.snapshot()["text_bytes"], 0)

    def test_callbacks_outside_active_prompt_refuse(self):
        client = ProbeClient()
        execute(client.session_update(**chunk()))
        self.assertEqual(client.violation, "CALLBACK_OUTSIDE_PROMPT")
        other = self.client()
        other.seal()
        execute(other.session_update(**chunk()))
        self.assertEqual(other.violation, "CALLBACK_OUTSIDE_PROMPT")

    def test_session_cannot_be_rebound(self):
        client = self.client()
        with self.assertRaisesRegex(BoundaryViolation, "SESSION_REBIND"):
            client.bind_session("fixture-2")

    def test_session_id_must_be_opaque_and_bounded(self):
        for value in ("", "a" * 129, "../path", "a\n", 1, True, None):
            with self.subTest(value=value), self.assertRaises(BoundaryViolation):
                ProbeClient().bind_session(value)

    def test_no_second_prompt_on_same_probe(self):
        client = self.client()
        client.seal()
        with self.assertRaisesRegex(BoundaryViolation, "PROMPT_ALREADY_ISSUED"):
            client.begin_prompt()

    def test_all_permission_requests_are_denied(self):
        client = self.client()
        response = execute(client.request_permission(
            session_id="fixture-1", tool_call={"toolCallId": "fixture-tool"},
            options=[{"optionId": "allow", "kind": "allow_always", "name": "Allow"}],
        ))
        self.assertEqual(response, {"outcome": {"outcome": "cancelled"}})
        self.assertEqual(client.snapshot()["permission_denials"], 1)
        self.assertIsNone(client.violation)

    def test_permission_wrong_session_is_denied_and_poisoned(self):
        client = self.client()
        response = execute(client.request_permission(session_id="wrong", tool_call={}, options=[]))
        self.assertEqual(response["outcome"]["outcome"], "cancelled")
        self.assertEqual(client.violation, "SESSION_MISMATCH")

    def test_tool_methods_do_not_touch_host(self):
        for name in ("read_text_file", "write_text_file", "create_terminal", "terminal_output",
                     "release_terminal", "wait_for_terminal_exit", "kill_terminal", "ext_method"):
            client = self.client()
            with self.subTest(name=name), self.assertRaisesRegex(BoundaryViolation, "TOOL_NOT_GRANTED"):
                execute(getattr(client, name)(session_id="fixture-1", path="/not-read"))
            self.assertEqual(client.violation, "TOOL_NOT_GRANTED")

    def test_update_and_text_budgets_refuse_utf8_bytes_not_characters(self):
        client = self.client(text_bytes=8)
        execute(client.session_update(**chunk(text="\u20ac" * 3)))
        self.assertEqual(client.violation, "TEXT_BUDGET_EXCEEDED")
        self.assertEqual(client.snapshot()["text_bytes"], 0)
        client = self.client(updates=2)
        for _ in range(3):
            execute(client.session_update(**chunk(text="x")))
        self.assertEqual(client.violation, "UPDATE_BUDGET_EXCEEDED")

    def test_unknown_and_malformed_updates_are_not_silently_ignored(self):
        for update in ({"sessionUpdate": "future_unknown"}, {"sessionUpdate": "agent_message_chunk"},
                       {"sessionUpdate": "agent_message_chunk", "content": {"type": "image"}},
                       {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": 1}}):
            client = self.client()
            execute(client.session_update(session_id="fixture-1", update=update))
            self.assertEqual(client.violation, "UPDATE_NOT_ADMITTED")

    def test_observation_is_not_an_executive_result(self):
        snapshot = self.client().snapshot()
        self.assertEqual(snapshot["proof_scope"], "PROVIDER_FREE_PROTOCOL_ONLY")
        self.assertFalse(snapshot["production_proven"])
        self.assertFalse(snapshot["worker_adapter_implemented"])
        self.assertNotIn("job_id", snapshot)

    def test_permission_storm_has_a_separate_bound(self):
        client = self.client(permission_requests=1)
        for _ in range(2):
            response = execute(client.request_permission(session_id="fixture-1", tool_call={}, options=[]))
            self.assertEqual(response["outcome"]["outcome"], "cancelled")
        self.assertEqual(client.violation, "PERMISSION_BUDGET_EXCEEDED")

    def test_invalid_limits_fail_before_observation(self):
        for kwargs in ({"frames": True}, {"frames": 0}, {"frame_bytes": 1048577}, {"updates": -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ProbeLimits(**kwargs)


class PromptPeer:
    def __init__(self, client, *, response=None, failure=None, wait_cancel=False, wrong_cancel=False):
        self.client, self.response, self.failure = client, response, failure
        self.wait_cancel, self.wrong_cancel = wait_cancel, wrong_cancel
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.calls = []

    async def prompt(self, *, session_id, prompt):
        self.calls.append(("prompt", session_id))
        self.started.set()
        await self.client.session_update(**chunk())
        if self.failure:
            raise self.failure
        if self.wait_cancel:
            await self.cancelled.wait()
            if self.wrong_cancel:
                await asyncio.Event().wait()
            return {"stopReason": "cancelled"}
        return self.response or {"stopReason": "end_turn"}

    async def cancel(self, *, session_id):
        self.calls.append(("cancel", session_id))
        self.cancelled.set()


class PromptTests(unittest.TestCase):
    def test_terminal_end_turn_observed_not_job_accepted(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client)
            receipt = await observe_prompt(peer, client, "fixture input", timeout=0.2)
            self.assertEqual(receipt["disposition"], "OBSERVED_END_TURN")
            self.assertFalse(receipt["production_proven"])
            self.assertEqual(peer.calls, [("prompt", "fixture-1")])
        execute(run())

    def test_cancel_awaits_original_prompt_terminal(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client, wait_cancel=True)
            event = asyncio.Event()
            task = asyncio.create_task(observe_prompt(peer, client, "fixture", cancel_event=event))
            await peer.started.wait(); event.set()
            receipt = await task
            self.assertEqual(receipt["disposition"], "OBSERVED_CANCELLED")
            self.assertEqual(peer.calls, [("prompt", "fixture-1"), ("cancel", "fixture-1")])
        execute(run())

    def test_cancel_notification_alone_is_not_terminal(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client, wait_cancel=True, wrong_cancel=True)
            receipt = await observe_prompt(peer, client, "fixture", timeout=0.01, cancel_timeout=0.01)
            self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
            self.assertEqual(receipt["reason"], "CANCEL_TERMINAL_UNOBSERVED")
            self.assertEqual(len(peer.calls), 2)
        execute(run())

    def test_disconnect_does_not_retry_or_invent_completion(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client, failure=ConnectionError("secret-shaped vendor details"))
            receipt = await observe_prompt(peer, client, "fixture", timeout=0.1)
            self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
            self.assertEqual(receipt["reason"], "PROMPT_TRANSPORT_UNCERTAIN")
            self.assertNotIn("secret-shaped", json.dumps(receipt))
            self.assertEqual(peer.calls, [("prompt", "fixture-1")])
        execute(run())

    def test_unknown_terminal_never_becomes_end_turn(self):
        for response in ({"stopReason": "future_reason"}, {"stopReason": "max_tokens"}, {},
                         {"stopReason": "cancelled"}):
            async def run(response=response):
                client = ProbeClient(); client.bind_session("fixture-1")
                peer = PromptPeer(client, response=response or {"other": True})
                receipt = await observe_prompt(peer, client, "fixture")
                self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
            execute(run())

    def test_poisoned_callback_prevents_successful_terminal_promotion(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client)
            original = peer.prompt
            async def bad(**kwargs):
                await client.session_update(**chunk(session="wrong"))
                return await original(**kwargs)
            peer.prompt = bad
            receipt = await observe_prompt(peer, client, "fixture")
            self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
            self.assertEqual(receipt["reason"], "SESSION_MISMATCH")
        execute(run())

    def test_precancel_has_zero_dispatch(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client); event = asyncio.Event(); event.set()
            receipt = await observe_prompt(peer, client, "fixture", cancel_event=event)
            self.assertEqual(receipt["disposition"], "NOT_DISPATCHED")
            self.assertEqual(peer.calls, [])
        execute(run())

    def test_concurrent_second_turn_refuses_before_second_dispatch(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client, wait_cancel=True)
            first = asyncio.create_task(observe_prompt(peer, client, "first", timeout=0.02))
            await peer.started.wait()
            with self.assertRaisesRegex(BoundaryViolation, "PROMPT_ALREADY_ISSUED"):
                await observe_prompt(peer, client, "second")
            receipt = await first
            self.assertEqual(receipt["disposition"], "OBSERVED_CANCELLED")
            self.assertEqual(sum(name == "prompt" for name, _ in peer.calls), 1)
        execute(run())

    def test_invalid_timeout_and_oversized_input_do_not_dispatch(self):
        for kwargs in ({"timeout": True}, {"timeout": float("inf")}, {"cancel_timeout": 0},
                       {"timeout": 31}):
            async def run(kwargs=kwargs):
                client = ProbeClient(); client.bind_session("fixture-1"); peer = PromptPeer(client)
                with self.assertRaises(ValueError):
                    await observe_prompt(peer, client, "fixture", **kwargs)
                self.assertEqual(peer.calls, [])
            execute(run())

    def test_outer_cancellation_is_not_a_terminal_success_receipt(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client, wait_cancel=True)
            task = asyncio.create_task(observe_prompt(peer, client, "fixture"))
            await peer.started.wait(); task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaisesRegex(BoundaryViolation, "PROMPT_ALREADY_ISSUED"):
                client.begin_prompt()
            self.assertEqual(peer.calls, [("prompt", "fixture-1")])
        execute(run())

    def test_unsettled_local_await_is_not_cleanup_success(self):
        async def run():
            client = ProbeClient(); client.bind_session("fixture-1")
            peer = PromptPeer(client, wait_cancel=True)
            release = asyncio.Event()
            retained = []
            async def stubborn(**kwargs):
                retained.append(asyncio.current_task())
                peer.calls.append(("prompt", kwargs["session_id"]))
                peer.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    await release.wait()
                return {"stopReason": "cancelled"}
            peer.prompt = stubborn
            receipt = await observe_prompt(peer, client, "fixture", timeout=0.005, cancel_timeout=0.005)
            self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
            self.assertEqual(receipt["reason"], "LOCAL_TASK_SETTLEMENT_UNPROVEN")
            self.assertEqual(receipt["local_tasks_pending"], 1)
            release.set()
            await asyncio.wait_for(retained[0], timeout=1)
            self.assertEqual(receipt["disposition"], "INCONCLUSIVE")
        execute(run())


if __name__ == "__main__":
    unittest.main(verbosity=2)
