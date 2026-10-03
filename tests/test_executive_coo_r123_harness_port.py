"""Real public port bridge proof; typed fixtures are not native actor acceptance."""

import dataclasses
import json

import pytest

from control_plane.executive_operator_harness_port import ExecutiveOperatorHarnessPort
from control_plane.executive_runtime import AttemptLease, StateConflict
from tests.test_executive_coo_r119_later_turn import (
    _begin_turn_intents,
    _charge_events,
    _charge_rows,
    _domain_attempt,
    _happy_args,
    _seeded_domain,
)
from tests.test_executive_coo_r121_role_body_projection import _inventory


def _public_port(tmp_path, monkeypatch):
    runtime, root, domain, attempt_id = _seeded_domain(
        tmp_path, monkeypatch, genuine_enabled=True,
    )
    generation, operation, fence, token, digest = _happy_args(
        runtime, root.job_id, attempt_id,
    )
    attempt = runtime.attempts.get_attempt(attempt_id)
    assert attempt is not None and attempt.fence_generation == fence
    port = ExecutiveOperatorHarnessPort(runtime, AttemptLease(attempt, token))
    return runtime, root, domain, attempt_id, generation, operation, digest, port


def test_public_port_delegates_current_identity_and_reserves_one_final_unit(
    tmp_path, monkeypatch,
):
    runtime, root, domain, attempt, generation, operation, digest, port = _public_port(
        tmp_path, monkeypatch,
    )
    before = _inventory(runtime)
    identity_before = tuple(_domain_attempt(runtime, attempt))
    counts = (
        len(_charge_rows(runtime, root.job_id)),
        len(_charge_events(runtime, domain.job_id)),
        len(_begin_turn_intents(runtime, attempt)),
    )
    actual_reserve = runtime.operator_harness.reserve_domain_consumption_turn
    calls = []

    def observed_reserve(**kwargs):
        calls.append(kwargs)
        return actual_reserve(**kwargs)

    monkeypatch.setattr(runtime.operator_harness, "reserve_domain_consumption_turn", observed_reserve)
    turn = port.begin_operator_domain_consumption_turn(
        attempt, generation, operation, expected_consumption_projection_digest=digest,
    )
    assert calls == [{
        "generation": generation,
        "operation_id": operation,
        "fence_generation": port.fence_generation,
        "lease_token": port.lease_token,
        "expected_consumption_projection_digest": digest,
    }]
    assert turn.attempt_id == attempt
    assert turn.session_epoch_id == generation.session_epoch_id
    assert turn.process_generation_id == generation.process_generation_id
    assert tuple(_domain_attempt(runtime, attempt)) == identity_before
    after = _inventory(runtime)
    assert after["jobs"] == before["jobs"]
    assert after["attempts"] == before["attempts"]
    rows = _charge_rows(runtime, root.job_id)
    events = _charge_events(runtime, domain.job_id)
    intents = _begin_turn_intents(runtime, attempt)
    assert (len(rows), len(events), len(intents)) == tuple(x + 1 for x in counts)
    row = rows[-1]
    payload = json.loads(events[-1]["payload_json"])
    intent = json.loads(intents[-1]["payload_json"])
    for material in (row, payload):
        assert material["root_job_id"] == root.job_id
        assert material["operation_id"] == operation.command_id
        assert material["effect_class"] == "FINAL"
        assert material["turn_id"] == turn.turn_id
    assert row["job_id"] == domain.job_id
    assert row["attempt_id"] == attempt
    assert row["worker_id"] == generation.worker_id
    assert payload["domain_job_id"] == domain.job_id
    assert payload["domain_attempt_id"] == attempt
    assert payload["session_epoch_id"] == generation.session_epoch_id
    assert payload["process_generation_id"] == generation.process_generation_id
    assert row["event_id"] == events[-1]["event_id"]
    assert payload["consumption_projection_digest"] == digest
    assert intent["turn_id"] == turn.turn_id
    assert intent["provider_session_id"] == _domain_attempt(runtime, attempt)["provider_session_id"]
    assert intents[-1]["command_id"] == operation.command_id
    assert port.begin_operator_domain_consumption_turn(
        attempt, generation, operation, expected_consumption_projection_digest=digest,
    ) == turn
    assert _inventory(runtime) == after


def test_wrong_bound_attempt_refuses_before_generation_lookup(tmp_path, monkeypatch):
    runtime, _, _, attempt, generation, operation, digest, port = _public_port(tmp_path, monkeypatch)
    before = _inventory(runtime)

    def forbidden_lookup(*args, **kwargs):
        pytest.fail("wrong bound Attempt reached generation lookup")

    monkeypatch.setattr(runtime.operator_harness, "generation_refs", forbidden_lookup)
    with pytest.raises(StateConflict, match="different AttemptLease"):
        port.begin_operator_domain_consumption_turn(
            attempt + "-foreign", generation, operation,
            expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


@pytest.mark.parametrize("foreign", ["stored-generation", "epoch-attempt"])
def test_foreign_generation_or_epoch_refuses_before_reservation(tmp_path, monkeypatch, foreign):
    runtime, _, _, attempt, generation, operation, digest, port = _public_port(tmp_path, monkeypatch)
    before = _inventory(runtime)
    epoch, stored = runtime.operator_harness.generation_refs(generation.process_generation_id)
    if foreign == "stored-generation":
        stored = dataclasses.replace(stored, generation_number=stored.generation_number + 1)
    else:
        epoch = dataclasses.replace(epoch, attempt_id=attempt + "-foreign")
    monkeypatch.setattr(runtime.operator_harness, "generation_refs", lambda _id: (epoch, stored))

    def forbidden_reserve(**kwargs):
        pytest.fail("foreign identity reached FINAL reservation")

    monkeypatch.setattr(runtime.operator_harness, "reserve_domain_consumption_turn", forbidden_reserve)
    with pytest.raises(StateConflict, match="another identity"):
        port.begin_operator_domain_consumption_turn(
            attempt, generation, operation, expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


@pytest.mark.parametrize("stale", ["fence", "token", "digest", "malformed-digest"])
def test_real_runtime_refuses_stale_lease_or_projection_without_effects(tmp_path, monkeypatch, stale):
    runtime, _, _, attempt, generation, operation, digest, port = _public_port(tmp_path, monkeypatch)
    before = _inventory(runtime)
    if stale == "fence":
        port = ExecutiveOperatorHarnessPort(runtime, AttemptLease(
            dataclasses.replace(port.lease.attempt, fence_generation=port.fence_generation + 1),
            port.lease_token,
        ))
    elif stale == "token":
        port = ExecutiveOperatorHarnessPort(runtime, AttemptLease(port.lease.attempt, "foreign-token"))
    else:
        digest = "0" * 64 if stale == "digest" else "not-a-projection-digest"
    with pytest.raises(StateConflict):
        port.begin_operator_domain_consumption_turn(
            attempt, generation, operation, expected_consumption_projection_digest=digest,
        )
    assert _inventory(runtime) == before


def test_constructor_performs_no_runtime_io(tmp_path, monkeypatch):
    runtime, _, _, _, _, _, _, port = _public_port(tmp_path, monkeypatch)
    before = _inventory(runtime)

    def forbidden_io(*args, **kwargs):
        pytest.fail("constructor performed Runtime IO")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.store, "read", forbidden_io)
        patch.setattr(runtime.operator_harness, "generation_refs", forbidden_io)
        rebuilt = ExecutiveOperatorHarnessPort(runtime, port.lease)
        assert rebuilt.runtime is runtime and rebuilt.lease is port.lease
    assert _inventory(runtime) == before
