"""Exact destination reconstruction from real temporary Runtime/Wake records.

Provider/harness inputs are the existing synthetic fixture. No live admission,
Slack message, credential, or installed target binding is exercised here.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib
import importlib.util
from types import SimpleNamespace

import pytest

from control_plane.dialogue_source_resolution import (
    DialogueSourceObservation,
    PhysicalDialogueSourceIdentity,
    attention_source_ref,
    correlated_source_ref,
)
from control_plane.executive_delegation_identity import derive_delegation_identity
from control_plane.executive_runtime import StateConflict
from control_plane.wake_events import mint_obligation, mint_obligation_id
from control_plane.wake_ledger import requested_record
from control_plane.wake_persist import WakeLedgerRepository
from integrations.company_consultation_dispatch import (
    ConsultationPacketCarrierUnknown,
    InMemoryConsultationPacketCarrier,
)
from tests import test_company_inbox_iac1 as fixtures
from tests.test_workspace_agent_runtime_binding import source

WORKSPACE = "T0BRD2AQXQV"
CHANNEL = "C0BRUL9F2V7"
THREAD_A = "1787961600.000001"
THREAD_B = "1787961700.000001"


def _api():
    name = "integrations.company_consultation_target_resolution"
    assert importlib.util.find_spec(name) is not None, "canonical packet target resolver is not implemented"
    return importlib.import_module(name)


def _seed(tmp_path, monkeypatch, *, physical=True, root_source=True):
    runtime = fixtures._runtime_at(tmp_path / "runtime")
    original_submit = fixtures.submit_intent
    def with_source(runtime, payload):
        # Root admission requires the source's exact workstream in the intent.
        payload = dict(payload, workstream=source().work_ref)
        return original_submit(runtime, payload, dialogue_source=source().to_dict() if root_source else None)
    monkeypatch.setattr(fixtures, "submit_intent", with_source)
    a, b, _, root = fixtures._workers(runtime)
    repo, revision = fixtures._fixture_repo(tmp_path / "repo")
    seed = SimpleNamespace(runtime=runtime, a=a, b=b, root=root, repo=repo, revision=revision)
    if physical:
        _physical(seed, a, THREAD_A, "asd-target-a-0001")
        _physical(seed, b, THREAD_B, "asd-target-b-0001")
    return seed


def _physical(seed, actor, thread, key, *, workspace=WORKSPACE, channel=CHANNEL, parent_fingerprint="a" * 64):
    identity = derive_delegation_identity(seed.runtime.jobs.get_job(actor[0]))
    candidate = {
        "mode": "ACTIVE_CURRENT_WORKER", "root_job_id": seed.root,
        "job_id": actor[0], "attempt_id": actor[1], "worker_id": actor[2],
        "evidence_digest": hashlib.sha256(actor[1].encode()).hexdigest(),
    }
    observation = DialogueSourceObservation(workspace, channel, thread, key, "c" * 64)
    attention = attention_source_ref(parent_fingerprint=parent_fingerprint, message_key=key, target_seat="coo")
    logical = correlated_source_ref(attention_source_ref=attention, parent_fingerprint=parent_fingerprint,
                                    operation_key=identity.operation_key, candidate=candidate)
    physical = PhysicalDialogueSourceIdentity.create(
        logical_source_ref=logical,
        obligation_id=mint_obligation_id(source_kind="agent_dialogue_attention", source_ref=logical,
                                        wake_kind="dialogue_turn_pending"),
        observation=observation, parent_fingerprint=parent_fingerprint,
        operation_key=identity.operation_key, target_seat="coo", candidate=candidate,
    )
    obligation = mint_obligation(
        wake_kind="dialogue_turn_pending", source_kind="agent_dialogue_attention",
        source_ref=logical, declared_target_seat="coo", job_id=actor[0], attempt_id=actor[1],
        root_job_id=seed.root, source_workstream=source().work_ref,
        emitted_at="2026-09-14T00:00:00Z",
    )
    WakeLedgerRepository(seed.runtime).append_record(
        requested_record(obligation, physical_source=physical), obligation=obligation,
    )


def _resolver(seed, **kwargs):
    return _api().ExecutiveConsultationPacketTargetResolver(
        seed.runtime, workspace_id=WORKSPACE, channel_id=CHANNEL, **kwargs,
    )


def _admit(seed):
    packets = InMemoryConsultationPacketCarrier()
    dispatcher = fixtures._make_dispatcher(seed.runtime, seed.repo,
        requester=seed.a, recipient=seed.b, packets=packets,
        invocations=fixtures._p1_invocations())
    response = asyncio.run(fixtures._gateway_with_dispatcher(dispatcher).call(
        "company.consult", fixtures._consult_args(question="Keep the exact admitted recipient.",
            evidence_refs=[], artifact_revisions=[seed.revision]),
    ))
    assert response["ok"] is True, response
    consultation_id = response["data"]["consultation_ref"]
    return asyncio.run(packets.get_question(consultation_id))


def _event_count(seed):
    with seed.runtime.store.read() as connection:
        return connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]


def test_new_question_reconstructs_exact_current_target_without_writes(tmp_path, monkeypatch):
    _api()
    seed = _seed(tmp_path, monkeypatch)
    frame = fixtures._packet_frame(seed.a, seed.b)
    before = _event_count(seed)
    access = _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
    assert dict(access.target.actor_ref) == frame["recipient_actor_ref"]
    assert access.target.thread_ts == THREAD_B
    assert access.target.operation_key == derive_delegation_identity(seed.runtime.jobs.get_job(seed.b[0])).operation_key
    assert access.target.work_ref == source().work_ref
    assert dict(access.target.commission_ref) == source().commission_ref.to_dict()
    assert not hasattr(access.target, "allowed_message_types")
    assert _event_count(seed) == before


@pytest.mark.parametrize("purpose,thread", [("QUESTION", THREAD_B), ("ANSWER", THREAD_A)])
def test_admitted_target_reconstructs_after_runtime_reopen(tmp_path, monkeypatch, purpose, thread):
    _api()
    seed = _seed(tmp_path, monkeypatch)
    frame = _admit(seed)
    first = _resolver(seed).resolve(frame["consultation_id"], purpose=purpose)
    seed.runtime = fixtures._runtime_at(tmp_path / "runtime")
    before = _event_count(seed)
    second = _resolver(seed).resolve(frame["consultation_id"], purpose=purpose)
    assert second == first
    assert second.target.thread_ts == thread
    assert _event_count(seed) == before


def test_missing_intent_is_not_a_discoverable_read_or_answer_destination(tmp_path, monkeypatch):
    _api()
    seed = _seed(tmp_path, monkeypatch)
    frame = fixtures._packet_frame(seed.a, seed.b)
    for purpose in ("QUESTION", "ANSWER"):
        with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
            _resolver(seed).resolve(frame["consultation_id"], purpose=purpose)
    answer = fixtures._packet_frame(seed.a, seed.b, purpose="ANSWER")
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        _resolver(seed).resolve(answer["consultation_id"], purpose="ANSWER", frame=answer)


@pytest.mark.parametrize("kind", ["missing", "ambiguous", "wrong_channel", "wrong_workspace", "root_absent"])
def test_unavailable_or_foreign_physical_source_refuses_without_latest_fallback(tmp_path, monkeypatch, kind):
    _api()
    seed = _seed(tmp_path, monkeypatch, physical=kind not in ("missing", "wrong_channel", "wrong_workspace"),
                 root_source=kind != "root_absent")
    if kind == "ambiguous":
        _physical(seed, seed.b, "1787961800.000001", "asd-other-thread-0001")
    if kind == "wrong_channel":
        _physical(seed, seed.b, THREAD_B, "asd-wrong-channel-0001", channel="C0BSBM78V1N")
    if kind == "wrong_workspace":
        _physical(seed, seed.b, THREAD_B, "asd-wrong-workspace-0001", workspace="T000000001")
    frame = fixtures._packet_frame(seed.a, seed.b)
    before = _event_count(seed)
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
    assert _event_count(seed) == before


def test_more_attention_for_same_thread_does_not_rotate_target_evidence(tmp_path, monkeypatch):
    _api()
    seed = _seed(tmp_path, monkeypatch)
    frame = fixtures._packet_frame(seed.a, seed.b)
    first = _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
    _physical(seed, seed.b, THREAD_B, "asd-later-attention-0001")
    second = _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
    assert second == first


def test_admitted_read_keeps_old_attempt_and_new_question_refuses_stale_attempt(tmp_path, monkeypatch):
    _api()
    seed = _seed(tmp_path, monkeypatch)
    admitted = _admit(seed)
    original = seed.runtime.jobs.get_job
    old_job = original(seed.b[0])
    rotated = dataclasses.replace(old_job, current_attempt_id="ATT-" + "d" * 32)
    monkeypatch.setattr(seed.runtime.jobs, "get_job", lambda job_id: rotated if job_id == seed.b[0] else original(job_id))
    historical = _resolver(seed).resolve(admitted["consultation_id"], purpose="QUESTION")
    assert historical.target.thread_ts == THREAD_B
    assert historical.target.actor_ref["attempt_id"] == seed.b[1]
    fresh = fixtures._packet_frame(seed.a, seed.b)
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        _resolver(seed).resolve(fresh["consultation_id"], purpose="QUESTION", frame=fresh)


def test_current_target_changes_between_owner_reads_refuses(tmp_path, monkeypatch):
    api = _api()
    seed = _seed(tmp_path, monkeypatch)
    frame = fixtures._packet_frame(seed.a, seed.b)
    original = api._read_current_target
    reads = []
    def changing(runtime, operation_key):
        value = original(runtime, operation_key)
        reads.append(value)
        return value if len(reads) == 1 else dataclasses.replace(value, fence_generation=value.fence_generation + 1)
    monkeypatch.setattr(api, "_read_current_target", changing)
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
    assert len(reads) == 2


def test_existing_intent_parties_override_a_conflicting_candidate(tmp_path, monkeypatch):
    _api()
    seed = _seed(tmp_path, monkeypatch)
    frame = _admit(seed)
    changed = dict(frame)
    changed["recipient_actor_ref"] = dict(frame["recipient_actor_ref"], worker_id="not-the-recipient")
    changed["fingerprint"] = ""
    from common.agent_dialogue_consultation_contract import build_consultation
    changed = build_consultation(changed)
    with pytest.raises((StateConflict, ConsultationPacketCarrierUnknown)):
        _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=changed)


# ---------------------------------------------------------------------------
# P1-R1 repair: resolver evidence failures leave the carrier-outage bucket
# ---------------------------------------------------------------------------


def _targets():
    return importlib.import_module("integrations.company_consultation_targets")


@pytest.mark.parametrize("kind,expected", [
    # Adjudicated by the resolver itself against the host's own exact scope.
    ("wrong_channel", "conflict"),
    ("wrong_workspace", "conflict"),
    # The owner readers collapse these into one code, so they stay unknown.
    ("missing", "unavailable"),
    ("ambiguous", "unavailable"),
    ("root_absent", "unavailable"),
])
def test_resolver_evidence_failures_are_classified_not_pooled(tmp_path, monkeypatch, kind, expected):
    """Each of missing/ambiguous/foreign gets its exact class, not one bucket.

    The incumbent acceptance for these five kinds accepts either class, so it
    cannot distinguish a deterministic target conflict from a dead carrier.
    This pins which is which, and records that ``missing``/``ambiguous`` are
    honestly undecidable here rather than pretending otherwise.
    """
    targets = _targets()
    _api()
    seed = _seed(
        tmp_path, monkeypatch,
        physical=kind not in ("missing", "wrong_channel", "wrong_workspace"),
        root_source=kind != "root_absent",
    )
    if kind == "ambiguous":
        _physical(seed, seed.b, "1787961800.000001", "asd-other-thread-0001")
    if kind == "wrong_channel":
        _physical(seed, seed.b, THREAD_B, "asd-wrong-channel-0001", channel="C0BSBM78V1N")
    if kind == "wrong_workspace":
        _physical(seed, seed.b, THREAD_B, "asd-wrong-workspace-0001", workspace="T000000001")
    frame = fixtures._packet_frame(seed.a, seed.b)
    before = _event_count(seed)

    if expected == "conflict":
        with pytest.raises(targets.ConsultationTargetConflict) as caught:
            _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
        # A closed adjudication: never retried or re-resolved as an outage.
        assert isinstance(caught.value, StateConflict)
        assert not isinstance(caught.value, ConsultationPacketCarrierUnknown)
    else:
        with pytest.raises(targets.ConsultationTargetEvidenceUnavailable) as caught:
            _resolver(seed).resolve(frame["consultation_id"], purpose="QUESTION", frame=frame)
        # Real observation uncertainty must never become a safe refusal.
        assert isinstance(caught.value, ConsultationPacketCarrierUnknown)
        assert not isinstance(caught.value, StateConflict)
    assert "BINDING_UNAVAILABLE" not in str(caught.value)
    assert _event_count(seed) == before


@pytest.mark.parametrize("rotation", ["valid_other_attempt", "absent_attempt"])
def test_sticky_target_rotation_classification_boundary(tmp_path, monkeypatch, rotation):
    """A peer that moved on is a conflict; an unreadable peer stays unknown.

    Both are "sticky-target" in prose, and they classify differently for a
    real reason. When the owner can still name a current Attempt and it is not
    the admitted one, the resolver adjudicates that itself. When the rotation
    leaves no readable Attempt at all, the owner's single conflated code is all
    that exists and honesty requires unknown.
    """
    targets = _targets()
    api = _api()
    seed = _seed(tmp_path, monkeypatch)
    fresh = fixtures._packet_frame(seed.a, seed.b)

    if rotation == "valid_other_attempt":
        original = api._read_current_target
        monkeypatch.setattr(
            api, "_read_current_target",
            lambda runtime, operation_key: dataclasses.replace(
                original(runtime, operation_key), attempt_id="ATT-" + "e" * 32,
            ),
        )
        with pytest.raises(targets.ConsultationTargetConflict) as caught:
            _resolver(seed).resolve(fresh["consultation_id"], purpose="QUESTION", frame=fresh)
        assert not isinstance(caught.value, ConsultationPacketCarrierUnknown)
    else:
        get_job = seed.runtime.jobs.get_job
        rotated = dataclasses.replace(
            get_job(seed.b[0]), current_attempt_id="ATT-" + "d" * 32,
        )
        monkeypatch.setattr(
            seed.runtime.jobs, "get_job",
            lambda job_id: rotated if job_id == seed.b[0] else get_job(job_id),
        )
        with pytest.raises(targets.ConsultationTargetEvidenceUnavailable) as caught:
            _resolver(seed).resolve(fresh["consultation_id"], purpose="QUESTION", frame=fresh)
        assert not isinstance(caught.value, StateConflict)
    assert "BINDING_UNAVAILABLE" not in str(caught.value)


def test_owner_readers_carry_exactly_one_conflated_refusal_code():
    """Why ``missing``/``ambiguous`` cannot be adjudicated here — and a falsifier.

    ``_refuse()`` is the single refusal in the owner module and raises one
    code for a missing fact, an ambiguous one, a foreign scope and an
    unreadable store alike. If an owner ever adds a distinguishing code this
    fails, which is the signal to refine the mapping above rather than leave
    genuine conflicts sitting in the unknown bucket.
    """
    import ast
    import pathlib
    import re

    from integrations import workspace_agent_runtime_binding as owner

    source = pathlib.Path(owner.__file__).read_text()
    codes = set(re.findall(r'WorkspaceReturnError\(\s*"([A-Z_]+)"\s*\)', source))
    assert codes == {"BINDING_UNAVAILABLE"}, codes

    # ... and the ambiguity branch really does route through that one code.
    tree = ast.parse(source)
    refusals = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(sub, ast.Call)
            and getattr(sub.func, "id", None) == "WorkspaceReturnError"
            for sub in ast.walk(node)
        )
    }
    assert refusals == {"_refuse"}, refusals
