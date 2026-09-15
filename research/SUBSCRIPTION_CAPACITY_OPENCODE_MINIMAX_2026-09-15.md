# OpenCode Go + MiniMax subscription capacity application — 2026-09-15

## Mission

Apply `docs/EXECUTIVE_SUBSCRIPTION_CAPACITY_ECONOMICS_LAW.md` to the two visibly underused fixed-fee pools without inventing a new router, quota ledger, worker lifecycle, account pool, or provider permission.

This is current research / routing input. It does not arm a provider, approve a purchase, merge a quarantine-release PR, or satisfy a provider usage-policy gate.

Protected Mastermind base used for repository truth: `8e25bb32601ef5f40a689da6d6f24149e79e31fa`.

## 1. OpenCode Go — current external facts

OpenCode's current Go documentation states:

- plan price: $10/month;
- only one member per workspace can subscribe;
- current model list spans Grok 4.6, GPT 5.6 Luna, GLM 5.3/5.3 Flash/5.2/5.1, Kimi K3/K2.7 Code/K2.6, MiniMax M3/M2.7, Qwen 3.8/3.7/3.6 variants, DeepSeek V4 variants, MiMo, Hy, Muse and LongCat;
- quotas are model-specific monthly dollar ceilings; each model has 5-hour = 20% and weekly = 50% of its monthly ceiling;
- many models currently carry $60 monthly model-specific ceilings while several premium/new models carry $15 or $30;
- the current published table totals roughly $1,200 of nominal non-fungible model-bucket ceilings if every listed row is counted, but this is **not** $1,200 of fungible balance and must never be represented as such;
- Codex and Claude Code are listed as validated clients when session identity is preserved;
- current Go traffic is expected to look like coding-agent traffic and carry stable session identity;
- Go usage limits may change.

Current source: https://dev.opencode.ai/docs/go/

OpenCode Terms effective 2026-08-15 prohibit creating/maintaining/using accounts in bulk or using multiple accounts to circumvent usage limits, access restrictions, billing obligations, promotions, suspensions, or other policies.

Current source: https://opencode.ai/legal/terms-of-service

### Chairman screenshots observed this turn

Three Go subscriptions showed current weekly utilization of approximately 11.2%, 21.0% and 12.7%, and monthly utilization of approximately 5.6%, 10.5% and 6.3%.

The visible spend was concentrated disproportionately in GPT 5.6 Luna. One account was effectively Luna-only, while large model-specific buckets such as MiniMax M3, Qwen Plus, DeepSeek Flash and several other open-model lanes remained nearly untouched.

This is evidence of **poor portfolio allocation**, not proof that Go itself is uneconomic.

## 2. OpenCode routing decision

Do **not** scale additional accounts for the purpose of multiplying one operator's limits. That conflicts with current OpenCode terms and the existing Mastermind `usage_policy_satisfied` gate.

Treat any currently legitimate Go subscription as a diversified fixed-fee portfolio:

1. Use Go where it provides incremental model diversity, independent review, overflow, or otherwise-expiring model-specific capacity.
2. Do not treat total account utilization as the routing unit; preserve each model/window bucket.
3. Do not make Luna the default Go worker merely because generic fast-engineering aliases prefer Luna elsewhere.
4. When direct OpenAI included capacity is healthy, Go-Luna normally has lower portfolio value than Go access to model families not otherwise abundant.
5. When direct MiniMax Token Plan capacity is healthy, Go-M3/M2.7 normally has lower portfolio value than Go's other underused model families unless Go capacity is about to expire, direct MiniMax is unavailable, or Go provides a needed independent reviewer.
6. Use model-specific current evaluation evidence before promoting a Go model to a task cohort. Unused quota is not evidence of quality.

### Near-term Go evaluation priority

Before the next reset, benchmark/qualify high-headroom Go candidates against real bounded cohorts rather than blindly burning them. Current high-value candidates include:

- `DeepSeek V4.1 Flash` — currently carries a temporary 4× / $60 monthly Go ceiling through Sep 20; prioritize useful canary/evaluation work while the promotion exists, subject to task quality;
- `GLM-5.3-Flash` — large $60 model bucket and high estimated request volume; useful fast-lane candidate;
- `Qwen3.7 Plus` / `Qwen3.8 Flash` — large/medium Go buckets; candidates for routine/standard coding and research after evaluation;
- `Kimi K2.7 Code` — coding-specific candidate with a large Go bucket;
- `DeepSeek V4 Flash` / `MiMo V2.5` / `Hy3` — high-volume candidates for bounded lower-cost cohorts;
- `Grok 4.6`, `Qwen3.8 Max`, `Kimi K3`, `GLM-5.3`, `DeepSeek V4 Pro` — lower model-specific ceilings; preserve for tasks where their quality or independence justifies the scarcer bucket;
- `GPT 5.6 Luna` — use only when Luna is actually the best eligible route after considering direct OpenAI capacity, continuity, quality and expiry pressure.

The exact cohort map remains Model Router evidence, not this memo.

## 3. OpenCode implementation state inside Mastermind

Protected source currently keeps the OpenCode Go Codex realm in `CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY`; no worker binding is authorized from that candidate registry.

The protected OpenCode composition checkpoint is `PARTIAL / BUILT_NOT_PROVEN / PRODUCTION-INERT`. Synthetic tests proved request/session custody and safe pre-effect rollover semantics, but did not prove live account independence, real quota, running coding-agent recall, or production provider execution.

Existing ownership is correct and must be preserved:

- Model Router — suitability;
- Shared AI Provider Control — account/quota/headroom/health;
- Capacity Fabric + Executive OS — allocation and lifecycle;
- provider-home owner — credentials;
- OpenCode transport kernel — effect-safe request custody only.

Do not add another OpenCode-specific router.

## 4. MiniMax — current external facts

MiniMax's current Token Plan page advertises approximately:

- Plus: ~1.7B M3 tokens/month and 3–4 concurrent agents;
- Max: ~5.1B M3 tokens/month and 4–5 concurrent agents;
- Ultra: ~12.5B M3 tokens/month and 6–7 concurrent agents;
- annual prices currently around $198 / $495 / $1,188 on the promotional subscription page, with another current page showing rounded $200 / $500 / $1,200 annual pricing;
- access to the MiniMax family including M3 / M2.7 plus image and speech; image/video input understanding is native on M3; text/image/speech share plan quota;
- own-tool integration through Token Plan keys and common coding clients.

Current source: https://platform.minimax.io/subscribe/token-plan

MiniMax M3 is currently positioned by MiniMax as a coding/agentic frontier model with up to 1M context, native image/video understanding, autonomous task decomposition, tool invocation, multi-step reasoning, and computer-use capability. Provider benchmark claims are marketing evidence and must not substitute for Mastermind task-cohort evaluation.

Current source: https://www.minimax.io/models/text/m3

Current pay-as-you-go M3 rates published by MiniMax are $0.30/M input and $1.20/M output up to 512K context, with $0.60/M input and $2.40/M output for 512K–1M, plus discounted cache reads. M2.7 standard is also $0.30/M input and $1.20/M output with cache pricing.

Current source: https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise

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

For sustained MiniMax-family work, the direct Token Plan is economically the workhorse product because it advertises billions of M3 tokens/month and multiple concurrent agents. OpenCode's MiniMax bucket is valuable diversification/overflow, but its current M3 model-specific monthly ceiling is $60-equivalent and should not be the primary place to spend MiniMax-family work while a much larger legitimate direct MiniMax pool is idle.

Conversely, OpenCode is unusually valuable for **breadth**: one $10 plan currently exposes many separate model buckets. Its economic advantage comes from harvesting useful diversity, not from sending most work to the same Luna or MiniMax model that Mastermind already owns elsewhere.

## 8. Purchase decision

### OpenCode

Current decision: **do not add more accounts to increase pooled capacity.** First maximize lawful use of existing legitimate subscriptions by model-specific routing and evaluation. Revisit purchasing only for provider-supported distinct member/workspace use, not quota circumvention.

### MiniMax

Current decision: **do not buy more MiniMax capacity until the existing plan is actually admitted and utilized.** The observed problem is currently access/routing, not shortage. Finish governed harness admission, then measure accepted-result utilization and concurrency pressure. Upgrade only if real useful demand saturates the current plan or direct-plan concurrency becomes the bottleneck.

## 9. Exact implementation sequence

1. Land/review the generic subscription-capacity economics law without touching live provider activation.
2. Preserve current source custody on routing source files already touched by open PRs; do not collide with them merely to insert prose.
3. Give the incumbent Capacity/Fable integration owner this dated application as source intake.
4. MiniMax: repair/resume the existing #665 lane rather than rebuild; satisfy its recorded blockers, then run the governed real canary only when current activation/policy gates allow.
5. MiniMax: create task-cohort evaluation receipts for M3 and then M2.7; promote only cohorts that meet accepted-result quality/reliability.
6. OpenCode: complete the already-planned single-account reviewed streaming harness before any production route; keep multi-account circumvention explicitly rejected.
7. Feed model-specific headroom/reset evidence into existing Capacity ranking; do not average model buckets into account utilization.
8. Route real bounded work and measure accepted outcomes, native burn, repair/review cost and avoided marginal spend.
9. Only then decide subscription upgrades from observed saturation and accepted-work economics.

## Capability state

- generic capacity-economics source law: proposed in this branch, not protected until merged;
- OpenCode economic diagnosis: research complete; production route still not proven;
- OpenCode pooled/multi-account use: policy-gated; no expansion authorization;
- MiniMax model suitability for broad worker cohorts: promising but not accepted merely from provider claims;
- MiniMax current autonomous Fabric use: `DARK_OR_DISCONNECTED` / disarmed by current binding/profile gates;
- MiniMax Codex transport candidate (#665): `BUILT_NOT_PROVEN`, parked with known blockers;
- subscription scale-up decision: hold purchases until current capacity is legitimately admitted and measured.
