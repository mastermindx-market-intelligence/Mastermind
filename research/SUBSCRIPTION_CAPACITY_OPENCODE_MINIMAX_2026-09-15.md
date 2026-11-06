# OpenCode Go + MiniMax subscription capacity application — 2026-09-15

## Mission

Apply `docs/EXECUTIVE_SUBSCRIPTION_CAPACITY_ECONOMICS_LAW.md` to two visibly underused fixed-fee avenues without inventing a new router, quota ledger, worker lifecycle, account pool, or provider permission.

This is current research only, **not routing authority**. No consumer may size capacity, choose a route, authorize a purchase, or satisfy `capacity_known` from this memo. Any routing decision must re-enter the canonical Model Router / Shared AI Provider Control / Capacity owners with current accepted evidence. This memo does not arm a provider, approve a purchase, merge a quarantine-release PR, or satisfy a provider usage-policy gate.

Original branch base: Mastermind `8e25bb32601ef5f40a689da6d6f24149e79e31fa`. Reconciled current protected Mastermind during the quota-semantics correction: `e1f752a58df8f874efa12e30957d911627a0c4f8`.

### Evidence status for changing provider/account facts

This memo intentionally separates architecture from fast-changing quantitative facts. **Any provider price, allowance, promotion, concurrency number, model menu, account-utilization percentage, or reset/headroom observation that is not bound below to an immutable source commit or a secret-safe dated Provider Control receipt is `UNVERIFIED_FOR_ROUTING`.** It may motivate a research cohort, but it MUST NOT size capacity, choose a route, authorize a purchase, or satisfy `capacity_known`. Current allocation must consume fresh evidence from the existing Provider Control/offer owners. Public URLs remain discovery pointers, not frozen receipts.

## 1. OpenCode Go — current facts and the important quota-semantics correction

OpenCode's current Go documentation states:

- plan price: $10/month;
- only one member per workspace can subscribe;
- current model list spans Grok 4.6, GPT 5.6 Luna, GLM 5.3/5.3 Flash/5.2/5.1, Kimi K3/K2.7 Code/K2.6, MiniMax M3/M2.7, Qwen 3.8/3.7/3.6 variants, DeepSeek V4 variants, MiMo, Hy, Muse and LongCat;
- the public table gives each model a monthly dollar-equivalent limit plus model-specific token prices;
- the page states five-hour = 20%, weekly = 50%, and monthly = 100% of the listed monthly equivalent;
- Codex and Claude Code are listed as validated clients when session identity is preserved;
- current Go traffic is expected to look like coding-agent traffic and carry stable session identity;
- Go usage limits may change.

Current public source: https://opencode.ai/docs/go/

### Do not interpret those table rows as independent wallets

A deeper current-source reconciliation changes the correct economic model.

At upstream OpenCode commit `e03db9bc6908f75c9334d8aa997deeaac81c0298`:

- `packages/console/app/src/routes/zen/go/v1/usage.ts` authenticates one workspace/user and returns ONE `rolling`, ONE `weekly`, and ONE `monthly` usage percentage/reset triplet from `LiteTable.rollingUsage`, `weeklyUsage`, and `monthlyUsage`;
- `packages/console/app/src/routes/workspace/[id]/go/lite-section.tsx` builds usage detail from that same shared window, groups historical usage by model and recorded `costMultiplier`, and computes each row's `quotaCost` from cost × multiplier;
- `packages/console/app/src/lib/lite-usage.ts` defines `getModelQuotaLimit(limit, multiplier) = limit / multiplier`.

Current upstream sources:

- https://github.com/anomalyco/opencode/blob/dev/packages/console/app/src/routes/zen/go/v1/usage.ts
- https://github.com/anomalyco/opencode/blob/dev/packages/console/app/src/routes/workspace/%5Bid%5D/go/lite-section.tsx
- https://github.com/anomalyco/opencode/blob/dev/packages/console/app/src/lib/lite-usage.ts

Macro #7143 independently reached the same architectural conclusion in `research/OPENCODE_GO_DYNAMIC_OFFERS_AND_MODEL_DISCOVERY_2026-09-14.md`: the account API is the source of current usage; advertised model-equivalent allowances are not independent balances; the shared subscription ledger applies model cost multipliers; changing models does not refill account usage.

**Routing consequence:** represent Go as shared account/workspace five-hour + weekly + monthly native resources with model-specific debit/rate functions. The public per-model $15/$30/$60 rows are useful model-equivalent allowance/rate evidence, but they MUST NOT become dozens of fictional independent wallets. A model switch changes how efficiently the shared resource is consumed; it does not create fresh quota.

If a later reviewed provider contract exposes genuinely independent model ledgers, Provider Control may version the resource semantics then. Until that proof exists, shared-window truth wins and any disputed dimension fails closed.

OpenCode Terms effective 2026-08-15 prohibit creating/maintaining/using accounts in bulk or using multiple accounts to circumvent usage limits, access restrictions, billing obligations, promotions, suspensions, or other policies.

Current source: https://opencode.ai/legal/terms-of-service

### Chairman-observed account state

`UNVERIFIED_FOR_ROUTING`: the qualitative dashboard observation that motivated this study was not captured in this artifact with timestamped percentages, reset timestamps, account-scope identity, or an immutable snapshot digest. It therefore does **not** establish current Go utilization or `capacity_known`. Before any allocation decision, Provider Control must obtain a fresh authenticated account-shared rolling/weekly/monthly observation through the existing owner.

The architectural opportunity-cost finding does not depend on that missing snapshot: because the Go windows are shared, spending them on a model family for which Mastermind has abundant eligible direct capacity can crowd out differentiated model choices available through the same Go resource. Whether Luna or any other specific model should be avoided on a particular turn remains a current Model Router + Provider Control + Capacity decision.

## 2. OpenCode routing decision

Do **not** scale additional accounts for the purpose of multiplying one operator's limits. That conflicts with current OpenCode terms and the existing Mastermind `usage_policy_satisfied` gate.

Treat every currently legitimate Go subscription as a diversified model-access portfolio backed by shared native usage windows:

1. Provider Control owns the shared rolling/weekly/monthly headroom and reset evidence.
2. Model Router owns whether a particular Go model is good enough for the task.
3. The model-economics/offer owner supplies each model's current rate/debit multiplier and time/context/promotion bands.
4. Capacity ranks only models that pass those gates, using expected accepted-result value per shared quota debit plus portfolio opportunity cost.
5. Do not make Luna the default Go worker merely because a generic fast-engineering alias prefers Luna elsewhere.
6. When direct OpenAI included capacity is healthy, spending shared Go capacity on Luna normally has higher opportunity cost than using Go for a differentiated model that also meets the quality floor.
7. When direct MiniMax Token Plan capacity is healthy, the same logic usually favors direct MiniMax for sustained M3/M2.7 work and preserves shared Go allowance for breadth, overflow or independent comparison.
8. A cheaper debit rate is not sufficient on its own; accepted-result quality and repair burden must be measured by task cohort.

### Near-term Go evaluation priority

Evaluate differentiated candidates against real bounded cohorts and measure both accepted-result quality and shared-quota debit. Current candidates include:

- `DeepSeek V4.1 Flash` — a time-limited promotion was visible during research, but its exact multiplier/value/expiry is `UNVERIFIED_FOR_ROUTING` in this artifact; refresh it through the existing offer owner before using it economically;
- `GLM-5.3-Flash` — low published token rates and a high model-equivalent allowance; useful fast-lane candidate;
- `Qwen3.7 Plus` / `Qwen3.8 Flash` — candidates for routine/standard coding and research after evaluation;
- `Kimi K2.7 Code` — coding-specific candidate;
- `DeepSeek V4 Flash` / `MiMo V2.5` / `Hy3` — potentially quota-efficient bounded-worker candidates;
- `Grok 4.6`, `Qwen3.8 Max`, `Kimi K3`, `GLM-5.3`, `DeepSeek V4 Pro` — useful where their quality or independence justifies their higher shared-quota debit / lower model-equivalent allowance;
- `GPT 5.6 Luna` — use when Luna is actually the best eligible route after considering direct OpenAI capacity, continuity, quality and the opportunity cost of the shared Go window.

The exact cohort map remains Model Router evidence, not this memo.

## 3. OpenCode implementation state inside Mastermind

Protected source currently keeps the OpenCode Go Codex realm in `CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY`; no worker binding is authorized from that candidate registry.

Macro #7143 already owns the Go public offer + authenticated usage observation path. Its usage parser correctly emits the Go resource as `scope="account_shared"` with rolling/five-hour, weekly, and monthly percentage/reset rows. Its public catalog parser keeps model rates and model-equivalent allowance facts separate from entitlement truth. Do not fork either responsibility.

The broader OpenCode composition remains `PARTIAL / BUILT_NOT_PROVEN / PRODUCTION-INERT`: source/synthetic tests prove substantial request/session/effect-safety behavior, but the complete governed production worker route and accepted-result consumption path are not yet proven.

Existing ownership is correct and must be preserved:

- Model Router — suitability;
- Shared AI Provider Control / Macro #7103 + #7143 — account quota/headroom/reset/health and offer observations;
- existing model-economics owner — model-specific debit/rate conversion;
- Capacity Fabric + Executive OS — allocation, claim-time revalidation and lifecycle;
- provider-home owner — credentials;
- existing OpenCode transport kernel — effect-safe request custody only.

Do not add another OpenCode-specific router, account ledger, or quota store.

## 4. MiniMax — current external facts

MiniMax's public Token Plan and model pages market tiered M3-family subscription capacity, bounded concurrent-agent usage, common coding-client integration, long-context/agentic capabilities, multimodal understanding, and a separate pay-as-you-go API offering.

**All changing MiniMax allowances, concurrency counts, subscription prices, promotions, model availability, context-dependent PAYG rates, and cache rates are `UNVERIFIED_FOR_ROUTING` in this artifact.** The research pass observed conflicting rounded/promotional price presentations and did not store an immutable provider-page snapshot or digest, so those numbers have been deliberately removed from the decision-bearing memo rather than pretending that a live URL is a reproducible receipt. Before routing, sizing, or purchasing, the existing Provider Control/offer owner must capture a secret-safe dated observation (UTC observation time, source URL/endpoint or immutable source id, exact observed values, and receipt/snapshot digest).

Discovery pointers:

- https://platform.minimax.io/subscribe/token-plan
- https://www.minimax.io/models/text/m3
- https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise

Provider benchmark/marketing claims remain research inputs only and must not substitute for Mastermind task-cohort evaluation or current quota truth.

## 5. Why MiniMax is underused inside Mastermind

The protected source shows an admission problem, not an obvious model-capability problem.

`config/subscription_provider_profiles.v1.json` currently defines `minimax-token-plan` with MiniMax M3 for routine/hard/fast/subagent classes but keeps:

- `autonomous_allowed: false`;
- `interactive_only: true`;
- `unattended_background_allowed: false`;
- `production_backend_allowed: false`;
- enrollment/capacity and usage-policy gates.

`config/subscription_harness_bindings.v1.json` currently has:

- MiniMax Claude-compatible binding: `BUILT_NOT_PROVEN`, autonomous false;
- MiniMax OpenAI-compatible binding: `SPEC_ONLY`, autonomous false.

Therefore the Fabric cannot legitimately treat the large Token Plan as ordinary unattended worker capacity today.

### Existing work must be extended, not rebuilt

Open draft PR #665 already advances a MiniMax Codex Responses lane. It proposes:

- `minimax-token-plan.codex-responses` using `codex-cli` / Responses;
- MiniMax realm promotion from candidate to reviewed transport registry;
- `BUILT_NOT_PROVEN`, `autonomous_allowed: false`;
- a kit-side Codex 0.154.0 `MiniMax-M3` PONG canary.

PR #665 explicitly does **not** prove governed production execution. Its current parked comment records blockers including in-repo proof placement, collection receipt cleanup, the kit slot mapping pointing at the wrong MiniMax binding, and activation-fact/generation-receipt composition that could un-arm the pool.

Do not open a duplicate MiniMax adapter lane. Resume/repair #665 only under its incumbent source custody and current sequencing.

Macro #7103 already contains the MiniMax remaining-quota acquisition/parser path. That path exposes model-scoped five-hour/weekly provider-allocation rows from MiniMax's remaining-quota endpoint. It remains Provider Control evidence, not a worker activation.

## 6. MiniMax target role after governed admission

If governed canaries and cohort evaluation meet the quality floor, MiniMax M3 should become a **bulk standard/elevated worker avenue**, not an exotic fallback.

High-value cohorts to evaluate first:

1. multi-file implementation and refactors where 1M context reduces repeated discovery;
2. long-context repository archaeology followed by bounded implementation;
3. debugging with substantial logs/code/context;
4. test generation, repair loops and mechanical follow-through under a frozen design;
5. substantial research/synthesis that benefits from large context;
6. independent code/research review when cross-provider independence is valuable;
7. multimodal UI/browser/computer-use work **only when the admitted harness actually exposes and proves those tools**;
8. long-running agentic execution where the provider plan and Mastermind runtime both explicitly permit the mode.

Do not assign M3 principal/CEO authority merely because the model is strong or abundant. Architecture, product thesis and consequential ambiguity remain with the lawful principal.

### M2.7

MiniMax direct plans also expose M2.7. Treat it as a candidate economical fast/standard lane, not as automatically equivalent to M3. It needs its own task-cohort evaluation and route record before broad use.

## 7. Direct MiniMax vs OpenCode MiniMax

For sustained MiniMax-family work, the direct Token Plan is the intended concentrated-workhorse candidate **only after fresh Provider Control evidence proves current entitlement, headroom, concurrency, and usage-policy eligibility**. OpenCode remains valuable access to MiniMax for diversification/overflow/review, but Go M3 consumes the same shared Go native windows used by Go's other models.

If a fresh Provider Control observation shows the direct MiniMax pool eligible with headroom, test routine M3-family demand against that direct pool first under the ordering law; absent that observation the pool ranks from UNKNOWN. Spending shared Go allowance on M3 has a portfolio opportunity cost because it reduces the same Go resource available for Qwen/Kimi/GLM/DeepSeek/Grok choices.

OpenCode's economic advantage is **breadth under a shared fixed-fee resource with model-dependent debit economics**, not a sum of independent model wallets.

## 8. Purchase decision

### OpenCode

Current decision: **do not add more accounts to increase pooled capacity.** First maximize lawful useful work on existing legitimate subscriptions through shared-window-aware model routing and evaluation. Revisit purchasing only for provider-supported distinct member/workspace use, not quota circumvention.

### MiniMax

Current decision: **do not buy more MiniMax capacity until the existing plan is actually admitted and utilized.** The observed problem is currently access/routing, not shortage. Finish governed harness admission, then measure accepted-result utilization and concurrency pressure. Upgrade only if real useful demand saturates the current plan or direct-plan concurrency becomes the bottleneck.

## 9. Exact implementation sequence

1. Review/land the generic subscription-capacity economics law without touching live provider activation.
2. Preserve current source custody on routing/provider files already touched by open PRs; do not collide with them merely to insert prose.
3. Incumbent Fable remains cross-repository integration principal; Sol retains economics/routing architecture and acceptance. Bounded mechanical work should route to least-scarce capable workers under current law.
4. MiniMax Provider Control: finish/reconcile #7103's current source gates and prove the already-existing MiniMax remaining-quota path. When current credential/policy gates permit, obtain one authorized secret-safe fresh model-scoped observation.
5. MiniMax worker path: reconcile #665's recorded predecessors/blockers and resume that SAME carrier when lawful; do not rebuild. Governed canary acceptance requires a real bounded task -> visible workspace result -> native before/after usage -> independent review -> parent consumption, not a PONG.
6. MiniMax learning: create task-cohort receipts for M3 and then M2.7; promote only cohorts that meet accepted-result quality/reliability.
7. OpenCode Provider Control: keep #7143's `account_shared` usage rows canonical; combine those same shared resources with model-specific reviewed debit/rate functions from the existing economics/offer owners. Never create per-model balance rows from the public table alone.
8. OpenCode worker path: complete the existing reviewed single-account streaming/governed harness before production placement; keep multi-account circumvention explicitly rejected.
9. Quota economics #7116: bind all Go model options to the SAME shared native window identities with different expected debit costs. For direct MiniMax, consume the provider's model-scoped resource rows. Keep hard suitability/policy/admission gates first.
10. Extend #7116 ranking with explicit, explainable portfolio opportunity cost rather than a new allocator: marginal cash, measured native cost per accepted outcome, expiry pressure, demand reserves, alternate eligible capacity, and review/continuity constraints.
11. Route real bounded work and measure accepted outcomes, native burn, repair/review cost, concurrency and avoided marginal spend. Only then decide subscription upgrades from observed saturation.

## 10. Concrete acceptance matrix

### MiniMax first useful vertical

Input: one already-authorized bounded implementation/refactor task in a cohort M3 has passed in evaluation.

Machine path owed:

`fresh Provider Control MiniMax observation -> Model Router suitability -> Capacity economic rank -> Executive claim/admission -> existing governed MiniMax harness -> same workspace visible result -> normalized terminal usage/outcome -> independent review -> parent result consumption -> corrected Provider Control observation`

Acceptance requires no Chairman account/model selection, no duplicate attempt, no hidden pay-as-you-go fallback, and a routing receipt that shows why direct MiniMax was chosen over scarcer/metered alternatives.

### OpenCode first useful vertical

Input: one bounded task for which at least two Go models are eligible and current shared Go capacity is fresh.

Machine path owed:

`one account-shared 5h/weekly/monthly observation + current offer/rates -> candidate-specific shared-quota debit estimates -> Model Router quality tier -> Capacity choice -> existing Go transport with stable session -> accepted result -> actual shared-window burn reconciliation -> parent consumption`

Acceptance requires proof that the model choice did not assume an independent wallet, did not rotate accounts around limits, and remained better after accepted-result/repair cost rather than raw token price alone.

## Capability state

- generic capacity-economics source law: proposed in #671, corrected for shared-vs-model-scoped quota semantics; not protected until merged;
- OpenCode public plan + upstream implementation reconciliation: current evidence supports shared native windows with model-dependent debit/equivalent allowance semantics;
- OpenCode Provider Control observation (#7143): `BUILT_NOT_PROVEN` / account-shared semantics preserved;
- OpenCode production worker route: `PARTIAL / BUILT_NOT_PROVEN` depending slice; full accepted-result route not proven;
- OpenCode multi-account pooling for limit expansion: rejected by design/policy; no expansion authorization;
- MiniMax model suitability for broad worker cohorts: promising but not accepted merely from provider claims;
- MiniMax current autonomous Fabric use: `DARK_OR_DISCONNECTED` / disarmed by current binding/profile gates;
- MiniMax Provider Control parser (#7103): built in current draft owner, exact governed/live integration still gated;
- MiniMax Codex transport candidate (#665): `BUILT_NOT_PROVEN`, parked with known blockers;
- quota-economics integration (#7116): `PARTIAL`; current implementation already has hard gates, native resource costs, expiry forecast and demand reserves, but full Provider-Control -> claim-time production composition remains unproven;
- subscription scale-up decision: hold purchases until current legitimate capacity is admitted and measured on accepted work.
