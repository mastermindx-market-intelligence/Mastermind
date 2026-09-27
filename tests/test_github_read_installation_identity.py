"""Read-service installation identity: synthetic signing keys and HTTP only."""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
import importlib.util
import json

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

from integrations.mastermind_github_app.github_port import HttpResponse

PERMISSIONS = {"administration": "read", "contents": "read", "metadata": "read"}
TOKEN = "synthetic_installation_value_" + "x" * 90


def test_concrete_read_installation_provider_exists():
    assert importlib.util.find_spec("integrations.mastermind_github_app.read_installation_identity") is not None


class Owner:
    def __init__(self):
        from integrations.mastermind_github_app.read_installation_identity import ReadInstallationBinding
        self.now = 1_790_000_000
        self.binding = ReadInstallationBinding(
            app_id=1234, installation_id=4567, account_id=8901,
            account_login="example", repository_id=2345, repository="example/repository",
            generation="credential:review-one", expires_at=self.now + 900)
        self.calls = []
        self.signs = 0
        self.variant = "normal"
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def current_binding(self):
        return self.binding

    def sign_app_jwt(self, *, app_id, issued_at, expires_at):
        self.signs += 1
        return jwt.encode({"iss": str(app_id), "iat": issued_at, "exp": expires_at},
                          self.key, algorithm="RS256")

    async def request(self, *, method, url, headers, body, timeout_seconds):
        assert 0 < timeout_seconds <= 20
        assert headers["Authorization"].startswith("Bearer ")
        claims = jwt.decode(headers["Authorization"][7:], self.key.public_key(), algorithms=["RS256"],
                            options={"verify_exp": False, "verify_iat": False})
        assert claims == {"iss": "1234", "iat": self.now - 60, "exp": self.now + 300}
        self.calls.append((method, url, json.loads(body) if body else None))
        if method == "GET":
            assert url == "https://api.github.com/repos/example/repository/installation"
            document = {"id": 4567, "app_id": 1234, "target_id": 8901, "target_type": "Organization",
                "account": {"id": 8901, "login": "example", "type": "Organization"},
                "suspended_at": None, "repository_selection": "selected", "permissions": dict(PERMISSIONS)}
            if self.variant == "wrong_app": document["app_id"] = 999
            if self.variant == "wrong_installation": document["id"] = 999
            if self.variant == "wrong_account": document["account"]["id"] = 999
            if self.variant == "suspended": document["suspended_at"] = "2026-01-01T00:00:00Z"
            if self.variant == "missing_suspension": del document["suspended_at"]
            if self.variant == "all_repositories": document["repository_selection"] = "all"
            if self.variant == "write_installation": document["permissions"]["administration"] = "write"
            if self.variant == "missing_permission": del document["permissions"]["administration"]
            if self.variant == "expire_preflight": self.now += 901
            if self.variant == "move_preflight": self.binding = dataclasses.replace(self.binding, generation="credential:two")
            if self.variant == "redirect": return HttpResponse(302, {"Location": "https://foreign.invalid"}, b"private")
            if self.variant == "permission_denied": return HttpResponse(403, {}, b"private-provider-details")
            return HttpResponse(200, {}, json.dumps(document).encode())
        assert method == "POST" and url == "https://api.github.com/app/installations/4567/access_tokens"
        assert json.loads(body) == {"repository_ids": [2345], "permissions": PERMISSIONS}
        if self.variant == "lost_post": raise OSError("private credential transport detail")
        if self.variant == "cancel_post": raise asyncio.CancelledError()
        if self.variant == "post_redirect": return HttpResponse(302, {}, b"private")
        if self.variant == "post_denied": return HttpResponse(403, {}, b"private")
        expiry = datetime.fromtimestamp(self.now + 3600, timezone.utc).isoformat().replace("+00:00", "Z")
        document = {"token": TOKEN, "expires_at": expiry, "permissions": dict(PERMISSIONS),
            "repository_selection": "selected", "repositories": [{"id": 2345, "full_name": "example/repository"}]}
        if self.variant == "write_token": document["permissions"]["contents"] = "write"
        if self.variant == "extra_permission": document["permissions"]["issues"] = "read"
        if self.variant == "wrong_repository": document["repositories"][0]["id"] = 999
        if self.variant == "wrong_repository_name": document["repositories"][0]["full_name"] = "foreign/repository"
        if self.variant == "extra_repository": document["repositories"].append({"id": 99, "full_name": "example/other"})
        if self.variant == "no_repositories": del document["repositories"]
        if self.variant == "expired_token": document["expires_at"] = "2000-01-01T00:00:00Z"
        if self.variant == "unbounded_expiry": document["expires_at"] = "2100-01-01T00:00:00Z"
        if self.variant == "invalid_token": document["token"] = "header\r\ninjection"
        if self.variant == "move_post": self.binding = dataclasses.replace(self.binding, generation="credential:two")
        if self.variant == "duplicate_json": return HttpResponse(201, {}, b'{"token":"first","token":"second"}')
        return HttpResponse(201, {}, json.dumps(document).encode())


def provider(owner, *, armed=True):
    from integrations.mastermind_github_app.read_installation_identity import ReadInstallationTokenProvider
    return ReadInstallationTokenProvider(resolve_binding=owner.current_binding, signer=owner,
        transport=owner, clock=lambda: owner.now, production_armed=armed)


def test_default_disarm_does_not_sign_or_contact_github():
    from integrations.mastermind_github_app.read_installation_identity import ReadInstallationTokenProvider, InstallationCredentialError
    owner = Owner()
    subject = ReadInstallationTokenProvider(resolve_binding=owner.current_binding, signer=owner,
        transport=owner, clock=lambda: owner.now)
    with pytest.raises(InstallationCredentialError, match="PRODUCTION_DISARMED"):
        asyncio.run(subject.installation_token())
    assert owner.signs == 0 and owner.calls == []


def test_exact_identity_scoped_token_and_cached_current_reuse():
    async def run():
        owner = Owner()
        subject = provider(owner)
        assert await subject.installation_token() == TOKEN
        assert await subject.installation_token() == TOKEN
        assert [c[0] for c in owner.calls] == ["GET", "POST"] and owner.signs == 1
        assert subject.evidence()["repository_id"] == 2345
        assert TOKEN not in json.dumps(subject.evidence())
    asyncio.run(run())


@pytest.mark.parametrize("variant", ["wrong_app", "wrong_installation", "wrong_account", "suspended",
    "missing_suspension", "all_repositories", "write_installation", "missing_permission",
    "expire_preflight", "move_preflight", "redirect", "permission_denied"])
def test_unqualified_installation_refuses_before_token_issuance(variant):
    from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
    owner = Owner(); owner.variant = variant
    with pytest.raises(InstallationCredentialError) as caught:
        asyncio.run(provider(owner).installation_token())
    assert all(call[0] == "GET" for call in owner.calls)
    assert "private" not in str(caught.value) and TOKEN not in str(caught.value)
    assert caught.value.issuance_possible is False


@pytest.mark.parametrize("variant", ["write_token", "extra_permission", "wrong_repository", "wrong_repository_name",
    "extra_repository", "no_repositories", "expired_token", "unbounded_expiry", "invalid_token", "move_post",
    "duplicate_json", "post_redirect", "post_denied", "lost_post"])
def test_post_boundary_failure_never_returns_token_or_reissues(variant):
    from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
    async def run():
        owner = Owner(); owner.variant = variant
        subject = provider(owner)
        with pytest.raises(InstallationCredentialError) as caught:
            await subject.installation_token()
        assert "private" not in str(caught.value) and TOKEN not in str(caught.value)
        assert caught.value.issuance_possible is True
        with pytest.raises(InstallationCredentialError, match="ISSUANCE_RECONCILIATION_REQUIRED"):
            await subject.installation_token()
        assert sum(call[0] == "POST" for call in owner.calls) == 1
        assert TOKEN not in json.dumps(subject.evidence())
    asyncio.run(run())


def test_cancellation_after_issuance_boundary_seals_original_provider():
    from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
    async def run():
        owner = Owner(); owner.variant = "cancel_post"
        subject = provider(owner)
        with pytest.raises(asyncio.CancelledError): await subject.installation_token()
        with pytest.raises(InstallationCredentialError, match="ISSUANCE_RECONCILIATION_REQUIRED"):
            await subject.installation_token()
        assert sum(call[0] == "POST" for call in owner.calls) == 1
    asyncio.run(run())


def test_cached_token_never_outlives_current_owner_authority():
    from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
    async def run():
        owner = Owner(); subject = provider(owner)
        await subject.installation_token()
        owner.now += 901
        with pytest.raises(InstallationCredentialError): await subject.installation_token()
        assert len(owner.calls) == 2
    asyncio.run(run())


def test_overlapping_requests_share_one_qualified_issuance():
    async def run():
        owner = Owner(); subject = provider(owner)
        assert await asyncio.gather(subject.installation_token(), subject.installation_token()) == [TOKEN, TOKEN]
        assert len(owner.calls) == 2
    asyncio.run(run())


def test_rsa_signer_uses_only_custody_supplied_key_and_bounded_claims():
    from integrations.mastermind_github_app.read_installation_identity import RsaAppJwtSigner, InstallationCredentialError
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer = RsaAppJwtSigner(key)
    value = signer.sign_app_jwt(app_id=1234, issued_at=1000, expires_at=1360)
    claims = jwt.decode(value, key.public_key(), algorithms=["RS256"],
                        options={"verify_exp": False, "verify_iat": False})
    assert claims == {"iss": "1234", "iat": 1000, "exp": 1360}
    with pytest.raises(InstallationCredentialError):
        signer.sign_app_jwt(app_id=1234, issued_at=1000, expires_at=5000)
    assert value not in repr(signer)


@pytest.mark.parametrize("field", ["app_id", "id", "target_id", "account_id", "repository_id"])
def test_remote_identity_numbers_must_be_integers_not_equal_floats(field):
    from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
    async def run():
        owner = Owner(); original = owner.request
        async def changed(**kwargs):
            response = await original(**kwargs)
            data = json.loads(response.body)
            if kwargs["method"] == "GET" and field != "repository_id":
                if field == "account_id": data["account"]["id"] = float(data["account"]["id"])
                else: data[field] = float(data[field])
            elif kwargs["method"] == "POST" and field == "repository_id":
                data["repositories"][0]["id"] = float(data["repositories"][0]["id"])
            return dataclasses.replace(response, body=json.dumps(data).encode())
        owner.request = changed
        with pytest.raises(InstallationCredentialError): await provider(owner).installation_token()
        if field != "repository_id": assert len(owner.calls) == 1
    asyncio.run(run())


def test_json_token_request_has_explicit_content_type():
    async def run():
        owner = Owner(); original = owner.request
        async def checked(**kwargs):
            if kwargs["method"] == "POST":
                assert kwargs["headers"].get("Content-Type") == "application/json"
            return await original(**kwargs)
        owner.request = checked
        assert await provider(owner).installation_token() == TOKEN
    asyncio.run(run())


def test_app_jwt_expiry_during_preflight_refuses_before_post():
    from integrations.mastermind_github_app.read_installation_identity import InstallationCredentialError
    async def run():
        owner = Owner(); original = owner.request; attempts = []
        async def delayed(**kwargs):
            attempts.append(kwargs["method"])
            if kwargs["method"] == "POST":
                raise AssertionError("expired app authorization must never reach POST")
            response = await original(**kwargs)
            owner.now += 301
            return response
        owner.request = delayed
        with pytest.raises(InstallationCredentialError) as caught:
            await provider(owner).installation_token()
        assert caught.value.issuance_possible is False
        assert attempts == ["GET"]
    asyncio.run(run())
