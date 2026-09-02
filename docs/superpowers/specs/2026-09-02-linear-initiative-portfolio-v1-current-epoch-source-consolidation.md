# Linear Initiative Portfolio V1 — Current-Epoch Source Consolidation

**Date:** 2026-09-02  
**Owner:** Sol / portfolio architecture  
**Chairman:** Chris  
**Status:** `DRAFT / SOURCE-LAW CONSOLIDATION / NO LIVE EFFECT`  
**Operation key:** `linear-initiative-v1-current-epoch-source-20260902-sol-001`  
**Carrier:** `Mastermind:sol/linear-initiative-v1-current-epoch-source-20260902`  
**Authoring protected base:** `mastermindx-market-intelligence/Mastermind@162af533a4bcf380125895d225b6962987c3c582`  
**Base strategic design:** `mastermindx-market-intelligence/Mastermind@d004f5bf7953e943281dff7efd8fe17a54b0cf6c:docs/superpowers/specs/2026-08-29-linear-initiative-portfolio-architecture-design.md`  
**Companion execution amendment:** `docs/superpowers/plans/2026-09-02-linear-initiative-portfolio-v1-current-epoch.md`

This record closes one precise authority-provenance gap in the Linear Initiative portfolio. It does not authorize a Linear write, Project or Initiative creation, GitHub merge, runtime action, worker dispatch, Workroom build, deployment or production claim.

## 1. Why this consolidation is required

The protected base design froze seven Initiative definitions, fifty exact Project-to-Initiative memberships and two deliberately unassigned exceptions. Two canonical active workstreams were created after that design epoch:

- `WS:CROSS-REPO-CONTRACT-GOVERNANCE`;
- `WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE`.

The deterministic Macro companion was later extended to classify those workstreams, producing the current `7 Initiatives / 52 memberships / 2 exceptions` strategy. The classifications were explicitly adjudicated by Sol on the original same-carrier dialogue and were implemented in Macro PR #6658, but the durable protected strategy source still described only the original fifty-membership epoch.

That left an unacceptable split:

```text
protected strategic source -> 50 memberships
machine-readable companion -> 52 memberships
receipt source locator     -> protected 50-membership source
```

A content digest can prove which companion bytes were consumed, but it cannot by itself prove that the two added classifications were authorized. Slack is transport/hot-state evidence, not the durable strategy authority. This consolidation makes the current epoch independently recoverable without creating a second portfolio registry.

## 2. Source-of-truth and precedence law

The base design at `d004f5bf7953e943281dff7efd8fe17a54b0cf6c` remains authoritative for:

- the seven Initiative definitions and metadata;
- the Initiative outcome, moat, completion-ruler and scope-law prose;
- the original fifty exact primary memberships;
- the one-primary-membership rule;
- the two deliberate exceptions;
- the prohibition on fuzzy/title/program/market inference;
- the Linear/Agent OS/Executive OS/GitHub/Slack source-owner boundaries.

**After this file is reviewed and merged to protected `master`, this file becomes the current v1 membership source identity.** It incorporates the base design by the exact repository, path and immutable revision above, then adds only the two rows in §3. It has narrow precedence over stale literal counts and missing-Project lists in the base design and its 2026-08-29 rollout plan.

Nothing in this file changes the seven Initiative definitions, reclassifies an existing membership, removes a membership, creates a new exception or widens Linear into canonical organizational/runtime truth.

## 3. Exact current-epoch additions

### 3.1 Cross-Repository Contract Governance

```text
workstream: WS:CROSS-REPO-CONTRACT-GOVERNANCE
primary Initiative key: canonical-intelligence-substrate-learning
primary Initiative name: Canonical Intelligence Substrate & Learning
```

**Rationale:** the workstream’s durable job is to make cross-repository producer/consumer contracts explicit, versioned, correction-safe, authority-safe and production-provable while explicitly refusing a new runtime/control plane. Its primary company outcome is reusable canonical intelligence composition, not release operations or autonomous execution.

### 3.2 Technical Opportunity Intelligence

```text
workstream: WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
primary Initiative key: legendary-alpha-discovery-timing
primary Initiative name: Legendary Alpha Discovery & Timing
```

**Rationale:** the workstream’s durable job is a multi-timeframe opportunity/timing layer that distinguishes Forming/Armed from Triggered/Confirmed and earns authority through prospective evidence. Its primary company outcome is opportunity discovery and timing.

Neither workstream is an unassigned exception. Neither classification may be inferred for a different workstream by similarity.

## 4. Final v1 structural ruler

The complete current membership source is:

```text
base 50 rows from Mastermind@d004f5bf... architecture design
+ WS:CROSS-REPO-CONTRACT-GOVERNANCE -> canonical-intelligence-substrate-learning
+ WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE -> legendary-alpha-discovery-timing
= 52 memberships
```

The exact structural counts are:

```text
Initiatives: 7
memberships: 52
unassigned exceptions: 2
parent/sub-Initiative relations: 0
Initiative labels created by v1: 0
new Project labels created by v1: 0
```

Exact membership group counts, in the frozen Initiative order, are:

```text
Canonical Intelligence Substrate & Learning:       10
Legendary Alpha Discovery & Timing:                 15
Institutional Company & Event Intelligence:         11
Global Markets, Regimes & Risk Command:              5
Personal Institutional Desk:                         3
Trusted Production & Customer Platform:              5
Autonomous AI Organization:                          3
```

The two exceptions remain exactly:

```text
WS:WATCHLIST-PORTFOLIO-CEO
Linear Project 9aef6461-306a-4a3c-911b-c6a4b6635a78 (Mastermind-X Linear OS)
```

## 5. Current live-witness consequence

The read-only Linear witness on 2026-09-02 showed:

```text
visible Projects: 50
Initiatives: 0
Project -> Initiative memberships: 0
```

All fifty visible Projects were unique by their current visible identities, and the two frozen exceptions remained present and unassigned. The four currently active strategy members absent as Linear Projects were:

```text
WS:TOP-ANATOMY
WS:EVAL-OS-EVIDENCE-VIEW
WS:CROSS-REPO-CONTRACT-GOVERNANCE
WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
```

If that live witness remains unchanged at the accepted dry-run boundary, the deterministic pre-apply signature is:

```text
initiative_missing: 7
membership_missing: 48
project_create_required: 4
hard_blockers: 0
```

These are witness-derived values, not permanent quotas. Any material Linear or Agent OS change before apply requires a fresh snapshot and recompilation. The strategic source remains 52 memberships even when the observed create/drift counts change.

## 6. Protected source identity and receipt contract

Once this record lands, the machine-readable strategy companion must identify the protected source as:

```text
repository: mastermindx-market-intelligence/Mastermind
path: docs/superpowers/specs/2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md
protected_revision: <the exact protected merge commit containing this file>
```

A source identity that still points only to `d004f5bf7953e943281dff7efd8fe17a54b0cf6c` is stale for the 52-membership epoch and must not be accepted as complete provenance.

The deterministic compiler receipt must continue to bind:

- the exact structured protected source identity;
- the exact consumed strategy companion bytes through `strategy_content_sha256`;
- the exact desired membership rows through `desired_memberships_sha256`;
- the Initiative-plan semantic hash;
- the Project-plan semantic hash;
- the exact desired/group/exception/drift counts.

A reviewer must be able to locate this protected source, follow its immutable base-source incorporation, reproduce the companion and membership digests, and distinguish the approved 52-row epoch from the original 50-row epoch without access to process-local state.

The compiler remains deterministic, zero-network and zero-write. It validates source identity but does not call GitHub at runtime. GitHub protection/review proves the source revision externally.

## 7. Failure and correction behavior

The current epoch fails closed on:

- missing or malformed source identity;
- source path/repository mismatch;
- non-40-hex protected revision;
- source identity still naming the 50-row base epoch while the companion contains 52 rows;
- any membership count other than 52;
- any group counts other than `10,15,11,5,3,5,3`;
- either added workstream missing, duplicated, mapped to another Initiative or also listed as an exception;
- any change to the two frozen exceptions;
- any unknown active workstream absent from both the exact membership map and approved exception set;
- malformed, ambiguous or effect-unknown live evidence.

A future membership change requires a new durable protected source amendment or consolidation. Editing the static companion alone is insufficient. A Slack ruling or PR comment may preserve decision evidence, but it does not replace the protected strategy source.

## 8. No-rebuild and authority boundaries

Preserve all existing owners:

- Agent OS owns durable workstream identity and organizational state;
- `linear_portfolio_plan.py` remains the Project normalization compiler;
- `linear_initiative_plan.py` remains the deterministic Initiative desired-state/drift compiler;
- Linear remains the selected human portfolio projection;
- Executive OS remains Job/Attempt/Worker/Event truth;
- GitHub remains implementation/evidence truth;
- Slack remains transport/hot-state visibility;
- Project Workrooms remain downstream consumers and may not create a second Initiative strategy store.

This source consolidation introduces no database, queue, lifecycle, router, identity service, retry plane, watcher, provider binding or SaaS write path.

## 9. Release and completion boundary

Merging this record to protected `master` makes only the current 52-membership strategic source durable. It does not make the Macro compiler accepted, create any Linear object, normalize any Project, implement WR-P0, create a Slack channel, or prove the AI Operating Hub live.

The next dependency is exact and sequential:

```text
protect this source consolidation
-> update Macro PR #6658 to cite its exact protected revision
-> re-prove and independently review #6658
-> merge #6658 as BUILT_NOT_PROVEN / PRODUCTION_INERT
-> fresh dry run
-> one bounded Linear apply + full read-back
-> durable closeout
-> start WR-P0 against accepted 7/52/2 portfolio truth
```
