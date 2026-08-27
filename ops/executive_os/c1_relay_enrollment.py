"""Native, secret-owning enrollment ceremony for the C1 SOL_STATE Relay.

This helper does not provision a Slack app and never starts or enables a service.
A native operator first creates/selects the dedicated Executive Relay app and
invites its bot to the private ``#sol-runtime`` channel.  This root-only helper
then validates the prepared host, accepts one no-echo token line from stdin,
qualifies the exact Slack identity/scopes/channel, writes the fixed private
files, and stops with the Relay disabled and unloaded.

``resume`` is limited to the one reviewed crash state where the token file was
committed but config was not. ``verify`` is read-only with respect to enrollment
files. No operation overwrites ambiguous existing state.
"""
from __future__ import annotations

import argparse
import asyncio
import grp
import json
import os
import plistlib
import pwd
import re
import stat
import subprocess
import sys
import termios
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO, TextIO

_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from integrations.slack_executive import c1_runtime  # noqa: E402
from integrations.slack_executive.slack_web_api import (  # noqa: E402
    SlackHttpTransport,
    SlackWebApiStateClient,
)
from ops.executive_os import release_manifest  # noqa: E402

RELAY_USER = "_mastermind_sol_relay"
RELAY_GROUP = "_mastermind_sol_relay"
RELAY_UID = 452
RELAY_GID = 452
RELAY_LABEL = "com.mastermind.executive.sol-state-relay"
CONTROL_LABEL = "com.mastermind.executive.control"
CONTROL_CONFIG = Path(
    "/Library/Application Support/MastermindExecutive/config/control.json"
)
CONTROL_PLIST = Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist")
RELAY_PLIST = Path(
    "/Library/LaunchDaemons/com.mastermind.executive.sol-state-relay.plist"
)
SYSTEM_RELEASE_ROOT = Path(
    "/Library/Application Support/MastermindExecutive/releases"
)
MAX_TOKEN_BYTES = 2048
_TOKEN_SHAPED_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"
)
_RELEASE_RE = re.compile(r"^[0-9a-f]{40}$")

ERROR_CODES = frozenset(
    {
        "C1_ENROLLMENT_ARGUMENTS_REFUSED",
        "C1_ENROLLMENT_CHANNEL_REFUSED",
        "C1_ENROLLMENT_COLLISION",
        "C1_ENROLLMENT_EXISTING_REFUSED",
        "C1_ENROLLMENT_HOST_REFUSED",
        "C1_ENROLLMENT_IDENTITY_REFUSED",
        "C1_ENROLLMENT_INPUT_REFUSED",
        "C1_ENROLLMENT_INTERNAL",
        "C1_ENROLLMENT_SECRET_SURFACE_REFUSED",
        "C1_ENROLLMENT_WRITE_REFUSED",
    }
)


class C1EnrollmentError(RuntimeError):
    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown C1 enrollment error code")
        super().__init__(code)
        self.code = code


class _OpaqueParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse path
        raise C1EnrollmentError("C1_ENROLLMENT_ARGUMENTS_REFUSED")


def build_parser() -> argparse.ArgumentParser:
    parser = _OpaqueParser(description="Enroll the Mastermind C1 SOL_STATE Relay")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("enroll", "resume", "verify"):
        child = commands.add_parser(name)
        child.add_argument("--expected-bot-user-id", required=True)
    return parser


def assert_secret_surfaces_clean(
    *, argv: Sequence[str], environ: Mapping[str, str]
) -> None:
    if any(_TOKEN_SHAPED_RE.search(str(value)) for value in argv):
        raise C1EnrollmentError("C1_ENROLLMENT_SECRET_SURFACE_REFUSED")
    for key, value in environ.items():
        normalized = str(key).upper()
        if (
            ("SLACK" in normalized and "TOKEN" in normalized)
            or normalized in {"C1_RELAY_TOKEN", "MASTERMIND_SLACK_TOKEN"}
            or _TOKEN_SHAPED_RE.search(str(value))
        ):
            raise C1EnrollmentError("C1_ENROLLMENT_SECRET_SURFACE_REFUSED")


def _decode_token_bytes(raw: bytes) -> str:
    if not raw or len(raw) > MAX_TOKEN_BYTES + 1:
        raise C1EnrollmentError("C1_ENROLLMENT_INPUT_REFUSED")
    if raw.endswith(b"\n"):
        raw = raw[:-1]
        if raw.endswith(b"\r"):
            raw = raw[:-1]
    if (
        not raw
        or len(raw) > MAX_TOKEN_BYTES
        or b"\n" in raw
        or b"\r" in raw
        or any(byte in b" \t\v\f" for byte in raw)
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_INPUT_REFUSED")
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        raise C1EnrollmentError("C1_ENROLLMENT_INPUT_REFUSED") from None


def _tty_fd(stream: BinaryIO) -> int | None:
    try:
        descriptor = stream.fileno()
    except (AttributeError, OSError, ValueError):
        return None
    return descriptor if os.isatty(descriptor) else None


def read_token_from_stdin(stream: BinaryIO) -> str:
    """Read exactly one bounded token line; suppress terminal echo when native."""

    descriptor = _tty_fd(stream)
    if descriptor is None:
        return _decode_token_bytes(stream.readline(MAX_TOKEN_BYTES + 2))
    try:
        original = termios.tcgetattr(descriptor)
        muted = list(original)
        muted[3] &= ~termios.ECHO
        termios.tcsetattr(descriptor, termios.TCSANOW, muted)
    except (OSError, termios.error):
        raise C1EnrollmentError("C1_ENROLLMENT_INPUT_REFUSED") from None
    try:
        raw = stream.readline(MAX_TOKEN_BYTES + 2)
    finally:
        try:
            termios.tcsetattr(descriptor, termios.TCSANOW, original)
        except (OSError, termios.error):
            raise C1EnrollmentError("C1_ENROLLMENT_INPUT_REFUSED") from None
    return _decode_token_bytes(raw)


def build_config_document(*, bot_user_id: str, release_sha: str) -> dict[str, object]:
    if c1_runtime._BOT_USER_RE.fullmatch(bot_user_id or "") is None:  # noqa: SLF001
        raise C1EnrollmentError("C1_ENROLLMENT_ARGUMENTS_REFUSED")
    if _RELEASE_RE.fullmatch(release_sha or "") is None:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    return {
        "schema": c1_runtime.CONFIG_SCHEMA,
        "executive_socket": os.fspath(c1_runtime.EXECUTIVE_SOCKET_PATH),
        "slack_workspace_id": c1_runtime.SLACK_WORKSPACE_ID,
        "slack_channel_id": c1_runtime.SLACK_CHANNEL_ID,
        "slack_bot_user_id": bot_user_id,
        "slack_token_file": os.fspath(c1_runtime.TOKEN_PATH),
        "poll_seconds": c1_runtime.POLL_SECONDS,
        "heartbeat_seconds": c1_runtime.HEARTBEAT_SECONDS,
        "max_executive_age_seconds": c1_runtime.MAX_EXECUTIVE_AGE_SECONDS,
        "relay_version": release_sha,
    }


async def qualify_token(
    *,
    token: str,
    bot_user_id: str,
    identity_transport: SlackHttpTransport | None = None,
    history_transport: SlackHttpTransport | None = None,
) -> dict[str, object]:
    try:
        identity = await c1_runtime.verify_slack_identity(
            token=token,
            expected_workspace_id=c1_runtime.SLACK_WORKSPACE_ID,
            expected_bot_user_id=bot_user_id,
            transport=identity_transport,
        )
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_IDENTITY_REFUSED") from None

    history = SlackWebApiStateClient(
        token=token,
        bot_user_id=bot_user_id,
        transport=history_transport,
    )
    try:
        try:
            await history.fetch_history(
                channel_id=c1_runtime.SLACK_CHANNEL_ID,
                limit=1,
            )
        except Exception:
            raise C1EnrollmentError("C1_ENROLLMENT_CHANNEL_REFUSED") from None
    finally:
        await history.aclose()
    return {
        "bot_user_id": identity.bot_user_id,
        "channel_id": c1_runtime.SLACK_CHANNEL_ID,
        "scopes": list(identity.scopes),
        "workspace_id": identity.workspace_id,
    }


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_new_private_file(
    path: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> None:
    """Create a new final file with O_EXCL; never overwrite existing state."""

    path = Path(path)
    if not path.is_absolute() or not payload or len(payload) > 64 * 1024:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
    try:
        parent = path.parent.lstat()
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise C1EnrollmentError("C1_ENROLLMENT_COLLISION") from None
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
        if info.st_uid != int(uid) or info.st_gid != int(gid):
            os.fchown(descriptor, int(uid), int(gid))
        os.fchmod(descriptor, int(mode))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
            view = view[written:]
        os.fsync(descriptor)
    except C1EnrollmentError:
        raise
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    try:
        final = path.lstat()
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    if (
        not stat.S_ISREG(final.st_mode)
        or final.st_nlink != 1
        or final.st_uid != int(uid)
        or final.st_gid != int(gid)
        or stat.S_IMODE(final.st_mode) != int(mode)
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
    try:
        _fsync_parent(path)
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None


def _release_identity() -> str:
    root = _ROOT.resolve(strict=True)
    try:
        root.relative_to(SYSTEM_RELEASE_ROOT)
    except ValueError:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    release_sha = root.name
    if _RELEASE_RE.fullmatch(release_sha) is None:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    manifest = root / release_manifest.MANIFEST_NAME
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        tree_sha = value["tree_sha"]
        if value.get("commit_sha") != release_sha or _RELEASE_RE.fullmatch(tree_sha) is None:
            raise ValueError
        release_manifest.verify(root, release_sha, tree_sha)
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    return release_sha


def _launchd_disabled(label: str) -> bool:
    try:
        completed = subprocess.run(
            ["/bin/launchctl", "print-disabled", "system"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False
    return re.search(
        rf'^\s*"{re.escape(label)}"\s*=>\s*true\s*$',
        completed.stdout,
        re.MULTILINE,
    ) is not None


def _launchd_loaded(label: str) -> bool:
    try:
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"system/{label}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    return completed.returncode == 0


def _exact_file(path: Path, *, uid: int, gid: int, mode: int) -> None:
    try:
        info = path.lstat()
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != uid
        or info.st_gid != gid
        or stat.S_IMODE(info.st_mode) != mode
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    try:
        if c1_runtime._path_has_acl(path, expected_info=info):  # noqa: SLF001
            raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    except C1EnrollmentError:
        raise
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None


def validate_host_relay_groups() -> None:
    """Resolve the Relay account's full group vector and apply shared C1 law."""

    try:
        gids = os.getgrouplist(RELAY_USER, RELAY_GID)
        names = {grp.getgrgid(gid).gr_name for gid in gids}
        c1_runtime.validate_relay_group_names(names)
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None


def _assert_host_prepared() -> str:
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    release_sha = _release_identity()
    try:
        account = pwd.getpwnam(RELAY_USER)
        group = grp.getgrnam(RELAY_GROUP)
    except KeyError:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    if (
        account.pw_uid != RELAY_UID
        or account.pw_gid != RELAY_GID
        or group.gr_gid != RELAY_GID
        or group.gr_mem
        or account.pw_dir != "/var/db/mastermind-executive/sol-state-relay/home"
        or account.pw_shell != "/usr/bin/false"
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    # This runs before any token is read. A prepared host with admin/wheel or
    # any other unreviewed supplementary group is not eligible for enrollment.
    validate_host_relay_groups()

    _exact_file(CONTROL_CONFIG, uid=0, gid=450, mode=0o440)
    _exact_file(CONTROL_PLIST, uid=0, gid=0, mode=0o644)
    _exact_file(RELAY_PLIST, uid=0, gid=0, mode=0o644)

    try:
        control = json.loads(CONTROL_CONFIG.read_text(encoding="utf-8"))
        if (
            control.get("proof_base_sha") != release_sha
            or control.get("ceo_ingress_launchd_socket_name") != "CeoIngress"
            or control.get("ceo_ingress_peer_uid") != RELAY_UID
            or control.get("ceo_ingress_socket_path")
            != os.fspath(c1_runtime.EXECUTIVE_SOCKET_PATH)
            or "ceo_ingress_armed" in control
        ):
            raise ValueError
        control_plist = plistlib.loads(CONTROL_PLIST.read_bytes())
        sockets = control_plist["Sockets"]
        if set(sockets) != {"Operator", "CeoIngress"}:
            raise ValueError
        if (
            sockets["Operator"].get("SockPathOwner") != 450
            or sockets["Operator"].get("SockPathGroup") != 453
            or sockets["Operator"].get("SockPathMode") != 0o660
            or sockets["CeoIngress"].get("SockPathOwner") != 450
            or sockets["CeoIngress"].get("SockPathGroup") != RELAY_GID
            or sockets["CeoIngress"].get("SockPathMode") != 0o660
        ):
            raise ValueError

        relay_plist = plistlib.loads(RELAY_PLIST.read_bytes())
        if relay_plist.get("Label") != RELAY_LABEL:
            raise ValueError
        if (
            relay_plist.get("UserName") != RELAY_USER
            or relay_plist.get("GroupName") != RELAY_GROUP
        ):
            raise ValueError
        expected_program = [
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
            "-I",
            "-S",
            "-B",
            os.fspath(_ROOT / "scripts" / "c1_sol_state_relay.py"),
            "--config",
            os.fspath(c1_runtime.CONFIG_PATH),
        ]
        if relay_plist.get("ProgramArguments") != expected_program:
            raise ValueError
        environment = relay_plist.get("EnvironmentVariables")
        if not isinstance(environment, dict) or any(
            "TOKEN" in str(key).upper() for key in environment
        ):
            raise ValueError
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None

    if (
        _launchd_loaded(CONTROL_LABEL)
        or _launchd_loaded(RELAY_LABEL)
        or not _launchd_disabled(RELAY_LABEL)
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    return release_sha


def _path_present(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_EXISTING_REFUSED") from None


def _existing_token() -> str:
    try:
        raw = c1_runtime._read_exact_private_bytes(  # noqa: SLF001
            c1_runtime.TOKEN_PATH,
            expected_uid=RELAY_UID,
            expected_gid=RELAY_GID,
            expected_mode=0o400,
            max_bytes=MAX_TOKEN_BYTES,
        )
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_EXISTING_REFUSED") from None
    return _decode_token_bytes(raw)


def _canonical_config_bytes(document: Mapping[str, object]) -> bytes:
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


async def _enroll(*, bot_user_id: str, stdin: BinaryIO) -> dict[str, object]:
    release_sha = _assert_host_prepared()
    if _path_present(c1_runtime.TOKEN_PATH) or _path_present(c1_runtime.CONFIG_PATH):
        raise C1EnrollmentError("C1_ENROLLMENT_COLLISION")
    token = read_token_from_stdin(stdin)
    qualification = await qualify_token(token=token, bot_user_id=bot_user_id)
    write_new_private_file(
        c1_runtime.TOKEN_PATH,
        (token + "\n").encode("ascii"),
        uid=RELAY_UID,
        gid=RELAY_GID,
        mode=0o400,
    )
    config = build_config_document(bot_user_id=bot_user_id, release_sha=release_sha)
    write_new_private_file(
        c1_runtime.CONFIG_PATH,
        _canonical_config_bytes(config),
        uid=0,
        gid=RELAY_GID,
        mode=0o440,
    )
    c1_runtime.load_config(c1_runtime.CONFIG_PATH, expected_group_gid=RELAY_GID)
    return {**qualification, "action": "enrolled", "release_sha": release_sha}


async def _resume(*, bot_user_id: str) -> dict[str, object]:
    release_sha = _assert_host_prepared()
    if not _path_present(c1_runtime.TOKEN_PATH) or _path_present(c1_runtime.CONFIG_PATH):
        raise C1EnrollmentError("C1_ENROLLMENT_EXISTING_REFUSED")
    token = _existing_token()
    qualification = await qualify_token(token=token, bot_user_id=bot_user_id)
    config = build_config_document(bot_user_id=bot_user_id, release_sha=release_sha)
    write_new_private_file(
        c1_runtime.CONFIG_PATH,
        _canonical_config_bytes(config),
        uid=0,
        gid=RELAY_GID,
        mode=0o440,
    )
    c1_runtime.load_config(c1_runtime.CONFIG_PATH, expected_group_gid=RELAY_GID)
    return {**qualification, "action": "resumed", "release_sha": release_sha}


async def _verify(*, bot_user_id: str) -> dict[str, object]:
    release_sha = _assert_host_prepared()
    if not _path_present(c1_runtime.TOKEN_PATH) or not _path_present(
        c1_runtime.CONFIG_PATH
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_EXISTING_REFUSED")
    config = c1_runtime.load_config(
        c1_runtime.CONFIG_PATH,
        expected_group_gid=RELAY_GID,
    )
    if config.slack_bot_user_id != bot_user_id or config.relay_version != release_sha:
        raise C1EnrollmentError("C1_ENROLLMENT_EXISTING_REFUSED")
    token = _existing_token()
    qualification = await qualify_token(token=token, bot_user_id=bot_user_id)
    return {**qualification, "action": "verified", "release_sha": release_sha}


def _fixed_error(code: str) -> dict[str, object]:
    return {
        "error": code,
        "schema": "mastermind.c1_relay_enrollment.v1",
        "status": "ERROR",
    }


def run(
    argv: Sequence[str],
    *,
    stdin: BinaryIO,
    stdout: TextIO,
    environ: Mapping[str, str],
) -> int:
    try:
        assert_secret_surfaces_clean(argv=argv, environ=environ)
        args = build_parser().parse_args(list(argv))
        if args.command == "enroll":
            receipt = asyncio.run(
                _enroll(bot_user_id=args.expected_bot_user_id, stdin=stdin)
            )
        elif args.command == "resume":
            receipt = asyncio.run(_resume(bot_user_id=args.expected_bot_user_id))
        elif args.command == "verify":
            receipt = asyncio.run(_verify(bot_user_id=args.expected_bot_user_id))
        else:  # pragma: no cover
            raise C1EnrollmentError("C1_ENROLLMENT_ARGUMENTS_REFUSED")
        stdout.write(
            json.dumps(
                {
                    **receipt,
                    "schema": "mastermind.c1_relay_enrollment.v1",
                    "status": "PASS",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 0
    except C1EnrollmentError as exc:
        stdout.write(
            json.dumps(
                _fixed_error(exc.code),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2
    except Exception:
        stdout.write(
            json.dumps(
                _fixed_error("C1_ENROLLMENT_INTERNAL"),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        return 2


def main() -> int:
    return run(
        sys.argv[1:],
        stdin=sys.stdin.buffer,
        stdout=sys.stdout,
        environ=os.environ,
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "C1EnrollmentError",
    "ERROR_CODES",
    "MAX_TOKEN_BYTES",
    "assert_secret_surfaces_clean",
    "build_config_document",
    "build_parser",
    "main",
    "qualify_token",
    "read_token_from_stdin",
    "run",
    "validate_host_relay_groups",
    "write_new_private_file",
]
