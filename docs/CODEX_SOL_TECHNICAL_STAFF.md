# Codex-Sol Technical Staff

## Status

This document defines the **identity and authority composition** for using Codex as a bounded technical/CTO-style reasoning arm of Sol. It does not create a new Executive seat, Job role, Worker type, provider route, Wake transport, Slack identity, credential, host process, or production arming.

Canonical architecture: `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md` from Mastermind #172.

## Identity composition

A Codex-Sol continuation is represented by existing identities that remain deliberately separate:

```text
accountable executive seat:  ceo
technical duty:              existing orchestration role + bounded commission/effective grant
reasoning surface:           codex when Codex performs the reasoning
Executive Worker:            execution identity only when a Worker/Attempt actually runs
provider/model/account:      execution/capacity evidence only
provider session/thread:     runtime evidence only
Slack principal:             communication identity only
```

`sol_technical_staff` is a human-readable duty label. It is **not** a new database field, executive seat, lifecycle role, provider class, Worker authority, or routing authority.

The durable Executive seats remain exactly:

```text
coo | ceo | chairman
```

The existing bounded orchestration duties remain:

```text
plan | work | review | repair | aggregation
```

A technical continuation uses whichever existing duty truthfully describes the work. Naming the model or provider must never widen the authority granted by the parent operation.

## What Codex-Sol may do

When the current Chairman/Sol authority packet and effective grant permit it, a Codex-Sol technical arm may:

- perform repository and runtime archaeology;
- turn an already-approved architecture into bounded technical plans;
- make architecture-preserving implementation decisions inside an explicit commission;
- execute ordinary test/review/repair loops within that bounded technical scope;
- inspect CI and runtime evidence against a frozen acceptance law;
- delegate strict-subset child work through the canonical Executive lineage when that delegation path is available;
- return a technical recommendation, review finding, or bounded implementation result to Sol.

## Return boundaries

A Codex-Sol technical arm must return to the accountable Sol/Chairman authority boundary before it materially changes any of the following:

- Chairman intent or the primary product/user outcome;
- canonical ownership or system architecture;
- lifecycle, queue, identity, memory, grounding, retry, graph, publication, or authority planes;
- rights, legal, material spend, credentials, security posture, or destructive operations;
- merge/deploy/trading/capital authority not already present in the effective grant;
- final executive acceptance of a material program.

Model confidence, provider capability, a successful tool invocation, a Slack sender identity, or an available native app does not grant any of those authorities.

## Provider and Worker independence

A CEO-owned technical Job remains CEO-owned regardless of which lawful provider or Worker later executes a bounded Attempt. The identities answer different questions:

```text
owner_seat        -> which executive role is accountable?
orchestration_role-> which bounded duty is being performed?
effective grant   -> what is actually permitted?
Worker             -> which governed execution identity handled the Attempt?
provider/model     -> which execution implementation was used?
provider session   -> which runtime invocation/thread produced evidence?
Slack principal    -> who communicated?
```

Changing one identity must not silently rewrite another.

## Routing boundary

The Model Router answers suitability/execution-shape questions. It does not mint Executive Jobs, set `owner_seat`, grant authority, choose a Slack principal, or make a provider identity authoritative.

Provider-neutral quality/equivalence tiers belong to the separate RF1 Capacity Fabric wave. Capacity/cost selection may rank only among already-lawful candidates; it may never promote a cheaper but inadequate model into an executive or higher-quality task.

## Wake boundary

Actual continuation/wake mechanics are owned by Executive Wake Fabric and the separate Wake PR3 carrier. This role document does not implement or arm Wake delivery. A runtime binding or native Codex thread is an address for a reasoning surface, not the canonical Sol identity.

## Slack boundary

ChatGPT1/2/3 may remain Sol-seat communication principals. A Codex-Sol continuation may communicate through an appropriate Sol-facing principal for human-readable company conversation, but machine-consumable authority must be derived from the exact Executive seat, commission/effective grant, Worker/Attempt lineage, and runtime evidence—not from the Slack username.

## Conformance proof

`tests/test_codex_sol_identity_conformance.py` pins the critical invariants:

- Codex versus ChatGPT reasoning surface does not change the accountable CEO seat;
- a Codex/model identity cannot create a CEO-owned Job without typed executive provenance;
- Slack-like prose cannot select a seat or grant authority;
- Executive Job ownership is structurally separate from Worker/provider/session identity;
- existing orchestration roles remain unchanged;
- Model Router contracts contain suitability fields, not executive authority fields;
- child delegation remains shrink-only under existing parent-grant law;
- provider/runtime identities cannot become Job-owner fields.

If a future provider/harness change falsifies one of those laws, repair the canonical existing owner. Do not add a parallel Sol identity or provider-derived authority plane.
