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


def admission_evidence_fixture(approval, admission, reservation):
    return {
        "approval": approval.to_dict(),
        "admission": admission.to_dict(),
        "preconditions": reservation["preconditions"],
        "root_qualification_digest": digest(reservation),
    }


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
        self.peer_calls = []
        self.owner = ReleaseBrokerOwner(
            state_factory if not snapshot_changes else (lambda transition: snapshot),
            root_journal=self.journal)
        self._monkeypatch = monkeypatch
        monkeypatch.setattr(
            __import__("control_plane.executive_release_owner", fromlist=["time"]).time,
            "time_ns", lambda: NOW[0] * 1_000_000)
        monkeypatch.setattr(
            __import__("control_plane.executive_release_owner", fromlist=["time"]).time,
            "monotonic_ns", lambda: MONOTONIC[0])
        monkeypatch.setattr(
            __import__("control_plane.executive_release_owner", fromlist=["_qualify_connection"]),
            "_qualify_connection", self._record_peer)

    def _record_peer(self, connection, role):
        self.peer_calls.append((id(connection), role))

    def frame(self, operation, **changes):
        public = ingress.project_frame(
            "commit_prepared_release_transition",
            {"operation_key": self.approval["operation_key"], "prepared_token": self.token},
            principal=self.principal)
        value = {**public, "schema": consumer.BROKER_SCHEMA, "operation": operation,
                 "approval": self.approval.to_dict()}
        if operation == "start_reserved_release":
            value["reservation"] = self._plain(self.reservation)
            value["admission_evidence"] = self._plain(self.evidence)
        value.update(changes)
        return value

    def reserve(self):
        result = self.owner.handle(self.frame("reserve_release_prestart"), object())
        self.reservation = result["result"]["reservation"]
        self.admission = admission_fixture(self.approval, self.reservation)
        self.evidence = admission_evidence_fixture(
            self.approval, self.admission, self.reservation)
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
    NOW[0] += 1
    MONOTONIC[0] += 1_000_000
    replay = composition.start()
    assert replay == started


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

        def delayed_snapshot(_transition, _state=None):
            evidence = copy.deepcopy(composition.evidence)
            if clock == "wall":
                NOW[0] = composition.prepared["expires_at_ms"] + past
            else:
                MONOTONIC[0] = composition.prepared["expires_monotonic_ns"] + past
            return evidence

        monkeypatch.setattr(composition.owner, "_snapshot", delayed_snapshot)
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
    real_snapshot = composition.owner._snapshot
    calls = {"count": 0}

    def drift_snapshot(transition):
        calls["count"] += 1
        # The first outer private-inputs call still sees the original
        # snapshot; the drift becomes visible to the second call (which
        # the journal acquire callback invokes after all blocking reads)
        # and would also be visible to ``qualify_locked_start`` if it
        # ran. Either way the journal must refuse to write a START.
        if calls["count"] >= 2:
            if field == "before":
                changed = copy.deepcopy(composition.snapshot.before)
                changed["broker_binary_digest"] = "0" * 64
            elif field == "actuator_generation":
                changed = composition.snapshot.actuator_generation + 1
            else:
                changed = "0" * 64
            return replace(composition.snapshot, **{field: changed})
        return real_snapshot(transition)

    composition.owner._snapshot = drift_snapshot
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


@pytest.mark.parametrize("clock", ["wall", "monotonic"])
def test_expiry_during_final_journal_lock_prevents_durable_start(
        tmp_path, monkeypatch, inputs, clock):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    NOW[0] = composition.prepared["expires_at_ms"] - 1
    MONOTONIC[0] = composition.prepared["expires_monotonic_ns"] - 1_000_000
    acquire = composition.journal._acquire_flock
    calls = []

    def delayed(descriptor, deadline, **kwargs):
        acquire(descriptor, deadline, **kwargs)
        calls.append(1)
        if len(calls) == 3:
            if clock == "wall":
                NOW[0] = composition.prepared["expires_at_ms"]
            else:
                MONOTONIC[0] = composition.prepared["expires_monotonic_ns"]

    monkeypatch.setattr(composition.journal, "_acquire_flock", delayed)
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start()
    assert len(calls) == 3
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


@pytest.mark.parametrize("field", ["reservation", "admission_evidence"])
def test_start_rejects_missing_top_level_field(tmp_path, monkeypatch, inputs, field):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    raw.pop(field)
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_BROKER_FRAME_INVALID"):
        composition.start(raw)


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
    good = copy.deepcopy(composition.evidence)
    cases = []
    cases.append(("missing", None))
    changed_join = copy.deepcopy(good)
    changed_join["admission"]["target_observation_digest"] = "0" * 64
    cases.append(("foreign", changed_join))
    changed_digest = copy.deepcopy(good)
    changed_digest["root_qualification_digest"] = "0" * 64
    cases.append(("digest", changed_digest))
    extra = copy.deepcopy(good)
    extra["extra"] = 1
    cases.append(("extra", extra))
    for _name, evidence in cases:
        composition.evidence = evidence
        with pytest.raises(consumer.ReleaseConsumerError,
                           match="RELEASE_BROKER_FRAME_INVALID|RELEASE_ADMISSION_EVIDENCE|RELEASE_ROOT_JOURNAL_"):
            composition.start()
    composition.evidence = copy.deepcopy(good)
    NOW[0] += 300_001
    MONOTONIC[0] += 300_001_000_000
    try:
        with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_APPROVAL_NOT_CURRENT"):
            composition.start()
    finally:
        NOW[0] -= 300_001
        MONOTONIC[0] -= 300_001_000_000
    composition.evidence = copy.deepcopy(good)
    assert composition.start()["ok"] is True


def test_start_rejects_changed_reservation_admission_or_target_observation(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    reservation = copy.deepcopy(composition.reservation)
    reservation["target_observation_digest"] = "7" * 64
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start(composition.frame("start_reserved_release", reservation=reservation))
    evidence = copy.deepcopy(composition.evidence)
    evidence["admission"]["target_observation_digest"] = "7" * 64
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ROOT_JOURNAL_ADMISSION_JOIN"):
        composition.start(composition.frame("start_reserved_release", admission_evidence=evidence))
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


# ---------------------------------------------------------------------------
# R10 strict private-wire and evidence regression tests.
# ---------------------------------------------------------------------------


def test_start_strict_wire_keys(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    assert set(raw) == {
        "schema", "operation", "arguments", "principal", "approval",
        "reservation", "admission_evidence"}
    assert "admission" not in raw
    nested = raw["admission_evidence"]
    assert set(nested) == {
        "approval", "admission", "preconditions", "root_qualification_digest"}


@pytest.mark.parametrize("mutation,change", [
    ("admission_top_level", {"admission": {}}),
    ("approval_top_level", {"approval": {}}),
    ("reservation_top_level", {"reservation": {}}),
    ("evidence_extra_field", {"admission_evidence": {
        "approval": None, "admission": None, "preconditions": None,
        "root_qualification_digest": None, "extra": 1}}),
    ("evidence_missing_field", {"admission_evidence": {
        "approval": None, "admission": None, "root_qualification_digest": None}}),
    ("wrong_type_evidence", {"admission_evidence": "notamapping"}),
    ("wrong_type_approval", {"admission_evidence": {
        "approval": [], "admission": None, "preconditions": None,
        "root_qualification_digest": None}}),
    ("wrong_type_digest", {"admission_evidence": {
        "approval": None, "admission": None, "preconditions": None,
        "root_qualification_digest": []}}),
])
def test_start_rejects_strict_wire_mutation(tmp_path, monkeypatch, inputs, mutation, change):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    raw.update(change)
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start(raw)


def test_start_evidence_approval_must_byte_equal_top_level_approval(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    # Build a second sealed approval using a different owner codec so the
    # two approvals are both valid but their canonical bytes differ.
    # Mutating the original approval in place fails the frozen validator
    # before the canonical-byte check can run.
    principal2, _effect2, _snapshot2, _factory2 = fixture(inputs)
    different_codec = _OwnerReleaseCodec(
        key=bytes(reversed(range(32))), key_id="test-key", trust_generation=1,
        owner_installation_id=OWNER)
    snapshot2 = ReleaseOwnerSnapshot(
        policy=composition.snapshot.policy, codec=different_codec,
        owner_installation_id=OWNER, target_ref=TARGET,
        boot_id=OWNER, key_id="test-key", trust_generation=1,
        app_generation=1, schema_digest="1" * 64,
        admission_contract_digest="e" * 64, effect=composition.snapshot.effect,
        preconditions=composition.snapshot.preconditions,
        actuator_generation=ACTUATOR_GENERATION,
        target_observation_digest=TARGET_OBSERVATION,
        before=composition.snapshot.before)
    different_approval = approval_fixture(
        snapshot2, principal2, operation_key=composition.approval["operation_key"])
    assert (contract.canonical_release_bytes(different_approval.to_dict())
            != contract.canonical_release_bytes(composition.approval.to_dict()))
    raw["admission_evidence"]["approval"] = different_approval.to_dict()
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ADMISSION_EVIDENCE"):
        composition.start(raw)


def test_start_evidence_digest_must_equal_reservation_digest(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    raw["admission_evidence"]["root_qualification_digest"] = "0" * 64
    with pytest.raises(consumer.ReleaseConsumerError, match="RELEASE_ADMISSION_EVIDENCE_MISMATCH"):
        composition.start(raw)


@pytest.mark.parametrize("field", [
    "reservation_prepared_token_digest",
    "reservation_target_observation_digest",
    "admission_target_observation_digest",
    "preconditions_production_arming_digest",
    "root_qualification_digest",
])
def test_start_full_join_mutation_refuses(tmp_path, monkeypatch, inputs, field):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    if field == "reservation_prepared_token_digest":
        raw["reservation"]["prepared_token_digest"] = "0" * 64
    elif field == "reservation_target_observation_digest":
        raw["reservation"]["target_observation_digest"] = "0" * 64
    elif field == "admission_target_observation_digest":
        raw["admission_evidence"]["admission"]["target_observation_digest"] = "0" * 64
    elif field == "preconditions_production_arming_digest":
        raw["admission_evidence"]["preconditions"]["production_arming_digest"] = "0" * 64
    elif field == "root_qualification_digest":
        raw["admission_evidence"]["root_qualification_digest"] = "0" * 64
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start(raw)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


def test_start_rejects_qualifier_owner_drift_at_final_lock(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    real_inputs = composition.owner._private_inputs

    def drift_inputs(frame, raw, **kwargs):
        state, effect, sealed, payload, preconditions = real_inputs(frame, raw, **kwargs)
        return (replace(state, target_observation_digest="0" * 64),
                effect, sealed, payload, preconditions)

    monkeypatch.setattr(composition.owner, "_private_inputs", drift_inputs)
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start()
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


def test_start_peer_qualification_runs_at_final_lock(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    composition.peer_calls = []
    composition.start()
    # The final operation lock qualifier must invoke peer qualification
    # at least once after every blocking read and immediately before
    # create/replay. Each call into ``_qualify_connection`` records a tuple
    # containing the role; assert at least one such call was made during
    # the locked start.
    assert any(role == "control" for _id, role in composition.peer_calls)


@pytest.mark.parametrize("invalidating_snapshot", [1, 2])
def test_start_refuses_peer_invalidation_during_final_owner_snapshots(
        tmp_path, monkeypatch, inputs, invalidating_snapshot):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    real_inputs = composition.owner._private_inputs
    real_snapshot = composition.owner._snapshot
    private_calls = 0
    final_snapshot_calls = 0
    peer_valid = True

    def tracked_inputs(frame, raw, **kwargs):
        nonlocal private_calls
        private_calls += 1
        return real_inputs(frame, raw, **kwargs)

    def invalidating_snapshot_call(transition):
        nonlocal final_snapshot_calls, peer_valid
        if private_calls == 2:
            final_snapshot_calls += 1
            if final_snapshot_calls == invalidating_snapshot:
                peer_valid = False
        return real_snapshot(transition)

    def qualify(_connection, role):
        assert role == "control"
        if not peer_valid:
            raise consumer.ReleaseConsumerError("RELEASE_PEER_UNAVAILABLE")

    monkeypatch.setattr(composition.owner, "_private_inputs", tracked_inputs)
    monkeypatch.setattr(composition.owner, "_snapshot", invalidating_snapshot_call)
    monkeypatch.setattr(
        __import__("control_plane.executive_release_owner",
                   fromlist=["_qualify_connection"]),
        "_qualify_connection", qualify)
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_PEER_UNAVAILABLE"):
        composition.start()
    assert final_snapshot_calls == 2
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


@pytest.mark.parametrize("clock", ["wall", "monotonic"])
def test_start_refuses_expiry_during_final_peer_qualification(
        tmp_path, monkeypatch, inputs, clock):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    owner_module = __import__(
        "control_plane.executive_release_owner", fromlist=["_qualify_connection"])
    calls = 0

    def expiring_peer(_connection, role):
        nonlocal calls
        assert role == "control"
        calls += 1
        if calls == 2:
            if clock == "wall":
                NOW[0] += 300_000
            else:
                MONOTONIC[0] += 300_000_000_000

    monkeypatch.setattr(owner_module, "_qualify_connection", expiring_peer)
    with pytest.raises(consumer.ReleaseConsumerError,
                       match="RELEASE_PREPARED_EXPIRED"):
        composition.start()
    assert calls == 2
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])


def test_start_rejects_owner_drift_at_final_qualifier(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    real_snapshot = composition.owner._snapshot
    drift_calls = {"count": 0}

    def drift(transition):
        drift_calls["count"] += 1
        if drift_calls["count"] == 2:
            return replace(composition.snapshot, target_observation_digest="0" * 64)
        return real_snapshot(transition)

    composition.owner._snapshot = drift
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start()


def test_start_no_mutation_on_refusal(tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    stem = actuator._operation_stem(composition.approval["operation_key"])
    snapshot_files = sorted(
        p.name for p in Path(composition.journal._root).iterdir())
    raw = composition.frame("start_reserved_release")
    raw["admission_evidence"]["admission"]["target_observation_digest"] = "0" * 64
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start(raw)
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError,
                       match="NOT_FOUND"):
        composition.journal.read(composition.approval["operation_key"])
    assert sorted(
        p.name for p in Path(composition.journal._root).iterdir()) == snapshot_files


def test_start_rejects_evidence_with_wrong_preconditions(
        tmp_path, monkeypatch, inputs):
    composition = Composition(tmp_path, monkeypatch, inputs)
    composition.reserve()
    raw = composition.frame("start_reserved_release")
    raw["admission_evidence"]["preconditions"]["production_arming_digest"] = "0" * 64
    with pytest.raises(consumer.ReleaseConsumerError):
        composition.start(raw)


# Owner START aggregate deadline regression tests.
from control_plane import executive_release_owner as owner
from control_plane.executive_release_consumer import ReleaseConsumerError
import inspect


BUDGET = 12_000_000_000


STAGES = [("snapshot", n) for n in range(1, 5)] + [
    ("peer", 1), ("peer", 2), ("evidence", 1),
    *[("authorize", n) for n in range(1, 6)],
    ("reservation", 1), ("create", 1),
]


def hook_target(composition, phase):
    return {
        "snapshot": (composition.owner, "_snapshot"),
        "peer": (owner, "_qualify_connection"),
        "evidence": (owner, "_validate_evidence"),
        "authorize": (owner, "authorize_release_transition"),
        "reservation": (composition.journal, "read_prestart_reservation"),
        "create": (composition.journal, "create"),
        "history": (composition.journal, "read"),
    }[phase]


def read_record(composition):
    return composition.journal.read(composition.approval["operation_key"])


def no_start(composition):
    with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
        read_record(composition)
    assert caught.value.code == "NOT_FOUND"


@pytest.mark.parametrize("phase,ordinal", STAGES)
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_boundary_each_owner_phase(tmp_path, monkeypatch, inputs, phase, ordinal, offset):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    target, name = hook_target(c, phase)
    original = getattr(target, name)
    calls = []

    def delayed(*args, **kwargs):
        calls.append(1)
        if phase == "create" and len(calls) == ordinal:
            MONOTONIC[0] = endpoint + offset
        result = original(*args, **kwargs)
        if phase != "create" and len(calls) == ordinal:
            MONOTONIC[0] = endpoint + offset
        return result

    monkeypatch.setattr(target, name, delayed)
    if offset < 0:
        assert c.start()["result"]["start_record"]["state"] == "STARTED"
    else:
        with pytest.raises(ReleaseConsumerError) as caught:
            c.start()
        assert "DEADLINE" in caught.value.code
        no_start(c)
    assert len(calls) >= ordinal


@pytest.mark.parametrize("phase,ordinal", [p for p in STAGES if p[0] != "create"])
def test_primary_callback_exception_survives_expiry(tmp_path, monkeypatch, inputs, phase, ordinal):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    target, name = hook_target(c, phase)
    original = getattr(target, name)
    primary = RuntimeError("primary refused " + phase)
    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        if len(calls) == ordinal:
            MONOTONIC[0] = endpoint
            raise primary
        return original(*args, **kwargs)

    monkeypatch.setattr(target, name, failing)
    with pytest.raises(RuntimeError) as caught:
        c.start()
    assert caught.value is primary
    no_start(c)


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_absent_start_history_consumes_deadline(tmp_path, monkeypatch, inputs, offset):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    original = c.journal.read
    calls = []

    def delayed(*args, **kwargs):
        calls.append(kwargs.get("deadline_monotonic_ns"))
        try:
            return original(*args, **kwargs)
        except actuator.ExecutiveReleaseActuatorJournalError as exc:
            assert exc.code == "NOT_FOUND"
            MONOTONIC[0] = endpoint + offset
            raise

    monkeypatch.setattr(c.journal, "read", delayed)
    if offset < 0:
        assert c.start()["ok"]
    else:
        with pytest.raises(ReleaseConsumerError) as caught:
            c.start()
        assert "DEADLINE" in caught.value.code
        monkeypatch.setattr(c.journal, "read", original)
        no_start(c)
    assert calls == [endpoint]


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_existing_start_history_late_return_cannot_create_again(tmp_path, monkeypatch, inputs, offset):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    first = c.start()
    endpoint = MONOTONIC[0] + BUDGET
    original_read, original_create = c.journal.read, c.journal.create
    creates = []

    def delayed(*args, **kwargs):
        result = original_read(*args, **kwargs)
        MONOTONIC[0] = endpoint + offset
        return result

    def create(*args, **kwargs):
        creates.append(kwargs)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(c.journal, "read", delayed)
    monkeypatch.setattr(c.journal, "create", create)
    if offset < 0:
        assert c.start() == first
        assert len(creates) == 1
    else:
        with pytest.raises(ReleaseConsumerError) as caught:
            c.start()
        assert "DEADLINE" in caught.value.code
        assert not creates
    assert original_read(c.approval["operation_key"]).to_dict() == first["result"]["start_record"]


def test_identical_endpoint_across_journal_and_fresh_replay_request(tmp_path, monkeypatch, inputs):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    seen = []
    for name in ("read_prestart_reservation", "read", "create"):
        original = getattr(c.journal, name)
        def recording(*args, _fn=original, _name=name, **kwargs):
            seen.append((_name, kwargs.get("deadline_monotonic_ns")))
            return _fn(*args, **kwargs)
        monkeypatch.setattr(c.journal, name, recording)
    first = c.start()
    assert seen == [(name, endpoint) for name in ("read_prestart_reservation", "read", "create")]
    MONOTONIC[0] += BUDGET * 2
    seen.clear()
    assert c.start() == first
    assert seen == [(name, endpoint + BUDGET * 2) for name in ("read_prestart_reservation", "read", "create")]
    def no_deadline(value):
        if isinstance(value, dict):
            assert not any("deadline" in key for key in value)
            for item in value.values(): no_deadline(item)
        elif isinstance(value, list):
            for item in value: no_deadline(item)
    recorded = first["result"]["start_record"]
    assert recorded["start_deadline_monotonic_ns"] == endpoint
    assert recorded["boot_id"] == recorded["preconditions"]["boot_id"]
    assert recorded["schema"] == "mastermind.executive_release_actuator_journal/v3"
    detached = copy.deepcopy(first)
    del detached["result"]["start_record"]["start_deadline_monotonic_ns"]
    no_deadline(detached)
    no_deadline(c.frame("start_reserved_release"))


def test_cumulative_snapshots_do_not_reset_request_budget(tmp_path, monkeypatch, inputs):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    original = c.owner._snapshot
    count = []
    def delayed(transition):
        count.append(1)
        result = original(transition)
        MONOTONIC[0] += BUDGET // 4
        return result
    monkeypatch.setattr(c.owner, "_snapshot", delayed)
    with pytest.raises(ReleaseConsumerError) as caught:
        c.start()
    assert "DEADLINE" in caught.value.code
    assert len(count) == 4
    no_start(c)


@pytest.mark.parametrize("offset", [0, 1])
def test_known_canonical_create_result_survives_late_return(tmp_path, monkeypatch, inputs, offset):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    original = c.journal.create
    created = []
    def delayed(**kwargs):
        record = original(**kwargs)
        created.append(record)
        MONOTONIC[0] = endpoint + offset
        return record
    monkeypatch.setattr(c.journal, "create", delayed)
    result = c.start()
    assert len(created) == 1
    assert result["result"]["start_record"] == created[0].to_dict() == read_record(c).to_dict()


@pytest.mark.parametrize("after_write", [False, True])
def test_create_primary_exception_no_reissue_or_automatic_read(tmp_path, monkeypatch, inputs, after_write):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    original_create, original_read = c.journal.create, c.journal.read
    creates, reads = [], []
    primary = RuntimeError("lost create return")
    def fail(**kwargs):
        creates.append(kwargs)
        if after_write: original_create(**kwargs)
        MONOTONIC[0] += BUDGET
        raise primary
    def read(*args, **kwargs):
        reads.append(kwargs)
        return original_read(*args, **kwargs)
    monkeypatch.setattr(c.journal, "create", fail)
    monkeypatch.setattr(c.journal, "read", read)
    with pytest.raises(RuntimeError) as caught: c.start()
    assert caught.value is primary
    assert len(creates) == len(reads) == 1
    # A separate canonical observation demonstrates the uncertainty; the failed
    # START request does not retry/create/recover itself using a new budget.
    monkeypatch.setattr(c.journal, "read", original_read)
    if after_write: assert read_record(c)["state"] == "STARTED"
    else: no_start(c)


@pytest.mark.parametrize("code", ["DEADLINE_EXCEEDED", "DEADLINE_EFFECT_UNKNOWN", "CONFLICT", "RECORD_REPLACED"])
def test_existing_journal_error_code_is_not_masked(tmp_path, monkeypatch, inputs, code):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    calls = []
    def fail(**kwargs):
        calls.append(kwargs)
        MONOTONIC[0] += BUDGET
        raise actuator.ExecutiveReleaseActuatorJournalError(code)
    monkeypatch.setattr(c.journal, "create", fail)
    with pytest.raises(ReleaseConsumerError) as caught: c.start()
    assert caught.value.code == "RELEASE_ROOT_JOURNAL_" + code
    assert len(calls) == 1


def test_public_handle_signature_unchanged():
    assert str(inspect.signature(owner.ReleaseBrokerOwner.handle)) == "(self, raw, connection)"


def test_handle_establishes_endpoint_before_private_frame(tmp_path, monkeypatch, inputs):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    began = MONOTONIC[0]
    seen = []
    expected = object()
    def observe(raw, connection, *, deadline_monotonic_ns=None):
        seen.append(deadline_monotonic_ns)
        return expected
    monkeypatch.setattr(c.owner, "_start_reserved_release", observe)
    assert c.start() is expected
    assert seen == [began + BUDGET]


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_real_journal_post_publish_boundary_preserves_durable_truth(tmp_path, monkeypatch, inputs, offset):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    original = c.journal._publish_start
    calls = []
    def delayed(*args, **kwargs):
        calls.append(kwargs.get("deadline_monotonic_ns"))
        result = original(*args, **kwargs)
        MONOTONIC[0] = endpoint + offset
        return result
    monkeypatch.setattr(c.journal, "_publish_start", delayed)
    if offset < 0:
        assert c.start()["result"]["start_record"]["state"] == "STARTED"
    else:
        with pytest.raises(ReleaseConsumerError) as caught: c.start()
        assert caught.value.code == "RELEASE_ROOT_JOURNAL_DEADLINE_EFFECT_UNKNOWN"
    assert calls == [endpoint]
    # This is a distinct read observation, never an automatic retry in START.
    assert c.journal.read(c.approval["operation_key"])["state"] == "STARTED"


@pytest.mark.parametrize("ordinal", [1, 2, 3])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_same_deadline_before_each_actual_journal_lock(tmp_path, monkeypatch, inputs, ordinal, offset):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    endpoint = MONOTONIC[0] + BUDGET
    original = c.journal._locked
    calls = []
    def delayed(*args, **kwargs):
        calls.append(kwargs.get("deadline_monotonic_ns"))
        if len(calls) == ordinal: MONOTONIC[0] = endpoint + offset
        return original(*args, **kwargs)
    monkeypatch.setattr(c.journal, "_locked", delayed)
    if offset < 0: assert c.start()["ok"]
    else:
        with pytest.raises(ReleaseConsumerError) as caught: c.start()
        assert caught.value.code == "RELEASE_ROOT_JOURNAL_DEADLINE_EXCEEDED"
    assert calls and set(calls) == {endpoint}
    if offset >= 0: assert len(calls) == ordinal
    monkeypatch.setattr(c.journal, "_locked", original)
    if offset >= 0:
        with pytest.raises(actuator.ExecutiveReleaseActuatorJournalError) as caught:
            c.journal.read(c.approval["operation_key"])
        assert caught.value.code == "NOT_FOUND"


def test_reserve_has_no_deadline_keyword_or_ambient_budget(tmp_path, monkeypatch, inputs):
    c = Composition(tmp_path, monkeypatch, inputs)
    initial_dict = copy.copy(c.owner.__dict__)
    original = c.journal._locked
    seen = []
    def record(*args, **kwargs):
        seen.append(kwargs)
        return original(*args, **kwargs)
    monkeypatch.setattr(c.journal, "_locked", record)
    c.reserve()
    assert all("deadline_monotonic_ns" not in kw for kw in seen)
    c.start()
    assert c.owner.__dict__ == initial_dict


@pytest.mark.parametrize("endpoint", [False, True, 0, -1, 1.2, "42", 1 << 63])
def test_private_endpoint_validation_prevents_dependent_effects(tmp_path, monkeypatch, inputs, endpoint):
    c = Composition(tmp_path, monkeypatch, inputs)
    c.reserve()
    calls = []
    monkeypatch.setattr(owner, "_qualify_connection", lambda *a, **kw: calls.append("peer"))
    with pytest.raises(ReleaseConsumerError) as caught:
        c.owner._start_reserved_release(c.frame("start_reserved_release"), object(), deadline_monotonic_ns=endpoint)
    assert "INVALID" in caught.value.code
    assert not calls


@pytest.mark.parametrize('phase',['PUBLICATION_INTENT','PUBLISHED','BROKER_RESTART_PENDING','RECOVERING','SUCCEEDED','ROLLED_BACK'])
def test_owner_projects_exact_new_protocol_journal_without_effect(tmp_path,monkeypatch,inputs,phase):
    c=Composition(tmp_path,monkeypatch,inputs);reserved=c.reserve()['result']['reservation']
    record=c.start()['result']['start_record'];original=dict(record)
    phases=['PUBLICATION_INTENT','PUBLISHED','BROKER_RESTART_PENDING','RECOVERING']
    for step in phases:
        record=c.journal.advance(c.approval['operation_key'],expected_generation=record['journal_generation'],
            state=step,reservation=reserved,approval=c.approval)
        if step==phase:break
    if phase in ('SUCCEEDED','ROLLED_BACK'):
        before=reserved['before'];after=copy.deepcopy(before)
        if phase=='SUCCEEDED':
            effect=c.approval['normalized_requested_effect']
            after.update(release_commit=effect['to_release_commit'],release_tree=effect['to_release_tree'],
                broker_source_commit=effect['to_release_commit'],broker_source_tree=effect['to_release_tree'])
        rollback={'attempted':False} if phase=='SUCCEEDED' else {'attempted':True,'restored_preimage_digest':digest(before)}
        record=c.journal.advance(c.approval['operation_key'],expected_generation=record['journal_generation'],
            state=phase,reservation=reserved,approval=c.approval,completed_at_ms=NOW[0]+1,
            postcondition_digest='f'*64,before=before,after=after,rollback=rollback,
            after_actuator_generation=record['actuator_generation']+(1 if phase=='SUCCEEDED' else 2))
    status=c.owner._closure_status(record,reserved,digest(reserved),record['admission'],c.approval)
    assert status['schema']=='mastermind.executive_release_terminal_status/v2' and status['state']==phase
    assert status['before']==reserved['before']
    assert status['start_deadline_monotonic_ns']==original['start_deadline_monotonic_ns']
    assert status['preconditions']['boot_id']==original['boot_id']
    if phase in ('SUCCEEDED','ROLLED_BACK'):
        receipt=status['terminal_receipt']
        assert receipt['after_actuator_generation']==record['terminal']['after_actuator_generation']
        assert receipt['publication_intent_digest']==digest(record['publication_intent'])


# R2 preserves the original authority deadline during bounded replay.
def test_owner_shorter_replay_io_budget(tmp_path,monkeypatch,inputs):
    comp=Composition(tmp_path,monkeypatch,inputs);comp.reserve();first=comp.start();before=(comp.journal._root/comp.journal._name(comp.approval['operation_key'])).read_bytes()
    record=first['result']['start_record'];shorter=MONOTONIC[0]+1_000_000_000
    assert shorter<record['start_deadline_monotonic_ns']
    replay=comp.owner._start_reserved_release(comp.frame('start_reserved_release'),object(),deadline_monotonic_ns=shorter)
    assert replay==first and (comp.journal._root/comp.journal._name(comp.approval['operation_key'])).read_bytes()==before
