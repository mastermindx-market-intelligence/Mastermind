"""Executive placement authority (MMOS V1 WO-14; OQ-1 ruling).

``AttemptRegistry.claim_job`` is the SOLE placement authority.  For a Job
that carries a ``child_placement`` spec (a ``ChildExecutionRequest.v1``
admitted by the owner), one Executive SQLite transaction:

1. rechecks root/parent/grant, effective class, route descriptor, the
   capacity registry revision, host observations and counters, account
   readiness/cooldown and EVERY shared quota resource;
2. reserves host slot + root concurrency + shared quota as ONE physical
   commitment through the incumbent ``ResourceBroker`` persistence owner
   (``physical_resource_commitments``; no second allocator, no ad hoc DDL);
3. binds attempt/host/route/``fence_counter`` and returns
   ``ExecutionBinding.v1`` at ``claim_payload["execution_binding"]``.

The deployed Fabric lease broker (``ext/broker/leases.sqlite``) is an
OBSERVATION SOURCE only: :func:`read_lease_broker_observation` opens it
``?mode=ro`` and never writes.  All file/DB/network reads happen in
:func:`observe_placement_inputs` OUTSIDE the claim transaction; the claim
transaction only consumes the frozen :class:`PlacementObservations` plus
broker-owned same-store counters.

This module is pure apart from that read-only observation reader.  It
never writes Executive state; the Runtime owns every mutation.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from control_plane.child_execution_contracts import (
    CANONICAL_TASK_COMPLEXITIES,
    POLICY_REVISION,
    REVIEW_LANE,
    ChildExecutionRequest,
    ExecutionBinding,
    canonical_task_complexity,
)

CHILD_PLACEMENT_KEY = "child_placement"
CHILD_PLACEMENT_SCHEMA = "mastermind.child_placement_spec/v1"
OBSERVATIONS_SCHEMA = "mastermind.placement_observations/v1"
DEFERRAL_SCHEMA = "mastermind.job_placement_deferral/v1"
DEFERRAL_AGGREGATE = "job_placement"
DEFERRAL_EVENT = "JOB_PLACEMENT_DEFERRED"
RELEASE_EVENT = "JOB_CLAIM_RELEASED"
PLACEMENT_OWNER = "executive-placement-authority"
PLACEMENT_PROFILE = "executive.placement.v1"
PLACEMENT_EFFECT_SCOPE = ["host-slot", "root-concurrency", "shared-quota"]
DEFAULT_ROOT_CONCURRENCY = 32
MAX_ROOT_CONCURRENCY = 512
DEFAULT_OBSERVATION_MAX_AGE_MS = 45_000
LEASE_ACTIVE_STATES = ("held", "rented")
_ROUTE_KEYS = frozenset({"adapter_id", "model_ref", "provider_ref", "pool_ref"})
_SPEC_KEYS = frozenset({
    "schema", "child_execution_request", "effective_complexity",
    "registry_revision", "route", "shared_quota_resource_refs",
    "root_concurrency_limit", "authority_policy_hash",
})


class PlacementRefusal(Exception):
    """A placement predicate refused; the Job stays QUEUED with this reason."""

    def __init__(self, code: str, detail: str = "", *, resource_ref: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.resource_ref = resource_ref

    def to_dict(self) -> dict[str, str]:
        return {"reason_code": self.code, "detail": self.detail,
                "resource_ref": self.resource_ref}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(f"{label} must be a non-empty string")
    return text


def _positive_int(value: Any, label: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{label} must be a positive integer"
                         + (f" <= {maximum}" if maximum is not None else ""))
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


# --- pools ---------------------------------------------------------------------

def host_slot_pool(host_id: str) -> str:
    return f"host-slot:{host_id}"


def root_concurrency_pool(root_job_id: str) -> str:
    return f"root-concurrency:{root_job_id}"


def shared_quota_pool(resource_ref: str) -> str:
    return f"shared-quota:{resource_ref}"


def placement_operation_key(job_id: str) -> str:
    return f"placement:{job_id}"


def placement_phase_key(attempt_number: int) -> str:
    return f"attempt-{attempt_number}"


# --- the admitted spec carried in Job constraints -------------------------------

def normalize_child_placement_spec(raw: Any) -> dict[str, Any]:
    """Validate the closed ``child_placement`` constraint; refuse drift.

    The spec is written by the owner's admission (WO-13).  It references
    the admitted ``ChildExecutionRequest.v1`` and pins what the claim must
    recheck: effective class, capacity registry revision, route
    descriptor, every shared quota resource and the root concurrency cap.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("child_placement must be a mapping")
    unknown = set(raw) - _SPEC_KEYS
    if unknown:
        raise ValueError(f"child_placement has unknown keys {sorted(unknown)}")
    if raw.get("schema", CHILD_PLACEMENT_SCHEMA) != CHILD_PLACEMENT_SCHEMA:
        raise ValueError("child_placement schema is not v1")
    request = ChildExecutionRequest.from_dict(raw.get("child_execution_request") or {})
    effective = canonical_task_complexity(raw.get("effective_complexity")
                                          or request.requested_complexity)
    if effective not in CANONICAL_TASK_COMPLEXITIES and effective != REVIEW_LANE:
        raise ValueError("child_placement effective_complexity is not canonical")
    route_raw = raw.get("route") or {}
    if not isinstance(route_raw, Mapping) or set(route_raw) - _ROUTE_KEYS:
        raise ValueError("child_placement route is not a closed descriptor")
    route = {key: str(route_raw.get(key) or "").strip() for key in sorted(_ROUTE_KEYS)}
    refs_raw = raw.get("shared_quota_resource_refs") or []
    if isinstance(refs_raw, str) or not isinstance(refs_raw, Iterable):
        raise ValueError("shared_quota_resource_refs must be a list")
    refs = [str(ref).strip() for ref in refs_raw]
    if any(not ref or ":" not in ref for ref in refs) or len(set(refs)) != len(refs):
        raise ValueError("shared_quota_resource_refs must be unique provider:account refs")
    limit = raw.get("root_concurrency_limit", DEFAULT_ROOT_CONCURRENCY)
    _positive_int(limit, "root_concurrency_limit", maximum=MAX_ROOT_CONCURRENCY)
    spec: dict[str, Any] = {
        "schema": CHILD_PLACEMENT_SCHEMA,
        "child_execution_request": request.to_dict(),
        "effective_complexity": effective,
        "registry_revision": _nonempty(raw.get("registry_revision"), "registry_revision"),
        "route": route,
        "shared_quota_resource_refs": sorted(refs),
        "root_concurrency_limit": limit,
    }
    if raw.get("authority_policy_hash"):
        spec["authority_policy_hash"] = _nonempty(raw["authority_policy_hash"],
                                                  "authority_policy_hash")
    return spec


def child_request_of(spec: Mapping[str, Any]) -> ChildExecutionRequest:
    return ChildExecutionRequest.from_dict(spec["child_execution_request"])


def recheck_effective_class(spec: Mapping[str, Any]) -> None:
    """The admitted class must still be what the shared law produced."""
    request = child_request_of(spec)
    effective = spec["effective_complexity"]
    if request.policy_revision != POLICY_REVISION:
        raise PlacementRefusal("POLICY_REVISION_MOVED",
                               f"request {request.policy_revision} != owner {POLICY_REVISION}")
    decision = request.routing_decision
    if decision is not None:
        if not decision.resolved:
            raise PlacementRefusal("EFFECTIVE_CLASS_REFUSED", decision.reason)
        if decision.task_complexity != effective:
            raise PlacementRefusal("EFFECTIVE_CLASS_MOVED",
                                   f"{decision.task_complexity} != {effective}")
    elif request.requested_complexity != effective:
        raise PlacementRefusal("EFFECTIVE_CLASS_MOVED",
                               f"{request.requested_complexity} != {effective}")


def recheck_route_descriptor(spec: Mapping[str, Any], *, provider: str, model: str,
                             adapter_id: str) -> None:
    route = spec["route"]
    for key, actual in (("provider_ref", provider), ("model_ref", model),
                        ("adapter_id", adapter_id)):
        if route.get(key) and route[key] != (actual or ""):
            raise PlacementRefusal("DESCRIPTOR_MOVED", f"{key} {route[key]!r} != {actual!r}")


# --- observations (frozen OUTSIDE the transaction) -------------------------------

@dataclasses.dataclass(frozen=True)
class HostObservation:
    host_id: str
    boot_id: str
    eligible_slots: int
    observed_at_ms: int
    max_age_ms: int = DEFAULT_OBSERVATION_MAX_AGE_MS

    def __post_init__(self) -> None:
        _nonempty(self.host_id, "host_id")
        _nonempty(self.boot_id, "boot_id")
        _nonnegative_int(self.eligible_slots, "eligible_slots")
        _nonnegative_int(self.observed_at_ms, "observed_at_ms")
        _positive_int(self.max_age_ms, "max_age_ms")

    @classmethod
    def from_host_readiness_snapshot(cls, snapshot: Mapping[str, Any], *,
                                     boot_id: str | None = None) -> "HostObservation":
        """Project a WO-04 ``HostReadinessSnapshot.v1``.

        ``eligible_slots`` (0 until enrolled) is authoritative; the proposed
        slot count is never promoted.  ``no_new_claims_after_s`` bounds age.
        """
        if snapshot.get("schema") != "mastermind.host_readiness_snapshot/v1":
            raise ValueError("not a HostReadinessSnapshot.v1")
        observed = snapshot.get("observed_at_utc") or snapshot.get("collected_at")
        observed_ms = int(datetime.strptime(str(observed), "%Y-%m-%dT%H:%M:%SZ")
                          .replace(tzinfo=timezone.utc).timestamp() * 1000)
        thresholds = snapshot.get("proposed_thresholds") or {}
        max_age_s = int(thresholds.get("no_new_claims_after_s") or 45)
        eligible = snapshot.get("eligible_slots")
        if snapshot.get("reachable") is not True or type(eligible) is not int:
            eligible = 0
        uptime = snapshot.get("uptime_s")
        boot = boot_id or (f"uptime-epoch:{observed_ms // 1000 - int(uptime)}"
                           if type(uptime) is int else "boot-unknown")
        return cls(host_id=str(snapshot["host_id"]), boot_id=boot, eligible_slots=eligible,
                   observed_at_ms=observed_ms, max_age_ms=max_age_s * 1000)


@dataclasses.dataclass(frozen=True)
class SharedQuotaObservation:
    resource_ref: str
    per_account_cap: int
    enabled: bool = True
    credential_ready: bool = True
    parked_until_ms: int | None = None
    cooldown_until_ms: int | None = None
    cooldown_mode: str = "HARD"
    soft_cap: int | None = None
    external_active_leases: int = 0
    window_usage_pct: float | None = None

    def __post_init__(self) -> None:
        _nonempty(self.resource_ref, "resource_ref")
        _nonnegative_int(self.per_account_cap, "per_account_cap")
        _nonnegative_int(self.external_active_leases, "external_active_leases")
        if self.cooldown_mode not in ("HARD", "SOFT"):
            raise ValueError("cooldown_mode must be HARD or SOFT")
        if self.window_usage_pct is not None and not 0 <= float(self.window_usage_pct):
            raise ValueError("window_usage_pct must be >= 0")


@dataclasses.dataclass(frozen=True)
class PlacementObservations:
    """Frozen inputs read OUTSIDE the claim transaction (no I/O inside it)."""

    registry_revision: str
    observed_at_ms: int
    hosts: Mapping[str, HostObservation]
    shared_quota: Mapping[str, SharedQuotaObservation]
    lease_broker_source: str = ""
    max_age_ms: int = DEFAULT_OBSERVATION_MAX_AGE_MS

    def __post_init__(self) -> None:
        _nonempty(self.registry_revision, "registry_revision")
        _nonnegative_int(self.observed_at_ms, "observed_at_ms")
        _positive_int(self.max_age_ms, "max_age_ms")
        object.__setattr__(self, "hosts", dict(self.hosts))
        object.__setattr__(self, "shared_quota", dict(self.shared_quota))
        for key, host in self.hosts.items():
            if type(host) is not HostObservation or host.host_id != key:
                raise ValueError("hosts must map host_id -> HostObservation")
        for key, quota in self.shared_quota.items():
            if type(quota) is not SharedQuotaObservation or quota.resource_ref != key:
                raise ValueError("shared_quota must map ref -> SharedQuotaObservation")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": OBSERVATIONS_SCHEMA,
                "registry_revision": self.registry_revision,
                "observed_at_ms": self.observed_at_ms,
                "max_age_ms": self.max_age_ms,
                "lease_broker_source": self.lease_broker_source,
                "hosts": {k: dataclasses.asdict(v) for k, v in sorted(self.hosts.items())},
                "shared_quota": {k: dataclasses.asdict(v)
                                 for k, v in sorted(self.shared_quota.items())}}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())


def _iso_ms(value: Any) -> int | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(str(value), "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def read_lease_broker_observation(db_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read the deployed Fabric lease broker as an OBSERVATION SOURCE only.

    Opens ``file:<path>?mode=ro`` (SQLite refuses every write on this
    handle).  Returns active (``held``/``rented``) lease counts per quota
    scope and the cooldown rows.  OQ-1: this broker never allocates for
    Executive placement; its live leases only reduce observed headroom.
    """
    path = Path(db_path)
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    try:
        connection.execute("PRAGMA query_only=ON")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(leases)")}
        scope_expr = ("COALESCE(NULLIF(quota_scope,''), pool || ':' || account)"
                      if "quota_scope" in columns else "pool || ':' || account")
        marks = ",".join("?" for _ in LEASE_ACTIVE_STATES)
        active: dict[str, int] = {}
        for scope, account, count in connection.execute(
                f"SELECT {scope_expr}, account, COUNT(*) FROM leases "
                f"WHERE state IN ({marks}) GROUP BY 1,2", LEASE_ACTIVE_STATES):
            active[str(scope)] = active.get(str(scope), 0) + int(count)
        cooldowns: list[dict[str, Any]] = []
        has_cooldowns = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='quota_cooldowns'"
        ).fetchone() is not None
        if has_cooldowns:
            for scope, until_ts, mode, soft_cap in connection.execute(
                    "SELECT scope, until_ts, mode, soft_cap FROM quota_cooldowns"):
                cooldowns.append({"scope": str(scope), "until_ms": int(float(until_ts) * 1000),
                                  "mode": str(mode or "HARD").upper(),
                                  "soft_cap": int(soft_cap) if soft_cap is not None else None})
        stat = path.stat()
        source = _digest({"path": str(path), "size": stat.st_size,
                          "mtime_ns": stat.st_mtime_ns, "active": active,
                          "cooldowns": cooldowns})
        return {"active_leases": active, "cooldowns": cooldowns, "source": source}
    finally:
        connection.close()


def _cooldown_for(ref: str, cooldowns: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    provider, _, account = ref.partition(":")
    best = None
    for row in cooldowns:
        scope = str(row.get("scope") or "")
        scope_provider, _, scope_account = scope.partition(":")
        if scope == ref or (scope_account == account
                            and scope_provider.split("-", 1)[0] == provider):
            if best is None or int(row["until_ms"]) > int(best["until_ms"]):
                best = row
    return best


def observations_from_projection(projection: Mapping[str, Any], *,
                                 host_snapshots: Iterable[Mapping[str, Any]],
                                 lease_observation: Mapping[str, Any] | None,
                                 observed_at_ms: int) -> PlacementObservations:
    """Compose WO-03 projection + WO-04 snapshots + lease-broker observation."""
    lease = lease_observation or {"active_leases": {}, "cooldowns": [], "source": ""}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in projection.get("shared_quota_resources") or []:
        grouped.setdefault(f"{row['provider']}:{row['account_name']}", []).append(row)
    quotas: dict[str, SharedQuotaObservation] = {}
    for ref, rows in sorted(grouped.items()):
        # The account row carries the cap; supplementary bucket rows (e.g.
        # ``inline_key_bucket``) only add usage. Never let a cap-less row
        # overwrite the account; an account with no cap row admits nothing.
        accounts = [r for r in rows if "per_account_cap" in r]
        if len(accounts) > 1:
            raise ValueError(f"shared quota resource {ref} has conflicting account rows")
        row = accounts[0] if accounts else {}
        usage = [float(r["pct_7d"]) for r in rows if r.get("pct_7d") is not None]
        cooldown = _cooldown_for(ref, lease.get("cooldowns") or [])
        quotas[ref] = SharedQuotaObservation(
            resource_ref=ref, per_account_cap=int(row.get("per_account_cap") or 0),
            enabled=bool(row.get("enabled_flag")),
            credential_ready=bool(row.get("has_credential_ref")),
            parked_until_ms=_iso_ms(row.get("parked_until")),
            cooldown_until_ms=int(cooldown["until_ms"]) if cooldown else None,
            cooldown_mode=str(cooldown["mode"]) if cooldown else "HARD",
            soft_cap=cooldown.get("soft_cap") if cooldown else None,
            external_active_leases=int((lease.get("active_leases") or {}).get(ref, 0)),
            window_usage_pct=max(usage) if usage else None)
    hosts = {}
    for snapshot in host_snapshots:
        host = HostObservation.from_host_readiness_snapshot(snapshot)
        hosts[host.host_id] = host
    return PlacementObservations(
        registry_revision=_nonempty(projection.get("registry_revision"), "registry_revision"),
        observed_at_ms=observed_at_ms, hosts=hosts, shared_quota=quotas,
        lease_broker_source=str(lease.get("source") or ""))


def observe_placement_inputs(*, projection_path: str | os.PathLike[str],
                             host_snapshot_dir: str | os.PathLike[str],
                             lease_broker_db: str | os.PathLike[str] | None,
                             observed_at_ms: int) -> PlacementObservations:
    """All I/O for one placement decision, run BEFORE the claim transaction."""
    projection = json.loads(Path(projection_path).read_text(encoding="utf-8"))
    snapshots = [json.loads(p.read_text(encoding="utf-8"))
                 for p in sorted(Path(host_snapshot_dir).glob("*.json"))]
    lease = read_lease_broker_observation(lease_broker_db) if lease_broker_db else None
    return observations_from_projection(projection, host_snapshots=snapshots,
                                        lease_observation=lease,
                                        observed_at_ms=observed_at_ms)


# --- the in-transaction predicate ----------------------------------------------

@dataclasses.dataclass(frozen=True)
class PlacementDecision:
    host_id: str
    boot_id: str
    root_job_id: str
    pools: tuple[str, ...]
    shared_quota_resource_refs: tuple[str, ...]
    observations_digest: str
    registry_revision: str


def evaluate_placement(*, spec: Mapping[str, Any], observations: PlacementObservations,
                       host_id: str | None, root_job_id: str, now_ms: int,
                       pool_charges: Mapping[str, int]) -> PlacementDecision:
    """Pure predicate over frozen observations + same-transaction counters.

    ``pool_charges`` are the Executive's own live commitments read by the
    ResourceBroker inside the claim transaction.  Raises
    :class:`PlacementRefusal` with the first failing reason.
    """
    if observations.registry_revision != spec["registry_revision"]:
        raise PlacementRefusal("REGISTRY_REVISION_MOVED",
                               "capacity registry revision differs from admission")
    if (observations.observed_at_ms > now_ms
            or now_ms - observations.observed_at_ms > observations.max_age_ms):
        raise PlacementRefusal("OBSERVATIONS_STALE", "placement observations are stale")
    if not host_id:
        raise PlacementRefusal("HOST_BINDING_UNAVAILABLE", "Worker declares no host_id")
    host = observations.hosts.get(host_id)
    if host is None:
        raise PlacementRefusal("HOST_UNOBSERVED", host_id, resource_ref=host_id)
    if host.observed_at_ms > now_ms or now_ms - host.observed_at_ms > host.max_age_ms:
        raise PlacementRefusal("HOST_OBSERVATION_STALE", host_id, resource_ref=host_id)
    slot_pool = host_slot_pool(host_id)
    used = int(pool_charges.get(slot_pool, 0))
    if host.eligible_slots <= 0 or used + 1 > host.eligible_slots:
        raise PlacementRefusal("HOST_CAPACITY_EXHAUSTED",
                               f"{used}/{host.eligible_slots} slots held", resource_ref=host_id)
    root_pool = root_concurrency_pool(root_job_id)
    root_used = int(pool_charges.get(root_pool, 0))
    if root_used + 1 > int(spec["root_concurrency_limit"]):
        raise PlacementRefusal("ROOT_CONCURRENCY_EXHAUSTED",
                               f"{root_used}/{spec['root_concurrency_limit']}",
                               resource_ref=root_job_id)
    pools = [slot_pool, root_pool]
    for ref in spec["shared_quota_resource_refs"]:
        quota = observations.shared_quota.get(ref)
        if quota is None:
            raise PlacementRefusal("SHARED_QUOTA_UNOBSERVED", ref, resource_ref=ref)
        if not quota.enabled or not quota.credential_ready:
            raise PlacementRefusal("ACCOUNT_NOT_READY", ref, resource_ref=ref)
        if quota.parked_until_ms is not None and quota.parked_until_ms > now_ms:
            raise PlacementRefusal("ACCOUNT_PARKED", ref, resource_ref=ref)
        if quota.window_usage_pct is not None and quota.window_usage_pct >= 100.0:
            raise PlacementRefusal("SHARED_QUOTA_WINDOW_EXHAUSTED",
                                   f"{quota.window_usage_pct}% of window used", resource_ref=ref)
        cap = quota.per_account_cap
        if quota.cooldown_until_ms is not None and quota.cooldown_until_ms > now_ms:
            if quota.cooldown_mode == "HARD":
                raise PlacementRefusal("ACCOUNT_COOLDOWN", ref, resource_ref=ref)
            if quota.soft_cap is not None:
                cap = min(cap, quota.soft_cap)
        pool = shared_quota_pool(ref)
        held = int(pool_charges.get(pool, 0)) + quota.external_active_leases
        if held + 1 > cap:
            raise PlacementRefusal("SHARED_QUOTA_EXHAUSTED", f"{held}/{cap} held",
                                   resource_ref=ref)
        pools.append(pool)
    return PlacementDecision(host_id=host_id, boot_id=host.boot_id, root_job_id=root_job_id,
                             pools=tuple(pools),
                             shared_quota_resource_refs=tuple(spec["shared_quota_resource_refs"]),
                             observations_digest=observations.digest,
                             registry_revision=observations.registry_revision)


def build_placement_request(decision: PlacementDecision, *, spec: Mapping[str, Any],
                            job_id: str, attempt_id: str, attempt_number: int,
                            lease_owner: str, duration_ms: int,
                            timestamp: int) -> dict[str, Any]:
    """The closed physical request for ONE commitment carrying every demand.

    The physical contract's git-source fields carry placement identity
    digests (registry revision, admitted request digest), not a git commit;
    a dedicated placement request kind is a reviewed-schema follow-up.
    """
    request_digest = spec["child_execution_request"]["request_digest"]
    window = {"unit": "count", "window_ms": duration_ms, "baseline_id": "placement",
              "boot_id": decision.boot_id}
    return {
        "operation_key": placement_operation_key(job_id),
        "host_id": decision.host_id,
        "boot_id": decision.boot_id,
        "owner_id": PLACEMENT_OWNER,
        "carrier_id": attempt_id,
        "command_id": f"physical:placement:{attempt_id}:reserve",
        "acquisition_time_ms": timestamp,
        "source_binding": {
            "commit_sha": hashlib.sha1(
                f"{decision.registry_revision}:{request_digest}".encode()).hexdigest(),
            "helper_sha256": request_digest,
            "common_git_store": {"realpath": f"placement://registry/{decision.registry_revision}",
                                 "device": 0, "inode": 0},
            "destination": {"realpath": f"placement://host/{decision.host_id}", "device": 0,
                            "capacity_pool_id": host_slot_pool(decision.host_id)},
        },
        "policy_binding": {"revision": f"placement-authority/{POLICY_REVISION}",
                           "sha256": decision.observations_digest},
        "caller_binding": {"session_id": lease_owner, "pid": os.getpid(),
                           "start_id": attempt_id},
        "phases": [{
            "phase_key": placement_phase_key(attempt_number),
            "profile": PLACEMENT_PROFILE,
            "duration_ms": duration_ms,
            "effect_scope": list(PLACEMENT_EFFECT_SCOPE),
            "demands": [{"dimension": "heavy_phase_count", "capacity_pool_id": pool,
                         "qualified_incremental_peak": 1, "window_binding": dict(window)}
                        for pool in decision.pools],
        }],
    }


def issue_execution_binding(*, spec: Mapping[str, Any], decision: PlacementDecision,
                            job_id: str, root_job_id: str, attempt_id: str,
                            attempt_number: int, worker_id: str, provider: str,
                            model: str, adapter_id: str, fence_counter: int,
                            lease_expires_at_ms: int) -> ExecutionBinding:
    request = child_request_of(spec)
    route = spec["route"]
    expiry = datetime.fromtimestamp(lease_expires_at_ms / 1000, tz=timezone.utc)
    decision_ref = ("routing-decision:" + _digest(request.routing_decision.to_dict())
                    if request.routing_decision is not None else "")
    return ExecutionBinding(
        root_run_ref=request.root_ref,
        immediate_parent_run_ref=request.immediate_parent_run_ref,
        logical_child_key=request.logical_child_key,
        request_digest=request.request_digest,
        effective_complexity=spec["effective_complexity"],
        original_root_orchestrator_ref=f"executive-root:{root_job_id}",
        task_kind=request.task_kind,
        job_ref=job_id,
        attempt_ref=attempt_id,
        policy_revision=request.policy_revision,
        decision_ref=decision_ref,
        scope_digest=request.scope_digest,
        budget_grant_ref=request.budget_grant_ref,
        adapter_id=adapter_id or route.get("adapter_id", ""),
        model_ref=model or route.get("model_ref", ""),
        provider_ref=provider,
        pool_ref=route.get("pool_ref", ""),
        shared_quota_resource_refs=decision.shared_quota_resource_refs,
        host_id=decision.host_id,
        worker_id=worker_id,
        host_boot_id=decision.boot_id,
        assignment_generation=attempt_number,
        fence_counter=fence_counter,
        lease_expiry=expiry.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    )
