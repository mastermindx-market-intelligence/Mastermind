# OCR-2C Family B — Multi-Host Quota-Domain Amendment

**Date:** 2026-09-15  
**Parent operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Narrow precedence:** this amendment supersedes the parent Family-B records wherever they overload `realm_generation`, introduce a separate `binding_generation`, use `capacity_generation` as the Macro provider-domain epoch, route B5 through the canary-only `CapacityOwnerFact`, imply one native capacity capability can have only one host binding, or direct B1 native registration into the unrelated secret-reference capability manifest.

## Why this amendment exists

Mastermind-X is becoming a multi-Mac fleet. One direct Claude subscription may intentionally be usable from more than one physical Mac, while every such host realm still consumes the **same provider quota/cooling domain**. Conversely, a host-local Claude failure should not automatically make a healthy realm of the same subscription on another Mac unusable.

The accepted Capacity F0/CF2 architecture already anticipated this. Slot identity is `(host_ref, capability_id)`; host identity is opaque; and provider capacity truth is joined to private worker-realm readiness at claim time rather than normalized again in Executive.

Fresh current-source archaeology also resolves two draft ambiguities:

1. protected Mastermind already has distinct provider-realm and canary-Capacity generations; and
2. `CapacityOwnerFact` is a subscription-canary activation fact, **not** the accepted CF2 production placement/claim contract.

Family B must extend those owners rather than create new generation or placement planes.

## Frozen owner model

```text
capacity_capability_id + capability_generation
    = Macro Shared AI Provider Control logical provider capacity / quota domain

host_ref + capacity_capability_id + realm_generation
    = Mastermind provider-realm owner's current executable enrollment/custody of that domain on one host

CapacityOwnerFact.generation  (subscription-canary field: capacity_generation)
    = existing Mastermind canary Capacity/Model Router fact generation
    = NOT provider subscription identity and NOT the CF2 production claim generation
```

These values must never be aliased merely because all are integers.

### `capability_generation`

Owned by Macro Shared AI Provider Control. It changes only when the logical provider-capability domain represented by `capacity_capability_id` is deliberately replaced/redefined or a current registration is revoked/re-enrolled as a new provider-domain generation.

Ordinary token refresh, Claude binary update, host reboot, Capacity fact refresh, or replacement of one host realm does not advance `capability_generation`.

The name is deliberate: protected Mastermind already uses `capacity_generation` for a different canary fact.

### `realm_generation`

Owned by the existing provider-realm owner. Protected source already seals `ProviderRealmEnrollmentReceipt.generation` and exposes it through `mastermind.subscription_canary_admission/v1` as `realm_generation`.

Family-B V2 extends that owner to bind exact host/principal/config custody. Realm generation advances when the local executable enrollment is deliberately replaced/re-provisioned. There is no new `binding_generation` owner.

A stale realm generation cannot START work even if the provider capability generation is current.

### Existing `capacity_generation`

Protected `CapacityOwnerFact.generation` is minted by the current Capacity/Model Router seam and consumed by the interactive subscription-canary admission path. Current code search finds it in the owner fact, its minting seam, subscription canary admission and tests—not in the accepted CF2 production claim path.

Family B therefore does **not** promote `CapacityOwnerFact` into provider-domain identity or production placement authority. If a later bounded native Claude canary continues to use `subscription_canary_admission`, its `capacity_generation` retains exactly its existing canary meaning.

If a future canary admission must bind Provider Capacity V2 provenance, evolve that admission through a reviewed versioned successor rather than repurposing `CapacityOwnerFact.generation`.

## Binding rule for account replacement on one host

If a host intentionally moves from logical Claude subscription A to logical subscription B:

```text
old host/A realm enrollment -> revoke or supersede
host binds to B's capacity_capability_id/current capability_generation
new realm_generation for that host/B enrollment
```

Do not advance A's capability generation merely because one replica moved to B. Advance it only when logical provider-capability domain A itself is replaced/redefined.

Provider surfaces still cannot safely prove account equality from ordinary auth status. This remains a managed provisioning invariant, not a PII-derived identity claim.

## Provider-realm enrollment V2 correction

```text
schema = mastermind.provider_realm_enrollment/v2
capacity_capability_id
capability_generation
realm_generation
provider_family = anthropic
product = claude-code
execution_surface = native_cli
auth_family = claudeai_subscription
host_ref
os_principal_ref
config_custody_ref
enrollment_state = enrolled | unenrolled
registration_receipt_digest
source_receipt_digest
receipt_id
receipt_digest
```

`registration_receipt_digest` is the canonical B1 registration digest. The withdrawn `capacity_identity_receipt_digest` name has no alias or mapping and must be rejected.

Macro Provider Control supplies `capacity_capability_id + capability_generation`. The existing provider-realm owner supplies/seals `realm_generation + host/principal/config custody`. Neither side mints a competing account identity.

Existing V1 realm receipts remain valid for existing consumers; V2 is additive.

## Boot currentness composes after stable enrollment

`boot_ref` is the existing FP1B/host-capacity boot-generation reference. It is not a fourth Family-B generation and does not enter B2 enrollment identity. An ordinary reboot changes current physical readiness, not the logical provider domain or the enrolled host/principal/config realm; therefore reboot alone advances neither `capability_generation` nor `realm_generation`. B3/B4 readiness is bound to exact current `boot_ref`, and old-boot readiness is ineligible for new work after reboot.

## Preserve the accepted slot and CF2 join law

Native Claude V2 executable slot identity remains:

```text
(host_ref, capacity_capability_id)
```

The same `capacity_capability_id + capability_generation` may appear on several hosts, with one current `realm_generation` per host/capability pair. Those rows are execution realms, not separate quota pools.

The accepted CF2 production architecture remains the model for B5:

```text
strict Macro Provider Capacity snapshot
        +
boot-bound realm-local readiness / provider-realm evidence
        +
incumbent FP1B physical qualification and fresh host evidence
        |
        v
immutable (host_ref, capacity_capability_id) join
+ exact host_ref/boot_ref composition with FP1B host_id/boot_id
        |
        v
Mastermind strict consumer + deterministic rank of already-lawful candidates
        |
        v
existing atomic claim / immutable capacity evidence
```

Family B V2 extends that acquisition/join/claim-evidence path. It does not replace it with `CapacityOwnerFact` and does not create a second scheduler or capacity normalizer.

## Shared quota domain vs host-local readiness

### Provider-domain scoped

Facts belong to `capacity_capability_id + capability_generation` only when source semantics prove provider/account-domain scope:

- provider quota horizons;
- provider/account usage-limit cooling;
- provider-wide account/auth revocation;
- provider-wide health evidence.

### Realm/host scoped

Realm enrollment facts belong to `(host_ref, capacity_capability_id, realm_generation)`; current readiness facts additionally bind exact `boot_ref`:

- Claude binary/install readiness;
- local credential/auth readability;
- config/principal mismatch;
- host transport/broker availability;
- host recovery readiness;
- browser/computer-use resource readiness;
- host-local process/runtime failure.

Unknown scope remains unknown/degraded; it is never broadened by convenience.

## Provider Capacity V2 projection

```text
capability_id = capacity_capability_id
host_ref = exact opaque host
realm_binding = {
  capability_generation,
  boot_ref,
  realm_generation,
  enrollment_receipt_digest
}
```

The earlier per-row `capacity_independence = verified | unknown` proposal is withdrawn. Cross-domain independence is relational and Family B V2 makes no fleet-total numeric Max entitlement claim.

Quota aggregation key:

```text
(capacity_capability_id, capability_generation)
```

Execution realm and current-readiness keys:

```text
execution realm = (host_ref, capacity_capability_id, realm_generation)
current readiness = (host_ref, boot_ref, capacity_capability_id, realm_generation)
```

No consumer may sum host rows to estimate quota.

## B1 native registration owner correction

Current Macro `config/capability_manifest.yml` is a `capability_manifest.v1` **secret-reference broker** owned by `metabolism-phase0`; its rows contain `secret_ref` and lane/tier policy. A native attached-login registration has different semantics and must not be forced into that manifest merely because Capacity F0 reads it as one existing source.

B1 must use a reviewed, versioned, **secret-free** native Provider-Control registration surface inside `shared-ai-provider-control` (or an exact current successor proven to own the same fact). It may contain opaque provider-capability id/generation, provider/billing/execution classification, registration state and material-source receipt—never credential bytes, a secret-ref name, host binding, raw config path, provider account PII or Worker identity.

This is not permission to build an account database.

## B5 consumer/claim correction

B5 must not manufacture a new “Capacity owner fact bridge” simply because `CapacityOwnerFact` exists elsewhere. Its production mission is:

1. acquire/validate the accepted `mastermind.provider_capacity.v2` through a bounded successor of the current CF2 source-acquisition contract;
2. validate current provider-realm V2 enrollment and boot-bound readiness through the existing owner boundary;
3. separately consume the incumbent FP1B physical qualification/result and its fresh host-capacity/pressure evidence;
4. join at exact `(host_ref, capacity_capability_id)`, verify `capability_generation + realm_generation`, and require byte-exact `host_ref == host_id` plus `boot_ref == boot_id`;
5. require current `capacity_pool_ref`, `qualification_revision` and accepted physical freshness before provider claim/BEGIN consumption;
6. rank only already-lawful candidates under the existing Model Router/Capacity policy;
7. bind provider evidence and the existing FP1B evidence separately into the **existing CF2 claim/placement and ResourceBroker path**;
8. preserve historical replay without re-reading current provider or physical state.

The current interactive `SubscriptionCanaryAdmission` may remain a separate B6/B7 activation canary if still useful. It does not become production placement authority.

## Cooling propagation law

```text
provider-domain usage_limit/account cooling
    -> every current realm of that provider-capability domain is ineligible for new work

host A auth/binary/transport/recovery failure
    -> only host A realm degrades; host B may remain eligible

unknown scope
    -> preserve unknown/degraded; do not propagate by guess
```

Provider Control owns provider-scope normalization; the Claude adapter does not propagate cooling.

## Initial four-domain canary and later fleet replication

First prove four intended Max provider-capability domains with **one accepted host realm each**. Only later attach additional M1/M6/Studio realms to an accepted domain.

Later replication must prove:

```text
same capacity_capability_id + capability_generation
new distinct host_ref
new realm_generation and custody receipt
shared quota evidence is not duplicated as additive capacity
host-local failure affects only the failing realm
provider-domain usage-limit affects every replica
```

## Required mutation/falsifier tests

The implementation must kill at least:

```text
same provider domain on two hosts counted twice in fleet quota
host A auth failure cools host B without domain-scoped evidence
account usage-limit cools only the reporting host when scope is proven domain-wide
stale realm generation accepted under current capability generation
stale capability generation accepted under fresh realm generation
host B receipt substituted for host A
pre-reboot readiness accepted after boot_ref changes
reboot advances provider or realm generation instead of only readiness currentness
Provider Capacity boot_ref treated as FP1B admission authority
provider host_ref/boot_ref mismatches FP1B host_id/boot_id
wrong/stale capacity_pool_ref or qualification_revision accepted
stale/incomplete host-capacity or mismatched pressure evidence accepted
physical failure widened to provider-domain cooling
historical replay re-reads current physical state
one host re-provisioned to logical account B while retaining account A capability identity
capability generation increment forces unrelated realm generation increment
realm generation increment silently creates a new quota domain
Macro capability_generation confused with canary CapacityOwnerFact capacity_generation
CapacityOwnerFact substituted for Provider Capacity V2 claim evidence
caller forges provider capability id or generation
replay re-reads current provider capacity instead of returning historical claim evidence
```

## Implementation-plan supersession

This amendment has narrow precedence over the candidate implementation plan wherever that plan says:

- Macro provider domain = `capacity_capability_id + realm_generation` or provider-domain `capacity_generation`;
- host custody = `binding_generation`;
- native observation is keyed by `capacity_capability_id + realm_generation`;
- `realm_binding` contains provider-domain `capacity_generation`, `binding_generation`, or `capacity_independence`;
- B1 should default native registration into metabolism `capability_manifest.v1`;
- B5 should export an existing `CapacityOwnerFact` as the production placement bridge.

Read those locations as `capacity_capability_id + capability_generation`, incumbent `realm_generation`, secret-free Shared AI Provider Control registration, and the canonical CF2 V2 acquisition/join/claim-evidence path above.

## No effect

This amendment changes only architecture records. It creates no capability registration, credential, host realm, provider call, quota observation, Capacity fact, RuntimeBinding, Worker, route, browser/GUI lease or host mutation.