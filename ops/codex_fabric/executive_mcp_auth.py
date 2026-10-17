"""Client-only credential contract for Codex -> installed Executive MCP.

This module does not authenticate callers on the server and owns no Executive
state.  It validates continuity with the installed non-secret resource policy
and prepares one bearer header for Codex's supported http_headers_helper path.
Cryptographic access-token verification remains server-owned.
"""
from __future__ import annotations

import base64
import ctypes
import errno
import fcntl
import dataclasses
import hashlib
import hmac
import json
import os
import queue
import threading
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from integrations.business_mcp_auth.contracts import subject_digest

DEFAULT_POLICY_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/executive-mcp.json"
)
REQUIRED_READ_SCOPE = "mastermind.executive.read"
REQUIRED_SUBMIT_SCOPE = "mastermind.executive.intent.submit"
NON_AUTHORIZING_SCOPES = frozenset({"offline_access"})
REFRESH_SKEW_SECONDS = 120
REFRESH_LOCK_TIMEOUT_SECONDS = 2.0
REFRESH_LOCK_DIRNAME = "mastermind-codex-fabric"
HEADER_HELPER_DEADLINE_SECONDS = 5.0
MAX_POLICY_BYTES = 1024 * 1024
MAX_TOKEN_CHARS = 32768
MAX_CREDENTIAL_BYTES = 64 * 1024
CREDENTIAL_SCHEMA = "mastermind.codex_fabric.executive_mcp_credential.v1"
KEYCHAIN_SERVICE = b"mastermind.codex.fabric.executive-mcp"
KEYCHAIN_ACCOUNT = b"astra-executive-client"
_SECURITY_FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_ERR_SEC_ITEM_NOT_FOUND = -25300


class ExecutiveAuthError(RuntimeError):
    """Closed client-auth refusal; messages never include credential material."""


@dataclasses.dataclass(frozen=True)
class ExecutiveAuthPolicy:
    issuer: str
    resource: str
    required_scopes: tuple[str, ...]
    allowed_subject_digests: tuple[str, ...]
    policy_digest: str


@dataclasses.dataclass(frozen=True)
class CredentialBundle:
    client_id: str
    access_token: str
    refresh_token: str
    expires_at: int
    policy_digest: str
    refresh_state: str = "ready"


class CredentialStore(Protocol):
    def load(self) -> CredentialBundle: ...
    def save(self, bundle: CredentialBundle) -> None: ...


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_policy_bytes(path: Path, *, expected_uid: int) -> bytes:
    try:
        before = path.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != expected_uid
            or before.st_nlink != 1
            or before.st_mode & 0o022
            or not 1 <= before.st_size <= MAX_POLICY_BYTES
        ):
            raise ExecutiveAuthError("installed Executive auth policy is unavailable")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
    except (OSError, ExecutiveAuthError):
        raise ExecutiveAuthError("installed Executive auth policy is unavailable") from None
    try:
        observed = os.fstat(fd)
        if (
            observed.st_dev != before.st_dev
            or observed.st_ino != before.st_ino
            or observed.st_uid != before.st_uid
            or observed.st_size != before.st_size
        ):
            raise ExecutiveAuthError("installed Executive auth policy changed during read")
        raw = os.read(fd, MAX_POLICY_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) != before.st_size:
        raise ExecutiveAuthError("installed Executive auth policy changed during read")
    return raw


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ExecutiveAuthError(f"installed Executive {field} policy is invalid")
    return value


def _subjects(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ExecutiveAuthError("installed Executive subject policy is invalid")
    items = tuple(sorted(value))
    if len(set(items)) != len(items) or any(
        not isinstance(item, str) or len(item) != 64
        or any(ch not in "0123456789abcdef" for ch in item)
        for item in items
    ):
        raise ExecutiveAuthError("installed Executive subject policy is invalid")
    return items


def _scopes(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ExecutiveAuthError("installed Executive scope policy is invalid")
    return tuple(sorted(value))


def load_installed_policy(
    path: Path | str = DEFAULT_POLICY_PATH, *, expected_uid: int = 0
) -> ExecutiveAuthPolicy:
    try:
        document = json.loads(_read_policy_bytes(Path(path), expected_uid=expected_uid))
        policies = document["policies"]
        read = policies["read"]
        submit = policies["submit"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ExecutiveAuthError("installed Executive auth policy is invalid") from None

    read_issuer = _string(read.get("issuer"), "issuer")
    submit_issuer = _string(submit.get("issuer"), "issuer")
    read_resource = _string(read.get("resource"), "resource")
    submit_resource = _string(submit.get("resource"), "resource")
    read_subjects = _subjects(read.get("allowed_subject_digests"))
    submit_subjects = _subjects(submit.get("allowed_subject_digests"))
    read_scopes = _scopes(read.get("required_scopes"))
    submit_scopes = _scopes(submit.get("required_scopes"))
    expected_submit = tuple(sorted((REQUIRED_READ_SCOPE, REQUIRED_SUBMIT_SCOPE)))
    if (
        read_issuer != submit_issuer
        or read_resource != submit_resource
        or read_subjects != submit_subjects
        or read_scopes != (REQUIRED_READ_SCOPE,)
        or submit_scopes != expected_submit
    ):
        raise ExecutiveAuthError("installed Executive auth policy is incoherent")
    projection = {
        "issuer": read_issuer,
        "resource": read_resource,
        "required_scopes": list(expected_submit),
        "allowed_subject_digests": list(read_subjects),
    }
    return ExecutiveAuthPolicy(
        issuer=read_issuer,
        resource=read_resource,
        required_scopes=expected_submit,
        allowed_subject_digests=read_subjects,
        policy_digest=_canonical_digest(projection),
    )


def _jwt_claims(token: str) -> Mapping[str, Any]:
    if not isinstance(token, str) or not 1 <= len(token) <= MAX_TOKEN_CHARS:
        raise ExecutiveAuthError("Executive access token is unavailable")
    parts = token.split(".")
    if len(parts) != 3 or not parts[1]:
        raise ExecutiveAuthError("Executive access token is malformed")
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        claims = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError):
        raise ExecutiveAuthError("Executive access token is malformed") from None
    if not isinstance(claims, Mapping):
        raise ExecutiveAuthError("Executive access token is malformed")
    return claims


def _validate_claims(
    token: str, policy: ExecutiveAuthPolicy
) -> tuple[Mapping[str, Any], int]:
    claims = _jwt_claims(token)
    issuer = claims.get("iss")
    audience = claims.get("aud")
    subject = claims.get("sub")
    scope = claims.get("scope")
    expiry = claims.get("exp")
    if (
        issuer != policy.issuer
        or audience != policy.resource
        or not isinstance(subject, str)
        or not isinstance(scope, str)
        or isinstance(expiry, bool)
        or not isinstance(expiry, int)
    ):
        raise ExecutiveAuthError("Executive access token does not match installed policy")

    try:
        observed_subject = subject_digest(issuer=policy.issuer, subject=subject)
    except Exception:
        raise ExecutiveAuthError("Executive access token subject is invalid") from None
    if not any(
        hmac.compare_digest(observed_subject, allowed)
        for allowed in policy.allowed_subject_digests
    ):
        raise ExecutiveAuthError("Executive access token subject is not authorized")
    granted = frozenset(part for part in scope.split(" ") if part)
    required = frozenset(policy.required_scopes)
    if not required.issubset(granted) or not granted.issubset(required | NON_AUTHORIZING_SCOPES):
        raise ExecutiveAuthError("Executive access token scopes are not authorized")
    return claims, expiry


def validate_access_token(
    token: str, policy: ExecutiveAuthPolicy, *, now_epoch: int
) -> Mapping[str, Any]:
    claims, expiry = _validate_claims(token, policy)
    if expiry <= now_epoch:
        raise ExecutiveAuthError("Executive access token is expired")
    return claims


def _validate_bundle_for_use(
    bundle: CredentialBundle,
    policy: ExecutiveAuthPolicy,
) -> int:
    if not isinstance(bundle, CredentialBundle) or bundle.policy_digest != policy.policy_digest:
        raise ExecutiveAuthError("stored Executive credential does not match installed policy")
    if bundle.refresh_state != "ready":
        raise ExecutiveAuthError(
            "stored Executive credential refresh state requires reauthorization"
        )
    _claims, observed_expiry = _validate_claims(bundle.access_token, policy)
    if observed_expiry != bundle.expires_at:
        raise ExecutiveAuthError("stored Executive credential expiry is inconsistent")
    return observed_expiry


@contextmanager
def _exclusive_refresh_lock(
    *,
    lock_root: Path | None = None,
    timeout_seconds: float = REFRESH_LOCK_TIMEOUT_SECONDS,
):
    """One bounded, non-secret local mutex for refresh-token rotation."""

    root = (
        Path(lock_root)
        if lock_root is not None
        else Path.home() / "Library" / "Caches" / REFRESH_LOCK_DIRNAME
    )
    try:
        root.mkdir(mode=0o700, parents=False, exist_ok=True)
        directory = root.lstat()
    except OSError:
        raise ExecutiveAuthError("Executive refresh lock is unavailable") from None
    if (
        stat.S_ISLNK(directory.st_mode)
        or not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != os.geteuid()
        or stat.S_IMODE(directory.st_mode) != 0o700
    ):
        raise ExecutiveAuthError("Executive refresh lock metadata is unsafe")

    lock_path = root / "refresh.lock"
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        raise ExecutiveAuthError("Executive refresh lock is unavailable") from None
    acquired = False
    try:
        opened = os.fstat(descriptor)
        named = lock_path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
        ):
            raise ExecutiveAuthError("Executive refresh lock metadata is unsafe")
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    raise ExecutiveAuthError("Executive refresh lock is unavailable") from None
                if time.monotonic() >= deadline:
                    raise ExecutiveAuthError("Executive refresh lock timed out") from None
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(descriptor)


def headers_for_codex(
    *,
    policy_path: Path | str,
    store: CredentialStore,
    now_epoch: int,
    expected_uid: int = 0,
    refresh_fn: Callable[[ExecutiveAuthPolicy, CredentialBundle], Mapping[str, Any]] | None = None,
    refresh_lock: Callable[[], Any] | None = None,
) -> dict[str, str]:
    policy = load_installed_policy(policy_path, expected_uid=expected_uid)
    bundle = store.load()
    observed_expiry = _validate_bundle_for_use(bundle, policy)
    if observed_expiry > now_epoch + REFRESH_SKEW_SECONDS:
        validate_access_token(bundle.access_token, policy, now_epoch=now_epoch)
        return {"Authorization": f"Bearer {bundle.access_token}"}
    if not callable(refresh_fn):
        raise ExecutiveAuthError("Executive access token refresh is unavailable")

    lock_factory = refresh_lock if refresh_lock is not None else _exclusive_refresh_lock
    try:
        lock_context = lock_factory()
    except Exception:
        raise ExecutiveAuthError("Executive refresh lock is unavailable") from None

    with lock_context:
        # Another helper may have won while this process waited.  Re-read both
        # policy and credential under the mutex before any refresh effect.
        policy = load_installed_policy(policy_path, expected_uid=expected_uid)
        bundle = store.load()
        observed_expiry = _validate_bundle_for_use(bundle, policy)
        if observed_expiry > now_epoch + REFRESH_SKEW_SECONDS:
            validate_access_token(bundle.access_token, policy, now_epoch=now_epoch)
            return {"Authorization": f"Bearer {bundle.access_token}"}

        # Persist the same credential document as pending before the network
        # effect.  Any timeout/crash/save ambiguity after this point therefore
        # quarantines future helpers instead of replaying a rotating token.
        pending = dataclasses.replace(bundle, refresh_state="pending")
        store.save(pending)
        try:
            response = refresh_fn(policy, bundle)
        except ExecutiveAuthError:
            raise
        except Exception:
            raise ExecutiveAuthError("Executive access token refresh failed") from None
        if not isinstance(response, Mapping):
            raise ExecutiveAuthError("Executive access token refresh failed")
        replacement = response.get("access_token")
        if not isinstance(replacement, str):
            raise ExecutiveAuthError("Executive access token refresh failed")
        claims = validate_access_token(replacement, policy, now_epoch=now_epoch)
        expiry = claims.get("exp")
        assert isinstance(expiry, int) and not isinstance(expiry, bool)
        rotated = response.get("refresh_token", bundle.refresh_token)
        if not isinstance(rotated, str) or not rotated:
            raise ExecutiveAuthError("Executive refresh token rotation is invalid")
        updated = CredentialBundle(
            client_id=bundle.client_id,
            access_token=replacement,
            refresh_token=rotated,
            expires_at=expiry,
            policy_digest=policy.policy_digest,
            refresh_state="ready",
        )
        store.save(updated)
        return {"Authorization": f"Bearer {replacement}"}


_CREDENTIAL_KEYS = frozenset(
    {
        "schema", "client_id", "access_token", "refresh_token", "expires_at",
        "policy_digest", "refresh_state",
    }
)


def _credential_bytes(bundle: CredentialBundle) -> bytes:
    if not isinstance(bundle, CredentialBundle):
        raise ExecutiveAuthError("Executive credential is invalid")
    document = {
        "schema": CREDENTIAL_SCHEMA,
        "client_id": bundle.client_id,
        "access_token": bundle.access_token,
        "refresh_token": bundle.refresh_token,
        "expires_at": bundle.expires_at,
        "policy_digest": bundle.policy_digest,
        "refresh_state": bundle.refresh_state,
    }
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_CREDENTIAL_BYTES:
        raise ExecutiveAuthError("Executive credential is invalid")
    return raw


def _credential_from_bytes(raw: bytes | None) -> CredentialBundle:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_CREDENTIAL_BYTES:
        raise ExecutiveAuthError("stored Executive credential is unavailable")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ExecutiveAuthError("stored Executive credential is invalid") from None
    if not isinstance(document, dict) or set(document) != _CREDENTIAL_KEYS:
        raise ExecutiveAuthError("stored Executive credential is invalid")
    client_id = document.get("client_id")
    access_token = document.get("access_token")
    refresh_token = document.get("refresh_token")
    expires_at = document.get("expires_at")
    policy_digest = document.get("policy_digest")
    refresh_state = document.get("refresh_state")
    if (
        document.get("schema") != CREDENTIAL_SCHEMA
        or not isinstance(client_id, str) or not client_id or client_id != client_id.strip()
        or not isinstance(access_token, str) or not access_token or len(access_token) > MAX_TOKEN_CHARS
        or not isinstance(refresh_token, str) or not refresh_token or len(refresh_token) > MAX_TOKEN_CHARS
        or isinstance(expires_at, bool) or not isinstance(expires_at, int) or expires_at <= 0
        or not isinstance(policy_digest, str) or len(policy_digest) != 64
        or any(ch not in "0123456789abcdef" for ch in policy_digest)
        or refresh_state not in {"ready", "pending"}
    ):
        raise ExecutiveAuthError("stored Executive credential is invalid")
    return CredentialBundle(
        client_id=client_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        policy_digest=policy_digest,
        refresh_state=refresh_state,
    )


class _MacKeychainApi:
    """Fixed generic-password adapter; secret bytes never enter argv or environment."""

    def __init__(self, *, loader=ctypes.CDLL):
        security = loader(_SECURITY_FRAMEWORK)
        core = loader(_CORE_FOUNDATION)
        self._find = security.SecKeychainFindGenericPassword
        self._find.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._find.restype = ctypes.c_int32
        self._free_content = security.SecKeychainItemFreeContent
        self._free_content.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._free_content.restype = ctypes.c_int32
        self._add = security.SecKeychainAddGenericPassword
        self._add.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
            ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        self._add.restype = ctypes.c_int32
        self._modify = security.SecKeychainItemModifyAttributesAndData
        self._modify.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        self._modify.restype = ctypes.c_int32
        self._delete = security.SecKeychainItemDelete
        self._delete.argtypes = [ctypes.c_void_p]
        self._delete.restype = ctypes.c_int32
        self._release = core.CFRelease
        self._release.argtypes = [ctypes.c_void_p]
        self._release.restype = None

    def read(self, service: bytes, account: bytes) -> bytes | None:
        length = ctypes.c_uint32()
        data = ctypes.c_void_p()
        status = self._find(
            None, len(service), service, len(account), account,
            ctypes.byref(length), ctypes.byref(data), None,
        )
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return None
        if status != 0 or not data.value or length.value > MAX_CREDENTIAL_BYTES:
            if data.value:
                self._free_content(None, data)
            raise ExecutiveAuthError("stored Executive credential is unavailable")
        try:
            return ctypes.string_at(data, length.value)
        finally:
            self._free_content(None, data)

    @staticmethod
    def _secret_pointer(value: bytes):
        buffer = ctypes.create_string_buffer(value)
        return buffer, ctypes.cast(buffer, ctypes.c_void_p)

    def upsert(self, service: bytes, account: bytes, value: bytes) -> None:
        item = ctypes.c_void_p()
        status = self._find(None, len(service), service, len(account), account, None, None, ctypes.byref(item))
        buffer, pointer = self._secret_pointer(value)
        try:
            if status == _ERR_SEC_ITEM_NOT_FOUND:
                result = self._add(None, len(service), service, len(account), account, len(value), pointer, None)
            elif status == 0 and item.value:
                result = self._modify(item, None, len(value), pointer)
            else:
                raise ExecutiveAuthError("stored Executive credential is unavailable")
        finally:
            del buffer
            if item.value:
                self._release(item)
        if result != 0:
            raise ExecutiveAuthError("stored Executive credential could not be updated")

    def delete(self, service: bytes, account: bytes) -> bool:
        item = ctypes.c_void_p()
        status = self._find(
            None, len(service), service, len(account), account,
            None, None, ctypes.byref(item),
        )
        if status == _ERR_SEC_ITEM_NOT_FOUND:
            return False
        if status != 0 or not item.value:
            if item.value:
                self._release(item)
            raise ExecutiveAuthError("stored Executive credential is unavailable")
        try:
            result = self._delete(item)
        finally:
            self._release(item)
        if result != 0:
            raise ExecutiveAuthError("stored Executive credential could not be deleted")
        return True


class KeychainCredentialStore:
    """One fixed Codex Executive credential document in the current user's Keychain."""

    def __init__(self, *, api=None):
        self._api = api if api is not None else _MacKeychainApi()

    def load_optional(self) -> CredentialBundle | None:
        raw = self._api.read(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        if raw is None:
            return None
        return _credential_from_bytes(raw)

    def load(self) -> CredentialBundle:
        value = self.load_optional()
        if value is None:
            raise ExecutiveAuthError("stored Executive credential is unavailable")
        return value

    def save(self, bundle: CredentialBundle) -> None:
        self._api.upsert(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, _credential_bytes(bundle))


def _issuer_token_endpoint(issuer: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(issuer)
    except ValueError:
        raise ExecutiveAuthError("Executive issuer is invalid") from None
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.query or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ExecutiveAuthError("Executive issuer is invalid")
    return urllib.parse.urlunsplit(("https", parsed.netloc, "/oauth/token", "", ""))


def _post_form(url: str, fields: dict[str, str]) -> Mapping[str, Any]:
    body = urllib.parse.urlencode(fields).encode("ascii")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read(MAX_CREDENTIAL_BYTES + 1)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        raise ExecutiveAuthError("Executive access token refresh failed") from None
    if len(raw) > MAX_CREDENTIAL_BYTES:
        raise ExecutiveAuthError("Executive access token refresh failed")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ExecutiveAuthError("Executive access token refresh failed") from None
    if not isinstance(payload, Mapping):
        raise ExecutiveAuthError("Executive access token refresh failed")
    return payload


def refresh_access_token(
    policy: ExecutiveAuthPolicy,
    bundle: CredentialBundle,
    *,
    post_form: Callable[[str, dict[str, str]], Mapping[str, Any]] = _post_form,
) -> Mapping[str, Any]:
    if not isinstance(bundle.client_id, str) or not bundle.client_id:
        raise ExecutiveAuthError("Executive OAuth client is unavailable")
    if not isinstance(bundle.refresh_token, str) or not bundle.refresh_token:
        raise ExecutiveAuthError("Executive refresh token is unavailable")
    endpoint = _issuer_token_endpoint(policy.issuer)
    try:
        payload = post_form(
            endpoint,
            {
                "grant_type": "refresh_token",
                "client_id": bundle.client_id,
                "refresh_token": bundle.refresh_token,
            },
        )
    except ExecutiveAuthError:
        raise
    except Exception:
        raise ExecutiveAuthError("Executive access token refresh failed") from None
    if not isinstance(payload, Mapping) or payload.get("token_type") != "Bearer":
        raise ExecutiveAuthError("Executive access token refresh failed")
    return payload


def header_helper_main(
    *,
    policy_path: Path | str = DEFAULT_POLICY_PATH,
    expected_uid: int = 0,
    store: CredentialStore | None = None,
    now_fn: Callable[[], float] = time.time,
    refresh_fn: Callable[[ExecutiveAuthPolicy, CredentialBundle], Mapping[str, Any]] | None = None,
    deadline_seconds: float = HEADER_HELPER_DEADLINE_SECONDS,
    stdout=None,
    stderr=None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    if (
        isinstance(deadline_seconds, bool)
        or not isinstance(deadline_seconds, (int, float))
        or deadline_seconds <= 0
        or deadline_seconds > 30
    ):
        print("REFUSED: Executive MCP authorization unavailable.", file=err)
        return 2
    selected_store = KeychainCredentialStore() if store is None else store
    selected_refresh = refresh_access_token if refresh_fn is None else refresh_fn
    result_queue: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)

    def run_authorization() -> None:
        try:
            headers = headers_for_codex(
                policy_path=policy_path,
                store=selected_store,
                now_epoch=int(now_fn()),
                expected_uid=expected_uid,
                refresh_fn=selected_refresh,
            )
        except BaseException:
            result = ("error", None)
        else:
            result = ("ok", headers)
        try:
            result_queue.put_nowait(result)
        except queue.Full:
            pass

    worker = threading.Thread(
        target=run_authorization,
        name="mastermind-executive-mcp-header-helper",
        daemon=True,
    )
    worker.start()
    try:
        status, value = result_queue.get(timeout=float(deadline_seconds))
    except queue.Empty:
        print("REFUSED: Executive MCP authorization unavailable.", file=err)
        return 2
    if status != "ok" or not isinstance(value, dict):
        print("REFUSED: Executive MCP authorization unavailable.", file=err)
        return 2
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["headers"]):
        print("REFUSED: Executive MCP authorization unavailable.", file=sys.stderr)
        return 2
    return header_helper_main()


if __name__ == "__main__":
    raise SystemExit(main())
