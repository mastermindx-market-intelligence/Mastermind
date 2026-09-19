from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from control_plane import executive_privileged_broker as broker_module
from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    canonical_request_bytes,
    validate_request,
)
from control_plane.executive_privileged_broker import (
    BROKER_CONFIG_SCHEMA,
    BrokerTrustError,
    EffectUnknownError,
    PeerAuthorizationError,
    PrivilegedActionBroker,
    PrivilegedBrokerConfig,
    RequestIdConflictError,
    serve_connection,
)


def _raw(action: str = "executive.services.start", request_id: str = "req-001", args=None):
    return {"schema": REQUEST_SCHEMA, "request_id": request_id, "action": action, "args": args or {}}


class FakeExecutor:
    def __init__(self, *, returncode: int = 0, stdout: bytes = b"READY\n", stderr: bytes = b""):
        self.calls = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, argv, *, cwd, env, timeout):
        self.calls.append((tuple(argv), Path(cwd), dict(env), timeout))
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def _broker(tmp_path: Path, executor=None) -> PrivilegedActionBroker:
    release = tmp_path / ("a" * 40)
    release.mkdir()
    receipt_root = tmp_path / "receipts"
    config = PrivilegedBrokerConfig(
        release_root=release,
        receipt_root=receipt_root,
        allowed_peer_uids=(501, 450),
        timeout_seconds=30,
        broker_version="test",
    )
    return PrivilegedActionBroker(
        config,
        executor=executor or FakeExecutor(),
        require_root=False,
        trust_validator=lambda _config: None,
    )


def test_trusted_effect_paths_cover_every_root_actuator() -> None:
    assert broker_module._TRUSTED_EFFECT_PATHS == (
        "ops/executive_os/service-control.sh",
        "ops/executive_os/provision-worker-auth.sh",
        "ops/executive_os/secondary_host_power_policy.py",
    )


def test_peer_uid_must_be_allowlisted_before_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    with pytest.raises(PeerAuthorizationError):
        broker.handle(_raw(), peer_uid=502)
    assert executor.calls == []


def test_power_policy_action_uses_existing_receipt_and_replay_owner(tmp_path: Path) -> None:
    executor = FakeExecutor(stdout=b'{"autorestart":1,"scope":"charger","sleep":0}\n')
    broker = _broker(tmp_path, executor)

    first = broker.handle(
        _raw("executive.host.prepare_secondary_power_policy", "req-power-001"),
        peer_uid=501,
    )
    second = broker.handle(
        _raw("executive.host.prepare_secondary_power_policy", "req-power-001"),
        peer_uid=501,
    )

    assert first == second
    assert first["effect_class"] == "HOST_POWER_POLICY"
    assert first["action"] == "executive.host.prepare_secondary_power_policy"
    assert first["outcome"] == "SUCCEEDED"
    assert len(executor.calls) == 1
    argv = executor.calls[0][0]
    assert argv[:4] == ("/usr/bin/python3", "-I", "-S", "-B")
    assert argv[4].endswith("/ops/executive_os/secondary_host_power_policy.py")


def test_success_persists_terminal_receipt_and_replays_without_second_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    first = broker.handle(_raw(), peer_uid=501)
    second = broker.handle(_raw(), peer_uid=501)
    assert first == second
    assert first["outcome"] == "SUCCEEDED"
    assert first["exit_code"] == 0
    assert len(executor.calls) == 1
    receipt = broker.receipt_path("req-001")
    assert receipt.is_file()
    assert not broker.inflight_path("req-001").exists()
    assert json.loads(receipt.read_text()) == first


def test_wire_response_marks_fresh_and_replayed_successes(tmp_path: Path) -> None:
    class MemoryConnection:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.sent = bytearray()

        def recv(self, _size: int) -> bytes:
            payload, self.payload = self.payload, b""
            return payload

        def sendall(self, payload: bytes) -> None:
            self.sent.extend(payload)

    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    payload = (json.dumps(_raw(), sort_keys=True, separators=(",", ":")) + "\n").encode()

    first = MemoryConnection(payload)
    serve_connection(broker, first, peer_resolver=lambda _connection: 501)
    first_response = json.loads(bytes(first.sent))
    assert first_response["ok"] is True
    assert first_response["replayed"] is False

    second = MemoryConnection(payload)
    serve_connection(broker, second, peer_resolver=lambda _connection: 501)
    second_response = json.loads(bytes(second.sent))
    assert second_response["ok"] is True
    assert second_response["replayed"] is True
    assert len(executor.calls) == 1


def test_terminal_receipt_from_other_release_conflicts_without_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    path = broker.receipt_path("req-001")
    value = json.loads(path.read_text())
    value["release_sha"] = "f" * 40
    path.write_text(json.dumps(value) + "\n")

    with pytest.raises(RequestIdConflictError, match="release"):
        broker.handle(_raw(), peer_uid=501)
    assert len(executor.calls) == 1


def test_inflight_marker_from_other_release_conflicts_without_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    validated = validate_request(_raw())
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    broker.inflight_path("req-001").write_text(
        json.dumps({
            "schema": "mastermind.executive_privileged_action_inflight.v1",
            "request_id": "req-001",
            "request_sha256": digest,
            "release_sha": "foreign-release",
        }) + "\n"
    )
    with pytest.raises(RequestIdConflictError, match="release"):
        broker.handle(_raw(), peer_uid=501)
    assert executor.calls == []


def test_changed_request_reusing_terminal_id_refuses_without_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    with pytest.raises(RequestIdConflictError):
        broker.handle(_raw("executive.services.stop"), peer_uid=501)
    assert len(executor.calls) == 1


def test_stale_inflight_same_request_is_effect_unknown_without_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    validated = validate_request(_raw())
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    broker.inflight_path("req-001").write_text(json.dumps({"schema": "mastermind.executive_privileged_action_inflight.v1", "request_id": "req-001", "request_sha256": digest, "release_sha": broker.config.release_root.name}) + "\n")
    with pytest.raises(EffectUnknownError):
        broker.handle(_raw(), peer_uid=501)
    assert executor.calls == []


def test_stale_inflight_different_request_hash_is_conflict(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.inflight_path("req-001").write_text(json.dumps({"schema": "mastermind.executive_privileged_action_inflight.v1", "request_id": "req-001", "request_sha256": "0" * 64, "release_sha": broker.config.release_root.name}) + "\n")
    with pytest.raises(RequestIdConflictError):
        broker.handle(_raw(), peer_uid=501)
    assert executor.calls == []


def test_nonzero_child_is_failed_and_external_text_is_bounded_and_redacted(tmp_path: Path) -> None:
    secret = "sk-ant-" + "x" * 40
    executor = FakeExecutor(returncode=65, stderr=("bad credential " + secret + "\n").encode())
    broker = _broker(tmp_path, executor)
    result = broker.handle(_raw(), peer_uid=501)
    assert result["outcome"] == "FAILED"
    assert result["exit_code"] == 65
    assert secret not in json.dumps(result)
    assert "<redacted>" in result["stderr_excerpt"]
    assert len(result["stderr_excerpt"]) <= 320


def test_receipt_failure_after_spawn_preserves_inflight_as_effect_unknown(tmp_path: Path, monkeypatch) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)

    def fail_receipt(*_args, **_kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(broker, "_write_terminal_receipt", fail_receipt)
    with pytest.raises(EffectUnknownError, match="terminal receipt"):
        broker.handle(_raw(), peer_uid=501)
    assert len(executor.calls) == 1
    assert broker.inflight_path("req-001").is_file()


def test_executor_oserror_after_marker_is_effect_unknown_and_preserves_marker(tmp_path: Path) -> None:
    class OSErrorExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, argv, *, cwd, env, timeout):
            self.calls += 1
            raise OSError("post-spawn transport failure")

    executor = OSErrorExecutor()
    broker = _broker(tmp_path, executor)
    with pytest.raises(EffectUnknownError, match="effect is unknown"):
        broker.handle(_raw(), peer_uid=501)
    assert executor.calls == 1
    assert broker.inflight_path("req-001").is_file()


def test_terminal_and_inflight_request_ids_use_disjoint_namespaces(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(request_id="foo.inflight"), peer_uid=501)
    result = broker.handle(_raw(request_id="foo"), peer_uid=501)
    assert result["outcome"] == "SUCCEEDED"
    assert len(executor.calls) == 2
    assert broker.receipt_path("foo.inflight") != broker.inflight_path("foo")


def test_default_executor_timeout_kills_the_entire_spawned_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "descendant.pid"
    child = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        f"open({str(marker)!r}, 'w').write(str(p.pid)); "
        "time.sleep(60)"
    )
    descendant_pid = None
    try:
        with pytest.raises(EffectUnknownError, match="timed out"):
            broker_module._default_executor(
                [sys.executable, "-c", child], cwd=tmp_path, env=os.environ, timeout=1
            )
        deadline = time.time() + 2
        while not marker.exists() and time.time() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        descendant_pid = int(marker.read_text())
        deadline = time.time() + 2
        while time.time() < deadline:
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        with pytest.raises(ProcessLookupError):
            os.kill(descendant_pid, 0)
    finally:
        if descendant_pid is not None:
            try:
                os.kill(descendant_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_run_broker_exits_when_idle_and_survives_one_client_socket_error(tmp_path: Path, monkeypatch) -> None:
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _value):
            pass

    class FakeListener:
        def __init__(self) -> None:
            self.timeout = None
            self.accepts = 0

        def settimeout(self, value):
            self.timeout = value

        def accept(self):
            self.accepts += 1
            if self.accepts == 1:
                return FakeConnection(), None
            raise TimeoutError("idle")

    config = _broker(tmp_path).config
    listener = FakeListener()
    monkeypatch.setattr(broker_module, "PrivilegedActionBroker", lambda _config: object())
    monkeypatch.setattr(
        broker_module, "serve_connection", lambda *_args, **_kwargs: (_ for _ in ()).throw(BrokenPipeError())
    )
    broker_module.run_broker(config, activated_socket=listener)
    assert listener.timeout == broker_module._BROKER_IDLE_TIMEOUT_SECONDS
    assert listener.accepts == 2


def test_config_mapping_requires_fixed_production_roots_and_control_peer() -> None:
    release = "/Library/Application Support/MastermindExecutive/releases/" + "a" * 40
    config = PrivilegedBrokerConfig.from_mapping(
        {
            "schema": BROKER_CONFIG_SCHEMA,
            "release_root": release,
            "receipt_root": "/var/db/mastermind-executive/privileged-actions/receipts",
            "allowed_peer_uids": [450, 501],
            "timeout_seconds": 120,
            "broker_version": "1",
        }
    )
    assert config.release_root == Path(release)
    assert config.allowed_peer_uids == (450, 501)


@pytest.mark.parametrize(
    "patch",
    [
        {"release_root": "/tmp/release"},
        {"receipt_root": "/tmp/receipts"},
        {"allowed_peer_uids": [501]},
        {"allowed_peer_uids": [0, 450, 501]},
        {"timeout_seconds": 0},
    ],
)
def test_config_mapping_refuses_unreviewed_production_policy(patch: dict[str, object]) -> None:
    raw = {
        "schema": BROKER_CONFIG_SCHEMA,
        "release_root": "/Library/Application Support/MastermindExecutive/releases/" + "a" * 40,
        "receipt_root": "/var/db/mastermind-executive/privileged-actions/receipts",
        "allowed_peer_uids": [450, 501],
        "timeout_seconds": 120,
        "broker_version": "1",
    }
    raw.update(patch)
    with pytest.raises(ValueError):
        PrivilegedBrokerConfig.from_mapping(raw)


def _status(request_id: str = "req-001") -> dict[str, object]:
    return {"schema": STATUS_REQUEST_SCHEMA, "request_id": request_id}


def _write_inflight_marker(broker: PrivilegedActionBroker, request_id: str, *, digest: str, release_sha: str | None = None) -> None:
    broker.inflight_path(request_id).write_text(
        json.dumps(
            {
                "schema": "mastermind.executive_privileged_action_inflight.v1",
                "request_id": request_id,
                "request_sha256": digest,
                "release_sha": release_sha or broker.config.release_root.name,
            }
        )
        + "\n"
    )


def test_status_terminal_returns_stored_receipt_without_respawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    receipt = broker.handle(_raw(), peer_uid=501)

    projection = broker.query_status(_status(), peer_uid=501)

    assert projection["status"] == "TERMINAL"
    assert projection["receipt"] == receipt
    assert len(executor.calls) == 1


def test_status_inflight_marker_is_effect_unknown_without_repair(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    digest = hashlib.sha256(canonical_request_bytes(validate_request(_raw()))).hexdigest()
    _write_inflight_marker(broker, "req-001", digest=digest)

    projection = broker.query_status(_status(), peer_uid=501)

    assert projection["status"] == "EFFECT_UNKNOWN"
    assert projection["marker_release_sha"] == broker.config.release_root.name
    assert broker.inflight_path("req-001").is_file()
    assert executor.calls == []


def test_status_not_found_creates_nothing(tmp_path: Path) -> None:
    broker = _broker(tmp_path)

    projection = broker.query_status(_status("req-ghost"), peer_uid=501)

    assert projection == {
        "status": "NOT_FOUND",
        "request_id": "req-ghost",
        "installed_release_sha": broker.config.release_root.name,
    }
    assert not broker.receipt_path("req-ghost").exists()
    assert not broker.inflight_path("req-ghost").exists()


def test_status_terminal_wins_over_leftover_marker(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    receipt = broker.handle(_raw(), peer_uid=501)
    digest = hashlib.sha256(canonical_request_bytes(validate_request(_raw()))).hexdigest()
    _write_inflight_marker(broker, "req-001", digest=digest)

    projection = broker.query_status(_status(), peer_uid=501)

    assert projection["status"] == "TERMINAL"
    assert projection["receipt"] == receipt
    assert len(executor.calls) == 1


def test_status_permits_foreign_release_readback_without_reinterpreting_as_current(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    path = broker.receipt_path("req-001")
    value = json.loads(path.read_text())
    value["release_sha"] = "f" * 40
    path.write_text(json.dumps(value) + "\n")

    projection = broker.query_status(_status(), peer_uid=501)

    assert projection["status"] == "TERMINAL"
    assert projection["receipt"]["release_sha"] == "f" * 40
    assert projection["installed_release_sha"] == broker.config.release_root.name
    assert projection["installed_release_sha"] != projection["receipt"]["release_sha"]
    assert len(executor.calls) == 1


def test_status_malformed_receipt_digest_fails_closed_without_effect(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    path = broker.receipt_path("req-001")
    value = json.loads(path.read_text())
    value["request_sha256"] = "not-a-valid-digest"
    path.write_text(json.dumps(value) + "\n")

    with pytest.raises(BrokerTrustError):
        broker.query_status(_status(), peer_uid=501)
    assert len(executor.calls) == 1  # Only the fixture-producing effect, not the status query.


def test_status_malformed_receipt_release_field_fails_closed_without_effect(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    path = broker.receipt_path("req-001")
    value = json.loads(path.read_text())
    value["release_sha"] = 12345
    path.write_text(json.dumps(value) + "\n")

    with pytest.raises(BrokerTrustError):
        broker.query_status(_status(), peer_uid=501)
    assert len(executor.calls) == 1  # Only the fixture-producing effect, not the status query.


def test_status_malformed_marker_json_fails_closed_without_effect(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.inflight_path("req-001").write_text("not json")

    with pytest.raises(BrokerTrustError):
        broker.query_status(_status(), peer_uid=501)
    assert executor.calls == []


def test_status_malformed_marker_digest_fails_closed_without_effect(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.inflight_path("req-001").write_text(
        json.dumps(
            {
                "schema": "mastermind.executive_privileged_action_inflight.v1",
                "request_id": "req-001",
                "request_sha256": "not-a-valid-digest",
                "release_sha": broker.config.release_root.name,
            }
        )
        + "\n"
    )

    with pytest.raises(BrokerTrustError):
        broker.query_status(_status(), peer_uid=501)
    assert executor.calls == []


def test_status_rejects_unauthorized_peer_before_request_validation(tmp_path: Path) -> None:
    broker = _broker(tmp_path)
    malformed = {"schema": "bogus-schema", "request_id": "../etc/passwd"}

    with pytest.raises(PeerAuthorizationError):
        broker.query_status(malformed, peer_uid=502)


@pytest.mark.parametrize(
    "malformed_status",
    [
        {"schema": STATUS_REQUEST_SCHEMA, "request_id": "../etc/passwd"},
        {"schema": STATUS_REQUEST_SCHEMA, "request_id": "req; rm -rf /"},
        {"schema": STATUS_REQUEST_SCHEMA, "request_id": "req-001", "action": "executive.services.start"},
        {"schema": REQUEST_SCHEMA, "request_id": "req-001"},
    ],
)
def test_status_traversal_shell_and_extra_keys_refuse_before_lookup(
    tmp_path: Path, malformed_status: dict[str, object]
) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    with pytest.raises(Exception):
        broker.query_status(malformed_status, peer_uid=501)
    assert executor.calls == []


def test_serve_connection_dispatches_status_schema(tmp_path: Path) -> None:
    class MemoryConnection:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload
            self.sent = bytearray()

        def recv(self, _size: int) -> bytes:
            payload, self.payload = self.payload, b""
            return payload

        def sendall(self, payload: bytes) -> None:
            self.sent.extend(payload)

    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)

    payload = (json.dumps(_status(), sort_keys=True, separators=(",", ":")) + "\n").encode()
    connection = MemoryConnection(payload)
    serve_connection(broker, connection, peer_resolver=lambda _connection: 501)

    response = json.loads(bytes(connection.sent))
    assert response["ok"] is True
    assert response["query"] is True
    assert response["status"] == "TERMINAL"
    assert len(executor.calls) == 1


def test_serve_connection_status_rejects_unauthorized_peer_before_body_read(tmp_path: Path) -> None:
    class ExplodingConnection:
        def __init__(self) -> None:
            self.sent = b""

        def recv(self, _size: int) -> bytes:
            raise AssertionError("body must not be read for an unauthorized peer")

        def sendall(self, payload: bytes) -> None:
            self.sent = payload

    broker = _broker(tmp_path)
    connection = ExplodingConnection()
    serve_connection(broker, connection, peer_resolver=lambda _connection: 999)

    response = json.loads(connection.sent)
    assert response["ok"] is False
    assert response["error"] == "PEER_UNAUTHORIZED"


def test_real_socket_effect_then_status_share_one_executor_call(tmp_path: Path, short_socket_root: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    socket_path = short_socket_root / "broker.sock"

    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(2)

    def send(payload: bytes) -> dict[str, object]:
        def serve_one() -> None:
            connection, _address = listener.accept()
            with connection:
                serve_connection(broker, connection, peer_resolver=lambda _connection: 501)

        thread = threading.Thread(target=serve_one)
        thread.start()
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(socket_path))
        client.sendall(payload)
        data = b""
        while not data.endswith(b"\n"):
            data += client.recv(4096)
        client.close()
        thread.join(2)
        return json.loads(data)

    try:
        effect_payload = (json.dumps(_raw(), sort_keys=True, separators=(",", ":")) + "\n").encode()
        effect_response = send(effect_payload)
        assert effect_response["ok"] is True
        assert effect_response["replayed"] is False

        status_payload = (json.dumps(_status(), sort_keys=True, separators=(",", ":")) + "\n").encode()
        status_response = send(status_payload)
        assert status_response["ok"] is True
        assert status_response["query"] is True
        assert status_response["status"] == "TERMINAL"
        assert status_response["receipt"] == effect_response["receipt"]
        assert len(executor.calls) == 1
    finally:
        listener.close()


@pytest.mark.parametrize("field,value", [("release_sha", "not-a-git-sha"), ("outcome", "RUNNING"), ("outcome", None)])
def test_status_rejects_corrupt_terminal_metadata(tmp_path: Path, field: str, value) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    path = broker.receipt_path("req-001")
    receipt = json.loads(path.read_text())
    if value is None:
        receipt.pop(field)
    else:
        receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(BrokerTrustError):
        broker.query_status(_status(), peer_uid=501)
    assert len(executor.calls) == 1


@pytest.mark.parametrize("state_kind", ["receipt", "inflight"])
@pytest.mark.parametrize("entry_kind", ["dangling", "loop"])
@pytest.mark.parametrize("query", [True, False])
def test_malformed_state_entry_never_becomes_absence_or_reexecution(
    tmp_path: Path, state_kind: str, entry_kind: str, query: bool
) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    path = (broker.receipt_path if state_kind == "receipt" else broker.inflight_path)("req-001")
    path.symlink_to(path if entry_kind == "loop" else tmp_path / "missing-state.json")
    with pytest.raises(BrokerTrustError):
        if query:
            broker.query_status(_status(), peer_uid=501)
        else:
            broker.handle(_raw(), peer_uid=501)
    assert executor.calls == []
    assert path.is_symlink()


def test_replay_rejects_corrupt_terminal_receipt_without_second_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    receipt_path = broker.receipt_path("req-001")
    receipt = json.loads(receipt_path.read_text())
    receipt["stdout_sha256"] = "not-a-valid-digest"
    receipt_path.write_text(json.dumps(receipt) + "\n")

    with pytest.raises(BrokerTrustError, match="terminal receipt"):
        broker.handle(_raw(), peer_uid=501)
    assert len(executor.calls) == 1


def test_status_rejects_incomplete_terminal_receipt_shape(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.handle(_raw(), peer_uid=501)
    receipt_path = broker.receipt_path("req-001")
    receipt = json.loads(receipt_path.read_text())
    receipt.pop("effect_class")
    receipt_path.write_text(json.dumps(receipt) + "\n")

    with pytest.raises(BrokerTrustError, match="terminal receipt"):
        broker.query_status(_status(), peer_uid=501)
    assert len(executor.calls) == 1
