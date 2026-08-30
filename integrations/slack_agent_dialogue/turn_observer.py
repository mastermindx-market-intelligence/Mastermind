"""One bounded, production-disarmed Agent Dialogue turn observation pass.

The observer reuses the injected Slack history client and canonical Wake
owners.  It owns no token, daemon, cursor, scheduler, queue, or persistence.
"""
from __future__ import annotations

import asyncio
import dataclasses
from enum import Enum
from typing import Callable, Protocol, runtime_checkable

from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetError,
    SessionTargetRegistry,
    WakeRoute,
    route_obligation,
)
from control_plane.wake_dispatcher import WakeEffectUnknownError, WakePreSubmitError
from control_plane.wake_events import WakeObligation, utc_now_iso
from integrations.slack_agent_dialogue.contract import DialogueContractError
from integrations.slack_agent_dialogue.contract_v2 import (
    MESSAGE_DISCRIMINATOR_V2,
    PARENT_DISCRIMINATOR_V2,
    parse_message_frame_v2,
    parse_parent_frame_v2,
)
from integrations.slack_agent_dialogue.engine import (
    DialoguePolicy,
    HistoryPage,
    SlackDialogueClient,
    SlackMessage,
)
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2
from integrations.slack_agent_dialogue.turn_wake_adapter import (
    attention_to_wake_obligation,
)
from integrations.slack_agent_dialogue.turn_watcher import (
    AgentDialogueAttention,
    TurnAction,
    TurnDecision,
    TurnRoutingFacts,
    classify_turn,
)


class ObservationOutcome(str, Enum):
    WAKE_SUBMITTED = "WAKE_SUBMITTED"
    NO_ACTION = "NO_ACTION"
    REFUSED = "REFUSED"
    RECONCILIATION_INCOMPLETE = "RECONCILIATION_INCOMPLETE"
    ACTIVE_WAITER_SUPPRESSED = "ACTIVE_WAITER_SUPPRESSED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    EFFECT_UNKNOWN_HOLD = "EFFECT_UNKNOWN_HOLD"


class WakeCarrierState(str, Enum):
    """Canonical-carrier reconciliation result; never provider status."""

    MISSING = "MISSING"
    RECORDED = "RECORDED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


@runtime_checkable
class WakeCarrier(Protocol):
    """Injected composition seam over the existing Wake Fabric carrier."""

    async def reconcile(
        self, obligation: WakeObligation, route: WakeRoute
    ) -> WakeCarrierState: ...

    async def submit(self, obligation: WakeObligation, route: WakeRoute) -> None: ...


@dataclasses.dataclass(frozen=True)
class ObservationReceipt:
    outcome: ObservationOutcome
    reason: str
    decision: TurnDecision | None
    obligation: WakeObligation | None
    route: WakeRoute | None


class _HistoryIncomplete(RuntimeError):
    pass


class _HistoryRefused(RuntimeError):
    pass


class DialogueTurnObserver:
    """Reconstruct and reconcile one exact watched dialogue turn."""

    def __init__(
        self,
        *,
        policy: DialoguePolicy,
        client: SlackDialogueClient,
        registry: SessionTargetRegistry,
        wake_carrier: WakeCarrier,
        binding_for: Callable[[str], RuntimeBinding | None] | None = None,
        has_active_waiter: Callable[[str, str], bool] | None = None,
        emitted_at: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.policy = policy
        self.client = client
        self.registry = registry
        self.wake_carrier = wake_carrier
        self._binding_for = binding_for or (lambda _seat: None)
        self._has_active_waiter = has_active_waiter or (
            lambda _source_ref, _target_seat: False
        )
        self._emitted_at = emitted_at
        self._submitted_source_refs: set[str] = set()
        self._effect_unknown_source_refs: set[str] = set()

    async def _page(self, awaitable: object) -> HistoryPage:
        try:
            page = await asyncio.wait_for(
                awaitable, timeout=self.policy.method_timeout_seconds
            )
        except Exception:
            raise _HistoryIncomplete("TRANSPORT_UNAVAILABLE") from None
        if not isinstance(page, HistoryPage) or not page.complete:
            raise _HistoryIncomplete("BOUNDED_HISTORY_INCOMPLETE")
        if not page.mutation_evidence_complete:
            raise _HistoryIncomplete("MUTATION_RECONCILIATION_INCOMPLETE")
        return page

    @staticmethod
    def _created_text(message: SlackMessage) -> str:
        if not (message.edited or message.deleted):
            return message.text
        if message.created_text is None:
            raise _HistoryIncomplete("MUTATION_RECONCILIATION_INCOMPLETE")
        return message.created_text

    @staticmethod
    def _same_applicability_carrier(
        trusted: dict[str, object], observed: dict[str, object]
    ) -> bool:
        if trusted["kind"] != observed["kind"]:
            return False
        if trusted["kind"] == "repository":
            return all(
                trusted[field] == observed[field]
                for field in ("repository", "pr")
            )
        return trusted["job_id"] == observed["job_id"]

    async def _accepted_history(
        self, context: DialogueContextV2
    ) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
        normalized = context.normalized()
        channel = await self._page(
            self.client.fetch_channel_history(
                channel_id=self.policy.channel_id,
                limit=self.policy.max_channel_history,
            )
        )
        matches: list[tuple[SlackMessage, dict[str, object]]] = []
        for transport in channel.messages:
            if transport.thread_ts not in {None, transport.ts}:
                continue
            if transport.author_user_id not in self.policy.allowed_parent_user_ids:
                continue
            raw = self._created_text(transport)
            if not raw.startswith(PARENT_DISCRIMINATOR_V2):
                continue
            try:
                parent = parse_parent_frame_v2(raw)
            except DialogueContractError:
                raise _HistoryRefused("PARENT_MESSAGE_INVALID") from None
            identity = tuple(
                parent[field]
                for field in (
                    "work_ref",
                    "commission_ref",
                    "session_ref",
                    "operation_key",
                    "watch_mode",
                )
            )
            wanted = tuple(
                normalized[field]
                for field in (
                    "work_ref",
                    "commission_ref",
                    "session_ref",
                    "operation_key",
                    "watch_mode",
                )
            )
            if identity == wanted:
                if tuple(parent["allowed_sol_user_ids"]) != self.policy.allowed_sol_user_ids:
                    raise _HistoryRefused("THREAD_CONTEXT_MISMATCH")
                matches.append((transport, parent))
        if len(matches) != 1:
            raise _HistoryRefused("THREAD_BINDING_AMBIGUOUS")

        parent_transport, parent = matches[0]
        thread = await self._page(
            self.client.fetch_thread(
                channel_id=self.policy.channel_id,
                thread_ts=parent_transport.ts,
                limit=self.policy.max_thread_history,
            )
        )
        messages: list[dict[str, object]] = []
        for transport in thread.messages:
            if transport.ts == parent_transport.ts:
                continue
            if transport.thread_ts != parent_transport.ts:
                continue
            raw = self._created_text(transport)
            if not raw.startswith(MESSAGE_DISCRIMINATOR_V2):
                continue
            sender_known = (
                transport.author_user_id == self.policy.relay_bot_user_id
                or transport.author_user_id in self.policy.allowed_sol_user_ids
            )
            if not sender_known:
                continue
            try:
                message = parse_message_frame_v2(raw)
            except DialogueContractError:
                raise _HistoryRefused("THREAD_MESSAGE_INVALID") from None
            if not self._same_applicability_carrier(
                normalized["applies_to"], message["applies_to"]
            ):
                raise _HistoryRefused(
                    "DIALOGUE_APPLICABILITY_CARRIER_MISMATCH"
                )
            actor = message["actor_ref"]
            if transport.author_user_id != self.policy.relay_bot_user_id and not (
                actor["kind"] == "executive_surface"
                and actor["seat"] in {"ceo", "chairman"}
            ):
                continue
            messages.append(message)
        return parent, tuple(messages)

    @staticmethod
    def _receipt(
        outcome: ObservationOutcome,
        reason: str,
        *,
        decision: TurnDecision | None = None,
        obligation: WakeObligation | None = None,
        route: WakeRoute | None = None,
    ) -> ObservationReceipt:
        return ObservationReceipt(
            outcome=outcome,
            reason=reason,
            decision=decision,
            obligation=obligation,
            route=route,
        )

    async def reconcile_once(
        self,
        *,
        context: DialogueContextV2,
        routing: TurnRoutingFacts,
    ) -> ObservationReceipt:
        try:
            parent, messages = await self._accepted_history(context)
        except _HistoryIncomplete as exc:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE, str(exc)
            )
        except _HistoryRefused as exc:
            return self._receipt(ObservationOutcome.REFUSED, str(exc))
        except Exception:
            return self._receipt(ObservationOutcome.REFUSED, "OBSERVER_INPUT_INVALID")

        decision = classify_turn(parent=parent, messages=messages, routing=routing)
        if decision.action is TurnAction.REFUSE:
            return self._receipt(
                ObservationOutcome.REFUSED,
                decision.refusal_code or decision.reason,
                decision=decision,
            )
        if decision.attention is None:
            return self._receipt(
                ObservationOutcome.NO_ACTION,
                decision.reason,
                decision=decision,
            )

        attention: AgentDialogueAttention = decision.attention
        source_message = next(
            (
                message
                for message in messages
                if message["message_key"] == attention.message_key
            ),
            None,
        )
        if source_message is not None:
            source_actor = source_message["actor_ref"]
            if (
                source_actor["kind"] == "executive_surface"
                and source_actor["seat"] == attention.target_seat
            ):
                return self._receipt(
                    ObservationOutcome.REFUSED,
                    "DIALOGUE_SELF_LOOP_REFUSED",
                    decision=decision,
                )
        obligation = attention_to_wake_obligation(
            attention, emitted_at=self._emitted_at()
        )
        try:
            route = route_obligation(
                obligation,
                self.registry,
                binding=self._binding_for(attention.target_seat),
            )
        except SessionTargetError as exc:
            return self._receipt(
                ObservationOutcome.REFUSED,
                f"DIALOGUE_WAKE_TARGET_UNBOUND: {exc}",
                decision=decision,
                obligation=obligation,
            )

        source_ref = attention.source_ref
        if self._has_active_waiter(source_ref, attention.target_seat):
            return self._receipt(
                ObservationOutcome.ACTIVE_WAITER_SUPPRESSED,
                "EXACT_ACTIVE_WAITER",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        if source_ref in self._submitted_source_refs:
            return self._receipt(
                ObservationOutcome.DUPLICATE_SUPPRESSED,
                "ATTENTION_IDENTITY_ALREADY_SUBMITTED",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        if source_ref in self._effect_unknown_source_refs:
            return self._receipt(
                ObservationOutcome.EFFECT_UNKNOWN_HOLD,
                "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD",
                decision=decision,
                obligation=obligation,
                route=route,
            )

        try:
            carrier_state = await self.wake_carrier.reconcile(obligation, route)
        except Exception:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "WAKE_CARRIER_RECONCILIATION_UNAVAILABLE",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        if carrier_state is WakeCarrierState.RECORDED:
            self._submitted_source_refs.add(source_ref)
            return self._receipt(
                ObservationOutcome.DUPLICATE_SUPPRESSED,
                "WAKE_OBLIGATION_ALREADY_RECORDED",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        if carrier_state is WakeCarrierState.EFFECT_UNKNOWN:
            self._effect_unknown_source_refs.add(source_ref)
            return self._receipt(
                ObservationOutcome.EFFECT_UNKNOWN_HOLD,
                "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        if carrier_state is not WakeCarrierState.MISSING:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "WAKE_CARRIER_RECONCILIATION_INVALID",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        try:
            await self.wake_carrier.submit(obligation, route)
        except WakePreSubmitError:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "WAKE_TARGET_UNAVAILABLE",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        except WakeEffectUnknownError:
            self._effect_unknown_source_refs.add(source_ref)
            return self._receipt(
                ObservationOutcome.EFFECT_UNKNOWN_HOLD,
                "WAKE_EFFECT_UNKNOWN_SAME_CARRIER_HOLD",
                decision=decision,
                obligation=obligation,
                route=route,
            )
        self._submitted_source_refs.add(source_ref)
        return self._receipt(
            ObservationOutcome.WAKE_SUBMITTED,
            "DIALOGUE_TURN_PENDING",
            decision=decision,
            obligation=obligation,
            route=route,
        )


__all__ = [
    "DialogueTurnObserver",
    "ObservationOutcome",
    "ObservationReceipt",
    "WakeCarrier",
    "WakeCarrierState",
]
