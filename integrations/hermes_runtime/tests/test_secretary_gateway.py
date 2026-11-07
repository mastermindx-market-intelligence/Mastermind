"""Role HTTP -> actual native private wire; no provider or host acceptance claim."""
from dataclasses import replace
import http.client
import json
from pathlib import Path
import socket
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from integrations.hermes_harness.stack import compose_profile
from integrations.hermes_runtime.constants import SECRETARY_CONVERSATION_TOKEN_ENV, SECRETARY_PATH, conversation_contract
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.gateway import Gateway
from integrations.hermes_runtime import native_session_control as control
from integrations.hermes_runtime.secrets import (
    Secrets, child_env, register_child_secret_env, secretary_conversation_token,
)
from integrations.hermes_runtime.supervisor import ServiceRuntime

HEALTH = "health-credential-for-fixture"
CONVERSATION = "conversation-credential-for-fixture"
IMPLEMENTATION = "a" * 40


def post(gateway, body, *, token=CONVERSATION, path=SECRETARY_PATH, extra=()):
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    peer = http.client.HTTPConnection(gateway.host, gateway.port, timeout=3)
    try:
        peer.putrequest("POST", path)
        peer.putheader("Authorization", "Bearer " + token)
        peer.putheader("Content-Type", "application/json")
        peer.putheader("Content-Length", str(len(body)))
        for key, value in extra:
            peer.putheader(key, value)
        peer.endheaders(body)
        response = peer.getresponse()
        return response.status, response.read(), response.getheader("Connection")
    finally:
        peer.close()


@pytest.fixture
def gateway():
    calls = []
    def handler(request):
        calls.append(request)
        if request.get("lose"):
            raise TimeoutError("native response was lost")
        return request
    instance = Gateway("127.0.0.1", 0, HEALTH, lambda: (200, {"status": "ok"}),
                       conversation_token=CONVERSATION, conversation_handler=handler)
    try:
        yield instance, calls
    finally:
        instance.close()


def test_separate_credential_and_one_dispatch(gateway):
    instance, calls = gateway
    assert post(instance, {"operation": "observe"}, token=HEALTH)[0] == 401
    assert calls == []
    status, raw, connection = post(instance, {"operation": "observe"})
    assert status == 200 and json.loads(raw) == {"operation": "observe"}
    assert connection == "close" and calls == [{"operation": "observe"}]


@pytest.mark.parametrize("body,path,extra", [
    (b'{"operation":"observe","operation":"submit"}', SECRETARY_PATH, ()),
    (b'{"target":{"revision":0,"revision":1}}', SECRETARY_PATH, ()),
    (b'{"value":NaN}', SECRETARY_PATH, ()),
    (b"[]", SECRETARY_PATH, ()),
    (b"{}", SECRETARY_PATH + "?operation=submit", ()),
    (b"{}", SECRETARY_PATH, (("Transfer-Encoding", "chunked"),)),
    (b"{}", SECRETARY_PATH, (("Content-Length", "2"),)),
    (b" " * (65536 + 1), SECRETARY_PATH, ()),
])
def test_malformed_request_never_enters_native_owner(gateway, body, path, extra):
    instance, calls = gateway
    assert post(instance, body, path=path, extra=extra)[0] == 400
    assert calls == []


def test_duplicate_authorization_refuses(gateway):
    instance, calls = gateway
    assert post(instance, {}, extra=(("Authorization", "Bearer " + CONVERSATION),))[0] == 401
    assert calls == []


def test_legacy_gateway_remains_read_only():
    instance = Gateway("127.0.0.1", 0, HEALTH, lambda: (200, {"status": "ok"}))
    try:
        assert post(instance, {}, token=HEALTH)[0] == 405
    finally:
        instance.close()


def test_post_dispatch_exception_is_unknown_and_not_retried(gateway):
    instance, calls = gateway
    status, raw, _ = post(instance, {"lose": True})
    assert status == 503 and json.loads(raw) == {"status": "effect_unknown"}
    assert calls == [{"lose": True}]


@pytest.mark.parametrize("secret", [HEALTH, CONVERSATION])
def test_response_cannot_disclose_front_door_credentials(gateway, secret):
    instance, calls = gateway
    status, raw, _ = post(instance, {"answer": secret})
    assert status == 503 and secret.encode() not in raw
    assert len(calls) == 1


def test_conversation_credential_stays_with_existing_secret_owner(tmp_path):
    values = {SECRETARY_CONVERSATION_TOKEN_ENV: CONVERSATION, "PROVIDER_KEY": "provider-fixture-value"}
    secrets = Secrets(HEALTH, "hermes", "dashboard-fixture-value", values)
    assert secretary_conversation_token(secrets) == CONVERSATION
    assert CONVERSATION not in child_env(secrets, home=tmp_path).values()
    with pytest.raises(RuntimeRefusal, match="STAYS_ON_THE_FRONT_DOOR"):
        register_child_secret_env([SECRETARY_CONVERSATION_TOKEN_ENV])
    for alias in (HEALTH, secrets.dashboard_password, values["PROVIDER_KEY"]):
        with pytest.raises(RuntimeRefusal, match="CREDENTIAL_ALIAS_REFUSED"):
            secretary_conversation_token(Secrets(HEALTH, "hermes", secrets.dashboard_password,
                {**values, SECRETARY_CONVERSATION_TOKEN_ENV: alias}))


def selected_runtime(tmp_path, role="mmsecretary"):
    state = tmp_path / "state"
    hermes_home = state / "current/hermes-home"
    home = hermes_home / "profiles" / role
    home.mkdir(parents=True)
    profile = replace(compose_profile(role, state_dir=state, hermes_home=hermes_home,
                                      secrets_file=tmp_path / "secret.env"),
                      gateway_backend="native-session-authority")
    launch = SimpleNamespace(owner=SimpleNamespace(root=Path("/inert") / IMPLEMENTATION),
                             check=lambda: None, observe_child=lambda pid: None,
                             qualify=lambda profile, executable: None)
    secrets = Secrets(HEALTH, "hermes", "dashboard-fixture-value",
                      {conversation_contract(role).token_env: CONVERSATION})
    runtime = ServiceRuntime(profile, secrets, Path("/inert/hermes"), native_launch=launch)
    runtime._child = SimpleNamespace(pid=420, poll=lambda: None)
    runtime._backend_ready = True
    runtime._native_home = home.resolve()
    return runtime


def wrapper(request, implementation=IMPLEMENTATION, *, role="mmsecretary"):
    return {"schema": conversation_contract(role).request_schema,
            "implementation_sha": implementation, "request": request}


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_actual_role_gateway_reaches_one_native_private_request(monkeypatch, tmp_path, role):
    runtime = selected_runtime(tmp_path, role=role)
    contract = conversation_contract(role)
    sibling = conversation_contract("mmmeta" if role == "mmsecretary" else "mmsecretary")
    left, right = socket.socketpair()
    seen = []
    def serve():
        with right:
            raw = bytearray()
            while b"\n" not in raw:
                raw.extend(right.recv(65536))
            seen.append(json.loads(raw))
            right.sendall(json.dumps({"protocol": 1, "id": 1, "ok": True,
                "result": {"schema": contract.native_schema, "status": "TARGET", "target": {"session_id": "s"}}}).encode() + b"\n")
    worker = threading.Thread(target=serve)
    worker.start()
    module = ModuleType("hermes_cli.gateway_runtime_discovery")
    module.connect_private = lambda home, timeout: left
    module.query_identify = lambda home, timeout: {"pid": 420, "hermes_home": str(home)}
    monkeypatch.setitem(sys.modules, module.__name__, module)
    endpoint = ModuleType("hermes_cli.gateway_runtime")
    endpoint._endpoint = lambda payload, home: SimpleNamespace(state="ready", endpoint=object())
    monkeypatch.setitem(sys.modules, endpoint.__name__, endpoint)
    instance = Gateway("127.0.0.1", 0, HEALTH, runtime.health_snapshot,
                       conversation_token=CONVERSATION, conversation_handler=runtime._native_conversation,
                       role=role)
    try:
        request = {"operation": "observe", "session_id": "s"}
        assert post(instance, wrapper(request, role=role), path=sibling.path)[0] == 405
        assert post(instance, wrapper(request, role=role), path=contract.path,
                    token="sibling-role-fixture-token")[0] == 401
        for refused in (wrapper(request, "b" * 40, role=role),
                        wrapper(request, role=sibling.role)):
            code, raw, _ = post(instance, refused, path=contract.path)
            result = json.loads(raw)
            assert code == 200 and result["result"]["status"] == "REFUSED"
            assert result["schema"] == contract.response_schema
            assert result["result"]["schema"] == contract.native_schema
        assert seen == []
        status, raw, _ = post(instance, wrapper(request, role=role), path=contract.path)
        result = json.loads(raw)
        assert status == 200 and result["implementation_sha"] == IMPLEMENTATION
        assert result["result"]["status"] == "TARGET"
        assert result["schema"] == contract.response_schema
        assert result["result"]["schema"] == contract.native_schema
    finally:
        instance.close()
        worker.join(timeout=2)
    assert not worker.is_alive() and len(seen) == 1
    assert seen[0]["verb"] == contract.native_verb
    assert seen[0]["params"] == {"operation": "observe", "profile_id": str(runtime._native_home), "session_id": "s"}


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_post_native_source_loss_preserves_uncertainty(monkeypatch, tmp_path, role):
    runtime = selected_runtime(tmp_path, role=role)
    calls = []
    def dispatch(self, request):
        calls.append(request)
        runtime._native_launch.check = lambda: (_ for _ in ()).throw(RuntimeError("source changed"))
        return {"schema": conversation_contract(role).native_schema, "status": "ADMITTED", "admission": {"admission_id": "a"}}
    monkeypatch.setattr(control.NativeSecretaryClient, "dispatch", dispatch)
    result = runtime._native_conversation(wrapper({"operation": "submit"}, role=role))
    assert result["result"]["status"] == "EFFECT_UNKNOWN"
    assert len(calls) == 1


@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_unavailable_native_child_never_dispatches(monkeypatch, tmp_path, role):
    runtime = selected_runtime(tmp_path, role=role)
    runtime._backend_ready = False
    monkeypatch.setattr(control.NativeSecretaryClient, "dispatch",
                        lambda *args: pytest.fail("unavailable owner must not receive a request"))
    assert runtime._native_conversation(wrapper({"operation": "submit"}, role=role))["result"]["status"] == "UNAVAILABLE"


def test_json_escaping_cannot_hide_disclosed_conversation_credential():
    escaped = 'conversation-"quoted"-\\-credential'
    instance = Gateway("127.0.0.1", 0, HEALTH, lambda: (200, {"status": "ok"}),
                       conversation_token=escaped,
                       conversation_handler=lambda request: {"nested": [{"answer": escaped}]})
    try:
        status, raw, _ = post(instance, {}, token=escaped)
        assert status == 503 and json.loads(raw) == {"status": "effect_unknown"}
    finally:
        instance.close()


@pytest.mark.parametrize("change", ["stop", "restart", "home", "not-ready"])
@pytest.mark.parametrize("role", ["mmsecretary", "mmmeta"])
def test_owner_change_during_submit_is_unknown(monkeypatch, tmp_path, change, role):
    runtime = selected_runtime(tmp_path, role=role)
    calls = []
    def dispatch(self, request):
        calls.append(request)
        if change == "stop":
            runtime._stop.set()
        elif change == "restart":
            runtime._child = SimpleNamespace(pid=421, poll=lambda: None)
        elif change == "home":
            runtime._native_home = tmp_path / "other"
        else:
            runtime._backend_ready = False
        return {"schema": conversation_contract(role).native_schema, "status": "ADMITTED"}
    monkeypatch.setattr(control.NativeSecretaryClient, "dispatch", dispatch)
    assert runtime._native_conversation(wrapper({"operation": "submit"}, role=role))["result"]["status"] == "EFFECT_UNKNOWN"
    assert len(calls) == 1


def test_native_identify_wrong_supervised_pid_never_connects(monkeypatch, tmp_path):
    discovery = ModuleType("hermes_cli.gateway_runtime_discovery")
    discovery.query_identify = lambda home, timeout: {"pid": 421, "hermes_home": str(home)}
    discovery.connect_private = lambda *args: pytest.fail("different child received a request")
    monkeypatch.setitem(sys.modules, discovery.__name__, discovery)
    runtime = ModuleType("hermes_cli.gateway_runtime")
    runtime._endpoint = lambda *args: pytest.fail("unqualified identify accepted")
    monkeypatch.setitem(sys.modules, runtime.__name__, runtime)
    with pytest.raises(RuntimeRefusal, match="OWNER_CHANGED"):
        control.NativeSecretaryClient(tmp_path, expected_pid=420).observe("s")
