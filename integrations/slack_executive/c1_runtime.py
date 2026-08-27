"""Closed non-secret production configuration for the C1 SOL_STATE Relay.

Secrets never belong in this JSON contract.  The configuration names the
root-managed credential file and the already-owned CeoIngress socket, plus the
fixed Slack workspace/channel/bot identity and reviewed timing bounds.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

CONFIG_SCHEMA = "mastermind.sol_state_relay_config.v1"
SLACK_API_ROOT = "https://slack.com/api/"
_CONFIG_KEYS = frozenset(
    {
        "schema",
        "executive_socket",
        "slack_workspace_id",
        "slack_channel_id",
        "slack_bot_user_id",
        "slack_token_file",
        "poll_seconds",
        "heartbeat_seconds",
        "max_executive_age_seconds",
        "relay_version",
    }
)


@dataclass(frozen=True)
class C1RuntimeConfig:
    executive_socket: Path
    slack_workspace_id: str
    slack_channel_id: str
    slack_bot_user_id: str
    slack_token_file: Path
    poll_seconds: int
    heartbeat_seconds: int
    max_executive_age_seconds: int
    relay_version: str


@dataclass(frozen=True)
class SlackIdentityReceipt:
    workspace_id: str
    bot_user_id: str


def _positive_int(value: Any, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"invalid C1 config: {name}")
    return value


def _nonempty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid C1 config: {name}")
    return value.strip()


def _absolute_path(value: Any, *, name: str) -> Path:
    text = _nonempty_string(value, name=name)
    path = Path(text)
    if not path.is_absolute():
        raise ValueError(f"invalid C1 config: {name}")
    return path


def load_config(path: str | Path) -> C1RuntimeConfig:
    config_path = Path(path)
    try:
        raw = config_path.read_text(encoding="utf-8")
        document: Any = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("invalid C1 config") from None
    if not isinstance(document, dict) or set(document) != _CONFIG_KEYS:
        raise ValueError("invalid C1 config")
    if document.get("schema") != CONFIG_SCHEMA:
        raise ValueError("invalid C1 config: schema")

    config = C1RuntimeConfig(
        executive_socket=_absolute_path(
            document.get("executive_socket"), name="executive_socket"
        ),
        slack_workspace_id=_nonempty_string(
            document.get("slack_workspace_id"), name="slack_workspace_id"
        ),
        slack_channel_id=_nonempty_string(
            document.get("slack_channel_id"), name="slack_channel_id"
        ),
        slack_bot_user_id=_nonempty_string(
            document.get("slack_bot_user_id"), name="slack_bot_user_id"
        ),
        slack_token_file=_absolute_path(
            document.get("slack_token_file"), name="slack_token_file"
        ),
        poll_seconds=_positive_int(document.get("poll_seconds"), name="poll_seconds"),
        heartbeat_seconds=_positive_int(
            document.get("heartbeat_seconds"), name="heartbeat_seconds"
        ),
        max_executive_age_seconds=_positive_int(
            document.get("max_executive_age_seconds"),
            name="max_executive_age_seconds",
        ),
        relay_version=_nonempty_string(
            document.get("relay_version"), name="relay_version"
        ),
    )
    if config.heartbeat_seconds < config.poll_seconds:
        raise ValueError("invalid C1 config: heartbeat_seconds")
    if config.max_executive_age_seconds < config.heartbeat_seconds:
        raise ValueError("invalid C1 config: max_executive_age_seconds")
    return config


def read_token_file(path: str | Path) -> str:
    """Read one private token file without leaking filesystem or secret detail."""

    token_path = Path(path)
    try:
        info = token_path.stat(follow_symlinks=False)
    except OSError:
        raise RuntimeError("C1_TOKEN_FILE_UNAVAILABLE") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise RuntimeError("C1_TOKEN_FILE_UNSAFE")
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        raise RuntimeError("C1_TOKEN_FILE_UNAVAILABLE") from None
    if not token or "\n" in token or "\r" in token:
        raise RuntimeError("C1_TOKEN_FILE_INVALID")
    return token


async def verify_slack_identity(
    *,
    token: str,
    expected_workspace_id: str,
    expected_bot_user_id: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> SlackIdentityReceipt:
    """Qualify the production token against the fixed workspace/bot identity."""

    if not token or not expected_workspace_id or not expected_bot_user_id:
        raise ValueError("invalid C1 Slack identity inputs")
    client = httpx.AsyncClient(
        base_url=SLACK_API_ROOT,
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(10.0),
        follow_redirects=False,
        transport=transport,
    )
    try:
        try:
            response = await client.post("auth.test")
            response.raise_for_status()
        except httpx.HTTPError:
            raise RuntimeError("C1_SLACK_IDENTITY_UNAVAILABLE") from None
        try:
            payload: Any = response.json()
        except ValueError:
            raise RuntimeError("C1_SLACK_IDENTITY_REFUSED") from None
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
        workspace_id = payload.get("team_id")
        bot_user_id = payload.get("user_id")
        if (
            workspace_id != expected_workspace_id
            or bot_user_id != expected_bot_user_id
        ):
            raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
        return SlackIdentityReceipt(
            workspace_id=expected_workspace_id,
            bot_user_id=expected_bot_user_id,
        )
    finally:
        await client.aclose()
