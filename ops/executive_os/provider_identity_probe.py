"""Secret-free Codex App Server identity probe for the Executive worker.

The credential stays opaque in the dedicated ``CODEX_HOME``.  The live probe
classifies the pinned CLI's exact, non-secret ``login status`` output, then
starts the pinned Codex App Server as the disabled worker principal and requests
``account/read(refreshToken:false)``.  Only the small, reviewed classification
returned by :func:`evaluate_identity` may leave this process; email, account
identifiers, raw JSON-RPC frames, and unreviewed stderr are never emitted or
persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import stat
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if __package__ in {None, ""} and str(_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIRECTORY))

try:
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
PINNED_CODEX_VERSION = "0.147.0"
WORKER_USER = "_mastermind_worker"
WORKER_GROUP = "_mastermind_worker"
PROVIDER_HOME = Path("/var/db/mastermind-executive/workers/codex-01/provider-home")
INSTALLED_CODEX_BINARY = Path(
    "/Library/Application Support/MastermindExecutive/bin/codex-0.147.0"
)
PINNED_CODEX_SHA256 = "19c4f144c5226a9f17c58e6f0fa854843b0f77a6eb420f40e2745a12f10f5d37"
PINNED_CODEX_TEAM_ID = "2DC432GLL2"
WORKSPACE_BINDING_CLASS = COMPANY_WORKSPACE_BINDING_CLASS
WORKER_UID = 451
WORKER_GID = 451
# These strings are the complete stderr contract in the pinned Codex 0.147.0
# ``run_login_status`` implementation.  API-key status contains a redacted key
# fragment and every unreviewed/future string is deliberately rejected.
LOGIN_STATUS_AUTH_MODE = {
    b"Logged in using access token\n": "agentIdentity",
    b"Logged in using personal access token\n": "personalAccessToken",
    b"Logged in using ChatGPT\n": "chatgpt",
}
_FORCED_CONFIG_KEYS = frozenset(
    {"forced_chatgpt_workspace_id", "forced_login_method"}
)
_AUTH_STORE_KEY = "cli_auth_credentials_store"


class IdentityProbeError(RuntimeError):
    """A bounded, non-secret identity refusal."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assert_no_macos_acl(path: Path) -> None:
    completed = subprocess.run(
        ["/usr/bin/stat", "-f", "%Sp", os.fspath(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip().endswith("+"):
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
    return LOGIN_STATUS_AUTH_MODE.get(stderr)


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
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._messages.put({"_malformed": True})
                continue
            self._messages.put(value if isinstance(value, dict) else {"_malformed": True})
        self._messages.put(None)

    def _send(self, value: Mapping[str, Any]) -> None:
        if self._proc.stdin is None:
            raise IdentityProbeError("app_server_closed")
        self._proc.stdin.write((json.dumps(dict(value)) + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def notify(self, method: str) -> None:
        self._send({"method": method})

    def request(self, request_id: int, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        self._send({"id": request_id, "method": method, "params": dict(params)})
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
) -> dict[str, Any]:
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
        return result
    finally:
        client.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe sanitized Executive provider identity")
    parser.add_argument("--binary", type=Path, default=INSTALLED_CODEX_BINARY)
    parser.add_argument("--provider-home", type=Path, default=PROVIDER_HOME)
    parser.add_argument("--worker-user", default=WORKER_USER)
    parser.add_argument("--worker-group", default=WORKER_GROUP)
    parser.add_argument("--worker-uid", type=int, default=WORKER_UID)
    parser.add_argument("--worker-gid", type=int, default=WORKER_GID)
    parser.add_argument("--expected-kind", choices=sorted(EXPECTED_AUTH_MODE), required=True)
    parser.add_argument("--workspace-binding-class", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
        except (IdentityProbeError, OSError, subprocess.SubprocessError):
            result = _refusal("identity_probe_failed", expected_kind=args.expected_kind)
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0 if result.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
