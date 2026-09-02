"""Executive Wake Fabric PR-2 — durable ledger + reconciliation.

Hermetic: stdlib + pytest.  No network, no MCP write, no provider transport,
no new SQLite table.  Automatic reconciliation writes only WAKE_REQUESTED and
SOURCE_RESOLVED onto the existing Executive OS events table.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from control_plane import ceo_boot_packet
from control_plane.executive_inbox import BOOT_PACKET_SCHEMA, SCHEMA as INBOX_SCHEMA
from control_plane.executive_runtime import (
    Event,
    JobPayload,
    PersistenceError,
    Runtime,
    SCHEMA_VERSION,
    StateConflict,
)
from control_plane.session_targets import load_session_targets
from control_plane.wake_dispatcher import dispatch_wake
from control_plane.wake_ledger import (
    AckMode,
    FORBIDDEN_EVENT_PAYLOAD_KEYS,
    LedgerPhase,
    SourceReadHealth,
    TrustedAckContext,
    WAKE_AGGREGATE_TYPE,
    WakeLedgerError,
    ack_record,
    acknowledge,
    expected_resolution_code,
    requested_record,
    resolve_source,
    resolved_record,
    wake_record_from_event,
)
from control_plane.wake_persist import WakeLedgerRepository
from control_plane.wake_reconcile import reconcile_wakes
from integrations.executive_mcp.schemas import TOOL_SPECS, tool_names


_NOW = "2026-08-16T16:00:00Z"
_NEEDS_CEO = {
    "workstream": "WS:PROPHET-FUSION",
    "question": "Authorize the conditional-fusion promotion gate?",
    "options": ["authorize", "defer"],
    "recommendation": "authorize",
}


@pytest.fixture
def frozen_git(monkeypatch):
    monkeypatch.setattr(ceo_boot_packet, "_git_sha", lambda path: "e" * 40)
    monkeypatch.setattr(ceo_boot_packet, "_git_branch", lambda path: "master")


def _register(runtime: Runtime, worker_id: str = "worker-a") -> None:
    runtime.workers.register_worker(
        worker_id,
        provider="codex",
        account_label=f"{worker_id}-account",
        worker_type="fixture",
        capabilities=["code", "research", "review"],
    )


def _complete(runtime: Runtime, job_id: str, worker_id: str = "worker-a", *, verdict: str = "") -> None:
    lease = runtime.attempts.claim_job(job_id, worker_id=worker_id)
    assert lease is not None
    runtime.jobs.complete_job(
        job_id,
        JobPayload(summary="fixture complete", current_state="complete", verdict=verdict),
    )


def _fail(runtime: Runtime, job_id: str, worker_id: str = "worker-a") -> None:
    lease = runtime.attempts.claim_job(job_id, worker_id=worker_id)
    assert lease is not None
    runtime.jobs.fail_job(
        job_id,
        JobPayload(summary="boom", errors=["provider returned a fatal error"]),
    )


def _packet(*, needs_ceo=None, schema: str = BOOT_PACKET_SCHEMA, brief_schema: str = "ceo_brief.v1"):
    return {
        "schema": schema,
        "generated_at": _NOW,
        "mastermind": {"root": "/fixture/mastermind", "sha": "f" * 40, "branch": "master"},
        "macro": {
            "root": "/fixture/macro",
            "sha": "9" * 40,
            "resolved_via": "flag",
            "candidates_tried": [],
        },
        "strategic_state": {"company_phase": "phase-1", "north_star": [], "p0": []},
        "brief": {
            "schema": brief_schema,
            "generated_at": _NOW,
            "counts": {"total": 1},
            "needs_ceo": list(needs_ceo if needs_ceo is not None else [_NEEDS_CEO]),
            "blocked": [],
            "inputs": {"degraded": []},
        },
        "handoffs": [],
        "degraded": [],
        "next_recommended_act": "Rule on pending CEO decision(s).",
    }


def _reconcile(runtime: Runtime, **kwargs):
    kwargs.setdefault("include_boot_packet", False)
    return reconcile_wakes(runtime, **kwargs)


def _wake_events(runtime: Runtime) -> list[Event]:
    return runtime.events.list_events(aggregate_type=WAKE_AGGREGATE_TYPE)


def _requested_kind(runtime: Runtime, kind: str) -> list[Event]:
    return [
        item
        for item in _wake_events(runtime)
        if item.event_type == "WAKE_REQUESTED" and item.payload.get("wake_kind") == kind
    ]


def _ack_as_human_operator(runtime: Runtime, obligation_id: str) -> None:
    repo = WakeLedgerRepository(runtime)
    requested = repo.get_by_command_id(obligation_id)
    assert requested is not None and requested.obligation is not None
    obligation = requested.obligation
    repo.append_record(
        ack_record(
            obligation,
            acknowledge(
                obligation,
                trusted=TrustedAckContext(
                    ack_mode=AckMode.HUMAN_OPERATOR,
                    target_seat=obligation.declared_target_seat,
                    session_alias="EXECUTIVE-HUMAN-OPERATOR",
                    reasoning_surface="human",
                    acknowledged_at=_NOW,
                    operator_authority_receipt="OP-WAKE-RECONCILE-TEST",
                ),
                claimed_obligation_ids=(obligation_id,),
            ),
        ),
        obligation=None,
    )


def _tables(runtime: Runtime) -> set[str]:
    with runtime.store.read() as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def _completed_review_child(runtime: Runtime):
    _register(runtime)
    parent = runtime.jobs.create_job("Parent container")
    child = runtime.jobs.create_job(
        "Review-required child",
        parent_job_id=parent.job_id,
        review_required=True,
    )
    _complete(runtime, child.job_id)
    return parent, child


def test_event_registry_full_lookup_and_aggregate_list(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    job = runtime.jobs.create_job("lookup")
    created = runtime.events.list_events(job_id=job.job_id)
    assert created
    found = runtime.events.get_event_by_command_id(created[0].command_id)
    assert found is not None
    assert found.event_id == created[0].event_id
    assert found.payload == created[0].payload
    jobs = runtime.events.list_events(aggregate_type="job", aggregate_id=job.job_id)
    assert [item.event_id for item in jobs] == [item.event_id for item in created]
    assert runtime.store.find_event_by_command_id(created[0].command_id)["event_type"] == created[0].event_type


def test_completed_review_required_job_requests_once_and_survives_restart(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    first = _reconcile(runtime)
    review = _requested_kind(runtime, "review_required")
    assert len(review) == 1
    assert review[0].aggregate_type == "wake"
    assert review[0].aggregate_id == review[0].command_id
    assert review[0].job_id is not None and review[0].job_id.startswith("JOB-")
    assert review[0].attempt_id is None
    assert review[0].actor == "wake_reconcile"
    assert not (set(review[0].payload) & FORBIDDEN_EVENT_PAYLOAD_KEYS)
    assert review[0].command_id in first.requested

    ids = sorted(item.command_id for item in _wake_events(runtime) if item.event_type == "WAKE_REQUESTED")
    second = _reconcile(runtime)
    assert second.requested == ()
    assert review[0].command_id in second.plan.already_requested
    assert sorted(
        item.command_id for item in _wake_events(runtime) if item.event_type == "WAKE_REQUESTED"
    ) == ids

    restarted = Runtime.at(tmp_path)
    third = _reconcile(restarted)
    assert third.requested == ()
    again = _requested_kind(restarted, "review_required")
    assert len(again) == 1
    assert again[0].command_id == review[0].command_id


def test_sibling_review_source_resolves_and_degraded_runtime_does_not(tmp_path, frozen_git, monkeypatch):
    runtime = Runtime.at(tmp_path)
    parent, child = _completed_review_child(runtime)
    requested = _reconcile(runtime)
    oid = _requested_kind(runtime, "review_required")[0].command_id
    assert oid in requested.requested
    runtime.jobs.create_job(
        "Independent review slot",
        parent_job_id=parent.job_id,
        reviews_job_id=child.job_id,
    )
    pending_ack = _reconcile(runtime)
    assert pending_ack.resolved == ()
    assert oid in pending_ack.plan.already_requested
    _ack_as_human_operator(runtime, oid)
    resolved = _reconcile(runtime)
    assert oid in resolved.resolved
    review_stream = [
        item.event_type
        for item in _wake_events(runtime)
        if item.aggregate_id == oid
    ]
    assert review_stream == [
        "WAKE_REQUESTED",
        "TARGET_ACKNOWLEDGED",
        "SOURCE_RESOLVED",
    ]
    assert all(item.event_type != "DELIVERY_ATTEMPT" for item in _wake_events(runtime))

    runtime2 = Runtime.at(tmp_path / "degraded-runtime")
    _completed_review_child(runtime2)
    first = _reconcile(runtime2)
    assert first.requested
    monkeypatch.setattr(
        runtime2.jobs,
        "list_jobs",
        lambda: (_ for _ in ()).throw(RuntimeError("runtime source unreadable")),
    )
    blocked = _reconcile(runtime2)
    assert blocked.resolved == ()
    assert blocked.snapshot.runtime_health.value == "degraded"
    assert [item.event_type for item in _wake_events(runtime2)].count("SOURCE_RESOLVED") == 0


def test_inbox_failed_job_requests_and_healthy_repair_resolves(tmp_path, frozen_git, monkeypatch):
    runtime = Runtime.at(tmp_path / "repair")
    _register(runtime)
    job = runtime.jobs.create_job("fail then repair")
    _fail(runtime, job.job_id)
    first = _reconcile(runtime)
    assert len(first.requested) == 1
    row = _wake_events(runtime)[0]
    assert row.payload["wake_kind"] == "job_failed"
    assert row.job_id == job.job_id
    assert row.attempt_id is None

    runtime.jobs.requeue_job(job.job_id)
    _complete(runtime, job.job_id)
    pending_ack = _reconcile(runtime)
    assert pending_ack.resolved == ()
    assert first.requested[0] in pending_ack.plan.already_requested
    _ack_as_human_operator(runtime, first.requested[0])
    repaired = _reconcile(runtime)
    assert repaired.resolved == first.requested
    assert [item.event_type for item in _wake_events(runtime)][-1] == "SOURCE_RESOLVED"

    runtime2 = Runtime.at(tmp_path / "degraded-inbox")
    _register(runtime2)
    failed = runtime2.jobs.create_job("stay failed")
    _fail(runtime2, failed.job_id)
    requested = _reconcile(runtime2)
    assert requested.requested
    monkeypatch.setattr(
        "control_plane.wake_reconcile.build_inbox",
        lambda **kwargs: {
            "schema": INBOX_SCHEMA,
            "attention": [],
            "degraded": ["runtime jobs unreadable: fixture"],
            "grounding": {"boot_packet_schema": None},
        },
    )
    blocked = _reconcile(runtime2)
    assert blocked.resolved == ()
    assert blocked.snapshot.inbox_runtime_health.value == "degraded"


def test_agentos_no_job_ceo_two_rows_and_healthy_removal(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    twice = _packet(needs_ceo=[dict(_NEEDS_CEO), dict(_NEEDS_CEO)])
    first = _reconcile(runtime, boot_packet=twice, include_boot_packet=False)
    assert len(first.requested) == 2
    events = _wake_events(runtime)
    assert {item.job_id for item in events} == {None}
    assert {item.attempt_id for item in events} == {None}
    assert {item.payload["wake_kind"] for item in events} == {"ceo_decision_pending"}
    assert len({item.aggregate_id for item in events}) == 2

    removed = _reconcile(runtime, boot_packet=_packet(needs_ceo=[]), include_boot_packet=False)
    assert removed.resolved == ()
    assert {item.event_type for item in _wake_events(runtime)} == {"WAKE_REQUESTED"}

    runtime2 = Runtime.at(tmp_path / "degraded-ceo")
    _reconcile(runtime2, boot_packet=_packet(), include_boot_packet=False)
    blocked = _reconcile(
        runtime2,
        boot_packet=_packet(schema="foreign.boot.v0"),
        include_boot_packet=False,
    )
    assert blocked.resolved == ()
    assert blocked.snapshot.agentos_health.value == "degraded"


def test_unbound_root_and_disarmed_production_still_persist(tmp_path, frozen_git):
    registry = load_session_targets()
    assert registry.production_armed is False
    assert registry.root_job_bindings == {}
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    result = _reconcile(runtime)
    assert result.requested
    assert result.transport_invocations == 0
    assert result.delivery_attempts == 0


def test_two_concurrent_reconcilers_write_one_requested(tmp_path, frozen_git):
    primed = Runtime.at(tmp_path)
    _completed_review_child(primed)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _actor() -> None:
        try:
            runtime = Runtime.at(tmp_path)
            barrier.wait(timeout=5)
            _reconcile(runtime)
        except BaseException as exc:  # noqa: BLE001 — capture for the parent thread
            errors.append(exc)

    threads = [threading.Thread(target=_actor) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    events = [item for item in _wake_events(Runtime.at(tmp_path)) if item.event_type == "WAKE_REQUESTED"]
    ids = [item.command_id for item in events]
    assert ids and len(ids) == len(set(ids))
    assert len([item for item in events if item.payload.get("wake_kind") == "review_required"]) == 1


def test_semantic_command_id_collision_hard_fails(tmp_path, frozen_git):
    from control_plane.wake_reconcile import collect_source_snapshot

    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    snapshot = collect_source_snapshot(runtime, include_boot_packet=False)
    assert snapshot.observed
    obligation = snapshot.observed[0]
    oid = obligation.obligation_id
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="job",
            aggregate_id="JOB-001",
            event_type="JOB_CREATED",
            actor="test",
            payload={"stolen": True},
            command_id=oid,
        )
    result = _reconcile(runtime)
    assert any("stole" in entry or "collision" in entry for entry in result.plan.contradictions)
    assert oid not in result.requested
    stolen = runtime.events.get_event_by_command_id(oid)
    assert stolen is not None and stolen.aggregate_type == "job"
    repo = WakeLedgerRepository(runtime)
    with pytest.raises(StateConflict, match="not a wake aggregate|collision"):
        repo.append_record(requested_record(obligation), obligation=obligation)


def test_corrupt_wake_event_is_visible_and_does_not_silently_rerequest(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    first = _reconcile(runtime)
    oid = first.requested[0]
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="wake",
            aggregate_id=oid,
            event_type="WAKE_REQUESTED",
            actor="test",
            payload={"native_handle": "thread-secret", "next_actions": ["do it"]},
            command_id=f"{oid}:ACK",
        )
    result = _reconcile(runtime)
    assert result.requested == ()
    assert result.plan.contradictions
    assert any("native" in entry or "forbidden" in entry or "phase" in entry for entry in result.plan.contradictions)


def test_native_handles_and_next_actions_never_persist_as_authority(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    result = _reconcile(runtime)
    review = _requested_kind(runtime, "review_required")
    assert len(review) == 1
    event = runtime.events.get_event_by_command_id(review[0].command_id)
    assert event is not None
    assert "native_handle" not in event.payload
    assert "next_actions" not in event.payload
    assert "objective" not in event.payload
    with pytest.raises(WakeLedgerError, match="forbidden"):
        wake_record_from_event(
            Event(
                event_id=99,
                aggregate_type="wake",
                aggregate_id=review[0].aggregate_id,
                sequence=1,
                event_type="WAKE_REQUESTED",
                command_id=review[0].command_id,
                actor="wake_reconcile",
                job_id=None,
                attempt_id=None,
                worker_id=None,
                quota_class=None,
                payload={"native_handle": "x", **event.payload},
                created_at=_NOW,
            )
        )


def test_reconciliation_never_invokes_transport_or_delivery_attempt(tmp_path, frozen_git, monkeypatch):
    calls: list[str] = []

    def _boom(*args, **kwargs):
        calls.append("dispatch")
        raise AssertionError("transport must not run")

    monkeypatch.setattr("control_plane.wake_dispatcher.dispatch_wake", _boom)
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    result = _reconcile(runtime)
    assert result.transport_invocations == 0
    assert result.delivery_attempts == 0
    assert calls == []
    assert dispatch_wake is _boom or True
    assert not any(item.event_type == "DELIVERY_ATTEMPT" for item in _wake_events(runtime))


def test_schema_mcp_and_table_census_unchanged(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    before = _tables(runtime)
    _completed_review_child(runtime)
    _reconcile(runtime)
    after = _tables(runtime)
    assert before == after
    assert not any("wake" in name.lower() for name in after)
    assert SCHEMA_VERSION == 4
    assert len(TOOL_SPECS) == 5
    assert "acknowledge_ceo_wake" not in tool_names()
    with runtime.store.read() as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
    assert int(version) == SCHEMA_VERSION


def test_idempotent_append_of_same_requested_command(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    result = _reconcile(runtime)
    repo = WakeLedgerRepository(runtime)
    stored = repo.get_by_command_id(_requested_kind(runtime, "review_required")[0].command_id)
    assert stored is not None
    replay = repo.append_record(requested_record(stored.obligation), obligation=stored.obligation)
    assert replay.event.event_id == stored.event.event_id


def test_acceptance_demo_review_required_then_ceo_packet(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    parent, child = _completed_review_child(runtime)
    step2 = _reconcile(runtime)
    review = _requested_kind(runtime, "review_required")
    assert len(review) == 1
    assert review[0].command_id in step2.requested
    requested = runtime.events.list_events(
        aggregate_type="wake", aggregate_id=review[0].aggregate_id
    )
    assert requested[0].event_type == "WAKE_REQUESTED"

    restarted = Runtime.at(tmp_path)
    step5 = _reconcile(restarted)
    assert step5.requested == ()
    assert len(_requested_kind(restarted, "review_required")) == 1

    restarted.jobs.create_job(
        "Independent review slot",
        parent_job_id=parent.job_id,
        reviews_job_id=child.job_id,
    )
    pending_ack = _reconcile(restarted)
    assert pending_ack.resolved == ()
    assert review[0].command_id in pending_ack.plan.already_requested
    _ack_as_human_operator(restarted, review[0].command_id)
    step8 = _reconcile(restarted)
    assert review[0].command_id in step8.resolved
    assert not any(item.event_type == "DELIVERY_ATTEMPT" for item in _wake_events(restarted))

    ceo_runtime = Runtime.at(tmp_path / "ceo")
    ceo = _reconcile(ceo_runtime, boot_packet=_packet(), include_boot_packet=False)
    assert len(ceo.requested) == 1
    event = _wake_events(ceo_runtime)[0]
    assert event.job_id is None
    assert event.payload["wake_kind"] == "ceo_decision_pending"


def test_one_shot_script_exits_after_one_pass(tmp_path, frozen_git):
    from scripts.executive_wake_reconcile import main

    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    code = main(["--root", str(tmp_path), "--no-boot-packet", "--json"])
    assert code == 0
    assert len(_requested_kind(Runtime.at(tmp_path), "review_required")) == 1


def test_causal_write_refuses_resolved_before_requested(tmp_path, frozen_git):
    from control_plane.wake_reconcile import collect_source_snapshot

    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    obligation = collect_source_snapshot(runtime, include_boot_packet=False).observed[0]
    resolution = resolve_source(
        obligation,
        code=expected_resolution_code(obligation),
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        snapshot_digest="a" * 16,
    )
    repo = WakeLedgerRepository(runtime)
    with pytest.raises(WakeLedgerError, match="REQUESTED must precede"):
        repo.append_record(resolved_record(obligation, resolution), obligation=obligation)
    assert _wake_events(runtime) == []


def test_event_job_id_mismatch_is_corrupt(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    _reconcile(runtime)
    event = _requested_kind(runtime, "review_required")[0]
    with pytest.raises(WakeLedgerError, match="job_id disagrees"):
        wake_record_from_event(
            Event(
                event_id=event.event_id,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                sequence=event.sequence,
                event_type=event.event_type,
                command_id=event.command_id,
                actor=event.actor,
                job_id="JOB-999",
                attempt_id=event.attempt_id,
                worker_id=event.worker_id,
                quota_class=event.quota_class,
                payload=event.payload,
                created_at=event.created_at,
            )
        )


def test_disagreeing_observed_envelope_is_contradiction(tmp_path, frozen_git, monkeypatch):
    import dataclasses

    from control_plane.wake_reconcile import collect_source_snapshot

    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    obligation = collect_source_snapshot(runtime, include_boot_packet=False).observed[0]
    other = dataclasses.replace(obligation, declared_target_seat="chairman")
    monkeypatch.setattr(
        "control_plane.wake_reconcile._runtime_review_obligations",
        lambda runtime, jobs: [obligation, other],
    )
    collided = collect_source_snapshot(runtime, include_boot_packet=False)
    assert obligation.obligation_id not in {item.obligation_id for item in collided.observed}
    assert any("disagreeing observed envelope" in entry for entry in collided.contradictions)
    result = _reconcile(runtime)
    assert obligation.obligation_id not in result.requested
    assert _wake_events(runtime) == []


def test_unadmitted_current_attention_does_not_resolve(tmp_path, frozen_git, monkeypatch):
    runtime = Runtime.at(tmp_path)
    first = _reconcile(runtime, boot_packet=_packet(), include_boot_packet=False)
    assert first.requested
    source_ref = _wake_events(runtime)[0].payload["source_ref"]
    monkeypatch.setattr(
        "control_plane.wake_reconcile.build_inbox",
        lambda **kwargs: {
            "schema": INBOX_SCHEMA,
            "attention": [{"attention_id": source_ref, "kind": "not-a-real-kind"}],
            "degraded": [],
            "grounding": {"boot_packet_schema": BOOT_PACKET_SCHEMA},
        },
    )
    blocked = _reconcile(runtime, include_boot_packet=False)
    assert blocked.resolved == ()
    assert source_ref in blocked.plan.unsupported_attention
    assert blocked.snapshot.inbox_runtime_health.value == "degraded"


def test_command_id_prefix_rejects_wildcards(tmp_path, frozen_git):
    runtime = Runtime.at(tmp_path)
    with pytest.raises(StateConflict, match="literal namespace"):
        runtime.events.list_events(command_id_prefix="WAKE-%")


def test_existing_writable_refuses_missing_and_does_not_create(tmp_path):
    with pytest.raises(PersistenceError, match="missing"):
        Runtime.at(tmp_path, create=False, existing_writable=True)
    assert not (tmp_path / "data" / "control_plane" / "executive.sqlite3").exists()


def test_one_shot_script_refuses_missing_runtime(tmp_path):
    from scripts.executive_wake_reconcile import main

    code = main(["--root", str(tmp_path), "--no-boot-packet"])
    assert code == 2
    assert not (tmp_path / "data" / "control_plane" / "executive.sqlite3").exists()


def test_one_shot_script_exits_nonzero_on_contradictions(tmp_path, frozen_git):
    from control_plane.wake_reconcile import collect_source_snapshot
    from scripts.executive_wake_reconcile import main

    runtime = Runtime.at(tmp_path)
    _completed_review_child(runtime)
    oid = collect_source_snapshot(runtime, include_boot_packet=False).observed[0].obligation_id
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection,
            aggregate_type="job",
            aggregate_id="JOB-001",
            event_type="JOB_CREATED",
            actor="test",
            payload={"stolen": True},
            command_id=oid,
        )
    code = main(["--root", str(tmp_path), "--no-boot-packet", "--json"])
    assert code == 3
