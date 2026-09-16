# OCR-2C Family B — Revocation, Observation Acquisition, and Digest Identity Correction

**Date:** 2026-09-16  
**Owner:** Sol / existing `WS:EXECUTIVE-CAPACITY-FABRIC`  
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `AUTHOR-SIDE REVIEW REPAIR CANDIDATE / RECORDS ONLY / SPEC_ONLY / HOLD FOR NEW INDEPENDENT REVIEW`  
**Consumes review:** `ocr2c-family-b-paired-architecture-review-20260914-sol-001`, report SHA-256 `eda93658073085edb41aa562fc899fac72d5cfe1ff0f39b25b29841256988115`.  
**Paired Macro record:** `agentos/decisions/DEC-NATIVE-CLAUDE-FAMILY-B-REVOCATION-OBSERVATION-ACQUISITION.md`.

## 1. Narrow precedence

This correction supersedes only three conflicting or incomplete clauses in the pending Family-B records:

1. the B1 registry row being closed to `registration_state = registered` while its owner export and currentness law allow revocation;
2. the B2 field name `capacity_identity_receipt_digest` where B1 already owns the canonical `registration_receipt_digest`;
3. any B4 interpretation that accepts caller-supplied `mastermind.provider_native_realm_observation/v1` JSON, or treats `source_receipt_digest` as producer authentication.

It has narrow precedence over:

- `docs/superpowers/specs/2026-09-14-ocr2c-family-b-native-claude-realm-capacity-design.md`;
- `docs/superpowers/plans/2026-09-14-ocr2c-family-b-native-claude-realm-capacity-implementation.md`;
- `docs/superpowers/specs/2026-09-14-ocr2c-family-b-multihost-quota-domain-amendment.md`;
- the paired Macro architecture, decisions and handoffs only where they conflict with the clauses below.

All other accepted candidate boundaries remain: Macro owns provider-domain identity and Provider Capacity normalization; Mastermind owns host-realm enrollment/custody and Executive lifecycle; `capability_generation`, incumbent `realm_generation`, and canary `capacity_generation` remain distinct; `/login` plus dedicated OS principal/Keychain remains the first-production auth boundary; B2 remains gated by `REALM_OWNER_REALIZATION_REQUIRED`; no second scheduler, account database, quota graph, claim ledger, session registry, receipt store or retry plane is introduced.

## 2. B1 current registration state is explicit and source-owned

The checked-in B1 registry remains:

```text
config/provider_native_capabilities.v1.json
schema = mastermind.provider_native_capability_registry/v1
owner_program = shared-ai-provider-control
```

A closed capability row now contains:

```text
capacity_capability_id
capability_generation
provider = claude
billing_mode = subscription
credential_kind = attached_login
execution_surface = native_cli
registration_state = registered | revoked
```

### Current-state law

For each `capacity_capability_id`, the accepted registry contains **exactly one current row**. Duplicate current rows, omission after a previously accepted registration, or conflicting states for the same identity are invalid.

`registration_state = revoked` is the deterministic tombstone for the current provider-domain generation. Row removal is not revocation: absence cannot distinguish never-registered from deliberately revoked and therefore fails current-source acquisition when the identity existed in the preceding accepted registry.

The transition law is:

```text
never registered
  -> registered(g)

registered(g)
  -> revoked(g)          # generation g becomes terminal

revoked(g)
  -> registered(g2)      # re-enrollment; g2 > g
```

A revoked generation never becomes registered again. Re-enrollment requires a strictly greater owner-issued `capability_generation`; generation reuse, decrement, rollback, resurrection of an older registered row, and source reversion to a previously accepted generation are refused.

The current file is not a standalone history database. Monotonicity is checked by the existing Provider Control source/release acquisition owner against the immediately preceding accepted registry/release identity. Git history and immutable accepted-release evidence preserve history; no mutable runtime account store is created.

`capability_generation` still does not advance for token refresh, binary update, host reboot, local realm repair or canary fact refresh. Revoking a current generation changes its current registration state; a later re-enrollment creates a newer generation.

### B1 export

The canonical export remains:

```text
schema = mastermind.provider_native_capability_registration/v1
capacity_capability_id
capability_generation
provider
billing_mode
credential_kind
execution_surface
registration_state = registered | revoked
material_source_digest
registration_receipt_digest
```

The export state must equal the validated current registry row. A revoked export is deterministic, secret-free and cannot be used for a new realm enrollment or execution. Historical accepted claim/replay evidence remains historical and effect-free; revocation does not rewrite prior facts.

### B1 discriminators

B1 RED/GREEN tests must distinguish at least:

```text
registered(g) -> revoked(g) accepted as terminal current state
revoked(g) -> registered(g2), g2 > g, accepted as re-enrollment
revoked(g) -> registered(g) refused
registered(g) -> registered(g-1) refused
previously accepted identity removed from current registry refused
same capability identity duplicated refused
registered and revoked rows for one identity refused
source reversion to an older accepted registration refused
caller-selected id/generation/state override refused
revoked export accepted only as non-executable current owner fact
V1 Provider Capacity output remains unchanged
```

## 3. One canonical registration digest crosses B1 into B2

The only provider-domain registration digest field is:

```text
registration_receipt_digest
```

B2 `mastermind.provider_realm_enrollment/v2` therefore contains:

```text
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

The draft name `capacity_identity_receipt_digest` is withdrawn and invalid. No mapping, alias or second digest owner is created.

The provider-realm owner must consume the exact current Macro registration document and `registration_receipt_digest` through its approved owner/source-acquisition boundary. A caller-computed public digest, an alternate field name, a digest from another capability generation, and any mismatch between registration document and digest are refused.

Required B2 discriminators include alternate-name refusal, mismatched digest refusal, revoked registration refusal for new enrollment/execution, stale capability generation, stale realm generation, wrong host/principal/custody and cross-host receipt substitution.

## 4. B4 observation acquisition reuses the existing Provider Control source-owned seam

`mastermind.provider_native_realm_observation/v1` remains a secret-free observation contract, but it is **not a public submission API**.

Macro's existing Provider Capacity producer already owns this pattern:

```text
build_snapshot()
  -> collect_current_observations()
  -> _build_snapshot_from_observations(...)
```

`build_snapshot()` and `collect_current_observations()` are producer-owned. Current callers may select only the repository root; they cannot inject arbitrary observation rows. Family B B4 extends this exact source-owned collection boundary (or its reviewed current successor) with one fixed native-realm observation adapter. It does not expose `_build_snapshot_from_observations(...)`, the V2 CLI, a request body, Worker/model output or caller JSON as production acquisition authority.

### Producer and acquisition ownership

The accepted observation producer is the composed Mastermind B2/B3 owner boundary:

```text
current Macro registration
+ current provider-realm enrollment/custody
+ provider-work-free Claude preflight/readiness observation
-> one secret-free native-realm observation
```

The producer must bind:

```text
capacity_capability_id
capability_generation
registration_receipt_digest
host_ref
boot_ref
realm_generation
enrollment_receipt_digest
os_principal_ref
config_custody_ref
preflight/source receipt identity
producer release/commit identity
material_source_digest
observed_at + stale_after/freshness identity
```

Provider PII, credential material, Keychain labels/content, raw config paths, prompts/results and provider conversation ids remain forbidden.

Macro's fixed `collect_current_observations()` adapter acquires this owner-produced fact from the approved deployment/source boundary and validates every identity above before normalization. Acquisition trust comes from the fixed source adapter, installed release identity, OS/deployment custody and accepted owner receipts—not from `source_receipt_digest` alone.

`source_receipt_digest` remains content-integrity evidence. It cannot authenticate the producer, grant scope, make stale data fresh or let a request/Worker/model choose provider-domain, host, realm, principal, custody, release or freshness fields.

When the fixed producer is unavailable, ungrounded, stale, wrong-host, wrong-generation, wrong-release or lower-quality than required, Provider Control emits the applicable existing unknown/degraded evidence and does not synthesize availability, cooling scope or quota.

No new daemon, observation database, receipt store, normalizer, scheduler or cross-repository transaction is authorized. Exact transport/deployment realization must be selected inside the existing source-owner adapter at B4 implementation START after current protected re-pin; it may not change the ownership and no-caller-input contract above.

### B4 discriminators

B4 tests must kill at least:

```text
arbitrary caller JSON accepted as a production observation
public source_receipt_digest treated as producer authentication
caller chooses capability/host/realm/principal/custody/release identity
registration digest or generation mismatch
cross-host enrollment or preflight receipt substitution
missing/stale/wrong boot_ref or pre-reboot readiness accepted after reboot
Provider Capacity boot provenance treated as physical admission authority
stale observation or stale producer release accepted as fresh
unavailable producer treated as available
source-quality downgrade silently widened to exact/provider-domain evidence
realm-local failure widened to provider-domain scope
provider-domain cooling confined to one host when scope is proven
```

Safe fixtures may call the internal normalization builder directly for deterministic unit tests; that test seam is never the production acquisition path.

## 5. Corrected implementation ordering

The production ladder remains unchanged, but the gates are now explicit:

```text
B0 repaired paired architecture independently accepted
-> B1 registry/export with current revocation law
-> B2 owner-current realm realization using canonical registration_receipt_digest
-> B3 provider-work-free preflight bridge
-> B4 fixed source-owned observation acquisition + Provider Capacity V2
-> B5 existing CF2 acquisition/join/claim/replay evolution
-> B6 one managed /login dedicated-principal realm
-> B7 one bounded real native Claude Worker
-> later separately qualified domains/realms
```

B1 may not START until this correction and its paired Macro decision receive fresh current-head/current-base checks and a new independent paired review PASS followed by explicit Sol `FAMILY_B_ARCHITECTURE_FROZEN`.

## 6. No-effect boundary

This correction is records-only. It creates no registry file, provider capability, realm enrollment, observation adapter, runtime source, provider call, login/logout, credential read/change, host permission, Capacity snapshot, claim, RuntimeBinding, Worker, browser/GUI action, Ready transition or merge authority.