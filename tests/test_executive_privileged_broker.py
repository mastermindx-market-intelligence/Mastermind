from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from control_plane.executive_privileged_action import REQUEST_SCHEMA, canonical_request_bytes, validate_request
from control_plane.executive_privileged_broker import (
    BROKER_CONFIG_SCHEMA,
    EffectUnknownError,
    PeerAuthorizationError,
    PrivilegedActionBroker,
    PrivilegedBrokerConfig,
    RequestIdConflictError,
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
    release = tmp_path / "release"
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


def test_peer_uid_must_be_allowlisted_before_spawn(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    with pytest.raises(PeerAuthorizationError):
        broker.handle(_raw(), peer_uid=502)
    assert executor.calls == []


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
    broker.inflight_path("req-001").write_text(json.dumps({"schema": "mastermind.executive_privileged_action_inflight.v1", "request_id": "req-001", "request_sha256": digest}) + "\n")
    with pytest.raises(EffectUnknownError):
        broker.handle(_raw(), peer_uid=501)
    assert executor.calls == []


def test_stale_inflight_different_request_hash_is_conflict(tmp_path: Path) -> None:
    executor = FakeExecutor()
    broker = _broker(tmp_path, executor)
    broker.inflight_path("req-001").write_text(json.dumps({"schema": "mastermind.executive_privileged_action_inflight.v1", "request_id": "req-001", "request_sha256": "0" * 64}) + "\n")
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
