"""Production-disarmed composition of the existing persisted Wake owners.

The helper wires the accepted turn observer to the canonical Wake ledger,
dispatcher registry, retry policy, and current RuntimeBinding revalidation.
It creates no new store, lifecycle, queue, watcher, retry, or provider plane.
"""
from __future__ import annotations

from collections.abc import Callable

from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetRegistry,
    WakeRoute,
)
from control_plane.wake_events import utc_now_iso
from control_plane.wake_ledger import WakeRetryPolicy
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.engine import (
    DialoguePolicy,
    SlackDialogueClient,
)
from integrations.slack_agent_dialogue.persisted_wake_carrier import (
    PersistedWakeCarrier,
)
from integrations.slack_agent_dialogue.turn_observer import DialogueTurnObserver


def compose_persisted_turn_observer(
    *,
    policy: DialoguePolicy,
    client: SlackDialogueClient,
    registry: SessionTargetRegistry,
    repository: WakeLedgerRepository,
    dispatchers: WakeDispatcherRegistry,
    current_binding_for: Callable[[WakeRoute], RuntimeBinding | None],
    retry_policy: WakeRetryPolicy,
    has_active_waiter: Callable[[str, str], bool],
    binding_for: Callable[[str], RuntimeBinding | None] | None = None,
    emitted_at: Callable[[], str] = utc_now_iso,
) -> DialogueTurnObserver:
    """Compose one observer over the canonical persisted Wake carrier."""

    if not callable(has_active_waiter):
        raise TypeError("has_active_waiter must be callable")

    carrier = PersistedWakeCarrier(
        repository=repository,
        dispatchers=dispatchers,
        current_binding_for=current_binding_for,
        retry_policy=retry_policy,
        target_registry=registry,
    )
    return DialogueTurnObserver(
        policy=policy,
        client=client,
        registry=registry,
        wake_carrier=carrier,
        binding_for=binding_for,
        has_active_waiter=has_active_waiter,
        emitted_at=emitted_at,
    )


__all__ = ["compose_persisted_turn_observer"]
