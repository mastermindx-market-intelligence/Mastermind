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
import sys
import time
from typing import Any, Iterator, Mapping
import uuid

from control_plane.fs_security import FilesystemSecurityError, has_macos_acl

_SCOPE_CONSTRUCTION = object()


class CodexAccountError(ValueError):
    """Fixed, secret-free diagnostic; never includes a credential or RPC body."""


def _require_no_acl(path: Path, info: os.stat_result, descriptor=None) -> None:
    try:
        present = has_macos_acl(path, expected_identity=info, descriptor=descriptor)
    except (FilesystemSecurityError, OSError):
        raise CodexAccountError("ACCOUNT_ACL_UNPROVEN") from None
    if present:
        raise CodexAccountError("ACCOUNT_ACL_FORBIDDEN")


def _private_file(path: Path) -> bytes:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1
                    or info.st_size > 1024 * 1024):
                raise CodexAccountError("AUTH_FILE_UNSAFE")
            _require_no_acl(path, info, stream.fileno())
            return stream.read(1024 * 1024 + 1)
    except OSError:
        raise CodexAccountError("AUTH_FILE_UNAVAILABLE") from None


def _is_macos_var_alias(path: Path, canonical: Path) -> bool:
    """Admit only macOS's OS-owned ``/var`` spelling of ``/private/var``."""

    return (
        sys.platform == "darwin"
        and path.parts[:2] == ("/", "var")
        and canonical == Path("/private") / path.relative_to("/")
    )


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


def _home(path: Path, *, principal_home_admitted: bool = False) -> Path:
    path = Path(path)
    try:
        canonical = path.resolve(strict=True)
        info = path.lstat()
    except OSError:
        raise CodexAccountError("PROVIDER_HOME_UNAVAILABLE") from None
    if (not path.is_absolute()
            or (path != canonical and not _is_macos_var_alias(path, canonical))
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077
            or canonical == (Path.home() / ".codex").resolve()
            or (canonical == Path.home().resolve() and not principal_home_admitted)):
        raise CodexAccountError("PROVIDER_HOME_NOT_PRIVATE_DEDICATED")
    _require_no_acl(path, info)
    return path


@contextmanager
def native_codex_account_scope(provider_home: Path, *, principal_home_admitted: bool = False) -> Iterator["CodexAccountEnvironment"]:
    """Serialize one pre-existing private home, never wait or choose another account.

Runtime wraps its entire existing broker lifetime in this scope, including
startup reconciliation and shutdown. It must not release the scope merely
because a model request timed out. Cross-host admission stays with Executive.
    """
    home = _home(provider_home, principal_home_admitted=principal_home_admitted)
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
        _require_no_acl(home / ".executive-native-account.lock", info, fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CodexAccountError("ACCOUNT_REFRESH_WRITER_BUSY") from None
        environment = CodexAccountEnvironment(home, principal_home_admitted=principal_home_admitted,
                                               _scope=_SCOPE_CONSTRUCTION)
        try:
            yield environment
        finally:
            environment._active = False
    finally:
        os.close(fd)


class CodexAccountEnvironment:
    """Construct through native_codex_account_scope; auth remains in this home."""

    def __init__(self, home: Path, *, principal_home_admitted: bool = False, _scope=None):
        if _scope is not _SCOPE_CONSTRUCTION:
            raise CodexAccountError("ACCOUNT_SCOPE_REQUIRED")
        self.home = home
        info = home.lstat()
        self._home_identity = (info.st_dev, info.st_ino)
        self._principal_home_admitted = principal_home_admitted
        self._active = True

    def _check(self) -> None:
        if not self._active:
            raise CodexAccountError("ACCOUNT_SCOPE_CLOSED")
        _home(self.home, principal_home_admitted=self._principal_home_admitted)
        info = self.home.lstat()
        if (info.st_dev, info.st_ino) != self._home_identity:
            raise CodexAccountError("ACCOUNT_HOME_CHANGED")

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

    def worker_adapter(self, binary_path: Path, *, binary_attestation=None,
                       allowed_versions: frozenset[str] | None = None,
                       required_team_identifier: str | None = "2DC432GLL2",
                       **overrides: Any):
        """Existing Executive adapter factory seam, bound to this exact home."""
        from control_plane.codex_worker import CodexWorkerAdapter
        self.auth_metadata()
        if overrides:
            raise CodexAccountError("NATIVE_ACCOUNT_OVERRIDE_FORBIDDEN")
        return CodexWorkerAdapter(binary_path, codex_home=self.home,
            binary_attestation=binary_attestation, allowed_versions=allowed_versions,
            required_team_identifier=required_team_identifier)


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


def reset_credit_inventory(limits: Mapping[str, Any], *, now: float) -> dict[str, Any]:
    """Project native earned-reset facts; missing details are never zero balance.

    Native availableCount is authoritative: the service may cap detail rows or
    return null. Opaque IDs are retained for an admitted owner's explicit reset
    proposal; provider titles/descriptions and all auth material are excluded.
    This function cannot redeem, authorize, purchase or replenish a reset.
    """
    result: dict[str, Any] = {"state": "UNKNOWN", "available_count": None,
        "details_complete": False, "credits": [], "source": "account/rateLimits/read",
        "reset_execution_authorized": False}
    raw = limits.get("rateLimitResetCredits")
    if not isinstance(raw, Mapping):
        return result
    count = raw.get("availableCount")
    if type(count) is not int or not 0 <= count <= 10000:
        return result
    result.update(state="COUNT_OBSERVED", available_count=count)
    rows = raw.get("credits")
    if rows is None:
        return result
    if not isinstance(rows, list) or len(rows) > 1000:
        result["state"] = "DETAILS_INVALID"
        return result
    parsed, seen = [], set()
    for row in rows:
        if not isinstance(row, Mapping):
            result["state"] = "DETAILS_INVALID"
            return result
        ident, expires = row.get("id"), row.get("expiresAt")
        if (not isinstance(ident, str) or not ident.strip() or len(ident) > 256
                or any(ord(c) < 32 or ord(c) == 127 for c in ident) or ident in seen
                or row.get("status") != "available"
                or row.get("resetType") != "codexRateLimits"
                or (expires is not None and (type(expires) is not int or expires <= 0))):
            result["state"] = "DETAILS_INVALID"
            return result
        seen.add(ident)
        parsed.append({"credit_id": ident, "expires_at": expires,
                       "expiry_state": "UNKNOWN" if expires is None else
                           ("EXPIRED_OBSERVATION" if expires <= now else "FUTURE")})
    result["credits"] = sorted(parsed, key=lambda c: (c["expires_at"] is None, c["expires_at"] or 0, c["credit_id"]))
    consistent = count >= len(parsed) and not any(c["expiry_state"] == "EXPIRED_OBSERVATION" for c in parsed)
    result["details_complete"] = consistent and len(parsed) == count
    result["state"] = ("DETAILS_INCONSISTENT" if not consistent else
                       "DETAILS_OBSERVED" if result["details_complete"] else "DETAILS_PARTIAL")
    return result


def account_readiness(account: Mapping[str, Any], limits: Mapping[str, Any], *,
                      now: float | None = None, limit_id: str = "codex") -> dict[str, Any]:
    """Project provider evidence without admission or quota reservation.

    ``windows`` retains only validated measurements for existing consumers.
    ``window_states`` preserves each native position independently: UNKNOWN
    before identity/bucket observation, MISSING for an omitted key,
    NOT_APPLICABLE only for explicit null, INVALID_OR_STALE for rejected data,
    and OBSERVED for a validated window. EXHAUSTED may coexist with an unknown
    sibling constraint; it is not completeness or permission to reset.
    """
    now = time.time() if now is None else now
    result: dict[str, Any] = {"observed_at_unix": now, "auth_state": "UNKNOWN",
        "capacity_state": "UNKNOWN", "plan_type": None, "windows": {},
        "window_states": {"primary": "UNKNOWN", "secondary": "UNKNOWN"},
        "source": ["account/read", "account/rateLimits/read"],
        "account_identity_is_cached": True, "admission_granted": False,
        "limit_id": limit_id, "reset_credits": reset_credit_inventory({}, now=now)}
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
    result["reset_credits"] = reset_credit_inventory(limits, now=now)
    plan = identity.get("planType")
    if isinstance(plan, str) and len(plan) <= 80:
        result["plan_type"] = plan
    # Account/read is a local observation; a real rate-limit response establishes
    # remote reachability. Prefer the named current bucket, never sum accounts.
    if "rateLimitsByLimitId" in limits:
        buckets = limits["rateLimitsByLimitId"]
        selected = buckets.get(limit_id) if isinstance(buckets, Mapping) else None
    else:
        selected = limits.get("rateLimits")
    if not isinstance(selected, Mapping):
        return result
    for key in ("primary", "secondary"):
        # A depleted sibling does not make absent evidence complete. Keep the
        # provider's explicit N/A distinct from missing or invalid measurements
        # through the existing JSON probe output, even when capacity is exhausted.
        if key not in selected:
            result["window_states"][key] = "MISSING"
        elif selected[key] is None:
            result["window_states"][key] = "NOT_APPLICABLE"
        else:
            parsed = _window(selected[key], now)
            if parsed is None:
                result["window_states"][key] = "INVALID_OR_STALE"
            else:
                result["window_states"][key] = "OBSERVED"
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
    client = None
    result: dict[str, Any] = {"account": None, "state": "UNKNOWN", "api_fallback": False,
                            "home_identity": environment.auth_metadata()}
    stage = "construct"
    try:
        client = AppServerClient([str(binary), "app-server", "-c",
            'cli_auth_credentials_store="file"', "-c", 'model_provider="openai"'],
            env=environment.process_environment(), cwd=environment.home,
            start_new_session=True)
        stage = "start"
        client.start()
        stage = "initialize"
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
        if client is None:
            result["stop"] = {"termination_outcome": "not-constructed",
                              "private_group_empty": False}
        else:
            try:
                result["stop"] = asdict(client.graceful_close())
            except Exception:
                # Shutdown may carry provider text too. Preserve uncertainty;
                # never report native-read success or retry a possibly live run.
                result["state"] = "NATIVE_CLEANUP_UNPROVEN"
                result["stop"] = {"termination_outcome": "unproven",
                                  "private_group_empty": False}
            if result["state"] == "NATIVE_READS_COMPLETED" and not result["stop"].get("private_group_empty"):
                result["state"] = "NATIVE_CLEANUP_UNPROVEN"
    return result
