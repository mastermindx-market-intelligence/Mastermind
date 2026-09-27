"""Existing provider restart counterexamples; synthetic credentials/HTTP only."""
from __future__ import annotations
import asyncio
import dataclasses
import pytest
from test_github_read_installation_identity import Owner, provider, TOKEN
from integrations.mastermind_github_app.read_installation_identity import (
    InstallationCredentialError, ReadInstallationTokenProvider,
)


def test_armed_provider_without_durable_owner_refuses_before_signing():
    owner = Owner()
    subject = ReadInstallationTokenProvider(resolve_binding=owner.current_binding,
        signer=owner, transport=owner, clock=lambda: owner.now, production_armed=True)
    with pytest.raises(InstallationCredentialError):
        asyncio.run(subject.installation_token())
    assert owner.signs == 0 and owner.calls == []


@pytest.mark.parametrize("changed_generation", [False, True])
def test_new_provider_cannot_repeat_original_uncertain_issuance(changed_generation):
    async def run():
        owner = Owner()
        owner.variant = "lost_post"
        with pytest.raises(InstallationCredentialError):
            await provider(owner).installation_token()
        assert sum(c[0] == "POST" for c in owner.calls) == 1
        if changed_generation:
            owner.binding = dataclasses.replace(owner.binding, generation="credential:replacement")
        before = (owner.signs, len(owner.calls))
        with pytest.raises(InstallationCredentialError):
            await provider(owner).installation_token()
        assert sum(c[0] == "POST" for c in owner.calls) == 1
        assert (owner.signs, len(owner.calls)) == before
    asyncio.run(run())


def test_atomic_claim_is_in_existing_event_store_and_secret_free(tmp_path):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    before = fence._store.path.stat()
    claim = fence.claim(owner.binding)
    recreated = durable_fence(owner, tmp_path)
    with pytest.raises(InstallationCredentialError):
        recreated.claim(owner.binding)
    with fence._store.read() as connection:
        rows = connection.execute("SELECT event_type,payload_json FROM events WHERE aggregate_type='github_read_credential'").fetchall()
    assert len(rows) == 1 and rows[0][0] == "GITHUB_READ_CREDENTIAL_ATTEMPT"
    assert TOKEN not in rows[0][1] and "Bearer" not in rows[0][1]
    assert "private_key" not in rows[0][1] and "credential:review-one" not in rows[0][1]
    assert before.st_ino == fence._store.path.stat().st_ino
    assert claim.slot_command.startswith("github-read-issuance:")


@pytest.mark.parametrize("variant", ["lost_post", "cancel_post", "write_token", "move_post"])
def test_uncertain_post_is_held_after_reopening_exact_runtime(tmp_path, variant):
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        owner._issuance_fence = durable_fence(owner, tmp_path)
        owner.variant = variant
        with pytest.raises((InstallationCredentialError, asyncio.CancelledError)):
            await provider(owner).installation_token()
        before = len(owner.calls)
        owner._issuance_fence = durable_fence(owner, tmp_path)
        with pytest.raises(InstallationCredentialError) as caught:
            await provider(owner).installation_token()
        assert caught.value.issuance_possible is True
        assert len(owner.calls) == before
    asyncio.run(run())


def test_qualified_cache_uses_same_durable_result_but_replacement_cannot_reissue(tmp_path):
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        owner._issuance_fence = durable_fence(owner, tmp_path)
        subject = provider(owner)
        assert await subject.installation_token() == TOKEN
        assert await subject.installation_token() == TOKEN
        assert len(owner.calls) == 2
        with owner._issuance_fence._store.read() as connection:
            rows = connection.execute("SELECT event_type,payload_json FROM events WHERE aggregate_type='github_read_credential' ORDER BY sequence").fetchall()
        assert [r[0] for r in rows] == ["GITHUB_READ_CREDENTIAL_ATTEMPT", "GITHUB_READ_CREDENTIAL_QUALIFIED"]
        assert TOKEN not in str([tuple(r) for r in rows])
        with pytest.raises(InstallationCredentialError):
            await provider(owner).installation_token()
        assert len(owner.calls) == 2
    asyncio.run(run())


@pytest.mark.parametrize("change", ["missing", "foreign_runtime", "foreign_binding", "expired", "wrong_type"])
def test_bad_or_missing_runtime_admission_refuses_before_signer(tmp_path, change):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    original = fence._authorize
    def admission(binding):
        value = original(binding)
        if change == "missing": return None
        if change == "foreign_runtime": return dataclasses.replace(value, runtime_identity=(0, 1))
        if change == "foreign_binding": return dataclasses.replace(value, binding_fingerprint="f" * 64)
        if change == "expired": return dataclasses.replace(value, expires_at_ms=owner.now * 1000)
        return {"authorized": True}
    fence._authorize = admission
    owner._issuance_fence = fence
    with pytest.raises(InstallationCredentialError):
        asyncio.run(provider(owner).installation_token())
    assert owner.signs == 0 and owner.calls == []
    with fence._store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE aggregate_type='github_read_credential'").fetchone()[0] == 0


def test_credential_fence_never_bootstraps_or_uses_projection_store(tmp_path):
    from control_plane.executive_runtime import RuntimeStore
    from integrations.mastermind_github_app.read_issuance_runtime import RuntimeReadIssuanceFence
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    for store in (RuntimeStore(root=tmp_path), RuntimeStore(root=tmp_path, create=False)):
        with pytest.raises(InstallationCredentialError):
            RuntimeReadIssuanceFence(store=store, authorize=fence._authorize)


def test_runtime_admission_rechecked_inside_transaction_before_claim(tmp_path):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    original = fence._authorize
    calls = []
    def admission(binding):
        calls.append(1)
        value = original(binding)
        return value if len(calls) == 1 else dataclasses.replace(value, authority_digest="e" * 64)
    fence._authorize = admission
    with pytest.raises(InstallationCredentialError):
        fence.claim(owner.binding)
    with fence._store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE aggregate_type='github_read_credential'").fetchone()[0] == 0


def test_two_independent_providers_contend_for_one_durable_attempt(tmp_path):
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        owner._issuance_fence = durable_fence(owner, tmp_path)
        one, two = provider(owner), provider(owner)
        values = await asyncio.gather(one.installation_token(), two.installation_token(), return_exceptions=True)
        assert sum(v == TOKEN for v in values) == 1
        assert sum(isinstance(v, InstallationCredentialError) for v in values) == 1
        assert sum(c[0] == "POST" for c in owner.calls) == 1
    asyncio.run(run())


def test_narrower_admission_deadline_caps_cached_credential(tmp_path):
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        fence = durable_fence(owner, tmp_path)
        original = fence._authorize
        deadline = (owner.now + 120) * 1000
        fence._authorize = lambda binding: dataclasses.replace(original(binding), expires_at_ms=deadline)
        owner._issuance_fence = fence
        subject = provider(owner)
        assert await subject.installation_token() == TOKEN
        assert subject.evidence()["usable_until"] == deadline // 1000
        owner.now += 120
        with pytest.raises(InstallationCredentialError):
            await subject.installation_token()
        assert sum(c[0] == "POST" for c in owner.calls) == 1
    asyncio.run(run())


@pytest.mark.parametrize("change", ["expire", "move"])
def test_admission_is_fresh_immediately_before_post(tmp_path, change):
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        fence = durable_fence(owner, tmp_path)
        original_admit, original_claim, original_request = fence._authorize, fence.claim, owner.request
        deadline = (owner.now + 60) * 1000
        moved = [False]
        def admission(binding):
            return dataclasses.replace(original_admit(binding), expires_at_ms=deadline,
                authority_digest=("f" if moved[0] else "b") * 64)
        fence._authorize = admission
        def claim(binding):
            result = original_claim(binding)
            if change == "expire": owner.now += 61
            else: moved[0] = True
            return result
        fence.claim = claim
        posts = []
        async def request(**kwargs):
            if kwargs["method"] == "POST":
                posts.append(1)
                raise OSError("synthetic credential response loss")
            return await original_request(**kwargs)
        owner.request = request
        owner._issuance_fence = fence
        with pytest.raises(InstallationCredentialError):
            await provider(owner).installation_token()
        assert posts == [], "expired or changed issuance admission must stop before POST"
    asyncio.run(run())


@pytest.mark.parametrize("bad_id", [False, 1.5, 0, -1, 2**53, "1234"])
def test_durable_adapter_rejects_invalid_binding_before_event(tmp_path, bad_id):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    owner.binding = dataclasses.replace(owner.binding, app_id=bad_id)
    fence = durable_fence(owner, tmp_path)
    with pytest.raises(InstallationCredentialError):
        fence.claim(owner.binding)
    with fence._store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events WHERE aggregate_type='github_read_credential'").fetchone()[0] == 0


def test_completion_delay_does_not_return_an_expired_credential(tmp_path):
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        fence = durable_fence(owner, tmp_path)
        original = fence.complete
        def complete(*args):
            original(*args)
            owner.now += 901
        fence.complete = complete
        owner._issuance_fence = fence
        with pytest.raises(InstallationCredentialError):
            await provider(owner).installation_token()
        assert sum(c[0] == "POST" for c in owner.calls) == 1
    asyncio.run(run())


def test_runtime_schema_drift_is_not_repaired_by_credential_use(tmp_path):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    with fence._store.transaction() as connection:
        connection.execute("UPDATE schema_migrations SET checksum='synthetic-drift' WHERE version=1")
    owner._issuance_fence = fence
    with pytest.raises(InstallationCredentialError):
        asyncio.run(provider(owner).installation_token())
    assert owner.calls == [] and owner.signs == 0


def test_orphan_qualified_record_cannot_be_replaced_by_new_attempt(tmp_path):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    with fence._store.transaction() as connection:
        fence._store.append_event(connection, aggregate_type="github_read_credential",
            aggregate_id="synthetic-orphan", event_type="GITHUB_READ_CREDENTIAL_QUALIFIED",
            command_id=fence._command(owner.binding) + ":qualified", payload={})
    owner._issuance_fence = fence
    with pytest.raises(InstallationCredentialError):
        asyncio.run(provider(owner).installation_token())
    assert owner.calls == [] and owner.signs == 0


def test_successful_issuance_adds_no_tables_and_no_secret_bytes(tmp_path):
    from test_github_read_installation_identity import durable_fence
    owner = Owner()
    fence = durable_fence(owner, tmp_path)
    owner._issuance_fence = fence
    with fence._store.read() as connection:
        before = connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert asyncio.run(provider(owner).installation_token()) == TOKEN
    with fence._store.read() as connection:
        after = connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert [tuple(r) for r in after] == [tuple(r) for r in before]
    for path in fence._store.path.parent.glob(fence._store.path.name + "*"):
        if path.is_file():
            assert TOKEN.encode() not in path.read_bytes()


@pytest.mark.parametrize("failure", ["before_attempt_commit", "after_attempt_commit", "after_result_commit"])
def test_persistence_failure_never_opens_a_second_issuance(tmp_path, failure):
    from contextlib import contextmanager
    from control_plane.executive_runtime import PersistenceError
    from test_github_read_installation_identity import durable_fence
    async def run():
        owner = Owner()
        fence = durable_fence(owner, tmp_path)
        owner._issuance_fence = fence
        real_transaction = fence._store.transaction
        calls = [0]
        @contextmanager
        def transaction():
            calls[0] += 1
            if failure == "before_attempt_commit" and calls[0] == 1:
                raise PersistenceError("synthetic persistence failure before transaction")
            with real_transaction() as connection:
                yield connection
            if ((failure == "after_attempt_commit" and calls[0] == 1)
                    or (failure == "after_result_commit" and calls[0] == 2)):
                raise PersistenceError("synthetic acknowledgement loss after commit")
        fence._store.transaction = transaction
        subject = provider(owner)
        with pytest.raises(InstallationCredentialError):
            await subject.installation_token()
        expected_posts = 1 if failure == "after_result_commit" else 0
        assert sum(c[0] == "POST" for c in owner.calls) == expected_posts
        assert subject.evidence()["credential_obtained"] is False
        if failure != "before_attempt_commit":
            # A fresh adapter reconciles durable evidence, not the lost acknowledgement.
            owner._issuance_fence = durable_fence(owner, tmp_path)
            before = len(owner.calls)
            with pytest.raises(InstallationCredentialError):
                await provider(owner).installation_token()
            assert len(owner.calls) == before
    asyncio.run(run())
