"""Exact #1468 wire-fence discriminator; source-only and no issuer actions."""
import pytest
from control_plane import executive_privileged_broker as broker

class FiniteFrame:
    def __init__(self, raw: bytes): self.raw = raw
    def recv(self, size: int) -> bytes:
        part, self.raw = self.raw[:size], self.raw[size:]
        return part

def frame(schema: str, fragment: str) -> FiniteFrame:
    return FiniteFrame(("{\"schema\":\"" + schema + "\"," + fragment + "}\n").encode("utf-8"))

@pytest.mark.parametrize("schema", [
    broker.FORWARD_STATUS_REQUEST_SCHEMA,
    broker.FORWARD_ACTION_REQUEST_SCHEMA,
])
def test_forward_ambiguity_refused_before_broker_dispatch(schema):
    connection = frame(schema, "\"request_id\":\"foreign\",\"request_id\":\"original\"")
    with pytest.raises(broker.PrivilegedBrokerError, match="forward frame has duplicate fields"):
        broker._read_request_frame(connection)

@pytest.mark.parametrize("schema", [
    broker.FORWARD_STATUS_REQUEST_SCHEMA,
    broker.FORWARD_ACTION_REQUEST_SCHEMA,
])
def test_forward_unambiguous_frame_still_passes_parser(schema):
    raw = broker._read_request_frame(frame(schema, "\"request_id\":\"original\""))
    assert raw == {"schema": schema, "request_id": "original"}

def test_original_release_duplicate_error_unchanged():
    with pytest.raises(broker.PrivilegedBrokerError, match="release frame has duplicate fields"):
        broker._read_request_frame(frame("mastermind.executive_release_broker/v1",
             "\"request_id\":\"a\",\"request_id\":\"b\""))

@pytest.mark.parametrize("schema", [
    broker.FORWARD_STATUS_REQUEST_SCHEMA,
    broker.FORWARD_ACTION_REQUEST_SCHEMA,
])
def test_forward_duplicate_never_invokes_privileged_broker(schema):
    from types import SimpleNamespace
    import json
    class Socket(FiniteFrame):
        sent = b""
        def sendall(self, data: bytes) -> None:
            self.sent += data
    class SpyBroker:
        config = SimpleNamespace(allowed_peer_uids=(501,))
        def forward_status(self, *_args, **_kwargs):
            pytest.fail("duplicate forward status dispatched")
        def _handle_forward_outcome(self, *_args, **_kwargs):
            pytest.fail("duplicate forward action dispatched")
    connection = Socket(frame(schema, '"request_id":"foreign","request_id":"original"').raw)
    broker.serve_connection(SpyBroker(), connection, peer_resolver=lambda _: 501)
    response = json.loads(connection.sent)
    assert response["ok"] is False
    assert response["error"] == "REFUSED"
    assert response["detail"] == "forward frame has duplicate fields"

@pytest.mark.parametrize("forward_schema", [
    broker.FORWARD_STATUS_REQUEST_SCHEMA,
    broker.FORWARD_ACTION_REQUEST_SCHEMA,
])
def test_forward_first_schema_cannot_be_overwritten_by_legacy_schema(forward_schema):
    raw = FiniteFrame((
        '{"schema":"' + forward_schema + '",'
        '"schema":"' + broker.STATUS_REQUEST_SCHEMA + '",'
        '"request_id":"fixture"}\n'
    ).encode("utf-8"))
    with pytest.raises(broker.PrivilegedBrokerError, match="forward frame has duplicate fields"):
        broker._read_request_frame(raw)


def test_legacy_duplicate_schema_preserves_existing_parser_behavior():
    raw = FiniteFrame((
        '{"schema":"' + broker.STATUS_REQUEST_SCHEMA + '",'
        '"schema":"' + broker.STATUS_REQUEST_SCHEMA + '",'
        '"request_id":"fixture"}\n'
    ).encode("utf-8"))
    assert broker._read_request_frame(raw) == {
        "schema": broker.STATUS_REQUEST_SCHEMA,
        "request_id": "fixture",
    }
