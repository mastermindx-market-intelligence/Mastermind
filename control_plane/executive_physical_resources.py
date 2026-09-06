"""Storeless contracts and accounting predicates for physical resources.

This module performs no I/O except reading the one policy document. It owns no
database, runtime, effect runner, queue, retry, or host sampler.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "mastermind.physical_resource_policy.v1"
DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "config" / "executive_physical_resources.json"
INT64_MAX = (1 << 63) - 1
DIMENSION_UNITS = {"memory_bytes": "bytes", "disk_bytes": "bytes", "cpu_us_per_window": "cpu_us", "io_bytes_per_window": "io_bytes", "heavy_phase_count": "count"}
_REQUEST_KEYS = frozenset({"operation_key", "host_id", "boot_id", "owner_id", "carrier_id", "command_id", "source_binding", "policy_binding", "caller_binding", "acquisition_time_ms", "phases"})
_SOURCE_KEYS = frozenset({"commit_sha", "helper_sha256", "common_git_store", "destination"})
_COMMON_STORE_KEYS = frozenset({"realpath", "device", "inode"})
_DESTINATION_KEYS = frozenset({"realpath", "device", "capacity_pool_id"})
_POLICY_BINDING_KEYS = frozenset({"revision", "sha256"})
_CALLER_KEYS = frozenset({"session_id", "pid", "start_id"})
_PHASE_KEYS = frozenset({"phase_key", "profile", "duration_ms", "effect_scope", "demands"})
_DEMAND_KEYS = frozenset({"dimension", "capacity_pool_id", "qualified_incremental_peak", "window_binding"})
_WINDOW_KEYS = frozenset({"unit", "window_ms", "baseline_id", "boot_id"})
_POLICY_KEYS = frozenset({"schema", "production_armed", "qualification", "policy_revision", "authority_receipt", "qualification_evidence", "canonical_runtime", "physical_pools", "allowed_callers", "profiles", "windows", "limits", "freshness", "waits", "recovery"})
_RUNTIME_KEYS = frozenset({"runtime_id", "host_id", "boot_id", "endpoint", "database_identity", "schema_identity"})
_WINDOW_POLICY_KEYS = frozenset({"cpu_window_ms", "io_window_ms", "normalization_evidence"})
_LIMIT_KEYS = frozenset({"cpu_budget_us", "cpu_protected_us", "memory_budget_bytes", "memory_protected_bytes", "internal_protected_bytes", "external_protected_bytes", "io_budget_bytes", "io_protected_bytes", "max_heavy_phases"})
_FRESHNESS_KEYS = frozenset({"sample_max_age_ms", "sample_cadence_ms", "decision_to_effect_max_ms"})
_WAIT_KEYS = frozenset({"service_request_max_ms", "database_lock_max_ms"})
_RECOVERY_KEYS = frozenset({"reservation_horizon_ms", "reconciliation_interval_ms"})
_PROFILE_KEYS = frozenset({"profile", "qualified_duration_ms", "qualification_evidence", "effect_scope", "qualified_demands"})
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PhysicalResourceRefusal(ValueError):
    """Typed fail-closed refusal from the pure M2 contract."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


def _refuse(code: str, message: str) -> None:
    raise PhysicalResourceRefusal(code, message)


def _mapping(value: object, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        _refuse("INVALID_CONTRACT", f"{label} must contain exactly {sorted(keys)}")
    return value


def _nonempty(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 512:
        _refuse("INVALID_CONTRACT", f"{label} must be bounded nonempty text")
    return value


def _uint(value: object, label: str) -> int:
    if type(value) is not int or value < 0 or value > INT64_MAX:
        _refuse("INVALID_NUMERIC_FIELD", f"{label} must be a nonnegative signed-64 integer")
    return value


def _positive(value: object, label: str) -> int:
    value = _uint(value, label)
    if value == 0:
        _refuse("INVALID_NUMERIC_FIELD", f"{label} must be positive")
    return value


def _sum64(values: Sequence[int], label: str) -> int:
    total = 0
    for value in values:
        value = _uint(value, label)
        if total > INT64_MAX - value:
            _refuse("NUMERIC_OVERFLOW", f"{label} exceeds signed-64 range")
        total += value
    return total


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _refuse("INVALID_CONTRACT", f"duplicate policy key: {key}")
        result[key] = value
    return result


def load_physical_resource_policy(path: Path | str = DEFAULT_POLICY_PATH, *, claimed_context: object | None = None) -> dict[str, Any]:
    """Read the single production policy; source defaults never arm admission."""
    if claimed_context is not None:
        _refuse("CLAIMED_CONTEXT_REFUSED", "caller-claimed verification is never authority")
    try:
        policy = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_pairs_no_duplicates)
    except PhysicalResourceRefusal:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _refuse("POLICY_INVALID", f"physical resource policy is unreadable: {exc}")
    _validate_policy(policy, allow_synthetic=False)
    if policy["production_armed"]:
        _refuse("RESOURCE_SCHEMA_UNADMITTED", "no production M2 schema/runtime adapter is admitted")
    return copy.deepcopy(policy)


def _validate_policy(policy: object, *, allow_synthetic: bool) -> Mapping[str, Any]:
    policy = _mapping(policy, _POLICY_KEYS, "policy")
    if policy["schema"] != POLICY_SCHEMA or type(policy["production_armed"]) is not bool:
        _refuse("POLICY_INVALID", "policy schema or armed state is invalid")
    qualification = policy["qualification"]
    runtime = _mapping(policy["canonical_runtime"], _RUNTIME_KEYS, "canonical_runtime")
    windows = _mapping(policy["windows"], _WINDOW_POLICY_KEYS, "windows")
    limits = _mapping(policy["limits"], _LIMIT_KEYS, "limits")
    freshness = _mapping(policy["freshness"], _FRESHNESS_KEYS, "freshness")
    waits = _mapping(policy["waits"], _WAIT_KEYS, "waits")
    recovery = _mapping(policy["recovery"], _RECOVERY_KEYS, "recovery")
    for key in ("physical_pools", "allowed_callers", "profiles", "qualification_evidence"):
        if type(policy[key]) is not list:
            _refuse("POLICY_INVALID", f"policy.{key} must be a list")
    if qualification == "SYNTHETIC_TEST_ONLY" and not allow_synthetic:
        _refuse("SYNTHETIC_POLICY_REFUSED", "synthetic policy cannot enter production")
    if not policy["production_armed"]:
        nullable = [policy["policy_revision"], policy["authority_receipt"], *runtime.values(), *windows.values(), *limits.values(), *freshness.values(), *waits.values(), *recovery.values()]
        if qualification != "UNQUALIFIED" or any(value is not None for value in nullable):
            _refuse("POLICY_INVALID", "unarmed source policy must preserve explicit null qualification")
        if any(policy[key] for key in ("physical_pools", "allowed_callers", "profiles", "qualification_evidence")):
            _refuse("POLICY_INVALID", "unarmed source policy cannot contain grants")
        return policy
    if policy["production_armed"]:
        accepted = {"SYNTHETIC_TEST_ONLY"} if allow_synthetic else {"QUALIFIED"}
        if qualification not in accepted:
            _refuse("POLICY_UNQUALIFIED", "armed policy lacks accepted qualification")
        _nonempty(policy["policy_revision"], "policy.policy_revision")
        _nonempty(policy["authority_receipt"], "policy.authority_receipt")
        if type(policy["qualification_evidence"]) is not list or not policy["qualification_evidence"]:
            _refuse("POLICY_UNQUALIFIED", "qualification evidence is required")
        for key, value in runtime.items():
            _nonempty(value, f"canonical_runtime.{key}")
        for group_name, group in (("windows", windows), ("limits", limits), ("freshness", freshness), ("waits", waits), ("recovery", recovery)):
            for key, value in group.items():
                if key == "normalization_evidence":
                    _nonempty(value, f"{group_name}.{key}")
                else:
                    _uint(value, f"{group_name}.{key}")
        seen_pools: set[str] = set()
        for pool in policy["physical_pools"]:
            pool = _mapping(pool, frozenset({"capacity_pool_id", "protected_reserve"}), "physical_pool")
            pool_id = _nonempty(pool["capacity_pool_id"], "physical_pool.capacity_pool_id")
            if pool_id in seen_pools:
                _refuse("POLICY_INVALID", "physical pool IDs must be unique")
            seen_pools.add(pool_id)
            _uint(pool["protected_reserve"], "physical_pool.protected_reserve")
        for caller in policy["allowed_callers"]:
            caller = _mapping(caller, frozenset({"owner_id", "carrier_id", "session_id"}), "allowed_caller")
            for key, value in caller.items():
                _nonempty(value, f"allowed_caller.{key}")
        seen_profiles: set[str] = set()
        for profile in policy["profiles"]:
            profile = _mapping(profile, _PROFILE_KEYS, "profile")
            name = _nonempty(profile["profile"], "profile.profile")
            if name in seen_profiles:
                _refuse("POLICY_INVALID", "profile names must be unique")
            seen_profiles.add(name)
            _positive(profile["qualified_duration_ms"], "profile.qualified_duration_ms")
            if type(profile["qualification_evidence"]) is not list or not profile["qualification_evidence"]:
                _refuse("POLICY_UNQUALIFIED", "profile qualification evidence is required")
            for evidence in profile["qualification_evidence"]:
                _nonempty(evidence, "profile.qualification_evidence")
            if type(profile["effect_scope"]) is not list or not profile["effect_scope"]:
                _refuse("POLICY_INVALID", "profile effect scope must be nonempty")
            for effect in profile["effect_scope"]:
                _nonempty(effect, "profile.effect_scope")
            if type(profile["qualified_demands"]) is not list or not profile["qualified_demands"]:
                _refuse("POLICY_UNQUALIFIED", "qualified profile demands are required")
            for demand in profile["qualified_demands"]:
                demand = _mapping(demand, _DEMAND_KEYS, "profile.qualified_demand")
                dimension = demand["dimension"]
                if type(dimension) is not str or dimension not in DIMENSION_UNITS:
                    _refuse("POLICY_INVALID", "qualified demand dimension is invalid")
                _nonempty(demand["capacity_pool_id"], "profile.capacity_pool_id")
                _uint(demand["qualified_incremental_peak"], "profile.qualified_incremental_peak")
                window = _mapping(demand["window_binding"], _WINDOW_KEYS, "profile.window_binding")
                if window["unit"] != DIMENSION_UNITS[dimension]:
                    _refuse("POLICY_INVALID", "qualified demand window unit is invalid")
                _positive(window["window_ms"], "profile.window_binding.window_ms")
                _nonempty(window["baseline_id"], "profile.window_binding.baseline_id")
                if window["boot_id"] != runtime["boot_id"]:
                    _refuse("POLICY_INVALID", "qualified demand boot is not canonical")
    return policy


def validate_physical_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a closed request, aggregating duplicate pool rows."""
    request = _mapping(request, _REQUEST_KEYS, "request")
    for key in ("operation_key", "host_id", "boot_id", "owner_id", "carrier_id", "command_id"):
        _nonempty(request[key], f"request.{key}")
    if not request["command_id"].startswith("physical:"):
        _refuse("INVALID_CONTRACT", "command_id must use the reserved physical: namespace")
    _uint(request["acquisition_time_ms"], "request.acquisition_time_ms")
    source = _mapping(request["source_binding"], _SOURCE_KEYS, "source_binding")
    if type(source["commit_sha"]) is not str or not _HEX40.fullmatch(source["commit_sha"]):
        _refuse("INVALID_CONTRACT", "source commit must be lowercase canonical hex")
    if type(source["helper_sha256"]) is not str or not _HEX64.fullmatch(source["helper_sha256"]):
        _refuse("INVALID_CONTRACT", "helper hash must be lowercase canonical hex")
    common_store = _mapping(source["common_git_store"], _COMMON_STORE_KEYS, "common_git_store")
    destination = _mapping(source["destination"], _DESTINATION_KEYS, "destination")
    for value, label in ((common_store["realpath"], "common_git_store.realpath"), (destination["realpath"], "destination.realpath"), (destination["capacity_pool_id"], "destination.capacity_pool_id")):
        _nonempty(value, label)
    _uint(common_store["device"], "common_git_store.device")
    _uint(common_store["inode"], "common_git_store.inode")
    _uint(destination["device"], "destination.device")
    binding = _mapping(request["policy_binding"], _POLICY_BINDING_KEYS, "policy_binding")
    _nonempty(binding["revision"], "policy_binding.revision")
    if type(binding["sha256"]) is not str or not _HEX64.fullmatch(binding["sha256"]):
        _refuse("INVALID_CONTRACT", "policy hash must be lowercase canonical hex")
    caller = _mapping(request["caller_binding"], _CALLER_KEYS, "caller_binding")
    _nonempty(caller["session_id"], "caller_binding.session_id")
    _positive(caller["pid"], "caller_binding.pid")
    _nonempty(caller["start_id"], "caller_binding.start_id")
    phases = request["phases"]
    if type(phases) is not list or not phases:
        _refuse("INVALID_CONTRACT", "phases must be a nonempty ordered list")
    normalized = copy.deepcopy(dict(request))
    normalized_phases: list[dict[str, Any]] = []
    phase_keys: set[str] = set()
    for phase_index, raw_phase in enumerate(phases):
        phase = _mapping(raw_phase, _PHASE_KEYS, f"phases[{phase_index}]")
        phase_key = _nonempty(phase["phase_key"], "phase_key")
        if phase_key in phase_keys:
            _refuse("INVALID_CONTRACT", "phase keys must be unique")
        phase_keys.add(phase_key)
        profile = _nonempty(phase["profile"], "profile")
        duration_ms = _positive(phase["duration_ms"], "duration_ms")
        effect_scope = phase["effect_scope"]
        if type(effect_scope) is not list or not effect_scope:
            _refuse("INVALID_CONTRACT", "effect_scope must be duplicate-free and nonempty")
        for item in effect_scope:
            _nonempty(item, "effect_scope item")
        if len(set(effect_scope)) != len(effect_scope):
            _refuse("INVALID_CONTRACT", "effect_scope must be duplicate-free and nonempty")
        if type(phase["demands"]) is not list or not phase["demands"]:
            _refuse("INVALID_CONTRACT", "demands must be nonempty")
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for raw_demand in phase["demands"]:
            demand = _mapping(raw_demand, _DEMAND_KEYS, "demand")
            dimension = demand["dimension"]
            if type(dimension) is not str or dimension not in DIMENSION_UNITS:
                _refuse("INVALID_CONTRACT", "resource dimension is not admitted")
            pool = _nonempty(demand["capacity_pool_id"], "capacity_pool_id")
            peak = _uint(demand["qualified_incremental_peak"], "qualified_incremental_peak")
            window = _mapping(demand["window_binding"], _WINDOW_KEYS, "window_binding")
            if window["unit"] != DIMENSION_UNITS[dimension]:
                _refuse("INVALID_CONTRACT", "window unit does not match dimension")
            _positive(window["window_ms"], "window_binding.window_ms")
            _nonempty(window["baseline_id"], "window_binding.baseline_id")
            if window["boot_id"] != request["boot_id"]:
                _refuse("INVALID_CONTRACT", "window boot does not match request")
            key = (dimension, pool)
            existing = aggregated.get(key)
            if existing is None:
                aggregated[key] = copy.deepcopy(dict(demand))
            else:
                if existing["window_binding"] != demand["window_binding"]:
                    _refuse("DEMAND_CONFLICT", "duplicate demand has conflicting window")
                existing["qualified_incremental_peak"] = _sum64([existing["qualified_incremental_peak"], peak], "aggregated demand")
        normalized_demands = []
        for demand in aggregated.values():
            normalized_demands.append(demand)
        normalized_phases.append({"phase_key": phase_key, "profile": profile, "duration_ms": duration_ms, "effect_scope": list(effect_scope), "demands": normalized_demands})
    normalized["phases"] = normalized_phases
    return normalized


def physical_request_fingerprint(request: Mapping[str, Any]) -> str:
    normalized = validate_physical_request(request)
    normalized.pop("command_id", None)
    normalized.pop("acquisition_time_ms", None)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _admission_context(request, policy, observations, decision_time_ms):
    normalized = validate_physical_request(request)
    policy = _validate_policy(policy, allow_synthetic=True)
    if not policy["production_armed"]:
        _refuse("POLICY_UNARMED", "physical resource policy is unarmed")
    if normalized["host_id"] != observations.get("host_id"):
        _refuse("HOST_MISMATCH", "observation host changed")
    if normalized["boot_id"] != observations.get("boot_id"):
        _refuse("BOOT_MISMATCH", "observation boot changed")
    if normalized["policy_binding"]["revision"] != policy["policy_revision"] or observations.get("policy_revision") != policy["policy_revision"]:
        _refuse("POLICY_MOVED", "policy revision moved")
    sequence = _uint(observations.get("sequence"), "observation.sequence")
    required_sequence = _uint(observations.get("required_sequence"), "observation.required_sequence")
    if sequence != required_sequence:
        _refuse("SEQUENCE_MISMATCH", "observation sequence is not current")
    max_age = _uint(policy["freshness"].get("sample_max_age_ms"), "sample_max_age_ms")
    observed_at = _uint(observations.get("observed_at_ms"), "observed_at_ms")
    now = _uint(decision_time_ms, "decision_time_ms")
    if observed_at > now or now - observed_at > max_age:
        _refuse("STALE_OBSERVATION", "physical observation is stale")
    profiles = {profile.get("profile"): profile for profile in policy["profiles"] if type(profile) is dict}
    caller = normalized["caller_binding"]
    admitted_callers = {
        (entry.get("owner_id"), entry.get("carrier_id"), entry.get("session_id"))
        for entry in policy["allowed_callers"] if type(entry) is dict
    }
    if (normalized["owner_id"], normalized["carrier_id"], caller["session_id"]) not in admitted_callers:
        _refuse("CALLER_UNQUALIFIED", "caller is not admitted by current policy")
    for phase in normalized["phases"]:
        profile = profiles.get(phase["profile"])
        if profile is None:
            _refuse("PROFILE_UNQUALIFIED", "requested profile is not qualified")
        if profile.get("effect_scope") != phase["effect_scope"]:
            _refuse("EFFECT_SCOPE_MISMATCH", "effect scope differs from profile")
        if phase["duration_ms"] != profile["qualified_duration_ms"]:
            _refuse("PROFILE_DURATION_MISMATCH", "phase duration differs from qualified profile")
        for demand in phase["demands"]:
            if demand["dimension"] == "cpu_us_per_window" and demand["window_binding"]["window_ms"] != policy["windows"]["cpu_window_ms"]:
                _refuse("WINDOW_MISMATCH", "CPU window differs from qualified policy")
            if demand["dimension"] == "io_bytes_per_window" and demand["window_binding"]["window_ms"] != policy["windows"]["io_window_ms"]:
                _refuse("WINDOW_MISMATCH", "I/O window differs from qualified policy")
        qualified: dict[tuple[str, str], dict[str, Any]] = {}
        for demand in profile["qualified_demands"]:
            key = (demand["dimension"], demand["capacity_pool_id"])
            if key not in qualified:
                qualified[key] = copy.deepcopy(demand)
            else:
                if qualified[key]["window_binding"] != demand["window_binding"]:
                    _refuse("POLICY_INVALID", "duplicate qualified demand window conflicts")
                qualified[key]["qualified_incremental_peak"] = _sum64(
                    [qualified[key]["qualified_incremental_peak"], demand["qualified_incremental_peak"]],
                    "qualified demand",
                )
        actual = {(d["dimension"], d["capacity_pool_id"]): d for d in phase["demands"]}
        if actual != qualified:
            _refuse("PROFILE_DEMAND_MISMATCH", "request must exactly match qualified demands")
    return normalized, policy


def _charges_by_pool(charges: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, list[int]] = {}
    for charge in charges:
        pool = _nonempty(charge.get("capacity_pool_id"), "charge.capacity_pool_id")
        grouped.setdefault(pool, []).append(_uint(charge.get("remaining_charge"), "remaining_charge"))
    return {pool: _sum64(values, f"charges for {pool}") for pool, values in grouped.items()}


def _request_charges(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    charges = []
    for phase in request["phases"]:
        for raw in phase["demands"]:
            demand = copy.deepcopy(raw)
            demand["remaining_charge"] = demand["qualified_incremental_peak"]
            demand["attributed_materialized_or_active"] = 0
            demand["attribution"] = None
            charges.append(demand)
    return charges


def _check_capacity(policy, observations, charges):
    reserves = {}
    for raw in policy["physical_pools"]:
        if type(raw) is not dict or set(raw) != {"capacity_pool_id", "protected_reserve"}:
            _refuse("POLICY_INVALID", "pool contract is not closed")
        pool = _nonempty(raw["capacity_pool_id"], "pool.capacity_pool_id")
        if pool in reserves:
            _refuse("POLICY_INVALID", "pool IDs must be unique")
        reserves[pool] = _uint(raw["protected_reserve"], "protected_reserve")
    dimensions_by_pool: dict[str, set[str]] = {}
    for charge in charges:
        dimension = charge.get("dimension")
        if dimension not in DIMENSION_UNITS:
            _refuse("INVALID_CONTRACT", "charge dimension is not admitted")
        dimensions_by_pool.setdefault(charge.get("capacity_pool_id"), set()).add(dimension)
    if any(len(dimensions) != 1 for dimensions in dimensions_by_pool.values()):
        _refuse("MIXED_POOL_DIMENSIONS", "one physical pool cannot combine unlike units")
    totals = _charges_by_pool(charges)
    observed_pools = observations.get("pools")
    if type(observed_pools) is not dict:
        _refuse("OBSERVATION_INVALID", "pool observations are required")
    for pool, charge in totals.items():
        if pool not in reserves or type(observed_pools.get(pool)) is not dict:
            _refuse("POOL_UNQUALIFIED", "every physical pool must be qualified and observed")
        available = _uint(observed_pools[pool].get("available"), "pool.available")
        dimension = next(iter(dimensions_by_pool[pool]))
        budget_key = {
            "memory_bytes": "memory_budget_bytes",
            "cpu_us_per_window": "cpu_budget_us",
            "io_bytes_per_window": "io_budget_bytes",
            "heavy_phase_count": "max_heavy_phases",
        }.get(dimension)
        protected_key = {
            "memory_bytes": "memory_protected_bytes",
            "cpu_us_per_window": "cpu_protected_us",
            "io_bytes_per_window": "io_protected_bytes",
        }.get(dimension)
        if budget_key is not None:
            available = min(available, _uint(policy["limits"][budget_key], budget_key))
        protected = reserves[pool]
        if protected_key is not None:
            protected = max(protected, _uint(policy["limits"][protected_key], protected_key))
        if charge > available or available - charge < protected:
            _refuse("INSUFFICIENT_CAPACITY", f"protected reserve would be breached for {pool}")


def evaluate_reservation(request, *, policy, current_charges, observations, decision_time_ms):
    normalized, policy = _admission_context(request, policy, observations, decision_time_ms)
    new_charges = _request_charges(normalized)
    _check_capacity(policy, observations, [*current_charges, *new_charges])
    return {"admitted": True, "code": "RESERVED", "request_fingerprint": physical_request_fingerprint(request), "fresh_begin": False, "charges": new_charges}


def evaluate_begin(request, *, policy, current_charges, observations, decision_time_ms):
    """Evaluate additive capacity after the broker proves the owned reservation.

    ``current_charges`` is the global accounting view, so it cannot prove which
    rows belong to this request.  The ResourceBroker must first fence and verify
    the request's exact commitment rows.  A successful result here is therefore
    conditional accounting evidence, not an independently usable resource grant.
    """
    normalized, policy = _admission_context(request, policy, observations, decision_time_ms)
    _check_capacity(policy, observations, current_charges)
    return {"admitted": True, "code": "FRESH_BEGIN", "request_fingerprint": physical_request_fingerprint(request), "fresh_begin": True, "charges": _request_charges(normalized)}


def apply_physical_observation(demands, observation):
    """Conservatively account real usage without expanding immutable scope."""
    if type(observation) is not dict or set(observation) != {"usage", "attribution_id", "baseline_id"}:
        _refuse("OBSERVATION_INVALID", "observation contract is not closed")
    usage = observation.get("usage")
    if type(usage) is not dict:
        _refuse("OBSERVATION_INVALID", "usage must be a pool mapping")
    result = copy.deepcopy(list(demands))
    overrun = False
    for demand in result:
        pool = demand.get("capacity_pool_id")
        peak = _uint(demand.get("qualified_incremental_peak"), "qualified_incremental_peak")
        prior = _uint(demand.get("remaining_charge"), "remaining_charge")
        measured = _uint(usage.get(pool, 0), f"usage.{pool}")
        demand["remaining_charge"] = max(prior, peak, measured)
        demand["attributed_materialized_or_active"] = measured
        overrun = overrun or measured > peak
        if measured:
            demand["attribution"] = {
                "attribution_id": _nonempty(observation["attribution_id"], "attribution_id"),
                "baseline_id": _nonempty(observation["baseline_id"], "baseline_id"),
            }
    return {"charges": result, "overrun": overrun}


def settle_physical_accounting(demands, settlement):
    """Release only positively terminal, baseline-attributed disk materialization."""
    allowed = {"terminal_effect_state", "pools", "positive_no_effect", "process_terminal", "descendants_terminal"}
    if type(settlement) is not dict or not {"terminal_effect_state", "pools"}.issubset(settlement) or set(settlement) - allowed:
        _refuse("SETTLEMENT_INVALID", "settlement contract is not closed")
    state = settlement["terminal_effect_state"]
    if state not in {"NO_EFFECT", "TERMINAL", "UNKNOWN"} or type(settlement["pools"]) is not dict:
        _refuse("SETTLEMENT_INVALID", "terminal evidence is invalid")
    result = copy.deepcopy(list(demands))
    for demand in result:
        demand["remaining_charge"] = _uint(demand.get("remaining_charge"), "remaining_charge")
        if state == "NO_EFFECT" and settlement.get("positive_no_effect") is True:
            demand["remaining_charge"] = 0
        elif state == "TERMINAL" and settlement.get("process_terminal") is True and settlement.get("descendants_terminal") is True:
            if demand.get("dimension") != "disk_bytes":
                demand["remaining_charge"] = 0
            else:
                evidence = settlement["pools"].get(demand.get("capacity_pool_id"), {})
                attribution = demand.get("attribution")
                if type(attribution) is dict and evidence.get("baseline_id") == attribution.get("baseline_id") and attribution.get("attribution_id") in evidence.get("included_materializations", []):
                    demand["remaining_charge"] = 0
    return {"charges": result}


def bounded_wait_ms(policy, *, remaining_start_ms):
    remaining = _uint(remaining_start_ms, "remaining_start_ms")
    waits = policy.get("waits") if type(policy) is dict else None
    if type(waits) is not dict:
        _refuse("WAIT_BUDGET_UNQUALIFIED", "wait bounds are missing")
    values = [waits.get("service_request_max_ms"), waits.get("database_lock_max_ms")]
    if any(type(value) is not int or type(value) is bool or value <= 0 or value > INT64_MAX for value in values):
        _refuse("WAIT_BUDGET_UNQUALIFIED", "wait bounds must be qualified positive integers")
    return min(remaining, *values)
