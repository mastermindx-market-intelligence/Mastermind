"""Closed incident v2 provenance across real inert parent/client/broker pipes."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from control_plane import executive_incident_origin as o
from control_plane import executive_incident_forward_host as h
from control_plane import executive_incident_release_observation as i
from control_plane import executive_release_observation as generic
from tests.test_incident_origin_composition import world, chain, release, interval


@pytest.mark.parametrize("kind", ["origin-interval", "precheck"])
@pytest.mark.parametrize("field,value", [
    ("v", 1), ("purpose", "generic-release-v1"),
    ("cohort_content_sha256", "9" * 64),
])
def test_child_rejects_mismatched_initial_scope_before_action(world, monkeypatch, kind, field, value):
    send = o._write_child_frame
    def altered(child, frame, budget):
        if frame["kind"] == kind:
            frame = dict(frame, **{field: value})
        return send(child, frame, budget)
    monkeypatch.setattr(o, "_write_child_frame", altered)
    result, errors, _, connection, _ = chain(monkeypatch, world)
    assert result.classification == "REFUSED_CLEAN", (result, errors)
    assert connection.submissions == 0


@pytest.mark.parametrize("stage", o._STAGES)
@pytest.mark.parametrize("field,value", [
    ("v", 1), ("purpose", "generic-release-v1"),
    ("cohort_content_sha256", "9" * 64),
])
def test_broker_rejects_each_stage_substitution_without_replay(world, monkeypatch, stage, field, value):
    check = h._IncidentForwardHostContext._check_reply
    def altered(self, reply, current_stage, ordinal, reservation):
        if current_stage == stage:
            reply = dict(reply, **{field: value})
        return check(self, reply, current_stage, ordinal, reservation)
    monkeypatch.setattr(h._IncidentForwardHostContext, "_check_reply", altered)
    result, errors, stages, connection, origin = chain(monkeypatch, world)
    assert result.classification == "UNKNOWN_RETAINED", (result, errors)
    assert connection.submissions == 1 and origin.closed
    assert len(stages) == o._STAGES.index(stage)
    expected = "ORIGIN_FRAME_MALFORMED" if field == "v" else "FORWARD_HOST_COHORT_MISMATCH"
    assert any(getattr(error, "code", None) == expected for error in errors), errors


def test_parent_rejects_cohort_drift_before_bootstrap(world, monkeypatch):
    context = interval(world)
    context.phase = "EXCLUSIVE"
    context.bootstrapped = False
    current = release("UNLOADED")
    rows = list(current.roles)
    relay = rows[2]
    content = replace(relay.content, configuration_digest="9" * 64)
    from dataclasses import asdict
    rows[2] = replace(relay, content=content,
        service_generation_digest=generic._digest(generic._CONTENT_DOMAIN, asdict(content)))
    rows = tuple(rows)
    changed = replace(current, roles=rows, cohort_content_sha256=i._cohort_digest(rows))
    monkeypatch.setattr(i, "_observe_incident_release", lambda **kwargs: changed)
    commands = []
    monkeypatch.setattr(o, "_run_origin_command", lambda *args: commands.append(args))
    with pytest.raises(o.OriginIntervalError, match="ORIGIN_COHORT_DRIFT"):
        context.bootstrap_once()
    assert commands == [] and not context.bootstrap_attempted
    with pytest.raises(o.OriginIntervalError, match="ORIGIN_INTERVAL_FAILED"):
        context.bootstrap_once()


def test_generic_release_validator_still_refuses_true_mixed_roles():
    observation = release()
    i._validate_observation(observation)
    with pytest.raises(generic.ReleaseObservationError, match="RELEASE_OBSERVATION_MIXED_CONTENT"):
        generic._validate_roles(observation.roles)


@pytest.mark.parametrize("stage", o._STAGES)
def test_broker_rejects_matching_new_content_after_original_acquisition(world, monkeypatch, stage):
    """Matching fresh samples cannot replace the held original content anchor."""
    from dataclasses import asdict
    original = release()
    rows = list(original.roles)
    content = replace(rows[2].content, configuration_digest="9" * 64)
    rows[2] = replace(rows[2], content=content,
        service_generation_digest=generic._digest(generic._CONTENT_DOMAIN, asdict(content)))
    rows = tuple(rows)
    changed = replace(original, roles=rows, cohort_content_sha256=i._cohort_digest(rows))
    i._validate_observation(changed)
    check = h._IncidentForwardHostContext._check_reply
    def altered(self, reply, current_stage, ordinal, reservation):
        if current_stage != stage:
            return check(self, reply, current_stage, ordinal, reservation)
        # Only the broker-side native observation leaf changes. The real
        # checker receives a matching new digest but must retain the old anchor.
        native = SimpleNamespace(_observe_incident_release=lambda **kw: changed,
            _validate_observation=i._validate_observation, _PURPOSE=i._PURPOSE)
        with monkeypatch.context() as local:
            local.setattr(h, "incident_release", native)
            return check(self, dict(reply, cohort_content_sha256=changed.cohort_content_sha256),
                         current_stage, ordinal, reservation)
    monkeypatch.setattr(h._IncidentForwardHostContext, "_check_reply", altered)
    result, errors, stages, connection, _ = chain(monkeypatch, world)
    assert result.classification == "UNKNOWN_RETAINED" and connection.submissions == 1
    assert len(stages) == o._STAGES.index(stage)
    assert any(getattr(error, "code", None) == "FORWARD_HOST_COHORT_MISMATCH" for error in errors)


def test_incident_consumer_refuses_generic_observation_type(world, monkeypatch):
    observation = release()
    old = generic._ReleaseObservation(observation.boot_id, observation.roles, "a" * 64, observation.freshness)
    monkeypatch.setattr(i, "_observe_incident_release", lambda **kwargs: old)
    context = interval(world)
    with pytest.raises(generic.ReleaseObservationError, match="INCIDENT_OBSERVATION_PURPOSE_REFUSED"):
        o._parent_observation(context, "precheck", 0, context._budget())
