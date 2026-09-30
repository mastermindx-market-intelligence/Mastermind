"""Private closure validation; root transport and records are synthetic.

The initial cases isolate synthetic registry/context adapters. Later real-registry
cases prove canonical closure writes; all root transport/host identity is synthetic.
No installed root authority or physical release is attested.
"""

import copy
import dataclasses
import hashlib
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


def broker_response():
    evidence, root = records()
    return evidence["approval"], {
        "schema": c.BROKER_SCHEMA,
        "operation": "read_release_closure",
        "ok": True,
        "approval": root.approval.to_dict(),
        "result": root.result,
    }


def test_private_history_wire_has_no_renewal_token_or_public_selector(monkeypatch):
    approval, reply = broker_response()
    calls = []

    def send(payload, **kwargs):
        calls.append((payload, kwargs))
        return reply

    monkeypatch.setattr(transport, "_send_one_frame", send)
    root = c.ReleaseBrokerClient().read_release_closure(approval=approval)
    assert root.approval.to_dict() == approval
    assert len(calls) == 1
    assert calls[0] == (
        {
            "schema": c.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "approval": approval,
        },
        {
            "socket_path": transport.DEFAULT_SOCKET,
            "timeout_seconds": 15,
            "require_root_peer": True,
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
def test_private_history_rejects_protocol_drift_without_retry(monkeypatch, mutation):
    approval, reply = broker_response()
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
        c.ReleaseBrokerClient().read_release_closure(approval=approval)
    assert len(calls) == 1


def test_private_transport_loss_is_not_retried(monkeypatch):
    approval, _ = broker_response()
    calls = []

    def lost(*args, **kwargs):
        calls.append(args)
        raise TimeoutError("response absent")

    monkeypatch.setattr(transport, "_send_one_frame", lost)
    with pytest.raises(TimeoutError):
        c.ReleaseBrokerClient().read_release_closure(approval=approval)
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

    def history(*, approval):
        assert not runtime.store._read_connections
        assert not runtime.store._write_connections
        assert approval == state["evidence"]["approval"]
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

    def send(payload, **options):
        assert not runtime.store._write_connections
        assert not runtime.store._read_connections
        assert payload == {
            "schema": c.BROKER_SCHEMA,
            "operation": "read_release_closure",
            "approval": approval,
        }
        assert options == {
            "socket_path": transport.DEFAULT_SOCKET,
            "timeout_seconds": 15,
            "require_root_peer": True,
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
        assert options == {
            "socket_path": transport.DEFAULT_SOCKET,
            "timeout_seconds": 15,
            "require_root_peer": True,
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
                "admission",
            }
            assert request["arguments"] == frame.arguments
            assert request["reservation"] == reservation
            result = {
                "reservation": copy.deepcopy(reservation),
                "admission": copy.deepcopy(request["admission"]),
                "start_record": _synthetic_start(
                    approval, reservation, request["admission"]
                ),
            }
        else:
            assert operation == "read_release_closure"
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
    clone = dataclasses.replace(capability)
    lane["control"].broker.start_reserved_release(fresh_admission=clone)
    with pytest.raises(
        c.ReleaseConsumerError, match="RELEASE_FRESH_ADMISSION_REQUIRED"
    ):
        lane["control"].broker.start_reserved_release(fresh_admission=capability)
    assert len(lane["calls"]) == 2


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
