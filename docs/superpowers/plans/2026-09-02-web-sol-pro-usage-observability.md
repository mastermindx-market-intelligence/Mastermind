# Web-Sol Pro Usage Observability — Release Plan

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Chairman operation:** `web-sol-pro-usage-observability-20260902-sol-001`  
**Source law:** `docs/EXECUTIVE_WEB_SOL_USAGE_CAPACITY_LAW.md`  
**Design:** `docs/superpowers/specs/2026-09-02-web-sol-pro-usage-observability-design.md`  
**Protected Mastermind base:** `162af533a4bcf380125895d225b6962987c3c582`  
**Macro review base:** `818451efac2c1a95917f6110fabb024054911356`  
**Current state:** `SPEC_ONLY / PRODUCTION_INERT`.

## 0. End mission

The end product lets the Chairman see, per exact ChatGPT Web realm:

- what Mastermind itself has definitely used;
- what the provider has actually reported about quota/headroom/reset;
- how fresh that evidence is;
- what is merely estimated;
- whether the realm is healthy, scarce, exhausted/cooling, stale, or unknown;
- eventually, whether one **new, not-yet-started** eligible task should preserve scarce frontier capacity for later work.

Completion requires real provider/account observations and a useful Control Room projection. A merged counter or source schema is not completion.

## 1. Program boundaries

This plan extends two existing owners without merging them:

```text
WS:CHAIRMAN-CONTROL-ROOM
    owns Web-Sol source observation/product projection

WS:EXECUTIVE-CAPACITY-FABRIC
    owns canonical Provider Control capacity normalization and eventual placement use
```

The Mastermind carrier freezes the Web-Sol/product side first. A later Macro operation updates Agent OS and Provider Control only after this source law is accepted; do not maintain two live architecture carriers for one unresolved design.

Current Web-Sol T1 PR #308 remains a hard implementation collision boundary for extension/native-host files. Current CF2-H0/P0/CF2-I remains a hard boundary for the existing `mastermind.provider_capacity.v1` consumer path.

## 2. Wave DAG

```text
WSX-Q0 source law / architecture / plan
    |
    +--> WSX-QF0 supported-source + UI falsifier (research/proof)
    |
    +--> WSX-Q1 local observed-usage source contract
    |       |
    |       +--> waits for T1 protection + INSTALL1 disposable substrate
    |               |
    |               +--> WSX-Q2 bounded metadata observer
    |
    +--> CAP-WEB-F0 Provider Control vNext architecture
            |
            +--> waits for accepted current CF2 baseline / no v1 collision
                    |
                    +--> CAP-WEB-1 Provider Control implementation
                            |
                            +--> CR-Q1 Control Room capacity cards
                                    |
                                    +--> Q-D1 disposable end-to-end
                                            |
                                            +--> Q-PROD1 real observation proof
```

`WSX-QF0`, `WSX-Q1`, and `CAP-WEB-F0` may proceed as source/research waves in parallel only when their changed paths and authority owners are disjoint. No browser/Provider Control runtime mutation begins merely because their documentation is complete.

## 3. WSX-Q0 — architecture freeze

### Observable mission

Protect one reviewed source law and design that prevents Web-Sol quota observability from becoming a browser scraper, a second quota store, or a cross-account failover mechanism.

### Files

- `docs/EXECUTIVE_WEB_SOL_USAGE_CAPACITY_LAW.md`
- `docs/superpowers/specs/2026-09-02-web-sol-pro-usage-observability-design.md`
- `docs/superpowers/plans/2026-09-02-web-sol-pro-usage-observability.md`
- `tests/test_web_sol_usage_capacity_source_law.py`

### Acceptance

- source-law static test passes;
- current Web-Sol/Capacity owner paths are unchanged;
- current `mastermind.provider_capacity.v1` is unchanged;
- no browser/provider/Executive/runtime effect;
- independent review confirms no private-endpoint/account-switch/limit-evasion authority;
- protected merge is records/source-law only and remains `SPEC_ONLY`.

### Stop condition

Stop after reviewed source protection. Do not begin extension implementation on this carrier.

## 4. WSX-QF0 — supported-source and visible-product falsifier

### Observable mission

Determine what OpenAI actually and lawfully exposes today for each relevant ChatGPT plan/model quota class without turning the experiment into automated data extraction.

### Preferred avenue

`CTO Sol` or another browser-capable research session. `WHY NOT FABLE`: the product/authority architecture is frozen; this is bounded provider research and disposable UI evidence.

### Exact environment

Use disposable/non-sensitive managed profiles or normal user-visible product surfaces. No production Mastermind mutations, no quota-driving synthetic traffic, and no private endpoint calls.

### Research matrix

For each plan actually available to the company:

```text
Personal Pro 5x
Personal Pro 20x
Business Standard
Business Premium
Enterprise/Edu only if lawfully available
```

For each relevant reasoning/model class, capture only the following closed conclusions:

```text
SUPPORTED_API
  YES | NO_DOCUMENTED_SOURCE_FOUND | UNKNOWN

VISIBLE_RESET
  EXACT_TIMESTAMP | RELATIVE_TIME | CADENCE_ONLY | NOT_VISIBLE | UNKNOWN

VISIBLE_HEADROOM
  ABSOLUTE_COUNT | PERCENT | USED_ONLY | NONE | UNKNOWN

WINDOW_TYPE
  ROLLING | FIXED | BILLING_CYCLE | UNKNOWN

DOCUMENTED_CADENCE
  FIVE_HOUR | WEEKLY | MONTHLY | MODEL_SPECIFIC | WORKSPACE_SPECIFIC | UNKNOWN

MACHINE_READABLE_SUPPORTED_SOURCE
  PROVIDER_API | ADMIN_API | PROVIDER_SUPPORTED_SURFACE | NONE | UNKNOWN
```

Record official documentation URL/title/date and screenshots of user-visible quota/reset controls only when privacy-safe. No email/account id, cookie/storage, hidden DOM, transcript, prompt, response or private API response enters evidence.

### Required negative checks

Prove that:

- a normal OpenAI API usage dashboard is separate from ChatGPT subscription allowance;
- Business/Enterprise admin usage-limit settings are not silently current per-model remaining quota;
- subscription billing renewal is not assumed to be reset time;
- one plan's weekly/monthly cadence is not generalized to another;
- discovering an undocumented endpoint does not authorize calling it.

### Acceptance

One secret-safe evidence packet with a typed row for every actually tested plan/model class and explicit UNKNOWN for all untested/unavailable fields.

### Stop condition

Return to Sol before any automated quota acquisition implementation. A newly documented provider API may change CAP-WEB-F0 design.

## 5. WSX-Q1 — local observed-usage contract

### Observable mission

Freeze exactly what Mastermind can count about its own Web-Sol activity without claiming total account usage.

### Scope

Records/schema/validator only. Do not touch `content.js`, `background.js`, native host, Chrome manifest, provider capacity v1, or deployment.

### Required contract behavior

Implement/validate the candidate `mastermind.web_sol_usage_event.v1` only if review confirms it can reuse an existing source-event/receipt transport without creating a new durable queue/ledger.

The contract must:

- use opaque adapter/realm ids;
- inherit idempotency from existing action identity where possible;
- distinguish generic local submission from known `sol_pro` submission;
- preserve `effect_unknown` without retry;
- contain zero prompt/response/account PII/browser credential data;
- forbid deriving provider remaining quota from local counts;
- make duplicate/replay events deterministically reject or dedupe at the canonical ingestion owner.

### Critical implementation decision

If exact-once passive/manual browser submission counting requires a new Web-Sol durable store, **do not build it in Q1**. Keep passive/manual counting out of the exact contract and return to Sol. The first exact counter may cover only governed Mastermind actions whose existing operation identity provides idempotency.

### Acceptance

Hostile tests prove double callbacks, service-worker restart, same operation replay, unknown reasoning mode, and effect-unknown do not create false Pro counts.

## 6. CAP-WEB-F0 — Provider Control vNext architecture

### Observable mission

Extend the canonical Shared AI Provider Control design to represent ChatGPT Web attached-browser capacity realms without changing the currently accepted v1 semantics or consumer release sequence.

### Repository

`mastermindx-market-intelligence/macro`

### Authority

Existing `WS:EXECUTIVE-CAPACITY-FABRIC` and `DEC:EXECUTIVE-CAPACITY-FABRIC-OWNERSHIP-AND-CONTRACT` remain parent authority.

### Required rulings

Freeze:

1. opaque `capacity_capability_id` for one managed-browser realm;
2. binding to Web-Sol adapter instance/profile fingerprint without PII;
3. realm-generation/re-auth invalidation semantics;
4. source ingestion boundary for `web_sol_usage_event` and provider usage observation;
5. source precedence/freshness/correction behavior;
6. separate `observed_activity` versus provider `quota_horizons` semantics;
7. versioned Provider Control contract evolution (`v2` or another explicitly reviewed version), not an in-place v1 semantic patch;
8. exact compatibility story for existing CF2 consumers;
9. no new daemon/DB/queue/scheduler;
10. no provider credential access transferred to Mastermind/Web-Sol.

### Acceptance

Architecture review can explain how current v1 consumers continue unchanged while vNext is added and how an unknown Personal-Pro quota remains unknown end-to-end.

### Stop condition

No Macro runtime implementation until current CF2 baseline collision is resolved and the vNext design is independently accepted.

## 7. WSX-Q2 — bounded Web-Sol observer

### Hard dependencies

All must be true before START:

1. WSX-Q0 source law protected;
2. WSX-Q1 contract accepted if used;
3. T1 PR #308 (or successor exact source carrier) protected on current master;
4. INSTALL1 has produced an accepted disposable installed generation with profile isolation and rollback proof;
5. no active PR owns the same extension/native-host paths;
6. source acquisition being implemented is permitted by QF0 and current provider policy;
7. no new Chrome permission is required outside the accepted closed surface unless a separate amendment is reviewed first.

### Observable mission

Produce one exact profile-bound secret-free usage event from a governed action and/or the narrowest permitted bounded metadata observation, carry it through the existing profile-local transport, and prove zero content/account leakage.

### Non-goals

No:

- quota menu scraping;
- private provider API;
- cookie/token/storage/network reads;
- generic click/type/send/navigation;
- account/model switching;
- local quota DB;
- retry queue;
- Provider Control normalization;
- Control Room UI.

### Failure proof

Inject service-worker restart, native disconnect, duplicate callback, unknown model mode, stale profile realm generation, wrong-profile transport, and possible-send/lost-receipt. Confirm zero double count and zero replay.

## 8. CAP-WEB-1 — Provider Control implementation

### Dependencies

- accepted CAP-WEB-F0;
- current CF2 baseline no longer in a state where the change would silently alter v1 claim semantics;
- accepted source observation producer/transport;
- exact Macro current source re-pinned at implementation time.

### Observable mission

Ingest one secret-free ChatGPT-Web realm source, normalize it under the accepted versioned contract, and expose exact/unknown/estimated fields truthfully to a real machine consumer.

### Required source behavior

- local activity counters are `mastermind_observed_only`;
- provider quota fields remain null when unavailable;
- `reset_at` crossing stales old headroom;
- realm-generation mismatch invalidates provider evidence;
- supported provider source outranks manual/estimate only for comparable fields;
- historical corrections preserve lineage;
- no old provider source timestamp is restamped as fresh.

### Production proof

Use a disposable or approved read-only realm observation. No provider call solely for proof and no forced quota exhaustion.

## 9. CR-Q1 — Control Room product projection

### Observable mission

A Chairman can answer, in seconds:

```text
Which Web-Sol realms are currently usable?
Which are scarce or exhausted?
How many Pro submissions has Mastermind itself observed this epoch?
What reset is actually known, and from what source?
Which numbers are estimates?
How stale is the evidence?
```

### Required UI states

- loading;
- supported provider evidence fresh;
- only local activity known;
- provider quota unknown;
- stale evidence;
- exhausted/cooling with known reset;
- exhausted/cooling with unknown reset;
- auth required;
- profile realm invalidated;
- provider source unsupported;
- forecast unavailable due insufficient history.

### UX redline

Never hide UNKNOWN behind `0`, `100%`, `unlimited`, or a synthetic progress bar.

## 10. Q-D1 — disposable end-to-end proof

### Observable mission

Prove two disposable Web-Sol realms remain isolated while local activity and provider observations travel to canonical Provider Control and project correctly.

### Matrix

1. realm A one governed Sol-Pro submission -> A local count +1, B unchanged;
2. duplicate/replayed receipt -> no +2;
3. realm A provider reset manually confirmed -> A only;
4. realm B provider quota unknown -> remains unknown;
5. cross-profile observation -> rejected;
6. realm-generation bump -> previous provider evidence stale/invalid;
7. reset timestamp passes -> old headroom stale, no 100% refill assumption;
8. effect-unknown send -> no blind repeat;
9. generic provider error -> no usage-limit classification without accepted signal;
10. Control Room faithfully renders each source class.

No automatic placement is required by Q-D1.

## 11. Q-PROD1 — production observation proof

### Observable mission

On approved real company realms, prove the same read-only observation lifecycle over natural usage.

### Minimum acceptance

- two distinct real realm slots or one real realm across two naturally occurring evidence epochs;
- at least one exact Mastermind activity count;
- at least one supported/manual provider reset/headroom observation if available, otherwise explicit provider UNKNOWN remains accepted;
- no leaked PII/credential/content;
- no account switch;
- no forced exhaustion;
- no duplicate provider effect;
- durable correction/freshness behavior proven;
- Control Room usable by Chairman.

The program may reach useful production state with provider remaining quota UNKNOWN if OpenAI exposes no supported source; local usage/cooling/reset observations must remain truthful.

## 12. Future planning integration (held)

Only after canonical ChatGPT-Web capacity exists and the Executive Capacity Fabric consumer is accepted may a later wave use it for new-work planning.

The future policy may:

- prefer fresh available subscription capacity over metered overflow where suitability is equal;
- reserve a scarce high-quality realm for interactive/critical work;
- avoid assigning a new long mission to a known exhausted/cooling realm;
- wait for a known reset when policy says delay is better than lower-quality execution.

It may not:

- evade a provider rate/usage limit;
- rotate accounts to continue the same blocked operation;
- move a started/effect-unknown Attempt;
- choose an unauthorized model/provider;
- create a second lifecycle/scheduler;
- infer quota from Slack identity or browser title.

This planning integration requires its own current-policy review and is not authorized by this plan.

## 13. Program acceptance table

| Wave | Capability after acceptance | Still not proven |
|---|---|---|
| WSX-Q0 | frozen architecture/source law | observer, Provider Control, UI |
| WSX-QF0 | current supported-source evidence | automated collection |
| WSX-Q1 | local usage event contract | installed source event |
| CAP-WEB-F0 | versioned Provider Control design | implementation |
| WSX-Q2 | real bounded source observation | canonical capacity normalization |
| CAP-WEB-1 | canonical ChatGPT-Web capacity truth | Chairman UI / planning |
| CR-Q1 | useful capacity UI | end-to-end live correctness |
| Q-D1 | disposable end-to-end | real production evidence |
| Q-PROD1 | production observation lifecycle | automatic new-work planning unless separately approved |

## 14. Exact next action after WSX-Q0 protection

Run **WSX-QF0**, not extension implementation. The most important unknown is provider-source legality/capability: if OpenAI has a supported per-account quota/reset surface we should design around it; if it does not, Personal-Pro exact remaining/reset must stay UNKNOWN and Q2 should focus on local activity/error availability only.

Return to Sol immediately if:

- current OpenAI policy materially changes the collection boundary;
- an official supported Personal-Pro quota API is found;
- T1/INSTALL1 architecture changes Web-Sol transport/permission assumptions;
- current Capacity Fabric evolves its provider contract before CAP-WEB-F0;
- a source observation would require private credential/session access;
- exact passive browser counting cannot be made idempotent without a new store.