from __future__ import annotations

import copy
import inspect

import pytest

from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp
from tests import test_web_sol_continuation_submit as continuation
from tests import test_web_sol_cognition_observe as observe


@pytest.fixture(autouse=True)
def isolated_process_fence(monkeypatch):
    monkeypatch.setattr(native, "_SUBMIT_CONTINUATION_NONCES", set())
    monkeypatch.setattr(native, "_SUBMIT_CONTINUATION_TURNS", set())


def payload(lease=None):
    lease = lease or continuation.runtime_lease()
    return observe.cognition.cognition._observe(
        runtime_binding_id=lease.runtime_binding.binding_id,
        runtime_binding_generation=lease.runtime_binding.binding_generation,
        runtime_binding_fingerprint=lease.runtime_binding_fingerprint,
    )


def request(**overrides):
    lease = continuation.runtime_lease()
    observe_payload = payload(lease)
    value = observe.request(
        conversation_fingerprint=continuation.HEX_A,
        session_alias=lease.runtime_binding.session_alias,
        runtime_binding_id=lease.runtime_binding.binding_id,
        runtime_binding_generation=lease.runtime_binding.binding_generation,
        runtime_binding_fingerprint=lease.runtime_binding_fingerprint,
        cognition_observe_payload=observe_payload,
    )
    value["cognition_observe_payload"] = observe_payload
    value.update(overrides)
    return value


def forward(req, writes, *, read=None, boot=continuation.RUNTIME_BOOT, write=None):
    observation = observe.result_observation(
        runtime_binding_id=req["runtime_binding_id"],
        runtime_binding_generation=req["runtime_binding_generation"],
        runtime_binding_fingerprint=req["runtime_binding_fingerprint"],
        document_epoch=observe.DOCUMENT_EPOCH,
    )
    return native.forward_request(
        req,
        write_chrome=write or writes.append,
        read_chrome=read or (lambda _: observe.ready(req=req, observation=observation)),
        timeout_seconds=1,
        expected_instance_id=continuation.runtime_lease().target.adapter_instance_id,
        boot_nonce=boot,
    )


def invoke(*, lease=None, data=None, **kwargs):
    lease = lease or continuation.runtime_lease()
    window = request()
    return client.observe_cognition_result_via_extension(
        continuation.binding(),
        lease,
        operation_key=observe.cognition.OPERATION,
        cognition_observe_payload=data if data is not None else payload(lease),
        issued_at=window["issued_at"],
        expires_at=window["expires_at"],
        nonce=observe.cognition.NONCE,
        **kwargs,
    )


def fake_exchange(monkeypatch, *, transform=None, boot=continuation.RUNTIME_BOOT):
    writes = []

    def exchange(req, *, before_action, **kwargs):
        before_action({"boot_nonce": boot})
        answer = forward(req, writes)
        return transform(answer) if transform else answer

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    return writes


def test_client_api_is_exact_and_result_only():
    signature = inspect.signature(client.observe_cognition_result_via_extension)
    assert list(signature.parameters) == [
        "binding",
        "runtime_binding_lease",
        "operation_key",
        "cognition_observe_payload",
        "issued_at",
        "expires_at",
        "nonce",
    ]
    for forbidden in ("prompt", "message", "text", "instruction", "selector", "url", "retry"):
        assert forbidden not in signature.parameters


def test_real_client_native_protocol_path_returns_detached_ready(monkeypatch):
    data = payload()
    original = copy.deepcopy(data)
    writes = fake_exchange(monkeypatch)
    answer = invoke(data=data)
    assert answer["status"] == "COGNITION_RESULT_READY"
    assert answer["cognition_observation"]["result"] is not None
    assert answer["cognition_observation"] is not data
    assert data == original
    assert writes[0]["cognition_observe_payload"] is not data
    assert len(writes) == 1


@pytest.mark.parametrize(
    "field", sorted(wsp._COGNITION_OBSERVE_IDENTITY_KEYS)
)
@pytest.mark.parametrize("layer", ["client", "native"])
def test_every_observation_identity_mutation_fails_after_one_exchange(
    monkeypatch, field, layer
):
    def wrong(answer):
        answer = copy.deepcopy(answer)
        old = answer["cognition_observation"][field]
        if field == "role":
            value = "review"
        elif field == "runtime_binding_generation":
            value = old + 1
        elif field.endswith("digest") or field in {"runtime_binding_id", "runtime_binding_fingerprint", "document_epoch"}:
            value = "e" * (48 if field == "runtime_binding_id" else 64 if field != "document_epoch" else 32)
        else:
            value = old + "-other"
        answer["cognition_observation"][field] = value
        return answer

    writes = []
    if layer == "client":
        writes = fake_exchange(monkeypatch, transform=wrong)
        action, error = invoke, client.WebSolExtensionError
    else:
        req = request()
        action = lambda: forward(
            req, writes, read=lambda _: wrong(observe.ready(req=req))
        )
        error = native.NativeHostError
    with pytest.raises(error, match="cognition_result_invalid"):
        action()
    assert len(writes) == 1


@pytest.mark.parametrize("field", ["session_alias", "runtime_binding_id", "runtime_binding_generation", "runtime_binding_fingerprint"])
@pytest.mark.parametrize("layer", ["client", "native"])
def test_outer_binding_mismatch_is_invalid_not_effect_unknown(monkeypatch, field, layer):
    def wrong(answer):
        answer = copy.deepcopy(answer)
        answer[field] = "review" if field == "session_alias" else answer[field] + (
            1 if field == "runtime_binding_generation" else "-x"
        )
        return answer

    writes = []
    if layer == "client":
        writes = fake_exchange(monkeypatch, transform=wrong)
        action, error = invoke, client.WebSolExtensionError
    else:
        req = request()
        action = lambda: forward(req, writes, read=lambda _: wrong(observe.ready(req=req)))
        error = native.NativeHostError
    with pytest.raises(error, match="cognition_result_invalid"):
        action()
    assert len(writes) == 1


@pytest.mark.parametrize("layer", ["client", "native"])
def test_stale_boot_or_lease_refuses_before_write(monkeypatch, layer):
    writes = []
    if layer == "client":
        writes = fake_exchange(
            monkeypatch, boot="different-native-boot-nonce-0001"
        )
        current = continuation.runtime_lease()
        old = current.runtime_binding
        stale = type(old)(
            session_alias=old.session_alias,
            binding_id="bind-wsx-" + ("f" * 48),
            binding_generation=old.binding_generation,
            native_handle=old.native_handle,
            account_label=old.account_label,
            reasoning_surface=old.reasoning_surface,
        )
        lease = continuation.wrb.WebSolRuntimeBindingLease(
            target=current.target,
            runtime_binding=stale,
            runtime_binding_fingerprint=(
                continuation.wrb.runtime_binding_fingerprint(
                    stale, current.target
                )
            ),
        )
        action = lambda: invoke(lease=lease, data=payload(lease))
    else:
        action = lambda: forward(request(), writes, boot="different-native-boot-nonce-0001")
    with pytest.raises(
        (client.WebSolExtensionError, native.NativeHostError),
        match="runtime_binding_stale",
    ):
        action()
    assert writes == []


@pytest.mark.parametrize("failure", ["timeout", "disconnect", "malformed"])
def test_read_failure_is_invalid_or_timeout_and_never_retries(failure):
    req, writes = request(), []

    def read(_):
        if failure == "timeout":
            return None
        if failure == "disconnect":
            raise OSError("closed")
        return {"cognition_observation": []}

    expected = "cognition_result_timeout" if failure == "timeout" else "cognition_result_invalid"
    with pytest.raises(native.NativeHostError, match=expected):
        forward(req, writes, read=read)
    assert len(writes) == 1


def test_two_identical_reads_do_not_consume_submit_effect_capacity():
    req, writes = request(), []
    first = forward(req, writes)
    second_nonce = copy.deepcopy(req)
    second_nonce["nonce"] += "-second"
    second = forward(second_nonce, writes)
    assert first["cognition_observation"] == second["cognition_observation"]
    assert first["cognition_observation"] is not second["cognition_observation"]
    assert native._SUBMIT_CONTINUATION_NONCES == set()
    assert native._SUBMIT_CONTINUATION_TURNS == set()
    assert len(writes) == 2


def test_client_missing_lease_or_inner_binding_drift_never_exchanges(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid request must not reach exchange")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", unexpected)
    req = request()
    with pytest.raises(client.WebSolExtensionError, match="runtime_binding_required"):
        client.observe_cognition_result_via_extension(
            continuation.binding(), None, operation_key=observe.cognition.OPERATION,
            cognition_observe_payload=payload(), issued_at=req["issued_at"],
            expires_at=req["expires_at"], nonce=observe.cognition.NONCE,
        )
    data = payload()
    data["runtime_binding_fingerprint"] = "f" * 64
    with pytest.raises(wsp.WebSolProtocolError):
        invoke(data=data)


@pytest.mark.parametrize("layer", ["native", "client"])
def test_generic_null_refusal_crosses_boundary_without_result_or_effect(monkeypatch, layer):
    def refused(answer):
        answer["status"] = "REQUEST_EXPIRED"
        answer["cognition_observation"] = None
        return answer
    if layer == "client":
        writes = fake_exchange(monkeypatch, transform=refused)
        answer = invoke()
    else:
        writes = []
        req = request()
        answer = forward(req, writes, read=lambda _: refused(observe.ready(req=req)))
    assert answer["status"] == "REQUEST_EXPIRED"
    assert answer["cognition_observation"] is None
    assert len(writes) == 1
    assert native._SUBMIT_CONTINUATION_NONCES == set()
    assert native._SUBMIT_CONTINUATION_TURNS == set()


def test_client_accepts_actual_valid_epoch_without_an_invented_expected_value(monkeypatch):
    def actual_epoch(answer):
        answer["cognition_observation"]["document_epoch"] = "d" * 32
        return answer
    fake_exchange(monkeypatch, transform=actual_epoch)
    assert invoke()["cognition_observation"]["document_epoch"] == "d" * 32


@pytest.mark.parametrize("field", sorted(wsp._COGNITION_OBSERVE_IDENTITY_KEYS))
@pytest.mark.parametrize("layer", ["client", "native"])
def test_selfconsistent_pending_foreign_identity_still_fails_request_join(monkeypatch, field, layer):
    def wrong(answer):
        answer = copy.deepcopy(answer)
        answer["status"] = "COGNITION_RESULT_PENDING"
        value = answer["cognition_observation"]
        value.update(status="COGNITION_RESULT_PENDING", provider_native_turn_id=None,
                     provider_turn_artifact_digest=None, result=None, result_digest=None,
                     result_byte_length=0)
        if field == "role":
            value[field] = "review"
        elif field == "runtime_binding_generation":
            value[field] += 1
        elif field == "runtime_binding_id":
            value[field] = "bind-wsx-" + "e" * 48
        elif field.endswith("digest") or field == "runtime_binding_fingerprint":
            value[field] = "e" * 64
        else:
            value[field] += "-other"
        if field.startswith("runtime_binding_"):
            answer[field] = value[field]
        # Prove this is a valid observation/outer receipt in isolation. Only the
        # immutable original request makes this foreign response unacceptable.
        assert wsp.validate_receipt(answer) == answer
        return answer
    if layer == "client":
        writes = fake_exchange(monkeypatch, transform=wrong)
        action, error = invoke, client.WebSolExtensionError
    else:
        writes = []
        req = request()
        def read(_):
            observation = observe.result_observation(
                runtime_binding_id=req["runtime_binding_id"],
                runtime_binding_generation=req["runtime_binding_generation"],
                runtime_binding_fingerprint=req["runtime_binding_fingerprint"],
            )
            return wrong(observe.ready(req=req, observation=observation))
        action = lambda: forward(req, writes, read=read)
        error = native.NativeHostError
    with pytest.raises(error, match="cognition_result_invalid"):
        action()
    assert len(writes) == 1
