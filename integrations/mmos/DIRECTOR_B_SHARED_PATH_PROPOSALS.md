# Director B shared-path changes (src-tauri) — exact patches for the integrator

My exclusive scope is `app/mastermind_os/src/hermes-native/**`, the session-bridge Hermes
python, and the two new control_plane contract modules. The #2180 native host path lives in
`app/mastermind_os/src-tauri/src/hermes_native/` — outside that scope, but it is the only
place a new native operation can be produced. Only `src-tauri/src/auth.rs` was on the
do-not-edit list, so I made the two minimal edits below directly on my branch **and** record
them here verbatim for integrator review. Both are additive; no existing operation, guard
or auth path changed. If the integrator prefers to re-own these paths, revert my two
src-tauri hunks and apply exactly these patches.

## 1. `src-tauri/src/hermes_native/core.rs` — one match arm + test asserts

The `team_roster` operation is read-only: exactly the `operation` field, like `status`/`list`.

```rust
 // in valid_fields(), the match on operation:
         "status" | "list" => &["operation"],
+        "team_roster" => &["operation"],
         "create" => &["operation", "role", "requestId"],
```

```rust
 // in mod tests::closed_operations():
+        assert!(valid_fields("team_roster", &["operation"]));
+        assert!(!valid_fields("team_roster", &["operation", "sessionId"]));
```

Run `cargo test` in `src-tauri` (not run in this lane — no Rust build performed here;
SOURCE_ONLY, see the lane ledger).

## 2. `src-tauri/src/hermes_native/bridge.py` — four additive hunks

**(a) FIELDS / normalize_request** — admit the operation with no arguments:

```python
-FIELDS = {"status": {"operation"}, "list": {"operation"},
+FIELDS = {"status": {"operation"}, "list": {"operation"}, "team_roster": {"operation"},
 ...
-    if operation in {"list"}:
+    if operation in {"list", "team_roster"}:
         return operation, {}
```

**(b) execute_request** — read-only dispatch, same envelope shape as `list`, plus the
roster payload (built off-thread; `runtime.team_roster` never mutates anything):

```python
     if operation == "list":
         ...
+    if operation == "team_roster":
+        roster = await asyncio.to_thread(runtime.team_roster, public)
+        return envelope("READY", operation=operation, runtime=public, roster=roster)
```

**(c) failureReason enrichment** — after projecting a receipt for `send`/`receipt` (and in
the `recover_send` branch), when the receipt is terminal+failed, attach the producer's
stamped failure classification (from `admission_result` → `stamp_failure`
`failure_reason`, falling back to `classify_agent_error` on the error text, else
`"unknown"`). The TS parser only accepts it on terminal+failed receipts (closed
14-value vocabulary mirroring `tools.bot_failure_reasons`).

**(d) NativeRuntime additions** — `receipt_failure_reason(admission_id)`,
`require_roster_source()` (hermes-agent source pin: `observed_code` commit + sha256 of
`tools/bot_mode_probe.py` / `tools/bot_failure_reasons.py`; drift ⇒
`NATIVE_ROSTER_SOURCE_CHANGED` before any roster work), and `team_roster(public)`
(importing the roster predicates from the pinned install, building ≤64 bot rows of
`mastermind.team_roster/v1` with the same evidence ladder as
`control_plane/team_roster_projection.py`: identify-beats-lock, lock+ps with
recycled-PID start-time defense, `state.db` activity, unknown-with-reason otherwise).

`native-port.ts` needed **zero** edits: the roster operation rides the existing
non-mutating dispatch path (closed echo check + `parseNativeView` validation).

## 3. Files I own outright (for integration context)

- `control_plane/team_roster_projection.py`, `control_plane/teamlink_contracts.py`
- `integrations/session_bridge/hermes_native_continuity.py`
- `app/mastermind_os/src/hermes-native/{team-roster-contract,teamlink-contract,continuity}.ts`
  and the `contract.ts` op-union/view/receipt edits
- tests: `tests/test_team_roster_projection.py`, `tests/test_teamlink_contracts.py`,
  `tests/test_session_bridge_native_continuity.py`, and the four new vitest suites

See `LANE_HERMES_DIRECTOR_B.md` for PROVEN vs SOURCE_ONLY and the gates.
