"""Compose the existing native T3 CLI with the Capacity-only session client.

The caller supplies an independently authorized, bounded process runner. This
module starts no process, loads no credential and owns no retry, queue or server.
Each invocation keeps the CLI's existing native EnvironmentAuth lifecycle.
"""
from __future__ import annotations

import inspect
import json
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from .t3_native_client import MAX_BYTES, Scope, T3NativeClient, Unavailable
from .t3_web_client import CliInvocation, CliResult

MAX_CATALOG_BYTES = 2 * 1024 * 1024
NATIVE_TOOLS = frozenset({
    "t3_environment_read", "orchestrator_capabilities", "t3_project_list",
    "t3_thread_list", "t3_thread_read", "t3_thread_launch", "t3_thread_send",
    "t3_thread_wait", "t3_thread_interrupt", "t3_thread_configure",
    "t3_thread_organize", "t3_queue", "t3_pending_request", "t3_thread_lifecycle",
})


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate native JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise ValueError("Non-finite native JSON")


def _encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def _decode(text: Any, limit: int) -> dict[str, Any]:
    if type(text) is not str or not 0 < len(text.encode("utf-8")) <= limit:
        raise ValueError("Native output exceeds its bounded contract")
    value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    if type(value) is not dict:
        raise ValueError("Native JSON object required")
    return value


class NativeCliFailure(Unavailable):
    """The original invocation is retained; diagnostics/prompts are not printed.

    A failed modifying invocation is NOT a pre-effect rejection. The existing
    T3NativeClient converts this failure into its original EffectUnknown fence.
    The runner remains responsible for retaining its own process/operation handle.
    """
    def __init__(self, invocation: CliInvocation, *, attempted: bool) -> None:
        self.invocation = invocation
        self.attempted = attempted
        super().__init__("Native CLI observation unavailable; reconcile the original invocation.")


class T3NativeCliTransport:
    """One explicitly selected native CLI, not a shell or an execution grant.

    command is either the absolute installed t3 executable, or the absolute node
    executable followed by the absolute qualified native bin.ts/bin.mjs. No
    caller-supplied shell/options, alternate data directory, auth or provider
    configuration are accepted. The injected runner owns process limits and
    original-handle recovery; there is exactly one call and no retry here.
    """
    def __init__(self, command: tuple[str, ...], runner: Callable[[CliInvocation], Any]):
        if (type(command) is not tuple or len(command) not in (1, 2)
                or not callable(runner)):
            raise ValueError("An exact native CLI command and authorized runner are required")
        for part in command:
            if (type(part) is not str or not PurePosixPath(part).is_absolute()
                    or not 1 <= len(part.encode("utf-8")) <= 4096
                    or any(ord(c) < 32 or ord(c) == 127 for c in part)
                    or ".." in PurePosixPath(part).parts):
                raise ValueError("Absolute native executable/script paths are required")
        if len(command) == 2 and PurePosixPath(command[1]).name not in {"bin.ts", "bin.mjs"}:
            raise ValueError("Only the qualified native CLI entrypoint is supported")
        self.command, self.runner = command, runner
        self._schemas: dict[str, dict[str, Any]] | None = None
        self._environment_id: str | None = None

    async def _invoke(self, suffix: tuple[str, ...], *, stdin: str | None,
                      limit: int) -> dict[str, Any]:
        guard = () if self._environment_id is None else ("--expected-environment-id", self._environment_id)
        invocation = CliInvocation((*self.command, "--log-level", "error", "thread", *suffix, *guard), stdin)
        try:
            response = self.runner(invocation)
            if inspect.isawaitable(response):
                response = await response
            if type(response) is not CliResult or type(response.returncode) is not int or response.returncode != 0:
                raise ValueError("Native CLI did not return a qualified result")
            return _decode(response.stdout, limit)
        except Exception:
            # Cancellation is a BaseException and must reach the existing native
            # client's modifying-effect guard, never become a hidden retry.
            raise NativeCliFailure(invocation, attempted=True) from None

    async def discover(self) -> dict[str, dict[str, Any]]:
        """Read the original allowlisted catalog; no inferred or cached tools.

        A failed refresh clears the transport's capability snapshot. It cannot
        turn a previously advertised tool into permission for a new invocation.
        """
        self._schemas = None
        catalog = await self._invoke(("native-catalog", "--json"), stdin=None,
                                     limit=MAX_CATALOG_BYTES)
        try:
            tools = catalog["tools"]
            if type(tools) is not list or not 1 <= len(tools) <= len(NATIVE_TOOLS):
                raise ValueError("Bounded native tools required")
            schemas: dict[str, dict[str, Any]] = {}
            for tool in tools:
                if type(tool) is not dict or tool.get("name") not in NATIVE_TOOLS:
                    raise ValueError("Unexpected native tool")
                name, schema = tool["name"], tool.get("inputSchema")
                if (name in schemas or type(schema) is not dict
                        or schema.get("type") != "object" or type(schema.get("properties")) is not dict):
                    raise ValueError("Malformed or duplicated native schema")
                required = schema.get("required", [])
                if (type(required) is not list or any(type(k) is not str for k in required)
                        or len(set(required)) != len(required)
                        or not set(required) <= schema["properties"].keys()):
                    raise ValueError("Malformed native required inputs")
                schemas[name] = schema
            if "t3_environment_read" not in schemas:
                raise ValueError("Native environment discovery is unavailable")
            self._schemas = json.loads(_encoded(schemas))
            return json.loads(_encoded(schemas))
        except (KeyError, TypeError, ValueError, RecursionError, UnicodeError):
            raise Unavailable("Native catalog is not qualified") from None

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Forward one discovered native request and preserve the MCP envelope."""
        if (type(name) is not str or self._environment_id is None
                or self._schemas is None or name not in self._schemas):
            raise Unavailable("Native tool has not been discovered")
        if type(arguments) is not dict:
            raise ValueError("Native argument object required")
        schema = self._schemas[name]
        if (not arguments.keys() <= schema["properties"].keys()
                or not set(schema.get("required", [])) <= arguments.keys()):
            raise Unavailable("Native arguments do not match the installed schema")
        selection = arguments.get("modelSelection")
        if name in {"t3_thread_launch", "t3_thread_configure", "t3_thread_lifecycle"}:
            selecting = name == "t3_thread_launch" or selection is not None or arguments.get("action") == "set_model"
            if selecting and (type(selection) is not dict or selection.get("instanceId") != "capacity_fabric"):
                raise ValueError("Only explicit Capacity Fabric model selection is supported")
        try:
            payload = _encoded(arguments)
            if len(payload.encode("utf-8")) > MAX_BYTES:
                raise ValueError("Native input exceeds the bounded contract")
        except (TypeError, ValueError, RecursionError, UnicodeError):
            raise ValueError("Native arguments are not a bounded JSON object") from None
        return await self._invoke(("native", name, "--json"), stdin=payload, limit=MAX_BYTES)

    async def connect(self, scope: Scope) -> T3NativeClient:
        """Bind the existing client only after an actual native environment read."""
        if type(scope) is not Scope:
            raise ValueError("An exact observed native scope is required")
        if self._environment_id is not None and self._environment_id != scope.environment_id:
            raise Unavailable("An existing native transport cannot be retargeted")
        self._environment_id = scope.environment_id
        try:
            schemas = await self.discover()
            observed = await self.call_tool("t3_environment_read", {})
            body, error = observed.get("structuredContent"), observed.get("isError")
            if ((error is not None and error is not False) or type(body) is not dict
                    or body.get("environmentId") != scope.environment_id):
                raise Unavailable("Native CLI environment does not match the original scope")
            return T3NativeClient(scope, self.call_tool, schemas)
        except BaseException:
            self._schemas = None
            raise
