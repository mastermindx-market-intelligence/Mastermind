"""Private root START composition tests; no production path is constructed."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane import executive_release_actuator as actuator
from control_plane import executive_release_contract as contract
from control_plane import executive_release_consumer as consumer
from control_plane import executive_release_ingress as ingress
from control_plane.executive_authority import (
    ReleaseControllerPolicy, release_principal_projection,
)
from control_plane.executive_release_owner import ReleaseBrokerOwner, ReleaseOwnerSnapshot
from control_plane.executive_release_token import ReleaseTokenError, _OwnerReleaseCodec
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
def restore_test_clocks():
    wall, monotonic = NOW[0], MONOTONIC[0]
    yield
    NOW[0], MONOTONIC[0] = wall, monotonic


def digest(value):
    return hashlib.sha256(contract.canonical_release_bytes(value)).hexdigest()


def reader(**changes):
    value = {
        "schema": consumer.BROKER_SCHEMA,
        "operation": "start_reserved_release",
        "arguments": {"operation_key": "root-start-proof", "prepared_token": None},
        "principal": "unused",
        "approval": None,
        "reservation": None,
        "admission": None,
    }
    value.update(changes)
    return value


class AdmissionReader:
    def __init__(self):
        self.evidence = None
        self.calls = []

    def read_admission_evidence(self, *, approved_transition_ref, request_fingerprint):
        self.calls.append((approved_transition_ref, request_fingerprint))
        return copy.deepcopy(self.evidence)


def fixture(inputs):
    principal, effect, policy = copy.deepcopy(inputs)
    effect = contract.validate_normalized_effect(effect)
    policy = ReleaseControllerPolicy.from_bytes(source(policy))
    codec = _OwnerReleaseCodec(
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
    snapshot = ReleaseOwnerSnapshot(
        policy=policy, codec=codec, owner_installation_id=OWNER, target_ref=TARGET,
        boot_id=OWNER, key_id="test-key", trust_generation=1, app_generation=1,
        schema_digest="1" * 64, admission_contract_digest="e" * 64, effect=effect,
        preconditions=preconditions, actuator_generation=ACTUATOR_GENERATION,
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
                "control": "8" * 64,
                "worker": "9" * 64,
                "relay": "a" * 64,
                "gateway": "b" * 64,
                "broker": "c" * 64,
            },
        })

    def state_factory(transition):
        assert transition == digest(snapshot.effect)
        return snapshot

    return principal, effect, snapshot, state_factory


def approval_fixture(snapshot, principal, *, operation_key="root-start-proof"):
    now = NOW[0]
    principal_projection = release_principal_projection(principal)
    principal_digest = digest(principal_projection)
    confirmation_digest = hashlib.sha256(
        b"MMX_EXECUTIVE_RELEASE_DELEGATION_V1\0"
        + contract.canonical_release_bytes({
            "policy_id": principal.policy_id, "policy_generation": 7,
            "confirmation_requirement": "delegated",
            "authority_policy_hash": snapshot.policy.sha256,
            "principal_digest": principal_digest, "target_ref": TARGET,
            "transition_digest": digest(snapshot.effect),
        })).hexdigest()
    grant = {
        "schema": "mastermind.executive_release_grant/v1",
        "principal_digest": principal_digest,
        "authority_policy_hash": snapshot.policy.sha256,
        "policy_id": principal.policy_id,
        "policy_generation": 7,
        "action": snapshot.effect["action"],
        "target_ref": TARGET,
        "transition_digest": digest(snapshot.effect),
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
        "action": snapshot.effect["action"],
        "owner_installation_id": OWNER,
        "target_ref": TARGET,
        "principal_projection": principal_projection.to_dict(),
        "normalized_requested_effect": snapshot.effect.to_dict(),
        "transition_digest": digest(snapshot.effect),
        "grant": grant,
        "effective_grant_digest": digest(grant),
        "created_at_ms": now, "expires_at_ms": grant["expires_at_ms"],
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
        "key_id": "test-key", "authenticated_principal_digest": digest(approval["principal_projection"]),
        "approved_transition_ref": approval["approved_transition_ref"],
        "approval_evidence_digest": digest(approval), "policy_id": principal_policy(approval),
        "policy_generation": 7, "authority_policy_hash": snapshot.policy.sha256,
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


def principal_policy(approval):
    return approval["principal_projection"]["policy_id"]


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


class Composition:
    def __init__(self, tmp_path, monkeypatch, inputs, **snapshot_changes):
        principal, effect, snapshot, state_factory = fixture(inputs)
        if snapshot_changes:
            snapshot = ReleaseOwnerSnapshot(**{
                **dict(policy=snapshot.policy, codec=snapshot.codec,
                       owner_installation_id=snapshot.owner_installation_id,
                       target_ref=snapshot.target_ref, boot_id=snapshot.boot_id,
                       key_id=snapshot.key_id, trust_generation=snapshot.trust_generation,
                       app_generation=snapshot.app_generation, schema_digest=snapshot.schema_digest,
                       admission_contract_digest=snapshot.admission_contract_digest,
                       effect=snapshot.effect, preconditions=snapshot.preconditions,
                       input_identity_digest=snapshot.input_identity_digest,
                       actuator_generation=snapshot.actuator_generation,
                       target_observation_digest=snapshot.target_observation_digest,
                       before=snapshot.before),
                **snapshot_changes})
        self.principal, self.effect, self.snapshot = principal, effect, snapshot
        self.approval = approval_fixture(snapshot, principal)
        self.prepared = prepared_fixture(snapshot, self.approval)
        self.token = snapshot.codec.encode_prepared(self.prepared)
        self.journal = actuator._ExecutiveReleaseActuatorJournal._for_tests(
            tmp_path / "journal")
        self.admission_reader = AdmissionReader()
        self.owner = ReleaseBrokerOwner(
            state_factory if not snapshot_changes else (lambda transition: snapshot),
            root_journal=self.journal, admission_reader=self.admission_reader)
        monkeypatch.setattr(
            __import__("control_plane.executive_release_owner", fromlist=["time"]).time,
            "time_ns", lambda: NOW[0] * 1_000_000)
        monkeypatch.setattr(
            __import__("control_plane.executive_release_owner", fromlist=["time"]).time,
            "monotonic_ns", lambda: MONOTONIC[0])
        monkeypatch.setattr(
            __import__("control_plane.executive_release_owner", fromlist=["_qualify_connection"]),
            "_qualify_connection", lambda connection, role: None)

    def frame(self, operation, **changes):
        public = ingress.project_frame(
            "commit_prepared_release_transition",
            {"operation_key": self.approval["operation_key"], "prepared_token": self.token},
            principal=self.principal)
        value = {**public, "schema": consumer.BROKER_SCHEMA, "operation": operation,
                 "approval": self.approval.to_dict()}
        if operation == "start_reserved_release":
            value["reservation"] = self._plain(self.reservation)
            value["admission"] = self._plain(self.admission)
        value.update(changes)
        return value

    def reserve(self):
        result = self.owner.handle(self.frame("reserve_release_prestart"), object())
        self.reservation = result["result"]["reservation"]
        self.admission = admission_fixture(self.approval, self.reservation)
        self.admission_reader.evidence = {
            "approval": self.approval.to_dict(),
            "admission": self.admission.to_dict(),
            "preconditions": self.reservation["preconditions"],
            "root_qualification_digest": digest(self.reservation),
        }
        return result

    def start(self, raw=None):
        return self.owner.handle(raw or self.frame("start_reserved_release"), object())

    @staticmethod
    def _plain(value):
        return value.to_dict() if hasattr(value, "to_dict") else copy.deepcopy(value)


def test_snapshot_defaults_are_public_and_private_operations_refuse_them(tmp_path, monkeypatch, inputs):
    principal, _effect, snapshot, state_factory = fixture(inputs)
    inert = ReleaseOwnerSnapshot(
        policy=snapshot.policy, codec=snapshot.codec, owner_installation_id=OWNER,
        target_ref=TARGET, boot_id=OWNER, key_id="test-key", trust_generation=1,
        app_generation=1, schema_digest="1" * 64, admission_contract_digest="e" * 64,
        effect=snapshot.effect, preconditions=snapshot.preconditions)
    assert inert.actuator_generation == 0
    assert inert.target_observation_digest == ""
    composition = Composition(tmp_path, monkeypatch, inputs)
    assert Composition(tmp_path, monkeypatch, inputs).snapshot.actuator_generation == 9
    assert state_factory(digest(snapshot.effect)) is snapshot
    assert principal.policy_id == "release-policy"


def test_reserve_start_and_exact_replay(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    reserved = composition.reserve()
    assert reserved["operation"] == "reserve_release_prestart"
    assert reserved["result"]["reservation"]["reservation_generation"] == 1
    assert reserved["result"]["reservation"]["before"] == composition.snapshot.before
    NOW[0] += 1
    MONOTONIC[0] += 1_000_000
    replayed_reservation = composition.owner.handle(
        composition.frame("reserve_release_prestart"), object())
    assert replayed_reservation == reserved
    started = composition.start()
    assert started["operation"] == "start_reserved_release"
    record = started["result"]["start_record"]
    assert record["state"] == "STARTED"
    assert record["journal_generation"] == 1
    assert record["actuator_generation"] == ACTUATOR_GENERATION
    assert composition.admission_reader.calls == [(
        composition.reservation["approved_transition_ref"],
        composition.reservation["request_fingerprint"])]
    NOW[0] += 1
    MONOTONIC[0] += 1_000_000
    replay = composition.start()
    assert replay == started
    assert composition.admission_reader.calls[-1] == composition.admission_reader.calls[0]


@pytest.mark.parametrize("clock", ["wall", "monotonic"])
@pytest.mark.parametrize("past", [0, 1])
def test_expiry_during_runtime_read_prevents_durable_start(
        tmp_path, monkeypatch, inputs, clock, past):
    wall, monotonic = NOW[0], MONOTONIC[0]
    try:
        composition = Composition(tmp_path, monkeypatch, inputs)
        composition.reserve()
        NOW[0] = composition.prepared["expires_at_ms"] - 1
        MONOTONIC[0] = composition.prepared["expires_monotonic_ns"] - 1_000_000
        read = composition.admission_reader.read_admission_evidence

        def delayed(**kwargs):
            evidence = read(**kwargs)
            if clock == "wall":
                NOW[0] = composition.prepared["expires_at_ms"] + past
            else:
                MONOTONIC[0] = composition.prepared["expires_monotonic_ns"] + past
            return evidence

        monkeypatch.setattr(
            composition.admission_reader, "read_admission_evidence", delayed)
        with pytest.raises(consumer.ReleaseConsumerError):
            composition.start()
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                           match="NOT_FOUND"):
            composition.journal.read(composition.approval["operation_key"])
    finally:
        NOW[0], MONOTONIC[0] = wall, monotonic


@pytest.mark.parametrize(
    "field", ["target_observation_digest", "before", "actuator_generation"])
def test_physical_snapshot_drift_during_runtime_read_prevents_start(
        tmp_path, monkeypatch, inputs, field):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    read = composition.admission_reader.read_admission_evidence

    def drift(**kwargs):
        evidence = read(**kwargs)
        if field == "before":
            changed = copy.deepcopy(composition.snapshot.before)
            changed["broker_binary_digest"] = "0" * 64
        elif field == "actuator_generation":
            changed = composition.snapshot.actuator_generation + 1
        else:
            changed = "0" * 64
        current = replace(composition.snapshot, **{field: changed})
        composition.owner._snapshot = lambda transition: current
        return evidence

    monkeypatch.setattr(
        composition.admission_reader, "read_admission_evidence", drift)
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


@pytest.mark.parametrize("field", ["reservation", "admission"])
def test_start_rejects_missing_top_level_field(tmp_path, monkeypatch, inputs, field):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    raw.pop(field)
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_BROKER_FRAME_INVALID"):
        composition.start(raw)
    assert not composition.admission_reader.calls


def test_private_envelope_rejects_extra_fields_and_public_commit_remains_disarmed(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    reserve = composition.frame("reserve_release_prestart")
    reserve["reservation"] = {}
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_BROKER_FRAME_INVALID"):
        composition.owner.handle(reserve, object())
    public = ingress.project_frame(
        "commit_prepared_release_transition",
        {"operation_key": "root-start-proof", "prepared_token": composition.token},
        principal=composition.principal)
    raw = {**public, "schema": consumer.BROKER_SCHEMA, "approval": composition.approval.to_dict()}
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_COMMIT_DISARMED"):
        composition.owner.handle(raw, object())


def test_start_rejects_missing_expired_or_foreign_admission_evidence(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    good = copy.deepcopy(composition.admission_reader.evidence)
    cases = []
    cases.append(("missing", None))
    changed_admission = copy.deepcopy(good)
    changed_admission["admission"]["maintenance_sequence"] = 2
    cases.append(("foreign", changed_admission))
    changed_digest = copy.deepcopy(good)
    changed_digest["root_qualification_digest"] = "0" * 64
    cases.append(("digest", changed_digest))
    extra = copy.deepcopy(good)
    extra["extra"] = 1
    cases.append(("extra", extra))
    for _name, evidence in cases:
        composition.admission_reader.evidence = evidence
        with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ADMISSION_EVIDENCE"):
            composition.start()
    composition.admission_reader.evidence = copy.deepcopy(good)
    NOW[0] += 300_001
    MONOTONIC[0] += 300_001_000_000
    try:
        with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_APPROVAL_NOT_CURRENT"):
            composition.start()
    finally:
        NOW[0] -= 300_001
        MONOTONIC[0] -= 300_001_000_000
    composition.admission_reader.evidence = copy.deepcopy(good)
    assert composition.start()["ok"] is True


def test_start_rejects_changed_reservation_admission_or_target_observation(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    reservation = copy.deepcopy(composition.reservation)
    reservation["target_observation_digest"] = "7" * 64
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start(composition.frame("start_reserved_release", reservation=reservation))
    admission = composition.admission.to_dict()
    admission["maintenance_sequence"] = 2
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ADMISSION_EVIDENCE_MISMATCH"):
        composition.start(composition.frame("start_reserved_release", admission=admission))
    snapshot = replace(composition.snapshot, target_observation_digest="7" * 64)
    composition.snapshot = snapshot
    composition.owner._snapshot = lambda transition: snapshot
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_RESERVATION_MISMATCH"):
        composition.start()


def test_start_rejects_changed_policy_principal_or_dependency_defaults(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    other_principal, _effect, other_snapshot, _factory = fixture(inputs)
    assert other_principal == composition.principal
    foreign = composition.frame("start_reserved_release")
    foreign["principal"]["subject_digest"] = "9" * 64
    with pytest.raises(Exception, match="RELEASE_PRINCIPAL_NOT_AUTHORIZED"):
        composition.start(foreign)
    composition.owner._snapshot = lambda transition: composition.snapshot
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ROOT_OWNER_UNAVAILABLE"):
        changed = Composition(tmp_path, monkeypatch, inputs, actuator_generation=0)
        changed.reserve()
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ROOT_OWNER_UNAVAILABLE"):
        changed = Composition(tmp_path, monkeypatch, inputs, target_observation_digest="")
        changed.reserve()
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ROOT_OWNER_UNAVAILABLE"):
        changed = Composition(tmp_path, monkeypatch, inputs, before={})
        changed.reserve()


def test_missing_reservation_and_cancellation_refuse_start(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ROOT_JOURNAL_NOT_FOUND"):
        composition.reserve()
        Path(composition.journal._root).mkdir(parents=True, exist_ok=True)
        for path in Path(composition.journal._root).iterdir():
            if path.name.endswith(".reservation.json"):
                path.unlink()
        composition.start()
    cancelled = Composition(tmp_path, monkeypatch, inputs)
    cancelled.reserve()
    cancelled.journal.cancel_prestart(
        cancellation=cancellation_fixture(cancelled),
        reservation=cancelled.reservation,
        admission=cancelled.admission,
        approval=cancelled.approval,
    )
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ROOT_JOURNAL_RESERVATION_CONFLICT"):
        cancelled.start()


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


def test_admission_reader_must_be_object_method_not_callable(tmp_path, monkeypatch, inputs):
    principal, effect, snapshot, state_factory = fixture(inputs)
    with pytest.raises(TypeError):
        ReleaseBrokerOwner(
            state_factory, admission_reader=lambda *_args, **_kwargs: None)
    reader = AdmissionReader()
    owner = ReleaseBrokerOwner(state_factory, admission_reader=reader)
    assert not callable(owner._admission_reader)
    assert callable(owner._admission_reader.read_admission_evidence)


def test_public_snapshot_constructor_is_positionally_compatible(inputs):
    principal, effect, snapshot, _factory = fixture(inputs)
    rebuilt = ReleaseOwnerSnapshot(
        snapshot.policy, snapshot.codec, snapshot.owner_installation_id,
        snapshot.target_ref, snapshot.boot_id, snapshot.key_id,
        snapshot.trust_generation, snapshot.app_generation, snapshot.schema_digest,
        snapshot.admission_contract_digest, snapshot.effect, snapshot.preconditions)
    assert rebuilt.actuator_generation == 0
    assert rebuilt.target_observation_digest == ""
    assert rebuilt.before == {}
