---
schema: mastermind.web_sol_fleet_c3_architecture.v1
operation_key: web-sol-fleet-c3-design-plan-source-20260908-sol-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_issue: 501
chairman_approval_comment: 5592792563
protected_source: e18cab4f3ca41725fdb517623543fa4fb1aba467
protected_tree: 74c3af1fc2805eb0fdc7d8651c722fd5db40e3b8
self_review_parent: b45f042040157c03fc97c5d6ad27acaa4c5b93e4
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
**Status:** `CHAIRMAN_APPROVED / SELF_REVIEW_REPAIRED / SPEC_ONLY / IMPLEMENTATION_PRE_START / PRODUCTION_INERT`

This record freezes the Chairman-approved C3 architecture. It changes no browser, profile, account, extension, native host, socket, RuntimeBinding, Executive lifecycle, Control Room route, cache, service, provider state, installation, deployment, or production capability.

The approved C3 constants narrowly supersede only the earlier C3 scale proposal in the protected C2 design: use at most **four** enrolled profile adapters, deterministic **sequential** reads, and one **40-second fleet admission window**. All still-valid C2 identity, privacy, transport, no-retry, uncertainty, package, installation, and authority laws remain unchanged.

The self-review repair closes four implementation ambiguities without changing that approved direction: exact C2 receipt/null mapping, duplicate binding-ID refusal, finite pure-input bounds, and a six-match display cap whose legal four-profile worst case must fit the 512 KiB C3 payload ceiling. Oversized or internally invalid projections never fabricate a fallback fleet document; the existing Control Room degradation path carries the fixed failure instead.

## 1. Executive ruling and user journey

C3 is the first useful multi-profile consumer of the protected C2 profile-local census.

The Chairman opens the existing local Control Room, enters **Advanced → Web Sessions**, and sees:

- which enrolled ChatGPT profile adapters were expected;
- which selected adapters were attempted, collected, unavailable, or not attempted before the fleet deadline;
- how many additional adapters were omitted by the four-profile cap;
- every retained browser-observation row, including duplicate tabs and unknown states;
- exact navigation matches to existing surface bindings;
- observation time, cache state, inventory coverage, and probe coverage;
- explicit `UNKNOWN / UNVERIFIED` model and effort evidence.

C3 is browser observation, not company execution. It never converts a visible tab, stop-button cue, selected window, profile process, native response, or binding into a Worker, Job, START, capacity claim, source owner, or provider-compute assertion.

Decision-First **Today** remains the Chairman default. C3 appears only in Advanced. It cannot change Chairman attention, decision admission, Sol accountability, priority, work focus, autonomy actionability, or the Today headline.

## 2. Current estate and prerequisites

Protected source already contains:

- the transient profile-local census popup and collector;
- complete extension-bundle rendering;
- C2 compact request/receipt/table validation;
- C2 native-host, extension-worker, client, and CLI transport;
- the existing `mastermind.surface_bindings.v1` navigation owner;
- the pure/local Chairman Control Room compositor, cache, local UI, and separate remote X1 projection.

C2 source is protected through PR #542 / merge `fc29e14a0d9ee41105264a5abc1d182daee7abbf`, but it is not installed or production-proven. Issue #340 remains the sole exact-generation two-profile install/fault/rollback owner. Issue #359 owns the missing second disposable profile and non-sensitive account-realm prerequisite. Issue #338 owns provider continuation/effect falsification. Issue #480 owns visible model/effort evidence.

C3 source START remains held until the exact gates in section 15 are true. This record does not assign a worker.

## 3. Canonical ownership and no-rebuild boundary

| Fact or effect | Canonical owner | C3 treatment |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle | Executive OS | not inferred or modified |
| organizational responsibility, decisions, discoveries, handoffs | Agent OS | not inferred or modified |
| exact logical target / provider generation | RuntimeBinding / SessionTarget owners | not replaced |
| browser navigation coordinate | `mastermind.surface_bindings.v1` | one loaded read-only input and exact navigation match |
| one profile census | protected C2 Web-Sol owner | validated input |
| provider quota/headroom | Macro Provider Control | not inferred |
| host CPU/memory/resource admission | Capacity / Workbench host-facts owners | not inferred |
| Control Room composition/cache | existing local Control Room owner | extended, not duplicated |
| remote X1 redaction/release | existing remote projection owner | C3 omitted and type-checked |
| source, review, CI, release evidence | GitHub | exact records |
| transport/hot collaboration | Slack | evidence only |

Deleting C3 changes only this optional Advanced observation. It cannot change any canonical organizational or runtime fact.

Hard prohibitions:

- no second fleet/session registry;
- no persistence in `surface_bindings`;
- no C3 database, cache, timer, scheduler, daemon, queue, retry ledger, or event stream;
- no new HTTP route or browser/native transport;
- no account/profile discovery owner;
- no model, quota, capacity, worker, lifecycle, admission, or completion inference;
- no newest/title/recency/seat election;
- no remote X1 profile projection;
- no blind retry or profile/socket/host failover.

## 4. Architecture

```text
one loaded valid surface-bindings document
  -> deterministic unique adapter groups
  -> at most four sequential C2 calls
  -> closed content-free expected/observation inputs
  -> pure mastermind.web_sol_fleet_projection.v1
  -> existing mastermind.chairman_control_room.v1
  -> existing process-memory Control Room cache
  -> Advanced / Web Sessions
```

### 4.1 Pure projection owner

Create:

```text
control_plane/web_sol_fleet_projection.py
```

It owns only:

- the closed C3 wire contract;
- strict recursive validation;
- deterministic aggregation and ordering;
- profile/tab/count/coverage equations;
- content-free navigation-match projection;
- input and output bounds;
- fixed, non-secret failure vocabulary.

It performs no file, socket, subprocess, browser, clock, environment, network, provider, credential, or model I/O.

### 4.2 Gather owner

The existing `control_plane.chairman_control_room.build_control_room()` gather layer:

1. loads the existing binding document once;
2. derives unique profile adapter groups with the existing Web-Sol instance and conversation-fingerprint functions;
3. performs at most one C2 call for each selected adapter;
4. reduces every known C2/client outcome to a closed observation row;
5. passes one already-collected C3 value into the pure compositor.

`compose_control_room()` gains one optional already-collected input and remains clock/I/O free.

The Web-Sol integration imports needed only by the local gather occur inside the gather seam. The remote extracted release must continue to import and compose when Web-Sol integration modules are not shipped.

### 4.3 Existing cache and HTTP path

The existing server continues to expose the canonical document only through its cached `/api/state` envelope. C3 is collected whenever the existing Control Room owner performs a whole composition.

The first C3 vertical adds no C3-specific refresh endpoint and does not repurpose `/api/refresh-builds`. A page read may display the last cached observation while the existing single-flight owner refreshes the whole canonical document. The UI shows the C3 observation timestamp and the cache’s refresh/error state rather than calling retained evidence fresh.

A future manual resample control, if still needed after real usability proof, must invoke the existing cache owner through a separately reviewed generic composition action. It may not add a C3 cache or independently poll adapters.

## 5. Adapter target derivation and binding safety

The loaded binding document is the only expected-profile source.

Include only bindings with:

```text
provider == chatgpt
locator_kind == chatgpt_managed_env
```

For each included binding:

- derive `adapter_instance_id` through the existing `web_sol_instance.adapter_instance_id(binding)`;
- derive `conversation_fingerprint` through the existing `web_sol_client.conversation_fingerprint(binding)`;
- preserve the exact source spelling of `binding_id` for later local lookup;
- group by exact adapter instance;
- sort adapter groups by `adapter_instance_id`;
- sort group bindings by `(binding_id.lower(), binding_id)`.

The first sorted binding is the deterministic representative used only to reach that profile-local socket. This is not a newest-tab, account, work, title, seat, or ownership election: every binding in the group derives the same adapter coordinate by contract.

A binding document that passes the existing owner validator may still contain duplicate IDs because that owner does not use `binding_id` as canonical company identity. C3 requires exact local navigation resolution, so duplicate `binding_id.lower()` values anywhere in the eligible C3 input make the C3 binding state `INVALID`; no C2 call occurs. C3 never lets the server’s first-match lookup silently choose between duplicate addresses.

The output preserves the exact original binding-ID spelling. The UI offers an Open control only after resolving exactly one canonical binding summary from the same Control Room generation. Zero or multiple matches suppress the control.

A valid empty document, or a valid document with no eligible ChatGPT binding, yields `EMPTY_IN_SCOPE`. A missing document yields `UNAVAILABLE / BINDINGS_UNAVAILABLE`. A malformed document, duplicate case-folded binding ID, invalid derived identity, or input-bound overflow yields `UNAVAILABLE / BINDINGS_INVALID`.

A returned document accompanied only by the existing owner’s permission warning remains structurally available; that warning continues through the existing `surface_bindings:` degraded channel. C3 does not invent a second permission policy.

## 6. Bounds, request construction, time, and effect law

Frozen constants:

```text
MAX_ADAPTERS = 4
MAX_ATTEMPTS_PER_ADAPTER = 1
C2_MAX_SECONDS_PER_ATTEMPT = 10
FLEET_ADMISSION_SECONDS = 40
MAX_EXPECTED_PROFILES = 8192
MAX_NAVIGATION_INDEX_ROWS = 8192 total
MAX_NAVIGATION_MATCHES_PER_SESSION = 6
MAX_SESSIONS_PER_PROFILE = 128
MAX_FLEET_JSON_BYTES = 524288
```

The 8,192-row pure-input ceiling is above the physical bound of the existing 1 MiB binding file while preventing an unbounded caller-provided list. `binding_count` equals the exact navigation-index length for that adapter, and the sum of all navigation-index lengths is at most 8,192.

Acquisition rules:

1. Select the first `min(expected_profile_count, 4)` deterministic adapter groups. Remaining adapters are counted as omitted and are not called or represented by profile rows.
2. Read selected adapters sequentially. A later call cannot begin before the prior call returns.
3. Before each call, require at least the protected C2 owner’s full `TOTAL_SECONDS` remaining in the fleet admission window.
4. Create one unique operation key and nonce per attempted adapter. Build `issued_at` from an aware UTC sample and `expires_at = issued_at + C2 TOTAL_SECONDS`; validate through the existing C2 request owner before transport.
5. Never retry, switch representative binding, switch socket/profile, or fail over to another host.
6. The 40-second value is an admission window. No later profile call may begin once it closes.
7. A call that began lawfully but returns at or after the fleet deadline preserves the actual monotonic duration and any validated dated C2 result, sets `completed_within_fleet_deadline=false`, admits no later call, and makes fleet coverage non-complete.
8. Monotonic durations use non-negative finite samples and integer milliseconds. Invalid/regressing wall or monotonic time cannot be laundered into a fleet document; the local Control Room emits `web_sol_fleet=null` with fixed `web_sol_fleet: unavailable` degradation.
9. A C2/client exception is mapped to a fixed code. No path, socket, URL, profile ID, account identity, operation key, nonce, exception text, or traceback is projected.
10. The gather performs no mutation. Its effect is always `NONE`.
11. Each whole Control Room composition replaces the prior process-memory C3 observation. No sticky history or independent correction store exists.

C3 does not raise the C2 61,440-byte payload target or 65,536-byte native frame guard.

## 7. Closed pure inputs

The pure module accepts no raw binding locator, representative binding, C2 receipt, operation key, nonce, or exception.

Public API:

```python
validate_fleet_projection(value: object) -> dict
compose_fleet_projection(
    *,
    expected_profiles: list[dict],
    observations: list[dict],
    started_at: str,
    completed_at: str,
    duration_ms: int,
    binding_state: str,
) -> dict
```

`binding_state` is exactly:

```text
AVAILABLE
MISSING
INVALID
```

For `MISSING` or `INVALID`, both input lists are empty.

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

Rules:

- adapter and conversation fingerprints are lower-case 64-hex;
- binding IDs have the existing UUID shape and preserve source spelling;
- adapter IDs are unique;
- case-folded binding IDs are unique across the whole input;
- `binding_count == len(navigation_index) > 0`;
- expected rows and navigation rows are accepted in any order but canonicalized deterministically;
- total expected rows and total navigation rows respect section 6 bounds.

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

Each input `sessions` row contains exactly the C2 `ROW_FIELDS`; the pure C3 owner derives navigation-match fields and all counts. Observations may exist only for the selected first four expected adapters, exactly once each.

## 8. Closed fleet output and equations

Top-level key set:

```text
schema
scope
coverage
probe_coverage
reason_codes
started_at
completed_at
duration_ms
admission_window_ms
expected_profile_count
attempted_profile_count
collected_profile_count
unavailable_profile_count
not_attempted_profile_count
omitted_profile_count
known_session_count
total_session_count
known_unique_conversation_count
duplicate_tab_count
observed_generation_cue_count
unknown_generation_cue_count
profiles
```

Fixed values:

```text
schema = mastermind.web_sol_fleet_projection.v1
scope = ENROLLED_CHATGPT_PROFILE_ADAPTERS
admission_window_ms = 40000
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
```

The reason list equals the exact derived set, sorted and deduplicated. It contains no caller/source text.

### 8.1 Cardinality

For `AVAILABLE` bindings:

```text
expected_profile_count = len(expected_profiles)
selected_profile_count = min(expected_profile_count, 4)
len(profiles) = selected_profile_count
attempted_profile_count + not_attempted_profile_count = selected_profile_count
collected_profile_count + unavailable_profile_count = attempted_profile_count
expected_profile_count = selected_profile_count + omitted_profile_count
```

For `MISSING` or `INVALID` bindings:

```text
expected_profile_count = null
all other profile counts = 0
profiles = []
total_session_count = null
```

A profile with `state=NOT_ATTEMPTED` is selected but not attempted. An adapter after the selection cap is omitted and has no profile row.

`known_session_count` is the sum of retained session rows. It is not an Executive session or provider-execution count.

`total_session_count` is an integer only when fleet coverage is `COMPLETE_IN_SCOPE`; otherwise it is `null`.

`known_unique_conversation_count`, `duplicate_tab_count`, and cue counts are derived independently inside each adapter and then summed. The same conversation fingerprint in two adapters remains two profile-scoped observations.

### 8.2 Coverage

`EMPTY_IN_SCOPE` requires available bindings, exactly zero expected adapters, exact zero counts, empty profiles, `probe_coverage=NONE`, and no reason codes.

`COMPLETE_IN_SCOPE` requires:

- available bindings;
- no omitted or not-attempted adapter;
- every expected adapter attempted exactly once;
- every attempt has `state=COLLECTED` and `completed_within_fleet_deadline=true`;
- every C2 snapshot has `inventory_coverage=COMPLETE_IN_SCOPE`;
- no top-level reason code.

`PARTIAL` requires at least one collected profile and any non-complete condition, including omitted, not attempted, unavailable, late, or partial inventory.

`UNAVAILABLE` applies when expected coverage is unknown or no profile produced a collected C2 snapshot. It never means zero sessions.

Top-level reasons derive exactly:

- missing bindings -> `BINDINGS_UNAVAILABLE`;
- malformed/ambiguous/over-bound bindings -> `BINDINGS_INVALID`;
- omitted adapter count > 0 -> `ADAPTER_LIMIT`;
- a selected adapter is not attempted or an attempted result completes outside the fleet window -> `FLEET_DEADLINE`;
- unavailable profile count > 0 -> `PROFILE_UNAVAILABLE`;
- any collected profile has non-complete inventory or probe coverage -> `PROFILE_PARTIAL`.

### 8.3 Probe coverage

Probe coverage is independent of inventory coverage and is derived from retained session status:

- fleet `EMPTY_IN_SCOPE` -> `NONE`;
- fleet with no collected profile -> `UNAVAILABLE`;
- known sessions == 0 -> `NONE`;
- fleet complete and every known session has `status=OBSERVED` -> `COMPLETE_IN_SCOPE`;
- at least one but not all known sessions has `status=OBSERVED` -> `PARTIAL`;
- known sessions exist and none has `status=OBSERVED` -> `NONE`.

A complete profile inventory with unobserved probes does not become complete probe coverage.

## 9. Closed profile contract

Profile key set:

```text
adapter_instance_id
binding_count
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
known_session_count
total_session_count
known_unique_conversation_count
duplicate_tab_count
observed_generation_cue_count
unknown_generation_cue_count
sessions
```

Closed profile states:

```text
COLLECTED
UNAVAILABLE
NOT_ATTEMPTED
```

Closed `receipt_status` values are exactly the protected C2 `STATUSES`:

```text
COLLECTED
COLLECTOR_UNAVAILABLE
READ_DEADLINE_EXCEEDED
RESULT_TOO_LARGE
INVALID_OBSERVATION
```

It may be `null` only when no valid C2 receipt was accepted.

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

Exact state law:

- `COLLECTED`: accepted C2 receipt status is `COLLECTED`; C2 snapshot fields and sessions are present. Reason is `NONE` when completed inside the fleet window, otherwise `FLEET_DEADLINE_OVERRUN`.
- `UNAVAILABLE`: the C3 profile attempt occurred but no collected snapshot exists. A valid non-collected C2 receipt preserves its exact status and maps the same value into `reason_code`. Invalid binding/preparation maps `INVALID_BINDING`; C2 validation failure maps `RECEIPT_INVALID`; identity mismatch maps `RECEIPT_IDENTITY_MISMATCH`; every other fixed client/transport/unknown failure maps `CENSUS_UNAVAILABLE`. A valid receipt returning outside the fleet window instead uses `FLEET_DEADLINE_OVERRUN` while `receipt_status` retains its exact owner value.
- `NOT_ATTEMPTED`: reason is `FLEET_DEADLINE`; receipt status is null.

Attempt fields:

- `COLLECTED` and `UNAVAILABLE` require non-null UTC attempt start/completion, non-negative integer monotonic duration, and Boolean `completed_within_fleet_deadline`;
- `NOT_ATTEMPTED` requires those four fields null;
- completion cannot precede start;
- `completed_within_fleet_deadline` is true only when the monotonic completion is strictly before the fleet deadline.

C2 snapshot fields:

- `COLLECTED` requires non-null validated C2 start/completion/duration, inventory coverage, consistency, C2 reason, and probe coverage;
- other states require all of them null;
- C2 enums and timestamp/count relationships remain exactly those validated by the protected C2 owner.

Counts:

- `COLLECTED` derives every known count from `sessions` and sets profile `total_session_count` only when its C2 inventory is complete;
- other states have exact known-row counts of zero, `total_session_count=null`, and `sessions=[]`;
- `binding_count` equals the matching expected-profile row and is always positive.

## 10. Closed session and navigation contract

Session key set:

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

Preserve C2 snapshot order through validated one-based `slot`; the slot is local to one profile observation and is never durable tab identity.

Each navigation match contains exactly:

```text
binding_id
```

Only exact `(adapter_instance_id, conversation_fingerprint)` equality creates a match. A null conversation fingerprint produces zero matches. Matches sort by `(binding_id.lower(), binding_id)`. `navigation_match_count` is the exact total, `navigation_matches` contains the first at most six, and `navigation_matches_omitted` equals the difference.

C3 never contains locator, URL, environment manager, folder/profile ID, account label, title, DOM, prompt, output, transcript, path, cookie, storage, credential, token, operation identity, or arbitrary text.

All model fields remain:

```text
selected_model = null
selected_effort = null
served_model = null
model_evidence = UNVERIFIED
```

until the separate #480 owner supplies accepted current product evidence and a new reviewed schema generation.

## 11. Payload and validation boundary

A canonical compact-JSON C3 document must be at most `524288` UTF-8 bytes. The legal worst-case test uses four collected 128-row profiles, the longest legal closed values, 8,192 exact source bindings, and six displayed navigation matches on every session. It must pass below the ceiling.

A seven-match-per-session mutant is required to fail the frozen limit or its exact cap assertion. Implementers may not raise the payload ceiling, drop session rows, silently truncate profiles, compress through an alternate schema, or weaken C2 limits.

`validate_fleet_projection` rejects oversized or malformed values. `compose_fleet_projection` must produce either a legal bounded document or raise its fixed validation exception. It does **not** emit a synthetic payload fallback whose counts can no longer be derived from visible rows.

An unexpected local gather/projection failure is caught by the existing Control Room gather boundary: the canonical document carries `web_sol_fleet=null` and fixed `web_sol_fleet: unavailable` degradation. Invalid caller-supplied fleet data at the pure compositor boundary carries `web_sol_fleet=null` and fixed `web_sol_fleet: invalid`. No raw exception or rejected value is exposed.

## 12. Control Room composition

`compose_control_room()` additively accepts:

```python
web_sol_fleet: Mapping[str, Any] | None = None
```

When the optional pure projection module is present:

- validate and deep-copy a supplied fleet document;
- `None` means the optional local source was not supplied and is carried silently as null;
- invalid supplied input becomes null plus fixed invalid degradation;
- no untrusted exception text is copied.

When the optional module is absent:

- retain the top-level key as null;
- add no fleet-specific global degradation merely because an extracted release omitted the optional local capability;
- continue composing every existing section.

The local `build_control_room()` path supplies an explicit `UNAVAILABLE` C3 document for missing or invalid bindings. Unexpected gather failure uses the fixed unavailable degradation in section 11.

Add `web_sol_fleet` to closed `OUTPUT_KEYS`. No other output key or existing section changes. Preliminary autonomy composition and final composition receive the same already-collected value. C3 is gathered once per cache generation, never once per compose call.

## 13. Remote X1 boundary

The remote projection:

- validates that the canonical document has the new closed top-level key;
- accepts only null or a mapping at that local-only branch;
- recursively runs the existing sensitive-value refusal over a supplied mapping;
- relies on the canonical compositor—not a duplicated remote C3 validator—for full local schema validity;
- omits `web_sol_fleet` entirely from `mastermind.chairman_control_room_remote.v1`;
- ships no Web-Sol client, native, binding locator, profile, or C3 projection dependency merely to discard the data.

The remote required runtime file allowlist remains unchanged. The optional local module stays out of X1.

## 14. Advanced Web Sessions experience

Add one System/Advanced card after source clocks and before provider capability:

```text
Browser observation
Web Sessions
```

Summary copy distinguishes:

- expected, selected, attempted, collected, unavailable, not-attempted, and omitted profiles;
- known session rows versus unknown total;
- inventory coverage versus probe coverage;
- observation timestamp;
- cache refresh in flight or last refresh failure;
- details withheld by null/invalid/unavailable state.

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

The UI displays only a short opaque adapter prefix, never a profile label inferred from bindings. Session rows expose Open controls only by resolving each C3 binding ID to exactly one canonical binding object from the same loaded document and then reusing the current `openBinding()` path. It never builds a URL from C3 data and never elects among multiple matches.

No C3 content enters Today, Programs, Ask Sol, Autonomy, Work focus/ranking, source validity, or decision admission.

## 15. Source START gates

C3 implementation may START only after one fresh turn proves:

1. this exact C3 architecture/plan carrier has independent non-author acceptance, current-base repository/security proof, protected merge, and source-writer release;
2. issue #501 proof-maintenance source has fixed the cross-process proof-artifact race and its source custody is settled;
3. PR #537’s fixed-repository-boundary blocker is repaired, independently reviewed, current-base proven, protected, and writer-released;
4. PR #531 is independently reviewed, current-base proven, protected, and writer-released;
5. protected master still contains accepted C2 source and a compatible same-SHA Skillpack;
6. issue #359 and PF-1/#338 have released the exact disposable resources needed by #340;
7. issue #340 has completed exact two-profile installation/fault/rollback proof for the intended C2 generation;
8. every intended C3 path is unowned across open PRs, branches, registered worktrees, processes, and source writers;
9. one exact implementation branch/PR and one concrete eligible writer are bound;
10. remote X1 and Decision-First Today boundaries are freshly reread;
11. no prior C3 source, profile, provider, or transport effect is unknown.

A missing gate returns `DEPENDENCY_HELD / effect=NONE`. No implementation branch or worker START is inferred from this record.

## 16. Completion and proof

A source PR is independently useful only when this local vertical exists:

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

Green CI, a source merge, a C2 receipt, or a visible card alone is not production acceptance.
