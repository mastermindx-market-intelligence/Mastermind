"""Read CF2F identity joins from the existing immutable Worker quota registry.

This is identity evidence only, NOT eligibility, admission, selection, a source
closure receipt, provider-capacity normalization or a host registry. It writes
nothing, acquires no provider/broker observations and never enumerates Workers.
The caller must still match current Provider Control/broker evidence and perform
canonical transactional revalidation before any claim or remote effect.

The three-candidate bound is the existing CF2F acquisition ceiling, not a fleet
size limit. A wider accepted acquisition contract must precede increasing it.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Sequence
from itertools import islice
from typing import Any, Protocol

from control_plane.executive_host_pressure import HOST_REF_RE

JOIN_SCHEMA = "mastermind.executive_capacity_join/v1"
PROVIDER_CAPACITY_SCHEMA = "mastermind.provider_capacity.v1"
MAX_CANDIDATES = 3
_JOIN_KEYS = frozenset({"schema", "host_ref", "capacity_capability_id",
                       "provider_capacity_schema", "worker_source_config_digest"})
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")


class CapacityJoinError(ValueError):
    """A closed identity-read refusal; raw registry errors are never projected."""
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise CapacityJoinError(code)


def _token(value: object, code: str) -> str:
    if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
        _refuse(code)
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class CapacityJoin:
    host_ref: str
    capacity_capability_id: str
    provider_capacity_schema: str
    worker_source_config_digest: str

    def __post_init__(self) -> None:
        if type(self.host_ref) is not str or (
            self.host_ref != "local-unbound" and HOST_REF_RE.fullmatch(self.host_ref) is None
        ):
            _refuse("HOST_REFERENCE_INVALID")
        _token(self.capacity_capability_id, "CAPABILITY_ID_INVALID")
        if type(self.provider_capacity_schema) is not str or self.provider_capacity_schema != PROVIDER_CAPACITY_SCHEMA:
            _refuse("PROVIDER_CAPACITY_SCHEMA_INVALID")
        if type(self.worker_source_config_digest) is not str or _DIGEST_RE.fullmatch(self.worker_source_config_digest) is None:
            _refuse("WORKER_CONFIG_DIGEST_INVALID")

    def to_dict(self) -> dict[str, str]:
        return {"schema": JOIN_SCHEMA, **dataclasses.asdict(self)}


def validate_capacity_join(value: object) -> CapacityJoin:
    """Validate the frozen five-key wire; local V1 remains diagnostic-only."""
    if type(value) is not dict or len(value) != len(_JOIN_KEYS):
        _refuse("JOIN_FIELDS_INVALID")
    snapshot = value.copy()
    if any(type(key) is not str for key in snapshot) or set(snapshot) != _JOIN_KEYS:
        _refuse("JOIN_FIELDS_INVALID")
    if type(snapshot["schema"]) is not str or snapshot["schema"] != JOIN_SCHEMA:
        _refuse("JOIN_SCHEMA_INVALID")
    return CapacityJoin(**{key: snapshot[key] for key in _JOIN_KEYS if key != "schema"})


@dataclasses.dataclass(frozen=True, slots=True)
class RegisteredCapacityJoin:
    worker_id: str
    quota_class: str
    provider: str
    capacity_join: CapacityJoin

    def __post_init__(self) -> None:
        _token(self.worker_id, "WORKER_ID_INVALID")
        _token(self.quota_class, "QUOTA_CLASS_INVALID")
        _token(self.provider, "PROVIDER_INVALID")
        if not isinstance(self.capacity_join, CapacityJoin):
            _refuse("JOIN_FIELDS_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {"worker_id": self.worker_id, "quota_class": self.quota_class,
                "provider": self.provider, "capacity_join": self.capacity_join.to_dict()}


class QuotaIdentityReader(Protocol):
    """Existing exact-quota read API; no alternate store, census or writer."""
    def get_quota_class(self, worker_id: str, quota_class: str) -> Any: ...


def _candidate_keys(value: object) -> tuple[tuple[str, str], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _refuse("CANDIDATE_KEYS_INVALID")
    # Bound acquisition itself, including a custom Sequence with a false length.
    try:
        snapshot = tuple(islice(iter(value), MAX_CANDIDATES + 1))
    except Exception:
        raise CapacityJoinError("CANDIDATE_KEYS_INVALID") from None
    if not 1 <= len(snapshot) <= MAX_CANDIDATES:
        _refuse("CANDIDATE_COUNT_INVALID")
    keys: list[tuple[str, str]] = []
    for raw in snapshot:
        if type(raw) not in (tuple, list) or len(raw) != 2:
            _refuse("CANDIDATE_KEY_INVALID")
        # Freeze only the accepted two-item key. The third-item cap detects a
        # concurrent growth without copying an arbitrarily large malformed list.
        key = tuple(islice(iter(raw), 3))
        if len(key) != 2:
            _refuse("CANDIDATE_KEY_INVALID")
        worker_id, quota_class = key
        _token(worker_id, "WORKER_ID_INVALID")
        _token(quota_class, "QUOTA_CLASS_INVALID")
        if quota_class != quota_class.lower():
            _refuse("QUOTA_CLASS_INVALID")
        keys.append((worker_id, quota_class))
    if len(set(keys)) != len(keys):
        _refuse("DUPLICATE_CANDIDATE_KEY")
    return tuple(keys)


def read_remote_capacity_joins(
    registry: QuotaIdentityReader,
    candidate_keys: Sequence[tuple[str, str]],
) -> tuple[RegisteredCapacityJoin, ...]:
    """Read a bounded explicit candidate set without ranking or writing.

    Registration immutability and Worker/quota provider equality remain the
    existing WorkerRegistry/database owner's responsibility. get_worker() is
    deliberately not called: it materializes every quota on the Worker.
    At most three exact quota reads occur; a missing/error row never qualifies. Duplicate
    checks cover this supplied candidate set, not a full-registry census. Reads
    are not a transactional claim snapshot. Returned order preserves input order
    and conveys no preference; neither occupancy nor freshness is asserted.
    local-unbound can be parsed for the local canary but ALWAYS refuses here.
    """
    keys = _candidate_keys(candidate_keys)
    results: list[RegisteredCapacityJoin] = []
    identities: set[tuple[str, str]] = set()
    for worker_id, quota_class in keys:
        try:
            quota = registry.get_quota_class(worker_id, quota_class)
        except Exception:
            raise CapacityJoinError("REGISTRY_READ_FAILED") from None
        if quota is None:
            _refuse("QUOTA_MISSING")
        if (getattr(quota, "worker_id", None), getattr(quota, "quota_class", None)) != (worker_id, quota_class):
            _refuse("QUOTA_IDENTITY_MISMATCH")
        provider = _token(getattr(quota, "provider", None), "PROVIDER_INVALID")
        if provider != provider.lower():
            _refuse("PROVIDER_INVALID")
        metadata = getattr(quota, "metadata", None)
        if type(metadata) is not dict or "capacity_join" not in metadata:
            _refuse("JOIN_MISSING")
        capacity_join = validate_capacity_join(metadata["capacity_join"])
        if capacity_join.host_ref == "local-unbound":
            _refuse("REMOTE_HOST_UNBOUND")
        identity = (capacity_join.host_ref, capacity_join.capacity_capability_id)
        if identity in identities:
            _refuse("DUPLICATE_CAPACITY_JOIN")
        identities.add(identity)
        results.append(RegisteredCapacityJoin(worker_id, quota_class, provider, capacity_join))
    return tuple(results)
