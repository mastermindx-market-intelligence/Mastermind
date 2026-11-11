"""Native CLI composition, exact environment, bounds and no-replay regressions."""
from __future__ import annotations

import asyncio
import json
import unittest

from integrations.session_bridge.t3_cli_transport import (
    MAX_CATALOG_BYTES, NativeCliFailure, T3NativeCliTransport,
)
from integrations.session_bridge.t3_native_client import (
    MAX_BYTES, EffectUnknown, Rejected, Scope, Unavailable,
)
from integrations.session_bridge.t3_web_client import CliResult

SCOPE = Scope("qualified-host-cli", "environment-1", "project-1")
COMMAND = ("/opt/bin/node", "/qualified/t3/apps/server/src/bin.ts")


def envelope(body, **extra):
    return {"content": [{"type": "text", "text": json.dumps(body)}],
            "structuredContent": body, "isError": False, **extra}


def catalog():
    fields = {
        "t3_environment_read": {},
        "t3_thread_read": {"threadId": {}, "cursor": {}, "limit": {}, "textLimit": {}, "itemId": {}},
        "t3_thread_send": {"threadId": {}, "message": {}, "mode": {}},
        "t3_thread_launch": {"projectId": {}, "message": {}, "modelSelection": {}},
        "t3_thread_configure": {"threadId": {}, "modelSelection": {}},
        "t3_thread_lifecycle": {"threadId": {}, "action": {}, "modelSelection": {}},
    }
    return {"tools": [{"name": name, "inputSchema": {"type": "object", "properties": props}}
                      for name, props in fields.items()]}


class Runner:
    def __init__(self):
        self.calls = []
        self.responses = [catalog(), envelope({"environmentId": SCOPE.environment_id})]

    def __call__(self, invocation):
        self.calls.append(invocation)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result if isinstance(result, CliResult) else CliResult(0, json.dumps(result))


class NativeCliTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runner = Runner()
        self.transport = T3NativeCliTransport(COMMAND, self.runner)

    async def connected(self):
        return await self.transport.connect(SCOPE)

    async def test_connect_uses_exact_native_entrypoint_and_environment_guard(self):
        client = await self.connected()
        self.assertEqual(client.scope, SCOPE)
        self.assertEqual(len(self.runner.calls), 2)
        self.assertEqual(self.runner.calls[0].argv, (*COMMAND, "--log-level", "error", "thread",
                         "native-catalog", "--json", "--expected-environment-id", "environment-1"))
        self.assertIsNone(self.runner.calls[0].stdin)
        self.assertEqual(json.loads(self.runner.calls[1].stdin), {})
        self.assertIn("t3_environment_read", self.runner.calls[1].argv)

    async def test_async_runner_is_supported(self):
        async def run(invocation):
            return self.runner(invocation)
        transport = T3NativeCliTransport(("/qualified/t3",), run)
        self.assertEqual((await transport.connect(SCOPE)).scope, SCOPE)

    async def test_capability_discovery_does_not_grant_unbound_invocation(self):
        await self.transport.discover()
        before = len(self.runner.calls)
        with self.assertRaises(Unavailable):
            await self.transport.call_tool("t3_thread_read", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), before)

    async def test_preserves_original_mcp_envelope_verbatim(self):
        await self.connected()
        original = envelope({"threadId": "thread-1", "sequence": 7}, _meta={"native": "receipt"})
        self.runner.responses.append(original)
        self.assertEqual(await self.transport.call_tool("t3_thread_read", {"threadId": "thread-1"}), original)
        self.assertEqual(len(self.runner.calls), 3)
        self.assertEqual(self.runner.calls[-1].argv[-2:], ("--expected-environment-id", "environment-1"))

    async def test_native_error_envelope_is_not_converted_to_success(self):
        client = await self.connected()
        self.runner.responses.append({"isError": True, "structuredContent": {"code": "capability_denied"}})
        with self.assertRaises(Rejected) as result:
            await client._call("t3_thread_send", {"threadId": "thread-1"}, modifying=True,
                               request_id="original-request", thread_id="thread-1")
        self.assertEqual(result.exception.code, "capability_denied")
        self.assertEqual(len(self.runner.calls), 3)

    async def test_transport_failure_on_modification_is_unknown_without_replay(self):
        client = await self.connected()
        self.runner.responses.append(CliResult(2, "", "Bearer secret-diagnostic-never-display"))
        with self.assertRaises(EffectUnknown) as result:
            await client._call("t3_thread_send", {"threadId": "thread-1"}, modifying=True,
                               request_id="original-request", thread_id="thread-1")
        self.assertEqual((result.exception.request_id, result.exception.thread_id), ("original-request", "thread-1"))
        self.assertNotIn("secret", str(result.exception))
        self.assertEqual(len(self.runner.calls), 3)

    async def test_cancellation_on_modification_stays_original_effect_unknown(self):
        client = await self.connected()
        self.runner.responses.append(asyncio.CancelledError())
        with self.assertRaises(EffectUnknown):
            await client._call("t3_thread_send", {"threadId": "thread-1"}, modifying=True,
                               request_id="original-request", thread_id="thread-1")
        self.assertEqual(len(self.runner.calls), 3)

    async def test_read_cancellation_is_not_swallowed(self):
        await self.connected()
        self.runner.responses.append(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.transport.call_tool("t3_thread_read", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_failure_retains_original_invocation_but_not_raw_diagnostics(self):
        await self.connected()
        self.runner.responses.append(CliResult(1, "not json", "private-key-material"))
        with self.assertRaises(NativeCliFailure) as result:
            await self.transport.call_tool("t3_thread_read", {"threadId": "thread-1"})
        self.assertIs(result.exception.invocation, self.runner.calls[-1])
        self.assertTrue(result.exception.attempted)
        self.assertNotIn("private", str(result.exception))

    async def test_environment_mismatch_clears_capabilities_and_cannot_retarget(self):
        self.runner.responses[1] = envelope({"environmentId": "foreign-environment"})
        with self.assertRaises(Unavailable):
            await self.connected()
        with self.assertRaises(Unavailable):
            await self.transport.call_tool("t3_thread_send", {"threadId": "thread-1"})
        with self.assertRaises(Unavailable):
            await self.transport.connect(Scope("other", "foreign-environment", "project-1"))
        self.assertEqual(len(self.runner.calls), 2)

    async def test_connect_observation_failure_clears_discovery(self):
        self.runner.responses[1] = OSError("unavailable")
        with self.assertRaises(NativeCliFailure):
            await self.connected()
        with self.assertRaises(Unavailable):
            await self.transport.call_tool("t3_thread_read", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), 2)

    async def test_connect_refuses_nonboolean_or_error_environment_flag(self):
        for flag in (0, 1, True, "false", [], {}):
            with self.subTest(flag=flag):
                runner = Runner()
                runner.responses[1]["isError"] = flag
                with self.assertRaises(Unavailable):
                    await T3NativeCliTransport(COMMAND, runner).connect(SCOPE)
                self.assertEqual(len(runner.calls), 2)

    async def test_failed_refresh_cannot_reuse_stale_tool_snapshot(self):
        await self.connected()
        self.runner.responses.append(CliResult(1, ""))
        with self.assertRaises(NativeCliFailure):
            await self.transport.discover()
        with self.assertRaises(Unavailable):
            await self.transport.call_tool("t3_thread_send", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_catalog_schema_is_copied_not_caller_mutable(self):
        discovered = await self.transport.discover()
        discovered["t3_thread_read"]["properties"]["secretOverride"] = {}
        self.runner.responses = [catalog(), envelope({"environmentId": SCOPE.environment_id})]
        await self.connected()
        with self.assertRaises(Unavailable):
            await self.transport.call_tool("t3_thread_read", {"secretOverride": "x"})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_invalid_catalogs_are_rejected_before_environment_or_write(self):
        base = catalog()
        cases = [
            {}, {"tools": []}, {"tools": "not-list"}, {"tools": base["tools"] * 2},
            {"tools": [{"name": "request_secret", "inputSchema": {"type": "object", "properties": {}}}]},
            {"tools": [{"name": [], "inputSchema": {}}]},
            {"tools": [{"name": "t3_environment_read", "inputSchema": {"type": "array", "properties": {}}}]},
            {"tools": [{"name": "t3_environment_read", "inputSchema": {"type": "object"}}]},
            {"tools": [{"name": "t3_environment_read", "inputSchema": {"type": "object", "properties": {}, "required": ["absent"]}}]},
            {"tools": [{"name": "t3_environment_read", "inputSchema": {"type": "object", "properties": {}, "required": "bad"}}]},
            {"tools": base["tools"][1:]},
        ]
        for value in cases:
            with self.subTest(value=value):
                runner = Runner(); runner.responses = [value]
                with self.assertRaises(Unavailable):
                    await T3NativeCliTransport(COMMAND, runner).connect(SCOPE)
                self.assertEqual(len(runner.calls), 1)

    async def test_stdout_must_be_one_bounded_strict_json_object(self):
        invalid = ['{"tools":[],"tools":[]}', '{"tools":NaN}', '[]', '{}\n{}', 'log\n{}', '',
                   '{"x":"' + 'x' * MAX_CATALOG_BYTES + '"}']
        for text in invalid:
            with self.subTest(length=len(text)):
                runner = Runner(); runner.responses = [CliResult(0, text, "sensitive diagnostics")]
                with self.assertRaises(Unavailable):
                    await T3NativeCliTransport(COMMAND, runner).discover()
                self.assertEqual(len(runner.calls), 1)

    async def test_native_response_byte_limit_counts_utf8_not_characters(self):
        await self.connected()
        text = json.dumps({"text": "\u4e2d" * (MAX_BYTES // 2)}, ensure_ascii=False)
        self.assertLess(len(text), MAX_BYTES)
        self.runner.responses.append(CliResult(0, text))
        with self.assertRaises(NativeCliFailure):
            await self.transport.call_tool("t3_thread_read", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_nonzero_exit_cannot_smuggle_a_success_envelope(self):
        await self.connected()
        self.runner.responses.append(CliResult(1, json.dumps(envelope({"sequence": 8}))))
        with self.assertRaises(NativeCliFailure):
            await self.transport.call_tool("t3_thread_send", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_boolean_returncode_is_not_integer_success(self):
        self.runner.responses = [CliResult(False, json.dumps(catalog()))]
        with self.assertRaises(NativeCliFailure):
            await self.transport.discover()

    async def test_unknown_tools_and_arguments_never_invoke_runner(self):
        await self.connected()
        for name, args in [("request_secret", {}), ("t3_thread_read", {"unknown": True}),
                           ("t3_thread_read", [])]:
            with self.subTest(name=name, args=args):
                with self.assertRaises((Unavailable, ValueError)):
                    await self.transport.call_tool(name, args)
        self.assertEqual(len(self.runner.calls), 2)

    async def test_required_schema_inputs_are_enforced(self):
        self.runner.responses[0]["tools"][1]["inputSchema"]["required"] = ["threadId"]
        await self.connected()
        with self.assertRaises(Unavailable):
            await self.transport.call_tool("t3_thread_read", {})
        self.assertEqual(len(self.runner.calls), 2)

    async def test_explicit_capacity_only_selection_without_default_or_fallback(self):
        await self.connected()
        cases = [("t3_thread_launch", {}),
                 ("t3_thread_launch", {"modelSelection": {"instanceId": "other"}}),
                 ("t3_thread_configure", {"modelSelection": {"instanceId": "other"}}),
                 ("t3_thread_lifecycle", {"action": "set_model"}),
                 ("t3_thread_lifecycle", {"action": "set_model", "modelSelection": {"instanceId": "other"}})]
        for name, args in cases:
            with self.subTest(name=name, args=args):
                with self.assertRaises(ValueError):
                    await self.transport.call_tool(name, args)
        self.assertEqual(len(self.runner.calls), 2)
        self.runner.responses.append(envelope({"threadId": "thread-1"}))
        await self.transport.call_tool("t3_thread_launch", {"modelSelection": {"instanceId": "capacity_fabric", "modelId": "logical-model"}})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_configuration_read_does_not_need_healthy_capacity(self):
        await self.connected()
        self.runner.responses.append(envelope({"threadId": "thread-1"}))
        await self.transport.call_tool("t3_thread_configure", {"threadId": "thread-1"})
        self.assertEqual(len(self.runner.calls), 3)

    async def test_oversized_or_nonfinite_input_never_invokes_runner(self):
        await self.connected()
        for message in ("x" * MAX_BYTES, float("nan")):
            with self.subTest(type=type(message).__name__):
                with self.assertRaises(ValueError):
                    await self.transport.call_tool("t3_thread_send", {"message": message})
        self.assertEqual(len(self.runner.calls), 2)

    def test_no_shell_options_relative_paths_or_arbitrary_scripts(self):
        invalid = [("t3",), ("/t3", "--base-dir"), ("/bin/node", "/tmp/worker.py"),
                   ("/t3", "/tmp/bin.ts", "--flag"), ("/tmp/../t3",), ("/t3\n",), ["/t3"]]
        for command in invalid:
            with self.subTest(command=command):
                with self.assertRaises(ValueError):
                    T3NativeCliTransport(command, self.runner)


if __name__ == "__main__":
    unittest.main()
