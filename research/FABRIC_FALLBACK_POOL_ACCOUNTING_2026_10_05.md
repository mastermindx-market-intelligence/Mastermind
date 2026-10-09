# Fabric fallback and subscription-pool accounting

Status: tested source candidate; native concurrency and routing are unchanged.

Operation: `fabric-fallback-pool-accounting-20261005-pro-001`.
Protected source/procedure: `7eac3ec252475600147ec9a376b8ca16403ac4c5`.
Mode: user-selected Pro; no platform capacity or compaction inference from that label.

## 1. Outcome and consumer

The Chairman requested maximum useful concurrency, inexpensive fallback when GLM/Alibaba/MiniMax are full, frontier preservation, strong expiry-aware preferences, and correct Cursor/Alibaba/OpenCode accounting. This contribution repairs the existing model-economics input to that path. It does not introduce another router, quota ledger, scheduler, observer, account registry or model-selection authority.

Implemented in the existing catalog and `control_plane/provider_model_economics.py`:

- Explicit public Cursor product-pool families: Grok 4.6/4.7 and Composer 2.5 use `cursor_models`; Cursor Luna 5.6, Terra 5.6 and Sonnet 5.5 use `other_models`.
- Surface-qualified regular/long-context Cursor Luna/Terra prices, plus Sonnet 5.5 and Haiku 4.5 metadata. Haiku has no invented Cursor entitlement or price.
- Eight OpenCode Go valuations for already cataloged models: GLM 5.3/Flash, MiniMax M3, Qwen 3.8 Max/Flash, Grok 4.6/4.7 and Luna 5.6. Different reseller surfaces do not inherit each other's token prices or context-price boundaries.
- OpenCode native quota burn remains measured, not inferred by summing advertised model-specific dollar limits. New Go price records do not register a serving driver or grant access.
- Strict optional-field validation and a fail-closed accessor. Old catalog documents still load; an absent pool family cannot become a guessed independent balance.

The named consumer is the existing Model Router / Capacity / Provider Control integration. It can now distinguish inexpensive fallback token value from the exact product family it would consume. These APIs provide metadata, not authentication, admission, a claim, or permission to use a model.

## 2. Evidence and limits

Test-first baseline for Cursor/fallback metadata: **15 failed, 13 passed**. First repaired economics run: 102 passed. Expanded compatibility run: 233 passed. The subsequent OpenCode source increment first produced **12 failed, 28 deselected**; after implementation the combined seven-module run produced **245 passed**.

Command used:

```text
python3 -m pytest -o addopts='' -q \
  tests/test_fallback_model_pool_accounting.py \
  tests/test_provider_model_economics.py \
  tests/test_gpt6_model_economics.py \
  tests/test_provider_offer_economics.py \
  tests/test_capacity_economics_projection.py \
  tests/test_executive_model_router.py \
  tests/test_subscription_provider_profiles.py --tb=short
```

The new cases discriminate missing source data, exact price bands, disjoint cache categories, malformed optional fields, incompatible units/surfaces, legacy unknown-family behavior, absent Haiku-on-Cursor evidence, unsupported Go cache-write prices and absence of live quota fields. In particular, Go Grok remains at its lower rate at 200,000 context tokens, while the separately retained direct xAI card changes at that boundary. The source tests observe that distinction; they do not prove a provider invoice.

The catalog has 19 models. Existing unrelated model records and original source entries are preserved. Compact JSON serialization is retained. The new loader and catalog must release together: the old strict v1 loader rejects the added field rather than silently ignoring it. This is backward read compatibility, not permission to install the new catalog over an old reader.

Quote scope is deliberately narrow. Base model-token value excludes dynamic team fees, regional uplifts, tool charges, unreviewed Fast modes and paid-overage authorization. Anthropic cache-write cards use the published five-minute price, not the one-hour price. A flat price band does not prove a serving harness accepts unbounded context. Context setting, effort, API format and actual served model still require binding by the existing runtime owner. Dates identify this review's applicability, not model launch dates.

No live provider request, worker dispatch, quota/cap mutation, account change, paid setting, native install, service restart, merge, deployment or measured throughput improvement is claimed. Local source tests do not replace independent review, hosted checks or installed original-parent return proof.

## 3. Findings that change the integration design

### Cursor: two pools and no verified fixed dollar denominator

Cursor documents two separately renewing monthly pools. Its September 25 staff response says included dollar amounts are no longer published as fixed values and can vary. The Chairman's actual current allowance, reset timestamp and remaining percentages were not obtained. Neither $100 nor $400 is seeded into this candidate. A scoped connected-email search returned no matching account evidence. [C1, C2]

The supported team Admin API exposes usage events and spend. `spendCents` is on-demand spend; `overallSpendCents` includes included usage; `monthlyLimitDollars` is a spending control, not an allowance. Cents may be fractional. Usage-event aggregation is hourly, with polling recommended no more than hourly. This is a team API, not proof that an individual/bundled account has that capability. [C3]

Integration recommendation: prefer provider-owned current pool percentages and cycle identity. Retain independently reconstructed token value as an estimate, not a replacement for the provider meter. Conflicting observations should narrow claims and preserve the paid-spend gate; never select a favorable stale denominator. Account-specific API access and authenticated supported UI/export observation remain to be qualified by the existing observer owner. No credential extraction or undocumented session-cookie replay is proposed.

### Alibaba: identify the actual product before applying windows

The current English Personal Token Plan documentation removes the weekly limit from September 22, 2026 and describes monthly credits. It recommends 6-8 concurrent tasks for Pro, but does not promise an immutable account maximum. Model multipliers, temporary off-peak discounts and expiring add-on packs also matter; provider deduction order is not user-selectable merely because a bundle expires sooner. [A1]

The Personal FAQ restricts use to interactive coding/agent tools rather than unattended batch production and says dynamic RPM/TPM limits cannot be increased. The overview and FAQ differ on multiple-device wording. The exact product, edition, subscriber and allowed execution pattern must therefore be reconciled before pooling fleet workers. Do not transfer legacy Coding Plan weekly quotas into Token Plan or infer multi-user rights from a working key. [A2]

These are admission inputs, not a reason to alter existing account configuration from a web page. Current user-account facts remain required. No purchase, upgrade or account restriction was made here.

### OpenCode: multiple model offers are not automatically independent budgets

Go publishes model-specific token valuation and monthly allowances with additional five-hour and weekly constraints. Public model discovery confirms available identifiers, not this account's entitlement or headroom. Use actual deductions and the complete owner-declared window set; do not sum all listed monthly dollar figures as new capacity. The optional `Use balance` setting spills into paid Zen balance, so it is a separate spending gate. [O1, O2]

Protocol is also part of identity: Go lists Responses for Grok/Luna, Chat Completions for GLM, and Messages for MiniMax/Qwen. Actual integration must bind the listed serving ID and protocol, retain the existing conversation identity, and preserve the real client's supported session header. It must not impersonate another client to obtain eligibility. The new catalog records quote provenance; it deliberately does not create those drivers. [O1]

Candidate expansion should qualify Kimi/DeepSeek/MiMo and newer Luna options using bounded real task evidence, exact model revisions and data-use constraints, not automatically enroll every advertised model. Contributor/training-enabled or geographically restricted offers require a compatible data classification. New-model discovery cannot auto-expand the admitted routing set.

### GLM and MiniMax: configured caps are not vendor guarantees

Z.ai describes plan-dependent dynamic concurrency and higher off-peak capacity, not a universal numeric maximum. Its July 30 credit-system announcement preserves legacy plan distinctions. The balancer must bind the actual enrolled generation and observations; API keys and physical hosts are not independent subscriptions. [G1, G2]

MiniMax's earlier Token Plan page had quota/concurrency guidance, but the current URL redirected to an M Plan shell without extractable quota details. That is insufficient to establish a new fixed maximum. The existing MiniMax observer's actual account/window facts remain necessary. No cached marketing number was written into live configuration. [M1]

## 4. Target routing policy, to integrate through the existing owners

This section records the requested behavior and acceptance contract. It is not installed routing policy and does not supersede protected source by being in this draft.

### Feasibility first, economics second

For each ready bounded task, preserve the canonical identity and effect state. The existing TaskFit owner establishes the real minimum capability, context, tool/data permissions, impact and independent-review requirement. A business-important but mechanically simple task need not become frontier work. A hard task does not become easy because an inexpensive pool is nearly empty or nearly resetting.

Intersect current account, product, model, provider, host, root/ancestor, reviewer and all quota-window constraints. Capacity is not the sum of labels in a model menu. Two processes using one subscription and two keys for one account can consume the same constraint. A free slot is not a replenished daily/weekly/monthly allowance. A forecast reset is not present spendable balance.

Only then rank the lawful candidates. The preferred order for easy work is qualified GLM Flash/Qwen Flash/MiniMax and comparable economical offers, then qualified Luna/Haiku, then Sonnet/Terra when their whole-task economics or capability makes sense. Preserve Grok/Cursor frontier capacity by default. Medium/hard bounded work and orchestration can use qualified full GLM, Grok/Cursor, Sonnet/Terra or stronger admitted routes as appropriate. These are preferences, not claims that every named model is suitable for every task.

Cross-product selection must preserve the actual harness/provider identity: Cursor is a delivery product with multiple model families, not synonymous with Grok. Sonnet/Luna/Terra through Cursor can consume a different pool from Grok. The same underlying model through OpenCode, Alibaba or a direct provider can have different economics, windows, tooling and permissions.

### Expiring surplus can override preference, not capability or authority

The Chairman specifically wants strong use-before-reset priority, even when it promotes an otherwise overpowered model for easy work. The integration should support that explicit preference. An eligible frontier model may do easy work when its allowance would otherwise expire unused; an incapable model must not receive hard work simply to consume its balance.

Distinguish true expiring monthly/week-long allowance from rolling-window recovery. A five-hour throttle reopening does not imply the monthly pool should be depleted. Account for already reserved completions, pending difficult work, observed task durations, review/repair/return costs and uncertainty before declaring surplus. A task that cannot finish before expiry does not have the same benefit as one that can. Do not run synthetic work merely to burn credits.

The existing quota-economics owner already owns the underlying arithmetic and forecast/reserve machinery. Its integration should attach an explicit reason such as `expiring_eligible_surplus` and preserve the source observations. Do not add a competing local scoring ledger. Where current protected Router tiers encode strict first-tier selection, the owner must reconcile that rule with this newly requested preference in the existing amendment; this source patch does not silently bypass it.

### Raise effective concurrency, not merely a number

There is no defensible single fleet-wide unlimited cap. The effective concurrent wave is the intersection of current admission ceilings, real provider capacity, physical-host resources and conserved root/reviewer closure. Use the actual native broker admission result, not an optimistic plan display. The #1248 source evidence is a concrete warning: its synthetic full-GLM plan advertised 30 while unchanged admission stopped at 15. Those are fixture results, not this account's live measured cap. [I1]

The next native step is to reconcile exact installed configuration and active leases, then lift only unnecessarily restrictive local ceilings under the approved owner. Provider throttles, paid budgets and physical-resource guards stay enforced. A controlled increase can use useful admitted tasks, measured latency/error/queue pressure and rollback, with prompt backoff on overload. Stagger starts and account for memory-heavy context/cache warmup. Adding fleet hosts expands physical capacity, not a subscription's allowance.

Avoid creating all leaves at once just because many slots exist: retain capacity for independent review, repair and final return; advance dependency-ready work while unrelated checks run. Report ready/running/waiting separately from total starts. Preserve the existing root lifecycle instead of nesting unlimited orchestration trees.

### Fallback and fairness

A known pre-start busy/throttled/exhausted result may select another already admitted candidate. An auth/permission denial must not be evaded through another account or model. A timeout after possible provider or filesystem effects retains its original carrier until reconciled; it cannot safely launch a substitute writer. Respect provider Retry-After and existing retry ownership.

Within equally useful admissible work, protect against a dominant root starving other roots. Favor cache/session locality when it reduces accepted-result cost, but not enough to defeat deadlines or strand an eligible pool. Optimize expected cost and latency of a verified result, including retries, failed output, independent review, repair and parent aggregation, rather than prompt price alone. Qualified vision/tool support remains a hard requirement; delegation of a visual subtask still consumes the same conserved closure budget.

## 5. Owner-preserving integration sequence and acceptance

| Existing owner | Remaining work | Evidence required |
| --- | --- | --- |
| Model catalog / this candidate | Source acceptance and paired reader/catalog release | Exact-head checks/review; preserved old metadata; strict unknown-family refusal |
| Macro #7103/#7116 and current Provider Control observers | Bind product generation, account, family, native units, all windows and current balances | Fresh authenticated owner observations; repeated deductions and reset transitions; no additive shared-pool inflation |
| Macro #8255/#8311 | Consume actual reset observations and strong eligible-surplus preference | Stale/future/missing facts never restore current capacity; paid balance remains separate |
| Mastermind #1248 and incumbent native installer | Reconcile real caps/leases, classify per task and use correct capacity plan | Plan/claim agreement; exact installed before/after hashes; preserved active work |
| Mastermind #1247 / Capacity and Runtime | Atomic multi-constraint claim plus host/root/reviewer conservation | Competing roots cannot double reserve the same shared bucket; claim-time revalidation |
| Existing native driver and parent-return owners | Activate qualified fallback surfaces and verify served model/format/return | Actual process/model/product, quota delta, reviewed result and original-parent consumption |

No ownership is transferred by this table. #1041 is not assumed to be an accepted hierarchy rollout dependency. #1228's known installer holds are not cleared by metadata tests. #7116's refused unpublished repair is not recreated or republished through this operation.

Minimum release scenarios: all primary economical pools saturated with an easy task; only a suitable economical fallback available; frontier needed for hard work; a near-expiry frontier surplus doing easy work without violating hard reserve; one shared pool reached through multiple models/hosts; stale or inconsistent balance; monthly boundary versus rolling recovery; provider rejection before start versus timeout after a possible effect; disabled paid spill; successful original-parent consumption. Each needs negative assertions as well as a happy path. The existing owner suites should implement the runtime scenarios; this catalog suite is not their substitute.

## 6. Effects, current frontier and recovery

The source workspace was acquired through `mmx-workspace` under this operation and exact base. All edits were confined to the catalog, its module/tests and this evidence report. The first publication-status precheck returned a valid current-operation status: dirty, local base head, no remote branch, not yet published. That is not a failed or refused write.

A direct read of the live native kit's picker, broker configuration references and config filenames was platform-blocked before dispatch. It was not replayed through another command, account, tool, host or worker. That live-read/dependent installation lane remains blocked. Source-only edits in this registered workspace are independent. No active worker or uncertain modifying effect was created.

Do not redo the original blocked native read, #7116's refused publication, or #1248's account-linking-gated review via another carrier. Preserve the incumbent candidates and their evidence. No autonomous wake or background agent has been claimed.

The immediate next source action is exact-head review/checks and publication of this candidate; the next operational action is original-owner reconciliation of the native read gate and real account observations, followed by the normal qualified installation and acceptance path. `MISSION_COMPLETE=false` until the live concurrency/fallback/reset behavior and original-parent result are proven. Source publication alone cannot close the Chairman's end-to-end request.

## Sources and provenance

All public pages below were read during the 2026-10-05 UTC source review. Public facts do not establish this user's current entitlement.

- C1: Cursor Models & Pricing, https://cursor.com/docs/models-and-pricing
- C2: Cursor staff response, September 25, 2026, post 25, https://forum.cursor.com/t/bug-help-other-models-hits-100-while-usage-export-at-published-api-rates-only-reconstructs-65-how-to-reconcile-the-meter/172012/25 . User replies are not treated as authoritative allowance values.
- C3: Cursor team Admin API, https://cursor.com/docs/account/teams/admin-api
- C4: Cursor Luna, https://cursor.com/docs/models/gpt-5-6-luna ; Terra, https://cursor.com/docs/models/gpt-5-6-terra ; Sonnet, https://cursor.com/docs/models/claude-sonnet-5-5
- H1: Anthropic Sonnet, https://platform.claude.com/docs/en/models/sonnet-5-5/overview ; Haiku, https://platform.claude.com/docs/en/models/haiku-4-5/overview ; native configuration, https://code.claude.com/docs/en/model-config
- A1: Alibaba Personal Token Plan, https://www.alibabacloud.com/help/en/model-studio/token-plan-personal-overview
- A2: Alibaba Personal Token Plan FAQ, https://www.alibabacloud.com/help/en/model-studio/token-plan-personal-faq
- O1: OpenCode Go, https://opencode.ai/docs/go/
- O2: Public model identifiers, https://opencode.ai/zen/go/v1/models
- G1: Z.ai usage policy, https://docs.z.ai/devpack/usage-policy
- G2: Z.ai plan-generation notice, https://docs.z.ai/devpack/notice/usage-revision
- M1: MiniMax current redirected plan surface, https://www.minimax.io/m-plan ; prior Token Plan URL https://platform.minimax.io/subscribe/token-plan
- I1: Mastermind #1248, `c2168fb0656688c11c386e83b26d0dc778bb4be4`, https://github.com/mastermindx-market-intelligence/Mastermind/pull/1248
- I2: Mastermind #1247, `0b76d83cb49ccfadaf749e9442531b00dbae0de2`, https://github.com/mastermindx-market-intelligence/Mastermind/pull/1247
- I3: Macro #7116, published records `4d7ddfd24a5f02b91375c074efdefc3b77a04c1a`, https://github.com/mastermindx-market-intelligence/macro/pull/7116
- I4: Macro #8311, observed-reset merge `0504e3bad7739a61124ad8f4274b5d5cd282be62`, https://github.com/mastermindx-market-intelligence/macro/pull/8311
