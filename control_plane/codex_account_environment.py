"""Persistent native Codex authentication, without routing or lifecycle authority.

The Executive owner supplies an already admitted account/host and keeps one scope
for the lifetime of its broker. This local mutex is not a remote lease or a
replacement for the broker's dedicated-UID residual-process reconciliation.
Switcher stores are deliberately not imported: a second refresh writer must be
reconciled before a native login file may be seeded onto a serialized stream.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
from typing import Any, Iterator, Mapping
import uuid


class CodexAccountError(ValueError):
    """Fixed, secret-free diagnostic; never includes a credential or RPC body."""


def _private_file(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1
                    or info.st_size > 1024 * 1024):
                raise CodexAccountError("AUTH_FILE_UNSAFE")
            return stream.read(1024 * 1024 + 1)
    except OSError:
        raise CodexAccountError("AUTH_FILE_UNAVAILABLE") from None


def _managed_auth(raw: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise CodexAccountError("AUTH_DOCUMENT_INVALID") from None
    if not isinstance(value, dict) or value.get("auth_mode") != "chatgpt":
        raise CodexAccountError("MANAGED_CHATGPT_AUTH_REQUIRED")
    tokens = value.get("tokens")
    if value.get("OPENAI_API_KEY") or not isinstance(tokens, dict):
        raise CodexAccountError("MANAGED_CHATGPT_AUTH_REQUIRED")
    if any(not isinstance(tokens.get(k), str) or not tokens[k].strip()
           for k in ("access_token", "refresh_token", "id_token", "account_id")):
        raise CodexAccountError("MANAGED_CHATGPT_AUTH_INCOMPLETE")
    return value


def _home(path: Path) -> Path:
    path = Path(path)
    try:
        canonical = path.resolve(strict=True)
        info = path.lstat()
    except OSError:
        raise CodexAccountError("PROVIDER_HOME_UNAVAILABLE") from None
    if (not path.is_absolute() or path != canonical or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077
            or path in {Path.home().resolve(), (Path.home() / ".codex").resolve()}):
        raise CodexAccountError("PROVIDER_HOME_NOT_PRIVATE_DEDICATED")
    return path


@contextmanager
def native_codex_account_scope(provider_home: Path) -> Iterator["CodexAccountEnvironment"]:
    """Serialize one pre-existing private home, never wait or choose another account.

Runtime wraps its entire existing broker lifetime in this scope, including
startup reconciliation and shutdown. It must not release the scope merely
because a model request timed out. Cross-host admission stays with Executive.
    """
    home = _home(provider_home)
    try:
        fd = os.open(home / ".executive-native-account.lock",
                     os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        raise CodexAccountError("ACCOUNT_LOCK_UNAVAILABLE") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077):
            raise CodexAccountError("ACCOUNT_LOCK_UNSAFE")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CodexAccountError("ACCOUNT_REFRESH_WRITER_BUSY") from None
        environment = CodexAccountEnvironment(home)
        try:
            yield environment
        finally:
            environment._active = False
    finally:
        os.close(fd)


class CodexAccountEnvironment:
    """Construct through native_codex_account_scope; auth remains in this home."""

    def __init__(self, home: Path):
        self.home = home
        self._active = True

    def _check(self) -> None:
        if not self._active:
            raise CodexAccountError("ACCOUNT_SCOPE_CLOSED")
        _home(self.home)

    def seed_if_missing(self, seed_file: Path) -> str:
        """Seed an explicitly admitted native auth file once, without replacement.

No account extraction, token exchange, automatic reseed, or Switcher mutation.
The caller must establish exclusive refresh-stream custody before this call.
Existing credentials take precedence even when the seed is absent or stale.
        """
        self._check()
        auth = self.home / "auth.json"
        if os.path.lexists(auth):
            self.auth_metadata()
            return "PRESERVED_EXISTING"
        raw = _private_file(Path(seed_file))
        _managed_auth(raw)
        temporary = self.home / (".native-auth-seed-" + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Atomic no-clobber publication; replace/rename would lose a refresh.
            try:
                os.link(temporary, auth, follow_symlinks=False)
            except FileExistsError:
                self.auth_metadata()
                return "PRESERVED_CONCURRENT_PUBLICATION"
            finally:
                temporary.unlink()
            directory_fd = os.open(self.home, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return "SEEDED_ONCE"
        finally:
            if temporary.exists():
                temporary.unlink()

    def auth_metadata(self) -> dict[str, Any]:
        self._check()
        value = _managed_auth(_private_file(self.home / "auth.json"))
        return {"auth_mode": "chatgpt", "has_refresh_token": True,
                "account_id_sha256": hashlib.sha256(
                    value["tokens"]["account_id"].encode()).hexdigest()}

    def process_environment(self) -> dict[str, str]:
        self.auth_metadata()
        # No inherited API key, provider URL, proxy, or external-token override.
        return {"HOME": str(self.home), "CODEX_HOME": str(self.home),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}

    def worker_adapter(self, binary_path: Path, **kwargs: Any):
        """Existing Executive adapter factory seam, bound to this exact home."""
        from control_plane.codex_worker import CodexWorkerAdapter
        self.auth_metadata()
        if {"codex_home", "provider_realm", "provider_credential_loader"} & kwargs.keys():
            raise CodexAccountError("NATIVE_ACCOUNT_OVERRIDE_FORBIDDEN")
        return CodexWorkerAdapter(binary_path, codex_home=self.home, **kwargs)


def _window(value: Any, now: float) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    used, duration, reset = (value.get(k) for k in
                             ("usedPercent", "windowDurationMins", "resetsAt"))
    if (isinstance(used, bool) or not isinstance(used, (int, float))
            or not math.isfinite(used) or not 0 <= used <= 100
            or type(duration) is not int or duration <= 0
            or type(reset) is not int or reset <= now):
        return None
    return {"used_percent": used, "remaining_percent": 100 - used,
            "window_minutes": duration, "resets_at": reset}


def account_readiness(account: Mapping[str, Any], limits: Mapping[str, Any], *,
                      now: float | None = None, limit_id: str = "codex") -> dict[str, Any]:
    """Projection of provider evidence, not an admission or a quota reservation."""
    now = time.time() if now is None else now
    result: dict[str, Any] = {"observed_at_unix": now, "auth_state": "UNKNOWN",
        "capacity_state": "UNKNOWN", "plan_type": None, "windows": {},
        "source": ["account/read", "account/rateLimits/read"],
        "account_identity_is_cached": True, "admission_granted": False}
    identity = account.get("account")
    if identity is None and "account" in account:
        result["auth_state"] = "LOGIN_REQUIRED"
        return result
    if "account" not in account:
        return result
    if not isinstance(identity, Mapping) or identity.get("type") != "chatgpt":
        result["auth_state"] = "NATIVE_CHATGPT_AUTH_REQUIRED"
        return result
    result["auth_state"] = "MANAGED_CHATGPT_OBSERVED"
    plan = identity.get("planType")
    if isinstance(plan, str) and len(plan) <= 80:
        result["plan_type"] = plan
    # Account/read is a local observation; a real rate-limit response establishes
    # remote reachability. Prefer the named current bucket, never sum accounts.
    if "rateLimitsByLimitId" in limits and limits["rateLimitsByLimitId"] is not None:
        buckets = limits["rateLimitsByLimitId"]
        selected = buckets.get(limit_id) if isinstance(buckets, Mapping) else None
    else:
        selected = limits.get("rateLimits")
    if not isinstance(selected, Mapping):
        return result
    for key in ("primary", "secondary"):
        parsed = _window(selected.get(key), now)
        if parsed is not None:
            result["windows"][key] = parsed
    if any(w["remaining_percent"] == 0 for w in result["windows"].values()):
        result["capacity_state"] = "EXHAUSTED"
    elif (result["windows"] and all(key in selected for key in ("primary", "secondary"))
          and all(selected[key] is None or key in result["windows"]
                  for key in ("primary", "secondary"))):
        # An explicit null window is not applicable. A missing or malformed
        # window remains unknown; never manufacture a second quota window.
        result["capacity_state"] = "AVAILABLE_OBSERVED"
    return result


def _failure_kind(error: Exception) -> str:
    """Classify for the existing owner without retaining provider error text."""
    message = str(error).lower()
    if any(s in message for s in ("401", "unauthorized", "refresh_token_reused",
                                  "refresh token", "not authenticated")):
        return "LOGIN_REQUIRED"
    if "429" in message or "rate limit" in message:
        return "QUOTA_UNAVAILABLE"
    if "timeout" in message or "timed out" in message:
        return "TRANSPORT_TIMEOUT"
    return "NATIVE_READ_UNAVAILABLE"


def probe_native_account(environment: CodexAccountEnvironment, binary: Path,
                         *, timeout: float = 20) -> dict[str, Any]:
    """Two native reads in a contained app-server; no thread, turn or model call."""
    from scripts.ohf.laboratory import AppServerClient
    # The explicit provider overrides prevent a saved profile selecting an API
    # route. File storage lets Codex persist its own refreshed managed session.
    client = AppServerClient([str(binary), "app-server", "-c",
        'cli_auth_credentials_store="file"', "-c", 'model_provider="openai"'],
        env=environment.process_environment(), cwd=environment.home,
        start_new_session=True)
    result: dict[str, Any] = {"account": None, "state": "UNKNOWN", "api_fallback": False,
                            "home_identity": environment.auth_metadata()}
    stage = "initialize"
    try:
        client.start()
        initialized = client.request("initialize", {"clientInfo": {
            "name": "mastermind_native_account", "version": "1.0"},
            "capabilities": {"experimentalApi": True}}, timeout=timeout)
        client.notify("initialized", {})
        result["harness_version"] = initialized.get("userAgent")
        stage = "account/read"
        account = client.request("account/read", {"refreshToken": False}, timeout=timeout)
        result["account"] = account_readiness(account, {})
        stage = "account/rateLimits/read"
        limits = client.request("account/rateLimits/read", {}, timeout=timeout)
        result["account"] = account_readiness(account, limits)
        result["state"] = "NATIVE_READS_COMPLETED"
    except Exception as error:
        # Provider errors can echo tokens/headers. Never return arbitrary errors.
        result["state"] = _failure_kind(error)
        result["failed_method"] = stage
    finally:
        result["stop"] = asdict(client.graceful_close())
    return result
