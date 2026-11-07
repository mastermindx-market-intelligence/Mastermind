import asyncio
import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.os_publication_auth import (
    OsPublicationAuthenticator, PublicationAuthRefused, RESOURCE,
)
from integrations.mastermind_executive_app.os_transport import principal_scope

rsa_key = fixture.rsa_key
other_rsa_key = fixture.other_rsa_key


class Audit:
    def __init__(self):
        self.events = []
        self.fail = False

    def emit(self, event):
        if self.fail:
            raise OSError("private audit failure")
        self.events.append(event)


def token(key, **claims):
    claims.setdefault("scope", f"{fixture.READ_SCOPE} {fixture.SUBMIT_SCOPE}")
    return fixture._token(key, aud=RESOURCE, **claims)


def composition(key, *, grants=None):
    policy = fixture._submit_policy(
        resource=RESOURCE, resource_metadata_url=RESOURCE + "/.well-known/oauth-protected-resource",
    )
    auth = JwtAuthenticator(policy=policy, jwks_cache=fixture._FakeJwksCache(key))
    clock = [fixture.NOW]
    sink = Audit()
    verifier = MastermindTokenVerifier(authenticator=auth, policy=policy, now=lambda: clock[0], audit_sink=sink)
    principal = asyncio.run(auth.verify_token(token(key), now=fixture.NOW))
    namespace = principal_scope(principal)
    composed = OsPublicationAuthenticator(
        verifier=verifier, authenticator=auth,
        allowed_principal_scopes=(namespace,) if grants is None else grants,
        clock=lambda: clock[0],
    )
    return composed, auth, clock, sink, namespace


def test_signed_original_bearer_and_explicit_publication_grant(rsa_key):
    composed, _, _, sink, namespace = composition(rsa_key)
    result = asyncio.run(composed.authenticate(token(rsa_key)))
    assert result.principal_scope == namespace
    assert len(result.policy_digest) == 64
    assert result.expires_at > fixture.NOW
    assert sink.events[-1].accepted is True
    assert set(dataclasses.asdict(result)) == {"principal_scope", "policy_digest", "expires_at"}
    assert token(rsa_key) not in repr(result)


def test_valid_executive_identity_without_publication_grant_refuses(rsa_key):
    composed, *_ = composition(rsa_key, grants=("0" * 64,))
    with pytest.raises(PublicationAuthRefused, match="^publication authentication refused$"):
        asyncio.run(composed.authenticate(token(rsa_key)))


@pytest.mark.parametrize("claims", [
    {"scope": fixture.READ_SCOPE}, {"scope": fixture.SUBMIT_SCOPE},
    {"sub": "other-subject"}, {"azp": "different-client"},
    {"exp": fixture.NOW - 100}, {"iss": "https://foreign.example"},
])
def test_principal_scope_and_canonical_claim_checks(rsa_key, claims):
    composed, *_ = composition(rsa_key)
    with pytest.raises(PublicationAuthRefused):
        asyncio.run(composed.authenticate(token(rsa_key, **claims)))


def test_connector_audience_cannot_publish(rsa_key):
    composed, *_ = composition(rsa_key)
    with pytest.raises(PublicationAuthRefused):
        asyncio.run(composed.authenticate(fixture._submit_token(rsa_key)))


def test_wrong_signature_cannot_publish(rsa_key, other_rsa_key):
    composed, *_ = composition(rsa_key)
    with pytest.raises(PublicationAuthRefused):
        asyncio.run(composed.authenticate(token(other_rsa_key)))


def test_every_reauthorization_rechecks_expiry(rsa_key):
    composed, _, clock, _, _ = composition(rsa_key)
    bearer = token(rsa_key)
    asyncio.run(composed.authenticate(bearer))
    clock[0] += 1000
    with pytest.raises(PublicationAuthRefused):
        asyncio.run(composed.authenticate(bearer))


def test_audit_failure_is_not_identity(rsa_key):
    composed, _, _, sink, _ = composition(rsa_key)
    sink.fail = True
    with pytest.raises(PublicationAuthRefused):
        asyncio.run(composed.authenticate(token(rsa_key)))


def test_authenticator_policy_drift_closes(rsa_key):
    composed, auth, *_ = composition(rsa_key)
    auth._policy = dataclasses.replace(auth.policy, policy_id="changed")
    with pytest.raises(PublicationAuthRefused):
        asyncio.run(composed.authenticate(token(rsa_key)))


@pytest.mark.parametrize("grants", [(), [], ("bad",), ("a" * 64, "a" * 64)])
def test_no_default_or_ambiguous_publication_grant(rsa_key, grants):
    with pytest.raises(ValueError):
        composition(rsa_key, grants=grants)
