"""Persisted WakeCarrier adapter for the production-disarmed turn observer.

This module composes existing Wake Fabric owners only.  It owns no watcher,
ledger, retry state, binding registry, provider discovery, or lifecycle state.
"""
from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Sequence

from control_plane.dialogue_wake_canary_activation import (
    DialogueWakeCanaryActivationGrant,
    DialogueWakeCanaryActivationError,
    DialogueWakeCanaryProfile,
    effective_dialogue_wake_canary_route,
)

from control_plane.executive_runtime import StateConflict
from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    PhysicalDialogueSourceIdentity,
)
from control_plane.session_targets import (
    RuntimeBinding,
    SessionTarget,
    SessionTargetRegistry,
    WakeRoute,
    destination_digest,
)
from control_plane.wake_dispatcher import (
    PersistedNudgeState,
    PersistedDeliveredAckState,
    WakeEffectUnknownError,
    WakePreSubmitError,
    dispatch_persisted_nudge,
    mint_nudge_id,
    reconcile_persisted_delivered_ack,
)
from control_plane.wake_events import WakeObligation, canonical_json_bytes
from control_plane.wake_ledger import (
    DeliveryAttempt,
    LedgerPhase,
    WakeRetryPolicy,
    event_payload_for,
    payloads_equivalent,
    parse_ledger_record,
    requested_record,
)
from control_plane.wake_persist import PersistedWakeEvent, WakeLedgerRepository
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
        target_registry: SessionTargetRegistry | None = None,
        canary_profile: DialogueWakeCanaryProfile | None = None,
        historical_context_for: (
            Callable[[DeliveryAttempt], "HistoricalWakeContext"] | None
        ) = None,
        physical_source: PhysicalDialogueSourceIdentity | None = None,
    ) -> None:
        if not isinstance(repository, WakeLedgerRepository):
            raise TypeError("repository must be WakeLedgerRepository")
        if not isinstance(dispatchers, WakeDispatcherRegistry):
            raise TypeError("dispatchers must be WakeDispatcherRegistry")
        if not callable(current_binding_for):
            raise TypeError("current_binding_for must be callable")
        if not isinstance(retry_policy, WakeRetryPolicy):
            raise TypeError("retry_policy must be WakeRetryPolicy")
        if target_registry is not None and not isinstance(
            target_registry, SessionTargetRegistry
        ):
            raise TypeError("target_registry must be SessionTargetRegistry or None")
        if (
            canary_profile is not None
            and type(canary_profile) is not DialogueWakeCanaryProfile
        ):
            raise TypeError("canary_profile must be a closed DialogueWakeCanaryProfile")
        if historical_context_for is not None and not callable(
            historical_context_for
        ):
            raise TypeError("historical_context_for must be callable or None")
        if physical_source is not None and type(physical_source) is not PhysicalDialogueSourceIdentity:
            raise TypeError("physical_source must be a closed physical identity")
        if physical_source is not None and canary_profile is None:
            raise TypeError("physical_source requires the closed canary profile")
        self._repository = repository
        self._dispatchers = dispatchers
        self._current_binding_for = current_binding_for
        self._retry_policy = retry_policy
        self._target_registry = target_registry
        self._canary_profile = canary_profile
        self._historical_context_for = historical_context_for
        self._physical_source = physical_source

    def has_persisted_attempt(self, obligation: WakeObligation) -> bool:
        """Classify effect presence without route resolution or provider access."""

        persisted = self._repository.list_records(obligation.obligation_id)
        if not persisted:
            return False
        _assert_requested_replay(obligation, persisted, self._physical_source)
        attempts = sum(
            item.record.phase is LedgerPhase.DELIVERY_ATTEMPT for item in persisted
        )
        if attempts > 1 and self._canary_profile is not None:
            raise CanaryWakeHistoryError(
                "canary Wake has contradictory multiple attempts"
            )
        return attempts == 1

    async def reconcile(
        self,
        obligation: WakeObligation,
        route: WakeRoute,
    ) -> WakeCarrierState:
        _assert_pair(obligation, route)
        persisted = self._repository.list_records(obligation.obligation_id)
        if not persisted:
            return WakeCarrierState.MISSING

        _assert_requested_replay(obligation, persisted, self._physical_source)
        records = tuple(item.record for item in persisted)
        if self._canary_profile is not None:
            return await self._reconcile_canary(obligation, route, records)
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

        if (
            LedgerPhase.ACCEPTED in phases
            and LedgerPhase.DELIVERED not in phases
            and LedgerPhase.TARGET_ACKNOWLEDGED not in phases
        ):
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
                target_registry=self._target_registry,
            )
            if result.state is PersistedNudgeState.DELIVERED:
                return WakeCarrierState.RECORDED
            return WakeCarrierState.EFFECT_UNKNOWN

        return WakeCarrierState.RECORDED

    async def submit(self, obligation: WakeObligation, route: WakeRoute) -> None:
        _assert_pair(obligation, route)
        # Always traverse the canonical repository replay boundary.  WAKE-* is
        # source-identity scoped rather than a full-envelope hash; an existing
        # command id is therefore not proof that this caller supplied the same
        # frozen target/correlation envelope.  The repository's idempotent
        # append validates exact correlation and payload equivalence without
        # creating a second row for an identical replay.
        self._repository.append_record(
            requested_record(obligation, physical_source=self._physical_source),
            obligation=obligation,
        )

        if self._canary_profile is not None:
            records = tuple(
                item.record
                for item in self._repository.list_records(obligation.obligation_id)
            )
            state = await self._reconcile_canary(
                obligation,
                route,
                records,
                submit_if_missing=True,
            )
            if state is WakeCarrierState.EFFECT_UNKNOWN:
                raise CanaryWakeHistoryError("canary Wake effect remains unknown")
            return

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
            target_registry=self._target_registry,
        )
        if result.state is PersistedNudgeState.RECONCILIATION_REQUIRED:
            raise WakeEffectUnknownError(
                "persisted Wake delivery requires same-attempt reconciliation"
            )

    async def reconcile_delivered_ack(
        self,
        source_observation: DialogueSourceObservation,
        obligation: WakeObligation,
    ) -> WakeCarrierState:
        """Drain one ACK for the exact stored v2 DELIVERED attempt."""

        physical = self._physical_source
        if (
            self._canary_profile is None
            or type(source_observation) is not DialogueSourceObservation
            or type(physical) is not PhysicalDialogueSourceIdentity
            or source_observation.to_dict()
            != {
                "workspace_id": physical.workspace_id,
                "channel_id": physical.channel_id,
                "thread_ts": physical.thread_ts,
                "predecessor_message_key": physical.predecessor_message_key,
                "predecessor_message_fingerprint": physical.predecessor_message_fingerprint,
            }
        ):
            return WakeCarrierState.EFFECT_UNKNOWN
        persisted = self._repository.list_records(obligation.obligation_id)
        if not persisted:
            return WakeCarrierState.MISSING
        try:
            _assert_requested_replay(obligation, persisted, physical)
            grant = self._canary_profile.grant
            if grant is None:
                return WakeCarrierState.EFFECT_UNKNOWN
            matched = _validated_delayed_ack_attempt(
                obligation, persisted, grant
            )
            if matched is None:
                return WakeCarrierState.EFFECT_UNKNOWN
            attempt, effective_route = matched
            resolver = self._historical_context_for
            if not callable(resolver):
                return WakeCarrierState.EFFECT_UNKNOWN
            context = resolver(attempt)
            if not isinstance(context, HistoricalWakeContext):
                return WakeCarrierState.EFFECT_UNKNOWN
            dispatcher = context.dispatchers.resolve(effective_route.wake_transport)
            registry = context.target_registry
            if registry is None:
                return WakeCarrierState.EFFECT_UNKNOWN
            result = await reconcile_persisted_delivered_ack(
                self._repository,
                [(obligation, effective_route)],
                dispatcher=dispatcher,
                binding=context.runtime_binding,
                target_registry=registry,
            )
        except Exception:
            return WakeCarrierState.EFFECT_UNKNOWN
        if result.state is PersistedDeliveredAckState.RECORDED:
            return WakeCarrierState.RECORDED
        if result.state is PersistedDeliveredAckState.HOLD:
            return WakeCarrierState.MISSING
        return WakeCarrierState.EFFECT_UNKNOWN

    def delayed_ack_history_matches(self, obligation: WakeObligation) -> bool:
        """Validate terminal replay identity without entering a provider seam."""

        profile = self._canary_profile
        physical = self._physical_source
        if (
            type(profile) is not DialogueWakeCanaryProfile
            or profile.grant is None
            or type(physical) is not PhysicalDialogueSourceIdentity
        ):
            return False
        persisted = self._repository.list_records(obligation.obligation_id)
        try:
            _assert_requested_replay(obligation, persisted, physical)
            return _validated_delayed_ack_attempt(
                obligation, persisted, profile.grant
            ) is not None
        except Exception:
            return False

    async def _reconcile_canary(
        self,
        obligation: WakeObligation,
        route: WakeRoute,
        records: Sequence[object],
        *,
        submit_if_missing: bool = False,
    ) -> WakeCarrierState:
        """Apply the closed zero-or-one-attempt canary history contract."""

        profile = self._canary_profile
        assert profile is not None
        attempt_records = tuple(
            record
            for record in records
            if getattr(record, "phase", None) is LedgerPhase.DELIVERY_ATTEMPT
        )
        if len(attempt_records) > 1:
            raise CanaryWakeHistoryError(
                "canary Wake has contradictory multiple attempts"
            )
        if not attempt_records:
            if not submit_if_missing:
                return WakeCarrierState.MISSING
            if profile.grant is None:
                raise WakePreSubmitError("canary activation grant is unavailable")
            effective_route = _canary_effective_route(profile, route)
            binding = self._current_binding_for(effective_route)
            _assert_current_binding(binding, effective_route)
            assert binding is not None
            dispatcher = self._dispatchers.resolve(route.wake_transport)
            result = await dispatch_persisted_nudge(
                self._repository,
                [(obligation, effective_route)],
                dispatcher=dispatcher,
                binding=binding,
                retry_policy=self._retry_policy,
                target_registry=self._target_registry,
            )
            if result.state is PersistedNudgeState.RECONCILIATION_REQUIRED:
                return WakeCarrierState.EFFECT_UNKNOWN
            return WakeCarrierState.RECORDED

        attempt = _delivery_attempt(attempt_records[0])
        if profile.grant is None:
            raise CanaryWakeHistoryError("persisted canary attempt has no retained grant")
        effective_route = _canary_effective_route(profile, route)
        if not attempt.matches_route(effective_route):
            raise CanaryWakeHistoryError("persisted canary attempt identity disagrees")
        phases = tuple(getattr(record, "phase", None) for record in records)
        terminal = {
            LedgerPhase.DELIVERED,
            LedgerPhase.TARGET_ACKNOWLEDGED,
            LedgerPhase.SOURCE_RESOLVED,
            LedgerPhase.FAILED,
            LedgerPhase.TARGET_UNAVAILABLE,
        }
        if any(phase in terminal for phase in phases):
            return WakeCarrierState.RECORDED
        if LedgerPhase.ACCEPTED not in phases:
            return WakeCarrierState.EFFECT_UNKNOWN
        resolver = self._historical_context_for
        if not callable(resolver):
            return WakeCarrierState.EFFECT_UNKNOWN
        try:
            context = resolver(attempt)
        except Exception:
            return WakeCarrierState.EFFECT_UNKNOWN
        if not isinstance(context, HistoricalWakeContext):
            return WakeCarrierState.EFFECT_UNKNOWN
        try:
            dispatcher = context.dispatchers.resolve(effective_route.wake_transport)
            result = await dispatch_persisted_nudge(
                self._repository,
                [(obligation, effective_route)],
                dispatcher=dispatcher,
                binding=context.runtime_binding,
                retry_policy=self._retry_policy,
                target_registry=context.target_registry,
            )
        except Exception:
            return WakeCarrierState.EFFECT_UNKNOWN
        if result.state is PersistedNudgeState.DELIVERED:
            return WakeCarrierState.RECORDED
        return WakeCarrierState.EFFECT_UNKNOWN


class CanaryWakeHistoryError(WakeEffectUnknownError):
    """Persisted canary evidence exists but cannot be credited safely."""


@dataclasses.dataclass(frozen=True)
class HistoricalWakeContext:
    dispatchers: WakeDispatcherRegistry
    runtime_binding: RuntimeBinding
    target_registry: SessionTargetRegistry | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dispatchers, WakeDispatcherRegistry):
            raise TypeError("historical dispatchers are invalid")
        if not isinstance(self.runtime_binding, RuntimeBinding):
            raise TypeError("historical RuntimeBinding is invalid")
        if self.target_registry is not None and not isinstance(
            self.target_registry, SessionTargetRegistry
        ):
            raise TypeError("historical target registry is invalid")


def _delivery_attempt(record: object) -> DeliveryAttempt:
    parsed = parse_ledger_record(record)
    return DeliveryAttempt(
        obligation_id=str(parsed.command_id).split(":", 1)[0],
        attempt_n=int(parsed.attempt_n or 0),
        attempt_command_id=str(parsed.command_id),
        destination_digest=str(parsed.destination_digest or ""),
        route_digest=str(parsed.route_digest or ""),
        binding_id=str(parsed.binding_id or ""),
        binding_generation=int(parsed.binding_generation or 0),
        session_alias=str(parsed.session_alias or ""),
        reasoning_surface=str(parsed.reasoning_surface or ""),
        wake_transport=str(parsed.wake_transport or ""),
        nudge_id=parsed.nudge_id,
        nudge_attempt_command_ids=tuple(parsed.nudge_attempt_command_ids),
    )


def _validated_delayed_ack_attempt(
    obligation: WakeObligation,
    persisted: Sequence[PersistedWakeEvent],
    grant: DialogueWakeCanaryActivationGrant,
) -> tuple[DeliveryAttempt, WakeRoute] | None:
    """Bind a stored singleton delivery to the currently installed grant."""

    attempts = tuple(
        item.record
        for item in persisted
        if item.record.phase is LedgerPhase.DELIVERY_ATTEMPT
    )
    delivered = tuple(
        item.record
        for item in persisted
        if item.record.phase is LedgerPhase.DELIVERED
    )
    if len(attempts) != 1 or len(delivered) != 1:
        return None
    attempt = _delivery_attempt(attempts[0])
    if (
        not delivered[0].matches_attempt(attempt)
        or not attempt.nudge_id
        or attempt.nudge_attempt_command_ids != (attempt.attempt_command_id,)
        or attempt.session_alias != grant.target_session_alias
        or attempt.binding_id != grant.binding_id
        or attempt.binding_generation != grant.binding_generation
    ):
        return None
    expected_destination = destination_digest(
        target=SessionTarget(
            session_alias=grant.target_session_alias,
            target_seat=grant.target_seat,
            reasoning_surface=attempt.reasoning_surface,
            wake_transport=attempt.wake_transport,
            allowed_transports=(attempt.wake_transport,),
            workstream=obligation.workstream,
            target_enabled=False,
        ),
        binding_id=grant.binding_id,
        binding_generation=grant.binding_generation,
    )
    if attempt.destination_digest != expected_destination:
        return None
    if attempt.nudge_id != mint_nudge_id(
        expected_destination,
        (attempt.attempt_command_id,),
    ):
        return None
    effective_policy = hashlib.sha256(
        canonical_json_bytes({
            "base_policy_digest": grant.policy_digest,
            "grant_digest": grant.digest,
        })
    ).hexdigest()[:16]
    from control_plane.session_targets import route_digest

    expected_route_digest = route_digest(
        obligation_id=obligation.obligation_id,
        destination=expected_destination,
        policy_digest=effective_policy,
    )
    if attempt.route_digest != expected_route_digest:
        return None
    route = WakeRoute(
        obligation_id=obligation.obligation_id,
        session_alias=grant.target_session_alias,
        target_seat=grant.target_seat,
        reasoning_surface=attempt.reasoning_surface,
        wake_transport=attempt.wake_transport,
        binding_id=grant.binding_id,
        binding_generation=grant.binding_generation,
        route_digest=expected_route_digest,
        destination_digest=expected_destination,
        policy_digest=effective_policy,
        root_job_id=obligation.root_job_id,
        workstream=obligation.workstream,
        production_armed=True,
        target_enabled=True,
        transport_implemented=True,
        requires_runtime_binding=True,
        binding_ready=True,
        human_required=False,
        policy_version="dialogue-canary-v1",
        interface_version="mastermind.wake_dispatcher/v1",
    )
    return attempt, route


def _canary_effective_route(
    profile: DialogueWakeCanaryProfile,
    route: WakeRoute,
) -> WakeRoute:
    grant = profile.grant
    if grant is None:
        raise WakePreSubmitError("canary activation grant is unavailable")
    input_was_base = not route.production_armed and not route.target_enabled
    if input_was_base:
        base = route
    else:
        base = dataclasses.replace(
            route,
            production_armed=False,
            target_enabled=False,
            policy_digest=grant.policy_digest,
            route_digest="",
        )
    # Reconstitute the canonical disarmed route digest before deriving the only
    # effective route; callers cannot smuggle armed flags or policy bytes.
    from control_plane.session_targets import route_digest

    canonical_base = dataclasses.replace(
        base,
        route_digest=route_digest(
            obligation_id=base.obligation_id,
            destination=base.destination_digest,
            policy_digest=base.policy_digest,
        ),
    )
    if input_was_base and route != canonical_base:
        raise CanaryWakeHistoryError("canary base route digest disagrees")
    base = canonical_base
    try:
        expected = effective_dialogue_wake_canary_route(profile, base)
    except DialogueWakeCanaryActivationError as exc:
        raise CanaryWakeHistoryError("canary route identity is invalid") from exc
    if not input_was_base and route != expected:
        raise CanaryWakeHistoryError("canary effective route identity disagrees")
    return expected


def _assert_pair(obligation: WakeObligation, route: WakeRoute) -> None:
    if route.obligation_id != obligation.obligation_id:
        raise ValueError("Wake route obligation_id does not match the obligation")


def _assert_requested_replay(
    obligation: WakeObligation,
    persisted: Sequence[PersistedWakeEvent],
    physical_source: PhysicalDialogueSourceIdentity | None,
) -> None:
    """Read-validate one supplied obligation against the frozen request envelope."""

    requested = tuple(
        item for item in persisted if item.record.phase is LedgerPhase.WAKE_REQUESTED
    )
    if len(requested) != 1:
        raise StateConflict("wake stream requires exactly one WAKE_REQUESTED event")
    proposed = event_payload_for(
        requested_record(obligation, physical_source=physical_source),
        obligation=obligation,
    )
    if not payloads_equivalent(
        requested[0].event.payload,
        proposed,
        phase=LedgerPhase.WAKE_REQUESTED,
    ):
        raise StateConflict("command_id collision: existing payload disagrees")


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


__all__ = [
    "CanaryWakeHistoryError",
    "HistoricalWakeContext",
    "PersistedWakeCarrier",
]
