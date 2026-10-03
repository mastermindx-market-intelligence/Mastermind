"""Exact-target composition adapters for Session Bridge.

These adapters own no dialogue, lifecycle, placement, retry, queue, provider
process, or session state. They compose incumbent canonical owners only.
"""
from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .native_wire import AttentionReference
from .schemas import BridgeError


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class ExactTargetRouter:
    """Route one exact target by explicit prefix; never guess or fall back."""

    def __init__(
        self,
        *,
        fabric_reply: Callable[[str, str, str, str], Any],
        codex_reply: Callable[[str, str, str, str], Any],
        claude_reply: Callable[[str, str, str, str], Any],
    ) -> None:
        self._replies = {
            "fabric_attempt": fabric_reply,
            "codex": codex_reply,
            "claude": claude_reply,
        }
        if any(not callable(reply) for reply in self._replies.values()):
            raise TypeError("all exact-target reply adapters must be callable")

    def __call__(
        self,
        target_ref: str,
        instruction: str,
        stop_condition: str,
        operation_key: str,
    ) -> Any:
        kind, sep, opaque = target_ref.partition(":")
        if not sep or not opaque:
            raise BridgeError(
                "invalid_input", "target_ref must include an explicit target kind"
            )
        reply = self._replies.get(kind)
        if reply is None:
            raise BridgeError("not_found", "target kind is not addressable")
        return reply(target_ref, instruction, stop_condition, operation_key)


class CanonicalReplyCoordinator:
    """Commit the canonical dialogue reply before attempting native attention.

    reply_writer is the existing Agent Dialogue owner (or a thin adapter over
    it) and must fresh-read/reconcile the exact carrier itself. attention_waker
    is attention only: Codex may use current-writer Wake/OHF attention; Claude
    may use an exact attested session-management owner when available.

    A missing/failed attention result never causes the carrier reply to be sent
    again. An unknown carrier effect must be surfaced by reply_writer and never
    reaches attention_waker.
    """

    def __init__(
        self,
        *,
        reply_writer: Callable[[str, str, str, str], Any],
        attention_waker: Callable[[str, AttentionReference], Any],
        attention_reconciler: Callable[[str, AttentionReference], Any] | None = None,
    ) -> None:
        if not callable(reply_writer) or not callable(attention_waker):
            raise TypeError("reply_writer and attention_waker must be callable")
        if attention_reconciler is not None and not callable(attention_reconciler):
            raise TypeError("attention_reconciler must be callable when supplied")
        self._reply_writer = reply_writer
        self._attention_waker = attention_waker
        self._attention_reconciler = attention_reconciler

    async def __call__(
        self,
        target_ref: str,
        instruction: str,
        stop_condition: str,
        operation_key: str,
    ) -> dict[str, Any]:
        carrier = await _maybe_await(
            self._reply_writer(
                target_ref,
                instruction,
                stop_condition,
                operation_key,
            )
        )
        if not isinstance(carrier, Mapping) or carrier.get("reply_committed") is not True:
            raise BridgeError(
                "carrier_not_committed",
                "canonical dialogue reply was not proven committed",
            )
        try:
            reference = AttentionReference(
                operation_key=operation_key,
                message_key=carrier.get("message_key"),
            )
        except (TypeError, ValueError):
            raise BridgeError(
                "effect_unknown",
                "canonical dialogue reply committed without a usable attention reference; "
                "reconcile the original operation",
            ) from None

        if carrier.get("action") == "DUPLICATE":
            # The canonical message was already committed by an earlier call.
            # Never replay native attention on duplicate reconciliation. If an
            # incumbent attention owner exposes a read-only reconciliation seam,
            # consume only that result; otherwise preserve effect uncertainty.
            if self._attention_reconciler is None:
                attention = {"state": "EFFECT_UNKNOWN"}
            else:
                try:
                    attention = await _maybe_await(
                        self._attention_reconciler(target_ref, reference)
                    )
                    if not isinstance(attention, Mapping):
                        attention = {"state": "EFFECT_UNKNOWN"}
                except Exception:
                    attention = {"state": "EFFECT_UNKNOWN"}
        else:
            try:
                attention = await _maybe_await(
                    self._attention_waker(target_ref, reference)
                )
            except Exception:
                # The reply is already committed. Retain its exact receipt even
                # when attention fails; do not retry or expose backend diagnostics.
                # Cancellation remains cancellation, not an inferred no-effect.
                attention = {"state": "EFFECT_UNKNOWN"}
        return {
            "target_ref": target_ref,
            "reply_committed": True,
            "carrier": dict(carrier),
            "attention": attention,
        }


class CanonicalTargetReader:
    """Compose existing projections without inventing a session registry."""

    def __init__(
        self,
        *,
        fabric_reader: Callable[[], Any],
        codex_reader: Callable[[], Any],
        claude_reader: Callable[[], Any],
    ) -> None:
        self._readers = {
            "fabric_attempt": fabric_reader,
            "codex": codex_reader,
            "claude": claude_reader,
        }
        if any(not callable(reader) for reader in self._readers.values()):
            raise TypeError("all target readers must be callable")

    def __call__(self, kind: str | None) -> Any:
        if kind is not None:
            reader = self._readers.get(kind)
            if reader is None:
                raise BridgeError("invalid_input", "unsupported target kind")
            return reader()
        values: dict[str, Any] = {}
        remaining = iter(self._readers.items())
        for name, reader in remaining:
            value = reader()
            if inspect.isawaitable(value):
                async def finish() -> dict[str, Any]:
                    values[name] = await value
                    # Invoke subsequent readers lazily, leaving no unawaited
                    # sibling coroutine if this read fails or is cancelled.
                    for next_name, next_reader in remaining:
                        values[next_name] = await _maybe_await(next_reader())
                    return values
                return finish()
            values[name] = value
        return values


@dataclasses.dataclass(frozen=True)
class ExecutiveSummonBinding:
    """Trusted host-owned fields required by canonical Executive admission."""

    department: str
    priority: int = 0
    workstream: str | None = None
    allowed_write_paths: tuple[str, ...] = ()
    validation: Mapping[str, Any] | None = None
    attempt_limit: int = 2


class ExecutiveSummonBindingResolver(Protocol):
    def resolve(
        self, *, operation_key: str, execution_profile: str
    ) -> ExecutiveSummonBinding: ...


class ExecutiveSummonAdapter:
    """Build one canonical intent using trusted host scope, then submit it.

    The Dot supplies only objective/profile/operation identity. Department,
    priority, workstream, write scope, validation and attempt ceiling come from
    the authenticated host's binding resolver. Provider/host placement remains
    entirely with Executive/Capacity.
    """

    def __init__(
        self,
        submit_intent: Callable[[Mapping[str, Any]], Any],
        *,
        binding_resolver: ExecutiveSummonBindingResolver,
    ) -> None:
        if not callable(submit_intent):
            raise TypeError("submit_intent must be callable")
        if not hasattr(binding_resolver, "resolve") or not callable(binding_resolver.resolve):
            raise TypeError("binding_resolver must expose resolve()")
        self._submit_intent = submit_intent
        self._binding_resolver = binding_resolver

    def __call__(self, arguments: Mapping[str, Any]) -> Any:
        operation_key = arguments["operation_key"]
        execution_profile = arguments["execution_profile"]
        try:
            binding = self._binding_resolver.resolve(
                operation_key=operation_key,
                execution_profile=execution_profile,
            )
        except Exception:
            raise BridgeError(
                "binding_unavailable", "trusted Executive summon binding unavailable"
            ) from None
        if not isinstance(binding, ExecutiveSummonBinding):
            raise BridgeError("binding_unavailable", "trusted Executive summon binding invalid")
        if not isinstance(binding.department, str) or not binding.department:
            raise BridgeError("binding_unavailable", "trusted Executive department unavailable")
        if isinstance(binding.priority, bool) or not isinstance(binding.priority, int):
            raise BridgeError("binding_unavailable", "trusted Executive priority invalid")
        if not 1 <= binding.attempt_limit <= 3:
            raise BridgeError("binding_unavailable", "trusted Executive attempt limit invalid")

        payload: dict[str, Any] = {
            "operation_key": operation_key,
            "objective": arguments["objective"],
            "department": binding.department,
            "priority": binding.priority,
            "execution_profile": execution_profile,
            "attempt_limit": binding.attempt_limit,
        }
        if binding.workstream is not None:
            payload["workstream"] = binding.workstream

        if execution_profile == "bounded_code_change":
            if not binding.allowed_write_paths or not isinstance(binding.validation, Mapping):
                raise BridgeError(
                    "binding_unavailable",
                    "bounded code summon requires trusted write scope and validation",
                )
            payload["allowed_write_paths"] = list(binding.allowed_write_paths)
            payload["validation"] = dict(binding.validation)
        elif binding.allowed_write_paths or binding.validation is not None:
            raise BridgeError(
                "binding_unavailable",
                "research summon binding must not carry write scope",
            )

        return self._submit_intent(payload)


__all__ = [
    "CanonicalReplyCoordinator",
    "CanonicalTargetReader",
    "ExactTargetRouter",
    "ExecutiveSummonAdapter",
    "ExecutiveSummonBinding",
    "ExecutiveSummonBindingResolver",
]
