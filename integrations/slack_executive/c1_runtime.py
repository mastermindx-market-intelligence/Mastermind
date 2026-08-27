"""Closed production configuration and startup guards for C1 SOL_STATE.

The production Relay runs under the sealed Executive Python invocation
``-I -S -B``. This module therefore remains standard-library-only apart from
C1-local first-party imports. Production policy is intentionally fixed rather
than request-configurable: one Executive socket, workspace, channel, token path
and 30/60/120 cadence. Only the native action-time bot user identity and the
release-version label vary after qualification.
"""
from __future__ import annotations

import grp
import json
import os
import pwd
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .slack_web_api import (
    SLACK_API_ROOT,
    SlackHttpTransport,
    UrllibSlackHttpTransport,
    decode_slack_json,
)

CONFIG_SCHEMA = "mastermind.sol_state_relay_config.v1"
RELAY_USERNAME = "_mastermind_sol_relay"
REQUIRED_SLACK_SCOPES = ("chat:write", "groups:history")
CONFIG_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/sol-state-relay.json"
)
TOKEN_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/sol-state-relay.token"
)
EXECUTIVE_SOCKET_PATH = Path("/var/run/mastermind-executive/ceo-ingress.sock")
SLACK_WORKSPACE_ID = "T0BRD2AQXQV"
SLACK_CHANNEL_ID = "C0BSGABKBFY"
POLL_SECONDS = 30
HEARTBEAT_SECONDS = 60
MAX_EXECUTIVE_AGE_SECONDS = 120
_CONFIG_MAX_BYTES = 8192
_TOKEN_MAX_BYTES = 2048
_BOT_USER_RE = re.compile(r"^U[A-Z0-9]{8,31}$")
_RELAY_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
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


class _PrivateFileError(RuntimeError):
    pass


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
    scopes: tuple[str, ...]


def _path_has_acl(path: Path, *, expected_info: os.stat_result) -> bool:
    """Inspect macOS ACL marker without trusting a second file identity."""

    if sys.platform != "darwin":
        return False
    try:
        completed = subprocess.run(
            ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        after = path.lstat()
    except (OSError, subprocess.SubprocessError):
        raise _PrivateFileError from None
    if (
        completed.returncode != 0
        or after.st_dev != expected_info.st_dev
        or after.st_ino != expected_info.st_ino
    ):
        raise _PrivateFileError
    return b"+" in completed.stdout


def _read_exact_private_bytes(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int,
    max_bytes: int,
) -> bytes:
    """Open once, no-follow, attest the opened inode, then read bounded bytes."""

    try:
        before = path.lstat()
    except OSError:
        raise _PrivateFileError from None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise _PrivateFileError

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        if (
            info.st_dev != before.st_dev
            or info.st_ino != before.st_ino
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or info.st_gid != expected_gid
            or stat.S_IMODE(info.st_mode) != expected_mode
        ):
            raise _PrivateFileError
        if _path_has_acl(path, expected_info=info):
            raise _PrivateFileError

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 4096))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if not payload or len(payload) > max_bytes:
            raise _PrivateFileError
        return payload
    except _PrivateFileError:
        raise
    except OSError:
        raise _PrivateFileError from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _nonempty_string(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid C1 config: {name}")
    return value.strip()


def load_config(
    path: str | Path,
    *,
    expected_path: str | Path = CONFIG_PATH,
    expected_owner_uid: int = 0,
    expected_group_gid: int | None = None,
) -> C1RuntimeConfig:
    """Load the exact root-owned C1 production policy from one attested inode."""

    config_path = Path(path)
    if config_path != Path(expected_path):
        raise ValueError("invalid C1 config")
    group_gid = os.getegid() if expected_group_gid is None else int(expected_group_gid)
    try:
        raw = _read_exact_private_bytes(
            config_path,
            expected_uid=int(expected_owner_uid),
            expected_gid=group_gid,
            expected_mode=0o440,
            max_bytes=_CONFIG_MAX_BYTES,
        )
        document: Any = json.loads(raw.decode("utf-8"))
    except (_PrivateFileError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("invalid C1 config") from None
    if not isinstance(document, dict) or set(document) != _CONFIG_KEYS:
        raise ValueError("invalid C1 config")
    if document.get("schema") != CONFIG_SCHEMA:
        raise ValueError("invalid C1 config: schema")

    bot_user_id = _nonempty_string(
        document.get("slack_bot_user_id"), name="slack_bot_user_id"
    )
    relay_version = _nonempty_string(
        document.get("relay_version"), name="relay_version"
    )
    if _BOT_USER_RE.fullmatch(bot_user_id) is None:
        raise ValueError("invalid C1 config: slack_bot_user_id")
    if _RELAY_VERSION_RE.fullmatch(relay_version) is None:
        raise ValueError("invalid C1 config: relay_version")

    expected = {
        "executive_socket": os.fspath(EXECUTIVE_SOCKET_PATH),
        "slack_workspace_id": SLACK_WORKSPACE_ID,
        "slack_channel_id": SLACK_CHANNEL_ID,
        "slack_token_file": os.fspath(TOKEN_PATH),
        "poll_seconds": POLL_SECONDS,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "max_executive_age_seconds": MAX_EXECUTIVE_AGE_SECONDS,
    }
    if any(document.get(key) != value for key, value in expected.items()):
        raise ValueError("invalid C1 config: fixed policy")

    return C1RuntimeConfig(
        executive_socket=EXECUTIVE_SOCKET_PATH,
        slack_workspace_id=SLACK_WORKSPACE_ID,
        slack_channel_id=SLACK_CHANNEL_ID,
        slack_bot_user_id=bot_user_id,
        slack_token_file=TOKEN_PATH,
        poll_seconds=POLL_SECONDS,
        heartbeat_seconds=HEARTBEAT_SECONDS,
        max_executive_age_seconds=MAX_EXECUTIVE_AGE_SECONDS,
        relay_version=relay_version,
    )


def assert_relay_principal() -> None:
    """Fail closed unless the process is the exact dedicated non-root Relay."""

    try:
        euid = os.geteuid()
        if euid == 0:
            raise RuntimeError("C1_RELAY_PRINCIPAL_REFUSED")
        account = pwd.getpwuid(euid)
        if account.pw_name != RELAY_USERNAME:
            raise RuntimeError("C1_RELAY_PRINCIPAL_REFUSED")
        gids = set(os.getgroups()) | {account.pw_gid}
        group_names = {grp.getgrgid(gid).gr_name for gid in gids}
    except RuntimeError:
        raise
    except (KeyError, OSError):
        raise RuntimeError("C1_RELAY_PRINCIPAL_REFUSED") from None

    forbidden = {
        name
        for name in group_names
        if name.startswith("_mastermind_worker")
        or name.startswith("_mastermind_codex")
        or name in {"_mastermind_exec", "_mastermind_ops"}
    }
    if forbidden:
        raise RuntimeError("C1_RELAY_PRINCIPAL_REFUSED")


def read_token_file(
    path: str | Path,
    *,
    expected_path: str | Path = TOKEN_PATH,
) -> str:
    """Read the exact private credential inode without a path-reopen race."""

    token_path = Path(path)
    if token_path != Path(expected_path):
        raise RuntimeError("C1_TOKEN_FILE_UNSAFE")
    try:
        token_path.lstat()
    except OSError:
        raise RuntimeError("C1_TOKEN_FILE_UNAVAILABLE") from None
    try:
        raw = _read_exact_private_bytes(
            token_path,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
            expected_mode=0o400,
            max_bytes=_TOKEN_MAX_BYTES,
        )
        token = raw.decode("utf-8").strip()
    except _PrivateFileError:
        raise RuntimeError("C1_TOKEN_FILE_UNSAFE") from None
    except UnicodeDecodeError:
        raise RuntimeError("C1_TOKEN_FILE_INVALID") from None
    if not token or "\n" in token or "\r" in token or any(ch.isspace() for ch in token):
        raise RuntimeError("C1_TOKEN_FILE_INVALID")
    return token


def _parse_scope_header(headers: Mapping[str, str]) -> tuple[str, ...]:
    raw = headers.get("x-oauth-scopes")
    if not isinstance(raw, str):
        raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not values or len(values) != len(set(values)):
        raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
    normalized = tuple(sorted(values))
    if normalized != REQUIRED_SLACK_SCOPES:
        raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
    return REQUIRED_SLACK_SCOPES


async def verify_slack_identity(
    *,
    token: str,
    expected_workspace_id: str,
    expected_bot_user_id: str,
    transport: SlackHttpTransport | None = None,
) -> SlackIdentityReceipt:
    """Qualify credential identity and exact least-privilege scope set."""

    if (
        not token
        or expected_workspace_id != SLACK_WORKSPACE_ID
        or _BOT_USER_RE.fullmatch(expected_bot_user_id or "") is None
    ):
        raise ValueError("invalid C1 Slack identity inputs")
    client = transport or UrllibSlackHttpTransport()
    try:
        try:
            response = await client.request(
                method="POST",
                path="auth.test",
                token=token,
            )
        except Exception:
            raise RuntimeError("C1_SLACK_IDENTITY_UNAVAILABLE") from None
        if (
            response.status_code != 200
            or response.final_url != SLACK_API_ROOT + "auth.test"
        ):
            raise RuntimeError("C1_SLACK_IDENTITY_UNAVAILABLE")
        try:
            payload = decode_slack_json(response)
        except RuntimeError:
            raise RuntimeError("C1_SLACK_IDENTITY_REFUSED") from None
        if payload.get("ok") is not True:
            raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
        workspace_id = payload.get("team_id")
        bot_user_id = payload.get("user_id")
        if (
            workspace_id != SLACK_WORKSPACE_ID
            or bot_user_id != expected_bot_user_id
        ):
            raise RuntimeError("C1_SLACK_IDENTITY_REFUSED")
        scopes = _parse_scope_header(response.headers)
        return SlackIdentityReceipt(
            workspace_id=SLACK_WORKSPACE_ID,
            bot_user_id=expected_bot_user_id,
            scopes=scopes,
        )
    finally:
        await client.aclose()


__all__ = [
    "CONFIG_PATH",
    "CONFIG_SCHEMA",
    "C1RuntimeConfig",
    "EXECUTIVE_SOCKET_PATH",
    "HEARTBEAT_SECONDS",
    "MAX_EXECUTIVE_AGE_SECONDS",
    "POLL_SECONDS",
    "RELAY_USERNAME",
    "REQUIRED_SLACK_SCOPES",
    "SLACK_CHANNEL_ID",
    "SLACK_WORKSPACE_ID",
    "TOKEN_PATH",
    "SlackIdentityReceipt",
    "assert_relay_principal",
    "load_config",
    "read_token_file",
    "verify_slack_identity",
]
