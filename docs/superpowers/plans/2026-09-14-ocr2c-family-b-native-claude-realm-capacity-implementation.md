# OCR-2C Family B — Native Claude Provider Capability + Realm Capacity Implementation Plan

**Date:** 2026-09-15  
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `IMPLEMENTATION PLAN CANDIDATE / RECORDS ONLY / NO START`  
**Depends on:** independent acceptance/protection of the paired Family-B architecture; current protected source and Skillpack re-pin at every later child START.  
**Current architecture basis:** Mastermind Family-B primary design + multi-host/auth amendments on PR #662, paired Macro PR #7162.

## Goal

Deliver a sequence of independently useful verticals that turns direct native `claude.ai` Claude Code subscriptions into governed Agent-Fabric execution capacity while preserving existing Executive OS, Capacity/Model Router, Provider Control, provider-realm, RuntimeBinding and resource owners.

Do not map native realms to numbered Macro OAuth slots, expose provider identity/credentials, count host replicas as extra quota, promote canary facts into production placement, or create another scheduler/account/quota/session/retry plane.

## Current owner model every child must preserve

```text
Macro provider domain
  capacity_capability_id + capability_generation

Mastermind host realm
  host_ref + capacity_capability_id + realm_generation

Mastermind subscription-canary Capacity fact
  CapacityOwnerFact.generation / public capacity_generation
  (canary-only under current source; not provider identity or production claim authority)
```

Production placement reuses accepted CF2:

```text
Provider Capacity snapshot
+ realm-local readiness
-> immutable (host_ref, capacity_capability_id) join
-> deterministic rank of already-lawful candidates
-> existing Executive atomic claim + immutable replay evidence
```

First-production auth remains protected PF1/OCR-1 law:

```text
native /login + dedicated OS principal + macOS Keychain + worker-context native-auth preflight
```

Setup-token and same-user multi-config isolation are future requalification only.

## Mandatory pickup law for every later child

Before START:

1. re-pin protected Mastermind + same-SHA Skillpack;
2. re-pin current Macro main;
3. re-read the protected Family-B decision/architecture and any newer accepted correction;
4. perform open-PR path/collision census and active-writer/effect census;
5. preserve one source writer/carrier and reconcile any `EFFECT_UNKNOWN` before replacement;
6. keep provider login/provisioning effects out of source-only waves;
7. use independent review and real-path proof appropriate to the capability; green CI is never production acceptance.

If current source has materially changed an owner boundary, stop and return to Sol rather than adapting the architecture locally.

---

## B0 — Protect the paired architecture

**Capability:** one current cross-repository law exists before code.

**Owner:** Sol + independent reviewer.  
**Effects:** records only.

Acceptance:

- exact Mastermind #662 and Macro #7162 heads independently reviewed together;
- latest-base/material compatibility clear;
- exact-head repository checks green;
- one canonical provider-capability identity, existing realm generation, V1 coexistence, CF2 claim reuse and auth boundary confirmed;
- explicit Sol `FAMILY_B_ARCHITECTURE_FROZEN` source-release record.

Stop if review requests changes. **No B1 effect before B0 protection.**

---

## B1 — Secret-free Provider Control native capability registration

**Capability:** Macro can deterministically define/export a native Claude provider-capability domain without credentials or host identity.

**Primary repo:** Macro.  
**Owner:** `shared-ai-provider-control`.

Frozen candidate source:

```text
CREATE config/provider_native_capabilities.v1.json
schema = mastermind.provider_native_capability_registry/v1
```

Closed current row:

```text
capacity_capability_id
capability_generation
provider = claude
billing_mode = subscription
credential_kind = attached_login
execution_surface = native_cli
registration_state = registered | revoked
```

Exactly one current row exists per `capacity_capability_id`. `revoked` is the deterministic current-state tombstone; removal is not revocation. The implementation compares the candidate registry with the immediately preceding accepted Provider Control release and refuses generation reuse, decrement, rollback, resurrection or reversion. Re-enrollment after `revoked(g)` requires `registered(g2)` with `g2 > g`.

Typed export:

```text
mastermind.provider_native_capability_registration/v1
capacity_capability_id
capability_generation
provider/billing/credential/execution classification
registration_state
material_source_digest
registration_receipt_digest
```

Forbidden:

- `config/capability_manifest.yml` reuse as native account registry;
- host/principal/Worker/config-path fields;
- token/key/secret-ref/account PII;
- provider calls/login/logout;
- mutable runtime account DB.

RED-first tests:

- closed schema/refusal of extras;
- duplicate/non-opaque/ordinal-like ids refuse under frozen policy;
- owner-issued generation >= 1 and comparison with the immediately preceding accepted release;
- `registered(g) -> revoked(g)` and `revoked(g) -> registered(g2)` only when `g2 > g`;
- removal, generation reuse/decrement, rollback, resurrection and source reversion refuse;
- secret/PII/path-shaped contamination refuses;
- deterministic receipt/source digest;
- V1 capacity projection remains byte/semantic identical with registry present;
- caller cannot mint/override id/generation/state.

Production proof ceiling: `BUILT_NOT_PROVEN / PROVIDER_CAPABILITY_REGISTRY_PROVEN / NO PROVIDER EFFECT`.

Stop after one reviewed Draft/HOLD B1 PR. Do not absorb B2/B4.

---

## B2 — Provider-realm enrollment V2

**Capability:** Mastermind can bind one current Provider-Control domain generation to one exact host/principal/config custody using the incumbent realm owner.

**Primary repo:** Mastermind.  
**Owner:** existing provider-realm owner.

Wire:

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
enrollment_state
registration_receipt_digest
source_receipt_digest
receipt_id
receipt_digest
```

Rules:

- reuse `realm_generation`; never add `binding_generation`;
- raw config path never enters public receipt;
- `config_custody_ref` is not provider identity or auth-isolation proof;
- Provider Control supplies id/generation; caller cannot choose them;
- `registration_receipt_digest` is the exact current B1 export digest; alternate names and mismatched documents refuse;
- V1 provider-realm receipts remain valid for their current consumers;
- ordinary host reboot does not advance `capability_generation` or `realm_generation`; physical boot currentness is bound later in B3/B4 readiness and B5 FP1B composition.

Tests must reject stale capability generation, stale realm generation, wrong host/principal/custody, swapped B-host receipt, forged Provider-Control registration digest and V1/V2 confusion.

No real login/logout is required in B2.

---

## B3 — Current Claude preflight bridge

**Capability:** the admitted realm can produce bounded provider-work-free readiness evidence bound to the same host/principal/realm generation and exact current FP1B `boot_ref`.

Reuse `ops/executive_os/claude-worker-preflight.py` and current provider-realm facts; extend/version only where necessary.

Preserve:

- `OS_PRINCIPAL_KEYCHAIN` isolation basis for first production;
- fixed binary/version/auth-status observations;
- provider PII discard-only handling;
- denial of `CLAUDE_CODE_OAUTH_TOKEN`, API/cloud auth and other stronger precedence inputs;
- no login, model turn or auth mutation;
- current `boot_ref` is copied from the incumbent host/FP1B owner and older-boot readiness refuses for new execution;
- boot provenance never substitutes for FP1B physical qualification, pool policy or resource admission.

`config_custody_ref` may be bound as local configuration identity but cannot replace the OS-principal/Keychain proof.

Stop after provider-work-free source/tests. No provider turn.

---

## B4 — Native observation + Provider Capacity V2

**Capability:** Macro normalizes current native realm evidence into a strict coexistence-safe Provider Capacity V2 while V1 stays unchanged.

**Primary repo:** Macro.

Frozen candidate surfaces:

```text
MODIFY engine/provider_capacity.py with shared V2 logic that preserves V1 behavior
CREATE scripts/build_provider_capacity_v2.py
ADD focused native registration/observation/V2 tests
```

Do not change `scripts/build_provider_capacity.py` V1 semantics unless a necessary source-neutral refactor is proven and V1 golden vectors remain exact.

Input:

```text
mastermind.provider_native_realm_observation/v1
capacity_capability_id + capability_generation
host_ref + boot_ref + realm_generation
enrollment_receipt_digest
scoped realm_auth / provider_health / cooling / quota / provider_outcome evidence
source_receipt_digest
```

Scope where applicable:

```text
provider_domain | realm | unknown
```

V2 row:

```text
capability_id = capacity_capability_id
host_ref
...V1 fields...
realm_binding = {
  capability_generation,
  boot_ref,
  realm_generation,
  enrollment_receipt_digest
}
```

Key laws:

```text
quota evidence key = (capacity_capability_id, capability_generation)
execution realm key = (host_ref, capacity_capability_id, realm_generation)
current readiness provenance key = (host_ref, boot_ref, capacity_capability_id, realm_generation)
host rows are never summed
unknown scope never broadens by guess
provider outcome != Executive completion
```

Required falsifiers include stale capability/realm generations, missing/stale/wrong `boot_ref`, pre-reboot readiness accepted on a later boot, cross-host receipt substitution, Provider Capacity boot provenance treated as physical authority, domain cooling scoped only to one host, host-local/physical failure widened to all replicas, row-level quota multiplication, secret/path/PII leakage, V1 drift, and V1 accepted as V2.

Real proof is a no-write V2 producer over safe fixtures/accepted local evidence only; no provider call is required in B4.

---

## B5 — Provider Capacity V2 acquisition + existing CF2 claim evolution

**Capability:** production placement can consume V2 without a second placement/claim plane.

**Primary repo:** Mastermind.  
**Owners:** current CF2 source acquisition, realm-readiness join, deterministic placement and atomic claim/replay owners.

Journey:

```text
strict Provider Capacity V2 acquisition
+ provider-realm V2 / boot-bound realm-local readiness
+ incumbent FP1B host qualification and fresh host-capacity/pressure evidence
-> exact (host_ref, capacity_capability_id) join
-> validate capability_generation + realm_generation
-> require host_ref == host_id and boot_ref == boot_id byte-for-byte
-> require current capacity_pool_ref + qualification_revision and fresh physical evidence
-> rank only already-lawful candidates under existing policy
-> existing Executive atomic claim / physical ResourceBroker BEGIN path
-> immutable provider V2 + physical evidence binding
-> replay returns historical accepted evidence without current provider/physical re-read or rerank
```

Claim evidence successor binds at minimum:

```text
provider_capacity_schema = mastermind.provider_capacity.v2
capacity_snapshot_hash
snapshot freshness identity
capacity_capability_id
capability_generation
host_ref
boot_ref
realm_generation
enrollment/source receipt digest(s)
current capacity_pool_ref
host_qualification_revision
host_capacity_snapshot_sha256 + accepted freshness identity
host_pressure_snapshot_sha256 / BEGIN identity
existing physical request/policy binding and deterministic policy/reason-code evidence
```

Forbidden:

- production placement through `CapacityOwnerFact`;
- second Capacity normalizer/ledger/selector/replay store;
- live Macro imports as fallback;
- current provider or physical-owner re-read on historical replay;
- Provider Capacity `boot_ref` used as the sole physical qualification/admission fact;
- a new host sampler, physical policy, qualification store, receipt owner or claim plane.

If a bounded subscription canary later needs V2 provenance, version `SubscriptionCanaryAdmission` separately; retain its existing `capacity_generation` meaning.

---

## B6 — One managed real `/login` realm + unattended recovery proof

**Capability:** one actual native Claude provider realm is usable after restart/cold boot without Chairman intervention under the accepted security boundary.

This is the first provisioning/provider-effect wave and therefore needs a fresh effectful START/permission gate.

Realm profile:

```text
one capacity_capability_id + capability_generation
one host_ref
one dedicated OS principal
one macOS Keychain realm
one exact reviewed config custody
native /login
one current realm_generation
```

Required proof:

```text
REALM_ISOLATION_PASS
AUTH_PRECEDENCE_PASS
RESTART_AUTH_PASS
COLD_BOOT_AUTH_PASS
EXPIRY_OBSERVABILITY_PASS
CAPABILITY_MODE_PASS
canonical HOST_RECOVERY_READY
```

A real cold boot must preserve host recovery and Claude auth as separate proofs.

Setup-token and same-user multi-config realm fanout remain out of scope unless a separate auth-source requalification has already protected a new rule.

Logout/re-enrollment proof must invalidate the old realm generation. Out-of-band credential mutation invalidates the managed-enrollment assumption rather than silently passing.

Stop after one accepted realm. Do not jump to four accounts.

---

## B7 — One bounded real native Claude Worker

**Capability:** one admitted realm executes one bounded real Claude CLI Worker through existing HF1/Executive paths.

Use existing Worker Harness/HF1 and RuntimeBinding. Do not create a Claude-specific lifecycle.

Acceptance requires real input -> canonical START/RuntimeBinding -> provider turn -> normalized Worker result/effect receipt -> Executive completion/reconciliation. CI/CLI success alone is insufficient.

Rate limit or transport failure after possible effect never transparently fails over.

---

## B8 — Four provider domains, one realm each

**Capability:** four intended Max provider-capability domains can be governed without Chairman account selection.

Keep the first proof deliberately one host realm per provider-capability domain to avoid mixing multi-host replication into initial identity proof.

For each domain:

- B1 registration accepted;
- B2 realm enrollment accepted;
- B6 isolation/restart/cold-boot proof accepted;
- one bounded real B7 provider turn accepted.

Do **not** claim the four domains have additive numeric Max entitlement without separately accepted relationship evidence.

---

## B9 — Capacity-selected multi-realm placement

**Capability:** new pre-START work selects among accepted Claude provider domains/realms through canonical Capacity, without Chairman account selection.

Prove:

- hard suitability/authority filters win first;
- known cooling/exhaustion excludes only with correct scope;
- unknown quota is neither full nor infinite;
- deterministic fairness/reservation/tie-break comes from existing Capacity policy;
- pre-START re-placement only when effect-free;
- post-START RuntimeBinding stays sticky;
- independent-review requirements never self-waive when capacity is scarce.

At least one real bounded Job must be placed by this path.

---

## Later multi-host replication

Only after B8/B9 core proof may one provider-capability domain be enrolled on multiple M1/M6/Studio hosts.

Prove:

```text
same capacity_capability_id + capability_generation
multiple host_ref values
separate realm_generation/custody receipts
host-local failure affects only failing realm
proven provider-domain usage-limit affects replicas
quota evidence is deduped by provider domain
no host-row quota multiplication
```

This adds locality/concurrency, not subscription entitlement.

---

## B10 / B11 — Persistent Operator, browser and computer use

B10 consumes accepted Family-B identity through OCR-4A/Operator Harness; B11 adds separately leased browser/computer-use capability through existing resource owners.

Neither may be used as evidence that Provider Control identity, Capacity placement, realm enrollment or Worker lifecycle is complete.

## Architecture-wide hostile tests

Every implementation wave must preserve tests/refusals for:

```text
ordinal/native-to-OAuth aliasing
provider PII/secret/path leakage
caller-forged capability id/generation
binding_generation reintroduction
capability_generation vs canary capacity_generation confusion
stale capability or realm generation
cross-host enrollment substitution
same provider domain double-counted across hosts
wrong failure-scope propagation
V1 semantic drift
CapacityOwnerFact used as production placement evidence
historical replay using current provider state
setup-token silently admitted under current /login law
config_custody_ref treated as auth-isolation proof
duplicate scheduler/quota/account/session/retry/claim plane
```

## Stop / continuation law

Each B-wave completes one useful capability and returns exact head/paths/tests/CI/review/real-proof receipts plus remaining gate. A green PR does not authorize the next wave. Sol explicitly adjudicates acceptance and commissions the next dependency.

Until B0 is independently accepted/protected, **all B1+ implementation and live provider effects remain unstarted**.