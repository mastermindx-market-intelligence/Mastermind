"""Route table and admission-time selection for the unified fabric router.

The router composes incumbent capacity owners; it creates no new credential
store. API-key material is read live from the Hermes ``credential_pool`` in
``~/.hermes/auth.json`` at request time (the same pattern the Anthropic OAuth
gateway uses), and loopback fabric gateways are reached with their own local
tokens. Selection happens strictly BEFORE the upstream send; a request is
never replayed to a second route after a possible effect.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

DEFAULT_AUTH_STORE = Path.home() / ".hermes" / "auth.json"

# Wire the request speaks on the left; what the route accepts on the right.
WIRE_ANTHROPIC = "anthropic"
WIRE_OPENAI = "openai"
WIRE_RESPONSES = "responses"


@dataclass(frozen=True)
class Route:
    route_id: str
    kind: str                      # gateway | credential_pool | config_file
    base_url: str
    wire: str                      # upstream wire the route natively speaks
    models: tuple[str, ...]        # public model slugs this route may serve
    weight: float = 1.0
    priority: int = 100            # lower tier first; within a tier, weights
    pool: str = ""                 # credential_pool key for kind="credential_pool"
    api_key_label: str = ""        # label inside the pool entry
    env_key: str = ""              # NAME in the incumbent env file (~/.hermes/.env)
    gateway_token_env: str = ""    # env name holding the loopback token
    config_path: str = ""          # incumbent key config for kind="config_file"
    key_pointer: str = ""          # dotted pointer to the key inside that config
    base_url_pointer: str = ""     # optional dotted pointer to the base URL
    token_url: str = ""            # OAuth refresh endpoint for kind="oauth_pool"
    client_id: str = ""            # OAuth client id for kind="oauth_pool"
    originator: str = ""           # identity header mirrored from the incumbent client
    upstream_model: tuple[tuple[str, str], ...] = ()  # public slug -> wire id
    auth_header: str = ""          # upstream header for the raw credential (default Bearer authorization)
    session_header: str = ""       # upstream header carrying a stable per-affinity session id
    notes: str = ""
    max_in_flight: int = 0          # local bulkhead; zero leaves only the global cap
    concurrency_group: str = ""    # explicit shared local scope, never inferred quota
    group_max_in_flight: int = 0
    model_priority: dict[str, int] = field(default_factory=dict)
    model_weight: dict[str, float] = field(default_factory=dict)
    model_params: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (not self.route_id or not self.models
                or not all(isinstance(m, str) and m.strip() for m in self.models)):
            raise ValueError("route identity and models are required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.route_id):
            raise ValueError("route identity must be a bounded safe label")
        if any(len(m) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in m) for m in self.models):
            raise ValueError("model identifiers must be bounded visible ASCII")
        if type(self.weight) not in (int, float) or not math.isfinite(self.weight) or self.weight < 0:
            raise ValueError("route weight must be finite and non-negative")
        if type(self.priority) is not int:
            raise ValueError("route priority must be an integer")
        models = {m.lower() for m in self.models}
        for field_name in ("model_priority", "model_weight", "model_params"):
            supplied = getattr(self, field_name)
            if not isinstance(supplied, dict):
                raise ValueError("per-model routing overrides must be objects")
            normalized = {}
            for key, value in supplied.items():
                if (not isinstance(key, str) or key.strip().lower() not in models
                        or key.strip().lower() in normalized):
                    raise ValueError("per-model overrides must name unique served models")
                key = key.strip().lower()
                if field_name == "model_priority":
                    if type(value) is not int:
                        raise ValueError("per-model priority must be an integer")
                elif field_name == "model_weight":
                    if (type(value) not in (int, float) or not math.isfinite(value)
                            or value < 0):
                        raise ValueError("per-model weight must be finite and non-negative")
                    value = float(value)
                else:
                    # Provider tuning cannot replace caller messages, tools, the
                    # routed model, stream mode or any ownership/authentication field.
                    if (not isinstance(value, dict) or set(value) - {"reasoning_effort"}
                            or (value and (not isinstance(value.get("reasoning_effort"), str)
                                or value["reasoning_effort"] not in {
                                    "none", "minimal", "low", "medium", "high", "xhigh", "max"}))):
                        raise ValueError("unsupported per-model request parameters")
                    if value and self.wire != WIRE_OPENAI:
                        raise ValueError("reasoning effort override requires OpenAI wire")
                    value = dict(value)
                normalized[key] = value
            object.__setattr__(self, field_name, normalized)
        if self.wire not in {WIRE_ANTHROPIC, WIRE_OPENAI, WIRE_RESPONSES}:
            raise ValueError("unsupported route wire")
        if self.kind not in {"gateway", "credential_pool", "config_file", "oauth_pool"}:
            raise ValueError("unsupported route kind")
        if (self.kind == "oauth_pool") != (self.wire == WIRE_RESPONSES):
            raise ValueError("Responses wire requires the OAuth pool owner")
        for limit in (self.max_in_flight, self.group_max_in_flight):
            if type(limit) is not int or limit < 0:
                raise ValueError("concurrency limits must be non-negative integers")
        if bool(self.concurrency_group) != bool(self.group_max_in_flight):
            raise ValueError("a concurrency group requires its explicit positive ceiling")
        if self.concurrency_group and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.concurrency_group):
            raise ValueError("concurrency group must be a bounded safe label")

    def serves(self, model: str) -> bool:
        wanted = model.strip().lower()
        return wanted in {slug.lower() for slug in self.models}

    def effective_priority(self, model: str) -> int:
        return self.model_priority.get(model.strip().lower(), self.priority)

    def effective_weight(self, model: str = "") -> float:
        # A route-wide zero is an operator drain across every model. A model
        # override may additionally drain one model, but cannot undo that hold.
        if self.weight == 0:
            return 0.0
        return self.model_weight.get(model.strip().lower(), self.weight)

    def effective_params(self, model: str) -> dict:
        return dict(self.model_params.get(model.strip().lower(), {}))

    def wire_model(self, model: str) -> str:
        wanted = model.strip().lower()
        for slug, wire_id in self.upstream_model:
            if slug.lower() == wanted:
                return wire_id
        return model


@dataclass
class RoutePermit:
    route_id: str
    group: str
    generation: int
    probe: bool
    released: bool = False


@dataclass
class RouteState:
    """Single-event-loop circuit/bulkhead state, not provider quota authority.

    Selection and acquire contain no await. The installed service uses one
    worker; this state makes no cross-process or direct-provider guarantee.
    """
    cooldown_until: dict[str, float] = field(default_factory=dict)
    last_failure: dict[str, tuple[float, str]] = field(default_factory=dict)
    consecutive_failures: dict[str, int] = field(default_factory=dict)
    generation: dict[str, int] = field(default_factory=dict)
    in_flight: dict[str, int] = field(default_factory=dict)
    group_in_flight: dict[str, int] = field(default_factory=dict)
    probes: set[str] = field(default_factory=set)

    def available(self, route_id: str, now: float) -> bool:
        return (self.cooldown_until.get(route_id, 0.0) <= now
                and route_id not in self.probes)

    def has_room(self, route: Route) -> bool:
        return ((not route.max_in_flight
                 or self.in_flight.get(route.route_id, 0) < route.max_in_flight)
                and (not route.concurrency_group or self.group_in_flight.get(
                    route.concurrency_group, 0) < route.group_max_in_flight))

    def exclusion_reason(self, route: Route, now: float, model: str = "") -> str:
        """First local hard exclusion, shared by selection and acquisition."""
        if route.effective_weight(model) <= 0:
            return "drained"
        if self.cooldown_until.get(route.route_id, 0.0) > now:
            return "circuit_open"
        if route.route_id in self.probes:
            return "probe_occupied"
        if route.max_in_flight and self.in_flight.get(route.route_id, 0) >= route.max_in_flight:
            return "route_limit"
        if route.concurrency_group and self.group_in_flight.get(
                route.concurrency_group, 0) >= route.group_max_in_flight:
            return "group_limit"
        return ""

    def acquire(self, route: Route, *, now: float, model: str = "") -> RoutePermit | None:
        if self.exclusion_reason(route, now, model):
            return None
        probe = self.consecutive_failures.get(route.route_id, 0) > 0
        if probe:
            self.probes.add(route.route_id)
        self.in_flight[route.route_id] = self.in_flight.get(route.route_id, 0) + 1
        if route.concurrency_group:
            self.group_in_flight[route.concurrency_group] = self.group_in_flight.get(
                route.concurrency_group, 0) + 1
        return RoutePermit(route.route_id, route.concurrency_group,
                           self.generation.get(route.route_id, 0), probe)

    def release(self, permit: RoutePermit) -> None:
        if permit.released:
            return
        permit.released = True
        self.in_flight[permit.route_id] -= 1
        if permit.group:
            self.group_in_flight[permit.group] -= 1
        if permit.probe:
            self.probes.discard(permit.route_id)

    def record_failure(self, route_id: str, reason: str, *, now: float,
                       cooldown_s: float = 30.0,
                       retry_after_s: float | None = None,
                       generation: int | None = None) -> None:
        if generation is not None and generation != self.generation.get(route_id, 0):
            return
        count = self.consecutive_failures.get(route_id, 0) + 1
        self.consecutive_failures[route_id] = count
        self.last_failure[route_id] = (now, reason)
        self.generation[route_id] = self.generation.get(route_id, 0) + 1
        backoff = min(cooldown_s * (2 ** min(count - 1, 10)), 300.0)
        # Positive jitter never shortens the provider's minimum Retry-After.
        delay = max(backoff, retry_after_s or 0.0) + random.uniform(0, min(backoff * .1, 5))
        self.cooldown_until[route_id] = max(self.cooldown_until.get(route_id, 0), now + delay)

    def record_success(self, route_id: str, *, generation: int | None = None) -> None:
        # An older request finishing after a fresh failure cannot heal it.
        if generation is not None and generation != self.generation.get(route_id, 0):
            return
        if self.consecutive_failures.get(route_id, 0):
            self.generation[route_id] = self.generation.get(route_id, 0) + 1
        self.consecutive_failures[route_id] = 0
        self.cooldown_until.pop(route_id, None)

    def circuit(self, route_id: str, now: float) -> str:
        if route_id in self.probes:
            return "half_open"
        if self.cooldown_until.get(route_id, 0) > now:
            return "open"
        return "probe_ready" if self.consecutive_failures.get(route_id, 0) else "closed"


def retry_after_seconds(value: str, *, wall_now: float) -> float | None:
    """Parse delta seconds or HTTP-date once; callers use monotonic deadlines."""
    if not value or len(value) > 128:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = date.timestamp() - wall_now
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def credential_pool_accounts(auth_store: Path = DEFAULT_AUTH_STORE) -> dict[str, list[dict]]:
    """Read the Hermes credential pool; values stay inside this process."""
    document = json.loads(auth_store.read_text(encoding="utf-8"))
    pool = document.get("credential_pool")
    if not isinstance(pool, dict):
        return {}
    result = {}
    for name, accounts in pool.items():
        if isinstance(accounts, list):
            result[name] = [a for a in accounts if isinstance(a, dict)]
    return result


def _resolve_pointer(document, pointer: str):
    value = document
    for part in pointer.split("."):
        if isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def config_file_route_key(config_path: str, key_pointer: str,
                          base_url_pointer: str = "") -> tuple[str, str]:
    """Key (and optional base URL) from an incumbent pool config file.

    The GLM coding plan (``~/.glm/config.json``), the Bailian token plan
    (``~/.bailian/config.json``) and MiniMax (``~/.minimax/config.json``) each
    own their key material in their own 0600 config; this reads exactly the
    pointer the operator configured and nothing else.
    """
    path = Path(config_path).expanduser()
    document = json.loads(path.read_text(encoding="utf-8"))
    key = _resolve_pointer(document, key_pointer)
    if not isinstance(key, str) or not key:
        raise ValueError(f"{key_pointer!r} in {path} is not a usable key")
    base_url = ""
    if base_url_pointer:
        candidate = _resolve_pointer(document, base_url_pointer)
        if isinstance(candidate, str) and candidate:
            base_url = candidate
    return key, base_url


def env_file_value(auth_store: Path, name: str) -> str:
    """One KEY=VALUE from the incumbent env file beside the auth store."""
    env_file = auth_store.parent / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip('"').strip("'")
    raise ValueError(f"{name} missing in {env_file}")


def credential_pool_key(auth_store: Path, pool: str, label: str) -> str:
    """One API key from the incumbent pool, honouring its own env sources."""
    for account in credential_pool_accounts(auth_store).get(pool, []):
        if account.get("label") != label:
            continue
        for name in ("api_key", "key", "token", "access_token"):
            value = account.get(name)
            if isinstance(value, str) and value:
                return value
        source = account.get("source")
        if isinstance(source, str) and source.startswith("env:"):
            return env_file_value(auth_store, source[len("env:"):])
    raise ValueError(f"credential_pool.{pool} label {label!r} has no usable key")


def affinity_route(route_ids: list[str], affinity_key: str, *, ttl_buckets: int = 64,
                   weights: dict[str, float] | None = None) -> str:
    """Weighted rendezvous: removing one route only remaps its own callers."""
    def rank(route_id: str) -> tuple[float, str]:
        digest = hashlib.sha256(json.dumps([affinity_key, route_id]).encode()).digest()
        # 52 bits keep both endpoints strictly excluded after float rounding.
        uniform = ((int.from_bytes(digest[:8], "big") >> 12) + 1) / (2**52 + 1)
        weight = (weights or {}).get(route_id, 1.0)
        return (-math.log(uniform) / weight, route_id)
    return min(route_ids, key=rank)


@dataclass(frozen=True)
class RouteDecision:
    route: Route | None
    reason: str
    evidence: dict


def decide_route(routes: list[Route], model: str, *, state: RouteState, now: float,
                 affinity_key: str | None = None) -> RouteDecision:
    """One selection with bounded evidence, never an admission permit.

    The caller has already applied transport and owner preflight exclusions.
    Evidence contains only configured route labels, counts and fixed reasons;
    raw model, alias, affinity and credential inputs are never retained.
    """
    candidates = [r for r in routes if r.serves(model)]
    excluded = {key: 0 for key in ("drained", "circuit_open", "probe_occupied",
                                   "route_limit", "group_limit")}
    healthy = []
    for route in candidates:
        # First failing gate wins, so these counts form a disjoint partition.
        reason = state.exclusion_reason(route, now, model)
        if reason:
            excluded[reason] += 1
        else:
            healthy.append(route)
    evidence = {
        "scope": "local_after_owner_preflight", "matched_routes": len(candidates),
        "excluded": excluded, "eligible_routes": len(healthy),
        "selected_priority": None, "priority_routes": 0,
        "least_pressure_routes": 0, "tie_break": "none", "selected_route": None,
    }

    def result(route: Route | None, reason: str = "") -> RouteDecision:
        evidence["selected_route"] = route.route_id if route else None
        return RouteDecision(route, reason, evidence)

    if not candidates:
        return result(None, "FABRIC_MODEL_UNKNOWN")
    if excluded["drained"] == len(candidates):
        return result(None, "FABRIC_ROUTES_DRAINED")
    if sum(excluded[key] for key in ("drained", "circuit_open", "probe_occupied")) == len(candidates):
        return result(None, "FABRIC_ALL_ROUTES_COOLING")
    if not healthy:
        return result(None, "FABRIC_ROUTES_BUSY")
    lowest_tier = min(r.effective_priority(model) for r in healthy)
    tier = sorted((r for r in healthy if r.effective_priority(model) == lowest_tier),
                  key=lambda r: r.route_id)
    evidence.update(selected_priority=lowest_tier, priority_routes=len(tier))
    # Affinity is soft: an idle equally eligible route wins over a busy one.
    load = {r.route_id: state.in_flight.get(r.route_id, 0) / r.effective_weight(model)
            for r in tier}
    best = min(load.values())
    tier = [r for r in tier if math.isclose(load[r.route_id], best, abs_tol=1e-12)]
    evidence["least_pressure_routes"] = len(tier)
    if len(tier) == 1:
        evidence["tie_break"] = ("single_route_in_tier" if evidence["priority_routes"] == 1
                                 else "lowest_local_pressure")
        return result(_weighted_pick(tier, model))
    if (affinity_key and len(tier) > 1
            and len({(r.base_url.rstrip('/'), r.wire) for r in tier}) == 1):
        evidence["tie_break"] = "weighted_rendezvous"
        chosen = affinity_route([r.route_id for r in tier], affinity_key,
                                weights={r.route_id: r.effective_weight(model) for r in tier})
        for route in tier:
            if route.route_id == chosen:
                return result(route)
    evidence["tie_break"] = "weighted_random"
    return result(_weighted_pick(tier, model))


def select_route(routes: list[Route], model: str, *, state: RouteState, now: float,
                 affinity_key: str | None = None) -> tuple[Route | None, str]:
    """Compatibility projection of the single explained selection path."""
    decision = decide_route(routes, model, state=state, now=now, affinity_key=affinity_key)
    return decision.route, decision.reason


def ordered_routes(routes: list[Route], model: str, *, state: RouteState, now: float,
                   affinity_key: str | None = None) -> list[Route]:
    """Compatibility snapshot of the explained selector, without reserving capacity.

    Admission must select again after every proven pre-send failure: availability
    can change while an upstream connection is being attempted.
    """
    remaining = list(routes)
    ordered = []
    while remaining:
        decision = decide_route(remaining, model, state=state, now=now,
                                affinity_key=affinity_key)
        if decision.route is None:
            break
        ordered.append(decision.route)
        remaining = [r for r in remaining if r.route_id != decision.route.route_id]
    return ordered


def _weighted_pick(tier: list[Route], model: str = "") -> Route:
    # The explained selector has already excluded every zero effective weight.
    total = sum(r.effective_weight(model) for r in tier)
    point = random.random() * total
    accumulated = 0.0
    for route in tier:
        accumulated += route.effective_weight(model)
        if point < accumulated:
            return route
    return tier[-1]
