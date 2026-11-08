"""Small foreground ChatGPT/OS client for the *existing* authenticated Session Bridge.

Presentation only: no MCP listener, credential, session lifecycle, task queue,
watcher, polling controller, transcript store or retry owner. The injected tool
caller is the already-authenticated Executive MCP connector. In particular a
Hermes reply is original-result evidence, not Web-chat push or consumption.
"""
from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from integrations.session_bridge.schemas import validate_tool_arguments

HERMES_KINDS = ("hermes_meta", "hermes_secretary")
_OPERATION = re.compile(r"session-continue-[0-9a-f]{64}\Z")


class TeamBusUnavailable(RuntimeError):
    """No verified tool result; do not infer target, send or completed reply."""


class TeamBusEffectUnknown(RuntimeError):
    """A modifying call may have crossed the transport; do not retry it."""

    def __init__(self, operation_key: str, *, tool_name: str = "session_send") -> None:
        self.operation_key = operation_key
        self.tool_name = tool_name
        recovery = (
            "Read the original operation via session_reply_read; do not resend."
            if tool_name == "session_send" else
            "Recover the original Executive admission receipt and reconcile its exact "
            "request_ref with the existing Executive owner when available. Without "
            "that receipt the effect remains unresolved; do not resubmit."
        )
        super().__init__(
            f"{tool_name} operation {operation_key} has an unknown effect. {recovery}"
        )


@dataclass(frozen=True, slots=True)
class HermesTarget:
    kind: str
    target_ref: str
    operation_key: str
    work_ref: str | None = None


def _unpack(tool: str, value: Any) -> Any:
    """Treat non-success as unknown/unavailable, never as a false empty roster."""
    if (not isinstance(value, Mapping) or value.get("ok") is not True
            or value.get("tool") not in (None, tool)
            or "data" not in value):
        raise TeamBusUnavailable(f"{tool} has no verified successful result")
    return value["data"]


def _operation_key(value: Any) -> str:
    if not isinstance(value, str) or _OPERATION.fullmatch(value) is None:
        raise ValueError("the exact original continuation operation key is required")
    return value


class WebTeamClient:
    """Adapt only incumbent MCP tools; always use fresh server-side authority.

    A projected target must be selected by a discovery call on this client.
    Local selection is UX hygiene, not an authorization decision: the Executive
    ingress independently rechecks principal, generation, admission and effects.
    """

    def __init__(self, call_tool: Callable[[str, Mapping[str, Any]], Any]) -> None:
        if not callable(call_tool):
            raise TypeError("authenticated existing MCP tool caller required")
        self._call_tool = call_tool
        self._selected: dict[tuple[str, str], HermesTarget] = {}

    async def _call(self, name: str, args: Mapping[str, Any]) -> Any:
        result = self._call_tool(name, dict(args))
        if inspect.isawaitable(result):
            return await result
        return result

    async def targets(self, kind: str) -> tuple[HermesTarget, ...]:
        """Discover one supported native Hermes role without guessing sessions."""
        if kind not in HERMES_KINDS:
            raise ValueError("only installed native Hermes kind selectors are supported")
        try:
            rows = _unpack("session_targets", await self._call("session_targets", {"kind": kind}))
        except Exception as exc:
            if isinstance(exc, TeamBusUnavailable):
                raise
            raise TeamBusUnavailable("native target observation unavailable") from exc
        if not isinstance(rows, list) or len(rows) > 256:
            raise TeamBusUnavailable("native target projection malformed")
        targets: list[HermesTarget] = []
        for row in rows:
            if not isinstance(row, Mapping) or row.get("kind") != kind:
                raise TeamBusUnavailable("native target kind changed")
            ref, op = row.get("target_ref"), row.get("continuation_operation_key")
            if (not isinstance(ref, str) or not ref.startswith(kind + ":")
                    or not re.fullmatch(r"[0-9a-f]{64}", ref[len(kind) + 1:])
                    or not isinstance(op, str) or _OPERATION.fullmatch(op) is None):
                raise TeamBusUnavailable("native target identity malformed")
            work_ref = row.get("work_ref")
            if work_ref is not None and (not isinstance(work_ref, str)
                                          or not work_ref.startswith("WS:")):
                raise TeamBusUnavailable("native workstream malformed")
            target = HermesTarget(kind, ref, op, work_ref)
            targets.append(target)
        # Replace only this kind's ephemeral projection; never persist or arm it.
        self._selected = {key: item for key, item in self._selected.items()
                          if item.kind != kind}
        for target in targets:
            self._selected[(target.target_ref, target.operation_key)] = target
        return tuple(targets)

    async def send(self, target: HermesTarget, instruction: str, stop_condition: str) -> Mapping[str, Any]:
        """Make exactly one original, headless continuation attempt.

        Return original owner result unmodified. A transport exception is an
        uncertain effect; it MUST NOT trigger retry, target substitution or
        another carrier. Use read_original to reconcile the original key.
        """
        if (not isinstance(target, HermesTarget)
                or self._selected.get((target.target_ref, target.operation_key)) != target):
            raise ValueError("select the exact current Hermes target from session_targets")
        args = validate_tool_arguments("session_send", dict(
            target_ref=target.target_ref, operation_key=target.operation_key,
            instruction=instruction, stop_condition=stop_condition))
        try:
            result = await self._call("session_send", args)
        except asyncio.CancelledError as exc:
            effect = TeamBusEffectUnknown(target.operation_key)
            exc.team_bus_effect = effect
            exc.add_note(str(effect))
            raise
        except Exception as exc:
            raise TeamBusEffectUnknown(target.operation_key) from exc
        if not isinstance(result, Mapping) or result.get("tool") not in (None, "session_send"):
            raise TeamBusEffectUnknown(target.operation_key)
        # If the canonical tool returns a typed refusal, preserve its exact
        # error/effect classification. Caller must not blindly re-submit.
        if result.get("ok") is not True and result.get("ok") is not False:
            raise TeamBusEffectUnknown(target.operation_key)
        return result

    async def read_original(self, operation_key: str) -> Any:
        """Read original answer; never re-send, mark consumed or create a wake."""
        key = _operation_key(operation_key)
        try:
            return _unpack("session_reply_read", await self._call(
                "session_reply_read", {"operation_key": key}))
        except Exception as exc:
            if isinstance(exc, TeamBusUnavailable):
                raise
            raise TeamBusUnavailable("canonical original-result read unavailable") from exc

    async def submit_worker(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Request existing Executive admission; NOT a pin to DeepSeek/provider."""
        args = validate_tool_arguments("session_summon", request)
        key = args["operation_key"]
        try:
            result = await self._call("session_summon", args)
        except asyncio.CancelledError as exc:
            effect = TeamBusEffectUnknown(key, tool_name="session_summon")
            exc.team_bus_effect = effect
            exc.add_note(str(effect))
            raise
        except Exception as exc:
            raise TeamBusEffectUnknown(key, tool_name="session_summon") from exc
        if (not isinstance(result, Mapping)
                or result.get("tool") not in (None, "session_summon")
                or (result.get("ok") is not True and result.get("ok") is not False)):
            raise TeamBusEffectUnknown(key, tool_name="session_summon")
        return result
