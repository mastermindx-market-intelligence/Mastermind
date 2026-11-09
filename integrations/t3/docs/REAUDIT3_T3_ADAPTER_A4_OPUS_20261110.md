# Distinct re-audit #3 — A4 delta of the T3 durable adapter (`1fb4a9a6d..b5bed5d3f` + integrator reconciliation)

Reviewer: Claude Opus 5.5, READ_ONLY, capacity_fabric path, distinct from the A4 author. Technical assessment, not a
GitHub approval. Verdict: **NEEDS_REWORK (narrow)** — every A4 fix holds under attack; one latent MAJOR on an older
recovery path (R1) and the required suite red at HEAD by one stale expectation (R3, already fixed in `07748bdbe`).

Ran: required 10-file suite 242 passed / 1 failed (R3) / 117 subtests; A4 extra suites + guard policy 418 passed / 1 xfail;
159 probe checks against the real classes (153 as expected; 3 real findings R1×2, R2×1; 3 reviewer mis-expectations where
the adapter was right): N1 classifier matrix 5 tools × 17 codes + 18 port error paths (65/65); replay/adopt 16/18; 4 kill
points × 2 orderings over shared SQLite + 8-process mixed-principal barrier race × 5 rounds (28/29); N2/N9 10/11; N3/N4/N5
21/23; binding join 13/13. Donor source read at pin `07704468` (handlers, access checks, OrchestratorMcpService,
ThreadManagementService, PeerForwarding/PeerMcpClient, effect McpServer.ts).

| # | Status | Evidence |
|---|---|---|
| N1 | FIXED_CONFIRMED (local MCP path) | reviewer's own derivation from the donor equals A4's allowlist (launch: capability_denied, parent_not_active, thread_not_found, target_required, both escalation codes; interrupt: capability_denied, parent_not_active, thread_not_found); HTTP 400/401/403/405/406/415 pre-handler; 404 correctly UNKNOWN (McpServer.ts:1979); -32602 pre-dispatch only; classifier total |
| N2 | FIXED_CONFIRMED | 999/1000 items name the final item; 1001/1200, stalled nextPosition, missing hasMore refused, nothing ledgered |
| N3 | FIXED_CONFIRMED | 7 foreign same-name shapes refused on rw and ro open; legacy v1 file: ro open no DDL, rw upgrade in place, row reattaches with 0 calls |
| N4 | FIXED_CONFIRMED | 4 undecodable specs refused before claim, 0 calls |
| N5 | FIXED_CONFIRMED | non-derived threadId → UNKNOWN; echo-free replies never ACKed |
| N6 | FIXED_CONFIRMED by probe (not live) | adoption under B: 0 mutating calls, receipt under original A; B then PRINCIPAL_MISMATCH everywhere; forged bindings refused |
| N7 | FIXED_CONFIRMED | note: legacy unqualified-namespace rows still accept status/cancel/collect from any principal |
| N8 | NOT_FIXED (not assigned) | `claim_token` readable via `load_run`; store-direct callers only |
| N9 | FIXED_CONFIRMED (minor R2) | 60-run thread → exact lookup `timeoutMs: 1`; donor `t3_thread_wait` returns `{runId,status,timedOut}` |
| D1 | FIXED_CONFIRMED | all 10 donor run statuses mapped; terminal set equals donor `isTerminalRunStatus`; live S4 settled from `interrupted` |

Invariants: 1 PROVEN_LIVE on the durable-store path (`s1.p2.reattach.native_calls=0`, `s2.p2.native_launch_calls_total=1`,
`s5.p2.adopted_original_committed_thread=true`) + PROVEN_BY_PROBE across the kill matrix, **REFUTED on the no-store-row
path (R1)**; 2 PROVEN_LIVE (`s3 PRINCIPAL_MISMATCH`, `adapter_port_calls=0`), REFUTED on the no-row path; 3 PROVEN_BY_PROBE
(live only via harness-injected failure after a real commit); 4 PROVEN_BY_PROBE (R4 edge); 5 PROVEN_BY_TEST; 6 PROVEN_LIVE
(`s4.interrupt.payload_run_matches`, settled from exact-run `interrupted`); 7 PROVEN_LIVE (final assistant item) + probe;
8 PROVEN_BY_PROBE; 9 PROVEN_BY_PROBE (1 started / 7 conflicts / 1 upstream thread every round), REFUTED across separate
stores (R1); 10 PROVEN_BY_TEST + N3 probes; 11 PROVEN_BY_TEST only (live boot NOT_COVERED).

## New findings
- **R1 MAJOR (latent, from `deb6868967`)** `reattach` no-store-row path (~:2636-2654 + `_reconstruct_envelope`): with no
  row, the launch is rebuilt under the CURRENT port's principal and `replay_launch` (a real `t3_thread_launch`) is called
  before any proof the principal is the original; probe: launches 1→2, upstream threads 1→2 under client B against an
  empty/other store (the per-checkout default path makes this reachable). Fix: no mutating call unless
  `t3_expected_launch_thread_id(attested, key) == original.provider_session_id`; regression test with zero mutating calls.
- **R2 MINOR** `_lookup_exact_run`: donor `t3_thread_wait` reports `runOutcome(run)` (restart-cut completed run →
  `interrupted`) while `recentRuns` reports raw status → a run can read SUCCEEDED inside the last 50 and CANCELLED past 50;
  second `collect_result` then raises `T3ResultLedgerConflictError` (fails closed, state not stable). Fix: freeze terminal
  state from the ledger, or normalise the two vocabularies.
- **R3 MINOR** stale nm15 expectation in the E2E (fixed `07748bdbe`).
- **R4 NOTE** donor `PeerMcpClient.ts:184-195` retries 404 by renewing the session and maps 401 → `capability_denied`, so
  an allowlisted code can follow a commit on a linked peer. Not live (no composition sets `environmentId`). Fix: refuse
  `environmentId` in `launch_arguments` before sending.
- **R5 NOTE** receipt: no tokens/`client:` values/user paths; adapter (`3b931f5b…`) and harness (`ed52a565…`) digests match
  `128e5e8be`; r2 file digest not pinned (r1's is); "launch count 1" counts adapter port operations — upstream received the
  launch plus one idempotent replay in S2/S5; the exactly-once evidence is the same thread id + `thread_run_count=1`; S3
  derivations appear as harness booleans only; HEAD's adapter ≠ live-run adapter (binding-join hunk only, verified by probe).
- **R6 NOTE** `McpHttp` does not re-initialize its MCP session after a 404; after a T3 server restart every mutating call is
  EFFECT_UNKNOWN until a new process runs (safe, blocks progress).

Binding-join relaxation (`33ae86792`): sound — the pre-relaxation claim stamped a principal-agnostic constant, so admitting
an empty namespace removes no binding that existed; non-empty foreign namespaces still refused with 0 calls; `operation_key`
byte-exact. Hard constraints hold (scope, `_NORMALIZED_V7_SCHEMA_DIGEST`, r1 receipt `e18afad9…` byte-identical, no new
identity literals).

## Remaining gaps before DONE_WHEN 4 is PROVEN_LIVE (reviewer)
1. Fix R1 + regression test. 2. R3 (done). 3. Boot the admission patch live with `MASTERMIND_ADMISSION_ENDPOINT` unset
(invariant 11 has no live coverage). 4. #14: a runtime composing the SQLite store, `T3McpToolPort` and a real pre-ACK
recovery-binding producer; decide the default store path (per-checkout default is what makes R1 reachable). 5. Select the
`t3-native` route. 6. Thin live coverage: N1 only via injected failure; N6/N9 never live; HEAD's adapter bytes never ran
live — re-run the canary at the final head or attach the live claim to `128e5e8be`. 7. Optional: R2, R4.

**Integrator disposition (Fable):** R1 fixed on the build branch (no-row replay proves `expected_launch_thread_id(attested,
key) == original thread` via the port's derivation before any mutating call; `PRINCIPAL_MISMATCH` / `PRINCIPAL_UNPROVABLE`
typed refusals; 3 regression tests incl. a principal-qualified fake upstream); R4 fixed (`T3McpToolPort` refuses
`environmentId` at construction and before send); R5 r2 receipt bytes pinned; R3 fixed earlier. R2/R6 recorded, not fixed.
Live claim attaches to adapter `128e5e8be` + live-run harness; HEAD bytes are test-proven only. A short distinct re-check of
the R1/R4 delta is requested before the row is called reviewed.

## Distinct re-check of the R1/R4/R5 delta (`d2c9429e5`) — Opus READ_ONLY, 2026-11-10

Verdict **ACCEPT_WITH_MINORS**: R1/R4/R5 FIXED_CONFIRMED; invariants 1/2/9 on the no-row path PROVEN_BY_PROBE (24/24 probe
checks with the real `T3ExecutionAdapter` + `SQLiteT3AdapterStateStore` + `T3McpToolPort.from_access_token` over a shared
upstream fake; 12 concurrent recoveries on separate empty stores → 1 upstream thread; Python derivation byte-equal to node
`JSON.stringify` on 4 tricky vectors). `environmentId` confirmed the only forwarding knob in the donor. Residuals (not
introduced by R1): a caller-forged `provider_session_id` or a port attested as A over a transport authenticated as B can
still cause one replay-then-refusal — the existing store/claim locality gap and composition precondition (M2).
Minors applied by the integrator in the same session: **M1** regression test through the REAL `T3McpToolPort` with two
OAuth sessions (`ReCheckR1LivePortNoRowTests`); **M2** composition precondition recorded in the port docstring (build only
with `from_access_token` over the same token the transport sends); **N1** no-row recovery under the proven principal now
adopts the original thread by a READ (`_adopt_original_by_read`, zero mutating calls) when the port offers
`read_launch_thread`, replay only as fallback; **N2** prover exceptions wrapped as `PRINCIPAL_UNPROVABLE`; protocol
docstring lists the optional `expected_launch_thread_id`. Not covered: donor deleted-thread replay semantics; no live run of
HEAD bytes (live claim attaches to adapter `128e5e8be`).
