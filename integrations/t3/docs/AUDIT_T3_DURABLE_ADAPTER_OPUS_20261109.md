# Distinct technical audit — T3 durable adapter (exactly-once / durable recovery)

- **Reviewer:** Claude Opus 5.5, READ_ONLY, on the capacity_fabric path (distinct from the
  authors: GLM-5.3 Director A + Fable principal). Technical assessment only — **not** a
  formal GitHub approval.
- **Scope reviewed:** `bbfad42da..d1ba1eb74` — `control_plane/t3_execution_adapter.py`,
  `tests/test_t3_adapter_durability.py`, `tests/test_t3_execution_adapter.py`,
  `integrations/t3/live_proof/t3_live_proof.py`, `integrations/t3/upstream_patches/`.
- **Verdict:** **NEEDS_REWORK**. Rework commissioned to Director A3 (Opus, implementation)
  from `67e01ab26`; finding→fix→test mapping lands in `LANE_T3_DIRECTOR_A.md`.
- Every CONFIRMED item was reproduced by the reviewer with throwaway probes against the real
  classes (and effect@4.1.2 for the patch). Nothing in the repository was changed by the audit.

## Findings (severity, location at d1ba1eb74, scenario, fix)

1. **BLOCKER** — Two processes can both launch the same run (inv 9). CONFIRMED.
   `start()` reads with `load_run` outside any transaction, calls `binding_source`, then
   upserts the intent (`INSERT … ON CONFLICT DO UPDATE`, :839-865); `BEGIN IMMEDIATE` covers
   only that write. Two threads with separate connections and a 0.3 s `binding_source` →
   `launch_thread` called twice, both ACKed. With two principals the row ends as last-writer;
   a clean refusal by A can `clear_launch_attempt` B's intent before B's receipt upsert
   recreates a receipt-only row. Fix: atomic claim (`ON CONFLICT DO NOTHING` in
   `BEGIN IMMEDIATE`, refuse on `changes()==0`), never upsert intents, claimant-conditional
   clear, two-connection race test.
2. **BLOCKER** — Disabled admission is not a pure passthrough at composition level (inv 11).
   CONFIRMED mechanism / PLAUSIBLE in the real graph. `decorateServiceLayer`
   (patch :769-785) nests `Layer.build(incumbent)`; in effect 4.1.2 `Layer.build` forks the
   memo map, so dependency layers first built inside the fork are rebuilt by the outer graph
   before the `mode === "disabled"` check. Probe: shared Store built twice under
   `mergeAll(decorated, undecorated)`. Impact: duplicate singletons (ProjectionStore,
   CommandOutputHub, Orchestrator, TextGeneration) possible with the endpoint unset.
   Fix: never `Layer.build` inside a decorator; take the incumbent service as a dependency
   provided by the outer graph; add a built-exactly-once composition test.
3. **MAJOR** — Namespace isolation fails open; the only real port does nothing (inv 2).
   CONFIRMED. `if not principal: return` (:1310-1312) skips continuity when the port cannot
   attest a principal; the live port has no `authenticated_namespace`, never sends a
   namespace upstream, echoes `request_namespace`/`client_request_id` from the envelope
   (so crash-zone echo checks are tautological), and its `replay_launch` is `launch_thread`.
   Fix: refuse replay without attestation when the persisted namespace names a principal;
   selectable ports must attest the OAuth client identity; echoes must come from upstream.
4. **MAJOR** — Live-port lost replies become clean refusals (inv 3/4). By reading. All
   transport exceptions → `RuntimeError` → adapter rolls the intent back. Fix: map timeouts /
   resets / 5xx-after-send to `T3UnknownOutcomeError`.
5. **MAJOR** — Spec round-trip changes types; post-restart reattach refused (inv 8/1).
   CONFIRMED. `allowed_artifact_paths` stored as str, loaded as `Path`; sha drifts; reattach
   fails "launch spec drifted". Fix: exact per-field typing or stored original-spec sha;
   round-trip test with non-normalized paths.
6. **MAJOR** — `executive.sqlite3` guard bypassable (inv 10). CONFIRMED. Name-only,
   case-sensitive compare; `Executive.sqlite3` on APFS and symlink aliases open the real
   file and run DDL. Fix: `resolve()` + `samefile`/(dev,ino) + casefold; refuse any existing
   file with foreign tables before DDL.
7. **MAJOR** — Live port interrupt is not exact-run (inv 6). `hasattr(ref, "thread_id")` is
   always false → `t3_thread_interrupt({})`; without `runId` upstream interrupts the newest
   turn. Fix: send `threadId=ref.provider_session_id` + native `runId` from the receipt.
8. **MINOR** — Cursor can go backwards (`next_cursor=""` resets; concurrent writers).
9. **MINOR** — Second `cancel()` downgrades a settled record.
10. **MINOR** — Result ledger is last-write-wins.
11. **MINOR** — COMMIT failure leaves the tx open; existence checks outside tx; rowcount
    ignored.
12. **MINOR** — Store failure after a successful launch surfaces raw sqlite3 error, not
    `T3LaunchEffectUnknownError`.
13. **MINOR** — `collect_result` reads from the incremental cursor; live `last_text` may be
    empty; `result_ref` falls back to `thread_id` so the refusal never triggers.
14. **NOTE** — No real producer of the pre-ACK `WorkerRecoveryBinding`; adapter not composed
    into any runtime (tests, registry, live proof only).
15. **NOTE** — `updated_ms` uses `monotonic_ns`; reads bypass the lock; patch admission
    ledger in-memory/1024-capped; `creationSource` forwarded but must not be authority;
    default state path is per-checkout.

## Invariant status at d1ba1eb74 (reviewer's table)

| # | Invariant | Status |
|---|---|---|
| 1 | Restart before/after ACK keeps launch count 1 | PROVEN_BY_TEST single-process; not covered concurrently (#1); breaks for #5 specs; pre-ACK binding test-built (#14) |
| 2 | Different namespace refused | PROVEN_BY_TEST only for attesting ports; fails open otherwise (#3) |
| 3 | Unknown outcome keeps intent | PROVEN_BY_TEST in adapter; defeated by live port mapping (#4) |
| 4 | Clean refusal rolls back only without receipt | PROVEN_BY_TEST; cross-process deletion possible (#1) |
| 5 | Cursor forward-only, durable | PROVEN_BY_TEST except #8 |
| 6 | Cancel honest + exact-run | honesty PROVEN_BY_TEST (#9); exact-run broken in live port (#7) |
| 7 | Result ledgered before receipt | PROVEN_BY_TEST; overwritable (#10) |
| 8 | Exact round-trip | NOT_COVERED; refuted (#5) |
| 9 | No cross-process double launch | NOT_COVERED; refuted (#1) |
| 10 | Never opens executive.sqlite3 | PROVEN_BY_TEST lowercase only; bypassed (#6) |
| 11 | Patch: interrupts never blocked / disabled passthrough / no request-field authority | interrupts + authority PROVEN_BY_READING; passthrough refuted at composition (#2) |
