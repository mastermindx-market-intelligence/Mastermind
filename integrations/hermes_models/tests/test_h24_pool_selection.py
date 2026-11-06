"""Offline H24-05 acceptance: synthetic owner facts, never live eligibility.

Positive ModelArk/MiniMax fixtures describe the typed seam that an authenticated
owner would need to supply. They do NOT assert those routes exist at the base.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal as D, localcontext
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from integrations.hermes_models.contract import MODELARK_CONTRACT, PROVIDERS, ROLES
from integrations.hermes_models.pool_selection import (
    Auth, Binding, Budget, Candidate, Capability, Capacity, Debit, Demand,
    Effect, EffectEvidence, Failure, Health, ModelHealth, ModelQuota, Owner,
    PoolFacts, PoolHealth, PoolSelectionError, ProviderFacts, Quote, RealmHealth,
    SourcePin, Stamp, Suitability, SURFACE, Unit, Window,
    candidate_ref, demand_digest, project_model_pool,
)


NOW = 1_793_966_400
FLASH = "byteplus-modelark.glm-5.3-flash"
DEEPSEEK = "byteplus-modelark.deepseek-v4.1-flash"
GLM = "zai.glm-5.3"
MINIMAX = "minimax.attended"
CURSOR = "cursor-pool"


def stamp(owner, source, digit):
    return Stamp(SourcePin(owner, "owner-issuer", source, digit * 64), NOW - 10, NOW + 120)


def fixture(role="secretary", effect="read_only"):
    """A coherent synthetic frozen snapshot with two usable secretary models."""
    demand = Demand("request-1", "job-1", role, 1000, 500, 2,
                    ("text", "tools"), D("0.20"), effect)
    digest = demand_digest(demand)
    router = stamp(Owner.ROUTER, "router", "1")
    capacity_stamp = stamp(Owner.CAPACITY, "capacity", "2")
    provider_stamp = stamp(Owner.PROVIDER, "provider", "3")
    economics = stamp(Owner.ECONOMICS, "economics", "4")
    rate_source = SourcePin(Owner.ECONOMICS, "owner-issuer", "rate-card", "f" * 64)
    executive = stamp(Owner.EXECUTIVE, "budget", "5")
    effect_stamp = stamp(Owner.EXECUTIVE, "effect", "6")
    ark_binding = Binding("byteplus", MODELARK_CONTRACT["realm_id"], "commercial-pool", "a" * 64)
    candidates = []
    capabilities = []
    realms = []
    pools = []
    models = []
    quotas = []
    windows = []
    quotes = []
    bindings = set()
    for rank, provider_id in enumerate(ROLES[role].provider_ids):
        spec = PROVIDERS[provider_id]
        binding = ark_binding if provider_id.startswith("byteplus-modelark.") else Binding(
            spec.hermes_name, spec.hermes_name + "-realm", spec.hermes_name + "-pool", "b" * 64)
        if binding not in bindings:
            bindings.add(binding)
            realms.append(RealmHealth(binding.issuer_id, binding.realm_id, Auth.READY))
            pools.append(PoolHealth(binding, Health.READY))
            # A single daily credit window shared by both ModelArk models.
            windows.append(Window(binding.pool_id + ".daily", binding, None, Unit.CREDITS,
                                  NOW - 3600, NOW + 3600, D("100"), D("20"), D("10")))
        alias = spec.router_alias or provider_id
        candidates.append(Candidate(
            "candidate-" + str(rank), alias, provider_id, spec.served_model, SURFACE,
            binding, "host-1", "lane-1", "worker-" + str(rank), "c" * 64,
            "d" * 64, "e" * 64, True, Health.READY, True, True, rank))
        capabilities.append(Capability(economics, alias, provider_id, spec.served_model,
                                       SURFACE, 16000, 4000, ("text", "tools", "vision", "computer-use")))
        models.append(ModelHealth(binding, spec.served_model, Health.READY, None))
        request_resource = provider_id + ".requests"
        token_resource = provider_id + ".tokens"
        windows.extend((
            Window(request_resource, binding, spec.served_model, Unit.REQUESTS,
                   NOW - 30, NOW + 30, D("100"), D("2"), D("3")),
            Window(token_resource, binding, spec.served_model, Unit.TOKENS,
                   NOW - 30, NOW + 30, D("200000"), D("5000"), D("1000")),
        ))
        required = (binding.pool_id + ".daily", request_resource, token_resource)
        quotas.append(ModelQuota(binding, spec.served_model, required, True))
        quotes.append(Quote(economics, "quote-" + str(rank), rate_source, binding,
                            alias, provider_id, spec.served_model, SURFACE, digest, 0, 16000,
                            "USD", D("0.10"), (Debit(required[0], Unit.CREDITS, D("5")),
                                                 Debit(required[1], Unit.REQUESTS, D("2")),
                                                 Debit(required[2], Unit.TOKENS, D("3000")))))
    facts = PoolFacts(
        Suitability(router, digest, "tier-1", tuple(c.model_alias for c in candidates)),
        Capacity(capacity_stamp, digest, router.pin, "tier-1", tuple(candidates)),
        ProviderFacts(provider_stamp, tuple(realms), tuple(pools), tuple(models), tuple(quotas), tuple(windows)),
        tuple(capabilities), tuple(quotes),
        Budget(executive, "root-budget", demand.job_id, digest, 10, 1, 1,
               20000, 1000, 2000, D("1.00"), D("0.20"), D("0.30")),
        EffectEvidence(effect_stamp, digest, Effect.PRE_SEND, Failure.NONE, None, None, None, None))
    pins = tuple(s.pin for s in (router, capacity_stamp, provider_stamp, economics, executive, effect_stamp)) + (rate_source,)
    return demand, facts, pins


def changed_demand(demand, facts, **changes):
    demand = replace(demand, **changes)
    digest = demand_digest(demand)
    return demand, replace(facts,
        suitability=replace(facts.suitability, demand_digest=digest),
        capacity=replace(facts.capacity, demand_digest=digest),
        budget=replace(facts.budget, job_id=demand.job_id, demand_digest=digest),
        effect=replace(facts.effect, demand_digest=digest),
        quotes=tuple(replace(q, demand_digest=digest) for q in facts.quotes))


def candidate_change(facts, index=0, **changes):
    candidates = list(facts.capacity.candidates)
    candidates[index] = replace(candidates[index], **changes)
    return replace(facts, capacity=replace(facts.capacity, candidates=tuple(candidates)))


def quote_change(facts, index=0, **changes):
    quotes = list(facts.quotes)
    quotes[index] = replace(quotes[index], **changes)
    return replace(facts, quotes=tuple(quotes))


def cap_change(facts, index=0, **changes):
    capabilities = list(facts.capabilities)
    capabilities[index] = replace(capabilities[index], **changes)
    return replace(facts, capabilities=tuple(capabilities))


def window_change(facts, resource_id, **changes):
    windows = tuple(replace(w, **changes) if w.resource_id == resource_id else w
                    for w in facts.provider.windows)
    return replace(facts, provider=replace(facts.provider, windows=windows))


def evidence(facts, *, state=Effect.READ_ONLY_NO_EFFECT, failure=Failure.OUTAGE,
             provider_id=FLASH, response_status=503, served_model=None, proof="7" * 64):
    return replace(facts, effect=replace(facts.effect, state=state, failure=failure,
        attempted_provider_id=provider_id, response_status=response_status,
        served_model=served_model, no_effect_receipt=proof))


class H24PoolSelectionTests(unittest.TestCase):
    def setUp(self):
        self.demand, self.facts, self.pins = fixture()

    def project(self, facts=None, demand=None, pins=None, now=NOW):
        return project_model_pool(demand or self.demand, facts or self.facts,
                                  current_sources=self.pins if pins is None else pins, now=now)

    def reasons(self, decision):
        return set(decision.reasons).union(*(e.reasons for e in decision.exclusions))

    def assertRejected(self, facts, reason, *, provider_id=FLASH, demand=None, pins=None):
        result = self.project(facts, demand, pins)
        self.assertIn(reason, self.reasons(result))
        self.assertNotIn(provider_id, [s.provider_id for s in
                         ((result.selected,) if result.selected else ()) + result.alternatives])
        return result

    def test_role_policy_glm_modelark_minimax_and_disabled_cursor(self):
        for role, primary in (("meta-ceo", GLM), ("secretary", FLASH),
                              ("watcher", FLASH), ("implementation-subagent", FLASH),
                              ("vision", MINIMAX), ("computer-use", MINIMAX)):
            with self.subTest(role=role):
                demand, facts, pins = fixture(role)
                result = self.project(facts, demand, pins)
                self.assertEqual(result.selected.provider_id, primary)
                self.assertIn("PROFILE_PROVIDER_DISABLED", self.reasons(result))
                self.assertNotIn(CURSOR, [x.provider_id for x in result.alternatives])

    def test_ranked_alternatives_and_quote_provenance(self):
        result = self.project()
        self.assertEqual(result.status, "PROJECTED")
        self.assertEqual(result.selected.provider_id, FLASH)
        self.assertEqual([x.provider_id for x in result.alternatives], [DEEPSEEK])
        self.assertEqual(result.selected.quote.cash_upper_bound, "0.10")
        self.assertEqual(result.selected.quote.source.revision, "4" * 64)
        self.assertEqual(result.selected.quote.rate_card_revision, "f" * 64)
        self.assertEqual(result.expires_at, NOW + 30)
        self.assertIn("CAPACITY_OWNER_ORDER_PRESERVED", result.trace)

    def test_owner_order_wins_without_new_economic_ranking(self):
        facts = candidate_change(self.facts, 0, owner_rank=10)
        facts = quote_change(facts, 0, cash_upper_bound=D("0.01"))
        result = self.project(facts)
        self.assertEqual(result.selected.provider_id, DEEPSEEK)
        self.assertEqual(result.alternatives[0].provider_id, FLASH)

    def test_later_suitability_tier_cannot_replace_unavailable_first(self):
        facts = replace(self.facts, suitability=replace(self.facts.suitability, model_aliases=(FLASH,)))
        facts = candidate_change(facts, available=False)
        result = self.project(facts)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("OUTSIDE_FIRST_SUITABILITY_TIER", self.reasons(result))

    def test_missing_router_commercial_alias_does_not_become_eligible(self):
        facts = replace(self.facts, suitability=replace(self.facts.suitability,
                                                       model_aliases=("glm.paid.sealed-input",)))
        result = self.project(facts)
        self.assertIsNone(result.selected)
        self.assertIn("OUTSIDE_FIRST_SUITABILITY_TIER", self.reasons(result))

    def test_minimax_needs_current_owner_policy_qualification(self):
        demand, facts, pins = fixture("vision")
        facts = candidate_change(facts, policy_qualified=False)
        self.assertRejected(facts, "OWNER_POLICY_NOT_QUALIFIED", provider_id=MINIMAX, demand=demand, pins=pins)

    def test_family_name_cannot_substitute_exact_glm_wire_identity(self):
        demand, facts, pins = fixture("meta-ceo")
        facts = candidate_change(facts, served_model="glm-5.3-flash")
        self.assertRejected(facts, "MODEL_CONTRACT_MISMATCH", provider_id=GLM, demand=demand, pins=pins)

    def test_foreign_role_cannot_borrow_healthy_candidate(self):
        facts = candidate_change(self.facts, provider_id=GLM, served_model="glm-5.3")
        self.assertRejected(facts, "ROLE_PROVIDER_NOT_ALLOWED", provider_id=GLM)

    def test_personal_modelark_realm_is_refused(self):
        binding = replace(self.facts.capacity.candidates[0].binding, realm_id="byteplus-personal")
        self.assertRejected(candidate_change(self.facts, binding=binding), "MODELARK_COMMERCIAL_BINDING_REQUIRED")

    def test_unknown_readiness_is_not_positive_quota(self):
        self.assertRejected(candidate_change(self.facts, readiness=Health.UNKNOWN), "CAPACITY_NOT_READY")

    def test_unqualified_source_is_not_positive_capacity(self):
        self.assertRejected(candidate_change(self.facts, source_qualified=False), "CAPACITY_SOURCE_UNQUALIFIED")

    def test_pre_send_outage_can_propose_alternative_for_modifying_work(self):
        demand, facts = changed_demand(self.demand, self.facts, effect="side_effecting")
        result = self.project(candidate_change(facts, available=False), demand)
        self.assertEqual(result.selected.provider_id, DEEPSEEK)
        self.assertIn("PRE_SEND_PROJECTION", result.reasons)

    def test_read_only_no_effect_outage_fallthrough(self):
        result = self.project(evidence(self.facts))
        self.assertEqual(result.selected.provider_id, DEEPSEEK)
        self.assertIn("READ_ONLY_NO_EFFECT_FALLBACK", result.reasons)

    def test_network_loss_with_unknown_effect_never_falls_through(self):
        for effect in ("read_only", "side_effecting"):
            with self.subTest(effect=effect):
                demand, facts = changed_demand(self.demand, self.facts, effect=effect)
                result = self.project(evidence(facts, state=Effect.UNKNOWN, response_status=None), demand)
                self.assertEqual(result.status, "BLOCKED")
                self.assertIsNone(result.selected)
                self.assertEqual(result.alternatives, ())
                self.assertIn("PRIOR_EFFECT_FORBIDS_SELECTION", result.reasons)

    def test_modifying_send_cannot_use_read_only_no_effect_label(self):
        demand, facts = changed_demand(self.demand, self.facts, effect="side_effecting")
        result = self.project(evidence(facts), demand)
        self.assertIn("READ_ONLY_NO_EFFECT_PROOF_REQUIRED", result.reasons)
        self.assertIsNone(result.selected)

    def test_no_effect_proof_cannot_be_omitted(self):
        self.assertRejected(evidence(self.facts, proof=None), "READ_ONLY_NO_EFFECT_PROOF_REQUIRED")

    def test_completed_effect_is_not_new_placement_permission(self):
        self.assertRejected(evidence(self.facts, state=Effect.OBSERVED), "PRIOR_EFFECT_FORBIDS_SELECTION")

    def test_pre_send_with_response_is_incoherent(self):
        self.assertRejected(evidence(self.facts, state=Effect.PRE_SEND), "INCOHERENT_PRE_SEND_EVIDENCE")

    def test_wrong_or_missing_model_response_is_terminal(self):
        for served in ("GLM-5-3-FLASH-260828", "glm-5.3", None):
            with self.subTest(served=served):
                self.assertRejected(evidence(self.facts, served_model=served, response_status=200),
                                    "SERVED_MODEL_MISMATCH")

    def test_declared_model_mismatch_is_not_outage(self):
        self.assertRejected(evidence(self.facts, failure=Failure.MODEL_MISMATCH), "SERVED_MODEL_MISMATCH")

    def test_auth_response_does_not_authorize_failover(self):
        for status in (401, 403):
            with self.subTest(status=status):
                self.assertRejected(evidence(self.facts, failure=Failure.AUTH_DENIED,
                                             response_status=status), "AUTH_DENIAL_NOT_FAILOVER")

    def test_401_denies_all_models_and_pools_in_exact_realm(self):
        provider = self.facts.provider
        realm = replace(provider.realms[0], auth=Auth.DENIED)
        facts = replace(self.facts, provider=replace(provider, realms=(realm,) + provider.realms[1:]))
        result = self.project(facts)
        self.assertIsNone(result.selected)
        denied = [e for e in result.exclusions if "REALM_AUTH_DENIED" in e.reasons]
        self.assertEqual(len(denied), 2)
        # A second pool cannot turn the same issuer/realm denial into model health.
        binding = replace(facts.capacity.candidates[1].binding, pool_id="other-pool")
        result = self.project(candidate_change(facts, 1, binding=binding))
        self.assertEqual(sum("REALM_AUTH_DENIED" in e.reasons for e in result.exclusions), 2)

    def test_429_is_model_scoped_and_does_not_refill_shared_credit(self):
        models = self.facts.provider.models
        cooling = replace(models[0], health=Health.RATE_LIMITED, cooldown_until=NOW + 60)
        facts = replace(self.facts, provider=replace(self.facts.provider, models=(cooling,) + models[1:]))
        result = self.project(facts)
        self.assertEqual(result.selected.provider_id, DEEPSEEK)
        self.assertIn("MODEL_COOLDOWN", self.reasons(result))
        daily = next(d for d in result.selected.quote.debits if d.unit == "credits")
        self.assertEqual(D(daily.remaining_before), D("70"))
        self.assertEqual(D(daily.remaining_after), D("65"))

    def test_429_read_only_proof_allows_proposal_but_never_reservation(self):
        result = self.project(evidence(self.facts, failure=Failure.RATE_LIMITED, response_status=429))
        self.assertEqual(result.selected.provider_id, DEEPSEEK)
        self.assertFalse(result.to_dict()["capacity_claimed"])

    def test_expired_cooldown_requires_fresh_positive_owner_health(self):
        models = self.facts.provider.models
        cooling = replace(models[0], health=Health.RATE_LIMITED, cooldown_until=NOW - 1)
        facts = replace(self.facts, provider=replace(self.facts.provider, models=(cooling,) + models[1:]))
        self.assertRejected(facts, "MODEL_HEALTH_REQUIRES_REFRESH")

    def test_pool_outage_blocks_all_its_models(self):
        pools = self.facts.provider.pools
        facts = replace(self.facts, provider=replace(self.facts.provider,
                        pools=(replace(pools[0], health=Health.UNAVAILABLE),) + pools[1:]))
        result = self.project(facts)
        self.assertIsNone(result.selected)
        self.assertIn("POOL_NOT_HEALTHY", self.reasons(result))

    def test_daily_credit_cap_dominates_other_available_horizons(self):
        daily = self.facts.provider.windows[0]
        facts = window_change(self.facts, daily.resource_id, limit=D("34.999999999"))
        result = self.project(facts)
        self.assertIsNone(result.selected)
        self.assertIn("QUOTA_HARD_CAP_EXCEEDED", self.reasons(result))

    def test_daily_credit_exact_boundary_and_shared_identity(self):
        daily = self.facts.provider.windows[0]
        result = self.project(window_change(self.facts, daily.resource_id, limit=D("35")))
        self.assertEqual(result.status, "PROJECTED")
        first = next(d for d in result.selected.quote.debits if d.unit == "credits")
        second = next(d for d in result.alternatives[0].quote.debits if d.unit == "credits")
        self.assertEqual(first.resource_ref, second.resource_ref)
        self.assertEqual(D(first.remaining_after), D(0))

    def test_partial_quota_is_not_available(self):
        quotas = self.facts.provider.quotas
        facts = replace(self.facts, provider=replace(self.facts.provider,
                        quotas=(replace(quotas[0], complete=False),) + quotas[1:]))
        self.assertRejected(facts, "QUOTA_INCOMPLETE")

    def test_missing_quota_horizon_is_not_zero_cost(self):
        provider = replace(self.facts.provider, windows=self.facts.provider.windows[1:])
        result = self.project(replace(self.facts, provider=provider))
        self.assertIsNone(result.selected)
        self.assertIn("QUOTA_HORIZON_MISSING", self.reasons(result))

    def test_omitted_daily_horizon_detected_even_with_complete_flag(self):
        quotas = self.facts.provider.quotas
        facts = replace(self.facts, provider=replace(self.facts.provider,
            quotas=(replace(quotas[0], required_resources=quotas[0].required_resources[1:]),) + quotas[1:]))
        facts = quote_change(facts, debits=facts.quotes[0].debits[1:])
        self.assertRejected(facts, "QUOTA_APPLICABLE_SET_MISMATCH")

    def test_stale_quota_window_never_locally_rolls_over(self):
        resource = self.facts.provider.windows[0].resource_id
        self.assertRejected(window_change(self.facts, resource, resets_at=NOW), "QUOTA_HORIZON_STALE_OR_FUTURE")

    def test_pre_window_observation_cannot_become_post_reset_balance(self):
        resource = self.facts.provider.windows[0].resource_id
        self.assertRejected(window_change(self.facts, resource, starts_at=NOW - 5),
                            "QUOTA_HORIZON_STALE_OR_FUTURE")

    def test_ready_observation_before_cooldown_expiry_needs_refresh(self):
        models = self.facts.provider.models
        cooling = replace(models[0], health=Health.READY, cooldown_until=NOW - 5)
        facts = replace(self.facts, provider=replace(self.facts.provider, models=(cooling,) + models[1:]))
        self.assertRejected(facts, "MODEL_HEALTH_REQUIRES_REFRESH")

    def test_capacity_cannot_mix_equal_revision_router_origins(self):
        for changes in ({"issuer_id": "router-b"}, {"source_id": "other-router-source"}):
            with self.subTest(changes=changes):
                source = replace(self.facts.suitability.stamp.pin, **changes)
                route = replace(self.facts.suitability, stamp=replace(self.facts.suitability.stamp, pin=source))
                pins = (source,) + self.pins[1:]
                self.assertRejected(replace(self.facts, suitability=route),
                                    "CAPACITY_ROUTER_SOURCE_MISMATCH", pins=pins)

    def test_model_specific_quota_does_not_borrow_other_model_headroom(self):
        windows = self.facts.provider.windows
        token = next(w for w in windows if w.resource_id == FLASH + ".tokens")
        self.assertRejected(window_change(self.facts, token.resource_id, limit=D("8999")), "QUOTA_HARD_CAP_EXCEEDED")

    def test_quota_debit_must_cover_full_request_token_budget(self):
        for index, value in ((1, D("1")), (2, D("2999"))):
            with self.subTest(index=index):
                debits = list(self.facts.quotes[0].debits)
                debits[index] = replace(debits[index], upper_bound=value)
                self.assertRejected(quote_change(self.facts, debits=tuple(debits)), "QUOTA_DEBIT_UNDERSTATED")

    def test_competing_job_request_and_token_reservations(self):
        for changes, reason in (({"requests_reserved": 8}, "JOB_REQUEST_BUDGET_EXHAUSTED"),
                                ({"tokens_reserved": 16001}, "JOB_TOKEN_BUDGET_EXHAUSTED")):
            with self.subTest(reason=reason):
                facts = replace(self.facts, budget=replace(self.facts.budget, **changes))
                self.assertRejected(facts, reason)

    def test_competing_job_cash_reservations(self):
        facts = replace(self.facts, budget=replace(self.facts.budget, cash_reserved=D("0.71")))
        result = self.project(facts)
        self.assertIsNone(result.selected)
        self.assertIn("JOB_CASH_BUDGET_EXHAUSTED", self.reasons(result))

    def test_request_cash_ceiling_is_separate_from_pool_quota(self):
        demand, facts = changed_demand(self.demand, self.facts, cash_ceiling_usd=D("0.099999999"))
        result = self.project(facts, demand)
        self.assertIsNone(result.selected)
        self.assertIn("REQUEST_CASH_CEILING", self.reasons(result))

    def test_capabilities_context_output_and_tools_are_separate(self):
        for changes, reason in (({"context_window_tokens": 1499}, "MODEL_CONTEXT_OR_OUTPUT_EXCEEDED"),
                                ({"max_output_tokens": 499}, "MODEL_CONTEXT_OR_OUTPUT_EXCEEDED"),
                                ({"context_window_tokens": None}, "EFFECTIVE_LIMITS_UNKNOWN"),
                                ({"capabilities": ("text",)}, "REQUIRED_CAPABILITY_MISSING")):
            with self.subTest(reason=reason, changes=changes):
                self.assertRejected(cap_change(self.facts, **changes), reason)

    def test_prices_from_other_surface_are_not_hermes_quotes(self):
        self.assertRejected(quote_change(self.facts, surface="opencode_go"), "EXACT_QUOTE_MISSING")

    def test_quote_must_match_demand_and_pricing_context_band(self):
        self.assertRejected(quote_change(self.facts, demand_digest="0" * 64), "QUOTE_IDENTITY_OR_DEMAND_MISMATCH")
        self.assertRejected(quote_change(self.facts, context_min=1001), "QUOTE_CONTEXT_BAND_MISMATCH")

    def test_quote_and_capability_source_expiry(self):
        for method, items in ((quote_change, self.facts.quotes), (cap_change, self.facts.capabilities)):
            with self.subTest(method=method.__name__):
                self.assertRejected(method(self.facts, stamp=replace(items[0].stamp, expires_at=NOW)),
                                    "SOURCE_STALE_OR_FUTURE")

    def test_stale_or_future_common_owner_facts_block_whole_projection(self):
        for name in ("suitability", "capacity", "provider", "budget", "effect"):
            for observation, expiry in ((NOW - 30, NOW), (NOW + 1, NOW + 20)):
                with self.subTest(name=name, observation=observation):
                    fact = getattr(self.facts, name)
                    fact = replace(fact, stamp=replace(fact.stamp, observed_at=observation, expires_at=expiry))
                    self.assertRejected(replace(self.facts, **{name: fact}), "SOURCE_STALE_OR_FUTURE")

    def test_current_source_movement_invalidates_all_affected_facts(self):
        for i, pin in enumerate(self.pins):
            with self.subTest(source=pin.source_id):
                pins = list(self.pins)
                pins[i] = replace(pin, revision="0" * 64)
                result = self.project(pins=tuple(pins))
                self.assertIsNone(result.selected)
                self.assertIn("SOURCE_MOVED", self.reasons(result))

    def test_missing_current_source_and_mixed_source_issuer(self):
        self.assertRejected(self.facts, "CURRENT_SOURCE_MISSING", pins=self.pins[1:])
        pins = (replace(self.pins[0], issuer_id="different-issuer"),) + self.pins[1:]
        self.assertRejected(self.facts, "SOURCE_ISSUER_MISMATCH", pins=pins)

    def test_owner_stamp_type_cannot_be_promoted(self):
        route = self.facts.suitability
        stamp_ = replace(route.stamp, pin=replace(route.stamp.pin, owner=Owner.CAPACITY))
        self.assertRejected(replace(self.facts, suitability=replace(route, stamp=stamp_)), "WRONG_SOURCE_OWNER")

    def test_capacity_must_join_exact_router_revision_and_tier(self):
        moved = replace(self.facts.capacity.suitability_source, revision="0" * 64)
        for changes, reason in (({"suitability_source": moved}, "CAPACITY_ROUTER_SOURCE_MISMATCH"),
                                ({"first_tier_id": "tier-2"}, "CAPACITY_FIRST_TIER_MISMATCH")):
            with self.subTest(reason=reason):
                self.assertRejected(replace(self.facts, capacity=replace(self.facts.capacity, **changes)), reason)

    def test_demand_and_job_binding_cannot_mix_other_work(self):
        self.assertRejected(replace(self.facts, budget=replace(self.facts.budget, job_id="other-job")),
                            "JOB_BUDGET_IDENTITY_MISMATCH")
        self.assertRejected(replace(self.facts, effect=replace(self.facts.effect, demand_digest="0" * 64)),
                            "DEMAND_BINDING_MISMATCH")

    def test_pool_issuer_realm_generation_and_model_joins_are_exact(self):
        binding = self.facts.capacity.candidates[0].binding
        for changes in ({"issuer_id": "other-issuer"}, {"realm_id": "other-realm"},
                        {"pool_id": "other-pool"}, {"generation": "0" * 64}):
            with self.subTest(changes=changes):
                self.assertRejected(candidate_change(self.facts, binding=replace(binding, **changes)),
                                    "EXACT_QUOTE_MISSING")
        window = self.facts.provider.windows[1]
        self.assertRejected(window_change(self.facts, window.resource_id,
                                         served_model=PROVIDERS[DEEPSEEK].served_model), "QUOTA_BINDING_MISMATCH")

    def test_duplicate_native_resource_and_ambiguous_rank_are_rejected(self):
        invalid = (
            replace(self.facts, provider=replace(self.facts.provider,
                    windows=self.facts.provider.windows + (self.facts.provider.windows[0],))),
            candidate_change(self.facts, 1, owner_rank=0),
            replace(self.facts, quotes=self.facts.quotes + (self.facts.quotes[0],)),
        )
        for facts in invalid:
            with self.subTest(facts=type(facts).__name__), self.assertRaises(PoolSelectionError):
                self.project(facts)

    def test_bad_money_never_coerces_to_available(self):
        for value in (D("NaN"), D("Infinity"), D("-0.01"), D("1E-10"), D("0E+999999"), 0.1, True):
            with self.subTest(value=str(value)), self.assertRaises(PoolSelectionError):
                self.project(quote_change(self.facts, cash_upper_bound=value))

    def test_booleans_and_mutable_sequences_are_rejected(self):
        with self.assertRaises(PoolSelectionError):
            self.project(demand=replace(self.demand, max_requests=True))
        with self.assertRaises(PoolSelectionError):
            self.project(replace(self.facts, quotes=list(self.facts.quotes)))
        with self.assertRaises(PoolSelectionError):
            self.project(now=True)

    def test_unknown_fields_and_non_typed_facts_are_rejected(self):
        with self.assertRaises(TypeError):
            Binding("x", "y", "z", "0" * 64, api_key="not-a-real-key")
        with self.assertRaises(PoolSelectionError):
            self.project(facts={"api_key": "not-a-real-key"})

    def test_secret_canaries_absent_from_json_repr_and_errors(self):
        secret = "mmx-secret-canary-do-not-copy"
        facts = candidate_change(self.facts, candidate_id=secret, host_id=secret, worker_id=secret)
        facts = quote_change(facts, quote_id=secret)
        facts = replace(facts, budget=replace(facts.budget, budget_id=secret))
        result = self.project(facts)
        self.assertNotIn(secret, json.dumps(result.to_dict(), sort_keys=True))
        self.assertNotIn(secret, repr(facts))
        self.assertNotIn(secret, repr(facts.capacity.candidates[0]))
        bad = candidate_change(facts, host_id="Bearer " + secret)
        with self.assertRaises(PoolSelectionError) as error:
            self.project(bad)
        self.assertNotIn(secret, str(error.exception))

    def test_source_label_canaries_are_hashed_in_provenance(self):
        secret = "source-secret-canary"
        new_pin = replace(self.facts.provider.stamp.pin, issuer_id=secret, source_id=secret)
        provider = replace(self.facts.provider, stamp=replace(self.facts.provider.stamp, pin=new_pin))
        pins = tuple(new_pin if p.owner is Owner.PROVIDER else p for p in self.pins)
        result = self.project(replace(self.facts, provider=provider), pins=pins)
        self.assertEqual(result.status, "PROJECTED")
        self.assertNotIn(secret, json.dumps(result.to_dict()))

    def test_no_credentials_environment_network_or_files_read(self):
        with patch("builtins.open", side_effect=AssertionError("file I/O")), \
             patch("socket.socket", side_effect=AssertionError("network I/O")), \
             patch("os.getenv", side_effect=AssertionError("environment I/O")), \
             patch("pathlib.Path.read_text", side_effect=AssertionError("file I/O")):
            self.assertEqual(self.project().status, "PROJECTED")

    def test_parallel_readers_are_stable_and_do_not_reserve(self):
        before = repr(self.facts.provider.windows), self.facts.budget, self.facts.provider
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.project().to_dict(), range(32)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(before, (repr(self.facts.provider.windows), self.facts.budget, self.facts.provider))
        for field in ("selection_is_commitment", "capacity_claimed", "live_admission", "provider_connected"):
            self.assertFalse(results[0][field])
        self.assertTrue(results[0]["claim_time_revalidation_required"])
        self.assertTrue(results[0]["incumbent_reservation_required"])

    def test_decimal_precision_cannot_round_over_budget_into_acceptance(self):
        daily = self.facts.provider.windows[0]
        facts = window_change(self.facts, daily.resource_id, limit=D("34.999999999"))
        expected = self.project(facts)
        for precision in (1, 2, 6, 28, 80):
            with self.subTest(precision=precision), localcontext() as context:
                context.prec = precision
                self.assertEqual(self.project(facts), expected)
                self.assertIsNone(self.project(facts).selected)

    def test_input_and_output_are_immutable_and_export_detached(self):
        with self.assertRaises(FrozenInstanceError):
            self.facts.capacity.candidates[0].available = False
        result = self.project()
        exported = result.to_dict()
        exported["selected"]["provider_id"] = "tampered"
        self.assertEqual(result.selected.provider_id, FLASH)

    def test_empty_capacity_is_truthful_blocked_result(self):
        facts = replace(self.facts, capacity=replace(self.facts.capacity, candidates=()))
        result = self.project(facts)
        self.assertEqual(result.reasons, ("NO_QUALIFIED_CANDIDATE",))
        self.assertIsNone(result.expires_at)

    def test_candidate_join_key_changes_on_source_and_placement_movement(self):
        c = self.facts.capacity.candidates[0]
        original = candidate_ref(c)
        for changes in ({"source_digest": "0" * 64}, {"worker_id": "other-worker"},
                        {"execution_profile_digest": "0" * 64}, {"capability_policy_digest": "0" * 64}):
            with self.subTest(changes=changes):
                self.assertNotEqual(candidate_ref(replace(c, **changes)), original)

    def test_rate_card_source_cannot_change_under_same_quote_stamp(self):
        moved = replace(self.facts.quotes[0].rate_card_source, revision="0" * 64)
        self.assertRejected(quote_change(self.facts, rate_card_source=moved), "SOURCE_MOVED")

    def test_rate_card_source_issuer_must_match_current_origin(self):
        moved = replace(self.facts.quotes[0].rate_card_source, issuer_id="another-issuer")
        self.assertRejected(quote_change(self.facts, rate_card_source=moved), "SOURCE_ISSUER_MISMATCH")

    def test_debit_units_cannot_be_reinterpreted_by_resource_id(self):
        debits = list(self.facts.quotes[0].debits)
        debits[0] = replace(debits[0], unit=Unit.USD)
        self.assertRejected(quote_change(self.facts, debits=tuple(debits)), "QUOTA_DEBIT_UNIT_MISMATCH")

    def test_fresh_post_cooldown_ready_observation_qualifies(self):
        models = self.facts.provider.models
        recovered = replace(models[0], health=Health.READY, cooldown_until=NOW - 10)
        facts = replace(self.facts, provider=replace(self.facts.provider, models=(recovered,) + models[1:]))
        self.assertEqual(self.project(facts).selected.provider_id, FLASH)


if __name__ == "__main__":
    unittest.main()
