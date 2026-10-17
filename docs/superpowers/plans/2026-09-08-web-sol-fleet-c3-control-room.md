# Web-Sol Fleet Census C3 Control Room Implementation Plan

> **For the assigned implementation worker:** use superpowers:executing-plans task by task, superpowers:test-driven-development before every behavior change, superpowers:systematic-debugging for unexpected failures, and superpowers:verification-before-completion before any completion claim.

**Goal:** Deliver one bounded, read-only, multi-profile Web-Sol fleet observation inside the existing local Chairman Control Room at **Advanced → Web Sessions**, using protected C2 reads and existing surface bindings without creating another source reader, cache, lifecycle, registry, retry plane, endpoint, or remote profile surface.

**Architecture:** The existing Control Room gather layer groups one loaded valid binding document into unique ChatGPT adapter instances and performs at most four deterministic sequential C2 reads inside one 40-second admission window. A new pure `mastermind.web_sol_fleet_projection.v1` module validates and aggregates closed, content-free inputs. The canonical Control Room adds one local-only key; the existing cached `/api/state` path serves it; the existing UI renders it; remote X1 type-checks and omits it.

**Tech Stack:** Python 3.12, existing Web-Sol Python/native contracts, dependency-free browser JavaScript, existing HTML/CSS, pytest, Node syntax checks, Playwright through the existing UI test harness.

**Spec:** `docs/superpowers/specs/2026-09-08-web-sol-fleet-c3-control-room-design.md`

**Operation:** `web-sol-fleet-c3-source-20260908-sol-001`  
**Parent:** Mastermind issue #501 / approval comment `5592792563`  
**Plan source operation:** `web-sol-fleet-c3-design-plan-source-20260908-sol-001`  
**Self-review parent:** `b45f042040157c03fc97c5d6ad27acaa4c5b93e4`  
**Admission state:** `PRE_START / DEPENDENCY_HELD / effect=NONE`

The self-review repair freezes exact C2 receipt/null mapping, rejects duplicate case-folded binding IDs, bounds pure inputs, caps displayed navigation matches at six, and removes the contradictory synthetic payload fallback. These are plan corrections, not C3 implementation.

---

## 0. Admission, exact source, and path freeze

Do not implement until every spec section 15 gate is positively true in one fresh turn, including protection and source-writer release of the C3 records carrier itself.

**Expected implementation ceiling:**

1. Create `control_plane/web_sol_fleet_projection.py`
2. Modify `control_plane/chairman_control_room.py`
3. Modify `control_plane/chairman_control_room_remote.py`
4. Modify `app/static/chairman_control/index.html`
5. Modify `app/static/chairman_control/control_room.js`
6. Modify `app/static/chairman_control/control_room.css`
7. Create `tests/test_web_sol_fleet_projection.py`
8. Modify `tests/test_chairman_control_room.py`
9. Modify `tests/test_chairman_control_room_remote.py`
10. Modify `tests/test_chairman_control_room_ui_x1.py`
11. Modify `tests/test_chairman_control_room_server.py`
12. Modify `docs/CHAIRMAN_CONTROL_ROOM.md`

`scripts/chairman_control_room.py` is not modified. A required server production edit is a path-widening decision return before modification.

**Preflight:**

```bash
git fetch origin master
git rev-parse origin/master
git rev-parse origin/master^{tree}
git status --short
git diff --check
git worktree list --porcelain
```

Run the repository’s current complete open-PR/path/rename census and registered-worktree/process/source-writer census. Re-read #501, #531, #537, #546, #542, #340, #359, #338, #480 and current Decision-First records. Confirm the exact expected paths are unowned and no C3 effect is unknown.

Only then create one implementation branch from the action-time protected SHA:

```text
sol/web-sol-fleet-c3-20260908
```

Return `DEPENDENCY_HELD / effect=NONE` if any gate is missing. Do not create a placeholder branch, worktree, PR, or receiver.

---

## Task 1: Freeze the pure C3 contract with RED tests

**Files:**
- Create: `tests/test_web_sol_fleet_projection.py`
- Create after RED: `control_plane/web_sol_fleet_projection.py`

### Step 1: Write closed-shape RED tests

Import:

```python
from control_plane import web_sol_fleet_projection as fleet
```

Require exactly:

```python
fleet.validate_fleet_projection(value: object) -> dict
fleet.compose_fleet_projection(
    *,
    expected_profiles: list[dict],
    observations: list[dict],
    started_at: str,
    completed_at: str,
    duration_ms: int,
    binding_state: str,
) -> dict
```

Tests must pin:

- exact top-level, profile, session, expected-profile, navigation-index, and observation key sets;
- fixed schema/scope/admission window;
- `MAX_ADAPTERS=4`, C2 owner `TOTAL_SECONDS=10`, `MAX_EXPECTED_PROFILES=8192`, total navigation rows `<=8192`, `MAX_NAVIGATION_MATCHES_PER_SESSION=6`, C2 rows `<=128`, and output `<=524288` bytes;
- exact fleet/profile/receipt/C2 enums;
- unknown key refusal at every level;
- bool-as-int refusal;
- malformed/non-Z UTC timestamp and completion-before-start refusal;
- negative, non-finite, non-integer, regressing, or unsafe durations;
- invalid zero/non-sequential session `slot`;
- invalid lower-case 64-hex adapter/conversation fingerprint;
- invalid UUID binding ID;
- duplicate adapter ID;
- duplicate `binding_id.lower()` anywhere in the input;
- `binding_count != len(navigation_index)`;
- non-empty expected/observation inputs under `MISSING` or `INVALID` binding state;
- observation for an omitted or unknown adapter;
- non-null model/effort/served-model or model evidence other than `UNVERIFIED`;
- locator/URL/profile/folder/account/path/traceback/credential/operation-key/nonce fields anywhere;
- non-finite JSON, control characters, oversized strings, and canonical output above 524,288 bytes.

### Step 2: Verify RED

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_web_sol_fleet_projection.py
```

Expected initial result: import/collection failure because the module does not exist. Record it.

### Step 3: Implement the smallest pure validator surface

Use exact-key validation, `type(value) is int`, deep copies, and canonical compact JSON:

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

No integration import, I/O, clock, environment, subprocess, socket, filesystem, network, model, or caller callback belongs in the pure module.

`validate_fleet_projection` rejects malformed or oversized documents. No synthetic payload fallback.

### Step 4: Verify GREEN and commit

Run the focused contract tests. Commit only the pure module and its owning test when green. This is not an independently useful C3 release yet.

---

## Task 2: Implement deterministic count, coverage, probe, and correction equations

**Files:**
- Modify: `tests/test_web_sol_fleet_projection.py`
- Modify: `control_plane/web_sol_fleet_projection.py`

### Step 1: Write RED behavior tests

Cover:

1. `AVAILABLE` + zero expected -> `EMPTY_IN_SCOPE`, exact zero totals, `probe_coverage=NONE`;
2. `MISSING` -> `UNAVAILABLE / BINDINGS_UNAVAILABLE`, expected null, other profile counts zero;
3. `INVALID` -> `UNAVAILABLE / BINDINGS_INVALID`;
4. one complete profile -> complete exact totals;
5. one collected partial-inventory profile -> retained rows, `PARTIAL`, total null;
6. one collected complete profile with partial probes -> fleet inventory complete but probe partial and `PROFILE_PARTIAL`;
7. one collected + one unavailable -> known rows retained, fleet partial, total null;
8. all expected profiles unavailable -> `UNAVAILABLE`, never empty/zero-complete;
9. five expected profiles -> four selected profile rows, one omitted, `ADAPTER_LIMIT`;
10. selected deadline-skipped profile -> `NOT_ATTEMPTED`, exact not-attempted count, `FLEET_DEADLINE`;
11. collected or unavailable result completing at/after deadline -> non-complete and `FLEET_DEADLINE`;
12. duplicate tabs within one profile -> exact unique/duplicate count;
13. same fingerprint in two adapters -> two profile-scoped unique observations;
14. zero known sessions -> probe coverage `NONE`;
15. some `OBSERVED` rows -> probe `PARTIAL`;
16. all known rows `OBSERVED` under complete fleet -> probe `COMPLETE_IN_SCOPE`;
17. input-order permutations -> byte-identical output;
18. caller mutation after composition -> prior output unchanged;
19. corrected next input -> warning disappears without sticky state.

Pin equations:

```text
selected = min(expected, 4)
len(profiles) = selected
attempted + not_attempted = selected
collected + unavailable = attempted
expected = selected + omitted
```

All output counts are derived, never caller-authored.

### Step 2: Verify RED

Run only the new equation tests and confirm failures name missing behavior rather than setup errors.

### Step 3: Implement minimal aggregation

- canonicalize expected profiles by adapter ID;
- canonicalize navigation rows by `(binding_id.lower(), binding_id)`;
- canonicalize observations by adapter ID;
- reject duplicates and observations outside the selected first four;
- preserve session order by validated one-based `slot`;
- derive exact top-level reason set;
- derive all counts, profile totals, fleet coverage, and probe coverage from rows and fixed state.

Do not add a clock, history, fallback count, or inferred total.

### Step 4: Verify GREEN and commit

Run the complete projection suite twice and compare one canonical permutation digest.

---

## Task 3: Add deterministic adapter grouping and binding safety

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED target-derivation tests

Use real valid `mastermind.surface_bindings.v1` fixtures.

Required cases:

- non-ChatGPT binding excluded;
- only `chatgpt_managed_env` included;
- two conversation bindings for one managed profile produce one adapter target;
- adapter identity comes only from existing `web_sol_instance.adapter_instance_id`;
- conversation identity comes only from existing `web_sol_client.conversation_fingerprint`;
- pure navigation index carries only conversation fingerprint and exact source-spelled binding ID;
- adapter/binding order deterministic under permutations;
- representative sort key is `(binding_id.lower(), binding_id)`;
- representative changes do not change adapter identity;
- duplicate case-folded binding IDs anywhere -> `INVALID`, zero C2 calls;
- structurally malformed binding document -> unavailable, zero C2 calls;
- existing permission warning with returned valid document remains available while the existing degraded warning survives;
- valid empty/no-eligible document -> `EMPTY_IN_SCOPE`, zero calls;
- more than 8,192 expected/navigation rows -> invalid;
- five adapters -> four targets and one explicit omission;
- no work ref, seat ref, profile ID, locator, URL, title, or account label enters pure input.

### Step 2: Verify RED

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_chairman_control_room.py \
  -k 'web_sol_fleet or fleet_census'
```

### Step 3: Implement the private local target seam

Inside `chairman_control_room.py`, add private, injectable helpers:

```python
def _web_sol_fleet_targets(bindings: Mapping[str, Any] | None) -> ...
def _gather_web_sol_fleet(
    bindings,
    *,
    census_call=None,
    utc_now=None,
    monotonic=None,
    operation_key_factory=None,
    nonce_factory=None,
) -> dict[str, Any] | None:
    ...
```

Production defaults import Web-Sol instance/client/C2 protocol only inside the local helper. Avoid module-scope integration imports.

Keep the representative binding private. Return only the closed expected-profile input plus private call target in an internal type; never serialize the latter.

### Step 4: Verify GREEN and commit

Run target tests and all stable Web-Sol instance/client/census protocol suites. Do not modify protected C2 source to make C3 pass.

---

## Task 4: Prove request construction, sequential acquisition, deadline, and no replay

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED controlled-clock/client tests

Inject aware UTC samples, monotonic samples, factories, and a fake C2 call.

Required cases:

- issued/expires window is exactly owner-valid and no longer than C2 `TOTAL_SECONDS`;
- operation keys and nonces are unique per attempted profile and never appear in public output;
- invalid/naive/regressing UTC or invalid monotonic samples produce fixed gather unavailability and zero fabricated fleet facts;
- four fast calls execute sequentially in adapter order;
- no later call begins before the prior return;
- one C2 call per attempted adapter, never more than four;
- fifth adapter never called;
- less than one full C2 budget remaining -> selected profile `NOT_ATTEMPTED / FLEET_DEADLINE`;
- a call returning strictly before deadline -> `completed_within_fleet_deadline=true`;
- return at or after deadline -> false, no later call, top deadline reason;
- no retry on valid non-collected receipt, exception, invalid receipt, identity mismatch, or overrun;
- no representative/socket/profile failover;
- no retained state across gather invocations;
- no writes.

### Step 2: Write RED exact receipt/failure-mapping tests

Pin:

```text
accepted COLLECTED receipt -> state COLLECTED, receipt_status COLLECTED
accepted non-collected C2 status -> state UNAVAILABLE, receipt_status and reason preserved
invalid_census_value -> RECEIPT_INVALID, receipt_status null
receipt_identity_mismatch -> RECEIPT_IDENTITY_MISMATCH, receipt_status null
invalid_binding -> INVALID_BINDING, receipt_status null
other fixed/unknown client failure -> CENSUS_UNAVAILABLE, receipt_status null
lawful result returned late -> reason FLEET_DEADLINE_OVERRUN while receipt_status remains owner value
not attempted -> receipt_status and all attempt fields null
```

For attempted states, attempt times/duration and completion Boolean are present. C2 snapshot fields are present only for collected state.

### Step 3: Verify RED

Confirm sequential, receipt/null, deadline, and no-retry tests fail on the initial target-only code.

### Step 4: Implement minimal acquisition

- start fleet monotonic admission window immediately before first possible attempt;
- use existing C2 owner constants and validators;
- require full remaining C2 budget before start;
- use one request identity per attempt;
- catch only to fixed mapping; never expose `str(exc)`;
- preserve validated C2 snapshot rows and owner enums;
- stop after deadline overrun;
- do not wrap C2 in a timeout thread/process;
- do not cancel and start another adapter.

### Step 5: Verify GREEN and commit

Run focused gather tests twice. Assert exact call counts and no retry.

---

## Task 5: Wire one already-collected value through the pure compositor

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED compositor tests

Add optional `web_sol_fleet` to the pure signature and closed output.

Cases:

- valid fleet document copied verbatim but without aliasing;
- caller mutation after composition cannot mutate output;
- invalid supplied document -> null + exactly `web_sol_fleet: invalid`;
- optional projection module absent -> null, no fleet-specific degradation, every existing section intact;
- `None` supplied -> null and silent;
- no C3 input changes sources, attention, work, autonomy, placement, bindings, disagreements, or focus;
- same inputs byte-deterministic;
- pure path performs no clock/file/socket/environment read.

### Step 2: Verify RED

Run focused composition tests.

### Step 3: Implement optional-owner composition

Use the existing `_optional_control_plane_module` pattern. Add only `web_sol_fleet` to `OUTPUT_KEYS` and final document.

Do not add C3 values to `sources`, attention, work, autonomy, or source validity.

### Step 4: Verify GREEN and commit

Run all `tests/test_chairman_control_room.py`.

---

## Task 6: Gather once per canonical cache generation and fail safely

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `tests/test_chairman_control_room_server.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED integration tests

Prove:

- `build_control_room()` gathers C3 once after the existing binding load;
- precursor autonomy compose and final compose receive the same C3 object;
- direct `compose_control_room()` never gathers;
- absent optional module makes zero Web-Sol calls;
- missing/invalid binding input produces an explicit valid unavailable C3 document;
- unexpected target/time/projection failure produces `web_sol_fleet=null` and exactly `web_sol_fleet: unavailable`, with no exception text;
- binding load still occurs once;
- current `/api/state` envelope carries the canonical document without a new endpoint;
- retained cached C3 evidence remains dated while the existing refresh is in flight or failed;
- no C3 cache, route, interval, TTL, generation, or refresh arbitration appears.

### Step 2: Verify RED

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_chairman_control_room.py \
  tests/test_chairman_control_room_server.py \
  -k 'web_sol_fleet or fleet_census or state_cache'
```

Leave `scripts/chairman_control_room.py` untouched. Server tests pin reuse of the existing cached canonical document.

### Step 3: Implement gather placement

Gather once after binding load and before precursor compose. Pass the same value to both compose calls. Carry an internal fixed failure marker into the existing extra-degraded stage; never duplicate gather or expose a path/exception.

### Step 4: Verify GREEN and commit

Run all Control Room compositor/server tests.

---

## Task 7: Keep remote X1 local-data-free

**Files:**
- Modify: `tests/test_chairman_control_room_remote.py`
- Modify: `control_plane/chairman_control_room_remote.py`

### Step 1: Write RED remote tests

Cases:

- canonical document with valid C3 still produces the exact old remote output key set;
- remote output contains no C3 key, adapter/conversation fingerprint, binding ID, profile count, cue, or model field;
- non-null non-mapping C3 rejected;
- sensitive/path/URL/session-shaped data nested in a mapping cannot hide behind omission;
- safe but otherwise malformed local mapping may be omitted only because the canonical compositor already owns full validation;
- extracted remote release boots without `control_plane/web_sol_fleet_projection.py` or Web-Sol integrations;
- `REQUIRED_RUNTIME_PATHS` remains unchanged;
- remote composition supplies `None` and never runs the local gather.

### Step 2: Verify RED

Run the remote suite and confirm closed-key failure before implementation.

### Step 3: Implement type-check, sensitive-scan, and drop

Accept null or mapping, run the existing recursive sensitive-value refusal on mapping, and omit it. Do not duplicate the C3 validator or add local modules to the remote release.

### Step 4: Verify GREEN and commit

Run full remote projection, release-manifest, and no-`.git` extracted-boot proof.

---

## Task 8: Build the real Advanced Web Sessions consumer

**Files:**
- Modify: `app/static/chairman_control/index.html`
- Modify: `app/static/chairman_control/control_room.js`
- Modify: `app/static/chairman_control/control_room.css`
- Modify: `tests/test_chairman_control_room_ui_x1.py`

### Step 1: Write structural RED tests

Require:

- exactly one `#ccr-web-sol-fleet` card inside `#system`;
- it follows canonical inputs and precedes provider/navigation capability;
- no new primary nav item;
- no C3 markup in Today, Autonomy, Work, or Surfaces;
- remote HTML contains no C3 container;
- no inline script/style;
- existing CSP/static map unchanged.

### Step 2: Write actual-browser RED tests

Use the existing intercepted-fixture Playwright harness. Render:

1. complete two-profile fleet;
2. collected partial inventory;
3. complete inventory with partial/none probe coverage;
4. one collected plus one unavailable profile;
5. all-unavailable fleet;
6. valid empty-in-scope;
7. five expected/four selected with exact omitted count;
8. deadline not-attempted row;
9. duplicate tabs;
10. one exact navigation binding;
11. duplicate/missing canonical binding resolution suppressing Open;
12. more than six exact matches with exact total and omitted count;
13. null model/effort;
14. correction from partial to complete on next canonical document;
15. refresh-in-flight and refresh-error dated copy;
16. null or malformed direct fixture input causing fixed unavailable rendering, not script failure;
17. 375, 760, 1280, 1440, and 1920 widths;
18. light and dark themes;
19. remote page unchanged.

Assert zero page errors and zero unexpected requests.

### Step 3: Verify RED

```bash
MMX_REQUIRE_INVENTORY_BROWSER=1 \
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_chairman_control_room_ui_x1.py \
  -k 'web_sol_fleet'
```

### Step 4: Implement minimal UI

Use safe text nodes and existing helpers. Recommended renderer:

```javascript
function renderWebSolFleet(fleet, envelope) { ... }
```

Render exact coverage, profile cardinality, known-versus-total, probe coverage, observation time, and cache state. Display only a short adapter prefix.

For navigation, resolve a projected binding ID against `allBindings()` from the same loaded document. Only exactly one canonical object may reach existing `openBinding()`. Never post the C3 row itself or build a URL.

Never render running, idle, spare capacity, account online, all-company coverage, Sol Pro, or actual served model.

### Step 5: Verify GREEN and commit

Run C3 browser tests and all existing UI/remote/topbar/inventory suites. Preserve #531/#537 behavior and tests intact.

---

## Task 9: Prove payload, privacy, and hostile mutations

**Files:**
- Modify: `tests/test_web_sol_fleet_projection.py`
- Modify: `tests/test_chairman_control_room.py`
- Modify: `tests/test_chairman_control_room_ui_x1.py`

### Step 1: Build the exact legal worst case

Construct four collected 128-row C2 profiles with:

- longest legal closed strings and timestamps;
- every nullable Boolean populated where legal;
- 8,192 exact source binding rows distributed across expected profiles;
- exact duplicate/cue extremes;
- six displayed navigation matches on every session;
- exact total/omitted match counts.

Canonical compact JSON must be `<=524288` bytes. The same construction with seven displayed matches per session must fail the cap or frozen six-match assertion. Do not raise the ceiling or drop rows.

### Step 2: Add hostile privacy tests

Attempt to inject:

- `https://`, `file://`, arbitrary URL and HTML;
- `/Users`, `/Volumes`, `/home`, `/private`, `/var`, `/tmp`, `/etc`, `/opt`, `/Library`;
- Windows drive/UNC paths;
- profile/folder/account labels;
- email, cookie, token, password, secret, auth data;
- operation key, nonce, raw exception, traceback;
- prompt, transcript, reasoning, output, model prose;
- non-finite JSON, control characters, oversized strings.

Only frozen closed fields survive.

### Step 3: Mutation discrimination

Kill at least:

- missing binding -> empty;
- partial total -> integer;
- all unavailable -> complete zero;
- fifth adapter call;
- retry on C2 failure;
- parallel calls;
- adapter grouping by seat/title;
- duplicate binding-ID first-match election;
- cross-profile fingerprint deduplication;
- newest binding election;
- invalid receipt accepted;
- receipt status fabricated on exception;
- raw exception copied;
- non-null model inference;
- seven navigation matches displayed;
- payload fallback fabricated;
- remote C3 leak;
- UI says running/idle.

Restore each mutation and re-run GREEN. Record exact mutants and outcomes.

### Step 4: Commit proof tests

No production code-only commit may bypass the owning tests.

---

## Task 10: Documentation and complete source verification

**Files:**
- Modify: `docs/CHAIRMAN_CONTROL_ROOM.md`

### Step 1: Document operator truth

Add:

- Advanced → Web Sessions location;
- expected/selected/attempted/collected/unavailable/not-attempted/omitted meanings;
- inventory versus probe coverage;
- observation/cache timestamp behavior;
- no worker/capacity/model inference;
- no new refresh endpoint;
- exact source/install/production distinctions;
- duplicate-binding refusal;
- missing binding, C2 unavailable, partial inventory, and retained-cache troubleshooting;
- #340 installation-proof dependency.

### Step 2: Run focused verification

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_web_sol_fleet_projection.py \
  tests/test_chairman_control_room.py \
  tests/test_chairman_control_room_server.py \
  tests/test_chairman_control_room_remote.py \
  tests/test_chairman_control_room_ui_x1.py

node --check app/static/chairman_control/control_room.js
python3 -m compileall -q \
  control_plane/web_sol_fleet_projection.py \
  control_plane/chairman_control_room.py \
  control_plane/chairman_control_room_remote.py
git diff --check
```

Set required browser flags so C3 browser absence fails rather than skips.

### Step 3: Run current repository/security proof

Use the repository’s discovery-first current gate. Record exact protected base, source head/tree, generated merge ref/tree/parents, actual hosted checkout, test/security conclusions, every skip/limitation, and exact changed paths. Never transfer older green.

### Step 4: Independent review

A genuine non-author reviewer must assess:

- one canonical gather/cache and no duplicate owner;
- exact adapter/binding identity and duplicate-ID refusal;
- strict null/receipt/count/coverage equations;
- sequential request-window/deadline/no-retry behavior;
- pure-input and payload bounds;
- privacy and fixed failures;
- gather once/pure compose;
- Today isolation;
- remote omission;
- useful real consumer;
- proof-class honesty.

Repair only on the same branch/PR.

---

## Task 11: Installed two-profile production proof

**Owner boundary:** the source worker does not perform this task unless issue #340 explicitly transfers the exact installed-evidence duty after its own gates.

Required journey:

```text
exact protected C2+C3 generation
-> two released disposable non-Chairman profiles
-> exact package/install readback
-> real profile A and B C2 observations
-> one cached local Control Room generation
-> Advanced Web Sessions visible
-> one profile unavailable fault
-> correction on next composition
-> exact binding navigation
-> rollback or retained-install disposition
```

Evidence includes protected source/package/artifact digests, opaque host/profile identities, complete/partial/unavailable screenshots, matching C2 receipts, no private leak, no Today/remote regression, fault/no-retry proof, rollback/residual-state proof, and independent evidence review.

Only this may support `PROVEN_LIVE` for the exact two-profile C3 epoch.

---

## Stop condition and continuation handoff

The implementation worker stops at one immutable Draft/HOLD PR with:

- exact base/head/tree/paths;
- RED→GREEN and mutant receipts;
- focused and whole-repository/security results;
- browser evidence;
- no unresolved review threads;
- `BUILT_NOT_PROVEN / NOT_INSTALLED`;
- exact #340 production-proof handoff;
- explicit Sol `CONTINUE | REQUEST_REPAIR | STOP` awaited on the same carrier.

Do not mark Ready, merge, install, access Chairman profiles, run PF-1, infer model/effort, create a new cache/endpoint/registry, or start a successor wave.
