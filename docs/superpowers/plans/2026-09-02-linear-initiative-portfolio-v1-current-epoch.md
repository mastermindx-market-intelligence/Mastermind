# Linear Initiative Portfolio V1 — Current-Epoch Rollout Amendment

> This plan has narrow precedence over stale literal counts, membership totals and missing-Project lists in `docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md`. All architecture, source-owner, one-primary-membership, idempotency, effect-unknown and no-fuzzy-match laws not explicitly changed here remain binding.

**Date:** 2026-09-02  
**Owner:** Sol  
**Status:** `DRAFT / PLAN-ONLY / NO LINEAR EFFECT`  
**Operation key:** `linear-initiative-v1-current-epoch-source-20260902-sol-001`  
**Initial branch base:** `mastermindx-market-intelligence/Mastermind@162af533a4bcf380125895d225b6962987c3c582`  
**Current procedure re-pin:** `mastermindx-market-intelligence/Mastermind@24fa9bc4acfbffb77f09193dd50d1ee8f90bcbf8`  
**Agent OS census pin:** `mastermindx-market-intelligence/macro@818451efac2c1a95917f6110fabb024054911356`  
**Current-epoch source:** `docs/superpowers/specs/2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md`  
**Base rollout plan:** `docs/superpowers/plans/2026-08-29-linear-initiative-portfolio-rollout.md`

## Goal

Complete the Chairman-approved Linear Initiative layer as one deterministic, correction-safe portfolio projection:

```text
7 strategic Initiatives
58 exact primary Project memberships
2 deliberate unassigned exceptions
0 fuzzy bindings
0 multi-parent Projects
full post-apply read-back
```

Then unlock Project Workroom WR-P0 against accepted portfolio truth. Do not let the Initiative rollout become a second organizational/runtime store or let Workrooms consume an unproven portfolio.

## Current capability ledger

At this plan revision:

- protected Initiative architecture: `SPEC_ONLY / PROTECTED` for the original 50-row epoch;
- current-epoch 58-row source consolidation: `SPEC_ONLY / DRAFT` until the source carrier merges;
- Macro Initiative compiler PR #6658: `BUILT_NOT_PROVEN / PRODUCTION_INERT / DRAFT`, but statically frozen at the stale 52-row epoch;
- live Linear Initiative objects: `NOT_BUILT` (`0` observed);
- live Initiative memberships: `NOT_BUILT` (`0` observed);
- live Linear Project estate: `PARTIAL / STALE PROJECTION` (`50` Projects observed, ten portfolio-eligible strategy members absent);
- Project Workroom architecture: `SPEC_ONLY / PROTECTED`;
- WR-P0 planner: `NOT_BUILT`;
- AI Operating Hub end-to-end workflow: `NOT_BUILT`.

No later task may be called complete merely because an earlier PR is green or merged.

## Corrected current-epoch constants

The strategy epoch pinned by the source consolidation is:

```text
Initiatives: 7
memberships: 58
exceptions: 2
group counts: 10,16,11,5,4,7,5
```

The eight additions relative to the protected 2026-08-29 base design are:

```text
WS:CROSS-REPO-CONTRACT-GOVERNANCE
  -> canonical-intelligence-substrate-learning

WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
  -> legendary-alpha-discovery-timing

WS:AGENT-EVAL-FABRIC
  -> autonomous-ai-organization

WS:EXECUTIVE-OS-DISASTER-RECOVERY
  -> trusted-production-customer-platform

WS:OPERATION-ASSURANCE
  -> autonomous-ai-organization

WS:PROPHET-CANDIDATE-ADDED-DATE
  -> legendary-alpha-discovery-timing

WS:REACTIVE-PROJECTION
  -> personal-institutional-desk

WS:REPRODUCIBLE-WORKER-ENVIRONMENTS
  -> trusted-production-customer-platform
```

The two exceptions remain:

```text
WS:WATCHLIST-PORTFOLIO-CEO
Linear Project 9aef6461-306a-4a3c-911b-c6a4b6635a78 (Mastermind-X Linear OS)
```

If the 2026-09-02 read-only Linear witness and the pinned Agent OS eligibility universe remain unchanged, ten exact Projects require creation:

```text
WS:TOP-ANATOMY
WS:EVAL-OS-EVIDENCE-VIEW
WS:CROSS-REPO-CONTRACT-GOVERNANCE
WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE
WS:AGENT-EVAL-FABRIC
WS:EXECUTIVE-OS-DISASTER-RECOVERY
WS:OPERATION-ASSURANCE
WS:PROPHET-CANDIDATE-ADDED-DATE
WS:REACTIVE-PROJECTION
WS:REPRODUCIBLE-WORKER-ENVIRONMENTS
```

Under that unchanged witness, the expected pre-apply drift is:

```text
initiative_missing: 7
membership_missing: 48
project_create_required: 10
hard_blockers: 0
```

After successful apply under the same frozen witness, the structural acceptance census is:

```text
visible Projects: 60
Projects with exactly one Initiative: 58
unassigned visible exceptions: 2
Initiatives: 7
```

These live-estate counts must be re-derived if Linear or Agent OS changes. The 58-row strategic source does not change merely because observed create or drift counts change; a new portfolio-eligible workstream does require a new protected strategy epoch.

---

## Task 0 — Protect the complete current-epoch source consolidation

**Repository:** `mastermindx-market-intelligence/Mastermind`  
**Carrier:** the one PR from `sol/linear-initiative-v1-current-epoch-source-20260902`  
**Files:** exactly the current-epoch source and this plan amendment.

1. Fresh-read protected `master`, the same-SHA Skillpack, both current-epoch files and the original `d004f5bf...` design.
2. Verify the Agent OS census at `Macro@818451ef...` and prove all portfolio-eligible direct workstreams equal:

   ```text
   58 strategy memberships
   + WS:WATCHLIST-PORTFOLIO-CEO exception
   ```

   Review candidates at `status: proposed` are subject to the same set-equality law.
3. Verify all eight added classifications against their current direct Agent OS objectives; no title/program/owner inference may substitute for the explicit protected mapping.
4. Verify no open writer touches either new path and no newer accepted strategy source supersedes this epoch.
5. History-preservingly reconcile current protected `master`; do not reset/rebase/force over the source branch.
6. Require exact-head protected `test` success and a non-author review that checks the set census, mapping rationales, arithmetic, precedence and provenance law—not only prose quality.
7. Merge only with immutable-head protection.
8. Capture the exact protected merge commit. That commit becomes the `protected_revision` used by the Macro strategy companion.

**Stop:** this task creates no Linear, Macro, Agent OS, runtime or Workroom effect.

---

## Task 1 — Close the stale 52-preserving Macro child operation

The started worker operation `linear-initiative-6658-release-repair-r4-20260902-sol-001` was explicitly scoped to preserve 52 memberships. The current 58-row source is a material semantic change, not a source-locator-only repair.

After the source carrier is stable enough to make the ruling durable:

1. fresh-read the exact R4 Slack carrier and Macro PR #6658;
2. reconcile the current branch head and all effects;
3. issue terminal `SOL CLOSED / STOP` for R4;
4. tell the worker to stop, remove only the exact R4 child source from its watcher, and make no further source/branch/Linear effect;
5. preserve the existing branch and all D1/D2 work as implementation evidence;
6. do not reinterpret R4 as permission to add six memberships.

Any subsequent Macro work uses a fresh operation key, commission, pickup and watcher cycle, while retaining the same sole PR/branch carrier after collision reconciliation.

---

## Task 2 — Advance the same Macro PR to the protected 58-row epoch

**Repository:** `mastermindx-market-intelligence/macro`  
**Carrier:** existing PR #6658 and existing branch only.  
**Dependency:** Task 0 protected merge and Task 1 terminal R4 closure.  
**Operation:** one fresh bounded 58-row compiler repair operation.

The D1 malformed-witness repair and D2 receipt structure remain useful, but the implementation must move from a stale 52-row strategy to the complete protected 58-row epoch.

Required changes, still within the existing five-path ceiling:

1. Update `config/linear_initiative_portfolio.v1.json`:
   - add exactly the six mappings not already present in the 52-row companion;
   - preserve the two historical post-base mappings;
   - preserve all original 50 mappings and all seven Initiative definitions;
   - set `source_design` to:

     ```text
     repository: mastermindx-market-intelligence/Mastermind
     path: docs/superpowers/specs/2026-09-02-linear-initiative-portfolio-v1-current-epoch-source-consolidation.md
     protected_revision: <Task-0 protected merge SHA>
     ```

2. Update the compiler’s closed expected source identity, membership count and exact group-count law to the same current epoch.
3. Add discriminating RED tests proving:
   - the old `d004f5bf...` 50-row locator is rejected;
   - the intermediate 52-row strategy is rejected against the current Project plan;
   - omitting or misclassifying any one of the six new rows fails closed;
   - the exact 58-row set compiles deterministically;
   - a new eligible Project-plan workstream outside memberships/exceptions produces `strategy_unmapped_active_workstream`.
4. Preserve:
   - malformed-row refusal with collection plus absolute row index;
   - immutable-ID-over-name law;
   - exact two exceptions;
   - zero network and zero write behavior;
   - existing Agent OS CI ownership;
   - the same overall Initiative-plan semantic hash contract;
   - exactly five effective PR paths.
5. History-preservingly join then-current Macro `main`; never rebase, reset, force-push or reconstruct the branch.
6. Re-run focused Project/Initiative suites, compile, Agent OS validation/owner job, unrun/trigger guards, fences and full semantic CI.
7. Update the PR body to current protected/source/head/base/proof identities and accurate `7 / 58 / 2` capability language.
8. Return a final immutable DRAFT head. Do not mark Ready or merge in the worker operation.

**Required receipt:** emitted `strategy_provenance.source_identity` points to the Task-0 protected source; `strategy_content_sha256` and `desired_memberships_sha256` are independently reproducible from the exact committed 58-row companion.

---

## Task 3 — Independent exact-head review and Macro compiler release

A non-author reviewer must verify on the immutable final #6658 head:

- the REDs genuinely distinguish malformed-row loss, stale source epoch, stale membership count and missing current workstreams;
- the current protected source contains the complete 58-row authority chain;
- the companion and desired-membership digests are deterministic and independently reproducible;
- `7 / 58 / 2` and group counts `10,16,11,5,4,7,5` are exact;
- ten active missing Project identities are recognized when the committed/live witness contains them;
- every eligible Project-plan workstream is mapped or exactly excepted;
- immutable IDs outrank names and ambiguous/malformed evidence fails closed;
- no network, Linear write, second Project compiler, second CI job or control plane exists;
- all exact-head required checks and the actual owner pack are green;
- current Macro main is an ancestor and the effective diff remains exactly five paths.

Only after that review may Sol make #6658 Ready and merge with expected-head protection.

**What merge makes true:** deterministic compiler source becomes durable as `BUILT_NOT_PROVEN / PRODUCTION_INERT`.

**What merge does not make true:** no Project or Initiative exists because of the merge; no Linear normalization, membership, Workroom, Slack channel or production Hub workflow is proven.

---

## Task 4 — Fresh read-only Project/Initiative snapshot and dry run

**Effect:** read-only Linear plus evidence artifact only.  
**Dependency:** #6658 merged.

1. Re-pin protected Mastermind, current Macro main, the exact compiler merge and the complete current Agent OS eligibility census.
2. Read every Linear Initiative including stable IDs and fields.
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
   unclassified eligible workstreams: 0
   unmapped visible Projects beyond the two exceptions: 0
   ambiguous Project bindings: 0
   malformed witness rows: 0
   desired Initiatives: 7
   desired memberships: 58
   desired exceptions: 2
   ```

8. If the current estate still matches the plan-authoring witness, additionally require exact drift `7 / 48 / 10 / 0` and the ten exact create keys listed above.

Any unexpected Initiative, manual relation, concurrent edit, malformed row, new eligible workstream or effect uncertainty stops before mutation.

---

## Task 5 — Normalize existing Projects and create only currently required eligible Projects

**Effect:** live Linear Project mutation.  
**Carrier:** one new stable apply operation after Task 4 passes.  
**No repository source edits during the live batch.**

1. Immediately re-read every target and compare stable ID plus `updatedAt` to the Task-4 witness.
2. Apply only deterministic Project fields owned by `linear_portfolio_plan.py`:

   ```text
   name
   summary
   state
   ```

3. Preserve priority, lead, labels, milestones, arbitrary human description text and Issue state unless a separately accepted managed-block contract explicitly owns them.
4. Create only eligible, still-absent Projects returned as `project_create_required`. Under the unchanged witness those are the ten exact workstreams listed above.
5. Bind every creation by exact canonical `WS:<KEY>` identity; never approximate-search by title.
6. Re-read every successful write. After each bounded tranche, re-list and verify exact state.
7. On timeout or ambiguous response, classify `EFFECT_UNKNOWN`, stop the batch, re-read the exact target and never blind retry or switch carriers.
8. Require a Project-normalization read showing all exact WS bindings unique, all managed fields correct, compatibility residue preserved as designed and the two exceptions still unassigned.

Only then may Initiative objects be created.

---

## Task 6 — Create exactly seven Initiatives

1. Re-list Initiatives immediately before creation. Any unexpected or confusingly similar object is a hard stop.
2. Create sequentially in frozen strategy-key order with exact name, summary, deterministic description, Active status, numeric priority, MastermindX lead team, unset owner, unset target date, unset health, empty labels and no parents.
3. Re-read each returned stable Initiative ID before creating the next.
4. Persist the seven ID bindings in the live apply receipt, not a second strategy store.
5. On effect uncertainty, stop and reconcile by exact returned/name identity before any retry.
6. Proceed only when a fresh list shows exactly the seven approved Initiatives and no extra object created by the operation.

---

## Task 7 — Apply exactly 58 one-primary memberships

1. Resolve every Project by stable exact ID from the accepted snapshot/create receipt.
2. Resolve every Initiative by the stable ID returned in Task 6.
3. Use replace/set semantics with exactly one Initiative ID; do not append blindly.
4. Apply group by group in the frozen order and require exact set equality after each group:

   ```text
   Canonical Intelligence Substrate & Learning: 10
   Legendary Alpha Discovery & Timing: 16
   Institutional Company & Event Intelligence: 11
   Global Markets, Regimes & Risk Command: 5
   Personal Institutional Desk: 4
   Trusted Production & Customer Platform: 7
   Autonomous AI Organization: 5
   ```

5. Explicitly verify the two exceptions have zero Initiative parents.
6. Stop on any concurrent `updatedAt` movement, unexpected parent, duplicate ID, missing ID or ambiguous write result.

---

## Task 8 — Full post-apply read-back and strategic updates

1. Capture every Initiative including Project relations and every relevant Project including Initiative parents.
2. Run the deterministic compiler against the post-apply snapshot.
3. Require zero structural drift across Initiative existence/fields, Project creates, membership missing/wrong/multi-parent, exceptions and unmapped visible Projects.
4. Under an unchanged frozen witness, require:

   ```text
   7 Initiatives
   60 visible Projects
   58 Projects with exactly one Initiative
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

## Task 9 — Durable closeout and WR-P0 release gate

The closeout records pointers, not a duplicate strategy:

- current protected source path and SHA;
- #6658 merge SHA;
- Initiative-plan semantic hash;
- strategy and desired-membership digests;
- seven Initiative names and stable Linear IDs;
- final Project, membership and exception counts;
- exact currently required Project-create results;
- post-apply snapshot path/hash;
- health values actually set, if any;
- all unresolved disagreements;
- exact next action.

Validate Agent OS and focused/unrun ownership on the closeout head. Merge the records-only carrier after review.

Only when Tasks 0–9 are accepted may WR-P0 begin. WR-P0 remains a pure zero-network planner from:

```text
current protected Workroom strategy
+ canonical Project plan
+ accepted 7/58/2 Initiative truth
+ observed Linear/Slack snapshots
-> typed desired Workroom plan
```

WR-P0 may not create Slack channels, Canvases, Lists, bookmarks, Workflows, Linear objects, Executive Jobs, provider sessions or a new lifecycle/store.

## Global stop conditions

Return to Sol before further effect on any of:

- protected source movement that changes Initiative/Workroom authority;
- current-head or base movement on an active carrier;
- another writer touching an owned path;
- new portfolio-eligible Agent OS workstream after the frozen census;
- unexpected Initiative or confusingly similar name;
- malformed or filtered snapshot evidence;
- duplicate or multi-parent Project identity;
- Linear write timeout or ambiguous response;
- required sixth source path on Macro #6658;
- failing exact-head required CI/review;
- any proposal to use Workrooms, Slack or Linear as a replacement truth/control plane.

## Completion standard

This rollout is complete only when the live Linear estate is structurally read back as the accepted current epoch and the durable closeout points to exact protected/source/receipt identities. Even then, the broader AI Operating Hub remains incomplete until WR-P0 and later Workroom/Steward verticals provide a real Chairman-visible, action-safe workflow over canonical truth.
