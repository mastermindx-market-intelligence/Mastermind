"""Attest native CEO/COO membership with the existing Claude management owner.

Fake manager and host principal reader. No native session, credentials, Slack,
messages, wake, or installed host is involved. Success is SOURCE proof only.
"""
from dataclasses import replace

import pytest

from control_plane.fabric_coordination_policy import (
    CoordinationIdentity, CoordinationNativeIdentity, CoordinationParticipant,
    CoordinationRole, CoordinationSnapshot,
)
from integrations.fabric_coordination_native import (
    NativeCoordinationObservationSource as Source, NativeCoordinationUnavailable,
)
from integrations.session_bridge.claude_native import ClaudeNativeTargetProjector
from tests.test_session_bridge_claude_native import Port, session, SESSION

NATIVE = CoordinationNativeIdentity(SESSION, "gen-001", "m2studio", "principal-1")
NOW = 1000


def participant(identity=NATIVE, *, role=CoordinationRole.COO, active=True):
    return CoordinationParticipant(
        identity=identity, role=role, tenant_ref="tenant", portfolio_ref="portfolio",
        project_ref="project", program_ref="program", active=active,
    )


def scope(*members):
    return CoordinationSnapshot("owner-revision-1", NOW, NOW + 25, tuple(members))


def setup(*, owner_scope=None, manager=None, principal_reader=None, now=None):
    port = manager or Port()
    host_scope = [owner_scope or scope(participant())]
    read_calls = []
    def read_membership():
        read_calls.append(host_scope[0])
        return host_scope[0]
    principals = principal_reader or (lambda sid, host: "principal-1"
                                      if (sid, host) == (SESSION, "m2studio")
                                      else "unexpected")
    verifier = Source(projector=ClaudeNativeTargetProjector(port),
                      membership_reader=read_membership,
                      principal_reader=principals,
                      now=now or (lambda: NOW + 1))
    return verifier, port, host_scope, read_calls


def refused(verifier):
    with pytest.raises(NativeCoordinationUnavailable, match="NATIVE_COORDINATION_UNAVAILABLE"):
        verifier.observe()


def test_native_owner_join_has_no_provider_effect_or_runtime_job():
    verifier, port, _, calls = setup()
    attestation = verifier.observe()
    assert attestation.identities == (NATIVE,)
    assert attestation.snapshot_revision == "owner-revision-1"
    assert attestation.valid_until == NOW + 25
    assert len(calls) == 2
    assert port.send_calls == [] and port.reconcile_calls == []


def test_reading_native_participants_never_attests_unchecked_runtime_worker():
    worker = CoordinationIdentity("JOB-1", "ATT-1", "worker", "bind-1", 1)
    runtime_member = CoordinationParticipant(
        identity=worker, role=CoordinationRole.WORKER,
        tenant_ref="tenant", portfolio_ref="portfolio", project_ref="project",
        program_ref="program", workstream_ref="ws", coordination_group_ref="g",
    )
    verifier, port, *_ = setup(owner_scope=scope(participant(), runtime_member))
    assert verifier.observe().identities == (NATIVE,)
    assert not port.send_calls


@pytest.mark.parametrize("changed", [
    replace(NATIVE, session_id="11111111-2222-4333-8444-555555555555"),
    replace(NATIVE, generation="gen-002"),
    replace(NATIVE, host_ref="other-host"),
    replace(NATIVE, principal_ref="foreign-principal"),
])
def test_foreign_or_rotated_native_owner_fails_closed(changed):
    verifier, port, *_ = setup(owner_scope=scope(participant(changed)))
    refused(verifier)
    assert port.send_calls == []


def test_manager_revoked_addressability_refuses():
    port = Port([session(addressable=False)])
    verifier, _, *_ = setup(manager=port)
    refused(verifier)


def test_manager_get_session_generation_drift_refuses():
    port = Port()
    port.current[SESSION] = session(generation="gen-002")
    verifier, _, *_ = setup(manager=port)
    refused(verifier)


def test_manager_list_generation_drift_after_initial_join_refuses():
    class DriftPort(Port):
        def __init__(self):
            super().__init__()
            self.calls = 0
        def list_sessions(self):
            self.calls += 1
            if self.calls >= 3:
                self.sessions[0] = session(generation="gen-003")
            return super().list_sessions()
    verifier, port, *_ = setup(manager=DriftPort())
    refused(verifier)
    assert port.send_calls == []


def test_membership_change_during_join_refuses_even_if_revision_unchanged():
    verifier, port, scopes, calls = setup()
    original = verifier._memberships

    def mutate():
        x = original()
        if len(calls) == 1:
            scopes[0] = replace(x, participants=(replace(participant(), active=False),))
        return x

    verifier._memberships = mutate
    refused(verifier)
    assert port.send_calls == []


def test_principal_change_during_join_refuses():
    calls = [0]
    def principal(sid, host):
        calls[0] += 1
        return "principal-1" if calls[0] == 1 else "rotated-principal"
    verifier, port, *_ = setup(principal_reader=principal)
    refused(verifier)
    assert not port.send_calls


def test_owner_scope_expiry_refuses():
    verifier, *_ = setup(now=lambda: NOW + 25)
    refused(verifier)


def test_new_observation_cannot_extend_original_expiry():
    verifier, _, scopes, calls = setup()
    first = verifier._memberships
    def refreshed():
        x = first()
        if len(calls) == 2:
            return replace(x, observed_at=NOW + 1, valid_until=NOW + 26)
        return x
    verifier._memberships = refreshed
    assert verifier.observe().valid_until == NOW + 25


def test_no_admitted_live_native_member_refuses():
    verifier, *_ = setup(owner_scope=scope(participant(active=False)))
    refused(verifier)


def test_callback_exception_sanitized():
    def failed(*args):
        raise RuntimeError("secret manager credential")
    verifier, *_ = setup(principal_reader=failed)
    with pytest.raises(NativeCoordinationUnavailable) as error:
        verifier.observe()
    assert str(error.value) == "NATIVE_COORDINATION_UNAVAILABLE"
    assert "secret" not in str(error.value)


def test_invalid_callback_shapes_cannot_pass_constructor():
    async def asynchronous():
        return scope(participant())
    with pytest.raises(TypeError):
        Source(projector=ClaudeNativeTargetProjector(Port()),
               membership_reader=asynchronous,
               principal_reader=lambda s, h: "principal-1",
               now=lambda: NOW + 1)
