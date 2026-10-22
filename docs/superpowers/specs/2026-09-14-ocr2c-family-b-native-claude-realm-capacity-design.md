# OCR-2C Family B — Native Claude Provider Capability + Realm Capacity Architecture

**Date:** 2026-09-15  
**Owner:** Sol, AI CEO  
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `CHAIRMAN-APPROVED DIRECTION / ARCHITECTURE CANDIDATE / RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Current protected reconciliation basis:** `Mastermind@8e25bb32601ef5f40a689da6d6f24149e79e31fa`, Skillpack `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1.  
**Organizational owner:** existing `WS:EXECUTIVE-CAPACITY-FABRIC`; no new workstream.  
**Paired owner candidate:** Macro PR #7162.

## 1. Outcome

The target is not “four Claude processes.” It is a governed execution path:

```text
Chairman / CEO intent
-> Executive Job / Attempt
-> provider-neutral Model Router suitability
-> canonical Capacity placement
-> one exact native Claude provider-capability domain + host realm
-> existing Worker / Operator Harness
-> useful result through existing Executive lifecycle/effect law
```

Routine work must not require the Chairman to choose a numbered account, foreground a cloned app, or manually move a task after quota loss. Provider/account/host changes remain governed by pre-START placement and post-START RuntimeBinding/effect reconciliation; `EFFECT_UNKNOWN` never becomes failover permission.

The independently useful Family-B capability is narrower: **give direct `claude.ai` native execution canonical Provider Control identity and correction-safe host-realm evidence without rebuilding provider capacity or placement inside Mastermind.**

## 2. Family A refusal remains binding

Do not equate native Claude realms with Macro `claude_code_oauth_N` by ordinal, app/Slack/seat name, config path, plan type, reset time, usage percentage, provider/model name, token fingerprint or operator intuition.

No current safe provider-supported, secret-free, rotation-safe equality witness proves those are the same paid subscription domains. Family B therefore evolves Provider Control directly.

## 3. Owners preserved

| Fact / action | Canonical owner |
|---|---|
| Job / Attempt / Worker / Event / effect reconciliation | Executive OS |
| acceptable model/execution class | Model Router |
| provider-capability identity/generation, provider health/cooling/quota normalization | Macro Shared AI Provider Control |
| host-local provider realm enrollment and `realm_generation` | existing provider-realm owner |
| production Provider Capacity acquisition, realm-readiness join, deterministic ranking, atomic claim/replay evidence | existing CF2 path |
| interactive subscription-canary Capacity fact generation | existing `CapacityOwnerFact` / subscription canary admission only |
| provider-work-free Claude binary/auth readiness | existing Claude preflight family |
| bounded provider execution | HF1 / Worker Harness |
| persistent provider session mechanics | OCR-4A / Operator Harness |
| exact STARTed provider/host/session binding | RuntimeBinding |
| physical unattended host recovery | canonical host-recovery owner |
| browser / GUI exclusivity | BrowserResource / host-resource owners |
| durable organizational continuity | Agent OS |

No Claude account database, second quota table, provider scheduler, placement ledger, retry daemon, lifecycle plane, session registry or browser/computer-use control plane is authorized.

## 4. Three generation owners must not be collapsed

Current protected source already has two Mastermind generation owners, so Family B uses three distinct epochs:

```text
A. capacity_capability_id + capability_generation
   owner: Macro Shared AI Provider Control
   meaning: one logical provider capacity / quota domain

B. host_ref + capacity_capability_id + realm_generation
   owner: existing Mastermind provider-realm owner
   meaning: one current executable enrollment/custody of A on one host

C. CapacityOwnerFact.generation
   public subscription-canary field: capacity_generation
   owner: Mastermind Capacity/Model Router canary seam
   meaning: current canary Capacity fact generation
```

A, B and C are independent. Equality of integer values proves nothing.

`capability_generation` advances only when the logical Provider-Control domain is deliberately replaced/redefined or its native registration is revoked/re-enrolled as a new provider-domain generation. It does not advance for token refresh, Claude binary update, host reboot, local realm repair or an ordinary canary Capacity fact refresh.

Protected `ProviderRealmEnrollmentReceipt.generation` already owns the local correction epoch. Family-B V2 extends that owner to bind exact host/principal/config custody; there is **no `binding_generation`**.

Protected `CapacityOwnerFact.generation`, exposed by `mastermind.subscription_canary_admission/v1` as `capacity_generation`, remains a canary activation fact. It is not provider subscription identity and is not the accepted production CF2 claim contract.

## 5. Provider Control B1 registration

The paired Macro architecture freezes the candidate checked-in source as:

```text
config/provider_native_capabilities.v1.json
schema = mastermind.provider_native_capability_registry/v1
owner_program = shared-ai-provider-control
```

One closed row contains only:

```text
capacity_capability_id
capability_generation
provider = claude
billing_mode = subscription
credential_kind = attached_login
execution_surface = native_cli
registration_state = registered | revoked
```

Exactly one current row exists per capability identity. `revoked` is the source-owned tombstone for the current generation; removal, reuse, rollback and resurrection refuse against the immediately preceding accepted Provider Control release. Re-enrollment requires a strictly newer owner-issued generation.

`capacity_capability_id` is opaque, non-ordinal and non-PII. It must not encode account email/id/org, host, Worker, config path, token/secret, Keychain label, app clone or `claude_code_oauth_N`.

The registry is the smallest deterministic Provider Control source, not a mutable runtime account database.

Macro owner export:

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

There is deliberately no `host_ref` in the Provider Control registration export.

## 6. Provider-realm enrollment V2

Family B evolves the existing provider-realm owner rather than creating a Claude-native realm registry.

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

Provider Control supplies the provider-domain coordinate. Mastermind seals the host realm and custody. Neither side mints a second account identity.

The raw `CLAUDE_CONFIG_DIR` path is provider-private launch state and must not enter public/canonical evidence. `config_custody_ref` is an opaque non-reversible configuration-custody coordinate. Under current protected PF1/OCR-1 source law, it **does not prove macOS credential isolation** and cannot replace the dedicated OS-principal/Keychain boundary.

If a host intentionally moves from logical provider domain A to B, revoke/supersede the old host/A realm, bind the host to B's current provider-domain coordinate, and mint a new realm generation. Do not redefine A merely because one replica moved away from it.

## 7. First-production Claude auth boundary remains protected law

Family B capacity identity does not authorize credential mechanisms.

The first production-real B6 realm remains:

```text
native /login
+ dedicated OS principal
+ macOS Keychain
+ exact reviewed Claude Code binary/profile
+ worker-context preflight proving native Claude.ai auth wins precedence
```

Current provider support for setup-token and stronger `CLAUDE_CONFIG_DIR` credential/Keychain keying is useful future requalification evidence, but does not silently supersede current PF1/OCR-1 law.

Therefore setup-token is not admitted in B6, same-OS-user multi-config fanout is not admitted as production isolation proof, stronger API/cloud/token/profile auth remains fail-closed, and alternative auth/isolation requires a separate source-law requalification.

Cruise-mode production requires real `RESTART_AUTH_PASS`, `COLD_BOOT_AUTH_PASS`, `AUTH_PRECEDENCE_PASS`, `EXPIRY_OBSERVABILITY_PASS`, `REALM_ISOLATION_PASS`, plus separate capability-mode proof. Physical recovery remains owned by `mastermind.host_recovery_readiness/v1`.

## 8. Native realm observation into Provider Control

After Provider Control registration and provider-realm enrollment exist, a bounded host-side source may report evidence about that exact domain/realm:

```text
schema = mastermind.provider_native_realm_observation/v1
capacity_capability_id
capability_generation
host_ref
boot_ref
realm_generation
enrollment_receipt_digest
observed_at
realm_auth {state, method, source_quality}
provider_health {state, error_class, scope, observed_at}
cooling {active, kind, reset_at, evidence, scope, observed_at}
quota_horizons[] {existing V1 quota evidence fields + scope}
last_provider_outcome {class, observed_at, scope}
source_receipt_digest
```

Scope distinguishes `provider_domain`, `realm` and `unknown` where applicable.

`boot_ref` is the exact current physical boot-generation reference already owned by FP1B/host-capacity. It is readiness provenance, not provider identity, enrollment identity, quota identity or a new Family-B generation. B2 enrollment remains stable across an ordinary reboot; neither `capability_generation` nor `realm_generation` advances merely because `boot_ref` changes. A B3/B4 observation from an earlier boot is ineligible for new execution after the host advances to another current boot.

This is source evidence only. It cannot create a provider capability, rank workers, set another provider domain cooling, assert Executive completion or replace claim-time worker/realm readiness.

Reject provider PII, credentials/fingerprints, Keychain labels/content, raw config paths, prompts/results, Job/Attempt ids, Slack identities and provider conversation ids.

## 9. Provider Capacity V2

`mastermind.provider_capacity.v1` remains unchanged.

V2 preserves the V1 top-level semantic model and evidence laws and adds one closed slot identity extension:

```text
realm_binding = null
  | {
      capability_generation,
      boot_ref,
      realm_generation,
      enrollment_receipt_digest
    }
```

Native Claude row:

```text
capability_id = capacity_capability_id
provider = claude
billing_mode = subscription
credential_kind = attached_login
execution_surface = native_cli
host_ref = exact accepted opaque host
realm_binding != null
```

Existing V1-style rows in V2 use `realm_binding = null` unless separately versioned evidence gives them equivalent semantics. V1 and V2 are separate closed schemas. V1 output and material-source identity do not change because V2 definitions exist.

Preserved laws include: unknown is not false or unlimited, stale is not fresh, presence is not authentication, authentication is not health, provider outcome is not Executive completion, host matters, correction does not rewrite historical placement evidence, and semantic evidence is secret-free.

## 10. Multi-host quota domain law

One provider-capability domain may have several host realms:

```text
quota evidence key = (capacity_capability_id, capability_generation)
execution realm key = (host_ref, capacity_capability_id, realm_generation)
current readiness provenance key = (host_ref, boot_ref, capacity_capability_id, realm_generation)
```

No consumer may sum host rows into aggregate quota.

Different `capacity_capability_id` values are likewise not assumed numerically additive merely because provisioning intended different Max subscriptions. Family B makes no fleet-total numeric entitlement claim without separately accepted relationship evidence.

Provider-domain usage-limit/cooling propagates to current replicas only when source semantics prove domain scope. Binary/local-auth/config/transport/host-recovery/resource failures remain realm-local. Unknown scope remains unknown/degraded.

The earlier per-row `capacity_independence` proposal is withdrawn.

## 11. Production B5 reuses canonical CF2 acquisition/join/claim/replay

Accepted CF2-F already freezes the production pattern. Family B extends it rather than inventing a bridge around it:

```text
strict Provider Capacity V2 snapshot
        +
current provider-realm V2 / boot-bound realm-local readiness evidence
        +
incumbent FP1B physical qualification + fresh host-capacity/pressure evidence
        |
        v
immutable (host_ref, capacity_capability_id) join
+ capability_generation + realm_generation validation
+ byte-exact host_ref == host_id and boot_ref == boot_id
+ current capacity_pool_ref + qualification_revision validation
        |
        v
strict Mastermind V2 consumer
+ deterministic ranking of already-lawful candidates
        |
        v
existing Executive atomic claim / ResourceBroker BEGIN path
+ separately bound provider-capacity and FP1B physical evidence
+ historical replay without current provider or physical re-read/rerank
```

The claim-evidence successor binds at minimum Provider Capacity V2 schema/hash/freshness identity, selected `capacity_capability_id + capability_generation`, selected `host_ref + boot_ref + realm_generation`, enrollment/source receipt digests, and existing deterministic policy/reason-code evidence. It also binds the incumbent FP1B request/result identities required by the existing physical owner, including current `capacity_pool_ref`, `host_qualification_revision`, host-capacity snapshot digest/freshness and BEGIN pressure snapshot digest. Family B references those accepted physical facts; it does not mint a second physical receipt or make Provider Capacity the admission authority.

Use the existing event/claim/placement owner. No second capacity ledger, selector DB or replay plane.

Current `SubscriptionCanaryAdmission` remains a separate canary mechanism. If a later B6/B7 canary needs V2 provenance, version that admission explicitly rather than changing the meaning of its `capacity_generation`.

## 12. Selection law after four domains are proven

Once four provider-capability domains with one accepted host realm each are accepted:

```text
Executive authority/capability filters
-> first lawful Model Router tier
-> Provider Capacity V2 provider-domain eligibility
-> exact realm/host/resource eligibility
-> provider cooling/quota when known
-> existing deterministic Capacity fairness/reservation policy
-> atomic claim
```

Unknown quota is not full quota and is not automatically disqualifying unless current policy requires known capacity.

Before START, a definite unavailable realm/domain may be replaced under current placement law when no effect/effect uncertainty exists. After START, RuntimeBinding is sticky.

Multi-host replication is a later proof after the core four-domain canary. It must demonstrate shared quota deduplication, realm-local failure isolation and provider-domain cooling propagation.

## 13. Downstream execution/resource boundaries

Family B does not define persistent provider session lifecycle, browser automation, computer use, provider background retry/failover, MCP/package realization or Operator Harness session ownership.

HF1, OCR-4A, RuntimeBinding, BrowserResource and host-resource owners consume accepted Family-B identity/capacity facts later.

## 14. Required falsifiers

Independent review and later tests must kill at least:

```text
native realm aliases claude_code_oauth_N by ordinal/name/path
provider capability id encodes provider PII or host/Worker identity
caller forges capacity_capability_id or capability_generation
new binding_generation is created beside realm_generation
Macro capability_generation is confused with canary capacity_generation
same provider domain on two hosts is counted twice as quota
host-local auth failure cools all replicas without provider-domain evidence
provider-domain usage-limit cools only reporting realm
stale realm generation is accepted under current capability generation
stale capability generation is accepted under current realm generation
host B enrollment is substituted for host A
pre-reboot readiness is accepted after current boot_ref changes
reboot incorrectly advances capability_generation or realm_generation
Provider Capacity boot_ref is treated as physical admission authority
provider host_ref/boot_ref differs from FP1B host_id/boot_id
stale or wrong capacity_pool_ref / qualification_revision is accepted
stale/incomplete host-capacity or mismatched BEGIN pressure evidence is accepted
physical host failure is widened to provider-domain cooling
historical replay re-reads current physical qualification
Provider Capacity V1 changes because V2 definitions exist
V1 is accepted as V2 by structural superset
CapacityOwnerFact substitutes for production V2 claim evidence
historical replay re-reads current provider capacity
provider observation is interpreted as Executive Job success
public evidence contains raw path/secret/account PII
config_custody_ref is treated as macOS auth-isolation proof
setup-token is silently admitted under the protected /login source law
```

## 15. Implementation ladder

```text
B0 architecture protected
-> B1 Macro secret-free provider-capability registry/export
-> B2 provider-realm enrollment v2
-> B3 current Claude preflight bridge
-> B4 native observation + provider_capacity.v2
-> B5 V2 acquisition + existing CF2 join/claim/replay evolution
-> B6 one managed /login OS-principal realm + restart/cold-boot proof
-> B7 one bounded real native Claude Worker
-> B8 four provider domains, one realm each
-> B9 Capacity-selected multi-realm Jobs
-> later multi-host replication
-> B10 persistent Operator Harness
-> B11 browser/computer use
```

Each step has independent current-source START and production proof.

## 16. Acceptance and no-effect boundary

This architecture remains `SPEC_ONLY` until independent current-head paired review, latest-base/material compatibility, exact-head repository validation and explicit Sol source release record `FAMILY_B_ARCHITECTURE_FROZEN`.

This records wave authorizes no login/logout/setup-token generation, provider call, capability registration, host mutation, Runtime/claim mutation, Worker launch, route activation, browser/GUI action, Ready transition or merge.