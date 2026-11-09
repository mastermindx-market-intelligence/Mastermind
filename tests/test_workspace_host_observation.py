"""Real inert claim/BEGIN capture and original bounded Runtime reader."""
import copy
import dataclasses
import json
import pytest
from tests.test_finite_initial_transaction import _build, claim, snap
from tests import test_executive_finite_guards as helpers
from tests.test_runtime_admitted_plan_read import _bound
from control_plane.workspace_host_observation import project_host_observation, runtime_source_identity
from common.workspace_host_observation_contract import validate_observation


@pytest.fixture
def setup(tmp_path, monkeypatch):
    original = helpers._drive_to_admitted
    def with_workstream(*args, **kwargs):
        return original(*args, **kwargs, workstream="WS:ONE")
    monkeypatch.setattr(helpers, "_drive_to_admitted", with_workstream)
    yield from _build(tmp_path, monkeypatch)


def captured(s):
    lease = claim(s)
    selected = dict(work_ref="WS:ONE", root_job_id=s.job.root_job_id,
                    job_id=s.job.job_id, attempt_id=lease.attempt.attempt_id)
    with _bound(s.runtime) as (reader, _namespace, _binding):
        with reader.observe_bounded_read() as observation:
            source = observation.read_retained_capacity_bounded(s.job.root_job_id, s.job.job_id, lease.attempt.attempt_id)
        receipt = observation.receipt
    return source, receipt, dict(**selected, now_ms=s.clock.value,
        expected_runtime_identity=runtime_source_identity(s.runtime))


def test_actual_capture_to_bound_read_is_historical_physical_host_only(setup):
    source, receipt, selected = captured(setup)
    before = snap(setup)
    body = project_host_observation(source, receipt, **selected)
    assert validate_observation(body, selected) is body
    assert body["platform"] == "darwin"
    assert body["observed_host_role"] == "PHYSICAL_RESOURCE_HOST"
    assert body["snapshot"] == source.begin_event.payload["capacity_capture"]["snapshot"]
    assert body["age_ms"] == selected["now_ms"] - body["snapshot"]["observed_at_ms"]
    assert body["can_place_work"] is False and body["admission_state"] == "NOT_EVALUATED"
    assert "runtime_identity" not in json.dumps(body)
    assert "namespace_sha256" not in body and "worker_ready" not in body
    assert snap(setup) == before


@pytest.mark.parametrize("field", ["host_ref", "boot_ref", "capacity_pool_ref", "operation_key", "request_fingerprint", "runtime_identity_sha256", "source_commit_sha", "source_helper_sha256"])
def test_capture_identity_and_source_substitution_are_refused(setup, field):
    source, receipt, selected = captured(setup)
    payload = copy.deepcopy(source.begin_event.payload)
    payload["capacity_capture"]["binding"][field] = "foreign"
    source = dataclasses.replace(source, begin_event=dataclasses.replace(source.begin_event, payload=payload))
    with pytest.raises(ValueError):
        project_host_observation(source, receipt, **selected)


@pytest.mark.parametrize("case", ["absent", "extra", "snapshot", "digest", "clock", "capability", "future_read", "foreign_receipt", "foreign_runtime"])
def test_missing_or_changed_capture_and_clock_cannot_become_host_metrics(setup, case):
    source, receipt, selected = captured(setup)
    payload = copy.deepcopy(source.begin_event.payload)
    capture = payload["capacity_capture"]
    if case == "absent": payload.pop("capacity_capture")
    elif case == "extra": capture["path"] = "/private"
    elif case == "snapshot": capture["snapshot"]["pool_free_bytes"] -= 1
    elif case == "digest": capture["snapshot_sha256"] = "f" * 64
    elif case == "clock": capture["decision_time_ms"] -= 1000
    elif case == "capability": capture["can_place_work"] = True
    elif case == "future_read": selected["now_ms"] = 1
    elif case == "foreign_receipt": receipt = dataclasses.replace(receipt, source_identity="f" * 32)
    else: selected["expected_runtime_identity"] = "f" * 64
    source = dataclasses.replace(source, begin_event=dataclasses.replace(source.begin_event, payload=payload))
    with pytest.raises((ValueError, RuntimeError)):
        project_host_observation(source, receipt, **selected)


def test_old_observation_keeps_actual_age_and_never_becomes_current(setup):
    source, receipt, selected = captured(setup)
    selected["now_ms"] += 86_400_000
    body = project_host_observation(source, receipt, **selected)
    assert body["age_ms"] >= 86_400_000
    assert body["observation_kind"] == "RETAINED_PHYSICAL_BEGIN"
    assert body["admission_state"] == "NOT_EVALUATED"
    for key in ("age_ms", "oldest_observation_age_ms"):
        bad = {**body, key: 0}
        with pytest.raises(ValueError): validate_observation(bad, selected)
