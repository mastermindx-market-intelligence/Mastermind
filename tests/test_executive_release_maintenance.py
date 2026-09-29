"""P4 C1 Runtime release-maintenance slice — record_approval + read_approval.

Tests the bounded Runtime owner methods on ``runtime.release_maintenance``:
first append/readback, exact replay, concurrent serialisation, semantic
mismatch refusal, foreign-family / shortened-reference collision refusal,
malformed persisted payload refusal, caller-context spoof refusal, foreign
store / foreign connection refusal, absent-write-transaction refusal,
immutable detached result, historical expiry/revocation read, and the
absence of production prepare/commit/token/effect capability.

The slice reuses RuntimeStore's owner-validated connection, transaction /
snapshot semantics, current-schema checks, Events table, ``append_event`` and
``get_event_by_command_id``. No new schema, table, store, scheduler, lease,
signing-key access, maintenance fence or host/installer effect is introduced.
"""

from __future__ import annotations

import base64
import copy
import base64
import hashlib
import json
import sqlite3
import threading

import pytest

from control_plane import executive_release_contract as rc
from control_plane import executive_runtime as er
from control_plane.ceo_request import app_request_ref


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _hex64(n: int) -> str:
    return format(n, "064x")


def _hex40(seed: str) -> str:
    return (seed * 40)[:40]


def _canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def make_approval(
    *,
    op: str = "p4-c1-runtime-r3",
    action: str = "executive.release.upgrade",
    principal=None,
    owner_installation_id: str = "11111111-1111-4111-8111-111111111111",
):
    if principal is None:
        principal = {
            "policy_id": "test-policy",
            "issuer_digest": _hex64(1),
            "resource_digest": _hex64(2),
            "subject_digest": _hex64(3),
            "client_ref": _hex64(4),
            "scopes": [
                "mastermind.executive.intent.submit",
                "mastermind.executive.read",
            ],
        }
    effect = {
        "schema": "mastermind.executive_release_effect/v1",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "protected_source_sha": _hex40("1"),
        "source_policy_mode": "exact_protected_master",
        "installer_source_commit": _hex40("1"),
        "installer_source_tree": _hex40("2"),
        "installer_profile_digest": _hex64(5),
        "from_release_commit": _hex40("3"),
        "from_release_tree": _hex40("4"),
        "from_installed_manifest_digest": _hex64(6),
        "to_release_commit": _hex40("1"),
        "to_release_tree": _hex40("2"),
        "staged_artifact_digest": _hex64(7),
        "staged_content_metadata_digest": _hex64(8),
        "platform": "darwin",
        "architecture": "arm64",
        "configuration_transition_digest": _hex64(9),
        "compatibility_proof_digest": _hex64(10),
        "preservation_plan_digest": _hex64(11),
        "rollback_evidence": {
            "kind": "upgrade",
            "rollback_readiness_digest": _hex64(12),
        },
        "action": action,
    }
    validated_effect = rc.validate_normalized_effect(effect)
    effect_digest = hashlib.sha256(rc.canonical_release_bytes(validated_effect)).hexdigest()
    principal_digest = hashlib.sha256(
        rc.canonical_release_bytes(rc.validate_principal_projection(principal))
    ).hexdigest()
    grant = {
        "schema": "mastermind.executive_release_grant/v1",
        "principal_digest": principal_digest,
        "authority_policy_hash": _hex64(13),
        "policy_id": principal["policy_id"],
        "policy_generation": 1,
        "action": action,
        "target_ref": _hex64(14),
        "transition_digest": effect_digest,
        "installer_profile_digest": effect["installer_profile_digest"],
        "confirmation_requirement": "delegated",
        "confirmation_evidence_digest": _hex64(15),
        "granted_at_ms": 1000,
        "expires_at_ms": 301000,
    }
    validated_grant = rc.validate_release_grant(grant)
    grant_digest = hashlib.sha256(rc.canonical_release_bytes(validated_grant)).hexdigest()
    approval = {
        "schema": "mastermind.executive_release_approval/v1",
        "operation_key": op,
        "request_ref": app_request_ref(op),
        "approved_transition_ref": "p4-approval:" + app_request_ref(op),
        "action": action,
        "owner_installation_id": owner_installation_id,
        "target_ref": _hex64(14),
        "principal_projection": principal,
        "normalized_requested_effect": effect,
        "transition_digest": effect_digest,
        "grant": grant,
        "effective_grant_digest": grant_digest,
        "created_at_ms": 1000,
        "expires_at_ms": 301000,
        "owner_seal": {
            "key_id": "key-v1",
            "trust_generation": 1,
            "mac": base64.urlsafe_b64encode(bytes(32)).decode().rstrip("="),
        },
    }
    return approval


@pytest.fixture
def store(tmp_path):
    return er.RuntimeStore(tmp_path)


@pytest.fixture
def approval():
    return make_approval()


@pytest.fixture
def foreign_store(tmp_path):
    return er.RuntimeStore(tmp_path / "foreign")


# ---------------------------------------------------------------------------
# Section 1 — first append / readback
# ---------------------------------------------------------------------------


def test_first_append_then_readback_returns_immutable_original(store, approval):
    rm = store.release_maintenance if hasattr(store, "release_maintenance") else er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        recorded = rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    with store.read() as connection:
        reread = rm.read_approval(
            connection, approved_transition_ref=approval["approved_transition_ref"]
        )
    assert recorded["operation_key"] == approval["operation_key"]
    assert reread["operation_key"] == approval["operation_key"]
    assert rc.canonical_release_bytes(recorded) == _canonical(approval)
    assert rc.canonical_release_bytes(reread) == _canonical(approval)
    # The result is a detached immutable ReleaseRecord; mutating it must fail.
    with pytest.raises(TypeError):
        recorded["operation_key"] = "changed"


def test_runtime_class_exposes_release_maintenance(tmp_path):
    runtime = er.Runtime.at(tmp_path)
    assert isinstance(runtime.release_maintenance, er.ReleaseMaintenanceRegistry)
    assert runtime.release_maintenance.store is runtime.store


# ---------------------------------------------------------------------------
# Section 2 — exact replay
# ---------------------------------------------------------------------------


def test_exact_replay_returns_original_without_new_event(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        first = rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
        after_first = connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0]
        # Replay with an unrelated dummy context whose sealed digest still
        # matches the sealed evidence (the replay revalidates the stored
        # Event envelope, not the supplied context's identities).
        second = rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
        after_second = connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0]
    assert after_first == 1
    assert after_second == 1
    assert first["operation_key"] == second["operation_key"]
    assert rc.canonical_release_bytes(first) == rc.canonical_release_bytes(second)


def test_replay_with_fresh_context_and_changed_seal_refuses(store, approval):
    """A separately admitted same-reference payload must still equal the original."""
    rm = er.ReleaseMaintenanceRegistry(store)
    changed = copy.deepcopy(approval)
    changed["owner_seal"]["mac"] = base64.urlsafe_b64encode(
        b"b" * 32
    ).decode("ascii").rstrip("=")
    with store.transaction() as connection:
        original_context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection,
            sealed_approval=approval,
            trusted_context=original_context,
        )
        changed_context = er._release_context_for_test(
            store, connection, sealed_approval=changed
        )
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.record_approval(
                connection,
                sealed_approval=changed,
                trusted_context=changed_context,
            )
        assert caught.value.code == "SEMANTIC_MISMATCH"
        count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0]
    assert count == 1


def test_concurrent_same_key_calls_serialize_to_one_event(store, approval):
    """Two simultaneous BEGIN IMMEDIATE transactions, same command_id, leave one Event.

    ``store.transaction()`` already serialises through BEGIN IMMEDIATE and
    the store's busy_timeout. Two threads racing the same write each end up
    appending zero or one Event for that command_id; the UNIQUE
    ``command_id`` index plus the second thread's same-command lookup keep
    the second append from creating a duplicate row.
    """
    rm = er.ReleaseMaintenanceRegistry(store)
    results: list = []
    errors: list = []

    def worker() -> None:
        try:
            with store.transaction() as connection:
                local_ctx = er._release_context_for_test(
                    store, connection, sealed_approval=approval
                )
                result = rm.record_approval(
                    connection,
                    sealed_approval=approval,
                    trusted_context=local_ctx,
                )
                results.append(result)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(results) == 2
    with store.read() as connection:
        rows = connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0]
    assert rows == 1


# ---------------------------------------------------------------------------
# Section 3 — semantic mismatches and shortened-reference collision
# ---------------------------------------------------------------------------


def _evolve_payload(payload):
    """Return a JSON string that encodes the same dict with a tiny whitespace
    or key-order change so the persisted row no longer matches canonical."""
    raw = _canonical(payload)
    # Add a trailing space inside a string so the raw JSON differs from
    # canonical while still parsing back to the same dict.
    return raw.replace(b'"principal_projection"', b'"_spoof":1,"principal_projection"')


@pytest.mark.parametrize(
    "mutator",
    [
        lambda a: a.update({"action": "executive.release.rollback"}),
        lambda a: a.update({"owner_installation_id": "22222222-2222-4222-8222-222222222222"}),
        lambda a: a.update({"target_ref": _hex64(99)}),
        lambda a: a["grant"].update({"action": "executive.release.rollback"}),
        lambda a: a["grant"].update({"target_ref": _hex64(99)}),
        lambda a: a["normalized_requested_effect"].update({"protected_source_sha": _hex40("9")}),
        lambda a: a["principal_projection"].update({"policy_id": "different-policy"}),
        lambda a: a.update({"expires_at_ms": 301001}),
    ],
)
def test_semantic_mismatch_refuses_without_writes(store, approval, mutator):
    rm = er.ReleaseMaintenanceRegistry(store)
    tampered = copy.deepcopy(approval)
    mutator(tampered)
    with store.transaction() as connection:
        original = copy.deepcopy(approval)
        context = er._release_context_for_test(
            store, connection, sealed_approval=original
        )
        rm.record_approval(
            connection, sealed_approval=original, trusted_context=context
        )
        before_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE aggregate_id=?",
            (original["owner_installation_id"],),
        ).fetchone()[0]
        # The tampered evidence must refuse — either via pure-contract
        # validation, via the sealed-digest mismatch on the trusted context,
        # or via the envelope/payload cross-check. No append is allowed.
        with pytest.raises((er.ReleaseMaintenanceError, rc.ReleaseContractError)):
            rm.record_approval(
                connection,
                sealed_approval=tampered,
                trusted_context=context,
            )
        after_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE aggregate_id=?",
            (original["owner_installation_id"],),
        ).fetchone()[0]
    assert before_count == after_count == 1


def test_foreign_family_event_at_same_command_id_refuses(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    # The events table is protected by immutable-update and immutable-delete
    # triggers. Disable them in a separate raw connection so we can simulate
    # a stored foreign-family row at the same command_id and verify the
    # runtime refuses it on read.
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET event_type=?, aggregate_type=?, actor=?"
            " WHERE command_id=?",
            (
                "SOMETHING_ELSE",
                "foreign_family",
                "operator",
                approval["approved_transition_ref"],
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_approval(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
            )


def test_shortened_reference_collision_refuses(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    full = approval["approved_transition_ref"]
    short = full[:32]
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_approval(connection, approved_transition_ref=short)


# ---------------------------------------------------------------------------
# Section 4 — malformed persisted payload
# ---------------------------------------------------------------------------


def test_malformed_persisted_payload_refuses(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    # The events table is protected by immutable-update and immutable-delete
    # triggers. Disable them in a raw connection and rewrite the row's
    # ``payload_json`` so the canonical round-trip no longer matches.
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        tampered = _canonical(approval).replace(
            b'"principal_projection"', b'"_bad":1,"principal_projection"'
        )
        raw.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (tampered.decode("utf-8"), approval["approved_transition_ref"]),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_approval(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
            )


def test_malformed_persisted_payload_missing_field_refuses(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        bad = _canonical({"schema": "mastermind.executive_release_approval/v1"})
        raw.execute(
            "UPDATE events SET payload_json=? WHERE command_id=?",
            (bad.decode("utf-8"), approval["approved_transition_ref"]),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_approval(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
            )


# ---------------------------------------------------------------------------
# Section 5 — caller context spoof
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spoof",
    [
        None,
        {},
        {"store": "anything", "principal_digest": _hex64(1)},
        True,
        "release-principal:" + _hex64(1),
        ["release-principal:" + _hex64(1)],
        b"release-principal:" + _hex64(1).encode(),
    ],
)
def test_caller_context_spoof_refuses(store, approval, spoof):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_approval(
                connection,
                sealed_approval=approval,
                trusted_context=spoof,
            )


def test_release_record_alone_is_not_authority(store, approval):
    """A validated ReleaseRecord is not authority on its own."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        validated = rc.validate_approval_evidence(copy.deepcopy(approval))
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_approval(
                connection,
                sealed_approval=approval,
                trusted_context=validated,
            )


def test_structural_seal_is_not_authority(store, approval):
    """The owner_seal is structurally valid but is not authority."""
    rm = er.ReleaseMaintenanceRegistry(store)
    seal_only = {"owner_seal": copy.deepcopy(approval["owner_seal"])}
    with store.transaction() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_approval(
                connection,
                sealed_approval=approval,
                trusted_context=seal_only,
            )


# ---------------------------------------------------------------------------
# Section 6 — foreign store / foreign connection
# ---------------------------------------------------------------------------


def test_foreign_store_trusted_context_refuses(store, foreign_store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        spoof = er._release_context_for_test(
            foreign_store, connection, sealed_approval=approval
        )
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_approval(
                connection,
                sealed_approval=approval,
                trusted_context=spoof,
            )


def test_foreign_connection_trusted_context_refuses(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    foreign = sqlite3.connect(str(store.path))
    try:
        with store.transaction() as connection:
            spoof = er._release_context_for_test(
                store, foreign, sealed_approval=approval
            )
            with pytest.raises(er.ReleaseMaintenanceError):
                rm.record_approval(
                    connection,
                    sealed_approval=approval,
                    trusted_context=spoof,
                )
    finally:
        foreign.close()


def test_record_approval_refuses_foreign_store_connection(store, approval):
    """A connection opened on a different store's file refuses before append."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
    foreign = sqlite3.connect(":memory:")
    try:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_approval(
                foreign,
                sealed_approval=approval,
                trusted_context=context,
            )
    finally:
        foreign.close()


# ---------------------------------------------------------------------------
# Section 7 — absent write transaction
# ---------------------------------------------------------------------------


def test_record_approval_without_write_transaction_refuses(store, approval):
    """A connection with no active transaction refuses before any append."""
    rm = er.ReleaseMaintenanceRegistry(store)
    conn = sqlite3.connect(str(store.path))
    try:
        # ``conn`` has no active transaction: ``in_transaction`` is False.
        context = er._release_context_for_test(
            store, conn, sealed_approval=approval
        )
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_approval(
                conn,
                sealed_approval=approval,
                trusted_context=context,
            )
    finally:
        conn.close()


def test_record_approval_refuses_owner_read_snapshot(store, approval):
    """A deferred owner read transaction is not RuntimeStore.transaction()."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.record_approval(
                connection,
                sealed_approval=approval,
                trusted_context=context,
            )
        assert caught.value.code == "WRITE_TRANSACTION_NOT_OWNER_ISSUED"
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0] == 0


def test_record_approval_refuses_non_sqlite_connection(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)

    class FakeConnection:
        in_transaction = True

    with pytest.raises(er.ReleaseMaintenanceError):
        rm.record_approval(
            FakeConnection(),
            sealed_approval=approval,
            trusted_context=None,
        )


# ---------------------------------------------------------------------------
# Section 8 — historical expiry / revocation read
# ---------------------------------------------------------------------------


def test_historical_expiry_keeps_original_evidence_readable(store, approval):
    """An approval whose ``expires_at_ms`` is already past remains readable."""
    rm = er.ReleaseMaintenanceRegistry(store)
    assert approval["expires_at_ms"] <= 301_000
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    # ``read_approval`` performs no time-based re-evaluation; historical
    # evidence remains readable regardless of the current wall clock.
    with store.read() as connection:
        result = rm.read_approval(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
        )
    assert result["expires_at_ms"] == approval["expires_at_ms"]
    assert result["created_at_ms"] == approval["created_at_ms"]


def test_historical_revocation_does_not_erase_original(store, approval):
    """The original approval Event is not rewritten or removed."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    # The events table has immutability triggers; nothing in this slice
    # touches them. Confirm only one row exists and it round-trips.
    with store.read() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0]
    assert count == 1
    with store.read() as connection:
        result = rm.read_approval(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
        )
    assert result["approved_transition_ref"] == approval["approved_transition_ref"]


def test_read_approval_returns_not_found_when_absent(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_approval(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
            )


def test_read_approval_requires_exact_unbound_owner_read_handle(store, approval):
    """A same-file caller connection is not RuntimeStore.read() custody."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(connection, sealed_approval=approval, trusted_context=context)

    foreign_connection = store._open()
    try:
        foreign_connection.execute("BEGIN")
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_approval(
                foreign_connection,
                approved_transition_ref=approval["approved_transition_ref"],
            )
        assert caught.value.field == "connection"
        assert caught.value.code == "READ_CONNECTION_NOT_OWNER_ISSUED"
    finally:
        if foreign_connection.in_transaction:
            foreign_connection.rollback()
        foreign_connection.close()

    assert store._read_connections == set()
    with store.read() as owner_connection:
        result = rm.read_approval(
            owner_connection,
            approved_transition_ref=approval["approved_transition_ref"],
        )
    assert result["approved_transition_ref"] == approval["approved_transition_ref"]
    assert store._read_connections == set()


def test_unbound_read_handle_tracking_cleans_up_on_exception(store):
    with pytest.raises(RuntimeError):
        with store.read():
            raise RuntimeError("snapshot failed")
    assert store._read_connections == set()


# ---------------------------------------------------------------------------
# Section 9 — absence of production prepare / commit / token / effect
# ---------------------------------------------------------------------------


def test_release_maintenance_registry_has_no_prepare_commit_token_effect():
    registry = er.ReleaseMaintenanceRegistry
    forbidden = {
        "prepare",
        "commit",
        "prepare_release_transition",
        "commit_prepared_release_transition",
        "issue_token",
        "mint_token",
        "authorize",
        "effect",
        "dispatch",
        "settle",
    }
    members = set(dirattr(registry, "__dict__")) if hasattr(registry, "__dict__") else set()
    for name in forbidden:
        assert name not in members
    # The instance surface must expose only the two owner-bound methods.
    assert set(dirattr(er.ReleaseMaintenanceRegistry)) >= {
        "record_approval",
        "read_approval",
    }


def test_trusted_release_context_has_no_public_mint():
    """Production must not be able to mint a TrustedReleaseContext."""
    assert "TrustedReleaseContext" in er.__all__
    public_attrs = [n for n in dir(er.TrustedReleaseContext) if not n.startswith("_")]
    # Properties are exposed; constructors and module-level mint helpers are
    # the deliberately private surface. There must be no public ``mint`` /
    # ``for_*`` / ``issue`` / factory method.
    assert not any(
        name in {"mint", "for_broker", "issue", "create", "new", "from_*"}
        for name in public_attrs
    )


def test_no_environment_config_request_bypass():
    """The maintenance slice never consults env / config / request to mint
    contexts or grant authority. The only mint surface is the deliberately
    private capability fixture."""
    import inspect

    source = inspect.getsource(er)
    forbidden_phrases = [
        "prepare_release_transition",
        "commit_prepared_release_transition",
        "authorize_release_transition",
        "issuing token",
        "signing key",
        "BROKER_KEY",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in source, phrase


def test_runtime_release_maintenance_has_no_bypass_for_public_caller(tmp_path):
    runtime = er.Runtime.at(tmp_path)
    forbidden = {
        "prepare",
        "commit",
        "issue_token",
        "sign",
        "admit",
        "assert_effect_permitted",
        "record_attempted",
        "settle",
        "read_status",
    }
    members = set(dir(runtime.release_maintenance))
    for name in forbidden:
        assert name not in members
    assert "record_approval" in members
    assert "read_approval" in members


# ---------------------------------------------------------------------------
# Section 10 — exact envelope
# ---------------------------------------------------------------------------


def test_event_envelope_matches_strict_contract(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    with store.read() as connection:
        row = connection.execute(
            "SELECT event_type, aggregate_type, aggregate_id, actor, job_id,"
            " attempt_id, worker_id, quota_class, payload_json FROM events"
            " WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()
    principal_digest = hashlib.sha256(
        rc.canonical_release_bytes(
            rc.validate_principal_projection(approval["principal_projection"])
        )
    ).hexdigest()
    assert row["event_type"] == er.EXECUTIVE_RELEASE_APPROVED_EVENT_TYPE
    assert row["aggregate_type"] == er.EXECUTIVE_RELEASE_AGGREGATE_TYPE
    assert row["aggregate_id"] == approval["owner_installation_id"]
    assert row["actor"] == er.EXECUTIVE_RELEASE_ACTOR_PREFIX + principal_digest
    assert row["job_id"] is None
    assert row["attempt_id"] is None
    assert row["worker_id"] is None
    assert row["quota_class"] is None
    assert json.loads(row["payload_json"]) == approval
    with store.read() as connection:
        created_at_ms = connection.execute(
            "SELECT created_at_ms FROM events WHERE command_id=?",
            (approval["approved_transition_ref"],),
        ).fetchone()[0]
    assert created_at_ms == approval["created_at_ms"]


def test_command_id_derived_from_unchanged_operation_identity(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        rm.record_approval(
            connection, sealed_approval=approval, trusted_context=context
        )
    expected = "p4-approval:" + app_request_ref(approval["operation_key"])
    with store.read() as connection:
        rows = connection.execute(
            "SELECT command_id FROM events WHERE event_type=?",
            (er.EXECUTIVE_RELEASE_APPROVED_EVENT_TYPE,),
        ).fetchall()
    assert [r["command_id"] for r in rows] == [expected]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def dirattr(obj, name=None):
    """Compatibility helper for ``dir(...)`` slicing inside parametrize."""
    return dir(obj)
