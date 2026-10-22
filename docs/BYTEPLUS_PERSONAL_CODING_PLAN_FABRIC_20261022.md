# BytePlus Personal Coding Plan — Fabric enrollment and qualification

**Status:** source-only DRAFT/HOLD; **not a funded/runnable Fabric pool**. The
Chairman's first personal Pro subscription is purchased. Credential transfer
and private account state are owned outside this public repository.
Provider login validity, active subscription entitlement, quota balance,
concurrent worker limit, and model invocation were **not** observed.
Do not record private enrollment state, a key or personal account identifier
in GitHub, logs, events, worker packets, provider profiles or reports.

## Original job and use-policy boundary

Expose an additional economical coding-worker avenue through the **existing**
Model Router / Capacity Fabric / Executive OS with the same trusted identity,
admission, claim, quota and result owners. A provider profile is not an
account, lease, runtime worker, installed adapter, canary or permission to run.

BytePlus documents that the personal Coding Plan can be used **only in
supported AI programming tools**, with one plan's quota shared among them.
It is not a general API inference entitlement. Do not point arbitrary
Fabric backend requests directly at its endpoint, multiplex it into
unsupported products, or operate a personal seat as an unattended/shared
service without provider permission. A generic ModelArk pay-as-you-go
endpoint may incur separate charges.

Exact supported Anthropic coding endpoint:
`https://ark.ap-southeast.bytepluses.com/api/coding`

Exact supported OpenAI-compatible coding endpoint:
`https://ark.ap-southeast.bytepluses.com/api/coding/v3`

**Do not** confuse either endpoint with `/api/v3` (PAYG).
Provider docs: https://docs.byteplus.com/en/docs/modelark/coding-plan-personal-plan-overview
and https://docs.byteplus.com/en/docs/modelark/coding-plan-personal-ai-claude-code

## Published quotas (estimates, not actual account observations)

| Window | Personal Pro advertised up to | Reset basis |
| --- | ---: | --- |
| Five hours | ~9,500 model requests | Sliding window since consumption |
| Week | ~60,000 model requests | Vendor Monday reset (confirm timezone in account console) |
| Subscription month | ~120,000 model requests | Subscription-month anniversary |

The actual usable quota and throughput depend on model coefficients, context,
workload, account, region and provider throttling. No fixed number of
concurrent workers is proven. A prompt may trigger many model invocations.
Keep concurrency UNKNOWN until an authorized supported-tool canary and
bounded 1/2/4/8-worker experiment with real quota and 429 observations.

## Published supported model names

- `dola-seed-2.0-pro`, `dola-seed-2.0-lite`, `dola-seed-2.0-code`
- `bytedance-seed-code`
- `glm-5.3-flash`, `glm-5.2`, `glm-5.1`
- `kimi-k2.5`, `gpt-oss-120b`
- `deepseek-v4.1-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`
- `ark-code-latest` (console-selected model or automatic routing)

Use the regional console's allowed models as the actual final authority.
`glm-5.3` full is **not** in the currently published BytePlus catalog;
the incumbent Z.AI pool remains the source for that full model.

Proposed suitability **only after real model-specific qualification**:
GLM-5.3-Flash for routine code/test/long context; Seed-Code and Dola
Code/Pro for implementation; Kimi-K2.5 for UI/visual tasks; DeepSeek
V4-Pro for exceptional complex review due higher quota coefficient.
Each family must pass a tool/use-policy and quality canary.

## Economic policy: Z.AI peak only, not universal GLM penalty

Z.AI source currently specifies both `GLM-5.3` and
`GLM-5.3-Flash` at **0.5x subscription credit usage outside**
Monday–Friday 14:00–18:00 Asia/Singapore (UTC+8). This is the Z.AI
account's *credit consumption rule*, not a BytePlus price discount.
The existing `glm_keys.py` economic helper already represents this
window. Do not alter it or impose a penalty on other GLM providers.

When Z.AI is peak, BytePlus GLM Flash can be preferred **only if**
its independently observed remaining quota, supported tool identity,
actual model availability and capacity are eligible. Outside the peak
window, consider the Z.AI half-credit advantage alongside each pool's
burn-down horizon and measured failure rate. If BytePlus lacks qualified
capacity, use the incumbent existing admitted pool; never invent availability.

## Safe activation ladder (single writer, exact target)

1. Review this source catalog and inert alias with a second owner.
   The `byteplus-coding-plan-personal` binding is `SPEC_ONLY`,
   `autonomous_allowed=false`, and `byteplus.attended` is excluded
   from all automatic routes. No new queue, retry loop, account registry,
   scheduler or credential store is authorized.
2. Obtain the exact coding-plan provider credential through the
   existing private credential owner, with only local user-attended
   Keychain consent. The Keychain item being present is **not**
   enrolled provider-home evidence. Do not copy/echo credentials in
   shells, argv, source, chat, CI, or logs.
3. Qualify a dedicated, **distinct BytePlus** supported Claude Code
   worker/attended realm. The existing installed finite
   MiniMax-only host `minimax-finite-01` and its config are immutable
   and cannot be relabeled or borrowed. Reuse provider-neutral adapter
   primitives after review, never claim the MiniMax receipt covers BytePlus.
4. Validate dedicated byteplus endpoint, explicit model, isolated
   Claude Code configuration, a bounded foreground supported-tool
   invocation and `/status`/provider activation-management readback.
   Confirm no PAYG fallback and compare an actual quota decrement. No
   provider authentication/canary receipt has been obtained yet.
5. Feed a real source-owned Capacity fact and provider realm receipt
   into the existing admission owner. Enroll one OFFLINE runtime
   worker through the Executive OS owned path before any subsequent
   eligible status; never hand-author eligibility flags or reuse an
   existing worker principal.
6. Only then extend the incumbent picker and broker in one
   reconciled modifying carrier, retaining per-provider key quotas,
   worker leases, original root/parent, model exclusion, retry and
   effect fences. ModelRouter accepts the inert alias but will **not**
   route it automatically. No separate Fabric scheduler.
7. Use a quota-aware foreground canary and bounded concurrency tests.
   Validate 401/403, 429, exhausted five-hour/weekly/monthly windows,
   unsupported models, peak rollover, Keychain denial, offline worker,
   unknown capacity and fallback. Check quality and independent review
   before accepting ordinary coding tasks.

## Current proof and blockers

- PR #1725 is the source owner. Provider profile, binding and inert
  model alias validated in unit tests, including rejection from
  automatic routes.
- Local secret handoff and account state remain **outside** source control.
  A local key handoff is not proof of root-owned credential enrollment.
- Credential materialization is held to the authorized existing owner and
  explicit user-attended supported-tool path. Do not create a parallel
  credential-injecting launcher or rerun a stopped carrier effect.
- No real model response, subscription debit, concurrency ceiling,
  private provider-home installation, Executive broker receipt,
  installed worker, accepted CI/review, or deployment has been proven.

**Next owner action:** bind the actual user-attended supported coding
tool through the approved provider credential owner and obtain a
positive coding-plan quota consumption/canary receipt, without
changing the incumbent MiniMax realm or live Fabric router.
