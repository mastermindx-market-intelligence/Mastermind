# OCR-2C Family B — Multi-Host Quota-Domain Amendment

**Date:** 2026-09-14  
**Parent operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Narrow precedence:** this amendment supersedes the parent Family-B records only where they used one `realm_generation` for both provider-capacity identity and host-local native credential custody, or where they implied one native capacity capability can have only one host binding.

## Why this amendment exists

Mastermind-X is becoming a multi-Mac fleet. One direct Claude subscription may intentionally be usable from more than one physical Mac, while every such host binding still consumes the **same provider quota/cooling domain**. Conversely, a host-local Claude failure (binary missing, local auth unavailable, config custody broken, transport unavailable) should not automatically make a healthy binding of the same subscription on another Mac unusable.

The accepted Capacity F0 architecture already anticipated this. Slot identity is the pair `(host_ref, capability_id)`, not `capability_id` alone; host identity is opaque; and an attached subscription present on Mac A is not assumed callable on Mac B. Family B must preserve that law rather than collapse account/quota identity and host execution binding into one generation.

## Frozen two-axis identity model

Family B uses **one Provider-Control capacity identity** and **zero second account identities**, but it has two independent correction generations:

```text
capacity_capability_id + capacity_generation
    = Provider-Control-owned logical provider capacity / quota domain

host_ref + capacity_capability_id + binding_generation
    = one host-local executable custody binding of that capacity domain
```

`binding_generation` is an epoch, not another account/capacity identifier. It exists only to make replacement of one host/principal/config custody correction-safe.

### `capacity_generation`

Owned by Macro Shared AI Provider Control. It changes when the company deliberately replaces/redefines the logical provider-capacity domain represented by `capacity_capability_id`.

Examples that require a new capacity generation:

- the company intentionally repoints that opaque capacity domain to a different direct subscription;
- the Provider-Control registration for the domain is revoked and re-enrolled as a new current generation;
- a later accepted provider identity source proves the current domain membership has changed.

Ordinary OAuth/access-token refresh, a Claude Code binary update, host reboot, or re-creating one host's local custody does **not** change `capacity_generation`.

### `binding_generation`

Owned by the existing provider-realm/custody binding owner for the exact `(host_ref, capacity_capability_id)` relationship. It changes when the executable native custody on that host is replaced or deliberately re-provisioned.

Examples that require a new binding generation:

- new dedicated OS principal for the same capacity domain on the same host;
- new/replaced accepted `CLAUDE_CONFIG_DIR` custody;
- logout/re-login or credential-custody replacement that must invalidate the prior local binding;
- moving the executable binding to a replacement host while keeping the same logical capacity domain.

A stale binding generation cannot START work even when the capacity generation itself is still current.

## Binding rule for account replacement on one host

A host binding may not silently turn into a different logical subscription while retaining the old capacity-domain identity.

If the provisioning owner deliberately changes that host from logical Claude subscription A to logical subscription B:

```text
old host/A binding -> revoke or supersede
host binds to B's capacity_capability_id/current capacity_generation
new binding_generation for that host/B relationship
```

Do not mutate A's capacity generation merely because one replica moved to B. Advance A's capacity generation only when the **logical A capacity domain itself** is deliberately replaced/redefined.

Current provider surfaces still cannot automatically prove Anthropic account equality. This is therefore a managed provisioning invariant, not a claim that `auth status` can identify the account.

## Provider-realm enrollment V2 correction

The parent proposed wire is narrowed to:

```text
schema = mastermind.provider_realm_enrollment/v2
capacity_capability_id
capacity_generation
binding_generation
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

The Provider-Control owner supplies `capacity_capability_id + capacity_generation`. The provider-realm owner supplies/binds `binding_generation + host/principal/config custody`. Neither side mints a competing account identity.

Receipt verification must cover both generations and the exact host/custody relationship.

## Preserve the accepted slot identity law

For native Claude V2, current executable slot identity stays:

```text
(host_ref, capacity_capability_id)
```

At most one current binding generation exists for a pair. The same `capacity_capability_id + capacity_generation` may appear on several distinct `host_ref` values when that logical capacity domain has accepted native custody on several hosts.

This does **not** make those rows separate quota pools.

## Shared quota domain vs host-local readiness

Provider Control must preserve source scope before deriving effective slot eligibility.

### Capacity-domain-scoped facts

These belong to `capacity_capability_id + capacity_generation` and apply to every current host binding of that domain when the source really describes provider/account-wide capacity:

- authoritative provider quota horizons;
- provider/account usage-limit cooling;
- provider-wide account/auth revocation when proven to be domain-wide;
- accepted provider/account health evidence that is not host-specific.

A provider usage-limit observation from one accepted binding may cool the whole capacity domain only when the source/classification law says the error is account/provider-domain scoped. A local timeout or local auth-read failure is not enough.

### Binding/host-scoped facts

These belong only to one current `(host_ref, capacity_capability_id, binding_generation)`:

- Claude binary present/attested on that host;
- exact local credential-custody/auth readiness;
- local config/principal mismatch;
- host transport/broker availability;
- host recovery readiness;
- local browser/computer-use resource readiness;
- host-local process/runtime failure.

A binding-local failure cannot degrade healthy replicas except through separately proven shared provider evidence.

## Provider Capacity V2 projection rule

The V2 row remains host-addressable and uses the normal `capability_id` field:

```text
capability_id = capacity_capability_id
host_ref = exact opaque host
realm_binding = {
  capacity_generation,
  binding_generation,
  enrollment_receipt_digest
}
```

This amendment withdraws the parent proposal to put an underspecified per-row `capacity_independence = verified | unknown` boolean inside `realm_binding`. Cross-domain independence is relational and cannot be truthfully expressed as one unqualified boolean on one row.

Until a future accepted relationship contract exists:

- same `capacity_capability_id + capacity_generation` across hosts is one shared quota domain by construction;
- different `capacity_capability_id` values are **not assumed additive/independent** for a fleet-wide numeric entitlement claim;
- Family B V2 need not publish a fleet-total Max quota at all.

This is safer than inventing an “independence verified” bit without naming what it is independent from.

## Quota duplication and aggregation law

A V2 producer may repeat domain-scoped quota evidence on several host rows for local placement convenience only if the schema makes the common `capacity_capability_id + capacity_generation` explicit and a strict consumer treats those copies as the **same quota-domain evidence**.

No consumer may compute fleet quota by summing host rows.

Conceptually:

```text
quota aggregation key = (capacity_capability_id, capacity_generation)
host execution key    = (host_ref, capacity_capability_id, binding_generation)
```

For the initial Family-B release, the safest public aggregate behavior is **no numeric cross-domain fleet total**. Placement can still rank/qualify individual slots using fresh evidence without claiming a mathematically additive subscription entitlement.

## Cooling propagation law

```text
usage_limit / provider-account cooling with domain-scoped evidence
    -> applies to every current host binding of that capacity domain

auth unavailable only on host A
    -> host A binding unavailable; host B binding may remain eligible

binary/transport/host-recovery failure on host A
    -> host A binding unavailable; capacity domain and host B remain truthful

unknown error scope
    -> do not broaden to domain-wide cooling; preserve unknown/degraded evidence
```

The adapter never decides this scope. Provider Control normalizes it from reviewed source semantics.

## Placement law across replicas

Model Router first establishes a lawful execution-quality tier. Capacity then reasons in two stages without a new scheduler:

```text
1. choose an eligible capacity domain using provider health/cooling/quota/fairness evidence
2. choose an eligible host binding of that exact domain using host/binding/resource evidence
```

The implementation may perform this as one deterministic ranking pass; the conceptual split exists to prevent quota and host health from contaminating each other.

Before START, placement may select another current host binding of the same capacity domain if the first host becomes definitely unavailable and no effect/effect uncertainty exists. After START, RuntimeBinding remains sticky. Switching host, account or domain after START follows the existing Attempt/effect reconciliation law.

## Initial four-account canary and later fleet replication

B8 remains simple: first prove four intended Max capacity domains with **one accepted host binding each**. This avoids multiplying variables while the account/capacity contract is new.

Only after that proof may a later multi-host expansion attach additional M1/M6/Studio bindings to an already accepted capacity domain. That expansion must prove:

```text
same capacity_capability_id + capacity_generation
new distinct host_ref
new binding_generation and custody receipt
shared quota-domain observations are not duplicated as additive capacity
host-local failure affects only the failing binding
provider-domain usage-limit affects every replica
```

This lets the M6 fleet add execution locality/concurrency without lying that copying one Max login creates more Max quota.

## Required mutation/falsifier tests

The implementation must kill at least:

```text
same capacity domain on two hosts counted twice in fleet quota
host A auth failure cools host B without domain-scoped evidence
account usage-limit cools only the reporting host when scope is proven domain-wide
stale binding generation accepted under current capacity generation
stale capacity generation accepted under fresh binding generation
host B receipt substituted for host A
one host re-provisioned to logical account B while retaining account A capability identity
capacity generation increment forces unrelated binding generation increment
binding generation increment silently creates a new quota domain
```

## No effect

This amendment changes only architecture records. It creates no capability registration, credential, host binding, provider call, quota observation, RuntimeBinding, Worker, route, browser/GUI lease or host mutation.