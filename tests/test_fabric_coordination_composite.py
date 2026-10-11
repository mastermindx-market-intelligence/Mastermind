"""Mixed native/Runtime hierarchy evidence through existing read-only owners.

Source-composed fixtures, never actual native provider execution or permission.
"""
from dataclasses import replace

import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationNativeIdentity, CoordinationParticipant, CoordinationRole,
    authorize_coordination,
)
from integrations.fabric_coordination_composite import (
    CompositeCoordinationObservationSource as Source,
    CompositeCoordinationUnavailable,
)
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
from tests.test_fabric_coordination_runtime import setup
from tests.test_session_bridge_claude_native import Port, session, SESSION

NATIVE = CoordinationNativeIdentity(SESSION, "gen-001", "m2studio", "principal-1")
NOW = 1789344000


def native_member():
    return CoordinationParticipant(
        NATIVE, CoordinationRole.COO,
        tenant_ref="fixture-tenant", portfolio_ref="fixture-portfolio",
        project_ref="fixture-project", program_ref="fixture-program",
    )


def fixture(tmp_path, monkeypatch, *, port=None, reader=None):
    seed, _, _, owner, _ = setup(tmp_path, monkeypatch)
    source = native_member()
    owner.snapshot = replace(owner.snapshot, participants=(
        replace(owner.participants[0], parent_identity=NATIVE),
        owner.participants[1], source,
    ))
    p = port or Port()
    obs = Source(
        runtime=seed.runtime,
        native_projector=ClaudeNativeTargetProjector(p),
        membership_reader=reader or (lambda: owner.snapshot),
        native_principal_reader=lambda sid, host: "principal-1"
            if (sid, host) == (SESSION, "m2studio") else "foreign",
    )
    return obs, owner, p


def deny(observation):
    with pytest.raises(CompositeCoordinationUnavailable, match="COMPOSITE_COORDINATION_UNAVAILABLE"):
        observation.observe()


def test_composite_attests_native_coo_and_actual_runtime_worker_parent(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    evidence = observation.observe()
    assert len(evidence.worker_peer_refs) == 2
    assert evidence.native_ids == (NATIVE,)
    assert len(evidence.evidence_digest) == 64
    assert evidence.snapshot.revision == owner.snapshot.revision
    assert authorize_coordination(evidence.snapshot, NATIVE,
        owner.participants[0].identity, topic_ref="schema",
        now=evidence.snapshot.observed_at + 1).relation == "direct_parent_child"
    assert port.send_calls == [] and port.reconcile_calls == []


def test_composite_refuses_native_manager_generation_drift(tmp_path, monkeypatch):
    port = Port()
    port.current[SESSION] = session(generation="gen-002")
    observation, _, port = fixture(tmp_path, monkeypatch, port=port)
    deny(observation)
    assert not port.send_calls


def test_composite_refuses_false_runtime_worker(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    malformed = replace(owner.snapshot.participants[0], identity=replace(
        owner.participants[0].identity, worker_id="invented-worker",
    ))
    owner.snapshot = replace(owner.snapshot,
                             participants=(malformed, *owner.snapshot.participants[1:]))
    deny(observation)
    assert not port.send_calls


def test_composite_refuses_mid_read_scope_mutation(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    counter = [0]
    def drift():
        counter[0] += 1
        if counter[0] > 3:
            owner.snapshot = replace(owner.snapshot, revision="other-revision")
        return owner.snapshot
    observation._memberships = drift
    deny(observation)
    assert not port.send_calls


def test_composite_requires_both_native_and_worker_sources(tmp_path, monkeypatch):
    observation, owner, _ = fixture(tmp_path, monkeypatch)
    whole = owner.snapshot
    owner.snapshot = replace(whole, participants=(native_member(),))
    deny(observation)
    owner.snapshot = replace(whole, participants=whole.participants[:2])
    deny(observation)


def test_no_sender_identity_from_public_args(tmp_path, monkeypatch):
    observation, _, _ = fixture(tmp_path, monkeypatch)
    evidence = observation.observe()
    assert "send" not in vars(type(observation))  # no transport operation
    assert "sender" not in evidence.__dataclass_fields__
    assert "authorized" not in evidence.__dataclass_fields__


def test_native_rotation_during_worker_recheck_refuses(tmp_path, monkeypatch):
    """A rotated COO must not be trusted after workers are re-attested."""
    from integrations.fabric_coordination_runtime import RuntimeCoordinationObservationSource
    observation, _, port = fixture(tmp_path, monkeypatch)
    original = RuntimeCoordinationObservationSource.observe
    count = [0]

    def rotate_after_second_worker_observation(self):
        result = original(self)
        count[0] += 1
        if count[0] == 2:
            port.current[SESSION] = session(generation="gen-002")
        return result

    monkeypatch.setattr(RuntimeCoordinationObservationSource, "observe",
                        rotate_after_second_worker_observation)
    deny(observation)
    assert count[0] == 2
    assert port.send_calls == [] and port.reconcile_calls == []


def test_scope_expiring_after_last_owner_read_refuses(tmp_path, monkeypatch):
    """Expiration after both owner reads is not extended by prior admission."""
    from integrations.fabric_coordination_native import NativeCoordinationObservationSource
    from integrations.fabric_coordination_runtime import RuntimeCoordinationObservationSource
    observation, owner, port = fixture(tmp_path, monkeypatch)
    real_native = NativeCoordinationObservationSource.observe
    real_now = RuntimeCoordinationObservationSource.now
    native_reads = [0]
    after_both_owner_reads = [False]

    def last_native_read(self):
        result = real_native(self)
        native_reads[0] += 1
        if native_reads[0] == 2:
            after_both_owner_reads[0] = True
        return result

    def clock(self):
        if after_both_owner_reads[0]:
            return owner.snapshot.valid_until
        return real_now(self)

    monkeypatch.setattr(NativeCoordinationObservationSource, "observe", last_native_read)
    monkeypatch.setattr(RuntimeCoordinationObservationSource, "now", clock)
    deny(observation)
    assert native_reads[0] == 2
    assert not port.send_calls and not port.reconcile_calls


def test_worker_rotation_during_native_join_refuses(tmp_path, monkeypatch):
    from integrations.fabric_coordination_runtime import RuntimeCoordinationObservationSource
    observation, _, port = fixture(tmp_path, monkeypatch)
    original = RuntimeCoordinationObservationSource.observe
    count = [0]
    def changed(self):
        result = original(self)
        count[0] += 1
        if count[0] == 2:
            # A second owner observation reports a different Runtime generation.
            return replace(result, snapshot=replace(
                result.snapshot, revision="runtime-binding-rotated",
            ))
        return result
    monkeypatch.setattr(RuntimeCoordinationObservationSource, "observe", changed)
    deny(observation)
    assert count[0] == 2
    assert port.send_calls == []


def test_same_owner_revision_with_changed_membership_changes_evidence_digest(tmp_path, monkeypatch):
    observation, owner, port = fixture(tmp_path, monkeypatch)
    original = observation.observe()
    members = owner.snapshot.participants
    owner.snapshot = replace(owner.snapshot, participants=(
        replace(members[0], coordination_group_ref="different-group"),
        *members[1:],
    ))
    changed = observation.observe()
    assert original.snapshot.revision == changed.snapshot.revision
    assert original.evidence_digest != changed.evidence_digest
    assert port.send_calls == []


def test_native_attestation_must_bind_full_organizational_scope(tmp_path, monkeypatch):
    """The native owner cannot attest foreign role/grant facts under same label."""
    from integrations.fabric_coordination_native import NativeCoordinationObservationSource
    observation, _, port = fixture(tmp_path, monkeypatch)
    original = NativeCoordinationObservationSource.observe

    def tampered(self):
        proof = original(self)
        return replace(proof, membership_digest="0" * 64)

    monkeypatch.setattr(NativeCoordinationObservationSource, "observe", tampered)
    deny(observation)
    assert not port.send_calls and not port.reconcile_calls
