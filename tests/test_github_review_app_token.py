"""No-key-log JWT / installation scope proof with synthetic ephemeral RSA key."""
import datetime
import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from integrations.github_review_app_token import (
    GitHubAppInstallationTokens, GitHubAppTokenUnavailable,
)

NOW = 1792660000.0


def private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key, pem


def make(handler, pem):
    return GitHubAppInstallationTokens(
        app_id=123, installation_id=4242, repository="example/repo",
        private_key_source=lambda: pem,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: NOW,
    )


def test_signed_jwt_requests_only_scoped_repo_and_narrow_permissions():
    key, pem = private_key()
    calls = []
    expires = datetime.datetime.fromtimestamp(
        NOW + 3000, tz=datetime.timezone.utc
    ).isoformat().replace("+00:00", "Z")

    def handler(req):
        calls.append(req)
        assert req.url.path == "/app/installations/4242/access_tokens"
        assert req.method == "POST"
        auth = req.headers["authorization"]
        assert auth.startswith("Bearer ")
        signed = auth.removeprefix("Bearer ")
        claims = jwt.decode(
            signed, key.public_key(),
            algorithms=["RS256"], options={"verify_exp": False}
        )
        assert claims["iss"] == "123"
        assert claims["iat"] == int(NOW) - 60
        assert claims["exp"] == int(NOW) + 480
        request = json.loads(req.content)
        assert request["repositories"] == ["repo"]
        assert request["permissions"] == {
            "contents": "read", "pull_requests": "write",
        }
        return httpx.Response(201, json={
            "token": "ghs_APPID_JWT_unique_token_any_length",
            "expires_at": expires,
            "permissions": {"metadata": "read", "contents": "read",
                            "pull_requests": "write"},
            "repositories": [{"full_name": "example/repo"}],
        })

    app = make(handler, pem)
    assert app.token_for_installation(installation_id=4242).startswith("ghs_")
    assert app.token_for_installation(installation_id=4242).startswith("ghs_")
    assert len(calls) == 1  # Process-local bounded token reuse.
    assert pem.decode() not in repr(app)
    with pytest.raises(GitHubAppTokenUnavailable, match="OUT_OF_SCOPE"):
        app.token_for_installation(installation_id=4243)
    assert len(calls) == 1


def test_broadened_token_grants_fail_closed_without_leaking_token():
    _, pem = private_key()
    def handler(req):
        return httpx.Response(201, json={
            "token": "SENSITIVE_INVALID_TOKEN",
            "expires_at": "2026-10-22T16:00:00Z",
            "permissions": {"contents": "write", "pull_requests": "write"},
            "repositories": [{"full_name": "example/repo"}],
        })
    app = make(handler, pem)
    with pytest.raises(GitHubAppTokenUnavailable, match="UNAVAILABLE") as e:
        app.token_for_installation(installation_id=4242)
    assert "SENSITIVE_INVALID_TOKEN" not in str(e.value)


def test_redirect_is_not_followed_to_attacker():
    _, pem = private_key()
    calls = []
    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(302, headers={"location": "https://evil.example/token"})
    app = make(handler, pem)
    with pytest.raises(GitHubAppTokenUnavailable, match="UNAVAILABLE"):
        app.token_for_installation(installation_id=4242)
    assert len(calls) == 1 and "evil.example" not in calls[0]
