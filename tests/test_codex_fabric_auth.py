from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pytest

from integrations.business_mcp_auth.contracts import subject_digest
from ops.codex_fabric.executive_mcp_auth import (
    CredentialBundle,
    ExecutiveAuthError,
    headers_for_codex,
    load_installed_policy,
    validate_access_token,
)

ISSUER = "https://issuer.example.com/"
RESOURCE = "https://resource.example.com/executive"
SUBJECT = "auth0|chairman"
SUBJECT_DIGEST = subject_digest(issuer=ISSUER, subject=SUBJECT)
SCOPES = ("mastermind.executive.intent.submit", "mastermind.executive.read")


def _policy_document(*, resource: str = RESOURCE, submit_resource: str | None = None) -> dict:
    common = {
        "issuer": ISSUER,
        "resource": resource,
        "allowed_subject_digests": [SUBJECT_DIGEST],
    }
    return {
        "policies": {
            "read": {**common, "required_scopes": ["mastermind.executive.read"]},
            "submit": {
                **common,
                "resource": submit_resource if submit_resource is not None else resource,
                "required_scopes": list(SCOPES),
            },
        }
    }


def _write_policy(tmp_path: Path, **kwargs) -> Path:
    path = tmp_path / "executive-mcp.json"
    path.write_text(json.dumps(_policy_document(**kwargs)), encoding="utf-8")
    path.chmod(0o644)
    return path


def _segment(value: dict) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _token(*, exp: int = 2_000_000_000, audience=RESOURCE, scope: str | None = None,
           subject: str = SUBJECT, issuer: str = ISSUER) -> str:
    header = _segment({"alg": "RS256", "typ": "JWT"})
    payload = _segment({
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "scope": scope if scope is not None else " ".join((*SCOPES, "offline_access")),
        "exp": exp,
        "iat": 1_900_000_000,
    })
    return f"{header}.{payload}.signature"


def _bundle(policy, *, access_token: str | None = None, refresh_token: str = "refresh-current"):
    token = access_token if access_token is not None else _token()
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    expires_at = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))["exp"]
    return CredentialBundle(
        client_id="client-public-123",
        access_token=token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        policy_digest=policy.policy_digest,
    )


class MemoryStore:
    def __init__(self, bundle):
        self.bundle = bundle
        self.saved = []

    def load(self):
        return self.bundle

    def save(self, bundle):
        self.bundle = bundle
        self.saved.append(bundle)


def test_installed_policy_joins_read_and_submit_without_widening(tmp_path: Path):
    path = _write_policy(tmp_path)
    policy = load_installed_policy(path, expected_uid=os.getuid())

    assert policy.issuer == ISSUER
    assert policy.resource == RESOURCE
    assert policy.required_scopes == SCOPES
    assert policy.allowed_subject_digests == (SUBJECT_DIGEST,)
    assert len(policy.policy_digest) == 64


def test_installed_policy_refuses_read_submit_resource_disagreement(tmp_path: Path):
    path = _write_policy(tmp_path, submit_resource="https://other.example.com/")

    with pytest.raises(ExecutiveAuthError, match="policy"):
        load_installed_policy(path, expected_uid=os.getuid())


@pytest.mark.parametrize(
    "mutation",
    [
        {"audience": "https://wrong.example.com/"},
        {"scope": "mastermind.executive.read offline_access"},
        {"subject": "auth0|other"},
        {"issuer": "https://other-issuer.example.com/"},
        {"exp": 1_900_000_001},
    ],
)
def test_access_token_safety_check_refuses_policy_or_expiry_drift(tmp_path: Path, mutation: dict):
    policy = load_installed_policy(_write_policy(tmp_path), expected_uid=os.getuid())
    token = _token(**mutation)

    with pytest.raises(ExecutiveAuthError):
        validate_access_token(token, policy, now_epoch=1_900_000_001)


def test_headers_use_current_keychain_token_without_refresh(tmp_path: Path):
    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    store = MemoryStore(_bundle(policy))
    refresh_calls = []

    headers = headers_for_codex(
        policy_path=policy_path,
        store=store,
        now_epoch=1_900_000_100,
        expected_uid=os.getuid(),
        refresh_fn=lambda *_args, **_kwargs: refresh_calls.append(True),
    )

    assert headers == {"Authorization": f"Bearer {store.bundle.access_token}"}
    assert refresh_calls == []
    assert store.saved == []


def test_headers_refresh_once_near_expiry_and_persist_rotation(tmp_path: Path):
    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    old = _bundle(policy, access_token=_token(exp=1_900_000_150))
    store = MemoryStore(old)
    refreshed = _token(exp=1_900_100_000)
    calls = []

    def refresh(policy_arg, bundle_arg):
        calls.append((policy_arg, bundle_arg))
        return {"access_token": refreshed, "refresh_token": "refresh-rotated"}

    headers = headers_for_codex(
        policy_path=policy_path, store=store, now_epoch=1_900_000_100,
        expected_uid=os.getuid(), refresh_fn=refresh,
    )

    assert headers == {"Authorization": f"Bearer {refreshed}"}
    assert len(calls) == 1
    assert [bundle.refresh_state for bundle in store.saved] == ["pending", "ready"]
    assert store.bundle.refresh_token == "refresh-rotated"
    assert store.bundle.access_token == refreshed
    assert store.bundle.expires_at == 1_900_100_000


def test_refresh_with_invalid_replacement_quarantines_same_credential(tmp_path: Path):
    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    original = _bundle(policy, access_token=_token(exp=1_900_000_150))
    store = MemoryStore(original)

    with pytest.raises(ExecutiveAuthError):
        headers_for_codex(
            policy_path=policy_path, store=store, now_epoch=1_900_000_100,
            expected_uid=os.getuid(),
            refresh_fn=lambda *_args: {"access_token": _token(audience="https://wrong.example.com/")},
        )

    assert store.bundle == dataclasses.replace(original, refresh_state="pending")
    assert [bundle.refresh_state for bundle in store.saved] == ["pending"]


def test_policy_digest_movement_refuses_before_refresh(tmp_path: Path):
    path = _write_policy(tmp_path)
    policy = load_installed_policy(path, expected_uid=os.getuid())
    store = MemoryStore(_bundle(policy, access_token=_token(exp=1_900_000_150)))
    moved = _policy_document()
    moved["policies"]["submit"]["allowed_subject_digests"] = ["f" * 64]
    moved["policies"]["read"]["allowed_subject_digests"] = ["f" * 64]
    path.write_text(json.dumps(moved), encoding="utf-8")
    calls = []

    with pytest.raises(ExecutiveAuthError, match="policy"):
        headers_for_codex(
            policy_path=path, store=store, now_epoch=1_900_000_100,
            expected_uid=os.getuid(), refresh_fn=lambda *_args: calls.append(True),
        )
    assert calls == []


def test_keychain_store_uses_fixed_coordinates_and_round_trips_bundle(tmp_path: Path):
    import ops.codex_fabric.executive_mcp_auth as auth

    policy = load_installed_policy(_write_policy(tmp_path), expected_uid=os.getuid())
    bundle = _bundle(policy)

    class FakeKeychain:
        def __init__(self):
            self.value = None
            self.calls = []

        def read(self, service: bytes, account: bytes):
            self.calls.append(("read", service, account))
            return self.value

        def upsert(self, service: bytes, account: bytes, value: bytes):
            self.calls.append(("upsert", service, account))
            self.value = value

    api = FakeKeychain()
    store = auth.KeychainCredentialStore(api=api)
    store.save(bundle)
    assert store.load() == bundle
    assert {call[1:] for call in api.calls if call[0] == "read"} == {
        (auth.KEYCHAIN_SERVICE, auth.KEYCHAIN_ACCOUNT)
    }
    assert {call[1:3] for call in api.calls if call[0] == "upsert"} == {
        (auth.KEYCHAIN_SERVICE, auth.KEYCHAIN_ACCOUNT)
    }
    assert b"refresh-current" in api.value


def test_keychain_store_refuses_malformed_or_unknown_credential_document():
    import ops.codex_fabric.executive_mcp_auth as auth

    class FakeKeychain:
        def __init__(self, value):
            self.value = value
        def read(self, _service, _account):
            return self.value
        def upsert(self, *_args):
            raise AssertionError("unexpected write")

    for value in (
        None,
        b"not-json",
        json.dumps({"schema": "wrong"}).encode(),
        json.dumps({
            "schema": auth.CREDENTIAL_SCHEMA,
            "client_id": "client",
            "access_token": "a.b.c",
            "refresh_token": "refresh",
            "expires_at": 2_000_000_000,
            "policy_digest": "0" * 64,
            "extra": "refuse",
        }).encode(),
    ):
        with pytest.raises(ExecutiveAuthError, match="credential"):
            auth.KeychainCredentialStore(api=FakeKeychain(value)).load()


def test_default_refresh_posts_only_to_exact_issuer_token_endpoint(tmp_path: Path):
    import ops.codex_fabric.executive_mcp_auth as auth

    policy = load_installed_policy(_write_policy(tmp_path), expected_uid=os.getuid())
    bundle = _bundle(policy)
    observed = {}

    def fake_post(url: str, fields: dict[str, str]):
        observed["url"] = url
        observed["fields"] = fields
        return {
            "access_token": _token(exp=2_000_100_000),
            "refresh_token": "rotated",
            "token_type": "Bearer",
        }

    result = auth.refresh_access_token(policy, bundle, post_form=fake_post)
    assert observed == {
        "url": "https://issuer.example.com/oauth/token",
        "fields": {
            "grant_type": "refresh_token",
            "client_id": "client-public-123",
            "refresh_token": "refresh-current",
        },
    }
    assert result["refresh_token"] == "rotated"


def test_header_helper_entrypoint_emits_only_json_header_on_success(tmp_path: Path, capsys):
    import ops.codex_fabric.executive_mcp_auth as auth

    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    store = MemoryStore(_bundle(policy))

    code = auth.header_helper_main(
        policy_path=policy_path,
        expected_uid=os.getuid(),
        store=store,
        now_fn=lambda: 1_900_000_100,
        refresh_fn=lambda *_args: pytest.fail("refresh should not run"),
    )
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out) == {"Authorization": f"Bearer {store.bundle.access_token}"}
    assert captured.err == ""


def test_header_helper_entrypoint_failure_is_opaque_and_never_echoes_secret(tmp_path: Path, capsys):
    import ops.codex_fabric.executive_mcp_auth as auth

    policy_path = _write_policy(tmp_path)
    secret = "refresh-SHOULD-NOT-LEAK"

    class BadStore:
        def load(self):
            raise RuntimeError(secret)
        def save(self, _bundle):
            raise AssertionError("unexpected write")

    code = auth.header_helper_main(
        policy_path=policy_path,
        expected_uid=os.getuid(),
        store=BadStore(),
        now_fn=lambda: 1_900_000_100,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == "REFUSED: Executive MCP authorization unavailable.\n"
    assert secret not in captured.err


def test_default_refresh_refuses_non_bearer_token_type(tmp_path: Path):
    import ops.codex_fabric.executive_mcp_auth as auth

    policy = load_installed_policy(_write_policy(tmp_path), expected_uid=os.getuid())
    bundle = _bundle(policy)

    with pytest.raises(ExecutiveAuthError, match="refresh failed"):
        auth.refresh_access_token(
            policy,
            bundle,
            post_form=lambda _url, _fields: {
                "access_token": _token(exp=2_000_100_000),
                "refresh_token": "rotated",
                "token_type": "MAC",
            },
        )


def test_refresh_marks_same_keychain_bundle_pending_before_network_and_restores_ready(tmp_path: Path):
    from contextlib import nullcontext
    import ops.codex_fabric.executive_mcp_auth as auth

    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    old = _bundle(policy, access_token=_token(exp=1_900_000_150))
    store = MemoryStore(old)
    replacement = _token(exp=1_900_100_000)
    observed_states = []

    def refresh(_policy, _bundle):
        observed_states.append(store.bundle.refresh_state)
        return {
            "access_token": replacement,
            "refresh_token": "refresh-rotated",
        }

    headers = headers_for_codex(
        policy_path=policy_path,
        store=store,
        now_epoch=1_900_000_100,
        expected_uid=os.getuid(),
        refresh_fn=refresh,
        refresh_lock=lambda: nullcontext(),
    )

    assert observed_states == ["pending"]
    assert [bundle.refresh_state for bundle in store.saved] == ["pending", "ready"]
    assert store.bundle.refresh_state == "ready"
    assert headers == {"Authorization": f"Bearer {replacement}"}


def test_refresh_failure_leaves_pending_and_next_helper_refuses_without_second_effect(tmp_path: Path):
    from contextlib import nullcontext

    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    store = MemoryStore(_bundle(policy, access_token=_token(exp=1_900_000_150)))
    calls = []

    with pytest.raises(ExecutiveAuthError):
        headers_for_codex(
            policy_path=policy_path,
            store=store,
            now_epoch=1_900_000_100,
            expected_uid=os.getuid(),
            refresh_fn=lambda *_args: calls.append("effect") or (_ for _ in ()).throw(TimeoutError()),
            refresh_lock=lambda: nullcontext(),
        )
    assert calls == ["effect"]
    assert store.bundle.refresh_state == "pending"

    with pytest.raises(ExecutiveAuthError, match="refresh state"):
        headers_for_codex(
            policy_path=policy_path,
            store=store,
            now_epoch=1_900_000_101,
            expected_uid=os.getuid(),
            refresh_fn=lambda *_args: calls.append("duplicate"),
            refresh_lock=lambda: nullcontext(),
        )
    assert calls == ["effect"]


def test_waiting_helper_reloads_bundle_after_lock_and_uses_concurrent_winner(tmp_path: Path):
    from contextlib import contextmanager

    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    old = _bundle(policy, access_token=_token(exp=1_900_000_150))
    winner = _bundle(
        policy,
        access_token=_token(exp=1_900_100_000),
        refresh_token="winner-refresh",
    )
    store = MemoryStore(old)
    calls = []

    @contextmanager
    def lock_with_winner():
        store.bundle = winner
        yield

    headers = headers_for_codex(
        policy_path=policy_path,
        store=store,
        now_epoch=1_900_000_100,
        expected_uid=os.getuid(),
        refresh_fn=lambda *_args: calls.append("duplicate"),
        refresh_lock=lock_with_winner,
    )
    assert calls == []
    assert headers == {"Authorization": f"Bearer {winner.access_token}"}


def test_refresh_lock_uses_fixed_private_metadata(tmp_path: Path):
    import stat as stat_module
    import ops.codex_fabric.executive_mcp_auth as auth

    root = tmp_path / "cache"
    with auth._exclusive_refresh_lock(lock_root=root, timeout_seconds=0.2):
        directory = root.lstat()
        lock_file = (root / "refresh.lock").lstat()
        assert stat_module.S_IMODE(directory.st_mode) == 0o700
        assert stat_module.S_IMODE(lock_file.st_mode) == 0o600
        assert directory.st_uid == os.geteuid()
        assert lock_file.st_uid == os.geteuid()
        assert stat_module.S_ISDIR(directory.st_mode)
        assert stat_module.S_ISREG(lock_file.st_mode)


def test_header_helper_deadline_refuses_blocked_keychain_without_header(tmp_path: Path, capsys):
    import time
    import ops.codex_fabric.executive_mcp_auth as auth

    policy_path = _write_policy(tmp_path)

    class BlockingStore:
        def load(self):
            time.sleep(2)
            raise AssertionError("deadline should return before this completes")
        def save(self, _bundle):
            raise AssertionError("unexpected write")

    started = time.monotonic()
    code = auth.header_helper_main(
        policy_path=policy_path,
        expected_uid=os.getuid(),
        store=BlockingStore(),
        deadline_seconds=0.05,
    )
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    assert code == 2
    assert elapsed < 0.5
    assert captured.out == ""
    assert captured.err == "REFUSED: Executive MCP authorization unavailable.\n"


def test_header_helper_deadline_still_emits_success_before_bound(tmp_path: Path, capsys):
    import ops.codex_fabric.executive_mcp_auth as auth

    policy_path = _write_policy(tmp_path)
    policy = load_installed_policy(policy_path, expected_uid=os.getuid())
    store = MemoryStore(_bundle(policy))
    code = auth.header_helper_main(
        policy_path=policy_path,
        expected_uid=os.getuid(),
        store=store,
        now_fn=lambda: 1_900_000_100,
        deadline_seconds=0.5,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out) == {"Authorization": f"Bearer {store.bundle.access_token}"}
    assert captured.err == ""
