# T3 attempt-fleet contract + native bridge proposal — exact patches for the integrator

Author: Director G (GLM-5.3 sub-orchestrator), lane `t3/attempt-fleet-visibility`.
My exclusive scope was `control_plane/t3_attempt_fleet_projection.py`,
`control_plane/t3_process_census.py`, `scripts/t3_attempt_fleet_snapshot.py`
and their tests. `app/mastermind_os/src-tauri/**` belongs to the integrator, so
the hunks below are PROPOSED VERBATIM and NOT applied (same convention as
`DIRECTOR_B_SHARED_PATH_PROPOSALS.md`). Nothing here edits React: the Fleet
view is Director D's surface; §3 names where it reads.

Source of truth for the payload: `control_plane/t3_attempt_fleet_projection.py`
(`mastermind.t3_attempt_fleet/v1`, `validate_attempt` is the fail-closed
parser this TS mirror must match field-for-field).

## 1. The `mastermind.t3_attempt_fleet/v1` document

Top level: `{ schema, evaluated_at_utc, attempts: Attempt[], notes: string[] }`.
On typed refusal (corrupt/unreadable evidence) the bridge returns
`{ schema, refusal: <CODE>, attempts: [] }` — never a partial projection.

### Attempt (field-by-field, closed vocabularies)

| field | type | vocabulary / grammar |
| --- | --- | --- |
| `attempt_id` | string | `[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}` — the company run id (`runs/...`) |
| `idempotency.key` | string \| null | sha256 clientRequestId, null when no intent/receipt |
| `idempotency.namespace` | string \| null | principal-qualified request namespace |
| `t3_thread.thread_id` | string \| null | native thread id (`mcp:launch:<hex>`) |
| `t3_thread.run_id` | string \| null | native run id (`run:thread:...`) |
| `t3_thread.state` | string \| null | bounded native status (≤32) or null |
| `t3_thread.unknown_reason` | `NO_ADAPTER_ROW` \| `NO_RECEIPT` \| null | null ⇒ thread_id present |
| `harness_process.pid` | number \| null | census pid of the harness tree root |
| `harness_process.provider` | string \| null | `claude` \| `codex` \| `dsh` (executable family) |
| `harness_process.model` | string \| null | `--model` flag value (≤64) |
| `harness_process.start_time` | ISO string \| null | UTC, second precision |
| `harness_process.unknown_reason` | `HARNESS_NOT_OBSERVED` \| `CENSUS_STALE` \| `CENSUS_ABSENT` \| `NO_WORKSPACE_IN_SPEC` \| `NO_THREAD_TO_CORRELATE` \| null | null ⇔ pid present |
| `thread_count_for_key` | number \| null | distinct thread ids minted under (key, namespace) |
| `thread_count_reason` | `NO_RECEIPT_THREAD` \| `NO_IDEMPOTENCY_IDENTITY` \| null | |
| `harness_count_for_thread` | number \| null | correlated harness TREES (wrapper+child collapse to 1) |
| `harness_count_reason` | same vocabulary as harness_process.unknown_reason \| null | 0 count carries `HARNESS_NOT_OBSERVED` |
| `duplicate_launcher.observed` | boolean \| null | null = unknown (never collapse to false) |
| `duplicate_launcher.kinds` | (`dsh_direct`\|`codex_cli`\|`second_t3_thread`\|`other`)[] | sorted, deduped |
| `duplicate_launcher.evidence_refs` | string[] | `adapter_state:*` \| `census:pid:*` \| `thread_read:*`, ≤24 |
| `duplicate_launcher.unknown_reason` | string \| null | null ⇔ observed is boolean |
| `invariant.exactly_one_thread` | `PROVEN` \| `VIOLATED` \| `UNKNOWN` | VIOLATED ⇔ ≥2 threads under one (key, namespace) |
| `invariant.exactly_one_harness` | `PROVEN` \| `VIOLATED` \| `UNKNOWN` | 0 observed harnesses is UNKNOWN, never VIOLATED |
| `freshness.adapter_state` | `fresh` \| `unknown` | |
| `freshness.census` | `fresh` \| `stale` \| `unknown` | stale ⇒ every process-side fact is unknown |
| `freshness.thread_read` | `fresh` \| `stale` \| `absent` \| `unknown` | |
| `evidence_refs` | string[] | ≤24, bounded, no newlines |

Invariants that must hold in ANY parser: `observed === true ⇒ kinds.length ≥ 1`;
`observed === null ⇔ unknown_reason !== null`; `thread_id === null ⇔
unknown_reason !== null`; `pid === null ⇔ harness unknown_reason !== null`;
every closed set enforced exactly (unknown extra field ⇒ reject).

### Proposed TS mirror — `app/mastermind_os/src/hermes-native/t3-attempt-fleet-contract.ts`

```ts
/** T3 attempt fleet contract (mastermind.t3_attempt_fleet/v1) — read-only
 * per-attempt exactly-one projection. Fail-closed like parseTeamRoster:
 * unknown stays unknown with its typed reason; UNKNOWN never collapses to a
 * healthy verdict. No transport, credential, authority or retry surface. */
export type InvariantVerdict = "PROVEN" | "VIOLATED" | "UNKNOWN";
export type FreshnessState = "fresh" | "stale" | "absent" | "unknown";
export type DuplicateKind = "dsh_direct" | "codex_cli" | "second_t3_thread" | "other";

export interface T3AttemptIdempotency { key: string | null; namespace: string | null; }
export interface T3Thread {
  thread_id: string | null; run_id: string | null; state: string | null;
  unknown_reason: string | null;
}
export interface T3HarnessProcess {
  pid: number | null; provider: string | null; model: string | null;
  start_time: string | null; unknown_reason: string | null;
}
export interface T3DuplicateLauncher {
  observed: boolean | null; kinds: DuplicateKind[];
  evidence_refs: string[]; unknown_reason: string | null;
}
export interface T3Attempt {
  attempt_id: string;
  idempotency: T3AttemptIdempotency;
  t3_thread: T3Thread;
  harness_process: T3HarnessProcess;
  thread_count_for_key: number | null; thread_count_reason: string | null;
  harness_count_for_thread: number | null; harness_count_reason: string | null;
  duplicate_launcher: T3DuplicateLauncher;
  invariant: { exactly_one_thread: InvariantVerdict; exactly_one_harness: InvariantVerdict };
  freshness: { adapter_state: FreshnessState; census: FreshnessState; thread_read: FreshnessState };
  evidence_refs: string[];
}
export interface T3AttemptFleet {
  schema: "mastermind.t3_attempt_fleet/v1"; evaluated_at_utc: string;
  attempts: T3Attempt[]; notes: string[];
}
export function parseT3AttemptFleet(value: unknown): T3AttemptFleet;
// Mirror control_plane/t3_attempt_fleet_projection.py validate_attempt():
// exact key sets, closed vocabularies, attempt_id/iso/reason patterns, and
// the four cross-field invariants above. Reject anything else with
// NATIVE_RESPONSE_INVALID.
```

## 2. Proposed native bridge operation — `t3_attempt_fleet` (read-only)

One attempt per call, like `read`; fields exactly `{operation, attemptId}`.
`attemptId` is the company run id — it CONTAINS `/` (`runs/t3-live-proof-1`),
so it must NOT be validated with `identifier()`/`valid_id()` (their grammar
excludes `/`); use the dedicated `ATTEMPT_ID` grammar below.

### (a) `src-tauri/src/hermes_native/core.rs`

```rust
 // in valid_fields(), the match on operation:
         "status" | "list" => &["operation"],
         "team_roster" => &["operation"],
+        "t3_attempt_fleet" => &["operation", "attemptId"],
         "create" => &["operation", "role", "requestId"],

 // new guard beside valid_id (run ids carry '/', session ids never do):
+pub fn valid_attempt_id(value: &str) -> bool {
+    (1..=160).contains(&value.len())
+        && value.as_bytes()[0].is_ascii_alphanumeric()
+        && value.bytes().all(|c| c.is_ascii_alphanumeric() || b"_./:%=-".contains(&c))
+        && !value.contains("..")
+}

 // in mod tests::closed_operations():
+        assert!(valid_fields("t3_attempt_fleet", &["operation", "attemptId"]));
+        assert!(!valid_fields("t3_attempt_fleet", &["operation"]));
+        assert!(!valid_fields("t3_attempt_fleet", &["operation", "attemptId", "url"]));

 // in mod tests (attempt ids are run ids, not session ids):
+        assert!(valid_attempt_id("runs/t3-live-proof-1"));
+        assert!(!valid_attempt_id("../evil"));
+        assert!(!valid_attempt_id("/tmp/evil"));
```

### (b) `src-tauri/src/hermes_native/bridge.py`

```python
 # module constants — the attempt-id grammar admits run ids (contain '/'),
 # never paths, dotdots or control characters:
+ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:%=-]{0,159}\Z")

-FIELDS = {"status": {"operation"}, "list": {"operation"}, "team_roster": {"operation"},
+FIELDS = {"status": {"operation"}, "list": {"operation"}, "team_roster": {"operation"},
+          "t3_attempt_fleet": {"operation", "attemptId"},

 # in normalize_request(), beside the sessionId branch:
     session = {"session_id": identifier(value["sessionId"])} if "sessionId" in value else {}
+    if operation == "t3_attempt_fleet":
+        if type(value["attemptId"]) is not str or not ATTEMPT_ID.fullmatch(value["attemptId"]):
+            raise BridgeRefusal("REQUEST_INVALID")
+        return operation, {"attempt_id": value["attemptId"]}

 # in execute_request(), beside the read-only team_roster dispatch:
         if operation == "team_roster":
             roster = await asyncio.to_thread(runtime.team_roster, public)
             return envelope("READY", operation=operation, runtime=public, roster=roster)
+        if operation == "t3_attempt_fleet":
+            fleet = await asyncio.to_thread(runtime.t3_attempt_fleet, params["attempt_id"])
+            return envelope("READY", operation=operation, runtime=public, attempt=fleet)
```

### (c) `NativeRuntime` addition (bridge-side, integrator-owned)

`t3_attempt_fleet(attempt_id)` = compose the existing pure modules off-thread:

```python
def t3_attempt_fleet(self, attempt_id):
    from control_plane.t3_attempt_fleet_projection import (
        T3AttemptFleetError, project_attempt, read_adapter_attempt_rows)
    from control_plane.t3_process_census import take_census
    rows = read_adapter_attempt_rows(default_t3_adapter_state_path())  # mode=ro
    fleet = project_attempt(attempt_id, rows=[r for r in rows if r.run_id == attempt_id],
                            all_rows=rows, census=take_census())
    return fleet.to_dict()   # BridgeRefusal("NATIVE_T3_FLEET_REFUSED") on T3AttemptFleetError
```

No daemon, no listener, no new store: one read-only sqlite open (the sibling
`t3_adapter_state.sqlite3`, never `executive.sqlite3`), one bounded `ps`, one
pure projection. `native-port.ts` needs ZERO edits — the operation rides the
existing non-mutating dispatch path (closed echo check + `parseNativeView`),
exactly like `team_roster`.

## 3. Where Director D's Fleet view reads it

The Fleet surface today (see `App.fabric-fleet.test.tsx`) is the
"Fleet & Capacity" company-operation route with two blocks: "Original capacity
receipts and run records" and "Recent Fabric runs" (Load runs → per-run select
→ "Use in run inspector"). Proposal:

- **Attempt list source**: the existing attended-Fabric catalog run list
  (`readAttendedFabricCatalog`) already returns run ids; an attempt row's
  `attempt_id` IS that run id. No second list API is introduced.
- **Per-attempt T3 block**: next to the run inspector, a "T3 attempt fleet"
  details block that dispatches `t3_attempt_fleet` with the selected run id
  through `native-port.ts` (non-mutating path), parses with
  `parseT3AttemptFleet`, and renders the two invariant chips
  (`exactly_one_thread`, `exactly_one_harness`) with the honest four-state
  vocabulary PROVEN / VIOLATED / UNKNOWN(+reason) — same authority-honesty
  pattern as the design-lead's PREVIEW EFFECT·NONE chips (MMOS_REV5 design
  reassessment) — plus `duplicate_launcher` kinds when observed=true, and
  harness pid/provider/model/start_time when observed.
- **Disabled/no-source states**: no native host or signed-out ⇒ the block
  renders unknown-with-reason, never healthy, never zero — matching the
  existing "No qualified retained host observation is connected" pattern.

## 4. Known correlation limits (render honestly, do not hide)

1. **Workspace-grain harness correlation.** The durable state carries
   `spec.workspace_path`, and T3 harness argv carries the worktree path — that
   is the only thread→harness join argv offers (the `--session-id` is a
   provider session id, not the T3 thread id). When several live attempts
   share one worktree, EACH attempt's `harness_count_for_thread` counts all
   trees in that worktree (observed live: worktree `t3-c4bdadf2` hosted 3
   harness pairs on 2026-11-09). Display VIOLATED-with-reason as designed;
   the durable fix is a thread-id→pid fact from T3 itself (upstream gap,
   recorded in the lane ledger).
2. **Remote/already-exited harnesses** read as count 0 ⇒ UNKNOWN, never
   VIOLATED (mission test row).
3. **Adapter-state absence** (no durable store composed yet) ⇒ zero attempts,
   note `ADAPTER_STATE_EMPTY` — the desktop's ad-hoc threads are not
   adapter-minted runs and are deliberately NOT projected as attempts.

## 5. Integrator decision (Fable, 2026-11-09)

§2's native-bridge operation is **not applied**. `src-tauri/src/hermes_native/bridge.py`
runs inside the installed desktop app against the Hermes install under `~/.hermes`;
it has no Mastermind checkout on `sys.path` (it *mirrors* `team_roster_projection.py`
rather than importing it), and the durable adapter state lives beside the Executive
runtime (`data/control_plane/t3_adapter_state.sqlite3`), not on the Hermes host.
The per-attempt fleet read therefore belongs on the **Workspace read route** that the
Capacity Fabric panel already uses (`/workspace/resources/fabric/current`, #2351):
a sibling `GET /workspace/resources/t3/attempts/<attempt_id>` composed in
`integrations/mastermind_workspace_app/app.py` + `control_plane/workspace_read_service.py`,
admitted in the Executive transport fence (`_WORKSPACE_ADDITIONAL_GET_ROUTES`), read by
the OS through the existing signed HTTP read, parsed by the §1 TS mirror. Those files
carry reviewed identity pins; the lane that lands the route moves the pins exactly and
takes a distinct CRITICAL review. §1 (contract), §3 (where the Fleet view reads it) and
§4 (correlation limits) stand unchanged. Delegated to Director G2.
