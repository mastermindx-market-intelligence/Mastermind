"""hermes_native_return delivery tests (DONE_WHEN row 5).

Idempotent delivery keyed by (return digest, conversation id), receipt
vocabulary closure, ambiguous send → unknown with NO second send, clean
refusals, the adapter over the existing native send seam (against an
injected fake seam — the live Hermes gateway is never contacted), and
cross-language receipt parity against the committed fixture."""
import asyncio
import json
from pathlib import Path

import pytest

from control_plane.execution_return_projection import (
    EXECUTION_RETURN_DELIVERY_SCHEMA,
    project_execution_return,
    validate_execution_return,
)
from control_plane.remote_worker_transport import TransportEffect, TransportError
from integrations.session_bridge.hermes_native_return import (
    HermesExecutionReturnDeliverer,
    HermesReturnDeliveryError,
    HermesReturnUnknownOutcome,
    SecretaryNativeSendTransport,
    mint_return_submission_id,
    validate_execution_return_delivery,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "integrations" / "mmos" / "fixtures" / "execution_return_v1"

SEALED = "9" * 64
NAMESPACE = "mastermind.control_plane.t3_execution_adapter/v1:hermes-eng-seat-1"
CONVERSATION = "sess-3f9c2"


def record(**over):
    facts = {
        "attempt": {
            "attempt_id": "ATT-000042", "root_id": "root-wo19-coding-7",
            "idempotency_key": "t3-launch-abc123",
            "authenticated_namespace": NAMESPACE,
            "t3_thread_id": "th_ready_9", "t3_run_id": "run-77",
            "seal": {"digest": SEALED},
        },
        "result": {"text": "done → union-green", "artifact_refs": ["tests/x.py"]},
        "github": {"branch": "t3/execution-return-path", "pr_number": 2338,
                   "pr_url": None,
                   "checks": [{"name": "ci", "conclusion": "success"}],
                   "merge_state": "merged"},
        "original_requester": {
            "teammate_id": "hermes-engineering", "conversation_id": CONVERSATION,
            "project_id": "proj-mmos-v1", "authenticated_namespace": NAMESPACE,
        },
    }
    facts.update(over)
    return project_execution_return(facts)


class FakeTransport:
    """Deterministic fake for the native send seam port."""

    def __init__(self, *, outcome="delivered", ref="adm-1", refusal=None):
        self.outcome = outcome
        self.ref = ref
        self.refusal = refusal
        self.sends = []

    async def send(self, *, conversation_id, submission_id, text):
        self.sends.append({"conversation_id": conversation_id,
                           "submission_id": submission_id, "text": text})
        if self.outcome == "delivered":
            return self.ref
        if self.outcome == "unknown":
            raise HermesReturnUnknownOutcome("lost reply")
        raise self.refusal or HermesReturnDeliveryError("SESSION_BUSY", "gateway busy")


class FakeNativeSession:
    """Fake for the HermesNativeSession.request seam (duck-typed)."""

    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    def require_binding(self, binding):
        pass

    def require_submit(self, binding):
        pass

    async def request(self, binding, native_request, *, before_write=None):
        if getattr(self.error, "code", None) == "binding_unavailable":
            raise self.error
        if native_request["operation"] == "submit":
            if not callable(before_write):
                raise TransportError("before_write_required", TransportEffect.NO_EFFECT)
            before_write("submit", json.loads(json.dumps(native_request)))
        self.requests.append({"binding": binding, "native_request": native_request})
        if self.error is not None:
            raise self.error
        return self.result


def run(coro):
    return asyncio.run(coro)


# --- delivered + idempotent redelivery --------------------------------------

def test_delivered_receipt_and_idempotent_redelivery():
    transport = FakeTransport()
    deliverer = HermesExecutionReturnDeliverer(transport)
    first = run(deliverer.deliver(record()))
    assert first["schema"] == EXECUTION_RETURN_DELIVERY_SCHEMA
    assert first["state"] == "delivered"
    assert first["transport_ref"] == "adm-1"
    assert first["refusal_code"] is None
    assert first["conversation_id"] == CONVERSATION
    assert first["submission_id"] == mint_return_submission_id(
        first["return_digest"], CONVERSATION)
    assert len(transport.sends) == 1
    # The native text is the canonical record, byte-identical to the digest basis.
    sent = json.loads(transport.sends[0]["text"])
    assert validate_execution_return(sent) == sent
    # Redelivery returns the PRIOR receipt and never sends again.
    second = run(deliverer.deliver(record()))
    assert second == first
    assert len(transport.sends) == 1
    assert deliverer.prior_receipt(record()) == first


def test_different_conversation_or_digest_is_a_new_delivery():
    transport = FakeTransport()
    deliverer = HermesExecutionReturnDeliverer(transport)
    run(deliverer.deliver(record()))
    other_conversation = record(original_requester={
        "teammate_id": "hermes-engineering", "conversation_id": "sess-other",
        "project_id": "proj-mmos-v1", "authenticated_namespace": NAMESPACE,
    })
    run(deliverer.deliver(other_conversation))
    other_result = record(result={"text": "different", "artifact_refs": []})
    run(deliverer.deliver(other_result))
    assert len(transport.sends) == 3


# --- ambiguous send → unknown, never a second send --------------------------

def test_ambiguous_send_is_unknown_and_never_retried():
    transport = FakeTransport(outcome="unknown")
    deliverer = HermesExecutionReturnDeliverer(transport)
    first = run(deliverer.deliver(record()))
    assert first["state"] == "unknown"
    assert first["transport_ref"] is None
    assert first["refusal_code"] is None
    assert len(transport.sends) == 1
    # Repeated delivery attempts return the SAME unknown receipt and the
    # transport is never called again — no auto-retry after unknown.
    for _ in range(3):
        again = run(deliverer.deliver(record()))
        assert again == first
    assert len(transport.sends) == 1


def test_malformed_transport_ref_is_ambiguous_not_refused():
    class WeirdRefTransport(FakeTransport):
        async def send(self, **kwargs):
            await super().send(**kwargs)
            return ""  # post-send malformed ref: cannot downgrade to refusal

    transport = WeirdRefTransport()
    receipt = run(HermesExecutionReturnDeliverer(transport).deliver(record()))
    assert receipt["state"] == "unknown"


# --- clean refusals ----------------------------------------------------------

def test_clean_refusal_receipt_and_terminal_redelivery():
    transport = FakeTransport(
        outcome="refused",
        refusal=HermesReturnDeliveryError("SESSION_BUSY", "gateway busy"))
    deliverer = HermesExecutionReturnDeliverer(transport)
    first = run(deliverer.deliver(record()))
    assert first["state"] == "refused"
    assert first["refusal_code"] == "SESSION_BUSY"
    assert first["transport_ref"] is None
    assert len(transport.sends) == 1
    assert run(deliverer.deliver(record())) == first
    assert len(transport.sends) == 1


def test_untyped_exception_is_unknown_without_proof_of_no_effect():
    class ExplodingTransport(FakeTransport):
        async def send(self, **kwargs):
            await super().send(**kwargs)
            raise RuntimeError("socket exploded before dispatch")

    transport = ExplodingTransport()
    receipt = run(HermesExecutionReturnDeliverer(transport).deliver(record()))
    assert receipt["state"] == "unknown"
    assert receipt["refusal_code"] is None


def test_invalid_record_is_refused_before_any_send():
    transport = FakeTransport()
    deliverer = HermesExecutionReturnDeliverer(transport)
    tampered = record()
    tampered["stage"] = "checks_green"  # evidence says merged
    with pytest.raises(Exception):
        run(deliverer.deliver(tampered))
    assert transport.sends == []
    with pytest.raises(HermesReturnDeliveryError):
        HermesExecutionReturnDeliverer(object())


# --- receipt validator closure ----------------------------------------------

def test_receipt_validator_is_fail_closed():
    good = run(HermesExecutionReturnDeliverer(FakeTransport()).deliver(record()))
    assert validate_execution_return_delivery(good) == good
    bad_state = dict(good, state="maybe")
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(bad_state)
    delivered_no_ref = dict(good, transport_ref=None)
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(delivered_no_ref)
    unknown_with_ref = dict(good, state="unknown", transport_ref="x")
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(unknown_with_ref)
    refused_without_code = dict(good, state="refused", refusal_code=None)
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(refused_without_code)
    non_refused_with_code = dict(good, refusal_code="X")
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(non_refused_with_code)
    bad_submission = dict(good, submission_id="execret-nothex")
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(bad_submission)
    bad_code = dict(good, state="refused", refusal_code="not a code")
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(bad_code)
    extra = dict(good, extra=1)
    with pytest.raises(HermesReturnDeliveryError):
        validate_execution_return_delivery(extra)


# --- the production adapter over the EXISTING native send seam --------------

def native_binding():
    return {"schema": "mastermind.session_bridge.hermes_secretary_binding.v1",
            "session_id": CONVERSATION, "profile_id": "engineering",
            "principal_id": "hermes-engineering"}


def native_target():
    return {"profile_id": "engineering", "session_id": CONVERSATION,
            "principal_id": "hermes-engineering", "instance_id": "inst-1",
            "authority_epoch": 4, "revision": 9, "execution_generation": 2}


def native_admission(reference="adm-42"):
    return {"admission_id": reference, "status": "queued", "sequence": 1,
            "ref": {"profile_id": "engineering", "session_id": CONVERSATION},
            "authority_epoch": 4, "execution_generation": None, "outcome": None}


def test_adapter_submits_the_closed_native_request_through_the_seam():
    session = FakeNativeSession(result={
        "schema": "mastermind.hermes_secretary_native_control/v1",
        "status": "ADMITTED",
        "admission": native_admission(),
    })
    transport = SecretaryNativeSendTransport(
        session, native_binding(), target=native_target())
    originals = []
    receipt = run(HermesExecutionReturnDeliverer(transport).deliver(
        record(), before_write=lambda original: originals.append(original)))
    assert receipt["state"] == "delivered"
    assert receipt["transport_ref"] == "adm-42"
    assert len(session.requests) == 1
    binding, native_request = session.requests[0]["binding"], session.requests[0]["native_request"]
    assert binding["session_id"] == CONVERSATION
    assert set(native_request) == {"operation", "target", "submission_id", "text"}
    assert native_request["operation"] == "submit"
    assert native_request["target"]["session_id"] == CONVERSATION
    assert native_request["submission_id"] == receipt["submission_id"]
    assert json.loads(native_request["text"])["schema"] == "mastermind.execution_return/v1"
    assert originals[0]["request"] == native_request
    assert originals[0]["binding"] == binding


def test_adapter_refuses_a_conversation_mismatch_before_dispatch():
    session = FakeNativeSession()
    transport = SecretaryNativeSendTransport(
        session, native_binding(), target=native_target())
    other = record(original_requester={
        "teammate_id": "hermes-engineering", "conversation_id": "sess-not-mine",
        "project_id": "proj-mmos-v1", "authenticated_namespace": NAMESPACE,
    })
    receipt = run(HermesExecutionReturnDeliverer(transport).deliver(other))
    assert receipt["state"] == "refused"
    assert receipt["refusal_code"] == "CONVERSATION_MISMATCH"
    assert session.requests == []


def test_adapter_maps_native_status_law():
    def receipt_for(result, error=None):
        session = FakeNativeSession(result=result, error=error)
        transport = SecretaryNativeSendTransport(
            session, native_binding(), target=native_target())
        return run(HermesExecutionReturnDeliverer(transport).deliver(
            record(), before_write=lambda original: None))

    observed = receipt_for({"schema": "mastermind.hermes_secretary_native_control/v1", "status": "OBSERVED",
                            "admission": native_admission("adm-9")})
    assert observed["state"] == "delivered" and observed["transport_ref"] == "adm-9"

    refused = receipt_for({"schema": "mastermind.hermes_secretary_native_control/v1", "status": "REFUSED", "reason": "SESSION_BUSY"})
    assert refused["state"] == "refused" and refused["refusal_code"] == "SESSION_BUSY"

    not_submitted = receipt_for({"schema": "mastermind.hermes_secretary_native_control/v1", "status": "NOT_SUBMITTED"})
    assert not_submitted["state"] == "refused" and not_submitted["refusal_code"] == "NOT_SUBMITTED"

    effect_unknown = receipt_for({"schema": "mastermind.hermes_secretary_native_control/v1", "status": "EFFECT_UNKNOWN"})
    assert effect_unknown["state"] == "unknown"

    ambiguous_shape = receipt_for({"schema": "mastermind.hermes_secretary_native_control/v1", "status": "SOMETHING_ELSE"})
    assert ambiguous_shape["state"] == "unknown"  # post-dispatch unreadable ⇒ ambiguous

    class GuardError(Exception):
        code = "binding_unavailable"

    guard = receipt_for(None, error=GuardError("original native binding is unavailable"))
    assert guard["state"] == "refused" and guard["refusal_code"] == "binding_unavailable"

    class MidFlightError(Exception):
        pass

    ambiguous_exception = receipt_for(None, error=MidFlightError("lost reply mid-send"))
    assert ambiguous_exception["state"] == "unknown"


def test_adapter_constructor_is_fail_closed():
    with pytest.raises(HermesReturnDeliveryError):
        SecretaryNativeSendTransport(object(), native_binding(), target=native_target())
    with pytest.raises(HermesReturnDeliveryError):
        SecretaryNativeSendTransport(FakeNativeSession(), {}, target=native_target())
    with pytest.raises(HermesReturnDeliveryError):
        SecretaryNativeSendTransport(FakeNativeSession(), native_binding(), target={})


# --- cross-language fixture parity -------------------------------------------

def test_committed_sample_receipt_parses_in_python():
    sample = json.loads((FIXTURE_DIR / "sample_receipt.json").read_text("utf-8"))
    assert validate_execution_return_delivery(sample) == sample


def test_submission_id_mint_is_deterministic():
    digest = record()["digest"]
    first = mint_return_submission_id(digest, CONVERSATION)
    assert first == mint_return_submission_id(digest, CONVERSATION)
    assert first.startswith("execret-") and len(first) == len("execret-") + 32
    assert first != mint_return_submission_id("0" * 64, CONVERSATION)
    assert first != mint_return_submission_id(digest, "sess-other")
