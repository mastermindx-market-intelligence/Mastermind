"""Runtime identity join and real dispatcher journey; no live admission proof.

Organizational assignments and native consumption signals are synthetic. The
Job/Attempt/OHF state, consultation dispatcher, and local socket path are real
implementations operating only in temporary test state.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile

import pytest

from control_plane.fabric_coordination_policy import CoordinationIdentity, CoordinationRefused
from integrations.fabric_coordination_runtime import (
    RuntimeCoordinationObservationSource as Source, RuntimeCoordinationUnavailable,
    build_runtime_coordination_gateway as build,
)
from integrations.mastermind_company_mcp.consultation import COMPANY_CONSULTATION_TOOL_SCHEMA_DIGEST as DIGEST
from tests import test_company_inbox_iac1 as fixtures
from tests.test_company_consultation_target_resolution import _seed, _event_count
from tests.test_company_consultation_targeted_dispatch import _bindings, _client_and_sources, _dispatch
from tests.test_fabric_coordination_journey import FixtureOwner, TOPIC, _request


def setup(tmp_path, monkeypatch):
    seed = _seed(tmp_path, monkeypatch, physical=False)
    bindings = _bindings(seed)
    client = _client_and_sources(seed, bindings)
    owner = FixtureOwner(seed)
    now = seed.runtime.store.now_ms() // 1000
    owner.participants = tuple(replace(
        member, parent_job_id=seed.runtime.jobs.get_job(member.identity.job_id).parent_job_id,
    ) for member in owner.participants)
    owner.snapshot = replace(owner.snapshot, participants=owner.participants,
                             observed_at=now, valid_until=now+30)
    source = Source(seed.runtime, membership_reader=lambda: owner.snapshot)
    return seed, bindings, client, owner, source


def test_current_runtime_identities_are_projected_without_effects(tmp_path, monkeypatch):
    seed, _, _, owner, source = setup(tmp_path, monkeypatch)
    before = _event_count(seed)
    first, second = source.observe(), source.observe()
    assert first == second
    assert first.snapshot.revision.startswith("runtime-")
    assert len(first.peers) == 2
    assert len({peer.peer_ref for peer in first.peers}) == 2
    for member, peer in zip(owner.participants, first.peers):
        assert peer.actor_ref["attempt_id"] == member.identity.attempt_id
        assert peer.binding["binding_id"] == member.identity.binding_id
        assert peer.program_ref == member.program_ref
        assert set(peer.binding) == {"binding_id", "binding_generation", "reasoning_surface"}
        assert "account" not in str(peer.public_projection())
        assert "thread-" not in str(peer.public_projection())
    assert _event_count(seed) == before


@pytest.mark.parametrize("field,value", [
    ("job_id", "JOB-999999"), ("attempt_id", "ATT-missing"),
    ("worker_id", "foreign-worker"), ("binding_id", "bind-" + "f" * 40),
    ("binding_generation", 999),
])
def test_fictional_or_stale_owner_identity_cannot_become_peer(tmp_path, monkeypatch, field, value):
    seed, _, _, owner, source = setup(tmp_path, monkeypatch)
    first, second = owner.participants
    wrong = replace(second, identity=replace(second.identity, **{field: value}))
    owner.snapshot = replace(owner.snapshot, participants=(first, wrong))
    before = _event_count(seed)
    with pytest.raises(RuntimeCoordinationUnavailable, match="^RUNTIME_COORDINATION_UNAVAILABLE$"):
        source.observe()
    assert _event_count(seed) == before


@pytest.mark.parametrize("change", [
    {"parent_job_id": "JOB-other-parent"}, {"parent_job_id": None},
    {"program_ref": "JOB-other/operation"},
])
def test_scope_cannot_forge_runtime_parent_or_program(tmp_path, monkeypatch, change):
    _, _, _, owner, source = setup(tmp_path, monkeypatch)
    owner.snapshot = replace(owner.snapshot, participants=(
        owner.participants[0], replace(owner.participants[1], **change),
    ))
    with pytest.raises(RuntimeCoordinationUnavailable):
        source.observe()


def test_expired_membership_does_not_get_refreshed_by_runtime_read(tmp_path, monkeypatch):
    _, _, _, owner, source = setup(tmp_path, monkeypatch)
    now = source.now()
    owner.snapshot = replace(owner.snapshot, observed_at=now-40, valid_until=now-10)
    with pytest.raises(RuntimeCoordinationUnavailable):
        source.observe()


def test_membership_change_during_join_refuses_instead_of_torn_snapshot(tmp_path, monkeypatch):
    seed, _, _, owner, _ = setup(tmp_path, monkeypatch)
    calls = []
    def reader():
        calls.append(1)
        return owner.snapshot if len(calls) == 1 else replace(owner.snapshot, revision="changed")
    with pytest.raises(RuntimeCoordinationUnavailable):
        Source(seed.runtime, membership_reader=reader).observe()
    assert len(calls) == 2


def test_unaccepted_provider_mapping_is_not_silently_enabled(tmp_path, monkeypatch):
    seed, _, _, _, source = setup(tmp_path, monkeypatch)
    original = seed.runtime.current_harness_binding_source
    def other(_runtime, *args, **kwargs):
        return replace(original(*args, **kwargs), provider="not-an-admitted-provider")
    monkeypatch.setattr(type(seed.runtime), "current_harness_binding_source", other)
    with pytest.raises(RuntimeCoordinationUnavailable):
        source.observe()


def test_runtime_error_is_sanitized_and_does_not_publish(tmp_path, monkeypatch):
    seed, _, _, _, source = setup(tmp_path, monkeypatch)
    before = _event_count(seed)
    def unavailable(*args, **kwargs):
        raise RuntimeError("private SQL native handle account data")
    monkeypatch.setattr(type(seed.runtime), "current_harness_binding_source", unavailable)
    with pytest.raises(RuntimeCoordinationUnavailable) as error:
        source.observe()
    assert str(error.value) == "RUNTIME_COORDINATION_UNAVAILABLE"
    assert _event_count(seed) == before


def test_inactive_member_is_not_projected_as_live(tmp_path, monkeypatch):
    _, _, _, owner, source = setup(tmp_path, monkeypatch)
    owner.snapshot = replace(owner.snapshot, participants=(
        owner.participants[0], replace(owner.participants[1], active=False),
    ))
    observed = source.observe()
    assert len(observed.peers) == 1
    assert observed.peers[0].actor_ref["job_id"] == owner.participants[0].identity.job_id


def test_factory_rejects_nonmember_caller(tmp_path, monkeypatch):
    seed, _, _, owner, _ = setup(tmp_path, monkeypatch)
    calls = []
    async def dispatch(*args):
        calls.append(args)
    with pytest.raises(CoordinationRefused):
        build(runtime=seed.runtime, caller=replace(owner.participants[0].identity, worker_id="wrong"),
              membership_reader=lambda: owner.snapshot, consultation_parties=owner.parties,
              topic_ref=TOPIC, dispatcher=dispatch, utc_now=lambda: "2026-09-14T00:00:00Z", observed_tool_schema_digest=DIGEST)
    assert calls == []


def test_runtime_factory_question_reply_and_consume_journey(tmp_path, monkeypatch):
    seed, bindings, client, owner, source = setup(tmp_path, monkeypatch)
    async def scenario():
        with tempfile.TemporaryDirectory(prefix="fabric-runtime-", dir="/tmp") as root:
            socket = Path(root) / "relay.sock"
            service, task = await fixtures._start_relay_service(socket_path=socket, client=client)
            try:
                def gateway(index, dispatcher):
                    return build(runtime=seed.runtime, caller=owner.participants[index].identity,
                                 membership_reader=lambda: owner.snapshot,
                                 consultation_parties=owner.parties, topic_ref=TOPIC,
                                 dispatcher=dispatcher, utc_now=lambda: "2026-09-14T00:00:00Z", observed_tool_schema_digest=DIGEST)
                sender_dispatcher = _dispatch(seed, bindings, socket)
                sender = gateway(0, sender_dispatcher)
                peers = await sender.call("company.peers", {})
                assert peers["ok"] is True, peers
                args = dict(_request(seed), to=peers["data"]["peers"][0]["peer_ref"])
                sent = await sender.call("company.consult", args)
                assert sent["ok"] is True, sent
                reference = sent["data"]["consultation_ref"]
                parties = source.verify_parties(owner.parties(reference))
                assert parties.recipient == owner.participants[1].identity
                with pytest.raises(RuntimeCoordinationUnavailable):
                    source.verify_parties(replace(parties, requester=replace(parties.requester, worker_id="impostor")))
                # The persisted requester epoch is just as important as the
                # recipient: a successor may not consume an older requester's
                # answer after a silent binding rearm under the same actor IDs.
                with pytest.raises(RuntimeCoordinationUnavailable):
                    source.verify_parties(replace(parties, requester=replace(
                        parties.requester,
                        binding_generation=parties.requester.binding_generation + 1,
                    )))
                with pytest.raises(RuntimeCoordinationUnavailable):
                    source.verify_parties(replace(parties, requester=replace(
                        parties.requester, binding_id="bind-" + "a" * 40,
                    )))
                # Remap only the requester provider; recipient stays exactly
                # current. This must NOT pass merely because its actor triple
                # and old binding ID/generation are unchanged.
                original_source = seed.runtime.current_harness_binding_source
                original_requester_facts = original_source(parties.requester.attempt_id)
                alternate = (
                    "openai-codex" if original_requester_facts.provider != "openai-codex"
                    else "chatgpt"
                )
                with monkeypatch.context() as patched:
                    def requester_provider_remap(_runtime, attempt_id, *args, **kwargs):
                        facts = original_source(attempt_id, *args, **kwargs)
                        if attempt_id == parties.requester.attempt_id:
                            return replace(facts, provider=alternate)
                        return facts
                    patched.setattr(
                        type(seed.runtime), "current_harness_binding_source",
                        requester_provider_remap,
                    )
                    with pytest.raises(RuntimeCoordinationUnavailable):
                        source.verify_parties(parties)
                # The persisted consultation pins the original recipient epoch.
                # A replacement binding may have the same Job/Attempt/Worker.
                with pytest.raises(RuntimeCoordinationUnavailable):
                    source.verify_parties(replace(parties, recipient=replace(
                        parties.recipient, binding_generation=parties.recipient.binding_generation + 1,
                    )))
                with pytest.raises(RuntimeCoordinationUnavailable):
                    source.verify_parties(replace(parties, recipient=replace(
                        parties.recipient, binding_id="bind-" + "0" * 40,
                    )))
                # The persisted recipient surface is immutable across an
                # unchanged Attempt/binding: a provider remap cannot inherit
                # the older consultation.
                with monkeypatch.context() as patched:
                    patched.setattr(
                        "integrations.fabric_coordination_runtime.reasoning_surface_for_provider",
                        lambda provider: "claude",
                    )
                    with pytest.raises(RuntimeCoordinationUnavailable):
                        source.verify_parties(parties)
                receiver = gateway(1, _dispatch(seed, bindings, socket, caller_index=1))
                read = await receiver.call("company.consultation", {"consultation_ref": reference})
                assert read["ok"] is True, read
                fixtures._deliver_and_ack_wake_path(seed.runtime, reference)
                answered = await receiver.call("company.reply", {
                    "consultation_ref": reference, "answer": "Use the attached exact interface revision.",
                    "evidence_refs": [],
                })
                assert answered["ok"] is True, answered
                answer = await sender.call("company.consultation", {"consultation_ref": reference})
                assert answer["ok"] is True, answer
                assert answer["data"]["answer"]["text"] == "Use the attached exact interface revision."
                assert fixtures._consultation_event_count(seed.runtime, reference, "INTENT") == 1
                assert fixtures._consultation_event_count(seed.runtime, reference, "ANSWER_AVAILABLE") == 1
                consumed = await sender_dispatcher.consume_answer(reference)
                assert consumed["state"] == "CONSUMED"
                assert (await sender_dispatcher.consume_answer(reference))["inserted"] is False
            finally:
                await fixtures._stop_relay_service(service, task)
    asyncio.run(scenario())


def test_membership_refresh_does_not_widen_original_expiry(tmp_path, monkeypatch):
    seed, _, _, owner, source = setup(tmp_path, monkeypatch)
    now = source.now()
    original = replace(owner.snapshot, observed_at=now-5, valid_until=now+20)
    fresh = replace(owner.snapshot, observed_at=now, valid_until=now+30)
    calls = []
    def reader():
        calls.append(1)
        return original if len(calls) == 1 else fresh
    joined = Source(seed.runtime, membership_reader=reader).observe()
    assert joined.snapshot.valid_until == original.valid_until
    assert joined.snapshot.observed_at == original.observed_at


def test_same_revision_cannot_hide_membership_mutation(tmp_path, monkeypatch):
    seed, _, _, owner, _ = setup(tmp_path, monkeypatch)
    changed = replace(owner.snapshot, participants=(owner.participants[0],
        replace(owner.participants[1], coordination_group_ref="changed")))
    calls = []
    def reader():
        calls.append(1)
        return owner.snapshot if len(calls) == 1 else changed
    with pytest.raises(RuntimeCoordinationUnavailable):
        Source(seed.runtime, membership_reader=reader).observe()


def test_full_scope_changes_the_joined_digest_even_when_revision_label_is_reused(tmp_path, monkeypatch):
    _, _, _, owner, source = setup(tmp_path, monkeypatch)
    before = source.observe()
    owner.snapshot = replace(owner.snapshot, participants=(owner.participants[0],
        replace(owner.participants[1], coordination_group_ref="changed")))
    after = source.observe()
    assert before.snapshot.revision != after.snapshot.revision


def test_expiry_during_runtime_read_refuses(tmp_path, monkeypatch):
    _, _, _, owner, source = setup(tmp_path, monkeypatch)
    times = iter((owner.snapshot.observed_at, owner.snapshot.valid_until))
    monkeypatch.setattr(source, "now", lambda: next(times))
    with pytest.raises(RuntimeCoordinationUnavailable):
        source.observe()


def test_runtime_owner_seat_does_not_promote_workers_to_coos(tmp_path, monkeypatch):
    seed, _, _, owner, source = setup(tmp_path, monkeypatch)
    joined = source.observe()
    for member, peer in zip(owner.participants, joined.peers):
        assert seed.runtime.jobs.get_job(member.identity.job_id).owner_seat == "coo"
        assert member.role.value == "worker"
        assert peer.display_name == "worker"


def test_gateway_rechecks_runtime_after_construction(tmp_path, monkeypatch):
    seed, _, _, owner, _ = setup(tmp_path, monkeypatch)
    calls = []
    async def dispatcher(*args):
        calls.append(args)
        return {"ok": True, "result": {}}
    gateway = build(runtime=seed.runtime, caller=owner.participants[0].identity,
                    membership_reader=lambda: owner.snapshot,
                    consultation_parties=owner.parties, topic_ref=TOPIC,
                    dispatcher=dispatcher, utc_now=lambda: "2026-09-14T00:00:00Z", observed_tool_schema_digest=DIGEST)
    peers = asyncio.run(gateway.call("company.peers", {}))
    target = peers["data"]["peers"][0]["peer_ref"]
    owner.snapshot = replace(owner.snapshot, participants=(owner.participants[0],
        replace(owner.participants[1], coordination_group_ref="revoked")))
    before = _event_count(seed)
    response = asyncio.run(gateway.call("company.consult", dict(_request(seed), to=target)))
    assert response["error"]["code"] == "BINDING_UNAVAILABLE"
    assert calls == []
    assert _event_count(seed) == before


def test_missing_intent_does_not_make_owner_party_assertion_authoritative(tmp_path, monkeypatch):
    from integrations.fabric_coordination import CoordinationConsultationParties
    seed, _, _, owner, source = setup(tmp_path, monkeypatch)
    parties = CoordinationConsultationParties("consult-" + "a" * 32,
        owner.participants[0].identity, owner.participants[1].identity, TOPIC)
    before = _event_count(seed)
    with pytest.raises(RuntimeCoordinationUnavailable):
        source.verify_parties(parties)
    assert _event_count(seed) == before


def test_factory_does_not_self_attest_the_observed_tool_schema(tmp_path, monkeypatch):
    seed, _, _, owner, _ = setup(tmp_path, monkeypatch)
    calls = []
    async def dispatcher(*args):
        calls.append(args)
        return {"ok": True, "result": {}}
    gateway = build(runtime=seed.runtime, caller=owner.participants[0].identity,
                    membership_reader=lambda: owner.snapshot,
                    consultation_parties=owner.parties, topic_ref=TOPIC,
                    dispatcher=dispatcher, utc_now=lambda: "2026-09-14T00:00:00Z",
                    observed_tool_schema_digest="not-current")
    before = _event_count(seed)
    result = asyncio.run(gateway.call("company.peers", {}))
    assert result["error"]["code"] == "CAPABILITY_NOT_ATTESTED"
    assert calls == []
    assert _event_count(seed) == before


def test_worker_runtime_gateway_does_not_claim_native_ceo_enrollment(tmp_path, monkeypatch):
    """A pure native policy actor cannot impersonate a Fabric Job/Attempt."""
    from control_plane.fabric_coordination_policy import (
        CoordinationNativeIdentity, CoordinationParticipant, CoordinationRole,
    )

    _, _, _, owner, source = setup(tmp_path, monkeypatch)
    native = CoordinationParticipant(
        identity=CoordinationNativeIdentity(
            "99999999-1111-4333-8444-555555555555", "gen-1",
            "ubuntu1", "native-principal",
        ),
        role=CoordinationRole.PROJECT_CEO,
        tenant_ref="fixture-tenant",
        portfolio_ref="fixture-portfolio",
        project_ref="fixture-project",
        program_ref="fixture-program",
    )
    owner.snapshot = replace(owner.snapshot, participants=owner.snapshot.participants + (native,))
    with pytest.raises(RuntimeCoordinationUnavailable):
        source.observe()
