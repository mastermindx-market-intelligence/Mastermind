"""One-time public-client enrollment contracts for Codex -> Executive MCP.

DCR/PKCE is client-side only.  Executive OAuth resource policy and JWT
verification remain owned by the installed server.  DCR client identity is
persisted before user authorization so an interrupted login never creates a
new Auth0 application on every retry.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import http.server
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from ops.codex_fabric.executive_mcp_auth import (
    CredentialBundle,
    ExecutiveAuthError,
    ExecutiveAuthPolicy,
    KEYCHAIN_SERVICE,
    KeychainCredentialStore,
    DEFAULT_POLICY_PATH,
    MAX_CREDENTIAL_BYTES,
    load_installed_policy,
    _MacKeychainApi,
    _post_form as _auth_post_form,
    validate_access_token,
)

CALLBACK_URL = "http://127.0.0.1:8769/oauth/callback"
CLIENT_NAME = "Mastermind Codex Astra"
REGISTRATION_SCHEMA = "mastermind.codex_fabric.executive_mcp_registration.v1"
PENDING_REGISTRATION_SCHEMA_V1 = "mastermind.codex_fabric.executive_mcp_registration_attempt.v1"
PENDING_REGISTRATION_SCHEMA = "mastermind.codex_fabric.executive_mcp_registration_attempt.v2"
REGISTRATION_ACCOUNT = b"astra-executive-registration"
_REGISTRATION_KEYS = frozenset({"schema", "client_id", "redirect_uri", "policy_digest"})
_PENDING_REGISTRATION_V1_KEYS = frozenset({"schema", "attempt_ref", "redirect_uri", "policy_digest"})
_PENDING_REGISTRATION_KEYS = frozenset(
    {"schema", "attempt_ref", "client_name", "redirect_uri", "policy_digest"}
)


class EnrollmentError(RuntimeError):
    """Closed enrollment refusal; never contains codes, tokens, or browser payloads."""


class EnrollmentEffectUnknown(EnrollmentError):
    """DCR may have committed; automatic retry is forbidden until reconciled."""


class EnrollmentDefinitiveRefusal(EnrollmentError):
    """Auth0 returned a bounded refusal proving this DCR effect did not commit."""


@dataclasses.dataclass(frozen=True)
class OidcMetadata:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str


@dataclasses.dataclass(frozen=True)
class ClientRegistration:
    client_id: str
    redirect_uri: str
    policy_digest: str


@dataclasses.dataclass(frozen=True)
class PendingRegistration:
    attempt_ref: str
    redirect_uri: str
    policy_digest: str
    client_name: str | None = None


class KeychainRegistrationStore:
    """One fixed DCR state item: absent, pending-effect, or completed client."""

    def __init__(self, *, api=None):
        self._api = api if api is not None else _MacKeychainApi()

    @staticmethod
    def _hex64(value: Any) -> bool:
        return (
            isinstance(value, str) and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value)
        )

    def load_state(self) -> ClientRegistration | PendingRegistration | None:
        raw = self._api.read(KEYCHAIN_SERVICE, REGISTRATION_ACCOUNT)
        if raw is None:
            return None
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_CREDENTIAL_BYTES:
            raise EnrollmentError("stored Executive client registration is invalid")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise EnrollmentError("stored Executive client registration is invalid") from None
        if not isinstance(value, dict):
            raise EnrollmentError("stored Executive client registration is invalid")
        schema = value.get("schema")
        if schema == REGISTRATION_SCHEMA and set(value) == _REGISTRATION_KEYS:
            client_id = value.get("client_id")
            redirect_uri = value.get("redirect_uri")
            policy_digest = value.get("policy_digest")
            if (
                not isinstance(client_id, str) or not client_id.startswith("tpc_")
                or redirect_uri != CALLBACK_URL or not self._hex64(policy_digest)
            ):
                raise EnrollmentError("stored Executive client registration is invalid")
            return ClientRegistration(client_id, redirect_uri, policy_digest)
        if schema == PENDING_REGISTRATION_SCHEMA and set(value) == _PENDING_REGISTRATION_KEYS:
            attempt_ref = value.get("attempt_ref")
            client_name = value.get("client_name")
            redirect_uri = value.get("redirect_uri")
            policy_digest = value.get("policy_digest")
            if (
                not self._hex64(attempt_ref)
                or client_name != f"{CLIENT_NAME} {attempt_ref[:16]}"
                or redirect_uri != CALLBACK_URL
                or not self._hex64(policy_digest)
            ):
                raise EnrollmentError("stored Executive client registration is invalid")
            return PendingRegistration(attempt_ref, redirect_uri, policy_digest, client_name)
        if (
            schema == PENDING_REGISTRATION_SCHEMA_V1
            and set(value) == _PENDING_REGISTRATION_V1_KEYS
        ):
            attempt_ref = value.get("attempt_ref")
            redirect_uri = value.get("redirect_uri")
            policy_digest = value.get("policy_digest")
            if (
                not self._hex64(attempt_ref)
                or redirect_uri != CALLBACK_URL
                or not self._hex64(policy_digest)
            ):
                raise EnrollmentError("stored Executive client registration is invalid")
            return PendingRegistration(attempt_ref, redirect_uri, policy_digest, None)
        raise EnrollmentError("stored Executive client registration is invalid")

    def load_optional(self) -> ClientRegistration | None:
        state = self.load_state()
        if isinstance(state, PendingRegistration):
            raise EnrollmentEffectUnknown("Executive public client registration effect is unknown")
        return state

    def save_pending(self, pending: PendingRegistration) -> None:
        if (
            not isinstance(pending, PendingRegistration)
            or not self._hex64(pending.attempt_ref)
            or pending.client_name != f"{CLIENT_NAME} {pending.attempt_ref[:16]}"
            or pending.redirect_uri != CALLBACK_URL
            or not self._hex64(pending.policy_digest)
        ):
            raise EnrollmentError("Executive client registration attempt is invalid")
        raw = json.dumps(
            {
                "schema": PENDING_REGISTRATION_SCHEMA,
                "attempt_ref": pending.attempt_ref,
                "client_name": pending.client_name,
                "redirect_uri": pending.redirect_uri,
                "policy_digest": pending.policy_digest,
            },
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        self._api.upsert(KEYCHAIN_SERVICE, REGISTRATION_ACCOUNT, raw)

    def clear_pending(self, attempt_ref: str) -> None:
        state = self.load_state()
        if not isinstance(state, PendingRegistration) or state.attempt_ref != attempt_ref:
            raise EnrollmentError("Executive client registration attempt does not match pending state")
        try:
            deleted = self._api.delete(KEYCHAIN_SERVICE, REGISTRATION_ACCOUNT)
        except Exception:
            raise EnrollmentEffectUnknown(
                "Executive client registration cleanup effect is unknown"
            ) from None
        if deleted is not True:
            raise EnrollmentEffectUnknown(
                "Executive client registration cleanup effect is unknown"
            )
        try:
            remaining = self.load_state()
        except Exception:
            raise EnrollmentEffectUnknown(
                "Executive client registration cleanup effect is unknown"
            ) from None
        if remaining is not None:
            raise EnrollmentEffectUnknown(
                "Executive client registration cleanup effect is unknown"
            )

    def save(self, registration: ClientRegistration) -> None:
        if (
            not isinstance(registration, ClientRegistration)
            or not registration.client_id.startswith("tpc_")
            or registration.redirect_uri != CALLBACK_URL
            or not self._hex64(registration.policy_digest)
        ):
            raise EnrollmentError("Executive client registration is invalid")
        raw = json.dumps(
            {
                "schema": REGISTRATION_SCHEMA,
                "client_id": registration.client_id,
                "redirect_uri": registration.redirect_uri,
                "policy_digest": registration.policy_digest,
            },
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        self._api.upsert(KEYCHAIN_SERVICE, REGISTRATION_ACCOUNT, raw)


def _exact_issuer_endpoint(policy: ExecutiveAuthPolicy, suffix: str, value: Any) -> str:
    expected = policy.issuer.rstrip("/") + suffix
    if value != expected:
        raise EnrollmentError("Executive authorization metadata is incompatible")
    return expected


def _validated_issuer_root(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise EnrollmentError("Executive authorization metadata is incompatible") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/"
        or parsed.query
        or parsed.fragment
        or value != urllib.parse.urlunsplit(("https", parsed.netloc, "/", "", ""))
    ):
        raise EnrollmentError("Executive authorization metadata is incompatible")
    return value


def discover_metadata(
    policy: ExecutiveAuthPolicy,
    *,
    get_json: Callable[[str], Mapping[str, Any]],
) -> OidcMetadata:
    issuer = _validated_issuer_root(policy.issuer)
    discovery_url = issuer + ".well-known/openid-configuration"
    try:
        value = get_json(discovery_url)
    except EnrollmentError:
        raise
    except Exception:
        raise EnrollmentError("Executive authorization metadata is unavailable") from None
    if not isinstance(value, Mapping) or value.get("issuer") != policy.issuer:
        raise EnrollmentError("Executive authorization metadata is incompatible")
    authorization_endpoint = _exact_issuer_endpoint(policy, "/authorize", value.get("authorization_endpoint"))
    token_endpoint = _exact_issuer_endpoint(policy, "/oauth/token", value.get("token_endpoint"))
    registration_endpoint = _exact_issuer_endpoint(policy, "/oidc/register", value.get("registration_endpoint"))
    methods = value.get("code_challenge_methods_supported")
    grants = value.get("grant_types_supported")
    if (
        not isinstance(methods, list) or "S256" not in methods
        or not isinstance(grants, list)
        or "authorization_code" not in grants
        or "refresh_token" not in grants
    ):
        raise EnrollmentError("Executive authorization metadata is incompatible")
    return OidcMetadata(authorization_endpoint, token_endpoint, registration_endpoint)


def ensure_client_registration(
    policy: ExecutiveAuthPolicy,
    metadata: OidcMetadata,
    *,
    store: KeychainRegistrationStore,
    post_json: Callable[[str, dict[str, Any]], Mapping[str, Any]],
    attempt_ref_fn: Callable[[], str] = lambda: secrets.token_hex(32),
) -> ClientRegistration:
    existing = store.load_state()
    if isinstance(existing, PendingRegistration):
        raise EnrollmentEffectUnknown("Executive public client registration effect is unknown")
    if existing is not None:
        if existing.policy_digest != policy.policy_digest or existing.redirect_uri != CALLBACK_URL:
            raise EnrollmentError("stored Executive client registration does not match installed policy")
        return existing
    attempt_ref = attempt_ref_fn()
    pending = PendingRegistration(
        attempt_ref,
        CALLBACK_URL,
        policy.policy_digest,
        f"{CLIENT_NAME} {attempt_ref[:16]}",
    )
    store.save_pending(pending)
    request = {
        "client_name": pending.client_name,
        "redirect_uris": [CALLBACK_URL],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    try:
        response = post_json(metadata.registration_endpoint, request)
    except EnrollmentDefinitiveRefusal:
        store.clear_pending(attempt_ref)
        raise EnrollmentError("Executive public client registration was refused") from None
    except Exception:
        raise EnrollmentEffectUnknown("Executive public client registration effect is unknown") from None
    if not isinstance(response, Mapping):
        raise EnrollmentEffectUnknown("Executive public client registration effect is unknown")
    client_id = response.get("client_id")
    redirects = response.get("redirect_uris")
    grants = response.get("grant_types")
    auth_method = response.get("token_endpoint_auth_method")
    if (
        not isinstance(client_id, str) or not client_id.startswith("tpc_")
        or response.get("client_secret") is not None
        or redirects != [CALLBACK_URL]
        or not isinstance(grants, list)
        or not {"authorization_code", "refresh_token"}.issubset(set(grants))
        or auth_method != "none"
    ):
        raise EnrollmentEffectUnknown("Executive public client registration effect is unknown")
    registration = ClientRegistration(client_id, CALLBACK_URL, policy.policy_digest)
    try:
        store.save(registration)
    except Exception:
        raise EnrollmentEffectUnknown("Executive public client registration effect is unknown") from None
    return registration


def reconcile_pending_registration(
    policy: ExecutiveAuthPolicy,
    *,
    store: KeychainRegistrationStore,
    observed_client_id: str,
    observed_attempt_ref: str,
    observed_client_name: str,
) -> ClientRegistration:
    """Bind one admin-observed DCR client to the exact pending operation.

    This is reconciliation only: it never calls Auth0 and never clears an
    absent or stale pending state.
    """

    state = store.load_state()
    if not isinstance(state, PendingRegistration):
        raise EnrollmentError("Executive public client registration is not pending")
    if (
        state.policy_digest != policy.policy_digest
        or state.redirect_uri != CALLBACK_URL
        or not isinstance(observed_attempt_ref, str)
        or observed_attempt_ref != state.attempt_ref
        or state.client_name is None
        or observed_client_name != state.client_name
        or not isinstance(observed_client_id, str)
        or observed_client_id != observed_client_id.strip()
        or not observed_client_id.startswith("tpc_")
        or len(observed_client_id) > 512
    ):
        raise EnrollmentError("pending Executive public client registration cannot be reconciled")
    registration = ClientRegistration(
        client_id=observed_client_id,
        redirect_uri=CALLBACK_URL,
        policy_digest=policy.policy_digest,
    )
    try:
        store.save(registration)
    except Exception:
        raise EnrollmentEffectUnknown(
            "Executive public client registration reconciliation effect is unknown"
        ) from None
    return registration


def pending_registration_status(
    policy: ExecutiveAuthPolicy,
    *,
    store: KeychainRegistrationStore,
) -> dict[str, Any]:
    """Return only non-secret metadata needed to reconcile one pending DCR effect."""

    state = store.load_state()
    if not isinstance(state, PendingRegistration):
        raise EnrollmentError("Executive public client registration is not pending")
    if (
        state.policy_digest != policy.policy_digest
        or state.redirect_uri != CALLBACK_URL
    ):
        raise EnrollmentError(
            "pending Executive public client registration does not match installed policy"
        )
    return {
        "attempt_ref": state.attempt_ref,
        "client_name": state.client_name,
        "policy_digest": state.policy_digest,
        "reconcilable": state.client_name is not None,
        "redirect_uri": state.redirect_uri,
        "state": "effect_unknown",
    }


def build_authorize_url(
    policy: ExecutiveAuthPolicy,
    metadata: OidcMetadata,
    registration: ClientRegistration,
    *,
    state: str,
    code_challenge: str,
) -> str:
    if registration.policy_digest != policy.policy_digest or registration.redirect_uri != CALLBACK_URL:
        raise EnrollmentError("Executive public client registration is stale")
    if not state or not code_challenge:
        raise EnrollmentError("Executive PKCE request is invalid")
    scope = " ".join((*policy.required_scopes, "offline_access"))
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": registration.client_id,
            "redirect_uri": registration.redirect_uri,
            "audience": policy.resource,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{metadata.authorization_endpoint}?{query}"


def exchange_authorization_code(
    policy: ExecutiveAuthPolicy,
    metadata: OidcMetadata,
    registration: ClientRegistration,
    *,
    code: str,
    code_verifier: str,
    now_epoch: int,
    store: KeychainCredentialStore,
    post_form: Callable[[str, dict[str, str]], Mapping[str, Any]],
) -> CredentialBundle:
    if (
        registration.policy_digest != policy.policy_digest
        or registration.redirect_uri != CALLBACK_URL
        or not isinstance(code, str) or not code
        or not isinstance(code_verifier, str) or not 43 <= len(code_verifier) <= 128
    ):
        raise EnrollmentError("Executive authorization code exchange refused")
    fields = {
        "grant_type": "authorization_code",
        "client_id": registration.client_id,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": registration.redirect_uri,
    }
    try:
        response = post_form(metadata.token_endpoint, fields)
    except Exception:
        raise EnrollmentError("Executive authorization code exchange failed") from None
    if not isinstance(response, Mapping) or response.get("token_type") != "Bearer":
        raise EnrollmentError("Executive authorization code exchange failed")
    access_token = response.get("access_token")
    refresh_token = response.get("refresh_token")
    if not isinstance(access_token, str) or not isinstance(refresh_token, str) or not refresh_token:
        raise EnrollmentError("Executive authorization code exchange failed")
    try:
        claims = validate_access_token(access_token, policy, now_epoch=now_epoch)
    except ExecutiveAuthError:
        raise EnrollmentError("Executive authorization code exchange returned unusable authorization") from None
    expiry = claims.get("exp")
    if isinstance(expiry, bool) or not isinstance(expiry, int):
        raise EnrollmentError("Executive authorization code exchange returned unusable authorization")
    bundle = CredentialBundle(
        client_id=registration.client_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expiry,
        policy_digest=policy.policy_digest,
    )
    try:
        store.save(bundle)
    except Exception:
        raise EnrollmentError("Executive authorization could not be stored") from None
    return bundle


@dataclasses.dataclass(frozen=True)
class EnrollmentReceipt:
    client_id_digest: str
    policy_digest: str
    expires_at: int


def parse_callback_target(target: str, *, expected_state: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(target)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    except ValueError:
        raise EnrollmentError("Executive OAuth callback was invalid") from None
    if parsed.path != "/oauth/callback" or parsed.fragment:
        raise EnrollmentError("Executive OAuth callback was invalid")
    if query.get("state") != [expected_state] or "error" in query or len(query.get("code", [])) != 1:
        raise EnrollmentError("Executive OAuth callback was refused")
    code = query["code"][0]
    if not code or len(code) > 8192:
        raise EnrollmentError("Executive OAuth callback was refused")
    return code


def _read_json_response(response) -> Mapping[str, Any]:
    raw = response.read(MAX_CREDENTIAL_BYTES + 1)
    if len(raw) > MAX_CREDENTIAL_BYTES:
        raise EnrollmentError("Executive authorization response exceeded its budget")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise EnrollmentError("Executive authorization response was invalid") from None
    if not isinstance(value, Mapping):
        raise EnrollmentError("Executive authorization response was invalid")
    return value


def _get_json(url: str) -> Mapping[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return _read_json_response(response)
    except EnrollmentError:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        raise EnrollmentError("Executive authorization metadata is unavailable") from None


def _post_json(url: str, payload: dict[str, Any]) -> Mapping[str, Any]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return _read_json_response(response)
    except EnrollmentError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 401, 403}:
            try:
                raw = exc.read(MAX_CREDENTIAL_BYTES + 1)
                value = json.loads(raw.decode("utf-8")) if len(raw) <= MAX_CREDENTIAL_BYTES else None
            except (OSError, UnicodeError, json.JSONDecodeError):
                value = None
            if (
                isinstance(value, Mapping)
                and isinstance(value.get("error"), str)
                and value.get("error")
                and value.get("client_id") is None
            ):
                raise EnrollmentDefinitiveRefusal(
                    "Executive public client registration was refused"
                ) from None
        raise EnrollmentError("Executive public client registration failed") from None
    except (OSError, urllib.error.URLError):
        raise EnrollmentError("Executive public client registration failed") from None


def _post_form(url: str, fields: dict[str, str]) -> Mapping[str, Any]:
    try:
        return _auth_post_form(url, fields)
    except Exception:
        raise EnrollmentError("Executive authorization code exchange failed") from None


def _browser_authorize(url: str, expected_state: str) -> str:
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib callback name
            try:
                result["code"] = parse_callback_target(self.path, expected_state=expected_state)
                status = 200
                body = b"Mastermind Codex authorization received. You may close this tab."
            except EnrollmentError:
                result["error"] = "refused"
                status = 400
                body = b"Mastermind Codex authorization was refused."
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    try:
        server = http.server.HTTPServer(("127.0.0.1", 8769), Handler)
    except OSError:
        raise EnrollmentError("Executive OAuth callback listener is unavailable") from None
    server.timeout = 1.0
    try:
        try:
            launched = subprocess.run(
                ["/usr/bin/open", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            raise EnrollmentError("Executive OAuth browser launch failed") from None
        if launched.returncode != 0:
            raise EnrollmentError("Executive OAuth browser launch failed")
        deadline = time.monotonic() + 180
        while "code" not in result and "error" not in result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if "code" in result:
        return result["code"]
    raise EnrollmentError("Executive OAuth authorization did not complete")


def enroll_once(
    *,
    policy_path=DEFAULT_POLICY_PATH,
    expected_uid: int = 0,
    registration_store: KeychainRegistrationStore | None = None,
    credential_store: KeychainCredentialStore | None = None,
    get_json: Callable[[str], Mapping[str, Any]] = _get_json,
    post_json: Callable[[str, dict[str, Any]], Mapping[str, Any]] = _post_json,
    post_form: Callable[[str, dict[str, str]], Mapping[str, Any]] = _post_form,
    authorize_code: Callable[[str, str], str] = _browser_authorize,
    now_fn: Callable[[], float] = time.time,
    random_token: Callable[[int], str] = secrets.token_urlsafe,
) -> EnrollmentReceipt:
    try:
        policy = load_installed_policy(policy_path, expected_uid=expected_uid)
    except ExecutiveAuthError:
        raise EnrollmentError("installed Executive auth policy is unavailable") from None
    registrations = KeychainRegistrationStore() if registration_store is None else registration_store
    credentials = KeychainCredentialStore() if credential_store is None else credential_store
    metadata = discover_metadata(policy, get_json=get_json)
    registration = ensure_client_registration(
        policy, metadata, store=registrations, post_json=post_json
    )
    try:
        existing_credential = credentials.load_optional()
    except ExecutiveAuthError:
        raise EnrollmentError("stored Executive OAuth credential is invalid") from None
    if (
        existing_credential is not None
        and existing_credential.client_id != registration.client_id
    ):
        raise EnrollmentError("stored Executive OAuth client does not match registration")
    state = random_token(32)
    verifier = random_token(64)
    if (
        not isinstance(state, str) or len(state) < 32
        or not isinstance(verifier, str) or not 43 <= len(verifier) <= 128
    ):
        raise EnrollmentError("Executive PKCE entropy source is invalid")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    url = build_authorize_url(
        policy, metadata, registration, state=state, code_challenge=challenge
    )
    try:
        code = authorize_code(url, state)
    except EnrollmentError:
        raise
    except Exception:
        raise EnrollmentError("Executive OAuth authorization failed") from None
    bundle = exchange_authorization_code(
        policy,
        metadata,
        registration,
        code=code,
        code_verifier=verifier,
        now_epoch=int(now_fn()),
        store=credentials,
        post_form=post_form,
    )
    return EnrollmentReceipt(
        client_id_digest=hashlib.sha256(registration.client_id.encode("utf-8")).hexdigest(),
        policy_digest=policy.policy_digest,
        expires_at=bundle.expires_at,
    )


def main(
    argv: list[str] | None = None,
    *,
    policy_path=DEFAULT_POLICY_PATH,
    expected_uid: int = 0,
    registration_store: KeychainRegistrationStore | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reconcile-client-id",
        help="public Auth0 DCR client id observed by an authorized tenant admin",
    )
    parser.add_argument(
        "--reconcile-attempt-ref",
        help="exact pending DCR attempt ref read from the local registration state",
    )
    parser.add_argument(
        "--reconcile-client-name",
        help="exact attempt-fingerprinted Auth0 client name observed by the tenant admin",
    )
    parser.add_argument(
        "--pending-status",
        action="store_true",
        help="print non-secret metadata for the exact pending DCR operation",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        reconciliation_values = (
            args.reconcile_client_id,
            args.reconcile_attempt_ref,
            args.reconcile_client_name,
        )
        if args.pending_status and any(
            value is not None for value in reconciliation_values
        ):
            raise EnrollmentError(
                "pending status cannot be combined with reconciliation"
            )
        if any(value is None for value in reconciliation_values) and any(
            value is not None for value in reconciliation_values
        ):
            raise EnrollmentError(
                "reconciliation requires client id, attempt ref, and client name together"
            )
        if args.pending_status:
            registrations = (
                KeychainRegistrationStore()
                if registration_store is None
                else registration_store
            )
            policy = load_installed_policy(policy_path, expected_uid=expected_uid)
            payload = pending_registration_status(policy, store=registrations)
        elif args.reconcile_client_id is not None:
            registrations = (
                KeychainRegistrationStore()
                if registration_store is None
                else registration_store
            )
            policy = load_installed_policy(policy_path, expected_uid=expected_uid)
            registration = reconcile_pending_registration(
                policy,
                store=registrations,
                observed_client_id=args.reconcile_client_id,
                observed_attempt_ref=args.reconcile_attempt_ref,
                observed_client_name=args.reconcile_client_name,
            )
            payload = {
                "client_id_digest": hashlib.sha256(
                    registration.client_id.encode("utf-8")
                ).hexdigest(),
                "policy_digest": registration.policy_digest,
                "state": "reconciled",
            }
        else:
            receipt = enroll_once(
                policy_path=policy_path,
                expected_uid=expected_uid,
                registration_store=registration_store,
            )
            payload = dataclasses.asdict(receipt)
    except Exception:
        print("REFUSED: Executive MCP enrollment unavailable.", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
