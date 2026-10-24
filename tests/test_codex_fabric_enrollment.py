from __future__ import annotations

import base64
import dataclasses
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from integrations.business_mcp_auth.contracts import subject_digest
from ops.codex_fabric.executive_mcp_auth import (
    CredentialBundle,
    KeychainCredentialStore,
    load_installed_policy,
)
from ops.codex_fabric.enroll_executive_mcp import (
    CALLBACK_URL,
    ClientRegistration,
    EnrollmentError,
    KeychainRegistrationStore,
    build_authorize_url,
    discover_metadata,
    ensure_client_registration,
    exchange_authorization_code,
)

ISSUER = "https://issuer.example.com/"
RESOURCE = "https://resource.example.com/executive"
SUBJECT = "auth0|chairman"
SCOPES = ("mastermind.executive.intent.submit", "mastermind.executive.read")
SUBJECT_DIGEST = subject_digest(issuer=ISSUER, subject=SUBJECT)


def _policy(tmp_path: Path):
    path = tmp_path / "executive-mcp.json"
    common = {
        "issuer": ISSUER,
        "resource": RESOURCE,
        "allowed_subject_digests": [SUBJECT_DIGEST],
    }
    path.write_text(json.dumps({"policies": {
        "read": {**common, "required_scopes": ["mastermind.executive.read"]},
        "submit": {**common, "required_scopes": list(SCOPES)},
    }}), encoding="utf-8")
    path.chmod(0o644)
    return load_installed_policy(path, expected_uid=os.getuid())


def _seg(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(*, exp: int = 2_000_000_000, audience: str = RESOURCE) -> str:
    return ".".join((
        _seg({"alg": "RS256", "typ": "JWT"}),
        _seg({
            "iss": ISSUER,
            "aud": audience,
            "sub": SUBJECT,
            "scope": " ".join((*SCOPES, "offline_access")),
            "exp": exp,
            "iat": 1_900_000_000,
        }),
        "signature",
    ))


class BlobApi:
    def __init__(self):
        self.values = {}
    def read(self, service: bytes, account: bytes):
        return self.values.get((service, account))
    def upsert(self, service: bytes, account: bytes, value: bytes):
        self.values[(service, account)] = value
    def delete(self, service: bytes, account: bytes):
        return self.values.pop((service, account), None) is not None


def _metadata_document(**updates):
    value = {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "authorize",
        "token_endpoint": ISSUER + "oauth/token",
        "registration_endpoint": ISSUER + "oidc/register",
        "code_challenge_methods_supported": ["S256", "plain"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "scopes_supported": ["openid", "profile", "offline_access"],
    }
    value.update(updates)
    return value


def test_discovery_requires_exact_same_issuer_endpoints_and_pkce(tmp_path: Path):
    policy = _policy(tmp_path)
    seen = []
    metadata = discover_metadata(policy, get_json=lambda url: seen.append(url) or _metadata_document())
    assert seen == [ISSUER + ".well-known/openid-configuration"]
    assert metadata.authorization_endpoint == ISSUER + "authorize"
    assert metadata.token_endpoint == ISSUER + "oauth/token"
    assert metadata.registration_endpoint == ISSUER + "oidc/register"

    for mutation in (
        {"issuer": "https://other.example.com/"},
        {"token_endpoint": "https://evil.example.com/oauth/token"},
        {"registration_endpoint": "https://evil.example.com/oidc/register"},
        {"code_challenge_methods_supported": ["plain"]},
        {"grant_types_supported": ["authorization_code"]},
    ):
        with pytest.raises(EnrollmentError):
            discover_metadata(policy, get_json=lambda _url, m=mutation: _metadata_document(**m))


def test_discovery_refuses_malformed_policy_issuer_before_network(tmp_path: Path):
    policy = _policy(tmp_path)
    malformed = dataclasses.replace(policy, issuer="http://issuer.example.com/")
    seen = []
    with pytest.raises(EnrollmentError):
        discover_metadata(malformed, get_json=lambda url: seen.append(url) or _metadata_document())
    assert seen == []


def test_dcr_registration_is_persisted_and_reused_without_duplicate_client(tmp_path: Path):
    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    api = BlobApi()
    store = KeychainRegistrationStore(api=api)
    calls = []

    def post_json(url, payload):
        calls.append((url, payload))
        return {
            "client_name": "Mastermind Codex Astra aaaaaaaaaaaaaaaa",
            "client_id": "tpc_client123",
            "redirect_uris": [CALLBACK_URL],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        }

    first = ensure_client_registration(
        policy, metadata, store=store, post_json=post_json,
        attempt_ref_fn=lambda: "a" * 64,
    )
    second = ensure_client_registration(policy, metadata, store=store, post_json=lambda *_: pytest.fail("duplicate DCR"))
    assert first == second == ClientRegistration(
        client_id="tpc_client123", redirect_uri=CALLBACK_URL, policy_digest=policy.policy_digest
    )
    assert len(calls) == 1
    assert calls[0][0] == ISSUER + "oidc/register"
    assert calls[0][1] == {
        "client_name": "Mastermind Codex Astra aaaaaaaaaaaaaaaa",
        "redirect_uris": [CALLBACK_URL],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }


def test_dcr_refuses_secret_or_incomplete_public_client(tmp_path: Path):
    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    for response in (
        {"client_id": "client-no-tpc", "redirect_uris": [CALLBACK_URL], "grant_types": ["authorization_code", "refresh_token"], "token_endpoint_auth_method": "none"},
        {"client_id": "tpc_secret", "client_secret": "do-not-own", "redirect_uris": [CALLBACK_URL], "grant_types": ["authorization_code", "refresh_token"], "token_endpoint_auth_method": "none"},
        {"client_id": "tpc_norefresh", "redirect_uris": [CALLBACK_URL], "grant_types": ["authorization_code"], "token_endpoint_auth_method": "none"},
    ):
        with pytest.raises(EnrollmentError):
            ensure_client_registration(
                policy, metadata, store=KeychainRegistrationStore(api=BlobApi()),
                post_json=lambda *_args, r=response: r,
            )


def test_authorize_url_uses_exact_audience_scopes_state_and_s256_without_openid(tmp_path: Path):
    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    registration = ClientRegistration("tpc_client123", CALLBACK_URL, policy.policy_digest)
    url = build_authorize_url(
        policy, metadata, registration,
        state="state-123", code_challenge="challenge-456",
    )
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme + "://" + parsed.netloc + parsed.path == ISSUER + "authorize"
    assert query == {
        "response_type": ["code"],
        "client_id": ["tpc_client123"],
        "redirect_uri": [CALLBACK_URL],
        "audience": [RESOURCE],
        "scope": ["mastermind.executive.intent.submit mastermind.executive.read offline_access"],
        "state": ["state-123"],
        "code_challenge": ["challenge-456"],
        "code_challenge_method": ["S256"],
    }
    assert "openid" not in query["scope"][0]


def test_code_exchange_validates_access_token_then_saves_keychain_bundle(tmp_path: Path):
    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    registration = ClientRegistration("tpc_client123", CALLBACK_URL, policy.policy_digest)
    api = BlobApi()
    credential_store = KeychainCredentialStore(api=api)
    observed = []

    result = exchange_authorization_code(
        policy, metadata, registration,
        code="authorization-code", code_verifier="v" * 64,
        now_epoch=1_900_000_100, store=credential_store,
        post_form=lambda url, fields: observed.append((url, fields)) or {
            "access_token": _token(), "refresh_token": "refresh-issued", "token_type": "Bearer"
        },
    )
    assert result.client_id == "tpc_client123"
    assert result.refresh_token == "refresh-issued"
    assert observed == [(ISSUER + "oauth/token", {
        "grant_type": "authorization_code",
        "client_id": "tpc_client123",
        "code": "authorization-code",
        "code_verifier": "v" * 64,
        "redirect_uri": CALLBACK_URL,
    })]
    assert credential_store.load() == result


def test_invalid_code_exchange_token_never_mutates_credential_store(tmp_path: Path):
    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    registration = ClientRegistration("tpc_client123", CALLBACK_URL, policy.policy_digest)
    api = BlobApi()
    store = KeychainCredentialStore(api=api)

    with pytest.raises(EnrollmentError):
        exchange_authorization_code(
            policy, metadata, registration,
            code="authorization-code", code_verifier="v" * 64,
            now_epoch=1_900_000_100, store=store,
            post_form=lambda *_: {
                "access_token": _token(audience="https://wrong.example.com/"),
                "refresh_token": "refresh-issued", "token_type": "Bearer",
            },
        )
    assert api.values == {}


def test_enroll_once_persists_dcr_before_browser_and_binds_pkce(tmp_path: Path):
    import hashlib
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy_path = tmp_path / "executive-mcp.json"
    common = {"issuer": ISSUER, "resource": RESOURCE, "allowed_subject_digests": [SUBJECT_DIGEST]}
    policy_path.write_text(json.dumps({"policies": {
        "read": {**common, "required_scopes": ["mastermind.executive.read"]},
        "submit": {**common, "required_scopes": list(SCOPES)},
    }}), encoding="utf-8")
    policy_path.chmod(0o644)
    registration_api = BlobApi()
    credential_api = BlobApi()
    registration_store = KeychainRegistrationStore(api=registration_api)
    credential_store = KeychainCredentialStore(api=credential_api)
    authorize_seen = {}
    exchange_seen = {}

    def authorize(url: str, expected_state: str) -> str:
        assert registration_store.load_optional() is not None
        query = parse_qs(urlsplit(url).query)
        assert query["state"] == [expected_state]
        authorize_seen.update(query)
        return "auth-code"

    def post_form(url, fields):
        exchange_seen["url"] = url
        exchange_seen["fields"] = fields
        return {"access_token": _token(), "refresh_token": "refresh-live", "token_type": "Bearer"}

    receipt = enroll.enroll_once(
        policy_path=policy_path,
        expected_uid=os.getuid(),
        registration_store=registration_store,
        credential_store=credential_store,
        get_json=lambda _url: _metadata_document(),
        post_json=lambda _url, _payload: {
            "client_name": "Mastermind Codex Astra",
            "client_id": "tpc_client123",
            "redirect_uris": [CALLBACK_URL],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        },
        post_form=post_form,
        authorize_code=authorize,
        now_fn=lambda: 1_900_000_100,
        random_token=lambda n: "s" * 43 if n == 32 else "v" * 64,
    )
    verifier = exchange_seen["fields"]["code_verifier"]
    expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert authorize_seen["code_challenge"] == [expected_challenge]
    assert receipt.policy_digest == load_installed_policy(policy_path, expected_uid=os.getuid()).policy_digest
    assert len(receipt.client_id_digest) == 64
    assert receipt.expires_at == 2_000_000_000
    assert credential_store.load().refresh_token == "refresh-live"


def test_enroll_once_refuses_existing_credential_bound_to_different_client_before_browser(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    registration_store = KeychainRegistrationStore(api=BlobApi())
    registration_store.save(ClientRegistration("tpc_registration", CALLBACK_URL, policy.policy_digest))
    credential_store = KeychainCredentialStore(api=BlobApi())
    credential_store.save(CredentialBundle(
        client_id="tpc_other",
        access_token=_token(),
        refresh_token="refresh-existing",
        expires_at=2_000_000_000,
        policy_digest=policy.policy_digest,
    ))
    browser_calls = []
    with pytest.raises(EnrollmentError, match="client"):
        enroll.enroll_once(
            policy_path=policy_path,
            expected_uid=os.getuid(),
            registration_store=registration_store,
            credential_store=credential_store,
            get_json=lambda _url: _metadata_document(),
            post_json=lambda *_: pytest.fail("DCR must not repeat"),
            authorize_code=lambda *_args: browser_calls.append(True) or "code",
        )
    assert browser_calls == []


def test_enroll_once_reuses_persisted_dcr_client_without_second_registration(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    registration_api = BlobApi()
    registration_store = KeychainRegistrationStore(api=registration_api)
    registration_store.save(ClientRegistration("tpc_existing", CALLBACK_URL, policy.policy_digest))
    credential_store = KeychainCredentialStore(api=BlobApi())

    receipt = enroll.enroll_once(
        policy_path=policy_path,
        expected_uid=os.getuid(),
        registration_store=registration_store,
        credential_store=credential_store,
        get_json=lambda _url: _metadata_document(),
        post_json=lambda *_: pytest.fail("DCR must not repeat"),
        post_form=lambda _url, _fields: {
            "access_token": _token(), "refresh_token": "refresh-live", "token_type": "Bearer"
        },
        authorize_code=lambda _url, _state: "auth-code",
        now_fn=lambda: 1_900_000_100,
        random_token=lambda n: "s" * 43 if n == 32 else "v" * 64,
    )
    assert receipt.client_id_digest != ""


def test_callback_parser_rejects_wrong_state_and_oauth_error():
    import ops.codex_fabric.enroll_executive_mcp as enroll

    assert enroll.parse_callback_target("/oauth/callback?code=abc&state=expected", expected_state="expected") == "abc"
    for target in (
        "/oauth/callback?code=abc&state=wrong",
        "/oauth/callback?error=access_denied&state=expected",
        "/wrong?code=abc&state=expected",
        "/oauth/callback?code=a&code=b&state=expected",
    ):
        with pytest.raises(EnrollmentError):
            enroll.parse_callback_target(target, expected_state="expected")


def test_enrollment_main_emits_only_redacted_receipt(monkeypatch, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    receipt = enroll.EnrollmentReceipt(
        client_id_digest="a" * 64,
        policy_digest="b" * 64,
        expires_at=2_000_000_000,
    )
    monkeypatch.setattr(enroll, "enroll_once", lambda **_kwargs: receipt)
    assert enroll.main([]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "client_id_digest": "a" * 64,
        "expires_at": 2_000_000_000,
        "policy_digest": "b" * 64,
    }
    assert "token" not in captured.out.lower()
    assert "client_id\"" not in captured.out
    assert captured.err == ""


def test_enrollment_main_defers_keychain_construction_to_enroll_once(monkeypatch, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    receipt = enroll.EnrollmentReceipt(
        client_id_digest="a" * 64,
        policy_digest="b" * 64,
        expires_at=2_000_000_000,
    )
    calls = []

    def fake_enroll_once(**kwargs):
        calls.append(kwargs)
        return receipt

    monkeypatch.setattr(
        enroll,
        "KeychainRegistrationStore",
        lambda: pytest.fail("normal enrollment must not construct the platform store in main"),
    )
    monkeypatch.setattr(enroll, "enroll_once", fake_enroll_once)

    assert enroll.main([]) == 0
    assert len(calls) == 1
    assert calls[0]["registration_store"] is None
    captured = capsys.readouterr()
    assert captured.err == ""


def test_dcr_persists_attempt_before_post_and_ambiguous_failure_blocks_retry(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    store = KeychainRegistrationStore(api=BlobApi())
    observed = []

    def ambiguous_post(_url, _payload):
        state = store.load_state()
        observed.append(state)
        assert isinstance(state, enroll.PendingRegistration)
        raise TimeoutError("response lost")

    with pytest.raises(enroll.EnrollmentEffectUnknown):
        ensure_client_registration(
            policy, metadata, store=store, post_json=ambiguous_post,
            attempt_ref_fn=lambda: "a" * 64,
        )
    assert len(observed) == 1
    pending = store.load_state()
    assert isinstance(pending, enroll.PendingRegistration)
    assert pending.attempt_ref == "a" * 64

    with pytest.raises(enroll.EnrollmentEffectUnknown):
        ensure_client_registration(
            policy, metadata, store=store,
            post_json=lambda *_: pytest.fail("effect-unknown DCR must never retry"),
            attempt_ref_fn=lambda: "b" * 64,
        )


def test_invalid_dcr_success_payload_keeps_effect_unknown_marker(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    store = KeychainRegistrationStore(api=BlobApi())

    with pytest.raises(enroll.EnrollmentEffectUnknown):
        ensure_client_registration(
            policy, metadata, store=store,
            post_json=lambda *_: {"client_id": "unexpected-shape"},
            attempt_ref_fn=lambda: "c" * 64,
        )
    assert isinstance(store.load_state(), enroll.PendingRegistration)


def test_definitive_dcr_refusal_clears_only_same_pending_attempt(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    metadata = discover_metadata(policy, get_json=lambda _url: _metadata_document())
    store = KeychainRegistrationStore(api=BlobApi())

    def refused(_url, _payload):
        raise enroll.EnrollmentDefinitiveRefusal("refused")

    with pytest.raises(EnrollmentError, match="refused"):
        ensure_client_registration(
            policy, metadata, store=store, post_json=refused,
            attempt_ref_fn=lambda: "9" * 64,
        )
    assert store.load_state() is None


def test_http_400_oauth_error_is_definitive_dcr_refusal(monkeypatch):
    import io
    import urllib.error
    import ops.codex_fabric.enroll_executive_mcp as enroll

    body = json.dumps({"error": "invalid_client_metadata", "error_description": "blocked"}).encode()
    error = urllib.error.HTTPError(
        ISSUER + "oidc/register", 400, "Bad Request", {}, io.BytesIO(body)
    )
    monkeypatch.setattr(enroll.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(enroll.EnrollmentDefinitiveRefusal):
        enroll._post_json(ISSUER + "oidc/register", {"client_name": "x"})


def test_legacy_prefingerprint_pending_marker_stays_readable_but_is_not_reconcilable(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    api = BlobApi()
    raw = json.dumps({
        "schema": "mastermind.codex_fabric.executive_mcp_registration_attempt.v1",
        "attempt_ref": "c" * 64,
        "redirect_uri": CALLBACK_URL,
        "policy_digest": policy.policy_digest,
    }, sort_keys=True, separators=(",", ":")).encode()
    api.values[(enroll.KEYCHAIN_SERVICE, enroll.REGISTRATION_ACCOUNT)] = raw
    store = KeychainRegistrationStore(api=api)
    state = store.load_state()
    assert isinstance(state, enroll.PendingRegistration)
    assert state.client_name is None
    with pytest.raises(EnrollmentError, match="reconcil"):
        enroll.reconcile_pending_registration(
            policy, store=store, observed_client_id="tpc_any",
            observed_attempt_ref="c" * 64,
            observed_client_name="Mastermind Codex Astra cccccccccccccccc",
        )
    assert store.load_state() == state


def _legacy_pending_store(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    api = BlobApi()
    api.values[(enroll.KEYCHAIN_SERVICE, enroll.REGISTRATION_ACCOUNT)] = json.dumps({
        "schema": "mastermind.codex_fabric.executive_mcp_registration_attempt.v1",
        "attempt_ref": "c" * 64,
        "redirect_uri": CALLBACK_URL,
        "policy_digest": policy.policy_digest,
    }, sort_keys=True, separators=(",", ":")).encode()
    return policy, api, KeychainRegistrationStore(api=api)


def test_legacy_reconciliation_accepts_one_exact_tenant_observation_without_dcr(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy, _api, store = _legacy_pending_store(tmp_path)
    registration, observation_digest = enroll.reconcile_legacy_pending_registration(
        policy,
        store=store,
        observed_client_id="tpc_legacy_exact",
        observed_attempt_ref="c" * 64,
        observed_client_name="Mastermind Codex Astra",
        observed_redirect_uri=CALLBACK_URL,
        observed_policy_digest=policy.policy_digest,
        observed_match_count=1,
        observed_at_epoch=1_790_000_000,
    )
    assert registration == ClientRegistration(
        "tpc_legacy_exact", CALLBACK_URL, policy.policy_digest
    )
    assert store.load_state() == registration
    assert len(observation_digest) == 64
    assert "tpc_legacy_exact" not in observation_digest


@pytest.mark.parametrize("field,value", [
    ("observed_attempt_ref", "d" * 64),
    ("observed_client_name", "Mastermind Codex Astra wrong"),
    ("observed_redirect_uri", "http://127.0.0.1:9999/oauth/callback"),
    ("observed_policy_digest", "f" * 64),
    ("observed_client_id", "client_not_tpc"),
    ("observed_match_count", 0),
    ("observed_match_count", 2),
])
def test_legacy_reconciliation_refuses_mismatched_or_nonunique_tenant_evidence(
    tmp_path: Path, field: str, value
):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy, _api, store = _legacy_pending_store(tmp_path)
    before = store.load_state()
    kwargs = {
        "observed_client_id": "tpc_legacy_exact",
        "observed_attempt_ref": "c" * 64,
        "observed_client_name": "Mastermind Codex Astra",
        "observed_redirect_uri": CALLBACK_URL,
        "observed_policy_digest": policy.policy_digest,
        "observed_match_count": 1,
        "observed_at_epoch": 1_790_000_000,
    }
    kwargs[field] = value
    with pytest.raises(EnrollmentError):
        enroll.reconcile_legacy_pending_registration(policy, store=store, **kwargs)
    assert store.load_state() == before


def test_legacy_reconciliation_readback_ambiguity_stays_effect_unknown(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy, api, store = _legacy_pending_store(tmp_path)
    original_read = api.read
    reads = {"count": 0}

    def ambiguous_read(service, account):
        reads["count"] += 1
        if reads["count"] >= 2:
            raise OSError("ambiguous keychain readback")
        return original_read(service, account)

    api.read = ambiguous_read
    with pytest.raises(enroll.EnrollmentEffectUnknown):
        enroll.reconcile_legacy_pending_registration(
            policy,
            store=store,
            observed_client_id="tpc_legacy_exact",
            observed_attempt_ref="c" * 64,
            observed_client_name="Mastermind Codex Astra",
            observed_redirect_uri=CALLBACK_URL,
            observed_policy_digest=policy.policy_digest,
            observed_match_count=1,
            observed_at_epoch=1_790_000_000,
        )


def test_cli_legacy_reconciliation_emits_digest_only_receipt(tmp_path: Path, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy, _api, store = _legacy_pending_store(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    public_id = "tpc_legacy_cli"
    code = enroll.main(
        [
            "--legacy-reconcile",
            "--reconcile-client-id", public_id,
            "--reconcile-attempt-ref", "c" * 64,
            "--reconcile-client-name", "Mastermind Codex Astra",
            "--reconcile-redirect-uri", CALLBACK_URL,
            "--reconcile-policy-digest", policy.policy_digest,
            "--reconcile-match-count", "1",
            "--reconcile-observed-at-epoch", "1790000000",
        ],
        policy_path=policy_path,
        expected_uid=os.getuid(),
        registration_store=store,
    )
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["state"] == "reconciled_legacy"
    assert payload["policy_digest"] == policy.policy_digest
    assert len(payload["client_id_digest"]) == 64
    assert len(payload["observation_digest"]) == 64
    assert public_id not in captured.out
    assert "client_secret" not in captured.out
    assert "access_token" not in captured.out
    assert "refresh_token" not in captured.out
    assert captured.err == ""


def test_reconcile_pending_registration_accepts_exact_public_client_without_new_dcr(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    api = BlobApi()
    store = KeychainRegistrationStore(api=api)
    store.save_pending(enroll.PendingRegistration("d" * 64, CALLBACK_URL, policy.policy_digest, "Mastermind Codex Astra dddddddddddddddd"))

    reconciled = enroll.reconcile_pending_registration(
        policy,
        store=store,
        observed_client_id="tpc_reconciled123",
        observed_attempt_ref="d" * 64,
        observed_client_name="Mastermind Codex Astra dddddddddddddddd",
    )
    assert reconciled == ClientRegistration(
        "tpc_reconciled123", CALLBACK_URL, policy.policy_digest
    )
    assert store.load_state() == reconciled


def test_reconcile_pending_registration_refuses_absent_completed_stale_or_non_tpc(tmp_path: Path):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)

    with pytest.raises(EnrollmentError):
        enroll.reconcile_pending_registration(
            policy, store=KeychainRegistrationStore(api=BlobApi()), observed_client_id="tpc_x", observed_attempt_ref="a" * 64, observed_client_name="Mastermind Codex Astra aaaaaaaaaaaaaaaa"
        )

    completed_api = BlobApi()
    completed = KeychainRegistrationStore(api=completed_api)
    completed.save(ClientRegistration("tpc_existing", CALLBACK_URL, policy.policy_digest))
    with pytest.raises(EnrollmentError):
        enroll.reconcile_pending_registration(policy, store=completed, observed_client_id="tpc_other", observed_attempt_ref="a" * 64, observed_client_name="Mastermind Codex Astra aaaaaaaaaaaaaaaa")

    stale_api = BlobApi()
    stale = KeychainRegistrationStore(api=stale_api)
    stale.save_pending(enroll.PendingRegistration("e" * 64, CALLBACK_URL, "f" * 64, "Mastermind Codex Astra eeeeeeeeeeeeeeee"))
    with pytest.raises(EnrollmentError):
        enroll.reconcile_pending_registration(policy, store=stale, observed_client_id="tpc_x", observed_attempt_ref="e" * 64, observed_client_name="Mastermind Codex Astra eeeeeeeeeeeeeeee")

    pending_api = BlobApi()
    pending = KeychainRegistrationStore(api=pending_api)
    pending.save_pending(enroll.PendingRegistration("a" * 64, CALLBACK_URL, policy.policy_digest, "Mastermind Codex Astra aaaaaaaaaaaaaaaa"))
    for bad in ("client123", "", " tpc_bad", "tpc_bad "):
        with pytest.raises(EnrollmentError):
            enroll.reconcile_pending_registration(policy, store=pending, observed_client_id=bad, observed_attempt_ref="a" * 64, observed_client_name="Mastermind Codex Astra aaaaaaaaaaaaaaaa")
    assert isinstance(pending.load_state(), enroll.PendingRegistration)
    with pytest.raises(EnrollmentError):
        enroll.reconcile_pending_registration(
            policy, store=pending, observed_client_id="tpc_valid", observed_attempt_ref="b" * 64, observed_client_name="Mastermind Codex Astra aaaaaaaaaaaaaaaa"
        )
    assert isinstance(pending.load_state(), enroll.PendingRegistration)
    with pytest.raises(EnrollmentError):
        enroll.reconcile_pending_registration(
            policy, store=pending, observed_client_id="tpc_valid",
            observed_attempt_ref="a" * 64, observed_client_name="Mastermind Codex Astra legacy"
        )
    assert isinstance(pending.load_state(), enroll.PendingRegistration)


def test_cli_reconciles_pending_public_client_id_without_echoing_it(tmp_path: Path, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    api = BlobApi()
    store = KeychainRegistrationStore(api=api)
    store.save_pending(enroll.PendingRegistration("f" * 64, CALLBACK_URL, policy.policy_digest, "Mastermind Codex Astra ffffffffffffffff"))
    public_id = "tpc_reconcile_cli_123"

    code = enroll.main(
        ["--reconcile-client-id", public_id, "--reconcile-attempt-ref", "f" * 64,
         "--reconcile-client-name", "Mastermind Codex Astra ffffffffffffffff"],
        policy_path=policy_path,
        expected_uid=os.getuid(),
        registration_store=store,
    )
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload == {
        "client_id_digest": __import__("hashlib").sha256(public_id.encode()).hexdigest(),
        "policy_digest": policy.policy_digest,
        "state": "reconciled",
    }
    assert public_id not in captured.out
    assert captured.err == ""
    assert store.load_state() == ClientRegistration(public_id, CALLBACK_URL, policy.policy_digest)


def test_cli_reconcile_refusal_is_opaque_and_does_not_clear_pending(tmp_path: Path, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    api = BlobApi()
    store = KeychainRegistrationStore(api=api)
    pending = enroll.PendingRegistration("a" * 64, CALLBACK_URL, policy.policy_digest, "Mastermind Codex Astra aaaaaaaaaaaaaaaa")
    store.save_pending(pending)

    code = enroll.main(
        ["--reconcile-client-id", "not-a-dcr-client", "--reconcile-attempt-ref", "a" * 64,
         "--reconcile-client-name", "Mastermind Codex Astra aaaaaaaaaaaaaaaa"],
        policy_path=policy_path,
        expected_uid=os.getuid(),
        registration_store=store,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == "REFUSED: Executive MCP enrollment unavailable.\n"
    assert store.load_state() == pending


def test_cli_pending_status_exposes_only_nonsecret_reconciliation_metadata(tmp_path: Path, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    store = KeychainRegistrationStore(api=BlobApi())
    store.save_pending(enroll.PendingRegistration(
        "7" * 64, CALLBACK_URL, policy.policy_digest,
        "Mastermind Codex Astra 7777777777777777",
    ))
    code = enroll.main(
        ["--pending-status"],
        policy_path=policy_path,
        expected_uid=os.getuid(),
        registration_store=store,
    )
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload == {
        "attempt_ref": "7" * 64,
        "client_name": "Mastermind Codex Astra 7777777777777777",
        "policy_digest": policy.policy_digest,
        "reconcilable": True,
        "redirect_uri": CALLBACK_URL,
        "state": "effect_unknown",
    }
    assert captured.err == ""


def test_cli_pending_status_marks_legacy_prefingerprint_marker_nonreconcilable(tmp_path: Path, capsys):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    policy = _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    api = BlobApi()
    api.values[(enroll.KEYCHAIN_SERVICE, enroll.REGISTRATION_ACCOUNT)] = json.dumps({
        "schema": "mastermind.codex_fabric.executive_mcp_registration_attempt.v1",
        "attempt_ref": "8" * 64,
        "redirect_uri": CALLBACK_URL,
        "policy_digest": policy.policy_digest,
    }, sort_keys=True, separators=(",", ":")).encode()
    code = enroll.main(
        ["--pending-status"], policy_path=policy_path, expected_uid=os.getuid(),
        registration_store=KeychainRegistrationStore(api=api),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["state"] == "effect_unknown"
    assert payload["reconcilable"] is False
    assert payload["client_name"] is None
    assert payload["attempt_ref"] == "8" * 64


def test_cli_normal_enrollment_keychain_unavailable_refuses_opaquely(
    tmp_path: Path, monkeypatch, capsys
):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    calls = []

    def unavailable_keychain():
        calls.append(True)
        raise OSError("Security.framework is unavailable")

    monkeypatch.setattr(enroll, "KeychainRegistrationStore", unavailable_keychain)

    code = enroll.main(
        [], policy_path=policy_path, expected_uid=os.getuid()
    )
    captured = capsys.readouterr()
    assert calls == [True]
    assert code == 2
    assert captured.out == ""
    assert captured.err == "REFUSED: Executive MCP enrollment unavailable.\n"


def test_cli_reconcile_keychain_unavailable_refuses_opaquely(
    tmp_path: Path, monkeypatch, capsys
):
    import ops.codex_fabric.enroll_executive_mcp as enroll

    _policy(tmp_path)
    policy_path = tmp_path / "executive-mcp.json"
    calls = []

    def unavailable_keychain():
        calls.append(True)
        raise OSError("Security.framework is unavailable")

    monkeypatch.setattr(enroll, "KeychainRegistrationStore", unavailable_keychain)

    code = enroll.main(
        [
            "--reconcile-client-id",
            "tpc_x",
            "--reconcile-attempt-ref",
            "a" * 64,
            "--reconcile-client-name",
            "Mastermind Codex Astra aaaaaaaaaaaaaaaa",
        ],
        policy_path=policy_path,
        expected_uid=os.getuid(),
    )
    captured = capsys.readouterr()
    assert calls == [True]
    assert code == 2
    assert captured.out == ""
    assert captured.err == "REFUSED: Executive MCP enrollment unavailable.\n"
