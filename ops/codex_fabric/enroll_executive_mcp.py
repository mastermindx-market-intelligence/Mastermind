"""One-time public-client enrollment contracts for Codex -> Executive MCP.

DCR/PKCE is client-side only.  Executive OAuth resource policy and JWT
verification remain owned by the installed server.  DCR client identity is
persisted before user authorization so an interrupted login never creates a
new Auth0 application on every retry.
"""
from __future__ import annotations

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
REGISTRATION_ACCOUNT = b"astra-executive-registration"
_REGISTRATION_KEYS = frozenset({"schema", "client_id", "redirect_uri", "policy_digest"})


class EnrollmentError(RuntimeError):
    """Closed enrollment refusal; never contains codes, tokens, or browser payloads."""


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


class KeychainRegistrationStore:
    """One fixed public DCR client identity, separate from the token bundle."""

    def __init__(self, *, api=None):
        self._api = api if api is not None else _MacKeychainApi()

    def load_optional(self) -> ClientRegistration | None:
        raw = self._api.read(KEYCHAIN_SERVICE, REGISTRATION_ACCOUNT)
        if raw is None:
            return None
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_CREDENTIAL_BYTES:
            raise EnrollmentError("stored Executive client registration is invalid")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise EnrollmentError("stored Executive client registration is invalid") from None
        if not isinstance(value, dict) or set(value) != _REGISTRATION_KEYS:
            raise EnrollmentError("stored Executive client registration is invalid")
        client_id = value.get("client_id")
        redirect_uri = value.get("redirect_uri")
        policy_digest = value.get("policy_digest")
        if (
            value.get("schema") != REGISTRATION_SCHEMA
            or not isinstance(client_id, str) or not client_id.startswith("tpc_")
            or not isinstance(redirect_uri, str) or redirect_uri != CALLBACK_URL
            or not isinstance(policy_digest, str) or len(policy_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in policy_digest)
        ):
            raise EnrollmentError("stored Executive client registration is invalid")
        return ClientRegistration(client_id, redirect_uri, policy_digest)

    def save(self, registration: ClientRegistration) -> None:
        if (
            not isinstance(registration, ClientRegistration)
            or not registration.client_id.startswith("tpc_")
            or registration.redirect_uri != CALLBACK_URL
            or len(registration.policy_digest) != 64
        ):
            raise EnrollmentError("Executive client registration is invalid")
        raw = json.dumps(
            {
                "schema": REGISTRATION_SCHEMA,
                "client_id": registration.client_id,
                "redirect_uri": registration.redirect_uri,
                "policy_digest": registration.policy_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self._api.upsert(KEYCHAIN_SERVICE, REGISTRATION_ACCOUNT, raw)


def _exact_issuer_endpoint(policy: ExecutiveAuthPolicy, suffix: str, value: Any) -> str:
    expected = policy.issuer.rstrip("/") + suffix
    if value != expected:
        raise EnrollmentError("Executive authorization metadata is incompatible")
    return expected


def discover_metadata(
    policy: ExecutiveAuthPolicy,
    *,
    get_json: Callable[[str], Mapping[str, Any]],
) -> OidcMetadata:
    discovery_url = policy.issuer.rstrip("/") + "/.well-known/openid-configuration"
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
) -> ClientRegistration:
    existing = store.load_optional()
    if existing is not None:
        if existing.policy_digest != policy.policy_digest or existing.redirect_uri != CALLBACK_URL:
            raise EnrollmentError("stored Executive client registration does not match installed policy")
        return existing
    request = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [CALLBACK_URL],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    try:
        response = post_json(metadata.registration_endpoint, request)
    except EnrollmentError:
        raise
    except Exception:
        raise EnrollmentError("Executive public client registration failed") from None
    if not isinstance(response, Mapping):
        raise EnrollmentError("Executive public client registration failed")
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
        raise EnrollmentError("Executive public client registration failed")
    registration = ClientRegistration(client_id, CALLBACK_URL, policy.policy_digest)
    store.save(registration)
    return registration


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
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
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


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("REFUSED: Executive MCP enrollment unavailable.", file=sys.stderr)
        return 2
    try:
        receipt = enroll_once()
    except Exception:
        print("REFUSED: Executive MCP enrollment unavailable.", file=sys.stderr)
        return 2
    print(json.dumps(dataclasses.asdict(receipt), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
