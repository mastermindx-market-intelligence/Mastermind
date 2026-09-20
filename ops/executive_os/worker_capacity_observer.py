"""Host-local evidence adapter for the frozen worker-capacity observation.

The adapter consumes existing root-owned broker/source bindings, the reviewed
provider-worker slot catalog and the existing provider-readiness receipt.  It
never accepts model-authored placement inputs, reads credential bytes, calls a
provider, ranks workers, reserves capacity, mutates Executive lifecycle state
or performs transport/retry work.

A later Worker Broker integration may call :meth:`WorkerCapacityObserver.observe`
only after its own peer, group, autonomy and busy-state admission succeeds.  The
method intentionally accepts no request payload, so a remote caller cannot
expand host, capability, provider, path, identity or time authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from control_plane.executive_capacity_observation import (
    CapacityObservationError,
    WorkerCapacityObservation,
)
from control_plane.executive_capacity_observation_producer import (
    INT64_MAX,
    WorkerCapacitySourceConfig,
    build_worker_capacity_observation,
    canonical_worker_capacity_source_config_json,
    validate_worker_capacity_readiness,
    validate_worker_capacity_source_config,
    worker_capacity_source_config_digest,
)
from control_plane.fs_security import FilesystemSecurityError, has_macos_acl
from ops.executive_os import capacity_broker_topology
from ops.executive_os import provider_readiness
from ops.executive_os import provider_worker_slots as worker_slots


_ROOT_UID = 0
_MAX_SOURCE_CONFIG_BYTES = 4_096
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _refuse(code: str) -> None:
    raise CapacityObservationError(code)


def _digest(value: object) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CapacityObservationError("CAPACITY_OBSERVE_CONFIG_DRIFT") from None


def canonical_identity_digest(value: Mapping[str, Any]) -> str:
    """Digest one already-accepted secret-free canonical identity object."""

    if not isinstance(value, Mapping):
        raise TypeError("value must be a mapping")
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_nlink),
        int(info.st_uid),
        int(info.st_gid),
        int(info.st_size),
        int(info.st_mtime_ns),
        int(info.st_ctime_ns),
    )


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        result[key] = value
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class _SourceConfigSnapshot:
    source: WorkerCapacitySourceConfig
    identity: tuple[int, ...]
    content_sha256: str


def source_config_storage_contract(*, worker_gid: int) -> tuple[int, int, int]:
    """Return the authority-owned, exact-slot-readable source-file contract."""

    if (
        isinstance(worker_gid, bool)
        or not isinstance(worker_gid, int)
        or worker_gid < 0
    ):
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return _ROOT_UID, worker_gid, 0o440


def _load_root_owned_source_config(
    path: Path, *, worker_gid: int
) -> _SourceConfigSnapshot:
    lexical = Path(path)
    if not lexical.is_absolute():
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    expected_uid, expected_gid, expected_mode = source_config_storage_contract(
        worker_gid=worker_gid
    )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if type(nofollow) is not int or nofollow <= 0:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    flags = (
        os.O_RDONLY
        | nofollow
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(lexical, flags)
    except OSError:
        raise CapacityObservationError("CAPACITY_OBSERVE_CONFIG_DRIFT") from None
    try:
        try:
            before = os.fstat(descriptor)
        except OSError:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != expected_uid
            or before.st_gid != expected_gid
            or stat.S_IMODE(before.st_mode) != expected_mode
            or before.st_nlink != 1
            or not 0 < before.st_size <= _MAX_SOURCE_CONFIG_BYTES
        ):
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        try:
            if has_macos_acl(
                lexical,
                expected_identity=before,
                descriptor=descriptor,
            ):
                _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        except FilesystemSecurityError:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")

        chunks: list[bytes] = []
        total = 0
        while total <= _MAX_SOURCE_CONFIG_BYTES:
            try:
                chunk = os.read(
                    descriptor,
                    min(65_536, _MAX_SOURCE_CONFIG_BYTES + 1 - total),
                )
            except OSError:
                _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > _MAX_SOURCE_CONFIG_BYTES:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        try:
            after = os.fstat(descriptor)
        except OSError:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        if _identity(before) != _identity(after):
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    finally:
        try:
            os.close(descriptor)
        except OSError:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")

    raw = b"".join(chunks)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CapacityObservationError("CAPACITY_OBSERVE_CONFIG_DRIFT") from None
    source = validate_worker_capacity_source_config(value)
    if raw != canonical_worker_capacity_source_config_json(source):
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return _SourceConfigSnapshot(
        source=source,
        identity=_identity(before),
        content_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _revalidate_source_config(
    path: Path,
    *,
    worker_gid: int,
    expected: _SourceConfigSnapshot,
) -> None:
    current = _load_root_owned_source_config(path, worker_gid=worker_gid)
    if current != expected:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")


def _format_observed_at(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    try:
        normalized = value.astimezone(UTC).replace(microsecond=0)
    except (OverflowError, ValueError):
        raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID") from None
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def _expected_capability_id(slot_id: str) -> str:
    personal_slots = tuple(
        slot.slot_id
        for slot in worker_slots.all_slots()
        if slot.oauth_seat_ref is not None
    )
    capability_ids = tuple(capacity_broker_topology.PERSONAL_CAPABILITY_IDS)
    if len(personal_slots) != len(capability_ids):
        _refuse("CAPACITY_OBSERVE_REALM_INVALID")
    mapping = dict(zip(personal_slots, capability_ids))
    try:
        return mapping[slot_id]
    except KeyError:
        raise CapacityObservationError("CAPACITY_OBSERVE_REALM_INVALID") from None


def _validate_realm(
    slot: worker_slots.ProviderWorkerSlot,
) -> tuple[int, ...]:
    try:
        info = slot.provider_home.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != slot.worker_uid
            or info.st_gid != slot.worker_gid
            or stat.S_IMODE(info.st_mode) & 0o077
        ):
            _refuse("CAPACITY_OBSERVE_REALM_INVALID")
        if has_macos_acl(slot.provider_home, expected_identity=info):
            _refuse("CAPACITY_OBSERVE_REALM_INVALID")
        return _identity(info)
    except (OSError, FilesystemSecurityError):
        _refuse("CAPACITY_OBSERVE_REALM_INVALID")


def _read_current_credential_identity(
    slot: worker_slots.ProviderWorkerSlot,
) -> dict[str, int]:
    try:
        slot.auth_path.lstat()
    except FileNotFoundError:
        _refuse("CAPACITY_OBSERVE_CREDENTIAL_ABSENT")
    except OSError:
        _refuse("CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID")
    try:
        identity = provider_readiness.current_auth_identity(
            slot.auth_path,
            worker_uid=slot.worker_uid,
            worker_gid=slot.worker_gid,
        )
    except (OSError, provider_readiness.ReadinessError):
        _refuse("CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID")
    if not isinstance(identity, dict):
        _refuse("CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID")
    return dict(identity)


def _read_current_binary_identity(path: Path) -> dict[str, Any]:
    try:
        value = provider_readiness.current_binary_identity(path)
    except (OSError, provider_readiness.ReadinessError):
        raise CapacityObservationError("CAPACITY_OBSERVE_BINARY_UNATTESTED") from None
    if not isinstance(value, dict):
        _refuse("CAPACITY_OBSERVE_BINARY_UNATTESTED")
    return dict(value)


def _validate_readiness_receipt(
    *,
    slot: worker_slots.ProviderWorkerSlot,
    binary_path: Path,
    binary_identity: Mapping[str, Any],
    credential_identity: Mapping[str, int],
) -> None:
    try:
        receipt = provider_readiness.validate_receipt_file(
            slot.readiness_receipt,
            auth_path=slot.auth_path,
            binary_path=binary_path,
            expected_kind=slot.default_credential_kind,
            workspace_binding_class=slot.workspace_binding_class,
            worker_uid=slot.worker_uid,
            worker_gid=slot.worker_gid,
        )
    except (OSError, provider_readiness.ReadinessError) as exc:
        code = str(exc)
        if "binary" in code or "team" in code:
            _refuse("CAPACITY_OBSERVE_BINARY_UNATTESTED")
        if "credential" in code or "auth" in code:
            _refuse("CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID")
        _refuse("CAPACITY_OBSERVE_REALM_INVALID")
    if not isinstance(receipt, dict):
        _refuse("CAPACITY_OBSERVE_REALM_INVALID")
    if receipt.get("codex_binary") != dict(binary_identity):
        _refuse("CAPACITY_OBSERVE_BINARY_UNATTESTED")
    if receipt.get("credential_lstat") != dict(credential_identity):
        _refuse("CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID")


@dataclasses.dataclass(frozen=True, slots=True)
class WorkerCapacityObserverBinding:
    """Immutable broker-local facts sourced outside the observe request."""

    slot_id: str
    host_ref: str
    source_config_path: Path
    binary_path: Path
    broker_release_identity_digest: str
    broker_operation_identity_digest: str
    broker_generation: int
    executive_peer_policy_digest: str
    worker_realm_metadata_policy_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.slot_id, str) or not self.slot_id:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        if not isinstance(self.host_ref, str) or not self.host_ref:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        for path in (self.source_config_path, self.binary_path):
            if not isinstance(path, Path) or not path.is_absolute():
                _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        for value in (
            self.broker_release_identity_digest,
            self.broker_operation_identity_digest,
            self.executive_peer_policy_digest,
            self.worker_realm_metadata_policy_digest,
        ):
            _digest(value)
        if (
            type(self.broker_generation) is not int
            or not 0 <= self.broker_generation <= INT64_MAX
        ):
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")


class WorkerCapacityObserver:
    """Build one short-lived observation from current host-local owners."""

    def __init__(
        self,
        binding: WorkerCapacityObserverBinding,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(binding, WorkerCapacityObserverBinding):
            raise TypeError("binding must be WorkerCapacityObserverBinding")
        self.binding = binding
        self.clock = clock or (lambda: datetime.now(UTC))

    def observe(self) -> WorkerCapacityObservation:
        try:
            slot = worker_slots.get_slot(self.binding.slot_id)
        except Exception:
            raise CapacityObservationError("CAPACITY_OBSERVE_REALM_INVALID") from None
        if not isinstance(slot, worker_slots.ProviderWorkerSlot):
            _refuse("CAPACITY_OBSERVE_REALM_INVALID")

        expected_capability = _expected_capability_id(slot.slot_id)
        realm_identity = _validate_realm(slot)
        source_snapshot = _load_root_owned_source_config(
            self.binding.source_config_path, worker_gid=slot.worker_gid
        )
        source = source_snapshot.source
        if (
            source.host_ref != self.binding.host_ref
            or source.capacity_capability_id != expected_capability
            or source.broker_release_identity_digest
            != self.binding.broker_release_identity_digest
            or source.broker_operation_identity_digest
            != self.binding.broker_operation_identity_digest
            or source.executive_peer_policy_digest
            != self.binding.executive_peer_policy_digest
            or source.worker_realm_metadata_policy_digest
            != self.binding.worker_realm_metadata_policy_digest
        ):
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
        if source.broker_generation != self.binding.broker_generation:
            _refuse("CAPACITY_OBSERVE_GENERATION_UNREADY")

        credential_identity = _read_current_credential_identity(slot)
        binary_identity = _read_current_binary_identity(self.binding.binary_path)
        if (
            canonical_identity_digest(binary_identity)
            != source.provider_binary_identity_digest
        ):
            _refuse("CAPACITY_OBSERVE_BINARY_UNATTESTED")
        _validate_readiness_receipt(
            slot=slot,
            binary_path=self.binding.binary_path,
            binary_identity=binary_identity,
            credential_identity=credential_identity,
        )
        if _validate_realm(slot) != realm_identity:
            _refuse("CAPACITY_OBSERVE_REALM_INVALID")
        if _read_current_credential_identity(slot) != credential_identity:
            _refuse("CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID")
        if _read_current_binary_identity(self.binding.binary_path) != binary_identity:
            _refuse("CAPACITY_OBSERVE_BINARY_UNATTESTED")

        readiness = validate_worker_capacity_readiness(
            {
                "realm_metadata_valid": True,
                "credential_present": True,
                "credential_metadata_valid": True,
                "provider_binary_attested": True,
                "broker_generation_ready": True,
            }
        )
        try:
            observed_at = _format_observed_at(self.clock())
        except CapacityObservationError:
            raise
        except Exception:
            raise CapacityObservationError("CAPACITY_OBSERVE_INTERNAL") from None
        _revalidate_source_config(
            self.binding.source_config_path,
            worker_gid=slot.worker_gid,
            expected=source_snapshot,
        )
        return build_worker_capacity_observation(
            source_config=source,
            readiness=readiness,
            observed_at=observed_at,
        )


__all__ = [
    "WorkerCapacityObserver",
    "WorkerCapacityObserverBinding",
    "canonical_identity_digest",
    "source_config_storage_contract",
]
