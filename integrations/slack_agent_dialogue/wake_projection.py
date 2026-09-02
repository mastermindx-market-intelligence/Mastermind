"""Production-disarmed composition of the persisted Agent Dialogue wake vertical.

This module wires two already-accepted owners together: the
:class:`~integrations.slack_agent_dialogue.turn_observer.DialogueTurnObserver`
(bounded turn reconstruction + reconciliation) and the
:class:`~integrations.slack_agent_dialogue.persisted_wake_carrier.PersistedWakeCarrier`
(durable Wake Fabric ledger bridge).  It owns no watcher, loop, store,
transport, retry, binding, or lifecycle state of its own, and it starts
nothing -- calling :func:`compose_persisted_turn_observer` only constructs
the two existing owners from caller-supplied arguments.

Staging note: this module is staged ahead of Wake PR3 Task 3 (W3C runtime
composition), which remains HELD per
``docs/superpowers/plans/2026-08-29-wake-pr3-runtime-completion.md`` pending
MAS-237 (a canonical current ``RuntimeBinding`` source and a trusted
production ``TurnRoutingFacts`` resolver).  Nothing in production source
consumes this module yet, BY DESIGN: it pins the composition seam under an
end-to-end test ahead of that hold releasing.  Do not wire it into
``integrations/slack_agent_dialogue/runtime.py`` (or any other runtime/loop
owner) before the W3C hold is explicitly released.
"""
from __future__ import annotations

from typing import Callable

from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetRegistry,
    WakeRoute,
)
from control_plane.wake_events import utc_now_iso
from control_plane.wake_ledger import WakeRetryPolicy
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.engine import DialoguePolicy, SlackDialogueClient
from integrations.slack_agent_dialogue.persisted_wake_carrier import PersistedWakeCarrier
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
    binding_for: Callable[[str], RuntimeBinding | None] | None = None,
    has_active_waiter: Callable[[str, str], bool] | None = None,
    emitted_at: Callable[[], str] = utc_now_iso,
) -> DialogueTurnObserver:
    """Compose one :class:`DialogueTurnObserver` over one persisted carrier.

    ``PersistedWakeCarrier`` validates its own constructor arguments (see
    ``integrations/slack_agent_dialogue/persisted_wake_carrier.py``).
    ``DialogueTurnObserver`` does not -- its ``__init__`` performs no type
    checking (``integrations/slack_agent_dialogue/turn_observer.py``), so
    callers of this function own the type correctness of ``policy``,
    ``client``, and ``registry``.  This function adds no policy, retry,
    binding, or lifecycle behavior of its own -- it is pure composition.
    """

    carrier = PersistedWakeCarrier(
        repository=repository,
        dispatchers=dispatchers,
        current_binding_for=current_binding_for,
        retry_policy=retry_policy,
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
