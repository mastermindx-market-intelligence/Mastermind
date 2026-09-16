# OCR-2C Family B — Boot Currentness and FP1B Physical Composition Correction

**Date:** 2026-09-16
**Owner:** Sol / existing `WS:EXECUTIVE-CAPACITY-FABRIC`
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`
**Review operation held:** `ocr2c-family-b-paired-architecture-review-r2-20260916-sol-001` on `C0BSBM78V1N/1789588297.647319`.
**Status:** `CONCRETE-DEFECT REPAIR CANDIDATE / RECORDS ONLY / SPEC_ONLY / HOLD FOR FRESH GATES AND R2 REVIEW`
**Paired Macro decision:** `agentos/decisions/DEC-NATIVE-CLAUDE-FAMILY-B-BOOT-CURRENTNESS-PHYSICAL-COMPOSITION.md`.

## 1. Defect and narrow precedence

Current FP1B source qualifies exact `host_id + boot_id + capacity_pool_ref + qualification_revision` and refuses wrong host, stale boot, wrong pool, stale/incomplete host-capacity evidence and mismatched BEGIN pressure evidence. Family B kept B2 enrollment stable correctly, but B3/B4 readiness carried only `host_ref + realm_generation`, and B5 validated only provider/realm generations. That allowed an old-boot readiness fact to remain structurally eligible after reboot while FP1B had advanced to another physical generation.

This correction supersedes only conflicting boot-currentness and physical-composition clauses in the pending Family-B design, implementation plan, multi-host amendment, observation-acquisition correction and paired Macro records. It does not alter provider identity, quota normalization, B2 enrollment ownership, FP1B policy, ResourceBroker ordering, Executive lifecycle, CF2 claim ownership or historical replay law.

## 2. Stable B2 enrollment; boot-bound B3/B4 readiness

`boot_ref` is the existing opaque boot-generation reference owned by FP1B/host-capacity. It is not provider identity, realm enrollment identity, quota identity or another generation owner.

An ordinary reboot changes neither `capacity_capability_id + capability_generation` nor `host_ref + capacity_capability_id + realm_generation`. B2 therefore does not add `boot_ref`, and reboot alone advances neither provider nor realm generation.

B3 provider-work-free readiness and B4 native observation must bind exact current:

```text
host_ref
boot_ref
capacity_capability_id
capability_generation
realm_generation
enrollment/preflight/source receipt identity
observed_at + freshness identity
```

When the current host boot changes, evidence from the older `boot_ref` becomes ineligible for new execution. It remains valid historical evidence.

## 3. Provider Capacity V2 carries provenance, not physical authority

Native V2 `realm_binding` is:

```text
{
  capability_generation,
  boot_ref,
  realm_generation,
  enrollment_receipt_digest
}
```

`boot_ref` lets consumers detect old-boot readiness. Macro does not qualify a physical host, pool, pressure state or BEGIN. Presence of a matching-looking `boot_ref` in Provider Capacity cannot substitute for FP1B acquisition and validation.

Provider quota key remains `(capacity_capability_id, capability_generation)`. Provider realm enrollment key remains `(host_ref, capacity_capability_id, realm_generation)`. Current readiness provenance additionally binds `boot_ref`.

## 4. B5 separately composes incumbent FP1B authority

Before a selected native realm can be consumed into the existing claim/BEGIN path, B5 must separately acquire and validate:

```text
Provider Capacity V2 + boot-bound realm readiness
AND
current FP1B host qualification + fresh host-capacity/pressure evidence
```

The composition requires byte-exact:

```text
provider/readiness host_ref == FP1B host_id
provider/readiness boot_ref == FP1B boot_id
current capacity_pool_ref
current qualification_revision
fresh host-capacity snapshot bound to the same host/boot/pool
BEGIN pressure snapshot matching the host-capacity HP0 binding
```

Provider evidence and physical evidence remain separate authorities and are bound separately into the existing CF2/Executive claim and ResourceBroker path. Family B creates no host sampler, physical policy, qualification database, observation store, new receipt owner, scheduler, generation, transaction or claim plane. Current FP1B ordering remains controlling.

The claim/effect evidence successor preserves accepted provider identities and the incumbent physical request/result identities, including the physical request fingerprint/policy binding, `capacity_pool_ref`, `host_qualification_revision`, host-capacity digest/freshness and BEGIN pressure digest. Exact implementation field placement is selected by the existing owners at B5 START; no Family-B-owned duplicate physical document is authorized.

## 5. Scope and replay

A stale boot, wrong pool, wrong qualification revision, stale/incomplete physical snapshot or physical pressure mismatch is realm/host-local ineligibility. It must not cool the provider domain or rewrite provider quota.

Historical replay returns the exact provider and physical evidence accepted at the historical claim. It does not re-read current Provider Capacity, current realm readiness, current FP1B qualification or current host telemetry.

## 6. Required discriminators

Later implementation and R2 review must kill at least:

```text
pre-reboot readiness accepted after current boot_ref changes
missing/noncanonical boot_ref accepted for a native V2 row
reboot advances capability_generation or realm_generation
Provider Capacity boot_ref is accepted as physical qualification
provider host_ref differs from FP1B host_id
provider boot_ref differs from FP1B boot_id
wrong or stale capacity_pool_ref / qualification_revision accepted
stale/incomplete host-capacity evidence accepted
host-capacity and BEGIN pressure snapshots are not the same HP0 generation
physical host failure is widened to provider-domain cooling
historical replay re-reads current physical state
a new host sampler, physical store, receipt owner, generation or claim plane appears
```

## 7. Gate and no-effect boundary

The existing R2 review operation remains PRE_START and unbound. The prior paired heads are superseded for review after this correction publishes. Fresh exact-head checks and current-base/material compatibility are required before one independent reviewer may START on the replacement heads.

This record creates no B1 registry, provider registration, login/logout, credential read/change, realm enrollment, observation adapter, Provider Capacity snapshot, physical qualification, claim, RuntimeBinding, Worker, route, host permission, browser/GUI action, Ready transition or merge authority. B0 remains `SPEC_ONLY / HOLD`; B1+ remains unstarted.
