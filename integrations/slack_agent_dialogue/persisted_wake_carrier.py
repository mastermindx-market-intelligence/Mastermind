"""Persisted WakeCarrier adapter for the production-disarmed turn observer.

This module composes existing Wake Fabric owners only.  It owns no watcher,
ledger, retry state, binding registry, provider discovery, or lifecycle state.
"""
from __future__ import annotations

from collections.abc import Callable

from control_plane.session_targets import RuntimeBinding, WakeRoute
from control_plane.wake_dispatcher import (
    PersistedNudgeState,
    WakeEffectUnknownError,
    WakePreSubmitError,
    dispatch_persisted_nudge,
)
from control_plane.wake_events import WakeObligation
from control_plane.wake_ledger import (
    LedgerPhase,
    WakeRetryPolicy,
    requested_record,
)
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.turn_observer import WakeCarrierState


class PersistedWakeCarrier:
    """Bridge one observed dialogue obligation into the existing Wake ledger."""

    def __init__(
        self,
        *,
        repository: WakeLedgerRepository,
        dispatchers: WakeDispatcherRegistry,
        current_binding_for: Callable[[WakeRoute], RuntimeBinding | None],
        retry_policy: WakeRetryPolicy,
    ) -> None:
        if not isinstance(repository, WakeLedgerRepository):
            raise TypeError("repository must be WakeLedgerRepository")
        if not isinstance(dispatchers, WakeDispatcherRegistry):
            raise TypeError("dispatchers must be WakeDispatcherRegistry")
        if not callable(current_binding_for):
            raise TypeError("current_binding_for must be callable")
        if not isinstance(retry_policy, WakeRetryPolicy):
            raise TypeError("retry_policy must be WakeRetryPolicy")
        self._repository = repository
        self._dispatchers = dispatchers
        self._current_binding_for = current_binding_for
        self._retry_policy = retry_policy

    async def reconcile(
        self,
        obligation: WakeObligation,
        route: WakeRoute,
    ) -> WakeCarrierState:
        _assert_pair(obligation, route)
        records = tuple(
            item.record for item in self._repository.list_records(obligation.obligation_id)
        )
        if not records:
            return WakeCarrierState.MISSING

        phases = tuple(record.phase for record in records)
        if phases == (LedgerPhase.WAKE_REQUESTED,):
            # A crash between durable request persistence and delivery-attempt
            # creation must remain submit-eligible after restart.
            return WakeCarrierState.MISSING

        unfinished_attempts = {
            int(record.attempt_n)
            for record in records
            if record.phase is LedgerPhase.DELIVERY_ATTEMPT
            and record.attempt_n is not None
            and not any(
                later.attempt_n == record.attempt_n
                and later.phase
                in {
                    LedgerPhase.ACCEPTED,
                    LedgerPhase.DELIVERED,
                    LedgerPhase.FAILED,
                    LedgerPhase.TARGET_UNAVAILABLE,
                }
                for later in records
            )
        }
        if unfinished_attempts:
            return WakeCarrierState.EFFECT_UNKNOWN

        return WakeCarrierState.RECORDED

    async def submit(self, obligation: WakeObligation, route: WakeRoute) -> None:
        _assert_pair(obligation, route)
        records = self._repository.list_records(obligation.obligation_id)
        if not any(item.record.phase is LedgerPhase.WAKE_REQUESTED for item in records):
            self._repository.append_record(
                requested_record(obligation),
                obligation=obligation,
            )

        binding = self._current_binding_for(route)
        _assert_current_binding(binding, route)
        assert binding is not None

        dispatcher = self._dispatchers.resolve(route.wake_transport)
        result = await dispatch_persisted_nudge(
            self._repository,
            [(obligation, route)],
            dispatcher=dispatcher,
            binding=binding,
            retry_policy=self._retry_policy,
        )
        if result.state is PersistedNudgeState.RECONCILIATION_REQUIRED:
            raise WakeEffectUnknownError(
                "persisted Wake delivery requires same-attempt reconciliation"
            )


def _assert_pair(obligation: WakeObligation, route: WakeRoute) -> None:
    if route.obligation_id != obligation.obligation_id:
        raise ValueError("Wake route obligation_id does not match the obligation")


def _assert_current_binding(
    binding: RuntimeBinding | None,
    route: WakeRoute,
) -> None:
    if binding is None:
        raise WakePreSubmitError("current RuntimeBinding is unavailable")
    if (
        binding.session_alias != route.session_alias
        or binding.binding_id != route.binding_id
        or binding.binding_generation != route.binding_generation
        or binding.reasoning_surface != route.reasoning_surface
    ):
        raise WakePreSubmitError(
            "current RuntimeBinding no longer matches the Wake route"
        )


__all__ = ["PersistedWakeCarrier"]
