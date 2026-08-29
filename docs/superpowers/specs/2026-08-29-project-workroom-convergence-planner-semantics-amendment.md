# Project Workroom Convergence — Planner Semantics Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Status:** `SPEC_ONLY / CHAIRMAN-APPROVED / RECORDS_ONLY`  
**Operation key:** `project-workroom-convergence-20260829-sol-001`  
**Carrier:** Mastermind PR #232 / `sol/project-workroom-convergence-20260829`  
**Current protected release basis:** `mastermindx-market-intelligence/Mastermind@1b99ea1d0a6232e11fd46915d348685764cb00cf`  
**Authority:** narrow precedence correction for WR-P0 action emission, rollout/apply eligibility, summary semantics and rename behavior. It supersedes conflicting generic wording in the Workroom design, current-state amendment and implementation plan. It creates no Slack, Linear, runtime or credential mutation authority.

---

## 1. Records carrier file census

The exact PR #232 records-only carrier now contains four files:

```text
docs/superpowers/specs/2026-08-29-project-workroom-convergence-design.md
docs/superpowers/specs/2026-08-29-project-workroom-convergence-current-state-amendment.md
docs/superpowers/specs/2026-08-29-project-workroom-convergence-planner-semantics-amendment.md
docs/superpowers/plans/2026-08-29-project-workroom-convergence.md
```

No runtime, config, test, Agent OS, Linear, Slack, credential or production path is modified by this records carrier.

---

## 2. Shadow is planning-only

A strategy row with:

```text
rollout_mode = shadow
```

may compile a truthful desired-state/drift plan and evidence receipt, but it is never live-apply eligible.

The Workroom plan must distinguish:

```text
planning eligibility
live apply eligibility
```

A row may be planning-eligible when:

- it is an exact active project in `linear_portfolio_plan.v1`;
- its exact Linear Project/Initiative observations are available and consistent;
- no target-specific portfolio warning/refusal exists; and
- its Slack observation is exact or absent in a way the planner can describe.

It is live-apply eligible only when all planning gates pass **and**:

```text
rollout_mode in {canary, active}
```

`shadow` never becomes apply authority merely because all observations are clean.

The planner must emit a source-attributed hold such as:

```text
shadow_mode_no_apply
```

or an equivalent closed-schema field that makes the non-applicability explicit. It must not report a shadow row as `apply_eligible=true`.

---

## 3. Summary semantics

The plan summary must contain both:

```text
eligible_workroom_count
apply_eligible_workroom_count
shadow_workroom_count
```

Exact meaning:

- `eligible_workroom_count` = rows that are organizationally/planning eligible after exact Agent OS portfolio, Linear and Slack observation checks;
- `apply_eligible_workroom_count` = rows whose planning checks pass and whose rollout mode permits a live actuator;
- `shadow_workroom_count` = strategy rows whose rollout mode is `shadow`, regardless of whether another hold also exists.

Do not use `eligible_workroom_count` as a synonym for “safe to mutate Slack.”

---

## 4. Action emission is bounded by canonical eligibility and exact remote identity

### 4.1 Active exact Project rows

Only a workstream found exactly once in `active_projects` may emit normal create/update Workroom actions, and only after an exact Linear Project ID has been observed and bound.

A missing or ambiguous Linear Project produces no channel/Canvas/List/bookmark create action. This prevents creating a Slack Workroom whose project identity has not been stabilized.

### 4.2 Review candidates

A workstream found in `review_candidates` emits:

```text
portfolio_workstream_requires_review
```

and **zero** Workroom create/update actions.

### 4.3 Excluded workstreams

A workstream found in `excluded_projects` emits:

```text
portfolio_workstream_ineligible
```

and zero channel/Canvas/List/bookmark create/update actions.

If an exact already-bound Workroom exists for that excluded workstream, the planner may emit only:

```text
would_archive_after_acceptance
```

as a review candidate. It may not archive, reactivate, rename or otherwise mutate the Workroom by itself.

### 4.4 Missing/ambiguous portfolio identity

`portfolio_workstream_missing` or `portfolio_workstream_ambiguous` produces zero Workroom actions.

### 4.5 Missing target URLs

An action requiring a URL, such as a Linear or Control Room bookmark, is omitted when its exact safe URL is unavailable. The row receives the appropriate refusal/degradation code, for example:

```text
control_room_resource_missing
```

Never emit an action with `url = null`, an empty string, an unreviewed scheme or a guessed destination.

---

## 5. Channel rename is explicit

When an exact managed Workroom marker binds an existing immutable Slack channel ID but the observed channel name differs from the reviewed desired slug, the planner emits:

```text
would_rename_channel
```

It must not disguise a name change as:

```text
would_update_managed_purpose
```

Managed-purpose drift and channel-name drift are separate actions and separate optimistic-concurrency observations.

The immutable channel ID remains the binding evidence. A manual rename never creates another Workroom or changes canonical project identity.

---

## 6. Manual remote change belongs to the actuator wave

WR-P0 is a pure snapshot compiler. It can report observed drift, malformed managed blocks, duplicate markers and snapshot inconsistencies.

The exact race condition:

```text
remote state changed after snapshot but before mutation
```

cannot be proven by the pure planner alone. `manual_remote_change` / `REMOTE_CHANGED` is therefore reserved for WR-A0/WR-C0 actuator optimistic re-read behavior.

WR-P0 must not pretend it observed a between-read-and-write race when it performed no write and no second remote read.

---

## 7. Deterministic action ordering

Add `would_rename_channel` to the closed action vocabulary and deterministic precedence list.

The action order must preserve dependency clarity, conceptually:

```text
would_create_channel
would_rename_channel
would_update_managed_purpose
would_create_home_canvas
would_update_managed_canvas_block
would_create_project_radar
would_update_managed_radar_rows
would_add_linear_bookmark
would_add_control_room_bookmark
would_archive_after_acceptance
noop
```

An implementation may use another fixed order only if it is explicitly tested and byte-deterministic.

---

## 8. Required discriminating tests

WR-P0 must include RED-first tests proving:

```text
shadow row can be planning-eligible but never apply-eligible
canary/active rollout is required before apply eligibility
review candidate emits zero create/update actions
parked/done/killed row emits zero create/update actions
missing Linear Project emits zero unbound Workroom actions
exact excluded bound Workroom may emit archive candidate only
channel name drift emits would_rename_channel
managed purpose drift remains a separate action
missing Control Room URL emits no null bookmark action
manual_remote_change is absent from pure WR-P0 semantics
eligible, apply-eligible and shadow summary counts are distinct
```

---

## 9. No other change

All other Workroom architecture, owner boundaries, Initiative-session exclusivity, Agent OS portfolio-plan input, Sol Project Steward model, operator isolation, Slack principal split, Canvas/List/workflow law, one-carrier/effect-unknown behavior, security boundaries, rollout stages, failure matrix and acceptance canaries remain unchanged.

This amendment does not make WR-P0 protected, a Slack actuator available, a Workroom apply safe, or any live channel/Canvas/List/Linear mutation authorized.