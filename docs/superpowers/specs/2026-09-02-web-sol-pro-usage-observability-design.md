# Web-Sol Pro Usage Observability — Architecture Freeze Candidate

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman operation:** `web-sol-pro-usage-observability-20260902-sol-001`  
**Parent product workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Capacity owner:** `WS:EXECUTIVE-CAPACITY-FABRIC` / Macro Shared AI Provider Control  
**Source law:** `docs/EXECUTIVE_WEB_SOL_USAGE_CAPACITY_LAW.md`  
**Protected Mastermind design base:** `162af533a4bcf380125895d225b6962987c3c582`  
**Macro review base:** `818451efac2c1a95917f6110fabb024054911356`  
**State:** `SPEC_ONLY / PRODUCTION_INERT`.

## 1. Product thesis

Mastermind is building a workforce whose scarce resource is not just tokens or dollars; it is high-quality frontier reasoning time distributed across paid provider realms. The Chairman should be able to hand the company work without manually remembering which ChatGPT account is close to a Pro allowance, when a reset happens, or whether a long conversation is failing because of context versus account quota.

The useful product is therefore not a browser counter. It is a truthful capacity instrument:

```text
bounded realm-local observations
+ supported provider quota/reset observations
+ source freshness/corrections
+ historical consumption learning
-> canonical Provider Control truth
-> eventual eligible-new-work planning
-> Control Room explanation
```

The moat is the learning layer above provenance: over repeated real epochs, Mastermind can learn how many useful Sol outcomes its own work produces per scarce provider allowance without falsifying provider entitlement or forcing synthetic usage.

## 2. Architecture decisions

### D1 — Web-Sol senses; Macro owns quota truth

Web-Sol may emit bounded source observations from its exact managed-browser realm. It does not persist canonical capacity state, choose another account, or rank providers.

Macro Shared AI Provider Control remains the owner that normalizes presence, health, cooling, quota and correction semantics into a versioned capacity projection.

### D2 — Browser profile is the capacity realm slot

The durable company identity is an opaque capacity slot bound to one Web-Sol adapter instance / managed-browser realm. It is not the provider's account id and carries no PII.

A future provisioning receipt should minimally bind:

```text
capacity_capability_id
web_sol_adapter_instance_id
managed_profile_fingerprint
realm_generation
bound_at
binding_source_digest
```

Only opaque company-local fingerprints are durable. `realm_generation` advances when the profile's authenticated provider realm is deliberately re-provisioned or may have changed; the prior provider quota observations become stale/invalid rather than being silently reused.

### D3 — Own activity, provider quota and forecast are separate objects

We will not build a scalar `remaining_pro_turns` field.

The system has three layers:

```text
ObservedUsageEvent
    exact facts about Mastermind-observed/governed activity

ProviderUsageObservation
    supported/manual provider-reported quota/reset evidence

CapacityEstimate
    advisory runway forecast derived from the first two plus history
```

A Product projection may join them but must preserve provenance.

### D4 — no private ChatGPT quota endpoint

Current public research did not establish a supported Personal-Pro quota API. Unofficial trackers demonstrate that private authenticated endpoints can exist, but that is not an accepted interface. We deliberately reject browser-session endpoint replay, cookie/token use, network interception and hidden metadata extraction.

The supported-source gate is part of architecture, not an implementation inconvenience.

### D5 — current Provider Capacity v1 remains frozen

`mastermind.provider_capacity.v1` is already accepted for existing provider realms and is in the CF2-H0/P0/CF2-I release sequence. It has a closed source-kind vocabulary and current semantic identity rules.

ChatGPT-Web capacity does not patch v1 in place. Provider Control will later choose a versioned vNext contract after the current baseline is stable enough to consume it lawfully.

## 3. Current-state ledger

| Capability | State | Design consequence |
|---|---|---|
| Web-Sol metadata probe (`content.js`) | `BUILT_NOT_PROVEN` | can be extended only through a reviewed closed observation, not generic page access |
| R1 service-worker reconstitution | `BUILT_NOT_PROVEN` | no usage observer may bypass its exact recovery generation |
| T1 transport hardening | `BUILT_NOT_PROVEN` / repair active | no extension/native-host implementation wave may overlap T1 before protection |
| Installed disposable Web-Sol | `NOT_BUILT` / proof issue open | Q2 browser implementation waits for installed substrate |
| Context rotation law | `SPEC_ONLY` | account quota and context succession remain orthogonal |
| Macro provider_capacity v1 | accepted existing projection | preserve; do not reopen for ChatGPT Web |
| Executive capacity-aware placement | `NOT_BUILT` | quota data cannot route jobs automatically yet |
| ChatGPT-Web Provider Control realm | `NOT_BUILT` | requires CAP-WEB-F0 architecture first |
| Supported Personal-Pro remaining/reset API | not established | exact provider headroom/reset defaults UNKNOWN |
| Private endpoint scraping | `REJECTED_BY_DESIGN` | no fallback |

## 4. Source observation contracts

These are architecture shapes for later review; they do not create a new canonical state store.

### 4.1 `mastermind.web_sol_usage_event.v1`

Purpose: one secret-free event that says what Mastermind can prove happened on its own exact browser realm.

Closed candidate shape:

```json
{
  "schema": "mastermind.web_sol_usage_event.v1",
  "event_id": "<opaque deterministic/idempotent id>",
  "adapter_instance_id": "<opaque>",
  "realm_generation": 4,
  "capacity_capability_id": "<opaque or null until provisioned>",
  "event_kind": "governed_submission",
  "reasoning_class": "sol_pro",
  "effect": "applied",
  "observed_at": "2026-09-02T08:00:00Z",
  "source_kind": "governed_action_receipt"
}
```

Closed initial vocabularies:

```text
event_kind:
  governed_submission | local_submission_observed | generation_started |
  generation_finished | usage_limit_observed | availability_reobserved

reasoning_class:
  sol_pro | sol | other | unknown

effect:
  none | applied | effect_unknown

source_kind:
  governed_action_receipt | bounded_local_observation | supported_provider_surface |
  manual_confirmation | unknown
```

Important constraints:

- `governed_submission` can claim `reasoning_class=sol_pro` only when the exact action contract selected that class.
- `local_submission_observed` is not automatically Pro-specific.
- no prompt, response, title, email, provider account id, raw URL, DOM text or raw provider error enters the event.
- a service-worker replay must not generate a second `event_id` for one governed operation.
- passive/manual browser events that cannot be made idempotent without a new durable browser store remain advisory or out of scope; do not create a Web-Sol ledger to fix them.

### 4.2 `mastermind.web_sol_provider_usage_observation.v1`

Purpose: bounded source evidence about provider quota/reset state, before Macro normalizes it.

Closed candidate shape:

```json
{
  "schema": "mastermind.web_sol_provider_usage_observation.v1",
  "observation_id": "<opaque>",
  "adapter_instance_id": "<opaque>",
  "realm_generation": 4,
  "capacity_capability_id": "<opaque or null>",
  "quota_class": "chatgpt_sol_pro",
  "plan_class": "personal_pro_20x",
  "window_type": "unknown",
  "window_duration_seconds": null,
  "limit": null,
  "used": null,
  "remaining": null,
  "used_percent": null,
  "reset_at": "2026-09-05T06:42:00Z",
  "availability": "available",
  "observed_at": "2026-09-02T08:00:00Z",
  "stale_after": "2026-09-02T08:30:00Z",
  "evidence": "manual_confirmed",
  "source_kind": "manual_confirmation"
}
```

Closed source/evidence classes must remain no stronger than the source:

```text
evidence:
  provider_reported | manual_confirmed | estimated | unknown

source_kind:
  supported_provider_api | supported_admin_api | supported_provider_surface |
  manual_confirmation | local_error_signal | unknown
```

`plan_class` is optional/nullable in implementation unless it can be established without provider PII or credential inspection. Current product labels such as `personal_pro_5x` / `personal_pro_20x` are descriptive entitlement classes, not account identity.

`local_error_signal` may establish an availability/exhaustion state only when a reviewed bounded non-content signal can classify it truthfully. A generic error boolean does not equal `usage_limit_observed`.

### 4.3 No provider observation from private authenticated requests

The following cannot populate `ProviderUsageObservation`:

```text
chatgpt.com/backend-api/* private endpoints
cookies/session tokens
copied OAuth/access/refresh tokens
DevTools/CDP network interception
chrome.webRequest/debugger
localStorage/sessionStorage
raw HTML/text scraping
provider response bodies
```

If no supported source exists, the correct provider observation is absent/UNKNOWN.

## 5. Canonical Provider Control vNext candidate

`CAP-WEB-F0` must decide the final contract, but the required semantic distinction is already frozen.

A vNext slot needs to represent both provider quota and Mastermind-only observed activity without pretending the latter is total provider usage. One candidate is:

```json
{
  "capability_id": "chatgpt_web_<opaque>",
  "provider": "chatgpt_web",
  "execution_surface": "supported_tool",
  "present": true,
  "enabled": true,
  "health": {},
  "cooling": {},
  "quota_horizons": [],
  "observed_activity": [
    {
      "metric": "mastermind_reasoning_submits",
      "reasoning_class": "sol_pro",
      "scope": "mastermind_observed_only",
      "count": 41,
      "epoch_ref": "<opaque>",
      "observed_through": "2026-09-02T08:00:00Z",
      "evidence": "exact_local"
    }
  ],
  "last_outcome": {}
}
```

This is illustrative, not permission to modify v1. `CAP-WEB-F0` may choose another versioned shape if it preserves the same truth boundaries and current consumers.

## 6. Epoch model

We need two independent epoch types.

### 6.1 Provider quota epoch

Anchored only by accepted provider evidence. Fields may include:

```text
provider_epoch_ref
quota_class
observed_reset_at
first_observed_at
last_observed_at
source/evidence
```

If provider reset time is unknown, there is no authoritative provider epoch boundary.

### 6.2 Mastermind observation epoch

A local analytical window for counting Mastermind-observed work. It may be aligned to a provider reset only when that reset is known. Otherwise it is explicitly local and must not be rendered as the provider's week/month.

At an observed provider reset boundary:

```text
old provider headroom -> stale
re-observe
new provider evidence -> new provider epoch
local Mastermind counter -> may begin a new linked observation epoch
```

No automatic `100% remaining` assertion occurs.

## 7. Deduplication and effect semantics

For a governed submission, the idempotency key must be inherited from the existing action/operation identity, not generated from prompt content.

Required cases:

| Case | Accounting |
|---|---|
| action rejected before browser/provider mutation | count 0 |
| exact accepted send receipt | count 1 local governed submission |
| response lost after possible send | `effect_unknown`; do not increment confirmed count and do not resend |
| service-worker/native restart after receipt | same event id, no second count |
| response stream has N chunks | still one submit |
| generation retries internally at provider/UI without a new accepted user submit | no extra local submit |
| human/manual submit with unknown model mode | generic local observation only if an allowed/idempotent observer exists |

Accounting correctness never justifies a retry.

## 8. Source precedence and correction

For the same field/horizon, prefer fresh sources in this order only when semantically comparable:

```text
supported provider API/surface
> manual provider confirmation
> bounded local error/availability observation
> estimator
> unknown
```

A later higher-quality observation may correct an older lower-quality record. Corrections append lineage/reference; they do not silently rewrite the historical evidence used by an earlier Executive claim.

Provider and local scopes remain orthogonal. A provider-reported `used_percent=60` does not overwrite `mastermind_observed_submits=41`; they describe different things.

## 9. Freshness policy

The exact stale budgets are implementation-time configuration owned by Provider Control. The design rules are:

- source-native timestamps are preserved;
- reserialization never refreshes an old observation;
- `reset_at` crossing makes pre-reset headroom stale even if its normal stale budget has not elapsed;
- a manual confirmation has a bounded freshness budget and cannot silently stay current for weeks;
- local action counters are historical facts, but an estimate derived from them has its own `evaluated_at` and confidence;
- profile realm-generation mismatch invalidates provider quota evidence immediately.

## 10. Estimation / intelligence layer

Only after enough real epochs exist may Mastermind compute advisory metrics such as:

```text
Mastermind-observed Pro submits per provider epoch
median and p90 observed submits before first usage-limit observation
useful accepted work outcomes per observed submit
elapsed Sol reasoning hours per provider epoch (when duration is lawfully observed)
forecasted Mastermind submits to exhaustion
forecast calibration error
unused capacity at reset (only when provider evidence supports it)
```

A forecast record must carry:

```text
model/version
training/evaluation window refs
inputs
estimate
interval/range
confidence
observed_at/evaluated_at
```

No LLM judgment is required to compute or rank a quota estimate. Deterministic statistical methods are preferred until enough observations justify a more complex model.

## 11. Control Room experience

The first useful view is a per-realm capacity card with explicit truth labels, not a dashboard full of invented precision.

Required states:

```text
AVAILABLE
SCARCE/LOW_CONFIDENCE
EXHAUSTED/COOLING
RESET_EXPECTED
STALE
UNKNOWN
AUTH_REQUIRED
SURFACE_UNUSABLE
```

Example composition:

```text
ChatGPT Web Realm A — Sol Pro
Availability             AVAILABLE
Mastermind Pro submits   41  [EXACT LOCAL]
Provider usage           UNKNOWN
Provider reset           Sep 5 23:42  [MANUAL CONFIRMED]
Forecast runway          18-27 submits  [ESTIMATED / LOW]
Last fresh observation   2m ago
```

The card should explain why a field is unknown rather than replacing it with `0` or `unlimited`.

## 12. Planning boundary

Until CF2-I and a later ChatGPT-Web capacity consumer are accepted, all usage observations are informational. They cannot place an Executive Job.

After those gates, Capacity may influence **new-work selection** only within already-lawful workers/models and under provider usage policy. It may rank a fresh available realm ahead of a scarce realm or reserve scarce frontier capacity.

It may not:

- move a started Attempt to another realm because quota is low;
- repeat an effect-unknown modification;
- create a second successor chat to escape a usage limit;
- select a lower-quality/unauthorized model merely because it has quota;
- turn Slack identities into worker/capacity identities;
- switch the Chairman's account/profile automatically;
- create a provider-specific scheduler.

## 13. Provider-plan matrix

The observer architecture must support heterogeneous cadence without hardcoding policy:

| Plan/surface | What may be known | Default if unsupported |
|---|---|---|
| Personal Pro 5x/20x Chat | visible/current provider allowances may differ by model; supported API not established | quota/reset UNKNOWN; local own-activity only |
| Business Standard/Premium Chat | workspace/model allowances can differ; admin analytics/settings may expose some fields | use only documented exact fields; do not infer Personal semantics |
| Enterprise/Edu | supported Admin API can expose some usage-limit settings | setting != live remaining unless documented |
| OpenAI API | organization API usage/billing | separate product; never substitute for ChatGPT subscription quota |
| Work/Codex | provider-native rate-limit windows may exist | separate quota class from ordinary Chat Pro |

One paid account can therefore have multiple independent quota classes. Do not use an account-level scalar `remaining_quota`.

## 14. Failure matrix

| Failure | Truthful result |
|---|---|
| supported quota API absent | provider quota UNKNOWN |
| private endpoint discovered | REJECTED source; no call |
| generic provider error visible | provider error present; usage-limit classification UNKNOWN |
| provider-supported reset observed | store timestamp + evidence + freshness |
| reset timestamp passes | old headroom STALE; reobserve |
| manual account change suspected | realm generation invalid; provider evidence UNKNOWN |
| mode selection cannot be proven | no Pro-specific increment |
| send effect unknown | preserve uncertainty; zero resend |
| stale provider quota | not capacity-eligible evidence for new automatic placement |
| percentage without limit | percentage may be shown; absolute remaining stays null |
| conflicting provider/manual values | preserve both + correction/disagreement until source precedence resolves |
| browser observer unavailable | local counter incomplete; provider truth unaffected |

## 15. Security model

The ideal source receipt is boring. It contains opaque ids, enums, counts and timestamps only.

Do not add Chrome permissions for `cookies`, `storage`, `webRequest`, `debugger`, `scripting`, clipboard, browsing history or generic navigation merely for quota telemetry.

Do not inspect prompt or response text. Do not use prompt hashes as event ids; even hashes can create content-derived linkage without need.

The native host may transport a bounded observation, but no new long-lived daemon, socket family, queue, retry store or quota database is created. Any future Provider Control ingestion transport must reuse an accepted bridge/transport or return for a separate architecture ruling.

## 16. Proof requirements

### Source-law proof

A static test must preserve the core redlines:

- Macro Provider Control owns canonical quota/cooling;
- Web-Sol does not create a quota DB/scheduler;
- v1 is not patched in place;
- unsupported/private endpoint/cookie/token/network interception paths are forbidden;
- unknown is not full/zero/unlimited;
- context exhaustion and quota exhaustion are distinct;
- no automatic cross-account failover;
- reset timestamp crossing does not assert a full refill;
- effect-unknown submissions are not resent for accounting.

### Disposable browser proof

Later Q2 needs two disposable managed profiles because one-profile tests cannot prove isolation. It must demonstrate that observations are bound to the exact profile-local adapter instance and cannot leak/cross to the other profile.

### Production proof

Do not force exhaustion. Production proof waits for naturally occurring usage/reset evidence and proves truthful transition through available/scarce/exhausted/reset/stale states as those states become observable.

## 17. Architecture freeze

The following decisions are frozen for implementation waves unless Sol explicitly amends them after new provider evidence:

1. Web-Sol is a sensor, not canonical quota owner.
2. Macro Shared AI Provider Control remains canonical capacity owner.
3. managed browser realm is an opaque slot, not provider account PII.
4. local observed activity != provider total usage != estimated runway.
5. no universal weekly/monthly/billing-reset rule.
6. current `mastermind.provider_capacity.v1` is not patched in place for ChatGPT Web.
7. no private ChatGPT backend, cookie/token, storage or network-interception quota source.
8. unsupported Personal-Pro provider remaining/reset stays UNKNOWN unless manually confirmed.
9. context succession is not quota failover.
10. no started/effect-unknown operation is duplicated across accounts.
11. Control Room must label provenance/freshness explicitly.
12. later planning applies only to eligible new work and must preserve provider usage policy.