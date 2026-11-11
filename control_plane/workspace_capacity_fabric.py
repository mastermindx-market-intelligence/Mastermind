"""Public projection of existing quota previews and H2 account observations.

No collector, refresh, configuration store, eligibility decision or reservation.
All inputs are selected by the installed owner, never an HTTP caller. The preview
is WO-09's existing artifact; optional callbacks are pure incumbent owner READs.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from common import workspace_capacity_fabric_contract as wire
from common.executive_workspace_contract import canonical

PREVIEW_SCHEMA = "mastermind.quota_economics_preview/v1"
WINDOW_TTL = 600
_DEFAULT_WINDOWS = {"glm": ("5h", "weekly"), "minimax": ("5h", "weekly"),
                    "go": ("5h", "weekly", "monthly")}
_MAIN_WINDOWS = ("5h", "weekly", "monthly")
_MAX_SOURCE_BYTES = 2 * 1024 * 1024


class CapacitySourceError(ValueError):
    def __init__(self, reason="SOURCE_UNAVAILABLE"):
        self.reason = reason
        super().__init__(reason)


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CapacitySourceError()
        result[key] = value
    return result


def _regular_json(path: Path):
    """One bounded coherent read, refusing links, special files and replacement."""
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= _MAX_SOURCE_BYTES:
            raise CapacitySourceError()
        chunks, size = [], 0
        while size <= _MAX_SOURCE_BYTES:
            chunk = os.read(fd, min(65536, _MAX_SOURCE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after, current = os.fstat(fd), os.stat(path, follow_symlinks=False)
        signature = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if size > _MAX_SOURCE_BYTES or signature(before) != signature(after) or signature(after) != signature(current):
            raise CapacitySourceError("SOURCE_CHANGED")
        raw = b"".join(chunks)
        data = json.loads(raw, object_pairs_hook=_no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(CapacitySourceError()))
        if type(data) is not dict:
            raise CapacitySourceError()
        return data, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def _stamp(value):
    try:
        return wire.timestamp(value)
    except (ValueError, TypeError, OverflowError):
        return None


def _time(value):
    return value if _stamp(value) is not None else None


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def _count(value):
    return value if wire.number(value, integer=True) else None


def _window(name, required, candidates, qualified, now):
    item = {"window": name, "required": required, "remaining_pct": None,
            "observed_at": None, "reset_at": None, "state": "UNKNOWN", "reason": "WINDOW_MISSING"}
    if len(candidates) != 1:
        if candidates:
            item["reason"] = "WINDOW_AMBIGUOUS"
        return item, None
    source = candidates[0]
    item["observed_at"], item["reset_at"] = _time(source.get("observed_at")), _time(source.get("reset_at"))
    stamp, reset = _stamp(item["observed_at"]), _stamp(item["reset_at"])
    pct = source.get("remaining_pct")
    if not qualified or source.get("source") != "PROVIDER_AUTHORITATIVE":
        item.update(state="UNQUALIFIED", reason="SOURCE_UNQUALIFIED")
    elif stamp is None or not 0 <= now - stamp < WINDOW_TTL:
        item.update(state="STALE", reason="OBSERVATION_STALE_OR_INVALID")
    elif source.get("reset_at") is not None and (reset is None or reset <= now):
        item.update(state="STALE", reason="RESET_REQUIRES_OBSERVATION")
    elif not wire.number(pct, maximum=100):
        item["reason"] = "BALANCE_UNKNOWN"
    elif not (source.get("ready") is True or source.get("reason") == "EXHAUSTED"):
        item.update(state="UNQUALIFIED", reason="SOURCE_UNQUALIFIED")
    elif (source.get("reason") == "EXHAUSTED") != (pct == 0):
        item.update(state="UNQUALIFIED", reason="SOURCE_UNQUALIFIED")
    else:
        item.update(state="EXHAUSTED" if pct == 0 else "CURRENT", reason="EXHAUSTED" if pct == 0 else "CURRENT",
                    remaining_pct=pct)
        return item, min(stamp + WINDOW_TTL, reset) if reset is not None else stamp + WINDOW_TTL
    return item, None


def _source_binding(value):
    """Current incumbent registry and H2 bindings, never merely a cache epoch."""
    if (type(value) is not dict or set(value) != {"registry_revision", "accounts", "consumer_revision"}
            or not wire.token(value["registry_revision"]) or type(value["accounts"]) is not dict
            or len(value["accounts"]) > wire.MAX_RESOURCES
            or value["consumer_revision"] is not None and not wire.token(value["consumer_revision"])):
        raise CapacitySourceError()
    for ref, binding in value["accounts"].items():
        if (not wire.token(ref) or type(binding) is not dict
                or set(binding) != {"config_generation", "account_generation", "allowance_scope", "endpoint", "broker_scope"}
                or not wire.token(binding["config_generation"])
                or any(binding[key] is not None and not wire.token(binding[key]) for key in ("account_generation", "allowance_scope", "broker_scope"))
                or type(binding["endpoint"]) is not str or not 0 < len(binding["endpoint"]) <= 2048):
            raise CapacitySourceError()
    if len(canonical(value)) > 262144:
        raise CapacitySourceError()
    return value


def _resource(source, view, binding, now):
    if type(source) is not dict:
        raise CapacitySourceError()
    ref, provider, pool = (source.get(key) for key in ("shared_quota_resource_ref", "provider_ref", "pool_ref"))
    if not all(wire.token(x) for x in (ref, provider, pool)) or not ref.startswith(provider + ":"):
        raise CapacitySourceError()
    account = ref[len(provider) + 1:]
    view = view if type(view) is dict else {}
    matched = view.get("provider") == provider and view.get("account") == account
    windows = view.get("windows", []) if matched else []
    if type(windows) is not list or len(windows) > 16 or any(type(row) is not dict or not wire.token(row.get("window")) for row in windows):
        raise CapacitySourceError()
    supplied_names = [row["window"] for row in windows]
    required = set(_DEFAULT_WINDOWS.get(provider, supplied_names or _MAIN_WINDOWS)) | set(supplied_names)
    names = list(dict.fromkeys([*_MAIN_WINDOWS, *sorted(required)]))
    qualified = (matched and type(binding) is dict and not view.get("refresh_error")
                 and all(view.get(key) == binding[key] for key in ("config_generation", "account_generation", "allowance_scope", "endpoint")))
    projected, deadlines = [], []
    for name in names:
        row, deadline = _window(name, name in required, [x for x in windows if x["window"] == name], qualified, now)
        projected.append(row)
        if deadline is not None:
            deadlines.append(deadline)
    identity = bool(qualified and wire.token(view.get("allowance_scope")) and wire.token(view.get("account_generation")))
    reason_codes = source.get("reason_codes", [])
    if type(reason_codes) is not list or len(reason_codes) > 16 or any(not wire.token(x) for x in reason_codes):
        raise CapacitySourceError()
    readiness = source.get("readiness_state")
    if not wire.token(readiness):
        raise CapacitySourceError()
    cap, active, queued = (_count(source.get(x)) for x in ("configured_concurrency_cap", "active_slots", "reserved_slots"))
    cap_basis = {"accounts_yaml_per_account_cap": "ACCOUNT", "pools_yaml_concurrent": "POOL"}.get(source.get("configured_cap_basis"), "UNKNOWN")
    # WO-09 currently attributes held/rented leases using provider:account. An
    # explicitly declared shared broker scope cannot be counted through that key.
    if type(binding) is not dict or binding["broker_scope"] != ref:
        active = None
    # WO-09 reserved_slots counts broker waiters, not admitted reservations.
    cooldown = _time(source.get("cooldown_until"))
    valid_windows = [w for w in projected if w["required"]]
    if readiness != "ready":
        pressure = "UNAVAILABLE"
    elif (cooldown is not None and wire.timestamp(cooldown) > now) or "cooldown_active" in reason_codes:
        pressure = "COOLDOWN"
    elif any(w["state"] == "EXHAUSTED" for w in valid_windows):
        pressure = "LIMIT_REACHED"
    elif cap_basis == "ACCOUNT" and cap is not None and active is not None and active >= cap:
        pressure = "SLOTS_OCCUPIED"
    elif not valid_windows or any(w["state"] != "CURRENT" for w in valid_windows):
        pressure = "UNKNOWN"
    elif min(w["remaining_pct"] for w in valid_windows) <= 20:
        pressure = "LOW_ALLOWANCE"
    else:
        # This describes allowance evidence only; it never overrides admission.
        pressure = "HEADROOM_RECORDED"
    scalar = source.get("remaining_quota")
    scalar_source = source.get("quota_source")
    scalar_observed = _stamp(source.get("quota_observed_at"))
    scalar_reset = _stamp(source.get("reset_at"))
    scalar_basis = "UNKNOWN"
    if type(scalar_source) is str and "local_reconstruction" in scalar_source:
        scalar_basis = "LOCAL_ESTIMATE"
    elif type(scalar_source) is str and source.get("quota_knowledge") == "observed":
        scalar_basis = "RECORDED_OBSERVATION"
    scalar_current = (wire.number(scalar, maximum=100)
        and source.get("remaining_quota_basis") == "percent_of_window_remaining"
        and scalar_basis != "UNKNOWN" and scalar_observed is not None
        and 0 <= now - scalar_observed < WINDOW_TTL
        and (source.get("reset_at") is None or scalar_reset is not None and now < scalar_reset))
    if scalar_current:
        deadlines.append(min(scalar_observed + WINDOW_TTL, scalar_reset)
                         if scalar_reset is not None else scalar_observed + WINDOW_TTL)
    return {"resource_ref": ref, "provider": provider, "pool": pool,
            "allowance_scope": view.get("allowance_scope") if identity else None,
            "identity_qualified": identity, "readiness": readiness,
            "configured_concurrency": cap, "configured_cap_basis": cap_basis, "active": active, "queued": queued,
            "cooldown_until": cooldown, "pressure": pressure, "reason_codes": reason_codes,
            "windows": projected, "preview_eligible": source.get("admission_eligibility") if type(source.get("admission_eligibility")) is bool else None,
            "single_window_remaining_pct": scalar if scalar_current else None,
            "single_window_observed_at": source["quota_observed_at"] if scalar_current else None,
            "single_window_source": scalar_basis}, deadlines


def project_capacity_fabric(preview, *, binding, account_views=None, consumer_views=None, now):
    """Allowlist existing observations; never turn a preview into execution truth."""
    if type(now) not in (int, float) or not math.isfinite(now) or now <= 0:
        raise CapacitySourceError()
    if type(preview) is not dict or preview.get("schema") != PREVIEW_SCHEMA:
        raise CapacitySourceError()
    binding = _source_binding(binding)
    if preview.get("registry_revision") != binding["registry_revision"]:
        raise CapacitySourceError("SOURCE_CHANGED")
    asof, expiry = _stamp(preview.get("as_of")), _stamp(preview.get("expires_at"))
    if asof is None or expiry is None or not 0 < expiry - asof <= wire.MAX_PREVIEW_LIFETIME_SECONDS or asof > now:
        raise CapacitySourceError()
    if now >= expiry:
        raise CapacitySourceError("SOURCE_EXPIRED")
    if (preview.get("authority") != "NONE_PREVIEW_ONLY" or preview.get("live_admission") is not False
            or preview.get("production_armed") is not False or preview.get("claim_time_revalidation_required") is not True):
        raise CapacitySourceError()
    sources = preview.get("resources")
    if type(sources) is not list or len(sources) > wire.MAX_RESOURCES or not wire.token(preview.get("registry_revision")):
        raise CapacitySourceError()
    account_views = account_views if type(account_views) is dict else {}
    consumer_views = consumer_views if type(consumer_views) is dict else {}
    rows, deadlines, refs = [], [expiry], set()
    for source in sources:
        ref = source.get("shared_quota_resource_ref") if type(source) is dict else None
        if not wire.token(ref) or ref in refs:
            raise CapacitySourceError()
        refs.add(ref)
        # Every row belongs to this exact original preview, not another registry.
        if source.get("registry_revision") != preview["registry_revision"] or source.get("observed_at") != preview["as_of"] or source.get("expires_at") != preview["expires_at"]:
            raise CapacitySourceError("SOURCE_CHANGED")
        row, expires = _resource(source, account_views.get(ref), binding["accounts"].get(ref), now)
        rows.append(row)
        deadlines.extend(expires)
    # A shared allowance is never summed. Conflicting observations with the same
    # qualified identity are withdrawn instead of selecting the rosier snapshot.
    scopes = {}
    for row in rows:
        if row["identity_qualified"]:
            scopes.setdefault(row["allowance_scope"], []).append(row)
    for members in scopes.values():
        if len({canonical(row["windows"]) for row in members}) > 1:
            for row in members:
                row["pressure"] = "UNKNOWN"
                row["reason_codes"] = [*row["reason_codes"], "SHARED_ALLOWANCE_CONFLICT"]
                row["windows"] = [{**w, "state": "UNQUALIFIED", "remaining_pct": None, "reason": "SHARED_ALLOWANCE_CONFLICT"} for w in row["windows"]]
    consumers = []
    for name in wire.CONSUMERS:
        item = {"consumer": name, "source_state": "SPEC_ONLY" if name == "t3_code" else "BUILT",
                "runtime_state": "NOT_OBSERVED", "observed_at": None, "evidence_ref": None}
        evidence = consumer_views.get(name)
        if type(evidence) is dict:
            stamp, until = _stamp(evidence.get("observed_at")), _stamp(evidence.get("expires_at"))
            if (stamp is not None and until is not None and stamp <= now < until and 0 < until - stamp <= wire.MAX_CONSUMER_RECEIPT_SECONDS
                    and binding["consumer_revision"] is not None
                    and evidence.get("source_revision") == binding["consumer_revision"]
                    and evidence.get("runtime_state") in wire.RUNTIME_STATES - {"NOT_OBSERVED"}
                    and wire.token(evidence.get("evidence_ref"))):
                # A qualified installed enrollment/run/result receipt also
                # establishes that this consumer has implementation source.
                # Do not retain T3's baseline SPEC_ONLY label after real proof.
                item.update(source_state="BUILT", runtime_state=evidence["runtime_state"],
                            observed_at=evidence["observed_at"], evidence_ref=evidence["evidence_ref"])
                deadlines.append(until)
        consumers.append(item)
    pressures = {row["pressure"] for row in rows}
    advice = []
    for states, code in (({"UNKNOWN"}, "UPDATE_USAGE"), ({"LIMIT_REACHED", "COOLDOWN"}, "WAIT_FOR_RESET"),
                         ({"LOW_ALLOWANCE"}, "CONSERVE_ALLOWANCE"), ({"SLOTS_OCCUPIED"}, "REVIEW_QUEUE"),
                         ({"HEADROOM_RECORDED"}, "REVIEW_ROUTING")):
        if pressures & states:
            advice.append(code)
    if pressures & {"LOW_ALLOWANCE", "LIMIT_REACHED", "SLOTS_OCCUPIED"}:
        advice.append("MEASURE_DEMAND")
    if "REVIEW_QUEUE" not in advice and any(row["queued"] is not None and row["queued"] > 0 for row in rows):
        advice.append("REVIEW_QUEUE")
    evidence_digest = hashlib.sha256(canonical({"preview": preview, "binding": binding,
                                              "windows": account_views, "consumers": consumer_views})).hexdigest()
    return wire.validate_result({"schema": wire.BODY_SCHEMA, "availability": "AVAILABLE", "reason_codes": [],
            "observed_at": preview["as_of"], "expires_at": _iso(min(deadlines)),
            "source_revision": evidence_digest, "resources": rows, "consumers": consumers,
            "recommendations": advice, "admission_authorized": False}, now=now)


@dataclass(frozen=True)
class ExistingCapacityFabricSource:
    """Installed read adapter; no defaults, environment lookup or HTTP paths.

    ``preview_path`` is the incumbent WO-09 output already selected by the host.
    ``account_views`` must invoke cache-only H2/account_quota_view, never a refresh.
    ``current_revision`` returns the original owner's current binding, with exact
    keys ``registry_revision``, ``accounts`` and ``consumer_revision``. Account
    entries contain ``config_generation``, ``account_generation``,
    ``allowance_scope``, ``endpoint`` and incumbent ``broker_scope``. It must read the current owner, not the
    retained quota cache. Every view is matched to that binding and the complete
    binding is rechecked after reading. Consumer receipts must carry its current
    ``source_revision``. This adapter creates no registry or generation owner.
    """
    preview_path: Path
    account_views: Callable | None = None
    consumer_views: Callable | None = None
    current_revision: Callable | None = None
    now: Callable = lambda: datetime.now(timezone.utc).timestamp()

    def __post_init__(self):
        if not isinstance(self.preview_path, Path) or not self.preview_path.is_absolute():
            raise ValueError("installed_absolute_preview_required")
        if any(value is not None and not callable(value) for value in (self.account_views, self.consumer_views, self.current_revision, self.now)):
            raise ValueError("installed_readers_required")
        if self.current_revision is None:
            raise ValueError("original_owner_generation_required")

    def read(self):
        try:
            binding = _source_binding(self.current_revision())
            generation = canonical(binding)
            preview, digest = _regular_json(self.preview_path)
            refs = tuple(row["shared_quota_resource_ref"] for row in preview.get("resources", [])[:wire.MAX_RESOURCES + 1])
            windows = self.account_views(refs) if self.account_views is not None else {}
            consumers = self.consumer_views() if self.consumer_views is not None else {}
            if type(windows) is not dict or type(consumers) is not dict or len(canonical(windows)) > _MAX_SOURCE_BYTES or len(canonical(consumers)) > 16384:
                raise CapacitySourceError()
            body = project_capacity_fabric(preview, binding=binding, account_views=windows, consumer_views=consumers, now=self.now())
            _, after = _regular_json(self.preview_path)
            if after != digest or canonical(_source_binding(self.current_revision())) != generation:
                raise CapacitySourceError("SOURCE_CHANGED")
            released_at = self.now()
            if released_at >= wire.timestamp(body["expires_at"]):
                raise CapacitySourceError("SOURCE_EXPIRED")
            wire.validate_result(body, now=released_at)
            return {"ok": True, "result": body}
        except CapacitySourceError as exc:
            return wire.unavailable(exc.reason)
        except Exception:
            return wire.unavailable()
