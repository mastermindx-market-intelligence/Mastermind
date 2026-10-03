"""Queue one canonical Wake on an existing, host-bound Codex RPC connection.

This is an alternative client for CodexAppServerWakeDispatcher, not a new
transport, connection manager or queue. The trusted host supplies an already
negotiated/authorized connection and a guard that checks current binding,
account/host, target inbound policy and the existing Wake reservation. No client
here opens a socket, starts/resumes a session, selects credentials or activates
itself. The OHF current-writer client remains unchanged.

IMPORTANT: clientUserMessageId is correlation, NOT a vendor idempotency promise.
Only the canonical Wake owner may reserve a first submission. After any uncertain
send, call reconcile_wake, never deliver_wake again. Queue absence can mean the
native owner already consumed/deleted the item, so it is always unresolved here.
Queue evidence proves ACCEPTED, never native delivery, ACK or parent consumption.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import math
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

from control_plane.session_targets import RuntimeBinding
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError, _NUDGE_ID_RE
from integrations.executive_wake.codex_app_server import CODEX_WAKE_INSTRUCTION, CodexWakeDeliveryObservation

RpcCall = Callable[[dict[str, Any]], Awaitable[Mapping[str, Any]]]
BindingGuard = Callable[[RuntimeBinding, str, tuple[str, ...]], bool | Awaitable[bool]]
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_MAX_RESPONSE_BYTES = 65536
_MAX_OPAQUE_IDS = 64


def _token(value: Any, limit: int = 256) -> bool:
    return (type(value) is str and 0 < len(value) <= limit
            and all(32 <= ord(c) < 127 for c in value))


class CodexQueuedWakeClient:
    """Single-submit/read-only-reconcile implementation of the existing seam.

    rpc accepts an exact JSON-RPC request and returns the correlated raw reply;
    its existing host must bound wire bytes before decoding. This adapter adds
    a complete decoded-response bound and never exposes unrelated queue content.
    guard must return exactly True and remain tied to the original reservation.
    Both callbacks are host configuration, never model/tool arguments.
    """

    def __init__(self, *, rpc: RpcCall, runtime_binding: RuntimeBinding,
                 guard: BindingGuard, timeout_seconds: float = 15.0,
                 page_size: int = 32, max_pages: int = 4) -> None:
        if not callable(rpc) or not callable(guard):
            raise TypeError("an existing RPC connection and binding guard are required")
        if type(runtime_binding) is not RuntimeBinding:
            raise TypeError("the exact existing RuntimeBinding is required")
        try:
            native = runtime_binding.native_handle
            if (type(native) is not str or str(UUID(native)) != native
                    or runtime_binding.reasoning_surface != "codex"
                    or not _token(runtime_binding.account_label)):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("an exact account-bound Codex session is required") from None
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0.01 <= timeout_seconds <= 60.0):
            raise ValueError("timeout_seconds must be finite and between 0.01 and 60")
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("page_size must be an integer between 1 and 100")
        if type(max_pages) is not int or not 1 <= max_pages <= 16:
            raise ValueError("max_pages must be an integer between 1 and 16")
        self._rpc, self._binding, self._guard = rpc, runtime_binding, guard
        self._timeout = float(timeout_seconds)
        self._page_size, self._max_pages = page_size, max_pages

    def _arguments(self, native_handle: str, nudge_id: str,
                   opaque_ids: Sequence[str]) -> tuple[str, ...]:
        if (native_handle != self._binding.native_handle
                or type(nudge_id) is not str or _NUDGE_ID_RE.fullmatch(nudge_id) is None
                or not isinstance(opaque_ids, (tuple, list))
                or not 1 <= len(opaque_ids) <= _MAX_OPAQUE_IDS
                or any(type(v) is not str or _OPAQUE.fullmatch(v) is None for v in opaque_ids)
                or len(set(opaque_ids)) != len(opaque_ids)):
            raise ValueError("invalid exact queued Wake identity")
        return tuple(sorted(opaque_ids))

    async def _guard_current(self, nudge_id: str, ids: tuple[str, ...]) -> None:
        result = self._guard(self._binding, nudge_id, ids)
        if inspect.isawaitable(result):
            result = await result
        if result is not True:
            raise ValueError("original queued Wake binding is not current")

    @staticmethod
    def _before_deadline(deadline: float) -> None:
        # asyncio's timeout callback cannot fire until the loop regains control.
        # A synchronous guard or inline coroutine must still obey the same budget
        # BEFORE provider entry and before accepted evidence can be returned.
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("queued Wake deadline exceeded")

    @staticmethod
    def _input(nudge_id: str, ids: tuple[str, ...]) -> list[dict[str, Any]]:
        text = CODEX_WAKE_INSTRUCTION + "\n" + json.dumps(
            {"nudge_id": nudge_id, "opaque_ids": ids}, sort_keys=True, separators=(",", ":"))
        return [{"type": "text", "text": text, "text_elements": []}]

    @staticmethod
    def _result(response: Any, request_id: str) -> dict[str, Any]:
        if type(response) is not dict or set(response) not in (
                {"id", "result"}, {"jsonrpc", "id", "result"}):
            raise ValueError("ambiguous queue reply")
        if (response["id"] != request_id or type(response["result"]) is not dict
                or ("jsonrpc" in response and response["jsonrpc"] != "2.0")):
            raise ValueError("uncorrelated queue reply")
        encoded = json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode("ascii")) > _MAX_RESPONSE_BYTES:
            raise ValueError("queue reply exceeds its bound")
        # Detach before any awaited guard; a transport cannot mutate evidence in place.
        return json.loads(encoded)["result"]

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        if (type(row) is not dict or set(row) != {"id", "input", "clientUserMessageId"}
                or not _token(row["id"]) or not _token(row["clientUserMessageId"])
                or type(row["input"]) is not list):
            raise ValueError("malformed native queued submission")
        return row

    def _accepted(self, native_handle: str, nudge_id: str) -> CodexWakeDeliveryObservation:
        return CodexWakeDeliveryObservation(native_handle=native_handle, nudge_id=nudge_id,
                                             accepted=True, delivered=False)

    async def deliver_wake(self, *, native_handle: str, nudge_id: str,
                           opaque_ids: Sequence[str], instruction: str) -> CodexWakeDeliveryObservation:
        submitted = False
        try:
            ids = self._arguments(native_handle, nudge_id, opaque_ids)
            if instruction != CODEX_WAKE_INSTRUCTION:
                raise ValueError("queued Wake instruction is not canonical")
            expected_input = self._input(nudge_id, ids)
            # Transport correlation is per invocation; durable message identity stays
            # nudge_id. Concurrent readers must not collide in the host RPC map.
            request_id = nudge_id + ":queue-add:" + uuid4().hex
            deadline = asyncio.get_running_loop().time() + self._timeout
            async with asyncio.timeout_at(deadline):
                await self._guard_current(nudge_id, ids)
                self._before_deadline(deadline)
                submitted = True
                result = self._result(await self._rpc({
                    "id": request_id, "method": "thread/queue/add", "params": {
                        "threadId": native_handle, "clientUserMessageId": nudge_id,
                        "input": self._input(nudge_id, ids)}}), request_id)
                if set(result) != {"queuedSubmission"}:
                    raise ValueError("ambiguous queued result")
                row = self._row(result["queuedSubmission"])
                if row["clientUserMessageId"] != nudge_id or row["input"] != expected_input:
                    raise ValueError("queued result changed the original Wake")
                await self._guard_current(nudge_id, ids)
                self._before_deadline(deadline)
                return self._accepted(native_handle, nudge_id)
        except Exception:
            if submitted:
                raise WakeEffectUnknownError("queued Wake requires original-operation reconciliation") from None
            raise WakePreSubmitError("queued Wake was refused before submission") from None

    async def reconcile_wake(self, *, native_handle: str, nudge_id: str,
                             opaque_ids: Sequence[str]) -> CodexWakeDeliveryObservation:
        """Read queue evidence only; never add/start/resume or infer safe absence."""
        try:
            ids = self._arguments(native_handle, nudge_id, opaque_ids)
            expected_input = self._input(nudge_id, ids)
            cursor = None
            seen_cursors: set[str] = set()
            seen_rows: set[str] = set()
            matched = False
            deadline = asyncio.get_running_loop().time() + self._timeout
            async with asyncio.timeout_at(deadline):
                for page in range(self._max_pages):
                    await self._guard_current(nudge_id, ids)
                    self._before_deadline(deadline)
                    request_id = nudge_id + ":queue-list:" + str(page) + ":" + uuid4().hex
                    params = {"threadId": native_handle, "limit": self._page_size}
                    if cursor is not None:
                        params["cursor"] = cursor
                    result = self._result(await self._rpc({
                        "id": request_id, "method": "thread/queue/list", "params": params}), request_id)
                    await self._guard_current(nudge_id, ids)
                    self._before_deadline(deadline)
                    if (set(result) != {"data", "nextCursor"} or type(result["data"]) is not list
                            or len(result["data"]) > self._page_size):
                        raise ValueError("incomplete queue page")
                    for item in result["data"]:
                        row = self._row(item)
                        if row["id"] in seen_rows:
                            raise ValueError("queue pagination repeated a row")
                        seen_rows.add(row["id"])
                        if row["clientUserMessageId"] == nudge_id:
                            if matched or row["input"] != expected_input:
                                raise ValueError("ambiguous original queued Wake")
                            matched = True
                    cursor = result["nextCursor"]
                    if cursor is None:
                        if matched:
                            return self._accepted(native_handle, nudge_id)
                        raise ValueError("absence cannot distinguish consumed from never submitted")
                    if not _token(cursor) or cursor in seen_cursors:
                        raise ValueError("queue pagination did not advance")
                    seen_cursors.add(cursor)
                raise ValueError("queue scan exhausted its bound")
        except Exception:
            raise WakeEffectUnknownError("queued Wake reconciliation remains unresolved") from None


__all__ = ["CodexQueuedWakeClient"]
