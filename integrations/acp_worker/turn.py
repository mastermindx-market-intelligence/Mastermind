"""One read-only ACP turn over an existing owner's exclusive stdio streams.

The maintained ACP SDK owns JSON-RPC. Executive OS still owns admission, process
launch/attestation, realm isolation, replay, validation, cleanup and acceptance.
This module neither starts a process nor registers/enables a worker. A returned
candidate is NOT a CollectionReceipt and must pass the existing result consumer.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from importlib.metadata import version
from types import MappingProxyType
from typing import Any

from control_plane.worker_execution_contract import WorkerLaunchSpec

SDK_VERSION = "0.12.1"
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+\-]{0,127}\Z")
_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}\Z")
_MAX_PROMPT = 128 * 1024
_MAX_OUTPUT = 1024 * 1024
_MAX_UPDATES = 4096


@dataclasses.dataclass(frozen=True)
class AcpProfile:
    """Reviewed protocol expectations, never credential or launch authority."""
    agent_name: str
    agent_version: str
    model_option_id: str = "model"
    auth_method: str | None = None
    required_mode: str | None = None
    # Concrete ACP servers may use an opaque provider+model selector while
    # WorkerLaunchSpec.model remains the provider-neutral requested model id.
    model_option_provider: str | None = None

    def __post_init__(self) -> None:
        for value in dataclasses.astuple(self):
            if value is not None and not _TOKEN.fullmatch(value):
                raise ValueError("invalid ACP profile identifier")
        # No interactive enrollment or environment-token injection in this port.
        if self.auth_method not in (None, "cached_token"):
            raise ValueError("ACP authentication method is not admitted")

    def model_option_value(self, model: str) -> str:
        """Render the reviewed server-private selector for one requested model."""
        if not _TOKEN.fullmatch(model):
            raise ValueError("invalid ACP model identifier")
        if self.model_option_provider is None:
            return model
        return json.dumps([self.model_option_provider, model], separators=(",", ":"))


@dataclasses.dataclass(frozen=True)
class AcpCandidate:
    run_id: str
    job_id: str
    worker_id: str
    session_id: str | None
    requested_model: str
    observed_model: str | None
    stop_reason: str | None
    output_json: str | None
    output_sha256: str | None
    error: str | None
    effect_unknown: bool
    cancellation_observed: bool
    usage: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))


class _Refused(Exception):
    pass


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate result key")
        result[key] = value
    return result


def _nonfinite(_value: str) -> Any:
    raise ValueError("nonfinite result number")


def _document(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if not isinstance(value, dict):
        raise _Refused("ACP_SCHEMA_DRIFT")
    return value


def _model_option(options: Any, option_id: str) -> dict[str, Any]:
    if not isinstance(options, list):
        raise _Refused("ACP_MODEL_SELECTION_UNAVAILABLE")
    matches = [x for x in options if isinstance(x, dict) and x.get("id") == option_id]
    if len(matches) != 1 or matches[0].get("type") != "select":
        raise _Refused("ACP_MODEL_SELECTION_UNAVAILABLE")
    if matches[0].get("category") != "model":
        raise _Refused("ACP_MODEL_SELECTION_UNAVAILABLE")
    return matches[0]


def _option_values(option: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    rows = option.get("options")
    if not isinstance(rows, list):
        raise _Refused("ACP_MODEL_SELECTION_UNAVAILABLE")
    for row in rows:
        if not isinstance(row, dict):
            raise _Refused("ACP_SCHEMA_DRIFT")
        children = row.get("options", [row])
        if not isinstance(children, list):
            raise _Refused("ACP_SCHEMA_DRIFT")
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get("value"), str):
                raise _Refused("ACP_SCHEMA_DRIFT")
            values.add(child["value"])
    return values


class AcpReadOnlyTurn:
    """Single use. Retains unresolved SDK task handles for its owning caller.

    No process, filesystem, terminal, MCP, elicitation or native helper grant is
    provided by this client. Provider-internal isolation still needs independent
    installed-profile proof; client-side refusal alone is not a sandbox.
    """
    def __init__(self, profile: AcpProfile) -> None:
        self.profile = profile
        self._used = False
        self._session: str | None = None
        self._early_sessions: set[str] = set()
        self._model: str | None = None
        self._model_option_value: str | None = None
        self._phase = "setup"
        self._chunks: list[str] = []
        self._bytes = 0
        self._updates = 0
        self._error: str | None = None
        self._violation = asyncio.Event()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._rpc_uncertain = False
        self.last_candidate: AcpCandidate | None = None

    @property
    def unsettled_tasks(self) -> tuple[asyncio.Task[Any], ...]:
        return tuple(task for task in self._tasks if not task.done())

    def _refuse(self, code: str) -> None:
        self._error = self._error or code
        self._violation.set()

    def _session_matches(self, session_id: str) -> bool:
        if not isinstance(session_id, str) or not _SESSION.fullmatch(session_id):
            self._refuse("ACP_SESSION_MISMATCH")
            return False
        if self._session is None:
            self._early_sessions.add(session_id)
            if len(self._early_sessions) > 1:
                self._refuse("ACP_SESSION_MISMATCH")
                return False
        elif self._session != session_id:
            self._refuse("ACP_SESSION_MISMATCH")
            return False
        return True

    async def request_permission(self, session_id: str, **_: Any) -> Any:
        from acp.schema import DeniedOutcome, RequestPermissionResponse
        self._session_matches(session_id)
        self._refuse("ACP_PERMISSION_REFUSED")
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def _deny(self, *_args: Any, **_kwargs: Any) -> Any:
        from acp import RequestError
        self._refuse("ACP_CLIENT_CAPABILITY_REFUSED")
        raise RequestError.method_not_found("unadvertised-client-capability")

    read_text_file = write_text_file = create_terminal = _deny
    terminal_output = release_terminal = wait_for_terminal_exit = kill_terminal = _deny
    create_elicitation = complete_elicitation = ext_method = ext_notification = _deny

    async def session_update(self, session_id: str, update: Any, **_: Any) -> None:
        if not self._session_matches(session_id):
            return
        self._updates += 1
        if self._updates > _MAX_UPDATES:
            self._refuse("ACP_UPDATE_LIMIT")
            return
        self.validate_update(update)

    def validate_update(self, update: Any, *, commit: bool = True) -> str | None:
        try:
            data = _document(update)
            kind = data.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = data.get("content", {})
                if self._phase != "prompt" or content.get("type") != "text":
                    raise _Refused("ACP_UNEXPECTED_CONTENT")
                text = content.get("text")
                if not isinstance(text, str):
                    raise _Refused("ACP_UNEXPECTED_CONTENT")
                size = len(text.encode("utf-8"))
                if self._bytes + size > _MAX_OUTPUT:
                    raise _Refused("ACP_OUTPUT_LIMIT")
                if commit:
                    self._bytes += size
                    self._chunks.append(text)
            elif kind == "config_option_update":
                option = _model_option(data.get("configOptions"), self.profile.model_option_id)
                if (
                    self._phase == "prompt"
                    and option.get("currentValue") != self._model_option_value
                ):
                    raise _Refused("ACP_MODEL_DRIFT")
            elif kind == "current_mode_update":
                if self.profile.required_mode is None or data.get("currentModeId") != self.profile.required_mode:
                    raise _Refused("ACP_MODE_DRIFT")
            elif kind not in {"user_message_chunk", "agent_thought_chunk",
                              "available_commands_update", "session_info_update", "usage_update"}:
                # Tool calls/plans/compaction are not silently elevated into grants.
                raise _Refused("ACP_UNADMITTED_UPDATE")
            elif kind == "user_message_chunk":
                content = data.get("content", {})
                if (self._phase != "prompt" or content.get("type") != "text"
                        or not isinstance(content.get("text"), str)):
                    raise _Refused("ACP_UNEXPECTED_CONTENT")
            return None
        except (_Refused, UnicodeError, AttributeError) as exc:
            reason = str(exc) if isinstance(exc, _Refused) else "ACP_SCHEMA_DRIFT"
            self._refuse(reason)
            return reason

    def _task(self, awaitable: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(awaitable)
        self._tasks.add(task)
        # Retrieve exceptions even when a deadline expires; the handle is retained.
        task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        return task

    async def _bounded(self, awaitable: Any, deadline: float) -> Any:
        if asyncio.get_running_loop().time() >= deadline:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise _Refused("ACP_RPC_DEADLINE")
        task = self._task(awaitable)
        try:
            done, _ = await asyncio.wait({task}, timeout=max(0.0, deadline - asyncio.get_running_loop().time()))
            if not done:
                self._rpc_uncertain = True
                task.cancel()
                raise _Refused("ACP_RPC_DEADLINE")
            return task.result()
        except BaseException:
            # A lost RPC response never proves the remote operation did not occur.
            self._rpc_uncertain = True
            raise

    @staticmethod
    def validate_spec(spec: WorkerLaunchSpec) -> None:
        """Effect-free checks shared with the common-worker binding."""
        grants = set(spec.authorities) | ({spec.authority} if spec.authority else set())
        if not grants or not grants <= {"READ", "RESEARCH"}:
            raise ValueError("ACP first profile is read-only")
        if not spec.workspace_path.is_absolute() or not _TOKEN.fullmatch(spec.model):
            raise ValueError("invalid ACP workspace/model")
        if len(spec.prompt.encode("utf-8")) > _MAX_PROMPT:
            raise ValueError("ACP prompt exceeds limit")
        if not math.isfinite(spec.timeout_seconds) or not 0 < spec.timeout_seconds <= 3600:
            raise ValueError("invalid ACP timeout")
        if not math.isfinite(spec.cancel_grace_seconds) or not 0 < spec.cancel_grace_seconds <= 30:
            raise ValueError("invalid ACP cancellation grace")
        if version("agent-client-protocol") != SDK_VERSION:
            raise ValueError("ACP SDK version is not qualified")

    async def run(self, spec: WorkerLaunchSpec, writer: asyncio.StreamWriter,
                  reader: asyncio.StreamReader, *, cancelled: asyncio.Event,
                  validate_output: Callable[[dict[str, Any]], None],
                  frame_guard: Any | None = None) -> AcpCandidate:
        """Consume only caller-owned streams; return an unaccepted candidate.

        The caller must fence one actual process/Attempt and call its existing
        cleanup/reconciliation on EVERY outcome, including cancellation and errors.
        """
        if self._used:
            raise ValueError("an ACP turn cannot be replayed")
        self._used = True
        self.validate_spec(spec)
        from acp import PROTOCOL_VERSION, connect_to_agent
        from acp.schema import ClientCapabilities, Implementation, TextContentBlock
        loop = asyncio.get_running_loop()
        deadline = loop.time() + spec.timeout_seconds
        conn = None
        sender_tasks = None
        terminal_observed = False
        prompt_task = None
        stop_reason = None
        output = None
        usage: dict[str, int] = {}
        unknown = False
        cancelled_terminal = False
        propagate_cancel = False
        try:
            if cancelled.is_set():
                raise _Refused("ACP_CANCELLED_BEFORE_START")
            if frame_guard is None:
                conn = connect_to_agent(self, writer, reader)
            else:
                # Reuse the existing ACP framing owner, not a second decoder.
                from scripts.ohf.acp_probe_boundary import ProbeClient, StrictFrameReader
                from acp._transport import NdjsonTransport
                from acp.task import MessageSender, TaskSupervisor
                if not isinstance(frame_guard, ProbeClient):
                    raise _Refused("ACP_FRAME_GUARD_UNQUALIFIED")
                sender_tasks = TaskSupervisor(source="mastermind-acp-worker")
                transport = NdjsonTransport(StrictFrameReader(reader, frame_guard),
                    MessageSender(writer, sender_tasks), receive_timeout=spec.timeout_seconds)
                conn = connect_to_agent(self, transport)
            init = _document(await self._bounded(conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=Implementation(name="mastermind", version="1")), deadline))
            info = init.get("agentInfo", {})
            if init.get("protocolVersion") != PROTOCOL_VERSION or info.get("name") != self.profile.agent_name or info.get("version") != self.profile.agent_version:
                raise _Refused("ACP_AGENT_MISMATCH")
            if self.profile.auth_method is not None:
                methods = init.get("authMethods", [])
                if not any(x.get("id") == self.profile.auth_method for x in methods):
                    raise _Refused("ACP_AUTH_UNAVAILABLE")
                await self._bounded(conn.authenticate(method_id=self.profile.auth_method), deadline)
            session = _document(await self._bounded(conn.new_session(
                cwd=str(spec.workspace_path), mcp_servers=[]), deadline))
            self._session = session.get("sessionId")
            if not self._session_matches(self._session) or self._early_sessions - {self._session}:
                raise _Refused("ACP_SESSION_MISMATCH")
            if frame_guard is not None:
                frame_guard.bind_session(self._session)
            if self.profile.required_mode is not None and session.get("modes", {}).get("currentModeId") != self.profile.required_mode:
                raise _Refused("ACP_MODE_MISMATCH")
            option = _model_option(session.get("configOptions"), self.profile.model_option_id)
            model_option_value = self.profile.model_option_value(spec.model)
            if model_option_value not in _option_values(option):
                raise _Refused("ACP_MODEL_UNAVAILABLE")
            self._model_option_value = model_option_value
            if option.get("currentValue") != model_option_value:
                changed = _document(await self._bounded(conn.set_config_option(
                    session_id=self._session, config_id=self.profile.model_option_id,
                    value=model_option_value), deadline))
                option = _model_option(changed.get("configOptions"), self.profile.model_option_id)
            if option.get("currentValue") != model_option_value:
                raise _Refused("ACP_MODEL_MISMATCH")
            self._model = spec.model
            if self._error or cancelled.is_set():
                raise _Refused(self._error or "ACP_CANCELLED_BEFORE_PROMPT")
            if loop.time() >= deadline:
                raise _Refused("ACP_DEADLINE_BEFORE_PROMPT")
            if frame_guard is not None:
                frame_guard.begin_prompt()
            self._phase = "prompt"
            prompt_task = self._task(conn.prompt(session_id=self._session,
                prompt=[TextContentBlock(type="text", text=spec.prompt)]))
            cancel_wait = self._task(cancelled.wait())
            refusal_wait = self._task(self._violation.wait())
            done, _ = await asyncio.wait({prompt_task, cancel_wait, refusal_wait},
                timeout=max(0.0, deadline - loop.time()), return_when=asyncio.FIRST_COMPLETED)
            cancel_wait.cancel()
            refusal_wait.cancel()
            if prompt_task not in done or cancelled.is_set() or self._error:
                code = self._error or ("ACP_CANCEL_REQUESTED" if cancelled.is_set() else "ACP_TURN_DEADLINE")
                self._refuse(code)
                grace = loop.time() + spec.cancel_grace_seconds
                await self._bounded(conn.cancel(session_id=self._session), grace)
                done, _ = await asyncio.wait({prompt_task}, timeout=max(0.0, grace - loop.time()))
                if not done:
                    unknown = True
                    raise _Refused("ACP_TERMINAL_UNOBSERVED")
            response = _document(prompt_task.result())
            stop_reason = response.get("stopReason")
            terminal_observed = stop_reason in {"end_turn", "cancelled", "refusal", "max_tokens", "max_turn_requests"}
            cancelled_terminal = stop_reason == "cancelled"
            if self._error:
                raise _Refused(self._error)
            if stop_reason != "end_turn":
                raise _Refused("ACP_NON_SUCCESS_TERMINAL")
            if loop.time() > deadline or cancelled.is_set():
                raise _Refused("ACP_LATE_TERMINAL")
            text = "".join(self._chunks)
            value = json.loads(text, object_pairs_hook=_object_pairs, parse_constant=_nonfinite)
            if not isinstance(value, dict):
                raise _Refused("ACP_RESULT_NOT_OBJECT")
            try:
                validate_output(value)
                output = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            except Exception as exc:
                raise _Refused("ACP_RESULT_REJECTED") from exc
            if loop.time() > deadline or cancelled.is_set():
                raise _Refused("ACP_LATE_TERMINAL")
            # Provider usage is observational; absent is unknown, never zero quota.
            for key, value in (response.get("usage") or {}).items():
                if key in {"inputTokens", "outputTokens", "totalTokens", "cachedReadTokens", "cachedWriteTokens"} and type(value) is int and 0 <= value <= 2**63 - 1:
                    usage[key] = value
        except asyncio.CancelledError:
            propagate_cancel = True
            self._refuse("ACP_CALLER_CANCELLED")
            unknown = prompt_task is not None and not terminal_observed
            if conn is not None and self._session is not None and unknown:
                try:
                    grace = loop.time() + spec.cancel_grace_seconds
                    await self._bounded(conn.cancel(session_id=self._session), grace)
                    done, _ = await asyncio.wait({prompt_task}, timeout=max(0.0, grace - loop.time()))
                    if done:
                        stop_reason = _document(prompt_task.result()).get("stopReason")
                        terminal_observed = stop_reason in {"end_turn", "cancelled", "refusal", "max_tokens", "max_turn_requests"}
                        cancelled_terminal = stop_reason == "cancelled"
                        unknown = not terminal_observed
                except (Exception, asyncio.CancelledError):
                    unknown = True
        except _Refused as exc:
            self._refuse(str(exc))
            unknown = unknown or str(exc) in {"ACP_RPC_DEADLINE", "ACP_TERMINAL_UNOBSERVED"}
        except Exception:
            self._refuse("ACP_PROTOCOL_OR_RESULT_ERROR")
            unknown = prompt_task is not None and not terminal_observed
        finally:
            self._phase = "closed"
            if frame_guard is not None:
                frame_guard.seal()
            if conn is not None:
                try:
                    await self._bounded(conn.close(), loop.time() + spec.cancel_grace_seconds)
                except (Exception, asyncio.CancelledError):
                    self._refuse("ACP_CONNECTION_CLOSE_UNCERTAIN")
                    unknown = True
            if sender_tasks is not None:
                try:
                    await self._bounded(sender_tasks.shutdown(), loop.time() + spec.cancel_grace_seconds)
                except (Exception, asyncio.CancelledError):
                    self._refuse("ACP_SENDER_CLOSE_UNCERTAIN")
                    unknown = True
            if frame_guard is not None and frame_guard.violation:
                self._refuse("ACP_FRAME_BOUNDARY_REFUSED")
            if self.unsettled_tasks:
                self._refuse("ACP_TASK_SETTLEMENT_UNCERTAIN")
                unknown = True
            if self._error:
                output = None
        self.last_candidate = AcpCandidate(spec.run_id, spec.job_id, spec.worker_id, self._session,
            spec.model, self._model, stop_reason, output,
            hashlib.sha256(output.encode("utf-8")).hexdigest() if output is not None else None,
            self._error, unknown or self._rpc_uncertain, cancelled_terminal, usage)
        if propagate_cancel:
            raise asyncio.CancelledError
        return self.last_candidate
