"""Private closure validation; root transport and records are synthetic.

The initial cases isolate synthetic registry/context adapters. Later real-registry
cases prove canonical closure writes; all root transport/host identity is synthetic.
No installed root authority or physical release is attested.
"""

import copy
import dataclasses
import hashlib
import json
import os

import pytest

from control_plane import executive_release_consumer as c
from control_plane import executive_release_contract as contract
from control_plane import executive_privileged_client as transport
from control_plane import executive_runtime as runtime_api
from tests.test_executive_release_contract import prestart_fixture, terminal_fixture
from control_plane import executive_release_ingress as ingress
from control_plane import executive_installed_peer as installed_peer
from tests.test_executive_release_consumer import (
    installed,
    inputs,
    approve_arguments,
    typed_history,
)
from tests.test_executive_release_contract import PRESTART_TEST_COMMON


def records(kind="terminal", state="SUCCEEDED", reason="PREPARED_TOKEN_EXPIRED"):
    approval, reservation, admission, cancellation = prestart_fixture(reason)
    _, status = terminal_fixture(state)
    evidence = {
        "approval": approval,
        "admission": admission,
        "preconditions": reservation["preconditions"],
        "root_qualification_digest": c._hash(reservation),
    }
    result = {
        "reservation": reservation,
        "terminal_status": status if kind == "terminal" else None,
        "cancellation": cancellation if kind == "cancellation" else None,
    }
    response = c._RootReleaseResponse(
        approval=contract.validate_approval_evidence(approval),
        result=result,
        capability=c._BROKER_RESPONSE_CAPABILITY,
        operation="read_release_closure",
    )
    return evidence, response


@pytest.mark.parametrize("state", ["SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"])
def test_terminal_closure_exact_join_returns_detached_validated_records(state):
    evidence, response = records(state=state)
    kind, status, reservation = c._validated_release_closure(response, evidence)
    assert kind == "terminal" and status["state"] == state
    assert c._hash(reservation) == evidence["root_qualification_digest"]
    assert "root_qualification_digest" not in status
    response.result["reservation"]["before"]["broker_binary_digest"] = "f" * 64
    assert reservation["before"]["broker_binary_digest"] != "f" * 64


@pytest.mark.parametrize(
    "reason",
    [
        "PREPARED_TOKEN_EXPIRED",
        "PRINCIPAL_EXPIRED",
        "GRANT_EXPIRED",
        "AUTHORITY_REVOKED",
        "PRECONDITIONS_CHANGED",
        "TARGET_OBSERVATION_CHANGED",
    ],
)
def test_cancellation_uses_its_separate_validator_and_original_reservation(reason):
    evidence, response = records(kind="cancellation", reason=reason)
    kind, cancellation, reservation = c._validated_release_closure(response, evidence)
    assert kind == "cancellation" and cancellation["reason"] == reason
    assert cancellation["root_qualification_digest"] == c._hash(reservation)
    assert "started_at_ms" not in cancellation


@pytest.mark.parametrize(
    "state",
    [
        "NOT_FOUND",
        "STARTED",
        "PUBLISHED",
        "BROKER_RESTART_PENDING",
        "RECOVERING",
    ],
)
def test_missing_or_nonterminal_history_cannot_close(state):
    evidence, response = records(state=state)
    expected = (
        "RELEASE_CLOSURE_UNQUALIFIED"
        if state == "NOT_FOUND"
        else "RELEASE_EFFECT_IN_PROGRESS"
    )
    with pytest.raises(c.ReleaseConsumerError, match=expected):
        c._validated_release_closure(response, evidence)


@pytest.mark.parametrize("kind", ["terminal", "cancellation"])
@pytest.mark.parametrize(
    "mutation",
    [
        "missing_reservation",
        "missing_outcome",
        "two_outcomes",
        "extra_result",
        "wrong_root_digest",
        "foreign_approval",
        "changed_preconditions",
        "changed_admission",
        "changed_target_observation",
        "changed_reservation",
        "foreign_pid",
        "foreign_capability",
        "wrong_operation",
        "extra_evidence",
        "missing_evidence",
    ],
)
def test_closure_rejects_unqualified_or_drifting_evidence(kind, mutation):
    evidence, response = records(kind)
    if mutation == "missing_reservation":
        response.result["reservation"] = None
    elif mutation == "missing_outcome":
        response.result["terminal_status"] = response.result["cancellation"] = None
    elif mutation == "two_outcomes":
        _, response.result["terminal_status"] = terminal_fixture()
        response.result["cancellation"] = prestart_fixture()[3]
    elif mutation == "extra_result":
        response.result["start"] = True
    elif mutation == "wrong_root_digest":
        evidence["root_qualification_digest"] = "f" * 64
    elif mutation == "foreign_approval":
        response.approval = copy.deepcopy(evidence["approval"])
        response.approval["owner_seal"]["mac"] = "B" * 43
    elif mutation == "changed_preconditions":
        evidence["preconditions"] = copy.deepcopy(evidence["preconditions"])
        evidence["preconditions"]["production_arming_digest"] = "f" * 64
    elif mutation == "changed_admission":
        evidence["admission"] = copy.deepcopy(evidence["admission"])
        evidence["admission"]["maintenance_sequence"] = 2
    elif mutation == "changed_target_observation":
        evidence["admission"] = copy.deepcopy(evidence["admission"])
        evidence["admission"]["target_observation_digest"] = "f" * 64
    elif mutation == "changed_reservation":
        response.result["reservation"]["prepared_token_digest"] = "f" * 64
    elif mutation == "foreign_pid":
        response.receiver_pid = os.getpid() + 1
    elif mutation == "foreign_capability":
        response._capability = object()
    elif mutation == "wrong_operation":
        response.operation = "approve_release_transition"
    elif mutation == "extra_evidence":
        evidence["force"] = True
    elif mutation == "missing_evidence":
        del evidence["root_qualification_digest"]
    with pytest.raises((c.ReleaseConsumerError, contract.ReleaseContractError)):
        c._validated_release_closure(response, evidence)


def test_terminal_before_identity_cannot_change_with_same_approval_and_admission():
    evidence, response = records()
    response.result["terminal_status"]["terminal_receipt"]["before"][
        "broker_binary_digest"
    ] = ("f" * 64)
    # This is still structurally valid terminal evidence. The reservation join
    # must independently reject the substituted physical before identity.
    contract.validate_release_terminal_status(
        response.result["terminal_status"], expected_approval=evidence["approval"]
    )
    with pytest.raises(c.ReleaseConsumerError):
        c._validated_release_closure(response, evidence)


def test_start_before_reservation_cannot_close():
    evidence, response = records()
    status = response.result["terminal_status"]
    status["started_at_ms"] = status["terminal_receipt"]["started_at_ms"] = 1999
    contract.validate_release_terminal_status(
        status, expected_approval=evidence["approval"]
    )
    with pytest.raises(c.ReleaseConsumerError):
        c._validated_release_closure(response, evidence)


def _capture_canonical_capability(control, monkeypatch):
    """Capture only the real finalizer's mint, before its broker consumes it."""
    captured = []

    class Captured(Exception):
        pass

    def capture(*, canonical_evidence):
        assert not control.runtime.store._read_connections
        assert not control.runtime.store._write_connections
        captured.append(canonical_evidence)
        raise Captured

    with monkeypatch.context() as patch:
        patch.setattr(control.broker, "read_release_closure", capture)
        with pytest.raises(Captured):
            control.finalize_unresolved_admission()
    assert len(captured) == 1
    return captured[0]


@pytest.fixture
def canonical_lane(tmp_path, monkeypatch):
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    approval, reservation, _, _, status = _seed_real_admission(runtime)
    control = c.ReleaseControlConsumer(runtime)
    capability = _capture_canonical_capability(control, monkeypatch)
    reply = {
        "schema": c.BROKER_SCHEMA,
        "operation": "read_release_closure",
        "ok": True,
        "approval": approval,
        "result": {
            "reservation": reservation,
            "terminal_status": status,
            "cancellation": None,
        },
    }
    return dict(runtime=runtime, control=control, capability=capability,
                evidence=json.loads(capability.evidence_bytes), reply=reply)


def test_private_history_wire_has_no_renewal_token_or_public_selector(
    canonical_lane, monkeypatch
):
    lane = canonical_lane
    approval, reply = lane["evidence"]["approval"], lane["reply"]
    calls = []

    def send(payload, **kwargs):
        calls.append((payload, kwargs))
        return reply

    monkeypatch.setattr(transport, "_send_one_frame", send)
    root = c.ReleaseBrokerClient().read_release_closure(
        canonical_evidence=lane["capability"])
    assert root.approval.to_dict() == approval
    assert len(calls) == 1
    endpoint = calls[0][1]["deadline_monotonic_ns"]
    assert type(endpoint) is int
    assert 0 < endpoint - c.time.monotonic_ns() <= 15_000_000_000
    assert calls[0] == (
        {
            "schema": c.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "admission_evidence": lane["evidence"],
        },
        {
            "socket_path": transport.DEFAULT_SOCKET,
            "timeout_seconds": 15,
            "require_root_peer": True,
            "deadline_monotonic_ns": endpoint,
        },
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "schema",
        "operation",
        "ok_integer",
        "extra_envelope",
        "missing_approval",
        "changed_approval",
        "extra_result",
        "missing_result_field",
        "list_result",
        "unknown_error",
        "error_extra_field",
    ],
)
def test_private_history_rejects_protocol_drift_without_retry(
    canonical_lane, monkeypatch, mutation
):
    lane = canonical_lane
    approval, reply = lane["evidence"]["approval"], lane["reply"]
    if mutation in {"schema", "operation"}:
        reply[mutation] = "other"
    elif mutation == "ok_integer":
        reply["ok"] = 1
    elif mutation == "extra_envelope":
        reply["principal"] = approval["principal_projection"]
    elif mutation == "missing_approval":
        del reply["approval"]
    elif mutation == "changed_approval":
        reply["approval"]["owner_seal"]["mac"] = "B" * 43
    elif mutation == "extra_result":
        reply["result"]["start"] = True
    elif mutation == "missing_result_field":
        del reply["result"]["cancellation"]
    elif mutation == "list_result":
        reply["result"] = []
    else:
        reply = {
            "schema": c.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "ok": False,
            "error": "RELEASE_REFUSED",
        }
        if mutation == "unknown_error":
            reply["error"] = "RETRY_NOW"
        else:
            reply["retry"] = True
    calls = []
    monkeypatch.setattr(
        transport, "_send_one_frame", lambda *a, **k: calls.append(a) or reply
    )
    with pytest.raises((c.ReleaseConsumerError, contract.ReleaseContractError)):
        c.ReleaseBrokerClient().read_release_closure(
            canonical_evidence=lane["capability"])
    with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
        c.ReleaseBrokerClient().read_release_closure(
            canonical_evidence=lane["capability"])
    assert len(calls) == 1


def test_private_transport_loss_is_not_retried(canonical_lane, monkeypatch):
    calls = []

    def lost(*args, **kwargs):
        calls.append(args)
        raise TimeoutError("response absent")

    monkeypatch.setattr(transport, "_send_one_frame", lost)
    with pytest.raises(TimeoutError):
        c.ReleaseBrokerClient().read_release_closure(
            canonical_evidence=canonical_lane["capability"])
    with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
        c.ReleaseBrokerClient().read_release_closure(
            canonical_evidence=canonical_lane["capability"])
    assert len(calls) == 1


@pytest.fixture
def finalizer(tmp_path, monkeypatch):
    """Real RuntimeStore transactions; synthetic pending registry/context API.

    The complete foundation's qualification and real closure Event semantics
    require its own integrated tests after its source is accepted.
    """
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    control = c.ReleaseControlConsumer(runtime)
    trace = []
    state = {"evidence": None, "response": None, "write_result": "exact", "race": None}
    command = "synthetic-closure-proof"

    @dataclasses.dataclass(frozen=True)
    class Context:
        _store: object
        _connection: object
        _evidence_digest: str
        _capability: object
        _record: object

    terminal_capability, cancellation_capability = object(), object()
    for name, value in {
        "TrustedReleaseClosingContext": Context,
        "TrustedReleaseCancellationContext": Context,
        "_RELEASE_CLOSING_CAPABILITY": terminal_capability,
        "_RELEASE_CANCELLATION_CAPABILITY": cancellation_capability,
    }.items():
        monkeypatch.setattr(runtime_api, name, value, raising=False)

    def read(connection):
        is_write = connection in runtime.store._write_connections
        trace.append("read-write" if is_write else "read")
        assert connection.in_transaction
        if is_write and state["race"] == "disappeared":
            return None
        evidence = copy.deepcopy(state["evidence"])
        if is_write and state["race"] == "changed":
            evidence["root_qualification_digest"] = "e" * 64
        found = runtime.store.get_event_by_command_id(command, connection=connection)
        if found is not None and state["race"] != "readback":
            return None
        return evidence

    def write(
        connection,
        *,
        trusted_context,
        approved_transition_ref,
        request_fingerprint,
        terminal_status=None,
        cancellation=None,
        reservation=None,
    ):
        assert (
            connection in runtime.store._write_connections and connection.in_transaction
        )
        assert trusted_context._store is runtime.store
        assert trusted_context._connection is connection
        purpose = "closing" if terminal_status is not None else "cancellation"
        assert trusted_context._capability is (
            terminal_capability if purpose == "closing" else cancellation_capability
        )
        assert trusted_context._evidence_digest == c._hash(
            {"purpose": purpose, "record": dict(trusted_context._record)}
        )
        with pytest.raises(TypeError):
            trusted_context._record["target_ref"] = "f" * 64
        outcome = terminal_status if terminal_status is not None else cancellation
        assert approved_transition_ref == outcome["approved_transition_ref"]
        assert request_fingerprint == outcome["request_fingerprint"]
        if cancellation is not None:
            assert c._hash(reservation) == cancellation["root_qualification_digest"]
        trace.append("write-" + purpose)
        runtime.store.append_event(
            connection,
            aggregate_type="synthetic_closure",
            aggregate_id="one",
            event_type="synthetic_closure",
            command_id=command,
            payload={"context": dict(trusted_context._record)},
        )
        return outcome if state["write_result"] == "exact" else {}

    def history(*, canonical_evidence):
        assert not runtime.store._read_connections
        assert not runtime.store._write_connections
        assert type(canonical_evidence) is c._CanonicalUnresolvedReleaseEvidence
        assert _bytes(canonical_evidence._consume()) == _bytes(state["evidence"])
        trace.append("broker")
        if isinstance(state["response"], BaseException):
            raise state["response"]
        return state["response"]

    registry = runtime.release_maintenance
    monkeypatch.setattr(registry, "read_unresolved_admission", read, raising=False)
    monkeypatch.setattr(registry, "record_terminal", write, raising=False)
    monkeypatch.setattr(registry, "record_cancellation", write, raising=False)
    monkeypatch.setattr(control.broker, "read_release_closure", history)
    return runtime, control, state, trace


@pytest.mark.parametrize("kind", ["terminal", "cancellation"])
def test_finalizer_queries_outside_sql_then_closes_once_on_rejoined_snapshot(
    finalizer, kind
):
    runtime, control, state, trace = finalizer
    state["evidence"], state["response"] = records(kind)
    assert control.finalize_unresolved_admission() is None
    assert trace == [
        "read",
        "broker",
        "read-write",
        "write-" + ("closing" if kind == "terminal" else "cancellation"),
        "read",
    ]
    assert len(runtime.events.list_events()) == 1
    assert control.finalize_unresolved_admission() is None
    assert trace[-1] == "read" and trace.count("broker") == 1
    assert len(runtime.events.list_events()) == 1


def test_finalizer_genuine_absence_does_not_query_root_or_write(finalizer):
    runtime, control, state, trace = finalizer
    assert control.finalize_unresolved_admission() is None
    assert trace == ["read"] and runtime.events.list_events() == []


@pytest.mark.parametrize("race", ["changed", "disappeared"])
@pytest.mark.parametrize("kind", ["terminal", "cancellation"])
def test_finalizer_rejects_snapshot_races_before_any_event(finalizer, race, kind):
    runtime, control, state, trace = finalizer
    state["evidence"], state["response"] = records(kind)
    state["race"] = race
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_CLOSURE_ADMISSION_CHANGED"
    ):
        control.finalize_unresolved_admission()
    assert trace == ["read", "broker", "read-write"]
    assert runtime.events.list_events() == []


@pytest.mark.parametrize("kind", ["terminal", "cancellation"])
def test_finalizer_wrong_write_readback_rolls_back_the_owner_transaction(
    finalizer, kind
):
    runtime, control, state, trace = finalizer
    state["evidence"], state["response"] = records(kind)
    state["write_result"] = "wrong"
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_CLOSURE_READBACK_UNKNOWN"
    ):
        control.finalize_unresolved_admission()
    assert trace.count("broker") == 1
    assert runtime.events.list_events() == []


@pytest.mark.parametrize("kind", ["terminal", "cancellation"])
def test_finalizer_post_commit_uncertainty_is_not_replayed(finalizer, kind):
    runtime, control, state, trace = finalizer
    state["evidence"], state["response"] = records(kind)
    state["race"] = "readback"
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_CLOSURE_READBACK_UNKNOWN"
    ):
        control.finalize_unresolved_admission()
    assert trace.count("broker") == 1
    assert len([step for step in trace if step.startswith("write-")]) == 1
    assert len(runtime.events.list_events()) == 1


@pytest.mark.parametrize("state_name", ["NOT_FOUND", "STARTED", "RECOVERING"])
def test_finalizer_unknown_history_never_enters_a_write_transaction(
    finalizer, state_name
):
    runtime, control, state, trace = finalizer
    state["evidence"], state["response"] = records(state=state_name)
    with pytest.raises(c.ReleaseConsumerError):
        control.finalize_unresolved_admission()
    assert trace == ["read", "broker"]
    assert runtime.events.list_events() == []


def test_finalizer_transport_loss_never_retries_or_writes(finalizer):
    runtime, control, state, trace = finalizer
    state["evidence"], _ = records()
    state["response"] = TimeoutError("root response missing")
    with pytest.raises(TimeoutError):
        control.finalize_unresolved_admission()
    assert trace == ["read", "broker"]
    assert runtime.events.list_events() == []


def test_finalizer_refuses_a_partial_runtime_composition(tmp_path, monkeypatch):
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    monkeypatch.setattr(
        runtime.release_maintenance, "record_cancellation", None, raising=False
    )
    control = c.ReleaseControlConsumer(runtime)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_RUNTIME_CLOSURE_UNAVAILABLE"
    ):
        control.finalize_unresolved_admission()
    assert runtime.events.list_events() == []


# Real protected Runtime registry composition. Test mints seed admission only.
def _bytes(value):
    return contract.canonical_release_bytes(value)


def _seed_real_admission(
    runtime, *, state="SUCCEEDED", reason="PREPARED_TOKEN_EXPIRED"
):
    store, registry = runtime.store, runtime.release_maintenance
    store.now_ms = lambda: 2000
    approval, reservation, _, cancellation = prestart_fixture(reason)
    with store.transaction() as connection:
        registry.record_approval(
            connection,
            sealed_approval=approval,
            trusted_context=runtime_api._release_context_for_test(
                store, connection, sealed_approval=approval
            ),
        )
        context = registry._release_admission_context_for_test(
            store,
            connection,
            approval=approval,
            preconditions=reservation["preconditions"],
            target_observation_digest=reservation["target_observation_digest"],
            prepared_deadline_ms=reservation["prepared_payload"]["expires_at_ms"],
            root_qualification_digest=c._hash(reservation),
        )
        admission = registry.record_admission(
            connection,
            sealed_approval=approval,
            request_fingerprint=contract.request_fingerprint_for(approval),
            preconditions=reservation["preconditions"],
            target_observation_digest=reservation["target_observation_digest"],
            trusted_context=context,
        )
    cancellation["admission_digest"] = c._hash(admission)
    _, status = terminal_fixture(state)
    if state != "NOT_FOUND":
        status["admission"] = admission.to_dict()
        status["admission_digest"] = c._hash(admission)
        if "terminal_receipt" in status:
            status["terminal_receipt"]["admission_digest"] = c._hash(admission)
    # Historical closure must not renew approval/token/principal deadlines.
    store.now_ms = lambda: 400_000
    return approval, reservation, admission, cancellation, status


def _wire(
    monkeypatch, runtime, approval, reservation, *, status=None, cancellation=None
):
    calls = []
    result = {
        "reservation": reservation,
        "terminal_status": status,
        "cancellation": cancellation,
    }
    with runtime.store.read() as connection:
        evidence = json.loads(_bytes(
            runtime.release_maintenance.read_unresolved_admission(connection)))

    def send(payload, **options):
        assert not runtime.store._write_connections
        assert not runtime.store._read_connections
        assert payload == {
            "schema": c.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "admission_evidence": evidence,
        }
        endpoint = options["deadline_monotonic_ns"]
        assert type(endpoint) is int
        assert 0 < endpoint - c.time.monotonic_ns() <= 15_000_000_000
        assert options == {
            "socket_path": transport.DEFAULT_SOCKET,
            "timeout_seconds": 15,
            "require_root_peer": True,
            "deadline_monotonic_ns": endpoint,
        }
        calls.append(copy.deepcopy(payload))
        return {
            "schema": c.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "ok": True,
            "approval": copy.deepcopy(approval),
            "result": copy.deepcopy(result),
        }

    monkeypatch.setattr(transport, "_send_one_frame", send)
    return calls, result


def _events(runtime):
    with runtime.store.read() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                "SELECT sequence,event_type,payload_json FROM main.events ORDER BY sequence"
            )
        ]


def _assert_test_mints_unused(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("production closure called a Runtime test mint")

    monkeypatch.setattr(runtime_api, "_release_context_for_test", forbidden)
    for name in (
        "_release_admission_context_for_test",
        "_release_closing_context_for_test",
        "_release_cancellation_context_for_test",
    ):
        monkeypatch.setattr(runtime_api.ReleaseMaintenanceRegistry, name, forbidden)


@pytest.mark.parametrize(
    "outcome",
    [
        "SUCCEEDED",
        "ROLLED_BACK",
        "FAILED_NOT_APPLIED",
        "PREPARED_TOKEN_EXPIRED",
        "PRINCIPAL_EXPIRED",
        "GRANT_EXPIRED",
        "AUTHORITY_REVOKED",
        "PRECONDITIONS_CHANGED",
        "TARGET_OBSERVATION_CHANGED",
    ],
)
def test_real_registry_closure_once_then_reopen_has_no_new_effect(
    tmp_path, monkeypatch, outcome
):
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    terminal = outcome in {"SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"}
    approval, reservation, admission, cancellation, status = _seed_real_admission(
        runtime,
        state=outcome if terminal else "SUCCEEDED",
        reason="PREPARED_TOKEN_EXPIRED" if terminal else outcome,
    )
    original = _events(runtime)
    calls, _ = _wire(
        monkeypatch,
        runtime,
        approval,
        reservation,
        status=status if terminal else None,
        cancellation=None if terminal else cancellation,
    )
    _assert_test_mints_unused(monkeypatch)
    control = c.ReleaseControlConsumer(runtime)
    assert control.finalize_unresolved_admission() is None
    closed = _events(runtime)
    assert len(closed) == len(original) + 1
    assert closed[:-1] == original
    assert closed[-1][1] == (
        "EXECUTIVE_RELEASE_CLOSED"
        if terminal
        else "EXECUTIVE_RELEASE_PRESTART_CANCELLED"
    )
    with runtime.store.read() as connection:
        assert runtime.release_maintenance.read_unresolved_admission(connection) is None
        evidence = runtime.release_maintenance.read_admission_evidence(
            connection,
            approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=contract.request_fingerprint_for(approval),
        )
        assert _bytes(evidence["admission"]) == _bytes(admission)
        assert evidence["root_qualification_digest"] == c._hash(reservation)
    assert control.finalize_unresolved_admission() is None
    reopened = runtime_api.Runtime.from_store(
        runtime_api.RuntimeStore(runtime.store.root)
    )
    assert c.ReleaseControlConsumer(reopened).finalize_unresolved_admission() is None
    assert _events(reopened) == closed
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["terminal", "cancellation"])
def test_real_closure_releases_existing_claim_fence_only_after_qualified_write(
    tmp_path, monkeypatch, kind
):
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    runtime.store.now_ms = lambda: 1000
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("bounded closure source proof")
    approval, reservation, _, cancellation, status = _seed_real_admission(runtime)
    calls, _ = _wire(
        monkeypatch,
        runtime,
        approval,
        reservation,
        status=status if kind == "terminal" else None,
        cancellation=cancellation if kind == "cancellation" else None,
    )
    with pytest.raises(runtime_api.StateConflict, match="release admission"):
        runtime.attempts.claim_job(job.job_id)
    assert runtime.attempts.list_attempts(job.job_id) == []
    c.ReleaseControlConsumer(runtime).finalize_unresolved_admission()
    lease = runtime.attempts.claim_job(job.job_id)
    assert lease is not None
    assert len(runtime.attempts.list_attempts(job.job_id)) == 1
    assert len(calls) == 1


@pytest.mark.parametrize(
    "state",
    ["NOT_FOUND", "STARTED", "PUBLISHED", "BROKER_RESTART_PENDING", "RECOVERING"],
)
def test_real_unresolved_history_cannot_write_closure(tmp_path, monkeypatch, state):
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    approval, reservation, _, _, status = _seed_real_admission(runtime, state=state)
    calls, _ = _wire(monkeypatch, runtime, approval, reservation, status=status)
    original = _events(runtime)
    with pytest.raises(c.ReleaseConsumerError):
        c.ReleaseControlConsumer(runtime).finalize_unresolved_admission()
    assert _events(runtime) == original
    with runtime.store.read() as connection:
        assert (
            runtime.release_maintenance.read_unresolved_admission(connection)
            is not None
        )
    assert len(calls) == 1


def test_real_empty_registry_never_queries_root(tmp_path, monkeypatch):
    runtime = runtime_api.Runtime.at(tmp_path / "runtime")

    def forbidden(*args, **kwargs):
        pytest.fail("genuine absence contacted root")

    monkeypatch.setattr(transport, "_send_one_frame", forbidden)
    c.ReleaseControlConsumer(runtime).finalize_unresolved_admission()
    assert _events(runtime) == []


# R8.2: real owner approval/token and Runtime admission; synthetic root journal.


def _synthetic_start(approval, reservation, admission):
    before = reservation["before"]
    effect = approval["normalized_requested_effect"]
    return {
        "schema": "mastermind.executive_release_actuator_journal/v2",
        "state": "STARTED",
        "operation_key": approval["operation_key"],
        "request_fingerprint": reservation["request_fingerprint"],
        "approval_evidence_digest": c._hash(approval),
        "normalized_requested_effect_digest": c._hash(effect),
        "expected_source_and_precondition_digest": c._hash(
            reservation["preconditions"]
        ),
        "action_target_digest": reservation["action_target_digest"],
        "owner_installation_id": approval["owner_installation_id"],
        "target_ref": approval["target_ref"],
        "before_release_commit": before["release_commit"],
        "before_release_tree": before["release_tree"],
        "before_installed_manifest_digest": before["installed_manifest_digest"],
        "before_configuration_digest": before["configuration_digest"],
        "target_release_commit": effect["to_release_commit"],
        "target_release_tree": effect["to_release_tree"],
        "boot_id": reservation["preconditions"]["boot_id"],
        "preconditions": copy.deepcopy(reservation["preconditions"]),
        "admission": copy.deepcopy(admission),
        "actuator_generation": 1,
        "journal_generation": 1,
        "started_at_ms": reservation["reserved_at_ms"],
        "root_qualification_digest": c._hash(reservation),
    }


@pytest.fixture
def fresh_lane(installed, monkeypatch):
    mono = [2_000_000_000]
    monkeypatch.setattr(c.time, "monotonic_ns", lambda: mono[0])
    call, runtime = installed["call"], installed["runtime"]
    runtime.store.now_ms = lambda: installed["now"][0]
    args = approve_arguments(installed)
    approved = call("approve_release_transition", args)
    approval = installed["control"]._read(args["operation_key"])
    prepared = call(
        "prepare_release_transition",
        {
            "operation_key": args["operation_key"],
            "approved_transition_ref": approved["approved_transition_ref"],
        },
    )
    snapshot = installed["states"][0]
    payload = snapshot.codec.decode_prepared(
        prepared["prepared_token"],
        now_ms=installed["now"][0],
        monotonic_ns=mono[0],
        boot_id=snapshot.boot_id,
    )
    status = typed_history(approval, "SUCCEEDED", snapshot.preconditions)
    reservation = {key: copy.deepcopy(status[key]) for key in PRESTART_TEST_COMMON}
    reservation.update(
        schema="mastermind.executive_release_prestart_reservation/v1",
        reservation_generation=1,
        reserved_at_ms=installed["now"][0],
        reserved_monotonic_ns=mono[0],
        preconditions=status["preconditions"],
        expected_precondition_digest=c._hash(status["preconditions"]),
        prepared_payload=payload.to_dict(),
        prepared_token_digest=hashlib.sha256(
            prepared["prepared_token"].encode()
        ).hexdigest(),
        before=status["terminal_receipt"]["before"],
        target_observation_digest=status["admission"]["target_observation_digest"],
    )
    contract.validate_release_prestart_reservation(
        reservation, expected_approval=approval
    )
    frame = ingress.validate_frame(
        ingress.project_frame(
            "commit_prepared_release_transition",
            {
                "operation_key": args["operation_key"],
                "prepared_token": prepared["prepared_token"],
            },
            principal=installed["principal"],
        )
    )
    monkeypatch.setattr(
        installed_peer, "_observe_real_boot_id", lambda: snapshot.boot_id
    )
    calls = []
    knobs = {"after_reserve": None, "reply_mutation": None, "loss": None}

    def send(request, **options):
        assert (
            not runtime.store._read_connections and not runtime.store._write_connections
        )
        endpoint = options["deadline_monotonic_ns"]
        assert type(endpoint) is int
        assert 0 < endpoint - c.time.monotonic_ns() <= 15_000_000_000
        assert options == {
            "socket_path": transport.DEFAULT_SOCKET,
            "timeout_seconds": 15,
            "require_root_peer": True,
            "deadline_monotonic_ns": endpoint,
        }
        calls.append(copy.deepcopy(request))
        operation = request["operation"]
        if knobs["loss"] == operation:
            raise TimeoutError("synthetic lost root response")
        if operation == "reserve_release_prestart":
            assert set(request) == {
                "schema",
                "operation",
                "arguments",
                "principal",
                "approval",
            }
            assert request["arguments"] == frame.arguments
            if knobs["after_reserve"] is not None:
                knobs["after_reserve"]()
            result = {"reservation": copy.deepcopy(reservation)}
        elif operation == "start_reserved_release":
            assert set(request) == {
                "schema",
                "operation",
                "arguments",
                "principal",
                "approval",
                "reservation",
                "admission_evidence",
            }
            assert request["arguments"] == frame.arguments
            assert request["reservation"] == reservation
            with runtime.store.read() as connection:
                canonical = runtime.release_maintenance.read_unresolved_admission(connection)
                assert _bytes(request["admission_evidence"]) == _bytes(canonical)
            result = {
                "reservation": copy.deepcopy(reservation),
                "admission": copy.deepcopy(request["admission_evidence"]["admission"]),
                "start_record": _synthetic_start(
                    approval, reservation, request["admission_evidence"]["admission"]
                ),
            }
        else:
            assert operation == "read_release_closure"
            assert set(request) == {"schema", "operation", "admission_evidence"}
            with runtime.store.read() as connection:
                canonical = runtime.release_maintenance.read_unresolved_admission(connection)
                assert _bytes(request["admission_evidence"]) == _bytes(canonical)
            result = {
                "reservation": copy.deepcopy(reservation),
                "terminal_status": None,
                "cancellation": None,
            }
        reply = {
            "schema": c.BROKER_SCHEMA,
            "operation": operation,
            "ok": True,
            "approval": approval.to_dict(),
            "result": result,
        }
        if knobs["reply_mutation"] is not None:
            knobs["reply_mutation"](reply)
        return reply

    monkeypatch.setattr(transport, "_send_one_frame", send)
    return dict(
        installed=installed,
        runtime=runtime,
        control=installed["control"],
        approval=approval,
        reservation=reservation,
        frame=frame,
        calls=calls,
        knobs=knobs,
        mono=mono,
    )


def _fresh(lane):
    return lane["control"]._reserve_and_admit(
        frame=lane["frame"], connection=lane["installed"]["socket"]
    )


def _admission_count(lane):
    return sum(
        row[1] == "EXECUTIVE_RELEASE_ADMITTED" for row in _events(lane["runtime"])
    )


def test_real_new_admission_commits_before_one_start_and_persists_no_token(
    fresh_lane, monkeypatch
):
    lane = fresh_lane
    _assert_test_mints_unused(monkeypatch)
    capability = _fresh(lane)
    assert type(capability) is c._FreshReleaseAdmission
    assert [r["operation"] for r in lane["calls"]] == ["reserve_release_prestart"]
    assert _admission_count(lane) == 1
    token = lane["frame"].arguments["prepared_token"]
    assert token not in repr(capability) and token not in repr(capability.root_response)
    assert token not in str(_events(lane["runtime"]))
    start = lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert (
        type(start) is c._RootReleaseStartResponse
        and start.start_record["state"] == "STARTED"
    )
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert len(lane["calls"]) == 2 and _admission_count(lane) == 1
    with lane["runtime"].store.read() as connection:
        assert (
            lane["runtime"].release_maintenance.read_unresolved_admission(connection)
            is not None
        )
    assert lane["installed"]["root_broker"]._executor.calls == []


def test_public_commit_stays_disarmed_even_with_complete_source(fresh_lane):
    lane = fresh_lane
    result = lane["installed"]["call"](
        "commit_prepared_release_transition", lane["frame"].arguments
    )
    assert result["error"]["code"] == "RELEASE_COMMIT_DISARMED"
    assert lane["calls"] == [] and _admission_count(lane) == 0


def test_historical_admission_never_reserves_or_mints_again(fresh_lane):
    lane = fresh_lane
    _fresh(lane)
    with pytest.raises(c.ReleaseConsumerError, match="RELEASE_CLOSURE_UNQUALIFIED"):
        _fresh(lane)
    assert [r["operation"] for r in lane["calls"]] == [
        "reserve_release_prestart",
        "read_release_closure",
    ]
    assert _admission_count(lane) == 1


@pytest.mark.parametrize(
    "operation", ["reserve_release_prestart", "start_reserved_release"]
)
def test_private_loss_never_retries_or_restores_fresh_capability(fresh_lane, operation):
    lane = fresh_lane
    if operation == "reserve_release_prestart":
        lane["knobs"]["loss"] = operation
        with pytest.raises(TimeoutError):
            _fresh(lane)
        assert len(lane["calls"]) == 1 and _admission_count(lane) == 0
    else:
        capability = _fresh(lane)
        lane["knobs"]["loss"] = operation
        with pytest.raises(TimeoutError):
            lane["control"].broker.start_reserved_release(fresh_admission=capability)
        with pytest.raises(c.ReleaseConsumerError):
            lane["control"].broker.start_reserved_release(fresh_admission=capability)
        assert len(lane["calls"]) == 2 and _admission_count(lane) == 1


@pytest.mark.parametrize("drift", ["wall", "monotonic", "principal"])
def test_expiry_after_admission_consumes_capability_without_start(fresh_lane, drift):
    lane = fresh_lane
    capability = _fresh(lane)
    if drift == "wall":
        lane["installed"]["now"][0] = lane["reservation"]["prepared_payload"][
            "expires_at_ms"
        ]
    elif drift == "monotonic":
        lane["mono"][0] = lane["reservation"]["prepared_payload"][
            "expires_monotonic_ns"
        ]
    else:
        lane["installed"]["now"][0] = lane["frame"].principal.expires_at * 1000
    with pytest.raises(c.ReleaseConsumerError):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    lane["installed"]["now"][0] = lane["reservation"]["reserved_at_ms"]
    lane["mono"][0] = lane["reservation"]["reserved_monotonic_ns"]
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert len(lane["calls"]) == 1


def test_admission_race_inside_owner_transaction_never_mints_fresh(fresh_lane):
    lane = fresh_lane
    runtime, approval, reservation = (
        lane["runtime"],
        lane["approval"],
        lane["reservation"],
    )

    def race():
        registry = runtime.release_maintenance
        with runtime.store.transaction() as sql:
            context = registry._release_admission_context_for_test(
                runtime.store,
                sql,
                approval=approval,
                preconditions=reservation["preconditions"],
                target_observation_digest=reservation["target_observation_digest"],
                prepared_deadline_ms=reservation["prepared_payload"]["expires_at_ms"],
                root_qualification_digest=c._hash(reservation),
            )
            registry.record_admission(
                sql,
                sealed_approval=approval,
                request_fingerprint=contract.request_fingerprint_for(approval),
                preconditions=reservation["preconditions"],
                target_observation_digest=reservation["target_observation_digest"],
                trusted_context=context,
            )

    lane["knobs"]["after_reserve"] = race
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_ADMISSION_NO_LONGER_FRESH"
    ):
        _fresh(lane)
    assert _admission_count(lane) == 1 and len(lane["calls"]) == 1


def test_bad_writer_return_rolls_back_real_admission(fresh_lane, monkeypatch):
    lane = fresh_lane
    registry = lane["runtime"].release_maintenance
    original = registry.record_admission

    def wrong(*args, **kwargs):
        original(*args, **kwargs)
        return {}

    monkeypatch.setattr(registry, "record_admission", wrong)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_ADMISSION_READBACK_UNKNOWN"
    ):
        _fresh(lane)
    assert _admission_count(lane) == 0 and len(lane["calls"]) == 1


def test_fresh_readback_uncertainty_preserves_admission_without_start(
    fresh_lane, monkeypatch
):
    lane = fresh_lane
    registry = lane["runtime"].release_maintenance
    original = registry.read_admission_evidence

    def drift(*args, **kwargs):
        result = dict(original(*args, **kwargs))
        result["root_qualification_digest"] = "f" * 64
        return result

    monkeypatch.setattr(registry, "read_admission_evidence", drift)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_ADMISSION_READBACK_UNKNOWN"
    ):
        _fresh(lane)
    assert _admission_count(lane) == 1 and len(lane["calls"]) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "token",
        "boot",
        "expired",
        "regressed_monotonic",
        "extra_result",
        "integer_ok",
        "foreign_approval",
    ],
)
def test_reservation_mismatch_refuses_before_runtime_write(
    fresh_lane, monkeypatch, mutation
):
    lane = fresh_lane
    if mutation == "boot":
        monkeypatch.setattr(
            installed_peer,
            "_observe_real_boot_id",
            lambda: "33333333-3333-4333-8333-333333333333",
        )
    elif mutation == "expired":
        lane["knobs"]["after_reserve"] = lambda: lane["installed"]["now"].__setitem__(
            0, lane["reservation"]["prepared_payload"]["expires_at_ms"]
        )
    elif mutation == "regressed_monotonic":
        lane["knobs"]["after_reserve"] = lambda: lane["mono"].__setitem__(0, 1)
    else:

        def change(reply):
            if mutation == "token":
                reply["result"]["reservation"]["prepared_token_digest"] = "f" * 64
            elif mutation == "extra_result":
                reply["result"]["start"] = True
            elif mutation == "integer_ok":
                reply["ok"] = 1
            else:
                reply["approval"]["owner_seal"]["mac"] = "B" * 43

        lane["knobs"]["reply_mutation"] = change
    with pytest.raises((c.ReleaseConsumerError, contract.ReleaseContractError)):
        _fresh(lane)
    assert _admission_count(lane) == 0 and len(lane["calls"]) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "root_digest",
        "admission",
        "reservation",
        "state",
        "generation",
        "started_at",
        "extra",
        "operation",
    ],
)
def test_start_response_drift_never_restores_consumed_authority(fresh_lane, mutation):
    lane = fresh_lane
    capability = _fresh(lane)

    def change(reply):
        start = reply["result"]["start_record"]
        if mutation == "root_digest":
            start["root_qualification_digest"] = "f" * 64
        elif mutation == "admission":
            start["admission"]["maintenance_sequence"] += 1
        elif mutation == "reservation":
            reply["result"]["reservation"]["prepared_token_digest"] = "f" * 64
        elif mutation == "state":
            start["state"] = "PUBLISHED"
        elif mutation == "generation":
            start["journal_generation"] = 2
        elif mutation == "started_at":
            start["started_at_ms"] = 1
        elif mutation == "extra":
            reply["result"]["private"] = True
        else:
            reply["operation"] = "reserve_release_prestart"

    lane["knobs"]["reply_mutation"] = change
    with pytest.raises((ValueError, RuntimeError)):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert _admission_count(lane) == 1 and len(lane["calls"]) == 2


def test_copy_serialization_and_dataclass_replace_cannot_duplicate_start(fresh_lane):
    import pickle

    lane = fresh_lane
    capability = _fresh(lane)
    for value in (capability, capability.root_response):
        for duplicate in (copy.copy, copy.deepcopy, pickle.dumps):
            with pytest.raises(TypeError):
                duplicate(value)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        dataclasses.replace(capability)
    lane["control"].broker.start_reserved_release(fresh_admission=capability)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert len(lane["calls"]) == 2


@pytest.mark.parametrize("after_loss", [False, True])
@pytest.mark.parametrize("replacement", [[], False, None, {}, True])
def test_replacement_cannot_reset_consumption_after_start(
    fresh_lane, after_loss, replacement
):
    import threading

    lane = fresh_lane
    capability = _fresh(lane)
    if after_loss:
        lane["knobs"]["loss"] = "start_reserved_release"
        with pytest.raises(TimeoutError):
            lane["control"].broker.start_reserved_release(fresh_admission=capability)
        lane["knobs"]["loss"] = None
    else:
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    for fields in (
        {"_consumed": replacement},
        {"_consumed": replacement, "_lock": threading.Lock()},
        {"_lock": threading.Lock()},
    ):
        with pytest.raises(
            c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
        ):
            dataclasses.replace(capability, **fields)
    with pytest.raises(dataclasses.FrozenInstanceError):
        capability._consumed = False
    assert capability._consumed is True
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert _admission_count(lane) == 1 and len(lane["calls"]) == 2


def test_concurrent_consumers_can_send_start_only_once(fresh_lane):
    from concurrent.futures import ThreadPoolExecutor

    lane = fresh_lane
    capability = _fresh(lane)

    def start():
        try:
            return lane["control"].broker.start_reserved_release(
                fresh_admission=capability
            )
        except c.ReleaseConsumerError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: start(), range(2)))
    assert sum(type(value) is c._RootReleaseStartResponse for value in outcomes) == 1
    assert outcomes.count("RELEASE_FRESH_ADMISSION_REQUIRED") == 1
    assert len(lane["calls"]) == 2


@pytest.mark.parametrize("first", ["before", "success", "loss", "preflight"])
def test_constructor_and_state_hooks_cannot_issue_or_restore_start(fresh_lane, first):
    lane = fresh_lane
    capability = _fresh(lane)
    if first == "success":
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    elif first == "loss":
        lane["knobs"]["loss"] = "start_reserved_release"
        with pytest.raises(TimeoutError):
            lane["control"].broker.start_reserved_release(fresh_admission=capability)
        lane["knobs"]["loss"] = None
    elif first == "preflight":
        original = lane["mono"][0]
        lane["mono"][0] = lane["reservation"]["prepared_payload"][
            "expires_monotonic_ns"
        ]
        with pytest.raises(c.ReleaseConsumerError):
            lane["control"].broker.start_reserved_release(fresh_admission=capability)
        lane["mono"][0] = original
    used = capability._consumed
    args = (
        capability.root_response,
        capability.admission_evidence,
        capability._capability,
    )
    for construct in (c._FreshReleaseAdmission, capability.__init__):
        with pytest.raises(
            c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
        ):
            construct(*args)
    for value in (capability, capability.root_response):
        with pytest.raises(TypeError, match="process-local"):
            value.__getstate__()
        with pytest.raises(TypeError, match="process-local"):
            value.__setstate__([None] * 7)
    assert capability._consumed is used
    if first == "before":
        result = lane["control"].broker.start_reserved_release(
            fresh_admission=capability
        )
        with pytest.raises(TypeError, match="process-local"):
            result.__getstate__()
        with pytest.raises(TypeError, match="process-local"):
            result.__setstate__([None] * 6)
    else:
        with pytest.raises(
            c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
        ):
            lane["control"].broker.start_reserved_release(fresh_admission=capability)
    starts = sum(row["operation"] == "start_reserved_release" for row in lane["calls"])
    assert starts == (0 if first == "preflight" else 1)
    assert _admission_count(lane) == 1


def test_dataclass_replace_cannot_rebind_fresh_capability(fresh_lane):
    from types import MappingProxyType

    lane = fresh_lane
    capability = _fresh(lane)
    for fields in (
        {"root_response": dataclasses.replace(capability.root_response)},
        {"admission_evidence": MappingProxyType(dict(capability.admission_evidence))},
        {"receiver_pid": os.getpid() + 1},
        {"_capability": object()},
    ):
        with pytest.raises(
            c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
        ):
            dataclasses.replace(capability, **fields)
    assert len(lane["calls"]) == 1
    assert (
        lane["control"]
        .broker.start_reserved_release(fresh_admission=capability)
        .start_record["state"]
        == "STARTED"
    )


def test_active_attempt_prevents_admission_after_reserve(fresh_lane):
    lane = fresh_lane
    runtime = lane["runtime"]
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("bounded source proof already active")
    assert runtime.attempts.claim_job(job.job_id) is not None
    with pytest.raises(runtime_api.ReleaseMaintenanceError, match="ACTIVE_ATTEMPT"):
        _fresh(lane)
    assert _admission_count(lane) == 0 and len(lane["calls"]) == 1


@pytest.mark.parametrize("first", ["before", "success", "loss", "preflight"])
def test_canonical_capability_cannot_be_copied_constructed_or_restored(
    canonical_lane, monkeypatch, first
):
    import pickle
    import threading

    lane, calls = canonical_lane, []
    capability = lane["capability"]

    def send(*args, **kwargs):
        calls.append(args)
        if first == "loss":
            raise TimeoutError("lost closure response")
        return lane["reply"]

    monkeypatch.setattr(transport, "_send_one_frame", send)
    read = lambda: lane["control"].broker.read_release_closure(
        canonical_evidence=capability)
    if first == "success":
        read()
    elif first == "loss":
        with pytest.raises(TimeoutError):
            read()
    elif first == "preflight":
        raw = capability.evidence_bytes
        object.__setattr__(capability, "evidence_bytes", raw + b" ")
        with pytest.raises(c.ReleaseConsumerError):
            read()
        object.__setattr__(capability, "evidence_bytes", raw)
    consumed = capability._consumed
    for duplicate in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="process-local"):
            duplicate(capability)
    for construct in (c._CanonicalUnresolvedReleaseEvidence, capability.__init__):
        with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
            construct(capability.evidence_bytes, capability.evidence_digest,
                      capability._capability)
    for fields in ({}, {"_consumed": False}, {"_lock": threading.Lock()},
                   {"evidence_bytes": b"{}"}, {"receiver_pid": os.getpid() + 1}):
        with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
            dataclasses.replace(capability, **fields)
    with pytest.raises(TypeError, match="process-local"):
        capability.__getstate__()
    with pytest.raises(TypeError, match="process-local"):
        capability.__setstate__([None] * 6)
    with pytest.raises(dataclasses.FrozenInstanceError):
        capability._consumed = False
    assert capability._consumed is consumed
    if first == "before":
        read()
    with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
        read()
    assert len(calls) == (0 if first == "preflight" else 1)


@pytest.mark.parametrize("replacement", [None, {}, b"{}", "approval", object()])
def test_closure_client_requires_exact_private_capability(monkeypatch, replacement):
    calls = []
    monkeypatch.setattr(transport, "_send_one_frame", lambda *a, **k: calls.append(a))
    with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
        c.ReleaseBrokerClient().read_release_closure(canonical_evidence=replacement)
    assert calls == []


@pytest.mark.parametrize("mutation", ["pid", "capability", "digest", "bytes_type", "bytes"])
def test_canonical_capability_tampering_refuses_before_transport(
    canonical_lane, monkeypatch, mutation
):
    capability, calls = canonical_lane["capability"], []
    monkeypatch.setattr(transport, "_send_one_frame", lambda *a, **k: calls.append(a))
    field, value = {
        "pid": ("receiver_pid", os.getpid() + 1),
        "capability": ("_capability", object()),
        "digest": ("evidence_digest", "f" * 64),
        "bytes_type": ("evidence_bytes", bytearray(capability.evidence_bytes)),
        "bytes": ("evidence_bytes", capability.evidence_bytes + b" "),
    }[mutation]
    object.__setattr__(capability, field, value)
    with pytest.raises(c.ReleaseConsumerError, match="CANONICAL_EVIDENCE_REQUIRED"):
        c.ReleaseBrokerClient().read_release_closure(canonical_evidence=capability)
    assert calls == []


@pytest.mark.parametrize("field", ["approval", "admission", "preconditions", "root_qualification_digest"])
@pytest.mark.parametrize("mutation", ["missing", "wrong_type"])
def test_canonical_capability_revalidates_every_field_before_transport(
    canonical_lane, monkeypatch, field, mutation
):
    lane, calls = canonical_lane, []
    evidence, capability = lane["evidence"], lane["capability"]
    if mutation == "missing":
        del evidence[field]
    else:
        evidence[field] = []
    raw = _bytes(evidence)
    object.__setattr__(capability, "evidence_bytes", raw)
    object.__setattr__(capability, "evidence_digest", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(transport, "_send_one_frame", lambda *a, **k: calls.append(a))
    with pytest.raises((c.ReleaseConsumerError, contract.ReleaseContractError)):
        lane["control"].broker.read_release_closure(canonical_evidence=capability)
    assert calls == [] and capability._consumed is True


@pytest.mark.parametrize("mutation", ["extra_field", "noncanonical", "invalid_digest"])
def test_canonical_capability_rejects_extra_or_noncanonical_evidence(
    canonical_lane, monkeypatch, mutation
):
    lane, calls = canonical_lane, []
    evidence, capability = lane["evidence"], lane["capability"]
    if mutation == "extra_field":
        evidence["retry"] = True
    elif mutation == "invalid_digest":
        evidence["root_qualification_digest"] = "F" * 64
    raw = _bytes(evidence) + (b" " if mutation == "noncanonical" else b"")
    object.__setattr__(capability, "evidence_bytes", raw)
    object.__setattr__(capability, "evidence_digest", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(transport, "_send_one_frame", lambda *a, **k: calls.append(a))
    with pytest.raises((c.ReleaseConsumerError, contract.ReleaseContractError)):
        lane["control"].broker.read_release_closure(canonical_evidence=capability)
    assert calls == [] and capability._consumed is True


def test_concurrent_closure_consumers_send_only_once(canonical_lane, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    lane, calls = canonical_lane, []
    monkeypatch.setattr(transport, "_send_one_frame",
                        lambda *a, **k: calls.append(a) or lane["reply"])

    def read(_):
        try:
            return lane["control"].broker.read_release_closure(
                canonical_evidence=lane["capability"])
        except c.ReleaseConsumerError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(read, range(2)))
    assert sum(type(value) is c._RootReleaseResponse for value in results) == 1
    assert results.count("RELEASE_CANONICAL_EVIDENCE_REQUIRED") == 1
    assert len(calls) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires actual fork inheritance")
@pytest.mark.parametrize("lane_name", ["fresh_lane", "canonical_lane"])
def test_fork_rejects_before_waiting_on_inherited_capability_lock(request, lane_name):
    import select
    import signal

    lane = request.getfixturevalue(lane_name)
    capability = _fresh(lane) if lane_name == "fresh_lane" else lane["capability"]
    expected = ("RELEASE_FRESH_ADMISSION_REQUIRED" if lane_name == "fresh_lane"
                else "RELEASE_CANONICAL_EVIDENCE_REQUIRED")
    reader, writer = os.pipe()
    capability._lock.acquire()
    child = None
    try:
        child = os.fork()
        if child == 0:
            os.close(reader)
            try:
                capability._consume()
                result = "UNEXPECTED_ACCEPTANCE"
            except c.ReleaseConsumerError as exc:
                result = exc.code
            except BaseException:
                result = "UNEXPECTED_EXCEPTION"
            os.write(writer, result.encode("ascii"))
            os._exit(0)
        os.close(writer)
        assert select.select([reader], [], [], 3)[0], "fork waited on inherited lock"
        assert os.read(reader, 256).decode("ascii") == expected
        assert capability._consumed is False
    finally:
        capability._lock.release()
        os.close(reader)
        if child is None:
            os.close(writer)
        elif child > 0:
            observed, _ = os.waitpid(child, os.WNOHANG)
            if observed == 0:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)


def test_lost_closure_keeps_runtime_evidence_and_reopen_closes_once(
    canonical_lane, monkeypatch
):
    lane, calls = canonical_lane, []
    runtime = lane["runtime"]
    before = _events(runtime)

    def lost(*args, **kwargs):
        calls.append(args)
        raise TimeoutError("lost closure response")

    monkeypatch.setattr(transport, "_send_one_frame", lost)
    with pytest.raises(TimeoutError):
        lane["control"].finalize_unresolved_admission()
    assert len(calls) == 1 and _events(runtime) == before
    with runtime.store.read() as connection:
        pending = runtime.release_maintenance.read_unresolved_admission(connection)
        assert _bytes(pending) == _bytes(lane["evidence"])
    reopened = runtime_api.Runtime.at(runtime.store.root)
    reply = lane["reply"]
    calls, _ = _wire(monkeypatch, reopened, reply["approval"],
                     reply["result"]["reservation"],
                     status=reply["result"]["terminal_status"])
    control = c.ReleaseControlConsumer(reopened)
    assert control.finalize_unresolved_admission() is None
    assert len(_events(reopened)) == len(before) + 1 and len(calls) == 1
    assert control.finalize_unresolved_admission() is None
    assert len(_events(reopened)) == len(before) + 1 and len(calls) == 1


def test_private_frame_limits_include_ascii_expansion_and_newline():
    from control_plane import executive_privileged_broker as broker

    assert broker._MAX_REQUEST_BYTES == 64 * 1024
    assert transport._MAX_RESPONSE_BYTES == 128 * 1024
    assert contract._MAX_BYTES == 16 * 1024
    # This is a transport boundary probe, not a valid release record. Unicode
    # expands to six ASCII bytes in the real shared transport's encoder.
    payload = {"x": "\u00e9" * 10_000 + "a" * 5_527}
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    assert len(encoded) == broker._MAX_REQUEST_BYTES
    assert c._bounded_private_payload(payload) is payload
    payload["x"] += "a"
    with pytest.raises(c.ReleaseConsumerError, match="REQUEST_TOO_LARGE"):
        c._bounded_private_payload(payload)
    assert len(_bytes({"x": "a" * (16 * 1024 - 8)})) == 16 * 1024
    with pytest.raises(contract.ReleaseContractError):
        _bytes({"x": "a" * (16 * 1024 - 7)})


@pytest.mark.parametrize("fault", ["read_error", "foreign_snapshot", "malformed_event", "orphan_admission"])
def test_failed_canonical_read_never_reaches_broker(tmp_path, monkeypatch, fault):
    import sqlite3

    runtime = runtime_api.Runtime.at(tmp_path / "runtime")
    _seed_real_admission(runtime)
    control = c.ReleaseControlConsumer(runtime)
    calls = []
    monkeypatch.setattr(control.broker, "read_release_closure",
                        lambda **kwargs: calls.append(kwargs))
    if fault in {"malformed_event", "orphan_admission"}:
        # Fault injection is confined to this disposable test database.
        with sqlite3.connect(runtime.store.path) as raw:
            if fault == "malformed_event":
                raw.execute("DROP TRIGGER events_are_immutable_update")
                raw.execute("UPDATE events SET payload_json='{}' "
                            "WHERE event_type='EXECUTIVE_RELEASE_ADMITTED'")
            else:
                raw.execute("DROP TRIGGER events_are_immutable_delete")
                raw.execute("DELETE FROM events WHERE event_type='EXECUTIVE_RELEASE_APPROVED'")
    before = _events(runtime)
    with monkeypatch.context() as patch:
        if fault == "read_error":
            def failed_read(connection):
                raise sqlite3.OperationalError("test read failed")
            patch.setattr(runtime.release_maintenance, "read_unresolved_admission", failed_read)
        elif fault == "foreign_snapshot":
            foreign = runtime_api.Runtime.at(tmp_path / "foreign")
            patch.setattr(runtime.store, "read", foreign.store.read)
        with pytest.raises((runtime_api.ReleaseMaintenanceError,
                            contract.ReleaseContractError, runtime_api.PersistenceError)):
            control.finalize_unresolved_admission()
    assert calls == [] and _events(runtime) == before
    assert not runtime.store._read_connections and not runtime.store._write_connections


def test_complete_start_and_closure_frames_fit_unchanged_bounds(fresh_lane):
    lane = fresh_lane
    capability = _fresh(lane)
    lane["control"].broker.start_reserved_release(fresh_admission=capability)
    with pytest.raises(c.ReleaseConsumerError, match="CLOSURE_UNQUALIFIED"):
        lane["control"].finalize_unresolved_admission()
    start, closure = lane["calls"][-2:]
    assert start["operation"] == "start_reserved_release"
    assert closure["operation"] == "read_release_closure"
    assert start["admission_evidence"] == closure["admission_evidence"]
    assert len(_bytes(start["admission_evidence"])) <= 16 * 1024
    for payload in (start, closure):
        encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        assert len(encoded) <= 64 * 1024
