"""Explicit, fail-closed Experiential Labs two-organization admission adapter.

This is a local Brain backend adapter, NOT an Executive OS capacity owner.
It routes only NEW independent chat completions. A failed, refused, timed-out,
or ambiguous request is NEVER replayed or moved to another organization.
Status/telemetry are read from the gateway's existing org-scoped APIs;
local in-flight counters are per-process only, not fleet-wide quotas.
The existing shared ModelRouter and provider waterfall are unchanged.
"""
from __future__ import annotations

import hmac
import math
import os
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Callable

import httpx

from brain import explabs_client as gateway

_API_HOST = "https://api.experientiallabs.ai"
_REFRESH_SECONDS = 60.0
_SLOTS = (("1", "EXPLABS_API_KEY", "EXPLABS_ACCOUNT_1"), ("2", "EXPLABS_API_KEY_2", "EXPLABS_ACCOUNT_2"))


@dataclass(frozen=True)
class Account:
    slot: str
    key: str
    expected_org: str
    max_inflight: int
    max_daily_usd: float


@dataclass(frozen=True)
class Observation:
    org_id: str
    org_slug: str
    model: str
    key_remaining_usd: float | None
    credits_remaining_usd: float | None


@dataclass
class _Health:
    observation: Observation | None = None
    checked_at: float = 0.0
    blocked: str | None = None
    cooldown_until: float = 0.0
    inflight: int = 0
    unit_cost_per_1k_tokens: float | None = None


def _money(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _configs() -> tuple[Account, Account]:
    accounts = []
    for slot, key_name, stem in _SLOTS:
        key = os.environ.get(key_name, "")
        org = os.environ.get(stem + "_ORG_SLUG", "").strip()
        enable = os.environ.get(stem + "_ENABLED") == "1"
        if not enable or not key or not org:
            raise gateway.ExperientialError("explabs_pool_account_not_configured")
        raw = os.environ.get(stem + "_MAX_INFLIGHT", "2")
        try:
            cap = int(raw)
        except (TypeError, ValueError):
            raise gateway.ExperientialError("explabs_pool_invalid_capacity") from None
        if cap < 1 or cap > 32:
            raise gateway.ExperientialError("explabs_pool_invalid_capacity")
        max_daily_usd = _money(os.environ.get(stem + "_DAILY_CAP_USD"))
        if max_daily_usd is None or max_daily_usd <= 0:
            raise gateway.ExperientialError("explabs_pool_daily_cap_required")
        accounts.append(Account(slot, key, org, cap, max_daily_usd))
    if accounts[0].expected_org == accounts[1].expected_org:
        raise gateway.ExperientialError("explabs_pool_requires_distinct_orgs")
    return accounts[0], accounts[1]


def available() -> bool:
    if os.environ.get("EXPLABS_POOL_ENABLED") != "1":
        return False
    try:
        _configs()
    except gateway.ExperientialError:
        return False
    return True


class AccountPool:
    """Thread-safe in-process pre-dispatch selection; no retry engine or worker queue."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = http_client
        self._clock = clock
        self._lock = threading.RLock()
        self._health = {"1": _Health(), "2": _Health()}
        self._last_chosen = "2"
        self._bound_orgs: tuple[str, str] | None = None
        self._bound_keys: tuple[str, str] | None = None  # in-memory only, never logged
        self._verified_org_ids: tuple[str, str] | None = None
        self._pair_verified = False

    def _get(self, url: str, key: str) -> dict:
        transport = self._client.get if self._client is not None else httpx.get
        try:
            result = transport(
                url,
                headers={"Authorization": f"Bearer {key}"},
                timeout=10.0,
            )
        except httpx.HTTPError:
            raise gateway.ExperientialError("explabs_probe_transport_error") from None
        if result.status_code != 200:
            raise gateway.ExperientialError(
                f"explabs_probe_http_{result.status_code}",
                status=result.status_code,
            )
        try:
            obj = result.json()
        except ValueError:
            raise gateway.ExperientialError("explabs_probe_invalid_response") from None
        if not isinstance(obj, dict):
            raise gateway.ExperientialError("explabs_probe_invalid_response")
        return obj

    def _probe(self, account: Account, model: str) -> Observation:
        identity = self._get(_API_HOST + "/api/whoami", account.key)
        org_slug = identity.get("org_slug")
        org_id = identity.get("org_id")
        if (not isinstance(org_id, str) or not org_id or
                not isinstance(org_slug, str) or org_slug != account.expected_org):
            raise gateway.ExperientialError("explabs_pool_org_mismatch")
        catalog = self._get(_API_HOST + "/v1/models", account.key).get("data")
        if not isinstance(catalog, list) or model not in {
            row.get("id") for row in catalog if isinstance(row, dict)
            and isinstance(row.get("id"), str)
        }:
            raise gateway.ExperientialError("explabs_pool_model_not_listed")
        key_meta = self._get(_API_HOST + "/api/v1/key", account.key).get("data")
        credit_meta = self._get(_API_HOST + "/api/v1/credits", account.key).get("data")
        if not isinstance(key_meta, dict) or not isinstance(credit_meta, dict):
            raise gateway.ExperientialError("explabs_probe_invalid_response")
        key_cap = _money(key_meta.get("limit"))
        remaining = _money(key_meta.get("limit_remaining"))
        if (key_cap is None or key_cap <= 0 or
                key_cap > account.max_daily_usd + 1e-9 or remaining is None):
            # A local target is NOT a hard spending cap; require the gateway's
            # actual enforced, per-key daily cap and verified remaining budget.
            raise gateway.ExperientialError("explabs_pool_gateway_cap_not_verified")
        total_credits = _money(credit_meta.get("total_credits"))
        total_usage = _money(credit_meta.get("total_usage"))
        credits = (
            total_credits - total_usage
            if total_credits is not None and total_usage is not None else None
        )
        return Observation(org_id, org_slug, model, remaining, credits)

    def _ensure_fresh(self, accounts: tuple[Account, Account], model: str) -> None:
        now = self._clock()
        expected = (accounts[0].expected_org, accounts[1].expected_org)
        current_keys = (accounts[0].key, accounts[1].key)
        if self._bound_keys is not None and not all(
            hmac.compare_digest(old, new)
            for old, new in zip(self._bound_keys, current_keys)
        ):
            raise gateway.ExperientialError("explabs_pool_key_rotation_requires_restart")
        self._bound_keys = current_keys
        if self._bound_orgs is not None and self._bound_orgs != expected:
            # An identity change requires an explicitly new pool object, not
            # silently reusing health or usage from another organization.
            raise gateway.ExperientialError("explabs_pool_identity_changed")
        self._bound_orgs = expected
        for account in accounts:
            state = self._health[account.slot]
            if state.blocked:
                continue
            if now < state.cooldown_until:
                continue
            if (state.observation is not None and
                    state.observation.model == model and
                    now - state.checked_at < _REFRESH_SECONDS):
                continue
            try:
                state.observation = self._probe(account, model)
                state.checked_at = now
            except gateway.ExperientialError as exc:
                state.observation = None
                state.blocked = str(exc)  # sanitized machine code only
        observations = [self._health[a.slot].observation for a in accounts]
        if all(observations):
            if observations[0].org_id == observations[1].org_id:
                for state in self._health.values():
                    state.observation = None
                    state.blocked = "explabs_pool_duplicate_org"
                raise gateway.ExperientialError("explabs_pool_duplicate_org")
            observed_ids = (observations[0].org_id, observations[1].org_id)
            if self._verified_org_ids is not None and self._verified_org_ids != observed_ids:
                raise gateway.ExperientialError("explabs_pool_org_identity_changed")
            self._verified_org_ids = observed_ids
            self._pair_verified = True
        if not self._pair_verified:
            # Both orgs must be independently verified before FIRST dispatch.
            # Later a blocked account can be skipped for distinct NEW requests.
            raise gateway.ExperientialError("explabs_pool_initial_verification_required")

    def _pick(self, accounts: tuple[Account, Account]) -> Account:
        eligible = []
        for a in accounts:
            state = self._health[a.slot]
            obs = state.observation
            if (state.blocked or state.cooldown_until > self._clock() or
                    obs is None or state.inflight >= a.max_inflight):
                continue
            if obs.key_remaining_usd is not None and obs.key_remaining_usd <= 0:
                continue
            # Unverified wallet/free allowance is NOT assumed to be free or
            # unlimited. Gateway key caps remain the authoritative spend fence.
            util = state.inflight / a.max_inflight
            unit_cost = state.unit_cost_per_1k_tokens
            cost_signal = 0.5 if unit_cost is None else min(1.0, max(0.0, unit_cost / 0.01))
            capacity_signal = (
                0.5 if obs.key_remaining_usd is None
                else 1.0 / (1.0 + max(0.0, obs.key_remaining_usd))
            )
            # Prioritize real headroom and present work, then observed price.
            score = 0.55 * util + 0.25 * capacity_signal + 0.20 * cost_signal
            tie = 0 if a.slot != self._last_chosen else 1
            eligible.append((score, tie, a.slot, a))
        if not eligible:
            raise gateway.ExperientialError("explabs_pool_no_eligible_account")
        eligible.sort(key=lambda item: (item[0], item[1], item[2]))
        return eligible[0][3]

    def complete(self, system: str, user: str) -> gateway.Completion:
        """One selection, one dispatch, one result. Never retry or cross-account replay."""
        if not available():
            raise gateway.ExperientialError("explabs_pool_disabled")
        accounts = _configs()
        model = os.environ.get("EXPLABS_MODEL") or gateway.DEFAULT_MODEL
        with self._lock:
            self._ensure_fresh(accounts, model)
            account = self._pick(accounts)
            state = self._health[account.slot]
            state.inflight += 1
            self._last_chosen = account.slot
        try:
            reply = gateway.complete(
                system, user, model=model,
                client=self._client,
                api_key=account.key,
            )
        except gateway.ExperientialError as exc:
            with self._lock:
                state = self._health[account.slot]
                if exc.status == 429 and exc.code == "rate_limit_exceeded":
                    state.cooldown_until = self._clock() + (exc.retry_after or 60)
                else:
                    # Permission, quota, transport and unknown outcomes are held
                    # until an explicit new pool/authorization, not auto retried.
                    state.blocked = str(exc)
            raise
        else:
            with self._lock:
                total_tokens = reply.input_tokens + reply.output_tokens
                if reply.cost_usd is not None and total_tokens > 0:
                    sample = reply.cost_usd * 1000.0 / total_tokens
                    state = self._health[account.slot]
                    previous = state.unit_cost_per_1k_tokens
                    state.unit_cost_per_1k_tokens = (
                        sample if previous is None else 0.8 * previous + 0.2 * sample
                    )
            return replace(reply, account_slot=account.slot)
        finally:
            with self._lock:
                self._health[account.slot].inflight -= 1

    def status(self) -> dict[str, dict]:
        """Redacted in-process diagnostic; no credential or account-id exposure."""
        with self._lock:
            return {
                slot: {
                    "verified": state.observation is not None,
                    "blocked": state.blocked,
                    "inflight": state.inflight,
                    "cooldown": state.cooldown_until > self._clock(),
                    "key_remaining_usd": (
                        state.observation.key_remaining_usd
                        if state.observation is not None else None
                    ),
                    "credits_remaining_usd": (
                        state.observation.credits_remaining_usd
                        if state.observation is not None else None
                    ),
                    "observed_usd_per_1k": state.unit_cost_per_1k_tokens,
                }
                for slot, state in self._health.items()
            }


_POOL = AccountPool()


def complete(system: str, user: str) -> gateway.Completion:
    return _POOL.complete(system, user)
