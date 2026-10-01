"""Canonical reviewed role bodies in the COO consumption projection."""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from control_plane.executive_orchestration_result import (
    MAX_CANONICAL_RESULT_BYTES,
    canonical_bytes,
    canonical_digest,
)
from control_plane.executive_runtime import (
    StateConflict,
    orchestration_digest,
)
from control_plane import executive_runtime
from control_plane import executive_orchestration_result
from control_plane.executive_runtime import _coo_domain_consumption_projection
from control_plane.executive_agent_capabilities import (
    DEFAULT_CAPABILITY_POLICY_PATH,
    COO_DOMAIN_EXECUTION_PROFILE,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from tests.test_executive_os_phase1fc import _complete_ohf_role
from tests.test_executive_coo_hierarchy import (
    _r7a_dispatch_cycle_work,
    _r7a_plan_digest_for_domain,
    _r7a_runtime_with_work_and_review_workers,
    _r6a_submit_domain_root,
    _R6ADomainAdapter,
    _R7ADomainAdapter,
    _R6APromptSource,
)


def _seeded_runtime(
    tmp_path: Path, monkeypatch, *, reviewed=True, verdict="approve",
    review_worker="worker-r6a-review", producer_tag="first",
) -> dict:
    # Load genuine enabled bytes BEFORE immutable public root creation. The
    # typed hermetic adapter supplies observations; no disabled-profile proxy
    # or dataclass enabling under an old whole-policy digest is used.
    tmp_path.mkdir(parents=True, exist_ok=True)
    raw = json.loads(DEFAULT_CAPABILITY_POLICY_PATH.read_bytes())
    raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE]["enabled"] = True
    policy_path = tmp_path / "enabled-policy.json"
    policy_path.write_text(json.dumps(raw), encoding="utf-8")
    real_loader = ExecutionCapabilityRegistry.load
    registry = real_loader(policy_path)
    assert registry.policy_digest != real_loader().policy_digest
    registry.resolve(COO_DOMAIN_EXECUTION_PROFILE)
    monkeypatch.setattr(
        ExecutionCapabilityRegistry, "load",
        classmethod(lambda cls, *args, **kwargs: registry),
    )
    runtime, root, domain, _workspace = _r6a_submit_domain_root(
        tmp_path, business_impact="material" if reviewed else "routine",
    )
    assert root.constraints["capability_policy_digest"] == registry.policy_digest
    adapter = (_R7ADomainAdapter if reviewed else _R6ADomainAdapter)(runtime)
    supervisor = ExecutiveOperatorSupervisor(
        runtime, adapter_factory=lambda loader: adapter,
        prompt_source=_R6APromptSource(),
    )
    outcome = asyncio.run(supervisor.start_cycle_job(
        domain.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{domain.job_id}:attempt:1",
    ))
    assert outcome.outcome == "ACTIVE"
    domain = runtime.jobs.get_job(domain.job_id)
    assert domain is not None and domain.status.value == "CHECKPOINTED"
    _r7a_runtime_with_work_and_review_workers(runtime)
    domain_attempt_id = domain.current_attempt_id
    assert domain_attempt_id is not None
    work = runtime.jobs.admit_cycle_plan(
        root.job_id,
        command_id=f"coo-cycle:{root.job_id}:admit-plan:{domain_attempt_id}",
    )[0]
    plan_digest = _r7a_plan_digest_for_domain(
        runtime, root.job_id, domain_attempt_id
    )
    work_dispatch = _r7a_dispatch_cycle_work(
        runtime,
        root_job_id=root.job_id,
        work_job_id=work.job_id,
        worker_id="worker-r6a-work",
        quota_class="codex-coo",
    )
    work_evidence_digest = canonical_digest(
        {
            "source": "actual hermetic R121 producer fixture",
            "material": "non-empty canonical work evidence",
            "producer_tag": producer_tag,
        }
    )
    work_body = {
        "schema_version": "mastermind.work_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": domain_attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": work.plan_step_id,
        "repair_round": 0,
        "artifacts": [
            {
                "path": "RESULT.md",
                "digest": work_evidence_digest,
            }
        ],
        "evidence_digests": [work_evidence_digest],
    }
    work_seal, _terminal = _complete_ohf_role(
        runtime, work_dispatch, work_body, identity_seed=812101
    )
    if not reviewed:
        return locals()
    review_job = runtime.jobs.create_cycle_review(
        root.job_id,
        work.job_id,
        command_id=f"coo-cycle:{root.job_id}:create-review:{work.job_id}:1",
    )
    review_dispatch = runtime.attempts.dispatch_cycle_job(
        review_job.job_id,
        command_id=(
            f"coo-cycle:{root.job_id}:dispatch:{review_job.job_id}:attempt:1"
        ),
        worker_id=review_worker,
        quota_class="codex-coo",
    )
    assert review_dispatch is not None and review_dispatch.outcome == "ACTIVE"
    review_evidence_digest = canonical_digest(
        {
            "source": "actual hermetic R121 reviewer fixture",
            "material": "distinct independent review evidence",
            "producer_tag": producer_tag,
        }
    )
    review_body = {
        "schema_version": "mastermind.review_result/v1",
        "root_job_id": root.job_id,
        "plan_attempt_id": domain_attempt_id,
        "plan_digest": plan_digest,
        "plan_step_id": work.plan_step_id,
        "reviewed_job_id": work.job_id,
        "reviewed_attempt_id": work_dispatch.attempt.attempt_id,
        "reviewed_result_digest": work_seal["role_result_digest"],
        "repair_round": 0,
        "verdict": verdict,
        "evidence_digests": [review_evidence_digest],
        "findings": [
            {
                "code": "SOURCE_CONTROL",
                "severity": "blocking" if verdict == "reject" else "info",
                "message": "Exact distinct independently reviewed producer material",
                "evidence_digests": [review_evidence_digest],
            }
        ],
    }
    review_seal, _terminal = _complete_ohf_role(
        runtime,
        review_dispatch,
        review_body,
        identity_seed=812102,
    )
    return {
        "runtime": runtime,
        "root": root,
        "domain": domain,
        "domain_attempt_id": domain_attempt_id,
        "work": work,
        "work_dispatch": work_dispatch,
        "work_body": work_body,
        "work_seal": work_seal,
        "review_job": review_job,
        "review_dispatch": review_dispatch,
        "review_body": review_body,
        "review_seal": review_seal,
    }


def _root_and_projection(fixture: dict) -> tuple[sqlite3.Row, dict]:
    with fixture["runtime"].store.read() as connection:
        root_row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (fixture["root"].job_id,)
        ).fetchone()
    assert root_row is not None
    return root_row, _projection(fixture)


def _adversarial_update(runtime, table: str, sql: str, values: tuple) -> None:
    """Negative-only corruption, with all original trigger bytes restored."""
    assert table in {"jobs", "attempts", "events"}
    with sqlite3.connect(runtime.store.path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        triggers = connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
            (table,),
        ).fetchall()
        for name, _definition in triggers:
            connection.execute(f'DROP TRIGGER "{name}"')
        connection.execute(sql, values)
        for _name, definition in triggers:
            connection.execute(definition)


def _replace_event_payload(runtime, event_id: str, payload: dict) -> None:
    _adversarial_update(
        runtime, "events", "UPDATE events SET payload_json=? WHERE event_id=?",
        (json.dumps(payload, sort_keys=True, separators=(",", ":")), event_id),
    )


def _projection(fixture: dict) -> dict:
    return fixture["runtime"].jobs.project_cycle_domain_consumption(
        fixture["root"].job_id,
        domain_attempt_id=fixture["domain_attempt_id"],
    )


def _inventory(runtime) -> dict:
    """Full durable inventory, including Event, charges and native identities."""
    with runtime.store.read() as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        return {
            str(row[0]): sorted(
                [tuple(value) for value in connection.execute(f'SELECT * FROM "{row[0]}"')],
                key=repr,
            )
            for row in tables
        }


def _assert_refused_before_effects(fixture: dict, conflict: str) -> None:
    runtime = fixture["runtime"]
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match=conflict):
        _projection(fixture)
    assert _inventory(runtime) == before


def test_public_projection_contains_validated_distinct_work_and_review_bodies(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _seeded_runtime(tmp_path, monkeypatch)
    projection = _projection(fixture)

    assert projection["revision_results_schema_version"] == (
        "mastermind.executive_coo_domain_revision_results/v1"
    )
    revision = projection["revisions"][0]
    expected_result = {
        "ordinal": revision["ordinal"],
        "plan_step_id": revision["plan_step_id"],
        "current_job_id": revision["current_job_id"],
        "current_attempt_id": revision["current_attempt_id"],
        "work_result": fixture["work_body"],
        "qualifying_review_job_id": fixture["review_job"].job_id,
        "qualifying_review_attempt_id": (
            fixture["review_dispatch"].attempt.attempt_id
        ),
        "review_result": fixture["review_body"],
    }
    assert projection["revision_results"] == [expected_result]
    assert canonical_digest(fixture["work_body"]) == fixture["work_seal"][
        "role_result_digest"
    ]
    assert canonical_digest(fixture["review_body"]) == fixture["review_seal"][
        "role_result_digest"
    ]
    expected_digest = orchestration_digest(
        {
            key: value
            for key, value in projection.items()
            if key != "consumption_projection_digest"
        }
    )
    assert projection["consumption_projection_digest"] == expected_digest
    metadata_only = {
        key: value for key, value in projection.items()
        if key not in {"consumption_projection_digest", "revision_results",
                       "revision_results_schema_version"}
    }
    assert expected_digest != orchestration_digest(metadata_only)
    with fixture["runtime"].store.read() as connection:
        root_row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (fixture["root"].job_id,),
        ).fetchone()
        admission, plan_body = executive_runtime._validated_plan_admission(connection, root_row)
        original_revisions, _history = executive_runtime._current_orchestration_tree_material(
            connection, root_row, admission, plan_body,
            allow_active_domain_job_id=fixture["domain"].job_id,
        )
    assert projection["revisions"] == original_revisions
    assert len(canonical_bytes(projection)) <= MAX_CANONICAL_RESULT_BYTES
    assert _projection(fixture) == projection


def test_second_producer_run_binds_distinct_bodies_and_projection_digests(
    tmp_path: Path, monkeypatch
) -> None:
    first_patch = pytest.MonkeyPatch()
    second_patch = pytest.MonkeyPatch()
    try:
        first = _seeded_runtime(tmp_path / "first", first_patch)
        first_projection = _projection(first)
    finally:
        first_patch.undo()
    try:
        second = _seeded_runtime(tmp_path / "second", second_patch, producer_tag="second")
        second_projection = _projection(second)
    finally:
        second_patch.undo()

    assert first_projection["revision_results"][0]["work_result"] != (
        second_projection["revision_results"][0]["work_result"]
    )
    assert first_projection["revision_results"][0]["review_result"] != (
        second_projection["revision_results"][0]["review_result"]
    )
    assert first_projection["consumption_projection_digest"] != (
        second_projection["consumption_projection_digest"]
    )


def test_corrupt_body_under_stored_seal_digest_refuses_without_effects(
    tmp_path: Path, monkeypatch
) -> None:
    fixture = _seeded_runtime(tmp_path, monkeypatch)
    attempt_id = fixture["work_dispatch"].attempt.attempt_id
    with fixture["runtime"].store.read() as connection:
        event = connection.execute(
            """
            SELECT event_id,payload_json FROM events
            WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED'
              AND attempt_id=?
            """,
            (attempt_id,),
        ).fetchone()
        assert event is not None
        root_row, _projection_before = _root_and_projection(fixture)
        assert _coo_domain_consumption_projection(
            connection,
            root_row=root_row,
            domain_job_id=fixture["domain"].job_id,
            domain_attempt_id=fixture["domain_attempt_id"],
        ) == _projection_before
    payload = json.loads(event["payload_json"])
    payload["result_envelope"]["role_result"]["evidence_digests"] = ["00" * 32]
    _replace_event_payload(
        fixture["runtime"], str(event["event_id"]), payload
    )

    _assert_refused_before_effects(
        fixture, "sealed work result is invalid|seal receipt material is malformed"
    )


@pytest.mark.parametrize(
    "edge", ["review_job", "review_attempt", "review_grant", "review_principal",
             "review_target", "omitted_work_body", "omitted_review_body", "work_placement"],
)
def test_corrupted_selected_material_refuses_without_effects(tmp_path, monkeypatch, edge):
    fixture = _seeded_runtime(tmp_path, monkeypatch)
    runtime = fixture["runtime"]
    revision = _projection(fixture)["revisions"][0]
    if edge in {"review_job", "review_attempt"}:
        field = "reviews_job_id" if edge == "review_job" else "current_attempt_id"
        value = fixture["root"].job_id if edge == "review_job" else fixture["domain_attempt_id"]
        _adversarial_update(runtime, "jobs", f"UPDATE jobs SET {field}=? WHERE job_id=?",
                            (value, fixture["review_job"].job_id))
    elif edge in {"review_grant", "review_principal", "work_placement"}:
        field = {"review_grant": "effective_grant_digest",
                 "review_principal": "execution_principal_snapshot_digest",
                 "work_placement": "placement_snapshot_digest"}[edge]
        attempt_id = revision["current_attempt_id"] if edge == "work_placement" else revision["qualifying_review_attempt_id"]
        _adversarial_update(runtime, "attempts", f"UPDATE attempts SET {field}=? WHERE attempt_id=?",
                            ("0" * 64, attempt_id))
    else:
        attempt_id = revision["current_attempt_id"] if edge == "omitted_work_body" else revision["qualifying_review_attempt_id"]
        with runtime.store.read() as connection:
            event = connection.execute(
                "SELECT event_id,payload_json FROM events WHERE event_type='ORCHESTRATION_ROLE_RESULT_SEALED' AND attempt_id=?",
                (attempt_id,),
            ).fetchone()
        payload = json.loads(event["payload_json"])
        if edge.startswith("omitted"):
            del payload["result_envelope"]["role_result"]
        else:
            payload["result_envelope"]["role_result"]["reviewed_result_digest"] = "0" * 64
        _replace_event_payload(runtime, event["event_id"], payload)
    _assert_refused_before_effects(fixture, ".+")


@pytest.mark.parametrize("case", ["reject", "same_principal"])
def test_unresolved_or_non_independent_review_refuses(tmp_path, monkeypatch, case):
    fixture = _seeded_runtime(
        tmp_path, monkeypatch,
        verdict="reject" if case == "reject" else "approve",
        review_worker="worker-r6a-work" if case == "same_principal" else "worker-r6a-review",
    )
    _assert_refused_before_effects(fixture, "unresolved independent reject|qualifying independent approval")


def test_unreviewed_policy_has_canonical_work_and_null_review(tmp_path, monkeypatch):
    fixture = _seeded_runtime(tmp_path, monkeypatch, reviewed=False)
    before = _inventory(fixture["runtime"])
    projection = _projection(fixture)
    entry = projection["revision_results"][0]
    assert projection["revisions"][0]["review_required"] is False
    assert entry["work_result"] == fixture["work_body"]
    assert entry["qualifying_review_job_id"] is None
    assert entry["qualifying_review_attempt_id"] is None
    assert entry["review_result"] is None
    assert _inventory(fixture["runtime"]) == before


def test_checkpointed_domain_repair_currently_refuses_without_effects(tmp_path, monkeypatch):
    """R121 does not repair the separate missing active-domain creation flag.

    This real public negative is a receipted integration gap, not repair
    consumption acceptance or a SQL-manufactured positive.
    """
    fixture = _seeded_runtime(tmp_path, monkeypatch, verdict="reject")
    runtime, root, work = fixture["runtime"], fixture["root"], fixture["work"]
    rejected_digest = fixture["review_seal"]["role_result_digest"]
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="plan lineage does not name the completed plan child"):
        runtime.jobs.create_cycle_repair(
            root.job_id, work.job_id, fixture["review_job"].job_id,
            command_id=f"coo-cycle:{root.job_id}:create-repair:{work.job_id}:{fixture['review_job'].job_id}:{rejected_digest}:1",
        )
    assert _inventory(runtime) == before


@pytest.mark.parametrize("delta", [0, -1])
def test_scaled_total_byte_ceiling_includes_final_digest(tmp_path, monkeypatch, delta):
    """Synthetic scaled limit; actual public producers and serialization unchanged."""
    fixture = _seeded_runtime(tmp_path, monkeypatch)
    projection = _projection(fixture)
    exact_size = len(canonical_bytes(projection))
    assert exact_size > len(canonical_bytes(fixture["review_body"]))
    monkeypatch.setattr(executive_orchestration_result, "MAX_CANONICAL_RESULT_BYTES", exact_size + delta)
    before = _inventory(fixture["runtime"])
    if delta == 0:
        assert _projection(fixture) == projection
    else:
        with pytest.raises(StateConflict, match="projection exceeds its byte ceiling"):
            _projection(fixture)
    assert _inventory(fixture["runtime"]) == before


def test_projection_canonical_error_is_typed_and_without_effects(tmp_path, monkeypatch):
    fixture = _seeded_runtime(tmp_path, monkeypatch)
    def refuse_projection(value):
        if isinstance(value, dict) and value.get("schema_version") == "mastermind.executive_coo_domain_consumption_projection/v1":
            raise ValueError("synthetic canonical error in projection only")
        return canonical_bytes(value)
    monkeypatch.setattr(executive_orchestration_result, "canonical_bytes", refuse_projection)
    _assert_refused_before_effects(fixture, "projection is not canonical")


def test_metadata_only_expected_digest_cannot_reserve_or_reset_final_credit(tmp_path, monkeypatch):
    from tests.test_executive_coo_r119_later_turn import _happy_args
    fixture = _seeded_runtime(tmp_path, monkeypatch)
    runtime = fixture["runtime"]
    projection = _projection(fixture)
    obsolete = {
        key: value for key, value in projection.items()
        if key not in {"consumption_projection_digest", "revision_results", "revision_results_schema_version"}
    }
    generation, operation_id, fence, token, _digest = _happy_args(
        runtime, fixture["root"].job_id, fixture["domain_attempt_id"],
    )
    before = _inventory(runtime)
    with pytest.raises(StateConflict, match="projection.*drift|projection.*stale|digest"):
        runtime.operator_harness.reserve_domain_consumption_turn(
            generation=generation, operation_id=operation_id,
            fence_generation=fence, lease_token=token,
            expected_consumption_projection_digest=orchestration_digest(obsolete),
        )
    assert _inventory(runtime) == before
