"""Private long-running Agent Relay composition over the existing AF_UNIX owner.

The runtime owns no dialogue, worker, retry, Wake, queue, or durable lifecycle
state. It reads one host-provisioned token exactly once at startup, injects one
Slack client into the existing V1 and V2 engines, and serves their closed
request surface over one group-reachable, peer-credentialled Unix socket.

W3C adds only an optional, production-disarmed in-process turn loop. The loop
recomputes exact-current-worker and target bindings on every pass and delegates
all history, Wake persistence, retry, and provider effects to existing owners.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import os
import stat
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.executive_delegation_identity import ExecutiveDelegationIdentity
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
from integrations.slack_agent_dialogue.engine import DialogueEngine, DialoguePolicy
from integrations.slack_agent_dialogue.engine_v2 import (
    DialogueContextV2,
    DialogueEngineV2,
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
    resolve_turn_routing_facts,
)
from integrations.slack_agent_dialogue.wake_projection import (
    compose_persisted_turn_observer,
)

_TOKEN_MAX_BYTES = 2048
AGENT_RELAY_SOCKET_PATH = Path("/var/run/mastermind-agent-relay/agent-relay.sock")
EXECUTIVE_CLIENT_UID = 450
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
    """One host-owned input snapshot for a bounded turn-observation pass."""

    context: DialogueContextV2
    delegation_identity: ExecutiveDelegationIdentity
    dialogue_parent: Mapping[str, Any]
    thread_ts: str
    current_worker: CurrentWorkerDialogueSnapshot | None
    actor: WorkerDialogueCaller
    routing_workstream: str | None = None


class AgentRelayTurnRuntime:
    """Recompute trusted routing and invoke the existing observer in-process."""

    def __init__(
        self,
        *,
        observer: DialogueTurnObserver,
        registry: SessionTargetRegistry,
        current_binding_for: Callable[[str], RuntimeBinding | None],
        candidate_source: Callable[[], Iterable[RelayTurnCandidate]],
        poll_interval_seconds: float = 1.0,
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

        self.observer = observer
        self.registry = registry
        self._current_binding_for = current_binding_for
        self._candidate_source = candidate_source
        self._poll_interval_seconds = float(poll_interval_seconds)

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

    @staticmethod
    def _trusted_workstream(value: str | None) -> str | None:
        if value is None:
            return None
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 200
            or any(ord(character) < 32 for character in value)
        ):
            raise TurnRoutingFactsError("DIALOGUE_BINDING_MISMATCH")
        return value

    async def _reconcile_candidate(
        self,
        candidate: RelayTurnCandidate,
    ) -> ObservationReceipt:
        if not isinstance(candidate, RelayTurnCandidate):
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_CANDIDATE_INVALID",
            )

        resolution = resolve_company_dialogue_binding(
            delegation_identity=candidate.delegation_identity,
            dialogue_parent=candidate.dialogue_parent,
            thread_ts=candidate.thread_ts,
            current=candidate.current_worker,
            actor=candidate.actor,
        )
        if resolution.state is not BindingState.RESOLVED or resolution.binding is None:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "CURRENT_WORKER_REFUSED:"
                f"{resolution.state.value}/{resolution.reason.value}",
            )

        assert candidate.current_worker is not None
        try:
            routing = resolve_turn_routing_facts(
                dialogue_parent=candidate.dialogue_parent,
                current_worker=candidate.current_worker,
                binding_resolution=resolution,
                registry=self.registry,
                current_binding_for=self._current_binding_for,
            )
            routing_workstream = self._trusted_workstream(
                candidate.routing_workstream
            )
            if routing_workstream is not None:
                routing = dataclasses.replace(
                    routing,
                    routing_workstream=routing_workstream,
                )
        except TurnRoutingFactsError as exc:
            return self._receipt(ObservationOutcome.REFUSED, exc.code)
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_ROUTING_FACTS_INVALID",
            )

        try:
            return await self.observer.reconcile_once(
                context=candidate.context,
                routing=routing,
            )
        except Exception:
            return self._receipt(
                ObservationOutcome.REFUSED,
                "TURN_OBSERVER_UNAVAILABLE",
            )

    async def reconcile_once(self) -> tuple[ObservationReceipt, ...]:
        try:
            candidates = tuple(self._candidate_source())
        except Exception:
            return (
                self._receipt(
                    ObservationOutcome.REFUSED,
                    "TURN_CANDIDATE_SOURCE_UNAVAILABLE",
                ),
            )

        receipts: list[ObservationReceipt] = []
        for candidate in candidates:
            receipts.append(await self._reconcile_candidate(candidate))
        return tuple(receipts)

    async def serve_forever(self) -> None:
        while True:
            await self.reconcile_once()
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
    return AgentDialogueService(
        ServiceConfig(
            socket_path=config.socket_path,
            allowed_peer_uids=config.allowed_peer_uids,
            socket_parent_mode=0o710,
            socket_mode=0o660,
            socket_group_gid=os.getegid(),
        ),
        DialogueEngine(policy, client, authority_policy=authority),
        engine_v2=DialogueEngineV2(policy, client, authority_policy=authority),
    )


def build_turn_runtime(
    service: AgentDialogueService,
    *,
    registry: SessionTargetRegistry,
    repository: WakeLedgerRepository,
    dispatchers: WakeDispatcherRegistry,
    current_binding_for: Callable[[str], RuntimeBinding | None],
    retry_policy: WakeRetryPolicy,
    candidate_source: Callable[[], Iterable[RelayTurnCandidate]],
    has_active_waiter: Callable[[str, str], bool] | None = None,
    emitted_at: Callable[[], str] = utc_now_iso,
    poll_interval_seconds: float = 1.0,
) -> AgentRelayTurnRuntime:
    """Compose the disarmed W3C loop around the already-built relay service."""

    if not isinstance(service, AgentDialogueService):
        raise TypeError("service must be AgentDialogueService")
    if service.engine_v2 is None or service.engine.client is not service.engine_v2.client:
        raise RelayRuntimeError("RUNTIME_INVALID")

    def current_for_route(route: WakeRoute) -> RuntimeBinding | None:
        return current_binding_for(route.target_seat)

    observer = compose_persisted_turn_observer(
        policy=service.engine.policy,
        client=service.engine.client,
        registry=registry,
        repository=repository,
        dispatchers=dispatchers,
        current_binding_for=current_for_route,
        retry_policy=retry_policy,
        binding_for=current_binding_for,
        has_active_waiter=has_active_waiter,
        emitted_at=emitted_at,
    )
    return AgentRelayTurnRuntime(
        observer=observer,
        registry=registry,
        current_binding_for=current_binding_for,
        candidate_source=candidate_source,
        poll_interval_seconds=poll_interval_seconds,
    )


async def run_relay(
    config: RelayRuntimeConfig,
    *,
    turn_runtime_factory: Callable[[AgentDialogueService], Any] | None = None,
) -> None:
    """Run the relay, plus an explicitly injected W3C loop, until cancelled."""

    service = build_service(config)
    if turn_runtime_factory is None:
        await service.serve_forever()
        return

    try:
        turn_runtime = turn_runtime_factory(service)
        turn_serve = turn_runtime.serve_forever
    except Exception:
        raise RelayRuntimeError("RUNTIME_INVALID") from None
    if not callable(turn_serve):
        raise RelayRuntimeError("RUNTIME_INVALID")

    service_task = asyncio.create_task(service.serve_forever())
    turn_task = asyncio.create_task(turn_serve())
    tasks = (service_task, turn_task)
    try:
        done, _pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            await task
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
    "EXECUTIVE_CLIENT_UID",
    "AgentRelayTurnRuntime",
    "ObservationOutcome",
    "ObservationReceipt",
    "PrivateRelayAuthorityPolicy",
    "RelayRuntimeConfig",
    "RelayRuntimeError",
    "RelayTurnCandidate",
    "TurnRoutingFactsError",
    "build_service",
    "build_turn_runtime",
    "main",
    "read_private_token_file",
    "run_relay",
]
