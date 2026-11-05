"""Durable external observation gates: exact CI, exact-head review, service health.

The whole path runs against the real Runtime, the real COO cycle and the real
supervisor prompt.  Only the network is a deterministic fake: no credential, no
mutation, no provider call and no production service is ever contacted.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest

from control_plane import coo_external_observation as external
from control_plane import coo_observation as observation
from control_plane.coo_external_observation import (
    ComposedObservationHost,
    ExternalObservationHost,
)
from control_plane.executive_coo_cycle import CooCycle
from control_plane.executive_operator_supervisor import ExecutiveOperatorSupervisor
from control_plane.executive_orchestration_result import PLAN_SCHEMA_V7
from control_plane.executive_runtime import (
    JobStatus, ObservationUnavailable, Runtime, StateConflict,
)
from control_plane.executive_supervisor import ExecutiveSupervisor
from ops.fabric_launch import finite_watch, observe
from test_executive_operator_supervisor import (
    _PromptSource, _seed_dispatchable_operator_planner,
)
from test_planner_producer_binding import _VersionedAdapter

CLOCK = 1_800_000_000_000
DEADLINE = CLOCK + 600_000
HEAD = "a" * 40
OTHER_HEAD = "b" * 40
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
RUN_ID = 41987375801


def ci_source(*, head=HEAD, runs=((RUN_ID, 1),)):
    return {
        "kind": "github_ci",
        "repository": REPOSITORY,
        "pull_request": 2066,
        "expected_head_sha": head,
        "selected_runs": [{"run_id": run_id, "run_attempt": attempt}
                          for run_id, attempt in runs],
    }


def review_source(*, head=HEAD, review_id=900, state="APPROVED", commit=HEAD,
                  login="reviewer"):
    return {
        "kind": "github_review",
        "repository": REPOSITORY,
        "pull_request": 2066,
        "expected_head_sha": head,
        "baseline": {"review_id": review_id, "state": state, "commit": commit,
                     "login": login},
    }


def health_source(*, service="studio-read", baseline="READY", expected="READY"):
    return {"kind": "service_health", "service": service,
            "baseline_state": baseline, "expected_state": expected}


def gate(source, *, deadline=DEADLINE, max_samples=3, interval=0, timeout=5_000,
         calls=32, response_bytes=262_144):
    return {
        "schema_version": observation.EXTERNAL_GATE_SCHEMA,
        "source": source,
        "deadline_at_ms": deadline,
        "max_samples": max_samples,
        "min_interval_ms": interval,
        "sample_timeout_ms": timeout,
        "max_api_calls": calls,
        "max_response_bytes": response_bytes,
    }


def ci_facts(*, head=HEAD, status="completed", conclusion="success",
             run_id=RUN_ID, attempt=1):
    return {"head_sha": head,
            "runs": [{"run_id": run_id, "run_attempt": attempt, "status": status,
                      "conclusion": conclusion if status == "completed" else None, "head_sha": head}]}


def review_facts(*, head=HEAD, records=()):
    return {"head_sha": head, "reviews": list(records)}


class _FakeNetwork:
    """A deterministic fake network.  It never touches a socket."""

    def __init__(self, facts=(), *, error=None):
        self.facts = list(facts)
        self.error = error
        self.calls = []

    def __call__(self, source, *, timeout_ms, max_api_calls, max_response_bytes):
        self.calls.append({"source": source, "timeout_ms": timeout_ms,
                           "max_api_calls": max_api_calls,
                           "max_response_bytes": max_response_bytes})
        if self.error is not None:
            raise self.error
        index = min(len(self.calls) - 1, len(self.facts) - 1)
        payload = self.facts[index] if self.facts else {}
        return {"facts": payload, "api_calls": 1, "response_bytes": 64}


class _ExternalPlanAdapter(_VersionedAdapter):
    """Extend the inert native producer with V7's versioned external gate."""

    def __init__(self, runtime, loader, version, *, gates, review_indices=()):
        super().__init__(runtime, loader, version)
        self.gates = list(gates)
        self.review_indices = frozenset(review_indices)

    def _canonical_result(self, turn):
        raw = super()._canonical_result(turn)
        if self.returned_version != PLAN_SCHEMA_V7:
            return raw
        envelope = json.loads(raw)
        body = envelope["role_result"]
        template = body["steps"][0]
        steps = []
        for index, spec in enumerate(self.gates):
            step = json.loads(json.dumps(template))
            step["ordinal"] = index
            step["step_id"] = f"step-{index + 1}"
            step["prerequisite_step_ids"] = []
            step["placement"] = {"provider_realm": "codex", "quota_class": "codex-coo"}
            step["observation_gate"] = spec
            step["review_required"] = index in self.review_indices
            steps.append(step)
        body["steps"] = steps
        return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


def _prepared(tmp_path, *, gates, reader, services=frozenset({"studio-read"}),
              admit=True, review_indices=()):
    clock = [CLOCK]
    runtime, root, planner = _seed_dispatchable_operator_planner(
        tmp_path, clock=lambda: clock[0], plan_schema_version=PLAN_SCHEMA_V7,
        routing_capacity=True)

    def factory(_attempt, _requested, loader, recovery):
        assert recovery is False
        return _ExternalPlanAdapter(runtime, loader, PLAN_SCHEMA_V7,
                                    gates=gates, review_indices=review_indices)

    supervisor = ExecutiveOperatorSupervisor(
        runtime, claimed_adapter_factory=factory, prompt_source=_PromptSource(),
        plan_schema_version=PLAN_SCHEMA_V7)
    dispatch = asyncio.run(supervisor.start_cycle_job(
        planner.job_id,
        command_id=f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"))
    assert dispatch.outcome == "TERMINAL"
    command = f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}"
    host = ComposedObservationHost(
        timer=observation.TimerObservationHost("test-timer"),
        external=ExternalObservationHost(binding_ref="test-external", reader=reader,
                                         services=services))
    members = (runtime.jobs.admit_cycle_plan(root.job_id, command_id=command,
                                             observation_host=host) if admit else [])
    assert len(members) == (sum(spec is None for spec in gates) if admit else 0)
    return SimpleNamespace(runtime=runtime, root=root, planner=planner, dispatch=dispatch,
                           clock=clock, host=host, command=command, path=tmp_path / "runtime", members=members)


def _cycle(case, dispatcher=None):
    return CooCycle(case.runtime, observation_host=case.host,
                    dispatcher=dispatcher or (
                        lambda job_id, command_id:
                        case.runtime.attempts.dispatch_cycle_job(job_id, command_id=command_id)))


def _counts(runtime):
    with runtime.store.read() as connection:
        return tuple(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                     for table in ("jobs", "attempts", "events"))


def _events(case, event_type):
    return [event for event in case.runtime.events.list_events(job_id=case.root.job_id)
            if event.event_type == event_type]


def _create_work(case, manifest=None, step_id="step-1"):
    manifest = manifest or case.runtime.jobs.project_cycle_work_dependency_manifest(
        case.root.job_id, step_id)
    command = (f"coo-cycle:{case.root.job_id}:create-work:{step_id}:"
               f"{manifest['dependency_manifest_digest']}")
    return case.runtime.jobs.create_cycle_work(case.root.job_id, step_id,
                                                dependency_manifest=manifest,
                                                command_id=command,
                                                observation_host=case.host)


# --- the admitted exact-CI gate through restart, work and the real prompt ---

def test_exact_ci_gate_restart_material_record_one_work_and_real_prompt(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)

    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "MATERIAL" and first["created"] is True
    assert network.calls and network.calls[0]["source"]["kind"] == "github_ci"
    # The bounded reader seam was given the reserved budget, not a free hand.
    assert network.calls[0]["max_api_calls"] >= 1
    assert network.calls[0]["max_response_bytes"] >= 1
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 1
    assert len(_events(case, observation.EVENT_TYPE)) == 1
    record = first["record"]
    assert record["disposition"] == "MATERIAL"
    assert record["snapshot"]["runs"][0]["conclusion"] == "success"
    assert record["reservation_command_id"].endswith(":reserve:1")

    # A restart keeps the counters, the selected identity and the record.
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    replay = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=None)
    assert replay["created"] is False and replay["record"] == record
    assert replay["event_id"] == first["event_id"]
    assert len(_events(case, observation.EVENT_TYPE)) == 1

    manifest = case.runtime.jobs.project_cycle_work_dependency_manifest(
        case.root.job_id, "step-1")
    assert manifest["observation"]["evidence_digest"] == record["evidence_digest"]
    work = _create_work(case, manifest)
    # The same reservation and the same manifest never mint a second Job.
    assert _create_work(case, manifest).job_id == work.job_id
    assert len([job for job in case.runtime.jobs.list_jobs()
                if job.plan_step_id == "step-1"]) == 1

    outcome = _cycle(case).run_once(case.root.job_id)
    assert outcome.action == "DISPATCHED" and outcome.selected_job_id == work.job_id
    current = case.runtime.jobs.get_job(work.job_id)
    attempt = case.runtime.attempts.get_attempt(current.current_attempt_id)
    value = case.runtime.jobs.read_cycle_observation_input(work.job_id, attempt.attempt_id)
    assert value["evidence"] == record
    assert value["observation"]["event_id"] == first["event_id"]
    supervisor = ExecutiveSupervisor(case.runtime, SimpleNamespace(inspector=object()))
    prompt = supervisor._prompt(current, attempt)
    assert observation.INPUT_SCHEMA in prompt
    assert record["evidence_digest"] in prompt
    assert '"conclusion": "success"' in prompt


def test_pending_then_later_completion_is_the_only_way_the_gate_opens(tmp_path):
    network = _FakeNetwork([ci_facts(status="in_progress", conclusion=None),
                             ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "PENDING" and first["created"] is True
    with pytest.raises(StateConflict, match="not satisfied"):
        _create_work(case)
    second = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert second["disposition"] == "MATERIAL"
    assert second["record"]["sample_index"] == 2
    assert second["record"]["previous_snapshot_digest"] == first["record"]["snapshot_digest"]
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 2


@pytest.mark.parametrize("facts", [
    ci_facts(head=OTHER_HEAD),
    ci_facts(run_id=RUN_ID + 1),
    ci_facts(attempt=2),
])
def test_wrong_head_run_or_attempt_never_satisfies_the_gate(tmp_path, facts):
    network = _FakeNetwork([facts])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "STALE" and result["created"] is True
    with pytest.raises(StateConflict, match="not satisfied"):
        _create_work(case)


def test_review_dismissal_of_the_same_id_is_visible(tmp_path):
    baseline = review_source()
    dismissed = review_facts(records=[
        {"id": 900, "state": "DISMISSED", "commit": HEAD, "login": "reviewer"}])
    network = _FakeNetwork([dismissed])
    case = _prepared(tmp_path, gates=[gate(baseline)], reader=network)
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "MATERIAL"
    assert result["record"]["snapshot"]["changed"] == [
        {"id": 900, "state": "DISMISSED", "commit": HEAD, "login": "reviewer"}]


def test_unchanged_review_is_not_material_and_a_new_formal_review_is(tmp_path):
    unchanged = review_facts(records=[
        {"id": 900, "state": "APPROVED", "commit": HEAD, "login": "reviewer"}])
    network = _FakeNetwork([unchanged])
    case = _prepared(tmp_path, gates=[gate(review_source())], reader=network)
    assert case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)["disposition"] == "PENDING"

    fresh = review_facts(records=[
        {"id": 900, "state": "APPROVED", "commit": HEAD, "login": "reviewer"},
        {"id": 901, "state": "CHANGES_REQUESTED", "commit": HEAD, "login": "other"}])
    network = _FakeNetwork([fresh])
    case = _prepared(tmp_path / "fresh", gates=[gate(review_source())], reader=network)
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "MATERIAL"
    assert [row["id"] for row in result["record"]["snapshot"]["changed"]] == [901]


def test_nonaffirmative_health_is_not_material_and_affirmative_change_is(tmp_path):
    network = _FakeNetwork([{"state": "UNAVAILABLE"}])
    case = _prepared(tmp_path, gates=[gate(health_source())], reader=network)
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "UNAVAILABLE"
    with pytest.raises(StateConflict, match="not satisfied"):
        _create_work(case)

    network = _FakeNetwork([{"state": "DEGRADED"}])
    case = _prepared(tmp_path / "degraded", gates=[gate(health_source())], reader=network)
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "MATERIAL"
    assert result["record"]["snapshot"]["observed_state"] == "DEGRADED"


def test_explicit_auth_refusal_terminates_the_watch_action(tmp_path):
    network = _FakeNetwork([{"state": "AUTH_REQUIRED"}])
    case = _prepared(tmp_path, gates=[gate(health_source())], reader=network)
    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "DENIED"
    calls = len(network.calls)
    # The refusal terminates this watch action; it is never retried.
    for _ in range(3):
        again = case.runtime.jobs.advance_cycle_observation(
            case.root.job_id, "step-1", observation_host=case.host)
        assert again["disposition"] == "DENIED" and again["created"] is False
    assert len(network.calls) == calls
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 1


def test_cancelled_root_never_satisfies_the_gate(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    case.runtime.jobs.cancel_job(case.root.job_id)
    before = _counts(case.runtime)
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "CANCELLED" and result["created"] is False
    assert _counts(case.runtime) == before
    assert not network.calls


def test_total_deadline_expires_without_evidence(tmp_path):
    network = _FakeNetwork([ci_facts(status="in_progress", conclusion=None)])
    case = _prepared(tmp_path, gates=[gate(ci_source(), deadline=CLOCK + 10_000,
                                            max_samples=10)], reader=network)
    case.clock[0] += 20_000
    result = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert result["disposition"] == "EXPIRED" and result["created"] is False
    with pytest.raises(StateConflict, match="not satisfied"):
        _create_work(case)


def test_budget_exhaustion_stops_sampling(tmp_path):
    network = _FakeNetwork([ci_facts(status="in_progress", conclusion=None)])
    case = _prepared(tmp_path, gates=[gate(ci_source(), max_samples=2, calls=6)],
                     reader=network)
    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "PENDING"
    second = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert second["disposition"] == "PENDING"
    calls = len(network.calls)
    third = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert third["disposition"] == "BUDGET_EXHAUSTED" and third["created"] is False
    assert len(network.calls) == calls


def test_interrupted_reservation_is_reconciled_and_never_reissued(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source(), max_samples=3)], reader=network)
    # Simulate a process loss between the reservation and its committed result.
    with case.runtime.store.transaction() as connection:
        observation_admission = next(
            event.payload for event in case.runtime.events.list_events(
                job_id=case.root.job_id) if event.event_type == "COO_PLAN_ADMITTED")
        spec = observation_admission["steps"][0]["observation"]["spec"]
        gate_digest = observation_admission["steps"][0]["observation"]["gate_digest"]
        reservation = observation.make_reservation(
            observation_admission["steps"][0]["observation"], sample_index=1,
            source_kind=spec["source"]["kind"],
            source_digest=external.source_digest(spec["source"]),
            reserved_at_ms=CLOCK, deadline_at_ms=DEADLINE, reserved_api_calls=3,
            reserved_response_bytes=65_536, sample_timeout_ms=5_000)
        case.runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=case.root.job_id,
            event_type=observation.RESERVATION_EVENT_TYPE, actor="coo",
            job_id=case.root.job_id, attempt_id=observation_admission["plan_attempt_id"],
            payload=reservation,
            command_id=f"coo-observation:{gate_digest}:reserve:1", timestamp_ms=CLOCK)

    # Still inside the reserved window: the sample is in flight, not reissued.
    in_flight = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert in_flight["disposition"] == "UNRESOLVED" and in_flight["created"] is False
    assert not network.calls

    case.clock[0] += 10_000
    reconciled = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert reconciled["disposition"] == "UNRESOLVED" and reconciled["created"] is False
    assert reconciled["command_id"].endswith(":reserve:1")
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 1
    assert not _events(case, observation.EVENT_TYPE)
    assert not network.calls


def test_commit_response_loss_replays_the_exact_committed_evidence(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "MATERIAL"
    # The committed record is the exact canonical evidence on every replay.
    for _ in range(3):
        again = case.runtime.jobs.advance_cycle_observation(
            case.root.job_id, "step-1", observation_host=case.host)
        assert again["record"] == first["record"]
        assert again["event_id"] == first["event_id"]
    assert len(_events(case, observation.EVENT_TYPE)) == 1


def test_at_most_one_new_sample_per_bounded_cycle_and_no_sleep(tmp_path):
    network = _FakeNetwork([ci_facts(status="in_progress", conclusion=None)])
    case = _prepared(tmp_path, gates=[gate(ci_source(), interval=0)], reader=network)
    for _ in range(3):
        before = case.clock[0]
        outcome = _cycle(case).run_once(case.root.job_id)
        assert outcome.action == "NO_ACTION"
        assert outcome.receipt["reason"] == "observation_pending"
        assert case.clock[0] == before  # no sleep, no model call during the wait
    assert len(network.calls) == 3
    assert len(_events(case, observation.RESERVATION_EVENT_TYPE)) == 3


def test_an_in_flight_sample_does_not_block_another_gate_tick(tmp_path):
    network = _FakeNetwork([ci_facts(run_id=RUN_ID + 1, status="in_progress", conclusion=None)])
    case = _prepared(tmp_path, gates=[gate(ci_source()), gate(ci_source(runs=((RUN_ID + 1, 1),)))],
                     reader=network)
    with case.runtime.store.transaction() as connection:
        admitted = next(event.payload for event in case.runtime.events.list_events(
            job_id=case.root.job_id) if event.event_type == "COO_PLAN_ADMITTED")
        first = admitted["steps"][0]["observation"]
        reservation = observation.make_reservation(
            first, sample_index=1, source_kind="github_ci",
            source_digest=external.source_digest(first["spec"]["source"]),
            reserved_at_ms=CLOCK, deadline_at_ms=DEADLINE, reserved_api_calls=3,
            reserved_response_bytes=65_536, sample_timeout_ms=5_000)
        case.runtime.store.append_event(
            connection, aggregate_type="job", aggregate_id=case.root.job_id,
            event_type=observation.RESERVATION_EVENT_TYPE, actor="coo",
            job_id=case.root.job_id, attempt_id=admitted["plan_attempt_id"],
            payload=reservation,
            command_id=observation.reservation_command_id(first, 1), timestamp_ms=CLOCK)
    outcome = _cycle(case).run_once(case.root.job_id)
    # The first gate is in flight; the other gate still got its bounded tick.
    assert outcome.action == "NO_ACTION"
    assert len(network.calls) == 1


def test_material_evidence_satisfies_only_its_own_reserved_plan_leaf(tmp_path):
    network = _FakeNetwork([ci_facts(), ci_facts(run_id=RUN_ID + 1)])
    case = _prepared(tmp_path, gates=[gate(ci_source()),
                                      gate(ci_source(runs=((RUN_ID + 1, 1),)))],
                     reader=network)
    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "MATERIAL"
    other = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-2", observation_host=case.host)
    assert other["disposition"] == "MATERIAL"
    assert other["record"]["gate_digest"] != first["record"]["gate_digest"]
    assert other["record"]["plan_step_id"] == "step-2"
    # Each leaf keeps its own evidence; neither opens the other.
    step_one = case.runtime.jobs.project_cycle_work_dependency_manifest(
        case.root.job_id, "step-1")
    step_two = case.runtime.jobs.project_cycle_work_dependency_manifest(
        case.root.job_id, "step-2")
    assert step_one["observation"]["evidence_digest"] == first["record"]["evidence_digest"]
    assert step_two["observation"]["evidence_digest"] == other["record"]["evidence_digest"]


def test_missing_host_preserves_committed_evidence(tmp_path):
    network = _FakeNetwork([ci_facts()])
    case = _prepared(tmp_path, gates=[gate(ci_source())], reader=network)
    first = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert first["disposition"] == "MATERIAL"
    case.runtime = Runtime.at(case.path, clock=lambda: case.clock[0])
    replay = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=None)
    assert replay["record"] == first["record"]
    # A fresh effect without the trusted host is refused; the committed
    # evidence stays readable.
    network2 = _FakeNetwork([ci_facts()])
    case2 = _prepared(tmp_path / "pending", gates=[gate(ci_source())], reader=network2)
    with pytest.raises(ObservationUnavailable):
        case2.runtime.jobs.advance_cycle_observation(
            case2.root.job_id, "step-1", observation_host=None)
    assert not network2.calls


def test_service_outside_the_incumbent_allowlist_is_refused(tmp_path):
    network = _FakeNetwork([{"state": "READY"}])
    case = _prepared(tmp_path, gates=[gate(health_source(service="not-allowed"))],
                     reader=network, admit=False)
    with pytest.raises(StateConflict, match="incumbent allowlist"):
        case.runtime.jobs.admit_cycle_plan(
            case.root.job_id, command_id=case.command, observation_host=case.host)


def test_the_bounded_reader_seam_counts_calls_and_bytes(tmp_path):
    """The real reader seam, with a deterministic fake network."""

    seen = []

    def fake_gh(path, timeout):
        seen.append(path)
        if path.endswith("/pulls/2066"):
            return {"number": 2066, "base": {"repo": {"full_name": REPOSITORY}},
                    "head": {"sha": HEAD}}
        return {"id": RUN_ID, "run_attempt": 1, "status": "completed",
                "conclusion": "success", "head_sha": HEAD,
                "repository": {"full_name": REPOSITORY}}

    result = finite_watch.read_external_sample(
        ci_source(), timeout_ms=5_000, max_api_calls=8, max_response_bytes=262_144,
        gh_get=fake_gh)
    assert result["facts"]["head_sha"] == HEAD
    assert result["facts"]["runs"] == [
        {"run_id": RUN_ID, "run_attempt": 1, "status": "completed",
         "conclusion": "success"}]
    assert result["api_calls"] == 3 and result["response_bytes"] > 0
    assert len(seen) == 3

    with pytest.raises(finite_watch.SourceUnavailable):
        finite_watch.read_external_sample(
            ci_source(), timeout_ms=5_000, max_api_calls=1,
            max_response_bytes=262_144, gh_get=fake_gh)


def test_v1_to_v6_plans_and_digests_are_unchanged():
    """The published V6 timer gate and every earlier plan stay byte-identical."""

    from control_plane.executive_orchestration_result import orchestration_result_schema

    assert observation.digest(observation.gate_schema()) == (
        "ed7c7ebc36fbd24df760f452dfa52ed916e8065114f6269ace494ac78d923ecf")
    v6 = orchestration_result_schema("plan", plan_schema_version="mastermind.execution_plan/v6")
    v6_step = v6["properties"]["role_result"]["properties"]["steps"]["items"]
    assert v6_step["properties"]["observation_gate"]["anyOf"][1]["properties"][
        "source"]["properties"]["kind"] == {"const": "timer"}
    v7 = orchestration_result_schema("plan", plan_schema_version="mastermind.execution_plan/v7")
    v7_step = v7["properties"]["role_result"]["properties"]["steps"]["items"]
    kinds = v7_step["properties"]["observation_gate"]["anyOf"][1]["properties"]["source"]["anyOf"]
    assert {branch["properties"]["kind"]["const"] for branch in kinds} == {
        "timer", "github_ci", "github_review", "service_health"}
    # The V1 timer gate is still refused by the V1 validator.
    with pytest.raises(observation.ObservationError):
        observation.validate_spec({
            "schema_version": observation.GATE_SCHEMA,
            "source": {"kind": "github_ci", "repository": REPOSITORY},
            "deadline_at_ms": 2000, "max_samples": 1, "min_interval_ms": 0,
            "sample_timeout_ms": 0, "max_api_calls": 0, "max_response_bytes": 0})


def test_a_versioned_timer_gate_keeps_its_published_timer_meaning(tmp_path):
    network = _FakeNetwork([ci_facts()])
    timer_gate = {
        "schema_version": observation.EXTERNAL_GATE_SCHEMA,
        "source": {"kind": "timer", "due_at_ms": CLOCK + 1_000},
        "deadline_at_ms": CLOCK + 10_000,
        "max_samples": 1, "min_interval_ms": 0, "sample_timeout_ms": 0,
        "max_api_calls": 0, "max_response_bytes": 0,
    }
    case = _prepared(tmp_path, gates=[timer_gate], reader=network)
    pending = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert pending["disposition"] == "PENDING" and pending["created"] is False
    assert not network.calls
    case.clock[0] += 1_000
    due = case.runtime.jobs.advance_cycle_observation(
        case.root.job_id, "step-1", observation_host=case.host)
    assert due["disposition"] == "MATERIAL" and due["created"] is True
    # The published timer record and digest are unchanged.
    assert due["record"]["schema_version"] == observation.RECORD_SCHEMA
    assert due["record"]["snapshot"] == {
        "kind": "timer", "due_at_ms": CLOCK + 1_000, "observed_at_ms": CLOCK + 1_000}
    assert not network.calls


def test_the_v7_native_producer_contract_is_published_and_closed():
    from jsonschema import Draft7Validator

    from control_plane.claude_operator_helper_protocol import (
        EXECUTIVE_PLAN_CONTRACT_V7,
        native_plan_contract,
        native_plan_contract_for_version,
        native_plan_schema,
    )

    assert native_plan_contract(EXECUTIVE_PLAN_CONTRACT_V7)["name"] == "executive-plan-v7"
    assert native_plan_contract_for_version(PLAN_SCHEMA_V7)["name"] == "executive-plan-v7"
    schema = native_plan_schema(EXECUTIVE_PLAN_CONTRACT_V7)
    Draft7Validator.check_schema(schema)
    assert schema["properties"]["role_result"]["properties"]["schema_version"] == {
        "const": PLAN_SCHEMA_V7}
    step = schema["properties"]["role_result"]["properties"]["steps"]["items"]
    assert set(step["required"]) == {
        "ordinal", "step_id", "objective", "business_impact", "review_required",
        "requested_authorities", "allowed_write_paths", "validation_ids",
        "attempt_limit", "cost_class", "placement", "prerequisite_step_ids",
        "observation_gate"}


def test_unknown_gate_version_and_unknown_fields_refuse():
    with pytest.raises(observation.ObservationError):
        observation.validate_spec({
            "schema_version": "mastermind.coo_observation_gate/v3",
            "source": {"kind": "timer", "due_at_ms": 1}, "deadline_at_ms": 2000,
            "max_samples": 1, "min_interval_ms": 0, "sample_timeout_ms": 0,
            "max_api_calls": 0, "max_response_bytes": 0})
    with pytest.raises(observation.ObservationError):
        observation.validate_spec({
            "schema_version": observation.EXTERNAL_GATE_SCHEMA,
            "source": {"kind": "github_ci", "repository": REPOSITORY,
                       "pull_request": 2066, "expected_head_sha": HEAD,
                       "selected_runs": [{"run_id": 1, "run_attempt": 1}],
                       "unexpected": True},
            "deadline_at_ms": 2000, "max_samples": 1, "min_interval_ms": 0,
            "sample_timeout_ms": 1000, "max_api_calls": 4, "max_response_bytes": 1024})
    with pytest.raises(observation.ObservationError):
        observation.validate_spec({
            "schema_version": observation.EXTERNAL_GATE_SCHEMA,
            "source": {"kind": "github_ci", "repository": REPOSITORY,
                       "pull_request": 2066, "expected_head_sha": "not-a-sha",
                       "selected_runs": [{"run_id": 1, "run_attempt": 1}]},
            "deadline_at_ms": 2000, "max_samples": 1, "min_interval_ms": 0,
            "sample_timeout_ms": 1000, "max_api_calls": 4, "max_response_bytes": 1024})


def test_service_composition_keeps_the_default_flags_and_needs_the_opt_in(tmp_path):
    from control_plane.executive_service import ExecutiveControlService
    from test_executive_service import _config

    config = _config(tmp_path)
    assert config.coo_external_observations_armed is False
    service = ExecutiveControlService(config)
    assert service._observation_host is None
    with pytest.raises(ValueError, match="external observations require armed observations"):
        dataclasses.replace(config, coo_autonomy_armed=True,
                            coo_external_observations_armed=True)
    armed = dataclasses.replace(config, coo_autonomy_armed=True,
                                coo_observations_armed=True)
    plain = ExecutiveControlService(armed, autonomy_guard=lambda: None)
    assert isinstance(plain._observation_host, observation.TimerObservationHost)
    with pytest.raises(ValueError, match="external observation reader requires"):
        ExecutiveControlService(armed, autonomy_guard=lambda: None,
                                external_observation_reader=lambda *a, **k: None)
    composed = ExecutiveControlService(
        dataclasses.replace(armed, coo_external_observations_armed=True),
        autonomy_guard=lambda: None)
    assert isinstance(composed._observation_host, external.ComposedObservationHost)


def test_reader_credential_refusal_is_terminal_and_never_retried(tmp_path):
    def refused(path, timeout):
        raise finite_watch.SourceUnavailable({"code": "GH_API_FAILED", "exit_code": 4})

    with pytest.raises(finite_watch.SourceUnavailable) as caught:
        finite_watch.read_external_sample(
            ci_source(), timeout_ms=5_000, max_api_calls=8,
            max_response_bytes=262_144, gh_get=refused)
    assert caught.value.signal_payload.get("terminal") is True
    assert caught.value.signal_payload.get("code") == "GH_AUTH_REFUSED"


def test_external_state_constants_match_the_incumbent_observer():
    assert external.FORMAL_REVIEW_STATES == finite_watch.FORMAL_REVIEW_STATES
    assert external.HEALTH_STATES == finite_watch.HEALTH_STATES
    assert external.TERMINAL_HEALTH_STATES == frozenset(
        {"AUTH_REQUIRED", "DENIED"})
    assert set(observe.ENDPOINTS) >= set(external.incumbent_services())
