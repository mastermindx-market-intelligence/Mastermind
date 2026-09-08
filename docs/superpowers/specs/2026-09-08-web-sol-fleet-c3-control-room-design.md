---
schema: mastermind.web_sol_fleet_c3_architecture.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_issue: 501
chairman_approval_comment: 5592792563
protected_source: e18cab4f3ca41725fdb517623543fa4fb1aba467
protected_tree: 74c3af1fc2805eb0fdc7d8651c722fd5db40e3b8
skillpack_schema: mastermind.sol_skillpack.v1
skillpack_version: 1.0.1
minimum_bootstrap_major: 1
capability_state: SPEC_ONLY
production_effect: NONE
---

# Web-Sol Fleet Census C3 — Advanced Control Room design

**Date:** 2026-09-08  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** `CHAIRMAN_APPROVED / SPEC_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This records the Chairman-approved C3 architecture. It changes no browser, profile, account, extension, native host, socket, RuntimeBinding, Executive lifecycle, Control Room route, cache, service, provider state, installation, deployment, or production capability.

The approved C3 constants narrowly supersede only the earlier C3 scale proposal in the protected C2 design: use at most **four** enrolled profile adapters, deterministic **sequential** reads, and one **40-second fleet admission window**. All still-valid C2 identity, privacy, transport, no-retry, uncertainty, package, installation, and authority laws remain unchanged.

## 1. Executive ruling

C3 is the first useful multi-profile consumer of the protected C2 profile-local census.

The Chairman opens the existing local Control Room, enters **Advanced → Web Sessions**, and sees:

- which enrolled ChatGPT profile adapters were expected;
- which were actually attempted and observed;
- which were unavailable, partial, omitted, or not attempted before the fleet deadline;
- every retained browser-observation row, including duplicate tabs and unknown states;
- exact navigation matches to existing surface bindings;
- observation time and coverage limits;
- explicit `UNKNOWN / UNVERIFIED` model and effort evidence.

C3 is browser observation, not company execution. It never converts a visible tab, stop-button cue, selected window, profile process, or native response into a Worker, Job, START, capacity claim, source owner, or provider-compute assertion.

The existing Decision-First **Today** remains the Chairman default. C3 appears only in Advanced. It cannot change Chairman attention, decision admission, Sol accountability, priority, or the Today headline.

## 2. Current estate and prerequisites

Protected source already contains:

- the transient profile-local census popup and collector;
- complete extension-bundle rendering;
- C2 compact request/receipt/table validation;
- C2 native-host, extension-worker, client, and CLI transport;
- the existing `mastermind.surface_bindings.v1` navigation owner;
- the pure/local Chairman Control Room compositor, cache, local UI, and separate remote X1 projection.

C2 source is protected through PR #542 / merge `fc29e14a0d9ee41105264a5abc1d182daee7abbf`, but it is not installed or production-proven. Issue #340 remains the sole exact-generation two-profile install/fault/rollback owner. Issue #359 owns the missing second disposable profile and non-sensitive account-realm prerequisite. Issue #338 owns provider continuation/effect falsification. Issue #480 owns visible model/effort evidence.

C3 source START remains held until the exact path/source-owner gates in section 14 are true. This record does not assign a worker.

## 3. Canonical ownership

| Fact or effect | Canonical owner | C3 treatment |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle | Executive OS | not inferred or modified |
| organizational responsibility, decisions, discoveries, handoffs | Agent OS | not inferred or modified |
| exact logical target / provider generation | RuntimeBinding / SessionTarget owners | not replaced |
| browser navigation coordinate | `mastermind.surface_bindings.v1` | read-only input and exact navigation match |
| one profile census | protected C2 Web-Sol owner | validated input |
| provider quota/headroom | Macro Provider Control | not inferred |
| host CPU/memory/resource admission | Capacity / Workbench host-facts owners | not inferred |
| Control Room composition/cache | existing local Control Room owner | extended, not duplicated |
| remote X1 redaction/release | existing remote projection owner | C3 omitted and type-checked |
| source, review, CI, release evidence | GitHub | exact records |
| transport/hot collaboration | Slack | evidence only |

Deleting C3 changes only this optional Advanced observation. It cannot change any canonical organizational or runtime fact.

## 4. Architecture

```text
valid local surface bindings
  -> deterministic unique adapter groups
  -> at most four sequential C2 calls
  -> closed collected-observation input
  -> pure mastermind.web_sol_fleet_projection.v1
  -> existing mastermind.chairman_control_room.v1
  -> existing process-memory Control Room cache
  -> Advanced / Web Sessions
```

There is no new service, endpoint, database, registry, scheduler, polling daemon, background browser loop, telemetry cache, account store, lifecycle, retry plane, or provider router.

### 4.1 Pure projection owner

Create:

```text
control_plane/web_sol_fleet_projection.py
```

This module owns only:

- the closed C3 wire contract;
- strict recursive validation;
- deterministic aggregation and ordering;
- profile/tab/count/coverage equations;
- content-free navigation-match projection;
- payload-limit validation;
- fixed, non-secret failure vocabulary.

It performs no file, socket, subprocess, browser, clock, environment, network, provider, or credential I/O.

### 4.2 Gather owner

The existing `control_plane.chairman_control_room.build_control_room()` gather layer:

1. loads the existing binding document once;
2. derives unique profile adapter groups with the existing Web-Sol instance and conversation fingerprint functions;
3. performs at most one C2 call for each selected adapter;
4. passes a closed already-collected C3 document into the pure compositor.

`compose_control_room()` gains one optional already-collected input and remains clock/I/O free.

The Web-Sol integration imports needed only by the local gather occur inside the gather seam. The remote extracted release must continue to import and compose when Web-Sol integration modules are not shipped.

### 4.3 Existing cache and HTTP path

The existing server continues to expose the canonical document only through its cached `/api/state` envelope. C3 is collected whenever the existing Control Room owner performs a composition.

The first C3 vertical adds no C3-specific refresh endpoint and does not repurpose `/api/refresh-builds`. A page read may display the last cached observation while the existing single-flight owner refreshes the whole canonical document. The UI must show the C3 observation timestamp and the cache’s refresh/error state rather than calling a retained census “fresh.”

A future manual resample control, if still needed after real usability proof, must invoke the existing cache owner through a separately reviewed generic composition action. It may not add a C3 cache or independently poll adapters.

## 5. Adapter target derivation

The valid binding document is the only expected-profile input.

Include only bindings with:

```text
provider == chatgpt
locator_kind == chatgpt_managed_env
```

For each included binding:

- derive `adapter_instance_id` through the existing `web_sol_instance.adapter_instance_id(binding)`;
- derive `conversation_fingerprint` through the existing `web_sol_client.conversation_fingerprint(binding)`;
- retain only a local safe binding summary for projection;
- group by exact adapter instance;
- sort adapter groups by `adapter_instance_id`;
- sort a group’s bindings by lower-case `binding_id`.

The first sorted binding is the deterministic representative used to reach the profile-local socket. This is not a newest-tab, account, work, title, or ownership election: every binding in the group derives the same adapter coordinate by contract.

A valid empty binding document yields `EMPTY_IN_SCOPE`. A missing or malformed binding document yields `UNAVAILABLE`, never empty.

The C3 projection places independent display bounds on copied values: fingerprints and binding IDs have their existing fixed formats, enums remain closed, and timestamps retain the C2 format. No unbounded work/seat/free-form string is copied from the binding document.

## 6. Acquisition bounds and effect law

Constants:

```text
MAX_ADAPTERS = 4
MAX_ATTEMPTS_PER_ADAPTER = 1
C2_MAX_SECONDS_PER_ATTEMPT = 10
FLEET_ADMISSION_SECONDS = 40
MAX_NAVIGATION_MATCHES_PER_SESSION = 8
MAX_FLEET_JSON_BYTES = 524288
```

Rules:

1. Select at most the first four deterministic adapter groups.
2. Read them sequentially.
3. Never retry a C2 call, switch representative binding, switch socket/profile, or fail over to another host.
4. Before each call, require enough remaining fleet admission budget for one C2 attempt. If not, emit a `NOT_ATTEMPTED / FLEET_DEADLINE` profile row.
5. The 40-second value is an admission window: no later profile call may begin after it closes. A local syscall that outlives that deadline cannot be made safely cancellable by inventing a thread/process wrapper. If a call returns after the fleet deadline, preserve the actual elapsed duration, retain its dated observation only as partial evidence, admit no later call, and mark the fleet `PARTIAL`.
6. A C2 exception is reduced to a fixed code. No path, socket, URL, profile ID, account identity, exception text, or traceback is projected.
7. The gather performs no mutation. Its effect is always `NONE`.
8. Each whole Control Room composition replaces the prior process-memory C3 observation. No sticky history or independent correction store exists.

C3 does not raise the C2 61,440-byte payload target or 65,536-byte native frame guard.

## 7. Closed fleet contract

Top-level schema:

```json
{
  "schema": "mastermind.web_sol_fleet_projection.v1",
  "scope": "ENROLLED_CHATGPT_PROFILE_ADAPTERS",
  "coverage": "COMPLETE_IN_SCOPE",
  "probe_coverage": "COMPLETE_IN_SCOPE",
  "reason_codes": [],
  "started_at": "2026-09-08T00:00:00.000Z",
  "completed_at": "2026-09-08T00:00:00.100Z",
  "duration_ms": 100,
  "admission_window_ms": 40000,
  "expected_profile_count": 2,
  "attempted_profile_count": 2,
  "collected_profile_count": 2,
  "unavailable_profile_count": 0,
  "not_attempted_profile_count": 0,
  "omitted_profile_count": 0,
  "known_session_count": 4,
  "total_session_count": 4,
  "known_unique_conversation_count": 3,
  "duplicate_tab_count": 1,
  "observed_generation_cue_count": 1,
  "unknown_generation_cue_count": 0,
  "profiles": []
}
```

Closed fleet coverage:

```text
COMPLETE_IN_SCOPE
PARTIAL
UNAVAILABLE
EMPTY_IN_SCOPE
```

Closed fleet probe coverage:

```text
COMPLETE_IN_SCOPE
PARTIAL
NONE
UNAVAILABLE
```

Closed top-level reason codes:

```text
BINDINGS_UNAVAILABLE
BINDINGS_INVALID
ADAPTER_LIMIT
FLEET_DEADLINE
PROFILE_UNAVAILABLE
PROFILE_PARTIAL
PAYLOAD_LIMIT
```

The list is sorted, deduplicated, and contains no source text.

### 7.1 Pure input envelopes

The pure module accepts no binding locators and no raw C2 receipt. The gather translates already-validated owner values into two closed, content-free inputs.

Each `expected_profiles` row contains exactly:

```text
adapter_instance_id
binding_count
navigation_index
```

Each `navigation_index` row contains exactly:

```text
conversation_fingerprint
binding_id
```

The existing canonical `work[].bindings` and `unbound_surfaces` projections remain the one local source for work/role/seat labels. C3 does not duplicate those fields.

Each `observations` row contains exactly:

```text
adapter_instance_id
state
reason_code
receipt_status
attempt_started_at
attempt_completed_at
attempt_duration_ms
completed_within_fleet_deadline
c2_started_at
c2_completed_at
c2_duration_ms
inventory_coverage
consistency
c2_reason
probe_coverage
sessions
```

Each input `sessions` row contains the C3 session fields except the three derived navigation-match fields. All rows are closed and validated again by the C3 owner. The private representative binding used for the socket call never enters either pure input.

`binding_state` is exactly:

```text
AVAILABLE
MISSING
INVALID
```

### 7.2 Count law

`admission_window_ms` is exactly `40000`. Every duration is a non-negative integer no larger than JavaScript’s exact-integer ceiling. `duration_ms` records actual elapsed time and may exceed the admission window only when an already-started call returns late; that condition requires `FLEET_DEADLINE` and non-complete coverage.

`expected_profile_count` is `null` only when the binding input is unavailable or invalid.

`known_session_count` counts retained profile-scoped browser rows. It is not an Executive session or provider execution count.

`attempted_profile_count == collected_profile_count + unavailable_profile_count`.

`expected_profile_count == attempted_profile_count + not_attempted_profile_count + omitted_profile_count` whenever the expected set is known.

`total_session_count` is an integer only when:

- the binding input is valid;
- no adapter was omitted;
- every expected adapter was attempted exactly once;
- every attempt returned `COLLECTED`;
- every C2 snapshot has `inventory_coverage == COMPLETE_IN_SCOPE`;
- no fleet deadline or payload limit was crossed.

Otherwise it is `null`.

`known_unique_conversation_count`, `duplicate_tab_count`, and cue counts are sums of retained, validated profile rows. Identical conversation fingerprints in different adapters remain distinct profile-scoped observations.

`EMPTY_IN_SCOPE` requires a valid binding document and exactly zero eligible adapters. It requires exact zero counts and an empty profile list.

`UNAVAILABLE` means no usable fleet observation could be produced or the expected set is unknown. It never means zero sessions.

### 7.3 Fleet coverage law

`COMPLETE_IN_SCOPE` requires all total-count conditions above.

`PARTIAL` applies when at least one profile observation is retained but any expected profile, inventory boundary, deadline, or adapter-limit condition is incomplete. A selected profile skipped by the fleet deadline increments `not_attempted_profile_count`; an adapter beyond the four-profile selection cap increments `omitted_profile_count`.

`UNAVAILABLE` applies when expected coverage is unknown or no profile produced a retained `COLLECTED` snapshot.

If a candidate projection exceeds `MAX_FLEET_JSON_BYTES`, emit one minimal valid `UNAVAILABLE` envelope with `reason_codes=["PAYLOAD_LIMIT"]`, no profile/session rows, known-row counts zero, total counts null, and the actual fleet timing. The payload fallback carries no raw rejected value. A legal worst-case fixture must fit without using this fallback before source acceptance.

Fleet `probe_coverage` is independent of inventory coverage. Complete profile inventory with unknown probes is not complete probe coverage.

## 8. Closed profile row

```json
{
  "adapter_instance_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "binding_count": 2,
  "state": "COLLECTED",
  "reason_code": "NONE",
  "receipt_status": "COLLECTED",
  "attempt_started_at": "2026-09-08T00:00:00.000Z",
  "attempt_completed_at": "2026-09-08T00:00:00.060Z",
  "attempt_duration_ms": 60,
  "completed_within_fleet_deadline": true,
  "c2_started_at": "2026-09-08T00:00:00.005Z",
  "c2_completed_at": "2026-09-08T00:00:00.055Z",
  "c2_duration_ms": 50,
  "inventory_coverage": "COMPLETE_IN_SCOPE",
  "consistency": "STABLE_AT_BOUNDARIES",
  "c2_reason": "NONE",
  "probe_coverage": "COMPLETE_IN_SCOPE",
  "known_session_count": 2,
  "total_session_count": 2,
  "known_unique_conversation_count": 1,
  "duplicate_tab_count": 1,
  "observed_generation_cue_count": 1,
  "unknown_generation_cue_count": 0,
  "sessions": []
}
```

Closed profile states:

```text
COLLECTED
UNAVAILABLE
NOT_ATTEMPTED
```

Closed profile reason codes:

```text
NONE
FLEET_DEADLINE
CENSUS_UNAVAILABLE
INVALID_BINDING
COLLECTOR_UNAVAILABLE
READ_DEADLINE_EXCEEDED
RESULT_TOO_LARGE
INVALID_OBSERVATION
RECEIPT_INVALID
RECEIPT_IDENTITY_MISMATCH
FLEET_DEADLINE_OVERRUN
```

When `state != COLLECTED`, the attempt timestamps/duration remain explicit when an attempt occurred; C2 snapshot timestamps/coverage are `null`; counts are known-zero only for retained rows; `total_session_count` is `null`; and `sessions` is empty. A `NOT_ATTEMPTED` row has null attempt and C2 times.

## 9. Closed session row

Project only validated C2 fields. Preserve C2 snapshot order through its validated one-based `slot`; the slot is local to one profile observation and is never a durable tab identity.

```text
slot
conversation_fingerprint
identity_evidence
document_binding
status
generation_cue
selected_in_window
discarded
frozen
visibility
auth_required
provider_error_present
duplicate_count
duplicate_cue_disagreement
observed_at
selected_model
selected_effort
served_model
model_evidence
navigation_match_count
navigation_matches_omitted
navigation_matches
```

Each `navigation_matches` row contains exactly:

```text
binding_id
```

The local UI resolves that ID against the existing canonical binding summaries from the same Control Room generation before offering `/api/open`. It never accepts a C3-supplied URL, locator, work label, role, or seat label.

C3 never contains `locator`, URL, environment manager, folder/profile ID, account label, title, DOM, prompt, output, transcript, path, cookie, storage, credential, token, or arbitrary text.

Only exact `(adapter_instance_id, conversation_fingerprint)` equality creates a navigation match. At most eight sorted matches are projected per session. Exact match count and omitted count remain visible.

All model fields remain:

```text
selected_model = null
selected_effort = null
served_model = null
model_evidence = UNVERIFIED
```

until the separate #480 owner supplies accepted current product evidence and a new reviewed schema generation.

## 10. Control Room composition

`compose_control_room()` additively accepts:

```python
web_sol_fleet: Mapping[str, Any] | None = None
```

When the pure projection module is present:

- validate and deep-copy a supplied fleet document;
- `None` means the optional local source was not projected and is carried silently as `null`;
- invalid supplied input becomes `web_sol_fleet = null` plus fixed `web_sol_fleet: invalid` degradation;
- no untrusted exception text is copied.

When the optional projection module is absent:

- retain the top-level key as `null`;
- add no fleet-specific global degradation merely because an extracted/local release omitted the optional capability;
- continue composing every existing section.

The local `build_control_room()` path supplies an explicit `UNAVAILABLE` C3 document for missing or invalid bindings, so a real local source failure is never hidden by the silent optional `None` behavior.

Add `web_sol_fleet` to the closed `OUTPUT_KEYS`. No other output key or existing section changes.

The preliminary autonomy composition and final composition receive the same already-collected C3 value. C3 is gathered once per Control Room generation, never once per compose call.

## 11. Remote X1 boundary

The remote projection:

- validates that the canonical document has the new closed top-level key;
- accepts only `null` or a mapping at that local-only branch;
- recursively runs the existing sensitive-value refusal over a supplied mapping;
- relies on the canonical compositor—not a duplicated remote validator—for full C3 schema validity;
- omits `web_sol_fleet` entirely from `mastermind.chairman_control_room_remote.v1`;
- ships no Web-Sol client, native, binding locator, profile, or C3 projection dependency merely to display remote state.

The remote required runtime file allowlist remains unchanged. The optional local module stays out of X1.

## 12. Advanced Web Sessions experience

Add one System/Advanced card after source clocks and before provider capability:

```text
Browser observation
Web Sessions
```

Summary copy must distinguish:

- expected, attempted, collected, unavailable, and omitted profiles;
- known session rows versus unknown total;
- inventory coverage versus probe coverage;
- observation timestamp;
- cache refresh in flight or last refresh failure.

Examples:

```text
Complete in scope · 2 of 2 profiles observed · 4 browser rows
Partial · 2 profiles observed · 1 unavailable · total browser rows unknown
Unavailable · enrolled-profile observation could not be established
Empty in scope · no enrolled ChatGPT profile adapter is recorded
```

Never render:

```text
worker running
profile idle
capacity available
account online
all company sessions
Sol Pro
actual served model
```

Profile cards render fixed state/cue labels and safe counts. Session rows may expose exact existing binding actions through the current `/api/open` path. One row with multiple exact matches displays each bounded match; it never elects newest/title/seat.

No C3 content enters Today, Programs, Ask Sol, Autonomy, Work focus/ranking, source validity, or decision admission.

## 13. Truth, failure, and correction behavior

- Missing is not empty.
- Partial zero is not clear.
- An unavailable profile remains visible.
- Frozen, discarded, loading, navigating, malformed, timed-out, and target-changed rows remain unknown—not idle.
- A generation cue is a page cue, not server execution.
- Browser `active`/`selected_in_window` is window selection, not work ownership.
- A binding is a navigation address, not lifecycle or cognition.
- A successful C2 read is not installed-fleet acceptance.
- A new Control Room composition replaces the prior process-memory observation. It does not rewrite GitHub evidence or append provider history.
- A source/browser/package/profile epoch change invalidates only the named evidence epoch.
- No uncertain read is retried for cleaner output.

## 14. Source START gates

C3 implementation may START only after one fresh turn proves:

1. issue #501 proof-maintenance source has fixed the cross-process proof-artifact race and its source custody is settled;
2. PR #537’s fixed-repository-boundary blocker is repaired, independently reviewed, current-base proven, protected, and writer-released;
3. PR #531 is independently reviewed, current-base proven, protected, and writer-released;
4. protected master still contains accepted C2 source and compatible Skillpack;
5. issue #359 and PF-1/#338 have released the exact disposable resources needed by #340;
6. issue #340 has completed exact two-profile installation/fault/rollback proof for the intended C2 generation;
7. every intended C3 path is unowned across open PRs, branches, registered worktrees, processes, and source writers;
8. one exact implementation branch/PR and one concrete eligible writer are bound;
9. remote X1 and Decision-First Today boundaries are freshly reread;
10. no prior C3 source or provider effect is unknown.

A missing gate returns `DEPENDENCY_HELD / effect=NONE`. No source branch or worker START is inferred from this record.

## 15. Completion standard

A source PR is complete only when one independently useful local vertical exists:

```text
two or more enrolled profile adapters
-> real C2 reads
-> one canonical cached Control Room generation
-> Advanced Web Sessions
-> complete/partial/unavailable rendering
-> exact binding navigation
-> remote omission
```

Source merge remains `BUILT_NOT_PROVEN`.

Production acceptance additionally requires:

- exact installed C2 generation and two-profile proof from #340;
- a real local Control Room read showing both profiles;
- one forced unavailable-profile case;
- one duplicate-tab case;
- one correction on the next whole composition;
- desktop/tablet/mobile browser proof;
- zero private-data leakage;
- no Today/remote regression;
- independent evidence review;
- complete rollback or retained-install disposition by the installation owner.

## 16. Rejected approaches

- second fleet/session registry;
- persistence in `surface_bindings`;
- background polling daemon;
- C3-specific telemetry cache;
- new browser or native transport;
- direct provider/network interception;
- host CPU or provider quota inference;
- model/effort heuristics;
- newest/title/recency target election;
- parallel first-release reads;
- retry/failover after unavailable or ambiguous effects;
- remote X1 profile projection;
- a foundation-only schema PR without a real Advanced consumer.
