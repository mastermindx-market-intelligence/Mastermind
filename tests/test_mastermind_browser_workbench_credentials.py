"""Real signed tokens, private files, contention and bounded issuer simulation."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest

from integrations.business_mcp_auth import client_credentials as exchange
from integrations.mastermind_browser_plugin import workbench_credentials as credentials
from integrations.mastermind_browser_plugin.workbench_transport import _credential
from tests.test_mastermind_browser_workbench_transport import Host


@pytest.fixture
def setup(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    private = tmp_path / "credentials"
    private.mkdir(mode=0o700)
    secret = private / "client-secret"
    secret.write_text("synthetic-secret-for-tests\n")
    secret.chmod(0o600)
    host = Host("credential-fixture")
    route = replace(host.route, credential_file=private / "access.json")
    policy = json.loads(json.dumps(asdict(host.policy)))
    enrollment_file = private / "enrollment.json"
    document = {"schema": credentials.ENROLLMENT_SCHEMA, "credentials": [{
        "host_ref": route.host_ref, "client_id": host.client_id,
        "client_secret_file": str(secret), "policy": policy}]}
    enrollment_file.write_text(json.dumps(document))
    enrollment_file.chmod(0o600)
    monkeypatch.setattr(credentials.file_owner, "_user_root", lambda: tmp_path)
    rows = credentials.parse_enrollment(document, routes=(route,), enrollment_file=enrollment_file)
    state = SimpleNamespace(now=host.now, clock=0.0, admitted=True, token=host.token, calls=[])
    async def acquire(**kwargs):
        assert kwargs["policy"] == host.policy and kwargs["client_id"] == host.client_id
        assert kwargs["client_secret"] == "synthetic-secret-for-tests"
        state.calls.append("POST")
        return state.token
    def publisher(selected_acquire=acquire):
        return credentials.WorkbenchCredentialPublisher(
            enrollments=rows, now=lambda: state.now, monotonic=lambda: state.clock,
            ensure_current=lambda: state.admitted, authenticator_factory=lambda row: host.auth,
            acquire=selected_acquire)
    def token(**changes):
        claims = {"iss": host.issuer, "sub": "broker", "aud": host.resource,
                  "iat": state.now - 1, "exp": state.now + 600,
                  "scope": "workbench.action", "client_id": host.client_id}
        claims.update(changes)
        claims = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(claims, host.key, algorithm="RS256", headers={"kid": "fixture"})
    return SimpleNamespace(host=host, route=route, rows=rows, secret=secret, document=document,
                           enrollment_file=enrollment_file, state=state, publisher=publisher, token=token)


def status(value):
    assert len(value) == 1
    assert set(value[0]) == {"host_ref", "status"}
    return value[0]["status"]


def test_publish_signed_expiry_reuse_and_independent_transport_rotation(setup):
    async def exercise():
        publisher = setup.publisher()
        assert status(await publisher.refresh()) == "PUBLISHED"
        first = json.loads(setup.route.credential_file.read_bytes())
        assert first["expires_at"] == setup.state.now + 600
        assert stat_mode(setup.route.credential_file) == 0o600
        lock = credentials._lock_path(setup.route.credential_file)
        lock_inode = lock.stat().st_ino
        first_inode = setup.route.credential_file.stat().st_ino
        assert status(await publisher.refresh()) == "REUSED"
        assert setup.state.calls == ["POST"]
        assert setup.route.credential_file.stat().st_ino == first_inode
        setup.state.now += 500
        setup.state.token = setup.token()
        assert status(await publisher.refresh()) == "PUBLISHED"
        assert _credential(setup.route, setup.state.now) == setup.state.token
        assert lock.stat().st_ino == lock_inode and setup.state.calls == ["POST", "POST"]
    asyncio.run(exercise())


def stat_mode(path):
    return path.stat().st_mode & 0o777


@pytest.mark.parametrize("change", [
    {"iss": "https://other-issuer.test"}, {"aud": "https://other-resource.test"},
    {"sub": "other-subject"}, {"client_id": "other-client"}, {"client_id": None},
    {"azp": "different-client"}, {"scope": "browser.control"}, {"exp": "near"},
])
def test_verified_principal_must_match_exact_route_and_have_remaining_lifetime(setup, change):
    if change.get("exp") == "near":
        change = {"exp": setup.state.now + 10}
    setup.state.token = setup.token(**change)
    async def exercise():
        assert status(await setup.publisher().refresh()) == "UNAVAILABLE"
        assert not setup.route.credential_file.exists()
        assert setup.state.calls == ["POST"]
    asyncio.run(exercise())


@pytest.mark.parametrize("field", ["host_ref", "client_id", "policy", "client_secret_file", "extra"])
def test_enrollment_cannot_override_route_or_overlap_outputs(setup, field):
    document = json.loads(json.dumps(setup.document))
    row = document["credentials"][0]
    if field == "host_ref":
        row[field] = "unknown"
    elif field == "client_id":
        row[field] = "other-client"
    elif field == "policy":
        row[field]["allowed_subject_digests"] = ["f" * 64]
    elif field == "client_secret_file":
        row[field] = str(setup.route.credential_file)
    else:
        row["mcp_url"] = "https://other-endpoint.test/mcp"
    with pytest.raises((ValueError, RuntimeError)):
        credentials.parse_enrollment(document, routes=(setup.route,), enrollment_file=setup.enrollment_file)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "public"])
def test_unsafe_secret_is_not_read_or_sent(setup, kind):
    original = setup.secret.with_name("original-secret")
    setup.secret.rename(original)
    if kind == "symlink":
        setup.secret.symlink_to(original)
    elif kind == "hardlink":
        os.link(original, setup.secret)
    elif kind == "fifo":
        os.mkfifo(setup.secret, 0o600)
    else:
        setup.secret.write_text("synthetic-secret-for-tests")
        setup.secret.chmod(0o644)
    async def exercise():
        assert status(await setup.publisher().refresh()) == "UNAVAILABLE"
        assert setup.state.calls == [] and not setup.route.credential_file.exists()
    asyncio.run(exercise())


def test_two_publishers_contend_on_original_inode_without_duplicate_issuance(setup):
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        async def paused(**kwargs):
            setup.state.calls.append("POST")
            entered.set()
            await release.wait()
            return setup.state.token
        first = asyncio.create_task(setup.publisher(paused).refresh())
        await entered.wait()
        try:
            assert status(await setup.publisher().refresh()) == "BUSY"
            assert setup.state.calls == ["POST"]
        finally:
            release.set()
        assert status(await first) == "PUBLISHED"
        assert status(await setup.publisher().refresh()) == "REUSED"
        assert setup.state.calls == ["POST"]
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["admission", "lock", "parent", "output"])
def test_change_during_issuance_prevents_publication(setup, change):
    async def acquire(**kwargs):
        if change == "admission":
            setup.state.admitted = False
        elif change == "lock":
            path = credentials._lock_path(setup.route.credential_file)
            path.rename(path.with_name("original-held-lock"))
            path.touch(mode=0o600)
        elif change == "parent":
            path = setup.route.credential_file.parent
            path.rename(path.with_name("original-parent"))
            path.mkdir(mode=0o700)
        else:
            setup.route.credential_file.write_text("external-original")
            setup.route.credential_file.chmod(0o600)
        return setup.state.token
    async def exercise():
        value = status(await setup.publisher(acquire).refresh())
        assert value == ("INACTIVE" if change == "admission" else "UNAVAILABLE")
        if change == "output":
            assert setup.route.credential_file.read_text() == "external-original"
        else:
            assert not setup.route.credential_file.exists()
    asyncio.run(exercise())


def test_cancelled_issuer_closes_before_lock_release_and_never_publishes(setup):
    async def exercise():
        entered, closed = asyncio.Event(), asyncio.Event()
        async def paused(**kwargs):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
        pending = asyncio.create_task(setup.publisher(paused).refresh())
        await entered.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert closed.is_set() and not setup.route.credential_file.exists()
        assert status(await setup.publisher().refresh()) == "PUBLISHED"
    asyncio.run(exercise())


def test_failed_refresh_preserves_live_original_and_applies_bounded_backoff(setup):
    async def exercise():
        assert status(await setup.publisher().refresh()) == "PUBLISHED"
        original = setup.route.credential_file.read_bytes()
        setup.state.now += 500
        async def unavailable(**kwargs):
            setup.state.calls.append("failed POST")
            raise RuntimeError("synthetic provider detail must not appear in result")
        publisher = setup.publisher(unavailable)
        assert status(await publisher.refresh()) == "UNAVAILABLE"
        assert setup.route.credential_file.read_bytes() == original
        assert status(await publisher.refresh()) == "DEFERRED"
        assert setup.state.calls == ["POST", "failed POST"]
        setup.state.clock += 10
        assert status(await publisher.refresh()) == "UNAVAILABLE"
    asyncio.run(exercise())


@pytest.mark.parametrize("kind", ["valid", "redirect", "oversize", "duplicate", "extra_token", "encoding", "stall"])
def test_bounded_client_credentials_http_exchange(setup, monkeypatch, kind):
    requests, closed = [], []
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if kind == "stall":
                await asyncio.Event().wait()
            if kind == "duplicate":
                yield b'{"access_token":"one","access_token":"two"}'
            elif kind == "oversize":
                yield b"x" * (exchange.MAX_RESPONSE_BYTES + 1)
            else:
                document = {"access_token": setup.state.token, "token_type": "Bearer", "expires_in": 999999}
                if kind == "extra_token":
                    document["refresh_token"] = "must-not-store"
                yield json.dumps(document).encode()
        async def aclose(self):
            closed.append(True)
    async def respond(request):
        requests.append(request)
        assert str(request.url) == setup.host.issuer + "/oauth/token"
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body == {"grant_type": "client_credentials", "client_id": setup.host.client_id,
                        "client_secret": "synthetic-secret-for-tests", "audience": setup.host.resource,
                        "scope": "workbench.action"}
        headers = {"content-type": "application/json"}
        if kind == "redirect":
            headers["location"] = "https://unapproved.test/oauth/token"
        if kind == "encoding":
            headers["content-encoding"] = "gzip"
        return httpx.Response(302 if kind == "redirect" else 200, headers=headers, stream=Stream())
    monkeypatch.setattr(exchange, "TIMEOUT_SECONDS", .1)
    async def exercise():
        async def acquire(**kwargs):
            return await exchange.acquire_client_credentials(**kwargs, transport_factory=lambda: httpx.MockTransport(respond))
        result = await setup.publisher(acquire).refresh()
        assert status(result) == ("PUBLISHED" if kind == "valid" else "UNAVAILABLE")
        assert len(requests) == 1 and closed == [True]
        if kind == "valid":
            # Provider response lifetime cannot extend the signed JWT expiry.
            assert json.loads(setup.route.credential_file.read_bytes())["expires_at"] == setup.state.now + 600
        else:
            assert not setup.route.credential_file.exists()
    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["before_replace", "after_replace"])
def test_fsync_failure_distinguishes_unchanged_from_uncertain_publication(setup, monkeypatch, phase):
    import stat
    actual = credentials.os.fsync
    async def exercise():
        publisher = setup.publisher()
        assert status(await publisher.refresh()) == "PUBLISHED"
        original = setup.route.credential_file.read_bytes()
        setup.state.now += 500
        setup.state.token = setup.token()
        def fsync(descriptor):
            mode = os.fstat(descriptor).st_mode
            if phase == "before_replace" and stat.S_ISREG(mode):
                raise OSError("synthetic file barrier refusal")
            if phase == "after_replace" and stat.S_ISDIR(mode) and setup.route.credential_file.read_bytes() != original:
                raise OSError("synthetic directory barrier uncertainty")
            actual(descriptor)
        monkeypatch.setattr(credentials.os, "fsync", fsync)
        assert status(await publisher.refresh()) == ("UNAVAILABLE" if phase == "before_replace" else "UNCERTAIN")
        current = setup.route.credential_file.read_bytes()
        assert (current == original) == (phase == "before_replace")
        assert not list(setup.route.credential_file.parent.glob(".*.tmp"))
        monkeypatch.setattr(credentials.os, "fsync", actual)
        if phase == "after_replace":
            setup.state.clock += 10
            assert status(await publisher.refresh()) == "REUSED"
            assert setup.state.calls == ["POST", "POST"]
    asyncio.run(exercise())


def test_constructor_rejects_directly_constructed_output_collision(setup):
    other_route = replace(setup.route, host_ref="another-host", mcp_url="https://credential-fixture.test/other")
    other = replace(setup.rows[0], route=other_route)
    with pytest.raises(credentials.CredentialError):
        credentials.WorkbenchCredentialPublisher(
            enrollments=(setup.rows[0], other), now=lambda: setup.state.now,
            monotonic=lambda: 0, ensure_current=lambda: True)


def test_pass_timeout_preserves_configured_failure_backoff(setup, monkeypatch):
    policy = replace(setup.host.policy, fetch_failure_backoff_seconds=300)
    row = replace(setup.rows[0], policy=policy)
    calls = []
    async def stalled(**kwargs):
        calls.append("POST")
        await asyncio.Event().wait()
    monkeypatch.setattr(credentials, "PASS_TIMEOUT_SECONDS", .03)
    async def exercise():
        publisher = credentials.WorkbenchCredentialPublisher(
            enrollments=(row,), now=lambda: setup.state.now, monotonic=lambda: setup.state.clock,
            ensure_current=lambda: True, authenticator_factory=lambda row: setup.host.auth, acquire=stalled)
        assert status(await publisher.refresh()) == "UNAVAILABLE"
        setup.state.clock = 299
        assert status(await publisher.refresh()) == "DEFERRED"
        assert calls == ["POST"]
        setup.state.clock = 300
        assert status(await publisher.refresh()) == "UNAVAILABLE"
        assert calls == ["POST", "POST"]
    asyncio.run(exercise())


def test_client_identity_factor_preserves_qualified_long_issuer():
    import hashlib
    from integrations.business_mcp_auth.claims import _client_ref, client_ref_digest
    issuer = "https://identity.example/" + "a" * 1500
    expected = hashlib.sha256((issuer + "\nclient\n" + "client-id").encode()).hexdigest()
    assert _client_ref({"client_id": "client-id"}, issuer) == expected
    assert client_ref_digest(issuer=issuer, client_id="client-id") == expected


@pytest.mark.parametrize("descriptor_kind", ["parent", "lock"])
def test_descriptor_cleanup_after_publication_retains_uncertainty(setup, monkeypatch, descriptor_kind):
    import stat
    actual = credentials.os.close
    failed = []
    def close(descriptor):
        info = os.fstat(descriptor)
        selected = stat.S_ISDIR(info.st_mode) if descriptor_kind == "parent" else (
            stat.S_ISREG(info.st_mode) and info.st_size == 0)
        actual(descriptor)
        if selected and setup.route.credential_file.exists() and not failed:
            failed.append(True)
            raise OSError("synthetic post-publication descriptor-close uncertainty")
    monkeypatch.setattr(credentials.os, "close", close)
    async def exercise():
        assert status(await setup.publisher().refresh()) == "UNCERTAIN"
        assert failed == [True]
        assert _credential(setup.route, setup.state.now) == setup.state.token
    asyncio.run(exercise())


def test_successful_rename_does_not_attempt_temporary_unlink(setup, monkeypatch):
    actual = credentials.os.unlink
    def unlink(path, *args, **kwargs):
        if str(path).endswith(".tmp"):
            pytest.fail("successfully renamed temporary file must not be unlinked")
        return actual(path, *args, **kwargs)
    monkeypatch.setattr(credentials.os, "unlink", unlink)
    async def exercise():
        assert status(await setup.publisher().refresh()) == "PUBLISHED"
    asyncio.run(exercise())
