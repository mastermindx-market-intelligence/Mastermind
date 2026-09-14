---
schema: mastermind.web_sol_fleet_c3_steward_s1_compatibility.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_pr: 546
parent_spec_blob: 6a4186045327d4216eae91705b2fc0939d9dd22a
parent_plan_blob: 6d217a2380ed781ea171182bc54e1c199a51f7ff
protected_source_at_amendment: 686af274d8ae1558f3f3ae35e0b3aae68be80a01
protected_tree_at_amendment: 4791f226e3b2f9988201d2d3c9569e06477ef2f9
protected_movement_pr: 463
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
capability_state: SPEC_ONLY
production_effect: NONE
---

# Web-Sol Fleet C3 — protected Steward S1 compatibility addendum

**Date:** 2026-09-08  
**Status:** `CURRENT-SOURCE-COMPATIBILITY / RECORDS_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This addendum has narrow precedence over the parent C3 design and implementation plan only for the protected-source movement and downstream-consumer proof described below. It does not change the Chairman-approved product direction, the four-adapter/sequential/40-second acquisition law, the C3 wire contract, the implementation branch, or any production effect.

## 1. Protected movement

After the repaired C3 records head `160e13f9df4a33794eca7588725dca017caf77c9` was published, protected `master` advanced from:

```text
e18cab4f3ca41725fdb517623543fa4fb1aba467
```

to:

```text
686af274d8ae1558f3f3ae35e0b3aae68be80a01
```

through merged PR #463, tree `4791f226e3b2f9988201d2d3c9569e06477ef2f9`.

The fourteen protected paths are disjoint from the three C3 records and from the parent plan’s expected C3 implementation paths. The protected Skillpack remains byte-compatible at schema `mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`.

PR #463 adds the protected, source-only Mastermind Steward S1 app. Its `ControlRoomStewardReadPort` consumes `mastermind.chairman_control_room.v1` and projects six bounded read tools. It validates the Control Room schema and the source fields it consumes, but it does not require an exact top-level key set. Therefore adding the local-only `web_sol_fleet` key to the canonical Control Room is compatible with the current implementation in principle.

That observed permissiveness is not sufficient release proof. C3 changes the canonical document’s closed top-level shape, so Steward S1 is now an explicit downstream compatibility consumer.

## 2. Amendment to the C3 implementation proof

The C3 implementation worker must add a discriminating compatibility test in an already-owned C3 test path—prefer `tests/test_chairman_control_room.py` or `tests/test_web_sol_fleet_projection.py`. Do **not** edit `integrations/mastermind_steward_app/**` or its existing tests merely to make C3 appear compatible.

The test must:

1. build one valid canonical Control Room document without C3 and one otherwise byte-equivalent document carrying a legal non-empty `web_sol_fleet` projection;
2. pass each document through the real protected `ControlRoomStewardReadPort`;
3. invoke all six public read methods with the same arguments;
4. prove canonical public outputs are byte-identical with and without C3;
5. prove adapter IDs, conversation fingerprints, binding IDs, profile/session counts, generation cues, C3 reason codes, and model fields never enter Steward grounding, structured MCP output, or the Steward UI resource;
6. prove malformed C3 cannot reach Steward through the real canonical compositor—the compositor must first reduce it to `web_sol_fleet=null` plus fixed C3 degradation;
7. preserve the Steward app’s exact schema generation, six-tool surface, auth boundary, grouped-v2 wire, 64-fact cap, and zero-write authority.

Required existing regression commands now include:

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_mastermind_steward_app_projection.py \
  tests/test_mastermind_steward_app_server.py \
  tests/test_mastermind_steward_app_static_fences.py
```

Add those suites to the C3 focused verification and whole-release evidence. A passing historical #463 campaign is not a C3 compatibility receipt.

## 3. Path and failure boundary

No additional production path is added to the C3 implementation ceiling by this amendment.

If the real compatibility test fails, the C3 worker must return:

```text
PATH_WIDENING_REQUIRED / PROTECTED_STEWARD_CONSUMER_CONFLICT
```

with the exact failing input/output and no source edit outside the existing C3 ceiling. Sol must then decide whether the C3 top-level extension should be redesigned or whether a separately reviewed Steward compatibility change is justified. The worker may not:

- weaken the Steward schema or auth checks;
- teach Steward to expose C3 browser/profile facts;
- add a second Control Room projection;
- silently filter data in the HTTP/server layer;
- modify the protected Steward UI or six-tool contract;
- widen remote X1;
- call the failure a test-only issue without proving it.

## 4. Review and release consequence

Because this addendum changes the candidate-owned records set and proof closure, any review of `160e13f...` is superseded. Independent review must bind the new immutable C3 records head and all three record blobs.

The semantic architecture remains the same, but current integration proof must bind that new head to protected `686af274...` or a later compatible protected base through a generated merge ref or equivalent immutable integration candidate.

Capability remains:

```text
C3 architecture: SPEC_ONLY / CHAIRMAN_APPROVED
C3 implementation: PRE_START / DEPENDENCY_HELD
Steward S1 source: BUILT_NOT_PROVEN / PROTECTED / PRODUCTION_INERT
C3-to-Steward compatibility: SPECIFIED / NOT YET IMPLEMENTED OR PROVEN
production effect: NONE
```
