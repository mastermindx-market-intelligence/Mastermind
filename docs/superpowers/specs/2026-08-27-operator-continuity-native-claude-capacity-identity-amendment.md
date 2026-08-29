# Operator Continuity — Native Claude Execution Realms Need Canonical Capacity Identity

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This closes a cross-owner identity mismatch found during Sol review of the five-subscription pool design.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Current protected review basis:** `65d5f07eb7667304c50c9673c61b9a0a6b95d3f3`, compatible Skillpack v1.0.0 / bootstrap major 1.  
**Existing owners preserved:** Macro Shared AI Provider Control / `mastermind.provider_capacity.v1`; `WS:EXECUTIVE-CAPACITY-FABRIC`; Executive Worker realm/placement law.

## 1. Mismatch found

Current Macro `mastermind.provider_capacity.v1` enumerates Claude capacity capabilities such as:

```text
claude_code_oauth
claude_code_oauth_1 ... claude_code_oauth_7
```

Those slots are owned by Macro's existing OAuth/token-based provider lanes and are discovered/observed under that source law.

The approved first Executive Claude Worker path is different:

```text
native Claude subscription login
+ dedicated Worker host/OS principal
+ Claude-owned credential realm / Keychain on macOS
+ opaque Executive account/realm label such as claude-pro-01
```

A native Executive Claude realm is therefore **not automatically identical** to a Macro `claude_code_oauth_N` capability merely because both use Claude subscriptions or an ordinal looks similar.

## 2. Frozen ruling

Do not join native Claude Worker capacity by:

- matching `claude-pro-01` to `claude_code_oauth_1` by number;
- matching Slack/app names such as Claude5;
- matching environment variable names;
- assuming five Macro OAuth secrets are the same five native logins;
- using provider/model name alone;
- treating native auth readiness as exact quota/headroom truth.

Before a native Claude Worker realm participates in **capacity-aware automatic placement**, Executive Capacity Fabric needs a reviewed `capacity_capability_id` whose provider-capacity evidence truthfully belongs to that same paid subscription/capacity realm.

## 3. Two lawful architecture families to falsify

### Family A — same-subscription capacity twin

Use an existing Macro Provider Control capability only if a bounded provisioning/verification ceremony can prove that:

```text
native Worker realm R
and Macro capacity capability C
consume the same provider subscription quota realm
```

without exposing/storing provider account PII or credential values.

The durable Mastermind binding may store only the existing opaque Worker/account label plus existing `capacity_capability_id`/host evidence required by CF2 law. It must not create a second account ID.

The proof must also define **rotation invalidation**: if the Macro credential behind C is replaced/re-enrolled, the prior R<->C equivalence cannot remain silently authoritative unless the existing Provider Control capability identity itself guarantees stable account semantics. If current Macro secret slots cannot make rotation drift detectable, Family A is not production-safe.

### Family B — native-realm Provider Control observation

Evolve the existing Shared AI Provider Control owner so native Claude Worker realms are represented directly in a reviewed versioned provider-capacity contract. Macro remains the sole provider-capacity normalizer/semantic-hash owner; Executive consumes the new accepted projection and does not create its own quota table.

This may require a new provider-capacity schema/version and a corresponding bounded CF2 consumer evolution. It must preserve:

```text
unknown quota != unlimited
freshness/null semantics
host/auth realm separation
secret-free evidence
provider outcome/cooling truth
one canonical normalizer
```

Do not fork `mastermind.provider_capacity.v1` logic inside Mastermind merely to avoid a versioned cross-repo contract change.

## 4. V1 sequencing consequence

Current CF2-H0/P0/CF2-I work for its already-frozen realm set continues independently and must not be reopened merely because Operator Continuity needs native Claude realms later.

PF1 may prove **one exact Claude provider vertical/Worker** under its accepted bounded proof law when the Worker is explicitly provisioned and claimed through a reviewed test/acceptance path. That does not make all native Claude realms generally capacity-routable.

Before OCR-5 automatic Claude realm A -> realm B selection and before OCR-8 calls the five subscriptions a real pool, the new OCR-2C capacity-identity wave must be accepted for the participating native Claude realms.

## 5. Capacity evidence may remain partially unknown

A native Claude capacity contract does not need to invent exact remaining quota if Anthropic does not expose it safely before a turn.

It may truthfully carry:

```text
present/auth readiness
health
last provider outcome
cooling/reset evidence when provider-reported
quota horizon = unknown when unobservable
```

CF2/Model Router may still deterministically select among eligible available realms according to accepted unknown/null semantics. A rate-limited realm becomes unavailable/cooling through reviewed provider outcome evidence. Unknown headroom is never interpreted as full headroom.

## 6. Provider-status/worker observations

Provider-native statusline, response metadata, auth status or worker-broker observations may be useful **source observations**, but they do not become a second normalizer. If Family B uses them, define a bounded secret-free observation wire into Shared AI Provider Control and keep normalization/versioning in Macro.

A Worker/adapter may report one exact provider outcome associated with its own realm; it may not rank providers, set another realm cooling or modify Executive placement itself.

## 7. No-rebuild proof

This amendment does not authorize:

- a Mastermind-native quota database;
- a `claude_capacity.json` side ledger;
- ordinal account matching;
- a new provider scheduler;
- secret/account fingerprint persistence;
- direct Executive reads of Macro OAuth token values.

The gap is resolved by exact identity proof to the existing owner or by evolving that owner, not by adding a parallel capacity plane.
