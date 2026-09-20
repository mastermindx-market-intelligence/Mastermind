from __future__ import annotations

import dataclasses
import inspect
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from control_plane.executive_capacity_observation import CapacityObservationError
from ops.executive_os import provider_readiness, provider_worker_slots
from ops.executive_os.worker_capacity_observer import (
    WorkerCapacityObserver,
    WorkerCapacityObserverBinding,
    canonical_identity_digest,
)


NOW = datetime(2026, 9, 20, 8, 15, 0, tzinfo=UTC)
DIGESTS = {
    "release": "1" * 64,
    "operation": "2" * 64,
    "peer": "3" * 64,
    "realm": "4" * 64,
}
SECRET = b"credential-bytes-must-never-be-read"


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


@dataclasses.dataclass
class Harness:
    module: Any
    slot: provider_worker_slots.ProviderWorkerSlot
    binding: WorkerCapacityObserverBinding
    source_path: Path
    source: dict[str, Any]
    binary_identity: dict[str, Any]

    def write_source(self, value: dict[str, Any] | None = None, *, suffix: bytes = b"") -> None:
        self.source_path.chmod(0o600)
        self.source_path.write_bytes(_canonical(self.source if value is None else value) + suffix)
        self.source_path.chmod(0o400)

    def observer(self, **kwargs: Any) -> WorkerCapacityObserver:
        return WorkerCapacityObserver(
            self.binding,
            clock=lambda: NOW,
            **kwargs,
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    import ops.executive_os.worker_capacity_observer as module

    provider_home = tmp_path / "provider-home"
    provider_home.mkdir(mode=0o700)
    receipt = tmp_path / "readiness.json"
    receipt.write_text("{}", encoding="utf-8")
    receipt.chmod(0o400)
    auth = provider_home / "auth.json"
    auth.write_bytes(SECRET)
    auth.chmod(0o600)
    binary = tmp_path / "codex"
    binary.write_bytes(b"reviewed-binary")
    binary.chmod(0o555)

    canonical_slot = provider_worker_slots.get_slot("codex-pro-01")
    slot = dataclasses.replace(
        canonical_slot,
        worker_uid=os.getuid(),
        worker_gid=os.getgid(),
        worker_user="_mastermind_test",
        worker_group="_mastermind_test",
        provider_home=provider_home,
        readiness_receipt=receipt,
    )
    monkeypatch.setattr(module.worker_slots, "get_slot", lambda slot_id: slot if slot_id == slot.slot_id else None)
    monkeypatch.setattr(module, "_ROOT_UID", os.getuid())
    monkeypatch.setattr(module, "_ROOT_GID", os.getgid())

    binary_identity = {
        "path": str(binary),
        "version": "0.147.0",
        "sha256": "a" * 64,
        "team_identifier": "2DC432GLL2",
        "device": 7,
        "inode": 11,
        "uid": 0,
        "gid": 0,
        "mode": 0o555,
        "size": 123,
        "mtime_ns": 456,
        "ctime_ns": 789,
        "nlink": 1,
    }
    source_path = tmp_path / "worker-capacity-source.json"
    source = {
        "schema_version": "mastermind.executive_worker_capacity_source_config/v1",
        "host_ref": "host-" + "b" * 64,
        "capacity_capability_id": "codex_account",
        "broker_release_identity_digest": DIGESTS["release"],
        "broker_operation_identity_digest": DIGESTS["operation"],
        "broker_generation": 7,
        "executive_peer_policy_digest": DIGESTS["peer"],
        "worker_realm_metadata_policy_digest": DIGESTS["realm"],
        "provider_binary_identity_digest": canonical_identity_digest(binary_identity),
    }
    source_path.write_bytes(_canonical(source))
    source_path.chmod(0o400)
    binding = WorkerCapacityObserverBinding(
        slot_id=slot.slot_id,
        host_ref=source["host_ref"],
        source_config_path=source_path,
        binary_path=binary,
        broker_release_identity_digest=DIGESTS["release"],
        broker_operation_identity_digest=DIGESTS["operation"],
        broker_generation=7,
        executive_peer_policy_digest=DIGESTS["peer"],
        worker_realm_metadata_policy_digest=DIGESTS["realm"],
    )
    return Harness(module, slot, binding, source_path, source, binary_identity)


def _validated_observer(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> WorkerCapacityObserver:
    captured: dict[str, Any] = {}

    def binary_identity(path: Path) -> dict[str, Any]:
        captured["binary_path"] = path
        return dict(harness.binary_identity)

    def readiness(path: Path, **kwargs: Any) -> dict[str, Any]:
        captured["receipt_path"] = path
        captured.update(kwargs)
        return {"codex_binary": dict(harness.binary_identity)}

    monkeypatch.setattr(harness.module.provider_readiness, "current_binary_identity", binary_identity)
    monkeypatch.setattr(harness.module.provider_readiness, "validate_receipt_file", readiness)
    observer = harness.observer()
    observer._test_capture = captured  # type: ignore[attr-defined]
    return observer


def test_observe_emits_one_canonical_current_success_without_sensitive_fields(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = _validated_observer(harness, monkeypatch)

    observed = observer.observe()
    payload = observed.to_dict()

    assert payload == {
        "schema_version": "mastermind.executive_worker_capacity_observation/v1",
        "host_ref": harness.source["host_ref"],
        "capacity_capability_id": "codex_account",
        "realm_metadata_valid": True,
        "credential_present": True,
        "credential_metadata_valid": True,
        "provider_binary_attested": True,
        "broker_generation_ready": True,
        "source_config_digest": harness.module.worker_capacity_source_config_digest(
            harness.module.validate_worker_capacity_source_config(harness.source)
        ),
        "observed_at": "2026-09-20T08:15:00Z",
        "expires_at": "2026-09-20T08:15:15Z",
        "observation_digest": payload["observation_digest"],
    }
    rendered = json.dumps(payload, sort_keys=True)
    for forbidden in (
        str(harness.slot.auth_path),
        str(harness.slot.provider_home),
        str(harness.slot.readiness_receipt),
        harness.slot.worker_user,
        harness.slot.oauth_seat_ref,
        SECRET.decode("ascii"),
    ):
        assert forbidden not in rendered
    capture = observer._test_capture  # type: ignore[attr-defined]
    assert capture == {
        "binary_path": harness.binding.binary_path,
        "receipt_path": harness.slot.readiness_receipt,
        "auth_path": harness.slot.auth_path,
        "binary_path": harness.binding.binary_path,
        "expected_kind": harness.slot.default_credential_kind,
        "workspace_binding_class": harness.slot.workspace_binding_class,
        "worker_uid": harness.slot.worker_uid,
        "worker_gid": harness.slot.worker_gid,
    }


def test_observe_accepts_no_request_payload(harness: Harness) -> None:
    assert tuple(inspect.signature(WorkerCapacityObserver.observe).parameters) == ("self",)
    with pytest.raises(TypeError):
        harness.observer().observe({"host_ref": "attacker"})  # type: ignore[call-arg]


def test_credential_bytes_are_never_read(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = _validated_observer(harness, monkeypatch)
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def guarded_read_bytes(path: Path, *args: Any, **kwargs: Any) -> bytes:
        if path == harness.slot.auth_path:
            raise AssertionError("credential bytes were read")
        return original_read_bytes(path, *args, **kwargs)

    def guarded_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == harness.slot.auth_path:
            raise AssertionError("credential bytes were read")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    observer.observe()


@pytest.mark.parametrize(
    ("field", "replacement", "code"),
    [
        ("host_ref", "host-" + "c" * 64, "CAPACITY_OBSERVE_CONFIG_DRIFT"),
        ("capacity_capability_id", "codex_account_2", "CAPACITY_OBSERVE_CONFIG_DRIFT"),
        ("broker_release_identity_digest", "a" * 64, "CAPACITY_OBSERVE_CONFIG_DRIFT"),
        ("broker_operation_identity_digest", "b" * 64, "CAPACITY_OBSERVE_CONFIG_DRIFT"),
        ("executive_peer_policy_digest", "c" * 64, "CAPACITY_OBSERVE_CONFIG_DRIFT"),
        ("worker_realm_metadata_policy_digest", "d" * 64, "CAPACITY_OBSERVE_CONFIG_DRIFT"),
        ("broker_generation", 8, "CAPACITY_OBSERVE_GENERATION_UNREADY"),
        ("provider_binary_identity_digest", "e" * 64, "CAPACITY_OBSERVE_BINARY_UNATTESTED"),
    ],
)
def test_changed_identity_or_generation_refuses_before_observation(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: Any,
    code: str,
) -> None:
    observer = _validated_observer(harness, monkeypatch)
    changed = dict(harness.source)
    changed[field] = replacement
    harness.write_source(changed)

    with pytest.raises(CapacityObservationError) as raised:
        observer.observe()
    assert raised.value.code == code


@pytest.mark.parametrize("suffix", [b"\n", b" ", b"\x00"])
def test_source_config_must_be_exact_canonical_bytes(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
    suffix: bytes,
) -> None:
    observer = _validated_observer(harness, monkeypatch)
    harness.write_source(suffix=suffix)

    with pytest.raises(CapacityObservationError) as raised:
        observer.observe()
    assert raised.value.code == "CAPACITY_OBSERVE_CONFIG_DRIFT"


def test_source_config_must_be_root_owned_regular_mode_0400(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = _validated_observer(harness, monkeypatch)
    monkeypatch.setattr(harness.module, "_ROOT_UID", os.getuid() + 1)

    with pytest.raises(CapacityObservationError) as raised:
        observer.observe()
    assert raised.value.code == "CAPACITY_OBSERVE_CONFIG_DRIFT"


def test_source_config_symlink_refuses(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observer = _validated_observer(harness, monkeypatch)
    real = tmp_path / "real.json"
    real.write_bytes(_canonical(harness.source))
    real.chmod(0o400)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    observer = WorkerCapacityObserver(
        dataclasses.replace(harness.binding, source_config_path=link),
        clock=lambda: NOW,
    )

    with pytest.raises(CapacityObservationError) as raised:
        observer.observe()
    assert raised.value.code == "CAPACITY_OBSERVE_CONFIG_DRIFT"


def test_invalid_provider_home_metadata_refuses_realm(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = _validated_observer(harness, monkeypatch)
    harness.slot.provider_home.chmod(0o755)

    with pytest.raises(CapacityObservationError) as raised:
        observer.observe()
    assert raised.value.code == "CAPACITY_OBSERVE_REALM_INVALID"


def test_missing_credential_refuses_without_calling_readiness(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    def readiness(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(harness.module.provider_readiness, "validate_receipt_file", readiness)
    harness.slot.auth_path.unlink()

    with pytest.raises(CapacityObservationError) as raised:
        harness.observer().observe()
    assert raised.value.code == "CAPACITY_OBSERVE_CREDENTIAL_ABSENT"
    assert called is False


def test_invalid_credential_metadata_refuses(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.slot.auth_path.chmod(0o644)

    with pytest.raises(CapacityObservationError) as raised:
        harness.observer().observe()
    assert raised.value.code == "CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID"


def test_binary_attestation_failure_is_bounded(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        harness.module.provider_readiness,
        "current_binary_identity",
        lambda _path: (_ for _ in ()).throw(provider_readiness.ReadinessError("unsafe /private/path")),
    )

    with pytest.raises(CapacityObservationError) as raised:
        harness.observer().observe()
    assert raised.value.code == "CAPACITY_OBSERVE_BINARY_UNATTESTED"
    assert "/private/path" not in str(raised.value)


def test_stale_or_invalid_readiness_receipt_refuses_realm(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        harness.module.provider_readiness,
        "current_binary_identity",
        lambda _path: dict(harness.binary_identity),
    )
    monkeypatch.setattr(
        harness.module.provider_readiness,
        "validate_receipt_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            provider_readiness.ReadinessError("readiness_expired_or_insufficient_margin")
        ),
    )

    with pytest.raises(CapacityObservationError) as raised:
        harness.observer().observe()
    assert raised.value.code == "CAPACITY_OBSERVE_REALM_INVALID"


def test_readiness_receipt_must_bind_exact_current_binary(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        harness.module.provider_readiness,
        "current_binary_identity",
        lambda _path: dict(harness.binary_identity),
    )
    changed = dict(harness.binary_identity)
    changed["sha256"] = "f" * 64
    monkeypatch.setattr(
        harness.module.provider_readiness,
        "validate_receipt_file",
        lambda *_args, **_kwargs: {"codex_binary": changed},
    )

    with pytest.raises(CapacityObservationError) as raised:
        harness.observer().observe()
    assert raised.value.code == "CAPACITY_OBSERVE_BINARY_UNATTESTED"
