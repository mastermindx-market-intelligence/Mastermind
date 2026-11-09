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
import random
import time
from dataclasses import dataclass, field
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
class RouteState:
    """Local, in-process circuit knowledge; never a second quota ledger."""
    cooldown_until: dict[str, float] = field(default_factory=dict)
    last_failure: dict[str, tuple[float, str]] = field(default_factory=dict)
    consecutive_failures: dict[str, int] = field(default_factory=dict)

    def available(self, route_id: str, now: float) -> bool:
        return self.cooldown_until.get(route_id, 0.0) <= now

    def record_failure(self, route_id: str, reason: str, *, now: float,
                       cooldown_s: float = 30.0) -> None:
        count = self.consecutive_failures.get(route_id, 0) + 1
        self.consecutive_failures[route_id] = count
        self.last_failure[route_id] = (now, reason)
        self.cooldown_until[route_id] = now + min(cooldown_s * count, 300.0)

    def record_success(self, route_id: str) -> None:
        self.consecutive_failures[route_id] = 0
        self.cooldown_until.pop(route_id, None)


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


def affinity_route(route_ids: list[str], affinity_key: str, *, ttl_buckets: int = 64) -> str:
    """Stable route for a caller so prompt-cache locality survives requests."""
    digest = hashlib.sha256(affinity_key.encode("utf-8")).digest()
    return route_ids[digest[0] % len(route_ids)]


def select_route(routes: list[Route], model: str, *, state: RouteState, now: float,
                 affinity_key: str | None = None) -> tuple[Route | None, str]:
    """Admission-time selection: healthy routes for the model, tier then weight.

    Returns (route, reason). reason is set when no route can serve the model.
    """
    candidates = [r for r in routes if r.serves(model)]
    if not candidates:
        return None, "FABRIC_MODEL_UNKNOWN"
    healthy = [r for r in candidates if state.available(r.route_id, now)]
    if not healthy:
        return None, "FABRIC_ALL_ROUTES_COOLING"
    lowest_tier = min(r.priority for r in healthy)
    tier = sorted((r for r in healthy if r.priority == lowest_tier),
                  key=lambda r: r.route_id)
    if affinity_key and len(tier) > 1:
        chosen = affinity_route([r.route_id for r in tier], affinity_key)
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
