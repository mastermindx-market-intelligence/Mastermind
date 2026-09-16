# Executive Subscription Capacity Economics Law

**Authority:** standing Chairman source law for subscription-capacity economics and provider/model scarcity routing.  
**Status:** canonical policy proposal until merged; merging this document does not arm any provider, worker, account, credential, route, or purchase.  
**Scope:** how already-eligible provider/model capacity is economically ranked after capability, policy, security, continuity, and runtime admission gates pass.  
**Precedence:** this law is more specific than generic "cheapest" or "least-scarce" wording for fixed-fee subscription capacity. It does not override Executive OS lifecycle, Model Router suitability, Shared AI Provider Control quota truth, RuntimeBinding/carrier law, provider terms, or source-writer custody.

## 1. Outcome

Mastermind should turn fixed-fee subscriptions into useful accepted work instead of letting valuable capacity expire, while never degrading quality, violating provider policy, inventing quota, duplicating control planes, or burning scarce capacity merely to make a utilization graph look full.

The objective is **accepted useful capability per marginal dollar and per scarce capacity unit**, not raw requests, raw tokens, percentage utilization, or theoretical quota value.

## 2. Existing authority remains canonical

No new router, quota ledger, retry engine, lifecycle, account registry, or cost database is introduced.

- **Model Router** owns model/task suitability and required quality/capability.
- **Shared AI Provider Control** owns fresh entitlement, health, quota/headroom, reset, cooling, concurrency, and provider-policy observations.
- **Executive OS** owns Job/Attempt/Worker lifecycle, claims, budgets, and effect state.
- **RuntimeBinding / carrier law** owns exact started-session continuity and effect-unknown restrictions.
- `control_plane/provider_model_economics.py` and its reviewed catalog own static model capability/rate-card declarations where present; they never become quota truth.

A missing or stale fact stays unknown. Economic pressure never converts UNKNOWN into AVAILABLE.

## 3. Hard eligibility gates come before economics

A route is economically rankable only after all required non-economic gates are satisfied for that mission, including as applicable:

1. provider usage policy / rights and confidentiality;
2. reviewed harness and adapter compatibility;
3. model capability and task-fit floor;
4. required quality/reliability floor for the mission risk;
5. credential/enrollment and fresh capacity evidence;
6. exact workspace/session/carrier continuity;
7. effect-state safety and no duplicate START/EFFECT_UNKNOWN operation;
8. required independence for review;
9. current budget and organizational authority.

No amount of expiring quota makes an ineligible route eligible.

## 4. Capacity follows provider-native depletion identity

Capacity ranking MUST preserve the finest provider-owned allocation unit that actually depletes independently. UI labels, advertised API-dollar equivalents, model menus, or an account-average percentage do not determine the ledger shape by themselves.

Valid provider shapes can include:

- model-scoped balances/windows that genuinely deplete independently;
- shared account/workspace windows with different model-specific debit multipliers or rate functions;
- shared credits across several models;
- concurrency pools plus one or more usage windows;
- provider-specific combinations of those resources.

When the provider exposes genuinely model-specific resources, reason over those model-scoped resources and never average them away. When the provider exposes a shared resource, **do not split that shared resource into fictional per-model wallets** merely because documentation presents per-model equivalent limits or request estimates.

For a shared resource with model-dependent consumption, each eligible model option should bind to the SAME canonical resource identity while carrying its own reviewed native debit/cost function. Switching models does not refill shared capacity unless fresh provider evidence proves a distinct ledger.

A useful resource identity is therefore closer to:

`entitlement × native resource/window × scope × depletion/debit function × headroom × reset/expiry × concurrency/health`

not universally `account × model`.

Capacity evidence precedence is fail-closed. Authenticated/native quota observations and the reviewed provider contract establish what is actually depleted. Public plan tables and model-equivalent marketing rows may explain rates or consumption functions but MUST NOT manufacture separate balances. If current provider surfaces disagree about whether a resource is shared or independent, rank only from the intersection that is proven and mark the disputed dimension UNKNOWN until reconciled.

## 5. Fixed-fee capacity has a shadow cost

Already-paid subscription capacity has near-zero immediate cash cost but a real opportunity cost. Among equally eligible routes, ranking MUST consider:

- marginal cash spend now;
- probability of an accepted result for this task class;
- repair/review burden and latency;
- remaining included headroom;
- time until reset/expiry;
- model/provider scarcity across the whole portfolio;
- availability of economically equivalent capacity elsewhere;
- continuity cost of moving or restarting work;
- independence value for review.

Ranking MUST preserve a **Pareto/lexicographic** decision boundary rather than hiding unlike economic dimensions inside one universal weighted score. First remove a route only when current admitted evidence shows it is strictly dominated on the decisive economic dimensions for this mission (no better on any decisive dimension and strictly worse on at least one). When real trade-offs remain, apply a documented lexicographic ordering appropriate to the mission/risk class.

A bounded scalar may be used only inside one already-frozen lexicographic stage or as a display aid; it MUST NOT override a stronger stage, silently trade away a hard reserve, or recreate universal provider precedence. **Static provider preference is a deterministic tie-break only after the admitted quality/economic dimensions are materially tied, unless a typed non-economic hard constraint explicitly elevates it.** No component may fabricate provider capacity or treat nominal API-dollar equivalence as fungible cash.

## 6. Expiring-capacity harvest rule

After hard gates and quality floors pass, prefer useful work on already-paid capacity that is both sufficiently capable and likely to expire unused, before opening incremental pay-as-you-go spend or consuming a materially scarcer equivalent route.

This is **not** a "burn quota at all costs" rule. Do not manufacture low-value work, widen scope, run redundant agents, lower the quality bar, or add review debt solely to consume capacity.

When two included routes are materially equivalent for the accepted outcome, prefer the route with the higher avoidable-expiry risk and lower portfolio opportunity cost.

For shared provider windows, expiry pressure applies to the shared resource. Model choice inside that resource is then an efficiency/suitability decision using the model-specific debit function; it is not evidence that another model has a separate expiring wallet.

## 7. Scarcity-preservation rule

Preserve capacity that is uniquely valuable for tasks other routes cannot reliably perform. A broadly capable premium/frontier lane should not absorb routine work merely because it is available.

Likewise, aggregator capacity should normally be preserved for diversification, overflow, resilience, independent review, or imminent shared-resource expiry when Mastermind already owns a much larger direct fixed-fee pool for the same model family. Whether that aggregator capacity is model-scoped or shared MUST come from provider truth, not assumption.

The inverse is also true: a large direct subscription that is safely eligible and materially underused SHOULD absorb suitable steady-state work before equivalent metered spend elsewhere.

## 8. Direct subscription vs aggregator law

Treat diversified aggregators and direct provider memberships as different economic products:

- **Aggregator subscription:** breadth, optionality, provider/model diversification, overflow, independent comparison/review, and cheap access to many model choices whose quota may be shared, model-scoped, or mixed according to provider-native semantics.
- **Direct subscription:** concentrated workhorse capacity, predictable continuity, higher same-model throughput/concurrency, and provider-native capabilities.

Do not choose one category universally. Route by the actual mission and current capacity facts.

A shared aggregator window has additional portfolio opportunity cost: spending it on a model family for which Mastermind owns abundant direct capacity can crowd out other model choices available only or most cheaply through that aggregator. That opportunity cost may justify preferring the direct pool when both routes meet the same quality floor.

Buy or upgrade a direct plan when observed accepted-work demand for that model family repeatedly exceeds existing economical capacity, or when provider-native continuity/capability has material value that the aggregator cannot supply.

Buy an additional aggregator seat/account only for a legitimate provider-supported member/workspace use that complies with the provider's current terms. **Never create, maintain, pool, or rotate accounts to circumvent usage limits, access restrictions, billing obligations, promotions, suspensions, or provider policy.**

## 9. Purchase-scaling evidence

Do not scale a subscription because its advertised theoretical token or API-dollar allowance looks large.

A purchase or upgrade case should use existing telemetry/evidence to show, for the relevant model/task cohort:

- accepted useful work that would otherwise spill to a more expensive/scarcer route;
- observed native burn and reset behavior;
- quality/repair/review performance;
- concurrency or continuity pressure;
- expected avoided marginal spend or unlocked throughput;
- provider-policy eligibility for the intended usage.

Prefer at least two representative reset/billing observations when time allows. A short-lived surge may justify a bounded exception, but should be stated as such rather than projected as steady-state demand.

## 10. Task-class allocation

Capacity does not receive work solely because it is cheap. Model Router first establishes what task classes a model can reliably own from current evaluation evidence.

Examples of independently evaluable cohorts include:

- mechanical edits / fixtures / tests;
- routine implementation;
- standard multi-file implementation/refactor;
- debugging;
- long-context repository work;
- research/synthesis;
- multimodal/computer-use work;
- independent technical review;
- principal-level architecture/judgment.

Promote a model into a broader cohort only from attributable accepted-result evidence. Do not infer authority from model marketing, context length, benchmark claims, or unused quota.

## 11. Continuity beats micro-optimization after START

Pre-START placement may choose the best eligible capacity under current law. After START, exact carrier/session and effect-state law wins over small economic improvements.

Do not restart, migrate, rotate provider/account/model, or replay a modifying operation merely because another route has more headroom. `EFFECT_UNKNOWN` blocks economic failover until canonically reconciled.

## 12. Provider-specific application belongs in current facts, not this law

Provider model lists, prices, quota numbers, debit multipliers, reset schedules, plan names, promotions, terms, and supported clients change. Keep dated provider-specific findings in reviewed catalogs/research/Provider Control and refresh them before decisions.

This law must remain valid when OpenCode, MiniMax, OpenAI, Anthropic, GLM, Alibaba, xAI, Cursor, or another provider changes its plans.

## 13. Required economic routing receipt

For a meaningful capacity choice where more than one eligible avenue exists, the existing routing/placement evidence should be able to recover:

```text
TASK_CLASS
QUALITY_FLOOR / REQUIRED_CAPABILITIES
ELIGIBLE_ROUTES_CONSIDERED
CHOSEN_PROVIDER_MODEL_SURFACE
NATIVE_RESOURCE_IDENTITIES_CONSUMED
CAPACITY_EVIDENCE_FRESHNESS
SHARED_VS_MODEL_SCOPED_SEMANTICS
MODEL_DEBIT / COST EVIDENCE (when applicable)
RESET_OR_EXPIRY_PRESSURE (known | unknown)
MARGINAL_CASH_CLASS
PORTFOLIO_SCARCITY_REASON
ORDERING_STAGE / DOMINANCE_REASON
STATIC_PROVIDER_PREFERENCE_ROLE (hard_constraint | tie_break | not_used)
WHY_THIS_CAPACITY
WHY_NOT_MORE_SCARCE_OR_METERED_ROUTE
POLICY / RIGHTS GATE
CONTINUITY / EFFECT STATE
```

This is explanatory evidence, not a second lifecycle or quota ledger.

## 14. Learning loop

Measure economics on **accepted outcomes**, not provider turns. Reuse existing telemetry owners to attribute when available:

- provider/model/surface and task cohort;
- native before/after burn observation;
- accepted vs rejected result;
- repairs and reviewer cost;
- elapsed latency/concurrency pressure;
- avoided metered spend estimate where a reviewed rate exists;
- failure class and escalation route.

For shared resources, attribute model-specific debit against the shared resource rather than fabricating a model balance. Corrections/retractions must update the existing evidence path rather than double-counting history.

Use these observations to improve Model Router suitability and Capacity ranking. Do not let an LLM summary become quota authority or self-authorize purchases.

## 15. Default principle

> **Pass policy, safety, capability, quality, continuity, and admission gates first. Then use the lowest-marginal-cost / least-scarce eligible route, preserving the provider's real depletion identity and harvesting useful expiring fixed-fee capacity without sacrificing accepted-result quality. Preserve uniquely scarce capacity, exploit large legitimate underused direct pools for steady work, use aggregators for breadth/overflow/independence, and scale subscriptions only from observed accepted-work demand.**