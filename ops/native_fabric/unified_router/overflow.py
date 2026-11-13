"""Admission-time overflow add-on for the unified fabric router's model-tier policy.

PREPARED, NOT APPLIED. Composes with ``model_policy.ModelPolicyState`` from the
model-tier-routing candidate (model-tier-v1-20261111) by wrapping five methods
on the live policy instance: plan, begin, finish, learn_limit and snapshot.
It reuses the candidate's rate window, prefix estimates, per-resource budgets,
in-flight caps, cooldowns and 30-minute stickiness; it owns none of them.

What it adds
  * NEW sessions pinned to an exact kimi-* / deepseek-* model are diverted to a
    configured GLM target when no per-key budget can admit them.
  * In-flight sessions are never migrated. One exception: a short session may
    take ONE diverted request after N consecutive 429s.
  * A diverted session stays on its target (it is in flight there).
  * Hysteresis: a family keeps overflowing until it has shown no 429, cooldown
    or saturation for ``healthy_hold_s``.
  * Warm-wait: a session with a warm prefix on one key waits for that key
    rather than re-paying its whole prefix uncached on the sibling key.
  * Per-key accounting against a headroom target (default 80% of the limit).
  * Morph's ``{"detail": "..."}`` 429 body is translated for learn_limit.
  * The Claude Code billing-header line is removed from the system prompt on
    non-Anthropic wires so the upstream prefix is identical across sessions.

Nothing here reads credentials, sends inference or touches auth handling.
Disabled unless the routing policy contains ``"overflow": {"enabled": true}``;
``FABRIC_OVERFLOW=0`` in the process environment forces it off.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from collections import OrderedDict, deque
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

VERSION = "fabric-overflow-v1-20261110"
_log = logging.getLogger("fabric.overflow")

DEFAULTS = {
    "enabled": False,
    # Exact-model pins only; alias groups already spill inside the tier policy.
    "families": {
        "kimi": {"match": ["kimi-"], "target": "glm-5.3", "cap_fallback": "wait"},
        "deepseek": {"match": ["deepseek-"], "target": "glm-5.3-flash"},
    },
    # Limits on diversion INTO a target. cap_fallback: "wait" or a model slug.
    "caps": {"glm-5.3": {"max_inflight": 2, "max_new_sessions_per_hour": 20}},
    "headroom": 0.8,
    "oversize_on_idle": False,
    "new_session_max_messages": 3,
    "diverted_sticky_s": 1800,
    "healthy_hold_s": 300,
    "short_session": {"consecutive_429": 3, "max_served_turns": 3,
                      "max_input_estimate": 30000},
    "warm_wait": {"enabled": True, "max_wait_s": 90,
                  "cold_failover_max_estimate": 8000},
    "strip_billing_header": True,
}

_BILLING = re.compile(r"\A\s*x-anthropic-billing-header:[^\n]*(?:\n|\Z)")
_LIMIT = re.compile(r"limit\s*[:=]?\s*([0-9][0-9,]{0,12})\s+(uncached\s+input|input|output)\s+tokens")


def merged_config(raw):
    """DEFAULTS overlaid with the policy's ``overflow`` object (one level deep)."""
    result = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        if key not in DEFAULTS:
            continue
        if isinstance(DEFAULTS[key], dict) and key not in ("families", "caps"):
            if isinstance(value, dict):
                result[key].update(value)
        elif isinstance(DEFAULTS[key], dict):
            if isinstance(value, dict):
                result[key] = value
        elif type(value) is type(DEFAULTS[key]) or (
                isinstance(DEFAULTS[key], float) and type(value) is int):
            result[key] = value
    if not 0.1 <= float(result["headroom"]) <= 1.0:
        result["headroom"] = DEFAULTS["headroom"]
    return result


def strip_billing_header(payload):
    """Return a payload whose system prompt has no Claude Code billing-header line.

    The line carries a per-session suffix and is the first bytes of the system
    prompt, so it defeats cross-session prefix caching on OpenAI-wire upstreams.
    Never mutates the input; returns the same object when nothing changes.
    """
    system = payload.get("system") if isinstance(payload, dict) else None
    if isinstance(system, str):
        stripped = _BILLING.sub("", system, count=1)
        return payload if stripped == system else dict(payload, system=stripped)
    if not isinstance(system, list):
        return payload
    out, changed = [], False
    for block in system:
        text = block.get("text") if isinstance(block, dict) and block.get("type") == "text" else None
        if not changed and isinstance(text, str) and _BILLING.match(text):
            changed = True
            rest = _BILLING.sub("", text, count=1)
            if rest.strip():
                out.append(dict(block, text=rest))
            continue
        out.append(block)
    return dict(payload, system=out) if changed else payload


def translate_limit_body(body):
    """Morph 429 ``{"detail": "... Limit: N uncached input tokens/minute."}`` ->
    the ``{"error": {"message", "limit"}}`` shape the candidate's learn_limit parses.
    Returns the original bytes when the shape is not recognised."""
    if not isinstance(body, bytes) or len(body) > 4096:
        return body
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        return body
    if not isinstance(data, dict):
        return body
    text = data.get("detail")
    if not isinstance(text, str):
        error = data.get("error")
        text = error.get("message") if isinstance(error, dict) and type(error.get("limit")) is not int else None
    if not isinstance(text, str):
        return body
    match = _LIMIT.search(text[:3000].lower())
    if not match:
        return body
    kind = "uncached input" if "input" in match.group(2) else "output"
    return json.dumps({"error": {"message": kind + " tokens per minute limit",
                                 "limit": int(match.group(1).replace(",", ""))}}).encode()


def _has_rich_input(payload):
    stack = [payload.get("messages", []), payload.get("system", [])]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if value.get("type") in ("image", "document", "audio", "video"):
                return True
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False


class Overflow:
    """Ephemeral overflow state attached to one ModelPolicyState instance."""

    def __init__(self, policy, clock=time.monotonic):
        self.policy = policy
        self.clock = clock
        self._plan, self._begin = policy.plan, policy.begin
        self._finish, self._learn, self._snapshot = policy.finish, policy.learn_limit, policy.snapshot
        self.seen = OrderedDict()        # session -> served turns on its requested model
        self.diverted = OrderedDict()    # session -> [target, last_used, family, requested]
        self.c429 = OrderedDict()        # session -> consecutive 429 count
        self.fell_back = OrderedDict()   # session -> time of its one short fallback
        self.health = {}                 # family -> {"unhealthy_at", "since", "signal"}
        self.intents = OrderedDict()     # id(payload) -> (kind, family, requested, target, time)
        self.tokens = {}                 # admission token -> (kind, family, requested, target)
        self.cap_sessions = {}           # target -> deque of new-diversion times
        self.peak = {}                   # resource -> peak fraction of limit seen
        self.warm_waiting = OrderedDict()
        self.pending_429 = None
        self.events = deque(maxlen=64)
        self.counters = {k: 0 for k in (
            "diverted_new_session", "diverted_sticky", "diverted_short_fallback",
            "diverted_completed", "diverted_failed", "primary_admitted",
            "cap_refused", "target_unavailable", "warm_waits", "provider_429",
            "limit_bodies_translated", "billing_headers_stripped")}

    # ---- configuration -------------------------------------------------
    def config(self):
        return merged_config(self.policy.policy.get("overflow"))

    def enabled(self, cfg=None):
        if os.environ.get("FABRIC_OVERFLOW", "") == "0":
            return False
        return (cfg or self.config())["enabled"] is True

    @staticmethod
    def family_of(cfg, model):
        if not isinstance(model, str):
            return None, None
        low = model.lower()

        def _hit(pattern, value):
            pattern = pattern.lower()
            if pattern.startswith("*") and pattern.endswith("*"):
                return pattern[1:-1] in value
            if pattern.startswith("*"):
                return value.endswith(pattern[1:])
            if pattern.endswith("*"):
                return value.startswith(pattern[:-1])
            return value == pattern

        for name, fam in cfg["families"].items():
            if not isinstance(fam, dict):
                continue
            # An excluded slug keeps its own dedicated route. Uncensored and
            # abliterated variants are separate products: matching them into a
            # family would divert them to a censored model and silently change
            # what the caller asked for (observed 2026-11-11 with
            # deepseek-v4.1-flash-uncensored -> glm-5.3-flash).
            if any(isinstance(x, str) and x and _hit(x, low)
                   for x in fam.get("exclude", ())):
                continue
            if any(isinstance(p, str) and p and (
                    low.startswith(p[:-1]) if p.endswith("*")
                    else low.startswith(p) if p.endswith("-")
                    else low == p
                ) for p in fam.get("match", ())):
                return name, fam
        return None, None

    _WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

    @classmethod
    def _hhmm(cls, value, fallback_minutes):
        try:
            h_raw, _, m_raw = str(value).strip().partition(":")
            hour, minute = int(h_raw), int(m_raw or 0)
        except (TypeError, ValueError):
            return fallback_minutes
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return fallback_minutes
        return hour * 60 + minute

    @classmethod
    def in_window(cls, fam):
        """True when the family's diversion window is open (wall clock).

        The window is anchored in the provider's OWN billing timezone (e.g.
        Asia/Shanghai for Z.ai peak) so it can never drift with any observer's
        DST: "01:00-05:00 EST" is the winter rendering of 14:00-18:00 Shanghai,
        and anchoring New York instead would fire an hour early every summer.
        An absent window means "always"; an unparseable one means "never"
        (fail-closed: no diversion rather than diversion at the wrong hour).
        """
        win = fam.get("window") if isinstance(fam, dict) else None
        if not isinstance(win, dict):
            return True
        tz_name = str(win.get("tz") or "UTC")
        if ZoneInfo is None:
            return False
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            return False
        now = datetime.now(tz)
        start = cls._hhmm(win.get("start"), 0)
        end = cls._hhmm(win.get("end"), 24 * 60)
        if start == end:
            return False
        cur = now.hour * 60 + now.minute
        inside = (start <= cur < end) if start < end else (cur >= start or cur < end)
        if not inside:
            return False
        days = win.get("days")
        if isinstance(days, list) and days:
            want = {str(x).strip().lower()[:3] for x in days}
            if cls._WEEKDAYS[now.weekday()] not in want:
                return False
        return True

    # ---- helpers -------------------------------------------------------
    def _trim(self, mapping, limit=4096):
        while len(mapping) > limit:
            mapping.popitem(last=False)

    def _primary_routes(self, model):
        p = self.policy
        return [r for r in p.routes.values() if r.serves(model) and r.effective_weight(model) > 0
                and (r.route_id not in p.metered or p.allow_metered)]

    def _managed_routes(self, model):
        """Primary routes whose capacity this policy actually budgets (per-key
        input_tpm rules). Fallback lanes without a resource rule (e.g. a
        quota-walled weekly plan) carry no managed key: their cooldowns or
        quota 429s say nothing about the family's primary capacity and must
        not mark the whole family unhealthy. Observed live 2026-11-11:
        byteplus_coding's exhausted weekly quota kept the deepseek family in
        overflow for hours while both Morph keys sat idle at 0% load."""
        p = self.policy
        return [r for r in self._primary_routes(model) if r.route_id in p.resources]

    def _mark_unhealthy(self, family, now, signal):
        state = self.health.setdefault(family, {"unhealthy_at": None, "since": None, "signal": None})
        if state["since"] is None:
            state["since"] = now
            self._event({"event": "overflow_entered", "family": family, "signal": signal})
        state["unhealthy_at"], state["signal"] = now, signal

    def overflowing(self, family, now, cfg):
        state = self.health.get(family)
        if not state or state["unhealthy_at"] is None:
            return False
        if now - state["unhealthy_at"] >= float(cfg["healthy_hold_s"]):
            self._event({"event": "overflow_exited", "family": family,
                         "overflowed_s": round(now - state["since"], 1)})
            self.health[family] = {"unhealthy_at": None, "since": None, "signal": None}
            return False
        return True

    def _event(self, event):
        event = dict(event, t=round(time.time(), 3))
        self.events.append(event)
        _log.warning("fabric overflow %s", json.dumps(event, sort_keys=True))

    def _admissible(self, model, payload, session, now, fingerprint, cfg):
        """(admissible, oversize, best_eta): can a per-key budget take this request now
        while leaving ``1 - headroom`` of the key for sessions already in flight?"""
        p = self.policy
        best, oversize_all, any_route = float("inf"), True, False
        for route in self._primary_routes(model):
            any_route = True
            eta = p.eta(route, model, payload, session, now, fingerprint)
            best = min(best, eta)
            resource, rule = p.resource(route)
            limit = rule.get("input_tpm")
            if not limit:
                oversize_all = False
                if eta <= 0:
                    return True, False, 0.0
                continue
            inp = p.estimate(route, model, payload, session, now, fingerprint)[0]
            used = p.window.totals(resource, now)[0]
            target = float(cfg["headroom"]) * limit
            self.peak[resource] = max(self.peak.get(resource, 0.0), used / limit)
            if inp <= target:
                oversize_all = False
                if eta <= 0 and used + inp <= target:
                    return True, False, 0.0
            elif cfg["oversize_on_idle"] is True and eta <= 0 and used == 0:
                return True, True, 0.0
        return False, bool(any_route and oversize_all), best

    def _cap_ok(self, target, now, cfg, new_session):
        cap = cfg["caps"].get(target)
        if not isinstance(cap, dict):
            return True
        inflight = sum(1 for v in self.tokens.values() if v[3] == target)
        if inflight >= int(cap.get("max_inflight", 1 << 30)):
            return False
        if new_session:
            window = self.cap_sessions.setdefault(target, deque())
            while window and now - window[0] >= 3600:
                window.popleft()
            if len(window) >= int(cap.get("max_new_sessions_per_hour", 1 << 30)):
                return False
        return True

    def _divert(self, kind, family, fam, requested, payload, session, nonce, now, elapsed,
                fingerprint, cfg, profile):
        """Plan on the family's target chain; a plan tuple, or None to use base.

        The chain is ``targets`` (ordered), then the legacy single ``target``
        if set, then ``cap_fallback`` when it is a model slug. First target
        whose caps allow it AND whose plan has a ready ladder wins; a target
        that is capped or saturated is skipped, not fatal — the next rung (or
        finally the requested model itself, via the caller's base plan) serves.
        """
        choices: list = [t for t in (fam.get("targets") or []) if isinstance(t, str) and t]
        legacy = fam.get("target")
        if isinstance(legacy, str) and legacy and legacy not in choices:
            choices.append(legacy)
        fallback = fam.get("cap_fallback", "wait")
        if isinstance(fallback, str) and fallback not in ("wait", "") and fallback not in choices:
            choices.append(fallback)
        if kind == "sticky":
            # A diverted session is pinned to the model it was diverted TO:
            # hopping to another rung mid-conversation would silently switch
            # models on an in-flight session. If its target cannot serve, the
            # session reverts to base (sticky_revert) or waits — it never
            # tries a different substitute.
            choices = [t for t in choices if t == fam.get("target")]
        for target in choices:
            if kind != "sticky" and not self._cap_ok(target, now, cfg, kind == "new_session"):
                self.counters["cap_refused"] += 1
                continue
            ladder, eta, _, _ = self._plan([(target, "")], payload, session, nonce, now,
                                           elapsed, False, fingerprint)
            if ladder:
                self.intents[id(payload)] = (kind, family, requested, target, now)
                self._trim(self.intents, 512)
                return ladder, eta, "overflow_" + kind, profile
            if kind == "sticky" and math.isfinite(eta):
                if fam.get("sticky_revert"):
                    # Substitute chains prefer returning to the requested model
                    # over parking on a saturated substitute.
                    return None
                # An in-flight diverted session waits for its target; it is not bounced back.
                return [], eta, "FABRIC_OVERFLOW_TARGET_WAIT", profile
            self.counters["target_unavailable"] += 1
        return None

    # ---- wrapped policy methods ---------------------------------------
    def plan(self, candidates, payload, session, nonce, now, elapsed=0.0, counting=False,
             fingerprint=None):
        base = lambda: self._plan(candidates, payload, session, nonce, now, elapsed,
                                  counting, fingerprint)
        cfg = self.config()
        if counting or not self.enabled(cfg) or len(candidates) != 1 or candidates[0][1]:
            return base()
        requested = candidates[0][0]
        family, fam = self.family_of(cfg, requested)
        if family is None or _has_rich_input(payload):
            return base()   # never move image/document/audio input to another model
        profile = "model:" + requested
        p = self.policy
        managed = self._managed_routes(requested)
        if managed and all(p.route_state.cooldown_until.get(r.route_id, 0.0) > now
                           for r in managed):
            self._mark_unhealthy(family, now, "cooldown")

        # 1. A session already diverted stays where it is.
        record = self.diverted.get(session) if session else None
        if record and now - record[1] >= float(cfg["diverted_sticky_s"]):
            self.diverted.pop(session, None)
            record = None
        if record:
            plan = self._divert("sticky", family, dict(fam, target=record[0], cap_fallback="wait"),
                                requested, payload, session, nonce, now, elapsed,
                                fingerprint, cfg, profile)
            return plan if plan is not None else base()

        messages = payload.get("messages")
        count = len(messages) if isinstance(messages, list) else 0
        # In flight = already served on the requested model (or, after a router
        # restart that lost this memory, visibly past its first turns).
        in_flight = bool(session and (self.seen.get(session, 0) > 0 or (profile, session) in p.sticky)) \
            or count > int(cfg["new_session_max_messages"])

        if not in_flight:
            # 2. New session: divert when overflowing or when no key can admit it.
            admissible, oversize, _ = self._admissible(requested, payload, session, now,
                                                       fingerprint, cfg)
            if not admissible and not oversize:
                self._mark_unhealthy(family, now, "saturated")
            # A proactive family diverts NEW sessions while its window is open —
            # cost policy, not saturation: e.g. GLM-5.3 lanes open on Qwen4
            # while Qwen4's discount window makes it the cheaper primary.
            # A windowed family diverts ONLY inside its window: outside it, a
            # transient glm cooldown must not trigger substitution — the base
            # ladder (six chairman keys, benches, pacing) handles that, and
            # substituting outside the window pays the wrong provider's bill.
            windowed = isinstance(fam.get("window"), dict)
            window_open = not windowed or self.in_window(fam)
            proactive = bool(fam.get("proactive")) and window_open
            # A healthy independent seat wins over stale family hysteresis. Only
            # an explicit proactive/windowed policy may divert usable capacity.
            if window_open and (not admissible or proactive):
                plan = self._divert("new_session", family, fam, requested, payload, session,
                                    nonce, now, elapsed, fingerprint, cfg, profile)
                if plan is not None:
                    return plan
            return base()

        # 3. In-flight session: never migrated, except one short-session fallback.
        short = cfg["short_session"]
        if (session and self.c429.get(session, 0) >= int(short["consecutive_429"])
                and session not in self.fell_back
                and self.seen.get(session, 0) <= int(short["max_served_turns"])
                and count <= 2 * int(short["max_served_turns"]) + 1
                and (fingerprint[1] if fingerprint else 0) <= float(short["max_input_estimate"])):
            plan = self._divert("short_fallback", family, fam, requested, payload, session,
                                nonce, now, elapsed, fingerprint, cfg, profile)
            if plan is not None:
                return plan

        # 4. Prefer waiting for the warm key over re-paying the prefix on a cold sibling.
        ladder, eta, reason, prof = base()
        warm = cfg["warm_wait"]
        if warm.get("enabled") is True and session and ladder:
            warm_ids = {rid for (rid, model, sess), value in p.prefixes.items()
                        if sess == session and model == requested and now - value[0] < 900}
            if warm_ids and not any(route.route_id in warm_ids for route, _ in ladder):
                warm_eta = min((p.eta(p.routes[rid], requested, payload, session, now, fingerprint)
                                for rid in warm_ids if rid in p.routes), default=float("inf"))
                if 0 < warm_eta <= float(warm["max_wait_s"]) and elapsed < float(warm["max_wait_s"]):
                    limit = float(warm["cold_failover_max_estimate"])
                    kept = [(route, model) for route, model in ladder
                            if model != requested or p.estimate(route, model, payload, session,
                                                                now, fingerprint)[0] <= limit]
                    if not kept:
                        if id(payload) not in self.warm_waiting:
                            self.warm_waiting[id(payload)] = now
                            self._trim(self.warm_waiting, 512)
                            self.counters["warm_waits"] += 1
                        return [], warm_eta, "FABRIC_OVERFLOW_WARM_WAIT", prof
                    ladder = kept
        return ladder, eta, reason, prof

    def begin(self, route, model, payload, session, profile, now, fingerprint=None, *, operation="inference"):
        if operation != "inference":
            self.intents.pop(id(payload), None)
            self.warm_waiting.pop(id(payload), None)
            return self._begin(route, model, payload, session, profile, now, fingerprint, operation=operation)
        admission = self._begin(route, model, payload, session, profile, now, fingerprint)
        intent = self.intents.pop(id(payload), None)
        self.warm_waiting.pop(id(payload), None)
        requested = profile[6:] if isinstance(profile, str) and profile.startswith("model:") else None
        family = self.family_of(self.config(), requested)[0] if requested and requested != model else None
        if family:
            # The policy only admits another model under an exact pin when plan() diverted it.
            kind = intent[0] if intent and intent[3] == model else (
                "sticky" if session and session in self.diverted else "new_session")
            target = model
            self.tokens[admission.token] = (kind, family, requested, target)
            self.counters["diverted_" + kind] += 1
            if session:
                if kind == "short_fallback":
                    self.fell_back[session] = now
                    self.c429.pop(session, None)
                    self._trim(self.fell_back)
                else:
                    if kind == "new_session":
                        self.cap_sessions.setdefault(target, deque()).append(now)
                    self.diverted[session] = [target, now, family, requested]
                    self.diverted.move_to_end(session)
                    self._trim(self.diverted)
            elif kind == "new_session":
                self.cap_sessions.setdefault(target, deque()).append(now)
            self._event({"event": "diverted", "kind": kind, "family": family,
                         "requested_model": requested, "served_model": model,
                         "route": route.route_id, "request": admission.token,
                         "session": session[:12] if session else None,
                         "input_estimate": round(admission.full_estimate)})
        elif self.enabled() and profile == "model:" + model and self.family_of(self.config(), model)[0]:
            self.counters["primary_admitted"] += 1
            if session:
                self.seen.setdefault(session, 0)
                self.seen.move_to_end(session)
                self._trim(self.seen)
        return admission

    def finish(self, admission, *, success=False, no_send=False):
        if admission is None or admission.settled:
            return self._finish(admission, success=success, no_send=no_send)
        if getattr(admission, "operation", "inference") != "inference":
            return self._finish(admission, success=success, no_send=no_send)
        hit_429 = self.pending_429 == admission.route_id
        self.pending_429 = None
        self._finish(admission, success=success, no_send=no_send)
        marked = self.tokens.pop(admission.token, None)
        session = admission.session
        if marked:
            self.counters["diverted_completed" if success else "diverted_failed"] += 1
            if success and session in self.diverted:
                self.diverted[session][1] = self.clock()
        elif session:
            if success:
                self.c429.pop(session, None)
                if session in self.seen:
                    self.seen[session] += 1
            elif hit_429:
                self.c429[session] = self.c429.get(session, 0) + 1
                self.c429.move_to_end(session)
                self._trim(self.c429)

    def learn_limit(self, route, body):
        cfg = self.config()
        if not self.enabled(cfg):
            return self._learn(route, body)
        now = self.clock()
        self.pending_429 = route.route_id
        self.counters["provider_429"] += 1
        if route.route_id in self.policy.resources and route.route_id not in self.policy.metered:
            # Only a managed primary key's 429 signals family-level pressure.
            # A quota-walled fallback (weekly plan exhausted) is that route's
            # own ceiling, not evidence the family's primaries are saturated.
            for name, fam in cfg["families"].items():
                if any(self.family_of({"families": {name: fam}}, m)[0] for m in route.models):
                    self._mark_unhealthy(name, now, "provider_429")
        translated = translate_limit_body(body)
        if translated is not body:
            self.counters["limit_bodies_translated"] += 1
        return self._learn(route, translated)

    def keys(self, cfg=None):
        """Per-key uncached-input accounting against the headroom target."""
        cfg = cfg or self.config()
        p, now, result = self.policy, self.clock(), {}
        for route in p.routes.values():
            resource, rule = p.resource(route)
            limit = rule.get("input_tpm")
            if not limit or resource in result:
                continue
            used = p.window.totals(resource, now)[0]
            self.peak[resource] = max(self.peak.get(resource, 0.0), used / limit)
            result[resource] = {
                "input_tpm_limit": limit, "target": round(float(cfg["headroom"]) * limit, 1),
                "used_or_reserved": round(used, 1), "used_pct_of_limit": round(100 * used / limit, 1),
                "over_target": used > float(cfg["headroom"]) * limit,
                "peak_pct_of_limit": round(100 * self.peak[resource], 1),
                "cooling_s": round(max(0.0, p.route_state.cooldown_until.get(route.route_id, 0.0) - now), 1)}
        return result

    def snapshot(self):
        result = self._snapshot()
        cfg = self.config()
        enabled = self.enabled(cfg)
        now = self.clock()
        c = self.counters
        diverted = c["diverted_new_session"] + c["diverted_sticky"] + c["diverted_short_fallback"]
        considered = diverted + c["primary_admitted"]
        families = {}
        for name in cfg["families"]:
            state = self.health.get(name) or {}
            active = enabled and self.overflowing(name, now, cfg)
            state = self.health.get(name) or {}
            fam_cfg = cfg["families"].get(name) or {}
            families[name] = {
                "overflowing": bool(active),
                "signal": state.get("signal") if active else None,
                "overflowing_for_s": round(now - state["since"], 1) if active else 0.0,
                "healthy_in_s": round(float(cfg["healthy_hold_s"]) - (now - state["unhealthy_at"]), 1) if active else 0.0,
                "proactive_window_open": bool(fam_cfg.get("proactive")) and self.in_window(fam_cfg)}
        result["overflow"] = {
            "version": VERSION, "enabled": enabled, "counters": dict(c),
            "diverted_requests": diverted,
            "diversion_share": round(diverted / considered, 4) if considered else 0.0,
            "families": families, "keys": self.keys(cfg),
            "diverted_sessions": len(self.diverted),
            "diverted_inflight": len(self.tokens),
            "recent": list(self.events)[-20:]}
        if enabled:
            # Exact kimi-*/deepseek-* pins may now be served by the overflow target.
            result["exact_model_pins_preserved"] = False
        return result


_ACTIVE = []  # the overflow instance of the most recently installed app


def install(app, gateway_module=None):
    """Attach overflow to ``app.state.model_policy``. Idempotent. Call once in
    create_app, after the policy is constructed. ``gateway_module`` (the module
    that owns ``anthropic_to_openai``) gets the billing-header strip."""
    policy = app.state.model_policy
    overflow = getattr(policy, "overflow", None)
    if overflow is None:
        overflow = Overflow(policy)
        policy.overflow = overflow
        policy.plan, policy.begin, policy.finish = overflow.plan, overflow.begin, overflow.finish
        policy.learn_limit, policy.snapshot = overflow.learn_limit, overflow.snapshot
    _ACTIVE[:] = [overflow]
    if gateway_module is not None and not getattr(gateway_module, "_overflow_wire_wrapped", False):
        for name in ("anthropic_to_openai", "anthropic_to_responses"):
            original = getattr(gateway_module, name, None)
            if original is None:
                continue

            def translate(body, _original=original):
                current = _ACTIVE[0] if _ACTIVE else None
                if current is not None:
                    cfg = current.config()
                    if current.enabled(cfg) and cfg["strip_billing_header"] is True:
                        stripped = strip_billing_header(body)
                        if stripped is not body:
                            current.counters["billing_headers_stripped"] += 1
                        body = stripped
                return _original(body)

            setattr(gateway_module, name, translate)
        gateway_module._overflow_wire_wrapped = True
    return overflow
