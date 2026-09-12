---
schema: mastermind.web_sol_fleet_c3_navigation_capability_addendum.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_pr: 546
parent_head: 9b3e1a21bf4c2d6274f83fc401f93c892eafdcdf
protected_source_at_repair: 686af274d8ae1558f3f3ae35e0b3aae68be80a01
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
capability_state: SPEC_ONLY
production_effect: NONE
---

# Web-Sol Fleet Census C3 — navigation-capability correction

**Date:** 2026-09-08  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `CHAIRMAN_APPROVED_DIRECTION / CURRENT-SOURCE-CORRECTION / SPEC_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This addendum has narrow precedence over the parent C3 design and implementation plan wherever they require an active **Open** control or exact binding navigation in C3. It also closes opaque adapter-label ambiguity. Every other C3 architecture, count, coverage, deadline, privacy, payload, Today, remote-X1, Steward, installation, and production-proof law remains unchanged.

## 1. Current protected source falsifies active C3 navigation

Protected `master` at `686af274d8ae1558f3f3ae35e0b3aae68be80a01` establishes all of the following:

1. `app/static/chairman_control/control_room.js::bindingConfidence()` returns `UNSUPPORTED`, `openable=false` for every `chatgpt` binding.
2. `integrations/chairman_surfaces/chatgpt.py::open_surface()` refuses closed on every managed-browser path. The module documents that neither supported managed-browser vendor provides an official surface to open a URL in, focus, or attach to an already-running GUI profile, and it forbids unofficial fallback.
3. The local Control Room's existing `/api/open` route uses that current surface adapter path. Passing a ChatGPT binding to `openBinding()` therefore cannot produce supported navigation.
4. Protected Web-Sol separately has exact `FOREGROUND` semantics, but that is an effect-bearing native action with its own request/receipt/effect-uncertainty law. It is not the existing Control Room `/api/open` path and is not granted to C3 by census read authority.
5. The frozen C3 path ceiling excludes `scripts/chairman_control_room.py`, Web-Sol action source, managed-browser adapters, and a new route. C3 also prohibits a new endpoint and browser actuation.

Therefore the earlier requirement that C3 reuse `openBinding()` and prove exact binding navigation is not implementable from current source without either a permanently refused control or an unauthorized action-path expansion.

A disabled button that always refuses is not an independently useful capability. Bypassing `bindingConfidence()` to call `openBinding()` directly would also violate current source law.

## 2. Corrected C3 first vertical

C3 v1 provides **exact binding correlation**, not navigation actuation.

For each observed session it may show:

```text
exact navigation match count
bounded omitted-match count
binding correlation state
```

Closed presentation states:

```text
UNBOUND
BOUND_EXACT
BOUND_AMBIGUOUS
NAVIGATION_UNSUPPORTED
```

These are UI-derived presentation labels, not new canonical output fields unless the implementation reviewer proves a closed pure field is required within the existing payload ceiling. The canonical C3 document continues to carry only the already-frozen exact binding IDs/counts and never carries a URL, locator, profile ID, vendor coordinate, or action token.

Current-source behavior for exactly one matched ChatGPT binding is:

```text
binding correlation: BOUND_EXACT
navigation: NAVIGATION_UNSUPPORTED
active Open control: ABSENT
```

Zero matches is `UNBOUND`. Multiple canonical binding-object matches is `BOUND_AMBIGUOUS`. Neither case presents an active control.

C3 must never:

- call `openBinding()` directly for a ChatGPT census row;
- bypass or locally reimplement `bindingConfidence()`;
- invoke Web-Sol `FOREGROUND` or any modifying native action;
- add a server endpoint, POST family, action receipt, effect state, retry, or target selector;
- build or expose a URL from C3 or binding data;
- use `window.open`, generic anchors, Chrome tab focus, managed-vendor commands, UI automation, or unofficial attachment;
- modify `chatgpt.py`, surface runner, server route code, Web-Sol action code, or deployment source to make C3 appear navigable.

The current C3 implementation path ceiling remains unchanged.

## 3. Full vision preserved through the correct owner

The end-state still includes exact navigation from an observed fleet row. It belongs to a later separately admitted vertical that composes:

```text
protected installed Web-Sol action generation
+ exact current binding and adapter generation
+ current Control Room action admission
+ supported semantic FOREGROUND request
+ effect-uncertainty reconciliation
-> active exact navigation control
```

That vertical must remain with the existing Web-Sol action/Control Room navigation/RuntimeBinding owners and must decide its own route, permission, effect, installed-generation, rollback, and production-proof gates. It may not be hidden inside C3 or inferred from issue #340 installation proof alone.

Issue #340 proves installed S0/S1/C2 behavior on disposable profiles; it does not by itself wire `FOREGROUND` into the Control Room or supersede `chatgpt.open_surface()`.

C3 can later consume a supported existing navigation capability without changing its observation schema. Until then, the UI is honest and non-actionable.

## 4. Corrected UI and browser-proof requirements

Task 8 is amended as follows.

Required browser cases:

1. one exact ChatGPT binding match -> exact match count visible, fixed `Navigation unavailable` explanation, no enabled Open control;
2. zero canonical matches -> unbound text, no control;
3. duplicate/multiple canonical matches -> ambiguous text, no control;
4. more than six exact matches -> six bounded references or summaries at most, exact total/omitted counts, no control;
5. a malicious direct fixture that marks a ChatGPT row openable cannot create a control;
6. calling or monkeypatching `openBinding()` must not be part of C3 rendering;
7. a source mutation that bypasses `bindingConfidence`, adds an anchor/URL, or invokes `/api/open` from a C3 row must make the tests fail;
8. existing non-C3 surface controls remain unchanged;
9. remote X1 still contains no C3 row or control.

The implementation uses existing binding objects only to establish exact local correlation and existing confidence text. It does not pass them to an action function.

Task 11's installed journey replaces:

```text
exact binding navigation
```

with:

```text
exact binding correlation
+ explicit current navigation-unavailable state
+ proof that no navigation/action request occurred
```

A C3 production PASS proves useful fleet observation and correlation only. It must not claim active row navigation.

## 5. Collision-safe opaque adapter labels

The earlier phrase “display only a short opaque adapter prefix” is insufficient when two distinct adapter digests share that prefix.

C3 must derive labels from full validated adapter IDs with this deterministic presentation-only algorithm:

1. start at eight lowercase hexadecimal characters;
2. increase one character at a time until every visible profile prefix is unique;
3. use the full 64-character digest only when required for uniqueness;
4. append an ellipsis only when fewer than 64 characters are shown;
5. compute labels after canonical adapter-ID sorting so input order cannot affect them.

The label is not persisted, returned to the server, or used for identity, grouping, navigation, ownership, sorting, or correction. Full adapter identity remains the canonical key.

Required tests:

- ordinary distinct eight-character prefixes;
- two adapters sharing 8, 32, and 63 characters;
- order permutations produce the same labels;
- adding/removing a different profile cannot merge two existing identities;
- duplicate full adapter IDs remain a contract error, not a label suffix election;
- long labels wrap without colliding with counts or controls at all required widths;
- no seat, title, provider account, profile name, binding order, array index, or recency enters the label.

Do not use `Profile A/B`, newest-profile order, or seat labels as a substitute; those labels can move across corrections and would create false continuity.

## 6. Required mutation discrimination

Kill at least these mutants:

- create an active Open button for one exact ChatGPT binding;
- call `/api/open` or `openBinding()` from the C3 renderer;
- treat issue #340 installation as proof that current Control Room navigation is supported;
- expose the stored conversation URL or managed-profile locator;
- invoke Web-Sol `FOREGROUND` from C3;
- mark exact correlation as active navigation;
- use a fixed eight-character prefix without collision handling;
- use profile array index or seat label to disambiguate adapters.

Restore each mutation and rerun the full C3 and existing surface-navigation suites.

## 7. Effect and continuation boundary

This records-only correction narrows an impossible action claim; it does not reduce the full product vision. It changes no implementation source, browser, profile, native host, socket, binding, Runtime, provider, Control Room service, route, action, installation, deployment, or production state.

PR #546 remains Draft/Hold. Independent review must consume this addendum with the five prior C3 records. C3 implementation remains `PRE_START / DEPENDENCY_HELD` until every frozen source, ownership, review, installation, and production-proof gate is separately satisfied.