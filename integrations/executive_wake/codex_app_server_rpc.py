"""Concrete exact-thread Codex App Server client for Executive Wake.

This module is deliberately transport-only.  The caller supplies the attested
App Server client factory and the exact runtime-only native thread handle.
It never selects an account, discovers a thread by title/recency, creates or
forks a thread, persists Wake state, or decides whether delivery is allowed.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

from control_plane.wake_dispatcher import (
    TransportOutcome,
    WakePreSubmitError,
)
from integrations.executive_wake.codex_app_server import (
    CodexWakeDeliveryObservation,
)
from scripts.ohf.laboratory import AppServerClient, JsonRpcError


_CLIENT_INFO = {
    "name": "mastermind-wake",
    "title": "Mastermind Executive Wake",
    "version": "1.0",
}
_INITIALIZE_PARAMS = {
    "clientInfo": _CLIENT_INFO,
    "capabilities": {"experimentalApi": True},
}
_COMPLETION_METHOD = "turn/completed"
_COMPLETION_TIMEOUT_PREFIX = "timeout waiting for notification turn/completed"


class CodexAppServerRpcWakeClient:
    """Resume one exact Codex thread and submit one bounded Wake turn.

    Failures before ``turn/start`` begins are typed as definite pre-submit
    failures.  Once ``turn/start`` begins, exceptions remain untyped so the
    existing :class:`CodexAppServerWakeDispatcher` classifies the provider
    effect as unknown and blocks blind retry.
    """

    def __init__(
        self,
        *,
        client_factory: Callable[[], AppServerClient],
        request_timeout_seconds: float = 15.0,
        completion_timeout_seconds: float = 15.0,
    ) -> None:
        if not callable(client_factory):
            raise TypeError("client_factory must be callable")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if completion_timeout_seconds <= 0:
            raise ValueError("completion_timeout_seconds must be positive")
        self._client_factory = client_factory
        self._request_timeout_seconds = float(request_timeout_seconds)
        self._completion_timeout_seconds = float(completion_timeout_seconds)

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
        instruction: str,
    ) -> CodexWakeDeliveryObservation:
        return await asyncio.to_thread(
            self._deliver_sync,
            native_handle=str(native_handle),
            nudge_id=str(nudge_id),
            opaque_ids=tuple(str(item) for item in opaque_ids),
            instruction=str(instruction),
        )

    def _deliver_sync(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        opaque_ids: tuple[str, ...],
        instruction: str,
    ) -> CodexWakeDeliveryObservation:
        try:
            client = self._client_factory()
        except Exception as exc:  # pragma: no cover - exercised through factory contracts
            raise _pre_submit("codex app-server client could not be created") from exc

        provider_submission_begun = False
        try:
            try:
                client.start()
                client.request(
                    "initialize",
                    _INITIALIZE_PARAMS,
                    timeout=self._request_timeout_seconds,
                )
                client.notify("initialized", {})
                resumed = client.request(
                    "thread/resume",
                    {"threadId": native_handle},
                    timeout=self._request_timeout_seconds,
                )
                resumed_thread_id = _thread_id(resumed)
                if resumed_thread_id != native_handle:
                    raise ValueError("thread/resume did not return the exact requested thread")
            except Exception as exc:
                raise _pre_submit("exact Codex thread is unavailable") from exc

            turn_params = {
                "threadId": native_handle,
                "clientUserMessageId": nudge_id,
                "input": [
                    {
                        "type": "text",
                        "text": _wake_text(instruction, opaque_ids),
                        "text_elements": [],
                    }
                ],
            }

            # The effect boundary is immediately before the provider request.
            # Any exception from here onward is potentially post-submit.
            provider_submission_begun = True
            started = client.request(
                "turn/start",
                turn_params,
                timeout=self._request_timeout_seconds,
            )
            turn_id = _turn_id(started)
            if not turn_id:
                raise RuntimeError("turn/start response is missing the turn id")

            try:
                completion = client.wait_notification(
                    _COMPLETION_METHOD,
                    timeout=self._completion_timeout_seconds,
                )
            except JsonRpcError as exc:
                if str(exc).startswith(_COMPLETION_TIMEOUT_PREFIX):
                    return CodexWakeDeliveryObservation(
                        native_handle=native_handle,
                        nudge_id=nudge_id,
                        accepted=True,
                        delivered=False,
                    )
                raise

            if not _completion_matches(
                completion,
                native_handle=native_handle,
                turn_id=turn_id,
            ):
                raise RuntimeError("turn/completed completion identity mismatch")

            return CodexWakeDeliveryObservation(
                native_handle=native_handle,
                nudge_id=nudge_id,
                accepted=True,
                delivered=True,
            )
        finally:
            try:
                client.close()
            except Exception:
                # Before turn/start this cannot create a provider effect, so keep
                # the original definite pre-submit classification.  After
                # turn/start begins, cleanup uncertainty is itself effect-unknown
                # and must never be downgraded to retryability.
                if provider_submission_begun:
                    raise


def _pre_submit(reason: str) -> WakePreSubmitError:
    return WakePreSubmitError(
        reason,
        outcome=TransportOutcome.TARGET_UNAVAILABLE,
        reason_code="target_unavailable",
    )


def _thread_id(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    thread = response.get("thread")
    if not isinstance(thread, dict):
        return ""
    return str(thread.get("id") or "").strip()


def _turn_id(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    turn = response.get("turn")
    if not isinstance(turn, dict):
        return ""
    return str(turn.get("id") or "").strip()


def _wake_text(instruction: str, opaque_ids: tuple[str, ...]) -> str:
    ids = "\n".join(f"- {item}" for item in opaque_ids)
    if not ids:
        return instruction
    return f"{instruction}\n\nOpaque Wake identities (not authority):\n{ids}"


def _completion_matches(
    notification: Any,
    *,
    native_handle: str,
    turn_id: str,
) -> bool:
    if not isinstance(notification, dict):
        return False
    if str(notification.get("method") or "") != _COMPLETION_METHOD:
        return False
    params = notification.get("params")
    if not isinstance(params, dict):
        return False
    if str(params.get("threadId") or "").strip() != native_handle:
        return False
    turn = params.get("turn")
    if not isinstance(turn, dict):
        return False
    return str(turn.get("id") or "").strip() == turn_id
