"""Focused ACP integration checks; run in the optional acp-worker environment."""
import asyncio
import json
from pathlib import Path
import unittest

try:
    import acp
except ImportError:
    acp = None

from control_plane.worker_execution_contract import WorkerLaunchSpec
from integrations.acp_worker.turn import AcpProfile, AcpReadOnlyTurn


@unittest.skipIf(acp is None, "optional ACP SDK absent; ACP capability is NOT qualified")
class AcpTurnTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, behavior="ok", *, requested="model-a"):
        from acp.schema import (
            AgentMessageChunk, InitializeResponse, Implementation, NewSessionResponse,
            PromptResponse, SessionConfigOptionSelect, SessionConfigSelectOption,
            TextContentBlock,
        )
        started = asyncio.Event()
        stopped = asyncio.Event()
        records = {"prompts": 0, "cancels": 0, "denied": False}
        handlers = set()

        class Peer:
            def on_connect(self, client):
                self.client = client

            async def initialize(self, **kwargs):
                return InitializeResponse(protocol_version=acp.PROTOCOL_VERSION,
                    agent_info=Implementation(name="fixture", version="1"))

            async def new_session(self, **kwargs):
                assert kwargs["mcp_servers"] == []
                return NewSessionResponse(session_id="session-1", config_options=[
                    SessionConfigOptionSelect(id="model", name="Model", category="model",
                        type="select", current_value="model-a", options=[
                            SessionConfigSelectOption(value="model-a", name="Model A")])])

            async def prompt(self, session_id, prompt, **kwargs):
                records["prompts"] += 1
                started.set()
                if behavior == "wait":
                    await stopped.wait()
                    return PromptResponse(stop_reason="cancelled")
                if behavior == "forbidden-read":
                    try:
                        await self.client.read_text_file(session_id=session_id, path="/unapproved")
                    except acp.RequestError:
                        records["denied"] = True
                text = '{"answer":42}' if behavior != "duplicate-json" else '{"answer":1,"answer":42}'
                await self.client.session_update(session_id=("wrong-session" if behavior == "wrong-session" else session_id),
                    update=AgentMessageChunk(session_update="agent_message_chunk",
                        content=TextContentBlock(type="text", text=text)))
                return PromptResponse(stop_reason="end_turn")

            async def cancel(self, session_id, **kwargs):
                records["cancels"] += 1
                stopped.set()

        async def handle(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                await acp.run_agent(Peer(), writer, reader)
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(task)

        server = await asyncio.start_server(handle, "127.0.0.1", 0, limit=65536)
        cancel = asyncio.Event()
        reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1], limit=65536)
        spec = WorkerLaunchSpec(run_id="run-1", job_id="JOB-1", worker_id="worker-1",
            workspace_path=Path("/fixture"), run_dir=Path("/fixture-run"), prompt="Return an answer.",
            result_schema_path=Path("/fixture-schema"), authorities=("READ", "RESEARCH"),
            model=requested, timeout_seconds=2, cancel_grace_seconds=1)
        driver = AcpReadOnlyTurn(AcpProfile(agent_name="fixture", agent_version="1"))

        def validate(value):
            if set(value) != {"answer"} or type(value["answer"]) is not int:
                raise ValueError("invalid result")

        try:
            task = asyncio.create_task(driver.run(spec, writer, reader, cancelled=cancel, validate_output=validate))
            if behavior == "wait":
                await asyncio.wait_for(started.wait(), 1)
                cancel.set()
            result = await asyncio.wait_for(task, 4)
            with self.assertRaisesRegex(ValueError, "cannot be replayed"):
                await driver.run(spec, writer, reader, cancelled=cancel, validate_output=validate)
            self.assertFalse(driver.unsettled_tasks)
            return result, records
        finally:
            stopped.set()
            writer.close()
            await writer.wait_closed()
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.wait_for(asyncio.gather(*tuple(handlers)), 1)

    async def test_original_sdk_roundtrip_returns_validated_candidate(self):
        result, calls = await self.exercise()
        self.assertIsNone(result.error)
        self.assertFalse(result.effect_unknown)
        self.assertEqual(json.loads(result.output_json), {"answer": 42})
        self.assertEqual(result.observed_model, "model-a")
        self.assertEqual(calls["prompts"], 1)
        self.assertEqual(dict(result.usage), {})

    async def test_unadvertised_model_never_starts_prompt(self):
        result, calls = await self.exercise(requested="model-b")
        self.assertEqual(result.error, "ACP_MODEL_UNAVAILABLE")
        self.assertEqual(calls["prompts"], 0)

    async def test_cancel_consumes_original_prompt_terminal(self):
        result, calls = await self.exercise("wait")
        self.assertEqual(calls["cancels"], 1)
        self.assertTrue(result.cancellation_observed)
        self.assertEqual(result.stop_reason, "cancelled")
        self.assertFalse(result.effect_unknown)
        self.assertIsNone(result.output_json)

    async def test_unadvertised_filesystem_request_refuses_candidate(self):
        result, calls = await self.exercise("forbidden-read")
        self.assertTrue(calls["denied"])
        self.assertEqual(result.error, "ACP_CLIENT_CAPABILITY_REFUSED")
        self.assertIsNone(result.output_json)

    async def test_other_session_cannot_supply_output(self):
        result, _ = await self.exercise("wrong-session")
        self.assertEqual(result.error, "ACP_SESSION_MISMATCH")
        self.assertIsNone(result.output_json)

    async def test_duplicate_json_fields_are_not_accepted(self):
        result, _ = await self.exercise("duplicate-json")
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.output_json)


if __name__ == "__main__":
    unittest.main()
