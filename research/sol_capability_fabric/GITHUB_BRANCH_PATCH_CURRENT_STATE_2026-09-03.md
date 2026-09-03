# SCF GitHub Branch-Patch — Current-State Reconciliation

**Observed/recorded:** 2026-09-03  
**Operation:** `mastermind-sol-capability-fabric-ghp1-20260902-sol-001`  
**Carrier:** `sol/sol-capability-fabric-ghp1-20260902`  
**Pickup protected source:** `068b83883915919802894fc9c31e7e7757100eb9`  
**State:** `SOURCE_CANDIDATE / PRODUCTION_INERT / VERIFICATION_PENDING`

## Correction of non-canonical chat claims

A prior chat response described GHP1–GHP4 as built and referenced locally generated status/bundle artifacts. Those artifacts are not GitHub implementation truth and do not establish source, deployment, installation, app publication, GitHub App enrollment, or a production canary.

Canonical GitHub truth at this operation's pickup was:

```text
one branch existed after Sol created it
no GHP implementation PR existed
no live apply-patch tool existed on the connected GitHub surface
no custom app generation was installed or proven
```

This carrier is the first canonical GHP source candidate. Until GitHub exact-head checks, review, release, installation and a real canary establish otherwise, capability states remain:

```text
strict pure patch materializer source     BUILT_NOT_PROVEN only after source proof
model-facing GitHub patch owner app       NOT_BUILT
custom app deployment/enrollment          NOT_BUILT
real >10,000-line production canary        NOT_BUILT
end-to-end ChatGPT branch patch            NOT_BUILT
```

## What this carrier actually contains

This source candidate adds only:

```text
control_plane/github_branch_patch.py
tests/test_github_branch_patch.py
docs/superpowers/specs/2026-09-03-sol-capability-fabric-github-branch-patch-design.md
docs/superpowers/plans/2026-09-03-sol-capability-fabric-ghp1.md
research/sol_capability_fabric/GITHUB_BRANCH_PATCH_CURRENT_STATE_2026-09-03.md
```

The intended capability is a pure, strict, deterministic materializer over already-fetched exact bytes. It performs no GitHub action and is not an MCP/custom app.

## Remaining dependency chain

```text
GHP1 exact-head source proof and protection
+ required SCF-GH1 dependency resolution
-> separately authorized GHP2 owner app
-> separately authorized GHP3 deployment/enrollment
-> separately authorized GHP4 disposable real-path canary
-> promotion decision
```

No downstream child inherits START, carrier, receiver assignment, merge permission, app publication permission, credential access or production arming from this record.

## Exact next action

Open one Draft/Hold PR for this carrier, allow hosted tests/security checks to inspect the exact candidate head, repair any failure on the same branch, obtain independent exact-head adversarial review, reconcile current protected master, and only then adjudicate source release.
