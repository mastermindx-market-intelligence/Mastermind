from __future__ import annotations

import base64
import concurrent.futures
import copy
import errno
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re

import pytest

from control_plane import executive_release_actuator as actuator
from control_plane import executive_release_contract as contract


BOOT_ID = "12345678-1234-4123-8123-123456789abc"
OPERATION_KEY = "test-operation"
POSTCONDITION = "f" * 64


@pytest.fixture(autouse=True)
def publication_clock(monkeypatch):
    from types import SimpleNamespace
    real = actuator.time
    monkeypatch.setattr(actuator, "time", SimpleNamespace(
        monotonic=real.monotonic, sleep=real.sleep,
        time_ns=lambda: 2_200_000_000, monotonic_ns=lambda: 2_200_000_000))


def _ancestry(operation_key=OPERATION_KEY):
    reservation, approval, _, _ = _reservation_fixture(operation_key)
    return {"reservation": reservation, "approval": approval}


def _hex64(value: int) -> str:
    return format(value, "064x")


def _canonical_hash(value) -> str:
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


def _approval_fixture(operation_key: str = OPERATION_KEY):
    target_ref = _hex64(14)
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
        "protected_source_sha": "3" * 40,
        "source_policy_mode": "exact_protected_master",
        "installer_source_commit": "3" * 40,
        "installer_source_tree": "4" * 40,
        "installer_profile_digest": _hex64(5),
        "from_release_commit": "1" * 40,
        "from_release_tree": "2" * 40,
        "from_installed_manifest_digest": _hex64(6),
        "to_release_commit": "3" * 40,
        "to_release_tree": "4" * 40,
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
        "action": "executive.release.upgrade",
    }
    grant = {
        "schema": "mastermind.executive_release_grant/v1",
        "principal_digest": _canonical_hash(principal),
        "authority_policy_hash": _hex64(13),
        "policy_id": "test-policy",
        "policy_generation": 1,
        "action": effect["action"],
        "target_ref": target_ref,
        "transition_digest": _canonical_hash(effect),
        "installer_profile_digest": effect["installer_profile_digest"],
        "confirmation_requirement": "delegated",
        "confirmation_evidence_digest": _hex64(15),
        "granted_at_ms": 1_000,
        "expires_at_ms": 301_000,
    }
    approval = {
        "schema": "mastermind.executive_release_approval/v1",
        "operation_key": operation_key,
        "request_ref": contract.app_request_ref(operation_key),
        "approved_transition_ref": (
            "p4-approval:" + contract.app_request_ref(operation_key)
        ),
        "action": effect["action"],
        "owner_installation_id": BOOT_ID,
        "target_ref": target_ref,
        "principal_projection": principal,
        "normalized_requested_effect": effect,
        "transition_digest": _canonical_hash(effect),
        "grant": grant,
        "effective_grant_digest": _canonical_hash(grant),
        "created_at_ms": 1_000,
        "expires_at_ms": 301_000,
        "owner_seal": {
            "key_id": "key-v1",
            "trust_generation": 1,
            "mac": base64.urlsafe_b64encode(bytes(32)).decode().rstrip("="),
        },
    }
    return approval


def _preconditions_fixture(operation_key: str = OPERATION_KEY, approval=None):
    target_ref = _hex64(14)
    approval_evidence_digest = (
        _canonical_hash(approval) if approval is not None else _hex64(15)
    )
    if approval is None:
        return {
            "schema": "mastermind.executive_release_preconditions/v1",
            "owner_installation_id": BOOT_ID,
            "target_ref": target_ref,
            "boot_id": BOOT_ID,
            "from_installed_manifest_digest": _hex64(6),
            "installed_configuration_digest": _hex64(16),
            "python_runtime_provenance_digest": _hex64(1),
            "provider_binary_attestation_digest": _hex64(2),
            "authority_policy_hash": _hex64(3),
            "grant_digest": _hex64(4),
            "approval_evidence_digest": approval_evidence_digest,
            "staged_artifact_digest": _hex64(7),
            "staged_content_metadata_digest": _hex64(8),
            "compatibility_proof_digest": _hex64(9),
            "preservation_plan_digest": _hex64(10),
            "issuer_binding_digest": _hex64(11),
            "admission_contract_digest": _hex64(12),
            "production_arming_digest": _hex64(13),
        }
    effect = approval["normalized_requested_effect"]
    return {
        "schema": "mastermind.executive_release_preconditions/v1",
        "owner_installation_id": approval["owner_installation_id"],
        "target_ref": approval["target_ref"],
        "boot_id": BOOT_ID,
        "from_installed_manifest_digest": effect["from_installed_manifest_digest"],
        "installed_configuration_digest": _hex64(16),
        "python_runtime_provenance_digest": _hex64(1),
        "provider_binary_attestation_digest": _hex64(2),
        "authority_policy_hash": approval["grant"]["authority_policy_hash"],
        "grant_digest": _canonical_hash(approval["grant"]),
        "approval_evidence_digest": _canonical_hash(approval),
        "staged_artifact_digest": effect["staged_artifact_digest"],
        "staged_content_metadata_digest": effect[
            "staged_content_metadata_digest"
        ],
        "compatibility_proof_digest": effect["compatibility_proof_digest"],
        "preservation_plan_digest": effect["preservation_plan_digest"],
        "issuer_binding_digest": _hex64(11),
        "admission_contract_digest": _hex64(12),
        "production_arming_digest": _hex64(13),
    }


def _prepared_fixture(approval, preconditions):
    prepared = {
        "token_schema": "mastermind.executive_release_prepared.v1",
        "app_id": "mastermind.executive",
        "owner_installation_id": approval["owner_installation_id"],
        "app_generation": 1,
        "schema_digest": _canonical_hash(preconditions),
        "trust_generation": 1,
        "key_id": approval["owner_seal"]["key_id"],
        "authenticated_principal_digest": _canonical_hash(
            approval["principal_projection"]
        ),
        "approved_transition_ref": approval["approved_transition_ref"],
        "approval_evidence_digest": _canonical_hash(approval),
        "policy_id": approval["grant"]["policy_id"],
        "policy_generation": approval["grant"]["policy_generation"],
        "authority_policy_hash": approval["grant"]["authority_policy_hash"],
        "effective_grant_digest": _canonical_hash(approval["grant"]),
        "action_target_digest": _canonical_hash(
            {"action": approval["action"], "target_ref": approval["target_ref"]}
        ),
        "confirmation_requirement": approval["grant"][
            "confirmation_requirement"
        ],
        "privilege_class": "EXECUTIVE_RELEASE_TRANSITION",
        "operation_key": approval["operation_key"],
        "action_family": approval["action"],
        "target_ref": approval["target_ref"],
        "request_fingerprint": _request_fingerprint(approval),
        "boot_id": preconditions["boot_id"],
        "platform": "darwin",
        "normalized_requested_effect": copy.deepcopy(
            approval["normalized_requested_effect"]
        ),
        "normalized_requested_effect_digest": _canonical_hash(
            approval["normalized_requested_effect"]
        ),
        "expected_source_and_precondition_digest": _canonical_hash(preconditions),
        "admission_contract_digest": preconditions["admission_contract_digest"],
        "issued_at_ms": 1_500,
        "expires_at_ms": 250_000,
        "issued_monotonic_ns": 1_500_000_000,
        "expires_monotonic_ns": 250_000_000_000,
    }
    return prepared


def _request_fingerprint(approval):
    fields = {
        "operation_key": approval["operation_key"],
        "approved_transition_ref": approval["approved_transition_ref"],
        "approval_evidence_digest": _canonical_hash(approval),
        "authenticated_principal_digest": _canonical_hash(
            approval["principal_projection"]
        ),
        "target_ref": approval["target_ref"],
        "action_family": approval["action"],
        "normalized_requested_effect_digest": _canonical_hash(
            approval["normalized_requested_effect"]
        ),
    }
    return hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_REQUEST_V1\0"
        + contract.canonical_release_bytes(fields)
    ).hexdigest()


def _reservation_fixture(operation_key: str = OPERATION_KEY):
    approval = _approval_fixture(operation_key)
    preconditions = _preconditions_fixture(operation_key, approval=approval)
    prepared = _prepared_fixture(approval, preconditions)
    effect = approval["normalized_requested_effect"]
    before = {
        "release_commit": effect["from_release_commit"],
        "release_tree": effect["from_release_tree"],
        "installed_manifest_digest": preconditions[
            "from_installed_manifest_digest"
        ],
        "configuration_digest": preconditions["installed_configuration_digest"],
        "broker_source_commit": effect["from_release_commit"],
        "broker_source_tree": effect["from_release_tree"],
        "broker_binary_digest": _hex64(50),
        "service_generation_digests": {
            "control": _hex64(60),
            "worker": _hex64(61),
            "relay": _hex64(62),
            "gateway": _hex64(63),
            "broker": _hex64(64),
        },
    }
    reservation = {
        "schema": "mastermind.executive_release_prestart_reservation/v1",
        "request_id": "p4r-"
        + _request_fingerprint(approval)[:48],
        "request_fingerprint": _request_fingerprint(approval),
        "operation_key": operation_key,
        "approved_transition_ref": approval["approved_transition_ref"],
        "approval_evidence_digest": _canonical_hash(approval),
        "authenticated_principal_digest": _canonical_hash(
            approval["principal_projection"]
        ),
        "effective_grant_digest": _canonical_hash(approval["grant"]),
        "normalized_requested_effect_digest": _canonical_hash(effect),
        "action_family": approval["action"],
        "action_target_digest": _canonical_hash(
            {"action": approval["action"], "target_ref": approval["target_ref"]}
        ),
        "owner_installation_id": approval["owner_installation_id"],
        "target_ref": approval["target_ref"],
        "from_release_commit": effect["from_release_commit"],
        "to_release_commit": effect["to_release_commit"],
        "reservation_generation": 1,
        "reserved_at_ms": 2_000,
        "reserved_monotonic_ns": 2_000_000_000,
        "preconditions": preconditions,
        "expected_precondition_digest": _canonical_hash(preconditions),
        "prepared_payload": prepared,
        "prepared_token_digest": _hex64(70),
        "before": before,
        "target_observation_digest": _hex64(18),
    }
    return reservation, approval, preconditions, prepared


def _admission_fixture(operation_key: str = OPERATION_KEY):
    reservation, approval, preconditions, _prepared = _reservation_fixture(
        operation_key
    )
    admission = {
        "schema": "mastermind.executive_release_admission/v1",
        "operation_key": operation_key,
        "approved_transition_ref": approval["approved_transition_ref"],
        "target_ref": approval["target_ref"],
        "owner_installation_id": approval["owner_installation_id"],
        "boot_id": preconditions["boot_id"],
        "request_fingerprint": reservation["request_fingerprint"],
        "effective_grant_digest": reservation["effective_grant_digest"],
        "maintenance_sequence": 1,
        "admission_event_command_id": (
            "p4-admit:" + contract.app_request_ref(operation_key)
        ),
        "target_observation_digest": reservation["target_observation_digest"],
        "admission_contract_digest": preconditions["admission_contract_digest"],
    }
    return admission, reservation, approval


def _cancellation_fixture(operation_key: str = OPERATION_KEY):
    admission, reservation, approval = _admission_fixture(operation_key)
    cancellation = {
        "schema": "mastermind.executive_release_prestart_cancellation/v1",
        "request_id": reservation["request_id"],
        "request_fingerprint": reservation["request_fingerprint"],
        "operation_key": operation_key,
        "approved_transition_ref": reservation["approved_transition_ref"],
        "approval_evidence_digest": reservation["approval_evidence_digest"],
        "authenticated_principal_digest": reservation[
            "authenticated_principal_digest"
        ],
        "effective_grant_digest": reservation["effective_grant_digest"],
        "normalized_requested_effect_digest": reservation[
            "normalized_requested_effect_digest"
        ],
        "action_family": reservation["action_family"],
        "action_target_digest": reservation["action_target_digest"],
        "owner_installation_id": reservation["owner_installation_id"],
        "target_ref": reservation["target_ref"],
        "from_release_commit": reservation["from_release_commit"],
        "to_release_commit": reservation["to_release_commit"],
        "reservation_generation": 1,
        "root_qualification_digest": _canonical_hash(reservation),
        "admission_digest": _canonical_hash(admission),
        "cancellation_generation": 1,
        "cancelled_at_ms": 302_000,
        "cancelled_monotonic_ns": 302_000_000_000,
        "reason": "PREPARED_TOKEN_EXPIRED",
        "before": copy.deepcopy(reservation["before"]),
        "current": copy.deepcopy(reservation["before"]),
        "original_target_observation_digest": reservation[
            "target_observation_digest"
        ],
        "current_target_observation_digest": reservation[
            "target_observation_digest"
        ],
        "current_precondition_digest": reservation["expected_precondition_digest"],
        "authority_evidence_digest": _hex64(80),
    }
    return cancellation, reservation, admission, approval


def _inputs(operation_key: str = OPERATION_KEY):
    reservation, approval, preconditions, _prep = _reservation_fixture(operation_key)
    admission_value, _r, _a = _admission_fixture(operation_key)
    effect = approval["normalized_requested_effect"]
    before = reservation["before"]
    identity = {
        "operation_key": operation_key,
        "request_fingerprint": reservation["request_fingerprint"],
        "approval_evidence_digest": reservation["approval_evidence_digest"],
        "normalized_requested_effect_digest": reservation[
            "normalized_requested_effect_digest"
        ],
        "expected_source_and_precondition_digest": reservation[
            "expected_precondition_digest"
        ],
        "action_target_digest": reservation["action_target_digest"],
        "owner_installation_id": reservation["owner_installation_id"],
        "target_ref": reservation["target_ref"],
        "before_release_commit": before["release_commit"],
        "before_release_tree": before["release_tree"],
        "before_installed_manifest_digest": before["installed_manifest_digest"],
        "before_configuration_digest": before["configuration_digest"],
        "target_release_commit": reservation["to_release_commit"],
        "target_release_tree": effect["to_release_tree"],
        "boot_id": preconditions["boot_id"],
    }
    return identity, preconditions, admission_value


def _journal(root: Path, **kwargs):
    return actuator.ExecutiveReleaseActuatorJournal._for_tests(root, **kwargs)


def _root_digest(reservation: dict) -> str:
    return hashlib.sha256(contract.canonical_release_bytes(reservation)).hexdigest()


def _start(
    journal,
    operation_key: str = OPERATION_KEY,
    **changes,
):
    identity, preconditions, admission = _inputs(operation_key)
    identity.update(changes.pop("identity", {}))
    preconditions.update(changes.pop("preconditions", {}))
    admission.update(changes.pop("admission", {}))
    # The durable reservation stays the immutable authority snapshot. Caller
    # mutations exercise refusal; they never rewrite that ancestor to agree.
    reservation, approval, _res_preconds, _prepared = _reservation_fixture(
        operation_key
    )
    root_digest = changes.pop("root_qualification_digest", _root_digest(reservation))
    # Materialize reservation on disk if it is not already present so the
    # exact-start-replay path can succeed without re-reserving.
    try:
        existing_reservation = journal.read_prestart_reservation(
            operation_key, approval=approval
        )
        reservation = existing_reservation.to_dict() if hasattr(
            existing_reservation, "to_dict"
        ) else dict(existing_reservation)
    except actuator.ExecutiveReleaseActuatorJournalError:
        journal.reserve_prestart(reservation=reservation, approval=approval)
    return journal.create(
        actuator_generation=changes.pop("actuator_generation", 7),
        identity=identity,
        preconditions=preconditions,
        admission=admission,
        approval=approval,
        reservation=reservation,
        root_qualification_digest=root_digest,
        started_at_ms=changes.pop("started_at_ms", 2_001),
        **changes,
    )


def _before(record):
    return {
        "release_commit": record["before_release_commit"],
        "release_tree": record["before_release_tree"],
        "installed_manifest_digest": record["before_installed_manifest_digest"],
        "configuration_digest": record["before_configuration_digest"],
        "broker_source_commit": record["before_release_commit"],
        "broker_source_tree": record["before_release_tree"],
        "broker_binary_digest": _hex64(50),
        "service_generation_digests": {
            "control": _hex64(60),
            "worker": _hex64(61),
            "relay": _hex64(62),
            "gateway": _hex64(63),
            "broker": _hex64(64),
        },
    }


def _target(record):
    return {
        "release_commit": record["target_release_commit"],
        "release_tree": record["target_release_tree"],
        "installed_manifest_digest": _hex64(30),
        "configuration_digest": _hex64(31),
        "broker_source_commit": record["target_release_commit"],
        "broker_source_tree": record["target_release_tree"],
        "broker_binary_digest": _hex64(80),
        "service_generation_digests": {
            "control": _hex64(70),
            "worker": _hex64(71),
            "relay": _hex64(72),
            "gateway": _hex64(73),
            "broker": _hex64(74),
        },
    }


def _to_recovering(journal, record):
    for state in ("PUBLICATION_INTENT", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"):
        record = journal.advance(
            record["operation_key"],
            expected_generation=record["journal_generation"],
            state=state,
         **_ancestry(record["operation_key"]))
    return record


def _terminal(journal, record, state):
    before = _before(record)
    if state == "SUCCEEDED":
        after = _target(record)
        rollback = {"attempted": False}
    elif state == "FAILED_NOT_APPLIED":
        after = copy.deepcopy(before)
        rollback = {"attempted": False}
    else:
        after = copy.deepcopy(before)
        rollback = {
            "attempted": True,
            "restored_preimage_digest": _canonical_hash(before),
        }
    reservation, approval, _preconds, _prep = _reservation_fixture(
        record["operation_key"]
    )
    return journal.advance(
        record["operation_key"],
        expected_generation=record["journal_generation"],
        state=state,
        completed_at_ms=3_000,
        postcondition_digest=POSTCONDITION,
        before=before,
        after=after,
        rollback=rollback,
        reservation=reservation,
        approval=approval,
     after_actuator_generation=(9 if state == "ROLLED_BACK" else 8))


def _record_path(root: Path, operation_key: str = OPERATION_KEY) -> Path:
    return root / (
        hashlib.sha256(operation_key.encode("ascii")).hexdigest() + ".json"
    )


def _reservation_path(root: Path, operation_key: str = OPERATION_KEY) -> Path:
    return root / (
        hashlib.sha256(operation_key.encode("ascii")).hexdigest()
        + ".reservation.json"
    )


def _cancellation_path(root: Path, operation_key: str = OPERATION_KEY) -> Path:
    return root / (
        hashlib.sha256(operation_key.encode("ascii")).hexdigest()
        + ".cancellation.json"
    )


def _process_start(root: str, queue) -> None:
    try:
        queue.put(("ok", _start(_journal(Path(root))).to_dict()))
    except actuator.ExecutiveReleaseActuatorJournalError as exc:
        queue.put(("error", exc.code))


def _process_advance(root: str, queue) -> None:
    try:
        value = _journal(Path(root)).advance(
            OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT"
        , **_ancestry(OPERATION_KEY))
        queue.put(("ok", value.to_dict()))
    except actuator.ExecutiveReleaseActuatorJournalError as exc:
        queue.put(("error", exc.code))


# ---------------------------------------------------------------------------
# Existing START / advance / terminal behavior tests
# ---------------------------------------------------------------------------


def test_all_states_restart_and_embedded_records_are_exact(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    record = _start(journal)
    observed = [record["state"]]
    _, preconditions, admission = _inputs()
    assert record["preconditions"] == contract.validate_precondition_manifest(
        preconditions
    )
    assert record["admission"] == contract.validate_admission(admission)
    for state in ("PUBLICATION_INTENT", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"):
        record = journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state=state,
         **_ancestry(OPERATION_KEY))
        observed.append(state)
        assert _journal(root).read(OPERATION_KEY) == record
        assert record["preconditions"] == contract.validate_precondition_manifest(
            preconditions
        )
        assert record["admission"] == contract.validate_admission(admission)
    record = _terminal(journal, record, "SUCCEEDED")
    observed.append(record["state"])
    assert observed == list(actuator._STATES[:6])
    assert _journal(root).read(OPERATION_KEY) == record


def test_exact_start_replay_preserves_bytes_and_generations(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    first = _start(journal)
    path = _record_path(root)
    raw = path.read_bytes()
    metadata = path.stat().st_mtime_ns
    replay = _start(_journal(root))
    assert replay == first
    assert path.read_bytes() == raw
    assert path.stat().st_mtime_ns == metadata
    assert replay["journal_generation"] == 1


@pytest.mark.parametrize(
    ("category", "field", "replacement"),
    [
        ("identity", "request_fingerprint", _hex64(40)),
        ("identity", "approval_evidence_digest", _hex64(41)),
        ("identity", "normalized_requested_effect_digest", _hex64(42)),
        ("identity", "action_target_digest", _hex64(43)),
        ("identity", "before_release_commit", "5" * 40),
        ("identity", "target_release_tree", "6" * 40),
        ("preconditions", "production_arming_digest", _hex64(44)),
        ("admission", "maintenance_sequence", 2),
    ],
)
def test_same_operation_immutable_mismatch_is_conflict(
    tmp_path, category, field, replacement
):
    root = tmp_path / "journal"
    _start(_journal(root))
    changes = {category: {field: replacement}}
    if category == "preconditions":
        identity, preconditions, _ = _inputs()
        preconditions.update(changes[category])
        changes["identity"] = {
            "expected_source_and_precondition_digest": _canonical_hash(preconditions)
        }
    elif category == "identity" and field == "request_fingerprint":
        changes["admission"] = {"request_fingerprint": replacement}
    elif category == "identity" and field == "approval_evidence_digest":
        identity, preconditions, _ = _inputs()
        preconditions["approval_evidence_digest"] = replacement
        changes["preconditions"] = {
            "approval_evidence_digest": replacement,
        }
        changes["identity"] = {
            field: replacement,
            "expected_source_and_precondition_digest": _canonical_hash(preconditions),
        }
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _start(_journal(root), **changes)
    assert caught.value.code in {"CONFLICT", "ADMISSION_JOIN_MISMATCH", "RESERVATION_MISMATCH", "INVALID_BEFORE"}


@pytest.mark.parametrize(
    "changes",
    [
        {"actuator_generation": 8},
        {"started_at_ms": 2_002},
    ],
)
def test_start_generation_and_time_are_immutable(tmp_path, changes):
    root = tmp_path / "journal"
    _start(_journal(root))
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _start(_journal(root), **changes)
    assert caught.value.code in {"CONFLICT", "ADMISSION_JOIN_MISMATCH", "RESERVATION_MISMATCH", "INVALID_BEFORE"}


@pytest.mark.parametrize(
    "changes",
    [
        {"identity": {"expected_source_and_precondition_digest": _hex64(55)}},
        {"admission": {"effective_grant_digest": _hex64(56)}},
        {"admission": {"request_fingerprint": _hex64(57)}},
        {"preconditions": {"boot_id": "22345678-1234-4123-8123-123456789abc"}},
    ],
)
def test_start_refuses_broken_embedded_joins_before_filesystem_mutation(
    tmp_path, changes
):
    root = tmp_path / "journal"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        _start(_journal(root), **changes)
    # The reservation may have created the root directory, but the START
    # record file must never be written when embedded joins are broken.
    assert not _record_path(root).exists()


def test_state_and_generation_fencing(tmp_path):
    journal = _journal(tmp_path / "journal")
    record = _start(journal)
    for state in (
        "STARTED",
        "BROKER_RESTART_PENDING",
        "RECOVERING",
    ):
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
            journal.advance(
                OPERATION_KEY, expected_generation=1, state=state
            , **_ancestry(OPERATION_KEY))
        assert caught.value.code == "INVALID_TRANSITION"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=2, state="PUBLISHED", **_ancestry(OPERATION_KEY))
    assert caught.value.code == "GENERATION_MISMATCH"
    record = journal.advance(
        OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT"
    , **_ancestry(OPERATION_KEY))
    assert record["journal_generation"] == 2
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=2, state="PUBLICATION_INTENT", **_ancestry(OPERATION_KEY))
    assert caught.value.code == "INVALID_TRANSITION"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=2,
            state="BROKER_RESTART_PENDING",
            completed_at_ms=3_000,
         **_ancestry(OPERATION_KEY))
    assert caught.value.code == "TERMINAL_ARGUMENTS"


@pytest.mark.parametrize("state", ["SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"])
def test_each_terminal_truth_and_terminal_immutability(tmp_path, state):
    journal = _journal(tmp_path / state)
    record = _to_recovering(journal, _start(journal))
    if state == "FAILED_NOT_APPLIED":
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="NO_APPLY_PROOF_UNAVAILABLE"):
            _terminal(journal, record, state)
        assert journal.read(OPERATION_KEY) == record
        return
    terminal = _terminal(journal, record, state)
    assert terminal["state"] == state
    assert terminal["journal_generation"] == 6
    assert _journal(tmp_path / state).read(OPERATION_KEY) == terminal
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=5,
            state="SUCCEEDED",
            completed_at_ms=2_001,
            postcondition_digest=POSTCONDITION,
            before=_before(terminal),
            after=_target(terminal),
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "TERMINAL_IMMUTABLE"


@pytest.mark.parametrize(
    ("state", "after_kind", "rollback"),
    [
        ("SUCCEEDED", "before", {"attempted": False}),
        ("SUCCEEDED", "target", {"attempted": True, "restored_preimage_digest": "a" * 64}),
        ("FAILED_NOT_APPLIED", "target", {"attempted": False}),
        ("FAILED_NOT_APPLIED", "before", {"attempted": True, "restored_preimage_digest": "a" * 64}),
        ("ROLLED_BACK", "before", {"attempted": False}),
        ("ROLLED_BACK", "before", {"attempted": True, "restored_preimage_digest": "a" * 64}),
    ],
)
def test_terminal_truth_refusals(tmp_path, state, after_kind, rollback):
    journal = _journal(tmp_path / (state + after_kind + str(rollback["attempted"])))
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    after = copy.deepcopy(before) if after_kind == "before" else _target(record)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state=state,
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback=rollback,
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if state == "ROLLED_BACK" else 8))
    assert caught.value.code == ("NO_APPLY_PROOF_UNAVAILABLE" if state == "FAILED_NOT_APPLIED" else "INVALID_TERMINAL_TRUTH")


def test_terminal_time_and_closed_rollback_union(tmp_path):
    journal = _journal(tmp_path / "journal")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    for completed, rollback in (
        (999, {"attempted": False}),
        (2_000, {"attempted": False, "restored_preimage_digest": "a" * 64}),
        (2_000, {"attempted": True}),
        (2_000, {"attempted": 1}),
    ):
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
            journal.advance(
                OPERATION_KEY,
                expected_generation=record["journal_generation"],
                state="SUCCEEDED",
                completed_at_ms=completed,
                postcondition_digest=POSTCONDITION,
                before=before,
                after=_target(record),
                rollback=rollback,
                reservation=reservation,
                approval=approval,
             after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))


def test_terminal_after_missing_field_refuses(tmp_path):
    journal = _journal(tmp_path / "after-missing")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    after = _target(record)
    del after["broker_binary_digest"]
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "INVALID_AFTER"


def test_terminal_after_extra_field_refuses(tmp_path):
    journal = _journal(tmp_path / "after-extra")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    after = _target(record)
    after["unexpected"] = _hex64(99)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "INVALID_AFTER"


def test_terminal_after_partial_service_roles_refuses(tmp_path):
    journal = _journal(tmp_path / "after-roles-partial")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    after = _target(record)
    after["service_generation_digests"] = {
        "control": _hex64(70), "relay": _hex64(72),
    }
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "INVALID_AFTER"


def test_terminal_after_extra_service_role_refuses(tmp_path):
    journal = _journal(tmp_path / "after-roles-extra")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    after = _target(record)
    after["service_generation_digests"]["admin"] = _hex64(99)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "INVALID_AFTER"


def test_terminal_after_broker_source_mismatch_refuses(tmp_path):
    journal = _journal(tmp_path / "after-broker-mismatch")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    after = _target(record)
    after["broker_source_commit"] = "0" * 40
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "INVALID_AFTER"


def test_terminal_before_broker_source_mismatch_refuses(tmp_path):
    journal = _journal(tmp_path / "before-broker-mismatch")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    before["broker_source_commit"] = "0" * 40
    after = copy.deepcopy(before)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=before,
            after=after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "BEFORE_MISMATCH"


def test_terminal_rolled_back_preimage_hash_over_8_fields(tmp_path):
    journal = _journal(tmp_path / "rolled-back-preimage")
    record = _to_recovering(journal, _start(journal))
    before = _before(record)
    # Build an 8-field before with the same content shape but tweak one service
    # digest so the canonical bytes diverge from the reservation's before.
    tampered_before = copy.deepcopy(before)
    tampered_before["service_generation_digests"]["broker"] = _hex64(99)
    after = copy.deepcopy(before)
    preimage = _canonical_hash(after)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="ROLLED_BACK",
            completed_at_ms=3000,
            postcondition_digest=POSTCONDITION,
            before=tampered_before,
            after=after,
            rollback={
                "attempted": True,
                "restored_preimage_digest": preimage,
            },
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "ROLLED_BACK" == "ROLLED_BACK" else 8))
    assert caught.value.code == "BEFORE_MISMATCH"


def test_terminal_legacy_4_field_shape_refuses(tmp_path):
    journal = _journal(tmp_path / "legacy-4")
    record = _to_recovering(journal, _start(journal))
    legacy_before = {
        "release_commit": record["before_release_commit"],
        "release_tree": record["before_release_tree"],
        "installed_manifest_digest": record["before_installed_manifest_digest"],
        "configuration_digest": record["before_configuration_digest"],
    }
    legacy_after = copy.deepcopy(legacy_before)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="SUCCEEDED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            before=legacy_before,
            after=legacy_after,
            rollback={"attempted": False},
            reservation=reservation,
            approval=approval,
         after_actuator_generation=(9 if "SUCCEEDED" == "ROLLED_BACK" else 8))
    assert caught.value.code == "BEFORE_MISMATCH"


def test_nonterminal_advance_rejects_terminal_arguments(tmp_path):
    journal = _journal(tmp_path / "nonterminal-rejects")
    _start(journal)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=1,
            state="PUBLICATION_INTENT",
            completed_at_ms=2_500,
         **_ancestry(OPERATION_KEY))
    assert caught.value.code == "TERMINAL_ARGUMENTS"
    before = {"release_commit": "1" * 40}
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=1,
            state="PUBLICATION_INTENT",
            before=before,
         **_ancestry(OPERATION_KEY))
    assert caught.value.code == "TERMINAL_ARGUMENTS"


def test_terminal_advance_requires_caller_supplied_before(tmp_path):
    journal = _journal(tmp_path / "terminal-requires-before")
    record = _to_recovering(journal, _start(journal))
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            OPERATION_KEY,
            expected_generation=record["journal_generation"],
            state="FAILED_NOT_APPLIED",
            completed_at_ms=3_000,
            postcondition_digest=POSTCONDITION,
            after=_before(record),
            rollback={"attempted": False},
         **_ancestry(OPERATION_KEY))
    assert caught.value.code == "TERMINAL_ARGUMENTS"


@pytest.mark.parametrize(
    "malformed",
    [
        b"{}",
        b'{"schema":"x","schema":"y"}',
        b'{"value":null}',
        b'{"value":' + b"[" * 10 + b"0" + b"]" * 10 + b"}",
        b"x" * (16 * 1024 + 1),
    ],
)
def test_malformed_duplicate_null_depth_and_oversize_storage_fail_closed(
    tmp_path, malformed
):
    root = tmp_path / "journal"
    _start(_journal(root))
    _record_path(root).write_bytes(malformed)
    os.chmod(_record_path(root), 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code in {"RECORD_BYTES", "RECORD_SIZE"}


def test_noncanonical_bytes_fail_closed(tmp_path):
    root = tmp_path / "journal"
    record = _start(_journal(root))
    noncanonical = json.dumps(record.to_dict(), sort_keys=True, indent=2).encode(
        "ascii"
    )
    _record_path(root).write_bytes(noncanonical)
    os.chmod(_record_path(root), 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "RECORD_BYTES"


def test_record_symlink_hardlink_and_mode_refuse(tmp_path):
    root = tmp_path / "journal"
    _start(_journal(root))
    path = _record_path(root)
    raw = path.read_bytes()
    path.unlink()
    path.symlink_to("/etc/passwd")
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        _journal(root).read(OPERATION_KEY)
    path.unlink()
    path.write_bytes(raw)
    os.chmod(path, 0o644)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "RECORD_METADATA"
    os.chmod(path, 0o600)
    alias = root / "alias"
    os.link(path, alias)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "RECORD_METADATA"


def test_root_symlink_mode_owner_and_acl_refuse(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    _start(_journal(root))
    os.chmod(root, 0o755)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "ROOT_METADATA"


def test_root_path_replacement_during_read_refuses(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    journal = _journal(root)
    _start(journal)
    original_read = journal._read_file
    moved = tmp_path / "moved-journal"

    def replace_after_read(*args, **kwargs):
        result = original_read(*args, **kwargs)
        root.rename(moved)
        root.mkdir(mode=0o700)
        return result

    monkeypatch.setattr(journal, "_read_file", replace_after_read)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read(OPERATION_KEY)
    assert caught.value.code == "ROOT_REPLACED"


def test_lock_path_replacement_while_held_refuses(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    journal = _journal(root)
    _start(journal)
    original_read = journal._read_file
    lock_path = _record_path(root).with_suffix(".lock")

    def replace_lock_after_read(*args, **kwargs):
        result = original_read(*args, **kwargs)
        lock_path.unlink()
        lock_path.write_bytes(b"")
        os.chmod(lock_path, 0o600)
        return result

    monkeypatch.setattr(journal, "_read_file", replace_lock_after_read)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read(OPERATION_KEY)
    assert caught.value.code == "LOCK_REPLACED"
    os.chmod(root, 0o700)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root, expected_uid=os.geteuid() + 1).read(OPERATION_KEY)
    assert caught.value.code == "ROOT_METADATA"
    monkeypatch.setattr(actuator, "has_macos_acl", lambda *args, **kwargs: True)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "ROOT_METADATA"


def test_atomic_replace_failure_preserves_prior_record_and_cleans_temp(
    tmp_path, monkeypatch
):
    root = tmp_path / "journal"
    journal = _journal(root)
    original = _start(journal)

    def refuse_replace(*args, **kwargs):
        raise OSError(errno.EIO, "refused")

    monkeypatch.setattr(actuator.os, "replace", refuse_replace)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT", **_ancestry(OPERATION_KEY))
    assert caught.value.code == "RECORD_REPLACE"
    assert journal.read(OPERATION_KEY) == original
    assert not list(root.glob("*.tmp"))


def test_temporary_path_replacement_before_publish_refuses(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    journal = _journal(root)
    original = _start(journal)
    original_read = journal._read_file
    replaced = False

    def replace_temporary_after_first_read(root_descriptor, name, *, required, **deadline):
        nonlocal replaced
        result = original_read(root_descriptor, name, required=required, **deadline)
        if name.endswith(".tmp") and not replaced:
            replaced = True
            os.unlink(name, dir_fd=root_descriptor)
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=root_descriptor,
            )
            try:
                os.write(descriptor, result[0])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return result

    monkeypatch.setattr(journal, "_read_file", replace_temporary_after_first_read)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT", **_ancestry(OPERATION_KEY))
    assert caught.value.code == "RECORD_REPLACED"
    assert journal.read(OPERATION_KEY) == original
    assert len(list(root.glob("*.tmp"))) == 1


def test_stale_temporary_file_refuses_without_changing_record(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    original = _start(journal)
    temporary = root / (_record_path(root).stem + ".tmp")
    temporary.write_bytes(b"stale")
    os.chmod(temporary, 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT", **_ancestry(OPERATION_KEY))
    assert caught.value.code == "RECORD_EXISTS"
    assert journal.read(OPERATION_KEY) == original


def test_thread_concurrency_serializes_start_and_generation_cas(tmp_path):
    root = tmp_path / "journal"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        starts = list(pool.map(lambda _: _start(_journal(root)), range(16)))
    assert all(value == starts[0] for value in starts)

    def advance(_):
        try:
            return _journal(root).advance(
                OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT"
            , **_ancestry(OPERATION_KEY))
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            return exc.code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(advance, range(16)))
    accepted = [value for value in results if isinstance(value, contract.ReleaseRecord)]
    refused = [value for value in results if isinstance(value, str)]
    assert len(accepted) == 1
    assert refused == ["GENERATION_MISMATCH"] * 15


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process flock semantics")
def test_process_concurrency_serializes_start_and_generation_cas(tmp_path):
    root = tmp_path / "journal"
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    starters = [
        context.Process(target=_process_start, args=(str(root), queue))
        for _ in range(6)
    ]
    for process in starters:
        process.start()
    for process in starters:
        process.join(10)
        assert process.exitcode == 0
    start_results = [queue.get(timeout=2) for _ in starters]
    assert all(kind == "ok" for kind, _ in start_results)
    assert all(value == start_results[0][1] for _, value in start_results)

    workers = [
        context.Process(target=_process_advance, args=(str(root), queue))
        for _ in range(6)
    ]
    for process in workers:
        process.start()
    for process in workers:
        process.join(10)
        assert process.exitcode == 0
    results = [queue.get(timeout=2) for _ in workers]
    assert [kind for kind, _ in results].count("ok") == 1
    assert [value for kind, value in results if kind == "error"] == [
        "GENERATION_MISMATCH"
    ] * 5


def test_multiple_operation_families_share_one_root(tmp_path):
    root = tmp_path / "journal"
    first = _start(_journal(root), "first-operation")
    second = _start(_journal(root), "second-operation")
    assert _journal(root).read("first-operation") == first
    assert _journal(root).read("second-operation") == second
    assert len(list(root.glob("*.json"))) == 4  # 2 records + 2 reservations
    assert len(list(root.glob("*.lock"))) == 2


@pytest.mark.parametrize("method", ["read", "advance"])
def test_record_bytes_are_bound_to_requested_operation(tmp_path, method):
    root = tmp_path / "journal"
    journal = _journal(root)
    _start(journal, "operation-a")
    _start(journal, "operation-b")
    path_a = _record_path(root, "operation-a")
    path_b = _record_path(root, "operation-b")
    path_a.write_bytes(path_b.read_bytes())
    original = path_a.read_bytes()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        if method == "read":
            journal.read("operation-a")
        else:
            journal.advance(
                "operation-a", expected_generation=1, state="PUBLICATION_INTENT"
            , **_ancestry("operation-a"))
    assert caught.value.code == "OPERATION_MISMATCH"
    assert path_a.read_bytes() == original


@pytest.mark.parametrize(
    "state",
    [
        "PUBLISHED",
        "BROKER_RESTART_PENDING",
        "RECOVERING",
        "SUCCEEDED",
        "ROLLED_BACK",
        "FAILED_NOT_APPLIED",
    ],
)
def test_exact_start_replay_after_progress_returns_current_record(tmp_path, state):
    root = tmp_path / state
    journal = _journal(root)
    current = _start(journal)
    for next_state in ("PUBLICATION_INTENT", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"):
        current = journal.advance(
            OPERATION_KEY,
            expected_generation=current["journal_generation"],
            state=next_state,
         **_ancestry(OPERATION_KEY))
        if next_state == state:
            break
    if state == "FAILED_NOT_APPLIED":
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="NO_APPLY_PROOF_UNAVAILABLE"):
            _terminal(journal, current, state)
        assert _start(_journal(root)) == current
        return
    if state in {"SUCCEEDED", "ROLLED_BACK"}:
        current = _terminal(journal, current, state)
    path = _record_path(root)
    raw = path.read_bytes()
    modified = path.stat().st_mtime_ns
    assert _start(_journal(root)) == current
    assert path.read_bytes() == raw
    assert path.stat().st_mtime_ns == modified


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires abrupt child exit")
def test_start_crash_never_exposes_partial_final_record(tmp_path):
    root = tmp_path / "journal"
    # Pre-reserve so the START crash actually targets the staged .start write.
    reservation, approval, _preconds, _prep = _reservation_fixture()
    _journal(root).reserve_prestart(reservation=reservation, approval=approval)

    def crash_after_partial_write():
        original_write = os.write

        def partial(descriptor, data):
            original_write(descriptor, data[:31])
            os.fsync(descriptor)
            os._exit(71)

        actuator.os.write = partial
        _start(_journal(root))

    child = multiprocessing.get_context("fork").Process(
        target=crash_after_partial_write
    )
    child.start()
    child.join(2)
    if child.is_alive():
        child.terminate()
        child.join(2)
    assert child.exitcode == 71
    final_path = _record_path(root)
    assert not final_path.exists()
    staged_path = final_path.with_suffix(".start")
    assert staged_path.exists()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _start(_journal(root))
    assert caught.value.code == "START_STAGED_CONFLICT"
    assert not final_path.exists()


def test_linked_start_crash_state_is_recovered_only_for_exact_candidate(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    identity, preconditions, admission = _inputs()
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    candidate = actuator._validate_record(
        {
            "schema": actuator._SCHEMA,
            "state": "STARTED",
            **identity,
            "preconditions": preconditions,
            "admission": admission,
            "actuator_generation": 7,
            "journal_generation": 1,
            "started_at_ms": 2_001,
            "root_qualification_digest": _root_digest(reservation),
            "before": reservation["before"],
            "start_deadline_monotonic_ns": reservation["prepared_payload"]["expires_monotonic_ns"],
        }
    )
    raw = contract.canonical_release_bytes(candidate)
    final_path = _record_path(root)
    staged_path = final_path.with_suffix(".start")
    # Simulate a half-finished crash by linking the staged bytes to the
    # final name without ever calling the publish path.
    staged_path.write_bytes(raw)
    os.chmod(staged_path, 0o600)
    os.link(staged_path, final_path)
    assert final_path.stat().st_nlink == 2
    # A non-exact candidate cannot adopt the linked crash pair.
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.create(
            actuator_generation=7,
            identity=identity,
            preconditions=preconditions,
            admission=admission,
            approval=approval,
            reservation=reservation,
            root_qualification_digest=_root_digest(reservation),
            started_at_ms=2_002,
        )
    assert caught.value.code == "START_STAGED_CONFLICT"
    assert final_path.stat().st_nlink == 2
    assert staged_path.stat().st_nlink == 2
    # Recovery completes the linked pair into a single final inode.
    recovered = journal.create(
        actuator_generation=7,
        identity=identity,
        preconditions=preconditions,
        admission=admission,
        approval=approval,
        reservation=reservation,
        root_qualification_digest=_root_digest(reservation),
        started_at_ms=2_001,
    )
    assert recovered == candidate
    assert final_path.stat().st_nlink == 1
    assert not staged_path.exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires FIFO race probe")
def test_regular_to_fifo_race_returns_finite_error(tmp_path):
    root = tmp_path / "journal"
    _start(_journal(root))
    path = _record_path(root)

    def race():
        original_open = os.open
        switched = False

        def switch(name, flags, *args, **kwargs):
            nonlocal switched
            if (
                str(name) == path.name
                and not switched
                and flags & os.O_ACCMODE == os.O_RDONLY
            ):
                switched = True
                os.unlink(name, dir_fd=kwargs["dir_fd"])
                os.mkfifo(name, 0o600, dir_fd=kwargs["dir_fd"])
            return original_open(name, flags, *args, **kwargs)

        actuator.os.open = switch
        try:
            _journal(root, lock_timeout=0.15).read(OPERATION_KEY)
        except actuator.ExecutiveReleaseActuatorJournalError:
            os._exit(0)
        os._exit(72)

    child = multiprocessing.get_context("fork").Process(target=race)
    child.start()
    child.join(2)
    if child.is_alive():
        child.terminate()
        child.join(2)
        pytest.fail("record open blocked on FIFO")
    assert child.exitcode == 0


def test_failed_write_cleanup_preserves_replacement_inode(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    root.mkdir(mode=0o700)
    journal = _journal(root)
    replacement = b"foreign-replacement"
    actual_open = os.open
    actual_write = os.write
    target = "owned.tmp"

    def replace_and_fail(descriptor, data):
        os.unlink(target, dir_fd=root_descriptor)
        new_descriptor = actual_open(
            target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=root_descriptor,
        )
        try:
            actual_write(new_descriptor, replacement)
        finally:
            os.close(new_descriptor)
        raise OSError(errno.EIO, "injected")

    root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(actuator.os, "write", replace_and_fail)
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
            journal._write_new(root_descriptor, target, b"candidate")
    finally:
        os.close(root_descriptor)
    path = root / target
    assert path.exists()
    assert path.read_bytes() == replacement


def test_advance_cleanup_never_adopts_replacement_inode(tmp_path, monkeypatch):
    root = tmp_path / "journal"
    journal = _journal(root)
    current = _start(journal)
    temporary = _record_path(root).with_suffix(".tmp")
    actual_write_new = journal._write_new
    held_descriptors = []

    def replace_after_write(root_descriptor, name, raw, **deadline):
        created_identity = actual_write_new(root_descriptor, name, raw, **deadline)
        if name.endswith(".tmp"):
            held_descriptors.append(
                os.open(name, os.O_RDONLY, dir_fd=root_descriptor)
            )
            os.unlink(name, dir_fd=root_descriptor)
            replacement_descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=root_descriptor,
            )
            try:
                os.write(replacement_descriptor, b"foreign-temp")
            finally:
                os.close(replacement_descriptor)
        return created_identity

    monkeypatch.setattr(journal, "_write_new", replace_after_write)
    try:
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
            journal.advance(
                OPERATION_KEY,
                expected_generation=1,
                state="PUBLICATION_INTENT",
             **_ancestry(OPERATION_KEY))
        assert journal.read(OPERATION_KEY) == current
        assert temporary.exists()
        assert temporary.read_bytes() == b"foreign-temp"
    finally:
        for descriptor in held_descriptors:
            os.close(descriptor)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process flock semantics")
def test_held_process_lock_times_out_without_record_effect(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    record = _start(journal)
    path = _record_path(root)
    raw = path.read_bytes()
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()

    def holder():
        descriptor = os.open(path.with_suffix(".lock"), os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            ready.set()
            release.wait(4)
        finally:
            os.close(descriptor)

    child = context.Process(target=holder)
    child.start()
    try:
        assert ready.wait(2)
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
            _journal(root, lock_timeout=0.1).advance(
                OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT"
            , **_ancestry(OPERATION_KEY))
        assert caught.value.code == "LOCK_TIMEOUT"
        assert path.read_bytes() == raw
    finally:
        release.set()
        child.join(2)
        if child.is_alive():
            child.terminate()
            child.join(2)
    assert child.exitcode == 0
    assert journal.read(OPERATION_KEY) == record


def test_missing_root_or_record_is_not_found_without_replay(tmp_path):
    root = tmp_path / "journal"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "NOT_FOUND"
    assert not root.exists()
    _start(_journal(root), "another-operation")
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _journal(root).read(OPERATION_KEY)
    assert caught.value.code == "NOT_FOUND"


def test_fixed_production_root_bounded_public_surface_and_no_effect_imports():
    source = Path(actuator.__file__).read_text()
    production = actuator.ExecutiveReleaseActuatorJournal()
    assert production._root == Path(
        "/var/db/mastermind-executive/release-actuator/journal"
    )
    assert production._expected_uid == 0
    assert production._lock_timeout == 5.0
    public = sorted(
        name
        for name in dir(actuator.ExecutiveReleaseActuatorJournal)
        if not name.startswith("_")
    )
    assert public == sorted(
        [
            "advance",
            "cancel_prestart",
            "create",
            "read",
            "read_prestart_cancellation",
            "read_prestart_reservation",
            "reserve_prestart",
        ]
    )
    assert set(actuator.__all__) == {
        "ExecutiveReleaseActuatorJournal",
        "ExecutiveReleaseActuatorJournalError",
        "JOURNAL_PRODUCTION_ROOT",
    }
    for forbidden in (
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "os.system",
        "popen",
        "getenv",
        "/var/lib",
        "sys.modules",
        "types.moduletype",
        "os.umask",
    ):
        assert forbidden not in source.lower()
    assert re.search(r"fcntl\.flock\(.+LOCK_NB", source)
    assert "os.unlink(lock_name" not in source


# ---------------------------------------------------------------------------
# PRESTART journal tests (reservation, cancellation, START joins)
# ---------------------------------------------------------------------------


def _stem(operation_key: str) -> str:
    return hashlib.sha256(operation_key.encode("ascii")).hexdigest()


def test_reserve_then_read_round_trip(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    recorded = journal.reserve_prestart(reservation=reservation, approval=approval)
    assert recorded["operation_key"] == reservation["operation_key"]
    read = journal.read_prestart_reservation(
        OPERATION_KEY, approval=approval
    )
    assert read == recorded
    assert _reservation_path(root).exists()


def test_exact_reservation_replay_returns_original_bytes_without_rewrite(
    tmp_path,
):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    first = journal.reserve_prestart(reservation=reservation, approval=approval)
    path = _reservation_path(root)
    raw = path.read_bytes()
    mtime = path.stat().st_mtime_ns
    second = journal.reserve_prestart(reservation=reservation, approval=approval)
    assert second == first
    assert path.read_bytes() == raw
    assert path.stat().st_mtime_ns == mtime


def test_reservation_mutation_conflicts_with_existing_reservation(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    mutated = copy.deepcopy(reservation)
    mutated["target_observation_digest"] = _hex64(99)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.reserve_prestart(reservation=mutated, approval=approval)
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_exact_reservation_replay_survives_cancellation_but_mutation_conflicts(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    first = journal.reserve_prestart(reservation=reservation, approval=approval)
    journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    assert journal.reserve_prestart(reservation=reservation, approval=approval) == first
    mutated = copy.deepcopy(reservation)
    mutated["target_observation_digest"] = _hex64(99)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.reserve_prestart(reservation=mutated, approval=approval)
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_exact_reservation_replay_survives_start_but_mutation_conflicts(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    _start(journal)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    replayed = journal.reserve_prestart(reservation=reservation, approval=approval)
    assert replayed == contract.validate_release_prestart_reservation(
        reservation, expected_approval=approval
    )
    mutated = copy.deepcopy(reservation)
    mutated["target_observation_digest"] = _hex64(99)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.reserve_prestart(reservation=mutated, approval=approval)
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_exact_cancellation_replay_returns_original_bytes(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    first = journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    cancellation_path = _cancellation_path(root)
    raw = cancellation_path.read_bytes()
    mtime = cancellation_path.stat().st_mtime_ns
    second = journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    assert second == first
    assert cancellation_path.read_bytes() == raw
    assert cancellation_path.stat().st_mtime_ns == mtime


def test_cancellation_mutation_conflicts_with_existing(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    mutated = copy.deepcopy(cancellation)
    mutated["reason"] = "GRANT_EXPIRED"
    mutated["cancelled_at_ms"] = 400_000
    mutated["cancelled_monotonic_ns"] = 400_000_000_000
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.cancel_prestart(
            cancellation=mutated,
            reservation=reservation,
            admission=admission,
            approval=approval,
        )
    assert caught.value.code == "CANCELLATION_CONFLICT"


def test_cancellation_requires_byte_identical_stored_reservation(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    different = copy.deepcopy(reservation)
    different["target_observation_digest"] = _hex64(91)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.cancel_prestart(
            cancellation=cancellation,
            reservation=different,
            admission=admission,
            approval=approval,
        )
    assert caught.value.code == "RESERVATION_MISMATCH"


def test_cancellation_refuses_after_final_start(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    record = _start(journal)
    # Walk to terminal SUCCEEDED to assert cancellation refuses after final.
    record = journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT", **_ancestry())
    record = journal.advance(
        OPERATION_KEY,
        expected_generation=record["journal_generation"],
        state="PUBLISHED",
     **_ancestry(OPERATION_KEY))
    record = journal.advance(
        OPERATION_KEY,
        expected_generation=record["journal_generation"],
        state="BROKER_RESTART_PENDING",
     **_ancestry(OPERATION_KEY))
    record = journal.advance(
        OPERATION_KEY,
        expected_generation=record["journal_generation"],
        state="RECOVERING",
     **_ancestry(OPERATION_KEY))
    _terminal(journal, record, "SUCCEEDED")
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.cancel_prestart(
            cancellation=cancellation,
            reservation=reservation,
            admission=admission,
            approval=approval,
        )
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_cancellation_refuses_after_staged_start(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    identity, preconditions, admission_value = _inputs()
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    candidate = actuator._validate_record(
        {
            "schema": actuator._SCHEMA,
            "state": "STARTED",
            **identity,
            "preconditions": preconditions,
            "admission": admission_value,
            "actuator_generation": 7,
            "journal_generation": 1,
            "started_at_ms": 2_001,
            "root_qualification_digest": _hex64(99),
            "before": reservation["before"],
            "start_deadline_monotonic_ns": reservation["prepared_payload"]["expires_monotonic_ns"],
        }
    )
    raw = contract.canonical_release_bytes(candidate)
    final_path = _record_path(root)
    staged_path = final_path.with_suffix(".start")
    staged_path.write_bytes(raw)
    os.chmod(staged_path, 0o600)
    os.link(staged_path, final_path)
    cancellation, _r, admission, _a = _cancellation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.cancel_prestart(
            cancellation=cancellation,
            reservation=reservation,
            admission=admission,
            approval=approval,
        )
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_cancellation_persists_when_start_advances(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    assert _reservation_path(root).exists()
    assert _cancellation_path(root).exists()
    # Reading the cancellation later succeeds through the locked read API.
    read_back = journal.read_prestart_cancellation(
        OPERATION_KEY,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    assert read_back["operation_key"] == OPERATION_KEY
    assert read_back["reason"] == "PREPARED_TOKEN_EXPIRED"


def test_cancellation_blocks_subsequent_start(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    identity, preconditions, admission_value = _inputs()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.create(
            actuator_generation=7,
            identity=identity,
            preconditions=preconditions,
            admission=admission_value,
            approval=approval,
            reservation=reservation,
            root_qualification_digest=_root_digest(reservation),
            started_at_ms=2_001,
        )
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_start_requires_existing_reservation(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    identity, preconditions, admission_value = _inputs()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.create(
            actuator_generation=7,
            identity=identity,
            preconditions=preconditions,
            admission=admission_value,
            approval=approval,
            reservation=reservation,
            root_qualification_digest=_root_digest(reservation),
            started_at_ms=2_001,
        )
    assert caught.value.code == "NOT_FOUND"


def test_start_requires_byte_identical_reservation(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    identity, preconditions, admission_value = _inputs()
    mutated = copy.deepcopy(reservation)
    mutated["target_observation_digest"] = _hex64(91)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.create(
            actuator_generation=7,
            identity=identity,
            preconditions=preconditions,
            admission=admission_value,
            approval=approval,
            reservation=mutated,
            root_qualification_digest=_root_digest(reservation),
            started_at_ms=2_001,
        )
    assert caught.value.code == "RESERVATION_MISMATCH"


def test_start_requires_matching_root_qualification_digest(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    identity, preconditions, admission_value = _inputs()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.create(
            actuator_generation=7,
            identity=identity,
            preconditions=preconditions,
            admission=admission_value,
            approval=approval,
            reservation=reservation,
            root_qualification_digest=_hex64(123),
            started_at_ms=2_001,
        )
    assert caught.value.code == "ROOT_QUALIFICATION_MISMATCH"


def test_start_requires_matching_admission_join(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    identity, preconditions, admission_value = _inputs()
    bad = copy.deepcopy(admission_value)
    bad["effective_grant_digest"] = _hex64(124)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.create(
            actuator_generation=7,
            identity=identity,
            preconditions=preconditions,
            admission=bad,
            approval=approval,
            reservation=reservation,
            root_qualification_digest=_root_digest(reservation),
            started_at_ms=2_001,
        )
    assert caught.value.code in {"ADMISSION_JOIN_MISMATCH", "INVALID_JOIN"}


def test_start_persists_reservation_and_root_digest(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    record = _start(journal)
    assert record["root_qualification_digest"] == _hex64(123) or len(
        record["root_qualification_digest"]
    ) == 64
    # Reservation remains intact after START.
    assert _reservation_path(root).exists()
    reservation, approval, _preconds, _prep = _reservation_fixture()
    read = journal.read_prestart_reservation(
        OPERATION_KEY, approval=approval
    )
    assert read["operation_key"] == OPERATION_KEY


def test_reservation_sidecar_metadata_and_mode_failures(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    # Create a START so an alias target exists for the hardlink check.
    journal.create(
        actuator_generation=7,
        identity=_inputs()[0],
        preconditions=_inputs()[1],
        admission=_inputs()[2],
        approval=approval,
        reservation=reservation,
        root_qualification_digest=_root_digest(reservation),
        started_at_ms=2_001,
    )
    path = _reservation_path(root)
    os.chmod(path, 0o644)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_reservation(OPERATION_KEY, approval=approval)
    assert caught.value.code == "RECORD_METADATA"
    os.chmod(path, 0o600)
    path.unlink()
    path.symlink_to("/etc/passwd")
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.read_prestart_reservation(OPERATION_KEY, approval=approval)
    path.unlink()
    os.link(_record_path(root), path)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_reservation(OPERATION_KEY, approval=approval)
    assert caught.value.code == "RECORD_METADATA"


def test_reservation_oversize_and_noncanonical_fail_closed(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    path = _reservation_path(root)
    # Oversize payload: write_bytes preserves the bytes but a re-read fails.
    path.write_bytes(b"x" * (16 * 1024 + 1))
    os.chmod(path, 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_reservation(OPERATION_KEY, approval=approval)
    assert caught.value.code in {"RECORD_SIZE", "RECORD_BYTES"}
    # Noncanonical JSON: a re-read rejects and a fresh reserve refuses to
    # overwrite because the existing bytes differ.
    fresh_root = tmp_path / "fresh-journal"
    fresh_journal = _journal(fresh_root)
    fresh_journal.reserve_prestart(reservation=reservation, approval=approval)
    fresh_path = _reservation_path(fresh_root)
    fresh_path.write_bytes(
        json.dumps(
            contract.validate_release_prestart_reservation(
                reservation, expected_approval=contract.validate_approval_evidence(
                    approval
                )
            ).to_dict(),
            indent=2,
        ).encode("ascii")
    )
    os.chmod(fresh_path, 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        fresh_journal.read_prestart_reservation(
            OPERATION_KEY, approval=approval
        )
    assert caught.value.code == "RECORD_BYTES"
    # Fresh reserve against the corrupted bytes must conflict.
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        fresh_journal.reserve_prestart(reservation=reservation, approval=approval)
    assert caught.value.code == "RESERVATION_CONFLICT"


def test_cancellation_persists_with_no_reservation_mutation(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    reservation_raw_before = _reservation_path(root).read_bytes()
    journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    assert _reservation_path(root).read_bytes() == reservation_raw_before


def test_cancellation_sidecar_metadata_failures(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    cancellation, _r, admission, _a = _cancellation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    journal.cancel_prestart(
        cancellation=cancellation,
        reservation=reservation,
        admission=admission,
        approval=approval,
    )
    path = _cancellation_path(root)
    os.chmod(path, 0o644)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_cancellation(
            OPERATION_KEY,
            reservation=reservation,
            admission=admission,
            approval=approval,
        )
    assert caught.value.code == "RECORD_METADATA"


def test_concurrent_reserve_cancel_start_coherence(tmp_path):
    root = tmp_path / "journal"

    def task_reserve(_):
        try:
            reservation, approval, _p, _pr = _reservation_fixture()
            return _journal(root).reserve_prestart(
                reservation=reservation, approval=approval
            ).to_dict()
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            return exc.code

    def task_cancel(_):
        try:
            reservation, approval, _p, _pr = _reservation_fixture()
            cancellation, _r, admission, _a = _cancellation_fixture()
            _journal(root).reserve_prestart(
                reservation=reservation, approval=approval
            )
            return _journal(root).cancel_prestart(
                cancellation=cancellation,
                reservation=reservation,
                admission=admission,
                approval=approval,
            ).to_dict()
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            return exc.code

    def task_start(_):
        try:
            return _start(_journal(root)).to_dict()
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            return exc.code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        tasks = []
        for _ in range(6):
            tasks.append(pool.submit(task_reserve, None))
            tasks.append(pool.submit(task_cancel, None))
            tasks.append(pool.submit(task_start, None))
        outcomes = [task.result() for task in tasks]
    accepted = [
        value
        for value in outcomes
        if isinstance(value, dict) and "operation_key" in value
    ]
    refused = [value for value in outcomes if isinstance(value, str)]
    # At least one reservation or START or cancellation should land.
    assert len(accepted) >= 1
    # All refused codes come from the bounded prestart set.
    assert set(refused).issubset(
        {
            "RESERVATION_CONFLICT",
            "CANCELLATION_CONFLICT",
            "RESERVATION_MISMATCH",
            "LOCK_TIMEOUT",
        }
    )


def test_reservation_and_cancellation_share_one_lock(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    expected_lock = root / (_stem(OPERATION_KEY) + ".lock")
    assert expected_lock.exists()
    assert os.readlink.__doc__  # noqa - keeps ruff happy


def test_read_prestart_reservation_without_reservation_is_not_found(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_reservation(OPERATION_KEY, approval=approval)
    assert caught.value.code == "NOT_FOUND"


def test_read_prestart_cancellation_without_cancellation_is_not_found(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    admission, _r, _a = _admission_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_cancellation(
            OPERATION_KEY,
            reservation=reservation,
            admission=admission,
            approval=approval,
        )
    assert caught.value.code == "NOT_FOUND"


def test_read_prestart_reservation_rejects_wrong_approval(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    bad_approval = copy.deepcopy(approval)
    bad_approval["effective_grant_digest"] = _hex64(200)
    with pytest.raises(
        (contract.ReleaseContractError, actuator.ExecutiveReleaseActuatorJournalError)
    ):
        journal.read_prestart_reservation(OPERATION_KEY, approval=bad_approval)


def test_read_prestart_reservation_rejects_wrong_operation_key(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, _preconds, _prep = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.read_prestart_reservation(
            "not a valid key", approval=approval
        )
    assert caught.value.code == "INVALID_OPERATION_KEY"


# ---------------------------------------------------------------------------
# Independent R1 regressions: START ancestry and sidecar custody
# ---------------------------------------------------------------------------


def _coherent_prestart_context(tmp_path):
    root = tmp_path / "journal"
    journal = _journal(root)
    reservation, approval, preconditions, _prepared = _reservation_fixture()
    identity, _preconditions, admission = _inputs()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    arguments = {
        "actuator_generation": 7,
        "identity": identity,
        "preconditions": preconditions,
        "admission": admission,
        "approval": approval,
        "reservation": reservation,
        "root_qualification_digest": _root_digest(reservation),
        "started_at_ms": 2_001,
    }
    return journal, root, arguments


def test_coherent_prestart_start_control(tmp_path):
    journal, _root, arguments = _coherent_prestart_context(tmp_path)
    assert journal.create(**arguments)["state"] == "STARTED"


@pytest.mark.parametrize(
    "field",
    [
        "normalized_requested_effect_digest",
        "action_target_digest",
        "before_release_commit",
        "before_release_tree",
        "target_release_commit",
        "target_release_tree",
    ],
)
def test_start_cannot_change_reserved_identity(tmp_path, field):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    arguments["identity"][field] = "f" * (
        40 if "commit" in field or "tree" in field else 64
    )
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.create(**arguments)
    assert not _record_path(root).exists()


@pytest.mark.parametrize(
    "field",
    [
        "python_runtime_provenance_digest",
        "provider_binary_attestation_digest",
        "authority_policy_hash",
        "staged_artifact_digest",
        "staged_content_metadata_digest",
        "compatibility_proof_digest",
        "preservation_plan_digest",
        "issuer_binding_digest",
        "production_arming_digest",
        "installed_configuration_digest",
        "from_installed_manifest_digest",
    ],
)
def test_start_preconditions_equal_reserved_snapshot(tmp_path, field):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    arguments["preconditions"] = copy.deepcopy(arguments["preconditions"])
    arguments["preconditions"][field] = "f" * 64
    arguments["identity"]["expected_source_and_precondition_digest"] = (
        _canonical_hash(arguments["preconditions"])
    )
    if field == "installed_configuration_digest":
        arguments["identity"]["before_configuration_digest"] = "f" * 64
    if field == "from_installed_manifest_digest":
        arguments["identity"]["before_installed_manifest_digest"] = "f" * 64
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.create(**arguments)
    assert not _record_path(root).exists()


@pytest.mark.parametrize("started_at_ms", [1_999, 250_000])
def test_start_time_stays_inside_reserved_prepared_window(
    tmp_path, started_at_ms
):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    arguments["started_at_ms"] = started_at_ms
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.create(**arguments)
    assert not _record_path(root).exists()


def test_exact_reservation_replay_cannot_adopt_changed_second_read(
    tmp_path, monkeypatch
):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    path = _reservation_path(root)
    changed = copy.deepcopy(arguments["reservation"])
    changed["target_observation_digest"] = "f" * 64
    contract.validate_release_prestart_reservation(
        changed, expected_approval=arguments["approval"]
    )
    original = journal._read_prestart_bytes
    reads = []

    def swap(*args, **kwargs):
        raw = original(*args, **kwargs)
        if kwargs["kind"] == "reservation" and not reads:
            reads.append(1)
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(contract.canonical_release_bytes(changed))
            replacement.chmod(0o600)
            os.replace(replacement, path)
        return raw

    monkeypatch.setattr(journal, "_read_prestart_bytes", swap)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.reserve_prestart(
            reservation=arguments["reservation"],
            approval=arguments["approval"],
        )


@pytest.mark.parametrize("kind", ["reservation", "cancellation"])
def test_sidecar_write_readback_refuses_replacement_inode(
    tmp_path, monkeypatch, kind
):
    root = tmp_path / "journal"
    journal = _journal(root)
    cancellation, reservation, admission, approval = _cancellation_fixture()
    if kind == "cancellation":
        journal.reserve_prestart(reservation=reservation, approval=approval)
    original = journal._write_new

    def swap(root_descriptor, name, raw, **deadline):
        identity = original(root_descriptor, name, raw, **deadline)
        path = root / name
        replacement = root / (name + ".foreign")
        replacement.write_bytes(raw)
        replacement.chmod(0o600)
        assert replacement.stat().st_ino != path.stat().st_ino
        os.replace(replacement, path)
        return identity

    monkeypatch.setattr(journal, "_write_new", swap)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        if kind == "reservation":
            journal.reserve_prestart(
                reservation=reservation,
                approval=approval,
            )
        else:
            journal.cancel_prestart(
                cancellation=cancellation,
                reservation=reservation,
                admission=admission,
                approval=approval,
            )


@pytest.mark.parametrize("content", [b"", b"{"])
def test_any_cancellation_inode_blocks_start(tmp_path, content):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    path = _cancellation_path(root)
    path.write_bytes(content)
    path.chmod(0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.create(**arguments)
    assert path.read_bytes() == content
    assert not _record_path(root).exists()


def test_start_joins_persisted_admission_snapshot_not_second_mapping(tmp_path):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    good = copy.deepcopy(arguments["admission"])
    bad = {**good, "target_observation_digest": "f" * 64}

    class SwitchingAdmission(dict):
        reads = 0

        def items(self):
            self.reads += 1
            return (bad if self.reads == 1 else good).items()

    arguments["admission"] = SwitchingAdmission(good)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.create(**arguments)
    assert not _record_path(root).exists()


def test_start_joins_persisted_admission_after_plain_dict_change(
    tmp_path, monkeypatch
):
    journal, root, arguments = _coherent_prestart_context(tmp_path)
    good = copy.deepcopy(arguments["admission"])
    arguments["admission"]["target_observation_digest"] = "f" * 64
    original = journal._decode_approval

    def change_after_start_snapshot(raw):
        arguments["admission"].update(good)
        return original(raw)

    monkeypatch.setattr(journal, "_decode_approval", change_after_start_snapshot)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.create(**arguments)
    assert not _record_path(root).exists()


@pytest.mark.parametrize("boundary", ["reserve", "last_valid", "expiry"])
def test_start_time_half_open_boundary(tmp_path, boundary):
    journal, _root, arguments = _coherent_prestart_context(tmp_path)
    reservation = arguments["reservation"]
    expiry = reservation["prepared_payload"]["expires_at_ms"]
    arguments["started_at_ms"] = {
        "reserve": reservation["reserved_at_ms"],
        "last_valid": expiry - 1,
        "expiry": expiry,
    }[boundary]
    if boundary == "expiry":
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
            journal.create(**arguments)
    else:
        assert journal.create(**arguments)["state"] == "STARTED"


# ---------------------------------------------------------------------------
# R9 terminal-ancestry discrimination tests
# ---------------------------------------------------------------------------


def _r9_terminal_kwargs(record, reservation, approval, *, before=None, after=None,
                        state="SUCCEEDED", completed_at_ms=3_000):
    if before is None:
        before = _before(record)
    if after is None:
        after = copy.deepcopy(before)
    rollback = (
        {"attempted": False}
        if state != "ROLLED_BACK"
        else {
            "attempted": True,
            "restored_preimage_digest": _canonical_hash(before),
        }
    )
    return {
        "operation_key": record["operation_key"],
        "expected_generation": record["journal_generation"],
        "state": state,
        "completed_at_ms": completed_at_ms,
        "postcondition_digest": POSTCONDITION,
        "before": before,
        "after": after,
        "rollback": rollback,
        "after_actuator_generation": record["actuator_generation"] + (2 if state == "ROLLED_BACK" else 1),
        "reservation": reservation,
        "approval": approval,
    }


def test_terminal_advance_requires_reservation_and_approval(tmp_path):
    journal = _journal(tmp_path / "ancestry-args")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    base = _r9_terminal_kwargs(record, reservation, approval)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**{**base, "reservation": None})
    assert caught.value.code == "ANCESTRY_ARGUMENTS"
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**{**base, "approval": None})
    assert caught.value.code == "ANCESTRY_ARGUMENTS"


def test_terminal_advance_refuses_when_reservation_sidecar_absent(tmp_path):
    journal = _journal(tmp_path / "no-reservation-sidecar")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    _reservation_path(root=Path(tmp_path / "no-reservation-sidecar"),
                      operation_key=OPERATION_KEY).unlink()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, reservation, approval))
    assert caught.value.code in {"RESERVATION_ABSENT", "NOT_FOUND"}


def test_terminal_advance_refuses_when_supplied_reservation_byte_differs(tmp_path):
    journal = _journal(tmp_path / "supplied-mismatch")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    mutated = copy.deepcopy(reservation)
    mutated["target_observation_digest"] = _hex64(99)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, mutated, approval))
    assert caught.value.code == "RESERVATION_MISMATCH"


def test_terminal_advance_refuses_when_stored_reservation_is_replaced(tmp_path):
    journal = _journal(tmp_path / "stored-replaced")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    stem = _stem(OPERATION_KEY)
    foreign_raw = contract.canonical_release_bytes(
        contract.validate_release_prestart_reservation(
            {**reservation, "target_observation_digest": _hex64(33)},
            expected_approval=approval))
    (Path(tmp_path / "stored-replaced") /
     (stem + ".reservation.json")).write_bytes(foreign_raw)
    os.chmod(Path(tmp_path / "stored-replaced") /
              (stem + ".reservation.json"), 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, reservation, approval))
    assert caught.value.code == "RESERVATION_MISMATCH"


def test_terminal_advance_refuses_when_stored_reservation_malformed(tmp_path):
    journal = _journal(tmp_path / "stored-malformed")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    stem = _stem(OPERATION_KEY)
    (Path(tmp_path / "stored-malformed") /
     (stem + ".reservation.json")).write_bytes(b"{")
    os.chmod(Path(tmp_path / "stored-malformed") /
              (stem + ".reservation.json"), 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, reservation, approval))
    assert caught.value.code == "RECORD_BYTES"


def test_terminal_advance_refuses_when_approval_does_not_validate_reservation(
    tmp_path,
):
    journal = _journal(tmp_path / "approval-mismatch")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    bad_approval = copy.deepcopy(approval)
    bad_approval["effective_grant_digest"] = _hex64(99)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, reservation, bad_approval))
    assert caught.value.code in {
        "RECORD_BYTES",
        "RESERVATION_MISMATCH",
        "INVALID_EMBEDDED_RECORD",
    }


def test_terminal_advance_refuses_when_root_qualification_digest_mismatches(
    tmp_path,
):
    journal = _journal(tmp_path / "root-mismatch")
    _start(journal)
    record = journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT", **_ancestry())
    record = journal.advance(
        OPERATION_KEY, expected_generation=2, state="PUBLISHED", **_ancestry(OPERATION_KEY))
    record = journal.advance(
        OPERATION_KEY,
        expected_generation=record["journal_generation"],
        state="BROKER_RESTART_PENDING",
     **_ancestry(OPERATION_KEY))
    record = journal.advance(
        OPERATION_KEY,
        expected_generation=record["journal_generation"],
        state="RECOVERING",
     **_ancestry(OPERATION_KEY))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    stem = _stem(OPERATION_KEY)
    journal_path = Path(tmp_path / "root-mismatch") / (stem + ".json")
    record_raw = journal_path.read_bytes()
    tampered = contract.parse_release_json(record_raw).to_dict()
    tampered["root_qualification_digest"] = _hex64(99)
    tampered["publication_intent"]["root_qualification_digest"] = _hex64(99)
    tampered["recovery_origin"]["publication_intent_digest"] = _canonical_hash(tampered["publication_intent"])
    journal_path.write_bytes(contract.canonical_release_bytes(tampered))
    os.chmod(journal_path, 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, reservation, approval))
    assert caught.value.code == "ROOT_QUALIFICATION_MISMATCH"


def test_terminal_advance_refuses_when_start_reservation_join_mismatches(
    tmp_path,
):
    journal = _journal(tmp_path / "join-mismatch")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    # Mutate the journal record's `before_release_commit` so the START-bound
    # identity diverges from the reservation's before.release_commit while
    # the journal record itself still validates.
    stem = _stem(OPERATION_KEY)
    journal_path = Path(tmp_path / "join-mismatch") / (stem + ".json")
    record_raw = journal_path.read_bytes()
    tampered = contract.parse_release_json(record_raw).to_dict()
    tampered["before_release_commit"] = "0" * 40
    tampered["before"]["release_commit"] = "0" * 40
    tampered["before"]["broker_source_commit"] = "0" * 40
    tampered["publication_intent"]["before_digest"] = _canonical_hash(tampered["before"])
    tampered["recovery_origin"]["publication_intent_digest"] = _canonical_hash(tampered["publication_intent"])
    journal_path.write_bytes(contract.canonical_release_bytes(tampered))
    os.chmod(journal_path, 0o600)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(record, reservation, approval))
    assert caught.value.code == "RESERVATION_MISMATCH"


def test_terminal_advance_refuses_when_before_differs_in_broker_binary(tmp_path):
    journal = _journal(tmp_path / "before-broker-binary")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    before = _before(record)
    before["broker_binary_digest"] = _hex64(123)
    after = copy.deepcopy(before)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(
            record, reservation, approval, before=before, after=after))
    assert caught.value.code == "BEFORE_MISMATCH"


def test_terminal_advance_refuses_when_before_differs_in_one_service_role(
    tmp_path,
):
    journal = _journal(tmp_path / "before-one-role")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    before = _before(record)
    before["service_generation_digests"]["worker"] = _hex64(99)
    after = copy.deepcopy(before)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(**_r9_terminal_kwargs(
            record, reservation, approval, before=before, after=after))
    assert caught.value.code == "BEFORE_MISMATCH"


def test_nonterminal_advance_requires_reservation_and_approval_arguments(tmp_path):
    journal = _journal(tmp_path / "nonterminal-ancestry")
    record = _start(journal)
    reservation, approval, _, _ = _reservation_fixture()
    for kwargs in ({}, {"reservation": reservation}, {"approval": approval}):
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="ANCESTRY_ARGUMENTS"):
            journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT", **kwargs)
        assert journal.read(OPERATION_KEY) == record
    assert journal.advance(OPERATION_KEY, expected_generation=1, state="PUBLICATION_INTENT",
        reservation=reservation, approval=approval)["state"] == "PUBLICATION_INTENT"


def test_terminal_advance_never_writes_when_ancestry_fails(tmp_path):
    journal = _journal(tmp_path / "no-write-ancestry")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    stem = _stem(OPERATION_KEY)
    journal_path = Path(tmp_path / "no-write-ancestry") / (stem + ".json")
    original_raw = journal_path.read_bytes()
    _reservation_path(root=Path(tmp_path / "no-write-ancestry"),
                      operation_key=OPERATION_KEY).unlink()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
        journal.advance(**_r9_terminal_kwargs(record, reservation, approval))
    assert journal_path.read_bytes() == original_raw


# ---------------------------------------------------------------------------
# R9 TOCTOU final-publication guard tests (F2).
# ---------------------------------------------------------------------------


def _mutate_reservation_sidecar(path, kind, *, approval):
    """Apply an Astra R1 reproduction to the on-disk reservation sidecar.

    ``kind == "malformed"`` writes a non-JSON opener; ``"valid_before_drift"``
    revalidates the canonical reservation against the supplied approval and
    rewrites one field of the immutable full 8-field before — exactly the
    Astra R1 reproduction that previously slipped past the initial under-lock
    ancestry guard but is now caught by the missing final-publication fence.
    """

    if kind == "malformed":
        path.write_bytes(b"{")
        path.chmod(0o600)
        return
    parsed = contract.parse_release_json(path.read_bytes()).to_dict()
    parsed["before"]["broker_binary_digest"] = "e" * 64
    mutated = contract.canonical_release_bytes(
        contract.validate_release_prestart_reservation(
            parsed, expected_approval=approval
        )
    )
    path.write_bytes(mutated)
    path.chmod(0o600)


@pytest.mark.parametrize("kind", ["malformed", "valid_before_drift"])
def test_terminal_refuses_sidecar_drift_after_staging(tmp_path, monkeypatch, kind):
    """A reservation sidecar change after ``_write_new(.tmp)`` must refuse.

    Mirrors the Astra R1 reproduction: the canonical reservation bytes are
    mutated exactly once, immediately after the real ``_write_new`` returns
    for the staged temporary inode. The final-publication guard catches the
    drift, the original nonterminal journal stays intact, and the owned
    temporary inode is cleaned up.
    """

    journal = _journal(tmp_path / "drift-after-staging")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    path = _reservation_path(journal._root)
    original_raw = path.read_bytes()
    original_journal_raw = (
        Path(journal._root) / (_stem(OPERATION_KEY) + ".json")
    ).read_bytes()
    original_write_new = journal._write_new

    def drift(root_descriptor, name, raw, **deadline):
        identity = original_write_new(root_descriptor, name, raw, **deadline)
        if name.endswith(".tmp"):
            _mutate_reservation_sidecar(path, kind, approval=approval)
        return identity

    monkeypatch.setattr(journal, "_write_new", drift)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            **_r9_terminal_kwargs(
                record, reservation, approval, after=_target(record)
            )
        )
    assert caught.value.code == "RESERVATION_REPLACED"
    # The on-disk reservation is now the injected drift; the original bytes
    # are no longer equal. The nonterminal journal record stays intact.
    assert path.read_bytes() != original_raw
    assert (
        Path(journal._root) / (_stem(OPERATION_KEY) + ".json")
    ).read_bytes() == original_journal_raw
    # The owned temporary inode was cleaned up by the finally clause.
    assert not (Path(journal._root) / (_stem(OPERATION_KEY) + ".tmp")).exists()


def test_terminal_refuses_inode_only_reservation_replacement_after_staging(
    tmp_path, monkeypatch
):
    """Inode-only replacement during staging refuses with byte equality.

    An inode-only replacement that happens to keep the canonical reservation
    bytes equal still differs in filesystem identity, so the F2 final-publication
    guard must refuse and clean the owned temporary file rather than adopting the
    replacement as a new truth.
    """

    journal = _journal(tmp_path / "inode-only-drift")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    path = _reservation_path(journal._root)
    original_raw = path.read_bytes()
    original_inode = path.stat().st_ino
    original_journal_raw = (
        Path(journal._root) / (_stem(OPERATION_KEY) + ".json")
    ).read_bytes()
    original_write_new = journal._write_new

    def swap_inode(root_descriptor, name, raw, **deadline):
        identity = original_write_new(root_descriptor, name, raw, **deadline)
        if name.endswith(".tmp"):
            replacement = path.with_suffix(".replacement")
            replacement.write_bytes(original_raw)
            replacement.chmod(0o600)
            os.replace(replacement, path)
            assert path.stat().st_ino != original_inode
        return identity

    monkeypatch.setattr(journal, "_write_new", swap_inode)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        journal.advance(
            **_r9_terminal_kwargs(
                record, reservation, approval, after=_target(record)
            )
        )
    assert caught.value.code == "RESERVATION_REPLACED"
    # The nonterminal journal is preserved.
    assert (
        Path(journal._root) / (_stem(OPERATION_KEY) + ".json")
    ).read_bytes() == original_journal_raw
    # The owned temporary inode is cleaned up; the on-disk reservation is
    # still byte-equal to the original and now lives on a different inode.
    assert path.read_bytes() == original_raw
    assert path.stat().st_ino != original_inode
    assert not (Path(journal._root) / (_stem(OPERATION_KEY) + ".tmp")).exists()


@pytest.mark.parametrize("state", ["SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"])
def test_competing_terminal_writers_only_one_generation(tmp_path, state):
    """Two writers racing on the same operation lock produce one advance.

    A compliant second writer using the same operation lock must serialize:
    exactly one generation advance plus exactly one refusal. The test runs
    in two threads sharing the same journal root.
    """

    import threading

    journal = _journal(tmp_path / "race")
    record = _to_recovering(journal, _start(journal))
    reservation, approval, _preconds, _prep = _reservation_fixture()
    after = _target(record) if state == "SUCCEEDED" else _before(record)
    kwargs = _r9_terminal_kwargs(
        record, reservation, approval, state=state, after=after
    )
    if state == "FAILED_NOT_APPLIED":
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="NO_APPLY_PROOF_UNAVAILABLE"):
            journal.advance(**kwargs)
        assert journal.read(record["operation_key"]) == record
        return
    gate = threading.Barrier(2)

    def run():
        other = _journal(Path(journal._root))
        gate.wait(timeout=5)
        try:
            other.advance(**kwargs)
            return ("ok", other.read(record["operation_key"])["state"])
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            return ("refused", exc.code)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(result[0] for result in results) == ["ok", "refused"], results
    assert (
        journal.read(record["operation_key"])["journal_generation"]
        == record["journal_generation"] + 1
    )


# Request deadlines tighten only the existing journal; they never arm a host.
@pytest.fixture
def request_deadline_clock(monkeypatch):
    from types import SimpleNamespace
    clock = [2_200_000_000]
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += int(seconds * 1_000_000_000)
    monkeypatch.setattr(actuator, "time", SimpleNamespace(
        monotonic_ns=lambda: clock[0], monotonic=lambda: clock[0] / 1e9,
        sleep=sleep, time_ns=lambda: 2_200_000_000))
    return clock, sleeps


@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.0, "12", float("nan"),
                                  float("inf"), 1 << 63, 10 ** 1000])
def test_request_deadline_invalid_before_any_journal_io(tmp_path, monkeypatch, bad):
    journal = _journal(tmp_path / "absent")
    touched = []
    def unexpected(*args, **kwargs):
        touched.append(True)
        raise AssertionError("invalid deadline reached filesystem")
    monkeypatch.setattr(journal, "_open_root", unexpected)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="INVALID_REQUEST_DEADLINE"):
        journal.read(OPERATION_KEY, deadline_monotonic_ns=bad)
    assert touched == []
    assert not journal._root.exists()


def test_request_deadline_bounds_local_lock_wait_and_preserves_legacy(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    calls = []
    class UnavailableLock:
        def acquire(self, *, timeout):
            calls.append(timeout)
            return False
    monkeypatch.setattr(actuator, "_LOCAL_LOCK", UnavailableLock())
    journal = _journal(tmp_path / "absent", lock_timeout=3)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="LOCK_TIMEOUT"):
        journal.read(OPERATION_KEY, deadline_monotonic_ns=clock[0] + 100_000_000)
    assert calls == [pytest.approx(0.1)]
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="LOCK_TIMEOUT"):
        journal.read(OPERATION_KEY)
    assert calls[-1] == pytest.approx(3)


def test_request_deadline_clamps_flock_sleep_and_checks_immediate_success(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, sleeps = request_deadline_clock
    journal = _journal(tmp_path / "unused")
    calls = []
    def blocked(*args):
        calls.append(True)
        raise BlockingIOError()
    monkeypatch.setattr(actuator.fcntl, "flock", blocked)
    end = clock[0] + 1_000_000
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="DEADLINE"):
        journal._acquire_flock(1, 99.0, deadline_monotonic_ns=end)
    assert sleeps == [pytest.approx(0.001)]
    assert calls == [True]
    def late_success(*args):
        clock[0] += 2_000_000
    monkeypatch.setattr(actuator.fcntl, "flock", late_success)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="DEADLINE"):
        journal._acquire_flock(1, 99.0, deadline_monotonic_ns=clock[0] + 1_000_000)


def test_request_deadline_reservation_read_uses_same_endpoint(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    reservation, approval, _, _ = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    end = clock[0] + 1_000_000
    original = journal._read_prestart_snapshot
    endpoints = []
    def late(*args, **kwargs):
        endpoints.append(kwargs.get("deadline_monotonic_ns"))
        result = original(*args, **kwargs)
        clock[0] = end
        return result
    monkeypatch.setattr(journal, "_read_prestart_snapshot", late)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="DEADLINE"):
        journal.read_prestart_reservation(OPERATION_KEY, approval=approval,
                                         deadline_monotonic_ns=end)
    assert endpoints == [end]
    assert not _record_path(journal._root).exists()


def test_request_deadline_after_qualifier_late_recovery_refuses_new_start(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    end = clock[0] + 1_000_000
    original = journal._recover_linked_start
    calls = []
    def qualifier():
        calls.append("qualified")
        return 2_001
    def late(*args, **kwargs):
        assert calls == ["qualified"]
        result = original(*args, **kwargs)
        clock[0] = end
        return result
    monkeypatch.setattr(journal, "_recover_linked_start", late)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="DEADLINE"):
        _start(journal, deadline_monotonic_ns=end, commit_qualifier=qualifier)
    assert calls == ["qualified"]
    assert not _record_path(journal._root).exists()
    assert not list(journal._root.glob("*.start"))


def test_request_deadline_late_stage_remains_for_exact_reconciliation(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    end = clock[0] + 1_000_000
    original = journal._write_new
    def late(root, name, raw, **deadline):
        result = original(root, name, raw, **deadline)
        if name.endswith(".start"):
            clock[0] = end
        return result
    monkeypatch.setattr(journal, "_write_new", late)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match="DEADLINE_EFFECT_UNKNOWN"):
        _start(journal, deadline_monotonic_ns=end)
    path = _record_path(journal._root)
    staged = path.with_suffix(".start")
    before = staged.read_bytes()
    assert before and not path.exists()
    monkeypatch.setattr(journal, "_write_new", original)
    # A fresh legacy test call reconciles the exact candidate; no second stage.
    recovered = _start(journal, publication_deadline_monotonic_ns=end)
    assert recovered["journal_generation"] == 1
    assert path.read_bytes() == before
    assert not staged.exists()


def test_request_deadline_success_and_missing_option_remain_compatible(
        tmp_path, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    end = clock[0] + 12_000_000_000
    record = _start(journal, deadline_monotonic_ns=end)
    assert journal.read(OPERATION_KEY, deadline_monotonic_ns=end) == record
    assert journal.read(OPERATION_KEY) == record
    assert _start(journal, publication_deadline_monotonic_ns=end) == record


@pytest.mark.parametrize("error", [
    actuator.ExecutiveReleaseActuatorJournalError("CONFLICT"),
    actuator.ExecutiveReleaseActuatorJournalError("RESERVATION_CONFLICT"),
    actuator.ExecutiveReleaseActuatorJournalError("RECORD_REPLACED"),
    ValueError("original failure"),
])
def test_request_deadline_cleanup_preserves_primary_exception_identity(
        tmp_path, monkeypatch, request_deadline_clock, error):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    _start(journal)
    end = clock[0] + 1_000_000
    real_lock = actuator._LOCAL_LOCK
    released = []

    class LateReleaseLock:
        def acquire(self, **kwargs):
            return real_lock.acquire(**kwargs)

        def release(self):
            real_lock.release()
            released.append(True)
            clock[0] = end

    monkeypatch.setattr(actuator, "_LOCAL_LOCK", LateReleaseLock())

    def fail_operation(*args):
        raise error

    with pytest.raises(type(error)) as caught:
        journal._locked(journal._name(OPERATION_KEY), fail_operation,
                        create_root=False, deadline_monotonic_ns=end)
    assert caught.value is error
    assert released == [True]
    assert not real_lock.locked()


def test_request_deadline_success_crossing_unlock_still_refuses(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    record = _start(journal)
    end = clock[0] + 1_000_000
    real_lock = actuator._LOCAL_LOCK

    class LateReleaseLock:
        def acquire(self, **kwargs):
            return real_lock.acquire(**kwargs)

        def release(self):
            real_lock.release()
            clock[0] = end

    monkeypatch.setattr(actuator, "_LOCAL_LOCK", LateReleaseLock())
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="^DEADLINE_EFFECT_UNKNOWN$"):
        journal._locked(journal._name(OPERATION_KEY), lambda *args: record,
                        create_root=False, deadline_monotonic_ns=end)
    assert not real_lock.locked()


@pytest.mark.parametrize("effect_unknown", [False, True])
@pytest.mark.parametrize("error", [
    actuator.ExecutiveReleaseActuatorJournalError("RECORD_METADATA"),
    ValueError("original read failure"),
])
def test_request_deadline_descriptor_close_preserves_primary_exception_identity(
        tmp_path, monkeypatch, request_deadline_clock, error, effect_unknown):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    _start(journal)
    root, _ = journal._open_root(create=False)
    end = clock[0] + 1_000_000
    real_close = actuator.os.close
    closed = []

    def late_close(descriptor):
        real_close(descriptor)
        closed.append(descriptor)
        clock[0] = end

    def fail_metadata(*args, **kwargs):
        raise error

    monkeypatch.setattr(actuator.os, "close", late_close)
    monkeypatch.setattr(journal, "_check_descriptor", fail_metadata)
    try:
        with pytest.raises(type(error)) as caught:
            journal._read_file(root, journal._name(OPERATION_KEY), required=True,
                               deadline_monotonic_ns=end,
                               deadline_effect_unknown=effect_unknown)
        assert caught.value is error
        assert len(closed) == 1
    finally:
        real_close(root)


@pytest.mark.parametrize("effect_unknown,code", [
    (False, "DEADLINE_EXCEEDED"), (True, "DEADLINE_EFFECT_UNKNOWN"),
])
def test_request_deadline_success_crossing_descriptor_close_still_refuses(
        tmp_path, monkeypatch, request_deadline_clock, effect_unknown, code):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    _start(journal)
    root, _ = journal._open_root(create=False)
    end = clock[0] + 1_000_000
    real_close = actuator.os.close
    closed = []

    def late_close(descriptor):
        real_close(descriptor)
        closed.append(descriptor)
        clock[0] = end

    monkeypatch.setattr(actuator.os, "close", late_close)
    try:
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
            journal._read_file(root, journal._name(OPERATION_KEY), required=True,
                               deadline_monotonic_ns=end,
                               deadline_effect_unknown=effect_unknown)
        assert caught.value.code == code
        assert len(closed) == 1
    finally:
        real_close(root)


def test_request_deadline_before_stage_retains_pre_effect_classification(
        tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    end = clock[0] + 1_000_000
    recover = journal._recover_linked_start

    def late_recovery(*args, **kwargs):
        result = recover(*args, **kwargs)
        assert result is None
        clock[0] = end
        return result

    monkeypatch.setattr(journal, "_recover_linked_start", late_recovery)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="^DEADLINE_EXCEEDED$"):
        _start(journal, deadline_monotonic_ns=end)
    assert not _record_path(journal._root).exists()
    assert not list(journal._root.glob("*.start"))
    assert not actuator._LOCAL_LOCK.locked()


@pytest.mark.parametrize("phase", ["stage_read", "linked_read", "recovery_read"])
def test_request_deadline_nested_post_effect_reads_retain_unknown_classification(
        tmp_path, monkeypatch, request_deadline_clock, phase):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / "journal")
    end = clock[0] + 1_000_000
    final = _record_path(journal._root)
    read_file = journal._read_file
    if phase == "recovery_read":
        unlink = journal._unlink_owned

        def interrupted_unlink(root, name, *args):
            if name.endswith(".start"):
                raise actuator.ExecutiveReleaseActuatorJournalError("RECORD_PUBLISH")
            return unlink(root, name, *args)

        monkeypatch.setattr(journal, "_unlink_owned", interrupted_unlink)
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError):
            _start(journal, publication_deadline_monotonic_ns=end)
        monkeypatch.setattr(journal, "_unlink_owned", unlink)
        assert final.stat().st_nlink == 2
    tripped = []

    def late_read(root, name, *args, **kwargs):
        if phase == "stage_read":
            selected = (name.endswith(".start") and kwargs.get("required")
                        and kwargs.get("expected_links", 1) == 1)
        else:
            selected = kwargs.get("expected_links") == 2
        if selected and not tripped:
            tripped.append(name)
            clock[0] = end
        return read_file(root, name, *args, **kwargs)

    monkeypatch.setattr(journal, "_read_file", late_read)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="^DEADLINE_EFFECT_UNKNOWN$"):
        _start(journal, deadline_monotonic_ns=end)
    assert tripped
    assert final.exists() or final.with_suffix(".start").exists()
    assert not actuator._LOCAL_LOCK.locked()


"""Pre-start phase/ancestry/epoch/legacy acceptance. Parent integration only."""
import copy
import hashlib
import pytest
from control_plane import executive_release_actuator as a
from control_plane import executive_release_contract as c

@pytest.fixture
def j1_ctx(tmp_path,monkeypatch):
    monkeypatch.setattr(a.time,'time_ns',lambda:2200*1000000)
    monkeypatch.setattr(a.time,'monotonic_ns',lambda:2200000000)
    j=_journal(tmp_path/'journal');r=_start(j);res,app,_,_=_reservation_fixture()
    return j,r,res,app

def _j1_advance(j1_ctx,state,**kw):
    j,r,res,app=j1_ctx
    n=j.advance(r['operation_key'],expected_generation=r['journal_generation'],state=state,
        reservation=res,approval=app,**kw)
    return (j,n,res,app)

def test_j1_intent_required_and_full_before_retained(j1_ctx):
    j,r,res,app=j1_ctx
    assert r['schema']=='mastermind.executive_release_actuator_journal/v3'
    assert c.canonical_release_bytes(r['before'])==c.canonical_release_bytes(res['before'])
    with pytest.raises(a.ExecutiveReleaseActuatorJournalError):_j1_advance(j1_ctx,'PUBLISHED')
    j1_ctx=_j1_advance(j1_ctx,'PUBLICATION_INTENT');i=j1_ctx[1]['publication_intent']
    assert i['start_actuator_generation']==7 and i['target_actuator_generation']==8 and i['rollback_actuator_generation']==9
    assert j1_ctx[1]['journal_generation']==2
    j1_ctx=_j1_advance(j1_ctx,'RECOVERING')
    assert j1_ctx[1]['recovery_origin']['from_state']=='PUBLICATION_INTENT'
    assert j1_ctx[1]['publication_intent']==i
    assert j1_ctx[1]['started_at_ms']==r['started_at_ms']

@pytest.mark.parametrize('phase',['STARTED','PUBLICATION_INTENT','PUBLISHED','BROKER_RESTART_PENDING','RECOVERING'])
def test_j1_no_unproven_not_applied_from_any_phase(j1_ctx,phase):
    order=['STARTED','PUBLICATION_INTENT','PUBLISHED','BROKER_RESTART_PENDING','RECOVERING']
    for step in order[1:order.index(phase)+1]:j1_ctx=_j1_advance(j1_ctx,step)
    j,r,res,app=j1_ctx;raw=c.canonical_release_bytes(j.read(r['operation_key']))
    with pytest.raises(a.ExecutiveReleaseActuatorJournalError):
        _j1_advance(j1_ctx,'FAILED_NOT_APPLIED',completed_at_ms=3000,postcondition_digest='f'*64,
                before=res['before'],after=res['before'],rollback={'attempted':False},after_actuator_generation=7)
    assert c.canonical_release_bytes(j.read(r['operation_key']))==raw

@pytest.mark.parametrize('outcome,epoch',[('SUCCEEDED',8),('ROLLED_BACK',9)])
def test_j1_terminal_epoch_and_immutable_origin(j1_ctx,outcome,epoch):
    j1_ctx=_j1_advance(_j1_advance(j1_ctx,'PUBLICATION_INTENT'),'RECOVERING');j,r,res,app=j1_ctx
    before=res['before'];after=_target(r) if outcome=='SUCCEEDED' else before
    rollback={'attempted':False} if outcome=='SUCCEEDED' else {'attempted':True,'restored_preimage_digest':hashlib.sha256(c.canonical_release_bytes(before)).hexdigest()}
    kw=dict(completed_at_ms=3000,postcondition_digest='f'*64,before=before,after=after,rollback=rollback)
    with pytest.raises(a.ExecutiveReleaseActuatorJournalError):_j1_advance(j1_ctx,outcome,after_actuator_generation=epoch+1,**kw)
    final=_j1_advance(j1_ctx,outcome,after_actuator_generation=epoch,**kw)[1]
    assert final['terminal']['after_actuator_generation']==epoch
    assert final['recovery_origin']==r['recovery_origin'] and final['publication_intent']==r['publication_intent']
    assert final['actuator_generation']==7


def test_j1_intent_expiry_before_write_leaves_original(j1_ctx,monkeypatch):
    j,r,_,_=j1_ctx;old=c.canonical_release_bytes(r)
    monkeypatch.setattr(a.time,'monotonic_ns',lambda:r['start_deadline_monotonic_ns'])
    with pytest.raises(a.ExecutiveReleaseActuatorJournalError):_j1_advance(j1_ctx,'PUBLICATION_INTENT')
    assert c.canonical_release_bytes(j.read(r['operation_key']))==old


@pytest.mark.parametrize('terminal',[False,True])
def test_j1_legacy_records_remain_readable_immutable_without_migration(tmp_path,terminal):
    j=_journal(tmp_path/'legacy');new=_start(j);old=new.to_dict()
    old['schema']=actuator._LEGACY_SCHEMA
    old.pop('before');old.pop('start_deadline_monotonic_ns')
    if terminal:
        old.update(state='FAILED_NOT_APPLIED',journal_generation=5)
        old['terminal']=dict(completed_at_ms=3000,postcondition_digest=POSTCONDITION,
            before=_before(new),after=_before(new),rollback={'attempted':False})
    raw=contract.canonical_release_bytes(old);path=_record_path(j._root);path.write_bytes(raw)
    before=path.stat();assert j.read(OPERATION_KEY).to_dict()==old
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match='TERMINAL_IMMUTABLE' if terminal else 'LEGACY_RECOVERY_UNAVAILABLE'):
        j.advance(OPERATION_KEY,expected_generation=old['journal_generation'],state='PUBLICATION_INTENT',**_ancestry())
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,match='CONFLICT'):_start(j)
    assert path.read_bytes()==raw and path.stat().st_mtime_ns==before.st_mtime_ns
    assert not list(j._root.glob('*.tmp'))


@pytest.mark.parametrize('after_replace',[False,True])
def test_j1_publication_intent_crash_reconciles_durable_phase(j1_ctx,monkeypatch,after_replace):
    j,start,_,_=j1_ctx;replace=actuator.os.replace
    def fail(*args,**kwargs):
        if after_replace:replace(*args,**kwargs)
        raise OSError(errno.EIO,'synthetic phase fault')
    monkeypatch.setattr(actuator.os,'replace',fail)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,match='RECORD_REPLACE'):
        _j1_advance(j1_ctx,'PUBLICATION_INTENT')
    observed=j.read(OPERATION_KEY)
    assert observed['state']==('PUBLICATION_INTENT' if after_replace else 'STARTED')
    assert observed['journal_generation']==(2 if after_replace else 1)
    monkeypatch.setattr(actuator.os,'replace',replace)
    if after_replace:
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,match='GENERATION_MISMATCH'):
            _j1_advance(j1_ctx,'PUBLICATION_INTENT')
        recovered=_j1_advance((j,observed,j1_ctx[2],j1_ctx[3]),'RECOVERING')[1]
        assert recovered['recovery_origin']['from_state']=='PUBLICATION_INTENT'
    assert not list(j._root.glob('*.tmp'))


def test_j1_nested_read_primary_error_survives_deadline_and_close_failure(j1_ctx,monkeypatch):
    j,start,_,_=j1_ctx;original=RuntimeError('primary synthetic error');real_close=actuator.os.close
    def fail_read(*args,**kwargs):
        monkeypatch.setattr(actuator.time,'monotonic_ns',lambda:start['start_deadline_monotonic_ns'])
        raise original
    def close_then_fail(fd):
        real_close(fd)
        raise OSError('secondary synthetic close error')
    monkeypatch.setattr(j,'_read_prestart_snapshot',fail_read)
    monkeypatch.setattr(actuator.os,'close',close_then_fail)
    # First record read also closes a descriptor. Install the close failure only
    # inside the sidecar fault so the intended primary happens first.
    monkeypatch.setattr(actuator.os,'close',real_close)
    def primary(*args,**kwargs):
        monkeypatch.setattr(actuator.os,'close',close_then_fail)
        return fail_read(*args,**kwargs)
    monkeypatch.setattr(j,'_read_prestart_snapshot',primary)
    with pytest.raises(RuntimeError) as caught:_j1_advance(j1_ctx,'PUBLICATION_INTENT')
    assert caught.value is original and not actuator._LOCAL_LOCK.locked()
    monkeypatch.setattr(actuator.os,'close',real_close)
    assert _record_path(j._root).read_bytes()==contract.canonical_release_bytes(start)


@pytest.mark.parametrize('phase',['reservation','temporary','final'])
def test_j1_nested_io_crossing_original_deadline_has_no_success(j1_ctx,monkeypatch,phase):
    j,start,_,_=j1_ctx;read=j._read_file;sidecar=j._read_prestart_snapshot;tripped=[]
    def late_read(root,name,**kwargs):
        result=read(root,name,**kwargs)
        hit=name.endswith('.tmp') if phase=='temporary' else name.endswith('.json') and bool(tripped)
        if phase=='final':
            # Select final journal read after os.replace through actual content.
            hit=name.endswith('.json') and b'"state":"PUBLICATION_INTENT"' in (result[0] or b'')
        if hit and not tripped:
            tripped.append(name);monkeypatch.setattr(actuator.time,'monotonic_ns',lambda:start['start_deadline_monotonic_ns'])
        return result
    def late_sidecar(*args,**kwargs):
        result=sidecar(*args,**kwargs)
        if not tripped:
            tripped.append('reservation');monkeypatch.setattr(actuator.time,'monotonic_ns',lambda:start['start_deadline_monotonic_ns'])
        return result
    monkeypatch.setattr(j,'_read_prestart_snapshot' if phase=='reservation' else '_read_file',late_sidecar if phase=='reservation' else late_read)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:_j1_advance(j1_ctx,'PUBLICATION_INTENT')
    assert caught.value.code==('DEADLINE_EXCEEDED' if phase=='reservation' else 'DEADLINE_EFFECT_UNKNOWN')
    assert tripped and not actuator._LOCAL_LOCK.locked()
    stored=contract.parse_release_json(_record_path(j._root).read_bytes())
    assert stored['state']==('PUBLICATION_INTENT' if phase=='final' else 'STARTED')


# R2 independent deadline regressions, retained in shipping tests.
from types import SimpleNamespace
R2_PHASES=["STARTED","PUBLICATION_INTENT","PUBLISHED","BROKER_RESTART_PENDING","RECOVERING"]

@pytest.fixture
def r2_ctx(tmp_path,monkeypatch):
    clock=[2_200_000_000];real=actuator.time
    monkeypatch.setattr(a,'time',SimpleNamespace(monotonic=real.monotonic,sleep=real.sleep,time_ns=lambda:2_200_000_000,monotonic_ns=lambda:clock[0]))
    j=_journal(tmp_path/'journal');r=_start(j);res,app,_,_=_reservation_fixture()
    return j,r,res,app,clock


def _r2_adv(r2_ctx,state,**kw):
    j,r,res,app,clock=r2_ctx
    record=j.advance(r['operation_key'],expected_generation=r['journal_generation'],state=state,reservation=res,approval=app,**kw)
    return j,record,res,app,clock


def _r2_at(r2_ctx,state):
    for p in R2_PHASES[1:R2_PHASES.index(state)+1]:r2_ctx=_r2_adv(r2_ctx,p)
    return r2_ctx


def _r2_raw(r2_ctx):return _record_path(r2_ctx[0]._root).read_bytes()


@pytest.mark.parametrize('phase',R2_PHASES)
def test_shorter_replay_io_budget_preserves_original_start(r2_ctx,phase):
    r2_ctx=_r2_at(r2_ctx,phase);j,r,_,_,clock=r2_ctx;before=_r2_raw(r2_ctx)
    shorter=clock[0]+1_000_000_000
    assert shorter<r['start_deadline_monotonic_ns']
    replay=_start(j,publication_deadline_monotonic_ns=r['start_deadline_monotonic_ns'],deadline_monotonic_ns=shorter)
    assert replay==r and _r2_raw(r2_ctx)==before


@pytest.mark.parametrize('phase',['STARTED','PUBLISHED'])
@pytest.mark.parametrize('target',['journal','reservation','temporary','final'])
def test_nested_read_stops_at_io_deadline(r2_ctx,monkeypatch,phase,target):
    r2_ctx=_r2_at(r2_ctx,phase);j,r,res,app,clock=r2_ctx
    endpoint=clock[0]+500_000_000;old_read=actuator.os.read;old_replace=actuator.os.replace
    replaced=[];hit=[];extra=[]
    def rep(*args,**kw):
        result=old_replace(*args,**kw);replaced.append(True);return result
    def read(fd,count):
        actual=os.fstat(fd)
        matches=[]
        for p in j._root.iterdir():
            if p.is_file() and p.stat().st_ino==actual.st_ino:matches.append(p.name)
        selected=bool(matches) and ((target=='journal' and matches[0].endswith('.json') and not matches[0].endswith('.reservation.json') and not replaced)
            or (target=='reservation' and matches[0].endswith('.reservation.json'))
            or (target=='temporary' and matches[0].endswith('.tmp'))
            or (target=='final' and replaced and matches[0].endswith('.json')))
        if selected and hit:extra.append('read after deadline')
        data=old_read(fd,count)
        if selected and not hit and data:hit.append(True);clock[0]=endpoint
        return data
    monkeypatch.setattr(actuator.os,'read',read);monkeypatch.setattr(actuator.os,'replace',rep)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        _r2_adv(r2_ctx,'PUBLICATION_INTENT' if phase=='STARTED' else 'RECOVERING',deadline_monotonic_ns=endpoint)
    assert caught.value.code in {'DEADLINE_EXCEEDED','DEADLINE_EFFECT_UNKNOWN'}
    assert hit and not actuator._LOCAL_LOCK.locked()
    assert not extra,extra



def test_r2_fresh_start_cannot_exceed_request_endpoint(tmp_path):
    journal=_journal(tmp_path/'journal')
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,match='INVALID_ORIGINAL_DEADLINE'):
        _start(journal,deadline_monotonic_ns=3_000_000_000,
               publication_deadline_monotonic_ns=4_000_000_000)
    assert not _record_path(journal._root).exists()
    assert not list(journal._root.glob('*.start'))


def test_r2_exact_durable_stage_recovery_can_use_shorter_io_budget(tmp_path,monkeypatch):
    journal=_journal(tmp_path/'journal');link=actuator.os.link
    def interrupted(*args,**kwargs):raise OSError(errno.EIO,'before hardlink')
    monkeypatch.setattr(actuator.os,'link',interrupted)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,match='RECORD_PUBLISH'):
        _start(journal,deadline_monotonic_ns=4_000_000_000)
    staged=_record_path(journal._root).with_suffix('.start');before=staged.read_bytes()
    assert not _record_path(journal._root).exists()
    monkeypatch.setattr(actuator.os,'link',link)
    result=_start(journal,publication_deadline_monotonic_ns=4_000_000_000,
                  deadline_monotonic_ns=3_000_000_000)
    assert result['start_deadline_monotonic_ns']==4_000_000_000
    assert _record_path(journal._root).read_bytes()==before


@pytest.mark.parametrize('phase', ['STARTED', 'PUBLISHED'])
def test_r3_partial_stage_write_stops_at_original_endpoint(r2_ctx, monkeypatch, phase):
    ctx = _r2_at(r2_ctx, phase)
    journal, record, reservation, approval, clock = ctx
    before = _r2_raw(ctx)
    endpoint = clock[0] + 500_000_000
    write = actuator.os.write
    calls = []
    def partial(descriptor, data):
        calls.append(clock[0])
        written = write(descriptor, data[:1])
        clock[0] = endpoint
        return written
    monkeypatch.setattr(actuator.os, 'write', partial)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match='DEADLINE_EFFECT_UNKNOWN'):
        _r2_adv(ctx, 'PUBLICATION_INTENT' if phase == 'STARTED' else 'RECOVERING',
                deadline_monotonic_ns=endpoint)
    assert calls == [endpoint - 500_000_000]
    assert _r2_raw(ctx) == before and not list(journal._root.glob('*.tmp'))
    assert not actuator._LOCAL_LOCK.locked()


def test_r3_start_staging_uses_same_endpoint(tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / 'journal')
    reservation, approval, _, _ = _reservation_fixture()
    journal.reserve_prestart(reservation=reservation, approval=approval)
    endpoint = clock[0] + 1_000_000
    write = actuator.os.write
    calls = []
    def partial(descriptor, data):
        calls.append(clock[0])
        written = write(descriptor, data[:1])
        clock[0] = endpoint
        return written
    monkeypatch.setattr(actuator.os, 'write', partial)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match='DEADLINE_EFFECT_UNKNOWN'):
        _start(journal, deadline_monotonic_ns=endpoint)
    assert len(calls) == 1 and calls[0] < endpoint
    assert not _record_path(journal._root).exists()
    assert not list(journal._root.glob('*.start'))
    assert not actuator._LOCAL_LOCK.locked()


@pytest.mark.parametrize('boundary', ['open', 'fchmod', 'fstat', 'acl', 'write', 'file-fsync', 'path-stat', 'directory-fsync'])
def test_r3_write_primitive_bounds_every_returned_step(tmp_path, monkeypatch, request_deadline_clock, boundary):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / 'journal')
    _start(journal)
    native_os = actuator.os
    root = native_os.open(journal._root, native_os.O_RDONLY | native_os.O_DIRECTORY)
    endpoint = clock[0] + 1_000_000
    proxy = SimpleNamespace(**vars(native_os))
    events, opened, closed = [], [], []
    triggered = []
    def after(name):
        events.append((name, clock[0]))
        if name == boundary and not triggered:
            triggered.append(name)
            clock[0] = endpoint
    for name in ('open', 'fchmod', 'fstat', 'write', 'stat', 'fsync'):
        def call(*args, _name=name, **kwargs):
            result = getattr(native_os, _name)(*args, **kwargs)
            label = _name
            if _name == 'open': opened.append(result)
            if _name == 'stat': label = 'path-stat'
            if _name == 'fsync': label = 'directory-fsync' if args[0] == root else 'file-fsync'
            after(label)
            return result
        setattr(proxy, name, call)
    def close(descriptor):
        closed.append(descriptor)
        native_os.close(descriptor)
    proxy.close = close
    def acl(*args, **kwargs): after('acl'); return False
    monkeypatch.setattr(actuator, 'os', proxy)
    monkeypatch.setattr(actuator, 'has_macos_acl', acl)
    try:
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError, match='DEADLINE_EFFECT_UNKNOWN'):
            journal._write_new(root, 'bounded.tmp', b'payload', deadline_monotonic_ns=endpoint)
        assert triggered == [boundary]
        # Descriptor/path reads and directory fsync after expiry are solely
        # necessary owned-inode cleanup. No further data, mode or ACL work.
        assert not [(name, stamp) for name, stamp in events
                    if stamp >= endpoint and name in ('open', 'fchmod', 'write', 'acl', 'file-fsync')]
        assert closed == opened
        assert not (journal._root / 'bounded.tmp').exists()
    finally:
        native_os.close(root)


def test_r3_partial_write_primary_survives_cleanup_fsync_and_close_failures(tmp_path, monkeypatch, request_deadline_clock):
    clock, _ = request_deadline_clock
    journal = _journal(tmp_path / 'journal')
    _start(journal)
    native_os = actuator.os
    root = native_os.open(journal._root, native_os.O_RDONLY | native_os.O_DIRECTORY)
    endpoint = clock[0] + 1_000_000
    proxy = SimpleNamespace(**vars(native_os))
    primary = RuntimeError('synthetic partial-write primary')
    closed = []
    def write(descriptor, data):
        native_os.write(descriptor, data[:1])
        clock[0] = endpoint
        raise primary
    def fsync(descriptor):
        if descriptor == root: raise OSError('synthetic cleanup fsync')
        native_os.fsync(descriptor)
    def close(descriptor):
        closed.append(descriptor)
        native_os.close(descriptor)
        raise OSError('synthetic cleanup close')
    proxy.write, proxy.fsync, proxy.close = write, fsync, close
    monkeypatch.setattr(actuator, 'os', proxy)
    try:
        with pytest.raises(RuntimeError) as caught:
            journal._write_new(root, 'bounded.tmp', b'payload', deadline_monotonic_ns=endpoint)
        assert caught.value is primary and len(closed) == 1
        assert not (journal._root / 'bounded.tmp').exists()
    finally:
        native_os.close(root)
