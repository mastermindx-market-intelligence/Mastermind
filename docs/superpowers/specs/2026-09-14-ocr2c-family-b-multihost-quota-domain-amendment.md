# OCR-2C Family B — Multi-Host Quota-Domain Amendment

**Date:** 2026-09-14  
**Parent operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Narrow precedence:** this amendment supersedes the parent Family-B records wherever they overload `realm_generation`, introduce a separate `binding_generation`, use `capacity_generation` as the Macro provider-domain epoch, imply one native capacity capability can have only one host binding, or direct B1 native registration into the unrelated secret-reference capability manifest.

## Why this amendment exists

Mastermind-X is becoming a multi-Mac fleet. One direct Claude subscription may intentionally be usable from more than one physical Mac, while every such host binding still consumes the **same provider quota/cooling domain**. Conversely, a host-local Claude failure (binary missing, local auth unavailable, config custody broken, transport unavailable) should not automatically make a healthy binding of the same subscription on another Mac unusable.

The accepted Capacity F0 architecture already anticipated this. Slot identity is the pair `(host_ref, capability_id)`, not `capability_id` alone; host identity is opaque; and an attached subscription present on Mac A is not assumed callable on Mac B. Family B must preserve that law rather than collapse provider capacity identity and host execution custody into one generation.

Current protected Mastermind source also resolves the generation-owner ambiguity. The existing provider-realm owner already issues a sealed `ProviderRealmEnrollmentReceipt.generation`, exposed to consumers as `realm_generation`, while the Capacity/Model Router owner separately issues `CapacityOwnerFact.generation`, exposed by `subscription_canary_admission` as `capacity_generation`. Family B must extend those owners rather than inventing a third host-binding generation or silently changing what `capacity_generation` means.

## Frozen three-owner generation model

Family B uses **one Provider-Control capacity identity** and **zero second account identities**. It preserves three distinct correction generations because they have different canonical owners and meanings:

```text
capacity_capability_id + capability_generation
    = Macro Shared AI Provider Control logical provider capacity / quota domain

host_ref + capacity_capability_id + realm_generation
    = Mastermind provider-realm owner's current executable enrollment/custody of that domain on one host

CapacityOwnerFact.generation  (public canary field: capacity_generation)
    = existing Mastermind Capacity/Model Router fact generation for one worker-capacity observation
```

These values must never be aliased merely because all three are integers.

### `capability_generation`

Owned by Macro Shared AI Provider Control. It changes when the company deliberately replaces or redefines the logical provider-capacity domain represented by `capacity_capability_id`.

Examples that require a new capability generation:

- the company intentionally repoints that opaque provider-capability domain to a different direct subscription;
- the Provider-Control native registration for the domain is revoked and re-enrolled as a new current generation;
- a later accepted provider identity source proves the current domain membership has changed.

Ordinary OAuth/access-token refresh, a Claude Code binary update, host reboot, or re-creating one host's local custody does **not** change `capability_generation`.

The name is deliberate: current protected Mastermind already uses `capacity_generation` for the independent `CapacityOwnerFact.generation`. Family B must not reuse that existing field name for a different cross-repository epoch.

### `realm_generation`

Owned by the existing provider-realm owner. Current protected source already seals this generation into `ProviderRealmEnrollmentReceipt` and into `mastermind.subscription_canary_admission/v1`. Family-B V2 extends that owner to bind the current `(host_ref, capacity_capability_id)` to exact principal/config custody; it does not add a new `binding_generation` owner.

Examples that require a new realm generation after V2 enrollment exists:

- new dedicated OS principal for the same provider capacity domain on the same host;
- new/replaced accepted config custody;
- logout/re-login or credential-custody replacement that must invalidate the prior local enrollment;
- moving executable custody to a replacement host while keeping the same logical provider capacity domain.

A stale realm generation cannot START work even when the provider capability generation itself is current.

### Existing `capacity_generation`

Current protected `ops/executive_os/capacity_owner_facts.py` and `control_plane/subscription_canary_admission.py` already use the Capacity/Model Router's fact generation as `capacity_generation`. Family B does not redefine it as provider-account identity.

A later B5 consumer may mint/consume an existing Capacity owner fact only after it has independently validated the accepted Provider Capacity V2 snapshot and native realm coordinate. If the current owner-fact/admission schema cannot bind the required provider-domain provenance without ambiguity, B5 must use a reviewed versioned successor rather than renaming or overloading existing fields.

## Binding rule for account replacement on one host

A host enrollment may not silently turn into a different logical subscription while retaining the old provider-capability identity.

If the provisioning owner deliberately changes that host from logical Claude subscription A to logical subscription B:

```text
old host/A realm enrollment -> revoke or supersede
host binds to B's capacity_capability_id/current capability_generation
new realm_generation for that host/B enrollment
```

Do not advance A's capability generation merely because one replica moved to B. Advance A's capability generation only when the **logical A provider-capability domain itself** is deliberately replaced/redefined.

Current provider surfaces still cannot automatically prove Anthropic account equality. This is therefore a managed provisioning invariant, not a claim that `auth status` can identify the account.

## Provider-realm enrollment V2 correction

The parent proposed wire is narrowed to extend the existing provider-realm owner:

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
capacity_identity_receipt_digest
source_receipt_digest
receipt_id
receipt_digest
```

The Provider-Control owner supplies `capacity_capability_id + capability_generation`. The existing provider-realm owner supplies/seals `realm_generation + host/principal/config custody`. Neither side mints a competing account identity.

Receipt verification must cover both cross-owner generations and the exact host/custody relationship. Existing V1 realm receipts and `realm_generation` semantics remain valid for their current consumers; V2 is an additive evolution, not an in-place reinterpretation.

## Preserve the accepted slot identity law

For native Claude V2, current executable slot identity stays:

```text
(host_ref, capacity_capability_id)
```

At most one current realm generation exists for a pair. The same `capacity_capability_id + capability_generation` may appear on several distinct `host_ref` values when that logical provider-capacity domain has accepted native custody on several hosts.

This does **not** make those rows separate quota pools.

## Shared quota domain vs host-local readiness

Provider Control must preserve source scope before deriving effective slot eligibility.

### Provider-capability-domain-scoped facts

These belong to `capacity_capability_id + capability_generation` and apply to every current host enrollment of that domain when the source really describes provider/account-wide capacity:

- authoritative provider quota horizons;
- provider/account usage-limit cooling;
- provider-wide account/auth revocation when proven to be domain-wide;
- accepted provider/account health evidence that is not host-specific.

A provider usage-limit observation from one accepted enrollment may cool the whole provider-capability domain only when the source/classification law says the error is account/provider-domain scoped. A local timeout or local auth-read failure is not enough.

### Realm/host-scoped facts

These belong only to one current `(host_ref, capacity_capability_id, realm_generation)`:

- Claude binary present/attested on that host;
- exact local credential-custody/auth readiness;
- local config/principal mismatch;
- host transport/broker availability;
- host recovery readiness;
- local browser/computer-use resource readiness;
- host-local process/runtime failure.

A realm-local failure cannot degrade healthy replicas except through separately proven shared provider evidence.

## Provider Capacity V2 projection rule

The V2 row remains host-addressable and uses the normal `capability_id` field:

```text
capability_id = capacity_capability_id
host_ref = exact opaque host
realm_binding = {
  capability_generation,
  realm_generation,
  enrollment_receipt_digest
}
```

This amendment withdraws the parent proposal to put an underspecified per-row `capacity_independence = verified | unknown` boolean inside `realm_binding`. Cross-domain independence is relational and cannot be truthfully expressed as one unqualified boolean on one row.

Until a future accepted relationship contract exists:

- same `capacity_capability_id + capability_generation` across hosts is one shared quota domain by construction;
- different `capacity_capability_id` values are **not assumed additive/independent** for a fleet-wide numeric entitlement claim;
- Family B V2 need not publish a fleet-total Max quota at all.

This is safer than inventing an “independence verified” bit without naming what it is independent from.

## Quota duplication and aggregation law

A V2 producer may repeat provider-domain-scoped quota evidence on several host rows for local placement convenience only if the schema makes the common `capacity_capability_id + capability_generation` explicit and a strict consumer treats those copies as the **same quota-domain evidence**.

No consumer may compute fleet quota by summing host rows.

Conceptually:

```text
quota aggregation key = (capacity_capability_id, capability_generation)
host execution key    = (host_ref, capacity_capability_id, realm_generation)
```

For the initial Family-B release, the safest public aggregate behavior is **no numeric cross-domain fleet total**. Placement can still rank/qualify individual slots using fresh evidence without claiming a mathematically additive subscription entitlement.

## B1 native registration owner correction

Current Macro `config/capability_manifest.yml` is a `capability_manifest.v1` **secret-reference broker** owned by `metabolism-phase0`; its rows contain `secret_ref` and lane/tier policy. A native Claude attached-login registration has different semantics and must not be forced into that manifest merely because Capacity F0 reads it as one existing source.

B1 must therefore use a reviewed, versioned, **secret-free** native Provider-Control registration surface inside the existing `shared-ai-provider-control` ownership boundary (or an exact current successor proven to own the same fact). It may contain the opaque `capacity_capability_id`, `capability_generation`, provider/billing/execution classification, registration state and material-source receipt—never a token, secret ref, host binding, raw config path or Executive Worker identity.

This is not permission to create a provider account database. The durable representation must remain the smallest deterministic registration needed by the existing Provider Control normalizer.

## Cooling propagation law

```text
usage_limit / provider-account cooling with domain-scoped evidence
    -> applies to every current host enrollment of that provider-capability domain

auth unavailable only on host A
    -> host A realm unavailable; host B realm may remain eligible

binary/transport/host-recovery failure on host A
    -> host A realm unavailable; provider-capability domain and host B remain truthful

unknown error scope
    -> do not broaden to domain-wide cooling; preserve unknown/degraded evidence
```

The adapter never decides this scope. Provider Control normalizes it from reviewed source semantics.

## Placement law across replicas

Model Router first establishes a lawful execution-quality tier. Capacity then reasons in two conceptual dimensions without a new scheduler:

```text
1. provider-capability domain eligibility using provider health/cooling/quota/fairness evidence
2. host realm eligibility inside that exact domain using realm/host/resource evidence
```

The implementation may perform this as one deterministic ranking pass; the conceptual split exists to prevent quota and host health from contaminating each other.

Before START, placement may select another current host realm of the same provider-capability domain if the first host becomes definitely unavailable and no effect/effect uncertainty exists. After START, RuntimeBinding remains sticky. Switching host, account or domain after START follows the existing Attempt/effect reconciliation law.

## Initial four-account canary and later fleet replication

B8 remains simple: first prove four intended Max provider-capability domains with **one accepted host realm each**. This avoids multiplying variables while the account/capacity contract is new.

Only after that proof may a later multi-host expansion attach additional M1/M6/Studio realms to an already accepted provider-capability domain. That expansion must prove:

```text
same capacity_capability_id + capability_generation
new distinct host_ref
new realm_generation and custody receipt
shared quota-domain observations are not duplicated as additive capacity
host-local failure affects only the failing realm
provider-domain usage-limit affects every replica
```

This lets the M6 fleet add execution locality/concurrency without lying that copying one Max login creates more Max quota.

## Required mutation/falsifier tests

The implementation must kill at least:

```text
same provider-capability domain on two hosts counted twice in fleet quota
host A auth failure cools host B without domain-scoped evidence
account usage-limit cools only the reporting host when scope is proven domain-wide
stale realm generation accepted under current capability generation
stale capability generation accepted under fresh realm generation
host B receipt substituted for host A
one host re-provisioned to logical account B while retaining account A capability identity
capability generation increment forces unrelated realm generation increment
realm generation increment silently creates a new quota domain
Macro capability_generation confused with Mastermind CapacityOwnerFact capacity_generation
caller forges capability id or provider capability generation
```

## Implementation-plan supersession

This amendment has narrow precedence over the same candidate's implementation plan wherever that plan says:

- Macro provider domain = `capacity_capability_id + realm_generation` or `capacity_generation`;
- host custody = `binding_generation`;
- native observation is keyed by `capacity_capability_id + realm_generation`;
- `realm_binding` contains `capacity_generation`, `binding_generation`, or the withdrawn `capacity_independence` field;
- B1 should put native attached-login registration into the metabolism `capability_manifest.v1` merely by default.

Read those locations as the corrected `capacity_capability_id + capability_generation`, existing owner `realm_generation`, closed V2 `realm_binding`, and secret-free Shared AI Provider Control registration law above. Do not begin B1 from the stale terminology.

## No effect

This amendment changes only architecture records. It creates no capability registration, credential, host binding, provider call, quota observation, Capacity owner fact, RuntimeBinding, Worker, route, browser/GUI lease or host mutation.