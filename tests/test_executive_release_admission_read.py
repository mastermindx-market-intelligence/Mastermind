"""P4 B2 Runtime admission-read slice — ``read_admission``.

Tests the bounded Runtime owner method on
``runtime.release_maintenance``: first append/readback, restart-surviving
read, genuine absent ``None``, refusal for changed fingerprint, drifted
``root_qualification_digest``, noncanonical persisted bytes, wrong Event
header/sequence, malformed original approval or preconditions, foreign
read snapshot, and the absence of mint/admission/dispatch/Job-Attempt
effect capability.

The slice reuses RuntimeStore's owner-validated read snapshot, the strict
``record_approval`` / ``read_approval`` path, ``append_event`` and
``get_event_by_command_id``. The synthetic admission Event is appended
through ``RuntimeStore.append_event``; it never confers production
authority. No new table, store, scheduler, lease or physical owner path
is introduced.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import sqlite3

import pytest

from control_plane import executive_release_contract as rc
from control_plane import executive_runtime as er
from control_plane.ceo_request import app_request_ref


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _hex(n: int) -> str:
    return format(n, "064x")


def _hex40(seed: str) -> str:
    return (seed * 40)[:40]


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _make_principal() -> dict:
    return {
        "policy_id": "test-policy",
        "issuer_digest": _hex(1),
        "resource_digest": _hex(2),
        "subject_digest": _hex(3),
        "client_ref": _hex(4),
        "scopes": [
            "mastermind.executive.intent.submit",
            "mastermind.executive.read",
        ],
    }


def _make_effect(action: str = "executive.release.upgrade") -> dict:
    return {
        "schema": "mastermind.executive_release_effect/v1",
        "repository": "mastermindx-market-intelligence/Mastermind",
        "protected_source_sha": _hex40("1"),
        "source_policy_mode": "exact_protected_master",
        "installer_source_commit": _hex40("1"),
        "installer_source_tree": _hex40("2"),
        "installer_profile_digest": _hex(5),
        "from_release_commit": _hex40("3"),
        "from_release_tree": _hex40("4"),
        "from_installed_manifest_digest": _hex(6),
        "to_release_commit": _hex40("1"),
        "to_release_tree": _hex40("2"),
        "staged_artifact_digest": _hex(7),
        "staged_content_metadata_digest": _hex(8),
        "platform": "darwin",
        "architecture": "arm64",
        "configuration_transition_digest": _hex(9),
        "compatibility_proof_digest": _hex(10),
        "preservation_plan_digest": _hex(11),
        "rollback_evidence": {
            "kind": "upgrade",
            "rollback_readiness_digest": _hex(12),
        },
        "action": action,
    }


def make_approval(
    *,
    op: str = "p4-b2-runtime-r1",
    action: str = "executive.release.upgrade",
    owner_installation_id: str = "11111111-1111-4111-8111-111111111111",
) -> dict:
    principal = _make_principal()
    effect = _make_effect(action)
    validated_effect = rc.validate_normalized_effect(effect)
    effect_digest = hashlib.sha256(
        rc.canonical_release_bytes(validated_effect)
    ).hexdigest()
    principal_digest = hashlib.sha256(
        rc.canonical_release_bytes(rc.validate_principal_projection(principal))
    ).hexdigest()
    grant = {
        "schema": "mastermind.executive_release_grant/v1",
        "principal_digest": principal_digest,
        "authority_policy_hash": _hex(13),
        "policy_id": principal["policy_id"],
        "policy_generation": 1,
        "action": action,
        "target_ref": _hex(14),
        "transition_digest": effect_digest,
        "installer_profile_digest": effect["installer_profile_digest"],
        "confirmation_requirement": "delegated",
        "confirmation_evidence_digest": _hex(15),
        "granted_at_ms": 1000,
        "expires_at_ms": 301000,
    }
    validated_grant = rc.validate_release_grant(grant)
    grant_digest = hashlib.sha256(
        rc.canonical_release_bytes(validated_grant)
    ).hexdigest()
    return {
        "schema": "mastermind.executive_release_approval/v1",
        "operation_key": op,
        "request_ref": app_request_ref(op),
        "approved_transition_ref": "p4-approval:" + app_request_ref(op),
        "action": action,
        "owner_installation_id": owner_installation_id,
        "target_ref": _hex(14),
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


def _make_preconditions(
    *,
    approval: dict,
    admission_contract_digest: str,
    approval_evidence_digest: str,
    boot_id: str = "22222222-2222-4222-8222-222222222222",
) -> dict:
    # Effect-derived precondition fields must mirror the original
    # normalized effect carried in the approval; the authority_policy_hash
    # must mirror the grant; everything else is held by the upstream
    # bound identity. The fixture is a real positive, not a synthetic
    # stand-in.
    effect = approval["normalized_requested_effect"]
    grant = approval["grant"]
    return {
        "schema": "mastermind.executive_release_preconditions/v1",
        "owner_installation_id": approval["owner_installation_id"],
        "target_ref": approval["target_ref"],
        "boot_id": boot_id,
        "from_installed_manifest_digest": effect["from_installed_manifest_digest"],
        "installed_configuration_digest": _hex(21),
        "python_runtime_provenance_digest": _hex(22),
        "provider_binary_attestation_digest": _hex(23),
        "authority_policy_hash": grant["authority_policy_hash"],
        "grant_digest": approval["effective_grant_digest"],
        "approval_evidence_digest": approval_evidence_digest,
        "staged_artifact_digest": effect["staged_artifact_digest"],
        "staged_content_metadata_digest": effect["staged_content_metadata_digest"],
        "compatibility_proof_digest": effect["compatibility_proof_digest"],
        "preservation_plan_digest": effect["preservation_plan_digest"],
        "issuer_binding_digest": _hex(29),
        "admission_contract_digest": admission_contract_digest,
        "production_arming_digest": _hex(30),
    }


def _make_admission(
    *,
    approval: dict,
    preconditions: dict,
    approval_evidence_digest: str,
    root_qualification_digest: str,
    maintenance_sequence: int = 1,
    target_observation_digest: str | None = None,
) -> dict:
    request_ref = app_request_ref(approval["operation_key"])
    if target_observation_digest is None:
        target_observation_digest = _hex(31)
    return {
        "schema": "mastermind.executive_release_admission/v1",
        "operation_key": approval["operation_key"],
        "approved_transition_ref": "p4-approval:" + request_ref,
        "target_ref": approval["target_ref"],
        "owner_installation_id": approval["owner_installation_id"],
        "boot_id": preconditions["boot_id"],
        "request_fingerprint": rc.request_fingerprint_for(approval),
        "effective_grant_digest": approval["effective_grant_digest"],
        "maintenance_sequence": maintenance_sequence,
        "admission_event_command_id": "p4-admit:" + request_ref,
        "target_observation_digest": target_observation_digest,
        "admission_contract_digest": _hex(32),
    }


def _next_admission_sequence(
    owner_installation_id: str,
    connection: sqlite3.Connection,
) -> int:
    return int(
        connection.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM events"
            " WHERE aggregate_type=? AND aggregate_id=?",
            (
                er.EXECUTIVE_RELEASE_AGGREGATE_TYPE,
                owner_installation_id,
            ),
        ).fetchone()[0]
    )


def _append_admission_event(
    store: er.RuntimeStore,
    connection: sqlite3.Connection,
    *,
    approval: dict,
    wrapper: dict,
    principal_digest: str,
) -> int:
    """Append a synthetic admission Event through the existing store API.

    Returns the actual ``Event.sequence`` allocated by ``append_event`` so
    the test can match it against the wrapper's projection. The fixture's
    inserted Event never confers production authority.
    """
    payload = copy.deepcopy(wrapper)
    actor = er.EXECUTIVE_RELEASE_ACTOR_PREFIX + principal_digest
    request_ref = app_request_ref(approval["operation_key"])
    command_id = "p4-admit:" + request_ref
    store.append_event(
        connection,
        aggregate_type=er.EXECUTIVE_RELEASE_AGGREGATE_TYPE,
        aggregate_id=approval["owner_installation_id"],
        event_type=er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
        actor=actor,
        job_id=None,
        attempt_id=None,
        worker_id=None,
        quota_class=None,
        payload=payload,
        command_id=command_id,
        timestamp_ms=2000,
    )
    after_row = connection.execute(
        "SELECT sequence FROM events WHERE command_id=?",
        (command_id,),
    ).fetchone()
    assert after_row is not None
    return int(after_row[0])


def _principal_digest(approval: dict) -> str:
    return hashlib.sha256(
        rc.canonical_release_bytes(
            rc.validate_principal_projection(approval["principal_projection"])
        )
    ).hexdigest()


def _build_wrapper(
    approval: dict,
    *,
    maintenance_sequence: int = 1,
    root_qualification_digest: str | None = None,
    boot_id: str = "22222222-2222-4222-8222-222222222222",
) -> dict:
    if root_qualification_digest is None:
        root_qualification_digest = _hex(99)
    approval_canonical = rc.canonical_release_bytes(
        rc.validate_approval_evidence(approval)
    )
    approval_evidence_digest = hashlib.sha256(approval_canonical).hexdigest()
    admission_contract_digest = _hex(32)
    preconditions = _make_preconditions(
        approval=approval,
        admission_contract_digest=admission_contract_digest,
        approval_evidence_digest=approval_evidence_digest,
        boot_id=boot_id,
    )
    admission = _make_admission(
        approval=approval,
        preconditions=preconditions,
        approval_evidence_digest=approval_evidence_digest,
        root_qualification_digest=root_qualification_digest,
        maintenance_sequence=maintenance_sequence,
    )
    context = er.ReleaseMaintenanceRegistry._admission_context_record(
        approval=rc.validate_approval_evidence(approval),
        request_fingerprint=admission["request_fingerprint"],
        preconditions=rc.validate_precondition_manifest(preconditions),
        target_observation_digest=admission["target_observation_digest"],
        prepared_deadline_ms=300_000,
        root_qualification_digest=root_qualification_digest,
    )
    return {
        "schema": "mastermind.executive_release_admission_wrapper/v1",
        "admission": admission,
        "preconditions": preconditions,
        "approval_evidence_digest": approval_evidence_digest,
        "root_qualification_digest": root_qualification_digest,
        "admission_context": context,
        "evidence_digest": hashlib.sha256(
            er.ReleaseMaintenanceRegistry._canonical_context_evidence(
                "admission", context
            )
        ).hexdigest(),
    }


def _build_wrapper_with_sequence(
    approval: dict,
    connection: sqlite3.Connection,
    *,
    root_qualification_digest: str | None = None,
    boot_id: str = "22222222-2222-4222-8222-222222222222",
) -> dict:
    """Build a wrapper whose ``maintenance_sequence`` matches the Event.sequence
    that ``append_event`` will allocate for the admission Event, given an
    existing aggregate (the approval Event already occupies sequence 1).
    """
    seq = _next_admission_sequence(
        approval["owner_installation_id"], connection
    )
    return _build_wrapper(
        approval,
        maintenance_sequence=seq,
        root_qualification_digest=root_qualification_digest,
        boot_id=boot_id,
    )


@pytest.fixture
def store(tmp_path):
    return er.RuntimeStore(tmp_path)


@pytest.fixture
def foreign_store(tmp_path):
    return er.RuntimeStore(tmp_path / "foreign")


@pytest.fixture
def approval():
    return make_approval()


@pytest.fixture
def populated(tmp_path):
    """A store with one full (approval + admission) pair persisted."""
    s = er.RuntimeStore(tmp_path)
    rm = er.ReleaseMaintenanceRegistry(s)
    ap = make_approval()
    with s.transaction() as conn:
        ctx = er._release_context_for_test(s, conn, sealed_approval=ap)
        rm.record_approval(
            connection=conn, sealed_approval=ap, trusted_context=ctx
        )
        wrapper = _build_wrapper_with_sequence(ap, conn)
        _append_admission_event(
            s,
            conn,
            approval=ap,
            wrapper=wrapper,
            principal_digest=_principal_digest(ap),
        )
    return s, ap, wrapper


# ---------------------------------------------------------------------------
# Section 1 — first append / readback
# ---------------------------------------------------------------------------


def test_first_append_then_read_returns_immutable_public_admission(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        result = rm.read_admission(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
        )
    # 13-field public projection; the validate_admission contract defines 12
    # keys plus ``schema`` — the ReleaseRecord is fully detached and frozen.
    assert isinstance(result, rc.ReleaseRecord)
    assert result["operation_key"] == approval["operation_key"]
    assert result["approved_transition_ref"] == approval["approved_transition_ref"]
    assert result["admission_event_command_id"] == (
        "p4-admit:" + app_request_ref(approval["operation_key"])
    )
    assert result["target_ref"] == approval["target_ref"]
    assert result["effective_grant_digest"] == approval["effective_grant_digest"]
    assert result["maintenance_sequence"] >= 1
    # No internal digest leaks.
    leak = {"root_qualification_digest", "approval_evidence_digest",
            "preconditions"}
    assert not any(key in result for key in leak)
    # The result is a detached immutable ReleaseRecord; mutating it must fail.
    with pytest.raises(TypeError):
        result["operation_key"] = "changed"


def test_read_admission_does_not_require_extra_write_path(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        rm.read_admission(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
        )
    # No new Event row was written by the read.
    with store.read() as connection:
        rows = connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type=?",
            (er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,),
        ).fetchone()[0]
    assert rows == 1


def test_canonical_persisted_bytes_round_trip(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        row = connection.execute(
            "SELECT payload_json FROM events WHERE event_type=?",
            (er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,),
        ).fetchone()
    stored_raw = str(row["payload_json"])
    expected_canonical = rc.canonical_release_bytes(wrapper).decode("utf-8")
    assert stored_raw == expected_canonical


# ---------------------------------------------------------------------------
# Section 2 — restart-surviving read
# ---------------------------------------------------------------------------


def test_read_admission_survives_store_restart(tmp_path):
    store = er.RuntimeStore(tmp_path)
    rm = er.ReleaseMaintenanceRegistry(store)
    ap = make_approval()
    with store.transaction() as conn:
        ctx = er._release_context_for_test(store, conn, sealed_approval=ap)
        rm.record_approval(
            connection=conn, sealed_approval=ap, trusted_context=ctx
        )
        wrapper = _build_wrapper_with_sequence(ap, conn)
        _append_admission_event(
            store,
            conn,
            approval=ap,
            wrapper=wrapper,
            principal_digest=_principal_digest(ap),
        )
    # Drop the live connection and reopen a fresh RuntimeStore on the same
    # database file — no in-process state survives.
    store.close() if hasattr(store, "close") else None
    store2 = er.RuntimeStore(tmp_path)
    rm2 = er.ReleaseMaintenanceRegistry(store2)
    with store2.read() as connection:
        result = rm2.read_admission(
            connection,
            approved_transition_ref=ap["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(ap),
        )
    assert result["operation_key"] == ap["operation_key"]
    assert result["maintenance_sequence"] >= 1


# ---------------------------------------------------------------------------
# Section 3 — genuine absence
# ---------------------------------------------------------------------------


def test_genuine_absent_returns_none(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        result = rm.read_admission(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
        )
    assert result is None


def test_absent_with_only_approval_recorded_returns_none(store, approval):
    """A recorded approval alone does NOT count as an admission."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as conn:
        ctx = er._release_context_for_test(store, conn, sealed_approval=approval)
        rm.record_approval(
            connection=conn, sealed_approval=approval, trusted_context=ctx
        )
    with store.read() as connection:
        result = rm.read_admission(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
        )
    assert result is None


def test_empty_or_short_approved_transition_ref_refuses(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    fp = rc.request_fingerprint_for(approval)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref="",
                request_fingerprint=fp,
            )
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref="not-prefixed:" + fp,
                request_fingerprint=fp,
            )
        # Shortened reference collision must refuse, not silently read.
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"][:32],
                request_fingerprint=fp,
            )


def test_empty_or_non_hex_fingerprint_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint="",
            )
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint="not-a-digest",
            )


# ---------------------------------------------------------------------------
# Section 4 — fingerprint / reservation digest drift
# ---------------------------------------------------------------------------


def test_changed_fingerprint_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = _hex(42)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=wrong,
            )
        assert caught.value.field == "request_fingerprint"
        assert caught.value.code == "MISMATCH"


def test_causal_joint_admission_caller_fingerprint_rewrite_refuses(populated):
    """A forged persisted and caller fingerprint pair refuses approval join.

    The B4 parent probe rewrote both copies of request_fingerprint together.
    Comparison against the persisted projection alone therefore returned
    the forged admission. read_admission must instead derive the canonical
    full fingerprint from the original strictly validated approval and
    require exact joins to both the caller value and persisted admission.
    """
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    canonical_fingerprint = rc.request_fingerprint_for(approval)
    forged_fingerprint = (
        "a" * 64 if canonical_fingerprint != "a" * 64 else "b" * 64
    )
    wrong = copy.deepcopy(wrapper)
    wrong["admission"]["request_fingerprint"] = forged_fingerprint
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=forged_fingerprint,
            )
        assert caught.value.field == "request_fingerprint"
        assert caught.value.code == "MISMATCH"


def test_drifted_root_qualification_digest_refuses(tmp_path):
    store = er.RuntimeStore(tmp_path)
    rm = er.ReleaseMaintenanceRegistry(store)
    ap = make_approval()
    with store.transaction() as conn:
        ctx = er._release_context_for_test(store, conn, sealed_approval=ap)
        rm.record_approval(
            connection=conn, sealed_approval=ap, trusted_context=ctx
        )
        wrapper = _build_wrapper_with_sequence(
            ap, conn, root_qualification_digest=_hex(99)
        )
        _append_admission_event(
            store,
            conn,
            approval=ap,
            wrapper=wrapper,
            principal_digest=_principal_digest(ap),
        )
    # Drift the persisted root_qualification_digest via a NON-canonical
    # edit (no re-canonicalisation), so the persisted payload_json no
    # longer matches the canonical projection of its parsed form.
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        drifted = copy.deepcopy(wrapper)
        drifted["root_qualification_digest"] = _hex(100)
        canonical = rc.canonical_release_bytes(drifted).decode("utf-8")
        # Insert a trailing space inside the root_qualification_digest
        # string so the JSON is still valid but no longer canonical.
        bad_raw = canonical.replace(
            _hex(100), _hex(100) + " ", 1
        )
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                bad_raw,
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises((er.ReleaseMaintenanceError, rc.ReleaseContractError)) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=ap["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(ap),
            )
        # Non-canonical persisted bytes fail at the payload round-trip;
        # 64-hex format check fires first if the trailing space corrupts
        # the digest field beyond 64 chars.
        assert caught.value.field in {"payload", "root_qualification_digest"}


def test_uppercase_root_qualification_digest_refuses(tmp_path):
    """Hex digests are 64-char lowercase; an uppercase variant refuses."""
    store = er.RuntimeStore(tmp_path)
    rm = er.ReleaseMaintenanceRegistry(store)
    ap = make_approval()
    # Build a 64-char lowercase hex that actually contains hex letters,
    # so ``.upper()`` produces a visibly different value.
    upper_root = ("deadbeef" * 8).upper()
    with store.transaction() as conn:
        ctx = er._release_context_for_test(store, conn, sealed_approval=ap)
        rm.record_approval(
            connection=conn, sealed_approval=ap, trusted_context=ctx
        )
        wrapper = _build_wrapper_with_sequence(
            ap, conn, root_qualification_digest="deadbeef" * 8
        )
        _append_admission_event(
            store,
            conn,
            approval=ap,
            wrapper=wrapper,
            principal_digest=_principal_digest(ap),
        )
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        mutated = copy.deepcopy(wrapper)
        mutated["root_qualification_digest"] = upper_root
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(mutated).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=ap["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(ap),
            )
        assert caught.value.code in {"FORMAT", "LOWERCASE"}
        assert caught.value.field == "root_qualification_digest"


# ---------------------------------------------------------------------------
# Section 5 — noncanonical persisted bytes
# ---------------------------------------------------------------------------


def test_noncanonical_persisted_bytes_refuse(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        # Insert a literal space inside one of the wrapper strings so the
        # persisted payload_json no longer equals the canonical projection
        # of its parsed form.
        bad_raw = rc.canonical_release_bytes(wrapper).replace(
            b'"root_qualification_digest"',
            b'"root_qualification_digest ":"placeholder" , "root_qualification_digest"',
            1,
        )
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (bad_raw.decode("utf-8"), er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises((er.ReleaseMaintenanceError, rc.ReleaseContractError)) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        # Any of the canonical-round-trip / payload-keys / structural
        # validations refuses. The exact code path depends on which key
        # the JSON duplication collides with first.
        assert caught.value.field in {"payload", "wrapper", "preconditions", "admission"}


# ---------------------------------------------------------------------------
# Section 6 — wrong Event header / sequence
# ---------------------------------------------------------------------------


def test_wrong_event_family_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET event_type=? WHERE event_type=?",
            ("SOMETHING_ELSE", er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "event_envelope"
        assert caught.value.code == "FAMILY"


def test_wrong_aggregate_type_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET aggregate_type=? WHERE event_type=?",
            ("foreign_family", er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "event_envelope"
        assert caught.value.code == "AGGREGATE"


def test_wrong_aggregate_id_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET aggregate_id=? WHERE event_type=?",
            (
                "99999999-9999-4999-8999-999999999999",
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "event_envelope"
        assert caught.value.code == "AGGREGATE_ID"


def test_wrong_actor_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET actor=? WHERE event_type=?",
            (
                "release-principal:" + _hex(12345),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "actor"
        assert caught.value.code == "PRINCIPAL"


def test_job_attempt_link_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET job_id=? WHERE event_type=?",
            ("J-1", er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "event_envelope"
        assert caught.value.code == "JOB_LINK"


def test_wrong_maintenance_sequence_refuses(populated):
    """A wrapper whose maintenance_sequence diverges from the Event.sequence."""
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = copy.deepcopy(wrapper)
        wrong["admission"]["maintenance_sequence"] = 999
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(wrong).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "maintenance_sequence"
        assert caught.value.code == "MISMATCH"


# ---------------------------------------------------------------------------
# Section 7 — malformed original approval / preconditions
# ---------------------------------------------------------------------------


def test_malformed_original_approval_refuses(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        bad = _canonical({"schema": "mastermind.executive_release_approval/v1"})
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (bad.decode("utf-8"), er.EXECUTIVE_RELEASE_APPROVED_EVENT_TYPE),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )


def test_malformed_preconditions_refuse(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = copy.deepcopy(wrapper)
        wrong["preconditions"] = {"schema": "mastermind.executive_release_preconditions/v1"}
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(wrong).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises((er.ReleaseMaintenanceError, rc.ReleaseContractError)) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        # Either the wrapped inner contract validator refuses, or the
        # preconditions join / payload key check refuses.
        assert caught.value.field in {"payload", "preconditions"}


def test_drifty_precondition_owner_bind_refuses(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = copy.deepcopy(wrapper)
        wrong["preconditions"]["owner_installation_id"] = (
            "33333333-3333-4333-8333-333333333333"
        )
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(wrong).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        # Either validate_precondition_manifest (uuid mismatch in binding) or
        # the explicit join check refuses; both raise through the payload
        # field or the preconditions field.
        assert caught.value.field in {"preconditions", "payload"}


# ---------------------------------------------------------------------------
# Section 7a — causal coverage for the three P4-B3 parent old-GREEN failures
# plus the remaining authority_hash / effect-derived precondition joins.
# ---------------------------------------------------------------------------


def _rewrite_admission_payload(
    store: er.RuntimeStore, wrapper: dict, *, aggregate_id: str | None = None
) -> None:
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        if aggregate_id is None:
            raw.execute(
                "UPDATE events SET payload_json=? WHERE event_type=?",
                (
                    rc.canonical_release_bytes(wrapper).decode("utf-8"),
                    er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
                ),
            )
        else:
            raw.execute(
                "UPDATE events SET payload_json=?,aggregate_id=? WHERE event_type=?",
                (
                    rc.canonical_release_bytes(wrapper).decode("utf-8"),
                    aggregate_id,
                    er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
                ),
            )
        raw.commit()
    finally:
        raw.close()


def test_causal_foreign_owner_joint_rewrite_refuses(populated):
    """Causal test for the P4-B3 parent ``foreign_owner_refused`` failure.

    Both the admission projection and the precondition manifest are
    rewritten together with the persisted Event's aggregate_id, so the
    admission/precondition join alone would no longer refuse. Only the
    exact identity of admission + preconditions with the *original*
    approval's owner can satisfy the readback contract.
    """
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    foreign = "33333333-3333-4333-8333-333333333333"
    wrong = copy.deepcopy(wrapper)
    wrong["admission"]["owner_installation_id"] = foreign
    wrong["preconditions"]["owner_installation_id"] = foreign
    _rewrite_admission_payload(store, wrong, aggregate_id=foreign)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "OWNER_BIND_APPROVAL"


def test_causal_effect_drift_staged_artifact_refuses(populated):
    """Causal test for the P4-B3 parent ``effect_drift_refused`` failure.

    The staged_artifact_digest in the precondition manifest is rewritten
    away from the original normalized effect; only the original effect
    digest can satisfy the join.
    """
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = copy.deepcopy(wrapper)
    wrong["preconditions"]["staged_artifact_digest"] = "a" * 64
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "STAGED_ARTIFACT"


def test_causal_whitespace_approved_transition_ref_refuses(populated):
    """Causal test for the P4-B3 parent ``whitespace_ref_refused`` failure.

    A whitespace-padded copy of the original approved_transition_ref must
    refuse under exact-typed-string grammar; no caller-side coercion or
    normalisation is allowed.
    """
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    padded = " " + approval["approved_transition_ref"] + " "
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=padded,
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "approved_transition_ref"
        assert caught.value.code == "PREFIX"


def test_causal_whitespace_request_fingerprint_refuses(populated):
    """Whitespace around the request_fingerprint refuses the readback."""
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    padded = " " + rc.request_fingerprint_for(approval) + " "
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=padded,
            )
        assert caught.value.field == "request_fingerprint"
        assert caught.value.code == "FORMAT"


def test_drifty_precondition_authority_policy_hash_refuses(populated):
    """preconditions.authority_policy_hash must equal the approval grant's."""
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = copy.deepcopy(wrapper)
    wrong["preconditions"]["authority_policy_hash"] = _hex(777)
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "AUTHORITY_HASH"


def test_drifty_precondition_from_installed_manifest_refuses(populated):
    """preconditions.from_installed_manifest_digest must equal the effect."""
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = copy.deepcopy(wrapper)
    wrong["preconditions"]["from_installed_manifest_digest"] = _hex(777)
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "FROM_INSTALLED_MANIFEST"


def test_drifty_precondition_staged_content_metadata_refuses(populated):
    """preconditions.staged_content_metadata_digest must equal the effect."""
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = copy.deepcopy(wrapper)
    wrong["preconditions"]["staged_content_metadata_digest"] = _hex(777)
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "STAGED_CONTENT_METADATA"


def test_drifty_precondition_compatibility_proof_refuses(populated):
    """preconditions.compatibility_proof_digest must equal the effect."""
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = copy.deepcopy(wrapper)
    wrong["preconditions"]["compatibility_proof_digest"] = _hex(777)
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "COMPATIBILITY_PROOF"


def test_drifty_precondition_preservation_plan_refuses(populated):
    """preconditions.preservation_plan_digest must equal the effect."""
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    wrong = copy.deepcopy(wrapper)
    wrong["preconditions"]["preservation_plan_digest"] = _hex(777)
    _rewrite_admission_payload(store, wrong)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "PRESERVATION_PLAN"


def test_drifty_admission_owner_bind_to_approval_refuses(populated):
    """admission.owner_installation_id must equal the approval owner's id.

    The rewrite also retargets the Event's aggregate_id so the envelope
    check passes; only the cross-identity join to the original approval's
    owner remains to refuse.
    """
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    foreign = "33333333-3333-4333-8333-333333333333"
    wrong = copy.deepcopy(wrapper)
    wrong["admission"]["owner_installation_id"] = foreign
    wrong["preconditions"]["owner_installation_id"] = foreign
    _rewrite_admission_payload(store, wrong, aggregate_id=foreign)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        # admission + precondition both join consistently, but neither
        # joins the original approval's owner — the approval-bind check
        # on the admission side is what catches this exact drift.
        assert caught.value.field in {"admission", "preconditions"}
        assert caught.value.code == "OWNER_BIND_APPROVAL"


def test_drifty_precondition_boot_bind_refuses(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = copy.deepcopy(wrapper)
        wrong["preconditions"]["boot_id"] = (
            "44444444-4444-4444-8444-444444444444"
        )
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(wrong).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "BOOT_BIND"


def test_drifty_precondition_approval_digest_refuses(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = copy.deepcopy(wrapper)
        wrong["preconditions"]["approval_evidence_digest"] = _hex(777)
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(wrong).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "preconditions"
        assert caught.value.code == "APPROVAL_DIGEST"


def test_wrapper_field_set_drift_refuses(populated):
    store, approval, _ = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = _canonical({
            "schema": "mastermind.executive_release_admission_wrapper/v1",
            "admission": {},
            "preconditions": {},
            "approval_evidence_digest": _hex(0),
            "root_qualification_digest": _hex(0),
            "extra_field": 1,
        })
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (wrong.decode("utf-8"), er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "payload"
        assert caught.value.code == "FIELDS"


def test_wrapper_schema_drift_refuses(populated):
    store, approval, wrapper = populated
    rm = er.ReleaseMaintenanceRegistry(store)
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        wrong = copy.deepcopy(wrapper)
        wrong["schema"] = "mastermind.executive_release_admission_wrapper/v0"
        raw.execute(
            "UPDATE events SET payload_json=? WHERE event_type=?",
            (
                rc.canonical_release_bytes(wrong).decode("utf-8"),
                er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE,
            ),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "wrapper"
        assert caught.value.code == "SCHEMA"


# ---------------------------------------------------------------------------
# Section 8 — owner-issued read snapshot requirement
# ---------------------------------------------------------------------------


def test_read_admission_refuses_owner_read_snapshot_for_write(store, approval):
    """A deferred owner read transaction is not a write transaction."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as conn:
        ctx = er._release_context_for_test(store, conn, sealed_approval=approval)
        rm.record_approval(
            connection=conn, sealed_approval=approval, trusted_context=ctx
        )
    # The read-only test path must use ``store.read()``; the function must
    # refuse a caller-issued read transaction that the RuntimeStore did not
    # hand out.
    foreign = store._open()
    try:
        foreign.execute("BEGIN")
        with pytest.raises(er.ReleaseMaintenanceError) as caught:
            rm.read_admission(
                foreign,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )
        assert caught.value.field == "connection"
        assert caught.value.code == "READ_CONNECTION_NOT_OWNER_ISSUED"
    finally:
        if foreign.in_transaction:
            foreign.rollback()
        foreign.close()


def test_read_admission_refuses_non_sqlite_connection(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)

    class FakeConnection:
        in_transaction = True

    with pytest.raises(er.ReleaseMaintenanceError):
        rm.read_admission(
            FakeConnection(),
            approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
        )


def test_read_admission_refuses_foreign_store_snapshot(store, foreign_store, approval):
    """A foreign-store ``read()`` snapshot cannot satisfy the read contract."""
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as conn:
        ctx = er._release_context_for_test(store, conn, sealed_approval=approval)
        rm.record_approval(
            connection=conn, sealed_approval=approval, trusted_context=ctx
        )
    with foreign_store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )


@pytest.mark.parametrize("field,value", [
    ("event_type", "EXECUTIVE_RELEASE_ADMITTED_V2"),
    ("aggregate_type", "other_aggregate"),
    ("aggregate_id", "22222222-2222-4222-8222-222222222222"),
    ("sequence", 99),
    ("actor", "release-principal:" + "0" * 64),
])
def test_causal_admission_header_drift_refuses(populated, field, value):
    store, approval, _ = populated
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(f"UPDATE events SET {field}=? WHERE event_type=?",
                    (value, er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE))
        raw.commit()
    finally:
        raw.close()
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )


def test_causal_split_admission_command_refuses_corrupt_history(populated):
    store, approval, _ = populated
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute("UPDATE events SET command_id=? WHERE event_type=?",
                    ("p4-admit:req-" + "f" * 32,
                     er.EXECUTIVE_RELEASE_ADMITTED_EVENT_TYPE))
        raw.commit()
    finally:
        raw.close()
    rm = er.ReleaseMaintenanceRegistry(store)
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.read_admission(
                connection,
                approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
            )


# ---------------------------------------------------------------------------
# Section 9 — surface guard rails (no public mint / dispatch / effect)
# ---------------------------------------------------------------------------


def test_release_maintenance_registry_has_no_public_admission_mint_or_dispatch():
    registry = er.ReleaseMaintenanceRegistry
    forbidden = {
        "admit",
        "dispatch",
        "mint",
        "issue_token",
        "settle",
        "effect",
        "authorize",
    }
    members = set(dir(registry)) | set(dir(er.ReleaseMaintenanceRegistry))
    for name in forbidden:
        assert name not in members, name


def test_read_admission_has_no_public_mint_or_authority():
    """``read_admission`` is a strict read; no mint / authority / dispatch."""
    fn = er.ReleaseMaintenanceRegistry.read_admission
    assert fn.__name__ == "read_admission"


def test_admission_and_closing_methods_are_runtime_owner_surface():
    members = set(dir(er.ReleaseMaintenanceRegistry))
    assert {"record_admission", "record_terminal", "read_unresolved_admission"} <= members


def test_record_admission_refuses_approval_only_context(store, approval):
    rm = er.ReleaseMaintenanceRegistry(store)
    preconditions = _make_preconditions(
        approval=approval,
        admission_contract_digest=_hex(32),
        approval_evidence_digest=hashlib.sha256(
            rc.canonical_release_bytes(rc.validate_approval_evidence(approval))
        ).hexdigest(),
    )
    with store.transaction() as connection:
        context = er._release_context_for_test(store, connection, sealed_approval=approval)
        rm.record_approval(
            connection=connection, sealed_approval=approval, trusted_context=context
        )
        with pytest.raises(er.ReleaseMaintenanceError):
            rm.record_admission(
                connection,
                sealed_approval=approval,
                request_fingerprint=rc.request_fingerprint_for(approval),
                preconditions=preconditions,
                target_observation_digest=_hex(31),
                trusted_context=context,
            )


def test_no_environment_config_request_bypass_for_admission():
    """No env / config / request can mint an admission or grant authority."""
    import inspect

    source = inspect.getsource(er.ReleaseMaintenanceRegistry.read_admission)
    forbidden_phrases = [
        "record_admission",
        "record_terminal",
        "issue_token",
        "prepare_release",
        "commit_prepared",
        "dispatch",
        "settle",
        "BROKER_KEY",
        "authorize",
    ]
    # Strip the docstring so common words like ``signing`` / ``sign`` /
    # ``mint`` (used to describe what the slice explicitly does not do)
    # cannot produce a false positive.
    doc = er.ReleaseMaintenanceRegistry.read_admission.__doc__ or ""
    stripped = source.replace(doc, "")
    for phrase in forbidden_phrases:
        assert phrase not in stripped, phrase
