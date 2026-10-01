"""Causal tests for the R119 atomic domain-consumption later-turn reservation.

These tests exercise ``OperatorHarnessRegistry.reserve_domain_consumption_turn``
end-to-end through the public R7A domain lifecycle:

* Seed an active (CHECKPOINTED) domain with completed initial
  ``begin_turn`` INTENT + APPLIED + OHF_CANDIDATE_RESULT_RECORDED via
  ``_r7a_seed_active_domain_with_review``;
* Derive the current settled reviewed-consumption projection digest via
  the public ``project_cycle_domain_consumption`` reader;
* Call ``reserve_domain_consumption_turn`` and assert exact Event,
  charge row and INTENT identity, plus idempotent exact-replay;
* Cover the full inventory guard set: missing/duplicate/foreign/
  unacknowledged/interrupted/EFFECT_UNKNOWN initial evidence; lease/
  writer/host/digest refusals before any side effect; full-ledger
  drift refusals; exact FINAL replay with zero mutations; boundary
  counts; and a production-disabled profile refusal before effects.

The seed already runs the supervisor's domain dispatch, so the initial
BEGIN_TURN + APPLIED + candidate evidence for the domain attempt are
authoritative when the test enters.  The unique admitted domain work
step (``r6a-step-1``) is the only step carried by the typed plan.
"""
import hashlib
import dataclasses
import json
import sqlite3
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import MappingProxyType

import pytest

from control_plane.executive_runtime import (
    COO_DOMAIN_EXECUTION_PROFILE,
    AttemptRegistry,
    CooCyclePolicy,
    OperationId,
    OperatorHarnessRegistry,
    Runtime,
    StateConflict,
    _coo_domain_admitted,
    _coo_domain_row,
    _coo_provider_budget_body,
    _COO_PROVIDER_BUDGET_EVENT,
    _coo_domain_consumption_projection,
    _normalise_constraints,
    orchestration_digest,
)
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from tests.test_executive_coo_hierarchy import _r7a_seed_active_domain_with_review
from tests.test_executive_coo_r116_charge_schema import CHARGE_COLUMNS


CHED_ROOT_SCHEMA = "mastermind.executive_coo_provider_work_budget_reservation/v1"


def _lease(runtime: Runtime, attempt_id: str) -> tuple[int, str]:
    """Return ``(fence_generation, lease_token)`` for a live CHECKPOINTED attempt."""

    with runtime.store.read() as connection:
        row = connection.execute(
            "SELECT fence_generation, lease_token FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
    assert row is not None and row["lease_token"] is not None
    return int(row["fence_generation"]), str(row["lease_token"])


def _domain_attempt(runtime: Runtime, domain_attempt_id: str) -> sqlite3.Row:
    with runtime.store.read() as connection:
        row = connection.execute(
            """
            SELECT g.process_generation_id, g.session_epoch_id, g.generation_number,
                   g.worker_id, g.executive_writer_held,
                   e.attempt_id, e.epoch_number, e.state, e.provider_session_id
            FROM process_generations g
            JOIN harness_session_epochs e
              ON e.session_epoch_id = g.session_epoch_id
            WHERE e.attempt_id = ?
            """,
            (domain_attempt_id,),
        ).fetchone()
    assert row is not None
    return row


def _begin_turn_intents(runtime: Runtime, attempt_id: str) -> list[sqlite3.Row]:
    with runtime.store.read() as connection:
        return list(
            connection.execute(
                """
                SELECT * FROM events
                WHERE aggregate_type='operator_operation'
                  AND event_type='OPERATOR_OPERATION_INTENT'
                  AND attempt_id=?
                ORDER BY event_id
                """,
                (attempt_id,),
            )
        )


def _charge_events(runtime: Runtime, domain_job_id: str) -> list[sqlite3.Row]:
    with runtime.store.read() as connection:
        return list(
            connection.execute(
                "SELECT * FROM events WHERE event_type=? AND aggregate_id=? ORDER BY event_id",
                (
                    "COO_DOMAIN_CONSUMPTION_CHARGED",
                    domain_job_id,
                ),
            )
        )


def _charge_rows(runtime: Runtime, root_job_id: str) -> list[sqlite3.Row]:
    with runtime.store.read() as connection:
        return list(
            connection.execute(
                "SELECT * FROM coo_provider_charges WHERE root_job_id=? ORDER BY event_id",
                (root_job_id,),
            )
        )


def _inventory(runtime: Runtime, root_job_id: str | None = None) -> dict:
    """Return a byte-stable snapshot of every persisted table (durable only)."""

    with runtime.store.read() as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        snapshot: dict[str, list[dict]] = {}
        for table in tables:
            columns = [col[1] for col in connection.execute(
                f"PRAGMA table_info({table})"
            )]
            rows = list(connection.execute(f"SELECT * FROM {table}"))
            payload = []
            for row in rows:
                rec = {}
                for idx, column in enumerate(columns):
                    value = row[idx]
                    rec[column] = value
                payload.append(json.dumps(rec, sort_keys=True, default=str))
            snapshot[table] = sorted(payload)
    return snapshot


def _expected_charge_id(operation_id: str) -> str:
    return hashlib.sha256(
        ("coo-domain-consumption:" + operation_id).encode("utf-8")
    ).hexdigest()


def _seeded_domain(tmp_path, monkeypatch, *, genuine_enabled=False) -> tuple:
    """Return (runtime, root, domain, domain_attempt_id) for a settled reviewed
    domain.

    Follows the R7A seeded path through the full work + independent-review
    cycle so the public settled-review projection reader
    (``project_cycle_domain_consumption``) finds no living children and
    the new ``reserve_domain_consumption_turn`` API has the closed v2
    root/domain admission, settled reviewed projection, completed initial
    BEGIN_TURN + APPLIED + OHF_CANDIDATE_RESULT_RECORDED, and the unique
    ``r6a-step-1`` work step id available as its canonical anchors.
    """

    from tests.test_executive_coo_hierarchy import (
        _r7a_complete_review,
        _r7a_complete_work,
        _r7a_dispatch_cycle_work,
        _r7a_plan_digest_for_domain,
        _r7a_runtime_with_work_and_review_workers,
    )

    if genuine_enabled:
        from control_plane.executive_agent_capabilities import DEFAULT_CAPABILITY_POLICY_PATH
        raw = json.loads(DEFAULT_CAPABILITY_POLICY_PATH.read_bytes())
        raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] = True
        policy_path = tmp_path / "genuine-enabled-capability-policy.json"
        policy_path.write_text(json.dumps(raw), encoding="utf-8")
        real_loader = ExecutionCapabilityRegistry.load
        registry = real_loader(policy_path)
        assert registry.policy_digest != real_loader().policy_digest
        registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
        monkeypatch.setattr(
            ExecutionCapabilityRegistry, "load",
            classmethod(lambda cls, *args, **kwargs: registry),
        )
    runtime, root, domain, _adapter, _dispatch = _r7a_seed_active_domain_with_review(
        tmp_path, monkeypatch=monkeypatch,
    )
    source_registry = ExecutionCapabilityRegistry.load()
    domain_profile = source_registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    enabled_profile = dataclasses.replace(domain_profile, enabled=True)
    enabled_registry = dataclasses.replace(
        source_registry,
        profiles=MappingProxyType({
            **source_registry.profiles,
            COO_DOMAIN_EXECUTION_PROFILE: enabled_profile,
        }),
    )
    monkeypatch.setattr(
        ExecutionCapabilityRegistry,
        "load",
        classmethod(lambda cls, *args, **kwargs: enabled_registry),
    )
    domain_attempt_id = domain.current_attempt_id
    assert domain_attempt_id is not None
    _r7a_runtime_with_work_and_review_workers(runtime)
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )
    work = leaves[0]
    plan_digest = _r7a_plan_digest_for_domain(
        runtime, root.job_id, domain_attempt_id,
    )
    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    work_seal = _r7a_complete_work(
        runtime,
        work_dispatch,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        identity_seed=9101,
    )
    review = runtime.jobs.create_cycle_review(
        root.job_id,
        work.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-review:{work.job_id}:1",
    )
    review_dispatch = runtime.attempts.dispatch_cycle_job(
        review.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{review.job_id}:attempt:1",
        worker_id="worker-r6a-review",
        quota_class="codex-coo",
    )
    _r7a_complete_review(
        runtime,
        review_dispatch,
        plan_attempt_id=domain_attempt_id,
        plan_digest=plan_digest,
        reviewed_job_id=work.job_id,
        reviewed_attempt_id=work_dispatch.attempt.attempt_id,
        reviewed_result_digest=work_seal["role_result_digest"],
        identity_seed=9102,
    )
    settled = runtime.jobs.get_job(domain.job_id)
    assert settled is not None
    assert settled.current_attempt_id == domain_attempt_id
    return runtime, root, settled, domain_attempt_id


def _consumption_projection_digest(runtime: Runtime, root_job_id: str, attempt_id: str) -> str:
    projection = runtime.jobs.project_cycle_domain_consumption(
        root_job_id, domain_attempt_id=attempt_id,
    )
    return str(projection["consumption_projection_digest"])


def _happy_args(runtime: Runtime, root_job_id: str, attempt_id: str):
    """Build the success-path kwargs for ``reserve_domain_consumption_turn``."""

    fence, token = _lease(runtime, attempt_id)
    durable = _domain_attempt(runtime, attempt_id)
    from control_plane.executive_runtime import ProcessGenerationRef
    generation = ProcessGenerationRef(
        str(durable["process_generation_id"]),
        str(durable["session_epoch_id"]),
        int(durable["generation_number"]),
        str(durable["worker_id"]),
    )
    digest = _consumption_projection_digest(runtime, root_job_id, attempt_id)
    operation_id = OperationId(f"ohf-op:coo-consume-{attempt_id[:8]}")
    return generation, operation_id, fence, token, digest


def _drop_immutability_trigger(database: Path, trigger_name: str) -> str:
    connection = sqlite3.connect(database)
    try:
        trigger_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
            (trigger_name,),
        ).fetchone()
        assert trigger_sql is not None, f"missing {trigger_name}"
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.commit()
        return trigger_sql[0]
    finally:
        connection.close()


def _stage_charge(runtime, root_id, job_id, attempt_id, identity, *, row=True, actor="coo"):
    budget = runtime.jobs.project_cycle_domain_provider_budget(root_id)
    with runtime.store.transaction() as connection:
        attempt = connection.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        payload = {
            "charge_id": f"r119-charge-{identity}", "root_job_id": root_id,
            "job_id": job_id, "attempt_id": attempt_id,
            "worker_id": attempt["worker_id"], "operation_id": f"r119-op-{identity}",
            "effect_class": "ORDINARY", "turn_id": f"r119-turn-{identity}",
            "reservation_identity": budget["reservation_digest"],
        }
        runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=job_id,
            event_type="COO_PROVIDER_CHARGE_RECORDED", actor=actor,
            job_id=job_id, attempt_id=attempt_id, worker_id=attempt["worker_id"],
            quota_class=attempt["quota_class"], payload=payload,
        )
        event_id = connection.execute("SELECT MAX(event_id) FROM events").fetchone()[0]
        if row:
            connection.execute(
                f"INSERT INTO coo_provider_charges({','.join(CHARGE_COLUMNS)}) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (payload["charge_id"], root_id, job_id, attempt_id, attempt["worker_id"],
                 payload["operation_id"], "ORDINARY", payload["turn_id"],
                 payload["reservation_identity"], event_id, runtime.store.now_ms()),
            )


def test_fresh_reservation_appends_final_charge_intent_and_coo_provider_charge_row(
    tmp_path, monkeypatch,
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    before_charge_events = len(_charge_events(runtime, domain.job_id))
    before_charge_rows = len(_charge_rows(runtime, root.job_id))
    before_intents = len(_begin_turn_intents(runtime, attempt_id))
    before_inventory = _inventory(runtime)

    turn = runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )

    assert turn.attempt_id == attempt_id
    assert turn.session_epoch_id == generation.session_epoch_id
    assert turn.process_generation_id == generation.process_generation_id
    assert turn.turn_id != operation_id.command_id
    charge_event_rows = _charge_events(runtime, domain.job_id)
    assert len(charge_event_rows) == before_charge_events + 1
    charge_event = charge_event_rows[-1]
    assert charge_event["actor"] == "coo"
    assert charge_event["aggregate_type"] == "job"
    assert charge_event["aggregate_id"] == domain.job_id
    assert charge_event["job_id"] == domain.job_id
    assert charge_event["attempt_id"] == attempt_id
    payload = json.loads(charge_event["payload_json"])
    expected_charge_id = _expected_charge_id(operation_id.command_id)
    assert payload["charge_id"] == expected_charge_id
    assert payload["root_job_id"] == root.job_id
    assert payload["domain_job_id"] == domain.job_id
    assert payload["domain_attempt_id"] == attempt_id
    assert payload["operation_id"] == operation_id.command_id
    assert payload["effect_class"] == "FINAL"
    assert payload["turn_id"] == turn.turn_id
    assert payload["session_epoch_id"] == turn.session_epoch_id
    assert payload["process_generation_id"] == turn.process_generation_id
    assert payload["consumption_projection_digest"] == digest
    budget_body = runtime.jobs.project_cycle_domain_provider_budget(root.job_id)
    assert payload["reservation_identity"] == budget_body["reservation_digest"]
    charge_rows = _charge_rows(runtime, root.job_id)
    assert len(charge_rows) == before_charge_rows + 1
    charge_row = charge_rows[-1]
    for column in CHARGE_COLUMNS:
        assert column in charge_row.keys()
    assert charge_row["charge_id"] == expected_charge_id
    assert charge_row["operation_id"] == operation_id.command_id
    assert charge_row["effect_class"] == "FINAL"
    assert charge_row["turn_id"] == turn.turn_id
    assert charge_row["reservation_identity"] == budget_body["reservation_digest"]
    assert charge_row["event_id"] == int(charge_event["event_id"])
    intents = _begin_turn_intents(runtime, attempt_id)
    assert len(intents) == before_intents + 1
    later_intent = intents[-1]
    assert later_intent["command_id"] == operation_id.command_id
    assert later_intent["aggregate_id"] == operation_id.command_id
    assert later_intent["event_type"] == "OPERATOR_OPERATION_INTENT"
    assert later_intent["worker_id"] == generation.worker_id
    intent_payload = json.loads(later_intent["payload_json"])
    assert intent_payload["schema_version"] == "mastermind.operator_harness_turn_intent/v1"
    assert intent_payload["operation_kind"] == "begin_turn"
    assert intent_payload["attempt_id"] == attempt_id
    assert intent_payload["session_epoch_id"] == turn.session_epoch_id
    assert intent_payload["process_generation_id"] == turn.process_generation_id
    assert intent_payload["worker_id"] == generation.worker_id
    assert intent_payload["provider_session_id"] is not None
    assert intent_payload["turn_id"] == turn.turn_id


def test_exact_replay_returns_identical_turnref_with_zero_mutations(
    tmp_path, monkeypatch,
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    turn_first = runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    inventory_after_first = _inventory(runtime)

    turn_second = runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    assert turn_second.turn_id == turn_first.turn_id
    assert turn_second.session_epoch_id == turn_first.session_epoch_id
    assert turn_second.process_generation_id == turn_first.process_generation_id
    assert turn_second.attempt_id == turn_first.attempt_id
    assert _inventory(runtime) == inventory_after_first


def test_31_ordinary_then_one_final_consumption_succeeds(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    charge_root = root.job_id
    for ordinal in range(1, 32):
        with runtime.store.transaction() as connection:
            attempt_row = connection.execute(
                "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            payload = {
                "charge_id": f"charge-r119-{ordinal}",
                "root_job_id": charge_root,
                "operation_id": f"operation-r119-{ordinal}",
                "effect_class": "ORDINARY",
                "turn_id": f"turn-r119-{ordinal}",
                "job_id": domain.job_id,
                "attempt_id": attempt_id,
                "worker_id": attempt_row["worker_id"],
                "reservation_identity": runtime.jobs.project_cycle_domain_provider_budget(
                    charge_root
                )["reservation_digest"],
            }
            runtime.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=domain.job_id,
                event_type="COO_PROVIDER_CHARGE_RECORDED",
                    actor="coo",
                    job_id=domain.job_id,
                    attempt_id=attempt_id,
                    worker_id=attempt_row["worker_id"],
                    quota_class=attempt_row["quota_class"],
                payload=payload,
            )
            charge_event_id = connection.execute(
                "SELECT MAX(event_id) FROM events"
            ).fetchone()[0]
            connection.execute(
                f"INSERT INTO coo_provider_charges({','.join(CHARGE_COLUMNS)}) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    payload["charge_id"], charge_root, domain.job_id,
                    attempt_id, attempt_row["worker_id"], payload["operation_id"],
                    "ORDINARY", payload["turn_id"], payload["reservation_identity"],
                    charge_event_id, runtime.store.now_ms(),
                ),
            )
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    turn = runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    with runtime.store.read() as connection:
        ordinary_count = connection.execute(
            "SELECT COUNT(*) FROM coo_provider_charges "
            "WHERE root_job_id=? AND effect_class='ORDINARY'",
            (charge_root,),
        ).fetchone()[0]
        final_count = connection.execute(
            "SELECT COUNT(*) FROM coo_provider_charges "
            "WHERE root_job_id=? AND effect_class='FINAL'",
            (charge_root,),
        ).fetchone()[0]
    assert ordinary_count == 31
    assert final_count == 1
    charge_rows = _charge_rows(runtime, charge_root)
    final_row = next(row for row in charge_rows if row["effect_class"] == "FINAL")
    assert final_row["turn_id"] == turn.turn_id


def test_32_ordinary_then_final_consumption_is_refused(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    charge_root = root.job_id
    with runtime.store.read() as connection:
        trigger = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
            "AND sql LIKE '%root ordinary COO provider charge ceiling%'"
        ).fetchone()
        assert trigger is not None
    trigger_sql = _drop_immutability_trigger(runtime.store.path, trigger["name"])
    for ordinal in range(1, 33):
        with runtime.store.transaction() as connection:
            attempt_row = connection.execute(
                "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            payload = {
                "charge_id": f"charge-r119-32-{ordinal}",
                "root_job_id": charge_root,
                "operation_id": f"operation-r119-32-{ordinal}",
                "effect_class": "ORDINARY",
                "turn_id": f"turn-r119-32-{ordinal}",
                "job_id": domain.job_id,
                "attempt_id": attempt_id,
                "worker_id": attempt_row["worker_id"],
                "reservation_identity": runtime.jobs.project_cycle_domain_provider_budget(
                    charge_root
                )["reservation_digest"],
            }
            runtime.store.append_event(
                connection,
                aggregate_type="job",
                aggregate_id=domain.job_id,
                event_type="COO_PROVIDER_CHARGE_RECORDED",
                actor="coo",
                job_id=domain.job_id,
                attempt_id=attempt_id,
                worker_id=attempt_row["worker_id"],
                quota_class=attempt_row["quota_class"],
                payload=payload,
            )
            charge_event_id = connection.execute(
                "SELECT MAX(event_id) FROM events"
            ).fetchone()[0]
            connection.execute(
                f"INSERT INTO coo_provider_charges({','.join(CHARGE_COLUMNS)}) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    payload["charge_id"], charge_root, domain.job_id,
                    attempt_id, attempt_row["worker_id"], payload["operation_id"],
                    "ORDINARY", payload["turn_id"], payload["reservation_identity"],
                    charge_event_id, runtime.store.now_ms(),
                ),
            )
    with runtime.store.transaction() as connection:
        connection.execute(trigger_sql)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="charge ceiling"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_new_command_after_final_slot_spent_is_refused(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, op_first, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=op_first,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    op_second = OperationId(f"ohf-op:coo-consume-other-{attempt_id[:8]}")
    before = _inventory(runtime)
    with pytest.raises(StateConflict):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=op_second,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_applied_for_later_operation_refuses_as_nonretryable(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    with runtime.store.transaction() as connection:
        from control_plane.operator_harness_contract import (
            OperationReceiptKind,
            operation_receipt_command_id,
        )
        attempt_row = connection.execute(
            "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        runtime.store.append_event(
            connection,
            aggregate_type="operator_operation",
            aggregate_id=operation_id.command_id,
            event_type=OperationReceiptKind.APPLIED.value,
            command_id=operation_receipt_command_id(
                operation_id, OperationReceiptKind.APPLIED,
            ),
            actor="supervisor",
            job_id=domain.job_id,
            attempt_id=attempt_id,
            worker_id=attempt_row["worker_id"],
            quota_class=attempt_row["quota_class"],
            payload={
                "schema_version": "mastermind.operator_harness_turn_applied/v1",
                "operation_kind": "begin_turn",
                "attempt_id": attempt_id,
                "session_epoch_id": generation.session_epoch_id,
                "process_generation_id": generation.process_generation_id,
                "turn_id": "consumed-turn",
                "provider_native_turn_id": "native-applied",
                "acknowledged": True,
            },
        )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="already APPLIED"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


@pytest.mark.parametrize(
    "kind",
    ["applied", "effect-unknown", "foreign-intent", "interrupt"],
)
def test_noncanonical_later_evidence_claims_bound_operation_and_refuses(
    tmp_path, monkeypatch, kind
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation, operation_id=operation_id,
        fence_generation=fence, lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    with runtime.store.read() as connection:
        intent = next(
            row for row in connection.execute(
                "SELECT * FROM events WHERE aggregate_type='operator_operation' "
                "AND event_type='OPERATOR_OPERATION_INTENT' AND attempt_id=?",
                (attempt_id,),
            ) if json.loads(row["payload_json"]).get("operation_kind") == "begin_turn"
        )
        payload = json.loads(intent["payload_json"])
        later_intent_payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM events WHERE command_id=?",
                (operation_id.command_id,),
            ).fetchone()["payload_json"]
        )
    from control_plane.operator_harness_contract import OperationReceiptKind
    receipt_kind = {
        "applied": OperationReceiptKind.APPLIED,
        "effect-unknown": OperationReceiptKind.EFFECT_UNKNOWN,
        "foreign-intent": OperationReceiptKind.INTENT,
        "interrupt": OperationReceiptKind.APPLIED,
    }[kind]
    if kind == "effect-unknown":
        receipt_payload = {
            "operation_id": operation_id.command_id,
            "operation_kind": "begin_turn",
                "turn_id": later_intent_payload["turn_id"],
            "phase": "fixture",
        }
    else:
        receipt_payload = {
                    "schema_version": "mastermind.operator_harness_turn_intent/v1",
                    "provider_session_id": payload["provider_session_id"],
            "operation_kind": "interrupt_turn" if kind == "interrupt" else "begin_turn",
            "operation_id": operation_id.command_id,
            "attempt_id": attempt_id,
            "session_epoch_id": payload["session_epoch_id"],
            "process_generation_id": payload["process_generation_id"],
                "turn_id": later_intent_payload["turn_id"],
        }
        if kind == "interrupt":
            receipt_payload["initial_turn_id"] = payload["turn_id"]
    with runtime.store.transaction() as connection:
        attempt = connection.execute(
            "SELECT worker_id,quota_class FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        runtime.store.append_event(
            connection, aggregate_type="operator_operation",
            aggregate_id=operation_id.command_id,
            event_type=receipt_kind.value,
            command_id=f"{operation_id.command_id}:{kind}-forged",
            actor="supervisor", job_id=domain.job_id, attempt_id=attempt_id,
            worker_id=attempt["worker_id"], quota_class=attempt["quota_class"],
            payload=receipt_payload,
        )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="interrupted|APPLIED|EFFECT_UNKNOWN|INTENT"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_noncanonical_initial_and_foreign_candidate_claims_refuse(
    tmp_path, monkeypatch
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    with runtime.store.read() as connection:
        intent = next(
            row for row in connection.execute(
                "SELECT * FROM events WHERE aggregate_type='operator_operation' "
                "AND event_type='OPERATOR_OPERATION_INTENT' AND attempt_id=?",
                (attempt_id,),
            ) if json.loads(row["payload_json"]).get("operation_kind") == "begin_turn"
        )
        applied = connection.execute(
            "SELECT * FROM events WHERE event_type='OPERATOR_OPERATION_APPLIED' "
            "AND attempt_id=?", (attempt_id,),
        ).fetchone()
        candidate = connection.execute(
            "SELECT * FROM events WHERE event_type='OHF_CANDIDATE_RESULT_RECORDED' "
            "AND attempt_id=?", (attempt_id,),
        ).fetchone()
    intent_payload = json.loads(intent["payload_json"])
    applied_payload = json.loads(applied["payload_json"])
    candidate_payload = json.loads(candidate["payload_json"])
    foreign_candidate = dict(candidate_payload)
    foreign_candidate["turn"] = dict(
        candidate_payload["turn"], turn_id="foreign-candidate-turn"
    )
    with runtime.store.transaction() as connection:
        attempt = connection.execute(
            "SELECT worker_id,quota_class FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        runtime.store.append_event(
            connection, aggregate_type="operator_operation",
            aggregate_id=intent["command_id"],
            event_type="OPERATOR_OPERATION_APPLIED",
            command_id="ohf-op:coo-noncanonical-initial:applied",
            actor="supervisor", job_id=domain.job_id, attempt_id=attempt_id,
            worker_id=attempt["worker_id"], quota_class=attempt["quota_class"],
            payload=dict(applied_payload),
        )
        runtime.store.append_event(
            connection, aggregate_type="operator_turn", aggregate_id="foreign-aggregate",
            event_type="OHF_CANDIDATE_RESULT_RECORDED",
            command_id=f"ohf-candidate:{intent_payload['turn_id']}-foreign",
            actor="supervisor", job_id=domain.job_id, attempt_id=attempt_id,
            worker_id=attempt["worker_id"], quota_class=attempt["quota_class"],
            payload=foreign_candidate,
        )
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="unacknowledged|candidate"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_initial_receipt_must_match_retained_plan_seal_and_candidate_digest(
    tmp_path, monkeypatch
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    with runtime.store.read() as connection:
        intent = next(
            row for row in connection.execute(
                "SELECT * FROM events WHERE aggregate_type='operator_operation' "
                "AND event_type='OPERATOR_OPERATION_INTENT' AND attempt_id=?",
                (attempt_id,),
            ) if json.loads(row["payload_json"]).get("operation_kind") == "begin_turn"
        )
        seal = connection.execute(
            "SELECT * FROM events WHERE event_type=? AND attempt_id=?",
            ("ORCHESTRATION_ROLE_RESULT_SEALED", attempt_id),
        ).fetchone()
        applied = connection.execute(
            "SELECT * FROM events WHERE event_type='OPERATOR_OPERATION_APPLIED' "
            "AND aggregate_id=?", (intent["command_id"],),
        ).fetchone()
    seal_payload = json.loads(seal["payload_json"])
    replacement = "forged-provider-native-turn"
    assert replacement != seal_payload["provider_native_turn_id"]
    applied_payload = json.loads(applied["payload_json"])
    applied_json = str(applied["payload_json"]).replace(
        json.dumps(seal_payload["provider_native_turn_id"]),
        json.dumps(replacement),
    )
    assert json.loads(applied_json)["provider_native_turn_id"] == replacement
    trigger_sql = _drop_immutability_trigger(
        database, "events_are_immutable_update"
    )
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE events SET payload_json=? WHERE event_id=?",
                (
                    applied_json, applied["event_id"],
                ),
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="acknowledgment drifted"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_attempt_linked_charge_orphan_with_forged_root_refuses(
    tmp_path, monkeypatch
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    with runtime.store.read() as connection:
        target = connection.execute(
            """
            SELECT j.job_id,a.attempt_id,a.worker_id,a.quota_class
            FROM jobs j JOIN attempts a ON a.job_id=j.job_id
            WHERE j.root_job_id=? AND j.orchestration_role='work' LIMIT 1
            """,
            (root.job_id,),
        ).fetchone()
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=target["job_id"],
            event_type="COO_PROVIDER_CHARGE_RECORDED", actor="coo",
            job_id=target["job_id"], attempt_id=target["attempt_id"],
            worker_id=target["worker_id"], quota_class=target["quota_class"],
            payload={
                "charge_id": "attempt-linked-orphan",
                "root_job_id": "foreign-root",
                "job_id": target["job_id"],
                "attempt_id": target["attempt_id"],
                "worker_id": target["worker_id"],
                "operation_id": "attempt-linked-orphan-operation",
                "effect_class": "ORDINARY",
                "turn_id": "attempt-linked-orphan-turn",
                "reservation_identity": runtime.jobs.project_cycle_domain_provider_budget(
                    root.job_id
                )["reservation_digest"],
            },
        )
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="orphan|lineage conflicts"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_effect_unknown_for_later_operation_refuses_as_nonretryable(
    tmp_path, monkeypatch,
):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    with runtime.store.transaction() as connection:
        from control_plane.operator_harness_contract import (
            OperationReceiptKind,
            operation_receipt_command_id,
        )
        attempt_row = connection.execute(
            "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        runtime.store.append_event(
            connection,
            aggregate_type="operator_operation",
            aggregate_id=operation_id.command_id,
            event_type=OperationReceiptKind.EFFECT_UNKNOWN.value,
            command_id=operation_receipt_command_id(
                operation_id, OperationReceiptKind.EFFECT_UNKNOWN,
            ),
            actor="supervisor",
            job_id=domain.job_id,
            attempt_id=attempt_id,
            worker_id=attempt_row["worker_id"],
            quota_class=attempt_row["quota_class"],
            payload={
                "schema_version": "mastermind.operator_harness_effect_unknown/v1",
                "phase": "reserve_domain_consumption",
                "detail": "deliberate fixture",
            },
        )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="EFFECT_UNKNOWN"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_duplicate_initial_begin_turn_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with runtime.store.transaction() as connection:
        attempt_row = connection.execute(
            "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        initial_intent = next(
            intent
            for intent in connection.execute(
                """
                SELECT * FROM events
                WHERE aggregate_type='operator_operation'
                  AND event_type='OPERATOR_OPERATION_INTENT'
                  AND attempt_id=?
                """,
                (attempt_id,),
            )
            if json.loads(intent["payload_json"]).get("operation_kind") == "begin_turn"
        )
        runtime.store.append_event(
            connection,
            aggregate_type="operator_operation",
            aggregate_id=initial_intent["command_id"],
            event_type="OPERATOR_OPERATION_INTENT",
            command_id="ohf-op:coo-duplicate-begin-turn",
            actor="supervisor",
            job_id=domain.job_id,
            attempt_id=attempt_id,
            worker_id=attempt_row["worker_id"],
            quota_class=attempt_row["quota_class"],
            payload=dict(json.loads(initial_intent["payload_json"])),
        )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="exactly one completed initial"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_missing_initial_begin_turn_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    trigger_sql = _drop_immutability_trigger(database, "events_are_immutable_delete")
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                DELETE FROM events
                WHERE aggregate_type='operator_operation'
                  AND event_type='OPERATOR_OPERATION_INTENT'
                  AND attempt_id=?
                  AND json_extract(payload_json,'$.operation_kind')='begin_turn'
                """,
                (attempt_id,),
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with pytest.raises(StateConflict, match="exactly one completed initial"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )


def test_unacknowledged_initial_evidence_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    trigger_sql = _drop_immutability_trigger(database, "events_are_immutable_delete")
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                DELETE FROM events
                WHERE event_type='OPERATOR_OPERATION_APPLIED' AND attempt_id=?
                  AND json_extract(payload_json,'$.operation_kind')='begin_turn'
                """,
                (attempt_id,),
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with pytest.raises(StateConflict, match="unacknowledged"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )


def test_interrupted_initial_evidence_without_candidate_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    trigger_sql = _drop_immutability_trigger(database, "events_are_immutable_delete")
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                "DELETE FROM events WHERE event_type='OHF_CANDIDATE_RESULT_RECORDED'"
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with pytest.raises(StateConflict, match="candidate missing"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )


def test_effect_unknown_for_initial_evidence_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with runtime.store.transaction() as connection:
        for intent in connection.execute(
            """
            SELECT * FROM events
            WHERE aggregate_type='operator_operation'
              AND event_type='OPERATOR_OPERATION_INTENT'
              AND attempt_id=?
            """,
            (attempt_id,),
        ):
            payload = json.loads(intent["payload_json"])
            if payload.get("operation_kind") != "begin_turn":
                continue
            initial_command_id = intent["command_id"]
            break
        else:
            pytest.fail("initial BEGIN_TURN evidence was already absent")
        from control_plane.operator_harness_contract import OperationReceiptKind
        runtime.store.append_event(
            connection,
            aggregate_type="operator_operation",
            aggregate_id=initial_command_id,
            event_type=OperationReceiptKind.EFFECT_UNKNOWN.value,
            command_id=f"{initial_command_id}:effect-unknown",
            actor="supervisor",
            job_id=domain.job_id,
            attempt_id=attempt_id,
            payload={"phase": "fixture", "detail": "fixture"},
        )
        charge_event_id = connection.execute(
            "SELECT MAX(event_id) FROM events"
        ).fetchone()[0]
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with pytest.raises(StateConflict, match="EFFECT_UNKNOWN"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )


def test_foreign_initial_begin_turn_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    trigger_sql = _drop_immutability_trigger(database, "events_are_immutable_update")
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE events
                SET payload_json=?
                WHERE aggregate_type='operator_operation'
                  AND event_type='OPERATOR_OPERATION_INTENT'
                  AND attempt_id=?
                  AND payload_json LIKE '%begin_turn%'
                """,
                (
                    json.dumps({
                        "schema_version": "mastermind.operator_harness_turn_intent/v1",
                        "operation_kind": "begin_turn",
                        "attempt_id": attempt_id,
                        "session_epoch_id": "foreign-session",
                        "process_generation_id": "foreign-generation",
                        "worker_id": "foreign-worker",
                        "provider_session_id": "foreign-session",
                        "turn_id": "foreign-turn",
                    }),
                    attempt_id,
                ),
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    with pytest.raises(StateConflict, match="foreign"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )


def test_disabled_production_profile_consumption_refuses_before_effects(
    tmp_path, monkeypatch,
):
    """A production-disabled profile cannot consume through any mutating
    API path.  The mutating surface must call the existing disabled-profile
guard without bypassing it and must leave full inventory unchanged."""

    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    source_registry = ExecutionCapabilityRegistry.load()
    domain_profile = source_registry.profiles[COO_DOMAIN_EXECUTION_PROFILE]
    disabled_profile = dataclasses.replace(domain_profile, enabled=False)
    disabled_registry = dataclasses.replace(
        source_registry,
        profiles=MappingProxyType({
            **source_registry.profiles,
            COO_DOMAIN_EXECUTION_PROFILE: disabled_profile,
        }),
    )
    monkeypatch.setattr(
        ExecutionCapabilityRegistry,
        "load",
        classmethod(lambda cls, *args, **kwargs: disabled_registry),
    )
    assert disabled_profile.enabled is False
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="production-disarmed"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before
    with runtime.store.read() as connection:
        domain_row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (domain.job_id,),
        ).fetchone()
        assert _coo_domain_admitted(domain_row, allow_disabled=True) is True
        with pytest.raises(StateConflict):
            _coo_domain_admitted(domain_row, allow_disabled=False)


def test_changed_projection_digest_refuses_before_effects(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, _digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    bogus_digest = "0" * 64
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="projection digest"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=bogus_digest,
        )
    assert _inventory(runtime) == before


def test_malformed_projection_digest_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, _digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="64-char hex"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest="not-hex",
        )
    assert _inventory(runtime) == before


def test_bad_lease_token_refuses_before_any_mutation(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, _fence, _token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="lease token"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=_fence,
            lease_token="definitely-not-the-real-lease-token",
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_tampered_budget_event_refuses(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    trigger_sql = _drop_immutability_trigger(database, "events_are_immutable_update")
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE events
                SET payload_json=?
                WHERE event_type=? AND aggregate_id=?
                """,
                (
                    json.dumps({"tampered": True}),
                    "COO_PROVIDER_WORK_BUDGET_RESERVED",
                    root.job_id,
                ),
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_tampered_reservation_identity_in_existing_charge_refuses(tmp_path, monkeypatch):
    """Mutating an existing immutable charge row's reservation_identity must
    be impossible (the trigger refuses), so this test instead stages a
    manually-attached charge row whose reservation_identity drifts, and
    proves the inventory guard rejects it before any new effects."""

    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    database = tmp_path / "runtime" / "data" / "control_plane" / "executive.sqlite3"
    with sqlite3.connect(database) as connection:
        budget = connection.execute(
            "SELECT payload_json FROM events WHERE event_type=? AND aggregate_id=?",
            ("COO_PROVIDER_WORK_BUDGET_RESERVED", root.job_id),
        ).fetchone()
    body = json.loads(budget[0])
    body["reservation_digest"] = "f" * 64
    trigger_sql = _drop_immutability_trigger(database, "events_are_immutable_update")
    try:
        with sqlite3.connect(database) as connection:
            connection.execute(
                """
                UPDATE events
                SET payload_json=?
                WHERE event_type=? AND aggregate_id=?
                """,
                (json.dumps(body), "COO_PROVIDER_WORK_BUDGET_RESERVED", root.job_id),
            )
            connection.commit()
    finally:
        with sqlite3.connect(database) as connection:
            connection.execute(trigger_sql)
            connection.commit()
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation,
            operation_id=operation_id,
            fence_generation=fence,
            lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_orphan_charge_event_refuses_before_new_effects(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    _stage_charge(runtime, root.job_id, domain.job_id, attempt_id, "orphan", row=False)
    generation, operation_id, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="orphan"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


@pytest.mark.parametrize("failure_stage", ["charge_insert", "intent_append"])
def test_atomic_rollback_after_partial_reservation(tmp_path, monkeypatch, failure_stage):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    with runtime.store.transaction() as connection:
        if failure_stage == "charge_insert":
            connection.execute(
                "CREATE TRIGGER r119_injected_failure BEFORE INSERT ON coo_provider_charges "
                "WHEN NEW.effect_class='FINAL' BEGIN "
                "SELECT RAISE(ABORT,'r119 charge insert failure'); END"
            )
        else:
            connection.execute(
                "CREATE TRIGGER r119_injected_failure BEFORE INSERT ON events "
                "WHEN NEW.event_type='OPERATOR_OPERATION_INTENT' "
                "AND NEW.command_id='" + operation_id.command_id + "' BEGIN "
                "SELECT RAISE(ABORT,'r119 intent append failure'); END"
            )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="r119 .* failure"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before



def test_reservation_holds_31_ordinary_inventory_identity(tmp_path, monkeypatch):
    """The 31st ORDINARY charge must already bind to a charge Event whose
    payload mirrors every column; a fresh reservation must preserve that
    binding without writing an unrelated row."""

    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    charge_root = root.job_id
    for ordinal in range(1, 32):
        with runtime.store.transaction() as connection:
            attempt_row = connection.execute(
                "SELECT worker_id, quota_class FROM attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            payload = {
                "charge_id": f"charge-bind-{ordinal}",
                "root_job_id": charge_root,
                "operation_id": f"operation-bind-{ordinal}",
                "effect_class": "ORDINARY",
                "turn_id": f"turn-bind-{ordinal}",
                "job_id": domain.job_id,
                "attempt_id": attempt_id,
                "worker_id": attempt_row["worker_id"],
                "reservation_identity": runtime.jobs.project_cycle_domain_provider_budget(
                    charge_root
                )["reservation_digest"],
            }
            runtime.store.append_event(
                    connection,
                    aggregate_type="job",
                    aggregate_id=domain.job_id,
                    event_type="COO_PROVIDER_CHARGE_RECORDED",
                    actor="coo",
                    job_id=domain.job_id,
                    attempt_id=attempt_id,
                    worker_id=attempt_row["worker_id"],
                    quota_class=attempt_row["quota_class"],
                payload=payload,
            )
            charge_event_id = connection.execute(
                "SELECT MAX(event_id) FROM events"
            ).fetchone()[0]
            connection.execute(
                f"INSERT INTO coo_provider_charges({','.join(CHARGE_COLUMNS)}) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    payload["charge_id"], charge_root, domain.job_id,
                    attempt_id, attempt_row["worker_id"], payload["operation_id"],
                    "ORDINARY", payload["turn_id"], payload["reservation_identity"],
                    charge_event_id, runtime.store.now_ms(),
                ),
            )
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    charge_rows = _charge_rows(runtime, charge_root)
    assert len(charge_rows) == 32
    final_row = next(row for row in charge_rows if row["effect_class"] == "FINAL")
    final_event = next(
        event
        for event in _charge_events(runtime, domain.job_id)
        if int(event["event_id"]) == int(final_row["event_id"])
    )
    payload = json.loads(final_event["payload_json"])
    identity_columns = [column for column in CHARGE_COLUMNS if column not in {"event_id", "created_at_ms"}]
    for column in identity_columns:
        assert str(payload.get(column, "")) == str(final_row[column])
    assert int(final_event["event_id"]) == int(final_row["event_id"])


def test_concurrent_replays_collapse_to_single_turn(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    before_inventory = _inventory(runtime)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda _: OperatorHarnessRegistry.reserve_domain_consumption_turn(
                runtime.operator_harness,
                generation=generation,
                operation_id=operation_id,
                fence_generation=fence,
                lease_token=token,
                expected_consumption_projection_digest=digest,
            ),
            range(2),
        ))
    assert results[0].turn_id == results[1].turn_id
    charge_rows = _charge_rows(runtime, root.job_id)
    assert len(charge_rows) == 1
    final_rows = [row for row in charge_rows if row["effect_class"] == "FINAL"]
    assert len(final_rows) == 1


def test_ordinary_root_and_flat_job_path_stay_refused(tmp_path):
    """Without a domain admitted, the API has no current domain attempt /
    OHF generation and must refuse; ordinary roots continue to refuse
    seal_cycle_domain_consumption too."""

    from control_plane.operator_harness_contract import ProcessGenerationRef
    runtime = Runtime.at(tmp_path)
    bogus_generation = ProcessGenerationRef(
        process_generation_id="PG-fake",
        session_epoch_id="SE-fake",
        generation_number=1,
        worker_id="worker-fake",
    )
    with pytest.raises(StateConflict):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=bogus_generation,
            operation_id=OperationId("ohf-op:coo-fake-consume"),
            fence_generation=1,
            lease_token="fake-token",
            expected_consumption_projection_digest="0" * 64,
        )


def test_typed_plan_step_id_is_unique_domain_step(tmp_path, monkeypatch):
    """The R7A typed plan envelope admits exactly one unique step
    (``r6a-step-1``).  The new API must not mint or reference a different
    step id; the FINAL charge payload and the BEGIN_TURN intent must
    carry no per-step identifier."""

    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    leaves = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{attempt_id}",
    )
    assert len(leaves) == 1
    assert leaves[0].plan_step_id == "r6a-step-1"
    generation, operation_id, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    turn = runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation,
        operation_id=operation_id,
        fence_generation=fence,
        lease_token=token,
        expected_consumption_projection_digest=digest,
    )
    charge_payload = json.loads(_charge_events(runtime, domain.job_id)[-1]["payload_json"])
    assert "plan_step_id" not in charge_payload
    intent_payload = json.loads(
        next(
            intent
            for intent in _begin_turn_intents(runtime, attempt_id)
            if intent["command_id"] == operation_id.command_id
        )["payload_json"]
    )
    assert "plan_step_id" not in intent_payload
    assert turn.turn_id.startswith("ohf-coo-consumption-turn-")

@pytest.mark.parametrize("orphan_role", ["plan", "work", "review"])
@pytest.mark.parametrize("actor", ["coo", "forged"])
def test_root_wide_orphan_event_cannot_hide_on_leaf_or_wrong_actor(tmp_path, monkeypatch, orphan_role, actor):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    with runtime.store.read() as connection:
        target = connection.execute(
            "SELECT j.job_id,a.attempt_id FROM jobs j JOIN attempts a ON a.job_id=j.job_id "
            "WHERE j.root_job_id=? AND j.orchestration_role=?",
            (root.job_id, orphan_role),
        ).fetchone()
    _stage_charge(runtime, root.job_id, target["job_id"], target["attempt_id"], "foreign-event", row=False, actor=actor)
    generation, op, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="orphan"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=op, fence_generation=fence,
            lease_token=token, expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_root_inventory_accepts_domain_work_and_independent_review_charges(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    with runtime.store.read() as connection:
        targets = connection.execute(
            "SELECT j.job_id,a.attempt_id,j.orchestration_role FROM jobs j "
            "JOIN attempts a ON a.attempt_id=j.current_attempt_id "
            "WHERE j.root_job_id=? AND j.orchestration_role IN ('plan','work','review')",
            (root.job_id,),
        ).fetchall()
    assert {target["orchestration_role"] for target in targets} == {"plan", "work", "review"}
    for target in targets:
        _stage_charge(runtime, root.job_id, target["job_id"], target["attempt_id"], target["orchestration_role"])
    generation, op, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    turn = runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation, operation_id=op, fence_generation=fence,
        lease_token=token, expected_consumption_projection_digest=digest,
    )
    assert turn.attempt_id == attempt_id
    assert len(_charge_rows(runtime, root.job_id)) == 4


def test_ordinary_turn_guard_does_not_inherit_final_seal_exception(tmp_path, monkeypatch):
    from control_plane.executive_runtime import SessionEpochRef
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, op, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="active-work admitted"):
        runtime.operator_harness.reserve_turn(
            epoch=SessionEpochRef(generation.session_epoch_id, attempt_id, generation.worker_id, 1),
            generation=generation, operation_id=op,
            fence_generation=fence, lease_token=token,
        )
    assert _inventory(runtime) == before


@pytest.mark.parametrize("drift", ["epoch", "generation_number", "worker", "writer", "ended", "fence"])
def test_final_reservation_rejects_forged_refs_or_lost_current_custody(tmp_path, monkeypatch, drift):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    generation, op, fence, token, digest = _happy_args(runtime, root.job_id, attempt_id)
    if drift == "epoch":
        generation = dataclasses.replace(generation, session_epoch_id="foreign-epoch")
    elif drift == "generation_number":
        generation = dataclasses.replace(generation, generation_number=2)
    elif drift == "worker":
        generation = dataclasses.replace(generation, worker_id="foreign-worker")
    elif drift == "fence":
        fence += 1
    else:
        with runtime.store.transaction() as connection:
            if drift == "writer":
                connection.execute("UPDATE process_generations SET executive_writer_held=0 WHERE process_generation_id=?", (generation.process_generation_id,))
            else:
                connection.execute("UPDATE process_generations SET ended_at_ms=? WHERE process_generation_id=?", (runtime.store.now_ms(), generation.process_generation_id))
    before = _inventory(runtime)
    with pytest.raises(StateConflict):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=op, fence_generation=fence,
            lease_token=token, expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


# Consequential-review counterexamples: drive the public reservation API after
# changing only the evidence edge under examination. Fault injection is confined
# to these temporary test databases, with immutable triggers restored before use.
def _reserve_from_args(runtime, args):
    generation, operation_id, fence, token, digest = args
    return runtime.operator_harness.reserve_domain_consumption_turn(
        generation=generation, operation_id=operation_id,
        fence_generation=fence, lease_token=token,
        expected_consumption_projection_digest=digest,
    )


def _initial_evidence(runtime, attempt_id):
    with runtime.store.read() as connection:
        intent = next(event for event in connection.execute(
            "SELECT * FROM events WHERE event_type='OPERATOR_OPERATION_INTENT' AND attempt_id=?",
            (attempt_id,),
        ) if json.loads(event["payload_json"]).get("operation_kind") == "begin_turn")
        applied = connection.execute(
            "SELECT * FROM events WHERE event_type='OPERATOR_OPERATION_APPLIED' AND aggregate_id=?",
            (intent["command_id"],),
        ).fetchone()
        candidate = connection.execute(
            "SELECT * FROM events WHERE event_type='OHF_CANDIDATE_RESULT_RECORDED' AND attempt_id=?",
            (attempt_id,),
        ).fetchone()
    return intent, applied, candidate


def _replace_test_event(runtime, event_id, **changes):
    trigger_sql = _drop_immutability_trigger(runtime.store.path, "events_are_immutable_update")
    try:
        with sqlite3.connect(runtime.store.path) as connection:
            connection.execute(
                "UPDATE events SET " + ",".join(f"{name}=?" for name in changes) + " WHERE event_id=?",
                (*changes.values(), event_id),
            )
    finally:
        with sqlite3.connect(runtime.store.path) as connection:
            connection.execute(trigger_sql)


def test_genuine_enabled_pin_exposes_current_pre_dispatch_domain_creation_gate(tmp_path, monkeypatch):
    from control_plane.executive_agent_capabilities import DEFAULT_CAPABILITY_POLICY_PATH, CapabilityPolicyError
    from control_plane.executive_runtime import JobRegistry
    canonical_bytes = DEFAULT_CAPABILITY_POLICY_PATH.read_bytes()
    observed = {}
    original_create = JobRegistry.create_cycle_domain

    def observe_creation(self, root_id, **kwargs):
        observed["registry"] = self
        observed["root"] = self.get_job(root_id)
        return original_create(self, root_id, **kwargs)

    monkeypatch.setattr(JobRegistry, "create_cycle_domain", observe_creation)
    with pytest.raises(CapabilityPolicyError, match="is not disabled"):
        _seeded_domain(tmp_path, monkeypatch, genuine_enabled=True)
    registry = ExecutionCapabilityRegistry.load()
    root = observed["root"]
    assert root.constraints["capability_policy_digest"] == registry.policy_digest
    assert root.constraints["execution_profile_digest"] == registry.resolve(COO_DOMAIN_EXECUTION_PROFILE).profile_digest
    assert DEFAULT_CAPABILITY_POLICY_PATH.read_bytes() == canonical_bytes
    assert json.loads(canonical_bytes)["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] is False
    with observed["registry"].store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs WHERE parent_job_id=?", (root.job_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM process_generations").fetchone()[0] == 0
    # This proves an existing pre-dispatch gate, not enabled-runtime admission.


@pytest.mark.parametrize("receipt_kind", ["OPERATOR_OPERATION_APPLIED", "OPERATOR_OPERATION_EFFECT_UNKNOWN"])
@pytest.mark.parametrize("edge", ["aggregate", "canonical-command", "payload-operation", "payload-turn"])
def test_later_receipt_cannot_hide_behind_wrong_headers_or_aggregate_type(tmp_path, monkeypatch, receipt_kind, edge):
    from control_plane.operator_harness_contract import OperationReceiptKind, operation_receipt_command_id
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    args = _happy_args(runtime, root.job_id, attempt_id)
    later_turn = _reserve_from_args(runtime, args)
    operation = args[1]
    payload = {"phase": "identity-counterexample"}
    aggregate = "unrelated-aggregate"
    command = "unrelated-command"
    if edge == "aggregate": aggregate = operation.command_id
    elif edge == "canonical-command": command = operation_receipt_command_id(operation, OperationReceiptKind(receipt_kind))
    elif edge == "payload-operation": payload["operation_id"] = operation.command_id
    else: payload["turn_id"] = later_turn.turn_id
    with runtime.store.transaction() as connection:
        runtime.store.append_event(
            connection, aggregate_type="foreign", aggregate_id=aggregate,
            command_id=command, event_type=receipt_kind, actor="supervisor", payload=payload,
        )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="APPLIED|EFFECT_UNKNOWN"):
        _reserve_from_args(runtime, args)
    assert _inventory(runtime) == before


def test_duplicate_initial_applied_affiliates_through_attempt_even_when_turn_and_aggregate_lie(tmp_path, monkeypatch):
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    _intent, applied, _candidate = _initial_evidence(runtime, attempt_id)
    payload = json.loads(applied["payload_json"])
    payload["turn_id"] = "lying-turn"
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="foreign", aggregate_id="foreign-op",
            event_type="OPERATOR_OPERATION_APPLIED", command_id="duplicate-initial-with-lying-keys",
            actor="supervisor", payload=payload)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="unacknowledged"):
        _reserve_from_args(runtime, _happy_args(runtime, root.job_id, attempt_id))
    assert _inventory(runtime) == before


def test_duplicate_candidate_payload_turn_is_detected_without_canonical_headers(tmp_path, monkeypatch):
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    _intent, _applied, candidate = _initial_evidence(runtime, attempt_id)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="foreign", aggregate_id="foreign-turn",
            event_type="OHF_CANDIDATE_RESULT_RECORDED", command_id="duplicate-candidate-with-lying-keys",
            actor="supervisor", payload=json.loads(candidate["payload_json"]))
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="candidate"):
        _reserve_from_args(runtime, _happy_args(runtime, root.job_id, attempt_id))
    assert _inventory(runtime) == before


@pytest.mark.parametrize("field", ["candidate", "events", "cursor"])
def test_candidate_substitution_cannot_reuse_retained_plan_seal(tmp_path, monkeypatch, field):
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    _intent, _applied, candidate = _initial_evidence(runtime, attempt_id)
    payload = json.loads(candidate["payload_json"])
    payload[field] = None
    _replace_test_event(runtime, candidate["event_id"], payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")))
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="candidate|seal"):
        _reserve_from_args(runtime, _happy_args(runtime, root.job_id, attempt_id))
    assert _inventory(runtime) == before


def test_actual_public_interrupt_receipt_refuses_with_candidate_still_present(tmp_path, monkeypatch):
    from control_plane.executive_runtime import TurnRef
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    intent, _applied, candidate = _initial_evidence(runtime, attempt_id)
    payload = json.loads(intent["payload_json"])
    turn = TurnRef(payload["turn_id"], payload["session_epoch_id"], payload["process_generation_id"], attempt_id)
    fence, token = _lease(runtime, attempt_id)
    interrupt = OperationId("ohf-op:actual-initial-interrupt")
    runtime.operator_harness.reserve_turn_operation(turn=turn, operation_id=interrupt,
        operation_kind="interrupt_turn", fence_generation=fence, lease_token=token)
    runtime.operator_harness.apply_turn_operation(turn=turn, operation_id=interrupt,
        operation_kind="interrupt_turn", fence_generation=fence, lease_token=token)
    with runtime.store.read() as connection:
        assert connection.execute("SELECT 1 FROM events WHERE event_id=?", (candidate["event_id"],)).fetchone()
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="interrupted"):
        _reserve_from_args(runtime, _happy_args(runtime, root.job_id, attempt_id))
    assert _inventory(runtime) == before


@pytest.mark.parametrize("edge", ["header-attempt", "payload-job", "payload-attempt", "domain-job", "domain-attempt", "epoch", "generation", "aggregate-attempt", "operation"])
@pytest.mark.parametrize("replay", [False, True])
def test_charge_orphan_identity_links_cannot_be_hidden_by_a_forged_root(tmp_path, monkeypatch, edge, replay):
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    args = _happy_args(runtime, root.job_id, attempt_id)
    if replay: _reserve_from_args(runtime, args)
    initial, _applied, _candidate = _initial_evidence(runtime, attempt_id)
    payload = {"root_job_id": "lying-foreign-root", "effect_class": "ORDINARY"}
    aggregate = "foreign-id"
    header_attempt = None
    if edge == "header-attempt": header_attempt = attempt_id
    elif edge == "payload-job": payload["job_id"] = domain.job_id
    elif edge == "payload-attempt": payload["attempt_id"] = attempt_id
    elif edge == "domain-job": payload["domain_job_id"] = domain.job_id
    elif edge == "domain-attempt": payload["domain_attempt_id"] = attempt_id
    elif edge == "epoch": payload["session_epoch_id"] = args[0].session_epoch_id
    elif edge == "generation": payload["process_generation_id"] = args[0].process_generation_id
    elif edge == "aggregate-attempt": aggregate = attempt_id
    else: payload["operation_id"] = initial["command_id"]
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="foreign", aggregate_id=aggregate,
            event_type="COO_PROVIDER_CHARGE_RECORDED", actor="coo", attempt_id=header_attempt, payload=payload)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="orphan|lineage conflicts"):
        _reserve_from_args(runtime, args)
    assert _inventory(runtime) == before


@pytest.mark.parametrize("hidden_edge", [None, "operation-aggregate", "turn-aggregate", "payload-turn"])
@pytest.mark.parametrize("replay", [False, True])
def test_valid_other_root_charge_does_not_spend_current_root_budget(tmp_path, monkeypatch, hidden_edge, replay):
    import tests.test_executive_coo_hierarchy as hierarchy_fixtures
    original_runtime = hierarchy_fixtures._r6a_runtime_with_operator

    def populated_foreign_runtime(path):
        from control_plane.executive_runtime import WorkerRegistry
        register = WorkerRegistry.register_worker
        def register_foreign(self, worker_id, *args, **kwargs):
            return register(self, "foreign-" + worker_id, *args, **kwargs)
        with monkeypatch.context() as registration_patch:
            registration_patch.setattr(WorkerRegistry, "register_worker", register_foreign)
            foreign = original_runtime(path)
        for ordinal in range(10):
            foreign.jobs.create_job(f"Existing unrelated queued job {ordinal}")
        return foreign

    with monkeypatch.context() as foreign_patch:
        foreign_patch.setattr(hierarchy_fixtures, "_r6a_runtime_with_operator", populated_foreign_runtime)
        foreign, foreign_root, foreign_domain, _adapter, _dispatch = _r7a_seed_active_domain_with_review(
            tmp_path / "other", monkeypatch=foreign_patch,
        )
    runtime, root, domain, attempt_id = _seeded_domain(tmp_path / "current", monkeypatch)
    assert foreign_root.job_id != root.job_id
    foreign_attempt = foreign_domain.current_attempt_id
    assert foreign_attempt is not None
    _stage_charge(foreign, foreign_root.job_id, foreign_domain.job_id, foreign_attempt, "foreign-root-control")
    with foreign.store.read() as connection:
        workers = list(connection.execute("SELECT * FROM workers"))
        quotas = list(connection.execute("SELECT * FROM worker_quota_classes"))
        jobs = list(connection.execute("SELECT * FROM jobs WHERE root_job_id=? ORDER BY depth", (foreign_root.job_id,)))
        attempts = list(connection.execute("SELECT * FROM attempts"))
        event = connection.execute("SELECT * FROM events WHERE event_type='COO_PROVIDER_CHARGE_RECORDED'").fetchone()
        charge = dict(connection.execute("SELECT * FROM coo_provider_charges").fetchone())
    with runtime.store.transaction() as connection:
        connection.execute("PRAGMA defer_foreign_keys=ON")
        for table, records in (("workers", workers), ("worker_quota_classes", quotas), ("jobs", jobs), ("attempts", attempts)):
            for record in records:
                names = list(record.keys())
                connection.execute(f"INSERT INTO {table}({','.join(names)}) VALUES({','.join('?' for _ in names)})", tuple(record))
        runtime.store.append_event(connection, aggregate_type=event["aggregate_type"], aggregate_id=event["aggregate_id"],
            event_type=event["event_type"], actor=event["actor"], job_id=event["job_id"], attempt_id=event["attempt_id"],
            worker_id=event["worker_id"], quota_class=event["quota_class"], payload=json.loads(event["payload_json"]))
        charge["event_id"] = connection.execute("SELECT MAX(event_id) FROM events").fetchone()[0]
        connection.execute(f"INSERT INTO coo_provider_charges({','.join(CHARGE_COLUMNS)}) VALUES({','.join('?' for _ in CHARGE_COLUMNS)})", tuple(charge[column] for column in CHARGE_COLUMNS))
    before_foreign = [dict(record) for record in _charge_rows(runtime, foreign_root.job_id)]
    args = _happy_args(runtime, root.job_id, attempt_id)
    if hidden_edge is not None:
        if replay:
            _reserve_from_args(runtime, args)
        initial, _applied, _candidate = _initial_evidence(runtime, attempt_id)
        initial_payload = json.loads(initial["payload_json"])
        aggregate = "foreign-aggregate"
        payload = {"root_job_id": foreign_root.job_id, "effect_class": "ORDINARY"}
        if hidden_edge == "operation-aggregate":
            aggregate = initial["command_id"]
        elif hidden_edge == "turn-aggregate":
            aggregate = initial_payload["turn_id"]
        else:
            payload["turn_id"] = initial_payload["turn_id"]
        with runtime.store.transaction() as connection:
            runtime.store.append_event(connection, aggregate_type="foreign", aggregate_id=aggregate,
                event_type="COO_PROVIDER_CHARGE_RECORDED", actor="coo", payload=payload)
        before = _inventory(runtime)
        with pytest.raises(StateConflict, match="lineage conflicts|orphan"):
            _reserve_from_args(runtime, args)
        assert _inventory(runtime) == before
        return
    turn = _reserve_from_args(runtime, args)
    before_replay = _inventory(runtime)
    assert _reserve_from_args(runtime, args) == turn
    assert _inventory(runtime) == before_replay
    assert [dict(record) for record in _charge_rows(runtime, foreign_root.job_id)] == before_foreign
    assert len(_charge_rows(runtime, root.job_id)) == 1


@pytest.mark.parametrize("receipt_kind", ["OPERATOR_OPERATION_INTENT", "OPERATOR_OPERATION_APPLIED", "OPERATOR_OPERATION_EFFECT_UNKNOWN"])
@pytest.mark.parametrize("false_kind", ["not-a-valid-kind", "start_session", None])
@pytest.mark.parametrize("replay", [False, True])
def test_initial_identity_is_reconciled_before_false_operation_kind(tmp_path, monkeypatch, receipt_kind, false_kind, replay):
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    args = _happy_args(runtime, root.job_id, attempt_id)
    if replay:
        _reserve_from_args(runtime, args)
    initial, applied, _candidate = _initial_evidence(runtime, attempt_id)
    payload = json.loads((initial if receipt_kind.endswith("INTENT") else applied)["payload_json"])
    payload["operation_kind"] = false_kind
    payload["turn_id"] = "lying-turn"
    aggregate = "unrelated-operation"
    if receipt_kind.endswith("INTENT"):
        aggregate = initial["command_id"]
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="foreign", aggregate_id=aggregate,
            event_type=receipt_kind, command_id="ohf-op:identity-before-discriminator-forgery",
            actor="supervisor", payload=payload)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="initial BEGIN_TURN|EFFECT_UNKNOWN|launch"):
        _reserve_from_args(runtime, args)
    assert _inventory(runtime) == before


@pytest.mark.parametrize("replay", [False, True])
def test_initial_operation_aggregate_only_false_kind_intent_refuses(tmp_path, monkeypatch, replay):
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    args = _happy_args(runtime, root.job_id, attempt_id)
    if replay: _reserve_from_args(runtime, args)
    initial, _applied, _candidate = _initial_evidence(runtime, attempt_id)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="foreign", aggregate_id=initial["command_id"],
            event_type="OPERATOR_OPERATION_INTENT", command_id="ohf-op:aggregate-only-false-kind",
            actor="supervisor", payload={"operation_kind": "not-a-valid-kind", "turn_id": "lying-turn"})
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="initial BEGIN_TURN"):
        _reserve_from_args(runtime, args)
    assert _inventory(runtime) == before


@pytest.mark.parametrize("nonturn_kind", ["start_session", "checkpoint"])
@pytest.mark.parametrize("receipt_kind", ["OPERATOR_OPERATION_INTENT", "OPERATOR_OPERATION_APPLIED", "OPERATOR_OPERATION_EFFECT_UNKNOWN"])
@pytest.mark.parametrize("edge", ["operation-aggregate", "payload-operation", "receipt-aggregate"])
@pytest.mark.parametrize("replay", [False, True])
def test_nonturn_operation_only_receipt_inventory_refuses(tmp_path, monkeypatch, nonturn_kind, receipt_kind, edge, replay):
    runtime, root, _domain, attempt_id = _seeded_domain(tmp_path, monkeypatch)
    args = _happy_args(runtime, root.job_id, attempt_id)
    if replay:
        _reserve_from_args(runtime, args)
    with runtime.store.read() as connection:
        intents = connection.execute("SELECT * FROM events WHERE event_type='OPERATOR_OPERATION_INTENT' AND attempt_id=?", (attempt_id,)).fetchall()
        current = next(event for event in intents if (
            json.loads(event["payload_json"]).get("operation_kind") == "start_session"
            if nonturn_kind == "start_session" else
            "expected_checkpoint_sequence" in json.loads(event["payload_json"])
        ))
    from control_plane.operator_harness_contract import OperationId, OperationReceiptKind, operation_receipt_command_id
    operation = current["command_id"]
    aggregate = operation
    payload = {"operation_kind": "not-a-valid-kind"}
    if edge == "payload-operation":
        aggregate = "unrelated-operation"
        payload["operation_id"] = operation
    elif edge == "receipt-aggregate":
        aggregate = operation_receipt_command_id(OperationId(operation), OperationReceiptKind.APPLIED)
    with runtime.store.transaction() as connection:
        runtime.store.append_event(connection, aggregate_type="operator_operation", aggregate_id=aggregate,
            event_type=receipt_kind, command_id="ohf-op:nonturn-shadow",
            actor="supervisor", payload=payload)
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="nonturn operation evidence"):
        _reserve_from_args(runtime, args)
    assert _inventory(runtime) == before
