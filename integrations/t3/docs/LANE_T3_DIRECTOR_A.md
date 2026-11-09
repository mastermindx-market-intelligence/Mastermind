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

## A3 audit rework (Director A3, 2026-11-09) — finding → fix → test

Source of findings: `integrations/t3/docs/AUDIT_T3_DURABLE_ADAPTER_OPUS_20261109.md`
(distinct Opus audit, verdict NEEDS_REWORK). Base: `t3/t3-hermes-restart-recovery`
@ `70dabba15`. Branch: `t3/a3-adapter-audit-rework-r2` (the planned name
`t3/a3-adapter-audit-rework` is still checked out — clean, no commits — in a dead first
attempt's worktree, which this lane did not touch).

**Fail-before method.** No stash, no extra worktree: `git archive 70dabba15 -- control_plane
tests integrations config common scripts | tar -x -C /tmp/a3-prefix/tree`, copy the NEW
test files over, run them against the pre-fix adapter (byte-identical to `70dabba15`, verified
with `cmp`). Result: **38 failed / 42 passed** pre-fix; **80 passed** post-fix (same two
files). The upstream-patch regression was proven by swapping the pre-fix
`MastermindAdmissionAdapter.ts` back into a private scratch clone and running the new vitest
block (`expected 2 to be 1`). "API absent" means the pre-fix code had no such surface at all;
the "behavior" column is the observed pre-fix failure.

| # | Sev | Fix (file:symbol) | Regression test(s) | Fail-before (pre-fix) | After |
|---|---|---|---|---|---|
| 1 | BLOCKER | `t3_execution_adapter.py` `SQLiteT3AdapterStateStore.claim_launch_intent` (INSERT … ON CONFLICT DO NOTHING in BEGIN IMMEDIATE, `changes()`), `T3ExecutionAdapter.start` (claim before native call, loser → `T3LaunchClaimConflictError`), `put_launch_intent` (never upserts), `clear_launch_attempt(claim_token=)`, write-once `put_launch_receipt(claim_token=)` | `test_t3_adapter_durability.py::AuditReworkStartRaceTests::test_nm01_two_connections_race_start_exactly_one_launch` (2 threads, 2 connections, 0.3 s binding_source), `::test_nm01_two_processes_race_start_exactly_one_launch` (2 OS processes), `::test_nm02_loser_during_in_flight_launch_replays_the_winner`; `AuditReworkStoreTests::test_launch_intents_are_never_upserted`, `::test_clear_launch_attempt_is_claimant_conditional` | `2 != 1` launches (both ACKed); `['started','started']`; upsert not refused; claimant clear: API absent. (NM-02 in-flight test also passes pre-fix: extra coverage, not the fail-before proof) | pass: 1 launch, loser reattaches to winner with 0 native calls, 1 ledger row |
| 2 | BLOCKER | upstream patch `MastermindAdmissionAdapter.ts` `decorateServiceLayer`: no `Layer.build`; incumbent wired via `Layer.provide` (same memo map). Patch sha256 `5785ac95…4e922f` | colocated vitest `MastermindAdmissionAdapter composition` (4 cases: disabled/enforce × both `mergeAll` orders); `test_t3_upstream_patch.py::test_decorators_never_nest_layer_build`, `::test_colocated_suite_pins_built_exactly_once_composition`, `::test_patch_bytes_are_the_pinned_a3_rework` | vitest `expected 2 to be 1` (shared dep built twice, decorated-first, both modes); static: `Layer.build(incumbent)` found | vitest 13/13 + ThreadLaunchService 46/46; `effect-tsgo` exit 0 (0 errors, 491 suggestions = baseline); `git apply --check` clean on the pinned clone (left clean) |
| 3 | MAJOR | `T3ExecutionAdapter._require_attested_principal` (launch needs attestation), `_require_namespace_continuity(native_call=)` (unattested/different principal → `T3NamespaceAttestationError`, code `T3_REAUTH_REQUIRED`; legacy unqualified rows never replay), `_verify_replayed_thread` (crash-zone adoption needs upstream-derived echo), pre-durability replay needs a known thread; live port `T3McpToolPort.from_access_token` (namespace `client:<sid>` from the token claims = upstream `requestNamespace`), echoes only when `threadId == t3_expected_launch_thread_id(ns,key)` | `AuditReworkAdapterTests::test_nm08_unattested_port_cannot_reattach_a_principal_scoped_run`, `::test_nm08_unattested_port_cannot_replay_a_crash_zone_intent`, `::test_nm08_unattested_port_cannot_launch`, `::test_crash_zone_replay_without_upstream_echo_is_not_adopted`; `test_t3_execution_adapter.py::T3LivePortReworkTests::test_port_attests_the_upstream_session_from_the_token_claims`, `::test_receipt_echoes_come_only_from_the_upstream_thread_id`, `::test_expected_thread_id_matches_the_donor_json_stringify_derivation` (node-computed vectors), `::test_port_refuses_an_envelope_for_another_namespace_before_sending` | reattach/replay/launch NOT refused (fail-open skip); echo-free receipt adopted; live port: API absent | pass |
| 4 | MAJOR | `T3McpTransportError` + `t3_mcp_failure_is_definitive_refusal` + `T3McpToolPort._invoke`: pre-send, 4xx (≠408), JSON-RPC −32700/−32600/−32601/−32602, tool `isError` = clean refusal; timeout/reset/5xx/408/other JSON-RPC/garbled/unclassified-after-send = `T3UnknownOutcomeError` | `T3LivePortReworkTests::test_lost_replies_keep_the_intent_and_clean_refusals_roll_back` (12 subtests), `::test_unparsable_launch_reply_is_an_unknown_outcome` | API absent; pre-fix live port (`t3_live_proof.py` `LiveT3McpPort.launch_thread`) wrapped every exception in `RuntimeError` → adapter clean refusal → intent rolled back (by reading) | pass: unknown keeps the intent, clean rolls back |
| 5 | MAJOR | `_t3_spec_from_json`/`_decode_typed` (per-field declared type via `typing.get_type_hints`; scalars keep JSON type) + persisted `spec_sha256` of the caller's ORIGINAL spec (authoritative in `reattach`) | `AuditReworkAdapterTests::test_spec_with_non_normalized_paths_round_trips_and_reattaches` | loaded `allowed_artifact_paths` = `PosixPath('out/result.json')…` ≠ `'out/./result.json'` → reattach "launch spec drifted" | pass: exact round-trip, reattach with 0 native calls |
| 6 | MAJOR | `_refuse_executive_runtime_file` (casefolded given+resolved names, resolved-path casefold compare, `samefile` + `(st_dev,st_ino)`), `_ensure_schema` refuses foreign schema objects BEFORE DDL inside the same IMMEDIATE tx | `AuditReworkStoreTests::test_executive_guard_refuses_a_case_variant_name`, `::test_executive_guard_refuses_a_symlink_alias`, `::test_executive_guard_refuses_a_hardlink_alias_by_inode`; `StateStoreTests::test_store_refuses_an_existing_file_with_foreign_tables_before_ddl` (replaces the refuted coexistence test) | all four opened the file and ran DDL (not raised) | pass; Executive stand-in's tables unchanged |
| 7 | MAJOR | `T3McpToolPort.interrupt_run` sends `{threadId, runId, reason}` from `t3_native_run_coordinates(ref)` (suffix after the known thread id; never a naive split) and refuses a reply echoing another thread/run (unknown outcome) | `T3LivePortReworkTests::test_interrupt_payload_carries_thread_and_native_run_id`, `::test_interrupt_echoing_another_run_is_an_unknown_outcome` | API absent; pre-fix live port sent `t3_thread_interrupt({})` (`hasattr(ref,"thread_id")` always false) → newest turn (by reading) | pass |
| 8 | MINOR | `_merge_cursor` in both stores (`""` = no advance; decimal positions forward-only; kind change refused); compare-and-set UPDATE | `AuditReworkStoreTests::test_nm03_cursor_never_moves_backwards_across_writers`; `AuditReworkAdapterTests::test_nm03_status_read_with_empty_or_lower_cursor_never_rewinds` | `'4' != '7'` (stale writer rewound); `'' != '5'` (empty reset) | pass |
| 9 | MINOR | `_merge_cancel` (settled is final; first request kept) + `cancel()` returns the settled ledger without a second interrupt | `AuditReworkAdapterTests::test_second_cancel_never_downgrades_a_settled_record` | settled → `False` after 2nd cancel | pass: still settled, 1 interrupt |
| 10 | MINOR | `_merge_result` (identical re-record = no-op keeping the first `recorded_at`; different → `T3ResultLedgerConflictError`) | `AuditReworkStoreTests::test_result_ledger_is_write_once` | overwrite not refused | pass |
| 11 | MINOR | `SQLiteT3AdapterStateStore._transaction` (BEGIN IMMEDIATE; statement or COMMIT failure → ROLLBACK, tx closed, `T3StateStoreError`); every existence check / CAS / rowcount (`_expect_one`, `changes()`) inside the tx | `AuditReworkStoreTests::test_commit_failure_rolls_back_closes_tx_and_is_typed`, `::test_existence_check_and_rowcount_are_inside_the_transaction` | raw `sqlite3.OperationalError: injected failure on COMMIT`; 0-row UPDATE passed silently | pass; next write succeeds |
| 12 | MINOR | `start()`/`_replay_and_adopt`: receipt-persist failure after a successful native call → `T3LaunchEffectUnknownError` (intent kept) | `AuditReworkAdapterTests::test_store_failure_after_successful_launch_is_effect_unknown` | raw `sqlite3.OperationalError: disk I/O error` | pass |
| 13 | MINOR | `collect_result` → `_read_terminal` (port `read_result` if present, else head read; never the status cursor, never moves it); refuses `result_ref` equal to the thread/run id; `T3McpToolPort.read_result` names the exact run's final `assistant_message` item | `AuditReworkAdapterTests::test_collect_uses_a_terminal_read_not_the_status_cursor`, `::test_collect_refuses_a_bare_thread_id_as_result_reference`; `T3LivePortReworkTests::test_collect_reads_the_exact_runs_final_assistant_item`, `::test_collect_refuses_when_the_exact_run_has_no_final_reply` | "carries no canonical result reference" after a terminal poll; bare thread id accepted; live port: API absent | pass |
| 14 | NOTE | not changed: no runtime composes the adapter / produces the pre-ACK `WorkerRecoveryBinding` (selection is a deployment act) | — | — | open (unchanged) |
| 15 | NOTE | reads now take the store lock; `updated_ms` is wall-clock (`time.time_ns`); `creationSource`/ledger cap / per-checkout default path unchanged | covered by the suites above | — | partial |
| G | API | `SQLiteT3AdapterStateStore.open_read_only(path)` (`mode=ro` URI, `PRAGMA query_only`, no DDL, Executive guard + foreign-object refusal, writes refused typed). Director G's projection NOT switched (per assignment) | `AuditReworkStoreTests::test_open_read_only_reads_without_ddl_and_refuses_writes` | API absent | pass; file bytes unchanged |
| C-P1 | API | `T3ExecutionAdapter._verify_binding_join`: a v1.1 binding with `runtime_kind="t3-native"` (or any `operation_key`/`caller_namespace`) must carry `operation_key == derive_t3_client_request_id(binding)` and `caller_namespace ∈ {T3_REQUEST_NAMESPACE, t3_request_namespace(attested principal)}` → else `T3BindingJoinDriftError` before any claim | `AuditReworkAdapterTests::test_cp1_drifted_operation_key_is_refused`, `::test_cp1_foreign_caller_namespace_is_refused`, `::test_cp1_claim_seam_binding_launches_under_the_joined_key` (real `AttemptRegistry.claim_job` binding launches under its `operation_key`; corrupted copy refused) | drifted bindings launched (not raised) | pass |

**C-P2 / C-P3 — documented, not implemented.** C-P2 (launch containment of
`spec.workspace_path` inside `binding.workspace_ref`) needs a defined mapping from the
lease's opaque `workspace_ref` to a filesystem path, which the binding does not carry;
guessing containment from a string prefix would be wrong. C-P3 (persist
`t3_workspace_id`) belongs to the lease/workspace lifecycle on Director C's path, not this
adapter. Both stay proposals.

**Store schema.** `t3_adapter_runs` gains two NULLABLE columns, `spec_sha256` and
`claim_token` (added in place by `ALTER TABLE` on older files; the original columns and the
fleet projection's read slice are unchanged).

**Behavior changes callers must know.** (1) every launch needs a port with
`authenticated_namespace()`; (2) `clear_launch_attempt` requires `claim_token=`; (3) a second
`start()` for a run raises `T3LaunchClaimConflictError` (a `T3ExecutionAdapterError`);
(4) `collect_result` uses a terminal read; (5) opening an existing file that holds any foreign
table is refused.

**A2 harness (one separate final commit, receipts untouched).** Forced by (1)–(2):
`t3_durable_canary.py` `CrashHookStore.put_launch_receipt` forwards `claim_token`
(otherwise S1's receipt write would raise `TypeError` → EFFECT_UNKNOWN), and
`t3_live_proof.py` now binds the adapter's reference `T3McpToolPort` (token-attested
namespace, typed transport errors from `McpHttp`, exact-run interrupt, terminal read) and
imports THIS repo instead of the old lane worktree path. `CanaryLivePort` was NOT changed:
it still attests a token-hash principal and copies envelope echoes (audit #3 residue in the
proven canary harness; migrating it to `T3McpToolPort` is a follow-up that needs a live
re-run). No live T3 thread was launched by A3; the rework is PROVEN_BY_TEST.

**Verification (this lane, 2026-11-09).** `env -u PYTHONPATH /opt/homebrew/bin/python3.12
-m pytest -q tests/test_t3_adapter_durability.py tests/test_t3_execution_adapter.py
tests/test_t3_upstream_patch.py tests/test_session_bridge_t3.py tests/test_worker_adapter.py
tests/test_rev5_contracts_v1_1.py tests/test_t3_attempt_fleet_projection.py
tests/test_mmos_negative_matrix.py tests/test_executive_claim_job_placement_authority.py
tests/test_t3_durable_canary_receipt.py` → see the final commit message for the exact count.

## A4 — re-audit N1–N9, harness swap, live canary r2 (Director A4, 2026-11-09)

Source of findings: the distinct re-audit of A3's rework, carried as the authoritative
acceptance spec in the A4 brief (no separate re-audit document is in the repository; the
brief lists N1–N7 and N9 — **N8 was not provided to this lane** and is reported as such).
Base: `t3/t3-hermes-restart-recovery` @ `1fb4a9a6d`. Branch: `t3/a4-liveport-fixes-canary`.
Code commit used by the live run: `128e5e8be` (recorded in the r2 receipt and checked by its
pin test against the adapter file bytes at that commit).

**Fail-before method.** No stash: `git archive HEAD -- control_plane tests integrations config
common scripts ops pyproject.toml | tar -x -C /tmp/a4-failbefore/tree` (adapter byte-identical
to `HEAD`, verified with `cmp`). Baseline in the export: the required suite list = **275
passed, 1 xfailed** (the xfail is pre-existing). Overlaying ONLY the two new test files on the
pre-fix tree: **36 failed / 88 passed**; post-fix the same two files: **108 passed**.
Several N1/N4/N6 tests fail pre-fix as "API absent" (`TypeError` on `tool_error_code=`, missing
`T3LaunchSpecNotDurableError`/`adopt_stranded_launch`), so the reviewer's N1 double-launch was
also reproduced BEHAVIOURALLY on the pre-fix tree with pre-fix API only
(`/tmp/a4-failbefore/probe_n1.py`, donor server model): a post-commit `isError` → intent
cleared → a second OAuth client's `start` ACKed → **2 upstream threads for one logical run**.
Post-fix: `T3LaunchEffectUnknownError`, intent kept, second client
`T3LaunchClaimConflictError`, **1 thread**.

### Finding → fix → test

Tests below live in `tests/test_t3_execution_adapter.py` unless marked `[D]`
(`tests/test_t3_adapter_durability.py`). `DonorMcpServer` is a donor-faithful model (shared
upstream state, per-OAuth-session `client:<sid>` namespace, head paging with
`limit`/`hasMore`/`nextPosition`, `recentRuns` capped by `runLimit`, `t3_thread_wait` exact-run
lookup, declared-failure `isError` bodies).

| # | Sev | Fix (file:symbol) | Regression test(s) | Fail-before (pre-fix) | After |
|---|---|---|---|---|---|
| N1 | MAJOR | `t3_mcp_failure_is_definitive_refusal(exc, tool=)` — TOTAL (any exception ⇒ UNKNOWN), explicit allowlists from donor source: `_T3_MCP_PRE_DISPATCH_HTTP_STATUSES` = {400, 401, 403, 405, 406, 415}; JSON-RPC {−32700, −32600, −32601, −32602}; `_T3_MCP_PRE_DISPATCH_TOOL_ERROR_CODES` per mutating tool (launch: `capability_denied`, `parent_not_active`, `thread_not_found`, `target_required`, runtime/interaction escalation; interrupt: `capability_denied`, `parent_not_active`, `thread_not_found`). UNKNOWN: `invalid_request` (also returned AFTER `thread.create` committed: the initial `message.dispatch` is refused by `assertDispatchTargetEnabled` / `refuseAboveRuntimeModeCeiling`, both mapped to `invalid_request`), `orchestration_error` (`unavailable()` wraps post-commit failures), codeless `isError` (effect's internal-error text), HTTP 404 (effect McpServer replaces an already produced tool response with a bare 404 when the session ended mid-request), 408/409/422/429/499/5xx, non-`int` statuses, unknown tools. `t3_mcp_tool_error_code` parses only the donor declared-failure shape (`failureMode:"return"` → `content[].text` = JSON `{_tag:"OrchestratorMcpFailure", code, message}`); `T3McpTransportError.tool_error_code`; `T3McpToolPort._invoke`; `t3_live_proof.McpHttp.call_tool` carries the code | `A4ReauditN1ClassifierTests::test_n1_classifier_table` (42 rows), `::test_n1_tool_error_code_parses_only_the_donor_declared_failure_shape`; `A4ReauditLivePortTests::test_n1_is_error_after_commit_keeps_intent_and_replay_adopts_original`, `::test_n1_mcp_isError_with_an_allowlisted_code_is_a_clean_refusal`; `T3LivePortReworkTests::test_lost_replies_keep_the_intent_and_clean_refusals_roll_back` (A3 table corrected: 429 and codeless/`invalid_request` `isError` moved to UNKNOWN); `A4HarnessTests::test_mcp_http_carries_the_donor_failure_code`, `::test_canary_s5_injection_keeps_the_intent_and_replay_adopts` | API absent (`TypeError`); behavioural probe: intent cleared, 2 upstream threads | pass: intent kept, replay adopts the ORIGINAL thread, 1 thread; LIVE S5 |
| N2 | MINOR | `T3McpToolPort.read_result`: `complete` only when a page says `hasMore is False`; page budget exhausted, stalled/garbled `nextPosition` with `hasMore` ⇒ `result_ref=""` (refuse), the intermediate item is never named | `A4ReauditLivePortTests::test_n2_terminal_read_refuses_when_pages_run_out_with_has_more` (1,200-item timeline vs the 20×50 budget), `::test_n2_stalled_paging_with_has_more_refuses`, `::test_n2_terminal_read_names_the_final_item_of_a_complete_timeline` (900 items → `i-900`) | collect NOT refused (ledgered `step 1000`) | pass; LIVE S1/S2/S5 name the final assistant item |
| N3 | MINOR | `_refuse_foreign_adapter_table` (`PRAGMA table_info`: mandatory v1 columns + optional post-v1 columns, each with declared type / NOT NULL / pk) runs before ANY DDL in `_ensure_schema` (same IMMEDIATE tx) and in `open_read_only` | `[D] A4ReauditN3StoreTests::test_n3_same_name_foreign_tables_are_refused_before_any_ddl` (7 shapes; columns unchanged; read-only open refused too), `::test_n3_a_genuine_v1_table_is_accepted_and_upgraded_in_place` | all 7 opened and ran DDL | pass |
| N4 | MINOR | `_require_durable_spec` (encode → `_t3_spec_from_json` → sha compare; total) BEFORE the claim in `start`, and in `reattach` / `adopt_stranded_launch`; typed `T3LaunchSpecNotDurableError` (`code="T3_SPEC_NOT_DURABLE"`) | `A4ReauditAdapterTests::test_n4_undecodable_specs_are_refused_before_any_claim` (`isolation_roots=(["x"],)`, `result_schema_path=123`), `::test_n4_round_trip_drift_is_refused` (`workspace_path="…/./x"` str reloads as a normalized `Path`), `::test_n4_sqlite_store_never_persists_an_undecodable_spec` | intent persisted, launch called | pass: no row, no native call |
| N5 | MINOR | `T3McpToolPort._launch`: a `threadId` that is not this client's `t3_expected_launch_thread_id` ⇒ `T3UnknownOutcomeError`; `start()` ACKs only a receipt whose echo equals EXACTLY `(namespace, key)` (a missing echo is unproven too) | `A4ReauditLivePortTests::test_n5_unproven_thread_id_is_unknown_and_never_acked`, `::test_n5_adapter_never_acks_an_echo_free_receipt`; `T3LivePortReworkTests::test_receipt_echoes_come_only_from_the_upstream_thread_id` (updated) | ACKed with empty echoes | pass: intent kept, no receipt |
| N6 | NOTE | `T3ExecutionAdapter.adopt_stranded_launch` + optional port seam `T3McpToolPort.read_launch_thread` (see design note) | `A4ReauditAdapterTests::test_n6_any_session_adopts_a_stranded_launch_by_deterministic_read`, `::test_n6_absence_proves_nothing_and_keeps_the_intent`, `::test_n6_ports_without_the_read_seam_are_refused` | API absent | pass (PROVEN_BY_TEST only; not exercised live) |
| N7 | NOTE | `_require_run_state` applies `_require_namespace_continuity(native_call=False)` before ANY native call of `status` / `cancel` / `collect_result` | `A4ReauditAdapterTests::test_n7_status_cancel_collect_check_namespace_continuity` (different principal ⇒ `PRINCIPAL_MISMATCH`, unattested ⇒ `UNATTESTED`; zero native calls; no cancel record) | operated under a foreign principal | pass |
| N8 | — | not provided in the A4 brief; nothing changed for it | — | — | open (unknown content) |
| N9 | NOTE | reads request `runLimit=50` (donor max); a run absent from `recentRuns` while `thread.runCount` exceeds the listing is looked up EXACTLY with `t3_thread_wait {threadId, runId, timeoutMs: 1}` (donor `waitForThread`: `runs.find(id)`, `run_not_found` otherwise); a reply naming another run (restart continuation) or `run_not_found` stays unknown | `A4ReauditLivePortTests::test_n9_run_beyond_recent_runs_is_looked_up_exactly` (61 runs), `::test_n9_exact_lookup_never_guesses`, `::test_n9_listed_run_needs_no_lookup` | `RUNNING != SUCCEEDED` (run unlisted past 10) | pass (PROVEN_BY_TEST; live runs never exceeded 50) |
| D1 | MAJOR (A4-rated dry-run finding, not reviewer-rated) | `_T3_STATUS_MAP` gains the donor run vocabulary: `preparing`→STARTING, `waiting`→RUNNING, `interrupted`→CANCELLED, `rolled_back`→CANCELLED. Before, an interrupted run fell through to the non-terminal RUNNING default, so a requested cancel could NEVER settle (status stuck at CANCELLING) | `A4DryRunStatusVocabularyTests::test_d1_every_donor_run_status_maps_honestly`, `::test_d1_an_interrupted_run_settles_the_requested_cancel` | `interrupted`/`rolled_back`/`preparing` mis-mapped; never settled | pass; LIVE S4 settled from the run's own `interrupted` |

**N6 design note (what was and was not done).** Stranded claims still have NO expiry, by
design: an intent that may have an effect must never time out into a relaunch. `reattach`
is unchanged — a different principal is still refused `PRINCIPAL_MISMATCH` and NO replay
ever runs under another principal. The new, separate `adopt_stranded_launch` makes NO
mutating native call: it derives `t3_expected_launch_thread_id(<persisted client:<sid>>,
<persisted key>)` from the ORIGINAL persisted namespace (nothing but that command can mint
that id) and reads it through the port's read-only `read_launch_thread` under ANY session;
the launch run is the item whose `messageId == threadId` (donor: `MessageId.make(commandId)`).
Presence ⇒ the receipt (echo = the persisted identity the id proves) and ref are persisted
write-once; absence or an unidentified run proves NOTHING (the original launch may still be in
flight) ⇒ `T3LaunchEffectUnknownError`, intent kept. After adoption the run still belongs to
its original principal (N7): another principal can observe that it is no longer
EFFECT_UNKNOWN but cannot status/cancel/collect it. Legacy unqualified namespaces are refused
(`LEGACY_NAMESPACE_UNVERIFIABLE`).

### Harness swap (r2)

`CanaryLivePort` is gone. `t3_durable_canary.py` now runs the adapter's reference
`T3McpToolPort` (subclass `CanaryToolPort` adds ONLY call accounting and the S2 `os._exit`
hook after `super()._launch` returned) over `t3_live_proof.McpHttp` (typed
`T3McpTransportError` incl. `tool_error_code`). It attests `client:<sid>` from the token
claims, proves every receipt by `t3_expected_launch_thread_id`, never copies echo fields from
the request, and reads `recentRuns[].runId`. S1's crash stays in `CrashHookStore`; S5's lost
reply is a harness transport wrapper (`LostReplyTransport`). Fresh state root
`~/.hermes/profiles/engineering/cache/scratch/t3_durable_canary_r2/`; client tokens cached
0600 in distinct scratch files (`t3_canary_r2_client_{a,b}_token.txt`, never printed); a
durable 5-thread budget is reserved BEFORE each minting role. `t3_live_proof.obtain_mcp_access_token`
gained `token_path`/`label` parameters (defaults unchanged). Pre-flight: the whole driver was
dry-run twice against a scratch fake MCP server speaking the donor shapes (not committed) —
the first dry run exposed D1. New receipt `t3_durable_canary_receipt_r2.json` (r1 receipt
byte-identical, sha pinned); pin test `tests/test_t3_durable_canary_receipt_r2.py` (14 tests).

### Live canary r2 (m2studio, T3 0.1.7, `capacity_fabric` / `glm-5.3-flash`, adapter `128e5e8be`)

Outcome **DONE**; threads used **5 / 5** (budget exhausted exactly; nothing retried). All
roles exited as expected (prep 0, S1-P1 90, S1-P2 0, S2-P1 91, S2-P2 0, S3 0, S4 0, S5-P1 0,
S5-P2 0). Native-call counts are the `T3McpToolPort` port counts per process.

| Scenario | Thread | Evidence | Result |
|---|---|---|---|
| S1 crash after receipt | `mcp:launch:c15936fe…5a27` | P1: launch 1, `upstream_echo_proven=true`, receipt COMMITTED, exit 90. P2: reattach with **0 native calls** (retained ref); second `start` refused `T3LaunchClaimConflictError` with **0 native calls**; `RUNNING → SUCCEEDED`; `collect_result` ledgered the run's FINAL assistant item (`…native-item:a4532c9d…`, cross-checked by a full head read); `T3-CANARY-OK r2-s1`; thread runCount 1 | PASS |
| S2 crash after launch, before receipt | `mcp:launch:b0d6a873…04d8` | P1: launch 1, exit 91 after the native launch returned. P2 (same OAuth client, new process/MCP session): replay 1, launch 0, **`upstream_echo_proven=true`**, thread == P1's, **launch count total 1**, thread runCount 1; `T3-CANARY-OK r2-s2` | PASS |
| S3 real second OAuth client | `mcp:launch:4bc1eccd…a225` | second pairing ⇒ different `client:<sid>` (sha256 projections differ). Adapter: reattach S1/S2 ⇒ **`PRINCIPAL_MISMATCH`**, `start` S1/S2 ⇒ `T3LaunchClaimConflictError`, all **0 native calls**. Upstream: the SAME clientRequestId (S1's) launched directly by client B with NO message minted a DIFFERENT thread equal to client B's derivation (`runId: null` — no model turn), while client A's derivation equals S1's thread: **namespace = OAuth client, live** | PASS |
| S4 exact-run interrupt | `mcp:launch:b15a5d33…97fa` | `STARTING, RUNNING` before the interrupt; payload carried `threadId` + native `runId`, upstream echo verified; ledger after cancel: requested, NOT settled; then `CANCELLING → CANCELLED` with the settle recorded only after the exact run's own status read `interrupted` (≈5 s); launch 1, interrupt 1, reads 5 | PASS |
| S5 lost reply after commit | `mcp:launch:2a6d4267…debe` | P1: the real launch COMMITTED (transport saw the thread, matching client A's derivation), harness then raised the donor's `isError` `orchestration_error` ⇒ classifier UNKNOWN ⇒ `T3LaunchEffectUnknownError`, **intent kept, no receipt**. P2: replay 1, launch 0, `upstream_echo_proven=true`, **adopted the original committed thread, launch count total 1**, thread runCount 1; `T3-CANARY-OK r2-s5` | PASS |

Live observations (recorded, not inferred):

1. **r1 finding 4 re-attributed.** r1 reported "CANCELLING can outlast a 420 s poll". With D1
   fixed, S4 settled ≈5 s after the interrupt from the run's own `interrupted` status — the r1
   symptom matches the adapter vocabulary gap (D1), not slow upstream settling.
2. r1 finding 3 (interrupted scratch thread unreadable on the exact-run path) did NOT
   reproduce: the S4 thread read normally right after settling.
3. Upstream's thread-row `settled` flag stayed `false` after the run was `interrupted`; it is a
   thread-level flag, not run termination — the ledger's settle is evidenced by the exact
   run's status, never by that flag.
4. A fresh launch first reports run status `preparing` (now mapped to STARTING).
5. Upstream run ids are `run:thread:<url-encoded threadId>:ordinal:<n>`; item ids for this
   provider instance are `turn-item:provider:claudeAgent:native-item:<uuid>`.
6. Harness reporting defect: r2's `elapsed_s` under S1-P2 `reattach` / S2-P2 `recovery` was
   computed at role END (reattach start → after the terminal wait), not the reattach call
   alone; fixed after the run (`reattach_elapsed_s`). The receipt is left exactly as the live
   driver wrote it.

### Evidence scope — still SOURCE_ONLY / NOT PROVEN

- Upstream admission patch: SOURCE_ONLY (never booted in a live T3).
- Audit #14: no runtime composes the adapter or produces the pre-ACK `WorkerRecoveryBinding`;
  `t3-native` stays UNSELECTED (selection is a deployment act).
- N6 adoption, N9 exact-run lookup (no live thread exceeded 50 runs), N3/N4 refusals, D1's
  `rolled_back` mapping: PROVEN_BY_TEST only.
- N1 live coverage is the S5 harness injection of the donor's post-commit `isError` shape — a
  simulated lost reply after a REAL commit, not an observed upstream failure; the HTTP/JSON-RPC
  allowlists are proven by test and by donor reading only.
- N8: unknown (not provided).

**Verification (2026-11-09).** `env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q
tests/test_t3_adapter_durability.py tests/test_t3_execution_adapter.py
tests/test_t3_upstream_patch.py tests/test_session_bridge_t3.py tests/test_worker_adapter.py
tests/test_rev5_contracts_v1_1.py tests/test_executive_claim_job_placement_authority.py
tests/test_t3_durable_canary_receipt.py tests/test_t3_durable_canary_receipt_r2.py
tests/test_t3_attempt_fleet_projection.py tests/test_workspace_t3_attempt_fleet_read.py
tests/test_mmos_negative_matrix.py` → **315 passed, 1 xfailed** (xfail pre-existing at base).
