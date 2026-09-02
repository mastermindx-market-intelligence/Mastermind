# Linear Initiative Portfolio V1 — Current-Epoch Rollout Amendment

> This plan has narrow precedence over stale literal counts and missing-Project lists in `docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md`. All architecture, source-owner, one-primary-membership, idempotency, effect-unknown and no-fuzzy-match laws not explicitly changed here remain binding.

**Date:** 2026-09-02  
**Owner:** Sol  
**Status:** `DRAFT / PLAN-ONLY / NO LINEAR EFFECT`  
**Operation key:** `linear-initiative-v1-current-epoch-source-20260902-sol-001`  
**Authoring protected base:** `mastermindx-market-intelligence/Mastermind@162af533a4bcf380125895d225b6962987c3c582`  
**Current-epoch source:** `docs/superpowers/specs/2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md`  
**Base rollout plan:** `docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md`

## Goal

Complete the Chairman-approved Linear Initiative layer as one deterministic, correction-safe portfolio projection:

```text
7 strategic Initiatives
52 exact primary Project memberships
2 deliberate unassigned exceptions
0 fuzzy bindings
0 multi-parent Projects
full post-apply read-back
```

Then unlock Project Workroom WR-P0 against accepted portfolio truth. Do not let the Initiative rollout become a second organizational/runtime store or let Workrooms consume an unproven portfolio.

## Current capability ledger

At plan authoring:

- protected Initiative architecture: `SPEC_ONLY / PROTECTED` for the original epoch;
- current-epoch 52-row source consolidation: `SPEC_ONLY / DRAFT` until this carrier merges;
- Macro Initiative compiler PR #6658: `BUILT_NOT_PROVEN / PRODUCTION_INERT / DRAFT`;
- live Linear Initiative objects: `NOT_BUILT` (`0` observed);
- live Initiative memberships: `NOT_BUILT` (`0` observed);
- live Linear Project estate: `PARTIAL / STALE PROJECTION` (`50` Projects observed, four active strategy members absent);
- Project Workroom architecture: `SPEC_ONLY / PROTECTED`;
- WR-P0 planner: `NOT_BUILT`;
- AI Operating Hub end-to-end workflow: `NOT_BUILT`.

No later task may be called complete merely because an earlier PR is green or merged.

## Corrected current-epoch constants

The current strategy epoch is:

```text
Initiatives: 7
memberships: 52
exceptions: 2
group counts: 10,15,11,5,3,5,3
```

The two additions relative to the protected 2026-08-29 base design are:

```text
WS:CROSS-REPO-CONTRACT-GOVERNANCE
  -> canonical-intelligence-substrate-learning

WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
  -> legendary-alpha-discovery-timing
```

The two exceptions remain:

```text
WS:WATCHLIST-PORTFOLIO-CEO
Linear Project 9aef6461-306a-4a3c-911b-c6a4b6635a78 (Mastermind-X Linear OS)
```

If the 2026-09-02 read-only Linear witness remains unchanged, four exact Projects require creation:

```text
WS:TOP-ANATOMY
WS:EVAL-OS-EVIDENCE-VIEW
WS:CROSS-REPO-CONTRACT-GOVERNANCE
WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
```

Under that unchanged witness, the expected pre-apply drift is:

```text
initiative_missing: 7
membership_missing: 48
project_create_required: 4
hard_blockers: 0
```

After successful apply under the same frozen witness, the structural acceptance census is:

```text
visible Projects: 54
Projects with exactly one Initiative: 52
unassigned visible exceptions: 2
Initiatives: 7
```

These live-estate counts must be re-derived if Linear or Agent OS changes. The 52-row strategic source does not change merely because the observed create count changes.

---

## Task 0 — Protect the current-epoch source consolidation

**Repository:** `mastermindx-market-intelligence/Mastermind`  
**Carrier:** the one PR from `sol/linear-initiative-v1-current-epoch-source-20260902`  
**Files:** exactly the current-epoch source and this plan amendment.

1. Fresh-read protected `master`, the same-SHA Skillpack, both new files and the original `d004f5bf...` design.
2. Verify no open writer touches either new path and no newer accepted strategy source supersedes the two exact mappings.
3. Require exact-head protected `test` success and a non-author review that checks the incorporation/source-precedence law, not only prose quality.
4. Merge only with immutable-head protection.
5. Capture the exact protected merge commit. That commit becomes the `protected_revision` used by Macro #6658.

**Stop:** this task creates no Linear, Macro, Agent OS, runtime or Workroom effect.

---

## Task 1 — Repair Macro #6658 to cite the complete protected source

**Repository:** `mastermindx-market-intelligence/macro`  
**Carrier:** existing PR #6658 / existing branch only.  
**Dependency:** Task 0 protected merge.

The existing D1 malformed-witness repair remains accepted subject to exact-head proof. D2 is incomplete until the source identity names the protected current-epoch consolidation rather than the original 50-row revision alone.

Required changes, still within the existing five-path ceiling:

1. Update `config/linear_initiative_portfolio.v1.json` `source_design` to:

   ```text
   repository: mastermindx-market-intelligence/Mastermind
   path: docs/superpowers/specs/2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md
   protected_revision: <Task-0 protected merge SHA>
   ```

2. Update the compiler’s closed expected source identity to the same exact values.
3. Add a discriminating RED proving the old `d004f5bf...` locator is rejected for the 52-row epoch even when all strategy bytes/counts are otherwise valid.
4. Preserve exact strategy bytes except for the source identity unless a test proves another correction is required.
5. Preserve:
   - seven Initiative definitions;
   - 52 memberships;
   - group counts `10,15,11,5,3,5,3`;
   - two exceptions;
   - zero network and zero write behavior;
   - malformed-row refusal with collection plus absolute row index;
   - existing Agent OS CI ownership;
   - exactly five effective PR paths.
6. History-preservingly join then-current Macro `main`; never rebase, reset, force-push or reconstruct the branch.
7. Re-run focused Project/Initiative suites, compile, Agent OS validation/owner job, unrun/trigger guards, fences and full semantic CI.
8. Return a final immutable DRAFT head. Do not mark Ready or merge in the worker operation.

**Required receipt:** the emitted `strategy_provenance.source_identity` must point to the Task-0 protected source; `strategy_content_sha256` and `desired_memberships_sha256` must be reproducible from the exact committed companion.

---

## Task 2 — Independent exact-head review and Macro compiler release

A non-author reviewer must verify on the immutable final #6658 head:

- the RED genuinely distinguishes malformed-row loss and stale source epoch;
- the current protected source contains the complete 52-row authority chain;
- the companion and desired-membership digests are deterministic and independently reproducible;
- `7 / 52 / 2` and group counts are exact;
- four active missing Project identities are recognized when the committed/live witness contains them;
- immutable IDs outrank names and ambiguous/malformed evidence fails closed;
- no network, Linear write, second Project compiler, second CI job or control plane exists;
- all exact-head required checks and the actual owner pack are green;
- current Macro main is an ancestor and effective diff remains exactly five paths.

Only after that review may Sol make #6658 Ready and merge with expected-head protection.

**What merge makes true:** deterministic compiler source becomes durable as `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

**What merge does not make true:** no Project or Initiative exists because of the merge; no Linear normalization, membership, Workroom, Slack channel or production Hub workflow is proven.

---

## Task 3 — Fresh read-only Project/Initiative snapshot and dry run

**Effect:** read-only Linear plus evidence artifact only.  
**Dependency:** #6658 merged.

1. Re-pin protected Mastermind, current Macro main and the exact compiler merge.
2. Read all Linear Initiatives including stable IDs and fields.
3. Read every visible/archived Project needed by the deterministic Project compiler, including stable ID, exact name, summary, status, `updatedAt` and Initiative parents.
4. Normalize to `linear_initiative_snapshot.v1` without filtering malformed rows.
5. Run the Project compiler, then the Initiative compiler against that exact snapshot.
6. Store the snapshot and dry-run receipt in the existing `research/linear_initiative_portfolio/` evidence location; do not create another state store.
7. Verify the pre-apply stop condition:

   ```text
   unexpected Initiatives: 0
   confusingly similar Initiative names: 0
   multi-parent Project memberships: 0
   exception membership violations: 0
   unclassified active workstreams: 0
   unmapped visible Projects beyond the two exceptions: 0
   ambiguous Project bindings: 0
   malformed witness rows: 0
   desired Initiatives: 7
   desired memberships: 52
   desired exceptions: 2
   ```

8. If the current estate still matches the plan-authoring witness, additionally require exact drift `7 / 48 / 4 / 0` and exact create keys from the corrected constants above.

Any unexpected Initiative, manual relation, concurrent edit, malformed row, new active workstream or effect uncertainty stops before mutation.

---

## Task 4 — Normalize existing Projects and create only currently required active Projects

**Effect:** live Linear Project mutation.  
**Carrier:** one new stable apply operation after Task 3 passes.  
**No repository source edits during the live batch.**

1. Immediately re-read every target and compare stable ID plus `updatedAt` to the Task-3 witness.
2. Apply only the deterministic Project fields owned by `linear_portfolio_plan.py`:

   ```text
   name
   summary
   state
   ```

3. Preserve priority, lead, labels, milestones, arbitrary human description text and Issue state unless a separately accepted managed-block contract explicitly owns them.
4. Create only active, eligible, still-absent Projects returned as `project_create_required`. Under the unchanged witness those are the four exact workstreams listed above.
5. Bind every creation by exact canonical `WS:<KEY>` identity; never approximate-search by title.
6. Re-read every successful write. After each bounded tranche, re-list and verify exact state.
7. On timeout or ambiguous response, classify `EFFECT_UNKNOWN`, stop the batch, re-read the exact target and never blind retry or switch carriers.
8. Require a Project-normalization read showing all exact WS bindings unique, all managed fields correct, compatibility residue preserved as designed and the two exceptions still unassigned.

Only then may Initiative objects be created.

---

## Task 5 — Create exactly seven Initiatives

1. Re-list Initiatives immediately before creation. Any unexpected or confusingly similar object is a hard stop.
2. Create sequentially in frozen strategy-key order with exact name, summary, deterministic description, Active status, numeric priority, MastermindX lead team, unset owner, unset target date, unset health, empty labels and no parents.
3. Re-read each returned stable Initiative ID before creating the next.
4. Persist the seven ID bindings in the live apply receipt, not a second strategy store.
5. On effect uncertainty, stop and reconcile by exact returned/name identity before any retry.
6. Proceed only when a fresh list shows exactly the seven approved Initiatives and no extra object created by the operation.

---

## Task 6 — Apply exactly 52 one-primary memberships

1. Resolve every Project by stable exact ID from the accepted snapshot/create receipt.
2. Resolve every Initiative by the stable ID returned in Task 5.
3. Use replace/set semantics with exactly one Initiative ID; do not append blindly.
4. Apply group by group in the frozen order and require exact set equality after each group:

   ```text
   Canonical Intelligence Substrate & Learning: 10
   Legendary Alpha Discovery & Timing: 15
   Institutional Company & Event Intelligence: 11
   Global Markets, Regimes & Risk Command: 5
   Personal Institutional Desk: 3
   Trusted Production & Customer Platform: 5
   Autonomous AI Organization: 3
   ```

5. Explicitly verify the two exceptions have zero Initiative parents.
6. Stop on any concurrent `updatedAt` movement, unexpected parent, duplicate ID, missing ID or ambiguous write result.

---

## Task 7 — Full post-apply read-back and strategic updates

1. Capture every Initiative including Project relations and every relevant Project including Initiative parents.
2. Run the deterministic compiler against the post-apply snapshot.
3. Require zero structural drift across Initiative existence/fields, Project creates, membership missing/wrong/multi-parent, exceptions and unmapped visible Projects.
4. Under an unchanged frozen witness, require:

   ```text
   7 Initiatives
   54 visible Projects
   52 Projects with exactly one Initiative
   2 unassigned exceptions
   0 Initiative labels
   0 parent/sub-Initiative relations
   0 Initiative target dates
   0 invented Initiative owners
   ```

5. Compose one concise first status update per Initiative containing:

   ```text
   Material change
   Current strategic frontier
   Largest blocker/risk
   Next company-level dependency
   Evidence that changed the assessment
   ```

6. Set Initiative health only where fresh strategic evidence supports a Sol ruling. Otherwise leave it unset. Child-status averages, PR counts and CI percentages have zero health authority.
7. Commit the accepted post-apply snapshot/receipt through a separate records-only closeout carrier.

The live read-back, not the code merge or status update, is the portfolio acceptance evidence.

---

## Task 8 — Durable closeout and WR-P0 release gate

The closeout must record pointers, not duplicate the strategy:

- current protected source path and SHA;
- #6658 merge SHA;
- Initiative-plan semantic hash;
- strategy and desired-membership digests;
- seven Initiative names and stable Linear IDs;
- final Project/membership/exception counts;
- exact four-or-current create results;
- post-apply snapshot path/hash;
- any health values actually set;
- all unresolved disagreements;
- exact next action.

Validate Agent OS and focused/unrun ownership on the closeout head. Merge the records-only carrier after review.

Only when Tasks 0–8 are accepted may WR-P0 begin. WR-P0 remains a pure zero-network planner from:

```text
current protected Workroom strategy
+ canonical Project plan
+ accepted 7/52/2 Initiative truth
+ observed Linear/Slack snapshots
-> typed desired Workroom plan
```

WR-P0 may not create Slack channels, Canvases, Lists, bookmarks, Workflows, Linear objects, Executive Jobs, provider sessions or a new lifecycle/store.

## Global stop conditions

Return to Sol before further effect on any of:

- protected source movement that changes Initiative/Workroom authority;
- current-head or base movement on an active carrier;
- another writer touching an owned path;
- unexpected Initiative or confusingly similar name;
- unclassified active workstream;
- malformed/filtered snapshot evidence;
- duplicate or multi-parent Project identity;
- Linear write timeout or ambiguous response;
- required sixth source path on Macro #6658;
- failing exact-head required CI/review;
- any proposal to use Workrooms, Slack or Linear as a replacement truth/control plane.

## Completion standard

This rollout is complete only when the live Linear estate is structurally read back as the accepted current epoch and the durable closeout points to exact protected/source/receipt identities. Even then, the broader AI Operating Hub remains incomplete until WR-P0 and later Workroom/Steward verticals provide a real Chairman-visible, action-safe workflow over canonical truth.
