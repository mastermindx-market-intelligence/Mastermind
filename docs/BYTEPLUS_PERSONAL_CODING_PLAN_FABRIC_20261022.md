# BytePlus Personal Coding Plan — Fabric enrollment and qualification

**Status:** source-only DRAFT/HOLD; **not a funded/runnable Fabric pool**. The
Chairman purchased a $50 Personal Pro subscription. On October 22, 2026,
BytePlus's official CLI returned **Coding Plan / Personal / Pro / Running**
after a human-completed SSO ceremony on an authorized host. This proves one
account's then-current subscription tier, not any worker grant, model canary,
usage headroom in request units, production pool enrollment or legal right
to broker unrestricted inference. No account IDs, credentials or subscriber
profile files are published in this repository. Credential access remains
with the existing private owner; no raw secrets were observed.
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

## Published Pro-tier quota estimates (tier attested, capacity not measured)

| Window | Advertised personal Pro capacity, not account measurement | Reset basis |
| --- | ---: | --- |
| Five hours | ~9,500 model requests | Sliding window since consumption |
| Week | ~60,000 model requests | Vendor Monday reset (confirm timezone in account console) |
| Subscription month | ~120,000 model requests | Subscription-month anniversary |

These advertised amounts must **not** initialize Capacity quota, counters,
concurrency, eligibility or autonomous admission. The actual usable quota
and throughput depend on model coefficients, context,
workload, account, region and provider throttling. No fixed number of
concurrent workers is proven. A prompt may trigger many model invocations.
Keep concurrency UNKNOWN until an authorized supported-tool canary and
bounded 1/2/4/8-worker experiment with real quota and 429 observations.

## Published supported model names

- `dola-seed-2.0-pro`, `dola-seed-2.0-lite`, `dola-seed-2.0-code`
- `glm-5.3-flash`, `glm-5.2`
- `deepseek-v4.1-flash`, `deepseek-v4-flash`, `deepseek-v4-pro`

- `ark-code-latest` (console-selected model or automatic routing)

**Deprecated September 23, 2026:** `bytedance-seed-code`, `glm-5.1`,
`kimi-k2.5`, and `gpt-oss-120b` must not be durable routing defaults.
Some broad vendor setup pages still display them. Prefer the more specific
vendor deprecation notice:
https://docs.byteplus.com/en/docs/modelark/coding-plan-personal-model-deprecation

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


## October 22 owner observations: plan, catalog, quota, runtime

Source scope: authenticated BytePlus **official Ark CLI** for the subscribed
Personal Pro account in Singapore region, without raw credential disclosure.
A one-time management read returned scope Personal, tier Pro, status Running.
The account's `usage plan` and `usage balance --type plan` returned:

| Window | Displayed usage | Reset as reported by provider |
| --- | --- | --- |
| 5-hour | 0% (integer) | Not returned |
| Weekly | 0% (integer) | 2026-10-26T00:00:00+08:00 |
| Subscription month | 0% (integer) | 2026-11-22T23:59:59+08:00 |

**0% is a rounded display, not zero model requests or proof of a canary
debit.** The CLI did not return exact model-request counts, monetary
cost, weighted burn coefficient, or a numeric simultaneous-worker cap.
The prior human-reported attended Claude Code canary is not an
independently captured model response or quota decrement.

The vendor-authenticated `plans model-list --mode direct` offered
`dola-seed-2.0-pro`, `dola-seed-2.0-lite`, `dola-seed-2.0-code`,
`deepseek-v4.1-flash`, `glm-5.2`, `deepseek-v4-flash`,
`deepseek-v4-pro`, `glm-5.3-flash`, `ark-code-latest`,
and `skylark-embedding-vision` (embedding-only). This **does not**
qualify a model for every coding client. The routing catalog identified
DeepSeek V4.1 Flash's served snapshot as `deepseek-v4-1-flash-260910`;
do not claim BytePlus serves the newer October 17 release without another
provider-current readback. Models deprecated September 23 did not appear.

Provider sources:
- https://docs.byteplus.com/en/docs/modelark/coding-plan-personal-plan-overview
- https://docs.byteplus.com/en/docs/modelark/coding-plan-personal-model-deprecation
- https://docs.byteplus.com/en/docs/modelark/coding-plan-personal-ai-claude-code

## Seven-subscription comparison and actual router observations

Fleet premise supplied by Chairman: three existing Z.AI plans, three Alibaba
plans, one BytePlus Personal Pro account. The current repo does **not** contain
a common normalized, provider-attested unit of cost or per-account residual
capacity for all seven plans. Never equate BytePlus model requests with
Z.AI weighted credits or with Alibaba token counts. Subscription price is a
sunk monthly cost for plans already purchased; rank incremental work by
first-accepted outcome and opportunity cost of exhausting the right window.

### Actual incumbent routing

The live Ubuntu1 Fabric read-only observation on October 22 found
`execute_order = minimax, glm-flash, bailian, go, grok, cursor`.
The current preference weights already favor MiniMax for eligible leaves;
`glm_peak_active` applies during weekdays 14:00-18:00 Asia/Singapore,
but its existing GLM peak selection logic only demotes a **full**
GLM labor request to Flash when one is requested. It **does not**
in itself move the whole Z.AI Flash pool behind other eligible providers.

The tracked source version of the native picker is not identical to the
installed Ubuntu1 picker: exact observed live SHA-256
`957b05438170c3e1205d3ea6637241a5b90750b1ea7cf2da93867a659c36714b`;
source-tree `ops/native_fabric/quota_continuity/source/pick.py`
SHA-256 `0f5cbc32504680e09055b77cffdea81adea734388b7b061fcf77d017b7715cb2`.
They differ materially (over 300 live/source line differences).
**Do not** overwrite the installed picker with this historical staged source
or apply an unreviewed direct runtime patch. The existing generation/install
owner must reconcile the exact live baseline and release the next reviewed
generation without disturbing active original operations.

The incumbent launch ledger for October 15–22, 2026 showed approximately
172 GLM launch rows, 220 combined Alibaba/Qwen rows, and 71 MiniMax rows.
The corresponding `rc == 0` row counts were 164, 190 and 67.
Adapter exits are **not** accepted jobs; duplicate or follow-on rows are
possible. No baseline quality/accepted-outcome comparison with BytePlus exists.
`bailian` and `qwen` both refer to the Alibaba family and must not be
double-counted as independent subscription pools.

### Proposed decision matrix (not autonomous activation)

| Original job | Preferred eligible candidate | Scarcity and qualification rule |
| --- | --- | --- |
| Easy mechanical/code validation | Existing Qwen/MiniMax; GLM Flash if required | Cheapest *qualified* existing worker within first lawful tier, respecting cooldowns and first-pass acceptance |
| Routine backend coding | Z.AI GLM-5.3-Flash; BytePlus DeepSeek-V4.1-Flash challenger | BytePlus only inside subscribed user's supported coding tool, after measured coding canary |
| Frontend UI, screenshot-to-code | BytePlus Dola-Seed-2.0-Code challenger | Image+tool quality benchmark required; alternatives remain eligible |
| Difficult technical reasoning/independent review | Z.AI GLM-5.3 full or qualified independent provider | Do not equate GLM Flash on BytePlus with provider-independent review of Z.AI GLM |
| Long context technical code | BytePlus DeepSeek V4.1 Flash or GLM Flash challenger | Published 1M window != 1M reliably usable tokens; run actual long-context benchmark |
| Complex code planning in supported IDE | BytePlus Dola-Seed-2.0-Pro challenger | Supervised coding seat; no implied team/API backend permission |
| Exceptional expensive review | BytePlus DeepSeek V4 Pro only after outcome win | Higher published quota deduction coefficient; never routine default |

**Time-aware GLM rule:** Current Z.AI Devpack documentation states
5-hour/weekly Max budgets of 28,000/140,000 *weighted credits* per
account; input/cache/output multipliers for GLM-5.3 are 6.9/1.7/24,
and for GLM-5.3-Flash are 2.3/0.56/8, per 10,000 tokens. Both models
are charged half those subscription credits **off-peak**, with peak
Monday–Friday 14:00–18:00 Asia/Singapore. The special all-day
September 25–October 7 promotion has expired. Rank Z.AI's *eligible*
GLM use preferentially off-peak, but do not delay urgent work or
promote a less-suitable tier purely to exploit discounts. During peak,
prefer a qualified Alibaba/MiniMax alternative if it can satisfy the
same task/review rules, or BytePlus when a **separately supported human
coding-tool** job can lawfully consume it. Never apply Z.AI's discount
to BytePlus GLM Flash or Alibaba GLM.

Reference: https://docs.z.ai/devpack/overview

### Required load-balancing invariants

1. Model Router fixes the first lawful capability/quality tier. Capacity
   ranks only eligible options *within* it, based on currently observed
   account-specific quota, expiry, health, task quality and host room.
2. The existing account/lease broker owns each exact provider-plan-account-
   model-harness-host claim. Same vendor/model on separate subscriptions
   is **not** the same pool; conversely a single subscription used by
   several tools is **one shared allowance**.
3. Unsupported or stale quota, unknown concurrency or rounded-percent-only
   usage cannot originate a positive startable-job estimate. Never
   convert a nominal 9,500-call 5-hour package into '8 workers'.
4. A credit multiplier is economic advice, not permission to work.
   Respect server 401/403, 429/cooldown, quota, reviewer-not-author,
   original lease, no-double-start, host eligibility and root-budget
   before comparing costs.
5. Only an observed typed **pre-task** capacity rejection with existing
   effect-fence proof can permit the incumbent limited fallback. Post-START
   error, incomplete response and effect-unknown may not be replayed.
6. BytePlus Personal Pro may not be selected by the generic
   `capacity_economics_projection.project_quota_preference`; its
   `byteplus.attended` route is excluded even if a forged positive
   quota preview advertises many worker slots. Use only a reviewed
   supported coding-tool consumer and the existing provider realm.
7. Score candidate models on acceptance probability, reviewer independence,
   validated complexity/vision skill, measured latency and *real*
   incremental quota consumption. Unknown metrics remain unknown, never
   zero cost or unlimited slots.

### Qualification experiment (do not dispatch unattended calls)

Use one operator-attended approved coding tool on the subscribed user's
device. Capture redacted current plan tier and before/after usage via
BytePlus management API; run one small coding test with an exact model,
then a repeatable representative coding task. Record tool identity, model
alias and served snapshot, wall time, terminal exit, deterministic
artifact/test acceptance, throttling class and provider quota delta.
Only with observed permitted use should a conditional 2/4 concurrent
supported-tool session trial be attempted, with no uncontrolled background
pool or auto-retry. Stop on provider-policy denial, 401/403, ambiguous
effects or unexpected separate pay-as-you-go charges.

Benchmark each candidate against the incumbent Z.AI/Alibaba/MiniMax
candidate within the same *first-lawful* task tier. Use 30+ bounded
representative coding tasks with frozen source revisions, tests,
independent reviewer and paired success metrics before assigning new
default weight. Until then BytePlus is a qualified seat candidate,
**not** a measured low-cost general-purpose Fabric worker.
