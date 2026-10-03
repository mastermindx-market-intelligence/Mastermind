from __future__ import annotations

import copy
import io

import pytest

from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp
from tests import test_web_sol_cognition_submit as submit
from tests import test_web_sol_cognition_transport as cognition
from tests import test_web_sol_continuation_submit as continuation


@pytest.fixture(autouse=True)
def isolated_process_fence(monkeypatch):
    monkeypatch.setattr(native, "_SUBMIT_CONTINUATION_NONCES", set())
    monkeypatch.setattr(native, "_SUBMIT_CONTINUATION_TURNS", set())


def payload(lease=None):
    lease = lease or continuation.runtime_lease()
    return cognition._submit(
        runtime_binding_id=lease.runtime_binding.binding_id,
        runtime_binding_generation=lease.runtime_binding.binding_generation,
        runtime_binding_fingerprint=lease.runtime_binding_fingerprint,
    )


def request(**overrides):
    lease = continuation.runtime_lease()
    result = submit.request(
        cognition_payload=payload(lease),
        runtime_binding_id=lease.runtime_binding.binding_id,
        runtime_binding_generation=lease.runtime_binding.binding_generation,
        runtime_binding_fingerprint=lease.runtime_binding_fingerprint,
    )
    result.update(overrides)
    return result


def forward(req, writes, *, read=None, boot=continuation.RUNTIME_BOOT, write=None):
    return native.forward_request(
        req,
        write_chrome=write or writes.append,
        read_chrome=read or (lambda _: submit.receipt(req, "COGNITION_STARTED", generation_state="active")),
        timeout_seconds=1,
        expected_instance_id=continuation.runtime_lease().target.adapter_instance_id,
        boot_nonce=boot,
    )


def invoke(*, lease=None, data=None, **kwargs):
    lease = lease or continuation.runtime_lease()
    window = request()
    return client.submit_cognition_assignment_via_extension(
        continuation.binding(), lease, operation_key=submit.OPERATION,
        cognition_payload=data if data is not None else payload(lease),
        issued_at=window["issued_at"], expires_at=window["expires_at"], nonce=submit.NONCE,
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


def test_actual_client_native_path_correlates_detached_assignment(monkeypatch):
    data = payload()
    original = copy.deepcopy(data)
    writes = fake_exchange(monkeypatch)
    answer = invoke(data=data)
    assert answer["status"] == "COGNITION_STARTED"
    assert answer["cognition_identity"] == submit.identity(data)
    assert len(writes) == 1
    assert data == original
    assert writes[0]["cognition_payload"] is not data
    assert "assignment" not in answer["cognition_identity"]


@pytest.mark.parametrize("field", sorted(wsp._COGNITION_IDENTITY_KEYS))
@pytest.mark.parametrize("layer", ["client", "native"])
def test_each_wrong_well_formed_identity_is_unknown_after_single_send(monkeypatch, field, layer):
    def wrong(answer):
        answer = copy.deepcopy(answer)
        old = answer["cognition_identity"][field]
        answer["cognition_identity"][field] = (
            "review" if field == "role" else "f" * 64 if field.endswith("digest") else old + "-other"
        )
        return answer
    writes = []
    if layer == "client":
        writes = fake_exchange(monkeypatch, transform=wrong)
        action, error = invoke, client.WebSolExtensionError
    else:
        req = request()
        action = lambda: forward(req, writes, read=lambda _: wrong(submit.receipt(req, "COGNITION_STARTED", generation_state="active")))
        error = native.NativeHostError
    with pytest.raises(error, match="cognition_submit_effect_unknown"):
        action()
    assert len(writes) == 1


@pytest.mark.parametrize("layer", ["client", "native"])
def test_current_boot_mismatch_refuses_before_write(monkeypatch, layer):
    writes = []
    if layer == "client":
        writes = fake_exchange(monkeypatch, boot="different-native-boot-nonce-0001")
        action, error = invoke, client.WebSolExtensionError
    else:
        action = lambda: forward(request(), writes, boot="different-native-boot-nonce-0001")
        error = native.NativeHostError
    with pytest.raises(error, match="runtime_binding_stale"):
        action()
    assert writes == []


def test_client_missing_lease_and_inner_binding_drift_never_exchange(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid binding must not reach exchange")
    monkeypatch.setattr(client, "_exchange_web_sol_socket", unexpected)
    req = request()
    with pytest.raises(client.WebSolExtensionError, match="runtime_binding_required"):
        client.submit_cognition_assignment_via_extension(
            continuation.binding(), None, operation_key=submit.OPERATION,
            cognition_payload=payload(), issued_at=req["issued_at"], expires_at=req["expires_at"], nonce=submit.NONCE,
        )
    data = payload(); data["runtime_binding_fingerprint"] = "f" * 64
    with pytest.raises(wsp.WebSolProtocolError):
        invoke(data=data)


def test_client_adapter_mismatch_refuses_before_exchange(monkeypatch):
    other_binding = continuation.binding()
    other_binding["locator"]["profile_id"] = "bbbbbbbbbbbbbbbbbbbbbbbb"
    lease = continuation.runtime_lease(other_binding)
    monkeypatch.setattr(client, "_exchange_web_sol_socket", lambda *a, **k: pytest.fail("must not exchange"))
    with pytest.raises(client.WebSolExtensionError, match="runtime_binding_target_mismatch"):
        invoke(lease=lease)


@pytest.mark.parametrize("failure", ["timeout", "disconnect", "malformed", "write"])
def test_native_possible_send_failures_are_unknown_and_never_retry(failure):
    req, writes = request(), []
    def read(_):
        if failure == "timeout": return None
        if failure == "disconnect": raise OSError("closed")
        return {}
    def write(value):
        writes.append(value)
        if failure == "write": raise OSError("possibly partly written")
    with pytest.raises(native.NativeHostError, match="cognition_submit_effect_unknown"):
        forward(req, writes, read=read, write=write)
    assert len(writes) == 1
    with pytest.raises(native.NativeHostError, match="nonce_reused"):
        forward(req, writes)
    assert len(writes) == 1


def test_native_expired_request_never_writes():
    req = request()
    req["issued_at"] = "2020-01-01T00:00:00Z"
    req["expires_at"] = "2020-01-01T00:00:30Z"
    writes = []
    with pytest.raises(wsp.WebSolProtocolError):
        forward(req, writes)
    assert writes == []


@pytest.mark.parametrize("collision", ["nonce", "turn"])
def test_cognition_and_continuation_share_existing_process_fence(collision):
    req, writes = request(), []
    forward(req, writes)
    other = continuation.request()
    if collision == "nonce": other["nonce"] = req["nonce"]
    else: other["turn_id"] = req["cognition_payload"]["turn_id"]
    with pytest.raises(native.NativeHostError, match=collision + "_reused"):
        forward(other, writes)
    assert len(writes) == 1


@pytest.mark.parametrize("collision", ["nonce", "turn"])
def test_cognition_duplicate_nonce_or_turn_refuses_before_second_write(collision):
    req, writes = request(), []
    forward(req, writes)
    other = copy.deepcopy(req)
    if collision == "turn": other["nonce"] += "-other"
    else: other["cognition_payload"]["turn_id"] += "-other"
    with pytest.raises(native.NativeHostError, match=collision + "_reused"):
        forward(other, writes)
    assert len(writes) == 1


def test_existing_native_submit_capacity_is_shared(monkeypatch):
    monkeypatch.setattr(native, "MAX_SUBMIT_CONTINUATION_EFFECTS", 0)
    writes = []
    with pytest.raises(wsp.WebSolProtocolError, match="ledger full"):
        forward(request(), writes)
    assert writes == []


def test_client_socket_loss_before_and_after_possible_send(monkeypatch):
    class Stream(io.BytesIO):
        def close(self): pass
    class Connection:
        def __init__(self): self.writer, self.reader = Stream(), Stream()
        def settimeout(self, _): pass
        def connect(self, _): pass
        def makefile(self, mode, **kwargs): return self.writer if mode == "wb" else self.reader
        def close(self): pass
    connection = Connection()
    monkeypatch.setattr(client, "_private_socket", lambda _: None)
    monkeypatch.setattr(client.socket, "socket", lambda *a: connection)
    monkeypatch.setattr(client, "_complete_transport_handshake", lambda *a, **k: {"boot_nonce": continuation.RUNTIME_BOOT})
    # Actual write_frame writes the complete frame, then empty response refuses.
    req = request()
    with pytest.raises(client.WebSolExtensionError, match="cognition_submit_effect_unknown"):
        client._exchange_web_sol_socket(req, path=client.Path("unused"), expected_instance_id="unused")
    assert connection.writer.getvalue() == native.encode_frame(req)
    # A failure before action-frame writing leaves the action completely unsent.
    connection = Connection()
    def before(_): raise client.WebSolExtensionError("runtime_binding_stale")
    with pytest.raises(client.WebSolExtensionError, match="runtime_binding_stale"):
        client._exchange_web_sol_socket(request(), path=client.Path("unused"), expected_instance_id="unused", before_action=before)
    assert connection.writer.getvalue() == b""


@pytest.mark.parametrize("accepted_bytes,code", [(0, "extension_unavailable"), (2, "cognition_submit_effect_unknown")])
def test_partial_action_frame_uses_existing_write_progress(monkeypatch, accepted_bytes, code):
    class Stream(io.BytesIO):
        def close(self): pass
    class Partial(Stream):
        def write(self, value):
            if self.tell(): return 0
            return super().write(value[:accepted_bytes])
    writer = Partial()
    class Connection:
        def settimeout(self, _): pass
        def connect(self, _): pass
        def makefile(self, mode, **kwargs): return writer if mode == "wb" else Stream()
        def close(self): pass
    monkeypatch.setattr(client, "_private_socket", lambda _: None)
    monkeypatch.setattr(client.socket, "socket", lambda *a: Connection())
    monkeypatch.setattr(client, "_complete_transport_handshake", lambda *a, **k: {})
    with pytest.raises(client.WebSolExtensionError, match=code):
        client._exchange_web_sol_socket(request(), path=client.Path("unused"), expected_instance_id="unused")
    assert len(writer.getvalue()) == accepted_bytes


def test_native_deadline_before_write_is_definitely_not_submitted():
    writes = []
    with pytest.raises(native.NativeHostError, match="cognition_not_submitted"):
        native.forward_request(
            request(), write_chrome=writes.append, read_chrome=lambda _: None,
            timeout_seconds=1, deadline=native.Deadline(ends_at=0), monotonic=lambda: 1,
            expected_instance_id=continuation.runtime_lease().target.adapter_instance_id,
            boot_nonce=continuation.RUNTIME_BOOT,
        )
    assert writes == []
