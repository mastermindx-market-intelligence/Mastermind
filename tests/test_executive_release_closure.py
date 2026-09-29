"""Private closure validation; root transport and records are synthetic.

These cases do not attest an installed root owner or Runtime closure write.
"""

import copy
import os

import pytest

from control_plane import executive_release_consumer as c
from control_plane import executive_release_contract as contract
from control_plane import executive_privileged_client as transport
from tests.test_executive_release_contract import prestart_fixture, terminal_fixture


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
    with pytest.raises(c.ReleaseConsumerError, match="RELEASE_EFFECT_IN_PROGRESS"):
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
