"""Private current-admission observation must never submit or open Runtime."""
import asyncio
import dataclasses
import json
import os
import hashlib

import pytest

from control_plane import executive_service as svc
from scripts import executive_os_phase1c as cli
from tests.test_executive_service import _config


async def _observe(tmp_path, socket_root, monkeypatch, *, guard, peer=None,
                   args=None, armed=True):
    config = _config(tmp_path, socket_root=socket_root,
                     ceo_submit_armed=armed, allowed_peer_uids=(os.geteuid(), 9876))
    service = svc.ExecutiveControlService(config, ceo_submit_admission_guard=guard)
    # Bind only the existing request handler. No service startup, Runtime,
    # worker, provider, database, or admission envelope is constructed.
    def forbidden(*a, **kw):
        pytest.fail("diagnostic touched Runtime or ordinary command dispatch")
    monkeypatch.setattr(service, "_require_runtime", forbidden)
    monkeypatch.setattr(service, "_dispatch_request", forbidden)
    if peer is not None:
        monkeypatch.setattr(svc, "_peer_uid", lambda _: peer)
    server = await asyncio.start_unix_server(service._handle_connection,
                                             path=str(config.socket_path))
    try:
        return await svc.send_control_request(config.socket_path, "status",
                                              {"ceo_admission": True} if args is None else args)
    finally:
        server.close()
        await server.wait_closed()
        assert service.runtime is None


def test_private_status_runs_real_guard_once_without_runtime(tmp_path, short_socket_root, monkeypatch):
    calls = []
    result = asyncio.run(_observe(tmp_path, short_socket_root, monkeypatch,
                                  guard=lambda: calls.append("guard")))
    assert result == {"ok": True, "result": {
        "schema": "mastermind.executive_ceo_admission_observation/v1",
        "scope": "CURRENT_ONLY", "phase": "admitted"}}
    assert calls == ["guard"]


def test_private_status_denies_other_allowed_peer_before_guard(tmp_path, short_socket_root, monkeypatch):
    result = asyncio.run(_observe(tmp_path, short_socket_root, monkeypatch,
                                  guard=lambda: pytest.fail("unauthorized guard"), peer=9876))
    assert result["ok"] is False
    assert result["error"]["code"] == "peer_denied"


def test_cli_keeps_ordinary_status_unchanged_and_selects_private_observation():
    base = ["--socket", "/tmp/control.sock", "status"]
    assert cli._client_request(cli._parser().parse_args(base)) == ("status", {})
    assert cli._client_request(cli._parser().parse_args(base + ["--ceo-admission"])) == (
        "status", {"ceo_admission": True})


@pytest.mark.parametrize("args", [
    {"ceo_admission": False}, {"ceo_admission": 1}, {"ceo_admission": "true"},
    {"ceo_admission": True, "request_ref": "do-not-submit"},
])
def test_private_status_rejects_nonexact_request_without_guard(tmp_path, short_socket_root, monkeypatch, args):
    result = asyncio.run(_observe(tmp_path, short_socket_root, monkeypatch,
                                  args=args, guard=lambda: pytest.fail("invalid request reached guard")))
    assert result == {"ok": False, "error": {"code": "request_failed",
                                             "message": "invalid admission observation"}}


@pytest.mark.parametrize("fault,phase", [
    ("exception", "guard_refused"), ("return", "guard_refused"),
    ("attestation_refused", "attestation_refused"),
    ("config_binding_refused", "config_binding_refused"),
    ("receipt_refused", "receipt_refused"), ("unarmed", "unarmed"),
])
def test_private_status_closed_refusals_do_not_disclose_errors(tmp_path, short_socket_root, monkeypatch, fault, phase):
    calls = []
    secret = "/private/secret-token-should-never-escape"
    def guard():
        calls.append(1)
        if fault == "return":
            return {"secret": secret}
        if fault == "exception":
            raise RuntimeError(secret)
        if fault == "unarmed":
            pytest.fail("unarmed status invoked guard")
        try:
            raise RuntimeError(secret)
        except RuntimeError as exc:
            raise svc.CeoAdmissionPhaseRefusal(fault) from exc
    result = asyncio.run(_observe(tmp_path, short_socket_root, monkeypatch,
                                  guard=guard, armed=fault != "unarmed"))
    assert result["result"]["phase"] == phase
    assert set(result["result"]) == {"schema", "scope", "phase"}
    assert secret not in json.dumps(result)
    assert len(calls) == (0 if fault == "unarmed" else 1)


@pytest.mark.parametrize("change", ["closing", "config", "guard"])
def test_current_observation_rejects_composition_change(tmp_path, change):
    service = svc.ExecutiveControlService(_config(tmp_path, ceo_submit_armed=True))
    def guard():
        if change == "closing":
            service._closing = True
        elif change == "config":
            service.config = dataclasses.replace(service.config, ceo_submit_armed=False)
        else:
            service._ceo_submit_admission_guard = lambda: None
    service._ceo_submit_admission_guard = guard
    assert service._observe_ceo_submit_admission()["phase"] == "composition_changed"
    assert service.runtime is None


@pytest.mark.parametrize("unsafe_phase", ["/private/secret", ["secret"], None])
def test_unknown_typed_phase_is_generic(tmp_path, unsafe_phase):
    def guard():
        error = svc.CeoAdmissionPhaseRefusal("receipt_refused")
        error.phase = unsafe_phase
        raise error
    service = svc.ExecutiveControlService(_config(tmp_path, ceo_submit_armed=True),
                                          ceo_submit_admission_guard=guard)
    assert service._observe_ceo_submit_admission()["phase"] == "guard_refused"


def test_ordinary_status_does_not_probe_admission(tmp_path, monkeypatch):
    service = svc.ExecutiveControlService(_config(tmp_path, ceo_submit_armed=True),
        ceo_submit_admission_guard=lambda: pytest.fail("ordinary status invoked guard"))
    monkeypatch.setattr(service, "_require_runtime", lambda: None)
    result = asyncio.run(service._dispatch_request({
        "version": svc.CONTROL_PROTOCOL_VERSION, "command": "status", "args": {}}))
    assert result["protocol"] == svc.CONTROL_PROTOCOL_VERSION
    assert "ceo_admission" not in result
    assert "phase" not in result


@pytest.mark.parametrize("fault,phase", [
    (None, "admitted"), ("attestation", "attestation_refused"),
    ("config", "config_binding_refused"), ("file", "config_binding_refused"),
    ("receipt", "receipt_refused"),
])
def test_production_callback_preserves_order_and_classifies_private_phase(tmp_path, monkeypatch, fault, phase):
    from ops.executive_os import autonomy_control
    path = tmp_path / "control.json"
    path.write_text('{"fixture":"original"}')
    config_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    raw = {"fixture": "original"}
    calls = []
    def attest():
        calls.append("attestation")
        if fault == "attestation":
            raise RuntimeError("PRIVATE-ATTESTATION")
        return {"config_sha256": "0" * 64 if fault == "config" else config_sha}
    def receipts(value, *, own_config_sha256):
        calls.append("receipt")
        assert value is raw and own_config_sha256 == config_sha
        if fault == "receipt":
            raise RuntimeError("PRIVATE-RECEIPT")
    monkeypatch.setattr(autonomy_control, "require_ceo_submit_runtime_admission", receipts)
    production_guard = cli._ceo_admission_guard(raw, path, attest)
    if fault == "file":
        path.write_text('{"fixture":"changed"}')
    service = svc.ExecutiveControlService(_config(tmp_path, ceo_submit_armed=True),
                                          ceo_submit_admission_guard=production_guard)
    observed = service._observe_ceo_submit_admission()
    assert observed["phase"] == phase
    expected_calls = ["attestation"] + (["receipt"] if fault in (None, "receipt") else [])
    assert calls == expected_calls
    # Real submit uses exactly the same guard and remains opaque on failure.
    calls.clear()
    if fault is None:
        assert service._require_ceo_submit_admission() is None
    else:
        with pytest.raises(svc._CeoSubmitUnarmedError) as error:
            service._require_ceo_submit_admission()
        assert str(error.value) == ""
        assert error.value.__cause__.phase == phase
    assert calls == expected_calls
    assert service.runtime is None
