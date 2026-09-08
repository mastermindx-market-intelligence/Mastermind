# Web-Sol Fleet Census C3 Control Room Implementation Plan

> **For the assigned implementation worker:** use superpowers:executing-plans task by task, superpowers:test-driven-development before every behavior change, superpowers:systematic-debugging for unexpected failures, and superpowers:verification-before-completion before any completion claim.

**Goal:** Deliver one bounded, read-only, multi-profile Web-Sol fleet observation inside the existing local Chairman Control Room at **Advanced → Web Sessions**, using protected C2 reads and existing surface bindings without creating another source reader, cache, lifecycle, registry, retry plane, endpoint, or remote profile surface.

**Architecture:** The existing Control Room gather layer groups valid ChatGPT surface bindings into unique adapter instances and performs at most four deterministic sequential C2 reads inside one 40-second admission window. A new pure `mastermind.web_sol_fleet_projection.v1` module validates and aggregates those already-collected results. The canonical Control Room adds one local-only key; the existing cached `/api/state` path serves it; the existing UI renders it; remote X1 type-checks and omits it.

**Tech Stack:** Python 3.12, existing Web-Sol Python/native contracts, dependency-free browser JavaScript, existing HTML/CSS, pytest, Node syntax checks, Playwright through the existing UI test harness.

**Spec:** `docs/superpowers/specs/2026-09-08-web-sol-fleet-c3-control-room-design.md`

**Operation:** `web-sol-fleet-c3-source-20260908-sol-001`  
**Parent:** Mastermind issue #501 / approval comment `5592792563`  
**Plan source operation:** `web-sol-fleet-c3-design-plan-source-20260908-sol-001`  
**Admission state:** `PRE_START / DEPENDENCY_HELD / effect=NONE`

---

## 0. Admission, exact source, and path freeze

Do not implement until every spec section 14 gate is positively true in one fresh turn.

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

**Preflight commands/evidence:**

```bash
git fetch origin master
git rev-parse origin/master
git rev-parse origin/master^{tree}
git status --short
git diff --check
git worktree list --porcelain
```

Perform the repository’s current complete open-PR/path/rename census and registered-worktree/process/source-writer census. Confirm no exact path is owned by another source carrier. Re-read #501, #531, #537, #542, #340, #359, #338, #480 and the current Decision-First records.

Create exactly one branch from the action-time protected SHA only after the gates pass:

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

Write tests that import:

```python
from control_plane import web_sol_fleet_projection as fleet
```

Define and assert the exact public API:

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

Use these names. The two closed input envelopes and every nested key are frozen by the spec.

RED cases:

- exact top-level key set;
- exact profile and session key sets;
- unknown key at every level;
- bool-as-int refusal;
- malformed/non-Z UTC timestamps;
- completion before start;
- `admission_window_ms` other than exactly `40000`;
- negative/non-integer/unsafe actual duration;
- invalid zero/non-sequential session `slot`;
- invalid 64-hex adapter or conversation fingerprint;
- invalid enums;
- free-form reason text;
- non-null model/effort/served-model;
- model evidence other than `UNVERIFIED`;
- locator/URL/profile/folder/account/path/traceback/credential keys anywhere;
- non-finite values and oversized strings;
- output greater than 524,288 canonical JSON bytes;
- unknown/missing keys in `expected_profiles`, `navigation_index`, `observations`, and input `sessions`;
- private representative binding or locator material passed into the pure module.

### Step 2: Verify RED

Run:

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_web_sol_fleet_projection.py
```

Expected: collection/import failure because the module does not exist. Record the exact failure.

### Step 3: Implement the smallest closed types/validators

Implement constants and pure helpers only. No integration imports, I/O, clocks, environment, subprocess, sockets, filesystem, model, or network.

Use exact-key validation and `type(value) is int` for integers. Deep-copy accepted inputs/outputs. Serialize with:

```python
json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

Enforce `MAX_FLEET_JSON_BYTES = 512 * 1024`.

### Step 4: Verify GREEN

Run the focused test. Confirm every test passes, then commit the pure contract and tests.

This commit is not a useful C3 release by itself.

---

## Task 2: Implement count, coverage, ordering, and correction equations

**Files:**
- Modify: `tests/test_web_sol_fleet_projection.py`
- Modify: `control_plane/web_sol_fleet_projection.py`

### Step 1: Write RED behavior tests

Cover:

1. valid empty binding state -> `EMPTY_IN_SCOPE`, exact zero totals;
2. bindings missing -> `UNAVAILABLE`, expected/total counts null;
3. bindings invalid -> `UNAVAILABLE`;
4. one complete profile -> complete exact totals;
5. one partial profile -> retained rows, fleet `PARTIAL`, total null;
6. one collected + one unavailable -> known rows retained, total null;
7. all expected profiles unavailable -> `UNAVAILABLE`, not empty;
8. five expected profiles -> four selected observations plus one omitted, `ADAPTER_LIMIT`, total null;
9. fleet deadline not-attempted row -> partial, increments `not_attempted_profile_count`, and emits `FLEET_DEADLINE`;
10. completed-after-deadline row -> partial and `FLEET_DEADLINE`;
11. complete inventory + partial probe coverage -> complete inventory, partial probe coverage;
12. duplicate tabs within one profile -> one unique conversation and correct duplicate count;
13. same conversation fingerprint across two adapters -> two profile-scoped unique observations;
14. input order permutations -> byte-identical canonical output;
15. caller mutation after composition -> prior output unchanged;
16. corrected next input -> warning removed without sticky state.

### Step 2: Verify RED

Run only the new equations tests and confirm failures name missing behavior rather than test setup errors.

### Step 3: Implement minimal deterministic aggregation

- sort expected profiles by adapter ID;
- sort observations by adapter ID;
- reject duplicates and observations outside the expected set;
- preserve each validated C2 profile snapshot’s session order by exact one-based `slot`;
- derive every count from rows; never trust caller-supplied totals;
- sort/deduplicate reason codes;
- compute coverage from the frozen truth table.

Do not add history or a clock read.

### Step 4: Verify GREEN and commit

Run the complete projection suite twice and compare canonical output digest for one permuted fixture.

---

## Task 3: Add deterministic adapter grouping and one-call-per-profile gather

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED target-derivation tests

Use valid `mastermind.surface_bindings.v1` fixtures.

Required cases:

- non-ChatGPT bindings excluded;
- only `chatgpt_managed_env` accepted;
- two conversation bindings for the same managed profile produce one adapter target;
- adapter identity uses the existing `web_sol_instance.adapter_instance_id`;
- conversation identity uses the existing `web_sol_client.conversation_fingerprint`;
- the pure navigation index carries only `(conversation_fingerprint, binding_id)`;
- target and binding order are deterministic under input permutations;
- representative is the lower-case minimum binding ID;
- representative changes do not change adapter identity;
- malformed binding input produces no C2 call and an unavailable fleet document;
- valid empty document produces no C2 call and `EMPTY_IN_SCOPE`;
- five adapters produce only four call targets and one explicit omission.

### Step 2: Verify RED

Run:

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_chairman_control_room.py \
  -k 'web_sol_fleet or fleet_census'
```

Confirm failures occur before implementation.

### Step 3: Implement the private local gather seam

Inside `chairman_control_room.py`, add private helpers with injectable boundaries:

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
) -> dict[str, Any]:
    ...
```

Production defaults import `web_sol_instance`, `web_sol_client`, and `web_sol_census_protocol` only inside the local helper. Avoid a module-scope integration import.

Rules:

- one deterministic representative binding per adapter;
- max four;
- sequential loop;
- one C2 call each;
- no retry/fallback;
- no alternate socket/profile;
- fixed safe error mapping;
- no raw exception text;
- no profile/locator data in the returned wire.

### Step 4: Verify GREEN and commit

Run target/gather tests and all Web-Sol native census tests that exercise the client’s stable behavior. Do not modify C2 source to make C3 tests pass.

---

## Task 4: Prove the shared 40-second admission window and no replay

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED controlled-clock tests

Use an injected monotonic clock and fake C2 call.

Cases:

- four fast calls execute sequentially and in adapter order;
- no second call begins before the prior call returns;
- a call failure does not trigger retry;
- a call returning at/after the fleet deadline preserves actual elapsed time, is retained only as partial, and stops later calls;
- insufficient remaining admission budget emits `NOT_ATTEMPTED / FLEET_DEADLINE`;
- invalid receipt or identity mismatch does not retry or switch representative;
- unknown exception maps to fixed `CENSUS_UNAVAILABLE`;
- operation keys/nonces are unique per attempted adapter and absent from public output;
- total invocation count never exceeds four;
- a fifth adapter is never called;
- the gather performs zero writes and has no retained state across calls.

### Step 2: Verify RED

Confirm at least the sequential/deadline/retry tests fail on the initial gather implementation.

### Step 3: Implement minimal budget enforcement

The outer budget is an admission boundary, not a promise that an uninterruptible local syscall can be killed safely.

- start the fleet monotonic admission window immediately before the first possible C2 call;
- expose fixed `admission_window_ms=40000` while preserving actual `duration_ms`;
- do not start an attempt when its full C2 budget cannot fit;
- after a returned call, compare to the fleet deadline;
- after an overrun, downgrade and stop;
- do not wrap C2 in a timeout thread/process;
- never cancel and then start another profile.

### Step 4: Verify GREEN and commit

Run the focused gather suite twice. Assert exactly one call per attempted adapter.

---

## Task 5: Wire one already-collected value through the pure compositor

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`

### Step 1: Write RED compositor tests

Add `web_sol_fleet` to the pure signature and closed output.

Cases:

- valid fleet document is copied verbatim;
- caller mutation after composition cannot mutate output;
- invalid document becomes `null` and one fixed degradation;
- optional projection module absent still composes all existing sections;
- no C3 input changes attention, work, autonomy, placement, bindings, or disagreements;
- same inputs remain byte-deterministic;
- C3 has no clock/file/socket/environment reads in the pure path.

### Step 2: Verify RED

Run the focused composition tests.

### Step 3: Implement minimal optional-owner composition

Use the existing `_optional_control_plane_module` pattern for the pure projection module.

Add:

```text
web_sol_fleet
```

to `OUTPUT_KEYS` and the final document only.

Do not add C3 values to `sources`, `attention`, `work`, `autonomy`, or `degraded` except the one fixed invalid-source message.

### Step 4: Verify GREEN and commit

Run all `tests/test_chairman_control_room.py`.

---

## Task 6: Gather once per canonical cache generation

**Files:**
- Modify: `tests/test_chairman_control_room.py`
- Modify: `control_plane/chairman_control_room.py`
- Modify: `tests/test_chairman_control_room_server.py`

### Step 1: Write RED integration tests

Prove:

- `build_control_room()` gathers C3 once;
- precursor autonomy compose and final compose receive the same object;
- the C3 gather is not repeated during the precursor compose;
- an absent optional module makes zero Web-Sol calls;
- binding load occurs through the existing single read;
- direct `compose_control_room()` never gathers;
- current `/api/state` envelope carries the canonical document without a new endpoint;
- a retained cached document remains visibly dated while refresh is in flight/error.

### Step 2: Verify RED

Run:

```bash
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_chairman_control_room.py \
  tests/test_chairman_control_room_server.py \
  -k 'web_sol_fleet or fleet_census or state_cache'
```

The server tests must still pin that `/api/state` carries the canonical C3 key and retains existing cache-generation semantics. Leave the server production file untouched.

### Step 3: Implement gather placement

Gather after the existing binding load and before the precursor compose. Pass the same value to both compose calls.

Do not:

- add a C3 cache;
- add a route;
- call `/api/refresh-builds`;
- add an interval;
- change the state TTL;
- alter refresh generation arbitration.

### Step 4: Verify GREEN and commit

Run all Control Room compositor/server tests.

---

## Task 7: Keep remote X1 local-data-free

**Files:**
- Modify: `tests/test_chairman_control_room_remote.py`
- Modify: `control_plane/chairman_control_room_remote.py`

### Step 1: Write RED remote tests

Cases:

- canonical document with valid C3 still produces the exact existing remote output key set;
- remote output contains no `web_sol_fleet`, adapter ID, conversation fingerprint, binding ID, seat ref, model field, profile count, or generation cue;
- a non-null non-mapping C3 branch is rejected;
- sensitive/path/URL/session-shaped data nested inside the local-only mapping cannot hide behind omission;
- remote extracted release boots without `control_plane/web_sol_fleet_projection.py`;
- `REQUIRED_RUNTIME_PATHS` remains unchanged;
- `compose_collected()` supplies `web_sol_fleet=None` explicitly or through the new default without a local gather.

### Step 2: Verify RED

Run the remote suite and confirm closed-key failure occurs before implementation.

### Step 3: Implement type-check-and-drop

At the remote boundary:

- accept `None`;
- otherwise require a mapping;
- run the existing recursive sensitive-value refusal over that mapping;
- omit it from the remote document.

Do not duplicate the full C3 validator and do not stage the local C3 module or Web-Sol integration into the remote release solely to discard the data.

### Step 4: Verify GREEN and commit

Run all remote projection/release tests and the extracted no-`.git` boot proof.

---

## Task 8: Build the real Advanced Web Sessions consumer

**Files:**
- Modify: `app/static/chairman_control/index.html`
- Modify: `app/static/chairman_control/control_room.js`
- Modify: `app/static/chairman_control/control_room.css`
- Modify: `tests/test_chairman_control_room_ui_x1.py`

### Step 1: Write structural RED tests

Require:

- one `#ccr-web-sol-fleet` card inside `#system`;
- it follows canonical inputs and precedes navigation capability;
- no new primary nav item;
- no C3 markup in Today/Autonomy/Work/Surfaces;
- remote HTML contains no C3 container;
- no inline script/style;
- existing CSP/static map remains unchanged.

### Step 2: Write actual-browser RED tests

Use the existing intercepted-fixture Playwright harness.

Render:

1. complete two-profile fleet;
2. partial fleet with one collected and one unavailable;
3. all-unavailable fleet;
4. valid empty-in-scope;
5. five expected/four attempted with exact omitted count;
6. duplicate tabs;
7. one exact navigation-match binding ID resolved through the canonical binding summary;
8. more than eight exact matches with explicit omitted count;
9. null model/effort;
10. correction from partial to complete on the next loaded canonical document;
11. refresh-in-flight and refresh-error dated copy;
12. malformed C3 document causing fixed unavailable rendering, not script failure;
13. 375, 760, 1280, 1440, and 1920 widths;
14. light and dark themes;
15. remote page unchanged.

Assert zero page errors and zero unexpected requests.

### Step 3: Verify RED

Run:

```bash
MMX_REQUIRE_INVENTORY_BROWSER=1 \
python3 -B -m pytest -p no:cacheprovider -o addopts= -q \
  tests/test_chairman_control_room_ui_x1.py \
  -k 'web_sol_fleet'
```

### Step 4: Implement minimal UI

Use safe text nodes and existing helpers.

Recommended renderer:

```javascript
function renderWebSolFleet(fleet, envelope) { ... }
```

Render explicit labels:

```text
COMPLETE IN SCOPE
PARTIAL
UNAVAILABLE
EMPTY IN SCOPE
PROBE COVERAGE PARTIAL
TOTAL UNKNOWN
```

Resolve each match ID against the existing `allBindings()`/canonical binding summaries, then use the existing `openBinding()` path. Never build a URL from C3 data and never elect one of multiple matches.

Do not render running/idle/capacity/account-online/actual-model claims.

### Step 5: Verify GREEN and commit

Run the actual-browser C3 tests and the full existing UI/remote/topbar inventory suites. Preserve #531/#537 semantics exactly.

---

## Task 9: Payload, privacy, and hostile mutation proof

**Files:**
- Modify: `tests/test_web_sol_fleet_projection.py`
- Modify: `tests/test_chairman_control_room.py`
- Modify: `tests/test_chairman_control_room_ui_x1.py`

### Step 1: Build worst-case legal fixtures

Construct four complete 128-row C2 snapshots with:

- maximum fixed-length timestamps/fingerprints;
- every nullable boolean populated;
- duplicate groups;
- eight projected navigation matches on every session;
- exact omitted navigation counts;
- all closed enum extremes.

Prove canonical C3 JSON is at most 524,288 bytes. If the legal worst case exceeds the limit, reduce projected redundancy through the same schema before acceptance; do not silently truncate rows or raise the C2 native guard.

### Step 2: Add hostile privacy tests

Attempt to inject:

- raw `https://` and `file://` URLs;
- `/Users`, `/Volumes`, `/home`, `/private`, `/var`, `/tmp`, `/etc`, `/opt`, `/Library`;
- Windows drive and UNC paths;
- profile/folder/account names;
- email addresses;
- cookies/tokens/password/secret/auth strings;
- raw exception/traceback;
- prompt/transcript/reasoning/model-output content;
- arbitrary HTML;
- non-finite JSON;
- control characters and oversized strings.

Only fixed closed fields may survive.

### Step 3: Mutation discrimination

Mutate one behavior at a time and require a test failure:

- missing binding file -> empty;
- partial total -> integer;
- all unavailable -> zero complete;
- fifth adapter call enabled;
- retry on C2 failure;
- parallel calls;
- adapter grouping by seat/title instead of instance ID;
- cross-profile fingerprint deduplication;
- newest binding election;
- raw exception copied;
- non-null model inference;
- remote projection leaks C3;
- UI says “running” or “idle”;
- over-limit payload accepted.

Restore each mutation and re-run GREEN.

### Step 4: Commit proof tests

Record exact mutant list and outcomes in the PR body/evidence packet.

---

## Task 10: Documentation and complete source verification

**Files:**
- Modify: `docs/CHAIRMAN_CONTROL_ROOM.md`

### Step 1: Document operator truth

Add:

- Advanced → Web Sessions location;
- meaning of expected/attempted/collected/omitted;
- inventory versus probe coverage;
- observation timestamp/cache behavior;
- no worker/capacity/model inference;
- no new refresh endpoint;
- exact source/install/production distinctions;
- troubleshooting for missing bindings, C2 unavailable, partial inventory, and expired retained cache;
- #340 installation proof dependency.

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

Set required browser flags so browser absence fails rather than skips for the C3 evidence lane.

### Step 3: Run current repository/security proof

Use the repository’s discovery-first current test gate. Record:

- protected base;
- source head/tree;
- generated merge-ref commit/tree and ordered parents;
- actual checkout from logs;
- test and security conclusions;
- every skip/limitation;
- exact changed paths.

Do not transfer a green result from an older head or older merge ref.

### Step 4: Independent review

A genuine non-author reviewer must assess:

- no duplicate owner/control plane;
- exact binding/adapter identity;
- strict null/coverage equations;
- sequential/no-retry deadline behavior;
- privacy and payload bound;
- gather-once/pure compose;
- Today isolation;
- remote omission;
- real consumer usefulness;
- proof class honesty.

Repair on the same branch/PR only.

---

## Task 11: Installed two-profile production proof

**Owner boundary:** this task is not performed by the source worker unless issue #340 explicitly transfers the exact installed-evidence duty after its own gates.

Required real journey:

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

Evidence must include:

- protected source/package/artifact digests;
- host/profile opaque fingerprints;
- complete/partial/unavailable screenshots;
- C2 CLI receipts matching the visible generation;
- no private content leak;
- no Today/remote regression;
- fault injection and zero retry;
- rollback/residual-state proof;
- independent evidence review.

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
