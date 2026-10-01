---
schema: mastermind.web_sol_fleet_c3_probe_coverage_addendum.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_pr: 546
parent_head: c15b690c9f6930328514c1e9c040bbd478bebbfb
protected_source_at_repair: 686af274d8ae1558f3f3ae35e0b3aae68be80a01
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
capability_state: SPEC_ONLY
production_effect: NONE
---

# Web-Sol Fleet Census C3 — probe-coverage totality addendum

**Date:** 2026-09-08  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `CHAIRMAN_APPROVED_DIRECTION / SELF_REVIEW_REPAIR / SPEC_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This addendum has narrow precedence over only:

- section **8.3 Probe coverage** of `2026-09-08-web-sol-fleet-c3-control-room-design.md`;
- Task 2 probe-coverage cases and Task 9 probe mutations in `2026-09-08-web-sol-fleet-c3-control-room.md`.

Every other C3 architecture, ownership, bound, identity, null, deadline, privacy, payload, Today, remote-X1, Steward, installation, and production-proof law remains unchanged.

## 1. Defect being closed

The prior rule covered:

- all retained rows observed **when the fleet itself is complete**;
- some but not all retained rows observed;
- no retained rows observed.

It did not assign a value for a legal fleet that is `PARTIAL`, has at least one retained session, and has `status=OBSERVED` on every retained session. Examples include:

- one collected profile plus one unavailable profile;
- four collected profiles plus an omitted fifth profile;
- one collected profile whose inventory is partial but whose retained rows were all probed successfully;
- one timely collected profile plus a selected profile not attempted before the fleet deadline.

A required closed output cannot leave that state to implementation choice. In particular, the known subset being fully probed must not become `COMPLETE_IN_SCOPE` when expected-profile or profile-inventory coverage is incomplete.

## 2. Corrected meaning

Fleet `probe_coverage` is a separate dimension from inventory coverage, but its **complete** value is still scoped to the expected fleet. It answers whether every retained session in a completely covered fleet has an accepted `OBSERVED` row. It never attests provider computation, worker execution, capacity, model routing, or all account history.

Define:

```text
known = known_session_count
observed = count(session.status == OBSERVED across collected profile rows)
```

Both values are derived from retained validated rows. Neither is caller-authored.

## 3. Total ordered derivation

Evaluate these rules in order:

1. Fleet `coverage == EMPTY_IN_SCOPE` -> `probe_coverage = NONE`.
2. `collected_profile_count == 0` -> `probe_coverage = UNAVAILABLE`.
3. `known == 0` -> `probe_coverage = NONE`.
4. Fleet `coverage == COMPLETE_IN_SCOPE` **and** `observed == known` -> `probe_coverage = COMPLETE_IN_SCOPE`.
5. `observed > 0` -> `probe_coverage = PARTIAL`.
6. Otherwise -> `probe_coverage = NONE`.

Consequences:

- A partial fleet whose entire retained known subset is observed is `PARTIAL`, never `COMPLETE_IN_SCOPE`.
- A complete fleet with any unobserved retained row is `PARTIAL` when at least one row is observed, otherwise `NONE`.
- A complete or partial fleet with zero known rows is `NONE`, not complete.
- A fleet with expected profiles but no collected profile is `UNAVAILABLE`, not `NONE` or complete.
- `EMPTY_IN_SCOPE` remains the only no-profile state that yields `NONE` rather than `UNAVAILABLE`.

Validation must reject any document with `probe_coverage=COMPLETE_IN_SCOPE` unless all of the following hold:

```text
coverage == COMPLETE_IN_SCOPE
known_session_count > 0
observed_session_count == known_session_count
```

The validation rule is derived from visible retained session rows; no additional output field is added.

## 4. Required RED-to-GREEN matrix

Task 2 must add explicit failing tests before implementation for:

1. complete fleet + every known row observed -> `COMPLETE_IN_SCOPE`;
2. partial fleet caused by one unavailable profile + every retained row observed -> `PARTIAL`;
3. partial fleet caused by adapter omission + every retained row observed -> `PARTIAL`;
4. partial fleet caused by profile inventory partial + every retained row observed -> `PARTIAL`;
5. complete fleet + some but not all known rows observed -> `PARTIAL`;
6. partial fleet + some but not all known rows observed -> `PARTIAL`;
7. complete or partial fleet + known rows but zero observed -> `NONE`;
8. complete or partial fleet + zero known rows -> `NONE`;
9. expected profiles + zero collected profiles -> `UNAVAILABLE`;
10. valid empty-in-scope fleet -> `NONE`.

Add one small exhaustive table test over legal combinations of:

```text
fleet coverage
collected profile count
known session count
observed session count
```

The table must prove exactly one of the six ordered rules applies to every legal combination. Illegal combinations remain validator failures; the implementation must not silently coerce them.

## 5. Required mutation discrimination

Task 9 must include a mutant that removes the fleet-completeness precondition and promotes any `observed == known > 0` subset to `COMPLETE_IN_SCOPE`. The partial-fleet/all-retained-observed tests must fail under that mutant.

Also kill mutants that:

- return `UNAVAILABLE` for a valid empty fleet;
- return `NONE` when expected profiles exist but none was collected;
- call a zero-row complete fleet probe-complete;
- use profile-reported probe coverage alone instead of retained session statuses;
- count non-`OBSERVED` states as observed.

Restore each mutation and re-run the full projection suite.

## 6. UI and reason-code consequence

No new reason code or UI section is introduced.

The Advanced Web Sessions UI renders the corrected top-level `probe_coverage` verbatim through the existing safe closed renderer. A partial fleet may therefore display:

```text
Inventory: partial
Probe coverage: partial
```

even when every currently visible row was observed, because additional expected profile or inventory rows may exist. The supporting existing fleet reason—such as `PROFILE_UNAVAILABLE`, `ADAPTER_LIMIT`, `FLEET_DEADLINE`, or `PROFILE_PARTIAL`—explains why complete probe scope cannot be established.

The UI must not rewrite that state as “all visible sessions probed” without also displaying the incomplete fleet boundary, and must never shorten it to “complete.”

## 7. Effect and continuation boundary

This is a records-only correction. It changes no implementation source, branch outside PR #546, browser, profile, native host, socket, binding, Runtime, provider, Control Room service, cache, route, installation, deployment, or production state.

PR #546 remains Draft/Hold. Independent review must consume this addendum with the original design, implementation plan, and Steward S1 compatibility addendum. C3 implementation remains `PRE_START / DEPENDENCY_HELD` until every frozen source gate is separately satisfied.