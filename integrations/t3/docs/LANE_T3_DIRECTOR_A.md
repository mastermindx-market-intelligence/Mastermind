# LANE — T3 + DSH execution durability (Director A, Rev 5)

Repo-side ledger for the Director A work package (2026-11-09), branch
`t3/durable-t3-adapter-state`. Program-side context (read-only):
`~/.hermes/profiles/engineering/mmos/T3_HANDOFF_V2.md` (§2 P0, §3 scope,
§6 failure matrix), `LANE_T3.md` (live proof + finding 1), `LANE_DSH.md`
(§1 ACP boot args), `T3_CENSUS.md` / `SEAM_CENSUS.md`.

## What changed

### A1 — Durable adapter state (P0)

`control_plane/t3_execution_adapter.py` no longer keeps launch intents,
receipts, original refs, cursors, cancel records, result references or
launch bindings in process-local dicts. New `T3AdapterStateStore` protocol
with two implementations:

- `SQLiteT3AdapterStateStore` — `t3_adapter_runs` table in the SIBLING file
  `data/control_plane/t3_adapter_state.sqlite3` beside the Executive durable
  store (default via `default_t3_adapter_state_path()`). Integrator
  correction (Fable, 2026-11-09): the lane's first default placed the table
  inside `executive.sqlite3`; the Executive runtime pins a normalized digest
  over its ENTIRE `sqlite_master` (`_NORMALIZED_V7_SCHEMA_DIGEST`) and
  refuses to open on mismatch, so sharing the file would have bricked the
  runtime. The store now refuses that file outright. Folding the table into
  the Executive schema is an optional V8 migration on the shared path. Own
  connection: `BEGIN IMMEDIATE` per write, `busy_timeout=10000`,
  `row_factory=sqlite3.Row`, following the `WorkspaceLeaseStore` pattern.
  The Executive store was inspected first
  (`control_plane/executive_runtime.py`): it offers NO reusable
  attempt-scoped adapter-state facility — `attempts.launch_metadata_json`
  is writable only inside its own guarded transactions and that file is
  outside this lane's edit scope. Hence the same-file/different-table
  default, documented in the store docstring. No journal-mode change
  (whole-file property; the file is Executive-owned) — pinned by test.
- `InMemoryT3AdapterStateStore` — the test double; deliberately stores
  pre-serialized canonical JSON and reconstructs through the same
  rehydrators as SQLite, so tests exercise the real round-trip path.

Ordering claims now hold at the store seam (traced by `TracingStateStore`):
intent persisted BEFORE `launch_thread`; receipt + adopted original ref +
validated spec BEFORE the ACK; cursor advanced only after a successful
exact read; result reference ledgered BEFORE the `CollectionReceipt`;
cancel requested/settled states persisted.

**Idempotency identity is (authenticated namespace, clientRequestId).**
`T3NativeClientPort` gained optional `authenticated_namespace()`. Namespace
resolution: port principal > binding v1.1 `caller_namespace` > legacy
constant (`T3_REQUEST_NAMESPACE`). The intent persists the namespace, and
`reattach` refuses a different authenticated principal — the live-proof
finding that the SAME `clientRequestId` under two OAuth clients minted two
threads is now structurally impossible to replay silently.

Replay verification additions: a receipt echoing a foreign
`client_request_id` or request namespace is refused (in the
crash-between-intent-and-ACK zone the echo is the only identity evidence);
a known-thread original still requires the exact same thread.

### A2 — Cold-restart proof

`tests/test_t3_adapter_durability.py` (new): five failure-matrix scenarios
against SQLite on disk, driven by a counting fake port that models the
upstream idempotency surface (mint-then-lose-ACK included):

1. restart AFTER start: second adapter reattaches the SAME thread; native
   launch count stays 1; zero native calls; a second `start` is refused.
2. crash BETWEEN intent-persist and ACK: recovery replays the SAME
   key+namespace through `replay_launch` — never `launch_thread` — and the
   adopted execution is durable for a third process (no native call).
3. different authenticated namespace (another OAuth client): refused, no
   native call.
4. status cursor + requested-vs-settled cancel ledger survive restart;
   the new process's first read uses the persisted cursor.
5. replay returning a different thread / echoing a foreign key: refused.

Plus store-level round-trips (spec Paths/tuples/mappings, binding tuples,
receipt, ref), the same-file coexistence contract with an Executive-owned
table, journal-mode non-modification, and `clear_launch_attempt` refusing
to roll back a receipted attempt.

### A3 — Pinned upstream admission patch, real TypeScript proof

Donor pin `0770446869d247a8b28c27d7ed93f47f8ff0c1e4` (shared clone
READ-ONLY). Scratch copy at `/tmp/t3-patch-proof`, `pnpm@12.14.0 install`
(the repo pins that exact version), patch applied, then:

- `effect-tsgo tsrs --noEmit` in `apps/server`: the previous patch bytes
  had **5 real type errors** — all fixed (deterministic Context key;
  `JSON.stringify` hoisted out of the Effect lambda; `Effect.fromOption`
  with typed error mapper; `Effect.filterOrFail`; `Effect.ignore`). Final:
  exit 0, 0 errors; 491 effect suggestions vs 489 unpatched baseline (the
  +2 are `schemaClassMissingBrand` on the two new `TaggedError` classes —
  upstream's own idiom at this pin).
- New colocated suite `MastermindAdmissionAdapter.test.ts` (9 tests, run
  via vitest from the pnpm store since the repo's `vp` runner is external
  to scratch trees): disabled mode = pure passthrough (incumbent service
  INSTANCE returned, zero fetches); blocked launch fails with the typed
  cause before any preparation effect; admitted launch proceeds + binds
  the ledger; stale lease blocks start AND restart with the typed cause
  and never interrupts the original turn; `provider-turn.interrupt` never
  decorated (zero admission consults); steer records but proceeds.
- The suite exposed a real defect in the old bytes: three decorators
  DOUBLE-WRAPPED the blocked error. Fixed: fail with the raw
  `MastermindAdmissionBlockedError`, let each `mapError` wrap exactly once.
- Upstream regression check on the patched tree:
  `ThreadLaunchService.test.ts` 46/46 pass (default path unchanged).
- Standalone round-trip of the committed bytes from a clean pin checkout:
  typecheck 0 errors, 55/55 tests (9 admission + 46 upstream).
- `MANIFEST.md` regenerated (sha256 `f78413fb…`, 3 files, +1075/−6) with
  exact commands/outputs. No server started; port 3773 never bound; the
  patched tree was never run as a live desktop app.

### A4 — DSH facts

`DshAcpProviderConfig.argument_rows = ("--profile", "mmx-acp")` — TWO rows,
already correct in `control_plane/dsh_acp_runtime.py` (the
`shipped_profile_argument_rows = ("--profile", "acp")` variant is also
two-row). Fixed the one stale repo doc
(`integrations/t3/docs/ubuntu3_t3_install_recipe.md` §5) that still
prescribed THREE rows; it now cites the settled receipts and the refusal.
Descriptor stays `implemented=False`. No live probe needed — the receipts
in `LANE_DSH.md` §1 already settle this; no model turns spent.

### A5 — Runtime README truth pass

`integrations/mmos/README_V1_RUNTIME.md` §3 + lane ledger updated to the
post-D3/Director-A truth (below).

## PROVEN vs SOURCE_ONLY

- **PROVEN_LIVE (recorded receipt, pre-dates this lane):** the
  `t3-native` ADAPTER PATH — one real `t3_thread_launch` + cursor read
  through the native seam; receipt
  `integrations/t3/live_proof/t3_live_proof_receipt.json`, pinned in
  `tests/test_worker_adapter.py`. The live-proof harness
  (`integrations/t3/live_proof/t3_live_proof.py`) now runs on the same
  state-store seam.
- **PROVEN by tests (in-tree, fake ports):** all A1/A2 durability and
  idempotency claims; adapter behavior for namespace refusal, replay
  adoption, cursor/cancel survival.
- **PROVEN by toolchain (scratch, not installed):** the upstream admission
  patch typechecks clean at the pin and its unit suite + an upstream
  regression suite pass. This is SOURCE_ONLY — the patch is NOT applied to
  any live T3 installation; upstream adoption is a separate act.
- **NOT PROVEN:** installed-fleet behavior of `t3-native` (unselected as a
  worker route — selection is a deployment act); any `dsh-acp` execution
  (named-not-implemented); production admission endpoints (the wire
  protocol is exercised through fetch doubles only).

## Open issues

1. `t3-native` remains UNSELECTED as a worker route: flipping selection is
   a deployment act by the incumbent runtime, out of this lane's scope.
2. The admission patch's `ThreadLaunchError.operation` label for launch
   blocks is approximated as `"resolve-project"` (closed literals list
   upstream); the structured cause carries the real reason/phase.
3. The dsh-acp flip still needs the full T3→DSH composition and a real
   native descendant-admission hook (`bounded_native_fanout` requires a
   named enforcement ref).
4. The upstream patch should be proposed upstream (the donor is an
   external repo); the pinned patch + manifest are the durable artifact
   until then.
5. `MASTERMIND_ADMISSION_ENDPOINT` wire protocol is intentionally minimal
   (`POST /v1/admit`); schema validation was avoided to keep upstream's
   layer graph dependency-free — revisit if the endpoint grows.
