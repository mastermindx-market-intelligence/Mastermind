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
- **PROVEN_LIVE (this lane, Director A2 — durable canary receipt):** the
  A1/A2 durability claims ON THE REAL T3 SERVER (environment m2studio,
  T3 0.1.7, provider capacity_fabric / glm-5.3-flash) with SEPARATE OS
  PROCESSES per scenario sharing one on-disk `SQLiteT3AdapterStateStore`:
  crash-after-receipt cold restart recovers with ZERO native calls
  (retained ref), crash-after-launch recovers through exactly ONE
  idempotent replay that returns the ORIGINAL thread (one run upstream),
  and a foreign authenticated namespace is refused locally with zero
  native calls. Receipt
  `integrations/t3/live_proof/t3_durable_canary_receipt.json`, pinned in
  `tests/test_t3_durable_canary_receipt.py`. Exactly 3 real threads were
  minted (the whole budget); see "Live durable canary" below.
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

## Live durable canary (Director A2, 2026-11-09)

`integrations/t3/live_proof/t3_durable_canary.py` turns the fake-port
cold-restart proof into a REAL-PATH proof against the live T3 desktop app
at `http://127.0.0.1:3773/mcp`. Crash points are deterministic
`os._exit` hooks in HARNESS wrappers (a store wrapper after
`put_launch_receipt` commits, a port wrapper after the native launch
returns) — never in the adapter. Every scenario runs as its own OS
process; P1/P2 share one `SQLiteT3AdapterStateStore` at the harness's
authorized scratch root and one cached OAuth client identity (the live
finding-1 rule: the authenticated principal is part of launch
idempotency, so P2 must replay under P1's identity).

Outcome (receipt schema `mastermind.t3_durable_canary_receipt/v1`,
outcome `DONE`, exactly 3 threads = the whole budget):

| Scenario | Native thread | P1 | P2 recovery | Result |
|---|---|---|---|---|
| S1 crash-after-receipt | `…f7f383e3` | launch 1, crash (exit 90) after receipt COMMIT before ACK | ZERO launch/replay/read; retained ref; second start refused; SUCCEEDED; `T3-CANARY-OK durable-s1` | PASS |
| S2 crash-after-launch | `…08f2d536` | launch 1, crash (exit 91) after native launch before receipt | exactly ONE replay (same clientRequestId+namespace) → ORIGINAL thread, one run; SUCCEEDED; `T3-CANARY-OK durable-s2` | PASS |
| S3 foreign namespace | — | stubbed `authenticated_namespace`, no 2nd OAuth client | refused LOCALLY on both attempts, ZERO native calls | PASS |
| S4 interrupt honesty | `…c9ca2265` | live RUNNING target, interrupt `interrupt_requested` | ledger never claimed a settle; settle evidenced by upstream thread row | PASS |

Live findings recorded by the canary (all in the receipt):

1. **Terminal status polls advance the persisted read cursor past the
   final assistant reply**, so `collect_result` can legitimately read an
   empty page after `_wait_terminal`. The canary's reply capture now
   re-reads the thread head and scans ASSISTANT items for the labeled
   nonce line.
2. **A human can append messages to a canary thread through the T3 app
   after the run** (observed on S2: a manual message added failed runs
   ordinal 2–3 after the canary's completed ordinal 1). Verification
   therefore pins per-run evidence (`canary_run_status`), not thread-level
   status.
3. **T3 reclaims interrupted scratch threads from the exact-run read
   path** — `t3_thread_read` returned `thread_not_found` ("no longer
   available") for the interrupted S4 thread at one observation and read
   it normally minutes later; the project-scoped `t3_thread_list` row
   keeps reporting it (`status: interrupted`, `settled: false`). A settle
   must be evidenced by an observation, never inferred from a vanished
   thread; the adapter ledger correctly never claimed one.
4. **`CANCELLING` can outlast a 420 s poll deadline** on this
   server/model pair — the requested-vs-settled ledger (requested,
   unsettled) remained the honest state at deadline.

Operational notes: read-only verification roles (`--role s1-verify` …
`s4-verify`) cold-reattach a terminal run with zero launch/replay calls
and re-observe it; `--assemble` rebuilds the receipt from the current
batch's side files + role logs without spawning anything. The canary
never deletes or archives its threads (T3 owns lifecycle).

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
