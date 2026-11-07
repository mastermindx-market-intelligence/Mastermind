"""REAL durable-audit composition behind the sealed OS publication entry.

``tests/test_os_commission_auth_entry.py`` proves the sealed helper's wire,
digest and policy behavior against an in-memory audit double;
``tests/test_os_publication_auth.py`` proves the gate composition against that
same double; ``tests/test_business_mcp_auth_audit.py`` proves
``DurableAuthAuditSink`` in isolation.  No module yet runs the actual
``authenticate_document`` composition on a REAL durable sink acquisition.
This module owns exactly that gap:

* a real mode-0700, current-eUID-owned audit directory acquired through the
  production ``DurableAuthAuditSink.open`` descriptor pattern (never a fake
  sink, never a faked effective UID);
* retained, sanitized ``auth-audit.jsonl`` facts on real disk, proven by
  close/reopen continuity through a second real acquisition on the same
  persistent file and read back through the real sink reader;
* refused identity (missing scope, foreign resource, unlisted subject) and
  denied publication permission recorded as durable facts that can never
  become a positive identity projection;
* hostile audit topologies (writable directory, foreign symlink alias,
  occupied loose-mode ledger) refusing through the real sink before
  authentication can run at all.

Everything stays hermetic: the JWKS cache is the generated-key fake shared by
the sibling modules (the real ``_default_jwks_cache`` fetcher is never
constructed), the clock is fixed, and an autouse guard turns any socket
connect or address resolution into a test failure instead of a provider call.
No macOS ACL observation is patched: the sink's real ACL observer runs
unmodified on every platform this suite targets.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys

import pytest

from ops.executive_os.os_commission_auth_entry import authenticate_document

sys.path.insert(0, str(Path(__file__).parent))
try:
    import test_mastermind_executive_app_asgi as fixture
finally:
    sys.path.pop(0)

from integrations.business_mcp_auth.audit import (
    AuditSinkPoisoned,
    DurableAuthAuditSink,
)
from integrations.business_mcp_auth.contracts import AUTH_AUDIT_SCHEMA
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.mastermind_executive_app.os_publication_auth import (
    PublicationAuthRefused,
    RESOURCE,
)
from integrations.mastermind_executive_app.os_transport import principal_scope

rsa_key = fixture.rsa_key

AUDIT_NAME = "auth-audit.jsonl"
# Fixed opaque claims minted by the shared fixture module; they must never
# surface in a stdout projection or a durable audit line.
_JTI = "opaque-jti"
_CLIENT_ID = "e1-test-client"


@pytest.fixture(autouse=True)
def _inert_effect_guards(monkeypatch: pytest.MonkeyPatch):
    """Turn any network/provider effect into a loud local test failure."""

    def refused(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network effect attempted during hermetic audit test")

    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket.socket, "connect_ex", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket, "getaddrinfo", refused)


def bearer(key, **claims) -> str:
    claims.setdefault("scope", f"{fixture.READ_SCOPE} {fixture.SUBMIT_SCOPE}")
    claims.setdefault("aud", RESOURCE)
    return fixture._token(key, **claims)


def publication_policy():
    return fixture._submit_policy(
        resource=RESOURCE,
        resource_metadata_url=RESOURCE + "/.well-known/oauth-protected-resource",
    )


def publication_config(key, *, grants=None):
    """The exact sealed-helper configuration shape for one generated key."""

    policy = publication_policy()
    authenticator = JwtAuthenticator(
        policy=policy, jwks_cache=fixture._FakeJwksCache(key)
    )
    principal = asyncio.run(
        authenticator.verify_token(bearer(key), now=fixture.NOW)
    )
    namespace = principal_scope(principal)
    config = {
        "policy": json.loads(json.dumps(dataclasses.asdict(policy))),
        "grants": (
            [{"principal_scope": namespace}] if grants is None else grants
        ),
    }
    return config, namespace


def make_audit_directory(directory: Path) -> Path:
    """One real eUID-owned mode-0700 audit directory."""

    directory.mkdir()
    directory.chmod(0o700)
    return directory


def open_real_sink(directory: Path):
    """Acquire the real durable sink exactly as the sealed main() does."""

    descriptor = os.open(
        directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        return DurableAuthAuditSink.open(
            descriptor, policy_id=publication_policy().policy_id
        )
    finally:
        os.close(descriptor)


def run_commission(key, payload, *, sink, grants=None):
    """Run the actual helper against one real acquired sink."""

    config, _namespace = publication_config(key, grants=grants)
    return asyncio.run(
        authenticate_document(
            json.dumps(payload).encode("utf-8"),
            config,
            audit_sink=sink,
            clock=lambda: fixture.NOW,
            jwks_cache=fixture._FakeJwksCache(key),
        )
    )


def compose_through_real_sink(directory: Path, key, payload, *, grants=None):
    """The full production shape: acquire the real sink, then authenticate."""

    sink = open_real_sink(directory)
    try:
        return run_commission(key, payload, sink=sink, grants=grants)
    finally:
        sink.close()


def ledger(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (directory / AUDIT_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def audit_line(policy, *, accepted: bool, code: str = "accepted") -> dict:
    return {
        "accepted": accepted,
        "code": code,
        "policy_id": policy.policy_id,
        "schema": AUTH_AUDIT_SCHEMA,
    }


def secret_atoms(key, *, brief: str | None = None) -> list[str]:
    token_text = bearer(key)
    atoms = [
        token_text,
        *token_text.split("."),
        fixture.SUBJECT,
        _JTI,
        _CLIENT_ID,
        fixture.ISSUER,
        RESOURCE,
    ]
    if brief is not None:
        atoms.append(brief)
    return atoms


def test_accepted_authentication_projects_real_scope_and_retains_one_sanitized_fact(
    rsa_key, tmp_path: Path
):
    directory = make_audit_directory(tmp_path / "audit")
    config, namespace = publication_config(rsa_key)
    policy = publication_policy()
    sink = open_real_sink(directory)
    cache = fixture._FakeJwksCache(rsa_key)
    try:
        result = asyncio.run(
            authenticate_document(
                json.dumps({"bearer": bearer(rsa_key)}).encode("utf-8"),
                config,
                audit_sink=sink,
                clock=lambda: fixture.NOW,
                jwks_cache=cache,
            )
        )
    finally:
        sink.close()

    assert set(result) == {"ok", "identity"}
    identity = result["identity"]
    assert set(identity) == {"principal_scope", "policy_digest", "expires_at"}
    assert identity["principal_scope"] == namespace
    assert re.fullmatch(r"[0-9a-f]{64}", identity["policy_digest"])
    assert identity["expires_at"] == fixture.NOW + 300
    # Both composition passes resolved the key through the hermetic cache only.
    assert cache.calls == [fixture.KID, fixture.KID]

    expected = audit_line(policy, accepted=True)
    assert ledger(directory) == [expected]
    target = directory / AUDIT_NAME
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    projection = json.dumps(result, sort_keys=True)
    retained = target.read_bytes()
    for secret in secret_atoms(rsa_key):
        assert secret not in projection
        assert secret.encode("utf-8") not in retained

    # Flush/close then reopen on the SAME persistent ledger: the second real
    # acquisition continues the retained file, appends through the real sink
    # again, and the retained lines still decode through the exact encoders.
    reopened = open_real_sink(directory)
    try:
        second = run_commission(
            rsa_key, {"bearer": bearer(rsa_key)}, sink=reopened
        )
        assert second["identity"] == identity
        assert reopened.read_channel_admissions("b" * 64) == ()
    finally:
        reopened.close()
    assert ledger(directory) == [expected, expected]


def test_validated_brief_never_reaches_output_or_durable_audit(
    rsa_key, tmp_path: Path
):
    directory = make_audit_directory(tmp_path / "audit")
    brief = "Sealed audit brief with 🧪 and café text."
    arguments = {
        "operation_key": "mmos-launch-" + "b" * 40,
        "objective": brief,
        "department": "executive-infrastructure",
        "priority": 5,
        "execution_profile": "research_only",
        "workstream": "WS:NOIR",
    }
    sink = open_real_sink(directory)
    try:
        result = run_commission(
            rsa_key,
            {
                "bearer": bearer(rsa_key),
                "request_body": json.dumps({"arguments": arguments}),
            },
            sink=sink,
        )
    finally:
        sink.close()

    assert set(result) == {"ok", "identity", "arguments_digest"}
    assert ledger(directory) == [audit_line(publication_policy(), accepted=True)]
    retained = (directory / AUDIT_NAME).read_bytes()
    for secret in secret_atoms(rsa_key, brief=brief):
        assert secret not in json.dumps(result, sort_keys=True)
        assert secret.encode("utf-8") not in retained


@pytest.mark.parametrize(
    "claims,code",
    [
        ({"scope": fixture.READ_SCOPE}, "scope_refused"),
        ({"aud": "https://foreign-authority.example.test/mcp"}, "resource_refused"),
        ({"sub": "unlisted-opaque-subject"}, "subject_refused"),
    ],
)
def test_refused_identity_is_a_durable_refused_fact_and_never_a_positive_projection(
    rsa_key, tmp_path: Path, claims, code
):
    directory = make_audit_directory(tmp_path / "audit")
    policy = publication_policy()
    sink = open_real_sink(directory)
    try:
        with pytest.raises(
            PublicationAuthRefused, match="^publication authentication refused$"
        ):
            run_commission(
                rsa_key, {"bearer": bearer(rsa_key, **claims)}, sink=sink
            )
        refused_fact = audit_line(policy, accepted=False, code=code)
        assert ledger(directory) == [refused_fact]

        # The real sink survives the refusal and keeps composing: the very
        # next authenticated attempt appends after the retained refused fact.
        accepted = run_commission(rsa_key, {"bearer": bearer(rsa_key)}, sink=sink)
        assert set(accepted) == {"ok", "identity"}
        assert ledger(directory) == [
            refused_fact,
            audit_line(policy, accepted=True),
        ]
    finally:
        sink.close()

    retained = (directory / AUDIT_NAME).read_bytes()
    for secret in secret_atoms(rsa_key):
        assert secret.encode("utf-8") not in retained


def test_authenticated_identity_without_publication_grant_is_audited_but_refused(
    rsa_key, tmp_path: Path
):
    directory = make_audit_directory(tmp_path / "audit")
    policy = publication_policy()
    sink = open_real_sink(directory)
    try:
        with pytest.raises(
            PublicationAuthRefused, match="^publication authentication refused$"
        ):
            run_commission(
                rsa_key,
                {"bearer": bearer(rsa_key)},
                sink=sink,
                grants=[{"principal_scope": "0" * 64}],
            )
        # Identity was fully authenticated and durably audited, yet no
        # positive publication projection escaped and no grant fact exists.
        assert ledger(directory) == [audit_line(policy, accepted=True)]
    finally:
        sink.close()


def test_writable_audit_directory_refuses_before_authentication(
    rsa_key, tmp_path: Path
):
    directory = tmp_path / "audit"
    directory.mkdir()
    directory.chmod(0o722)
    with pytest.raises(AuditSinkPoisoned, match="audit directory security refused"):
        compose_through_real_sink(directory, rsa_key, {"bearer": bearer(rsa_key)})
    assert list(directory.iterdir()) == []


def test_foreign_symlink_ledger_refuses_and_never_writes_through(
    rsa_key, tmp_path: Path
):
    directory = make_audit_directory(tmp_path / "audit")
    foreign = tmp_path / "outside.jsonl"
    foreign.write_bytes(b"")
    (directory / AUDIT_NAME).symlink_to(foreign)
    with pytest.raises(AuditSinkPoisoned, match="durable audit acquisition refused"):
        compose_through_real_sink(
            directory, rsa_key, {"bearer": bearer(rsa_key)}
        )
    assert foreign.read_bytes() == b""
    assert (directory / AUDIT_NAME).is_symlink()
    assert list(directory.iterdir()) == [directory / AUDIT_NAME]


def test_occupied_loose_mode_ledger_refuses_and_stays_byte_identical(
    rsa_key, tmp_path: Path
):
    directory = make_audit_directory(tmp_path / "audit")
    occupied = directory / AUDIT_NAME
    occupied.write_bytes(b'{"occupied":true}\n')
    occupied.chmod(0o644)
    with pytest.raises(AuditSinkPoisoned, match="audit file security refused"):
        compose_through_real_sink(
            directory, rsa_key, {"bearer": bearer(rsa_key)}
        )
    assert occupied.read_bytes() == b'{"occupied":true}\n'
    assert stat.S_IMODE(occupied.stat().st_mode) == 0o644
