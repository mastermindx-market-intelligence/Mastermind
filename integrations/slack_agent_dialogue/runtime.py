"""Private long-running Agent Relay composition over the existing AF_UNIX owner.

The runtime owns no dialogue, worker, retry, Wake, queue, or durable lifecycle
state. It reads one host-provisioned token exactly once at startup, injects one
Slack client into the existing V1 and V2 engines, and serves their closed
request surface over one owner-private Unix-domain socket.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from integrations.slack_agent_dialogue.engine import DialogueEngine, DialoguePolicy
from integrations.slack_agent_dialogue.engine_v2 import DialogueEngineV2
from integrations.slack_agent_dialogue.service import (
    AgentDialogueService,
    DialogueServiceError,
    ServiceConfig,
)
from integrations.slack_agent_dialogue.slack_web_api import (
    SlackHttpTransport,
    SlackWebApiDialogueClient,
)

_TOKEN_MAX_BYTES = 2048
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
        token_file = Path(self.token_file)
        if not token_file.is_absolute() or "\x00" in os.fspath(token_file):
            raise RelayRuntimeError("RUNTIME_INVALID")
        object.__setattr__(self, "token_file", token_file)

        service_config = ServiceConfig(
            socket_path=Path(self.socket_path),
            allowed_peer_uids=self.allowed_peer_uids,
        )
        object.__setattr__(self, "socket_path", service_config.socket_path)
        DialoguePolicy(
            workspace_id=self.workspace_id,
            channel_id=self.channel_id,
            relay_bot_user_id=self.bot_user_id,
            allowed_sol_user_ids=self.allowed_sol_user_ids,
            allowed_parent_user_ids=self.allowed_parent_user_ids,
        )


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
        ),
        DialogueEngine(policy, client, authority_policy=authority),
        engine_v2=DialogueEngineV2(policy, client, authority_policy=authority),
    )


async def run_relay(config: RelayRuntimeConfig) -> None:
    """Run until the process is cancelled or terminated by its host supervisor."""

    await build_service(config).serve_forever()


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
    "PrivateRelayAuthorityPolicy",
    "RelayRuntimeConfig",
    "RelayRuntimeError",
    "build_service",
    "main",
    "read_private_token_file",
    "run_relay",
]
