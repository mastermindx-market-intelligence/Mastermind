---
schema: mastermind.web_sol_fleet_c3_contract_convergence_addendum.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_pr: 546
parent_head: fac757e8df58cdbcb7a86c8ac0deca474e63fe35
protected_source_at_repair: 686af274d8ae1558f3f3ae35e0b3aae68be80a01
protected_tree_at_repair: 4791f226e3b2f9988201d2d3c9569e06477ef2f9
review_operation: web-sol-fleet-c3-records-independent-review-20260908-sol-001
review_carrier: C0BSBM78V1N/1788911403.030389
review_result: 1788918322.611869
sol_ruling: 1788951303.942859
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
capability_state: SPEC_ONLY
implementation_state: PRE_START
production_effect: NONE
---

# Web-Sol Fleet Census C3 — contract convergence and staged-admission addendum

**Date:** 2026-09-09  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `CHAIRMAN_APPROVED_DIRECTION / REVIEW_REPAIR / FINAL_CONVERGENCE / SPEC_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This record closes the two exact equation blockers returned by the current non-author reviewer and the two connected Program-CEO architecture defects found during the same current-source review. It is intended to be the final records amendment before independent rereview.

It has narrow precedence over:

- sections **4.2–4.3, 5, 8.1–8.3, 12, 14–16** of `2026-09-08-web-sol-fleet-c3-control-room-design.md`;
- plan section **0**, Tasks **2, 5–6, 8–11**, the expected implementation path list, and the stop handoff in `2026-09-08-web-sol-fleet-c3-control-room.md`;
- the probe-coverage addendum where it retains the ambiguous `PROFILE_PARTIAL` reason or leaves inventory totals coupled to probe state;
- the Steward compatibility addendum where it requires output equality but does not prohibit unnecessary C2 acquisition by Steward callers;
- the degradation-isolation addendum only for the renamed inventory/probe reason families;
- any prior records statement that makes #499, #501 proof maintenance, #359, #338, or #340 a prerequisite for starting the deterministic C3 source wave.

The navigation-capability addendum remains fully controlling: C3 v1 provides exact binding correlation and honest `NAVIGATION_UNSUPPORTED`, never an active Open/FOREGROUND path. All still-valid C2 identity, privacy, payload, deadline, no-retry, Today isolation, remote-X1 omission, Steward no-leak, and no-duplicate-system laws remain unchanged.

No implementation source, browser, profile, account, native host, socket, Runtime, provider, installation, deployment, navigation action, or production state changes through this records repair.

## 1. Closed fleet inventory and probe dimensions

C3 exposes two independent coverage dimensions.

```text
coverage
  = whether the exact browser-row inventory is known across the expected
    enrolled profile-adapter scope in this fleet generation

probe_coverage
  = whether retained inventory rows have accepted current page observations
```

Probe uncertainty never erases an exact inventory count. Inventory uncertainty never becomes complete because every retained known row happened to be probed.

### 1.1 Closed top-level reason codes

The exact reason-code set becomes:

```text
BINDINGS_UNAVAILABLE
BINDINGS_INVALID
ADAPTER_LIMIT
FLEET_DEADLINE
PROFILE_UNAVAILABLE
PROFILE_INVENTORY_PARTIAL
PROFILE_PROBE_PARTIAL
```

`PROFILE_PARTIAL` is removed from the C3 top-level contract. It may not be accepted as a compatibility alias.

Inventory-affecting reasons are:

```text
BINDINGS_UNAVAILABLE
BINDINGS_INVALID
ADAPTER_LIMIT
FLEET_DEADLINE
PROFILE_UNAVAILABLE
PROFILE_INVENTORY_PARTIAL
```

`PROFILE_PROBE_PARTIAL` is probe-only and may coexist with `coverage=COMPLETE_IN_SCOPE`.

Derivation:

- `PROFILE_INVENTORY_PARTIAL` exists iff at least one collected profile has C2 `inventory_coverage != COMPLETE_IN_SCOPE`.
- `PROFILE_PROBE_PARTIAL` exists iff at least one known retained session is not `OBSERVED`.
- A zero-row complete inventory has no `PROFILE_PROBE_PARTIAL`; there was no retained row to probe.
- A partial fleet whose every retained known row is observed has no `PROFILE_PROBE_PARTIAL`; its top-level `probe_coverage=PARTIAL` still reflects incomplete expected scope under the existing ordered probe law.
- Reasons remain exact, sorted, deduplicated, and source-text-free.

Profile-level C2/client receipt statuses and profile `reason_code` values remain unchanged. This split changes only the fleet reason vocabulary and fleet inventory/probe equations.

### 1.2 Exact `total_session_count` law

```text
binding_state MISSING or INVALID
  expected_profile_count = null
  total_session_count = null

coverage EMPTY_IN_SCOPE
  expected_profile_count = 0
  known_session_count = 0
  total_session_count = 0

coverage COMPLETE_IN_SCOPE
  total_session_count = known_session_count
  total_session_count is an exact non-negative integer, including zero

coverage PARTIAL or UNAVAILABLE
  total_session_count = null
```

A validator must reject:

- `EMPTY_IN_SCOPE` with `total_session_count=null`;
- `EMPTY_IN_SCOPE` with a nonzero total;
- `COMPLETE_IN_SCOPE` with a null or non-exact total;
- `PARTIAL` or `UNAVAILABLE` with any integer total;
- a total that differs from the exact sum of complete collected profile inventories.

### 1.3 Exact fleet inventory coverage

For `AVAILABLE` bindings with zero expected adapters:

```text
coverage = EMPTY_IN_SCOPE
profiles = []
all profile counters = 0
known_session_count = 0
total_session_count = 0
probe_coverage = NONE
reason_codes = []
```

For `AVAILABLE` bindings with one or more expected adapters, `COMPLETE_IN_SCOPE` requires only inventory-completeness predicates:

- no omitted adapter;
- no selected adapter left not attempted;
- every expected adapter attempted exactly once;
- every attempt returned `state=COLLECTED`;
- every attempt completed strictly inside the fleet admission deadline;
- every accepted C2 snapshot has `inventory_coverage=COMPLETE_IN_SCOPE`;
- none of the six inventory-affecting reasons is present.

`PROFILE_PROBE_PARTIAL` does not block inventory `COMPLETE_IN_SCOPE`.

`PARTIAL` requires at least one collected profile and at least one inventory-incomplete predicate, including adapter omission, selected-not-attempted, unavailable profile, late result, or partial profile inventory.

`UNAVAILABLE` applies when expected inventory scope is unknown or when expected adapters exist but no profile produced a collected C2 snapshot. It never means exact zero.

### 1.4 Probe coverage retains its ordered total law

The probe addendum's ordered derivation remains:

1. fleet `EMPTY_IN_SCOPE` -> `NONE`;
2. zero collected profiles -> `UNAVAILABLE`;
3. zero known sessions -> `NONE`;
4. fleet inventory `COMPLETE_IN_SCOPE` and every known row `OBSERVED` -> `COMPLETE_IN_SCOPE`;
5. at least one observed row -> `PARTIAL`;
6. otherwise -> `NONE`.

Examples:

```text
complete inventory, 3 rows, 1 observed
  coverage = COMPLETE_IN_SCOPE
  total_session_count = 3
  probe_coverage = PARTIAL
  reason_codes = [PROFILE_PROBE_PARTIAL]

complete inventory, 3 rows, 0 observed
  coverage = COMPLETE_IN_SCOPE
  total_session_count = 3
  probe_coverage = NONE
  reason_codes = [PROFILE_PROBE_PARTIAL]

complete inventory, 0 rows
  coverage = COMPLETE_IN_SCOPE
  total_session_count = 0
  probe_coverage = NONE
  reason_codes = []

partial inventory, all retained rows observed
  coverage = PARTIAL
  total_session_count = null
  probe_coverage = PARTIAL
  reason_codes includes PROFILE_INVENTORY_PARTIAL
  reason_codes does not include PROFILE_PROBE_PARTIAL
```

No UI or validator may collapse the two dimensions into one healthy/partial label.

## 2. Required equation RED-to-GREEN and mutation proof

Before implementing fleet aggregation, Task 2 must add failing tests for:

1. valid empty scope -> exact total `0`;
2. empty scope with null total -> validator refusal;
3. partial/unavailable with integer total -> validator refusal;
4. complete inventory with partial probes -> exact total retained;
5. complete inventory with no observed probes -> exact total retained;
6. complete zero-row profile inventory -> exact total `0`, probe `NONE`;
7. partial profile inventory with every retained row observed -> total null;
8. partial fleet plus probe-only shortfall -> both precise reason families;
9. complete inventory with probe-only shortfall -> no inventory reason;
10. input-order permutations -> byte-identical result.

Task 9 must kill and restore at least:

```text
EMPTY total becomes null
PARTIAL or UNAVAILABLE accepts integer total
PROFILE_PROBE_PARTIAL blocks inventory COMPLETE
partial profile inventory fails to add PROFILE_INVENTORY_PARTIAL
probe-only shortfall adds PROFILE_INVENTORY_PARTIAL
known rows with zero observed omit PROFILE_PROBE_PARTIAL
complete zero-row inventory adds PROFILE_PROBE_PARTIAL
old PROFILE_PARTIAL compatibility alias is accepted
```

The tests must fail for the intended equation change, not because an unrelated shape check fails.

## 3. Local acquisition is explicit; public gathering stays inert by default

The public gatherer is shared by the local P0A server, the protected Steward launcher, checks, tests, and other library callers. C3 is an Advanced local browser observation and must not make every public caller perform profile-local native reads.

The implementation changes the public signature additively:

```python
build_control_room(
    *,
    ...,
    collect_web_sol_fleet: bool = False,
) -> dict[str, Any]
```

Require `type(collect_web_sol_fleet) is bool`.

When false:

```text
target derivation calls = 0
C2 calls = 0
web_sol_fleet = null
C3-specific global degradation = none
all pre-C3 canonical sections remain byte-equivalent
```

When true, the local gather:

1. loads bindings once through the existing owner;
2. derives targets once;
3. performs the bounded sequential C2 acquisition once;
4. passes the same already-collected C3 value to the precursor and final pure compositions;
5. publishes it only through the existing whole-document cache generation.

### 3.1 Local P0A opt-in owner

Add one default-off local option in the existing local server:

```text
--enable-web-sol-fleet
```

and one exact Boolean `ServerConfig.enable_web_sol_fleet` field. `_compose_state_doc()` passes that value as `collect_web_sol_fleet`.

No other production caller opts in during the first source vertical.

Source protection leaves the flag off. The installed canary owner enables it for the exact approved generation. A null value with no C3 integrity degradation renders in Advanced as `Not sampled in this Control Room generation`, not as empty or unavailable.

The first source vertical therefore adds `scripts/chairman_control_room.py` to the implementation ceiling. It adds no endpoint, route family, component cache, timer, daemon, scheduler, poller, registry, cursor, durable state, or retry plane.

### 3.2 Protected Steward zero-acquisition proof

`scripts/mastermind_steward_app.py` continues calling `build_control_room()` without the opt-in argument.

The C3-owned compatibility test must exercise the real protected Steward snapshot-provider path and all six public `ControlRoomStewardReadPort` methods. It must prove:

```text
C2 calls across all six reads = 0
all six public results remain byte-identical
no C3 identifier/value enters grounding, MCP output, or UI
```

Output equality after unnecessary acquisition is not sufficient.

Do not edit `integrations/mastermind_steward_app/**`, `scripts/mastermind_steward_app.py`, or their tests to special-case C3. The proof belongs in the C3-owned test ceiling.

### 3.3 Existing cache and timing law

With the local flag enabled:

- one canonical cache generation performs at most one C3 gather;
- precursor and final composition reuse the same value;
- repeated warm `GET /api/state` reads perform zero C2 calls;
- one background refresh generation performs at most one C3 gather;
- a superseded generation cannot publish;
- a C3 contract failure follows the existing fixed degradation and last-good-cache behavior.

The existing `compose_timeout` retains its current meaning for the existing Agent OS subprocess; it is not relabelled as a whole-composition deadline. C3 retains its separate 40-second admission window. Do not add those values into a fabricated timeout.

Flag-off startup/background composition has zero C3 latency. Flag-on proof records the actual whole-composition elapsed time and C3 contribution. Production acceptance must disclose that result instead of claiming the Advanced sensor is cost-free.

Required mutations:

```text
public builder defaults C3 on
Steward snapshot reads C3
precursor and final compose each gather independently
warm /api/state calls C3
background generations share or leak C3 state
C3 failure bypasses the last-good cache law
```

## 4. Exact implementation path ceiling

The first C3 source vertical may touch exactly these thirteen paths:

1. create `control_plane/web_sol_fleet_projection.py`;
2. modify `control_plane/chairman_control_room.py`;
3. modify `control_plane/chairman_control_room_remote.py`;
4. modify `scripts/chairman_control_room.py`;
5. modify `app/static/chairman_control/index.html`;
6. modify `app/static/chairman_control/control_room.js`;
7. modify `app/static/chairman_control/control_room.css`;
8. create `tests/test_web_sol_fleet_projection.py`;
9. modify `tests/test_chairman_control_room.py`;
10. modify `tests/test_chairman_control_room_remote.py`;
11. modify `tests/test_chairman_control_room_ui_x1.py`;
12. modify `tests/test_chairman_control_room_server.py`;
13. modify `docs/CHAIRMAN_CONTROL_ROOM.md`.

Any fourteenth path is `PATH_WIDENING_REQUIRED` and returns to Sol before modification.

The protected Steward implementation and test paths are not in this ceiling. The current navigation/addendum prohibition also keeps `chatgpt.py`, surface runners, Web-Sol action source, and new server routes out of scope.

## 5. Source, installation, and production gates are separate

The earlier records over-serialized deterministic source work behind physical resource and installed-proof completion. That is corrected.

### 5.1 Source START gates

A C3 source worker may start only after one fresh turn proves:

1. this complete records packet is independently accepted, protected, and its records writer released;
2. PR #537's overlapping Control Room inventory paths are repaired, protected, and writer-released;
3. PR #531's overlapping Control Room CSS path is current-base proven, protected, and writer-released;
4. protected master contains accepted C2 source and a compatible same-SHA Skillpack;
5. the exact thirteen paths are free across open PRs, renames, branches, registered worktrees, processes, and source writers;
6. one exact implementation branch/PR and one concrete eligible writer are bound;
7. Decision-First Today, remote X1, navigation, and Steward boundaries are freshly read;
8. no C3 source/ref effect is unknown.

The source START gate does not require #499, #501 proof maintenance, #359, PF-1/#338, #340, an installed Web-Sol generation, or an online approved profile host. Those owners touch no C3 source path.

If a later implementation chooses to consume #501's proof-artifact helper, that helper's cross-process stale-PASS repair becomes a proof-acceptance dependency for the corresponding claim; it does not block creation of the pure projection or UI source.

### 5.2 Source acceptance gates

The source worker must still deliver one complete local vertical through deterministic C2 fixtures and isolated required-browser proof:

```text
closed C2 fixtures
-> pure C3 validation/aggregation
-> explicit local gather opt-in
-> one existing cache generation
-> Advanced / Web Sessions
-> legal complete/partial/unavailable/empty rendering
-> exact binding correlation + NAVIGATION_UNSUPPORTED
-> Today isolation
-> remote omission
-> Steward six-read zero-C2 non-interference
```

It must return RED-to-GREEN, mutation, payload, privacy, focused, browser, repository, security, and exact-head independent review evidence.

Source protection establishes only:

```text
BUILT_NOT_PROVEN / NOT_INSTALLED / DEFAULT_OFF
```

### 5.3 Installed proof and production acceptance

Physical-resource proof remains a later separately admitted sequence:

```text
#499 H2 source release and real read-health qualification
-> #359 Profile B + dedicated non-sensitive account/empty Project release
-> PF-1 A/B and exact resource release
-> #340 exact protected C2+C3 installation checkpoint
-> C3 read-only two-profile visible canary
   and separately leased PF-1 C on the same checkpoint
-> #340 rollback or reviewed retained-install disposition
-> independent C3 production-evidence review
```

The C3 canary consumes #340's installed checkpoint before terminal rollback. It does not install, modify, foreground, navigate, call a provider, own the profile lease, or roll back anything. PF-1 and C3 remain separate operations/evidence consumers even when sequenced on the same installed epoch.

Do not require a second installation cycle merely because the source and physical tracks were separated.

Production acceptance still requires real complete, partial/unavailable, duplicate-tab, correction, viewport, privacy, no-action, Today, remote, Steward, and cleanup evidence. Only that can support `PROVEN_LIVE` for the exact two-profile epoch.

## 6. UI and documentation corrections

Task 8 and operator documentation must show inventory and probe coverage separately.

Examples:

```text
Inventory complete · 2 of 2 profiles collected · 4 browser rows
Probe coverage partial · 3 of 4 rows observed

Inventory complete · 1 of 1 profiles collected · 0 browser rows
Probe coverage none · no browser row required probing

Inventory partial · 1 profile collected · 1 unavailable
Total browser rows unknown
```

A complete inventory with partial probes must never render just `Partial`. An unavailable inventory must never render exact zero. `Not sampled in this Control Room generation` is distinct from `EMPTY_IN_SCOPE` and `UNAVAILABLE`.

The navigation-capability addendum remains controlling:

```text
exact correlation counts
+ explicit Navigation unavailable
+ zero enabled Open controls
+ zero action request
```

## 7. Required current verification and rereview

The repaired records head must receive:

- exact changed-file/blob/tree readback;
- a current merge ref with protected master as first parent and repaired head as second parent;
- terminal repository and security checks for that exact current integration;
- the same existing non-author reviewer refreshed on carrier `C0BSBM78V1N/1788911403.030389`;
- one current-head `APPROVE | REQUEST_CHANGES`;
- explicit Sol adjudication;
- guarded records-only protection and protected readback;
- records-writer release before any implementation START.

The reviewer must specifically verify:

- `EMPTY_IN_SCOPE` exact-zero total;
- complete inventory with partial/none probes keeps exact totals;
- precise inventory/probe reason split;
- public builder default-off behavior;
- six Steward reads make zero C2 calls;
- exact thirteen-path ceiling;
- staged source-versus-installed proof;
- every retained privacy, deadline, payload, no-navigation, remote, Today, and no-duplicate-system boundary.

Every earlier review and CI campaign remains historical for its actual head.

## 8. Effect and stop boundary

This records repair grants no Ready, merge, source implementation, browser/profile/account/native action, provider call, Runtime/Agent OS mutation, installation, deployment, navigation, or production authority.

PR #546 remains Draft/Hold. The records writer stops after one ordinary same-branch commit, exact remote readback, current PR-body/receipt update, and same-carrier reviewer continuation. The reviewer then returns a fresh exact-head verdict and awaits explicit Sol `CONTINUE | REQUEST_REPAIR | STOP`.

No new review task, watcher, carrier, PR, branch, cache, endpoint, lifecycle, identity, queue, retry, or state plane is created.
