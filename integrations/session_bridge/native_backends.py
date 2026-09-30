"""Provider-specific exact-target adapters for Session Bridge.

These adapters are intentionally tiny: they select an already-declared target
kind and delegate to an incumbent canonical owner. They own no discovery,
lifecycle, placement, retry, queue, provider process, or session state.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .schemas import BridgeError


class ExactTargetRouter:
    """Route one exact target by explicit prefix; never guess or fall back."""

    def __init__(
        self,
        *,
        fabric_sender: Callable[[str, str, str], Any],
        codex_sender: Callable[[str, str, str], Any],
        claude_sender: Callable[[str, str, str], Any],
    ) -> None:
        self._senders = {
            "fabric": fabric_sender,
            "codex": codex_sender,
            "claude": claude_sender,
        }
        if any(not callable(sender) for sender in self._senders.values()):
            raise TypeError("all exact-target senders must be callable")

    def __call__(self, target_ref: str, message: str, operation_key: str) -> Any:
        kind, sep, opaque = target_ref.partition(":")
        if not sep or not opaque:
            raise BridgeError("invalid_input", "target_ref must include an explicit target kind")
        sender = self._senders.get(kind)
        if sender is None:
            raise BridgeError("not_found", "target kind is not addressable")
        # The selected canonical owner must itself verify the opaque exact target
        # against current RuntimeBinding / dialogue / provider-session truth.
        return sender(target_ref, message, operation_key)


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
        # Read-only aggregation only. The returned records remain owned by their
        # canonical sources and MUST carry enough identity for an exact send.
        return {
            name: reader()
            for name, reader in self._readers.items()
        }


class ExecutiveSummonAdapter:
    """Delegate summon to the incumbent Executive admission function."""

    def __init__(self, submit_intent: Callable[[Mapping[str, Any]], Any]) -> None:
        if not callable(submit_intent):
            raise TypeError("submit_intent must be callable")
        self._submit_intent = submit_intent

    def __call__(self, arguments: Mapping[str, Any]) -> Any:
        # preferred_surface is a placement preference only. It grants no provider
        # spawn authority and the Executive owner may refuse or choose otherwise.
        return self._submit_intent(dict(arguments))


__all__ = ["CanonicalTargetReader", "ExactTargetRouter", "ExecutiveSummonAdapter"]
