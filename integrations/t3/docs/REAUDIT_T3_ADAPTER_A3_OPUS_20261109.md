# Distinct re-audit — A3 rework of the T3 durable adapter (`70dabba15..05cc5c7d4`)

Reviewer: Claude Opus 5.5, READ_ONLY, capacity_fabric path, a different session from the A3 author. Technical
assessment, not a GitHub approval. Verdict: **NEEDS_REWORK (narrow)** — 11 of 13 fixable findings FIXED_CONFIRMED
under attack; one MAJOR remains (N1) plus minors N2–N5 and notes N6–N10.

Ran: 8 suites → 182 passed / 43 subtests; patch `git apply --check` clean on the pinned clone, colocated vitest 13/13
(fail-before 2/4 with `Layer.build` reverted); node probe on effect 4.1.2 (8 combinations: new style builds the shared
dependency once in every case); python probes under /tmp: 8-process barrier-synchronised start race × 6 rounds (1 started,
7 `T3LaunchClaimConflictError`, 1 upstream thread, mixed principals included), 5 crash/kill scenarios, claim-token forgery,
4 namespace attacks, 6 lost-reply cases, 7 adversarial spec types, old-schema migration, 7 Executive-file aliases + a
same-name foreign table, 6 processes × 150 concurrent writes, a 1,200-item terminal read, 3 Python-vs-Node thread-id vectors
(3/3 match the donor's JSON.stringify + lowercase-hex derivation).

| # | Status | Evidence |
|---|---|---|
| 1 | FIXED_CONFIRMED | exactly-one start across processes; kill inside the claim tx rolls back; next process claims, 1 thread |
| 2 | FIXED_CONFIRMED | node probe + vitest fail-before/after |
| 3 | FIXED_CONFIRMED (adapter + `T3McpToolPort`) | unattested launch refused; other principal → `PRINCIPAL_MISMATCH`; `CanaryLivePort` still old (by design) |
| 4 | **PARTIAL** | timeouts/resets/502/-32603/unclassified keep the intent; tool `isError` after commit, HTTP 499, non-int status CLEAR it → N1 |
| 5 | FIXED_CONFIRMED | non-normalized str/Path/int/nested specs reattach; exceptions → N4 |
| 6 | FIXED_CONFIRMED | `Executive.SQLITE3`, `ſ` alias, relative path, 3-link symlink chain, hardlink all refused → N3 for same-name foreign table |
| 7 | FIXED_CONFIRMED (not live) | interrupt sends `{threadId, runId, reason}` |
| 8–12 | FIXED_CONFIRMED | cursor non-decreasing under 6 writers; settled cancel final; result write-once (1 ok / 5 conflicts); kill-in-tx rollback clean; receipt I/O error → EFFECT_UNKNOWN, intent kept |
| 13 | FIXED_CONFIRMED | terminal read has defect N2 |
| 14 | NOT_FIXED | no runtime code composes the adapter/store/`T3McpToolPort` |
| 15 | PARTIAL | wall-clock `updated_ms`, locked reads; ledger cap and per-checkout default path unchanged |

Invariants: 1 PROVEN_BY_PROBE (pre-ACK binding still test-built, #14); 2 PROVEN for launch/replay only (N7); **3 REFUTED
for the live port (N1)**; 4–6, 9, 10 PROVEN_BY_PROBE; 7 PROVEN but N2 can lock a wrong result; 8 PROVEN for well-typed
specs and legacy rows (N4); 11 PROVEN_BY_TEST + PROBE.

## New findings
- **N1 MAJOR** `t3_execution_adapter.py:2881-2884` + `t3_live_proof.py:321-330`: post-commit `isError` / HTTP 499 /
  non-int status → clean refusal → intent cleared → retry under a new MCP session launched **2 upstream threads**
  (reproduced). Donor: create-thread errors "can wrap post-message reads and prove nothing alone", surface as
  `orchestration_error`, MCP server returns handler failures as `isError: true`. Fix: mutating calls treat `isError` as
  UNKNOWN except a proven pre-dispatch code allowlist; allowlist specific 4xx codes only; classifier total (any exception ⇒
  UNKNOWN).
- **N2 MINOR** `_read_terminal` :3100-3127 returns the last assistant item seen when pages run out with `hasMore` true;
  an intermediate item was ledgered write-once and the final answer refused. Fix: refuse (`result_ref=""`).
- **N3 MINOR** foreign-table check by name only (:1118, :1291-1301); same-name foreign table received `ALTER TABLE`. Fix:
  `PRAGMA table_info` column-set check before any DDL.
- **N4 MINOR** undecodable specs (`isolation_roots=(["x"],)`, `result_schema_path=123`) persisted before launch (:1843) →
  `load_run` raises forever; reattach/status/cancel impossible for a live thread. Fix: round-trip decode + sha before claim.
- **N5 MINOR** `start()` (:3018-3031, :1902) ACKs a receipt with empty echoes when the token's session differs from the
  transport session. Fix: mismatching `threadId` derivation ⇒ `T3UnknownOutcomeError`.
- **N6 NOTE** no claim expiry; a crash in the claim→receipt window is recoverable only under the same `client:<sid>`;
  donor MCP sessions last 30 days, no refresh. Suggestion: adopt by deterministic thread-id read under any session, no replay.
- **N7 NOTE** namespace continuity checked only on reattach (status/cancel/collect accept any principal).
- **N8 NOTE** `claim_token` readable via `load_run`; race guard, not a capability.
- **N9 NOTE** run status looked up only in the 10 most recent runs.
- **N10 NOTE** `22df69ee6` redacted `store.path` inside the r1 canary receipt (sha256 fields unchanged).

Harness: no receipt JSON changed in the range; wrapper store only forwards `claim_token`. Hard constraints: all 9 files in
A3's scope; no secrets/identity literals; `_NORMALIZED_V7_SCHEMA_DIGEST` untouched.

## Live proof still owed (reviewer)
1. Fix N1 (and N2). 2. Replace `CanaryLivePort` with `T3McpToolPort` (attests `client:<sid>`, no request-copied echoes,
reads `recentRuns[].runId`); fresh store. 3. Re-run S1/S2, a REAL second OAuth client (`t3 auth pairing create`) →
`PRINCIPAL_MISMATCH` with 0 native calls and a different upstream thread for the same key, exact-run interrupt + echo,
`collect_result` names the final item, lost-reply injection → replay adopts the original thread. 4. Admission patch live
boot with `MASTERMIND_ADMISSION_ENDPOINT` unset (unknown, not done).

**Integrator disposition (Fable):** delegated to Director A4 (Opus) — N1–N9 fixes with fail-before tests, harness swap,
live re-run with ≤5 threads, new receipt `t3_durable_canary_receipt_r2.json`.
