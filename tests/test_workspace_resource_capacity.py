"""Actual inert Runtime/SQLite claims; all source probes are synthetic fixtures."""
import pytest
import json
from tests.test_finite_initial_transaction import _build, claim, snap
from tests import test_executive_finite_guards as helpers


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # Historical claims predate prospective capture retention. Preserve the
    # real original Event/Attempt transaction while exercising that absent path.
    import importlib.util
    if importlib.util.find_spec("control_plane.physical_capacity_capture_owner") is not None:
        from control_plane import physical_capacity_capture_owner as capture
        monkeypatch.setattr(capture, "mint_capacity_capture", lambda *a, **kw: None)
    original = helpers._drive_to_admitted
    def with_workstream(*args, **kwargs):
        return original(*args, **kwargs, workstream="WS:ONE")
    monkeypatch.setattr(helpers, "_drive_to_admitted", with_workstream)
    yield from _build(tmp_path, monkeypatch)


def test_real_retained_claim_projects_only_after_bound_read_closes_same(setup):
    from tests.test_runtime_admitted_plan_read import _bound
    from control_plane.workspace_resource_capacity import project_capacity_source
    s = setup
    lease = claim(s)
    selected = dict(work_ref="WS:ONE", root_job_id=s.job.root_job_id,
                    job_id=s.job.job_id, attempt_id=lease.attempt.attempt_id, now_ms=s.clock.value)
    with _bound(s.runtime) as (reader, _namespace, _binding):
        with reader.observe_bounded_read() as observation:
            source = observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
            with pytest.raises(RuntimeError):
                observation.receipt
        body = project_capacity_source(source, observation.receipt, **selected)
    assert body["claim_event_id"] == source.claim_event.event_id
    assert type(body["claim_event_id"]) is int
    assert body["begin_event_id"] == source.begin_event.event_id
    assert body["source_snapshot_sha256"] == s.p.evidence["provider_capacity"]["snapshot_hash"]
    assert body["current_eligibility"] == "NOT_EVALUATED" and body["can_place_work"] is False
    assert "actor" not in body and "capacity_evidence" not in body


@pytest.mark.parametrize("field", ["state", "source_identity", "before", "work_ref", "root_job_id", "job_id", "attempt_id"])
def test_safe_composer_rejects_foreign_receipt_or_selected_tuple(setup, field):
    import dataclasses
    from tests.test_runtime_admitted_plan_read import _bound
    from control_plane.workspace_resource_capacity import project_capacity_source
    s = setup
    lease = claim(s)
    selected = dict(work_ref="WS:ONE", root_job_id=s.job.root_job_id,
                    job_id=s.job.job_id, attempt_id=lease.attempt.attempt_id, now_ms=s.clock.value)
    with _bound(s.runtime) as (reader, _namespace, _binding):
        with reader.observe_bounded_read() as observation:
            source = observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
        receipt = observation.receipt
    if field in {"state", "source_identity", "before"}:
        bad = {"state": "CONFLICT", "source_identity": "f" * 32, "before": True}[field]
        receipt = dataclasses.replace(receipt, **{field: bad})
    else:
        selected[field] = "foreign"
    with pytest.raises(ValueError, match="RETAINED_CAPACITY_SOURCE_MISMATCH"):
        project_capacity_source(source, receipt, **selected)


def test_original_claim_capacity_is_read_without_acquisition_or_runtime_mutation(setup):
    s = setup
    lease = claim(s)
    before = snap(s)
    with s.runtime.observe_bounded_read() as observation:
        source = observation.read_retained_capacity_bounded(
            s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id,
        )
    assert source.root_metadata.root_job_id == s.job.root_job_id
    assert source.attempt.attempt_id == lease.attempt.attempt_id
    assert source.claim_event.command_id == s.command
    evidence = source.claim_event.payload["capacity_evidence"]
    assert evidence["provider_capacity"] == s.p.evidence["provider_capacity"]
    assert source.begin_event.event_id == evidence["physical_capacity"]["begin_event_id"]
    assert snap(s) == before


@pytest.mark.parametrize("field", ["root", "job", "attempt"])
def test_foreign_root_job_or_attempt_fails_closed_and_invalidates_selection(setup, field):
    s = setup
    lease = claim(s)
    selected = {"root": s.job.root_job_id, "job": s.job.job_id, "attempt": lease.attempt.attempt_id}
    selected[field] = "foreign-id"
    before = snap(s)
    with s.runtime.observe_bounded_read() as observation:
        with pytest.raises((ValueError, RuntimeError)):
            observation.read_retained_capacity_bounded(selected["root"], selected["job"], selected["attempt"])
        with pytest.raises(RuntimeError):
            observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
    assert snap(s) == before


def test_second_read_cannot_expand_one_runtime_observation_selection(setup):
    s = setup
    lease = claim(s)
    with s.runtime.observe_bounded_read() as observation:
        observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
        with pytest.raises(RuntimeError):
            observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)


def test_runtime_prevents_rewriting_retained_begin_pointer(setup):
    s = setup
    lease = claim(s)
    before = snap(s)
    with pytest.raises(RuntimeError, match="events are immutable"):
        with s.runtime.store.transaction() as connection:
            row = connection.execute("SELECT event_id,payload_json FROM events WHERE command_id=?", (s.command,)).fetchone()
            payload = json.loads(row["payload_json"])
            payload["capacity_evidence"]["physical_capacity"]["begin_event_id"] = row["event_id"]
            connection.execute("UPDATE events SET payload_json=? WHERE event_id=?", (json.dumps(payload), row["event_id"]))
    assert snap(s) == before
    with s.runtime.observe_bounded_read() as observation:
        source = observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
    assert source.begin_event.event_type == "PHYSICAL_RESOURCE_BEGIN"


def test_runtime_prevents_expanding_original_claim_payload(setup):
    s = setup
    lease = claim(s)
    before = snap(s)
    with pytest.raises(RuntimeError, match="events are immutable"):
        with s.runtime.store.transaction() as connection:
            row = connection.execute("SELECT event_id,payload_json FROM events WHERE command_id=?", (s.command,)).fetchone()
            payload = json.loads(row["payload_json"])
            payload["irrelevant_private_material"] = "x" * 65536
            connection.execute("UPDATE events SET payload_json=? WHERE event_id=?", (json.dumps(payload), row["event_id"]))
    assert snap(s) == before
    with s.runtime.observe_bounded_read() as observation:
        source = observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
    assert "irrelevant_private_material" not in source.claim_event.payload
