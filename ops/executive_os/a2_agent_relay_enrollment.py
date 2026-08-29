"""Native, production-disarmed enrollment for the private A2 Agent Relay.

The ceremony qualifies one stdin-only Slack bot token, installs the exact
release-bound token/config/launchd files, and stops.  It never provisions an
app or principal and never loads, enables, or starts the service.  The Relay
runs only as the host-prepared dedicated ``_mastermind_agent_relay`` owner;
``_mastermind_exec`` remains the single filesystem-reachable, peer-credential-
checked client. Slack prose conveys no host authority.
"""
from __future__ import annotations

import argparse
import asyncio
import grp
import io
import json
import os
import plistlib
import pwd
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO


_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from integrations.slack_agent_dialogue import metadata_verifier  # noqa: E402
from integrations.slack_agent_dialogue.slack_web_api import (  # noqa: E402
    SlackHttpTransport,
    SlackWebApiDialogueClient,
)
from ops.executive_os import c1_relay_enrollment as c1_enrollment  # noqa: E402


RELAY_USER = "_mastermind_agent_relay"
RELAY_GROUP = "_mastermind_agent_relay"
RELAY_UID = 457
RELAY_GID = 457
EXEC_USER = "_mastermind_exec"
EXEC_UID = 450
EXEC_GID = 450
PLIST_UID = 0
PLIST_GID = 0
RELAY_LABEL = "com.mastermind.executive.agent-relay"
RELAY_HOME = Path("/var/db/mastermind-agent-relay/home")
SYSTEM_ROOT = Path("/Library/Application Support/MastermindExecutive")
SYSTEM_RELEASE_ROOT = SYSTEM_ROOT / "releases"
TOKEN_PATH = SYSTEM_ROOT / "config" / "agent-relay.token"
CONFIG_PATH = SYSTEM_ROOT / "config" / "agent-relay.json"
PLIST_PATH = Path("/Library/LaunchDaemons/com.mastermind.executive.agent-relay.plist")
SOCKET_PATH = Path("/var/run/mastermind-agent-relay/agent-relay.sock")
PYTHON_BINARY = Path(
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
)
SLACK_WORKSPACE_ID = "T0BRD2AQXQV"
SLACK_CHANNEL_ID = "C0BSBM78V1N"
REQUIRED_SCOPES = ("channels:history", "chat:write")
ALLOWED_PEER_UIDS = (EXEC_UID,)
ALLOWED_SOL_USER_IDS = ("U0BRETDUAS2", "U0BSB73JWNL")
ALLOWED_PARENT_USER_IDS = ("U0BRETDUAS2",)
_RELAY_GROUP_MEMBERS = (EXEC_USER,)
_RELEASE_RE = re.compile(r"^[0-9a-f]{40}$")
_PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")

ERROR_CODES = frozenset(
    {
        "A2_ENROLLMENT_ARGUMENTS_REFUSED",
        "A2_ENROLLMENT_CHANNEL_REFUSED",
        "A2_ENROLLMENT_COLLISION",
        "A2_ENROLLMENT_EXISTING_REFUSED",
        "A2_ENROLLMENT_HOST_REFUSED",
        "A2_ENROLLMENT_IDENTITY_REFUSED",
        "A2_ENROLLMENT_INPUT_REFUSED",
        "A2_ENROLLMENT_INTERNAL",
        "A2_ENROLLMENT_ROLLBACK_REFUSED",
        "A2_ENROLLMENT_SECRET_SURFACE_REFUSED",
        "A2_ENROLLMENT_WRITE_REFUSED",
    }
)


class A2EnrollmentError(RuntimeError):
    """One closed caller-visible enrollment refusal."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown A2 enrollment error code")
        super().__init__(code)
        self.code = code


class _OpaqueParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse path
        del message
        raise A2EnrollmentError("A2_ENROLLMENT_ARGUMENTS_REFUSED")


@dataclass
class _CreatedFile:
    path: Path
    descriptor: int
    device: int | None
    inode: int | None


@dataclass(frozen=True)
class _BoundDirectory:
    descriptor: int
    device: int
    inode: int
    relay_gids: frozenset[int]


@dataclass
class _BoundCreatedFile:
    name: str
    descriptor: int
    device: int | None
    inode: int | None


def build_parser() -> argparse.ArgumentParser:
    parser = _OpaqueParser(description="Enroll the private A2 Agent Relay")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("enroll", "verify"):
        child = commands.add_parser(name)
        child.add_argument("--expected-bot-user-id", required=True)
    return parser


def assert_secret_surfaces_clean(
    *, argv: Sequence[str], environ: Mapping[str, str]
) -> None:
    try:
        c1_enrollment.assert_secret_surfaces_clean(argv=argv, environ=environ)
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_SECRET_SURFACE_REFUSED") from None


def read_token_from_stdin(stream: BinaryIO) -> str:
    try:
        return c1_enrollment.read_token_from_stdin(stream)
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_INPUT_REFUSED") from None


def build_config_document(*, bot_user_id: str, release_sha: str) -> dict[str, object]:
    try:
        metadata_verifier.validate_expectation(
            metadata_verifier.MetadataExpectation(
                team_id=SLACK_WORKSPACE_ID,
                bot_user_id=bot_user_id,
                scopes=REQUIRED_SCOPES,
            )
        )
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_ARGUMENTS_REFUSED") from None
    if _RELEASE_RE.fullmatch(release_sha or "") is None:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
    return {
        "schema": "mastermind.agent_relay_enrollment.v1",
        "release_sha": release_sha,
        "slack_workspace_id": SLACK_WORKSPACE_ID,
        "slack_channel_id": SLACK_CHANNEL_ID,
        "slack_bot_user_id": bot_user_id,
        "slack_scopes": list(REQUIRED_SCOPES),
        "slack_token_file": os.fspath(TOKEN_PATH),
        "relay_socket_path": os.fspath(SOCKET_PATH),
        "relay_user": RELAY_USER,
        "relay_uid": RELAY_UID,
        "allowed_peer_uids": list(ALLOWED_PEER_UIDS),
        "allowed_sol_user_ids": list(ALLOWED_SOL_USER_IDS),
        "allowed_parent_user_ids": list(ALLOWED_PARENT_USER_IDS),
    }


def _replace_placeholders(value: object, replacements: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return replacements.get(value, value)
    if isinstance(value, list):
        return [_replace_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_placeholders(item, replacements)
            for key, item in value.items()
        }
    return value


def render_plist(*, bot_user_id: str, release_sha: str) -> bytes:
    build_config_document(bot_user_id=bot_user_id, release_sha=release_sha)
    release_root = SYSTEM_RELEASE_ROOT / release_sha
    template_path = _ROOT / "ops" / "executive_os" / (
        "com.mastermind.executive.agent-relay.plist.template"
    )
    try:
        template = plistlib.loads(template_path.read_bytes())
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED") from None
    replacements = {
        "__PYTHON_BINARY__": os.fspath(PYTHON_BINARY),
        "__RELAY_ENTRYPOINT__": os.fspath(
            release_root / "scripts" / "slack_agent_dialogue_service.py"
        ),
        "__RELAY_SOCKET_PATH__": os.fspath(SOCKET_PATH),
        "__RELAY_TOKEN_FILE__": os.fspath(TOKEN_PATH),
        "__SLACK_WORKSPACE_ID__": SLACK_WORKSPACE_ID,
        "__SLACK_CHANNEL_ID__": SLACK_CHANNEL_ID,
        "__SLACK_BOT_USER_ID__": bot_user_id,
        "__ALLOWED_PEER_UID__": str(ALLOWED_PEER_UIDS[0]),
        "__ALLOWED_SOL_USER_ID__": ALLOWED_SOL_USER_IDS[0],
        "__ALLOWED_PARENT_USER_ID__": ALLOWED_PARENT_USER_IDS[0],
        "__RELEASE_ROOT__": os.fspath(release_root),
        "__RELAY_USER__": RELAY_USER,
        "__RELAY_GROUP__": RELAY_GROUP,
        "__RELAY_HOME__": os.fspath(RELAY_HOME),
        "__RELAY_STDOUT__": "/var/log/mastermind-executive/agent-relay.stdout.log",
        "__RELAY_STDERR__": "/var/log/mastermind-executive/agent-relay.stderr.log",
    }
    document = _replace_placeholders(template, replacements)
    try:
        arguments = document["ProgramArguments"]  # type: ignore[index]
        sol_index = arguments.index("--allowed-sol-user-id")
        arguments[sol_index : sol_index + 2] = [
            value
            for user_id in ALLOWED_SOL_USER_IDS
            for value in ("--allowed-sol-user-id", user_id)
        ]
        encoded = plistlib.dumps(document, fmt=plistlib.FMT_XML, sort_keys=False)
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED") from None
    if _PLACEHOLDER_RE.search(encoded.decode("utf-8")) is not None:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
    return encoded


async def qualify_token(
    *,
    token: str,
    bot_user_id: str,
    identity_transport: metadata_verifier.SlackAuthTestTransport | None = None,
    history_transport: SlackHttpTransport | None = None,
) -> dict[str, object]:
    try:
        identity = metadata_verifier.verify_metadata(
            token=token,
            expectation=metadata_verifier.MetadataExpectation(
                team_id=SLACK_WORKSPACE_ID,
                bot_user_id=bot_user_id,
                scopes=REQUIRED_SCOPES,
            ),
            transport=identity_transport
            or metadata_verifier.UrllibSlackAuthTestTransport(),
        )
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_IDENTITY_REFUSED") from None
    history = SlackWebApiDialogueClient(
        token=token,
        workspace_id=SLACK_WORKSPACE_ID,
        channel_id=SLACK_CHANNEL_ID,
        bot_user_id=bot_user_id,
        transport=history_transport,
    )
    try:
        await history.fetch_channel_history(channel_id=SLACK_CHANNEL_ID, limit=1)
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_CHANNEL_REFUSED") from None
    return {
        "bot_id": identity["bot_id"],
        "bot_user_id": identity["bot_user_id"],
        "channel_id": SLACK_CHANNEL_ID,
        "scopes": list(REQUIRED_SCOPES),
        "workspace_id": identity["team_id"],
    }


def write_new_private_file(
    path: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> _CreatedFile:
    """Create one final inode with C1's O_EXCL pattern and self-clean failures."""
    path = Path(path)
    if not path.is_absolute() or not payload or len(payload) > 64 * 1024:
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
    try:
        parent = path.parent.lstat()
    except OSError:
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED") from None
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    identity: _CreatedFile | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        identity = _CreatedFile(
            path=path,
            descriptor=descriptor,
            device=None,
            inode=None,
        )
        opened = os.fstat(descriptor)
        identity.device = opened.st_dev
        identity.inode = opened.st_ino
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
        if opened.st_uid != int(uid) or opened.st_gid != int(gid):
            os.fchown(descriptor, int(uid), int(gid))
        os.fchmod(descriptor, int(mode))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
            view = view[written:]
        os.fsync(descriptor)
    except FileExistsError:
        raise A2EnrollmentError("A2_ENROLLMENT_COLLISION") from None
    except BaseException:
        if identity is not None:
            _rollback_created((identity,))
        elif descriptor >= 0:
            os.close(descriptor)
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED") from None

    try:
        final = path.lstat()
        if (
            identity is None
            or not stat.S_ISREG(final.st_mode)
            or final.st_nlink != 1
            or final.st_dev != identity.device
            or final.st_ino != identity.inode
            or final.st_uid != int(uid)
            or final.st_gid != int(gid)
            or stat.S_IMODE(final.st_mode) != int(mode)
        ):
            raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
        c1_enrollment._fsync_parent(path)  # noqa: SLF001
    except BaseException:
        if identity is not None:
            _rollback_created((identity,))
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED") from None
    return identity


def _canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            dict(document),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _path_present(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED") from None


def _release_created(identity: _CreatedFile | _BoundCreatedFile) -> None:
    descriptor = identity.descriptor
    if descriptor < 0:
        return
    identity.descriptor = -1
    os.close(descriptor)


def _rollback_created(created: Sequence[_CreatedFile]) -> None:
    failed = False
    for identity in reversed(tuple(created)):
        if identity.descriptor < 0:
            continue
        try:
            original = os.fstat(identity.descriptor)
            info = identity.path.lstat()
            if (
                not stat.S_ISREG(original.st_mode)
                or original.st_dev != identity.device
                or original.st_ino != identity.inode
                or stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_dev != identity.device
                or info.st_ino != identity.inode
                or info.st_dev != original.st_dev
                or info.st_ino != original.st_ino
            ):
                failed = True
                continue
            identity.path.unlink()
            c1_enrollment._fsync_parent(identity.path)  # noqa: SLF001
        except OSError:
            failed = True
        finally:
            try:
                _release_created(identity)
            except OSError:
                failed = True
    if failed:
        raise A2EnrollmentError("A2_ENROLLMENT_ROLLBACK_REFUSED")


def _rollback_bound_created(
    binding: _BoundDirectory,
    created: Sequence[_BoundCreatedFile],
) -> None:
    failed = False
    for identity in reversed(tuple(created)):
        if identity.descriptor < 0:
            continue
        try:
            original = os.fstat(identity.descriptor)
            info = os.stat(
                identity.name,
                dir_fd=binding.descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(original.st_mode)
                or original.st_dev != identity.device
                or original.st_ino != identity.inode
                or stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_dev != identity.device
                or info.st_ino != identity.inode
                or info.st_dev != original.st_dev
                or info.st_ino != original.st_ino
            ):
                failed = True
                continue
            os.unlink(identity.name, dir_fd=binding.descriptor)
            os.fsync(binding.descriptor)
        except OSError:
            failed = True
        finally:
            try:
                _release_created(identity)
            except OSError:
                failed = True
    if failed:
        raise A2EnrollmentError("A2_ENROLLMENT_ROLLBACK_REFUSED")


def _rollback_enrollment_files(
    binding: _BoundDirectory,
    *,
    bound_created: Sequence[_BoundCreatedFile],
    absolute_created: Sequence[_CreatedFile],
) -> None:
    failed = False
    try:
        _rollback_created(absolute_created)
    except A2EnrollmentError:
        failed = True
    try:
        _rollback_bound_created(binding, bound_created)
    except A2EnrollmentError:
        failed = True
    if failed:
        raise A2EnrollmentError("A2_ENROLLMENT_ROLLBACK_REFUSED")


def _release_enrollment_files(
    *,
    bound_created: Sequence[_BoundCreatedFile],
    absolute_created: Sequence[_CreatedFile],
) -> None:
    failed = False
    for identity in (*reversed(tuple(absolute_created)), *reversed(tuple(bound_created))):
        try:
            _release_created(identity)
        except OSError:
            failed = True
    if failed:
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")


def _assert_disarmed() -> None:
    try:
        if c1_enrollment._launchd_loaded(  # noqa: SLF001
            RELAY_LABEL
        ) or not c1_enrollment._launchd_disabled(RELAY_LABEL):  # noqa: SLF001
            raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
    except A2EnrollmentError:
        raise
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED") from None


def _principal_can_traverse(path: Path, *, uid: int, gids: set[int]) -> bool:
    """Return whether one exact principal may safely traverse a real directory."""

    try:
        info = Path(path).lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return False
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return False
    if info.st_uid == uid:
        required = stat.S_IXUSR
    elif info.st_gid in gids:
        required = stat.S_IXGRP
    else:
        required = stat.S_IXOTH
    return bool(info.st_mode & required)


def _credential_directory_chain() -> tuple[Path, ...] | None:
    """Return the fixed lexical credential chain without resolving symlinks."""

    config_parent = SYSTEM_ROOT / "config"
    support = SYSTEM_ROOT.parent
    library = support.parent
    if (
        SYSTEM_ROOT.name != "MastermindExecutive"
        or support.name != "Application Support"
        or library.name != "Library"
        or TOKEN_PATH != config_parent / "agent-relay.token"
        or CONFIG_PATH != config_parent / "agent-relay.json"
    ):
        return None
    return (library, support, SYSTEM_ROOT, config_parent)


def _assert_bound_config_current(binding: _BoundDirectory) -> None:
    chain = _credential_directory_chain()
    try:
        current = CONFIG_PATH.parent.lstat()
    except OSError:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED") from None
    if (
        chain is None
        or not all(
            _principal_can_traverse(
                path,
                uid=RELAY_UID,
                gids=set(binding.relay_gids),
            )
            for path in chain
        )
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or current.st_dev != binding.device
        or current.st_ino != binding.inode
    ):
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")


def _open_bound_config_directory() -> _BoundDirectory:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = -1
    try:
        relay_gids = frozenset(os.getgrouplist(RELAY_USER, RELAY_GID))
        if RELAY_GID not in relay_gids or EXEC_GID in relay_gids:
            raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
        descriptor = os.open(CONFIG_PATH.parent, flags)
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
        binding = _BoundDirectory(
            descriptor=descriptor,
            device=info.st_dev,
            inode=info.st_ino,
            relay_gids=relay_gids,
        )
        _assert_bound_config_current(binding)
        return binding
    except A2EnrollmentError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED") from None


def _bound_path_present(binding: _BoundDirectory, name: str) -> bool:
    try:
        os.stat(name, dir_fd=binding.descriptor, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED") from None


def _write_new_bound_private_file(
    binding: _BoundDirectory,
    name: str,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> _BoundCreatedFile:
    if (
        name not in {TOKEN_PATH.name, CONFIG_PATH.name}
        or Path(name).name != name
        or not payload
        or len(payload) > 64 * 1024
    ):
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
    if not hasattr(os, "O_NOFOLLOW"):
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= os.O_NOFOLLOW
    descriptor = -1
    identity: _BoundCreatedFile | None = None
    try:
        descriptor = os.open(
            name,
            flags,
            0o600,
            dir_fd=binding.descriptor,
        )
        identity = _BoundCreatedFile(
            name=name,
            descriptor=descriptor,
            device=None,
            inode=None,
        )
        opened = os.fstat(descriptor)
        identity.device = opened.st_dev
        identity.inode = opened.st_ino
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
        if opened.st_uid != int(uid) or opened.st_gid != int(gid):
            os.fchown(descriptor, int(uid), int(gid))
        os.fchmod(descriptor, int(mode))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
            view = view[written:]
        os.fsync(descriptor)
    except FileExistsError:
        raise A2EnrollmentError("A2_ENROLLMENT_COLLISION") from None
    except BaseException:
        if identity is not None:
            _rollback_bound_created(binding, (identity,))
        elif descriptor >= 0:
            os.close(descriptor)
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED") from None

    try:
        final = os.stat(
            name,
            dir_fd=binding.descriptor,
            follow_symlinks=False,
        )
        if (
            identity is None
            or not stat.S_ISREG(final.st_mode)
            or final.st_nlink != 1
            or final.st_dev != identity.device
            or final.st_ino != identity.inode
            or final.st_uid != int(uid)
            or final.st_gid != int(gid)
            or stat.S_IMODE(final.st_mode) != int(mode)
        ):
            raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED")
        os.fsync(binding.descriptor)
        return identity
    except BaseException:
        if identity is not None:
            _rollback_bound_created(binding, (identity,))
        raise A2EnrollmentError("A2_ENROLLMENT_WRITE_REFUSED") from None


def _read_bound_exact(
    binding: _BoundDirectory,
    name: str,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(name, flags, dir_fd=binding.descriptor)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != int(uid)
            or info.st_gid != int(gid)
            or stat.S_IMODE(info.st_mode) != int(mode)
        ):
            raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED")
        raw = os.read(descriptor, 64 * 1024 + 1)
        if not raw or len(raw) > 64 * 1024:
            raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED")
        return raw
    except A2EnrollmentError:
        raise
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _assert_host_prepared() -> str:
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
    try:
        release_sha = c1_enrollment._release_identity()  # noqa: SLF001
        account = pwd.getpwnam(RELAY_USER)
        exec_account = pwd.getpwnam(EXEC_USER)
        group = grp.getgrnam(RELAY_GROUP)
        relay_gids = set(os.getgrouplist(RELAY_USER, RELAY_GID))
        exec_gids = set(os.getgrouplist(EXEC_USER, EXEC_GID))
        relay_group_names = {grp.getgrgid(gid).gr_name for gid in relay_gids}
        credential_chain = _credential_directory_chain()
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED") from None
    if (
        account.pw_uid != RELAY_UID
        or account.pw_gid != RELAY_GID
        or exec_account.pw_uid != EXEC_UID
        or exec_account.pw_gid != EXEC_GID
        or group.gr_gid != RELAY_GID
        or tuple(group.gr_mem) != _RELAY_GROUP_MEMBERS
        or account.pw_dir != os.fspath(RELAY_HOME)
        or account.pw_shell != "/usr/bin/false"
        or RELAY_GROUP not in relay_group_names
        or EXEC_GID in relay_gids
        or RELAY_GID not in exec_gids
        or credential_chain is None
        or not all(
            _principal_can_traverse(path, uid=RELAY_UID, gids=relay_gids)
            for path in credential_chain
        )
    ):
        raise A2EnrollmentError("A2_ENROLLMENT_HOST_REFUSED")
    _assert_disarmed()
    return release_sha


def _read_exact(path: Path, *, uid: int, gid: int, mode: int) -> bytes:
    try:
        return c1_enrollment.c1_runtime._read_exact_private_bytes(  # noqa: SLF001
            path,
            expected_uid=uid,
            expected_gid=gid,
            expected_mode=mode,
            max_bytes=64 * 1024,
        )
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED") from None


def _existing_token(binding: _BoundDirectory) -> str:
    raw = _read_bound_exact(
        binding,
        TOKEN_PATH.name,
        uid=RELAY_UID,
        gid=RELAY_GID,
        mode=0o400,
    )
    try:
        return metadata_verifier.read_token_from_stdin(io.BytesIO(raw))
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED") from None


def _validate_existing(
    binding: _BoundDirectory,
    *,
    bot_user_id: str,
    release_sha: str,
    expected_token: bytes | None = None,
) -> None:
    expected_config = _canonical_json_bytes(
        build_config_document(bot_user_id=bot_user_id, release_sha=release_sha)
    )
    expected_plist = render_plist(bot_user_id=bot_user_id, release_sha=release_sha)
    if (
        (
            expected_token is not None
            and _read_bound_exact(
                binding,
                TOKEN_PATH.name,
                uid=RELAY_UID,
                gid=RELAY_GID,
                mode=0o400,
            )
            != expected_token
        )
        or _read_bound_exact(
            binding,
            CONFIG_PATH.name,
            uid=RELAY_UID,
            gid=RELAY_GID,
            mode=0o400,
        )
        != expected_config
        or _read_exact(PLIST_PATH, uid=PLIST_UID, gid=PLIST_GID, mode=0o644)
        != expected_plist
    ):
        raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED")


async def _enroll(*, bot_user_id: str, stdin: BinaryIO) -> dict[str, object]:
    release_sha = _assert_host_prepared()
    binding = _open_bound_config_directory()
    bound_created: list[_BoundCreatedFile] = []
    absolute_created: list[_CreatedFile] = []
    try:
        if (
            _bound_path_present(binding, TOKEN_PATH.name)
            or _bound_path_present(binding, CONFIG_PATH.name)
            or _path_present(PLIST_PATH)
        ):
            raise A2EnrollmentError("A2_ENROLLMENT_COLLISION")
        token = read_token_from_stdin(stdin)
        qualification = await qualify_token(token=token, bot_user_id=bot_user_id)
        _assert_bound_config_current(binding)
        bound_created.append(
            _write_new_bound_private_file(
                binding,
                TOKEN_PATH.name,
                (token + "\n").encode("ascii"),
                uid=RELAY_UID,
                gid=RELAY_GID,
                mode=0o400,
            )
        )
        bound_created.append(
            _write_new_bound_private_file(
                binding,
                CONFIG_PATH.name,
                _canonical_json_bytes(
                    build_config_document(
                        bot_user_id=bot_user_id,
                        release_sha=release_sha,
                    )
                ),
                uid=RELAY_UID,
                gid=RELAY_GID,
                mode=0o400,
            )
        )
        absolute_created.append(
            write_new_private_file(
                PLIST_PATH,
                render_plist(bot_user_id=bot_user_id, release_sha=release_sha),
                uid=PLIST_UID,
                gid=PLIST_GID,
                mode=0o644,
            )
        )
        _validate_existing(
            binding,
            bot_user_id=bot_user_id,
            release_sha=release_sha,
            expected_token=(token + "\n").encode("ascii"),
        )
        _assert_disarmed()
        _assert_bound_config_current(binding)
        _release_enrollment_files(
            bound_created=bound_created,
            absolute_created=absolute_created,
        )
    except BaseException:
        try:
            _rollback_enrollment_files(
                binding,
                bound_created=bound_created,
                absolute_created=absolute_created,
            )
        except A2EnrollmentError:
            raise
        raise
    finally:
        os.close(binding.descriptor)
    return {**qualification, "action": "enrolled", "release_sha": release_sha}


async def _verify(*, bot_user_id: str) -> dict[str, object]:
    release_sha = _assert_host_prepared()
    binding = _open_bound_config_directory()
    try:
        if (
            not _bound_path_present(binding, TOKEN_PATH.name)
            or not _bound_path_present(binding, CONFIG_PATH.name)
            or not _path_present(PLIST_PATH)
        ):
            raise A2EnrollmentError("A2_ENROLLMENT_EXISTING_REFUSED")
        _validate_existing(
            binding,
            bot_user_id=bot_user_id,
            release_sha=release_sha,
        )
        token = _existing_token(binding)
        qualification = await qualify_token(token=token, bot_user_id=bot_user_id)
        _assert_disarmed()
        _assert_bound_config_current(binding)
        return {**qualification, "action": "verified", "release_sha": release_sha}
    finally:
        os.close(binding.descriptor)


def _fixed_error(code: str) -> dict[str, object]:
    return {
        "error": code,
        "schema": "mastermind.a2_agent_relay_enrollment.v1",
        "status": "ERROR",
    }


def _require_native_tty(stdin: BinaryIO) -> None:
    try:
        descriptor = stdin.fileno()
        if (
            isinstance(descriptor, bool)
            or not isinstance(descriptor, int)
            or descriptor < 0
            or not os.isatty(descriptor)
        ):
            raise A2EnrollmentError("A2_ENROLLMENT_INPUT_REFUSED")
    except Exception:
        raise A2EnrollmentError("A2_ENROLLMENT_INPUT_REFUSED") from None


def _run_invocation(
    argv: Sequence[str],
    *,
    stdin: BinaryIO,
    stdout: TextIO,
    environ: Mapping[str, str],
    require_native_tty: bool,
) -> int:
    try:
        assert_secret_surfaces_clean(argv=argv, environ=environ)
        args = build_parser().parse_args(list(argv))
        if require_native_tty and args.command == "enroll":
            _require_native_tty(stdin)
        if args.command == "enroll":
            receipt = asyncio.run(
                _enroll(bot_user_id=args.expected_bot_user_id, stdin=stdin)
            )
        elif args.command == "verify":
            receipt = asyncio.run(_verify(bot_user_id=args.expected_bot_user_id))
        else:  # pragma: no cover
            raise A2EnrollmentError("A2_ENROLLMENT_ARGUMENTS_REFUSED")
        stdout.write(
            json.dumps(
                {
                    **receipt,
                    "schema": "mastermind.a2_agent_relay_enrollment.v1",
                    "status": "PASS",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 0
    except A2EnrollmentError as exc:
        stdout.write(json.dumps(_fixed_error(exc.code), sort_keys=True, separators=(",", ":")) + "\n")
        return 2
    except Exception:
        stdout.write(
            json.dumps(
                _fixed_error("A2_ENROLLMENT_INTERNAL"),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


def run(
    argv: Sequence[str],
    *,
    stdin: BinaryIO,
    stdout: TextIO,
    environ: Mapping[str, str],
) -> int:
    return _run_invocation(
        argv,
        stdin=stdin,
        stdout=stdout,
        environ=environ,
        require_native_tty=False,
    )


def main() -> int:
    argv = sys.argv[1:]
    stdin = getattr(sys.stdin, "buffer", sys.stdin)
    return _run_invocation(
        argv,
        stdin=stdin,
        stdout=sys.stdout,
        environ=os.environ,
        require_native_tty=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "A2EnrollmentError",
    "ERROR_CODES",
    "build_config_document",
    "build_parser",
    "main",
    "qualify_token",
    "read_token_from_stdin",
    "render_plist",
    "run",
    "write_new_private_file",
]
