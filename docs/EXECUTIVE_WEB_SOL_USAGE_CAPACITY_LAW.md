# Executive Web-Sol Usage and Capacity Observability Law

**Date:** 2026-09-02  
**Chairman:** Chris  
**Owner:** Sol, AI CEO  
**Primary workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Dependent canonical capacity workstream:** `WS:EXECUTIVE-CAPACITY-FABRIC`  
**Operation:** `web-sol-pro-usage-observability-20260902-sol-001`  
**Protected Mastermind source pin:** `162af533a4bcf380125895d225b6962987c3c582`  
**Macro Provider Control review pin:** `818451efac2c1a95917f6110fabb024054911356`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**Capability state:** `RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT`.

This law answers one product problem: Mastermind must know how scarce each ChatGPT Web reasoning realm is, how much Mastermind has actually used it, and when it may become usable again without making the Chairman manually watch quota menus across accounts.

It does **not** authorize browser scraping, provider-private endpoints, account switching, usage-limit circumvention, a new quota database, a new scheduler, or automatic cross-account failover. It adds no browser, provider, Executive, RuntimeBinding, credential, billing, or production effect.

## 1. Chairman outcome

The intended end state is:

```text
one set of paid ChatGPT Web reasoning realms
-> each exact managed-browser realm has an opaque canonical capacity slot
-> Mastermind records the reasoning turns/effects it can prove it caused
-> supported provider quota/reset evidence is preserved with provenance and freshness
-> unknown provider headroom remains UNKNOWN
-> Control Room can show exact vs observed vs estimated capacity truth per realm
-> Capacity can eventually plan new eligible work against lawful fresh evidence
-> an exhausted realm is not confused with a full conversation context
-> no started or effect-unknown operation is duplicated on another realm
```

The Chairman should not need to remember whether an allowance is weekly, monthly, rolling, model-specific, or temporarily changed by the provider. Mastermind stores the **observed reset timestamp and evidence**, never a universal cadence assumption.

## 2. Canonical owner map

Ownership is frozen as follows:

```text
Web-Sol / managed-browser adapter
    = bounded source sensor for its own exact browser realm

Macro Shared AI Provider Control
    = canonical provider/account-slot availability, health, cooling and quota truth

mastermind.provider_capacity.*
    = secret-free versioned Provider Control projection

Model Router
    = model/execution suitability only

Executive OS
    = final Job/Attempt/Worker claim and lifecycle among already-lawful workers

SessionTargetRegistry / RuntimeBinding
    = logical Sol target and exact rotating conversation binding

Agent OS
    = durable organizational workstream/decision/discovery/handoff state

Control Room
    = read-only product projection of accepted truth
```

There is no Web-Sol quota database and no Executive `ProviderAccount`/`QuotaHorizon` truth store. `surface_bindings` remains navigation-only and may not receive usage, quota, reset, plan, or lifecycle fields.

## 3. Browser realm identity is a slot, not a provider account identity

A managed GoLogin/Multilogin profile already has one opaque Web-Sol adapter instance identity. A later Provider Control evolution may bind one reviewed opaque `capacity_capability_id` to that exact browser realm.

The binding means only:

```text
this company-managed browser realm is one capacity-bearing ChatGPT Web slot
```

It does **not** mean:

- the capability id is the provider's account id;
- two browser profiles belong to different paid subscriptions;
- two profiles belong to the same paid subscription;
- a Slack principal identifies the paid account;
- a profile ordinal or display name is account identity;
- an email, billing name, provider id, cookie, token, credential, or secret fingerprint may be persisted.

If a human changes the authenticated ChatGPT account inside a managed profile, prior provider quota evidence for that realm is invalid until the canonical Provider Control binding/provisioning generation is deliberately re-established. Web-Sol never tries to detect account equality by inspecting credentials or PII.

## 4. Three different numbers must never be collapsed

The product must distinguish:

### 4.1 Mastermind-observed reasoning activity

What Mastermind can prove about its own actions or bounded local browser events, for example:

- one governed Web-Sol submission definitely occurred;
- its requested reasoning mode is definitely known from the action contract;
- an accepted local observation saw a submission/generation boundary without reading message content.

This may support counters such as `mastermind_observed_sol_pro_submits`. It is **not** total provider-account usage because the Chairman, mobile clients, another browser, or another lawful surface may use the same subscription outside the observer.

### 4.2 Provider-reported quota/reset evidence

What a documented, supported provider surface truthfully reports, such as a quota percentage, fixed count, exhaustion state, or `reset_at` timestamp. Preserve the provider's semantics; do not convert a percentage into absolute remaining capacity when the limit is unknown.

### 4.3 Estimated runway

A forecast from historical Mastermind-observed activity and past provider exhaustion/reset observations. It is advisory. It may never be presented as provider-reported remaining quota or used to bypass a hard provider restriction.

A UI must visibly label these classes rather than presenting one synthetic `remaining turns` number.

## 5. Evidence vocabulary

Any future ChatGPT Web capacity source must use a closed provenance class no stronger than the evidence actually supports:

```text
exact_local
provider_reported
manual_confirmed
estimated
unknown
```

Interpretation:

- `exact_local`: a deterministic local Mastermind fact, such as one action receipt. It says nothing about unobserved provider usage.
- `provider_reported`: obtained through a currently documented/supported provider surface or API with reviewed authority.
- `manual_confirmed`: a human explicitly transcribed/confirmed a visible provider value; useful but not autonomously refreshed.
- `estimated`: derived from a reviewed estimator with explicit inputs and confidence.
- `unknown`: no safe evidence exists.

`unknown` is not zero, full, unlimited, available, or exhausted.

## 6. No universal weekly/monthly rule

Do not hardcode:

```text
ChatGPT Pro resets weekly
ChatGPT Pro resets monthly
billing renewal == quota reset
20x == a fixed number of Pro turns
one Pro turn == one fixed quota unit
```

OpenAI can expose different allowances and reset cadences by plan, model, workspace, entitlement, product surface, and time. The authoritative operational value is the current supported provider observation for that exact realm and quota class.

A quota observation may carry, when actually known:

```text
quota_class
model_or_reasoning_class
window_type
window_duration_seconds
used_percent
limit
used
remaining
reset_at
observed_at
stale_after
provenance
```

All dynamic numeric/time fields are nullable. `remaining` may not be derived from `used_percent` without a known limit. A reset timestamp may not be derived from a billing date.

## 7. Reset epochs are observations, not cron jobs

A reset is represented as an evidence epoch. If a provider-supported observation says `reset_at = T`:

```text
before T -> observation may be fresh according to its source freshness law
at/after T -> previous headroom evidence becomes stale
then -> re-observe through the accepted source
only after new evidence -> open the next provider quota epoch
```

Crossing `T` does **not** automatically assert `remaining = 100%`.

If no provider-supported reset time exists, reset remains `UNKNOWN`. A later local unavailable->available transition may be recorded as local evidence, but it may not be relabeled as the provider's contractual cadence.

## 8. What counts as a Pro turn

There is no company-wide assumption that every ChatGPT message consumes one equal unit of a Pro allowance.

A Pro-specific local counter increments only when both are proven for the same event:

1. one accepted submission/generation boundary occurred exactly once; and
2. the reasoning/model class for that submission is known through an approved bounded source or the exact Mastermind action contract.

If the submission is observed but the reasoning class is not known, increment only a generic `observed_chat_submits` counter and leave the Pro-specific counter unchanged/unknown for that event.

Duplicate service-worker events, page reloads, response streaming events, retries before provider mutation, and repeated observer callbacks must not double count one submission. An effect-unknown submission is preserved as uncertain; it is not blindly replayed to make accounting neat.

## 9. Supported-source gate

At this freeze, no Personal-Pro quota implementation is authorized to use:

- undocumented/private ChatGPT backend endpoints;
- browser cookies or session tokens;
- copied OAuth/access/refresh tokens;
- local/session storage extraction;
- network interception, HAR capture, `webRequest`, debugger or CDP credential reuse;
- hidden account metadata or provider-private GraphQL/REST calls;
- arbitrary DOM/transcript/model-output scraping;
- a normal OpenAI API key as a proxy for ChatGPT subscription allowance.

The existence of an unofficial browser extension or an internal endpoint is not a source-law exception.

A later automatic provider quota source requires one of:

1. a documented OpenAI account/workspace usage API whose terms and scopes cover the required field; or
2. another explicitly reviewed provider-supported machine-readable surface.

Until then, Personal-Pro provider headroom/reset is `UNKNOWN` unless manually confirmed. Manual confirmation is an interim observation input, not an automation substitute.

Enterprise/Edu/Business administrative APIs or analytics may be used only for the exact fields they document. A workspace usage-limit setting is not silently treated as current per-model remaining Personal-Pro quota.

## 10. Terms and anti-evasion boundary

This program is capacity observability and planning, not usage-limit evasion.

It must preserve current OpenAI usage restrictions and current Mastermind context-rotation law. In particular:

- do not automatically/programmatically extract ChatGPT data through an unsupported mechanism;
- do not circumvent or configure Mastermind to avoid provider rate/usage limits;
- do not share or export account credentials to pool capacity;
- do not treat a second paid account as permission to duplicate an in-flight operation;
- do not silently switch account/profile/model after exhaustion;
- do not create provider traffic merely to measure a limit.

A future lawful multi-seat capacity policy may choose among independently provisioned eligible seats for **new, not-yet-started work** only after the canonical Capacity/Executive policy admits that use. It may not retry an effect-unknown modification, evade a provider restriction, or broaden account entitlement.

## 11. Context exhaustion and account quota exhaustion are orthogonal

The product must preserve:

```text
conversation context unusable
    -> same logical responsibility may require exact chat succession

account/model quota exhausted
    -> capacity availability/cooling problem
```

A context-rotation successor normally stays in the same approved profile/account realm. Context rotation is not quota failover. Quota exhaustion is not evidence that the current conversation context is full.

## 12. Relationship to current `mastermind.provider_capacity.v1`

Current Macro `mastermind.provider_capacity.v1` is accepted for its existing provider realms and is already in the CF2-H0/P0/CF2-I release sequence. This Web-Sol program must **not patch that v1 contract in place** merely to add ChatGPT-Web source semantics while those gates are in flight.

ChatGPT-Web attached-browser realms follow the same architectural family already required for new native provider realms:

```text
bounded secret-free source observation
-> Shared AI Provider Control
-> explicitly reviewed versioned contract evolution
-> later Executive consumer evolution
```

The implementation may introduce a small versioned upstream observation contract owned by Web-Sol/Provider Control, but that contract is not itself canonical capacity truth. Macro remains the normalizer and correction owner.

## 13. Initial product projection

A truthful Control Room row may look like:

```text
ChatGPT Web Realm A / Sol Pro
Availability: AVAILABLE
Mastermind-observed Pro submits: 41 [EXACT_LOCAL]
Provider used/remaining: UNKNOWN
Provider reset: UNKNOWN
Forecast runway: 18-27 Mastermind turns [ESTIMATED / LOW CONFIDENCE]
Observation age: 2m
```

If a supported/manual provider reset exists:

```text
Provider reset: 2026-09-05T06:42:00Z [PROVIDER_REPORTED | MANUAL_CONFIRMED]
```

Never render `41 / 50` or `9 turns left` unless the denominator and arithmetic are actually supported by accepted provider evidence.

## 14. Release ladder

The program is split so Web-Sol reliability work and current Capacity Fabric release gates are not destabilized:

### `WSX-QF0` — source/policy falsifier

Determine, on disposable/non-sensitive surfaces, exactly which quota/reset fields OpenAI documents or visibly exposes for relevant plan families and which supported APIs exist. No private endpoint, credential extraction, browser automation, or production account mutation.

### `WSX-Q1` — local usage observation source law

Freeze exact-once local submission/accounting semantics and a secret-free upstream event contract. Source-law only.

### `CAP-WEB-F0` — Provider Control realm architecture

Freeze opaque ChatGPT-Web realm identity, re-auth invalidation, source precedence, correction/freshness behavior, and the versioned Provider Control contract evolution. Preserve current v1/CF2 release behavior.

### `WSX-Q2` — bounded Web-Sol observer

Only after current Web-Sol T1 source is protected and an installed disposable generation exists, implement the smallest allowed metadata-only observer/action receipts. No transcript/output/raw DOM/private endpoint.

### `CAP-WEB-1` — Provider Control implementation

Only after the Provider Control architecture is accepted and the current CF2 baseline is not being silently mutated, ingest the secret-free source into canonical Capacity truth.

### `CR-Q1` — Control Room projection

Show source class, freshness, observed turns, provider headroom/reset when known, and estimates without collapsing them.

### `Q-PROD1` — production observation proof

Prove at least one real account's observation lifecycle, including a naturally occurring reset/exhaustion boundary when available, with zero account switch/failover/limit-evasion behavior. Do not force traffic to hit a quota for the canary.

## 15. Failure states

Fail closed to `UNKNOWN`, `STALE`, or the current typed availability state when:

- provider quota/reset source disappears or changes shape;
- no supported source exists;
- plan/model class is ambiguous;
- profile/account binding may have changed;
- source evidence is stale;
- a percentage exists without a known absolute limit;
- a local event could have been counted twice;
- browser/service-worker interruption makes a submit effect uncertain;
- provider error exists but cannot be classified as a usage-limit signal without reading forbidden text;
- a current source-law/terms review rejects automated collection.

Accounting uncertainty must never cause an extra provider request.

## 16. Security and privacy redlines

Durable quota/capacity observations may contain only bounded operational metadata and opaque company-local identity. They must contain no:

- prompt or response content;
- transcript/model output;
- email, billing name, provider account id, subscription invoice id;
- cookie, token, password, API key, auth-file bytes;
- browser fingerprint/proxy values;
- raw private profile path or host address;
- arbitrary DOM/HTML/text extract;
- provider error body;
- full private URL when an opaque conversation/profile fingerprint suffices.

No browser permission is broadened merely because quota visibility would be convenient.

## 17. Capability ledger at this freeze

| Capability | State |
|---|---|
| Existing Web-Sol bounded surface observation source | `BUILT_NOT_PROVEN` |
| R1 service-worker reconstitution source | `BUILT_NOT_PROVEN` |
| T1 transport hardening | `BUILT_NOT_PROVEN` / repair active / unprotected at freeze |
| Context-rotation source law | `SPEC_ONLY` |
| Existing Macro Provider Capacity v1 | `BUILT_NOT_PROVEN` for Executive placement / accepted provider projection source |
| Automatic Executive capacity-aware placement | `NOT_BUILT` / gated by current CF2 sequence |
| ChatGPT-Web capacity realm in Provider Control | `NOT_BUILT` |
| Personal-Pro provider remaining/reset API | `NOT_BUILT` / no supported source accepted at freeze |
| Local exact Mastermind Pro-turn accounting | `NOT_BUILT` |
| Control Room ChatGPT-Web quota projection | `NOT_BUILT` |
| Private-endpoint/cookie quota scraping | `REJECTED_BY_DESIGN` |
| Automatic cross-account quota failover | `REJECTED_BY_DESIGN` for this program |

## 18. Completion standard

This program is not complete when a counter increments. It is complete only when:

- **Truth:** each realm's evidence is correctly identified as local/provider/manual/estimated/unknown, reset freshness is correction-safe, and no unsupported provider source is used;
- **Intelligence:** Mastermind can estimate its own consumption/runway without presenting estimates as entitlement;
- **Product:** the Chairman can see which reasoning realms are healthy, scarce, exhausted, stale, or unknown without watching provider menus;
- **Control:** new-work planning can eventually consume accepted Capacity truth without account switching, duplicate effects, usage-limit evasion, or another scheduler;
- **Learning:** historical observations show useful Mastermind turns per provider epoch and forecast calibration error, without creating synthetic traffic merely to learn the limit.

Until those gates land, the truthful answer for unsupported Personal-Pro remaining quota is **UNKNOWN**, not a guessed weekly/monthly balance.