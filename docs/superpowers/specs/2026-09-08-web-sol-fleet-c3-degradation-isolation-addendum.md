---
schema: mastermind.web_sol_fleet_c3_degradation_isolation_addendum.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_pr: 546
parent_head: ea67e6cebebd105e905b0074a7afb27e960584c6
protected_source_at_repair: 686af274d8ae1558f3f3ae35e0b3aae68be80a01
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
capability_state: SPEC_ONLY
production_effect: NONE
---

# Web-Sol Fleet Census C3 — degradation-isolation addendum

**Date:** 2026-09-08  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `CHAIRMAN_APPROVED_DIRECTION / SELF_REVIEW_REPAIR / SPEC_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This addendum has narrow precedence over the parent C3 design, implementation plan, and Steward S1 compatibility addendum only for C3 failure placement and the required compatibility matrix below. Every other C3 architecture, bound, identity, deadline, payload, privacy, Today, remote-X1, installation, and production-proof law remains unchanged.

## 1. Defect being closed

Protected Steward S1's `ControlRoomStewardReadPort` consumes selected fields from `mastermind.chairman_control_room.v1` and ignores an additive legal `web_sol_fleet` value. It also deliberately treats **any** non-empty canonical top-level `degraded` list as `STEWARD_DEGRADED`.

The prior C3 records required byte-identical Steward outputs for one legal non-empty C3 projection and required malformed C3 to become `web_sol_fleet=null` plus fixed global degradation. They did not explicitly distinguish all ordinary C3 operational states from internal C3 contract failure.

Without that distinction, an implementation could append `web_sol_fleet: unavailable` whenever an adapter is unavailable, the fleet deadline is reached, a fifth adapter is omitted, bindings are absent, or profile inventory is partial. That would make a non-authoritative browser-observation condition change all six protected organizational read results even though C3 is not a source for those facts.

That coupling is rejected.

## 2. Two failure classes

### 2.1 Legal C3 operational state — C3-local only

Every successfully validated `mastermind.web_sol_fleet_projection.v1` document is ordinary canonical data, regardless of whether its coverage is:

```text
COMPLETE_IN_SCOPE
PARTIAL
UNAVAILABLE
EMPTY_IN_SCOPE
```

Its closed `reason_codes` and profile `reason_code` fields are the sole C3 operational explanation channel. These include ordinary conditions such as:

```text
BINDINGS_UNAVAILABLE
BINDINGS_INVALID
ADAPTER_LIMIT
FLEET_DEADLINE
PROFILE_UNAVAILABLE
PROFILE_PARTIAL
```

and the already-frozen profile-level C2/client outcomes.

A legal C3 document must **not** append any C3-specific item to the canonical top-level `degraded` list. In particular, partial or unavailable browser census is not evidence that Agent OS, Executive OS, attention, responsibility, runtime, binding navigation, or Steward grounding is degraded.

The existing Control Room's unrelated pre-existing degradation entries remain unchanged and retain their existing meaning.

### 2.2 C3 contract/integrity failure — global degradation allowed

Only failure to construct or validate the C3 contract itself may use the parent design's fixed global boundary:

```text
web_sol_fleet = null
web_sol_fleet: unavailable
```

or, for invalid caller-provided pure compositor input:

```text
web_sol_fleet = null
web_sol_fleet: invalid
```

This class is limited to conditions such as:

- malformed or oversized pure projection output;
- impossible closed-contract relationships;
- unexpected gather/projection exception after fixed error mapping is exhausted;
- invalid or regressing time samples that prevent a truthful C3 document;
- missing optional local C3 implementation in a release that claims to ship the local capability.

This is a code/contract integrity failure, not an adapter/profile condition. The fixed global degradation may consequently make protected Steward report `STEWARD_DEGRADED`; that is the existing canonical safety response to a malformed whole Control Room generation. No C3 identifier, reason code, count, profile fact, exception, path, operation key, or raw value may enter Steward output.

The separately extracted remote X1 release still omits C3 and does not claim the local capability. Its intentional C3 absence is not a local C3 contract failure and does not add a remote degradation entry.

## 3. Required Steward non-interference matrix

The C3 implementation worker must build one otherwise byte-identical valid Control Room generation for each case below and invoke all six real protected `ControlRoomStewardReadPort` methods with the same arguments and clock:

1. no `web_sol_fleet` value at the optional pure-compositor input boundary;
2. legal `COMPLETE_IN_SCOPE` C3;
3. legal `PARTIAL` C3 caused by `PROFILE_UNAVAILABLE`;
4. legal `PARTIAL` C3 caused by `FLEET_DEADLINE`;
5. legal `PARTIAL` C3 caused by `ADAPTER_LIMIT`;
6. legal `PARTIAL` C3 caused by `PROFILE_PARTIAL`;
7. legal `UNAVAILABLE / BINDINGS_UNAVAILABLE` C3;
8. legal `UNAVAILABLE / BINDINGS_INVALID` C3;
9. legal `UNAVAILABLE` C3 with expected profiles but no collected profile;
10. legal `EMPTY_IN_SCOPE` C3.

For cases 1–10:

- all six canonical public outputs must be byte-identical;
- the canonical top-level `degraded` list must be byte-identical;
- no C3 identifier, count, cue, reason, model field, or profile/session value may enter Steward grounding, structured MCP output, or the Steward UI resource;
- Today/DF1 inputs and outputs must remain byte-identical where the C3 implementation test surface can exercise them without widening source ownership.

The matrix must use real legal C3 documents produced by the pure C3 owner, not hand-written dictionaries that bypass its validator.

## 4. Required contract-failure matrix

Separately prove through the real canonical compositor:

1. malformed C3 pure input -> `web_sol_fleet=null` plus exactly one fixed `web_sol_fleet: invalid` degradation;
2. unexpected local C3 gather/projection failure -> `web_sol_fleet=null` plus exactly one fixed `web_sol_fleet: unavailable` degradation;
3. raw rejected values and exceptions are absent from the canonical document, Steward output, MCP output, and UI;
4. protected Steward then follows its existing global-degradation law rather than learning a C3-specific exception;
5. correction with a later legal C3 input removes only the fixed C3 degradation on the next ordinary whole composition and restores the baseline Steward bytes; no sticky C3 or Steward state exists.

Do not modify `integrations/mastermind_steward_app/**` or its tests to special-case C3. The compatibility proof belongs in existing C3-owned test paths.

## 5. Required mutation discrimination

Kill at least these mutants:

- append global degradation whenever C3 `coverage != COMPLETE_IN_SCOPE`;
- append global degradation whenever any profile `state != COLLECTED`;
- append global degradation for `BINDINGS_UNAVAILABLE` or `BINDINGS_INVALID` legal documents;
- suppress the fixed global degradation for malformed C3 contract input;
- copy a C3 reason code or identifier into a global degradation string;
- teach Steward to ignore all global degradation merely to make the compatibility test pass;
- retain a fixed C3 degradation after the next legal whole composition.

The first three mutants must fail because legal operational states changed Steward or the global degradation bytes. The fourth and fifth must fail the contract-failure boundary. The sixth is forbidden path widening. The seventh must fail correction/replacement proof.

## 6. Product consequence

Advanced → Web Sessions can show a partial or unavailable browser census while the protected organizational read surface remains healthy:

```text
Web Sessions: unavailable — bindings unavailable
Steward responsibilities: unchanged
```

This does not call the company healthy; it preserves source relevance. A browser census cannot degrade unrelated truth merely because it is incomplete, and a genuine malformed canonical generation cannot be hidden merely because C3 is optional.

No new source reader, degradation registry, cache, status authority, exception taxonomy, endpoint, Steward rule, Today dependency, or remote projection is introduced.

## 7. Effect and continuation boundary

This records-only correction changes no implementation source, browser, profile, native host, socket, binding, Runtime, provider, Control Room service, cache, route, installation, deployment, or production state.

PR #546 remains Draft/Hold. Independent review must consume this addendum with the four existing C3 records. C3 implementation remains `PRE_START / DEPENDENCY_HELD` until every frozen source, ownership, review, installation, and production-proof gate is separately satisfied.