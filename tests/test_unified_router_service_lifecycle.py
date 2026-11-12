"""Service lifecycle tests use synthetic config and sockets; no live service calls."""
from __future__ import annotations

import errno
import math
import socket
from types import SimpleNamespace

import pytest
import uvicorn

from ops.native_fabric.unified_router import gateway, service


@pytest.fixture
def service_owner(monkeypatch, tmp_path):
    """Observe only the source entrypoint; never open a network listener."""
    state = SimpleNamespace(events=[], config=None, config_kwargs=None,
                            bind_error=None, run_error=None, closed=False,
                            settings=SimpleNamespace(request_timeout_s=1800.0))
    for name in service._ALLOWED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(service, "load_environment", lambda path: {})

    def settings():
        state.events.append("validated_settings")
        return state.settings

    def app(config):
        assert config is state.settings
        state.events.append("app_from_validated_settings")
        return "synthetic-asgi-app"

    class Listener:
        def setsockopt(self, *args):
            state.events.append(("setsockopt", args))

        def bind(self, address):
            state.events.append(("bind", address))
            if state.bind_error:
                raise state.bind_error

        def listen(self, backlog):
            state.events.append(("listen", backlog))

        def close(self):
            state.closed = True
            state.events.append("closed")

    listener = Listener()

    def make_socket(*args):
        state.events.append("socket_created")
        return listener

    def configure(app, **kwargs):
        state.config = app
        state.config_kwargs = kwargs
        return "synthetic-uvicorn-config"

    class Server:
        def __init__(self, cfg):
            assert cfg == "synthetic-uvicorn-config"
            state.events.append("server_created")

        def run(self, *, sockets):
            assert sockets == [listener]
            state.events.append("server_running")
            if state.run_error:
                raise state.run_error
            if callable(state.config):
                assert state.config() == "synthetic-asgi-app"

    monkeypatch.setattr(gateway, "settings_from_env", settings)
    monkeypatch.setattr(gateway, "create_app", app)
    monkeypatch.setattr(socket, "socket", make_socket)
    monkeypatch.setattr(uvicorn, "Config", configure)
    monkeypatch.setattr(uvicorn, "Server", Server)
    state.args = ["--env-file", str(tmp_path / "synthetic.env"), "--port", "8339"]
    return state


@pytest.mark.parametrize("request_timeout", [0.25, 30.0, 1800.5])
def test_one_accepting_process_preserves_configured_request_and_cleanup_deadline(service_owner, request_timeout):
    state = service_owner
    state.settings.request_timeout_s = request_timeout
    service.main(state.args)
    assert state.config_kwargs["timeout_graceful_shutdown"] == math.ceil(request_timeout + 5.0)
    assert state.events.index("validated_settings") < state.events.index("socket_created")
    assert state.config_kwargs["workers"] == 1
    assert state.config_kwargs["factory"] is True
    assert state.config_kwargs["access_log"] is False
    assert not any(isinstance(event, tuple) and event[0] == "setsockopt"
                   and event[1][:2] == (socket.SOL_SOCKET, socket.SO_REUSEPORT)
                   for event in state.events)
    assert ("bind", ("127.0.0.1", 8339)) in state.events
    assert state.closed


def test_occupied_listener_fails_closed_and_releases_only_its_socket(service_owner):
    state = service_owner
    state.bind_error = OSError(errno.EADDRINUSE, "synthetic occupied listener")
    with pytest.raises(OSError) as error:
        service.main(state.args)
    assert error.value.errno == errno.EADDRINUSE
    assert "server_created" not in state.events
    assert state.closed


def test_failed_server_run_releases_its_listener_without_restarting(service_owner):
    state = service_owner
    state.run_error = RuntimeError("synthetic runner failure")
    with pytest.raises(RuntimeError, match="synthetic runner failure"):
        service.main(state.args)
    assert state.events.count("server_running") == 1
    assert state.closed


def test_invalid_settings_refuse_before_any_listener_is_created(service_owner, monkeypatch):
    state = service_owner

    def refuse():
        raise ValueError("synthetic invalid runtime settings")

    monkeypatch.setattr(gateway, "settings_from_env", refuse)
    with pytest.raises(ValueError, match="synthetic invalid runtime settings"):
        service.main(state.args)
    assert "socket_created" not in state.events
    assert "server_created" not in state.events


def test_active_listener_cannot_be_shared_by_another_process_local_bulkhead(service_owner):
    state = service_owner
    service.main(state.args)
    assert not any(isinstance(event, tuple) and event[0] == "setsockopt"
                   and event[1][:2] == (socket.SOL_SOCKET, socket.SO_REUSEPORT)
                   for event in state.events)


def test_normal_service_exit_releases_its_owned_listener(service_owner):
    state = service_owner
    service.main(state.args)
    assert state.closed
