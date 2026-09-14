"""SDK-dispatch and physical-drain tests for the local Workbench MCP edge."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from common.bounded_sync_executor import (
    BoundedSyncExecutor,
    SyncExecutorCloseTimeout,
    SyncExecutorClosed,
)
from integrations.workbench_local_mcp.adapter import LocalWorkbenchGateway
from integrations.workbench_local_mcp.schemas import (
    CONFIG_SCHEMA,
    MAX_ARGUMENT_BYTES,
    MAX_RESULT_BYTES,
    PROFILE_PRO_READ_PREPARE,
    LocalProfileError,
    TOOL_SPECS,
    canonical_json,
    parse_config,
)


class _Fixtures:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name) / "project"
        root.mkdir()
        (root / "README.md").write_text(
            "# Mastermind\nvalue = 1\n", encoding="utf-8"
        )
        self.payload = {
            "schema": CONFIG_SCHEMA,
            "profile": PROFILE_PRO_READ_PREPARE,
            "project_ref": "test-project",
            "project_root": str(root),
            "allowed_paths": ["README.md"],
            "committed_head": "a" * 40,
            "lease_expires_at_ms": int(time.time() * 1000) + 60_000,
        }
        self.config = parse_config(self.payload)

    def teardown(self) -> None:
        self._tmp.cleanup()


class ServerSurfaceTests(unittest.TestCase):
    def test_sdk_surface_matches_closed_specs(self) -> None:
        try:
            from integrations.workbench_local_mcp.server import build_tools
        except ImportError as exc:
            self.skipTest(f"optional MCP SDK unavailable: {exc}")
        tools = build_tools()
        self.assertEqual([tool.name for tool in tools], [spec.name for spec in TOOL_SPECS])
        for tool in tools:
            annotations = tool.annotations
            self.assertTrue(annotations.readOnlyHint)
            self.assertFalse(annotations.destructiveHint)
            self.assertTrue(annotations.idempotentHint)
            self.assertFalse(annotations.openWorldHint)


class SdkDispatchBoundaryTests(unittest.TestCase):
    """Exercise the real MCP 1.28 request handler and unwrap ServerResult.root."""

    def setUp(self) -> None:
        self.fixtures = _Fixtures()

    def tearDown(self) -> None:
        self.fixtures.teardown()

    @staticmethod
    def _request(name: str, arguments: dict[str, Any] | None = None):
        import mcp.types as mcp_types

        return mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name=name,
                arguments={} if arguments is None else arguments,
            ),
        )

    def _dispatch(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        config=None,
    ):
        async def scenario():
            import mcp.types as mcp_types
            from integrations.workbench_local_mcp.server import build_server

            gateway = LocalWorkbenchGateway.open(config or self.fixtures.config)
            executor = BoundedSyncExecutor(max_concurrency=2)
            try:
                server = build_server(gateway, executor)
                handler = server.request_handlers[mcp_types.CallToolRequest]
                server_result = await handler(self._request(name, arguments))
                self.assertIsInstance(server_result, mcp_types.ServerResult)
                return server_result.root
            finally:
                await executor.aclose(timeout=1.0)
                gateway.close()

        return asyncio.run(scenario())

    @staticmethod
    def _payload(result) -> dict[str, Any]:
        return json.loads(result.content[0].text)

    def test_unknown_tool_is_fixed_bounded_error_before_sdk_warning(self) -> None:
        private_name = "PRIVATE_REJECTED_SENTINEL-" + "x" * 4096
        with self.assertNoLogs("mcp.server.lowlevel.server", level="WARNING"):
            result = self._dispatch(private_name)
        payload = self._payload(result)
        self.assertTrue(result.isError)
        self.assertEqual(payload["tool"], "unknown")
        self.assertEqual(payload["error"]["code"], "TOOL_NOT_AVAILABLE")
        self.assertNotIn(private_name, result.content[0].text)
        self.assertNotIn("PRIVATE_REJECTED_SENTINEL", result.content[0].text)
        self.assertLessEqual(len(result.content[0].text.encode("utf-8")), MAX_RESULT_BYTES)

    def test_valid_manifest_and_file_read_succeed_through_sdk(self) -> None:
        manifest = self._dispatch("workspace_manifest")
        self.assertFalse(manifest.isError)
        self.assertTrue(self._payload(manifest)["ok"])

        read = self._dispatch("read_project_file", {"relative_path": "README.md"})
        self.assertFalse(read.isError)
        payload = self._payload(read)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["content"], "# Mastermind\nvalue = 1\n")

    def test_refused_path_and_expired_lease_are_sdk_errors(self) -> None:
        refused = self._dispatch(
            "read_project_file", {"relative_path": "private.env"}
        )
        self.assertTrue(refused.isError)
        self.assertEqual(
            self._payload(refused)["error"]["code"], "PROJECT_READ_REFUSED"
        )

        expired = parse_config(
            {
                **self.fixtures.payload,
                "lease_expires_at_ms": int(time.time() * 1000) - 1,
            }
        )
        result = self._dispatch("workspace_manifest", config=expired)
        self.assertTrue(result.isError)
        self.assertEqual(
            self._payload(result)["error"]["code"], "PROJECT_READ_REFUSED"
        )

    def test_all_advertised_schema_constraints_are_internal_and_sanitized(self) -> None:
        private = "PRIVATE_REJECTED_SENTINEL"
        oversized = private + "秘密" * (MAX_ARGUMENT_BYTES // 2)
        self.assertGreater(
            len(canonical_json({"relative_path": oversized})), MAX_ARGUMENT_BYTES
        )
        invalid_cases = (
            ("workspace_manifest", {"extra": private}),
            ("read_project_file", {}),
            ("read_project_file", {"relative_path": ""}),
            ("read_project_file", {"relative_path": 1}),
            ("read_project_file", {"relative_path": "r" * 513}),
            ("read_project_file", {"relative_path": "README.md", "line_start": True}),
            ("read_project_file", {"relative_path": "README.md", "line_start": "0"}),
            ("read_project_file", {"relative_path": "README.md", "line_start": -1}),
            ("read_project_file", {"relative_path": "README.md", "line_start": 1_048_577}),
            ("read_project_file", {"relative_path": "README.md", "line_count": 0}),
            ("read_project_file", {"relative_path": "README.md", "line_count": 257}),
            ("read_project_file", {"relative_path": "README.md", "expected_sha256": "A" * 64}),
            ("read_project_file", {"relative_path": "README.md", "expected_sha256": 1}),
            ("read_project_file", {"relative_path": "README.md", "extra": private}),
            ("read_project_file", {"relative_path": oversized}),
            ("preview_text_replace", {"relative_path": "README.md"}),
            (
                "preview_text_replace",
                {
                    "relative_path": 1,
                    "expected_sha256": "a" * 64,
                    "old_text": "x",
                    "new_text": "y",
                },
            ),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": "a" * 64,
                    "old_text": "",
                    "new_text": "x",
                },
            ),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": "a" * 64,
                    "old_text": "x" * (16 * 1024 + 1),
                    "new_text": "",
                },
            ),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": "A" * 64,
                    "old_text": "x",
                    "new_text": "y",
                },
            ),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": "a" * 64,
                    "old_text": 1,
                    "new_text": "y",
                },
            ),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": "a" * 64,
                    "old_text": "x",
                    "new_text": "y" * (16 * 1024 + 1),
                },
            ),
            (
                "preview_text_replace",
                {
                    "relative_path": "README.md",
                    "expected_sha256": "a" * 64,
                    "old_text": "x",
                    "new_text": "y",
                    "extra": private,
                },
            ),
            ("preview_project_command", {}),
            ("preview_project_command", {"recipe": "shell"}),
            ("preview_project_command", {"recipe": 1}),
            ("preview_project_command", {"recipe": "pytest_targets", "targets": "tests/a.py"}),
            (
                "preview_project_command",
                {"recipe": "pytest_targets", "targets": ["tests/a.py"] * 17},
            ),
            (
                "preview_project_command",
                {"recipe": "pytest_targets", "targets": [""]},
            ),
            (
                "preview_project_command",
                {"recipe": "pytest_targets", "targets": [1]},
            ),
            (
                "preview_project_command",
                {"recipe": "pytest_targets", "targets": ["t" * 513]},
            ),
            ("preview_project_command", {"recipe": "git_diff_check", "extra": private}),
        )
        for name, arguments in invalid_cases:
            with self.subTest(name=name, arguments=list(arguments)):
                result = self._dispatch(name, arguments)
                text = result.content[0].text
                self.assertTrue(result.isError)
                self.assertEqual(self._payload(result)["error"]["code"], "INVALID_REQUEST")
                self.assertNotIn(private, text)
                self.assertNotIn("validation", text.lower())
                self.assertNotIn("additionalProperties", text)
                self.assertLessEqual(len(text.encode("utf-8")), MAX_RESULT_BYTES)

    def test_executor_is_retained_by_server_owner(self) -> None:
        from integrations.workbench_local_mcp.server import build_server

        async def scenario() -> None:
            gateway = LocalWorkbenchGateway.open(self.fixtures.config)
            executor = BoundedSyncExecutor(max_concurrency=2)
            try:
                server = build_server(gateway, executor)
                self.assertIs(server._workbench_executor, executor)
            finally:
                await executor.aclose(timeout=1.0)
                gateway.close()

        asyncio.run(scenario())

    def test_default_executor_has_exact_two_call_capacity(self) -> None:
        from integrations.workbench_local_mcp.server import build_server

        async def scenario() -> None:
            gateway = LocalWorkbenchGateway.open(self.fixtures.config)
            server = build_server(gateway)
            executor = server._workbench_executor
            try:
                self.assertEqual(executor.max_concurrency, 2)
            finally:
                await executor.aclose(timeout=1.0)
                gateway.close()

        asyncio.run(scenario())

    def test_injected_executor_cannot_widen_two_call_capacity(self) -> None:
        from integrations.workbench_local_mcp.server import build_server

        gateway = LocalWorkbenchGateway.open(self.fixtures.config)
        try:
            with self.assertRaisesRegex(ValueError, "must not exceed two calls"):
                build_server(gateway, BoundedSyncExecutor(max_concurrency=3))
        finally:
            gateway.close()

    def test_run_stdio_closes_gateway_when_server_construction_fails(self) -> None:
        from integrations.workbench_local_mcp import server as local_server

        gateway = LocalWorkbenchGateway.open(self.fixtures.config)
        descriptor = gateway._project.fd
        with mock.patch.object(
            local_server,
            "build_server",
            side_effect=RuntimeError("controlled server construction failure"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "controlled server construction failure"
            ):
                asyncio.run(local_server.run_stdio(gateway))
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_run_stdio_drains_executor_when_options_construction_fails(self) -> None:
        from integrations.workbench_local_mcp import server as local_server

        gateway = LocalWorkbenchGateway.open(self.fixtures.config)
        descriptor = gateway._project.fd
        built: list[Any] = []
        original_build = local_server.build_server

        def capture_server(*args: Any, **kwargs: Any):
            server = original_build(*args, **kwargs)
            built.append(server)
            return server

        async def scenario() -> None:
            with (
                mock.patch.object(local_server, "build_server", side_effect=capture_server),
                mock.patch.object(
                    local_server,
                    "initialization_options",
                    side_effect=RuntimeError("controlled options failure"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "controlled options failure"):
                    await local_server.run_stdio(gateway)
            executor = built[0]._workbench_executor
            with self.assertRaises(SyncExecutorClosed):
                await executor.run(lambda: None, timeout=1.0)

        asyncio.run(scenario())
        self.assertEqual(len(built), 1)
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_run_stdio_cleanup_uncertainty_supersedes_construction_failure(self) -> None:
        from integrations.workbench_local_mcp import server as local_server

        gateway = LocalWorkbenchGateway.open(self.fixtures.config)
        original_close = gateway.close

        def uncertain_close() -> None:
            raise LocalProfileError("PROJECT_CLEANUP_UNCERTAIN")

        gateway.close = uncertain_close  # type: ignore[method-assign]
        try:
            with mock.patch.object(
                local_server,
                "build_server",
                side_effect=RuntimeError("controlled server construction failure"),
            ):
                with self.assertRaises(LocalProfileError) as caught:
                    asyncio.run(local_server.run_stdio(gateway))
            self.assertEqual(caught.exception.code, "PROJECT_CLEANUP_UNCERTAIN")
        finally:
            gateway.close = original_close  # type: ignore[method-assign]
            gateway.close()

    def test_native_launcher_refuses_private_malformed_frame_and_recovers(self) -> None:
        from tests.test_mcp_stdio_boundary import SENTINEL, child, initialize

        config_path = Path(self.fixtures._tmp.name) / "native-profile.json"
        config_path.write_text(json.dumps(self.fixtures.payload), encoding="utf-8")
        launcher = (
            Path(__file__).resolve().parents[2]
            / "scripts"
            / "mastermind_workbench_local_mcp.py"
        )
        with child(
            [sys.executable, str(launcher), "--config", str(config_path)]
        ) as process:
            initialize(process)
            process.send(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": [SENTINEL]},
                }
            )
            self.assertEqual(
                process.receive(),
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32600,
                        "message": "WORKBENCH_MCP_INVALID_REQUEST",
                    },
                },
            )
            process.send(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "workspace_manifest", "arguments": {}},
                }
            )
            recovered = process.receive()
            self.assertEqual(recovered["id"], 3)
            self.assertFalse(recovered["result"]["isError"])
            process.assert_exit()
            self.assertNotIn(SENTINEL.encode(), process.wire + process.stderr())
            self.assertFalse(process.fallback_used)

    def test_physical_timeout_blocks_descriptor_close_until_eventual_drain(self) -> None:
        import mcp.types as mcp_types
        from integrations.workbench_local_mcp.server import (
            _drain_and_close,
            build_server,
        )

        entered = threading.Event()
        release = threading.Event()

        async def scenario() -> None:
            gateway = LocalWorkbenchGateway.open(self.fixtures.config)
            executor = BoundedSyncExecutor(max_concurrency=1)
            original_call = gateway.call

            def blocked_call(name: str, arguments: object) -> dict[str, Any]:
                entered.set()
                if not release.wait(2.0):
                    raise AssertionError("controlled physical operation was not released")
                return original_call(name, arguments)

            gateway.call = blocked_call  # type: ignore[method-assign]
            server = build_server(gateway, executor, call_timeout_seconds=0.2)
            handler = server.request_handlers[mcp_types.CallToolRequest]
            try:
                pending = asyncio.create_task(
                    handler(self._request("workspace_manifest"))
                )
                deadline = asyncio.get_running_loop().time() + 1.0
                while not entered.is_set() and asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.005)
                self.assertTrue(entered.is_set())
                server_result = await pending
                result = server_result.root
                self.assertTrue(result.isError)
                self.assertEqual(self._payload(result)["error"]["code"], "INTERNAL_ERROR")
                self.assertTrue(entered.is_set())
                self.assertEqual(len(executor.attempts_snapshot()), 1)
                with self.assertRaises(SyncExecutorCloseTimeout):
                    await _drain_and_close(
                        gateway, executor, drain_timeout_seconds=0.03
                    )
                gateway._scope()
            finally:
                release.set()
                await _drain_and_close(
                    gateway, executor, drain_timeout_seconds=1.0
                )
            with self.assertRaises(LocalProfileError):
                gateway._scope()

        asyncio.run(scenario())

    def test_caller_cancellation_keeps_physical_operation_owned_until_drain(self) -> None:
        import mcp.types as mcp_types
        from integrations.workbench_local_mcp.server import _drain_and_close, build_server

        entered = threading.Event()
        release = threading.Event()

        async def scenario() -> None:
            gateway = LocalWorkbenchGateway.open(self.fixtures.config)
            executor = BoundedSyncExecutor(max_concurrency=1)
            original_call = gateway.call

            def blocked_call(name: str, arguments: object) -> dict[str, Any]:
                entered.set()
                if not release.wait(2.0):
                    raise AssertionError("controlled physical operation was not released")
                return original_call(name, arguments)

            gateway.call = blocked_call  # type: ignore[method-assign]
            server = build_server(gateway, executor, call_timeout_seconds=1.0)
            handler = server.request_handlers[mcp_types.CallToolRequest]
            pending = asyncio.create_task(handler(self._request("workspace_manifest")))
            try:
                deadline = asyncio.get_running_loop().time() + 1.0
                while not entered.is_set() and asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.005)
                self.assertTrue(entered.is_set())
                pending.cancel()
                outcome = await asyncio.gather(pending, return_exceptions=True)
                self.assertIsInstance(outcome[0], asyncio.CancelledError)
                self.assertEqual(len(executor.attempts_snapshot()), 1)
                with self.assertRaises(SyncExecutorCloseTimeout):
                    await _drain_and_close(
                        gateway, executor, drain_timeout_seconds=0.03
                    )
                gateway._scope()
            finally:
                release.set()
                await _drain_and_close(
                    gateway, executor, drain_timeout_seconds=1.0
                )

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
