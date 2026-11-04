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
    key: str  # raw provider key only in legacy direct mode, otherwise scoped local token
    expected_org: str
    max_inflight: int
    max_daily_usd: float
    api_origin: str = _API_HOST  # exact checked local gateway or fixed vendor origin
    shared_gateway: bool = False


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


def _configs() -> tuple[Account, ...]:
    """Return explicitly enabled accounts; disabled orgs are never probed."""
    accounts = []
    for slot, key_name, stem in _SLOTS:
        if os.environ.get(stem + "_ENABLED") != "1":
            continue
        # Operator sets serving verification only after a separate canary
        # and provider billing-policy confirmation. Merely listing a model
        # in /v1/models is not proof of a callable serving lane.
        if os.environ.get(stem + "_SERVING_VERIFIED") != "1":
            raise gateway.ExperientialError("explabs_pool_serving_unverified")
        transport = os.environ.get(stem + "_TRANSPORT", "direct").strip()
        if transport not in {"direct", "shared_gateway"}:
            raise gateway.ExperientialError("explabs_pool_invalid_transport")
        shared_gateway = transport == "shared_gateway"
        org = os.environ.get(stem + "_ORG_SLUG", "").strip()
        if shared_gateway:
            if os.environ.get(key_name, ""):
                # The raw vendor credential belongs only on the gateway host.
                raise gateway.ExperientialError("explabs_pool_provider_key_on_brain_host")
            raw_origin = os.environ.get(stem + "_GATEWAY_ORIGIN", "")
            api_origin = gateway.validated_shared_gateway_origin(raw_origin)
            key = os.environ.get(stem + "_GATEWAY_TOKEN", "").strip()
            if len(key) < 24 or len(key) > 256 or any(c.isspace() for c in key):
                raise gateway.ExperientialError("explabs_pool_invalid_gateway_token")
        else:
            if (os.environ.get(stem + "_GATEWAY_ORIGIN")
                    or os.environ.get(stem + "_GATEWAY_TOKEN")):
                raise gateway.ExperientialError("explabs_pool_gateway_binding_requires_optin")
            api_origin = _API_HOST
            key = os.environ.get(key_name, "")
        if not key or not org:
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
        accounts.append(Account(slot, key, org, cap, max_daily_usd,
                                api_origin, shared_gateway))
    if not accounts:
        raise gateway.ExperientialError("explabs_pool_no_enabled_accounts")
    if len({a.expected_org for a in accounts}) != len(accounts):
        raise gateway.ExperientialError("explabs_pool_requires_distinct_orgs")
    # One gateway has one provider key and one physical RPM state owner.
    # Two distinct organizations must NOT be assigned the same gateway.
    gateway_origins = [a.api_origin for a in accounts if a.shared_gateway]
    if len(gateway_origins) != len(set(gateway_origins)):
        raise gateway.ExperientialError("explabs_pool_duplicate_gateway_owner")
    return tuple(accounts)


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
        self._bound_orgs: tuple[str, ...] | None = None
        self._bound_keys: tuple[str, ...] | None = None  # in-memory only, never logged
        self._verified_org_ids: tuple[str, ...] | None = None
        self._eligible_set_verified = False

    def _get(self, url: str, key: str) -> dict:
        # Shared local gateway metadata must ignore all ambient proxy settings.
        # The direct-vendor compatibility transport remains unchanged.
        # Injected HTTPX clients are test/owner supplied and own their policy.
        kwargs = {"headers": {"Authorization": f"Bearer {key}"}, "timeout": 10.0}
        try:
            if self._client is not None:
                result = self._client.get(url, **kwargs)
            elif httpx.URL(url).host == "127.0.0.1":
                with httpx.Client(trust_env=False, follow_redirects=False) as local:
                    result = local.get(url, **kwargs)
            else:
                result = httpx.get(url, **kwargs)
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

    def _read_spend_cap(self, account: Account) -> float:
        """Verify the upstream daily *charged USD* cap before every dispatch."""
        key_meta = self._get(account.api_origin + "/api/v1/key", account.key).get("data")
        if not isinstance(key_meta, dict):
            raise gateway.ExperientialError("explabs_probe_invalid_response")
        key_cap = _money(key_meta.get("limit"))
        remaining = _money(key_meta.get("limit_remaining"))
        if (key_cap is None or key_cap <= 0 or
                key_cap > account.max_daily_usd + 1e-9 or
                remaining is None or remaining < 0 or remaining > key_cap + 1e-9):
            # Key cap must be enforced by the provider. A local policy alone
            # cannot safely bound charges across processes or hosts.
            raise gateway.ExperientialError("explabs_pool_gateway_cap_not_verified")
        return remaining

    def _probe(self, account: Account, model: str) -> Observation:
        identity = self._get(account.api_origin + "/api/whoami", account.key)
        org_slug = identity.get("org_slug")
        org_id = identity.get("org_id")
        if (not isinstance(org_id, str) or not org_id or
                not isinstance(org_slug, str) or org_slug != account.expected_org):
            raise gateway.ExperientialError("explabs_pool_org_mismatch")
        catalog = self._get(account.api_origin + "/v1/models", account.key).get("data")
        if not isinstance(catalog, list) or model not in {
            row.get("id") for row in catalog if isinstance(row, dict)
            and isinstance(row.get("id"), str)
        }:
            raise gateway.ExperientialError("explabs_pool_model_not_listed")
        remaining = self._read_spend_cap(account)
        credit_meta = self._get(account.api_origin + "/api/v1/credits", account.key).get("data")
        if not isinstance(credit_meta, dict):
            raise gateway.ExperientialError("explabs_probe_invalid_response")
        total_credits = _money(credit_meta.get("total_credits"))
        total_usage = _money(credit_meta.get("total_usage"))
        credits = (
            total_credits - total_usage
            if total_credits is not None and total_usage is not None else None
        )
        return Observation(org_id, org_slug, model, remaining, credits)

    def _ensure_fresh(self, accounts: tuple[Account, ...], model: str) -> None:
        now = self._clock()
        expected = tuple(a.expected_org for a in accounts)
        current_keys = tuple(a.key for a in accounts)
        if self._bound_keys is not None and (
            len(self._bound_keys) != len(current_keys)
            or not all(hmac.compare_digest(old, new)
                       for old, new in zip(self._bound_keys, current_keys))
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
            observed_ids = tuple(obs.org_id for obs in observations)
            if len(set(observed_ids)) != len(observed_ids):
                for account in accounts:
                    state = self._health[account.slot]
                    state.observation = None
                    state.blocked = "explabs_pool_duplicate_org"
                raise gateway.ExperientialError("explabs_pool_duplicate_org")
            if self._verified_org_ids is not None and self._verified_org_ids != observed_ids:
                raise gateway.ExperientialError("explabs_pool_org_identity_changed")
            self._verified_org_ids = observed_ids
            self._eligible_set_verified = True
        if not self._eligible_set_verified:
            # Verify every ENABLED org before first dispatch. Disabled/blocked
            # organizations are never probed and cannot be chosen. Subsequent
            # new requests may use an already verified healthy eligible org.
            raise gateway.ExperientialError("explabs_pool_initial_verification_required")

    def _refresh_candidate_headroom(self, accounts: tuple[Account, ...]) -> list[gateway.ExperientialError]:
        """Read each eligible key's current provider cap before selecting a slot.

        This happens strictly BEFORE any inference dispatch. If one key is
        exhausted or its provider cap no longer satisfies policy, a separate
        eligible key may serve the NEW request. Never retry a dispatched call.
        """
        failures: list[gateway.ExperientialError] = []
        for account in accounts:
            state = self._health[account.slot]
            if (state.blocked or state.observation is None or
                    state.cooldown_until > self._clock() or
                    state.inflight >= account.max_inflight):
                continue
            try:
                remaining = self._read_spend_cap(account)
            except gateway.ExperientialError as exc:
                state.blocked = str(exc)
                state.observation = None
                failures.append(exc)
                continue
            state.observation = replace(
                state.observation, key_remaining_usd=remaining
            )
        return failures

    def _pick(self, accounts: tuple[Account, ...]) -> Account:
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

    def complete(
        self, system: str, user: str, *, max_tokens: int = 1500
    ) -> gateway.Completion:
        """One selection, one dispatch, one result. Never retry or cross-account replay."""
        if not available():
            raise gateway.ExperientialError("explabs_pool_disabled")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
            # Local malformed budget must not quarantine a healthy account.
            raise gateway.ExperientialError("explabs_invalid_max_tokens")
        accounts = _configs()
        model = os.environ.get("EXPLABS_MODEL") or gateway.DEFAULT_MODEL
        with self._lock:
            self._ensure_fresh(accounts, model)
            failures = self._refresh_candidate_headroom(accounts)
            try:
                account = self._pick(accounts)
            except gateway.ExperientialError as exc:
                # Preserve the exact cap failure if every candidate was
                # refused before dispatch; never turn it into a retry.
                if failures:
                    raise failures[0] from None
                raise exc
            state = self._health[account.slot]
            state.inflight += 1
            self._last_chosen = account.slot
        try:
            reply = gateway.complete(
                system, user, model=model,
                client=self._client,
                api_key=account.key,
                max_tokens=max_tokens,
                shared_gateway_origin=(account.api_origin if account.shared_gateway else None),
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
                state = self._health[account.slot]
                # The per-key cap only constrains *platform-funded* spend.
                # If routing unexpectedly changes to BYOK (or usage.cost is
                # absent), the response may already be served and must be
                # attributed, but never admit another request on that slot
                # until a separate billing-path reconciliation is done.
                if reply.is_byok is True:
                    state.blocked = "explabs_unexpected_byok"
                elif reply.cost_usd is None:
                    state.blocked = "explabs_missing_gateway_cost"
                elif reply.is_byok is not False:
                    state.blocked = "explabs_unknown_funding_lane"
                else:
                    total_tokens = reply.input_tokens + reply.output_tokens
                    if total_tokens > 0:
                        sample = reply.cost_usd * 1000.0 / total_tokens
                        previous = state.unit_cost_per_1k_tokens
                        state.unit_cost_per_1k_tokens = (
                            sample if previous is None
                            else 0.8 * previous + 0.2 * sample
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


def complete(system: str, user: str, *, max_tokens: int = 1500) -> gateway.Completion:
    return _POOL.complete(system, user, max_tokens=max_tokens)
