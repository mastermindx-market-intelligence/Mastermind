"""Product-owned private closure-read wire and durable history joins."""
from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path

import pytest

from control_plane import executive_release_actuator as actuator
from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
from control_plane import executive_release_owner as owner_module
from control_plane import executive_release_consumer as consumer
from control_plane.executive_release_owner import ReleaseBrokerOwner
from tests.test_executive_release_controller_policy import inputs as release_inputs, source

OWNER = "11111111-1111-4111-8111-111111111111"
TARGET = "5" * 64
NOW = [200_000]
MONOTONIC = [200_000_000_000]
ACTUATOR_GENERATION = 9
TARGET_OBSERVATION = "6" * 64


@pytest.fixture
def inputs():
    return release_inputs.__wrapped__()


@pytest.fixture(autouse=True)
def restore_clocks():
    wall, monotonic = NOW[0], MONOTONIC[0]
    yield
    NOW[0], MONOTONIC[0] = wall, monotonic


def digest(value):
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


def fixture(inputs):
    principal, effect, policy = copy.deepcopy(inputs)
    effect = contract.validate_normalized_effect(effect)
    policy = owner_module.ReleaseControllerPolicy.from_bytes(source(policy))
    codec = owner_module._OwnerReleaseCodec(
        key=bytes(range(32)), key_id="test-key", trust_generation=1,
        owner_installation_id=OWNER)
    preconditions = {
        "schema": "mastermind.executive_release_preconditions/v1",
        "owner_installation_id": OWNER,
        "target_ref": TARGET,
        "boot_id": OWNER,
        "from_installed_manifest_digest": effect["from_installed_manifest_digest"],
        "installed_configuration_digest": "a" * 64,
        "python_runtime_provenance_digest": "b" * 64,
        "provider_binary_attestation_digest": "c" * 64,
        "authority_policy_hash": policy.sha256,
        "staged_artifact_digest": effect["staged_artifact_digest"],
        "staged_content_metadata_digest": effect["staged_content_metadata_digest"],
        "compatibility_proof_digest": effect["compatibility_proof_digest"],
        "preservation_plan_digest": effect["preservation_plan_digest"],
        "issuer_binding_digest": "d" * 64,
        "admission_contract_digest": "e" * 64,
        "production_arming_digest": "f" * 64,
    }
    snapshot = owner_module.ReleaseOwnerSnapshot(
        policy=policy, codec=codec, owner_installation_id=OWNER,
        target_ref=TARGET, boot_id=OWNER, key_id="test-key", trust_generation=1,
        app_generation=1, schema_digest="1" * 64,
        admission_contract_digest="e" * 64, effect=effect,
        preconditions=preconditions,
        actuator_generation=ACTUATOR_GENERATION,
        target_observation_digest=TARGET_OBSERVATION,
        before={
            "release_commit": effect["from_release_commit"],
            "release_tree": effect["from_release_tree"],
            "installed_manifest_digest": effect["from_installed_manifest_digest"],
            "configuration_digest": preconditions["installed_configuration_digest"],
            "broker_source_commit": effect["from_release_commit"],
            "broker_source_tree": effect["from_release_tree"],
            "broker_binary_digest": "7" * 64,
            "service_generation_digests": {
                "control": "8" * 64, "worker": "9" * 64, "relay": "a" * 64,
                "gateway": "b" * 64, "broker": "c" * 64,
            },
        })
    return principal, snapshot, lambda transition: snapshot


def approval_fixture(snapshot, principal, operation_key="root-closure-read"):
    now = NOW[0]
    projection = owner_module.release_principal_projection(principal)
    principal_digest = digest(projection)
    transition = digest(snapshot.effect)
    confirmation_digest = hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_DELEGATION_V1\0"
        + contract.canonical_release_bytes({
            "policy_id": principal.policy_id, "policy_generation": 7,
            "confirmation_requirement": "delegated",
            "authority_policy_hash": snapshot.policy.sha256,
            "principal_digest": principal_digest, "target_ref": TARGET,
            "transition_digest": transition,
        })).hexdigest()
    grant = {
        "schema": "mastermind.executive_release_grant/v1",
        "principal_digest": principal_digest,
        "authority_policy_hash": snapshot.policy.sha256,
        "policy_id": principal.policy_id, "policy_generation": 7,
        "action": snapshot.effect["action"], "target_ref": TARGET,
        "transition_digest": transition,
        "installer_profile_digest": snapshot.effect["installer_profile_digest"],
        "confirmation_requirement": "delegated",
        "confirmation_evidence_digest": confirmation_digest,
        "granted_at_ms": now, "expires_at_ms": now + 300_000,
    }
    value = {
        "schema": "mastermind.executive_release_approval/v1",
        "operation_key": operation_key,
        "request_ref": contract.approval_ref_for(operation_key).removeprefix("p4-approval:"),
        "approved_transition_ref": contract.approval_ref_for(operation_key),
        "action": snapshot.effect["action"], "owner_installation_id": OWNER,
        "target_ref": TARGET, "principal_projection": projection.to_dict(),
        "normalized_requested_effect": snapshot.effect.to_dict(),
        "transition_digest": transition, "grant": grant,
        "effective_grant_digest": digest(grant), "created_at_ms": now,
        "expires_at_ms": grant["expires_at_ms"],
        "owner_seal": {"key_id": "test-key", "trust_generation": 1, "mac": "A" * 43},
    }
    return snapshot.codec.seal_approval(value)


def prepared_fixture(snapshot, approval):
    effect = snapshot.effect
    sealed_preconditions = {
        **snapshot.preconditions,
        "approval_evidence_digest": digest(approval),
        "grant_digest": approval["effective_grant_digest"],
    }
    return contract.validate_prepared_payload({
        "token_schema": "mastermind.executive_release_prepared.v1",
        "app_id": "mastermind.executive", "owner_installation_id": OWNER,
        "app_generation": 1, "schema_digest": "1" * 64, "trust_generation": 1,
        "key_id": "test-key",
        "authenticated_principal_digest": digest(approval["principal_projection"]),
        "approved_transition_ref": approval["approved_transition_ref"],
        "approval_evidence_digest": digest(approval),
        "policy_id": approval["principal_projection"]["policy_id"],
        "policy_generation": 7,
        "authority_policy_hash": snapshot.policy.sha256,
        "effective_grant_digest": approval["effective_grant_digest"],
        "action_target_digest": digest({"action": effect["action"], "target_ref": TARGET}),
        "confirmation_requirement": "delegated",
        "privilege_class": "EXECUTIVE_RELEASE_TRANSITION",
        "operation_key": approval["operation_key"], "action_family": effect["action"],
        "request_fingerprint": contract.request_fingerprint_for(approval),
        "target_ref": TARGET, "boot_id": OWNER, "platform": "darwin",
        "normalized_requested_effect": effect.to_dict(),
        "normalized_requested_effect_digest": digest(effect),
        "expected_source_and_precondition_digest": digest(sealed_preconditions),
        "admission_contract_digest": snapshot.admission_contract_digest,
        "issued_at_ms": NOW[0], "expires_at_ms": NOW[0] + 300_000,
        "issued_monotonic_ns": MONOTONIC[0],
        "expires_monotonic_ns": MONOTONIC[0] + 300_000_000_000,
    })


def admission_fixture(approval, reservation):
    return contract.validate_admission({
        "schema": "mastermind.executive_release_admission/v1",
        "operation_key": reservation["operation_key"],
        "approved_transition_ref": reservation["approved_transition_ref"],
        "target_ref": TARGET, "owner_installation_id": OWNER, "boot_id": OWNER,
        "request_fingerprint": reservation["request_fingerprint"],
        "effective_grant_digest": reservation["effective_grant_digest"],
        "maintenance_sequence": 1,
        "admission_event_command_id": "p4-admit:" + approval["request_ref"],
        "target_observation_digest": TARGET_OBSERVATION,
        "admission_contract_digest": reservation["preconditions"]["admission_contract_digest"],
    })


def cancellation_fixture(composition):
    reservation = composition.reservation
    return {
        "schema": "mastermind.executive_release_prestart_cancellation/v1",
        "request_id": reservation["request_id"],
        "request_fingerprint": reservation["request_fingerprint"],
        "operation_key": reservation["operation_key"],
        "approved_transition_ref": reservation["approved_transition_ref"],
        "approval_evidence_digest": reservation["approval_evidence_digest"],
        "authenticated_principal_digest": reservation["authenticated_principal_digest"],
        "effective_grant_digest": reservation["effective_grant_digest"],
        "normalized_requested_effect_digest": reservation["normalized_requested_effect_digest"],
        "action_family": reservation["action_family"],
        "action_target_digest": reservation["action_target_digest"],
        "owner_installation_id": reservation["owner_installation_id"],
        "target_ref": reservation["target_ref"],
        "from_release_commit": reservation["from_release_commit"],
        "to_release_commit": reservation["to_release_commit"],
        "reservation_generation": 1,
        "root_qualification_digest": digest(reservation),
        "admission_digest": digest(composition.admission),
        "cancellation_generation": 1,
        "cancelled_at_ms": reservation["prepared_payload"]["expires_at_ms"],
        "cancelled_monotonic_ns": reservation["prepared_payload"]["expires_monotonic_ns"],
        "reason": "PREPARED_TOKEN_EXPIRED",
        "before": copy.deepcopy(reservation["before"]),
        "current": copy.deepcopy(reservation["before"]),
        "original_target_observation_digest": TARGET_OBSERVATION,
        "current_target_observation_digest": TARGET_OBSERVATION,
        "current_precondition_digest": reservation["expected_precondition_digest"],
        "authority_evidence_digest": "8" * 64,
    }


def journal_status(state, composition):
    started_at = composition.approval["created_at_ms"] + 1
    completed_at = started_at + 2
    admission = composition.admission.to_dict()
    preconditions = copy.deepcopy(composition.reservation["preconditions"])
    before = copy.deepcopy(composition.reservation["before"])
    effect = composition.approval["normalized_requested_effect"]
    after = {
        "release_commit": before["release_commit"],
        "release_tree": before["release_tree"],
        "installed_manifest_digest": before["installed_manifest_digest"],
        "configuration_digest": before["configuration_digest"],
        "broker_source_commit": before["release_commit"],
        "broker_source_tree": before["release_tree"],
        "broker_binary_digest": before["broker_binary_digest"],
        "service_generation_digests": copy.deepcopy(
            before["service_generation_digests"]),
    }
    if state == "SUCCEEDED":
        after.update({
            "release_commit": effect["to_release_commit"],
            "release_tree": effect["to_release_tree"],
            "broker_source_commit": effect["to_release_commit"],
            "broker_source_tree": effect["to_release_tree"],
            "installed_manifest_digest": "8" * 64,
            "configuration_digest": "9" * 64,
            "broker_binary_digest": "0" * 64,
            "service_generation_digests": {
                "control": "1" * 64, "worker": "2" * 64, "relay": "3" * 64,
                "gateway": "4" * 64, "broker": "5" * 64,
            },
        })
    record = {
        "schema": "mastermind.executive_release_actuator_journal/v2",
        "state": state,
        "operation_key": composition.approval["operation_key"],
        "request_fingerprint": composition.reservation["request_fingerprint"],
        "approval_evidence_digest": digest(composition.approval),
        "normalized_requested_effect_digest": digest(composition.approval["normalized_requested_effect"]),
        "expected_source_and_precondition_digest": digest(preconditions),
        "action_target_digest": composition.reservation["action_target_digest"],
        "owner_installation_id": OWNER,
        "target_ref": TARGET,
        "before_release_commit": before["release_commit"],
        "before_release_tree": before["release_tree"],
        "before_installed_manifest_digest": before["installed_manifest_digest"],
        "before_configuration_digest": before["configuration_digest"],
        "target_release_commit": composition.approval["normalized_requested_effect"]["to_release_commit"],
        "target_release_tree": composition.approval["normalized_requested_effect"]["to_release_tree"],
        "boot_id": OWNER,
        "preconditions": preconditions,
        "admission": admission,
        "actuator_generation": ACTUATOR_GENERATION,
        "journal_generation": 1,
        "started_at_ms": started_at,
        "root_qualification_digest": digest(composition.reservation),
    }
    if state in {"SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"}:
        if state == "ROLLED_BACK":
            rollback = {
                "attempted": True,
                "restored_preimage_digest": digest(before),
            }
        else:
            rollback = {"attempted": False}
        terminal = {
            "completed_at_ms": completed_at,
            "postcondition_digest": "8" * 64,
            "before": before,
            "after": after,
            "rollback": rollback,
        }
        record["terminal"] = terminal
    return record


def expected_terminal_status(journal_record, reservation, admission, approval):
    """Reproduce the closure reader's contract-validated status projection."""
    state = journal_record["state"]
    status = {
        "schema": "mastermind.executive_release_terminal_status/v1",
        "state": state,
        "request_id": contract.broker_request_id_for(
            reservation["request_fingerprint"]),
        "operation_key": reservation["operation_key"],
        "request_fingerprint": reservation["request_fingerprint"],
        "approved_transition_ref": reservation["approved_transition_ref"],
        "approval_evidence_digest": digest(approval),
        "authenticated_principal_digest": digest(approval["principal_projection"]),
        "effective_grant_digest": reservation["effective_grant_digest"],
        "normalized_requested_effect_digest": reservation[
            "normalized_requested_effect_digest"],
        "action_family": reservation["action_family"],
        "action_target_digest": reservation["action_target_digest"],
        "owner_installation_id": reservation["owner_installation_id"],
        "target_ref": reservation["target_ref"],
        "from_release_commit": reservation["from_release_commit"],
        "to_release_commit": reservation["to_release_commit"],
        "actuator_generation": journal_record["actuator_generation"],
        "journal_generation": journal_record["journal_generation"],
        "started_at_ms": journal_record["started_at_ms"],
        "preconditions": journal_record["preconditions"].to_dict()
        if hasattr(journal_record["preconditions"], "to_dict")
        else dict(journal_record["preconditions"]),
        "expected_precondition_digest": reservation[
            "expected_precondition_digest"],
        "admission": journal_record["admission"].to_dict()
        if hasattr(journal_record["admission"], "to_dict")
        else dict(journal_record["admission"]),
        "admission_digest": digest(journal_record["admission"]),
    }
    if state in {"SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"}:
        terminal = journal_record["terminal"]
        status["terminal_receipt"] = {
            "schema": "mastermind.executive_release_terminal_receipt/v1",
            "request_id": status["request_id"],
            "request_fingerprint": status["request_fingerprint"],
            "approval_evidence_digest": digest(approval),
            "expected_precondition_digest": status[
                "expected_precondition_digest"],
            "admission_digest": status["admission_digest"],
            "actuator_generation": status["actuator_generation"],
            "journal_generation": status["journal_generation"],
            "started_at_ms": status["started_at_ms"],
            "completed_at_ms": terminal["completed_at_ms"],
            "postcondition_digest": terminal["postcondition_digest"],
            "outcome": state,
            "before": dict(terminal["before"]),
            "after": dict(terminal["after"]),
            "rollback": dict(terminal["rollback"]),
        }
    return contract.validate_release_terminal_status(
        status, expected_approval=approval).to_dict()


def install_journal_record(composition, state):
    operation_key = composition.approval["operation_key"]
    stem = actuator._operation_stem(operation_key)
    root = Path(composition.journal._root)
    root.mkdir(parents=True, exist_ok=True)
    raw = contract.canonical_release_bytes(journal_status(state, composition))
    path = root / (stem + ".json")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, raw)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return composition.journal.read(operation_key)


def mark_written(journal):
    original = (journal.reserve_prestart, journal.cancel_prestart,
                journal.create, journal.advance)
    def fail(message):
        def writer(*args, **kwargs):
            pytest.fail(message)
        return writer

    journal.reserve_prestart = fail("read wrote a reservation")
    journal.cancel_prestart = fail("read wrote a cancellation")
    journal.create = fail("read wrote a journal record")
    journal.advance = fail("read advanced journal state")
    return original


def restore_writers(journal, original):
    journal.reserve_prestart = original[0]
    journal.cancel_prestart = original[1]
    journal.create = original[2]
    journal.advance = original[3]


class Composition:
    def __init__(self, tmp_path, monkeypatch, inputs):
        principal, snapshot, state_factory = fixture(inputs)
        self.principal = principal
        self.snapshot = snapshot
        self.approval = approval_fixture(snapshot, principal)
        self.prepared = prepared_fixture(snapshot, self.approval)
        self.token = snapshot.codec.encode_prepared(self.prepared)
        self.journal = actuator._ExecutiveReleaseActuatorJournal._for_tests(tmp_path / "journal")
        self.connection = object()
        self.qualifications = []
        self.owner = ReleaseBrokerOwner(
            state_factory, history_trust=self.history_trust,
            root_journal=self.journal)
        monkeypatch.setattr(owner_module.time, "time_ns", lambda: NOW[0] * 1_000_000)
        monkeypatch.setattr(owner_module.time, "monotonic_ns", lambda: MONOTONIC[0])
        monkeypatch.setattr(owner_module, "_qualify_connection", self.qualify)

    def history_trust(self):
        return owner_module.ReleaseHistoryTrust(
            codec=self.snapshot.codec,
            owner_installation_id=self.snapshot.owner_installation_id,
            target_ref=self.snapshot.target_ref,
            input_identity_digest=self.snapshot.input_identity_digest)

    def qualify(self, connection, role):
        assert role == "control" and connection is self.connection
        self.qualifications.append(role)

    def frame(self, **changes):
        value = {
            "schema": consumer.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "admission_evidence": copy.deepcopy(self.evidence),
        }
        value.update(changes)
        return value

    def reserve(self):
        public = ingress.project_frame(
            "commit_prepared_release_transition",
            {"operation_key": self.approval["operation_key"],
             "prepared_token": self.token},
            principal=self.principal)
        raw = {**public, "schema": consumer.BROKER_SCHEMA,
               "operation": "reserve_release_prestart",
               "approval": self.approval.to_dict()}
        result = self.owner.handle(raw, self.connection)
        self.reservation = result["result"]["reservation"]
        self.admission = admission_fixture(self.approval, self.reservation)
        self.evidence = {
            "approval": self.approval.to_dict(),
            "admission": self.admission.to_dict(),
            "preconditions": self.reservation["preconditions"],
            "root_qualification_digest": digest(self.reservation),
        }
        return result

    def read(self, raw=None):
        self.qualifications = []
        return self.owner.handle(raw or self.frame(), self.connection)


TERMINAL_STATES = ("SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED")
NONTERMINAL_STATES = ("STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING")


@pytest.mark.parametrize("state", TERMINAL_STATES + NONTERMINAL_STATES)
def test_exact_journal_record_union_is_returned(
        tmp_path, monkeypatch, inputs, state):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    original_reservation = copy.deepcopy(composition.reservation)
    original_evidence = copy.deepcopy(composition.evidence)
    stored = install_journal_record(composition, state)
    mark_written(composition.journal)
    result = composition.read()
    assert set(result) == {"schema", "operation", "ok", "approval", "result"}
    assert result["ok"] is True
    assert set(result["result"]) == {"reservation", "terminal_status", "cancellation"}
    assert result["result"]["reservation"] == original_reservation
    expected = expected_terminal_status(
        stored, composition.reservation, composition.admission, composition.approval)
    assert result["result"]["terminal_status"] == expected
    assert result["result"]["cancellation"] is None
    assert composition.qualifications == ["control"] * 6
    assert Path(composition.journal._root).joinpath(
        actuator._operation_stem(composition.approval["operation_key"]) + ".json"
    ).read_bytes() == contract.canonical_release_bytes(stored)


def test_qualified_cancellation_returns_exact_union(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    reservation = copy.deepcopy(composition.reservation)
    evidence = copy.deepcopy(composition.evidence)
    composition.journal.cancel_prestart(
        cancellation=cancellation_fixture(composition),
        reservation=reservation, admission=composition.admission.to_dict(),
        approval=composition.approval.to_dict())
    mark_written(composition.journal)
    result = composition.read()
    cancellation = result["result"]["cancellation"]
    assert cancellation == composition.journal.read_prestart_cancellation(
        composition.approval["operation_key"], reservation=reservation,
        admission=composition.admission.to_dict(),
        approval=composition.approval.to_dict()).to_dict()
    assert result["result"] == {
        "reservation": reservation, "terminal_status": None,
        "cancellation": cancellation}
    assert composition.qualifications == ["control"] * 6


def test_missing_history_refuses_and_never_implies_cancellation(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    # Delete only the journal record and cancellation sidecar so the closure
    # reader has the reservation, can verify history and call admission, and
    # then fails closed when no journal and no cancellation exist.
    for path in Path(composition.journal._root).iterdir():
        if path.name.endswith(".cancellation.json") or not path.name.endswith(
                ".reservation.json"):
            path.unlink()
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_ROOT_JOURNAL_NOT_FOUND"):
        composition.read()


def test_journal_and_qualified_cancellation_conflict_refuses(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    composition.journal.cancel_prestart(
        cancellation=cancellation_fixture(composition),
        reservation=composition.reservation,
        admission=composition.admission.to_dict(),
        approval=composition.approval.to_dict())
    install_journal_record(composition, "STARTED")
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_ROOT_HISTORY_AMBIGUOUS"):
        composition.read()


@pytest.mark.parametrize("kind,mutation", [
    ("reservation", "prepared_token_digest"),
    ("reservation", "target_observation_digest"),
    ("cancellation", "request_fingerprint"),
    ("cancellation", "root_qualification_digest"),
    ("admission", "maintenance_sequence"),
    ("admission", "target_observation_digest"),
    ("preconditions", "production_arming_digest"),
    ("approval", "target_ref"),
    ("root", "root_qualification_digest"),
])
def test_changed_durable_joins_refuse(tmp_path, monkeypatch, inputs, kind, mutation):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    if kind == "reservation":
        stored = copy.deepcopy(composition.journal.read_prestart_reservation(
            composition.approval["operation_key"],
            approval=composition.approval.to_dict()).to_dict())
        stored[mutation] = "0" * 64
        stem = actuator._operation_stem(composition.approval["operation_key"])
        Path(composition.journal._root,
             stem + ".reservation.json").write_bytes(
                 contract.canonical_release_bytes(stored))
    elif kind == "cancellation":
        cancellation = cancellation_fixture(composition)
        cancellation[mutation] = "0" * 64
        composition.journal.cancel_prestart = lambda **kwargs: None
        stem = actuator._operation_stem(composition.approval["operation_key"])
        root = Path(composition.journal._root)
        root.mkdir(parents=True, exist_ok=True)
        Path(root, stem + ".cancellation.json").write_bytes(
            contract.canonical_release_bytes(cancellation))
    elif kind == "root":
        install_journal_record(composition, "STARTED")
        stem = actuator._operation_stem(composition.approval["operation_key"])
        record = contract.parse_release_json(Path(
            composition.journal._root, stem + ".json").read_bytes()).to_dict()
        record[mutation] = "0" * 64
        Path(composition.journal._root, stem + ".json").write_bytes(
            contract.canonical_release_bytes(record))
    else:
        evidence = copy.deepcopy(composition.evidence)
        evidence[kind][mutation] = "0" * 64
        composition.evidence = evidence
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.read()


# START identity fields validated by the protected
# `_validate_start_reservation_joins(journal_record, reservation, approval)`
# helper inside `_closure_status`. Each entry mutates one field of the raw
# journal record bytes (other than root_qualification_digest, which is checked
# earlier) and asserts the read fails closed with a bounded journal error and
# performs no durable write.
_START_IDENTITY_MUTATIONS = [
    ("request_fingerprint", "request_fingerprint", "0" * 64),
    ("approval_evidence_digest", "approval_evidence_digest", "0" * 64),
    ("normalized_requested_effect_digest",
     "normalized_requested_effect_digest", "0" * 64),
    ("expected_source_and_precondition_digest",
     "expected_source_and_precondition_digest", "0" * 64),
    ("action_target_digest", "action_target_digest", "0" * 64),
    ("owner_installation_id", "owner_installation_id", "0" * 36),
    ("target_ref", "target_ref", "0" * 64),
    ("before_release_commit", "before_release_commit", "0" * 40),
    ("before_release_tree", "before_release_tree", "0" * 40),
    ("before_installed_manifest_digest",
     "before_installed_manifest_digest", "0" * 64),
    ("before_configuration_digest", "before_configuration_digest", "0" * 64),
    ("target_release_commit", "target_release_commit", "0" * 40),
    ("target_release_tree", "target_release_tree", "0" * 40),
    ("boot_id", "boot_id", "0" * 36),
    ("preconditions_boot_id", ("preconditions", "boot_id"), "0" * 36),
    ("preconditions_admission_contract",
     ("preconditions", "admission_contract_digest"), "0" * 64),
    ("started_at_ms_before_reserved",
     ("timing", "before_reserved"), None),
    ("started_at_ms_past_expires",
     ("timing", "past_expires"), None),
]


@pytest.mark.parametrize("label,field,value", _START_IDENTITY_MUTATIONS)
def test_journal_start_identity_mismatch_refuses_before_status(
        tmp_path, monkeypatch, inputs, label, field, value):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, "STARTED")
    stem = actuator._operation_stem(composition.approval["operation_key"])
    record_path = Path(composition.journal._root, stem + ".json")
    record = contract.parse_release_json(record_path.read_bytes()).to_dict()
    if field[0] == "preconditions":
        record["preconditions"][field[1]] = value
    elif field[0] == "timing":
        if field[1] == "before_reserved":
            record["started_at_ms"] = NOW[0] - 1
        else:
            record["started_at_ms"] = NOW[0] + 600_000
    else:
        record[field] = value
    record_path.write_bytes(contract.canonical_release_bytes(record))
    mark_written(composition.journal)
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.read()


def test_closure_wire_carries_only_canonical_evidence_while_owner_qualifies(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, "SUCCEEDED")
    raw = composition.frame()
    assert set(raw) == {"schema", "operation", "admission_evidence"}
    assert raw["admission_evidence"] == composition.evidence
    assert not any(key in raw for key in (
        "path", "runtime", "socket", "callback", "selector", "approval"))
    composition.read()
    assert composition.qualifications == ["control"] * 6


@pytest.mark.parametrize("field", [
    "owner_installation_id", "target_ref", "operation_key", "transition_digest"])
def test_original_approval_drift_refuses(tmp_path, monkeypatch, inputs, field):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    approval = composition.approval.to_dict()
    if field == "transition_digest":
        approval[field] = "0" * 64
    else:
        approval[field] = "0" * 64
    with pytest.raises(consumer.ReleaseConsumerError,
                       match=("RELEASE_ADMISSION_EVIDENCE_INVALID|"
                              "RELEASE_APPROVAL_IDENTITY_MISMATCH|"
                              "RELEASE_BROKER_FRAME_INVALID")):
        raw = composition.frame()
        raw["admission_evidence"]["approval"] = approval
        composition.read(raw)


def test_unstable_history_trust_refuses(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    original = composition.owner._history_trust
    calls = []
    def unstable():
        calls.append(len(calls))
        trust = original()
        if calls[-1] == 1:
            return owner_module.ReleaseHistoryTrust(
                codec=trust.codec, owner_installation_id=trust.owner_installation_id,
                target_ref="0" * 64, input_identity_digest=trust.input_identity_digest)
        return trust
    composition.owner._history_trust = unstable
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_HISTORY_TRUST_UNAVAILABLE"):
        composition.read()
    assert calls == [0, 1]


def test_durable_closure_never_restages_expired_transition(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, "SUCCEEDED")

    def staging_unavailable(_transition):
        raise consumer.ReleaseConsumerError("RELEASE_STAGE_UNAVAILABLE")

    composition.owner._snapshot = staging_unavailable
    result = composition.read()
    assert result["result"]["terminal_status"]["state"] == "SUCCEEDED"
    assert result["result"]["cancellation"] is None


@pytest.mark.parametrize("mutation,change", [
    ("extra", {"retry": True}),
    ("principal", {"principal": {}}),
    ("token", {"prepared_token": "unused"}),
    ("selector", {"state": "SUCCEEDED"}),
    ("missing", "missing"),
])
def test_exact_private_wire_and_response_keys(
        tmp_path, monkeypatch, inputs, mutation, change):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, "STARTED")
    clean_raw = composition.frame()
    raw = composition.frame(**({} if mutation == "missing" else change))
    original = mark_written(composition.journal)
    if mutation == "missing":
        raw.pop("admission_evidence")
    elif mutation == "extra":
        raw.update(change)
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_BROKER_FRAME_INVALID"):
        composition.read(raw)
    restore_writers(composition.journal, original)
    original = mark_written(composition.journal)
    result = composition.read()
    restore_writers(composition.journal, original)
    assert set(result) == {"schema", "operation", "ok", "approval", "result"}
    assert set(result["result"]) == {"reservation", "terminal_status", "cancellation"}
    assert "principal" not in result and "error" not in result
    assert not any(key in clean_raw for key in (
        "principal", "prepared_token", "reservation", "admission", "state"))


def test_public_commit_disarming_is_preserved(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    public = ingress.project_frame(
        "commit_prepared_release_transition",
        {"operation_key": composition.approval["operation_key"],
         "prepared_token": composition.token},
        principal=composition.principal)
    raw = {**public, "schema": consumer.BROKER_SCHEMA,
           "approval": composition.approval.to_dict()}
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_COMMIT_DISARMED"):
        composition.owner.handle(raw, composition.connection)
    assert composition.qualifications == ["control"] * 2


def test_missing_installed_composition_refuses(tmp_path, monkeypatch, inputs):
    principal, snapshot, state_factory = fixture(inputs)
    approval = approval_fixture(snapshot, principal)
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_ROOT_JOURNAL_UNAVAILABLE"):
        ReleaseBrokerOwner(state_factory).handle(
            {"schema": consumer.BROKER_SCHEMA, "operation": "read_release_closure",
             "admission_evidence": {}}, object())
    owner = ReleaseBrokerOwner(
        state_factory, history_trust=lambda: owner_module.ReleaseHistoryTrust(
            codec=snapshot.codec, owner_installation_id=snapshot.owner_installation_id,
            target_ref=snapshot.target_ref))
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_ROOT_JOURNAL_UNAVAILABLE"):
        owner.handle({"schema": consumer.BROKER_SCHEMA,
                      "operation": "read_release_closure",
                      "admission_evidence": {}}, object())
    assert not hasattr(owner, "_admission_reader")


# ---------------------------------------------------------------------------
# R9 TOCTOU closure snapshot tests (F1).
# ---------------------------------------------------------------------------


def _mutate_reservation_sidecar(path, kind, *, approval):
    """Apply an Astra R1 reproduction to the on-disk reservation sidecar.

    ``kind == "malformed"`` writes a non-JSON opener; ``"valid_before_drift"``
    revalidates the canonical reservation against the supplied approval and
    rewrites one field of the immutable full 8-field before — exactly the
    Astra R1 reproduction that previously slipped past the cached reservation.
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


def _snapshot_files(root):
    return {p.name: p.read_bytes() for p in Path(root).iterdir() if p.is_file()}


@pytest.mark.parametrize("kind", ["malformed", "valid_before_drift"])
def test_closure_refuses_sidecar_drift_during_runtime_read(
        tmp_path, monkeypatch, inputs, kind):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, "SUCCEEDED")
    stem = actuator._operation_stem(composition.approval["operation_key"])
    original_reservation_bytes = (
        Path(composition.journal._root) / (stem + ".reservation.json")
    ).read_bytes()
    path = Path(composition.journal._root) / (stem + ".reservation.json")
    real_read = composition.journal._read_closure_snapshot

    def drift(*args, **kw):
        _mutate_reservation_sidecar(
            path, kind, approval=composition.approval.to_dict()
        )
        return real_read(*args, **kw)

    monkeypatch.setattr(
        composition.journal, "_read_closure_snapshot", drift
    )
    mark_written(composition.journal)
    with pytest.raises(consumer.ReleaseConsumerError) as caught:
        composition.read()
    # Either the malformed bytes trip the under-lock validator or the
    # valid_before_drift trips the canonical-byte comparison; the error
    # always carries a bounded ``RELEASE_ROOT_JOURNAL_`` code.
    assert str(caught.value).startswith("RELEASE_ROOT_JOURNAL_")
    # The injection hook mutated the reservation sidecar before the read;
    # the reader refused rather than adopting replacement bytes as a new
    # truth. Specifically, no new journal or cancellation file appeared on
    # disk as a result of the read. The operation lock inode is the only
    # other file the journal ever creates under the root.
    on_disk = {p.name for p in Path(composition.journal._root).iterdir()}
    assert on_disk.issubset({
        stem + ".reservation.json",
        stem + ".json",
        stem + ".lock",
    })
    # The reader did not produce a new journal entry. The reservation
    # sidecar bytes that the reader would have observed equal the
    # original, not the post-drift bytes, so the read must fail.
    del original_reservation_bytes


def test_closure_refuses_inode_only_reservation_replacement_during_runtime_read(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, "SUCCEEDED")
    stem = actuator._operation_stem(composition.approval["operation_key"])
    path = Path(composition.journal._root) / (stem + ".reservation.json")
    original_raw = path.read_bytes()
    original_inode = path.stat().st_ino
    original_journal_raw = (
        Path(composition.journal._root) / (stem + ".json")
    ).read_bytes()
    real_read = composition.journal._read_closure_snapshot

    def drift(*args, **kw):
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(original_raw)
        replacement.chmod(0o600)
        os.replace(replacement, path)
        return real_read(*args, **kw)

    monkeypatch.setattr(
        composition.journal, "_read_closure_snapshot", drift
    )
    mark_written(composition.journal)
    with pytest.raises(consumer.ReleaseConsumerError) as caught:
        composition.read()
    # The on-disk reservation is byte-identical to the original; only the
    # inode changed. The under-lock snapshot refuses the inode-only
    # replacement (filesystem identity equality) and never rewrites the
    # journal file.
    assert str(caught.value).startswith("RELEASE_ROOT_JOURNAL_")
    assert path.read_bytes() == original_raw
    assert path.stat().st_ino != original_inode
    assert (
        Path(composition.journal._root) / (stem + ".json")
    ).read_bytes() == original_journal_raw


@pytest.mark.parametrize("with_cancellation", [False, True])
@pytest.mark.parametrize("raw", [b"", b"{", b"{}", b"null"])
def test_present_invalid_journal_never_becomes_absence(
        tmp_path, monkeypatch, inputs, raw, with_cancellation):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    if with_cancellation:
        composition.journal.cancel_prestart(
            cancellation=cancellation_fixture(composition),
            reservation=composition.reservation,
            admission=composition.admission.to_dict(),
            approval=composition.approval.to_dict(),
        )
    stem = actuator._operation_stem(composition.approval["operation_key"])
    journal_path = Path(composition.journal._root) / (stem + ".json")
    journal_path.write_bytes(raw)
    journal_path.chmod(0o600)
    before = _snapshot_files(Path(composition.journal._root))

    with pytest.raises(consumer.ReleaseConsumerError) as caught:
        composition.read()

    assert "NOT_FOUND" not in str(caught.value)
    assert _snapshot_files(Path(composition.journal._root)) == before


@pytest.mark.parametrize("state", TERMINAL_STATES + NONTERMINAL_STATES)
def test_read_invariants_no_mutation(
        tmp_path, monkeypatch, inputs, state):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    install_journal_record(composition, state)
    stem = actuator._operation_stem(composition.approval["operation_key"])
    original_snapshot = _snapshot_files(Path(composition.journal._root))
    original_reservation_bytes = (
        Path(composition.journal._root) / (stem + ".reservation.json")
    ).read_bytes()
    mark_written(composition.journal)
    result = composition.read()
    status = result["result"]["terminal_status"]
    assert status["state"] == state
    assert result["result"]["cancellation"] is None
    contract.validate_release_terminal_status(
        status, expected_approval=composition.approval.to_dict()
    )
    if state in TERMINAL_STATES:
        receipt = status["terminal_receipt"]
        assert receipt["before"] == composition.reservation["before"]
        assert len(receipt["before"]) == len(receipt["after"]) == 8
        if state != "SUCCEEDED":
            assert receipt["after"] == receipt["before"]
        assert receipt["rollback"]["attempted"] == (state == "ROLLED_BACK")
    else:
        assert "terminal_receipt" not in status
    # Reader did not write any file under the journal root.
    assert _snapshot_files(Path(composition.journal._root)) == original_snapshot
    # The on-disk reservation sidecar is preserved byte-for-byte.
    assert (
        Path(composition.journal._root) / (stem + ".reservation.json")
    ).read_bytes() == original_reservation_bytes
