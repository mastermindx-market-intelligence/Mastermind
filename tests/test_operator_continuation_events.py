"""OCR-3 Event integration: real SQLite and admitted target, no provider calls.

The historical predecessor row is seeded test data, not proof of live rollover.
The target is admitted by the existing RuntimeBinding integration fixture.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_runtime import AttemptLease, StateConflict
from control_plane.operator_continuation import (
    ContinuationAck, OperatorContinuationDraft,
    OPERATOR_CONTINUATION_ACK_SCHEMA,
)
from test_runtime_binding_projection import _admitted_runtime


PIN = "732cf7be88e7159b4995a8885fbd381cd1484e3e"
SOURCE_ID = "ATT-0123456789abcdef0123456789abcdef"


def _journey(tmp_path, *, source_evidence=True):
    runtime, dispatch, *_ = _admitted_runtime(tmp_path)
    target_id = dispatch.attempt.attempt_id
    runtime.workers.register_worker(
        "predecessor-worker", provider="openai-codex", account_label="account-b",
        worker_type="fixture", capabilities=["read"],
        quota_classes={"default": {"provider": "openai-codex",
                                   "capabilities": ["read"], "cost_class": "small"}},
    )
    checkpoint = {
        "summary": "Verified the source revision.",
        "completed_steps": ["Read the pinned source."],
        "current_state": "Source verified; review remains.",
        "artifacts": [], "next_actions": ["Review the next bounded change."],
        "errors": [], "verdict": None,
    }
    with runtime.store.transaction() as connection:
        source = dict(connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (target_id,)
        ).fetchone())
        source.update(
            attempt_id=SOURCE_ID, attempt_number=1, worker_id="predecessor-worker",
            status="RATE_LIMITED", lease_token=None, checkpoint_sequence=1,
            finished_at_ms=runtime.store.now_ms(),
            checkpoint_json=json.dumps(checkpoint, sort_keys=True, separators=(",", ":")),
        )
        placement = json.loads(source["placement_snapshot_json"])
        placement.update(worker_id="predecessor-worker", account_label="account-b")
        encoded = json.dumps(placement, sort_keys=True, separators=(",", ":"))
        source["placement_snapshot_json"] = encoded
        source["placement_snapshot_digest"] = hashlib.sha256(encoded.encode()).hexdigest()
        connection.execute(
            "UPDATE attempts SET attempt_number=2 WHERE attempt_id=?", (target_id,)
        )
        connection.execute(
            "UPDATE jobs SET attempt_count=2 WHERE job_id=?", (source["job_id"],)
        )
        connection.execute(
            f"INSERT INTO attempts ({','.join(source)}) VALUES ({','.join('?' for _ in source)})",
            tuple(source.values()),
        )
    job = runtime.jobs.get_job(dispatch.attempt.job_id)
    draft = OperatorContinuationDraft(
        root_job_id=job.root_job_id or job.job_id, job_id=job.job_id,
        source_attempt_id=SOURCE_ID, target_attempt_id=target_id,
        operation_key="portable-continuity-fixture", target_seat="coo",
        session_alias="COO-CODEX",
        effective_grant_digest=dispatch.attempt.effective_grant_digest,
        source_authority_refs=("docs/sol_skills/INDEX.md",),
        agentos_refs=("agentos/workstreams/WS-EXECUTIVE-CAPACITY-FABRIC.md",),
        github_state={"repository": "mastermindx-market-intelligence/Mastermind", "head_sha": PIN},
        prior_attempt_receipt={
            "attempt_id": SOURCE_ID, "status": "RATE_LIMITED", "terminal": True,
            "worker_id": "predecessor-worker", "quota_class": "default",
            "checkpoint_sequence": 1,
        },
        checkpoint=checkpoint, slack_dialogue_ref=None, accepted_ruling_refs=(),
        next_action="Review the next bounded change.", known_unknowns=(),
        source_revisions={"mastermind": PIN},
    )
    port = ExecutiveOperatorHarnessPort(
        runtime, AttemptLease(dispatch.attempt, dispatch.lease_token)
    )
    if source_evidence:
        _seed_released_predecessor(runtime, port)
    return runtime, port, draft


def _events(runtime, event_type):
    with runtime.store.read() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM events WHERE event_type=? ORDER BY event_id", (event_type,)
        ).fetchall()]


def test_prepare_replays_exact_bytes_and_one_existing_store_event(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    with runtime.store.read() as connection:
        schema_before = tuple(connection.execute("SELECT sql FROM sqlite_master ORDER BY name"))
    first = port.prepare_operator_continuation(port.attempt_id, draft)
    second = port.prepare_operator_continuation(port.attempt_id, draft)
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.capsule_id == second.capsule_id
    events = _events(runtime, "OPERATOR_CONTINUATION_PREPARED")
    assert len(events) == 1
    payload = json.loads(events[0]["payload_json"])
    assert payload["capsule"] == first.to_dict()
    assert payload["provider_session_id"] == "PROVIDER-SESSION-1"
    with runtime.store.read() as connection:
        assert tuple(connection.execute("SELECT sql FROM sqlite_master ORDER BY name")) == schema_before


def test_ack_is_idempotent_without_completing_job_or_wake(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    capsule = port.prepare_operator_continuation(port.attempt_id, draft)
    before = runtime.jobs.get_job(draft.job_id)
    ack = ContinuationAck(OPERATOR_CONTINUATION_ACK_SCHEMA, port.attempt_id,
                          capsule.capsule_id, "PROVIDER-SESSION-1", True)
    port.acknowledge_operator_continuation(port.attempt_id, ack)
    port.acknowledge_operator_continuation(port.attempt_id, ack)
    assert len(_events(runtime, "OPERATOR_CONTINUATION_ACKNOWLEDGED")) == 1
    assert runtime.jobs.get_job(draft.job_id) == before
    assert _events(runtime, "TARGET_ACKNOWLEDGED") == []


@pytest.mark.parametrize("field,value", [
    ("next_action", "Invented progress."),
    ("effective_grant_digest", "f" * 64),
    ("root_job_id", "JOB-999"),
    ("source_attempt_id", "ATT-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
])
def test_prepare_refuses_unverified_runtime_draft_fields(tmp_path, field, value):
    runtime, port, draft = _journey(tmp_path)
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(port.attempt_id, dataclasses.replace(draft, **{field: value}))
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


def test_changed_external_source_conflicts_after_prepare(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    port.prepare_operator_continuation(port.attempt_id, draft)
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(
            port.attempt_id, dataclasses.replace(draft, source_revisions={"mastermind": "f" * 40})
        )
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


def test_missing_prepare_does_not_accept_an_ack(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    ack = ContinuationAck(OPERATOR_CONTINUATION_ACK_SCHEMA, port.attempt_id,
                          "f" * 64, "PROVIDER-SESSION-1", True)
    with pytest.raises(StateConflict):
        port.acknowledge_operator_continuation(port.attempt_id, ack)
    assert _events(runtime, "OPERATOR_CONTINUATION_ACKNOWLEDGED") == []


@pytest.mark.parametrize("mutation", ["expired_lease", "wrong_owner"])
def test_current_state_drift_refuses_without_an_event(tmp_path, mutation):
    runtime, port, draft = _journey(tmp_path)
    with runtime.store.transaction() as connection:
        if mutation == "expired_lease":
            connection.execute("UPDATE attempts SET lease_expires_at_ms=0 WHERE attempt_id=?", (port.attempt_id,))
        else:
            connection.execute("UPDATE jobs SET owner_seat='ceo' WHERE job_id=?", (draft.job_id,))
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


@pytest.mark.parametrize("mutation", ["checkpoint", "provider_session"])
def test_existing_store_fences_reject_immutable_source_mutation(tmp_path, mutation):
    runtime, port, draft = _journey(tmp_path)
    with pytest.raises(StateConflict, match="immutable"):
        with runtime.store.transaction() as connection:
            if mutation == "checkpoint":
                connection.execute("UPDATE attempts SET checkpoint_json=? WHERE attempt_id=?",
                                   (json.dumps({"next_actions": ["Different action."]}), SOURCE_ID))
            else:
                connection.execute("UPDATE harness_session_epochs SET provider_session_id='OTHER-SESSION' WHERE attempt_id=?", (port.attempt_id,))
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


def test_wrong_attempt_or_stale_fence_cannot_prepare(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(SOURCE_ID, draft)
    port.lease = AttemptLease(dataclasses.replace(port.lease.attempt, fence_generation=99), port.lease_token)
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


@pytest.mark.parametrize("field,value", [("capsule_id", "f" * 64), ("provider_session_id", "OTHER-SESSION")])
def test_wrong_ack_cannot_create_consumption_evidence(tmp_path, field, value):
    runtime, port, draft = _journey(tmp_path)
    capsule = port.prepare_operator_continuation(port.attempt_id, draft)
    ack = ContinuationAck(OPERATOR_CONTINUATION_ACK_SCHEMA, port.attempt_id,
                          capsule.capsule_id, "PROVIDER-SESSION-1", True)
    with pytest.raises(StateConflict):
        port.acknowledge_operator_continuation(port.attempt_id, dataclasses.replace(ack, **{field: value}))
    assert _events(runtime, "OPERATOR_CONTINUATION_ACKNOWLEDGED") == []


@pytest.mark.parametrize("field,value", [("actor", "untrusted"), ("worker_id", "predecessor-worker")])
def test_existing_event_fence_rejects_metadata_mutation(tmp_path, field, value):
    runtime, port, draft = _journey(tmp_path)
    port.prepare_operator_continuation(port.attempt_id, draft)
    with pytest.raises(StateConflict, match="immutable"):
        with runtime.store.transaction() as connection:
            connection.execute(f"UPDATE events SET {field}=? WHERE event_type='OPERATOR_CONTINUATION_PREPARED'", (value,))
    port.prepare_operator_continuation(port.attempt_id, draft)
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


def test_existing_event_fence_rejects_payload_mutation_without_replacement(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    port.prepare_operator_continuation(port.attempt_id, draft)
    row = _events(runtime, "OPERATOR_CONTINUATION_PREPARED")[0]
    payload = json.loads(row["payload_json"])
    payload["capsule"]["next_action"] = "Tampered action."
    with pytest.raises(StateConflict, match="immutable"):
        with runtime.store.transaction() as connection:
            connection.execute("UPDATE events SET payload_json=? WHERE event_id=?", (json.dumps(payload), row["event_id"]))
    port.prepare_operator_continuation(port.attempt_id, draft)
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


def test_reopened_runtime_replays_the_persisted_capsule(tmp_path):
    from control_plane.executive_runtime import Runtime
    runtime, port, draft = _journey(tmp_path)
    first = port.prepare_operator_continuation(port.attempt_id, draft)
    reopened = Runtime.at(tmp_path)
    second_port = ExecutiveOperatorHarnessPort(reopened, port.lease)
    second = second_port.prepare_operator_continuation(port.attempt_id, draft)
    assert first.canonical_bytes() == second.canonical_bytes()
    assert len(_events(reopened, "OPERATOR_CONTINUATION_PREPARED")) == 1


def test_transaction_failure_leaves_no_partial_capsule(tmp_path, monkeypatch):
    runtime, port, draft = _journey(tmp_path)
    original = runtime.store.append_event
    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs.get("event_type") == "OPERATOR_CONTINUATION_PREPARED":
            raise RuntimeError("simulated transaction interruption")
    monkeypatch.setattr(runtime.store, "append_event", fail_after_insert)
    with pytest.raises(RuntimeError, match="simulated transaction interruption"):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


def test_concurrent_preparations_share_one_identity(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    runtime, port, draft = _journey(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: port.prepare_operator_continuation(port.attempt_id, draft), range(2)))
    assert results[0].canonical_bytes() == results[1].canonical_bytes()
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


def test_timestamp_comes_from_runtime_and_remains_frozen(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    runtime, port, draft = _journey(tmp_path)
    now = runtime.store.now_ms()
    monkeypatch.setattr(runtime.store, "now_ms", lambda: now)
    first = port.prepare_operator_continuation(port.attempt_id, draft)
    expected = datetime.fromtimestamp(now / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    assert first.generated_at == expected
    monkeypatch.setattr(runtime.store, "now_ms", lambda: now + 1000)
    assert port.prepare_operator_continuation(port.attempt_id, draft).canonical_bytes() == first.canonical_bytes()


@pytest.mark.parametrize("side", ["source", "target"])
def test_effect_unknown_blocks_prepare_without_a_new_event(tmp_path, side):
    runtime, port, draft = _journey(tmp_path)
    source = side == "source"
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection, aggregate_type="operator_operation", aggregate_id="ohf-op:unknown-fixture",
            event_type="OPERATOR_OPERATION_EFFECT_UNKNOWN", actor="supervisor",
            job_id=draft.job_id, attempt_id=SOURCE_ID if source else port.attempt_id,
            worker_id="predecessor-worker" if source else "worker-a", quota_class="default",
            command_id="ohf-op:unknown-fixture:effect-unknown", payload={"operation_kind": "TURN"},
        )
    with pytest.raises(StateConflict, match="unreconciled"):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


@pytest.mark.parametrize("method", [
    ExecutiveOperatorHarnessPort.prepare_operator_continuation,
    ExecutiveOperatorHarnessPort.acknowledge_operator_continuation,
])
def test_public_continuation_types_are_resolvable(method):
    from typing import get_type_hints
    assert get_type_hints(method)


def _seed_prepared_event(runtime, port, draft, *, quota_class="default", change=None):
    from datetime import datetime, timezone
    from control_plane.operator_continuation import finalize_continuation
    now = runtime.store.now_ms()
    stamp = datetime.fromtimestamp(now / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    capsule = finalize_continuation(draft, generated_at=stamp)
    facts = runtime.current_harness_binding_source(port.attempt_id)
    payload = {
        "schema_version": "mastermind.operator_continuation_prepared/v1",
        "source_attempt_id": SOURCE_ID, "target_attempt_id": port.attempt_id,
        "capsule_id": capsule.capsule_id, "capsule_semantic_digest": capsule.semantic_digest,
        "provider_session_id": "PROVIDER-SESSION-1", "session_epoch_id": facts.session_epoch_id,
        "capsule": capsule.to_dict(),
    }
    if change is not None:
        change(payload)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection, aggregate_type="attempt", aggregate_id=port.attempt_id,
            event_type="OPERATOR_CONTINUATION_PREPARED", actor="supervisor",
            job_id=draft.job_id, attempt_id=port.attempt_id, worker_id="worker-a", quota_class=quota_class,
            command_id=f"operator-continuation:prepare:{port.attempt_id}", payload=payload, timestamp_ms=now,
        )


def test_preexisting_event_with_wrong_quota_identity_is_not_replayed(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    with runtime.store.transaction() as connection:
        quota = dict(connection.execute(
            "SELECT * FROM worker_quota_classes WHERE worker_id='worker-a' AND quota_class='default'"
        ).fetchone())
        quota.update(quota_class="foreign", status="AVAILABLE", held_attempt_id=None, fence_counter=0)
        connection.execute(
            f"INSERT INTO worker_quota_classes ({','.join(quota)}) VALUES ({','.join('?' for _ in quota)})",
            tuple(quota.values()),
        )
    _seed_prepared_event(runtime, port, draft, quota_class="foreign")
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


@pytest.mark.parametrize("field", ["capsule_semantic_digest", "session_epoch_id", "provider_session_id"])
def test_foreign_prepared_payload_is_not_replayed(tmp_path, field):
    runtime, port, draft = _journey(tmp_path)
    _seed_prepared_event(runtime, port, draft, change=lambda p: p.update({field: "foreign"}))
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


def test_content_address_tampering_is_not_replayed(tmp_path):
    runtime, port, draft = _journey(tmp_path)
    _seed_prepared_event(runtime, port, draft,
                         change=lambda p: p["capsule"].update(next_action="Forged work."))
    with pytest.raises(StateConflict):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1


@pytest.mark.parametrize("ended,writer,held,accepted", [
    (False, "RELEASED", False, False), (True, "UNKNOWN", False, False),
    (True, "HELD", False, False), (True, "RELEASED", True, False),
    (True, "RELEASED", False, True),
])
def test_predecessor_generation_requires_positive_release_evidence(tmp_path, ended, writer, held, accepted):
    runtime, port, draft = _journey(tmp_path, source_evidence=False)
    with runtime.store.transaction() as connection:
        epoch = dict(connection.execute("SELECT * FROM harness_session_epochs WHERE attempt_id=?", (port.attempt_id,)).fetchone())
        generation = dict(connection.execute("SELECT * FROM process_generations WHERE session_epoch_id=?", (epoch["session_epoch_id"],)).fetchone())
        epoch.update(session_epoch_id=epoch["session_epoch_id"][:-8] + "00000001",
                     attempt_id=SOURCE_ID, worker_id="predecessor-worker")
        generation.update(process_generation_id=generation["process_generation_id"][:-8] + "00000001",
                          session_epoch_id=epoch["session_epoch_id"], worker_id="predecessor-worker",
                          ended_at_ms=runtime.store.now_ms() if ended else None,
                          executive_writer_held=int(held), provider_writer_state=writer)
        for table, row in (("harness_session_epochs", epoch), ("process_generations", generation)):
            connection.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
    if accepted:
        port.prepare_operator_continuation(port.attempt_id, draft)
        assert len(_events(runtime, "OPERATOR_CONTINUATION_PREPARED")) == 1
    else:
        with pytest.raises(StateConflict, match="predecessor"):
            port.prepare_operator_continuation(port.attempt_id, draft)
        assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []


def _seed_released_predecessor(runtime, port):
    """Historical fixture evidence only; no claim of an actual provider process."""
    with runtime.store.transaction() as connection:
        epoch = dict(connection.execute(
            "SELECT * FROM harness_session_epochs WHERE attempt_id=?", (port.attempt_id,)
        ).fetchone())
        generation = dict(connection.execute(
            "SELECT * FROM process_generations WHERE session_epoch_id=?", (epoch["session_epoch_id"],)
        ).fetchone())
        epoch.update(session_epoch_id=epoch["session_epoch_id"][:-8] + "11111111",
                     attempt_id=SOURCE_ID, worker_id="predecessor-worker")
        generation.update(process_generation_id=generation["process_generation_id"][:-8] + "11111111",
                          session_epoch_id=epoch["session_epoch_id"], worker_id="predecessor-worker",
                          ended_at_ms=runtime.store.now_ms(), executive_writer_held=0,
                          provider_writer_state="RELEASED")
        for table, row in (("harness_session_epochs", epoch), ("process_generations", generation)):
            connection.execute(
                f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
                tuple(row.values()),
            )


def test_missing_predecessor_process_evidence_is_not_release(tmp_path):
    runtime, port, draft = _journey(tmp_path, source_evidence=False)
    with pytest.raises(StateConflict, match="predecessor"):
        port.prepare_operator_continuation(port.attempt_id, draft)
    assert _events(runtime, "OPERATOR_CONTINUATION_PREPARED") == []
