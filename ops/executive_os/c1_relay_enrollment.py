"""Native, secret-owning enrollment ceremony for the C1 SOL_STATE Relay.

This helper does not provision a Slack app and never starts or enables a service.
A native operator first creates/selects the dedicated Executive Relay app and
invites its bot to the private ``#sol-runtime`` channel.  This root-only helper
then validates the prepared host, accepts one no-echo token line from stdin,
qualifies the exact Slack identity/scopes/channel, writes the fixed private
files, and stops with the Relay disabled and unloaded.

``resume`` is limited to the one reviewed crash state where the token file was
committed but config was not. ``verify`` is read-only with respect to enrollment
files. ``rebind-release`` binds one already complete enrollment to the exact
release tree this helper is executing from, preserving the credential and every
non-version policy field; it never enrolls, enables or starts a service. No
operation overwrites ambiguous existing state.
"""
from __future__ import annotations

import argparse
import asyncio
import grp
import hashlib
import json
import os
import plistlib
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import termios
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
DIALOGUE_OBSERVATION_SOCKET = Path(
    "/var/run/mastermind-dialogue-observation/dialogue-observation.sock"
)
DIALOGUE_RELAY_GID = 457
RELAY_PLIST = Path(
    "/Library/LaunchDaemons/com.mastermind.executive.sol-state-relay.plist"
)
SYSTEM_RELEASE_ROOT = Path(
    "/Library/Application Support/MastermindExecutive/releases"
)
# Pinned host identities. They are named so a fixture host can mirror them onto
# one unprivileged test account; production values are unchanged.
CONTROL_CONFIG_UID = 0
CONTROL_CONFIG_GID = 450
CONTROL_PLIST_UID = 0
CONTROL_PLIST_GID = 0
OPS_GID = 453
RELAY_PLIST_UID = 0
RELAY_PLIST_GID = 0
RELAY_CONFIG_UID = 0
RELAY_CONFIG_GID = RELAY_GID
PYTHON_BINARY = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
RELAY_HOME = "/var/db/mastermind-executive/sol-state-relay/home"
RELAY_STDOUT_PATH = "/var/log/mastermind-executive/sol-state-relay/stdout.log"
RELAY_STDERR_PATH = "/var/log/mastermind-executive/sol-state-relay/stderr.log"
PLIST_MODE = 0o644
CONFIG_MODE = 0o440
TOKEN_MODE = 0o400
PLIST_MAX_BYTES = 64 * 1024
CONFIG_MAX_BYTES = 8192
MAX_TOKEN_BYTES = 2048
_TOKEN_SHAPED_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"
)
_RELEASE_RE = re.compile(r"^[0-9a-f]{40}$")
_PLACEHOLDER_RE = re.compile(r"__[A-Z0-9_]+__")

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
        "C1_REBIND_EFFECT_UNCERTAIN",
        "C1_REBIND_MIXED_GENERATION",
        "C1_REBIND_PARTIAL_STATE",
        "C1_REBIND_PLIST_REFUSED",
        "C1_REBIND_SERVICE_RUNNING",
        "C1_REBIND_STALE_CONFIG",
        "C1_REBIND_TOKEN_DRIFT",
        "C1_REBIND_TOKEN_REFUSED",
        "C1_REBIND_VERSION_MISMATCH",
        "C1_REBIND_WRITE_REFUSED",
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
    for name in ("enroll", "resume", "verify", "rebind-release"):
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


@dataclass(frozen=True)
class _PrivateFileAttestation:
    device: int
    inode: int
    size: int
    mtime_ns: int
    uid: int
    gid: int
    mode: int
    link_count: int
    sha256: str


def _attest_private_bytes(
    path: Path,
    *,
    uid: int,
    gid: int,
    mode: int,
    max_bytes: int,
    code: str,
) -> tuple[bytes, _PrivateFileAttestation]:
    """Read one exact private file and attest its identity and content digest."""

    try:
        before = path.lstat()
        raw = c1_runtime._read_exact_private_bytes(  # noqa: SLF001
            path,
            expected_uid=int(uid),
            expected_gid=int(gid),
            expected_mode=int(mode),
            max_bytes=int(max_bytes),
        )
        after = path.lstat()
    except Exception:
        raise C1EnrollmentError(code) from None
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or (before.st_dev, before.st_ino, before.st_nlink)
        != (after.st_dev, after.st_ino, after.st_nlink)
    ):
        raise C1EnrollmentError(code)
    return raw, _PrivateFileAttestation(
        device=before.st_dev,
        inode=before.st_ino,
        size=before.st_size,
        mtime_ns=before.st_mtime_ns,
        uid=before.st_uid,
        gid=before.st_gid,
        mode=stat.S_IMODE(before.st_mode),
        link_count=before.st_nlink,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _try_attest_private_bytes(
    path: Path,
    *,
    uid: int,
    gid: int,
    mode: int,
    max_bytes: int,
) -> bytes | None:
    """Best-effort durable read used only to reconcile observed state."""

    try:
        return _attest_private_bytes(
            path,
            uid=uid,
            gid=gid,
            mode=mode,
            max_bytes=max_bytes,
            code="C1_REBIND_EFFECT_UNCERTAIN",
        )[0]
    except C1EnrollmentError:
        return None


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
    # macOS emits enabled/disabled; retain the legacy boolean form as well.
    # An absent, unknown, or repeated override cannot prove a stopped boundary.
    states = re.findall(
        rf'^\s*"{re.escape(label)}"\s*=>\s*(\S+)\s*$',
        completed.stdout,
        re.MULTILINE,
    )
    return states in (["true"], ["disabled"])


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


def _install_release_root() -> Path:
    try:
        return _ROOT.resolve(strict=True)
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None


def _relay_substrate() -> str:
    """Validate every release-agnostic C1 host precondition.

    This deliberately does not bind the installed relay plist to a release:
    enroll/resume/verify add that strict current-release check themselves, and
    rebind must instead validate the *previous* enrollment it is replacing.
    """

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
        or account.pw_dir != RELAY_HOME
        or account.pw_shell != "/usr/bin/false"
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    # This runs before any token is read. A prepared host with admin/wheel or
    # any other unreviewed supplementary group is not eligible for enrollment.
    validate_host_relay_groups()

    _exact_file(
        CONTROL_CONFIG,
        uid=CONTROL_CONFIG_UID,
        gid=CONTROL_CONFIG_GID,
        mode=0o440,
    )
    _exact_file(CONTROL_PLIST, uid=CONTROL_PLIST_UID, gid=CONTROL_PLIST_GID, mode=PLIST_MODE)

    try:
        control = json.loads(CONTROL_CONFIG.read_text(encoding="utf-8"))
        if (
            control.get("proof_base_sha") != release_sha
            or control.get("ceo_ingress_launchd_socket_name") != "CeoIngress"
            or control.get("ceo_ingress_peer_uid") != RELAY_UID
            or control.get("ceo_ingress_socket_path")
            != os.fspath(c1_runtime.EXECUTIVE_SOCKET_PATH)
            or control.get("dialogue_bridge_armed") is not False
            or control.get("dialogue_observation_launchd_socket_name")
            != "DialogueObservation"
            or control.get("dialogue_observation_peer_uid") != DIALOGUE_RELAY_GID
            or control.get("dialogue_observation_socket_path")
            != os.fspath(DIALOGUE_OBSERVATION_SOCKET)
            or control.get("dialogue_wake_retry_policy")
            != {
                "accepted_ttl_s": None,
                "armed": False,
                "max_delivery_attempts": None,
                "reenable_on_binding_rotation": True,
                "retry_cooldown_s": None,
                "target_unavailable_backoff_s": None,
            }
            or "ceo_ingress_armed" in control
        ):
            raise ValueError
        control_plist = plistlib.loads(CONTROL_PLIST.read_bytes())
        sockets = control_plist["Sockets"]
        if set(sockets) != {"Operator", "CeoIngress", "DialogueObservation"}:
            raise ValueError
        if (
            sockets["Operator"].get("SockPathOwner") != 450
            or sockets["Operator"].get("SockPathGroup") != OPS_GID
            or sockets["Operator"].get("SockPathMode") != 0o660
            or sockets["CeoIngress"].get("SockPathOwner") != 450
            or sockets["CeoIngress"].get("SockPathGroup") != RELAY_GID
            or sockets["CeoIngress"].get("SockPathMode") != 0o660
            or sockets["DialogueObservation"].get("SockPathName")
            != os.fspath(DIALOGUE_OBSERVATION_SOCKET)
            or sockets["DialogueObservation"].get("SockPathOwner") != 450
            or sockets["DialogueObservation"].get("SockPathGroup")
            != DIALOGUE_RELAY_GID
            or sockets["DialogueObservation"].get("SockPathMode") != 0o660
        ):
            raise ValueError
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    return release_sha


def _assert_services_stopped(code: str) -> None:
    """Require control and relay absent/stopped and the relay explicitly disabled."""

    if (
        _launchd_loaded(CONTROL_LABEL)
        or _launchd_loaded(RELAY_LABEL)
        or not _launchd_disabled(RELAY_LABEL)
    ):
        raise C1EnrollmentError(code)


def _assert_host_prepared() -> str:
    """The strict current-release gate used by enroll, resume and verify.

    The installed relay plist must already be the exact closed enrollment bound
    to this release tree. Rebind must not use this gate: on the stale host it
    exists to repair, the plist is still bound to the previous release.
    """

    release_sha = _relay_substrate()
    raw, _attestation = _attest_private_bytes(
        RELAY_PLIST,
        uid=RELAY_PLIST_UID,
        gid=RELAY_PLIST_GID,
        mode=PLIST_MODE,
        max_bytes=PLIST_MAX_BYTES,
        code="C1_ENROLLMENT_HOST_REFUSED",
    )
    observed_root = _assert_relay_plist_document(
        _parse_relay_plist(raw, code="C1_ENROLLMENT_HOST_REFUSED"),
        code="C1_ENROLLMENT_HOST_REFUSED",
    )
    if observed_root != _install_release_root():
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    _assert_services_stopped("C1_ENROLLMENT_HOST_REFUSED")
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
            expected_mode=TOKEN_MODE,
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


RELAY_PLIST_TEMPLATE_NAME = "com.mastermind.executive.sol-state-relay.plist.template"


def _relay_environment() -> dict[str, str]:
    return {
        "HOME": RELAY_HOME,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONUNBUFFERED": "1",
        "TZ": "UTC",
    }


def _relay_program_arguments(release_root: Path) -> list[str]:
    """The exact relay argv, identical to the shell render owner's input."""

    return [
        PYTHON_BINARY,
        "-I",
        "-S",
        "-B",
        os.fspath(release_root / "scripts" / "c1_sol_state_relay.py"),
        "--config",
        os.fspath(c1_runtime.CONFIG_PATH),
    ]


def _expected_relay_plist_document(release_root: Path) -> dict[str, object]:
    """The one closed relay LaunchDaemon contract for a release root."""

    return {
        "Label": RELAY_LABEL,
        "ProgramArguments": _relay_program_arguments(release_root),
        "WorkingDirectory": os.fspath(release_root),
        "UserName": RELAY_USER,
        "GroupName": RELAY_GROUP,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ExitTimeOut": 15,
        "AbandonProcessGroup": False,
        "ProcessType": "Background",
        "Umask": 0o77,
        "HardResourceLimits": {"Core": 0, "FileSize": 16 * 1024 * 1024},
        "EnvironmentVariables": _relay_environment(),
        "StandardOutPath": RELAY_STDOUT_PATH,
        "StandardErrorPath": RELAY_STDERR_PATH,
    }


def _contains_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return _PLACEHOLDER_RE.search(value) is not None
    if isinstance(value, Mapping):
        return any(
            _contains_placeholder(key) or _contains_placeholder(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_placeholder(item) for item in value)
    return False


def _parse_relay_plist(raw: bytes, *, code: str) -> dict[str, object]:
    """Parse one relay plist without ever indexing before the type is checked."""

    try:
        document = plistlib.loads(raw)
    except Exception:
        raise C1EnrollmentError(code) from None
    if not isinstance(document, dict):
        raise C1EnrollmentError(code)
    return document


def _relay_plist_release_root(document: Mapping[str, object], *, code: str) -> Path:
    """Derive the single installed release root one document is bound to."""

    working_directory = document.get("WorkingDirectory")
    if not isinstance(working_directory, str) or not working_directory:
        raise C1EnrollmentError(code)
    release_root = Path(working_directory)
    if not release_root.is_absolute() or release_root != Path(
        os.path.normpath(working_directory)
    ):
        raise C1EnrollmentError(code)
    try:
        relative = release_root.relative_to(SYSTEM_RELEASE_ROOT.resolve())
    except ValueError:
        raise C1EnrollmentError(code) from None
    if len(relative.parts) != 1 or _RELEASE_RE.fullmatch(relative.parts[0]) is None:
        raise C1EnrollmentError(code)
    return release_root


def _assert_relay_plist_document(
    document: Mapping[str, object], *, code: str
) -> Path:
    """Validate one complete closed relay enrollment and return its release root.

    The document must equal the single reviewed relay contract for its own
    release root: exact 7-element ProgramArguments, exact Python/-I/-S/-B, the
    exact ``scripts/c1_sol_state_relay.py`` entrypoint beneath one 40-hex
    release root, the exact config path and WorkingDirectory, the exact
    Label/UserName/GroupName and static contract, and one closed
    EnvironmentVariables allowlist with no TOKEN key and no leftover template
    placeholder.
    """

    release_root = _relay_plist_release_root(document, code=code)
    if document != _expected_relay_plist_document(release_root) or _contains_placeholder(
        document
    ):
        raise C1EnrollmentError(code)
    return release_root


def _render_relay_plist(release_root: Path) -> bytes:
    """Render the new generation from the installed plist template owner.

    ``prepare-c1-sol-state-relay.sh`` installs the template and then binds
    ProgramArguments, WorkingDirectory, UserName, GroupName, HOME, stdout and
    stderr to the release.  This mirrors that composition, and the composed
    document must equal the closed contract exactly, so template drift fails
    closed instead of writing a second unchecked plist semantics.
    """

    try:
        document = plistlib.loads(
            (
                _install_release_root()
                / "ops"
                / "executive_os"
                / RELAY_PLIST_TEMPLATE_NAME
            ).read_text(encoding="utf-8").encode("utf-8")
        )
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    if not isinstance(document, dict):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    environment = document.get("EnvironmentVariables")
    if not isinstance(environment, dict):
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED")
    document["ProgramArguments"] = _relay_program_arguments(release_root)
    document["WorkingDirectory"] = os.fspath(release_root)
    document["UserName"] = RELAY_USER
    document["GroupName"] = RELAY_GROUP
    environment["HOME"] = RELAY_HOME
    document["EnvironmentVariables"] = environment
    document["StandardOutPath"] = RELAY_STDOUT_PATH
    document["StandardErrorPath"] = RELAY_STDERR_PATH
    try:
        if document != _expected_relay_plist_document(release_root):
            raise ValueError
        _assert_relay_plist_document(document, code="C1_ENROLLMENT_HOST_REFUSED")
        rendered = plistlib.dumps(document, sort_keys=True)
        if _contains_placeholder(_parse_relay_plist(
            rendered, code="C1_ENROLLMENT_HOST_REFUSED"
        )):
            raise ValueError
    except C1EnrollmentError:
        raise
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_HOST_REFUSED") from None
    return rendered


def _replace_exact_file_atomic(
    path: Path,
    payload: bytes,
    *,
    uid: int,
    gid: int,
    mode: int,
) -> None:
    """Atomically replace one attested private file in place.

    Mirrors ``write_new_private_file``'s parent and attestation discipline while
    keeping the inode-backed path identity launchd already holds.  It never
    creates a missing final file, and it refuses an original that is a symlink,
    has an extra hard link, or does not already carry the expected ownership,
    mode and ACL state before the rename.  The replacement is staged under a
    collision-safe temporary name and every failure path unlinks it.
    """

    path = Path(path)
    if not path.is_absolute() or not payload or len(payload) > PLIST_MAX_BYTES:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
    try:
        parent = path.parent.lstat()
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    if stat.S_ISLNK(parent.st_mode) or not stat.S_ISDIR(parent.st_mode):
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
    try:
        if c1_runtime._path_has_acl(path.parent, expected_info=parent):  # noqa: SLF001
            raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED")
    except C1EnrollmentError:
        raise
    except Exception:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    try:
        before = path.lstat()
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    _exact_file(path, uid=uid, gid=gid, mode=mode)

    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temporary = Path(temporary_name)
        staged = os.fstat(descriptor)
        if staged.st_uid != int(uid) or staged.st_gid != int(gid):
            os.fchown(descriptor, int(uid), int(gid))
        os.fchmod(descriptor, int(mode))
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError
            view = view[written:]
        os.fsync(descriptor)
        staged = os.fstat(descriptor)
        if (
            not stat.S_ISREG(staged.st_mode)
            or staged.st_nlink != 1
            or staged.st_uid != int(uid)
            or staged.st_gid != int(gid)
            or stat.S_IMODE(staged.st_mode) != int(mode)
        ):
            raise OSError
        os.close(descriptor)
        descriptor = -1
        current = path.lstat()
        if (current.st_dev, current.st_ino, current.st_nlink) != (
            before.st_dev,
            before.st_ino,
            before.st_nlink,
        ):
            raise OSError
        os.replace(temporary, path)
        temporary = None
        _fsync_parent(path)
        after = path.lstat()
        if after.st_dev != staged.st_dev or after.st_ino != staged.st_ino:
            raise OSError
    except C1EnrollmentError:
        raise
    except OSError:
        raise C1EnrollmentError("C1_ENROLLMENT_WRITE_REFUSED") from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
    _exact_file(path, uid=uid, gid=gid, mode=mode)


@dataclass(frozen=True)
class _RebindTarget:
    bot_user_id: str
    release_sha: str
    plist_bytes: bytes
    config_bytes: bytes

    def writes(self) -> tuple[tuple[Path, bytes, int, int, int], ...]:
        return (
            (
                RELAY_PLIST,
                self.plist_bytes,
                RELAY_PLIST_UID,
                RELAY_PLIST_GID,
                PLIST_MODE,
            ),
            (
                c1_runtime.CONFIG_PATH,
                self.config_bytes,
                RELAY_CONFIG_UID,
                RELAY_CONFIG_GID,
                CONFIG_MODE,
            ),
        )


def _load_rebind_config(*, code: str) -> c1_runtime.C1RuntimeConfig:
    """Reuse the existing closed config owner; never surface INTERNAL."""

    try:
        return c1_runtime.load_config(
            c1_runtime.CONFIG_PATH,
            expected_path=c1_runtime.CONFIG_PATH,
            expected_owner_uid=RELAY_CONFIG_UID,
            expected_group_gid=RELAY_GID,
        )
    except Exception:
        raise C1EnrollmentError(code) from None


def _attest_token() -> _PrivateFileAttestation:
    """Attest the credential identity without ever exposing its bytes."""

    _raw, attestation = _attest_private_bytes(
        c1_runtime.TOKEN_PATH,
        uid=RELAY_UID,
        gid=RELAY_GID,
        mode=TOKEN_MODE,
        max_bytes=MAX_TOKEN_BYTES,
        code="C1_REBIND_TOKEN_REFUSED",
    )
    return attestation


def _stage_rebind_target(*, bot_user_id: str, release_sha: str) -> _RebindTarget:
    """Stage and validate both target documents before the first mutation."""

    plist_bytes = _render_relay_plist(_install_release_root())
    _assert_relay_plist_document(
        _parse_relay_plist(plist_bytes, code="C1_REBIND_PLIST_REFUSED"),
        code="C1_REBIND_PLIST_REFUSED",
    )
    config_document = build_config_document(
        bot_user_id=bot_user_id,
        release_sha=release_sha,
    )
    config_bytes = _canonical_config_bytes(config_document)
    try:
        staged_document = json.loads(config_bytes.decode("utf-8"))
    except Exception:
        raise C1EnrollmentError("C1_REBIND_STALE_CONFIG") from None
    if (
        not isinstance(staged_document, dict)
        or _canonical_config_bytes(staged_document) != config_bytes
    ):
        raise C1EnrollmentError("C1_REBIND_STALE_CONFIG")
    return _RebindTarget(
        bot_user_id=bot_user_id,
        release_sha=release_sha,
        plist_bytes=plist_bytes,
        config_bytes=config_bytes,
    )


def _read_rebind_pair() -> tuple[bytes | None, bytes | None]:
    """Fresh attested read of both durable files; None means unreadable."""

    return (
        _try_attest_private_bytes(
            RELAY_PLIST,
            uid=RELAY_PLIST_UID,
            gid=RELAY_PLIST_GID,
            mode=PLIST_MODE,
            max_bytes=PLIST_MAX_BYTES,
        ),
        _try_attest_private_bytes(
            c1_runtime.CONFIG_PATH,
            uid=RELAY_CONFIG_UID,
            gid=RELAY_CONFIG_GID,
            mode=CONFIG_MODE,
            max_bytes=CONFIG_MAX_BYTES,
        ),
    )


def _converge_rebind_pair(target: _RebindTarget) -> C1EnrollmentError | None:
    """Drive both durable files to the exact staged target bytes.

    Returns the first typed write failure, or None when the durable pair is the
    staged target.  A write that raised may still have committed, so callers
    always reconcile against a fresh durable read instead of trusting the raise.
    """

    for path, payload, uid, gid, mode in target.writes():
        if (
            _try_attest_private_bytes(
                path,
                uid=uid,
                gid=gid,
                mode=mode,
                max_bytes=PLIST_MAX_BYTES,
            )
            == payload
        ):
            continue
        try:
            _replace_exact_file_atomic(path, payload, uid=uid, gid=gid, mode=mode)
        except C1EnrollmentError as exc:
            return exc
    return None


def _restore_rebind_pair(
    target: _RebindTarget,
    plist_preimage: bytes,
    config_preimage: bytes,
    *,
    entry_coherent: bool,
    fallback: BaseException | None,
) -> None:
    """Prove one coherent generation, or report effect-uncertain.

    A clean refusal is reported only after a fresh read proves BOTH durable
    files are the exact entry preimages again.  A mixed entry generation has no
    coherent preimage to restore, so it is never reported as a rollback.  A
    durable pair that is provably half of each generation is reported as a
    typed mixed generation; anything else is effect-uncertain.
    """

    if entry_coherent:
        for path, payload, uid, gid, mode in (
            (
                RELAY_PLIST,
                plist_preimage,
                RELAY_PLIST_UID,
                RELAY_PLIST_GID,
                PLIST_MODE,
            ),
            (
                c1_runtime.CONFIG_PATH,
                config_preimage,
                RELAY_CONFIG_UID,
                RELAY_CONFIG_GID,
                CONFIG_MODE,
            ),
        ):
            if (
                _try_attest_private_bytes(
                    path,
                    uid=uid,
                    gid=gid,
                    mode=mode,
                    max_bytes=PLIST_MAX_BYTES,
                )
                == payload
            ):
                continue
            try:
                _replace_exact_file_atomic(path, payload, uid=uid, gid=gid, mode=mode)
            except C1EnrollmentError:
                break
        else:
            if _read_rebind_pair() == (plist_preimage, config_preimage):
                raise C1EnrollmentError("C1_REBIND_WRITE_REFUSED") from fallback
    current = _read_rebind_pair()
    if (
        current[0] in (plist_preimage, target.plist_bytes)
        and current[1] in (config_preimage, target.config_bytes)
        and None not in current
    ):
        raise C1EnrollmentError("C1_REBIND_MIXED_GENERATION") from fallback
    raise C1EnrollmentError("C1_REBIND_EFFECT_UNCERTAIN") from fallback


def _validate_rebind_pair(
    target: _RebindTarget,
    token_attestation: _PrivateFileAttestation,
) -> None:
    """Post-write proof that both durable files are the exact new generation."""

    plist_bytes, config_bytes = _read_rebind_pair()
    if plist_bytes != target.plist_bytes or config_bytes != target.config_bytes:
        raise C1EnrollmentError("C1_REBIND_EFFECT_UNCERTAIN")
    observed_root = _assert_relay_plist_document(
        _parse_relay_plist(plist_bytes, code="C1_REBIND_EFFECT_UNCERTAIN"),
        code="C1_REBIND_EFFECT_UNCERTAIN",
    )
    if os.fspath(observed_root) != os.fspath(_install_release_root()):
        raise C1EnrollmentError("C1_REBIND_EFFECT_UNCERTAIN")
    config = _load_rebind_config(code="C1_REBIND_EFFECT_UNCERTAIN")
    if (
        config.relay_version != target.release_sha
        or config.slack_bot_user_id != target.bot_user_id
    ):
        raise C1EnrollmentError("C1_REBIND_EFFECT_UNCERTAIN")
    if _attest_token() != token_attestation:
        raise C1EnrollmentError("C1_REBIND_TOKEN_DRIFT")


async def _rebind(*, bot_user_id: str) -> dict[str, object]:
    """Rebind one complete existing enrollment to the installed release.

    This is not enrollment.  It never qualifies, reads out or rewrites the
    credential, never calls a provider, and never enables, bootstraps,
    kickstarts or starts a service.
    """

    release_sha = _relay_substrate()
    _assert_services_stopped("C1_REBIND_SERVICE_RUNNING")
    if not _path_present(c1_runtime.TOKEN_PATH) or not _path_present(
        c1_runtime.CONFIG_PATH
    ):
        raise C1EnrollmentError("C1_REBIND_PARTIAL_STATE")

    token_attestation = _attest_token()
    plist_preimage, _plist_attestation = _attest_private_bytes(
        RELAY_PLIST,
        uid=RELAY_PLIST_UID,
        gid=RELAY_PLIST_GID,
        mode=PLIST_MODE,
        max_bytes=PLIST_MAX_BYTES,
        code="C1_REBIND_PLIST_REFUSED",
    )
    config_preimage, _config_attestation = _attest_private_bytes(
        c1_runtime.CONFIG_PATH,
        uid=RELAY_CONFIG_UID,
        gid=RELAY_CONFIG_GID,
        mode=CONFIG_MODE,
        max_bytes=CONFIG_MAX_BYTES,
        code="C1_REBIND_STALE_CONFIG",
    )
    old_release_root = _assert_relay_plist_document(
        _parse_relay_plist(plist_preimage, code="C1_REBIND_PLIST_REFUSED"),
        code="C1_REBIND_PLIST_REFUSED",
    )
    old_release = old_release_root.name
    old_config = _load_rebind_config(code="C1_REBIND_STALE_CONFIG")
    if old_config.slack_bot_user_id != bot_user_id:
        raise C1EnrollmentError("C1_REBIND_STALE_CONFIG")
    config_release = old_config.relay_version
    if old_release == config_release:
        if old_release == release_sha:
            return {
                "action": "already-current",
                "bot_user_id": bot_user_id,
                "release_sha": release_sha,
            }
        entry_coherent = True
    elif release_sha in (old_release, config_release):
        # A crash between the two renames: one durable file is already forward.
        entry_coherent = False
    else:
        raise C1EnrollmentError("C1_REBIND_VERSION_MISMATCH")

    target = _stage_rebind_target(bot_user_id=bot_user_id, release_sha=release_sha)
    _assert_services_stopped("C1_REBIND_SERVICE_RUNNING")

    failure = _converge_rebind_pair(target)
    if failure is not None and _read_rebind_pair() != (
        target.plist_bytes,
        target.config_bytes,
    ):
        # The failing write did not (or could not) commit the intended bytes.
        _restore_rebind_pair(
            target,
            plist_preimage,
            config_preimage,
            entry_coherent=entry_coherent,
            fallback=failure,
        )
    try:
        _validate_rebind_pair(target, token_attestation)
    except C1EnrollmentError as exc:
        _restore_rebind_pair(
            target,
            plist_preimage,
            config_preimage,
            entry_coherent=entry_coherent,
            fallback=exc,
        )
    _assert_services_stopped("C1_REBIND_SERVICE_RUNNING")
    return {
        "action": "rebound",
        "bot_user_id": bot_user_id,
        "release_sha": release_sha,
    }


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
        mode=TOKEN_MODE,
    )
    config = build_config_document(bot_user_id=bot_user_id, release_sha=release_sha)
    write_new_private_file(
        c1_runtime.CONFIG_PATH,
        _canonical_config_bytes(config),
        uid=RELAY_CONFIG_UID,
        gid=RELAY_CONFIG_GID,
        mode=CONFIG_MODE,
    )
    c1_runtime.load_config(
        c1_runtime.CONFIG_PATH,
        expected_path=c1_runtime.CONFIG_PATH,
        expected_owner_uid=RELAY_CONFIG_UID,
        expected_group_gid=RELAY_GID,
    )
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
        uid=RELAY_CONFIG_UID,
        gid=RELAY_CONFIG_GID,
        mode=CONFIG_MODE,
    )
    c1_runtime.load_config(
        c1_runtime.CONFIG_PATH,
        expected_path=c1_runtime.CONFIG_PATH,
        expected_owner_uid=RELAY_CONFIG_UID,
        expected_group_gid=RELAY_GID,
    )
    return {**qualification, "action": "resumed", "release_sha": release_sha}


async def _verify(*, bot_user_id: str) -> dict[str, object]:
    release_sha = _assert_host_prepared()
    if not _path_present(c1_runtime.TOKEN_PATH) or not _path_present(
        c1_runtime.CONFIG_PATH
    ):
        raise C1EnrollmentError("C1_ENROLLMENT_EXISTING_REFUSED")
    config = c1_runtime.load_config(
        c1_runtime.CONFIG_PATH,
        expected_path=c1_runtime.CONFIG_PATH,
        expected_owner_uid=RELAY_CONFIG_UID,
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
        elif args.command == "rebind-release":
            receipt = asyncio.run(_rebind(bot_user_id=args.expected_bot_user_id))
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
