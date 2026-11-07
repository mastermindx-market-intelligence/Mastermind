"""Retained native ACP connection over one original full-application process.

The caller's existing OHF generation owns this object. The maintained SDK owns
JSON-RPC; stdout remains native application output. No retry, account selection,
Job/Attempt admission, session registry or alternate broad Stop is implemented.
"""
from __future__ import annotations
import asyncio
import dataclasses
import hashlib
import math
from importlib.metadata import version
from pathlib import Path
import socket
from typing import Any, Callable, Mapping, Sequence

from control_plane.worker_execution_contract import BinaryAttestation, ProcessInspector
from integrations.acp_worker.process_resource import NativeProcessResource, NativeProcessSettlement
from integrations.acp_worker.turn import AcpProfile, _model_option
from integrations.deepseek_harness.native_protocol import (
    EXTENSION_V2, OBSERVATION_REQUEST_SCHEMA, NativeClaim, NativeProtocolError, NativeResult,
    document, integer, native_extension, native_id, native_observation,
    request_id as checked_request_id,
)
from scripts.ohf.acp_probe_boundary import BoundaryViolation, ProbeClient, ProbeLimits, StrictFrameReader


class NativeEffectUnknown(RuntimeError):
    """The original native request remains owned; never replay it on timeout."""


@dataclasses.dataclass
class _Prompt:
    operation_id: str
    claim_ready: asyncio.Future[NativeClaim]
    request_id: str | int | None = None
    claim: NativeClaim | None = None
    task: asyncio.Task[NativeResult] | None = None
    result: NativeResult | None = None
    frames: int = 0
    wire_terminal: bool = False
    cancel_task: asyncio.Task[dict[str, Any]] | None = None
    cancel_status: str | None = None


class NativeClient(ProbeClient):
    """Finite native observations; permissions and unrelated extensions deny."""

    def __init__(self, on_update: Callable[[dict[str, Any]], None] | None = None, *,
                 before_send: Callable[[str], None] | None = None,
                 before_write: Callable[[], None] | None = None):
        super().__init__(ProbeLimits(frames=4096, text_bytes=1024*1024, updates=4096))
        self.current: _Prompt | None = None
        self.turns = 0
        self.on_update = on_update
        self.before_send, self.before_write = before_send, before_write
        self.advertised = False

    def begin_native_prompt(self, operation_id: str) -> _Prompt:
        native_id(operation_id)
        if (self.violation or not self.advertised or self.session_id is None or self.turns >= 64
                or (self.current is not None and (self.current.result is None
                    or (self.current.cancel_task is not None and self.current.cancel_status is None)))):
            raise NativeProtocolError("NATIVE_PROMPT_OWNER_NOT_READY")
        self.turns += 1
        self._active = True
        self._updates = self._text_bytes = self._denials = 0
        self.current = _Prompt(operation_id, asyncio.get_running_loop().create_future())
        return self.current

    def admit_frame(self, message: dict[str, Any]) -> None:
        current = self.current
        if current is not None:
            if current.wire_terminal:
                if message.get("method") in {"session/update", "session/request_permission", "_mastermind/native_claim"}:
                    self.poison("NATIVE_CALLBACK_AFTER_TERMINAL")
                    raise BoundaryViolation(self.violation)
                # Ordinary observation/close responses belong to their own SDK
                # requests. StrictFrameReader still enforces the global budget.
                return
            current.frames += 1
            if current.frames > 512:
                self.poison("NATIVE_TURN_FRAME_BUDGET_EXCEEDED")
                raise BoundaryViolation(self.violation)

    def _matching_claim(self, value: Any) -> NativeClaim:
        claim = NativeClaim.parse(value)
        current = self.current
        if (not self.advertised or not self._active or current is None
                or claim.session_id != self.session_id or claim.operation_id != current.operation_id
                or type(claim.request_id) is not type(current.request_id)
                or claim.request_id != current.request_id
                or (current.claim is not None and current.claim != claim)):
            raise NativeProtocolError("NATIVE_CLAIM_OWNER_MISMATCH")
        return claim

    def admit_extension_frame(self, message: dict[str, Any]) -> bool:
        if set(message) != {"jsonrpc", "method", "params"} or message["method"] != "_mastermind/native_claim":
            return False
        self._matching_claim(message["params"])
        return True

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        if method != "mastermind/native_claim":
            self.poison("NATIVE_EXTENSION_NOT_ADMITTED")
            raise NativeProtocolError(self.violation)
        try:
            claim = self._matching_claim(params)
        except ValueError:
            self.poison("NATIVE_CLAIM_OWNER_MISMATCH")
            raise
        current = self.current
        if current.claim is not None:
            self.poison("NATIVE_DUPLICATE_CLAIM")
            raise NativeProtocolError(self.violation)
        current.claim = claim
        current.claim_ready.set_result(claim)

    def bind_outgoing(self, message: dict[str, Any]) -> None:
        if message.get("method") != "session/prompt":
            return
        current, params = self.current, message.get("params")
        if (current is None or not self._active or not self.advertised or current.request_id is not None
                or type(params) is not dict or set(params) != {"sessionId", "prompt", "_meta"}
                or params["sessionId"] != self.session_id
                or params["_meta"] != {"mastermindNative": {"operationId": current.operation_id}}):
            self.poison("NATIVE_PROMPT_REPLAY_OR_OWNER_MISMATCH")
            raise NativeProtocolError(self.violation)
        current.request_id = checked_request_id(message.get("id"))

    def observe_wire(self, event: Any) -> None:
        current, message = self.current, event.message
        if current is None:
            return
        if (event.direction == "incoming" and "method" not in message
                and type(message.get("id")) is type(current.request_id)
                and message.get("id") == current.request_id):
            current.wire_terminal = True

    def admit_update(self, update: Any) -> int:
        data = document(update)
        kind = data.get("sessionUpdate")
        if kind in {"agent_message_chunk", "agent_thought_chunk", "user_message_chunk"}:
            if not {"sessionUpdate", "content"} <= set(data) or set(data) - {"sessionUpdate", "content", "messageId"}:
                raise BoundaryViolation("UPDATE_NOT_ADMITTED")
            content = data["content"]
            if type(content) is not dict or set(content) != {"type", "text"} or content["type"] != "text" or not isinstance(content["text"], str):
                raise BoundaryViolation("UPDATE_NOT_ADMITTED")
            if "messageId" in data:
                native_id(data["messageId"])
            return len(content["text"].encode("utf-8"))
        if kind == "usage_update" and set(data) == {"sessionUpdate", "used", "size"}:
            integer(data["used"])
            integer(data["size"])
            return 0
        raise BoundaryViolation("UPDATE_NOT_ADMITTED")

    def commit_update(self, update: Any) -> None:
        # NativeResult hashes native terminal facts. Session remains body owner.
        pass

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        before = self._updates
        await super().session_update(session_id, update, **kwargs)
        if self._updates != before and self.on_update is not None:
            data = document(update)
            content = data.get("content", {})
            text = content.get("text", "")
            # Original Session owns text/history. OHF gets bounded progress facts.
            self.on_update({"kind": data["sessionUpdate"], "message_id": data.get("messageId"),
                            "text_bytes": len(text.encode()), "text_sha256": hashlib.sha256(text.encode()).hexdigest()})


class NativeTransport:
    """Bind the SDK's generated ID before send can yield; no framing or ID minting."""

    def __init__(self, transport: Any, client: NativeClient):
        self.transport, self.client = transport, client

    async def send(self, message: dict[str, Any]) -> None:
        self.client.bind_outgoing(message)
        if self.client.before_send is not None:
            self.client.before_send(message.get("method", ""))
        await self.transport.send(message)

    async def receive(self) -> dict[str, Any] | None:
        return await self.transport.receive()

    async def close(self) -> None:
        await self.transport.close()


class NativeWriteGuard:
    """Recheck the retained owner at the SDK sender's actual synchronous write.

    MessageSender owns its existing queue and payloads. No bytes are parsed here.
    The callback must cover all queued writes; there is no cleanup bypass.
    """
    def __init__(self, writer: Any, require_current: Callable[[], None]):
        self.writer, self.require_current = writer, require_current

    def write(self, data: bytes) -> None:
        outcome = self.require_current()
        if outcome is not None:
            if asyncio.iscoroutine(outcome):
                outcome.close()
            raise NativeProtocolError("NATIVE_WRITE_GUARD_MUST_BE_SYNCHRONOUS")
        self.writer.write(data)  # no await between currentness and physical write

    def __getattr__(self, name):
        return getattr(self.writer, name)


@dataclasses.dataclass(frozen=True)
class NativeConnectionSettlement:
    physical: NativeProcessSettlement
    protocol_settled: bool


class NativeAcpProcess:
    """A caller-owned generation; all methods run on its original event loop."""

    def __init__(self, client: NativeClient):
        self.client = client
        self.resource: NativeProcessResource | None = None
        self.connection = self.writer = self.sender_tasks = None
        self.provider_session_id: str | None = None
        self.initialization: dict[str, Any] | None = None
        self.native_extension: dict[str, str] | None = None
        self.session_options: dict[str, Any] | None = None
        self._tasks: set[asyncio.Task] = set()
        self._closing: asyncio.Task[NativeConnectionSettlement] | None = None
        self._close_reason: str | None = None

    def _own(self, awaitable) -> asyncio.Task:
        task = asyncio.create_task(awaitable)
        self._tasks.add(task)
        def settled(done):
            if not done.cancelled():
                done.exception()
            self._tasks.discard(done)
        task.add_done_callback(settled)
        return task

    async def _bounded(self, awaitable, seconds: float):
        task = self._own(awaitable)
        done, _ = await asyncio.wait({task}, timeout=seconds)
        if not done:
            raise NativeEffectUnknown("NATIVE_RPC_OUTCOME_UNOBSERVED")
        return task.result()

    async def open(
        self, *, binary: BinaryAttestation, argv: Sequence[str], environment: Mapping[str, str],
        cwd: Path, capture_directory: Path, protocol_profile: AcpProfile, model: str,
        provider_session_id: str | None = None, inspector: ProcessInspector | None = None,
    ) -> None:
        if self.resource is not None or self.connection is not None or self._closing is not None:
            raise NativeProtocolError("NATIVE_GENERATION_ALREADY_OPENED")
        if version("agent-client-protocol") != "0.12.1" or protocol_profile.auth_method is not None:
            raise NativeProtocolError("NATIVE_SDK_PROFILE_REFUSED")
        if "MMX_NATIVE_COMPANY_FD" in environment:
            raise NativeProtocolError("NATIVE_DESCRIPTOR_OWNER_REFUSED")
        if provider_session_id is not None:
            native_id(provider_session_id)
        from acp import PROTOCOL_VERSION, connect_to_agent
        from acp.schema import ClientCapabilities, Implementation
        from acp._transport import NdjsonTransport
        from acp.task import MessageSender, TaskSupervisor
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        parent.setblocking(False)
        env = dict(environment, MMX_NATIVE_COMPANY_FD=str(child.fileno()))
        try:
            self.resource = await NativeProcessResource.open(
                binary=binary, argv=argv, environment=env, cwd=cwd,
                stdout_path=capture_directory/"native-app.stdout", stderr_path=capture_directory/"native-app.stderr",
                stdout_limit_bytes=4*1024*1024, stderr_limit_bytes=4*1024*1024,
                settle_seconds=30, stdout_is_protocol=False, pass_fds=(child.fileno(),), inspector=inspector,
            )
            child.close()
            reader, self.writer = await asyncio.open_connection(sock=parent, limit=64*1024)
            self.sender_tasks = TaskSupervisor(source="mastermind-native-acp")
            transport = NdjsonTransport(
                StrictFrameReader(reader, self.client, extension_policy=self.client),
                MessageSender(NativeWriteGuard(self.writer, self.client.before_write)
                              if self.client.before_write is not None else self.writer,
                              self.sender_tasks), receive_timeout=None,
            )
            self.connection = connect_to_agent(self.client, NativeTransport(transport, self.client),
                                               observers=[self.client.observe_wire])
            initialized = document(await self._bounded(self.connection.initialize(
                protocol_version=PROTOCOL_VERSION, client_capabilities=ClientCapabilities(),
                client_info=Implementation(name="mastermind-native-owner", version="1")), 60))
            info = initialized.get("agentInfo", {})
            if (initialized.get("protocolVersion") != PROTOCOL_VERSION
                    or info.get("name") != protocol_profile.agent_name or info.get("version") != protocol_profile.agent_version):
                raise NativeProtocolError("NATIVE_INITIALIZATION_MISMATCH")
            self.native_extension = native_extension(initialized.get("_meta", {}).get("mastermindNative"))
            self.initialization = initialized
            self.client.advertised = True
            if provider_session_id is None:
                selected = document(await self._bounded(self.connection.new_session(cwd=str(cwd), mcp_servers=[]), 30))
                self.provider_session_id = native_id(selected.get("sessionId"))
            else:
                selected = document(await self._bounded(self.connection.resume_session(
                    session_id=provider_session_id, cwd=str(cwd), mcp_servers=[]), 30))
                self.provider_session_id = provider_session_id
            self.client.bind_session(self.provider_session_id)
            option = _model_option(selected.get("configOptions"), protocol_profile.model_option_id)
            if option.get("currentValue") != protocol_profile.model_option_value(model):
                raise NativeProtocolError("NATIVE_MODEL_SELECTION_MISMATCH")
            self.session_options = selected
        except BaseException:
            if self.resource is not None:
                await self.close("startup failed")
            raise
        finally:
            child.close()
            if self.writer is None:
                parent.close()


    async def observe(self, *, timeout_seconds: float = 30):
        """Read facts from the same retained connection; no prompt or new owner."""
        connection, session_id = self.connection, self.provider_session_id
        def require_current():
            if (connection is None or session_id is None or self.connection is not connection
                    or self.provider_session_id != session_id or self.client.session_id != session_id
                    or self._closing is not None or self.client.violation
                    or self.native_extension != EXTENSION_V2):
                raise NativeProtocolError("NATIVE_OBSERVATION_OWNER_UNAVAILABLE")
        require_current()  # a v1 peer is refused before any extension request
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 60):
            raise NativeProtocolError("NATIVE_OBSERVATION_BOUND_REFUSED")
        value = await self._bounded(connection.ext_method("mastermind/native_observe", {
            "schema": OBSERVATION_REQUEST_SCHEMA, "sessionId": session_id,
        }), timeout_seconds)
        observed = native_observation(value, session_id)
        require_current()
        return observed

    async def begin_prompt(self, operation_id: str, text: str, *, timeout_seconds: float = 30) -> NativeClaim:
        if self._closing is not None or self.connection is None or not isinstance(text, str) or not 0 < len(text.encode()) <= 128*1024:
            raise NativeProtocolError("NATIVE_PROMPT_REFUSED")
        from acp.schema import TextContentBlock
        current = self.client.begin_native_prompt(operation_id)
        async def run():
            response = await self.connection.prompt(session_id=self.provider_session_id,
                prompt=[TextContentBlock(type="text", text=text)], mastermindNative={"operationId": operation_id})
            result = NativeResult.parse(response)
            if (self.client.violation or result.terminal.operation_id != current.operation_id
                    or type(result.terminal.request_id) is not type(current.request_id)
                    or result.terminal.request_id != current.request_id
                    or result.terminal.claim != current.claim):
                raise NativeProtocolError("NATIVE_TERMINAL_OWNER_MISMATCH")
            current.result = result
            self.client.seal()
            return result
        current.task = self._own(run())
        done, _ = await asyncio.wait({current.claim_ready, current.task}, timeout=timeout_seconds,
                                     return_when=asyncio.FIRST_COMPLETED)
        if current.claim_ready in done:
            if self.client.violation:
                raise NativeProtocolError(self.client.violation)
            return current.claim_ready.result()
        if current.task in done:
            current.task.result()
            raise NativeProtocolError("NATIVE_PROMPT_NOT_CLAIMED")
        raise NativeEffectUnknown("NATIVE_CLAIM_UNOBSERVED")

    async def result(self, claim: NativeClaim, *, timeout_seconds: float = 30) -> NativeResult:
        current = self.client.current
        if current is None or current.claim != claim or current.task is None:
            raise NativeProtocolError("NATIVE_RESULT_OWNER_MISMATCH")
        done, _ = await asyncio.wait({current.task}, timeout=timeout_seconds)
        if not done:
            raise NativeEffectUnknown("NATIVE_TERMINAL_UNOBSERVED")
        return current.task.result()

    async def interrupt(self, claim: NativeClaim, *, timeout_seconds: float = 10) -> str:
        current = self.client.current
        if self._closing is not None or current is None or current.claim != claim or self.connection is None:
            raise NativeProtocolError("NATIVE_STOP_OWNER_MISMATCH")
        if current.cancel_task is None:
            current.cancel_task = self._own(self.connection.ext_method("mastermind/native_cancel", claim.to_wire()))
        done, _ = await asyncio.wait({current.cancel_task}, timeout=timeout_seconds)
        if not done:
            raise NativeEffectUnknown("NATIVE_STOP_OUTCOME_UNOBSERVED")
        response = current.cancel_task.result()
        if type(response) is not dict or set(response) != {"status"} or response["status"] not in {
                "requested", "already_requested", "not_current", "native_turn_closed_or_superseded"}:
            raise NativeProtocolError("NATIVE_STOP_RESPONSE_REFUSED")
        current.cancel_status = response["status"]
        return current.cancel_status

    async def close(self, reason: str | None = None) -> NativeConnectionSettlement:
        if self.resource is None:
            raise NativeProtocolError("NATIVE_PHYSICAL_RESOURCE_UNOBSERVED")
        if self._closing is None:
            self._close_reason = reason
            self._closing = asyncio.create_task(self._close_once(reason))
        elif self._close_reason != reason:
            raise NativeProtocolError("NATIVE_CLOSE_ALREADY_BOUND")
        return await asyncio.shield(self._closing)

    async def _close_once(self, reason: str | None) -> NativeConnectionSettlement:
        protocol_settled = True
        try:
            if self.connection is not None and self.provider_session_id is not None:
                await self._bounded(self.connection.close_session(session_id=self.provider_session_id), 20)
        except Exception:
            protocol_settled = False
        finally:
            self.client.seal()
            for operation in (
                self.connection.close if self.connection is not None else None,
                self.sender_tasks.shutdown if self.sender_tasks is not None else None,
            ):
                if operation is not None:
                    try:
                        await self._bounded(operation(), 5)
                    except Exception:
                        protocol_settled = False
            if self.writer is not None:
                self.writer.close()
                try:
                    await self._bounded(self.writer.wait_closed(), 5)
                except Exception:
                    protocol_settled = False
        physical = await self.resource.finish(reason)
        if self._tasks:
            done, pending = await asyncio.wait(self._tasks, timeout=1)
            protocol_settled = protocol_settled and not pending
        return NativeConnectionSettlement(physical, protocol_settled)
