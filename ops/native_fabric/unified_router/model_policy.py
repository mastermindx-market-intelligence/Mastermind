"""Model-tier admission inside the incumbent router, not a new service or quota authority.

All estimates are local pacing hints. Provider limits/refusals remain authoritative.
Nothing here reads credentials, sends inference, rewrites prompts, or restarts work.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field

VERSION = "model-tier-v1-20261111"


def positive(value, default=0.0, maximum=1e9):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value) if math.isfinite(value) and 0 <= value <= maximum else default


def session_key(headers, payload):
    """Stable per-conversation hints, never an authentication or account identity."""
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    fabric = metadata.get("fabric") or {}
    if not isinstance(fabric, dict):
        fabric = {}
    sdk_session = None
    sdk_user = metadata.get("user_id")
    if isinstance(sdk_user, str) and len(sdk_user) <= 1024:
        if sdk_user.startswith("{"):
            try:
                decoded = json.loads(sdk_user)
                sdk_session = decoded.get("session_id") if isinstance(decoded, dict) else None
            except ValueError:
                pass
        else:
            import re
            match = re.search(r"(?:^|_)session_([a-fA-F0-9-]{16,64})$", sdk_user)
            sdk_session = match.group(1) if match else None
    candidates = [headers.get(k) for k in (
        "x-fabric-session-id", "x-session-id", "session_id", "x-conversation-id")]
    candidates += [fabric.get("session_id"), payload.get("prompt_cache_key"),
                   metadata.get("session_id"), metadata.get("conversation_id"), sdk_session]
    for value in candidates:
        if isinstance(value, str) and 0 < len(value) <= 512 and not any(ord(c) < 32 for c in value):
            return hashlib.sha256(value.encode()).hexdigest()
    key = conversation_key(payload)
    if key:
        return key
    return None  # No messages to anchor on: keep truly empty callers unmerged.


def conversation_key(payload: dict) -> str | None:
    """Stable per-conversation key for callers that send no session hint.

    Headerless callers (T3/DSH lanes) previously fell through to a per-request
    nonce in plan(), which made routing actively anti-affine: every turn of the
    same thread could land on a different key and repay the whole prompt cache.
    Anchor on the parts of a thread that never change across turns -- system
    prompt, tool definitions, and the FIRST user message -- so the key is
    stable from turn 1 onward (hashing messages[:2] would split identity
    between turns 1 and 2). Colliding threads share only a route pin and a
    cache lane; no request data crosses, and estimate() still intersects
    actual prefix hashes so a collision cannot fake warm-token credit.
    """
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        return None
    first_user = next((m for m in msgs if isinstance(m, dict) and m.get("role") == "user"), None)
    if first_user is None:
        return None
    try:
        basis = json.dumps({"s": payload.get("system"), "t": payload.get("tools"),
                            "m": first_user},
                           sort_keys=True, ensure_ascii=False, default=str,
                           separators=(",", ":"))[:16384]
    except (TypeError, ValueError):
        return None
    return "anon-" + hashlib.sha256(basis.encode()).hexdigest()


def prefix_signature(payload):
    """Bounded prefix hashes, no retained prompt text. Estimates are NOT token counts."""
    chunks = [json.dumps({k: payload[k] for k in ("system", "tools") if k in payload},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))]
    messages = payload.get("messages", [])
    if isinstance(messages, list):
        chunks.extend(json.dumps(m, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":")) for m in messages)
    digest = hashlib.sha256()
    result, total = [], 0.0
    for chunk in chunks:
        # Bytes/3 is conservative for English/code and does not undercount CJK as chars/4 does.
        data = chunk.encode(); total += len(data) / 3.0 + 12.0
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
        result.append((digest.hexdigest(), total))
    # Full context accounting remains intact; only retained fingerprint detail is bounded.
    return tuple(result[-512:]), max(1.0, total)


def normalized_usage(usage, wire):
    """Return total input, uncached input, cache read, output; None means unknown."""
    if not isinstance(usage, dict):
        return None
    def integer(key, source=usage):
        value = source.get(key)
        return value if type(value) is int and 0 <= value <= 10**9 else None
    if wire == "anthropic":
        inp, out = integer("input_tokens"), integer("output_tokens")
        cache = integer("cache_read_input_tokens") or 0
        creation = integer("cache_creation_input_tokens") or 0
        if inp is None or out is None:
            return None
        return {"input": inp + cache + creation, "uncached_input": inp + creation,
                "cached_input": cache, "output": out}
    inp, out = integer("prompt_tokens"), integer("completion_tokens")
    if inp is None:  # Responses wire
        inp, out = integer("input_tokens"), integer("output_tokens")
    if inp is None or out is None:
        return None
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    cache = integer("cached_tokens", details) if isinstance(details, dict) else None
    hit, miss = integer("prompt_cache_hit_tokens"), integer("prompt_cache_miss_tokens")
    if cache is None:
        cache = hit if hit is not None else 0
    if cache > inp or (hit is not None and miss is not None and hit + miss != inp):
        return None
    if miss is not None and hit is None and cache == 0:
        if miss > inp:
            return None
        cache = inp - miss
    return {"input": inp, "uncached_input": inp - cache,
            "cached_input": cache, "output": out}


@dataclass
class Admission:
    token: str
    route_id: str
    resource: str
    model: str
    session: str | None
    profile: str
    started: float
    input_estimate: float
    output_estimate: float
    prefixes: tuple
    full_estimate: float
    usage: dict | None = None
    reported_model: str | None = None
    sent: bool = False
    completed: bool = False
    settled: bool = False
    input_basis: str = "total"
    requested_max_tokens: int = 4096
    effective_max_tokens: int | None = None
    finish_reason: str | None = None
    operation: str = "inference"
    concurrency_group: str = ""
    circuit_generation: int = 0


class ModelPolicyState:
    """Ephemeral state attached to RouterState; the existing RateWindow owns reservations."""
    def __init__(self, routes, aliases, policy, rate_window, route_state):
        self.routes = {r.route_id: r for r in routes}
        self.concurrency_limits = {}
        for route in routes:
            if route.concurrency_group:
                previous = self.concurrency_limits.setdefault(route.concurrency_group, route.group_max_in_flight)
                if previous != route.group_max_in_flight:
                    raise ValueError("conflicting shared concurrency limits")
        self.aliases = dict(aliases)
        self.policy = policy or {}
        self.window = rate_window
        self.route_state = route_state
        self.groups = self.policy.get("groups", {})
        self.resources = self.policy.get("resources", {})
        self.metered = frozenset(self.policy.get("metered_routes", []))
        self.allow_metered = self.policy.get("allow_metered_fallback", False) is True
        self.sticky = OrderedDict()
        self.prefixes = OrderedDict()
        self.output_ewma = {}
        self.active = {}
        self.waiters = {}
        self.events = deque(maxlen=128)
        self.changed = asyncio.Event()
        self.draining = False
        self.observed_limits = {}
        self.provider_capacity = {}
        self.recovery_until = {}
        self.checkpoint_path = None
        self.persistence_error = None
        self.persistence_restored = False
        self.async_checkpoints = False
        self.checkpoint_revision = 0
        self.durable_revision = 0
        self.checkpoint_write_ms = None
        self._checkpoint_task = None
        self._checkpoint_changed = asyncio.Event()
        self._checkpoint_urgent = asyncio.Event()
        self._checkpoint_next_at = 0.0
        self.uncertainty_s = 960.0
        self.counters = {k: 0 for k in ("selected", "completed", "failed", "cache_affinity_hits",
            "model_spillovers", "capacity_waits", "queue_refused", "unknown_usage", "quota_refusals",
            "metering_selected", "metering_completed", "metering_failed")}
        self._validate()

    def configure_persistence(self, path, uncertainty_s=960):
        from .admission_state import restore
        self.checkpoint_path = path
        self.uncertainty_s = uncertainty_s
        restore(self)

    def checkpoint(self):
        if self.checkpoint_path is not None:
            if self.async_checkpoints:
                self.checkpoint_revision += 1
                self._start_checkpoint_writer()
                return self.persistence_error is None
            from .admission_state import save
            return save(self)
        return True

    def _start_checkpoint_writer(self):
        if self.persistence_error or self.checkpoint_path is None:
            return
        if self._checkpoint_task is None or self._checkpoint_task.done():
            self._checkpoint_task = asyncio.create_task(self._write_checkpoints())

    async def _write_checkpoints(self):
        from .admission_state import encode, write
        try:
            while self.durable_revision < self.checkpoint_revision and not self.persistence_error:
                delay = max(0.0, self._checkpoint_next_at - time.monotonic())
                if delay and not self._checkpoint_urgent.is_set():
                    try:
                        await asyncio.wait_for(self._checkpoint_urgent.wait(), delay)
                    except TimeoutError:
                        pass
                self._checkpoint_urgent.clear()
                revision = self.checkpoint_revision
                raw = encode(self)
                began = time.monotonic()
                # One writer, immutable bytes, and monotonic revisions: a slow
                # older write can never overwrite a newer committed snapshot.
                await asyncio.to_thread(write, self.checkpoint_path, raw)
                self.checkpoint_write_ms = round((time.monotonic() - began) * 1000, 1)
                self.durable_revision = revision
                self._checkpoint_next_at = time.monotonic() + 1.0
                self._checkpoint_changed.set()
        except (OSError, ValueError, TypeError):
            # Latch errors; no write/retry storm on an unavailable state store.
            self.persistence_error = "FABRIC_ADMISSION_CHECKPOINT_WRITE_FAILED"
        finally:
            self._checkpoint_changed.set()

    async def flush_checkpoint(self, timeout_s=10.0):
        if self.checkpoint_path is None:
            return True
        if not self.async_checkpoints:
            return self.checkpoint()
        target = self.checkpoint_revision
        deadline = time.monotonic() + timeout_s
        self._checkpoint_urgent.set()
        self._start_checkpoint_writer()
        while self.durable_revision < target and not self.persistence_error:
            self._checkpoint_changed.clear()
            try:
                await asyncio.wait_for(self._checkpoint_changed.wait(), max(0.001, deadline - time.monotonic()))
            except TimeoutError:
                self.persistence_error = "FABRIC_ADMISSION_CHECKPOINT_TIMEOUT"
                self._checkpoint_changed.set()
        return self.persistence_error is None

    def _validate(self):
        if not isinstance(self.groups, dict) or not isinstance(self.resources, dict):
            raise ValueError("invalid model routing policy")
        for key, default, maximum in (("max_waiters", 128, 1024), ("max_per_session_waiters", 8, 32)):
            value = self.policy.get(key, default)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid bounded queue limit")
        for name, group in self.groups.items():
            if name not in self.aliases or not isinstance(group, dict):
                raise ValueError("model routing group must name an existing alias")
            if group.get("strategy", "balanced") not in ("balanced", "ordered"):
                raise ValueError("invalid model-tier strategy")
            if "capacity_aware" in group and type(group["capacity_aware"]) is not bool:
                raise ValueError("invalid capacity-aware routing policy")
            allowed = group.get("routes", {})
            weights = group.get("weights", {})
            if not isinstance(allowed, dict) or not isinstance(weights, dict):
                raise ValueError("invalid model group routes/weights")
            for model in self.aliases[name]:
                if model not in allowed or not allowed[model]:
                    raise ValueError("every group model needs explicit allowed routes")
                if positive(weights.get(model), -1) <= 0:
                    raise ValueError("model weight must be finite and positive")
                for rid in allowed[model]:
                    if rid not in self.routes or not self.routes[rid].serves(model):
                        raise ValueError("model group route/model binding is invalid")
                    if rid in self.metered and not self.allow_metered:
                        raise ValueError("included model tier must not include metered routes")
        exact = self.policy.get("exact_route_allowlists", {})
        if not isinstance(exact, dict):
            raise ValueError("invalid exact-model route constraints")
        for model, ids in exact.items():
            if not isinstance(ids, list) or not ids or any(rid not in self.routes or not self.routes[rid].serves(model) for rid in ids):
                raise ValueError("invalid exact-model route binding")
        if self.metered - set(self.routes):
            raise ValueError("metered route identity is unknown")
        for rid, rule in self.resources.items():
            if rid not in self.routes or not isinstance(rule, dict):
                raise ValueError("resource route binding is invalid")
            key = rule.get("key", rid)
            if not isinstance(key, str) or not 1 <= len(key) <= 128:
                raise ValueError("invalid native resource reference")
            for field in ("input_tpm", "output_tpm", "max_inflight"):
                if field in rule and positive(rule[field], -1) <= 0:
                    raise ValueError("invalid admission resource limit")
            cap = rule.get("max_inflight", 8)
            if type(cap) is not int or not 1 <= cap <= 128:
                raise ValueError("inflight cap must be a bounded integer")
            if "allow_one_oversize" in rule and type(rule["allow_one_oversize"]) is not bool:
                raise ValueError("invalid oversize admission policy")
            if rule.get("input_basis", "total") not in ("total", "uncached"):
                raise ValueError("invalid resource input accounting basis")
            if not 0 < positive(rule.get("headroom", 1), -1, 1) <= 1:
                raise ValueError("invalid resource headroom")
            for flag in ("strict_output_reservation", "require_observed_cache", "provider_headers"):
                if flag in rule and type(rule[flag]) is not bool:
                    raise ValueError("invalid resource capacity policy")
            if "alias_max_output_tokens" in rule and (type(rule["alias_max_output_tokens"]) is not int
                    or not 1 <= rule["alias_max_output_tokens"] <= 1000000):
                raise ValueError("invalid alias output bound")
        # One native resource cannot acquire contradictory limits from route aliases.
        seen = {}
        for rid, rule in self.resources.items():
            key = rule.get("key", rid)
            value = tuple(rule.get(k) for k in ("input_tpm", "output_tpm", "max_inflight", "input_basis",
                "headroom", "strict_output_reservation", "alias_max_output_tokens", "provider_headers",
                "require_observed_cache", "allow_one_oversize"))
            if key in seen and seen[key] != value:
                raise ValueError("shared native resource has contradictory limits")
            seen[key] = value

    def resource(self, route):
        rule = self.resources.get(route.route_id, {})
        return rule.get("key", route.route_id), rule

    def limits(self, route):
        _, rule = self.resource(route)
        factor = positive(rule.get("headroom", 1), 1, 1)
        return tuple(positive(rule.get(field, route.rate_budget(kind))) * factor
                     for field, kind in (("input_tpm", "input"), ("output_tpm", "output")))

    def output_bound(self, route, model, payload):
        """Aliases may opt into a visible bound; exact-model ceilings stay intact."""
        _, rule = self.resource(route)
        requested = max(1, int(positive(payload.get("max_tokens"), 4096)))
        effective = requested
        if str(payload.get("model", "")).strip().lower() in self.groups:
            effective = min(effective, int(rule.get("alias_max_output_tokens", effective)))
        return requested, effective if rule.get("strict_output_reservation") else None

    def headroom(self, route, now):
        resource, rule = self.resource(route)
        if self.recovery_until.get(resource, 0) > now or (self.persistence_error and rule.get("strict_output_reservation")):
            return 0.0
        amounts = self.window.totals(resource, now)
        ratios = [max(0.0, 1 - used / limit) for used, limit in zip(amounts, self.limits(route)) if limit]
        ratios.append(max(0.0, 1 - sum(a.resource == resource for a in self.active.values()) /
                          int(rule.get("max_inflight", 8))))
        for dimension, view in self.provider_capacity.get(resource, {}).items():
            if now - view["at"] < 60:
                ratios.append(max(0.0, view["remaining"] / max(1, view["limit"])))
        return min(ratios, default=1.0)

    def estimate(self, route, model, payload, session, now, fingerprint=None):
        signatures, full = fingerprint or prefix_signature(payload)
        cached = 0.0
        prior = self.prefixes.get((route.route_id, model, session)) if session else None
        if prior and now - prior[0] < 900:
            # Only prefixes acknowledged by the same model/route are reusable hints.
            old = dict(prior[1])
            common = max((min(amount, old[h]) for h, amount in signatures if h in old), default=0.0)
            # Never assume perfect caching. A newly warmed prefix receives only a 90% hint;
            # an observed cache miss reduces that expectation for this session.
            cached = common * prior[2]
        _, rule = self.resource(route)
        inp = max(1.0, full - cached) if rule.get("input_basis") == "uncached" else full
        cap, bound = self.output_bound(route, model, payload)
        predicted = max(256.0, self.output_ewma.get((route.route_id, model), 512.0) * 1.5)
        out = float(bound) if bound is not None else min(cap, predicted, 4096.0)
        return inp, out, signatures, full

    @staticmethod
    def wire_compatible(route, payload):
        if route.wire == "anthropic":
            return True
        # Completed MCP history can be translated, but provider-side tool
        # configuration and state cannot be dropped to fit another wire.
        if payload.get("mcp_servers") or payload.get("container"):
            return False
        if not isinstance(payload.get("tools", []), list):
            return False
        return not any(isinstance(tool, dict) and tool.get("type") not in (None, "custom")
                       for tool in (payload.get("tools") or []))

    def concurrency_eta(self, route, *, inference=True):
        """All concurrency constraints derive from the single active ledger."""
        if len(self.active) >= 128:
            return 1.0
        resource, rule = self.resource(route)
        active = tuple(self.active.values())
        if sum(a.resource == resource for a in active) >= int(rule.get("max_inflight", 8)):
            return 1.0
        if route.max_in_flight and sum(a.route_id == route.route_id for a in active) >= route.max_in_flight:
            return 1.0
        if route.concurrency_group and sum(a.concurrency_group == route.concurrency_group for a in active) >= route.group_max_in_flight:
            return 1.0
        if inference and self.route_state.consecutive_failures.get(route.route_id, 0):
            if any(a.route_id == route.route_id and a.operation == "inference" for a in active):
                return 1.0
        return 0.0

    def eta(self, route, model, payload, session, now, fingerprint=None):
        if not self.wire_compatible(route, payload):
            return float("inf")
        if route.effective_weight(model) <= 0:
            return float("inf")
        until = self.route_state.cooldown_until.get(route.route_id, 0.0)
        if until > now:
            return until - now
        resource, rule = self.resource(route)
        if self.persistence_error and rule.get("strict_output_reservation"):
            return float("inf")
        recovery = self.recovery_until.get(resource, 0.0)
        if recovery > now:
            return recovery - now
        concurrency_wait = self.concurrency_eta(route)
        if concurrency_wait:
            return concurrency_wait
        inp, out, _, _ = self.estimate(route, model, payload, session, now, fingerprint)
        wait = self.window.wait_for(route, now, inp, out, resource_id=resource,
            limits=self.limits(route), allow_oversize=rule.get("allow_one_oversize", False) is True)
        for dimension, extra in (("input", inp), ("output", out)):
            view = self.provider_capacity.get(resource, {}).get(dimension)
            if view and now - view["at"] < 60 and extra > view["remaining"]:
                wait = max(wait, 60 - (now - view["at"]))
        return wait

    @staticmethod
    def _rendezvous(key, name, weight):
        raw = int.from_bytes(hashlib.sha256((key + "|" + name).encode()).digest()[:8], "big")
        u = (raw + 1) / (2**64 + 1)
        return -math.log(u) / weight

    def plan(self, candidates, payload, session, nonce, now, elapsed=0.0, counting=False, fingerprint=None):
        profile = candidates[0][1] or ("model:" + candidates[0][0])
        group = self.groups.get(profile)
        fingerprint = fingerprint or prefix_signature(payload)
        if group:
            # These cohorts qualify text/tool workflows only. Do not drop rich input to fit a tier.
            stack = [payload.get("messages", []), payload.get("system", [])]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    if value.get("type") in ("image", "document", "audio", "video"):
                        return [], float("inf"), "FABRIC_TIER_CAPABILITY_UNAVAILABLE", profile
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
        key = session or nonce
        sticky = self.sticky.get((profile, session)) if session else None
        if sticky and now - sticky[2] >= 1800:
            self.sticky.pop((profile, session), None); sticky = None
        options = []
        any_model = False
        incompatible_wire = False
        model_headroom = {}
        if group and group.get("capacity_aware"):
            for model, _ in candidates:
                model_headroom[model] = max((self.headroom(r, now) for r in self.routes.values()
                    if r.route_id in group["routes"].get(model, ())
                    and self.eta(r, model, payload, session, now, fingerprint) <= 0), default=0.0)
        for order, (model, _) in enumerate(candidates):
            for route in self.routes.values():
                if not route.serves(model):
                    continue
                any_model = True
                if route.effective_weight(model) <= 0:
                    continue
                has_included = any(r.serves(model) and r.route_id not in self.metered for r in self.routes.values())
                if route.route_id in self.metered and not self.allow_metered and (group or has_included):
                    continue
                exact_allowlist = self.policy.get("exact_route_allowlists", {}).get(model)
                if not group and exact_allowlist is not None and route.route_id not in exact_allowlist:
                    continue
                if group and route.route_id not in group["routes"].get(model, ()):
                    continue
                if not self.wire_compatible(route, payload):
                    incompatible_wire = True
                    continue
                if counting and route.wire != "anthropic":
                    continue
                eta = max(0.0, self.route_state.cooldown_until.get(route.route_id, 0) - now,
                    self.concurrency_eta(route, inference=False)) if counting else self.eta(route, model, payload, session, now, fingerprint)
                resource = self.resource(route)[0]
                inflight = sum(a.resource == resource for a in self.active.values())
                cap = self.resource(route)[1].get("max_inflight", 8)
                model_load = sum(a.model == model for a in self.active.values())
                model_weight = group["weights"].get(model, 1.0) if group else 1.0
                if group and group.get("capacity_aware"):
                    model_weight *= max(0.1, model_headroom.get(model, 0.0))
                model_rank = (order if group and group.get("strategy") == "ordered" else
                    self._rendezvous(key, model, model_weight) + model_load * 0.15 if group else order)
                route_rank = self._rendezvous(key, route.route_id, route.effective_weight(model))
                is_sticky = bool(sticky and sticky[0] == model and sticky[1] == route.route_id)
                options.append((eta, is_sticky, model_rank, route.effective_priority(model),
                                max(inflight / cap, 1 - self.headroom(route, now)), route_rank, route, model))
        if not options:
            code = "FABRIC_COUNT_TOKENS_WIRE" if counting and any_model else (
                "FABRIC_TIER_CAPABILITY_UNAVAILABLE" if incompatible_wire else
                "FABRIC_TIER_CAPACITY_UNAVAILABLE" if any_model else "FABRIC_MODEL_UNKNOWN")
            return [], float("inf"), code, profile
        ready = [x for x in options if x[0] <= 0]
        preference_s = min(2.0, positive(self.policy.get("affinity_wait_s", 1.5)))
        sticky_wait = next((x[0] for x in options if x[1]), float("inf"))
        if sticky and 0 < sticky_wait <= preference_s and elapsed < preference_s and not counting:
            return [], min(sticky_wait, preference_s - elapsed), "FABRIC_AFFINITY_WAIT", profile
        ready.sort(key=lambda x: (not x[1], x[2], x[3], x[4], x[5]))
        if group:
            # Two safe account probes per model, then another qualified model.
            # Six unhealthy accounts must not consume the whole cross-model attempt budget.
            by_model = OrderedDict()
            for option in ready:
                by_model.setdefault(option[7], deque()).append(option)
            ready = []
            while any(by_model.values()):
                for bucket in by_model.values():
                    for _ in range(min(2, len(bucket))):
                        ready.append(bucket.popleft())
        return [(x[6], x[7]) for x in ready], min(x[0] for x in options), (
            "session_affinity" if ready and ready[0][1] else "ready_tier" if group else "exact_model"), profile

    def begin(self, route, model, payload, session, profile, now, fingerprint=None, *, operation="inference"):
        resource, rule = self.resource(route)
        if operation not in {"inference", "count_tokens"}:
            raise ValueError("unknown admission operation")
        if self.concurrency_eta(route, inference=operation == "inference"):
            raise ValueError("admission concurrency changed before reservation")
        inp, out, signatures, full = (self.estimate(route, model, payload, session, now, fingerprint)
            if operation == "inference" else (0.0, 0.0, (), 0.0))
        token = uuid.uuid4().hex
        admission = Admission(token, route.route_id, resource, model, session, profile,
                              now, inp, out, signatures, full)
        admission.operation = operation
        admission.concurrency_group = route.concurrency_group
        admission.circuit_generation = self.route_state.generations.get(route.route_id, 0)
        if operation == "count_tokens":
            self.active[token] = admission
            self.counters["metering_selected"] += 1
            return admission
        admission.input_basis = rule.get("input_basis", "total")
        admission.requested_max_tokens, admission.effective_max_tokens = self.output_bound(route, model, payload)
        # No await between availability recheck and reservation: one event-loop owner.
        self.window.reserve(route.route_id, inp, out, request_id=token,
                            resource_id=resource, now=now)
        self.active[token] = admission
        for dimension, amount in (("input", inp), ("output", out)):
            view = self.provider_capacity.get(resource, {}).get(dimension)
            if view and now - view["at"] < 60:
                view["remaining"] -= amount
                view["reserved"][token] = amount
        self.counters["selected"] += 1
        self.checkpoint()
        return admission

    def observe_usage(self, admission, usage, wire, reported_model=None):
        if admission is None:
            return
        normalized = normalized_usage(usage, wire)
        if normalized is not None:
            admission.usage = normalized
        if isinstance(reported_model, str) and 0 < len(reported_model) <= 128 and all(
                c.isalnum() or c in "._-:/" for c in reported_model):
            admission.reported_model = reported_model

    def observe_headers(self, route, headers, admission=None, *, now=None):
        """Morph balances are observations, not grants; output is pre-completion.

        Reserve all locally active output against each new observation. The current
        request's input is already charged in its headers; other active inputs are
        conservatively deducted. Burst credit is never inferred or spent here.
        """
        from urllib.parse import urlsplit
        if urlsplit(route.base_url).hostname != "api.morphllm.com":
            return
        resource, rule = self.resource(route)
        if not rule.get("provider_headers"):
            return
        now = time.monotonic() if now is None else now
        def number(name, *, allow_negative=False):
            value = headers.get(name)
            if not isinstance(value, str) or len(value) > 16:
                return None
            digits = value[1:] if allow_negative and value.startswith("-") else value
            if not digits.isascii() or not digits.isdigit():
                return None
            parsed = int(value)
            return parsed if -10**9 <= parsed <= 10**9 else None
        changed = False
        for dimension, prefix, field in (("input", "uncached-input", "input_tpm"),
                                         ("output", "output", "output_tpm")):
            base = "x-morph-ultra-" + prefix
            limit = number(base + "-limit")
            remaining = number(base + "-remaining", allow_negative=True)
            if limit is None or limit <= 0:
                continue
            old = positive(rule.get(field))
            if old and limit < old:
                changed = True
                self.observed_limits.setdefault(resource, {})[field] = limit
                for rid, other in self.resources.items():
                    if other.get("key", rid) == resource:
                        other[field] = min(positive(other.get(field), limit), limit)
            if remaining is None:
                continue
            allowed = min(limit, positive(rule.get(field), limit)) * positive(rule.get("headroom", 1), 1, 1)
            reservations = {a.token: a.output_estimate if dimension == "output" else a.input_estimate
                for a in self.active.values() if a.resource == resource
                and (dimension == "output" or a is not admission)}
            self.provider_capacity.setdefault(resource, {})[dimension] = {
                "at": now, "limit": allowed, "remaining": min(remaining, allowed) - sum(reservations.values()),
                "reported_remaining": remaining, "reserved": reservations,
                "basis": "provider_pre_completion_minus_local_reservations" if dimension == "output"
                         else "provider_after_input_minus_other_reservations"}
            changed = True
        if changed:
            self.checkpoint()
            self.changed.set()

    def finish(self, admission, *, success=False, no_send=False):
        if admission is None or admission.settled:
            return
        admission.settled = True
        now = time.monotonic()
        if admission.operation == "count_tokens":
            self.active.pop(admission.token, None)
            self.counters["metering_completed" if success else "metering_failed"] += 1
            self.events.append({"request": admission.token, "operation": "count_tokens",
                "route": admission.route_id, "success": bool(success), "elapsed_s": round(now-admission.started, 3)})
            self.changed.set()
            return
        rule = self.resources.get(admission.route_id, {})
        usage = admission.usage
        if (admission.effective_max_tokens is not None and admission.sent
                and not no_send and not admission.completed and not success):
            # A disconnected local stream does not prove upstream stopped. Keep
            # this seat quarantined through the request horizon plus one window.
            self.recovery_until[admission.resource] = max(
                self.recovery_until.get(admission.resource, 0),
                admission.started + self.uncertainty_s)
        if usage and not no_send and hasattr(self, "usage_counters"):
            bucket = self.usage_counters.setdefault(admission.route_id, {"input": 0, "output": 0,
                "uncached_input": 0, "cached_input": 0})
            for name, amount in usage.items():
                bucket[name] = bucket.get(name, 0) + amount
        if no_send:
            self.window.release(admission.token)
        else:
            if usage:
                inp = usage["uncached_input"] if admission.input_basis == "uncached" else usage["input"]
                out = usage["output"]
                if not success and admission.effective_max_tokens is not None:
                    # A partial usage frame cannot prove upstream computation stopped.
                    inp, out = max(inp, admission.input_estimate), max(out, admission.output_estimate)
            else:
                inp, out = admission.input_estimate, admission.output_estimate
                self.counters["unknown_usage"] += 1
            # Uncertain/partial/missing-usage sends retain a conservative completed charge.
            self.window.settle(admission.route_id, now, inp, out, request_id=admission.token)
        for dimension, estimate in (("input", admission.input_estimate), ("output", admission.output_estimate)):
            view = self.provider_capacity.get(admission.resource, {}).get(dimension)
            if view and admission.token in view["reserved"]:
                reserved = view["reserved"].pop(admission.token)
                actual = 0.0 if no_send else (inp if dimension == "input" else out)
                view["remaining"] = min(view["limit"], view["remaining"] + reserved - actual)
        self.active.pop(admission.token, None)
        if success:
            self.counters["completed"] += 1
            if usage:
                old = self.output_ewma.get((admission.route_id, admission.model), usage["output"])
                self.output_ewma[(admission.route_id, admission.model)] = old * 0.75 + usage["output"] * 0.25
            if admission.session:
                key = (admission.profile, admission.session)
                old = self.sticky.get(key)
                if old and old[0] != admission.model:
                    self.counters["model_spillovers"] += 1
                elif old and old[:2] == (admission.model, admission.route_id):
                    self.counters["cache_affinity_hits"] += 1
                self.sticky[key] = (admission.model, admission.route_id, now)
                self.sticky.move_to_end(key)
                if usage:
                    pkey = (admission.route_id, admission.model, admission.session)
                    had_warm = pkey in self.prefixes
                    ratio = min(0.90, usage["cached_input"] / max(1, usage["input"])) if (
                        had_warm or rule.get("require_observed_cache")) else 0.90
                    self.prefixes[pkey] = (now, admission.prefixes, ratio)
                    self.prefixes.move_to_end(pkey)
                while len(self.sticky) > 4096:
                    self.sticky.popitem(last=False)
                while len(self.prefixes) > 1024:
                    self.prefixes.popitem(last=False)
        else:
            self.counters["failed"] += 1
            if admission.finish_reason == "stream_incomplete":
                self.route_state.record_failure(admission.route_id, "FABRIC_STREAM_INCOMPLETE",
                    now=now, cooldown_s=30, generation=admission.circuit_generation)
        self.events.append({"request": admission.token, "profile": admission.profile,
            "selected_model": admission.model, "reported_model": admission.reported_model,
            "route": admission.route_id, "success": bool(success),
            "requested_max_tokens": admission.requested_max_tokens,
            "effective_max_tokens": admission.effective_max_tokens,
            "finish_reason": admission.finish_reason,
            "usage": usage, "usage_known": usage is not None,
            "elapsed_s": round(now - admission.started, 3)})
        self.checkpoint()
        self.changed.set()

    def join_wait(self, nonce, session):
        limit = int(self.policy.get("max_waiters", 128))
        if len(self.waiters) >= limit or (session and sum(s == session for s in self.waiters.values()) >= self.policy.get("max_per_session_waiters", 8)):
            self.counters["queue_refused"] += 1
            return False
        self.waiters[nonce] = session
        self.counters["capacity_waits"] += 1
        return True

    def snapshot(self):
        now = time.monotonic()
        resources = {}
        for route in self.routes.values():
            resource, rule = self.resource(route)
            inp, out = self.window.totals(resource, now)
            input_limit, output_limit = self.limits(route)
            provider = {dimension: {"limit": view["limit"],
                "remaining_after_reservations": round(max(0.0, view["remaining"]), 1),
                "reported_remaining": view["reported_remaining"],
                "age_s": round(max(0, now - view["at"]), 1),
                "fresh": now - view["at"] < 60, "basis": view["basis"]}
                for dimension, view in self.provider_capacity.get(resource, {}).items()}
            resources[resource] = {"input_tpm": rule.get("input_tpm"),
                "output_tpm": rule.get("output_tpm"), "input_basis": rule.get("input_basis", "total"),
                "local_input_charged_or_reserved": round(inp, 1),
                "local_output_charged_or_reserved": round(out, 1),
                "inflight": sum(a.resource == resource for a in self.active.values()),
                "max_inflight": rule.get("max_inflight", 8),
                "effective_input_tpm": input_limit, "effective_output_tpm": output_limit,
                "headroom_fraction": round(self.headroom(route, now), 4),
                "strict_output_reservation": rule.get("strict_output_reservation", False),
                "alias_max_output_tokens": rule.get("alias_max_output_tokens"),
                "provider_capacity": provider,
                "recovery_wait_s": round(max(0, self.recovery_until.get(resource, 0) - now), 1),
                "quota_truth": "local_estimate_not_provider_balance"}
        return {"version": VERSION, "draining": self.draining, "active": len(self.active),
            "inference_active": sum(a.operation == "inference" for a in self.active.values()),
            "metering_active": sum(a.operation == "count_tokens" for a in self.active.values()),
            "concurrency_groups": {name: {"max_in_flight": limit,
                "inflight": sum(a.concurrency_group == name for a in self.active.values())}
                for name, limit in self.concurrency_limits.items()},
            "waiting": len(self.waiters), "counters": dict(self.counters),
            "resources": resources, "recent": list(self.events)[-20:],
            "exact_model_pins_preserved": True, "metered_fallback": self.allow_metered,
            "persistence": {"enabled": self.checkpoint_path is not None,
                "restored": self.persistence_restored, "error": self.persistence_error,
                "async_writer": self.async_checkpoints,
                "pending_revision": self.checkpoint_revision,
                "durable_revision": self.durable_revision,
                "last_write_ms": self.checkpoint_write_ms},
            "profiles": {name: {"models": list(self.aliases.get(name, ())),
                "strategy": group.get("strategy", "balanced"),
                "capacity_aware": group.get("capacity_aware", False),
                "weights": dict(group.get("weights", {}))} for name, group in self.groups.items()}}

    def learn_limit(self, route, body):
        """Accept only a LOWER numeric limit from a Morph 429, never an increase/grant.

        Unknown error shapes merely retain Retry-After handling. No raw upstream
        error text, account identifiers or credentials enter diagnostics.
        """
        from urllib.parse import urlsplit
        import re
        if urlsplit(route.base_url).hostname != "api.morphllm.com":
            return
        rule = self.resources.get(route.route_id)
        if not rule or not isinstance(body, bytes) or len(body) > 4096:
            return
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            return
        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            return
        text = error.get("message", "")
        if not isinstance(text, str):
            return
        text = text[:3000].lower()
        field = "input_tpm" if "uncached" in text and "input" in text else (
            "output_tpm" if "output" in text else None)
        if field is None:
            return
        limit = error.get("limit")
        if type(limit) is not int:
            match = re.search(r"(?:limit(?:\s+is)?|maximum)\s*[:=]?\s*([0-9][0-9,]{0,12})\s*(?:tokens|tpm|per minute|/min)", text)
            limit = int(match.group(1).replace(",", "")) if match else None
        old = rule.get(field)
        if type(limit) is int and 0 < limit < positive(old):
            resource = rule.get("key", route.route_id)
            self.observed_limits.setdefault(resource, {})[field] = limit
            for rid, other in self.resources.items():
                if other.get("key", rid) == resource:
                    other[field] = limit
            self.events.append({"route": route.route_id, "provider_limit_lowered": field,
                                "previous": old, "current": limit, "source": "upstream_429"})
            self.checkpoint()
