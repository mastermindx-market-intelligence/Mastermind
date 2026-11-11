"""QuotaEconomicsPreviewProducer — real runtime read projection (MMOS V1 WO-09).

Produces ``mastermind.quota_economics_preview/v1`` — the consumer schema
pinned at ``control_plane.capacity_economics_projection.QUOTA_PREVIEW_SCHEMA``
(:19) — from five read-only inputs:

1. the sanitized WO-03 owner_ext registry projection (JSON file);
2. deployed lease-broker active/reserved counters and cooldowns (SQLite,
   opened strictly as ``file:...?mode=ro``; the broker is an observation
   source per OQ-1, never a second allocator);
3. existing credential/profile readiness verdicts carried by the projection
   (enabled flags, credential refs, owner park verdicts) — no secrets;
4. provider usage/limit/reset observations only where the owner actually
   exposes them (bailian inline 7-day key buckets, the grok weekly chairman
   provider screenshot window). Whatever a provider does not expose stays
   ``null`` with ``quota_knowledge="unknown"`` (OQ-3 stays open on purpose;
   numbers are never invented and configuration is never reported as
   observed provider quota);
5. owner-configured concurrency ceilings, explicitly labeled configuration.

The preview never reserves, launches or admits; ``authority`` stays
``NONE_PREVIEW_ONLY`` and ``production_armed`` stays false. One shared
bucket stays one resource across credentials: rows are keyed by
``(provider, account)`` and bailian-style inline key-bucket entries merge
into the same resource instead of duplicating it.

Broker read semantics: the deployed database is opened strictly through a
``file:...?mode=ro`` URI. Because the live broker database runs in WAL mode,
SQLite may materialize its transient zero-byte ``-wal`` and shared-memory
``-shm`` reader sidecars next to it; that is SQLite's standard reader
machinery for live WAL databases. The database file itself is never written
(byte- and mode-identity are asserted by the tests).

The producer goes through the existing trusted factory boundary: it only
accepts a ``WorkerCapacitySourceConfig`` sealed by
``executive_capacity_observation_producer.validate_worker_capacity_source_config``
(:174, class :109) — the same trusted-source family used by
``capacity_runtime_observation.observe_runtime_workload`` (:84). There are
no pytest-only constructors, environment-variable switches, loosened
attestation checks or fixture receipts on this path.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote as _uri_quote

from control_plane.capacity_economics_projection import QUOTA_PREVIEW_SCHEMA
from control_plane.executive_capacity_observation_producer import (
    _SOURCE_SEAL,
    WorkerCapacitySourceConfig,
    worker_capacity_source_config_digest,
)
from control_plane.provider_quota_observation import (
    OBSERVATION_SCHEMA,
    QuotaObservation,
    QuotaObservationError,
    load_quota_observation_document,
)

PROJECTION_SCHEMA = "mastermind.owner_ext_registry_projection/v1"
PREVIEW_STATUS_READY = "PREVIEW_READY"
PREVIEW_STATUS_NO_ELIGIBLE = "PREVIEW_NO_ELIGIBLE_OPTION"
SELECTED_TIER_LABEL = "first_lawful_suitability_tier"
PREVIEW_LIFETIME_SECONDS = 900  # consumer QuotaPreviewFreshness max bound
SOURCE_OWNER_REF = "owner_ext"
MAX_RESOURCES = 256
MAX_REASON_CODES = 12
_HELD_LEASE_STATES = ("held", "rented")
_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REDACTED_MARKERS = ("<REDACTED",)


class QuotaEconomicsPreviewError(ValueError):
    """A read-only quota-economics preview input is invalid or unavailable."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _refuse(code: str, detail: str | None = None) -> None:
    raise QuotaEconomicsPreviewError(code, detail)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        _refuse("QUOTA_PREVIEW_SCHEMA_INVALID")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc_seconds(value: object) -> datetime:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        _refuse("QUOTA_PREVIEW_OBSERVED_AT_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _refuse("QUOTA_PREVIEW_OBSERVED_AT_INVALID")


def _iso_z(value: object) -> str | None:
    """Normalize an owner-recorded timestamp to UTC ``Z`` form; never invent.

    Returns ``None`` for absent or unparsable values (honest unknown), and
    keeps redaction placeholders out of timestamp fields.
    """
    if not isinstance(value, str) or not value or any(
        marker in value for marker in _REDACTED_MARKERS
    ):
        return None
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    for form in (candidate, candidate + ":00"):
        try:
            parsed = datetime.fromisoformat(form)
        except ValueError:
            continue
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        try:
            return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, ValueError):
            return None
    return None


def _epoch_z(value: object) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(
                float(value), timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _bounded_number(value: object) -> float | int | None:
    if type(value) in (int, float) and -1e15 < value < 1e15:
        return round(value, 2) if isinstance(value, float) else value
    return None


def read_broker_observation(broker_db_path: object) -> dict[str, Any]:
    """Read active/reserved counters and cooldowns from the deployed broker.

    The database is opened strictly through a read-only SQLite URI; a missing
    or unreadable database refuses (it is never created or repaired here).
    Active slots are leases in the broker's held states (``held``/``rented``);
    reserved slots are queued waiter rows.
    """
    path = Path(broker_db_path)
    if not path.is_file():
        _refuse("QUOTA_PREVIEW_BROKER_UNAVAILABLE", str(path))
    uri = "file:" + _uri_quote(str(path)) + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        _refuse("QUOTA_PREVIEW_BROKER_UNAVAILABLE", str(error))
    try:
        cursor = connection.cursor()
        # Pin all counters and cooldowns to one read-only WAL snapshot.
        cursor.execute("BEGIN")
        generation = int(
            cursor.execute("SELECT COUNT(*) FROM leases").fetchone()[0]
        )
        leases_by_state = {
            str(state): count
            for state, count in cursor.execute(
                "SELECT state, COUNT(*) FROM leases GROUP BY state"
            )
        }
        active_by_scope = {
            str(scope): count
            for scope, count in cursor.execute(
                "SELECT quota_scope, COUNT(*) FROM leases "
                "WHERE state IN (?, ?) AND quota_scope IS NOT NULL "
                "GROUP BY quota_scope",
                _HELD_LEASE_STATES,
            )
        }
        reserved_by_pool_account = {
            f"{pool}:{account}": count
            for pool, account, count in cursor.execute(
                "SELECT pool, account, COUNT(*) FROM waiters "
                "WHERE pool IS NOT NULL AND account IS NOT NULL "
                "GROUP BY pool, account"
            )
        }
        waiters_total = int(
            cursor.execute("SELECT COUNT(*) FROM waiters").fetchone()[0]
        )
        cooldowns = []
        for scope, observed_at, until_ts, failures, kind, mode, soft_cap in cursor.execute(
            "SELECT scope, observed_at, until_ts, failures, kind, mode, soft_cap "
            "FROM quota_cooldowns"
        ):
            cooldowns.append(
                {
                    "scope": str(scope) if scope is not None else None,
                    "observed_at": _epoch_z(observed_at),
                    "until": _epoch_z(until_ts),
                    "failures": failures if type(failures) is int else None,
                    "kind": str(kind) if kind is not None else None,
                    "mode": str(mode) if mode is not None else None,
                    "soft_cap": soft_cap if type(soft_cap) is int else None,
                }
            )
    except sqlite3.Error as error:
        _refuse("QUOTA_PREVIEW_BROKER_UNAVAILABLE", str(error))
    finally:
        connection.close()
    return {
        "generation": generation,
        "leases_by_state": leases_by_state,
        "active_by_quota_scope": active_by_scope,
        "reserved_by_pool_account": reserved_by_pool_account,
        "waiters_total": waiters_total,
        "cooldowns": cooldowns,
    }


def _load_projection(projection_path: object) -> tuple[dict[str, Any], str]:
    path = Path(projection_path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        _refuse("QUOTA_PREVIEW_PROJECTION_UNAVAILABLE", str(error))
    try:
        projection = json.loads(raw)
    except ValueError as error:
        _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", str(error))
    if not isinstance(projection, Mapping):
        _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", "not an object")
    if projection.get("schema") != PROJECTION_SCHEMA:
        _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", f"expected {PROJECTION_SCHEMA}")
    pools = projection.get("pools")
    resources = projection.get("shared_quota_resources")
    if (
        not isinstance(pools, Sequence)
        or isinstance(pools, (str, bytes))
        or not pools
        or not isinstance(resources, Sequence)
        or isinstance(resources, (str, bytes))
        or not resources
    ):
        _refuse(
            "QUOTA_PREVIEW_PROJECTION_INVALID",
            "pools and shared_quota_resources must be non-empty sequences",
        )
    return dict(projection), hashlib.sha256(raw).hexdigest()


def _bounded_percentage(value: object) -> float | int | None:
    number = _bounded_number(value)
    return number if number is not None and 0 <= number <= 100 else None


def _pool_windows_usage(pool: Mapping[str, Any]) -> dict[str, Any] | None:
    """Owner-exposed provider usage inside pool windows, if any.

    Only a window carrying both a numeric remaining percentage and its own
    observation time counts as an observation; reset hints such as
    ``reset_approx`` ("1st of month ~00:00Z") are configuration text and are
    never converted into timestamps.
    """
    windows = pool.get("windows")
    if not isinstance(windows, Mapping) or not windows:
        return None
    for window in windows.values():
        if not isinstance(window, Mapping):
            continue
        remaining = _bounded_percentage(window.get("remaining_pct"))
        observed_at = _iso_z(window.get("observed_at"))
        if remaining is not None and observed_at is not None:
            return {
                "remaining": remaining,
                "observed_at": observed_at,
                "reset_at": _iso_z(window.get("reset_at")),
                "source": window.get("source"),
                "kind": window.get("anchor"),
            }
    return None


def _merge_resources(
    projection: Mapping[str, Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    """Key shared quota resources by (provider, account) — one bucket, one row.

    Canonical accounts.yaml rows establish the resource. Inline key-bucket
    rows (bailian ``inline_key_bucket`` usage buckets) merge into the same
    (provider, account) resource as usage observations instead of becoming
    separate resources.
    """
    pools: dict[str, dict[str, Any]] = {}
    for pool in projection.get("pools", ()):  # type: ignore[union-attr]
        if isinstance(pool, Mapping) and isinstance(pool.get("id"), str):
            pools[pool["id"]] = dict(pool)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in projection.get("shared_quota_resources", ()):  # type: ignore[union-attr]
        if not isinstance(row, Mapping):
            continue
        provider = row.get("provider")
        account = row.get("account_name")
        if not isinstance(provider, str) or not isinstance(account, str):
            continue
        key = (provider, account)
        resource = merged.setdefault(
            key,
            {
                "provider": provider,
                "account": account,
                "enabled_flag": None,
                "per_account_cap": None,
                "windows": None,
                "parked_until": None,
                "has_credential_ref": None,
                "pool_aliases": None,
                "inline": None,
                "sources": [],
            },
        )
        if row.get("kind") == "inline_key_bucket":
            if resource["inline"] is not None:
                _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", "duplicate inline quota resource")
            resource["sources"].append("inline_key_bucket")
            # Usage observation only; caps and readiness stay canonical.
            resource["inline"] = {"pct_7d": _bounded_percentage(row.get("pct_7d"))}
            continue
        resource["sources"].append("canonical")
        if resource["sources"].count("canonical") > 1:
            _refuse(
                "QUOTA_PREVIEW_PROJECTION_INVALID",
                f"duplicate canonical resource {provider}:{account}",
            )
        resource["enabled_flag"] = row.get("enabled_flag")
        resource["per_account_cap"] = row.get("per_account_cap")
        resource["windows"] = row.get("windows")
        resource["parked_until"] = row.get("parked_until")
        resource["has_credential_ref"] = row.get("has_credential_ref")
        resource["pool_aliases"] = row.get("pool_aliases")
    if not merged:
        _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", "no shared quota resources")
    if len(merged) > MAX_RESOURCES:
        _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", "too many shared quota resources")
    return merged, pools


def _attribute_cooldowns(
    broker: Mapping[str, Any],
    merged: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[dict[tuple[str, str], list[Mapping[str, Any]]], list[str]]:
    """Attribute broker cooldown scopes to (provider, account) resources.

    A scope like ``bailian-adaptive429:Kris`` is attributed only when the
    provider (or a prefixed policy form of it) and the account both match a
    known resource; anything else (e.g. ``declared:<provider>:<sha>``) stays
    unassigned and is reported, never guessed.
    """
    attributed: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    unassigned: list[str] = []
    for cooldown in broker.get("cooldowns", ()):
        scope = cooldown.get("scope")
        if not isinstance(scope, str) or ":" not in scope:
            if isinstance(scope, str):
                unassigned.append(scope)
            continue
        prefix, _, account = scope.rpartition(":")
        match = None
        for provider, candidate in merged:
            if account != candidate:
                continue
            if prefix == provider or prefix.startswith(provider + "-"):
                match = (provider, account)
                break
        if match is None:
            unassigned.append(scope)
        else:
            attributed.setdefault(match, []).append(cooldown)
    for rows in attributed.values():
        rows.sort(key=lambda item: (str(item.get("scope")), str(item.get("mode")),
                                   str(item.get("until")), str(item.get("soft_cap"))))
    return attributed, unassigned


@dataclasses.dataclass(frozen=True, slots=True)
class QuotaEconomicsPreview:
    """Immutable preview document; ``to_dict`` is the wire artifact."""

    document: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.document, sort_keys=True))

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.document)


def produce_quota_economics_preview(
    *,
    source_config: WorkerCapacitySourceConfig,
    projection_path: object,
    broker_db_path: object,
    observed_at: str,
    quota_observations_path: object = None,
) -> QuotaEconomicsPreview:
    """Produce one read-only quota-economics preview document.

    Every input is an explicit argument: there are no environment switches,
    no pytest-only constructors and no fixture receipts on this path. The
    ``source_config`` must come from the existing trusted factory
    ``validate_worker_capacity_source_config``.

    ``quota_observations_path`` (optional) names one validated
    ``mastermind.provider_quota_observation/v1`` document of live provider
    observations. When absent, the preview is byte-for-byte identical to the
    pre-observation producer. When present, every live ``provider_api``
    observation replaces the resource's unknown with real observed fields and
    a provenance block (and may supersede a registry fact for the same field,
    keeping both provenance entries); every typed unknown is appended to the
    resource's ``reason_codes`` and no unknown is ever converted to a number.
    The four registry observations (bailian inline buckets, the grok window)
    are preserved with their registry provenance.
    """
    if (
        not isinstance(source_config, WorkerCapacitySourceConfig)
        or source_config._seal is not _SOURCE_SEAL
    ):
        raise TypeError("source_config must be a validated WorkerCapacitySourceConfig")

    observed = _parse_utc_seconds(observed_at)
    expires_at = (observed + timedelta(seconds=PREVIEW_LIFETIME_SECONDS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    projection, projection_sha256 = _load_projection(projection_path)
    broker = read_broker_observation(broker_db_path)
    broker_path = Path(broker_db_path)
    broker_sha256 = _sha256_file(broker_path)
    # The database file omits uncheckpointed WAL data. Bind preview identity
    # to the actual single-transaction observation while retaining file provenance.
    broker_snapshot = {**broker, "cooldowns": sorted(broker["cooldowns"], key=_canonical_bytes)}
    broker_snapshot_sha256 = hashlib.sha256(_canonical_bytes(broker_snapshot)).hexdigest()

    quota_observations: dict[tuple[str, str], QuotaObservation] | None = None
    quota_observations_meta: dict[str, Any] | None = None
    quota_observations_sha256: str | None = None
    if quota_observations_path is not None:
        try:
            (
                quota_observations,
                quota_observations_meta,
            ) = load_quota_observation_document(quota_observations_path)
        except QuotaObservationError as error:
            _refuse(error.code, error.detail)
        quota_observations_sha256 = _sha256_file(Path(str(quota_observations_path)))

    merged, pools = _merge_resources(projection)
    cooldowns, unassigned_scopes = _attribute_cooldowns(broker, merged)
    registry_revision = projection.get("registry_revision")
    if not isinstance(registry_revision, str) or not registry_revision:
        _refuse("QUOTA_PREVIEW_PROJECTION_INVALID", "registry_revision missing")

    priority_order: list[str] = []
    routing_policy = projection.get("routing_policy")
    if isinstance(routing_policy, Mapping):
        order = routing_policy.get("priority_order")
        if isinstance(order, Sequence) and not isinstance(order, (str, bytes)):
            priority_order = [item for item in order if isinstance(item, str)]

    projection_produced_at = _iso_z(projection.get("produced_at"))

    resources: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for key in sorted(merged):
        provider, account = key
        resource = merged[key]
        pool = pools.get(provider)
        row = _build_resource_row(
            provider=provider,
            account=account,
            resource=resource,
            pool=pool,
            registry_revision=registry_revision,
            observed_at=observed,
            expires_at=expires_at,
            broker=broker,
            cooldown=cooldowns.get(key),
            pool_usage=_pool_usage_for_provider(pools, provider),
            projection_produced_at=projection_produced_at,
            observation=(
                quota_observations.get(key)
                if quota_observations is not None
                else None
            ),
            emit_provenance=quota_observations is not None,
        )
        resources.append(row)
        option = _build_option(row, pool, priority_order)
        if option is not None:
            options.append(option)

    options.sort(key=lambda item: (item["_priority"], item["option_id"]))
    for option in options:
        option.pop("_priority")
    quota_observed = sum(
        1 for row in resources if row["quota_knowledge"] == "observed"
    )
    quota_unknown = sum(
        1 for row in resources if row["quota_knowledge"] == "unknown"
    )
    eligible = sum(1 for row in resources if row["admission_eligibility"])
    status = PREVIEW_STATUS_READY if options else PREVIEW_STATUS_NO_ELIGIBLE

    source_owner = projection.get("source_owner_ref")
    owner_ext_root = (
        source_owner.get("owner_ext_root")
        if isinstance(source_owner, Mapping)
        else None
    )
    document: dict[str, Any] = {
        "schema": QUOTA_PREVIEW_SCHEMA,
        "authority": "NONE_PREVIEW_ONLY",
        "binding_verification": "NOT_PERFORMED",
        "live_admission": False,
        "claim_time_revalidation_required": True,
        "production_armed": False,
        "status": status,
        "selected_tier": SELECTED_TIER_LABEL,
        "as_of": observed_at,
        "expires_at": expires_at,
        "suggested_option": options[0]["option_id"] if options else None,
        "options": options,
        "resources": resources,
        "knowledge_summary": {
            "resources_total": len(resources),
            "quota_observed": quota_observed,
            "quota_unknown": quota_unknown,
            "admission_eligible": eligible,
            "observed_vs_unknown": f"{quota_observed} observed / {quota_unknown} unknown",
        },
        "source_owner_ref": SOURCE_OWNER_REF,
        "registry_revision": registry_revision,
        "registry_revision_basis": projection.get("registry_revision_basis"),
        "projection": {
            "schema": projection.get("schema"),
            "sha256": projection_sha256,
            "produced_at": projection.get("produced_at"),
            "path": str(Path(projection_path)),
        },
        "source_owner": {"owner_ext_root": owner_ext_root},
        "broker": {
            "path": str(broker_path),
            "sha256": broker_sha256,
            "sha256_basis": "main_database_file_bytes_excludes_uncheckpointed_wal",
            "snapshot_sha256": broker_snapshot_sha256,
            "snapshot_basis": "single_read_only_sqlite_transaction",
            "opened_mode": "ro",
            "generation": broker["generation"],
            "leases_by_state": broker["leases_by_state"],
            "waiters_total": broker["waiters_total"],
            "cooldown_scopes_unassigned": unassigned_scopes,
        },
        "producer": {
            "source_config_digest": worker_capacity_source_config_digest(
                source_config
            ),
            "source_config": source_config.to_dict(),
        },
    }
    if quota_observations_meta is not None:
        document["quota_observations"] = {
            "schema": quota_observations_meta["schema"],
            "observed_at": quota_observations_meta["observed_at"],
            "path": quota_observations_meta["path"],
            "sha256": quota_observations_sha256,
        }
    preview_id = hashlib.sha256(
        _canonical_bytes(
            {
                "schema": QUOTA_PREVIEW_SCHEMA,
                "registry_revision": registry_revision,
                "observed_at": observed_at,
                "projection_sha256": projection_sha256,
                "broker_sha256": broker_sha256,
                "broker_snapshot_sha256": broker_snapshot_sha256,
            }
        )
    ).hexdigest()
    document["preview_id"] = preview_id[:32]
    document["observation_digest"] = hashlib.sha256(
        _canonical_bytes(document)
    ).hexdigest()
    return QuotaEconomicsPreview(document=document)


def _pool_usage_for_provider(
    pools: Mapping[str, Mapping[str, Any]], provider: str
) -> dict[str, Any] | None:
    pool = pools.get(provider)
    if pool is None:
        return None
    return _pool_windows_usage(pool)


def _build_resource_row(
    *,
    provider: str,
    account: str,
    resource: Mapping[str, Any],
    pool: Mapping[str, Any] | None,
    registry_revision: str,
    observed_at: datetime,
    expires_at: str,
    broker: Mapping[str, Any],
    cooldown: Sequence[Mapping[str, Any]] | None,
    pool_usage: Mapping[str, Any] | None,
    projection_produced_at: str | None,
    observation: QuotaObservation | None = None,
    emit_provenance: bool = False,
) -> dict[str, Any]:
    resource_ref = f"{provider}:{account}"
    observed_at_text = observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    reasons: list[str] = []

    enabled_flag = resource.get("enabled_flag")
    pool_enabled = pool.get("enabled") if pool is not None else None
    has_credential = resource.get("has_credential_ref") is True
    inline = resource.get("inline")
    owner_parked_verdict = _owner_parked_verdict(pool, account)
    parked_until_raw = _iso_z(resource.get("parked_until"))
    parked_until_dt = (
        datetime.strptime(parked_until_raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        if parked_until_raw is not None
        else None
    )
    owner_parked = owner_parked_verdict or (
        parked_until_dt is not None and parked_until_dt > observed_at
    )

    if owner_parked_verdict:
        reasons.append("owner_parked_verdict")
    elif parked_until_dt is not None and parked_until_dt > observed_at:
        reasons.append("parked_until_future")

    # Readiness verdict (registry-carried credential/profile verdicts only).
    if not has_credential:
        readiness = "missing_credential"
        reasons.append("credential_ref_absent")
    elif enabled_flag is False or pool_enabled is False:
        readiness = "disabled"
        reasons.append("disabled_by_configuration")
    elif enabled_flag == "auto" or pool_enabled == "auto":
        readiness = "auto_unresolved"
        reasons.append("enabled_flag_auto_unresolved")
    elif enabled_flag is not True or pool_enabled is not True:
        readiness = "unavailable"
        reasons.append("enabled_configuration_unqualified")
    elif owner_parked:
        readiness = "parked"
    else:
        readiness = "ready"

    # Configured ceilings — explicitly labeled configuration, never quota.
    per_account_cap = resource.get("per_account_cap")
    ceilings = (
        pool.get("configured_ceilings")
        if pool is not None and isinstance(pool.get("configured_ceilings"), Mapping)
        else None
    )
    pool_concurrency = ceilings.get("concurrent") if ceilings is not None else None
    if type(per_account_cap) is int:
        configured_cap = per_account_cap
        cap_basis = "accounts_yaml_per_account_cap"
    elif type(pool_concurrency) is int:
        configured_cap = pool_concurrency
        cap_basis = "pools_yaml_concurrent"
    else:
        configured_cap = None
        cap_basis = "no_configured_cap"

    active_slots = int(
        (broker.get("active_by_quota_scope") or {}).get(resource_ref, 0)
    )
    reserved_slots = int(
        (broker.get("reserved_by_pool_account") or {}).get(resource_ref, 0)
    )

    # Provider usage/limit/reset observations — only where actually exposed.
    remaining: float | int | None = None
    remaining_basis: str | None = None
    quota_observed_at: str | None = None
    quota_source: str | None = None
    reset_at: str | None = None
    registry_provenance: list[dict[str, Any]] = []
    inline_pct = inline.get("pct_7d") if isinstance(inline, Mapping) else None
    if inline_pct is not None:
        # Bailian 7-day per-key usage bucket exposed by the owner projection.
        registry_remaining = round(100.0 - float(inline_pct), 2)
        remaining = registry_remaining
        remaining_basis = "percent_of_window_remaining"
        quota_observed_at = projection_produced_at
        quota_source = "bailian_inline_7d_local_reconstruction"
        reset_at = _inline_reset_at(pool, account)
        if emit_provenance:
            registry_provenance.append(
                {
                    "source_kind": "registry",
                    "field": "remaining_quota",
                    "source": quota_source,
                    "observed_at": quota_observed_at,
                }
            )
    if remaining is None and pool_usage is not None and account == "default":
        # Owner-exposed provider window observation (e.g. grok weekly).
        registry_remaining = pool_usage.get("remaining")
        remaining = registry_remaining
        remaining_basis = "percent_of_window_remaining"
        quota_observed_at = pool_usage.get("observed_at")
        quota_source = str(pool_usage.get("source") or "pool_windows")
        reset_at = pool_usage.get("reset_at")
        if emit_provenance:
            registry_provenance.append(
                {
                    "source_kind": "registry",
                    "field": "remaining_quota",
                    "source": quota_source,
                    "observed_at": quota_observed_at,
                }
            )

    # Live observation (OQ-3): supersedes an unknown and may supersede a
    # registry fact for the same field while keeping both provenance
    # entries. A typed unknown NEVER converts to a number.
    if observation is not None and observation.observed:
        provenance = observation.provenance or {}
        remaining = _bounded_number(observation.usage)
        remaining_basis = observation.usage_unit
        quota_observed_at = provenance.get("observed_at")
        if provenance.get("source_kind") == "local_gateway_state":
            if provenance.get("source_ref"):
                quota_source = (
                    f"local_gateway_state:{provenance['source_ref']}"
                )
        elif provenance.get("endpoint_host_path"):
            quota_source = f"provider_api:{provenance['endpoint_host_path']}"
        if observation.reset_at is not None:
            reset_at = observation.reset_at
    elif observation is not None and not observation.observed:
        reasons.append(str(observation.reason_code))

    quota_knowledge = "observed" if remaining is not None else "unknown"
    if quota_knowledge == "unknown":
        # OQ-3: no bounded unknown-quota mode is authorized yet, so an
        # unobserved bucket stays unavailable for autonomous placement.
        reasons.append("quota_unknown_no_bounded_unknown_mode_authorized")

    # Preserve every attributed observation. The incumbent account_cap uses
    # an exact default scope as HARD; qualified adaptive Bailian SOFT feedback
    # only lowers its concurrency ceiling and must not become a HARD denial.
    cooldown_until: str | None = None
    cooldown_source = "lease_broker_quota_cooldown" if cooldown else None
    effective_cap = configured_cap
    hard_blocked = False
    cooldown_active = False
    for entry in cooldown or ():
        until_text = entry.get("until")
        until_dt = (datetime.strptime(until_text, "%Y-%m-%dT%H:%M:%SZ")
                    .replace(tzinfo=timezone.utc)) if until_text is not None else None
        if until_text is not None:
            cooldown_until = max(cooldown_until or until_text, until_text)
        active = until_dt is not None and until_dt > observed_at
        cooldown_active = cooldown_active or active
        if entry.get("scope") == resource_ref:
            if until_dt is None or active:
                hard_blocked = True
                effective_cap = 0
            elif effective_cap is not None:
                effective_cap = min(effective_cap, 1)  # incumbent half-open bound
        elif (provider == "bailian"
              and entry.get("scope") == f"bailian-adaptive429:{account}"
              and entry.get("mode") == "SOFT" and active):
            soft_cap = entry.get("soft_cap")
            if type(soft_cap) is int and soft_cap >= 3 and effective_cap is not None:
                effective_cap = min(effective_cap, soft_cap)
    if cooldown_active:
        reasons.append("cooldown_active")
    elif cooldown_until is not None:
        reasons.append("cooldown_elapsed")
    if hard_blocked:
        reasons.append("hard_cooldown_blocks_preview")
    elif effective_cap != configured_cap:
        reasons.append("broker_cooldown_lowers_concurrency")
    if not cooldown and owner_parked and parked_until_raw is not None:
        cooldown_until = parked_until_raw
        cooldown_source = "registry_parked_until"

    # Admission eligibility for autonomous placement (preview-only verdict).
    eligible = not hard_blocked
    if readiness != "ready":
        eligible = False
    if configured_cap is None:
        reasons.append("no_configured_concurrency_cap")
        eligible = False
    if active_slots + reserved_slots >= (effective_cap or 0):
        reasons.append("concurrency_cap_reached")
        eligible = False
    if quota_knowledge == "observed" and remaining is not None and remaining <= 0:
        reasons.append("quota_exhausted")
        eligible = False
    if quota_knowledge == "unknown":
        eligible = False
    if quota_knowledge == "observed":
        if quota_observed_at is None:
            remaining = None
            remaining_basis = None
            quota_knowledge = "unknown"
            reasons.append("quota_observation_timestamp_unqualified")
            eligible = False
        else:
            observed_dt = datetime.strptime(
                quota_observed_at, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            if observed_dt > observed_at:
                reasons.append("quota_observation_in_future")
                eligible = False
            elif (observed_at - observed_dt) > timedelta(days=7):
                reasons.append("quota_observation_stale")
                eligible = False
    if eligible:
        reasons.insert(0, "eligible_in_preview")
    if quota_source == "bailian_inline_7d_local_reconstruction":
        reasons.append("quota_source_local_reconstruction")

    if len(reasons) > MAX_REASON_CODES:
        _refuse("QUOTA_PREVIEW_SCHEMA_INVALID", "too many reason codes")

    observation_id = hashlib.sha256(
        _canonical_bytes(
            {
                "resource": resource_ref,
                "registry_revision": registry_revision,
                "observed_at": observed_at_text,
            }
        )
    ).hexdigest()[:16]

    row: dict[str, Any] = {
        # registry_provenance appended conditionally below (observations path only)
        "pool_ref": provider,
        "shared_quota_resource_ref": resource_ref,
        "provider_ref": provider,
        "auth_route_ref": (pool.get("access_route") if pool is not None else None),
        "registry_revision": registry_revision,
        "source_owner_ref": SOURCE_OWNER_REF,
        "observation_id": observation_id,
        "observed_at": observed_at_text,
        "expires_at": expires_at,
        "readiness_state": readiness,
        "configured_concurrency_cap": configured_cap,
        "configured_cap_basis": cap_basis,
        "broker_limited_concurrency_cap": effective_cap,
        "active_slots": active_slots,
        "reserved_slots": reserved_slots,
        "remaining_quota": remaining,
        "remaining_quota_basis": remaining_basis,
        "reset_at": reset_at,
        "quota_knowledge": quota_knowledge,
        "quota_observed_at": quota_observed_at,
        "quota_source": quota_source,
        "cooldown_until": cooldown_until,
        "cooldown_source": cooldown_source,
        "admission_eligibility": eligible,
        "reason_codes": reasons,
    }
    if observation is not None and observation.observed:
        raw_provenance = dict(observation.provenance or {})
        provenance_block: dict[str, Any] = {
            "source_kind": raw_provenance.get("source_kind") or "provider_api",
            "observed_at": raw_provenance.get("observed_at"),
            "expires_at": raw_provenance.get("expires_at"),
            "confidence": raw_provenance.get("confidence"),
        }
        if raw_provenance.get("source_kind") == "local_gateway_state":
            provenance_block["source_ref"] = raw_provenance.get("source_ref")
        else:
            provenance_block["endpoint_host_path"] = raw_provenance.get(
                "endpoint_host_path"
            )
            provenance_block["http_status"] = raw_provenance.get("http_status")
        windows = (observation.details or {}).get("windows")
        if windows is not None:
            provenance_block["windows"] = windows
        row["quota_observation"] = provenance_block
        row["provenance"] = list(registry_provenance) + [
            {
                "source_kind": provenance_block["source_kind"],
                "field": "remaining_quota",
                "endpoint_host_path": provenance_block.get("endpoint_host_path"),
                "source_ref": provenance_block.get("source_ref"),
                "observed_at": provenance_block.get("observed_at"),
            }
        ]
    return row


def _owner_parked_verdict(pool: Mapping[str, Any] | None, account: str) -> bool:
    """Owner-recorded park verdict for an inline key bucket, if exposed.

    The WO-03 projection carries the verdict only on the pool's inline key
    entries (e.g. bailian ``parked: true``); it is read verbatim and never
    re-derived from usage percentages here.
    """
    if pool is None:
        return False
    entries = pool.get("inline_key_entries")
    if not isinstance(entries, Sequence):
        return False
    for entry in entries:
        if (
            isinstance(entry, Mapping)
            and entry.get("name") == account
            and entry.get("parked") is True
        ):
            return True
    return False


def _inline_reset_at(pool: Mapping[str, Any] | None, account: str) -> str | None:
    """Owner-recorded per-key reset time from the pool's inline entries."""
    entries = pool.get("inline_key_entries") if pool is not None else None
    if not isinstance(entries, Sequence):
        return None
    for entry in entries:
        if isinstance(entry, Mapping) and entry.get("name") == account:
            return _iso_z(entry.get("resets_at"))
    return None


def _build_option(
    row: Mapping[str, Any],
    pool: Mapping[str, Any] | None,
    priority_order: Sequence[str],
) -> dict[str, Any] | None:
    """One consumer option per admission-eligible resource with a model alias.

    ``estimated_startable_jobs`` is a configured-capacity estimate
    (``cap - active - reserved``) labeled configuration; it is never an
    observed provider-quota claim.
    """
    if not row["admission_eligibility"]:
        return None
    model_alias = _resolve_model_alias(pool)
    if model_alias is None:
        return None
    cap = row["broker_limited_concurrency_cap"]
    if type(cap) is not int or cap <= 0:
        return None
    estimate = max(0, cap - row["active_slots"] - row["reserved_slots"])
    if estimate <= 0:
        return None
    provider = row["provider_ref"]
    priority = (
        priority_order.index(provider)
        if provider in priority_order
        else len(priority_order)
    )
    return {
        "_priority": priority,
        "option_id": row["shared_quota_resource_ref"],
        "provider": provider,
        "model_alias": model_alias,
        "eligible_in_preview": True,
        "estimated_startable_jobs": estimate,
        "suggested_parallelism": estimate,
        "expiry_pressure_jobs_per_hour": None,
        "estimate_basis": (
            "configured_concurrency_minus_broker_active_reserved"
            if cap == row["configured_concurrency_cap"] else
            "configured_concurrency_limited_by_broker_cooldown_minus_active_reserved"
        ),
    }


def _resolve_model_alias(pool: Mapping[str, Any] | None) -> str | None:
    if pool is None:
        return None
    models = pool.get("models")
    if not isinstance(models, Mapping):
        return None
    default = models.get("default")
    if isinstance(default, str) and default:
        return default
    worker_models = models.get("worker_models")
    if (
        isinstance(worker_models, Sequence)
        and not isinstance(worker_models, (str, bytes))
        and worker_models
        and isinstance(worker_models[0], str)
        and worker_models[0]
    ):
        return worker_models[0]
    return None


__all__ = [
    "MAX_REASON_CODES",
    "MAX_RESOURCES",
    "PREVIEW_LIFETIME_SECONDS",
    "PREVIEW_STATUS_NO_ELIGIBLE",
    "PREVIEW_STATUS_READY",
    "PROJECTION_SCHEMA",
    "SELECTED_TIER_LABEL",
    "SOURCE_OWNER_REF",
    "QuotaEconomicsPreview",
    "QuotaEconomicsPreviewError",
    "produce_quota_economics_preview",
    "read_broker_observation",
]
