"""Keep optional forward exception resolution out of ordinary broker failures."""

import json
from types import SimpleNamespace

import pytest

from control_plane import executive_privileged_broker as broker


class Frame:
    def __init__(self, schema):
        self.raw = (json.dumps({"schema": schema}) + "\n").encode()
        self.sent = b""

    def recv(self, size):
        part, self.raw = self.raw[:size], self.raw[size:]
        return part

    def sendall(self, data):
        self.sent += data


@pytest.mark.parametrize("schema,method", [
    (broker.STATUS_REQUEST_SCHEMA, "query_status"),
    (broker.RECONCILE_REQUEST_SCHEMA, "reconcile_not_applied"),
    (broker.REQUEST_SCHEMA, "_handle_outcome"),
])
def test_ordinary_unexpected_failure_does_not_resolve_forward_error(monkeypatch, schema, method):
    resolved = []
    monkeypatch.setattr(broker, "_forward_error", lambda: resolved.append(True) or ())

    def fail(*args, **kwargs):
        raise RuntimeError("ordinary operation failed")

    owner = SimpleNamespace(config=SimpleNamespace(allowed_peer_uids=(501,)))
    setattr(owner, method, fail)
    connection = Frame(schema)
    with pytest.raises(RuntimeError, match="ordinary operation failed"):
        broker.serve_connection(owner, connection, peer_resolver=lambda _: 501)
    assert resolved == []
    assert connection.sent == b""


@pytest.mark.parametrize("schema,method", [
    (broker.FORWARD_STATUS_REQUEST_SCHEMA, "forward_status"),
    (broker.FORWARD_ACTION_REQUEST_SCHEMA, "_handle_forward_outcome"),
])
@pytest.mark.parametrize("unavailable", [False, True])
def test_forward_routes_keep_their_typed_refusal(monkeypatch, schema, method, unavailable):
    class ForwardRefusal(Exception):
        pass

    resolved = []
    monkeypatch.setattr(broker, "_forward_error",
                        lambda: resolved.append(True) or (ForwardRefusal,))

    def fail(*args, **kwargs):
        if unavailable:
            raise ImportError("optional module absent")
        raise ForwardRefusal("forward operation refused")

    owner = SimpleNamespace(config=SimpleNamespace(allowed_peer_uids=(501,)))
    setattr(owner, method, fail)
    connection = Frame(schema)
    broker.serve_connection(owner, connection, peer_resolver=lambda _: 501)
    response = json.loads(connection.sent)
    assert response["ok"] is False
    assert response["error"] == "FORWARD_REFUSED"
    assert response["detail"] == ("forward protocol module is unavailable" if unavailable
                                    else "forward operation refused")
    assert resolved == ([] if unavailable else [True])
