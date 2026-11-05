"""Timer bounds are source facts, not network or execution authority."""
import copy

import pytest

from control_plane import coo_observation as observation


def spec(due=1010, deadline=2000):
    return {"schema_version": observation.GATE_SCHEMA,
            "source": {"kind": "timer", "due_at_ms": due}, "deadline_at_ms": deadline,
            "max_samples": 1, "min_interval_ms": 0, "sample_timeout_ms": 0,
            "max_api_calls": 0, "max_response_bytes": 0}


def admission(*, gate=None, host=None, finite_expiry_ms=None):
    gate = spec() if gate is None else gate
    host = host or observation.TimerObservationHost("test-host")
    return observation.make_admission(root_job_id="JOB-1", plan_attempt_id="ATT-1",
        plan_digest="a" * 64, plan_step_id="step-0", root_creation_event_id=1,
        authority_policy_hash="b" * 64, spec=gate, admitted_at_ms=1000,
        scope=host.require_scope(root_job_id="JOB-1", source=gate["source"]),
        finite_expiry_ms=finite_expiry_ms)


@pytest.mark.parametrize("key,value", [
    ("max_samples", True), ("max_samples", 2), ("max_api_calls", 1),
    ("sample_timeout_ms", 1), ("deadline_at_ms", float("inf")),
    ("deadline_at_ms", 1010), ("deadline_at_ms", 2000.0),
    ("callback", "run arbitrary command"),
])
def test_unqualified_fields_and_budgets_refuse(key, value):
    gate = spec(); gate[key] = value
    with pytest.raises(observation.ObservationError):
        observation.validate_spec(gate)


def test_external_source_is_not_implicitly_admitted():
    gate = spec(); gate["source"] = {"kind": "github_ci", "repository": "owner/repo"}
    with pytest.raises(observation.ObservationError):
        observation.validate_spec(gate)


def test_due_timer_and_horizon_are_absolute_acquisition_bounds():
    admitted = admission(gate=spec(due=900), finite_expiry_ms=1500)
    assert admitted["spec"]["source"]["due_at_ms"] == 900
    assert admitted["effective_deadline_at_ms"] == 1500
    assert observation.make_record(admitted, 1000)["disposition"] == "MATERIAL"
    assert observation.make_record(admitted, 1500)["disposition"] == "EXPIRED"
    constrained = admission(host=observation.TimerObservationHost("test-host", 100))
    assert constrained["effective_deadline_at_ms"] == 1100
    with pytest.raises(observation.ObservationError, match="horizon"):
        admission(host=observation.TimerObservationHost("test-host", 5))


def test_record_rejects_coherent_wrong_clock_and_boolean_equivalence():
    admitted = admission()
    record = observation.make_record(admitted, 1010)
    changed = copy.deepcopy(record); changed["sample_index"] = True
    with pytest.raises(observation.ObservationError):
        observation.validate_record(changed, admitted)
    changed = copy.deepcopy(record); changed["snapshot"]["due_at_ms"] = 1009
    changed["snapshot_digest"] = observation.digest(changed["snapshot"])
    changed.pop("evidence_digest"); changed["evidence_digest"] = observation.digest(changed)
    with pytest.raises(observation.ObservationError):
        observation.validate_record(changed, admitted)


def test_scope_drift_is_not_repaired_by_changing_the_admitted_binding():
    admitted = admission()
    observation.TimerObservationHost("test-host").require_current(admission=admitted)
    with pytest.raises(observation.ObservationError, match="changed"):
        observation.TimerObservationHost("different-host").require_current(admission=admitted)
    with pytest.raises(observation.ObservationError, match="changed"):
        observation.TimerObservationHost("test-host", 2000).require_current(admission=admitted)
