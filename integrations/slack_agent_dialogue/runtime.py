"""Private long-running Agent Relay composition over the existing AF_UNIX owner.

The runtime owns no dialogue, worker, retry, Wake, queue, or durable lifecycle
state. It reads one host-provisioned token exactly once at startup, injects one
Slack client into the existing V1 and V2 engines, and serves their closed
request surface over one group-reachable, peer-credentialled Unix socket.

W3C adds only an optional, production-disarmed in-process turn loop. The loop
recomputes exact-current-worker and target bindings on every pass and delegates
all history, Wake persistence, retry, and provider effects to existing owners.
A completed terminal RESULT remains explicitly held until an accepted owner
supplies a durable post-time dialogue binding; W3C never weakens WP-3 to infer it.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import stat
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence, Union

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
from control_plane.executive_runtime import (
    AttemptStatus,
    ExecutiveDialogueSource,
    WorkerStatus,
)
from control_plane.executive_terminal_return import TerminalReturnCandidate
from control_plane.session_targets import (
    RuntimeBinding,
    SessionTargetRegistry,
    WakeRoute,
)
from control_plane.wake_events import utc_now_iso
from control_plane.wake_ledger import WakeRetryPolicy
from control_plane.wake_persist import WakeLedgerRepository
from integrations.executive_wake.registry import WakeDispatcherRegistry
from integrations.slack_agent_dialogue.company_dialogue_runtime_binding import (
    BindingState,
    CurrentWorkerDialogueSnapshot,
    WorkerDialogueCaller,
    resolve_company_dialogue_binding,
)
from integrations.slack_agent_dialogue.engine import (
    DialogueEngine,
    DialogueEngineError,
    DialoguePolicy,
)
from integrations.slack_agent_dialogue.engine_v2 import (
    DialogueContextV2,
    DialogueEngineV2,
)
from integrations.slack_agent_dialogue.executive_observation_client import (
    ExecutiveDialogueObservationClient,
    ExecutiveObservationClientError,
    ResolvedDialogueObservation,
)
from integrations.slack_agent_dialogue.executive_terminal_return_projector import (
    ResolvedTerminalReturnBinding,
    RuntimeTerminalReturnBindingResolver,
    TerminalReturnBindingResolver,
    TerminalReturnProjectionReceipt,
    _build_message as build_terminal_result_message,
)
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService,
    DialogueServiceError,
    ServiceConfig,
)
from integrations.slack_agent_dialogue.slack_web_api import (
    SlackHttpTransport,
    SlackWebApiDialogueClient,
)
from integrations.slack_agent_dialogue.turn_observer import (
    DialogueTurnObserver,
    ObservationOutcome,
    ObservationReceipt,
)
from integrations.slack_agent_dialogue.turn_routing_facts import (
    TurnRoutingFactsError,
    resolve_terminal_turn_routing_facts,
    resolve_turn_routing_facts,
)
from integrations.slack_agent_dialogue.turn_runtime_primitives import (
    ActiveWaiterKey,
    ActiveWaiterRegistry,
    AsyncCandidateCollector,
    CandidateCollectionBusy,
    CandidateCollectionOverflow,
    CandidateCollectionTimeout,
    CandidateCollectionUnavailable,
)
from integrations.slack_agent_dialogue.wake_projection import (
    compose_persisted_turn_observer,
)

_TOKEN_MAX_BYTES = 2048
AGENT_RELAY_SOCKET_PATH = Path("/var/run/mastermind-agent-relay/agent-relay.sock")
EXECUTIVE_OBSERVATION_SOCKET_PATH = Path(
    "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
)
EXECUTIVE_CLIENT_UID = 450
DEFAULT_MAX_TURN_CANDIDATES_PER_PASS = 32
MAX_TURN_CANDIDATES_PER_PASS = 256
DEFAULT_TURN_CANDIDATE_COLLECTION_TIMEOUT_SECONDS = 10.0
_RUNTIME_ERROR_CODES = frozenset(
    {
        "RUNTIME_INVALID",
        "TOKEN_FILE_INVALID",
        "TOKEN_FILE_UNAVAILABLE",
        "TOKEN_FILE_UNSAFE",
    }
)


class RelayRuntimeError(RuntimeError):
    """One opaque startup refusal; credential bytes never enter the error."""

    def __init__(self, code: str) -> None:
        if code not in _RUNTIME_ERROR_CODES:
            raise ValueError("unknown Agent Relay runtime error code")
        super().__init__(code)
        self.code = code


class ActiveWaiterStateUnavailable(RuntimeError):
    """Trusted active-waiter evidence is missing, malformed, or unavailable."""

    def __init__(self) -> None:
        super().__init__("ACTIVE_WAITER_STATE_UNAVAILABLE")
        self.code = "ACTIVE_WAITER_STATE_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class _ActiveWaiterLookupContext:
    parent_fingerprint: str
    operation_key: str
    session_ref: str


class PrivateRelayAuthorityPolicy:
    """Fixed host authority used only after the engines validate exact lineage.

    Slack prose cannot lower this policy. The V1/V2 engines first validate the
    bound parent, sender identity, reply direction, context, and exact reply
    lineage. Only then may a syntactically valid Sol ``CONTINUE`` reach
    ``allows_continuation``. RULING options always retain the Chairman floor.
    """

    def minimum_authority(
        self,
        *,
        request: Mapping[str, Any],
        option: Mapping[str, Any],
    ) -> str:
        del request, option
        return "CHAIRMAN_REQUIRED"

    def allows_continuation(
        self,
        *,
        request: Mapping[str, Any],
        reply: Mapping[str, Any],
    ) -> bool:
        del request, reply
        return True


@dataclass(frozen=True)
class RelayRuntimeConfig:
    socket_path: Path
    token_file: Path
    workspace_id: str
    channel_id: str
    bot_user_id: str
    allowed_peer_uids: tuple[int, ...]
    allowed_sol_user_ids: tuple[str, ...]
    allowed_parent_user_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            socket_path = Path(self.socket_path)
        except (TypeError, ValueError):
            raise RelayRuntimeError("RUNTIME_INVALID") from None
        if (
            socket_path != AGENT_RELAY_SOCKET_PATH
            or self.allowed_peer_uids != (EXECUTIVE_CLIENT_UID,)
        ):
            raise RelayRuntimeError("RUNTIME_INVALID")

        token_file = Path(self.token_file)
        if not token_file.is_absolute() or "\x00" in os.fspath(token_file):
            raise RelayRuntimeError("RUNTIME_INVALID")
        object.__setattr__(self, "token_file", token_file)

        service_config = ServiceConfig(
            socket_path=socket_path,
            allowed_peer_uids=self.allowed_peer_uids,
            socket_parent_mode=0o710,
            socket_mode=0o660,
            socket_group_gid=os.getegid(),
        )
        object.__setattr__(self, "socket_path", service_config.socket_path)
        DialoguePolicy(
            workspace_id=self.workspace_id,
            channel_id=self.channel_id,
            relay_bot_user_id=self.bot_user_id,
            allowed_sol_user_ids=self.allowed_sol_user_ids,
            allowed_parent_user_ids=self.allowed_parent_user_ids,
        )


@dataclass(frozen=True)
class RelayTurnCandidate:
    """One host-owned input snapshot for a bounded turn-observation pass.

    The candidate carries only source-owner facts needed to re-resolve the
    exact current worker. The observer context and routing namespace are
    derived from the accepted WP-3 result and canonical target owners inside
    :class:`AgentRelayTurnRuntime`; callers cannot author parallel identity
    or routing facts.

    A completed Attempt is never silently treated as a current BUSY worker.
    Its optional evidence group must contain both protected R2 objects and is
    independently revalidated by a trusted Runtime resolver before observation.
    """

    delegation_identity: ExecutiveDelegationIdentity
    dialogue_parent: Mapping[str, Any]
    thread_ts: str
    current_worker: CurrentWorkerDialogueSnapshot | None
    actor: WorkerDialogueCaller | None
    terminal_candidate: TerminalReturnCandidate | None = None
    terminal_projection_receipt: TerminalReturnProjectionReceipt | None = None


_CandidateSource = Callable[
    [],
    Union[
        Awaitable[AsyncIterator[RelayTurnCandidate]],
        AsyncIterator[RelayTurnCandidate],
        tuple[RelayTurnCandidate, ...],
    ],
]


class _FrozenCandidateIterator:
    """Async view over one constructor-time immutable compatibility snapshot."""

    def __init__(self, values: tuple[RelayTurnCandidate, ...]) -> None:
        self._values = values
        self._index = 0

    def __aiter__(self) -> "_FrozenCandidateIterator":
        return self

    async def __anext__(self) -> RelayTurnCandidate:
        if self._index >= len(self._values):
            raise StopAsyncIteration
        value = self._values[self._index]
        self._index += 1
        return value

    async def aclose(self) -> None:
        self._index = len(self._values)


def build_executive_observation_candidate_source(
    engine_v2: DialogueEngineV2,
    observation_client: ExecutiveDialogueObservationClient | object,
    *,
    maximum: int = DEFAULT_MAX_TURN_CANDIDATES_PER_PASS,
) -> Callable[[], Awaitable[AsyncIterator[RelayTurnCandidate]]]:
    """Compose bounded Relay discovery with the Executive read-only listener.

    The engine supplies the existing shared Slack client and accepted parent
    author policy.  Each eligible parent receives exactly one observation
    request.  Typed non-resolution is zero-effect and contributes no candidate;
    the outer collector still owns one absolute pass timeout and cardinality cap.
    """

    if not isinstance(engine_v2, DialogueEngineV2):
        raise TypeError("engine_v2 must be DialogueEngineV2")
    resolve = getattr(observation_client, "resolve", None)
    if not callable(resolve):
        raise TypeError("observation_client must expose resolve")
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not 1 <= maximum <= MAX_TURN_CANDIDATES_PER_PASS
    ):
        raise ValueError("maximum is outside the turn-candidate bound")

    async def source() -> AsyncIterator[RelayTurnCandidate]:
        parents = await engine_v2.discover_validated_parents(maximum=maximum)

        async def observations() -> AsyncIterator[RelayTurnCandidate]:
            for discovered in parents:
                try:
                    resolved = await resolve(
                        parent=discovered.parent,
                        thread_ts=discovered.thread_ts,
                    )
                except ExecutiveObservationClientError:
                    continue
                if (
                    type(resolved) is not ResolvedDialogueObservation
                    or resolved.state != "RESOLVED"
                    or resolved.dialogue_parent != discovered.parent
                    or resolved.thread_ts != discovered.thread_ts
                ):
                    raise ExecutiveObservationClientError("RESPONSE_REFUSED")
                yield RelayTurnCandidate(
                    delegation_identity=resolved.delegation_identity,
                    dialogue_parent=discovered.parent,
                    thread_ts=discovered.thread_ts,
                    current_worker=resolved.current_worker,
                    actor=resolved.actor,
                    terminal_candidate=resolved.terminal_candidate,
                    terminal_projection_receipt=(
                        resolved.terminal_projection_receipt
                    ),
                )

        return observations()

    return source


def _normalize_candidate_source(
    source: object,
) -> Callable[[], Awaitable[AsyncIterator[RelayTurnCandidate]]]:
    """Require an async live source or freeze one legacy tuple before serving.

    The compatibility branch exists only for callers that already materialize
    an exact immutable tuple during composition. It is evaluated once before
    the long-running Relay tasks start; no synchronous callback executes in a
    collection pass. Every dynamic/live source must be an async callable and
    is acquired under :class:`AsyncCandidateCollector`'s one absolute timeout.
    """

    source_call = getattr(source, "__call__", None)
    if inspect.iscoroutinefunction(source) or inspect.iscoroutinefunction(
        source_call
    ):
        return source  # type: ignore[return-value]
    if inspect.isasyncgenfunction(source) or inspect.isasyncgenfunction(
        source_call
    ):

        async def async_generator_source() -> AsyncIterator[RelayTurnCandidate]:
            return source()  # type: ignore[operator, no-any-return]

        return async_generator_source
    if not callable(source):
        raise TypeError("candidate_source must be an async callable")
    try:
        snapshot = source()
    except Exception as exc:
        captured = exc

        async def unavailable_source() -> AsyncIterator[RelayTurnCandidate]:
            raise captured

        return unavailable_source
    if type(snapshot) is not tuple:
        raise TypeError("candidate_source must be an async callable")
    frozen = tuple(snapshot)

    async def frozen_source() -> AsyncIterator[RelayTurnCandidate]:
        return _FrozenCandidateIterator(frozen)

    return frozen_source


class AgentRelayTurnRuntime:
    """Recompute trusted routing and invoke the existing observer in-process."""

    def __init__(
        self,
        *,
        observer: DialogueTurnObserver,
        registry: SessionTargetRegistry,
        current_binding_for: Callable[[str], RuntimeBinding | None],
        candidate_source: _CandidateSource,
        poll_interval_seconds: float = 1.0,
        max_candidates_per_pass: int = DEFAULT_MAX_TURN_CANDIDATES_PER_PASS,
        candidate_collection_timeout_seconds: float = (
            DEFAULT_TURN_CANDIDATE_COLLECTION_TIMEOUT_SECONDS
        ),
        active_waiter_registry: ActiveWaiterRegistry | None = None,
        active_waiter_context: ContextVar[
            _ActiveWaiterLookupContext | None
        ] | None = None,
        dialogue_engine_v2: DialogueEngineV2 | None = None,
        terminal_binding_resolver: TerminalReturnBindingResolver | None = None,
        _executive_observation_source: bool = False,
    ) -> None:
        if not hasattr(observer, "reconcile_once"):
            raise TypeError("observer must expose reconcile_once")
        if not isinstance(registry, SessionTargetRegistry):
            raise TypeError("registry must be SessionTargetRegistry")
        if not callable(current_binding_for):
            raise TypeError("current_binding_for must be callable")
        if not callable(candidate_source):
            raise TypeError("candidate_source must be callable")
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or poll_interval_seconds <= 0
        ):
            raise ValueError("poll_interval_seconds must be positive")
        if (
            isinstance(max_candidates_per_pass, bool)
            or not isinstance(max_candidates_per_pass, int)
            or not 1
            <= max_candidates_per_pass
            <= MAX_TURN_CANDIDATES_PER_PASS
        ):
            raise ValueError(
                "max_candidates_per_pass must be an integer between 1 and "
                f"{MAX_TURN_CANDIDATES_PER_PASS}"
            )

        self.observer = observer
        self.registry = registry
        self._current_binding_for = current_binding_for
        self._candidate_collector = AsyncCandidateCollector(
            source=_normalize_candidate_source(candidate_source),
            max_candidates=max_candidates_per_pass,
            timeout_seconds=candidate_collection_timeout_seconds,
        )
        self._poll_interval_seconds = float(poll_interval_seconds)
        if (
            not isinstance(active_waiter_registry, ActiveWaiterRegistry)
            or not isinstance(active_waiter_context, ContextVar)
            or not isinstance(dialogue_engine_v2, DialogueEngineV2)
            or dialogue_engine_v2.active_waiter_registry
            is not active_waiter_registry
            or not callable(getattr(terminal_binding_resolver, "resolve", None))
        ):
            # AgentRelayTurnRuntime *is* the enabled W3C overlay.  Unlike an
            # ordinary standalone DialogueEngineV2 it has no compatibility
            # mode without the exact process-local waiter owner and terminal
            # authority seam.
            raise RelayRuntimeError("RUNTIME_INVALID")
        self.active_waiter_registry = active_waiter_registry
        self._active_waiter_context = active_waiter_context
        self._dialogue_engine_v2 = dialogue_engine_v2
        self._terminal_binding_resolver = terminal_binding_resolver
        if type(_executive_observation_source) is not bool:
            raise RelayRuntimeError("RUNTIME_INVALID")
        self._executive_observation_source = _executive_observation_source

    @staticmethod
    def _receipt(
        outcome: ObservationOutcome,
        reason: str,
    ) -> ObservationReceipt:
        return ObservationReceipt(
            outcome=outcome,
            reason=reason,
            decision=None,
            obligation=None,
            route=None,
        )

    async def _observe(
        self,
        *,
        context: DialogueContextV2,
        routing: object,
    ) -> ObservationReceipt:
        scope = self._active_waiter_context
        engine = self._dialogue_engine_v2
        active_waiters = self.active_waiter_registry
        if (
            not isinstance(scope, ContextVar)
            or not isinstance(engine, DialogueEngineV2)
            or not isinstance(active_waiters, ActiveWaiterRegistry)
            or engine.active_waiter_registry is not active_waiters
        ):
            raise ActiveWaiterStateUnavailable()
        try:
            parent_fingerprint = routing.bound_commission_fingerprint
        except AttributeError:
            raise ActiveWaiterStateUnavailable() from None
        if not isinstance(parent_fingerprint, str) or not parent_fingerprint:
            raise ActiveWaiterStateUnavailable()
        token = scope.set(
            _ActiveWaiterLookupContext(
                # Routing is the immutable accepted owner projection.  The
                # candidate mapping remains untrusted and may be mutable while
                # terminal Slack verification awaits transport reads.
                parent_fingerprint=parent_fingerprint,
                operation_key=context.operation_key,
                session_ref=context.session_ref,
            )
        )
        try:
            return await self.observer.reconcile_once(
                context=context,
                routing=routing,
            )
        finally:
            scope.reset(token)

    @staticmethod
    def _context_from_binding(binding: object) -> DialogueContextV2:
        """Derive the observer context only from the accepted WP-3 binding."""

        try:
            return DialogueContextV2(
                work_ref=binding.work_ref,
                commission_ref=binding.commission_ref,
                session_ref=binding.session_ref,
                operation_key=binding.operation_key,
                watch_mode=binding.watch_mode,
                actor_ref=binding.actor_ref,
                applies_to=binding.applies_to,
            )
        except (AttributeError, TypeError, ValueError):
            raise TurnRoutingFactsError("DIALOGUE_BINDING_MISMATCH") from None

    def _terminal_snapshot_from_observation(
        self,
        candidate: RelayTurnCandidate,
    ) -> CurrentWorkerDialogueSnapshot | None:
        """Adapt revalidated terminal facts to the existing terminal router.

        Terminal routing consumes only the completed identity/status and parent
        fields from this compatibility shape.  Its RuntimeBinding is a fresh
        public COO target read; no active-worker or provider claim is inferred.
        """

        terminal = candidate.terminal_candidate
        if (
            type(terminal) is not TerminalReturnCandidate
            or not self._executive_observation_source
        ):
            return None
        try:
            runtime_binding = self._current_binding_for("coo")
        except Exception:
            return None
        if not isinstance(runtime_binding, RuntimeBinding):
            return None
        from integrations.mastermind_company_mcp.schemas import (
            SERVER_IDENTITY,
            SERVER_VERSION,
            TOOL_SCHEMA_DIGEST,
        )

        return CurrentWorkerDialogueSnapshot(
            root_job_id=terminal.root_job_id,
            job_id=terminal.job_id,
            attempt_id=terminal.attempt_id,
            worker_id=terminal.worker_id,
            attempt_status=AttemptStatus.COMPLETED,
            worker_status=WorkerStatus.AVAILABLE,
            execution_profile_id="executive-terminal",
            execution_profile_digest=terminal.effective_grant_digest,
            capability_policy_digest=terminal.effective_grant_digest,
            runtime_binding=runtime_binding,
            parent_fingerprint=str(candidate.dialogue_parent.get("fingerprint", "")),
            company_dialogue_server_identity=SERVER_IDENTITY,
            company_dialogue_server_version=SERVER_VERSION,
            company_dialogue_tool_schema_digest=TOOL_SCHEMA_DIGEST,
            company_dialogue_attested=True,
        )

    @staticmethod
    def _terminal_binding_from_executive_observation(
        candidate: RelayTurnCandidate,
    ) -> ResolvedTerminalReturnBinding | None:
        """Adapt only an Executive-resolved candidate into the existing router."""

        terminal = candidate.terminal_candidate
        if type(terminal) is not TerminalReturnCandidate:
            return None
        source = terminal.dialogue_source
        if not isinstance(source, ExecutiveDialogueSource):
            return None
        try:
            commission_ref = source.commission_ref.to_dict()
            return ResolvedTerminalReturnBinding(
                work_ref=source.work_ref,
                commission_ref=commission_ref,
                session_ref=terminal.session_ref,
                operation_key=terminal.operation_key,
                watch_mode=source.watch_mode,
                actor_ref={
                    "kind": "worker_attempt",
                    "job_id": terminal.job_id,
                    "attempt_id": terminal.attempt_id,
                    "worker_id": terminal.worker_id,
                },
                applies_to={
                    "kind": "executive_attempt",
                    "job_id": terminal.job_id,
                    "attempt_id": terminal.attempt_id,
                    "worker_id": terminal.worker_id,
                },
            )
        except (AttributeError, TypeError, ValueError):
            return None

    async def _reconcile_terminal_candidate(
        self,
        candidate: RelayTurnCandidate,
    ) -> ObservationReceipt:
        current_worker = candidate.current_worker
        terminal = candidate.terminal_candidate
        receipt = candidate.terminal_projection_receipt
        resolver = self._terminal_binding_resolver
        engine = self._dialogue_engine_v2
        if current_worker is None:
            current_worker = self._terminal_snapshot_from_observation(candidate)
        if (
            type(current_worker) is not CurrentWorkerDialogueSnapshot
            or type(terminal) is not TerminalReturnCandidate
            or type(receipt) is not TerminalReturnProjectionReceipt
            or resolver is None
            or engine is None
        ):
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
            )
        resolved = (
            self._terminal_binding_from_executive_observation(candidate)
            if self._executive_observation_source
            else None
        )
        if resolved is None and not self._executive_observation_source:
            try:
                resolved = resolver.resolve(terminal)
            except Exception:
                return self._receipt(
                    ObservationOutcome.RECONCILIATION_INCOMPLETE,
                    "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
                )
        if type(resolved) is not ResolvedTerminalReturnBinding:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TERMINAL_RESULT_BINDING_MISMATCH",
            )

        try:
            context = self._context_from_binding(resolved)
            expected_message = build_terminal_result_message(
                terminal,
                context.normalized(),
            )
            if (
                receipt.message_key != expected_message["message_key"]
                or receipt.fingerprint != expected_message["fingerprint"]
                or receipt.parent_author_user_id
                != engine.policy.relay_bot_user_id
            ):
                raise TurnRoutingFactsError(
                    "TERMINAL_RESULT_RECEIPT_MISMATCH"
                )
            routing = resolve_terminal_turn_routing_facts(
                delegation_identity=candidate.delegation_identity,
                dialogue_parent=candidate.dialogue_parent,
                thread_ts=candidate.thread_ts,
                current_worker=current_worker,
                terminal_candidate=terminal,
                projection_receipt=receipt,
                resolved_binding=resolved,
                registry=self.registry,
                current_binding_for=self._current_binding_for,
            )
        except TurnRoutingFactsError as exc:
            return self._receipt(ObservationOutcome.REFUSED, exc.code)
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TERMINAL_RESULT_BINDING_MISMATCH",
            )

        try:
            bound = await engine.bind_or_verify_relay_parent_thread(context)
            if (
                bound.thread_ts != candidate.thread_ts
                or bound.thread_ts != receipt.thread_ts
                or bound.parent_fingerprint != receipt.parent_fingerprint
                or bound.parent_fingerprint
                != candidate.dialogue_parent["fingerprint"]
                or bound.parent_author_user_id != receipt.parent_author_user_id
                or bound.parent_author_user_id != engine.policy.relay_bot_user_id
            ):
                raise ValueError("receipt does not bind canonical parent")
            physical = await engine.read_thread(
                thread_ts=candidate.thread_ts,
                context=context,
            )
            matches = [
                item
                for item in physical.messages
                if item.message["message_key"] == receipt.message_key
            ]
            if len(matches) != 1:
                raise ValueError("terminal result is absent or ambiguous")
            observed = matches[0]
            if (
                dict(observed.message) != expected_message
                or observed.primary_ts != receipt.message_ts
                or observed.duplicate_timestamps != receipt.duplicate_timestamps
            ):
                raise ValueError("physical terminal result drifted")
        except DialogueEngineError as exc:
            if exc.code in {
                "TRANSPORT_UNAVAILABLE",
                "THREAD_HISTORY_INCOMPLETE",
                "THREAD_RECONCILIATION_INCOMPLETE",
            }:
                return self._receipt(
                    ObservationOutcome.RECONCILIATION_INCOMPLETE,
                    "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
                )
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TERMINAL_RESULT_RECEIPT_MISMATCH",
            )
        except (KeyError, TypeError, ValueError):
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TERMINAL_RESULT_RECEIPT_MISMATCH",
            )
        except Exception:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
            )

        try:
            return await self._observe(
                context=context,
                routing=routing,
            )
        except ActiveWaiterStateUnavailable:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "ACTIVE_WAITER_STATE_UNAVAILABLE",
            )
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_OBSERVER_UNAVAILABLE",
            )

    async def _reconcile_candidate_inner(
        self,
        candidate: object,
    ) -> ObservationReceipt:
        if not isinstance(candidate, RelayTurnCandidate):
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_CANDIDATE_INVALID",
            )

        current_worker = candidate.current_worker
        terminal_evidence_count = sum(
            value is not None
            for value in (
                candidate.terminal_candidate,
                candidate.terminal_projection_receipt,
            )
        )
        if terminal_evidence_count == 1:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
            )
        if terminal_evidence_count == 2 and (
            (
                isinstance(current_worker, CurrentWorkerDialogueSnapshot)
                and current_worker.attempt_status is AttemptStatus.COMPLETED
            )
            or (
                current_worker is None
                and self._executive_observation_source
            )
        ):
            return await self._reconcile_terminal_candidate(candidate)
        if (
            isinstance(current_worker, CurrentWorkerDialogueSnapshot)
            and current_worker.attempt_status is AttemptStatus.COMPLETED
        ):
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "TERMINAL_RESULT_POST_BINDING_UNAVAILABLE",
            )
        if terminal_evidence_count:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_CANDIDATE_MODE_CONFLICT",
            )

        resolution = resolve_company_dialogue_binding(
            delegation_identity=candidate.delegation_identity,
            dialogue_parent=candidate.dialogue_parent,
            thread_ts=candidate.thread_ts,
            current=current_worker,
            actor=candidate.actor,
        )
        if resolution.state is not BindingState.RESOLVED or resolution.binding is None:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "CURRENT_WORKER_REFUSED:"
                f"{resolution.state.value}/{resolution.reason.value}",
            )

        assert current_worker is not None
        try:
            context = self._context_from_binding(resolution.binding)
            routing = resolve_turn_routing_facts(
                dialogue_parent=candidate.dialogue_parent,
                current_worker=current_worker,
                binding_resolution=resolution,
                registry=self.registry,
                current_binding_for=self._current_binding_for,
            )
        except TurnRoutingFactsError as exc:
            return self._receipt(ObservationOutcome.REFUSED, exc.code)
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_ROUTING_FACTS_INVALID",
            )

        try:
            return await self._observe(
                context=context,
                routing=routing,
            )
        except ActiveWaiterStateUnavailable:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "ACTIVE_WAITER_STATE_UNAVAILABLE",
            )
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_OBSERVER_UNAVAILABLE",
            )

    async def _reconcile_candidate(
        self,
        candidate: object,
    ) -> ObservationReceipt:
        try:
            return await self._reconcile_candidate_inner(candidate)
        except asyncio.CancelledError:
            raise
        except ActiveWaiterStateUnavailable:
            return self._receipt(
                ObservationOutcome.RECONCILIATION_INCOMPLETE,
                "ACTIVE_WAITER_STATE_UNAVAILABLE",
            )
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_CANDIDATE_PROCESSING_FAILED",
            )

    async def reconcile_once(self) -> tuple[ObservationReceipt, ...]:
        try:
            collected = await self._candidate_collector.collect()
        except CandidateCollectionUnavailable:
            return (
                self._receipt(
                    ObservationOutcome.REFUSED,
                    "TURN_CANDIDATE_SOURCE_UNAVAILABLE",
                ),
            )
        except CandidateCollectionTimeout:
            return (
                self._receipt(
                    ObservationOutcome.REFUSED,
                    "TURN_CANDIDATE_COLLECTION_TIMEOUT",
                ),
            )
        except CandidateCollectionOverflow:
            return (
                self._receipt(
                    ObservationOutcome.REFUSED,
                    "TURN_CANDIDATE_LIMIT_EXCEEDED",
                ),
            )
        except CandidateCollectionBusy:
            return (
                self._receipt(
                    ObservationOutcome.REFUSED,
                    "TURN_CANDIDATE_COLLECTION_INFLIGHT",
                ),
            )

        receipts: list[ObservationReceipt] = []
        for candidate in collected:
            receipts.append(await self._reconcile_candidate(candidate))
        return tuple(receipts)

    async def serve_forever(self) -> None:
        while True:
            try:
                await self.reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # The optional data-plane overlay cannot terminate the accepted
                # AF_UNIX dialogue service. The next bounded pass recomputes.
                pass
            await asyncio.sleep(self._poll_interval_seconds)


def read_private_token_file(path: str | Path) -> str:
    """Read one exact owner-only regular inode without following a final symlink."""

    token_path = Path(path)
    try:
        before = token_path.lstat()
    except OSError:
        raise RelayRuntimeError("TOKEN_FILE_UNAVAILABLE") from None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RelayRuntimeError("TOKEN_FILE_UNSAFE")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(token_path, flags)
        info = os.fstat(descriptor)
        if (
            info.st_dev != before.st_dev
            or info.st_ino != before.st_ino
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or info.st_gid != os.getegid()
            or stat.S_IMODE(info.st_mode) != 0o400
        ):
            raise RelayRuntimeError("TOKEN_FILE_UNSAFE")
        raw = os.read(descriptor, _TOKEN_MAX_BYTES + 1)
        if not raw or len(raw) > _TOKEN_MAX_BYTES:
            raise RelayRuntimeError("TOKEN_FILE_INVALID")
    except RelayRuntimeError:
        raise
    except OSError:
        raise RelayRuntimeError("TOKEN_FILE_UNSAFE") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    try:
        token = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise RelayRuntimeError("TOKEN_FILE_INVALID") from None
    if token.endswith("\n"):
        token = token[:-1]
    if not token or any(character.isspace() for character in token):
        raise RelayRuntimeError("TOKEN_FILE_INVALID")
    return token


def build_service(
    config: RelayRuntimeConfig,
    *,
    transport: SlackHttpTransport | None = None,
) -> AgentDialogueService:
    """Compose the accepted engines and service around one startup-bound client."""

    token = read_private_token_file(config.token_file)
    client = SlackWebApiDialogueClient(
        token=token,
        workspace_id=config.workspace_id,
        channel_id=config.channel_id,
        bot_user_id=config.bot_user_id,
        transport=transport,
    )
    policy = DialoguePolicy(
        workspace_id=config.workspace_id,
        channel_id=config.channel_id,
        relay_bot_user_id=config.bot_user_id,
        allowed_sol_user_ids=config.allowed_sol_user_ids,
        allowed_parent_user_ids=config.allowed_parent_user_ids,
    )
    authority = PrivateRelayAuthorityPolicy()
    active_waiters = ActiveWaiterRegistry()
    return AgentDialogueService(
        ServiceConfig(
            socket_path=config.socket_path,
            allowed_peer_uids=config.allowed_peer_uids,
            socket_parent_mode=0o710,
            socket_mode=0o660,
            socket_group_gid=os.getegid(),
        ),
        DialogueEngine(policy, client, authority_policy=authority),
        engine_v2=DialogueEngineV2(
            policy,
            client,
            authority_policy=authority,
            active_waiter_registry=active_waiters,
        ),
    )


def build_turn_runtime(
    service: AgentDialogueService,
    *,
    registry: SessionTargetRegistry,
    repository: WakeLedgerRepository,
    dispatchers: WakeDispatcherRegistry,
    current_binding_for: Callable[[str], RuntimeBinding | None],
    retry_policy: WakeRetryPolicy,
    candidate_source: _CandidateSource | None = None,
    observation_client: ExecutiveDialogueObservationClient | None = None,
    terminal_binding_resolver: RuntimeTerminalReturnBindingResolver,
    emitted_at: Callable[[], str] = utc_now_iso,
    poll_interval_seconds: float = 1.0,
    max_candidates_per_pass: int = DEFAULT_MAX_TURN_CANDIDATES_PER_PASS,
    candidate_collection_timeout_seconds: float = (
        DEFAULT_TURN_CANDIDATE_COLLECTION_TIMEOUT_SECONDS
    ),
) -> AgentRelayTurnRuntime:
    """Compose the disarmed W3C loop around the already-built relay service."""

    if not isinstance(service, AgentDialogueService):
        raise TypeError("service must be AgentDialogueService")
    if service.engine_v2 is None or service.engine.client is not service.engine_v2.client:
        raise RelayRuntimeError("RUNTIME_INVALID")
    if (candidate_source is None) == (observation_client is None):
        raise RelayRuntimeError("RUNTIME_INVALID")
    if observation_client is not None:
        if (
            not isinstance(observation_client, ExecutiveDialogueObservationClient)
            or observation_client.socket_path != EXECUTIVE_OBSERVATION_SOCKET_PATH
        ):
            raise RelayRuntimeError("RUNTIME_INVALID")
        candidate_source = build_executive_observation_candidate_source(
            service.engine_v2,
            observation_client,
            maximum=max_candidates_per_pass,
        )
    executive_observation_source = observation_client is not None
    # ``candidate_source`` is the protected pre-I1 unit-test compatibility
    # seam.  Production composition supplies ``observation_client`` above.
    assert candidate_source is not None
    active_waiters = service.engine_v2.active_waiter_registry
    if not isinstance(active_waiters, ActiveWaiterRegistry):
        raise RelayRuntimeError("RUNTIME_INVALID")
    if not isinstance(
        terminal_binding_resolver,
        RuntimeTerminalReturnBindingResolver,
    ):
        raise RelayRuntimeError("RUNTIME_INVALID")
    waiter_context: ContextVar[_ActiveWaiterLookupContext | None] = ContextVar(
        f"agent_relay_waiter_context_{id(service):x}",
        default=None,
    )

    def current_for_route(route: WakeRoute) -> RuntimeBinding | None:
        return current_binding_for(route.target_seat)

    def exact_active_waiter(source_ref: str, target_seat: str) -> bool:
        if not isinstance(source_ref, str) or not source_ref:
            raise ActiveWaiterStateUnavailable()
        try:
            scope = waiter_context.get()
            if scope is None:
                raise ActiveWaiterStateUnavailable()
            key = ActiveWaiterKey(
                parent_fingerprint=scope.parent_fingerprint,
                operation_key=scope.operation_key,
                session_ref_canonical=scope.session_ref,
                target_seat=target_seat,
            )
            observed = active_waiters.is_active(key)
        except Exception:
            raise ActiveWaiterStateUnavailable() from None
        if type(observed) is not bool:
            raise ActiveWaiterStateUnavailable()
        return observed

    observer = compose_persisted_turn_observer(
        policy=service.engine.policy,
        client=service.engine.client,
        registry=registry,
        repository=repository,
        dispatchers=dispatchers,
        current_binding_for=current_for_route,
        retry_policy=retry_policy,
        binding_for=current_binding_for,
        has_active_waiter=exact_active_waiter,
        emitted_at=emitted_at,
    )
    return AgentRelayTurnRuntime(
        observer=observer,
        registry=registry,
        current_binding_for=current_binding_for,
        candidate_source=candidate_source,
        poll_interval_seconds=poll_interval_seconds,
        max_candidates_per_pass=max_candidates_per_pass,
        candidate_collection_timeout_seconds=candidate_collection_timeout_seconds,
        active_waiter_registry=active_waiters,
        active_waiter_context=waiter_context,
        dialogue_engine_v2=service.engine_v2,
        terminal_binding_resolver=terminal_binding_resolver,
        _executive_observation_source=executive_observation_source,
    )


async def _contain_turn_overlay(awaitable: object) -> None:
    """Contain an optional W3C overlay failure without stopping Agent Relay."""

    try:
        await awaitable  # type: ignore[misc]
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def run_relay(
    config: RelayRuntimeConfig,
    *,
    turn_runtime_factory: Callable[[AgentDialogueService], Any] | None = None,
) -> None:
    """Run Agent Relay; an injected W3C overlay can never terminate it."""

    service = build_service(config)
    if turn_runtime_factory is None:
        await service.serve_forever()
        return

    try:
        turn_runtime = turn_runtime_factory(service)
        turn_serve = turn_runtime.serve_forever
        if not callable(turn_serve):
            raise TypeError("turn runtime serve_forever is not callable")
        turn_awaitable = turn_serve()
        if not inspect.isawaitable(turn_awaitable):
            raise TypeError("turn runtime serve_forever did not return an awaitable")
    except Exception:
        raise RelayRuntimeError("RUNTIME_INVALID") from None

    service_task = asyncio.create_task(service.serve_forever())
    turn_task = asyncio.create_task(_contain_turn_overlay(turn_awaitable))
    tasks = (service_task, turn_task)
    try:
        await service_task
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the private Agent Relay")
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--bot-user-id", required=True)
    parser.add_argument("--allowed-peer-uid", required=True, type=int, action="append")
    parser.add_argument("--allowed-sol-user-id", required=True, action="append")
    parser.add_argument("--allowed-parent-user-id", required=True, action="append")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        config = RelayRuntimeConfig(
            socket_path=Path(namespace.socket_path),
            token_file=Path(namespace.token_file),
            workspace_id=namespace.workspace_id,
            channel_id=namespace.channel_id,
            bot_user_id=namespace.bot_user_id,
            allowed_peer_uids=tuple(namespace.allowed_peer_uid),
            allowed_sol_user_ids=tuple(namespace.allowed_sol_user_id),
            allowed_parent_user_ids=tuple(namespace.allowed_parent_user_id),
        )
        asyncio.run(run_relay(config))
        return 0
    except KeyboardInterrupt:
        return 0
    except (DialogueServiceError, RelayRuntimeError, ValueError) as exc:
        code = getattr(exc, "code", "RUNTIME_INVALID")
        print(f"agent-relay refused: {code}", file=sys.stderr)
        return 2


__all__ = [
    "AGENT_RELAY_SOCKET_PATH",
    "DEFAULT_MAX_TURN_CANDIDATES_PER_PASS",
    "DEFAULT_TURN_CANDIDATE_COLLECTION_TIMEOUT_SECONDS",
    "EXECUTIVE_CLIENT_UID",
    "EXECUTIVE_OBSERVATION_SOCKET_PATH",
    "MAX_TURN_CANDIDATES_PER_PASS",
    "ActiveWaiterStateUnavailable",
    "AgentRelayTurnRuntime",
    "ObservationOutcome",
    "ObservationReceipt",
    "PrivateRelayAuthorityPolicy",
    "RelayRuntimeConfig",
    "RelayRuntimeError",
    "RelayTurnCandidate",
    "TurnRoutingFactsError",
    "build_service",
    "build_executive_observation_candidate_source",
    "build_turn_runtime",
    "main",
    "read_private_token_file",
    "run_relay",
]
