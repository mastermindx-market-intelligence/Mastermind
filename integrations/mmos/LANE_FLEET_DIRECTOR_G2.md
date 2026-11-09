# Lane ledger — Director G2: T3 attempt-fleet read route (`t3/fleet-attempt-read-route`)

Mission: DONE_WHEN 3 — the per-attempt fleet observation (Director G's
`mastermind.t3_attempt_fleet/v1` projection) is **visible from Mastermind OS**
through the Workspace read path: backend read route + OS fail-closed parser +
per-attempt details block in the Fleet & Capacity route, with pin moves and
tests. Base `70dabba15` (`t3/t3-hermes-restart-recovery`); no push, no PR, no
other worktree touched. Read-only effects only: per request one `mode=ro`
sqlite open of the adapter state and one bounded `ps` census; nothing was
launched, interrupted or sent to any T3 thread.

Standing decision kept: the read rides the **Workspace read route**
(fabric-read parity), NOT a Hermes native bridge (proposal §5 is absent from
this checkout).

## Deliverables

| file | what |
| --- | --- |
| `common/workspace_t3_attempt_fleet_contract.py` | wire contract: frame schema `mastermind.workspace_t3_attempt_fleet_read.v1`, document schema `mastermind.t3_attempt_fleet/v1`, closed refusal vocabularies (17 evidence + 2 read refusals), 16_384-byte response bound, attempt-id grammar, `validate_frame`/`validate_document`/`refusal_document` |
| `control_plane/workspace_t3_attempt_fleet_read.py` | pure composition source: `attempt_id → read_adapter_attempt_rows(mode=ro) + take_census() + project_attempt()`, `T3AttemptFleetError → typed refusal document`; `handle_t3_attempt_fleet_frame` mirrors `handle_capacity_fabric_frame` (authorize → permission stamp → `asyncio.to_thread` → await owned → recheck → SOURCE_CHANGED → validate); `default_source()` helper for production install |
| `integrations/mastermind_workspace_app/app.py` | route + `_RawPathFence` admission for `GET /workspace/resources/t3/attempts/current` |
| `integrations/mastermind_workspace_app/t3_attempt_fleet.py` | endpoint: authenticate → reject body → strict query decode (`attempt_id` required) → frame → control-room permission stamps → client → recheck + principal expiry → 200 always for v1 documents (honest unknown AND typed refusal), 4xx/403 for malformed/unauthorized |
| `integrations/executive_mcp/server.py` | route added to `_WORKSPACE_ADDITIONAL_QUERY_GET_ROUTES` (same auth/expiry semantics as the fabric route) |
| `integrations/mastermind_workspace_app/installed.py` | `CeoIngressWorkspaceClient.request` admitted-schema elif + per-schema ceiling (socket frame path) |
| `control_plane/executive_service.py` | CEO-ingress admitted schema set member + elif validate/ceiling (service frame path) |
| `control_plane/workspace_read_service.py` | provider param `t3_attempt_fleet_source` (exact-type guard, like the fabric source) + frame dispatch |
| `app/mastermind_os/src/resources/t3-attempt-fleet-contract.ts` | fail-closed TS parser mirroring the Python contract: exact key sets, closed vocabularies, 4 cross-field invariants, byte bound, detach |
| `app/mastermind_os/src/resources/T3AttemptFleetBlock.tsx` (+ css) | per-attempt "T3 attempt fleet" block next to the run inspector: two invariant chips PROVEN/VIOLATED/UNKNOWN(+reason), harness pid/provider/model/start_time when observed, duplicate kinds when observed, freshness/notes/evidence details; en + zh-CN; no-source/signed-out → unknown-with-reason, never healthy, never zero |
| `app/mastermind_os/src/host.ts` | guarded `readT3AttemptFleet` MissionHost method (epoch/auth verify before+after); NO native invoke-table entry (src-tauri is integrator-owned) |
| `app/mastermind_os/src/web-auth.ts` | HTTP reader: `read("acquisition", …?attempt_id=…, {cap: 16_384, typedUnavailableSchema: null})` — refusals arrive as 200 documents, not 503 |
| `app/mastermind_os/src/fabric/AttendedFabricWorkspace.tsx` | mounts the block with the catalog-selected run id |
| `integrations/mmos/fixtures/t3_attempt_fleet_v1/{attempt,refusal}.json` | produced by the Python `to_dict()`; Python route test and TS vitest both assert equality against these exact bytes |
| `tests/test_workspace_t3_attempt_fleet_read.py` | composition + frame-handler + route suite (85 tests) |

## Router decision (query param, not path segment)

Run ids contain `/`. The incumbent router supports **fixed literal paths only**:
`_RawPathFence` rejects any `%` in `raw_path`, so a URL-encoded attempt id can
never appear as a path segment; and ASGI `raw_path` excludes the query string.
The router-supported shape is therefore a fixed route with a required query
parameter: **`GET /workspace/resources/t3/attempts/current?attempt_id=<run id>`**,
decoded once by the existing strict `_decode_v2_query` (foreign/duplicate/missing
keys → 400). The `/current` suffix follows the incumbent naming convention.

## Four-layer frame admission (all four were required, all four done)

The production OS web path is web-auth → HTTP route → `CeoIngressWorkspaceClient`
(installed.py) → CEO ingress socket → `ExecutiveControlService` ingress
(executive_service.py) → provider factory → `WorkspaceReadService`. Each layer
has its own admitted-frame-schema gate; the frame is now admitted in:

1. `app.py` — route row + fence `_READ_ROUTES`;
2. `integrations/executive_mcp/server.py` — query-GET route tuple;
3. `installed.py` — socket client elif + ceiling;
4. `executive_service.py` — ingress admitted set + elif.

Each gate rejects unknown schemas fail-closed (verified: before (3)/(4) the
bridge tests answered 503 `source_unavailable`, never a partial projection).

## Evidence ladder

| claim | grade | evidence |
| --- | --- | --- |
| Route serves the exact fixture document through the real workspace app test client | **PROVEN_BY_TEST** | `test_route_serves_the_canonical_fixture_document` (params form AND raw-slash `runs/att-1` form; byte-equality vs `fixtures/t3_attempt_fleet_v1/attempt.json`) |
| Fixture parity across both languages | **PROVEN_BY_TEST** | Python route test and TS `t3-attempt-fleet-contract.test.ts` both load the same two fixture files; TS asserts exact mirrored fields, refusal fixture equals `{kind: refusal, ADAPTER_STATE_SCHEMA_UNKNOWN}` |
| Unknown attempt → honest unknown, notes explain | **PROVEN_BY_TEST** | unrecorded id in a non-empty store → 200, `NO_ADAPTER_ROW`, both invariants UNKNOWN; empty whole store → `ADAPTER_STATE_EMPTY` |
| Corrupt/foreign evidence → typed refusal, never 500 | **PROVEN_BY_TEST** | corrupt row → 200 refusal document, equality vs `refusal.json`; every projection refusal code proven wire-legal (`test_every_projection_refusal_code_is_wire_legal` scans `project_attempt` source) |
| Bad request surface → 4xx typed | **PROVEN_BY_TEST** | 9-case rejection matrix (missing/foreign/duplicate query keys, bad id, missing auth, foreign scope, body, POST, encoded route) all 4xx, provider factory never called |
| Auth/expiry matrix identical to the fabric route | **PROVEN_BY_TEST** | disabled binding / permission-changed / expired principal → 403, attempt id absent from response |
| Production frame path (socket + ingress service) | **PROVEN_BY_TEST** | `[bridge]` transport tests through `CeoIngressWorkspaceClient` + `ExecutiveControlService` + `CeoIngressAppBinding` — the same four layers the OS web client uses |
| Source swapped mid-read → SOURCE_CHANGED, never stale data | **PROVEN_BY_TEST** | monkeypatched read returning after a source swap → typed SOURCE_CHANGED envelope |
| OS parser is fail-closed | **PROVEN_BY_TEST** | 13 fault-injection cases (extra key, bad verdict, invariant-without-reason, observed-without-kinds, pid 0, facts-without-pid, bad freshness, two attempts, newline evidence, bad note, future stamp, schema drift, oversized body) all → `INVALID_RESPONSE` |
| Panel states | **PROVEN_BY_TEST** | vitest: unknown-no-source, PROVEN chips+facts, VIOLATED with reason + duplicate kinds, harness UNKNOWN with reason, typed refusal rendering, signed-out/no-reader unknown-with-reason (asserts `bindMissionHost` omits the method), unreadable run id disabled before fetch |
| Live composition against the real default state path | **OBSERVED_LIVE** | `default_source().read("runs/live-probe")` 2026-11-09T13:34:14Z → honest `ADAPTER_STATE_EMPTY` document (below): census genuinely fresh, every invariant UNKNOWN with its reason; the store does not exist in this checkout yet, which is honest empty, not an error |
| src-tauri Rust command `read_t3_attempt_fleet` | **SOURCE_ONLY** | NOT added (src-tauri is integrator-owned in this lane); the native client therefore has no `readT3AttemptFleet` and the desktop block shows honestly-not-connected — asserted by vitest |
| Production service install of `default_source()` | **SOURCE_ONLY** | `scripts/executive_os_phase1c.py` untouched (keeps the d7 pin; production composition is outside this lane's grant). Until wired, the production route answers the typed `SOURCE_UNAVAILABLE` refusal — honest, never a fake projection. `default_source()` is the one-line install point |

### Redacted live read (2026-11-09T13:34:14Z, real `take_census()`, mode=ro open of the absent default store)

```json
{
 "schema": "mastermind.t3_attempt_fleet/v1",
 "attempts": [{
   "attempt_id": "runs/live-probe",
   "t3_thread": {"thread_id": null, "run_id": null, "state": null, "unknown_reason": "NO_ADAPTER_ROW"},
   "harness_process": {"pid": null, "provider": null, "model": null, "start_time": null, "unknown_reason": "NO_THREAD_TO_CORRELATE"},
   "thread_count_for_key": null, "thread_count_reason": "NO_IDEMPOTENCY_IDENTITY",
   "harness_count_for_thread": null, "harness_count_reason": "NO_THREAD_TO_CORRELATE",
   "duplicate_launcher": {"observed": null, "kinds": [], "evidence_refs": ["adapter_state:read"], "unknown_reason": "THREAD_COUNT_UNKNOWN"},
   "invariant": {"exactly_one_thread": "UNKNOWN", "exactly_one_harness": "UNKNOWN"},
   "freshness": {"adapter_state": "fresh", "census": "fresh", "thread_read": "absent"},
   "idempotency": {"key": null, "namespace": null},
   "evidence_refs": ["adapter_state:read"]}],
 "notes": ["ADAPTER_STATE_EMPTY"],
 "evaluated_at_utc": "2026-11-09T13:34:14+00:00"
}
```

## Pin moves requiring distinct CRITICAL review

All moved pins go to the exact new reviewed bytes/sites of the same reviewed
tokens; the source-changing commit is named at each pin. No pin was deleted,
skipped, xfailed or weakened.

1. `tests/executive_fabric_release_identity_review.py` `REVIEWED_FILES`:
   - `integrations/mastermind_workspace_app/app.py` → sha256 `f7e4e50df2b8945be5dfdb8e5092f4d68dcfe738c75cf39efaa89a1ffb463e95`; sites rows 927/938/946/952/961/971/976/982 → **928/939/947/953/962/972/977/983** (same columns; values 400/403/400/400/400/403/503/403 unchanged). Source commit ``108e84da3`` (+7 lines: route constant, fence row, 4-line endpoint, Route row — all additive, below the pinned sites; corrected per the distinct review #2).
   - `control_plane/workspace_read_service.py` → sha256 `4666348f25299d01df1d57dd1d06d5e656f1dcf9f469e76480cbc69dbb34d2f1`; sites `((719,93,96),(721,56,59),(728,46,49),(729,56,59))` → **`((723,93,96),(725,56,59),(732,46,49),(733,56,59))`** all `'403'`. Source commit ``108e84da3`` (+4 guard lines, +4 dispatch lines and two signature edits — additive, below the pinned sites; corrected per the distinct review #2).
2. `tests/executive_company_identity_review.py` anchor `_handle_ceo_ingress_connection`: `source_sha256` `21754f04…` → **`af0a97de9bfc503db756626d0eacf65876848473cfb2230d8fbe478c9bb5c1cc`**; `ast_sha256` `27f53e56…` → **`8ba83fc94d6ccbfe11eec5ed1b477a28e0ec92bd199f34c4123eb5be6803d912`**; relative site paths `'body', 59` → **`'body', 60`** for the three ingress denial operands (spellings unchanged; deeper indexes held; verified same literals resolve at lines 6056/6069/6071 before recording). Source commit ``108e84da3`` (one import, one elif, and one edit to the existing admitted-schema set line inside the reviewed method; corrected per the distinct review #2). This anchor is shared by `tests/test_company_consultation_identity_review.py` (no separate edit needed).
3. `tests/test_workspace_fabric_review_pins.py`: `STATUS_SITES` `((6048,66,69),(6061,74,77),(6063,75,78))` → **`((6056,66,69),(6069,74,77),(6071,75,78))`** (`executive_service.py` rows). Source commit ``108e84da3``.
4. `tests/test_workspace_control_room_review_pins.py`: `EXPECTED[HTTP_PATH]` rows 927/938/946/952/961/971/976/982 → **928/939/947/953/962/972/977/983** (same columns). Source commit ``108e84da3``.

Not touched: `tests/test_next_mounted_identity_pins.py`, `tests/test_executive_reviewed_site_identity_tokens.py`, `tests/test_company_consultation_identity_review.py` (shares anchor (2), self-adjusts), d7 (`scripts/executive_os_phase1c.py` unedited — production install deliberately left to the integrator), `tests/test_discovery_correction_identity_review.py` (auth.rs untouched).

### d8 self-scan (`_scan_added_identity_diff` over `git diff 70dabba15`)

Run on the final diff per the brief. Three prose mentions of reviewed literals
in my dated comments ("403, 403, 503", "0o710", "reviewed 403 operands") were
**reworded** away. Residual findings are exactly the 12 pin-site coordinates
above (928…983, 723…733) inside the two review-pin test files — the reviewed
tokens' new locations, which the pin format requires verbatim (same as the
accepted 2026-11-09 reconciliation precedent). **No production path is
flagged; no new identity/topology literal was introduced.**

## Exact commands + counts

```
env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
  tests/test_workspace_t3_attempt_fleet_read.py tests/test_workspace_capacity_fabric.py \
  tests/test_t3_attempt_fleet_projection.py tests/test_t3_process_census.py \
  tests/executive_fabric_release_identity_review.py tests/test_workspace_fabric_review_pins.py \
  tests/test_workspace_control_room_review_pins.py tests/test_next_mounted_identity_pins.py \
  tests/test_executive_reviewed_site_identity_tokens.py tests/test_company_consultation_identity_review.py \
  tests/test_ceo_submit_armed_composition.py
→ rc=0, 765 passed, 0 failed (dot count; this repo's reporter prints no summary
  line under -q — 765 dots, cross-checked exactly against per-file
  --collect-only counts: 46 new route tests + 69 capacity fabric + 42 projection
  + 40 census + 321 d7/d8 + 182 reviewed-site tokens + 27 fabric pins
  + 18 control-room pins + 8 next-mounted pins + 12 consultation; the two
  `executive_*_identity_review.py` modules are shared REVIEWED_FILES data with
  no tests of their own)

cd app/mastermind_os && npm run typecheck
→ rc=0

cd app/mastermind_os && npx vitest run --maxWorkers=2
→ final: 7129 passed | 12 skipped | 1 failed (7142) across 429 files; the one
  failure is `App.project-draft-files.test.tsx` with a 5s jsdom timeout — the
  load-flake signature E's reconciliation already documented for this machine
  (full-parallel runs under external load); it passes 5/5 in isolation (rc=0)
  and passed in the prior full run. Every deterministically-failing test found
  during this lane was root-caused and fixed (see the regression section); the
  two prior full runs' 78–81 failures were the auth-store loop, all green now.
```

### OS-side regressions found and fixed during this lane (before commit)

1. **Auth-store render loop (78–81 App tests red).** The first panel mount read
   auth through `useSyncExternalStore` with an inline `getSnapshot` closure;
   against App hosts whose `getState()` returns a fresh object per call this
   drove React into `Maximum update depth exceeded` (`updateStoreInstance →
   forceStoreRerender` loop), first masked as 5s jsdom timeouts under load.
   Bisected empirically: base `host.ts`/`web-auth.ts`/`AttendedFabricWorkspace.tsx`
   passed 32/32; my `host.ts`+`web-auth.ts` with base workspace still passed —
   the mount was the sole cause. Fixed by adopting the incumbent panel pattern
   exactly (`CapacityFabricRead.tsx:15`): plain render-time
   `host?.auth?.getState()`.
2. **Single-listener auth mock displacement (1 App test red).** After (1), one
   office test still failed deterministically (`refuses a submission whose
   frozen preview is no longer current`): the office test mock's
   `subscribe: fn => { listener = fn; … }` keeps ONE listener slot, and my
   block's in-`useEffect` auth subscription displaced the App's listener, so
   `made.notify` never advanced the App's epoch and the stale-preview refusal
   never fired. Passed on base, failed with the mount, passed with the
   subscription removed (each verified by rerun). A bound host already bumps
   its epoch on every auth change and the parent remounts this block through
   `key={epoch}`, so the in-block subscription was redundant: removed; the
   effect now only aborts/drops any owned read. `host.ts`/`web-auth.ts` diffs
   are purely additive (optional interface members + a guarded spread inert
   until a client defines `readT3AttemptFleet`) and were proven non-causal by
   the same bisections.

Three of my own first-draft test assertions were also wrong (unavailable
`toBeDisabled` matcher; a no-op fault mutation; an assertion aimed at the
wrong region) — all corrected.

(Isolation re-runs: the three pin/review files re-ran green after the d8
reword — `18 passed in 3.41s`.)

## What the integrator must do

1. **CRITICAL review of the pin moves above** (review/release-automation row;
   genuinely distinct read-only reviewer; nothing else in this lane is pending).
2. src-tauri: add the Rust `read_t3_attempt_fleet` command (compose
   `workspace_t3_attempt_fleet_read` + census off-thread; G's proposal §2
   hunks still apply) and a native client entry named `readT3AttemptFleet` —
   `host.ts` already activates the guarded method the moment the client
   exposes it; until then desktop honestly shows not-connected.
3. Optionally install `default_source()` into the production service
   composition via `scripts/executive_os_phase1c.py` (needs the d7 re-pin);
   until then the production route answers the typed `SOURCE_UNAVAILABLE`
   refusal rather than a projection.
4. Merge rides the existing Workspace read path and protected queue; no new
   listener, daemon, queue, registry or store was added anywhere in this lane.

## Not done, and why

- No push/PR (brief forbids; the integrator consumes this branch).
- No src-tauri edits or `cargo test` (forbidden surface in this lane).
- No production `executive_os_phase1c.py` install (outside grant; d7 pin
  preserved; route stays honestly SOURCE_UNAVAILABLE there until step 3).
- No live thread-read evidence exists on this machine, so `thread_read`
  freshness stays honestly `absent` in every observation.
