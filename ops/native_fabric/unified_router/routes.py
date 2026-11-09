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

    def __post_init__(self) -> None:
        if (not self.route_id or not self.models
                or not all(isinstance(m, str) and m.strip() for m in self.models)):
            raise ValueError("route identity and models are required")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", self.route_id):
            raise ValueError("route identity must be a bounded safe label")
        if any(len(m) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in m) for m in self.models):
            raise ValueError("model identifiers must be bounded visible ASCII")
        if not math.isfinite(self.weight) or self.weight < 0:
            raise ValueError("route weight must be finite and non-negative")
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

    def acquire(self, route: Route, *, now: float) -> RoutePermit | None:
        if route.weight <= 0 or not self.available(route.route_id, now) or not self.has_room(route):
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


def select_route(routes: list[Route], model: str, *, state: RouteState, now: float,
                 affinity_key: str | None = None) -> tuple[Route | None, str]:
    """Admission-time selection: healthy routes for the model, tier then weight.

    Returns (route, reason). reason is set when no route can serve the model.
    """
    candidates = [r for r in routes if r.serves(model)]
    if not candidates:
        return None, "FABRIC_MODEL_UNKNOWN"
    enabled = [r for r in candidates if r.weight > 0]
    if not enabled:
        return None, "FABRIC_ROUTES_DRAINED"
    healthy = [r for r in enabled if state.available(r.route_id, now)]
    if not healthy:
        return None, "FABRIC_ALL_ROUTES_COOLING"
    healthy = [r for r in healthy if state.has_room(r)]
    if not healthy:
        return None, "FABRIC_ROUTES_BUSY"
    lowest_tier = min(r.priority for r in healthy)
    tier = sorted((r for r in healthy if r.priority == lowest_tier),
                  key=lambda r: r.route_id)
    # Affinity is soft: an idle equally eligible route wins over a busy one.
    load = {r.route_id: state.in_flight.get(r.route_id, 0) / r.weight for r in tier}
    best = min(load.values())
    tier = [r for r in tier if math.isclose(load[r.route_id], best, abs_tol=1e-12)]
    if affinity_key and len(tier) > 1:
        chosen = affinity_route([r.route_id for r in tier], affinity_key,
                                weights={r.route_id: r.weight for r in tier})
        for route in tier:
            if route.route_id == chosen:
                return route, ""
    return _weighted_pick(tier), ""


def _weighted_pick(tier: list[Route]) -> Route:
    total = sum(max(r.weight, 0.0) for r in tier)
    if total <= 0:
        return tier[0]
    point = random.random() * total
    accumulated = 0.0
    for route in tier:
        accumulated += max(route.weight, 0.0)
        if point <= accumulated:
            return route
    return tier[-1]
