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
    # Chairman 2026-11-09 wide-distribution ruling: one model may join several
    # providers in a single tier without disturbing the route's other models.
    # Keys are public slugs (lowercased); missing -> route-wide defaults above.
    model_priority: dict[str, int] = field(default_factory=dict)
    model_weight: dict[str, float] = field(default_factory=dict)
    # Per-model request parameter overrides applied after wire translation
    # (slug -> e.g. {"reasoning_effort": "medium"} for upstreams whose default
    # is unusable). Keys are public slugs (lowercased).
    model_params: dict[str, dict] = field(default_factory=dict)
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
    # Admission pacing budget per subscription/window, tokens per 60s:
    # {"input": N, "output": M}. Requests queue so aggregate observed usage
    # stays under budget -- converts would-be 429s into bounded waits.
    rate_limit: tuple = ()
    notes: str = ""
    max_in_flight: int = 0
    concurrency_group: str = ""
    group_max_in_flight: int = 0

    def __post_init__(self):
        for value in (self.max_in_flight, self.group_max_in_flight):
            if type(value) is not int or not 0 <= value <= 1000000:
                raise ValueError("invalid route concurrency limit")
        if (not isinstance(self.concurrency_group, str) or len(self.concurrency_group) > 128
                or bool(self.concurrency_group) != bool(self.group_max_in_flight)
                or any(ord(c) < 33 or ord(c) > 126 for c in self.concurrency_group)):
            raise ValueError("invalid shared concurrency group")
        object.__setattr__(self, "model_priority", {
            k.strip().lower(): int(v) for k, v in self.model_priority.items()})
        object.__setattr__(self, "model_weight", {
            k.strip().lower(): float(v) for k, v in self.model_weight.items()})
        object.__setattr__(self, "model_params", {
            k.strip().lower(): dict(v) for k, v in self.model_params.items()})
        object.__setattr__(self, "rate_limit", tuple(
            (str(k), float(v)) for k, v in dict(self.rate_limit).items()))

    def rate_budget(self, kind: str) -> float:
        for key, value in self.rate_limit:
            if key == kind:
                return value
        return 0.0

    @staticmethod
    def canon(slug: str) -> str:
        """Canonical public-slug form: vendors publish both '.' and '-' spellings
        of the same model id (claude-fable-5.1 / claude-fable-5-1). Route
        matching is spelling-tolerant so a session pinned to either spelling
        resolves to the declared slug (and its upstream_model mapping) instead
        of failing FABRIC_MODEL_UNKNOWN."""
        return slug.strip().lower().replace(".", "-")

    def canonical_slug(self, model: str) -> str | None:
        """The DECLARED public slug for ``model`` (either spelling), else None."""
        wanted = self.canon(model)
        for slug in self.models:
            if self.canon(slug) == wanted:
                return slug
        return None

    def serves(self, model: str) -> bool:
        return self.canonical_slug(model) is not None

    def effective_priority(self, model: str) -> int:
        wanted = self.canon(model)
        return self.model_priority.get(wanted,
            self.model_priority.get(self.canonical_slug(model) or "", self.priority))

    def effective_weight(self, model: str) -> float:
        wanted = self.canon(model)
        return self.model_weight.get(wanted,
            self.model_weight.get(self.canonical_slug(model) or "", self.weight))

    def effective_params(self, model: str) -> dict:
        """Request parameter overrides for ``model``; empty when none."""
        wanted = self.canon(model)
        return dict(self.model_params.get(wanted,
            self.model_params.get(self.canonical_slug(model) or "", {})))

    def wire_model(self, model: str) -> str:
        # Resolve either spelling to the declared slug first, then apply the
        # public->wire mapping, so variant-spelled requests send the correct
        # upstream id (or the declared slug) -- never the raw variant.
        declared = self.canonical_slug(model)
        if declared is not None:
            for slug, wire_id in self.upstream_model:
                if slug.lower() == declared.strip().lower():
                    return wire_id
            return declared
        for slug, wire_id in self.upstream_model:
            if slug.lower() == model.strip().lower():
                return wire_id
        return model


@dataclass
class RouteState:
    """Local, in-process circuit knowledge; never a second quota ledger."""
    cooldown_until: dict[str, float] = field(default_factory=dict)
    last_failure: dict[str, tuple[float, str]] = field(default_factory=dict)
    consecutive_failures: dict[str, int] = field(default_factory=dict)
    generations: dict[str, int] = field(default_factory=dict)
    owner_holds: dict[str, dict] = field(default_factory=dict)
    model_holds: dict[str, dict[str, dict]] = field(default_factory=dict)

    def held(self, route_id: str, model: str):
        return self.owner_holds.get(route_id) or self.model_holds.get(route_id, {}).get(model)

    def available(self, route_id: str, now: float) -> bool:
        return route_id not in self.owner_holds and self.cooldown_until.get(route_id, 0.0) <= now

    def hold(self, route_id: str, category: str, code: str, *, now: float, model: str | None = None) -> None:
        if model is not None:
            self.model_holds.setdefault(route_id, {})[model] = {"category": category, "code": code}
            self.generations[route_id] = self.generations.get(route_id, 0) + 1
            return
        previous = self.owner_holds.get(route_id)
        if previous and previous.get("category") == "permission":
            return
        self.owner_holds[route_id] = {"category": category, "code": code}
        self.generations[route_id] = self.generations.get(route_id, 0) + 1
        self.consecutive_failures[route_id] = max(1, self.consecutive_failures.get(route_id, 0))
        self.last_failure[route_id] = (now, code)

    def record_failure(self, route_id: str, reason: str, *, now: float,
                       cooldown_s: float = 30.0, escalate: bool = True,
                       generation: int | None = None, quota: bool = False,
                       permission: bool = False) -> bool:
        import math
        current = self.generations.get(route_id, 0)
        if generation is not None and generation != current and not (quota or permission):
            return False
        try:
            cooldown_s = float(cooldown_s)
        except (TypeError, ValueError, OverflowError):
            cooldown_s = 30.0
        if not math.isfinite(cooldown_s) or not 0 <= cooldown_s <= 1e9:
            cooldown_s = 30.0
        count = self.consecutive_failures.get(route_id, 0) + 1
        self.consecutive_failures[route_id] = count
        self.generations[route_id] = current + 1
        self.last_failure[route_id] = (now, reason)
        # Rate-limit (quota window) refusals must NOT escalate: the window is a
        # fixed per-minute meter, so benching for count*window would strand a
        # healthy route for minutes after a short burst. Hard failures still
        # back off up to the cap. Authoritative quota/permission holds remain
        # effective even when their response arrives from an older generation.
        self.cooldown_until[route_id] = max(self.cooldown_until.get(route_id, 0), now + (
            min(cooldown_s * count, 300.0) if escalate
            else cooldown_s))
        return True

    def record_success(self, route_id: str, *, generation: int | None = None,
                       now: float | None = None) -> bool:
        if route_id in self.owner_holds:
            return False
        current = self.generations.get(route_id, 0)
        if generation is not None and generation != current:
            return False
        if self.cooldown_until.get(route_id, 0) > (time.monotonic() if now is None else now):
            return False
        if self.consecutive_failures.get(route_id, 0):
            self.generations[route_id] = current + 1
        self.consecutive_failures[route_id] = 0
        self.cooldown_until.pop(route_id, None)
        return True


RATE_WINDOW_S = 60.0


class RateWindow:
    """Local request-keyed pacing, never authoritative provider headroom.

    Active reservations live until their request/stream closes, not for an arbitrary
    60-second TTL. Input and output are settled by exact reservation identity, so
    out-of-order completions cannot release a sibling's reservation.
    """
    def __init__(self):
        import collections
        self._collections = collections
        self._samples = {}
        self._pending = {}

    @staticmethod
    def _amount(value):
        import math
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("invalid pacing estimate")
        if not math.isfinite(value) or not 0 <= value <= 1e9:
            raise ValueError("invalid pacing estimate")
        return float(value)

    def _q(self, resource, now):
        q = self._samples.setdefault(resource, self._collections.deque())
        while q and now - q[0][0] >= RATE_WINDOW_S:
            q.popleft()
        return q

    def reserve(self, route_id, inp, out, *, request_id=None, resource_id=None, now=None):
        import uuid
        key = request_id or uuid.uuid4().hex
        if key in self._pending:
            raise ValueError("duplicate request reservation")
        self._pending[key] = (time.monotonic() if now is None else now,
            resource_id or route_id, route_id, self._amount(inp), self._amount(out))
        return key

    def release(self, request_id):
        return self._pending.pop(request_id, None) is not None

    def settle(self, route_id, now, inp, out, *, request_id=None):
        inp, out = self._amount(inp), self._amount(out)
        if request_id is None:
            matching = [k for k, p in self._pending.items() if p[2] == route_id]
            if len(matching) > 1:
                raise ValueError("settlement requires the original request identity")
            request_id = matching[0] if matching else None
        pending = self._pending.pop(request_id, None) if request_id else None
        resource = pending[1] if pending else route_id
        if inp > 0 or out > 0:
            self._q(resource, now).append((now, inp, out))

    def totals(self, resource, now):
        q = self._q(resource, now)
        inp = sum(s[1] for s in q)
        out = sum(s[2] for s in q)
        for p in self._pending.values():
            if p[1] == resource:
                inp += p[3]; out += p[4]
        return inp, out

    def wait_for(self, route, now, est_in, est_out, *, resource_id=None,
                 limits=None, allow_oversize=False):
        resource = resource_id or route.route_id
        budgets = limits or (route.rate_budget("input"), route.rate_budget("output"))
        q = self._q(resource, now)
        totals = self.totals(resource, now)
        pending = any(p[1] == resource for p in self._pending.values())
        waits = [0.0]
        for idx, (budget, used, extra) in enumerate(zip(budgets, totals, (est_in, est_out)), 1):
            budget = self._amount(budget or 0)
            extra = self._amount(extra)
            if budget <= 0 or used + extra <= budget:
                continue
            if extra > budget:
                # Morph explicitly permits one oversized request before throttling.
                # Never turn that rule into unlimited parallel oversized admission.
                if allow_oversize and used == 0 and not pending:
                    continue
                if not allow_oversize:
                    return float("inf")
                waits.append(max((s[0] + RATE_WINDOW_S - now for s in q), default=1.0))
                continue
            need = used + extra - budget
            freed = 0.0
            for sample in q:
                freed += sample[idx]
                if freed >= need:
                    waits.append(max(0.001, sample[0] + RATE_WINDOW_S - now))
                    break
            else:
                waits.append(1.0 if pending else RATE_WINDOW_S)
        return max(waits)

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

    Tier and weight are per-model (``model_priority``/``model_weight`` override
    the route-wide values), so one slug can spread across several providers in
    a single tier while the route's other models keep their own tiers.

    Caller affinity pins one route only while the tier is a single upstream
    provider (same base URL), where prompt-cache locality is real. Across
    different providers the configured weights distribute the traffic instead:
    a lone caller must not monopolise one plan while the rest sit idle.

    Returns (route, reason). reason is set when no route can serve the model.
    """
    candidates = [r for r in routes if r.serves(model)]
    if not candidates:
        return None, "FABRIC_MODEL_UNKNOWN"
    healthy = [r for r in candidates if state.available(r.route_id, now)]
    if not healthy:
        return None, "FABRIC_ALL_ROUTES_COOLING"
    wanted = model.strip().lower()
    lowest_tier = min(r.effective_priority(wanted) for r in healthy)
    tier = sorted((r for r in healthy if r.effective_priority(wanted) == lowest_tier),
                  key=lambda r: r.route_id)
    if (affinity_key and len(tier) > 1
            and len({r.base_url for r in tier}) == 1):
        chosen = affinity_route([r.route_id for r in tier], affinity_key)
        for route in tier:
            if route.route_id == chosen:
                return route, ""
    return _weighted_pick(tier, wanted), ""


def _weighted_pick(tier: list[Route], model: str) -> Route:
    total = sum(max(r.effective_weight(model), 0.0) for r in tier)
    if total <= 0:
        return tier[0]
    point = random.random() * total
    accumulated = 0.0
    for route in tier:
        accumulated += max(route.effective_weight(model), 0.0)
        if point <= accumulated:
            return route
    return tier[-1]


def _weighted_order(tier: list[Route], model: str) -> list[Route]:
    """Weighted draw without replacement: distribution first, ladder after."""
    remaining = list(tier)
    ordered: list[Route] = []
    while remaining:
        route = _weighted_pick(remaining, model)
        ordered.append(route)
        remaining.remove(route)
    return ordered


def ordered_routes(routes: list[Route], model: str, *, state: "RouteState",
                   now: float, affinity_key: str | None = None) -> list[Route]:
    """Every healthy route serving ``model``, best-first, for one request.

    This is the failover ladder behind a single client request: the router may
    try successive entries while no byte has reached the client. Tiers ascend;
    inside a tier the configured weights order the attempts (drawn without
    replacement), and caller affinity pins the first attempt only while the
    tier is a single upstream provider where prompt-cache locality is real.
    """
    candidates = [r for r in routes if r.serves(model)]
    healthy = [r for r in candidates if state.available(r.route_id, now)]
    if not healthy:
        return []
    wanted = model.strip().lower()
    by_tier: dict[int, list[Route]] = {}
    for route in healthy:
        by_tier.setdefault(route.effective_priority(wanted), []).append(route)
    ordered: list[Route] = []
    for tier_priority in sorted(by_tier):
        tier = by_tier[tier_priority]
        if (affinity_key and len(tier) > 1
                and len({r.base_url for r in tier}) == 1):
            chosen_id = affinity_route([r.route_id for r in tier], affinity_key)
            first = [r for r in tier if r.route_id == chosen_id]
            rest = _weighted_order(
                [r for r in tier if r.route_id != chosen_id], wanted)
            ordered.extend(first + rest)
        else:
            ordered.extend(_weighted_order(tier, wanted))
    return ordered
