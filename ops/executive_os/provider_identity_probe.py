"""Secret-free Codex App Server identity probe for the Executive worker.

The credential stays opaque in the dedicated ``CODEX_HOME``.  The live probe
classifies the pinned CLI's exact, non-secret ``login status`` output, then
starts the pinned Codex App Server as the disabled worker principal and requests
``account/read(refreshToken:false)``.  Only the small, reviewed classification
returned by :func:`evaluate_identity` may leave this process; email, account
identifiers, raw JSON-RPC frames, and unreviewed stderr are never emitted or
persisted.

``--compare-seat-stdin`` is a separate opt-in diagnostic.  It reads exactly
one expected account email from a private bounded pipe and prints only
``MATCH``, ``MISMATCH`` or ``UNKNOWN``.  That expected email is never taken
from argv, environment, or a file, is never forwarded to a child process,
and is never persisted or echoed back.

``--refusal-code-stdin`` is an offline formatter for the provisioner's failed
probe document. It reads at most 16 KiB plus one overflow byte and prints one
closed refusal code. It never initiates a live probe or opens a credential.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import select
import stat
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

_RELEASE_ROOT = Path(__file__).resolve().parents[2]
if os.fspath(_RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_RELEASE_ROOT))

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if __package__ in {None, ""} and str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

try:
    from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
    from ops.executive_os.provider_identity_policy import (
        COMPANY_WORKSPACE_BINDING_CLASS,
        EXPECTED_AUTH_MODE,
        evaluate_identity_policy,
    )
except ModuleNotFoundError:  # pragma: no cover - installed direct-script mode
    from provider_identity_policy import (  # type: ignore[no-redef]
        COMPANY_WORKSPACE_BINDING_CLASS,
        EXPECTED_AUTH_MODE,
        evaluate_identity_policy,
    )


SCHEMA_VERSION = "mastermind.executive_provider_identity/v1"
REFUSAL_CODE_FLAG = "--refusal-code-stdin"
_REFUSAL_DOCUMENT_MAX_BYTES = 16 * 1024
# These codes are observations, never authority to retry or requalify identity.
# Do not accept arbitrary exception messages or merely regex-shaped strings.
IDENTITY_REFUSAL_CODES = frozenset({
    "identity_probe_failed", "live_probe_requires_darwin_root",
    "binary_acl_invalid", "binary_metadata_invalid", "binary_sha256_invalid",
    "binary_signature_invalid", "binary_team_invalid", "binary_version_invalid",
    "credential_metadata_invalid", "worker_identity_invalid",
    "app_server_closed", "app_server_timeout", "app_server_malformed",
    "app_server_request_failed", "login_status_unreviewed",
    "forced_auth_configuration_present", "login_status_changed_during_probe",
    "binary_identity_changed_during_probe", "credential_identity_changed_during_probe",
    "credential_kind_unknown", "auth_mode_missing_or_unknown", "auth_mode_policy_mismatch",
    "account_read_malformed", "account_read_spoofed_auth_mode", "account_missing",
    "account_type_not_chatgpt", "plan_type_missing", "openai_auth_requirement_malformed",
    "company_plan_required", "personal_pro_device_auth_required",
    "personal_pro_plan_required", "workspace_binding_class_unknown",
})
PINNED_CODEX_VERSION = "0.159.2"
WORKER_USER = "_mastermind_worker"
WORKER_GROUP = "_mastermind_worker"
PROVIDER_HOME = Path("/var/db/mastermind-executive/workers/codex-01/provider-home")
INSTALLED_CODEX_BINARY = Path(
    "/Library/Application Support/MastermindExecutive/bin/codex-0.159.2"
)
PINNED_CODEX_SHA256 = "16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704"
PINNED_CODEX_TEAM_ID = "2DC432GLL2"
WORKSPACE_BINDING_CLASS = COMPANY_WORKSPACE_BINDING_CLASS
WORKER_UID = 451
WORKER_GID = 451
# These strings are the complete stderr contract in the pinned Codex 0.159.2
# ``run_login_status`` implementation.  API-key status contains a redacted key
# fragment and every unreviewed/future string is deliberately rejected.
_ARG0_CLEANUP_WARNING = (
    b"WARNING: failed to clean up stale arg0 temp dirs: Permission denied (os error 13)\n"
)

LOGIN_STATUS_AUTH_MODE = {
    b"Logged in using access token\n": "agentIdentity",
    b"Logged in using personal access token\n": "personalAccessToken",
    b"Logged in using ChatGPT\n": "chatgpt",
}
_FORCED_CONFIG_KEYS = frozenset(
    {"forced_chatgpt_workspace_id", "forced_login_method"}
)
_AUTH_STORE_KEY = "cli_auth_credentials_store"

# Opt-in, secret-free seat equality diagnostic.  The complete stdout contract in
# that mode is one of these three uppercase words; nothing else may be emitted.
COMPARE_SEAT_FLAG = "--compare-seat-stdin"
SEAT_MATCH = "MATCH"
SEAT_MISMATCH = "MISMATCH"
SEAT_UNKNOWN = "UNKNOWN"
# A 254-byte canonical email plus one optional trailing LF is the only accepted
# stdin shape.  Anything longer, or any read still open at the deadline, is
# refused without inspection.
_SEAT_EMAIL_MAX_BYTES = 254
_SEAT_LOCAL_PART_MAX_BYTES = 64
_SEAT_DOMAIN_LABEL_MAX_BYTES = 63
_SEAT_INPUT_MAX_BYTES = _SEAT_EMAIL_MAX_BYTES + 1
_SEAT_INPUT_TIMEOUT_SECONDS = 5.0
_SEAT_ATEXT = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_SEAT_LOCAL_PART_RE = re.compile(rf"{_SEAT_ATEXT}(?:\.{_SEAT_ATEXT})*")
_SEAT_DOMAIN_LABEL_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


class IdentityProbeError(RuntimeError):
    """A bounded, non-secret identity refusal."""


def _bounded_refusal_code(value: Any) -> str:
    if type(value) is str and value in IDENTITY_REFUSAL_CODES:
        return value
    return "identity_probe_failed"


def bounded_refusal_from_document(value: Any) -> str:
    """Project only a reviewed code; discard all identity/account/error fields."""
    if (type(value) is not dict or value.get("schema_version") != SCHEMA_VERSION
            or value.get("passed") is not False):
        return "identity_probe_failed"
    return _bounded_refusal_code(value.get("refusal"))


def _unique_diagnostic_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate diagnostic field")
        result[key] = value
    return result


def _refusal_code_main(tokens: Sequence[str]) -> int:
    code = "identity_probe_failed"
    if list(tokens) == [REFUSAL_CODE_FLAG]:
        try:
            payload = sys.stdin.buffer.read(_REFUSAL_DOCUMENT_MAX_BYTES + 1)
            if len(payload) <= _REFUSAL_DOCUMENT_MAX_BYTES:
                code = bounded_refusal_from_document(json.loads(
                    payload, object_pairs_hook=_unique_diagnostic_fields
                ))
        except (Exception, SystemExit, KeyboardInterrupt):
            # Never echo malformed input, exception text, or a traceback.
            pass
    try:
        sys.stdout.write(code + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        return 2
    return 0


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_no_macos_acl(path: Path) -> None:
    try:
        present = has_macos_acl(path)
    except FilesystemSecurityError:
        raise IdentityProbeError("binary_acl_invalid")
    if present:
        raise IdentityProbeError("binary_acl_invalid")


def binary_identity(path: Path) -> dict[str, Any]:
    info = path.lstat()
    if (
        info.st_uid != 0
        or info.st_gid != 0
        or not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or (info.st_mode & 0o777) != 0o555
        or info.st_nlink != 1
    ):
        raise IdentityProbeError("binary_metadata_invalid")
    _assert_no_macos_acl(path)
    digest = _sha256_file(path)
    if digest != PINNED_CODEX_SHA256:
        raise IdentityProbeError("binary_sha256_invalid")
    verify = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", os.fspath(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if verify.returncode != 0:
        raise IdentityProbeError("binary_signature_invalid")
    detail = subprocess.run(
        ["/usr/bin/codesign", "-dv", "--verbose=4", os.fspath(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    team = ""
    for line in detail.stderr.splitlines():
        if line.startswith("TeamIdentifier="):
            team = line.split("=", 1)[1]
    if team != PINNED_CODEX_TEAM_ID:
        raise IdentityProbeError("binary_team_invalid")
    version_output = subprocess.run(
        [os.fspath(path), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    ).stdout.split()
    version = version_output[1] if len(version_output) == 2 and version_output[0] == "codex-cli" else ""
    if version != PINNED_CODEX_VERSION:
        raise IdentityProbeError("binary_version_invalid")
    return {
        "path": os.fspath(path),
        "version": version,
        "sha256": digest,
        "team_identifier": team,
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mode": int(info.st_mode & 0o777),
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "ctime_ns": int(info.st_ctime_ns),
        "nlink": int(info.st_nlink),
    }


def credential_identity(
    path: Path,
    *,
    worker_uid: int = WORKER_UID,
    worker_gid: int = WORKER_GID,
) -> dict[str, int]:
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != worker_uid
        or info.st_gid != worker_gid
        or (info.st_mode & 0o777) != 0o600
        or info.st_nlink != 1
        or info.st_size <= 0
    ):
        raise IdentityProbeError("credential_metadata_invalid")
    _assert_no_macos_acl(path)
    return {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "uid": int(info.st_uid),
        "gid": int(info.st_gid),
        "mode": int(info.st_mode & 0o777),
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "ctime_ns": int(info.st_ctime_ns),
        "nlink": int(info.st_nlink),
    }


def _refusal(code: str, *, expected_kind: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": False,
        "refusal": code,
        "expected_credential_kind": expected_kind,
        "auth_mode": "UNKNOWN",
        "account_type": "UNKNOWN",
        "plan_type": "UNKNOWN",
        "requires_openai_auth": None,
        "workspace_binding_class": "UNATTESTED",
    }


def _account_read(result: Mapping[str, Any] | None) -> tuple[str, str, bool] | str:
    """Validate the exact safe portion of v2/GetAccountResponse.

    A top-level ``authMode`` is a known fake/spoofed shape.  We deliberately do
    not return the ChatGPT account's optional email field.
    """

    if not isinstance(result, Mapping):
        return "account_read_malformed"
    if "authMode" in result:
        return "account_read_spoofed_auth_mode"
    requires = result.get("requiresOpenaiAuth")
    if not isinstance(requires, bool):
        return "account_read_malformed"
    account = result.get("account")
    if not isinstance(account, Mapping):
        return "account_missing"
    account_type = account.get("type")
    if account_type != "chatgpt":
        return "account_type_not_chatgpt"
    plan_type = account.get("planType")
    if not isinstance(plan_type, str) or not plan_type:
        return "plan_type_missing"
    return (account_type, plan_type, requires)


def classify_login_status(*, returncode: int, stderr: bytes) -> str | None:
    """Map only exact pinned, identifier-free status strings to an auth mode."""

    if returncode != 0:
        return None
    payload = bytes(stderr)
    if payload.startswith(_ARG0_CLEANUP_WARNING):
        payload = payload[len(_ARG0_CLEANUP_WARNING):]
    return LOGIN_STATUS_AUTH_MODE.get(payload)


def config_has_no_forced_auth_policy(value: Mapping[str, Any] | None) -> bool:
    """Prove forced-auth absence and the exact session-scoped file auth store.

    Raw config, origins, paths, and managed-layer identifiers never leave this
    function.  An underlying user/system credential-store preference may exist,
    but the App Server used for this proof must visibly override it in the
    session layer and report ``file`` as the effective value.
    """

    if not isinstance(value, Mapping):
        return False
    config = value.get("config")
    origins = value.get("origins")
    layers = value.get("layers")
    if not isinstance(config, Mapping) or not isinstance(origins, Mapping):
        return False
    if not isinstance(layers, list):
        return False
    if config.get(_AUTH_STORE_KEY) != "file":
        return False
    store_origin = origins.get(_AUTH_STORE_KEY)
    if not isinstance(store_origin, Mapping):
        return False
    store_origin_name = store_origin.get("name")
    if not isinstance(store_origin_name, Mapping):
        return False
    if store_origin_name.get("type") != "sessionFlags":
        return False
    if any(config.get(key) is not None for key in _FORCED_CONFIG_KEYS):
        return False
    if any(key in origins for key in _FORCED_CONFIG_KEYS):
        return False
    session_store_layers = 0
    for layer in layers:
        if not isinstance(layer, Mapping):
            return False
        source = layer.get("name")
        layer_config = layer.get("config")
        if not isinstance(source, Mapping) or not isinstance(layer_config, Mapping):
            return False
        if source.get("type") == "project":
            return False
        if any(key in layer_config for key in _FORCED_CONFIG_KEYS):
            return False
        if source.get("type") == "sessionFlags":
            if layer_config.get(_AUTH_STORE_KEY) != "file":
                return False
            session_store_layers += 1
    return session_store_layers == 1


def evaluate_identity(
    *,
    account_read: Mapping[str, Any] | None,
    auth_mode: str | None,
    expected_kind: str,
    workspace_binding_class: str,
) -> dict[str, Any]:
    """Return a sanitized policy verdict without retaining provider identity."""

    if expected_kind not in EXPECTED_AUTH_MODE:
        return _refusal("credential_kind_unknown", expected_kind=expected_kind)
    account = _account_read(account_read)
    if isinstance(account, str):
        return _refusal(account, expected_kind=expected_kind)
    if auth_mode not in EXPECTED_AUTH_MODE.values():
        return _refusal("auth_mode_missing_or_unknown", expected_kind=expected_kind)
    account_type, account_plan, requires = account
    safe = {
        "schema_version": SCHEMA_VERSION,
        "passed": False,
        "refusal": None,
        "expected_credential_kind": expected_kind,
        "auth_mode": auth_mode,
        "account_type": account_type,
        "plan_type": account_plan,
        "requires_openai_auth": requires,
        "workspace_binding_class": workspace_binding_class,
    }
    refusal = evaluate_identity_policy(
        expected_kind=expected_kind,
        auth_mode=auth_mode,
        account_type=account_type,
        plan_type=account_plan,
        requires_openai_auth=requires,
        workspace_binding_class=workspace_binding_class,
    )
    if refusal is None:
        safe["passed"] = True
    else:
        safe["refusal"] = refusal
    return safe


class _SeatArgumentRefusal(IdentityProbeError):
    """A bounded comparison-mode argument refusal that prints nothing."""


class _SeatArgumentParser(argparse.ArgumentParser):
    """Parser for comparison mode: no help, usage, argv, or error details."""

    def error(self, message: str) -> NoReturn:
        raise _SeatArgumentRefusal("seat_arguments_invalid")

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        raise _SeatArgumentRefusal("seat_arguments_invalid")


def _seat_canonical_email(value: Any) -> str | None:
    """Return an exact ASCII dot-atom email, or ``None`` when unsupported.

    There is deliberately no normalization, case folding, alias stripping,
    substring matching, or seat-label inference.  Display names, quoted forms,
    comments, Unicode, whitespace, control characters, empty dot atoms, and
    over-long local parts, labels, or totals are all unsupported.
    """

    if not isinstance(value, str) or not value.isascii():
        return None
    if len(value) > _SEAT_EMAIL_MAX_BYTES or value.count("@") != 1:
        return None
    local, _, domain = value.partition("@")
    if not local or len(local) > _SEAT_LOCAL_PART_MAX_BYTES:
        return None
    if _SEAT_LOCAL_PART_RE.fullmatch(local) is None:
        return None
    labels = domain.split(".")
    if len(labels) < 2:
        return None
    for label in labels:
        if not label or len(label) > _SEAT_DOMAIN_LABEL_MAX_BYTES:
            return None
        if _SEAT_DOMAIN_LABEL_RE.fullmatch(label) is None:
            return None
    return value


def _decode_seat_input(raw: bytes) -> str | None:
    """Validate one optional trailing-LF stdin payload without persisting it."""

    data = bytes(raw)
    if data.endswith(b"\n"):
        data = data[:-1]
    if not data or b"\n" in data or b"\r" in data:
        return None
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None
    return _seat_canonical_email(text)


def _read_expected_seat_email(
    stdin: Any = None,
    *,
    timeout_seconds: float = _SEAT_INPUT_TIMEOUT_SECONDS,
) -> str | None:
    """Read the expected seat email from bounded private pipe stdin only.

    A TTY, a regular file, any non-pipe descriptor, an oversized payload,
    a second line, and a still-open pipe at the finite
    deadline all yield ``None``, which the caller reports as ``UNKNOWN``.
    """

    stream = sys.stdin if stdin is None else stdin
    try:
        if stream.isatty():
            return None
        descriptor = int(stream.fileno())
        info = os.fstat(descriptor)
    except (AttributeError, OSError, ValueError, TypeError):
        return None
    if not stat.S_ISFIFO(info.st_mode):
        return None
    payload = bytearray()
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while len(payload) < _SEAT_INPUT_MAX_BYTES + 1:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            ready, _, _ = select.select([descriptor], [], [], remaining)
        except (OSError, ValueError):
            return None
        if not ready:
            return None
        try:
            chunk = os.read(descriptor, _SEAT_INPUT_MAX_BYTES + 1 - len(payload))
        except OSError:
            return None
        if not chunk:
            break
        payload.extend(chunk)
    if len(payload) > _SEAT_INPUT_MAX_BYTES:
        return None
    return _decode_seat_input(payload)


def _compare_expected_seat(*, account_read: Any, expected_email: Any) -> str:
    """Classify observed-versus-expected seat equality as a bounded enum.

    Both sides must be independently valid canonical emails.  Anything missing,
    malformed, unsupported, or unavailable is conservative ``UNKNOWN``; a verdict
    is never a success claim on its own.
    """

    expected = _seat_canonical_email(expected_email)
    if expected is None:
        return SEAT_UNKNOWN
    if isinstance(_account_read(account_read), str):
        return SEAT_UNKNOWN
    account = account_read.get("account")
    if not isinstance(account, Mapping):
        return SEAT_UNKNOWN
    observed = _seat_canonical_email(account.get("email"))
    if observed is None:
        return SEAT_UNKNOWN
    if observed == expected:
        return SEAT_MATCH
    return SEAT_MISMATCH


def _seat_verdict(value: Any) -> str:
    """Collapse any non-enum comparison value to ``UNKNOWN``."""

    if value == SEAT_MATCH:
        return SEAT_MATCH
    if value == SEAT_MISMATCH:
        return SEAT_MISMATCH
    return SEAT_UNKNOWN


class _Client:
    """Minimal line-delimited JSON-RPC client that never records stderr."""

    def __init__(self, argv: Sequence[str], env: Mapping[str, str], cwd: Path) -> None:
        self._proc = subprocess.Popen(
            list(argv),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=os.fspath(cwd),
            env=dict(env),
        )
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        # Reader threads must never render an unreviewed transport exception.
        try:
            assert self._proc.stdout is not None
            for raw in self._proc.stdout:
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._messages.put({"_malformed": True})
                    continue
                self._messages.put(value if isinstance(value, dict) else {"_malformed": True})
        except BaseException:
            self._messages.put({"_malformed": True})
        finally:
            self._messages.put(None)

    def _send(self, value: Mapping[str, Any]) -> None:
        if self._proc.stdin is None:
            raise IdentityProbeError("app_server_closed")
        self._proc.stdin.write((json.dumps(dict(value)) + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def notify(self, method: str) -> None:
        self._send({"method": method})

    def request(self, request_id: int, method: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
        self._send({"id": request_id, "method": method, "params": None if params is None else dict(params)})
        deadline = time.monotonic() + 15.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise IdentityProbeError("app_server_timeout")
            try:
                message = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise IdentityProbeError("app_server_timeout") from exc
            if message is None or message.get("_malformed"):
                raise IdentityProbeError("app_server_malformed")
            if message.get("id") == request_id:
                if "error" in message or not isinstance(message.get("result"), dict):
                    raise IdentityProbeError("app_server_request_failed")
                return dict(message["result"])

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=3.0)


MODEL_CAPACITY_FLAG = "--model-capacity-diagnostic"
MODEL_CAPACITY_SCHEMA = "mastermind.executive_provider_model_capacity_diagnostic/v1"
_DIAGNOSTIC_REFUSALS = frozenset({
    "diagnostic_arguments_invalid", "diagnostic_payload_invalid", "diagnostic_probe_failed",
})

# Internal, transaction-bound recovery observation.  Unlike the exported
# capacity diagnostic above, this document is bound to one designated successor
# request, the live installed source, the live credential metadata and one
# observation time, and it is consumable only by the readiness transaction that
# named that request.  It is never a readiness receipt and never a standalone
# authorization.
RECOVERY_OBSERVATION_FLAG = "--recovery-observation"
RECOVERY_OBSERVATION_SCHEMA = "mastermind.executive_provider_recovery_observation/v1"
_RECOVERY_OBSERVATION_REFUSALS = frozenset({
    "recovery_observation_arguments_invalid", "recovery_observation_payload_invalid",
    "recovery_observation_probe_failed",
})
_RECOVERY_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


def _diagnostic_code(value: Any) -> str:
    if type(value) is str and value in IDENTITY_REFUSAL_CODES | _DIAGNOSTIC_REFUSALS:
        return value
    return "diagnostic_probe_failed"


def _diagnostic_window(value: Any) -> dict[str, int | None] | None:
    if value is None:
        return None
    if type(value) is not dict:
        raise IdentityProbeError("diagnostic_payload_invalid")
    result = {}
    for source, target, maximum, minimum in (
        ("usedPercent", "used_percent", 100, 0),
        ("windowDurationMins", "window_duration_mins", 2**31 - 1, 1),
        ("resetsAt", "resets_at", 2**53 - 1, 0),
    ):
        item = value.get(source)
        if item is None and source != "usedPercent":
            result[target] = None
        elif type(item) is int and minimum <= item <= maximum:
            result[target] = item
        else:
            raise IdentityProbeError("diagnostic_payload_invalid")
    return result


def normalize_model_capacity(models: Any, limits: Any) -> dict[str, Any]:
    """Project two bounded read results; never infer execution or recovery authority."""
    from ops.executive_os.provider_readiness import PRODUCTION_MODEL

    if type(models) is not dict or type(limits) is not dict:
        raise IdentityProbeError("diagnostic_payload_invalid")
    rows, cursor = models.get("data"), models.get("nextCursor")
    if (type(rows) is not list or len(rows) > 100
            or (cursor is not None and (type(cursor) is not str or not 0 < len(cursor) <= 4096))):
        raise IdentityProbeError("diagnostic_payload_invalid")
    matches = 0
    for row in rows:
        if (type(row) is not dict or type(row.get("model")) is not str
                or not 0 < len(row["model"]) <= 256):
            raise IdentityProbeError("diagnostic_payload_invalid")
        matches += row["model"] == PRODUCTION_MODEL
    if matches > 1:
        raise IdentityProbeError("diagnostic_payload_invalid")
    permission = limits.get("ordinaryUsageAllowed")
    if permission is not None and type(permission) is not bool:
        raise IdentityProbeError("diagnostic_payload_invalid")
    buckets = limits.get("rateLimitsByLimitId")
    if buckets is not None and type(buckets) is not dict:
        raise IdentityProbeError("diagnostic_payload_invalid")
    if buckets is not None and "codex" in buckets:
        snapshot, source = buckets["codex"], "codex"
        if type(snapshot) is not dict:
            raise IdentityProbeError("diagnostic_payload_invalid")
    else:
        snapshot = limits.get("rateLimits")
        source = "legacy" if snapshot is not None else "unknown"
    if snapshot is not None and type(snapshot) is not dict:
        raise IdentityProbeError("diagnostic_payload_invalid")
    snapshot = {} if snapshot is None else snapshot
    return {
        "model_catalog": {"listed_in_returned_page": matches == 1, "complete": cursor is None},
        "capacity": {"ordinary_usage_allowed": permission, "source_bucket": source,
                     "primary": _diagnostic_window(snapshot.get("primary")),
                     "secondary": _diagnostic_window(snapshot.get("secondary"))},
    }


def diagnostic_document(slot_id: str | None, observation: dict[str, Any] | None = None,
                        *, refusal: str | None = None) -> dict[str, Any]:
    from ops.executive_os.provider_readiness import PRODUCTION_MODEL

    return {
        "schema_version": MODEL_CAPACITY_SCHEMA, "diagnostic_only": True, "readiness_issued": False,
        "observation_status": "observed" if observation is not None else "refused",
        "refusal": None if observation is not None else _diagnostic_code(refusal),
        "slot_id": slot_id, "configured_model": PRODUCTION_MODEL,
        "model_catalog": ({"listed_in_returned_page": None, "complete": None}
                          if observation is None else observation["model_catalog"]),
        "capacity": ({"ordinary_usage_allowed": None, "source_bucket": "unknown",
                      "primary": None, "secondary": None}
                     if observation is None else observation["capacity"]),
    }


def _recovery_observation_code(value: Any) -> str:
    if type(value) is str and value in IDENTITY_REFUSAL_CODES | _RECOVERY_OBSERVATION_REFUSALS:
        return value
    return "recovery_observation_probe_failed"


def recovery_observation_document(
    successor_request_id: str | None,
    slot_id: str | None,
    observation: dict[str, Any] | None,
    identity: Mapping[str, Any] | None,
    *,
    refusal: str | None = None,
) -> dict[str, Any]:
    """Project one bound observation; never a readiness receipt."""

    from ops.executive_os.provider_readiness import PRODUCTION_MODEL

    observed = observation is not None and identity is not None
    document: dict[str, Any] = {
        "schema_version": RECOVERY_OBSERVATION_SCHEMA,
        "observation_only": True,
        "readiness_issued": False,
        "observation_status": "observed" if observed else "refused",
        "refusal": None if observed else _recovery_observation_code(refusal),
        "observed_at": identity.get("observed_at") if identity is not None else now_iso(),
        "successor_request_id": successor_request_id,
        "slot_id": slot_id,
        "workspace_binding_class": (
            identity.get("workspace_binding_class") if identity is not None else "UNATTESTED"
        ),
        "expected_credential_kind": (
            identity.get("expected_credential_kind") if identity is not None else None
        ),
        "configured_model": PRODUCTION_MODEL,
        "codex_binary": identity.get("codex_binary") if identity is not None else None,
        "executive_source": identity.get("executive_source") if identity is not None else None,
        "credential_lstat": identity.get("credential_lstat") if identity is not None else None,
        "provider_identity": ({k: v for k, v in identity.items() if k != "executive_source"}
                              if observed else None),
        "ordinary_usage_allowed": None,
        "model_catalog": None,
    }
    if observed:
        document["ordinary_usage_allowed"] = observation["capacity"]["ordinary_usage_allowed"]
        document["model_catalog"] = dict(observation["model_catalog"])
    return document


def _recovery_observation_main(tokens: Sequence[str]) -> int:
    slot_id = None
    request_id = None
    try:
        from ops.executive_os.provider_worker_slots import get_slot

        if (list(tokens).count(RECOVERY_OBSERVATION_FLAG) != 1
                or any(sum(t.split("=", 1)[0] == flag for t in tokens) != 1
                       for flag in ("--slot-id", "--expected-kind", "--successor-request-id"))
                or any(token.split("=", 1)[0] in (MODEL_CAPACITY_FLAG, COMPARE_SEAT_FLAG,
                                                  REFUSAL_CODE_FLAG) for token in tokens)):
            raise IdentityProbeError("recovery_observation_arguments_invalid")
        parser = _SeatArgumentParser(allow_abbrev=False, add_help=False)
        parser.add_argument(RECOVERY_OBSERVATION_FLAG, action="store_true")
        parser.add_argument("--slot-id", required=True)
        parser.add_argument("--expected-kind", required=True, choices=sorted(EXPECTED_AUTH_MODE))
        parser.add_argument("--successor-request-id", required=True)
        args = parser.parse_args(list(tokens))
        if _RECOVERY_REQUEST_ID_RE.fullmatch(args.successor_request_id) is None:
            raise IdentityProbeError("recovery_observation_arguments_invalid")
        slot = get_slot(args.slot_id)
        if slot.provider_family != "openai" or args.expected_kind not in slot.allowed_credential_kinds:
            raise IdentityProbeError("recovery_observation_arguments_invalid")
        slot_id = slot.slot_id
        request_id = args.successor_request_id
        if sys.platform != "darwin" or os.geteuid() != 0:
            raise IdentityProbeError("live_probe_requires_darwin_root")
        observation, identity = live_probe(
            binary=INSTALLED_CODEX_BINARY, provider_home=slot.provider_home,
            expected_kind=args.expected_kind,
            workspace_binding_class=slot.workspace_binding_class,
            worker_user=slot.worker_user, worker_group=slot.worker_group,
            worker_uid=slot.worker_uid, worker_gid=slot.worker_gid,
            recovery_request_id=request_id,
        )
        result = recovery_observation_document(
            request_id, slot_id, observation, identity,
        )
    except _SeatArgumentRefusal:
        result = recovery_observation_document(
            None, None, None, None, refusal="recovery_observation_arguments_invalid"
        )
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        code = (exc.args[0] if isinstance(exc, IdentityProbeError) and len(exc.args) == 1
                else "recovery_observation_arguments_invalid" if isinstance(exc, ValueError)
                else "recovery_observation_probe_failed")
        result = recovery_observation_document(
            request_id, slot_id, None, None, refusal=_recovery_observation_code(code)
        )
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result["observation_status"] == "observed" else 2


def _model_capacity_main(tokens: Sequence[str]) -> int:
    slot_id = None
    try:
        from ops.executive_os.provider_worker_slots import get_slot

        if (list(tokens).count(MODEL_CAPACITY_FLAG) != 1
                or any(sum(t.split("=", 1)[0] == flag for t in tokens) != 1
                       for flag in ("--slot-id", "--expected-kind"))):
            raise IdentityProbeError("diagnostic_arguments_invalid")
        parser = _SeatArgumentParser(allow_abbrev=False, add_help=False)
        parser.add_argument(MODEL_CAPACITY_FLAG, action="store_true")
        parser.add_argument("--slot-id", required=True)
        parser.add_argument("--expected-kind", required=True, choices=sorted(EXPECTED_AUTH_MODE))
        args = parser.parse_args(list(tokens))
        slot = get_slot(args.slot_id)
        if slot.provider_family != "openai" or args.expected_kind not in slot.allowed_credential_kinds:
            raise IdentityProbeError("diagnostic_arguments_invalid")
        slot_id = slot.slot_id
        if sys.platform != "darwin" or os.geteuid() != 0:
            raise IdentityProbeError("live_probe_requires_darwin_root")
        result = live_probe(binary=INSTALLED_CODEX_BINARY, provider_home=slot.provider_home,
            expected_kind=args.expected_kind, workspace_binding_class=slot.workspace_binding_class,
            worker_user=slot.worker_user, worker_group=slot.worker_group,
            worker_uid=slot.worker_uid, worker_gid=slot.worker_gid, diagnostic_slot_id=slot_id)
    except _SeatArgumentRefusal:
        result = diagnostic_document(None, refusal="diagnostic_arguments_invalid")
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        code = (exc.args[0] if isinstance(exc, IdentityProbeError) and len(exc.args) == 1
                else "diagnostic_arguments_invalid" if isinstance(exc, ValueError)
                else "diagnostic_probe_failed")
        result = diagnostic_document(slot_id, refusal=_diagnostic_code(code))
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result["observation_status"] == "observed" else 2


def live_probe(
    *,
    binary: Path,
    provider_home: Path,
    expected_kind: str,
    workspace_binding_class: str,
    worker_user: str = WORKER_USER,
    worker_group: str = WORKER_GROUP,
    worker_uid: int = WORKER_UID,
    worker_gid: int = WORKER_GID,
    expected_seat_email: str | None = None,
    diagnostic_slot_id: str | None = None,
    recovery_request_id: str | None = None,
) -> dict[str, Any] | tuple[dict[str, Any] | None, dict[str, Any] | None] | str:
    if recovery_request_id is not None:
        if (diagnostic_slot_id is not None or expected_seat_email is not None
                or type(recovery_request_id) is not str
                or _RECOVERY_REQUEST_ID_RE.fullmatch(recovery_request_id) is None):
            raise IdentityProbeError("recovery_observation_arguments_invalid")
        from ops.executive_os.provider_recovery import current_executive_source
        recovery_executive_source = current_executive_source()
    if diagnostic_slot_id is not None:
        from ops.executive_os.provider_worker_slots import get_slot

        try:
            slot = get_slot(diagnostic_slot_id)
        except ValueError as exc:
            raise IdentityProbeError("diagnostic_arguments_invalid") from exc
        if (slot.provider_family != "openai" or binary != INSTALLED_CODEX_BINARY or provider_home != slot.provider_home
                or (worker_user, worker_group, worker_uid, worker_gid, workspace_binding_class)
                != (slot.worker_user, slot.worker_group, slot.worker_uid, slot.worker_gid, slot.workspace_binding_class)
                or expected_kind not in slot.allowed_credential_kinds or expected_seat_email is not None):
            raise IdentityProbeError("diagnostic_arguments_invalid")
    before_binary = binary_identity(binary)
    auth_path = provider_home / "auth.json"
    if (
        re.fullmatch(r"_[a-z0-9_]{1,63}", worker_user) is None
        or re.fullmatch(r"_[a-z0-9_]{1,63}", worker_group) is None
        or isinstance(worker_uid, bool)
        or isinstance(worker_gid, bool)
        or not 400 <= worker_uid < 500
        or not 400 <= worker_gid < 500
    ):
        raise IdentityProbeError("worker_identity_invalid")
    before_credential = credential_identity(
        auth_path, worker_uid=worker_uid, worker_gid=worker_gid
    )
    worker_prefix = [
        "/usr/bin/sudo",
        "-n",
        "-u",
        worker_user,
        "-g",
        worker_group,
        "/usr/bin/env",
        "-i",
        f"HOME={provider_home}",
        f"CODEX_HOME={provider_home}",
        f"PWD={provider_home}",
        "PATH=/usr/bin:/bin",
        "LANG=C.UTF-8",
        "LC_ALL=C.UTF-8",
        "NO_COLOR=1",
        os.fspath(binary),
    ]
    status_before = subprocess.run(
        [*worker_prefix, "login", "status", "-c", 'cli_auth_credentials_store="file"'],
        cwd=os.fspath(provider_home),
        env={},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    auth_mode_before = classify_login_status(
        returncode=status_before.returncode, stderr=status_before.stderr
    )
    if auth_mode_before is None:
        raise IdentityProbeError("login_status_unreviewed")
    argv = [
        *worker_prefix,
        "-c",
        'cli_auth_credentials_store="file"',
        "app-server",
        "--strict-config",
        "--stdio",
    ]
    client = _Client(argv, {}, provider_home)
    try:
        client.request(
            1,
            "initialize",
            {
                "clientInfo": {"name": "mastermind-provider-identity", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        client.notify("initialized")
        config_read = client.request(2, "config/read", {"includeLayers": True})
        if not config_has_no_forced_auth_policy(config_read):
            raise IdentityProbeError("forced_auth_configuration_present")
        account = client.request(3, "account/read", {"refreshToken": False})
        diagnostic_observation = None
        if diagnostic_slot_id is not None or recovery_request_id is not None:
            admitted = evaluate_identity(account_read=account, auth_mode=auth_mode_before,
                expected_kind=expected_kind, workspace_binding_class=workspace_binding_class)
            if admitted.get("passed") is True:
                diagnostic_observation = normalize_model_capacity(
                    client.request(4, "model/list", {"limit": 100, "includeHidden": False}),
                    client.request(5, "account/rateLimits/read", None),
                )
        status_after = subprocess.run(
            [*worker_prefix, "login", "status", "-c", 'cli_auth_credentials_store="file"'],
            cwd=os.fspath(provider_home),
            env={},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        auth_mode_after = classify_login_status(
            returncode=status_after.returncode, stderr=status_after.stderr
        )
        if auth_mode_after is None or auth_mode_after != auth_mode_before:
            raise IdentityProbeError("login_status_changed_during_probe")
        result = evaluate_identity(
            account_read=account,
            auth_mode=auth_mode_after,
            expected_kind=expected_kind,
            workspace_binding_class=workspace_binding_class,
        )
        after_binary = binary_identity(binary)
        if before_binary != after_binary:
            raise IdentityProbeError("binary_identity_changed_during_probe")
        after_credential = credential_identity(
            auth_path, worker_uid=worker_uid, worker_gid=worker_gid
        )
        if before_credential != after_credential:
            raise IdentityProbeError("credential_identity_changed_during_probe")
        result.update(
            {
                "observed_at": now_iso(),
                "codex_binary": after_binary,
                "credential_lstat": after_credential,
                "forced_chatgpt_workspace_id_applied": False,
            }
        )
        if diagnostic_slot_id is not None:
            return diagnostic_document(diagnostic_slot_id,
                diagnostic_observation if result.get("passed") is True else None,
                refusal=result.get("refusal"))
        if recovery_request_id is not None:
            # Only a passing, still-current identity may carry an observation.
            # Any refusal returns the bounded refusal document instead.
            if result.get("passed") is not True:
                return (None, result)
            if current_executive_source() != recovery_executive_source:
                raise IdentityProbeError("recovery_observation_source_mismatch")
            result["executive_source"] = recovery_executive_source
            return (diagnostic_observation, result)
        if expected_seat_email is not None:
            # Return only the bounded enum after every existing policy,
            # config, login, binary, and credential guard has completed, and it
            # still cannot leave this function before ``client.close()`` below.
            # Candidate equality is never a success claim on its own.
            verdict = SEAT_UNKNOWN
            if result.get("passed") is True:
                verdict = _compare_expected_seat(
                    account_read=account,
                    expected_email=expected_seat_email,
                )
            return verdict
        return result
    finally:
        client.close()


def _parser(*, compare_seat: bool = False) -> argparse.ArgumentParser:
    parser_class: Any = argparse.ArgumentParser
    keywords: dict[str, Any] = {
        "description": "Probe sanitized Executive provider identity"
    }
    if compare_seat:
        parser_class = _SeatArgumentParser
        keywords.update({"allow_abbrev": False, "add_help": False})
    parser = parser_class(**keywords)
    parser.add_argument("--binary", type=Path, default=INSTALLED_CODEX_BINARY)
    parser.add_argument("--provider-home", type=Path, default=PROVIDER_HOME)
    parser.add_argument("--worker-user", default=WORKER_USER)
    parser.add_argument("--worker-group", default=WORKER_GROUP)
    parser.add_argument("--worker-uid", type=int, default=WORKER_UID)
    parser.add_argument("--worker-gid", type=int, default=WORKER_GID)
    parser.add_argument("--expected-kind", choices=sorted(EXPECTED_AUTH_MODE), required=True)
    parser.add_argument("--workspace-binding-class", required=True)
    parser.add_argument(
        COMPARE_SEAT_FLAG,
        dest="compare_seat_stdin",
        action="store_true",
        help="Compare a private pipe-supplied account email and print MATCH, "
        "MISMATCH, or UNKNOWN only",
    )
    return parser


def _seat_compare_main(tokens: Sequence[str]) -> int:
    """Run the opt-in seat equality diagnostic with an exact three-word stdout."""

    verdict = SEAT_UNKNOWN
    try:
        if list(tokens).count(COMPARE_SEAT_FLAG) != 1:
            raise _SeatArgumentRefusal("seat_flag_invalid")
        args = _parser(compare_seat=True).parse_args(list(tokens))
        expected_email = _read_expected_seat_email()
        if expected_email is None:
            raise IdentityProbeError("seat_expected_email_unavailable")
        if sys.platform != "darwin" or os.geteuid() != 0:
            raise IdentityProbeError("live_probe_requires_darwin_root")
        result = live_probe(
            binary=args.binary,
            provider_home=args.provider_home,
            expected_kind=args.expected_kind,
            workspace_binding_class=args.workspace_binding_class,
            worker_user=args.worker_user,
            worker_group=args.worker_group,
            worker_uid=args.worker_uid,
            worker_gid=args.worker_gid,
            expected_seat_email=expected_email,
        )
        verdict = _seat_verdict(result)
    except (Exception, SystemExit, KeyboardInterrupt):  # never echo untrusted errors
        verdict = SEAT_UNKNOWN
    try:
        sys.stdout.write(verdict + "\n")
        sys.stdout.flush()
    except (OSError, ValueError):  # a failed delivery cannot report success
        return 2
    return 0 if verdict == SEAT_MATCH else 2


def main(argv: Sequence[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    if any(token.startswith("--") and (
            MODEL_CAPACITY_FLAG.startswith(token.split("=", 1)[0])
            or token.split("=", 1)[0].startswith(MODEL_CAPACITY_FLAG)) for token in tokens):
        return _model_capacity_main(tokens)
    if any(token.startswith("--") and (
            RECOVERY_OBSERVATION_FLAG.startswith(token.split("=", 1)[0])
            or token.split("=", 1)[0].startswith(RECOVERY_OBSERVATION_FLAG))
            for token in tokens):
        return _recovery_observation_main(tokens)
    if any(
        token.startswith("--")
        and (
            COMPARE_SEAT_FLAG.startswith(token.split("=", 1)[0])
            or token.split("=", 1)[0].startswith(COMPARE_SEAT_FLAG)
        )
        for token in tokens
    ):
        return _seat_compare_main(tokens)
    if any(token.split("=", 1)[0] == REFUSAL_CODE_FLAG for token in tokens):
        return _refusal_code_main(tokens)
    args = _parser().parse_args(tokens)
    if args.compare_seat_stdin is True:
        # Only an abbreviation can reach here; comparison mode never abbreviates.
        return _seat_compare_main(tokens)
    if sys.platform != "darwin" or os.geteuid() != 0:
        result = _refusal("live_probe_requires_darwin_root", expected_kind=args.expected_kind)
    else:
        try:
            result = live_probe(
                binary=args.binary,
                provider_home=args.provider_home,
                expected_kind=args.expected_kind,
                workspace_binding_class=args.workspace_binding_class,
                worker_user=args.worker_user,
                worker_group=args.worker_group,
                worker_uid=args.worker_uid,
                worker_gid=args.worker_gid,
            )
        except IdentityProbeError as exc:
            code = _bounded_refusal_code(exc.args[0] if len(exc.args) == 1 else None)
            result = _refusal(code, expected_kind=args.expected_kind)
        except (OSError, subprocess.SubprocessError):
            result = _refusal("identity_probe_failed", expected_kind=args.expected_kind)
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
